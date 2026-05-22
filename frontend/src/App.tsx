import { FormEvent, useEffect, useState } from "react";

import type {
  DashboardSnapshot,
  IndexQuote,
  MarketEvent,
  MarketOverviewResponse,
  StockCard,
} from "./types";

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
  const [selectedTicker, setSelectedTicker] = useState<string | null>(null);
  const [tickerInput, setTickerInput] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [connected, setConnected] = useState(false);

  async function loadDashboard() {
    const response = await fetch(`/api/dashboard/${DEMO_USER_ID}`);
    if (!response.ok) {
      throw new Error("Failed to load dashboard snapshot.");
    }

    const payload = (await response.json()) as DashboardSnapshot;
    const nextStocks = sortByUrgency(payload.stocks);
    setStocks(nextStocks);
    setSelectedTicker((current) => current ?? nextStocks[0]?.ticker ?? null);
  }

  async function loadOverview() {
    const response = await fetch("/api/market-overview");
    if (!response.ok) {
      throw new Error("Failed to load market overview.");
    }

    const payload = (await response.json()) as MarketOverviewResponse;
    setIndices(payload.indices);
  }

  async function refresh() {
    setError(null);
    setLoading(true);
    try {
      await Promise.all([loadDashboard(), loadOverview()]);
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
    setSelectedTicker((current) => {
      if (current !== ticker) {
        return current;
      }
      return stocks.find((item) => item.ticker !== ticker)?.ticker ?? null;
    });
  }

  useEffect(() => {
    refresh();
  }, []);

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

  const selected = stocks.find((stock) => stock.ticker === selectedTicker) ?? stocks[0] ?? null;

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
          <article key={quote.ticker} className="overview-card">
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

      <section className="content-grid">
        <div className="card-grid">
          {stocks.map((stock) => (
            <article
              key={stock.ticker}
              className={`stock-card ${selected?.ticker === stock.ticker ? "selected" : ""}`}
              onClick={() => setSelectedTicker(stock.ticker)}
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

              <div className="mini-chart">
                <Sparkline points={stock.history} />
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

              <p className="detail-copy">
                Urgency blends price movement with sentiment confidence so the UI can surface
                names that need attention without polling every chart view individually.
              </p>
            </>
          ) : (
            <div className="empty-panel">
              <h2>No tracked tickers yet</h2>
              <p>Add a symbol to the watchlist to populate the dashboard.</p>
            </div>
          )}
        </aside>
      </section>
    </div>
  );
}

export default App;

