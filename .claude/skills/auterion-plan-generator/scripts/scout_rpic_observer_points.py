"""Scout RPIC observer points for the 41m highway-centerline pairs.

For each pair (east+west tile sharing a launch), if either tile has partial
VLOS from the launch point, grid-search outward for the NEAREST point that
gives 100% VLOS to the COMBINED flight path (both tiles).

The selected point is where the RPIC stands to maintain VLOS while a second
staff member acts as VO at the launch handling battery hot-swaps per Part 107.

The point does NOT have to be in the corridor (highway, hillside, ridge — any
accessible location is acceptable).

Output: per failing pair, the recommended RPIC location + distance from
launch + ground elevation + how much higher than launch.
"""
import os, sys, json, math, re

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SKILL_DIR, 'scripts'))

import dem_lookup
_explicit = os.path.expanduser('~/.claude/dem_cache/dem_ee0aa3a8a9d0.json')
if os.path.exists(_explicit):
    dem_lookup._explicit_meta_paths.insert(0, _explicit)
    dem_lookup._local_dem = None
    dem_lookup._local_meta = None

from dem_lookup import terrain_amsl, ensure_dem_for_bbox
from los_check import (extract_flight_path, interpolate_path, los_line_clear,
                       OPERATOR_EYE_M, hav, check_plan_vlos)

PLAN_DIR = 'C:/Users/rharbach.STAHLY/Documents/Auterion Mission Control/Missions'
KML_LAUNCHES = 'C:/Users/rharbach.STAHLY/Downloads/HomePoints.kml'

# Grid search params
RADIUS_M_PHASE1 = 2500.0
GRID_M_PHASE1   = 150.0
RADIUS_M_PHASE2 = 5000.0
GRID_M_PHASE2   = 250.0
PATH_SAMPLE_M   = 25.0
LOS_SAMPLES     = 100
VLOS_THRESHOLD  = 99.999  # >= 100%


def load_launches(path):
    txt = open(path, 'r', encoding='utf-8').read()
    pms = re.findall(r'<Placemark[^>]*>([\s\S]*?)</Placemark>', txt)
    out = []
    for pm in pms:
        nm = re.search(r'<name>([^<]+)</name>', pm)
        pt = re.search(r'<Point[\s\S]*?<coordinates>([^<]+)</coordinates>', pm)
        if not (nm and pt): continue
        if 'launch' not in nm.group(1).strip().lower(): continue
        lon, lat = pt.group(1).strip().split(',')[:2]
        out.append((float(lat), float(lon)))
    return out


def candidate_grid(origin_ll, radius_m, grid_m):
    m_lat = 111132.0
    m_lon = 111132.0 * math.cos(math.radians(origin_ll[0]))
    n = int(math.ceil(radius_m / grid_m))
    out = []
    for i in range(-n, n+1):
        for j in range(-n, n+1):
            dx = i * grid_m; dy = j * grid_m
            d = math.hypot(dx, dy)
            if d > radius_m: continue
            out.append((origin_ll[0] + dy / m_lat,
                       origin_ll[1] + dx / m_lon, d))
    return out


def vlos_pct(rpic_ll, combined_path):
    op_ground = terrain_amsl(*rpic_ll)
    op_amsl = op_ground + OPERATOR_EYE_M
    blocked = 0
    worst_below = 0
    for p in combined_path:
        clear, below, _ = los_line_clear(rpic_ll, op_amsl, (p[0], p[1]), p[2],
                                          samples=LOS_SAMPLES)
        if not clear:
            blocked += 1
            if below > worst_below: worst_below = below
    pct = 100.0 * (len(combined_path) - blocked) / len(combined_path) if combined_path else 0
    return pct, blocked, worst_below, op_ground


def scout_pair(label, plan_paths, launch_ll):
    """Try grid search outward. Return best 100%-VLOS candidate (nearest)."""
    combined = []
    for pp in plan_paths:
        plan = json.load(open(pp))
        combined.extend(extract_flight_path(plan))
    combined_path = interpolate_path(combined, PATH_SAMPLE_M)
    print(f'  Combined flight path: {len(combined_path)} samples')

    orig_pct, orig_blocked, orig_worst, orig_ground = vlos_pct(launch_ll, combined_path)
    print(f'  Launch VLOS = {orig_pct:.2f}% ({orig_blocked} blocked, worst {orig_worst:.1f} m below LOS, ground {orig_ground:.0f} m)')

    for phase, (R, G) in enumerate([(RADIUS_M_PHASE1, GRID_M_PHASE1),
                                     (RADIUS_M_PHASE2, GRID_M_PHASE2)], start=1):
        cands = candidate_grid(launch_ll, R, G)
        full_los = []
        for clat, clon, dist in cands:
            pct, _, _, ground = vlos_pct((clat, clon), combined_path)
            if pct >= VLOS_THRESHOLD:
                full_los.append({'lat': clat, 'lon': clon, 'dist': dist, 'ground': ground})
        if full_los:
            full_los.sort(key=lambda c: c['dist'])
            best = full_los[0]
            print(f'  Phase {phase}: found {len(full_los)} candidate(s) with {VLOS_THRESHOLD}% VLOS '
                  f'within {R:.0f} m at {G:.0f} m grid')
            return best, orig_ground
        else:
            print(f'  Phase {phase}: no 100%-VLOS candidate within {R:.0f} m at {G:.0f} m grid')
    return None, orig_ground


def main():
    # Read VLOS status for each plan
    plans = [f'Fergus{n}.plan' for n in range(3, 21)]
    plan_vlos = {}
    for fn in plans:
        v = check_plan_vlos(os.path.join(PLAN_DIR, fn))
        plan_vlos[fn] = v['los_pct']

    # Pairs: (pair_num, launch_index, east_plan, west_plan)
    pairs = [(n, n, f'Fergus{2*n+1}.plan', f'Fergus{2*n+2}.plan') for n in range(1, 10)]

    launches = load_launches(KML_LAUNCHES)
    launches.sort(key=lambda L: -L[1])

    # The explicit DEM cache (prepended at module load) covers the full corridor + 5 km buffer.
    # Skip ensure_dem_for_bbox -- live USGS fetch is intermittently failing.

    print('=== Per-plan VLOS from launch ===')
    print(f'{"Plan":<14}{"VLOS%":<10}{"Status"}')
    for fn in plans:
        ok = plan_vlos[fn] >= VLOS_THRESHOLD
        print(f'{fn:<14}{plan_vlos[fn]:<10.2f}{"100% from launch" if ok else "NEEDS RPIC SCOUT"}')

    # Determine which pairs need scouting
    pairs_to_scout = []
    for (n, l_idx, ep, wp) in pairs:
        if plan_vlos.get(ep, 100) < VLOS_THRESHOLD or plan_vlos.get(wp, 100) < VLOS_THRESHOLD:
            pairs_to_scout.append((n, l_idx, ep, wp))

    print(f'\n=== {len(pairs_to_scout)} pair(s) need RPIC observer scouting ===\n')

    results = []
    for (n, l_idx, ep, wp) in pairs_to_scout:
        launch_ll = launches[l_idx - 1]
        ep_path = os.path.join(PLAN_DIR, ep)
        wp_path = os.path.join(PLAN_DIR, wp)
        label = f'Pair {n} (L{l_idx}): {ep}({plan_vlos[ep]:.1f}%) + {wp}({plan_vlos[wp]:.1f}%)'
        print(f'--- {label} ---')
        print(f'  Launch: ({launch_ll[0]:.6f}, {launch_ll[1]:.6f})')
        best, orig_ground = scout_pair(label, [ep_path, wp_path], launch_ll)
        if best is None:
            print(f'  NO 100%-VLOS RPIC point found within {RADIUS_M_PHASE2:.0f} m\n')
            results.append({'pair': n, 'launch_ll': launch_ll, 'rpic': None,
                            'orig_ground': orig_ground})
        else:
            elev_diff = best['ground'] - orig_ground
            print(f'  -> RPIC point: ({best["lat"]:.6f}, {best["lon"]:.6f})')
            print(f'     Distance from launch: {best["dist"]:.0f} m')
            print(f'     Ground elev: {best["ground"]:.0f} m AMSL  '
                  f'({"+%.0f" % elev_diff if elev_diff >= 0 else "%.0f" % elev_diff} m vs launch)\n')
            results.append({'pair': n, 'launch_ll': launch_ll, 'rpic': best,
                            'orig_ground': orig_ground})

    print('=== Summary table ===')
    print(f'{"Pair":<6}{"Plans":<24}{"Launch":<28}{"RPIC observer":<28}{"Dist":<8}{"Elev"}')
    for r in results:
        n = r['pair']
        pair_def = next(p for p in pairs_to_scout if p[0] == n)
        plans_str = f'{pair_def[2].replace(".plan","")}+{pair_def[3].replace(".plan","")}'
        launch_str = f'({r["launch_ll"][0]:.5f},{r["launch_ll"][1]:.5f})'
        if r['rpic']:
            rpic_str = f'({r["rpic"]["lat"]:.5f},{r["rpic"]["lon"]:.5f})'
            dist_str = f'{r["rpic"]["dist"]:.0f} m'
            elev_diff = r['rpic']['ground'] - r['orig_ground']
            elev_str = f'{r["rpic"]["ground"]:.0f}m ({elev_diff:+.0f}m)'
        else:
            rpic_str = 'NOT FOUND'
            dist_str = '-'
            elev_str = '-'
        print(f'{n:<6}{plans_str:<24}{launch_str:<28}{rpic_str:<28}{dist_str:<8}{elev_str}')

    # Save results JSON for downstream use
    out_path = 'C:/Users/rharbach.STAHLY/Downloads/Fergus_41m_rpic_observer_points.json'
    json.dump([{
        'pair': r['pair'],
        'launch': {'lat': r['launch_ll'][0], 'lon': r['launch_ll'][1]},
        'rpic': ({'lat': r['rpic']['lat'], 'lon': r['rpic']['lon'],
                  'dist_from_launch_m': r['rpic']['dist'],
                  'ground_amsl_m': r['rpic']['ground']}
                 if r['rpic'] else None),
    } for r in results], open(out_path, 'w'), indent=2)
    print(f'\nSaved JSON: {out_path}')


if __name__ == '__main__':
    main()
