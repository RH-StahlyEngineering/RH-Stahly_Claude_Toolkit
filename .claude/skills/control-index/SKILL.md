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

- SMB share: SQLite rollback journal (no WAL). Concurrent `index` runs are safe but waste budget waiting on each other's write locks, so prefer one at a time. Searches are fine alongside.
- Schema version lives in the database; a database from an older layout is dropped on open and rebuilt by the next `index` run (coverage reads incomplete until then).
- Next to it sits RH's hand-built ArcGIS "Stahly All Points" dataset (`Geodatabase\Stahly_All_Points.gdb`, `Shapefiles\*Merge`, `TBC Exports-Raw`). Never modify it.

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
 "unparsed_files": [{"source_path", "error"}], "unparsed_total",
 "skipped_files": [{"source_path", "status", "reason"}], "skipped_total",
 "coverage": {"folders_indexed", "folders_pending", "complete", "last_complete_run"}}
```

- `results` ranked kind (control, monument, other) then distance; `--all` adds kind `other`.
- `--kml`: radius from the polygon edge (inside = 0). `--job`: `distance_mi` null.
- Copies of one mark collapse to one result; `sources` lists every copy. Grouping is decided at index time from unrounded positions: same kind, within ~2 m, same point number (CP60 / 60R) or same description, and descriptions not naming different monument types (MDT aluminum cap vs Stahly RPC; type table in `scripts/kinds.py`). The database keeps only a group id and a 1 m grouping bucket, never output.
- `unparsed_files` / `skipped_files` list only files in jobs with records in the search area (or the `--job`); `*_total` count the whole index.
- `locator` is the centre of a ~10 m cell (near-uniform N-S and E-W).
- `coverage.complete` false means the index is partial: say so when reporting results. `folders_pending` includes job folders seen but not yet crawled (a lower bound on remaining work).
- Kind, condition flags (bent/broken/tipped/disturbed) and monument types come from `scripts/kinds.py`, the one editable keyword table.

## Catch-up (background, callers like to-field)

Run as a BACKGROUND subagent; never block the caller on it:

```
python scripts/control_index.py index \\stahly\PROJECTS \\Stahly\Archives --budget 220
```

- Skips unchanged folders; a stopped run resumes next time.
- Exit code 0 even when the budget stops it. Read stdout JSON `{"complete", "stopped", "folders_read", "folders_skipped", "files_read"}`; `stopped` is `"budget"`/`"max_files"`/null.
- The caller searches whatever is indexed; it doesn't wait for catch-up.

## First full build

Only when RH explicitly asks. Same command without `--budget` (hours on the share):

```
python scripts/control_index.py index \\stahly\PROJECTS \\Stahly\Archives
```

## Sources and tests

- `.jxl` (`scripts/jxl.py`, notes `references/jxl-format.md`; Reductions section; WGS84 when stored, else grid projected from the job's ProjectionRecord).
- `.vce` TBC projects (`scripts/vce.py`, notes `references/vce-format.md`; points + latest codes; grid projected from the CSIB coordinate system).
- CSV exports (`name,N,E,Z,desc`) only when a sibling .vce/.jxl in the job tree gives the coordinate system; else in `skipped_files`. Ground-scaled projects are unscaled about the project origin; flags `ground_scaled` / `scale_unverified`.
- Tests: `python -m pytest tests` (fixtures are trimmed real .jxl/.vce files; temp databases only).
