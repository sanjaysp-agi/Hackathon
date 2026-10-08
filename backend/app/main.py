"""FastAPI app for the Intelligent Workflow Manager.

Thin HTTP layer over the deterministic engine (GET endpoints) plus the agentic
chat + governance endpoints added in later phases. The engine is rebuilt per
request from SQLite — cheap at demo scale and always reflects the current DB.
"""
from __future__ import annotations

import math
import typing

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from . import mutations
from .engine import Engine, Store


def _clean(obj):
    """Recursively replace NaN/inf (from pandas) with None so JSON is valid."""
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    return obj


class SafeJSON(JSONResponse):
    """Default response class that sanitizes NaN/inf before serializing."""

    def render(self, content: typing.Any) -> bytes:  # type: ignore[override]
        return super().render(_clean(content))


app = FastAPI(
    title="Intelligent Workflow Manager",
    version="0.1.0",
    default_response_class=SafeJSON,
)

# Dev CORS: allow the Vite dev server.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def engine() -> Engine:
    try:
        return Engine(Store())
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"engine init failed (did you run build_db.py?): {e}")


@app.get("/api/health")
def health():
    return engine().workflow_health()


@app.get("/api/risk/regulatory")
def regulatory(level: str | None = None, team: str | None = None):
    return engine().regulatory_risk(level=level, team=team)


@app.get("/api/risk/sla")
def sla(activity: str | None = None, team: str | None = None):
    return engine().sla_risk(activity=activity, team=team)


@app.get("/api/bottlenecks")
def bottlenecks():
    return engine().bottlenecks()


@app.get("/api/workload")
def workload(team: str | None = None):
    return engine().workload(team=team)


@app.get("/api/stuck")
def stuck():
    return engine().stuck_cases()


@app.get("/api/rebalance")
def rebalance(unit: str = "Medical Review"):
    return engine().rebalance_plan(unit)


@app.get("/api/briefing")
def briefing():
    return engine().daily_briefing()


class SimulateBody(BaseModel):
    from_user: str
    to_user: str
    case_ids: list[str] | None = None
    n: int | None = None


@app.post("/api/simulate")
def simulate(body: SimulateBody):
    return engine().simulate_reassignment(
        body.from_user, body.to_user, case_ids=body.case_ids, n=body.n
    )


@app.get("/api/cases")
def cases(sort: str = "risk"):
    """Active-case list for the critical-cases table, enriched with risk level."""
    e = engine()
    reg = {r["case_id"]: r for r in e.regulatory_risk()["evidence"]}
    stuck_ids = {r["case_id"] for r in e.stuck_cases()["evidence"]}
    rows = []
    for r in reg.values():
        rows.append(
            {
                "case_id": r["case_id"],
                "receipt": r["receipt"],
                "seriousness": r["seriousness"],
                "complexity": r["complexity"],
                "stage": r["stage"],
                "team": r["team"],
                "owner": r["assigned_to"],
                "level": r["level"],
                "days_to_sdd": r["days_to_sdd"],
                "days_to_cdd": r["days_to_cdd"],
                "breach_prob": r["breach_prob"],
                "is_stuck": r["case_id"] in stuck_ids,
            }
        )
    order = {"High": 0, "Medium": 1, "Low": 2}
    if sort == "deadline":
        rows.sort(key=lambda x: x["days_to_sdd"] if x["days_to_sdd"] is not None else 1e9)
    else:
        rows.sort(key=lambda x: (order.get(x["level"], 3),
                                 x["days_to_sdd"] if x["days_to_sdd"] is not None else 1e9))
    return {"count": len(rows), "cases": rows}


@app.get("/api/cases/{case_id}")
def case_detail(case_id: str):
    d = engine().case_detail(case_id)
    if "error" in d:
        raise HTTPException(404, d["error"])
    return d


@app.get("/api/cases/{case_id}/next-best-action")
def case_nba(case_id: str):
    return engine().next_best_action(case_id=case_id)


@app.get("/api/next-best-action")
def nba(team: str | None = None):
    return engine().next_best_action(team=team)


class ReassignBody(BaseModel):
    to_user: str
    note: str | None = None


@app.post("/api/cases/{case_id}/reassign")
def reassign(case_id: str, body: ReassignBody):
    """Execute a human-confirmed reassignment (blocks unqualified reviewers)."""
    r = mutations.reassign_case(case_id, body.to_user, body.note)
    if not r.get("ok"):
        raise HTTPException(409, r.get("error") or "reassignment blocked")
    return r


@app.post("/api/reset")
def reset():
    """Restore the baseline LSMV snapshot (keeps the audit trail)."""
    return mutations.reset_to_baseline()


@app.get("/api/analytics")
def analytics():
    """Caseload breakdowns for the stage table + classification charts."""
    return engine().caseload_analytics()


@app.get("/api/overview")
def overview():
    """Single call that powers the dashboard landing page."""
    e = engine()
    active_by_stage = e.active["current_activity"].value_counts()
    return {
        "health": e.workflow_health(),
        "regulatory": e.regulatory_risk(),
        "sla": e.sla_risk(),
        "bottlenecks": e.bottlenecks(),
        "workload": e.workload(),
        "stuck": e.stuck_cases(),
        "next_best_action": e.next_best_action(),
        "caseload": {
            "total": int(len(e.cases)),
            "active": int(len(e.active)),
            "closed": int(len(e.cases) - len(e.active)),
            "by_stage": [{"stage": k, "count": int(v)} for k, v in active_by_stage.items()],
        },
        "as_of": e.now.isoformat(),
    }


# --- Chat + governance endpoints are registered in later phases ----------
try:
    from .agent import register_agent_routes  # noqa: E402

    register_agent_routes(app, engine)
except Exception:  # agent module arrives in Phase 3; ignore until then
    pass
