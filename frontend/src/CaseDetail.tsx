import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, type CaseDetail as CD, type Nba } from "./api";
import { Card, Chip } from "./components";
import { PageHead } from "./App";
import { IcBack } from "./icons";

function fmt(iso?: string | null) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
    });
  } catch {
    return String(iso);
  }
}

interface LogRow { ts: string; kind: string; recommended_action: string | null; decision: string | null; note: string | null; }

export default function CaseDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const [d, setD] = useState<CD | null>(null);
  const [nba, setNba] = useState<Nba | null>(null);
  const [logs, setLogs] = useState<LogRow[]>([]);
  const [err, setErr] = useState<string | null>(null);

  // Go back to wherever the user came from; fall back to the dashboard if they
  // deep-linked straight to a case.
  function goBack() {
    if (window.history.length > 1) nav(-1);
    else nav("/");
  }

  function loadLogs(caseId: string) {
    api.audit(caseId).then((r) => setLogs(r.entries)).catch(() => {});
  }

  useEffect(() => {
    if (!id) return;
    api.caseDetail(id).then((cd) => { setD(cd); loadLogs(cd.case.case_id); }).catch((e) => setErr(String(e)));
    api.caseNba(id).then(setNba).catch(() => {});
  }, [id]);

  // Log a decision on this case's recommended action, then refresh the case log.
  async function decide(action: string) {
    if (!d || !nba?.value) return;
    try {
      await fetch("/api/decisions", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          case_id: d.case.case_id,
          recommended_action: nba.value.recommended_action,
          decision: action,
          note: nba.value.rationale?.[0] ?? "",
        }),
      });
    } catch { /* ignore */ }
    loadLogs(d.case.case_id);
  }

  if (err) return (
    <div className="content">
      <button className="btn sm" onClick={goBack} style={{ marginBottom: 16 }}><IcBack size={14} /> Back</button>
      <div className="loading">Case not found: {err}</div>
    </div>
  );
  if (!d) return <div className="content"><div className="loading">Loading case…</div></div>;

  const c = d.case;
  const rec = nba?.value;
  const title = c.receipt || id;

  return (
    <>
      <PageHead title={`Case ${title}`} subtitle={`${c.seriousness} · ${c.complexity} · ${c.current_activity}`} />
      <div className="content">
      <div className="grid">
        <Card title={`Case ${title}`} className="col-5">
          <div className="kv">
            <span className="k">AER#</span><span>{c.aer ?? "—"}</span>
            <span className="k">Seriousness</span><span>{c.seriousness}</span>
            <span className="k">Complexity</span><span>{c.complexity}</span>
            <span className="k">Product</span><span>{c.product ?? "—"}</span>
            <span className="k">Current activity</span><span>{c.current_activity}</span>
            <span className="k">Owner</span><span>{c.assigned_to} · {c.case_owner}</span>
            <span className="k">Submission due</span><span>{fmt(c.submission_due)} ({c.days_to_submission_due}d)</span>
            <span className="k">Case due</span><span>{fmt(c.case_due)} ({c.days_to_case_due}d)</span>
            <span className="k">Company unit</span><span>{c.company_unit}</span>
          </div>
        </Card>

        <Card title="Why this case is at risk" hint="Explainability · each flag cites its supporting data (AC-06)" className="col-7">
          {d.regulatory_risk ? (
            <div className="flex" style={{ marginBottom: 10, alignItems: "flex-start" }}>
              <Chip status={d.regulatory_risk.level} label={`REG ${d.regulatory_risk.level}`} />
              <span>{d.regulatory_risk.reason}</span>
            </div>
          ) : (
            <div className="muted">No regulatory-deadline risk flagged.</div>
          )}
          {d.sla_risk.map((s) => (
            <div key={s.case_id + s.stage} className="flex" style={{ marginBottom: 8, alignItems: "flex-start" }}>
              <Chip status="Amber" label="SLA" />
              <span>{s.reason}</span>
            </div>
          ))}
          {d.stuck.map((s) => (
            <div key={s.case_id + s.activity_name} className="flex" style={{ marginBottom: 8, alignItems: "flex-start" }}>
              <Chip status="Red" label="AGING" />
              <span>{s.reason}</span>
            </div>
          ))}
          {rec && (
            <div className={`card nba-card ${rec.recommended_action}`} style={{ marginTop: 14, padding: 13 }}>
              <div className="nba-action" style={{ textTransform: "capitalize" }}>Next best action: {rec.recommended_action}</div>
              <div className="nba-rationale">{rec.rationale.join(" ")}</div>
              <div className="nba-actions">
                <button className="btn primary sm" onClick={() => decide("accept")}>Accept</button>
                <button className="btn sm" onClick={() => decide("modify")}>Modify</button>
                <button className="btn ghost sm" onClick={() => decide("dismiss")}>Dismiss</button>
              </div>
              <div className="muted" style={{ fontSize: 11, marginTop: 8 }}>Human approval required before execution — your decision is logged below.</div>
            </div>
          )}
        </Card>

        <Card title="Workflow timeline" hint="Stage → status → owner · aging shown vs historical median" className="col-12">
          <div className="timeline">
            {d.activities.map((a) => {
              const st = String(a.status || "");
              const node =
                st === "Completed" ? "complete"
                : st === "In Progress" ? "inprogress"
                : "notstarted";
              const breached = String(a.due_status || "").startsWith("Red");
              return (
                <div className={`tl-step ${node === "inprogress" ? "active" : ""}`} key={a.activity_id}>
                  <span className={`tl-node ${node}`} />
                  <span className="stage">{a.activity_name}</span>
                  <Chip
                    status={node === "complete" ? "Green" : node === "inprogress" ? (breached ? "Red" : "Amber") : "LOW"}
                    label={st}
                  />
                  <span className="muted">
                    {a.assigned_to ? `${a.assigned_to} · ${a.processing_unit}` : a.processing_unit}
                    {a.aging_hours ? ` · ${Math.round(Number(a.aging_hours))}h` : ""}
                    {a.historical_median_hours ? ` / ${Math.round(Number(a.historical_median_hours))}h norm` : ""}
                    {a.aging_ratio ? ` (${Number(a.aging_ratio).toFixed(2)}×)` : ""}
                    {Number(a.reassignment_count) ? ` · ${a.reassignment_count} reassign` : ""}
                    {a.blocking_reason ? ` · ${a.blocking_reason}` : ""}
                  </span>
                </div>
              );
            })}
          </div>
        </Card>

        {d.assignments.length > 0 && (
          <Card title="Reassignment history" hint="Who held this case, when, and why (AC-08)" className="col-12">
            <table className="data">
              <thead><tr><th>When</th><th>Activity</th><th>From</th><th>To</th><th>Reason</th><th>Handover</th></tr></thead>
              <tbody>
                {d.assignments.map((r, i) => (
                  <tr key={i}>
                    <td>{fmt(r.changed_ts)}</td><td>{r.activity_name}</td>
                    <td>{r.from_user}</td><td>{r.to_user}</td>
                    <td>{r.reason}</td><td>{r.handover_status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        )}

        <Card title="Action Logs" hint="AI answers and human decisions recorded for this case — the governance record" className="col-12">
          {logs.length === 0 ? (
            <div className="muted">No actions logged for this case yet. Accept, modify, or dismiss the recommendation above and it will appear here.</div>
          ) : (
            <table className="data">
              <thead><tr><th>When (UTC)</th><th>Type</th><th>Action</th><th>Decision</th><th>Note</th></tr></thead>
              <tbody>
                {logs.map((l, i) => (
                  <tr key={i}>
                    <td className="mono">{fmt(l.ts + "Z")}</td>
                    <td><Chip status={l.kind === "decision" ? "Green" : "LOW"} label={l.kind === "decision" ? "decision" : "AI chat"} /></td>
                    <td style={{ textTransform: "capitalize" }}>{l.recommended_action ?? "—"}</td>
                    <td style={{ textTransform: "capitalize" }}>{l.decision ?? "—"}</td>
                    <td className="muted" style={{ maxWidth: 420 }}>{(l.note ?? "").slice(0, 90)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
      </div>
      </div>
    </>
  );
}
