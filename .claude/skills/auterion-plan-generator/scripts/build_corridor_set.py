"""End-to-end orchestrator: KML + HOMEs -> set of .plan files covering the corridor.

Runs the full workflow in one command:
  1. Pre-flight (DEM cache, KML parse, scipy/skimage import)
  2. Skeletonize corridor
  3. Place tiles + homes along spines (parameterized by --along/--perp/--target-amc/--agl)
  4. Generate .plan files for all tiles
  5. Refine outliers outside [duration_min, duration_max]
  6. Optional gap-fills at successive thresholds (suffixed as <prefix>_gap_NNN.plan)
  7. Simplify polygons via Douglas-Peucker (shapely)
  8. Rename + copy to root in east->west or west->east order
  9. Verify

Cleanup rule: only deletes files matching <prefix>_*.plan; never touches other .plan files.

Example:
  python build_corridor_set.py \
    --kml /path/corridor.kml --homes /path/homes.kml \
    --out-dir "C:/Users/.../Missions" --fc-subdir Fergus_corridor \
    --agl 70 --along 1000 --duration-max 12 --target-amc 11 \
    --east-to-west --gap-thresholds 8000,2000,500
"""
import argparse, json, math, os, shutil, subprocess, sys, glob

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)


def run(cmd, cwd=None):
    print(f"\n>>> {' '.join(cmd)}", file=sys.stderr)
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(r.stdout + r.stderr)
        raise RuntimeError(f"subcommand failed: {' '.join(cmd)}")
    print(r.stdout[-500:], file=sys.stderr)
    return r.stdout


def parse_corridor_bbox(kml_path):
    import re, xml.etree.ElementTree as ET
    tree = ET.parse(kml_path); root = tree.getroot()
    ns = re.compile(r'\{[^}]+\}')
    for e in root.iter(): e.tag = ns.sub('', e.tag)
    ring = next(root.iter('LinearRing'))
    lats, lons = [], []
    for tok in ring.find('coordinates').text.strip().split():
        lon, lat, *_ = tok.split(',')
        lats.append(float(lat)); lons.append(float(lon))
    pad_lat = 0.005; pad_lon = 0.005
    return (min(lats) - pad_lat, max(lats) + pad_lat,
            min(lons) - pad_lon, max(lons) + pad_lon)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--kml', required=True)
    ap.add_argument('--homes', required=True, help='Existing HOMEs KML (will be appended)')
    ap.add_argument('--out-dir', required=True, help='Missions root (where AMC loads from)')
    ap.add_argument('--fc-subdir', default='Fergus_corridor',
                    help='Working subdir under --out-dir (default: Fergus_corridor)')
    ap.add_argument('--prefix', default='fergus',
                    help='Plan filename prefix; gap-fills get <prefix>_gap_NNN.plan')

    ap.add_argument('--agl', type=float, default=40.0)
    ap.add_argument('--along', type=float, default=670.0)
    ap.add_argument('--perp', type=float, default=158.0)
    ap.add_argument('--target-amc', type=float, default=9.5)
    ap.add_argument('--duration-min', type=float, default=8.0)
    ap.add_argument('--duration-max', type=float, default=10.0)
    ap.add_argument('--gap-thresholds', default='',
                    help='Comma-separated m² thresholds for successive gap-fill passes (e.g. "8000,2000,500"). Empty = skip gap-fill.')
    ap.add_argument('--simplify-tolerance', type=float, default=10.0,
                    help='Douglas-Peucker tolerance in meters (default 10)')
    ap.add_argument('--east-to-west', action='store_true',
                    help='Number output as fergus_000=easternmost. Default is west->east.')

    ap.add_argument('--skip-dem-download', action='store_true',
                    help='Skip downloading bbox DEM (use existing cache)')
    ap.add_argument('--skip-verify', action='store_true')
    args = ap.parse_args()

    fc = os.path.join(args.out_dir, args.fc_subdir)
    os.makedirs(fc, exist_ok=True)
    placeholder = f"{args.prefix}_"

    # P0: pre-flight + DEM bbox download
    print("[P0] pre-flight + DEM cache", file=sys.stderr)
    from dem_lookup import terrain_amsl, ensure_dem_for_bbox
    if not args.skip_dem_download:
        bbox = parse_corridor_bbox(args.kml)
        meta_path = ensure_dem_for_bbox(*bbox)
        print(f"  DEM cached: {meta_path}", file=sys.stderr)

    # P1: skeletonize (uses corridor_tiler.py --phase skeletonize)
    run([sys.executable, os.path.join(SCRIPT_DIR, 'corridor_tiler.py'),
         '--kml', args.kml, '--homes', args.homes, '--out-dir', fc,
         '--phase', 'skeletonize'])

    # P2-P3: place homes + tiles (clip + size)
    run([sys.executable, os.path.join(SCRIPT_DIR, 'place_homes_and_tiles.py'),
         '--kml', args.kml, '--homes', args.homes, '--out-dir', fc,
         '--agl', str(args.agl), '--along', str(args.along), '--perp', str(args.perp),
         '--target-amc', str(args.target_amc)])
    shutil.copy(os.path.join(fc, 'HomePoints_extended.kml'), args.homes)

    # P4: generate plans
    run([sys.executable, os.path.join(SCRIPT_DIR, 'generate_corridor_batch_v2.py'), fc])

    # P5: refine outliers
    run([sys.executable, os.path.join(SCRIPT_DIR, 'refine_outlier_plans.py'),
         '--dir', fc, '--duration-min', str(args.duration_min),
         '--duration-max', str(args.duration_max),
         '--target-amc', str((args.duration_min + args.duration_max) / 2),
         '--agl', str(args.agl)])

    # P6: gap-fill passes
    for thresh_str in [t.strip() for t in args.gap_thresholds.split(',') if t.strip()]:
        thresh = float(thresh_str)
        print(f"[P6] gap-fill threshold {thresh} m²", file=sys.stderr)
        run([sys.executable, os.path.join(SCRIPT_DIR, 'fill_coverage_gaps.py'),
             '--kml', args.kml, '--homes', args.homes, '--dir', fc,
             '--along', str(args.along), '--perp', str(args.perp),
             '--target-amc', str(args.target_amc),
             '--min-gap-m2', str(thresh),
             '--plan-prefix', args.prefix])
        run([sys.executable, os.path.join(SCRIPT_DIR, 'refine_outlier_plans.py'),
             '--dir', fc, '--duration-min', str(args.duration_min),
             '--duration-max', str(args.duration_max),
             '--agl', str(args.agl)])

    # P7: DP simplify polygons via shapely
    if args.simplify_tolerance > 0:
        print(f"[P7] Douglas-Peucker simplify @ {args.simplify_tolerance} m", file=sys.stderr)
        simplify_polygons(fc, args.simplify_tolerance, args.kml)

    # P8: clean root + copy/rename
    print("[P8] cleanup + rename", file=sys.stderr)
    for f in glob.glob(os.path.join(args.out_dir, f"{args.prefix}_*.plan")):
        # SAFE: only deletes files matching this run's prefix
        os.remove(f)
    sized = json.load(open(os.path.join(fc, 'tiles_sized_v2.json')))
    main_tiles = [t for t in sized if not t.get('gap_fill')]
    gap_tiles = [t for t in sized if t.get('gap_fill')]
    keyfn = (lambda t: -t['center_lon']) if args.east_to_west else (lambda t: t['center_lon'])
    for new_idx, t in enumerate(sorted(main_tiles, key=keyfn)):
        src = os.path.join(fc, f"fergus_{t['id']:03d}.plan")
        if os.path.exists(src):
            shutil.copy(src, os.path.join(args.out_dir, f"{args.prefix}_{new_idx:03d}.plan"))
    for new_idx, t in enumerate(sorted(gap_tiles, key=keyfn)):
        src = os.path.join(fc, f"fergus_{t['id']:03d}.plan")
        if os.path.exists(src):
            shutil.copy(src, os.path.join(args.out_dir, f"{args.prefix}_gap_{new_idx:03d}.plan"))
    print(f"copied {len(main_tiles)} main + {len(gap_tiles)} gap-fills to {args.out_dir}",
          file=sys.stderr)

    # P9: verify (optional)
    if not args.skip_verify:
        run([sys.executable, os.path.join(SCRIPT_DIR, 'verify_corridor_set.py'),
             '--kml', args.kml, '--homes', args.homes, '--dir', fc,
             '--duration-min', str(args.duration_min),
             '--duration-max', str(args.duration_max),
             '--agl', str(args.agl)])


def simplify_polygons(fc, tol, kml_path):
    from shapely.geometry import Polygon
    sys.path.insert(0, SCRIPT_DIR)
    from tiling_helpers import make_local_projection
    import re, xml.etree.ElementTree as ET
    tree = ET.parse(kml_path); root = tree.getroot()
    ns = re.compile(r'\{[^}]+\}')
    for e in root.iter(): e.tag = ns.sub('', e.tag)
    ring = next(root.iter('LinearRing'))
    corr=[]
    for tok in ring.find('coordinates').text.strip().split():
        lon, lat, *_ = tok.split(',')
        corr.append((float(lat), float(lon)))
    if corr[0]==corr[-1]: corr=corr[:-1]
    cl_lat = sum(p[0] for p in corr)/len(corr); cl_lon = sum(p[1] for p in corr)/len(corr)
    to_xy, to_ll = make_local_projection(cl_lat, cl_lon)
    sized_path = os.path.join(fc, 'tiles_sized_v2.json')
    sized = json.load(open(sized_path))
    for t in sized:
        pxy = [to_xy(*v) for v in t['polygon_latlon']]
        if len(pxy) < 4: continue
        try:
            poly = Polygon(pxy).simplify(tol, preserve_topology=True)
            if poly.is_valid and not poly.is_empty:
                coords = list(poly.exterior.coords)[:-1]
                t['polygon_latlon'] = [list(to_ll(x, y)) for x, y in coords]
        except Exception:
            continue
    open(sized_path, 'w').write(json.dumps(sized, indent=2))
    # Re-emit plans
    base = os.path.join(os.path.dirname(SCRIPT_DIR), 'examples', 'base_terrain_following.plan')
    patched = os.path.join(fc, '_patched_simplify.plan')
    from generate_lidar_mission import build_mission
    for t in sized:
        out = os.path.join(fc, f"fergus_{t['id']:03d}.plan")
        p = json.load(open(base))
        sv = next(it for it in p['mission']['items'] if it.get('complexItemType')=='survey')
        sv['angle'] = t['bearing_deg']
        sv['TransectStyleComplexItem']['Items'] = []
        open(patched, 'wb').write(json.dumps(p, separators=(',',':')).encode('utf-8'))
        build_mission(patched, out, home=(t['home_lat'], t['home_lon']),
                      agl_target=t.get('agl_used', 70.0), speed=8.0, cross_margin=25.0,
                      polygon=[(p[0], p[1]) for p in t['polygon_latlon']],
                      figure8_duration=15.0)


if __name__ == '__main__':
    main()
