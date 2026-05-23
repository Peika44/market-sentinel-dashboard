import type {
  AlertRuleDraft,
  StockCard,
  StoredAlertRule,
  StoredJournalEntry,
  StoredTriggeredAlert,
  StoredTradePlanDraft,
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
  hasMoreAlerts: boolean;
  hasMoreJournal: boolean;
  onShowChart: () => void;
  onTradePlan: () => void;
  onAlertRule: () => void;
  onJournal: () => void;
  onLoadDraft: (draft: TradePlanDraft) => void;
  onEditAlertRule: (rule: StoredAlertRule) => void;
  onToggleAlertRule: (ruleId: string, enabled: boolean) => void;
  onDeleteAlertRule: (ruleId: string) => void;
  onLoadMoreAlerts: () => void;
  onLoadMoreJournal: () => void;
}

export function DetailPanel({
  selected,
  savedDrafts,
  groupedAlerts,
  triggeredAlerts,
  savedJournalEntries,
  hasMoreAlerts,
  hasMoreJournal,
  onShowChart,
  onTradePlan,
  onAlertRule,
  onJournal,
  onLoadDraft,
  onEditAlertRule,
  onToggleAlertRule,
  onDeleteAlertRule,
  onLoadMoreAlerts,
  onLoadMoreJournal,
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
  const hasHistory = selected.history.length > 0;

  return (
    <>
      <p className="eyebrow">Selected Position</p>
      <h2>{selected.ticker}</h2>
      <p className="detail-name">{selected.display_name}</p>
      {!isLive ? <p className="detail-status-banner">Subscribed. Waiting for first market update.</p> : null}
      <p className="detail-meta">
        {!isLive
          ? "Price, change, and alert seeds will unlock after the first live tick arrives."
          : selected.volume > 0
          ? `${selected.volume.toLocaleString("en-US")} shares in latest update`
          : "Market overview selection"}
      </p>

      <div className="detail-metrics">
        <div>
          <span>Last Price</span>
          <strong>{isLive ? formatCurrency(selected.current_price) : "Waiting…"}</strong>
        </div>
        <div>
          <span>Daily Change</span>
          <strong
            className={
              isLive
                ? selected.change_pct != null && selected.change_pct >= 0
                  ? "change-up"
                  : "change-down"
                : "change-pending"
            }
          >
            {isLive ? formatChangePct(selected.change_pct) : "Waiting…"}
          </strong>
        </div>
        <div>
          <span>Sentiment</span>
          <strong>{hasHistory ? selected.sentiment_label : "Pending"}</strong>
        </div>
        <div>
          <span>Urgency</span>
          <strong>{isLive ? selected.urgency_score.toFixed(0) : "Pending"}</strong>
          {isLive ? <UrgencyBar score={selected.urgency_score} /> : null}
        </div>
      </div>

      <div className="detail-chart">
        <Sparkline points={selected.history} />
      </div>

      <div className="detail-actions">
        <button className="refresh-button" onClick={onShowChart} disabled={!isLive || !hasHistory}>
          View Chart
        </button>
        <button className="ghost-button" onClick={onTradePlan} disabled={!isLive || selected.current_price == null}>
          Trade Plan
        </button>
        <button className="ghost-button" onClick={onAlertRule} disabled={!isLive || selected.current_price == null}>
          Alert Rule
        </button>
        <button className="ghost-button" onClick={onJournal}>
          Journal
        </button>
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

      <div className="saved-drafts-panel">
        <p className="eyebrow">Recent Triggered Alerts</p>
        {triggeredAlerts.length === 0 ? (
          <p className="draft-empty-state">No alerts have triggered yet.</p>
        ) : (
          <div className="saved-drafts-list">
            {triggeredAlerts.map((alert) => (
              <div
                key={`${alert.ticker}-${alert.triggered_at}-${alert.payload.condition}`}
                className="saved-draft-item"
              >
                <div className="triggered-alert-header">
                  <strong>{alert.ticker}</strong>
                  <span className="triggered-alert-badge">
                    {formatAlertCondition(alert.payload.condition)}
                  </span>
                </div>
                <span>{alert.payload.message}</span>
                <span className="triggered-alert-time">
                  {new Date(alert.triggered_at).toLocaleString()}
                </span>
              </div>
            ))}
            {hasMoreAlerts && (
              <button className="ghost-button load-more-button" onClick={onLoadMoreAlerts}>
                Load more
              </button>
            )}
          </div>
        )}
      </div>

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
