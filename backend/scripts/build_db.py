"""Build the SQLite DB from the REAL shared LSMV workbook (.xlsb).

Run:  py backend/scripts/build_db.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import lsmv  # noqa: E402


def main() -> int:
    path = lsmv.build()
    print(f"Ingested real LSMV workbook -> {path}")
    print(f"as-of = {lsmv.AS_OF.isoformat()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
