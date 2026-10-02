# Fergus 50 m corridor-LiDAR plan SPEC (2026-06-26)

This is the consolidated specification for the Fergus50_S{NN}_AB and Fergus50_S{NN}_BA `.plan` files. All requirements were stated by Ryan in the conversation; any item that depends on inference is marked **(inferred — verify)**.

---

## 1. Mission context

| Item | Value | Source |
|---|---|---|
| Mission type | Corridor LiDAR survey along Hwy 81 (Hilger → Roy) | Ryan |
| Crew | 2-person mobile, hot-swap pair architecture | Ryan |
| Session structure | 2 missions per session: A→B (mission 1) + B→A (mission 2) | Ryan |
| Battery | 10 min per leg (per flight, NOT per session) | Ryan: *"our battery is still 10 minutes, not 20 minutes"* |
| AGL | 50 m | Ryan: *"so we adjust our height so maybe that's at 50 meters"* |
| Speed | 11.5 m/s (constant via `cmd 178`) | Ryan implied via the 41/14 → 50 m equivalence |
| Line spacing | 50 m (= AGL) | **(inferred)** Skill convention; user stated 41 m at 41 m AGL, scaling assumes the same convention holds at 50 m |
| Per-line swath | 100 m (= 2·AGL, 90° FOV convention) | **(inferred)** Phoenix doc + skill convention |
| Combined corridor width | 150 m (= 3·AGL) | **(inferred)** Same convention scaled from 41 m → 123 m |
| Polyline | Hwy 81 centerline | Ryan |

**5-minute static is NOT in the plan**. Ryan: *"please don't plan the five minutes static as part of the mission. Our constraints don't change at all from the previous. You don't need to worry about the static for mission planning in any way, shape or form. That's just for me to know. I need to do the static at the beginning before I take off and at the end after I land."* The static is a ground procedure bracketing the .plan, not an in-air maneuver.

---

## 2. Per-mission item-order spec

### Mission 1 (A→B) — session start, gets START cal

| # | Section | Item count | Notes |
|---|---|---:|---|
| 1 | `cmd 530` mission options | 1 | params `[0, 2, null, null, null, null, null]`, frame=2 |
| 2 | `cmd 178` set speed | 1 | params `[1, 11.5, -1, 0, 0, 0, 0]`, frame=2 |
| 3 | **Kinematic straight line** (START cal #1) | 2 | Perpendicular to highway tangent at A. **Length ≥ 115 m (= SPEED × 10 s)**. The line's two endpoints are the only WPs — no climb-at-centerline waypoint. |
| 4 | **Figure-8** (START cal #2) | 11 | Centered at the **END of the kinematic line (K2)**, NOT at A. Standard Gerono lemniscate (10 unique vertices + 1 closer = 10 legs). |
| 5 | **Survey transect** | sparse | At **+25 m perpendicular RIGHT offset** from highway centerline, A→B direction. Waypoints **only at highway bearing changes** (Douglas-Peucker, tol ≈ 5 m). NO waypoints in long straight segments — AltitudeMode=3 handles terrain following between sparse WPs. |
| 6 | **Closing LOOP** | 12 | Single right-turn 360° lobe at the end of the survey. See §3 below for geometry. |
| 7 | **Closing TRANSECT** | 2 | Perpendicular to highway, near B. See §4 below for geometry. |
| 8 | **LOITER_UNLIM** (`cmd 17`) | 1 | At end of closing transect. Drone holds at 50 m AGL indefinitely. No `cmd 21 LAND` in plan. |

**Session-start cal ORDER**: kinematic line FIRST, figure-8 SECOND. (Then survey, then closing maneuvers.)

### Mission 2 (B→A) — session end, gets END cal

| # | Section | Item count | Notes |
|---|---|---:|---|
| 1 | `cmd 530` | 1 | Same as Mission 1 |
| 2 | `cmd 178` | 1 | Same |
| 3 | (no cal at start — hot-swap takeoff) | 0 | **Definitely no calibration at hot-swap takeoffs.** Drone takes off at B and goes directly to survey. |
| 4 | **Survey transect** | sparse | At **−25 m perpendicular RIGHT offset** (= +25 m relative to B→A forward direction, which mirrors A→B's +25 m). Sparse, bearing-changes only. |
| 5 | **Closing LOOP** | 12 | Same shape as Mission 1, located near A. **Order: loop comes first, transect second — SAME as Mission 1.** Not reversed. |
| 6 | **Closing TRANSECT** | 2 | Perpendicular near A. Geometry mirrors Mission 1's closing transect. |
| 7 | **Figure-8** (END cal #1) | 11 | Centered at the END of the closing transect (= where drone is after transect). |
| 8 | **Kinematic straight line** (END cal #2) | 2 | Perpendicular at the figure-8 centroid, length ≥ 115 m. |
| 9 | **LOITER_UNLIM** (`cmd 17`) | 1 | At end of kinematic line. |

**Session-end cal ORDER**: figure-8 FIRST, kinematic line SECOND. **Reversed relative to start cal.** (Closing-maneuver order: same as Mission 1 — loop then transect.)

---

## 3. CLOSING LOOP geometry

User words: *"a full loop at waypoint 61 turning right kind of like the figure 8 but only 1 loop, cross its own previous path somewhere around waypoint 60 to ensure FULL overlap between its current field of view after the circle is complete and ground coverage of the existing point cloud from the flight line(s) just did previous."*

Plus: *"It doesn't appear to be turning a radius that enters it back into the corridor."*

### Constraints
- **Right turn** (clockwise in plan view, when survey direction is forward).
- **Single 360° lobe** — drone enters at point P, flies a full circle clockwise, returns to P with same heading.
- **Loop must enter back into the corridor** — the loop's circumference must lie INSIDE the corridor's perpendicular extent ([−75 m, +75 m] perp from highway centerline).
- **Loop's LiDAR FOV must overlap the just-flown survey's coverage** so post-loop point cloud ties to the existing one.
- Entry/exit on the loop = last survey waypoint (at +25 m perp from highway).

### Implementation
- Loop entry/exit at the last survey waypoint (last_xy at +25 m perp).
- Loop center at last_xy + R × perp_right.
- Loop radius **R = 25 m** so the loop spans perp ∈ [+25 m, +75 m] — entirely within the corridor's right half.
- Loop circumference sampled at 12 points (≈ every 30°), all at +50 m AGL.
- **Verification**: max perp of loop = 75 m ≤ 75 m corridor edge ✓; min perp = 25 m ≥ −75 m corridor edge ✓.

### "Cross previous path" interpretation
A 360° right-turn loop with entry on the survey is geometrically TANGENT to the survey, not crossing. The "cross previous path" requirement is satisfied by the **LiDAR FOV during flight overlapping the previously-flown survey's coverage** — at the loop's far edge (+75 m perp), the drone's 100 m LiDAR swath extends from +25 m to +125 m perp, overlapping the survey FOV that extended to ~+75 m perp.

If Ryan rejects this interpretation, the alternative is to position the loop entry OFF the survey line (e.g., drone continues past the last survey WP into the loop entry); the loop circle then crosses the survey at two points. **Pending Ryan confirmation.**

---

## 4. CLOSING TRANSECT geometry

User words: *"this loop would cross waypoint 60 perpendicular to the center line. And then it would fly across the corridor, perpendicular, until it fully covers the entire width of our final point cloud."* and *"the point cloud it creates along the straight line will fully overlap with the point cloud that is created through the entire corridor, including the next mission."*

Plus: *"only has fifty percent overlap with the transect instead of 100."*

### Constraints
- **Perpendicular to highway tangent** at the transect's midpoint.
- **Flown at mission speed** (11.5 m/s).
- The transect's **LiDAR FOV strip must FULLY overlap the corridor coverage** (i.e., the strip is 100% inside the corridor footprint).
- Transect spans the **entire corridor width** (its perpendicular extent ≥ corridor's perpendicular extent).

### Geometric derivation
- LiDAR FOV strip created by flying the transect:
  - Along-corridor extent (parallel to highway): 100 m wide (= 2·AGL = LiDAR swath at 50 m AGL).
  - Perp-to-corridor extent: equals transect length.
- For 100% strip-inside-corridor (along direction): strip must satisfy `transect_along − 50 m ≥ A_along` AND `transect_along + 50 m ≤ B_along`.
  - → transect placed at `transect_along = B_along − 50 m` (Mission 1) so FOV strip occupies the last 100 m of corridor [B_along − 100, B_along]. **All inside this mission's corridor.**
- For transect to span corridor width: transect length ≥ 150 m. Use **200 m** (= corridor width 150 m + 25 m margin per side).

### Implementation
- **Transect midpoint** at along-distance `B_along − 50 m` along the highway, on the highway centerline (perp = 0).
- **Transect endpoints** at midpoint ± 100 m × perp_right (perpendicular to highway tangent at midpoint). 2 waypoints total.
- All at +50 m AGL.
- **Mirror geometry for Mission 2** at `A_along + 50 m`.

### Overlap verification
- Transect strip: along ∈ [B_along − 100, B_along], perp ∈ [−100, +100].
- This mission's corridor: along ∈ [A_along, B_along], perp ∈ [−75, +75].
- Overlap region: along ∈ [B_along − 100, B_along], perp ∈ [−75, +75] = 100 m × 150 m = 15,000 m².
- Transect strip area: 100 m × 200 m = 20,000 m².
- **Strip area inside corridor: 15,000 / 20,000 = 75%.** The other 25% extends 25 m past each corridor edge on the perpendicular direction.

**This is NOT 100% strip-inside-corridor**. Two possible interpretations:
- (a) Ryan wants 100% of strip inside corridor (= no overshoot past corridor edges). Then transect length ≤ 150 m. Use 150 m exactly, which still spans the corridor but doesn't overshoot.
- (b) Ryan wants the corridor area at the transect position to be 100% inside the strip. Both 150 m and 200 m satisfy this.

**Default to interpretation (b) with 200 m transect** for some calibration margin past the corridor edges. **Pending Ryan confirmation.**

---

## 5. Survey transect waypoint emission rule

User words: *"only emit a waypoint where the bearing changes: this only applies when using AltitudeMode=3."*

### Implementation
- For each session's offset polyline (highway centerline offset by +25 m perpendicular right):
  1. Sample the offset polyline densely (every 25 m along the highway).
  2. Apply Douglas-Peucker simplification with tolerance ≈ 5 m. This drops collinear intermediate points and keeps the corner structure.
- Result: typically 4–10 waypoints across a 4.5 km strip, sparse on straights, dense on curves.

### Rationale
- AltitudeMode = 3 (terrain follow) auto-interpolates terrain between waypoints — extra waypoints on straights add nothing.
- Extra waypoints risk the drone overshooting and backtracking to hit each one precisely, degrading scan uniformity.

---

## 6. JSON / AMC-required fields

### Top-level
- `fileType: "Plan"`, `version: 1`
- `mission.version: 2`, `mission.vehicleType: 2`, `mission.firmwareType: 12`
- `mission.cruiseSpeed: 15`, `mission.hoverSpeed: 10` (these are autopilot fallback constants, NOT the mission flight speed; cmd 178 sets the actual flight speed)
- `mission.globalPlanAltitudeMode: 3`
- `mission.plannedHomePosition: [home_lat, home_lon, ground_amsl_at_home]`

### Per cmd 16 / cmd 17 waypoint (REQUIRED — AMC rejects plans without these on standalone WPs)
- `MISSION_ITEM_ID`: string of 0-based index (e.g., `"3"`)
- `groupTag: 0`
- `AMSLAltAboveTerrain`: numeric AMSL value (= `params[6]`), NOT `null`
- `Altitude`: numeric AGL value (e.g., `50.0`)
- `AltitudeMode: 3`
- `autoContinue: true`
- `command: 16` (or `17` for LOITER_UNLIM)
- `doJumpId`: 1-based sequential
- `frame: 0` (absolute MSL)
- `params: [0, 0, 0, null, lat, lon, alt_amsl]`
- `type: "SimpleItem"`

### Per cmd 530 / cmd 178
- `MISSION_ITEM_ID`, `groupTag: 0`, `autoContinue: true`, `doJumpId`, `frame: 2`, `params: [...]`, `type: "SimpleItem"`
- NO altitude-related fields.

### File format
- Minified (no whitespace), LF line endings, UTF-8 no BOM.
- `json.dumps(plan, separators=(',', ':'))` + `open(path, 'wb').write(...)`.

---

## 7. DEM-baked altitudes

Every standalone cmd 16 / cmd 17 waypoint's `params[6]` (= `AMSLAltAboveTerrain` = `Altitude_AMSL`) must be `terrain_amsl(lat, lon) + AGL`. NOT a flat constant.

Standalone WPs include: kinematic line endpoints, figure-8 vertices, sparse survey waypoints, closing loop vertices, closing transect endpoints, LOITER hold.

(`AGL` field on the WP is the constant value 50.0 for AMC's display; `params[6]` carries the absolute MSL value.)

---

## 8. Verification checks (this spec is the source of truth)

A plan PASSES this spec iff ALL of the following hold:

1. **Item count by section** matches the table in §2 (Mission 1: 1 + 1 + 2 + 11 + N_sparse + 12 + 2 + 1; Mission 2 different ordering).
2. **Kinematic line length** ≥ 115 m, perpendicular to highway tangent at the cal location.
3. **Figure-8 centroid** = end of preceding kinematic line (start cal) OR start of following kinematic line (end cal), within 1 m tolerance. NOT at A or B.
4. **Survey waypoints**: at +25 m perp_right offset from highway (or −25 m for Mission 2). Sparse: total count ≤ 10 for a 4.5 km strip. No two consecutive waypoints have identical bearings (= no collinear redundancy).
5. **Closing loop**: 12 waypoints, perfect circle (radius std < 1 m), radius = 25 m, center at +50 m perp from highway, all WPs at perp ∈ [+25 m, +75 m].
6. **Closing transect**: 2 waypoints, length ≈ 200 m, perpendicular to highway at the inset position (along = B_along − 50 m for Mission 1).
7. **LOITER_UNLIM** at end of closing transect (Mission 1) or end of kinematic line (Mission 2).
8. **AMC fields**: every cmd 16 / cmd 17 has `AMSLAltAboveTerrain`, `Altitude`, `AltitudeMode`, `MISSION_ITEM_ID`, `groupTag`.
9. **cmd 530 params** = `[0, 2, null, null, null, null, null]`.
10. **cruiseSpeed** = 15, **hoverSpeed** = 10, **globalPlanAltitudeMode** = 3.
11. **DEM altitudes**: every WP's `params[6]` ≈ terrain at (lat, lon) + 50 m. Spot-check 3 WPs.
12. **File format**: minified, LF, UTF-8 no BOM.

---

## 9-RESOLVED. Ryan's answers (2026-06-26)

### A1. Closing transect length = 11 s × 11.5 m/s = **126.5 m**

Ryan: *"10 seconds is the key. make it 11 just to allow for accel/decel."* Applies to both the closing transect AND the kinematic line — same flight-time formula.

### A2. Closing loop is a TEARDROP (not a closed circle)

Ryan: *"it looks like a corner (our final waypoint) with a teardrop/loop coming off the corner at 45 degrees if the flight line is straight north and the transect is straight west. the radius is constant, but it has a tangent from the waypoint about 1*r in length, then it does the turn to the right, then has another tangent that intersects the waypoint. so the waypoint is the source of the teardrop and is the start of the perpendicular flight line."*

**Geometry** (in user's example: survey heading north, transect heading west — apply analogously when survey heading is `tan_S` (forward) and transect heading is `perp_left_of_tan_S`):

- **Anchor waypoint** = the last survey waypoint (= corner where survey meets transect).
- **Tangent 1**: from anchor, heading `tan_S` (continuing survey direction), length = R.
- **Arc**: starting at tangent 1 end, **270° clockwise (right turn)**, constant radius R. Arc center is at `anchor + R·tan_S + R·perp_right_of_tan_S`.
- **Tangent 2**: from arc end, heading `perp_left_of_tan_S` (= transect direction), length R, ends at anchor.
- **Transect**: continues from anchor heading `perp_left_of_tan_S`, length 126.5 m.

The teardrop physically occupies the quadrant `+tan_S × +perp_right_of_tan_S` from the anchor (= "outside" of the survey-to-transect corner, at 45° off the bisector).

**Implementation values**:
- R = 25 m (= AGL/2 — matches operational scale; user accepted "about 1*r" for tangents)
- Arc sampled at 10 intermediate waypoints (every 27° around the 270° sweep). Plus tangent-1 end + arc end as WPs = 12 teardrop WPs total (tangent-2 end is implicit since the same point is the transect start, which is also the anchor — drone flies straight through).
- Verification: arc center at `+R*tan_S + R*perp_right` relative to anchor; arc max excursion at `center + R*perp_right = +R*tan_S + 2R*perp_right` from anchor = at +50 m perp (within corridor's right edge at +75 m) and +25 m along — entirely within the corridor's right half. ✓

### A3. Survey transect side confirmed

A→B at **+25 m perpendicular RIGHT of forward direction** (= south side of highway at session 9 going NE).
B→A at **−25 m perpendicular RIGHT of forward direction** = **+25 m perpendicular LEFT of forward direction** (= north side of highway when going SW).

In absolute terms: the two transects FLANK the highway centerline. A→B on one side, B→A on the other. Combined coverage = full 150 m corridor centered on highway (with 50% overlap at the highway centerline strip).

### A4. End-cal kinematic line direction = toward landing position along centerline

Ryan: *"Kinematic line should be toward the takeoff/landing position, which we can assume to be somewhere along the centerline outside of the mission flight area."*

**Implementation**:
- HOME (= `plannedHomePosition`) is set to the takeoff/landing position: on the highway centerline, **50 m outside** the mission's flight area boundary (= 50 m before A for Mission 1's HOME, 50 m past B for Mission 2's HOME, but Mission 2 also returns to land near A, so the LANDING position is back near A; spec uses A_along - 50 m for both missions' relevant "landing position" reference because both sessions return to the team's parked vehicle near A).
- Mission 2 end kinematic line: starts at figure-8 centroid (= end of Mission 2's closing transect), heads TOWARD the landing position, length 126.5 m. Direction = unit vector from figure-8 centroid to landing position.
- Drone reaches end of kinematic line, then LOITERs. Operator manually flies the rest of the way to land.

### Mission 1 start kinematic line — direction NOT changed (still perpendicular)

Ryan's earlier instruction (MSG 96) for the START kinematic line was *"perpendicular to highway"*. That spec stands for Mission 1's session-start cal. The Q4 answer applies only to Mission 2's END cal kinematic.

---

## 10. Updated Mission 1 (A→B) structure

| # | Item | WP count | Position |
|---|---|---:|---|
| 0 | cmd 530 | 1 | header |
| 1 | cmd 178 | 1 | speed 11.5 |
| 2 | K1 (kinematic line start) | 1 | At A_along, perp = −101.5 m perp_right (= −101.5 m perp from highway) |
| 3 | K2 (kinematic line end, = figure-8 centroid) | 1 | At A_along, perp = +25 m perp_right of tan_A |
| 4–14 | Figure-8 (11 WPs) | 11 | Centered at K2 |
| 15–N | Survey transect (sparse, DP-simplified) | sparse (~4–10) | At +25 m perp_right offset, A_along → B_along |
| N+1 | Teardrop tangent-1 end (= arc start) | 1 | last_xy + R·tan_B (R = 25 m) |
| N+2 .. N+11 | Arc intermediate samples | 10 | 270° clockwise around (last_xy + R·tan_B + R·perp_right_B) |
| N+12 | Arc end (= tangent-2 start) | 1 | last_xy + R·perp_right_B |
| N+13 | Closing transect end | 1 | last_xy + 126.5 m · perp_left_B |
| N+14 | LOITER_UNLIM | 1 | Same position as N+13 |

Total nav waypoints: 1 + 1 + 11 + N + 12 + 1 + 1 = **N + 27** (where N is the number of sparse survey WPs).

HOME = (A_along − 50 m, 0 perp) on centerline = takeoff position, 50 m before A on highway, outside the mission flight area.

---

## 11. Open inferences still requiring confirmation

### Q1. CLOSING TRANSECT LENGTH — Ryan gave two different numbers

- **MSG 96 (first cross-line spec)**: *"perpendicular to highway. start 50 m outside the flight area polygon, fly perpendicular through the polygon in a straight line to a point 50m beyond the edge of the flight area polygon."* For the 150 m corridor: **transect length = 50 + 150 + 50 = 250 m**.
- **MSG 101 (closing transect)**: *"this could be the same distance as our straight line was at the beginning. I think that would be safe."* Straight line = 115 m. So **transect length = 115 m**.

These are the SAME element (the closing transect), described in two different messages. Spec needs Ryan to pick: **115 m** or **250 m** (or some hybrid).

### Q2. CLOSING LOOP GEOMETRY — three constraints, can't satisfy all three simultaneously for a 360° closed loop

Ryan's three statements about the loop:
- (a) **Right turn** (MSG 100): *"a full loop at waypoint 61 turning right"*.
- (b) **Cross own previous path** (MSG 100): *"cross its own previous path somewhere around waypoint 60"*. This means the loop's circumference geometrically intersects the survey transect line at two points (= a chord through the loop).
- (c) **Enter back into the corridor** (MSG 104): *"It doesn't appear to be turning a radius that enters it back into the corridor like we discussed."*

Geometric reality for a 360° closed loop (drone enters and exits at same point with same heading) entered from a +25 m perp survey going forward:
- A **right-turn** loop centers on the right side of survey (= further out, perp ≥ +25 + R). It cannot cross the survey at two points (tangent only) AND cannot extend into the corridor's interior half (perp < +25).
- A **left-turn** loop centers on the left side of survey (= toward highway centerline, perp = +25 − R). It CAN enter back into the corridor (perp from +25 down toward and past the centerline), but it's a LEFT turn, not a right turn.
- A loop entered OFF the survey line (e.g., drone continues past last survey WP into a loop entry that's NOT on the survey) CAN cross the survey at two points, but the entry geometry is more complex.

Ryan needs to pick which two of the three to satisfy strictly, or describe an alternative loop geometry. Possible reconciliations:
- (1) "Right turn" is actually a left turn (mis-spoken). Loop center inside corridor on the left side of survey.
- (2) Loop entry is OFF the survey line (drone continues past last survey WP). Loop circumference can then chord-cross the survey line.
- (3) "Cross previous path" means LiDAR FOV crossing, not geometric line crossing. (Spec §3's current interpretation.)
- (4) "Enter back into corridor" means the LiDAR FOV during the loop covers corridor area, not the geometric loop position.
- (5) The loop isn't a 360° closed circle — it's a teardrop / single Gerono lobe where entry and exit have different headings.

### Q3. SURVEY TRANSECT OFFSET SIDE

The two transects (one per mission of the session) must be offset by ±AGL/2 perpendicular from the polyline so the corridor is covered in two passes with 50% overlap. Ryan never specified which side is +.
- Default (skill convention): A→B at +25 m perpendicular RIGHT of forward (= south of highway at session 9 going NE). B→A at −25 m perpendicular RIGHT of forward (= north of highway when going SW = same absolute side as A→B's +25 m? or mirrored?).
- This question affects whether the two missions cover the SAME 150 m strip or shifted strips.

### Q4. MISSION 2 (B→A) DETAILED PLACEMENT

Ryan confirmed Mission 2 ORDER (Mission 2 ends with closing maneuvers in the same loop-then-transect order as Mission 1, then end-cal in reversed order figure-8-then-kinematic). Spec §2 (current) places:
- Closing transect at `A_along + 50 m` (mirror of Mission 1's `B_along - 50 m`).
- Figure-8 centered at end of closing transect.
- Kinematic line ≥ 115 m perpendicular from figure-8 centroid.
- LOITER at end of kinematic.

These specific placements were not stated by Ryan; they're spec-author inferences. Ryan: are they OK as defaults, or specify alternatives?
