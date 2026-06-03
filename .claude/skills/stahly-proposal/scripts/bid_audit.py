"""bid_audit.py -- read the Stahly bid workbook and emit a JSON audit.

USAGE
    python bid_audit.py <workbook.xlsx> [--summary | --json | --markdown] [--no-warnings]

Modes:
    --summary    (default) Human-readable phase summary + totals.
    --json       Full JSON audit dump (matches bid_workbook.read_workbook output).
    --markdown   Phase breakdown as a Markdown table -- paste into emails or status updates.
    --no-warnings  Suppress underbid warnings (don't do this in production).

Read-only. Never modifies the workbook.
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

# Allow running as either `python bid_audit.py …` or `python -m scripts.bid_audit`
sys.path.insert(0, str(Path(__file__).resolve().parent))
from bid_workbook import read_workbook, _roundup_1k


def _fmt_money(x: float) -> str:
    return f"${x:>10,.2f}"


def _print_summary(audit: dict) -> None:
    m = audit["metadata"]
    print(f"Workbook:   {m['workbook_path']}")
    print(f"Sheet:      {m['sheet_name']}")
    print(f"Client:     {m['client']}")
    print(f"Project:    {m['project']}")
    print(f"Date:       {m['date']}")
    print(f"Rate src:   {m['rate_source']}  (per-column shown below)")
    print()
    print("Staff:")
    for col, name in m["staff"].items():
        rate = m["staff_rates"][col]
        src = m["rate_sources"][col]
        src_flag = "" if src == "workbook" else f"  [{src}]"
        print(f"  {col}  {(name or '(blank)'):<25}  ${rate:>7.2f}/hr{src_flag}")
    print(
        f"  Mileage:   ${m['mileage_rate']:.2f}/mi"
        f"  [{m['mileage_rate_source']}]    "
        f"Per diem: ${m['per_diem_rate']:.2f}/day  [{m['per_diem_rate_source']}]"
    )
    print()

    if audit["warnings"]:
        print("!! WARNINGS:")
        for w in audit["warnings"]:
            print(f"   - {w}")
        print()

    # Phase summary
    print(f"{'Phase':<30} {'Hours':>7} {'Labor':>14} {'Expenses':>14} {'Subtotal':>14}")
    print("-" * 81)
    total_hours = 0.0
    for p in audit["phases"]:
        hrs = sum(sum(t["hours"].values()) for t in p["tasks"])
        total_hours += hrs
        print(
            f"{p['name'][:30]:<30} {hrs:>7.1f} {_fmt_money(p['labor_subtotal'])} "
            f"{_fmt_money(p['expense_subtotal'])} {_fmt_money(p['phase_total'])}"
        )
    print("-" * 81)
    t = audit["totals"]
    print(
        f"{'TOTAL':<30} {total_hours:>7.1f} {_fmt_money(t['labor'])} "
        f"{_fmt_money(t['expenses'])} {_fmt_money(t['grand'])}"
    )
    print()
    print(f"GRAND TOTAL (raw):                  ${t['grand']:>14,.2f}")
    print(f"ROUNDED UP TO $1K (per workbook):   ${t['rounded_1k']:>14,.0f}")


def _print_markdown(audit: dict) -> None:
    """Phase breakdown as a Markdown table (paste into an email or status update)."""
    print("| Phase | Hours | Labor | Expenses | Subtotal |")
    print("|---|---:|---:|---:|---:|")
    total_hours = 0.0
    for p in audit["phases"]:
        hrs = sum(sum(t["hours"].values()) for t in p["tasks"])
        total_hours += hrs
        print(
            f"| {p['name']} "
            f"| {hrs:.0f} "
            f"| ${p['labor_subtotal']:,.0f} "
            f"| ${p['expense_subtotal']:,.0f} "
            f"| ${p['phase_total']:,.0f} |"
        )
    t = audit["totals"]
    print(
        f"| **TOTAL** | **{total_hours:.0f}** | **${t['labor']:,.0f}** "
        f"| **${t['expenses']:,.0f}** | **${t['grand']:,.0f}** |"
    )
    print()
    print(f"**Total fee (rounded to nearest $1,000): ${t['rounded_1k']:,}**")
    if audit["warnings"]:
        print()
        print("Warnings:")
        for w in audit["warnings"]:
            print(f"- {w}")


def main():
    ap = argparse.ArgumentParser(description="Read-only audit of a Stahly bid workbook.")
    ap.add_argument("workbook", help="Path to the .xlsx bid workbook")
    grp = ap.add_mutually_exclusive_group()
    grp.add_argument("--summary", action="store_true", help="Print human-readable summary (default)")
    grp.add_argument("--json", action="store_true", help="Print full JSON audit")
    grp.add_argument("--markdown", action="store_true", help="Print phase breakdown as Markdown table")
    ap.add_argument("--no-warnings", action="store_true", help="Suppress underbid warnings")
    args = ap.parse_args()

    audit = read_workbook(args.workbook)

    if args.no_warnings:
        audit["warnings"] = []

    if args.json:
        print(json.dumps(audit, indent=2, default=str))
    elif args.markdown:
        _print_markdown(audit)
    else:
        _print_summary(audit)


if __name__ == "__main__":
    main()
