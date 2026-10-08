"""Dump every sheet of the shared .xlsb sample so we can align to it."""
import sys
from pathlib import Path
import pyxlsb

p = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("..") / "INTELLIGENT WORKFLOW MANAGER.xlsb"
wb = pyxlsb.open_workbook(str(p))
for name in wb.sheets:
    print("\n" + "=" * 90)
    print("SHEET:", name)
    print("=" * 90)
    with wb.get_sheet(name) as sh:
        rows = []
        for row in sh.rows():
            rows.append([c.v for c in row])
        # trim trailing empty rows
        while rows and all(v is None for v in rows[-1]):
            rows.pop()
        for i, r in enumerate(rows):
            vals = ["" if v is None else str(v) for v in r]
            # collapse very wide trailing empties
            while vals and vals[-1] == "":
                vals.pop()
            line = " | ".join(vals)
            print(f"{i:>3}: {line[:400]}")
        if not rows:
            print("(empty)")
