import { FormEvent, useEffect, useState } from "react";

import type {
  AlertRuleDraft,
  DashboardSnapshot,
  IndexQuote,
  MarketEvent,
  MarketOverviewResponse,
  StoredAlertRule,
  StockCard,
  StoredTradePlanDraft,
  StoredTriggeredAlert,
  TradePlanDraft,
} from "./types";
import { StockChartModal } from "./components/StockChartModal";
import { useMarketStatus } from "./hooks/useMarketStatus";

const DEMO_USER_ID = "demo-user";
const OVERVIEW_TICKERS = new Set(["SPY", "QQQ", "IWM"]);

function formatCurrency(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  }).format(value);
}

function computeUrgency(changePct: number, sentimentScore: number): number {
  const priceComponent = Math.min(Math.abs(changePct) * 5, 100) * 0.65;
  const sentimentComponent = (1 - sentimentScore) * 100 * 0.35;
  return Math.min(priceComponent + sentimentComponent, 100);
}

function sortByUrgency(stocks: StockCard[]): StockCard[] {
  return [...stocks].sort((left, right) => right.urgency_score - left.urgency_score);
}

function buildOverviewPreview(quote: IndexQuote): StockCard {
  return {
    ticker: quote.ticker,
    display_name: quote.label,
    current_price: quote.current_price,
    change_pct: quote.change_pct,
    volume: 0,
    last_updated: new Date().toISOString(),
    sentiment_score: 0.5,
    sentiment_label: "Neutral",
    urgency_score: computeUrgency(Math.abs(quote.change_pct), 0.5),
    history: [quote.current_price],
  };
}

function buildTradePlanDraft(stock: StockCard): TradePlanDraft {
  const entry = stock.current_price || 0;
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

async function saveAlertRuleDraft(userId: string, rule: AlertRuleDraft): Promise<void> {
  const response = await fetch("/api/alert-rules", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      user_id: userId,
      rule,
    }),
  });

  if (!response.ok) {
    throw new Error("Failed to save alert rule.");
  }
}

function getFreshnessLabel(lastUpdated: string): { label: string; stale: boolean } {
  const updatedAt = new Date(lastUpdated).getTime();
  const ageSeconds = Math.max(0, Math.round((Date.now() - updatedAt) / 1000));

  if (ageSeconds <= 10) {
    return { label: `Updated ${ageSeconds}s ago`, stale: false };
  }
  if (ageSeconds <= 60) {
    return { label: `Updated ${ageSeconds}s ago`, stale: false };
  }
  const ageMinutes = Math.round(ageSeconds / 60);
  return {
    label: `Updated ${ageMinutes}m ago`,
    stale: ageMinutes >= 2,
  };
}

function alertThresholdHelp(condition: string): string {
  if (condition === "price_change_above" || condition === "price_change_below") {
    return "Threshold is a percent change value, e.g. 2 means 2%.";
  }
  if (condition === "volume_above") {
    return "Threshold is a raw share volume number, e.g. 500000.";
  }
  if (condition === "target_hit" || condition === "drop_below_stop") {
    return "Threshold is a price level, e.g. 465 or 438.";
  }
  if (
    condition === "breakout_above_recent_high" ||
    condition === "breakdown_below_recent_low"
  ) {
    return "Threshold is a price buffer added to recent high/low. Use 0 for an exact level break, or 0.10 / 0.25 for confirmation.";
  }
  return "Threshold meaning depends on the selected condition.";
}

function Sparkline({ points }: { points: number[] }) {
  if (points.length < 2) {
    return <div className="chart-empty">Waiting for more ticks...</div>;
  }

  const min = Math.min(...points);
  const max = Math.max(...points);
  const spread = max - min || 1;

  const polyline = points
    .map((point, index) => {
      const x = (index / (points.length - 1)) * 100;
      const y = 100 - ((point - min) / spread) * 100;
      return `${x},${y}`;
    })
    .join(" ");

  return (
    <svg className="sparkline" viewBox="0 0 100 100" preserveAspectRatio="none">
      <polyline fill="none" stroke="currentColor" strokeWidth="4" points={polyline} />
    </svg>
  );
}

function App() {
  const [stocks, setStocks] = useState<StockCard[]>([]);
  const [indices, setIndices] = useState<IndexQuote[]>([]);
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
  const [tickerInput, setTickerInput] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [connected, setConnected] = useState(false);
  const [showChart, setShowChart] = useState(false);
  const [tradePlanDraft, setTradePlanDraft] = useState<TradePlanDraft | null>(null);
  const [savedDrafts, setSavedDrafts] = useState<StoredTradePlanDraft[]>([]);
  const [savingDraft, setSavingDraft] = useState(false);
  const [alertRuleDraft, setAlertRuleDraft] = useState<AlertRuleDraft | null>(null);
  const [savedAlertRules, setSavedAlertRules] = useState<StoredAlertRule[]>([]);
  const [savingAlertRule, setSavingAlertRule] = useState(false);
  const [triggeredAlerts, setTriggeredAlerts] = useState<StoredTriggeredAlert[]>([]);
  const marketStatus = useMarketStatus();

  async function loadDashboard() {
    const response = await fetch(`/api/dashboard/${DEMO_USER_ID}`);
    if (!response.ok) {
      throw new Error("Failed to load dashboard snapshot.");
    }

    const payload = (await response.json()) as DashboardSnapshot;
    const nextStocks = sortByUrgency(payload.stocks);
    setStocks(nextStocks);
    setSelectedSymbol((current) => current ?? nextStocks[0]?.ticker ?? null);
  }

  async function loadOverview() {
    const response = await fetch("/api/market-overview");
    if (!response.ok) {
      throw new Error("Failed to load market overview.");
    }

    const payload = (await response.json()) as MarketOverviewResponse;
    setIndices(payload.indices);
  }

  async function loadDrafts() {
    const response = await fetch(`/api/trade-plan-drafts/${DEMO_USER_ID}`);
    if (!response.ok) {
      throw new Error("Failed to load trade plan drafts.");
    }

    const payload = (await response.json()) as StoredTradePlanDraft[];
    setSavedDrafts(payload);
  }

  async function loadAlertRules() {
    const response = await fetch(`/api/alert-rules/${DEMO_USER_ID}`);
    if (!response.ok) {
      throw new Error("Failed to load alert rules.");
    }

    const payload = (await response.json()) as StoredAlertRule[];
    setSavedAlertRules(payload);
  }

  async function loadTriggeredAlerts() {
    const response = await fetch(`/api/triggered-alerts/${DEMO_USER_ID}?limit=10`);
    if (!response.ok) {
      throw new Error("Failed to load triggered alerts.");
    }

    const payload = (await response.json()) as StoredTriggeredAlert[];
    setTriggeredAlerts(payload);
  }

  async function refresh() {
    setError(null);
    setLoading(true);
    try {
      await Promise.all([
        loadDashboard(),
        loadOverview(),
        loadDrafts(),
        loadAlertRules(),
        loadTriggeredAlerts(),
      ]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Dashboard refresh failed.");
    } finally {
      setLoading(false);
    }
  }

  async function addTicker(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const ticker = tickerInput.trim().toUpperCase();
    if (!ticker) {
      return;
    }

    setError(null);
    const response = await fetch("/api/watchlist", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: DEMO_USER_ID, ticker }),
    });

    if (!response.ok) {
      setError("Failed to add ticker to watchlist.");
      return;
    }

    setTickerInput("");
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
      if (current !== ticker) {
        return current;
      }
      return stocks.find((item) => item.ticker !== ticker)?.ticker ?? null;
    });
  }

  useEffect(() => {
    refresh();
  }, []);

  async function persistDraft() {
    if (!tradePlanDraft) {
      return;
    }

    setSavingDraft(true);
    setError(null);
    try {
      const response = await fetch("/api/trade-plan-drafts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: DEMO_USER_ID,
          draft: tradePlanDraft,
        }),
      });

      if (!response.ok) {
        throw new Error("Failed to save trade plan draft.");
      }

      await loadDrafts();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save trade plan draft.");
    } finally {
      setSavingDraft(false);
    }
  }

  async function persistAlertRule() {
    if (!alertRuleDraft) {
      return;
    }

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

  useEffect(() => {
    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    const socket = new WebSocket(`${protocol}://${window.location.host}/ws/dashboard`);

    socket.onopen = () => setConnected(true);
    socket.onclose = () => setConnected(false);
    socket.onerror = () => setConnected(false);

    socket.onmessage = (message) => {
      const payload = JSON.parse(message.data) as MarketEvent;
      if (payload.type !== "price_update") {
        return;
      }

      if (OVERVIEW_TICKERS.has(payload.ticker)) {
        setIndices((current) =>
          current.map((quote) =>
            quote.ticker === payload.ticker
              ? {
                  ...quote,
                  current_price: payload.current_price,
                  change_pct: payload.change_pct,
                }
              : quote,
          ),
        );
        return;
      }

      setStocks((current) =>
        sortByUrgency(
          current.map((stock) => {
            if (stock.ticker !== payload.ticker) {
              return stock;
            }

            const history = [...stock.history, payload.current_price].slice(-24);
            return {
              ...stock,
              current_price: payload.current_price,
              change_pct: payload.change_pct,
              volume: payload.volume,
              history,
              urgency_score: computeUrgency(payload.change_pct, stock.sentiment_score),
            };
          }),
        ),
      );
    };

    return () => socket.close();
  }, []);

  const overviewSelections = indices.map(buildOverviewPreview);
  const selected =
    [...stocks, ...overviewSelections].find((stock) => stock.ticker === selectedSymbol) ??
    stocks[0] ??
    overviewSelections[0] ??
    null;

  return (
    <div className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Event-Driven Portfolio Monitor</p>
          <h1>Market Sentinel Dashboard</h1>
          <p className="subtitle">
            Kafka-backed watchlist dashboard with real-time urgency ranking and one-command deployment.
          </p>
        </div>
        <div className="status-cluster">
          <span
            className={`status-pill ${marketStatus.isOpen ? "market-open" : "market-closed"}`}
          >
            <span className="status-dot" />
            Market {marketStatus.label}
          </span>
          <span className={`status-pill ${connected ? "online" : "offline"}`}>
            <span className="status-dot" />
            {connected ? "WebSocket live" : "Reconnecting"}
          </span>
          <span className="status-pill neutral">Docker Compose</span>
          <span className="status-pill neutral">Redpanda / Kafka</span>
        </div>
      </header>

      <section className="hero-card">
        <div>
          <h2>Why this repo exists</h2>
          <p>
            The goal is to showcase deployable architecture, not just a static UI:
            a publisher emits market events, the backend consumes and rebroadcasts them,
            and the dashboard reconciles live updates into a ranked watchlist.
          </p>
        </div>
        <button className="refresh-button" onClick={refresh} disabled={loading}>
          {loading ? "Refreshing..." : "Refresh Snapshot"}
        </button>
      </section>

      <section className="toolbar">
        <form className="watchlist-form" onSubmit={addTicker}>
          <input
            value={tickerInput}
            onChange={(event) => setTickerInput(event.target.value.toUpperCase())}
            placeholder="Add ticker, e.g. AMZN"
            maxLength={10}
          />
          <button type="submit">Add</button>
        </form>
        <p className="toolbar-note">
          Demo user: <code>{DEMO_USER_ID}</code>
        </p>
      </section>

      {error ? <div className="error-banner">{error}</div> : null}

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
              className={`stock-card ${selected?.ticker === stock.ticker ? "selected" : ""}`}
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
                <strong>{formatCurrency(stock.current_price)}</strong>
                <span className={stock.change_pct >= 0 ? "change-up" : "change-down"}>
                  {stock.change_pct >= 0 ? "+" : ""}
                  {stock.change_pct.toFixed(2)}%
                </span>
              </div>

              <div className="badge-row">
                <span className="sentiment-badge">{stock.sentiment_label}</span>
                <span className="urgency-badge">Urgency {stock.urgency_score.toFixed(0)}</span>
              </div>

              <div className="freshness-row">
                {(() => {
                  const freshness = getFreshnessLabel(stock.last_updated);
                  return (
                    <span className={`freshness-pill ${freshness.stale ? "stale" : "fresh"}`}>
                      {freshness.label}
                    </span>
                  );
                })()}
              </div>

              <div className="mini-chart">
                <Sparkline points={stock.history} />
              </div>

              <div className="card-actions">
                <button
                  className="ghost-button"
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
          {selected ? (
            <>
              <p className="eyebrow">Selected Position</p>
              <h2>{selected.ticker}</h2>
              <p className="detail-name">{selected.display_name}</p>
              <p className="detail-meta">
                {selected.volume > 0
                  ? `${selected.volume.toLocaleString("en-US")} shares in latest update`
                  : "Market overview selection"}
              </p>

              <div className="detail-metrics">
                <div>
                  <span>Last Price</span>
                  <strong>{formatCurrency(selected.current_price)}</strong>
                </div>
                <div>
                  <span>Daily Change</span>
                  <strong className={selected.change_pct >= 0 ? "change-up" : "change-down"}>
                    {selected.change_pct >= 0 ? "+" : ""}
                    {selected.change_pct.toFixed(2)}%
                  </strong>
                </div>
                <div>
                  <span>Sentiment</span>
                  <strong>{selected.sentiment_label}</strong>
                </div>
                <div>
                  <span>Urgency Score</span>
                  <strong>{selected.urgency_score.toFixed(2)}</strong>
                </div>
              </div>

              <div className="detail-chart">
                <Sparkline points={selected.history} />
              </div>

              <div className="detail-actions">
                <button className="refresh-button" onClick={() => setShowChart(true)}>
                  View Range Chart
                </button>
                <button
                  className="ghost-button"
                  onClick={() => setTradePlanDraft(buildTradePlanDraft(selected))}
                >
                  Open Trade Plan Seed
                </button>
                <button
                  className="ghost-button"
                  onClick={() => setAlertRuleDraft(buildAlertRuleDraft(selected))}
                >
                  Open Alert Rule
                </button>
              </div>

              <p className="detail-copy">
                Urgency blends price movement with sentiment confidence so the UI can surface
                names that need attention without polling every chart view individually.
              </p>

              <div className="saved-drafts-panel">
                <p className="eyebrow">Saved Drafts</p>
                {savedDrafts.length === 0 ? (
                  <p className="draft-empty-state">No saved trade-plan drafts yet.</p>
                ) : (
                  <div className="saved-drafts-list">
                    {savedDrafts.slice(0, 4).map((draft) => (
                      <button
                        key={`${draft.ticker}-${draft.updated_at}`}
                        className="saved-draft-item"
                        onClick={() => setTradePlanDraft(draft.payload)}
                      >
                        <strong>{draft.ticker}</strong>
                        <span>{new Date(draft.updated_at).toLocaleString()}</span>
                      </button>
                    ))}
                  </div>
                )}
              </div>

              <div className="saved-drafts-panel">
                <p className="eyebrow">Saved Alerts</p>
                {savedAlertRules.length === 0 ? (
                  <p className="draft-empty-state">No saved alert rules yet.</p>
                ) : (
                  <div className="saved-drafts-list">
                    {savedAlertRules.slice(0, 4).map((rule) => (
                      <button
                        key={`${rule.ticker}-${rule.updated_at}`}
                        className="saved-draft-item"
                        onClick={() => setAlertRuleDraft(rule.payload)}
                      >
                        <strong>{rule.ticker}</strong>
                        <span>
                          {rule.payload.condition} · {rule.payload.threshold} · {new Date(rule.updated_at).toLocaleString()}
                        </span>
                      </button>
                    ))}
                  </div>
                )}
              </div>

              <div className="saved-drafts-panel">
                <p className="eyebrow">Recent Triggered Alerts</p>
                {triggeredAlerts.length === 0 ? (
                  <p className="draft-empty-state">No alerts have triggered yet.</p>
                ) : (
                  <div className="saved-drafts-list">
                    {triggeredAlerts.slice(0, 5).map((alert) => (
                      <div
                        key={`${alert.ticker}-${alert.triggered_at}-${alert.payload.condition}`}
                        className="saved-draft-item"
                      >
                        <strong>{alert.ticker}</strong>
                        <span>{alert.payload.message}</span>
                        <span>{new Date(alert.triggered_at).toLocaleString()}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </>
          ) : (
            <div className="empty-panel">
              <h2>No tracked tickers yet</h2>
              <p>Add a symbol to the watchlist to populate the dashboard.</p>
            </div>
          )}
        </aside>
      </section>

      {showChart && selected ? (
        <StockChartModal
          stock={selected}
          onClose={() => setShowChart(false)}
        />
      ) : null}

      {tradePlanDraft ? (
        <div
          className="modal-backdrop"
          onClick={(event) => {
            if (event.target === event.currentTarget) {
              setTradePlanDraft(null);
            }
          }}
        >
          <div className="modal-card trade-plan-modal">
            <div className="modal-header">
              <div>
                <p className="eyebrow">Trade Plan Seed</p>
                <h2>{tradePlanDraft.ticker}</h2>
                <p className="detail-name">
                  Lightweight workflow bridge from dashboard selection to an executable plan draft.
                </p>
              </div>
              <button
                className="modal-close-button"
                onClick={() => setTradePlanDraft(null)}
              >
                Close
              </button>
            </div>

            <div className="trade-plan-grid">
              <label>
                Entry Price
                <input
                  value={tradePlanDraft.entryPrice}
                  onChange={(event) =>
                    setTradePlanDraft((current) =>
                      current
                        ? { ...current, entryPrice: event.target.value }
                        : current,
                    )
                  }
                />
              </label>
              <label>
                Stop Loss
                <input
                  value={tradePlanDraft.stopLoss}
                  onChange={(event) =>
                    setTradePlanDraft((current) =>
                      current
                        ? { ...current, stopLoss: event.target.value }
                        : current,
                    )
                  }
                />
              </label>
              <label>
                Target Price
                <input
                  value={tradePlanDraft.targetPrice}
                  onChange={(event) =>
                    setTradePlanDraft((current) =>
                      current
                        ? { ...current, targetPrice: event.target.value }
                        : current,
                    )
                  }
                />
              </label>
              <label>
                Risk %
                <input
                  value={tradePlanDraft.riskPercent}
                  onChange={(event) =>
                    setTradePlanDraft((current) =>
                      current
                        ? { ...current, riskPercent: event.target.value }
                        : current,
                    )
                  }
                />
              </label>
              <label>
                Position Size USD
                <input
                  value={tradePlanDraft.positionSizeUsd}
                  onChange={(event) =>
                    setTradePlanDraft((current) =>
                      current
                        ? { ...current, positionSizeUsd: event.target.value }
                        : current,
                    )
                  }
                />
              </label>
              <label className="trade-plan-wide">
                Thesis
                <textarea
                  value={tradePlanDraft.thesis}
                  onChange={(event) =>
                    setTradePlanDraft((current) =>
                      current
                        ? { ...current, thesis: event.target.value }
                        : current,
                    )
                  }
                />
              </label>
            </div>

            <div className="trade-plan-summary">
              <div>
                <span>Risk / Reward</span>
                <strong>
                  {(() => {
                    const entry = Number.parseFloat(tradePlanDraft.entryPrice);
                    const stop = Number.parseFloat(tradePlanDraft.stopLoss);
                    const target = Number.parseFloat(tradePlanDraft.targetPrice);
                    const risk = Math.abs(entry - stop);
                    const reward = Math.abs(target - entry);
                    return risk > 0 ? `${(reward / risk).toFixed(2)}R` : "—";
                  })()}
                </strong>
              </div>
              <div>
                <span>Workflow Note</span>
                <strong>Use this draft as a handoff into a fuller trading workflow.</strong>
              </div>
            </div>

            <div className="trade-plan-actions">
              <button
                className="refresh-button"
                onClick={() => void persistDraft()}
                disabled={savingDraft}
              >
                {savingDraft ? "Saving..." : "Save Draft"}
              </button>
              <button
                className="ghost-button"
                onClick={() => setAlertRuleDraft(buildTargetAlertFromTradePlan(tradePlanDraft))}
              >
                Create Target Alert
              </button>
              <button
                className="ghost-button"
                onClick={() => setAlertRuleDraft(buildStopAlertFromTradePlan(tradePlanDraft))}
              >
                Create Stop Alert
              </button>
              <button
                className="ghost-button"
                onClick={() => void createBothAlertsFromDraft(tradePlanDraft)}
                disabled={savingAlertRule}
              >
                {savingAlertRule ? "Creating..." : "Create Both Alerts"}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {alertRuleDraft ? (
        <div
          className="modal-backdrop"
          onClick={(event) => {
            if (event.target === event.currentTarget) {
              setAlertRuleDraft(null);
            }
          }}
        >
          <div className="modal-card trade-plan-modal">
            <div className="modal-header">
              <div>
                <p className="eyebrow">Alert Rule</p>
                <h2>{alertRuleDraft.ticker}</h2>
                <p className="detail-name">
                  Minimal alert configuration to start building a decision-support loop.
                </p>
              </div>
              <button
                className="modal-close-button"
                onClick={() => setAlertRuleDraft(null)}
              >
                Close
              </button>
            </div>

            <div className="trade-plan-grid">
              <label>
                Condition
                <select
                  value={alertRuleDraft.condition}
                  onChange={(event) =>
                    setAlertRuleDraft((current) =>
                      current ? { ...current, condition: event.target.value } : current,
                    )
                  }
                >
                  <option value="urgency_above">Urgency Above</option>
                  <option value="price_change_above">Price Change Above %</option>
                  <option value="price_change_below">Price Change Below %</option>
                  <option value="volume_above">Volume Above</option>
                  <option value="target_hit">Target Hit</option>
                  <option value="drop_below_stop">Drop Below Stop</option>
                  <option value="breakout_above_recent_high">Breakout Above Recent High</option>
                  <option value="breakdown_below_recent_low">Breakdown Below Recent Low</option>
                </select>
              </label>
              <label>
                Threshold
                <input
                  value={alertRuleDraft.threshold}
                  onChange={(event) =>
                    setAlertRuleDraft((current) =>
                      current ? { ...current, threshold: event.target.value } : current,
                    )
                  }
                />
                <small className="field-help">
                  {alertThresholdHelp(alertRuleDraft.condition)}
                </small>
              </label>
              <label>
                Cooldown Minutes
                <input
                  value={alertRuleDraft.cooldownMinutes}
                  onChange={(event) =>
                    setAlertRuleDraft((current) =>
                      current ? { ...current, cooldownMinutes: event.target.value } : current,
                    )
                  }
                />
              </label>
              <label>
                Channel
                <input
                  value={alertRuleDraft.channel}
                  onChange={(event) =>
                    setAlertRuleDraft((current) =>
                      current ? { ...current, channel: event.target.value } : current,
                    )
                  }
                />
              </label>
            </div>

            <div className="trade-plan-actions">
              <button
                className="refresh-button"
                onClick={() => void persistAlertRule()}
                disabled={savingAlertRule}
              >
                {savingAlertRule ? "Saving..." : "Save Alert Rule"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

export default App;
