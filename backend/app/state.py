from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
import random

from app.config import settings
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
from app.models import CandlePoint, DashboardSnapshot, IndexQuote, MarketEvent, StockCard

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


class DashboardState:
    def __init__(self) -> None:
        self.watchlists: dict[str, set[str]] = {
            settings.default_user_id: set(DEFAULT_WATCHLIST)
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

    def add_to_watchlist(self, user_id: str, ticker: str) -> None:
        user_watchlist = self.watchlists.setdefault(user_id, set(DEFAULT_WATCHLIST))
        user_watchlist.add(ticker.upper())

    def remove_from_watchlist(self, user_id: str, ticker: str) -> None:
        user_watchlist = self.watchlists.setdefault(user_id, set(DEFAULT_WATCHLIST))
        user_watchlist.discard(ticker.upper())

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

        return candles
