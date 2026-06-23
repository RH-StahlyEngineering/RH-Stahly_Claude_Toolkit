"""Simulate the 9 proposed gap-fill pairs in memory and run VLOS check
against bare-earth DEM. Does not write any .plan files to the Missions folder
unless --commit is passed.

For each proposed launch (computed identically to analyze_gap_fills.py),
this builds the full plan dicts via generate_fergus_pair1.build_plan, writes
them to a TEMP directory, runs los_check.check_plan_vlos against the temp
files, then deletes the temp files. Reports a VLOS table for the 9 pairs.
"""
import os, sys, json, tempfile, shutil, math

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SKILL_DIR, 'scripts'))
from dem_lookup import ensure_dem_for_bbox, terrain_amsl, bake_amsl
from generate_fergus_pair1 import (
    load_centerline, hav, douglas_peucker, build_plan,
    AGL, SPEED, FIG8_DURATION, TURNAROUND_M, TILE_LEN_M, DECIMATE_TOL_M,
)
from generate_fergus_all_pairs import (
    project_onto_centerline, insert_meeting_into_centerline, walk_along,
)
from coverage_check_multi import (
    parse_kml_polygon, parse_plan_geometry, make_projection,
    corridorscan_coverage_polygon,
)
from los_check import check_plan_vlos, warm_dem_bbox_for
from shapely.geometry import Polygon, Point
from shapely.ops import unary_union

KML_CENTERLINE = 'C:/Users/rharbach.STAHLY/Downloads/HighwayCenterline.kml'
KML_TARGET     = 'C:/Users/rharbach.STAHLY/Downloads/Fergus Hilger-Roy — corridor union.kml'
PLAN_DIR       = 'C:/Users/rharbach.STAHLY/Documents/Auterion Mission Control/Missions'
F1_TEMPLATE    = os.path.join(PLAN_DIR, 'Fergus1.plan')
DEM_SAMPLE_M   = 50.0
TARGET_PCT     = 90.0
CORRIDOR_WIDTH = 140.208

def acres(area_m2): return area_m2 / 4046.86

def main():
    target_outer_ll, target_holes_ll = parse_kml_polygon(KML_TARGET)[0]
    ref_lat = sum(p[0] for p in target_outer_ll) / len(target_outer_ll)
    ref_lon = sum(p[1] for p in target_outer_ll) / len(target_outer_ll)
    to_xy, to_ll = make_projection(ref_lat, ref_lon)
    target_xy = Polygon([to_xy(*p) for p in target_outer_ll],
                        [[to_xy(*p) for p in h] for h in target_holes_ll])

    pad = 0.02
    lats = [p[0] for p in target_outer_ll]; lons = [p[1] for p in target_outer_ll]
    ensure_dem_for_bbox(min(lats)-pad, max(lats)+pad, min(lons)-pad, max(lons)+pad, resolution_m=10.0)

    # Build existing coverage from Fergus1..Fergus20
    plans = [os.path.join(PLAN_DIR, f'Fergus{n}.plan') for n in range(1, 21)]
    cov_polys = []
    for pp in plans:
        kind, geom_ll, agl, cw, ta = parse_plan_geometry(pp)
        if kind != 'CorridorScan': continue
        poly = corridorscan_coverage_polygon(geom_ll, agl, cw, ta, to_xy)
        if poly is not None and not poly.is_empty: cov_polys.append(poly)
    coverage = unary_union(cov_polys)

    # Centerline samples + DEM
    centerline_ll = load_centerline(KML_CENTERLINE)
    samples = []
    cum = 0.0
    last = centerline_ll[0]
    samples.append((cum, last[0], last[1], terrain_amsl(last[0], last[1])))
    for i in range(1, len(centerline_ll)):
        step = hav(centerline_ll[i-1], centerline_ll[i])
        if step == 0: continue
        s = 0.0
        while s + DEM_SAMPLE_M < step:
            s += DEM_SAMPLE_M
            frac = s / step
            lat = centerline_ll[i-1][0] + frac * (centerline_ll[i][0] - centerline_ll[i-1][0])
            lon = centerline_ll[i-1][1] + frac * (centerline_ll[i][1] - centerline_ll[i-1][1])
            samples.append((cum + s, lat, lon, terrain_amsl(lat, lon)))
        cum += step
        last = centerline_ll[i]
        samples.append((cum, last[0], last[1], terrain_amsl(last[0], last[1])))
    samples_xy = [to_xy(s[1], s[2]) for s in samples]

    # Reproduce the iterative gap-fill from analyze_gap_fills.py to get the 9 launches.
    # We RE-RUN the iteration but STOP at 9 pairs (skipping the bad-yield Pair 17).
    # See "Surveyor's plan": drop the 5.64 ac iter and keep the others.
    chosen = []
    iteration = 0
    while iteration < 20 and len(chosen) < 9:
        iteration += 1
        uncov = target_xy.difference(coverage)
        if uncov.is_empty: break
        polys = list(uncov.geoms) if uncov.geom_type == 'MultiPolygon' else [uncov]
        polys.sort(key=lambda p: -p.area)
        gap = polys[0]
        idx_in_gap = [i for i, xy in enumerate(samples_xy) if gap.contains(Point(xy))]
        if not idx_in_gap:
            found = False
            for cand in polys:
                idx = [i for i, xy in enumerate(samples_xy) if cand.contains(Point(xy))]
                if idx:
                    gap = cand; idx_in_gap = idx; found = True; break
            if not found: break
        best_i = max(idx_in_gap, key=lambda i: samples[i][3])
        best = samples[best_i]
        launch_ll = (best[1], best[2])
        launch_elev = best[3]

        d_proj, meeting_pt, seg_idx, frac = project_onto_centerline(centerline_ll, launch_ll)
        cl, i_meet = insert_meeting_into_centerline(centerline_ll, seg_idx, frac, meeting_pt)
        east_path, _ = walk_along(cl, i_meet, +1, TILE_LEN_M)
        west_path, _ = walk_along(cl, i_meet, -1, TILE_LEN_M)
        east_poly = douglas_peucker(list(reversed(east_path)), DECIMATE_TOL_M)
        west_poly = douglas_peucker(list(reversed(west_path)), DECIMATE_TOL_M)

        east_cov = corridorscan_coverage_polygon(east_poly, AGL, CORRIDOR_WIDTH, TURNAROUND_M, to_xy)
        west_cov = corridorscan_coverage_polygon(west_poly, AGL, CORRIDOR_WIDTH, TURNAROUND_M, to_xy)
        pair_cov = unary_union([east_cov, west_cov])
        new_coverage = unary_union([coverage, pair_cov])
        added_ac = acres(new_coverage.intersection(target_xy).area) - acres(coverage.intersection(target_xy).area)

        # Surveyor rule: skip iterations that add <10 ac (inefficient flights)
        if added_ac < 10.0:
            # Still update coverage so subsequent iterations don't re-pick this gap,
            # but don't add to the chosen list.
            coverage = new_coverage
            continue

        chosen.append({
            'launch_ll': launch_ll, 'launch_elev': launch_elev,
            'meeting_ll': meeting_pt,
            'east_poly': east_poly, 'west_poly': west_poly,
            'added_ac': added_ac,
        })
        coverage = new_coverage

    print(f'Selected {len(chosen)} proposed pairs (filtered to skip <10 ac yields)')
    final_pct = 100 * acres(coverage.intersection(target_xy).area) / acres(target_xy.area)
    print(f'Final coverage: {final_pct:.2f}%')

    # Build each proposed pair plan in memory, write to temp dir, run LOS check
    template = json.load(open(F1_TEMPLATE))
    tmpdir = tempfile.mkdtemp(prefix='fergus_los_check_')
    try:
        proposed_results = []
        for idx, c in enumerate(chosen):
            pair_num = 10 + idx
            east_idx = 21 + 2*idx
            west_idx = 22 + 2*idx
            launch_ground = terrain_amsl(c['launch_ll'][0], c['launch_ll'][1])
            plan_home = [c['launch_ll'][0], c['launch_ll'][1], launch_ground]
            meet_amsl = bake_amsl(c['meeting_ll'][0], c['meeting_ll'][1], AGL)
            east_plan = build_plan(template, c['east_poly'], plan_home, AGL,
                                   fig8_at_start=True, fig8_at_end=False,
                                   fig8_centroid_alt_amsl=meet_amsl,
                                   fig8_centroid_latlon=c['meeting_ll'])
            west_plan = build_plan(template, c['west_poly'], plan_home, AGL,
                                   fig8_at_start=False, fig8_at_end=True,
                                   fig8_centroid_alt_amsl=meet_amsl,
                                   fig8_centroid_latlon=c['meeting_ll'])
            east_path_temp = os.path.join(tmpdir, f'Fergus{east_idx}.plan')
            west_path_temp = os.path.join(tmpdir, f'Fergus{west_idx}.plan')
            with open(east_path_temp, 'wb') as f:
                f.write(json.dumps(east_plan, separators=(',', ':')).encode('utf-8'))
            with open(west_path_temp, 'wb') as f:
                f.write(json.dumps(west_plan, separators=(',', ':')).encode('utf-8'))
            re_check = check_plan_vlos(east_path_temp)
            rw_check = check_plan_vlos(west_path_temp)
            proposed_results.append({
                'pair': pair_num,
                'east': re_check, 'west': rw_check,
                'launch_ll': c['launch_ll'], 'launch_elev': c['launch_elev'],
                'added_ac': c['added_ac'],
                'east_name': f'Fergus{east_idx}.plan',
                'west_name': f'Fergus{west_idx}.plan',
            })
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    print(f'\nVLOS check for the {len(proposed_results)} proposed pairs:')
    print(f'{"Pair":<5}{"East file":<20}{"VLOS%":<8}{"Below":<7}{"Dist":<7}'
          f'{"West file":<20}{"VLOS%":<8}{"Below":<7}{"Dist":<7}{"Status"}')
    print('-' * 130)
    for r in proposed_results:
        e = r['east']; w = r['west']
        e_status = 'OK' if e['los_pct'] >= 99.99 else ('partial' if e['los_pct'] >= 95 else 'BLOCKED')
        w_status = 'OK' if w['los_pct'] >= 99.99 else ('partial' if w['los_pct'] >= 95 else 'BLOCKED')
        overall = 'OK' if e_status == 'OK' and w_status == 'OK' else f'{e_status}/{w_status}'
        print(f'  {r["pair"]:<3}'
              f'{r["east_name"]:<20}{e["los_pct"]:<8.2f}{e["worst_below_m"]:<7.1f}{e["worst_dist_m"]:<7.0f}'
              f'{r["west_name"]:<20}{w["los_pct"]:<8.2f}{w["worst_below_m"]:<7.1f}{w["worst_dist_m"]:<7.0f}'
              f'{overall}')

    # Summary: how many proposed pairs are 100% LOS, how many have issues
    ok_count = sum(1 for r in proposed_results
                   if r['east']['los_pct'] >= 99.99 and r['west']['los_pct'] >= 99.99)
    print(f'\n{ok_count}/{len(proposed_results)} proposed pairs have 100% VLOS on both tiles.')
    for r in proposed_results:
        if r['east']['los_pct'] < 99.99 or r['west']['los_pct'] < 99.99:
            ll = r['launch_ll']
            print(f'  Pair {r["pair"]} ({r["east_name"]}/{r["west_name"]}) at '
                  f'({ll[0]:.5f}, {ll[1]:.5f}) elev {r["launch_elev"]:.0f} m:')
            for tile, ck in [('east', r['east']), ('west', r['west'])]:
                if ck['los_pct'] < 99.99:
                    print(f'    {tile}: {ck["los_pct"]:.2f}% VLOS, worst block {ck["worst_below_m"]:.1f} m '
                          f'at {ck["worst_dist_m"]:.0f} m from launch')


if __name__ == '__main__':
    main()
