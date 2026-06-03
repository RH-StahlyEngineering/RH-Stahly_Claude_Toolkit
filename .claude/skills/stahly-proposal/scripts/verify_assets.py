"""Pre-build sanity checks. Run before build.py to fail fast on missing assets,
unknown offices/signatories, off-brand constants, etc.

Returns 0 on success, non-zero on failure. Prints findings to stdout.
"""
import argparse, json, re, sys
from datetime import datetime, timedelta
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


def check_brand_constants(skill_dir: Path):
    """Confirm build.py's color/font constants match brand_spec.md."""
    spec = (skill_dir / "references" / "brand_spec.md").read_text(encoding="utf-8")
    build_py = (skill_dir / "scripts" / "build.py").read_text(encoding="utf-8")
    issues = []
    for hex_val, label in [("#00548C", "Stahly Blue"), ("#BABAB1", "Stahly Tan"), ("#E9E6E1", "Stahly Cream")]:
        if hex_val not in spec:
            issues.append(f"{label} hex {hex_val} not in brand_spec.md")
        if hex_val not in build_py:
            issues.append(f"{label} hex {hex_val} not in build.py")
    for font in ("Rockwell", "Arial"):
        if font not in spec:
            issues.append(f"{font} not referenced in brand_spec.md")
        if font not in build_py:
            issues.append(f"{font} not registered in build.py")
    # Cambria is off-brand — must not appear in build.py
    if "Cambria" in build_py:
        issues.append("Cambria appears in build.py — this is off-brand per Identity Guide 2025")
    return issues


def check_assets(skill_dir: Path):
    issues = []
    for name in ("StahlyLogo_EO_official.png", "StahlyLogo_Artboard1_official.png"):
        p = skill_dir / "assets" / name
        if not p.exists():
            issues.append(f"Missing official logo: {p}")
    return issues


def check_offices(skill_dir: Path):
    issues = []
    path = skill_dir / "references" / "offices.json"
    if not path.exists():
        return [f"Missing offices.json: {path}"]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return [f"offices.json parse error: {e}"]
    offices = data.get("offices", {})
    seen_orders = set()
    for name, off in offices.items():
        for k in ("street", "city_state_zip", "phone", "address_band_order", "signatories"):
            if k not in off:
                issues.append(f"Office '{name}' missing field: {k}")
        order = off.get("address_band_order")
        if order in seen_orders:
            issues.append(f"Duplicate address_band_order in offices.json: {order}")
        seen_orders.add(order)
    return issues


def check_content(content_path: Path, skill_dir: Path):
    issues = []
    try:
        c = json.loads(content_path.read_text(encoding="utf-8"))
    except Exception as e:
        return [f"Content JSON parse error: {e}"]
    for k in ("project_name", "client_name", "date", "office", "signatory_name", "re_line", "addressee", "sections"):
        if k not in c:
            issues.append(f"Content missing required field: {k}")
    # Date sanity
    try:
        d = datetime.strptime(c["date"], "%Y-%m-%d").date()
        today = datetime.now().date()
        if d < today - timedelta(days=30):
            issues.append(f"Date {c['date']} is more than 30 days old")
        if d > today + timedelta(days=90):
            issues.append(f"Date {c['date']} is more than 90 days in the future")
    except (KeyError, ValueError):
        issues.append("Date missing or unparseable (need YYYY-MM-DD)")
    # Office + signatory must exist
    try:
        offices = json.loads((skill_dir / "references" / "offices.json").read_text(encoding="utf-8"))["offices"]
        if c["office"] not in offices:
            issues.append(f"Office '{c['office']}' not in offices.json")
        else:
            sigs = [s["name"] for s in offices[c["office"]]["signatories"]]
            if c["signatory_name"] not in sigs:
                issues.append(f"Signatory '{c['signatory_name']}' not in {c['office']} office. Known: {sigs}")
    except Exception:
        pass
    # Sections present
    sections = c.get("sections", [])
    if not sections:
        issues.append("No sections defined in content JSON")
    # Cover photo file existence
    cp = (c.get("cover_photo") or {}).get("path")
    if cp and not Path(cp).exists():
        issues.append(f"Cover photo file not found: {cp}")
    # Required sections present
    types = [s.get("type") for s in sections]
    for required in ("intro", "signature_block"):
        if required not in types:
            issues.append(f"Section type missing: '{required}' (required)")
    # Per-section validation
    for s in sections:
        t = s.get("type")
        if t == "subsection_group" and not s.get("subs"):
            issues.append("subsection_group has no subs")
        if t == "deliverables_list" and not s.get("items"):
            issues.append("deliverables_list has no items")
        if t == "fee_table" and not s.get("phases"):
            issues.append("fee_table has no phases")
        # Readability warning: long subsection bodies as a single paragraph
        # become walls of text that are hard to scan. Flag when a subsection
        # body string exceeds 200 words; recommend splitting into the list-
        # of-paragraphs form. The threshold is editorial, not hard — adjust
        # if Stahly's house style shifts.
        if t == "subsection_group":
            for sub in s.get("subs", []) or []:
                body = sub.get("body")
                if isinstance(body, str):
                    word_count = len(body.split())
                    if word_count > 200:
                        issues.append(
                            f"Subsection '{sub.get('title', '?')}' body is {word_count} words "
                            f"in a single paragraph — readability suffers. Consider splitting "
                            f"into a list of paragraphs (body: [\"para 1\", \"para 2\", ...]) "
                            f"to give the reader natural breakpoints."
                        )
    return issues


def check_rate_leakage(content_path: Path):
    """Scan the rendered text content of the proposal for patterns that
    reveal Stahly's labor rates or hour×rate math. This is a hard block:
    rates must never appear in a client-facing document.

    Patterns detected:
        - "$<NUM>/hr" or "$<NUM> per hour"
        - "<NUM> hr × $<NUM>"  (and "x", "*", "at", "@" variants)
        - Bare labor codes (LPS5, LST4, EPE6, etc. — full prefix list below)
        - "<NUM> hours" or "<NUM> hr" appearing within 60 chars of a "$<NUM>"

    Override: pass ``--allow-rate-disclosure`` to skip this check. Use only
    when the rate disclosure is intentional and client-approved (e.g., a
    time-and-materials contract that legitimately exposes rates).
    """
    issues = []
    try:
        c = json.loads(content_path.read_text(encoding="utf-8"))
    except Exception:
        return []  # parse errors are reported by check_content

    # Collect all rendered string content: section titles, lead-in text,
    # body paragraphs, subsection bodies, bullets, table cells, deliverable
    # bodies. Skip identification metadata (project_name, dates, etc.).
    text_blobs = []

    def collect(obj, key_hint=""):
        if isinstance(obj, str):
            text_blobs.append((key_hint, obj))
        elif isinstance(obj, list):
            for item in obj:
                collect(item, key_hint)
        elif isinstance(obj, dict):
            for k, v in obj.items():
                if k in ("project_name", "client_name", "date", "office",
                         "signatory_name", "re_line", "addressee"):
                    continue  # identification fields, skip
                collect(v, k)

    collect(c.get("sections", []))

    # Compiled patterns
    LABOR_CODE_PREFIXES = (
        "LPS", "LST", "LSI", "EPE", "ESE", "ETD", "ECD",
        "EEI", "EET", "CIN", "PPT", "AAA", "AGW", "AGA",
        "APC", "LFT", "LGI", "LGT", "EEW"
    )
    LABOR_CODE_RE = re.compile(
        r"\b(?:" + "|".join(LABOR_CODE_PREFIXES) + r")\d\b"
    )
    PER_HOUR_RE = re.compile(
        r"\$\s*\d[\d,]*(?:\.\d+)?\s*(?:/\s*hr|/\s*hour| per (?:hr|hour))",
        re.IGNORECASE,
    )
    # "<NUM> hr × $<NUM>" — × * x @ at — covers ASCII and unicode multiplication
    HOUR_RATE_RE = re.compile(
        r"\b\d+(?:\.\d+)?\s*(?:hr|hrs|hour|hours)\s*[×x*@]\s*\$\s*\d[\d,]*(?:\.\d+)?",
        re.IGNORECASE,
    )
    HOUR_AT_DOLLAR_RE = re.compile(
        r"\b\d+(?:\.\d+)?\s*(?:hr|hrs|hour|hours)\s+at\s+\$\s*\d[\d,]*(?:\.\d+)?",
        re.IGNORECASE,
    )

    for key, blob in text_blobs:
        for m in LABOR_CODE_RE.finditer(blob):
            issues.append(
                f"Rate leakage — labor code '{m.group(0)}' visible in client "
                f"text ({key or 'section'}). Labor codes reveal pay grade; "
                f"strip from proposal copy. Snippet: …{blob[max(0,m.start()-30):m.end()+30]}…"
            )
        for m in PER_HOUR_RE.finditer(blob):
            issues.append(
                f"Rate leakage — hourly rate '{m.group(0)}' in client text "
                f"({key or 'section'}). Snippet: …{blob[max(0,m.start()-30):m.end()+30]}…"
            )
        for m in HOUR_RATE_RE.finditer(blob):
            issues.append(
                f"Rate leakage — hour×rate math '{m.group(0)}' in client text "
                f"({key or 'section'}). This lets a reader back-calculate the "
                f"rate. Snippet: …{blob[max(0,m.start()-30):m.end()+30]}…"
            )
        for m in HOUR_AT_DOLLAR_RE.finditer(blob):
            issues.append(
                f"Rate leakage — '{m.group(0)}' in client text ({key or 'section'}). "
                f"Snippet: …{blob[max(0,m.start()-30):m.end()+30]}…"
            )
    return issues


def check_canonicals(skill_dir: Path):
    """Resolve every canonical resource and report which are reachable.
    Resolution failures are blocking — surface them so the user can either
    update the registry or escalate to IT."""
    issues = []
    try:
        sys.path.insert(0, str(skill_dir / "scripts"))
        from lib.canonical import resolve_all, CanonicalResourceNotFound  # type: ignore
    except ImportError as e:
        return [f"Cannot import canonical resolver: {e}"]
    try:
        resolve_all()
    except CanonicalResourceNotFound as e:
        issues.append(
            f"Canonical resolution failed for '{e.resource_id}'. "
            f"Update references/stahly_canonical_paths.md or ask the user "
            f"where the resource moved. Details:\n{e}"
        )
    except Exception as e:
        issues.append(f"Canonical resolver crashed: {e}")
    return issues


def check_bid_workbook(workbook_path: Path | None, skill_dir: Path):
    """Sanity-check a bid workbook against scope hints.

    - Confirms the file fingerprints as a Stahly bid workbook.
    - Reports silent-underbid traps from bid_workbook._underbid_warnings.
    - Flags NEW formula errors (the pristine template has 64 baseline errors
      on hidden Employee List rows 74-81; only NEW ones are alerts).
    """
    if workbook_path is None or not workbook_path.exists():
        return []
    issues = []
    sys.path.insert(0, str(skill_dir / "scripts"))
    try:
        import bid_workbook as bw  # type: ignore
    except ImportError as e:
        return [f"Cannot import bid_workbook: {e}"]
    try:
        result = bw.read_workbook(str(workbook_path))
    except ValueError as e:
        return [f"Bid workbook fingerprint check failed: {e}"]
    for w in result.get("warnings", []):
        issues.append(f"Bid workbook warning: {w}")
    return issues


def check_scope_vs_expenses(content: dict, workbook_path: Path | None, skill_dir: Path):
    """Scope-language → expense-line consistency.

    - SOW mentions OPUS / GNSS / RTK → expect GPS day rate on a task row
    - SOW mentions lidar / scanner / scan → expect scanner day rate
    - SOW mentions UAV / drone → expect UAV fee
    - Any trip with > 6-hour one-way drive → expect hotel-budgeted Other Misc
    - Crew described as 2-person + level loop → expect ≥ 2 staff columns with hours

    Each rule warns rather than blocks — the user may have a reason."""
    if workbook_path is None or not workbook_path.exists():
        return []
    issues = []
    sys.path.insert(0, str(skill_dir / "scripts"))
    try:
        import bid_workbook as bw  # type: ignore
        result = bw.read_workbook(str(workbook_path))
    except Exception:
        return []

    # Gather scope text from the content JSON
    scope_text = json.dumps(content, default=str).lower()

    # Aggregate workbook expense fields
    total_uav_fee = sum(
        t["expense_detail"]["uav_fee"]
        for p in result["phases"]
        for t in p["tasks"]
    )
    total_miles = sum(
        t["expense_detail"]["mileage_miles"]
        for p in result["phases"]
        for t in p["tasks"]
    )
    has_other_misc = any(
        t["expense_detail"]["other"] > 0
        for p in result["phases"]
        for t in p["tasks"]
    )

    if any(k in scope_text for k in ("opus", "gnss", "rtk", "static observation")):
        if total_uav_fee == 0:
            issues.append(
                "Scope mentions OPUS / GNSS / RTK but no GPS equipment day "
                "rate appears in column W of any task row. Add a $225/day GPS "
                "Per Unit line if applicable (see Rate Sheet)."
            )

    if any(k in scope_text for k in ("uav", "drone", "uas")):
        if total_uav_fee == 0:
            issues.append(
                "Scope mentions UAV / drone but no UAV/equipment fee in any "
                "task row's W column."
            )

    if any(k in scope_text for k in ("lidar", "scanner", "scan ")):
        if total_uav_fee == 0:
            issues.append(
                "Scope mentions lidar / scanner but no scanner day rate in "
                "any task row's W column (default rate $500/day)."
            )

    # Drive-distance heuristic: > 800 mi RT suggests a hotel night
    if total_miles > 800 and not has_other_misc:
        issues.append(
            f"Total round-trip mileage is {total_miles:g} mi (suggests "
            f"multi-trip work or a long single-trip). No Other Misc expense "
            f"present — confirm whether a hotel night or per-trip lodging "
            f"should be budgeted."
        )

    # 2-person crew sanity: if scope mentions "two-person" / "level loop",
    # expect at least 2 staff cols with hours on field-phase rows.
    if any(k in scope_text for k in ("two-person", "2-person", "level loop", "differential level")):
        staff_with_hours = sum(
            1 for c, hrs in result["metadata"]["staff"].items()
            if hrs and any(t["hours"].get(c, 0) > 0 for p in result["phases"] for t in p["tasks"])
        )
        if staff_with_hours < 2:
            issues.append(
                "Scope describes a 2-person field crew (level loop / "
                "differential leveling), but fewer than 2 staff columns "
                "have hours assigned. Verify field hours are split correctly."
            )

    return issues


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skill-dir", default=str(Path(__file__).resolve().parent.parent))
    ap.add_argument("--content", default=None, help="Optional content JSON to validate.")
    ap.add_argument("--workbook", default=None,
                    help="Optional bid workbook xlsx to sanity-check + cross-validate against scope.")
    ap.add_argument("--allow-rate-disclosure", action="store_true",
                    help="Skip the rate-leakage scanner. Use only when client-facing rate disclosure "
                         "is intentional (e.g., approved time-and-materials contracts).")
    args = ap.parse_args()
    skill = Path(args.skill_dir)

    print("== Canonical resources ==")
    canon_issues = check_canonicals(skill)
    for i in canon_issues: print(f"  ✗ {i}")

    print("== Brand constants ==")
    for i in check_brand_constants(skill): print(f"  ✗ {i}")

    print("== Assets ==")
    for i in check_assets(skill): print(f"  ✗ {i}")

    print("== Offices ==")
    for i in check_offices(skill): print(f"  ✗ {i}")

    issues_all = canon_issues + check_brand_constants(skill) + check_assets(skill) + check_offices(skill)

    if args.content:
        print("== Content ==")
        c_issues = check_content(Path(args.content), skill)
        for i in c_issues: print(f"  ✗ {i}")
        issues_all += c_issues

        if args.allow_rate_disclosure:
            print("== Rate leakage scan ==")
            print("  (skipped — --allow-rate-disclosure set)")
        else:
            print("== Rate leakage scan ==")
            rate_issues = check_rate_leakage(Path(args.content))
            for i in rate_issues: print(f"  ✗ {i}")
            issues_all += rate_issues

    workbook_path = Path(args.workbook) if args.workbook else None
    if workbook_path:
        print("== Bid workbook ==")
        wb_issues = check_bid_workbook(workbook_path, skill)
        for i in wb_issues: print(f"  ⚠ {i}")
        issues_all += wb_issues

        if args.content and Path(args.content).exists():
            print("== Scope-vs-expenses consistency ==")
            content = json.loads(Path(args.content).read_text(encoding="utf-8"))
            sc_issues = check_scope_vs_expenses(content, workbook_path, skill)
            for i in sc_issues: print(f"  ⚠ {i}")
            issues_all += sc_issues

    if issues_all:
        print(f"\n{len(issues_all)} issue(s). Fix before building.")
        sys.exit(1)
    print("\nAll checks pass.")
    sys.exit(0)


if __name__ == "__main__":
    main()
