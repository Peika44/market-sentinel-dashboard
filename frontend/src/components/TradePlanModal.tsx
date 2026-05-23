import type { AlertRuleDraft, JournalEntryDraft, TradePlanDraft } from "../types";

interface TradePlanModalProps {
  draft: TradePlanDraft;
  onChange: (next: TradePlanDraft) => void;
  onClose: () => void;
  onSave: () => void;
  savingDraft: boolean;
  savingAlertRule: boolean;
  onCreateTargetAlert: () => void;
  onCreateStopAlert: () => void;
  onCreateBothAlerts: () => void;
  onOpenJournal: () => void;
}

export function TradePlanModal({
  draft,
  onChange,
  onClose,
  onSave,
  savingDraft,
  savingAlertRule,
  onCreateTargetAlert,
  onCreateStopAlert,
  onCreateBothAlerts,
  onOpenJournal,
}: TradePlanModalProps) {
  function field<K extends keyof TradePlanDraft>(key: K) {
    return (event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
      onChange({ ...draft, [key]: event.target.value });
  }

  const entry = Number.parseFloat(draft.entryPrice);
  const stop = Number.parseFloat(draft.stopLoss);
  const target = Number.parseFloat(draft.targetPrice);
  const risk = Math.abs(entry - stop);
  const reward = Math.abs(target - entry);
  const rrLabel = risk > 0 ? `${(reward / risk).toFixed(2)}R` : "—";

  return (
    <div
      className="modal-backdrop"
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div className="modal-card trade-plan-modal">
        <div className="modal-header">
          <div>
            <p className="eyebrow">Trade Plan Seed</p>
            <h2>{draft.ticker}</h2>
            <p className="detail-name">
              Lightweight workflow bridge from dashboard selection to an executable plan draft.
            </p>
          </div>
          <button className="modal-close-button" onClick={onClose}>
            Close
          </button>
        </div>

        <div className="trade-plan-grid">
          <label>
            Entry Price
            <input value={draft.entryPrice} onChange={field("entryPrice")} />
          </label>
          <label>
            Stop Loss
            <input value={draft.stopLoss} onChange={field("stopLoss")} />
          </label>
          <label>
            Target Price
            <input value={draft.targetPrice} onChange={field("targetPrice")} />
          </label>
          <label>
            Risk %
            <input value={draft.riskPercent} onChange={field("riskPercent")} />
          </label>
          <label>
            Position Size USD
            <input value={draft.positionSizeUsd} onChange={field("positionSizeUsd")} />
          </label>
          <label className="trade-plan-wide">
            Thesis
            <textarea value={draft.thesis} onChange={field("thesis")} />
          </label>
        </div>

        <div className="trade-plan-summary">
          <div>
            <span>Risk / Reward</span>
            <strong>{rrLabel}</strong>
          </div>
          <div>
            <span>Workflow Note</span>
            <strong>Use this draft as a handoff into a fuller trading workflow.</strong>
          </div>
        </div>

        <div className="trade-plan-actions">
          <button className="refresh-button" onClick={onSave} disabled={savingDraft}>
            {savingDraft ? "Saving..." : "Save Draft"}
          </button>
          <button className="ghost-button" onClick={onCreateTargetAlert}>
            Create Target Alert
          </button>
          <button className="ghost-button" onClick={onCreateStopAlert}>
            Create Stop Alert
          </button>
          <button className="ghost-button" onClick={onOpenJournal}>
            Open Journal Review
          </button>
          <button className="ghost-button" onClick={onCreateBothAlerts} disabled={savingAlertRule}>
            {savingAlertRule ? "Creating..." : "Create Both Alerts"}
          </button>
        </div>
      </div>
    </div>
  );
}

// Suppress unused-import warnings for types used only in prop interfaces
export type { AlertRuleDraft, JournalEntryDraft };
