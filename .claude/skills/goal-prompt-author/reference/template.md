# Assembly template

## ⚠ Hard limit: 4000 characters

The `/goal` condition is capped at 4,000 characters. The structured form below can blow past that. **For complex tasks, prefer the COMPACT form + a reference to an external doc.**

Run `python scripts/validate_draft.py --input <draft>` before pasting to confirm length is OK.

---

## COMPACT form (default — fits under 4000 chars easily)

For most tasks. Aim for ~1000–2500 chars.

```
/goal <one-sentence task>.

End state: <verifiable condition>. Verify: `<exact command>` exits 0.

Methodology: follow <absolute/path/to/design.md> exactly. Pre-flight: run `<single setup-check command>` first; halt if it fails.

Constraints:
  - <thing NOT to touch>
  - <thing NOT to touch>
  - <thing NOT to touch>

Stop after <N> turns OR <X> minutes. Abort if: <specific failure mode>; <specific failure mode>.
```

That's ~600 chars of skeleton + your content. Plenty of room under 4000.

---

## STRUCTURED form (only when complexity warrants — watch the char budget)

```
/goal <one-sentence summary>

VERIFIABLE END STATE
  <One specific, checkable end state>
  Verify with: `<exact command>`
  When that command exits 0, the goal is met.

PRE-FLIGHT (only include if tool-fragile)
  1. <thing to check before starting>
  If pre-flight fails, halt and report.

ARCHITECTURE (only include if multi-phase)
  Follow <absolute/path/to/design.md> exactly. <— one line. Don't inline phases.

REFERENCE DATA (only include if it saves runner work)
  - <path to existing schema/doc>

CONSTRAINTS (no exceptions)
  - <constraint>
  - <constraint>

SCOPE BOUND
  Stop after <N> turns OR <X> minutes wall-clock.

ABORT CONDITIONS
  - <failure mode> → halt
  - <failure mode> → halt
```

## When the structured form blows past 4000 chars

1. **Inline ARCHITECTURE → external file**: replace 500-char phase descriptions with `Follow /path/to/design.md`. Saves ~450 chars.
2. **Inline REFERENCE DATA → bulleted paths only**: list paths, not summaries.
3. **Verify command → `python -c "..."`** instead of multi-line scripts.
4. **Drop PRE-FLIGHT if not tool-fragile.**
5. **Drop ARCHITECTURE if single-phase.**
6. **3-5 constraints**, not 10. Group related ones.
7. **3 abort conditions**, not 8. Drop generic ones.

## Assembly checklist

Before showing the user the final `/goal` block:

- [ ] **Length ≤ 4000 chars** (run `validate_draft.py`)
- [ ] End state is measurable (specific file/exit code/output)
- [ ] Stated check is a literal command
- [ ] At least one constraint listed
- [ ] Scope bound exists
- [ ] At least one abort condition that maps to a real failure mode
- [ ] Single end state (not a multi-goal compound)
- [ ] No aspirational language
- [ ] If task depends on tooling: pre-flight included (or referenced via a single command)
- [ ] If task is complex: architecture referenced (NOT inlined) via design-doc path
