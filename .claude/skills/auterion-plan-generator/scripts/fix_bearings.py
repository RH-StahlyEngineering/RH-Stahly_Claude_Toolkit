"""For each .plan, iteratively converge the survey.angle to the spec-strict bearing
(k=10 longest corridor segments with midpoints inside the polygon)."""
import argparse, glob, json, math, os, sys, re
import xml.etree.ElementTree as ET
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tiling_helpers import make_local_projection, sh_clip, point_in_polygon, decimate_polygon
from generate_lidar_mission import build_mission
from estimate_flight_time import estimate

ALONG_M = 700.0
PERP_M = 158.0


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


def strict_bearing(corridor_xy, footprint_xy):
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--kml', required=True)
    ap.add_argument('--dir', required=True)
    args = ap.parse_args()

    corridor_ll = parse_kml_polygon(args.kml)
    cl_lat = sum(p[0] for p in corridor_ll)/len(corridor_ll)
    cl_lon = sum(p[1] for p in corridor_ll)/len(corridor_ll)
    to_xy, to_ll = make_local_projection(cl_lat, cl_lon)
    corridor_xy = [to_xy(*p) for p in corridor_ll]

    sized = json.load(open(os.path.join(args.dir, 'tiles_sized_v2.json')))
    sized_by_id = {t['id']: t for t in sized}
    base = r'C:\Users\rharbach.STAHLY\.claude\skills\auterion-plan-generator\examples\base_terrain_following.plan'
    patched = os.path.join(args.dir, '_patched_bearing.plan')

    fixed = 0
    for plan_path in sorted(glob.glob(os.path.join(args.dir, 'fergus_*.plan'))):
        name = os.path.basename(plan_path)
        tid = int(name.replace('fergus_', '').replace('.plan', ''))
        tile = sized_by_id.get(tid)
        if tile is None: continue
        # Read current angle and polygon
        plan = json.load(open(plan_path))
        sv = next(it for it in plan['mission']['items'] if it.get('complexItemType')=='survey')
        cur_angle = sv['angle']
        polygon_ll = sv['polygon']
        polygon_xy = [to_xy(*v) for v in polygon_ll]
        # Compute strict bearing
        b = strict_bearing(corridor_xy, polygon_xy)
        if b is None: continue
        # Diff
        d = abs((cur_angle % 180) - b)
        d = min(d, 180 - d)
        if d < 4.5: continue   # already passes c8 (verifier uses <5)
        # Iterate: re-clip with new bearing, recompute bearing
        cx_xy = (sum(p[0] for p in polygon_xy)/len(polygon_xy),
                 sum(p[1] for p in polygon_xy)/len(polygon_xy))
        # Use tile center for rectangle origin (not polygon centroid)
        tcx_xy = to_xy(tile['center_lat'], tile['center_lon'])
        cur_b = b
        for it in range(5):
            th = math.radians(cur_b)
            fx, fy = math.sin(th), math.cos(th); px, py = -fy, fx
            cx, cy = tcx_xy
            rect = [
                (cx + fx*ALONG_M/2 + px*PERP_M/2, cy + fy*ALONG_M/2 + py*PERP_M/2),
                (cx + fx*ALONG_M/2 - px*PERP_M/2, cy + fy*ALONG_M/2 - py*PERP_M/2),
                (cx - fx*ALONG_M/2 - px*PERP_M/2, cy - fy*ALONG_M/2 - py*PERP_M/2),
                (cx - fx*ALONG_M/2 + px*PERP_M/2, cy - fy*ALONG_M/2 + py*PERP_M/2),
            ]
            clipped = sh_clip(corridor_xy, rect)
            clipped = decimate_polygon(clipped, 5.0)
            if len(clipped) < 3: break
            new_b = strict_bearing(corridor_xy, clipped)
            if new_b is None: break
            if abs(new_b - cur_b) < 0.5: break
            cur_b = new_b
        # Regenerate the plan with new bearing+polygon
        if len(clipped) < 3: continue
        new_poly_ll = [to_ll(x, y) for x, y in clipped]
        p2 = json.load(open(base))
        sv2 = next(it for it in p2['mission']['items'] if it.get('complexItemType')=='survey')
        sv2['angle'] = cur_b
        sv2['TransectStyleComplexItem']['Items'] = []
        open(patched, 'wb').write(json.dumps(p2, separators=(',', ':')).encode('utf-8'))
        try:
            build_mission(patched, plan_path, home=(tile['home_lat'], tile['home_lon']),
                          agl_target=70.0, speed=8.0, cross_margin=25.0,
                          polygon=[(p[0], p[1]) for p in new_poly_ll],
                          figure8_duration=15.0)
            amc = estimate(plan_path)['amc']
            if 8.0 <= amc <= 10.0:
                tile['bearing_deg'] = cur_b
                tile['polygon_latlon'] = new_poly_ll
                fixed += 1
        except Exception as e:
            print(f"  {name}: failed: {e}")

    open(os.path.join(args.dir, 'tiles_sized_v2.json'), 'w').write(json.dumps(sized, indent=2))
    print(f"\nFixed bearings on {fixed} plans")


if __name__ == '__main__':
    main()
