from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import httpx
from pydantic import BaseModel

from app.core.config import settings

logger = logging.getLogger("market_sentinel_scanner")

# ---------------------------------------------------------------------------
# Stock universe lists
# ---------------------------------------------------------------------------

SP500_TICKERS: list[str] = [
    "MMM", "AOS", "ABT", "ABBV", "ACN", "ADBE", "AMD", "AES", "AFL", "A",
    "APD", "ABNB", "AKAM", "ALB", "ARE", "ALGN", "ALLE", "LNT", "ALL", "GOOGL",
    "GOOG", "MO", "AMZN", "AMCR", "AEE", "AAL", "AEP", "AXP", "AIG", "AMT",
    "AWK", "AMP", "AME", "AMGN", "APH", "ADI", "ANSS", "AON", "APA", "AAPL",
    "AMAT", "APTV", "ACGL", "ADM", "ANET", "AJG", "AIZ", "T", "ATO", "ADSK",
    "AZO", "AVB", "AVY", "AXON", "BKR", "BALL", "BAC", "BBWI", "BAX", "BDX",
    "BRK.B", "BBY", "TECH", "BIIB", "BLK", "BX", "BA", "BCH", "BSX", "BMY",
    "AVGO", "BR", "BRO", "BF.B", "BLDR", "BG", "CDNS", "CZR", "CPT", "CPB",
    "COF", "CAH", "KMX", "CCL", "CARR", "CAT", "CBOE", "CBRE", "CDW", "CE",
    "COR", "CNC", "CNX", "CDAY", "CF", "CRL", "SCHW", "CHTR", "CVX", "CMG",
    "CB", "CHD", "CI", "CINF", "CTAS", "CSCO", "C", "CFG", "CLX", "CME",
    "CMS", "KO", "CTSH", "CL", "CMCSA", "CMA", "CAG", "COP", "ED", "STZ",
    "CEG", "COO", "CPRT", "GLW", "CTVA", "CSGP", "COST", "CTRA", "CCI", "CSX",
    "CMI", "CVS", "DHR", "DRI", "DVA", "DAY", "DE", "DAL", "XRAY", "DVN",
    "DXCM", "FANG", "DLR", "DFS", "DG", "DLTR", "D", "DPZ", "DOV", "DOW",
    "DHI", "DTE", "DUK", "DD", "EMN", "ETN", "EBAY", "ECL", "EIX", "EW",
    "EA", "ELV", "LLY", "EMR", "ENPH", "ETR", "EOG", "EPAM", "EQT", "EFX",
    "EQIX", "EQR", "ESS", "EL", "ETSY", "EG", "EVRG", "ES", "EXC", "EXPE",
    "EXPD", "EXR", "XOM", "FFIV", "FDS", "FICO", "FAST", "FRT", "FDX", "FIS",
    "FITB", "FSLR", "FE", "FI", "FLT", "FMC", "F", "FTNT", "FTV", "FOXA",
    "FOX", "BEN", "FCX", "GRMN", "IT", "GE", "GEHC", "GEV", "GEN", "GNRC",
    "GD", "GIS", "GM", "GPC", "GILD", "GS", "HAL", "HIG", "HAS", "HCA",
    "DOC", "HSIC", "HSY", "HES", "HPE", "HLT", "HOLX", "HD", "HON", "HRL",
    "HST", "HWM", "HPQ", "HUBB", "HUM", "HBAN", "HII", "IBM", "IEX", "IDXX",
    "ITW", "ILMN", "INCY", "IR", "PODD", "INTC", "ICE", "IFF", "IP", "IPG",
    "INTU", "ISRG", "IVZ", "INVH", "IQV", "IRM", "JBHT", "JBL", "JKHY", "J",
    "JNJ", "JCI", "JPM", "JNPR", "K", "KVUE", "KDP", "KEY", "KEYS", "KMB",
    "KIM", "KMI", "KLAC", "KHC", "KR", "LHX", "LH", "LRCX", "LW", "LVS",
    "LDOS", "LEN", "LIN", "LYV", "LKQ", "LMT", "L", "LOW", "LULU", "LYB",
    "MTB", "MRO", "MPC", "MKTX", "MAR", "MMC", "MLM", "MAS", "MA", "MTCH",
    "MKC", "MCD", "MCK", "MDT", "MRK", "META", "MET", "MTD", "MGM", "MCHP",
    "MU", "MSFT", "MAA", "MRNA", "MHK", "MOH", "TAP", "MDLZ", "MPWR", "MNST",
    "MCO", "MS", "MOS", "MSI", "MSCI", "NDAQ", "NTAP", "NFLX", "NEM", "NWSA",
    "NWS", "NEE", "NKE", "NI", "NDSN", "NSC", "NTRS", "NOC", "NCLH", "NRG",
    "NUE", "NVDA", "NVR", "NXPI", "ORLY", "OXY", "ODFL", "OMC", "ON", "OKE",
    "ORCL", "OTIS", "PCAR", "PKG", "PANW", "PARA", "PH", "PAYX", "PAYC", "PYPL",
    "PNR", "PEP", "PFE", "PCG", "PM", "PSX", "PNW", "PXD", "PNC", "POOL",
    "PPG", "PPL", "PFG", "PG", "PGR", "PLD", "PRU", "PEG", "PTC", "PSA",
    "PHM", "QRVO", "PWR", "QCOM", "DGX", "RL", "RJF", "RTX", "O", "REG",
    "REGN", "RF", "RSG", "RMD", "RVTY", "ROK", "ROL", "ROP", "ROST", "RCL",
    "SPGI", "CRM", "SBAC", "SLB", "STX", "SRE", "NOW", "SHW", "SPG", "SWKS",
    "SJM", "SW", "SNA", "SOLV", "SO", "LUV", "SWK", "SBUX", "STT", "STLD",
    "STE", "SYK", "SMCI", "SYF", "SNPS", "SYY", "TMUS", "TROW", "TTWO", "TPR",
    "TRGP", "TGT", "TEL", "TDY", "TFX", "TER", "TSLA", "TXN", "TXT", "TMO",
    "TJX", "TSCO", "TT", "TDG", "TRV", "TRMB", "TFC", "TYL", "TSN", "USB",
    "UBER", "UDR", "ULTA", "UNP", "UAL", "UPS", "URI", "UNH", "UHS", "VLO",
    "VTR", "VRSN", "VRSK", "VZ", "VRTX", "VTRS", "VICI", "V", "VMC", "WRB",
    "WAB", "WBA", "WMT", "DIS", "WBD", "WM", "WAT", "WEC", "WFC", "WELL",
    "WST", "WDC", "WY", "WHR", "WMB", "WTW", "GWW", "WYNN", "XEL", "XYL",
    "YUM", "ZBRA", "ZBH", "ZTS",
]

NASDAQ100_TICKERS: list[str] = [
    "ADBE", "AMD", "ABNB", "GOOGL", "GOOG", "AMZN", "AEP", "AMGN", "ADI", "ANSS",
    "AAPL", "AMAT", "ASML", "AZN", "TEAM", "ADSK", "ADP", "AXON", "BIIB", "BKNG",
    "AVGO", "CDNS", "CDW", "CHTR", "CTAS", "CSCO", "CCEP", "CTSH", "CMCSA", "CEG",
    "CPRT", "CSGP", "COST", "CRWD", "CSX", "DDOG", "DXCM", "FANG", "DLTR", "ENPH",
    "EA", "EXC", "FAST", "FTNT", "GEHC", "GILD", "GFS", "HON", "ILMN", "INTC",
    "INTU", "ISRG", "KDP", "KLAC", "KHC", "LRCX", "LULU", "MAR", "MRVL", "MTCH",
    "MKC", "MCHP", "MU", "MSFT", "MDLZ", "MRNA", "MNST", "NDAQ", "NXPI", "NFLX",
    "NVDA", "ORLY", "ODFL", "ON", "PCAR", "PANW", "PAYX", "PYPL", "PDD", "QCOM",
    "REGN", "ROP", "ROST", "SIRI", "SBUX", "SNPS", "TMUS", "TSLA", "TXN", "TTD",
    "VRSK", "VRTX", "WBD", "WBA", "WDAY", "XEL", "ZS", "ZM",
]

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class ScanRules(BaseModel):
    bottom_position_pct: float = 0.35
    volume_surge_ratio: float = 1.3
    rsi_oversold: float = 35.0
    rsi_recovery: float = 40.0
    min_score: int = 40


class ScanResult(BaseModel):
    rank: int
    ticker: str
    score: int
    signals: dict[str, bool]
    last_close: float
    position_in_range: float
    rsi_current: float
    volume_ratio: float
    macd_turning_up: bool
    price_change_pct: float


class ScanJobState(BaseModel):
    status: Literal["idle", "running", "completed", "failed"]
    progress_scanned: int = 0
    progress_total: int = 0
    results: list[ScanResult] = []
    started_at: str | None = None
    completed_at: str | None = None
    error: str | None = None


class ScanRunRequest(BaseModel):
    user_id: str
    preset: str = "sp500"
    custom_tickers: list[str] | None = None
    rules: ScanRules | None = None


# --- Breakout/Pullback scanner models ---


class BreakoutSignals(BaseModel):
    market_aligned: bool
    trend_up: bool
    volume_surge: bool
    breakout_signal: bool
    pullback_signal: bool


class BreakoutScanResult(BaseModel):
    rank: int
    ticker: str
    score: int
    signals: BreakoutSignals
    setup_type: Literal["breakout", "pullback"]
    last_close: float
    breakout_level: float
    close_strength: float
    daily_return_pct: float
    volume_ratio: float
    price_change_pct: float


class BreakoutScanJobState(BaseModel):
    status: Literal["idle", "running", "completed", "failed"]
    progress_scanned: int = 0
    progress_total: int = 0
    results: list[BreakoutScanResult] = []
    market_filter_active: bool = True
    started_at: str | None = None
    completed_at: str | None = None
    error: str | None = None


class BreakoutRunRequest(BaseModel):
    user_id: str
    preset: str = "sp500"
    custom_tickers: list[str] | None = None


# ---------------------------------------------------------------------------
# Technical indicators (pure Python, no extra deps)
# ---------------------------------------------------------------------------


def _sma(prices: list[float], period: int) -> list[float]:
    """Simple moving average. Returns a list the same length as prices."""
    result: list[float] = []
    for i in range(len(prices)):
        if i < period - 1:
            result.append(float("nan"))
        else:
            result.append(sum(prices[i - period + 1 : i + 1]) / period)
    return result


def _ema(prices: list[float], period: int) -> list[float]:
    """Exponential moving average using the standard multiplier 2/(period+1)."""
    result: list[float] = []
    k = 2.0 / (period + 1)
    ema = None
    for price in prices:
        if ema is None:
            ema = price
        else:
            ema = price * k + ema * (1 - k)
        result.append(ema)
    return result


def _rsi(prices: list[float], period: int = 14) -> list[float]:
    """Wilder's RSI (Relative Strength Index)."""
    if len(prices) < period + 1:
        return [50.0] * len(prices)

    deltas = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
    gains = [max(d, 0.0) for d in deltas]
    losses = [max(-d, 0.0) for d in deltas]

    # Seed with simple average
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    result: list[float] = [float("nan")] * period  # pad for alignment with prices
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0:
            result.append(100.0)
        else:
            rs = avg_gain / avg_loss
            result.append(100.0 - 100.0 / (1.0 + rs))

    # result has len(prices)-1 items so far; prepend one nan for the first price
    return [float("nan")] + result


def _macd(prices: list[float]) -> tuple[list[float], list[float], list[float]]:
    """Standard MACD (12, 26, 9). Returns (macd_line, signal_line, histogram)."""
    ema12 = _ema(prices, 12)
    ema26 = _ema(prices, 26)
    macd_line = [a - b for a, b in zip(ema12, ema26)]
    signal_line = _ema(macd_line, 9)
    histogram = [m - s for m, s in zip(macd_line, signal_line)]
    return macd_line, signal_line, histogram


# ---------------------------------------------------------------------------
# Scoring logic
# ---------------------------------------------------------------------------


def _score_ticker(
    closes: list[float],
    volumes: list[float],
    rules: ScanRules,
) -> dict[str, Any] | None:
    """
    Compute a 0-100 score for a stock based on four signal categories.

    Returns a dict with keys: score, signals, position_in_range, rsi_current,
    volume_ratio, macd_turning_up, price_change_pct.
    Returns None if there is not enough data.
    """
    if len(closes) < 30 or len(volumes) < 30:
        return None

    score = 0
    signals: dict[str, bool] = {
        "bottom_position": False,
        "volume_surge": False,
        "rsi_recovery": False,
        "ma_cross": False,
        "macd_signal": False,
    }

    last_close = closes[-1]
    prev_close = closes[-2] if len(closes) >= 2 else last_close
    price_change_pct = (last_close - prev_close) / prev_close * 100.0 if prev_close else 0.0

    # --- 1. Bottom position (25 pts) ---
    high_52w = max(closes[-252:]) if len(closes) >= 252 else max(closes)
    low_52w = min(closes[-252:]) if len(closes) >= 252 else min(closes)
    price_range = high_52w - low_52w
    position_in_range = (last_close - low_52w) / price_range if price_range > 0 else 0.5
    if position_in_range <= rules.bottom_position_pct:
        score += 25
        signals["bottom_position"] = True

    # --- 2. Volume surge (25 pts) ---
    recent_5d_vol = sum(volumes[-5:]) / 5.0 if len(volumes) >= 5 else 0.0
    prior_25d_vol = sum(volumes[-30:-5]) / 25.0 if len(volumes) >= 30 else 0.0
    volume_ratio = recent_5d_vol / prior_25d_vol if prior_25d_vol > 0 else 1.0

    # Check that high-volume days didn't cause large price drops
    big_vol_days = [
        i for i in range(max(0, len(volumes) - 10), len(volumes))
        if volumes[i] > prior_25d_vol * 2.0
    ]
    vol_healthy = all(
        (closes[i] - closes[i - 1]) / closes[i - 1] > -0.03
        for i in big_vol_days
        if i > 0 and closes[i - 1] > 0
    )

    if volume_ratio >= rules.volume_surge_ratio and vol_healthy:
        score += 25
        signals["volume_surge"] = True

    # --- 3. RSI recovery (20 pts) ---
    rsi_series = _rsi(closes, 14)
    valid_rsi = [r for r in rsi_series if not (r != r)]  # filter NaN
    rsi_current = valid_rsi[-1] if valid_rsi else 50.0

    # Check past 30 days for oversold condition
    recent_rsi = [r for r in valid_rsi[-30:] if not (r != r)]
    was_oversold = any(r <= rules.rsi_oversold for r in recent_rsi)
    rsi_trending_up = (
        len(valid_rsi) >= 3
        and valid_rsi[-1] > valid_rsi[-2] > valid_rsi[-3]
    )
    rsi_in_recovery_zone = rules.rsi_recovery <= rsi_current <= 60.0

    if was_oversold and rsi_in_recovery_zone and rsi_trending_up:
        score += 20
        signals["rsi_recovery"] = True

    # --- 4. MA cross (15 pts) ---
    sma5 = _sma(closes, 5)
    sma20 = _sma(closes, 20)

    valid5 = [v for v in sma5 if v == v]  # filter NaN
    valid20 = [v for v in sma20 if v == v]

    ma_cross = False
    if len(valid5) >= 2 and len(valid20) >= 2:
        # Golden cross: 5-day SMA crossing above 20-day SMA in the last 5 bars
        sma5_last = sma5[-1]
        sma20_last = sma20[-1]
        sma5_prev = next((v for v in reversed(sma5[:-1]) if v == v), None)
        sma20_prev = next((v for v in reversed(sma20[:-1]) if v == v), None)
        if sma5_last and sma20_last and sma5_prev and sma20_prev:
            # Price crossed above 20-day MA or golden cross
            if sma5_last > sma20_last and (sma5_prev <= sma20_prev or last_close > sma20_last):
                ma_cross = True
            # Or price recently crossed above 20-day SMA from below
            elif last_close > sma20_last and prev_close <= (sma20_prev or sma20_last):
                ma_cross = True

    if ma_cross:
        score += 15
        signals["ma_cross"] = True

    # --- 5. MACD signal (15 pts) ---
    _, _, histogram = _macd(closes)
    macd_turning_up = False
    if len(histogram) >= 3:
        h1, h2, h3 = histogram[-3], histogram[-2], histogram[-1]
        # Histogram rising for 3 consecutive bars (can be negative but improving)
        if h3 > h2 > h1:
            macd_turning_up = True
        # Or MACD line zero-cross near zero
        macd_line, _, _ = _macd(closes)
        if (
            len(macd_line) >= 2
            and macd_line[-2] < 0 <= macd_line[-1]
            and abs(macd_line[-1]) < 1.0  # near zero
        ):
            macd_turning_up = True

    if macd_turning_up:
        score += 15
        signals["macd_signal"] = True

    return {
        "score": score,
        "signals": signals,
        "position_in_range": round(position_in_range, 3),
        "rsi_current": round(rsi_current, 1),
        "volume_ratio": round(volume_ratio, 2),
        "macd_turning_up": macd_turning_up,
        "price_change_pct": round(price_change_pct, 2),
        "last_close": round(last_close, 2),
    }


# ---------------------------------------------------------------------------
# Breakout/Pullback scoring (translates TradingView Pine Script logic)
# ---------------------------------------------------------------------------


def _score_breakout_ticker(
    closes: list[float],
    highs: list[float],
    lows: list[float],
    volumes: list[float],
    market_ok: bool = True,
) -> dict[str, Any] | None:
    """
    Breakout/Pullback scanner based on Pine Script short-term model.

    Breakout setup: price clears 20-day high on strong volume (≥1.8x),
    close strength ≥ 0.72, daily return 2.5–9%, trend up.

    Pullback setup: price pulls back ≤6% after a prior strong impulse
    bar (≥1.75%), holding above SMA5×0.985, trend up.

    Returns None if neither setup qualifies.  Score 0-100 ranks quality.
    """
    if len(closes) < 25 or len(highs) < 25 or len(lows) < 25 or len(volumes) < 25:
        return None

    c = closes[-1]
    h = highs[-1]
    l = lows[-1]
    v = volumes[-1]
    c_prev = closes[-2] if len(closes) >= 2 else c
    c_prev2 = closes[-3] if len(closes) >= 3 else c_prev

    sma5 = _sma(closes, 5)
    sma20 = _sma(closes, 20)
    avg_vol = _sma(volumes, 10)

    s5 = sma5[-1]
    s20 = sma20[-1]
    av = avg_vol[-1]

    # Guard against NaN / zero
    if s5 != s5 or s20 != s20 or av != av or av == 0:
        return None

    daily_return = c / c_prev - 1.0 if c_prev > 0 else 0.0
    prev_daily_return = c_prev / c_prev2 - 1.0 if c_prev2 > 0 else 0.0
    close_strength = (c - l) / (h - l) if h > l else 0.5
    vol_ratio = v / av
    dollar_vol = c * v

    # Breakout level: highest high of previous 20 bars (not today)
    n = len(highs)
    lb_start = max(0, n - 21)
    lb_end = n - 1
    breakout_level = max(highs[lb_start:lb_end]) if lb_end > lb_start else h
    breakout_ext = c / breakout_level - 1.0 if breakout_level > 0 else 0.0
    pullback_depth = 1.0 - c / c_prev if c_prev > 0 else 0.0

    trend_up = c > s5 > s20

    # ---- Breakout signal (Pine: minCoreVolumeRatio=1.8 is the binding constraint) ----
    breakout_signal = bool(
        market_ok
        and trend_up
        and dollar_vol >= 5_000_000
        and 0.025 <= daily_return <= 0.09
        and vol_ratio >= 1.8
        and close_strength >= 0.72
        and c > breakout_level
        and breakout_ext <= 0.05
    )

    # ---- Pullback signal (Pine: minStrongBarReturn*0.7 = 1.75%; pullbackMaxPct = 6%) ----
    pullback_signal = bool(
        market_ok
        and trend_up
        and dollar_vol >= 5_000_000
        and prev_daily_return >= 0.0175
        and vol_ratio >= 0.90
        and close_strength >= 0.35
        and daily_return < 0.020
        and daily_return > -0.06
        and c < c_prev
        and 0 < pullback_depth <= 0.06
        and c >= s5 * 0.985
        and l >= s20 * 0.99
    )

    if not (breakout_signal or pullback_signal):
        return None

    # ---- Score (0-100) ----
    score = 0

    if market_ok:
        score += 15           # market filter passing

    if trend_up:
        score += 20           # trend confirmation

    # Volume quality: 0-25 pts
    if vol_ratio >= 3.0:
        score += 25
    elif vol_ratio >= 2.5:
        score += 22
    elif vol_ratio >= 2.0:
        score += 18
    elif vol_ratio >= 1.8:
        score += 15
    elif vol_ratio >= 1.3:
        score += 10
    else:
        score += 5

    # Setup quality: 0-40 pts
    if breakout_signal:
        score += 30           # base breakout quality
        # Close-strength bonus (0-10): 0 at 0.72, 10 at 1.0
        cs_bonus = int((close_strength - 0.72) / 0.28 * 10)
        score += max(0, min(10, cs_bonus))
    else:
        score += 25           # base pullback quality
        # Prior impulse bonus (0-15): 0 at 1.75%, 15 at 6%
        impulse_bonus = int((min(prev_daily_return, 0.06) - 0.0175) / (0.06 - 0.0175) * 15)
        score += max(0, min(15, impulse_bonus))

    setup_type: str = "breakout" if breakout_signal else "pullback"

    return {
        "score": min(100, score),
        "signals": {
            "market_aligned": market_ok,
            "trend_up": trend_up,
            "volume_surge": vol_ratio >= 1.3,
            "breakout_signal": breakout_signal,
            "pullback_signal": pullback_signal,
        },
        "setup_type": setup_type,
        "last_close": round(c, 2),
        "breakout_level": round(breakout_level, 2),
        "close_strength": round(close_strength, 3),
        "daily_return_pct": round(daily_return * 100, 2),
        "volume_ratio": round(vol_ratio, 2),
        "price_change_pct": round(daily_return * 100, 2),
    }


# ---------------------------------------------------------------------------
# Scanner service
# ---------------------------------------------------------------------------


class ScannerService:
    def __init__(self) -> None:
        self._states: dict[str, ScanJobState] = {}
        self._breakout_states: dict[str, BreakoutScanJobState] = {}
        self._lock = asyncio.Lock()

    def get_state(self, user_id: str) -> ScanJobState:
        return self._states.get(user_id, ScanJobState(status="idle"))

    def start_scan(
        self,
        user_id: str,
        preset: str = "sp500",
        custom_tickers: list[str] | None = None,
        rules: ScanRules | None = None,
    ) -> bool:
        """Launch a background scan. Returns False if one is already running."""
        current = self._states.get(user_id)
        if current and current.status == "running":
            return False

        if preset == "nasdaq100":
            tickers = list(NASDAQ100_TICKERS)
        elif preset == "custom" and custom_tickers:
            tickers = [t.upper() for t in custom_tickers if t.strip()]
        else:
            tickers = list(SP500_TICKERS)

        rules = rules or ScanRules()
        self._states[user_id] = ScanJobState(
            status="running",
            progress_scanned=0,
            progress_total=len(tickers),
            started_at=datetime.now(timezone.utc).isoformat(),
        )

        asyncio.create_task(self._scan_worker(user_id, tickers, rules))
        return True

    async def _scan_worker(
        self,
        user_id: str,
        tickers: list[str],
        rules: ScanRules,
    ) -> None:
        sem = asyncio.Semaphore(15)
        results: list[ScanResult] = []
        scanned = 0

        async def process(ticker: str) -> None:
            nonlocal scanned
            async with sem:
                try:
                    bars = await self._fetch_bars(ticker)
                    if bars:
                        closes, _highs, _lows, volumes = bars
                        scored = _score_ticker(closes, volumes, rules)
                        if scored and scored["score"] >= rules.min_score:
                            results.append(
                                ScanResult(
                                    rank=0,
                                    ticker=ticker,
                                    score=scored["score"],
                                    signals=scored["signals"],
                                    last_close=scored["last_close"],
                                    position_in_range=scored["position_in_range"],
                                    rsi_current=scored["rsi_current"],
                                    volume_ratio=scored["volume_ratio"],
                                    macd_turning_up=scored["macd_turning_up"],
                                    price_change_pct=scored["price_change_pct"],
                                )
                            )
                except Exception as exc:
                    logger.debug("Scanner skip %s: %s", ticker, exc)
                finally:
                    scanned += 1
                    state = self._states.get(user_id)
                    if state:
                        self._states[user_id] = state.model_copy(
                            update={"progress_scanned": scanned}
                        )

        try:
            await asyncio.gather(*[process(t) for t in tickers])
            results.sort(key=lambda r: r.score, reverse=True)
            for i, r in enumerate(results, 1):
                r.rank = i

            self._states[user_id] = ScanJobState(
                status="completed",
                progress_scanned=len(tickers),
                progress_total=len(tickers),
                results=results,
                started_at=self._states[user_id].started_at,
                completed_at=datetime.now(timezone.utc).isoformat(),
            )
            logger.info("Scan completed user=%s results=%d", user_id, len(results))
        except Exception as exc:
            logger.error("Scan failed user=%s: %s", user_id, exc)
            state = self._states.get(user_id, ScanJobState(status="failed"))
            self._states[user_id] = state.model_copy(
                update={"status": "failed", "error": str(exc)}
            )

    async def _fetch_bars(
        self,
        ticker: str,
    ) -> tuple[list[float], list[float], list[float], list[float]] | None:
        """Fetch 90 days of daily bars from Alpaca. Returns (closes, highs, lows, volumes) or None."""
        if not settings.alpaca_api_key:
            return None

        end = datetime.now(timezone.utc)
        start = end - timedelta(days=90)
        url = f"{settings.alpaca_data_url}/v2/stocks/{ticker}/bars"
        params = {
            "timeframe": "1Day",
            "start": start.isoformat(),
            "end": end.isoformat(),
            "limit": 100,
            "adjustment": "raw",
            "feed": settings.alpaca_feed,
        }
        headers = {
            "APCA-API-KEY-ID": settings.alpaca_api_key,
            "APCA-API-SECRET-KEY": settings.alpaca_secret_key,
        }

        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.get(url, params=params, headers=headers)
            response.raise_for_status()
            payload: dict[str, Any] = response.json()

        bars: list[dict[str, Any]] = payload.get("bars") or []
        if len(bars) < 20:
            return None

        closes = [float(b["c"]) for b in bars if "c" in b]
        highs = [float(b["h"]) for b in bars if "h" in b]
        lows = [float(b["l"]) for b in bars if "l" in b]
        volumes = [float(b["v"]) for b in bars if "v" in b]
        return closes, highs, lows, volumes

    # -----------------------------------------------------------------------
    # Breakout/Pullback scanner
    # -----------------------------------------------------------------------

    def get_breakout_state(self, user_id: str) -> BreakoutScanJobState:
        return self._breakout_states.get(user_id, BreakoutScanJobState(status="idle"))

    def start_breakout_scan(
        self,
        user_id: str,
        preset: str = "sp500",
        custom_tickers: list[str] | None = None,
    ) -> bool:
        """Launch a breakout/pullback background scan. Returns False if one is already running."""
        current = self._breakout_states.get(user_id)
        if current and current.status == "running":
            return False

        if preset == "nasdaq100":
            tickers = list(NASDAQ100_TICKERS)
        elif preset == "custom" and custom_tickers:
            tickers = [t.upper() for t in custom_tickers if t.strip()]
        else:
            tickers = list(SP500_TICKERS)

        self._breakout_states[user_id] = BreakoutScanJobState(
            status="running",
            progress_scanned=0,
            progress_total=len(tickers),
            started_at=datetime.now(timezone.utc).isoformat(),
        )
        asyncio.create_task(self._breakout_worker(user_id, tickers))
        return True

    async def _fetch_market_trend(self) -> bool:
        """
        Fetch QQQ 90-day daily bars and return True if the market is in uptrend.

        Mirrors the Pine Script marketOkay condition:
          marketTrendUp AND (marketBreakoutNow OR marketStrongBar)
        where:
          marketTrendUp   = QQQ close > SMA10 > SMA30
          marketBreakoutNow = QQQ close > 20-day high
          marketStrongBar   = daily return >= 1% on above-average volume
        """
        try:
            bars = await self._fetch_bars("QQQ")
            if not bars:
                return True  # can't verify — assume OK
            closes, highs, _, volumes = bars
            if len(closes) < 30:
                return True

            sma10 = _sma(closes, 10)
            sma30 = _sma(closes, 30)
            avg_vol = _sma(volumes, 10)

            s10, s30, av = sma10[-1], sma30[-1], avg_vol[-1]
            if s10 != s10 or s30 != s30 or av != av:  # NaN
                return True

            c = closes[-1]
            c_prev = closes[-2] if len(closes) >= 2 else c
            v = volumes[-1]

            market_trend_up = c > s10 and s10 > s30
            if not market_trend_up:
                return False

            # marketBreakoutNow
            n = len(highs)
            lb_start = max(0, n - 21)
            lb_end = n - 1
            market_breakout_level = max(highs[lb_start:lb_end]) if lb_end > lb_start else c
            market_breakout_now = c > market_breakout_level

            # marketStrongBar
            daily_ret = c / c_prev - 1.0 if c_prev > 0 else 0.0
            vol_ratio = v / av if av > 0 else 1.0
            market_strong_bar = daily_ret >= 0.01 and vol_ratio >= 1.0

            return market_trend_up and (market_breakout_now or market_strong_bar)
        except Exception:
            return True

    async def _breakout_worker(self, user_id: str, tickers: list[str]) -> None:
        market_ok = await self._fetch_market_trend()

        # Store market_ok flag in state
        state = self._breakout_states.get(user_id)
        if state:
            self._breakout_states[user_id] = state.model_copy(
                update={"market_filter_active": market_ok}
            )

        sem = asyncio.Semaphore(15)
        results: list[BreakoutScanResult] = []
        scanned = 0

        async def process(ticker: str) -> None:
            nonlocal scanned
            async with sem:
                try:
                    bars = await self._fetch_bars(ticker)
                    if bars:
                        closes, highs, lows, volumes = bars
                        scored = _score_breakout_ticker(closes, highs, lows, volumes, market_ok)
                        if scored:
                            results.append(
                                BreakoutScanResult(
                                    rank=0,
                                    ticker=ticker,
                                    score=scored["score"],
                                    signals=BreakoutSignals(**scored["signals"]),
                                    setup_type=scored["setup_type"],
                                    last_close=scored["last_close"],
                                    breakout_level=scored["breakout_level"],
                                    close_strength=scored["close_strength"],
                                    daily_return_pct=scored["daily_return_pct"],
                                    volume_ratio=scored["volume_ratio"],
                                    price_change_pct=scored["price_change_pct"],
                                )
                            )
                except Exception as exc:
                    logger.debug("Breakout scanner skip %s: %s", ticker, exc)
                finally:
                    scanned += 1
                    bstate = self._breakout_states.get(user_id)
                    if bstate:
                        self._breakout_states[user_id] = bstate.model_copy(
                            update={"progress_scanned": scanned}
                        )

        try:
            await asyncio.gather(*[process(t) for t in tickers])
            results.sort(key=lambda r: r.score, reverse=True)
            for i, r in enumerate(results, 1):
                r.rank = i

            started = self._breakout_states[user_id].started_at
            self._breakout_states[user_id] = BreakoutScanJobState(
                status="completed",
                progress_scanned=len(tickers),
                progress_total=len(tickers),
                results=results,
                market_filter_active=market_ok,
                started_at=started,
                completed_at=datetime.now(timezone.utc).isoformat(),
            )
            logger.info(
                "Breakout scan completed user=%s results=%d market_ok=%s",
                user_id, len(results), market_ok,
            )
        except Exception as exc:
            logger.error("Breakout scan failed user=%s: %s", user_id, exc)
            bstate = self._breakout_states.get(user_id, BreakoutScanJobState(status="failed"))
            self._breakout_states[user_id] = bstate.model_copy(
                update={"status": "failed", "error": str(exc)}
            )
