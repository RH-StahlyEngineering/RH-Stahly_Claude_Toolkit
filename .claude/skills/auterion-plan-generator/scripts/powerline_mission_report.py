"""Generate the operational summary for the 12 powerline plans (Fergus3..Fergus14):
  - Flight time per plan + total (via estimate_flight_time.py)
  - Coverage acres broken into once-covered vs twice-or-more covered
  - Point density (ppsm) using the per-pass values: min 21, avg 51.5, max 85.1

Geometry model (matches the skill's LiDAR FOV convention):
  - Each tile has 2 transects at offsets +/- AGL/2 = +/- 35.05 m perpendicular to polyline
  - Each transect's swath is +/- AGL = +/- 70.1 m perpendicular to itself
  - Total tile swath: polyline buffered by AGL/2 + AGL = 105.16 m perpendicular each side
  - Within-tile twice-covered: polyline buffered by AGL/2 = 35.05 m each side (overlap of 2 transects)
  - Inter-tile overlap (within a pair): the turnaround extensions of 60.96 m past each polyline endpoint
"""
import os, sys, json, math

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SKILL_DIR, 'scripts'))

import dem_lookup
e = os.path.expanduser('~/.claude/dem_cache/dem_ee0aa3a8a9d0.json')
if os.path.exists(e):
    dem_lookup._explicit_meta_paths.insert(0, e)
    dem_lookup._local_dem = None
    dem_lookup._local_meta = None

from shapely.geometry import LineString, Polygon
from shapely.ops import unary_union
from estimate_flight_time import estimate as AMC_minutes
from coverage_check_multi import make_projection, parse_plan_geometry

PLAN_DIR = 'C:/Users/rharbach.STAHLY/Documents/Auterion Mission Control/Missions'
AGL = 70.104
TURNAROUND_M = 60.96
PLANS = [f'Fergus{n}.plan' for n in range(3, 15)]

# Per-pass point densities at 8 m/s + 230 ft AGL
PPSM_MIN = 21.0
PPSM_AVG = 51.5
PPSM_MAX = 85.1


def polyline_to_swath_polygons(polyline_ll, to_xy):
    """Return (total_swath_polygon, within_tile_twice_polygon) as shapely Polygons
    in local meters (anchored by to_xy projection).
    """
    xy = [to_xy(*p) for p in polyline_ll]
    if len(xy) < 2:
        return None, None
    # Extend polyline by turnaround at both ends (so swath extends past polyline endpoints)
    def extend_pt(p_end, p_prev, dist):
        dx = p_end[0] - p_prev[0]; dy = p_end[1] - p_prev[1]
        L = math.hypot(dx, dy)
        if L == 0: return p_end
        return (p_end[0] + dist * dx / L, p_end[1] + dist * dy / L)
    extended = [extend_pt(xy[0], xy[1], TURNAROUND_M)] + xy[1:-1] + [extend_pt(xy[-1], xy[-2], TURNAROUND_M)]
    if len(xy) == 2:
        extended = [extend_pt(xy[0], xy[1], TURNAROUND_M), extend_pt(xy[-1], xy[-2], TURNAROUND_M)]
    line = LineString(extended)
    total_swath = line.buffer(AGL + AGL/2, cap_style='flat', join_style='round')   # = 1.5 * AGL each side
    twice_within = line.buffer(AGL/2, cap_style='flat', join_style='round')         # = 0.5 * AGL each side
    return total_swath, twice_within


def main():
    # Per-plan flight time
    print('=== Flight time per plan (calibrated AMC estimate) ===')
    print(f'{"Plan":<18}{"Minutes":<10}{"Notes"}')
    total_minutes = 0.0
    rows = []
    for fn in PLANS:
        p = os.path.join(PLAN_DIR, fn)
        try:
            r = AMC_minutes(p)
            t = r['amc']
        except Exception as ex:
            t = float('nan')
        rows.append((fn, t))
        total_minutes += t if t == t else 0
        print(f'{fn:<18}{t:<10.2f}')
    print(f'{"":-<28}')
    print(f'{"TOTAL":<18}{total_minutes:<10.2f}  minutes  = {total_minutes/60:.2f} hours')

    # Geometry: compute swaths and coverage areas
    print()
    print('=== Coverage geometry (shapely on per-transect swaths) ===')
    # Use a single projection anchored at the centroid of all polylines for consistency
    all_pts = []
    for fn in PLANS:
        kind, geom, agl, cw, ta = parse_plan_geometry(os.path.join(PLAN_DIR, fn))
        all_pts.extend(geom)
    ref_lat = sum(p[0] for p in all_pts) / len(all_pts)
    ref_lon = sum(p[1] for p in all_pts) / len(all_pts)
    to_xy, _ = make_projection(ref_lat, ref_lon)

    total_swaths = []   # one per tile (full 210 m wide envelope)
    twice_zones  = []   # one per tile (inner 70 m strip)
    for fn in PLANS:
        kind, geom, agl, cw, ta = parse_plan_geometry(os.path.join(PLAN_DIR, fn))
        ts, tw = polyline_to_swath_polygons(geom, to_xy)
        if ts is None: continue
        total_swaths.append(ts)
        twice_zones.append(tw)

    # Per-pair total-swath intersections (= inter-tile turnaround overlap, both swaths overlap fully)
    pair_overlaps = []
    for i in range(0, len(total_swaths), 2):
        if i + 1 >= len(total_swaths): break
        inter = total_swaths[i].intersection(total_swaths[i+1])
        if not inter.is_empty:
            pair_overlaps.append(inter)

    total_covered_polygon = unary_union(total_swaths)
    twice_or_more_polygon = unary_union(twice_zones + pair_overlaps)
    once_only_polygon = total_covered_polygon.difference(twice_or_more_polygon)

    def ac(geom): return geom.area / 4046.86

    total_ac = ac(total_covered_polygon)
    once_ac  = ac(once_only_polygon)
    twice_or_more_ac = ac(twice_or_more_polygon)

    # === Coverage vs the corridor-union target KML ===
    from coverage_check_multi import parse_kml_polygon
    target_outer, target_holes = parse_kml_polygon('C:/Users/rharbach.STAHLY/Downloads/Fergus Hilger-Roy — corridor union.kml')[0]
    # Re-project target to the SAME local frame we've been using
    target_xy_poly = Polygon([to_xy(*p) for p in target_outer],
                             [[to_xy(*p) for p in h] for h in target_holes])
    target_ac = target_xy_poly.area / 4046.86
    covered_in_target = total_covered_polygon.intersection(target_xy_poly)
    covered_in_target_ac = covered_in_target.area / 4046.86
    once_in_target = once_only_polygon.intersection(target_xy_poly).area / 4046.86
    twice_in_target = twice_or_more_polygon.intersection(target_xy_poly).area / 4046.86

    print(f'  Total area covered (union of all 12 tile swaths):  {total_ac:>9.2f} ac')
    print(f'    Covered ONCE only (single-pass) area:            {once_ac:>9.2f} ac')
    print(f'    Covered TWICE-OR-MORE area:                      {twice_or_more_ac:>9.2f} ac')
    print(f'    Sanity check: once + twice+ = {once_ac + twice_or_more_ac:.2f} ac (matches total: '
          f'{abs((once_ac + twice_or_more_ac) - total_ac) < 0.5})')
    sum_of_swaths_ac = sum(ac(s) for s in total_swaths)
    print(f'  Sum of 12 individual swaths (= acres x passes):    {sum_of_swaths_ac:>9.2f} ac')
    print(f'  Total / sum = avg pass count per covered point:    {sum_of_swaths_ac/total_ac:.3f} passes')

    print()
    print(f'=== Coverage vs the corridor-union target KML ===')
    print(f'  Target KML (Fergus Hilger-Roy - corridor union):     {target_ac:>9.2f} ac (denominator)')
    print(f'  Covered area inside target (intersection):           {covered_in_target_ac:>9.2f} ac (numerator)')
    print(f'  Coverage of target: {covered_in_target_ac:.2f} / {target_ac:.2f} = '
          f'{100*covered_in_target_ac/target_ac:.2f}%')
    print(f'    of which ONCE-covered inside target:               {once_in_target:>9.2f} ac '
          f'({100*once_in_target/target_ac:.2f}% of target)')
    print(f'    of which TWICE+-covered inside target:             {twice_in_target:>9.2f} ac '
          f'({100*twice_in_target/target_ac:.2f}% of target)')

    # Point density
    # Per-pass density: PPSM_MIN, PPSM_AVG, PPSM_MAX
    # On once-covered area: density = PPSM_PER_PASS
    # On twice-covered area: density = 2 * PPSM_PER_PASS (approximately; some areas may be 3+)
    once_m2  = once_ac * 4046.86
    twice_m2 = twice_or_more_ac * 4046.86
    print()
    print('=== Point density (ppsm) at 8 m/s + 230 ft AGL ===')
    print(f'  Per-pass ppsm (you reported): min {PPSM_MIN}, avg {PPSM_AVG}, max {PPSM_MAX}')
    print()
    print(f'{"Zone":<20}{"Area (ac)":<12}{"Passes":<10}{"Min ppsm":<12}{"Avg ppsm":<12}{"Max ppsm":<12}')
    print(f'{"Once-covered":<20}{once_ac:<12.2f}{1:<10}{PPSM_MIN:<12.1f}{PPSM_AVG:<12.1f}{PPSM_MAX:<12.1f}')
    print(f'{"Twice+-covered":<20}{twice_or_more_ac:<12.2f}{2:<10}{2*PPSM_MIN:<12.1f}{2*PPSM_AVG:<12.1f}{2*PPSM_MAX:<12.1f}')
    print()
    # Total points across the whole survey
    pts_min = once_m2 * PPSM_MIN + twice_m2 * 2 * PPSM_MIN
    pts_avg = once_m2 * PPSM_AVG + twice_m2 * 2 * PPSM_AVG
    pts_max = once_m2 * PPSM_MAX + twice_m2 * 2 * PPSM_MAX
    print(f'  Total points across whole survey:')
    print(f'    Min  (using 21.0 ppsm/pass):  {pts_min/1e6:>10.1f} million points')
    print(f'    Avg  (using 51.5 ppsm/pass):  {pts_avg/1e6:>10.1f} million points')
    print(f'    Max  (using 85.1 ppsm/pass):  {pts_max/1e6:>10.1f} million points')
    # Equivalent average ppsm (counting all passes as additive)
    print()
    print(f'  Equivalent surveywide avg ppsm (total points / total area):')
    print(f'    Min:  {pts_min / (total_ac * 4046.86):.1f}')
    print(f'    Avg:  {pts_avg / (total_ac * 4046.86):.1f}')
    print(f'    Max:  {pts_max / (total_ac * 4046.86):.1f}')


if __name__ == '__main__':
    main()
