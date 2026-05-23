export function Sparkline({ points }: { points: number[] }) {
  if (points.length < 2) {
    return <div className="chart-empty">—</div>;
  }

  const min = Math.min(...points);
  const max = Math.max(...points);
  const spread = max - min || 1;

  const coords = points.map((point, index) => ({
    x: (index / (points.length - 1)) * 100,
    y: 100 - ((point - min) / spread) * 100,
  }));

  const isUp = points[points.length - 1] >= points[0];
  const strokeColor = isUp ? "#8ff0b8" : "#ff9f9f";
  const gradId = isUp ? "spk-grad-up" : "spk-grad-down";

  const linePoints = coords.map(({ x, y }) => `${x},${y}`).join(" ");
  const areaPath =
    `M ${coords[0].x},100 ` +
    coords.map(({ x, y }) => `L ${x},${y}`).join(" ") +
    ` L ${coords[coords.length - 1].x},100 Z`;

  return (
    <svg className="sparkline" viewBox="0 0 100 100" preserveAspectRatio="none">
      <defs>
        <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={strokeColor} stopOpacity="0.28" />
          <stop offset="100%" stopColor={strokeColor} stopOpacity="0.02" />
        </linearGradient>
      </defs>
      <path fill={`url(#${gradId})`} d={areaPath} />
      <polyline fill="none" stroke={strokeColor} strokeWidth="2.5" points={linePoints} />
    </svg>
  );
}

export function UrgencyBar({ score }: { score: number }) {
  const pct = Math.min(100, Math.max(0, score));
  const color = pct >= 70 ? "#ff7171" : pct >= 40 ? "#f7ba59" : "#48d691";
  return (
    <div className="urgency-bar-track">
      <div className="urgency-bar-fill" style={{ width: `${pct}%`, background: color }} />
    </div>
  );
}
