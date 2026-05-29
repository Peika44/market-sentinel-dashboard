import type { AlertRuleDraft } from "../types";
import { alertThresholdHelp } from "../utils/format";

interface AlertRuleModalProps {
  draft: AlertRuleDraft;
  onChange: (next: AlertRuleDraft) => void;
  onClose: () => void;
  onSave: () => void;
  savingAlertRule: boolean;
  validationError: string | null;
}

export function AlertRuleModal({
  draft,
  onChange,
  onClose,
  onSave,
  savingAlertRule,
  validationError,
}: AlertRuleModalProps) {
  function field<K extends keyof AlertRuleDraft>(key: K) {
    return (event: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
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
            <p className="eyebrow">Alert Rule</p>
            <h2>{draft.ticker}</h2>
            <p className="detail-name">
              Minimal alert configuration to start building a decision-support loop.
            </p>
          </div>
          <button className="modal-close-button" onClick={onClose}>
            Close
          </button>
        </div>

        <div className="trade-plan-grid">
          <label>
            Condition
            <select
              value={draft.condition}
              onChange={(event) => {
                onChange({ ...draft, condition: event.target.value });
              }}
            >
              <option value="urgency_above">Urgency Above</option>
              <option value="price_change_above">Price Change Above %</option>
              <option value="price_change_below">Price Change Below %</option>
              <option value="gap_up_above">Gap Up Above %</option>
              <option value="gap_down_below">Gap Down Below %</option>
              <option value="volume_above">Volume Above</option>
              <option value="target_hit">Target Hit</option>
              <option value="drop_below_stop">Drop Below Stop</option>
              <option value="breakout_above_recent_high">Breakout Above Recent High</option>
              <option value="breakdown_below_recent_low">Breakdown Below Recent Low</option>
            </select>
          </label>
          <label>
            Threshold
            <input value={draft.threshold} onChange={field("threshold")} />
            <small className="field-help">{alertThresholdHelp(draft.condition)}</small>
          </label>
          <label>
            Cooldown Minutes
            <input value={draft.cooldownMinutes} onChange={field("cooldownMinutes")} />
          </label>
          <label>
            Channel
            <select
              value={draft.channel}
              onChange={(e) => onChange({ ...draft, channel: e.target.value })}
            >
              <option value="log">Log only</option>
              <option value="discord">Discord</option>
            </select>
          </label>
        </div>

        {validationError ? <p className="validation-error">{validationError}</p> : null}

        <div className="trade-plan-actions">
          <button className="refresh-button" onClick={onSave} disabled={savingAlertRule}>
            {savingAlertRule ? "Saving..." : "Save Alert Rule"}
          </button>
        </div>
      </div>
    </div>
  );
}
