import { useEffect, useState } from "react";
import { api, type NbaCandidate, type Overview as Ov } from "../api";
import { PageHead } from "../App";
import { IcChevron, IcFunnel, IcShield, IcSpark } from "../icons";
import { Hero } from "./Overview";
import { OperationsSection } from "./Operations";
import { CaseloadSection } from "./Caseload";
import { ActionsSection } from "./Actions";
import { LogsSection } from "./Audit";

/** An anchorable, foldable dashboard section. Click the header (or chevron) to
    collapse/expand; `id`/`data-section` drive scroll-to + sidebar scrollspy. */
function Section({
  id, title, subtitle, icon, action, children,
}: {
  id: string; title: string; subtitle?: string; icon: React.ReactNode;
  action?: React.ReactNode; children: React.ReactNode;
}) {
  const [open, setOpen] = useState(true);
  const toggle = () => setOpen((o) => !o);
  return (
    <section id={id} data-section={id} className={`dash-section ${open ? "" : "collapsed"}`}>
      <div className="sec-head" role="button" tabIndex={0} aria-expanded={open}
        onClick={toggle}
        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(); } }}>
        <span className="sec-ic">{icon}</span>
        <div className="sec-titles">
          <h2>{title}</h2>
          {subtitle && <p>{subtitle}</p>}
        </div>
        {action && <div className="sec-action" onClick={(e) => e.stopPropagation()}>{action}</div>}
        <span className="sec-chevron" data-open={open} aria-hidden="true"><IcChevron size={18} /></span>
      </div>
      {open && <div className="sec-body">{children}</div>}
    </section>
  );
}

/** The whole app, now a single scrolling control tower. The sidebar scrolls to
    these sections; each one collapses independently. Case drill-in is a route. */
export default function Dashboard({
  onDecision, go,
}: { onDecision: (c: NbaCandidate, a: string) => void; go: (id: string) => void }) {
  const [ov, setOv] = useState<Ov | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => { api.overview().then(setOv).catch((e) => setErr(String(e))); }, []);

  if (err) return <><PageHead title="Control Tower" subtitle="Connection error" /><div className="content"><div className="loading">Failed to load: {err}. Is the backend on :8000?</div></div></>;
  if (!ov) return <><PageHead title="Control Tower" subtitle="Loading…" /><div className="content"><div className="loading">Loading control tower…</div></div></>;

  return (
    <>
      <PageHead title="Control Tower" subtitle="One scrolling view of workflow health, risk, operations, and the actions that need a decision today." asOf={ov.as_of} />
      <div className="content">
        <section id="overview" data-section="overview" className="dash-section hero-section">
          <Hero ov={ov} go={go} />
          <div style={{ marginTop: 22 }}><CaseloadSection /></div>
        </section>

        <Section id="operations" icon={<IcFunnel size={18} />} title="Operations"
          subtitle="Where work is piling up, who is over capacity, and what a reassignment would do.">
          <OperationsSection ov={ov} />
        </Section>

        <Section id="actions" icon={<IcSpark size={18} />} title="Action Center"
          subtitle="The agent proposes; you decide. Every acceptance is recorded in the logs.">
          <ActionsSection onDecision={onDecision} />
        </Section>

        <Section id="logs" icon={<IcShield size={18} />} title="Action Logs"
          subtitle="Every AI answer and every human decision — timestamped and attributable.">
          <LogsSection />
        </Section>
      </div>
    </>
  );
}
