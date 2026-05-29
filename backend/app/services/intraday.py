"""
Intraday orderflow confirmation service.

Fetches today's 1-minute bars from yfinance and evaluates five signal checks
adapted from the intraday_orderflow_system, tuned for US equities:

  1. gap_ok          — opening gap ≤ 4%
  2. breakout_held   — price held above morning high (9:30–11:30) for ≥ 20 min
  3. orderflow_ok    — aggressive buy sequences ≥ 2, ask levels cleared ≥ 3,
                       bid replenishment ≥ 2
  4. pullback_ok     — pullback from session high ≤ 1.5%, volume contracted
  5. spoofing_ok     — no sharp high-volume reversals (≤ 1 event)

Data source: yfinance 1-minute bars (last 7 days available).
Runs in a thread executor to avoid blocking the async event loop.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Literal

import pandas as pd
import yfinance as yf
from pydantic import BaseModel

logger = logging.getLogger("market_sentinel_intraday")

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class IntradaySignals(BaseModel):
    gap_ok: bool
    breakout_held: bool
    orderflow_ok: bool
    pullback_ok: bool
    spoofing_ok: bool


class IntradayResult(BaseModel):
    ticker: str
    confirmed: bool
    signals_passed: int          # 0-5
    signals: IntradaySignals
    open_gap_pct: float
    session_high: float
    current_price: float
    pullback_from_high_pct: float
    volume_ratio: float          # afternoon vs morning avg per-minute volume
    breakout_hold_minutes: int
    entry_price: float | None
    stop_price: float | None
    target_price: float | None
    snapshot_time: str
    note: str


class IntradayJobState(BaseModel):
    status: Literal["idle", "running", "completed", "failed"]
    progress_scanned: int = 0
    progress_total: int = 0
    results: dict[str, IntradayResult] = {}   # keyed by ticker
    started_at: str | None = None
    completed_at: str | None = None
    error: str | None = None


class IntradayRunRequest(BaseModel):
    user_id: str
    tickers: list[str]


# ---------------------------------------------------------------------------
# Signal computation (pure pandas, runs in thread executor)
# ---------------------------------------------------------------------------

_MORNING_END = "11:30"
_ENTRY_START = "13:00"
_ENTRY_END = "15:00"
_MAX_GAP_PCT = 0.04
_MIN_HOLD_MINUTES = 20
_MIN_BUY_SEQUENCES = 2
_MIN_ASK_LEVELS = 3
_MIN_BID_REPLENISH = 2
_MAX_PULLBACK_PCT = 0.015
_MAX_PULLBACK_VOL_RATIO = 0.75
_MAX_SPOOFING = 1
_FIRST_TP_R = 2.0
_STOP_BUFFER_PCT = 0.003


def _compute_result(ticker: str, spy_return: float) -> IntradayResult:
    """Fetch 1-min bars and evaluate all five checks. Blocking – run in executor."""
    try:
        tk = yf.Ticker(ticker)
        df: pd.DataFrame = tk.history(period="2d", interval="1m", prepost=False)
    except Exception as exc:
        return _failed_result(ticker, f"yfinance fetch error: {exc}")

    if df is None or df.empty:
        return _failed_result(ticker, "no intraday data available")

    # Normalise index to US/Eastern naive timestamps
    if df.index.tz is not None:
        df.index = df.index.tz_convert("America/New_York").tz_localize(None)

    # Keep only today (most recent trading session)
    last_date = df.index.normalize().max()
    df = df[df.index.normalize() == last_date].copy()
    if df.empty:
        return _failed_result(ticker, "no bars for the current session")

    df["minute"] = df.index.strftime("%H:%M")
    df = df[df["minute"] >= "09:30"].copy()
    if len(df) < 10:
        return _failed_result(ticker, "too few intraday bars")

    # --- Context values ---
    prior_close = float(df["Close"].iloc[0] / (1 + df["Close"].pct_change().iloc[0]))
    open_price = float(df["Open"].iloc[0])
    open_gap_pct = (open_price - prior_close) / prior_close if prior_close > 0 else 0.0

    morning = df[df["minute"] <= _MORNING_END]
    morning_high = float(morning["High"].max()) if not morning.empty else open_price

    # Snapshot at entry window (use latest bar ≤ 15:00, or last bar)
    entry_df = df[df["minute"] <= _ENTRY_END]
    snap = entry_df.iloc[-1] if not entry_df.empty else df.iloc[-1]
    current_price = float(snap["Close"])
    snapshot_time = str(snap["minute"])

    session_high = float(df[df["minute"] <= snapshot_time]["High"].max())
    pullback_from_high = (session_high - current_price) / session_high if session_high > 0 else 0.0

    # Volume ratio: afternoon (13:00–15:00) avg per-min vs morning (9:30–11:30)
    afternoon_df = df[(df["minute"] >= _ENTRY_START) & (df["minute"] <= _ENTRY_END)]
    morning_vol = float(morning["Volume"].mean()) if not morning.empty else 1.0
    afternoon_vol = float(afternoon_df["Volume"].mean()) if not afternoon_df.empty else 0.0
    volume_ratio = afternoon_vol / morning_vol if morning_vol > 0 else 1.0

    # How many minutes price held above morning_high
    above_df = df[df["minute"] >= "11:30"]
    held_minutes = int((above_df["Close"] > morning_high).sum())

    # --- Check 1: gap ---
    gap_ok = open_gap_pct <= _MAX_GAP_PCT

    # --- Check 2: breakout hold ---
    breakout_held = (
        morning_high > 0
        and current_price > morning_high
        and held_minutes >= _MIN_HOLD_MINUTES
    )

    # --- Check 3: orderflow (approximated from 1-min bars) ---
    snap_df = df[df["minute"] <= snapshot_time].copy()

    # Aggressive buy sequences: consecutive up-close minutes (close > open)
    aggressive_buy_sequences = 0
    run_len = 0
    for is_up in (snap_df["Close"] > snap_df["Open"]):
        if is_up:
            run_len += 1
        else:
            if run_len >= 2:
                aggressive_buy_sequences += 1
            run_len = 0
    if run_len >= 2:
        aggressive_buy_sequences += 1

    # Ask levels cleared: price movement above breakout in $0.01 increments
    ask_levels_cleared = 0
    if morning_high > 0:
        highest_close = float(snap_df["Close"].cummax().iloc[-1]) if not snap_df.empty else current_price
        ask_levels_cleared = max(0, int(round((highest_close - morning_high) / 0.01)))

    # Bid replenishment: successive bars where Low ≥ prev Low, vol ≥ 85% prev vol, close ≥ open
    bid_replenish_count = 0
    for i in range(1, len(snap_df)):
        prev = snap_df.iloc[i - 1]
        cur = snap_df.iloc[i]
        if (
            cur["Low"] >= prev["Low"]
            and cur["Volume"] > prev["Volume"] * 0.85
            and cur["Close"] >= cur["Open"]
        ):
            bid_replenish_count += 1

    orderflow_ok = (
        aggressive_buy_sequences >= _MIN_BUY_SEQUENCES
        and ask_levels_cleared >= _MIN_ASK_LEVELS
        and bid_replenish_count >= _MIN_BID_REPLENISH
    )

    # --- Check 4: pullback ---
    pullback_vol_ratio = 1.0
    if not afternoon_df.empty and morning_vol > 0:
        pullback_bars = afternoon_df[afternoon_df["Close"] < afternoon_df["Open"]]
        if not pullback_bars.empty:
            pullback_vol_ratio = float(pullback_bars["Volume"].mean()) / morning_vol

    pullback_ok = (
        pullback_from_high <= _MAX_PULLBACK_PCT
        and pullback_vol_ratio <= _MAX_PULLBACK_VOL_RATIO
    )

    # --- Check 5: spoofing (high-vol up bar immediately reversed by down bar) ---
    spoofing_events = 0
    high_vol_threshold = float(snap_df["Volume"].median()) * 2.2 if not snap_df.empty else 0.0
    for i in range(1, len(snap_df)):
        prev = snap_df.iloc[i - 1]
        cur = snap_df.iloc[i]
        reversal = prev["Close"] > prev["Open"] and cur["Close"] < cur["Open"]
        if prev["Volume"] >= high_vol_threshold and reversal and cur["High"] <= prev["High"]:
            spoofing_events += 1

    spoofing_ok = spoofing_events <= _MAX_SPOOFING

    # --- Assemble signals ---
    signals = IntradaySignals(
        gap_ok=gap_ok,
        breakout_held=breakout_held,
        orderflow_ok=orderflow_ok,
        pullback_ok=pullback_ok,
        spoofing_ok=spoofing_ok,
    )
    signals_passed = sum([gap_ok, breakout_held, orderflow_ok, pullback_ok, spoofing_ok])
    confirmed = signals_passed == 5

    # --- Trade plan (only when confirmed) ---
    entry_price: float | None = None
    stop_price: float | None = None
    target_price: float | None = None
    if confirmed:
        entry_price = current_price
        confirmation_low = float(snap_df["Low"].min()) if not snap_df.empty else current_price * 0.98
        breakout_buffer = morning_high * (1.0 - _STOP_BUFFER_PCT)
        stop_price = round(min(confirmation_low, breakout_buffer), 2)
        risk = max(0.01, entry_price - stop_price)
        target_price = round(entry_price + risk * _FIRST_TP_R, 2)
        entry_price = round(entry_price, 2)
        stop_price = round(stop_price, 2)

    notes: list[str] = []
    if not gap_ok:
        notes.append(f"gap {open_gap_pct:.1%} > 4%")
    if not breakout_held:
        notes.append(f"breakout hold {held_minutes}min < {_MIN_HOLD_MINUTES}min")
    if not orderflow_ok:
        notes.append(
            f"orderflow: buy_seq={aggressive_buy_sequences} ask={ask_levels_cleared} bid={bid_replenish_count}"
        )
    if not pullback_ok:
        notes.append(f"pullback {pullback_from_high:.1%}")
    if not spoofing_ok:
        notes.append(f"spoofing events={spoofing_events}")

    return IntradayResult(
        ticker=ticker,
        confirmed=confirmed,
        signals_passed=signals_passed,
        signals=signals,
        open_gap_pct=round(open_gap_pct * 100, 2),
        session_high=round(session_high, 2),
        current_price=round(current_price, 2),
        pullback_from_high_pct=round(pullback_from_high * 100, 2),
        volume_ratio=round(volume_ratio, 2),
        breakout_hold_minutes=held_minutes,
        entry_price=entry_price,
        stop_price=stop_price,
        target_price=target_price,
        snapshot_time=snapshot_time,
        note="; ".join(notes) if notes else "all checks passed",
    )


def _failed_result(ticker: str, note: str) -> IntradayResult:
    return IntradayResult(
        ticker=ticker,
        confirmed=False,
        signals_passed=0,
        signals=IntradaySignals(
            gap_ok=False,
            breakout_held=False,
            orderflow_ok=False,
            pullback_ok=False,
            spoofing_ok=False,
        ),
        open_gap_pct=0.0,
        session_high=0.0,
        current_price=0.0,
        pullback_from_high_pct=0.0,
        volume_ratio=0.0,
        breakout_hold_minutes=0,
        entry_price=None,
        stop_price=None,
        target_price=None,
        snapshot_time="",
        note=note,
    )


def _fetch_spy_return() -> float:
    """Return SPY same-session return as index proxy. Blocking."""
    try:
        spy = yf.Ticker("SPY")
        df: pd.DataFrame = spy.history(period="2d", interval="1d", prepost=False)
        if df is not None and len(df) >= 2:
            return float(df["Close"].iloc[-1] / df["Close"].iloc[-2] - 1.0)
    except Exception:
        pass
    return 0.0


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class IntradayService:
    def __init__(self) -> None:
        self._states: dict[str, IntradayJobState] = {}

    def get_state(self, user_id: str) -> IntradayJobState:
        return self._states.get(user_id, IntradayJobState(status="idle"))

    def start_scan(self, user_id: str, tickers: list[str]) -> bool:
        current = self._states.get(user_id)
        if current and current.status == "running":
            return False

        tickers = [t.upper().strip() for t in tickers if t.strip()]
        if not tickers:
            return False

        self._states[user_id] = IntradayJobState(
            status="running",
            progress_scanned=0,
            progress_total=len(tickers),
            started_at=datetime.now(timezone.utc).isoformat(),
        )
        asyncio.create_task(self._worker(user_id, tickers))
        return True

    async def _worker(self, user_id: str, tickers: list[str]) -> None:
        loop = asyncio.get_event_loop()
        results: dict[str, IntradayResult] = {}
        scanned = 0

        # Fetch SPY return once in background thread
        try:
            spy_return = await loop.run_in_executor(None, _fetch_spy_return)
        except Exception:
            spy_return = 0.0

        # Process each ticker sequentially (yfinance rate-limit friendly)
        # Use Semaphore(5) for mild concurrency
        sem = asyncio.Semaphore(5)

        async def process(ticker: str) -> None:
            nonlocal scanned
            async with sem:
                try:
                    result = await loop.run_in_executor(
                        None, _compute_result, ticker, spy_return
                    )
                    results[ticker] = result
                except Exception as exc:
                    logger.debug("Intraday skip %s: %s", ticker, exc)
                    results[ticker] = _failed_result(ticker, str(exc))
                finally:
                    scanned += 1
                    state = self._states.get(user_id)
                    if state:
                        self._states[user_id] = state.model_copy(
                            update={"progress_scanned": scanned, "results": dict(results)}
                        )

        try:
            await asyncio.gather(*[process(t) for t in tickers])
            self._states[user_id] = IntradayJobState(
                status="completed",
                progress_scanned=len(tickers),
                progress_total=len(tickers),
                results=results,
                started_at=self._states[user_id].started_at,
                completed_at=datetime.now(timezone.utc).isoformat(),
            )
            confirmed = sum(1 for r in results.values() if r.confirmed)
            logger.info(
                "Intraday scan completed user=%s tickers=%d confirmed=%d",
                user_id, len(tickers), confirmed,
            )
        except Exception as exc:
            logger.error("Intraday scan failed user=%s: %s", user_id, exc)
            state = self._states.get(user_id, IntradayJobState(status="failed"))
            self._states[user_id] = state.model_copy(
                update={"status": "failed", "error": str(exc)}
            )
