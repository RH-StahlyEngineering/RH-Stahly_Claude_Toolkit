# Camera photogrammetry missions (Sony ILX-LR1)

Camera specs, per-flight limit and the time model live in [payloads.md](payloads.md). The code is the source of truth for settings: each script's docstring lists its config keys.

| Script | Job |
|---|---|
| `scripts/tradeoff_sweep.py` | Ranks options against constraints (`SITE`, `CONSTRAINTS`, `SWEEP`, `ORBITS` at the top) |
| `scripts/camera_plan_set.py` | Builds the plan set from a config (`row_config(SITE, row)` from the sweep) |
| `scripts/orbits.py` | Opt-in orbit pattern |
| `scripts/walls.py` | Building-wall coverage check |
| `scripts/viz3d.py` | 3D HTML view: terrain, paths, every photo footprint |
| `scripts/plan_outputs.py` | HOME suggestion, KML/CSV/MD summaries, save with supersede |

## Workflow

Each step ends when RH has answered; the sweep always runs before the build.

1. **Q&A — confirm defaults.** Show every camera default below and get RH's yes or his change.
2. **Set constraints.** GSD, blur, overlaps, battery cap, obliques yes/no, orbits yes/no → `CONSTRAINTS`.
3. **Run the sweep** (`py tradeoff_sweep.py`) and show the ranked table.
4. **RH picks a row.**
5. **Build** with `camera_plan_set.py` from that row's config. A "refused" report (exit 2) means a path left the DEM: get a bigger DEM (see run-outs below).
6. **Checks:** every flight under the payload limit; first-leg gimbal check (below); wall check when a building is the target.
7. **3D view** (`viz3d`) for RH to look over.
8. **Save** with `save_to`; an older set of the same name moves to `superseded_<date>_<reason>/`.

## Camera defaults — offered, confirmed, never silent

Offer each one in the Q&A; apply only what RH confirms.

- Shutter 1/1000 s
- Motion blur ≤ 0.75 px
- Fly 15% under the blur-limited speed (`speed_margin`)
- Trigger every 2 s (the camera's minimum)
- Manual exposure at f/5.6, Auto ISO
- RAW
- Focus at Infinity

**Current defaults, RH to confirm:**
- Oblique side-overlap floor **55%** in the sweep (`min_obl_side_pct`). RH's old script used 60%; the builder's near-edge model gives 57.7% for the row he chose at Toole.
- Wall-check occlusion ignores lidar surface cells within **3 m** of the building box (`walls.py`). A stricter 1 m fails the Toole west face on 2 low points near trees.

## RH's glossary

- **slow** = ≤ 8 mph.

## Patterns

- **One file per pattern** (nadir, each oblique direction, orbits), split further by battery. The pitch is in the file name (`_nadir90`, `_oblA45`).
- **Obliques:** 2 grids by default, `oblA` along the block axis and `oblB` across, at -45°. Orbits only when RH asks.
- **Orbits:** the ring pitch must aim at the target for that ring's radius and height (`orbits.py` derives it).
- **Wall check:** runs when `building` is set; pass rule in `walls.py`'s docstring.
- **Custom DEM = plain waypoints.** Plans are terrain-baked AMSL waypoints from the given DEM, not AMC terrain-follow surveys.

## Gimbal rule

Each plan sets its pitch with MAV_CMD 205 (gimbal control) at the start, and the pitch is in the file name so the pilot can see it. On the first leg of every file, the pilot checks the camera is at that pitch. If it is not, he sets it with AMC's Pitch buttons and flies on.

## Time model

The camera time model in [payloads.md](payloads.md) is provisional: recalibrate it from flown logs, and treat plans near the limit as uncertain until then.

## Toole lessons (Toole County Courthouse, 2026)

- **Show the options as a sweep.** Silently applied defaults blew the plan up to 12 batteries; laying out the trade-offs let RH pick a row that fit.
- **The 2 s trigger caps speed.** Above about 0.75 px blur, the trigger interval, not the shutter, limits speed, so a looser blur limit buys no time.
- **Obliques are most of the flight time.** Size them first. Open option: fly them higher than the nadir, since RH's GSD rule covers only the nadir.
- **Orbit pitch must match the ring geometry.** The first orbit pitch was set without it and had to be redone; derive it from radius and height.
- **The DEM must include the run-outs.** Oblique run-outs go `runout_m` past the limits; a DEM cut to the limits refuses the build.
