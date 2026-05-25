import { FormEvent, useEffect, useState } from "react";

import type {
  AlertRuleDraft,
  AlertTaskStatus,
  BoardFilters,
  CatalystEventDraft,
  DashboardSnapshot,
  EndOfDayDigest,
  FocusQueueBucket,
  FocusQueueEntryDraft,
  FocusQueueEntryView,
  HealthResponse,
  IndexQuote,
  JournalEntryDraft,
  LeaderHoldingDraft,
  MarketEvent,
  MarketOverviewResponse,
  ReviewMetrics,
  SavedFilterPreset,
  StoredAlertRule,
  StoredCatalystEvent,
  StoredJournalEntry,
  StoredLeaderHolding,
  StoredTickerNote,
  StoredUrgencySettings,
  StockCard,
  StoredTrade,
  StoredTradePlanDraft,
  StoredTriggeredAlert,
  ThesisOutcomeSummary,
  TickerNoteDraft,
  TickerValidationResult,
  TradeDraft,
  TradeFilters,
  TradePlanDraft,
  UrgencySettingsDraft,
} from "./types";
import { StockChartModal } from "./components/StockChartModal";
import { Sparkline, UrgencyBar } from "./components/Sparkline";
import { TradePlanModal } from "./components/TradePlanModal";
import { AlertRuleModal } from "./components/AlertRuleModal";
import { JournalModal } from "./components/JournalModal";
import { DetailPanel } from "./components/DetailPanel";
import { UrgencySettingsModal } from "./components/UrgencySettingsModal";
import { TradeLifecyclePanel } from "./components/TradeLifecyclePanel";
import { ReviewPanel } from "./components/ReviewPanel";
import { FilterStrip } from "./components/FilterStrip";
import {
  formatAlertCondition,
  formatChangePct,
  formatCurrency,
  formatVolume,
} from "./utils/format";
import { useMarketStatus } from "./hooks/useMarketStatus";

const DEMO_USER_ID = "demo-user";
const OVERVIEW_TICKERS = new Set(["SPY", "QQQ", "IWM"]);
const ALERTS_PAGE = 5;
const JOURNAL_PAGE = 5;
const SESSION_OPTIONS = [
  { id: "pre-market", label: "Pre-Market" },
  { id: "live", label: "Live" },
  { id: "close", label: "Close" },
] as const;
const VIEW_OPTIONS = [
  { id: "overview", label: "Overview" },
  { id: "board", label: "Watchlist" },
  { id: "workspace", label: "Workspace" },
  { id: "leader", label: "Leader" },
  { id: "catalysts", label: "Catalysts" },
  { id: "trades", label: "Trades" },
  { id: "review", label: "Review" },
] as const;
type SessionView = (typeof SESSION_OPTIONS)[number]["id"];
type MainView = (typeof VIEW_OPTIONS)[number]["id"];
const DEFAULT_URGENCY_SETTINGS: UrgencySettingsDraft = {
  priceWeightPct: 65,
  sentimentWeightPct: 35,
  priceMoveScale: 5,
  lowThreshold: 40,
  highThreshold: 70,
};

const DEFAULT_BOARD_FILTERS: BoardFilters = { status: "all", minUrgency: "any", hasCatalyst: false };
const DEFAULT_TRADE_FILTERS: TradeFilters = { setupType: "all", stage: "all", outcomeTag: "all" };
const LS_BOARD_FILTERS = "msd:board-filters";
const LS_TRADE_FILTERS = "msd:trade-filters";
const LS_PRESETS = "msd:filter-presets";

function loadFromStorage<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    if (raw == null) return fallback;
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

function saveToStorage<T>(key: string, value: T): void {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // ignore storage errors
  }
}

function computeUrgency(
  settings: UrgencySettingsDraft,
  changePct: number,
  sentimentScore: number,
): number {
  const totalWeight = settings.priceWeightPct + settings.sentimentWeightPct || 1;
  const priceWeight = settings.priceWeightPct / totalWeight;
  const sentimentWeight = settings.sentimentWeightPct / totalWeight;
  const priceComponent = Math.min(Math.abs(changePct) * settings.priceMoveScale, 100) * priceWeight;
  const sentimentComponent = (1 - sentimentScore) * 100 * sentimentWeight;
  return Math.min(priceComponent + sentimentComponent, 100);
}

function sortByUrgency(stocks: StockCard[]): StockCard[] {
  return [...stocks].sort((left, right) => right.urgency_score - left.urgency_score);
}

function buildOverviewPreview(
  urgencySettings: UrgencySettingsDraft,
  quote: IndexQuote,
  history: number[],
): StockCard {
  return {
    ticker: quote.ticker,
    display_name: quote.label,
    current_price: quote.current_price,
    change_pct: quote.change_pct,
    volume: 0,
    last_updated: new Date().toISOString(),
    data_status: "live",
    data_status_message: "Live overview snapshot.",
    data_feed: "Overview",
    sentiment_score: 0.5,
    sentiment_label: "Neutral",
    urgency_score: computeUrgency(urgencySettings, Math.abs(quote.change_pct), 0.5),
    history,
  };
}

function buildTradePlanDraft(stock: StockCard): TradePlanDraft {
  const entry = stock.current_price ?? 0;
  return {
    ticker: stock.ticker,
    setupType: "breakout",
    entryPrice: entry.toFixed(2),
    stopLoss: (entry * 0.97).toFixed(2),
    targetPrice: (entry * 1.06).toFixed(2),
    thesis: `${stock.ticker} is ranked high on the dashboard with ${stock.sentiment_label.toLowerCase()} sentiment and an urgency score of ${stock.urgency_score.toFixed(0)}.`,
    riskPercent: "1.0",
    positionSizeUsd: "1000",
    checklist: {
      hasCatalyst: false,
      atKeyLevel: false,
      rrSufficient: false,
      marketAligned: false,
      withinSession: false,
    },
  };
}

function buildAlertRuleDraft(stock: StockCard): AlertRuleDraft {
  return {
    ticker: stock.ticker,
    condition: "urgency_above",
    threshold: Math.max(40, Math.round(stock.urgency_score)).toString(),
    cooldownMinutes: "15",
    channel: "dashboard",
    enabled: true,
  };
}

function buildTargetAlertFromTradePlan(draft: TradePlanDraft): AlertRuleDraft {
  return {
    ticker: draft.ticker,
    condition: "target_hit",
    threshold: draft.targetPrice,
    cooldownMinutes: "15",
    channel: "dashboard",
    enabled: true,
  };
}

function buildStopAlertFromTradePlan(draft: TradePlanDraft): AlertRuleDraft {
  return {
    ticker: draft.ticker,
    condition: "drop_below_stop",
    threshold: draft.stopLoss,
    cooldownMinutes: "15",
    channel: "dashboard",
    enabled: true,
  };
}

function buildJournalDraft(stock: StockCard): JournalEntryDraft {
  return {
    ticker: stock.ticker,
    stage: "monitoring",
    thesis: `${stock.ticker} remains on the dashboard because of its current urgency and sentiment profile.`,
    review: "",
    outcome: "",
    outcomeTag: "open",
    entryPrice: "",
    stopLoss: "",
    targetPrice: "",
  };
}

function buildJournalFromTradePlan(draft: TradePlanDraft): JournalEntryDraft {
  return {
    ticker: draft.ticker,
    stage: "monitoring",
    thesis: draft.thesis,
    review: "",
    outcome: "",
    outcomeTag: "open",
    entryPrice: draft.entryPrice,
    stopLoss: draft.stopLoss,
    targetPrice: draft.targetPrice,
  };
}

async function saveAlertRuleDraft(userId: string, rule: AlertRuleDraft): Promise<void> {
  const response = await fetch("/api/alert-rules", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: userId, rule }),
  });
  if (!response.ok) {
    throw new Error("Failed to save alert rule.");
  }
}

async function readErrorMessage(response: Response, fallback: string): Promise<string> {
  try {
    const payload = (await response.json()) as { detail?: string };
    if (typeof payload.detail === "string" && payload.detail.trim()) {
      return payload.detail;
    }
  } catch {
    // Ignore malformed error bodies and fall back to the caller-supplied message.
  }
  return fallback;
}

async function fetchTickerValidation(ticker: string): Promise<TickerValidationResult> {
  const response = await fetch(`/api/tickers/validate?ticker=${encodeURIComponent(ticker)}`);
  if (!response.ok) {
    throw new Error(await readErrorMessage(response, "Ticker validation failed."));
  }
  return (await response.json()) as TickerValidationResult;
}

function isLiveStock(stock: StockCard): boolean {
  return stock.data_status === "live";
}

function hasUsablePrice(stock: StockCard): boolean {
  return stock.current_price != null;
}

function getFreshnessLabel(
  lastUpdated: string | null,
  dataStatus: StockCard["data_status"],
): { label: string; stale: boolean } {
  if (dataStatus === "waiting" || !lastUpdated) {
    return { label: "Waiting for first market tick", stale: true };
  }
  if (dataStatus === "delayed") {
    return { label: "Using delayed bootstrap data", stale: true };
  }

  const updatedAt = new Date(lastUpdated).getTime();
  const ageSeconds = Math.max(0, Math.round((Date.now() - updatedAt) / 1000));

  if (ageSeconds <= 60) {
    return { label: `Updated ${ageSeconds}s ago`, stale: false };
  }
  const ageMinutes = Math.round(ageSeconds / 60);
  return { label: `Updated ${ageMinutes}m ago`, stale: ageMinutes >= 2 };
}

function groupAlertsByTicker(rules: StoredAlertRule[]): Array<{
  ticker: string;
  rules: StoredAlertRule[];
}> {
  const groups = new Map<string, StoredAlertRule[]>();
  for (const rule of rules) {
    const existing = groups.get(rule.ticker) ?? [];
    existing.push(rule);
    groups.set(rule.ticker, existing);
  }
  return Array.from(groups.entries()).map(([ticker, groupedRules]) => ({
    ticker,
    rules: groupedRules,
  }));
}

function groupStocksByStrategy(
  stocks: StockCard[],
  notes: StoredTickerNote[],
): Array<{ name: string; stocks: StockCard[] }> {
  const strategyByTicker = new Map(
    notes.map((note) => [note.ticker, note.payload.strategyTag.trim() || "Unsorted"]),
  );
  const groups = new Map<string, StockCard[]>();

  for (const stock of stocks) {
    const groupName = strategyByTicker.get(stock.ticker) ?? "Unsorted";
    const existing = groups.get(groupName) ?? [];
    existing.push(stock);
    groups.set(groupName, existing);
  }

  return Array.from(groups.entries())
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([name, groupedStocks]) => ({
      name,
      stocks: groupedStocks,
    }));
}

function focusBucketLabel(bucket: FocusQueueBucket): string {
  if (bucket === "today_focus") return "Today Focus";
  if (bucket === "monitor") return "Monitor";
  return "Ignore for now";
}

function focusBucketDescription(bucket: FocusQueueBucket): string {
  if (bucket === "today_focus") return "Names that deserve active screen time and decision energy.";
  if (bucket === "monitor") return "Names worth tracking, but not yet primary action items.";
  return "Names to intentionally de-prioritize until the setup improves.";
}

function buildEmptyLeaderHolding(ticker = ""): LeaderHoldingDraft {
  return {
    ticker,
    positionStatus: "holding",
    conviction: "standard",
    timeHorizon: "swing",
    entryZone: "",
    thesis: "",
    invalidatedWhen: "",
    lastUpdatedAt: "",
  };
}

function buildEmptyCatalystEvent(ticker = ""): CatalystEventDraft {
  return {
    scope: ticker ? "ticker" : "macro",
    ticker,
    eventType: ticker ? "earnings" : "macro_cpi",
    headline: "",
    eventDate: "",
    timeLabel: "",
    tags: [],
    notes: "",
  };
}

function getTodayStr(): string {
  return new Date().toISOString().split("T")[0];
}

function getWeekEndStr(): string {
  const d = new Date();
  d.setDate(d.getDate() + 6);
  return d.toISOString().split("T")[0];
}

function buildSessionSummary(
  session: "pre-market" | "live" | "close",
  stocks: StockCard[],
  notes: StoredTickerNote[],
): { title: string; body: string } {
  if (session === "pre-market") {
    const tagged = notes.filter((note) => note.payload.strategyTag.trim()).length;
    return {
      title: "Plan the board before the bell",
      body: `${tagged} symbols already have a strategy tag. Use notes and thesis fields to shape the opening watchlist.`,
    };
  }
  if (session === "close") {
    const delayed = stocks.filter((stock) => stock.data_status === "delayed").length;
    return {
      title: "Review the session and tighten notes",
      body: `${delayed} symbols are still on delayed coverage. This is a good time to update notes, alerts, and journal entries before tomorrow.`,
    };
  }
  const live = stocks.filter((stock) => stock.data_status === "live").length;
  return {
    title: "Run the active session",
    body: `${live} symbols are live right now. Prioritize the highest-urgency names and keep notes current as setups evolve.`,
  };
}

function buildDailySummary(
  session: "pre-market" | "live" | "close",
  indices: IndexQuote[],
  stocks: StockCard[],
  alerts: StoredTriggeredAlert[],
  notes: StoredTickerNote[],
): Array<{ label: string; value: string; detail: string }> {
  const positiveIndices = indices.filter((quote) => quote.change_pct >= 0).length;
  const indexTone =
    positiveIndices === indices.length
      ? "Broad Risk-On"
      : positiveIndices === 0
        ? "Broad Risk-Off"
        : "Mixed Tape";

  const liveStocks = stocks.filter((stock) => stock.data_status === "live");
  const topUrgency = [...liveStocks]
    .sort((left, right) => right.urgency_score - left.urgency_score)
    .slice(0, 3)
    .map((stock) => stock.ticker)
    .join(", ") || "No live symbols";

  const recentTriggered = alerts.slice(0, 3).map((alert) => alert.ticker).join(", ") || "No triggers";
  const tagged = notes.filter((note) => note.payload.strategyTag.trim()).length;
  const delayed = stocks.filter((stock) => stock.data_status === "delayed").length;

  return [
    {
      label: "Index Tone",
      value: indexTone,
      detail:
        session === "pre-market"
          ? "Use this to frame opening bias before promoting names into active setups."
          : "Sector and index tone should shape which watchlist names deserve attention first.",
    },
    {
      label: "Top Urgency",
      value: topUrgency,
      detail: "Highest-ranked symbols based on the current urgency formula.",
    },
    {
      label: "Alert Pressure",
      value: recentTriggered,
      detail: "Most recent triggered alerts that may require review or follow-up.",
    },
    {
      label: "Prep Coverage",
      value: `${tagged}/${stocks.length} tagged · ${delayed} delayed`,
      detail: "How much of the board already has strategy context and where feed coverage is still limited.",
    },
  ];
}

function App() {
  const [stocks, setStocks] = useState<StockCard[]>([]);
  const [indices, setIndices] = useState<IndexQuote[]>([]);
  const [indexHistory, setIndexHistory] = useState<Record<string, number[]>>({});
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
  const [tickerInput, setTickerInput] = useState("");
  const [tickerValidation, setTickerValidation] = useState<TickerValidationResult | null>(null);
  const [validatingTicker, setValidatingTicker] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [connected, setConnected] = useState(false);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [sessionView, setSessionView] = useState<SessionView>("live");
  const [activeView, setActiveView] = useState<MainView>("overview");
  const [showChart, setShowChart] = useState(false);
  const [showUrgencySettings, setShowUrgencySettings] = useState(false);
  const [urgencySettings, setUrgencySettings] = useState<UrgencySettingsDraft>(DEFAULT_URGENCY_SETTINGS);
  const [savingUrgencySettings, setSavingUrgencySettings] = useState(false);
  const [tradePlanDraft, setTradePlanDraft] = useState<TradePlanDraft | null>(null);
  const [retryingBootstrap, setRetryingBootstrap] = useState(false);
  const [digest, setDigest] = useState<EndOfDayDigest | null>(null);
  const [sendingDigest, setSendingDigest] = useState(false);
  const [savedDrafts, setSavedDrafts] = useState<StoredTradePlanDraft[]>([]);
  const [savingDraft, setSavingDraft] = useState(false);
  const [alertRuleDraft, setAlertRuleDraft] = useState<AlertRuleDraft | null>(null);
  const [savedAlertRules, setSavedAlertRules] = useState<StoredAlertRule[]>([]);
  const [savingAlertRule, setSavingAlertRule] = useState(false);
  const [alertValidationError, setAlertValidationError] = useState<string | null>(null);
  const [triggeredAlerts, setTriggeredAlerts] = useState<StoredTriggeredAlert[]>([]);
  const [alertsOffset, setAlertsOffset] = useState(0);
  const [hasMoreAlerts, setHasMoreAlerts] = useState(false);
  const [journalDraft, setJournalDraft] = useState<JournalEntryDraft | null>(null);
  const [savedJournalEntries, setSavedJournalEntries] = useState<StoredJournalEntry[]>([]);
  const [savingJournalEntry, setSavingJournalEntry] = useState(false);
  const [thesisOutcomeSummary, setThesisOutcomeSummary] = useState<ThesisOutcomeSummary | null>(null);
  const [tickerNote, setTickerNote] = useState<StoredTickerNote | null>(null);
  const [editingNote, setEditingNote] = useState<TickerNoteDraft | null>(null);
  const [savingTickerNote, setSavingTickerNote] = useState(false);
  const [tickerNotes, setTickerNotes] = useState<StoredTickerNote[]>([]);
  const [focusQueueEntries, setFocusQueueEntries] = useState<FocusQueueEntryView[]>([]);
  const [editingFocusEntry, setEditingFocusEntry] = useState<FocusQueueEntryDraft | null>(null);
  const [focusQueueEntryMeta, setFocusQueueEntryMeta] = useState<FocusQueueEntryView | null>(null);
  const [savingFocusQueueEntry, setSavingFocusQueueEntry] = useState(false);
  const [leaderHoldings, setLeaderHoldings] = useState<StoredLeaderHolding[]>([]);
  const [editingLeaderHolding, setEditingLeaderHolding] = useState<LeaderHoldingDraft>(
    buildEmptyLeaderHolding(),
  );
  const [savingLeaderHolding, setSavingLeaderHolding] = useState(false);
  const [catalystEvents, setCatalystEvents] = useState<StoredCatalystEvent[]>([]);
  const [editingCatalystEvent, setEditingCatalystEvent] = useState<CatalystEventDraft>(
    buildEmptyCatalystEvent(),
  );
  const [catalystTagsInput, setCatalystTagsInput] = useState("");
  const [savingCatalystEvent, setSavingCatalystEvent] = useState(false);
  const [catalystView, setCatalystView] = useState<"today" | "this_week" | "by_ticker">("today");
  const [trades, setTrades] = useState<StoredTrade[]>([]);
  const [reviewMetrics, setReviewMetrics] = useState<ReviewMetrics | null>(null);
  const [journalOffset, setJournalOffset] = useState(0);
  const [hasMoreJournal, setHasMoreJournal] = useState(false);
  const [boardFilters, setBoardFiltersRaw] = useState<BoardFilters>(
    () => loadFromStorage(LS_BOARD_FILTERS, DEFAULT_BOARD_FILTERS),
  );
  const [tradeFilters, setTradeFiltersRaw] = useState<TradeFilters>(
    () => loadFromStorage(LS_TRADE_FILTERS, DEFAULT_TRADE_FILTERS),
  );
  const [savedPresets, setSavedPresetsRaw] = useState<SavedFilterPreset[]>(
    () => loadFromStorage(LS_PRESETS, []),
  );
  const marketStatus = useMarketStatus();
  function setBoardFilters(f: BoardFilters) { saveToStorage(LS_BOARD_FILTERS, f); setBoardFiltersRaw(f); }
  function setTradeFilters(f: TradeFilters) { saveToStorage(LS_TRADE_FILTERS, f); setTradeFiltersRaw(f); }
  function setSavedPresets(p: SavedFilterPreset[]) { saveToStorage(LS_PRESETS, p); setSavedPresetsRaw(p); }

  const groupedAlerts = groupAlertsByTicker(savedAlertRules);
  const normalizedTickerInput = tickerInput.trim().toUpperCase();
  const tickerAlreadyTracked = stocks.some((stock) => stock.ticker === normalizedTickerInput);

  async function loadDashboard() {
    const response = await fetch(`/api/dashboard/${DEMO_USER_ID}`);
    if (!response.ok) throw new Error("Failed to load dashboard snapshot.");
    const payload = (await response.json()) as DashboardSnapshot;
    const nextStocks = sortByUrgency(payload.stocks);
    setStocks(nextStocks);
    setSelectedSymbol((current) => current ?? nextStocks[0]?.ticker ?? null);
  }

  async function loadOverview() {
    const response = await fetch("/api/market-overview");
    if (!response.ok) throw new Error("Failed to load market overview.");
    const payload = (await response.json()) as MarketOverviewResponse;
    setIndices(payload.indices);
    setIndexHistory((prev) => {
      const next = { ...prev };
      for (const quote of payload.indices) {
        if (!next[quote.ticker]) next[quote.ticker] = [quote.current_price];
      }
      return next;
    });
  }

  async function loadHealth() {
    const response = await fetch("/health");
    if (!response.ok) throw new Error("Failed to load backend health.");
    setHealth((await response.json()) as HealthResponse);
  }

  async function loadUrgencySettings() {
    const response = await fetch(`/api/urgency-settings/${DEMO_USER_ID}`);
    if (!response.ok) throw new Error("Failed to load urgency settings.");
    const payload = (await response.json()) as StoredUrgencySettings;
    setUrgencySettings(payload.payload);
  }

  async function loadDrafts() {
    const response = await fetch(`/api/trade-plan-drafts/${DEMO_USER_ID}`);
    if (!response.ok) throw new Error("Failed to load trade plan drafts.");
    setSavedDrafts((await response.json()) as StoredTradePlanDraft[]);
  }

  async function loadAlertRules() {
    const response = await fetch(`/api/alert-rules/${DEMO_USER_ID}`);
    if (!response.ok) throw new Error("Failed to load alert rules.");
    setSavedAlertRules((await response.json()) as StoredAlertRule[]);
  }

  async function toggleAlertRuleEnabled(ruleId: string, enabled: boolean) {
    setError(null);
    try {
      const response = await fetch(
        `/api/alert-rules/${DEMO_USER_ID}/${ruleId}?enabled=${enabled}`,
        { method: "PATCH" },
      );
      if (!response.ok) throw new Error("Failed to update alert rule.");
      await loadAlertRules();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update alert rule.");
    }
  }

  async function deleteAlertRule(ruleId: string) {
    setError(null);
    try {
      const response = await fetch(`/api/alert-rules/${DEMO_USER_ID}/${ruleId}`, {
        method: "DELETE",
      });
      if (!response.ok) throw new Error("Failed to delete alert rule.");
      await loadAlertRules();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete alert rule.");
    }
  }

  async function loadTriggeredAlerts(offset = 0) {
    const response = await fetch(
      `/api/triggered-alerts/${DEMO_USER_ID}?limit=${ALERTS_PAGE + 1}&offset=${offset}`,
    );
    if (!response.ok) throw new Error("Failed to load triggered alerts.");
    const payload = (await response.json()) as StoredTriggeredAlert[];
    const hasMore = payload.length > ALERTS_PAGE;
    const page = payload.slice(0, ALERTS_PAGE);
    setTriggeredAlerts((prev) => (offset === 0 ? page : [...prev, ...page]));
    setAlertsOffset(offset);
    setHasMoreAlerts(hasMore);
  }

  async function updateAlertTaskStatus(
    alertId: string,
    status: "pending" | "snoozed" | "dismissed" | "acted",
    snoozedUntil?: string,
  ) {
    try {
      await fetch(`/api/triggered-alerts/${DEMO_USER_ID}/${alertId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ task_status: status, snoozed_until: snoozedUntil ?? null }),
      });
      setTriggeredAlerts((prev) =>
        prev.map((a) =>
          a.payload.alert_id === alertId
            ? {
                ...a,
                payload: {
                  ...a.payload,
                  task_status: status,
                  snoozed_until: snoozedUntil ?? null,
                },
              }
            : a,
        ),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update alert status.");
    }
  }

  async function loadJournalEntries(offset = 0) {
    const response = await fetch(
      `/api/journal-entries/${DEMO_USER_ID}?limit=${JOURNAL_PAGE + 1}&offset=${offset}`,
    );
    if (!response.ok) throw new Error("Failed to load journal entries.");
    const payload = (await response.json()) as StoredJournalEntry[];
    const hasMore = payload.length > JOURNAL_PAGE;
    const page = payload.slice(0, JOURNAL_PAGE);
    setSavedJournalEntries((prev) => (offset === 0 ? page : [...prev, ...page]));
    setJournalOffset(offset);
    setHasMoreJournal(hasMore);
  }

  async function loadTickerNote(ticker: string) {
    const response = await fetch(`/api/ticker-notes/${DEMO_USER_ID}/${ticker}`);
    if (!response.ok) throw new Error("Failed to load ticker notes.");
    const payload = (await response.json()) as StoredTickerNote;
    setTickerNote(payload);
    setEditingNote(payload.payload);
  }

  async function loadThesisOutcomeSummary(ticker: string) {
    const response = await fetch(`/api/thesis-outcome/${DEMO_USER_ID}/${ticker}`);
    if (!response.ok) throw new Error("Failed to load thesis/outcome summary.");
    setThesisOutcomeSummary((await response.json()) as ThesisOutcomeSummary);
  }

  async function loadTickerNotes() {
    const response = await fetch(`/api/ticker-notes/${DEMO_USER_ID}`);
    if (!response.ok) throw new Error("Failed to load ticker notes.");
    setTickerNotes((await response.json()) as StoredTickerNote[]);
  }

  async function loadFocusQueueEntries() {
    const response = await fetch(`/api/focus-queue/${DEMO_USER_ID}`);
    if (!response.ok) throw new Error("Failed to load focus queue.");
    setFocusQueueEntries((await response.json()) as FocusQueueEntryView[]);
  }

  async function loadFocusQueueEntry(ticker: string) {
    const response = await fetch(`/api/focus-queue/${DEMO_USER_ID}/${ticker}`);
    if (!response.ok) throw new Error("Failed to load focus queue entry.");
    const payload = (await response.json()) as FocusQueueEntryView;
    setFocusQueueEntryMeta(payload);
    setEditingFocusEntry(payload.payload);
  }

  async function loadDigest() {
    const response = await fetch(`/api/digest/${DEMO_USER_ID}`);
    if (!response.ok) throw new Error("Failed to load end-of-day digest.");
    setDigest((await response.json()) as EndOfDayDigest);
  }

  async function loadLeaderHoldings() {
    const response = await fetch(`/api/leader-holdings/${DEMO_USER_ID}`);
    if (!response.ok) throw new Error("Failed to load leader holdings.");
    setLeaderHoldings((await response.json()) as StoredLeaderHolding[]);
  }

  async function loadCatalystEvents() {
    const response = await fetch(`/api/catalyst-events/${DEMO_USER_ID}`);
    if (!response.ok) throw new Error("Failed to load catalyst events.");
    setCatalystEvents((await response.json()) as StoredCatalystEvent[]);
  }

  async function loadTrades() {
    const response = await fetch(`/api/trades/${DEMO_USER_ID}`);
    if (!response.ok) throw new Error("Failed to load trades.");
    setTrades((await response.json()) as StoredTrade[]);
  }

  async function loadReviewMetrics() {
    const res = await fetch(`/api/review-metrics/${DEMO_USER_ID}`);
    if (!res.ok) throw new Error("Failed to load review metrics.");
    setReviewMetrics((await res.json()) as ReviewMetrics);
  }

  async function persistTrade(trade: TradeDraft) {
    const response = await fetch("/api/trades", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: DEMO_USER_ID, trade }),
    });
    if (!response.ok) throw new Error("Failed to save trade.");
    await loadTrades();
  }

  async function deleteTrade(tradeId: string) {
    const response = await fetch(`/api/trades/${DEMO_USER_ID}/${tradeId}`, { method: "DELETE" });
    if (!response.ok) throw new Error("Failed to delete trade.");
    await loadTrades();
  }

  async function refresh() {
    setError(null);
    setLoading(true);
    try {
      await Promise.all([
        loadHealth(),
        loadUrgencySettings(),
        loadDashboard(),
        loadOverview(),
        loadDrafts(),
        loadAlertRules(),
        loadTriggeredAlerts(),
        loadJournalEntries(),
        loadTickerNotes(),
        loadFocusQueueEntries(),
        loadLeaderHoldings(),
        loadCatalystEvents(),
        loadTrades(),
        loadDigest(),
        loadReviewMetrics(),
      ]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Dashboard refresh failed.");
    } finally {
      setLoading(false);
    }
  }

  async function addTicker(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!normalizedTickerInput) return;
    if (tickerAlreadyTracked) {
      setError(`${normalizedTickerInput} is already on the watchlist.`);
      return;
    }

    setError(null);
    let validation = tickerValidation;
    if (!validation || validation.ticker !== normalizedTickerInput) {
      setValidatingTicker(true);
      try {
        validation = await fetchTickerValidation(normalizedTickerInput);
        setTickerValidation(validation);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Ticker validation failed.");
        return;
      } finally {
        setValidatingTicker(false);
      }
    }

    if (!validation?.can_add) {
      setError(validation?.message ?? "Ticker validation failed.");
      return;
    }

    const response = await fetch("/api/watchlist", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: DEMO_USER_ID, ticker: normalizedTickerInput }),
    });
    if (!response.ok) {
      setError(await readErrorMessage(response, "Failed to add ticker to watchlist."));
      return;
    }
    setTickerInput("");
    setTickerValidation(null);
    await Promise.all([loadDashboard(), loadFocusQueueEntries()]);
  }

  async function removeTicker(ticker: string) {
    setError(null);
    const response = await fetch(`/api/watchlist/${DEMO_USER_ID}/${ticker}`, {
      method: "DELETE",
    });
    if (!response.ok) {
      setError("Failed to remove ticker from watchlist.");
      return;
    }
    await Promise.all([loadDashboard(), loadFocusQueueEntries()]);
    setSelectedSymbol((current) => {
      if (current !== ticker) return current;
      return stocks.find((item) => item.ticker !== ticker)?.ticker ?? null;
    });
  }

  async function retryBootstrap(ticker: string) {
    setRetryingBootstrap(true);
    setError(null);
    try {
      const response = await fetch(`/api/watchlist/${DEMO_USER_ID}/${ticker}/retry`, {
        method: "POST",
      });
      if (!response.ok) {
        throw new Error(await readErrorMessage(response, "Failed to retry bootstrap."));
      }
      const payload = (await response.json()) as DashboardSnapshot;
      const nextStocks = sortByUrgency(payload.stocks);
      setStocks(nextStocks);
      setSelectedSymbol((current) => current ?? nextStocks[0]?.ticker ?? null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to retry bootstrap.");
    } finally {
      setRetryingBootstrap(false);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  useEffect(() => {
    setSessionView(marketStatus.session);
  }, [marketStatus.session]);

  useEffect(() => {
    if (!normalizedTickerInput) {
      setTickerValidation(null);
      setValidatingTicker(false);
      return;
    }

    if (tickerAlreadyTracked) {
      setTickerValidation({
        ticker: normalizedTickerInput,
        is_valid: true,
        can_add: false,
        feed_status: "unknown",
        source: "watchlist",
        message: `${normalizedTickerInput} is already on the watchlist.`,
      });
      setValidatingTicker(false);
      return;
    }

    let cancelled = false;
    const timer = window.setTimeout(async () => {
      setValidatingTicker(true);
      try {
        const result = await fetchTickerValidation(normalizedTickerInput);
        if (!cancelled) {
          setTickerValidation(result);
        }
      } catch (err) {
        if (!cancelled) {
          setTickerValidation({
            ticker: normalizedTickerInput,
            is_valid: false,
            can_add: false,
            feed_status: "unknown",
            source: "client",
            message: err instanceof Error ? err.message : "Ticker validation failed.",
          });
        }
      } finally {
        if (!cancelled) {
          setValidatingTicker(false);
        }
      }
    }, 350);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [normalizedTickerInput, tickerAlreadyTracked]);

  async function persistDraft() {
    if (!tradePlanDraft) return;
    setSavingDraft(true);
    setError(null);
    try {
      const response = await fetch("/api/trade-plan-drafts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: DEMO_USER_ID, draft: tradePlanDraft }),
      });
      if (!response.ok) throw new Error("Failed to save trade plan draft.");
      await loadDrafts();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save trade plan draft.");
    } finally {
      setSavingDraft(false);
    }
  }

  function validateAlertDraft(draft: AlertRuleDraft): string | null {
    const threshold = parseFloat(draft.threshold);
    if (!draft.threshold.trim() || isNaN(threshold)) {
      return "Threshold must be a valid number (e.g. 2.5 or 450).";
    }
    if (threshold < 0) return "Threshold must be zero or greater.";
    const cooldown = parseFloat(draft.cooldownMinutes);
    if (!draft.cooldownMinutes.trim() || isNaN(cooldown) || cooldown <= 0) {
      return "Cooldown must be a positive number of minutes.";
    }
    return null;
  }

  async function persistAlertRule() {
    if (!alertRuleDraft) return;
    const validationError = validateAlertDraft(alertRuleDraft);
    if (validationError) {
      setAlertValidationError(validationError);
      return;
    }
    setAlertValidationError(null);
    setSavingAlertRule(true);
    setError(null);
    try {
      await saveAlertRuleDraft(DEMO_USER_ID, alertRuleDraft);
      await loadAlertRules();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save alert rule.");
    } finally {
      setSavingAlertRule(false);
    }
  }

  async function createBothAlertsFromDraft(draft: TradePlanDraft) {
    setSavingAlertRule(true);
    setError(null);
    try {
      await saveAlertRuleDraft(DEMO_USER_ID, buildTargetAlertFromTradePlan(draft));
      await saveAlertRuleDraft(DEMO_USER_ID, buildStopAlertFromTradePlan(draft));
      await loadAlertRules();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create target and stop alerts.");
    } finally {
      setSavingAlertRule(false);
    }
  }

  async function persistJournalEntry() {
    if (!journalDraft) return;
    setSavingJournalEntry(true);
    setError(null);
    try {
      const response = await fetch("/api/journal-entries", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: DEMO_USER_ID, entry: journalDraft }),
      });
      if (!response.ok) throw new Error("Failed to save journal entry.");
      await loadJournalEntries();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save journal entry.");
    } finally {
      setSavingJournalEntry(false);
    }
  }

  async function persistTickerNote() {
    if (!editingNote) return;
    setSavingTickerNote(true);
    setError(null);
    try {
      const response = await fetch("/api/ticker-notes", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: DEMO_USER_ID, note: editingNote }),
      });
      if (!response.ok) throw new Error("Failed to save ticker notes.");
      await loadTickerNote(editingNote.ticker);
      await loadTickerNotes();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save ticker notes.");
    } finally {
      setSavingTickerNote(false);
    }
  }

  async function persistFocusQueueEntry() {
    if (!editingFocusEntry) return;
    setSavingFocusQueueEntry(true);
    setError(null);
    try {
      const response = await fetch("/api/focus-queue", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: DEMO_USER_ID, entry: editingFocusEntry }),
      });
      if (!response.ok) throw new Error("Failed to save focus queue entry.");
      await Promise.all([
        loadFocusQueueEntry(editingFocusEntry.ticker),
        loadFocusQueueEntries(),
      ]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save focus queue entry.");
    } finally {
      setSavingFocusQueueEntry(false);
    }
  }

  async function restoreGeneratedFocusQueueEntry(ticker: string) {
    setSavingFocusQueueEntry(true);
    setError(null);
    try {
      const response = await fetch(`/api/focus-queue/${DEMO_USER_ID}/${ticker}`, {
        method: "DELETE",
      });
      if (!response.ok) throw new Error("Failed to restore system suggestion.");
      await Promise.all([
        loadFocusQueueEntry(ticker),
        loadFocusQueueEntries(),
      ]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to restore system suggestion.");
    } finally {
      setSavingFocusQueueEntry(false);
    }
  }

  async function persistLeaderHolding() {
    if (!editingLeaderHolding.ticker.trim()) {
      setError("Leader holding ticker is required.");
      return;
    }
    setSavingLeaderHolding(true);
    setError(null);
    try {
      const response = await fetch("/api/leader-holdings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: DEMO_USER_ID, holding: editingLeaderHolding }),
      });
      if (!response.ok) throw new Error("Failed to save leader holding.");
      await loadLeaderHoldings();
      setEditingLeaderHolding(buildEmptyLeaderHolding());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save leader holding.");
    } finally {
      setSavingLeaderHolding(false);
    }
  }

  async function deleteLeaderHolding(ticker: string) {
    setError(null);
    try {
      const response = await fetch(`/api/leader-holdings/${DEMO_USER_ID}/${ticker}`, {
        method: "DELETE",
      });
      if (!response.ok) throw new Error("Failed to delete leader holding.");
      await loadLeaderHoldings();
      if (editingLeaderHolding.ticker === ticker) {
        setEditingLeaderHolding(buildEmptyLeaderHolding());
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete leader holding.");
    }
  }

  async function persistCatalystEvent() {
    if (!editingCatalystEvent.headline.trim()) {
      setError("Catalyst headline is required.");
      return;
    }
    if (editingCatalystEvent.scope === "ticker" && !editingCatalystEvent.ticker.trim()) {
      setError("Ticker catalysts require a ticker.");
      return;
    }
    setSavingCatalystEvent(true);
    setError(null);
    try {
      const response = await fetch("/api/catalyst-events", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: DEMO_USER_ID, event: editingCatalystEvent }),
      });
      if (!response.ok) throw new Error("Failed to save catalyst event.");
      await loadCatalystEvents();
      setEditingCatalystEvent(buildEmptyCatalystEvent());
      setCatalystTagsInput("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save catalyst event.");
    } finally {
      setSavingCatalystEvent(false);
    }
  }

  async function deleteCatalystEvent(eventId: string) {
    setError(null);
    try {
      const response = await fetch(`/api/catalyst-events/${DEMO_USER_ID}/${eventId}`, {
        method: "DELETE",
      });
      if (!response.ok) throw new Error("Failed to delete catalyst event.");
      await loadCatalystEvents();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete catalyst event.");
    }
  }

  async function persistUrgencySettings() {
    setSavingUrgencySettings(true);
    setError(null);
    try {
      const response = await fetch("/api/urgency-settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: DEMO_USER_ID, settings: urgencySettings }),
      });
      if (!response.ok) throw new Error("Failed to save urgency settings.");
      await refresh();
      setShowUrgencySettings(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save urgency settings.");
    } finally {
      setSavingUrgencySettings(false);
    }
  }

  async function sendDigest() {
    setSendingDigest(true);
    setError(null);
    try {
      const response = await fetch(`/api/digest/${DEMO_USER_ID}/send?channel=discord`, {
        method: "POST",
      });
      if (!response.ok) throw new Error("Failed to send end-of-day digest.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to send end-of-day digest.");
    } finally {
      setSendingDigest(false);
    }
  }

  function savePreset(name: string, view: "board" | "trades") {
    const preset: SavedFilterPreset = {
      id: crypto.randomUUID(),
      name,
      view,
      ...(view === "board" ? { boardFilters } : { tradeFilters }),
    };
    setSavedPresets([...savedPresets, preset]);
  }

  function deletePreset(id: string) {
    setSavedPresets(savedPresets.filter((p) => p.id !== id));
  }

  function applyPreset(preset: SavedFilterPreset) {
    if (preset.view === "board" && preset.boardFilters) setBoardFilters(preset.boardFilters);
    if (preset.view === "trades" && preset.tradeFilters) setTradeFilters(preset.tradeFilters);
    setActiveView(preset.view);
  }

  useEffect(() => {
    let destroyed = false;
    let retryDelay = 1_000;
    let socket: WebSocket | null = null;

    function connect() {
      if (destroyed) return;
      const protocol = window.location.protocol === "https:" ? "wss" : "ws";
      socket = new WebSocket(`${protocol}://${window.location.host}/ws/dashboard`);

      socket.onopen = () => {
        setConnected(true);
        retryDelay = 1_000;
      };

      socket.onclose = () => {
        setConnected(false);
        if (!destroyed) {
          setTimeout(connect, retryDelay);
          retryDelay = Math.min(retryDelay * 2, 30_000);
        }
      };

      socket.onerror = () => { socket?.close(); };

      socket.onmessage = (message) => {
        const payload = JSON.parse(message.data) as MarketEvent;
        if (payload.type !== "price_update") return;

        if (OVERVIEW_TICKERS.has(payload.ticker)) {
          setIndices((current) =>
            current.map((quote) =>
              quote.ticker === payload.ticker
                ? { ...quote, current_price: payload.current_price, change_pct: payload.change_pct }
                : quote,
            ),
          );
          setIndexHistory((prev) => ({
            ...prev,
            [payload.ticker]: [...(prev[payload.ticker] ?? []), payload.current_price].slice(-24),
          }));
          return;
        }

        setStocks((current) =>
          sortByUrgency(
            current.map((stock) => {
              if (stock.ticker !== payload.ticker) return stock;
              const history = [...stock.history, payload.current_price].slice(-24);
              return {
                ...stock,
                current_price: payload.current_price,
                change_pct: payload.change_pct,
                volume: payload.volume,
                last_updated: payload.as_of,
                data_status: "live",
                data_status_message: `Live stream via ${stock.data_feed ?? "market feed"}.`,
                history,
                urgency_score: computeUrgency(urgencySettings, payload.change_pct, stock.sentiment_score),
              };
            }),
          ),
        );
      };
    }

    connect();
    return () => { destroyed = true; socket?.close(); };
  }, []);

  const overviewSelections = indices.map((quote) =>
    buildOverviewPreview(urgencySettings, quote, indexHistory[quote.ticker] ?? [quote.current_price]),
  );
  const selected =
    [...stocks, ...overviewSelections].find((stock) => stock.ticker === selectedSymbol) ??
    overviewSelections.find((stock) => stock.ticker === selectedSymbol) ??
    stocks[0] ??
    overviewSelections[0] ??
    null;
  const selectedTrackedStock =
    stocks.find((stock) => stock.ticker === selectedSymbol) ??
    stocks[0] ??
    null;
  const activeTrackedTicker = selectedTrackedStock?.ticker ?? null;
  const selectedNoteSummary =
    (activeTrackedTicker
      ? tickerNotes.find((note) => note.ticker === activeTrackedTicker)
      : null) ?? tickerNote;
  const selectedAlertGroup =
    activeTrackedTicker != null
      ? groupedAlerts.find((group) => group.ticker === activeTrackedTicker) ?? null
      : null;
  const selectedTriggeredAlerts =
    activeTrackedTicker != null
      ? triggeredAlerts.filter((alert) => alert.ticker === activeTrackedTicker).slice(0, 3)
      : [];
  const selectedJournalPreview =
    activeTrackedTicker != null
      ? savedJournalEntries.filter((entry) => entry.ticker === activeTrackedTicker).slice(0, 2)
      : [];
  const selectedLeaderHolding =
    activeTrackedTicker != null
      ? leaderHoldings.find((holding) => holding.ticker === activeTrackedTicker) ?? null
      : null;
  const overlapLeaderHoldings = leaderHoldings.filter((holding) =>
    stocks.some((stock) => stock.ticker === holding.ticker),
  );
  const selectedTickerCatalysts =
    activeTrackedTicker != null
      ? catalystEvents.filter(
          (event) => event.payload.scope === "ticker" && event.ticker === activeTrackedTicker,
        )
      : [];
  const macroCatalysts = catalystEvents.filter((event) => event.payload.scope === "macro");
  const watchlistCatalysts = catalystEvents.filter(
    (event) => event.payload.scope === "ticker" && stocks.some((stock) => stock.ticker === event.ticker),
  );
  const todayStr = getTodayStr();
  const weekEndStr = getWeekEndStr();
  const todayCatalysts = catalystEvents.filter(
    (e) => e.payload.eventDate === todayStr,
  );
  const thisWeekCatalysts = catalystEvents.filter(
    (e) => e.payload.eventDate >= todayStr && e.payload.eventDate <= weekEndStr,
  );
  const byTickerMap = catalystEvents.reduce<Record<string, StoredCatalystEvent[]>>((acc, event) => {
    const key = event.payload.scope === "macro" ? "__macro__" : event.ticker || "__macro__";
    if (!acc[key]) acc[key] = [];
    acc[key].push(event);
    return acc;
  }, {});
  const selectedStrategyTag = selectedNoteSummary?.payload.strategyTag.trim() || "Unsorted";
  const topUrgencyStocks = stocks.slice(0, 6);
  const liveCount = stocks.filter((stock) => stock.data_status === "live").length;
  const delayedCount = stocks.filter((stock) => stock.data_status === "delayed").length;
  const waitingCount = stocks.filter((stock) => stock.data_status === "waiting").length;
  const taggedCount = tickerNotes.filter((note) => note.payload.strategyTag.trim()).length;
  const selectedStatusLabel = selected
    ? selected.data_status === "live"
      ? "Live"
      : selected.data_status === "delayed"
        ? "Delayed"
        : "Waiting"
    : "Idle";
  const providerLabel = health?.provider?.toUpperCase() ?? "UNKNOWN";
  const feedLabel = health?.feed?.toUpperCase() ?? "N/A";
  const sessionFilteredStocks =
    sessionView === "pre-market"
      ? stocks.filter((stock) => stock.data_status !== "live" || tickerNotes.some((note) => note.ticker === stock.ticker))
      : sessionView === "close"
        ? [...stocks].sort((left, right) => left.ticker.localeCompare(right.ticker))
        : stocks;

  function stockHasCatalyst(ticker: string): boolean {
    const today = new Date();
    const limit = new Date(today);
    limit.setDate(limit.getDate() + 7);
    return catalystEvents.some((e) => {
      if (e.payload.scope !== "ticker" || e.ticker !== ticker) return false;
      const d = new Date(e.payload.eventDate);
      return d >= today && d <= limit;
    });
  }

  const filteredStocks: StockCard[] = sessionFilteredStocks.filter((stock) => {
    if (boardFilters.status !== "all" && stock.data_status !== boardFilters.status) return false;
    if (boardFilters.minUrgency === "watch" && stock.urgency_score < urgencySettings.lowThreshold) return false;
    if (boardFilters.minUrgency === "hot" && stock.urgency_score < urgencySettings.highThreshold) return false;
    if (boardFilters.hasCatalyst && !stockHasCatalyst(stock.ticker)) return false;
    return true;
  });

  const filteredTrades: StoredTrade[] = trades.filter((t) => {
    if (tradeFilters.setupType !== "all" && t.payload.setupType !== tradeFilters.setupType) return false;
    if (tradeFilters.stage !== "all" && t.payload.stage !== tradeFilters.stage) return false;
    if (tradeFilters.outcomeTag !== "all" && t.payload.outcomeTag !== tradeFilters.outcomeTag) return false;
    return true;
  });

  const strategyGroups = groupStocksByStrategy(filteredStocks, tickerNotes);
  const sessionSummary = buildSessionSummary(sessionView, stocks, tickerNotes);
  const dailySummary = buildDailySummary(
    sessionView,
    indices,
    stocks,
    triggeredAlerts,
    tickerNotes,
  );
  const focusQueueGroups: Array<{ bucket: FocusQueueBucket; entries: FocusQueueEntryView[] }> = (
    ["today_focus", "monitor", "ignore"] as FocusQueueBucket[]
  ).map((bucket) => ({
    bucket,
    entries: focusQueueEntries.filter((entry) => entry.payload.bucket === bucket),
  }));
  const viewContext =
    activeView === "overview"
      ? {
          title: "Market context at a glance",
          body: `${indices.length} index cards and ${dailySummary.length} session metrics are grouped into one screen.`,
        }
      : activeView === "board"
        ? {
            title: "Urgency-ranked watchlist board",
            body: `${stocks.length} tracked symbols · ${liveCount} live · ${waitingCount} waiting.`,
          }
        : activeView === "leader"
          ? {
              title: "Leader holdings overlay",
              body: `${leaderHoldings.length} tracked leader positions · ${overlapLeaderHoldings.length} overlap with your board.`,
            }
          : activeView === "catalysts"
            ? {
                title: "Catalyst and calendar context",
                body: `${catalystEvents.length} saved catalyst events · ${macroCatalysts.length} macro · ${watchlistCatalysts.length} tied to your watchlist.`,
              }
          : {
            title: "Selected ticker workspace",
            body: activeTrackedTicker
              ? `${activeTrackedTicker} with ${selectedAlertGroup?.rules.length ?? 0} saved alerts and ${taggedCount} tagged setups across the board.`
              : "Select a tracked ticker to open notes, alerts, and journal context.",
          };
  const sessionTabs = (
    <div className="session-tabs compact-session-tabs">
      {SESSION_OPTIONS.map((option) => (
        <button
          key={option.id}
          className={`session-pill ${sessionView === option.id ? "selected" : ""}`}
          onClick={() => setSessionView(option.id)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
  const urgencyLegend = (
    <div className="legend-row compact-legend">
      <span className="legend-item">
        <span className="legend-swatch low" />
        Low urgency
      </span>
      <span className="legend-item">
        <span className="legend-swatch medium" />
        Medium urgency
      </span>
      <span className="legend-item">
        <span className="legend-swatch high" />
        High urgency
      </span>
    </div>
  );

  useEffect(() => {
    if (activeView === "overview" || selectedTrackedStock == null || selectedTrackedStock.data_status === "live") {
      return;
    }

    const timer = window.setTimeout(() => {
      void retryBootstrap(selectedTrackedStock.ticker);
    }, selectedTrackedStock.data_status === "waiting" ? 15000 : 30000);

    return () => window.clearTimeout(timer);
  }, [activeView, selectedTrackedStock?.ticker, selectedTrackedStock?.data_status]);

  useEffect(() => {
    if (activeView !== "overview" && stocks.length > 0 && !stocks.some((stock) => stock.ticker === selectedSymbol)) {
      setSelectedSymbol(stocks[0].ticker);
    }
  }, [activeView, stocks, selectedSymbol]);

  useEffect(() => {
    if (!selectedTrackedStock) {
      setTickerNote(null);
      setEditingNote(null);
      setFocusQueueEntryMeta(null);
      setEditingFocusEntry(null);
      setThesisOutcomeSummary(null);
      return;
    }

    let cancelled = false;
    void (async () => {
      try {
        const [noteResponse, summaryResponse, focusQueueResponse] = await Promise.all([
          fetch(`/api/ticker-notes/${DEMO_USER_ID}/${selectedTrackedStock.ticker}`),
          fetch(`/api/thesis-outcome/${DEMO_USER_ID}/${selectedTrackedStock.ticker}`),
          fetch(`/api/focus-queue/${DEMO_USER_ID}/${selectedTrackedStock.ticker}`),
        ]);
        if (!noteResponse.ok) throw new Error("Failed to load ticker notes.");
        if (!summaryResponse.ok) throw new Error("Failed to load thesis/outcome summary.");
        if (!focusQueueResponse.ok) throw new Error("Failed to load focus queue entry.");
        const notePayload = (await noteResponse.json()) as StoredTickerNote;
        const summaryPayload = (await summaryResponse.json()) as ThesisOutcomeSummary;
        const focusQueuePayload = (await focusQueueResponse.json()) as FocusQueueEntryView;
        if (!cancelled) {
          setTickerNote(notePayload);
          setEditingNote(notePayload.payload);
          setFocusQueueEntryMeta(focusQueuePayload);
          setEditingFocusEntry(focusQueuePayload.payload);
          setThesisOutcomeSummary(summaryPayload);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load ticker detail summary.");
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [selectedTrackedStock?.ticker]);

  return (
    <div className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Event-Driven Portfolio Monitor</p>
          <h1>Market Sentinel Dashboard</h1>
          <p className="subtitle">
            Real-time watchlist with urgency-ranked alerts, integrated trade plans, and a journaling loop.
          </p>
        </div>
        <div className="status-cluster">
          <span className={`status-pill ${marketStatus.isOpen ? "market-open" : "market-closed"}`}>
            <span className="status-dot" />
            Market {marketStatus.label}
          </span>
          <span className={`status-pill ${connected ? "online" : "offline"}`}>
            <span className="status-dot" />
            {connected ? "WebSocket live" : "Reconnecting"}
          </span>
        </div>
      </header>

      <section className="toolbar">
        <div className="watchlist-input-group">
          <form className="watchlist-form" onSubmit={addTicker}>
            <input
              value={tickerInput}
              onChange={(event) => setTickerInput(event.target.value.toUpperCase())}
              placeholder="Add ticker, e.g. AMZN"
              maxLength={10}
            />
            <button
              type="submit"
              disabled={validatingTicker || tickerAlreadyTracked || tickerValidation?.can_add === false}
            >
              {validatingTicker ? "Checking…" : "Add"}
            </button>
          </form>
          {normalizedTickerInput ? (
            <p
              className={`watchlist-validation ${
                validatingTicker ? "checking" : tickerValidation?.can_add ? "ok" : "error"
              }`}
            >
              {validatingTicker ? "Checking ticker…" : tickerValidation?.message ?? "Checking ticker…"}
            </p>
          ) : (
            <p className="toolbar-note">
              Add an active US equity ticker such as AMZN, NFLX, AMD, or SHOP.
            </p>
          )}
        </div>
        <button className="refresh-button" onClick={refresh} disabled={loading}>
          {loading ? "Refreshing…" : "Refresh"}
        </button>
        <button className="ghost-button" onClick={() => setShowUrgencySettings(true)}>
          Urgency Settings
        </button>
      </section>

      {error ? <div className="error-banner">{error}</div> : null}
      <section className="source-strip">
        <div className="source-card">
          <span className="source-label">Provider</span>
          <strong>{providerLabel}</strong>
          <small>Backend market-data provider</small>
        </div>
        <div className="source-card">
          <span className="source-label">Feed</span>
          <strong>{feedLabel}</strong>
          <small>Configured stream / bootstrap feed</small>
        </div>
        <div className="source-card">
          <span className="source-label">Selection</span>
          <strong>{selected ? `${selected.ticker} · ${selectedStatusLabel}` : "No symbol selected"}</strong>
          <small>{selected?.data_status_message ?? "Select a symbol to inspect its data source state."}</small>
        </div>
      </section>

      <section className="view-strip">
        <div className="view-tabs">
          {VIEW_OPTIONS.map((option) => (
            <button
              key={option.id}
              className={`view-pill ${activeView === option.id ? "selected" : ""}`}
              onClick={() => setActiveView(option.id)}
            >
              {option.label}
            </button>
          ))}
        </div>
        <div className="view-summary">
          <strong>{viewContext.title}</strong>
          <span>{viewContext.body}</span>
        </div>
      </section>

      <main className="dashboard-stage">
        {activeView === "overview" ? (
          <section className="tab-panel overview-panel">
            <div className="tab-panel-header">
              <div>
                <p className="eyebrow">Session Lens</p>
                <h2>Market overview</h2>
              </div>
              {sessionTabs}
            </div>

            <div className="overview-layout">
              <div className="overview-main">
                <section className="session-strip panel-card">
                  <div className="session-summary">
                    <strong>{sessionSummary.title}</strong>
                    <span>{sessionSummary.body}</span>
                  </div>
                  <div className="summary-grid">
                    {dailySummary.map((item) => (
                      <article key={item.label} className="summary-card">
                        <span className="summary-label">{item.label}</span>
                        <strong>{item.value}</strong>
                        <small>{item.detail}</small>
                      </article>
                    ))}
                  </div>
                </section>

                <section className="overview-grid">
                  {indices.map((quote) => (
                    <article
                      key={quote.ticker}
                      className={`overview-card interactive ${selectedSymbol === quote.ticker ? "selected" : ""}`}
                      onClick={() => setSelectedSymbol(quote.ticker)}
                    >
                      <span className="overview-label">{quote.ticker}</span>
                      <strong>{formatCurrency(quote.current_price)}</strong>
                      <span className={quote.change_pct >= 0 ? "change-up" : "change-down"}>
                        {quote.change_pct >= 0 ? "+" : ""}
                        {quote.change_pct.toFixed(2)}%
                      </span>
                      <small>{quote.label}</small>
                    </article>
                  ))}
                </section>

                <section className="snapshot-grid">
                  <article className="snapshot-card">
                    <span className="summary-label">Tracked Symbols</span>
                    <strong>{stocks.length}</strong>
                    <small>{liveCount} live · {delayedCount} delayed · {waitingCount} waiting</small>
                  </article>
                  <article className="snapshot-card">
                    <span className="summary-label">Strategy Tags</span>
                    <strong>{taggedCount}</strong>
                    <small>Tagged setups captured in ticker notes</small>
                  </article>
                  <article className="snapshot-card">
                    <span className="summary-label">Recent Alert Pressure</span>
                    <strong>{triggeredAlerts.length}</strong>
                    <small>Loaded triggered alerts in this workspace</small>
                  </article>
                </section>
              </div>

              <aside className="overview-side panel-card">
                <div className="compact-card-header">
                  <div>
                    <p className="eyebrow">Focus Name</p>
                    <h3>{selected?.ticker ?? "No symbol selected"}</h3>
                  </div>
                  {selected ? (
                    <span className={`status-pill neutral detail-status-inline ${selected.data_status}`}>
                      {selectedStatusLabel}
                    </span>
                  ) : null}
                </div>
                {selected ? (
                  <>
                    <p className="detail-name">{selected.display_name}</p>
                    <div className="focus-price-row">
                      <strong>{hasUsablePrice(selected) ? formatCurrency(selected.current_price) : "Waiting…"}</strong>
                      <span
                        className={
                          hasUsablePrice(selected)
                            ? selected.change_pct != null && selected.change_pct >= 0
                              ? "change-up"
                              : "change-down"
                            : "change-pending"
                        }
                      >
                        {hasUsablePrice(selected) ? formatChangePct(selected.change_pct) : "Pending"}
                      </span>
                    </div>
                    <div className="detail-chart compact-detail-chart">
                      <Sparkline points={selected.history} />
                    </div>
                    <div className="detail-metrics compact-detail-metrics">
                      <div>
                        <span>Sentiment</span>
                        <strong>{selected.sentiment_label}</strong>
                      </div>
                      <div>
                        <span>Urgency</span>
                        <strong>{hasUsablePrice(selected) ? selected.urgency_score.toFixed(0) : "Pending"}</strong>
                      </div>
                    </div>
                    {hasUsablePrice(selected) ? <UrgencyBar score={selected.urgency_score} /> : null}
                    <div className="card-actions compact-actions">
                      <button className="ghost-button" onClick={() => setShowChart(true)} disabled={selected.history.length === 0}>
                        Open Chart
                      </button>
                      {!OVERVIEW_TICKERS.has(selected.ticker) ? (
                        <button className="ghost-button" onClick={() => setActiveView("workspace")}>
                          Open Workspace
                        </button>
                      ) : (
                        <button className="ghost-button" onClick={() => setActiveView("board")}>
                          Open Watchlist
                        </button>
                      )}
                    </div>
                  </>
                ) : (
                  <p className="draft-empty-state">No selection available.</p>
                )}
              </aside>
            </div>

            {sessionView === "close" && digest ? (
              <section className="digest-card panel-card">
                <div className="digest-header">
                  <div>
                    <span className="summary-label">{digest.headline}</span>
                    <strong>{new Date(digest.generated_at).toLocaleString()}</strong>
                  </div>
                  <div className="inline-action-row">
                    <button className="ghost-button" onClick={() => void loadDigest()}>
                      Refresh Digest
                    </button>
                    <button className="refresh-button" onClick={() => void sendDigest()} disabled={sendingDigest}>
                      {sendingDigest ? "Sending..." : "Send to Discord"}
                    </button>
                  </div>
                </div>
                <p className="digest-summary">{digest.summary}</p>
                <div className="summary-grid">
                  {digest.metrics.map((item) => (
                    <article key={item.label} className="summary-card">
                      <span className="summary-label">{item.label}</span>
                      <strong>{item.value}</strong>
                      <small>{item.detail}</small>
                    </article>
                  ))}
                </div>
              </section>
            ) : null}
          </section>
        ) : null}

        {activeView === "board" ? (
          <section className="tab-panel board-panel">
            <div className="tab-panel-header">
              <div>
                <p className="eyebrow">Execution Board</p>
                <h2>Watchlist</h2>
              </div>
              {sessionTabs}
            </div>
            <FilterStrip
              view="board"
              boardFilters={boardFilters}
              onBoardFilters={setBoardFilters}
              presets={savedPresets.filter((p) => p.view === "board")}
              onSavePreset={(name) => savePreset(name, "board")}
              onDeletePreset={deletePreset}
              onApplyPreset={applyPreset}
              filteredCount={filteredStocks.length}
              totalCount={sessionFilteredStocks.length}
            />

            <div className="board-layout">
              <div className="board-side panel-card">
                <div className="compact-card-header">
                  <div>
                    <p className="eyebrow">Board Summary</p>
                    <h3>{sessionSummary.title}</h3>
                  </div>
                </div>
                <p className="detail-meta">{sessionSummary.body}</p>
                {urgencyLegend}
                <div className="saved-drafts-list board-summary-list">
                  {topUrgencyStocks.map((stock) => (
                    <button
                      key={`top-${stock.ticker}`}
                      className={`saved-draft-item board-summary-item ${activeTrackedTicker === stock.ticker ? "selected-list-item" : ""}`}
                      onClick={() => setSelectedSymbol(stock.ticker)}
                    >
                      <div className="triggered-alert-header">
                        <strong>{stock.ticker}</strong>
                        <span className={`urgency-badge urgency-${stock.urgency_score >= 70 ? "high" : stock.urgency_score >= 40 ? "med" : "low"}`}>
                          {stock.urgency_score.toFixed(0)}
                        </span>
                      </div>
                      <span>{stock.display_name}</span>
                    </button>
                  ))}
                </div>
                <div className="saved-drafts-panel">
                  <p className="eyebrow">Catalyst Context</p>
                  {watchlistCatalysts.length === 0 ? (
                    <p className="draft-empty-state">No watchlist catalysts saved yet.</p>
                  ) : (
                    <div className="saved-drafts-list">
                      {watchlistCatalysts.slice(0, 4).map((event) => (
                        <button
                          key={`watchlist-catalyst-${event.event_id}`}
                          className="saved-draft-item board-summary-item"
                          onClick={() => setActiveView("catalysts")}
                        >
                          <div className="triggered-alert-header">
                            <strong>{event.ticker || "Macro"}</strong>
                            <span className="triggered-alert-badge">{event.payload.eventType}</span>
                          </div>
                          <span>{event.payload.headline}</span>
                          <span>{event.payload.eventDate || "No date"} · {event.payload.timeLabel || "No time"}</span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
                <div className="saved-drafts-panel">
                  <p className="eyebrow">Leader Overlap</p>
                  {overlapLeaderHoldings.length === 0 ? (
                    <p className="draft-empty-state">No leader positions overlap with your watchlist yet.</p>
                  ) : (
                    <div className="saved-drafts-list">
                      {overlapLeaderHoldings.slice(0, 4).map((holding) => (
                        <button
                          key={`leader-overlap-${holding.ticker}`}
                          className="saved-draft-item board-summary-item"
                          onClick={() => {
                            setSelectedSymbol(holding.ticker);
                            setActiveView("leader");
                          }}
                        >
                          <div className="triggered-alert-header">
                            <strong>{holding.ticker}</strong>
                            <span className="triggered-alert-badge">{holding.payload.positionStatus}</span>
                          </div>
                          <span>
                            {holding.payload.conviction} conviction · {holding.payload.timeHorizon} horizon
                          </span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              <div className="board-main">
                <section className="focus-board-grid">
                  {focusQueueGroups.map((group) => (
                    <article key={group.bucket} className="focus-column panel-card">
                      <div className="compact-card-header">
                        <div>
                          <p className="eyebrow">Focus Queue</p>
                          <h3>{focusBucketLabel(group.bucket)}</h3>
                        </div>
                        <span className="strategy-count">{group.entries.length}</span>
                      </div>
                      <p className="detail-meta">{focusBucketDescription(group.bucket)}</p>
                      <div className="focus-entry-list">
                        {group.entries.length === 0 ? (
                          <p className="draft-empty-state">No symbols currently assigned.</p>
                        ) : (
                          group.entries.map((entry) => (
                            <button
                              key={`focus-${group.bucket}-${entry.ticker}`}
                              className={`saved-draft-item focus-entry-card ${activeTrackedTicker === entry.ticker ? "selected-list-item" : ""}`}
                              onClick={() => {
                                setSelectedSymbol(entry.ticker);
                                setActiveView("workspace");
                              }}
                            >
                              <div className="triggered-alert-header">
                                <strong>{entry.ticker}</strong>
                                <div className="focus-badge-group">
                                  {entry.generated_payload.catalystTag && (
                                    <span className="catalyst-boost-badge">
                                      {entry.generated_payload.catalystTag.split(";")[0].trim().split(" · ")[0]}
                                    </span>
                                  )}
                                  <span className={`focus-source-badge ${entry.source}`}>
                                    {entry.source === "saved" ? "Edited" : "Auto"}
                                  </span>
                                </div>
                              </div>
                              <span>{entry.payload.whyOnList}</span>
                              <span className="focus-helper-line">
                                Trigger: {entry.payload.triggerCondition}
                              </span>
                            </button>
                          ))
                        )}
                      </div>
                    </article>
                  ))}
                </section>

                <div className="card-grid board-card-grid">
                  {strategyGroups.map((group) => (
                    <section key={group.name} className="strategy-group">
                      <div className="strategy-group-header">
                        <div>
                          <p className="eyebrow">Strategy Group</p>
                          <h3>{group.name}</h3>
                        </div>
                        <span className="strategy-count">{group.stocks.length} symbols</span>
                      </div>
                      <div className="strategy-group-grid">
                        {group.stocks.map((stock) => (
                          <article
                            key={stock.ticker}
                            className={`stock-card ${activeTrackedTicker === stock.ticker ? "selected" : ""} ${
                              stock.data_status === "waiting"
                                ? "waiting"
                                : stock.data_status === "delayed"
                                  ? "delayed"
                                  : ""
                            }`}
                            onClick={() => setSelectedSymbol(stock.ticker)}
                          >
                            <div className="card-header">
                              <div>
                                <span className="ticker">{stock.ticker}</span>
                                <p>{stock.display_name}</p>
                              </div>
                              <button
                                className="remove-button"
                                onClick={(event) => {
                                  event.stopPropagation();
                                  void removeTicker(stock.ticker);
                                }}
                              >
                                Remove
                              </button>
                            </div>

                            <div className="card-price-row">
                              <strong className={stock.data_status === "waiting" ? "pending-price" : ""}>
                                {stock.data_status === "waiting" && !hasUsablePrice(stock)
                                  ? "Waiting for data"
                                  : formatCurrency(stock.current_price)}
                              </strong>
                              <span
                                className={
                                  stock.data_status === "live"
                                    ? stock.change_pct != null && stock.change_pct >= 0
                                      ? "change-up"
                                      : "change-down"
                                    : stock.data_status === "delayed"
                                      ? "change-delayed"
                                      : "change-pending"
                                }
                              >
                                {stock.data_status === "live" || stock.data_status === "delayed"
                                  ? formatChangePct(stock.change_pct)
                                  : "Subscribed"}
                              </span>
                            </div>

                            <div className="badge-row">
                              {stock.data_status === "live" || stock.data_status === "delayed" ? (
                                <>
                                  <span className="sentiment-badge">{stock.sentiment_label}</span>
                                  <span
                                    className={`urgency-badge urgency-${stock.urgency_score >= 70 ? "high" : stock.urgency_score >= 40 ? "med" : "low"}`}
                                  >
                                    {stock.urgency_score.toFixed(0)}
                                  </span>
                                </>
                              ) : (
                                <span className="data-status-badge waiting">Waiting for market data</span>
                              )}
                              {stock.data_status === "delayed" ? (
                                <span className="data-status-badge delayed">Delayed / limited feed</span>
                              ) : null}
                            </div>

                            {stock.data_status !== "waiting" ? <UrgencyBar score={stock.urgency_score} /> : null}

                            {stock.volume > 0 && (
                              <div className="vol-row">
                                <span className="vol-label">Vol</span>
                                <span className="vol-value">{formatVolume(stock.volume)}</span>
                              </div>
                            )}

                            <div className="freshness-row">
                              {(() => {
                                const freshness = getFreshnessLabel(stock.last_updated, stock.data_status);
                                return (
                                  <span className={`freshness-pill ${freshness.stale ? "stale" : "fresh"}`}>
                                    {freshness.label}
                                  </span>
                                );
                              })()}
                            </div>
                            {stock.data_status_message ? (
                              <div className="data-status-copy">{stock.data_status_message}</div>
                            ) : null}

                            <div className="mini-chart">
                              <Sparkline points={stock.history} />
                            </div>

                            <div className="card-actions">
                              <button
                                className="ghost-button"
                                disabled={stock.history.length === 0}
                                onClick={(event) => {
                                  event.stopPropagation();
                                  setSelectedSymbol(stock.ticker);
                                  setShowChart(true);
                                }}
                              >
                                Open Chart
                              </button>
                              <button
                                className="ghost-button"
                                disabled={!hasUsablePrice(stock)}
                                onClick={(event) => {
                                  event.stopPropagation();
                                  setSelectedSymbol(stock.ticker);
                                  setTradePlanDraft(buildTradePlanDraft(stock));
                                }}
                              >
                                Seed Trade Plan
                              </button>
                              <button
                                className="ghost-button"
                                disabled={!hasUsablePrice(stock)}
                                onClick={(event) => {
                                  event.stopPropagation();
                                  setSelectedSymbol(stock.ticker);
                                  setAlertRuleDraft(buildAlertRuleDraft(stock));
                                }}
                              >
                                Create Alert
                              </button>
                            </div>
                          </article>
                        ))}
                      </div>
                    </section>
                  ))}
                </div>
              </div>
            </div>
          </section>
        ) : null}

        {activeView === "workspace" ? (
          <section className="tab-panel workspace-panel">
            <div className="tab-panel-header">
              <div>
                <p className="eyebrow">Ticker Workspace</p>
                <h2>{selectedTrackedStock?.ticker ?? "Select a tracked ticker"}</h2>
              </div>
              <div className="workspace-controls">
                {sessionTabs}
                <button
                  className="ghost-button"
                  onClick={() => selectedTrackedStock && setShowChart(true)}
                  disabled={!selectedTrackedStock || selectedTrackedStock.history.length === 0}
                >
                  Open Chart
                </button>
              </div>
            </div>

            <div className="workspace-layout">
              <aside className="workspace-side panel-card">
                <div className="compact-card-header">
                  <div>
                    <p className="eyebrow">Tracked Names</p>
                    <h3>{stocks.length} symbols</h3>
                  </div>
                  <span className="strategy-count">{taggedCount} tagged</span>
                </div>
                <div className="workspace-stock-list">
                  {stocks.map((stock) => (
                    <button
                      key={`workspace-${stock.ticker}`}
                      className={`workspace-stock-item ${activeTrackedTicker === stock.ticker ? "selected-list-item" : ""}`}
                      onClick={() => setSelectedSymbol(stock.ticker)}
                    >
                      <div className="triggered-alert-header">
                        <strong>{stock.ticker}</strong>
                        <span className={`freshness-pill ${stock.data_status === "live" ? "fresh" : "stale"}`}>
                          {stock.data_status}
                        </span>
                      </div>
                      <span>{stock.display_name}</span>
                      <span>
                        {hasUsablePrice(stock) ? formatCurrency(stock.current_price) : "Waiting for data"} ·{" "}
                        {stock.sentiment_label}
                      </span>
                    </button>
                  ))}
                </div>
              </aside>

              <div className="workspace-main">
                <div className="workspace-summary-grid">
                  <article className="snapshot-card">
                    <span className="summary-label">Strategy</span>
                    <strong>{selectedTrackedStock ? selectedStrategyTag : "No selection"}</strong>
                    <small>{selectedTrackedStock?.display_name ?? "Choose a ticker from the list"}</small>
                  </article>
                  <article className="snapshot-card">
                    <span className="summary-label">Saved Alerts</span>
                    <strong>{selectedAlertGroup?.rules.length ?? 0}</strong>
                    <small>{selectedTrackedStock ? "Rules attached to this ticker" : "Select a ticker to inspect rules"}</small>
                  </article>
                  <article className="snapshot-card">
                    <span className="summary-label">Journal Entries</span>
                    <strong>{selectedJournalPreview.length}</strong>
                    <small>Recent journal items loaded for this ticker</small>
                  </article>
                  <article className="snapshot-card">
                    <span className="summary-label">Leader Overlay</span>
                    <strong>{selectedLeaderHolding ? selectedLeaderHolding.payload.positionStatus : "No overlap"}</strong>
                    <small>
                      {selectedLeaderHolding
                        ? `${selectedLeaderHolding.payload.conviction} conviction · ${selectedLeaderHolding.payload.timeHorizon} horizon`
                        : "No saved leader holding for this ticker"}
                    </small>
                  </article>
                  <article className="snapshot-card">
                    <span className="summary-label">Catalysts</span>
                    <strong>{selectedTickerCatalysts.length}</strong>
                    <small>
                      {selectedTickerCatalysts.length > 0
                        ? selectedTickerCatalysts[0].payload.headline
                        : "No catalyst saved for this ticker"}
                    </small>
                  </article>
                </div>

                <section className="panel-card focus-editor-card">
                  <div className="compact-card-header">
                    <div>
                      <p className="eyebrow">Focus Queue</p>
                      <h3>{selectedTrackedStock ? selectedTrackedStock.ticker : "Select a ticker"}</h3>
                    </div>
                    {focusQueueEntryMeta ? (
                      <span className={`focus-source-badge ${focusQueueEntryMeta.source}`}>
                        {focusQueueEntryMeta.source === "saved" ? "Using saved override" : "Using generated default"}
                      </span>
                    ) : null}
                  </div>
                  {editingFocusEntry && selectedTrackedStock ? (
                    <div className="focus-editor-grid">
                      <label>
                        <span>Queue Bucket</span>
                        <select
                          value={editingFocusEntry.bucket}
                          onChange={(event) =>
                            setEditingFocusEntry({
                              ...editingFocusEntry,
                              bucket: event.target.value as FocusQueueBucket,
                            })
                          }
                        >
                          <option value="today_focus">Today Focus</option>
                          <option value="monitor">Monitor</option>
                          <option value="ignore">Ignore for now</option>
                        </select>
                      </label>
                      <label className="trade-plan-wide">
                        <span>Why is this on the board?</span>
                        <textarea
                          value={editingFocusEntry.whyOnList}
                          onChange={(event) =>
                            setEditingFocusEntry({
                              ...editingFocusEntry,
                              whyOnList: event.target.value,
                            })
                          }
                        />
                      </label>
                      <label className="trade-plan-wide">
                        <span>Trigger condition</span>
                        <textarea
                          value={editingFocusEntry.triggerCondition}
                          onChange={(event) =>
                            setEditingFocusEntry({
                              ...editingFocusEntry,
                              triggerCondition: event.target.value,
                            })
                          }
                        />
                      </label>
                      <label className="trade-plan-wide">
                        <span>Invalidation condition</span>
                        <textarea
                          value={editingFocusEntry.invalidationCondition}
                          onChange={(event) =>
                            setEditingFocusEntry({
                              ...editingFocusEntry,
                              invalidationCondition: event.target.value,
                            })
                          }
                        />
                      </label>
                      {focusQueueEntryMeta ? (
                        <div className="focus-generated-hint trade-plan-wide">
                          <strong>Generated suggestion</strong>
                          <span>
                            {focusBucketLabel(focusQueueEntryMeta.generated_payload.bucket)}:{" "}
                            {focusQueueEntryMeta.generated_payload.whyOnList}
                          </span>
                          <span>
                            Trigger: {focusQueueEntryMeta.generated_payload.triggerCondition}
                          </span>
                          <span>
                            Invalidation: {focusQueueEntryMeta.generated_payload.invalidationCondition}
                          </span>
                        </div>
                      ) : null}
                    </div>
                  ) : (
                    <p className="draft-empty-state">Select a tracked ticker to edit its focus queue assignment.</p>
                  )}
                  <div className="trade-plan-actions">
                    <button
                      className="refresh-button"
                      onClick={() => void persistFocusQueueEntry()}
                      disabled={!editingFocusEntry || savingFocusQueueEntry}
                    >
                      {savingFocusQueueEntry ? "Saving..." : "Save Focus Queue"}
                    </button>
                    {focusQueueEntryMeta?.source === "saved" && selectedTrackedStock ? (
                      <button
                        className="ghost-button"
                        onClick={() => void restoreGeneratedFocusQueueEntry(selectedTrackedStock.ticker)}
                        disabled={savingFocusQueueEntry}
                      >
                        Restore System Suggestion
                      </button>
                    ) : null}
                  </div>
                </section>

                <aside className="detail-panel workspace-detail-panel">
                  <DetailPanel
                    selected={selectedTrackedStock}
                    savedDrafts={
                      selectedTrackedStock
                        ? savedDrafts.filter((draft) => draft.ticker === selectedTrackedStock.ticker)
                        : []
                    }
                    groupedAlerts={
                      selectedAlertGroup
                        ? [selectedAlertGroup]
                        : activeTrackedTicker == null
                          ? []
                          : groupedAlerts.filter((group) => group.ticker === activeTrackedTicker)
                    }
                    triggeredAlerts={selectedTriggeredAlerts}
                    savedJournalEntries={selectedJournalPreview}
                    thesisOutcomeSummary={thesisOutcomeSummary}
                    tickerNote={tickerNote}
                    editingNote={editingNote}
                    savingTickerNote={savingTickerNote}
                    hasMoreAlerts={activeTrackedTicker != null && triggeredAlerts.some((alert) => alert.ticker === activeTrackedTicker && !selectedTriggeredAlerts.includes(alert))}
                    hasMoreJournal={activeTrackedTicker != null && savedJournalEntries.some((entry) => entry.ticker === activeTrackedTicker && !selectedJournalPreview.includes(entry))}
                    onShowChart={() => setShowChart(true)}
                    onTradePlan={() =>
                      selectedTrackedStock &&
                      hasUsablePrice(selectedTrackedStock) &&
                      setTradePlanDraft(buildTradePlanDraft(selectedTrackedStock))
                    }
                    onAlertRule={() =>
                      selectedTrackedStock &&
                      hasUsablePrice(selectedTrackedStock) &&
                      setAlertRuleDraft(buildAlertRuleDraft(selectedTrackedStock))
                    }
                    onJournal={() => selectedTrackedStock && setJournalDraft(buildJournalDraft(selectedTrackedStock))}
                    onRetryBootstrap={() => selectedTrackedStock && void retryBootstrap(selectedTrackedStock.ticker)}
                    retryingBootstrap={retryingBootstrap}
                    onTickerNoteChange={(next) => setEditingNote(next)}
                    onSaveTickerNote={() => void persistTickerNote()}
                    onLoadDraft={(draft) => setTradePlanDraft(draft)}
                    onEditAlertRule={(rule) =>
                      setAlertRuleDraft({ ...rule.payload, ruleId: rule.rule_id })
                    }
                    onToggleAlertRule={(ruleId, enabled) =>
                      void toggleAlertRuleEnabled(ruleId, enabled)
                    }
                    onDeleteAlertRule={(ruleId) => void deleteAlertRule(ruleId)}
                    onLoadMoreAlerts={() => void loadTriggeredAlerts(alertsOffset + ALERTS_PAGE)}
                    onLoadMoreJournal={() => void loadJournalEntries(journalOffset + JOURNAL_PAGE)}
                    onUpdateAlertTask={(alertId, status, snoozedUntil) =>
                      void updateAlertTaskStatus(alertId, status, snoozedUntil)
                    }
                  />
                </aside>
              </div>
            </div>
          </section>
        ) : null}

        {activeView === "leader" ? (
          <section className="tab-panel leader-panel">
            <div className="tab-panel-header">
              <div>
                <p className="eyebrow">Leader Overlay</p>
                <h2>Leader Holdings</h2>
              </div>
              <div className="workspace-controls">
                <span className="strategy-count">{leaderHoldings.length} tracked positions</span>
              </div>
            </div>

            <div className="workspace-layout">
              <aside className="workspace-side panel-card">
                <div className="compact-card-header">
                  <div>
                    <p className="eyebrow">Overlap</p>
                    <h3>{overlapLeaderHoldings.length} symbols on your board</h3>
                  </div>
                </div>
                <div className="workspace-stock-list">
                  {leaderHoldings.length === 0 ? (
                    <p className="draft-empty-state">No leader holdings saved yet.</p>
                  ) : (
                    leaderHoldings.map((holding) => (
                      <button
                        key={`leader-${holding.ticker}`}
                        className={`workspace-stock-item ${
                          editingLeaderHolding.ticker === holding.ticker ? "selected-list-item" : ""
                        }`}
                        onClick={() => setEditingLeaderHolding(holding.payload)}
                      >
                        <div className="triggered-alert-header">
                          <strong>{holding.ticker}</strong>
                          <span className="triggered-alert-badge">{holding.payload.positionStatus}</span>
                        </div>
                        <span>{holding.payload.conviction} conviction · {holding.payload.timeHorizon} horizon</span>
                        <span>{holding.payload.entryZone || "No entry zone saved."}</span>
                      </button>
                    ))
                  )}
                </div>
              </aside>

              <div className="workspace-main">
                <div className="workspace-summary-grid">
                  <article className="snapshot-card">
                    <span className="summary-label">Overlap</span>
                    <strong>{overlapLeaderHoldings.length}</strong>
                    <small>Leader positions also present on your watchlist</small>
                  </article>
                  <article className="snapshot-card">
                    <span className="summary-label">Heavy Conviction</span>
                    <strong>{leaderHoldings.filter((holding) => holding.payload.conviction === "heavy").length}</strong>
                    <small>Leader positions marked as heavy</small>
                  </article>
                  <article className="snapshot-card">
                    <span className="summary-label">New / Adding</span>
                    <strong>{leaderHoldings.filter((holding) => ["new", "adding"].includes(holding.payload.positionStatus)).length}</strong>
                    <small>Fresh accumulation signals</small>
                  </article>
                </div>

                <section className="panel-card focus-editor-card">
                  <div className="compact-card-header">
                    <div>
                      <p className="eyebrow">Holding Editor</p>
                      <h3>{editingLeaderHolding.ticker || "New leader holding"}</h3>
                    </div>
                  </div>

                  <div className="focus-editor-grid">
                    <label>
                      <span>Ticker</span>
                      <input
                        value={editingLeaderHolding.ticker}
                        onChange={(event) =>
                          setEditingLeaderHolding({
                            ...editingLeaderHolding,
                            ticker: event.target.value.toUpperCase(),
                          })
                        }
                        placeholder="e.g. NVDA"
                      />
                    </label>
                    <label>
                      <span>Position Status</span>
                      <select
                        value={editingLeaderHolding.positionStatus}
                        onChange={(event) =>
                          setEditingLeaderHolding({
                            ...editingLeaderHolding,
                            positionStatus: event.target.value as LeaderHoldingDraft["positionStatus"],
                          })
                        }
                      >
                        <option value="holding">Holding</option>
                        <option value="new">New</option>
                        <option value="adding">Adding</option>
                        <option value="trimming">Trimming</option>
                        <option value="closed">Closed</option>
                      </select>
                    </label>
                    <label>
                      <span>Conviction</span>
                      <select
                        value={editingLeaderHolding.conviction}
                        onChange={(event) =>
                          setEditingLeaderHolding({
                            ...editingLeaderHolding,
                            conviction: event.target.value as LeaderHoldingDraft["conviction"],
                          })
                        }
                      >
                        <option value="light">Light</option>
                        <option value="standard">Standard</option>
                        <option value="heavy">Heavy</option>
                      </select>
                    </label>
                    <label>
                      <span>Time Horizon</span>
                      <select
                        value={editingLeaderHolding.timeHorizon}
                        onChange={(event) =>
                          setEditingLeaderHolding({
                            ...editingLeaderHolding,
                            timeHorizon: event.target.value as LeaderHoldingDraft["timeHorizon"],
                          })
                        }
                      >
                        <option value="short">Short</option>
                        <option value="swing">Swing</option>
                        <option value="mid">Mid</option>
                      </select>
                    </label>
                    <label>
                      <span>Entry Zone</span>
                      <input
                        value={editingLeaderHolding.entryZone}
                        onChange={(event) =>
                          setEditingLeaderHolding({
                            ...editingLeaderHolding,
                            entryZone: event.target.value,
                          })
                        }
                        placeholder="e.g. 114-118"
                      />
                    </label>
                    <label>
                      <span>Last Updated At</span>
                      <input
                        value={editingLeaderHolding.lastUpdatedAt}
                        onChange={(event) =>
                          setEditingLeaderHolding({
                            ...editingLeaderHolding,
                            lastUpdatedAt: event.target.value,
                          })
                        }
                        placeholder="e.g. 2026-05-24 09:10 PT"
                      />
                    </label>
                    <label className="trade-plan-wide">
                      <span>Thesis</span>
                      <textarea
                        value={editingLeaderHolding.thesis}
                        onChange={(event) =>
                          setEditingLeaderHolding({
                            ...editingLeaderHolding,
                            thesis: event.target.value,
                          })
                        }
                      />
                    </label>
                    <label className="trade-plan-wide">
                      <span>Invalidated When</span>
                      <textarea
                        value={editingLeaderHolding.invalidatedWhen}
                        onChange={(event) =>
                          setEditingLeaderHolding({
                            ...editingLeaderHolding,
                            invalidatedWhen: event.target.value,
                          })
                        }
                      />
                    </label>
                  </div>

                  <div className="trade-plan-actions">
                    <button
                      className="refresh-button"
                      onClick={() => void persistLeaderHolding()}
                      disabled={savingLeaderHolding}
                    >
                      {savingLeaderHolding ? "Saving..." : "Save Holding"}
                    </button>
                    {editingLeaderHolding.ticker ? (
                      <button
                        className="ghost-button"
                        onClick={() => void deleteLeaderHolding(editingLeaderHolding.ticker)}
                        disabled={savingLeaderHolding}
                      >
                        Delete Holding
                      </button>
                    ) : null}
                    <button
                      className="ghost-button"
                      onClick={() => setEditingLeaderHolding(buildEmptyLeaderHolding())}
                      disabled={savingLeaderHolding}
                    >
                      New Entry
                    </button>
                  </div>
                </section>

                <section className="panel-card focus-column">
                  <div className="compact-card-header">
                    <div>
                      <p className="eyebrow">Recent Holdings</p>
                      <h3>Leader activity</h3>
                    </div>
                  </div>
                  <div className="focus-entry-list">
                    {leaderHoldings.length === 0 ? (
                      <p className="draft-empty-state">Start by entering the first leader position.</p>
                    ) : (
                      leaderHoldings.map((holding) => (
                        <article key={`leader-list-${holding.ticker}`} className="saved-draft-item">
                          <div className="triggered-alert-header">
                            <strong>{holding.ticker}</strong>
                            <span className="triggered-alert-badge">{holding.payload.positionStatus}</span>
                          </div>
                          <span>{holding.payload.thesis || "No thesis saved yet."}</span>
                          <span>
                            {holding.payload.conviction} conviction · {holding.payload.timeHorizon} horizon · {holding.payload.entryZone || "No entry zone"}
                          </span>
                          <span className="triggered-alert-time">
                            Updated {holding.payload.lastUpdatedAt || new Date(holding.updated_at).toLocaleString()}
                          </span>
                        </article>
                      ))
                    )}
                  </div>
                </section>
              </div>
            </div>
          </section>
        ) : null}

        {activeView === "catalysts" ? (
          <section className="tab-panel leader-panel">
            <div className="tab-panel-header">
              <div>
                <p className="eyebrow">Calendar Layer</p>
                <h2>Catalysts</h2>
              </div>
              <div className="workspace-controls">
                <span className="strategy-count">{catalystEvents.length} saved events</span>
              </div>
            </div>

            <div className="workspace-layout">
              <aside className="workspace-side panel-card">
                <div className="compact-card-header">
                  <div>
                    <p className="eyebrow">Today Context</p>
                    <h3>{macroCatalysts.length} macro events</h3>
                  </div>
                </div>
                <div className="workspace-stock-list">
                  {macroCatalysts.length === 0 ? (
                    <p className="draft-empty-state">No macro catalysts saved yet.</p>
                  ) : (
                    macroCatalysts.map((event) => (
                      <button
                        key={`macro-${event.event_id}`}
                        className={`workspace-stock-item ${
                          editingCatalystEvent.eventId === event.event_id ? "selected-list-item" : ""
                        }`}
                        onClick={() => {
                          setEditingCatalystEvent(event.payload);
                          setCatalystTagsInput(event.payload.tags.join(", "));
                        }}
                      >
                        <div className="triggered-alert-header">
                          <strong>{event.payload.headline}</strong>
                          <span className="triggered-alert-badge">{event.payload.eventType}</span>
                        </div>
                        <span>{event.payload.eventDate || "No date"} · {event.payload.timeLabel || "No time"}</span>
                        <span>{event.payload.notes || "No notes saved."}</span>
                      </button>
                    ))
                  )}
                </div>
              </aside>

              <div className="workspace-main">
                <div className="workspace-summary-grid">
                  <article className="snapshot-card">
                    <span className="summary-label">Macro</span>
                    <strong>{macroCatalysts.length}</strong>
                    <small>CPI, FOMC, nonfarm payrolls, and other market-wide events</small>
                  </article>
                  <article className="snapshot-card">
                    <span className="summary-label">Watchlist Events</span>
                    <strong>{watchlistCatalysts.length}</strong>
                    <small>Earnings, dividends, splits, options expiry, and news tags on your board</small>
                  </article>
                  <article className="snapshot-card">
                    <span className="summary-label">Selected Ticker</span>
                    <strong>{selectedTrackedStock?.ticker ?? "None"}</strong>
                    <small>
                      {selectedTrackedStock
                        ? `${selectedTickerCatalysts.length} saved catalysts`
                        : "Select a ticker elsewhere to see ticker-specific catalyst overlap"}
                    </small>
                  </article>
                </div>

                <section className="panel-card focus-editor-card">
                  <div className="compact-card-header">
                    <div>
                      <p className="eyebrow">Catalyst Editor</p>
                      <h3>{editingCatalystEvent.headline || "New catalyst event"}</h3>
                    </div>
                  </div>

                  <div className="focus-editor-grid">
                    <label>
                      <span>Scope</span>
                      <select
                        value={editingCatalystEvent.scope}
                        onChange={(event) =>
                          setEditingCatalystEvent({
                            ...editingCatalystEvent,
                            scope: event.target.value as CatalystEventDraft["scope"],
                            ticker: event.target.value === "macro" ? "" : editingCatalystEvent.ticker,
                            eventType:
                              event.target.value === "macro"
                                ? "macro_cpi"
                                : editingCatalystEvent.eventType === "macro_cpi" ||
                                    editingCatalystEvent.eventType === "macro_fomc" ||
                                    editingCatalystEvent.eventType === "macro_nfp"
                                  ? "earnings"
                                  : editingCatalystEvent.eventType,
                          })
                        }
                      >
                        <option value="macro">Macro</option>
                        <option value="ticker">Ticker</option>
                      </select>
                    </label>
                    <label>
                      <span>Ticker</span>
                      <input
                        value={editingCatalystEvent.ticker}
                        onChange={(event) =>
                          setEditingCatalystEvent({
                            ...editingCatalystEvent,
                            ticker: event.target.value.toUpperCase(),
                          })
                        }
                        placeholder={editingCatalystEvent.scope === "macro" ? "Leave blank for macro" : "e.g. AAPL"}
                        disabled={editingCatalystEvent.scope === "macro"}
                      />
                    </label>
                    <label>
                      <span>Event Type</span>
                      <select
                        value={editingCatalystEvent.eventType}
                        onChange={(event) =>
                          setEditingCatalystEvent({
                            ...editingCatalystEvent,
                            eventType: event.target.value as CatalystEventDraft["eventType"],
                          })
                        }
                      >
                        {editingCatalystEvent.scope === "macro" ? (
                          <>
                            <option value="macro_cpi">CPI</option>
                            <option value="macro_fomc">FOMC</option>
                            <option value="macro_nfp">Nonfarm Payrolls</option>
                            <option value="news_tag">Macro News Tag</option>
                          </>
                        ) : (
                          <>
                            <option value="earnings">Earnings</option>
                            <option value="ex_dividend">Ex-Dividend</option>
                            <option value="split">Split</option>
                            <option value="options_expiry">Options Expiry</option>
                            <option value="news_tag">News Tag</option>
                          </>
                        )}
                      </select>
                    </label>
                    <label>
                      <span>Event Date</span>
                      <input
                        value={editingCatalystEvent.eventDate}
                        onChange={(event) =>
                          setEditingCatalystEvent({
                            ...editingCatalystEvent,
                            eventDate: event.target.value,
                          })
                        }
                        placeholder="e.g. 2026-06-12"
                      />
                    </label>
                    <label>
                      <span>Time Label</span>
                      <input
                        value={editingCatalystEvent.timeLabel}
                        onChange={(event) =>
                          setEditingCatalystEvent({
                            ...editingCatalystEvent,
                            timeLabel: event.target.value,
                          })
                        }
                        placeholder="e.g. Pre-market, 11:00 ET"
                      />
                    </label>
                    <label className="trade-plan-wide">
                      <span>Headline</span>
                      <input
                        value={editingCatalystEvent.headline}
                        onChange={(event) =>
                          setEditingCatalystEvent({
                            ...editingCatalystEvent,
                            headline: event.target.value,
                          })
                        }
                        placeholder="e.g. NVDA earnings after the close"
                      />
                    </label>
                    <label className="trade-plan-wide">
                      <span>Tags</span>
                      <input
                        value={catalystTagsInput}
                        onChange={(event) => {
                          setCatalystTagsInput(event.target.value);
                          setEditingCatalystEvent({
                            ...editingCatalystEvent,
                            tags: event.target.value
                              .split(",")
                              .map((tag) => tag.trim())
                              .filter(Boolean),
                          });
                        }}
                        placeholder="e.g. inflation, rates, AI, guidance"
                      />
                    </label>
                    <label className="trade-plan-wide">
                      <span>Notes</span>
                      <textarea
                        value={editingCatalystEvent.notes}
                        onChange={(event) =>
                          setEditingCatalystEvent({
                            ...editingCatalystEvent,
                            notes: event.target.value,
                          })
                        }
                      />
                    </label>
                  </div>

                  <div className="trade-plan-actions">
                    <button
                      className="refresh-button"
                      onClick={() => void persistCatalystEvent()}
                      disabled={savingCatalystEvent}
                    >
                      {savingCatalystEvent ? "Saving..." : "Save Catalyst"}
                    </button>
                    {editingCatalystEvent.eventId ? (
                      <button
                        className="ghost-button"
                        onClick={() => void deleteCatalystEvent(editingCatalystEvent.eventId!)}
                        disabled={savingCatalystEvent}
                      >
                        Delete Catalyst
                      </button>
                    ) : null}
                    <button
                      className="ghost-button"
                      onClick={() => {
                        setEditingCatalystEvent(buildEmptyCatalystEvent());
                        setCatalystTagsInput("");
                      }}
                      disabled={savingCatalystEvent}
                    >
                      New Event
                    </button>
                  </div>
                </section>

                <section className="panel-card focus-column">
                  <div className="compact-card-header">
                    <div>
                      <p className="eyebrow">Catalyst Calendar</p>
                      <h3>
                        {catalystView === "today"
                          ? `Today · ${todayCatalysts.length} event${todayCatalysts.length !== 1 ? "s" : ""}`
                          : catalystView === "this_week"
                            ? `This Week · ${thisWeekCatalysts.length} event${thisWeekCatalysts.length !== 1 ? "s" : ""}`
                            : `By Ticker · ${Object.keys(byTickerMap).length} group${Object.keys(byTickerMap).length !== 1 ? "s" : ""}`}
                      </h3>
                    </div>
                    <div className="catalyst-view-tabs">
                      <button
                        className={`catalyst-tab-btn ${catalystView === "today" ? "active" : ""}`}
                        onClick={() => setCatalystView("today")}
                      >
                        Today
                      </button>
                      <button
                        className={`catalyst-tab-btn ${catalystView === "this_week" ? "active" : ""}`}
                        onClick={() => setCatalystView("this_week")}
                      >
                        This Week
                      </button>
                      <button
                        className={`catalyst-tab-btn ${catalystView === "by_ticker" ? "active" : ""}`}
                        onClick={() => setCatalystView("by_ticker")}
                      >
                        By Ticker
                      </button>
                    </div>
                  </div>

                  {catalystView === "today" || catalystView === "this_week" ? (
                    <div className="focus-entry-list">
                      {(catalystView === "today" ? todayCatalysts : thisWeekCatalysts).length === 0 ? (
                        <p className="draft-empty-state">
                          {catalystView === "today"
                            ? "No events scheduled for today."
                            : "No events in the next 7 days."}
                        </p>
                      ) : (
                        (catalystView === "today" ? todayCatalysts : thisWeekCatalysts).map((event) => (
                          <button
                            key={`cv-${event.event_id}`}
                            className={`saved-draft-item catalyst-calendar-item ${
                              editingCatalystEvent.eventId === event.event_id ? "selected-list-item" : ""
                            }`}
                            onClick={() => {
                              setEditingCatalystEvent(event.payload);
                              setCatalystTagsInput(event.payload.tags.join(", "));
                            }}
                          >
                            <div className="triggered-alert-header">
                              <strong>{event.payload.headline}</strong>
                              <span className="triggered-alert-badge">{event.payload.eventType}</span>
                            </div>
                            <span className="catalyst-meta-line">
                              <span className={`catalyst-scope-tag ${event.payload.scope}`}>
                                {event.payload.scope === "macro" ? "Macro" : event.ticker}
                              </span>
                              {event.payload.eventDate && <span>{event.payload.eventDate}</span>}
                              {event.payload.timeLabel && <span>{event.payload.timeLabel}</span>}
                            </span>
                            {event.payload.tags.length > 0 && (
                              <span className="catalyst-tags">
                                {event.payload.tags.map((tag) => (
                                  <span key={tag} className="catalyst-tag-chip">{tag}</span>
                                ))}
                              </span>
                            )}
                          </button>
                        ))
                      )}
                    </div>
                  ) : (
                    <div className="focus-entry-list">
                      {Object.keys(byTickerMap).length === 0 ? (
                        <p className="draft-empty-state">Start by entering a macro or ticker catalyst.</p>
                      ) : (
                        Object.entries(byTickerMap)
                          .sort(([a], [b]) => (a === "__macro__" ? -1 : b === "__macro__" ? 1 : a.localeCompare(b)))
                          .map(([key, events]) => (
                            <div key={`group-${key}`} className="catalyst-ticker-group">
                              <p className="catalyst-group-label">
                                {key === "__macro__" ? "Macro" : key}
                                <span className="strategy-count">{events.length}</span>
                              </p>
                              {events
                                .slice()
                                .sort((a, b) => (a.payload.eventDate < b.payload.eventDate ? -1 : 1))
                                .map((event) => (
                                  <button
                                    key={`bt-${event.event_id}`}
                                    className={`saved-draft-item catalyst-calendar-item ${
                                      editingCatalystEvent.eventId === event.event_id ? "selected-list-item" : ""
                                    }`}
                                    onClick={() => {
                                      setEditingCatalystEvent(event.payload);
                                      setCatalystTagsInput(event.payload.tags.join(", "));
                                    }}
                                  >
                                    <div className="triggered-alert-header">
                                      <strong>{event.payload.headline}</strong>
                                      <span className="triggered-alert-badge">{event.payload.eventType}</span>
                                    </div>
                                    <span className="catalyst-meta-line">
                                      {event.payload.eventDate && <span>{event.payload.eventDate}</span>}
                                      {event.payload.timeLabel && <span>{event.payload.timeLabel}</span>}
                                    </span>
                                    {event.payload.tags.length > 0 && (
                                      <span className="catalyst-tags">
                                        {event.payload.tags.map((tag) => (
                                          <span key={tag} className="catalyst-tag-chip">{tag}</span>
                                        ))}
                                      </span>
                                    )}
                                  </button>
                                ))}
                            </div>
                          ))
                      )}
                    </div>
                  )}
                </section>
              </div>
            </div>
          </section>
        ) : null}

        {activeView === "trades" ? (
          <section className="tab-panel leader-panel">
            <div className="tab-panel-header">
              <div>
                <p className="eyebrow">Lifecycle Tracking</p>
                <h2>Trades</h2>
              </div>
              <div className="workspace-controls">
                <span className="strategy-count">{trades.length} tracked</span>
              </div>
            </div>
            <FilterStrip
              view="trades"
              tradeFilters={tradeFilters}
              onTradeFilters={setTradeFilters}
              presets={savedPresets.filter((p) => p.view === "trades")}
              onSavePreset={(name) => savePreset(name, "trades")}
              onDeletePreset={deletePreset}
              onApplyPreset={applyPreset}
              filteredCount={filteredTrades.length}
              totalCount={trades.length}
            />
            <TradeLifecyclePanel
              trades={filteredTrades}
              stocks={stocks}
              catalystEvents={catalystEvents}
              onSave={(trade) => persistTrade(trade)}
              onDelete={(tradeId) => deleteTrade(tradeId)}
            />
          </section>
        ) : null}

        {activeView === "review" ? (
          <section className="tab-panel leader-panel">
            <div className="tab-panel-header">
              <div>
                <p className="eyebrow">Self-Coaching</p>
                <h2>Review</h2>
              </div>
              <div className="workspace-controls">
                {reviewMetrics && (
                  <span className="strategy-count">
                    {reviewMetrics.total_closed} closed trades
                  </span>
                )}
              </div>
            </div>
            <ReviewPanel metrics={reviewMetrics} />
          </section>
        ) : null}
      </main>

      {showChart && selected ? (
        <StockChartModal stock={selected} onClose={() => setShowChart(false)} />
      ) : null}

      {tradePlanDraft ? (
        <TradePlanModal
          draft={tradePlanDraft}
          onChange={(next) => setTradePlanDraft(next)}
          onClose={() => setTradePlanDraft(null)}
          onSave={() => void persistDraft()}
          savingDraft={savingDraft}
          savingAlertRule={savingAlertRule}
          onCreateTargetAlert={() =>
            setAlertRuleDraft(buildTargetAlertFromTradePlan(tradePlanDraft))
          }
          onCreateStopAlert={() =>
            setAlertRuleDraft(buildStopAlertFromTradePlan(tradePlanDraft))
          }
          onCreateBothAlerts={() => void createBothAlertsFromDraft(tradePlanDraft)}
          onOpenJournal={() => setJournalDraft(buildJournalFromTradePlan(tradePlanDraft))}
        />
      ) : null}

      {alertRuleDraft ? (
        <AlertRuleModal
          draft={alertRuleDraft}
          onChange={(next) => {
            setAlertValidationError(null);
            setAlertRuleDraft(next);
          }}
          onClose={() => {
            setAlertRuleDraft(null);
            setAlertValidationError(null);
          }}
          onSave={() => void persistAlertRule()}
          savingAlertRule={savingAlertRule}
          validationError={alertValidationError}
        />
      ) : null}

      {journalDraft ? (
        <JournalModal
          draft={journalDraft}
          onChange={(next) => setJournalDraft(next)}
          onClose={() => setJournalDraft(null)}
          onSave={() => void persistJournalEntry()}
          savingJournalEntry={savingJournalEntry}
        />
      ) : null}

      {showUrgencySettings ? (
        <UrgencySettingsModal
          draft={urgencySettings}
          onChange={(next) => setUrgencySettings(next)}
          onClose={() => setShowUrgencySettings(false)}
          onSave={() => void persistUrgencySettings()}
          saving={savingUrgencySettings}
        />
      ) : null}
    </div>
  );
}

export default App;
