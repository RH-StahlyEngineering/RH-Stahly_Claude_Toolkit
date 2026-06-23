"""Generate all Fergus pairs from launches in HomePoints.kml.

For each Launch placemark in HomePoints.kml, generate one hot-swap pair:
  - meeting point = nearest centerline vertex to the launch
  - east tile (1.8 km east of meeting along centerline) = START cal flight
  - west tile (1.8 km west of meeting along centerline) = END cal flight
  - HOME = launch coords (DEM-baked ground AMSL)

Numbering is east-to-west:
  Pair 1 (easternmost) = Fergus3 (east tile) + Fergus4 (west tile)
  Pair 2              = Fergus5 + Fergus6
  ...
  Pair 9 (westernmost) = Fergus19 + Fergus20

Reuses the AGL/terrain-follow + Items-population logic from generate_fergus_pair1.
"""
import json, math, os, re, sys, hashlib

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SKILL_DIR, 'scripts'))
from figure8 import fig8_waypoints
from dem_lookup import ensure_dem_for_bbox, terrain_amsl, bake_amsl
from generate_fergus_pair1 import (
    load_centerline, hav, nearest_idx, douglas_peucker,
    build_corridor_inner_items, build_cross_line,
    deepcopy_json, minified_write, build_plan,
    AGL, SPEED, FIG8_DURATION, TURNAROUND_M,
    LINE_SPACING_M, HALF_LS_M, DECIMATE_TOL_M, TILE_LEN_M,
)

KML_CENTERLINE = 'C:/Users/rharbach.STAHLY/Downloads/HighwayCenterline.kml'
KML_LAUNCHES   = 'C:/Users/rharbach.STAHLY/Downloads/HomePoints.kml'
F1_TEMPLATE    = 'C:/Users/rharbach.STAHLY/Documents/Auterion Mission Control/Missions/Fergus1.plan'
OUT_DIR        = 'C:/Users/rharbach.STAHLY/Documents/Auterion Mission Control/Missions'

def load_launches(path):
    with open(path, 'r', encoding='utf-8') as f:
        txt = f.read()
    pms = re.findall(r'<Placemark[^>]*>([\s\S]*?)</Placemark>', txt)
    out = []
    for pm in pms:
        nm_m = re.search(r'<name>([\s\S]*?)</name>', pm)
        pt_m = re.search(r'<Point[\s\S]*?<coordinates>([\s\S]*?)</coordinates>', pm)
        if not (nm_m and pt_m): continue
        name = nm_m.group(1).strip()
        if 'launch' not in name.lower(): continue
        coord = pt_m.group(1).strip().split(',')
        lon, lat = float(coord[0]), float(coord[1])
        out.append((lat, lon))
    return out

def project_onto_centerline(pts, target):
    """Return (lat, lon, segment_idx, fraction) for the nearest point on the
    polyline pts to target. Uses local equirectangular projection per segment.
    Much more accurate than nearest_idx when KML has long straight segments."""
    best = (float('inf'), None, 0, 0.0)
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i+1]
        lat0 = (a[0] + b[0]) / 2
        m_lat = 111132.0
        m_lon = 111132.0 * math.cos(math.radians(lat0))
        ax = (a[1] - target[1]) * m_lon; ay = (a[0] - target[0]) * m_lat
        bx = (b[1] - target[1]) * m_lon; by = (b[0] - target[0]) * m_lat
        seg_x = bx - ax; seg_y = by - ay
        L2 = seg_x*seg_x + seg_y*seg_y
        if L2 == 0:
            t = 0.0; proj = a
        else:
            t = -(ax*seg_x + ay*seg_y) / L2
            t = max(0.0, min(1.0, t))
            proj = (a[0] + t * (b[0] - a[0]),
                    a[1] + t * (b[1] - a[1]))
        d = hav(proj, target)
        if d < best[0]:
            best = (d, proj, i, t)
    return best  # (distance_m, (lat,lon), seg_idx, fraction)

def insert_meeting_into_centerline(pts, seg_idx, frac, meeting_pt):
    """Return a new centerline list with meeting_pt inserted between seg_idx and seg_idx+1,
    and the index of meeting_pt in the new list. If frac is 0 or 1, snap to the
    existing vertex instead of inserting."""
    if frac <= 1e-9:
        return pts, seg_idx
    if frac >= 1.0 - 1e-9:
        return pts, seg_idx + 1
    new_pts = pts[:seg_idx+1] + [meeting_pt] + pts[seg_idx+1:]
    return new_pts, seg_idx + 1

def walk_along(pts, start_idx, direction, target_dist):
    """Walk along the centerline from pts[start_idx] in direction (+1 = forward,
    -1 = backward) for target_dist meters. Returns the path including
    pts[start_idx] at index 0 and an interpolated endpoint at the target distance.
    If the path runs off the end of pts, returns whatever was walked."""
    out = [pts[start_idx]]
    acc = 0.0
    i = start_idx
    while True:
        nxt = i + direction
        if nxt < 0 or nxt >= len(pts): break
        step = hav(pts[i], pts[nxt])
        if acc + step >= target_dist:
            frac = (target_dist - acc) / step
            lat = pts[i][0] + frac * (pts[nxt][0] - pts[i][0])
            lon = pts[i][1] + frac * (pts[nxt][1] - pts[i][1])
            out.append((lat, lon))
            return out, True
        out.append(pts[nxt])
        acc += step
        i = nxt
    return out, False

def main():
    centerline = load_centerline(KML_CENTERLINE)
    launches   = load_launches(KML_LAUNCHES)
    # Sort east-to-west (descending longitude); Pair 1 = easternmost
    launches.sort(key=lambda L: -L[1])
    print(f'Loaded {len(launches)} launches (sorted east-to-west):')
    for i, L in enumerate(launches):
        print(f'  Pair {i+1}: Launch at lat={L[0]:.6f}, lon={L[1]:.6f}')

    # Warm DEM cache: bbox covers all launches + tile reach
    pad = 0.02  # ~2 km padding
    lats = [L[0] for L in launches]
    lons = [L[1] for L in launches]
    bbox = (min(lats)-pad, max(lats)+pad, min(lons)-pad, max(lons)+pad)
    print(f'\nDEM bbox: lat [{bbox[0]:.4f},{bbox[1]:.4f}] lon [{bbox[2]:.4f},{bbox[3]:.4f}]')
    ensure_dem_for_bbox(*bbox, resolution_m=10.0)

    # Load Fergus1 template
    with open(F1_TEMPLATE, 'r', encoding='utf-8') as f:
        template = json.load(f)

    # For each pair: compute meeting point (= nearest point on KML SEGMENT to Launch),
    # walk east 1.8 km and west 1.8 km along KML from that meeting, build the two plans.
    report = []
    for n, (lat_L, lon_L) in enumerate(launches, start=1):
        d_proj, meeting_pt, seg_idx, frac = project_onto_centerline(centerline, (lat_L, lon_L))
        # Insert the projected point into the centerline so walk_along can use it as start
        pair_centerline, i_meet = insert_meeting_into_centerline(centerline, seg_idx, frac, meeting_pt)
        meet_amsl = bake_amsl(meeting_pt[0], meeting_pt[1], AGL)

        # East walk (forward through KML; KML is sorted west→east so forward = +1)
        east_path, east_full = walk_along(pair_centerline, i_meet, +1, TILE_LEN_M)
        west_path, west_full = walk_along(pair_centerline, i_meet, -1, TILE_LEN_M)

        # Polylines ordered with MEETING POINT LAST (EntryPoint=2 → entry/exit at meeting)
        east_polyline = list(reversed(east_path))  # was [meet, ..., east_far]
        west_polyline = list(reversed(west_path))  # was [meet, ..., west_far]

        east_polyline = douglas_peucker(east_polyline, DECIMATE_TOL_M)
        west_polyline = douglas_peucker(west_polyline, DECIMATE_TOL_M)

        # HOME = Launch coords with DEM-baked ground AMSL
        home_amsl = terrain_amsl(lat_L, lon_L)
        plan_home = [lat_L, lon_L, home_amsl]

        # File names (Pair 1 = Fergus3/Fergus4, Pair 2 = Fergus5/Fergus6, ...)
        east_idx = 2*n + 1   # 3, 5, 7, ...
        west_idx = 2*n + 2   # 4, 6, 8, ...
        east_name = f'Fergus{east_idx}.plan'
        west_name = f'Fergus{west_idx}.plan'

        # East tile = START cal flight (first in envelope)
        east_plan = build_plan(template, east_polyline, plan_home, AGL,
                               fig8_at_start=True, fig8_at_end=False,
                               fig8_centroid_alt_amsl=meet_amsl,
                               fig8_centroid_latlon=meeting_pt)
        # West tile = END cal flight (last in envelope)
        west_plan = build_plan(template, west_polyline, plan_home, AGL,
                               fig8_at_start=False, fig8_at_end=True,
                               fig8_centroid_alt_amsl=meet_amsl,
                               fig8_centroid_latlon=meeting_pt)

        minified_write(os.path.join(OUT_DIR, east_name), east_plan)
        minified_write(os.path.join(OUT_DIR, west_name), west_plan)

        # Compute polyline lengths for report
        def polylen(p):
            return sum(hav(p[i], p[i+1]) for i in range(len(p)-1))
        east_m = polylen(east_polyline)
        west_m = polylen(west_polyline)

        report.append({
            'pair': n,
            'launch': (lat_L, lon_L),
            'meeting': meeting_pt,
            'launch_to_meeting_m': d_proj,
            'east_name': east_name, 'west_name': west_name,
            'east_pts': len(east_polyline), 'east_len_m': east_m, 'east_full': east_full,
            'west_pts': len(west_polyline), 'west_len_m': west_m, 'west_full': west_full,
        })
        print(f'\nPair {n} ({east_name}/{west_name}):')
        print(f'  Launch        = ({lat_L:.6f}, {lon_L:.6f})')
        print(f'  Meeting (KML) = ({meeting_pt[0]:.6f}, {meeting_pt[1]:.6f})  ({d_proj:.0f} m from launch)')
        print(f'  East tile: {len(east_polyline)} pts, {east_m:.0f} m  full={east_full}')
        print(f'  West tile: {len(west_polyline)} pts, {west_m:.0f} m  full={west_full}')
        print(f'  HOME AMSL (ground) = {home_amsl:.1f} m, meeting+AGL = {meet_amsl:.1f} m AMSL')

    # Continuity report: how do adjacent pairs' tiles abut?
    print('\n=== Continuity between adjacent pairs ===')
    for n in range(len(report) - 1):
        a = report[n]; b = report[n+1]
        # Pair a's west tile ends at far_west = west_polyline[0] (since polyline reversed, meeting last)
        # Pair b's east tile ends at far_east = east_polyline[0]
        a_west_polyline = a  # we don't have full polyline now; just compare endpoints geographically
        # Recompute the west-far endpoint of pair a and east-far endpoint of pair b
        # by walking again — or just compare distance between the launches' walks
        pass
    # Just dump a summary table
    print('\n=== Summary ===')
    print(f'{"Pair":<5}{"Files":<22}{"Launch":<24}{"Meeting":<24}{"E km":<7}{"W km":<7}{"L->M m":<8}')
    for r in report:
        print(f'{r["pair"]:<5}'
              f'{r["east_name"]+"/"+r["west_name"]:<22}'
              f'({r["launch"][0]:.5f},{r["launch"][1]:.5f}) '
              f'({r["meeting"][0]:.5f},{r["meeting"][1]:.5f}) '
              f'{r["east_len_m"]/1000:<7.2f}{r["west_len_m"]/1000:<7.2f}{r["launch_to_meeting_m"]:<8.0f}')

    return report

if __name__ == '__main__':
    main()
