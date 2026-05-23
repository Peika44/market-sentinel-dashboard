import type { UrgencySettingsDraft } from "../types";

interface UrgencySettingsModalProps {
  draft: UrgencySettingsDraft;
  onChange: (next: UrgencySettingsDraft) => void;
  onClose: () => void;
  onSave: () => void;
  saving: boolean;
}

export function UrgencySettingsModal({
  draft,
  onChange,
  onClose,
  onSave,
  saving,
}: UrgencySettingsModalProps) {
  function field<K extends keyof UrgencySettingsDraft>(key: K) {
    return (event: React.ChangeEvent<HTMLInputElement>) =>
      onChange({ ...draft, [key]: Number.parseFloat(event.target.value || "0") });
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
            <p className="eyebrow">Urgency Formula</p>
            <h2>Ranking Settings</h2>
            <p className="detail-name">
              Tune the dashboard ranking model without changing code.
            </p>
          </div>
          <button className="modal-close-button" onClick={onClose}>
            Close
          </button>
        </div>

        <div className="trade-plan-grid">
          <label>
            Price Weight %
            <input type="number" value={draft.priceWeightPct} onChange={field("priceWeightPct")} />
          </label>
          <label>
            Sentiment Weight %
            <input type="number" value={draft.sentimentWeightPct} onChange={field("sentimentWeightPct")} />
          </label>
          <label>
            Price Move Scale
            <input type="number" value={draft.priceMoveScale} onChange={field("priceMoveScale")} />
          </label>
          <label>
            Low Threshold
            <input type="number" value={draft.lowThreshold} onChange={field("lowThreshold")} />
          </label>
          <label>
            High Threshold
            <input type="number" value={draft.highThreshold} onChange={field("highThreshold")} />
          </label>
        </div>

        <div className="trade-plan-actions">
          <button className="refresh-button" onClick={onSave} disabled={saving}>
            {saving ? "Saving..." : "Save Formula"}
          </button>
        </div>
      </div>
    </div>
  );
}
