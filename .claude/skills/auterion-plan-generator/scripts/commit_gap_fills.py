"""Generate the 9 surveyor-approved gap-fill pairs and write them to the
Missions folder. Hardcodes the launches from the prior analysis so reruns are
deterministic, then walks the centerline, builds each plan via the canonical
build_plan path (CorridorScan + cal + cross-line + inner Items + frame=0
DEM-baked AMSL), writes minified LF-only files, and runs VLOS check.
"""
import os, sys, json

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SKILL_DIR, 'scripts'))
from dem_lookup import ensure_dem_for_bbox, terrain_amsl, bake_amsl
from generate_fergus_pair1 import (
    load_centerline, douglas_peucker, build_plan, minified_write,
    AGL, SPEED, FIG8_DURATION, TURNAROUND_M, TILE_LEN_M, DECIMATE_TOL_M,
)
from generate_fergus_all_pairs import (
    project_onto_centerline, insert_meeting_into_centerline, walk_along,
)
from los_check import check_plan_vlos, warm_dem_bbox_for

KML_CENTERLINE = 'C:/Users/rharbach.STAHLY/Downloads/HighwayCenterline.kml'
PLAN_DIR       = 'C:/Users/rharbach.STAHLY/Documents/Auterion Mission Control/Missions'
F1_TEMPLATE    = os.path.join(PLAN_DIR, 'Fergus1.plan')

# 9 surveyor-approved launches (from analyze_gap_fills.py iter 1..10 minus
# the inefficient iter 8 = original "Pair 17" at 5.64 ac):
PROPOSED_PAIRS = [
    # (pair_num, launch_lat, launch_lon, east_idx, west_idx, label, expected_ac)
    (10, 47.336308, -109.041954, 21, 22, 'L2-L3 east lobe',      57.24),
    (11, 47.336176, -109.016625, 23, 24, 'L2-L3 middle',          59.25),
    (12, 47.287150, -109.236312, 25, 26, 'L5-L6 east lobe',       61.63),
    (13, 47.335934, -108.991556, 27, 28, 'L2-L3 west lobe',       58.30),
    (14, 47.296402, -109.215912, 29, 30, 'L5-L6 middle',          56.56),
    (15, 47.328395, -109.105251, 31, 32, 'L3-L4',                 38.98),
    (16, 47.336963, -108.907098, 33, 34, 'L1-L2',                 34.43),
    (17, 47.335859, -108.962808, 35, 36, 'L2-L3 east shoulder',   26.65),
    (18, 47.303523, -109.193004, 37, 38, 'L5-L6 west lobe',       24.47),
]

def main():
    centerline = load_centerline(KML_CENTERLINE)

    # Warm DEM cache for the full corridor bbox
    lats = [p[1] for p in PROPOSED_PAIRS]; lons = [p[2] for p in PROPOSED_PAIRS]
    pad = 0.02
    ensure_dem_for_bbox(min(lats)-pad, max(lats)+pad, min(lons)-pad, max(lons)+pad, resolution_m=10.0)

    template = json.load(open(F1_TEMPLATE))

    written = []
    for pair_num, lat_L, lon_L, e_idx, w_idx, label, expected_ac in PROPOSED_PAIRS:
        # Snap launch onto centerline (segment-projection), then walk east + west
        d_proj, meeting_pt, seg_idx, frac = project_onto_centerline(centerline, (lat_L, lon_L))
        cl, i_meet = insert_meeting_into_centerline(centerline, seg_idx, frac, meeting_pt)
        east_path, _ = walk_along(cl, i_meet, +1, TILE_LEN_M)
        west_path, _ = walk_along(cl, i_meet, -1, TILE_LEN_M)
        east_poly = douglas_peucker(list(reversed(east_path)), DECIMATE_TOL_M)
        west_poly = douglas_peucker(list(reversed(west_path)), DECIMATE_TOL_M)

        # HOME = launch ground AMSL
        launch_ground = terrain_amsl(lat_L, lon_L)
        plan_home = [lat_L, lon_L, launch_ground]
        meet_amsl = bake_amsl(meeting_pt[0], meeting_pt[1], AGL)

        # East tile = START cal (first flight after power-up)
        e_plan = build_plan(template, east_poly, plan_home, AGL,
                            fig8_at_start=True, fig8_at_end=False,
                            fig8_centroid_alt_amsl=meet_amsl,
                            fig8_centroid_latlon=meeting_pt)
        # West tile = END cal (last flight before power-down)
        w_plan = build_plan(template, west_poly, plan_home, AGL,
                            fig8_at_start=False, fig8_at_end=True,
                            fig8_centroid_alt_amsl=meet_amsl,
                            fig8_centroid_latlon=meeting_pt)

        e_path = os.path.join(PLAN_DIR, f'Fergus{e_idx}.plan')
        w_path = os.path.join(PLAN_DIR, f'Fergus{w_idx}.plan')
        minified_write(e_path, e_plan)
        minified_write(w_path, w_plan)
        written.append((pair_num, e_path, w_path, label, expected_ac, lat_L, lon_L, meeting_pt, d_proj))
        print(f'Pair {pair_num} ({label}): Fergus{e_idx}.plan + Fergus{w_idx}.plan -> meeting ({meeting_pt[0]:.6f}, {meeting_pt[1]:.6f}) projection {d_proj:.0f} m')

    # VLOS verification on every written file
    print(f'\n=== VLOS verification ===')
    print(f'{"Plan":<22}{"Pts":<6}{"VLOS%":<8}{"Status"}')
    print('-' * 70)
    for pair_num, ep, wp, *_ in written:
        for path in [ep, wp]:
            r = check_plan_vlos(path)
            status = 'OK' if r['los_pct'] >= 99.99 else f"BLOCKED at {r['worst_dist_m']:.0f}m ({r['worst_below_m']:.1f}m below)"
            print(f'{os.path.basename(path):<22}{r["path_pts"]:<6}{r["los_pct"]:<8.2f}{status}')

if __name__ == '__main__':
    main()
