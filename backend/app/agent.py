"""Agentic AI layer — Claude (Bedrock) with a typed toolbox over the engine.

The agent never computes numbers. It calls engine-backed tools, then explains /
predicts / recommends in natural language, citing the case & activity IDs the
tools returned. This is what keeps answers grounded, explainable, and auditable
(AC #6, #9, #10).

Exposes register_agent_routes(app, engine_factory):
  POST /api/chat        -> SSE stream of {type: tool|text|error}
  POST /api/decisions   -> log a human decision on a recommendation (governance)
  GET  /api/audit       -> the audit trail
"""
from __future__ import annotations

import json
import math
import sqlite3
import time
from datetime import datetime
from typing import Callable, Iterator

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from . import config, llm, mutations
from .engine import Engine

# --------------------------------------------------------------------------
# Tool definitions exposed to Claude. Each wraps an engine method. No raw SQL,
# no free-form compute — the agent can only speak about what these return.
# --------------------------------------------------------------------------
TOOLS = [
    {
        "name": "get_workflow_health",
        "description": "Overall workflow health score (0-100), its Green/Amber/Red "
        "status, and the component penalties that make up the score.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "list_regulatory_risk",
        "description": "Cases at risk of missing their regulatory reporting deadline, "
        "with the reason and days remaining. Optionally filter by level "
        "(HIGH/MEDIUM/LOW) or team.",
        "input_schema": {
            "type": "object",
            "properties": {
                "level": {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW"]},
                "team": {"type": "string"},
            },
        },
    },
    {
        "name": "list_sla_risk",
        "description": "In-progress activities predicted to breach SLA based on how far "
        "they have run past historical turnaround norms.",
        "input_schema": {
            "type": "object",
            "properties": {
                "activity": {"type": "string"},
                "team": {"type": "string"},
            },
        },
    },
    {
        "name": "get_bottlenecks",
        "description": "Workflow stages/teams ranked by bottleneck severity, with queue "
        "depth, median wait vs historical norm, and the contributing cases.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_workload",
        "description": "Per-user utilization (open items vs capacity) and who is "
        "overloaded or has slack. Optionally filter by team.",
        "input_schema": {
            "type": "object",
            "properties": {"team": {"type": "string"}},
        },
    },
    {
        "name": "list_stuck_cases",
        "description": "Cases stuck in their current activity far longer than the "
        "historical p95 norm.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_case",
        "description": "Full drill-down for one case: activities, reassignment history, "
        "and every risk flag with its reason.",
        "input_schema": {
            "type": "object",
            "properties": {"case_id": {"type": "string"}},
            "required": ["case_id"],
        },
    },
    {
        "name": "recommend_next_best_action",
        "description": "Engine-scored next best action candidates (prioritize / reassign "
        "/ escalate / monitor) for a case or across the team. Reassignment is "
        "qualification-aware (Medical Review stays with a Safety Physician).",
        "input_schema": {
            "type": "object",
            "properties": {
                "case_id": {"type": "string"},
                "team": {"type": "string"},
            },
        },
    },
    {
        "name": "simulate_reassignment",
        "description": "WHAT-IF: move case(s) from one owner to another and see the "
        "recomputed capacity for both and whether the move is clinically "
        "qualified. Use to answer 'what happens if I reassign X to Y'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "from_user": {"type": "string"},
                "to_user": {"type": "string"},
                "n": {"type": "integer", "description": "how many of the owner's highest-risk cases to move"},
            },
            "required": ["from_user", "to_user"],
        },
    },
    {
        "name": "rebalance_plan",
        "description": "Propose reassignments that relieve an overloaded processing "
        "unit (default Medical Review), routing each case to the BEST-SUITED "
        "qualified reviewer by skill, efficiency, and experience — not just who "
        "is free.",
        "input_schema": {
            "type": "object",
            "properties": {"unit": {"type": "string"}},
        },
    },
    {
        "name": "best_reviewer",
        "description": "Rank the qualified reviewers for a given stage and case "
        "profile by suitability (skill + efficiency + experience + spare "
        "capacity). Use to answer 'who should take this case' — it accounts for "
        "reviewer skill and track record, not just availability, and warns when a "
        "complex/serious case would land on a weaker reviewer.",
        "input_schema": {
            "type": "object",
            "properties": {
                "stage": {"type": "string", "description": "e.g. Medical Review"},
                "complexity": {"type": "string", "description": "Low / Medium / Large"},
                "seriousness": {"type": "string"},
                "exclude": {"type": "string", "description": "a reviewer to exclude (e.g. the current owner)"},
            },
            "required": ["stage"],
        },
    },
    {
        "name": "daily_briefing",
        "description": "The prioritized action list for today: P1 cases with owner, "
        "deadline, and recommended action, plus the critical bottleneck and "
        "overloaded users. Use for 'what requires action today'.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "query_cases",
        "description": (
            "Flexible fallback query over the case table for ANY breakdown, filter, or "
            "list that a more specific tool doesn't already cover. Use this before saying "
            "you can't answer a case-level data question. "
            "`group_by` returns counts per distinct value; or pass `filters` and get a "
            "list of matching cases. Numeric filters accept comparisons as strings, e.g. "
            "{\"reassignment_count\": \">1\"} or {\"breach_prob\": \">=75\"} or "
            "{\"days_to_submission_due\": \"<=2\"}. Queryable fields: seriousness, complexity, "
            "report_type, study_type, assessed, stage (current_activity), team "
            "(processing_unit), assigned_to/owner, report_classification, product, "
            "sender_org, activity_due_status, reg_risk, predictive_risk, breach_prob, "
            "aging_ratio, reassignment_count, days_to_submission_due, days_to_case_due. "
            "scope 'active' (44 live cases, default) or 'all' (165)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "group_by": {"type": "string", "description": "field to count by, e.g. complexity, stage, assigned_to"},
                "filters": {"type": "object", "description": "field→value equality filters, e.g. {\"assigned_to\": \"Person D\"}"},
                "select": {"type": "array", "items": {"type": "string"}, "description": "fields to include when listing cases"},
                "scope": {"type": "string", "enum": ["active", "all"]},
                "limit": {"type": "integer"},
            },
        },
    },
    {
        "name": "caseload_breakdown",
        "description": (
            "Aggregated counts of the ACTIVE caseload by category: by workflow stage, "
            "by seriousness (SUSAR / Serious / Life-threatening-Death), by complexity "
            "per stage (Low/Medium/Large), by report type (classification), and by "
            "deadline window. Use this for any distribution / breakdown question "
            "(e.g. 'break down cases by seriousness') and to chart those shares."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "propose_reassignment",
        "description": (
            "Propose reassigning a case to another reviewer. This does NOT execute — it "
            "surfaces a Confirm/Cancel card to the manager, who must approve before "
            "anything changes. Resolve a receipt to its CASE id if needed. If the manager "
            "is vague ('move Person A's riskiest case to someone with capacity'), first use "
            "read tools to pick the specific case and a QUALIFIED target, then propose that. "
            "If the target is unqualified for the case's stage, the card will show it as "
            "blocked — suggest a qualified alternative instead."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "case_id": {"type": "string", "description": "CASE-id or Receipt# of the case to move"},
                "to_user": {"type": "string", "description": "reviewer to reassign it to, e.g. Person E"},
                "reason": {"type": "string", "description": "short why (optional)"},
            },
            "required": ["case_id", "to_user"],
        },
    },
    {
        "name": "show_chart",
        "description": (
            "Render a chart inline in the chat to visualize or COMPARE numbers you have "
            "ALREADY obtained from other tools (reviewer utilization, risk distribution, "
            "cases per stage, a trend, etc.). Only chart values a tool returned — never "
            "invent numbers. Call it AFTER the data tool(s), then write a one-line "
            "takeaway. Do not chart a single value. Use 'line' for trends or multi-series "
            "comparisons, 'bar' for comparing categories, 'donut' for a share/breakdown."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "chart_type": {"type": "string", "enum": ["bar", "line", "donut"]},
                "title": {"type": "string"},
                "x_label": {"type": "string"},
                "y_label": {"type": "string"},
                "series": {
                    "type": "array",
                    "description": "One series for bar/donut; one or more for line.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "points": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "label": {"type": "string"},
                                        "value": {"type": "number"},
                                    },
                                    "required": ["label", "value"],
                                },
                            },
                        },
                        "required": ["points"],
                    },
                },
            },
            "required": ["chart_type", "title", "series"],
        },
    },
]

SYSTEM = """You are the Intelligent Workflow Manager assistant for a pharmacovigilance (PV) operations team using LSMV.

You help a PV Operations Manager understand workflow health, regulatory and SLA risk, bottlenecks, workload, and the caseload breakdown, and recommend management actions.

You can hold a light, natural conversation WITHIN your scope: greet the user, explain what you can do, and explain pharmacovigilance / LSMV-workflow concepts in plain language (e.g. "what is a SUSAR", "what does workflow health mean"). Answer those directly and warmly without a tool. Only live-data questions require tools.

When asked "what can you do", summarize briefly: workflow health, regulatory & predictive SLA risk, bottlenecks, workload/capacity, caseload breakdowns (stage, seriousness, complexity, deadline), per-case drill-downs, reassignment simulation & rebalancing, and inline charts — all grounded in the live LSMV data.

SCOPE — stay strictly in your lane:
- You ONLY help with THIS PV operations / LSMV workflow: workflow health, regulatory & SLA risk, bottlenecks, workload/capacity, caseload breakdowns, individual cases, reassignment, and directly-related pharmacovigilance concepts.
- If asked ANYTHING outside that scope (general trivia, sports, news, weather, jokes, math, coding, celebrities, personal opinions, etc.), do NOT answer it — even if you know the answer. In one short sentence say it's outside what you help with, then point to what you can do. Never provide the off-topic content itself (no trivia answers, no jokes, no essays).

STRICT RULES (this is a regulated PV context):
- For a data question, only state numbers, case IDs, names, and facts that appear in tool results. NEVER invent or estimate a value a tool did not return.
- Call the relevant tool(s) before answering a data question. Prefer the most specific tool. For distribution/breakdown questions use caseload_breakdown.
- If no specific tool fits a case-level data question (any field, filter, or breakdown), use query_cases — it can reach any case field by group_by or filters. Only say you can't answer AFTER query_cases also comes up empty.
- Cite the concrete case IDs / activity IDs / stage names behind every claim.
- When you recommend an action, make clear it is a recommendation for the manager to approve — you do not execute anything.
- If the tools return nothing relevant, say so plainly rather than guessing.

ANSWER STYLE:
- Lead with the one-sentence direct answer. Then supporting bullets with the concrete case IDs / names. Then, if useful, a single recommendation line prefixed "Recommend:".
- Do NOT narrate your process. Never write "Let me…", "I'll check…", "Quick correction", "Correction:", "my earlier filter…", or mention tool names (the user already sees tool activity separately). Just give the answer.
- Do not write any text BEFORE you call a tool — call the tool first, then write only the final answer.
- If something you said earlier was wrong, simply state the correct answer. Do not flag or apologize for the correction.

TAKING ACTION (reassignment):
- You can propose ONE action: reassigning a case to another reviewer. When the manager asks to reassign / move / hand over a case, call propose_reassignment with the exact case_id (resolve a receipt to its CASE id) and the target reviewer.
- If the manager is vague ("move Person A's riskiest case to someone with capacity"), FIRST use read tools (get_workload, list_regulatory_risk, best_reviewer) to pick the specific case and a qualified target, then propose that.
- NEVER say the reassignment is done — it applies only after the manager clicks Confirm on the card you surfaced. If it comes back blocked (unqualified reviewer), say so plainly and offer a qualified alternative from best_reviewer.
- The conversation may contain a prior "[What-if simulation]" note with specific case IDs and a target reviewer. If the manager then says "do it" / "apply that" / "go ahead", propose_reassignment for THAT simulated case and target. If that target was flagged not qualified, the proposal will be blocked — explain why and suggest a qualified alternative.

CHARTS:
- When the question involves a COMPARISON, DISTRIBUTION, BREAKDOWN, or TREND (e.g. "compare reviewer workload", "break down cases by seriousness", "cases per stage"), first get the numbers with a data tool, then call show_chart with ONLY those numbers to visualize them, then give the one-line takeaway.
- Pick the type: 'bar' to compare categories, 'donut' for a share/breakdown, 'line' for a trend or multi-series comparison.
- Never chart a single number, and never chart values no tool returned."""


def _tool_summary(name: str, args: dict) -> str:
    arg_str = ", ".join(f"{k}={v}" for k, v in args.items() if v is not None)
    return f"{name}({arg_str})" if arg_str else f"{name}()"


def _run_tool(engine: Engine, name: str, args: dict) -> dict:
    """Dispatch a tool call to the engine. Returns a trimmed, JSON-safe result."""
    try:
        if name == "get_workflow_health":
            return engine.workflow_health()
        if name == "list_regulatory_risk":
            r = engine.regulatory_risk(level=args.get("level"), team=args.get("team"))
            return {"counts": r["counts"], "cases": r["evidence"][:20]}
        if name == "list_sla_risk":
            r = engine.sla_risk(activity=args.get("activity"), team=args.get("team"))
            return {"count": r["value"], "activities": r["evidence"][:20]}
        if name == "get_bottlenecks":
            b = engine.bottlenecks()
            return {"top": b["value"], "stages": b["evidence"]}
        if name == "get_workload":
            r = engine.workload(team=args.get("team"))
            return {"overloaded": r["value"], "users": r["evidence"]}
        if name == "list_stuck_cases":
            r = engine.stuck_cases()
            return {"count": r["value"], "cases": r["evidence"]}
        if name == "get_case":
            return engine.case_detail(args["case_id"])
        if name == "recommend_next_best_action":
            return engine.next_best_action(case_id=args.get("case_id"), team=args.get("team"))
        if name == "simulate_reassignment":
            return engine.simulate_reassignment(
                args["from_user"], args["to_user"], n=args.get("n"))
        if name == "rebalance_plan":
            return engine.rebalance_plan(args.get("unit") or "Medical Review")
        if name == "best_reviewer":
            return {"ranked": engine.rank_reviewers(
                args["stage"], args.get("complexity", ""), args.get("seriousness", ""),
                exclude=args.get("exclude"))}
        if name == "daily_briefing":
            return engine.daily_briefing()
        if name == "query_cases":
            return engine.query_cases(
                group_by=args.get("group_by"),
                filters=args.get("filters"),
                select=args.get("select"),
                scope=args.get("scope") or "active",
                limit=args.get("limit") or 25,
            )
        if name == "caseload_breakdown":
            a = engine.caseload_analytics()
            return {
                "active_total": a["active_total"],
                "by_stage": [{"stage": s["stage"], "count": s["count"], "breached": s["breached"]} for s in a["stages"]],
                "by_seriousness": a["seriousness"],
                "by_complexity_stage": a["complexity_by_stage"],
                "by_classification": a["classification"],
                "by_deadline": a["deadline_watch"],
            }
        return {"error": f"unknown tool {name}"}
    except Exception as e:  # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}"}


def _sanitize_chart(args: dict) -> dict:
    """Clamp/clean an LLM-provided chart spec into a safe, renderable shape."""
    ctype = args.get("chart_type")
    if ctype not in ("bar", "line", "donut"):
        ctype = "bar"
    series = []
    for s in (args.get("series") or [])[:6]:
        pts = []
        for p in (s.get("points") or [])[:30]:
            try:
                v = float(p.get("value"))
            except (TypeError, ValueError):
                continue
            if not math.isfinite(v):
                continue
            pts.append({"label": str(p.get("label", ""))[:40], "value": v})
        if pts:
            series.append({"name": str(s.get("name") or "")[:40], "points": pts})
    return {
        "chart_type": ctype,
        "title": str(args.get("title") or "")[:80],
        "x_label": str(args.get("x_label") or "")[:40],
        "y_label": str(args.get("y_label") or "")[:40],
        "series": series,
    }


def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj)}\n\n"


class ChatBody(BaseModel):
    message: str
    history: list[dict] | None = None


class DecisionBody(BaseModel):
    case_id: str
    recommended_action: str
    decision: str  # accept | modify | dismiss
    note: str | None = None


# --------------------------------------------------------------------------
# Audit log (governance, AC #10)
# --------------------------------------------------------------------------
def _audit_con() -> sqlite3.Connection:
    con = sqlite3.connect(config.DB_PATH)
    con.execute(
        """CREATE TABLE IF NOT EXISTS audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT, kind TEXT, case_id TEXT, recommended_action TEXT,
            decision TEXT, note TEXT, detail TEXT
        )"""
    )
    return con


def _audit_write(kind: str, **fields) -> None:
    con = _audit_con()
    try:
        con.execute(
            "INSERT INTO audit (ts, kind, case_id, recommended_action, decision, note, detail)"
            " VALUES (?,?,?,?,?,?,?)",
            (
                datetime.utcnow().isoformat(),
                kind,
                fields.get("case_id"),
                fields.get("recommended_action"),
                fields.get("decision"),
                fields.get("note"),
                json.dumps(fields.get("detail")) if fields.get("detail") else None,
            ),
        )
        con.commit()
    finally:
        con.close()


# --------------------------------------------------------------------------
# Agentic loop (manual tool loop, streamed as SSE)
# --------------------------------------------------------------------------
def _build_messages(history: list[dict] | None, user_message: str) -> list[dict]:
    """Turn the client's text-level conversation into a valid alternating
    user/assistant message list, then append the new user turn."""
    turns: list[dict] = []
    for h in (history or [])[-20:]:
        role, content = h.get("role"), h.get("content")
        if role not in ("user", "assistant") or not str(content or "").strip():
            continue
        if turns and turns[-1]["role"] == role:
            turns[-1]["content"] += "\n\n" + str(content)
        else:
            turns.append({"role": role, "content": str(content)})
    while turns and turns[0]["role"] == "assistant":
        turns.pop(0)  # a conversation must start with a user turn
    if turns and turns[-1]["role"] == "user":
        turns[-1]["content"] += "\n\n" + user_message
    else:
        turns.append({"role": "user", "content": user_message})
    return turns


def _chat_stream(engine: Engine, user_message: str,
                 history: list[dict] | None = None) -> Iterator[str]:
    messages: list[dict] = _build_messages(history, user_message)
    tools_used: list[str] = []
    final_text = ""

    last_preamble = ""
    try:
        for _ in range(6):  # cap tool-use rounds
            resp = llm.chat(
                messages=messages,
                system=SYSTEM,
                tools=TOOLS,
                max_tokens=1500,
            )
            round_text = ""
            tool_uses = []
            for block in resp.content:
                btype = getattr(block, "type", None)
                if btype == "text":
                    round_text += block.text
                elif btype == "tool_use":
                    tool_uses.append(block)

            # Final (non-tool) round → stream its text as the answer. Text that
            # appears in a tool-calling round is just process narration ("I'll
            # check…") — discard it so the user only sees the clean answer.
            if resp.stop_reason != "tool_use" or not tool_uses:
                if round_text:
                    final_text += round_text
                    yield _sse({"type": "text", "text": round_text})
                break
            last_preamble = round_text or last_preamble

            # Record assistant turn (with tool_use blocks) then run the tools.
            messages.append({"role": "assistant", "content": resp.content})
            results = []
            for tu in tool_uses:
                if tu.name == "show_chart":
                    # No tool line — the rendered chart is the visible output.
                    spec = _sanitize_chart(tu.input or {})
                    tools_used.append(f"show_chart({spec['chart_type']})")
                    if spec["series"]:
                        yield _sse({"type": "chart", "spec": spec})
                        out = {"ok": True, "note": "Chart rendered to the user. Add a one-line takeaway."}
                    else:
                        out = {"error": "no valid numeric points to chart"}
                elif tu.name == "propose_reassignment":
                    a = tu.input or {}
                    tools_used.append(f"propose_reassignment({a.get('case_id')}→{a.get('to_user')})")
                    pv = mutations.preview_reassign(a.get("case_id", ""), a.get("to_user", ""))
                    if not pv.get("ok"):
                        out = {"error": pv.get("error")}
                    else:
                        blocked = not pv["qualified"]
                        yield _sse({
                            "type": "action_proposal", "action": "reassign",
                            "case_id": pv["case_id"], "receipt": pv["receipt"],
                            "from_user": pv["from_user"], "to_user": pv["to_user"],
                            "stage": pv["stage"], "complexity": pv["complexity"],
                            "seriousness": pv["seriousness"], "tier": pv["tier"],
                            "score": pv["score"], "warning": pv["warning"],
                            "blocked": blocked, "reason": a.get("reason"),
                            "note": a.get("reason") or "",
                        })
                        out = {"proposal_shown": True, "awaiting_confirmation": not blocked,
                               "blocked": blocked, "warning": pv["warning"],
                               "note": ("Reassignment is BLOCKED (unqualified reviewer); explain and suggest a qualified alternative."
                                        if blocked else
                                        "A Confirm/Cancel card was shown to the manager. Do NOT say it is done — it applies only after they confirm.")}
                else:
                    summary = _tool_summary(tu.name, tu.input or {})
                    tools_used.append(summary)
                    yield _sse({"type": "tool", "text": summary})
                    out = _run_tool(engine, tu.name, tu.input or {})
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tu.id,
                        "content": json.dumps(out, default=str),
                    }
                )
            messages.append({"role": "user", "content": results})

        # Safety net: if the model never produced a clean final-round answer,
        # fall back to the last text it wrote so the user isn't left empty.
        if not final_text.strip() and last_preamble.strip():
            final_text = last_preamble
            yield _sse({"type": "text", "text": last_preamble})

        _audit_write(
            "chat",
            note=user_message,
            detail={"tools": tools_used, "answer": final_text[:4000]},
        )
    except Exception as e:  # noqa: BLE001
        yield _sse({"type": "error", "text": f"{type(e).__name__}: {e}"})


def register_agent_routes(app: FastAPI, engine_factory: Callable[[], Engine]) -> None:
    @app.post("/api/chat")
    def chat(body: ChatBody):
        engine = engine_factory()

        def gen():
            yield from _chat_stream(engine, body.message, body.history)

        return StreamingResponse(gen(), media_type="text/event-stream")

    @app.post("/api/decisions")
    def decisions(body: DecisionBody):
        _audit_write(
            "decision",
            case_id=body.case_id,
            recommended_action=body.recommended_action,
            decision=body.decision,
            note=body.note,
        )
        return {"ok": True, "logged_at": datetime.utcnow().isoformat()}

    @app.get("/api/audit")
    def audit(limit: int = 100, case_id: str | None = None):
        con = _audit_con()
        try:
            if case_id:
                cur = con.execute(
                    "SELECT ts, kind, case_id, recommended_action, decision, note"
                    " FROM audit WHERE case_id = ? ORDER BY id DESC LIMIT ?",
                    (case_id, limit),
                )
            else:
                cur = con.execute(
                    "SELECT ts, kind, case_id, recommended_action, decision, note"
                    " FROM audit ORDER BY id DESC LIMIT ?",
                    (limit,),
                )
            cols = [c[0] for c in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        finally:
            con.close()
        return {"count": len(rows), "entries": rows}
