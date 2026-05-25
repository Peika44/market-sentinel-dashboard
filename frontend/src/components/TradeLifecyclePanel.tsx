import { useEffect, useState } from "react";
import type {
  SetupType,
  StoredCatalystEvent,
  StoredTrade,
  TradeDraft,
  TradeStage,
} from "../types";
import type { StockCard } from "../types";

const LS_ACCOUNT_SIZE = "msd:account-size";

// ─── Constants ───────────────────────────────────────────────────────────────

const STAGES: TradeStage[] = [
  "idea",
  "planned",
  "armed",
  "entered",
  "exited",
  "reviewed",
];

const STAGE_LABELS: Record<TradeStage, string> = {
  idea: "Idea",
  planned: "Planned",
  armed: "Armed",
  entered: "Entered",
  exited: "Exited",
  reviewed: "Reviewed",
};

const STAGE_PROMPTS: Record<TradeStage, string> = {
  idea: "What makes this ticker interesting right now? Note the initial edge and thesis.",
  planned: "Define entry, stop, and target. Record why this plan is valid.",
  armed: "What specific trigger or alert are you waiting for before entering?",
  entered: "Record your actual fill price and any execution context.",
  exited: "Record your exit price and outcome. What happened?",
  reviewed: "Post-trade review: what worked, what didn't, what you'd do differently.",
};

const NEXT_STAGE: Partial<Record<TradeStage, TradeStage>> = {
  idea: "planned",
  planned: "armed",
  armed: "entered",
  entered: "exited",
  exited: "reviewed",
};

const SETUP_LABELS: Record<SetupType, string> = {
  breakout: "Breakout",
  pullback: "Pullback",
  mean_reversion: "Mean Rev",
  trend_continuation: "Trend Cont.",
  event_driven: "Event-Driven",
};

const SETUP_TYPES: SetupType[] = [
  "breakout",
  "pullback",
  "mean_reversion",
  "trend_continuation",
  "event_driven",
];

const OUTCOME_LABELS: Record<string, string> = {
  open: "Open",
  win: "Win",
  loss: "Loss",
  scratch: "Scratch",
};

const MISTAKE_TAGS: { tag: string; label: string }[] = [
  { tag: "entry_too_early", label: "Entry Too Early" },
  { tag: "held_too_long", label: "Held Too Long" },
  { tag: "ignored_stop", label: "Ignored Stop" },
  { tag: "oversized", label: "Oversized" },
  { tag: "chased", label: "Chased" },
  { tag: "no_catalyst", label: "No Catalyst" },
  { tag: "market_not_aligned", label: "Market Not Aligned" },
  { tag: "fomo", label: "FOMO" },
  { tag: "overtraded", label: "Overtraded" },
];

// ─── Helpers ─────────────────────────────────────────────────────────────────

function buildEmptyTrade(ticker = ""): TradeDraft {
  const now = new Date().toISOString();
  return {
    ticker: ticker.toUpperCase(),
    setupType: "breakout",
    stage: "idea",
    stageNotes: {},
    stageTimestamps: { idea: now },
    entryPrice: "",
    stopLoss: "",
    targetPrice: "",
    riskPercent: "",
    actualEntry: "",
    actualExit: "",
    outcomeTag: "open",
  };
}

function stageColor(stage: TradeStage): string {
  const map: Record<TradeStage, string> = {
    idea: "stage-idea",
    planned: "stage-planned",
    armed: "stage-armed",
    entered: "stage-entered",
    exited: "stage-exited",
    reviewed: "stage-reviewed",
  };
  return map[stage];
}

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

// ─── Stage Stepper ────────────────────────────────────────────────────────────

function StageStepper({
  stage,
  onSetStage,
}: {
  stage: TradeStage;
  onSetStage: (s: TradeStage) => void;
}) {
  const currentIdx = STAGES.indexOf(stage);
  return (
    <div className="stage-stepper">
      {STAGES.map((s, idx) => {
        const isPast = idx < currentIdx;
        const isCurrent = idx === currentIdx;
        return (
          <div
            key={s}
            className={`stage-step ${isPast ? "past" : isCurrent ? "current" : "future"}`}
          >
            <button
              className="stage-dot"
              title={`Go to ${STAGE_LABELS[s]}`}
              onClick={() => onSetStage(s)}
            />
            <span className="stage-step-label">{STAGE_LABELS[s]}</span>
          </div>
        );
      })}
    </div>
  );
}

// ─── P&L Summary ──────────────────────────────────────────────────────────────

function PnlSummary({ trade }: { trade: TradeDraft }) {
  const plannedEntry = parseFloat(trade.entryPrice);
  const plannedStop = parseFloat(trade.stopLoss);
  const actualEntry = parseFloat(trade.actualEntry);
  const actualExit = parseFloat(trade.actualExit);

  const planRisk = Math.abs(plannedEntry - plannedStop);
  if (!planRisk || !trade.actualEntry || !trade.actualExit || isNaN(actualEntry) || isNaN(actualExit)) {
    return null;
  }

  const actualR = (actualExit - actualEntry) / planRisk;

  const accountNum = parseFloat((localStorage.getItem(LS_ACCOUNT_SIZE) ?? "").replace(/,/g, "")) || 0;
  const riskPctNum = parseFloat(trade.riskPercent) || 0;
  const dollarRisk = accountNum > 0 && riskPctNum > 0 ? accountNum * (riskPctNum / 100) : 0;
  const sharesCalc = dollarRisk > 0 ? Math.floor(dollarRisk / planRisk) : 0;
  const dollarPnL = sharesCalc > 0 ? sharesCalc * (actualExit - actualEntry) : null;

  return (
    <div className="pnl-summary">
      <p className="stage-section-label" style={{ marginTop: 12 }}>Actual P&L</p>
      <div className="pnl-grid">
        <div className="pnl-cell">
          <span>Actual R</span>
          <strong className={actualR > 0 ? "pnl-positive" : actualR < 0 ? "pnl-negative" : ""}>
            {actualR >= 0 ? "+" : ""}{actualR.toFixed(2)}R
          </strong>
        </div>
        <div className="pnl-cell">
          <span>Plan Risk / Share</span>
          <strong>${planRisk.toFixed(2)}</strong>
        </div>
        {sharesCalc > 0 && (
          <div className="pnl-cell">
            <span>Shares</span>
            <strong>{sharesCalc.toLocaleString()}</strong>
          </div>
        )}
        {dollarPnL !== null && (
          <div className="pnl-cell">
            <span>Dollar P&L</span>
            <strong className={dollarPnL > 0 ? "pnl-positive" : dollarPnL < 0 ? "pnl-negative" : ""}>
              {dollarPnL >= 0 ? "+" : "-"}${Math.abs(dollarPnL).toLocaleString(undefined, { maximumFractionDigits: 0 })}
            </strong>
          </div>
        )}
      </div>
      {accountNum === 0 && (
        <p className="pnl-hint">Set account size in Trade Plan to see shares and dollar P&L.</p>
      )}
    </div>
  );
}

// ─── Stage Content ────────────────────────────────────────────────────────────

function StageContent({
  trade,
  catalystCount,
  onChange,
}: {
  trade: TradeDraft;
  catalystCount: number;
  onChange: (next: TradeDraft) => void;
}) {
  const note = trade.stageNotes[trade.stage] ?? "";

  function setNote(text: string) {
    onChange({ ...trade, stageNotes: { ...trade.stageNotes, [trade.stage]: text } });
  }

  const entry = parseFloat(trade.entryPrice);
  const stop = parseFloat(trade.stopLoss);
  const target = parseFloat(trade.targetPrice);
  const risk = Math.abs(entry - stop);
  const reward = Math.abs(target - entry);
  const rrLabel = risk > 0 ? `${(reward / risk).toFixed(2)}R` : "—";
  const rrOk = risk > 0 && reward / risk >= 2;

  return (
    <div className="stage-content">
      {trade.stage === "idea" && (
        <>
          <p className="stage-section-label">Setup Type</p>
          <div className="setup-type-group">
            {SETUP_TYPES.map((type) => (
              <button
                key={type}
                className={`setup-type-btn ${trade.setupType === type ? "active" : ""}`}
                onClick={() => onChange({ ...trade, setupType: type })}
              >
                {SETUP_LABELS[type]}
              </button>
            ))}
          </div>
        </>
      )}

      {trade.stage === "planned" && (
        <>
          <p className="stage-section-label">Key Levels</p>
          <div className="stage-levels-grid">
            <label>
              Entry
              <input
                value={trade.entryPrice}
                onChange={(e) => onChange({ ...trade, entryPrice: e.target.value })}
                placeholder="e.g. 187.50"
              />
            </label>
            <label>
              Stop Loss
              <input
                value={trade.stopLoss}
                onChange={(e) => onChange({ ...trade, stopLoss: e.target.value })}
                placeholder="e.g. 182.00"
              />
            </label>
            <label>
              Target
              <input
                value={trade.targetPrice}
                onChange={(e) => onChange({ ...trade, targetPrice: e.target.value })}
                placeholder="e.g. 198.00"
              />
            </label>
            <label>
              Risk %
              <input
                value={trade.riskPercent}
                onChange={(e) => onChange({ ...trade, riskPercent: e.target.value })}
                placeholder="e.g. 1.0"
              />
            </label>
            <div className={`stage-rr-badge ${rrOk ? "ok" : risk > 0 ? "warn" : ""}`}>
              <span>R / R</span>
              <strong>{rrLabel}</strong>
            </div>
          </div>
        </>
      )}

      {trade.stage === "armed" && catalystCount > 0 && (
        <p className="stage-context-line">
          {catalystCount} catalyst event{catalystCount !== 1 ? "s" : ""} saved for this ticker.
        </p>
      )}

      {trade.stage === "entered" && (
        <>
          <p className="stage-section-label">Actual Entry</p>
          <input
            className="stage-single-input"
            value={trade.actualEntry}
            onChange={(e) => onChange({ ...trade, actualEntry: e.target.value })}
            placeholder="e.g. 187.80"
          />
        </>
      )}

      {trade.stage === "exited" && (
        <>
          <p className="stage-section-label">Actual Exit</p>
          <div className="stage-exit-row">
            <input
              className="stage-single-input"
              value={trade.actualExit}
              onChange={(e) => onChange({ ...trade, actualExit: e.target.value })}
              placeholder="e.g. 196.40"
            />
            <div className="outcome-selector">
              {(["win", "loss", "scratch"] as const).map((tag) => (
                <button
                  key={tag}
                  className={`outcome-btn ${tag} ${trade.outcomeTag === tag ? "active" : ""}`}
                  onClick={() => onChange({ ...trade, outcomeTag: tag })}
                >
                  {OUTCOME_LABELS[tag]}
                </button>
              ))}
            </div>
          </div>
        </>
      )}

      {trade.stage === "reviewed" && (
        <>
          <p className="stage-section-label" style={{ marginTop: 12 }}>
            Mistake Tags
          </p>
          <div className="mistake-tag-grid">
            {MISTAKE_TAGS.map(({ tag, label }) => {
              const active = (trade.mistakeTags ?? []).includes(tag);
              return (
                <button
                  key={tag}
                  className={`mistake-tag-btn ${active ? "active" : ""}`}
                  onClick={() => {
                    const current = trade.mistakeTags ?? [];
                    const next = active
                      ? current.filter((t) => t !== tag)
                      : [...current, tag];
                    onChange({ ...trade, mistakeTags: next });
                  }}
                >
                  {label}
                </button>
              );
            })}
          </div>
        </>
      )}

      {(trade.stage === "exited" || trade.stage === "reviewed") && (
        <PnlSummary trade={trade} />
      )}

      <p className="stage-section-label" style={{ marginTop: trade.stage === "idea" ? 16 : 12 }}>
        {STAGE_LABELS[trade.stage]} Note
      </p>
      <textarea
        className="stage-note-textarea"
        value={note}
        onChange={(e) => setNote(e.target.value)}
        placeholder={STAGE_PROMPTS[trade.stage]}
        rows={4}
      />
    </div>
  );
}

// ─── Stage History ────────────────────────────────────────────────────────────

function StageHistory({ trade }: { trade: TradeDraft }) {
  const completedStages = STAGES.filter((s) => {
    const idx = STAGES.indexOf(s);
    const currentIdx = STAGES.indexOf(trade.stage);
    return idx < currentIdx && (trade.stageNotes[s] || trade.stageTimestamps[s]);
  });

  if (completedStages.length === 0) return null;

  return (
    <div className="stage-history">
      <p className="eyebrow">Stage History</p>
      {completedStages.map((s) => (
        <div key={s} className="stage-history-entry">
          <div className="stage-history-header">
            <span className={`stage-pill ${stageColor(s)}`}>{STAGE_LABELS[s]}</span>
            {trade.stageTimestamps[s] && (
              <span className="triggered-alert-time">
                {new Date(trade.stageTimestamps[s]!).toLocaleString([], {
                  month: "short",
                  day: "numeric",
                  hour: "2-digit",
                  minute: "2-digit",
                })}
              </span>
            )}
          </div>
          {s === "planned" && (trade.entryPrice || trade.stopLoss || trade.targetPrice) && (
            <p className="stage-history-levels">
              Entry {trade.entryPrice || "—"} · Stop {trade.stopLoss || "—"} · Target{" "}
              {trade.targetPrice || "—"}
            </p>
          )}
          {s === "entered" && trade.actualEntry && (
            <p className="stage-history-levels">Fill @ {trade.actualEntry}</p>
          )}
          {s === "exited" && (trade.actualExit || trade.outcomeTag !== "open") && (
            <p className="stage-history-levels">
              Exit @ {trade.actualExit || "—"} ·{" "}
              <span className={`outcome-inline ${trade.outcomeTag}`}>
                {OUTCOME_LABELS[trade.outcomeTag]}
              </span>
            </p>
          )}
          {trade.stageNotes[s] && (
            <p className="stage-history-note">{trade.stageNotes[s]}</p>
          )}
        </div>
      ))}
    </div>
  );
}

// ─── Trade Detail ─────────────────────────────────────────────────────────────

function TradeDetail({
  trade,
  catalystEvents,
  onSave,
  onDelete,
  onBack,
}: {
  trade: TradeDraft;
  catalystEvents: StoredCatalystEvent[];
  onSave: (t: TradeDraft) => Promise<void>;
  onDelete: () => Promise<void>;
  onBack: () => void;
}) {
  const [editing, setEditing] = useState<TradeDraft>(trade);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setEditing(trade);
  }, [trade.tradeId]);

  const catalystCount = catalystEvents.filter(
    (e) => e.payload.scope === "ticker" && e.ticker === editing.ticker,
  ).length;

  const nextStage = NEXT_STAGE[editing.stage];

  async function save(draft: TradeDraft) {
    setSaving(true);
    try {
      await onSave(draft);
      setEditing(draft);
    } finally {
      setSaving(false);
    }
  }

  async function advance() {
    if (!nextStage) return;
    const now = new Date().toISOString();
    const next: TradeDraft = {
      ...editing,
      stage: nextStage,
      stageTimestamps: { ...editing.stageTimestamps, [nextStage]: now },
    };
    await save(next);
  }

  return (
    <div className="trade-detail-panel">
      <div className="trade-detail-header">
        <div>
          <p className="eyebrow">Trade Setup</p>
          <h3>
            {editing.ticker}{" "}
            <span className={`stage-pill ${stageColor(editing.stage)}`}>
              {STAGE_LABELS[editing.stage]}
            </span>
          </h3>
          <p className="detail-meta">{SETUP_LABELS[editing.setupType]}</p>
        </div>
        <div className="trade-detail-actions-top">
          <button className="ghost-button" onClick={onBack}>
            ← Back
          </button>
          <button
            className="ghost-button"
            onClick={() => void onDelete()}
          >
            Delete
          </button>
        </div>
      </div>

      <StageStepper
        stage={editing.stage}
        onSetStage={(s) => {
          const now = new Date().toISOString();
          const updated: TradeDraft = {
            ...editing,
            stage: s,
            stageTimestamps: editing.stageTimestamps[s]
              ? editing.stageTimestamps
              : { ...editing.stageTimestamps, [s]: now },
          };
          setEditing(updated);
        }}
      />

      <StageContent
        trade={editing}
        catalystCount={catalystCount}
        onChange={setEditing}
      />

      <div className="trade-detail-actions">
        <button
          className="refresh-button"
          onClick={() => void save(editing)}
          disabled={saving}
        >
          {saving ? "Saving…" : "Save"}
        </button>
        {nextStage && (
          <button
            className="ghost-button advance-btn"
            onClick={() => void advance()}
            disabled={saving}
          >
            Advance → {STAGE_LABELS[nextStage]}
          </button>
        )}
        {editing.stage === "reviewed" && (
          <span className="trade-complete-label">Trade complete</span>
        )}
      </div>

      <StageHistory trade={editing} />
    </div>
  );
}

// ─── New Trade Form ───────────────────────────────────────────────────────────

function NewTradeForm({
  stocks,
  onSave,
  onCancel,
}: {
  stocks: StockCard[];
  onSave: (t: TradeDraft) => Promise<void>;
  onCancel: () => void;
}) {
  const [draft, setDraft] = useState<TradeDraft>(buildEmptyTrade());
  const [saving, setSaving] = useState(false);

  async function submit() {
    if (!draft.ticker.trim()) return;
    setSaving(true);
    try {
      await onSave(draft);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="trade-new-form panel-card">
      <p className="eyebrow">New Trade</p>
      <h3>Start a trade lifecycle</h3>

      <div className="trade-new-fields">
        <label>
          Ticker
          <input
            value={draft.ticker}
            onChange={(e) => setDraft({ ...draft, ticker: e.target.value.toUpperCase() })}
            placeholder="e.g. AAPL"
            list="trade-ticker-list"
          />
          <datalist id="trade-ticker-list">
            {stocks.map((s) => (
              <option key={s.ticker} value={s.ticker}>
                {s.display_name}
              </option>
            ))}
          </datalist>
        </label>

        <label>
          Setup Type
          <div className="setup-type-group" style={{ marginTop: 6 }}>
            {SETUP_TYPES.map((type) => (
              <button
                key={type}
                className={`setup-type-btn ${draft.setupType === type ? "active" : ""}`}
                onClick={() => setDraft({ ...draft, setupType: type })}
              >
                {SETUP_LABELS[type]}
              </button>
            ))}
          </div>
        </label>

        <label>
          Initial Note
          <textarea
            value={draft.stageNotes.idea ?? ""}
            onChange={(e) =>
              setDraft({ ...draft, stageNotes: { ...draft.stageNotes, idea: e.target.value } })
            }
            placeholder={STAGE_PROMPTS.idea}
            rows={3}
          />
        </label>
      </div>

      <div className="trade-plan-actions">
        <button
          className="refresh-button"
          onClick={() => void submit()}
          disabled={saving || !draft.ticker.trim()}
        >
          {saving ? "Creating…" : "Create Trade"}
        </button>
        <button className="ghost-button" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </div>
  );
}

// ─── Trade List Item ──────────────────────────────────────────────────────────

function TradeListItem({
  trade,
  selected,
  onClick,
}: {
  trade: StoredTrade;
  selected: boolean;
  onClick: () => void;
}) {
  const ts = trade.payload.stageTimestamps[trade.payload.stage];
  return (
    <button
      className={`workspace-stock-item trade-list-item ${selected ? "selected-list-item" : ""}`}
      onClick={onClick}
    >
      <div className="triggered-alert-header">
        <strong>{trade.ticker}</strong>
        <span className={`stage-pill ${stageColor(trade.payload.stage)}`}>
          {STAGE_LABELS[trade.payload.stage]}
        </span>
      </div>
      <span className="detail-meta">{SETUP_LABELS[trade.payload.setupType]}</span>
      {ts && <span className="triggered-alert-time">{relativeTime(ts)}</span>}
    </button>
  );
}

// ─── Main Panel ───────────────────────────────────────────────────────────────

interface TradeLifecyclePanelProps {
  trades: StoredTrade[];
  stocks: StockCard[];
  catalystEvents: StoredCatalystEvent[];
  onSave: (trade: TradeDraft) => Promise<void>;
  onDelete: (tradeId: string) => Promise<void>;
}

export function TradeLifecyclePanel({
  trades,
  stocks,
  catalystEvents,
  onSave,
  onDelete,
}: TradeLifecyclePanelProps) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [showNew, setShowNew] = useState(false);

  const selectedTrade = trades.find((t) => t.trade_id === selectedId) ?? null;

  const activeTrades = trades.filter(
    (t) => !["exited", "reviewed"].includes(t.payload.stage),
  );
  const completedTrades = trades.filter((t) =>
    ["exited", "reviewed"].includes(t.payload.stage),
  );

  async function handleSave(draft: TradeDraft) {
    await onSave(draft);
    if (!selectedId && draft.tradeId) setSelectedId(draft.tradeId);
  }

  async function handleDelete(tradeId: string) {
    await onDelete(tradeId);
    setSelectedId(null);
  }

  async function handleNewSave(draft: TradeDraft) {
    await onSave(draft);
    setShowNew(false);
    // selectedId will be updated after trades reloads and tradeId is assigned by backend
  }

  return (
    <div className="workspace-layout">
      {/* Sidebar */}
      <aside className="workspace-side panel-card">
        <div className="compact-card-header">
          <div>
            <p className="eyebrow">Active</p>
            <h3>{activeTrades.length} trade{activeTrades.length !== 1 ? "s" : ""}</h3>
          </div>
          <button
            className="refresh-button"
            style={{ padding: "6px 12px", fontSize: "0.8rem" }}
            onClick={() => {
              setShowNew(true);
              setSelectedId(null);
            }}
          >
            + New
          </button>
        </div>
        <div className="workspace-stock-list">
          {activeTrades.length === 0 ? (
            <p className="draft-empty-state">No active trades.</p>
          ) : (
            activeTrades.map((t) => (
              <TradeListItem
                key={t.trade_id}
                trade={t}
                selected={selectedId === t.trade_id}
                onClick={() => {
                  setSelectedId(t.trade_id);
                  setShowNew(false);
                }}
              />
            ))
          )}
        </div>

        {completedTrades.length > 0 && (
          <>
            <div className="compact-card-header" style={{ marginTop: 16 }}>
              <div>
                <p className="eyebrow">Completed</p>
                <h3>{completedTrades.length}</h3>
              </div>
            </div>
            <div className="workspace-stock-list">
              {completedTrades.map((t) => (
                <TradeListItem
                  key={t.trade_id}
                  trade={t}
                  selected={selectedId === t.trade_id}
                  onClick={() => {
                    setSelectedId(t.trade_id);
                    setShowNew(false);
                  }}
                />
              ))}
            </div>
          </>
        )}
      </aside>

      {/* Main */}
      <div className="workspace-main">
        {showNew ? (
          <NewTradeForm
            stocks={stocks}
            onSave={handleNewSave}
            onCancel={() => setShowNew(false)}
          />
        ) : selectedTrade ? (
          <TradeDetail
            key={selectedTrade.trade_id}
            trade={selectedTrade.payload}
            catalystEvents={catalystEvents}
            onSave={handleSave}
            onDelete={() => handleDelete(selectedTrade.trade_id)}
            onBack={() => setSelectedId(null)}
          />
        ) : (
          <div className="panel-card" style={{ padding: 32, textAlign: "center" }}>
            <p className="eyebrow">Get Started</p>
            <h3 style={{ margin: "8px 0 12px" }}>No trade selected</h3>
            <p className="draft-empty-state" style={{ marginBottom: 16 }}>
              Select a trade from the list or create a new one to track its lifecycle from idea to review.
            </p>
            <button
              className="refresh-button"
              onClick={() => setShowNew(true)}
            >
              + New Trade
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
