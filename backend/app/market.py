from datetime import datetime, timezone

from app.models import MarketEvent

SEED_QUOTES = {
    "AAPL": 212.10,
    "MSFT": 428.55,
    "NVDA": 116.40,
    "TSLA": 177.25,
    "AMZN": 188.30,
    "META": 507.80,
    "SPY": 530.10,
    "QQQ": 456.20,
    "IWM": 208.35,
}

DISPLAY_NAMES = {
    "AAPL": "Apple",
    "MSFT": "Microsoft",
    "NVDA": "NVIDIA",
    "TSLA": "Tesla",
    "AMZN": "Amazon",
    "META": "Meta",
    "SPY": "S&P 500 ETF",
    "QQQ": "Nasdaq 100 ETF",
    "IWM": "Russell 2000 ETF",
}

SENTIMENT_SCORES = {
    "AAPL": 0.61,
    "MSFT": 0.58,
    "NVDA": 0.72,
    "TSLA": 0.37,
    "AMZN": 0.54,
    "META": 0.49,
}

OVERVIEW_TICKERS = ("SPY", "QQQ", "IWM")
DEFAULT_WATCHLIST = ("AAPL", "NVDA", "MSFT", "TSLA")


def sentiment_score_for(ticker: str) -> float:
    return SENTIMENT_SCORES.get(ticker, 0.5)


def sentiment_label_for(score: float) -> str:
    if score >= 0.62:
        return "Bullish"
    if score <= 0.38:
        return "Bearish"
    return "Neutral"


def compute_urgency(change_pct: float, sentiment_score: float) -> float:
    price_component = min(abs(change_pct) * 5.0, 100.0) * 0.65
    sentiment_component = (1.0 - sentiment_score) * 100.0 * 0.35
    return round(min(price_component + sentiment_component, 100.0), 2)


def placeholder_event(ticker: str) -> MarketEvent:
    return MarketEvent(
        ticker=ticker,
        display_name=DISPLAY_NAMES.get(ticker, ticker),
        current_price=SEED_QUOTES.get(ticker, 100.0),
        change_pct=0.0,
        volume=0,
        as_of=datetime.now(timezone.utc),
    )

