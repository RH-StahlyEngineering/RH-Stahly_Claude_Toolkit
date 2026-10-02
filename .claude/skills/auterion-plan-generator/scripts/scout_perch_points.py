"""Scout PERCH points for partial-VLOS pairs (the "ground controller perch" concept).

Workflow assumption (Ryan's standard practice):
  - RPIC + drone + VO at launch -> drone takes off
  - RPIC drives to PERCH while drone climbs to mission altitude (VO has VLOS during transit)
  - RPIC at PERCH has 100% VLOS to the SURVEY portion (transects, fig-8, cross-line, turnaround)
  - When low battery, drone RTL-s; VO at launch handles landing + hot swap
  - Two eyes on the vehicle at all times: RPIC sees survey, VO sees takeoff/landing

The "survey portion" is exactly what extract_flight_path returns (it excludes the
implicit home-to-first-waypoint transit and the last-waypoint-to-home RTL).

Search params:
  - 1.5 mi radius (2414 m) around each launch
  - 150 m grid
  - Early-exit on first blocked LOS sample
"""
import os, sys, json, math, re, gc

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SKILL_DIR, 'scripts'))

import dem_lookup
_explicit = os.path.expanduser('~/.claude/dem_cache/dem_ee0aa3a8a9d0.json')
if os.path.exists(_explicit):
    dem_lookup._explicit_meta_paths.insert(0, _explicit)
    dem_lookup._local_dem = None
    dem_lookup._local_meta = None

from dem_lookup import terrain_amsl
from los_check import (extract_flight_path, interpolate_path, los_line_clear,
                       OPERATOR_EYE_M, check_plan_vlos)

PLAN_DIR = 'C:/Users/rharbach.STAHLY/Documents/Auterion Mission Control/Missions'
KML_LAUNCHES = 'C:/Users/rharbach.STAHLY/Downloads/HomePoints.kml'
OUT_JSON = 'C:/Users/rharbach.STAHLY/Downloads/Fergus_41m_perch_points.json'

RADIUS_M       = 2414.0    # 1.5 mi
GRID_M         = 100.0
PATH_SAMPLE_M  = 50.0
LOS_SAMPLES    = 25
VLOS_THRESHOLD = 99.999


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


def scout(launch_ll, survey_samples):
    """Grid-search for nearest 100% VLOS perch within RADIUS_M of launch."""
    launch_ground = terrain_amsl(*launch_ll)
    m_lat = 111132.0
    m_lon = 111132.0 * math.cos(math.radians(launch_ll[0]))

    # Build candidate grid, sorted by distance
    n = int(math.ceil(RADIUS_M / GRID_M))
    cands = []
    for i in range(-n, n+1):
        for j in range(-n, n+1):
            dx = i * GRID_M; dy = j * GRID_M
            d = math.hypot(dx, dy)
            if d > RADIUS_M or d < 1: continue
            cands.append((launch_ll[0] + dy/m_lat,
                          launch_ll[1] + dx/m_lon, d))
    cands.sort(key=lambda c: c[2])

    checked = 0
    best_partial = None    # track best partial result if no 100% found
    for clat, clon, dist in cands:
        try:
            ground = terrain_amsl(clat, clon)
        except Exception:
            continue
        checked += 1
        op_amsl = ground + OPERATOR_EYE_M
        ok = True
        cleared = 0
        for p in survey_samples:
            clear, _, _ = los_line_clear((clat, clon), op_amsl, (p[0], p[1]), p[2],
                                          samples=LOS_SAMPLES)
            if clear: cleared += 1
            else:
                ok = False
                break
        if ok:
            return {'lat': clat, 'lon': clon, 'dist': dist, 'ground': ground,
                    'launch_ground': launch_ground,
                    'elev_above_launch_m': ground - launch_ground,
                    'checked': checked, 'total': len(cands), 'status': 'FOUND'}
        # Track best partial (highest cleared count)
        if best_partial is None or cleared > best_partial['cleared']:
            best_partial = {'lat': clat, 'lon': clon, 'dist': dist, 'ground': ground,
                            'cleared': cleared, 'total_samples': len(survey_samples),
                            'pct': 100.0 * cleared / len(survey_samples)}
    return {'status': 'NOT_FOUND', 'checked': checked, 'total': len(cands),
            'best_partial': best_partial,
            'launch_ground': launch_ground}


def main():
    import time
    t0 = time.time()
    plans = [f'Fergus{n}.plan' for n in range(3, 21)]
    plan_vlos = {fn: check_plan_vlos(os.path.join(PLAN_DIR, fn))['los_pct']
                 for fn in plans}

    # Pairs whose either tile has <100% VLOS from launch
    pairs = [(n, n, f'Fergus{2*n+1}.plan', f'Fergus{2*n+2}.plan') for n in range(1, 10)]
    pairs_to_scout = [p for p in pairs
                      if plan_vlos.get(p[2], 100) < VLOS_THRESHOLD
                      or plan_vlos.get(p[3], 100) < VLOS_THRESHOLD]
    print(f'Pairs needing perch: {[p[0] for p in pairs_to_scout]}')

    launches = load_launches(KML_LAUNCHES)
    launches.sort(key=lambda L: -L[1])

    results = {}
    for (pair_n, l_idx, ep, wp) in pairs_to_scout:
        launch_ll = launches[l_idx - 1]
        # Combine survey samples from both tiles
        survey_raw = []
        for fn in (ep, wp):
            plan = json.load(open(os.path.join(PLAN_DIR, fn)))
            survey_raw.extend(extract_flight_path(plan))
        survey_samples = interpolate_path(survey_raw, PATH_SAMPLE_M)

        t = time.time()
        result = scout(launch_ll, survey_samples)
        elapsed = time.time() - t

        print(f'\nPair {pair_n} (L{l_idx}, {ep}={plan_vlos[ep]:.1f}%, {wp}={plan_vlos[wp]:.1f}%): {elapsed:.1f}s')
        if result['status'] == 'FOUND':
            print(f'  PERCH: ({result["lat"]:.6f}, {result["lon"]:.6f})')
            print(f'    {result["dist"]:.0f} m from launch, '
                  f'ground {result["ground"]:.0f} m AMSL '
                  f'({result["elev_above_launch_m"]:+.0f} m vs launch)')
            print(f'    Found after {result["checked"]}/{result["total"]} grid cells')
        else:
            bp = result.get('best_partial')
            print(f'  NO 100% VLOS perch found within 1.5 mi after {result["checked"]} candidates')
            if bp:
                print(f'    Best partial: ({bp["lat"]:.6f}, {bp["lon"]:.6f}) at {bp["dist"]:.0f} m, '
                      f'sees {bp["pct"]:.1f}% of survey path')

        results[pair_n] = {
            'pair': pair_n,
            'launch': {'lat': launch_ll[0], 'lon': launch_ll[1],
                       'ground_amsl_m': round(result['launch_ground'], 1)},
            'plans': [ep, wp],
            'perch': ({'lat': result['lat'], 'lon': result['lon'],
                       'dist_from_launch_m': round(result['dist'], 1),
                       'ground_amsl_m': round(result['ground'], 1),
                       'elev_above_launch_m': round(result['elev_above_launch_m'], 1)}
                      if result['status'] == 'FOUND' else None),
            'best_partial': result.get('best_partial'),
        }
        gc.collect()

    json.dump(results, open(OUT_JSON, 'w'), indent=2)
    print(f'\nSaved: {OUT_JSON}')
    print(f'Total runtime: {time.time()-t0:.1f}s')

    # Summary
    print('\n=== Summary ===')
    found = [r for r in results.values() if r['perch']]
    notfound = [r for r in results.values() if not r['perch']]
    print(f'  Found perch (100% VLOS within 1.5 mi): {len(found)} pair(s) -> {[r["pair"] for r in found]}')
    print(f'  No perch: {len(notfound)} pair(s) -> {[r["pair"] for r in notfound]}')


if __name__ == '__main__':
    main()
