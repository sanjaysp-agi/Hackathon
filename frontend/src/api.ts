// Typed API client for the Intelligent Workflow Manager backend.

export type Status = "Green" | "Amber" | "Red";

export interface HealthComponent {
  name: string;
  label?: string;
  description?: string;
  penalty_fraction: number;
  weight: number;
  points_lost: number;
}
export interface Health {
  value: number;
  status: Status;
  formula?: string;
  bands?: { green: string; amber: string; red: string };
  components: HealthComponent[];
  explanation_inputs: Record<string, number>;
}

export type Level = "High" | "Medium" | "Low";

export interface RegRow {
  case_id: string;
  receipt: string;
  stage: string;
  team: string;
  seriousness: string;
  complexity: string;
  assigned_to: string;
  level: Level;
  days_to_sdd: number;
  days_to_cdd: number;
  breach_prob: number;
  reason: string;
}
export interface Regulatory {
  value: number;
  status: Status;
  counts: { High: number; Medium: number; Low: number };
  evidence: RegRow[];
}

export interface SlaRow {
  case_id: string;
  receipt: string;
  stage: string;
  team: string;
  assigned_to: string;
  complexity: string;
  activity_aging_hours: number;
  historical_hours: number;
  aging_ratio: number;
  activity_due_status: string;
  breach_prob: number;
  level: Level;
  reason: string;
}
export interface Sla { value: number; status: Status; counts: { High: number; Medium: number; Low: number }; evidence: SlaRow[]; }

export interface BottleneckRow {
  processing_unit: string;
  stage: string;
  active_wip: number;
  breached: number;
  approaching: number;
  avg_aging_hours: number;
  historical_median_hours: number;
  aging_ratio: number;
  status: "Critical" | "At Risk" | "Healthy";
  contributing_cases: string[];
  explanation?: string | null;
  management_action?: string | null;
  reason: string;
}
export interface Bottlenecks {
  value: string | null;
  max_breached: number;
  status: Status;
  evidence: BottleneckRow[];
}

export interface WorkloadRow {
  user: string;
  team: string;
  role: string;
  available_hours: number;
  planned_hours: number;
  wip: number;
  utilization: number;
  utilization_pct: number;
  state: "overloaded" | "balanced" | "slack";
  management_action: string;
}
export interface Workload {
  value: string[];
  status: Status;
  imbalance_index: number;
  evidence: WorkloadRow[];
}

export interface StuckRow {
  case_id: string;
  receipt: string;
  activity_name: string;
  team: string;
  assigned_to: string;
  activity_aging_hours: number;
  historical_hours: number;
  x_over_norm: number;
  reassignment_count: number;
  reason: string;
}
export interface Stuck { value: number; status: Status; evidence: StuckRow[]; }

export interface NbaCandidate {
  case_id: string;
  recommended_action: string;
  score: number;
  level: string;
  stage?: string;
  team?: string;
  rationale: string[];
  human_approval_required: boolean;
}
export interface Nba { value: NbaCandidate | null; candidates: NbaCandidate[]; }

export interface SimResult {
  from: { user: string; role: string; tier?: string; before_pct: number; after_pct: number };
  to: { user: string; role: string; tier?: string; efficiency?: number; experience?: number; before_pct: number; after_pct: number };
  moved_cases: string[];
  moved_count: number;
  qualified: boolean;
  suitability_score?: number | null;
  qualification_note: string;
  relieved_from_overload: number;
  summary: string;
  error?: string;
}

export interface RebalanceMove {
  case_id: string;
  receipt?: string;
  from: string;
  to: string;
  role: string;
  to_tier?: string;
  to_efficiency?: number;
  to_experience?: number;
  suitability?: number;
  complexity?: string;
  seriousness?: string;
  why: string;
  warning?: string | null;
}
export interface RebalancePlan {
  unit: string;
  moves: RebalanceMove[];
  move_count: number;
  note: string;
}

export interface Briefing {
  as_of: string;
  headline: string;
  p1_cases: Array<{
    case_id: string; receipt: string; stage: string; owner: string;
    days_to_sdd: number; action: string; reason: string;
  }>;
  critical_bottleneck: string;
  overloaded_users: string[];
  aging_count: number;
}

export interface Caseload {
  total: number;
  active: number;
  closed: number;
  by_stage: { stage: string; count: number }[];
}
export interface Overview {
  health: Health;
  regulatory: Regulatory;
  sla: Sla;
  bottlenecks: Bottlenecks;
  workload: Workload;
  stuck: Stuck;
  next_best_action: Nba;
  caseload?: Caseload;
  as_of: string;
}

export interface AnalyticsCase {
  case_id: string;
  receipt: string;
  seriousness: string;
  complexity: string;
  assigned_to: string;
  activity_due_status: string;
  days_to_sdd: number | null;
  breach_prob: number;
  level: Level;
}
export interface StageRow {
  stage: string;
  count: number;
  high_reg: number;
  breached: number;
  cases: AnalyticsCase[];
}
export interface ComplexityStage { stage: string; Low: number; Medium: number; Large: number; }
export interface Slice { label: string; value: number; }
export interface ActiveCase {
  case_id: string;
  receipt: string;
  stage: string;
  assigned_to: string;
  seriousness: string;
  seriousness_bucket: string;
  complexity: string;
  report_type: string;
  deadline_bucket: string;
  days_to_sdd: number | null;
  breach_prob: number;
  activity_due_status: string;
  level: Level;
}
export interface Analytics {
  active_total: number;
  stages: StageRow[];
  complexity_by_stage: ComplexityStage[];
  complexity_levels: string[];
  seriousness: Slice[];
  classification: Slice[];
  deadline_watch: Slice[];
  cases: ActiveCase[];
}

export interface CaseRow {
  case_id: string;
  receipt: string;
  seriousness: string;
  complexity: string;
  stage: string;
  team: string;
  owner: string;
  level: Level;
  days_to_sdd: number;
  days_to_cdd: number;
  breach_prob: number;
  is_stuck: boolean;
}

export interface CaseDetail {
  case: Record<string, any>;
  activities: Array<Record<string, any>>;
  assignments: Array<Record<string, any>>;
  regulatory_risk: RegRow | null;
  sla_risk: SlaRow[];
  stuck: StuckRow[];
}

async function get<T>(path: string): Promise<T> {
  const r = await fetch(`/api${path}`);
  if (!r.ok) throw new Error(`${path} -> ${r.status}`);
  return r.json();
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(`/api${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${path} -> ${r.status}`);
  return r.json();
}

export const api = {
  overview: () => get<Overview>("/overview"),
  analytics: () => get<Analytics>("/analytics"),
  cases: (sort = "risk") => get<{ count: number; cases: CaseRow[] }>(`/cases?sort=${sort}`),
  caseDetail: (id: string) => get<CaseDetail>(`/cases/${id}`),
  caseNba: (id: string) => get<Nba>(`/cases/${id}/next-best-action`),
  regulatory: (level?: string) =>
    get<Regulatory>(`/risk/regulatory${level ? `?level=${level}` : ""}`),
  briefing: () => get<Briefing>("/briefing"),
  audit: (caseId?: string) =>
    get<{ count: number; entries: Array<{ ts: string; kind: string; case_id: string | null; recommended_action: string | null; decision: string | null; note: string | null }> }>(
      `/audit?limit=100${caseId ? `&case_id=${encodeURIComponent(caseId)}` : ""}`),
  rebalance: (unit = "Medical Review") => get<RebalancePlan>(`/rebalance?unit=${encodeURIComponent(unit)}`),
  simulate: (body: { from_user: string; to_user: string; n?: number; case_ids?: string[] }) =>
    post<SimResult>("/simulate", body),
  reassign: (caseId: string, to_user: string, note?: string) =>
    post<{ ok: boolean; case_id: string; from: string; to: string; stage: string; warning?: string | null; capacity?: { hours: number; from_pct: number; to_pct: number } | null }>(
      `/cases/${encodeURIComponent(caseId)}/reassign`, { to_user, note }),
  reset: () => post<{ ok: boolean; message: string }>("/reset", {}),
};

export interface ActionProposal {
  action: "reassign";
  case_id: string;
  receipt: string;
  from_user: string;
  to_user: string;
  stage: string;
  complexity?: string;
  seriousness?: string;
  tier?: string;
  score?: number;
  warning?: string | null;
  blocked: boolean;
  reason?: string | null;
}
