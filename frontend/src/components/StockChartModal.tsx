import { useEffect, useMemo, useRef, useState } from "react";
import {
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  LineStyle,
  createChart,
  type CandlestickData,
  type IChartApi,
  type ISeriesApi,
  type Time,
} from "lightweight-charts";

import type { CandlePoint, HistoryRange, StockCard } from "../types";

const RANGES: HistoryRange[] = ["5m", "1h", "1D", "5D", "1M", "3M", "6M", "1Y"];

function formatCurrency(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  }).format(value);
}

function normalizeCandles(candles: CandlePoint[]): CandlestickData<Time>[] {
  return candles.map((candle, index) => ({
    time: index as Time,
    open: candle.open,
    high: candle.high,
    low: candle.low,
    close: candle.close,
  }));
}

function CandleChart({
  candles,
  labels,
}: {
  candles: CandlePoint[];
  labels: string[];
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);

  useEffect(() => {
    if (!containerRef.current || candles.length === 0) {
      return;
    }

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "#171d2a" },
        textColor: "#c9d4df",
      },
      grid: {
        vertLines: {
          color: "rgba(255,255,255,0.05)",
          style: LineStyle.Dotted,
        },
        horzLines: {
          color: "rgba(255,255,255,0.05)",
          style: LineStyle.Dotted,
        },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
      },
      rightPriceScale: {
        borderColor: "rgba(255,255,255,0.12)",
      },
      timeScale: {
        borderColor: "rgba(255,255,255,0.12)",
        tickMarkFormatter: (time: Time) => labels[Number(time)] ?? "",
      },
      height: 520,
      width: containerRef.current.clientWidth,
    });

    const series = chart.addSeries(CandlestickSeries, {
      upColor: "#82d2ff",
      downColor: "#ff8d8d",
      wickUpColor: "#82d2ff",
      wickDownColor: "#ff8d8d",
      borderVisible: false,
    });

    series.setData(normalizeCandles(candles));
    chart.timeScale().fitContent();

    chartRef.current = chart;
    seriesRef.current = series;

    const resizeObserver = new ResizeObserver(() => {
      if (containerRef.current && chartRef.current) {
        chartRef.current.applyOptions({
          width: containerRef.current.clientWidth,
        });
      }
    });

    resizeObserver.observe(containerRef.current);

    return () => {
      resizeObserver.disconnect();
      chartRef.current?.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, [candles, labels]);

  return <div ref={containerRef} className="modal-chart-canvas" />;
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

  const labels = useMemo(() => candles.map((candle) => candle.label), [candles]);

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
        {!loading && !error && candles.length > 0 ? (
          <div className="modal-chart-shell">
            <CandleChart candles={candles} labels={labels} />
            <div className="modal-axis">
              <span>{candles[0]?.label ?? ""}</span>
              <span>{candles[candles.length - 1]?.label ?? ""}</span>
            </div>
          </div>
        ) : null}

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
