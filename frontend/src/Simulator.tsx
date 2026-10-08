import { useMemo, useState } from "react";
import { api, type SimResult, type WorkloadRow } from "./api";
import { Card } from "./components";
import { IcAlert, IcCheck, IcSpark, IcUsers } from "./icons";

/** What-if reassignment simulator — the headline differentiator.
   Pick an overloaded owner, a recipient, and how many cases to move; the engine
   recomputes both utilizations and flags whether the move is clinically qualified. */
export default function Simulator({ workload }: { workload: WorkloadRow[] }) {
  const overloaded = useMemo(() => workload.filter((w) => w.state !== "slack"), [workload]);
  const [from, setFrom] = useState(workload.find((w) => w.state === "overloaded")?.user ?? workload[0]?.user ?? "");
  const [to, setTo] = useState("");
  const [n, setN] = useState(2);
  const [res, setRes] = useState<SimResult | null>(null);
  const [busy, setBusy] = useState(false);

  // sensible default recipient: same role, most slack
  const fromRow = workload.find((w) => w.user === from);
  const peers = workload.filter((w) => w.user !== from).sort((a, b) => a.utilization - b.utilization);
  const defaultTo = peers.find((w) => fromRow && w.role === fromRow.role)?.user ?? peers[0]?.user ?? "";
  const toUser = to || defaultTo;

  async function run() {
    setBusy(true);
    try {
      setRes(await api.simulate({ from_user: from, to_user: toUser, n }));
    } catch (e) {
      setRes({ error: String(e) } as SimResult);
    } finally {
      setBusy(false);
    }
  }

  const Meter = ({ label, role, before, after }: { label: string; role: string; before: number; after: number }) => {
    const col = (p: number) => (p > 100 ? "var(--critical)" : p < 70 ? "var(--good)" : "var(--series-1)");
    return (
      <div style={{ flex: 1 }}>
        <div className="flex between" style={{ fontSize: 12, marginBottom: 6 }}>
          <strong>{label}</strong><span className="muted">{role}</span>
        </div>
        {[["Before", before], ["After", after]].map(([t, p]) => (
          <div className="bar-row" key={t as string} style={{ gridTemplateColumns: "52px 1fr 46px" }}>
            <span className="name">{t}</span>
            <div className="bar-track">
              <div className="bar-fill" style={{ width: `${Math.min(Number(p) / 1.6, 100)}%`, background: col(Number(p)) }} />
              <div className="bar-threshold" style={{ left: `${(1 / 1.6) * 100}%` }} />
            </div>
            <span className="num" style={{ color: col(Number(p)) }}>{p}%</span>
          </div>
        ))}
      </div>
    );
  };

  return (
    <Card title="What-If Reassignment Simulator" icon={<IcSpark size={15} />}
      hint="Counterfactual capacity planning · checks skill, efficiency & experience — not just free capacity · nothing is executed">
      <div className="flex" style={{ gap: 10, flexWrap: "wrap", marginBottom: 14 }}>
        <label className="muted" style={{ fontSize: 12 }}>Move
          <select className="sim-select" value={n} onChange={(e) => setN(Number(e.target.value))}>
            {[1, 2, 3, 4, 5].map((x) => <option key={x} value={x}>{x} case{x > 1 ? "s" : ""}</option>)}
          </select>
        </label>
        <label className="muted" style={{ fontSize: 12 }}>from
          <select className="sim-select" value={from} onChange={(e) => { setFrom(e.target.value); setTo(""); setRes(null); }}>
            {workload.map((w) => <option key={w.user} value={w.user}>{w.user} ({w.utilization_pct}%)</option>)}
          </select>
        </label>
        <label className="muted" style={{ fontSize: 12 }}>to
          <select className="sim-select" value={toUser} onChange={(e) => { setTo(e.target.value); setRes(null); }}>
            {peers.map((w) => <option key={w.user} value={w.user}>{w.user} ({w.utilization_pct}%, {w.role.replace("PV ", "").replace("Safety ", "")})</option>)}
          </select>
        </label>
        <button className="btn primary" onClick={run} disabled={busy || !from || !toUser}>
          <IcUsers size={14} /> {busy ? "Simulating…" : "Simulate"}
        </button>
      </div>

      {res && !res.error && (
        <div>
          <div className="flex" style={{ gap: 24, alignItems: "flex-start" }}>
            <Meter label={res.from.user} role={res.from.tier ? `${res.from.tier} · ${res.from.role.replace("Safety ", "").replace("PV ", "")}` : res.from.role} before={res.from.before_pct} after={res.from.after_pct} />
            <Meter label={res.to.user} role={res.to.tier ? `${res.to.tier} · ${res.to.efficiency}× norm · ${res.to.experience} handled` : res.to.role} before={res.to.before_pct} after={res.to.after_pct} />
          </div>
          <div className={`sim-verdict ${res.qualified ? "ok" : "bad"}`}>
            <span className="ic">{res.qualified ? <IcCheck size={15} /> : <IcAlert size={15} />}</span>
            <span>{res.qualification_note}</span>
          </div>
          <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>
            Moving {res.moved_count} case(s): {res.moved_cases.join(", ")}.
            {res.to.after_pct > 100
              ? ` ⚠ This pushes ${res.to.user} over capacity (${res.to.after_pct}%) — overload is shifted, not relieved.`
              : res.relieved_from_overload > 0
                ? ` ✓ Relieves ${res.from.user}'s overload cleanly.`
                : ""}
          </div>
        </div>
      )}
      {res?.error && <div className="muted">Error: {res.error}</div>}
      {!res && <div className="muted" style={{ fontSize: 12 }}>Pick a move and simulate to preview the capacity impact before approving it.</div>}
    </Card>
  );
}
