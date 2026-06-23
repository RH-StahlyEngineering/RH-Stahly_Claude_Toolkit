"""
Generate Fergus3.plan + Fergus4.plan: Pair 1 west of Fergus2.

Pair geometry:
  Fergus3 east end = Fergus2 west end = (47.350576, -108.851527)
  Pair 1 meeting point = 1.8 km west of F2_W along the KML road
  Fergus4 west end    = 3.6 km west of F2_W along the KML road

Bracketing (one envelope per pair):
  Fergus3 = START cal flight  → outer items: [cmd530, 11x fig-8, CorridorScan]
  Fergus4 = END cal flight    → outer items: [cmd530, CorridorScan, 11x fig-8]

Template: copied from Fergus1.plan / Fergus2.plan (AMC-native CorridorScan).
Polyline: multi-point, decimated with Douglas-Peucker (tol 5 m).
Altitudes: DEM-baked (USGS 3DEP local raster).
Output: minified, LF-only, UTF-8 no BOM.
"""
import json, math, os, re, sys, hashlib

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SKILL_DIR, 'scripts'))
from figure8 import fig8_waypoints
from dem_lookup import ensure_dem_for_bbox, terrain_amsl, bake_amsl

KML_PATH       = 'C:/Users/rharbach.STAHLY/Downloads/HighwayCenterline.kml'
F1_TEMPLATE    = 'C:/Users/rharbach.STAHLY/Documents/Auterion Mission Control/Missions/Fergus1.plan'
OUT_DIR        = 'C:/Users/rharbach.STAHLY/Documents/Auterion Mission Control/Missions'
F2_W           = (47.350576, -108.851527)  # Fergus2 west end = Pair1 east end
TILE_LEN_M     = 1800.0
AGL            = 70.104
SPEED          = 8.0
FIG8_DURATION  = 15.0
DECIMATE_TOL_M = 5.0
TURNAROUND_M   = 60.96
LINE_SPACING_M = AGL  # by skill convention (90° FOV: line spacing = AGL)
HALF_LS_M      = LINE_SPACING_M / 2

# ------------------------------------------------------------ KML ----------
def load_centerline(path):
    with open(path, 'r', encoding='utf-8') as f:
        txt = f.read()
    m = re.search(r'<LineString[\s\S]*?<coordinates>([\s\S]+?)</coordinates>', txt)
    coords = m.group(1).strip().split()
    return [(float(c.split(',')[1]), float(c.split(',')[0])) for c in coords]

def hav(a, b):
    R = 6371000.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dl = math.radians(b[1] - a[1]); dp = p2 - p1
    x = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*R*math.asin(math.sqrt(x))

def nearest_idx(pts, target):
    return min(range(len(pts)), key=lambda i: hav(pts[i], target))

def walk_west_path(pts, start_idx, target_dist):
    """Return [pts visited going west, ending at interpolated target_dist point].
    Includes pts[start_idx] as the first vertex."""
    out = [pts[start_idx]]
    acc = 0.0
    i = start_idx
    while i > 0:
        step = hav(pts[i], pts[i-1])
        if acc + step >= target_dist:
            frac = (target_dist - acc) / step
            lat = pts[i][0] + frac * (pts[i-1][0] - pts[i][0])
            lon = pts[i][1] + frac * (pts[i-1][1] - pts[i][1])
            out.append((lat, lon))
            return out
        out.append(pts[i-1])
        acc += step
        i -= 1
    return out

# ----------------------------------------------- Douglas-Peucker ----------
def perp_dist_m(p, a, b):
    """Perpendicular distance from p to line a-b, in meters (local equirect)."""
    lat0 = (a[0] + b[0]) / 2
    m_lat = 111132; m_lon = 111132 * math.cos(math.radians(lat0))
    px = (p[1] - a[1]) * m_lon; py = (p[0] - a[0]) * m_lat
    bx = (b[1] - a[1]) * m_lon; by = (b[0] - a[0]) * m_lat
    L = math.hypot(bx, by)
    if L == 0: return math.hypot(px, py)
    return abs(px*by - py*bx) / L

def douglas_peucker(pts, tol):
    if len(pts) < 3: return list(pts)
    dmax = 0.0; idx = 0
    for i in range(1, len(pts)-1):
        d = perp_dist_m(pts[i], pts[0], pts[-1])
        if d > dmax:
            dmax = d; idx = i
    if dmax > tol:
        L = douglas_peucker(pts[:idx+1], tol)
        R = douglas_peucker(pts[idx:], tol)
        return L[:-1] + R
    return [pts[0], pts[-1]]

# --------------------------- Perpendicular offsets + Items population ----------
def _perp_offset_one(p, tangent_dlat, tangent_dlon, offset_m):
    """Offset point p by offset_m perpendicular to (tangent_dlat, tangent_dlon).
    Positive offset = 90° CCW from forward = LEFT of motion."""
    m_lat = 111132.0
    m_lon = 111132.0 * math.cos(math.radians(p[0]))
    # Tangent in local meters (east=x, north=y)
    tx = tangent_dlon * m_lon
    ty = tangent_dlat * m_lat
    n = math.hypot(tx, ty)
    if n == 0: return p
    # Perpendicular CCW: (-ty, tx) / n
    px = -ty / n
    py =  tx / n
    return (p[0] + offset_m * py / m_lat,
            p[1] + offset_m * px / m_lon)

def perp_offset_path(polyline, offset_m):
    """Return polyline offset perpendicular by offset_m (positive = left of forward)."""
    out = []
    N = len(polyline)
    for i, p in enumerate(polyline):
        if i == 0:
            tdla = polyline[1][0] - p[0]; tdlo = polyline[1][1] - p[1]
        elif i == N - 1:
            tdla = p[0] - polyline[i-1][0]; tdlo = p[1] - polyline[i-1][1]
        else:
            tdla = polyline[i+1][0] - polyline[i-1][0]
            tdlo = polyline[i+1][1] - polyline[i-1][1]
        out.append(_perp_offset_one(p, tdla, tdlo, offset_m))
    return out

def extend_endpoint(p_end, p_prev, distance_m):
    """Extend p_end OUTWARD past p_prev->p_end by distance_m."""
    m_lat = 111132.0
    m_lon = 111132.0 * math.cos(math.radians(p_end[0]))
    dx = (p_end[1] - p_prev[1]) * m_lon
    dy = (p_end[0] - p_prev[0]) * m_lat
    n = math.hypot(dx, dy)
    if n == 0: return p_end
    return (p_end[0] + distance_m * dy / (n * m_lat),
            p_end[1] + distance_m * dx / (n * m_lon))

def build_cross_line(polyline, agl_target, *, cross_margin=25.0, corridor_width=140.208, line_spacing=70.104):
    """Build the 2-waypoint cross-line for a CorridorScan with EntryPoint=2.

    Per skill canonical:
      - Perpendicular to flight lines (perpendicular to local polyline tangent at exit)
      - Centered ONE LINE_SPACING inset from the survey exit waypoint, toward
        polygon interior (= away from the exit, along the polyline tangent reversed)
      - Length = CorridorWidth + 2 * CROSS_MARGIN (extends past polygon edges)
      - frame=0 with per-endpoint DEM-baked AMSL (pitfall #3)

    Polyline is ordered [far_end, ..., exit_end]; exit = polyline[-1].
    Returns (wp_start, wp_end) as 2 SimpleItem dicts with doJumpId=0 (caller renumbers).
    """
    exit_pt = polyline[-1]
    prev_pt = polyline[-2]

    lat0 = (exit_pt[0] + prev_pt[0]) / 2
    m_lat = 111132.0
    m_lon = 111132.0 * math.cos(math.radians(lat0))

    # Tangent vector (prev → exit) in local meters
    tan_x = (exit_pt[1] - prev_pt[1]) * m_lon
    tan_y = (exit_pt[0] - prev_pt[0]) * m_lat
    tan_len = math.hypot(tan_x, tan_y)
    if tan_len == 0:
        raise ValueError("Polyline has zero-length last segment — cannot derive tangent")
    tx_u = tan_x / tan_len
    ty_u = tan_y / tan_len

    # Cross-line CENTER: ONE LINE_SPACING inset from exit, toward interior.
    # "Toward interior" = opposite of tangent (which points outward toward exit).
    cx = -line_spacing * tx_u
    cy = -line_spacing * ty_u

    # Perpendicular unit vector (90° CCW from tangent in local frame)
    perp_x = -ty_u
    perp_y =  tx_u

    half_len = corridor_width / 2 + cross_margin

    end_a_x = cx + half_len * perp_x
    end_a_y = cy + half_len * perp_y
    end_b_x = cx - half_len * perp_x
    end_b_y = cy - half_len * perp_y

    end_a = (exit_pt[0] + end_a_y / m_lat, exit_pt[1] + end_a_x / m_lon)
    end_b = (exit_pt[0] + end_b_y / m_lat, exit_pt[1] + end_b_x / m_lon)

    alt_a = bake_amsl(end_a[0], end_a[1], agl_target)
    alt_b = bake_amsl(end_b[0], end_b[1], agl_target)

    def _wp(lat, lon, alt):
        return {'autoContinue': True, 'command': 16, 'doJumpId': 0,
                'frame': 0, 'groupTag': 0,
                'params': [0, 0, 0, None, lat, lon, alt],
                'type': 'SimpleItem'}

    return _wp(end_a[0], end_a[1], alt_a), _wp(end_b[0], end_b[1], alt_b)

def _wp_inner(lat, lon, alt_amsl, doJumpId, frame=0):
    return {'autoContinue': True, 'command': 16, 'doJumpId': doJumpId,
            'frame': frame, 'groupTag': 0,
            'params': [0, 0, 0, None, lat, lon, alt_amsl],
            'type': 'SimpleItem'}

def _simple(command, params, doJumpId, frame=2):
    return {'autoContinue': True, 'command': command, 'doJumpId': doJumpId,
            'frame': frame, 'groupTag': 0,
            'params': list(params), 'type': 'SimpleItem'}

def build_corridor_inner_items(polyline, agl_target, speed, *, dj_start=2):
    """Compute the CorridorScan's TransectStyleComplexItem.Items array for
    a 2-transect (CorridorWidth = 2 * AGL) scan with EntryPoint=2 (entry/exit
    at polyline END). Mirrors the structure AMC generated for Fergus1/Fergus2.

    Pattern (entry at polyline[-1], far at polyline[0]):
      entry_TA_L, cmd178(speed), polyline_END_L, cmd206(0),
      [polyline[N-2..1]_L],
      cmd1001(-2,-2), cmd1000(camera), cmd532, cmd530, cmd93,
      polyline_START_L, cmd206(25),
      far_TA_L, far_TA_R, polyline_START_R, cmd206(0),
      [polyline[1..N-2]_R], polyline_END_R, cmd206(25), entry_TA_R,
      cmd1000(end), cmd1001(-3,-3), cmd530(0,0...), cmd93
    L = left of forward (= "south" side when polyline goes west).
    R = right of forward.
    Returns (items_list, visual_transect_pts).
    """
    N = len(polyline)
    if N < 2:
        return [], []
    left  = perp_offset_path(polyline, +HALF_LS_M)
    right = perp_offset_path(polyline, -HALF_LS_M)
    # End-cap turnaround extensions
    entry_TA_L = extend_endpoint(left[-1],  left[-2],  TURNAROUND_M)
    entry_TA_R = extend_endpoint(right[-1], right[-2], TURNAROUND_M)
    far_TA_L   = extend_endpoint(left[0],   left[1],   TURNAROUND_M)
    far_TA_R   = extend_endpoint(right[0],  right[1],  TURNAROUND_M)

    # DEM-bake AMSL for each waypoint
    def amsl(p): return bake_amsl(p[0], p[1], agl_target)

    # Build items in Fergus1's pattern
    dj = dj_start
    items = []

    # 1. entry_TA_L (cmd 16, frame 0)
    items.append(_wp_inner(entry_TA_L[0], entry_TA_L[1], amsl(entry_TA_L), dj, frame=0)); dj += 1
    # 2. cmd 178 speed
    items.append(_simple(178, [1, speed, -1, 0, 0, 0, 0], dj)); dj += 1
    # 3. polyline_END_L
    items.append(_wp_inner(left[-1][0], left[-1][1], amsl(left[-1]), dj, frame=0)); dj += 1
    # 4. cmd 206 (camera trigger distance = 0, action = 1 = start)
    items.append(_simple(206, [0, 0, 1, 0, 0, 0, 0], dj)); dj += 1
    # 5. intermediate left points (polyline[N-2..1])
    for k in range(N-2, 0, -1):
        items.append(_wp_inner(left[k][0], left[k][1], amsl(left[k]), dj, frame=0)); dj += 1
    # 6. markers
    items.append(_simple(1001, [-2, -2, -1, -1, 0, 0, 0], dj)); dj += 1
    items.append(_simple(1000, [-90, 0, None, None, 12, 0, 0], dj)); dj += 1
    items.append(_simple(532,  [2, 100, 0, 0, 0, 0, 0], dj)); dj += 1
    items.append(_simple(530,  [0, 2, 0, 0, 0, 0, 0], dj)); dj += 1
    items.append(_simple(93,   [2, -1, -1, -1, 0, 0, 0], dj)); dj += 1
    # 7. polyline_START_L
    items.append(_wp_inner(left[0][0], left[0][1], amsl(left[0]), dj, frame=0)); dj += 1
    # 8. cmd 206 (camera distance = 25)
    items.append(_simple(206, [25, 0, 1, 0, 0, 0, 0], dj)); dj += 1
    # 9. far_TA_L
    items.append(_wp_inner(far_TA_L[0], far_TA_L[1], amsl(far_TA_L), dj, frame=0)); dj += 1
    # 10. far_TA_R (jog)
    items.append(_wp_inner(far_TA_R[0], far_TA_R[1], amsl(far_TA_R), dj, frame=0)); dj += 1
    # 11. polyline_START_R
    items.append(_wp_inner(right[0][0], right[0][1], amsl(right[0]), dj, frame=0)); dj += 1
    # 12. cmd 206 (camera distance = 0)
    items.append(_simple(206, [0, 0, 1, 0, 0, 0, 0], dj)); dj += 1
    # 13. intermediate right points (polyline[1..N-2])
    for k in range(1, N-1):
        items.append(_wp_inner(right[k][0], right[k][1], amsl(right[k]), dj, frame=0)); dj += 1
    # 14. polyline_END_R
    items.append(_wp_inner(right[-1][0], right[-1][1], amsl(right[-1]), dj, frame=0)); dj += 1
    # 15. cmd 206 (camera distance = 25)
    items.append(_simple(206, [25, 0, 1, 0, 0, 0, 0], dj)); dj += 1
    # 16. entry_TA_R
    items.append(_wp_inner(entry_TA_R[0], entry_TA_R[1], amsl(entry_TA_R), dj, frame=0)); dj += 1
    # 17. end markers
    items.append(_simple(1000, [None, None, None, None, 2, 0, 0], dj)); dj += 1
    items.append(_simple(1001, [-3, -3, -1, -1, 0, 0, 0], dj)); dj += 1
    items.append(_simple(530,  [0, 0, 0, 0, 0, 0, 0], dj)); dj += 1
    items.append(_simple(93,   [2, -1, -1, -1, 0, 0, 0], dj)); dj += 1

    # VisualTransectPoints: corridor swath outline (closed)
    # Order matches Fergus1: [entry_TA_L, polyline_END_L, intermediate_L_decreasing,
    # polyline_START_L, far_TA_L, far_TA_R, polyline_START_R, intermediate_R_increasing,
    # polyline_END_R, entry_TA_R]
    vtp = []
    vtp.append([entry_TA_L[0], entry_TA_L[1]])
    vtp.append([left[-1][0], left[-1][1]])
    for k in range(N-2, 0, -1):
        vtp.append([left[k][0], left[k][1]])
    vtp.append([left[0][0], left[0][1]])
    vtp.append([far_TA_L[0], far_TA_L[1]])
    vtp.append([far_TA_R[0], far_TA_R[1]])
    vtp.append([right[0][0], right[0][1]])
    for k in range(1, N-1):
        vtp.append([right[k][0], right[k][1]])
    vtp.append([right[-1][0], right[-1][1]])
    vtp.append([entry_TA_R[0], entry_TA_R[1]])
    return items, vtp

# ----------------------------------- Build plan ----------
def deepcopy_json(obj):
    return json.loads(json.dumps(obj))

def build_plan(template, polyline, plan_home, agl, *, fig8_at_start, fig8_at_end, fig8_centroid_alt_amsl, fig8_centroid_latlon):
    """Construct a new plan modeled on Fergus1 template.

    polyline: list of (lat, lon), ordered AWAY-end first, MEETING-end last.
              EntryPoint=2 → entry/exit at polyline END = meeting point.
    plan_home: (lat, lon, amsl) for plannedHomePosition.
    fig8_at_start / fig8_at_end: include figure-8 waypoints before/after CorridorScan.
    """
    plan = deepcopy_json(template)
    plan['UUID'] = hashlib.sha1(json.dumps(polyline).encode()).hexdigest()
    plan['mission']['plannedHomePosition'] = list(plan_home)

    cs_template = plan['mission']['items'][1]
    cs = deepcopy_json(cs_template)
    cs['polyline'] = [list(p) for p in polyline]

    # Populate inner Items + VisualTransectPoints from the new polyline.
    # Leaving them empty makes AMC's survey panel default to MSL/HGT display
    # — populating them lets AMC render the survey in AGL/terrain-follow mode
    # immediately. AMC will recompute altitudes on open (Pitfall #1).
    inner_items, vtp = build_corridor_inner_items(polyline, agl, SPEED)
    cs['TransectStyleComplexItem']['Items'] = inner_items
    cs['TransectStyleComplexItem']['VisualTransectPoints'] = vtp
    # CameraShots estimate: ~1 shot per AGL meters along polyline length, × 2 transects.
    poly_len = sum(math.hypot(
        (polyline[i+1][1]-polyline[i][1]) * 111132 * math.cos(math.radians(polyline[i][0])),
        (polyline[i+1][0]-polyline[i][0]) * 111132) for i in range(len(polyline)-1))
    cs['TransectStyleComplexItem']['CameraShots'] = max(1, int(2 * poly_len / agl))

    cs['EntryPoint'] = 2
    cs['CorridorWidth'] = 140.208
    tsi = cs['TransectStyleComplexItem']
    tsi['CameraCalc']['DistanceToSurface'] = agl
    tsi['CameraCalc']['AdjustedFootprintSide'] = agl
    tsi['CameraCalc']['AdjustedFootprintFrontal'] = 25
    tsi['CameraCalc']['CameraName'] = 'Manual (no camera specs)'
    tsi['CameraCalc']['DistanceToSurfaceRelative'] = False
    tsi['FlightSpeed'] = SPEED
    tsi['FollowTerrain'] = True
    tsi['TurnAroundDistance'] = TURNAROUND_M

    cmd530 = deepcopy_json(plan['mission']['items'][0])

    # Build figure-8 waypoints with frame=0 + DEM-baked AMSL (skill canonical, pitfall #3).
    # The centroid altitude is already DEM-baked at the meeting point. For a tight fig-8
    # (~40 × 20 m), terrain variation across the vertices is sub-meter — using the
    # centroid AMSL for all 11 vertices is within tolerance. This gives AMC the correct
    # MSL altitude to display in the elevation profile (above the terrain line, not
    # underground), AND the drone still flies at 70 m AGL above the meeting point
    # because the AMSL value = terrain_amsl + AGL.
    fig8 = fig8_waypoints(lat=fig8_centroid_latlon[0],
                          lon=fig8_centroid_latlon[1],
                          alt_amsl=fig8_centroid_alt_amsl,
                          speed=SPEED, duration=FIG8_DURATION, frame=0)
    # Per-vertex DEM refinement: bake AMSL at each vertex to be fully terrain-correct
    for wp in fig8:
        lat = wp['params'][4]; lon = wp['params'][5]
        wp['params'][6] = bake_amsl(lat, lon, agl)

    # Cross-line goes AFTER the CorridorScan in every plan (mandatory per skill).
    # In START-cal plans: ...CorridorScan -> cross-line -> RTL implicit
    # In END-cal plans:   ...CorridorScan -> cross-line -> fig-8 END -> RTL implicit
    cx_a, cx_b = build_cross_line(polyline, agl)

    items = [cmd530]
    if fig8_at_start: items.extend(fig8)
    items.append(cs)
    items.append(cx_a)
    items.append(cx_b)
    if fig8_at_end:   items.extend(fig8)

    # Renumber doJumpId compactly (skip items that don't carry one), MISSION_ITEM_ID by position.
    next_id = 1
    for k, it in enumerate(items):
        if 'doJumpId' in it:
            it['doJumpId'] = next_id
            next_id += 1
        if 'MISSION_ITEM_ID' in it:
            it['MISSION_ITEM_ID'] = str(k)
    plan['mission']['items'] = items
    return plan

def minified_write(path, plan):
    txt = json.dumps(plan, separators=(',', ':'))
    with open(path, 'wb') as f:
        f.write(txt.encode('utf-8'))

# ----------------------------------- Main ----------
def main():
    pts = load_centerline(KML_PATH)
    i_anchor = nearest_idx(pts, F2_W)
    gap_dist = hav(F2_W, pts[i_anchor])

    # Build a single combined westward path starting at F2_W, bridging the KML
    # data gap to pts[i_anchor], then following dense KML samples west until
    # cumulative distance reaches 2 * TILE_LEN_M.
    f4_total = 2 * TILE_LEN_M
    f3_total = TILE_LEN_M
    combined = [F2_W, pts[i_anchor]]   # F2_W -> first real KML point
    cum = [0.0, gap_dist]
    i = i_anchor
    while i > 0 and cum[-1] < f4_total:
        step = hav(pts[i], pts[i-1])
        if cum[-1] + step >= f4_total:
            frac = (f4_total - cum[-1]) / step
            lat = pts[i][0] + frac * (pts[i-1][0] - pts[i][0])
            lon = pts[i][1] + frac * (pts[i-1][1] - pts[i][1])
            combined.append((lat, lon))
            cum.append(f4_total)
            break
        combined.append(pts[i-1])
        cum.append(cum[-1] + step)
        i -= 1

    # Locate meeting_pt = interpolated point at exactly f3_total along combined path.
    meet_idx = None
    for k in range(len(cum)):
        if cum[k] >= f3_total:
            meet_idx = k
            break
    if meet_idx is None:
        raise RuntimeError('combined path too short for 1800 m split')
    a, b = combined[meet_idx - 1], combined[meet_idx]
    frac = (f3_total - cum[meet_idx - 1]) / (cum[meet_idx] - cum[meet_idx - 1])
    meeting_pt = (a[0] + frac * (b[0] - a[0]),
                  a[1] + frac * (b[1] - a[1]))

    # Split the combined path into Fergus3 (east half) and Fergus4 (west half) at meeting_pt.
    f3_path = combined[:meet_idx] + [meeting_pt]
    f4_path = [meeting_pt] + combined[meet_idx:]
    f4_west_end = f4_path[-1]

    # Reverse Fergus4 path so MEETING end is last (EntryPoint=2 picks last vertex).
    f4_path_polyline = list(reversed(f4_path))

    # Decimate each path (Douglas-Peucker)
    f3_polyline = douglas_peucker(f3_path, DECIMATE_TOL_M)
    f4_polyline = douglas_peucker(f4_path_polyline, DECIMATE_TOL_M)

    print(f'Pair 1 geometry:')
    print(f'  Fergus3 east end  = F2_W           = {F2_W}')
    print(f'  Pair1 meeting pt                   = {meeting_pt}')
    print(f'  Fergus4 west end                   = {f4_west_end}')
    print(f'  Fergus3 polyline: {len(f3_polyline)} pts (decimated from {len(f3_path)})')
    print(f'  Fergus4 polyline: {len(f4_polyline)} pts (decimated from {len(f4_path_polyline)})')

    # Coverage sanity: max perpendicular deviation of decimated polyline from full path
    def max_path_dev(path, poly):
        """Max perpendicular distance from any path point to the nearest polyline segment."""
        maxd = 0.0
        for p in path:
            best = float('inf')
            for k in range(len(poly)-1):
                a, b = poly[k], poly[k+1]
                # signed perp dist
                d = perp_dist_m(p, a, b)
                # also check along-segment cap: if outside segment, use endpoint distance
                lat0 = (a[0]+b[0])/2; m_lat=111132; m_lon=111132*math.cos(math.radians(lat0))
                ax = (a[1]-b[1])*m_lon; ay = (a[0]-b[0])*m_lat
                px = (p[1]-b[1])*m_lon; py = (p[0]-b[0])*m_lat
                L = math.hypot(ax, ay)
                if L > 0:
                    t = (px*ax + py*ay)/(L*L)
                    if 0 <= t <= 1:
                        best = min(best, d)
                        continue
                best = min(best, hav(p, a), hav(p, b))
            maxd = max(maxd, best)
        return maxd

    dev3 = max_path_dev(f3_path, f3_polyline)
    dev4 = max_path_dev(f4_path_polyline, f4_polyline)
    print(f'  Fergus3 max dev from full path: {dev3:.1f} m (corridor swath half = 70.1 m)')
    print(f'  Fergus4 max dev from full path: {dev4:.1f} m')

    # DEM bake: warm the local raster cache for Pair 1 bbox
    lats = [p[0] for p in f3_path + f4_path_polyline]
    lons = [p[1] for p in f3_path + f4_path_polyline]
    pad = 0.005
    print(f'  DEM bbox: lat [{min(lats):.4f},{max(lats):.4f}] lon [{min(lons):.4f},{max(lons):.4f}]')
    ensure_dem_for_bbox(min(lats)-pad, max(lats)+pad, min(lons)-pad, max(lons)+pad,
                        resolution_m=10.0)

    meeting_amsl = bake_amsl(meeting_pt[0], meeting_pt[1], AGL)
    print(f'  Meeting-point AMSL (terrain + AGL) = {meeting_amsl:.2f} m')

    # Load Fergus1 as template
    with open(F1_TEMPLATE, 'r', encoding='utf-8') as f:
        template = json.load(f)

    # plannedHomePosition: place at meeting point (placeholder; user will adjust)
    plan_home = [meeting_pt[0], meeting_pt[1], meeting_amsl - AGL]  # ground AMSL

    # Build Fergus3 (START cal)
    f3_plan = build_plan(template, f3_polyline, plan_home, AGL,
                          fig8_at_start=True, fig8_at_end=False,
                          fig8_centroid_alt_amsl=meeting_amsl,
                          fig8_centroid_latlon=meeting_pt)
    f3_out = os.path.join(OUT_DIR, 'Fergus3.plan')
    minified_write(f3_out, f3_plan)
    print(f'\n  Wrote: {f3_out}')

    # Build Fergus4 (END cal)
    f4_plan = build_plan(template, f4_polyline, plan_home, AGL,
                          fig8_at_start=False, fig8_at_end=True,
                          fig8_centroid_alt_amsl=meeting_amsl,
                          fig8_centroid_latlon=meeting_pt)
    f4_out = os.path.join(OUT_DIR, 'Fergus4.plan')
    minified_write(f4_out, f4_plan)
    print(f'  Wrote: {f4_out}')

    return f3_out, f4_out, f3_polyline, f4_polyline, meeting_pt, f4_west_end

if __name__ == '__main__':
    main()
