import type {
  AlertUtilityStat,
  MistakeTagStat,
  ReviewMetrics,
  SessionBucket,
  SetupStat,
} from "../types";
import { formatAlertCondition } from "../utils/format";

// ─── Stat Card ────────────────────────────────────────────────────────────────

function StatCard({
  label,
  value,
  color,
}: {
  label: string;
  value: string;
  color?: "green" | "red" | "neutral";
}) {
  return (
    <div className="review-stat-card">
      <span className={`review-stat-value ${color ?? "neutral"}`}>{value}</span>
      <span className="review-stat-label">{label}</span>
    </div>
  );
}

// ─── Win Rate Bar ─────────────────────────────────────────────────────────────

function WinRateBar({
  label,
  win,
  count,
  winRate,
}: {
  label: string;
  win: number;
  count: number;
  winRate: number;
}) {
  const pct = Math.round(winRate * 100);
  return (
    <div className="review-bar-row">
      <span className="review-bar-label">{label}</span>
      <div className="review-bar-track">
        <div className="review-bar-fill" style={{ width: `${pct}%` }} />
      </div>
      <span className="review-bar-pct">{pct}%</span>
      <span className="review-bar-count">
        {win}/{count}
      </span>
    </div>
  );
}

// ─── Setup Section ────────────────────────────────────────────────────────────

const SETUP_LABELS: Record<string, string> = {
  breakout: "Breakout",
  pullback: "Pullback",
  mean_reversion: "Mean Rev",
  trend_continuation: "Trend Cont.",
  event_driven: "Event-Driven",
};

function SetupSection({ stats }: { stats: SetupStat[] }) {
  return (
    <div className="review-section">
      <p className="review-section-title">Setup Performance</p>
      {stats.length === 0 ? (
        <p className="review-empty-note">No closed trades yet.</p>
      ) : (
        stats.map((s) => (
          <WinRateBar
            key={s.setup_type}
            label={SETUP_LABELS[s.setup_type] ?? s.setup_type}
            win={s.win}
            count={s.count}
            winRate={s.win_rate}
          />
        ))
      )}
    </div>
  );
}

// ─── Session Section ──────────────────────────────────────────────────────────

function SessionSection({ buckets }: { buckets: SessionBucket[] }) {
  return (
    <div className="review-section">
      <p className="review-section-title">Session Performance</p>
      {buckets.length === 0 ? (
        <p className="review-empty-note">No entry timestamps recorded yet.</p>
      ) : (
        buckets.map((b) => (
          <WinRateBar
            key={b.label}
            label={b.label}
            win={b.win}
            count={b.count}
            winRate={b.win_rate}
          />
        ))
      )}
    </div>
  );
}

// ─── Alert Section ────────────────────────────────────────────────────────────

function AlertSection({ stats }: { stats: AlertUtilityStat[] }) {
  return (
    <div className="review-section">
      <p className="review-section-title">Alert Utility</p>
      {stats.length === 0 ? (
        <p className="review-empty-note">No alert history yet.</p>
      ) : (
        stats.map((a) => {
          const pct = Math.round(a.act_rate * 100);
          return (
            <div key={a.condition} className="review-alert-row">
              <span className="review-bar-label">{formatAlertCondition(a.condition)}</span>
              <div className="review-bar-track">
                <div className="review-bar-fill acted" style={{ width: `${pct}%` }} />
              </div>
              <span className="review-bar-pct">{pct}%</span>
              <span className="review-bar-count">
                {a.acted}/{a.total}
              </span>
            </div>
          );
        })
      )}
    </div>
  );
}

// ─── Mistake Section ──────────────────────────────────────────────────────────

function MistakeSection({ tags }: { tags: MistakeTagStat[] }) {
  const maxCount = tags.length > 0 ? Math.max(...tags.map((t) => t.count)) : 1;
  return (
    <div className="review-section">
      <p className="review-section-title">Mistake Patterns</p>
      {tags.length === 0 ? (
        <p className="review-empty-note">
          No mistake tags yet. In the Trades view, advance a trade to Reviewed and tag your
          mistakes to track patterns here.
        </p>
      ) : (
        tags.map((t) => (
          <div key={t.tag} className="review-bar-row">
            <span className="review-bar-label">{t.label}</span>
            <div className="review-bar-track">
              <div
                className="review-bar-fill mistake"
                style={{ width: `${Math.round((t.count / maxCount) * 100)}%` }}
              />
            </div>
            <span className="review-bar-count">{t.count}</span>
          </div>
        ))
      )}
    </div>
  );
}

// ─── Review Panel ─────────────────────────────────────────────────────────────

export function ReviewPanel({ metrics }: { metrics: ReviewMetrics | null }) {
  if (!metrics) {
    return (
      <div className="review-panel">
        <p className="review-empty-note">Loading review metrics…</p>
      </div>
    );
  }

  const winRatePct =
    metrics.total_closed > 0 ? `${Math.round(metrics.overall_win_rate * 100)}%` : "—";
  const avgWin = metrics.avg_winner_r != null ? `+${metrics.avg_winner_r.toFixed(2)}R` : "—";
  const avgLoss = metrics.avg_loser_r != null ? `${metrics.avg_loser_r.toFixed(2)}R` : "—";

  return (
    <div className="review-panel">
      <div className="review-stats-row">
        <StatCard label="Closed Trades" value={String(metrics.total_closed)} color="neutral" />
        <StatCard
          label="Win Rate"
          value={winRatePct}
          color={
            metrics.total_closed === 0
              ? "neutral"
              : metrics.overall_win_rate >= 0.5
                ? "green"
                : "red"
          }
        />
        <StatCard label="Avg Winner R" value={avgWin} color="green" />
        <StatCard label="Avg Loser R" value={avgLoss} color="red" />
      </div>

      <div className="review-grid-2col">
        <SetupSection stats={metrics.by_setup} />
        <SessionSection buckets={metrics.by_session} />
      </div>

      <div className="review-grid-2col">
        <AlertSection stats={metrics.alert_utility} />
        <MistakeSection tags={metrics.mistake_tags} />
      </div>
    </div>
  );
}
