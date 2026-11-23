---
name: to-field
description: To-field package for a Stahly survey job - from signed contract to a crew in the field. Runs a baseline sweep (project folder, proposal, Outlook, public control/lidar data) before asking anything, one batched decision round, then control, targets, flight, 811, pickup and the field card (PDF, phone page with KML, data collector points). Use only when RH types /to-field <job>.
disable-model-invocation: true
---

# To-field

Builds the **to-field package** for one job (terms: toolkit `GLOSSARY.md`). Done when the field card is published and every open item is closed or assigned to someone.

Paths use `\\stahly\PROJECTS` (never drive letters). Run share commands from PowerShell; Git Bash rewrites `\\server\share` paths.

## Step 1 - Baseline sweep (before asking RH anything)

Find every **fact** you can, each with its source. Run these as parallel read-only subagents; each returns facts as `fact | source (file, email or URL)`.

1. **Project folder** `\\stahly\PROJECTS\<client>\<job>\` if it exists: `Documents\Survey\_AI\STATE.md`, exhibits, `Plats_Maps_Deeds`, `Survey_GIS_Data\1-TBC` (template, Checkin), `2-UAV`, `4-Utility_Locates`, `5-Field_Notes`.
2. **Proposal** on `\\Stahly\marketing\Scope-Schedule-Budget\Survey - GIS\<year>\<office>\<NNN-Name>\` (offices: Great_Falls, Billings, Bozeman, Cody, ...). Folder names carry a proposal sequence number, not the job number: match by client and project name. Read the SOW PDF, bid workbook, fee trace, exhibits: limits, crew, field days, hours, deliverables, datum named in the contract.
3. **Outlook**: search by job number and client; read the **811 Locates** folder (ticket emails from mt@occinc.com, "Ticket Check Status for MT Ticket <n>").
4. **Public data**: NGS marks within ~5 mi (NGS radius search/datasheets: PID, mark type, order, NAVD88, last recovery); MTSRN stations and subnet (https://www.mtsrn.org/Images/MTSRN_MAP.pdf); USGS 3DEP and Montana state lidar coverage; low-distortion zone covering the site (RMCRS/RMTCRS manual, EPSG); NGS geoid API for GEOID18 vs older models.
5. **Records**: when boundary work is in scope, hand off to the records-research skill.
6. **Prior Stahly control**: control-index is not wired into v1. If RH wants it, run the control-index skill's search at the site.

Write the facts into STATE.md under **Facts** with sources. When two sources disagree, record both with sources and make it a decision; signed documents outrank drafts, newer outranks older.

On a re-run, sweep only files and emails new or changed since STATE.md's last sweep note, and show what changed.

## Step 2 - One decision round

Ask RH everything the sweep could not settle, in one batch, each with a recommendation worded so "yes" accepts it. Typical:
- **Grid and datum**: offer a low-distortion zone when one covers the site; keep the contract datum available by transform. Vertical NAVD88 with GEOID18.
- **Base**: primary and fallback marks (prior Stahly control, MDT caps, NGS), checked in from MTSRN VRS, local base logging static for OPUS.
- **Scope reading**: which branches apply (drone, boundary, lidar).
- Gaps: crew, dates, takeoff spot, anything not found.

Write each answer to STATE.md under **Decisions** as it is made.

## Step 3 - Branches

Always:
- **Control** (base pick, vertical tie, site control). A control checklist artifact helps RH pick marks: one checkbox and one aerial close-up per candidate (see `references/toole-example.md`).
- **811**: utility-locate skill; ticket numbers from the 811 Locates emails go on the card.
- **Pickup**: conventional pickup list and an exhibit drawn on a correctly georeferenced aerial (aerial rule in `references/gotchas.md`). Optional Street View walk with Claude in Chrome.

When in scope:
- **Drone**: targets (at least one image footprint inside photo coverage, spread in height; RH can draw them on a target-map artifact) and flight plans via auterion-plan-generator. Ask where the pilot will stand: the plan's home must be the takeoff spot.
- **Boundary**: records-research; monument search list on the card.
- **Lidar**: auterion-plan-generator (LiDAR mode).

## Step 4 - Outputs (one point list feeds everything)

1. Write `Survey_GIS_Data\3-To_Field\points.json` (schema in `scripts/field_points.py`): base marks, NGS marks, targets, site control, plus layers (limits, flight paths, coverage, exhibit zones).
2. `py scripts\field_points.py <points.json> <card.html>` writes `TooleCH`-style `<job>_field_pts_PNEZD.csv` beside it and fills the card's target/point table between `<!--PTS-->` markers. The PNEZD and the table always match.
3. `py scripts\mkkml.py <points.json>` writes a layered KML (base, NGS, targets, prior control, flight, exhibit) with tap-for-details control points.
4. Card: copy `templates\field_card_example_toole.html` to `3-To_Field\FIELD_CARD_<job>.html` and rewrite every section for this job from STATE.md (scope, datum and grid, base procedure, targets, flight, 811 tickets and members, schedule, pickup priorities, boundary, open items). Keep the layout.
5. `pwsh scripts\render_card.ps1 <card.html>` renders the PDF through a temp file and fails loudly if the PDF is open.
6. `py scripts\phone_page.py <card.html> <kml> [exhibit.png]` builds a phone page; publish it as an Artifact with `capabilities: {"downloads": true}` so the KML downloads in the field.
7. Email RH the plans, PNEZD, KML and PDF (send-outlook-email "send to myself" rule; copy attachments into the user profile first).

## Step 5 - Close out

List open items with owners in STATE.md and on the card. Report done only when the card is published and each open item is closed or assigned.

## References

- `references/toole-example.md`: the worked example (job 2071-07D26), every output's path.
- `references/gotchas.md`: things that broke on Toole and how to avoid them.
