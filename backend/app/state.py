from collections import defaultdict, deque
from datetime import datetime, timezone

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
from app.models import DashboardSnapshot, IndexQuote, MarketEvent, StockCard


class DashboardState:
    def __init__(self) -> None:
        self.watchlists: dict[str, set[str]] = {
            settings.default_user_id: set(DEFAULT_WATCHLIST)
        }
        self.latest_quotes: dict[str, MarketEvent] = {}
        self.price_history: dict[str, deque[float]] = defaultdict(
            lambda: deque(maxlen=24)
        )

        for ticker, price in SEED_QUOTES.items():
            self.price_history[ticker].append(price)

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
                    history=list(self.price_history[ticker]),
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

