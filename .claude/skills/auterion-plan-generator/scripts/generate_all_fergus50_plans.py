"""Generate all 20 Fergus50 .plan files (10 sessions × AB/BA directions).

Per the v7 spec (2026-06-29):
  - Mission 1 (AB, session start): kinematic + figure-8 + survey + tangent_1 + arc + perp_transect + LOITER
  - Mission 2 (BA, session end): survey + tangent_1 + arc + perp_transect + figure-8 + kinematic + LOITER
  - Cal order REVERSES between AB (kinematic first, fig-8 second) and BA (fig-8 first, kinematic second).
  - Closing arc: R = AGL = 50 m constant, 270° clockwise, lands at corridor right edge perpendicular.
  - Perpendicular transect: 200 m straight in perp_left of forward; crosses corridor + 50 m margin past exit.
  - BA end-cal kinematic line: from fig-8 centroid toward landing position (= A_along − 50 m on centerline).

HOME for each mission is 50 m outside the corridor on the centerline (= takeoff position).
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
N_STRIPS = 10                          # original whole-highway strip count (for reference only)
# --- 2026-07-03 revision: sessions 8, 9, 10 already flown; regenerate only 1..6 with 15% longer strips ---
N_NEW_STRIPS = 6                       # new strip count for the remaining west portion
COMPLETED_OLD_SESSIONS = {8, 9, 10}    # skip these — already flown, don't overwrite
# EAST boundary of remaining area = start of the easternmost completed old session (= old S08's A_along)
# Rally point (per Ryan's 8BA modification): +37.3 m E, +45.4 m N of last WP, altitude 45.72 m
RALLY_OFFSET_EAST_M = 37.3
RALLY_OFFSET_NORTH_M = 45.4
RALLY_ALT_M = 45.72

# Spec-derived constants (v7, 2026-06-29)
KINEMATIC_LEN_M    = SPEED * 11.0     # 126.5 m
TRANSECT_OFFSET_M  = AGL / 2          # 25 m
CLOSING_TRANSECT_LEN_M = 200.0        # straight perpendicular transect length
CLOSING_TANGENT_1_LEN_M = AGL / 2     # 25 m straight before arc
CLOSING_ARC_R_M    = AGL              # 50 m constant arc radius
CLOSING_ARC_SAMPLES = 8               # 8 intermediate WPs on 270° arc
DP_TOLERANCE_M     = 5.0
FIG8_DURATION_S    = 15.0
HOME_OFFSET_M      = 50.0


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
    """90 deg CLOCKWISE rotation = right of forward in plan view (y-up)."""
    return (ty, -tx)


def perp_left(tx, ty):
    return (-ty, tx)


TERRAIN_TOL_M      = 10.0             # max |AGL deviation| between WPs (± from target AGL)
TERRAIN_SAMPLE_M   = 5.0              # DEM sample step along a segment
TERRAIN_MIN_SEG_M  = 5.0              # don't split segments shorter than this
UNRESOLVABLE_LOG   = []               # (plan_name, segment_desc, seg_len_m, max_dev_m) collected during generation


def _terrain_refine_segment(p1, p2, agl, from_xy_fn, plan_name, seg_desc):
    """Recursively subdivide a horizontal segment (p1, p2) to keep target-AGL-line vs interpolated-AMSL
    deviation within TERRAIN_TOL_M. Each pt is (x, y, amsl). Returns [p1, ..., p2] with inserted WPs."""
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    seg_len = math.hypot(dx, dy)
    if seg_len < TERRAIN_MIN_SEG_M:
        return [p1, p2]
    n_samples = max(2, int(seg_len / TERRAIN_SAMPLE_M))
    max_dev = 0.0
    max_dev_k = None
    for k in range(1, n_samples):
        frac = k / n_samples
        sx = p1[0] + dx * frac
        sy = p1[1] + dy * frac
        interp_amsl = p1[2] + (p2[2] - p1[2]) * frac
        la, lo = from_xy_fn(sx, sy)
        terrain = terrain_amsl(la, lo)
        target_amsl = terrain + agl
        dev = target_amsl - interp_amsl
        if abs(dev) > abs(max_dev):
            max_dev = dev
            max_dev_k = k
    if abs(max_dev) <= TERRAIN_TOL_M or max_dev_k is None:
        return [p1, p2]
    # Log if we're unresolvable-close (split will still happen — option C = override)
    frac = max_dev_k / n_samples
    split_x = p1[0] + dx * frac
    split_y = p1[1] + dy * frac
    dist_from_p1 = math.hypot(split_x - p1[0], split_y - p1[1])
    dist_from_p2 = math.hypot(split_x - p2[0], split_y - p2[1])
    if dist_from_p1 < 30.0 or dist_from_p2 < 30.0:
        UNRESOLVABLE_LOG.append((plan_name, seg_desc, seg_len, max_dev, dist_from_p1, dist_from_p2))
    la, lo = from_xy_fn(split_x, split_y)
    split_amsl = terrain_amsl(la, lo) + agl
    split_pt = (split_x, split_y, split_amsl)
    left = _terrain_refine_segment(p1, split_pt, agl, from_xy_fn, plan_name, seg_desc)
    right = _terrain_refine_segment(split_pt, p2, agl, from_xy_fn, plan_name, seg_desc)
    return left[:-1] + right


def terrain_refine_polyline(pts, agl, from_xy_fn, plan_name, seg_desc):
    """Apply terrain refinement to a polyline (list of (x, y, amsl) points).
    Returns the refined polyline with inserted intermediate WPs."""
    if len(pts) < 2:
        return list(pts)
    result = [pts[0]]
    for i in range(len(pts) - 1):
        sub = _terrain_refine_segment(pts[i], pts[i + 1], agl, from_xy_fn, plan_name, f'{seg_desc}[{i}]')
        result.extend(sub[1:])
    return result


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


def add_rally_point(plan):
    """Append a rally point near the last nav WP of the plan, matching Ryan's 8BA pattern."""
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


def generate_plan(hwy_line, from_xy, session_index, direction):
    """Generate a single .plan dict. direction = 'AB' or 'BA'."""
    assert direction in ('AB', 'BA')

    # 2026-07-03: split the remaining west area (highway [0, east_boundary]) into N_NEW_STRIPS
    old_strip_len = hwy_line.length / N_STRIPS
    east_boundary_along = (min(COMPLETED_OLD_SESSIONS) - 1) * old_strip_len   # start of old S08 = 7 * old_strip
    strip_len = east_boundary_along / N_NEW_STRIPS
    a_along = (session_index - 1) * strip_len
    b_along = session_index * strip_len

    # Direction-specific setup
    if direction == 'AB':
        survey_start_along = a_along
        survey_end_along = b_along
        forward_sign = +1            # forward direction = +tangent
        home_along = a_along - HOME_OFFSET_M
        cal_at_start = True
        landing_along = None         # AB doesn't have an end-cal kinematic
    else:  # BA
        survey_start_along = b_along
        survey_end_along = a_along
        forward_sign = -1
        home_along = b_along + HOME_OFFSET_M
        cal_at_start = False
        landing_along = a_along - HOME_OFFSET_M  # = Mission 1's HOME, where the team is parked

    # HOME — clamp to line endpoints (shapely.interpolate treats negative as offset-from-end)
    home_along = max(0.0, min(hwy_line.length, home_along))
    home_pt = hwy_line.interpolate(home_along)
    home_lat, home_lon = from_xy(home_pt.x, home_pt.y)
    home_ground_amsl = terrain_amsl(home_lat, home_lon)

    # Survey-start tangents (where the survey BEGINS; for AB this is A, for BA this is B)
    start_pt = hwy_line.interpolate(survey_start_along)
    tan_start_raw = tangent_at_along(hwy_line, survey_start_along)
    tan_start = (forward_sign * tan_start_raw[0], forward_sign * tan_start_raw[1])
    perp_right_start = perp_right(*tan_start)

    # Survey-end tangents (where the survey ENDS; for AB this is B, for BA this is A — this is also the "anchor" position)
    end_pt = hwy_line.interpolate(survey_end_along)
    tan_end_raw = tangent_at_along(hwy_line, survey_end_along)
    tan_end = (forward_sign * tan_end_raw[0], forward_sign * tan_end_raw[1])
    perp_right_end = perp_right(*tan_end)
    perp_left_end = perp_left(*tan_end)

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

    # === Start cal (AB only): kinematic line + figure-8 ===
    if cal_at_start:
        # K2 at +25 perp_right of forward at survey start (= survey start offset side)
        K2_perp_offset = TRANSECT_OFFSET_M                       # +25
        K1_perp_offset = K2_perp_offset - KINEMATIC_LEN_M        # -101.5
        K1_x = start_pt.x + perp_right_start[0] * K1_perp_offset
        K1_y = start_pt.y + perp_right_start[1] * K1_perp_offset
        K2_x = start_pt.x + perp_right_start[0] * K2_perp_offset
        K2_y = start_pt.y + perp_right_start[1] * K2_perp_offset
        K1_lat, K1_lon = from_xy(K1_x, K1_y)
        K2_lat, K2_lon = from_xy(K2_x, K2_y)
        K1_amsl = terrain_amsl(K1_lat, K1_lon) + AGL
        K2_amsl = terrain_amsl(K2_lat, K2_lon) + AGL
        items.append(wp_simple(16, K1_lat, K1_lon, K1_amsl, AGL, dj, idx))
        idx += 1; dj += 1
        items.append(wp_simple(16, K2_lat, K2_lon, K2_amsl, AGL, dj, idx))
        idx += 1; dj += 1
        # Figure-8 centered at K2
        fig8 = fig8_waypoints(lat=K2_lat, lon=K2_lon, alt_amsl=K2_amsl,
                              speed=SPEED, duration=FIG8_DURATION_S, frame=0)
        for wp in fig8:
            la = wp['params'][4]; lo = wp['params'][5]
            a = terrain_amsl(la, lo) + AGL
            items.append(wp_simple(16, la, lo, a, AGL, dj, idx))
            idx += 1; dj += 1

    # === Survey at +25 m perp_right of forward, sparse via DP ===
    # Walk along the highway from survey_start_along to survey_end_along, sampling every 25 m and offsetting by +25 perp_right
    sample_step = 25.0
    offset_pts = []
    s = 0.0
    survey_length = abs(survey_end_along - survey_start_along)
    while True:
        s_clamped = min(s, survey_length)
        # Convert progress along the survey to actual along-distance on the highway
        actual_along = survey_start_along + forward_sign * s_clamped
        p = hwy_line.interpolate(actual_along)
        t_raw = tangent_at_along(hwy_line, actual_along)
        t = (forward_sign * t_raw[0], forward_sign * t_raw[1])
        pr = perp_right(*t)
        ox = p.x + pr[0] * TRANSECT_OFFSET_M
        oy = p.y + pr[1] * TRANSECT_OFFSET_M
        offset_pts.append((ox, oy))
        if s_clamped >= survey_length:
            break
        s += sample_step
    survey_dp = douglas_peucker(offset_pts, DP_TOLERANCE_M)

    # Sanity: last DP point should match the computed anchor (= end_pt + perp_right_end * 25)
    expected_anchor = (end_pt.x + perp_right_end[0] * TRANSECT_OFFSET_M,
                       end_pt.y + perp_right_end[1] * TRANSECT_OFFSET_M)
    err = math.hypot(survey_dp[-1][0] - expected_anchor[0], survey_dp[-1][1] - expected_anchor[1])
    assert err < 0.1, f'session {session_index} {direction}: anchor mismatch err={err:.3f}'

    # Terrain-refine the survey polyline (attach AMSL to each DP pt, then subdivide by 10 m AGL tolerance)
    plan_name = f'S{session_index:02d}_{direction}'
    survey_polyline = []
    for (x, y) in survey_dp:
        la, lo = from_xy(x, y)
        a = terrain_amsl(la, lo) + AGL
        survey_polyline.append((x, y, a))
    survey_refined = terrain_refine_polyline(survey_polyline, AGL, from_xy, plan_name, 'survey')
    n_survey_added = len(survey_refined) - len(survey_polyline)
    for (x, y, a) in survey_refined:
        la, lo = from_xy(x, y)
        items.append(wp_simple(16, la, lo, a, AGL, dj, idx))
        idx += 1; dj += 1

    # === Closing block: tangent_1 + arc + perp_transect ===
    # Anchor = last survey WP
    anchor_x = expected_anchor[0]
    anchor_y = expected_anchor[1]
    R = CLOSING_ARC_R_M
    L_t1 = CLOSING_TANGENT_1_LEN_M
    sweep = 3 * math.pi / 2

    # === Build the closing block as a single terrain-refinable polyline ===
    # anchor → tangent-1 end → arc samples (9 pts) → perpendicular transect end
    # Then refine and emit as WPs (skip the anchor itself since it's already emitted as the last survey WP).
    closing_polyline = []
    # Tangent 1 end
    t1_end_x = anchor_x + L_t1 * tan_end[0]
    t1_end_y = anchor_y + L_t1 * tan_end[1]
    t1_amsl = terrain_amsl(*from_xy(t1_end_x, t1_end_y)) + AGL
    closing_polyline.append((anchor_x, anchor_y, terrain_amsl(*from_xy(anchor_x, anchor_y)) + AGL))
    closing_polyline.append((t1_end_x, t1_end_y, t1_amsl))
    # Arc: 270° clockwise around (tangent_1_end + R * perp_right_end)
    cx = t1_end_x + R * perp_right_end[0]
    cy = t1_end_y + R * perp_right_end[1]
    theta_entry = math.atan2(t1_end_y - cy, t1_end_x - cx)
    n_segments = CLOSING_ARC_SAMPLES + 1
    arc_end_x = arc_end_y = None
    for k_step in range(1, n_segments + 1):
        frac = k_step / n_segments
        theta = theta_entry - sweep * frac
        x = cx + R * math.cos(theta)
        y = cy + R * math.sin(theta)
        a = terrain_amsl(*from_xy(x, y)) + AGL
        closing_polyline.append((x, y, a))
        arc_end_x, arc_end_y = x, y
    # Perpendicular transect end
    transect_end_x = arc_end_x + CLOSING_TRANSECT_LEN_M * perp_left_end[0]
    transect_end_y = arc_end_y + CLOSING_TRANSECT_LEN_M * perp_left_end[1]
    te_amsl = terrain_amsl(*from_xy(transect_end_x, transect_end_y)) + AGL
    closing_polyline.append((transect_end_x, transect_end_y, te_amsl))
    # Refine (skip the first pt = anchor, which was already emitted as the last survey WP)
    closing_refined = terrain_refine_polyline(closing_polyline, AGL, from_xy, plan_name, 'closing')
    n_closing_added = len(closing_refined) - len(closing_polyline)
    for (x, y, a) in closing_refined[1:]:   # skip anchor
        la, lo = from_xy(x, y)
        items.append(wp_simple(16, la, lo, a, AGL, dj, idx))
        idx += 1; dj += 1
    # Save the final transect end coords for the BA end-cal block
    te_lat, te_lon = from_xy(transect_end_x, transect_end_y)

    # === End cal (BA only): figure-8 + kinematic line toward landing position ===
    if not cal_at_start:
        # Figure-8 centered at perp transect end
        fig8 = fig8_waypoints(lat=te_lat, lon=te_lon, alt_amsl=te_amsl,
                              speed=SPEED, duration=FIG8_DURATION_S, frame=0)
        for wp in fig8:
            la = wp['params'][4]; lo = wp['params'][5]
            a = terrain_amsl(la, lo) + AGL
            items.append(wp_simple(16, la, lo, a, AGL, dj, idx))
            idx += 1; dj += 1
        # Kinematic line: from figure-8 centroid (= perp transect end) toward landing position
        landing_pt = hwy_line.interpolate(max(0.0, min(hwy_line.length, landing_along)))
        # Unit vector from te to landing position
        vx = landing_pt.x - transect_end_x
        vy = landing_pt.y - transect_end_y
        v_norm = math.hypot(vx, vy)
        ux = vx / v_norm
        uy = vy / v_norm
        kin_end_x = transect_end_x + KINEMATIC_LEN_M * ux
        kin_end_y = transect_end_y + KINEMATIC_LEN_M * uy
        kin_lat, kin_lon = from_xy(kin_end_x, kin_end_y)
        kin_amsl = terrain_amsl(kin_lat, kin_lon) + AGL
        items.append(wp_simple(16, kin_lat, kin_lon, kin_amsl, AGL, dj, idx))
        idx += 1; dj += 1
        # LOITER at end of kinematic line
        items.append(wp_simple(17, kin_lat, kin_lon, kin_amsl, AGL, dj, idx))
        idx += 1; dj += 1
    else:
        # AB: LOITER at end of perp transect
        items.append(wp_simple(17, te_lat, te_lon, te_amsl, AGL, dj, idx))
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
    return plan, len(items), n_survey_added, n_closing_added


def main():
    print('Loading highway centerline...')
    highway = load_linestring(KML_HIGHWAY)
    ref_lat = sum(p[0] for p in highway) / len(highway)
    ref_lon = sum(p[1] for p in highway) / len(highway)
    to_xy, from_xy = make_back_proj(ref_lat, ref_lon)
    hwy_xy = [to_xy(*p) for p in highway]
    hwy_line = LineString(hwy_xy)
    print(f'  Highway length: {hwy_line.length:.0f} m, {N_STRIPS} sessions, strip_len = {hwy_line.length/N_STRIPS:.0f} m')

    import shutil
    E_DRIVE = 'E:/Fergus_Electric_Lidar/Lidar_mission_plans'
    # 2026-07-03: only regenerate new sessions 1..N_NEW_STRIPS (S08-S10 stay as-flown)
    for session_index in range(1, N_NEW_STRIPS + 1):
        for direction in ('AB', 'BA'):
            plan, n_items, n_survey_added, n_closing_added = generate_plan(hwy_line, from_xy, session_index, direction)
            fname = f'Fergus50_S{session_index:02d}_{direction}.plan'
            out_path = os.path.join(OUT_DIR, fname)
            with open(out_path, 'wb') as f:
                f.write(json.dumps(plan, separators=(',', ':')).encode('utf-8'))
            # Copy to E-drive
            if os.path.isdir(E_DRIVE):
                shutil.copy(out_path, os.path.join(E_DRIVE, fname))
            print(f'  Wrote: {fname}  ({n_items} items, +{n_survey_added} survey, +{n_closing_added} closing terrain-inserts)')
    # Report unresolvable-close insertions (option C — we still added them, just flagging)
    if UNRESOLVABLE_LOG:
        print()
        print(f'  {len(UNRESOLVABLE_LOG)} terrain-forced WP inserts violated the 30 m spacing floor (override applied per spec):')
        by_plan = {}
        for name, seg, seg_len, dev, d1, d2 in UNRESOLVABLE_LOG:
            by_plan.setdefault(name, []).append((seg, seg_len, dev, min(d1, d2)))
        for name in sorted(by_plan):
            entries = by_plan[name]
            print(f'    {name}: {len(entries)} inserts, max |dev| = {max(abs(d) for _,_,d,_ in entries):.1f} m, tightest spacing = {min(s for _,_,_,s in entries):.1f} m')
    else:
        print('  All terrain-forced inserts satisfied the 30 m spacing floor naturally.')


if __name__ == '__main__':
    main()
