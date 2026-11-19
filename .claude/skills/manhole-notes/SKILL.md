---
name: manhole-notes
description: Fill out Stahly manhole and inlet note sheets (storm MH, sanitary MH, curb/grate/combo inlets) from field measure-downs, as Word .docx with a to-scale plan view and the field photo turned to true north. Use whenever a surveyor dictates or types manhole/inlet data (inverts, measure-downs, top of pipe, pipe sizes, drops, grade rings, lid position, structure diameter), sends a photo looking down a manhole, asks for "MH sheets", "manhole notes", "structure notes", "measure-downs", or wants the Manhole Note Template filled in — even if they only send one number at a time from the field.
---

# Manhole and inlet note sheets

A surveyor in the field sends structure data one value at a time, by chat or on a form page. You keep a clean record of exactly what they said. When a structure is complete, you produce the Stahly note sheet. The sheets feed design: an engineer sizes pipes and sets grades from them. A guessed value that looks measured is worse than a blank.

## The record is the crew's words

- **Write down only what the crew gave.** A value they didn't give stays out of the record. On the final sheet it prints `NOT RECORDED`. That is different from "none": "I didn't record it" is not "there are zero rings". RH corrected this once already.
- **Never write "presumed".** If the crew says one pipe "is the same size as" another, record the size and note that in their words.
- **A photo is evidence, not a measurement.** You may describe what it shows in the notes: the bench, silt, steps, how far a pipe sticks in. Never fill a measured field from a photo (material, drop, size) unless the crew confirms it.
- **Ask when something doesn't fit.** Examples: a size between standard pipe sizes, or a direction set that doesn't match the photo. Show the number and ask; don't round it to whatever looks right. In the field, the crew stated actual sizes (18", 30") that differed from the computed ones (19.4, 28.1). Keep both: the stated size on the box, the computed one in the notes.

## Geometry the crew relies on

- **Top of pipe means the outside top.** Invert = top + wall + ID, and ID = (invert − top − wall) × 12. Wall thickness comes from the crew, estimated per pipe or job-wide. If it's missing and a calculation needs it, ask; don't assume 0 or 0.05.
- **Slant tape:** vertical = √(slant² − horizontal²). Note it, because a long slant amplifies tape error.
- **Field north is usually square to the main street, not true north.**
  1. Get the street's bearing from OSM: Overpass, then a geodesic azimuth. That's true north, not grid.
  2. Set `field_north_az` (e.g. street N61.8°W gives field N = true N28.2°E).
  3. Record directions in `job.json` exactly as the crew called them.
  4. The sheet speaks only true north: the script converts every direction (pipe boxes, plan labels, lid side) to the nearest 16-point true direction, and rotates pipes, lid and photo together. An engineer reading the sheet should never have to wonder which north a label means. Don't add notes about field directions; they only create that doubt.
- **Every page shares one north.**
  - The photo must be turned to true north, using only what the crew tells you about it: "field north was up", "the rungs are SW", and so on. Never work out a rotation yourself from what the photo seems to show.
  - If what they said disagrees with itself (rungs SW, but "the pipe above the rungs is west" lands about 45° off), ask which one governs. Don't pick one or average them.
  - If you don't know, ask while they're still at the structure. A final sheet with an unknown photo orientation leaves the photo off rather than mixing norths.
- **Draw to scale.**
  - The circle stays the template's size, and the lid is 24 in.
  - Pipe width is pipe diameter over structure diameter.
  - Pipes extend into the structure by `proj`. When there's a photo and the crew didn't measure it, estimate each pipe's `proj` in inches from the photo yourself, against the known structure diameter. A flush pipe is 0-1. Don't skip this step, but only estimate a projection when you can tell which pipe in the photo is which. If the photo's north is unknown, leave `proj` out.
  - A pipe of unknown size is drawn as a single centerline.

## Field mode vs. the engineer's sheet

Two different readers:
- **In the field, the crew is your reader.** Push them for everything you can get: after each value, list what's still missing for that structure. Box size, pipe material and drop are worth asking for, but don't treat any one item as required.
- **On the sheet, the engineer is your reader.** It never talks to the crew:
  - no "?" marks, "size unknown" text, or reminders
  - missing values read NOT RECORDED (with `--final`), and nothing else
  - OTHER NOTES stays short: the crew's own notes, plus any calculation with its arithmetic. No boilerplate.

## Street labels

- Label the street the structure sits in, and a cross street only at an intersection. Those labels can be placed without ambiguity.
- Give each a true `bearing` so the text runs parallel to the street.
- For a street beside the structure rather than through it, also give `side`: the true azimuth from the structure toward the street centerline. The label goes on that side.
- Don't label a street that doesn't reach the structure, and never write distance-direction text like "Pine Ave 108' SE": a reader can't tell what it means.

## Workflow

1. **Set up the job once.** Do this the first time per job and day.
   - Field-north offset and its reference street.
   - Street names and bearings near the structures. Get these from the crew's point coordinates if you have their job file, otherwise ask.
   - What measure-downs start from (rim).
   - Any kinds the engineer said not to measure (sanitary often).
   - Wall thickness, if job-wide.
   - The output folder: `Survey_GIS_Data\5-Field_Notes\YYYY-MM-DD_Storm_Measure-Downs`, named for the field date (e.g. `2026-11-12_Storm_Measure-Downs`). Use `_Sanitary_Measure-Downs` for a sanitary-only day.

   Measure-downs are from the rim unless the crew says otherwise, for example top of grate on inlets. Set `measure_from` only to override that.

   Write all this to `job.json` (see `references/data_schema.md`) in the job's `Documents\Survey\_AI` folder or similar.
2. **Collect structures.**
   - **Chat:** append each value to `job.json` as it arrives, and echo back what you recorded in a short table so the crew can catch mistakes. Say what's still missing for that structure. When a computed value comes out odd, show the arithmetic.
   - **Form:** publish `assets/field_form.html` as a fresh artifact per job, with capabilities `{db:{rules:[{path:"manholes",read:"view",write:"admin"}]},user:{}}`. Seed known points with `ArtifactData`. Before writing, read the doc and pin `if_version`; a stale open page overwrote a write once. To build sheets, `ArtifactData list` with `out_dir`, then merge into `job.json`. The script accepts the form's field names.
3. **Build.** `python scripts/mh_sheet.py job.json --only <points>` writes a draft, with blanks still blank. Use `--final` once the crew says a structure is done, so missing values read NOT RECORDED.
4. **Check visually.** `python scripts/check_sheets.py <out_dir> --png <scratch>` renders through Word. LibreOffice paginates differently, so page counts from it are wrong. Look at every page 1 and page 2. The form must be 1 page. Check pipe angles against the photo, lid side, labels clear of pipes, and nothing clipped. Fix and re-run.
5. **Review independently.** Give each sheet one reviewer subagent with `references/review_prompt.md`, using the crew's verbatim words as ground truth. Fix real findings. Tell RH about any finding you decide not to fix.
6. **Deliver.**
   - Make sure the target .docx isn't open in Word; `check_sheets.py` reports a lock.
   - Write to `out_dir`.
   - Send RH the files.
   - Say what's still NOT RECORDED.

## Inlets and sanitary

- **Inlets** use the same form. The structure box gives box L × W and the opening/grate side, and the plan view draws the box as a rectangle, rotated with field north. A pipe whose invert can't be reached gets `top` plus `wall`; its invert is computed once the size is known.
- **Sanitary manholes** use the storm layout with `kind: sanitary_mh`. Engineers often waive sanitary measure-downs. Set `measure_downs.sanitary_mh: false` so those blanks stay empty instead of reading NOT RECORDED.

## Files

- `scripts/mh_sheet.py`: builds the sheets from `job.json` (draft or `--final`).
- `scripts/check_sheets.py`: Word render, page count, PNGs, open-in-Word check.
- `assets/stahly_manhole_template.docx`: a copy of the Stahly standard. It's bundled so sheets build off-network. The standard on `\\Stahly` is Brian Kray's to change; this skill doesn't replace it.
- `assets/field_form.html`: the field entry page.
- `references/data_schema.md`: every field, with an example.
- `references/review_prompt.md`: the independent reviewer brief.
