---
name: stahly-ppk
description: AI layer over Stahly_PPK, the repo that PPK-processes Stahly drone (UAV) flights. Finds the inputs, asks what only a person can answer, runs the repo's own code, checks and files the results, and reports. Use whenever RH asks to PPK, re-run, check or file drone photo positions, convert a base log to RINEX, pick a base mark for a UAV job, prepare camera positions for DroneMapper, or explain a PPK height/position bias, even if he just says "process the flights" or names a job and flight numbers.
---

# Stahly PPK

This skill holds judgement and policy. Procedure belongs in the Stahly_PPK code. If this file ever needs editing because the code changed, something here belongs in the code instead.

## 1. The code does the processing

- Process only with the repo's own commands. Never re-implement a processing step in your own scripts: solving, interpolation, lever arm, coordinate or height conversion, attitude. Repo output carries its QA and provenance; hand-rolled output doesn't, and it silently diverges from the tool.
- Read usage fresh every time; it changes often. Never use commands, options, config keys, output names or profile values from memory.
  - Repo: `C:\Users\rharbach\Desktop\Stahly_PPK` (GitHub `RH-StahlyEngineering/Stahly_PPK`). Run `git pull` on master first and report the commit you used.
  - Usage and job-config keys: `engine/README.md` and the tool's `-h`.
  - Aircraft geometry: `engine/profiles/`.
  - Method decisions and domain facts: `GLOSSARY.md`, `docs/adr/`, the README.
  - Unsettled questions: the repo's open issues. Treat them as open.
- Prefer the tool's machine-readable outputs (job/run JSON, QA report) over your own parsing when you check results.

## 2. Close the gaps, don't paper over them

When you have to do something by hand that the tool should do, do the minimum to finish safely, then **propose a GitHub issue on the repo** (title, why, acceptance criteria) and tell RH. Typical gaps: input checks, staging a job for discovery, renaming outputs to the folder standard, upload copies, comparing a re-run with the last result, base-log conversion.

Before doing a chore by hand, check whether the tool now does it (README, `-h`, closed issues). If the tool can't do something that matters to the result, stop and ask RH. Don't work around it.

Small helpers for chores outside processing are fine: copying, hardlinking, name checks. Keep them out of the repo unless they become an issue.

## 3. Find inputs, then ask

Use the `uav-folder-standard` skill to know where a job keeps photos, rover logs and imagelogs, base logs, base control, targets and PPK results. Look there first, then search the job briefly. If something is still missing, **ask RH where it is**, saying what you looked for and where. Never hard-code paths from memory.

Ask, unless RH already answered in this conversation:
- **Base mark:** point, coordinates with units and grid (or lat/lon/ellipsoidal height), height type and geoid, datum and epoch.
- **Antenna height reference:** is the base antenna height to the ARP or to the phase centre?
- **Output grid.**
- **Where any submission copies should go.**

Judge the evidence. A value found in a field file may be an old coordinate keyed in, not a measured setup. Say which you think it is.

## 4. Policy

- **Additive only.** Never overwrite or delete in jobs or shared folders. On a name clash, add a suffix and list it. Superseded results get moved aside, never removed.
- **Writing into PROJECTS needs RH's OK** for each job, unless he gave it in this conversation.
- **Nothing is submitted (e.g. to DroneMapper) without RH.** Prepare it; he sends.
- **Don't submit** FPV flights, test flights, or flights with no rover log. Set them aside by moving them.
- **Base vertical errors:** the only base error to consider is the ARP vs phase-centre confusion, i.e. the antenna calibration's vertical offset (12.9 cm for a Trimble R12i) counted twice or left out. Don't invent other measurement errors.
- **Same aircraft:** a run uses one aircraft profile. If the photos come from a different airframe than the profile's (compare the photo metadata's vehicle ID with a known job), stop and ask.
- **Honesty:** report what you did not do or could not verify. If a bias can't be shown consistently, say so. When RH asks yes or no, answer yes or no.

## 5. Shape of a run

1. Pull the repo and read the current usage.
2. Find the inputs (section 3); ask for what's missing.
3. Check the inputs with the tool's own checks where it has them; otherwise check by hand and propose an issue (section 2).
4. Run the tool into a temporary output location.
5. Check the results from the tool's outputs. Explain anything odd: low fix, unpositioned photos, warnings, a changed height.
6. File them where the folder standard says (RH's OK for PROJECTS), and prepare any submission copies RH asked for.
7. Report.

## 6. Report

Per flight: fix %, photos positioned / total, QA flags, the base value used and its source, and on a re-run the change from the last filed result. Then the repo commit, every path written, issues proposed, and anything not done or not verified. Keep it short.
