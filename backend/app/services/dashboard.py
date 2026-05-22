from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
import logging
import random
from typing import Any

import httpx

from app.core.cache import RedisCache
from app.core.config import settings
from app.domain.models import CandlePoint, DashboardSnapshot, IndexQuote, MarketEvent, StockCard
from app.infra.storage import SQLiteStore
from app.market import (
    DEFAULT_WATCHLIST,
    DISPLAY_NAMES,
    OVERVIEW_TICKERS,
    SEED_QUOTES,
    compute_urgency,
    placeholder_event,
    sentiment_label_for,
    sentiment_score_for,
)

logger = logging.getLogger("market_sentinel_state")

RANGE_POINTS = {
    "5m": 12,
    "1h": 24,
    "1D": 32,
    "5D": 48,
    "1M": 72,
    "3M": 96,
    "6M": 120,
    "1Y": 144,
}

RANGE_STEP_MINUTES = {
    "5m": 5,
    "1h": 15,
    "1D": 30,
    "5D": 60,
    "1M": 240,
    "3M": 720,
    "6M": 1440,
    "1Y": 2880,
}

ALPACA_TIMEFRAME_MAP = {
    "5m": ("5Min", 1),
    "1h": ("15Min", 1),
    "1D": ("30Min", 1),
    "5D": ("1Hour", 5),
    "1M": ("1Day", 30),
    "3M": ("1Day", 90),
    "6M": ("1Day", 180),
    "1Y": ("1Day", 365),
}


class DashboardState:
    def __init__(self, store: SQLiteStore, cache: RedisCache) -> None:
        self._store = store
        self._cache = cache
        persisted = self._store.load_watchlist(settings.default_user_id)
        self.watchlists: dict[str, set[str]] = {
            settings.default_user_id: set(persisted or DEFAULT_WATCHLIST)
        }
        self.latest_quotes: dict[str, MarketEvent] = {}
        self.price_history: dict[str, deque[float]] = defaultdict(
            lambda: deque(maxlen=180)
        )

        for ticker, price in SEED_QUOTES.items():
            for point in self._bootstrap_history(ticker, price):
                self.price_history[ticker].append(point)

    def _bootstrap_history(self, ticker: str, seed_price: float) -> list[float]:
        rng = random.Random(f"bootstrap:{ticker}")
        points: list[float] = []
        current = seed_price

        for _ in range(144):
            current *= 1.0 + rng.uniform(-0.006, 0.006)
            current = max(seed_price * 0.7, current)
            points.append(round(current, 2))

        return points

    def apply_event(self, event: MarketEvent) -> None:
        ticker = event.ticker.upper()
        normalized = event.model_copy(update={"ticker": ticker})
        self.latest_quotes[ticker] = normalized
        self.price_history[ticker].append(normalized.current_price)

    def recent_history_before_event(self, ticker: str, limit: int = 24) -> list[float]:
        history = list(self.price_history[ticker.upper()])
        return history[-limit:] if history else []

    def add_to_watchlist(self, user_id: str, ticker: str) -> None:
        user_watchlist = self.watchlists.setdefault(user_id, set(DEFAULT_WATCHLIST))
        user_watchlist.add(ticker.upper())
        self._store.replace_watchlist(user_id, list(user_watchlist))

    def remove_from_watchlist(self, user_id: str, ticker: str) -> None:
        user_watchlist = self.watchlists.setdefault(user_id, set(DEFAULT_WATCHLIST))
        user_watchlist.discard(ticker.upper())
        self._store.replace_watchlist(user_id, list(user_watchlist))

    def build_snapshot(self, user_id: str) -> DashboardSnapshot:
        tickers = sorted(self.watchlists.setdefault(user_id, set(DEFAULT_WATCHLIST)))
        cards: list[StockCard] = []

        for ticker in tickers:
            quote = self.latest_quotes.get(ticker, placeholder_event(ticker))
            sentiment_score = sentiment_score_for(ticker)
            cards.append(
                StockCard(
                    ticker=ticker,
                    display_name=DISPLAY_NAMES.get(ticker, ticker),
                    current_price=quote.current_price,
                    change_pct=quote.change_pct,
                    volume=quote.volume,
                    last_updated=quote.as_of,
                    sentiment_score=sentiment_score,
                    sentiment_label=sentiment_label_for(sentiment_score),
                    urgency_score=compute_urgency(
                        quote.change_pct,
                        sentiment_score,
                    ),
                    history=list(self.price_history[ticker])[-24:],
                )
            )

        cards.sort(key=lambda item: item.urgency_score, reverse=True)

        return DashboardSnapshot(
            user_id=user_id,
            updated_at=datetime.now(timezone.utc),
            stocks=cards,
        )

    def build_overview(self) -> list[IndexQuote]:
        if (
            settings.market_data_provider == "alpaca"
            and settings.alpaca_api_key
            and settings.alpaca_secret_key
        ):
            cached = self._cache.get_json("market_overview:alpaca")
            if cached:
                return [IndexQuote.model_validate(item) for item in cached]
            try:
                overview = self._fetch_alpaca_market_overview()
                self._cache.set_json(
                    "market_overview:alpaca",
                    [item.model_dump(mode="json") for item in overview],
                    ttl_seconds=15,
                )
                logger.info("overview SOURCE alpaca")
                return overview
            except Exception as exc:
                logger.warning("overview FALLBACK in-memory due to Alpaca error: %s", exc)

        indices: list[IndexQuote] = []
        for ticker in OVERVIEW_TICKERS:
            quote = self.latest_quotes.get(ticker, placeholder_event(ticker))
            indices.append(
                IndexQuote(
                    ticker=ticker,
                    label=DISPLAY_NAMES.get(ticker, ticker),
                    current_price=quote.current_price,
                    change_pct=quote.change_pct,
                )
            )
        return indices

    def build_history(self, ticker: str, range_key: str) -> list[CandlePoint]:
        if (
            settings.market_data_provider == "alpaca"
            and settings.alpaca_api_key
            and settings.alpaca_secret_key
        ):
            cache_key = f"history:alpaca:{ticker.upper()}:{range_key}"
            cached = self._cache.get_json(cache_key)
            if cached:
                return [CandlePoint.model_validate(item) for item in cached]
            try:
                candles = self._fetch_alpaca_history_sync(ticker.upper(), range_key)
                if candles:
                    ttl = 60 if range_key in {"5m", "1h", "1D", "5D"} else 300
                    self._cache.set_json(
                        cache_key,
                        [candle.model_dump(mode="json") for candle in candles],
                        ttl_seconds=ttl,
                    )
                    logger.info(
                        "history SOURCE alpaca ticker=%s range=%s ttl=%ss",
                        ticker.upper(),
                        range_key,
                        ttl,
                    )
                    return candles
            except Exception as exc:
                logger.warning(
                    "history FALLBACK synthetic ticker=%s range=%s due to Alpaca error: %s",
                    ticker.upper(),
                    range_key,
                    exc,
                )

        history = list(self.price_history[ticker.upper()])
        if not history:
            history = [placeholder_event(ticker).current_price]

        point_count = RANGE_POINTS.get(range_key, RANGE_POINTS["1M"])
        step_minutes = RANGE_STEP_MINUTES.get(range_key, RANGE_STEP_MINUTES["1M"])
        selected = history[-point_count:]
        now = datetime.now(timezone.utc)

        candles: list[CandlePoint] = []
        previous_close = selected[0]
        for index, close in enumerate(selected):
            timestamp = now - timedelta(
                minutes=step_minutes * (len(selected) - index - 1)
            )
            open_price = previous_close
            high = max(open_price, close) * 1.003
            low = min(open_price, close) * 0.997
            candles.append(
                CandlePoint(
                    label=timestamp.strftime("%b %d %H:%M"),
                    open=round(open_price, 2),
                    high=round(high, 2),
                    low=round(low, 2),
                    close=round(close, 2),
                )
            )
            previous_close = close

        logger.info("history SOURCE in-memory ticker=%s range=%s", ticker.upper(), range_key)
        return candles

    def _fetch_alpaca_history_sync(self, ticker: str, range_key: str) -> list[CandlePoint]:
        timeframe, days = ALPACA_TIMEFRAME_MAP.get(range_key, ALPACA_TIMEFRAME_MAP["1M"])
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days)
        url = f"{settings.alpaca_data_url}/v2/stocks/{ticker}/bars"
        params = {
            "timeframe": timeframe,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "limit": RANGE_POINTS.get(range_key, RANGE_POINTS["1M"]),
            "adjustment": "raw",
            "feed": settings.alpaca_feed,
            "sort": "asc",
        }
        headers = {
            "APCA-API-KEY-ID": settings.alpaca_api_key,
            "APCA-API-SECRET-KEY": settings.alpaca_secret_key,
        }

        with httpx.Client(timeout=10.0) as client:
            response = client.get(url, params=params, headers=headers)
            response.raise_for_status()
            payload: dict[str, Any] = response.json()

        bars = payload.get("bars", [])
        candles: list[CandlePoint] = []
        for bar in bars:
            timestamp = bar.get("t")
            label = timestamp if isinstance(timestamp, str) else ""
            if label:
                try:
                    dt = datetime.fromisoformat(label.replace("Z", "+00:00"))
                    label = dt.strftime("%b %d %H:%M") if timeframe != "1Day" else dt.strftime("%b %d")
                except ValueError:
                    pass

            candles.append(
                CandlePoint(
                    label=label,
                    open=round(float(bar.get("o", 0.0)), 2),
                    high=round(float(bar.get("h", 0.0)), 2),
                    low=round(float(bar.get("l", 0.0)), 2),
                    close=round(float(bar.get("c", 0.0)), 2),
                )
            )
        return candles

    def _fetch_alpaca_market_overview(self) -> list[IndexQuote]:
        symbols = ",".join(OVERVIEW_TICKERS)
        url = f"{settings.alpaca_data_url}/v2/stocks/snapshots"
        params = {
            "symbols": symbols,
            "feed": settings.alpaca_feed,
        }
        headers = {
            "APCA-API-KEY-ID": settings.alpaca_api_key,
            "APCA-API-SECRET-KEY": settings.alpaca_secret_key,
        }

        with httpx.Client(timeout=10.0) as client:
            response = client.get(url, params=params, headers=headers)
            response.raise_for_status()
            payload: dict[str, Any] = response.json()

        snapshots = payload.get("snapshots", {})
        overview: list[IndexQuote] = []

        for ticker in OVERVIEW_TICKERS:
            snapshot = snapshots.get(ticker, {})
            latest_trade = snapshot.get("latestTrade") or {}
            latest_quote = snapshot.get("latestQuote") or {}
            prev_daily_bar = snapshot.get("prevDailyBar") or {}
            daily_bar = snapshot.get("dailyBar") or {}

            current_price = (
                latest_trade.get("p")
                or daily_bar.get("c")
                or latest_quote.get("ap")
                or latest_quote.get("bp")
                or SEED_QUOTES.get(ticker, 0.0)
            )
            anchor = prev_daily_bar.get("c") or daily_bar.get("o") or current_price
            change_pct = (
                round(((float(current_price) - float(anchor)) / float(anchor)) * 100.0, 2)
                if anchor
                else 0.0
            )
            overview.append(
                IndexQuote(
                    ticker=ticker,
                    label=DISPLAY_NAMES.get(ticker, ticker),
                    current_price=round(float(current_price), 2),
                    change_pct=change_pct,
                )
            )

        return overview

    def save_trade_plan_draft(self, user_id: str, payload: dict, updated_at: str) -> None:
        ticker = str(payload["ticker"]).upper()
        self._store.save_trade_plan_draft(user_id, ticker, payload, updated_at)

    def list_trade_plan_drafts(self, user_id: str) -> list[dict]:
        return self._store.list_trade_plan_drafts(user_id)

    def save_alert_rule(self, user_id: str, payload: dict, updated_at: str) -> None:
        self._store.save_alert_rule(user_id, payload, updated_at)

    def list_alert_rules(self, user_id: str) -> list[dict]:
        return self._store.list_alert_rules(user_id)

    def set_alert_rule_enabled(
        self, user_id: str, rule_id: str, enabled: bool, updated_at: str
    ) -> dict | None:
        return self._store.set_alert_rule_enabled(user_id, rule_id, enabled, updated_at)

    def delete_alert_rule(self, user_id: str, rule_id: str) -> bool:
        return self._store.delete_alert_rule(user_id, rule_id)

    def save_journal_entry(self, user_id: str, payload: dict, updated_at: str) -> None:
        self._store.save_journal_entry(user_id, payload, updated_at)

    def list_journal_entries(self, user_id: str, limit: int = 12) -> list[dict]:
        return self._store.list_journal_entries(user_id, limit=limit)


__all__ = ["DashboardState"]
