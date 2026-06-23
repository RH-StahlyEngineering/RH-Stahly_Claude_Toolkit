"""For each large uncovered patch in the corridor, place a tile + HOME and generate a plan."""
import argparse, json, math, os, sys, re
import xml.etree.ElementTree as ET
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tiling_helpers import (make_local_projection, sh_clip, decimate_polygon,
                            signed_area, k_longest_bearing, point_in_polygon)
from generate_lidar_mission import build_mission
from estimate_flight_time import estimate
from skimage.draw import polygon as draw_polygon
from scipy.ndimage import label

ALONG_M = 700.0
PERP_M = 158.0
CELL = 10.0
MIN_GAP_M2 = 8000.0   # only fill gaps ≥ 2 acres
TARGET_AMC = 9.5
TURN_D = 15.24
FIG8_DIST = 240.0
CROSS_MARGIN = 25.0
SPEED_FLIGHT = 8.0
SPEED_CRUISE = 15.0


def required_d_home(along_clipped, perp_clipped, target_amc=TARGET_AMC):
    s_naive_min = (4*along_clipped + 3*TURN_D)/SPEED_FLIGHT/60
    s_amc = 1.05 * s_naive_min
    budget = target_amc - s_amc
    if budget <= 0: return 0.0
    t_naive_min = budget / 1.97
    transit_dist = t_naive_min * SPEED_CRUISE * 60
    cross_line = perp_clipped + 2*CROSS_MARGIN
    two_way = transit_dist - FIG8_DIST - cross_line
    if two_way <= 0: return None
    one_way = two_way / 2.0
    perp_half = perp_clipped/2 + CROSS_MARGIN
    if one_way < perp_half: return None
    along_term = math.sqrt(one_way**2 - perp_half**2)
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


def main():
    global ALONG_M, PERP_M, MIN_GAP_M2, TARGET_AMC
    ap = argparse.ArgumentParser()
    ap.add_argument('--kml', required=True)
    ap.add_argument('--homes', required=True)
    ap.add_argument('--dir', required=True)
    ap.add_argument('--agl', type=float, default=70.0)
    ap.add_argument('--along', type=float, default=ALONG_M)
    ap.add_argument('--perp', type=float, default=PERP_M)
    ap.add_argument('--min-gap-m2', type=float, default=MIN_GAP_M2)
    ap.add_argument('--target-amc', type=float, default=TARGET_AMC)
    ap.add_argument('--plan-prefix', default='fergus',
                    help='Plan filename prefix; gap-fills get <prefix>_gap_NNN.plan')
    args = ap.parse_args()
    ALONG_M = args.along
    PERP_M = args.perp
    MIN_GAP_M2 = args.min_gap_m2
    TARGET_AMC = args.target_amc

    corridor_ll = parse_kml_polygon(args.kml)
    cl_lat = sum(p[0] for p in corridor_ll)/len(corridor_ll)
    cl_lon = sum(p[1] for p in corridor_ll)/len(corridor_ll)
    to_xy, to_ll = make_local_projection(cl_lat, cl_lon)
    corridor_xy = [to_xy(*p) for p in corridor_ll]
    sized = json.load(open(os.path.join(args.dir, 'tiles_sized_v2.json')))

    # Build coverage mask
    xs = [p[0] for p in corridor_xy]; ys = [p[1] for p in corridor_xy]
    x0, x1 = min(xs)-50, max(xs)+50
    y0, y1 = min(ys)-50, max(ys)+50
    W = int((x1-x0)/CELL)+1; H = int((y1-y0)/CELL)+1
    target_mask = np.zeros((H, W), dtype=bool)
    cols = [(p[0]-x0)/CELL for p in corridor_xy]
    rows = [(p[1]-y0)/CELL for p in corridor_xy]
    rr, cc = draw_polygon(np.array(rows), np.array(cols), shape=target_mask.shape)
    target_mask[rr, cc] = True
    covered = np.zeros_like(target_mask)
    for t in sized:
        poly_xy = [to_xy(*v) for v in t['polygon_latlon']]
        c2 = [(p[0]-x0)/CELL for p in poly_xy]
        r2 = [(p[1]-y0)/CELL for p in poly_xy]
        rr, cc = draw_polygon(np.array(r2), np.array(c2), shape=target_mask.shape)
        rr = np.clip(rr, 0, H-1); cc = np.clip(cc, 0, W-1)
        covered[rr, cc] = True
    uncovered = target_mask & ~covered

    # Find regions
    labeled, n_regions = label(uncovered)
    print(f"uncovered regions: {n_regions}")
    gaps = []
    for i in range(1, n_regions+1):
        cells = (labeled == i)
        sz = int(cells.sum())
        area_m2 = sz * CELL * CELL
        if area_m2 < MIN_GAP_M2: continue
        rows, cols = np.where(cells)
        cx_m = x0 + cols.mean() * CELL
        cy_m = y0 + rows.mean() * CELL
        gaps.append({'area_m2': area_m2, 'center_xy': (cx_m, cy_m)})
    gaps.sort(key=lambda g: -g['area_m2'])
    print(f"large gaps (>{MIN_GAP_M2:.0f} m²): {len(gaps)}")

    # For each gap, place a tile, derive home, generate plan
    base = r'C:\Users\rharbach.STAHLY\.claude\skills\auterion-plan-generator\examples\base_terrain_following.plan'
    patched = os.path.join(args.dir, '_patched_gap_base.plan')

    # Read existing homes
    home_path = args.homes
    homes_content = open(home_path).read()

    next_id = max(t['id'] for t in sized) + 1
    new_tiles = []
    new_homes = []
    for gi, gap in enumerate(gaps):
        cx, cy = gap['center_xy']
        # Bearing from k=10 longest within 1500m
        b = k_longest_bearing(corridor_xy, near_xy=(cx, cy), radius=1500.0, k=10)
        if b is None: continue
        # Crude clip
        th = math.radians(b)
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
        # Strict bearing inside clipped polygon
        edges = []
        n = len(corridor_xy)
        for i in range(n):
            a = corridor_xy[i]; bb = corridor_xy[(i+1)%n]
            mid = ((a[0]+bb[0])/2, (a[1]+bb[1])/2)
            if not point_in_polygon(mid, clipped): continue
            dx, dy = bb[0]-a[0], bb[1]-a[1]
            L = math.hypot(dx, dy)
            if L < 0.5: continue
            brg = math.degrees(math.atan2(dx, dy)) % 180
            edges.append((L, brg))
        if len(edges) < 3:
            # fallback to crude bearing
            b_final = b
        else:
            edges.sort(reverse=True)
            top10 = edges[:10]
            total = sum(L for L,_ in top10)
            b_final = sum(L*x for L,x in top10) / total
        # Re-clip with final bearing
        th = math.radians(b_final)
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
        # Measure
        _th = -math.radians(b_final)
        _c, _s = math.cos(_th), math.sin(_th)
        rotp = [(_c*x + _s*y, -_s*x + _c*y) for x, y in clipped]
        perp_extent = max(p[0] for p in rotp) - min(p[0] for p in rotp)
        along_extent = max(p[1] for p in rotp) - min(p[1] for p in rotp)
        d_req = required_d_home(along_extent, perp_extent)
        if d_req is None: d_req = 600.0
        # HOME offset
        th = math.radians(b_final)
        ox = math.sin(th) * d_req
        oy = math.cos(th) * d_req
        hx, hy = cx + ox, cy + oy
        home_lat, home_lon = to_ll(hx, hy)
        # Polygon in lat/lon
        poly_ll = [to_ll(x, y) for x, y in clipped]
        tile = {
            'id': next_id,
            'spine_idx': -1,  # gap-fill, no spine
            'center_lat': to_ll(cx, cy)[0], 'center_lon': to_ll(cx, cy)[1],
            'bearing_deg': b_final,
            'home_lat': home_lat, 'home_lon': home_lon,
            'home_name': f"G{gi+1:03d}",
            'home_dist_m': d_req,
            'polygon_latlon': poly_ll,
            'gap_fill': True,
        }
        # Generate plan
        plan_name = f"fergus_{next_id:03d}.plan"
        out = os.path.join(args.dir, plan_name)
        plan = json.load(open(base))
        sv = next(it for it in plan['mission']['items'] if it.get('complexItemType')=='survey')
        sv['angle'] = b_final
        sv['TransectStyleComplexItem']['Items'] = []
        open(patched,'wb').write(json.dumps(plan,separators=(',',':')).encode('utf-8'))
        try:
            build_mission(patched, out, home=(home_lat, home_lon),
                         agl_target=70.0, speed=8.0, cross_margin=25.0,
                         polygon=[(p[0],p[1]) for p in poly_ll],
                         figure8_duration=15.0)
            e = estimate(out)
            print(f"  gap {gi+1} ({gap['area_m2']/4046.86:.1f} ac): tile #{next_id} AMC {e['amc']:.2f}")
            new_tiles.append(tile)
            new_homes.append({'name': f"G{gi+1:03d}", 'lat': home_lat, 'lon': home_lon})
            next_id += 1
        except Exception as ex:
            print(f"  gap {gi+1}: failed: {ex}")

    # Append to sized json
    sized_all = sized + new_tiles
    open(os.path.join(args.dir, 'tiles_sized_v2.json'), 'w').write(json.dumps(sized_all, indent=2))

    # Append homes to KML
    pm = ""
    for h in new_homes:
        pm += f'  <Placemark><name>{h["name"]}</name><Point><coordinates>{h["lon"]},{h["lat"]},0</coordinates></Point></Placemark>\n'
    open(home_path, 'w').write(homes_content.replace('</Document>', pm + '</Document>'))

    print(f"\nAdded {len(new_tiles)} gap-fill tiles, {len(new_homes)} new homes")


if __name__ == '__main__':
    main()
