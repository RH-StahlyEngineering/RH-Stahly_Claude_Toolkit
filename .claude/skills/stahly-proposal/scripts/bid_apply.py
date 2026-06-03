"""bid_apply.py -- write a single cell value into the Stahly bid workbook.

USAGE
    python bid_apply.py <workbook.xlsx> <row> <col_letter> <value>

Examples:
    python bid_apply.py work.xlsx 63 J 30        # set J63 to 30 hours
    python bid_apply.py work.xlsx 33 W 9900      # set UAV equipment fee
    python bid_apply.py work.xlsx 22 G 0         # clear hours

Refuses to overwrite formula cells, subtotal rows, and grand-total rows.
On a file-lock (Excel has the file open), writes a sibling `<stem>_PATCH.xlsx`
and emits merge instructions.

Read this and the locked spec before scripting bulk edits:
  references/bid_workbook_spec.md
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
from bid_workbook import apply_change, read_workbook


def _coerce(raw: str):
    """argparse hands us strings; coerce to int/float when the literal parses."""
    s = raw.strip()
    if s.lower() in ("none", "null", ""):
        return None
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        pass
    return s  # leave as string (won't be a formula because we strip "=" entry)


def main():
    ap = argparse.ArgumentParser(description="Write a single cell in a Stahly bid workbook.")
    ap.add_argument("workbook")
    ap.add_argument("row", type=int, help="1-based row number (task rows only: 9-18, 21-30, 33-42, 45-54, 57-66, 69-78)")
    ap.add_argument("col", help="Column letter (e.g., G, H, I, J, K, S, T, U, V, W, X, Y)")
    ap.add_argument("value", help="New value (number or string; pass 'none' to clear)")
    ap.add_argument("--json", action="store_true", help="Emit result as JSON")
    ap.add_argument("--show-diff", action="store_true", help="After write, print before/after totals")
    args = ap.parse_args()

    new_val = _coerce(args.value)
    if isinstance(new_val, str) and new_val.startswith("="):
        print("Refusing to write a formula via this script. Use Excel directly for formulas.", file=sys.stderr)
        sys.exit(2)

    before_totals = read_workbook(args.workbook)["totals"] if args.show_diff else None

    try:
        result = apply_change(args.workbook, args.row, args.col, new_val)
    except ValueError as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        sys.exit(2)

    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        print(f"OK: {result['sheet']}!{result['cell']}  {result['before']!r} -> {result['after']!r}")
        if result["locked_fallback"]:
            print(f"NOTE: original file was locked. Patched copy at:")
            print(f"      {result['saved_to']}")
            print("      Close Excel and merge or rename the patched file over the original.")
        else:
            print(f"      saved to {result['saved_to']}")

    if args.show_diff:
        after_totals = read_workbook(result["saved_to"])["totals"]
        print()
        print("Totals before -> after:")
        for k in ("labor", "expenses", "grand", "rounded_1k"):
            b = before_totals[k]
            a = after_totals[k]
            d = a - b
            sign = "+" if d >= 0 else ""
            print(f"  {k:<11}  ${b:>12,.2f}  ->  ${a:>12,.2f}   ({sign}${d:,.2f})")


if __name__ == "__main__":
    main()
