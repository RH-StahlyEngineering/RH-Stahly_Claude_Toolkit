"""Generate the 41 m AGL / 14 m/s variant of the Hilger-Roy powerline LiDAR set.

Configuration:
  - AGL          = 41 m
  - Speed        = 14 m/s (same PPSM as 70/8: 2 x AGL x speed nearly constant)
  - Line spacing = 41 m (90 deg FOV: line spacing = AGL)
  - Per-line swath  = 82 m
  - Combined swath  = 123 m wide (50% side overlap)
  - Tile length  = 3.6 km (target ~10 min flights at 14 m/s)
  - Polyline     = HIGHWAY CENTERLINE (Ryan's framing for this variant)
  - Lateral clearance floor = 41 * tan(15 deg) = 10.99 m
  - Inner transects at +/- 20.5 m from polyline -> 20.5 m clearance FROM CENTERLINE
    but the WIRE diverges from the highway (median 27 m, max 446 m), so where
    wire is in the [9.5, 31.5] m offset band, at least one transect is within
    the 11 m wire clearance floor -> VIOLATION.

Per-plan output classifies violations as:
  - sustained_in_transect: flight-path points within +/- ~25 m of the highway
    polyline AND within the 11 m wire clearance floor (the transect itself)
  - brief_off_transect: violations outside the transect band (fig-8, cross-line,
    turnaround jog, climb/RTL transit) -- accepted per Rule 3
"""
import os, sys, json, re, math

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SKILL_DIR, 'scripts'))

import dem_lookup
_explicit = os.path.expanduser('~/.claude/dem_cache/dem_ee0aa3a8a9d0.json')
if os.path.exists(_explicit):
    dem_lookup._explicit_meta_paths.insert(0, _explicit)
    dem_lookup._local_dem = None
    dem_lookup._local_meta = None

from dem_lookup import ensure_dem_for_bbox, terrain_amsl, bake_amsl

# Patch the module-level constants BEFORE importing functions that capture them.
import generate_fergus_pair1 as gfp1
gfp1.AGL            = 41.0
gfp1.SPEED          = 14.0
gfp1.LINE_SPACING_M = 41.0
gfp1.HALF_LS_M      = 20.5
gfp1.TILE_LEN_M     = 3600.0

from generate_fergus_pair1 import (
    hav, douglas_peucker, build_plan, minified_write,
    AGL, SPEED, FIG8_DURATION, TURNAROUND_M, TILE_LEN_M, DECIMATE_TOL_M,
)
from generate_fergus_all_pairs import (
    project_onto_centerline, insert_meeting_into_centerline, walk_along,
)
from los_check import check_plan_vlos, extract_flight_path, interpolate_path

KML_HIGHWAY    = 'C:/Users/rharbach.STAHLY/Downloads/HighwayCenterline.kml'
KML_POWERLINE  = 'C:/Users/rharbach.STAHLY/Downloads/Hilger-Roy existing line — joined.kml'
KML_LAUNCHES   = 'C:/Users/rharbach.STAHLY/Downloads/HomePoints.kml'
PLAN_DIR       = 'C:/Users/rharbach.STAHLY/Documents/Auterion Mission Control/Missions'
F1_TEMPLATE    = os.path.join(PLAN_DIR, 'Fergus1.plan')

MIN_LATERAL_CLEARANCE_M = AGL * math.tan(math.radians(15))   # 10.99 m
CORRIDOR_WIDTH_M        = 2 * AGL                            # 82.0 m
TRANSECT_BAND_M         = 25.0  # +/- 25 m from polyline = "on transect" band


def load_linestring(path):
    with open(path, 'r', encoding='utf-8') as f:
        txt = f.read()
    m = re.search(r'<LineString[\s\S]*?<coordinates>([\s\S]+?)</coordinates>', txt)
    if not m: raise ValueError(f'No LineString in {path}')
    return [tuple(map(float, t.split(',')[:2][::-1])) for t in m.group(1).strip().split()]


def load_launches(path):
    with open(path, 'r', encoding='utf-8') as f:
        txt = f.read()
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


def pt_to_polyline_min_dist_m(pt_lat, pt_lon, line):
    best = float('inf')
    lat0 = pt_lat
    m_lat = 111132.0
    m_lon = 111132.0 * math.cos(math.radians(lat0))
    for i in range(len(line) - 1):
        a, b = line[i], line[i+1]
        ax = (a[1] - pt_lon) * m_lon; ay = (a[0] - pt_lat) * m_lat
        bx = (b[1] - pt_lon) * m_lon; by = (b[0] - pt_lat) * m_lat
        dx = bx - ax; dy = by - ay
        L2 = dx*dx + dy*dy
        if L2 == 0:
            d = math.hypot(ax, ay)
        else:
            t = max(0.0, min(1.0, -(ax*dx + ay*dy) / L2))
            d = math.hypot(ax + t*dx, ay + t*dy)
        if d < best: best = d
    return best


def main():
    highway   = load_linestring(KML_HIGHWAY)
    powerline = load_linestring(KML_POWERLINE)
    launches_all = load_launches(KML_LAUNCHES)
    launches_all.sort(key=lambda L: -L[1])  # east-to-west

    hwy_len_mi = sum(hav(highway[i], highway[i+1]) for i in range(len(highway)-1)) / 1609
    pwr_len_mi = sum(hav(powerline[i], powerline[i+1]) for i in range(len(powerline)-1)) / 1609
    print(f'Highway   polyline: {len(highway)} pts, length-est {hwy_len_mi:.1f} mi')
    print(f'Powerline (ref):    {len(powerline)} pts, length-est {pwr_len_mi:.1f} mi')
    print(f'Launches:  {len(launches_all)} (using all 9 -- no SKIP filter; non-overlap to be reassessed after clearance filter)')
    print(f'\nConfig:')
    print(f'  AGL                  = {AGL} m')
    print(f'  Speed                = {SPEED} m/s')
    print(f'  Tile length          = {TILE_LEN_M} m  (target ~10 min flights at 14 m/s)')
    print(f'  Per-line swath       = {2*AGL:.1f} m')
    print(f'  Combined corridor    = {3*AGL:.1f} m')
    print(f'  Lateral clearance    = {MIN_LATERAL_CLEARANCE_M:.2f} m (15 deg off nadir)')
    print(f'  Inner transect dist  = +/- {AGL/2:.1f} m from highway centerline')
    print(f'  -> Wire VIOLATES sustained transect where its offset from highway is in [{AGL/2 - MIN_LATERAL_CLEARANCE_M:.1f}, {AGL/2 + MIN_LATERAL_CLEARANCE_M:.1f}] m band')

    lats = [p[0] for p in highway] + [L[0] for L in launches_all]
    lons = [p[1] for p in highway] + [L[1] for L in launches_all]
    pad = 0.02
    ensure_dem_for_bbox(min(lats) - pad, max(lats) + pad, min(lons) - pad, max(lons) + pad, resolution_m=10.0)

    template = json.load(open(F1_TEMPLATE))

    pair_reports = []
    for n, (lat_L, lon_L) in enumerate(launches_all, start=1):
        d_proj, meeting_pt, seg_idx, frac = project_onto_centerline(highway, (lat_L, lon_L))
        pl_with_meet, i_meet = insert_meeting_into_centerline(highway, seg_idx, frac, meeting_pt)
        east_path, _ = walk_along(pl_with_meet, i_meet, +1, TILE_LEN_M)
        west_path, _ = walk_along(pl_with_meet, i_meet, -1, TILE_LEN_M)
        east_polyline = douglas_peucker(list(reversed(east_path)), DECIMATE_TOL_M)
        west_polyline = douglas_peucker(list(reversed(west_path)), DECIMATE_TOL_M)

        plan_home = [lat_L, lon_L, terrain_amsl(lat_L, lon_L)]
        meet_amsl = bake_amsl(meeting_pt[0], meeting_pt[1], AGL)

        e_idx = 2 * n + 1   # 3, 5, 7, ..., 19
        w_idx = 2 * n + 2   # 4, 6, 8, ..., 20

        e_plan = build_plan(template, east_polyline, plan_home, AGL,
                            fig8_at_start=True, fig8_at_end=False,
                            fig8_centroid_alt_amsl=meet_amsl,
                            fig8_centroid_latlon=meeting_pt)
        w_plan = build_plan(template, west_polyline, plan_home, AGL,
                            fig8_at_start=False, fig8_at_end=True,
                            fig8_centroid_alt_amsl=meet_amsl,
                            fig8_centroid_latlon=meeting_pt)

        # Override hardcoded CorridorWidth = 140.208 from build_plan -> 82.0 for 41 m AGL
        for plan in (e_plan, w_plan):
            for it in plan['mission']['items']:
                if it.get('complexItemType') == 'CorridorComplexItem':
                    it['CorridorWidth'] = CORRIDOR_WIDTH_M

        e_path = os.path.join(PLAN_DIR, f'Fergus{e_idx}.plan')
        w_path = os.path.join(PLAN_DIR, f'Fergus{w_idx}.plan')
        minified_write(e_path, e_plan)
        minified_write(w_path, w_plan)

        pair_reports.append({
            'pair': n, 'launch_ll': (lat_L, lon_L), 'meeting_ll': meeting_pt,
            'launch_to_meeting_m': d_proj,
            'east_name': f'Fergus{e_idx}.plan', 'west_name': f'Fergus{w_idx}.plan',
        })
        print(f'Pair {n}: Fergus{e_idx}.plan + Fergus{w_idx}.plan -> '
              f'meeting ({meeting_pt[0]:.6f}, {meeting_pt[1]:.6f}) '
              f'launch->meeting {d_proj:.0f} m')

    # VLOS check
    print(f'\n=== VLOS check ===')
    print(f'{"Plan":<22}{"Pts":<6}{"VLOS%":<8}{"Status"}')
    for r in pair_reports:
        for path in [os.path.join(PLAN_DIR, r['east_name']),
                     os.path.join(PLAN_DIR, r['west_name'])]:
            v = check_plan_vlos(path)
            tag = 'OK' if v['los_pct'] >= 99.99 else f"partial {v['worst_below_m']:.1f}m at {v['worst_dist_m']:.0f}m"
            print(f'{os.path.basename(path):<22}{v["path_pts"]:<6}{v["los_pct"]:<8.2f}{tag}')

    # Powerline clearance check
    print(f'\n=== Powerline lateral clearance check (>= {MIN_LATERAL_CLEARANCE_M:.1f} m required from WIRE) ===')
    print(f'(Sustained = path point also within +/- {TRANSECT_BAND_M:.0f} m of highway polyline; brief = off-transect feature)')
    print(f'{"Plan":<22}{"#path":<7}{"#viol":<7}{"#sustained":<12}{"#brief":<8}{"%sustained":<11}{"Min m":<8}{"Verdict"}')
    plan_violation_rows = []
    for r in pair_reports:
        for path in [os.path.join(PLAN_DIR, r['east_name']),
                     os.path.join(PLAN_DIR, r['west_name'])]:
            plan = json.load(open(path))
            fp = extract_flight_path(plan)
            fp_interp = interpolate_path(fp, 10.0)
            total = len(fp_interp)
            n_viol = 0
            n_sustained = 0
            n_brief = 0
            min_dist = float('inf')
            for (la, lo, _amsl) in fp_interp:
                d_wire = pt_to_polyline_min_dist_m(la, lo, powerline)
                if d_wire < min_dist: min_dist = d_wire
                if d_wire < MIN_LATERAL_CLEARANCE_M:
                    n_viol += 1
                    d_hwy = pt_to_polyline_min_dist_m(la, lo, highway)
                    if d_hwy <= TRANSECT_BAND_M:
                        n_sustained += 1
                    else:
                        n_brief += 1
            pct_sustained = 100.0 * n_sustained / total if total else 0.0
            verdict = 'DELETE' if pct_sustained >= 5.0 else ('KEEP' if n_sustained < 10 else 'REVIEW')
            plan_violation_rows.append({
                'plan': os.path.basename(path), 'total': total, 'viol': n_viol,
                'sustained': n_sustained, 'brief': n_brief,
                'pct_sustained': pct_sustained, 'min_m': min_dist, 'verdict': verdict,
            })
            print(f'{os.path.basename(path):<22}{total:<7}{n_viol:<7}{n_sustained:<12}{n_brief:<8}'
                  f'{pct_sustained:<11.2f}{min_dist:<8.1f}{verdict}')

    print('\n=== Summary ===')
    keep = [r for r in plan_violation_rows if r['verdict'] == 'KEEP']
    delete = [r for r in plan_violation_rows if r['verdict'] == 'DELETE']
    review = [r for r in plan_violation_rows if r['verdict'] == 'REVIEW']
    print(f'  KEEP:   {len(keep):>2}  (sustained < 10 path-points = brief-crossing-only)')
    print(f'  REVIEW: {len(review):>2}  (sustained 10-{int(0.05*460)} path-points = borderline)')
    print(f'  DELETE: {len(delete):>2}  (sustained >= 5% of route = wire-near-highway violation)')

    if delete:
        print(f'\n  Files to delete:')
        for r in delete:
            print(f'    {r["plan"]:<22} sustained {r["sustained"]} / {r["total"]} = {r["pct_sustained"]:.1f}%')
    if review:
        print(f'\n  Files to review:')
        for r in review:
            print(f'    {r["plan"]:<22} sustained {r["sustained"]} / {r["total"]} = {r["pct_sustained"]:.1f}%')


if __name__ == '__main__':
    main()
