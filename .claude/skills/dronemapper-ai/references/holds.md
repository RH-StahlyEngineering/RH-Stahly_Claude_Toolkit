# Holds: reason code → cause → fix

Read the hold reason from the latest `needs_attention` job event (`references/commands.md`)
and the hold occurrence's evidence. Every fix below is a production change: RH approves it.
Staff RPCs take `p_expected` = the `identity` object from `job_state_identity`, not the whole
state.

| Reason code | What it meant on 22a9ac25 | Fix that worked | Notes |
|---|---|---|---|
| `INFRA_PREFLIGHT_FAIL: confidence_disk` | Floor projection (~694 GiB) above free space on D: | Set `BRIDGE_STEP_SCRATCH_ROOT` (User scope, puget-2) and make sure intake preflight passes it (#771); then re-run | Retry may refuse `RUN_PREDATES_THRESHOLDS` on a never-processed run: use `rerun_from_start` |
| upload check `control_file` "N targets, we need at least 3" | JXL points stored WGS84-only (no `<Grid>`) | Add `<Grid>` N/E/Elevation (metres) per point from the file's own CRS + GEOID18; customer re-attaches, or staff replace at `needs_attention` only | #769; `replace_control_file` RPC refuses `awaiting_data` |
| `MarkerRefinementRequired` | Target in shadow, never detected | Pin every target by hand: `marker-pins.md` (sub-agent picks, saddle refine, RH review on the pin page, write into `.snapshot.psz`, update `bytes`, Retry) | `pipeline-ops.md` procedure; ask the operator before resuming over their marker work; #673 is the supported route |
| `BATCH_END_UNCONFIRMED` (depth maps, "not enough space") | Depth maps filled D: | Move `<job>.files` to a roomy share with an admin `mklink /D` at the old path; Retry resumes at depth maps | Remove the target yourself after archive (reclaim won't follow it); #682 |
| `BATCH_RETRY_LOOP` "Access is denied" on `project.zip` | Puget 1's worker account lacked share/NTFS rights through the link | `Grant-SmbShareAccess` + `icacls /T` for `SEAENG\puget-1`; `R2R:1` on Puget 1; Retry | `nas-smb.md` |
| `QC_HOLD_SECOND_OPINION_UNAVAILABLE` ("CLI exited 1") | `second-opinion-home` login expired | RH re-logs in there (`CLAUDE_CONFIG_DIR` set, `claude`, `/exit`); test the isolated call; Retry | #833 (OAuth token), #834 (warning) |
| bridge `DISK HOLD` (no claims) | Deliverables on D: pushed it under the 50 GiB floor | Free space under the repo's procedures (post-delivery reclaim, or RH-approved removal) | Floor is fixed in code; don't change it |
| `WORKER_EXCEPTION` MemoryError / SSLEOFError during delivery | R2 upload with no retry config, 80 connections | Fixed by #848 (retries, 128 MiB parts, 16 connections, checksum when_required) | A Retry re-uploads from zero |

## Before any Retry

1. `git fetch`; confirm the job is `needs_attention` with no lease.
2. Make the fix and verify it (test call, `Test-Path`, re-run the failing probe).
3. Call the RPC with a reason naming the fix and "approved by RH".
4. Watch the next bridge dispatch line: `resume at <step>`, `snapshot valid`, or `fresh`
   (fresh means realignment; stop and check why).
