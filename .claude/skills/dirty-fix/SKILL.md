---
name: dirty-fix
description: Use when a concept needs proving fast on minimal real data before anyone builds it properly, or when an expensive rigorous implementation is about to begin from a spec that has never been validated against actual output. Triggers on "dirty fix", "quick and dirty", "just make it work", "prove it works first", "vibe code this", "I need to see output before we build this", "spike this", "is this even possible".
---

# Dirty Fix

## Overview

Produce an **acceptance bundle**: a machine-checkable definition of done, derived by
vibe-coding to an output a human approves, on the smallest real data that can prove it.

The bundle — not the code — is the deliverable. The code is deleted.

**Core principle:** rigorous implementation pipelines build the wrong thing correctly.
This skill establishes *what correct means*, in code, before that money gets spent.

**Announce at start:** "I'm using the dirty-fix skill to prove this concept before it
gets built properly."

## The deliverable

```
<repo>/dirty-fix/<slug>/          committed — spec and gate
  acceptance.md   check.py   metrics.json   coverage.md   fixture.lock

<store>/<project-id>/<slug>/      never committed — bulk and dirt
  fixture/  holdout/  expected/  work/  profile.json
  rejections.jsonl  appendix-hacks.md
```

The contract that makes the whole thing work:

```
python check.py --candidate <path>     exit 0 = acceptable, exit 1 = not
```

Runnable by anyone, on any machine, with this skill uninstalled.

## First run on a new machine

The skill is complete when pulled, but **the escort hook is a separate one-time
registration** — it lives in the harness settings file, which is not part of a skill.
Without it, bundles seal correctly and then sit there: nothing hands them to the next
session, which is the half that stops them rotting.

`df.py status` says so when it isn't registered. When you see that warning, tell the
human what it is and offer to run:

```
python <skill>/scripts/df.py install-hook
```

It backs up `settings.json`, validates the JSON before and after writing, and is
idempotent. Requires Python 3.8+ and git.

## Always run first

```
python <skill>/scripts/df.py status
```

Announce the state before doing anything else. Then:

| Situation | Action |
|---|---|
| A `LOOPING` bundle exists for this project | Report it. Ask: resume / start new / abandon. **Never silently start a new one.** |
| A `SEALED` bundle exists, unconsumed | Report it. Ask whether to escort it before starting new work. |
| No bundle, clear frame from the user | Phase 0 |
| No bundle, vague ask | Phase 0 — questions, not code |
| Running inside a Superpowers worktree | See "Sub-spike mode" below |

## Phase 0 — Frame

Establish three things. Do not write code, do not touch data, until all three exist.

1. **The sentence.** *This input* → *this output*. If it can't be said in one sentence,
   the concept isn't ready to prove.
2. **Judgment method.** How will the human decide it's right — visually, numerically,
   by opening it in a specific tool? This determines whether harvest can produce a gate
   at all.
3. **Disposition.**
   - `answer` — the output is the deliverable. No code will live. **No escort.**
   - `feature` — code will exist afterward and be maintained. **Escort required.**

Then classify the archetype. It sets the default gate:

| Archetype | Question | Default gate |
|---|---|---|
| `transform` | artifact → artifact | output invariants / tolerance match |
| `extract` | unstructured → structured facts | precision + recall vs. hand-labeled set |
| `decide` | input → label or threshold | confusion matrix including explicit negatives |
| `integrate` | does this external system behave as needed | recorded interactions, contract assertions |
| `perform` | does this fit a time/memory budget | budget assertion + scale caveat |

If none fit, record the new archetype in `metrics.json` and proceed. The catalog grows
by use.

Declare **non-determinism** now (LLM calls, sampling, wall-clock, network ordering).
It picks the comparator mode and is miserable to discover during harvest.

`df.py init <topic> --disposition <d> --archetype <a>`

## Phase 1 — Profile, reduce, hold out

**Read `references/fixture-minimization.md` before this phase.** It contains the
protocol, the reduction strategies, and the NOT-REDUCIBLE test.

The shape of it:

1. **Profile production first.** Never ask the human what belongs in the fixture — they
   will forget exactly the thing that later breaks. Scan the full input cheaply and
   inventory it. Record with `df.py profile`.
2. **Select typical + tail.** The clean specimen is how spikes lie. Include the outliers
   the profile surfaced.
3. **Cut a holdout** from a different region/tenant/period. It is never examined during
   the loop.
4. **Diff fixture against profile.** Everything in the inventory and not in the fixture
   is auto-listed as absent coverage. This converts unknown-unknowns into a written list
   mechanically.
5. **Set the iteration budget.** Default 90 seconds per full loop. The fixture is
   correctly sized when one iteration fits inside it.

Fixtures are **derived from real production input, never synthesized.** No real data
exhibiting an edge case means that edge case goes in "cannot prove" — it does not get
invented.

## Phase 2 — The loop

Fast, cheap, disposable. Dirty code lives in `work/` in the store, outside the repo,
where it cannot be committed, reviewed, or read by a later brainstorm.

**Prohibitions.** Each one is a place the loop stops being dirty:

- one file until it physically cannot be
- no tests, no abstractions, no error handling, no config, no argument parsing
- no refactoring, ever, for any reason
- hardcode paths, constants, magic numbers
- cheapest capable model

**Every iteration prints, next to the output:** the archetype's key counts, the delta
from the previous iteration, and the current status of every locus a previous rejection
flagged. The human's verdict is only as sharp as what they were shown.

**Every rejection is logged immediately:**

```
df.py log <slug> --verdict reject --observation "eaves clipped at roof edge" --locus "roof perimeter"
```

**Every fix writes its check immediately** — see Phase 3. Do not defer this.

**Budget:** if an iteration exceeds the budget, shrink the fixture. Never optimize the
dirty code to hit it. Checkpoint with the human every 5 iterations or 15 minutes:
continue / shrink / abandon.

## Phase 3 — Harvest, continuously

**Read `references/harvest-protocol.md` before the first fix lands.**

Harvest is not a phase at the end. When a rejection gets fixed, that is the moment:

1. Write the check that would have caught the rejection.
2. **Validate it against the previous iteration's output**, which is sitting right there
   and is a real failure rather than a synthetic mutant. A check that does not fail on
   the output that provoked it is dead — rewrite or delete it.
3. Record it: `df.py check-add <slug> --id ... --mode ... --from-rejection <n>`

This is why harvest never becomes a chore landing exactly when the human wants to stop,
and why mutation testing is nearly free.

Also required before sealing:

- **negative checks** — what must *not* appear. Without them the gate passes an
  implementation that labels everything.
- **gated vs. declared-subjective split.** Anything that cannot be asserted is named in
  `acceptance.md` as requiring human sign-off, and `check.py` emits review artifacts at
  exactly the loci the human cared about. Subjective criteria are *additional*. The
  moment taste leaks into `check.py`, the gate stops meaning anything.
- **the closing question, verbatim:**

  > Here are the N checks. If a future implementation passes all of them and you never
  > see its output, is that acceptable?

  A "no" means the metrics are incomplete. Keep eliciting.

## Phase 4 — Holdout

Run the dirty code against the holdout **exactly once**, before sealing. Not to judge
output quality — to detect crashes, format surprises, and assumptions the fixture
silently satisfied.

Iterating against the holdout is leakage and destroys its only property. If it fails,
that is a specific named gap: return to the loop, then cut a *new* holdout.

`df.py holdout <slug> --result pass|fail --notes "..."`

The result goes in the bundle either way. Passing is evidence; failing that was never
run is a lie.

## Phase 5 — Seal and escort

`df.py seal <slug>` refuses unless: checks exist, each has been validated against a real
failure, negative checks exist, the holdout has been run, and coverage is recorded.

Then write `acceptance.md` from `references/acceptance-template.md`, and **self-check it
for leaks**: any technique name, library name, or algorithm name is a defect. Data
formats and interfaces are permitted; solutions are not.

| Belongs in `acceptance.md` | Belongs in `appendix-hacks.md` |
|---|---|
| "raw Z fails on slopes over 15%" | "used a HAG filter, k=8" |
| "returns are unordered per pulse" | "sorted in memory, won't fit at full scale" |
| what must be true | how it was made true |

**Then verify the destination exists.** Check that the rigorous pipeline the human is
being escorted into is actually installed for this project. Escorting someone into a
plugin that is not installed is a dead end that looks like success.

**Then the transition.** The exit line is not "you can now run X":

> The bundle is verified. Type `/clear` — I'll pick it up from the other side.

`/clear` fires SessionStart, which drops the dirty context and injects the handoff. The
human's entire required action is one keystroke.

For `answer` disposition: no escort. Report the output location and close.

## Exit modes

All of them produce a bundle. A failed dirty-fix that names the wall is worth more than
its cost.

| Mode | Meaning |
|---|---|
| `SEALED` | checks green, holdout run, ready to escort |
| `PARTIAL` | accepted with named gaps; gaps become open questions downstream |
| `ABANDONED` | no working output; report the approach classes tried and what blocked them |
| `NOT_REDUCIBLE` | the phenomenon only exists at full scale or under real concurrency; fixture minimization fails by definition. Exit within ten minutes. |

`NOT_REDUCIBLE` is a good outcome delivered cheaply: *this cannot be proven small,
budget for proving it large.*

## Sub-spike mode

When invoked inside an existing implementation worktree, behavior changes:

- the store keys to the **main repo**, not the worktree
- refuses to write the in-repo half while the branch has uncommitted implementation work
- the bundle is marked `sub-spike`
- **the escort returns to the current implementation — no `/clear`.** Clearing would
  discard the implementation context the human is in the middle of.

## Common rationalizations

| What gets said | Reality |
|---|---|
| "It works — just clean it up and ship it" | The workarounds hold at fixture scale by construction. The dirty code is not a template, is not a reference, and does not graduate. Escort instead. |
| "Let's keep going here, I don't want to lose the context" | Losing that context is the mechanism. It is what stops the rigorous design from converging on the hack. |
| "I'll start the real work later" | Bundles expire against source mtime and fixtures go stale. Escort now, or mark disposition `answer` and close honestly. |
| "This is too small to build properly" | Then it is disposition `answer` and there is nothing to escort. The code still does not graduate. Those are the two options. |
| "Just show me how you did it so I can adapt it" | That is the appendix, and reading it before the design is the exact thing the boundary prevents. Available after a design is approved. |
| "Skip the profile, I know what's in the data" | The profile costs a scan and catches what you forgot. What you forgot is the thing that sends this back to the drawing board. |
| "The fixture is obviously representative" | Then the holdout will pass and cost you one run. Run it. |
| "Just peek at the holdout to see if it's working" | Iterating on the holdout destroys the only property it has. Cut a new one or admit it was consumed. |
| "Write the checks at the end, we're on a roll" | At the end the counterexamples are overwritten and the human wants to stop. The check gets written when the fix lands. |
| "It's close enough, seal it" | A gate whose checks were never validated against a real failure is decoration, and it will launder a false sense of safety through an expensive build. |

## Red flags

Stop and restart the phase if you notice:

- writing dirty code before the fixture exists
- the fixture chosen because it was convenient rather than because the profile pointed at it
- a rejection observed but not logged
- a fix landed without its check
- sealing with zero negative checks
- `acceptance.md` naming a library, algorithm, or technique
- the human asking to productionize the dirty code and you considering it
