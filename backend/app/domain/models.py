from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

_VALID_CONDITIONS = {
    "urgency_above",
    "price_change_above",
    "price_change_below",
    "gap_up_above",
    "gap_down_below",
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
    setupType: str = "breakout"
    entryPrice: str
    stopLoss: str
    targetPrice: str
    thesis: str
    riskPercent: str
    positionSizeUsd: str
    checklist: dict = Field(
        default_factory=lambda: {
            "hasCatalyst": False,
            "atKeyLevel": False,
            "rrSufficient": False,
            "marketAligned": False,
            "withinSession": False,
        }
    )


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
    alert_id: str | None = None
    ticker: str
    condition: str
    threshold: str
    channel: str
    triggered_value: str
    message: str
    # Market snapshot at trigger time
    snapshot_price: float | None = None
    snapshot_volume: int | None = None
    snapshot_change_pct: float | None = None
    # Task lifecycle
    task_status: str = "pending"  # pending | snoozed | dismissed | acted
    snoozed_until: str | None = None


class UpdateAlertTaskRequest(BaseModel):
    task_status: str
    snoozed_until: str | None = None


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
    outcomeTag: Literal["open", "win", "loss", "scratch"] = "open"
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


class ThesisOutcomeSummary(BaseModel):
    ticker: str
    strategy_tag: str = ""
    current_thesis: str = ""
    latest_review: str = ""
    latest_outcome: str = ""
    latest_outcome_tag: Literal["open", "win", "loss", "scratch"] = "open"
    latest_updated_at: str = ""
    total_closed_entries: int = 0
    win_count: int = 0
    loss_count: int = 0
    scratch_count: int = 0


class TickerNotePayload(BaseModel):
    ticker: str
    thesis: str = ""
    notes: str = ""
    strategyTag: str = ""


class SaveTickerNoteRequest(BaseModel):
    user_id: str
    note: TickerNotePayload


class StoredTickerNote(BaseModel):
    ticker: str
    updated_at: str
    payload: TickerNotePayload


class FocusQueueEntryPayload(BaseModel):
    ticker: str
    bucket: Literal["today_focus", "monitor", "ignore"] = "monitor"
    whyOnList: str = ""
    triggerCondition: str = ""
    invalidationCondition: str = ""
    catalystTag: str | None = None

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, v: str) -> str:
        return v.strip().upper()


class SaveFocusQueueEntryRequest(BaseModel):
    user_id: str
    entry: FocusQueueEntryPayload


class FocusQueueEntryView(BaseModel):
    ticker: str
    updated_at: str
    source: Literal["generated", "saved"] = "generated"
    payload: FocusQueueEntryPayload
    generated_payload: FocusQueueEntryPayload


class LeaderHoldingPayload(BaseModel):
    ticker: str
    positionStatus: Literal["holding", "new", "adding", "trimming", "closed"] = "holding"
    conviction: Literal["light", "standard", "heavy"] = "standard"
    timeHorizon: Literal["short", "swing", "mid"] = "swing"
    entryZone: str = ""
    thesis: str = ""
    invalidatedWhen: str = ""
    lastUpdatedAt: str = ""

    @field_validator("ticker")
    @classmethod
    def normalize_leader_ticker(cls, v: str) -> str:
        return v.strip().upper()


class SaveLeaderHoldingRequest(BaseModel):
    user_id: str
    holding: LeaderHoldingPayload


class StoredLeaderHolding(BaseModel):
    ticker: str
    updated_at: str
    payload: LeaderHoldingPayload


class CatalystEventPayload(BaseModel):
    eventId: str | None = None
    scope: Literal["macro", "ticker"] = "ticker"
    ticker: str = ""
    eventType: Literal[
        "earnings",
        "macro_cpi",
        "macro_fomc",
        "macro_nfp",
        "ex_dividend",
        "split",
        "options_expiry",
        "news_tag",
    ] = "news_tag"
    headline: str = ""
    eventDate: str = ""
    timeLabel: str = ""
    tags: list[str] = Field(default_factory=list)
    notes: str = ""

    @field_validator("ticker")
    @classmethod
    def normalize_catalyst_ticker(cls, v: str) -> str:
        return v.strip().upper()


class SaveCatalystEventRequest(BaseModel):
    user_id: str
    event: CatalystEventPayload


class StoredCatalystEvent(BaseModel):
    event_id: str
    ticker: str
    updated_at: str
    payload: CatalystEventPayload


class UrgencySettingsPayload(BaseModel):
    priceWeightPct: float = 65.0
    sentimentWeightPct: float = 35.0
    priceMoveScale: float = 5.0
    lowThreshold: float = 40.0
    highThreshold: float = 70.0

    @field_validator("priceWeightPct", "sentimentWeightPct")
    @classmethod
    def weights_must_be_non_negative(cls, v: float) -> float:
        if v < 0:
            raise ValueError("Weights must be zero or greater.")
        return v

    @field_validator("priceMoveScale")
    @classmethod
    def scale_must_be_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Price move scale must be greater than 0.")
        return v

    @field_validator("lowThreshold", "highThreshold")
    @classmethod
    def thresholds_must_be_in_range(cls, v: float) -> float:
        if v < 0 or v > 100:
            raise ValueError("Urgency thresholds must be between 0 and 100.")
        return v

    @model_validator(mode="after")
    def validate_formula(self) -> "UrgencySettingsPayload":
        if self.priceWeightPct + self.sentimentWeightPct <= 0:
            raise ValueError("At least one urgency weight must be greater than 0.")
        if self.highThreshold <= self.lowThreshold:
            raise ValueError("High threshold must be greater than low threshold.")
        return self


class SaveUrgencySettingsRequest(BaseModel):
    user_id: str
    settings: UrgencySettingsPayload


class StoredUrgencySettings(BaseModel):
    updated_at: str
    payload: UrgencySettingsPayload


class DigestMetric(BaseModel):
    label: str
    value: str
    detail: str


class EndOfDayDigest(BaseModel):
    user_id: str
    generated_at: str
    headline: str
    summary: str
    metrics: list[DigestMetric] = Field(default_factory=list)


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


class TradeLifecyclePayload(BaseModel):
    tradeId: str | None = None
    ticker: str
    setupType: str = "breakout"
    stage: Literal["idea", "planned", "armed", "entered", "exited", "reviewed"] = "idea"
    stageNotes: dict = Field(default_factory=dict)
    stageTimestamps: dict = Field(default_factory=dict)
    entryPrice: str = ""
    stopLoss: str = ""
    targetPrice: str = ""
    actualEntry: str = ""
    actualExit: str = ""
    outcomeTag: Literal["open", "win", "loss", "scratch"] = "open"
    mistakeTags: list[str] = Field(default_factory=list)

    @field_validator("ticker")
    @classmethod
    def normalize_trade_ticker(cls, v: str) -> str:
        return v.strip().upper()


class SaveTradeRequest(BaseModel):
    user_id: str
    trade: TradeLifecyclePayload


class StoredTrade(BaseModel):
    trade_id: str
    ticker: str
    updated_at: str
    payload: TradeLifecyclePayload


class SetupStat(BaseModel):
    setup_type: str
    count: int
    win: int
    loss: int
    scratch: int
    win_rate: float
    avg_winner_r: float | None = None


class SessionBucket(BaseModel):
    label: str
    count: int
    win: int
    loss: int
    scratch: int
    win_rate: float


class AlertUtilityStat(BaseModel):
    condition: str
    total: int
    acted: int
    dismissed: int
    act_rate: float


class MistakeTagStat(BaseModel):
    tag: str
    label: str
    count: int


class ReviewMetrics(BaseModel):
    user_id: str
    generated_at: str
    total_closed: int
    win_count: int
    loss_count: int
    scratch_count: int
    overall_win_rate: float
    avg_winner_r: float | None = None
    avg_loser_r: float | None = None
    by_setup: list[SetupStat]
    by_session: list[SessionBucket]
    alert_utility: list[AlertUtilityStat]
    mistake_tags: list[MistakeTagStat]
    total_alerts_fired: int
    alert_acted_rate: float
