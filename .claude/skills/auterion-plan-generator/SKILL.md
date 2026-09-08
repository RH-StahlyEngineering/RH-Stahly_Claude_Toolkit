---
name: auterion-plan-generator
description: Generate and modify Auterion Mission Control / QGroundControl .plan files for drone LiDAR / photogrammetry missions. Use when the user asks to create a flight plan, build a .plan file, design a LiDAR survey, add figure-8 calibration patterns, convert a KML to a flight plan, fix a plan that won't load on the RC controller, estimate flight duration, or work with terrain-following missions in Auterion.
when_to_use: "Create flight plan; generate .plan; Auterion mission; QGroundControl; LiDAR survey; figure-8 calibration; terrain follow; KML to plan; mission duration estimate; controller-loadable plan; fix plan format"
---

# Auterion / QGroundControl .plan generator

This skill encapsulates everything learned about building, modifying, and validating `.plan` files for Ryan's miniRanger / PX4-multirotor LiDAR workflow. Read [constants-and-variables.md](constants-and-variables.md) **and** [known-pitfalls.md](known-pitfalls.md) before generating or editing any plan — both contain hard-won knowledge that is not derivable from the file format alone.

## When to invoke

- "Generate a flight plan for ..."
- "Build a .plan from this KML"
- "Add figure-8s to this mission"
- "This .plan won't load on the controller — fix it"
- "How long will this mission take?"
- "Tweak the cross-line / trailing leg / home position in this plan"
- "Why is my mission flying at MSL instead of terrain-following?"

## Canonical LiDAR mission structure

Every LiDAR mission is assembled from the same building blocks. Speed never changes mid-mission. **What varies between missions is whether the figure-8 calibrations are present, and that depends on where the flight sits in a power-cycle envelope** (see *Session model* below). The survey + cross-line are mandatory on every flight; the figure-8s are conditional.

Building blocks, in order:

```
A. Header                  cmd 530 (mission options) + cmd 178 (set speed ONCE)
B. Climb to flight alt     1 waypoint at HOME, AGL = target
C. Figure-8 #1 (START cal) 11 waypoints (10 Gerono vertices + 1 closer = 10 legs)
                           — included ONLY if this is the first flight after power-up
D. Survey                  1 complex item (Manual-camera, FollowTerrain=true)
                           — MANDATORY on every flight, no exceptions
E. Cross-line              2 waypoints — perpendicular to flight lines,
                           positioned ONE AGL (line-spacing) from the survey
                           exit waypoint's lat/lon, toward polygon interior,
                           EXTENDED past polygon edges by CROSS_MARGIN each side
                           (Reading A: offset measured from the exit waypoint
                           coordinate, not from a polygon edge or swath edge)
                           — MANDATORY on every flight
                           — Purpose: transect the survey JUST COMPLETED in this
                             flight at a perpendicular angle, giving the LiDAR INS
                             a perpendicular ground-track to tie the parallel
                             transects together. "Previously flown" means the
                             CorridorScan/Survey from milliseconds ago in THIS
                             plan, NOT adjacent missions / yesterday's session.
                           — Placement rationale:
                             • Near exit (battery efficient — drone is already there)
                             • Inset by ONE AGL so it transects THROUGH the corridor
                               (not skimming the polygon edge)
                             • Extended past edges by CROSS_MARGIN so the drone
                               gets stable straight flight across the full swath
F. Figure-8 #2 (END cal)   11 waypoints centered at cross-line end
                           — included ONLY if this is the last flight before power-down
G. Return to HOME          1 waypoint == first waypoint (closed mission)
```

Variant item counts (assuming the same survey + cross-line shape):

**Survey-style** (the canonical, with standalone climb + cross-line + RTL waypoints):

| Flight role in its power-cycle envelope | Blocks included | Items |
|---|---|---|
| Single isolated flight (cold start, cold end) | A B **C** D E **F** G | **29** |
| First flight of a hot-swap session (cold start, hot-swap end) | A B **C** D E G | **18** |
| Middle flight of a hot-swap session (hot-swap start, hot-swap end) | A B D E G | **7** |
| Last flight of a hot-swap session (hot-swap start, cold end) | A B D E **F** G | **18** |

First waypoint and last waypoint must always share lat/lon (= HOME), regardless of variant.

**CorridorScan-style** (Fergus 1/2/3/4/... family — AMC-native CorridorScan handles
climb, internal transects, turnarounds, and RTL all inside its own `TransectStyleComplexItem.Items`; the OUTER mission.items list only carries the header, cal blocks, the CorridorScan, and the cross-line):

| Flight role in its power-cycle envelope | Outer items | Total |
|---|---|---|
| Single isolated flight (cold start, cold end) | cmd 530 + 11× fig-8 + CorridorScan + 2× cross-line + 11× fig-8 | **26** |
| First flight of a hot-swap session (cold start, hot-swap end) | cmd 530 + 11× fig-8 + CorridorScan + 2× cross-line | **15** |
| Middle flight of a hot-swap session (hot-swap start, hot-swap end) | cmd 530 + CorridorScan + 2× cross-line | **4** |
| Last flight of a hot-swap session (hot-swap start, cold end) | cmd 530 + CorridorScan + 2× cross-line + 11× fig-8 | **15** |

**Critical:** the cross-line is REQUIRED for CorridorScan flights too — don't be misled by the fact that the CorridorScan's internal `Items` array contains perpendicular jogs at the turnaround corners. Those jogs are ONE LINE_SPACING wide (= half the corridor width); the cross-line is CorridorWidth + 2·CROSS_MARGIN wide and provides the LiDAR INS reference the internal jogs don't. See `scripts/generate_fergus_pair1.py::build_cross_line` for the reference implementation. The cross-line goes AFTER the CorridorScan in the outer items list (between CorridorScan and fig-8 END in END-cal plans).

## Session model — when does each flight need calibration?

A **power-cycle envelope** is a contiguous run of flights flown without powering the drone down. Within an envelope, batteries get hot-swapped but the autopilot/IMU stays initialized — so the figure-8 IMU calibration only needs to bracket the *envelope*, not each individual flight.

Rules:

- **START cal (Figure-8 #1) is included iff this flight is the FIRST flight in its envelope** (drone was just powered up).
- **END cal (Figure-8 #2) is included iff this flight is the LAST flight in its envelope** (drone is about to be powered down).
- Hot-swap flights in between get neither — the cal from the envelope's first flight is still valid.
- A single isolated flight is *both* first and last in its envelope, so it gets both cals (the legacy 29-item structure).

**Canonical example (2-flight hot-swap session):**
- Flight 1: cold start → hot-swap end → blocks **A B C D E G** (18 items, START cal only)
- Flight 2: hot-swap start → cold end → blocks **A B D E F G** (18 items, END cal only)

**Why this matters:** putting a calibration on every flight wastes 3–5 min of battery per flight and re-calibrates an already-stable INS solution (no benefit). Omitting a calibration on a cold-start flight leaves the LiDAR INS solution unbracketed — point cloud quality degrades. The planner *must* know the session topology to call this correctly.

The bracketing also dictates where flights pair up geographically: hot-swap flights should share (or sit very close to) a common HOME so the operator can land, swap battery, relaunch without moving. When generating an N-tile corridor as a sequence of hot-swap pairs, group tiles into pairs with a shared HOME near the meeting point; each pair is its own power-cycle envelope (flight A = start cal, flight B = end cal).

## Workflow

### Generating a new mission from a polygon (KML or vertex list)

**Run the structured Q&A below first.** Don't invent defaults — the user has tight per-mission preferences. Defaults shown are the *current standing values* the user has confirmed; still offer them rather than silently using them.

#### Structured Q&A — run before generating any new plan

Group the questions into phases. Use `AskUserQuestion` when you have 2–4 related ones; otherwise ask conversationally. **Skip a phase only when its answers are already in the conversation context.**

**Phase 1 — Mission identity (REQUIRED)**

1. **Mission name?** (e.g. "fergus_electric_lidar_2") — used for the output filename.
2. **Polygon source?** Choose: KML file path / paste lat,lon vertices / reuse existing .plan polygon.
3. **HOME point — lat, lon?** This is the first AND last waypoint. User-defined per mission; do not default to `plannedHomePosition` from the base file unless the user says so.
4. **Session position?** — drives whether to include START cal (Figure-8 #1) and END cal (Figure-8 #2). Must be one of:
   - **Single isolated flight** → both cals (29-item structure)
   - **First flight of a hot-swap session** → START cal only (no end cal — drone keeps power)
   - **Middle flight of a hot-swap session** → neither cal (drone keeps power both ways)
   - **Last flight of a hot-swap session** → END cal only (no start cal — drone already calibrated from envelope's first flight)

   If the user is generating a *group* of plans, ask once about the session topology (e.g. "two flights, hot-swap in between") and infer the per-plan role from position. See *Session model* above.

**Phase 2 — Survey parameters (REQUIRED, defaults offered)**

4. **AGL_TARGET** (meters above terrain) — default **40**. Sets both flight altitude AND line spacing AND swath/2 (FOV 90° convention).
5. **SPEED** (m/s, constant throughout mission) — default **8**.
6. **Flight-line direction?** Auto (perpendicular to polygon long axis), or specify angle in degrees. AMC convention: 270 = E-W lines, 0 = N-S lines.

**Phase 3 — Calibration parameters (defaults usually fine)**

7. **Figure-8 duration** (seconds per loop) — default **15**.
8. **CROSS_MARGIN** (meters past polygon edges) — default **25**.
9. **TurnAroundDistance** (meters) — default **15.24** (50 ft).

**Phase 4 — Payload / camera (ask once per payload; reuse afterwards)**

10. **Payload name?** (e.g. "miniRanger LiDAR", "RGB photogrammetry")
11. **AdjustedFootprintFrontal** (m) — varies by payload.
12. **AdjustedFootprintSide** (m) — typically equals AGL_TARGET under the 90° FOV convention.
    Camera mode is hard-coded to `"Manual (no camera specs)"` — don't ask about sensor/focal/image dims.

**Phase 5 — Output (REQUIRED)**

13. **Output .plan path?** Default location: `C:\Users\rharbach.STAHLY\Documents\Auterion Mission Control\Missions\<mission_name>.plan`
14. **Base .plan to inherit constants from?** Default: `examples/base_terrain_following.plan` (bundled with the skill). The base provides camera block defaults, vehicle/firmware type, and terrain-follow settings — see [constants-and-variables.md](constants-and-variables.md).

#### After Q&A

1. **Run the generator** — see [scripts/generate_lidar_mission.py](scripts/generate_lidar_mission.py). It handles geometry, figure-8 placement, cross-line placement (Reading A or HOME-nearest-edge fallback), and DEM-baking via USGS 3DEP. Pass session-position flags so it includes/skips the right calibrations.
2. **Verify counts match the expected variant.** Look up the count from the variant table above based on session position: 29 (single), 18 (first OR last of session), or 7 (middle). Exactly **one** `cmd 178`. First waypoint == last waypoint == HOME. Survey + cross-line present on every variant.
3. **Verify session bracketing is correct for the group.** If generating multiple plans for a hot-swap session, confirm: exactly one plan has START cal, exactly one has END cal, both reside in the same envelope, and they share/neighbor HOMEs so the operator can land-swap-launch without moving.
4. **Run coverage check.** If a KML target was provided in phase 1, run [scripts/coverage_check.py](scripts/coverage_check.py) against it to confirm 100% coverage before declaring done. For multi-plan operations (corridor tiling, gap fills), use [scripts/coverage_check_multi.py](scripts/coverage_check_multi.py) — it unions per-plan ground swaths (CorridorScan envelope = `CorridorWidth/2 + AGL/2` perpendicular each side, plus turnaround caps) and intersects with the target KML. Optionally emits a KML of uncovered polygons for visual gap inspection.
5. **Run VLOS (Visual Line of Sight) check.** Use [scripts/los_check.py](scripts/los_check.py) on every plan. It samples the drone's full flight path (standalone waypoints + CorridorScan inner Items) at 25 m, shoots a 100-sample 3D line from operator eye (launch ground + 2 m) to drone (AMSL at AGL), and flags any sample where terrain rises above the LOS line. Output: `% VLOS`, worst block height, distance from launch where worst block occurs. Bare-earth DEM only — does not model trees/buildings. If a plan fails, use [scripts/scout_vlos_alternatives.py](scripts/scout_vlos_alternatives.py) to find the closest VLOS-clean alternative launch position within a configurable radius.
6. **Tell the user to open in AMC once.** AMC will regenerate survey transects + camera commands (Behavior A — see [known-pitfalls.md](known-pitfalls.md#1-terrain-recomputation-is-survey-only)). Save from AMC, then push to controller.

### Modifying an existing plan

1. **Read it.** Use `Read` or a small Python `json.load`.
2. **Identify what's a constant vs a variable.** Never edit a constant unless the user explicitly asks. See [constants-and-variables.md](constants-and-variables.md).
3. **Preserve everything you're not touching.** Carry dicts by reference where possible; renumber `doJumpId` sequentially at the end.
4. **Re-save minified.** RC controllers reject pretty-printed JSON. Use [scripts/minify_plan.py](scripts/minify_plan.py) or `json.dumps(p, separators=(',', ':'))`.

### Fixing a plan that won't load on the controller

Almost always one of these (see [known-pitfalls.md](known-pitfalls.md#2-rc-controller-rejects-pretty-printed-json)):
- CRLF line endings + pretty-printed JSON → minify with LF only
- CorridorScan complex item → replace with Survey or split into waypoints
- Polygon with hundreds of vertices → decimate

### Verifying KML coverage

Ryan's LiDAR convention: **total FOV = 90°, line spacing = AGL**. That means the ground swath per pass = `2 · AGL`, and adjacent passes overlap by 50%. Use [scripts/coverage_check.py](scripts/coverage_check.py) to confirm the survey footprint fully contains the target KML polygon before flight:

```bash
python coverage_check.py mission.plan target.kml --grid 1.0
```

It reports coverage %, transect count, and lat/lon of any uncovered points so gaps can be located on a map. **Always run this when generating from a KML.**

### Estimating flight duration

Use [scripts/estimate_flight_time.py](scripts/estimate_flight_time.py). Calibrated model (RMSE 0.18 min over 7 plans):

```
AMC_min ≈ 1.05·survey_min + 1.08·corridor_min + 1.97·transit_min
```

The transit ×1.97 multiplier captures climb/decel that the naive Σ(d/v) misses.

## Scripts (call these — don't reimplement)

| Script | Purpose |
|---|---|
| [scripts/generate_lidar_mission.py](scripts/generate_lidar_mission.py) | Full mission generator: polygon + HOME + AGL → .plan |
| [scripts/figure8.py](scripts/figure8.py) | Gerono-lemniscate vertex generator (10 unique + 1 closer = 10 legs) |
| [scripts/dem_lookup.py](scripts/dem_lookup.py) | USGS 3DEP terrain elevation, ~1 s/point, free, no auth |
| [scripts/minify_plan.py](scripts/minify_plan.py) | Strip whitespace + CRLF for RC controller compatibility |
| [scripts/estimate_flight_time.py](scripts/estimate_flight_time.py) | Calibrated AMC duration estimate from .plan alone |
| [scripts/inspect_plan.py](scripts/inspect_plan.py) | Quick structural dump for verification / debugging |
| [scripts/coverage_check.py](scripts/coverage_check.py) | Verify a single .plan survey fully covers a target KML polygon (LiDAR FOV math) |
| [scripts/coverage_check_multi.py](scripts/coverage_check_multi.py) | Union N plans' ground swaths, intersect with target KML, emit gaps as KML polygons |
| [scripts/los_check.py](scripts/los_check.py) | VLOS check per plan: bare-earth viewshed from operator eye to drone at every flight-path point |
| [scripts/scout_vlos_alternatives.py](scripts/scout_vlos_alternatives.py) | For a launch with VLOS issues, sample a 2 km / 200 m grid for the closest VLOS-clean alternative position |
| [scripts/analyze_gap_fills.py](scripts/analyze_gap_fills.py) | Iteratively place new launches in worst gaps until reaching a coverage target; rank tile-extension opportunities by acres-per-km |
| [scripts/find_photogrammetry_launches.py](scripts/find_photogrammetry_launches.py) | Minimum-launch set-cover for photogrammetry areas — 3-mi radius + 100% VLOS + 400 ft AGL + ≤60 m from centerline. See lesson #16 for the operating constraints; lessons #18–22 for what made the algorithm choices land right. |
| [scripts/build_3color_5vs8_kml.py](scripts/build_3color_5vs8_kml.py) | Trade-off visualization: classifies sample points as covered by both / only A / only B between two candidate launch sets and emits a 3-color KML. Pattern is reusable for any "N launches at 100% vs N-3 at 97%" decision. See lesson #21. |
| [scripts/generate_powerline_pairs.py](scripts/generate_powerline_pairs.py) | LiDAR powerline-corridor mission generator. Polyline = the wire (not the road), 2-transect CorridorScan with built-in lateral clearance per lesson #25 (`min_lat = AGL × tan(15°)`). Includes `SKIP_LAUNCHES_1BASED` filter for the no-overlap subset selection per lesson #29. |
| [scripts/scout_l6_l9_powerline.py](scripts/scout_l6_l9_powerline.py) | VLOS-alternative scouting against a SPECIFIC pair of plans (not the prior scout_vlos_alternatives.py's hardcoded list). Use as the template when you need to re-scout after switching from highway-polyline to powerline-polyline geometry — flight paths differ, alternatives need re-verification. |
| [scripts/powerline_mission_report.py](scripts/powerline_mission_report.py) | Operational summary per lesson #32: per-plan flight time, total swath acres split once vs twice-covered, coverage of target KML as N/D fraction, PPSM math at user-reported per-pass values. Reusable for any multi-plan mission set. |

All scripts use stdlib only (`json`, `math`, `urllib.request`) plus `shapely` for polygon set ops. The DEM raster handling uses `tifffile` for bilinear reads; `dem_lookup.ensure_dem_for_bbox` caches a per-bbox TIFF locally so per-point lookups are sub-microsecond.

## Multi-tile corridor missions (NEW workflow)

When the user gives one large KML and wants it sliced into many flyable .plan files (typical for utility/road/pipeline corridors), use the **end-to-end orchestrator**:

```bash
python scripts/build_corridor_set.py \
  --kml /path/to/corridor.kml \
  --homes /path/to/HomePoints.kml \
  --out-dir "C:/.../Auterion Mission Control/Missions" \
  --fc-subdir Fergus_corridor \
  --prefix fergus \
  --agl 70 --along 1000 --perp 158 \
  --target-amc 11 --duration-min 8 --duration-max 12 \
  --gap-thresholds 8000,2000,500 \
  --simplify-tolerance 10 \
  --east-to-west
```

This single command runs: DEM cache → skeletonize → place tiles → place homes → generate plans → refine outliers → 3 gap-fill passes → Douglas-Peucker simplify → rename E→W → verify.

### Required Q&A for corridor missions

1. **KML path** — single polygon, can be complex (corridors with branches/taps).
2. **HOMEs KML path** — existing launch points (will be augmented; original ones NEVER moved).
3. **Output Missions root + corridor subdir name.**
4. **AGL** — line spacing equals AGL per skill convention. Typical: 40 (RGB), 70 (LiDAR).
5. **Duration window** — `[duration_min, duration_max]` (e.g. [8, 10] or [8, 12]). Default 8–10.
6. **Target AMC** — middle of window; influences home placement.
7. **Tile size** — `--along` (e.g. 670 at AGL 40, 1000 at AGL 70) × `--perp` (~corridor width, ≤ 4·line_spacing).
8. **E→W or W→E ordering** — match the operator's intended flight sequence.
9. **Gap-fill thresholds (m²)** — list of cutoffs for successive small-gap fills. Skip if you want only the main spine tiles.
10. **Cleanup confirmation** — orchestrator deletes only `<prefix>_*.plan` from the root before output. Confirm no naming collision with other plans.

### Operational rules (learned the hard way)

- **Cleanup scope is `<prefix>_*.plan` only.** Never touch calibration plans (hilger_*, RBH_*, CourthouseLidar, stahlytest, etc.). Moving them to `_archive` broke the CSV regression check and frustrated the user.
- **East-to-west renaming on the FINAL copy to the Missions root.** Internal `tiles_sized_v2.json` uses generation-order IDs; the visible `<prefix>_NNN.plan` should be in the operator's flight order.
- **Gap-fill tiles get a distinct prefix.** They're optional flights chasing the last ~10% of coverage; renaming as `<prefix>_gap_NNN.plan` keeps them grouped separately so the operator can choose to skip them.
- **AMC sees the Missions root only, not subfolders.** Don't put plans in `Fergus_corridor/` and expect them to appear in AMC's launcher — they must be copied to the root.
- **Polygon simplification: use Douglas-Peucker (shapely), not nearest-neighbor decimation.** Nearest-neighbor chops corners off and creates surveys that miss real area. DP with 10 m tolerance keeps the corner structure and drops only collinear runs.
- **Coverage vs overlap is a tradeoff.** Aggressive small-gap fills (200 m²) push coverage to 99.9% but each fill is an isolated tile (fails the ≥10% neighbor-overlap constraint). For most operations, 99% coverage with no isolated tiles beats 99.9% with many.

### DEM caching is essential at scale

Per-point USGS 3DEP HTTP averages ~5 s/call (with retries). For 250 plans × 26 lookups each = ~3 hours. **Always call `ensure_dem_for_bbox(lat_min, lat_max, lon_min, lon_max)` at the start of any multi-tile run** — it downloads the corridor TIFF once (~25 MB for a 40 × 13 km bbox at 10 m resolution) and serves all subsequent lookups from memory at 0.4 µs each. Same batch then completes in ~10 seconds. Cache lives in `~/.claude/dem_cache/` and is reused across sessions.

The orchestrator does this automatically before any DEM-heavy phase.

---

## Lessons learned — Fergus corridor (2026-06-18 v2)

The Fergus run kept evolving as the user refined the spec. Key items beyond the original notes below:

### User overrides to the original spec are normal — make the tooling parameterizable
- AGL changed mid-run from 40 → 70 m. Line spacing follows AGL (Ryan's convention). At AGL 70 a 158 m perpendicular tile gives 3 transects + 2 turnarounds (vs 4+3 at AGL 40). Survey time drops; needed ALONG bumped from 700 → 1000 m to keep AMC ≥ 8.
- Duration cap relaxed from 10 → 12 min. The valid `d_home` window widens with the cap; you can share homes across adjacent tile pairs (~halves the home count).
- Original spec said "AGL = 40 exactly"; the verifier had to be parameterized. Both checks (c2 range, c7 AGL value) need to track whichever values are current.

### Local DEM raster is a 14,000× speedup
For a corridor that fits in one bbox, download the USGS 3DEP elevation as a TIFF via the Image Server `exportImage` endpoint:
`https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer/exportImage?bbox=...&size=...&format=tiff&pixelType=F32&f=image`
At 10 m resolution a 42 km × 13 km corridor is ~24 MB. `dem_lookup.py` does bilinear interpolation from the in-memory array — 0.37 µs/lookup vs 5+ s per HTTP call. Batch of 250 plans drops from ~30 min to ~6 s. **Always cache the raster locally for large jobs.**

### Cleanup discipline matters on Windows AMC
- "Clean up old missions" means **only the fergus_*.plan files** — never the calibration plans (hilger_*, CourthouseLidar, RBH_*, stahlytest). Earlier I moved them to `_archive` and that broke CSV regression testing. Lesson: scope cleanup to the operation's own files.
- Lots of stale .plan files in Missions root bogs down AMC's startup. Keep root deduped.

### East-to-west ordering for field operations
When the operator is flying east-to-west, number the plans so `fergus_000` is eastmost and `fergus_NNN` (highest) is westmost. The placement script sorts tiles W→E for numerical IDs but the final copy to root is renamed E→W so the operator can just load them in order.

### Polygon simplification: Douglas-Peucker, not nearest-neighbor
A nearest-neighbor decimation (drop vertices closer than X m) can chop off corners — turning a 90° turn into a chord that misses real area. Douglas-Peucker (`shapely.Polygon.simplify(tol)`) preserves corners by keeping any vertex whose distance from the chord exceeds `tol`. For a 70 m line-spacing tile, 10 m tolerance is enough to drop ~90 % of vertices while keeping the survey footprint intact.

### Bearing/polygon coupling is a fixed-point
The spec's c8 check ("survey.angle = strict bearing of segments inside footprint") is co-dependent with the polygon: changing the bearing rotates the rectangle, which after clipping produces a different polygon, which has a different set of corridor segments inside, which produces a different strict bearing. Naively setting `sv['angle'] = strict_bearing(polygon)` works for c8 but rotates the polygon's perpendicular extent — which can push tiles over 3 turnarounds (c4 violation) and out of [8, 12] (c2 violation). The right approach is fixed-point iteration: rotate → clip → bearing → rotate → clip → bearing, until stable, then accept whatever (bearing, polygon) pair results, even if its bearing isn't exactly what k-longest-segments gave. Worth implementing as a permanent place_homes pass.

### Coverage gap filling needs a small-gap threshold to clear 99.5 %
Successive passes at `MIN_GAP_M2 = 8000 → 2000 → 500 → 200` move coverage from 87 % → 96 % → 99.3 % → 99.83 %. Each pass adds ~10–30 tiles. The trade-off: smaller gap tiles tend to have lower AMC (smaller survey), needing larger home offsets for [8, 12], which then makes c5 (overlap) worse because tile placements are forced far from neighbors. Coverage and overlap pull in opposite directions for narrow corridor sections.

---

## Lessons learned — Fergus corridor (2026-06-18)

Slicing a 1,622-acre corridor (42 km × ~155 m wide) into 8–10 min .plan tiles surfaced several constraints and pipeline issues. Captured here so future runs avoid the re-discovery cost.

### Hard finding: home-spacing dominates feasibility

The skill's duration model is `AMC ≈ 1.05·survey + 1.97·transit`. Survey time is shrinkable (smaller polygon → fewer transects). **Transit time is not** — it's bounded below by round-trip HOME ↔ survey-area distance. With cruise speed (the value `estimate_flight_time.py` uses for transit) = 15 m/s and the canonical mission overhead, **any tile farther than ~700 m from its assigned HOME predicts >10 min**. Sparse HOMEs (9 points along 42 km = ~5 km spacing) made **44 of 61 candidate tiles geometrically infeasible** for the [8, 10] cap. Surface this constraint to the user up front: tile count is bounded by `~2·n_homes` if HOMEs are spread, not by polygon area.

### `estimate_flight_time.py` uses cruiseSpeed (mission header) for transit, not the cmd-178 speed

The CSV calibration was happenstance-correct because all calibration plans had cruiseSpeed=15 and short transits. For new plans where the cmd-178 sets a different cruise (we use 8 m/s), the predictor still uses cruiseSpeed=15 for transit math. Real flight at 8 m/s would take longer. **The skill's predictor reflects AMC's displayed duration, not actual flight time.** If user wants actual flight time, set cruiseSpeed = cmd-178 speed in the .plan header.

### Analytic-survey shortcut: needed when AMC hasn't opened the file yet

The skill's `estimate_flight_time.split_minutes` returns 0 survey time when the survey item's inner `Items` is empty. Added an analytic fallback: `(n_transects · along_extent + (n-1)·TurnAroundDistance) / FlightSpeed`. n_transects = `ceil(perp_extent / line_spacing)`. CSV regression stayed at RMSE 0.18 (analytic path only fires when Items empty; calibration plans were unaffected).

### Tiling pipeline architecture (in this skill at scripts/)

- `corridor_tiler.py` — end-to-end driver with phases: skeletonize → spine walk → clip/resize → (calls generator).
- `tiling_helpers.py` — Sutherland-Hodgman clipping, k-longest-segment bearing, decimation, local projection.
- `generate_corridor_batch.py` — sequential batch over a list of sized tiles; ~6–8 s per tile dominated by USGS 3DEP lookups.
- `verify_corridor_set.py` — runs every END-STATE constraint against a directory of plans; emits `verification_report.json`.

### Skeletonization

Rasterize @ 10 m → `skimage.morphology.skeletonize` → endpoint/branch detection → vectorize into per-spine polylines. For the Fergus polygon: 8,809 vertices → 66,788 raster cells → 5,236 skeleton cells → 332 spines, longest 4,157 m. Filter spines by `min_spine_length=200 m` before laying tiles.

### k-longest bearing beats mean+std for tap-aware orientation

Original spec had ±1σ filter. On a tap junction the std blows up to ~37° and the filter admits everything. Switched to **k=10 length-weighted longest segments within a 1500 m local window**. Tracks corridor orientation through bends and ignores stub taps automatically. Verifier still uses the strict spec (k=10 of segments whose midpoints lie inside the footprint), with a fallback to a 500 m radius when the footprint is too small to contain segment midpoints.

### Tile width = 4 · line_spacing exactly — beware float precision

With AGL = 40 and TILE_WID = 160 exactly, floating-point drift in clipping produced polygons with perp_extent = 160.16 m → `ceil(160.16/40) = 5` transects → 4 turnarounds (spec violation, ≤3 required). Fix: set TILE_WID = 158 (buffer) or round() instead of ceil() when within 1 m of boundary. **The base file had `DistanceToSurface = 39.9288` (legacy from a manual-camera setup); set to exactly 40.0 to make the "AGL == line spacing" identity exact.**

### Cross-line geometry must be in flight-frame coords

Previous bug: cross-line endpoints were set in absolute N-S / E-W and extended past the polygon's lat/lon bounding box. For tiles oriented at arbitrary bearings (here ~65°–85°), this produced cross-lines that were (a) not exactly perpendicular to the flight transects, (b) extending hundreds of meters past the actual corridor edge. Fix: rotate polygon into flight frame (`y` = along, `x` = perpendicular), compute extents there, place cross-line endpoints at `perp_min - CROSS_MARGIN` and `perp_max + CROSS_MARGIN`, then unrotate. Now cross-line is exactly perpendicular and 25 m past actual polygon edges.

### Coverage check FOV math

LiDAR convention: total FOV 90°, line spacing = AGL → swath = 2·AGL, adjacent passes overlap 50%. `coverage_check.py` rasterizes the target KML at 1 m grid and tests each grid point against the union of swath strips (each strip = transect ± AGL perpendicular). 100% on self-coverage; cleanly identifies undercoverage with lat/lon of uncovered points.

### Plan-file regeneration vs in-place edit

After sizing+generation, fixing per-plan camera/terrain fields (DistanceToSurface, AdjustedFootprintSide) can be done **in-place** (json.load + edit + minified rewrite) without re-running the DEM-baking pipeline. Saves ~8 min per pass during iteration.

### Failure modes encountered

1. **Infeasibility** when home-to-tile distance exceeds ~700 m given 8-min lower bound and 1.97× transit multiplier. Mitigation: add HOMEs, relax cap, or skip tiles.
2. **USGS 3DEP timeouts** on consecutive single-point queries. Mitigation: 3-retry with 1-s backoff is sufficient; full-corridor batches of 1,500 lookups complete in ~10 min sequentially.
3. **Verifier c8 (angle-matches-bearing) unverifiable** for small footprints where no KML edges have midpoints inside. Fallback: 500 m radius around footprint centroid.
4. **TILE_WID = 160 + AGL = 40** gave 4 turnarounds (off-by-one via ceil) on tiles slightly clipped past 160 m. Use TILE_WID = 158 or accept 4-transect tiles by enforcing strict perp_extent ≤ 4·line_spacing.

---

## Lessons learned — Fergus full corridor (2026-06-18 evening, Pairs 1–18)

Captured the night a 28-mile Hwy 81 corridor with 9 user-provided launches went from "rough sketch + 4 km of working plans (Fergus 1/2)" to **38 minified, VLOS-verified, cross-line-equipped, AGL-rendering, AMC-loadable CorridorScan plans covering 90.95% of a 1622 ac corridor union polygon, with the remaining 9% mapped as 28 named gap polygons in a KML.** What actually made that work, in order of usefulness:

### 1. Segment projection beats nearest-vertex when snapping a launch onto a sparse-vertex KML
The HighwayCenterline.kml has dense (~1.5 m) sampling for most of its length but several multi-km segments where consecutive vertices are 4 km apart. `nearest_idx` snapped Launch 5 to a vertex **3 km away** from where the highway actually runs, and forced Pair 4 + Pair 5 to share the same meeting point. Switching the snap to "nearest point on any KML segment" — local equirect projection of the launch onto each edge, take the minimum — dropped the worst case from 3092 m to 21 m. **For any KML-based snap, do segment projection, not vertex snap.** See `generate_fergus_all_pairs.project_onto_centerline`.

### 2. Insert the projected meeting into the centerline before bidirectional walk
The walk-east/walk-west function needs a vertex at the meeting point to anchor symmetric tile reach. If the meeting was projected onto a segment (not coinciding with a vertex), `insert_meeting_into_centerline(seg_idx, frac, meeting_pt)` splices a new vertex in. Skip this and your tiles drift off-center.

### 3. Warm the DEM cache for the FULL operation bbox, generously padded
Per-point USGS 3DEP HTTP averages 5+ s/call. Local raster from a cached TIFF: 0.4 µs. For 38 plans × ~200 path points × 100 LOS samples = 760K lookups, that's the difference between 1 hour and 0.3 seconds. **`ensure_dem_for_bbox` once at the start, padded to cover all flight paths + cross-line endpoints + LOS sample lines.** Use `pad = 0.05` (~5 km) for safety. Skimping on pad bites at the edges (see pitfall #14).

### 4. The skill's LiDAR FOV convention works for CorridorScan coverage too
Skill canonical: swath per pass = 2·AGL, line spacing = AGL, 50% overlap. For CorridorScan with `CorridorWidth = 2·AGL` (2 transects), outer ground-coverage envelope = `CorridorWidth/2 + AGL/2 = 1.5·AGL` perpendicular each side. For AGL 70.104 that's ±105.16 m → 210.3 m total swath. Use this as the buffer when computing per-plan coverage polygons; union N of them for total coverage. Add turnaround caps at the polyline endpoints (the drone is still flying with LiDAR on during the turn run-up).

### 5. Surveyor's "skip <10 ac yields" rule for iterative gap-filling
When iteratively placing new pairs to fill gaps, the algorithm finds the largest remaining uncovered polygon, places a pair at its high-elevation centerline point, recomputes coverage, and repeats. Sometimes the gap is wider perpendicular to the centerline than a single 210 m swath can fill — the pair only picks up ~5 ac of a 30 ac gap. **A surveyor will not fly 8 minutes of flight to gain 5 ac. Filter those iterations out and let the gap stay open.** For the Fergus corridor this dropped 1 pair (5.64 ac) without affecting whether we hit the coverage target.

### 6. High-elevation centerline points are a natural VLOS hedge
The gap-fill algorithm picks the highest-elevation centerline point inside each gap — primarily for the operator's "launch above the corridor it serves" criterion. As a free side-effect, **all 9 algorithmic launches passed 100% VLOS** on bare-earth terrain check, while several of the user's hand-picked road-access launches (L6–L9 in valley sections) failed. Elevation maxima correlate strongly with line of sight because they avoid being blocked by surrounding terrain. Worth remembering when an operator's preferred launch site fails VLOS — search nearby high points first.

### 7. VLOS check as a mandatory pre-commit step
`scripts/los_check.py` runs in a fraction of a second per plan and catches real terrain occlusion before the operator drives to the field and discovers the drone disappears behind a hill. **Wire it into the post-Q&A verification flow alongside coverage_check.** When a plan fails, `scripts/scout_vlos_alternatives.py` searches a 2 km / 200 m grid for the closest VLOS-clean alternative within `ROAD_ACCESS_M` of the centerline — output is one or two recommended coordinates the operator can drive to instead.

### 8. East-to-west file numbering matches operator flight order
The operator drives Hwy 81 east-to-west (typical Lewistown-based operations). Fergus 1 is easternmost, Fergus 38 is westernmost. Within a pair, the east tile is the *first* flight (START cal, lower file number) and the west tile is the *second* flight (END cal, higher file number). Always check this — generation-order numbering doesn't match flight-order numbering.

### 9. CorridorScan-style canonical structure is different from Survey-style
The skill's variant table now distinguishes Survey-style (with standalone climb + cross-line + RTL → 29/18/7 items) from CorridorScan-style (AMC handles climb + transects + RTL inside the CorridorScan's own `TransectStyleComplexItem.Items`; outer items list only carries header + cals + the CorridorScan + cross-line → 26/15/4 items). Don't conflate the two.

### 10. Cross-line is required on CorridorScan flights too — the internal turnaround jogs are NOT it
A CorridorScan's inner `Items` array contains a perpendicular jog at the far turnaround (one line-spacing wide). That is geometry for the autopilot to make the turn, not the cross-line. The cross-line is a standalone 2-waypoint item that goes AFTER the CorridorScan in the outer items list, perpendicular to flight lines, ONE LINE_SPACING inset from the survey exit, `CorridorWidth + 2·CROSS_MARGIN` wide.

### 11. "Previously flown mission" — for the cross-line — means the survey just finished in THIS flight
Not the adjacent pair, not yesterday's session. The cross-line transects the corridor that the drone just surveyed, perpendicular to those flight lines, giving the LiDAR INS a perpendicular ground-track constraint when stitching the parallel transects. This is mostly battery-efficient by design (cross-line near the exit) — and the "good overlap with previously flown" is between cross-line and the SAME flight's CorridorScan transects, not between flights.

### 12. AMC display modes depend on populated Items + VisualTransectPoints, not just the field values
Even with `globalPlanAltitudeMode: 3`, `FollowTerrain: true`, `DistanceToSurface: <AGL>`, AMC defaults the survey panel to HGT/MSL display if `TransectStyleComplexItem.Items` is empty. Pre-populate both Items and VisualTransectPoints from the polyline + CorridorWidth + AGL at generation time (see `build_corridor_inner_items`).

### 13. frame=0 + DEM-baked AMSL is "AGL" — frame=10 is broken-in-AMC AGL
Pitfall #3 is a hard rule. A user preference to "have waypoints in AGL" doesn't override it — the right answer is `frame: 0` with `altitude = terrain_amsl(lat, lon) + AGL_target` at every waypoint. Flight behavior is identical (drone flies at AGL above ground), AMC display works, and the elevation profile shows the waypoints correctly above the terrain line.

### 14. DEM cache mtime ordering can mask a larger TIFF with a smaller one
`_try_load_local_dem` picks the most-recently-mtime TIFF first. If you call `ensure_dem_for_bbox` with a tight bbox AFTER a wider one is cached, the tight TIFF becomes the latest-mtime and gets picked, leaving your edges uncovered. Either pad the bbox to cover everything from the start, or delete the smaller TIFFs to let the bigger one win the sort. Captured as pitfall #15.

### 15. Off-centerline polylines are valid for perpendicular-gap standalone flights
The skill canonical is "polyline = centerline." That's right for the main spine — every Fergus3..Fergus38 follows the highway. But Gap 25 (2026-06-18, near L6) sat **entirely south of the centerline**: the corridor union polygon is wider than the centerline-aligned 210 m swath at that location, and Pair 6 already filled the centerline strip. A centerline-aligned standalone (Fergus39 v1) duplicated Pair 6 and added 0.15 ac.

**Fix:** for a perpendicular-gap fill flight, offset the polyline perpendicular to the centerline by exactly enough to butt the new swath against the existing swath edge (no overlap, no gap). For a 2-transect CorridorScan (CW = 2·AGL), the offset = CW/2 + AGL/2 = 1.5·AGL ≈ 209 m for AGL 70.104. Use `perp_offset_path(centerline_polyline, -OFFSET_M)` from `generate_fergus_pair1` (negative offset = clockwise from forward = south when the polyline is going east; check tangent direction for other orientations). Fergus39 v2 with a 209 m south offset filled **100%** of Gap 25 (8.96 of 8.97 ac) in a single 26-item standalone flight (`scripts/rebuild_fergus39_offset.py`).

This is a deliberate, documented deviation from "polyline = centerline" — limited to standalone perpendicular-gap fills, not anything along the main spine. The cross-line still goes ONE LINE_SPACING inset from the polyline exit, perpendicular to the LOCAL polyline tangent (not the centerline tangent).

### 16. Photogrammetry-with-VO has a 3-mi radius constraint that LiDAR doesn't
Ryan flies two distinct mission modes with very different operating constraints:

- **LiDAR / corridor missions** (Fergus 1-39): single operator. The constraint is battery / flight-time — that's where the 1.8 km hot-swap tile pattern came from. No drone-to-operator distance rule was applied; tile reach was bounded by flight duration.
- **Photogrammetry missions with 2-person crew** (Part 107.33 with VO = Visual Observer): the constraints, all hard, are
  1. **Drone within 3 mi (4828 m) of the operator at all times.** Ryan's operational margin for VO mode, not a universal Part 107 number.
  2. **100% bare-earth VLOS** from operator (ground + 2 m) to drone (terrain + AGL) at every flight position.
  3. **AGL = 400 ft (121.92 m).** NOT the 40 m skill default for generic RGB. The higher altitude meaningfully relaxes VLOS but the 3-mi radius remains binding — at 26 mi corridor length the theoretical minimum is ~5 launches.
  4. **Launch within 60 m perpendicular of the highway centerline** (Hwy 81 / HighwayCenterline.kml). Operators stand on the shoulder; private rangeland requires landowner coordination. Filter candidate launches with `LineString.distance(Point) <= 60` against the centerline before running set cover.

This is a different *kind* of problem from picking one launch per gap. It's a **minimum-launch set cover**:
- Universe = grid-sampled drone positions over the survey polygons (at terrain + AGL).
- Sets = each candidate launch's coverage = points within 3 mi euclidean AND with VLOS clear.
- Solve greedy: at each step, pick the candidate covering the most still-uncovered points; remove from universe; repeat until empty.

`scripts/find_photogrammetry_launches.py` is the reference implementation. Same VLOS check as `los_check.py`, same DEM source. The 3-mi rule comes from the saved memory `feedback-photogrammetry-3mi-radius-2person.md` — check that file (or ask Ryan) when an operating-constraint isn't obvious from the mission KML.

**Don't confuse the modes.** If Ryan asks about LiDAR corridor work and you apply the 3-mi radius, you'll over-constrain it. If he asks about photogrammetry with a 2-person crew and you don't apply the radius, you'll produce single-launch-per-area plans that violate his actual operating envelope.

### 17. Skipping inefficient iterations requires NOT updating coverage state for the skip
A subtle iteration bug: my first pass at the surveyor's "<10 ac yield skip" filter still updated the simulated coverage when skipping (to avoid an infinite loop re-targeting the same gap). That gave a wrong final coverage % that included un-flown pairs. **Fix:** keep an "exhausted" set of gaps you've considered-and-rejected, NEVER update coverage for skipped iterations. Computed final % = baseline + (sum of selected pairs' coverage gains).

---

## Lessons learned — Fergus photogrammetry (2026-06-19)

Same 10-area corridor (Fergus Hilger-Roy, 10 mission-area polygons tiling the same ~26 mi Hwy 81 stretch as the LiDAR work) — but a fundamentally different mission mode and constraint set. The 4 constraints from lesson #16 (3 mi radius, 100% VLOS, 400 ft AGL, ≤60 m from centerline) ran as a greedy set-cover and ended at **8 launches for 100%** / **5 launches for 97.3%**. Captured what made that work.

### 18. Identify the binding constraint before changing parameters

Going from 40 m AGL to 400 ft (121.92 m) AGL DID NOT reduce the launch count (both gave 7 in the unconstrained run). **The 3-mi radius was binding, not VLOS.** At 26 mi corridor length and 6 mi diameter per launch, theoretical minimum ≈ 5 launches no matter how generous VLOS is. When Ryan asks "can we reduce by changing X," first check which constraint is binding — relaxing a non-binding constraint changes nothing.

### 19. Adding a centerline-proximity constraint costs ~1 launch per ~14% candidate pool shrink

The 60 m centerline filter shrank the candidate pool 646 → 161 (~25% remained). Launch count went 7 → 8 (+1, ~14% increase). Heuristic for similar accessibility constraints in the future: a tight perpendicular-distance filter that cuts candidates to ~25% of the unconstrained pool will typically add 1 launch on top of the unconstrained set-cover result. Useful when budgeting field-time conversations with Ryan.

### 20. Coverage targets are continuous — show the diminishing-returns curve

Greedy set-cover's marginal coverage drops fast. For the 8-launch / 100% Fergus photogrammetry set:
- Launches 1–5: cumulative 28.7%, 53.8%, 74.0%, 88.9%, **97.3%**
- Launches 6–8: each adds <1.5%, last one adds 0.70%

Ryan often wants to see the trade-off, not just "the answer." When set-cover returns N launches, also report the cumulative coverage at N-1, N-2, N-3 — and offer the lower-N option if those tail launches each pick up <1% (the "mop-up" tax of going from 97% to 100%). That gave Ryan the actual decision: "8 launches for full coverage, or 5 launches and skip 34 specific corner points?"

### 21. Three-color comparison KMLs make the trade-off concrete

When presenting a "save N launches at cost of C% coverage" trade-off, build a KML with sample points classified by **{covered by both options, only by option A, only by option B}** in 3 distinct colors. Lets Ryan literally see which specific corners of which polygons get dropped — way more useful than just stating an aggregate percentage. Reference implementation: `scripts/build_3color_5vs8_kml.py` (built via Workflow with adversarial verify pass).

### 22. The `dem_lookup.py` skill-bundled `fergus_dem.tif` doesn't cover the photogrammetry-areas SW corner

The skill ships `fergus_dem.tif` with bbox lat [47.24, 47.36] lon [-109.38, -108.8]. The photogrammetry Area 1 SW corner extends to (47.247, -109.367) — its 1.5 km candidate buffer reaches lat 47.232 / lon -109.387, OUTSIDE the bundled raster. `_try_load_local_dem` picks the bundled (= skill-dir) raster first, so candidates in the SW corner fall back to HTTP, which on Windows hits the WSAENOBUFS rate limit. **Fix:** at the top of any script that may sample candidates outside the canonical Fergus LiDAR bbox, prepend the wider cached TIFF explicitly:

```python
import dem_lookup
_explicit = os.path.expanduser('~/.claude/dem_cache/dem_ee0aa3a8a9d0.json')
if os.path.exists(_explicit):
    dem_lookup._explicit_meta_paths.insert(0, _explicit)
    dem_lookup._local_dem = None
    dem_lookup._local_meta = None
```

The wider TIFF covers lat [47.227, 47.379] lon [-109.387, -108.784] — enough for everything in the corridor. This is pitfall #15 (DEM cache mtime mask) bitten again; see also lesson #14.

### 23. Per-launch coverage visualization beats "list of coordinates" for operator briefings

After the set-cover algorithm picks N launches, build an **enriched KML** where each sampled drone position is colored by its assigned launch (nearest VLOS-clear within radius). Toggle a launch folder off in Google Earth and you see exactly that launch's service zone disappear — vastly more useful than a flat list of launch coordinates. Same pattern works for both set-cover output (photogrammetry) AND the iterative gap-fill output (LiDAR). Reference: build_enriched_kml workflow in this conversation.

### 24. Workflows pay for themselves when adversarial verify catches a build-agent claim

The 3-color comparison build agent reported 1114 / 0 / 34 points in the three categories. A second independent verify agent recounted from the KML and got the same 1114 / 0 / 34 — confirming both the algorithm and the KML emit were correct. The verify agent's job ISN'T to detect bugs in the algorithm — it's to detect "the build agent's report didn't match what's actually in the file." That happens often enough that the workflow pattern is worth the 5-min runtime.

---

## Lessons learned — Fergus powerline LiDAR (2026-06-19)

Same Hwy 81 corridor again, but a third operating mode: LiDAR mapping of an existing high-voltage **powerline corridor** (Hilger-Roy line). Hard constraint: drone never gets too close to the wire, measured as **15° off nadir** (not horizontal angle — easy to misread). Final result was a 6-pair, 12-plan set covering 37% of the corridor-union KML at 100% VLOS, with three deliberate gaps reserved for future fresh-battery follow-up flights at other bearings.

### 25. "15° off nadir" is a lateral-clearance constraint, NOT a bearing offset

When Ryan says "transects must be ≥ 15° off the powerline centerline," he means the wire must appear at least 15° off vertical from the drone's perspective — a *lateral clearance* requirement. He does NOT mean rotate the survey angle 15° away from the wire bearing. The flight lines themselves run *parallel* to the wire.

Formula: `min_lateral_clearance = AGL × tan(15°)`.

| AGL | Required lateral clearance | Sanity check |
|---|---:|---|
| 40 m | 10.72 m | per-pass swath = 80 m, transects sit at ±20 m → clearance to wire at center = 20 m ✓ if wire is at center; **fails** if wire is offset 9.3-30.7 m from the polyline |
| 41 m | 10.99 m | (the geometry Ryan proposed) |
| 70.104 m | 18.78 m | per-pass swath = 140 m, transects at ±35 m → 35 m clearance to centerline ✓ |
| 121.92 m | 32.67 m | photogrammetry AGL — much less binding |

**Misreading this constraint as a bearing offset** burned a full Q-and-A round in this session. If a future Ryan message says "15° off the powerline," default-interpret it as nadir-angle (lateral clearance) and confirm — don't rotate the survey angle.

### 26. Polyline = wire (not road) for powerline-clearance LiDAR

When the requirement is "stay laterally clear of the powerline," the safest base geometry is:
- **CorridorScan polyline = the powerline itself** (not the highway centerline).
- 2-transect setup (`CorridorWidth = 2·AGL`) → transects at `±AGL/2` perpendicular to polyline → automatically 35.05 m (at 70 m AGL) from the wire on the sustained passes.

The powerline diverges from the highway by **median 27 m, max 446 m** along this corridor (see `Hilger-Roy existing line — joined.kml` vs `HighwayCenterline.kml`). Setting `polyline = highway` would leave the wire inside the off-nadir cone for ~50% of the route. Setting `polyline = wire` keeps clearance perfect on transects.

Reference: `scripts/generate_powerline_pairs.py` — same hot-swap-pair architecture as Fergus3-20, but with `KML_POWERLINE` replacing `KML_CENTERLINE` in the polyline source.

### 27. The four accepted "brief crossing" categories vs sustained transect clearance

When `polyline = wire`, four parts of the flight path WILL cross or sit on the wire briefly. Ryan accepts these as operationally fine because they're not the sustained mapping passes:

1. **Figure-8 calibration** — 11 vertices centered at the meeting point = on the polyline = on the wire
2. **Cross-line** — by canonical design transects the polyline perpendicularly (pitfall #6)
3. **CorridorScan entry/exit and the perpendicular jog between the two transects at the turnaround corners** — drone is briefly above the wire while turning around
4. **Climb / RTL transit** from HOME to polyline endpoint — passes over the wire en route

Sustained transects (the long parallel passes) MUST satisfy `≥ AGL × tan(15°)` lateral clearance. The validation script in `generate_powerline_pairs.py` distinguishes these and only flags transect-position violations. Brief jog violations show up as 0.0 m min distance — that's the four accepted sources, not a real failure.

### 28. PPSM_per_pass is invariant under `2·AGL × speed = const`

Ryan reported per-pass PPSM at 70 m AGL + 8 m/s: **min 21, avg 51.5, max 85.1**. He asked whether he could fly at 41 m + 14 m/s and keep the same PPSM. Math:

```
ppsm_per_pass ≈ pulse_rate / (swath_width × ground_speed)
              = pulse_rate / (2·AGL × speed)
```

| Config | 2·AGL × speed | Same PPSM? |
|---|---:|---:|
| Current: 70 m × 8 m/s | 1120 m²/s | baseline |
| Proposed: 41 m × 14 m/s | 1148 m²/s | within 3% → ✓ effectively same |

**Implication:** swath shrinks (210 m → 123 m) so total ground covered shrinks, but per-pass PPSM holds. The faster flight at lower altitude is operationally identical per-pass.

### 29. No-overlap launch selection: spacing ≥ 2 × tile_length

Ryan's rule on adjacent pairs: "Overlap is bad if you're flying the same bearing — that's just redundant data." Only the natural ~122 m turnaround-extension overlap between adjacent tiles in a pair is OK; cross-pair overlap from too-close launches is a bug.

For tiles of length L, **adjacent pair meeting points must be ≥ 2L apart.**

- At 70 m AGL + 8 m/s → 10-min flight → L = 1.8 km → spacing ≥ 3.6 km
- At 41 m AGL + 14 m/s → 10-min flight → L ≈ 3.0 km → spacing ≥ 6.0 km

Greedy east-to-west selection from a set of launches: pick the easternmost, then the next one ≥ 2L west, etc. Drop launches in between. From the 9 HomePoints set, dropping L5/L7/L8 gave 6 non-overlapping pairs at the current scale (Fergus3..Fergus14).

Reference: `SKIP_LAUNCHES_1BASED = {5, 7, 8}` in `scripts/generate_powerline_pairs.py`.

### 30. Gaps between missions are a feature, not a bug — but they need to be worth a follow-up

Quote Ryan: "We would like to leave our gaps between missions big enough that we can attack them with their own set of fresh batteries to make it worth our while. We do not want the gaps to be a two-minute flight."

A 1-2 km gap of corridor between adjacent pairs is "big enough" — it fits a single-isolated specialized flight. A 200-300 m gap is too small; you'd burn cal cycles for trivial coverage. **Target gap floor: ≥ 1 km of corridor between adjacent pair coverage zones.** Below that, drop one of the adjacent launches.

Dropped launches become natural starting points for the *specialized* follow-up flights — see lesson #31.

### 31. Different mission features = different flight-line bearings

Powerline corridors with crossing lines (a main wire + branch wires) cannot all be surveyed with a single bearing. Each set of wires needs flight lines roughly parallel to itself:

- **Main flight set:** transects parallel to the main powerline. Crossing lines, where they exist, get **perpendicular-crossed** by these transects — which produces low-quality powerline data for the crossing wires (LiDAR returns from wires hit perpendicular to their length are sparse).
- **Crossing-line set:** a second, specialized flight per crossing-line section, transects parallel to that line. Survey angle changes; usually a single short flight, not a hot-swap pair.

The current 12-plan set is for the main line only. Crossing-line follow-ups are a separate scope, computed against the same corridor-union polygon but at the crossing line's bearing. Don't shoehorn both into a single mission set.

### 32. Operational report should split flight time, acres, and PPSM by once-covered vs twice-covered

When summarizing a multi-plan mission for Ryan, the format that works is:

```
Flight time per plan (calibrated AMC estimate) and total
  → each plan, plus sum

Coverage (shapely on the per-tile swath = polyline buffered by 1.5·AGL each side)
  Total swath = unary_union of all tile coverage polygons
    of which Once-covered = swath - twice-or-more zones
    of which Twice-or-more = unary_union of within-tile twice zones + between-tile turnaround intersections

Vs the target KML
  Numerator = intersection(swath, target) acres
  Denominator = target KML area
  % = numerator / denominator (this is what Ryan asks for; spell it out as a fraction)

PPSM math
  Once-area × per-pass-PPSM = points from single-coverage zones
  Twice-area × 2 × per-pass-PPSM = points from double-coverage zones
  Surveywide avg PPSM = total points / total in-target area
```

**Crucially**: don't include cross-line, fig-8, or transit areas in the swath calculation. Ryan was explicit: "I'm just talking about the area of the actual mission." Only buffer the CorridorScan polyline (extended by TurnAroundDistance at the ends).

Reference: `scripts/powerline_mission_report.py`.

### 33. AMC's mission picker shows the missions root only; old files persist there until you wipe them

AMC scans `<Documents>/Auterion Mission Control/Missions/` on startup and doesn't recurse into subfolders. If you delete files while AMC is open, AMC's picker may still show stale entries — Ctrl+R or a restart refreshes it. Pre-existing calibration plans (`hilger_*`, `RBH_*`, `CourthouseLidar*`, `stahlytest*`) live in this same folder and **must never be touched by skill-generated cleanup** — they're Ryan's controller regression set.

Cleanup scope when starting fresh: `Fergus<N>.plan` (capital F, this-session plans) + `fergus_*.plan` (lowercase, prior corridor-tiler outputs). Preserve `Fergus1.plan`, `Fergus2.plan`, and their `(1)` Drive duplicate backups (AMC-native originals). Preserve ALL non-Fergus calibration plans.

---

## Lessons learned — Fergus highway-corridor LiDAR with mobile crew (2026-06-24)

A long iteration on a 28-mi Hwy 81 corridor at 50 m AGL / 11.5 m/s, with a 2-person crew running a "ground controller perch" workflow distinct from prior single-operator hot-swap pair geometry. The shape of the final mission set differs in several important ways from earlier corridor work — captured here so we don't re-derive them.

### 34. Session = round trip A→B→A, hot swap mid-trip at B, one perch per A→B leg

Ryan's 2-person workflow for the long Hwy 81 corridor:

- **Session**: drone takes off from A, flies one direction to B (one battery, ~10 min), helper hot-swaps at B, drone flies back to A on the return battery (~10 min), lands at A. End of session.
- **A**: launch + return-landing. PIC starts AND ends the session here.
- **B**: hot-swap point. Helper pre-positions there before session start. Drone lands at B between batteries.
- **Perch (P)**: where the PIC drives to during the A→B flight to maintain VLOS during landing at B. Helper handles the physical hot swap; PIC commands the landing approach from the perch via radio.
- **Between sessions**: pack up at A, drive along the road to A_{i+1} (= same location as B_i in a contiguous-strip layout).

This is a fundamentally different architecture than the single-operator "hot-swap meeting-point pair" used in the earlier Fergus 3-38 work — there is no shared meeting-point figure-8 between the legs. **Each session is a closed A→B→A loop with calibration only at A (power-up + power-down).**

### 35. Calibration cadence and ORDER under the session model

Per Ryan's directive:
- Calibration (5 min static + straight-line + figure-8) happens ONLY at session start (power-up at A) and session end (power-down at A). **NOT before or after a hot swap.**
- The 5 min static is on the ground (sensor warmup / shutdown), NOT a hover.
- In-flight cal order is SYMMETRIC about the survey:
  - Start of session (A→B leg, after takeoff): straight-line FIRST, figure-8 SECOND, then survey
  - End of session (B→A leg, before landing): survey, figure-8 FIRST, straight-line SECOND, then land
- During hot-swap (mid-session), no cal. Just takeoff → survey → land.

This corrects the skill's earlier "figure-8 first at start" convention, which had it backwards. Symmetric framing matters: the IMU sees the same sequence in reverse on the way out and the way back.

### 36. Cross-line ("straight line") goes WHERE IT MAXIMIZES POLYGON COVERAGE, not necessarily through A

The cross-line / straight-line that the LiDAR uses for kinematic alignment doesn't have to pass through the launch point. **Position it anywhere that maximizes the line's intersection with the target polygon**, particularly through jut-outs (polygon protrusions perpendicular to the main corridor). The drone:

1. Takes off at A, climbs to AGL
2. Transits to the cross-line start position (may be 100–500 m off-axis from A)
3. Flies the cross-line
4. Transits back into position for the survey

For a polygon with perpendicular jut-outs:
- Find each jut-out via `target_polygon.difference(highway_centerline.buffer(swath_half))`
- The cross-line aligns with the jut-out's **major axis** (oriented bounding box long axis) and passes through the jut-out's **centroid**
- Length = polygon-along-axis extent + ~75 m margin each side
- 2D search (angle × perpendicular offset from centroid) gives the optimum

Reference: `scripts/optimize_crosslines.py`. Improvements observed in the Fergus polygon: 122 m → 853 m of in-polygon traversal at A1, 56 m → 2059 m at A13 (Roy end with 51.5 ac jut-out).

The transit cost (A → cross-line perpendicular distance) is typically 50–250 m, so 1–4% battery hit per cross-line. Acceptable.

**Note (2026-06-24)**: Ryan ultimately deferred the jut-out targeting in favor of a simpler canonical-perpendicular cross-line at each A for the final mission set. Keep the optimization available for cases where the jut-out content is high-value (utility easements with branch features, etc.).

### 37. Perches are at LOCAL ROAD HILLTOPS, identified by DEM profile, one per A→B leg

The "ground controller perch" is where the PIC parks during the A→B leg flight. Methodology (locked in from Ryan's manual placement on 2026-06-24):

- **On or very near the road centerline** (within 50 m). PIC stays on Hwy 81 the whole time — no off-road driving.
- **Local elevation maximum along the road** in the A→B segment. Cut a DEM profile of the road from A_i to B_i; pick a local peak.
- **Somewhat close to B** (within ~0.5–2.5 km of B). Close enough that PIC can clearly see the landing zone; far enough that PIC has time to drive there during the A→B flight.
- **Default fallback** if no local maximum exists in the A→B segment (road is monotonic): use B itself as the perch.

Algorithm:

```
For each session i:
  Sample DEM every 50 m along Hwy 81 from A_i to B_i
  Find local maxima (elev > both neighbors within ±100 m window)
  Pick the local max closest to B_i (or highest if multiple)
  If no local max: perch_i = B_i
```

KML convention: Green paddle = A, Orange paddle = B, **Blue paddle = Perch**. Same circle-paddle style across all three so they read as a triplet for each session.

### 38. PPSM is preserved under `2·AGL·speed = const`, NOT under altitude or speed individually

At 50 m AGL / 11.5 m/s, the per-pass density product is `2·50·11.5 = 1150`. The Fergus 70 m / 8 m/s reference is 1120. These match within ~3%, so the canonical per-pass PPSM values (min 21, avg 51.5, max 85.1) apply at both configurations.

Implication: when Ryan asks "can I fly at X AGL and Y speed and get the same PPSM," the answer is YES iff `2·X·Y ≈ 1120`. Solve for the speed at any target AGL:
- AGL 41 m → speed 13.7 m/s
- AGL 50 m → speed 11.2 m/s
- AGL 70 m → speed 8.0 m/s (baseline)
- AGL 121.9 m (400 ft) → speed 4.6 m/s

The trade-off is **swath width**: `3·AGL` is the combined coverage for 2 transects. Lower AGL means smaller swath — more passes to cover the same target. For the Fergus 1622 ac corridor (avg 145 m wide), 50 m AGL = 150 m swath = single-strip coverage; 41 m AGL = 123 m swath = doesn't cover, needs gap-fill passes.

### 39a. Corrected per-leg structure (2026-06-24 v2)

Lessons #35 + #36 above describe the EARLIER framing where I conflated the kinematic line, the cross-line, and the closing transect. **Ryan corrected this on 2026-06-24.** The right model has TWO orthogonal categories of items:

**Category A — CALIBRATION** (only at session start and session end, NOT at hot-swap takeoffs):
- **Kinematic straight line** — perpendicular to the survey direction, length = `SPEED × 10 s` minimum (e.g., 115 m at 11.5 m/s). Used by the LiDAR IMU for dynamic in-air alignment.
- **Figure-8** — Gerono lemniscate, 11 waypoints. **Centered at the END of the straight line, not back at the takeoff point** — saves the wasted transit back to A.

Calibration order is symmetric and REVERSES between the session's two missions:
- **Session-start mission (A→B)**: straight line FIRST, then figure-8.
- **Session-end mission (B→A)**: figure-8 FIRST, then straight line.

**Category B — CLOSING MANEUVERS** (data-tie maneuvers, ONLY for corridor surveys). **Revised 2026-06-29 (v7) to a single combined "survey→transect transition":**

- **Tangent 1** — straight segment from anchor (last survey WP) heading `tan_B` (survey forward direction), length **R_t1 = AGL/2 m** (= 25 m at AGL 50). Required so the arc has a clean tangent-entry instead of a kink at the anchor.
- **Closing arc** — constant-radius circle, **R_arc = AGL m** (= 50 m at AGL 50), **270° clockwise sweep** centered at `tangent_1_end + R_arc · perp_right_B`. The arc's end naturally lands at `anchor + (R_t1 + R_arc) · tan_B + R_arc · perp_right_B`, which is **at the corridor right edge (+1.5·AGL perp from highway centerline)** with heading **`perp_left of tan_B`** (= perpendicular to centerline). The arc occupies the perp_right side of the corridor (outside the corridor's right half), so the LiDAR sweep during the arc doesn't interfere with the survey path.
- **Straight perpendicular transect** — from arc end heading `perp_left`, length **≥ corridor_width + 50 m margin** (e.g., 200 m at AGL 50 where corridor_width = 3·AGL = 150 m). This straight segment IS the cross-line transect. It crosses the corridor cleanly perpendicular, exits the left edge, and continues ~50 m past for FOV margin.

**There is NO separate "closing transect from anchor"**. The arc end IS the transect start, and the perpendicular straight line that follows the arc IS the transect. The drone never goes back to the anchor between arc and transect.

Waypoint density: arc sampled at **9 WPs total** (1 entry + 8 intermediate), matching figure-8 density.

Closing-maneuver order is the SAME in both missions: **tangent 1 → arc → straight perpendicular transect**.

**Combined per-leg structure for a corridor-survey hot-swap pair:**

| Mission 1 (A→B, session start) | Mission 2 (B→A, session end) |
|---|---|
| Takeoff at A | Takeoff at B (no cal) |
| Straight line (cal) | Survey transect (B→A) |
| Figure-8 (cal, centered at end of straight line) | Tangent 1 + arc + perpendicular transect (closing) |
| Survey transect (A→B) | Figure-8 (cal, reversed order) |
| Tangent 1 + arc + perpendicular transect (closing) | Straight line (cal, reversed order, heading toward landing position) |
| HOLD at end of perpendicular transect | HOLD at end of straight line |

**Mission 1 final item count (AGL 50, N sparse survey WPs): 2 (header) + 2 (kinematic) + 11 (figure-8) + N (survey) + 1 (tangent 1 end) + 8 (arc intermediate) + 1 (arc end) + 1 (transect end) + 1 (LOITER) = N + 27**. For Session 9 with N=4: 31 items.

**Why constant-R circle and not a log spiral**: the user previously asked for a log spiral (varying curvature) but the geometric requirement "perpendicular at corridor right edge exactly" forces R_end ≈ 4·R_start for the spiral end to land where required — making the spiral ~2× wider than operationally needed. A constant-R = AGL circle satisfies the geometric requirements cleanly with simpler math. See `scripts/generate_fergus50_s09_ab.py` for the reference implementation (v7, 2026-06-29).

### 39b. Sparse survey waypoints — emit waypoints ONLY at bearing changes

When the survey polyline runs through long straight stretches of road or wire, **don't emit waypoints at fixed intervals along the straights**. With `AltitudeMode = 3` (terrain-relative), AMC auto-interpolates terrain following between sparse waypoints — so a single waypoint at each end of a straight section is sufficient.

Densely-sampled straight segments (one waypoint every 100 m on a 4-km straight) **risk the drone overshooting and backtracking** to hit each redundant point exactly, breaking the line and degrading scan uniformity.

**Rule**: walk the polyline, emit a waypoint at each end of each curved segment AND at each end of each straight segment. A long straight = exactly 2 waypoints.

Reference implementation: use Douglas-Peucker simplification with a tolerance ≈ 5 m on the polyline; that retains the corner structure and drops collinear intermediate points. The bearing-change rule maps cleanly to "the points DP keeps."

### 39c. Closing maneuvers are for corridor surveys only

The tangent-1 + arc + perpendicular-transect closing pattern (lesson #39a Category B) is specific to **corridor LiDAR surveys**. For non-corridor missions (open-polygon photogrammetry, single-tile LiDAR scans, calibration-only flights), the closing maneuvers don't apply — those missions end with the cal block + return to HOME.

The closing maneuvers exist because:
- Corridor surveys produce long, narrow point clouds where the ends are most likely to lose density / overlap with adjacent missions.
- The arc creates a smooth transition from the survey direction (`tan_B`) to the perpendicular-transect direction (`perp_left of tan_B`) — without an arc, the drone would either backtrack to anchor (wasteful) or take a hard ~90° corner (kinematically rough).
- The perpendicular transect itself is the cross-line that ties this mission's point cloud to the adjacent mission's at the corridor boundary.

### 39d. Closing-arc geometry — the perpendicular-entry constraint (2026-06-29)

The arc's two non-negotiable geometric properties:

1. **Arc end must be AT the corridor right edge** (= `+1.5·AGL` perp from highway centerline = `anchor_perp + AGL`). The straight perpendicular transect starts here.
2. **Arc end heading must be EXACTLY `perp_left of tan_B`**. The perpendicular transect direction is `perp_left of tan_B`, and any heading mismatch creates a turn at the transition.

For a 270° clockwise sweep from `tan_B` heading, the final heading is automatically `perp_left of tan_B` (rotation: `tan_B → perp_right → −tan_B → perp_left`). The end POSITION is determined by `R_arc` and the tangent-1 length:

- For a constant-R circle entered at `(L_t1, 0)` heading `+u` and swept 270° CW: arc end at `(L_t1 + R, R)` in local frame (u = tan_B, v = perp_right).
- Anchor is at `(0, 0)`, anchor perp = `+AGL/2` from centerline. For arc end at `+1.5·AGL` perp: arc end v-coord = `+1.5·AGL − AGL/2 = +AGL`. So we need `R = AGL`.

That's why **R_arc = AGL** (= 50 m for AGL 50) is the canonical value. Lower R lands the arc inside the corridor (not at the edge); higher R overshoots past the edge.

### 39h. Rally point on every corridor mission (2026-07-03)

Every .plan file should carry a `rallyPoints` block with one point near the mission's last nav waypoint. The rally point is a safety failover the autopilot flies to on an RC-link loss or low-battery event.

Pattern established by Ryan on `8BA.plan`:

```json
"rallyPoints": {
  "points": [[<lat>, <lon>, 45.72]],
  "version": 2
}
```

Where `[lat, lon]` = last-nav-WP coords offset by **+37.3 m East, +45.4 m North** (~59 m NE, ~150 ft AGL default altitude 45.72 m = 150 ft).

Implementation: after building `items`, walk `reversed(items)` to find the last cmd 16/17 WP, compute the offset via `RALLY_OFFSET_EAST_M / (111132 · cos(lat))` and `RALLY_OFFSET_NORTH_M / 111132`, and set `plan['rallyPoints']`. See `scripts/generate_all_fergus50_plans.py::add_rally_point` for the canonical helper — call it right before serialize.

### 39i. Mid-project strip resize: extend remaining battery utilization (2026-07-03)

If a project's corridor plans are generated for a conservative battery duration and a portion has already flown (with timestamps captured in the mission-order CSV), the REMAINING plans can be regenerated with a longer strip to use the surplus battery. This is a common "we learned we have margin" adjustment.

**Procedure:**
1. Determine which sessions are complete (from `completion_time` column of the ordering CSV).
2. Compute `east_boundary_along = (min(completed_old_sessions) - 1) × old_strip_len` — that's the boundary between "done" and "remaining."
3. Choose `N_NEW_STRIPS` such that `new_strip_len = east_boundary_along / N_NEW_STRIPS` gives the desired battery-utilization uplift (e.g., +16.7 % → drop N_STRIPS by 1 across the remaining sessions). Whole-strip snapping means the actual % rarely lands exactly on request; report the actual % to the user.
4. Archive the old S01..N_OLD_REMAINING plans to `old/superseded_YYYY_MM_DD/` — don't delete permanently.
5. Regenerate only the new-scheme sessions. Skip completed old sessions.
6. When regenerating the mission-order CSV, LOAD prior completion timestamps by filename and preserve them (`prev_timestamps[fname]` lookup). Never wipe manually-captured completion times on a re-run.
7. Save the new CSV as v3 (or bump version) so the user can compare timelines.

Reference: `scripts/order_fergus50_missions.py` and the `2026-07-03` block in `generate_all_fergus50_plans.py`.

### 39f. DEM-based intermediate waypoint insertion for AGL tolerance (2026-06-29)

Sparse waypoints along a straight or gently-curving segment leave the drone at a **linearly-interpolated AMSL** between endpoint WPs — but the ground beneath rises and falls. Over a hill peak, the drone (holding interpolated AMSL) ends up LOWER than target AGL; over a valley, HIGHER. If any point along the segment sees ground deviate from the AMSL-interpolation line by more than the AGL tolerance, we must insert an intermediate WP at that point (at target AMSL = terrain_amsl + AGL) so the drone tracks the ground properly.

**Algorithm (vertical Douglas-Peucker, gated by min spacing):**

For each segment `(p1, p2)` where p1, p2 = (x, y, target_amsl):
1. Sample the DEM every 5 m along the horizontal segment.
2. At each sample position `s`, compute `deviation = (terrain_amsl(s) + AGL_target) − interp_amsl(s)` where `interp_amsl` is the linear interpolation between p1.amsl and p2.amsl.
3. If `max(|deviation|)` along the segment exceeds `TERRAIN_TOL_M` (default 10 m), insert a new WP at the point of maximum deviation, at its target AMSL.
4. Recursively subdivide the resulting sub-segments until every sub-segment has `max(|deviation|) ≤ TERRAIN_TOL_M`.
5. **Min-spacing gate**: if a proposed insertion would create a WP < 30 m from an existing WP on the segment, log it. Two behavior modes:
   - **skip**: don't insert; accept the >10 m AGL deviation (safer for flight planning, but leaves altitude drift over steep short slopes).
   - **override** (the default for Ryan's corridor plans): insert anyway; log the tight spacing for after-the-fact review.

**Where to apply the refinement:**
- **Survey path** (sparse DP polyline)
- **Closing block**: tangent-1, arc, perpendicular transect (all together as one refinable polyline)
- **Skip**: figure-8 (small enough that DEM variation doesn't matter), kinematic calibration line (short, off-corridor, doesn't matter much)

**Reference implementation**: `scripts/generate_all_fergus50_plans.py::terrain_refine_polyline`. It applied 98 total inserts across the 20 v7 Fergus50 plans (all satisfying 30 m spacing naturally). See `known-pitfalls.md` #20 for the interpolation-behavior notes.

### 39g. Don't use a log spiral when a circle satisfies the constraints

If the constraint is "arc end at a specific position with a specific heading", a constant-R circle satisfies it cleanly. A log spiral has continuously-varying R, so the position constraint becomes a single equation in `R_end` (the spiral's growth-rate parameter), which usually doesn't have a clean solution at operationally-reasonable values.

Spec rationale: when Ryan sketched a varying-curvature teardrop on the v4 plot, the natural read was "use a log spiral." But once we added the constraint "end at corridor right edge perpendicular", the spiral solution required `R_end ≈ 4·R_start`, making the arc ~2× wider than the sketch. The constant-R circle satisfies the constraint with R = AGL — smaller, simpler, exact.

The reverse-decision is also valid: if you're solving for a smooth shape where the END constraint is "freer" (e.g., "loop must be inside the corridor's right half but exact end position doesn't matter"), a log spiral with growing R can match a sketch of varying curvature. Don't reach for spirals until you've checked whether your end constraint forces a clean R.

Open polygons don't have this end-of-corridor concern — the survey closes on itself geometrically.

### 39. Battery is per FLIGHT (10 min), not per session — strip length is half the round-trip range

Ryan's 10-minute battery applies to ONE flight leg, not the round trip. For a session A→B→A:
- Outbound leg: 10 min, includes ~2.75 min overhead (takeoff, climb, straight-line cal, figure-8 cal, transit, landing) → ~7 min survey
- Return leg: 10 min, includes ~1 min overhead (takeoff, transit, landing — no cal mid-session) → ~9 min survey
- **Strip length is bounded by the outbound leg's survey time** at ~7 min × 11.5 m/s = ~4.8 km maximum

The return leg has battery to spare (extra ~2 min unused) — that's safety margin against headwind on the return.

For a 28 mi corridor at 4.54 km strips: 10 strips, 10 sessions, 20 flights, ~187 min total flight time, ~87% coverage with 71.9 ppsm surveywide avg. Reference: `scripts/build_simple_layout.py`.

---

## Final checklist before declaring a plan ready

- [ ] Constants preserved (vehicleType, firmwareType, globalPlanAltitudeMode, terrain rates, camera Manual mode)
- [ ] Exactly one `cmd 178` (constant speed)
- [ ] Survey `FlightSpeed` matches the cmd-178 speed
- [ ] Standalone waypoint altitudes are AMSL via DEM-bake (NOT a flat constant)
- [ ] First waypoint == last waypoint == HOME
- [ ] Survey + cross-line present (mandatory on every flight, including CorridorScan-style)
- [ ] Cross-line extends past polygon edges by CROSS_MARGIN; centered ONE LINE_SPACING inset from the survey exit waypoint toward polygon interior; perpendicular to local polyline/flight-line tangent at the exit
- [ ] Cross-line goes AFTER the survey/CorridorScan in outer items (before fig-8 END if present)
- [ ] Figure-8s match session position: START cal iff first-after-power-up; END cal iff last-before-power-down; item count matches the variant table (29 / 18 / 7)
- [ ] For multi-flight sessions: bracketing is consistent across the group (exactly one START cal, exactly one END cal per envelope), and paired flights share/neighbor HOMEs
- [ ] File is minified, LF only, no BOM
- [ ] User instructed to open + save in AMC before pushing to controller
- [ ] `scripts/coverage_check.py` (or coverage_check_multi for multi-plan ops) confirms target KML is covered
- [ ] `scripts/los_check.py` reports 100% VLOS from the plan's plannedHomePosition; if not, scout_vlos_alternatives.py for the nearest VLOS-clean launch position
- [ ] **For powerline-corridor LiDAR missions**: every sustained transect waypoint is ≥ `AGL × tan(15°)` lateral distance from any powerline (see lesson #25). Brief crossings at fig-8 / cross-line / turnaround jog / climb-RTL transit are accepted (lesson #27).
- [ ] **For multi-pair powerline missions**: adjacent pair meeting points ≥ 2 × tile_length apart so coverage doesn't overlap beyond the natural turnaround zone (lesson #29). Gaps between pairs ≥ 1 km of corridor (lesson #30).
- [ ] **Don't conflate mission modes**: LiDAR corridor (no 3-mi radius), photogrammetry 2-person (3-mi + ≤60 m centerline at 400 ft AGL), and LiDAR powerline (lateral clearance + powerline-as-polyline) all have different binding constraints. See lessons #16, #25.
- [ ] **For 2-person mobile-crew highway-corridor missions** (Hwy 81 architecture): session = A→B→A round trip with cal at A only, mid-session hot swap at B (NO cal), perch P at road hilltop for PIC. Cross-line and figure-8 order is symmetric about the survey (straight-line first at start, figure-8 first at end). See lessons #34–#37.

## 41. PPK base-station power-cycle constraint (2026-07-16)

When a project is post-processed with PPK against ground base stations, the base geometry becomes a **hard mission-grouping constraint** that usually dominates the flight-time/battery budget:

- **One base station per power cycle** — a whole power cycle (start-cal → all items → end-cal, driving between items with the drone powered on) is post-processed against a single base occupation. You cannot mix bases within a cycle.
- **No point of a cycle's trajectory may exceed the max PPK baseline** from that cycle's base. For the Fergus Electric job the limit is **10 miles** (Ryan-stated); the generic Phoenix rule of thumb is ~7 mi (see memory `reference_phoenix_nav_ppk_readiness`). Confirm the number with the surveyor per job.
- **Check the worst-case point**, not the centroid: the farthest vertex of every tap line / area polygon in the cycle must be within the baseline of the base. A centroid check will pass missions whose ends bust the limit.

**Planning implication:** group power cycles by (1) which base can see the whole trajectory ≤ baseline, THEN (2) fit the flight-time budget within that. The base radius, not the 13-min flight budget, is typically what caps a cycle's length. Endpoints reachable by only one base (project extremities) force that base's cycle. Emit a KML with each base, its baseline ring, and the color-coded cycle trajectories for the surveyor to sign off before generating .plan files.

## 42. Montana State Plane EPSG + coordinate conversion (2026-07-16)

Ryan's Montana control-point coordinates are in **US/International feet**. The EPSG pair (do NOT state these backwards — verify before asserting):

- **EPSG:6515 = NAD83(2011) / Montana (feet)** ← Ryan's coordinates are in this
- **EPSG:6514 = NAD83(2011) / Montana (meters)**

Convert to WGS84 with `pyproj.Transformer.from_crs(6515, 4326, always_xy=True).transform(easting_ft, northing_ft)` — pass the **raw feet** values; pyproj's 6515 definition already carries the feet unit, so do NOT pre-multiply by 0.3048. Sanity-check the output lands in the project area (Fergus ≈ 47.3°N, -109.1°W) before trusting it. A wrong unit/EPSG assumption lands the points in Idaho.

## 43. Tap-line and area (polygon) gap-fill missions — different treatment (2026-07-16)

Leftover coverage after the main corridor comes in two flavors that fly differently:

- **Tap lines** (powerline spurs, given as KML LineStrings): fly as a **line corridor** — waypoint transects following the tap line, **2 passes** offset ±AGL/2 (same as the main corridor's two transects). Extend each line **50 ft (15.24 m) past both endpoints** (end buffer). No side buffer (the 2-pass offset covers the sides).
- **Areas** (given as KML polygons): fly as an **AMC `TransectStyleComplexItem` polygon survey**. Set `angle` = the polygon's **principal (longest) axis** so flight lines run as long as possible (fewest turnarounds). Buffer the polygon **50 ft (15.24 m) on the ends + 25 ft (7.62 m) on the sides** before generating transects.
- **Same AGL and line spacing** as the corridor (50 m / 50 m for the Fergus 50 m config).
- **No closing perpendicular transect** on these gap-fill missions (Ryan dropped that requirement for taps/areas 2026-07-16) — taps are just the 2-pass corridors, areas just the surveys.
- **Calibration**: bracket each **power cycle** (not each item) with start + end cal. Additionally give any single area whose own flight exceeds ~5 min its own dedicated cal pair.
- Order items **by position** (east-to-west or the project's long axis) and intermix taps + areas so the crew makes one sweep with no backtracking for pickups.

## 44. Verify ACTUAL coverage from the flown .nav, not just the plan (2026-07-17)

A plan can pass every generation check and still leave a real hole — because the survey polygon
was drawn smaller than the target. On the Fergus job, Area4 was redrawn smaller than the "Gap 1"
it was meant to fill and silently left **47% uncovered**, caught only after the crew had almost
demobbed. The fix is to close the loop between PLANNED and ACTUALLY-FLOWN coverage.

**Tool:** `scripts/nav_coverage_check.py <scan.nav> --agl 50 --fov 90 [--target gap.kml]`
- Read-only scan of the NovAtel-binary `.nav` for lat/lon doubles in a plausible window (robust
  heuristic; no full log parse). Same trick gives quick trajectory-extent / adjacent-scan-overlap
  checks (project both extents onto the corridor centerline; confirm overlap, not a gap).
- Buffers each fix by the LiDAR **half-swath = AGL · tan(FOV/2)**, unions to a footprint polygon.
  For the MiniRanger (90° FOV): half-swath = AGL, so ground swath = **2·AGL** per pass (100 m at
  50 m AGL). Overlap % is a *planning* input (sets line spacing) and does NOT enter here — the
  flown trajectory already reflects where the lines went.
- With `--target`, reports % of the target covered and writes the uncovered remainder to a KML.

**When to run:** (a) before demob, against each target/gap polygon, to catch holes while you can
still re-fly; (b) at plan-build time, verify every survey polygon *contains* its original target
polygon (union it in if short — lesson: a redrawn area is not guaranteed to cover the gap it
replaced); (c) between adjacent scans to confirm swath overlap.

## 45. Fly-to-next vs land-and-drive is a BATTERY decision, not a time decision (2026-07-17)

For scattered multi-target missions (taps / spot features) you repeatedly choose: fly the drone
to the next target, or land it, put it on the truck, drive, relaunch. The intuition "drive if it's
far" is usually wrong on *time*:

- Fly time ≈ D / speed. Land+drive ≈ (fixed overhead ~3 min) + D / drive_speed. Driving (~30 mph
  = 13.4 m/s) is barely faster than flying (~11.5 m/s), so the fixed land/relaunch overhead
  dominates: **flying wins on wall-clock out to ~9 miles.**
- So the ONLY reason to land-and-drive short/medium gaps is to **conserve survey battery** (and to
  respect VLOS, if that's binding — for a 2-person crew that keeps moving, it often isn't).

**Rule:** set a distance threshold from the battery budget, not from time. Fly to the next target
if the gap is under the threshold; land-and-drive if farther. On Fergus, **4,000 ft** was the
sweet spot — it flew the dense cluster of near targets (longest hop 53 s of battery) and drove
only the genuinely long jumps. Look for a natural break in the gap-distance distribution; check
that no continuous fly-run exceeds one battery.

**Structural consequence:** a power cycle splits into multiple *sub-mission plan files* — one per
fly-run, broken at every gap over the threshold (and at power-cycle/base boundaries). Cal flights
go only on the first and last sub-mission of each power cycle; the drone stays powered on the truck
across the drive-breaks (INS holds), so no re-cal between them. See `generate_fergus_remaining_plans.py`
(FLY_THRESHOLD_M) for the reference implementation.
