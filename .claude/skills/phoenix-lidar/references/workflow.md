# Workflow: validity, base selection, and gotchas

## What makes an acquisition "valid" / successful
Not just "files exist" — a *successful* acquisition is one that closed out cleanly and can be
processed:
1. **Closed out** — the `.txt` project summary exists. A session with only a `qt_temp` leftover and
   no `.txt` was aborted/scrapped.
2. **Photo integrity** — the `.txt` line `Number of events/photos recorded for CAM0: N / M` has
   `N == M` (every camera trigger produced a saved image). A mismatch = dropped imagery.
3. **A real trajectory** — the `.nav` yields a continuous GNSS/INS position solution. A bench test
   with no sky fix has a `.txt` but no trajectory and is **not** a valid acquisition.
4. **Type** — AERIAL if `cam0/*.jpg` exist, else MOBILE (mobile runs often have the camera off).

## Base selection
- A base **works** for a mission only if its RINEX obs window **fully brackets** the scan
  (first ≤ start AND last ≥ end). Partial overlap is useless — you can't PPK across a gap.
- **Baseline policy** (`--policy`):
  - `furthest` (default) — the base must be within range of the *whole* scan (max distance to any
    trajectory point). Conservative; right for compact flights.
  - `avg` — mean distance to the trajectory. Better for long mobile corridors where the furthest end
    inflates the number but most of the run is close.
- **Recommended base** = shortest baseline among bracketing bases. `--max-mi` (default 10) *flags*
  long baselines but doesn't exclude them — sometimes the closest available base is still the answer.
- **Batches** group missions by base **file** (one occupation), capped at 3, because PPK loads one
  base per run. The same physical control point occupied on two days = two separate files = two
  batches — don't merge them.

## Gotchas
- **Leap seconds / time systems:** RINEX header times are GPS; `.nav`-derived UTC is GPS − 18 s.
  Compare bracketing in GPS seconds (both sides) — the 18 s never flips a real bracket but stay
  consistent. `analyze.py` compares GPS-to-GPS.
- **Midnight-crossing windows:** a base logged 14:50 → 01:10 next day still brackets an evening scan;
  the code uses absolute GPS seconds so this just works.
- **Off-project sessions:** real acquisitions in other locations (a different town's bench test, a
  scan 100 mi away) are valid but no project base covers them — they land on the "No Base" sheet.
  That's correct, not a bug.
- **Position filter box:** `phoenix_lib.MT_BOX` is all-Montana on purpose. Too tight a box silently
  drops real acquisitions in other parts of the state. For a project outside Montana, widen/replace it.
- **Excel on Windows:** the xlsx `COUNTIF` counter can't be recalculated by the LibreOffice helper on
  Windows (no `AF_UNIX`); Excel computes it on open. Not a file error.

## Typical end-to-end
```
python scripts/analyze.py --sessions E:\...\Processing --bases <RINEX_A> --bases <RINEX_B> \
    --control control.csv --control-points 1,2,5 --policy furthest --max-mi 10 --out-dir OUT
python scripts/make_kml.py --acq OUT\acq_data.json --out OUT\acquisitions.kml --footprints --agl 50
python scripts/build_plan_xlsx.py --out-dir OUT --out OUT\Processing_Plan.xlsx --project "Fergus Hilger-to-Roy"
```
