export interface StockCard {
  ticker: string;
  display_name: string;
  current_price: number | null;
  change_pct: number | null;
  volume: number;
  last_updated: string | null;
  data_status: "live" | "waiting" | "delayed";
  data_status_message?: string | null;
  data_feed?: string | null;
  sentiment_score: number;
  sentiment_label: string;
  urgency_score: number;
  history: number[];
}

export interface DashboardSnapshot {
  user_id: string;
  updated_at: string;
  stocks: StockCard[];
}

export interface TickerValidationResult {
  ticker: string;
  is_valid: boolean;
  can_add: boolean;
  display_name?: string | null;
  feed_status: "supported" | "delayed" | "unknown";
  source: string;
  message: string;
}

export interface IndexQuote {
  ticker: string;
  label: string;
  current_price: number;
  change_pct: number;
}

export interface MarketOverviewResponse {
  indices: IndexQuote[];
}

export interface HealthResponse {
  status: string;
  service: string;
  provider: string;
  feed?: string;
  cache: string;
  websocket_clients: number;
}

export type HistoryRange = "5m" | "1h" | "1D" | "5D" | "1M" | "3M" | "6M" | "1Y";

export interface CandlePoint {
  label: string;
  open: number;
  high: number;
  low: number;
  close: number;
}

export interface MarketEvent {
  type: string;
  ticker: string;
  display_name: string;
  current_price: number;
  change_pct: number;
  volume: number;
  as_of: string;
}

export type SetupType =
  | "breakout"
  | "pullback"
  | "mean_reversion"
  | "trend_continuation"
  | "event_driven";

export interface TradeChecklist {
  hasCatalyst: boolean;
  atKeyLevel: boolean;
  rrSufficient: boolean;
  marketAligned: boolean;
  withinSession: boolean;
}

export const DEFAULT_CHECKLIST: TradeChecklist = {
  hasCatalyst: false,
  atKeyLevel: false,
  rrSufficient: false,
  marketAligned: false,
  withinSession: false,
};

export interface TradePlanDraft {
  ticker: string;
  setupType?: SetupType;
  entryPrice: string;
  stopLoss: string;
  targetPrice: string;
  thesis: string;
  riskPercent: string;
  positionSizeUsd: string;
  checklist?: TradeChecklist;
}

export interface StoredTradePlanDraft {
  ticker: string;
  updated_at: string;
  payload: TradePlanDraft;
}

export interface AlertRuleDraft {
  ruleId?: string;
  ticker: string;
  condition: string;
  threshold: string;
  cooldownMinutes: string;
  channel: string;
  enabled: boolean;
}

export interface StoredAlertRule {
  rule_id: string;
  ticker: string;
  updated_at: string;
  payload: AlertRuleDraft;
}

export type AlertTaskStatus = "pending" | "snoozed" | "dismissed" | "acted";

export interface TriggeredAlertPayload {
  ticker: string;
  condition: string;
  threshold: string;
  channel: string;
  triggered_value: string;
  message: string;
  // enriched task fields (present for alerts fired after the upgrade)
  alert_id?: string | null;
  snapshot_price?: number | null;
  snapshot_volume?: number | null;
  snapshot_change_pct?: number | null;
  task_status?: AlertTaskStatus;
  snoozed_until?: string | null;
}

export interface StoredTriggeredAlert {
  ticker: string;
  triggered_at: string;
  payload: TriggeredAlertPayload;
}

export interface JournalEntryDraft {
  ticker: string;
  stage: string;
  thesis: string;
  review: string;
  outcome: string;
  outcomeTag: "open" | "win" | "loss" | "scratch";
  entryPrice: string;
  stopLoss: string;
  targetPrice: string;
}

export interface StoredJournalEntry {
  entry_id: string;
  ticker: string;
  updated_at: string;
  payload: JournalEntryDraft;
}

export interface ThesisOutcomeSummary {
  ticker: string;
  strategy_tag: string;
  current_thesis: string;
  latest_review: string;
  latest_outcome: string;
  latest_outcome_tag: "open" | "win" | "loss" | "scratch";
  latest_updated_at: string;
  total_closed_entries: number;
  win_count: number;
  loss_count: number;
  scratch_count: number;
}

export interface TickerNoteDraft {
  ticker: string;
  thesis: string;
  notes: string;
  strategyTag: string;
}

export interface StoredTickerNote {
  ticker: string;
  updated_at: string;
  payload: TickerNoteDraft;
}

export type FocusQueueBucket = "today_focus" | "monitor" | "ignore";

export interface FocusQueueEntryDraft {
  ticker: string;
  bucket: FocusQueueBucket;
  whyOnList: string;
  triggerCondition: string;
  invalidationCondition: string;
  catalystTag?: string | null;
}

export interface FocusQueueEntryView {
  ticker: string;
  updated_at: string;
  source: "generated" | "saved";
  payload: FocusQueueEntryDraft;
  generated_payload: FocusQueueEntryDraft;
}

export interface LeaderHoldingDraft {
  ticker: string;
  positionStatus: "holding" | "new" | "adding" | "trimming" | "closed";
  conviction: "light" | "standard" | "heavy";
  timeHorizon: "short" | "swing" | "mid";
  entryZone: string;
  thesis: string;
  invalidatedWhen: string;
  lastUpdatedAt: string;
}

export interface StoredLeaderHolding {
  ticker: string;
  updated_at: string;
  payload: LeaderHoldingDraft;
}

export interface CatalystEventDraft {
  eventId?: string;
  scope: "macro" | "ticker";
  ticker: string;
  eventType:
    | "earnings"
    | "macro_cpi"
    | "macro_fomc"
    | "macro_nfp"
    | "ex_dividend"
    | "split"
    | "options_expiry"
    | "news_tag";
  headline: string;
  eventDate: string;
  timeLabel: string;
  tags: string[];
  notes: string;
}

export interface StoredCatalystEvent {
  event_id: string;
  ticker: string;
  updated_at: string;
  payload: CatalystEventDraft;
}

export interface UrgencySettingsDraft {
  priceWeightPct: number;
  sentimentWeightPct: number;
  priceMoveScale: number;
  lowThreshold: number;
  highThreshold: number;
}

export interface StoredUrgencySettings {
  updated_at: string;
  payload: UrgencySettingsDraft;
}

export type TradeStage =
  | "idea"
  | "planned"
  | "armed"
  | "entered"
  | "exited"
  | "reviewed";

export interface TradeDraft {
  tradeId?: string;
  ticker: string;
  setupType: SetupType;
  stage: TradeStage;
  stageNotes: Partial<Record<TradeStage, string>>;
  stageTimestamps: Partial<Record<TradeStage, string>>;
  entryPrice: string;
  stopLoss: string;
  targetPrice: string;
  riskPercent: string;
  actualEntry: string;
  actualExit: string;
  outcomeTag: "open" | "win" | "loss" | "scratch";
  mistakeTags?: string[];
}

export interface StoredTrade {
  trade_id: string;
  ticker: string;
  updated_at: string;
  payload: TradeDraft;
}

export interface DigestMetric {
  label: string;
  value: string;
  detail: string;
}

export interface EndOfDayDigest {
  user_id: string;
  generated_at: string;
  headline: string;
  summary: string;
  metrics: DigestMetric[];
}

export interface SetupStat {
  setup_type: string;
  count: number;
  win: number;
  loss: number;
  scratch: number;
  win_rate: number;
  avg_winner_r: number | null;
}

export interface SessionBucket {
  label: string;
  count: number;
  win: number;
  loss: number;
  scratch: number;
  win_rate: number;
}

export interface AlertUtilityStat {
  condition: string;
  total: number;
  acted: number;
  dismissed: number;
  act_rate: number;
}

export interface MistakeTagStat {
  tag: string;
  label: string;
  count: number;
}

export interface BoardFilters {
  status: "all" | "live" | "delayed" | "waiting";
  minUrgency: "any" | "watch" | "hot";
  hasCatalyst: boolean;
}

export interface TradeFilters {
  setupType: SetupType | "all";
  stage: TradeStage | "all";
  outcomeTag: "all" | "open" | "win" | "loss" | "scratch";
}

export interface SavedFilterPreset {
  id: string;
  name: string;
  view: "board" | "trades";
  boardFilters?: BoardFilters;
  tradeFilters?: TradeFilters;
}

export interface ReviewMetrics {
  user_id: string;
  generated_at: string;
  total_closed: number;
  win_count: number;
  loss_count: number;
  scratch_count: number;
  overall_win_rate: number;
  avg_winner_r: number | null;
  avg_loser_r: number | null;
  by_setup: SetupStat[];
  by_session: SessionBucket[];
  alert_utility: AlertUtilityStat[];
  mistake_tags: MistakeTagStat[];
  total_alerts_fired: number;
  alert_acted_rate: number;
}
