import { useRef, useState } from "react";
import { Markdown } from "./markdown";
import { ChatChart, type ChartSpec } from "./ChatChart";
import { api, type ActionProposal, type SimResult } from "./api";
import { IcSpark, IcTool, IcClose, IcUsers, IcCheck, IcArrow, IcAlert } from "./icons";

type Status = "pending" | "working" | "confirmed" | "cancelled" | "error";
interface Msg {
  role: "user" | "assistant" | "tool" | "chart" | "proposal" | "whatif";
  text: string; spec?: ChartSpec; prop?: ActionProposal; status?: Status; sim?: SimResult;
}
interface Reviewer { user: string; role: string; pct: number; state: string; }

const SUGGESTED = [
  "Compare reviewer workload",
  "Break down active cases by seriousness",
  "Reassign CASE-2026-0003 to a better-suited reviewer",
  "Why is Medical Review a bottleneck?",
];

export default function Chat({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [reviewers, setReviewers] = useState<Reviewer[]>([]);
  const [wf, setWf] = useState({ open: false, from: "", to: "", n: 1, running: false });
  const scroller = useRef<HTMLDivElement>(null);

  // /what-if simulator — a counterfactual run entirely in chat. Uses the pure
  // /api/simulate endpoint (never writes), so the dataset is untouched.
  async function openWhatIf() {
    let revs = reviewers;
    if (!revs.length) {
      try {
        const ov = await api.overview();
        revs = ov.workload.evidence.map((w) => ({ user: w.user, role: w.role, pct: w.utilization_pct, state: w.state }));
        setReviewers(revs);
      } catch { /* ignore */ }
    }
    const over = revs.find((r) => r.state === "overloaded");
    const slack = [...revs].reverse().find((r) => r.state !== "overloaded");
    setWf({ open: true, running: false, n: 1,
      from: over?.user ?? revs[0]?.user ?? "",
      to: slack?.user ?? revs[revs.length - 1]?.user ?? "" });
    scrollDown();
  }

  async function runWhatIf() {
    if (!wf.from || !wf.to || wf.from === wf.to) return;
    setWf((w) => ({ ...w, running: true }));
    try {
      const sim = await api.simulate({ from_user: wf.from, to_user: wf.to, n: wf.n });
      setMsgs((m) => [...m, { role: "whatif", text: "", sim }]);
    } catch (e) {
      setMsgs((m) => [...m, { role: "assistant", text: `⚠ Simulation failed: ${String(e)}` }]);
    }
    setWf((w) => ({ ...w, open: false, running: false }));
    scrollDown();
  }

  function scrollDown() {
    requestAnimationFrame(() => {
      scroller.current?.scrollTo({ top: scroller.current.scrollHeight });
    });
  }

  const setStatus = (idx: number, status: Status) =>
    setMsgs((m) => m.map((x, i) => (i === idx ? { ...x, status } : x)));

  async function confirmProposal(idx: number, p: ActionProposal) {
    setStatus(idx, "working");
    try {
      const r = await api.reassign(p.case_id, p.to_user, p.reason ?? undefined);
      setStatus(idx, "confirmed");
      const cap = r.capacity ? `\n\nCapacity shifted: ${p.from_user} → ${r.capacity.from_pct}%, ${p.to_user} → ${r.capacity.to_pct}%.` : "";
      setMsgs((m) => [...m, { role: "assistant", text: `✓ Reassigned **${p.receipt}** (${p.stage}) from ${p.from_user} to **${p.to_user}** — applied and logged to Action Logs.${cap}${r.warning ? `\n\n⚠ ${r.warning}` : ""}` }]);
      window.dispatchEvent(new CustomEvent("iwm:refetch"));
    } catch (e) {
      setStatus(idx, "error");
      setMsgs((m) => [...m, { role: "assistant", text: `⚠ Could not apply the reassignment: ${String(e)}` }]);
    }
    scrollDown();
  }

  // Build a text-level transcript the agent can reason over (multi-turn memory).
  // Non-text events (what-if, proposals) are summarized so follow-ups like
  // "do it" have the specific case IDs + target to act on.
  function toHistory(list: Msg[]) {
    const h: { role: string; content: string }[] = [];
    for (const m of list) {
      if (m.role === "user") h.push({ role: "user", content: m.text });
      else if (m.role === "assistant" && m.text.trim()) h.push({ role: "assistant", content: m.text });
      else if (m.role === "whatif" && m.sim && !m.sim.error) {
        const s = m.sim;
        h.push({ role: "assistant", content: `[What-if simulation] Moving ${s.moved_count} case(s) ${s.moved_cases.join(", ")} from ${s.from.user} to ${s.to.user}: ${s.from.user} ${s.from.before_pct}%→${s.from.after_pct}%, ${s.to.user} ${s.to.before_pct}%→${s.to.after_pct}%. ${s.qualified ? "Target is qualified." : "Target is NOT qualified for this work."}` });
      } else if (m.role === "proposal" && m.prop) {
        const st = m.status === "confirmed" ? " (confirmed & applied)" : m.status === "cancelled" ? " (cancelled)" : "";
        h.push({ role: "assistant", content: `[Proposed reassignment] ${m.prop.case_id} from ${m.prop.from_user} to ${m.prop.to_user}${st}.` });
      }
    }
    return h.slice(-20);
  }

  async function send(text: string) {
    if (!text.trim() || busy) return;
    if (text.trim().toLowerCase().startsWith("/what-if")) { setInput(""); openWhatIf(); return; }
    setInput("");
    const history = toHistory(msgs);
    setMsgs((m) => [...m, { role: "user", text }]);
    setBusy(true);
    scrollDown();

    // Streaming SSE from /api/chat. The agent calls engine tools; we surface
    // tool calls as muted lines and stream the final answer token by token.
    let assistant = "";
    let assistantIdx = -1;
    try {
      const resp = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, history }),
      });
      if (!resp.ok || !resp.body) throw new Error(`chat ${resp.status}`);
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const lines = buf.split("\n\n");
        buf = lines.pop() ?? "";
        for (const chunk of lines) {
          const line = chunk.replace(/^data: /, "");
          if (!line) continue;
          let ev: any;
          try { ev = JSON.parse(line); } catch { continue; }
          if (ev.type === "tool") {
            setMsgs((m) => [...m, { role: "tool", text: `↳ ${ev.text}` }]);
            scrollDown();
          } else if (ev.type === "chart" && ev.spec) {
            // A new chart resets the current assistant text target so any
            // follow-up takeaway renders as a fresh bubble below the chart.
            setMsgs((m) => [...m, { role: "chart", text: "", spec: ev.spec }]);
            assistant = "";
            assistantIdx = -1;
            scrollDown();
          } else if (ev.type === "action_proposal") {
            setMsgs((m) => [...m, { role: "proposal", text: "", prop: ev as ActionProposal, status: "pending" }]);
            assistant = "";
            assistantIdx = -1;
            scrollDown();
          } else if (ev.type === "text") {
            assistant += ev.text;
            setMsgs((m) => {
              const copy = [...m];
              if (assistantIdx === -1) {
                copy.push({ role: "assistant", text: assistant });
                assistantIdx = copy.length - 1;
              } else {
                copy[assistantIdx] = { role: "assistant", text: assistant };
              }
              return copy;
            });
            scrollDown();
          } else if (ev.type === "error") {
            setMsgs((m) => [...m, { role: "assistant", text: `⚠ ${ev.text}` }]);
          }
        }
      }
    } catch (e) {
      setMsgs((m) => [...m, { role: "assistant", text: `⚠ ${String(e)}` }]);
    } finally {
      setBusy(false);
      scrollDown();
    }
  }

  return (
    <aside className={`chat ${open ? "open" : ""}`} aria-hidden={!open}>
      <div className="head">
        <span className="dot-live" />
        <IcSpark size={15} /> Ask the Agent
        <button className="chat-close btn ghost" onClick={onClose} aria-label="Close chat">
          <IcClose size={16} />
        </button>
      </div>
      <div className="msgs" ref={scroller}>
        {msgs.length === 0 && (
          <div className="muted" style={{ fontSize: 12 }}>
            Ask about deadlines, bottlenecks, workload, or a specific case. Answers
            are grounded in live workflow data and cite case IDs.
          </div>
        )}
        {msgs.map((m, i) =>
          m.role === "tool" ? (
            <div key={i} className="msg tool"><span className="ic"><IcTool size={12} /></span>{m.text.replace(/^↳\s*/, "").slice(0, 70)}</div>
          ) : m.role === "chart" && m.spec ? (
            <div key={i} className="msg chartmsg"><ChatChart spec={m.spec} /></div>
          ) : m.role === "whatif" && m.sim ? (
            <div key={i} className="msg whatifmsg">
              <div className="card nba-card" style={{ padding: 13 }}>
                <div className="nba-action"><IcTool size={14} /> What-if result <span className="muted" style={{ fontWeight: 400, fontSize: 11 }}>· simulation only</span></div>
                {m.sim.error ? (
                  <div className="sim-verdict bad" style={{ marginTop: 8 }}><span className="ic"><IcAlert size={13} /></span>{m.sim.error}</div>
                ) : (
                  <>
                    <div className="prop-line">Move {m.sim.moved_count} case{m.sim.moved_count === 1 ? "" : "s"}: <b>{m.sim.from.user}</b> <IcArrow size={12} /> <b>{m.sim.to.user}</b></div>
                    <div className="wf-ba">
                      <div className="wf-ba-row"><span>{m.sim.from.user}</span><span className="mono">{m.sim.from.before_pct}% → <b>{m.sim.from.after_pct}%</b></span></div>
                      <div className="wf-ba-row"><span>{m.sim.to.user}{m.sim.to.tier ? ` · ${m.sim.to.tier}` : ""}</span><span className="mono">{m.sim.to.before_pct}% → <b>{m.sim.to.after_pct}%</b></span></div>
                    </div>
                    {!m.sim.qualified && <div className="sim-verdict bad" style={{ fontSize: 11.5, padding: "7px 10px" }}><span className="ic"><IcAlert size={13} /></span>{m.sim.qualification_note}</div>}
                    <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>{m.sim.summary}</div>
                    <div className="wf-note">Hypothetical — dataset unchanged. Ask me to “reassign {m.sim.from.user}'s case to {m.sim.to.user}” to actually apply it.</div>
                  </>
                )}
              </div>
            </div>
          ) : m.role === "proposal" && m.prop ? (
            <div key={i} className="msg proposalmsg">
              <div className="card nba-card reassign" style={{ padding: 13 }}>
                <div className="nba-action"><IcUsers size={14} /> Proposed reassignment</div>
                <div className="prop-line">
                  Move <span className="mono">{m.prop.receipt}</span> <span className="muted">({m.prop.stage})</span> from <b>{m.prop.from_user}</b> <IcArrow size={12} /> <b>{m.prop.to_user}</b>
                </div>
                {m.prop.tier && <div className="prop-meta">{m.prop.to_user}: {m.prop.tier} · suitability {m.prop.score}</div>}
                {m.prop.warning && <div className="sim-verdict bad" style={{ fontSize: 11.5, marginTop: 8, padding: "7px 10px" }}><span className="ic"><IcAlert size={13} /></span>{m.prop.warning}</div>}
                {m.prop.blocked ? (
                  <div className="sim-verdict bad" style={{ marginTop: 8 }}><span className="ic"><IcAlert size={14} /></span>Blocked — {m.prop.to_user} isn't qualified for {m.prop.stage}.</div>
                ) : m.status === "confirmed" ? (
                  <div className="sim-verdict ok" style={{ marginTop: 8 }}><span className="ic"><IcCheck size={14} /></span>Applied & logged.</div>
                ) : m.status === "cancelled" ? (
                  <div className="muted" style={{ marginTop: 8, fontSize: 12 }}>Cancelled — nothing changed.</div>
                ) : (
                  <div className="nba-actions">
                    <button className="btn primary sm" disabled={m.status === "working"} onClick={() => confirmProposal(i, m.prop!)}>
                      {m.status === "working" ? "Applying…" : "Confirm & apply"}
                    </button>
                    <button className="btn ghost sm" disabled={m.status === "working"} onClick={() => setStatus(i, "cancelled")}>Cancel</button>
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div key={i} className={`msg ${m.role}`}>
              {m.role === "assistant" ? <Markdown text={m.text} /> : m.text}
            </div>
          )
        )}
        {wf.open && (
          <div className="msg whatif-form">
            <div className="card" style={{ padding: 13, background: "var(--surface-2)" }}>
              <div className="nba-action"><IcTool size={14} /> What-if simulator <span className="muted" style={{ fontWeight: 400, fontSize: 11 }}>· nothing changes</span></div>
              <div className="wf-row"><label>Move from</label>
                <select value={wf.from} onChange={(e) => setWf((w) => ({ ...w, from: e.target.value }))}>
                  {reviewers.map((r) => <option key={r.user} value={r.user}>{r.user} — {r.pct}% {r.state === "overloaded" ? "⚠" : ""}</option>)}
                </select>
              </div>
              <div className="wf-row"><label>to</label>
                <select value={wf.to} onChange={(e) => setWf((w) => ({ ...w, to: e.target.value }))}>
                  {reviewers.map((r) => <option key={r.user} value={r.user}>{r.user} — {r.pct}%</option>)}
                </select>
              </div>
              <div className="wf-row"><label>cases</label>
                <input type="number" min={1} max={10} value={wf.n} onChange={(e) => setWf((w) => ({ ...w, n: Math.max(1, Math.min(10, Number(e.target.value) || 1)) }))} style={{ width: 70 }} />
              </div>
              <div className="nba-actions">
                <button className="btn primary sm" disabled={wf.running || !wf.from || !wf.to || wf.from === wf.to} onClick={runWhatIf}>{wf.running ? "Running…" : "Run simulation"}</button>
                <button className="btn ghost sm" disabled={wf.running} onClick={() => setWf((w) => ({ ...w, open: false }))}>Cancel</button>
              </div>
              {wf.from === wf.to && wf.from && <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>Pick two different reviewers.</div>}
            </div>
          </div>
        )}
        {busy && <div className="typing"><span /><span /><span /></div>}
      </div>
      <div className="suggested">
        <button className="btn wf-chip" onClick={openWhatIf} disabled={busy}>⚖ /what-if</button>
        {SUGGESTED.map((s) => (
          <button key={s} className="btn" onClick={() => send(s)} disabled={busy}>{s}</button>
        ))}
      </div>
      <div className="composer">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send(input)}
          placeholder="Ask a question…"
          disabled={busy}
        />
        <button className="btn primary" onClick={() => send(input)} disabled={busy}>Send</button>
      </div>
    </aside>
  );
}
