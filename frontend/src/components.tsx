import { useEffect, useMemo, useState } from "react";
import { IcAlert, IcCheck, IcClose, IcDot, IcFunnel } from "./icons";

/** Centered popup dialog over a dimmed scrim. Closes on the X, scrim click, Esc. */
export function Modal({
  title, subtitle, icon, onClose, children,
}: {
  title: string; subtitle?: string; icon?: React.ReactNode;
  onClose: () => void; children: React.ReactNode;
}) {
  useEffect(() => {
    const h = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [onClose]);
  return (
    <div className="scrim" onClick={onClose}>
      <div className="modal" role="dialog" aria-modal="true" aria-label={title} onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <div className="modal-titles">
            <h2>{icon && <span className="ic">{icon}</span>}{title}</h2>
            {subtitle && <p>{subtitle}</p>}
          </div>
          <button className="btn sm ghost modal-x" onClick={onClose} aria-label="Close"><IcClose size={16} /></button>
        </div>
        <div className="modal-body">{children}</div>
      </div>
    </div>
  );
}

/** Map engine Status / risk level to a reserved status-palette class.
   Handles both short codes and the workbook's full labels
   (e.g. "Amber - Attention Required", "Red - Immediate", "Critical"). */
export function statusClass(s: string): string {
  const v = (s || "").toLowerCase();
  if (v.startsWith("green") || v === "low" || v === "balanced" || v === "slack" || v === "healthy")
    return "good";
  if (v.startsWith("amber") || v === "medium" || v === "at risk")
    return "warning";
  if (v.startsWith("red") || v === "high" || v === "overloaded" || v === "critical")
    return "critical";
  return "warning";
}

/** Shorten the workbook's verbose status labels for compact chips. */
function shortLabel(s: string): string {
  if (/^(amber|red|green)/i.test(s)) return s.split(/\s*-\s*/)[0];
  return s;
}

/** Status chip = color + ICON + label (never color alone — accessibility). */
export function Chip({ status, label }: { status: string; label?: string }) {
  const cls = statusClass(status);
  const Ic = cls === "good" ? IcCheck : cls === "warning" ? IcDot : IcAlert;
  return (
    <span className={`chip ${cls}`}>
      <span className="ic"><Ic size={12} /></span>
      {label ?? shortLabel(status)}
    </span>
  );
}

export function StatTile({
  value,
  label,
  status,
  icon,
}: {
  value: React.ReactNode;
  label: string;
  status?: string;
  icon?: React.ReactNode;
}) {
  const cls = status ? statusClass(status) : "";
  return (
    <div className={`tile ${cls}`}>
      {icon && <div className="ic-wrap">{icon}</div>}
      <div className="body">
        <div className="flex between">
          <div className="value">{value}</div>
          {status && <Chip status={status} />}
        </div>
        <div className="label">{label}</div>
      </div>
    </div>
  );
}

/** Horizontal bars with an optional threshold marker. One hue; magnitude by length. */
export function BarRow({
  name,
  value,
  max,
  display,
  color,
  thresholdPct,
}: {
  name: string;
  value: number;
  max: number;
  display: string;
  color: string;
  thresholdPct?: number;
}) {
  const pct = max > 0 ? Math.min((value / max) * 100, 100) : 0;
  return (
    <div className="bar-row">
      <span className="name" title={name}>{name}</span>
      <div className="bar-track">
        <div className="bar-fill" style={{ width: `${pct}%`, background: color }} />
        {thresholdPct != null && (
          <div className="bar-threshold" style={{ left: `${Math.min(thresholdPct, 100)}%` }} />
        )}
      </div>
      <span className="num">{display}</span>
    </div>
  );
}

/** Semicircle health gauge: green/amber/red arc + animated needle, big number. */
export function Gauge({ value, status }: { value: number; status: string }) {
  const r = 70;
  const cx = 90;
  const cy = 90;
  const toXY = (frac: number) => {
    const a = Math.PI * (1 - frac);
    return [cx + r * Math.cos(a), cy - r * Math.sin(a)];
  };
  const arc = (from: number, to: number, color: string, dim = false) => {
    const [x1, y1] = toXY(from);
    const [x2, y2] = toXY(to);
    const large = to - from > 0.5 ? 1 : 0;
    return (
      <path
        d={`M ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2}`}
        stroke={color}
        strokeWidth={13}
        fill="none"
        strokeLinecap="round"
        opacity={dim ? 0.28 : 1}
      />
    );
  };
  const frac = Math.max(0, Math.min(1, value / 100));
  const [nx, ny] = toXY(frac);
  const active = statusClass(status);
  return (
    <div className="gauge-wrap">
      <svg width={180} height={104} viewBox="0 0 180 104" aria-label={`Health ${value} of 100`}>
        {/* track arcs, dimmed; active segment drawn bright */}
        {arc(0, 0.5, "var(--critical)", active !== "critical")}
        {arc(0.5, 0.75, "var(--warning)", active !== "warning")}
        {arc(0.75, 1, "var(--good)", active !== "good")}
        <g className="gauge-sweep">
          <line x1={cx} y1={cy} x2={nx} y2={ny} stroke="var(--text-primary)" strokeWidth={3} strokeLinecap="round" />
          <circle cx={cx} cy={cy} r={6} fill="var(--surface-1)" stroke="var(--text-primary)" strokeWidth={2.5} />
        </g>
      </svg>
      <div>
        <div className="gauge-num">{value}</div>
        <div style={{ marginTop: 6 }}><Chip status={status} /></div>
      </div>
    </div>
  );
}

/** Donut chart (inline SVG, no deps). Segments drawn as stroked arcs; center
    shows the total. Legend lists each segment with its count. */
export function Donut({
  segments, label, size = 148, onSliceClick,
}: {
  segments: { label: string; value: number; color: string }[];
  label?: string;
  size?: number;
  onSliceClick?: (label: string) => void;
}) {
  const sum = segments.reduce((s, x) => s + x.value, 0);
  const stroke = 18;
  const cx = size / 2;
  const R = cx - stroke / 2 - 2;
  const C = 2 * Math.PI * R;
  let off = 0;
  const clickable = !!onSliceClick;
  const click = (lbl: string) => (e: React.MouseEvent) => { e.stopPropagation(); onSliceClick?.(lbl); };
  return (
    <div className="donut">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label={`${label ?? "total"} ${sum}`}>
        <g transform={`rotate(-90 ${cx} ${cx})`}>
          <circle cx={cx} cy={cx} r={R} fill="none" stroke="var(--surface-3)" strokeWidth={stroke} />
          {segments.map((s, i) => {
            const frac = sum > 0 ? s.value / sum : 0;
            const len = frac * C;
            const seg = (
              <circle key={i} cx={cx} cy={cx} r={R} fill="none" stroke={s.color} strokeWidth={stroke}
                strokeDasharray={`${Math.max(len - 1.5, 0)} ${C - Math.max(len - 1.5, 0)}`} strokeDashoffset={-off}
                className={`donut-seg ${clickable ? "clickable" : ""}`}
                onClick={clickable ? click(s.label) : undefined}>
                <title>{s.label}: {s.value}</title>
              </circle>
            );
            off += len;
            return seg;
          })}
        </g>
        <text x="50%" y="48%" textAnchor="middle" dominantBaseline="middle" className="donut-num">{sum}</text>
        {label && <text x="50%" y="62%" textAnchor="middle" dominantBaseline="middle" className="donut-lbl">{label}</text>}
      </svg>
      <div className="donut-legend">
        {segments.map((s, i) => (
          <div className={`dl-row ${clickable ? "clickable" : ""}`} key={i}
            title={clickable ? `${s.value} case${s.value === 1 ? "" : "s"} — click to view` : undefined}
            onClick={clickable ? click(s.label) : undefined}
            tabIndex={clickable ? 0 : undefined}
            onKeyDown={clickable ? (e) => e.key === "Enter" && onSliceClick?.(s.label) : undefined}>
            <span className="dl-dot" style={{ background: s.color }} />
            <span className="dl-name">{s.label}</span>
            <span className="dl-val">{s.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ---- generic DataTable: Excel-style sort + per-column filters -------- */
export type Column<T> = {
  key: string;
  header: string;
  num?: boolean;                         // right-align + numeric sort
  render?: (row: T) => React.ReactNode;  // cell content (defaults to value)
  value?: (row: T) => string | number;   // sort/filter key; omit → display-only column
  filter?: boolean;                      // default true when value is provided
  className?: string;
};

export function DataTable<T>({
  columns, rows, rowKey, onRowClick, empty = "No rows.", maxHeight = 340, initialSort,
}: {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  onRowClick?: (row: T) => void;
  empty?: string;
  maxHeight?: number;
  initialSort?: { key: string; dir: 1 | -1 };
}) {
  const [sort, setSort] = useState<{ key: string; dir: 1 | -1 } | null>(initialSort ?? null);
  const [filters, setFilters] = useState<Record<string, string>>({});

  // Distinct values per filterable column → small sets become dropdowns.
  const distinct = useMemo(() => {
    const m: Record<string, string[]> = {};
    for (const c of columns) {
      if (!c.value || c.filter === false) continue;
      const set = new Set<string>();
      for (const r of rows) {
        const v = c.value(r);
        if (v !== "" && v != null) set.add(String(v));
      }
      m[c.key] = Array.from(set).sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));
    }
    return m;
  }, [columns, rows]);

  const isSelect = (key: string) => (distinct[key]?.length ?? 99) <= 10;

  const filtered = useMemo(() => rows.filter((r) =>
    columns.every((c) => {
      const f = filters[c.key];
      if (!f || !c.value) return true;
      const cell = String(c.value(r) ?? "");
      return isSelect(c.key) ? cell === f : cell.toLowerCase().includes(f.toLowerCase());
    })
  ), [rows, columns, filters, distinct]);

  const sorted = useMemo(() => {
    if (!sort) return filtered;
    const c = columns.find((x) => x.key === sort.key);
    if (!c?.value) return filtered;
    const get = c.value;
    return [...filtered].sort((a, b) => {
      const va = get(a), vb = get(b);
      const r = (typeof va === "number" && typeof vb === "number")
        ? va - vb
        : String(va).localeCompare(String(vb), undefined, { numeric: true });
      return r * sort.dir;
    });
  }, [filtered, sort, columns]);

  const activeCount = Object.values(filters).filter(Boolean).length;
  const toggleSort = (key: string) =>
    setSort((s) => (s?.key === key ? { key, dir: s.dir === 1 ? -1 : 1 } : { key, dir: 1 }));
  const setF = (key: string, val: string) => setFilters((f) => ({ ...f, [key]: val }));

  return (
    <div className="dt">
      <div className="dt-bar">
        {activeCount > 0 && (
          <button className="btn sm ghost" onClick={() => setFilters({})}>
            <IcFunnel size={12} /> Clear filters ({activeCount})
          </button>
        )}
        <span className="dt-count">{sorted.length} of {rows.length}</span>
      </div>
      <div className="table-scroll" style={{ maxHeight }}>
        <table className="data">
          <thead>
            <tr>
              {columns.map((c) => (
                <th key={c.key} className={`${c.num ? "num" : ""} ${sort?.key === c.key ? "sorted" : ""}`}>
                  <span className={`th-label ${c.value ? "sortable" : ""}`}
                    onClick={() => c.value && toggleSort(c.key)}>
                    {c.header}
                    {c.value && <span className="th-sort">{sort?.key === c.key ? (sort.dir === 1 ? "▲" : "▼") : ""}</span>}
                  </span>
                  {c.value && c.filter !== false && (
                    isSelect(c.key) ? (
                      <select className="th-filter" value={filters[c.key] ?? ""} onChange={(e) => setF(c.key, e.target.value)}>
                        <option value="">All</option>
                        {distinct[c.key].map((v) => <option key={v} value={v}>{v}</option>)}
                      </select>
                    ) : (
                      <input className="th-filter" placeholder="Filter…" value={filters[c.key] ?? ""}
                        onChange={(e) => setF(c.key, e.target.value)} />
                    )
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sorted.map((row) => (
              <tr key={rowKey(row)} className={onRowClick ? "rowlink" : ""} tabIndex={onRowClick ? 0 : undefined}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
                onKeyDown={onRowClick ? (e) => e.key === "Enter" && onRowClick(row) : undefined}>
                {columns.map((c) => (
                  <td key={c.key} className={`${c.num ? "num" : ""} ${c.className ?? ""}`}>
                    {c.render ? c.render(row) : String(c.value?.(row) ?? "")}
                  </td>
                ))}
              </tr>
            ))}
            {sorted.length === 0 && (
              <tr><td colSpan={columns.length} className="muted">{empty}</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function Card({
  title,
  hint,
  icon,
  children,
  className = "",
  action,
  style,
  onClick,
}: {
  title?: string;
  hint?: string;
  icon?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  action?: React.ReactNode;
  style?: React.CSSProperties;
  onClick?: () => void;
}) {
  return (
    <div className={`card ${className} ${onClick ? "clickable" : ""}`} style={style} onClick={onClick}>
      {title && (
        <div className="flex between" style={{ marginBottom: 2 }}>
          <h2>{icon && <span className="ic">{icon}</span>}{title}</h2>
          {action}
        </div>
      )}
      {hint && <div className="hint">{hint}</div>}
      {children}
    </div>
  );
}

/** Loading skeleton block. */
export function Skeleton({ h = 16, w = "100%", mt = 0 }: { h?: number; w?: string | number; mt?: number }) {
  return <div className="skeleton" style={{ height: h, width: w, marginTop: mt }} />;
}

export function CardSkeleton({ lines = 4 }: { lines?: number }) {
  return (
    <div className="card">
      <Skeleton h={13} w="40%" />
      <Skeleton h={10} w="65%" mt={8} />
      <div style={{ marginTop: 16 }}>
        {Array.from({ length: lines }).map((_, i) => (
          <Skeleton key={i} h={18} mt={i ? 10 : 0} />
        ))}
      </div>
    </div>
  );
}
