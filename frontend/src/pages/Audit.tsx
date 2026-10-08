import { useEffect, useState } from "react";
import { Card, Chip, DataTable, type Column } from "../components";
import { IcShield } from "../icons";

interface AuditEntry {
  _k: string;
  ts: string; kind: string; case_id: string | null;
  recommended_action: string | null; decision: string | null; note: string | null;
}

function fmt(iso: string) {
  try {
    return new Date(iso + "Z").toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit" });
  } catch { return iso; }
}

const COLUMNS: Column<AuditEntry>[] = [
  { key: "ts", header: "When (UTC)", className: "mono", value: (e) => e.ts, render: (e) => fmt(e.ts) },
  { key: "kind", header: "Type", value: (e) => (e.kind === "decision" ? "decision" : "AI chat"),
    render: (e) => <Chip status={e.kind === "decision" ? "Green" : "LOW"} label={e.kind === "decision" ? "decision" : "AI chat"} /> },
  { key: "case_id", header: "Case", className: "mono", value: (e) => e.case_id ?? "", render: (e) => e.case_id ?? "—" },
  { key: "recommended_action", header: "Recommended", value: (e) => e.recommended_action ?? "",
    render: (e) => <span style={{ textTransform: "capitalize" }}>{e.recommended_action ?? "—"}</span> },
  { key: "decision", header: "Decision", value: (e) => e.decision ?? "",
    render: (e) => <span style={{ textTransform: "capitalize" }}>{e.decision ?? "—"}</span> },
  { key: "note", header: "Detail", value: (e) => e.note ?? "",
    render: (e) => <span className="muted">{(e.note ?? "").slice(0, 90)}</span> },
];

/** Action-logs block: every AI answer + human decision. */
export function LogsSection() {
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/audit?limit=200").then((r) => r.json())
      .then((d) => setEntries((d.entries as AuditEntry[]).map((e, i) => ({ ...e, _k: String(i) }))))
      .catch((e) => setErr(String(e)));
  }, []);

  return (
    <Card title="Decision & Interaction Log" icon={<IcShield size={15} />} hint="AC-10 · each entry records the tools the agent used and the manager's decision">
      {err && <div className="muted">Failed to load: {err}</div>}
      <DataTable columns={COLUMNS} rows={entries} rowKey={(e) => e._k}
        empty="No audit entries yet. Ask the agent a question or accept a recommendation to populate the trail." />
    </Card>
  );
}
