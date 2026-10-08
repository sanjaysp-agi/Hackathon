import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, type Briefing, type NbaCandidate, type RebalancePlan } from "../api";
import { Card, Chip, DataTable, type Column } from "../components";
import { IcAlert, IcArrow, IcCheck, IcClock, IcSpark, IcUsers } from "../icons";

const ACTION_ICON: Record<string, React.ReactNode> = {
  escalate: <IcAlert size={14} />, reassign: <IcUsers size={14} />,
  prioritize: <IcSpark size={14} />, monitor: <IcClock size={14} />,
};

type P1 = Briefing["p1_cases"][number];
const BRIEF_COLUMNS: Column<P1>[] = [
  { key: "receipt", header: "Receipt#", className: "mono", value: (p) => p.receipt },
  { key: "stage", header: "Stage", value: (p) => p.stage },
  { key: "owner", header: "Owner", value: (p) => p.owner },
  { key: "sdd", header: "SDD", num: true, value: (p) => p.days_to_sdd, render: (p) => `${p.days_to_sdd}d` },
  { key: "action", header: "Recommended", value: (p) => p.action, render: (p) => <span style={{ textTransform: "capitalize" }}>{p.action}</span> },
  { key: "reason", header: "Reason", value: (p) => p.reason, render: (p) => <span className="muted">{p.reason}</span> },
];

/** Action center block: today's briefing + next-best-actions + rebalance plan.
    Rendered inline on the single-page dashboard. */
export function ActionsSection({ onDecision }: { onDecision: (c: NbaCandidate, a: string) => void }) {
  const [brief, setBrief] = useState<Briefing | null>(null);
  const [plan, setPlan] = useState<RebalancePlan | null>(null);
  const [nba, setNba] = useState<NbaCandidate[]>([]);
  const [done, setDone] = useState<Record<string, string>>({});
  const nav = useNavigate();

  useEffect(() => {
    api.briefing().then(setBrief).catch(() => {});
    api.rebalance().then(setPlan).catch(() => {});
    api.overview().then((o) => setNba(o.next_best_action.candidates)).catch(() => {});
  }, []);

  function decide(c: NbaCandidate, action: string) {
    onDecision(c, action);
    setDone((d) => ({ ...d, [c.case_id]: action }));
  }

  return (
    <>
      {brief && (
        <Card title="What requires action today" icon={<IcSpark size={15} />} hint={brief.headline} className="col-12" style={{ marginBottom: 18 }}>
          <DataTable columns={BRIEF_COLUMNS} rows={brief.p1_cases} rowKey={(p) => p.case_id}
            onRowClick={(p) => nav(`/case/${p.case_id}`)} empty="Nothing flagged for action today." />
        </Card>
      )}

      <div className="grid">
        <Card title="Next Best Actions" icon={<IcSpark size={15} />} hint="Ranked by urgency · reassignment is qualification-aware" className="col-7">
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {nba.slice(0, 6).map((c) => (
              <div key={c.case_id} className={`card nba-card ${c.recommended_action}`} style={{ padding: 13 }}>
                <div className="flex between">
                  <span className="nba-action">{ACTION_ICON[c.recommended_action]} {c.recommended_action} · <span className="mono" style={{ fontSize: 12 }}>{c.case_id.replace("CASE-", "")}</span></span>
                  <Chip status={c.level} />
                </div>
                <div className="nba-rationale">{c.rationale[0]}</div>
                {done[c.case_id] ? (
                  <div className="sim-verdict ok" style={{ marginTop: 0, padding: "7px 11px" }}>
                    <span className="ic"><IcCheck size={14} /></span>{done[c.case_id]} — logged to audit trail
                  </div>
                ) : (
                  <div className="nba-actions">
                    <button className="btn primary sm" onClick={() => decide(c, "accept")}>Accept</button>
                    <button className="btn sm" onClick={() => decide(c, "modify")}>Modify</button>
                    <button className="btn ghost sm" onClick={() => decide(c, "dismiss")}>Dismiss</button>
                    <button className="btn ghost sm" onClick={() => nav(`/case/${c.case_id}`)}>Drill in <IcArrow size={12} /></button>
                  </div>
                )}
              </div>
            ))}
          </div>
        </Card>

        <Card title="Rebalance Plan — Medical Review" icon={<IcUsers size={15} />} hint="Each case routed to the best-suited reviewer by skill, efficiency & experience — not just who's free" className="col-5">
          {plan && plan.moves.length > 0 ? (
            <>
              <div style={{ display: "flex", flexDirection: "column", gap: 9 }}>
                {plan.moves.map((m, i) => (
                  <div key={i} className="card" style={{ padding: 13, background: "var(--surface-2)" }}>
                    <div className="flex" style={{ gap: 8, fontSize: 13 }}>
                      <span className="mono">{(m.receipt ?? m.case_id).replace("CASE-", "")}</span>
                      <span className="muted">{m.from}</span>
                      <IcArrow size={13} />
                      <strong>{m.to}</strong>
                      {m.to_tier && <Chip status={m.to_tier === "Senior" ? "Green" : m.to_tier === "Proficient" ? "Amber" : "Red"} label={m.to_tier} />}
                    </div>
                    <div className="muted" style={{ fontSize: 11.5, marginTop: 6 }}>{m.why}</div>
                    {m.warning && (
                      <div className="sim-verdict bad" style={{ fontSize: 11.5, marginTop: 8, padding: "7px 10px" }}>
                        <span className="ic"><IcAlert size={13} /></span>{m.warning}
                      </div>
                    )}
                  </div>
                ))}
              </div>
              <div className="sim-verdict ok" style={{ fontSize: 12 }}><span className="ic"><IcCheck size={14} /></span>{plan.note}</div>
            </>
          ) : (
            <div className="muted">No suitable qualified reviewer has spare capacity right now. Consider temporary backup capacity or a staged handover.</div>
          )}
        </Card>
      </div>
    </>
  );
}
