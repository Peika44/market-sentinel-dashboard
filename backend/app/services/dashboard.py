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
    AlertUtilityStat,
    CandlePoint,
    CatalystEventPayload,
    DashboardSnapshot,
    DigestMetric,
    EndOfDayDigest,
    FocusQueueEntryPayload,
    FocusQueueEntryView,
    IndexQuote,
    LeaderHoldingPayload,
    MarketEvent,
    MistakeTagStat,
    ReviewMetrics,
    SessionBucket,
    SetupStat,
    StockCard,
    StoredCatalystEvent,
    StoredLeaderHolding,
    StoredTrade,
    TickerValidationResult,
    ThesisOutcomeSummary,
    TradeLifecyclePayload,
    UrgencySettingsPayload,
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
WAITING_TIMEOUT_SECONDS = 30
DEFAULT_URGENCY_SETTINGS = UrgencySettingsPayload()

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
        self.urgency_settings: dict[str, UrgencySettingsPayload] = {}
        self.display_names: dict[str, str] = dict(DISPLAY_NAMES)
        self.latest_quotes: dict[str, MarketEvent] = {}
        self.quote_sources: dict[str, str] = {}
        self.pending_since: dict[str, datetime] = {}
        self.status_messages: dict[str, str] = {}
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

        for ticker in self.watchlists.get(settings.default_user_id, set()):
            self.pending_since.setdefault(ticker.upper(), datetime.now(timezone.utc))

        stored_urgency_settings = self._store.load_urgency_settings(settings.default_user_id)
        if stored_urgency_settings:
            self.urgency_settings[settings.default_user_id] = UrgencySettingsPayload.model_validate(
                stored_urgency_settings["payload"]
            )

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
        self._record_quote(event, source="stream")

    def _record_quote(self, event: MarketEvent, source: str) -> None:
        ticker = event.ticker.upper()
        normalized = event.model_copy(update={"ticker": ticker})
        if normalized.display_name:
            self.display_names[ticker] = normalized.display_name
        self.latest_quotes[ticker] = normalized
        self.quote_sources[ticker] = source
        self.pending_since.pop(ticker, None)
        if source == "stream":
            self.status_messages.pop(ticker, None)
        self.price_history[ticker].append(normalized.current_price)

    def recent_history_before_event(self, ticker: str, limit: int = 24) -> list[float]:
        history = list(self.price_history[ticker.upper()])
        if self._is_placeholder_history(ticker.upper(), history):
            return []
        return history[-limit:] if history else []

    def add_to_watchlist(
        self,
        user_id: str,
        ticker: str,
        validation: TickerValidationResult | None = None,
    ) -> None:
        ticker_upper = ticker.upper()
        user_watchlist = self.watchlists.setdefault(user_id, set(DEFAULT_WATCHLIST))
        user_watchlist.add(ticker_upper)
        self._store.replace_watchlist(user_id, list(user_watchlist))
        self.pending_since[ticker_upper] = datetime.now(timezone.utc)
        self.quote_sources.pop(ticker_upper, None)
        self.latest_quotes.pop(ticker_upper, None)
        if validation and validation.feed_status == "delayed" and validation.message:
            self.status_messages[ticker_upper] = validation.message
        else:
            self.status_messages[ticker_upper] = self._waiting_message()
        self._sync_active_tickers()

    def remove_from_watchlist(self, user_id: str, ticker: str) -> None:
        ticker_upper = ticker.upper()
        user_watchlist = self.watchlists.setdefault(user_id, set(DEFAULT_WATCHLIST))
        user_watchlist.discard(ticker_upper)
        self._store.replace_watchlist(user_id, list(user_watchlist))
        self.pending_since.pop(ticker_upper, None)
        self.status_messages.pop(ticker_upper, None)
        self.quote_sources.pop(ticker_upper, None)
        self.latest_quotes.pop(ticker_upper, None)
        self._sync_active_tickers()

    def is_tracked(self, user_id: str, ticker: str) -> bool:
        ticker_upper = ticker.upper()
        return ticker_upper in self.watchlists.setdefault(user_id, set(DEFAULT_WATCHLIST))

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
                self._record_quote(
                    await self._fetch_alpaca_snapshot_event(normalized),
                    source="snapshot",
                )
                self.status_messages[normalized] = self._delayed_message(
                    "Seeded from the latest Alpaca snapshot while waiting for a live stream tick."
                )
                return
            except Exception as snapshot_exc:
                try:
                    self._record_quote(
                        await self._fetch_alpaca_latest_bar_event(normalized),
                        source="bar",
                    )
                    self.status_messages[normalized] = self._delayed_message(
                        "Seeded from the latest Alpaca daily bar because no live snapshot was available."
                    )
                    return
                except Exception as bar_exc:
                    logger.warning(
                        "snapshot/bar hydrate fallback ticker=%s snapshot_error=%s bar_error=%s",
                        normalized,
                        snapshot_exc,
                        bar_exc,
                    )
                    self.status_messages[normalized] = self._delayed_message(
                        "Subscribed successfully, but the current feed has not returned a live snapshot or recent bar yet."
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

        if result.message:
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
        urgency_settings = self.load_urgency_settings(user_id)

        for ticker in tickers:
            quote = self.latest_quotes.get(ticker)
            history = list(self.price_history[ticker])
            if self._is_placeholder_history(ticker, history):
                history = []
            sentiment_score = sentiment_score_from_history(history)
            data_status, status_message = self._resolve_data_status(ticker, quote)
            cards.append(
                StockCard(
                    ticker=ticker,
                    display_name=self.display_names.get(ticker, ticker),
                    current_price=quote.current_price if quote else None,
                    change_pct=quote.change_pct if quote else None,
                    volume=quote.volume if quote else 0,
                    last_updated=quote.as_of if quote else None,
                    data_status=data_status,
                    data_status_message=status_message,
                    data_feed=self._data_feed_label(),
                    sentiment_score=sentiment_score,
                    sentiment_label=sentiment_label_for(sentiment_score),
                    urgency_score=self.compute_urgency(
                        urgency_settings,
                        quote.change_pct,
                        sentiment_score,
                    ) if quote and data_status != "waiting" else 0.0,
                    history=history[-24:],
                )
            )

        cards.sort(
            key=lambda item: (
                item.data_status == "live",
                item.data_status == "delayed",
                item.urgency_score,
            ),
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
                feed_status="supported",
                source="demo_universe",
                message="",
            )

        supported = ", ".join(sorted(SUPPORTED_WATCHLIST_TICKERS))
        return TickerValidationResult(
            ticker=ticker,
            is_valid=False,
            can_add=False,
            feed_status="unknown",
            source="demo_universe",
            message=f"{ticker} is not in the demo ticker universe. Try {supported}.",
        )

    async def _validate_alpaca_ticker(self, ticker: str) -> TickerValidationResult:
        cache_key = f"ticker_validation:alpaca:v4:{ticker}"
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
                        feed_status="unknown",
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
                        feed_status="unknown",
                        source="alpaca_assets",
                        message=(
                            f"{name} ({ticker}) exists, but it is not an active tradable US equity."
                        ),
                    )
                    self._cache.set_json(cache_key, result.model_dump(mode="json"), ttl_seconds=3600)
                    return result

                feed_status, message = await self._probe_feed_status(ticker, name)
                result = TickerValidationResult(
                    ticker=ticker,
                    is_valid=True,
                    can_add=True,
                    display_name=name,
                    feed_status=feed_status,
                    source="alpaca_assets",
                    message=message,
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
            feed_status="unknown",
            source="alpaca_assets",
            message="Ticker validation is temporarily unavailable. Try again shortly.",
        )

    async def _probe_feed_status(self, ticker: str, display_name: str) -> tuple[str, str]:
        try:
            snapshot = await self._fetch_alpaca_snapshot(ticker)
            if self._market_event_from_snapshot(ticker, snapshot) is not None:
                return (
                    "supported",
                    f"{display_name} ({ticker}) is available to add.",
                )
        except Exception as exc:
            logger.info("feed probe snapshot miss ticker=%s reason=%s", ticker, exc)

        try:
            await self._fetch_alpaca_latest_bar_event(ticker)
            return (
                "delayed",
                (
                    f"{display_name} ({ticker}) is valid, but the configured "
                    f"{self._data_feed_label()} feed only has delayed bootstrap data right now."
                ),
            )
        except Exception as exc:
            logger.info("feed probe bar miss ticker=%s reason=%s", ticker, exc)

        return (
            "delayed",
            (
                f"{display_name} ({ticker}) is valid, but the configured "
                f"{self._data_feed_label()} feed has not returned snapshot or recent bar coverage yet."
            ),
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

    def _resolve_data_status(
        self,
        ticker: str,
        quote: MarketEvent | None,
    ) -> tuple[str, str | None]:
        source = self.quote_sources.get(ticker)
        if quote is not None:
            if source == "stream":
                return "live", f"Live stream via {self._data_feed_label()}."
            return "delayed", self.status_messages.get(ticker, self._delayed_message())

        pending_since = self.pending_since.get(ticker)
        status_message = self.status_messages.get(ticker)
        if status_message and status_message != self._waiting_message():
            return "delayed", status_message
        if pending_since is not None:
            age_seconds = (datetime.now(timezone.utc) - pending_since).total_seconds()
            if age_seconds < WAITING_TIMEOUT_SECONDS:
                return "waiting", self._waiting_message()

        return "delayed", status_message or self._delayed_message()

    def _data_feed_label(self) -> str:
        if settings.market_data_provider == "alpaca":
            return settings.alpaca_feed.upper()
        return settings.market_data_provider.upper()

    def _waiting_message(self) -> str:
        return f"Subscribed to {self._data_feed_label()}. Waiting for the first live tick."

    def _delayed_message(self, detail: str | None = None) -> str:
        if detail:
            return f"{self._data_feed_label()}: {detail}"
        return (
            f"{self._data_feed_label()}: live streaming has not started yet, so the card is using delayed or limited coverage."
        )

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

    def save_ticker_note(self, user_id: str, payload: dict, updated_at: str) -> None:
        ticker = str(payload["ticker"]).upper()
        self._store.save_ticker_note(user_id, ticker, payload, updated_at)

    def load_ticker_note(self, user_id: str, ticker: str) -> dict | None:
        return self._store.load_ticker_note(user_id, ticker)

    def list_ticker_notes(self, user_id: str) -> list[dict]:
        return self._store.list_ticker_notes(user_id)

    def save_focus_queue_entry(self, user_id: str, payload: dict, updated_at: str) -> None:
        entry = FocusQueueEntryPayload.model_validate(payload)
        self._store.save_focus_queue_entry(
            user_id,
            entry.ticker,
            entry.model_dump(),
            updated_at,
        )

    def delete_focus_queue_entry(self, user_id: str, ticker: str) -> bool:
        return self._store.delete_focus_queue_entry(user_id, ticker)

    def load_focus_queue_entry(self, user_id: str, ticker: str) -> FocusQueueEntryView:
        generated = self._build_generated_focus_queue_entry(user_id, ticker)
        saved = self._store.load_focus_queue_entry(user_id, ticker)
        if saved is None:
            return FocusQueueEntryView(
                ticker=generated.ticker,
                updated_at="",
                source="generated",
                payload=generated,
                generated_payload=generated,
            )
        return FocusQueueEntryView(
            ticker=saved["ticker"],
            updated_at=saved["updated_at"],
            source="saved",
            payload=FocusQueueEntryPayload.model_validate(saved["payload"]),
            generated_payload=generated,
        )

    def list_focus_queue_entries(self, user_id: str) -> list[FocusQueueEntryView]:
        snapshot = self.build_snapshot(user_id)
        saved_entries = {
            row["ticker"]: row
            for row in self._store.list_focus_queue_entries(user_id)
        }
        catalyst_events = self.list_catalyst_events(user_id)
        entries: list[FocusQueueEntryView] = []
        for stock in snapshot.stocks:
            generated = self._build_generated_focus_queue_entry(
                user_id, stock.ticker, snapshot=snapshot, catalyst_events=catalyst_events
            )
            saved = saved_entries.get(stock.ticker)
            if saved is None:
                entries.append(
                    FocusQueueEntryView(
                        ticker=stock.ticker,
                        updated_at="",
                        source="generated",
                        payload=generated,
                        generated_payload=generated,
                    )
                )
                continue
            entries.append(
                FocusQueueEntryView(
                    ticker=stock.ticker,
                    updated_at=saved["updated_at"],
                    source="saved",
                    payload=FocusQueueEntryPayload.model_validate(saved["payload"]),
                    generated_payload=generated,
                )
            )

        bucket_rank = {"today_focus": 0, "monitor": 1, "ignore": 2}
        entries.sort(
            key=lambda entry: (
                bucket_rank.get(entry.payload.bucket, 3),
                -next(
                    (stock.urgency_score for stock in snapshot.stocks if stock.ticker == entry.ticker),
                    0.0,
                ),
                entry.ticker,
            )
        )
        return entries

    def _build_generated_focus_queue_entry(
        self,
        user_id: str,
        ticker: str,
        *,
        snapshot: DashboardSnapshot | None = None,
        catalyst_events: list[StoredCatalystEvent] | None = None,
    ) -> FocusQueueEntryPayload:
        current_snapshot = snapshot or self.build_snapshot(user_id)
        stock = next(
            (item for item in current_snapshot.stocks if item.ticker == ticker.upper()),
            None,
        )
        if stock is None:
            return FocusQueueEntryPayload(
                ticker=ticker.upper(),
                bucket="monitor",
                whyOnList="Ticker is tracked, but no live dashboard snapshot is available yet.",
                triggerCondition="Wait for a valid market update before promoting it.",
                invalidationCondition="Remove it if the setup is no longer relevant to the session.",
            )

        bucket = self._focus_bucket_for_stock(user_id, stock)

        # Catalyst boost: elevate bucket when high-priority events are upcoming
        events = catalyst_events if catalyst_events is not None else self.list_catalyst_events(user_id)
        boost, catalyst_label = self._get_catalyst_info(events, stock.ticker)
        if boost in ("today_high", "week_high"):
            if bucket == "ignore":
                bucket = "monitor"
            elif bucket == "monitor" and boost == "today_high":
                bucket = "today_focus"

        trigger_condition = self._focus_trigger_for_stock(stock, bucket)
        invalidation_condition = self._focus_invalidation_for_stock(stock, bucket)
        why_on_list = self._focus_reason_for_stock(stock, bucket)
        if catalyst_label:
            why_on_list += f" Catalyst: {catalyst_label}."

        return FocusQueueEntryPayload(
            ticker=stock.ticker,
            bucket=bucket,
            whyOnList=why_on_list,
            triggerCondition=trigger_condition,
            invalidationCondition=invalidation_condition,
            catalystTag=catalyst_label if catalyst_label else None,
        )

    def _get_catalyst_info(
        self,
        catalyst_events: list[StoredCatalystEvent],
        ticker: str,
    ) -> tuple[str, str]:
        """Return (boost_level, catalyst_label) for upcoming events in the next 7 days.

        boost_level: "today_high" | "week_high" | "week_medium" | "none"
        """
        HIGH_PRIORITY = {"earnings", "macro_fomc", "news_tag"}

        today = datetime.now(timezone.utc).date()
        week_end = today + timedelta(days=7)

        relevant = [
            e for e in catalyst_events
            if e.payload.scope == "macro" or e.ticker.upper() == ticker.upper()
        ]

        best_boost = "none"
        labels: list[str] = []

        for event in relevant:
            try:
                event_date = datetime.strptime(event.payload.eventDate, "%Y-%m-%d").date()
            except (ValueError, TypeError):
                continue

            if event_date < today or event_date > week_end:
                continue

            is_today = event_date == today
            is_high = event.payload.eventType in HIGH_PRIORITY

            time_part = f" ({event.payload.timeLabel})" if event.payload.timeLabel else ""
            labels.append(f"{event.payload.eventType}{time_part} · {event.payload.eventDate}")

            if is_today and is_high and best_boost != "today_high":
                best_boost = "today_high"
            elif is_high and best_boost not in ("today_high", "week_high"):
                best_boost = "week_high"
            elif best_boost == "none":
                best_boost = "week_medium"

        label_str = "; ".join(labels[:2])
        return best_boost, label_str

    def _focus_bucket_for_stock(
        self,
        user_id: str,
        stock: StockCard,
    ) -> str:
        urgency_settings = self.load_urgency_settings(user_id)
        if stock.data_status == "waiting":
            return "monitor"
        if stock.data_status == "delayed":
            return "ignore" if stock.urgency_score < urgency_settings.lowThreshold else "monitor"
        if stock.urgency_score >= urgency_settings.highThreshold:
            return "today_focus"
        if stock.urgency_score >= urgency_settings.lowThreshold:
            return "monitor"
        return "ignore"

    def _focus_reason_for_stock(self, stock: StockCard, bucket: str) -> str:
        urgency_label = f"urgency {stock.urgency_score:.0f}"
        price_label = (
            f"{stock.change_pct:+.2f}%"
            if stock.change_pct is not None
            else "no usable price change yet"
        )
        if bucket == "today_focus":
            return (
                f"{stock.ticker} is live, ranked near the top of the board with {urgency_label}, "
                f"and is already moving {price_label}. This deserves active screen time today."
            )
        if bucket == "monitor":
            if stock.data_status == "waiting":
                return (
                    f"{stock.ticker} is on the watchlist, but the first market tick has not arrived yet. "
                    "Keep it visible until the feed confirms whether the setup is real."
                )
            if stock.data_status == "delayed":
                return (
                    f"{stock.ticker} only has delayed or bootstrap coverage right now. "
                    f"Keep it in monitor until live data confirms the current {urgency_label}."
                )
            return (
                f"{stock.ticker} has some signal value with {urgency_label} and {price_label}, "
                "but not enough confirmation yet to make it a primary focus name."
            )
        return (
            f"{stock.ticker} is currently lower-priority with {urgency_label} and {price_label}. "
            "Keep it off the main board unless the setup improves."
        )

    def _focus_trigger_for_stock(self, stock: StockCard, bucket: str) -> str:
        if bucket == "today_focus":
            return (
                "Keep it in Today Focus while price stays active, live data remains healthy, "
                "and the setup still matches your thesis."
            )
        if stock.data_status == "waiting":
            return "Promote it once the first live tick arrives and the board urgency is confirmed."
        if stock.data_status == "delayed":
            return "Promote it after live streaming replaces delayed coverage and the setup still looks actionable."
        return "Promote it if urgency rises further, price confirms, or a new catalyst makes it actionable."

    def _focus_invalidation_for_stock(self, stock: StockCard, bucket: str) -> str:
        if bucket == "today_focus":
            return "Demote it if momentum fades, thesis breaks, or the tape shifts against the setup."
        if bucket == "monitor":
            return "Move it to Ignore for now if live confirmation never comes or the setup loses edge."
        return "Bring it back only if urgency, price action, or your thesis materially improves."

    def save_leader_holding(self, user_id: str, payload: dict, updated_at: str) -> None:
        holding = LeaderHoldingPayload.model_validate(payload)
        self._store.save_leader_holding(
            user_id,
            holding.ticker,
            holding.model_dump(),
            updated_at,
        )

    def list_leader_holdings(self, user_id: str) -> list[StoredLeaderHolding]:
        rows = self._store.list_leader_holdings(user_id)
        return [
            StoredLeaderHolding(
                ticker=row["ticker"],
                updated_at=row["updated_at"],
                payload=LeaderHoldingPayload.model_validate(row["payload"]),
            )
            for row in rows
        ]

    def delete_leader_holding(self, user_id: str, ticker: str) -> bool:
        return self._store.delete_leader_holding(user_id, ticker)

    def save_catalyst_event(self, user_id: str, payload: dict, updated_at: str) -> None:
        event = CatalystEventPayload.model_validate(payload)
        self._store.save_catalyst_event(
            user_id,
            event.model_dump(),
            updated_at,
        )

    def list_catalyst_events(self, user_id: str) -> list[StoredCatalystEvent]:
        rows = self._store.list_catalyst_events(user_id)
        return [
            StoredCatalystEvent(
                event_id=row["event_id"],
                ticker=row["ticker"],
                updated_at=row["updated_at"],
                payload=CatalystEventPayload.model_validate(row["payload"]),
            )
            for row in rows
        ]

    def delete_catalyst_event(self, user_id: str, event_id: str) -> bool:
        return self._store.delete_catalyst_event(user_id, event_id)

    def save_trade(self, user_id: str, payload: dict, updated_at: str) -> str:
        trade = TradeLifecyclePayload.model_validate(payload)
        return self._store.save_trade(user_id, trade.model_dump(), updated_at)

    def list_trades(self, user_id: str) -> list[StoredTrade]:
        rows = self._store.list_trades(user_id)
        return [
            StoredTrade(
                trade_id=row["trade_id"],
                ticker=row["ticker"],
                updated_at=row["updated_at"],
                payload=TradeLifecyclePayload.model_validate(row["payload"]),
            )
            for row in rows
        ]

    def delete_trade(self, user_id: str, trade_id: str) -> bool:
        return self._store.delete_trade(user_id, trade_id)

    def build_thesis_outcome_summary(self, user_id: str, ticker: str) -> ThesisOutcomeSummary:
        ticker_upper = ticker.upper()
        note = self.load_ticker_note(user_id, ticker_upper)
        journal_entries = [
            entry
            for entry in self.list_journal_entries(user_id, limit=200, offset=0)
            if entry["ticker"] == ticker_upper
        ]

        latest_entry = journal_entries[0] if journal_entries else None
        closed_entries = [
            entry
            for entry in journal_entries
            if entry["payload"].get("outcomeTag") in {"win", "loss", "scratch"}
        ]

        win_count = sum(1 for entry in closed_entries if entry["payload"].get("outcomeTag") == "win")
        loss_count = sum(1 for entry in closed_entries if entry["payload"].get("outcomeTag") == "loss")
        scratch_count = sum(1 for entry in closed_entries if entry["payload"].get("outcomeTag") == "scratch")

        return ThesisOutcomeSummary(
            ticker=ticker_upper,
            strategy_tag=(note["payload"].get("strategyTag", "") if note else ""),
            current_thesis=(
                (note["payload"].get("thesis", "") if note else "")
                or (latest_entry["payload"].get("thesis", "") if latest_entry else "")
            ),
            latest_review=(latest_entry["payload"].get("review", "") if latest_entry else ""),
            latest_outcome=(latest_entry["payload"].get("outcome", "") if latest_entry else ""),
            latest_outcome_tag=(latest_entry["payload"].get("outcomeTag", "open") if latest_entry else "open"),
            latest_updated_at=(latest_entry["updated_at"] if latest_entry else ""),
            total_closed_entries=len(closed_entries),
            win_count=win_count,
            loss_count=loss_count,
            scratch_count=scratch_count,
        )

    def save_urgency_settings(self, user_id: str, payload: dict, updated_at: str) -> None:
        settings_payload = UrgencySettingsPayload.model_validate(payload)
        self.urgency_settings[user_id] = settings_payload
        self._store.save_urgency_settings(user_id, settings_payload.model_dump(), updated_at)

    def load_urgency_settings(self, user_id: str) -> UrgencySettingsPayload:
        return self.urgency_settings.get(user_id, DEFAULT_URGENCY_SETTINGS)

    @staticmethod
    def compute_urgency(
        urgency_settings: UrgencySettingsPayload,
        change_pct: float,
        sentiment_score: float,
    ) -> float:
        total_weight = urgency_settings.priceWeightPct + urgency_settings.sentimentWeightPct
        normalized_price_weight = urgency_settings.priceWeightPct / total_weight
        normalized_sentiment_weight = urgency_settings.sentimentWeightPct / total_weight
        price_component = min(abs(change_pct) * urgency_settings.priceMoveScale, 100.0) * normalized_price_weight
        sentiment_component = (1.0 - sentiment_score) * 100.0 * normalized_sentiment_weight
        return round(min(price_component + sentiment_component, 100.0), 2)

    async def build_end_of_day_digest(
        self,
        user_id: str,
        alerts: list[dict],
        journal: list[dict],
    ) -> EndOfDayDigest:
        snapshot = self.build_snapshot(user_id)
        overview = await self.build_overview()
        notes = self.list_ticker_notes(user_id)

        positive_indices = sum(1 for quote in overview if quote.change_pct >= 0)
        if positive_indices == len(overview):
            tone = "Broad Risk-On"
        elif positive_indices == 0:
            tone = "Broad Risk-Off"
        else:
            tone = "Mixed Tape"

        live_stocks = [stock for stock in snapshot.stocks if stock.data_status == "live"]
        top_urgency = ", ".join(stock.ticker for stock in live_stocks[:3]) or "No live symbols"
        recent_alerts = ", ".join(alert["ticker"] for alert in alerts[:3]) or "No recent triggers"
        tagged = sum(1 for note in notes if str(note["payload"].get("strategyTag", "")).strip())
        delayed = sum(1 for stock in snapshot.stocks if stock.data_status == "delayed")
        recent_journal = ", ".join(entry["ticker"] for entry in journal[:3]) or "No recent journal updates"

        metrics = [
            DigestMetric(
                label="Index Tone",
                value=tone,
                detail="Broad market context from SPY, QQQ, and IWM.",
            ),
            DigestMetric(
                label="Top Urgency",
                value=top_urgency,
                detail="Highest-ranked live names on the board.",
            ),
            DigestMetric(
                label="Alert Pressure",
                value=recent_alerts,
                detail="Most recent triggered alerts worth reviewing.",
            ),
            DigestMetric(
                label="Prep Coverage",
                value=f"{tagged}/{len(snapshot.stocks)} tagged · {delayed} delayed",
                detail="How much of the board is prepared and how much still has limited feed coverage.",
            ),
            DigestMetric(
                label="Journal Loop",
                value=recent_journal,
                detail="Most recent symbols with journal activity.",
            ),
        ]

        return EndOfDayDigest(
            user_id=user_id,
            generated_at=datetime.now(timezone.utc).isoformat(),
            headline="End-of-Day Digest",
            summary=(
                f"{tone}. Review {top_urgency} first, then check {recent_alerts} and fill any gaps in notes or journal coverage."
            ),
            metrics=metrics,
        )

    @staticmethod
    def render_end_of_day_digest_text(digest: EndOfDayDigest) -> str:
        lines = [digest.summary]
        for metric in digest.metrics:
            lines.append(f"{metric.label}: {metric.value} - {metric.detail}")
        return "\n".join(lines)

    def build_review_metrics(self, user_id: str, triggered_alerts: list[dict]) -> ReviewMetrics:
        trades = self.list_trades(user_id)
        closed = [t for t in trades if t.payload.outcomeTag != "open"]

        total_closed = len(closed)
        win_count = sum(1 for t in closed if t.payload.outcomeTag == "win")
        loss_count = sum(1 for t in closed if t.payload.outcomeTag == "loss")
        scratch_count = sum(1 for t in closed if t.payload.outcomeTag == "scratch")
        overall_win_rate = round(win_count / total_closed, 4) if total_closed > 0 else 0.0

        def _r_multiple(t: StoredTrade) -> float | None:
            try:
                entry = float(t.payload.actualEntry) if t.payload.actualEntry else float(t.payload.entryPrice)
                stop = float(t.payload.stopLoss)
                exit_price = float(t.payload.actualExit)
                risk = abs(entry - stop)
                if risk == 0:
                    return None
                return (exit_price - entry) / risk
            except (ValueError, TypeError):
                return None

        winner_rs = [r for t in closed if t.payload.outcomeTag == "win" for r in [_r_multiple(t)] if r is not None]
        loser_rs = [r for t in closed if t.payload.outcomeTag == "loss" for r in [_r_multiple(t)] if r is not None]
        avg_winner_r = round(sum(winner_rs) / len(winner_rs), 2) if winner_rs else None
        avg_loser_r = round(sum(loser_rs) / len(loser_rs), 2) if loser_rs else None

        # Setup performance
        setup_map: dict[str, list[StoredTrade]] = defaultdict(list)
        for t in closed:
            setup_map[t.payload.setupType].append(t)

        by_setup: list[SetupStat] = []
        for setup_type, group in setup_map.items():
            g_win = sum(1 for t in group if t.payload.outcomeTag == "win")
            g_loss = sum(1 for t in group if t.payload.outcomeTag == "loss")
            g_scratch = sum(1 for t in group if t.payload.outcomeTag == "scratch")
            g_count = len(group)
            g_wr = round(g_win / g_count, 4) if g_count > 0 else 0.0
            g_winner_rs = [r for t in group if t.payload.outcomeTag == "win" for r in [_r_multiple(t)] if r is not None]
            by_setup.append(SetupStat(
                setup_type=setup_type,
                count=g_count,
                win=g_win,
                loss=g_loss,
                scratch=g_scratch,
                win_rate=g_wr,
                avg_winner_r=round(sum(g_winner_rs) / len(g_winner_rs), 2) if g_winner_rs else None,
            ))
        by_setup.sort(key=lambda s: s.count, reverse=True)

        # Session bucketing (EDT = UTC-4)
        EDT_OFFSET = timedelta(hours=-4)
        SESSION_WINDOWS = [
            ("Pre-Market", 4 * 60, 9 * 60 + 30),
            ("Open Rush", 9 * 60 + 30, 11 * 60),
            ("Mid-Morning", 11 * 60, 14 * 60),
            ("Afternoon", 14 * 60, 16 * 60),
            ("After-Hours", 16 * 60, 20 * 60),
        ]

        session_map: dict[str, list[StoredTrade]] = defaultdict(list)
        for t in closed:
            ts_str = t.payload.stageTimestamps.get("entered")
            if ts_str:
                try:
                    dt_utc = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    dt_edt = dt_utc + EDT_OFFSET
                    minutes = dt_edt.hour * 60 + dt_edt.minute
                    label = "Other"
                    for lbl, start, end in SESSION_WINDOWS:
                        if start <= minutes < end:
                            label = lbl
                            break
                    session_map[label].append(t)
                except (ValueError, TypeError):
                    pass

        by_session: list[SessionBucket] = []
        session_order = [lbl for lbl, _, _ in SESSION_WINDOWS] + ["Other"]
        for label in session_order:
            group = session_map.get(label, [])
            if not group:
                continue
            g_win = sum(1 for t in group if t.payload.outcomeTag == "win")
            g_loss = sum(1 for t in group if t.payload.outcomeTag == "loss")
            g_scratch = sum(1 for t in group if t.payload.outcomeTag == "scratch")
            g_count = len(group)
            by_session.append(SessionBucket(
                label=label,
                count=g_count,
                win=g_win,
                loss=g_loss,
                scratch=g_scratch,
                win_rate=round(g_win / g_count, 4) if g_count > 0 else 0.0,
            ))

        # Alert utility
        alert_condition_map: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "acted": 0, "dismissed": 0})
        for alert in triggered_alerts:
            payload = alert.get("payload") or {}
            condition = str(payload.get("condition", "unknown"))
            task_status = str(payload.get("task_status", "pending"))
            alert_condition_map[condition]["total"] += 1
            if task_status == "acted":
                alert_condition_map[condition]["acted"] += 1
            elif task_status == "dismissed":
                alert_condition_map[condition]["dismissed"] += 1

        alert_utility: list[AlertUtilityStat] = []
        for condition, counts in alert_condition_map.items():
            total = counts["total"]
            acted = counts["acted"]
            dismissed = counts["dismissed"]
            alert_utility.append(AlertUtilityStat(
                condition=condition,
                total=total,
                acted=acted,
                dismissed=dismissed,
                act_rate=round(acted / total, 4) if total > 0 else 0.0,
            ))
        alert_utility.sort(key=lambda a: a.total, reverse=True)
        alert_utility = alert_utility[:10]

        total_alerts_fired = sum(a.total for a in alert_utility)
        total_acted = sum(a.acted for a in alert_utility)
        alert_acted_rate = round(total_acted / total_alerts_fired, 4) if total_alerts_fired > 0 else 0.0

        # Mistake tags
        MISTAKE_TAG_LABELS = {
            "entry_too_early": "Entry Too Early",
            "held_too_long": "Held Too Long",
            "ignored_stop": "Ignored Stop",
            "oversized": "Oversized",
            "chased": "Chased",
            "no_catalyst": "No Catalyst",
            "market_not_aligned": "Market Not Aligned",
            "fomo": "FOMO",
            "overtraded": "Overtraded",
        }
        tag_counts: dict[str, int] = defaultdict(int)
        for t in closed:
            for tag in (t.payload.mistakeTags or []):
                tag_counts[tag] += 1

        mistake_tags: list[MistakeTagStat] = [
            MistakeTagStat(
                tag=tag,
                label=MISTAKE_TAG_LABELS.get(tag, tag.replace("_", " ").title()),
                count=count,
            )
            for tag, count in sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)
        ]

        return ReviewMetrics(
            user_id=user_id,
            generated_at=datetime.now(timezone.utc).isoformat(),
            total_closed=total_closed,
            win_count=win_count,
            loss_count=loss_count,
            scratch_count=scratch_count,
            overall_win_rate=overall_win_rate,
            avg_winner_r=avg_winner_r,
            avg_loser_r=avg_loser_r,
            by_setup=by_setup,
            by_session=by_session,
            alert_utility=alert_utility,
            mistake_tags=mistake_tags,
            total_alerts_fired=total_alerts_fired,
            alert_acted_rate=alert_acted_rate,
        )

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
