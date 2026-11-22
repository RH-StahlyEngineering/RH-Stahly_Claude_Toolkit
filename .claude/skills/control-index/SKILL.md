---
name: control-index
description: Control index - find prior Stahly control, monuments and benchmarks already tied near a site. Branches - search near a site (lat/lon or limits KML) or by job number; background catch-up indexing of new project folders (callers like to-field); first full build (only when RH asks). Use when looking for existing control near a project, or when (re)indexing project folders.
---

# Control index

Points to records; never stores survey values. A result's `locator` is ~10 m and labelled "locator only": read real values from `source_path`.

## Database

Path resolves: `--db` flag, else `CONTROL_INDEX_DB` env, else `config.json` (`db`). Default is RH's shared GIS folder:
`\\Stahly\resource library\2 Department Resources\SURVEY_GIS\GIS Resources\Stahly Internal All Points GIS\Control_Index\control_index.sqlite`.
`python scripts/control_index.py where-db` prints the path in use.

- SMB share: SQLite rollback journal (no WAL). One writer at a time; don't start a second `index` while one runs. Searches are fine alongside.
- Next to it sits RH's hand-built ArcGIS "Stahly All Points" dataset (`Geodatabase\Stahly_All_Points.gdb`, `Shapefiles\*Merge`, `TBC Exports-Raw`). Never modify it. Possible later cross-check or seed; not used now.

## Search (near a site / by job)

```
python scripts/control_index.py search <lat> <lon> [--radius 1] [--all]
python scripts/control_index.py search --kml <limits.kml> [--radius 1] [--all]
python scripts/control_index.py search --job 2071-07D26 [--all]
```

Output contract (stdout JSON, tested in `tests/test_wiring.py`):

```
{"query": {...},
 "results": [{"kind", "distance_mi", "point_name", "feature_code", "description", "recorded", "flags",
              "job_number", "source_path", "coord_system", "date",
              "locator": {"lat", "lon", "label"}, "sources": [...]}],
 "unparsed_files": [{"source_path", "error"}],
 "skipped_files": [{"source_path", "status", "reason"}],
 "coverage": {"folders_indexed", "folders_pending", "complete", "last_complete_run"}}
```

- `results` ranked kind (control, monument, other) then distance; `--all` adds kind `other`.
- `--kml`: radius from the polygon edge (inside = 0). `--job`: `distance_mi` null.
- Copies of one mark (same kind, adjacent locator cell, same point number or description, e.g. CP60 / 60R) collapse to one result; `sources` lists every copy.
- `coverage.complete` false means the index is partial: say so when reporting results.
- Kind and condition flags (bent/broken/tipped/disturbed) come from `scripts/kinds.py`, the one editable keyword table.

## Catch-up (background, callers like to-field)

Run as a BACKGROUND subagent; never block the caller on it:

```
python scripts/control_index.py index \\stahly\PROJECTS \\Stahly\Archives --budget 220
```

- Skips unchanged folders; a stopped run resumes next time.
- Exit code 0 even when the budget stops it. Read stdout JSON `{"complete", "stopped", "folders_read", "folders_skipped", "files_read"}`; `stopped` is `"budget"`/`"max_files"`/null.
- The caller searches whatever is indexed; it doesn't wait for catch-up.

## First full build

Only when RH explicitly asks. No automatic trigger. Same command without `--budget` (hours on the share):

```
python scripts/control_index.py index \\stahly\PROJECTS \\Stahly\Archives
```

## Sources and tests

- `.jxl` (Reductions section; WGS84 when stored, else grid projected from the job's ProjectionRecord).
- `.vce` TBC projects (points + latest codes; grid projected from the CSIB coordinate system).
- CSV exports (`name,N,E,Z,desc`) only when a sibling .vce/.jxl in the job tree gives the coordinate system; else in `skipped_files`. Ground-scaled projects are unscaled about the project origin; flags `ground_scaled` / `scale_unverified`.
- Tests: `python -m pytest tests` (fixtures are trimmed real .jxl/.vce files; temp databases only).
