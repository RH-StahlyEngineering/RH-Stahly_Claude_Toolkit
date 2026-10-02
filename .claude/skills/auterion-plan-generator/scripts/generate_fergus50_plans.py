"""Generate 20 .plan files for the Fergus 50m/11.5m/highway-centerline mission set.

Per the 2026-06-24 mobile-crew architecture (skill lessons #34-#39):
  - 10 sessions, each a round-trip A->B->A with hot swap at B
  - 20 .plan files total: 10 A->B legs + 10 B->A legs
  - Each plan is ONE battery (~10 min)
  - Cal happens ONLY at session start (A->B leg, at A) and session end (B->A leg, at A)
  - Hot-swap legs have no cal (other-leg flights)

Plan structure (Survey-style with manual waypoints, NOT CorridorScan complex item):
  - cmd 530 (mission options)
  - cmd 178 (set speed = 11.5 m/s)
  - WP at HOME (climb to 50 m AGL above HOME terrain)
  - [A->B only:] Cross-line at A (2 WPs perpendicular through polygon, 50 m margins)
  - [A->B only:] Figure-8 at A (11 WPs)
  - Survey transect (N WPs along highway offset by +/-25 m perpendicular)
  - [B->A only:] Figure-8 at A (11 WPs)
  - [B->A only:] Cross-line at A (2 WPs)
  - cmd 17 LOITER_UNLIM at landing position (drone holds at 50 m AGL, no auto-land)

All waypoints use frame=0 (absolute MSL) with DEM-baked AMSL = terrain + 50 m.

Polyline offset per leg:
  - A->B leg: highway centerline offset +25 m perpendicular (RIGHT of forward)
  - B->A leg: highway centerline offset -25 m perpendicular (LEFT of forward, = +25 m of reversed direction)
"""
import os, sys, json, re, math, copy, hashlib
SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SKILL_DIR, 'scripts'))

import dem_lookup
_explicit = os.path.expanduser('~/.claude/dem_cache/dem_ee0aa3a8a9d0.json')
if os.path.exists(_explicit):
    dem_lookup._explicit_meta_paths.insert(0, _explicit)
    dem_lookup._local_dem = None
    dem_lookup._local_meta = None

from dem_lookup import terrain_amsl, bake_amsl, ensure_dem_for_bbox
from figure8 import fig8_waypoints
from shapely.geometry import LineString, Polygon, Point
from shapely.ops import substring
from coverage_check_multi import make_projection, parse_kml_polygon

# ----- Configuration -----
KML_HIGHWAY = 'C:/Users/rharbach.STAHLY/Downloads/HighwayCenterline.kml'
TARGET_KML  = 'C:/Users/rharbach.STAHLY/Downloads/Fergus Hilger-Roy — corridor union.kml'
LAYOUT_JSON = 'C:/Users/rharbach.STAHLY/Downloads/Fergus_simple_layout.json'  # we'll create this if missing
F1_TEMPLATE = 'C:/Users/rharbach.STAHLY/Documents/Auterion Mission Control/Missions/Fergus1 (1).plan'
OUT_DIR     = 'C:/Users/rharbach.STAHLY/Documents/Auterion Mission Control/Missions'

AGL = 50.0
SPEED = 11.5
N_STRIPS = 10
SURVEY_WP_SPACING_M = 100.0   # waypoint every 100 m along transect
TRANSECT_OFFSET_M   = 25.0    # AGL / 2
CROSS_LINE_MARGIN_M = 50.0    # per user spec
FIG8_DURATION_S     = 15.0


def load_linestring(path):
    txt = open(path, 'r', encoding='utf-8').read()
    m = re.search(r'<LineString[\s\S]*?<coordinates>([\s\S]+?)</coordinates>', txt)
    return [tuple(map(float, t.split(',')[:2][::-1])) for t in m.group(1).strip().split()]


def make_back_proj(ref_lat, ref_lon):
    m_lat = 111132.0
    m_lon = 111132.0 * math.cos(math.radians(ref_lat))
    def to_xy(lat, lon): return ((lon - ref_lon) * m_lon, (lat - ref_lat) * m_lat)
    def from_xy(x, y): return (ref_lat + y/m_lat, ref_lon + x/m_lon)
    return to_xy, from_xy


def perp_offset_polyline_segment(hwy_xy, start_along_m, end_along_m, perp_offset_m, to_xy, from_xy):
    """Build a list of (lat, lon) waypoints along the highway from start_along to end_along,
    offset perpendicular to highway tangent by perp_offset_m. Sample every SURVEY_WP_SPACING_M.
    """
    hwy_line = LineString(hwy_xy)
    # Direction: positive end_along - start_along = forward
    forward = end_along_m > start_along_m
    if forward:
        s_from, s_to = start_along_m, end_along_m
    else:
        s_from, s_to = end_along_m, start_along_m
    # Sample positions every SURVEY_WP_SPACING along forward direction
    n_steps = max(2, int(math.ceil((s_to - s_from) / SURVEY_WP_SPACING_M)))
    step = (s_to - s_from) / n_steps
    sample_alongs = [s_from + i * step for i in range(n_steps + 1)]
    if not forward:
        sample_alongs = list(reversed(sample_alongs))  # iterate from end to start
    out = []
    for s in sample_alongs:
        p = hwy_line.interpolate(s)
        # Highway tangent at this point (forward direction along increasing along_m)
        eps = 0.5
        p_before = hwy_line.interpolate(max(0, s - eps))
        p_after = hwy_line.interpolate(min(hwy_line.length, s + eps))
        tx = p_after.x - p_before.x; ty = p_after.y - p_before.y
        tlen = math.hypot(tx, ty)
        if tlen < 1e-6:
            out.append((p.x, p.y)); continue
        tx, ty = tx/tlen, ty/tlen
        # Perpendicular: rotate 90 deg CCW = (-ty, tx) = LEFT of forward direction
        # For RIGHT of forward (positive convention), rotate 90 CW = (ty, -tx)
        # Actually: for a "north-and-up" coord, perpendicular RIGHT of forward is (ty, -tx).
        # We use perp_offset_m sign: + = right of forward direction (along increasing along_m), - = left.
        # But we're walking the polyline forward, so the offset direction matches the polyline's tangent.
        # For the A->B leg flying forward, +offset = right side. For B->A, the polyline is iterated reversed,
        # so the tangent is still forward-along-original-highway. We need to convert "offset relative to flight direction"
        # to "offset along original highway tangent." For B->A flying reversed, the tangent flips.
        # SIMPLER: pass perp_offset_m as already-resolved relative to forward-along-original-highway.
        perp_x = ty; perp_y = -tx   # right of forward (CW)
        ox = p.x + perp_offset_m * perp_x
        oy = p.y + perp_offset_m * perp_y
        out.append((ox, oy))
    return [from_xy(*xy) for xy in out]


def perpendicular_cross_line(a_xy, hwy_line, target_poly, from_xy):
    """Build a 2-point cross-line through A, perpendicular to highway tangent at A,
    starting 50 m outside polygon and ending 50 m past polygon.
    Returns ((lat1, lon1), (lat2, lon2)).
    """
    # Tangent at A
    s = hwy_line.project(Point(a_xy))
    eps = 0.5
    p_before = hwy_line.interpolate(max(0, s - eps))
    p_after = hwy_line.interpolate(min(hwy_line.length, s + eps))
    tx = p_after.x - p_before.x; ty = p_after.y - p_before.y
    tlen = math.hypot(tx, ty)
    if tlen < 1e-6:
        tx, ty = 1.0, 0.0
    else:
        tx, ty = tx/tlen, ty/tlen
    # Perpendicular: rotate +90 deg CCW = (-ty, tx)
    perp_x = -ty; perp_y = tx
    # Cast long perpendicular ray both directions from A
    SEARCH_LEN = 3000
    end_pos = (a_xy[0] + perp_x * SEARCH_LEN, a_xy[1] + perp_y * SEARCH_LEN)
    end_neg = (a_xy[0] - perp_x * SEARCH_LEN, a_xy[1] - perp_y * SEARCH_LEN)
    long_line = LineString([end_neg, end_pos])
    ix = long_line.intersection(target_poly)
    if ix.is_empty:
        # Fallback: 200 m cross-line centered at A
        e1 = (a_xy[0] + perp_x * 100, a_xy[1] + perp_y * 100)
        e2 = (a_xy[0] - perp_x * 100, a_xy[1] - perp_y * 100)
        return from_xy(*e1), from_xy(*e2)
    if ix.geom_type == 'LineString':
        ix_lines = [ix]
    elif ix.geom_type == 'MultiLineString':
        ix_lines = list(ix.geoms)
    else:
        ix_lines = []
    if not ix_lines:
        e1 = (a_xy[0] + perp_x * 100, a_xy[1] + perp_y * 100)
        e2 = (a_xy[0] - perp_x * 100, a_xy[1] - perp_y * 100)
        return from_xy(*e1), from_xy(*e2)
    # Find min/max param of polygon entry/exit on long_line
    params = []
    for ll in ix_lines:
        for pt in ll.coords:
            params.append(long_line.project(Point(pt)))
    entry_p = min(params)
    exit_p = max(params)
    start_p = max(0, entry_p - CROSS_LINE_MARGIN_M)
    end_p = min(long_line.length, exit_p + CROSS_LINE_MARGIN_M)
    sp = long_line.interpolate(start_p)
    ep = long_line.interpolate(end_p)
    return from_xy(sp.x, sp.y), from_xy(ep.x, ep.y)


def wp_nav(lat, lon, alt_amsl, dj, ground_amsl=None):
    """cmd 16 NAV_WAYPOINT, frame=0 (absolute AMSL).
    AMC-required fields on STANDALONE waypoints: AMSLAltAboveTerrain (= alt_amsl),
    Altitude (= AGL value), AltitudeMode (=3 to match globalPlanAltitudeMode).
    """
    agl = alt_amsl - ground_amsl if ground_amsl is not None else 50.0
    return {
        'AMSLAltAboveTerrain': alt_amsl,
        'Altitude': agl,
        'AltitudeMode': 3,
        'MISSION_ITEM_ID': str(dj),
        'autoContinue': True,
        'command': 16,
        'doJumpId': dj,
        'frame': 0,
        'groupTag': 0,
        'params': [0, 0, 0, None, lat, lon, alt_amsl],
        'type': 'SimpleItem'
    }


def wp_loiter_unlim(lat, lon, alt_amsl, dj, ground_amsl=None):
    """cmd 17 LOITER_UNLIM - drone holds at this position indefinitely."""
    agl = alt_amsl - ground_amsl if ground_amsl is not None else 50.0
    return {
        'AMSLAltAboveTerrain': alt_amsl,
        'Altitude': agl,
        'AltitudeMode': 3,
        'MISSION_ITEM_ID': str(dj),
        'autoContinue': True,
        'command': 17,
        'doJumpId': dj,
        'frame': 0,
        'groupTag': 0,
        'params': [0, 0, 0, None, lat, lon, alt_amsl],
        'type': 'SimpleItem'
    }


def cmd_530():
    return {
        'MISSION_ITEM_ID': '0',
        'autoContinue': True,
        'command': 530,
        'doJumpId': 1,
        'frame': 2,
        'groupTag': 0,
        'params': [0, 2, None, None, None, None, None],
        'type': 'SimpleItem'
    }


def cmd_178(speed):
    return {
        'MISSION_ITEM_ID': '1',
        'autoContinue': True,
        'command': 178,
        'doJumpId': 2,
        'frame': 2,
        'groupTag': 0,
        'params': [1, speed, -1, 0, 0, 0, 0],
        'type': 'SimpleItem'
    }


def amc_normalize_item(it, idx):
    """Ensure a cmd 16 item has AMC's required standalone-waypoint fields:
    AMSLAltAboveTerrain (numeric), Altitude (AGL), AltitudeMode (3), MISSION_ITEM_ID, groupTag.
    Items from figure8.py and other helpers don't include these.
    """
    it = copy.deepcopy(it)
    cmd = it.get('command')
    it['groupTag'] = 0
    it['MISSION_ITEM_ID'] = str(idx)
    if cmd in (16, 17):
        p = it.get('params', [])
        alt_amsl = p[6] if len(p) > 6 and p[6] is not None else 0.0
        it['AMSLAltAboveTerrain'] = alt_amsl
        it['Altitude'] = AGL   # AGL value for AMC display
        it['AltitudeMode'] = 3
    return it


def build_plan(home_lat, home_lon, home_amsl, items, name):
    """Build a complete plan dict. items is the list of mission items AFTER cmd530+cmd178.
    Renumbers doJumpId and MISSION_ITEM_ID sequentially."""
    full_items = [cmd_530(), cmd_178(SPEED)]
    for it in items:
        full_items.append(copy.deepcopy(it))
    # Normalize each item with AMC-required fields and sequential IDs
    final_items = []
    for idx, it in enumerate(full_items):
        it = amc_normalize_item(it, idx)
        it['doJumpId'] = idx + 1
        final_items.append(it)
    return {
        'fileType': 'Plan',
        'geoFence': {'circles': [], 'polygons': [], 'version': 2},
        'groundStation': 'QGroundControl',
        'mission': {
            'cruiseSpeed': 15,         # skill canonical constant
            'firmwareType': 12,
            'globalPlanAltitudeMode': 3,
            'hoverSpeed': 10,          # skill canonical constant
            'items': final_items,
            'plannedHomePosition': [home_lat, home_lon, home_amsl],
            'vehicleType': 2,
            'version': 2
        },
        'rallyPoints': {'points': [], 'version': 2},
        'version': 1
    }


def main():
    print('Loading inputs...')
    highway = load_linestring(KML_HIGHWAY)
    target_outer, target_holes = parse_kml_polygon(TARGET_KML)[0]

    ref_lat = sum(p[0] for p in highway) / len(highway)
    ref_lon = sum(p[1] for p in highway) / len(highway)
    to_xy, from_xy = make_back_proj(ref_lat, ref_lon)

    hwy_xy = [to_xy(*p) for p in highway]
    hwy_line = LineString(hwy_xy)
    target_xy = Polygon([to_xy(*p) for p in target_outer],
                        [[to_xy(*p) for p in h] for h in target_holes])

    # Warm DEM bbox
    lats = [p[0] for p in highway]
    lons = [p[1] for p in highway]
    pad = 0.02
    try:
        ensure_dem_for_bbox(min(lats) - pad, max(lats) + pad,
                            min(lons) - pad, max(lons) + pad, resolution_m=10.0)
    except Exception as e:
        print(f'Warning: DEM bbox warm failed ({e}). Relying on cached TIFF.')

    # Compute A points: evenly spaced from 0 to hwy_line.length
    hwy_len_m = hwy_line.length
    strip_len_m = hwy_len_m / N_STRIPS
    a_alongs = [i * strip_len_m for i in range(N_STRIPS + 1)]
    a_lls = []
    for s in a_alongs:
        p = hwy_line.interpolate(min(s, hwy_len_m))
        lat, lon = from_xy(p.x, p.y)
        a_lls.append((lat, lon))

    print(f'Generating {2*N_STRIPS} plans for {N_STRIPS} sessions...\n')

    for i in range(N_STRIPS):
        sess = i + 1
        A_lat, A_lon = a_lls[i]
        B_lat, B_lon = a_lls[i+1]
        A_along = a_alongs[i]
        B_along = a_alongs[i+1]
        A_xy = to_xy(A_lat, A_lon)
        B_xy = to_xy(B_lat, B_lon)
        A_amsl = terrain_amsl(A_lat, A_lon)
        B_amsl = terrain_amsl(B_lat, B_lon)
        A_flight_amsl = A_amsl + AGL
        B_flight_amsl = B_amsl + AGL

        # Cross-line at A (same for both legs of this session)
        x1_ll, x2_ll = perpendicular_cross_line(A_xy, hwy_line, target_xy, from_xy)
        x1_amsl = terrain_amsl(*x1_ll) + AGL
        x2_amsl = terrain_amsl(*x2_ll) + AGL

        # Figure-8 at A: 11 waypoints
        fig8 = fig8_waypoints(lat=A_lat, lon=A_lon, alt_amsl=A_flight_amsl,
                               speed=SPEED, duration=FIG8_DURATION_S, frame=0)
        # Bake fig8 AMSL per waypoint
        for wp in fig8:
            la = wp['params'][4]; lo = wp['params'][5]
            wp['params'][6] = bake_amsl(la, lo, AGL)
            wp['Altitude'] = wp['params'][6]
            wp['AltitudeMode'] = 1

        # --- A->B PLAN ---
        # HOME = A, fly to B, hold at B
        # Order: cmd530 + cmd178 + [climb at A + cross-line + figure-8 + survey + hold at B]
        items = []
        # Climb waypoint at A
        items.append(wp_nav(A_lat, A_lon, A_flight_amsl, 0))
        # Cross-line: 2 waypoints
        items.append(wp_nav(x1_ll[0], x1_ll[1], x1_amsl, 0))
        items.append(wp_nav(x2_ll[0], x2_ll[1], x2_amsl, 0))
        # Figure-8
        for wp in fig8:
            items.append(copy.deepcopy(wp))
        # Survey transect at +25 m offset from highway, A->B direction
        survey_lls = perp_offset_polyline_segment(hwy_xy, A_along, B_along, +TRANSECT_OFFSET_M, to_xy, from_xy)
        for la, lo in survey_lls:
            t_amsl = terrain_amsl(la, lo) + AGL
            items.append(wp_nav(la, lo, t_amsl, 0))
        # Hold at B (= LOITER_UNLIM)
        items.append(wp_loiter_unlim(B_lat, B_lon, B_flight_amsl, 0))
        plan = build_plan(A_lat, A_lon, A_amsl, items, f'S{sess}_AB')
        out_path = os.path.join(OUT_DIR, f'Fergus50_S{sess:02d}_AB.plan')
        # Minified write (LF, UTF-8, no BOM)
        with open(out_path, 'wb') as f:
            f.write(json.dumps(plan, separators=(',', ':')).encode('utf-8'))
        n_items = len(plan['mission']['items'])
        print(f'  S{sess:02d}_AB: HOME=A({A_lat:.5f},{A_lon:.5f}) -> hold at B, {n_items} items')

        # --- B->A PLAN ---
        # HOME = B, fly to A, hold at A
        # Order: cmd530 + cmd178 + [climb at B + survey + figure-8 + cross-line + hold at A]
        items = []
        items.append(wp_nav(B_lat, B_lon, B_flight_amsl, 0))
        # Survey transect at -25 m offset, B->A direction
        survey_lls = perp_offset_polyline_segment(hwy_xy, B_along, A_along, -TRANSECT_OFFSET_M, to_xy, from_xy)
        for la, lo in survey_lls:
            t_amsl = terrain_amsl(la, lo) + AGL
            items.append(wp_nav(la, lo, t_amsl, 0))
        # Figure-8 at A
        for wp in fig8:
            items.append(copy.deepcopy(wp))
        # Cross-line: 2 waypoints (same cross-line as A->B)
        items.append(wp_nav(x2_ll[0], x2_ll[1], x2_amsl, 0))
        items.append(wp_nav(x1_ll[0], x1_ll[1], x1_amsl, 0))
        # Hold at A
        items.append(wp_loiter_unlim(A_lat, A_lon, A_flight_amsl, 0))
        plan = build_plan(B_lat, B_lon, B_amsl, items, f'S{sess}_BA')
        out_path = os.path.join(OUT_DIR, f'Fergus50_S{sess:02d}_BA.plan')
        with open(out_path, 'wb') as f:
            f.write(json.dumps(plan, separators=(',', ':')).encode('utf-8'))
        n_items = len(plan['mission']['items'])
        print(f'  S{sess:02d}_BA: HOME=B({B_lat:.5f},{B_lon:.5f}) -> hold at A, {n_items} items')

    print(f'\nGenerated 20 plans in {OUT_DIR}')


if __name__ == '__main__':
    main()
