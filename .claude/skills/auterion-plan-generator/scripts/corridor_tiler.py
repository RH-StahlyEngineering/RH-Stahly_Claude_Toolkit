"""
Corridor tiler — slice a single KML polygon into many .plan tiles.

Pipeline:
  Phase 1  skeletonize:   rasterize polygon @ RASTER_M, skimage.skeletonize, vectorize into spines
  Phase 2  spine walk:    lay overlapping raw rectangular tile centers along each spine
  Phase 3  clip & resize: SH-clip each rectangle to the corridor, resize length until duration in [LO,HI]
  Phase 4  generate:      build_mission() per tile with HOME = nearest from HomePoints.kml
  Phase 5  verify:        write verify_corridor_set.py, emit verification_report.json
  Phase 6  document:      append lessons to SKILL.md

Persistent state file lives in <out_dir>/status.json so progress survives interruption.

This file is intentionally a single batch script (not a long-lived service).
"""
import argparse, json, math, os, sys, time, re, pickle
import xml.etree.ElementTree as ET
import numpy as np

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from tiling_helpers import (
    sh_clip, k_longest_bearing, decimate_polygon, signed_area,
    make_local_projection, point_in_polygon, polygon_intersection_area,
)

# ---- Parameters ----
RASTER_M = 10.0      # raster cell size for skeletonization
TILE_WID = 160.0     # perpendicular tile width: 4 transects × 40 m
TILE_LEN_INIT = 950  # initial along-flight tile length (m); driver resizes
LO_MIN = 8.0         # duration lower bound (min)
HI_MIN = 10.0        # duration upper bound (min)
TARGET_MIN = 9.2     # aim slightly above 9 so >90% are >9
AGL_TARGET = 40.0
SPEED = 8.0
CROSS_MARGIN = 25.0
FIG8_DURATION = 15.0
K_BEARING = 10
SPINE_RADIUS = 1500.0     # window for k-longest segment bearing lookup
ALONG_OVERLAP = 0.15      # 15% along-spine overlap between consecutive tile CENTERS
# (Note: spec is for area overlap; this is the placement input.)


# ============================================================
# KML parsing
# ============================================================
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
    raise ValueError(f"no Polygon in {path}")


def parse_kml_points(path):
    tree = ET.parse(path); root = tree.getroot()
    ns = re.compile(r'\{[^}]+\}')
    for e in root.iter(): e.tag = ns.sub('', e.tag)
    out = []
    for pm in root.iter('Placemark'):
        name = pm.find('name').text.strip() if pm.find('name') is not None else ''
        for pt in pm.iter('Point'):
            c = pt.find('coordinates')
            if c is None: continue
            lon, lat, *_ = c.text.strip().split(',')
            out.append({'name': name, 'lat': float(lat), 'lon': float(lon)})
    return out


# ============================================================
# Phase 1 — Skeletonize
# ============================================================
def skeletonize_corridor(corridor_xy):
    """Rasterize the polygon, run skeletonize, vectorize into spine polylines.

    Returns dict with: cell_m, x_origin, y_origin, spines (list of list of (x,y)).
    Each spine is a polyline of points in local meters.
    """
    from skimage.morphology import skeletonize
    from skimage.draw import polygon as draw_polygon

    xs = np.array([p[0] for p in corridor_xy])
    ys = np.array([p[1] for p in corridor_xy])
    pad = 50.0
    x0, x1 = xs.min() - pad, xs.max() + pad
    y0, y1 = ys.min() - pad, ys.max() + pad
    W = int((x1 - x0) / RASTER_M) + 1
    H = int((y1 - y0) / RASTER_M) + 1
    print(f"[P1] raster {W}x{H} @ {RASTER_M} m", file=sys.stderr)

    mask = np.zeros((H, W), dtype=bool)
    cols = ((xs - x0) / RASTER_M).astype(int)
    rows = ((ys - y0) / RASTER_M).astype(int)
    rr, cc = draw_polygon(rows, cols, shape=mask.shape)
    mask[rr, cc] = True
    print(f"[P1] polygon cells: {mask.sum()}", file=sys.stderr)

    skel = skeletonize(mask)
    print(f"[P1] skeleton cells: {skel.sum()}", file=sys.stderr)

    # Vectorize skeleton: find endpoints (1 neighbor) and branch points (>2 neighbors)
    # Walk edges between special points.
    sk = skel.astype(np.uint8)
    # Pad for safe neighborhood lookup
    skp = np.pad(sk, 1, mode='constant')
    H2, W2 = skp.shape
    # Count 8-connected neighbors
    nbcount = np.zeros_like(skp, dtype=np.int8)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dx == 0 and dy == 0: continue
            nbcount[1:-1, 1:-1] += skp[1+dy:H2-1+dy, 1+dx:W2-1+dx]
    nbcount = nbcount[1:-1, 1:-1] * skel
    endpoints = set(zip(*np.where((nbcount == 1) & skel)))
    branchpts = set(zip(*np.where((nbcount >= 3) & skel)))
    nodes = endpoints | branchpts

    # Walk each edge
    visited_edges = set()
    spines_rc = []
    NB8 = [(-1,-1),(-1,0),(-1,1),(0,-1),(0,1),(1,-1),(1,0),(1,1)]
    def neighbors(r, c):
        for dr, dc in NB8:
            r2, c2 = r+dr, c+dc
            if 0 <= r2 < skel.shape[0] and 0 <= c2 < skel.shape[1] and skel[r2, c2]:
                yield (r2, c2)

    for node in nodes:
        for nb in neighbors(*node):
            edge = tuple(sorted([node, nb]))
            if edge in visited_edges: continue
            # Walk from node through nb until we hit another node or cycle back
            path = [node, nb]
            visited_edges.add(edge)
            cur = nb
            prev = node
            while cur not in nodes:
                nxt = None
                for n2 in neighbors(*cur):
                    if n2 == prev: continue
                    e2 = tuple(sorted([cur, n2]))
                    if e2 in visited_edges: continue
                    nxt = n2
                    break
                if nxt is None: break
                visited_edges.add(tuple(sorted([cur, nxt])))
                path.append(nxt)
                prev, cur = cur, nxt
            spines_rc.append(path)

    # Convert (row, col) → (x, y) meters
    spines_xy = []
    for sp in spines_rc:
        xy_path = []
        for r, c in sp:
            x = x0 + (c + 0.5) * RASTER_M
            y = y0 + (r + 0.5) * RASTER_M
            xy_path.append((x, y))
        if len(xy_path) >= 2:
            spines_xy.append(xy_path)

    # Sort longest spine first
    spines_xy.sort(key=lambda s: -_polyline_length(s))
    print(f"[P1] spines: {len(spines_xy)} (longest {_polyline_length(spines_xy[0]):.0f} m)",
          file=sys.stderr)
    return {'cell_m': RASTER_M, 'x_origin': x0, 'y_origin': y0,
            'W': W, 'H': H, 'spines': spines_xy}


def _polyline_length(pts):
    total = 0.0
    for i in range(len(pts) - 1):
        total += math.hypot(pts[i+1][0]-pts[i][0], pts[i+1][1]-pts[i][1])
    return total


# ============================================================
# Phase 2 — Lay tiles along spines
# ============================================================
def smooth_polyline(pts, window=11):
    """Boxcar-smooth a polyline to reduce raster jitter for tangent calc."""
    if len(pts) < window: return list(pts)
    out = list(pts)
    half = window // 2
    for i in range(half, len(pts) - half):
        x = sum(p[0] for p in pts[i-half:i+half+1]) / window
        y = sum(p[1] for p in pts[i-half:i+half+1]) / window
        out[i] = (x, y)
    return out


def lay_tile_centers(spines, corridor_xy, tile_len_m=TILE_LEN_INIT,
                     spacing_m=None, min_spine_length=200.0):
    """For each spine, sample tile centers at along-spine spacing.

    Returns list of dicts: {'spine_idx', 'idx_in_spine', 'center_xy', 'tangent_brg_deg'}.
    """
    if spacing_m is None:
        spacing_m = tile_len_m * (1 - ALONG_OVERLAP)  # 15% overlap → spacing = 85% of length

    tiles = []
    for si, raw in enumerate(spines):
        if _polyline_length(raw) < min_spine_length:
            continue
        sp = smooth_polyline(raw, window=11)
        # Walk cumulative arc length on smoothed polyline
        cum = [0.0]
        for i in range(len(sp) - 1):
            cum.append(cum[-1] + math.hypot(sp[i+1][0]-sp[i][0], sp[i+1][1]-sp[i][1]))
        L = cum[-1]
        if L < spacing_m / 2: continue
        target = spacing_m / 2  # start half-spacing in to leave end margin
        while target <= L - 1e-3:
            # find segment containing 'target'
            idx = next(j for j in range(len(cum)-1) if cum[j+1] >= target)
            seg_t = (target - cum[idx]) / max(cum[idx+1] - cum[idx], 1e-9)
            cx = sp[idx][0] + seg_t * (sp[idx+1][0] - sp[idx][0])
            cy = sp[idx][1] + seg_t * (sp[idx+1][1] - sp[idx][1])
            # tangent via local segment
            dx = sp[idx+1][0] - sp[idx][0]
            dy = sp[idx+1][1] - sp[idx][1]
            # bearing (CW from north)
            tangent = math.degrees(math.atan2(dx, dy)) % 360
            tiles.append({'spine_idx': si, 'center_xy': (cx, cy),
                          'tangent_deg': tangent})
            target += spacing_m
    print(f"[P2] tile centers laid: {len(tiles)}", file=sys.stderr)
    return tiles


# ============================================================
# Phase 3 — Clip & resize tiles
# ============================================================
def derive_tile_polygon(center_xy, bearing_deg, length_m, width_m, corridor_xy,
                        decimate_m=5.0):
    """Build a rectangle around center at given bearing, clip to corridor."""
    th = math.radians(bearing_deg)
    fx, fy = math.sin(th), math.cos(th)
    px, py = -fy, fx
    cx, cy = center_xy
    rect = [
        (cx + fx*length_m/2 + px*width_m/2, cy + fy*length_m/2 + py*width_m/2),
        (cx + fx*length_m/2 - px*width_m/2, cy + fy*length_m/2 - py*width_m/2),
        (cx - fx*length_m/2 - px*width_m/2, cy - fy*length_m/2 - py*width_m/2),
        (cx - fx*length_m/2 + px*width_m/2, cy - fy*length_m/2 + py*width_m/2),
    ]
    clipped = sh_clip(corridor_xy, rect)
    if len(clipped) < 3:
        return None
    return decimate_polygon(clipped, decimate_m)


def local_k_longest_bearing(corridor_xy, center_xy, radius=SPINE_RADIUS, k=K_BEARING):
    """Length-weighted bearing of the k longest corridor edges with midpoints near center."""
    return k_longest_bearing(corridor_xy, near_xy=center_xy, radius=radius, k=k)


CRUISE_FOR_ESTIMATE = 15.0  # estimate_flight_time.py uses cruiseSpeed for transit, not FlightSpeed

def analytic_duration_min(poly_xy, bearing_deg, home_xy, speed=SPEED,
                           agl=AGL_TARGET, turn_d=15.24, fig8_dur=FIG8_DURATION,
                           cross_margin=CROSS_MARGIN):
    """Predict AMC duration matching estimate_flight_time.py's bookkeeping:
       - survey time uses FlightSpeed = SPEED (cmd 178)
       - transit time uses cruiseSpeed (mission header, default 15) — NOT SPEED.
    """
    if len(poly_xy) < 3: return None
    th = -math.radians(bearing_deg)
    c, s = math.cos(th), math.sin(th)
    rot = [(c*x + s*y, -s*x + c*y) for x, y in poly_xy]
    perp_min = min(p[0] for p in rot); perp_max = max(p[0] for p in rot)
    along_min = min(p[1] for p in rot); along_max = max(p[1] for p in rot)
    perp_extent = perp_max - perp_min
    along_extent = along_max - along_min

    n_trans = max(1, min(4, int(math.ceil(perp_extent / agl))))
    survey_dist = n_trans * along_extent + (n_trans - 1) * turn_d
    survey_min = (survey_dist / speed) / 60

    poly_cx = sum(p[0] for p in poly_xy) / len(poly_xy)
    poly_cy = sum(p[1] for p in poly_xy) / len(poly_xy)
    home_to_poly = math.hypot(poly_cx - home_xy[0], poly_cy - home_xy[1])
    fig8_dist = speed * fig8_dur  # 120 m at SPEED=8
    cross_line_dist = perp_extent + 2 * cross_margin
    transit_dist = 2 * fig8_dist + cross_line_dist + 2 * home_to_poly
    transit_min = (transit_dist / CRUISE_FOR_ESTIMATE) / 60

    amc = 1.05 * survey_min + 1.97 * transit_min
    return {'amc': amc, 'survey': survey_min, 'transit': transit_min,
            'n_transects': n_trans, 'along': along_extent, 'perp': perp_extent}


def size_tile(center_xy, bearing_deg, corridor_xy, home_xy,
              lo=LO_MIN, hi=HI_MIN, target=TARGET_MIN, max_attempts=8):
    """Iterate raw tile length until analytic duration ∈ [lo, hi] with bias toward target.

    Returns (polygon_xy, raw_len_m, est) or (None, None, None) if can't fit.
    """
    raw_len = TILE_LEN_INIT
    last_polys = []
    for attempt in range(max_attempts):
        poly = derive_tile_polygon(center_xy, bearing_deg, raw_len, TILE_WID,
                                    corridor_xy)
        if poly is None:
            raw_len *= 1.4
            continue
        est = analytic_duration_min(poly, bearing_deg, home_xy)
        if est is None:
            raw_len *= 1.4; continue
        last_polys.append((poly, raw_len, est))
        if lo <= est['amc'] <= hi:
            return poly, raw_len, est
        # Adjust length
        # Linear-ish: amc roughly ~ k*along + constant; bigger raw → bigger along
        if est['amc'] < lo:
            raw_len *= 1.0 + (target - est['amc']) / max(est['amc'], 1.0)
        else:  # > hi
            raw_len *= 1.0 - (est['amc'] - target) / max(est['amc'], 1.0)
        # Bound raw_len sanely
        raw_len = max(200, min(3000, raw_len))
    # Couldn't fit — return closest to target
    best = min(last_polys, key=lambda p: abs(p[2]['amc'] - target))
    return best[0], best[1], best[2]


def nearest_home(home_xy_list, point_xy):
    """Return (home_dict, home_xy, dist_m) for closest HOME."""
    best = None; best_d = float('inf')
    for h, xy in home_xy_list:
        d = math.hypot(point_xy[0] - xy[0], point_xy[1] - xy[1])
        if d < best_d:
            best_d = d; best = (h, xy)
    return best[0], best[1], best_d


# ============================================================
# Persistence
# ============================================================
def save_status(path, data):
    with open(path, 'w') as f:
        json.dump(data, f, indent=2, default=str)


def load_status(path):
    if not os.path.exists(path): return {}
    try: return json.load(open(path))
    except: return {}


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--kml', required=True)
    ap.add_argument('--homes', required=True)
    ap.add_argument('--out-dir', required=True)
    ap.add_argument('--phase', choices=['skeletonize','tiles','clip','generate','verify','all'],
                    default='all')
    args = ap.parse_args()
    os.makedirs(args.out_dir, exist_ok=True)
    status_path = os.path.join(args.out_dir, 'status.json')
    status = load_status(status_path)

    corridor_ll = parse_kml_polygon(args.kml)
    homes = parse_kml_points(args.homes)
    print(f"corridor: {len(corridor_ll)} verts; homes: {len(homes)}", file=sys.stderr)
    centroid_lat = sum(p[0] for p in corridor_ll) / len(corridor_ll)
    centroid_lon = sum(p[1] for p in corridor_ll) / len(corridor_ll)
    to_xy, to_ll = make_local_projection(centroid_lat, centroid_lon)
    corridor_xy = [to_xy(*p) for p in corridor_ll]
    homes_xy = [(h, to_xy(h['lat'], h['lon'])) for h in homes]
    status['centroid'] = [centroid_lat, centroid_lon]
    status['n_homes'] = len(homes)

    if args.phase in ('skeletonize', 'all'):
        skel = skeletonize_corridor(corridor_xy)
        # save skeleton (pickle for the numpy/list structure)
        with open(os.path.join(args.out_dir, 'spines.pkl'), 'wb') as f:
            pickle.dump(skel, f)
        status['phase1_skeletonize'] = {'spines': len(skel['spines']),
                                         'cells_skel': sum(len(s) for s in skel['spines'])}
        save_status(status_path, status)

    if args.phase in ('tiles', 'all'):
        with open(os.path.join(args.out_dir, 'spines.pkl'), 'rb') as f:
            skel = pickle.load(f)
        tiles = lay_tile_centers(skel['spines'], corridor_xy)
        # Compute local bearing per tile
        for t in tiles:
            t['local_bearing'] = local_k_longest_bearing(corridor_xy, t['center_xy'])
        # Save tile centers
        with open(os.path.join(args.out_dir, 'tile_centers.json'), 'w') as f:
            json.dump([{
                'spine_idx': t['spine_idx'],
                'center_lat': to_ll(*t['center_xy'])[0],
                'center_lon': to_ll(*t['center_xy'])[1],
                'tangent_deg': t['tangent_deg'],
                'local_bearing_deg': t['local_bearing'],
            } for t in tiles], f, indent=2)
        status['phase2_tiles'] = {'count': len(tiles)}
        save_status(status_path, status)
        print(f"[P2] wrote tile_centers.json ({len(tiles)} tiles)", file=sys.stderr)

    if args.phase in ('clip', 'all'):
        with open(os.path.join(args.out_dir, 'spines.pkl'), 'rb') as f:
            skel = pickle.load(f)
        tiles_raw = json.load(open(os.path.join(args.out_dir, 'tile_centers.json')))
        sized = []
        in_range = 0; over9 = 0
        for i, t in enumerate(tiles_raw):
            cx_ll = (t['center_lat'], t['center_lon'])
            center_xy = to_xy(*cx_ll)
            bearing = t['local_bearing_deg']
            home_d, home_xy, home_dist = nearest_home(homes_xy, center_xy)
            poly_xy, raw_len, est = size_tile(center_xy, bearing, corridor_xy, home_xy)
            if poly_xy is None:
                print(f"  tile {i}: FAILED to size", file=sys.stderr); continue
            poly_ll = [to_ll(x, y) for x, y in poly_xy]
            sized.append({
                'id': i, 'spine_idx': t['spine_idx'],
                'center_lat': cx_ll[0], 'center_lon': cx_ll[1],
                'bearing_deg': bearing,
                'home_lat': home_d['lat'], 'home_lon': home_d['lon'],
                'home_dist_m': home_dist,
                'polygon_latlon': poly_ll,
                'raw_len_m': raw_len,
                'predicted_amc_min': est['amc'],
                'predicted_survey_min': est['survey'],
                'predicted_transit_min': est['transit'],
                'n_transects': est['n_transects'],
                'along_m': est['along'], 'perp_m': est['perp'],
            })
            if LO_MIN <= est['amc'] <= HI_MIN: in_range += 1
            if est['amc'] > 9.0: over9 += 1
        with open(os.path.join(args.out_dir, 'tiles_sized.json'), 'w') as f:
            json.dump(sized, f, indent=2)
        status['phase3_clip'] = {
            'count': len(sized),
            'in_range_8_10': in_range,
            'pct_over_9': 100*over9/len(sized) if sized else 0,
        }
        save_status(status_path, status)
        print(f"[P3] sized {len(sized)} tiles; in_range {in_range}; >9min {over9} ({100*over9/len(sized):.1f}%)",
              file=sys.stderr)
