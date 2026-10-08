import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { type BottleneckRow, type Overview as Ov } from "../api";
import { Card, Chip, Modal, statusClass } from "../components";
import Simulator from "../Simulator";
import { IcArrow, IcFunnel, IcUsers } from "../icons";

/** Operations block: bottlenecks (click a unit for detail) + workload + simulator. */
export function OperationsSection({ ov }: { ov: Ov }) {
  const bott = ov.bottlenecks.evidence;
  const maxBreach = Math.max(1, ...bott.map((b) => b.breached || 0.5));
  const wl = ov.workload.evidence;
  const [unit, setUnit] = useState<BottleneckRow | null>(null);
  const nav = useNavigate();

  return (
    <div className="grid">
      <Card title="Bottlenecks" icon={<IcFunnel size={15} />} hint="Critical = 2+ activities past their Activity Due Date · click a unit for detail" className="col-6">
        <div className="bars">
          {bott.map((b) => (
            <button className="bar-row bar-click" key={b.processing_unit} onClick={() => setUnit(b)}
              aria-label={`${b.processing_unit} bottleneck detail`}>
              <span className="name">{b.processing_unit}</span>
              <div className="bar-track">
                <div className="bar-fill" style={{ width: `${Math.min((b.breached || 0.4) / maxBreach * 100, 100)}%`, background: b.status === "Critical" ? "var(--critical)" : b.status === "At Risk" ? "var(--warning)" : "var(--series-1)" }} />
              </div>
              <span className="num">{b.breached ? `${b.breached}⚠` : `${b.active_wip}`}</span>
            </button>
          ))}
        </div>
        <div className="spacer" />
        <div className="flex" style={{ gap: 8 }}>
          <Chip status={ov.bottlenecks.status} label={bott[0]?.status} />
          <span className="muted" style={{ fontSize: 11 }}>{bott[0]?.reason}</span>
        </div>
      </Card>

      <Card title="Workload Distribution" icon={<IcUsers size={15} />} hint="Utilization = planned ÷ available hours · marker at 100%" className="col-6">
        <div className="bars">
          {wl.map((w) => {
            const max = Math.max(1.4, ...wl.map((x) => x.utilization));
            return (
              <div className="bar-row" key={w.user} style={{ gridTemplateColumns: "190px 1fr 48px" }}>
                <span className="name">{w.user} · <span className="muted">{w.role.replace("PV ", "").replace("Safety ", "")}</span></span>
                <div className="bar-track">
                  <div className="bar-fill" style={{ width: `${Math.min(w.utilization / max * 100, 100)}%`, background: w.state === "overloaded" ? "var(--critical)" : w.state === "slack" ? "var(--good)" : "var(--series-1)" }} />
                  <div className="bar-threshold" style={{ left: `${(1 / max) * 100}%` }} />
                </div>
                <span className="num">{w.utilization_pct}%</span>
              </div>
            );
          })}
        </div>
      </Card>

      <div className="col-12"><Simulator workload={wl} /></div>

      {unit && (
        <Modal title={unit.processing_unit} icon={<IcFunnel size={16} />}
          subtitle="Bottleneck detail · in-progress activities in this unit" onClose={() => setUnit(null)}>
          <div style={{ marginBottom: 14 }}><Chip status={unit.status} label={unit.status} /></div>
          <div className="bn-metrics">
            <span className="bn-metric"><b>{unit.active_wip}</b> in progress</span>
            <span className="bn-metric crit"><b>{unit.breached}</b> breached</span>
            <span className="bn-metric warn"><b>{unit.approaching}</b> approaching</span>
            <span className="bn-metric"><b>{unit.aging_ratio}×</b> vs norm</span>
            <span className="bn-metric"><b>{Math.round(unit.avg_aging_hours)}h</b> avg aging</span>
          </div>
          {unit.explanation && <div className="bn-line"><span className="bn-lbl">Assessment</span>{unit.explanation}</div>}
          {unit.management_action && <div className="bn-line"><span className="bn-lbl">Recommended</span>{unit.management_action}</div>}
          {unit.contributing_cases.length > 0 && (
            <div className="bn-cases">
              <div className="bn-cases-lbl">Breached cases ({unit.contributing_cases.length}) · click to open</div>
              <div className="bn-chips">
                {unit.contributing_cases.map((id) => (
                  <button key={id} className="bn-chip mono" onClick={() => nav(`/case/${id}`)}>
                    {id.replace("CASE-", "")} <IcArrow size={12} />
                  </button>
                ))}
              </div>
            </div>
          )}
        </Modal>
      )}
    </div>
  );
}
