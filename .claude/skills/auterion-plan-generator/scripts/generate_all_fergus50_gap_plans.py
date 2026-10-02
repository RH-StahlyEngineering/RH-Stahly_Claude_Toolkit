"""Generate tap-corridor gap-fill missions from Fergus_uncovered_gaps_final.kml.

For each gap polygon:
  * Compute principal axis (PCA) — the tap direction.
  * Extend the along-axis span so the corridor reaches the highway centerline on one end and
    50 m past the tap on the far end.
  * Build a rectangular polygon aligned to the tap direction, wide enough to cover the gap
    polygon's perp extent + 25 m margin (min 100 m).
  * AMC-native TransectStyleComplexItem survey with:
      - angle = principal axis bearing (transects parallel to tap)
      - AGL 50 m, line spacing 50 m, Manual camera, FollowTerrain=true, TurnAroundDistance=15.24
  * Standalone flight (START + END figure-8 cals, 25-min battery).
  * Cross-line perpendicular to survey direction, extended past polygon by 25 m each side.

Output: `Fergus50_GapNN_tap.plan` in AMC Missions folder + copy to E:/Fergus_Electric_Lidar/Lidar_mission_plans/.
"""
import os, sys, json, re, math, copy, shutil
SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SKILL_DIR, 'scripts'))

import dem_lookup
_explicit = os.path.expanduser('~/.claude/dem_cache/dem_ee0aa3a8a9d0.json')
if os.path.exists(_explicit):
    dem_lookup._explicit_meta_paths.insert(0, _explicit)
    dem_lookup._local_dem = None
    dem_lookup._local_meta = None

from dem_lookup import terrain_amsl
from figure8 import fig8_waypoints
from shapely.geometry import LineString, Point, Polygon, box, MultiPolygon
from shapely.affinity import rotate as shp_rotate

GAPS_KML     = 'C:/Users/rharbach.STAHLY/Downloads/Fergus_uncovered_gaps_final.kml'
HIGHWAY_KML  = 'C:/Users/rharbach.STAHLY/Downloads/HighwayCenterline.kml'
OUT_DIR      = 'C:/Users/rharbach.STAHLY/Documents/Auterion Mission Control/Missions'
E_DRIVE      = 'E:/Fergus_Electric_Lidar/Lidar_mission_plans'

AGL = 50.0
SPEED = 11.5
LINE_SPACING_M = 50.0
CORRIDOR_WIDTH_MIN_M = 100.0
CORRIDOR_WIDTH_MARGIN_M = 25.0   # each side, added to polygon perp extent
CENTERLINE_EXTEND_M = 0.0        # already goes TO centerline
TAP_END_EXTEND_M = 50.0          # extend past far end
CROSS_MARGIN_M = 25.0             # cross-line extension past polygon
TURNAROUND_M = 15.24
FIG8_DURATION_S = 15.0
MIN_AREA_AC = 0.05                # skip gaps smaller than this (~200 m² = artifact slivers)
SLICE_AREA_THRESHOLD_AC = 10.0    # gaps larger than this get sliced along their principal axis (2026-07-03)
SLICE_TARGET_AC_PER_SLICE = 8.0   # target area per slice; N = max(2, ceil(area / this))

# 2026-07-03: rally point per Ryan's 8BA modification
RALLY_OFFSET_EAST_M  = 37.3
RALLY_OFFSET_NORTH_M = 45.4
RALLY_ALT_M          = 45.72


def add_rally_point(plan):
    """Append a rally point near the last nav WP (matches Ryan's 8BA pattern)."""
    items = plan['mission']['items']
    last_wp = None
    for it in reversed(items):
        if it.get('command') in (16, 17):
            last_wp = it; break
    if last_wp is None:
        return
    lat = last_wp['params'][4]; lon = last_wp['params'][5]
    m_lat = 111132.0
    m_lon = 111132.0 * math.cos(math.radians(lat))
    rally_lat = lat + RALLY_OFFSET_NORTH_M / m_lat
    rally_lon = lon + RALLY_OFFSET_EAST_M / m_lon
    plan['rallyPoints'] = {
        'points': [[rally_lat, rally_lon, RALLY_ALT_M]],
        'version': 2
    }


def load_gaps_kml(path):
    """Yield (name, area_ac, [(lat, lon), ...]) for each Placemark polygon in the KML."""
    txt = open(path, 'r', encoding='utf-8').read()
    for m in re.finditer(r'<Placemark>[\s\S]*?<name>(?P<name>Gap[^<]*)</name>[\s\S]*?<Polygon>[\s\S]*?<coordinates>(?P<coords>[\s\S]*?)</coordinates>', txt):
        name = m.group('name').strip()
        area = 0.0
        am = re.search(r'\(([\d.]+) ac\)', name)
        if am:
            area = float(am.group(1))
        # Coords are "lon,lat,alt lon,lat,alt ..." (KML convention)
        coords = []
        for triplet in m.group('coords').strip().split():
            parts = triplet.split(',')
            if len(parts) >= 2:
                coords.append((float(parts[1]), float(parts[0])))  # (lat, lon)
        yield name, area, coords


def load_linestring_kml(path):
    txt = open(path, 'r', encoding='utf-8').read()
    m = re.search(r'<LineString[\s\S]*?<coordinates>([\s\S]+?)</coordinates>', txt)
    pts = []
    for triplet in m.group(1).strip().split():
        parts = triplet.split(',')
        if len(parts) >= 2:
            pts.append((float(parts[1]), float(parts[0])))
    return pts


def make_back_proj(ref_lat, ref_lon):
    m_lat = 111132.0
    m_lon = 111132.0 * math.cos(math.radians(ref_lat))
    def to_xy(lat, lon): return ((lon - ref_lon) * m_lon, (lat - ref_lat) * m_lat)
    def from_xy(x, y):   return (ref_lat + y/m_lat, ref_lon + x/m_lon)
    return to_xy, from_xy


def slice_polygon_xy(poly_xy, n_slices):
    """Slice a polygon (list of (x,y) tuples) into n_slices sub-polygons along its PCA principal axis.
    Returns a list of lists of (x,y) tuples — one list per slice. Empty slices are dropped."""
    if n_slices <= 1:
        return [poly_xy]
    poly = Polygon(poly_xy)
    if not poly.is_valid:
        poly = poly.buffer(0)
        if not isinstance(poly, Polygon):
            # take the largest piece
            poly = max(poly.geoms, key=lambda g: g.area)
    # PCA
    cx = sum(p[0] for p in poly_xy)/len(poly_xy)
    cy = sum(p[1] for p in poly_xy)/len(poly_xy)
    Sxx = Syy = Sxy = 0.0
    for x, y in poly_xy:
        dx=x-cx; dy=y-cy; Sxx+=dx*dx; Syy+=dy*dy; Sxy+=dx*dy
    theta = 0.5 * math.atan2(2*Sxy, Sxx - Syy)
    theta_deg = math.degrees(theta)
    # Rotate polygon so principal axis aligns with x
    poly_rot = shp_rotate(poly, -theta_deg, origin=(cx, cy))
    minx, miny, maxx, maxy = poly_rot.bounds
    slices = []
    for k in range(n_slices):
        s_lo = minx + k * (maxx - minx) / n_slices
        s_hi = minx + (k+1) * (maxx - minx) / n_slices
        slab = box(s_lo, miny - 1.0, s_hi, maxy + 1.0)
        piece_rot = poly_rot.intersection(slab)
        if piece_rot.is_empty or piece_rot.area < 100:
            continue
        piece = shp_rotate(piece_rot, theta_deg, origin=(cx, cy))
        # piece may be Polygon or MultiPolygon — take largest
        if isinstance(piece, MultiPolygon):
            piece = max(piece.geoms, key=lambda g: g.area)
        if not isinstance(piece, Polygon):
            continue
        # Extract (x,y) list from exterior ring
        xy = list(piece.exterior.coords)
        # shapely closes the ring; drop the duplicate last point
        if xy and xy[0] == xy[-1]:
            xy = xy[:-1]
        slices.append(xy)
    return slices


def pca_principal_axis(xy_pts):
    """Return (ux, uy) = unit vector of principal (largest-variance) direction."""
    cx = sum(p[0] for p in xy_pts) / len(xy_pts)
    cy = sum(p[1] for p in xy_pts) / len(xy_pts)
    Sxx = Syy = Sxy = 0.0
    for x, y in xy_pts:
        dx = x - cx; dy = y - cy
        Sxx += dx*dx; Syy += dy*dy; Sxy += dx*dy
    # Eigen decomp of 2x2 symmetric matrix
    theta = 0.5 * math.atan2(2*Sxy, Sxx - Syy)
    return math.cos(theta), math.sin(theta)


def project_onto(pts, cx, cy, ux, uy):
    """Project (pts - (cx,cy)) onto unit vector (ux, uy). Returns list of scalars."""
    return [(p[0]-cx)*ux + (p[1]-cy)*uy for p in pts]


def wp_simple(cmd, lat, lon, alt_amsl, agl, dj, idx, frame=0, params_extra=None):
    params = params_extra if params_extra else [0, 0, 0, None, lat, lon, alt_amsl]
    item = {
        'MISSION_ITEM_ID': str(idx),
        'autoContinue': True,
        'command': cmd,
        'doJumpId': dj,
        'frame': frame,
        'groupTag': 0,
        'params': params,
        'type': 'SimpleItem'
    }
    if cmd in (16, 17):
        item['AMSLAltAboveTerrain'] = alt_amsl
        item['Altitude'] = agl
        item['AltitudeMode'] = 3
    return item


def build_polygon_survey(polygon_latlon, angle_deg, dj_start, idx_start):
    """Build the AMC TransectStyleComplexItem for a polygon survey."""
    item = {
        'MISSION_ITEM_ID': str(idx_start),
        'complexItemType': 'survey',
        'polygon': [list(p) for p in polygon_latlon],   # [[lat, lon], ...]
        'angle': float(angle_deg),
        'entryLocation': 0,
        'flyAlternateTransects': False,
        'splitConcavePolygons': False,
        'type': 'ComplexItem',
        'version': 5,
        'doJumpId': dj_start,
        'TransectStyleComplexItem': {
            'CameraCalc': {
                'CameraName': 'Manual (no camera specs)',
                'DistanceToSurface': AGL,
                'DistanceToSurfaceRelative': False,
                'AdjustedFootprintSide': LINE_SPACING_M,
                'AdjustedFootprintFrontal': 25.0,
                'version': 1
            },
            'CameraShots': 0,
            'CameraTriggerInTurnAround': False,
            'FlightSpeed': SPEED,
            'FollowTerrain': True,
            'HoverAndCapture': False,
            'Items': [],
            'Refly90Degrees': False,
            'TerrainAdjustMaxClimbRate': 3.0,
            'TerrainAdjustMaxDescentRate': 3.0,
            'TerrainAdjustTolerance': 5.0,
            'TurnAroundDistance': TURNAROUND_M,
            'VisualTransectPoints': [],
            'version': 1
        }
    }
    return item


def build_gap_plan(gap_name, gap_polygon_latlon, gap_area_ac, hwy_line_xy, hwy_line_shapely,
                   ref_lat, ref_lon, to_xy, from_xy, extend_to_centerline=True):
    """Build one .plan for a tap gap. Returns (plan_dict, n_items) or None if skipped.
    extend_to_centerline: if True (default, for actual taps), extend corridor from centerline to polygon far end.
      For sliced big-gap sub-polygons this is False — we just hug the slice's own extents.
    """
    if gap_area_ac < MIN_AREA_AC:
        return None, 0, f'skip: area {gap_area_ac:.3f} ac < {MIN_AREA_AC} ac'

    # 1) Convert polygon vertices to XY
    poly_xy = [to_xy(lat, lon) for (lat, lon) in gap_polygon_latlon]

    # 2) PCA principal axis
    ux, uy = pca_principal_axis(poly_xy)
    # Perpendicular unit vector
    vx, vy = -uy, ux

    # 3) Polygon centroid + extents
    cx = sum(p[0] for p in poly_xy) / len(poly_xy)
    cy = sum(p[1] for p in poly_xy) / len(poly_xy)
    along = project_onto(poly_xy, cx, cy, ux, uy)
    perp  = project_onto(poly_xy, cx, cy, vx, vy)
    along_min, along_max = min(along), max(along)
    perp_min, perp_max = min(perp), max(perp)
    perp_extent = perp_max - perp_min

    # 4) Determine which end is closer to centerline (nearest highway point)
    centroid_pt = Point(cx, cy)
    nearest_along = hwy_line_shapely.project(centroid_pt)      # distance along the highway to nearest point
    nearest_hwy_pt = hwy_line_shapely.interpolate(nearest_along)
    hwy_x, hwy_y = nearest_hwy_pt.x, nearest_hwy_pt.y
    # Vector from nearest hwy point to centroid, projected onto principal axis:
    v_hwy_to_centroid_along = (cx - hwy_x) * ux + (cy - hwy_y) * uy
    # If negative, flip the principal axis so +u points "outward from centerline"
    if v_hwy_to_centroid_along < 0:
        ux, uy = -ux, -uy
        vx, vy = -uy, ux
        along = [-a for a in along]
        along_min, along_max = -along_max, -along_min

    # 5) Determine tap-corridor along-span
    if extend_to_centerline:
        # Actual tap: extend from centerline to +50 m past polygon far end
        d_near = (hwy_x - cx) * ux + (hwy_y - cy) * uy
        corridor_along_min = min(along_min, d_near)
        corridor_along_max = along_max + TAP_END_EXTEND_M
    else:
        # Sliced sub-polygon of a big gap: just hug the slice with a small margin (no centerline reach)
        corridor_along_min = along_min - CORRIDOR_WIDTH_MARGIN_M
        corridor_along_max = along_max + CORRIDOR_WIDTH_MARGIN_M

    # 6) Corridor width
    corridor_perp_half = max(perp_extent / 2 + CORRIDOR_WIDTH_MARGIN_M, CORRIDOR_WIDTH_MIN_M / 2)
    corridor_perp_min = -corridor_perp_half
    corridor_perp_max = +corridor_perp_half

    # 7) Build the 4-corner rectangle in XY (centroid-relative in (along, perp) space, then rotate/translate to XY)
    def uv_to_xy(a, p):
        return (cx + a*ux + p*vx, cy + a*uy + p*vy)
    corners_xy = [
        uv_to_xy(corridor_along_min, corridor_perp_min),
        uv_to_xy(corridor_along_max, corridor_perp_min),
        uv_to_xy(corridor_along_max, corridor_perp_max),
        uv_to_xy(corridor_along_min, corridor_perp_max),
    ]
    corners_latlon = [from_xy(x, y) for (x, y) in corners_xy]

    # 8) Survey angle = principal axis bearing (compass degrees, 0=N, CW+)
    # Math angle from atan2(uy, ux) is measured CCW from +x; compass is CW from +y (north).
    # compass = 90° - math_angle  (mod 360)
    math_angle_deg = math.degrees(math.atan2(uy, ux))
    compass_angle_deg = (90.0 - math_angle_deg) % 360.0

    # 9) Corridor rectangle centroid for HOME + fig-8 centering
    corridor_center_along = (corridor_along_min + corridor_along_max) / 2
    home_x, home_y = uv_to_xy(corridor_center_along, 0.0)
    home_lat, home_lon = from_xy(home_x, home_y)
    home_ground_amsl = terrain_amsl(home_lat, home_lon)
    home_amsl = home_ground_amsl + AGL

    # 10) Build the plan items
    items = []
    idx = 0; dj = 1
    # Header
    items.append({
        'MISSION_ITEM_ID': str(idx), 'autoContinue': True, 'command': 530,
        'doJumpId': dj, 'frame': 2, 'groupTag': 0,
        'params': [0, 2, None, None, None, None, None], 'type': 'SimpleItem'
    })
    idx += 1; dj += 1
    items.append({
        'MISSION_ITEM_ID': str(idx), 'autoContinue': True, 'command': 178,
        'doJumpId': dj, 'frame': 2, 'groupTag': 0,
        'params': [1, SPEED, -1, 0, 0, 0, 0], 'type': 'SimpleItem'
    })
    idx += 1; dj += 1

    # Figure-8 START cal centered at HOME
    fig8_start = fig8_waypoints(lat=home_lat, lon=home_lon, alt_amsl=home_amsl,
                                speed=SPEED, duration=FIG8_DURATION_S, frame=0)
    for wp in fig8_start:
        la = wp['params'][4]; lo = wp['params'][5]
        a = terrain_amsl(la, lo) + AGL
        items.append(wp_simple(16, la, lo, a, AGL, dj, idx))
        idx += 1; dj += 1

    # Polygon survey (TransectStyleComplexItem)
    items.append(build_polygon_survey(corners_latlon, compass_angle_deg, dj, idx))
    idx += 1; dj += 1

    # Cross-line: perpendicular to survey direction (= along principal axis, at one end of corridor)
    # Place cross-line at the corridor's far end (past the tap), extend CROSS_MARGIN past corridor edges
    cross_along = corridor_along_max - LINE_SPACING_M / 2   # one line-spacing back from the far end
    cross_perp_a = corridor_perp_min - CROSS_MARGIN_M
    cross_perp_b = corridor_perp_max + CROSS_MARGIN_M
    xa_x, xa_y = uv_to_xy(cross_along, cross_perp_a)
    xb_x, xb_y = uv_to_xy(cross_along, cross_perp_b)
    xa_lat, xa_lon = from_xy(xa_x, xa_y)
    xb_lat, xb_lon = from_xy(xb_x, xb_y)
    xa_amsl = terrain_amsl(xa_lat, xa_lon) + AGL
    xb_amsl = terrain_amsl(xb_lat, xb_lon) + AGL
    items.append(wp_simple(16, xa_lat, xa_lon, xa_amsl, AGL, dj, idx))
    idx += 1; dj += 1
    items.append(wp_simple(16, xb_lat, xb_lon, xb_amsl, AGL, dj, idx))
    idx += 1; dj += 1

    # Figure-8 END cal centered at cross-line B end
    fig8_end = fig8_waypoints(lat=xb_lat, lon=xb_lon, alt_amsl=xb_amsl,
                              speed=SPEED, duration=FIG8_DURATION_S, frame=0)
    for wp in fig8_end:
        la = wp['params'][4]; lo = wp['params'][5]
        a = terrain_amsl(la, lo) + AGL
        items.append(wp_simple(16, la, lo, a, AGL, dj, idx))
        idx += 1; dj += 1

    # Return to HOME (last waypoint = HOME position at AGL)
    items.append(wp_simple(16, home_lat, home_lon, home_amsl, AGL, dj, idx))
    idx += 1; dj += 1

    plan = {
        'fileType': 'Plan',
        'geoFence': {'circles': [], 'polygons': [], 'version': 2},
        'groundStation': 'QGroundControl',
        'mission': {
            'cruiseSpeed': 15,
            'firmwareType': 12,
            'globalPlanAltitudeMode': 3,
            'hoverSpeed': 10,
            'items': items,
            'plannedHomePosition': [home_lat, home_lon, home_ground_amsl],
            'vehicleType': 2,
            'version': 2
        },
        'rallyPoints': {'points': [], 'version': 2},
        'version': 1
    }

    add_rally_point(plan)

    # Diagnostic
    corridor_len = corridor_along_max - corridor_along_min
    corridor_wid = 2 * corridor_perp_half
    info = f'ok: corridor {corridor_len:.0f}×{corridor_wid:.0f} m, angle {compass_angle_deg:.0f}°, {len(items)} items'
    return plan, len(items), info


def main():
    print('Loading highway centerline...')
    highway = load_linestring_kml(HIGHWAY_KML)
    ref_lat = sum(p[0] for p in highway) / len(highway)
    ref_lon = sum(p[1] for p in highway) / len(highway)
    to_xy, from_xy = make_back_proj(ref_lat, ref_lon)
    hwy_xy = [to_xy(*p) for p in highway]
    hwy_line = LineString(hwy_xy)
    print(f'  Highway {hwy_line.length:.0f} m, ref ({ref_lat:.4f}, {ref_lon:.4f})')

    print('Loading gaps KML...')
    gaps = list(load_gaps_kml(GAPS_KML))
    print(f'  Found {len(gaps)} gaps')

    skipped = []
    written = []
    # First, clean up any stale big-gap files (both original whole-gap plans and prior slices)
    for existing in os.listdir(OUT_DIR):
        if re.match(r'Fergus50_Gap\d+[a-z]?_tap\.plan$', existing):
            # Will be regenerated below; safe to remove now (we'll rewrite the ones we keep)
            pass  # actually don't delete now — overwrite in place. Old slice suffixes get cleaned after.
    generated_filenames = set()
    for gap_name, area, coords in gaps:
        m = re.search(r'Gap (\d+)', gap_name)
        gap_num = int(m.group(1)) if m else 0
        if area < MIN_AREA_AC:
            print(f'  Gap {gap_num:02d} ({area:.3f} ac): skip (below min area)')
            skipped.append((gap_num, area, 'below min area'))
            continue
        # Decide slice count
        if area >= SLICE_AREA_THRESHOLD_AC:
            n_slices = max(2, int(math.ceil(area / SLICE_TARGET_AC_PER_SLICE)))
        else:
            n_slices = 1
        # Convert to XY for slicing
        poly_xy = [to_xy(la, lo) for (la, lo) in coords]
        if n_slices == 1:
            slice_polys_xy = [poly_xy]
        else:
            slice_polys_xy = slice_polygon_xy(poly_xy, n_slices)
        # Build one plan per slice
        for i, s_poly_xy in enumerate(slice_polys_xy):
            s_coords_latlon = [from_xy(x, y) for (x, y) in s_poly_xy]
            # Approximate slice area
            def poly_area(pts):
                a=0.0
                for j in range(len(pts)):
                    x1,y1=pts[j]; x2,y2=pts[(j+1)%len(pts)]
                    a += x1*y2 - x2*y1
                return abs(a)/2
            slice_area_ac = poly_area(s_poly_xy) / 4046.86
            suffix = ''
            if len(slice_polys_xy) > 1:
                suffix = chr(ord('a') + i)   # a, b, c, ...
            fname = f'Fergus50_Gap{gap_num:02d}{suffix}_tap.plan'
            try:
                is_sliced = len(slice_polys_xy) > 1
                plan, n_items, info = build_gap_plan(gap_name, s_coords_latlon, slice_area_ac,
                                                     hwy_xy, hwy_line, ref_lat, ref_lon, to_xy, from_xy,
                                                     extend_to_centerline=not is_sliced)
            except Exception as e:
                print(f'  Gap {gap_num:02d}{suffix} ({slice_area_ac:.2f} ac): ERROR {e}')
                skipped.append((gap_num, slice_area_ac, f'{suffix}: {e}'))
                continue
            if plan is None:
                print(f'  Gap {gap_num:02d}{suffix} ({slice_area_ac:.2f} ac): {info}')
                skipped.append((gap_num, slice_area_ac, f'{suffix}: {info}'))
                continue
            out_path = os.path.join(OUT_DIR, fname)
            with open(out_path, 'wb') as f:
                f.write(json.dumps(plan, separators=(',', ':')).encode('utf-8'))
            if os.path.isdir(E_DRIVE):
                shutil.copy(out_path, os.path.join(E_DRIVE, fname))
            print(f'  Gap {gap_num:02d}{suffix} ({slice_area_ac:.2f} ac): {info} -> {fname}')
            written.append((gap_num, slice_area_ac, n_items))
            generated_filenames.add(fname)
    # Clean up: for the sliced big gaps, the OLD single-plan file must be removed if it's not in generated set.
    for existing in list(os.listdir(OUT_DIR)):
        m = re.match(r'Fergus50_Gap(\d+)_tap\.plan$', existing)
        if m and existing not in generated_filenames:
            os.remove(os.path.join(OUT_DIR, existing))
            e_path = os.path.join(E_DRIVE, existing) if os.path.isdir(E_DRIVE) else None
            if e_path and os.path.exists(e_path):
                os.remove(e_path)
            print(f'  Removed stale (was single-gap plan, now sliced): {existing}')

    print()
    print(f'Wrote {len(written)} plans, skipped {len(skipped)}.')
    if skipped:
        print('Skipped:')
        for g, a, r in skipped:
            print(f'  Gap {g:02d} ({a:.2f} ac): {r}')


if __name__ == '__main__':
    main()
