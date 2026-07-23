# Puget Cluster Run Mechanics

Hard-won operational knowledge from the 2026-07-22 Build #1 smoke run (8 T4
attempts). Follow exactly; every rule here cost real hours or real data.

## Contents
- Cluster lifecycle (PID safety)
- Submitting jobs
- Monitoring long runs
- Per-attempt cleanup & archive
- Envelope PASS criteria
- Cycle-time budget

## Cluster lifecycle (PID safety)

`stop_cluster.ps1` kills ALL `metashape*` processes BY NAME — including the
operator's GUI session (this destroyed live operator work once). NEVER run it
without accounting for every PID first:

```powershell
Get-Process metashape* | Select Id,ProcessName   # expect exactly worker + server
```

If there are PIDs beyond the two `start_cluster.ps1` printed, they are the
operator's GUI — stop ONLY your own: `Stop-Process -Id <worker>,<server>`.

Restart the cluster after ANY worker-side code change (workers cache imported
modules) and purge bytecode first:

```powershell
Get-ChildItem -Path src, tools -Recurse -Directory -Filter __pycache__ | Remove-Item -Recurse -Force
```

Submitter-side changes (tools/puget/submit.py, src/runner/*) need no restart.

## Submitting jobs

- NO `--` separator: `metashape.exe -r tools\puget\submit.py --images ...`
  (the `--` reaches argparse verbatim and exits 2).
- Until finding F1 is fixed, export first:
  `$env:PYTHONPATH = 'C:\metashape-root\pylibs;C:\Agisoft_Coding'`
- Corridor / cross-target datasets need `--marker-tolerance 0
  --marker-maximum-residual 0.5` (defaults 50/5.0 detect pole cross-arms,
  miss real panels) unless finding F10 landed.
- Launch long runs DETACHED (they outlive any tool timeout):

```powershell
$p = Start-Process -FilePath 'C:\Program Files\Agisoft\Metashape Pro\metashape.exe' `
  -ArgumentList '-r','tools\puget\submit.py','--images','<DIR>','--jxl','<JXL>','--quality','draft','--job-id','<ID>' `
  -WorkingDirectory 'C:\Agisoft_Coding' `
  -RedirectStandardOutput 'C:\smoke\evidence\<ID>-console.log' `
  -RedirectStandardError  'C:\smoke\evidence\<ID>-stderr.log' -PassThru -NoNewWindow
```

## Monitoring long runs

- Do NOT poll PIDs from Git Bash (`kill -0`, `tasklist|grep` both gave false
  "exited"). Tail logs for terminal lines instead:

```
tail -f -n 0 <ID>-stderr.log | grep -E --line-buffered \
  "segment finished|step started|BATCH_RETRY_LOOP|abortBatch|Traceback|Run ended|All done"
```

- APPE emits NOTHING to the runner console for hours; its heartbeat is
  `C:\metashape-root\worker-stderr.log` (`orchestrator - INFO - Step N complete`).
- Abort-class step failures retry ~3-6x then abortBatch. If the failing step
  is EXPENSIVE (APPE re-runs its 104-min diagnostics per retry), kill the
  submit process immediately — do not wait out the retries.
- Kill leftover `tail` processes before zipping logs (they hold file locks).

## Per-attempt cleanup & archive (a fresh rerun REQUIRES all four deletions)

```powershell
# archive first
Move-Item C:\smoke\evidence\<ID>-*.log C:\smoke\evidence\<ID>-attemptN-<failtag>-... 
Copy-Item C:\metashape-root\projects\output\<name>\* C:\smoke\evidence\<ID>-attemptN-envelopes\ -Recurse
# then clean — otherwise the stale-envelope guard exits 2 (that guard IS test T3)
Remove-Item C:\metashape-root\projects\<name>.psx -Force
Remove-Item C:\metashape-root\projects\<name>.files -Recurse -Force
Remove-Item C:\metashape-root\projects\<name>_images -Recurse -Force
Remove-Item C:\metashape-root\projects\output\<name> -Recurse -Force
```

## Envelope PASS criteria (read from C:\metashape-root\projects\output\<name>\)

| Envelope | PASS looks like |
|---|---|
| result_sampling.json | `"sampling_method":"stratified"`, non-zero computed_keypoint_limit. `fallback_unlimited` + `chunk.document unavailable` = finding F4 unfixed |
| result_alignment_check.json | status ok, percentage >= 90. On failure, `unaligned_labels` names the dead session — diagnose pass structure |
| result_markers.json | total_detected == expected count; `unexpected: ["point N"...]` only. `detection_rate` reads 0.0 pre-assignment (known cosmetic) |
| result_marker_loading.json | status ok, `method: spatial_match`, all targets in valid_marker_labels, per-marker reference_errors (ft). FRAME_MISMATCH here can be the stochastic F6 gate — one identical resubmit is a legitimate retry |
| result_camera_translation.json | status ok; worker-stderr shows post_shift_rmse + outlier flags |
| result_appe.json | status ok. `peak` key ONLY when the RE sweep iterated; pre-cleaned data legally yields no peak (empty sweep) |
| result_confidence.json + deliverables | orthomosaic.tif, dem.tif, pointcloud.las, report.pdf all present, exit 0 |

## Cycle-time budget (202 draft photos, i9-14900K)

preflight+stage+CRS ~1 min · sampling ~10 s · match ~2 min · align ~1.5 min ·
markers ~1.5 min · **APPE diagnostics 104-126 min single-core (silent)** ·
RU/PA ~50 min · natives (depth→dense) ~10 min all-cores.
Marker gate is reached at ~7 min — front-load verification there; full cycle
~3.5-4 h. Plan fix-verify loops accordingly.
