export interface StockCard {
  ticker: string;
  display_name: string;
  current_price: number;
  change_pct: number;
  volume: number;
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
