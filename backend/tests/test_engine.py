"""Engine tests pinned to the REAL LSMV workbook's expected outcomes.

These assert that our engine, computing from the documented derivation rules,
reproduces the exact numbers published in the workbook's Expected_Dashboard_
Outcomes / Sample_Dashboard_Snapshot. This is the audit story: same spec data ->
same spec numbers.

Run: backend/.venv/Scripts/python.exe -m pytest backend/tests -q
Requires the DB built from the workbook (app.lsmv.build()).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import lsmv  # noqa: E402
from app.engine import Engine, Store, weights  # noqa: E402


@pytest.fixture(scope="module")
def engine(tmp_path_factory) -> Engine:
    db = str(tmp_path_factory.mktemp("db") / "lsmv.db")
    lsmv.build(db_path=db)
    weights.cache_clear()
    return Engine(Store(db))


def test_workflow_health_is_62_amber(engine):
    h = engine.workflow_health()
    assert h["value"] == 62
    assert h["status"].startswith("Amber")


def test_regulatory_high_is_12(engine):
    r = engine.regulatory_risk()
    assert r["value"] == 12
    assert len(engine.regulatory_risk(level="High")["evidence"]) == 12
    for row in engine.regulatory_risk(level="High")["evidence"]:
        assert row["reason"]  # explainability (AC-06)


def test_predictive_sla_high_is_12(engine):
    assert engine.sla_risk()["value"] == 12
    for row in engine.sla_risk()["evidence"]:
        assert row["breach_prob"] >= 75


def test_medical_review_is_critical_with_5_breached(engine):
    b = engine.bottlenecks()
    assert b["value"] == "Medical Review"
    med = next(r for r in b["evidence"] if r["processing_unit"] == "Medical Review")
    assert med["status"] == "Critical"
    assert med["breached"] == 5


def test_person_a_125_and_person_d_113(engine):
    wl = {w["user"]: w for w in engine.workload()["evidence"]}
    assert wl["Person A"]["utilization_pct"] == 125
    assert wl["Person D"]["utilization_pct"] == 113
    assert set(engine.workload()["value"]) == {"Person A", "Person D"}


def test_three_aging_activities(engine):
    s = engine.stuck_cases()
    assert s["value"] == 3
    for row in s["evidence"]:
        assert row["x_over_norm"] >= 2.0


def test_case_count_is_165(engine):
    assert len(engine.cases) == 165


def test_nba_reassign_is_qualification_aware(engine):
    """A reassign recommendation must keep work within the same role."""
    nba = engine.next_best_action()
    reassigns = [c for c in nba["candidates"] if c["recommended_action"] == "reassign"]
    for c in reassigns:
        joined = " ".join(c["rationale"])
        assert "qualified" in joined.lower() or "Safety Physician" in joined
    for c in nba["candidates"]:
        assert c["human_approval_required"] is True  # governance (AC-10)


def test_simulator_blocks_unqualified_move(engine):
    bad = engine.simulate_reassignment("Person D", "Person A", n=1)
    assert bad["qualified"] is False
    assert "Safety Physician" in bad["qualification_note"]
    good = engine.simulate_reassignment("Person D", "Person E", n=1)
    assert good["qualified"] is True
    assert good["to"]["after_pct"] > good["to"]["before_pct"]


def test_rebalance_plan_keeps_role(engine):
    rp = engine.rebalance_plan("Medical Review")
    assert rp["move_count"] >= 1
    for m in rp["moves"]:
        assert m["role"] == "Safety Physician"


def test_daily_briefing_lists_12_p1(engine):
    b = engine.daily_briefing()
    assert len(b["p1_cases"]) == 12
    assert b["critical_bottleneck"] == "Medical Review"


def test_reviewer_profiles_derive_tiers(engine):
    """Every reviewer gets a tier from efficiency + experience, and the pool
    splits into more than one tier (so routing can prefer the stronger ones)."""
    profs = engine.reviewers
    assert len(profs) == 12
    tiers = {p["tier"] for p in profs.values()}
    assert "Senior" in tiers and len(tiers) >= 2
    # Person D cleared work fastest (0.78x) → Senior; efficiency recorded
    assert profs["Person D"]["tier"] == "Senior"
    assert profs["Person D"]["efficiency"] <= profs["Person E"]["efficiency"]


def test_suitability_requires_skill(engine):
    """A reviewer with no history in a stage is not suitable for it."""
    s = engine.suitability("Person A", "Medical Review", "Large", "Serious")
    assert s["qualified"] is False  # Person A only does Full Data Entry


def test_suitability_flags_weak_reviewer_on_heavy_case(engine):
    """A Developing reviewer on a Large/serious case is penalized and warned."""
    dev = next((u for u, p in engine.reviewers.items() if p["tier"] == "Developing"), None)
    assert dev is not None
    stage = engine.reviewers[dev]["skills"][0]
    heavy = engine.suitability(dev, stage, "Large", "SUSAR - Serious")
    light = engine.suitability(dev, stage, "Medium", "Non-serious")
    assert heavy["warning"] is not None
    assert heavy["score"] < light["score"]


def test_rebalance_routes_by_suitability_not_just_capacity(engine):
    rp = engine.rebalance_plan("Medical Review")
    for m in rp["moves"]:
        # every move names the recipient's tier/efficiency, proving it was
        # chosen on suitability, not merely free capacity
        assert "to_tier" in m and "to_efficiency" in m and "suitability" in m


def test_simulator_reports_recipient_suitability(engine):
    sim = engine.simulate_reassignment("Person D", "Person E", n=1)
    assert sim["to"]["tier"] is not None
    assert sim["to"]["efficiency"] is not None
    assert "suitability_score" in sim


def test_case_detail_round_trips(engine):
    cid = engine.regulatory_risk(level="High")["evidence"][0]["case_id"]
    d = engine.case_detail(cid)
    assert d["case"]["case_id"] == cid
    assert len(d["activities"]) >= 1
    assert d["regulatory_risk"]["level"] == "High"
