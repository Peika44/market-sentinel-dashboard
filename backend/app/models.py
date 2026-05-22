from datetime import datetime

from pydantic import BaseModel, Field


class MarketEvent(BaseModel):
    type: str = "price_update"
    ticker: str
    display_name: str
    current_price: float
    change_pct: float
    volume: int
    as_of: datetime


class StockCard(BaseModel):
    ticker: str
    display_name: str
    current_price: float
    change_pct: float
    volume: int
    sentiment_score: float
    sentiment_label: str
    urgency_score: float
    history: list[float] = Field(default_factory=list)


class DashboardSnapshot(BaseModel):
    user_id: str
    updated_at: datetime
    stocks: list[StockCard] = Field(default_factory=list)


class WatchlistMutation(BaseModel):
    user_id: str
    ticker: str


class IndexQuote(BaseModel):
    ticker: str
    label: str
    current_price: float
    change_pct: float

