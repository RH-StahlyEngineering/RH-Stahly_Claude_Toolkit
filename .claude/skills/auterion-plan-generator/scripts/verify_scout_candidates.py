"""Verify the 4 candidates from the low-precision scout at full LOS sensitivity
(PATH_SAMPLE_M=25, LINE_SAMPLES=100). For each, also report the original launch's
VLOS at full sensitivity for comparison."""
import os, sys, json

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SKILL_DIR, 'scripts'))
from dem_lookup import terrain_amsl
from los_check import (
    extract_flight_path, interpolate_path, los_line_clear,
    OPERATOR_EYE_M, hav,
)

PLAN_DIR = 'C:/Users/rharbach.STAHLY/Documents/Auterion Mission Control/Missions'

# (label, files_pair, original_ll, scouted_alt_ll)
CASES = [
    ('Pair 6 (L6)', ('Fergus13.plan', 'Fergus14.plan'),
     (47.27476, -109.25332), (47.276110, -109.249341)),
    ('Pair 7 (L7)', ('Fergus15.plan', 'Fergus16.plan'),
     (47.26383, -109.28697), (47.265180, -109.290948)),
    ('Pair 8 (L8)', ('Fergus17.plan', 'Fergus18.plan'),
     (47.25977, -109.31117), (47.259770, -109.313159)),
    ('Pair 9 (L9)', ('Fergus19.plan', 'Fergus20.plan'),
     (47.26004, -109.34256), (47.26004, -109.34256)),
]

def vlos_pct(launch_ll, combined_path):
    op_ground = terrain_amsl(*launch_ll)
    op_amsl = op_ground + OPERATOR_EYE_M
    blocked = 0; worst = 0.0; worst_d = 0
    for p in combined_path:
        clear, below, _ = los_line_clear(launch_ll, op_amsl, (p[0], p[1]), p[2], samples=100)
        if not clear:
            blocked += 1
            if below > worst:
                worst = below
                worst_d = hav(launch_ll, (p[0], p[1]))
    pct = 100.0 * (len(combined_path) - blocked) / len(combined_path) if combined_path else 0
    return pct, blocked, worst, worst_d, op_ground

for label, (ef, wf), orig, alt in CASES:
    east_plan = json.load(open(os.path.join(PLAN_DIR, ef)))
    west_plan = json.load(open(os.path.join(PLAN_DIR, wf)))
    path = interpolate_path(extract_flight_path(east_plan) + extract_flight_path(west_plan), 25)
    o_pct, o_blocked, o_worst, o_dist, o_elev = vlos_pct(orig, path)
    a_pct, a_blocked, a_worst, a_dist, a_elev = vlos_pct(alt, path)
    drive = hav(orig, alt)
    print(f'\n=== {label}: {ef} + {wf} ===')
    print(f'  Original  ({orig[0]:.6f}, {orig[1]:.6f}) elev {o_elev:.0f} m  VLOS {o_pct:.2f}%  '
          f'worst block {o_worst:.1f} m at {o_dist:.0f} m')
    print(f'  Scouted   ({alt[0]:.6f}, {alt[1]:.6f}) elev {a_elev:.0f} m  VLOS {a_pct:.2f}%  '
          f'worst block {a_worst:.1f} m at {a_dist:.0f} m')
    print(f'  Drive distance from original: {drive:.0f} m')
    print(f'  Elevation change: {a_elev - o_elev:+.0f} m')
    print(f'  VLOS improvement: {a_pct - o_pct:+.2f} percentage points')
