# Known pitfalls

Things that have already bitten Ryan. **Read this before generating or modifying any .plan file.**

## 1. Terrain recomputation is survey-only (Behavior A)

**Confirmed by experiment 2026-06-17.** When AMC opens a file with `globalPlanAltitudeMode: 3`:

- **Survey inner `Items` (transect waypoints)**: AMC **recomputes** altitudes from its DEM on every open. You can stamp them with garbage values (we tested 9999) and AMC fixes them. CameraShots and VisualTransectPoints are also regenerated.
- **Standalone waypoints (climb, figure-8, cross-line, exit)**: AMC does **NOT** recompute. Whatever AMSL you wrote stays. If you set them to a flat constant, they will not follow terrain at all.

**Implication:** For terrain-following standalone waypoints, you **must** DEM-bake the AMSL altitudes at generation time. Use `scripts/dem_lookup.py` (USGS 3DEP, free, no auth, ~1 s/point, 1-meter resolution in MT).

## 2. RC controller rejects pretty-printed JSON

**Confirmed by experiment.** Files that opened in desktop AMC failed silently on the controller. Pure format difference, no content change required:

- Working: minified single-line JSON, no whitespace, no line endings
- Failing: 4-space-indented JSON with CRLF (`\r\n`) line endings

**Fix:** `json.dumps(plan, separators=(',', ':'))` + `open(path, 'wb').write(...)`. The `'wb'` binary mode is critical — text mode on Windows will inject CR. Use `scripts/minify_plan.py` to normalize any existing file.

## 3. `frame: 10` (TERRAIN_ALT) doesn't visualize in AMC

**Confirmed by experiment.** Setting standalone waypoints to `frame: 10` with `altitude: 40` (AGL):
- AMC accepts the file, preserves frame=10 + altitude=40 on save
- BUT AMC's elevation profile renders the waypoint as 40 m **MSL** (underground)
- Autopilot would probably honor frame=10 in flight, but you have no visual preview

**Conclusion:** Don't use frame=10 for plans you preview in AMC. Use frame=0 with DEM-baked AMSL instead.

**This is a HARD rule. Don't override it for a user preference.** Ryan has said things like "I would rather those be AGL" — that's a soft preference statement, not permission to break pitfall #3. The right response is to use `frame: 0` with `altitude = terrain_amsl(lat, lon) + AGL_target`, which gives **identical flight behavior** (drone flies at AGL_target m above ground at each waypoint) AND a correct AMC elevation-profile display. The "AGL" the user wants is a flight-behavior property, not a frame-number property — `frame: 0` with DEM-baked altitude achieves it. The only difference between `frame: 0` and `frame: 10` in flight is between waypoints (frame=10 continuously hugs terrain, frame=0 interpolates linearly in MSL), which is negligible for tight figure-8s on near-flat terrain.

If a future Ryan request really does mean "make the autopilot use TERRAIN_ALT frame at flight time," he'll need to say so explicitly *and* accept the AMC visual breakage. Don't infer it from a casual preference.

**Incident reference:** 2026-06-18 Fergus3/Fergus4 generation. Ryan said "I would rather those be AGL as well"; the prior agent switched fig-8 vertices to frame=10 + altitude=70.104. AMC then rendered them at 70 m MSL = 230 ft MSL — clearly wrong (ground in the area is ~3500 ft). Reverted to frame=0 with `bake_amsl` per-vertex.

## 4. CorridorScan — works iff AMC-native; risky if hand-fabricated

**Updated 2026-06-18.** Ryan confirmed CorridorScan loads + flies on his RC controller when the .plan was created and saved by AMC itself (the Fergus1.plan / Fergus2.plan files). The earlier hilger_lidar / hilger_miniranger / hilger_test_1 failures were from hand-fabricated files where some other detail (massive polygon vertex count, pretty-printing, missing internal fields) was the real issue — CorridorScan was the suspected but not the actual cause.

**Rule:**
- CorridorScan is a supported AMC complex item — don't strip it from existing plans the user made in AMC.
- When generating CorridorScan from scratch, **start from a confirmed-working AMC-native plan as the template** (Fergus1.plan / Fergus2.plan) and copy its exact field set. Don't invent a CorridorScan from spec — there are nested fields AMC populates that hand-generators miss.
- After generating, the "open + save in AMC once" round-trip (pitfall #10) is more important for CorridorScan than for Survey because AMC normalizes the inner item list and visualizes the corridor.
- For **non-LiDAR or non-corridor** geometry, Survey is still the canonical choice.

If a CorridorScan-based plan does fail to load on the controller, suspect pitfalls #2 (pretty-printed JSON), #5 (huge polyline vertex count), or a malformed nested field — not the CorridorScan type itself.

## 5. Massive polygon vertex counts break things

`hilger_test_1.plan` had a 931-vertex polygon (from an imported shapefile). 374 KB file. Failed to load.

**Rule of thumb:** Decimate polygons to <50 vertices before importing. Tools → Simplify in AMC, or hand-trace a clean boundary.

## 6. Cross-line must extend past polygon edges

If the cross-line endpoints sit exactly on the polygon edges, the drone is still completing a turn when it enters the survey area and starts turning before it leaves. This corrupts the LiDAR calibration the cross-line is meant to provide.

**Always extend by `CROSS_MARGIN`** (default 25 m) past each polygon edge in the cross-line direction. The drone gets stable straight-line flight through the entire survey width.

**Also: don't forget the cross-line on CorridorScan-style flights.** The skill canonical structure was originally written for Survey-style and a future agent can easily think "CorridorScan already does perpendicular jogs internally at the turnarounds, so skip the cross-line." That's wrong:
- The internal jogs in CorridorScan's `TransectStyleComplexItem.Items` are ONE LINE_SPACING wide (= half the corridor width = transect spacing). The cross-line is `CorridorWidth + 2·CROSS_MARGIN` wide — covers the entire swath and then some.
- The internal jogs happen at the FAR turnaround corner; the cross-line happens NEAR the EXIT side, ONE LINE_SPACING inset toward polygon interior. Different position.
- The internal jogs serve TURN GEOMETRY for the autopilot; the cross-line serves LiDAR INS reference for the SLAM solution. Different purpose.

Incident reference: 2026-06-18 Fergus3..Fergus20 generation. The prior agent generated 18 CorridorScan plans with no cross-line at all, taking the variant table's "CorridorScan-style" structure (cmd 530 + cals + CorridorScan) as complete. Ryan caught it; cross-line added on the second pass. The cross-line is mandatory on EVERY flight — survey or CorridorScan, single or hot-swap-bracketed, START cal or END cal — no exceptions.

**Placement reminder:** the "previously flown mission" the cross-line ties to is the survey JUST COMPLETED in this same flight — not adjacent missions, not yesterday's session. The cross-line transects through the corridor/polygon that the drone just surveyed, perpendicular to those flight lines, providing a perpendicular ground-track for the INS solution to use as a constraint when stitching the parallel transects.

## 7. Speed-change items kill kinematic calibration

The stahlytest.plan had a `cmd 178 DO_CHANGE_SPEED` between every post-survey waypoint, setting speed to the same value each time. Useless and disruptive — the autopilot decel/accels through each one.

**Rule:** Exactly **one** `cmd 178` in the entire plan, at the header. Speed never changes mid-mission. Survey `FlightSpeed` must match the header cmd-178 speed.

## 8. Figure-8 vertices must close on the centroid

A 10-vertex Gerono lemniscate has v0 = v5 = centroid (the true self-intersection). The drone flying v0→v1→...→v9 only flies **9 legs** — the figure-8 isn't closed.

**Fix:** Append an 11th waypoint at the centroid as a closer → 10 legs, true closed figure-8.

## 9. First waypoint == last waypoint

For mission symmetry (drone returns to launch position cleanly), the **first standalone waypoint** (climb at HOME) and the **last waypoint** (trailing-line endpoint) must share lat/lon = HOME.

The figure-8 #1 ends naturally at HOME (its centroid is HOME), so the climb waypoint, fig-8 #1 first vertex, and fig-8 #1 closer are all at HOME. The trailing line must also end at HOME.

## 10. Always round-trip through desktop AMC before flying

Even after careful generation, **open the .plan in desktop AMC, let it save, then push to the controller.** AMC will:
- Regenerate the survey's inner `Items` array with correct DEM-sampled transect altitudes
- Recompute `CameraShots` and `VisualTransectPoints`
- Normalize `MISSION_ITEM_ID` / `doJumpId` / `UUID` consistently

The desk save is the canonical "controller-ready" version. Generated files are "AMC-ready."

## 11. PX4 vs ArduPilot

Ryan's airframe is PX4 multirotor (`vehicleType: 2, firmwareType: 12`). If a future plan needs to fly on ArduPilot or fixed-wing, these values change AND many of the speed/turn behaviors above will need re-calibration. Don't reuse the calibrated time-estimation coefficients (1.05 / 1.08 / 1.97) across firmware families.

## 12. Don't sample DEM for survey item — only standalone

The survey's `CameraCalc.DistanceToSurfaceRelative: false` + `FollowTerrain: true` + `globalPlanAltitudeMode: 3` causes AMC to DEM-sample the survey internally on open. Don't pre-bake those — leave them however the user/AMC wrote them. DEM-baking is for **standalone** waypoints only.

## 13. Empty inner Items makes AMC show survey as HGT instead of AGL

**Confirmed 2026-06-18 (Fergus3/Fergus4 generation).** When a CorridorScan / Survey is written with `TransectStyleComplexItem.Items: []` and `VisualTransectPoints: []`, AMC's survey panel defaults the altitude display to **HGT (MSL)** even when every documented AGL/terrain-follow setting is correct:
- `globalPlanAltitudeMode: 3` ✓
- `FollowTerrain: true` ✓
- `DistanceToSurface: <AGL>` ✓
- `DistanceToSurfaceRelative: false` ✓

The user can SEE the survey display as HGT in AMC, even though the field values would compute as AGL. Trusting "AMC will regenerate Items on open" (pitfall #10) is not enough — until Items is populated, AMC has no transect path to render in AGL mode and falls back to MSL.

**Fix:** pre-populate `TransectStyleComplexItem.Items` and `VisualTransectPoints` based on the polyline + CorridorWidth at generation time. Use the same item pattern AMC produces (entry turnaround → cmd178 → polyline-left-side waypoints → cmd206 → markers → cmd206 → far-side turnaround → jog → polyline-right-side waypoints → cmd206 → entry turnaround). DEM-bake AMSL altitudes for every cmd 16. AMC will recompute on open (pitfall #1) but the survey now renders in AGL from the first display.

See `scripts/generate_fergus_pair1.py::build_corridor_inner_items` for the reference implementation.

## 14. Operator VLOS isn't guaranteed by a plan that passes coverage check

A `.plan` can be geometrically correct (covers the target, polylines clean, AMC loads it) and still be UNFLYABLE under Part 107 because terrain blocks the operator's view of the drone from the launch site. Bare-earth viewshed math: at every point along the flight path, the straight line from operator eye (launch ground + 2 m) to drone (terrain + AGL at that lat/lon) must stay above the terrain underneath the line.

For valley-floor launch sites in hilly terrain (the Snowy Mountains foothills section of Hwy 81), the drone disappears behind ridges within a kilometer. The 6 affected Fergus plans in the original 20 lost 11–63% of their flight paths to terrain occlusion — Fergus13 was the worst at 14.4 m of terrain rising above the LOS line at 1861 m from launch.

**Fix:** run `scripts/los_check.py` as a mandatory verify step (now in the post-Q&A flow). For any plan that fails, run `scripts/scout_vlos_alternatives.py` — it samples a 2 km / 200 m grid around the original launch and reports the closest position that gives 100% VLOS to both tiles of the pair, including ground elevation, drive distance, and distance from the centerline (proxy for road accessibility).

**Limitations of the check:**
- Bare-earth DEM only. Trees and buildings are NOT modeled. A LiDAR-clean LOS line in the bare-earth sense may still be obscured by tree cover or buildings in reality. Inspect the flight area visually before committing.
- Operator position = `plannedHomePosition` exactly. Real operator can stand ±10 m off; for marginal cases (worst block < 2 m) this matters.
- Earth curvature is ignored. Negligible at these ranges (max LOS ~ 4 km, curvature drop ~ 1.25 m).

**Algorithmic launches tend to pass VLOS by default.** The gap-fill algorithm picks the highest-elevation centerline point inside each gap; high points have inherent VLOS to the surrounding 1.8 km of corridor. The hand-picked road-access launches (HomePoints.kml) are placed for accessibility, not elevation, and are the ones that fail VLOS most often.

## 15. DEM cache mtime can mask a larger TIFF with a smaller one

`dem_lookup._try_load_local_dem` walks the candidate TIFFs in mtime order (newest first) and returns the first one it can open. If you call `ensure_dem_for_bbox` with a TIGHT bbox AFTER a wider one was already cached, the tight TIFF becomes most-recent and gets picked — but it doesn't cover the full extent of your flight paths. Lookups outside the tight bbox fall back to HTTP, which on Windows can exhaust socket buffers (WSAENOBUFS / WinError 10055) when you fire dozens of them in quick succession.

**Symptoms:**
- "USGS 3DEP lookup failed for (lat, lon): URLError [WinError 10055]" mid-script
- VLOS check shows lower % than expected because some flight-path lookups errored out and the code path silently failed
- Plans built with `bake_amsl` may have slightly wrong altitudes at the bbox edges

**Fix:**
- Pad the bbox generously up front. For a 28-mile corridor, use `pad = 0.05` (~5 km) at minimum.
- Compute the bbox from the FULL target geometry (corridor union, all polylines, all cross-line endpoints), not just from the launch positions.
- If a smaller TIFF has already snuck in, delete it from `~/.claude/dem_cache/` so the larger TIFF wins the mtime sort. Or `touch` the larger one.
- For multi-step pipelines (generate → coverage → VLOS → scout), warm ONE big bbox at the start of the first step; subsequent steps automatically reuse the cached raster.

Incident reference: 2026-06-18 commit_gap_fills.py initial run. The launch-positions-only bbox was 50 km × 6 km; flight paths extended to 50 km × 7 km. Mid-VLOS-check Windows hit WSAENOBUFS after ~30 HTTP fallback attempts. Cleared by deleting the small TIFF and re-running.

## 16. Calibration belongs to the power-cycle envelope, not the flight

Putting a figure-8 calibration on every individual flight is wrong on both sides:

- **Cal on a hot-swap flight (drone stays powered between flights):** wasted ~3–5 min of battery, and re-calibrates an INS solution that didn't go anywhere. Field operators notice the wasted time.
- **No cal on a cold-start flight (drone was just powered on):** the LiDAR INS solution isn't bracketed. Point-cloud quality in post-processing degrades. The user has confirmed this is the failure mode that drove the bracketing rule.

**Rule:** the START cal goes on the first flight after power-up, the END cal goes on the last flight before power-down. Hot-swap flights in between get neither. A single isolated flight gets both.

**Planning implication:** you can't decide whether a given flight needs cal by looking at the flight alone — you need to know its position in the operator's session. When generating a group of plans, always ask up front: "how is the operator running these — single flights, or hot-swap pairs/sessions, and where are the power cycles?" Then assign cals per envelope. See SKILL.md → "Session model" for the rules and the canonical 2-flight hot-swap example.

**Verification:** for a multi-plan set, count START cals and END cals across the group: exactly one START cal per envelope (in the first flight), exactly one END cal per envelope (in the last flight). Any other distribution is wrong.
