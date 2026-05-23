from datetime import datetime, timezone

from app.domain.models import MarketEvent

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

OVERVIEW_TICKERS = ("SPY", "QQQ", "IWM")
DEFAULT_WATCHLIST = ("AAPL", "NVDA", "MSFT", "TSLA")


def sentiment_score_from_history(history: list[float]) -> float:
    """Return a 0-1 momentum sentiment score derived from recent price history.

    Compares the average of the first quarter of the window against the last
    quarter.  A rising window scores above 0.5 (Bullish); falling scores below
    (Bearish).  Requires at least 4 data points; returns 0.5 otherwise.

    Mapping (momentum = % change older → recent):
        ≥ +6 %  →  0.95  (strongly Bullish)
          0 %   →  0.50  (Neutral)
        ≤ −6 %  →  0.05  (strongly Bearish)
    """
    if len(history) < 4:
        return 0.5

    quarter = max(1, len(history) // 4)
    older_avg = sum(history[:quarter]) / quarter
    recent_avg = sum(history[-quarter:]) / quarter

    if older_avg == 0.0:
        return 0.5

    momentum_pct = (recent_avg - older_avg) / older_avg * 100.0
    score = 0.5 + momentum_pct / 12.0
    return round(max(0.05, min(0.95, score)), 3)


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
