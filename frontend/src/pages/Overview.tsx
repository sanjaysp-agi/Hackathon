import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { type Overview as Ov, type RegRow, type SlaRow, type StuckRow } from "../api";
import { Chip, DataTable, Modal, statusClass, type Column } from "../components";
import { IcAlert, IcArrow, IcClock, IcFunnel, IcGrid, IcInfo, IcPause } from "../icons";

type Tele = {
  label: string; value: React.ReactNode; sub: string; cls: string;
  icon: React.ReactNode; onClick?: () => void; isText?: boolean; isStatic?: boolean;
  pop?: React.ReactNode;
};

const dueShort = (s: string) => (s.includes("-") ? s.split(/\s*-\s*/)[0] : s);

const REG_COLUMNS: Column<RegRow>[] = [
  { key: "receipt", header: "Receipt#", className: "mono", value: (r) => r.receipt },
  { key: "stage", header: "Stage", value: (r) => r.stage },
  { key: "team", header: "Team", value: (r) => r.team },
  { key: "owner", header: "Owner", value: (r) => r.assigned_to },
  { key: "seriousness", header: "Seriousness", value: (r) => r.seriousness },
  { key: "level", header: "Risk", value: (r) => r.level, render: (r) => <Chip status={r.level} /> },
  { key: "sdd", header: "SDD", num: true, value: (r) => r.days_to_sdd, render: (r) => `${r.days_to_sdd}d` },
  { key: "cdd", header: "CDD", num: true, value: (r) => r.days_to_cdd, render: (r) => `${r.days_to_cdd}d` },
  { key: "breach", header: "Breach%", num: true, value: (r) => r.breach_prob, render: (r) => `${r.breach_prob}%` },
  { key: "go", header: "", render: () => <span className="go"><IcArrow size={14} /></span> },
];

const SLA_COLUMNS: Column<SlaRow>[] = [
  { key: "receipt", header: "Receipt#", className: "mono", value: (s) => s.receipt },
  { key: "stage", header: "Stage", value: (s) => s.stage },
  { key: "owner", header: "Owner", value: (s) => s.assigned_to },
  { key: "aging", header: "Aging", num: true, value: (s) => s.activity_aging_hours, render: (s) => `${Math.round(s.activity_aging_hours)}h` },
  { key: "norm", header: "Norm", num: true, value: (s) => s.historical_hours, render: (s) => `${Math.round(s.historical_hours)}h` },
  { key: "ratio", header: "Ratio", num: true, value: (s) => s.aging_ratio, render: (s) => `${s.aging_ratio.toFixed(2)}×` },
  { key: "due", header: "Due status", value: (s) => dueShort(s.activity_due_status), render: (s) => <Chip status={s.activity_due_status} label={dueShort(s.activity_due_status)} /> },
  { key: "breach", header: "Breach%", num: true, value: (s) => s.breach_prob, render: (s) => `${s.breach_prob}%` },
];

const AGING_COLUMNS: Column<StuckRow>[] = [
  { key: "receipt", header: "Receipt#", className: "mono", value: (a) => a.receipt },
  { key: "activity", header: "Activity", value: (a) => a.activity_name },
  { key: "team", header: "Team", value: (a) => a.team },
  { key: "owner", header: "Owner", value: (a) => a.assigned_to },
  { key: "aging", header: "Aging", num: true, value: (a) => a.activity_aging_hours, render: (a) => `${Math.round(a.activity_aging_hours)}h` },
  { key: "norm", header: "Norm", num: true, value: (a) => a.historical_hours, render: (a) => `${Math.round(a.historical_hours)}h` },
  { key: "xnorm", header: "× norm", num: true, value: (a) => a.x_over_norm, render: (a) => <Chip status="Red" label={`${a.x_over_norm.toFixed(1)}×`} /> },
  { key: "go", header: "", render: () => <span className="go"><IcArrow size={14} /></span> },
];

/** A small "how this is calculated" callout for the drill-in popups. */
function CalcNote({ children }: { children: React.ReactNode }) {
  return (
    <div className="calc-note">
      <span className="ic"><IcInfo size={15} /></span>
      <div>{children}</div>
    </div>
  );
}

type ModalKind = null | "aging" | "regulatory" | "predicted" | "bottleneck";

/** The health ring + live telemetry + plain-language situation summary.
    Telemetry boxes open a drill-in popup (or scroll to the bottleneck chart). */
export function Hero({ ov, go }: { ov: Ov; go: (id: string) => void }) {
  const nav = useNavigate();
  const [modal, setModal] = useState<ModalKind>(null);
  const openCase = (c: { case_id: string }) => nav(`/case/${c.case_id}`);

  const score = ov.health.value;
  const cls = statusClass(ov.health.status);
  const color = `var(--${cls === "good" ? "good" : cls === "warning" ? "warning" : "critical"})`;
  const R = 92, C = 2 * Math.PI * R;
  const dash = C * (1 - score / 100);

  const cl = ov.caseload;
  const maxStage = cl ? Math.max(1, ...cl.by_stage.map((s) => s.count)) : 1;
  const activePop = cl ? (
    <>
      <div className="tp-title">LSMV snapshot · {cl.total} cases</div>
      <div className="tp-split">
        <span className="tp-pill active"><b>{cl.active}</b> in active workflow</span>
        <span className="tp-pill"><b>{cl.closed}</b> closed / dispatched</span>
      </div>
      <div className="tp-bars">
        {cl.by_stage.map((s) => (
          <div className="tp-row" key={s.stage}>
            <span className="tp-name">{s.stage}</span>
            <span className="tp-track"><span className="tp-fill" style={{ width: `${(s.count / maxStage) * 100}%` }} /></span>
            <span className="tp-num">{s.count}</span>
          </div>
        ))}
      </div>
      <div className="tp-foot">{cl.active} active across {cl.by_stage.length} stages · {cl.closed} already dispatched</div>
    </>
  ) : undefined;

  const tele: Tele[] = [
    { label: "Active cases", value: cl?.total ?? 165, sub: "in the LSMV snapshot", cls: "", icon: <IcGrid size={12} />, isStatic: true, pop: activePop },
    { label: "Regulatory risk", value: ov.regulatory.counts.High, sub: "within 2 days of deadline", cls: statusClass(ov.regulatory.status), icon: <IcAlert size={12} />, onClick: () => setModal("regulatory") },
    { label: "Predicted breach", value: ov.sla.value, sub: "≥75% SLA probability", cls: statusClass(ov.sla.status), icon: <IcClock size={12} />, onClick: () => setModal("predicted") },
    { label: "Bottleneck", value: ov.bottlenecks.value ?? "—", sub: `${ov.bottlenecks.max_breached} activities breached`, cls: statusClass(ov.bottlenecks.status), icon: <IcFunnel size={12} />, isText: true, onClick: () => setModal("bottleneck") },
    { label: "Aging work", value: ov.stuck.value, sub: "≥2× historical norm", cls: statusClass(ov.stuck.status), icon: <IcPause size={12} />, onClick: () => setModal("aging") },
  ];

  const h = ov.health;
  return (
    <>
      <div className="hero">
        <div className="ring-wrap has-info" tabIndex={0} aria-label={`Workflow health ${score}%. ${h.formula ?? ""}`}>
          <svg width="220" height="220" viewBox="0 0 220 220">
            <circle className="ring-track" cx="110" cy="110" r={R} fill="none" strokeWidth="14" />
            <circle className="ring-prog" cx="110" cy="110" r={R} fill="none" strokeWidth="14"
              strokeLinecap="round" stroke={color} strokeDasharray={C} strokeDashoffset={dash} style={{ color }} />
          </svg>
          <div className="ring-core">
            <div className="score" style={{ color }}>{score}<span className="pct">%</span></div>
            <div className="of">workflow health <IcInfo size={11} /></div>
            <div className="st"><Chip status={h.status} /></div>
          </div>

          {/* Hover/focus tooltip: what the score means + how it's computed */}
          <div className="health-pop" role="tooltip">
            <div className="hp-title">How workflow health is calculated</div>
            <p className="hp-formula">{h.formula}</p>
            <div className="hp-bars">
              {h.components.map((c) => {
                const maxW = Math.max(...h.components.map((x) => x.weight));
                return (
                  <div className="hp-row" key={c.name} title={c.description}>
                    <span className="hp-name">{c.label ?? c.name.replace(/_/g, " ")}</span>
                    <span className="hp-track">
                      <span className="hp-fill" style={{ width: `${Math.min((c.points_lost / maxW) * 100, 100)}%` }} />
                    </span>
                    <span className="hp-num">−{c.points_lost}</span>
                  </div>
                );
              })}
            </div>
            <div className="hp-foot">
              Starts at 100%, minus {h.components.reduce((s, c) => s + c.points_lost, 0).toFixed(0)} points of
              weighted risk = <b style={{ color }}>{score}%</b>.
              {h.bands && <> · {h.bands.green} · {h.bands.amber} · {h.bands.red}</>}
            </div>
          </div>
        </div>
        <div>
          <div className="hero-head"><span className="eyebrow">Live situation</span></div>
          <p className="hero-sum">
            <b>{ov.regulatory.counts.High} cases</b> are within two days of a reporting deadline and{" "}
            <b>{ov.sla.value}</b> are predicted to breach SLA. <b>{ov.bottlenecks.value}</b> is the active
            bottleneck with <b>{ov.bottlenecks.max_breached} breached</b> activities, and{" "}
            <b>{ov.workload.value.length} reviewer{ov.workload.value.length === 1 ? " is" : "s are"}</b> over capacity.
          </p>
          <div className="telemetry">
            {tele.map((t) => {
              const inner = (
                <>
                  <div className="t-label"><span className="ic">{t.icon}</span>{t.label}</div>
                  <div className={`t-value ${t.cls}${t.isText ? " t-text" : ""}`}>{t.value}</div>
                  <div className="t-sub">{t.sub}{!t.isStatic && <span className="t-go">View →</span>}</div>
                </>
              );
              return t.isStatic ? (
                <div className={`tele tele-static ${t.pop ? "has-pop" : ""}`} key={t.label} tabIndex={t.pop ? 0 : undefined}>
                  {inner}
                  {t.pop && <div className="tele-pop" role="tooltip">{t.pop}</div>}
                </div>
              ) : (
                <button className="tele" key={t.label} onClick={t.onClick}
                  aria-label={`${t.label}: ${t.value}. Open details`}>{inner}</button>
              );
            })}
          </div>
        </div>
      </div>

      {modal === "regulatory" && (
        <Modal title="Regulatory-Risk Cases" icon={<IcAlert size={16} />}
          subtitle="Active cases ranked by nearest Submission Due Date" onClose={() => setModal(null)}>
          <CalcNote>
            <b>How regulatory risk is banded:</b> by days to the Submission Due Date (SDD) —
            {" "}<b>≤ 2 days → High</b>, <b>3–6 days → Medium</b>, <b>7+ days → Low</b>.
            The <b>{ov.regulatory.counts.High}</b> figure counts the High band.
          </CalcNote>
          <DataTable columns={REG_COLUMNS} rows={ov.regulatory.evidence} rowKey={(r) => r.case_id}
            onRowClick={openCase} maxHeight={520} empty="No regulatory-risk cases." />
        </Modal>
      )}

      {modal === "predicted" && (
        <Modal title="Predicted SLA Breach" icon={<IcClock size={16} />}
          subtitle="Active cases with a ≥ 75% probability of breaching SLA" onClose={() => setModal(null)}>
          <CalcNote>
            <b>How breach probability is calculated:</b> it starts from deadline proximity
            {" "}(<b>≤ 2 days → 60%</b>, <b>3–6 days → 35%</b>, otherwise <b>10%</b>), adds
            {" "}<b>aging pressure</b> from the current activity's age vs its historical turnaround
            {" "}(up to <b>+26%</b>), then <b>+12%</b> if the activity due date is breached (Red) or
            {" "}<b>+6%</b> if at risk (Amber). Cases at <b>≥ 75%</b> are flagged High.
          </CalcNote>
          <DataTable columns={SLA_COLUMNS} rows={ov.sla.evidence} rowKey={(s) => s.case_id}
            onRowClick={openCase} maxHeight={520} empty="No predicted SLA breaches." />
        </Modal>
      )}

      {modal === "aging" && (
        <Modal title="Aging Activities" icon={<IcPause size={16} />}
          subtitle="Active activities running ≥ 2× the historical norm for their stage" onClose={() => setModal(null)}>
          <CalcNote>
            <b>How aging is flagged:</b> an activity is "aging" when its current age is at least
            {" "}<b>2× the historical median turnaround</b> for that activity + unit + complexity.
            The <b>× norm</b> column shows that multiple.
          </CalcNote>
          <DataTable columns={AGING_COLUMNS} rows={ov.stuck.evidence} rowKey={(a) => a.case_id}
            onRowClick={openCase} maxHeight={520} empty="No aging activities." />
        </Modal>
      )}

      {modal === "bottleneck" && (
        <Modal title="Bottlenecks by Processing Unit" icon={<IcFunnel size={16} />}
          subtitle="In-progress activities per unit · Critical = 2+ past their Activity Due Date"
          onClose={() => setModal(null)}>
          <div className="bn-list">
            {ov.bottlenecks.evidence.map((b) => (
              <div className={`bn-item ${statusClass(b.status)}`} key={b.processing_unit}>
                <div className="bn-head">
                  <span className="bn-name">{b.processing_unit}</span>
                  <Chip status={b.status} label={b.status} />
                </div>
                <div className="bn-metrics">
                  <span className="bn-metric"><b>{b.active_wip}</b> in progress</span>
                  <span className="bn-metric crit"><b>{b.breached}</b> breached</span>
                  <span className="bn-metric warn"><b>{b.approaching}</b> approaching</span>
                  <span className="bn-metric"><b>{b.aging_ratio}×</b> vs norm</span>
                </div>
                {b.explanation && <div className="bn-line"><span className="bn-lbl">Assessment</span>{b.explanation}</div>}
                {b.management_action && <div className="bn-line"><span className="bn-lbl">Recommended</span>{b.management_action}</div>}
              </div>
            ))}
          </div>
        </Modal>
      )}
    </>
  );
}
