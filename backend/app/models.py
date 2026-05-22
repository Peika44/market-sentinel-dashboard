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
    last_updated: datetime
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


class TradePlanDraftPayload(BaseModel):
    ticker: str
    entryPrice: str
    stopLoss: str
    targetPrice: str
    thesis: str
    riskPercent: str
    positionSizeUsd: str


class SaveTradePlanDraftRequest(BaseModel):
    user_id: str
    draft: TradePlanDraftPayload


class StoredTradePlanDraft(BaseModel):
    ticker: str
    updated_at: str
    payload: TradePlanDraftPayload


class AlertRulePayload(BaseModel):
    ticker: str
    condition: str
    threshold: str
    cooldownMinutes: str
    channel: str
    enabled: bool = True


class SaveAlertRuleRequest(BaseModel):
    user_id: str
    rule: AlertRulePayload


class StoredAlertRule(BaseModel):
    ticker: str
    updated_at: str
    payload: AlertRulePayload


class IndexQuote(BaseModel):
    ticker: str
    label: str
    current_price: float
    change_pct: float


class CandlePoint(BaseModel):
    label: str
    open: float
    high: float
    low: float
    close: float
