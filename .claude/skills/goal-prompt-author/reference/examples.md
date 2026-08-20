# Real-world /goal examples

Six well-formed `/goal` blocks across different categories, plus brief notes on why each works.

## ⚠ Char limit reminder

`/goal` is capped at 4,000 characters. The structured Example 1 below was originally 5,656 chars (rejected). The fix is in Example 1b — same intent, compact form, ~1,400 chars. **Always run `validate_draft.py` before firing.**

---

## Example 1: Audit (long-horizon, multi-phase)

This is the actual goal used to audit the trailquipt ops workbook — 21 sheets, 302 inventory items, 73 rules produced.

```
/goal Produce a complete cell-lineage audit for the ops workbook (16lz8d7fU9crD5iGxzqyuX70J1QfyUmUx9dm8H-zjH3M, "2024 Cells Map").

VERIFIABLE END STATE
  The file C:\Users\rharbach.STAHLY\.claude\skills\trailquipt\.cache\lineage\16lz8d7f\final.json exists, has one entry per (sheet, column) pair returned by mcp__workspace-script__getSpreadsheetInfo for the workbook (including all 21 sheets), and every entry has non-null source_type and non-null confirmed_by fields. Verify with:

    python -c "import json; d=json.load(open(r'C:\Users\rharbach.STAHLY\.claude\skills\trailquipt\.cache\lineage\16lz8d7f\final.json')); null=[r for r in d if r['source_type'] is None]; print('total', len(d), 'null', len(null)); assert len(d)>0 and len(null)==0"

  When that command exits 0 and prints `null 0`, the goal is met.

ARCHITECTURE
  Follow C:\Users\rharbach.STAHLY\.claude\skills\trailquipt\reference\lineage_audit_design.md exactly:
  - Phase 0: enumerate every sheet + column via getSpreadsheetInfo and read_sheet_values on row 1
  - Phase 1: for each sheet, spawn a subagent or read directly to identify coverage rules
  - Phase 2: call `lineage_audit.py gaps` between waves
  - Phase 3: for each remaining unexplained item, spawn a targeted investigator
  - Phase 4: queue external IMPORTRANGE deps; do NOT chase
  - Phase 5: synthesize final.json

CONSTRAINTS (no exceptions)
  - READ-ONLY: never write to the ops workbook; never modify either bound Apps Script
  - Source classifications must use the controlled vocabulary in lineage_audit.py SOURCE_TYPES
  - Items with ambiguous sources get source_type="unconfirmed", not best-guess
  - Cross-workbook deps are queued, not investigated
  - Every rule must include literal evidence (formula text or grep hit)

SCOPE BOUND
  Stop after 12 waves OR 60 minutes wall-clock, whichever first.

ABORT CONDITIONS
  - Any attempt to write to the ops workbook → halt
  - State file becomes corrupt → halt
  - Wave count reaches 12 with progress < 5% of remaining items → halt
```

**Why this works:**
- End state is a specific file with a verifiable schema; the verification command exits 0 only when condition holds
- Constraints are EXHAUSTIVE — every concern (read-only, vocabulary, evidence, no scope creep) is named
- Architecture references a design doc instead of inlining 100 lines of methodology
- Abort conditions map to real failure modes (corrupt state, non-convergence)
- Scope bound is generous (12 waves) but bounded

**⚠ Char count: 5,656 — over the 4,000 hard limit.** See Example 1b below for the fix.

---

## Example 1b: Same audit goal, COMPACT (~1,400 chars, fits the limit)

Same intent as Example 1, restructured to fit under 4,000 chars. The trick: reference the design doc instead of inlining methodology.

```
/goal Complete cell-lineage audit of ops workbook (16lz8d7fU9crD5iGxzqyuX70J1QfyUmUx9dm8H-zjH3M).

End state: C:\Users\rharbach.STAHLY\.claude\skills\trailquipt\.cache\lineage\16lz8d7f\final.json exists, has one entry per (sheet, column) pair from getSpreadsheetInfo (all 21 sheets), every entry has non-null source_type AND non-null confirmed_by.

Verify with: `python -c "import json; d=json.load(open(r'C:\Users\rharbach.STAHLY\.claude\skills\trailquipt\.cache\lineage\16lz8d7f\final.json')); n=[r for r in d if r['source_type'] is None]; assert len(d)>0 and len(n)==0"` exits 0.

Methodology: follow C:\Users\rharbach.STAHLY\.claude\skills\trailquipt\reference\lineage_audit_design.md exactly. Apply lessons from .cache\lineage\16lz8d7f\retrospective.md (orchestrator-direct preferred over subagents; mixed-content columns use covers_pattern not "ambiguous").

Pre-flight: run `python scripts\health_check.py --critical-only`; halt if non-zero.

Constraints:
  - READ-ONLY: never write to the workbook; never modify either bound Apps Script
  - source_type must come from lineage_audit.py SOURCE_TYPES controlled vocab
  - Items with insufficient evidence get "unconfirmed", not best-guess
  - Cross-workbook IMPORTRANGE deps are queued, not investigated
  - Every rule needs literal evidence (formula text or grep hit) in `evidence` field

Stop after 12 waves OR 60 minutes. If not converged, surface gaps via `lineage_audit.py gaps` and halt.

Abort if:
  - any write to the workbook is detected
  - state file becomes corrupt
  - wave count reaches 12 with progress < 5%
```

**Why this works (the compact version):**
- ~1,400 chars — well under the 4,000 limit
- Architecture/lessons/pre-flight are all referenced via file paths instead of inlined
- Constraints are tight (5 bullets vs 6); each is specific
- Aborts are 3 specific conditions, not pre-emptive paranoia
- Verification is a single Python one-liner that exits 0 on success
- The methodology line points the runner at TWO docs: the design + the retrospective, so lessons-learned are loaded automatically

---

## Example 2: Test-driven bug fix (short, single-phase)

```
/goal Fix the bug in src/parser.py such that:
  - `pytest tests/test_parser.py::test_handles_empty_input -x` exits 0
  - `pytest tests/test_parser.py -x` still exits 0 (no regressions)

CONSTRAINTS
  - Do not modify any file outside src/parser.py and tests/test_parser.py
  - Do not change the public API of the Parser class (signatures in __all__)
  - Do not add new dependencies to requirements.txt

SCOPE BOUND
  Stop after 5 turns.

ABORT CONDITIONS
  - The previously-passing test test_handles_unicode regresses → halt and surface
```

**Why this works:**
- End state is two commands that both must exit 0 — verifiable, no ambiguity
- Constraints prevent scope creep (parser changes don't bleed into config)
- Tight scope bound for a focused task
- Abort flags a specific regression worth halting on

---

## Example 3: Migration (multi-file, careful)

```
/goal Migrate every `console.log` in src/ to `logger.info` such that:
  - `grep -rn "console.log" src/` returns no matches
  - `npm test` exits 0
  - `npm run lint` exits 0

CONSTRAINTS
  - Do not modify any tests (tests still mock console; that's intentional)
  - Do not modify package.json or tsconfig.json
  - Do not change function signatures
  - At the top of each modified file, ensure `import { logger } from './logger'` (or appropriate relative path) is present; do not introduce new top-level imports other than logger

SCOPE BOUND
  Stop after 8 turns.

ABORT CONDITIONS
  - More than 100 files would need modification (this would be too broad — halt and ask for review)
  - The lint output mentions any rule other than `no-console`
```

**Why this works:**
- Triple end-state check (grep + tests + lint) catches the most likely ways to "complete" badly
- Constraints prevent the runner from "fixing" tests that intentionally use console
- Abort condition catches scope blowup before it happens

---

## Example 4: Data quality / one-off

```
/goal Ensure every row in users.email_verified_at is non-null. Verify with:
  psql -d production -c "SELECT COUNT(*) FROM users WHERE email_verified_at IS NULL;" returns 0.

CONSTRAINTS
  - READ-ONLY on the production database — do NOT issue any UPDATE/INSERT/DELETE
  - To fix: write the migration SQL to a file at migrations/2026_05_25_backfill_email_verified.sql
  - The migration must be idempotent (re-runnable safely)
  - End state is satisfied when the migration FILE exists and a dry-run plan is recorded; the user will execute it manually

SCOPE BOUND
  Stop after 3 turns.

ABORT CONDITIONS
  - Any actual DML statement is issued against production → halt immediately
```

**Why this works:**
- Read-only constraint is bold and unambiguous
- End state is moved from "the data is fixed" (would require write access) to "the migration file exists" (safer)
- Abort condition catches the worst-case violation

---

## Example 5: Documentation enforcement

```
/goal Every public function and class in src/api/ has a docstring (single-line minimum). Verify with:

  interrogate -i src/api/ --fail-under 100

  When that command exits 0, the goal is met.

CONSTRAINTS
  - Do not modify code, only add docstrings
  - Docstrings should describe what the function does in 1-3 sentences; do not invent semantics — read the function body and describe ACTUAL behavior
  - For functions whose behavior is unclear from reading, leave the docstring as `# TODO: confirm behavior with author` rather than guessing

SCOPE BOUND
  Stop after 6 turns.

ABORT CONDITIONS
  - Any function gets a docstring that contains the phrase "this function" with no specifics → halt (boilerplate isn't useful)
```

**Why this works:**
- Verification is a concrete tool (`interrogate`)
- Constraints differentiate "describe accurately" from "make up plausible-sounding docs"
- Abort catches "looks done but is empty calorie" output

---

## Anti-pattern example (what NOT to do)

```
/goal Clean up the codebase and make it production-ready. Tests should pass.
```

This violates:
- #1 Aspirational end state ("clean up" is not measurable)
- #2 Implicit verification ("tests should pass" → which tests? what command?)
- #3 Multiple independent goals (cleanup AND production-ready AND tests)
- #4 Unconstrained scope (no limits on what to touch)
- #6 Missing scope bound (no turn/time cap)
- #7 Missing abort conditions

Fix: split into 3+ targeted /goals, each with verifiable end state + check + constraints + scope bound + abort conditions.
