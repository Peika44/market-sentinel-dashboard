import { FormEvent, useEffect, useState } from "react";

import type {
  AlertRuleDraft,
  DashboardSnapshot,
  HealthResponse,
  IndexQuote,
  JournalEntryDraft,
  MarketEvent,
  MarketOverviewResponse,
  StoredAlertRule,
  StoredJournalEntry,
  StockCard,
  StoredTradePlanDraft,
  StoredTriggeredAlert,
  TickerValidationResult,
  TradePlanDraft,
} from "./types";
import { StockChartModal } from "./components/StockChartModal";
import { Sparkline, UrgencyBar } from "./components/Sparkline";
import { TradePlanModal } from "./components/TradePlanModal";
import { AlertRuleModal } from "./components/AlertRuleModal";
import { JournalModal } from "./components/JournalModal";
import { DetailPanel } from "./components/DetailPanel";
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

function computeUrgency(changePct: number, sentimentScore: number): number {
  const priceComponent = Math.min(Math.abs(changePct) * 5, 100) * 0.65;
  const sentimentComponent = (1 - sentimentScore) * 100 * 0.35;
  return Math.min(priceComponent + sentimentComponent, 100);
}

function sortByUrgency(stocks: StockCard[]): StockCard[] {
  return [...stocks].sort((left, right) => right.urgency_score - left.urgency_score);
}

function buildOverviewPreview(quote: IndexQuote, history: number[]): StockCard {
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
    urgency_score: computeUrgency(Math.abs(quote.change_pct), 0.5),
    history,
  };
}

function buildTradePlanDraft(stock: StockCard): TradePlanDraft {
  const entry = stock.current_price ?? 0;
  return {
    ticker: stock.ticker,
    entryPrice: entry.toFixed(2),
    stopLoss: (entry * 0.97).toFixed(2),
    targetPrice: (entry * 1.06).toFixed(2),
    thesis: `${stock.ticker} is ranked high on the dashboard with ${stock.sentiment_label.toLowerCase()} sentiment and an urgency score of ${stock.urgency_score.toFixed(0)}.`,
    riskPercent: "1.0",
    positionSizeUsd: "1000",
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
  const [showChart, setShowChart] = useState(false);
  const [tradePlanDraft, setTradePlanDraft] = useState<TradePlanDraft | null>(null);
  const [retryingBootstrap, setRetryingBootstrap] = useState(false);
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
  const [journalOffset, setJournalOffset] = useState(0);
  const [hasMoreJournal, setHasMoreJournal] = useState(false);
  const marketStatus = useMarketStatus();
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

  async function refresh() {
    setError(null);
    setLoading(true);
    try {
      await Promise.all([
        loadHealth(),
        loadDashboard(),
        loadOverview(),
        loadDrafts(),
        loadAlertRules(),
        loadTriggeredAlerts(),
        loadJournalEntries(),
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
    await loadDashboard();
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
    await loadDashboard();
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
                urgency_score: computeUrgency(payload.change_pct, stock.sentiment_score),
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
    buildOverviewPreview(quote, indexHistory[quote.ticker] ?? [quote.current_price]),
  );
  const selected =
    [...stocks, ...overviewSelections].find((stock) => stock.ticker === selectedSymbol) ??
    stocks[0] ??
    overviewSelections[0] ??
    null;
  const selectedStatusLabel = selected
    ? selected.data_status === "live"
      ? "Live"
      : selected.data_status === "delayed"
        ? "Delayed"
        : "Waiting"
    : "Idle";
  const providerLabel = health?.provider?.toUpperCase() ?? "UNKNOWN";
  const feedLabel = health?.feed?.toUpperCase() ?? "N/A";

  useEffect(() => {
    if (!selected || selected.data_status === "live") {
      return;
    }

    const timer = window.setTimeout(() => {
      void retryBootstrap(selected.ticker);
    }, selected.data_status === "waiting" ? 15000 : 30000);

    return () => window.clearTimeout(timer);
  }, [selected?.ticker, selected?.data_status]);

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

      <section className="legend-row">
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
      </section>

      <section className="content-grid">
        <div className="card-grid">
          {stocks.map((stock) => (
            <article
              key={stock.ticker}
              className={`stock-card ${selected?.ticker === stock.ticker ? "selected" : ""} ${
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

        <aside className="detail-panel">
          <DetailPanel
            selected={selected}
            savedDrafts={savedDrafts}
            groupedAlerts={groupedAlerts}
            triggeredAlerts={triggeredAlerts}
            savedJournalEntries={savedJournalEntries}
            hasMoreAlerts={hasMoreAlerts}
            hasMoreJournal={hasMoreJournal}
            onShowChart={() => setShowChart(true)}
            onTradePlan={() => selected && hasUsablePrice(selected) && setTradePlanDraft(buildTradePlanDraft(selected))}
            onAlertRule={() => selected && hasUsablePrice(selected) && setAlertRuleDraft(buildAlertRuleDraft(selected))}
            onJournal={() => selected && setJournalDraft(buildJournalDraft(selected))}
            onRetryBootstrap={() => selected && void retryBootstrap(selected.ticker)}
            retryingBootstrap={retryingBootstrap}
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
          />
        </aside>
      </section>

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
    </div>
  );
}

export default App;
