# dirty-fix

Prove a concept fast on minimal real data, then hand the rigorous pipeline a
**machine-checkable acceptance criterion** instead of a paragraph of English.

Rigorous agentic pipelines build the wrong thing correctly. This skill establishes
*what correct means*, in code, before that money gets spent.

---

## Install

### 1. Get the skill

Global (all projects):

```
.claude/skills/dirty-fix/
```

Or project-local: `<project>/.claude/skills/dirty-fix/`.

### 2. Register the escort hook — REQUIRED, one time per machine

```
python .claude/skills/dirty-fix/scripts/df.py install-hook
```

**This step is not optional and is not part of the skill files.** Hooks live in
`~/.claude/settings.json`, which is deliberately excluded from skill sync — so pulling
the skill cannot register it for you.

What it does: adds a `SessionStart` hook (`startup|clear|compact`) that detects sealed
bundles and hands them to the next session. Without it, bundles seal correctly and then
sit there. Nothing breaks; the handoff just never happens, and stale bundles are how
this whole approach quietly stops working.

The installer backs up `settings.json` first, validates the JSON before and after
writing, and is safe to run twice.

### 3. Verify

```
python .claude/skills/dirty-fix/scripts/df.py doctor
```

`escort hook   registered` means you're done.

**Requirements:** Python 3.8+, git. No third-party packages.

---

## What it produces

An **acceptance bundle**, split by durability:

```
<repo>/dirty-fix/<slug>/          committed — spec and gate
  acceptance.md   check.py   metrics.json   coverage.md   fixture.lock

~/.dirty-fix/<project-id>/<slug>/ never committed — bulk and dirt
  fixture/  holdout/  expected/  work/  profile.json
  rejections.jsonl  appendix-hacks.md
```

The contract:

```
python check.py --candidate <output>     exit 0 = acceptable, exit 1 = not
```

Runnable by anyone, on any machine, with this skill uninstalled.

Dirty code lives outside the repo and is deleted on consumption — it cannot be
committed, reviewed, or read by a later design session. That boundary is structural,
not a matter of instructions.

---

## How it goes

| Phase | What happens |
|---|---|
| 0 Frame | one sentence, judgment method, disposition (`answer` vs `feature`), archetype |
| 1 Reduce | **profile production first**, select typical + tail, cut a holdout, diff coverage |
| 2 Loop | vibe-code to an output the human approves; every rejection logged |
| 3 Harvest | each fix writes its check *immediately*, validated against the failure that caused it |
| 4 Holdout | run once against unseen data — catches an unrepresentative fixture cheaply |
| 5 Escort | seal, verify no implementation leaked into the spec, hand off |

Exit modes: `SEALED`, `PARTIAL`, `ABANDONED`, `NOT_REDUCIBLE`. All produce a bundle — a
failed dirty-fix that names the wall is worth more than its cost.

---

## Why the fixture won't lie to you

The classic spike failure is "proved it on 5k rows; the 40M had three format variants
the 5k didn't." Three mechanisms, none of which rely on foresight:

- **Profile before reducing.** Never ask what belongs in the fixture — people answer
  from memory and memory omits the thing that later breaks. Scan production, inventory
  it, then diff the fixture against the inventory. Absent coverage is listed
  mechanically.
- **Typical + tail.** A pleasant fixture proves a pleasant subset. Include the outliers
  the profile surfaced.
- **The holdout.** A second slice, never examined during the loop, run exactly once
  before sealing. If the dirty code explodes there, the fixture was unrepresentative and
  you learn it at dirty prices.

And the gate is **fixture-parameterized**: when production later reveals a case the
fixture lacked, add a fixture and a check. The spec extends rather than restarts.

---

## Commands

```
df.py status                 what's happening here (always run first)
df.py doctor                 environment + wiring check
df.py init <topic>           create a bundle
df.py profile <slug> <json>  record the production profile
df.py log <slug>             log a human verdict
df.py check-add <slug>       record a check (refuses without --validated-against)
df.py freeze <slug> <path>   freeze the approved output
df.py holdout <slug>         record the single holdout run
df.py seal <slug>            validate the gate and seal
df.py consume <slug>         mark escorted; deletes the dirty code
df.py abandon <slug>         terminal exit
df.py gc                     remove dirty code from terminal bundles
df.py export / import        portable bundle zip
df.py install-hook           register the escort hook
```

`DIRTY_FIX_HOME` overrides the store location. The store is keyed on the **git common
dir**, so bundles survive worktrees.

---

## Not for

Aesthetic or interactive questions — "what should this interface look like," "does this
feel right." There is no comparator for taste, and forcing one into `check.py` is how a
gate stops meaning anything. Subjective criteria can be *declared* in the spec for human
sign-off, but they are never gated. For genuinely design-shaped questions, use a
prototyping skill instead.
