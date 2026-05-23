from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

_VALID_CONDITIONS = {
    "urgency_above",
    "price_change_above",
    "price_change_below",
    "volume_above",
    "target_hit",
    "drop_below_stop",
    "breakout_above_recent_high",
    "breakdown_below_recent_low",
}


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
    current_price: float | None = None
    change_pct: float | None = None
    volume: int = 0
    last_updated: datetime | None = None
    data_status: Literal["live", "waiting", "delayed"] = "waiting"
    data_status_message: str | None = None
    data_feed: str | None = None
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


class TickerValidationResult(BaseModel):
    ticker: str
    is_valid: bool
    can_add: bool
    display_name: str | None = None
    feed_status: Literal["supported", "delayed", "unknown"] = "unknown"
    source: str
    message: str


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
    ruleId: str | None = None
    ticker: str
    condition: str
    threshold: str
    cooldownMinutes: str
    channel: str
    enabled: bool = True

    @field_validator("condition")
    @classmethod
    def condition_must_be_valid(cls, v: str) -> str:
        if v not in _VALID_CONDITIONS:
            raise ValueError(
                f"Unknown condition '{v}'. "
                f"Valid options: {', '.join(sorted(_VALID_CONDITIONS))}"
            )
        return v

    @field_validator("threshold")
    @classmethod
    def threshold_must_be_numeric(cls, v: str) -> str:
        try:
            val = float(v)
        except (TypeError, ValueError):
            raise ValueError("Threshold must be a valid number (e.g. 2.5 or 450).")
        if val < 0:
            raise ValueError("Threshold must be zero or greater.")
        return v

    @field_validator("cooldownMinutes")
    @classmethod
    def cooldown_must_be_positive(cls, v: str) -> str:
        try:
            val = float(v)
        except (TypeError, ValueError):
            raise ValueError("Cooldown must be a valid number of minutes (e.g. 15).")
        if val <= 0:
            raise ValueError("Cooldown must be greater than 0.")
        return v


class SaveAlertRuleRequest(BaseModel):
    user_id: str
    rule: AlertRulePayload


class StoredAlertRule(BaseModel):
    rule_id: str
    ticker: str
    updated_at: str
    payload: AlertRulePayload


class TriggeredAlertPayload(BaseModel):
    rule_id: str | None = None
    ticker: str
    condition: str
    threshold: str
    channel: str
    triggered_value: str
    message: str


class StoredTriggeredAlert(BaseModel):
    ticker: str
    triggered_at: str
    payload: TriggeredAlertPayload


class JournalEntryPayload(BaseModel):
    ticker: str
    stage: str
    thesis: str
    review: str
    outcome: str
    entryPrice: str = ""
    stopLoss: str = ""
    targetPrice: str = ""


class SaveJournalEntryRequest(BaseModel):
    user_id: str
    entry: JournalEntryPayload


class StoredJournalEntry(BaseModel):
    entry_id: str
    ticker: str
    updated_at: str
    payload: JournalEntryPayload


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
