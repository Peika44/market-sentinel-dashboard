export interface StockCard {
  ticker: string;
  display_name: string;
  current_price: number;
  change_pct: number;
  volume: number;
  last_updated: string;
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

export interface IndexQuote {
  ticker: string;
  label: string;
  current_price: number;
  change_pct: number;
}

export interface MarketOverviewResponse {
  indices: IndexQuote[];
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

export interface TradePlanDraft {
  ticker: string;
  entryPrice: string;
  stopLoss: string;
  targetPrice: string;
  thesis: string;
  riskPercent: string;
  positionSizeUsd: string;
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

export interface TriggeredAlertPayload {
  ticker: string;
  condition: string;
  threshold: string;
  channel: string;
  triggered_value: string;
  message: string;
}

export interface StoredTriggeredAlert {
  ticker: string;
  triggered_at: string;
  payload: TriggeredAlertPayload;
}
