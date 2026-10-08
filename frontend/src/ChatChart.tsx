import { Donut } from "./components";

export interface ChartSpec {
  chart_type: "bar" | "line" | "donut";
  title: string;
  x_label?: string;
  y_label?: string;
  series: { name?: string; points: { label: string; value: number }[] }[];
}

const PALETTE = [
  "var(--series-1)", "var(--series-2)", "var(--series-7)",
  "var(--series-4)", "var(--series-6)", "var(--warning)", "var(--good)",
];

const fmt = (v: number) => (Number.isInteger(v) ? String(v) : v.toFixed(1));

function BarChart({ spec }: { spec: ChartSpec }) {
  const pts = spec.series[0]?.points ?? [];
  const max = Math.max(1, ...pts.map((p) => Math.abs(p.value)));
  return (
    <div className="cc-bars">
      {pts.map((p, i) => (
        <div className="cc-row" key={i}>
          <span className="cc-name" title={p.label}>{p.label}</span>
          <span className="cc-track">
            <span className="cc-fill" style={{ width: `${(Math.abs(p.value) / max) * 100}%`, background: PALETTE[i % PALETTE.length] }} />
          </span>
          <span className="cc-val">{fmt(p.value)}</span>
        </div>
      ))}
    </div>
  );
}

function DonutChart({ spec }: { spec: ChartSpec }) {
  const pts = spec.series[0]?.points ?? [];
  const segments = pts.map((p, i) => ({ label: p.label, value: p.value, color: PALETTE[i % PALETTE.length] }));
  return <Donut segments={segments} size={120} />;
}

function LineChart({ spec }: { spec: ChartSpec }) {
  const series = spec.series.filter((s) => s.points.length);
  const labels = series[0]?.points.map((p) => p.label) ?? [];
  const vals = series.flatMap((s) => s.points.map((p) => p.value));
  const max = Math.max(...vals, 0);
  const min = Math.min(...vals, 0);
  const span = max - min || 1;
  const W = 360, H = 150, padL = 30, padB = 24, padT = 10, padR = 10;
  const n = labels.length;
  const x = (i: number) => padL + (n <= 1 ? (W - padL - padR) / 2 : (i * (W - padL - padR)) / (n - 1));
  const y = (v: number) => padT + (H - padT - padB) * (1 - (v - min) / span);

  return (
    <div className="cc-linewrap">
      <svg viewBox={`0 0 ${W} ${H}`} className="cc-line" preserveAspectRatio="xMidYMid meet">
        {/* baseline + max gridline */}
        <line x1={padL} y1={y(min)} x2={W - padR} y2={y(min)} className="cc-axis" />
        <line x1={padL} y1={y(max)} x2={W - padR} y2={y(max)} className="cc-grid" />
        <text x={padL - 5} y={y(max)} className="cc-tick" textAnchor="end" dominantBaseline="middle">{fmt(max)}</text>
        <text x={padL - 5} y={y(min)} className="cc-tick" textAnchor="end" dominantBaseline="middle">{fmt(min)}</text>
        {series.map((s, si) => {
          const color = PALETTE[si % PALETTE.length];
          const d = s.points.map((p, i) => `${i === 0 ? "M" : "L"} ${x(i)} ${y(p.value)}`).join(" ");
          return (
            <g key={si}>
              <path d={d} fill="none" stroke={color} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
              {s.points.map((p, i) => (
                <circle key={i} cx={x(i)} cy={y(p.value)} r={2.6} fill={color}><title>{p.label}: {fmt(p.value)}</title></circle>
              ))}
            </g>
          );
        })}
        {labels.map((l, i) => (
          <text key={i} x={x(i)} y={H - 7} className="cc-tick" textAnchor="middle">{l.length > 8 ? l.slice(0, 7) + "…" : l}</text>
        ))}
      </svg>
      {series.length > 1 && (
        <div className="cc-legend">
          {series.map((s, si) => (
            <span className="cc-leg" key={si}><span className="cc-dot" style={{ background: PALETTE[si % PALETTE.length] }} />{s.name || `Series ${si + 1}`}</span>
          ))}
        </div>
      )}
    </div>
  );
}

export function ChatChart({ spec }: { spec: ChartSpec }) {
  if (!spec.series.length) return null;
  return (
    <div className="chat-chart">
      {spec.title && <div className="cc-head">{spec.title}</div>}
      {spec.chart_type === "donut" ? <DonutChart spec={spec} />
        : spec.chart_type === "line" ? <LineChart spec={spec} />
          : <BarChart spec={spec} />}
    </div>
  );
}
