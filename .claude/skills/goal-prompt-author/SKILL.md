---
name: goal-prompt-author
description: Author or critique a Claude Code `/goal` prompt. Use when the user mentions writing a goal prompt, crafting a /goal, creating a goal block, helping with a /goal, reviewing a /goal draft, critiquing a goal, writing a goal directive, building a goal for an autonomous task, or any time they want to use the /goal slash command for multi-turn autonomous work and need help making the prompt good. Also triggers on phrases like "I need a goal prompt that...", "what should my /goal say", "is this /goal any good", "review my goal", or "make a /goal that does X".
---

# goal-prompt-author skill

You help the user write or critique a `/goal` prompt for Claude Code's autonomy harness.

## What `/goal` is and what it needs

`/goal` puts Claude in a loop: every turn an evaluator (a small fast model) checks the user-specified condition; if not met, Claude works another turn. Auto-clears when satisfied. **The condition is everything.** A vague condition makes the evaluator approve anything; an unverifiable one never converges.

## ⚠ Hard limit: 4000 characters

The `/goal` condition is capped at **4,000 characters**. Going over throws `Goal condition is limited to 4000 characters (got N)`. This is the single most important constraint to design around — especially for complex multi-phase tasks.

**Survival strategies when you need methodology but only 4000 chars:**

1. **Reference, don't inline.** A goal that says `Follow C:\path\to\design.md exactly` is 50 chars. The same methodology written out is 2000+.
2. **Move pre-flight to a script.** `Run python scripts/health_check.py and verify it exits 0.` is one line.
3. **Drop optional sections.** ARCHITECTURE / REFERENCE DATA / PRE-FLIGHT are recommended but not required.
4. **Tighten constraints.** 3 strong constraints > 10 weak ones.
5. **One verification command.** Not a sequence — one `python -c "..."` or shell pipe that returns 0/1.

Always end with `python scripts/validate_draft.py --input <draft>` to confirm the length is OK before pasting.

A good `/goal` has three components:

1. **One measurable end state** — a test result, an exit code, a specific file existing with a specific schema, a queue being empty. NOT "make this better" or "improve X."
2. **A stated check** — the literal command or inspection that proves completion. The evaluator only sees the transcript, so be explicit: `"npm test exits 0"` works; `"tests pass"` does not.
3. **Constraints** — what MUST NOT change during execution. E.g., `"don't modify any file outside /src/auth"`, `"read-only access to the database"`, `"don't touch package.json"`.

Plus optional but recommended:
- **Scope bound** (turns OR wall-clock) so it halts if not converging
- **Abort conditions** (specific failure modes that should halt)
- **Architecture / methodology** for complex tasks (phases, waves, agent caps)
- **Pre-flight validation** to catch tooling issues before fanning out
- **Reference data** pointers to existing files/docs the runner should leverage

See `reference/three_components.md` for details and `reference/anti_patterns.md` for what to avoid.

## How to invoke

### Authoring mode (default)
The user describes what they want done; you walk through the components and produce a copy-pasteable `/goal` block.

### Critique mode
The user pastes a draft; you point out gaps using the checklist in `scripts/validate_draft.py`.

If unsure which mode, ask once: "Want me to author a /goal from scratch, or critique a draft you have?"

## Authoring workflow

When the user wants a new `/goal`:

1. **Ask what success looks like as a verifiable end state.** Push back on aspirational answers ("make it work", "fix the bugs"). Examples of good answers: "the file X exists and contains Y", "this command exits 0", "all rows in this table have non-null column Z".
2. **Pin down the stated check.** Get the literal shell command or Python one-liner that proves completion. Often this is one line; sometimes it's a sequence. Have the user say it out loud or you propose it and confirm.
3. **Surface constraints.** Ask: what files/systems should NOT be modified? What dependencies should NOT be upgraded? What credentials should NOT be touched? Common ones: "read-only on database", "don't modify config files", "don't push to remote".
4. **Set a scope bound.** Default to 12–15 turns OR 60–90 minutes wall-clock for complex tasks. For simple one-shots, 5 turns / 15 min is plenty. The /goal runtime caps these anyway; explicit bounds are documentation.
5. **List abort conditions.** Standard ones to include: "state file becomes corrupt → halt"; "any subagent returns invalid output → reject and continue"; "[external safety condition] → halt". Tailor to the task.
6. **Optionally add architecture.** For multi-phase tasks (e.g., audits, migrations, large refactors), briefly describe the phases and reference any design docs.
7. **Add pre-flight validation if tooling-sensitive.** If the task depends on specific MCP behavior, version of a tool, file existing, etc. — add a pre-flight section that tests those FIRST and halts cleanly if they're not there.
8. **Add reference-data pointers.** If existing files/docs in the workspace make the task easier (schemas, prior outputs, design docs), point to them by absolute path.
9. **Assemble + show the user the /goal block** for them to paste.

Use the template in `reference/template.md` as the assembly skeleton.

## Critique workflow

When the user pastes a draft `/goal`:

1. **Run** `python scripts/validate_draft.py --input <path_or_stdin>` (or do its checks mentally if scripting isn't available).
2. **Report missing components** by name (end state / stated check / constraints / scope bound / abort conditions).
3. **Flag anti-patterns** (vague conditions, implicit verification, scope creep, multiple goals). See `reference/anti_patterns.md` for the canonical list.
4. **Propose specific rewrites** rather than vague advice. If the end state says "tests pass", suggest "the command `pytest tests/ -x` exits with code 0".
5. **Show the corrected block** at the end.

## Output discipline

- **Always end with the assembled `/goal` block in a code fence** so the user can copy-paste. No additional text inside the fence.
- **Default block format**: the structured form in `reference/template.md`.
- **For trivial goals** (single sentence sufficient), use the compact form — but still call out end state + check + constraints explicitly.

## When the user has access to /goal but you're not sure how it works

Reference: https://code.claude.com/docs/en/goal. The harness was released in v2.1.139 (May 11, 2026). Don't fabricate behavior — if the user asks a mechanic-level question you don't know, say so.

## Self-discipline

- **Don't write `/goal` blocks for tasks that don't need autonomy.** If the task is "explain X" or "what is Y" — that's a regular prompt, not a /goal. /goal is for multi-turn work where the user wants Claude to keep working without intervention until the condition holds.
- **Never invent abort conditions that don't apply.** Each abort should map to a real failure mode the user has reason to fear.
- **Push back on shoddy specifications.** A weak /goal wastes the user's time and tokens. Better to interview them than ship a vague block.

## Files

```
goal-prompt-author/
├── SKILL.md (this)
├── README.md
├── reference/
│   ├── three_components.md       (the canonical structure, deep)
│   ├── anti_patterns.md          (10 common mistakes + fixes)
│   ├── examples.md               (real-world /goal blocks, well-formed)
│   ├── verification_recipes.md   (how to write "stated check" for different langs/tools)
│   └── template.md               (the assembly skeleton)
└── scripts/
    └── validate_draft.py         (parse a /goal draft, score it, report gaps)
```
