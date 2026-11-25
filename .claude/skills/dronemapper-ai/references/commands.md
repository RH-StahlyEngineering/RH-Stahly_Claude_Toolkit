# Commands that worked (Puget 2)

## Supabase, read-only (one-line SQL through supabase.cmd)

```bash
S=/c/tools/supabase-cli/node_modules/.bin/supabase
$S db query --linked --project-ref nyhfimkuazzuxojzqzka "select status, to_char(updated_at at time zone 'America/Denver','MM-DD HH24:MI') u from jobs where id='<job>'"
```
Collapse multi-line SQL to one line (`" ".join(sql.split())`) or pass `-f <file>`.
Useful tables: `jobs`, `job_events`, `job_upload_checks`, `job_upload_generations`,
`job_post_delivery`, `job_hold_occurrences`, `worker_heartbeats`, `job_transitions`.

## Staff RPCs (service key; production change, RH approves)

```bash
U=$(powershell -NoProfile -c "[Environment]::GetEnvironmentVariable('BRIDGE_SUPABASE_URL','Machine')" | tr -d '\r')
K=$(powershell -NoProfile -c "[Environment]::GetEnvironmentVariable('BRIDGE_SUPABASE_SERVICE_KEY','Machine')" | tr -d '\r')
curl -s -X POST "$U/rest/v1/rpc/job_state_identity" -H "apikey: $K" -H "Authorization: Bearer $K" -H "Content-Type: application/json" -d '{"p_job":"<job>"}'
# then, with p_expected = the "identity" object from above:
curl -s -X POST "$U/rest/v1/rpc/retry_from_failed_step" -H "apikey: $K" -H "Authorization: Bearer $K" -H "Content-Type: application/json" \
  -d '{"p_job":"<job>","p_expected":{"kind":"hold_occurrence","occurrence_id":"<id>"},"p_reason":"<fix>. Approved by RH.","p_actor":"service:<session> for RH"}'
```
Keep backslashes out of `p_reason` (the JSON breaks). `rerun_from_start` takes the same
arguments.

## Logs

- Bridge: `C:\metashape-root\bridge-scratch\bridge.log` (dispatch lines, holds, liveness
  every minute, effective configuration each cycle).
- Pipeline: `C:\metashape-root\bridge-scratch\<job>\pipeline.log` (step boundaries only).
- Worker output: `C:\metashape-root\worker-stdout.log` (RunScript output, ExportPointCloud
  block saves; not flushed in real time).
- Run results: `D:\metashape-root\projects\output\job_<job>\result_*.json`,
  `checkpoint_residuals.jsonl` (until the reclaim; then on the NAS archive).

## Metashape network state

`scripts/workers.py` (run as `metashape.exe -r <path>`) writes the worker list and batch list
to `C:\t\monitor\workers.json`: per worker cpu/memory %, state, task, progress, errors; per
batch the task title, progress and workitems done/running/waiting/failed. Batch
`remaining_time` is always 0: compute an ETA from the progress rate.

## Puget 1 from Puget 2 (no admin)

Legacy WMI works: `Get-WmiObject Win32_PerfFormattedData_PerfOS_Memory -ComputerName 10.7.76.41`
(commit, available MB), `Win32_LogicalDisk`, `Win32_Process`. CIM, WinRM, typeperf and `C$`
are refused.

## R2 (bridge credentials, read-only unless RH approves)

Load `BRIDGE_R2_ENDPOINT/ACCESS_KEY/SECRET_KEY/BUCKET` (User then Machine scope) and use the
bridge venv's boto3. Upload progress: `list_multipart_uploads` + `list_parts` under
`org/<org>/jobs/<job>/outputs/<attempt>/`.

## Second-opinion check

```powershell
# exact isolated environment; expect exit 0 and "OK"
$env:CLAUDE_CONFIG_DIR='C:\metashape-root\bridge-scratch\second-opinion-home'
'Reply with the single word OK.' | claude -p --output-format text --tools "" --strict-mcp-config --disable-slash-commands
```
(DEPLOY.md recommends `cmd` for the hand test because PowerShell 5.1 can drop `""`.)

## Vercel request log (customer's browser activity)

`cd web && vercel logs --project dronemapper-web --environment production --since 2h --json`
(needs `vercel login` once). `/api/upload/manifest`, `/verify`, `/check` mark the upload stages.

## Deploying a bridge fix

1. Merge the PR once its checks pass. No posted result overrides a failing check (ADR 0005);
   if a check fails for a reason outside the change (the Vercel check, Actions minutes),
   report it to the CI owner instead of merging around it.
2. `git diff --stat HEAD origin/master -- pyproject.toml 'requirements*.txt' tools/bridge/config.py`;
   import the bridge modules from a detached worktree of origin/master with the bridge venv.
3. `git pull --ff-only origin master` in `C:\Agisoft_Coding`; wait for the next 5-minute
   cycle to log `cycle outcome` with no Traceback.
