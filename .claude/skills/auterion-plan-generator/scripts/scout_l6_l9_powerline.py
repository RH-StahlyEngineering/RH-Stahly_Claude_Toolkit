"""Scout VLOS-clean alternatives for L6 and L9 against the new powerline flight paths.

L6 problem: Fergus12 (Pair 5 west tile) at 43.46% VLOS.
L9 problem: Fergus14 (Pair 6 west tile) at 85.86% VLOS.

Same algorithm as scripts/scout_vlos_alternatives.py: grid-search around original
launch, check combined VLOS against both tiles of the pair, pick closest 100%-VLOS
candidate (prefer <500 m from centerline = road accessible).
"""
import os, sys, json, math

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SKILL_DIR, 'scripts'))

import dem_lookup
_explicit = os.path.expanduser('~/.claude/dem_cache/dem_ee0aa3a8a9d0.json')
if os.path.exists(_explicit):
    dem_lookup._explicit_meta_paths.insert(0, _explicit)
    dem_lookup._local_dem = None
    dem_lookup._local_meta = None

from dem_lookup import terrain_amsl
from los_check import (
    extract_flight_path, interpolate_path, los_line_clear,
    OPERATOR_EYE_M, hav,
)
from generate_fergus_pair1 import load_centerline

PLAN_DIR = 'C:/Users/rharbach.STAHLY/Documents/Auterion Mission Control/Missions'
KML_CENTERLINE = 'C:/Users/rharbach.STAHLY/Downloads/HighwayCenterline.kml'

RADIUS_M = 2000.0
GRID_M   = 200.0
PATH_SAMPLE_M = 25.0
LINE_SAMPLES = 100
ROAD_ACCESS_M = 500.0

CASES = [
    ('Pair 5 (L6) — Fergus11/12', ('Fergus11.plan', 'Fergus12.plan'), (47.274760, -109.253320)),
    ('Pair 6 (L9) — Fergus13/14', ('Fergus13.plan', 'Fergus14.plan'), (47.260041, -109.342557)),
]


def candidate_grid(orig_ll, radius_m, grid_m):
    m_lat = 111132.0
    m_lon = 111132.0 * math.cos(math.radians(orig_ll[0]))
    n = int(math.ceil(radius_m / grid_m))
    out = []
    for i in range(-n, n+1):
        for j in range(-n, n+1):
            dx = i * grid_m; dy = j * grid_m
            d = math.hypot(dx, dy)
            if d > radius_m: continue
            out.append((orig_ll[0] + dy / m_lat, orig_ll[1] + dx / m_lon, d))
    return out


def vlos_pct_combined(launch_ll, combined_path):
    op_ground = terrain_amsl(*launch_ll)
    op_amsl = op_ground + OPERATOR_EYE_M
    blocked = 0
    worst_below = 0
    for p in combined_path:
        clear, below, _ = los_line_clear(launch_ll, op_amsl, (p[0], p[1]), p[2], samples=LINE_SAMPLES)
        if not clear:
            blocked += 1
            if below > worst_below: worst_below = below
    pct = 100.0 * (len(combined_path) - blocked) / len(combined_path) if combined_path else 0
    return pct, blocked, worst_below, op_ground


def main():
    centerline = load_centerline(KML_CENTERLINE)

    for label, (ef, wf), orig in CASES:
        ep = json.load(open(os.path.join(PLAN_DIR, ef)))
        wp = json.load(open(os.path.join(PLAN_DIR, wf)))
        combined = interpolate_path(extract_flight_path(ep) + extract_flight_path(wp), PATH_SAMPLE_M)
        orig_pct, orig_blocked, orig_worst, orig_ground = vlos_pct_combined(orig, combined)
        print(f'\n=== {label} ===')
        print(f'  Original launch {orig}: elev {orig_ground:.0f} m, VLOS {orig_pct:.2f}% '
              f'({orig_blocked} blocked, worst {orig_worst:.1f} m)')

        cands = candidate_grid(orig, RADIUS_M, GRID_M)
        full_los = []
        all_cands = []
        for clat, clon, dist in cands:
            pct, blocked, below, ground = vlos_pct_combined((clat, clon), combined)
            cl_dist = min(hav((clat, clon), c) for c in centerline)
            entry = {'lat': clat, 'lon': clon, 'dist_from_orig': dist,
                     'ground': ground, 'vlos_pct': pct, 'worst': below,
                     'centerline_dist': cl_dist}
            all_cands.append(entry)
            if pct >= 99.999: full_los.append(entry)

        if full_los:
            full_los.sort(key=lambda c: c['dist_from_orig'])
            best = full_los[0]
            road_close = [c for c in full_los if c['centerline_dist'] < ROAD_ACCESS_M]
            road_close.sort(key=lambda c: c['dist_from_orig'])
            road_pick = road_close[0] if road_close else None
            print(f'  {len(full_los)} candidates with 100% VLOS')
            print(f'  CLOSEST to original: ({best["lat"]:.6f}, {best["lon"]:.6f}), '
                  f'{best["dist_from_orig"]:.0f} m drive, elev {best["ground"]:.0f} m, '
                  f'{best["centerline_dist"]:.0f} m from centerline')
            if road_pick is not None and road_pick is not best:
                print(f'  CLOSEST <{ROAD_ACCESS_M:.0f} m from centerline: '
                      f'({road_pick["lat"]:.6f}, {road_pick["lon"]:.6f}), '
                      f'{road_pick["dist_from_orig"]:.0f} m drive, elev {road_pick["ground"]:.0f} m, '
                      f'{road_pick["centerline_dist"]:.0f} m from centerline')
            elif road_pick is best:
                print(f'  (closest pick already <{ROAD_ACCESS_M:.0f} m from centerline)')
            else:
                print(f'  No 100%-VLOS candidate within {ROAD_ACCESS_M:.0f} m of centerline; best is off-road.')
        else:
            top = max(all_cands, key=lambda c: c['vlos_pct'])
            print(f'  NO candidate within {RADIUS_M/1000:.0f} km gave 100% VLOS.')
            print(f'  Best: ({top["lat"]:.6f}, {top["lon"]:.6f}), {top["dist_from_orig"]:.0f} m drive, '
                  f'VLOS {top["vlos_pct"]:.2f}%, worst {top["worst"]:.1f} m')


if __name__ == '__main__':
    main()
