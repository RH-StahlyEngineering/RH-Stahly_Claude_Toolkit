"""41 m AGL / 14 m/s / line spacing 41 m / polyline = HIGHWAY centerline,
   tile length TRUNCATED to wire-safe segments.

Coverage strategy (Ryan's: "I'm not saying we have to use the entire length"):
  - Polyline = highway centerline (covers the 123 m wide corridor side-to-side)
  - Inner transects at +/- 20.5 m from highway tangent
  - Violation band = wire perpendicular offset |h| in [9.5, 31.5] m (one transect <11 m from wire)
  - Per launch: walk east/west from meeting, STOP as soon as next highway vertex falls in violation band
  - Skip launches whose meeting point itself is in the violation band (figure-8 would cross wire too closely)
  - Skip launches whose total walked length is below MIN_TILE_LEN_M

Result: zero SUSTAINED-transect violations by construction. Brief crossings
(figure-8 at meeting, cross-line, turnaround jog at far end, climb/RTL) accepted
per Rule 3.
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

import generate_fergus_pair1 as gfp1
gfp1.AGL            = 41.0
gfp1.SPEED          = 14.0
gfp1.LINE_SPACING_M = 41.0
gfp1.HALF_LS_M      = 20.5
gfp1.TILE_LEN_M     = 3600.0

from generate_fergus_pair1 import (
    hav, douglas_peucker, build_plan, minified_write,
    AGL, SPEED, FIG8_DURATION, TURNAROUND_M, DECIMATE_TOL_M,
)
from generate_fergus_all_pairs import project_onto_centerline, insert_meeting_into_centerline
from los_check import check_plan_vlos, extract_flight_path, interpolate_path

KML_HIGHWAY    = 'C:/Users/rharbach.STAHLY/Downloads/HighwayCenterline.kml'
KML_POWERLINE  = 'C:/Users/rharbach.STAHLY/Downloads/Hilger-Roy existing line — joined.kml'
KML_LAUNCHES   = 'C:/Users/rharbach.STAHLY/Downloads/HomePoints.kml'
PLAN_DIR       = 'C:/Users/rharbach.STAHLY/Documents/Auterion Mission Control/Missions'
F1_TEMPLATE    = os.path.join(PLAN_DIR, 'Fergus1.plan')

MAX_TILE_LEN_M          = 3600.0
MIN_TILE_LEN_M          = 800.0
MIN_LATERAL_CLEARANCE_M = AGL * math.tan(math.radians(15))    # 10.99 m
TRANSECT_OFFSET_M       = AGL / 2                              # 20.5 m
VIOLATION_LO            = TRANSECT_OFFSET_M - MIN_LATERAL_CLEARANCE_M  # 9.51 m
VIOLATION_HI            = TRANSECT_OFFSET_M + MIN_LATERAL_CLEARANCE_M  # 31.49 m
CORRIDOR_WIDTH_M        = 2 * AGL                              # 82.0 m
TRANSECT_BAND_M         = 25.0


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


def seg_intersect_t(p1, p2, p3, p4):
    x1,y1 = p1; x2,y2 = p2; x3,y3 = p3; x4,y4 = p4
    denom = (x2-x1)*(y4-y3) - (y2-y1)*(x4-x3)
    if abs(denom) < 1e-12: return None
    t = ((x3-x1)*(y4-y3) - (y3-y1)*(x4-x3)) / denom
    u = ((x3-x1)*(y2-y1) - (y3-y1)*(x2-x1)) / denom
    if 0 <= t <= 1 and 0 <= u <= 1: return t
    return None


def wire_offset_at_vertex(hwy_xy, wire_xy, i):
    """Perpendicular offset of wire from highway tangent at vertex i.
    Returns abs(offset) in meters, or +inf if no wire crossing within 600 m."""
    if i <= 0 or i >= len(hwy_xy) - 1:
        # endpoints: use one-sided tangent
        if i == 0:
            dx = hwy_xy[1][0] - hwy_xy[0][0]; dy = hwy_xy[1][1] - hwy_xy[0][1]
        else:
            dx = hwy_xy[-1][0] - hwy_xy[-2][0]; dy = hwy_xy[-1][1] - hwy_xy[-2][1]
    else:
        dx = hwy_xy[i+1][0] - hwy_xy[i-1][0]; dy = hwy_xy[i+1][1] - hwy_xy[i-1][1]
    L = math.hypot(dx, dy)
    if L < 0.01: return float('inf')
    tan_u = (dx/L, dy/L)
    perp = (-tan_u[1], tan_u[0])
    px, py = hwy_xy[i]
    MAX_RAY = 600.0
    pl_end = (px + perp[0]*MAX_RAY, py + perp[1]*MAX_RAY)
    pr_end = (px - perp[0]*MAX_RAY, py - perp[1]*MAX_RAY)
    left_best = float('inf'); right_best = float('inf')
    for j in range(len(wire_xy) - 1):
        a, b = wire_xy[j], wire_xy[j+1]
        tl = seg_intersect_t((px,py), pl_end, a, b)
        if tl is not None:
            d = tl * MAX_RAY
            if d < left_best: left_best = d
        tr = seg_intersect_t((px,py), pr_end, a, b)
        if tr is not None:
            d = tr * MAX_RAY
            if d < right_best: right_best = d
    return min(left_best, right_best)


def is_safe(abs_offset):
    """Wire offset is 'safe' (no sustained transect within 11 m of wire)
    when |h| <= 9.5 m (wire under centerline) OR |h| >= 31.5 m."""
    return abs_offset <= VIOLATION_LO or abs_offset >= VIOLATION_HI


def walk_safe(pts, safe_mask, start_idx, direction, max_dist):
    """Walk along pts from start_idx in direction (+/-1), stopping at the
    first unsafe vertex or when accumulated distance >= max_dist.
    Returns (path_list_including_start, walked_distance_m).
    If start_idx itself is unsafe, returns ([pts[start_idx]], 0)."""
    if not safe_mask[start_idx]:
        return [pts[start_idx]], 0.0
    out = [pts[start_idx]]
    acc = 0.0
    i = start_idx
    while True:
        nxt = i + direction
        if nxt < 0 or nxt >= len(pts): break
        if not safe_mask[nxt]: break
        step = hav(pts[i], pts[nxt])
        if acc + step >= max_dist:
            frac = (max_dist - acc) / step
            lat = pts[i][0] + frac * (pts[nxt][0] - pts[i][0])
            lon = pts[i][1] + frac * (pts[nxt][1] - pts[i][1])
            out.append((lat, lon))
            return out, max_dist
        out.append(pts[nxt])
        acc += step
        i = nxt
    return out, acc


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
        if L2 == 0: d = math.hypot(ax, ay)
        else:
            t = max(0.0, min(1.0, -(ax*dx + ay*dy) / L2))
            d = math.hypot(ax + t*dx, ay + t*dy)
        if d < best: best = d
    return best


def delete_stale_fergus_plans():
    """Delete any existing Fergus3..Fergus20.plan files so we start clean."""
    for n in range(3, 21):
        p = os.path.join(PLAN_DIR, f'Fergus{n}.plan')
        if os.path.exists(p):
            os.remove(p)


def main():
    highway   = load_linestring(KML_HIGHWAY)
    powerline = load_linestring(KML_POWERLINE)
    launches_all = load_launches(KML_LAUNCHES)
    launches_all.sort(key=lambda L: -L[1])  # east-to-west

    print(f'Highway   polyline: {len(highway)} pts, {sum(hav(highway[i], highway[i+1]) for i in range(len(highway)-1))/1609:.1f} mi')
    print(f'Powerline ref:      {len(powerline)} pts, {sum(hav(powerline[i], powerline[i+1]) for i in range(len(powerline)-1))/1609:.1f} mi')
    print(f'\nConfig:')
    print(f'  AGL                  = {AGL} m')
    print(f'  Speed                = {SPEED} m/s')
    print(f'  Max tile length      = {MAX_TILE_LEN_M} m (target ~7 min at 14 m/s)')
    print(f'  Min tile length      = {MIN_TILE_LEN_M} m (skip launches below)')
    print(f'  Inner transect at    = +/- {TRANSECT_OFFSET_M:.1f} m from polyline (= highway centerline)')
    print(f'  Lateral floor        = {MIN_LATERAL_CLEARANCE_M:.2f} m (15 deg off nadir)')
    print(f'  Violation band       = wire |h| in [{VIOLATION_LO:.1f}, {VIOLATION_HI:.1f}] m')

    # Project highway + wire to local meters
    ref_lat = sum(p[0] for p in highway) / len(highway)
    ref_lon = sum(p[1] for p in highway) / len(highway)
    m_lat = 111132.0
    m_lon = 111132.0 * math.cos(math.radians(ref_lat))
    def to_xy(lat, lon):
        return ((lon - ref_lon) * m_lon, (lat - ref_lat) * m_lat)
    hwy_xy = [to_xy(*p) for p in highway]
    wire_xy = [to_xy(*p) for p in powerline]

    # Compute safe_mask for each highway vertex
    print(f'\nComputing safe_mask for {len(highway)} highway vertices...')
    safe_mask = [is_safe(wire_offset_at_vertex(hwy_xy, wire_xy, i)) for i in range(len(highway))]
    n_safe = sum(safe_mask)
    print(f'  {n_safe}/{len(highway)} ({100*n_safe/len(highway):.1f}%) vertices are wire-safe')

    # Print contiguous safe regions (as a sanity check)
    print(f'\nContiguous safe regions along highway (east-to-west, len > {MIN_TILE_LEN_M:.0f} m):')
    i = 0
    safe_regions = []
    while i < len(highway):
        if not safe_mask[i]:
            i += 1; continue
        j = i
        while j < len(highway) and safe_mask[j]: j += 1
        # safe run from i to j-1
        run_len = sum(hav(highway[k], highway[k+1]) for k in range(i, j-1)) if j > i+1 else 0
        if run_len >= MIN_TILE_LEN_M:
            safe_regions.append((i, j-1, run_len, highway[i], highway[j-1]))
            print(f'  vertices {i:>4} -> {j-1:>4}  length {run_len/1000:>5.2f} km  '
                  f'({highway[i][0]:.4f},{highway[i][1]:.4f}) -> ({highway[j-1][0]:.4f},{highway[j-1][1]:.4f})')
        i = j

    # Warm DEM for full bbox
    lats = [p[0] for p in highway] + [L[0] for L in launches_all]
    lons = [p[1] for p in highway] + [L[1] for L in launches_all]
    pad = 0.02
    ensure_dem_for_bbox(min(lats) - pad, max(lats) + pad, min(lons) - pad, max(lons) + pad, resolution_m=10.0)

    template = json.load(open(F1_TEMPLATE))

    # Wipe stale plans
    delete_stale_fergus_plans()

    pair_reports = []
    next_idx = 3
    print(f'\n=== Generating plans for {len(launches_all)} launches ===')
    for n, (lat_L, lon_L) in enumerate(launches_all, start=1):
        d_proj, meeting_pt, seg_idx, frac = project_onto_centerline(highway, (lat_L, lon_L))
        pl_with_meet, i_meet = insert_meeting_into_centerline(highway, seg_idx, frac, meeting_pt)
        # Recompute safe_mask for the inserted-meet polyline
        meet_xy = to_xy(*meeting_pt)
        # Approximate meet's safe: project meeting_pt onto highway segment seg_idx, use vertex i_meet's safe
        # Better: directly compute wire offset at meeting_pt
        if i_meet > 0 and i_meet < len(pl_with_meet) - 1:
            dx = pl_with_meet[i_meet+1][1] - pl_with_meet[i_meet-1][1]
            dy = pl_with_meet[i_meet+1][0] - pl_with_meet[i_meet-1][0]
        elif i_meet == 0:
            dx = pl_with_meet[1][1] - pl_with_meet[0][1]; dy = pl_with_meet[1][0] - pl_with_meet[0][0]
        else:
            dx = pl_with_meet[-1][1] - pl_with_meet[-2][1]; dy = pl_with_meet[-1][0] - pl_with_meet[-2][0]
        # Convert to local meters for perpendicular ray
        dxm = dx * m_lon; dym = dy * m_lat
        L = math.hypot(dxm, dym)
        if L < 0.01:
            meet_safe = False
        else:
            tan_u = (dxm/L, dym/L); perp = (-tan_u[1], tan_u[0])
            MAX_RAY = 600.0
            pl_e = (meet_xy[0] + perp[0]*MAX_RAY, meet_xy[1] + perp[1]*MAX_RAY)
            pr_e = (meet_xy[0] - perp[0]*MAX_RAY, meet_xy[1] - perp[1]*MAX_RAY)
            left_best = float('inf'); right_best = float('inf')
            for j in range(len(wire_xy)-1):
                a, b = wire_xy[j], wire_xy[j+1]
                tl = seg_intersect_t(meet_xy, pl_e, a, b)
                if tl is not None and tl*MAX_RAY < left_best: left_best = tl*MAX_RAY
                tr = seg_intersect_t(meet_xy, pr_e, a, b)
                if tr is not None and tr*MAX_RAY < right_best: right_best = tr*MAX_RAY
            meet_offset = min(left_best, right_best)
            meet_safe = is_safe(meet_offset)

        # Build a safe_mask for pl_with_meet (insert at i_meet)
        if frac <= 1e-9:
            pl_safe = safe_mask[:]
        elif frac >= 1.0 - 1e-9:
            pl_safe = safe_mask[:]
        else:
            pl_safe = safe_mask[:seg_idx+1] + [meet_safe] + safe_mask[seg_idx+1:]

        if not meet_safe:
            print(f'L{n}: meeting in violation band (|h|={meet_offset:.1f} m) -> SKIP')
            continue

        east_path, east_dist = walk_safe(pl_with_meet, pl_safe, i_meet, +1, MAX_TILE_LEN_M)
        west_path, west_dist = walk_safe(pl_with_meet, pl_safe, i_meet, -1, MAX_TILE_LEN_M)

        if east_dist < MIN_TILE_LEN_M and west_dist < MIN_TILE_LEN_M:
            print(f'L{n}: both tiles too short (E={east_dist:.0f} m, W={west_dist:.0f} m) -> SKIP')
            continue

        # If one tile is too short, still pair them; AMC will fly both regardless
        plan_home = [lat_L, lon_L, terrain_amsl(lat_L, lon_L)]
        meet_amsl = bake_amsl(meeting_pt[0], meeting_pt[1], AGL)

        e_idx = next_idx; w_idx = next_idx + 1
        next_idx += 2

        if east_dist >= MIN_TILE_LEN_M:
            east_polyline = douglas_peucker(list(reversed(east_path)), DECIMATE_TOL_M)
            e_plan = build_plan(template, east_polyline, plan_home, AGL,
                                fig8_at_start=True, fig8_at_end=False,
                                fig8_centroid_alt_amsl=meet_amsl,
                                fig8_centroid_latlon=meeting_pt)
            for it in e_plan['mission']['items']:
                if it.get('complexItemType') == 'CorridorComplexItem':
                    it['CorridorWidth'] = CORRIDOR_WIDTH_M
            e_path = os.path.join(PLAN_DIR, f'Fergus{e_idx}.plan')
            minified_write(e_path, e_plan)
            wrote_east = True
        else:
            wrote_east = False
            print(f'L{n}: east tile too short ({east_dist:.0f} m), skipping east plan only')

        if west_dist >= MIN_TILE_LEN_M:
            west_polyline = douglas_peucker(list(reversed(west_path)), DECIMATE_TOL_M)
            w_plan = build_plan(template, west_polyline, plan_home, AGL,
                                fig8_at_start=False, fig8_at_end=True,
                                fig8_centroid_alt_amsl=meet_amsl,
                                fig8_centroid_latlon=meeting_pt)
            for it in w_plan['mission']['items']:
                if it.get('complexItemType') == 'CorridorComplexItem':
                    it['CorridorWidth'] = CORRIDOR_WIDTH_M
            w_path = os.path.join(PLAN_DIR, f'Fergus{w_idx}.plan')
            minified_write(w_path, w_plan)
            wrote_west = True
        else:
            wrote_west = False
            print(f'L{n}: west tile too short ({west_dist:.0f} m), skipping west plan only')

        if wrote_east or wrote_west:
            pair_reports.append({
                'launch_idx': n, 'launch_ll': (lat_L, lon_L),
                'meeting_ll': meeting_pt, 'launch_to_meeting_m': d_proj,
                'east_name': f'Fergus{e_idx}.plan' if wrote_east else None,
                'east_dist': east_dist if wrote_east else 0,
                'west_name': f'Fergus{w_idx}.plan' if wrote_west else None,
                'west_dist': west_dist if wrote_west else 0,
            })
            both = (f'{f"Fergus{e_idx}.plan" if wrote_east else "(none)":<14} + '
                    f'{f"Fergus{w_idx}.plan" if wrote_west else "(none)":<14}')
            print(f'L{n}: {both}  meeting=({meeting_pt[0]:.5f},{meeting_pt[1]:.5f})  '
                  f'E={east_dist:.0f} m, W={west_dist:.0f} m')

    if not pair_reports:
        print('\n  NO plans generated. All launches dropped.')
        return

    # VLOS + clearance verification
    print(f'\n=== VLOS check ===')
    print(f'{"Plan":<22}{"Pts":<6}{"VLOS%":<8}{"Status"}')
    vlos_fails = []
    for r in pair_reports:
        for path_name in [r['east_name'], r['west_name']]:
            if not path_name: continue
            path = os.path.join(PLAN_DIR, path_name)
            v = check_plan_vlos(path)
            tag = 'OK' if v['los_pct'] >= 99.99 else f"partial {v['worst_below_m']:.1f}m at {v['worst_dist_m']:.0f}m"
            if v['los_pct'] < 99.99: vlos_fails.append((path_name, v['los_pct']))
            print(f'{path_name:<22}{v["path_pts"]:<6}{v["los_pct"]:<8.2f}{tag}')

    print(f'\n=== Powerline lateral clearance check (>= {MIN_LATERAL_CLEARANCE_M:.1f} m required from WIRE) ===')
    print(f'(Sustained = path point within +/- {TRANSECT_BAND_M:.0f} m of highway polyline AND violating; brief = off-transect)')
    print(f'{"Plan":<22}{"#path":<7}{"#viol":<7}{"#sustained":<12}{"#brief":<8}{"Min m":<8}{"Verdict"}')
    sustained_fails = []
    for r in pair_reports:
        for path_name in [r['east_name'], r['west_name']]:
            if not path_name: continue
            path = os.path.join(PLAN_DIR, path_name)
            plan = json.load(open(path))
            fp_interp = interpolate_path(extract_flight_path(plan), 10.0)
            total = len(fp_interp)
            n_viol = 0; n_sustained = 0; n_brief = 0
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
            verdict = 'OK' if n_sustained == 0 else f'{n_sustained} sustained'
            if n_sustained > 0: sustained_fails.append((path_name, n_sustained))
            print(f'{path_name:<22}{total:<7}{n_viol:<7}{n_sustained:<12}{n_brief:<8}'
                  f'{min_dist:<8.1f}{verdict}')

    print('\n=== Summary ===')
    total_plans = sum(1 for r in pair_reports for nm in (r['east_name'], r['west_name']) if nm)
    print(f'  {total_plans} plans generated across {len(pair_reports)} launches')
    if not sustained_fails:
        print(f'  All {total_plans} plans clear of sustained-transect violations.')
    else:
        print(f'  {len(sustained_fails)} plan(s) have SUSTAINED violations (should be zero by construction!):')
        for name, n_s in sustained_fails:
            print(f'    {name:<22} {n_s} sustained')
    if vlos_fails:
        print(f'\n  {len(vlos_fails)} plan(s) have VLOS issues (will need launch relocation):')
        for name, pct in vlos_fails: print(f'    {name:<22} VLOS {pct:.2f}%')
    else:
        print(f'\n  All {total_plans} plans pass VLOS.')

    total_e_km = sum(r['east_dist'] for r in pair_reports) / 1000
    total_w_km = sum(r['west_dist'] for r in pair_reports) / 1000
    print(f'\n  Total east-tile corridor:  {total_e_km:.2f} km')
    print(f'  Total west-tile corridor:  {total_w_km:.2f} km')
    print(f'  Total corridor coverage:   {total_e_km + total_w_km:.2f} km of {sum(hav(highway[i], highway[i+1]) for i in range(len(highway)-1))/1000:.2f} km '
          f'({100*(total_e_km + total_w_km)/(sum(hav(highway[i], highway[i+1]) for i in range(len(highway)-1))/1000):.1f}%)')


if __name__ == '__main__':
    main()
