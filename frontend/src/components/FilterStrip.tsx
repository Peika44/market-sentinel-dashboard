import { useState } from "react";
import type { BoardFilters, SavedFilterPreset, TradeFilters } from "../types";

interface ChipOption<T extends string> {
  v: T;
  l: string;
}

function ChipGroup<T extends string>({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: ChipOption<T>[];
  value: T;
  onChange: (v: T) => void;
}) {
  return (
    <div className="filter-chip-group">
      <span className="filter-chip-label">{label}</span>
      {options.map((opt) => (
        <button
          key={opt.v}
          className={`filter-chip ${value === opt.v ? "active" : ""} ${
            opt.v === "live" && value === opt.v ? "status-live" : ""
          }`}
          onClick={() => onChange(opt.v)}
        >
          {opt.l}
        </button>
      ))}
    </div>
  );
}

const SETUP_OPTIONS: ChipOption<BoardFilters["status"] | "all">[] = [
  { v: "all", l: "All" },
  { v: "live", l: "Live" },
  { v: "delayed", l: "Delayed" },
  { v: "waiting", l: "Waiting" },
];

const URGENCY_OPTIONS: ChipOption<BoardFilters["minUrgency"]>[] = [
  { v: "any", l: "Any" },
  { v: "watch", l: "Watch" },
  { v: "hot", l: "Hot" },
];

const TRADE_SETUP_OPTIONS: ChipOption<TradeFilters["setupType"]>[] = [
  { v: "all", l: "All" },
  { v: "breakout", l: "Breakout" },
  { v: "pullback", l: "Pullback" },
  { v: "mean_reversion", l: "Mean Rev" },
  { v: "trend_continuation", l: "Trend Cont." },
  { v: "event_driven", l: "Event-Driven" },
];

const STAGE_OPTIONS: ChipOption<TradeFilters["stage"]>[] = [
  { v: "all", l: "All" },
  { v: "idea", l: "Idea" },
  { v: "planned", l: "Planned" },
  { v: "armed", l: "Armed" },
  { v: "entered", l: "Entered" },
  { v: "exited", l: "Exited" },
  { v: "reviewed", l: "Reviewed" },
];

const OUTCOME_OPTIONS: ChipOption<TradeFilters["outcomeTag"]>[] = [
  { v: "all", l: "All" },
  { v: "open", l: "Open" },
  { v: "win", l: "Win" },
  { v: "loss", l: "Loss" },
  { v: "scratch", l: "Scratch" },
];

interface FilterStripProps {
  view: "board" | "trades";
  boardFilters?: BoardFilters;
  onBoardFilters?: (f: BoardFilters) => void;
  tradeFilters?: TradeFilters;
  onTradeFilters?: (f: TradeFilters) => void;
  presets: SavedFilterPreset[];
  onSavePreset: (name: string) => void;
  onDeletePreset: (id: string) => void;
  onApplyPreset: (preset: SavedFilterPreset) => void;
  filteredCount: number;
  totalCount: number;
}

export function FilterStrip({
  view,
  boardFilters,
  onBoardFilters,
  tradeFilters,
  onTradeFilters,
  presets,
  onSavePreset,
  onDeletePreset,
  onApplyPreset,
  filteredCount,
  totalCount,
}: FilterStripProps) {
  const [showSaveInput, setShowSaveInput] = useState(false);
  const [savingName, setSavingName] = useState("");

  function handleSave() {
    const name = savingName.trim();
    if (!name) return;
    onSavePreset(name);
    setSavingName("");
    setShowSaveInput(false);
  }

  const isFiltered = filteredCount !== totalCount;

  return (
    <div className="filter-strip">
      <div className="preset-row">
        {presets.map((preset) => (
          <span key={preset.id} className="preset-chip" onClick={() => onApplyPreset(preset)}>
            {preset.name}
            <button
              className="preset-chip-delete"
              onClick={(e) => {
                e.stopPropagation();
                onDeletePreset(preset.id);
              }}
            >
              ✕
            </button>
          </span>
        ))}
        {showSaveInput ? (
          <>
            <input
              className="filter-save-input"
              value={savingName}
              onChange={(e) => setSavingName(e.target.value)}
              placeholder="Preset name…"
              onKeyDown={(e) => {
                if (e.key === "Enter") handleSave();
                if (e.key === "Escape") { setShowSaveInput(false); setSavingName(""); }
              }}
              autoFocus
            />
            <button className="filter-save-btn" onClick={handleSave}>OK</button>
            <button className="filter-save-btn" onClick={() => { setShowSaveInput(false); setSavingName(""); }}>Cancel</button>
          </>
        ) : (
          <button className="filter-save-btn" onClick={() => setShowSaveInput(true)}>Save</button>
        )}
        {isFiltered ? (
          <span className="filter-count filtered">{filteredCount} of {totalCount}</span>
        ) : (
          <span className="filter-count">{totalCount}</span>
        )}
      </div>

      {view === "board" && boardFilters && onBoardFilters ? (
        <div className="filter-row">
          <ChipGroup
            label="Status"
            options={SETUP_OPTIONS as ChipOption<BoardFilters["status"]>[]}
            value={boardFilters.status}
            onChange={(v) => onBoardFilters({ ...boardFilters, status: v })}
          />
          <ChipGroup
            label="Urgency"
            options={URGENCY_OPTIONS}
            value={boardFilters.minUrgency}
            onChange={(v) => onBoardFilters({ ...boardFilters, minUrgency: v })}
          />
          <div className="filter-chip-group">
            <span className="filter-chip-label">Catalyst</span>
            <button
              className={`filter-chip ${boardFilters.hasCatalyst ? "active" : ""}`}
              onClick={() => onBoardFilters({ ...boardFilters, hasCatalyst: !boardFilters.hasCatalyst })}
            >
              Has Catalyst
            </button>
          </div>
        </div>
      ) : null}

      {view === "trades" && tradeFilters && onTradeFilters ? (
        <div className="filter-row">
          <ChipGroup
            label="Setup"
            options={TRADE_SETUP_OPTIONS}
            value={tradeFilters.setupType}
            onChange={(v) => onTradeFilters({ ...tradeFilters, setupType: v })}
          />
          <ChipGroup
            label="Stage"
            options={STAGE_OPTIONS}
            value={tradeFilters.stage}
            onChange={(v) => onTradeFilters({ ...tradeFilters, stage: v })}
          />
          <ChipGroup
            label="Outcome"
            options={OUTCOME_OPTIONS}
            value={tradeFilters.outcomeTag}
            onChange={(v) => onTradeFilters({ ...tradeFilters, outcomeTag: v })}
          />
        </div>
      ) : null}
    </div>
  );
}
