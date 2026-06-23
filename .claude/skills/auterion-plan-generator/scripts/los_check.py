"""Visual Line of Sight (VLOS) check for a .plan against bare-earth DEM terrain.

Models the operator standing at the launch (plannedHomePosition) with eye height
OPERATOR_EYE_M above ground. For every point along the drone's flight path,
shoots a 3D line from operator eye to drone position and samples the terrain
underneath that line. If at any sample the terrain rises above the line, the
operator cannot see the drone at that moment — VLOS is lost.

Uses local DEM raster (sub-microsecond per lookup), so checking a full mission
takes a fraction of a second.

Outputs per plan:
  - % of flight path with clear VLOS
  - max meters of terrain intrusion above the LOS line (= "worst block")
  - distance from launch where the worst block occurs
  - count of blocked flight-path points

Limitations:
  - Bare-earth DEM only — does NOT model trees / buildings / vehicles.
  - Operator position is exactly plannedHomePosition; real operator may stand
    ±10 m off, which can matter for marginal cases.
  - Ignores Earth-curvature (negligible at this range).
"""
import argparse
import glob
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dem_lookup import terrain_amsl, ensure_dem_for_bbox

OPERATOR_EYE_M = 2.0          # eye height above ground at launch
DEFAULT_PATH_SAMPLE_M = 25.0   # interpolation cadence along straight-line segments
DEFAULT_LOS_SAMPLES   = 100    # samples along each operator-to-drone line


def hav(a, b):
    R = 6371000.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dl = math.radians(b[1] - a[1]); dp = p2 - p1
    x = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*R*math.asin(math.sqrt(x))


def los_line_clear(op_ll, op_amsl, drone_ll, drone_amsl, samples=DEFAULT_LOS_SAMPLES):
    """Return (clear: bool, worst_below_m: float, worst_point_or_None).
    worst_below_m > 0 means terrain rose that many meters above the LOS line at
    its worst point."""
    worst_below = 0.0
    worst_pt = None
    for i in range(1, samples):
        frac = i / samples
        lat = op_ll[0] + frac * (drone_ll[0] - op_ll[0])
        lon = op_ll[1] + frac * (drone_ll[1] - op_ll[1])
        line_amsl = op_amsl + frac * (drone_amsl - op_amsl)
        ground = terrain_amsl(lat, lon)
        below = ground - line_amsl
        if below > worst_below:
            worst_below = below
            worst_pt = (lat, lon, ground, line_amsl)
    return (worst_below <= 0.0), worst_below, worst_pt


def extract_flight_path(plan):
    """Return [(lat, lon, amsl)] for every flight-path waypoint in the plan.
    Includes standalone cmd 16 (fig-8, cross-line) and CorridorScan inner Items."""
    path = []
    for it in plan['mission']['items']:
        if it.get('command') == 16:
            p = it['params']
            if p[4] is not None and p[5] is not None and p[6] is not None:
                path.append((p[4], p[5], p[6]))
        elif it.get('complexItemType') == 'CorridorScan':
            tsi = it['TransectStyleComplexItem']
            for sub in tsi.get('Items', []):
                if sub.get('command') == 16:
                    p = sub['params']
                    if p[4] is not None and p[5] is not None and p[6] is not None:
                        path.append((p[4], p[5], p[6]))
    return path


def interpolate_path(path, step_m):
    """Subdivide consecutive waypoints so no segment is longer than step_m."""
    if len(path) < 2:
        return list(path)
    out = [path[0]]
    for i in range(1, len(path)):
        a = path[i-1]; b = path[i]
        d = hav(a[:2], b[:2])
        if d <= step_m:
            out.append(b); continue
        n = int(math.ceil(d / step_m))
        for j in range(1, n + 1):
            f = j / n
            out.append((a[0] + f * (b[0] - a[0]),
                        a[1] + f * (b[1] - a[1]),
                        a[2] + f * (b[2] - a[2])))
    return out


def check_plan_vlos(plan_path, sample_m=DEFAULT_PATH_SAMPLE_M, line_samples=DEFAULT_LOS_SAMPLES):
    plan = json.load(open(plan_path))
    home = plan['mission']['plannedHomePosition']
    op_ll = (home[0], home[1])
    op_ground = terrain_amsl(*op_ll)
    op_amsl = op_ground + OPERATOR_EYE_M

    path = extract_flight_path(plan)
    if not path:
        return None
    path_interp = interpolate_path(path, sample_m)

    blocked = []
    worst_below = 0.0; worst_dist = 0.0; worst_drone_pt = None
    for p in path_interp:
        clear, below, _ = los_line_clear(op_ll, op_amsl, (p[0], p[1]), p[2], samples=line_samples)
        if not clear:
            d = hav(op_ll, (p[0], p[1]))
            blocked.append((p, below, d))
            if below > worst_below:
                worst_below = below; worst_dist = d; worst_drone_pt = p

    return {
        'plan': os.path.basename(plan_path),
        'launch_ll': op_ll,
        'launch_ground_amsl': op_ground,
        'path_pts': len(path_interp),
        'blocked_pts': len(blocked),
        'los_pct': 100.0 * (len(path_interp) - len(blocked)) / len(path_interp),
        'worst_below_m': worst_below,
        'worst_dist_m': worst_dist,
        'worst_drone_pt': worst_drone_pt,
    }


def warm_dem_bbox_for(plans, pad=0.02):
    lats, lons = [], []
    for pp in plans:
        plan = json.load(open(pp))
        h = plan['mission']['plannedHomePosition']; lats.append(h[0]); lons.append(h[1])
        for it in plan['mission']['items']:
            if it.get('command') == 16:
                p = it['params']
                if p[4] and p[5]: lats.append(p[4]); lons.append(p[5])
            elif it.get('complexItemType') == 'CorridorScan':
                for sub in it['TransectStyleComplexItem'].get('Items', []):
                    if sub.get('command') == 16:
                        p = sub['params']
                        if p[4] and p[5]: lats.append(p[4]); lons.append(p[5])
    if lats:
        ensure_dem_for_bbox(min(lats)-pad, max(lats)+pad, min(lons)-pad, max(lons)+pad,
                            resolution_m=10.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--plans-glob', required=True, action='append')
    ap.add_argument('--sample-m', type=float, default=DEFAULT_PATH_SAMPLE_M)
    ap.add_argument('--line-samples', type=int, default=DEFAULT_LOS_SAMPLES)
    args = ap.parse_args()

    plan_files = []
    for pat in args.plans_glob:
        plan_files.extend(sorted(glob.glob(pat)))

    warm_dem_bbox_for(plan_files)

    print(f'\nVLOS check (operator eye height {OPERATOR_EYE_M} m above launch ground)')
    print(f'Path interpolation: {args.sample_m:.0f} m / Line samples: {args.line_samples}\n')
    print(f'{"Plan":<22}{"Pts":<6}{"VLOS%":<8}{"Block":<7}{"WorstBelow":<12}{"WorstDist":<12}{"Status"}')
    print('-' * 100)
    for pp in plan_files:
        r = check_plan_vlos(pp, sample_m=args.sample_m, line_samples=args.line_samples)
        if r is None:
            print(f'{os.path.basename(pp):<22}  (no flight path)')
            continue
        if r['los_pct'] >= 99.99:
            tag = 'OK'
        elif r['los_pct'] >= 95:
            tag = 'minor partial loss'
        elif r['los_pct'] >= 80:
            tag = 'PARTIAL LOSS'
        else:
            tag = 'MAJOR LOSS'
        print(f'{r["plan"]:<22}{r["path_pts"]:<6}{r["los_pct"]:<8.2f}{r["blocked_pts"]:<7}'
              f'{r["worst_below_m"]:<12.1f}{r["worst_dist_m"]:<12.0f}{tag}')


if __name__ == '__main__':
    main()
