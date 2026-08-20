# The three components of a good /goal prompt

Per Anthropic's official `/goal` docs, an effective condition has three parts.

## 1. One measurable end state

**The condition Claude is working toward, expressed as something verifiable.** This is the most-violated component — users default to aspirational language.

### Good
- "the file `dist/bundle.js` exists and is < 200KB"
- "all rows in `users` table have non-null `email_verified_at`"
- "`pytest tests/ -x --tb=short` exits 0"
- "the `feature/auth-refactor` branch has 0 staged changes and all `auth/*.py` files pass `mypy --strict`"
- "the CHANGELOG.md file has a heading for every merged PR in the last 7 days"

### Bad — and how to fix
| Aspirational | Verifiable rewrite |
|---|---|
| "fix the failing tests" | "`pytest tests/auth -x` exits 0" |
| "improve the docs" | "every public function in `src/api/` has a docstring (verify with `interrogate -i src/api/`)" |
| "refactor the module" | "`src/auth.py` is split into files of < 200 lines each, all imports updated, all tests still passing" |
| "make it production-ready" | (too vague — break into multiple goals or define what "ready" means with specific checks) |
| "make this better" | (you don't have a goal — this is a vibe; the user needs to specify a metric) |

## 2. A stated check

**The literal command or inspection the evaluator can apply to the transcript to know the condition is met.** Spell it out in the goal text, not just in your head.

The evaluator is a small fast model (default Haiku) that reads what Claude has put in the transcript. If you say "tests pass", the evaluator has to guess. If you say "`pytest -x` exits 0", the evaluator looks for a 0-exit-code result in the transcript and knows.

### Good
```
Verify with:
  python -c "import json; d=json.load(open('out.json')); null=[r for r in d if r['source_type'] is None]; print(len(null)); assert len(null)==0"
When that command exits 0, the goal is met.
```

### Bad
```
The output should be correct.
Tests pass.
The bug is fixed.
```

### Pattern: paste the check command verbatim

A good pattern is to write the check as a `python -c "..."` or `bash -c "..."` one-liner the user can run themselves AND that prints a clear pass/fail indicator. The /goal evaluator looks at the transcript for evidence of that command being run with a passing result.

## 3. Constraints

**What MUST NOT change during execution.** Implicit constraints get violated; explicit constraints get respected.

### Good
- "READ-ONLY: never write to the production database"
- "do not modify any file outside `src/auth/`"
- "do not change `package.json` or `package-lock.json`"
- "do not push to any remote; commit locally only"
- "do not call any paid API (no Stripe, no OpenAI)"
- "do not delete or rename any existing tests"
- "treat the `vendor/` directory as untouchable"

### Bad
- (no constraints listed) — Claude may make sweeping changes
- "be careful" — not a constraint, just a vibe
- "don't break anything" — too vague to enforce

### Constraint design principle

For each constraint, ask: "if Claude violated this, would I have wanted to know before it happened?" If yes, the constraint belongs in the /goal.

## Optional: Architecture / methodology

For complex multi-phase tasks, briefly describe the approach.

Example (from a real audit goal):
```
ARCHITECTURE
  - Phase 0: inventory via getSpreadsheetInfo
  - Phase 1: orchestrator-direct formula reads (NOT subagents — lesson from prior run)
  - Phase 2: gap analysis
  - Phase 3: targeted investigators
  - Phase 4: queue external deps
  - Phase 5: synthesize final.json
```

Reference design docs by absolute path so the runner can read them.

## Optional: Scope bound

```
SCOPE BOUND
  Stop after 12 waves OR 60 minutes wall-clock, whichever first.
```

Acts as a safety net for non-convergence. The /goal runtime has its own caps; explicit bounds are documentation.

## Optional: Abort conditions

```
ABORT CONDITIONS
  - Any attempt to write to production DB is detected → halt
  - State file becomes corrupt (JSON parse fails) → halt
  - 3 consecutive turns produce no progress → halt
```

Map each abort to a specific real failure mode. Don't pad with generic conditions.

## Optional: Pre-flight validation

If the task depends on a specific tool / MCP / file existing in a specific state, validate BEFORE the work starts:

```
PRE-FLIGHT
  1. Run `python scripts/health_check.py --critical-only` and verify it exits 0.
  2. Confirm the MCP returns formula text by calling X with valueRenderOption=FORMULA and checking the result starts with '='. If not, halt with instructions to restart.
```

This is especially important for tasks that depend on environment quirks.

## Optional: Reference data

```
REFERENCE DATA
  - Sheet list with grid sizes: reference/reservations_workbook_schema.md
  - Apps Script write surface: reference/script_topology.md (use this to bulk-classify items)
  - Status legend: reference/status_legend.md
```

Saves the runner time by pre-loading what it'd otherwise have to discover.
