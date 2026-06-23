"""Place minimum HOMEs along corridor spines so every tile center is a HOME.

Strategy: use large tiles (along ≈ 900 m, perp = 160 m) with d_home = 0. Each
tile is centered on a HOME. Tile spacing along spine = `along·(1 - overlap)` so
adjacent tiles overlap by `overlap`.

With cruiseSpeed = 8 m/s and the canonical mission:
  S = (4·along + 3·turn_d) / 8 / 60 min
  T (d_home=0) = (240 + (perp+50)) / 8 / 60 min  ≈ 0.94 min
  AMC = 1.05·S + 1.97·T
  AMC(along=900) ≈ 1.05·7.60 + 1.85 ≈ 9.83 min   (in [8, 10] ✓, >9 ✓)

Existing HOMEs from input KML are preserved and reused if a tile center is
within REUSE_RADIUS_M of an existing HOME — otherwise a new HOME is added.
"""
import argparse, json, math, os, pickle, sys, re
import xml.etree.ElementTree as ET

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from tiling_helpers import (
    make_local_projection, sh_clip, k_longest_bearing, decimate_polygon,
    signed_area,
)

# Tile + HOME geometry — tuned for cruiseSpeed=15 (AMC display semantic).
# Empirically the duration model (from estimate.py walking the actual .plan) is:
#   AMC = 1.05·S + 1.97·T  where
#     S = (4·A + 3·turn_d)/8/60 · 1.05   (A = clipped polygon along-extent, m)
#     T = (240 + 2·sqrt(104² + (A/2 - 40 + d)²) + (perp+50)) / 15 / 60
#   with `d` = home offset along the spine tangent, cross-line on the FAR polygon edge.
#
# Solving for d that gives target AMC = 9.5 requires the polygon's actual along
# extent after clipping — so home placement happens *after* clipping each tile.
AGL = 70.0
LINE_SPACING = 70.0                  # = AGL per skill convention
ALONG_M = 1000.0                     # bigger tile to compensate for fewer transects (3 vs 4)
PERP_M = 158.0                       # ~corridor width; clipped ~155m → 3 transects = 2 turnarounds
SPACING_M = ALONG_M * 0.85           # 15% overlap → 850 m apart
TARGET_AMC = 11.5                    # mid of new [8, 12] window — gives more home-sharing budget
MIN_SPINE_LEN_M = 30.0
SMOOTH_WINDOW = 11
SPEED_FLIGHT = 8.0
SPEED_CRUISE = 15.0
TURN_D = 15.24
FIG8_DIST = 240.0
CROSS_MARGIN = 25.0


def required_d_home_for_target_amc(along_clipped, perp_clipped, target_amc=TARGET_AMC):
    """Solve for d_home (along survey-angle direction) that yields the target AMC.

    Survey: n_transects = max(1, ceil(perp / LINE_SPACING)), each of length along.
    Transit: 240 m fig8s + cross-line (perp + 50) + 2× HOME→cross_start.
    AMC = 1.05·S + 1.97·T (per CSV-calibrated model with cruiseSpeed = 15).
    """
    import math
    n_t = max(1, int(math.ceil(perp_clipped / LINE_SPACING)))
    s_naive_min = (n_t*along_clipped + (n_t-1)*TURN_D)/SPEED_FLIGHT/60
    s_amc = 1.05 * s_naive_min
    t_amc_budget = target_amc - s_amc
    if t_amc_budget <= 0:
        return 0.0
    t_naive_min = t_amc_budget / 1.97
    transit_dist = t_naive_min * SPEED_CRUISE * 60
    cross_line = perp_clipped + 2*CROSS_MARGIN
    home_to_cross_two = transit_dist - FIG8_DIST - cross_line
    if home_to_cross_two <= 0:
        return None
    home_to_cross_one = home_to_cross_two / 2.0
    perp_half = perp_clipped/2 + CROSS_MARGIN
    if home_to_cross_one < perp_half:
        return None
    along_term = math.sqrt(home_to_cross_one**2 - perp_half**2)
    d = along_term - (along_clipped/2 - 40)
    return max(0.0, d)


def parse_kml_polygon(path):
    tree = ET.parse(path); root = tree.getroot()
    ns = re.compile(r'\{[^}]+\}')
    for e in root.iter(): e.tag = ns.sub('', e.tag)
    for ring in root.iter('LinearRing'):
        c = ring.find('coordinates')
        if c is None: continue
        pts = []
        for tok in c.text.strip().split():
            lon, lat, *_ = tok.split(',')
            pts.append((float(lat), float(lon)))
        if pts[0] == pts[-1]: pts = pts[:-1]
        return pts


def parse_kml_points(path):
    tree = ET.parse(path); root = tree.getroot()
    ns = re.compile(r'\{[^}]+\}')
    for e in root.iter(): e.tag = ns.sub('', e.tag)
    out = []
    for pm in root.iter('Placemark'):
        name_el = pm.find('name')
        name = name_el.text.strip() if (name_el is not None and name_el.text) else ''
        for pt in pm.iter('Point'):
            c = pt.find('coordinates')
            if c is None: continue
            lon, lat, *_ = c.text.strip().split(',')
            out.append({'name': name, 'lat': float(lat), 'lon': float(lon)})
    return out


def polyline_length(pts):
    return sum(math.hypot(pts[i+1][0]-pts[i][0], pts[i+1][1]-pts[i][1]) for i in range(len(pts)-1))


def smooth(pts, window):
    if len(pts) < window: return list(pts)
    out = list(pts); h = window // 2
    for i in range(h, len(pts) - h):
        x = sum(p[0] for p in pts[i-h:i+h+1]) / window
        y = sum(p[1] for p in pts[i-h:i+h+1]) / window
        out[i] = (x, y)
    return out


def walk_spine(spine, spacing):
    """Return list of (center_xy, tangent_deg) sampled along the smoothed spine."""
    sp = smooth(spine, SMOOTH_WINDOW)
    cum = [0.0]
    for i in range(len(sp) - 1):
        cum.append(cum[-1] + math.hypot(sp[i+1][0]-sp[i][0], sp[i+1][1]-sp[i][1]))
    L = cum[-1]
    if L < MIN_SPINE_LEN_M: return []
    out = []
    if L < ALONG_M:
        # Short spine: one tile at the midpoint
        ts = [L / 2]
    else:
        ts = []
        t = spacing / 2.0
        while t <= L - spacing / 2.0 + 1e-3:
            ts.append(t); t += spacing
        if not ts:
            ts = [L / 2]
    for t in ts:
        idx = next((j for j in range(len(cum)-1) if cum[j+1] >= t), len(cum)-2)
        seg_t = (t - cum[idx]) / max(cum[idx+1] - cum[idx], 1e-9)
        cx = sp[idx][0] + seg_t*(sp[idx+1][0]-sp[idx][0])
        cy = sp[idx][1] + seg_t*(sp[idx+1][1]-sp[idx][1])
        dx = sp[idx+1][0] - sp[idx][0]
        dy = sp[idx+1][1] - sp[idx][1]
        tan_deg = math.degrees(math.atan2(dx, dy)) % 360
        out.append({'center_xy': (cx, cy), 'tangent_deg': tan_deg})
    return out


def main():
    global AGL, LINE_SPACING, ALONG_M, PERP_M, SPACING_M, TARGET_AMC, MIN_SPINE_LEN_M
    ap = argparse.ArgumentParser()
    ap.add_argument('--kml', required=True)
    ap.add_argument('--homes', required=True)
    ap.add_argument('--out-dir', required=True)
    ap.add_argument('--agl', type=float, default=AGL)
    ap.add_argument('--line-spacing', type=float, default=None,
                    help='Defaults to --agl (skill convention)')
    ap.add_argument('--along', type=float, default=ALONG_M)
    ap.add_argument('--perp', type=float, default=PERP_M)
    ap.add_argument('--target-amc', type=float, default=TARGET_AMC)
    ap.add_argument('--spacing', type=float, default=None,
                    help='Tile spacing; defaults to 0.85 * along (15%% overlap)')
    ap.add_argument('--min-spine-len', type=float, default=MIN_SPINE_LEN_M)
    args = ap.parse_args()
    AGL = args.agl
    LINE_SPACING = args.line_spacing if args.line_spacing is not None else args.agl
    ALONG_M = args.along
    PERP_M = args.perp
    SPACING_M = args.spacing if args.spacing is not None else args.along * 0.85
    TARGET_AMC = args.target_amc
    MIN_SPINE_LEN_M = args.min_spine_len

    corridor_ll = parse_kml_polygon(args.kml)
    homes_existing = parse_kml_points(args.homes)
    print(f"corridor: {len(corridor_ll)} verts; existing homes: {len(homes_existing)}", file=sys.stderr)
    centroid_lat = sum(p[0] for p in corridor_ll) / len(corridor_ll)
    centroid_lon = sum(p[1] for p in corridor_ll) / len(corridor_ll)
    to_xy, to_ll = make_local_projection(centroid_lat, centroid_lon)
    corridor_xy = [to_xy(*p) for p in corridor_ll]

    with open(os.path.join(args.out_dir, 'spines.pkl'), 'rb') as f:
        skel = pickle.load(f)

    # Lay tile centers spine-by-spine
    all_centers = []
    for si, spine in enumerate(skel['spines']):
        for tc in walk_spine(spine, SPACING_M):
            tc['spine_idx'] = si
            all_centers.append(tc)
    print(f"tile centers (and homes): {len(all_centers)}", file=sys.stderr)

    # Sort tile centers WEST TO EAST so output .plan files are ordered by longitude.
    # (Earlier was spine-by-spine; user prefers W→E numbering.)
    sorted_centers = sorted(all_centers, key=lambda t: (t['center_xy'][0], t['center_xy'][1]))
    all_centers = sorted_centers

    # Two-pass bearing: (1) crude clip using radius-based bearing, (2) compute spec-strict
    # bearing from k=10 longest corridor edges whose midpoints lie inside the clipped polygon,
    # (3) re-clip with the spec-strict bearing. This makes the placement match what
    # verify_corridor_set.py checks for c8.
    from tiling_helpers import point_in_polygon
    def strict_bearing(footprint_xy):
        edges = []
        n = len(corridor_xy)
        for i in range(n):
            a = corridor_xy[i]; b = corridor_xy[(i+1)%n]
            mid = ((a[0]+b[0])/2, (a[1]+b[1])/2)
            if not point_in_polygon(mid, footprint_xy): continue
            dx, dy = b[0]-a[0], b[1]-a[1]
            L = math.hypot(dx, dy)
            if L < 0.5: continue
            brg = math.degrees(math.atan2(dx, dy)) % 180
            edges.append((L, brg))
        if len(edges) < 3:
            # Fallback to 500 m centroid radius (matches verify_corridor_set.py)
            fc_x = sum(p[0] for p in footprint_xy)/len(footprint_xy)
            fc_y = sum(p[1] for p in footprint_xy)/len(footprint_xy)
            edges = []
            for i in range(n):
                a = corridor_xy[i]; b = corridor_xy[(i+1)%n]
                mid = ((a[0]+b[0])/2, (a[1]+b[1])/2)
                if math.hypot(mid[0]-fc_x, mid[1]-fc_y) > 500.0: continue
                dx, dy = b[0]-a[0], b[1]-a[1]
                L = math.hypot(dx, dy)
                if L < 0.5: continue
                brg = math.degrees(math.atan2(dx, dy)) % 180
                edges.append((L, brg))
        edges.sort(reverse=True)
        top10 = edges[:10]
        if not top10: return None
        total = sum(L for L,_ in top10)
        return sum(L*b for L,b in top10) / total

    for tc in all_centers:
        # Pass 1: crude bearing from 1500 m radius
        b1 = k_longest_bearing(corridor_xy, near_xy=tc['center_xy'], radius=1500.0, k=10)
        if b1 is None:
            b1 = tc['tangent_deg'] % 180
        # Crude clip
        cx, cy = tc['center_xy']
        th = math.radians(b1)
        fx, fy = math.sin(th), math.cos(th); px, py = -fy, fx
        rect = [
            (cx + fx*ALONG_M/2 + px*PERP_M/2, cy + fy*ALONG_M/2 + py*PERP_M/2),
            (cx + fx*ALONG_M/2 - px*PERP_M/2, cy + fy*ALONG_M/2 - py*PERP_M/2),
            (cx - fx*ALONG_M/2 - px*PERP_M/2, cy - fy*ALONG_M/2 - py*PERP_M/2),
            (cx - fx*ALONG_M/2 + px*PERP_M/2, cy - fy*ALONG_M/2 + py*PERP_M/2),
        ]
        crude_clip = sh_clip(corridor_xy, rect)
        # Pass 2: spec-strict bearing from segments INSIDE the crude clipped polygon
        b2 = strict_bearing(crude_clip) if len(crude_clip) >= 3 else None
        tc['bearing_deg'] = b2 if b2 is not None else b1

    # Pre-clip each tile to measure actual along/perp extent → required d_home
    for tc in all_centers:
        cx, cy = tc['center_xy']
        th = math.radians(tc['bearing_deg'])
        fx, fy = math.sin(th), math.cos(th); px, py = -fy, fx
        rect = [
            (cx + fx*ALONG_M/2 + px*PERP_M/2, cy + fy*ALONG_M/2 + py*PERP_M/2),
            (cx + fx*ALONG_M/2 - px*PERP_M/2, cy + fy*ALONG_M/2 - py*PERP_M/2),
            (cx - fx*ALONG_M/2 - px*PERP_M/2, cy - fy*ALONG_M/2 - py*PERP_M/2),
            (cx - fx*ALONG_M/2 + px*PERP_M/2, cy - fy*ALONG_M/2 + py*PERP_M/2),
        ]
        clipped = sh_clip(corridor_xy, rect)
        clipped = decimate_polygon(clipped, 5.0)
        tc['polygon_xy'] = clipped if len(clipped) >= 3 else rect
        # Rotate to flight frame to measure along/perp
        _th = -math.radians(tc['bearing_deg'])
        _c, _s = math.cos(_th), math.sin(_th)
        rotp = [(_c*x + _s*y, -_s*x + _c*y) for x, y in tc['polygon_xy']]
        tc['perp_extent'] = max(p[0] for p in rotp) - min(p[0] for p in rotp)
        tc['along_extent'] = max(p[1] for p in rotp) - min(p[1] for p in rotp)
        d_req = required_d_home_for_target_amc(tc['along_extent'], tc['perp_extent'])
        tc['d_required'] = d_req
        # ±25% tolerance bracket around the required value
        tc['d_min'] = (d_req * 0.75) if d_req is not None else None
        tc['d_max'] = (d_req * 1.25) if d_req is not None else None

    n_unfit = sum(1 for tc in all_centers if tc['d_required'] is None)
    print(f"tiles whose AMC cannot be brought to {TARGET_AMC} with any d_home: {n_unfit}",
          file=sys.stderr)

    # Greedy home assignment using adaptive d_home per tile
    existing_pool = [(h, to_xy(h['lat'], h['lon']), True) for h in homes_existing]
    new_pool = []
    new_homes_meta = []
    home_lookup = []

    for tc in all_centers:
        cx, cy = tc['center_xy']
        d_req = tc['d_required']
        if d_req is None:
            # Polygon too small to fit [8,10] — best effort: place home far along tangent
            d_req = 1000.0
            tc['d_min'] = 800.0; tc['d_max'] = 1500.0
        best = None; best_score = float('inf'); best_pool = None; best_d = None
        for pool in (existing_pool, new_pool):
            for h, xy, _ in pool:
                d = math.hypot(cx - xy[0], cy - xy[1])
                if tc['d_min'] <= d <= tc['d_max']:
                    score = abs(d - d_req)
                    if score < best_score:
                        best_score = score; best = h; best_pool = pool; best_d = d
        if best is not None:
            home_lookup.append({'lat': best['lat'], 'lon': best['lon'], 'name': best.get('name', ''),
                                'reused': True, 'd_m': best_d,
                                'is_existing_home': best_pool is existing_pool})
        else:
            # New home: offset d_req along the SURVEY ANGLE direction (= flight-line direction).
            # This keeps the home on the flight-frame +along axis so the analytic d_home math
            # actually predicts AMC. (Using spine tangent here adds an unintended perpendicular
            # offset whenever spine tangent diverges from k_longest_bearing.)
            tan = math.radians(tc['bearing_deg'])
            ox = math.sin(tan) * d_req
            oy = math.cos(tan) * d_req
            hx, hy = cx + ox, cy + oy
            lat, lon = to_ll(hx, hy)
            nm = f"H{len(new_homes_meta)+1:03d}"
            entry = {'lat': lat, 'lon': lon, 'name': nm}
            new_homes_meta.append(entry)
            new_pool.append((entry, (hx, hy), False))
            home_lookup.append({'lat': lat, 'lon': lon, 'name': nm,
                                'reused': False, 'd_m': d_req,
                                'is_existing_home': False})

    print(f"new homes added: {len(new_homes_meta)}", file=sys.stderr)
    reused_existing = sum(1 for h in home_lookup if h.get('is_existing_home'))
    reused_new = sum(1 for h in home_lookup if h['reused'] and not h.get('is_existing_home'))
    fresh = sum(1 for h in home_lookup if not h['reused'])
    print(f"  reused existing: {reused_existing}   reused new: {reused_new}   fresh: {fresh}",
          file=sys.stderr)

    # Build tile polygons (rectangle aligned to bearing, clipped to corridor)
    tiles_out = []
    for i, (tc, h) in enumerate(zip(all_centers, home_lookup)):
        cx, cy = tc['center_xy']
        th = math.radians(tc['bearing_deg'])
        fx, fy = math.sin(th), math.cos(th); px, py = -fy, fx
        rect = [
            (cx + fx*ALONG_M/2 + px*PERP_M/2, cy + fy*ALONG_M/2 + py*PERP_M/2),
            (cx + fx*ALONG_M/2 - px*PERP_M/2, cy + fy*ALONG_M/2 - py*PERP_M/2),
            (cx - fx*ALONG_M/2 - px*PERP_M/2, cy - fy*ALONG_M/2 - py*PERP_M/2),
            (cx - fx*ALONG_M/2 + px*PERP_M/2, cy - fy*ALONG_M/2 + py*PERP_M/2),
        ]
        clipped = sh_clip(corridor_xy, rect)
        clipped = decimate_polygon(clipped, 5.0)
        if len(clipped) < 3: continue
        poly_ll = [to_ll(x, y) for x, y in clipped]
        tiles_out.append({
            'id': i, 'spine_idx': tc['spine_idx'],
            'center_lat': to_ll(cx, cy)[0], 'center_lon': to_ll(cx, cy)[1],
            'bearing_deg': tc['bearing_deg'],
            'home_lat': h['lat'], 'home_lon': h['lon'],
            'home_name': h['name'], 'home_reused': h['reused'],
            'home_dist_m': h['d_m'],
            'polygon_latlon': poly_ll,
            'raw_along_m': ALONG_M, 'raw_perp_m': PERP_M,
        })

    with open(os.path.join(args.out_dir, 'tiles_sized_v2.json'), 'w') as f:
        json.dump(tiles_out, f, indent=2)
    with open(os.path.join(args.out_dir, 'homes_new.json'), 'w') as f:
        json.dump(new_homes_meta, f, indent=2)

    # Write merged HomePoints KML
    merged = list(homes_existing) + new_homes_meta
    out_kml = os.path.join(args.out_dir, 'HomePoints_extended.kml')
    with open(out_kml, 'w') as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n<kml xmlns="http://www.opengis.net/kml/2.2">\n<Document>\n')
        for h in merged:
            name = h.get('name', 'Launch')
            f.write(f'  <Placemark><name>{name}</name><Point><coordinates>{h["lon"]},{h["lat"]},0</coordinates></Point></Placemark>\n')
        f.write('</Document></kml>\n')

    print(f"tiles: {len(tiles_out)}  homes: {len(merged)} ({len(homes_existing)} existing + {len(new_homes_meta)} new)",
          file=sys.stderr)
    print(f"wrote tiles_sized_v2.json, homes_new.json, HomePoints_extended.kml", file=sys.stderr)


if __name__ == '__main__':
    main()
