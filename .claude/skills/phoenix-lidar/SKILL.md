---
name: phoenix-lidar
description: >
  QA, base-station matching, and processing-plan prep for Phoenix LiDAR acquisition data
  (SpatialExplorer sessions with .nav / .rxp / cam0 imagery + base-station RINEX). Use this
  skill WHENEVER the user is working with Phoenix / SpatialExplorer LiDAR data, mentions a
  .nav or .rxp file, wants to check which base station (RINEX) covers a flight or mobile scan,
  asks about PPK baseline length or whether a mission was "acquired with a base station",
  needs the trajectory/footprint extent of a scan, wants a KML of flights/footprints, wants to
  decide which base to process each mission against, or needs a processing checklist/plan
  across many missions. Also triggers on "which base for this mission", "is this flight
  base-covered", "make a lidar footprint KML", "group missions by base", T04/RINEX baseline
  questions, and building a LiDAR processing tracker. Do NOT use it to drive the actual PPK
  software (SpatialExplorer / Inertial Explorer) — this skill stops at the QA'd plan.
---

# Phoenix LiDAR — acquisition QA & base-matching

## What this skill does (and doesn't)

Phoenix Systems record each acquisition as a **session folder** (`YYYYMMDD-hhmmss/`) holding raw
laser (`.rxp`), a real-time GNSS/INS trajectory (`.nav`, NovAtel binary), optional camera imagery
(`cam0/*.jpg`), a project summary (`.txt`), and support files. Post-processing (PPK) needs a
**base-station RINEX** whose observation window covers the scan.

This skill turns a pile of session folders + base files into a **QA'd, base-matched processing
plan**: it decides which acquisitions are valid, which base covers each one, computes baselines,
draws the geometry in KML, and builds a tracking checklist. It **does not** run the PPK software.

Everything is **read-only** on the raw data — you parse `.nav` binary and RINEX *headers* directly,
never opening the multi-GB `.rxp`/imagery/obs bodies.

## The pipeline

Run the scripts in `scripts/` in order. They compose through a shared `scripts/phoenix_lib.py`.

1. **`analyze.py`** — enumerate sessions, classify valid/aerial/mobile, parse trajectories +
   time windows, parse base RINEX, match each mission to its best base, group into batches.
   Writes `acq_data.json` (intermediate) + `matrix.csv` + `batches.json`.
2. **`make_kml.py`** — draw trajectories (green=valid/red=invalid), extent boxes, footprints
   (aerial), base placemarks + baseline lines. Options for date filter and speed-band footprints.
3. **`build_plan_xlsx.py`** — the processing checklist workbook (boolean checkbox column, README,
   no-base sheet).

```
python scripts/analyze.py --sessions <PROCESSING_DIR> --bases <RINEX_DIR> [--bases <RINEX_DIR2> ...] \
    [--control <control.csv> --control-points 1,2,5] [--policy furthest|avg] [--max-mi 10] \
    --out-dir <OUT>
python scripts/make_kml.py --acq <OUT>/acq_data.json --out <OUT>/all_acquisitions.kml \
    [--footprints --agl 50] [--speed-band 9.5 12.25] [--date-min 2026-06-30]
python scripts/build_plan_xlsx.py --out-dir <OUT> --out <OUT>/Processing_Plan.xlsx
```

Always run `analyze.py` first — the other two read its outputs.

## Core definitions (see `references/workflow.md` for the reasoning)

- **Valid acquisition** = has a `.txt` project file whose `CAM0: N / M` event/photo counts match,
  AND a usable GNSS/INS trajectory (a bench test with no sky fix is not a valid acquisition).
- **Type** = AERIAL if the session has `cam0/*.jpg`, else MOBILE.
- **A base "works"** = its RINEX obs file **fully time-brackets** the scan (first obs ≤ scan start
  AND last obs ≥ scan end, no gap). Partial overlap does **not** count — you can't PPK a gap.
- **Baseline** = distance from base to the mission. Default policy is **furthest-point** (the base
  must be close to the *whole* scan); `--policy avg` uses mean distance (better for long corridors).
- **Recommended base** = among bracketing bases, the one with the shortest baseline. A configurable
  `--max-mi` (default 10) flags long baselines but does not exclude them.
- **Batches** = missions sharing one base *file* (one occupation), capped at 3 — you load one base
  per PPK run, so same-position/different-day setups are separate batches.

## Footprints (aerial only)

Ground swath from the trajectory, flat-ground / constant-AGL. The half-swath convention is
**1.5 × AGL** (full swath 3 × AGL; 75 m at 50 m AGL) — from the auterion-plan-generator LiDAR
model. `--speed-band lo hi` draws footprint only over trajectory segments flown in that ground-speed
band (the productive on-line speed; turns/accel are masked). See `references/coordinates_and_footprints.md`.

## Formats & transforms

Details you'll need are in the references — read the relevant one when the task calls for it:
- **`references/nav_and_rinex.md`** — `.nav` NovAtel binary message offsets, GPS→UTC, RINEX header fields.
- **`references/coordinates_and_footprints.md`** — ECEF→geodetic, Montana State Plane (EPSG:2256)→WGS84,
  T04 filename decode (`[receiver][DOY][session]`), footprint swath model.
- **`references/workflow.md`** — validity rules, base-selection policy, the 7/10-mi baseline convention,
  and the gotchas (leap seconds, midnight-crossing windows, off-project sessions).

## Gotchas worth remembering

- On-disk timestamps are the *copy* date — the real scan time is the GPS time inside `.nav`.
- RINEX header times are GPS time; `.nav`-derived UTC is GPS − 18 s. Compare in one system; the 18 s
  is immaterial for gap checks but be consistent.
- Base positions from RINEX `APPROX POSITION` are autonomous (~1–2 m). If the user has surveyed
  control (a State Plane CSV), prefer it — but the ~2 m difference doesn't change mileage decisions.
- Windows can't run the xlsx `recalc.py` (no `AF_UNIX`); the only formula is a `COUNTIF` counter that
  Excel recalculates on open. That's fine — don't treat the recalc failure as a file error.
