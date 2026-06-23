"""Scout for alternative launch positions that give full VLOS on a problem pair.

For each of the 4 launches where Fergus13/15/16/17/18/19 lost VLOS, sample a
grid of candidate positions within RADIUS_M of the original. For each candidate,
check VLOS against the COMBINED east + west flight paths (since both flights
share the same plannedHomePosition / operator stand). Pick the closest candidate
that gives 100% VLOS on both tiles.

Also report:
  - candidate elevation (DEM ground)
  - distance from original launch (operator drive)
  - distance from the centerline (proxy for road accessibility)

Pure read-only — does not modify any plan files. Output is recommendations the
user can apply by editing plannedHomePosition in the affected plans.
"""
import os, sys, json, math, re

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SKILL_DIR, 'scripts'))
from dem_lookup import terrain_amsl
from los_check import (
    extract_flight_path, interpolate_path, los_line_clear,
    OPERATOR_EYE_M, DEFAULT_PATH_SAMPLE_M, DEFAULT_LOS_SAMPLES, hav,
)
from generate_fergus_pair1 import load_centerline

PLAN_DIR       = 'C:/Users/rharbach.STAHLY/Documents/Auterion Mission Control/Missions'
KML_CENTERLINE = 'C:/Users/rharbach.STAHLY/Downloads/HighwayCenterline.kml'

# Search parameters
RADIUS_M        = 2000.0  # how far an operator might drive from the original launch
GRID_M          = 200.0   # candidate spacing (coarser; we'll refine with high-precision verify)
PATH_SAMPLE_M   = 25.0    # match los_check.py default sensitivity
LINE_SAMPLES    = 100     # match los_check.py default sensitivity
ROAD_ACCESS_M   = 500.0   # candidates within this distance of the centerline are "road-accessible"

# Problem pairs: (label, pair_num, east_file, west_file, original_launch_lat, original_launch_lon)
PROBLEMS = [
    ('Pair 6 (L6)', 6, 'Fergus13.plan', 'Fergus14.plan', 47.27476, -109.25332),
    ('Pair 7 (L7)', 7, 'Fergus15.plan', 'Fergus16.plan', 47.26383, -109.28697),
    ('Pair 8 (L8)', 8, 'Fergus17.plan', 'Fergus18.plan', 47.25977, -109.31117),
    ('Pair 9 (L9)', 9, 'Fergus19.plan', 'Fergus20.plan', 47.26004, -109.34256),
]


def nearest_centerline_dist(pt, centerline):
    return min(hav(pt, c) for c in centerline)


def candidate_grid(orig_ll, radius_m, grid_m):
    """Yield (lat, lon, dist_from_orig_m) for each grid candidate within radius."""
    m_lat = 111132.0
    m_lon = 111132.0 * math.cos(math.radians(orig_ll[0]))
    n = int(math.ceil(radius_m / grid_m))
    for i in range(-n, n+1):
        for j in range(-n, n+1):
            dx = i * grid_m  # east
            dy = j * grid_m  # north
            d = math.hypot(dx, dy)
            if d > radius_m: continue
            yield (orig_ll[0] + dy / m_lat, orig_ll[1] + dx / m_lon, d)


def candidate_vlos_pct(cand_ll, combined_path):
    """Return (vlos_pct, blocked_count, worst_below_m) for one candidate."""
    op_ground = terrain_amsl(*cand_ll)
    op_amsl = op_ground + OPERATOR_EYE_M
    blocked = 0
    worst_below = 0.0
    for p in combined_path:
        clear, below, _ = los_line_clear(cand_ll, op_amsl, (p[0], p[1]), p[2], samples=LINE_SAMPLES)
        if not clear:
            blocked += 1
            if below > worst_below: worst_below = below
    pct = 100.0 * (len(combined_path) - blocked) / len(combined_path)
    return pct, blocked, worst_below, op_ground


def main():
    centerline = load_centerline(KML_CENTERLINE)

    results = []
    for label, pair_num, e_file, w_file, lat_o, lon_o in PROBLEMS:
        ep = os.path.join(PLAN_DIR, e_file)
        wp = os.path.join(PLAN_DIR, w_file)
        east_plan = json.load(open(ep))
        west_plan = json.load(open(wp))
        path = extract_flight_path(east_plan) + extract_flight_path(west_plan)
        path_interp = interpolate_path(path, PATH_SAMPLE_M)
        orig_ground = terrain_amsl(lat_o, lon_o)
        orig_pct, *_ = candidate_vlos_pct((lat_o, lon_o), path_interp)
        print(f'\n=== {label}: {e_file} + {w_file} ===')
        print(f'  Original launch: ({lat_o:.6f}, {lon_o:.6f}), ground elev {orig_ground:.0f} m, current VLOS {orig_pct:.1f}%')

        # Scan grid
        full_los = []
        all_cands = []
        for clat, clon, dist in candidate_grid((lat_o, lon_o), RADIUS_M, GRID_M):
            pct, blocked, below, ground = candidate_vlos_pct((clat, clon), path_interp)
            cl_dist = nearest_centerline_dist((clat, clon), centerline)
            cand = {
                'lat': clat, 'lon': clon, 'dist_from_orig': dist,
                'ground_amsl': ground, 'vlos_pct': pct,
                'worst_below': below, 'centerline_dist': cl_dist,
            }
            all_cands.append(cand)
            if pct >= 99.99: full_los.append(cand)

        if full_los:
            # Pick the closest-to-original full-VLOS candidate that's also reasonably close to road
            full_los.sort(key=lambda c: c['dist_from_orig'])
            best = full_los[0]
            also_road_close = [c for c in full_los if c['centerline_dist'] < ROAD_ACCESS_M]
            road_pick = also_road_close[0] if also_road_close else None
            print(f'  Found {len(full_los)} candidates with 100% VLOS (out of {len(all_cands)} scanned)')
            print(f'  CLOSEST to original launch:')
            print(f'    ({best["lat"]:.6f}, {best["lon"]:.6f}), {best["dist_from_orig"]:.0f} m drive, '
                  f'elev {best["ground_amsl"]:.0f} m, {best["centerline_dist"]:.0f} m from centerline')
            if road_pick and road_pick is not best:
                print(f'  CLOSEST that\'s also <{ROAD_ACCESS_M:.0f} m from centerline (road-accessible):')
                print(f'    ({road_pick["lat"]:.6f}, {road_pick["lon"]:.6f}), {road_pick["dist_from_orig"]:.0f} m drive, '
                      f'elev {road_pick["ground_amsl"]:.0f} m, {road_pick["centerline_dist"]:.0f} m from centerline')
            elif road_pick is best:
                print(f'  (closest pick is already <{ROAD_ACCESS_M:.0f} m from centerline)')
            else:
                print(f'  No 100%-VLOS candidate within 100 m of centerline; best alternative is off-road.')
            results.append((label, pair_num, e_file, w_file, lat_o, lon_o, best, road_pick))
        else:
            # No 100% — show top-VLOS candidate
            top = max(all_cands, key=lambda c: (c['vlos_pct'], -c['dist_from_orig']))
            print(f'  NO candidate within {RADIUS_M/1000:.1f} km gave 100% VLOS')
            print(f'  Best available: ({top["lat"]:.6f}, {top["lon"]:.6f}), {top["dist_from_orig"]:.0f} m drive, '
                  f'elev {top["ground_amsl"]:.0f} m, VLOS {top["vlos_pct"]:.1f}%, '
                  f'worst block {top["worst_below"]:.1f} m')
            results.append((label, pair_num, e_file, w_file, lat_o, lon_o, top, None))

    # Concise summary table
    print(f'\n\n=== Recommended VLOS-clean launch alternatives ===')
    print(f'{"Pair":<14}{"Files":<26}{"Drive":<8}{"Elev":<7}{"Road":<7}{"VLOS%":<7}{"New Lat":<12}{"New Lon"}')
    print('-' * 110)
    for label, pn, ef, wf, lo, no, best, road in results:
        rec = road if road is not None else best
        rec_pct = rec['vlos_pct'] if rec else 0
        print(f'  {label:<12}{ef+"/"+wf:<26}{rec["dist_from_orig"]:<8.0f}{rec["ground_amsl"]:<7.0f}'
              f'{rec["centerline_dist"]:<7.0f}{rec_pct:<7.1f}{rec["lat"]:<12.6f}{rec["lon"]:.6f}')


if __name__ == '__main__':
    main()
