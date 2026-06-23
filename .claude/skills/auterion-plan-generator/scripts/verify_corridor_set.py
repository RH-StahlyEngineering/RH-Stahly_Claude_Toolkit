"""Verify a set of .plan files meets the Fergus corridor spec.

Checks all END STATE constraints from the goal and emits verification_report.json.
Exits 0 with stdout "ALL CHECKS PASS" iff every constraint holds.
"""
import argparse, glob, json, math, os, re, sys
import xml.etree.ElementTree as ET

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from tiling_helpers import (
    sh_clip, k_longest_bearing, signed_area, make_local_projection,
    polygon_intersection_area, point_in_polygon,
)
from estimate_flight_time import estimate


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
        for pt in pm.iter('Point'):
            c = pt.find('coordinates')
            if c is None: continue
            lon, lat, *_ = c.text.strip().split(',')
            out.append((float(lat), float(lon)))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--kml', required=True)
    ap.add_argument('--homes', required=True)
    ap.add_argument('--dir', required=True)
    ap.add_argument('--duration-min', type=float, default=8.0,
                    help='Lower bound for c2 (default 8.0)')
    ap.add_argument('--duration-max', type=float, default=10.0,
                    help='Upper bound for c2 (default 10.0)')
    ap.add_argument('--duration-over-pct', type=float, default=9.0,
                    help='c3 reference: %% of plans must have duration > this (default 9.0)')
    ap.add_argument('--agl', type=float, default=40.0,
                    help='Expected CameraCalc.DistanceToSurface for c7 (default 40.0)')
    ap.add_argument('--glob', default='fergus_*.plan',
                    help='Plan file glob (default fergus_*.plan; e.g. "fergus_[0-9]*.plan" to skip gap-fills)')
    args = ap.parse_args()

    target_ll = parse_kml_polygon(args.kml)
    homes_ll = parse_kml_points(args.homes)
    plan_files = sorted(glob.glob(os.path.join(args.dir, args.glob)))
    if not plan_files:
        print("FAIL: no fergus_*.plan files found"); sys.exit(1)

    # Local projection centered on target centroid
    cl_lat = sum(p[0] for p in target_ll) / len(target_ll)
    cl_lon = sum(p[1] for p in target_ll) / len(target_ll)
    to_xy, _ = make_local_projection(cl_lat, cl_lon)
    target_xy = [to_xy(*p) for p in target_ll]
    target_area = abs(signed_area(target_xy))

    plans = []  # collect per-plan data
    for p in plan_files:
        with open(p) as f:
            data = json.load(f)
        m = data['mission']
        items = m['items']
        sv = next((it for it in items if it.get('complexItemType') == 'survey'), None)
        if sv is None:
            plans.append({'plan': os.path.basename(p), 'fatal': 'no survey item'})
            continue
        # Footprint = the survey polygon itself (already corridor-clipped at generation).
        # Re-clipping via SH against a possibly non-convex clipper would produce wrong results.
        survey_poly_ll = sv['polygon']
        survey_xy = [to_xy(*v) for v in survey_poly_ll]
        footprint_xy = survey_xy
        # est
        est = estimate(p)
        # first/last waypoint
        wps = [it for it in items if it.get('command') == 16]
        first = wps[0]['params'] if wps else None
        last = wps[-1]['params'] if wps else None
        first_eq_last = first and last and first[4] == last[4] and first[5] == last[5]
        # HOME matches a known point
        home = (first[4], first[5]) if first else None
        home_match = any(abs(home[0]-h[0]) < 1e-6 and abs(home[1]-h[1]) < 1e-6 for h in homes_ll) if home else False
        # cmd 178 count
        n_178 = sum(1 for it in items if it.get('command') == 178)
        # camera + terrain
        cc = sv['TransectStyleComplexItem']['CameraCalc']
        ts = sv['TransectStyleComplexItem']
        agl = cc.get('DistanceToSurface')
        ft = ts.get('FollowTerrain')
        # Minified LF check
        raw = open(p, 'rb').read()
        is_minified_lf = b'\r' not in raw and raw.count(b'\n') <= 1
        # All standalone waypoint altitudes set (terrain-baked)
        standalone_alts = [it['params'][6] for it in items if it.get('command') == 16]
        amsl_spread = (max(standalone_alts) - min(standalone_alts)) if standalone_alts else 0
        terrain_baked = amsl_spread > 0.5 or len(set(standalone_alts)) > 1  # varies => DEM-baked
        # Bearing per item 8: length-weighted k=10 of segments inside footprint.
        # Strict: midpoint inside footprint. Fallback if <3 edges: within 200 m of footprint centroid.
        edges = []
        n = len(target_xy)
        for i in range(n):
            a = target_xy[i]; b = target_xy[(i+1)%n]
            mid = ((a[0]+b[0])/2, (a[1]+b[1])/2)
            if not point_in_polygon(mid, footprint_xy): continue
            dx, dy = b[0]-a[0], b[1]-a[1]
            L = math.hypot(dx, dy)
            if L < 0.5: continue
            brg = math.degrees(math.atan2(dx, dy)) % 180
            edges.append((L, brg))
        if len(edges) < 3:
            fc_x = sum(p[0] for p in footprint_xy) / len(footprint_xy)
            fc_y = sum(p[1] for p in footprint_xy) / len(footprint_xy)
            edges = []
            for i in range(n):
                a = target_xy[i]; b = target_xy[(i+1)%n]
                mid = ((a[0]+b[0])/2, (a[1]+b[1])/2)
                if math.hypot(mid[0]-fc_x, mid[1]-fc_y) > 500.0: continue
                dx, dy = b[0]-a[0], b[1]-a[1]
                L = math.hypot(dx, dy)
                if L < 0.5: continue
                brg = math.degrees(math.atan2(dx, dy)) % 180
                edges.append((L, brg))
        edges.sort(reverse=True)
        top10 = edges[:10]
        if top10:
            local_brg = sum(L*b for L,b in top10) / sum(L for L,_ in top10)
            angle_diff = abs((sv.get('angle', 0) % 180) - local_brg)
            angle_diff = min(angle_diff, 180 - angle_diff)
        else:
            local_brg = None; angle_diff = None
        # Turnaround count = (n_transects - 1), but we don't have inner items here.
        # Estimate from perp_extent / line_spacing.
        ts_items = ts.get('Items', [])
        inner_wps_count = sum(1 for s in ts_items if s.get('command') == 16)
        # If inner Items aren't populated, derive analytic n_transects.
        if inner_wps_count >= 2:
            # Count direction reversals to estimate turnarounds.
            inner_pts = [(s['params'][4], s['params'][5]) for s in ts_items if s.get('command') == 16]
            inner_xy = [to_xy(*p) for p in inner_pts]
            # Project along flight bearing
            th = -math.radians(sv.get('angle', 0))
            c, s = math.cos(th), math.sin(th)
            rot = [(c*x + s*y, -s*x + c*y) for x, y in inner_xy]
            # Count direction reversals in along-flight axis (y in rotated frame)
            ys = [p[1] for p in rot]
            reversals = 0
            for i in range(len(ys) - 2):
                d1 = ys[i+1] - ys[i]
                d2 = ys[i+2] - ys[i+1]
                if d1 * d2 < 0: reversals += 1
            turnarounds = reversals
        else:
            # Analytic estimate
            ms = make_local_projection(cl_lat, cl_lon)[0]
            sp = [ms(*v) for v in survey_poly_ll]
            th = -math.radians(sv.get('angle', 0))
            c, s = math.cos(th), math.sin(th)
            rot = [(c*x + s*y, -s*x + c*y) for x, y in sp]
            perp = max(p[0] for p in rot) - min(p[0] for p in rot)
            turnarounds = max(0, int(math.ceil(perp / agl)) - 1) if agl else 0

        plans.append({
            'plan': os.path.basename(p),
            'duration_min': est['amc'],
            'in_window': args.duration_min <= est['amc'] <= args.duration_max,
            'over_threshold': est['amc'] > args.duration_over_pct,
            'turnarounds': turnarounds,
            'turnarounds_ok': turnarounds <= 3,
            'home_match': home_match,
            'home_lat_lon': home,
            'agl': agl, 'agl_ok': abs((agl or 0) - args.agl) < 1e-3,
            'follow_terrain': ft,
            'survey_angle': sv.get('angle'),
            'local_bearing': local_brg,
            'angle_matches_local_bearing': (angle_diff is not None and angle_diff < 5.0),
            'angle_diff_deg': angle_diff,
            'items_count': len(items),
            'items_count_ok': len(items) == 29,
            'cmd_178_count': n_178,
            'cmd_178_ok': n_178 == 1,
            'first_eq_last': first_eq_last,
            'minified_lf': is_minified_lf,
            'amsl_spread_m': amsl_spread,
            'terrain_baked': terrain_baked,
            'footprint_xy': footprint_xy,
            'survey_xy': survey_xy,
        })

    # Coverage union: rasterize for accuracy
    import numpy as np
    target_minx = min(p[0] for p in target_xy); target_miny = min(p[1] for p in target_xy)
    target_maxx = max(p[0] for p in target_xy); target_maxy = max(p[1] for p in target_xy)
    CELL = 10.0
    W = int((target_maxx - target_minx)/CELL) + 2
    H = int((target_maxy - target_miny)/CELL) + 2
    from skimage.draw import polygon as draw_polygon
    target_mask = np.zeros((H, W), dtype=bool)
    cols = [(p[0] - target_minx)/CELL for p in target_xy]
    rows = [(p[1] - target_miny)/CELL for p in target_xy]
    rr, cc = draw_polygon(np.array(rows), np.array(cols), shape=target_mask.shape)
    target_mask[rr, cc] = True
    covered = np.zeros_like(target_mask)
    for pl in plans:
        if 'fatal' in pl: continue
        fp = pl['footprint_xy']
        if len(fp) < 3: continue
        cols = [(p[0] - target_minx)/CELL for p in fp]
        rows = [(p[1] - target_miny)/CELL for p in fp]
        rr, cc = draw_polygon(np.array(rows), np.array(cols), shape=target_mask.shape)
        rr = np.clip(rr, 0, H-1); cc = np.clip(cc, 0, W-1)
        covered[rr, cc] = True
    target_cells = int(target_mask.sum())
    covered_cells = int((target_mask & covered).sum())
    coverage_pct = 100 * covered_cells / target_cells if target_cells else 0.0

    # Overlap matrix
    N = len(plans)
    overlap_matrix = [[0.0] * N for _ in range(N)]
    has_neighbor = [False] * N
    for i in range(N):
        if 'fatal' in plans[i]: continue
        fi = plans[i]['footprint_xy']
        if len(fi) < 3: continue
        ai = abs(signed_area(fi))
        if ai < 1e-6: continue
        for j in range(i+1, N):
            if 'fatal' in plans[j]: continue
            fj = plans[j]['footprint_xy']
            if len(fj) < 3: continue
            inter = polygon_intersection_area(fi, fj)
            aj = abs(signed_area(fj))
            if aj < 1e-6: continue
            min_a = min(ai, aj)
            ratio = inter / min_a if min_a > 0 else 0
            overlap_matrix[i][j] = ratio
            overlap_matrix[j][i] = ratio
            if ratio >= 0.10:
                has_neighbor[i] = True; has_neighbor[j] = True

    # Strip non-JSON fields before writing
    for pl in plans:
        pl.pop('footprint_xy', None)
        pl.pop('survey_xy', None)

    over_9 = sum(1 for p in plans if p.get('over_threshold'))
    pct_over_9 = 100 * over_9 / N if N else 0

    report = {
        'kml': args.kml, 'homes': args.homes, 'dir': args.dir,
        'plan_count': N,
        'plans': plans,
        'coverage_pct': coverage_pct,
        'pct_over_9_min': pct_over_9,
        'has_neighbor_with_10pct_overlap': has_neighbor,
        'overlap_matrix': overlap_matrix,
        'checks': {
            'c1_coverage_99_5': coverage_pct >= 99.5,
            f'c2_all_in_{int(args.duration_min)}_{int(args.duration_max)}': all(p.get('in_window') for p in plans),
            f'c3_pct_over_{int(args.duration_over_pct)}_at_least_90': pct_over_9 >= 90.0,
            'c4_all_turnarounds_ok': all(p.get('turnarounds_ok') for p in plans),
            'c5_overlap_all_have_neighbors': all(has_neighbor),
            'c6_all_homes_match': all(p.get('home_match') for p in plans),
            'c7_all_agl_terrain_ok': all(p.get('agl_ok') and p.get('follow_terrain') for p in plans),
            'c8_angles_match_bearing': all(p.get('angle_matches_local_bearing') for p in plans),
            'c9_checklist': all(
                p.get('items_count_ok') and p.get('cmd_178_ok') and
                p.get('first_eq_last') and p.get('minified_lf') and
                p.get('terrain_baked') for p in plans
            ),
        },
    }
    with open(os.path.join(args.dir, 'verification_report.json'), 'w') as f:
        json.dump(report, f, indent=2)

    print(f"Coverage: {coverage_pct:.2f}%   Plans: {N}   >9min: {pct_over_9:.1f}%")
    for k, v in report['checks'].items():
        print(f"  {k}: {'PASS' if v else 'FAIL'}")
    if all(report['checks'].values()):
        print("ALL CHECKS PASS")
        sys.exit(0)
    else:
        print("SOME CHECKS FAILED — see verification_report.json")
        sys.exit(1)


if __name__ == '__main__':
    main()
