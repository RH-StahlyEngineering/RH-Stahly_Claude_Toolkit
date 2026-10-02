"""Operational summary for the 18 unconstrained 41m highway-centerline plans:
  - 9 launches, polyline=highway, AGL=41m, speed=14m/s, tile=3.6km, line spacing=41m
  - Flight time per plan + total (calibrated AMC estimate)
  - Coverage area inside the target KML (Fergus Hilger-Roy corridor union)
  - Once-covered vs twice-or-more covered split
  - PPSM (per-pass and surveywide)
  - Wire clearance reminder (ignored for this report - per user request)
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
from coverage_check_multi import make_projection, parse_plan_geometry, parse_kml_polygon

PLAN_DIR = 'C:/Users/rharbach.STAHLY/Documents/Auterion Mission Control/Missions'
AGL = 41.0
SPEED = 14.0
TILE_LEN_M = 3600.0
TURNAROUND_M = 60.96
LINE_SPACING_M = AGL
PLANS = [f'Fergus{n}.plan' for n in range(3, 21)]   # 18 plans

# Per-pass point densities at constant 2*AGL*speed product
# At 70/8 they were 21/51.5/85.1; 41/14 gives 2*41*14=1148 vs 2*70*8=1120
# (~2.5% richer per pass at 41/14). Use the same canonical values.
PPSM_MIN = 21.0
PPSM_AVG = 51.5
PPSM_MAX = 85.1


def polyline_to_swath_polygons(polyline_ll, to_xy):
    xy = [to_xy(*p) for p in polyline_ll]
    if len(xy) < 2:
        return None, None
    def extend_pt(p_end, p_prev, dist):
        dx = p_end[0] - p_prev[0]; dy = p_end[1] - p_prev[1]
        L = math.hypot(dx, dy)
        if L == 0: return p_end
        return (p_end[0] + dist * dx / L, p_end[1] + dist * dy / L)
    extended = [extend_pt(xy[0], xy[1], TURNAROUND_M)] + xy[1:-1] + [extend_pt(xy[-1], xy[-2], TURNAROUND_M)]
    if len(xy) == 2:
        extended = [extend_pt(xy[0], xy[1], TURNAROUND_M), extend_pt(xy[-1], xy[-2], TURNAROUND_M)]
    line = LineString(extended)
    total_swath = line.buffer(AGL + AGL/2, cap_style='flat', join_style='round')   # +/- 1.5*AGL = +/- 61.5 m
    twice_within = line.buffer(AGL/2, cap_style='flat', join_style='round')         # inner +/- 20.5 m (where two transects overlap)
    return total_swath, twice_within


def main():
    print('=== Flight time per plan (calibrated AMC estimate) ===')
    print(f'{"Plan":<18}{"Minutes":<10}')
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
    print(f'{"TOTAL":<18}{total_minutes:<10.2f}  minutes = {total_minutes/60:.2f} hours')

    # Build local projection from centroid of all polyline points
    all_pts = []
    for fn in PLANS:
        kind, geom, _, _, _ = parse_plan_geometry(os.path.join(PLAN_DIR, fn))
        all_pts.extend(geom)
    ref_lat = sum(p[0] for p in all_pts) / len(all_pts)
    ref_lon = sum(p[1] for p in all_pts) / len(all_pts)
    to_xy, _ = make_projection(ref_lat, ref_lon)

    total_swaths = []
    twice_zones = []
    for fn in PLANS:
        kind, geom, _, _, _ = parse_plan_geometry(os.path.join(PLAN_DIR, fn))
        ts, tw = polyline_to_swath_polygons(geom, to_xy)
        if ts is None: continue
        total_swaths.append(ts)
        twice_zones.append(tw)

    # Per-pair total-swath overlap = turnaround zone where both tiles of a pair share coverage
    pair_overlaps = []
    for i in range(0, len(total_swaths), 2):
        if i + 1 >= len(total_swaths): break
        inter = total_swaths[i].intersection(total_swaths[i+1])
        if not inter.is_empty:
            pair_overlaps.append(inter)

    # Adjacent-PAIR (different launches) overlap
    inter_pair_overlaps = []
    for i in range(0, len(total_swaths) - 2, 2):
        a = total_swaths[i].union(total_swaths[i+1])
        b = total_swaths[i+2].union(total_swaths[i+3]) if (i+3 < len(total_swaths)) else None
        if b is None: continue
        inter = a.intersection(b)
        if not inter.is_empty:
            inter_pair_overlaps.append(inter)

    total_covered_polygon = unary_union(total_swaths)
    twice_or_more_polygon = unary_union(twice_zones + pair_overlaps + inter_pair_overlaps)
    once_only_polygon = total_covered_polygon.difference(twice_or_more_polygon)

    def ac(g): return g.area / 4046.86

    total_ac = ac(total_covered_polygon)
    once_ac = ac(once_only_polygon)
    twice_or_more_ac = ac(twice_or_more_polygon)

    # Target
    from coverage_check_multi import parse_kml_polygon
    target_outer, target_holes = parse_kml_polygon('C:/Users/rharbach.STAHLY/Downloads/Fergus Hilger-Roy — corridor union.kml')[0]
    target_xy_poly = Polygon([to_xy(*p) for p in target_outer],
                             [[to_xy(*p) for p in h] for h in target_holes])
    target_ac = target_xy_poly.area / 4046.86
    covered_in_target = total_covered_polygon.intersection(target_xy_poly)
    covered_in_target_ac = ac(covered_in_target)
    once_in_target_ac = ac(once_only_polygon.intersection(target_xy_poly))
    twice_in_target_ac = ac(twice_or_more_polygon.intersection(target_xy_poly))

    print()
    print('=== Coverage geometry ===')
    print(f'  Total area covered (union of {len(total_swaths)} tile swaths): {total_ac:>9.2f} ac')
    print(f'    Covered ONCE only (single-pass):                   {once_ac:>9.2f} ac')
    print(f'    Covered TWICE-OR-MORE:                             {twice_or_more_ac:>9.2f} ac')
    sum_of_swaths_ac = sum(ac(s) for s in total_swaths)
    print(f'  Sum of individual swaths (= acres x passes):         {sum_of_swaths_ac:>9.2f} ac')
    print(f'  Total / sum = avg pass count per covered point:       {sum_of_swaths_ac/total_ac:.3f} passes')

    print()
    print('=== Coverage vs target KML (Fergus Hilger-Roy corridor union) ===')
    print(f'  Target KML area:                                 {target_ac:>9.2f} ac (denominator)')
    print(f'  Covered area inside target:                      {covered_in_target_ac:>9.2f} ac (numerator)')
    print(f'  Coverage: {covered_in_target_ac:.2f} / {target_ac:.2f} = '
          f'{100*covered_in_target_ac/target_ac:.2f}%')
    print(f'    of which ONCE-covered inside target:           {once_in_target_ac:>9.2f} ac '
          f'({100*once_in_target_ac/target_ac:.2f}% of target)')
    print(f'    of which TWICE+-covered inside target:         {twice_in_target_ac:>9.2f} ac '
          f'({100*twice_in_target_ac/target_ac:.2f}% of target)')

    # PPSM
    once_m2 = once_ac * 4046.86
    twice_m2 = twice_or_more_ac * 4046.86
    print()
    print(f'=== Point density (ppsm) at {SPEED} m/s + {AGL} m AGL ===')
    print(f'  PPSM per pass (same product 2*AGL*speed as 70/8 reference): min {PPSM_MIN}, avg {PPSM_AVG}, max {PPSM_MAX}')
    print()
    print(f'{"Zone":<20}{"Area (ac)":<12}{"Passes":<10}{"Min ppsm":<12}{"Avg ppsm":<12}{"Max ppsm":<12}')
    print(f'{"Once-covered":<20}{once_ac:<12.2f}{1:<10}{PPSM_MIN:<12.1f}{PPSM_AVG:<12.1f}{PPSM_MAX:<12.1f}')
    print(f'{"Twice+-covered":<20}{twice_or_more_ac:<12.2f}{2:<10}{2*PPSM_MIN:<12.1f}{2*PPSM_AVG:<12.1f}{2*PPSM_MAX:<12.1f}')
    print()
    pts_min = once_m2 * PPSM_MIN + twice_m2 * 2 * PPSM_MIN
    pts_avg = once_m2 * PPSM_AVG + twice_m2 * 2 * PPSM_AVG
    pts_max = once_m2 * PPSM_MAX + twice_m2 * 2 * PPSM_MAX
    print(f'  Total points across whole survey:')
    print(f'    Min  (using 21.0 ppsm/pass): {pts_min/1e6:>10.1f} million')
    print(f'    Avg  (using 51.5 ppsm/pass): {pts_avg/1e6:>10.1f} million')
    print(f'    Max  (using 85.1 ppsm/pass): {pts_max/1e6:>10.1f} million')
    print()
    print(f'  Equivalent surveywide avg ppsm (total points / total area):')
    print(f'    Min:  {pts_min / (total_ac * 4046.86):.1f}')
    print(f'    Avg:  {pts_avg / (total_ac * 4046.86):.1f}')
    print(f'    Max:  {pts_max / (total_ac * 4046.86):.1f}')

    # Clearance reminder
    print()
    print('=== Clearance reminder (NOT enforced in this run) ===')
    print(f'  At 41 m AGL, 15 deg off-nadir floor = {41 * math.tan(math.radians(15)):.2f} m lateral')
    print(f'  Inner transects at +/-20.5 m from highway -> wire violates when |h| in [9.5, 31.5] m')
    print(f'  ~25% of corridor has wire in violation band (median wire-highway offset = 68.3 m)')
    print(f'  Per-plan empirical violation rates 14-47% on sustained transects')


if __name__ == '__main__':
    main()
