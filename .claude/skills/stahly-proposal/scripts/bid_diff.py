"""bid_diff.py -- diff a Stahly bid workbook against a snapshot JSON.

USAGE
    # 1. Snapshot the current state
    python bid_audit.py work.xlsx --json > snapshot.json

    # 2. Edit the workbook (or run bid_apply.py)

    # 3. Compare current vs snapshot
    python bid_diff.py work.xlsx snapshot.json [--alert-pct 5]

Reports per-total deltas (labor, expenses, grand, rounded_1k) and fires an
alert if any total moved by more than --alert-pct percent.
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

# Force UTF-8 on Windows so non-ASCII status glyphs (✗ ✓ ⚠ → — etc.) don't
# crash with UnicodeEncodeError on cp1252 consoles.
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        import codecs
        sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, "strict")
        sys.stderr = codecs.getwriter("utf-8")(sys.stderr.buffer, "strict")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bid_workbook import diff_totals


def main():
    ap = argparse.ArgumentParser(description="Diff a Stahly bid workbook against a snapshot JSON.")
    ap.add_argument("workbook")
    ap.add_argument("snapshot", help="Path to a snapshot JSON (output of `bid_audit.py --json`)")
    ap.add_argument("--alert-pct", type=float, default=5.0, help="Alert when any total moves by more than this percent (default: 5)")
    ap.add_argument("--json", action="store_true", help="Emit result as JSON")
    args = ap.parse_args()

    snap = json.loads(Path(args.snapshot).read_text(encoding="utf-8"))
    # Accept either the full audit JSON or a bare totals dict
    snap_totals = snap.get("totals", snap)

    result = diff_totals(args.workbook, snap_totals, alert_pct=args.alert_pct)

    if args.json:
        print(json.dumps(result, indent=2, default=str))
        return

    print("Total deltas:")
    for key, d in result["deltas"].items():
        sign = "+" if d["delta"] >= 0 else ""
        print(f"  {key:<11}  ${d['prev']:>12,.0f}  ->  ${d['current']:>12,.0f}   ({sign}${d['delta']:,.0f})")
    print(f"  rounded_1k current: ${result['current']['rounded_1k']:,}")
    if result["alerts"]:
        print()
        print("!! ALERTS:")
        for a in result["alerts"]:
            print(f"  - {a}")


if __name__ == "__main__":
    main()
