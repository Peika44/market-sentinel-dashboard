import { useState } from "react";
import type {
  BreakoutScanJobState,
  BreakoutScanResult,
  IntradayJobState,
  IntradayResult,
  ScanJobState,
  ScanPreset,
  ScanResult,
  TradePlanDraft,
} from "../types";

interface ScannerPanelProps {
  scanStatus: ScanJobState | null;
  intradayStatus: IntradayJobState | null;
  breakoutStatus: BreakoutScanJobState | null;
  onRunScan: (preset: ScanPreset, minScore: number) => void;
  onRunIntraday: (tickers: string[]) => void;
  onRunBreakoutScan: (preset: ScanPreset) => void;
  onAddToWatchlist: (ticker: string) => void;
  onCreateTradePlan: (draft: TradePlanDraft) => void;
}

// ---------------------------------------------------------------------------
// Shared helpers
// ---------------------------------------------------------------------------

const DAILY_SIGNAL_LABELS: Record<string, string> = {
  bottom_position: "底部",
  volume_surge: "放量",
  rsi_recovery: "RSI回升",
  ma_cross: "均线金叉",
  macd_signal: "MACD",
};

const BREAKOUT_SIGNAL_LABELS: Record<string, string> = {
  market_aligned: "市场",
  trend_up: "趋势",
  volume_surge: "放量",
  breakout_signal: "突破",
  pullback_signal: "回调",
};

const INTRADAY_SIGNAL_LABELS: Record<string, string> = {
  gap_ok: "缺口",
  breakout_held: "突破保持",
  orderflow_ok: "订单流",
  pullback_ok: "缩量回调",
  spoofing_ok: "无虚假",
};

function ProgressBar({
  value,
  total,
  label,
}: {
  value: number;
  total: number;
  label?: string;
}) {
  const pct = total > 0 ? Math.min(100, Math.round((value / total) * 100)) : 0;
  return (
    <div className="scanner-progress-wrap">
      <div className="scanner-progress-bar-outer">
        <div className="scanner-progress-bar-inner" style={{ width: `${pct}%` }} />
      </div>
      <span className="scanner-progress-label">
        {label ?? "扫描中"} {value}/{total} 只… ({pct}%)
      </span>
    </div>
  );
}

function DailySignalBadges({ signals }: { signals: ScanResult["signals"] }) {
  const active = Object.entries(signals)
    .filter(([, v]) => v)
    .map(([k]) => k);
  if (active.length === 0) return null;
  return (
    <span className="scanner-signal-badges">
      {active.map((key) => (
        <span key={key} className="scanner-signal-badge">
          {DAILY_SIGNAL_LABELS[key] ?? key}
        </span>
      ))}
    </span>
  );
}

function BreakoutSignalBadges({ signals }: { signals: BreakoutScanResult["signals"] }) {
  const active = Object.entries(signals)
    .filter(([, v]) => v)
    .map(([k]) => k);
  if (active.length === 0) return null;
  return (
    <span className="scanner-signal-badges">
      {active.map((key) => (
        <span
          key={key}
          className={`scanner-signal-badge ${key === "breakout_signal" ? "breakout-badge" : key === "pullback_signal" ? "pullback-badge" : ""}`}
        >
          {BREAKOUT_SIGNAL_LABELS[key] ?? key}
        </span>
      ))}
    </span>
  );
}

function RangeBar({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  return (
    <span className="scanner-range-bar" title={`52周位置 ${pct}%`}>
      <span className="scanner-range-fill" style={{ width: `${pct}%` }} />
      <span className="scanner-range-label">{pct}%</span>
    </span>
  );
}

// ---------------------------------------------------------------------------
// Intraday confirmation badge
// ---------------------------------------------------------------------------

function IntradayBadge({
  ticker,
  intradayStatus,
}: {
  ticker: string;
  intradayStatus: IntradayJobState | null;
}) {
  if (!intradayStatus || intradayStatus.status === "idle") {
    return <span className="intraday-badge idle">—</span>;
  }

  if (intradayStatus.status === "running") {
    const done = ticker in intradayStatus.results;
    if (!done) return <span className="intraday-badge pending">…</span>;
  }

  const r: IntradayResult | undefined = intradayStatus.results[ticker];
  if (!r) return <span className="intraday-badge idle">—</span>;

  const cls = r.confirmed
    ? "confirmed"
    : r.signals_passed >= 3
      ? "partial"
      : "failed";

  const label = r.confirmed
    ? `✓ 5/5`
    : `${r.signals_passed}/5`;

  const signalSummary = Object.entries(r.signals)
    .map(([k, v]) => `${v ? "✓" : "✗"} ${INTRADAY_SIGNAL_LABELS[k] ?? k}`)
    .join(" · ");

  return (
    <span
      className={`intraday-badge ${cls}`}
      title={`${signalSummary}\n${r.note}`}
    >
      {label}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Bottom-building result row
// ---------------------------------------------------------------------------

function ResultRow({
  result,
  intradayStatus,
  onAddToWatchlist,
  onCreateTradePlan,
}: {
  result: ScanResult;
  intradayStatus: IntradayJobState | null;
  onAddToWatchlist: (ticker: string) => void;
  onCreateTradePlan: (draft: TradePlanDraft) => void;
}) {
  const changeCls = result.price_change_pct >= 0 ? "change-up" : "change-down";
  const changeStr =
    (result.price_change_pct >= 0 ? "+" : "") + result.price_change_pct.toFixed(2) + "%";

  const intradayResult: IntradayResult | undefined =
    intradayStatus?.results?.[result.ticker];

  function handleCreatePlan() {
    if (intradayResult?.confirmed && intradayResult.entry_price != null) {
      onCreateTradePlan({
        ticker: result.ticker,
        setupType: "mean_reversion",
        entryPrice: intradayResult.entry_price.toFixed(2),
        stopLoss: (intradayResult.stop_price ?? intradayResult.entry_price * 0.97).toFixed(2),
        targetPrice: (intradayResult.target_price ?? intradayResult.entry_price * 1.06).toFixed(2),
        thesis:
          `${result.ticker} 两级确认: 日线评分 ${result.score}/100 (52周 ${Math.round(result.position_in_range * 100)}%) · ` +
          `日内 ${intradayResult.signals_passed}/5 信号通过 · ` +
          `突破位保持 ${intradayResult.breakout_hold_minutes}min · 量比 ${intradayResult.volume_ratio.toFixed(1)}x`,
        riskPercent: "1.0",
        positionSizeUsd: "1000",
        checklist: {
          hasCatalyst: false,
          atKeyLevel: true,
          rrSufficient: true,
          marketAligned: false,
          withinSession: true,
        },
      });
    } else {
      const entry = result.last_close;
      onCreateTradePlan({
        ticker: result.ticker,
        setupType: "mean_reversion",
        entryPrice: entry.toFixed(2),
        stopLoss: (entry * 0.95).toFixed(2),
        targetPrice: (entry * 1.1).toFixed(2),
        thesis: `${result.ticker} 底部筑底信号: 评分 ${result.score}/100, 52周位置 ${Math.round(result.position_in_range * 100)}%, RSI ${result.rsi_current.toFixed(1)}, 量比 ${result.volume_ratio.toFixed(1)}x`,
        riskPercent: "1.0",
        positionSizeUsd: "1000",
        checklist: {
          hasCatalyst: false,
          atKeyLevel: true,
          rrSufficient: false,
          marketAligned: false,
          withinSession: false,
        },
      });
    }
  }

  return (
    <tr className={`scanner-result-row ${intradayResult?.confirmed ? "intraday-confirmed-row" : ""}`}>
      <td className="scanner-rank">{result.rank}</td>
      <td className="scanner-ticker">
        <strong>{result.ticker}</strong>
      </td>
      <td className="scanner-price">${result.last_close.toFixed(2)}</td>
      <td className={`scanner-change ${changeCls}`}>{changeStr}</td>
      <td className="scanner-range">
        <RangeBar value={result.position_in_range} />
      </td>
      <td className="scanner-rsi">{result.rsi_current.toFixed(1)}</td>
      <td className="scanner-volratio">{result.volume_ratio.toFixed(1)}x</td>
      <td className="scanner-score">
        <span className="scanner-score-badge">{result.score}</span>
      </td>
      <td className="scanner-signals-cell">
        <DailySignalBadges signals={result.signals} />
      </td>
      <td className="scanner-intraday-cell">
        <IntradayBadge ticker={result.ticker} intradayStatus={intradayStatus} />
      </td>
      <td className="scanner-actions">
        <button
          className="ghost-button scanner-action-btn"
          onClick={() => onAddToWatchlist(result.ticker)}
          title="加入监控列表"
        >
          加入监控
        </button>
        <button
          className="ghost-button scanner-action-btn"
          onClick={handleCreatePlan}
          title={intradayResult?.confirmed ? "使用日内精确价位制定计划" : "制定交易计划"}
        >
          制定计划
        </button>
      </td>
    </tr>
  );
}

// ---------------------------------------------------------------------------
// Breakout/Pullback result row
// ---------------------------------------------------------------------------

function BreakoutResultRow({
  result,
  onAddToWatchlist,
  onCreateTradePlan,
}: {
  result: BreakoutScanResult;
  onAddToWatchlist: (ticker: string) => void;
  onCreateTradePlan: (draft: TradePlanDraft) => void;
}) {
  const changeCls = result.price_change_pct >= 0 ? "change-up" : "change-down";
  const changeStr =
    (result.price_change_pct >= 0 ? "+" : "") + result.price_change_pct.toFixed(2) + "%";

  const isBreakout = result.setup_type === "breakout";

  function handleCreatePlan() {
    const entry = result.last_close;
    // Stop: just below signal-bar low (approximated as 2.5% below for breakout, 1.5% for pullback)
    const stopPct = isBreakout ? 0.025 : 0.015;
    const stop = entry * (1 - stopPct);
    const risk = entry - stop;
    const target = entry + risk * 1.8;  // 1.8R

    onCreateTradePlan({
      ticker: result.ticker,
      setupType: isBreakout ? "breakout" : "pullback",
      entryPrice: entry.toFixed(2),
      stopLoss: stop.toFixed(2),
      targetPrice: target.toFixed(2),
      thesis: isBreakout
        ? `${result.ticker} 突破信号: 突破位 $${result.breakout_level.toFixed(2)}, 今日+${result.daily_return_pct.toFixed(1)}%, 收盘强度 ${(result.close_strength * 100).toFixed(0)}%, 量比 ${result.volume_ratio.toFixed(1)}x, 评分 ${result.score}/100`
        : `${result.ticker} 回调信号: 价格回调至 $${entry.toFixed(2)}, 回调自高点, 量比 ${result.volume_ratio.toFixed(1)}x, 评分 ${result.score}/100`,
      riskPercent: "1.0",
      positionSizeUsd: "1000",
      checklist: {
        hasCatalyst: false,
        atKeyLevel: isBreakout,
        rrSufficient: true,
        marketAligned: result.signals.market_aligned,
        withinSession: true,
      },
    });
  }

  return (
    <tr className="scanner-result-row">
      <td className="scanner-rank">{result.rank}</td>
      <td className="scanner-ticker">
        <strong>{result.ticker}</strong>
      </td>
      <td className="scanner-price">${result.last_close.toFixed(2)}</td>
      <td className={`scanner-change ${changeCls}`}>{changeStr}</td>
      <td className="scanner-breakout-level">${result.breakout_level.toFixed(2)}</td>
      <td className="scanner-close-strength">
        <span
          className="scanner-strength-bar"
          title={`收盘强度 ${(result.close_strength * 100).toFixed(0)}%`}
        >
          <span
            className="scanner-strength-fill"
            style={{ width: `${Math.round(result.close_strength * 100)}%` }}
          />
          <span className="scanner-strength-label">
            {(result.close_strength * 100).toFixed(0)}%
          </span>
        </span>
      </td>
      <td className="scanner-volratio">{result.volume_ratio.toFixed(1)}x</td>
      <td className="scanner-score">
        <span className="scanner-score-badge">{result.score}</span>
      </td>
      <td className="scanner-setup-type">
        <span className={`setup-type-badge ${isBreakout ? "breakout" : "pullback"}`}>
          {isBreakout ? "突破" : "回调"}
        </span>
      </td>
      <td className="scanner-signals-cell">
        <BreakoutSignalBadges signals={result.signals} />
      </td>
      <td className="scanner-actions">
        <button
          className="ghost-button scanner-action-btn"
          onClick={() => onAddToWatchlist(result.ticker)}
          title="加入监控列表"
        >
          加入监控
        </button>
        <button
          className="ghost-button scanner-action-btn"
          onClick={handleCreatePlan}
          title="制定交易计划"
        >
          制定计划
        </button>
      </td>
    </tr>
  );
}

// ---------------------------------------------------------------------------
// Main panel
// ---------------------------------------------------------------------------

export function ScannerPanel({
  scanStatus,
  intradayStatus,
  breakoutStatus,
  onRunScan,
  onRunIntraday,
  onRunBreakoutScan,
  onAddToWatchlist,
  onCreateTradePlan,
}: ScannerPanelProps) {
  const [scanMode, setScanMode] = useState<"bottom" | "breakout">("bottom");

  const isDailyRunning = scanStatus?.status === "running";
  const isDailyCompleted = scanStatus?.status === "completed";
  const isDailyFailed = scanStatus?.status === "failed";
  const isIntradayRunning = intradayStatus?.status === "running";

  const isBreakoutRunning = breakoutStatus?.status === "running";
  const isBreakoutCompleted = breakoutStatus?.status === "completed";
  const isBreakoutFailed = breakoutStatus?.status === "failed";

  const candidateTickers =
    isDailyCompleted ? scanStatus.results.map((r) => r.ticker) : [];

  const intradayConfirmedCount = isDailyCompleted
    ? Object.values(intradayStatus?.results ?? {}).filter((r) => r.confirmed).length
    : 0;

  return (
    <div className="scanner-panel">
      {/* ── Mode toggle ── */}
      <div className="scanner-mode-toggle">
        <button
          className={`scanner-mode-btn ${scanMode === "bottom" ? "active" : ""}`}
          onClick={() => setScanMode("bottom")}
        >
          底部筑底
        </button>
        <button
          className={`scanner-mode-btn ${scanMode === "breakout" ? "active" : ""}`}
          onClick={() => setScanMode("breakout")}
        >
          突破 / 回调
        </button>
      </div>

      {/* ══════════════════════════════════════════
          BOTTOM-BUILDING MODE
      ══════════════════════════════════════════ */}
      {scanMode === "bottom" && (
        <>
          {/* ── Header + daily scan controls ── */}
          <div className="scanner-controls panel-card">
            <div className="scanner-controls-row">
              <div>
                <p className="eyebrow">两级信号扫描</p>
                <h3>底部筑底 + 日内订单流</h3>
              </div>
              <div className="scanner-preset-group">
                <button
                  className="refresh-button"
                  disabled={isDailyRunning}
                  onClick={() => onRunScan("sp500", 40)}
                >
                  {isDailyRunning ? "扫描中…" : "S&P 500 日线扫描"}
                </button>
                <button
                  className="ghost-button"
                  disabled={isDailyRunning}
                  onClick={() => onRunScan("nasdaq100", 40)}
                >
                  Nasdaq 100
                </button>
              </div>
            </div>

            <p className="scanner-description">
              <strong>第一级（日线）</strong>：52周低位 + 量价放量 + RSI回升 + 均线金叉 + MACD，满分100分，≥40分入选。
              <br />
              <strong>第二级（日内）</strong>：yfinance 1分钟数据，验证今日缺口 / 突破保持 / 订单流 / 缩量回调 / 无虚假拉升。
            </p>

            <div className="scanner-legend">
              <span className="scanner-legend-item scanner-legend-daily">日线：底部 25 · 放量 25 · RSI 20 · 均线 15 · MACD 15</span>
              <span className="scanner-legend-sep">|</span>
              <span className="scanner-legend-item scanner-legend-intraday">日内：缺口 · 突破 · 订单流 · 回调 · 无虚假</span>
            </div>
          </div>

          {isDailyRunning && scanStatus ? (
            <div className="panel-card">
              <ProgressBar
                value={scanStatus.progress_scanned}
                total={scanStatus.progress_total}
                label="日线扫描"
              />
            </div>
          ) : null}

          {isDailyFailed ? (
            <div className="error-banner">
              日线扫描失败：{scanStatus?.error ?? "未知错误"}
              {" · 请确认 Alpaca API 密钥已在 .env 中配置"}
            </div>
          ) : null}

          {scanStatus == null || scanStatus.status === "idle" ? (
            <div className="panel-card scanner-idle-hint">
              <p className="draft-empty-state">
                点击「S&P 500 日线扫描」开始。约扫描 460 只股票，按评分排序。
                <br />
                <small>日线扫描需要 Alpaca API Key；日内确认通过 yfinance（无需额外配置）。</small>
              </p>
            </div>
          ) : null}

          {isDailyCompleted && scanStatus.results.length > 0 ? (
            <div className="panel-card scanner-results-wrap">
              <div className="scanner-results-header">
                <strong>扫描结果</strong>
                <span className="strategy-count">{scanStatus.results.length} 只入选</span>

                {intradayStatus?.status === "running" ? (
                  <span className="intraday-running-label">
                    日内确认中 {intradayStatus.progress_scanned}/{intradayStatus.progress_total}…
                  </span>
                ) : intradayStatus?.status === "completed" ? (
                  <span className="intraday-summary-label">
                    日内确认：{intradayConfirmedCount} / {scanStatus.results.length} 只通过
                  </span>
                ) : (
                  <button
                    className="ghost-button scanner-action-btn"
                    disabled={isIntradayRunning}
                    onClick={() => onRunIntraday(candidateTickers)}
                  >
                    日内验证全部
                  </button>
                )}

                {scanStatus.completed_at ? (
                  <small className="scanner-completed-at">
                    日线完成 {new Date(scanStatus.completed_at).toLocaleTimeString()}
                  </small>
                ) : null}
              </div>

              {isIntradayRunning && intradayStatus ? (
                <div style={{ marginBottom: 10 }}>
                  <ProgressBar
                    value={intradayStatus.progress_scanned}
                    total={intradayStatus.progress_total}
                    label="日内验证"
                  />
                </div>
              ) : null}

              <div className="scanner-table-scroll">
                <table className="scanner-table">
                  <thead>
                    <tr>
                      <th>排名</th>
                      <th>代码</th>
                      <th>价格</th>
                      <th>今日</th>
                      <th>52周位置</th>
                      <th>RSI</th>
                      <th>量比</th>
                      <th>评分</th>
                      <th>日线信号</th>
                      <th>日内确认</th>
                      <th>操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {scanStatus.results.map((result) => (
                      <ResultRow
                        key={result.ticker}
                        result={result}
                        intradayStatus={intradayStatus}
                        onAddToWatchlist={onAddToWatchlist}
                        onCreateTradePlan={onCreateTradePlan}
                      />
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : isDailyCompleted && scanStatus.results.length === 0 ? (
            <div className="panel-card">
              <p className="draft-empty-state">
                本次扫描未发现符合条件的股票（评分 &lt; 40 分）。市场整体可能处于高位或数据不足。
              </p>
            </div>
          ) : null}
        </>
      )}

      {/* ══════════════════════════════════════════
          BREAKOUT / PULLBACK MODE
      ══════════════════════════════════════════ */}
      {scanMode === "breakout" && (
        <>
          {/* ── Header + breakout scan controls ── */}
          <div className="scanner-controls panel-card">
            <div className="scanner-controls-row">
              <div>
                <p className="eyebrow">动量信号扫描</p>
                <h3>突破 / 回调策略</h3>
              </div>
              <div className="scanner-preset-group">
                <button
                  className="refresh-button"
                  disabled={isBreakoutRunning}
                  onClick={() => onRunBreakoutScan("sp500")}
                >
                  {isBreakoutRunning ? "扫描中…" : "S&P 500 突破扫描"}
                </button>
                <button
                  className="ghost-button"
                  disabled={isBreakoutRunning}
                  onClick={() => onRunBreakoutScan("nasdaq100")}
                >
                  Nasdaq 100
                </button>
              </div>
            </div>

            <p className="scanner-description">
              <strong>突破形态</strong>：价格突破20日新高，当日涨幅 2.5–9%，量比 ≥ 1.8x，收盘强度 ≥ 72%，趋势向上（SMA5 &gt; SMA20）。
              <br />
              <strong>回调形态</strong>：前日强势上涨（≥1.75%）后今日缩量回调 ≤ 6%，收盘强度 ≥ 35%，价格不低于 SMA5×0.985。
            </p>

            <div className="scanner-legend">
              <span className="scanner-legend-item scanner-legend-daily">市场过滤：QQQ SMA10 &gt; SMA30 + 新高或强势日</span>
              <span className="scanner-legend-sep">|</span>
              <span className="scanner-legend-item scanner-legend-intraday">风险：R/R = 1.8，止损 = 信号低点×0.9975</span>
            </div>
          </div>

          {isBreakoutRunning && breakoutStatus ? (
            <div className="panel-card">
              <ProgressBar
                value={breakoutStatus.progress_scanned}
                total={breakoutStatus.progress_total}
                label="突破扫描"
              />
            </div>
          ) : null}

          {isBreakoutFailed ? (
            <div className="error-banner">
              突破扫描失败：{breakoutStatus?.error ?? "未知错误"}
              {" · 请确认 Alpaca API 密钥已在 .env 中配置"}
            </div>
          ) : null}

          {breakoutStatus == null || breakoutStatus.status === "idle" ? (
            <div className="panel-card scanner-idle-hint">
              <p className="draft-empty-state">
                点击「S&P 500 突破扫描」开始。筛选今日出现突破或强势回调信号的股票。
                <br />
                <small>使用 Alpaca 90天日线数据，自动验证 QQQ 市场过滤条件。</small>
              </p>
            </div>
          ) : null}

          {isBreakoutCompleted && breakoutStatus.results.length > 0 ? (
            <div className="panel-card scanner-results-wrap">
              <div className="scanner-results-header">
                <strong>突破/回调结果</strong>
                <span className="strategy-count">
                  {breakoutStatus.results.filter((r) => r.setup_type === "breakout").length} 突破
                  &nbsp;·&nbsp;
                  {breakoutStatus.results.filter((r) => r.setup_type === "pullback").length} 回调
                </span>
                {!breakoutStatus.market_filter_active ? (
                  <span className="market-filter-warn">市场过滤未通过（QQQ趋势不足）</span>
                ) : (
                  <span className="market-filter-ok">市场过滤通过</span>
                )}
                {breakoutStatus.completed_at ? (
                  <small className="scanner-completed-at">
                    完成 {new Date(breakoutStatus.completed_at).toLocaleTimeString()}
                  </small>
                ) : null}
              </div>

              <div className="scanner-table-scroll">
                <table className="scanner-table">
                  <thead>
                    <tr>
                      <th>排名</th>
                      <th>代码</th>
                      <th>价格</th>
                      <th>今日</th>
                      <th>突破位</th>
                      <th>收盘强度</th>
                      <th>量比</th>
                      <th>评分</th>
                      <th>形态</th>
                      <th>信号</th>
                      <th>操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {breakoutStatus.results.map((result) => (
                      <BreakoutResultRow
                        key={result.ticker}
                        result={result}
                        onAddToWatchlist={onAddToWatchlist}
                        onCreateTradePlan={onCreateTradePlan}
                      />
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : isBreakoutCompleted && breakoutStatus.results.length === 0 ? (
            <div className="panel-card">
              <p className="draft-empty-state">
                今日未发现突破或回调信号。
                {!breakoutStatus.market_filter_active
                  ? " QQQ 市场过滤未通过（整体趋势不足），所有信号被屏蔽。"
                  : " 可能处于整理行情，等待下一个交易日。"}
              </p>
            </div>
          ) : null}
        </>
      )}
    </div>
  );
}
