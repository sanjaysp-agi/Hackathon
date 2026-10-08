"""Governed write layer — the small set of actions the agent can actually
EXECUTE, but only after a human confirms. Today: reassign a case.

Design: deliberately tiny, parameterized SQL. Reassignment reuses the engine's
`suitability` gate so an UNQUALIFIED reviewer is blocked rather than silently
chosen. Every applied write is appended to the audit trail (governance, AC-10),
and `reset_to_baseline` re-ingests the workbook so the demo is repeatable.
"""
from __future__ import annotations

import json
import math
import sqlite3
from datetime import datetime, timezone

from . import config
from .engine import Engine, Store


def _find_case(engine: Engine, case_id: str):
    df = engine.cases
    m = df[(df["case_id"] == case_id) | (df["receipt"] == case_id)]
    return None if m.empty else m.iloc[0]


def preview_reassign(case_id: str, to_user: str) -> dict:
    """Validate a proposed reassignment WITHOUT writing — used to build the
    confirm card the manager sees before anything changes."""
    engine = Engine(Store())
    row = _find_case(engine, case_id)
    if row is None:
        return {"ok": False, "error": f"Case {case_id} not found."}
    stage = str(row.get("current_activity") or "")
    from_user = row.get("assigned_to")
    if to_user not in engine.reviewers:
        return {"ok": False, "error": f"{to_user} is not a known reviewer."}
    if str(from_user) == str(to_user):
        return {"ok": False, "error": f"{row['case_id']} is already assigned to {to_user}."}
    suit = engine.suitability(to_user, stage, str(row.get("complexity") or ""),
                              str(row.get("seriousness") or ""))
    return {
        "ok": True,
        "case_id": row["case_id"], "receipt": row["receipt"],
        "stage": stage, "complexity": row.get("complexity"), "seriousness": row.get("seriousness"),
        "from_user": from_user, "to_user": to_user,
        "qualified": bool(suit.get("qualified")),
        "tier": suit.get("tier"), "score": suit.get("score"),
        "warning": suit.get("warning"),
    }


def reassign_case(case_id: str, to_user: str, note: str | None = None) -> dict:
    """Apply a reassignment: update the case owner, append an assignment-history
    row, bump the reassignment count, and write an audit record."""
    pv = preview_reassign(case_id, to_user)
    if not pv.get("ok"):
        return pv
    if not pv["qualified"]:
        return {"ok": False, "blocked": True, "suitability": pv,
                "error": (f"{to_user} is not qualified for {pv['stage']} "
                          f"(no completed {pv['stage']} history). Reassignment blocked.")}

    engine = Engine(Store())
    row = _find_case(engine, case_id)
    cid, receipt = row["case_id"], row["receipt"]
    from_user = row.get("assigned_to")
    new_count = int(float(row.get("reassignment_count") or 0)) + 1
    ts = datetime.now(timezone.utc).isoformat()

    con = sqlite3.connect(config.DB_PATH)
    try:
        cur = con.cursor()
        cur.execute("CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY AUTOINCREMENT,"
                    " ts TEXT, kind TEXT, case_id TEXT, recommended_action TEXT,"
                    " decision TEXT, note TEXT, detail TEXT)")
        cur.execute("UPDATE cases SET assigned_to=?, reassignment_count=? WHERE case_id=?",
                    (to_user, new_count, cid))
        cur.execute(
            "INSERT INTO assignments (event_id, case_id, receipt, activity_name,"
            " processing_unit, reassignment_number, changed_ts, from_user, to_user,"
            " reason, handover_status) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (f"ASG-{cid.replace('CASE-', '')}-{new_count:02d}", cid, receipt,
             pv["stage"], row.get("processing_unit"), new_count, ts, from_user,
             to_user, note or "Manager-approved reassignment", "Pending"),
        )

        # Shift estimated capacity from the old owner to the new one so the
        # utilization KPI responds. Per-item hours = a reviewer's planned ÷ WIP;
        # utilization% is recomputed by the engine from planned ÷ available.
        cap = engine.capacity
        cap_shift = None

        def _row(u):
            m = cap[cap["user"] == u]
            return m.iloc[0] if not m.empty else None

        src, dst = _row(from_user), _row(to_user)
        if src is not None and dst is not None:
            s_pl, s_wip = float(src.get("planned_hours") or 0), float(src.get("wip") or 0)
            s_av = float(src.get("available_hours") or 0) or 1.0
            d_pl, d_wip = float(dst.get("planned_hours") or 0), float(dst.get("wip") or 0)
            d_av = float(dst.get("available_hours") or 0) or 1.0
            per_item = round(s_pl / s_wip, 1) if s_wip >= 1 else 0.0
            ns_pl, ns_wip = max(0.0, round(s_pl - per_item, 1)), max(0.0, s_wip - 1)
            nd_pl, nd_wip = round(d_pl + per_item, 1), d_wip + 1

            def pct(pl, av):
                return int(math.floor(pl / av * 100 + 0.5))

            cur.execute("UPDATE user_capacity SET planned_hours=?, wip=?, utilization_pct=? WHERE user=?",
                        (ns_pl, ns_wip, pct(ns_pl, s_av), from_user))
            cur.execute("UPDATE user_capacity SET planned_hours=?, wip=?, utilization_pct=? WHERE user=?",
                        (nd_pl, nd_wip, pct(nd_pl, d_av), to_user))
            cap_shift = {"hours": per_item,
                         "from_pct": pct(ns_pl, s_av), "to_pct": pct(nd_pl, d_av)}

        cur.execute(
            "INSERT INTO audit (ts, kind, case_id, recommended_action, decision, note, detail)"
            " VALUES (?,?,?,?,?,?,?)",
            (ts, "mutation", cid, "reassign", "applied", f"{from_user} → {to_user}",
             json.dumps({"from": from_user, "to": to_user, "stage": pv["stage"],
                         "tier": pv["tier"], "suitability": pv["score"]})),
        )
        con.commit()
    finally:
        con.close()

    return {"ok": True, "case_id": cid, "receipt": receipt, "from": from_user,
            "to": to_user, "stage": pv["stage"], "tier": pv["tier"],
            "score": pv["score"], "warning": pv["warning"], "capacity": cap_shift}


def reset_to_baseline() -> dict:
    """Re-ingest the workbook, restoring the exact 165-case baseline. The audit
    table is preserved so the governance trail survives a reset."""
    from . import lsmv
    lsmv.build()
    return {"ok": True, "message": "Caseload reset to the baseline LSMV snapshot."}
