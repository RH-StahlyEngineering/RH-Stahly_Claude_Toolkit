# stahly-proposal (personal skill)

Build client-ready branded PDF proposals for Stahly Engineering & Associates in 1–2 iterations, with mandatory visual QA and a paired markdown log per PDF.

## Why this exists

A 12-iteration session in May 2026 (Hilger-to-Roy LiDAR) proved that the loop is:
1. Read the official brand guide once, lock it
2. Build with proven layout
3. Verify visually before declaring done

Doing those out of order produces the spiral. This skill encodes them.

## Quick start

```powershell
# 1. Verify the skill is healthy
python ~/.claude/skills/stahly-proposal/scripts/verify_assets.py

# 2. (Optional) Get a content skeleton from an existing docx
python ~/.claude/skills/stahly-proposal/scripts/extract_docx.py path/to/proposal.docx

# 3. Edit the resulting JSON to fill in FIXMEs + correct section types
#    (see references/content_schema.md for the section vocabulary)

# 4. Build the PDF
python ~/.claude/skills/stahly-proposal/scripts/build.py \
    --content path/to/content.json \
    --out path/to/output.pdf \
    --cover-photo path/to/cover.jpg

# 5. Render PNGs for visual QA
python ~/.claude/skills/stahly-proposal/scripts/render_qa.py path/to/output.pdf

# 6. Walk references/qa_checklist.md against the rendered PNGs.
#    Promote each [ ] -> [x] only after looking at the rendered page.
```

Or invoke through Claude Code: `/stahly-proposal` (Claude reads `SKILL.md` and runs the intake).

## Layout

```
~/.claude/skills/stahly-proposal/
├── SKILL.md                                  # Orchestration prompt + intake
├── README.md                                 # This file + changelog
├── references/
│   ├── brand_spec.md                         # Official brand rules (Identity Guide 2025)
│   ├── content_schema.md                     # Section vocabulary
│   ├── bid_workbook_spec.md                  # Locked Stahly bid workbook structure + safety rules
│   ├── signature_prep.md                     # Guide for scanning a signature -> transparent PNG
│   ├── qa_checklist.md                       # MANDATORY visual checklist
│   ├── offices.json                          # 5 offices + signatories
│   └── schemas/
│       ├── lidar_remote_sensing.md           # Production-locked
│       ├── survey_general.md                 # Stub
│       └── civil_design.md                   # Stub
├── scripts/
│   ├── build.py                              # The build engine (CLI: --content, --out, --cover-photo, --workbook)
│   ├── render_qa.py                          # PDF → per-page PNGs
│   ├── verify_assets.py                      # Pre-build sanity checks
│   ├── extract_docx.py                       # docx → JSON skeleton
│   ├── bid_workbook.py                       # Shared library: read / apply / unhide / diff / fee_table_payload
│   ├── bid_audit.py                          # Read-only audit (--summary | --json | --markdown)
│   ├── bid_apply.py                          # Safe single-cell edit (refuses formulas + subtotals + grand totals)
│   ├── bid_unhide.py                         # Unhide every row + column on every sheet
│   ├── bid_diff.py                           # Diff workbook vs prior audit JSON snapshot
│   └── make_signature.py                     # Scan -> transparent-bg PNG (alpha-by-luminance ramp)
├── assets/
│   ├── StahlyLogo_EO_official.png            # Cover hero (4501×4278, transparent)
│   └── StahlyLogo_Artboard1_official.png     # Footer (480×361, transparent)
├── templates/                                # Reserved for layout.json (v1.2)
└── examples/                                 # Fixture proposals (Hilger-to-Roy)
```

## Brand specs (locked)

- **Colors:** Stahly Blue `#00548C` · Stahly Tan `#BABAB1` · Stahly Cream `#E9E6E1`
- **Fonts:** Rockwell Bold (headlines) · Arial Regular (body)
- **Logos:** transparent PNGs in `assets/`
- **Reference:** `\\Stahly\marketing\Branding-Identity\01_Brand Identity Guide\Stahly Engineering Identity Guide 2025.pdf`

## What's in v1.0 vs deferred to v1.1+

**v1.0 (this release):**
- ✅ Cover page (locked layout, flush stacked bands)
- ✅ Body pages with H1/H2/bullets, footer band, "Page N of M"
- ✅ Phase fee table with per-line $100 rounding + code-computed grand total
- ✅ Signature block with office contact lookup from `offices.json`
- ✅ Cover photo with aspect-ratio-aware placement
- ✅ Paired `_log.md` written automatically
- ✅ Visual QA renderer (per-page PNGs)
- ✅ Pre-build sanity checks (`verify_assets.py`)
- ✅ Schema markdown for LiDAR/Remote Sensing (production-tested)
- ✅ Schema stubs for Survey + Civil Design (promote after first real use)

**v1.1 (shipped 2026-05-13):**
- ✅ Workbook fee pull (openpyxl integration — read phase totals from .xlsx directly via `--workbook` flag on `build.py`)
- ✅ Locked bid workbook spec (`references/bid_workbook_spec.md`) + sheet fingerprint (auto-detect even when sheet renamed)
- ✅ Silent-underbid guards: blank-staff-name + hours, zero-rate + hours, fallback-rate sourcing (all three fire in `bid_audit.py`)
- ✅ Cached-value rate resolution (handles both formula and hand-overwritten constant cells in row 7)
- ✅ Read-only audit CLI with `--markdown` mode for email-ready phase tables
- ✅ Safe-write CLI (`bid_apply.py`) — refuses formula overwrites, subtotal rows, grand-total rows
- ✅ Unhide-everything CLI (`bid_unhide.py`)
- ✅ Diff-against-snapshot CLI (`bid_diff.py`)
- ✅ File-lock graceful fallback (writes `<stem>_PATCH.xlsx` and prints merge instructions when Excel has the workbook open)
- ✅ ROUNDUP-to-$1K rule applied at PDF rendering time when workbook source is used (per gotcha #4 — non-negotiable for displayed totals)
- ✅ Workbook lineage recorded in the paired `_log.md`

**v1.2 (planned):**
- 🔲 Bidirectional docx writeback (`apply_docx_writeback.py` — already prototyped on Hilger-to-Roy)
- 🔲 Multi-image body figures + landscape exhibits (cover photo handling exists; body/exhibit needs work)
- 🔲 Self-healing retrospective (SKILL.md describes the protocol; needs the analyze + propose flow wired up)
- 🔲 Subagent second-opinion review after visual QA
- 🔲 Templates/layout.json for designer-tweakable layout numbers
- 🔲 Production-test survey_general + civil_design schemas
- 🔲 Environmental + construction_admin schemas

## Dependencies

System fonts (Windows): Rockwell + Arial — both ship with Office.

Python packages: `reportlab`, `pypdfium2`, `python-docx`, `Pillow`, `pypdf`, `openpyxl` (v1.1)

## Changelog

### v1.2.3 — 2026-05-26 (Aethel retrospective: rate-leakage scanner, data-driven SignatureBlock, ROUNDUP rule split)

Three structural improvements catalyzed by the Aethel Wamsutter Tank Monitoring proposal retro:

- **Rate-leakage scanner in `verify_assets.py`** (blocks build by default). Scans the rendered text content of the proposal JSON for patterns that reveal Stahly's labor rates or hour×rate math: `$<NUM>/hr`, `$<NUM> per hour`, `<NUM> hr × $<NUM>`, `<NUM> hours at $<NUM>`, and bare labor codes (`LPS5`, `LST4`, `EPE6`, and the full prefix list). Each detection produces a specific cell+snippet error. New `--allow-rate-disclosure` flag for the rare intentional case (approved time-and-materials contracts). Catalyst: the first Aethel build exposed `(96 hr × $149/hr)` and labor categories in an Option B comparison table — a real client-confidentiality failure that the verifier should have caught before render.
- **SignatureBlock height becomes data-driven.** Was previously a hardcoded magic number (`1.30"` → `0.85"` → `1.05"` → `1.20"` across iterations) that required hand-tuning every time the proposal got near a page-break boundary. Now: height = SIGNING_ROOM (default 0.50") + below-line space computed from `len(contact_lines)`. Each signatory sizes their own block based on actual contact line count. Caller-overridable `signing_room` parameter for tighter or looser layouts without touching the class. Catalyst: 4 iterations of compress-rebuild-still-orphaned-rebuild on the Aethel signature page — the magic number was a single point of failure.
- **ROUNDUP-to-$1K rule split by display context** in `references/bid_workbook_spec.md`. Old rule said "every grand total displayed by any script must show both the raw number and the rounded number." The user explicitly rejected dual-display in client-facing PDFs (visual noise, invites "which number is real?" questions). New rule: **internal** displays (audit CLI, log files, diffs) keep the dual display because PMs negotiating a bid genuinely benefit from seeing both numbers; **client-facing** displays (proposal PDF, contracts, cover emails) show only the single $100-rounded sum of line items. `build.py` already implemented the new behavior in v1.2.x; the spec doc just caught up.

Catalyst: Aethel Wamsutter Tank Settlement Monitoring proposal sign-off retrospective (2026-05-26). All three findings traced back to specific iterations the user redirected during this build.

### v1.2.2 — 2026-05-22 (Windows stdout encoding)

Every CLI script in `scripts/` now reconfigures `sys.stdout`/`sys.stderr` to UTF-8 on Windows at module load. Fixes `UnicodeEncodeError: 'charmap' codec can't encode character '✗'` (and the same class of failure for ✓, →, ←, —, ¼, and every other non-ASCII character used for status output) on default Windows consoles where Python defaults to cp1252. No more need to manually set `PYTHONIOENCODING=utf-8` before running any skill script.

The fix is one block at the top of each script (right after imports), not per-print escapes — the existing glyphs in `print()` and `sys.stderr.write()` calls are intentional and stay as-is. `verify_assets.py` was the trigger (`✗`/`✓`/`⚠` in result lines), but `build.py`, `bid_audit.py`, `bootstrap_project.py`, and the rest also use em-dashes and arrows in their output, so the reconfig was applied to all 11 CLI scripts (including `scripts/lib/canonical.py`, which is both a library and a CLI).

### v1.2.1 — 2026-05-22 (general-purpose patterns from Aethel intake)

Six generalized findings folded back into the skill so they apply to any future proposal, not just survey monitoring:

- **Pre-warn on cost concentration** (SKILL.md rule 5). Before showing any rolled-up fee total, identify whether one cost driver is >25% of the total and surface it BEFORE the headline number. Skipping this is how a $50K bid surprises a user expecting $27K — the $25K windshield-time concentration was the entire story and should have been called out first.
- **Field-trip sanity check at intake** (SKILL.md rule 6). For any task involving drive to a remote site, compute drive RT + active field time per person. If > ~12 hr, propose overnight + hotel before the user has to ask. Threshold is conservative because field reality eats hours.
- **Tone discipline pointer** (SKILL.md rule 7). Tone rules from `send-outlook-email/SKILL.md` apply to all user-facing output (drafts, tables, summaries, intake recaps), not just emails. Pointer rather than duplicate.
- **Multi-deliverable close-out** (content_schema.md). Default for projects with N repeat-instance deliverables: no separate final summary report; the last instance is the close-out. Avoids ceremonial reports; leaves room for follow-on engagement. Override when client explicitly asks, regulator requires, or value pitch depends on synthesis.
- **Client-choice scope elements** (content_schema.md). When a scope element has 2+ acceptable methods AND the choice depends on client approval that hasn't been confirmed, offer both with "either A or B, at the Client's election." Avoids locking into a method the client will reject. Examples beyond chime drilling: permanent vs. temporary monuments, painted vs. flagged stakes, photo doc vs. notes-only.
- **Pre-proposal billable hours** (bid_workbook_spec.md). Scoping/kickoff hours expended before proposal signing are legitimately billed in the workbook (typically Phase 1) but never enumerated in the proposal narrative. The client sees the phase total; Stahly sees the line-item detail internally.

Catalyst: Aethel Wamsutter intake retrospective (2026-05-22). User pushed back on initial "skill updates" because they were specific to this project. Re-generalized so each rule applies across lidar, survey general, survey monitoring, and civil design proposals.

### v1.2 — 2026-05-22 (canonical resolver + 2026 12-phase template + Excel COM writes)

Triggered by the Aethel Wamsutter Tank Settlement Monitoring intake. Three structural shifts:

**Canonical resolver (new).** Every Stahly artifact path now flows through `scripts/lib/canonical.py` against `references/stahly_canonical_paths.md`. The registry stores filename + content-marker fingerprints alongside the cached path; the resolver verifies cache, falls back to glob `search_hints` on miss, and **writes the new path back** on success. Self-healing path drift. **No silent fallback on hard miss** — raises `CanonicalResourceNotFound` with structured detail so the orchestrator can escalate to the user instead of inventing a default. Resolution log at `references/canonical_resolution_log.md`. Replaces every hardcoded UNC path in code.

**2026 template support.** The 2026 bidding template ships with 12 phases (was 6), grand totals at row 152/153 (was 80/81), staff columns G–Q (was G–K), and per-diem rate $58 (was $54). The skill's bid-workbook layer was hard-coded for the 6-phase layout and was structurally broken for the current year before this release. Fingerprint, `PHASES`, `STAFF_COLS`, grand-total rows, and `FALLBACK_RATES` all updated. Spec doc (`references/bid_workbook_spec.md`) rewritten to match. **Sheet fingerprint is now purely structural** (no row-3 staff-name check), so blank-but-valid workbooks pass.

**Excel COM writes (new write driver).** openpyxl silently strips x14-namespace data validations on save, deleting every drop-down in a Stahly workbook (staff name picker, Rate Sheet selector, etc.). The skill's write helpers (`bid_workbook.apply_change`, `apply_changes`, `unhide_all`) now run through late-binding `win32com.client.Dispatch("Excel.Application")` — preserves drop-downs, formulas, conditional formatting, and merged cells. Late-binding because `gencache.EnsureDispatch` breaks on Stahly's Office typelib (same memory entry covers Outlook). All writes operate on a `%TEMP%` working copy and push back to the network destination on save. Pre-flight `cell.Formula` check refuses any write that would overwrite a formula. `cell.Value = None` used for clears (works on merged cells). `datetime.datetime` enforced for date values. Reads stay on openpyxl (read-only is safe).

**Bootstrap script (new).** `scripts/bootstrap_project.py` resolves the office's proposal folder root, finds the next free NNN-, creates the folder, true-SaveAs's the template to `.xlsx` via COM, and prefills the header cells (client, project, date, prepared-by, checked-by, per-diem rate, mileage rate, phase names). One call instead of six manual steps.

**Survey monitoring schema (new).** `references/schemas/survey_monitoring.md` covers settlement / dam / structure / slope monitoring projects with baked-in defaults: 3-monument stability check, 0.005 ft loop closure, drilled-and-set survey nails, OPUS-Static (2-hr min) datum tie, "data suitable for API 653 Annex B evaluation by others" disclaim phrasing.

**Intake reorder.** Staffing is now asked **before** any hours scaffolding. The hours grid shape (3 staff vs 4 vs 5; PM-and-SOR-same-person vs separate) determines the workbook layout; proposing hours blind has produced a guaranteed rework round.

**Office inference.** When the user identifies the bid workbook destination (or it's already in place), the office is determined by folder location. Skill confirms only if ambiguous instead of asking blind.

**Phase templates (content schema).** `fee_table.phases` now supports a `phase_template` entry expanded at build time — e.g. four quarterly monitoring rounds as one definition with `count: 4`, `start_n: 2`, `phase_template: "Round {n} Quarterly Monitoring"`.

**Verifier extended.** `verify_assets.py` now checks canonical resolution (resolution failures are blocking), bid-workbook fingerprint + silent-underbid warnings (`--workbook` flag), and scope-vs-expense consistency (OPUS/GNSS in scope → expect GPS day rate; UAV in scope → expect UAV fee; long-drive total → expect hotel Other Misc; 2-person field crew → expect ≥ 2 staff with hours).

**Pre-existing template defects documented.** The pristine 2026 template ships with 64 `#N/A` errors on hidden Employee List rows 74–81 (broken VLOOKUPs on empty employee slots). Baseline noise; the verifier ignores them and only flags NEW errors.

**Catalyst:** See the Aethel Wamsutter Tank Settlement Monitoring session retro (2026-05-22) — every change above traces back to a friction point in that intake. Net: ~12 manual steps → ~3.

### v1.1.1 — 2026-05-14 (signature prep folded in)
Absorbed the standalone `signature-transparent-bg` skill. Same alpha-by-luminance ramp logic, now exposed as a proper CLI (`scripts/make_signature.py`) with first-class flags (`--dark`, `--light`, `--blur`, `--autocontrast`, `--force-black`) and a sibling reference doc (`references/signature_prep.md`). The standalone skill was deleted -- one home for the proposal-adjacent prep tools instead of two. Rec. 601 luminance weighting kept (so blue ink isn't mis-weighted), ink color preserved by default, smooth ramp through mid-tones preserves anti-aliased pen edges.

### v1.1 — 2026-05-13 (workbook integration)
Promoted workbook fee pull from "planned" to "preferred when a Stahly bid workbook exists." Build engine now reads phase totals live from .xlsx via `--workbook` flag, eliminating manual transcription drift. Bid workbook structure locked in `references/bid_workbook_spec.md`.

Silent-underbid surface expanded beyond the original blank-staff-name trap. The audit now also fires on (a) zero-rate-with-hours (Rate Sheet lookup failure leaves a populated staff column paying $0/hr) and (b) fallback-rate sourcing (when the hardcoded 2025 rate table is used instead of the live Rate Sheet, so the user can verify the rate hasn't gone stale).

Sheet auto-detected by structural fingerprint, not by name — survives template renames (`ROW-Ph1` → `Lidar_Survey` in the Hilger-to-Roy case). Rate resolution prefers row-7 cell value first (constants and cached formula values), then row-6 rate code → fallback table, then unresolved-with-warning. Per-column rate source surfaced in the audit so the user can see exactly where each $/hr came from.

`apply_change` and `unhide_all` handle file-lock gracefully — writes `<stem>_PATCH.xlsx` and prints merge instructions when Excel has the workbook open. Refuse-write guards on subtotal rows, grand-total rows, and any formula cell so OFFSET-based subtotals and the ROUNDUP-to-$1K F81 formula can't be silently broken.

ROUNDUP-to-$1K rule (gotcha #4 — non-negotiable for displayed totals) applied at PDF rendering time when workbook source is used: if the sum of $100-rounded line items differs from the workbook's ROUNDUP value, the PDF prints both numbers below the fee table, and the per-mile unit rate is computed against the ROUNDUP total.

New CLI surfaces: `bid_audit.py --markdown` (paste phase breakdown into email or status update), `bid_apply.py` (safe single-cell edit), `bid_unhide.py`, `bid_diff.py` (workbook vs prior audit JSON snapshot). All share `scripts/bid_workbook.py` as the library.

### v1.0 — 2026-05-12 (initial release)
Built from Hilger-to-Roy LiDAR proposal (12 iter → 1 finalized). Production-tested against the Hilger-to-Roy content. Brand reconciled against Stahly Engineering Identity Guide 2025, First Edition 3.2025.

Wins baked in: Rockwell + Arial typography, official transparent logos, $100-rounded fee table with code-computed total, two-pass page numbering, mandatory visual QA, paired log file.

Anti-patterns coded against: Cambria body text (off-brand — refused), solid-blue tile behind cover logo (visually wrong — refused), hand-typed grand totals (refused), off-by-one page numbering (regression-tested), gap between address band and tagline band (structurally impossible via flush stacking).

Refused features (escalate to Marketing): color overrides, font swaps, alternate logo files, new page templates.

Deferred to v1.1: workbook pull, docx writeback wiring, retrospective automation, schema promotion for non-LiDAR types.
