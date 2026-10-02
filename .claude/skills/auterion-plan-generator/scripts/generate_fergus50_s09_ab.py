"""Generate Fergus50_S09_AB.plan per the FINAL SPEC (2026-06-26 v3).

Spec: specs/Fergus50_corridor_plan_spec.md (§§9-RESOLVED + §10).

Structure:
  0. cmd 530, cmd 178
  1. Kinematic line: K1 (perp = -101.5 m) -> K2 (perp = +25 m). 126.5 m, perpendicular to highway at A_along.
  2. Figure-8 centered at K2.
  3. Survey transect at +25 m perp_right offset, sparse (Douglas-Peucker).
  4. Teardrop closing loop: tangent_1 (R), arc 270° CW (R), tangent_2 (R, implicit) — anchor at last survey WP.
  5. Closing transect: 126.5 m perp_left_of_tan_B from anchor.
  6. LOITER_UNLIM at end of closing transect.

HOME = takeoff position = A_along - 50 m on highway centerline (outside corridor).
"""
import os, sys, json, re, math, copy
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
from shapely.geometry import LineString

KML_HIGHWAY = 'C:/Users/rharbach.STAHLY/Downloads/HighwayCenterline.kml'
OUT_DIR     = 'C:/Users/rharbach.STAHLY/Documents/Auterion Mission Control/Missions'

AGL = 50.0
SPEED = 11.5
N_STRIPS = 10
SESSION_INDEX = 9

# Spec-derived constants
KINEMATIC_LEN_M    = SPEED * 11.0     # 126.5 m (per Q1: 10 s + 1 s accel/decel)
TRANSECT_OFFSET_M  = AGL / 2          # 25 m (= +/- AGL/2, two-transect corridor)
CLOSING_TRANSECT_LEN_M = 200.0        # 200 m straight perpendicular line from spiral end (per revision v2 2026-06-29).
                                       # Spiral end ≈ corridor right edge; 200 m covers corridor crossing (150 m) + ~50 m margin past left edge.
CLOSING_TANGENT_1_LEN_M = AGL / 2     # 25 m straight tangent forward from anchor before arc
CLOSING_ARC_R_M    = AGL              # 50 m constant-radius circle (per Option A 2026-06-29)
CLOSING_ARC_SAMPLES = 8               # 8 intermediate WPs on the 270° arc (figure-8 density)
DP_TOLERANCE_M     = 5.0
FIG8_DURATION_S    = 15.0
HOME_OFFSET_FROM_A_M = 50.0           # HOME is 50 m before A on centerline


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


def douglas_peucker(pts, tol):
    if len(pts) < 3: return list(pts)
    dmax = 0.0; idx = 0
    a = pts[0]; b = pts[-1]
    L = math.hypot(b[0]-a[0], b[1]-a[1])
    for i in range(1, len(pts)-1):
        p = pts[i]
        if L == 0: d = math.hypot(p[0]-a[0], p[1]-a[1])
        else: d = abs((p[0]-a[0])*(b[1]-a[1]) - (p[1]-a[1])*(b[0]-a[0])) / L
        if d > dmax: dmax = d; idx = i
    if dmax > tol:
        return douglas_peucker(pts[:idx+1], tol)[:-1] + douglas_peucker(pts[idx:], tol)
    return [pts[0], pts[-1]]


def tangent_at_along(hwy_line, s):
    eps = 1.0
    p1 = hwy_line.interpolate(max(0, s - eps))
    p2 = hwy_line.interpolate(min(hwy_line.length, s + eps))
    dx = p2.x - p1.x; dy = p2.y - p1.y
    L = math.hypot(dx, dy)
    if L < 1e-6: return (1.0, 0.0)
    return (dx/L, dy/L)


def perp_right(tx, ty):
    """90 deg CLOCKWISE rotation of (tx, ty) = right of forward in plan view (y-up)."""
    return (ty, -tx)


def perp_left(tx, ty):
    return (-ty, tx)


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


def main():
    print('Loading inputs...')
    highway = load_linestring(KML_HIGHWAY)

    ref_lat = sum(p[0] for p in highway) / len(highway)
    ref_lon = sum(p[1] for p in highway) / len(highway)
    to_xy, from_xy = make_back_proj(ref_lat, ref_lon)

    hwy_xy = [to_xy(*p) for p in highway]
    hwy_line = LineString(hwy_xy)
    hwy_len_m = hwy_line.length
    strip_len_m = hwy_len_m / N_STRIPS

    a_along = (SESSION_INDEX - 1) * strip_len_m
    b_along = SESSION_INDEX * strip_len_m

    # HOME = 50 m before A on centerline
    home_along = a_along - HOME_OFFSET_FROM_A_M
    home_pt = hwy_line.interpolate(home_along)
    home_lat, home_lon = from_xy(home_pt.x, home_pt.y)
    home_ground_amsl = terrain_amsl(home_lat, home_lon)

    # Tangents
    tan_A = tangent_at_along(hwy_line, a_along)
    perp_right_A = perp_right(*tan_A)
    perp_left_A = perp_left(*tan_A)
    tan_B = tangent_at_along(hwy_line, b_along)
    perp_right_B = perp_right(*tan_B)
    perp_left_B = perp_left(*tan_B)

    A_pt = hwy_line.interpolate(a_along)
    B_pt = hwy_line.interpolate(b_along)

    print(f'Session {SESSION_INDEX}:')
    print(f'  HOME (50 m before A): along={home_along:.0f} m, ({home_lat:.6f}, {home_lon:.6f})')
    print(f'  A: along={a_along:.0f} m, ({from_xy(A_pt.x, A_pt.y)[0]:.6f}, {from_xy(A_pt.x, A_pt.y)[1]:.6f})')
    print(f'  B: along={b_along:.0f} m, ({from_xy(B_pt.x, B_pt.y)[0]:.6f}, {from_xy(B_pt.x, B_pt.y)[1]:.6f})')
    print(f'  Strip length: {b_along - a_along:.0f} m')
    print(f'  Constants: kinematic={KINEMATIC_LEN_M:.1f} m, perp_transect={CLOSING_TRANSECT_LEN_M:.1f} m, R_arc={CLOSING_ARC_R_M:.0f} m (constant)')

    items = []
    idx = 0; dj = 1

    # === Header ===
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

    # === Kinematic line: K1 at -101.5 perp_right of tan_A from A, K2 at +25 perp_right of tan_A from A ===
    # K2 at survey-start side (matches survey offset), K1 on opposite side. Line length = 25 - (-101.5) = 126.5 m.
    K2_perp_offset = TRANSECT_OFFSET_M                       # +25
    K1_perp_offset = K2_perp_offset - KINEMATIC_LEN_M        # -101.5
    K1_x = A_pt.x + perp_right_A[0] * K1_perp_offset
    K1_y = A_pt.y + perp_right_A[1] * K1_perp_offset
    K2_x = A_pt.x + perp_right_A[0] * K2_perp_offset
    K2_y = A_pt.y + perp_right_A[1] * K2_perp_offset
    K1_lat, K1_lon = from_xy(K1_x, K1_y)
    K2_lat, K2_lon = from_xy(K2_x, K2_y)
    K1_amsl = terrain_amsl(K1_lat, K1_lon) + AGL
    K2_amsl = terrain_amsl(K2_lat, K2_lon) + AGL
    items.append(wp_simple(16, K1_lat, K1_lon, K1_amsl, AGL, dj, idx))
    idx += 1; dj += 1
    items.append(wp_simple(16, K2_lat, K2_lon, K2_amsl, AGL, dj, idx))
    idx += 1; dj += 1

    # === Figure-8 centered at K2 ===
    fig8 = fig8_waypoints(lat=K2_lat, lon=K2_lon, alt_amsl=K2_amsl,
                          speed=SPEED, duration=FIG8_DURATION_S, frame=0)
    for wp in fig8:
        la = wp['params'][4]; lo = wp['params'][5]
        a = terrain_amsl(la, lo) + AGL
        wp['params'][6] = a
        items.append(wp_simple(16, la, lo, a, AGL, dj, idx))
        idx += 1; dj += 1

    # === Survey transect at +25 m perp_right of tan_S (forward direction), sparse via DP ===
    # IMPORTANT: ensure the final offset_pt is EXACTLY at b_along so anchor = item 18.
    offset_pts = []
    sample_step = 25.0
    s = a_along
    while True:
        s_clamped = min(s, b_along)
        p = hwy_line.interpolate(s_clamped)
        t = tangent_at_along(hwy_line, s_clamped)
        pr = perp_right(*t)
        ox = p.x + pr[0] * TRANSECT_OFFSET_M
        oy = p.y + pr[1] * TRANSECT_OFFSET_M
        offset_pts.append((ox, oy))
        if s_clamped >= b_along:
            break
        s += sample_step
    survey_dp = douglas_peucker(offset_pts, DP_TOLERANCE_M)
    print(f'  Survey waypoints: {len(offset_pts)} dense -> {len(survey_dp)} after DP')
    # Sanity check: last DP point should equal anchor (B_pt + perp_right_B * 25)
    expected_anchor = (B_pt.x + perp_right_B[0] * TRANSECT_OFFSET_M,
                       B_pt.y + perp_right_B[1] * TRANSECT_OFFSET_M)
    actual_last = survey_dp[-1]
    err = math.hypot(actual_last[0] - expected_anchor[0], actual_last[1] - expected_anchor[1])
    assert err < 0.1, f'anchor mismatch: survey_dp[-1] = {actual_last}, expected = {expected_anchor}, err = {err:.3f} m'
    print(f'  anchor sanity check: survey_dp[-1] matches expected to {err*1000:.1f} mm')

    for (x, y) in survey_dp:
        la, lo = from_xy(x, y)
        a = terrain_amsl(la, lo) + AGL
        items.append(wp_simple(16, la, lo, a, AGL, dj, idx))
        idx += 1; dj += 1

    # === Closing curve: CONSTANT-R CIRCLE (Option A, 2026-06-29 revision) ===
    # Anchor = last survey WP (at b_along, +25 m perp_right of tan_B).
    #   * Tangent 1: from anchor heading tan_B, length 25 m
    #   * Arc: 270° clockwise around (tangent_1_end + R·perp_right_B), constant R = 50 m
    #   * Arc end lands at (anchor + 75·tan_B + 50·perp_right_B), heading perp_left — at corridor right edge perpendicular
    #   * Straight perpendicular transect follows (200 m perp_left from arc end)
    anchor_x = B_pt.x + perp_right_B[0] * TRANSECT_OFFSET_M
    anchor_y = B_pt.y + perp_right_B[1] * TRANSECT_OFFSET_M
    R = CLOSING_ARC_R_M
    L_t1 = CLOSING_TANGENT_1_LEN_M
    sweep = 3 * math.pi / 2

    # --- Tangent 1 end ---
    t1_end_x = anchor_x + L_t1 * tan_B[0]
    t1_end_y = anchor_y + L_t1 * tan_B[1]
    t1_lat, t1_lon = from_xy(t1_end_x, t1_end_y)
    t1_amsl = terrain_amsl(t1_lat, t1_lon) + AGL
    items.append(wp_simple(16, t1_lat, t1_lon, t1_amsl, AGL, dj, idx))
    idx += 1; dj += 1

    # --- Circle arc: center at tangent_1_end + R*perp_right_B; 270° clockwise sweep ---
    cx = t1_end_x + R * perp_right_B[0]
    cy = t1_end_y + R * perp_right_B[1]
    # Entry-point angle from center (in global radians):
    theta_entry = math.atan2(t1_end_y - cy, t1_end_x - cx)
    # Sweep 270° clockwise = θ decreases by 3π/2:
    n_inter = CLOSING_ARC_SAMPLES   # 8
    n_segments = n_inter + 1
    for k_step in range(1, n_segments + 1):
        frac = k_step / n_segments
        theta = theta_entry - sweep * frac
        x = cx + R * math.cos(theta)
        y = cy + R * math.sin(theta)
        la, lo = from_xy(x, y)
        a = terrain_amsl(la, lo) + AGL
        items.append(wp_simple(16, la, lo, a, AGL, dj, idx))
        idx += 1; dj += 1
    # After loop: arc end at (x, y) with heading perp_left (analytical: anchor + (L_t1+R)·tan_B + R·perp_right_B)
    arc_end_x, arc_end_y = x, y
    print(f'  Arc: L_arc={R*sweep:.1f} m, R={R:.0f} m, end=({from_xy(arc_end_x, arc_end_y)})')

    # === Straight perpendicular transect: from ARC END heading perp_left, length 200 m ===
    # The arc lands at corridor right edge perpendicular; the straight tangent IS the cross-line transect.
    transect_end_x = arc_end_x + CLOSING_TRANSECT_LEN_M * perp_left_B[0]
    transect_end_y = arc_end_y + CLOSING_TRANSECT_LEN_M * perp_left_B[1]
    te_lat, te_lon = from_xy(transect_end_x, transect_end_y)
    te_amsl = terrain_amsl(te_lat, te_lon) + AGL
    items.append(wp_simple(16, te_lat, te_lon, te_amsl, AGL, dj, idx))
    idx += 1; dj += 1

    # === LOITER_UNLIM at end of straight transect ===
    items.append(wp_simple(17, te_lat, te_lon, te_amsl, AGL, dj, idx))
    idx += 1; dj += 1

    print(f'  Total items: {len(items)}')

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

    out_path = os.path.join(OUT_DIR, f'Fergus50_S{SESSION_INDEX:02d}_AB.plan')
    with open(out_path, 'wb') as f:
        f.write(json.dumps(plan, separators=(',', ':')).encode('utf-8'))
    print(f'Wrote: {out_path}')


if __name__ == '__main__':
    main()
