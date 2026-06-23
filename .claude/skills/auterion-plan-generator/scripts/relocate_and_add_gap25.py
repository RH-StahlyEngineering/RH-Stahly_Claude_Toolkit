"""Apply the three approved HOME relocations (Pair 6, 7, 8) and generate
Fergus39 as a standalone single-isolated flight at Gap 25.

For each relocation: read the affected plan, replace plannedHomePosition with
the scouted alternative + DEM-baked ground AMSL, write minified LF-only.
Polylines / fig-8 centroids / cross-line geometry remain unchanged (fig-8 is
anchored at the meeting point, not the HOME).

For Fergus39 (standalone): polyline 1.8 km along centerline through Gap 25
centroid projection, ordered so the polyline END (entry/exit per EntryPoint=2)
is closest to HOME for minimum transit. Built via the canonical build_plan
with fig8_at_start=True and fig8_at_end=True (26 outer items).
"""
import os, sys, json

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SKILL_DIR, 'scripts'))
from dem_lookup import ensure_dem_for_bbox, terrain_amsl, bake_amsl
from generate_fergus_pair1 import (
    load_centerline, hav, douglas_peucker, build_plan, minified_write,
    AGL, SPEED, FIG8_DURATION, TURNAROUND_M, TILE_LEN_M, DECIMATE_TOL_M,
)
from generate_fergus_all_pairs import (
    project_onto_centerline, insert_meeting_into_centerline, walk_along,
)
from los_check import check_plan_vlos

KML_CENTERLINE = 'C:/Users/rharbach.STAHLY/Downloads/HighwayCenterline.kml'
PLAN_DIR       = 'C:/Users/rharbach.STAHLY/Documents/Auterion Mission Control/Missions'
F1_TEMPLATE    = os.path.join(PLAN_DIR, 'Fergus1.plan')

# Approved HOME relocations: (pair_label, files_pair, new_lat, new_lon)
RELOCATIONS = [
    ('Pair 6', ('Fergus13.plan', 'Fergus14.plan'), 47.276110, -109.249341),
    ('Pair 7', ('Fergus15.plan', 'Fergus16.plan'), 47.265180, -109.290948),
    ('Pair 8', ('Fergus17.plan', 'Fergus18.plan'), 47.259770, -109.313159),
]

# Gap 25 centroid (from Fergus_uncovered_gaps.kml)
GAP25_CENTROID = (47.274234, -109.251122)
GAP25_NAME     = 'Fergus39.plan'
GAP25_HOME     = (47.276110, -109.249341)  # Reuse Pair 6's new launch (same area, VLOS-clean)


def relocate_one(plan_path, new_lat, new_lon):
    plan = json.load(open(plan_path))
    ground = terrain_amsl(new_lat, new_lon)
    old = list(plan['mission']['plannedHomePosition'])
    plan['mission']['plannedHomePosition'] = [new_lat, new_lon, ground]
    minified_write(plan_path, plan)
    return old, [new_lat, new_lon, ground]


def main():
    # Don't call ensure_dem_for_bbox — the existing cached rasters (dem_1caacfa268a6,
    # dem_ee0aa3a8a9d0) cover the full corridor and would be masked by any
    # smaller TIFF this script triggers. Rely on _try_load_local_dem's mtime-newest pick.
    # (See known-pitfalls.md #15 for the underlying gotcha.)

    # Step 1: relocate HOMEs
    print('=== HOME relocations ===')
    for label, (ef, wf), new_lat, new_lon in RELOCATIONS:
        e_path = os.path.join(PLAN_DIR, ef); w_path = os.path.join(PLAN_DIR, wf)
        old_e, new_e = relocate_one(e_path, new_lat, new_lon)
        old_w, new_w = relocate_one(w_path, new_lat, new_lon)
        print(f'{label}: {ef} + {wf}')
        print(f'  OLD HOME: ({old_e[0]:.6f}, {old_e[1]:.6f}, {old_e[2]:.1f} m)')
        print(f'  NEW HOME: ({new_e[0]:.6f}, {new_e[1]:.6f}, {new_e[2]:.1f} m)')

    # Step 2: Build Fergus39 (standalone, Gap 25)
    print(f'\n=== Fergus39 (standalone) for Gap 25 ===')
    centerline = load_centerline(KML_CENTERLINE)
    # Project Gap 25 centroid onto centerline
    d_proj, meeting_pt, seg_idx, frac = project_onto_centerline(centerline, GAP25_CENTROID)
    cl, i_meet = insert_meeting_into_centerline(centerline, seg_idx, frac, meeting_pt)
    print(f'  Gap 25 centroid:      {GAP25_CENTROID}')
    print(f'  Centerline projection: ({meeting_pt[0]:.6f}, {meeting_pt[1]:.6f})  '
          f'd_proj={d_proj:.0f} m')

    # Build the full 1.8 km tile (0.9 km each side of the centerline projection)
    # — but for a single isolated flight we want ONE polyline. Pick orientation so
    # the polyline END (entry/exit) is closest to HOME for minimum transit.
    east_path, _ = walk_along(cl, i_meet, +1, TILE_LEN_M / 2)
    west_path, _ = walk_along(cl, i_meet, -1, TILE_LEN_M / 2)

    # east_path[0] = meeting, east_path[-1] = 900 m east of meeting
    # west_path[0] = meeting, west_path[-1] = 900 m west of meeting
    east_end = east_path[-1]; west_end = west_path[-1]
    d_home_east = hav(GAP25_HOME, east_end)
    d_home_west = hav(GAP25_HOME, west_end)

    if d_home_east <= d_home_west:
        # Polyline runs west_end -> meeting -> east_end (east_end is closer to HOME = entry)
        full = list(reversed(west_path[1:])) + east_path
        # Reverse so east_end becomes LAST
        polyline = full
        entry_end = east_end
        print(f'  HOME closer to east end ({d_home_east:.0f} m vs {d_home_west:.0f} m to west) '
              f'-> entry/exit at east end')
    else:
        full = list(reversed(east_path[1:])) + west_path
        polyline = full
        entry_end = west_end
        print(f'  HOME closer to west end ({d_home_west:.0f} m vs {d_home_east:.0f} m to east) '
              f'-> entry/exit at west end')

    polyline_dp = douglas_peucker(polyline, DECIMATE_TOL_M)
    print(f'  Polyline: {len(polyline_dp)} pts (decimated from {len(polyline)})')
    poly_len_m = sum(hav(polyline_dp[i], polyline_dp[i+1]) for i in range(len(polyline_dp)-1))
    print(f'  Polyline length: {poly_len_m:.0f} m')

    # HOME for Fergus39 (= relocated Pair 6 spot)
    home_ground = terrain_amsl(*GAP25_HOME)
    plan_home = [GAP25_HOME[0], GAP25_HOME[1], home_ground]
    # Fig-8 centered at the entry/exit point of the survey
    entry_amsl = bake_amsl(entry_end[0], entry_end[1], AGL)

    template = json.load(open(F1_TEMPLATE))
    # Single isolated = BOTH cals
    plan = build_plan(template, polyline_dp, plan_home, AGL,
                      fig8_at_start=True, fig8_at_end=True,
                      fig8_centroid_alt_amsl=entry_amsl,
                      fig8_centroid_latlon=entry_end)
    out_path = os.path.join(PLAN_DIR, GAP25_NAME)
    minified_write(out_path, plan)
    print(f'  Wrote {out_path}')

    # Structural sanity
    plan_check = json.load(open(out_path))
    items = plan_check['mission']['items']
    cs_idx = next(i for i, it in enumerate(items) if it.get('complexItemType') == 'CorridorScan')
    fig8_before = sum(1 for it in items[:cs_idx] if it.get('command') == 16 and it.get('frame') == 0)
    fig8_after  = sum(1 for it in items[cs_idx+3:] if it.get('command') == 16 and it.get('frame') == 0)
    cross_after = sum(1 for it in items[cs_idx+1:cs_idx+3] if it.get('command') == 16 and it.get('frame') == 0)
    print(f'  Outer items: {len(items)} (expected 26)  cmd530=1 fig8_start={fig8_before} '
          f'CorridorScan=1 cross-line={cross_after} fig8_end={fig8_after}')

    # Step 3: VLOS verification on all 7 affected/new plans
    print(f'\n=== VLOS verification ===')
    print(f'{"Plan":<22}{"Pts":<6}{"VLOS%":<8}{"Status"}')
    for plan_name in ['Fergus13.plan', 'Fergus14.plan', 'Fergus15.plan', 'Fergus16.plan',
                       'Fergus17.plan', 'Fergus18.plan', 'Fergus39.plan']:
        path = os.path.join(PLAN_DIR, plan_name)
        r = check_plan_vlos(path)
        status = 'OK' if r['los_pct'] >= 99.99 else f"partial: {r['worst_below_m']:.1f}m at {r['worst_dist_m']:.0f}m"
        print(f'{plan_name:<22}{r["path_pts"]:<6}{r["los_pct"]:<8.2f}{status}')


if __name__ == '__main__':
    main()
