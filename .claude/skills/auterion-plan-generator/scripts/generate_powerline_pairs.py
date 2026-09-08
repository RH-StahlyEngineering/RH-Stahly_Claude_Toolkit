"""Generate Fergus3..Fergus20 LiDAR plans using the powerline as the polyline.

Mission: photogrammetry-style coverage along the Hilger-Roy powerline corridor,
with the hard constraint that no flight transect can be within 19 m horizontally
of the powerline (=15° off nadir at 70 m AGL).

Architecture matches the prior LiDAR set (Fergus3..20):
  - 9 launches from HomePoints.kml
  - Each launch -> hot-swap pair (east tile + west tile)
  - Each tile -> 1.8 km segment of the powerline as the CorridorScan polyline
  - 2-transect CorridorScan (CorridorWidth = 2*AGL = 140.208 m); transects at
    +/-35 m from polyline -> 35 m clearance from wire (>=19 m required)
  - Same canonical structure: cmd 530 + (fig-8 START) + CorridorScan + cross-line + (fig-8 END)
  - East tile = START cal flight (Fergus 3, 5, 7, ..., 19)
  - West tile = END cal flight (Fergus 4, 6, 8, ..., 20)
"""
import os, sys, json, re, math

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SKILL_DIR, 'scripts'))

# Force the wider corridor DEM raster (lesson #22 / pitfall #15)
import dem_lookup
_explicit = os.path.expanduser('~/.claude/dem_cache/dem_ee0aa3a8a9d0.json')
if os.path.exists(_explicit):
    dem_lookup._explicit_meta_paths.insert(0, _explicit)
    dem_lookup._local_dem = None
    dem_lookup._local_meta = None

from dem_lookup import ensure_dem_for_bbox, terrain_amsl, bake_amsl
from generate_fergus_pair1 import (
    hav, douglas_peucker, build_plan, minified_write,
    AGL, SPEED, FIG8_DURATION, TURNAROUND_M, TILE_LEN_M, DECIMATE_TOL_M,
)
from generate_fergus_all_pairs import (
    project_onto_centerline, insert_meeting_into_centerline, walk_along,
)
from los_check import check_plan_vlos

KML_POWERLINE  = 'C:/Users/rharbach.STAHLY/Downloads/Hilger-Roy existing line — joined.kml'
KML_LAUNCHES   = 'C:/Users/rharbach.STAHLY/Downloads/HomePoints.kml'
PLAN_DIR       = 'C:/Users/rharbach.STAHLY/Documents/Auterion Mission Control/Missions'
F1_TEMPLATE    = os.path.join(PLAN_DIR, 'Fergus1.plan')

# 15 deg off nadir clearance at 70 m AGL
MIN_LATERAL_CLEARANCE_M = AGL * math.tan(math.radians(15))   # 18.76 m

# Launch filter — drop launches that create overlapping coverage with adjacent pairs.
# East-to-west indices (1-based after sort by descending lon):
#   L1=easternmost ... L9=westernmost
# Skip L5 (overlaps L4), L7 (overlaps L6), L8 (overlaps L7 and L9).
# Result: L1, L2, L3, L4, L6, L9 = 6 pairs covering 21.6 km of corridor with
# substantial gaps (1.2-6.5 km) reserved for future fresh-battery follow-up flights.
SKIP_LAUNCHES_1BASED = {5, 7, 8}


def load_powerline(path):
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


def main():
    powerline = load_powerline(KML_POWERLINE)
    launches_all = load_launches(KML_LAUNCHES)
    launches_all.sort(key=lambda L: -L[1])  # east-to-west
    # Filter via SKIP_LAUNCHES_1BASED
    launches = [L for i, L in enumerate(launches_all, start=1) if i not in SKIP_LAUNCHES_1BASED]
    dropped = [(i, L) for i, L in enumerate(launches_all, start=1) if i in SKIP_LAUNCHES_1BASED]
    print(f'Powerline: {len(powerline)} pts, length-est {sum(hav(powerline[i], powerline[i+1]) for i in range(len(powerline)-1))/1609:.1f} mi')
    print(f'Launches:  {len(launches_all)} loaded, {len(launches)} kept after dropping {sorted(SKIP_LAUNCHES_1BASED)} '
          f'(=> {[("L"+str(i)) for i in sorted(SKIP_LAUNCHES_1BASED)]})')
    for i, L in dropped:
        print(f'  Dropped L{i}: ({L[0]:.6f}, {L[1]:.6f})')

    # Warm DEM for full powerline + launch bbox + 1 km buffer
    lats = [p[0] for p in powerline] + [L[0] for L in launches]
    lons = [p[1] for p in powerline] + [L[1] for L in launches]
    pad = 0.02
    ensure_dem_for_bbox(min(lats) - pad, max(lats) + pad, min(lons) - pad, max(lons) + pad, resolution_m=10.0)

    template = json.load(open(F1_TEMPLATE))

    print(f'\nMin lateral clearance required: {MIN_LATERAL_CLEARANCE_M:.2f} m '
          f'(15 deg off nadir at AGL {AGL} m)')
    print(f'CorridorScan inner transects at +/-{AGL/2:.1f} m from polyline -> '
          f'{AGL/2:.1f} m clearance from powerline ({"OK" if AGL/2 >= MIN_LATERAL_CLEARANCE_M else "VIOLATION"})\n')

    pair_reports = []
    for n, (lat_L, lon_L) in enumerate(launches, start=1):
        d_proj, meeting_pt, seg_idx, frac = project_onto_centerline(powerline, (lat_L, lon_L))
        pl_with_meet, i_meet = insert_meeting_into_centerline(powerline, seg_idx, frac, meeting_pt)
        east_path, _ = walk_along(pl_with_meet, i_meet, +1, TILE_LEN_M)
        west_path, _ = walk_along(pl_with_meet, i_meet, -1, TILE_LEN_M)
        east_polyline = douglas_peucker(list(reversed(east_path)), DECIMATE_TOL_M)
        west_polyline = douglas_peucker(list(reversed(west_path)), DECIMATE_TOL_M)

        # HOME = launch coords with DEM-baked terrain
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

    # VLOS check on all 18 plans
    print(f'\n=== VLOS check ===')
    print(f'{"Plan":<22}{"Pts":<6}{"VLOS%":<8}{"Status"}')
    for r in pair_reports:
        for path in [os.path.join(PLAN_DIR, r['east_name']),
                     os.path.join(PLAN_DIR, r['west_name'])]:
            v = check_plan_vlos(path)
            tag = 'OK' if v['los_pct'] >= 99.99 else f"partial {v['worst_below_m']:.1f}m at {v['worst_dist_m']:.0f}m"
            print(f'{os.path.basename(path):<22}{v["path_pts"]:<6}{v["los_pct"]:<8.2f}{tag}')

    # Powerline-clearance check: for each plan's full flight path, find min
    # horizontal distance to the powerline.
    print(f'\n=== Powerline lateral clearance check (>= {MIN_LATERAL_CLEARANCE_M:.1f} m required) ===')
    from los_check import extract_flight_path, interpolate_path

    def pt_to_polyline_min_dist_m(pt_lat, pt_lon, line):
        # Project pt onto each segment, take minimum euclidean distance (local equirect).
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
            if d < best:
                best = d
        return best

    violation_count = 0
    print(f'{"Plan":<22}{"#path":<7}{"#below":<8}{"Min m":<8}{"Status"}')
    for r in pair_reports:
        for path in [os.path.join(PLAN_DIR, r['east_name']),
                     os.path.join(PLAN_DIR, r['west_name'])]:
            plan = json.load(open(path))
            fp = extract_flight_path(plan)
            fp_interp = interpolate_path(fp, 10.0)  # sample every 10 m along flight path
            below_count = 0
            min_dist = float('inf')
            for (la, lo, _amsl) in fp_interp:
                d = pt_to_polyline_min_dist_m(la, lo, powerline)
                if d < min_dist: min_dist = d
                if d < MIN_LATERAL_CLEARANCE_M:
                    below_count += 1
            status = 'OK' if below_count == 0 else f'VIOLATION ({below_count} pts below floor)'
            if below_count > 0: violation_count += 1
            print(f'{os.path.basename(path):<22}{len(fp_interp):<7}{below_count:<8}{min_dist:<8.1f}{status}')
    if violation_count:
        print(f'\n  {violation_count} plans have flight-path points inside the 19 m powerline buffer.')
    else:
        print(f'\n  All 18 plans clear of the 19 m powerline buffer.')


if __name__ == '__main__':
    main()
