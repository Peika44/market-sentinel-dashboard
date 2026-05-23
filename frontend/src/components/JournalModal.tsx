import type { JournalEntryDraft } from "../types";

interface JournalModalProps {
  draft: JournalEntryDraft;
  onChange: (next: JournalEntryDraft) => void;
  onClose: () => void;
  onSave: () => void;
  savingJournalEntry: boolean;
}

export function JournalModal({
  draft,
  onChange,
  onClose,
  onSave,
  savingJournalEntry,
}: JournalModalProps) {
  function field<K extends keyof JournalEntryDraft>(key: K) {
    return (event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
      onChange({ ...draft, [key]: event.target.value });
  }

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
            <p className="eyebrow">Trade Journal</p>
            <h2>{draft.ticker}</h2>
            <p className="detail-name">
              Record the current thesis, review notes, and outcome so the dashboard becomes a feedback loop.
            </p>
          </div>
          <button className="modal-close-button" onClick={onClose}>
            Close
          </button>
        </div>

        <div className="trade-plan-grid">
          <label>
            Stage
            <select value={draft.stage} onChange={field("stage")}>
              <option value="monitoring">Monitoring</option>
              <option value="entered">Entered</option>
              <option value="managed">Managed</option>
              <option value="closed">Closed</option>
            </select>
          </label>
          <label className="trade-plan-wide">
            Thesis
            <textarea value={draft.thesis} onChange={field("thesis")} />
          </label>
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
          <label className="trade-plan-wide">
            Review
            <textarea value={draft.review} onChange={field("review")} />
          </label>
          <label className="trade-plan-wide">
            Outcome
            <textarea value={draft.outcome} onChange={field("outcome")} />
          </label>
        </div>

        <div className="trade-plan-actions">
          <button className="refresh-button" onClick={onSave} disabled={savingJournalEntry}>
            {savingJournalEntry ? "Saving..." : "Save Journal Entry"}
          </button>
        </div>
      </div>
    </div>
  );
}
