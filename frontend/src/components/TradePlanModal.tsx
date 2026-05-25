import { useState } from "react";
import type { AlertRuleDraft, JournalEntryDraft, SetupType, TradeChecklist, TradePlanDraft } from "../types";
import { DEFAULT_CHECKLIST } from "../types";

const LS_ACCOUNT_SIZE = "msd:account-size";
const LS_MAX_POSITION_PCT = "msd:max-position-pct";

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

const SETUP_CONFIGS: Record<
  SetupType,
  { label: string; guidance: string; catalystRequired?: boolean }
> = {
  breakout: {
    label: "Breakout",
    guidance:
      "Entry above a consolidation zone or resistance level. Requires volume expansion on the break. Stop sits below the breakout base.",
  },
  pullback: {
    label: "Pullback",
    guidance:
      "Entry on a retrace to a key level (support, VWAP, 20MA) within an uptrend. Volume should taper on the pullback and expand on resumption.",
  },
  mean_reversion: {
    label: "Mean Reversion",
    guidance:
      "Entry on an overextended move away from a mean (VWAP, 20MA). Confirm stretched conditions and identify a clear reversion target before entry.",
  },
  trend_continuation: {
    label: "Trend Continuation",
    guidance:
      "Entry on a flag, wedge, or orderly pause within an established trend. The trend structure must remain intact at entry. Tighten stops on failures.",
  },
  event_driven: {
    label: "Event-Driven",
    guidance:
      "Entry tied to a specific catalyst — earnings, macro event, or news release. Define your max loss before the event fires. Binary risk.",
    catalystRequired: true,
  },
};

const SETUP_TYPES: SetupType[] = [
  "breakout",
  "pullback",
  "mean_reversion",
  "trend_continuation",
  "event_driven",
];

interface ChecklistItem {
  key: keyof TradeChecklist;
  label: string;
  help: string;
}

const CHECKLIST_ITEMS: ChecklistItem[] = [
  {
    key: "hasCatalyst",
    label: "Has catalyst",
    help: "A known event or fundamental reason drives the move.",
  },
  {
    key: "atKeyLevel",
    label: "At key level",
    help: "Entry is near a meaningful support, resistance, VWAP, or moving average.",
  },
  {
    key: "rrSufficient",
    label: "R/R \u2265 2:1",
    help: "The reward-to-risk ratio is at least 2 to 1 based on your levels.",
  },
  {
    key: "marketAligned",
    label: "Market aligned",
    help: "SPY / QQQ are not in a strong opposing trend relative to this setup.",
  },
  {
    key: "withinSession",
    label: "Allowed session",
    help: "Entry falls within your preferred trading window (e.g., 9:30–11:00 ET).",
  },
];

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
  const setupType: SetupType = draft.setupType ?? "breakout";
  const checklist: TradeChecklist = draft.checklist ?? { ...DEFAULT_CHECKLIST };
  const config = SETUP_CONFIGS[setupType];

  const [accountSize, setAccountSizeRaw] = useState(
    () => localStorage.getItem(LS_ACCOUNT_SIZE) ?? ""
  );
  const [maxPositionPct, setMaxPositionPctRaw] = useState(
    () => localStorage.getItem(LS_MAX_POSITION_PCT) ?? "25"
  );
  function setAccountSize(v: string) {
    localStorage.setItem(LS_ACCOUNT_SIZE, v);
    setAccountSizeRaw(v);
  }
  function setMaxPositionPct(v: string) {
    localStorage.setItem(LS_MAX_POSITION_PCT, v);
    setMaxPositionPctRaw(v);
  }

  const entry = Number.parseFloat(draft.entryPrice);
  const stop = Number.parseFloat(draft.stopLoss);
  const target = Number.parseFloat(draft.targetPrice);
  const risk = Math.abs(entry - stop);
  const reward = Math.abs(target - entry);
  const rrRatio = risk > 0 ? reward / risk : 0;
  const rrLabel = risk > 0 ? `${rrRatio.toFixed(2)}R` : "—";
  const rrOk = rrRatio >= 2.0;

  const accountNum = parseFloat(accountSize.replace(/,/g, "")) || 0;
  const maxPct = parseFloat(maxPositionPct) || 25;
  const riskPctNum = parseFloat(draft.riskPercent) || 0;
  const dollarRisk = accountNum > 0 && riskPctNum > 0 ? accountNum * (riskPctNum / 100) : 0;
  const sharesCalc = risk > 0 && dollarRisk > 0 ? Math.floor(dollarRisk / risk) : 0;
  const positionValue = sharesCalc * (entry || 0);
  const positionPct = accountNum > 0 && positionValue > 0 ? (positionValue / accountNum) * 100 : 0;
  const sizerReady = accountNum > 0 && riskPctNum > 0 && risk > 0;
  const positionWarn = sizerReady && positionPct > maxPct;

  const checkCount = Object.values(checklist).filter(Boolean).length;
  const totalChecks = CHECKLIST_ITEMS.length;

  function field<K extends keyof TradePlanDraft>(key: K) {
    return (event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
      onChange({ ...draft, [key]: event.target.value });
  }

  function setSetup(next: SetupType) {
    onChange({ ...draft, setupType: next });
  }

  function toggleCheck(key: keyof TradeChecklist) {
    onChange({
      ...draft,
      checklist: { ...checklist, [key]: !checklist[key] },
    });
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
            <p className="eyebrow">Trade Setup</p>
            <h2>{draft.ticker}</h2>
            <p className="detail-name">
              Define the setup type, key levels, and pre-trade checklist before committing.
            </p>
          </div>
          <button className="modal-close-button" onClick={onClose}>
            Close
          </button>
        </div>

        {/* Setup type selector */}
        <div className="setup-type-section">
          <p className="setup-type-label">Setup Type</p>
          <div className="setup-type-group">
            {SETUP_TYPES.map((type) => (
              <button
                key={type}
                className={`setup-type-btn ${setupType === type ? "active" : ""}`}
                onClick={() => setSetup(type)}
              >
                {SETUP_CONFIGS[type].label}
              </button>
            ))}
          </div>
          <p className="setup-guidance">{config.guidance}</p>
        </div>

        {/* Price inputs */}
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
          <label className="trade-plan-wide">
            Thesis
            <textarea value={draft.thesis} onChange={field("thesis")} />
          </label>
        </div>

        {/* Position Sizer */}
        <div className="position-sizer">
          <div className="sizer-header">
            <p className="eyebrow">Position Sizer</p>
            <div className="sizer-inputs">
              <label>
                <span>Account ($)</span>
                <input
                  className="sizer-input"
                  value={accountSize}
                  onChange={(e) => setAccountSize(e.target.value)}
                  placeholder="50000"
                />
              </label>
              <label>
                <span>Max Position (%)</span>
                <input
                  className="sizer-input sizer-input-narrow"
                  value={maxPositionPct}
                  onChange={(e) => setMaxPositionPct(e.target.value)}
                  placeholder="25"
                />
              </label>
            </div>
          </div>
          <div className="sizer-grid">
            <div className="sizer-cell">
              <span>Dollar Risk</span>
              <strong>{sizerReady ? `$${dollarRisk.toFixed(0)}` : "—"}</strong>
            </div>
            <div className="sizer-cell">
              <span>Risk / Share</span>
              <strong>{risk > 0 ? `$${risk.toFixed(2)}` : "—"}</strong>
            </div>
            <div className="sizer-cell">
              <span>Shares</span>
              <strong>{sizerReady && sharesCalc > 0 ? sharesCalc.toLocaleString() : "—"}</strong>
            </div>
            <div className="sizer-cell">
              <span>Position Value</span>
              <strong>
                {sizerReady && positionValue > 0
                  ? `$${positionValue.toLocaleString(undefined, { maximumFractionDigits: 0 })}`
                  : "—"}
              </strong>
            </div>
            <div className={`sizer-cell ${positionWarn ? "sizer-warn" : ""}`}>
              <span>% of Account</span>
              <strong>
                {sizerReady && positionPct > 0 ? `${positionPct.toFixed(1)}%` : "—"}
                {positionWarn ? " ⚠" : ""}
              </strong>
            </div>
          </div>
          {positionWarn && (
            <p className="sizer-warn-msg">
              Position exceeds {maxPct}% of account. Reduce size or widen stop.
            </p>
          )}
        </div>

        {/* Checklist */}
        <div className="setup-checklist">
          <div className="setup-checklist-header">
            <p className="eyebrow">Pre-Trade Checklist</p>
            <span
              className={`checklist-score ${checkCount === totalChecks ? "complete" : checkCount >= 3 ? "partial" : "low"}`}
            >
              {checkCount}/{totalChecks}
            </span>
          </div>
          <div className="checklist-items">
            {CHECKLIST_ITEMS.map((item) => {
              const checked = checklist[item.key];
              const isCritical =
                item.key === "hasCatalyst" && config.catalystRequired;
              return (
                <button
                  key={item.key}
                  className={`checklist-row ${checked ? "checked" : ""} ${isCritical && !checked ? "critical" : ""}`}
                  onClick={() => toggleCheck(item.key)}
                >
                  <span className="checklist-box">{checked ? "✓" : ""}</span>
                  <span className="checklist-text">
                    <span className="checklist-label">
                      {item.label}
                      {item.key === "rrSufficient" && risk > 0 && (
                        <span className={`rr-calc ${rrOk ? "ok" : "warn"}`}>
                          {" "}({rrLabel})
                        </span>
                      )}
                    </span>
                    <span className="checklist-help">{item.help}</span>
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Summary */}
        <div className="trade-plan-summary">
          <div>
            <span>Risk / Reward</span>
            <strong className={rrOk ? "rr-ok" : undefined}>{rrLabel}</strong>
          </div>
          <div>
            <span>Checklist</span>
            <strong>
              {checkCount === totalChecks
                ? "All checks passed"
                : `${totalChecks - checkCount} item${totalChecks - checkCount !== 1 ? "s" : ""} remaining`}
            </strong>
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
            Open Journal
          </button>
          <button className="ghost-button" onClick={onCreateBothAlerts} disabled={savingAlertRule}>
            {savingAlertRule ? "Creating..." : "Both Alerts"}
          </button>
        </div>
      </div>
    </div>
  );
}

// Suppress unused-import warnings for types used only in prop interfaces
export type { AlertRuleDraft, JournalEntryDraft };
