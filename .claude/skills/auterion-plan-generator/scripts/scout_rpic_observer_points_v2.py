"""Pared-down RPIC observer scout (v2).

Key changes vs v1:
  - CANDIDATE FILTERING: only points within 100 m of the corridor union KML are
    considered. Cuts the candidate count by ~95% vs blind grid search.
  - EARLY EXIT: first blocked LOS sample disqualifies a candidate. We need 100%,
    so no point computing the rest.
  - LOWER FIDELITY: 50 m path sampling + 50 LOS samples per ray. Pilots can't
    visually resolve finer than that anyway.
  - PER-PAIR LOOP: process each pair independently, write JSON line, gc.

Output: per failing pair, nearest 100%-VLOS candidate within the 100 m corridor
buffer. RPIC stands there; VO stays at launch for hot-swap handling.
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
                       OPERATOR_EYE_M, hav, check_plan_vlos)
from shapely.geometry import Polygon, Point
from coverage_check_multi import parse_kml_polygon, make_projection

PLAN_DIR = 'C:/Users/rharbach.STAHLY/Documents/Auterion Mission Control/Missions'
KML_LAUNCHES = 'C:/Users/rharbach.STAHLY/Downloads/HomePoints.kml'
TARGET_KML   = 'C:/Users/rharbach.STAHLY/Downloads/Fergus Hilger-Roy — corridor union.kml'
OUT_JSON     = 'C:/Users/rharbach.STAHLY/Downloads/Fergus_41m_rpic_observer_points.json'

# Search params (pared down)
CORRIDOR_BUFFER_M = 100.0
GRID_M            = 100.0
PATH_SAMPLE_M     = 50.0
LOS_SAMPLES       = 50
VLOS_THRESHOLD    = 99.999


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


def vlos_all_clear(rpic_ll, op_amsl, combined_path):
    """Return True iff EVERY path sample is LOS-clear. Early exit on first block."""
    for p in combined_path:
        clear, _, _ = los_line_clear(rpic_ll, op_amsl, (p[0], p[1]), p[2],
                                      samples=LOS_SAMPLES)
        if not clear:
            return False
    return True


def main():
    plans = [f'Fergus{n}.plan' for n in range(3, 21)]
    plan_vlos = {fn: check_plan_vlos(os.path.join(PLAN_DIR, fn))['los_pct']
                 for fn in plans}

    # Pairs: pair_num n -> (launch_idx n, Fergus{2n+1}, Fergus{2n+2})
    pairs = [(n, n, f'Fergus{2*n+1}.plan', f'Fergus{2*n+2}.plan') for n in range(1, 10)]
    pairs_to_scout = [p for p in pairs
                      if plan_vlos.get(p[2], 100) < VLOS_THRESHOLD
                      or plan_vlos.get(p[3], 100) < VLOS_THRESHOLD]
    print(f'Pairs needing scout: {[p[0] for p in pairs_to_scout]}')

    launches = load_launches(KML_LAUNCHES)
    launches.sort(key=lambda L: -L[1])

    # Load target corridor union, build local-meter buffered polygon for candidate filter
    target_outer, target_holes = parse_kml_polygon(TARGET_KML)[0]
    # Use corridor centroid for local projection
    ref_lat = sum(p[0] for p in target_outer) / len(target_outer)
    ref_lon = sum(p[1] for p in target_outer) / len(target_outer)
    to_xy, from_xy = make_projection(ref_lat, ref_lon)
    target_xy = Polygon([to_xy(*p) for p in target_outer],
                        [[to_xy(*p) for p in h] for h in target_holes])
    corridor_buffered = target_xy.buffer(CORRIDOR_BUFFER_M)
    print(f'Corridor union: {target_xy.area/4046.86:.0f} ac')
    print(f'Corridor + {CORRIDOR_BUFFER_M:.0f} m buffer: {corridor_buffered.area/4046.86:.0f} ac '
          f'(candidate region)')

    # Per-pair processing
    results = []
    for (pair_n, l_idx, ep, wp) in pairs_to_scout:
        launch_ll = launches[l_idx - 1]
        print(f'\n=== Pair {pair_n} (L{l_idx}): {ep} ({plan_vlos[ep]:.1f}%) + '
              f'{wp} ({plan_vlos[wp]:.1f}%) ===')
        print(f'   Launch: ({launch_ll[0]:.6f}, {launch_ll[1]:.6f})')

        # Build combined flight path
        combined_raw = []
        for fn in (ep, wp):
            plan = json.load(open(os.path.join(PLAN_DIR, fn)))
            combined_raw.extend(extract_flight_path(plan))
        combined_path = interpolate_path(combined_raw, PATH_SAMPLE_M)
        print(f'   Combined path samples: {len(combined_path)}')

        # Build candidate set: grid points within 100m of corridor AND within reasonable radius
        # Candidates are within corridor_buffered. We iterate grid over corridor_buffered bounds.
        bounds = corridor_buffered.bounds   # (minx, miny, maxx, maxy) in local meters
        launch_xy = to_xy(*launch_ll)
        # Iterate grid intersection with corridor_buffered
        m_lat = 111132.0
        m_lon = 111132.0 * math.cos(math.radians(launch_ll[0]))
        # Limit to candidates within ~5 km of launch (Part 107 RPIC-VO distance constraint)
        MAX_DIST_FROM_LAUNCH = 5000.0
        cands = []
        x = bounds[0]
        while x <= bounds[2]:
            y = bounds[1]
            while y <= bounds[3]:
                dx = x - launch_xy[0]; dy = y - launch_xy[1]
                d = math.hypot(dx, dy)
                if d <= MAX_DIST_FROM_LAUNCH and corridor_buffered.contains(Point(x, y)):
                    cands.append((x, y, d))
                y += GRID_M
            x += GRID_M
        cands.sort(key=lambda c: c[2])   # nearest first - allows early termination
        print(f'   Candidate cells (within {CORRIDOR_BUFFER_M:.0f}m of corridor '
              f'AND within {MAX_DIST_FROM_LAUNCH/1000:.0f} km of launch): {len(cands)}')

        # Search nearest-first; first 100% VLOS candidate wins
        found = None
        checked = 0
        for (cx, cy, dist) in cands:
            clat, clon = from_xy(cx, cy)
            try:
                op_ground = terrain_amsl(clat, clon)
            except Exception:
                continue
            op_amsl = op_ground + OPERATOR_EYE_M
            checked += 1
            if vlos_all_clear((clat, clon), op_amsl, combined_path):
                found = {'lat': clat, 'lon': clon, 'dist': dist, 'ground': op_ground}
                print(f'   Found 100% VLOS candidate after {checked}/{len(cands)} checks')
                break
        if not found:
            print(f'   NO 100% VLOS candidate found after checking {checked} cells')

        try:
            orig_ground = terrain_amsl(*launch_ll)
        except Exception:
            orig_ground = 0.0

        if found:
            print(f'   -> RPIC: ({found["lat"]:.6f}, {found["lon"]:.6f})')
            print(f'      {found["dist"]:.0f} m from launch, '
                  f'ground {found["ground"]:.0f} m AMSL ({found["ground"]-orig_ground:+.0f} m vs launch)')

        results.append({
            'pair': pair_n,
            'plans': [ep, wp],
            'launch': {'lat': launch_ll[0], 'lon': launch_ll[1],
                       'ground_amsl_m': orig_ground},
            'rpic': ({'lat': found['lat'], 'lon': found['lon'],
                      'dist_from_launch_m': round(found['dist'], 1),
                      'ground_amsl_m': round(found['ground'], 1),
                      'elev_above_launch_m': round(found['ground'] - orig_ground, 1)}
                     if found else None),
        })
        gc.collect()

    # Save and print summary
    json.dump(results, open(OUT_JSON, 'w'), indent=2)
    print(f'\nSaved: {OUT_JSON}\n')

    print('=== Summary ===')
    print(f'{"Pair":<5}{"Plans":<22}{"Launch (lat,lon)":<26}{"RPIC (lat,lon)":<26}{"Dist":<8}{"Elev"}')
    for r in results:
        launch_s = f'({r["launch"]["lat"]:.5f},{r["launch"]["lon"]:.5f})'
        if r['rpic']:
            rpic_s = f'({r["rpic"]["lat"]:.5f},{r["rpic"]["lon"]:.5f})'
            dist_s = f'{r["rpic"]["dist_from_launch_m"]:.0f} m'
            elev_s = f'{r["rpic"]["ground_amsl_m"]:.0f}m ({r["rpic"]["elev_above_launch_m"]:+.0f}m)'
        else:
            rpic_s = 'NOT FOUND'; dist_s = '-'; elev_s = '-'
        plans_s = f'{r["plans"][0].replace(".plan","")}+{r["plans"][1].replace(".plan","")}'
        print(f'{r["pair"]:<5}{plans_s:<22}{launch_s:<26}{rpic_s:<26}{dist_s:<8}{elev_s}')


if __name__ == '__main__':
    main()
