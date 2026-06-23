"""Iteratively add launch points in worst gaps until >= 90% coverage,
and rank tile extensions for Fergus3..Fergus20 by acres-gained-per-km.

Algorithm — gap fills:
  1. Start from existing coverage (Fergus1..Fergus20 union).
  2. While coverage < target:
       a. Identify the largest uncovered polygon.
       b. Find the centerline segment that crosses it.
       c. Sample DEM (50 m cadence) along that segment.
       d. Pick the local-max elevation point inside the gap = new launch.
       e. Simulate adding a 3.6 km pair (1.8 km east + 1.8 km west) at that launch.
       f. Recompute coverage. Stop if >= 90% or no useful launch.

Algorithm — extension rankings:
  For each tile (Fergus3..Fergus20), measure acres-gained vs current coverage
  by extending the FAR end (the end away from the meeting point) by
  {0.25, 0.5, 0.75, 1.0} km. Skip Fergus1 / Fergus2 (off-limits).
"""
import os, sys, math, re, json, glob

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SKILL_DIR, 'scripts'))
from dem_lookup import ensure_dem_for_bbox, terrain_amsl
from generate_fergus_pair1 import (
    load_centerline, hav, douglas_peucker, AGL, TURNAROUND_M,
    HALF_LS_M, LINE_SPACING_M, TILE_LEN_M, DECIMATE_TOL_M,
)
from generate_fergus_all_pairs import (
    project_onto_centerline, insert_meeting_into_centerline, walk_along,
)
from coverage_check_multi import (
    parse_kml_polygon, parse_plan_geometry, make_projection,
    corridorscan_coverage_polygon, coverage_to_kml,
)
from shapely.geometry import Polygon, LineString
from shapely.ops import unary_union

KML_CENTERLINE = 'C:/Users/rharbach.STAHLY/Downloads/HighwayCenterline.kml'
KML_TARGET     = 'C:/Users/rharbach.STAHLY/Downloads/Fergus Hilger-Roy — corridor union.kml'
PLAN_DIR       = 'C:/Users/rharbach.STAHLY/Documents/Auterion Mission Control/Missions'
DEM_SAMPLE_M   = 50.0
TARGET_PCT     = 90.0
CORRIDOR_WIDTH = 140.208

def acres(area_m2): return area_m2 / 4046.86

def load_existing_coverage(plan_paths, to_xy):
    polys = []
    for pp in plan_paths:
        kind, geom_ll, agl, cw, ta = parse_plan_geometry(pp)
        if kind != 'CorridorScan':
            continue
        poly = corridorscan_coverage_polygon(geom_ll, agl, cw, ta, to_xy)
        if poly is not None and not poly.is_empty:
            polys.append(poly)
    return unary_union(polys)

def sample_centerline_with_dem(centerline_ll, sample_m):
    """Walk the centerline cumulatively and sample DEM at sample_m intervals."""
    samples = []
    cum = 0.0
    acc = 0.0
    last = centerline_ll[0]
    samples.append((cum, last[0], last[1], terrain_amsl(last[0], last[1])))
    for i in range(1, len(centerline_ll)):
        step = hav(centerline_ll[i-1], centerline_ll[i])
        if step == 0: continue
        # Walk in increments of sample_m along the segment
        s = 0.0
        while s + sample_m < step:
            s += sample_m
            frac = s / step
            lat = centerline_ll[i-1][0] + frac * (centerline_ll[i][0] - centerline_ll[i-1][0])
            lon = centerline_ll[i-1][1] + frac * (centerline_ll[i][1] - centerline_ll[i-1][1])
            cum_pt = cum + s
            samples.append((cum_pt, lat, lon, terrain_amsl(lat, lon)))
        # Add the segment endpoint
        cum += step
        last = centerline_ll[i]
        samples.append((cum, last[0], last[1], terrain_amsl(last[0], last[1])))
    return samples

def build_pair_coverage(launch_ll, centerline_ll, to_xy):
    """Build the coverage polygon for ONE pair (2 tiles) centered at launch_ll.
    Returns (coverage_poly, meeting_pt_ll, east_poly_pts, west_poly_pts)."""
    # Snap launch onto the centerline
    d_proj, meeting_pt, seg_idx, frac = project_onto_centerline(centerline_ll, launch_ll)
    cl, i_meet = insert_meeting_into_centerline(centerline_ll, seg_idx, frac, meeting_pt)
    east_path, _ = walk_along(cl, i_meet, +1, TILE_LEN_M)
    west_path, _ = walk_along(cl, i_meet, -1, TILE_LEN_M)
    east_poly = douglas_peucker(list(reversed(east_path)), DECIMATE_TOL_M)
    west_poly = douglas_peucker(list(reversed(west_path)), DECIMATE_TOL_M)

    # Coverage polygons for both tiles (use the same convention as
    # generate_fergus_pair1: polyline + CW/2 + AGL/2 buffer, with TA caps)
    east_cov = corridorscan_coverage_polygon(east_poly, AGL, CORRIDOR_WIDTH, TURNAROUND_M, to_xy)
    west_cov = corridorscan_coverage_polygon(west_poly, AGL, CORRIDOR_WIDTH, TURNAROUND_M, to_xy)
    return unary_union([east_cov, west_cov]), meeting_pt, east_poly, west_poly, d_proj

def centerline_points_in(polygon_xy, samples_xy):
    """Return indices of `samples_xy` that lie inside `polygon_xy`."""
    inside = []
    for i, (x, y) in enumerate(samples_xy):
        if polygon_xy.contains_properly(LineString([(x-1e-3, y), (x+1e-3, y)]).centroid):
            inside.append(i)
        elif polygon_xy.intersects(LineString([(x, y), (x, y+1e-3)])):  # boundary tolerance
            inside.append(i)
    return inside

def pick_high_point(samples, idx_in_gap):
    """Return the sample with the highest elevation among the candidate indices."""
    if not idx_in_gap: return None
    best = max(idx_in_gap, key=lambda i: samples[i][3])
    return best

def main():
    # Load target
    target_list = parse_kml_polygon(KML_TARGET)
    target_outer_ll, target_holes_ll = target_list[0]
    ref_lat = sum(p[0] for p in target_outer_ll) / len(target_outer_ll)
    ref_lon = sum(p[1] for p in target_outer_ll) / len(target_outer_ll)
    to_xy, to_ll = make_projection(ref_lat, ref_lon)
    target_xy = Polygon([to_xy(*p) for p in target_outer_ll],
                        [[to_xy(*p) for p in h] for h in target_holes_ll])
    print(f'Target: {acres(target_xy.area):.2f} ac')

    # Warm DEM for the full bbox
    pad = 0.02
    lats = [p[0] for p in target_outer_ll]; lons = [p[1] for p in target_outer_ll]
    print(f'Warming DEM cache for bbox lat [{min(lats):.4f},{max(lats):.4f}] lon [{min(lons):.4f},{max(lons):.4f}]')
    ensure_dem_for_bbox(min(lats)-pad, max(lats)+pad, min(lons)-pad, max(lons)+pad, resolution_m=10.0)

    # Existing coverage (Fergus1..Fergus20)
    plans = [os.path.join(PLAN_DIR, f'Fergus{n}.plan') for n in range(1, 21)]
    coverage = load_existing_coverage(plans, to_xy)
    current_cov_ac = acres(coverage.intersection(target_xy).area)
    print(f'Existing coverage (Fergus1..20): {current_cov_ac:.2f} ac = '
          f'{100*current_cov_ac/acres(target_xy.area):.2f}%')

    # Centerline + DEM profile
    centerline_ll = load_centerline(KML_CENTERLINE)
    print(f'Centerline: {len(centerline_ll)} vertices')
    print(f'Sampling DEM along centerline at {DEM_SAMPLE_M:.0f} m...')
    samples = sample_centerline_with_dem(centerline_ll, DEM_SAMPLE_M)
    print(f'  {len(samples)} DEM samples')
    samples_xy = [to_xy(s[1], s[2]) for s in samples]
    elevs = [s[3] for s in samples]
    print(f'  Centerline elevation range: {min(elevs):.0f} - {max(elevs):.0f} m AMSL')

    # === Phase 1: iterative gap fills ===
    print(f'\n=== Phase 1: Gap-fill launches until >= {TARGET_PCT}% coverage ===')
    new_pairs = []
    iteration = 0
    max_iter = 30
    while iteration < max_iter:
        iteration += 1
        uncov = target_xy.difference(coverage)
        if uncov.is_empty:
            print(f'  100% coverage reached.')
            break
        cov_ac = acres(coverage.intersection(target_xy).area)
        cov_pct = 100 * cov_ac / acres(target_xy.area)
        if cov_pct >= TARGET_PCT:
            print(f'  Reached {cov_pct:.2f}% (>= {TARGET_PCT}%). Stopping.')
            break

        # Largest current uncovered polygon
        polys = list(uncov.geoms) if uncov.geom_type == 'MultiPolygon' else [uncov]
        polys.sort(key=lambda p: -p.area)
        gap = polys[0]
        gap_ac = acres(gap.area)
        # Centerline samples inside this gap
        from shapely.geometry import Point
        idx_in_gap = [i for i, xy in enumerate(samples_xy) if gap.contains(Point(xy))]
        if not idx_in_gap:
            # No centerline inside the gap — try a polygon that does contain centerline
            found = False
            for cand in polys:
                idx = [i for i, xy in enumerate(samples_xy) if cand.contains(Point(xy))]
                if idx:
                    gap = cand; gap_ac = acres(gap.area); idx_in_gap = idx; found = True; break
            if not found:
                print(f'  Iter {iteration}: no gap with centerline inside. Stopping.')
                break

        # Pick the high-point inside the gap
        best_i = pick_high_point(samples, idx_in_gap)
        best = samples[best_i]
        launch_ll = (best[1], best[2])
        launch_elev = best[3]

        # Build coverage for this pair
        pair_cov, meeting_pt, east_poly, west_poly, d_proj = build_pair_coverage(
            launch_ll, centerline_ll, to_xy)

        # Pair coverage contribution to TARGET (only)
        before_ac = acres(coverage.intersection(target_xy).area)
        new_coverage = unary_union([coverage, pair_cov])
        after_ac = acres(new_coverage.intersection(target_xy).area)
        added_ac = after_ac - before_ac

        # Sanity: launch should be ABOVE corridor (compare to mean elev of polylines)
        e_elev = [terrain_amsl(p[0], p[1]) for p in east_poly]
        w_elev = [terrain_amsl(p[0], p[1]) for p in west_poly]
        all_elev = e_elev + w_elev
        corridor_mean = sum(all_elev) / len(all_elev)
        corridor_max = max(all_elev)
        above_mean = launch_elev - corridor_mean
        above_max = launch_elev - corridor_max

        new_pair_num = 10 + len(new_pairs)            # Pair 10, 11, 12, ...
        new_e_name = f'Fergus{21 + 2*len(new_pairs)}' # Fergus21, 23, 25, ... (start cal flight)
        new_w_name = f'Fergus{22 + 2*len(new_pairs)}' # Fergus22, 24, 26, ... (end cal flight)

        print(f'  Iter {iteration}: Gap = {gap_ac:.2f} ac (largest of {len(polys)})')
        print(f'    Launch: ({launch_ll[0]:.6f}, {launch_ll[1]:.6f}) elev {launch_elev:.0f} m')
        print(f'    Meeting (centerline): ({meeting_pt[0]:.6f}, {meeting_pt[1]:.6f}) projection dist {d_proj:.0f} m')
        print(f'    Corridor elev mean {corridor_mean:.0f} / max {corridor_max:.0f} m'
              f' -> launch is {above_mean:+.0f} m above mean, {above_max:+.0f} vs max')
        print(f'    Pair adds {added_ac:.2f} ac to target ({100*added_ac/acres(target_xy.area):.2f}%)')
        print(f'    Files would be {new_e_name}.plan (east, START cal) + {new_w_name}.plan (west, END cal)')

        if added_ac < 1.0:
            print(f'    Add < 1 ac — diminishing returns. Stopping.')
            break

        new_pairs.append({
            'pair': new_pair_num,
            'launch_ll': launch_ll,
            'launch_elev_m': launch_elev,
            'meeting_ll': meeting_pt,
            'corridor_mean_elev_m': corridor_mean,
            'corridor_max_elev_m': corridor_max,
            'above_mean_m': above_mean,
            'gap_ac_before': gap_ac,
            'added_ac': added_ac,
            'east_name': new_e_name, 'west_name': new_w_name,
            'east_poly': east_poly, 'west_poly': west_poly,
        })
        coverage = new_coverage

    final_cov_ac = acres(coverage.intersection(target_xy).area)
    final_pct = 100 * final_cov_ac / acres(target_xy.area)
    print(f'\nFinal coverage after {len(new_pairs)} new pairs: {final_cov_ac:.2f} ac = {final_pct:.2f}%')

    # === Phase 2: extension rankings on Fergus3..Fergus20 ===
    print(f'\n=== Phase 2: Extension opportunities for Fergus3..Fergus20 (Fergus1/2 off-limits) ===')
    # Re-load existing coverage so extensions are measured against pre-phase-1 baseline
    base_coverage = load_existing_coverage(plans, to_xy)
    base_cov_ac = acres(base_coverage.intersection(target_xy).area)

    EXTENSIONS = [0.25, 0.5, 0.75, 1.0]
    ext_results = []
    for n in range(3, 21):
        pp = os.path.join(PLAN_DIR, f'Fergus{n}.plan')
        kind, polyline_ll, agl, cw, ta = parse_plan_geometry(pp)
        if kind != 'CorridorScan' or len(polyline_ll) < 2:
            continue
        # The polyline is ordered [far_end, ..., exit_end]. Extending the FAR end
        # means walking further along the centerline FROM the far end, away from the meeting.
        far = polyline_ll[0]
        near = polyline_ll[1]
        # Direction the polyline was walking when it left the meeting:
        # vec from polyline[1] -> polyline[0] is the "outward" direction
        # We project `far` onto the centerline to figure out which way to walk.
        d_far, far_proj, far_seg, far_frac = project_onto_centerline(centerline_ll, far)
        # Use the closer of polyline[1] to centerline to decide direction
        d_near, near_proj, near_seg, near_frac = project_onto_centerline(centerline_ll, near)
        # If far_seg > near_seg (in KML order) → extending +1 means further east
        if far_seg >= near_seg:
            direction = +1
        else:
            direction = -1
        cl, i_far = insert_meeting_into_centerline(centerline_ll, far_seg, far_frac, far_proj)

        for ext_km in EXTENSIONS:
            ext_m = ext_km * 1000.0
            ext_path, _ = walk_along(cl, i_far, direction, ext_m)
            if len(ext_path) < 2:
                continue
            # Build coverage for the extension only (existing tile + the new extension)
            # Simpler: rebuild the full extended polyline = ext_path (away from meeting first)
            # + existing polyline (after the far_end interpolation duplicate)
            extended = list(reversed(ext_path[1:])) + polyline_ll
            extended_dp = douglas_peucker(extended, DECIMATE_TOL_M)
            new_cov = corridorscan_coverage_polygon(extended_dp, AGL, CORRIDOR_WIDTH, TURNAROUND_M, to_xy)
            # Difference from current tile's coverage
            current_tile = corridorscan_coverage_polygon(polyline_ll, AGL, CORRIDOR_WIDTH, TURNAROUND_M, to_xy)
            other_tiles = base_coverage.difference(current_tile)
            combined_with_ext = unary_union([other_tiles, new_cov])
            added_ac = acres(combined_with_ext.intersection(target_xy).area) - base_cov_ac
            if added_ac > 0.01:
                ext_results.append({
                    'plan': f'Fergus{n}', 'direction': 'east' if direction > 0 else 'west',
                    'extension_km': ext_km, 'added_ac': added_ac,
                    'ac_per_km': added_ac / ext_km,
                })

    # Rank by acres per km (efficiency), then absolute acres
    ext_results.sort(key=lambda r: (-r['ac_per_km'], -r['added_ac']))
    print(f'  Plan      Dir   +km    +ac    ac/km')
    seen_keys = set()
    top = []
    for r in ext_results:
        key = (r['plan'], r['direction'])
        if key in seen_keys: continue
        seen_keys.add(key)
        top.append(r)
        if len(top) >= 15: break
    # Re-sort top picks by ac/km
    top.sort(key=lambda r: -r['ac_per_km'])
    for r in top:
        print(f'  {r["plan"]:<10}{r["direction"]:<6}{r["extension_km"]:<6.2f}{r["added_ac"]:<7.2f}{r["ac_per_km"]:.2f}')

    # === Phase 3: emit summary
    print('\n=== Summary ===')
    print(f'Baseline (Fergus1..20): {base_cov_ac:.2f} ac = {100*base_cov_ac/acres(target_xy.area):.2f}%')
    print(f'After {len(new_pairs)} new gap-fill pairs: {final_cov_ac:.2f} ac = {final_pct:.2f}%')
    print(f'\nProposed new launches:')
    print(f'  {"Pair":<5}{"Files":<22}{"Launch lat":<12}{"Launch lon":<13}{"Elev":<6}{"Above":<8}{"Gain"}')
    for p in new_pairs:
        ll = p['launch_ll']
        print(f'  {p["pair"]:<5}{p["east_name"]+"/"+p["west_name"]:<22}'
              f'{ll[0]:<12.6f}{ll[1]:<13.6f}{p["launch_elev_m"]:<6.0f}'
              f'{p["above_mean_m"]:+5.0f} m {p["added_ac"]:.2f} ac')

if __name__ == '__main__':
    main()
