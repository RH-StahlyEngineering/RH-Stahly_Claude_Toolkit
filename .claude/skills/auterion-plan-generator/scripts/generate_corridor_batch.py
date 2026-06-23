"""Generate all sized tiles' .plan files. Run estimate.py on each, write summary."""
import json, math, os, sys, time
sys.path.insert(0, os.path.dirname(__file__))
from generate_lidar_mission import build_mission
from estimate_flight_time import estimate

if __name__ == '__main__':
    out_dir = sys.argv[1] if len(sys.argv) > 1 else \
        r'C:\Users\rharbach.STAHLY\Documents\Auterion Mission Control\Missions\Fergus_corridor'
    base = sys.argv[2] if len(sys.argv) > 2 else \
        r'C:\Users\rharbach.STAHLY\.claude\skills\auterion-plan-generator\examples\base_terrain_following.plan'

    sized = json.load(open(os.path.join(out_dir, 'tiles_sized.json')))
    patched = os.path.join(out_dir, '_patched_base.plan')

    results = []
    t0 = time.time()
    for i, t in enumerate(sized):
        plan = json.load(open(base))
        sv = next(it for it in plan['mission']['items'] if it.get('complexItemType') == 'survey')
        sv['angle'] = t['bearing_deg']
        sv['TransectStyleComplexItem']['Items'] = []
        open(patched, 'wb').write(json.dumps(plan, separators=(',', ':')).encode('utf-8'))

        plan_name = f"fergus_{t['id']:03d}.plan"
        out_path = os.path.join(out_dir, plan_name)
        try:
            stats = build_mission(patched, out_path,
                                  home=(t['home_lat'], t['home_lon']),
                                  agl_target=40.0, speed=8.0, cross_margin=25.0,
                                  polygon=[(p[0], p[1]) for p in t['polygon_latlon']],
                                  figure8_duration=15.0)
            est = estimate(out_path)
            results.append({
                'id': t['id'], 'plan': plan_name,
                'home_lat': t['home_lat'], 'home_lon': t['home_lon'],
                'home_dist_m': t['home_dist_m'],
                'bearing_deg': t['bearing_deg'],
                'predicted_analytic_min': t['predicted_amc_min'],
                'estimate_amc_min': est['amc'],
                'estimate_survey_min': est['survey'],
                'estimate_transit_min': est['transit'],
                'items': stats['items'],
                'first_eq_last': stats['first_eq_last'],
                'in_range_8_10': 8.0 <= est['amc'] <= 10.0,
            })
            elapsed = time.time() - t0
            print(f"[{i+1}/{len(sized)}] {plan_name}: analytic {t['predicted_amc_min']:.1f} -> estimate.py {est['amc']:.2f} min  ({'OK' if 8<=est['amc']<=10 else 'OUT'})  [{elapsed:.0f}s elapsed]")
        except Exception as e:
            print(f"  FAIL tile {t['id']}: {e}")
            results.append({'id': t['id'], 'error': str(e)})

    with open(os.path.join(out_dir, 'generation_results.json'), 'w') as f:
        json.dump(results, f, indent=2)

    in_range = [r for r in results if r.get('in_range_8_10')]
    print(f"\nGenerated {len(results)} plans; {len(in_range)} in [8,10]")
