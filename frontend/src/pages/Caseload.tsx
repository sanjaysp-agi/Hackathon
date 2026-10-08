import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, type ActiveCase, type AnalyticsCase, type Analytics, type ComplexityStage, type Slice, type StageRow } from "../api";
import { Card, Chip, DataTable, Donut, Modal, type Column } from "../components";
import { IcAlert, IcArrow, IcChevron, IcClock, IcGrid } from "../icons";

/** Map a slice label to a palette color per chart. */
const COLORS: Record<string, string> = {
  "Overdue": "var(--critical)",
  "Due ≤ 2 days": "var(--serious)",
  "3–6 days": "var(--warning)",
  "7+ days": "var(--good)",
  "Serious": "var(--warning)",
  "SUSAR (serious)": "var(--serious)",
  "Life-threatening / Death": "var(--critical)",
  "Non-serious": "var(--good)",
  "Spontaneous": "var(--series-1)",
  "Report from study": "var(--series-7)",
  "Unknown": "var(--muted)",
};
const colorFor = (label: string, i: number) => COLORS[label] ?? `var(--series-${(i % 7) + 1})`;
const paint = (slices: Slice[]) => slices.map((s, i) => ({ ...s, color: colorFor(s.label, i) }));

const COMPLEXITY_COLOR: Record<string, string> = {
  Low: "var(--series-2)", Medium: "var(--series-1)", Large: "var(--series-4)",
};

/** Columns for the per-stage expanded case list. */
const CASE_COLUMNS: Column<AnalyticsCase>[] = [
  { key: "receipt", header: "Receipt#", className: "mono", value: (c) => c.receipt },
  { key: "seriousness", header: "Seriousness", value: (c) => c.seriousness },
  { key: "complexity", header: "Complexity", value: (c) => c.complexity },
  { key: "assigned_to", header: "Owner", value: (c) => c.assigned_to },
  {
    key: "due", header: "Due status",
    value: (c) => { const d = c.activity_due_status || "On Track"; return d.includes("-") ? d.split(/\s*-\s*/)[1] : d; },
    render: (c) => dueChip(c.activity_due_status),
  },
  { key: "sdd", header: "SDD", num: true, value: (c) => c.days_to_sdd ?? 9999, render: (c) => (c.days_to_sdd == null ? "—" : `${c.days_to_sdd}d`) },
  { key: "breach", header: "Breach%", num: true, value: (c) => c.breach_prob, render: (c) => `${c.breach_prob}%` },
  { key: "go", header: "", render: () => <span className="go"><IcArrow size={14} /></span> },
];

/** Columns for the donut drill-in case table (active cases). */
const ACTIVE_COLUMNS: Column<ActiveCase>[] = [
  { key: "receipt", header: "Receipt#", className: "mono", value: (c) => c.receipt },
  { key: "stage", header: "Stage", value: (c) => c.stage },
  { key: "seriousness", header: "Seriousness", value: (c) => c.seriousness },
  { key: "complexity", header: "Complexity", value: (c) => c.complexity },
  { key: "assigned_to", header: "Owner", value: (c) => c.assigned_to },
  { key: "due", header: "Due status", value: (c) => shortDue(c.activity_due_status), render: (c) => dueChip(c.activity_due_status) },
  { key: "sdd", header: "SDD", num: true, value: (c) => c.days_to_sdd ?? 9999, render: (c) => (c.days_to_sdd == null ? "—" : `${c.days_to_sdd}d`) },
  { key: "breach", header: "Breach%", num: true, value: (c) => c.breach_prob, render: (c) => `${c.breach_prob}%` },
];

function shortDue(d: string) { d = d || "On Track"; return d.includes("-") ? d.split(/\s*-\s*/)[1] : d; }
function dueChip(dRaw: string) {
  const d = dRaw || "On Track";
  const chip = d.startsWith("Red") ? "Red" : d.startsWith("Amber") ? "Amber" : "Green";
  return <Chip status={chip} label={shortDue(d)} />;
}

type Dim = "deadline" | "seriousness" | "classification";
const DIMS: Record<Dim, {
  title: string; sub: string; icon: React.ReactNode;
  segs: (a: Analytics) => Slice[]; bucket: (c: ActiveCase) => string;
}> = {
  deadline: { title: "Deadline Watch", sub: "Active cases by days to Submission Due Date", icon: <IcClock size={16} />, segs: (a) => a.deadline_watch, bucket: (c) => c.deadline_bucket },
  seriousness: { title: "Seriousness", sub: "Active cases by seriousness classification", icon: <IcAlert size={16} />, segs: (a) => a.seriousness, bucket: (c) => c.seriousness_bucket },
  classification: { title: "Case Classification", sub: "Active cases by report type", icon: <IcGrid size={16} />, segs: (a) => a.classification, bucket: (c) => c.report_type },
};

/** Popup for a donut: segment chips to filter + the matching case table. */
function DonutModal({ a, dim, seg, onSeg, onClose }: {
  a: Analytics; dim: Dim; seg: string | null;
  onSeg: (s: string | null) => void; onClose: () => void;
}) {
  const nav = useNavigate();
  const cfg = DIMS[dim];
  const segs = paint(cfg.segs(a));
  const rows = seg ? a.cases.filter((c) => cfg.bucket(c) === seg) : a.cases;

  return (
    <Modal title={cfg.title} icon={cfg.icon} subtitle={cfg.sub} onClose={onClose}>
      <div className="seg-chips">
        <button className={`seg-chip ${!seg ? "on" : ""}`} onClick={() => onSeg(null)}>
          All <b>{a.cases.length}</b>
        </button>
        {segs.map((s) => (
          <button key={s.label} className={`seg-chip ${seg === s.label ? "on" : ""}`} onClick={() => onSeg(s.label)}>
            <span className="dl-dot" style={{ background: s.color }} /> {s.label} <b>{s.value}</b>
          </button>
        ))}
      </div>
      <DataTable columns={ACTIVE_COLUMNS} rows={rows} rowKey={(c) => c.case_id}
        onRowClick={(c) => nav(`/case/${c.case_id}`)} maxHeight={460} empty="No cases in this group." />
    </Modal>
  );
}

/** Combined per-stage chart: each stage is a complexity-segmented bar
    (Low/Medium/Large), expandable to the cases sitting in that stage. */
function StageChart({ stages, complexity, levels }: {
  stages: StageRow[]; complexity: ComplexityStage[]; levels: string[];
}) {
  const [open, setOpen] = useState<string | null>(stages[0]?.stage ?? null);
  const nav = useNavigate();
  const max = Math.max(1, ...stages.map((s) => s.count));
  const compOf = (stage: string) => complexity.find((c) => c.stage === stage);

  return (
    <div className="stage-chart">
      {stages.map((s) => {
        const isOpen = open === s.stage;
        const comp = compOf(s.stage);
        return (
          <div className="stage-block" key={s.stage}>
            <div className="stage-bar-row rowlink" tabIndex={0}
              onClick={() => setOpen(isOpen ? null : s.stage)}
              onKeyDown={(e) => e.key === "Enter" && setOpen(isOpen ? null : s.stage)}>
              <span className="stage-name" title={s.stage}>{s.stage}</span>
              <span className="stack-track stage-track">
                {levels.map((l) => {
                  const v = comp ? (comp[l as keyof ComplexityStage] as number) : 0;
                  return v > 0 ? (
                    <span key={l} className="stack-seg" title={`${l}: ${v}`}
                      style={{ width: `${(v / max) * 100}%`, background: COMPLEXITY_COLOR[l] }}>{v}</span>
                  ) : null;
                })}
              </span>
              <span className="stage-count">{s.count}</span>
              <span className="stage-chev" data-open={isOpen}><IcChevron size={16} /></span>
            </div>
            {isOpen && (
              <div className="stage-cases">
                <DataTable columns={CASE_COLUMNS} rows={s.cases} rowKey={(c) => c.case_id}
                  onRowClick={(c) => nav(`/case/${c.case_id}`)} maxHeight={260} empty="No cases in this stage." />
              </div>
            )}
          </div>
        );
      })}
      <div className="chart-legend">
        {levels.map((l) => (
          <span className="cl-item" key={l}><span className="cl-dot" style={{ background: COMPLEXITY_COLOR[l] }} />{l}</span>
        ))}
      </div>
    </div>
  );
}

export function CaseloadSection() {
  const [a, setA] = useState<Analytics | null>(null);
  const [modal, setModal] = useState<{ dim: Dim; seg: string | null } | null>(null);
  useEffect(() => { api.analytics().then(setA).catch(() => {}); }, []);

  if (!a) return <div className="loading">Loading caseload…</div>;

  const donut = (dim: Dim) => (
    <Card title={DIMS[dim].title} hint={`${DIMS[dim].sub} · click a slice to drill in`} className="col-4"
      onClick={() => setModal({ dim, seg: null })}>
      <Donut segments={paint(DIMS[dim].segs(a))} label="cases"
        onSliceClick={(seg) => setModal({ dim, seg })} />
    </Card>
  );

  return (
    <>
      <div className="grid">
        {donut("deadline")}
        {donut("seriousness")}
        {donut("classification")}
      </div>

      <div className="grid" style={{ marginTop: 20 }}>
        <Card title="Workflow Pipeline" icon={<IcChevron size={15} />} hint="Active cases at each pipeline stage, split by complexity · click a stage to see its cases" className="col-12">
          <StageChart stages={a.stages} complexity={a.complexity_by_stage} levels={a.complexity_levels} />
        </Card>
      </div>

      {modal && (
        <DonutModal a={a} dim={modal.dim} seg={modal.seg}
          onSeg={(seg) => setModal({ dim: modal.dim, seg })} onClose={() => setModal(null)} />
      )}
    </>
  );
}
