---
name: stahly-proposal
description: Build a client-ready branded PDF proposal for Stahly Engineering & Associates. Gathers project details through a structured intake, generates a brand-compliant PDF (official 2025 Identity Guide), and validates the output against a visual QA checklist. Triggers on "build a Stahly proposal", "write a proposal for [client]", "make the [project] proposal PDF", "stahly proposal", or when the user has a docx proposal that needs to be turned into a branded PDF.
---

# Stahly Proposal — Skill orchestration

You are building a branded PDF proposal for **Stahly Engineering & Associates**. The skill's job is to get to client-ready output in **one or two iterations**, not twelve.

There are four gates: **Canonicals → Intake → Build → QA**. Do not skip any. Do not declare the proposal complete until the visual QA checklist is walked through against a rendered PDF.

The skill ships with all the rules of engagement loaded:
- `references/stahly_canonical_paths.md` — fingerprint-based registry of every Stahly artifact path (bid template, instructions docx, rate sheet PDFs, per-office proposal folders)
- `references/brand_spec.md` — locked colors, fonts, logo usage, layout
- `references/content_schema.md` — locked section vocabulary
- `references/schemas/<type>.md` — proposal-type-specific vocabulary (`lidar_remote_sensing`, `survey_general`, `survey_monitoring`, `civil_design`)
- `references/qa_checklist.md` — the mandatory visual checklist
- `references/pre_send_checklist.md` — final content QA on top of visual QA (cover-your-ass items)
- `references/offices.json` — office directory + signatories (with `signing_limit` per signatory)
- `references/bid_workbook_spec.md` — locked Stahly bid workbook structure + safety rules (2026 12-phase template)
- `references/signature_prep.md` — guide for converting a scanned signature to a transparent PNG
- `references/contract_fill_spec.md` — content JSON shape + visual gotchas + QA checklist for contract assembly
- `references/clauses/scope_removal_clause.md` — asymmetric scope-removal clause pattern for T&M NTE proposals
- `references/clauses/third_party_preconditions.md` — Schedule + Assumptions pattern when third-party deliverables gate fieldwork
- `scripts/lib/canonical.py` — fingerprint-based resource resolver with self-healing path updates and hard-fail escalation on miss
- `scripts/bootstrap_project.py` — create a new Stahly project folder + bid workbook in one call (auto-detects next NNN- number, SaveAs template, prefill header cells)
- `scripts/build.py` — the build engine (CLI: `--content`, `--out`, `--cover-photo`, `--workbook`, `--writeback-docx`)
- `scripts/render_qa.py` — render PDF → per-page PNGs
- `scripts/verify_assets.py` — pre-build sanity checks
- `scripts/extract_docx.py` — best-effort docx → JSON skeleton
- `scripts/bid_workbook.py` — shared library: fingerprint detection, read, COM-safe writes (apply/batch/unhide), diff, fee-table-payload. **Writes go through Excel COM** because openpyxl strips x14 data validations (drop-downs).
- `scripts/bid_audit.py` — read-only audit (CLI: `--summary` / `--json` / `--markdown`)
- `scripts/bid_apply.py` — safe single-cell edit (refuses formulas, subtotals, grand-total rows)
- `scripts/bid_unhide.py` — unhide every row and column in every sheet
- `scripts/bid_diff.py` — diff workbook vs prior audit JSON snapshot
- `scripts/make_signature.py` — convert a scanned ink signature to a transparent PNG (alpha-by-luminance ramp; ink color preserved by default)
- `scripts/fill_contract.py` — fill a Stahly contract template + staple a proposal PDF behind it (CLI: `--content`, `--proposal`, `--template`, `--out`, `--no-staple`)
- `assets/StahlyLogo_*.png` — official transparent logos

## Top-of-session rules (apply to every gate)

1. **No silent fallback on missing resources.** If `canonical.resolve()`
   raises `CanonicalResourceNotFound`, surface the structured error to the
   user verbatim and ask where to look. Never invent a default path, never
   skip a dependent step, never assume.
2. **Use Excel COM for any write to a Stahly xlsx workbook.** openpyxl
   silently strips the x14-namespace data validations that power every
   drop-down in the bid template. The `bid_workbook.py` write helpers
   already use COM; use them rather than reaching for openpyxl.
3. **Work on local copies for network files.** Edit in `%TEMP%`, push back
   to the network destination on save. Python COM + UNC paths is fragile.
4. **Read Stahly's own canonical artifacts before guessing.** The bid
   template, instructions docx, rate sheets, and Employee List are
   resolvable via the canonical resolver. If you find yourself proposing
   defaults that the user immediately corrects, you skipped a read.
5. **Pre-warn on cost concentration before showing a total.** Before
   surfacing any rolled-up fee figure to the user, inspect the breakdown.
   If a single category (drive time, mobilization, equipment day rates,
   subconsultants, a single phase) is >25% of the rolled-up total, name
   the category and the math BEFORE the total. The user needs the chance
   to react to the cost driver before the headline number sets an
   expectation. Skipping this is how a $50K bid surprises a user expecting
   $27K — the $25K windshield-time concentration was the entire story.
6. **Field-trip sanity check at intake.** For any task that involves
   driving to a remote site, compute `drive_RT_hours + active_field_hours`
   per person. If the result exceeds ~12 hours, propose an overnight
   (with hotel + per diem days adjusted) before the user has to ask.
   Don't propose impossible single-day trips that depend on every minute
   going right. The threshold is conservative because field reality
   (weather, escort delays, gate access, instrument issues) eats hours.
7. **Tone discipline applies to all user-facing output**, not just emails.
   The canonical tone rules live in `~/.claude/skills/send-outlook-email/
   SKILL.md` (Tone discipline section). Apply them to every artifact the
   user sees — drafts, tables, summaries, intake recaps, retros. The
   rules: first names for internal staff, no time-of-day closers, no
   editorializing inside bullets, no drama bolding in prose, at most one
   em-dash aside, no section dividers in short outputs.
8. **Never leak internal logistics into the client-facing proposal.** The
   proposal is what Stahly is selling and committing to. Anything that
   describes how the sausage gets made stays in internal docs (paired log,
   methodology, bid workbook, scoping timeline). Specifically never put
   any of the following into the proposal PDF:
   - **Equipment procurement details.** Don't say "subject to receipt of
     the LiDAR sensor", "ordered upon execution", "three-week lead time",
     or anything else that implies Stahly doesn't already have the gear.
     The client expects you to be equipped.
   - **Soft commitments / hedge language.** "Best effort", "good faith",
     "weather and tooling cooperate", "tooling permitting" all read as
     pre-emptive excuses. Use plain commitments ("weather permitting" is
     fine; "tooling permitting" is not — the tools are Stahly's problem).
   - **Margin math, internal trade-offs, signing-authority thresholds.**
     "$4K margin absorbed to fit Aaron's signing authority" is internal
     reasoning, not client information.
   - **Back-references to prior project communications** like "per HDR's
     confirmation", "as discussed on the April 23 call", "revised
     proposal", "October 2025 proposal", etc. The proposal stands alone;
     state the scope and let it speak for itself. The client knows what
     they asked for.
   - **Internal staff turnover, tool changes mid-project, or anything
     else that implies execution risk** beyond the named assumptions and
     deliverables. Risks go in the Assumptions section, framed neutrally
     as facts about the world, not internal concerns.
   Treat this as a final pass before declaring the PDF done: read the
   client-facing language as if you were the client. Would any sentence
   make you wonder if Stahly was actually ready to do this work? If yes,
   strip it.
9. **Semantically-paired elements never split across pages.** Some
   visual elements only make sense together; if a page break drops one
   on a different page from the other, the proposal looks unprofessional
   and may even mislead. Wrap these pairs in `KeepTogether` proactively:
   - **Fee table + its caption / unit-rate footer** — the caption explains
     the table; orphaning it is confusing. (Already enforced in build.py
     for the `fee_table` section type.)
   - **Heading + first paragraph** — an H1 alone at page bottom is an
     orphan. (Already enforced for H1WithRule.)
   - **Signature block** — `Sincerely,` + firm name + image + line + name
     + title + contact lines all stay together. Never let any of these
     orphan. (Already enforced via SignatureBlock flowable height.)
   - **Bullet-list lead text + first 1-2 bullets** — the lead introduces
     the list; an isolated lead at page bottom reads as a hanging
     statement.
   - **Tables generally with their immediately-following explanation
     paragraph** — same logic as fee_table.
   You should be applying this rule proactively when adding new section
   types. The general principle: anything you'd read as "this group is
   one thought" must render as one visual unit.

## Step 0 — Canonicals (runs once at session start)

Before the first user question, resolve every canonical resource the skill
needs. Use `python -m scripts.lib.canonical --all` (or call `resolve_all()`
from Python). This:

- Confirms the bid template, instructions docx, rate sheet PDFs, and
  per-office proposal folders all exist and fingerprint-match their cached
  paths.
- Self-heals the registry if anything moved (the resolver searches
  `search_hints` and writes the new path back to
  `references/stahly_canonical_paths.md`, plus a log line in
  `references/canonical_resolution_log.md`).
- Hard-fails to the user if anything cannot be found at all (no silent
  fallback).

If a year just rolled over (e.g. template filename now reads `2027`), the
resolver auto-migrates. **Flag the year change to the user** — they may
want to re-verify labor rates in `bid_workbook.py`'s FALLBACK_RATES too.

If a resource is intentionally not used in this session (e.g. you're
building a proposal that has no bid workbook), it's OK to skip the resolve
for that specific ID — but never *because* you couldn't find it.

## Step 1 — Intake

Ask the questions below **in order**. Don't bundle. If the user has already given some answers inline (e.g. they said "build the Hilger-to-Roy proposal" and a docx is already in the project folder), skip those and ask only the missing ones.

Track answers as you go. When you have them all, **summarize the intake back and wait for explicit "build it" confirmation** before doing anything else.

### Identification
1. **Project title** — single line ≤ 35 chars, or pre-broken with `\n` to force a 2-line cover title. (e.g. `"Hilger Substation to\nRoy Substation"`)
2. **Project subtitle** — italic line under title. (e.g. `"LiDAR Survey – Approximately 28.1 Miles"`)
3. **Client name** — appears on cover + page-2 addressee.
4. **Addressee** — name, organization, street, city/state/zip (4 fields).
5. **RE line** — one sentence summarizing project + scope, appears on page 2.
6. **Date** — defaults to today (`YYYY-MM-DD`). Confirm.

### Office + signatory
7. **Office** — Bozeman / Billings / Helena / Great Falls / Cody. Skill looks up address, phone, and signatories from `references/offices.json`.
   - **Infer when possible.** If the project folder under
     `\\Stahly\marketing\Scope-Schedule-Budget\...\<Year>\<Office>\` is
     already known (because the user said where to save the bid workbook,
     or because the bid workbook lives there), the office is determined.
     Confirm with the user only if ambiguous (e.g. a Billings PM running a
     Great Falls project).
8. **Signatory** — pick from the office's signatory list. Skill auto-fills title and contact lines.
   - Each signatory has a `signing_limit` in offices.json (e.g. Office
     Manager: $80K; CFO: unlimited). `build.py` warns at the end of every
     build when the displayed grand total exceeds the chosen signatory's
     limit — this prevents the "we built the PDF then noticed the office
     manager couldn't actually sign it" cycle. When the warning fires,
     either reduce the fee total to within the limit, or change the
     signatory to someone with sufficient authority.

### Proposal type + content
9. **Proposal type** — what type of work? Loads the matching schema:
   - `lidar_remote_sensing` (production-locked)
   - `survey_general` (stub — boundary, ROW, topo, ALTA, utility)
   - `survey_monitoring` (stub — settlement / dam / structure / slope, repeat geodetic observation)
   - `civil_design` (stub — preliminary design, CDs, bidding, construction admin)
   - Other → ask the user to describe it, then propose a hybrid using the closest schema as a base.
10. **Content source** —
    - Path to a v3-style docx (run `scripts/extract_docx.py` to get a starting skeleton, then fill in section types per `references/content_schema.md`)
    - OR sections inline (ask for each section the schema requires)
    - OR mix (ask which sections come from docx, which are new)

### Staffing — ASK BEFORE PROPOSING ANY HOURS

11. **Who's on this project?** Resolve the Employee List from the
    canonical bid template (or the in-progress bid workbook if it exists)
    so you can present real names, not placeholders. Ask in roles, not
    columns:
    - **Project Manager** (the one who'll bill the project + sign off
      internally — may also be the SOR/EOR)
    - **Surveyor of Record / Engineer of Record** (the licensed
      professional sealing deliverables — may be the same person as PM)
    - **Field crew** (field tech(s) accompanying the SOR/EOR on site)
    - **Office deliverables drafter** (the person doing CAD / data
      reduction / report drafting; may also be a junior of the SOR)
    - **Prepared By** (fills the bid workbook C3 cell; convention is "the
      person assembling this bid" which often = PM)
    - **Checked By** (fills E3; QA/QC reviewer per Stahly contract-signing
      authority policy)
    
    **Do not propose hours scaffolding until staffing is locked.** The
    hours grid is shaped by who's on the project (3 staff vs 4 vs 5,
    PM-and-SOR-same-person vs separate, etc.). Walking hours without
    knowing the staff is a guaranteed rework round.

### Images
12. **Cover photo** — path to a single image for the cover photo zone. Optional. Confirm: any baked-in annotations (map callouts, scale bars, north arrows are OK; software UI like Google Earth watermarks are flagged but acceptable if it's a map; red working markup is NOT acceptable).
13. **Other images** — body figures and exhibits. List each as `{path, role: cover|body_figure|exhibit, caption, annotations_ok: yes/no}`. Skill computes aspect ratio and picks placement zone (see `references/brand_spec.md` § Image handling).

### Sample deliverables (when client provides one)

When the client (or their design engineer) provides a sample of the expected
deliverable — a sample LAS file, a reference report PDF, an example CAD set —
review it BEFORE locking the proposal scope. The sample often reveals:

- Custom classification schemes, code legends, or feature-code conventions
  that differ from the published spec
- Granularity expectations (lumped catch-all classes vs. per-feature breakouts)
- Format conventions (CSV/TXT alongside LAS, file naming, attribute schemas)
- Hidden delivery expectations not in the written spec

Analyze the sample explicitly. If it reveals scope ambiguity that affects
labor, flag it to the user before sending the proposal. The T&M NTE
structure absorbs scope uncertainty cleanly when paired with the
scope-removal clause — use that pattern rather than committing to specific
granularity the sample suggests but the spec doesn't.

The Hilger-Roy June 2026 proposal saw HDR's sample LAS reveal a custom
TerraScan class table different from both ASPRS and the RFP feature codes —
the design engineer ultimately offered to correlate codes on their end in
PLS-CADD, resolving the question without re-papering.

### Fees
14. **Fee mode** — (Build / verify the bid workbook BEFORE running build.py. If no workbook exists yet, use `scripts/bootstrap_project.py` to create the project folder and SaveAs the canonical template into it.)
    - **Workbook pull (preferred when a Stahly bid workbook exists)**: provide `{workbook_path}`. Skill auto-detects the bid sheet by structural fingerprint (sheet rename is OK), reads phase totals live via `bid_workbook.fee_table_payload`, and prints any underbid warnings (blank staff names + hours, zero rate + hours, fallback-rate sourcing). Pass `--workbook <path>` to `build.py` and supply title/lead/corridor_miles in the JSON's `fee_table` section. When the workbook's ROUNDUP-to-$1K total differs from the sum of $100-rounded line items, the PDF prints both numbers (per gotcha #4 in `references/bid_workbook_spec.md`: ROUNDUP rule is non-negotiable for displayed totals).
    - `phase_table`: provide each phase as `{name, labor, expenses}` as raw integer dollars. Skill rounds each to nearest $100 and sums in code. Use this when the project predates a bid workbook or the user wants to override workbook values.
    - `simple_callout`: provide a single total fee. Skill renders a 3-row callout.

### Output
15. **Output PDF path + slug** — defaults to parent folder + `{project_slug}_DRAFT.pdf`. Ask if this is a draft (`_DRAFT`), versioned (`_v1`), or final (`_FINAL_{date}`).

### Confirmation
Summarize the intake back to the user in a bulleted list. Ask: *"Build it? (yes / change #N / cancel)"*

## Step 2 — Build

Once the user confirms:

### 2a. Write content JSON
Write the gathered intake to a content JSON file matching `references/content_schema.md`. Put it next to the planned output PDF for traceability (e.g. `proposal_content.json` in the project folder).

### 2b. Run sanity checks
```powershell
python ~/.claude/skills/stahly-proposal/scripts/verify_assets.py --content <content.json>
```
If anything fails (missing logos, unknown office, off-brand color/font, missing required section, missing cover photo file), **fix before building**. Don't proceed past this gate.

### 2c. Build the PDF
```powershell
python ~/.claude/skills/stahly-proposal/scripts/build.py `
    --content "<content.json>" `
    --out "<output.pdf>" `
    --cover-photo "<cover_photo_path>" `   # omit if no cover photo
    --workbook "<bid_workbook.xlsx>"        # omit if no workbook; otherwise fee_table phases come from workbook
```

When `--workbook` is set: the `fee_table` section in the content JSON keeps its `title` / `lead` / `corridor_miles`, but its `phases` array is replaced by the workbook's live phase totals. Drift between the intake phases (if any were in the JSON) and the workbook is printed to stderr. Workbook underbid warnings (blank staff + hours, zero rate + hours, fallback-rate sources) also print to stderr — review them before declaring final.

If the target PDF is locked by a viewer (PermissionError), set `STAHLY_PROPOSAL_OUT=<versioned name>` and retry.

The build writes the PDF + a paired `*_log.md` file in the same folder. When `--workbook` is used, the log records the workbook path, sheet name (auto-detected by fingerprint, so a renamed sheet is fine), raw total, and ROUNDUP-to-$1K total. The log is non-negotiable — if it didn't write, something failed.

### 2d. Apply docx writeback (if user provided source docx + overrides)
If intake captured overrides to a source docx (e.g. the user changed the schedule duration during intake), apply those edits back to the docx so the docx + PDF stay paired. This is the bidirectional-sync behavior — for v1.0, this is done manually using `python-docx` (the wired-in writeback engine is planned for v1.1). Reference the Hilger-to-Roy `apply_redlines_to_v3_docx.py` script as a template.

## Reusable content patterns

Before drafting a proposal section from scratch, check whether the situation
matches one of these documented patterns:

- **T&M NTE phase with potential mid-execution removals** — use
  `references/clauses/scope_removal_clause.md`. The asymmetric clause (client
  can subtract without amendment; adds require amendment) protects margin
  while giving the client a real lever. First used Hilger-Roy June 2026.
- **Schedule that depends on third-party deliverables** — use
  `references/clauses/third_party_preconditions.md`. Two homes for the same
  precondition (Schedule paragraph + Assumptions section) so the dependency
  is visible to a reader scanning either location.
- **Mixed lump-sum + T&M fee structure** — the `fee_table` schema supports a
  per-phase `basis` field (`"Lump Sum"` / `"T&M NTE"` / etc.). When any
  phase declares a `basis`, build.py auto-renders a centered Basis column
  so the dual-basis structure is visible row-by-row instead of buried in
  the lead paragraph.
- **Bilateral fee structure proposals also use the scope_removal_clause** —
  pair the Basis column with the removal clause for consistent client-side
  understanding of what's fixed and what's flexible.

If the situation doesn't match an existing pattern, propose new clause
language to the user and offer to save it under `references/clauses/` for
future reuse. Patterns get encoded once and re-used; don't reinvent the
language each time.

## Step 3 — Visual QA

```powershell
python ~/.claude/skills/stahly-proposal/scripts/render_qa.py "<output.pdf>"
```

This writes one PNG per page to `<output_folder>/qa_renders/`. **Read each PNG** (use the Read tool — it shows you the image) and walk through `references/qa_checklist.md`. Promote each item `[ ]` → `[x]` only after looking at the rendered page.

If any item fails, identify the cause, fix it (either in the content JSON, the cover photo file, or by tweaking build.py if it's a layout regression), and rebuild. Rebuild = re-render PNGs = re-walk the checklist. Do not skip the re-walk.

**After every rebuild, the FIRST thing you do is render PNGs and read all of them — not "the changed ones." Hard rule.** Page-break behavior is non-local; a content edit on page 2 can shift the signature ceremony from page 5 to page 6. You will not catch cascade effects by spot-checking. The full walk is fast (5 Read calls); the cost of skipping it is a redlines round you didn't need.

**Page count is not the goal; cohesive per-page content is.** A 5-page proposal with an awkward break — fee table split from its caption, signature ceremony orphaned from "Sincerely," — is worse than a 6-page proposal with a dedicated signature page and breathing room between sections. Don't burn iterations trying to squeeze content into a target page count when the layout fundamentals (clean section boundaries, intact tables, coherent signing ceremony) are already satisfied.

Iterations are normal. Twelve iterations are not. If you're past three, escalate to the user — there's something the intake didn't capture.

After the visual QA passes, walk `references/pre_send_checklist.md` as a
final content pass before declaring done. The visual QA catches "the table
looks orphaned"; the pre-send checklist catches "the table commits us to
something we didn't mean." Both are mandatory; the proposal isn't done
until both have been walked.

### See-then-edit rule for user redlines

When the user gives redlines that reference a visual element (position, spacing, sizing, overflow, alignment, anything that requires looking at the page to understand), **always inspect the current rendered state FIRST, before making code/content changes**. The sequence is:

1. **See** — render the current PDF to PNGs (if not already rendered) and read the relevant pages with the Read tool.
2. **Diagnose** — confirm you understand each redline item against what you're actually looking at. If a redline is ambiguous after looking, ask the user — don't guess.
3. **Edit** — apply the fixes.
4. **See again** — re-render and re-read the same pages to confirm the redline is resolved.
5. **Iterate** — if a fix didn't land, repeat. Continue iterating until every redline item is visually confirmed resolved, not just code-confirmed applied.

This rule prevents "I changed the code, but the rendered page doesn't actually show what the user asked for" failures. A code edit that doesn't actually fix the user-visible problem is worse than no edit — it consumes a trust budget and a turn.

The rule applies to any visual element: cover layout, signature placement, table formatting, page-break behavior, image positioning, font sizes, indentation, alignment. It does NOT apply to pure text content edits (e.g. "change 'Roy' to 'Hilger'") where the diff is unambiguous from the redline alone.

## Step 4 — Sign-off + retrospective (self-healing)

When the user accepts the PDF as final:

1. **Promote the file**:
   - If still `_DRAFT`, rename to `_v1` or `_FINAL_{date}`.
   - Rebuild with `STAHLY_PROPOSAL_OUT=<new_path>` to keep the log file paired with the new name.
2. **Final log update**: open the paired `_log.md` and add the iteration count + sign-off date + user's name.
3. **Self-healing retrospective** (only fires when iterations > 2):
   - Summarize what required user redirection in the form: *"Iter N: user changed X → Y because Z."*
   - Propose 1–3 specific updates to the skill: a new intake question, a tightened sanity check, a clarified schema, or a tweak to the QA checklist.
   - **Do not silently apply.** Show the user the proposals and ask: *"Apply? Each accepted change gets a changelog entry in `README.md`."*
   - For each accepted change: edit the relevant skill file (SKILL.md, references/, scripts/), bump the changelog with date + 1-line description + reference to the proposal that catalyzed it.

## Side workflow — contract assembly (fill + staple for DocuSign)

When a project needs a signed contract that pairs with the proposal (typical for new clients, less common for retainers), the skill ships a parameterized contract filler:

```powershell
python ~/.claude/skills/stahly-proposal/scripts/fill_contract.py `
    --content <contract.json> `
    --proposal <signed_proposal.pdf>
```

Outputs to the proposal's parent folder by default:
- `<date>_<slug>_Contract_for_DocuSign.docx` — filled contract (source)
- `<date>_<slug>_Contract_for_DocuSign.pdf` — same as PDF
- `<date>_<slug>_Contract_AND_Proposal_for_DocuSign.pdf` — stapled file ready for the DocuSign envelope
- `<date>_<slug>_Contract_for_DocuSign_log.md` — paired log

The content JSON shape, the visual gotchas (two-column sig-block tab alignment, PM/Contact block layout, empty-paragraph spacer), and the QA checklist are documented in `references/contract_fill_spec.md`. The fill script never writes to the master template — it copies to the project folder first and edits only the project copy.

**See-then-edit applies here too.** When the user redlines the contract sig block (alignment, font size, spacing, who signs, etc.), render the contract PDF to PNGs FIRST, look at it, diagnose, then edit. The contract template's tab stops and styles are surprisingly fragile under arbitrary edits — visual inspection catches what code edits miss.

## Side workflow — preparing a signatory's signature image

If the user has a scanned ink signature (Aaron, Rylan, or any other signatory) that needs to become a transparent PNG before being overlaid on a signed proposal, contract, or email:

```powershell
python ~/.claude/skills/stahly-proposal/scripts/make_signature.py "C:\path\to\scan.jpg"
```

Default output is `<input_dir>/<stem>_transparent.png` with ink color preserved (blue pen stays blue). Read the output PNG and check: paper fully gone, strokes intact, edges clean. Tuning knobs (`--dark`, `--light`, `--blur`, `--autocontrast`, `--force-black`) are documented in `references/signature_prep.md` — use them when the default ramp doesn't fit the input scan.

Don't use this on full photos, color logos, or anything with both light and dark regions that matter — the luminance ramp can't tell a dark shadow from dark ink.

## What this skill refuses

- Color overrides ("can we make Stahly Blue darker?") — escalate to Marketing
- Font swaps (Cambria, etc.) — brand-locked Rockwell + Arial
- Logo file substitutions — official PNGs only
- New page templates / cover layouts — locked from Hilger-to-Roy production proof
- Hand-typed grand totals — `build.py` always computes from rounded line items

## What this skill expects from you

- **Read the rendered PNGs.** Text-only inspection misses what kills proposals.
- **Walk the QA checklist explicitly.** Don't claim done without checking each box.
- **Write the log file.** Build script does this automatically — if it doesn't write, the build failed.
- **Track iterations.** > 2 iterations → escalate.
- **Don't invent content.** Source from the docx or from user-provided sections. Light edits for clarity only.
