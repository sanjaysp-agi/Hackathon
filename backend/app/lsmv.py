"""Ingest the REAL shared LSMV workbook (.xlsb) into SQLite.

The workbook (INTELLIGENT WORKFLOW MANAGER.xlsb) is the authoritative sample +
expected-output spec: 165 cases, with pre-derived risk flags and the exact
numbers the dashboard must reproduce (62 health / 12 reg / 12 SLA / 12
predictive / 5 Medical Review breached / Person A 125% / 3 aging).

This loader reads every sheet, converts Excel serial dates to ISO timestamps,
normalizes column names to clean snake_case, and writes SQLite tables the engine
reads. The engine RECOMPUTES the risk classifications from the documented
derivation rules (it does not merely echo the workbook's flags) — the workbook's
flags are kept alongside so tests can prove our computation matches.

As-of ("now") is the workbook's dashboard timestamp: 2026-10-06 09:00.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import pyxlsb

from . import config

ROOT = Path(__file__).resolve().parents[2]
XLSB = ROOT / "INTELLIGENT WORKFLOW MANAGER.xlsb"

# Excel serial epoch (Windows 1900 system, with the standard 1899-12-30 base).
EXCEL_EPOCH = datetime(1899, 12, 30)
AS_OF_SERIAL = 46301.375  # from Sample_Dashboard_Snapshot -> 2026-10-06 09:00


def serial_to_dt(v) -> datetime | None:
    if v is None or v == "":
        return None
    try:
        return EXCEL_EPOCH + timedelta(days=float(v))
    except (TypeError, ValueError):
        return None


def serial_to_iso(v) -> str | None:
    dt = serial_to_dt(v)
    return dt.isoformat() if dt else None


AS_OF = serial_to_dt(AS_OF_SERIAL)


def _read_sheet(wb, name: str) -> pd.DataFrame:
    with wb.get_sheet(name) as sh:
        rows = [[c.v for c in r] for r in sh.rows()]
    if not rows:
        return pd.DataFrame()
    header = [str(h) if h is not None else f"col{i}" for i, h in enumerate(rows[0])]
    data = [r for r in rows[1:] if any(v is not None for v in r)]
    # pad/truncate every row to header width
    width = len(header)
    data = [(r + [None] * width)[:width] for r in data]
    return pd.DataFrame(data, columns=header)


# Column renames: workbook header -> clean snake_case used by the engine.
CASE_COLS = {
    "Company Unit": "company_unit",
    "Receipt#": "receipt",
    "AER#": "aer",
    "Assessed": "assessed",
    "WorkFlow Activity": "current_activity",
    "Case seriousness": "seriousness",
    "Report Type": "report_type",
    "Study Type": "study_type",
    "Suspect Product Count": "suspect_product_count",
    "Event Count": "event_count",
    "Case complexity": "complexity",
    "Date Of Creation": "created",
    "Latest Received Date": "latest_received",
    "Activity Received Date": "activity_received",
    "Activity Due Date": "activity_due",
    "Case Due Date": "case_due",
    "No of days due to Case Due Date": "days_to_case_due",
    "Submission Due Date": "submission_due",
    "No of days due to Submission Due Date": "days_to_submission_due",
    "Aging (Derived, Days)": "aging_days",
    "Historical turnaround time (Derived, Hours)": "historical_hours",
    "Current Activity Aging (Hours)": "activity_aging_hours",
    "Aging vs Historical Ratio": "aging_ratio",
    "Significantly Longer than Historical Norm": "sig_longer",
    "Product Description": "product",
    "Assigned To": "assigned_to",
    "Case Owner": "case_owner",
    "Report Classification": "report_classification",
    "Sender Organization as Coded": "sender_org",
    "Processing Unit": "processing_unit",
    "Activity Due Status": "activity_due_status",
    "Reassignment Count": "reassignment_count",
    "Regulatory Risk": "wb_regulatory_risk",      # wb_ = workbook's own flag
    "SLA Risk": "wb_sla_risk",
    "Predictive SLA Risk": "wb_predictive_risk",
    "Predicted SLA Breach Probability (%)": "wb_breach_prob",
    "Predictive Risk Reason": "wb_predictive_reason",
    "Composite Risk Score": "wb_risk_score",
    "Risk Reason": "wb_risk_reason",
    "Recommended Action": "wb_recommended_action",
}
DATE_FIELDS_CASE = [
    "created", "latest_received", "activity_received", "activity_due",
    "case_due", "submission_due",
]

ACT_COLS = {
    "Activity ID": "activity_id",
    "Case ID": "case_id",
    "Receipt#": "receipt",
    "Activity Sequence": "sequence",
    "WorkFlow Activity": "activity_name",
    "Processing Unit": "processing_unit",
    "Assigned To": "assigned_to",
    "Activity Status": "status",
    "Activity Start Timestamp": "start_ts",
    "Activity Due Date": "due_ts",
    "Activity Completed Timestamp": "completed_ts",
    "Activity Aging (Hours)": "aging_hours",
    "Historical Median (Hours)": "historical_median_hours",
    "Aging vs Historical Ratio": "aging_ratio",
    "Activity Due Status": "due_status",
    "Reassignment Count": "reassignment_count",
    "Dependency Status": "dependency_status",
    "Blocking Reason": "blocking_reason",
    "Last Updated Timestamp": "last_updated",
}
DATE_FIELDS_ACT = ["start_ts", "due_ts", "completed_ts", "last_updated"]

ASG_COLS = {
    "Assignment Event ID": "event_id",
    "Case ID": "case_id",
    "Receipt#": "receipt",
    "AER#": "aer",
    "Activity ID": "activity_id",
    "WorkFlow Activity": "activity_name",
    "Processing Unit": "processing_unit",
    "Reassignment Number": "reassignment_number",
    "Changed Timestamp": "changed_ts",
    "Assigned From": "from_user",
    "Assigned To": "to_user",
    "Change Reason": "reason",
    "Handover Status": "handover_status",
}

CAP_COLS = {
    "User ID": "user_id",
    "User Name": "user",
    "Processing Unit": "processing_unit",
    "Role": "role",
    "Available Hours / Week": "available_hours",
    "Planned Hours / Week": "planned_hours",
    "Capacity Utilization (%)": "utilization_pct",
    "Current WIP": "wip",
    "Capacity Status": "capacity_status",
    "Management Action": "management_action",
    "Active Cases in Dashboard": "active_cases",
}

BENCH_COLS = {
    "WorkFlow Activity": "activity_name",
    "Processing Unit": "processing_unit",
    "Case complexity": "complexity",
    "Historical Sample Size": "sample_size",
    "Median Turnaround Time (Hours)": "median_hours",
    "P75 Turnaround Time (Hours)": "p75_hours",
    "P90 Turnaround Time (Hours)": "p90_hours",
    "SLA Target (Hours)": "sla_target_hours",
    "Benchmark Period": "benchmark_period",
}

BOTT_COLS = {
    "Processing Unit": "processing_unit",
    "Active WIP": "active_wip",
    "Active Activities Past Activity Due Date": "breached",
    "Active Activities Approaching Activity Due Date": "approaching",
    "Average Activity Aging (Hours)": "avg_aging_hours",
    "Historical Median (Hours)": "historical_median_hours",
    "Aging vs Historical Ratio": "aging_ratio",
    "Bottleneck Status": "wb_status",
    "Bottleneck Explanation": "wb_explanation",
    "Management Action": "wb_action",
    "As Of Timestamp": "as_of",
}

# Governed P1 action log (Risk_Recommendations) — evidence, approval, audit ref.
REC_COLS = {
    "Action ID": "action_id",
    "Case ID": "case_id",
    "Receipt#": "receipt",
    "AER#": "aer",
    "Risk Type": "risk_type",
    "Risk Level": "risk_level",
    "Risk Score": "risk_score",
    "Predicted Miss Probability (%)": "miss_prob",
    "Predictive SLA Risk": "predictive_sla_risk",
    "Predicted SLA Breach Probability (%)": "breach_prob",
    "WorkFlow Activity": "activity",
    "Processing Unit": "processing_unit",
    "Assigned To": "assigned_to",
    "Activity Due Date": "activity_due",
    "Case Due Date": "case_due",
    "Submission Due Date": "submission_due",
    "Supporting Data": "supporting_data",
    "Risk Reason": "risk_reason",
    "Predictive Risk Reason": "predictive_reason",
    "Recommended Action": "recommended_action",
    "Action Priority": "priority",
    "Human Approval Required": "human_approval",
    "Action Status": "status",
    "Generated Timestamp": "generated_ts",
    "Audit Reference": "audit_ref",
}
DATE_FIELDS_REC = ["activity_due", "case_due", "submission_due", "generated_ts"]


def _apply(df: pd.DataFrame, mapping: dict, date_fields: list[str] | None = None) -> pd.DataFrame:
    keep = {k: v for k, v in mapping.items() if k in df.columns}
    out = df[list(keep)].rename(columns=keep).copy()
    for f in date_fields or []:
        if f in out.columns:
            out[f] = out[f].map(serial_to_iso)
    return out


def build(db_path: str | None = None) -> str:
    db_path = db_path or config.DB_PATH
    wb = pyxlsb.open_workbook(str(XLSB))

    cases = _apply(_read_sheet(wb, "Dashboard_Case_Detail"), CASE_COLS, DATE_FIELDS_CASE)
    acts = _apply(_read_sheet(wb, "Workflow_Activities"), ACT_COLS, DATE_FIELDS_ACT)
    asg = _apply(_read_sheet(wb, "Assignment_History"), ASG_COLS, ["changed_ts"])
    cap = _apply(_read_sheet(wb, "User_Capacity"), CAP_COLS)
    bench = _apply(_read_sheet(wb, "Historical_Benchmarks"), BENCH_COLS)
    bott = _apply(_read_sheet(wb, "Workflow_Bottlenecks"), BOTT_COLS, ["as_of"])

    # case_id: workbook uses Receipt# in case detail but CASE-id in activities.
    # Build a receipt->case_id map from activities so we can join either way.
    if "receipt" in acts.columns and "case_id" in acts.columns:
        r2c = acts.dropna(subset=["receipt", "case_id"]).drop_duplicates("receipt")
        r2c = dict(zip(r2c["receipt"], r2c["case_id"]))
        cases["case_id"] = cases["receipt"].map(r2c).fillna(cases["receipt"])
    else:
        cases["case_id"] = cases["receipt"]

    # numeric coercions
    for col in ["suspect_product_count", "event_count", "days_to_case_due",
                "days_to_submission_due", "aging_days", "historical_hours",
                "activity_aging_hours", "aging_ratio", "reassignment_count",
                "wb_breach_prob", "wb_risk_score"]:
        if col in cases.columns:
            cases[col] = pd.to_numeric(cases[col], errors="coerce")
    for col in ["sequence", "aging_hours", "historical_median_hours", "aging_ratio",
                "reassignment_count"]:
        if col in acts.columns:
            acts[col] = pd.to_numeric(acts[col], errors="coerce")
    for col in ["available_hours", "planned_hours", "utilization_pct", "wip", "active_cases"]:
        if col in cap.columns:
            cap[col] = pd.to_numeric(cap[col], errors="coerce")
    for col in ["sample_size", "median_hours", "p75_hours", "p90_hours", "sla_target_hours"]:
        if col in bench.columns:
            bench[col] = pd.to_numeric(bench[col], errors="coerce")
    for col in ["active_wip", "breached", "approaching", "avg_aging_hours",
                "historical_median_hours", "aging_ratio"]:
        if col in bott.columns:
            bott[col] = pd.to_numeric(bott[col], errors="coerce")

    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    try:
        cases.to_sql("cases", con, if_exists="replace", index=False)
        acts.to_sql("activities", con, if_exists="replace", index=False)
        asg.to_sql("assignments", con, if_exists="replace", index=False)
        cap.to_sql("user_capacity", con, if_exists="replace", index=False)
        bench.to_sql("benchmarks", con, if_exists="replace", index=False)
        bott.to_sql("bottlenecks_wb", con, if_exists="replace", index=False)
        pd.DataFrame([{"key": "as_of", "value": AS_OF.isoformat()}]).to_sql(
            "meta", con, if_exists="replace", index=False
        )
        con.commit()
    finally:
        con.close()
    return db_path


if __name__ == "__main__":
    path = build()
    print(f"Ingested real LSMV workbook -> {path}")
    print(f"as-of = {AS_OF.isoformat()}")
