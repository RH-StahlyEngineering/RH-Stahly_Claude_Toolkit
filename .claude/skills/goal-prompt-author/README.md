# goal-prompt-author skill

A Claude Code skill that helps you author or critique `/goal` prompts. Built from real experience writing `/goal` blocks for non-trivial autonomous tasks (multi-phase audits, refactors, migrations).

## What is `/goal`?

`/goal` is Claude Code's autonomy harness ([docs](https://code.claude.com/docs/en/goal)). You give Claude a condition; Claude works in a loop until the condition is met (evaluated by a small fast model each turn) or until it hits a scope bound. Auto-clears on success. **The condition is everything** — a vague condition makes it converge falsely; an unverifiable one never converges.

## Quick start

In a fresh Claude Code session, just describe what you want Claude to do autonomously:

```
I need a /goal prompt for refactoring auth.py into smaller files while keeping all tests passing
```

The skill auto-triggers and walks you through:
1. The verifiable end state
2. The stated check (the literal command that proves convergence)
3. Constraints (what must NOT change)
4. Scope bound (turns or wall-clock)
5. Abort conditions (failure modes that should halt)

Output: a copy-pasteable `/goal` block.

For a draft you already have, paste it and say "critique this /goal" — the skill will run `validate_draft.py` and point out gaps.

## Folder map

```
~/.claude/skills/goal-prompt-author/
├── SKILL.md                      Orchestration brain — auto-loaded by Claude
├── README.md                     This file
├── reference/
│   ├── three_components.md       Canonical structure (end state, check, constraints)
│   ├── anti_patterns.md          12 common mistakes + how to fix each
│   ├── examples.md               5 real well-formed /goal blocks across categories
│   ├── verification_recipes.md   "Stated check" patterns by language/tool
│   └── template.md               Assembly skeleton + checklist
└── scripts/
    └── validate_draft.py         Score a /goal draft against the canonical structure
```

## When to use this skill

- **You're about to write a `/goal`** and want to make sure it's well-formed
- **You've drafted a `/goal`** and want a sanity check before firing
- **A previous `/goal` failed to converge** and you want to figure out what was wrong
- **You're explaining `/goal` to someone else** and want a reference

## When NOT to use this skill

- **Trivial one-shot prompts** — `/goal` is overkill for "what does this code do" or "summarize X"
- **Pure analysis tasks** — `/goal` is for WORK with a convergence target, not Q&A
- **Multi-goal compounds** — split into separate `/goal` invocations, don't pile them up

## The three components

Every good `/goal` has:

1. **One measurable end state** — a checkable condition (file exists with schema, command exits 0, queue is empty)
2. **A stated check** — the literal verification command (`pytest -x exits 0`, not "tests pass")
3. **Constraints** — what MUST NOT change (read-only on database, don't modify config files)

Plus optional but recommended: scope bound, abort conditions, pre-flight validation, architecture for multi-phase tasks, reference data pointers.

See `reference/three_components.md` for details.

## Anti-patterns to watch for

The validator catches:
- Aspirational language ("make it better", "production-ready")
- Implicit verification ("tests pass")
- Multiple AND clauses (multi-goal compound)
- Broad-scope keywords ("refactor the codebase")
- Missing required sections

See `reference/anti_patterns.md` for all 12.

## Verification recipes

If you don't know how to verify a particular type of task, `reference/verification_recipes.md` has patterns for:
- Test suites (pytest, jest, mocha, cargo, etc.)
- Build/compile (tsc, webpack, docker, etc.)
- Lint/format (eslint, ruff, mypy, etc.)
- File existence and schema
- Git state
- Database state
- Background processes / services
- Custom Python verify-scripts

## Validating a draft

```bash
python scripts/validate_draft.py --input my_goal.txt
# Or pipe:
cat my_goal.txt | python scripts/validate_draft.py --stdin
```

Output: checklist of present components, weak components, missing optional components, detected anti-patterns. Exit 0 if no critical gaps; exit 1 if missing required sections.

## Real examples in the wild

`reference/examples.md` includes 5 worked examples across task types:
- **Audit** (long-horizon, multi-phase) — actual goal that completed the trailquipt lineage audit
- **Bug fix** (short, single-phase)
- **Migration** (multi-file, careful)
- **Data quality** (read-only with file-output proxy)
- **Documentation enforcement**

Plus one "what NOT to do" example with 6 anti-patterns called out.

## Tips from experience

- **Push back on shoddy specifications.** Better to interview the user than ship a vague `/goal`. A weak goal wastes tokens.
- **Always end with a code-fenced `/goal` block** so the user can copy-paste cleanly.
- **For tooling-sensitive tasks, add a PRE-FLIGHT** that tests dependencies first. We've had `/goal` runs halt mid-work because an MCP wasn't behaving — pre-flight prevents that.
- **Scope bound is a documentation tool, not just safety** — explicit caps tell future-you why the goal was framed the way it was.
- **Reference data pointers** save the runner a lot of discovery time. If existing files in the workspace make the task easier, point at them by absolute path.

## How the skill interview works

When you ask for a new `/goal`, the skill:

1. Asks what success looks like — pushes back on vague answers
2. Pins down the stated check — gets a literal command
3. Surfaces constraints — what files/systems should NOT be touched
4. Suggests a scope bound — turns + wall-clock
5. Lists abort conditions — specific failure modes
6. (For complex tasks) Adds architecture/pre-flight/reference data
7. Assembles the final block + spot-checks against `anti_patterns.md`
8. Outputs a copy-pasteable code-fenced block

## Extending

To add new examples:
- Add to `reference/examples.md` with the same "Why this works" callouts
- Real examples > synthetic ones; prefer goals that actually ran successfully

To add new verification recipes:
- Add to `reference/verification_recipes.md` under the right category
- Keep recipes as exit-code-based commands, not as prose

To improve validation:
- Add new anti-pattern regexes to `scripts/validate_draft.py`
- Keep regexes specific (false positives erode trust)
