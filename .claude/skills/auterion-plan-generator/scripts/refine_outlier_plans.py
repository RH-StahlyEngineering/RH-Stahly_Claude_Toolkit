"""For each .plan outside [8,10], move HOME and regenerate until in range.

Strategy: read current estimate, compare to target ([8,10] with bias toward 9.5),
shift HOME along the survey-angle direction by an amount derived from the gap.
Limit to 4 iterations per tile.
"""
import argparse, glob, json, math, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from generate_lidar_mission import build_mission
from estimate_flight_time import estimate
from tiling_helpers import make_local_projection

LO = 8.0; HI = 12.0; TARGET = 10.5
MAX_ITER = 4
CRUISE = 15.0

def shift_home_for_target(home, tile_center_lat, tile_center_lon, survey_angle_deg,
                          current_amc, target_amc):
    """Compute a new HOME by moving along the survey-angle direction.

    Heuristic: ΔAMC ≈ 1.97 · (2·Δd_home) / 15 / 60. Solve for Δd_home.
    """
    delta_amc = target_amc - current_amc
    delta_dist_total = delta_amc / 1.97 * CRUISE * 60   # net change in total transit dist
    delta_d_home = delta_dist_total / 2.0               # one-way change
    to_xy, to_ll = make_local_projection(tile_center_lat, tile_center_lon)
    hx, hy = to_xy(home[0], home[1])
    # Direction from tile center to current home, normalized
    norm = math.hypot(hx, hy)
    if norm < 1e-6:
        # Home was at center — pick survey-angle direction
        th = math.radians(survey_angle_deg)
        dx, dy = math.sin(th), math.cos(th)
    else:
        dx, dy = hx / norm, hy / norm
    # New home position: shift along the same direction by delta_d_home
    new_hx = hx + dx * delta_d_home
    new_hy = hy + dy * delta_d_home
    return to_ll(new_hx, new_hy)


def main():
    global LO, HI, TARGET, MAX_ITER
    ap = argparse.ArgumentParser()
    ap.add_argument('--dir', required=True)
    ap.add_argument('--base', default=r'C:\Users\rharbach.STAHLY\.claude\skills\auterion-plan-generator\examples\base_terrain_following.plan')
    ap.add_argument('--duration-min', type=float, default=8.0)
    ap.add_argument('--duration-max', type=float, default=12.0)
    ap.add_argument('--target-amc', type=float, default=10.5)
    ap.add_argument('--agl', type=float, default=70.0)
    ap.add_argument('--max-iter', type=int, default=4)
    ap.add_argument('--glob', default='fergus_*.plan')
    args = ap.parse_args()
    LO = args.duration_min
    HI = args.duration_max
    TARGET = args.target_amc
    MAX_ITER = args.max_iter

    sized = {t['id']: t for t in json.load(open(os.path.join(args.dir, 'tiles_sized_v2.json')))}
    new_homes_added = []
    fixed = 0
    failed = []
    patched = os.path.join(args.dir, '_patched_base_v2.plan')

    for plan_path in sorted(glob.glob(os.path.join(args.dir, args.glob))):
        name = os.path.basename(plan_path)
        tid = int(name.replace('fergus_', '').replace('.plan', ''))
        tile = sized.get(tid)
        if tile is None: continue
        amc = estimate(plan_path)['amc']
        if LO <= amc <= HI:
            continue
        # Iterate
        home = (tile['home_lat'], tile['home_lon'])
        last_amc = amc
        for iteration in range(MAX_ITER):
            new_home = shift_home_for_target(home, tile['center_lat'], tile['center_lon'],
                                             tile['bearing_deg'], last_amc, TARGET)
            # Patch base
            plan = json.load(open(args.base))
            sv = next(it for it in plan['mission']['items'] if it.get('complexItemType') == 'survey')
            sv['angle'] = tile['bearing_deg']
            sv['TransectStyleComplexItem']['Items'] = []
            open(patched, 'wb').write(json.dumps(plan, separators=(',', ':')).encode('utf-8'))
            try:
                build_mission(patched, plan_path, home=new_home,
                              agl_target=args.agl, speed=8.0, cross_margin=25.0,
                              polygon=[(p[0], p[1]) for p in tile['polygon_latlon']],
                              figure8_duration=15.0)
                new_amc = estimate(plan_path)['amc']
                if LO <= new_amc <= HI:
                    home = new_home; last_amc = new_amc; break
                home = new_home; last_amc = new_amc
            except Exception as e:
                print(f"  {name} iter {iteration}: build_mission failed: {e}")
                break
        # Final check
        if LO <= last_amc <= HI:
            # Update tile + record home
            tile['home_lat'] = home[0]; tile['home_lon'] = home[1]
            new_homes_added.append({'lat': home[0], 'lon': home[1], 'name': f"R{tid:03d}",
                                    'from_tile': tid})
            fixed += 1
            print(f"  {name}: {amc:.2f} -> {last_amc:.2f} OK")
        else:
            failed.append({'plan': name, 'final_amc': last_amc, 'initial_amc': amc})
            print(f"  {name}: {amc:.2f} -> {last_amc:.2f} STILL OUT")

    # Write refinement summary
    with open(os.path.join(args.dir, 'refinement_results.json'), 'w') as f:
        json.dump({'fixed': fixed, 'failed': failed, 'new_homes': new_homes_added}, f, indent=2)
    print(f"\nFixed {fixed}, still out {len(failed)}")
    return new_homes_added


if __name__ == '__main__':
    main()
