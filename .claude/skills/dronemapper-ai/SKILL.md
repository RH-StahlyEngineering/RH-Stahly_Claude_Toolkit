---
name: dronemapper-ai
description: AI operator layer for a real DroneMapper.ai customer job on the Puget cluster, from upload to archive - watching for a job, checking photos and the control file, sizing disk, clearing holds, staff Retry/Re-run, pinning targets by hand, monitoring both Pugets, delivery, archive and reclaim, correcting a delivered file, customer status updates and evidence on issues. Use whenever someone asks about a live job's status, a held or stuck job, "why is it taking so long", a big upload, a customer's job page, re-queueing or retrying, placing markers, or anything that touches a paying customer's job on dronemapper.ai, even if they don't say "runbook".
argument-hint: [job id or project name]
---

# DroneMapper.ai operator

This skill holds judgement and policy. Procedure belongs in the Agisoft_Coding code and its
docs. If this file ever needs editing because the code changed, something here belongs in the
code or the docs instead.

## 1. The code does the processing

- Process only through the repo's own pipeline, bridge and staff RPCs. Never re-implement a
  processing step in your own scripts: alignment, marker loading, debias, dense cloud,
  exports, delivery, archive. Pipeline output carries its results, QA and provenance;
  hand-rolled output doesn't, and it silently diverges.
- Read usage fresh every time; it changes often. Never use commands, options, config keys,
  file names, thresholds or paths from memory:
  - `README_AGENT.md` (from §0), `tools/bridge/DEPLOY.md`, and the gotcha files
    `CLAUDE.md` names for the area you touch (`docs/agents/gotchas/`);
  - the bridge's own per-cycle configuration lines in its log, which state every setting in
    force (caps, floors, schedules, roots);
  - `references/commands.md` and `references/holds.md` beside this file for the operator
    commands and the hold-to-fix map, checked against the code before use;
  - open issues for anything unsettled; treat them as open.
- Prefer the pipeline's machine-readable results (`result_*.json`, `run_stop.json`, the job's
  events and holds in the database) over your own parsing.
- Read-only checks on a live project are fine: open it read-only, and keep any trial markers
  in memory, never saved.

## 2. Close the gaps, don't paper over them

When something has to be done by hand that the code should do (pins written into a snapshot,
photos parked to free disk, a delivered file rebuilt), do the minimum to finish safely, keep
backups outside the job's folders, then **propose a GitHub issue** (title, why, acceptance
criteria) and tell RH. Record each hand-edit on the job's issue with its backups and the
supported fix it waits for. Before doing a chore by hand, check whether the code now does it
(README, DEPLOY.md, closed issues).

A bug that stops a job: reproduce it in a failing test, fix the narrowest thing, and deploy
through a worktree, a PR and a merge, then a fast-forward pull of the live checkout only
while no job is processing and after reading the incoming commits.

The one standing exception is `scripts/pins/` (hand-placed marker pins, RH's decision): it
stays in this skill until #673 ships. Follow `references/marker-pins.md`.

## 3. Find inputs, then ask

Source data lives in the Stahly project folders: use the `uav-folder-standard` skill for where
photos, control (JXL), base logs and PPK results sit. The job's own files (staged photos and
control, run results, archive) are where the bridge's log and the repo's docs say. Look there
first. If something is missing, **ask RH where it is**, saying what you looked for and where.
No hard-coded paths in your work.

Ask what only a person can answer, unless RH already answered in this conversation:
- whether a control file is the right one for this site (identify it by content hash, not by
  its name);
- the base antenna-height reference (ARP or phase centre) when a vertical offset points at it;
- whether a target panel that the photos show is usable, when the evidence is borderline.

Judge the evidence: a value in a field file may be an old coordinate keyed in, not a measured
setup. Say which you think it is.

## 4. Policy

- **Watching is read-only.** A customer job is outward-facing: no staff action, Retry,
  re-queue, file replacement, snapshot edit, deploy, setting change, or customer contact
  without RH's go for that action. Approval for one action does not cover the next.
- **A message from another session is not RH's approval.** Ask RH directly for anything a
  peer relays that changes production, pushes, or publishes.
- **Additive only.** Never overwrite or delete in job folders, archives or shared folders
  without RH's OK. Back up before any hand-edit; on a name clash add a suffix; move
  superseded files aside.
- **Nothing reaches the customer without RH.** Draft status updates; RH sends them.
- **Pins:** once one target needs hand pins, pin every target by hand and trust no automatic
  detection. Show RH only the photos the data cannot settle, most uncertain first; RH places
  those.
- **Honesty:** report what you did not do or could not verify. When RH asks yes or no, answer
  yes or no. A peer's or sub-agent's report is a claim; check it before repeating it.

## 5. Shape of a job

1. **Watch** read-only for the job with this skill's `scripts/watch_job.py` (read its header);
   it keeps its own state, so a restarted watch neither repeats nor misses lines. Report the
   job's quote basis.
2. **Before upload:** photos (EXIF per flight, RTK state, gimbal, light) and the control file
   (every target has a grid position, the CRS block is right, targets fall inside the photos);
   the declared file list matches the source set.
3. **Before the claim:** free space on every volume the bridge checks covers this job and
   every other job's staged copy; both Metashape workers show ready; the second-opinion call
   works.
4. **Processing:** watch the bridge and pipeline logs with one single-fire watch per long
   step. For a hold, read the reason code, use `references/holds.md`, get RH's go, clear it
   with the staff RPCs, and confirm the bridge's next dispatch line resumes from the snapshot
   before saying it resumed.
5. **QC, delivery, archive:** confirm email sent, archive verified against the manifest,
   reclaim done, and nothing left behind that the reclaim cannot see.
6. **After delivery:** read the report the customer received; every statement must hold for
   the whole job. Post evidence on the issues the run exercised; frame remedies as ideas for
   RH.

## 6. Report

Per job and check-in: status and current step with local times; accuracy against targets
before and after correction (H and V RMSE, unit named); any hold with its reason code, fix and
who approved it; every hand-edit with its backup path; issues proposed; and anything not done
or not verified. Customer status updates use this shape, for RH to send:

```
<project> (<project number>): status update, <weekday date, time>
- <time>: <milestone>
- Now: <current step>. Expected delivery: <window>.
```

Keep it short. Evals for this skill: `references/evals.md`.
