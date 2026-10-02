"""41 m AGL / 14 m/s / 3.6 km tiles / polyline = WIRE.

Geometry guarantees zero sustained-transect clearance violations:
  - Inner transects at +/- 20.5 m from wire (polyline)
  - Lateral clearance from wire = 20.5 m
  - Floor at 41 m AGL = 41 * tan(15 deg) = 10.99 m
  - 20.5 m > 10.99 m -> all sustained transects clear by construction

Only the 4 accepted brief-crossing categories may produce path points within
the 11 m floor:
  - figure-8 at meeting point (the centroid is ON the wire by construction)
  - cross-line (crosses wire perpendicularly at the meeting end)
  - turnaround jog at the far end (perpendicular hop between transects)
  - climb / RTL transit from HOME to polyline endpoint

Tile length = 3.6 km targets ~10 min flights at 14 m/s.
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

# Patch module-level constants BEFORE importing functions
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

KML_POWERLINE  = 'C:/Users/rharbach.STAHLY/Downloads/Hilger-Roy existing line — joined.kml'
KML_LAUNCHES   = 'C:/Users/rharbach.STAHLY/Downloads/HomePoints.kml'
PLAN_DIR       = 'C:/Users/rharbach.STAHLY/Documents/Auterion Mission Control/Missions'
F1_TEMPLATE    = os.path.join(PLAN_DIR, 'Fergus1.plan')

MIN_LATERAL_CLEARANCE_M = AGL * math.tan(math.radians(15))   # 10.99 m
CORRIDOR_WIDTH_M        = 2 * AGL                            # 82.0 m
TRANSECT_BAND_M         = 25.0  # +/- 25 m from polyline = "on transect"


def load_linestring(path):
    txt = open(path, 'r', encoding='utf-8').read()
    m = re.search(r'<LineString[\s\S]*?<coordinates>([\s\S]+?)</coordinates>', txt)
    if not m: raise ValueError(f'No LineString in {path}')
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


def pt_to_polyline_min_dist_m(pt_lat, pt_lon, line):
    best = float('inf')
    m_lat = 111132.0
    m_lon = 111132.0 * math.cos(math.radians(pt_lat))
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
    powerline = load_linestring(KML_POWERLINE)
    launches_all = load_launches(KML_LAUNCHES)
    launches_all.sort(key=lambda L: -L[1])  # east-to-west

    pwr_len_mi = sum(hav(powerline[i], powerline[i+1]) for i in range(len(powerline)-1)) / 1609
    print(f'Powerline polyline: {len(powerline)} pts, length-est {pwr_len_mi:.1f} mi')
    print(f'Launches:  {len(launches_all)} (using all 9)')
    print(f'\nConfig:')
    print(f'  AGL                  = {AGL} m')
    print(f'  Speed                = {SPEED} m/s')
    print(f'  Tile length          = {TILE_LEN_M} m')
    print(f'  Per-line swath       = {2*AGL:.1f} m')
    print(f'  Combined corridor    = {3*AGL:.1f} m (centered on WIRE)')
    print(f'  Lateral clearance    = {MIN_LATERAL_CLEARANCE_M:.2f} m (15 deg off nadir)')
    print(f'  Inner transect dist  = +/- {AGL/2:.1f} m from WIRE -> {AGL/2:.1f} m clearance (CLEAR by construction)\n')

    lats = [p[0] for p in powerline] + [L[0] for L in launches_all]
    lons = [p[1] for p in powerline] + [L[1] for L in launches_all]
    pad = 0.02
    ensure_dem_for_bbox(min(lats) - pad, max(lats) + pad, min(lons) - pad, max(lons) + pad, resolution_m=10.0)

    template = json.load(open(F1_TEMPLATE))

    pair_reports = []
    for n, (lat_L, lon_L) in enumerate(launches_all, start=1):
        d_proj, meeting_pt, seg_idx, frac = project_onto_centerline(powerline, (lat_L, lon_L))
        pl_with_meet, i_meet = insert_meeting_into_centerline(powerline, seg_idx, frac, meeting_pt)
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

        # Override hardcoded CorridorWidth = 140.208 from build_plan -> 82.0
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
    vlos_fails = []
    for r in pair_reports:
        for path in [os.path.join(PLAN_DIR, r['east_name']),
                     os.path.join(PLAN_DIR, r['west_name'])]:
            v = check_plan_vlos(path)
            tag = 'OK' if v['los_pct'] >= 99.99 else f"partial {v['worst_below_m']:.1f}m at {v['worst_dist_m']:.0f}m"
            if v['los_pct'] < 99.99:
                vlos_fails.append((os.path.basename(path), v['los_pct']))
            print(f'{os.path.basename(path):<22}{v["path_pts"]:<6}{v["los_pct"]:<8.2f}{tag}')

    # Clearance check
    print(f'\n=== Powerline lateral clearance check (>= {MIN_LATERAL_CLEARANCE_M:.1f} m required from WIRE) ===')
    print(f'{"Plan":<22}{"#path":<7}{"#viol":<7}{"#sustained":<12}{"#brief":<8}{"%sustained":<11}{"Min m":<8}{"Verdict"}')
    clearance_fails = []
    for r in pair_reports:
        for path in [os.path.join(PLAN_DIR, r['east_name']),
                     os.path.join(PLAN_DIR, r['west_name'])]:
            plan = json.load(open(path))
            fp = extract_flight_path(plan)
            fp_interp = interpolate_path(fp, 10.0)
            total = len(fp_interp)
            n_viol = 0; n_sustained = 0; n_brief = 0
            min_dist = float('inf')
            for (la, lo, _amsl) in fp_interp:
                d_wire = pt_to_polyline_min_dist_m(la, lo, powerline)
                if d_wire < min_dist: min_dist = d_wire
                if d_wire < MIN_LATERAL_CLEARANCE_M:
                    n_viol += 1
                    # Classify: on-transect (= sustained) if also within +/- TRANSECT_BAND_M of polyline (= wire here)
                    if d_wire <= TRANSECT_BAND_M:
                        # within polyline buffer, but distinguish brief crossings:
                        # brief = figure-8/cross-line points cluster near the polyline endpoint (the meeting end)
                        # Simple heuristic: sustained if this point is on or near a polyline interior segment
                        # (not within ~150m of meeting end)
                        d_to_meeting = pt_to_polyline_min_dist_m(la, lo,
                            [r['meeting_ll'], r['meeting_ll']])  # degenerate; use direct dist
                        meet_lat, meet_lon = r['meeting_ll']
                        m_lat_local = 111132.0
                        m_lon_local = 111132.0 * math.cos(math.radians(la))
                        d_to_meeting = math.hypot(
                            (lo - meet_lon) * m_lon_local,
                            (la - meet_lat) * m_lat_local)
                        if d_to_meeting < 200:
                            n_brief += 1   # likely figure-8 / cross-line at meeting end
                        else:
                            n_sustained += 1
                    else:
                        n_brief += 1  # off the polyline = turnaround / climb / RTL
            pct_sustained = 100.0 * n_sustained / total if total else 0.0
            verdict = 'OK' if n_sustained == 0 else f'{n_sustained} sustained'
            if n_sustained > 0:
                clearance_fails.append((os.path.basename(path), n_sustained, pct_sustained))
            print(f'{os.path.basename(path):<22}{total:<7}{n_viol:<7}{n_sustained:<12}{n_brief:<8}'
                  f'{pct_sustained:<11.2f}{min_dist:<8.1f}{verdict}')

    print('\n=== Summary ===')
    if not clearance_fails:
        print(f'  All {2*len(pair_reports)} plans clear of sustained-transect violations (brief crossings accepted per Rule 3).')
    else:
        print(f'  {len(clearance_fails)} plan(s) have SUSTAINED violations:')
        for name, n_s, pct in clearance_fails:
            print(f'    {name:<22} {n_s} sustained ({pct:.1f}%)')
    if vlos_fails:
        print(f'\n  {len(vlos_fails)} plan(s) have VLOS issues:')
        for name, pct in vlos_fails:
            print(f'    {name:<22} VLOS {pct:.2f}%')
    else:
        print(f'\n  All {2*len(pair_reports)} plans pass VLOS.')


if __name__ == '__main__':
    main()
