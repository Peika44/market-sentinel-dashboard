from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
import logging
import random
import re
from typing import Any

import httpx

from app.core.cache import RedisCache
from app.core.config import settings
from app.domain.models import (
    CandlePoint,
    DashboardSnapshot,
    IndexQuote,
    MarketEvent,
    StockCard,
    TickerValidationResult,
)
from app.infra.storage import SQLiteStore
from app.market import (
    DEFAULT_WATCHLIST,
    DISPLAY_NAMES,
    OVERVIEW_TICKERS,
    SEED_QUOTES,
    compute_urgency,
    placeholder_event,
    sentiment_label_for,
    sentiment_score_from_history,
)

logger = logging.getLogger("market_sentinel_state")

SUPPORTED_WATCHLIST_TICKERS = frozenset(SEED_QUOTES.keys())
TICKER_PATTERN = re.compile(r"^[A-Z][A-Z.\-]{0,9}$")
ACTIVE_TICKERS_CACHE_KEY = "market_feed:active_tickers"

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
        self.display_names: dict[str, str] = dict(DISPLAY_NAMES)
        self.latest_quotes: dict[str, MarketEvent] = {}
        self.price_history: dict[str, deque[float]] = defaultdict(
            lambda: deque(maxlen=180)
        )

        # Seed history: union of well-known tickers, current watchlist, and any
        # ticker that already has rows in the DB (added by previous sessions).
        seed_tickers = (
            set(SEED_QUOTES.keys())
            | set(self._store.list_all_watchlist_tickers())
            | self.watchlists.get(settings.default_user_id, set())
            | set(self._store.list_tickers_with_history())
        )
        tickers_to_purge_history: list[str] = []
        for ticker in seed_tickers:
            db_prices = self._store.load_price_history(ticker, limit=180)
            if self._is_placeholder_history(ticker.upper(), db_prices):
                logger.info("history PURGING placeholder residue ticker=%s", ticker.upper())
                tickers_to_purge_history.append(ticker.upper())
                db_prices = []
            if db_prices:
                for price in db_prices:
                    self.price_history[ticker.upper()].append(price)
                logger.info(
                    "history RESTORED from db ticker=%s points=%d",
                    ticker.upper(),
                    len(db_prices),
                )
            elif (
                settings.market_data_provider != "alpaca"
                or ticker.upper() in SEED_QUOTES
            ):
                seed = SEED_QUOTES.get(ticker.upper(), 100.0)
                for point in self._bootstrap_history(ticker.upper(), seed):
                    self.price_history[ticker.upper()].append(point)
            else:
                self.price_history[ticker.upper()]

        for ticker in tickers_to_purge_history:
            self._store.save_price_history_bulk(ticker, [])

        self._sync_active_tickers()

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
        if normalized.display_name:
            self.display_names[ticker] = normalized.display_name
        self.latest_quotes[ticker] = normalized
        self.price_history[ticker].append(normalized.current_price)

    def recent_history_before_event(self, ticker: str, limit: int = 24) -> list[float]:
        history = list(self.price_history[ticker.upper()])
        if self._is_placeholder_history(ticker.upper(), history):
            return []
        return history[-limit:] if history else []

    def add_to_watchlist(self, user_id: str, ticker: str) -> None:
        user_watchlist = self.watchlists.setdefault(user_id, set(DEFAULT_WATCHLIST))
        user_watchlist.add(ticker.upper())
        self._store.replace_watchlist(user_id, list(user_watchlist))
        self._sync_active_tickers()

    def remove_from_watchlist(self, user_id: str, ticker: str) -> None:
        user_watchlist = self.watchlists.setdefault(user_id, set(DEFAULT_WATCHLIST))
        user_watchlist.discard(ticker.upper())
        self._store.replace_watchlist(user_id, list(user_watchlist))
        self._sync_active_tickers()

    async def hydrate_watchlist_ticker(self, ticker: str) -> None:
        normalized = ticker.strip().upper()
        if not normalized:
            return

        if (
            settings.market_data_provider == "alpaca"
            and settings.alpaca_api_key
            and settings.alpaca_secret_key
        ):
            try:
                self.apply_event(await self._fetch_alpaca_snapshot_event(normalized))
                return
            except Exception as snapshot_exc:
                try:
                    self.apply_event(await self._fetch_alpaca_latest_bar_event(normalized))
                    return
                except Exception as bar_exc:
                    logger.warning(
                        "snapshot/bar hydrate fallback ticker=%s snapshot_error=%s bar_error=%s",
                        normalized,
                        snapshot_exc,
                        bar_exc,
                    )
            return

        if not self.price_history[normalized]:
            seed = SEED_QUOTES.get(normalized, 100.0)
            for point in self._bootstrap_history(normalized, seed):
                self.price_history[normalized].append(point)

    async def validate_ticker(self, ticker: str) -> TickerValidationResult:
        normalized = ticker.strip().upper()
        if not normalized:
            return TickerValidationResult(
                ticker="",
                is_valid=False,
                can_add=False,
                source="input",
                message="Enter a ticker symbol.",
            )

        if not TICKER_PATTERN.fullmatch(normalized):
            return TickerValidationResult(
                ticker=normalized,
                is_valid=False,
                can_add=False,
                source="input",
                message="Ticker must be 1-10 characters using letters, '.' or '-'.",
            )

        if (
            settings.market_data_provider == "alpaca"
            and settings.alpaca_api_key
            and settings.alpaca_secret_key
        ):
            result = await self._validate_alpaca_ticker(normalized)
        else:
            result = self._validate_demo_ticker(normalized)

        if not result.is_valid:
            return result

        if result.display_name:
            self.display_names[normalized] = result.display_name

        if not result.can_add:
            return result

        if result.display_name:
            return result.model_copy(
                update={"message": f"{result.display_name} ({normalized}) is available to add."}
            )
        return result.model_copy(update={"message": f"{normalized} is available to add."})

    def _is_placeholder_history(self, ticker: str, prices: list[float]) -> bool:
        if (
            settings.market_data_provider != "alpaca"
            or ticker.upper() in SEED_QUOTES
            or len(prices) != 1
        ):
            return False
        return abs(prices[0] - 100.0) < 1e-9

    def build_snapshot(self, user_id: str) -> DashboardSnapshot:
        tickers = sorted(self.watchlists.setdefault(user_id, set(DEFAULT_WATCHLIST)))
        cards: list[StockCard] = []

        for ticker in tickers:
            quote = self.latest_quotes.get(ticker)
            history = list(self.price_history[ticker])
            if self._is_placeholder_history(ticker, history):
                history = []
            sentiment_score = sentiment_score_from_history(history)
            has_live_data = quote is not None
            cards.append(
                StockCard(
                    ticker=ticker,
                    display_name=self.display_names.get(ticker, ticker),
                    current_price=quote.current_price if quote else None,
                    change_pct=quote.change_pct if quote else None,
                    volume=quote.volume if quote else 0,
                    last_updated=quote.as_of if quote else None,
                    data_status="live" if has_live_data else "waiting",
                    sentiment_score=sentiment_score,
                    sentiment_label=sentiment_label_for(sentiment_score),
                    urgency_score=compute_urgency(
                        quote.change_pct,
                        sentiment_score,
                    ) if quote else 0.0,
                    history=history[-24:],
                )
            )

        cards.sort(
            key=lambda item: (item.data_status == "live", item.urgency_score),
            reverse=True,
        )

        return DashboardSnapshot(
            user_id=user_id,
            updated_at=datetime.now(timezone.utc),
            stocks=cards,
        )

    async def build_overview(self) -> list[IndexQuote]:
        if (
            settings.market_data_provider == "alpaca"
            and settings.alpaca_api_key
            and settings.alpaca_secret_key
        ):
            cached = self._cache.get_json("market_overview:alpaca")
            if cached:
                return [IndexQuote.model_validate(item) for item in cached]
            try:
                overview = await self._fetch_alpaca_market_overview()
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
                    label=self.display_names.get(ticker, ticker),
                    current_price=quote.current_price,
                    change_pct=quote.change_pct,
                )
            )
        return indices

    def _sync_active_tickers(self) -> None:
        in_memory_tickers = {
            ticker
            for watchlist in self.watchlists.values()
            for ticker in watchlist
        }
        tickers = sorted(
            set(OVERVIEW_TICKERS)
            | set(self._store.list_all_watchlist_tickers())
            | in_memory_tickers
        )
        self._cache.set_json(
            ACTIVE_TICKERS_CACHE_KEY,
            {"tickers": tickers, "updated_at": datetime.now(timezone.utc).isoformat()},
        )

    def _validate_demo_ticker(self, ticker: str) -> TickerValidationResult:
        if ticker in SUPPORTED_WATCHLIST_TICKERS:
            return TickerValidationResult(
                ticker=ticker,
                is_valid=True,
                can_add=True,
                display_name=DISPLAY_NAMES.get(ticker, ticker),
                source="demo_universe",
                message="",
            )

        supported = ", ".join(sorted(SUPPORTED_WATCHLIST_TICKERS))
        return TickerValidationResult(
            ticker=ticker,
            is_valid=False,
            can_add=False,
            source="demo_universe",
            message=f"{ticker} is not in the demo ticker universe. Try {supported}.",
        )

    async def _validate_alpaca_ticker(self, ticker: str) -> TickerValidationResult:
        cache_key = f"ticker_validation:alpaca:v3:{ticker}"
        cached = self._cache.get_json(cache_key)
        if cached:
            return TickerValidationResult.model_validate(cached)

        headers = {
            "APCA-API-KEY-ID": settings.alpaca_api_key,
            "APCA-API-SECRET-KEY": settings.alpaca_secret_key,
        }
        last_error: str | None = None

        async with httpx.AsyncClient(timeout=8.0) as client:
            for base_url in self._alpaca_trading_base_urls():
                try:
                    response = await client.get(f"{base_url}/v2/assets/{ticker}", headers=headers)
                except httpx.HTTPError as exc:
                    last_error = str(exc)
                    continue

                if response.status_code == 404:
                    result = TickerValidationResult(
                        ticker=ticker,
                        is_valid=False,
                        can_add=False,
                        source="alpaca_assets",
                        message=f"{ticker} was not found in Alpaca assets.",
                    )
                    self._cache.set_json(cache_key, result.model_dump(mode="json"), ttl_seconds=3600)
                    return result

                if response.status_code in {401, 403}:
                    last_error = f"{base_url} returned {response.status_code}"
                    continue

                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    last_error = str(exc)
                    continue

                payload: dict[str, Any] = response.json()
                name = str(payload.get("name") or payload.get("symbol") or ticker)
                asset_status = str(payload.get("status") or "").lower()
                asset_class = str(payload.get("class") or "").lower()
                tradable = bool(payload.get("tradable"))

                if asset_status != "active" or asset_class != "us_equity" or not tradable:
                    result = TickerValidationResult(
                        ticker=ticker,
                        is_valid=False,
                        can_add=False,
                        display_name=name,
                        source="alpaca_assets",
                        message=(
                            f"{name} ({ticker}) exists, but it is not an active tradable US equity."
                        ),
                    )
                    self._cache.set_json(cache_key, result.model_dump(mode="json"), ttl_seconds=3600)
                    return result

                result = TickerValidationResult(
                    ticker=ticker,
                    is_valid=True,
                    can_add=True,
                    display_name=name,
                    source="alpaca_assets",
                    message="",
                )
                self._cache.set_json(cache_key, result.model_dump(mode="json"), ttl_seconds=3600)
                return result

        if ticker in SUPPORTED_WATCHLIST_TICKERS:
            logger.warning(
                "ticker validation FALLBACK to demo universe ticker=%s reason=%s",
                ticker,
                last_error or "unknown",
            )
            return self._validate_demo_ticker(ticker)

        return TickerValidationResult(
            ticker=ticker,
            is_valid=False,
            can_add=False,
            source="alpaca_assets",
            message="Ticker validation is temporarily unavailable. Try again shortly.",
        )

    def _alpaca_trading_base_urls(self) -> list[str]:
        candidates = [
            settings.alpaca_trading_url.strip(),
            "https://paper-api.alpaca.markets",
            "https://api.alpaca.markets",
        ]
        urls: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            normalized = candidate.rstrip("/")
            if not normalized or normalized in seen:
                continue
            urls.append(normalized)
            seen.add(normalized)
        return urls

    async def _fetch_alpaca_snapshot(self, ticker: str) -> dict[str, Any]:
        url = f"{settings.alpaca_data_url}/v2/stocks/snapshots"
        params = {
            "symbols": ticker,
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

        return (payload.get("snapshots") or {}).get(ticker) or {}

    def _market_event_from_snapshot(self, ticker: str, snapshot: dict[str, Any]) -> MarketEvent | None:
        latest_trade = snapshot.get("latestTrade") or {}
        latest_quote = snapshot.get("latestQuote") or {}
        prev_daily_bar = snapshot.get("prevDailyBar") or {}
        daily_bar = snapshot.get("dailyBar") or {}

        current_price = (
            latest_trade.get("p")
            or daily_bar.get("c")
            or latest_quote.get("ap")
            or latest_quote.get("bp")
        )
        if current_price in (None, ""):
            return None

        anchor = prev_daily_bar.get("c") or daily_bar.get("o") or current_price
        change_pct = (
            round(((float(current_price) - float(anchor)) / float(anchor)) * 100.0, 2)
            if anchor
            else 0.0
        )

        raw_timestamp = (
            latest_trade.get("t")
            or daily_bar.get("t")
            or datetime.now(timezone.utc).isoformat()
        )
        as_of = datetime.now(timezone.utc)
        if isinstance(raw_timestamp, str):
            try:
                as_of = datetime.fromisoformat(raw_timestamp.replace("Z", "+00:00"))
            except ValueError:
                pass

        return MarketEvent(
            ticker=ticker,
            display_name=self.display_names.get(ticker, ticker),
            current_price=round(float(current_price), 2),
            change_pct=change_pct,
            volume=int(daily_bar.get("v", 0) or 0),
            as_of=as_of,
        )

    async def _fetch_alpaca_snapshot_event(self, ticker: str) -> MarketEvent:
        snapshot = await self._fetch_alpaca_snapshot(ticker)
        event = self._market_event_from_snapshot(ticker, snapshot)
        if event is None:
            raise ValueError(
                f"Configured Alpaca {settings.alpaca_feed.upper()} feed returned no snapshot data."
            )
        return event

    async def _fetch_alpaca_latest_bar_event(self, ticker: str) -> MarketEvent:
        url = f"{settings.alpaca_data_url}/v2/stocks/{ticker}/bars"
        params = {
            "timeframe": "1Day",
            "limit": 2,
            "adjustment": "raw",
            "feed": settings.alpaca_feed,
            "sort": "desc",
        }
        headers = {
            "APCA-API-KEY-ID": settings.alpaca_api_key,
            "APCA-API-SECRET-KEY": settings.alpaca_secret_key,
        }

        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.get(url, params=params, headers=headers)
            response.raise_for_status()
            payload: dict[str, Any] = response.json()

        bars = payload.get("bars") or []
        if not bars:
            raise ValueError("No historical bars available.")

        latest = bars[0]
        previous = bars[1] if len(bars) > 1 else {}
        current_price = float(latest.get("c"))
        anchor = previous.get("c") or latest.get("o") or current_price
        change_pct = (
            round(((current_price - float(anchor)) / float(anchor)) * 100.0, 2)
            if anchor
            else 0.0
        )

        raw_timestamp = latest.get("t") or datetime.now(timezone.utc).isoformat()
        as_of = datetime.now(timezone.utc)
        if isinstance(raw_timestamp, str):
            try:
                as_of = datetime.fromisoformat(raw_timestamp.replace("Z", "+00:00"))
            except ValueError:
                pass

        return MarketEvent(
            ticker=ticker,
            display_name=self.display_names.get(ticker, ticker),
            current_price=round(current_price, 2),
            change_pct=change_pct,
            volume=int(latest.get("v", 0) or 0),
            as_of=as_of,
        )

    async def build_history(self, ticker: str, range_key: str) -> list[CandlePoint]:
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
                candles = await self._fetch_alpaca_history(ticker.upper(), range_key)
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
            return []

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

    async def _fetch_alpaca_history(self, ticker: str, range_key: str) -> list[CandlePoint]:
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

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, params=params, headers=headers)
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

    async def _fetch_alpaca_market_overview(self) -> list[IndexQuote]:
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

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, params=params, headers=headers)
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

    def list_journal_entries(self, user_id: str, limit: int = 12, offset: int = 0) -> list[dict]:
        return self._store.list_journal_entries(user_id, limit=limit, offset=offset)

    def flush_history_to_db(self) -> None:
        """Persist all in-memory price deques to SQLite. Safe to call from any thread."""
        for ticker, hist in list(self.price_history.items()):
            prices = list(hist)
            if self._is_placeholder_history(ticker, prices):
                self._store.save_price_history_bulk(ticker, [])
                continue
            if prices:
                self._store.save_price_history_bulk(ticker, prices)
        logger.info("history FLUSHED to db tickers=%d", len(self.price_history))


__all__ = ["DashboardState"]
