"""Generate a schema-compatible synthetic LSMV dataset for the demo.

Mirrors the field list in the problem statement (case id/type/seriousness,
reporting + activity due dates, workflow/activity status, assignment/team,
start/end timestamps, aging, reassignment history, complexity, historical
turnaround, reporting status).

The data is SEEDED (fixed PRNG) to reproduce the problem statement's headline
example when the engine runs against it:
  - 12 cases at HIGH risk of missing their reporting deadline
  - 5 cases delayed in Medical Review (the bottleneck stage)
  - Priya Nair operating at ~125% capacity, with Omar Haddad holding slack
  - 3 cases stuck in the same activity far longer than historical norm

Deterministic output keeps the demo and the engine unit tests reproducible.
Writes CSVs under backend/data/ and returns the frames.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import pandas as pd

# "Now" for the snapshot. Fixed so deadlines/aging are deterministic.
AS_OF = datetime(2026, 10, 8, 9, 0, 0)
SEED = 2026

# Workflow stages in order. Medical Review is deliberately the bottleneck.
STAGES = ["Data Entry", "Medical Review", "Quality Review", "Submission"]
TEAMS = {
    "Data Entry": "Intake",
    "Medical Review": "Medical",
    "Quality Review": "Quality",
    "Submission": "Regulatory",
}

# Users per team with CONCURRENT capacity (open cases carried at once).
USERS = [
    ("Aarav Shah", "Intake", 8.0),
    ("Diego Ramos", "Intake", 8.0),
    ("Priya Nair", "Medical", 8.0),      # overloaded in the plan (~125%)
    ("Mei Lin", "Medical", 8.0),
    ("Omar Haddad", "Medical", 8.0),     # slack in the plan (reassign target)
    ("Sofia Rossi", "Quality", 8.0),
    ("Tom Becker", "Quality", 8.0),
    ("Yuki Tanaka", "Regulatory", 7.0),
    ("Grace Owusu", "Regulatory", 7.0),
]

# Deterministic open-item target per user for in-progress activities. The
# per-team totals define how many in-progress cases sit at each stage.
#   Medical total 21: Priya 10 (125%), Mei 7 (88%), Omar 4 (50% slack)
WORKLOAD_PLAN = {
    "Aarav Shah": 7, "Diego Ramos": 6,                       # Intake  = 13
    "Priya Nair": 10, "Mei Lin": 7, "Omar Haddad": 4,        # Medical = 21
    "Sofia Rossi": 7, "Tom Becker": 6,                       # Quality = 13
    "Yuki Tanaka": 6, "Grace Owusu": 5,                      # Reg     = 11
}

# Historical turnaround benchmarks (hours) per stage x complexity: p50/p80/p95.
BENCHMARKS = {
    ("Data Entry", "low"): (6, 12, 20),
    ("Data Entry", "medium"): (10, 18, 30),
    ("Data Entry", "high"): (14, 26, 44),
    ("Medical Review", "low"): (18, 30, 48),
    ("Medical Review", "medium"): (28, 50, 80),
    ("Medical Review", "high"): (44, 80, 130),
    ("Quality Review", "low"): (8, 16, 28),
    ("Quality Review", "medium"): (12, 24, 40),
    ("Quality Review", "high"): (18, 34, 56),
    ("Submission", "low"): (4, 8, 14),
    ("Submission", "medium"): (6, 12, 20),
    ("Submission", "high"): (10, 18, 30),
}

CASE_TYPES = ["Spontaneous", "Clinical Trial", "Literature", "Regulatory Authority"]
COUNTRIES = ["US", "UK", "DE", "JP", "FR", "IN", "BR", "CA"]
PRODUCTS = ["Cardizol", "Neuroxa", "Immunept", "Dermaclear", "Oncolyn"]


@dataclass
class Gen:
    rng: random.Random = field(default_factory=lambda: random.Random(SEED))
    cases: list[dict] = field(default_factory=list)
    activities: list[dict] = field(default_factory=list)
    reassignments: list[dict] = field(default_factory=list)
    _aid: int = 0
    _cid: int = 0

    def hours(self, h: float) -> timedelta:
        return timedelta(hours=h)

    def new_case_id(self) -> str:
        self._cid += 1
        return f"CASE{self._cid:04d}"

    def new_activity_id(self) -> str:
        self._aid += 1
        return f"ACT{self._aid:05d}"

    def add_case(
        self,
        *,
        current_stage: str | None,
        seriousness: str,
        complexity: str,
        days_to_due: float,
        assignee: str | None = None,
        delayed: bool = False,
        stuck: bool = False,
    ) -> str:
        """Create one case plus its per-stage activities.

        Stages before current_stage are complete; current_stage is in-progress
        and owned by `assignee`; later stages are not-started. `delayed` makes
        the in-progress activity run moderately long (bottleneck); `stuck` makes
        it run past p95.
        """
        cid = self.new_case_id()
        created = AS_OF - self.hours(self.rng.uniform(24, 160))
        reporting_due = AS_OF + self.hours(days_to_due * 24)
        closed = current_stage is None

        self.cases.append(
            {
                "case_id": cid,
                "case_type": self.rng.choice(CASE_TYPES),
                "seriousness": seriousness,
                "complexity": complexity,
                "country": self.rng.choice(COUNTRIES),
                "product": self.rng.choice(PRODUCTS),
                "created_at": created.isoformat(),
                "reporting_due_date": reporting_due.isoformat(),
                "reporting_status": "submitted" if closed else "pending",
                "workflow_status": "closed" if closed else "in-progress",
            }
        )

        stage_idx = len(STAGES) if closed else STAGES.index(current_stage)
        cursor = created
        for i, stage in enumerate(STAGES):
            aid = self.new_activity_id()
            team = TEAMS[stage]
            p50, p80, p95 = BENCHMARKS[(stage, complexity)]

            if i < stage_idx:  # completed
                dur = self.rng.uniform(p50 * 0.6, p80)
                start, end = cursor, cursor + self.hours(dur)
                cursor = end
                self._emit(aid, cid, stage, team, "complete", start, end, None,
                           self._pick_user(team))
            elif i == stage_idx:  # in-progress
                if stuck:
                    elapsed = p95 * self.rng.uniform(1.4, 2.0)
                elif delayed:
                    elapsed = p80 * self.rng.uniform(1.05, 1.4)
                else:
                    elapsed = self.rng.uniform(p50 * 0.4, p80 * 0.9)
                start = AS_OF - self.hours(elapsed)
                act_due = start + self.hours(p80)
                self._emit(aid, cid, stage, team, "in-progress", start, None,
                           act_due, assignee or self._pick_user(team))
            else:  # not started
                self._emit(aid, cid, stage, team, "not-started", None, None, None, None)
        return cid

    def _pick_user(self, team: str) -> str:
        return self.rng.choice([u[0] for u in USERS if u[1] == team])

    def _emit(self, aid, cid, stage, team, status, start, end, act_due, assignee):
        self.activities.append(
            {
                "activity_id": aid,
                "case_id": cid,
                "activity_name": stage,
                "team": team,
                "assigned_to": assignee,
                "activity_status": status,
                "start_ts": start.isoformat() if start else None,
                "end_ts": end.isoformat() if end else None,
                "activity_due_date": act_due.isoformat() if act_due else None,
            }
        )
        if status == "in-progress" and self.rng.random() < 0.3:
            members = [u[0] for u in USERS if u[1] == team]
            for _ in range(self.rng.randint(1, 3)):
                self.reassignments.append(
                    {
                        "activity_id": aid,
                        "case_id": cid,
                        "from_user": self.rng.choice(members),
                        "to_user": assignee or self.rng.choice(members),
                        "ts": (AS_OF - self.hours(self.rng.uniform(2, 40))).isoformat(),
                        "reason": self.rng.choice(
                            ["load balancing", "expertise", "absence", "escalation"]
                        ),
                    }
                )


def generate() -> dict[str, pd.DataFrame]:
    g = Gen()

    # Build a per-team queue of (assignee) slots from the workload plan, so the
    # number of in-progress cases per stage matches the plan exactly.
    team_slots: dict[str, list[str]] = {t: [] for t in TEAMS.values()}
    for user, count in WORKLOAD_PLAN.items():
        team = next(u[1] for u in USERS if u[0] == user)
        team_slots[team].extend([user] * count)
    for team in team_slots:
        g.rng.shuffle(team_slots[team])

    stage_for_team = {v: k for k, v in TEAMS.items()}

    # Decide which in-progress cases are special. We want, across all stages:
    #   12 HIGH reg-risk (tight deadline + early stage + high complexity)
    #    5 delayed-in-Medical (bottleneck)
    #    3 stuck
    # Assign these flags as we fill team slots.
    high_risk_budget = 12
    stuck_budget = 3
    delayed_medical_budget = 5

    # Fill Medical first so delayed/stuck/high-risk land there visibly.
    order = ["Medical", "Intake", "Quality", "Regulatory"]
    for team in order:
        stage = stage_for_team[team]
        slots = team_slots[team]
        for idx, assignee in enumerate(slots):
            stuck = False
            delayed = False
            # distribute stuck across Medical/Quality
            if stuck_budget and team in ("Medical", "Quality") and idx % 7 == 2:
                stuck = True
                stuck_budget -= 1
            if (not stuck and delayed_medical_budget and team == "Medical"
                    and idx % 3 == 0):
                delayed = True
                delayed_medical_budget -= 1

            # high-risk: tight deadline + high complexity + early stage
            make_high = False
            if high_risk_budget and stage in ("Data Entry", "Medical Review"):
                # take ~2/3 of high-risk from Medical, rest from Intake
                if (team == "Medical" and idx % 2 == 1) or (team == "Intake" and idx % 2 == 0):
                    make_high = True
            if make_high:
                high_risk_budget -= 1
                g.add_case(
                    current_stage=stage,
                    seriousness="serious",
                    complexity="high",
                    days_to_due=g.rng.uniform(0.6, 2.0),
                    assignee=assignee,
                    delayed=delayed,
                    stuck=stuck,
                )
            else:
                g.add_case(
                    current_stage=stage,
                    seriousness=g.rng.choice(["serious", "non-serious"]),
                    complexity=g.rng.choice(["low", "medium", "high"]),
                    days_to_due=g.rng.uniform(5, 26),
                    assignee=assignee,
                    delayed=delayed,
                    stuck=stuck,
                )

    # Any leftover high-risk budget: add a few more early-stage tight cases to
    # non-plan slots (slightly raises team load, acceptable).
    while high_risk_budget > 0:
        high_risk_budget -= 1
        g.add_case(
            current_stage="Data Entry",
            seriousness="serious",
            complexity="high",
            days_to_due=g.rng.uniform(0.6, 2.0),
            assignee="Diego Ramos",
        )

    # Closed/background cases for realism (do not count as in-progress load).
    for _ in range(25):
        g.add_case(
            current_stage=None,
            seriousness=g.rng.choice(["serious", "non-serious"]),
            complexity=g.rng.choice(["low", "medium", "high"]),
            days_to_due=g.rng.uniform(-5, 20),
        )

    return {
        "cases": pd.DataFrame(g.cases),
        "activities": pd.DataFrame(g.activities),
        "reassignments": pd.DataFrame(g.reassignments),
        "users": pd.DataFrame(
            [{"user_id": u, "name": u, "team": t, "capacity_per_day": c} for u, t, c in USERS]
        ),
        "benchmarks": pd.DataFrame(
            [
                {"activity_name": s, "complexity": c, "p50": p50, "p80": p80, "p95": p95}
                for (s, c), (p50, p80, p95) in BENCHMARKS.items()
            ]
        ),
    }


def write_csvs(out_dir) -> dict[str, pd.DataFrame]:
    from pathlib import Path

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    frames = generate()
    for name, df in frames.items():
        df.to_csv(out / f"{name}.csv", index=False)
    return frames


if __name__ == "__main__":
    from pathlib import Path

    frames = write_csvs(Path(__file__).resolve().parents[1] / "data")
    for name, df in frames.items():
        print(f"{name:14s} {len(df):5d} rows")
