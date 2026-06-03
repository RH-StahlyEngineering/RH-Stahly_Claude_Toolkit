"""bootstrap_project.py — create a new Stahly project folder and prefill a bid workbook.

Resolves the master bid template via the canonical resolver, picks the next
NNN- number in the office's proposal folder root, creates the project folder,
SaveAs's the template to that folder as `NNN_<slug>_Bid.xlsx`, and writes the
project header cells (Client, Project Name, Date, Prepared By, Checked By,
phase names if supplied).

This replaces the manual sequence of:
  1. Browse network share, figure out next number
  2. Right-click → New → folder
  3. Copy/paste template
  4. Open in Excel, Save As, change extension to .xlsx
  5. Type in the header cells

USAGE
    python bootstrap_project.py \\
        --client "Aethel" \\
        --project-name "Wamsutter Tank Settlement Monitoring" \\
        --office great_falls \\
        --prepared-by "Harbach, Ryan" \\
        --checked-by "Kosine, Chris" \\
        --discipline survey_monitoring

Optional:
    --phase-names "Project Setup|Round 1 Baseline|Round 2 Q. Monitoring|..."
                       (pipe-separated, up to 12 — gets written to B8, B20, B32, ...)
    --per-diem-rate 58
    --mileage-rate 0.75
    --dry-run          Show what would happen without creating anything

Output: prints the project folder path and the bid workbook path on stdout.
Exits non-zero with a clear error if resources can't be resolved.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import re
import shutil
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

# scripts/ is on sys.path when invoked directly
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from lib.canonical import resolve, CanonicalResourceNotFound  # type: ignore
import bid_workbook as bw  # type: ignore


OFFICES = {
    "billings": "proposal_folder_root_billings",
    "bozeman": "proposal_folder_root_bozeman",
    "cody": "proposal_folder_root_cody",
    "great_falls": "proposal_folder_root_great_falls",
    "helena": "proposal_folder_root_helena",
}


def _slug(s: str) -> str:
    """Filename-safe slug: alphanumerics + underscore, collapse runs."""
    s = s.strip()
    s = re.sub(r"[^A-Za-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s)
    return s.strip("_")


def _next_number(office_root: Path) -> int:
    """Find next free NNN- folder number in the office root."""
    used = set()
    for child in office_root.iterdir():
        m = re.match(r"^(\d{3})[-_]", child.name)
        if m:
            used.add(int(m.group(1)))
    n = 1
    while n in used:
        n += 1
    return n


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Bootstrap a Stahly project folder + bid workbook.")
    parser.add_argument("--client", required=True)
    parser.add_argument("--project-name", required=True)
    parser.add_argument("--office", required=True, choices=sorted(OFFICES.keys()))
    parser.add_argument("--prepared-by", default=None,
                        help="Drop-down value from Employee List. Optional — leave to fill in Excel.")
    parser.add_argument("--checked-by", default=None,
                        help="Drop-down value from Employee List. Optional.")
    parser.add_argument("--phase-names", default=None,
                        help="Pipe-separated phase names, up to 12, written to B8/B20/.../B140")
    parser.add_argument("--per-diem-rate", type=float, default=None,
                        help="Override V7 (template default is per the resolved Rate Sheet)")
    parser.add_argument("--mileage-rate", type=float, default=None,
                        help="Override T7 (template default 0.75)")
    parser.add_argument("--date", default=None, help="YYYY-MM-DD; defaults to today")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    # Resolve canonical resources
    try:
        template = resolve("bid_template")
        office_root = resolve(OFFICES[args.office])
    except CanonicalResourceNotFound as e:
        print(str(e), file=sys.stderr)
        return 2

    # Pick next number
    if not office_root.exists():
        print(f"Office folder does not exist: {office_root}", file=sys.stderr)
        return 2
    n = _next_number(office_root)
    nnn = f"{n:03d}"

    # Build slug + folder name
    client_slug = _slug(args.client)
    project_slug = _slug(args.project_name)
    folder_name = f"{nnn}-{client_slug}_{project_slug}"
    project_dir = office_root / folder_name
    bid_path = project_dir / f"{nnn}_{client_slug}_{project_slug}_Bid.xlsx"

    print(f"Template:    {template}")
    print(f"Office root: {office_root}")
    print(f"Next number: {nnn}")
    print(f"Project dir: {project_dir}")
    print(f"Bid path:    {bid_path}")

    if args.dry_run:
        print("\n(dry-run — no files created)")
        return 0

    # Create folder + true SaveAs from .xltx → .xlsx via Excel COM
    project_dir.mkdir(parents=True, exist_ok=False)
    _save_as_xlsx(template, bid_path)

    # Build initial write list
    when = _dt.date.today() if not args.date else _dt.date.fromisoformat(args.date)
    changes: list[dict] = [
        {"row": 1, "col": "F", "value": args.client},
        {"row": 2, "col": "F", "value": args.project_name},
        {"row": 4, "col": "C", "value": _dt.datetime(when.year, when.month, when.day)},
    ]
    if args.prepared_by:
        changes.append({"row": 3, "col": "C", "value": args.prepared_by})
    if args.checked_by:
        changes.append({"row": 3, "col": "E", "value": args.checked_by})
    if args.per_diem_rate is not None:
        changes.append({"row": 7, "col": "V", "value": args.per_diem_rate})
    if args.mileage_rate is not None:
        changes.append({"row": 7, "col": "T", "value": args.mileage_rate})
    if args.phase_names:
        names = [n.strip() for n in args.phase_names.split("|") if n.strip()]
        phase_header_rows = [hdr for hdr, *_ in bw.PHASES]
        for name, hdr_row in zip(names, phase_header_rows):
            # Trailing space → concatenation with "Total" reads cleanly
            changes.append({"row": hdr_row, "col": "B", "value": name + " "})

    # Apply
    result = bw.apply_changes(bid_path, changes)
    print(f"\nApplied {result['count']} initial writes.")

    # Final report
    print(f"\nProject scaffold ready:")
    print(f"  folder:   {project_dir}")
    print(f"  workbook: {bid_path}")
    return 0


def _save_as_xlsx(template_xltx: Path, dest_xlsx: Path) -> None:
    """True Excel SaveAs from .xltx → .xlsx (xlOpenXMLWorkbook = 51).

    Working-copy pattern: open the template from a local copy to avoid the
    UNC-path quirks Python COM hits on rare network configurations. The
    destination, however, is written directly via Excel's SaveAs.
    """
    try:
        import win32com.client as win32  # type: ignore
        import pythoncom  # type: ignore
    except ImportError as e:
        raise RuntimeError(
            "bootstrap_project requires pywin32. Install with: pip install pywin32"
        ) from e

    import tempfile
    tmp_dir = Path(tempfile.mkdtemp(prefix="stahly_bootstrap_"))
    local_template = tmp_dir / template_xltx.name
    shutil.copy2(template_xltx, local_template)

    pythoncom.CoInitialize()
    app = win32.Dispatch("Excel.Application")
    app.Visible = False
    app.DisplayAlerts = False
    try:
        wb = app.Workbooks.Open(str(local_template))
        # xlOpenXMLWorkbook = 51
        wb.SaveAs(str(dest_xlsx), 51)
        wb.Close(SaveChanges=False)
    finally:
        try:
            app.Quit()
        except Exception:
            pass
        pythoncom.CoUninitialize()
        try:
            shutil.rmtree(tmp_dir)
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
