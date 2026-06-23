# Constants vs Variables

The single most important distinction when generating or editing a .plan file. **Never invent values for variables — ask the user. Never edit constants without explicit instruction.**

## CONSTANTS — hold across every mission

These are baked into the generator and the user has confirmed they should not change without explicit override.

### Top-level mission settings

| Field | Value | Notes |
|---|---|---|
| `fileType` | `"Plan"` | |
| `version` (top) | `1` | |
| `groundStation` | `"QGroundControl"` | AMC writes this too |
| `mission.version` | `2` | |
| `mission.vehicleType` | `2` | PX4 multirotor |
| `mission.firmwareType` | `12` | PX4 |
| `mission.cruiseSpeed` | `15` | Autopilot fallback — actual flight uses cmd 178 |
| `mission.hoverSpeed` | `10` | Autopilot fallback |
| `mission.globalPlanAltitudeMode` | `3` | Calc-Above-Terrain — REQUIRED for terrain-follow |
| `geoFence` | `{circles:[], polygons:[], version:2}` | Empty unless user adds one |
| `rallyPoints` | `{points:[], version:2}` | Empty unless user adds one |

### Survey complex item (`TransectStyleComplexItem`)

| Field | Value | Notes |
|---|---|---|
| `FollowTerrain` | `true` | Critical — turns on terrain follow for survey transects |
| `TerrainAdjustMaxClimbRate` | `3.0` | m/s — user standing constant |
| `TerrainAdjustMaxDescentRate` | `3.0` | m/s — user standing constant |
| `TerrainAdjustTolerance` | (preserve) | Leave whatever AMC wrote |
| `CameraTriggerInTurnAround` | `false` | |
| `HoverAndCapture` | `false` | |
| `Refly90Degrees` | `false` | |
| `splitConcavePolygons` | `false` | |
| `flyAlternateTransects` | `false` | |
| `CameraCalc.CameraName` | `"Manual (no camera specs)"` | Sidesteps sensor/focal/image-size question |
| `CameraCalc.DistanceToSurfaceRelative` | `false` | Always false when FollowTerrain=true |

**Note (2026-06-18):** AGL (`CameraCalc.DistanceToSurface`) and the duration window
were previously listed as constants but proved to be **per-mission variables** in
practice — Ryan flew the Fergus corridor at AGL 70 with a 12-min cap, not the
original 40 / 10-min. Treat AGL and duration cap as variables; default to 40 / 10
for new missions until the user specifies otherwise.

### Mission structure (item sequence)

Each mission's sequence is assembled from the same blocks; figure-8 calibrations are conditional based on the flight's role in its power-cycle envelope. **The survey + cross-line are always present.**

```
1× cmd 530   (mission options, params [0, 2, null, null, null, null, null])     ALWAYS
1× cmd 178   (set speed — the ONLY speed change in the plan)                    ALWAYS
1× cmd 16    (climb to flight alt at HOME)                                       ALWAYS
11× cmd 16   (figure-8 #1: 10 Gerono vertices + 1 closing return-to-centroid)   IFF first flight after power-up
1× survey                                                                        ALWAYS
2× cmd 16    (cross-line: start + end, EXTENDED past polygon edges)              ALWAYS
11× cmd 16   (figure-8 #2)                                                      IFF last flight before power-down
1× cmd 16    (return to HOME — must equal first waypoint location)              ALWAYS
```

Total item count by flight role within its power-cycle envelope:

| Role | Cals | Items |
|---|---|---|
| Single isolated flight (cold start + cold end) | START + END | 29 |
| First flight of a hot-swap session | START only | 18 |
| Middle flight of a hot-swap session | none | 7 |
| Last flight of a hot-swap session | END only | 18 |

First and last waypoints always share lat/lon (= HOME). See SKILL.md → "Session model" for the bracketing rules.

### File format

| Property | Value | Why |
|---|---|---|
| JSON style | **Minified** (no whitespace) | RC controller rejects pretty-printed |
| Line endings | **LF only** (no CRLF) | RC controller chokes on CR |
| Encoding | UTF-8 | |
| BOM | None | |

Use `json.dumps(plan, separators=(',', ':'))` and write as bytes via `open(path, 'wb').write(...)` to guarantee no CR sneaks in.

### Figure-8 geometry

| Property | Value | Notes |
|---|---|---|
| Shape | Gerono lemniscate | `x(t)=a·sin(t), y(t)=(a/2)·sin(2t)`, 10 evenly-spaced t values |
| Vertices | 10 unique + 1 closer at centroid | 11 entries, 10 flown legs |
| Polyline length | `5.82803 · a` | Use this to solve for `a` given duration × speed |
| Closure | Final vertex returns to centroid | Drone completes the 8 before moving on |
| Crossing point | Vertices 0 and 5 both at centroid | This is the true self-intersection |

### Flight-time estimation model

Calibrated against 7 plans (RMSE 0.18 min). Don't change coefficients without recalibrating:

```
AMC_min = 1.05·survey_min + 1.08·corridor_min + 1.97·transit_min
```

---

## VARIABLES — must be supplied per mission

Ask the user for these. Don't default them silently.

| Variable | Type | Typical | Notes |
|---|---|---|---|
| `HOME` | `[lat, lon]` | — | First & last waypoint of the mission. User-defined per mission. |
| `polygon` | list of `[lat, lon]` pairs | 4–20 verts | Survey boundary. From KML or hand-drawn. |
| `AGL_TARGET` | float (meters) | **40 (RGB)** or **70 (LiDAR)** | Above-terrain altitude — also drives camera footprint AND line spacing per skill convention |
| `DURATION_MIN` / `DURATION_MAX` | float (min) | **[8, 10]** default; user can relax to [8, 12] | Acceptable mission duration window per estimate_flight_time.py |
| `--gap-thresholds` | comma-separated m² | empty or "8000,2000,500" | Successive gap-fill cutoffs for the orchestrator. Each smaller threshold adds more (smaller) tiles. Skip to keep only main spine tiles. |
| `--prefix` (output naming) | str | "fergus" | Output plans are `<prefix>_NNN.plan` (main) and `<prefix>_gap_NNN.plan` (gap-fills). Cleanup only touches files matching this prefix. |
| `--east-to-west` | flag | false (= W→E) | Numbering order for output files. Set true when operator flies east → west. |
| `SPEED` | float (m/s) | 8 | Constant throughout mission; sets cmd 178, FlightSpeed, all transit |
| `CROSS_MARGIN` | float (meters) | 25 | How far the cross-line extends past polygon edges in its own direction |
| cross-line position rule | — | — | Cross-line sits ONE `AGL_TARGET` (line-spacing) from the survey exit waypoint's lat/lon, offset toward polygon center so it crosses the surveyed area. **Reading A**: offset is from the exit waypoint's coordinate, not from a polygon edge or swath edge. |
| `TurnAroundDistance` | float (meters) | 15.24 | Survey turnaround spacing |
| `survey.angle` | degrees | varies | Flight line orientation; can be derived from polygon principal axis |
| `survey.entryLocation` | int | 0 | Which polygon vertex transects start near |
| `CameraCalc.DistanceToSurface` | float (meters) | = AGL_TARGET | Must match AGL_TARGET |
| `AdjustedFootprintFrontal` | float (meters) | varies by payload | User supplies once per payload type |
| `AdjustedFootprintSide` | float (meters) | varies by payload | User supplies once per payload type |
| `figure8_duration` | seconds | 15 | Determines `a` parameter; user may override |

### Per-payload constants (effectively constants once chosen)

When the user names the payload (e.g. "miniRanger LiDAR", "RGB photogrammetry"), record:
- Camera mode (almost always `"Manual (no camera specs)"`)
- AdjustedFootprintFrontal (m)
- AdjustedFootprintSide (m)
- Default AGL
- Default front/side overlap (if not using Manual mode)

Store these in a per-payload preset block once the user confirms; reuse without re-asking.

---

## What to do if you're unsure

If you can't tell whether a field is a constant or a variable, default to **preserve verbatim** from the base file and ask the user. The user prefers that over silent edits.
