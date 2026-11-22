---
name: control-index
description: Find prior Stahly control and monument records near a site from the control index (a map of records by locator). Use when looking for existing control, monuments or benchmarks Stahly already tied near a project location, or when (re)indexing project folders into the control index.
---

# Control index

Points to records; never stores survey values. A result's `locator` is ~10 m and labelled "locator only": read real values from `source_path`.

```
python scripts/control_index.py index <root>... --db <control.sqlite>
python scripts/control_index.py search <lat> <lon> --db <control.sqlite> [--radius 1] [--all]
```

- Sources: `.jxl` (Reductions section; WGS84 when stored, else grid projected from the job's ProjectionRecord).
- Search JSON: `results` ranked kind (control, monument, other) then distance; `--all` adds kind `other`. `unparsed_files` lists files that failed to parse.
- Kind and condition flags (bent/broken/tipped/disturbed) come from `scripts/kinds.py`, the one editable keyword table.
- Database folder: pass `--db`; the shared location is RH's choice.
- Tests: `python -m pytest tests` (fixtures are trimmed real .jxl files).
