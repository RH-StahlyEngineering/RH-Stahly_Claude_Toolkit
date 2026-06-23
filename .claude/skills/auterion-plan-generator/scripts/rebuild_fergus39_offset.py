"""Rebuild Fergus39 as a south-offset standalone CorridorScan to actually fill
Gap 25 (the part of the corridor union sitting SOUTH of the centerline where
Pair 6's centerline-aligned swath doesn't reach).

Geometry choice — offset south by ~209 m so the new tile's NORTH edge butts
against Pair 6's SOUTH edge. That puts Fergus39's 210 m swath in the maximum
contiguous slice of Gap 25 with zero wasted overlap on Pair 6.

Structure — single isolated flight (cold start + cold end) per the skill
canonical CorridorScan variant: cmd 530 + 11x fig-8 (START) + CorridorScan
+ 2x cross-line + 11x fig-8 (END) = 26 outer items. HOME at the relocated
Pair 6 spot (operator already there).
"""
import os, sys, json, math

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SKILL_DIR, 'scripts'))
from dem_lookup import terrain_amsl, bake_amsl
from generate_fergus_pair1 import (
    load_centerline, hav, douglas_peucker, build_plan, minified_write,
    perp_offset_path,
    AGL, SPEED, FIG8_DURATION, TURNAROUND_M, TILE_LEN_M, DECIMATE_TOL_M,
    LINE_SPACING_M, HALF_LS_M,
)
from generate_fergus_all_pairs import (
    project_onto_centerline, insert_meeting_into_centerline, walk_along,
)
from los_check import check_plan_vlos
from coverage_check_multi import (
    parse_kml_polygon, parse_plan_geometry, make_projection,
    corridorscan_coverage_polygon,
)
from shapely.geometry import Polygon
from shapely.ops import unary_union

KML_CENTERLINE = 'C:/Users/rharbach.STAHLY/Downloads/HighwayCenterline.kml'
KML_TARGET     = 'C:/Users/rharbach.STAHLY/Downloads/Fergus Hilger-Roy — corridor union.kml'
KML_GAPS       = 'C:/Users/rharbach.STAHLY/Downloads/Fergus_uncovered_gaps.kml'
PLAN_DIR       = 'C:/Users/rharbach.STAHLY/Documents/Auterion Mission Control/Missions'
F1_TEMPLATE    = os.path.join(PLAN_DIR, 'Fergus1.plan')

GAP25_CENTROID = (47.274234, -109.251122)
GAP25_HOME     = (47.276110, -109.249341)   # relocated Pair 6 launch

# South offset: place Fergus39 north edge against Pair 6 south edge with no overlap.
# Pair 6 south edge sits at centerline - (CorridorWidth/2 + AGL/2) = centerline - 105.16 m.
# Fergus39 north edge = polyline + 105.16 m. Setting them equal gives polyline = centerline - 210.32 m.
SOUTH_OFFSET_M = 209.0  # ~210; tuned to land just below Pair 6's swath


def main():
    centerline = load_centerline(KML_CENTERLINE)

    # Project Gap 25 centroid onto centerline -> the "anchor" lat/lon
    d_proj, meeting_pt, seg_idx, frac = project_onto_centerline(centerline, GAP25_CENTROID)
    cl, i_anchor = insert_meeting_into_centerline(centerline, seg_idx, frac, meeting_pt)
    print(f'Centerline anchor (Gap 25 centroid projection): ({meeting_pt[0]:.6f}, {meeting_pt[1]:.6f})')

    # Walk 0.9 km east + 0.9 km west of the anchor along the centerline
    east_path, _ = walk_along(cl, i_anchor, +1, TILE_LEN_M / 2)
    west_path, _ = walk_along(cl, i_anchor, -1, TILE_LEN_M / 2)
    # Combine into [west_far, ..., anchor, ..., east_far] going west-to-east
    centerline_polyline = list(reversed(west_path)) + east_path[1:]
    print(f'Centerline polyline along KML: {len(centerline_polyline)} pts, '
          f'{sum(hav(centerline_polyline[i], centerline_polyline[i+1]) for i in range(len(centerline_polyline)-1)):.0f} m')

    # Offset perpendicular SOUTH (negative offset = clockwise from forward; forward is east → CW = south)
    # perp_offset_path with positive offset = 90 deg CCW from forward = north; negative = south.
    shifted = perp_offset_path(centerline_polyline, -SOUTH_OFFSET_M)
    print(f'Shifted {SOUTH_OFFSET_M:.0f} m south: {len(shifted)} pts')

    # Pick polyline ordering: end closest to HOME = LAST (entry/exit per EntryPoint=2)
    d_home_east = hav(GAP25_HOME, shifted[-1])
    d_home_west = hav(GAP25_HOME, shifted[0])
    if d_home_east <= d_home_west:
        polyline = shifted  # west_end first, east_end last
        entry_end = shifted[-1]
        print(f'  HOME closer to east end ({d_home_east:.0f} m vs {d_home_west:.0f} m) -> entry at east')
    else:
        polyline = list(reversed(shifted))
        entry_end = polyline[-1]
        print(f'  HOME closer to west end ({d_home_west:.0f} m vs {d_home_east:.0f} m) -> entry at west')

    polyline_dp = douglas_peucker(polyline, DECIMATE_TOL_M)
    print(f'  Polyline after Douglas-Peucker: {len(polyline_dp)} pts')
    poly_len = sum(hav(polyline_dp[i], polyline_dp[i+1]) for i in range(len(polyline_dp)-1))
    print(f'  Polyline length: {poly_len:.0f} m')

    # Verify south offset is real
    centerline_pts = [(p[0], p[1]) for p in centerline_polyline]
    poly_lats = [p[0] for p in polyline_dp]
    cl_lats = [p[0] for p in centerline_pts]
    print(f'  Centerline polyline lat range: [{min(cl_lats):.5f}, {max(cl_lats):.5f}]')
    print(f'  Shifted polyline lat range:    [{min(poly_lats):.5f}, {max(poly_lats):.5f}]')

    # Build the plan
    home_ground = terrain_amsl(*GAP25_HOME)
    plan_home = [GAP25_HOME[0], GAP25_HOME[1], home_ground]
    entry_amsl = bake_amsl(entry_end[0], entry_end[1], AGL)

    template = json.load(open(F1_TEMPLATE))
    plan = build_plan(template, polyline_dp, plan_home, AGL,
                      fig8_at_start=True, fig8_at_end=True,
                      fig8_centroid_alt_amsl=entry_amsl,
                      fig8_centroid_latlon=entry_end)
    out_path = os.path.join(PLAN_DIR, 'Fergus39.plan')
    minified_write(out_path, plan)
    print(f'\nWrote {out_path}')

    # Structural check
    items = plan['mission']['items']
    cs_idx = next(i for i, it in enumerate(items) if it.get('complexItemType') == 'CorridorScan')
    fig8_before = sum(1 for it in items[:cs_idx] if it.get('command') == 16 and it.get('frame') == 0)
    fig8_after  = sum(1 for it in items[cs_idx+3:] if it.get('command') == 16 and it.get('frame') == 0)
    cross = sum(1 for it in items[cs_idx+1:cs_idx+3] if it.get('command') == 16 and it.get('frame') == 0)
    print(f'Outer items: {len(items)} (expected 26)  '
          f'cmd530=1 fig8_start={fig8_before} CorridorScan=1 cross-line={cross} fig8_end={fig8_after}')

    # VLOS check
    print(f'\nVLOS verification:')
    r = check_plan_vlos(out_path)
    status = 'OK' if r['los_pct'] >= 99.99 else f"partial: {r['worst_below_m']:.1f}m at {r['worst_dist_m']:.0f}m"
    print(f'  Fergus39.plan  {r["path_pts"]} pts  VLOS {r["los_pct"]:.2f}%  {status}')

    # Coverage gain
    print(f'\nCoverage gain analysis:')
    target_outer, target_holes = parse_kml_polygon(KML_TARGET)[0]
    ref_lat = sum(p[0] for p in target_outer) / len(target_outer)
    ref_lon = sum(p[1] for p in target_outer) / len(target_outer)
    to_xy, _ = make_projection(ref_lat, ref_lon)
    target_xy = Polygon([to_xy(*p) for p in target_outer],
                        [[to_xy(*p) for p in h] for h in target_holes])

    def cov(plans):
        polys = []
        for n in plans:
            pp = os.path.join(PLAN_DIR, f'Fergus{n}.plan')
            kind, geom, agl, cw, ta = parse_plan_geometry(pp)
            if kind != 'CorridorScan': continue
            polys.append(corridorscan_coverage_polygon(geom, agl, cw, ta, to_xy))
        return unary_union(polys)

    base_cov = cov(range(1, 39))
    new_cov  = cov(list(range(1, 39)) + [39])
    def ac(g): return g.intersection(target_xy).area / 4046.86
    base_ac = ac(base_cov); new_ac = ac(new_cov); tgt_ac = target_xy.area / 4046.86
    print(f'  Target:                              {tgt_ac:.2f} ac')
    print(f'  Coverage Fergus1..38:                {base_ac:.2f} ac = {100*base_ac/tgt_ac:.2f}%')
    print(f'  Coverage Fergus1..38 + Fergus39:     {new_ac:.2f} ac = {100*new_ac/tgt_ac:.2f}%')
    print(f'  Fergus39 unique gain to target:      {new_ac-base_ac:.2f} ac = {100*(new_ac-base_ac)/tgt_ac:.2f}%')

    # How much of Gap 25 did the south-offset tile fill?
    import re
    with open(KML_GAPS, 'r', encoding='utf-8') as f:
        gaps_txt = f.read()
    m = re.search(r'<name>Gap 25[^<]*</name>[\s\S]*?<coordinates>\s*([^<]+)\s*</coordinates>', gaps_txt)
    if m:
        pts = [tuple(map(float, t.split(',')[:2])) for t in m.group(1).split()]
        gap25 = Polygon([to_xy(p[1], p[0]) for p in pts])
        f39_only = corridorscan_coverage_polygon(
            [tuple(p) for p in plan['mission']['items'][cs_idx]['polyline']],
            AGL, 140.208, TURNAROUND_M, to_xy)
        gap_ac = gap25.area / 4046.86
        filled = f39_only.intersection(gap25).area / 4046.86
        print(f'  Gap 25 total:                        {gap_ac:.2f} ac')
        print(f'  Fergus39 fills of Gap 25:            {filled:.2f} ac = {100*filled/gap_ac:.1f}%')


if __name__ == '__main__':
    main()
