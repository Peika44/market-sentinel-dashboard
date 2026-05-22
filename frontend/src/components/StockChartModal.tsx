import { useEffect, useMemo, useState } from "react";

import type { CandlePoint, HistoryRange, StockCard } from "../types";

const RANGES: HistoryRange[] = ["5m", "1h", "1D", "5D", "1M", "3M", "6M", "1Y"];

function formatCurrency(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  }).format(value);
}

function HistoryChart({ candles }: { candles: CandlePoint[] }) {
  const closes = candles.map((candle) => candle.close);
  const min = Math.min(...closes);
  const max = Math.max(...closes);
  const spread = max - min || 1;

  const points = closes
    .map((close, index) => {
      const x = (index / Math.max(closes.length - 1, 1)) * 100;
      const y = 100 - ((close - min) / spread) * 100;
      return `${x},${y}`;
    })
    .join(" ");

  return (
    <div className="modal-chart-shell">
      <svg className="modal-chart" viewBox="0 0 100 100" preserveAspectRatio="none">
        <defs>
          <linearGradient id="chart-fill" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="rgba(124, 208, 255, 0.55)" />
            <stop offset="100%" stopColor="rgba(124, 208, 255, 0.02)" />
          </linearGradient>
        </defs>
        <polygon
          points={`0,100 ${points} 100,100`}
          fill="url(#chart-fill)"
        />
        <polyline
          fill="none"
          stroke="currentColor"
          strokeWidth="2.4"
          points={points}
        />
      </svg>
      <div className="modal-axis">
        <span>{candles[0]?.label ?? ""}</span>
        <span>{candles[candles.length - 1]?.label ?? ""}</span>
      </div>
    </div>
  );
}

interface StockChartModalProps {
  stock: StockCard;
  onClose: () => void;
}

export function StockChartModal({ stock, onClose }: StockChartModalProps) {
  const [range, setRange] = useState<HistoryRange>("1M");
  const [candles, setCandles] = useState<CandlePoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };

    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [onClose]);

  useEffect(() => {
    let cancelled = false;

    async function loadHistory() {
      setLoading(true);
      setError(null);
      try {
        const response = await fetch(`/api/stocks/${stock.ticker}/history?range=${range}`);
        if (!response.ok) {
          throw new Error("Failed to load history.");
        }
        const payload = (await response.json()) as { candles: CandlePoint[] };
        if (!cancelled) {
          setCandles(payload.candles);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load history.");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void loadHistory();
    return () => {
      cancelled = true;
    };
  }, [range, stock.ticker]);

  const stats = useMemo(() => {
    if (!candles.length) {
      return null;
    }

    const closes = candles.map((candle) => candle.close);
    const high = Math.max(...candles.map((candle) => candle.high));
    const low = Math.min(...candles.map((candle) => candle.low));
    return {
      last: closes[closes.length - 1],
      high,
      low,
      change: closes[closes.length - 1] - closes[0],
    };
  }, [candles]);

  return (
    <div className="modal-backdrop" onClick={(event) => event.target === event.currentTarget && onClose()}>
      <div className="modal-card">
        <div className="modal-header">
          <div>
            <p className="eyebrow">Price History</p>
            <h2>{stock.ticker}</h2>
            <p className="detail-name">{stock.display_name}</p>
          </div>
          <button className="modal-close-button" onClick={onClose}>
            Close
          </button>
        </div>

        <div className="range-row">
          {RANGES.map((option) => (
            <button
              key={option}
              className={`range-pill ${range === option ? "selected" : ""}`}
              onClick={() => setRange(option)}
            >
              {option}
            </button>
          ))}
        </div>

        {loading ? <div className="modal-loading">Loading history...</div> : null}
        {error ? <div className="error-banner">{error}</div> : null}
        {!loading && !error && candles.length > 0 ? <HistoryChart candles={candles} /> : null}

        {stats ? (
          <div className="modal-metrics">
            <div>
              <span>Last</span>
              <strong>{formatCurrency(stats.last)}</strong>
            </div>
            <div>
              <span>Range High</span>
              <strong>{formatCurrency(stats.high)}</strong>
            </div>
            <div>
              <span>Range Low</span>
              <strong>{formatCurrency(stats.low)}</strong>
            </div>
            <div>
              <span>Net Move</span>
              <strong className={stats.change >= 0 ? "change-up" : "change-down"}>
                {stats.change >= 0 ? "+" : ""}
                {formatCurrency(stats.change)}
              </strong>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
