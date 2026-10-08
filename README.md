# Intelligent Workflow Manager — LSMV PV Control Tower
**Hack_2026_008** · Agentic AI control tower for pharmacovigilance workflow management

Turns LSMV workflow data from *"what happened"* (static QBE/LSBI reports) into a
live control tower that answers **what is happening, why, what happens next, and
what to do about it** — with every number computed deterministically and every
AI claim grounded in that data.

---

## Architecture in one line

> **The engine computes the numbers (deterministic Python). Claude explains,
> predicts, and recommends — grounded in those numbers, never inventing them.**

That split is what makes this audit-ready for a regulated PV context: an auditor
can re-run the math; the AI only adds the narrative on top, and every tool call
and decision is logged. See `ARCHITECTURE.md` for the full design.

```
React + TS dashboard  ──REST──▶  FastAPI  ──▶  Metrics & Risk Engine (deterministic)
   drill-down + chat   ──SSE──▶   /api/chat ──▶  Claude on AWS Bedrock + engine tools
                                   /api/audit ──▶ governance / audit log
```

## Stack

| Layer | Tech |
|---|---|
| Frontend | React + TypeScript + Vite (validated dataviz palette, light/dark) |
| Backend | Python + FastAPI |
| Data | pandas + SQLite (snapshot model) |
| AI | Claude on **AWS Bedrock** — Opus 4.8 (`us.anthropic.claude-opus-4-8`) |
| Agent | Claude tool-calling over a typed engine toolbox (grounded + auditable) |

## Run it

```bash
# 1. Backend  (Python 3.14 via the `py` launcher on Windows)
cd backend
py -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe scripts/check_bedrock.py       # verify Bedrock access
.venv/Scripts/python.exe scripts/build_db.py            # synth data -> SQLite
.venv/Scripts/python.exe -m uvicorn app.main:app --port 8000 --reload

# 2. Frontend
cd frontend
npm install
npm run dev            # http://localhost:5173  (proxies /api to :8000)

# 3. Tests (the audit story — deterministic engine)
cd backend
.venv/Scripts/python.exe -m pytest tests -q
```

`.env` holds `AWS_BEARER_TOKEN_BEDROCK` (region defaults to `us-east-1`). When the
real LSMV extract arrives, drop its CSVs into `backend/data/` (same column names)
and run `scripts/build_db.py --no-synth`.

## Acceptance criteria → where it lives

| # | Criterion | Implementation |
|---|---|---|
| 1 | Workflow health score + status | `engine.workflow_health()` · gauge on dashboard |
| 2 | Regulatory risk before overdue | `engine.regulatory_risk()` (work-left vs time-left) |
| 3 | Predictive SLA risk from history | `engine.sla_risk()` (elapsed vs p80 benchmark) |
| 4 | Bottleneck detection | `engine.bottlenecks()` · bottleneck bar panel |
| 5 | Workload intelligence | `engine.workload()` · utilization bars |
| 6 | Explainability | every engine result carries `reason` + evidence; case "why at risk" panel |
| 7 | Next best action | `engine.next_best_action()` · NBA cards (Accept/Modify/Dismiss) |
| 8 | Drill-down | dashboard → team → case → activity timeline |
| 9 | Agentic Q&A | `/api/chat` — Claude + engine tools, streamed |
| 10 | Governance | AI recommends, human decides; `/api/audit` logs every turn & decision |

See `DEMO.md` for the 90-second demo script.
