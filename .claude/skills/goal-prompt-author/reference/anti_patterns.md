# Common /goal anti-patterns

What to look for when reviewing a draft, and how to fix each.

## 1. Aspirational end state

**Symptom:** condition phrased as a wish, not a measurement.

```
BAD:  /goal Make the codebase production-ready
BAD:  /goal Improve the user experience
BAD:  /goal Make this work better
```

**Fix:** force the user to name a specific metric or output that can be checked.

```
GOOD: /goal Every endpoint in api/ has at least one test (verify: `pytest --collect-only tests/api/ | grep "test_"` finds tests covering every route in `src/api/routes.py`)
```

## 2. Implicit verification

**Symptom:** the condition assumes the evaluator knows how to verify.

```
BAD:  /goal Tests should pass
BAD:  /goal The bug is fixed
BAD:  /goal The output looks correct
```

**Fix:** spell out the verification command.

```
GOOD: /goal `pytest tests/auth -x --tb=short` exits 0
GOOD: /goal Issue #1234 reproduces no longer (verify by running `python repro_1234.py` and confirming exit 0)
```

## 3. Multiple independent goals in one /goal

**Symptom:** condition has "AND" joining unrelated outcomes.

```
BAD:  /goal All tests pass AND the docs are updated AND the changelog has entries
```

**Fix:** split into separate /goal invocations. Or use /loop for multi-pass work. A single /goal should target ONE convergent end state.

```
GOOD: Run three /goals in sequence:
  1. /goal `pytest -x` exits 0
  2. /goal Every public function in src/api/ has a docstring (verify with interrogate)
  3. /goal CHANGELOG.md has an entry for every PR merged this week
```

## 4. Unconstrained scope

**Symptom:** the goal mentions WHAT but not what NOT to touch.

```
BAD:  /goal Refactor the auth module
```

**Fix:** add explicit constraints.

```
GOOD: /goal Refactor src/auth/ so each file is < 200 lines, all tests still pass, all imports updated.
      CONSTRAINTS:
        - Do not modify any file outside src/auth/
        - Do not change the public API (function signatures in __all__)
        - Do not change config files or package.json
        - Do not delete any test
```

## 5. Vague success criteria

**Symptom:** the condition is technically verifiable but allows many interpretations.

```
BAD:  /goal The function returns the right value
```

**Fix:** specify the input/output pairs.

```
GOOD: /goal calculate_tax([{"amount": 100, "state": "MT"}]) returns 0.00; calculate_tax([{"amount": 100, "state": "CA"}]) returns 8.75
```

## 6. Missing scope bound

**Symptom:** no upper limit on turns or time, so a non-converging task burns indefinitely.

```
BAD:  /goal <condition with no SCOPE BOUND section>
```

**Fix:** always include either a wave/turn cap or wall-clock cap or both.

```
GOOD: SCOPE BOUND: Stop after 12 turns OR 60 minutes wall-clock.
```

## 7. Missing abort conditions

**Symptom:** the goal can't halt on a critical failure mode (corrupted state, lost auth, etc.) and tries to recover, making things worse.

```
BAD:  <no ABORT CONDITIONS section>
```

**Fix:** explicitly list halt triggers.

```
GOOD: ABORT CONDITIONS
  - Database connection fails 3 times consecutively → halt
  - Any test marked @critical regresses → halt
  - More than 10 file edits in a single turn → halt
```

## 8. Pre-flight blindness

**Symptom:** the goal depends on a tool/MCP/file existing, but doesn't verify before fanning out.

```
BAD:  /goal Use mcp__X to do Y (assumes X is available)
```

**Fix:** add a pre-flight that tests the dependency and halts cleanly if missing.

```
GOOD: PRE-FLIGHT
  1. Run mcp__X with a known-good test input. If output is empty or errors, halt with "X MCP not loaded; restart Claude Code."
  2. Confirm file `config.yaml` exists. If not, halt.
```

## 9. Reference data missing

**Symptom:** the goal could be done faster if it pointed at existing schemas/docs/prior outputs, but doesn't.

```
BAD:  /goal Audit the database schema (and the runner has to discover everything from scratch)
```

**Fix:** point at known-good reference material.

```
GOOD: REFERENCE DATA
  - Current schema dump: db/schema_2026_05.sql
  - Audit framework: docs/audit_methodology.md (follow phases exactly)
  - Known issues: docs/known_data_quality_issues.md (deduplicate against these)
```

## 10. "Best-effort" loophole

**Symptom:** the goal allows the runner to mark items as "skipped" or "unconfirmed" to converge faster, defeating the purpose.

```
BAD:  /goal Audit every record (or mark as "skipped" if unclear)
```

**Fix:** require items hit the controlled vocabulary; reject "unknown" as a convergence path.

```
GOOD: /goal Audit every record. Each row's status must be one of: VALID, INVALID, REQUIRES_HUMAN_REVIEW. The vocabulary is closed; do not introduce new statuses. Items with insufficient evidence get REQUIRES_HUMAN_REVIEW, but they MUST include the specific evidence gap in the note column.
```

## 11. Hidden multi-pass requirements

**Symptom:** the goal mentions one phase but actually needs many.

```
BAD:  /goal Convert all imports from CommonJS to ESM (no mention that this implies updating tsconfig.json, dependent packages, jest config, etc.)
```

**Fix:** if the work has multiple sub-tasks, name them in an ARCHITECTURE section.

```
GOOD: /goal Convert all imports from CommonJS to ESM such that `npm test` passes.
      ARCHITECTURE
        - Phase 1: Update all `require()` to `import`
        - Phase 2: Update all `module.exports` to `export`
        - Phase 3: Add "type": "module" to package.json
        - Phase 4: Update tsconfig.json module setting
        - Phase 5: Run `npm test` to verify
```

## 12. Wrong tool for the job

**Symptom:** the user wants a one-shot answer but writes it as a /goal.

```
BAD:  /goal Tell me what the codebase does
BAD:  /goal Explain the authentication flow
BAD:  /goal Suggest improvements to the API
```

**Fix:** these are regular prompts, not /goal targets. /goal is for autonomous multi-turn WORK toward a verifiable end state. Explanation/analysis with no convergence target should just be a regular prompt or `/ultrareview` style review.
