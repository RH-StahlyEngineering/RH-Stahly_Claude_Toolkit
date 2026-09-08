---
name: gh-issue-batching
description: Use when a GitHub repo's open issues need prioritizing and grouping into development sessions, arcs, or milestones — a backlog has piled up unscheduled, someone asks to batch/consolidate/organize issues into workstreams, or a Superpowers cycle is about to be pointed at a backlog.
---

# GitHub Issue Batching

## Overview

Cut a repo's open issues into the fewest development arcs that are still safe to run. "As big as possible" is bounded by two real limits — where a later design consumes an earlier phase's output (feedback flow), and how much a human can review well at one sitting (the review bottleneck) — never by preference or by label taxonomy.

## Method

1. **Scope.** Decide which workstream this batching serves (e.g. reusable codebase vs. project delivery — they are different backlogs even in one repo). Inventory with `gh issue list --state open --limit 100 --json number,title,labels,milestone`. An issue serving both workstreams gets moved deliberately, with a note, not duplicated.
2. **Triage before grouping.** Any issue plausibly already satisfied (superseded by merged work, "may already be done", pre-dating a rework) gets verified against the code and closed-with-evidence FIRST. Grouping an unverified inventory schedules solved work. Output: a close list with evidence pointers, plus the surviving inventory. **Verification method — see "Triage mechanics" below; a verdict reached from issue text alone is not a verdict.**
3. **Classify each survivor** on two axes:
   - *Dependency:* does its design consume another issue's output? An artifact that does not exist yet cannot be designed against.
   - *Execution mode:* independent fix (no open design questions) / design-coupled feature chain / measure-then-decide (evidence-gated — structurally incompatible with fire-and-forget).
4. **Cut arcs.** Fuse aggressively within a mode; never across modes:
   - Independent fixes → one big autonomous sweep arc, parallelizable across subagents.
   - A feature chain → one fused arc with named internal human checkpoints at every design-consumes-output seam. Later phases get their own short brainstorm once the input artifact exists — never pre-spec a phase whose inputs don't exist yet. Days of autonomy live inside phases, not across seams.
   - Evidence-gated work → its own arc, brainstormed last, after the measurements it needs exist.
   - Urgent delivery-gating work stays small and ships first; it is the one arc never maximized.
5. **Sequence and record.** One milestone per arc; the milestone description states the execution mode and checkpoints. A mixed-priority issue sits on the milestone its gating half belongs to, with the deferred tail recorded in the index — never split into two issues unless the author asks. Rewrite (don't delete) the repo's index issue as the arcs index with per-arc closure evidence. Apply in batches: `gh issue edit N1 N2 N3 --milestone "Arc 1: ..."`.

## Triage mechanics (step 2)

Every triage verdict is one of three, and each carries evidence:

| Verdict | Means | Evidence required to record it |
|---|---|---|
| `SATISFIED` | Close it | Merge commit SHA / PR number **plus** the code or test that demonstrates the behavior now exists |
| `PARTIAL` | Stays open, body rewritten to the remainder | Which sub-item merged work already answers, and what survives |
| `OPEN` | Survives to step 3 | The unfixed line or absent mechanism, read on the integration branch |

Establish the merge baseline before any verdict: `gh pr list --state merged`, `git branch --merged <integration branch>`, `git log <branch> --oneline`. Work hiding on an unmerged branch is not satisfied work, and an inventory verified against the wrong branch is verified against nothing.

Then, per issue, prefer positive evidence over absence of evidence:

- **Probe the artifact the issue itself names.** Issue bodies usually cite a file, symbol, or line — read *that* on the integration branch. Confirming the unfixed original line still exists is a far stronger `OPEN` than a null grep, which only proves your vocabulary didn't match.
- **Read the API surface, not the grep count.** "A module with that name exists" is not "the mechanism exists" — a pull-only object store greps identically to a delivery layer.
- **Watch for a predicate with no producer.** State checks, config flags, and enum members for a feature routinely land before the feature; they make an unbuilt thing grep as built. Trace to whatever is supposed to *write* the state.
- **Never take the index issue's own word for it.** The backlog index records a prior run's conclusion, not current truth; re-derive against code. Same for checkboxes in a plan or checklist — they lag code in both directions, so treat agreement between code and checkbox as a second independent signal, not as the signal.
- **Scan closed issues too** for a duplicate whose merged work satisfies an open one.

**Fan out when the inventory is big enough to flood context** — roughly a dozen-plus issues, or a history deep enough that per-issue archaeology means reading many diffs. Dispatch one subagent per issue (or per small cluster), each returning only the verdict plus its evidence pointers. This is context economy, not capability: the orchestrator needs the verdicts, not the diffs. Below that threshold, verify inline — fan-out costs more than it saves.

## Required deliverable shape

For each arc: name, member issues in order, execution mode, where human review sits, and **why the arc is not bigger**. Plus: the triage close-list, the mechanics commands run (or ready to run), and any assumption that would swap membership if wrong.

## Common mistakes

| Mistake | Fix |
|---|---|
| Grouping before triage | Verify suspect issues first; close with evidence |
| Triaging from issue text, titles, or the index's own claim | Verify against code on the integration branch; re-derive, don't inherit |
| Treating a null grep as proof a feature is absent | Read the line the issue names; a predicate with no producer greps as "built" |
| Serial archaeology across a large backlog | Fan out one subagent per issue; collect verdicts + evidence, not diffs |
| A binary done/not-done triage | `PARTIAL` is a verdict: keep it open, rewrite the body to the remainder |
| Promising "go and wait days" over a design-coupled chain | Name the checkpoints at each design-consumes-output seam |
| Evidence-gated spikes fused into an autonomous arc | They stall or steamroll the decision; separate arc, last |
| Grouping by area/label/technical layer | Group by shared mental model and dependency |
| Deleting the backlog index issue | Rewrite it as the arcs index |
| Splitting a mixed-priority issue in two | Milestone by gating half; record the tail in the index |
