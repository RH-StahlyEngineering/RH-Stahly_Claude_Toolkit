"""bid_unhide.py -- unhide every row and column across every sheet in a workbook.

USAGE
    python bid_unhide.py <workbook.xlsx>

The Stahly bid template ships with several rows and columns hidden by default
(Phase 4/6 task slots, columns N and Q on the bid sheet, etc.). This script
unhides every row and column on every sheet so all bid lines are visible.

On a file-lock, writes a sibling `<stem>_PATCH.xlsx` and emits merge
instructions.
"""
from __future__ import annotations
import argparse
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
from bid_workbook import unhide_all


def main():
    ap = argparse.ArgumentParser(description="Unhide every row and column in a Stahly bid workbook.")
    ap.add_argument("workbook")
    args = ap.parse_args()

    result = unhide_all(args.workbook)

    print(f"Saved to: {result['saved_to']}")
    if result["locked_fallback"]:
        print("NOTE: original file was locked; wrote a _PATCH copy. Close Excel and merge.")
    print(f"Rows unhidden: {result['rows_unhidden']}")
    print(f"Cols unhidden: {result['cols_unhidden']}")
    if result["by_sheet"]:
        print("By sheet:")
        for name, counts in result["by_sheet"].items():
            print(f"  {name}: {counts['rows']} rows, {counts['cols']} cols")
    else:
        print("(nothing was hidden -- workbook already fully visible)")


if __name__ == "__main__":
    main()
