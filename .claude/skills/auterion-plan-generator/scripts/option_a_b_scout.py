"""Option A + Option B for the 3 unfound pairs (5, 6, 8).
Pared aggressively to run in under 30 sec.

Option A: keep 3.6 km tiles, widen RPIC search (no corridor filter)
  - 3 km radius, 300 m grid, 75 m path sampling, 25 LOS samples
  - Early-exit on first blocked sample

Option B: shorten tiles per direction until 100% VLOS from launch
  - 5 candidate lengths per direction: 3000, 2400, 1800, 1200, 600 m
  - Pick the LARGEST that gives 100% VLOS
  - Save successful plans as Fergus{n}_short.plan
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

from dem_lookup import terrain_amsl, bake_amsl

import generate_fergus_pair1 as gfp1
gfp1.AGL            = 41.0
gfp1.SPEED          = 14.0
gfp1.LINE_SPACING_M = 41.0
gfp1.HALF_LS_M      = 20.5
gfp1.TILE_LEN_M     = 3600.0

from generate_fergus_pair1 import (
    hav, douglas_peucker, build_plan, minified_write,
    AGL, SPEED, TURNAROUND_M, DECIMATE_TOL_M,
)
from generate_fergus_all_pairs import (
    project_onto_centerline, insert_meeting_into_centerline, walk_along,
)
from los_check import (extract_flight_path, interpolate_path, los_line_clear,
                       OPERATOR_EYE_M, check_plan_vlos)

PLAN_DIR = 'C:/Users/rharbach.STAHLY/Documents/Auterion Mission Control/Missions'
KML_HIGHWAY    = 'C:/Users/rharbach.STAHLY/Downloads/HighwayCenterline.kml'
KML_LAUNCHES   = 'C:/Users/rharbach.STAHLY/Downloads/HomePoints.kml'
F1_TEMPLATE    = os.path.join(PLAN_DIR, 'Fergus1.plan')
OUT_JSON = 'C:/Users/rharbach.STAHLY/Downloads/Fergus_41m_options_AB.json'

CORRIDOR_WIDTH_M = 2 * AGL

A_RADIUS_M       = 3000.0
A_GRID_M         = 300.0
A_PATH_SAMPLE_M  = 75.0
A_LOS_SAMPLES    = 25
VLOS_THRESHOLD   = 99.999

B_LENGTHS_M      = [3000, 2400, 1800, 1200, 600, 300, 150]

UNFOUND_PAIRS = [5, 6, 8]


def load_linestring(path):
    txt = open(path, 'r', encoding='utf-8').read()
    m = re.search(r'<LineString[\s\S]*?<coordinates>([\s\S]+?)</coordinates>', txt)
    return [tuple(map(float, t.split(',')[:2][::-1])) for t in m.group(1).strip().split()]


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


def option_a_scout(launch_ll, ep_path, wp_path):
    combined_raw = []
    for pp in (ep_path, wp_path):
        plan = json.load(open(pp))
        combined_raw.extend(extract_flight_path(plan))
    path_samples = interpolate_path(combined_raw, A_PATH_SAMPLE_M)

    m_lat = 111132.0
    m_lon = 111132.0 * math.cos(math.radians(launch_ll[0]))
    cands = []
    n = int(math.ceil(A_RADIUS_M / A_GRID_M))
    for i in range(-n, n+1):
        for j in range(-n, n+1):
            dx = i * A_GRID_M; dy = j * A_GRID_M
            d = math.hypot(dx, dy)
            if d > A_RADIUS_M or d < 1: continue
            cands.append((launch_ll[0] + dy/m_lat,
                          launch_ll[1] + dx/m_lon, d))
    cands.sort(key=lambda c: c[2])

    checked = 0
    for clat, clon, dist in cands:
        try:
            op_ground = terrain_amsl(clat, clon)
        except Exception:
            continue
        checked += 1
        op_amsl = op_ground + OPERATOR_EYE_M
        ok = True
        for p in path_samples:
            clear, _, _ = los_line_clear((clat, clon), op_amsl, (p[0], p[1]), p[2],
                                          samples=A_LOS_SAMPLES)
            if not clear: ok = False; break
        if ok:
            return {'lat': clat, 'lon': clon, 'dist': dist, 'ground': op_ground,
                    'checked': checked, 'total': len(cands)}
    return None


def gen_tile_at_length(launch_ll, direction, L, highway, template, idx, fig8_start, fig8_end, suffix='_short'):
    """Generate a single-direction tile at length L. Returns plan path or None."""
    d_proj, meeting_pt, seg_idx, frac = project_onto_centerline(highway, launch_ll)
    pl_with_meet, i_meet = insert_meeting_into_centerline(highway, seg_idx, frac, meeting_pt)
    path, _ = walk_along(pl_with_meet, i_meet, direction, L)
    polyline = douglas_peucker(list(reversed(path)), DECIMATE_TOL_M)
    if len(polyline) < 2: return None
    plan_home = [launch_ll[0], launch_ll[1], terrain_amsl(*launch_ll)]
    meet_amsl = bake_amsl(meeting_pt[0], meeting_pt[1], AGL)
    plan = build_plan(template, polyline, plan_home, AGL,
                      fig8_at_start=fig8_start, fig8_at_end=fig8_end,
                      fig8_centroid_alt_amsl=meet_amsl,
                      fig8_centroid_latlon=meeting_pt)
    for it in plan['mission']['items']:
        if it.get('complexItemType') == 'CorridorComplexItem':
            it['CorridorWidth'] = CORRIDOR_WIDTH_M
    outp = os.path.join(PLAN_DIR, f'Fergus{idx}{suffix}.plan')
    minified_write(outp, plan)
    return outp


def option_b_shorten(launch_ll, highway, template, e_idx, w_idx):
    result = {'e_len_m': None, 'w_len_m': None,
              'e_path': None, 'w_path': None}
    # East tile
    for L in B_LENGTHS_M:
        p = gen_tile_at_length(launch_ll, +1, L, highway, template, e_idx, True, False)
        if p is None: continue
        v = check_plan_vlos(p)
        if v['los_pct'] >= VLOS_THRESHOLD:
            result['e_len_m'] = L; result['e_path'] = p
            break
        try: os.remove(p)
        except OSError: pass
    # West tile
    for L in B_LENGTHS_M:
        p = gen_tile_at_length(launch_ll, -1, L, highway, template, w_idx, False, True)
        if p is None: continue
        v = check_plan_vlos(p)
        if v['los_pct'] >= VLOS_THRESHOLD:
            result['w_len_m'] = L; result['w_path'] = p
            break
        try: os.remove(p)
        except OSError: pass
    return result


def main():
    import time
    t0 = time.time()
    highway = load_linestring(KML_HIGHWAY)
    launches = load_launches(KML_LAUNCHES)
    launches.sort(key=lambda L: -L[1])
    template = json.load(open(F1_TEMPLATE))

    results = {}
    for pair_n in UNFOUND_PAIRS:
        t_pair = time.time()
        launch_ll = launches[pair_n - 1]
        e_idx = 2*pair_n + 1; w_idx = 2*pair_n + 2
        e_plan_path = os.path.join(PLAN_DIR, f'Fergus{e_idx}.plan')
        w_plan_path = os.path.join(PLAN_DIR, f'Fergus{w_idx}.plan')

        print(f'\n--- Pair {pair_n} (L{pair_n}, Fergus{e_idx}/{w_idx}) ---')
        print(f'Launch: ({launch_ll[0]:.6f}, {launch_ll[1]:.6f})')

        ta = time.time()
        a_result = option_a_scout(launch_ll, e_plan_path, w_plan_path)
        a_time = time.time() - ta
        if a_result:
            try: orig_ground = terrain_amsl(*launch_ll)
            except Exception: orig_ground = 0.0
            print(f'[A] {a_time:.1f}s -- RPIC at ({a_result["lat"]:.6f}, {a_result["lon"]:.6f}), '
                  f'{a_result["dist"]:.0f} m from launch, '
                  f'ground {a_result["ground"]:.0f} m ({a_result["ground"]-orig_ground:+.0f} m vs launch) '
                  f'[{a_result["checked"]}/{a_result["total"]} cells]')
        else:
            print(f'[A] {a_time:.1f}s -- NO 100% VLOS within {A_RADIUS_M/1000:.0f} km')

        tb = time.time()
        b_result = option_b_shorten(launch_ll, highway, template, e_idx, w_idx)
        b_time = time.time() - tb
        e_len = b_result['e_len_m']; w_len = b_result['w_len_m']
        e_s = f'{e_len:.0f} m' if e_len else 'NONE'
        w_s = f'{w_len:.0f} m' if w_len else 'NONE'
        print(f'[B] {b_time:.1f}s -- Max east tile: {e_s}, Max west tile: {w_s} '
              f'(orig was 3600+3600 m)')

        results[pair_n] = {
            'pair': pair_n,
            'launch': {'lat': launch_ll[0], 'lon': launch_ll[1]},
            'option_a': ({'lat': a_result['lat'], 'lon': a_result['lon'],
                          'dist_from_launch_m': round(a_result['dist'], 1),
                          'ground_amsl_m': round(a_result['ground'], 1)}
                         if a_result else None),
            'option_b': {
                'e_idx': e_idx, 'w_idx': w_idx,
                'e_len_m': e_len, 'w_len_m': w_len,
                'e_short_plan': b_result['e_path'],
                'w_short_plan': b_result['w_path'],
            },
        }
        print(f'    Pair {pair_n} total: {time.time()-t_pair:.1f}s')
        gc.collect()

    json.dump(results, open(OUT_JSON, 'w'), indent=2)
    print(f'\nSaved: {OUT_JSON}')
    print(f'Total runtime: {time.time()-t0:.1f}s')


if __name__ == '__main__':
    main()
