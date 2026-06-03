# Stahly Canonical Paths — Fingerprint-Based Resource Registry

This file is **machine-readable** (`scripts/lib/canonical.py` parses the YAML
blocks below). It lists every Stahly artifact the skill depends on, with a
**fingerprint** that lets the resolver verify identity after a path change,
**search hints** that let the resolver re-locate a moved file, and a
**resolved_path** that the resolver writes back when resolution succeeds at a
new location.

## Rules of engagement

1. **The skill never hardcodes a path in code.** All paths flow through
   `canonical.resolve(resource_id)`.
2. **Stale `resolved_path` is recoverable.** If the path doesn't exist or
   doesn't fingerprint-match anymore, the resolver searches `search_hints` in
   order, updates this file with the new path, and continues.
3. **No silent fallback on miss.** If the resolver exhausts `search_hints`
   without a match, it raises `CanonicalResourceNotFound` with a structured
   error. The orchestrator surfaces the error to the user and asks where to
   look. The skill does **not** invent a default, skip the dependent step, or
   "assume."
4. **Self-update is logged.** Every resolved-path change appends a one-line
   entry to `references/canonical_resolution_log.md` (date, resource_id, old
   path, new path) so the user can audit drift over time.
5. **Resolution at session start.** The orchestrator invokes
   `canonical.resolve_all()` before the first user-facing question so missing
   resources surface as the very first thing, not mid-intake.

## How fingerprints work

Each resource carries one or more `content_markers` — lightweight checks the
resolver runs on a candidate file to verify it's actually the resource we want
(not just a same-named file). Markers are AND-ed; all must pass.

Marker types:

- `filename_exact`: the candidate's filename matches a literal string
- `filename_pattern`: the candidate's filename matches a glob
- `xlsx_sheet_name`: the candidate is an xlsx and has a sheet with the given
  name
- `xlsx_cell_value`: the candidate xlsx has a specific cell that contains a
  substring (case-insensitive)
- `docx_paragraph_starts_with`: the candidate's docx has a paragraph that
  starts with the given prefix
- `pdf_text_contains`: the candidate pdf's extracted text contains a substring
- `is_directory`: candidate is a directory
- `directory_contains_pattern`: directory contains at least one entry matching
  a glob (e.g. an `NNN-*` subfolder)
- `image_dimensions`: candidate image is exactly W x H (used for logo files)

## Resource registry

The blocks below are parsed as YAML. Edit the `resolved_path` only when you
know the file moved permanently and you want to skip a re-search next session.

### bid_template

```yaml
resource_id: bid_template
description: Stahly Project Bidding Template (current year, blank)
content_markers:
  - type: filename_pattern
    value: "Project Bidding Template *.xltx"
  - type: xlsx_sheet_name
    value: "Bid Sheet Template"
  - type: xlsx_cell_value
    sheet: "Bid Sheet Template"
    cell: "A7"
    contains: "Phase - Blue"
  - type: xlsx_cell_value
    sheet: "Bid Sheet Template"
    cell: "B1"
    contains: "Client Name"
search_hints:
  - "\\\\Stahly\\stahly standards\\5-Project_Management\\5.1-Project Budget\\Project Bidding Template *.xltx"
  - "\\\\Stahly\\stahly standards\\5-Project_Management\\5.1-Project Budget\\*.xltx"
  - "\\\\Stahly\\stahly standards\\**\\5.1-Project Budget\\Project Bidding Template *.xltx"
  - "\\\\Stahly\\stahly standards\\**\\Project Bidding Template *.xltx"
  - "\\\\Stahly\\**\\Project Bidding Template *.xltx"
resolved_path: "\\\\Stahly\\stahly standards\\5-Project_Management\\5.1-Project Budget\\Project Bidding Template 2026.xltx"
resolved_at: "2026-05-22"
notes: |
  Annual rollover: when "Project Bidding Template 2027.xltx" appears, the
  filename_pattern matches it and the resolver auto-migrates. Flag the year
  change to the user so they can also verify labor rates.
```

### bid_template_instructions

```yaml
resource_id: bid_template_instructions
description: Bidding Spreadsheet Instructions (how to use the template; color coding, hidden expansion, labor-code overrides)
content_markers:
  - type: filename_pattern
    value: "Bidding Spreadsheet Instructions*.docx"
  - type: docx_paragraph_starts_with
    value: "Bidding Spreadsheet:"
search_hints:
  - "\\\\Stahly\\stahly standards\\5-Project_Management\\5.1-Project Budget\\Bidding Spreadsheet Instructions*.docx"
  - "\\\\Stahly\\stahly standards\\**\\5.1-Project Budget\\Bidding Spreadsheet Instructions*.docx"
  - "\\\\Stahly\\stahly standards\\**\\Bidding Spreadsheet Instructions*.docx"
resolved_path: "\\\\Stahly\\stahly standards\\5-Project_Management\\5.1-Project Budget\\Bidding Spreadsheet Instructions.docx"
resolved_at: "2026-05-22"
```

### labor_rate_sheet_standard

```yaml
resource_id: labor_rate_sheet_standard
description: 2026 Labor Code Rate Sheet (Standard rates) — PDF
content_markers:
  - type: filename_pattern
    value: "INTERNAL USE ONLY * Labor Code Rate Sheet.pdf"
  - type: pdf_text_contains
    value: "Labor Code Rates"
search_hints:
  - "\\\\Stahly\\stahly standards\\5-Project_Management\\5.1-Project Budget\\INTERNAL USE ONLY * Labor Code Rate Sheet.pdf"
  - "\\\\Stahly\\stahly standards\\**\\5.1-Project Budget\\INTERNAL USE ONLY * Labor Code Rate Sheet.pdf"
  - "\\\\Stahly\\stahly standards\\**\\INTERNAL USE ONLY * Labor Code Rate Sheet.pdf"
resolved_path: "\\\\Stahly\\stahly standards\\5-Project_Management\\5.1-Project Budget\\INTERNAL USE ONLY 2026 Labor Code Rate Sheet.pdf"
resolved_at: "2026-05-22"
notes: |
  Filename excludes the word "Professionally" — this is the standard-rate PDF,
  not the professionally-discounted one. The resolver verifies absence of that
  word as part of the filename_pattern match.
```

### labor_rate_sheet_discounted

```yaml
resource_id: labor_rate_sheet_discounted
description: 2026 Professionally Discounted Labor Code Rate Sheet — PDF
content_markers:
  - type: filename_pattern
    value: "INTERNAL USE ONLY * Professionally Discounted Labor Code Rate Sheet.pdf"
  - type: pdf_text_contains
    value: "Professionally Discounted"
search_hints:
  - "\\\\Stahly\\stahly standards\\5-Project_Management\\5.1-Project Budget\\INTERNAL USE ONLY * Professionally Discounted Labor Code Rate Sheet.pdf"
  - "\\\\Stahly\\stahly standards\\**\\5.1-Project Budget\\INTERNAL USE ONLY * Professionally Discounted Labor Code Rate Sheet.pdf"
  - "\\\\Stahly\\stahly standards\\**\\INTERNAL USE ONLY * Professionally Discounted Labor Code Rate Sheet.pdf"
resolved_path: "\\\\Stahly\\stahly standards\\5-Project_Management\\5.1-Project Budget\\INTERNAL USE ONLY 2026 Professionally Discounted Labor Code Rate Sheet.pdf"
resolved_at: "2026-05-22"
```

### proposal_folder_root_billings

```yaml
resource_id: proposal_folder_root_billings
description: Per-office proposal folder root for Billings (current year). Holds NNN-* project subfolders.
content_markers:
  - type: is_directory
  - type: directory_contains_pattern
    value: "[0-9][0-9][0-9]*"
search_hints:
  - "\\\\Stahly\\marketing\\Scope-Schedule-Budget\\Survey - GIS\\2026\\Billings"
  - "\\\\Stahly\\marketing\\Scope-Schedule-Budget\\Survey - GIS\\*\\Billings"
  - "\\\\Stahly\\marketing\\Scope-Schedule-Budget\\**\\Billings"
resolved_path: "\\\\Stahly\\marketing\\Scope-Schedule-Budget\\Survey - GIS\\2026\\Billings"
resolved_at: "2026-05-22"
```

### proposal_folder_root_bozeman

```yaml
resource_id: proposal_folder_root_bozeman
description: Per-office proposal folder root for Bozeman (current year).
content_markers:
  - type: is_directory
  - type: directory_contains_pattern
    value: "[0-9][0-9][0-9]*"
search_hints:
  - "\\\\Stahly\\marketing\\Scope-Schedule-Budget\\Survey - GIS\\2026\\Bozeman"
  - "\\\\Stahly\\marketing\\Scope-Schedule-Budget\\Survey - GIS\\*\\Bozeman"
  - "\\\\Stahly\\marketing\\Scope-Schedule-Budget\\**\\Bozeman"
resolved_path: "\\\\Stahly\\marketing\\Scope-Schedule-Budget\\Survey - GIS\\2026\\Bozeman"
resolved_at: "2026-05-22"
```

### proposal_folder_root_great_falls

```yaml
resource_id: proposal_folder_root_great_falls
description: Per-office proposal folder root for Great Falls (current year).
content_markers:
  - type: is_directory
  - type: directory_contains_pattern
    value: "[0-9][0-9][0-9]*"
search_hints:
  - "\\\\Stahly\\marketing\\Scope-Schedule-Budget\\Survey - GIS\\2026\\Great_Falls"
  - "\\\\Stahly\\marketing\\Scope-Schedule-Budget\\Survey - GIS\\*\\Great_Falls"
  - "\\\\Stahly\\marketing\\Scope-Schedule-Budget\\**\\Great_Falls"
resolved_path: "\\\\Stahly\\marketing\\Scope-Schedule-Budget\\Survey - GIS\\2026\\Great_Falls"
resolved_at: "2026-05-22"
```

### proposal_folder_root_helena

```yaml
resource_id: proposal_folder_root_helena
description: Per-office proposal folder root for Helena (current year).
content_markers:
  - type: is_directory
  - type: directory_contains_pattern
    value: "[0-9][0-9][0-9]*"
search_hints:
  - "\\\\Stahly\\marketing\\Scope-Schedule-Budget\\Survey - GIS\\2026\\Helena"
  - "\\\\Stahly\\marketing\\Scope-Schedule-Budget\\Survey - GIS\\*\\Helena"
  - "\\\\Stahly\\marketing\\Scope-Schedule-Budget\\**\\Helena"
resolved_path: "\\\\Stahly\\marketing\\Scope-Schedule-Budget\\Survey - GIS\\2026\\Helena"
resolved_at: "2026-05-22"
```

### proposal_folder_root_cody

**REMOVED 2026-06-03 — Cody, WY office closed.** Historical resolutions retained in `canonical_resolution_log.md` for reference. The resolver should no longer try to resolve this resource ID; remove from the resolve_all() list in `scripts/lib/canonical.py` if it appears there.

## Discovered-but-unverified candidates

When the resolver finds candidates that *partially* match (filename pattern hits
but content markers fail), it appends them here so the user can audit. Empty by
default.

```yaml
# Format:
# - resource_id: <id>
#   candidate_path: <path>
#   failed_markers: [<list of marker types>]
#   discovered_at: <date>
```
