import type {
  AlertRuleDraft,
  AlertTaskStatus,
  StockCard,
  StoredAlertRule,
  StoredJournalEntry,
  StoredTickerNote,
  StoredTriggeredAlert,
  ThesisOutcomeSummary,
  StoredTradePlanDraft,
  TickerNoteDraft,
  TradePlanDraft,
} from "../types";
import { formatChangePct, formatCurrency, formatAlertCondition } from "../utils/format";
import { Sparkline, UrgencyBar } from "./Sparkline";

interface DetailPanelProps {
  selected: StockCard | null;
  savedDrafts: StoredTradePlanDraft[];
  groupedAlerts: Array<{ ticker: string; rules: StoredAlertRule[] }>;
  triggeredAlerts: StoredTriggeredAlert[];
  savedJournalEntries: StoredJournalEntry[];
  thesisOutcomeSummary: ThesisOutcomeSummary | null;
  tickerNote: StoredTickerNote | null;
  editingNote: TickerNoteDraft | null;
  savingTickerNote: boolean;
  hasMoreAlerts: boolean;
  hasMoreJournal: boolean;
  onShowChart: () => void;
  onTradePlan: () => void;
  onAlertRule: () => void;
  onJournal: () => void;
  onRetryBootstrap: () => void;
  retryingBootstrap: boolean;
  onTickerNoteChange: (next: TickerNoteDraft) => void;
  onSaveTickerNote: () => void;
  onLoadDraft: (draft: TradePlanDraft) => void;
  onEditAlertRule: (rule: StoredAlertRule) => void;
  onToggleAlertRule: (ruleId: string, enabled: boolean) => void;
  onDeleteAlertRule: (ruleId: string) => void;
  onLoadMoreAlerts: () => void;
  onLoadMoreJournal: () => void;
  onUpdateAlertTask: (alertId: string, status: AlertTaskStatus, snoozedUntil?: string) => void;
}

// ─── Alert Task Card ────────────────────────────────────────────────────────

function resolvedTaskStatus(alert: StoredTriggeredAlert): AlertTaskStatus {
  const status = alert.payload.task_status ?? "pending";
  if (status === "snoozed" && alert.payload.snoozed_until) {
    const expiry = new Date(alert.payload.snoozed_until).getTime();
    if (Date.now() >= expiry) return "pending";
  }
  return status;
}

interface AlertTaskListProps {
  triggeredAlerts: StoredTriggeredAlert[];
  hasMoreAlerts: boolean;
  onShowChart: () => void;
  onTradePlan: () => void;
  onLoadMoreAlerts: () => void;
  onUpdateAlertTask: (alertId: string, status: AlertTaskStatus, snoozedUntil?: string) => void;
}

function AlertTaskList({
  triggeredAlerts,
  hasMoreAlerts,
  onShowChart,
  onTradePlan,
  onLoadMoreAlerts,
  onUpdateAlertTask,
}: AlertTaskListProps) {
  const active = triggeredAlerts.filter((a) => resolvedTaskStatus(a) !== "dismissed");
  const dismissedCount = triggeredAlerts.length - active.length;

  function snooze15min(alertId: string) {
    const until = new Date(Date.now() + 15 * 60 * 1000).toISOString();
    onUpdateAlertTask(alertId, "snoozed", until);
  }

  return (
    <div className="saved-drafts-panel">
      <div className="alert-task-header">
        <p className="eyebrow">Alert Tasks</p>
        {dismissedCount > 0 && (
          <span className="alert-dismissed-count">{dismissedCount} dismissed</span>
        )}
      </div>
      {active.length === 0 ? (
        <p className="draft-empty-state">No active alert tasks.</p>
      ) : (
        <div className="saved-drafts-list">
          {active.map((alert) => {
            const status = resolvedTaskStatus(alert);
            const alertId = alert.payload.alert_id;
            const isLegacy = !alertId;
            const isSnoozed = status === "snoozed";
            const isActed = status === "acted";
            const isPending = status === "pending";

            const triggeredTime = new Date(alert.triggered_at);
            const timeLabel = triggeredTime.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
            const snoozedUntilLabel = isSnoozed && alert.payload.snoozed_until
              ? new Date(alert.payload.snoozed_until).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
              : null;

            return (
              <div
                key={`${alert.ticker}-${alert.triggered_at}`}
                className={`alert-task-card ${isSnoozed ? "snoozed" : ""} ${isActed ? "acted" : ""}`}
              >
                <div className="alert-task-top">
                  <div className="triggered-alert-header">
                    <span className="triggered-alert-badge">
                      {formatAlertCondition(alert.payload.condition)}
                    </span>
                    <span className="triggered-alert-time">{timeLabel}</span>
                  </div>
                  {isPending && (
                    <span className="alert-task-status-pill pending">Needs action</span>
                  )}
                  {isSnoozed && snoozedUntilLabel && (
                    <span className="alert-task-status-pill snoozed">Snoozed until {snoozedUntilLabel}</span>
                  )}
                  {isActed && (
                    <span className="alert-task-status-pill acted">Acted on</span>
                  )}
                </div>

                <p className="alert-task-message">{alert.payload.message}</p>

                {(alert.payload.snapshot_price != null ||
                  alert.payload.snapshot_change_pct != null ||
                  alert.payload.snapshot_volume != null) && (
                  <div className="alert-task-snapshot">
                    {alert.payload.snapshot_price != null && (
                      <span>@ ${alert.payload.snapshot_price.toFixed(2)}</span>
                    )}
                    {alert.payload.snapshot_change_pct != null && (
                      <span
                        className={alert.payload.snapshot_change_pct >= 0 ? "positive" : "negative"}
                      >
                        {alert.payload.snapshot_change_pct >= 0 ? "+" : ""}
                        {alert.payload.snapshot_change_pct.toFixed(2)}%
                      </span>
                    )}
                    {alert.payload.snapshot_volume != null && (
                      <span>Vol {(alert.payload.snapshot_volume / 1_000_000).toFixed(1)}M</span>
                    )}
                  </div>
                )}

                {!isLegacy && isPending && (
                  <div className="alert-task-actions">
                    <button
                      className="alert-action-btn primary"
                      onClick={() => {
                        onShowChart();
                        onUpdateAlertTask(alertId, "acted");
                      }}
                    >
                      Chart
                    </button>
                    <button
                      className="alert-action-btn primary"
                      onClick={() => {
                        onTradePlan();
                        onUpdateAlertTask(alertId, "acted");
                      }}
                    >
                      Build Plan
                    </button>
                    <button
                      className="alert-action-btn"
                      onClick={() => snooze15min(alertId)}
                    >
                      +15 min
                    </button>
                    <button
                      className="alert-action-btn dismiss"
                      onClick={() => onUpdateAlertTask(alertId, "dismissed")}
                    >
                      Dismiss
                    </button>
                  </div>
                )}
                {isLegacy && (
                  <div className="alert-task-actions">
                    <button className="alert-action-btn primary" onClick={onShowChart}>Chart</button>
                    <button className="alert-action-btn primary" onClick={onTradePlan}>Build Plan</button>
                  </div>
                )}
              </div>
            );
          })}
          {hasMoreAlerts && (
            <button className="ghost-button load-more-button" onClick={onLoadMoreAlerts}>
              Load more
            </button>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Main Panel ─────────────────────────────────────────────────────────────

export function DetailPanel({
  selected,
  savedDrafts,
  groupedAlerts,
  triggeredAlerts,
  savedJournalEntries,
  thesisOutcomeSummary,
  tickerNote,
  editingNote,
  savingTickerNote,
  hasMoreAlerts,
  hasMoreJournal,
  onShowChart,
  onTradePlan,
  onAlertRule,
  onJournal,
  onRetryBootstrap,
  retryingBootstrap,
  onTickerNoteChange,
  onSaveTickerNote,
  onLoadDraft,
  onEditAlertRule,
  onToggleAlertRule,
  onDeleteAlertRule,
  onLoadMoreAlerts,
  onLoadMoreJournal,
  onUpdateAlertTask,
}: DetailPanelProps) {
  if (!selected) {
    return (
      <div className="empty-panel">
        <h2>No tracked tickers yet</h2>
        <p>Add a symbol to the watchlist to populate the dashboard.</p>
      </div>
    );
  }

  const isLive = selected.data_status === "live";
  const isDelayed = selected.data_status === "delayed";
  const hasHistory = selected.history.length > 0;
  const hasUsablePrice = selected.current_price != null;

  return (
    <>
      <p className="eyebrow">Selected Position</p>
      <h2>{selected.ticker}</h2>
      <p className="detail-name">{selected.display_name}</p>
      {!isLive ? (
        <p className={`detail-status-banner ${isDelayed ? "delayed" : ""}`}>
          {selected.data_status_message ?? "Subscribed. Waiting for first market update."}
        </p>
      ) : null}
      <p className="detail-meta">
        {!isLive && !isDelayed
          ? "Price, change, and alert seeds will unlock after the first live tick arrives."
          : isDelayed
          ? `Feed ${selected.data_feed ?? "market"} is available in delayed mode until a live stream tick arrives.`
          : selected.volume > 0
          ? `${selected.volume.toLocaleString("en-US")} shares in latest update`
          : "Market overview selection"}
      </p>

      <div className="detail-metrics">
        <div>
          <span>Last Price</span>
          <strong>{hasUsablePrice ? formatCurrency(selected.current_price) : "Waiting…"}</strong>
        </div>
        <div>
          <span>Daily Change</span>
          <strong
            className={
              hasUsablePrice
                ? selected.change_pct != null && selected.change_pct >= 0
                  ? "change-up"
                  : "change-down"
                : "change-pending"
            }
          >
            {hasUsablePrice ? formatChangePct(selected.change_pct) : "Waiting…"}
          </strong>
        </div>
        <div>
          <span>Sentiment</span>
          <strong>{hasHistory ? selected.sentiment_label : "Pending"}</strong>
        </div>
        <div>
          <span>Urgency</span>
          <strong>{hasUsablePrice ? selected.urgency_score.toFixed(0) : "Pending"}</strong>
          {hasUsablePrice ? <UrgencyBar score={selected.urgency_score} /> : null}
        </div>
      </div>

      <div className="detail-chart">
        <Sparkline points={selected.history} />
      </div>

      <div className="detail-actions">
        <button className="refresh-button" onClick={onShowChart} disabled={!hasHistory}>
          View Chart
        </button>
        <button className="ghost-button" onClick={onTradePlan} disabled={!hasUsablePrice}>
          Trade Plan
        </button>
        <button className="ghost-button" onClick={onAlertRule} disabled={!hasUsablePrice}>
          Alert Rule
        </button>
        <button className="ghost-button" onClick={onJournal}>
          Journal
        </button>
        {!isLive ? (
          <button className="ghost-button" onClick={onRetryBootstrap} disabled={retryingBootstrap}>
            {retryingBootstrap ? "Retrying…" : "Retry Bootstrap"}
          </button>
        ) : null}
      </div>

      <div className="saved-drafts-panel">
        <p className="eyebrow">Ticker Notes</p>
        {editingNote ? (
          <div className="ticker-note-panel">
            <label>
              <span>Strategy Tag</span>
              <input
                value={editingNote.strategyTag}
                onChange={(event) =>
                  onTickerNoteChange({ ...editingNote, strategyTag: event.target.value })
                }
                placeholder="e.g. Breakout, Pullback, Swing"
              />
            </label>
            <label>
              <span>Thesis</span>
              <textarea
                value={editingNote.thesis}
                onChange={(event) =>
                  onTickerNoteChange({ ...editingNote, thesis: event.target.value })
                }
                placeholder="Why is this ticker on your board?"
              />
            </label>
            <label>
              <span>Notes</span>
              <textarea
                value={editingNote.notes}
                onChange={(event) =>
                  onTickerNoteChange({ ...editingNote, notes: event.target.value })
                }
                placeholder="Catalysts, risk factors, levels, or reminders"
              />
            </label>
            <div className="inline-action-row">
              <button className="ghost-button" onClick={onSaveTickerNote} disabled={savingTickerNote}>
                {savingTickerNote ? "Saving…" : "Save Notes"}
              </button>
              {tickerNote?.updated_at ? (
                <span className="triggered-alert-time">
                  Updated {new Date(tickerNote.updated_at).toLocaleString()}
                </span>
              ) : (
                <span className="triggered-alert-time">No saved note yet.</span>
              )}
            </div>
          </div>
        ) : (
          <p className="draft-empty-state">Select a ticker to load notes.</p>
        )}
      </div>

      <div className="saved-drafts-panel">
        <p className="eyebrow">Thesis vs Outcome</p>
        {thesisOutcomeSummary ? (
          <div className="thesis-summary-grid">
            <div className="saved-draft-item">
              <strong>Current Thesis</strong>
              <span>{thesisOutcomeSummary.current_thesis || "No thesis saved yet."}</span>
              <span className="triggered-alert-time">
                {thesisOutcomeSummary.strategy_tag
                  ? `Strategy: ${thesisOutcomeSummary.strategy_tag}`
                  : "No strategy tag assigned."}
              </span>
            </div>
            <div className="saved-draft-item">
              <strong>Latest Outcome</strong>
              <span>{thesisOutcomeSummary.latest_outcome || "No closed trade outcome yet."}</span>
              <span className="triggered-alert-time">
                Tag: {thesisOutcomeSummary.latest_outcome_tag}
              </span>
              {thesisOutcomeSummary.latest_review ? <span>{thesisOutcomeSummary.latest_review}</span> : null}
            </div>
            <div className="saved-draft-item">
              <strong>Closed Setups</strong>
              <span>{thesisOutcomeSummary.total_closed_entries}</span>
              <span className="triggered-alert-time">
                Wins {thesisOutcomeSummary.win_count} · Losses {thesisOutcomeSummary.loss_count} · Scratch {thesisOutcomeSummary.scratch_count}
              </span>
            </div>
          </div>
        ) : (
          <p className="draft-empty-state">Select a ticker to load thesis/outcome history.</p>
        )}
      </div>

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
                onClick={() => onLoadDraft(draft.payload)}
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
        {groupedAlerts.length === 0 ? (
          <p className="draft-empty-state">No saved alert rules yet.</p>
        ) : (
          <div className="saved-drafts-list">
            {groupedAlerts.slice(0, 4).map((group) => (
              <div key={group.ticker} className="saved-draft-item">
                <div className="triggered-alert-header">
                  <strong>{group.ticker}</strong>
                  <span className="triggered-alert-badge">{group.rules.length} rules</span>
                </div>
                <div className="grouped-alert-list">
                  {group.rules.map((rule) => (
                    <div key={rule.rule_id} className="grouped-alert-row">
                      <div>
                        <span>
                          {formatAlertCondition(rule.payload.condition)} · {rule.payload.threshold}
                        </span>
                        <span className="triggered-alert-time">
                          {new Date(rule.updated_at).toLocaleString()}
                        </span>
                      </div>
                      <div className="inline-action-row">
                        <button
                          className="ghost-button"
                          onClick={() => onEditAlertRule(rule)}
                        >
                          Edit
                        </button>
                        <button
                          className="ghost-button"
                          onClick={() => onToggleAlertRule(rule.rule_id, !rule.payload.enabled)}
                        >
                          {rule.payload.enabled ? "Disable" : "Enable"}
                        </button>
                        <button
                          className="ghost-button"
                          onClick={() => onDeleteAlertRule(rule.rule_id)}
                        >
                          Delete
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <AlertTaskList
        triggeredAlerts={triggeredAlerts}
        hasMoreAlerts={hasMoreAlerts}
        onShowChart={onShowChart}
        onTradePlan={onTradePlan}
        onLoadMoreAlerts={onLoadMoreAlerts}
        onUpdateAlertTask={onUpdateAlertTask}
      />

      <div className="saved-drafts-panel">
        <p className="eyebrow">Recent Journal Entries</p>
        {savedJournalEntries.length === 0 ? (
          <p className="draft-empty-state">No journal entries yet.</p>
        ) : (
          <div className="saved-drafts-list">
            {savedJournalEntries.map((entry) => (
              <div key={entry.entry_id} className="saved-draft-item">
                <div className="triggered-alert-header">
                  <strong>{entry.ticker}</strong>
                  <span className="triggered-alert-badge">{entry.payload.stage}</span>
                </div>
                <span>{entry.payload.thesis}</span>
                {entry.payload.review ? <span>{entry.payload.review}</span> : null}
                {entry.payload.outcome ? <span>{entry.payload.outcome}</span> : null}
                <span className="triggered-alert-time">
                  {new Date(entry.updated_at).toLocaleString()}
                </span>
              </div>
            ))}
            {hasMoreJournal && (
              <button className="ghost-button load-more-button" onClick={onLoadMoreJournal}>
                Load more
              </button>
            )}
          </div>
        )}
      </div>
    </>
  );
}

// re-export for convenience
export type { AlertRuleDraft, StoredAlertRule, TradePlanDraft };
