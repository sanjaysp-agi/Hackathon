import { useCallback, useEffect, useState } from "react";
import { BrowserRouter, Routes, Route, useNavigate, useLocation } from "react-router-dom";
import Dashboard from "./pages/Dashboard";
import CaseDetail from "./CaseDetail";
import Chat from "./Chat";
import { api, type NbaCandidate, type Overview as Ov } from "./api";
import {
  IcBack, IcChat, IcCheck, IcFunnel, IcGrid, IcMoon, IcPulse,
  IcReset, IcShield, IcSpark, IcSun,
} from "./icons";

const NAV = [
  { id: "overview", label: "Overview", icon: <IcGrid size={16} /> },
  { id: "operations", label: "Operations", icon: <IcFunnel size={16} /> },
  { id: "actions", label: "Action Center", icon: <IcSpark size={16} /> },
  { id: "logs", label: "Action Logs", icon: <IcShield size={16} /> },
];

/** Single-click dark/light switch, lives top-right in the command bar.
    Persists the choice to localStorage. */
function ThemeToggle() {
  const [dark, setDark] = useState(
    document.documentElement.getAttribute("data-theme") !== "light"
  );
  useEffect(() => {
    const mode = dark ? "dark" : "light";
    document.documentElement.setAttribute("data-theme", mode);
    try { localStorage.setItem("iwm-theme", mode); } catch { /* ignore */ }
  }, [dark]);
  return (
    <button className="btn sm" onClick={() => setDark((d) => !d)} aria-label="Toggle theme">
      {dark ? <><IcSun size={14} /> Light</> : <><IcMoon size={14} /> Dark</>}
    </button>
  );
}

/** Live wall clock in the command bar — reinforces the "live control tower" feel. */
function Clock() {
  const [now, setNow] = useState(new Date());
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);
  return (
    <span className="clock" title="Local time">
      <span className="live" />
      {now.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
    </span>
  );
}

/** Sidebar rail: brand, section nav (scrolls the single page + highlights the
    section currently in view), and footer controls. */
function Rail({ ov, active, go, onAsk }: {
  ov: Ov | null; active: string; go: (id: string) => void; onAsk: () => void;
}) {
  const regHigh = ov?.regulatory.counts.High ?? 0;
  return (
    <aside className="rail">
      <div className="brand" style={{ cursor: "pointer" }} onClick={() => go("overview")}>
        <div className="logo"><IcPulse size={19} /></div>
        <div>
          <h1>Intelligent<br />Workflow Manager</h1>
          <div className="sub">LSMV Control Tower</div>
        </div>
      </div>
      <nav>
        {NAV.map((n) => (
          <button key={n.id} onClick={() => go(n.id)}
            className={`navitem ${active === n.id ? "active" : ""}`}>
            <span className="ic">{n.icon}</span>
            {n.label}
            {n.id === "risk" && regHigh > 0 && <span className="count alert">{regHigh}</span>}
          </button>
        ))}
      </nav>
      <div className="spacer-fill" />
      <div className="railfoot">
        <button className="btn primary" onClick={onAsk}><IcChat size={14} /> Ask the Agent</button>
        <div className="asof" style={{ justifyContent: "center" }}>
          <span className="live" /> connected to LSMV
        </div>
      </div>
    </aside>
  );
}

/** Page header shown above the scrolling content. */
export function PageHead({ title, subtitle, asOf }: { title: string; subtitle: string; asOf?: string }) {
  const when = asOf ? new Date(asOf).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }) : null;
  return (
    <div className="pagehead">
      <div className="titles">
        <h2>{title}</h2>
        <p>{subtitle}</p>
      </div>
      {when && <div className="asof"><span className="live" /> LSMV snapshot · {when} · 165 cases</div>}
    </div>
  );
}

function Shell() {
  const loc = useLocation();
  const nav = useNavigate();
  const [toast, setToast] = useState<string | null>(null);
  const [chatOpen, setChatOpen] = useState(false);
  const [ov, setOv] = useState<Ov | null>(null);
  const [active, setActive] = useState("overview");
  const [rev, setRev] = useState(0);  // bumps to force a dashboard refetch after a mutation
  const atHome = loc.pathname === "/";

  // A mutation (agent reassignment / reset) dispatches "iwm:refetch".
  useEffect(() => {
    const h = () => setRev((r) => r + 1);
    window.addEventListener("iwm:refetch", h);
    return () => window.removeEventListener("iwm:refetch", h);
  }, []);

  async function doReset() {
    if (!window.confirm("Reset the caseload to the baseline LSMV snapshot? This undoes any agent reassignments (the audit log is kept).")) return;
    try {
      await api.reset();
      window.dispatchEvent(new CustomEvent("iwm:refetch"));
      setToast("Caseload reset to baseline — audit trail preserved");
      setTimeout(() => setToast(null), 2800);
    } catch { /* ignore */ }
  }

  // Scroll a dashboard section into view; if we're on a case page, go home first.
  const go = useCallback((id: string) => {
    const doScroll = () => {
      const el = document.getElementById(id);
      if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
      setActive(id);
    };
    if (loc.pathname !== "/") { nav("/"); setTimeout(doScroll, 90); }
    else doScroll();
  }, [loc.pathname, nav]);

  function goBack() {
    if (window.history.length > 1) nav(-1);
    else nav("/");
  }

  // Shared overview load for the rail badge; the Dashboard fetches its own copy.
  useEffect(() => {
    let on = true;
    api.overview().then((o) => on && setOv(o)).catch(() => {});
    return () => { on = false; };
  }, [loc.pathname, rev]);

  // Scrollspy: highlight the nav item whose section is nearest the top as the
  // window scrolls (the page scrolls on the window, not an inner container).
  useEffect(() => {
    if (!atHome) return;
    const onScroll = () => {
      const secs = Array.from(document.querySelectorAll<HTMLElement>("[data-section]"));
      if (!secs.length) return;
      let cur = secs[0].id;
      for (const s of secs) {
        if (s.getBoundingClientRect().top <= 140) cur = s.id;
      }
      setActive(cur);
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
    return () => window.removeEventListener("scroll", onScroll);
  }, [atHome, ov]);

  async function onDecision(c: NbaCandidate, action: string) {
    try {
      await fetch("/api/decisions", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ case_id: c.case_id, recommended_action: c.recommended_action, decision: action }),
      });
    } catch { /* optional */ }
    setToast(`${action} · ${c.recommended_action} on ${c.case_id} — logged`);
    setTimeout(() => setToast(null), 2800);
  }

  const crumb = atHome
    ? (NAV.find((n) => n.id === active)?.label ?? "Overview")
    : (loc.pathname.startsWith("/case/") ? "Case detail" : "");

  return (
    <div className="app">
      <Rail ov={ov} active={active} go={go} onAsk={() => setChatOpen(true)} />
      <div className="main">
        <div className="cmdbar">
          <div className="left">
            {!atHome && (
              <button className="btn sm" onClick={goBack} aria-label="Go back"><IcBack size={14} /> Back</button>
            )}
            <span className="crumbs">Control Tower{crumb ? ` / ${crumb}` : ""}</span>
          </div>
          <div className="right">
            <Clock />
            <button className="btn sm" onClick={doReset} title="Reset the caseload to the baseline snapshot"><IcReset size={13} /> Reset</button>
            <button className="btn sm" onClick={() => setChatOpen(true)}><IcChat size={13} /> Ask AI</button>
            <ThemeToggle />
          </div>
        </div>
        <Routes>
          <Route path="/" element={<Dashboard key={rev} onDecision={onDecision} go={go} />} />
          <Route path="/case/:id" element={<CaseDetail />} />
        </Routes>
      </div>

      {chatOpen && <div className="scrim" onClick={() => setChatOpen(false)} />}
      <Chat open={chatOpen} onClose={() => setChatOpen(false)} />
      {!chatOpen && (
        <button className="chat-fab" onClick={() => setChatOpen(true)} aria-label="Ask the AI agent">
          <IcChat size={21} />
        </button>
      )}

      {toast && (
        <div className="toast">
          <span style={{ color: "var(--good)" }}><IcCheck size={16} /></span>{toast}
        </div>
      )}
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Shell />
    </BrowserRouter>
  );
}
