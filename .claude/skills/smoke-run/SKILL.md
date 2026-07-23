---
name: smoke-run
description: Run cluster smoke tests of the Metashape pipeline on Puget — deploy a branch, carve alignment-viable photo datasets from an existing PSX + JXL, submit jobs safely, monitor multi-hour runs via log tails, archive evidence per attempt, judge PASS/FAIL from result envelopes, and keep a findings ledger for developer hand-off. Use when the user asks to smoke test a PR/branch on the cluster, run SMOKE_TEST.md, validate the pipeline end-to-end on real photos, prepare smoke datasets, or diagnose a cluster run failure. Triggers - "smoke test", "run the smoke checklist", "test this PR on Puget", "carve a dataset", "why did the batch die".
---

# Smoke Run

Operate as a TESTER, not a developer: default to **document-only** — record
root causes with file/line pointers in a findings ledger; do not patch the
code under test unless the operator explicitly authorizes test-enablement
patches (and then revert them at the end, keeping only the findings).

Read `references/run-mechanics.md` BEFORE the first cluster command — it holds
the PID-safety rule (stop_cluster kills the operator's GUI), submit flags,
monitoring patterns, cleanup checklist, envelope PASS criteria, and the
cycle-time budget. Read `tasks/lessons.md` too.

## Workflow

1. **Deploy** — pull the branch, purge `__pycache__`, restart the cluster
   (PID-safe, per run-mechanics). Verify with an instant preflight test before
   committing to a long run.

2. **Datasets** — carve from an existing aligned PSX + JXL with
   `scripts/carve_dataset.py`:
   - `sessions` mode FIRST: it prints per-session extent, spacing, and
     pass structure, flagging `SINGLE-PASS - NEVER THIN` sessions.
   - Aligned set: `session` mode with contiguous sessions covering the wanted
     targets, unthinned. Never select by target-proximity alone (disconnected
     islands align at ~45%).
   - No-target set: `far` mode (`--min-dist 500 --limit 20`).
   - Strip the JXL to the wanted targets with a small ElementTree edit; JXL
     Grid values are METERS regardless of DisplaySettings units.
   Keep datasets OUTSIDE `C:\metashape-root` (exercises staging).

3. **Cheap tests first** — run every instant/preflight assertion before any
   multi-hour run; an empty console log or import error found here saves a
   4-hour cycle.

4. **Long runs** — launch detached with log redirection; arm two tail-based
   monitors (runner stderr + `worker-stderr.log` for APPE step boundaries).
   Verify the front-loaded evidence in the first ~10 minutes (sampling
   envelope, alignment check, marker envelopes), then let it run.

5. **Per attempt** — archive logs + envelopes into
   `C:\smoke\evidence\<test>-attemptN-<failtag>\`, then perform the 4-item
   cleanup (PSX, .files, staged images, output dir) before resubmitting.
   Kill runs immediately when an expensive step enters an abort-retry loop.

6. **Judge** — assert PASS/FAIL from the `result_*.json` envelopes against
   the table in run-mechanics, never from console vibes. Deviations are
   findings, not noise.

7. **Findings ledger** — one markdown file, updated the moment anything is
   learned: numbered findings (symptom → root cause with file:line →
   disposition), a status table per test, validated-vs-unvalidated status for
   any authorized patch, and open items. Commit it to the repo
   (`tools/puget/SMOKE_FINDINGS_<date>.md`); it is the developer work order.

8. **Hand-off** — zip `C:\smoke\evidence\`, preserve any expensive artifacts
   (a built dense cloud is 3.5 h of compute — copy the staged PSX out of
   metashape-root before cleanup), revert authorized patches, verify the
   diff against the shipped commit is empty, commit findings.

## Judgment rules

- One identical resubmit is a legitimate retry for known-stochastic gates
  (marker frame-match); two failures of the same signature = stop, document,
  move on.
- When a step fails, decide deliberately: is it the code, the dataset, or the
  test expectation? Each has a different remedy (finding / re-carve / amend
  runbook), and today's run had all three.
- Track which checklist items each attempt PROVES even when the run fails
  overall — a failed run that proves 6 gates is a successful test.
