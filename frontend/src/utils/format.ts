export function formatCurrency(value: number | null | undefined): string {
  if (value == null) {
    return "—";
  }
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  }).format(value);
}

export function formatChangePct(value: number | null | undefined): string {
  if (value == null) {
    return "—";
  }
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

export function formatVolume(volume: number): string {
  if (volume >= 1_000_000) return `${(volume / 1_000_000).toFixed(1)}M`;
  if (volume >= 1_000) return `${Math.round(volume / 1_000)}K`;
  return volume.toLocaleString("en-US");
}

export function formatAlertCondition(condition: string): string {
  return condition.replace(/_/g, " ").replace(/\b\w/g, (char: string) => char.toUpperCase());
}

export function alertThresholdHelp(condition: string): string {
  if (condition === "price_change_above" || condition === "price_change_below") {
    return "Threshold is a percent change value, e.g. 2 means 2%.";
  }
  if (condition === "gap_up_above" || condition === "gap_down_below") {
    return "Threshold is a gap percentage value, e.g. 3 means 3%.";
  }
  if (condition === "volume_above") {
    return "Threshold is a raw share volume number, e.g. 500000.";
  }
  if (condition === "target_hit" || condition === "drop_below_stop") {
    return "Threshold is a price level, e.g. 465 or 438.";
  }
  if (
    condition === "breakout_above_recent_high" ||
    condition === "breakdown_below_recent_low"
  ) {
    return "Threshold is a price buffer added to recent high/low. Use 0 for an exact level break, or 0.10 / 0.25 for confirmation.";
  }
  return "Threshold meaning depends on the selected condition.";
}
