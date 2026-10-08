"""Load an LSMV dataset (CSV) into SQLite with precomputed derived fields.

This is the single plug point for the REAL dataset: point `CSV_DIR` at the real
extract (same column names) and re-run. Until then it reads the synthetic CSVs
produced by synthesize.py.

Derived fields computed at ingest and stored on the activities table:
  - aging_hours            : hours since the activity started (in-progress)
  - time_in_activity_hours : alias used by the engine for stuck detection
  - reassignment_count     : number of reassignment events for the activity
Plus per-case: days_to_reg_deadline.

Run:  py backend/scripts/build_db.py
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd

from . import config
from .synthesize import AS_OF

CSV_DIR = Path(__file__).resolve().parents[1] / "data"


def _dt(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce")


def _hours_between(later: datetime, earlier: pd.Series) -> pd.Series:
    e = _dt(earlier)
    return (pd.Timestamp(later) - e).dt.total_seconds() / 3600.0


def build(csv_dir: Path | None = None, db_path: str | None = None) -> str:
    csv_dir = Path(csv_dir or CSV_DIR)
    db_path = db_path or config.DB_PATH

    cases = pd.read_csv(csv_dir / "cases.csv")
    activities = pd.read_csv(csv_dir / "activities.csv")
    reassignments = pd.read_csv(csv_dir / "reassignments.csv")
    users = pd.read_csv(csv_dir / "users.csv")
    benchmarks = pd.read_csv(csv_dir / "benchmarks.csv")

    # --- derived: reassignment counts per activity -----------------------
    if len(reassignments):
        rc = reassignments.groupby("activity_id").size().rename("reassignment_count")
        activities = activities.merge(rc, on="activity_id", how="left")
    else:
        activities["reassignment_count"] = 0
    activities["reassignment_count"] = (
        activities["reassignment_count"].fillna(0).astype(int)
    )

    # --- derived: aging / time in current activity -----------------------
    # Only meaningful for in-progress activities (started, not ended).
    aging = _hours_between(AS_OF, activities["start_ts"])
    in_progress = activities["activity_status"].eq("in-progress")
    activities["aging_hours"] = aging.where(in_progress).round(2)
    activities["time_in_activity_hours"] = activities["aging_hours"]

    # --- derived: days to regulatory deadline per case -------------------
    cases["days_to_reg_deadline"] = (
        _hours_between(AS_OF, cases["reporting_due_date"]) / -24.0
    ).round(3)
    # positive = time remaining; negative handled by engine (overdue)
    cases["days_to_reg_deadline"] = -cases["days_to_reg_deadline"]

    # --- write SQLite -----------------------------------------------------
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    try:
        cases.to_sql("cases", con, if_exists="replace", index=False)
        activities.to_sql("activities", con, if_exists="replace", index=False)
        reassignments.to_sql("reassignments", con, if_exists="replace", index=False)
        users.to_sql("users", con, if_exists="replace", index=False)
        benchmarks.to_sql("benchmarks", con, if_exists="replace", index=False)
        # Store the snapshot "now" so the engine and API agree on time.
        meta = pd.DataFrame([{"key": "as_of", "value": AS_OF.isoformat()}])
        meta.to_sql("meta", con, if_exists="replace", index=False)
        con.commit()
    finally:
        con.close()
    return db_path


if __name__ == "__main__":
    path = build()
    print(f"Built SQLite DB at {path}")
