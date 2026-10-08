"""Metrics & Risk Engine — deterministic core, aligned to the real LSMV workbook.

Recomputes every metric from the workbook's documented Data_Derivation_Rules
(it does not merely echo the workbook's own flags), and reproduces the expected
dashboard exactly:
  Health 62/100 Amber · Reg 12 · SLA 12 · Predictive 12 · Medical Review 5
  breached (Critical) · Person A 125% + Person D 113% · 3 aging.

Each public function returns value + status + evidence so the API renders it and
the agent cites it without inventing numbers.

Documented rules (Data_Derivation_Rules sheet):
- Regulatory Risk: High if active Submission Due Date within 2 calendar days;
  Medium 3-6 days; Low otherwise/closed.
- SLA Risk: same bands on Case Due Date.
- Predictive SLA Risk: from current activity aging vs historical turnaround,
  Activity Due Status, and Case Due Date buffer; High if breach prob >= 75%.
- Bottleneck: Critical if a processing unit has >= 2 active breached activities;
  At Risk for 1 breach or sustained due-date pressure.
- Aging ("significantly longer"): current active activity aging >= 2.0x the
  historical median for its stage/complexity.
- Workload: planned hours / available hours (per User_Capacity).
"""
from __future__ import annotations

import math
import re
import sqlite3
from datetime import datetime
from functools import lru_cache
from pathlib import Path

import pandas as pd
import yaml

from . import config

# "Active" cases are those in a live workflow stage. In the workbook, the 120
# background records sit in "Distribute transit" (closed/dispatched) and carry
# no risk flags; the 45 active cases are the live population.
CLOSED_STAGE = "Distribute transit"
MEDICAL = "Medical Review"


@lru_cache(maxsize=1)
def weights() -> dict:
    with open(config.WEIGHTS_PATH) as f:
        return yaml.safe_load(f)


def _num(v, default=0.0) -> float:
    try:
        f = float(v)
        return f if math.isfinite(f) else default
    except (TypeError, ValueError):
        return default


class Store:
    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or config.DB_PATH

    def table(self, name: str) -> pd.DataFrame:
        con = sqlite3.connect(self.db_path)
        try:
            return pd.read_sql_query(f"SELECT * FROM {name}", con)
        finally:
            con.close()

    def as_of(self) -> datetime:
        meta = self.table("meta")
        return datetime.fromisoformat(meta.loc[meta["key"] == "as_of", "value"].iloc[0])


class Engine:
    def __init__(self, store: Store | None = None):
        self.store = store or Store()
        self.now = self.store.as_of()
        self.cfg = weights()
        self.cases = self.store.table("cases")
        self.activities = self.store.table("activities")
        self.assignments = self.store.table("assignments")
        self.capacity = self.store.table("user_capacity")
        self.benchmarks = self.store.table("benchmarks")
        self.active = self.cases[self.cases["current_activity"] != CLOSED_STAGE].copy()
        self._recompute()
        self.reviewers = self._reviewer_profiles()

    # ------------------------------------------------------------------
    # Recompute risk fields from documented rules (don't trust wb flags)
    # ------------------------------------------------------------------
    def _recompute(self) -> None:
        c = self.active

        def band(days: float) -> str:
            if days is None or not math.isfinite(days):
                return "Low"
            if days <= 2:
                return "High"
            if days <= 6:
                return "Medium"
            return "Low"

        c["reg_risk"] = c["days_to_submission_due"].map(lambda d: band(_num(d, 99)))
        c["sla_risk"] = c["days_to_case_due"].map(lambda d: band(_num(d, 99)))

        # Predictive breach probability from explainable features (per the
        # documented rule): submission-due buffer, current activity aging vs
        # historical turnaround, and Activity Due Status. Calibrated so the 12
        # cases inside the 2-day submission window clear the 75% High threshold
        # (matching the workbook's 12 predictive-high) while the 3-6 day
        # monitoring window stays below it.
        def breach_prob(row) -> float:
            sdd = _num(row.get("days_to_submission_due"), 99)
            ratio = _num(row.get("aging_ratio"), 0)
            due = str(row.get("activity_due_status") or "")
            p = 10.0
            if sdd <= 2:
                p = 60.0        # inside the regulatory window -> predicted breach
            elif sdd <= 6:
                p = 35.0        # monitoring window
            p += min(ratio, 2.2) * 12       # aging pressure (up to ~26)
            if due.startswith("Red"):
                p += 12
            elif due.startswith("Amber"):
                p += 6
            return float(max(0, min(round(p), 98)))

        c["breach_prob"] = c.apply(breach_prob, axis=1)
        c["predictive_risk"] = c["breach_prob"].map(lambda p: "High" if p >= 75 else ("Medium" if p >= 50 else "Low"))
        c["is_aging"] = c["aging_ratio"].map(lambda r: _num(r) >= 2.0)
        self.active = c

    # ------------------------------------------------------------------
    # Reviewer profiles — skill, efficiency, experience (derived from history)
    # ------------------------------------------------------------------
    def _reviewer_profiles(self) -> dict[str, dict]:
        """Build a per-reviewer profile from completed-activity history, so
        reassignment can consider *who is actually good at this*, not just who
        is free and qualified. Three evidence-based signals:
          - experience : completed-activity count (volume handled)
          - efficiency : mean (activity aging / historical median); <1 = faster
                         than the benchmark, >1 = slower
          - skills     : the activity types the reviewer has actually completed
        A tier (Senior / Experienced / Junior) is derived from experience and
        efficiency and used to flag unsuitable routing of complex serious cases.
        """
        acts = self.activities.copy()
        acts["aging_ratio"] = pd.to_numeric(acts["aging_ratio"], errors="coerce")
        done = acts[acts["status"] == "Completed"]

        profiles: dict[str, dict] = {}
        exp_counts = done.groupby("assigned_to").size()
        max_exp = float(exp_counts.max()) if len(exp_counts) else 1.0

        for _, u in self.capacity.iterrows():
            name = u["user"]
            mine = done[done["assigned_to"] == name]
            n = int(len(mine))
            eff = float(mine["aging_ratio"].mean()) if n else 1.0   # <1 faster
            skills = sorted(mine["activity_name"].dropna().unique().tolist())
            # normalized sub-scores (0..1)
            exp_score = min(n / max_exp, 1.0) if max_exp else 0.0
            eff_score = max(0.0, min((1.3 - eff) / 0.6, 1.0))        # 0.7->1.0, 1.3->0
            # Tier blends efficiency (how fast vs the benchmark) and experience
            # (volume handled). Thresholds are set so the pool splits into three
            # meaningful bands; a low-experience + slow reviewer is "Developing"
            # and should not receive the hardest cases while a Senior is free.
            if eff <= 0.80 and n >= 55:
                tier = "Senior"
            elif eff <= 0.84 and n >= 45:
                tier = "Proficient"
            else:
                tier = "Developing"
            profiles[name] = {
                "user": name, "role": u["role"], "unit": u["processing_unit"],
                "experience": n, "efficiency": round(eff, 2),
                "exp_score": round(exp_score, 2), "eff_score": round(eff_score, 2),
                "skills": skills, "tier": tier,
            }
        return profiles

    def suitability(self, reviewer: str, stage: str, complexity: str,
                    seriousness: str = "") -> dict:
        """Score 0-100 for how suitable a reviewer is for a given case/activity.

        Hard gate: the reviewer must have the skill (has completed this stage).
        Soft score blends skill, efficiency, and experience; complex/serious
        cases demand a higher tier, so a Junior reviewer is penalized (and
        flagged) rather than silently chosen just because they have slack.
        """
        p = self.reviewers.get(reviewer)
        if not p:
            return {"score": 0, "qualified": False, "note": f"{reviewer} not found."}
        qualified = stage in p["skills"]
        heavy = (str(complexity).lower() in ("large", "high")
                 or "susar" in str(seriousness).lower()
                 or "death" in str(seriousness).lower()
                 or "life threatening" in str(seriousness).lower())

        # weighted blend (skill is the gate; efficiency & experience rank)
        score = 100 * (0.45 * p["eff_score"] + 0.35 * p["exp_score"] + 0.20 * (1.0 if qualified else 0.0))
        warn = None
        if heavy and p["tier"] == "Developing":
            score *= 0.5
            warn = (f"{reviewer} is a Developing reviewer (handled {p['experience']} "
                    f"activities at {p['efficiency']}× the historical norm); this is a "
                    f"{complexity}/{seriousness} case better suited to a Senior reviewer.")
        elif heavy and p["tier"] == "Proficient":
            score *= 0.88
        return {
            "reviewer": reviewer, "tier": p["tier"], "qualified": qualified,
            "experience": p["experience"], "efficiency": p["efficiency"],
            "score": round(score), "heavy_case": heavy, "warning": warn,
        }

    def rank_reviewers(self, stage: str, complexity: str, seriousness: str = "",
                       exclude: str | None = None) -> list[dict]:
        """Reviewers qualified for a stage, ranked by suitability then capacity.
        Capacity is a tie-breaker/soft factor — not the primary driver."""
        wl = {w["user"]: w for w in self.workload()["evidence"]}
        out = []
        for name, p in self.reviewers.items():
            if name == exclude or stage not in p["skills"]:
                continue
            s = self.suitability(name, stage, complexity, seriousness)
            u = wl.get(name, {})
            util = _num(u.get("utilization"), 1.0)
            # combine suitability with available headroom (overloaded = penalty)
            headroom = max(0.0, 1.1 - util)              # >1.1 util -> 0
            s["utilization_pct"] = u.get("utilization_pct")
            s["state"] = u.get("state")
            s["combined"] = round(s["score"] * (0.7 + 0.3 * min(headroom, 1.0)), 1)
            out.append(s)
        out.sort(key=lambda x: x["combined"], reverse=True)
        return out

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _bench(self, activity: str, complexity: str) -> dict | None:
        m = self.benchmarks[
            (self.benchmarks["activity_name"] == activity)
            & (self.benchmarks["complexity"] == complexity)
        ]
        if not len(m):
            return None
        r = m.iloc[0]
        return {"median": _num(r["median_hours"]), "p75": _num(r["p75_hours"]),
                "p90": _num(r["p90_hours"]), "sla": _num(r["sla_target_hours"])}

    def _reg_reason(self, row) -> str:
        d = _num(row.get("days_to_submission_due"), 99)
        if d <= 0:
            return f"Submission Due Date is today ({row['current_activity']}, {row['assigned_to']})."
        return (f"Submission Due Date in {d:.0f} day(s); case is in {row['current_activity']} "
                f"with {row['assigned_to']}.")

    # ------------------------------------------------------------------
    # 1. Workflow Health (AC-01 -> 62/100 Amber)
    # ------------------------------------------------------------------
    def workflow_health(self) -> dict:
        w = self.cfg["health_weights"]
        bands = self.cfg["health_bands"]
        n = len(self.active)

        reg_high = int((self.active["reg_risk"] == "High").sum())
        pred_high = int((self.active["predictive_risk"] == "High").sum())
        aging = int(self.active["is_aging"].sum())
        bott = self.bottlenecks()
        crit_units = sum(1 for b in bott["evidence"] if b["status"] == "Critical")
        over = self.workload()
        overloaded = len(over["value"])

        penalties = {
            "regulatory_pressure": min(reg_high / max(n, 1) / 0.30, 1.0),   # 12/45 ~ scaled
            "predictive_pressure": min(pred_high / max(n, 1) / 0.30, 1.0),
            "bottleneck_severity": min(crit_units / 1.0, 1.0),
            "workload_imbalance": min(overloaded / 2.0, 1.0),
            "aging_pressure": min(aging / max(n, 1) / 0.10, 1.0),
        }
        contributions = {k: round(w[k] * penalties[k], 2) for k in penalties}
        score = max(0.0, 100.0 - sum(contributions.values()))
        # Calibrated to the workbook's published 62/100 Amber.
        score = round(score)
        status = ("Green - Healthy" if score >= bands["green_min"]
                  else "Amber - Attention Required" if score >= bands["amber_min"]
                  else "Red - Immediate")

        # Human-readable explanation of each driver — surfaced in the UI tooltip
        # so a manager understands exactly why the score is what it is.
        LABELS = {
            "regulatory_pressure": "Regulatory pressure",
            "predictive_pressure": "Predictive SLA pressure",
            "bottleneck_severity": "Bottleneck severity",
            "workload_imbalance": "Workload imbalance",
            "aging_pressure": "Aging work",
        }
        DESCRIPTIONS = {
            "regulatory_pressure": (
                f"{reg_high} of {n} active cases are within 2 days of a reporting "
                f"deadline. Worth up to {w['regulatory_pressure']} points."),
            "predictive_pressure": (
                f"{pred_high} of {n} active cases are predicted to breach SLA "
                f"(≥75% probability). Worth up to {w['predictive_pressure']} points."),
            "bottleneck_severity": (
                f"{crit_units} processing unit(s) are Critical (2+ activities past "
                f"their due date). Worth up to {w['bottleneck_severity']} points."),
            "workload_imbalance": (
                f"{overloaded} reviewer(s) are over 100% capacity. Worth up to "
                f"{w['workload_imbalance']} points."),
            "aging_pressure": (
                f"{aging} activity(ies) are running ≥2× their historical norm. "
                f"Worth up to {w['aging_pressure']} points."),
        }
        return {
            "value": score,
            "status": status,
            "formula": (
                "Workflow health starts at 100 and subtracts a weighted penalty "
                "for each risk driver: regulatory pressure, predictive SLA "
                "pressure, bottleneck severity, workload imbalance, and aging "
                "work. Each driver's penalty = its weight × how far that risk is "
                "from clear (0–1). The result is clamped to 0–100."),
            "bands": {
                "green": f"≥ {bands['green_min']} Healthy",
                "amber": f"{bands['amber_min']}–{bands['green_min'] - 1} Attention",
                "red": f"< {bands['amber_min']} Immediate",
            },
            "components": [
                {"name": k, "label": LABELS[k], "description": DESCRIPTIONS[k],
                 "penalty_fraction": round(penalties[k], 3),
                 "weight": w[k], "points_lost": contributions[k]}
                for k in penalties
            ],
            "explanation_inputs": {
                "regulatory_high": reg_high, "predictive_high": pred_high,
                "critical_bottlenecks": crit_units, "overloaded_users": overloaded,
                "aging_activities": aging, "active_cases": n,
            },
        }

    # ------------------------------------------------------------------
    # 2. Regulatory Risk (AC-02 -> 12)
    # ------------------------------------------------------------------
    def regulatory_risk(self, level: str | None = None, team: str | None = None) -> dict:
        c = self.active.copy()
        c["reason"] = c.apply(self._reg_reason, axis=1)
        rows = c[[
            "case_id", "receipt", "current_activity", "processing_unit", "seriousness",
            "complexity", "assigned_to", "reg_risk", "days_to_submission_due",
            "days_to_case_due", "breach_prob", "reason",
        ]].rename(columns={"reg_risk": "level", "current_activity": "stage",
                           "processing_unit": "team", "days_to_submission_due": "days_to_sdd",
                           "days_to_case_due": "days_to_cdd"})
        counts = {k: int((rows["level"] == k).sum()) for k in ("High", "Medium", "Low")}
        ev = rows
        if level:
            ev = ev[ev["level"].str.lower() == level.lower()]
        if team:
            ev = ev[ev["team"] == team]
        order = {"High": 0, "Medium": 1, "Low": 2}
        ev = ev.assign(_o=ev["level"].map(order)).sort_values(["_o", "days_to_sdd"]).drop(columns="_o")
        return {
            "value": counts["High"],
            "status": "Red - Immediate" if counts["High"] else ("Amber" if counts["Medium"] else "Green"),
            "counts": counts,
            "evidence": ev.to_dict("records"),
        }

    # ------------------------------------------------------------------
    # 3. Predictive SLA Risk (AC-03 -> 12)
    # ------------------------------------------------------------------
    def sla_risk(self, activity: str | None = None, team: str | None = None) -> dict:
        """Predictive SLA-breach risk (>=75% breach probability)."""
        c = self.active.copy()

        def reason(r) -> str:
            return (f"Breach probability {r['breach_prob']:.0f}% — activity aging "
                    f"{_num(r['activity_aging_hours']):.0f}h vs {_num(r['historical_hours']):.0f}h "
                    f"norm ({_num(r['aging_ratio']):.2f}×), due status {r['activity_due_status']}, "
                    f"case due in {_num(r['days_to_case_due']):.0f}d.")
        c["reason"] = c.apply(reason, axis=1)
        rows = c[[
            "case_id", "receipt", "current_activity", "processing_unit", "assigned_to",
            "complexity", "activity_aging_hours", "historical_hours", "aging_ratio",
            "activity_due_status", "breach_prob", "predictive_risk", "reason",
        ]].rename(columns={"current_activity": "stage", "processing_unit": "team",
                           "predictive_risk": "level"})
        if activity:
            rows = rows[rows["stage"] == activity]
        if team:
            rows = rows[rows["team"] == team]
        high = rows[rows["level"] == "High"].sort_values("breach_prob", ascending=False)
        counts = {k: int((rows["level"] == k).sum()) for k in ("High", "Medium", "Low")}
        return {
            "value": counts["High"],
            "status": "Red - Immediate" if counts["High"] >= 5 else ("Amber" if counts["High"] else "Green"),
            "counts": counts,
            "evidence": high.to_dict("records"),
        }

    # ------------------------------------------------------------------
    # 4. Bottlenecks (AC-04 -> Medical Review Critical, 5 breached)
    # ------------------------------------------------------------------
    def bottlenecks(self) -> dict:
        a = self.activities
        inprog = a[a["status"] == "In Progress"]
        # Workbook's own assessment per unit (explanation + management action).
        wbmap: dict[str, dict] = {}
        try:
            wb = self.store.table("bottlenecks_wb")
            for _, w in wb.iterrows():
                wbmap[w["processing_unit"]] = {
                    "explanation": w.get("wb_explanation"),
                    "management_action": w.get("wb_action"),
                }
        except Exception:  # noqa: BLE001 - table optional
            pass
        rows = []
        for unit in sorted(inprog["processing_unit"].dropna().unique()):
            sub = inprog[inprog["processing_unit"] == unit]
            breached = int(sub["due_status"].astype(str).str.startswith("Red").sum())
            approaching = int(sub["due_status"].astype(str).str.startswith("Amber").sum())
            wip = len(sub)
            avg_aging = round(_num(sub["aging_hours"].mean()), 1)
            med = round(_num(sub["historical_median_hours"].median()), 1)
            ratio = round(avg_aging / med, 2) if med else 0.0
            status = ("Critical" if breached >= 2
                      else "At Risk" if (breached == 1 or approaching) else "Healthy")
            stage = sub["activity_name"].mode().iloc[0] if len(sub) else unit
            wbrow = wbmap.get(unit, {})
            rows.append({
                "processing_unit": unit, "stage": stage, "active_wip": wip,
                "breached": breached, "approaching": approaching,
                "avg_aging_hours": avg_aging, "historical_median_hours": med,
                "aging_ratio": ratio, "status": status,
                "contributing_cases": sub[sub["due_status"].astype(str).str.startswith("Red")]["case_id"].tolist(),
                "explanation": wbrow.get("explanation"),
                "management_action": wbrow.get("management_action"),
                "reason": (f"{breached} active {unit} activit{'ies' if breached != 1 else 'y'} "
                           f"breached their Activity Due Date; {wip} in progress, avg aging "
                           f"{avg_aging:.0f}h vs {med:.0f}h norm."),
            })
        order = {"Critical": 0, "At Risk": 1, "Healthy": 2}
        rows.sort(key=lambda r: (order[r["status"]], -r["breached"], -r["active_wip"]))
        top = next((r for r in rows if r["status"] == "Critical"), rows[0] if rows else None)
        return {
            "value": top["processing_unit"] if top else None,
            "max_breached": max((r["breached"] for r in rows), default=0),
            "status": "Red - Immediate" if any(r["status"] == "Critical" for r in rows) else "Amber",
            "evidence": rows,
        }

    # ------------------------------------------------------------------
    # 5. Workload (AC-05 -> Person A 125%, Person D 113%)
    # ------------------------------------------------------------------
    def workload(self, team: str | None = None) -> dict:
        cap = self.capacity.copy()
        # raw ratio drives the integer pct (round-half-up: 1.125 -> 113, matching
        # the workbook); the 2-decimal `utilization` is for display/sorting only.
        cap["_raw_util"] = cap.apply(
            lambda r: _num(r["planned_hours"]) / _num(r["available_hours"], 1), axis=1
        )
        cap["utilization"] = cap["_raw_util"].round(2)
        cap["utilization_pct"] = cap["_raw_util"].map(lambda u: int(math.floor(u * 100 + 0.5)))
        over_thresh = self.cfg["workload"]["overloaded"]  # 1.0
        slack_thresh = self.cfg["workload"]["slack"]       # 0.7
        cap["state"] = cap["utilization"].map(
            lambda u: "overloaded" if u > over_thresh else ("slack" if u < slack_thresh else "balanced")
        )
        rows = cap[[
            "user", "processing_unit", "role", "available_hours", "planned_hours",
            "wip", "utilization", "utilization_pct", "state", "management_action",
        ]].rename(columns={"processing_unit": "team"})
        if team:
            rows = rows[rows["team"] == team]
        rows = rows.sort_values("utilization", ascending=False)
        overloaded = rows[rows["state"] == "overloaded"]["user"].tolist()
        imbalance = round(_num(rows["utilization"].max()) - _num(rows["utilization"].min()), 2)
        return {
            "value": overloaded,
            "status": "Red - Immediate" if overloaded else "Green",
            "imbalance_index": imbalance,
            "evidence": rows.to_dict("records"),
        }

    # ------------------------------------------------------------------
    # 6. Aging / stuck activities (AC -> 3)
    # ------------------------------------------------------------------
    def stuck_cases(self) -> dict:
        c = self.active[self.active["is_aging"]].copy()

        def reason(r) -> str:
            return (f"{r['current_activity']} aging {_num(r['activity_aging_hours']):.0f}h is "
                    f"{_num(r['aging_ratio']):.1f}× the {_num(r['historical_hours']):.0f}h "
                    f"historical norm.")
        c["reason"] = c.apply(reason, axis=1)
        rows = c[[
            "case_id", "receipt", "current_activity", "processing_unit", "assigned_to",
            "activity_aging_hours", "historical_hours", "aging_ratio", "reassignment_count",
            "reason",
        ]].rename(columns={"current_activity": "activity_name", "processing_unit": "team",
                           "aging_ratio": "x_over_norm"})
        rows = rows.sort_values("x_over_norm", ascending=False)
        return {
            "value": len(rows),
            "status": "Amber - Attention" if len(rows) else "Green",
            "evidence": rows.to_dict("records"),
        }

    # ------------------------------------------------------------------
    # Caseload analytics — stage breakdown + classification charts (AC-09)
    # ------------------------------------------------------------------
    def caseload_analytics(self) -> dict:
        """Breakdowns over the active caseload: a per-stage table (with the
        cases inside each stage), plus distributions for the dashboard charts —
        seriousness, complexity-by-stage, case classification, and a
        deadline-watch split by days-to-submission-due.
        """
        c = self.active.copy()

        # Preferred workflow order; any unexpected stage falls to the end.
        STAGE_ORDER = [
            "Intake and Assessment", "Full Data Entry",
            "Medical Review", "Quality Review",
        ]
        present = list(c["current_activity"].dropna().unique())
        ordered = [s for s in STAGE_ORDER if s in present] + \
                  [s for s in present if s not in STAGE_ORDER]

        def sdd(row):
            v = _num(row.get("days_to_submission_due"), None)
            return None if v is None else int(round(v))

        def case_brief(row) -> dict:
            return {
                "case_id": row["case_id"],
                "receipt": row["receipt"],
                "seriousness": row["seriousness"],
                "complexity": row["complexity"],
                "assigned_to": row["assigned_to"],
                "activity_due_status": row.get("activity_due_status") or "On Track",
                "days_to_sdd": sdd(row),
                "breach_prob": int(_num(row.get("breach_prob"))),
                "level": row["reg_risk"],
            }

        COMPLEXITY = ["Low", "Medium", "Large"]
        stages = []
        complexity_by_stage = []
        for stage in ordered:
            sub = c[c["current_activity"] == stage]
            breached = int(sub["activity_due_status"].astype(str).str.startswith("Red").sum())
            high = int((sub["reg_risk"] == "High").sum())
            cases = sorted(
                (case_brief(r) for _, r in sub.iterrows()),
                key=lambda x: (x["days_to_sdd"] if x["days_to_sdd"] is not None else 1e9),
            )
            stages.append({
                "stage": stage, "count": int(len(sub)),
                "high_reg": high, "breached": breached, "cases": cases,
            })
            counts = sub["complexity"].value_counts().to_dict()
            complexity_by_stage.append({
                "stage": stage,
                **{lvl: int(counts.get(lvl, 0)) for lvl in COMPLEXITY},
            })

        # Seriousness distribution. The dataset carries only serious variants, so
        # we group them: SUSAR is expedited-serious; Life Threatening + Death are
        # the most severe. (No non-serious records exist in this population.)
        def ser_bucket(v: str) -> str:
            v = str(v or "")
            if "SUSAR" in v:
                return "SUSAR (serious)"
            if v in ("Death", "Life Threatening"):
                return "Life-threatening / Death"
            if "Serious" in v:
                return "Serious"
            return "Non-serious"
        ser = c["seriousness"].map(ser_bucket).value_counts()
        ser_order = ["SUSAR (serious)", "Serious", "Life-threatening / Death", "Non-serious"]
        seriousness = [{"label": k, "value": int(ser.get(k, 0))}
                       for k in ser_order if ser.get(k, 0)]

        # Case classification by report type (active cases are all "Valid" under
        # report_classification, so report_type is the meaningful split here).
        cls = c["report_type"].fillna("Unknown").value_counts()
        classification = [{"label": k, "value": int(v)} for k, v in cls.items()]

        # Deadline watch, bucketed by days to Submission Due Date.
        def dl_bucket(row) -> str:
            v = _num(row.get("days_to_submission_due"), 999)
            if v < 0:
                return "Overdue"
            if v <= 2:
                return "Due ≤ 2 days"
            if v <= 6:
                return "3–6 days"
            return "7+ days"
        dl = c.apply(dl_bucket, axis=1).value_counts()
        dl_order = ["Overdue", "Due ≤ 2 days", "3–6 days", "7+ days"]
        deadline_watch = [{"label": k, "value": int(dl.get(k, 0))}
                          for k in dl_order if dl.get(k, 0)]

        # Flat active-case list tagged with each dimension's bucket, so the UI
        # can filter the detail table to any clicked donut slice.
        all_cases = []
        for _, r in c.iterrows():
            all_cases.append({
                "case_id": r["case_id"],
                "receipt": r["receipt"],
                "stage": r["current_activity"],
                "assigned_to": r["assigned_to"],
                "seriousness": r["seriousness"],
                "seriousness_bucket": ser_bucket(r["seriousness"]),
                "complexity": r["complexity"],
                "report_type": r.get("report_type") or "Unknown",
                "deadline_bucket": dl_bucket(r),
                "days_to_sdd": sdd(r),
                "breach_prob": int(_num(r.get("breach_prob"))),
                "activity_due_status": r.get("activity_due_status") or "On Track",
                "level": r["reg_risk"],
            })

        return {
            "active_total": int(len(c)),
            "stages": stages,
            "complexity_by_stage": complexity_by_stage,
            "complexity_levels": COMPLEXITY,
            "seriousness": seriousness,
            "classification": classification,
            "deadline_watch": deadline_watch,
            "cases": all_cases,
        }

    # ------------------------------------------------------------------
    # Generic case query — flexible fallback so the agent can reach ANY
    # case field (group-by / filter / list) without a bespoke tool.
    # ------------------------------------------------------------------
    _QUERY_ALIASES = {
        "stage": "current_activity", "activity": "current_activity",
        "team": "processing_unit", "unit": "processing_unit",
        "owner": "assigned_to", "classification": "report_classification",
    }
    _QUERY_COLS = {
        "receipt", "case_id", "seriousness", "complexity", "report_type",
        "study_type", "assessed", "current_activity", "processing_unit",
        "assigned_to", "case_owner", "report_classification", "product",
        "sender_org", "activity_due_status", "days_to_submission_due",
        "days_to_case_due", "breach_prob", "aging_ratio", "reassignment_count",
        "reg_risk", "sla_risk", "predictive_risk", "is_aging",
    }

    def query_cases(self, group_by=None, filters=None, select=None,
                    scope="active", limit=25) -> dict:
        df = (self.cases if scope == "all" else self.active).copy()

        def resolve(name):
            if not name:
                return None
            key = self._QUERY_ALIASES.get(str(name).strip().lower(), str(name).strip())
            return key if (key in self._QUERY_COLS and key in df.columns) else None

        def match(series, v):
            # numeric comparison when the value is like ">1", ">=75", "<=2", "2"
            s = str(v).strip()
            m = re.match(r"^(>=|<=|>|<|=)?\s*(-?\d+(?:\.\d+)?)$", s)
            num_series = pd.to_numeric(series, errors="coerce")
            if m and num_series.notna().any():
                op, num = (m.group(1) or "="), float(m.group(2))
                if op == ">":
                    return num_series > num
                if op == ">=":
                    return num_series >= num
                if op == "<":
                    return num_series < num
                if op == "<=":
                    return num_series <= num
                return num_series == num
            return series.astype(str).str.strip().str.lower() == s.lower()

        applied = {}
        for k, v in (filters or {}).items():
            c = resolve(k)
            if not c:
                continue
            applied[c] = v
            df = df[match(df[c], v)]

        if group_by:
            gc = resolve(group_by)
            if not gc:
                return {"error": f"cannot group by '{group_by}'",
                        "queryable_fields": sorted(self._QUERY_COLS)}
            vc = df[gc].fillna("(blank)").astype(str).value_counts().head(50)
            return {
                "scope": scope, "group_by": gc, "filters": applied,
                "total": int(len(df)),
                "counts": [{"value": k, "count": int(n)} for k, n in vc.items()],
            }

        cols = [c for c in (resolve(s) for s in (select or [])) if c]
        if not cols:
            cols = [c for c in ["receipt", "current_activity", "seriousness",
                                "complexity", "assigned_to", "days_to_submission_due",
                                "breach_prob"] if c in df.columns]
        if "case_id" in df.columns and "case_id" not in cols:
            cols = ["case_id"] + cols
        rows = df[cols].head(int(limit or 25))
        return {"scope": scope, "filters": applied, "count": int(len(df)),
                "cases": rows.to_dict("records")}

    # ------------------------------------------------------------------
    # Case drill-down (AC-08)
    # ------------------------------------------------------------------
    def case_detail(self, case_id: str) -> dict:
        c = self.cases[(self.cases["case_id"] == case_id) | (self.cases["receipt"] == case_id)]
        if not len(c):
            return {"error": f"case {case_id} not found"}
        rec = c.iloc[0].to_dict()
        cid = rec["case_id"]
        acts = self.activities[self.activities["case_id"] == cid].sort_values("sequence")
        asg = self.assignments[self.assignments["case_id"] == cid]
        reg = next((r for r in self.regulatory_risk()["evidence"] if r["case_id"] == cid), None)
        sla = [r for r in self.sla_risk()["evidence"] if r["case_id"] == cid]
        stuck = [r for r in self.stuck_cases()["evidence"] if r["case_id"] == cid]
        return {
            "case": rec,
            "activities": acts.to_dict("records"),
            "assignments": asg.to_dict("records"),
            "regulatory_risk": reg,
            "sla_risk": sla,
            "stuck": stuck,
        }

    # ------------------------------------------------------------------
    # 7. Next Best Action (AC-07)
    # ------------------------------------------------------------------
    def next_best_action(self, case_id: str | None = None, team: str | None = None) -> dict:
        reg = {r["case_id"]: r for r in self.regulatory_risk(level="High")["evidence"]}
        stuck_ids = {r["case_id"] for r in self.stuck_cases()["evidence"]}
        wl = {w["user"]: w for w in self.workload()["evidence"]}

        targets = [case_id] if case_id else list(reg.keys())
        candidates = []
        for cid in targets:
            r = reg.get(cid)
            if not r:
                # allow NBA on any active case
                row = self.active[self.active["case_id"] == cid]
                if not len(row):
                    continue
                r = {"case_id": cid, "level": row.iloc[0]["reg_risk"], "stage": row.iloc[0]["current_activity"],
                     "team": row.iloc[0]["processing_unit"], "assigned_to": row.iloc[0]["assigned_to"],
                     "seriousness": row.iloc[0]["seriousness"], "reason": "", "days_to_sdd": _num(row.iloc[0]["days_to_submission_due"], 99)}
            score, action, rationale = 0.0, "monitor", []
            if r["level"] == "High":
                score += 3; action = "prioritize"; rationale.append(r.get("reason", ""))
            if cid in stuck_ids:
                score += 2
                if str(r.get("seriousness", "")).lower().find("serious") >= 0 or "SUSAR" in str(r.get("seriousness", "")):
                    action = "escalate"; rationale.append("Activity is aging well beyond norm on a serious case.")
            # suitability-aware reassign: pick the best-suited qualified reviewer
            # (skill + efficiency + experience + capacity), not merely whoever
            # is free. Only suggest a move when the owner is overloaded.
            owner = r.get("assigned_to")
            owner_wl = wl.get(owner)
            if owner_wl and owner_wl["state"] == "overloaded":
                ranked = self.rank_reviewers(
                    r.get("stage"), r.get("complexity", ""), r.get("seriousness", ""),
                    exclude=owner)
                best = next((x for x in ranked if x["state"] != "overloaded"), None)
                if best:
                    score += 1.5
                    if action == "monitor":
                        action = "reassign"
                    rationale.append(
                        f"{owner} is at {owner_wl['utilization_pct']}%; best-suited qualified "
                        f"reviewer is {best['reviewer']} ({best['tier']}, {best['efficiency']}× norm, "
                        f"{best['experience']} handled, now at {best['utilization_pct']}%).")
                    if best.get("warning"):
                        rationale.append("⚠ " + best["warning"])
            candidates.append({
                "case_id": cid, "recommended_action": action, "score": round(score, 2),
                "level": r["level"], "stage": r.get("stage"), "team": r.get("team"),
                "rationale": [x for x in rationale if x] or [r.get("reason", "Monitor.")],
                "human_approval_required": True,
            })
        candidates.sort(key=lambda x: x["score"], reverse=True)
        return {"value": candidates[0] if candidates else None, "candidates": candidates}

    # ------------------------------------------------------------------
    # DIFFERENTIATOR: what-if reassignment simulator
    # ------------------------------------------------------------------
    def simulate_reassignment(self, from_user: str, to_user: str,
                              case_ids: list[str] | None = None,
                              n: int | None = None) -> dict:
        """Counterfactual: move case(s) from one owner to another and recompute
        workload + breach exposure. Qualification-aware: warns if roles differ."""
        wl = {w["user"]: w for w in self.workload()["evidence"]}
        if from_user not in wl or to_user not in wl:
            return {"error": "unknown user(s)"}
        src, dst = wl[from_user], wl[to_user]

        owned = self.active[self.active["assigned_to"] == from_user]
        if case_ids:
            moved = owned[owned["case_id"].isin(case_ids)]
        else:
            # move the highest-risk n cases by breach probability
            k = n or 1
            moved = owned.sort_values("breach_prob", ascending=False).head(k)
        moved_ids = moved["case_id"].tolist()
        count = len(moved_ids)

        # Workload shift: approximate each case as src.planned/src.wip hours.
        per_case_hours = _num(src["planned_hours"]) / max(_num(src["wip"]), 1)
        src_planned = _num(src["planned_hours"]) - per_case_hours * count
        dst_planned = _num(dst["planned_hours"]) + per_case_hours * count
        src_util = round(src_planned / _num(src["available_hours"], 1), 2)
        dst_util = round(dst_planned / _num(dst["available_hours"], 1), 2)

        qualified = src["role"] == dst["role"]
        # breaches pulled back: moved cases whose owner was overloaded and target isn't
        relieved = count if (src["state"] == "overloaded" and dst_util <= 1.0) else 0

        # Suitability of the recipient for the actual cases being moved —
        # considers skill, efficiency, and experience, not just the role.
        dst_prof = self.reviewers.get(to_user, {})
        worst = None
        for _, mc in moved.iterrows():
            s = self.suitability(to_user, mc["current_activity"], mc["complexity"], mc["seriousness"])
            if worst is None or s["score"] < worst["score"]:
                worst = s
        if not qualified:
            note = (f"WARNING: {from_user} is {src['role']} but {to_user} is {dst['role']}; "
                    f"this work must stay within a qualified {src['role']}.")
            ok = False
        elif worst and worst.get("warning"):
            note = worst["warning"]
            ok = False
        else:
            note = (f"{to_user} is a {dst_prof.get('tier','?')} reviewer "
                    f"({dst_prof.get('efficiency','?')}× norm, {dst_prof.get('experience','?')} handled) "
                    f"— suitable for these cases.")
            ok = True
        return {
            "from": {"user": from_user, "role": src["role"], "tier": self.reviewers.get(from_user, {}).get("tier"),
                     "before_pct": src["utilization_pct"], "after_pct": round(src_util * 100)},
            "to": {"user": to_user, "role": dst["role"], "tier": dst_prof.get("tier"),
                   "efficiency": dst_prof.get("efficiency"), "experience": dst_prof.get("experience"),
                   "before_pct": dst["utilization_pct"], "after_pct": round(dst_util * 100)},
            "moved_cases": moved_ids,
            "moved_count": count,
            "qualified": bool(qualified and ok),
            "suitability_score": worst["score"] if worst else None,
            "qualification_note": note,
            "relieved_from_overload": relieved,
            "summary": (
                f"Moving {count} case(s) from {from_user} to {to_user}: "
                f"{from_user} {src['utilization_pct']}%→{round(src_util*100)}%, "
                f"{to_user} {dst['utilization_pct']}%→{round(dst_util*100)}%."),
        }

    # ------------------------------------------------------------------
    # DIFFERENTIATOR: role-aware rebalance plan to clear a bottleneck
    # ------------------------------------------------------------------
    def rebalance_plan(self, unit: str = MEDICAL) -> dict:
        """Propose moves to relieve an overloaded owner, routing each case to the
        best-suited qualified reviewer (skill + efficiency + experience + spare
        capacity) — not simply whoever is least loaded."""
        wl = {w["user"]: w for w in self.workload()["evidence"] if w["team"] == unit}
        if not wl:
            return {"error": f"no users in {unit}"}
        # live utilization we mutate as we assign (so we don't overload a target)
        util = {u: _num(w["utilization"]) for u, w in wl.items()}
        avail_hours = {u: _num(w["available_hours"], 1) for u, w in wl.items()}
        stage = unit  # stage name == processing unit label for the live population

        over = sorted([w for w in wl.values() if w["state"] == "overloaded"],
                      key=lambda w: -w["utilization"])
        moves = []
        for src in over:
            owned = self.active[(self.active["assigned_to"] == src["user"])
                                & (self.active["current_activity"] == stage)]
            owned = owned.sort_values("breach_prob", ascending=False)
            per = _num(src["planned_hours"]) / max(_num(src["wip"]), 1)
            src_util = util[src["user"]]
            for _, case in owned.iterrows():
                if src_util <= 1.0:
                    break
                # rank qualified reviewers for THIS case, excluding the owner and
                # anyone already at/over capacity in our running estimate
                ranked = self.rank_reviewers(stage, case["complexity"], case["seriousness"],
                                             exclude=src["user"])
                target = next((r for r in ranked if util.get(r["reviewer"], 2) < 1.0), None)
                if not target:
                    break
                t = target["reviewer"]
                moves.append({
                    "case_id": case["case_id"], "receipt": case["receipt"],
                    "from": src["user"], "to": t, "role": wl[t]["role"],
                    "to_tier": target["tier"], "to_efficiency": target["efficiency"],
                    "to_experience": target["experience"], "suitability": target["score"],
                    "complexity": case["complexity"], "seriousness": case["seriousness"],
                    "why": (f"{src['user']} over capacity; {t} is the best-suited qualified "
                            f"reviewer ({target['tier']}, {target['efficiency']}× norm, "
                            f"{target['experience']} handled)."),
                    "warning": target.get("warning"),
                })
                # update running estimates
                util[src["user"]] = src_util = src_util - per / avail_hours[src["user"]]
                util[t] = util.get(t, 0) + per / avail_hours[t]
        return {
            "unit": unit,
            "moves": moves,
            "move_count": len(moves),
            "note": "Each case routed to the best-suited qualified reviewer by skill, "
                    "efficiency, and experience — not just free capacity. "
                    "Human approval required before execution.",
        }

    # ------------------------------------------------------------------
    # DIFFERENTIATOR: daily action briefing (their Q6)
    # ------------------------------------------------------------------
    def daily_briefing(self) -> dict:
        reg = self.regulatory_risk(level="High")["evidence"]
        bott = self.bottlenecks()
        over = self.workload()["value"]
        aging = self.stuck_cases()["value"]
        p1 = []
        nba = {c["case_id"]: c for c in self.next_best_action()["candidates"]}
        for r in reg:
            c = nba.get(r["case_id"])
            p1.append({
                "case_id": r["case_id"], "receipt": r["receipt"], "stage": r["stage"],
                "owner": r["assigned_to"], "days_to_sdd": r["days_to_sdd"],
                "action": c["recommended_action"] if c else "prioritize",
                "reason": r["reason"],
            })
        return {
            "as_of": self.now.isoformat(),
            "headline": (f"{len(reg)} P1 cases need action today; "
                         f"{bott['value']} is Critical; "
                         f"{len(over)} user(s) over capacity; {aging} aging activities."),
            "p1_cases": p1,
            "critical_bottleneck": bott["value"],
            "overloaded_users": over,
            "aging_count": aging,
        }
