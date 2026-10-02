# Teardrop revision plan (2026-06-29)

## What this revises

`specs/Fergus50_corridor_plan_spec.md` § 9-A2 "Closing loop is a TEARDROP" and § 10 (item-count table).

Currently the teardrop is a constant-radius circle (R=25 m, 12 sample WPs in 270° arc). Ryan's hand-drawn purple correction on the v4 plot shows a wider, smoothly opening teardrop. He picked Option C (logarithmic-spiral teardrop) with simplified waypoint density.

## New spec for the closing teardrop

### Curve type
**Logarithmic spiral**, parameterized as `r(θ) = a · e^(k·θ)` in the spiral's intrinsic frame.

- Sweep direction: **clockwise (right turn)**
- Total sweep angle: **270°** (= 3π/2 rad)
- Radius at entry (smallest): **R_start = 25 m**
- Radius at exit (largest): **R_end = 75 m**
- Growth rate `k` derived from `R_end / R_start = e^(k · 3π/2)` ⇒ k ≈ −0.233 (negative because clockwise).

### Geometric placement (REVISED 2026-06-29 v2 per Ryan)

**Ryan's correction**: "the spiral must enter the flight area (gray area in the image) on a path perpendicular to the centerline and remain on that path thru exit of said area. and then the existing red line can go away because the spiral to tangent you are working on IS the transect!"

The closing block is now: spiral → straight perpendicular line. There is **NO separate closing transect from the anchor**. The spiral handles the curved transition from survey direction to perpendicular, and the straight tangent that follows the spiral end IS the cross-line transect.

- **Tangent 1** (straight line, R_start long): from anchor heading `tan_B`. Ends at `anchor + R_start · tan_B`.
- **Spiral**: 270° clockwise log-spiral arc, R growing from R_start = 25 m to R_end = 75 m. Sized so the spiral end lands at (≈ corridor right edge, perp ≈ +75 from highway centerline) with heading `perp_left of tan_B`. In v5 measurement: spiral end is at local frame (u ≈ −34, v ≈ +54) relative to anchor — that's roughly +79 m perp from highway centerline (= 4 m past corridor right edge), close enough to "perpendicular entry at the corridor right edge."
- **Straight perpendicular transect** (NEW): from spiral end heading `perp_left of tan_B`, **length 200 m**. The straight line crosses the corridor: starts at ~+79 m perp, crosses centerline (perp = 0) at ~79 m in, exits corridor left edge (perp = −75) at ~154 m in, ends at ~−121 m perp (= 46 m past corridor left edge, ≈ Ryan's "50 m beyond polygon" spec from MSG 96).
- **No more "anchor revisit" waypoint**: the v5 setup had an item 29 = anchor (gold star), where the drone flew tangent-2 from spiral end back to anchor and then started the closing transect. That's all removed. After spiral end, drone flies straight perpendicular for 200 m and LOITERs.
- **No more separate "closing transect from anchor"**: the v5 red line from anchor to LOITER is removed. The straight perpendicular line FROM the spiral end IS the transect.

### Waypoint count and placement (figure-8 density)
Ryan: *"use the existing figure-8 structure as a rule of thumb for waypoint density. simplify the structure."*

The figure-8 uses **11 WPs** for the whole figure (10 Gerono vertices + 1 closer). Applying that density rule to the teardrop's three segments:

| Segment | WP count | Notes |
|---|---:|---|
| Tangent 1 (anchor → spiral entry) | 1 | Just the endpoint (= entry to spiral) |
| Spiral arc (270° clockwise) | 9 | Sampled by **equal arc-length**, NOT by equal angle (because radius grows, equal-angle samples would crowd at the small end and sparse at the large end). 8 intermediate WPs + 1 endpoint = 9. |
| Tangent 2 (spiral exit → anchor) | 1 | Just the endpoint (= anchor; implicit if next item is the closing transect end since the drone flies a straight line through anchor to the transect end) |
| **Total teardrop WPs** | **11** | matches figure-8 density |

### Simplification: omit the anchor waypoint between tangent 2 and the closing transect
The drone flies tangent 2 from spiral exit toward anchor, then continues straight to the closing transect end. If those two segments are colinear (i.e., tangent 2's direction = perp_left direction), then anchor is just a point on a straight line; AMC doesn't need it as a waypoint.

But tangent 2 direction ≠ perp_left exactly (because the spiral exit isn't on the perp_right ray from anchor when R_end > R_start). So tangent 2 + transect is a bent path with anchor as the elbow.

**Decision**: emit `anchor` as a waypoint (so the drone flies tangent 2 to anchor, then turns to fly the transect to its endpoint).

This adds 1 WP. New total: 11 + 1 = **12 teardrop WPs + 1 transect endpoint = 13 WPs in the closing block** (vs 14 in v4: 1 tangent 1 end + 10 arc samples + 1 arc end + 1 transect end + 1 LOITER = 14; the v4 setup skipped the anchor WP between tangent 2 and transect because it was a straight line).

## Updated item-count table (Mission 1 / A→B, v6 = REVISED 2026-06-29)

| # | Item | WP count |
|---|---|---:|
| 0 | cmd 530 | 1 |
| 1 | cmd 178 | 1 |
| 2 | K1 (kinematic line start) | 1 |
| 3 | K2 (kinematic line end = figure-8 centroid) | 1 |
| 4–14 | Figure-8 (11 WPs) | 11 |
| 15–N | Sparse survey (DP-simplified) | N (typically 4–10) |
| N+1 | Tangent-1 end (spiral entry) | 1 |
| N+2 .. N+9 | Spiral arc samples (8 intermediate) | 8 |
| N+10 | Spiral end (heading perp_left, ≈ corridor right edge) | 1 |
| N+11 | Straight perpendicular transect end (200 m past spiral end) | 1 |
| N+12 | LOITER_UNLIM (same position as N+11) | 1 |

Total: **N + 27** items.

For Session 9 with N = 4 sparse survey WPs: **31 items** (was 32 in v5, 33 in v4).

The removed items vs v5: the explicit anchor-revisit WP (v5 item 29) and the separate closing transect from anchor (v5 item 30 was the transect endpoint at anchor + 126.5 · perp_left). Both gone.

## Spec verification checks (replaces v3 §8 checks for the teardrop)

| Check | Description |
|---|---|
| C1 | Item count by section matches table above |
| C2 | Kinematic line length ≥ 115 m, perpendicular to highway at A_along |
| C3 | Figure-8 centered at K2 |
| C4 | Survey at +25 m perp_right offset, sparse via DP |
| **C5a (revised)** | Tangent-1 length = R_start = 25 m, direction = tan_B |
| **C5b (revised)** | Spiral has 9 sample WPs (1 entry + 8 intermediate; note: entry = item N+1; the spiral END is at item N+10). 8 intermediate samples. |
| **C5c (revised)** | Spiral curve fits a log spiral: at each sample, `r(θ) / a = e^(k·θ)` holds to within 1 m residual; tangent direction at each sample matches the spiral derivative. |
| **C5d (revised)** | Spiral end heading is `perp_left of tan_B` (heading derived from the spiral's tangent at the exit angle; should match within 1° of `perp_left`) |
| **C5e (NEW)** | Spiral arc-length sampling: consecutive WPs have approximately equal arc-length spacing (not equal-angle). Variance of arc-length intervals < 20% of mean. |
| **C5f (NEW)** | Tangent-2: straight line from spiral end to anchor. Length = distance from spiral exit to anchor. |
| **C5g (NEW)** | Closing transect: from anchor, length 126.5 m, direction perp_left of tan_B |
| C7 | LOITER_UNLIM at end of closing transect |
| C8 | AMC required fields on all cmd 16/17 WPs |
| C9 | cmd 530 params = `[0, 2, null, null, null, null, null]` |
| C10 | cruiseSpeed/hoverSpeed/altMode = 15/10/3 |
| C11 | DEM-baked altitudes |
| C12 | File minified, LF, UTF-8 no BOM |
| C13 | HOME at A_along − 50 m on centerline |

Old C5d (loop inside corridor [+25, +75] perp) is dropped — the new spiral CAN extend beyond +75 m perp because R_end = 75 m, which means the spiral's outer extent reaches `+25 + 2·R_end = +175 m perp` past anchor. That's outside the corridor — by design, the teardrop is **outside** the corridor on the perp_right side, and the LiDAR FOV during the spiral sweeps back over the corridor for the data tie.

## Implementation plan

1. Edit `scripts/generate_fergus50_s09_ab.py`:
   - Remove the existing constant-R circle teardrop generation.
   - Add a new function `generate_log_spiral_teardrop(anchor, tan_B, perp_right_B, R_start, R_end, n_samples)` that:
     - Computes spiral parameters (a, k, θ_0, center) from R_start, R_end, sweep = −3π/2.
     - Generates arc-length parameterized samples (8 intermediate + 1 end).
     - Returns the list of (lat, lon, AMSL) for all teardrop WPs (tangent-1 end + 8 spiral + spiral end + anchor).
   - Append closing transect end + LOITER as before.
2. Regenerate `Fergus50_S09_AB.plan`.
3. Spawn the spec-verifier subagent with the revised check list (C1–C13).
4. If all PASS, spawn the plotter subagent to make a new PNG (`_v5_planview.png`).
5. Bring PNG back to Ryan for confirmation.

## Open question

**R_end value**: I picked **75 m** as a compromise. The purple sketch suggests the spiral reaches ~100–120 m from anchor at its widest. A larger R_end means a bigger teardrop and more LiDAR FOV overlap, but also longer flight time (the spiral arc grows). The user can override.

- R_end = 50 m: teardrop reaches +125 m perp from highway, 270° arc length ≈ 138 m (12 sec at 11.5 m/s)
- **R_end = 75 m: teardrop reaches +175 m perp, arc length ≈ 235 m (20 sec)** ← default
- R_end = 100 m: teardrop reaches +225 m perp, arc length ≈ 332 m (29 sec)
