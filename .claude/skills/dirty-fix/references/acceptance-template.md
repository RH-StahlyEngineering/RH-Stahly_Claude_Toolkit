# acceptance.md template

Fill every section. Delete none. An empty section is a signal, not an omission.

---

```markdown
<!--
  ACCEPTANCE BUNDLE — SPECIFICATION, NOT DOCUMENTATION
  This describes software that does NOT yet exist. It is not a description of
  existing code. Produced by dirty-fix v{VERSION} from bundle {SLUG} on {DATE}.
  The prototype that produced it has been deleted by design.
-->

# {Title}

## Problem

One paragraph, plain language. What is being attempted and why. No solution content.

## Input contract

- **Format:** {what the input is}
- **Fixture:** `{path}` — the minimized real input this specification was proven against
- **Source:** derived from `{production source}` via {reduction strategy}
- **Holdout:** `{path}` — a second slice, run once, result below

## Output contract

- **Format:** {what the output must be}
- **Reference:** `{path}` — the approved output, if a frozen reference applies
- **Meaning of correct:** {stated as properties, not as a procedure}

## Acceptance checks

Definition of done. Run:

    python check.py --candidate <output-path>

Exit 0 is the gate. Exit 1 is not done.

| ID | Mode | Asserts | Why it exists |
|----|------|---------|---------------|
| {id} | {mode} | {assertion} | {the rejection it came from} |

Each check was validated against a real observed failure. See `metrics.json` for
provenance.

### Requires human sign-off

Criteria that cannot be asserted mechanically. `check.py` emits review artifacts for
each; a human must confirm them before this work is considered complete.

| Criterion | Review artifact |
|-----------|-----------------|
| {criterion} | {what check.py emits to make the review fast} |

## Constraints discovered

Domain facts learned while proving this. True regardless of implementation approach.
No techniques, no libraries, no algorithms.

- {constraint}

## Coverage

| Dimension | Production | Fixture | Verdict |
|-----------|-----------|---------|---------|
| {dimension} | {value} | {value} | covered / underrepresented / absent |

**Holdout result:** {pass/fail} — {notes}

## What this fixture cannot prove

Each item is a design question to resolve or a risk to explicitly accept. None of them
is an assumption that may be inherited.

- {absent or underrepresented coverage}
- {scale, concurrency, or volume behavior never exercised}
- {stubbed side effects}
- {edge conditions removed by the reduction}

## Out of scope

- {explicitly not part of this work}

## For the implementing agent

These rules are part of the specification.

- Do not read `appendix-hacks.md`. If you stall, say so and ask first.
- This document contains no implementation guidance by design. You are under no
  constraint as to approach — any approach that passes the checks is acceptable.
- "What this fixture cannot prove" lists behaviors that were never exercised. Each is a
  design question you must resolve, not an assumption you may inherit.
- The implementation plan's final task MUST run:

      python dirty-fix/{SLUG}/check.py --candidate <output>

  Definition of done is exit 0, plus human sign-off on any declared-subjective criteria.
  Not your reading of the output.
- `check.py` accepts `--fixture <path>`. When production later reveals a case this
  fixture lacked, add a fixture and a check rather than rewriting this specification.
```

---

## Leak self-check

Before sealing, scan the written file. Any of these is a defect to fix:

- a library or package name in anything but the input/output format description
- an algorithm name
- a named technique, filter, or method
- a code snippet outside the check table
- a sentence that begins "the approach is" or "it works by"

Formats and interfaces are permitted — the input really is a `.laz` file, the output
really is JSON. Solutions are not.
