"""Apply the prior-scouted launch relocations to Pairs 6/7/8 of the
powerline-clearance plans (Fergus13..Fergus18) and re-verify both VLOS and
powerline transect clearance. Also check whether the new HOME positions put
the climb/RTL transit path through an ADJACENT pair's coverage zone or close
to powerlines at non-transect points.
"""
import os, sys, json, math

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SKILL_DIR, 'scripts'))

import dem_lookup
_explicit = os.path.expanduser('~/.claude/dem_cache/dem_ee0aa3a8a9d0.json')
if os.path.exists(_explicit):
    dem_lookup._explicit_meta_paths.insert(0, _explicit)
    dem_lookup._local_dem = None
    dem_lookup._local_meta = None

from dem_lookup import terrain_amsl
from generate_fergus_pair1 import minified_write, hav, AGL
from los_check import check_plan_vlos, extract_flight_path, interpolate_path
from generate_powerline_pairs import load_powerline, KML_POWERLINE

PLAN_DIR = 'C:/Users/rharbach.STAHLY/Documents/Auterion Mission Control/Missions'
MIN_LATERAL_M = AGL * math.tan(math.radians(15))  # 18.78 m

RELOCATIONS = [
    # (label, pair_files, new_lat, new_lon)
    ('Pair 6', ('Fergus13.plan', 'Fergus14.plan'), 47.276110, -109.249341),
    ('Pair 7', ('Fergus15.plan', 'Fergus16.plan'), 47.265180, -109.290948),
    ('Pair 8', ('Fergus17.plan', 'Fergus18.plan'), 47.259770, -109.313159),
]

def pt_to_polyline_min_dist_m(pt_lat, pt_lon, line):
    best = float('inf')
    m_lat = 111132.0
    m_lon = 111132.0 * math.cos(math.radians(pt_lat))
    for i in range(len(line) - 1):
        a, b = line[i], line[i+1]
        ax = (a[1] - pt_lon) * m_lon; ay = (a[0] - pt_lat) * m_lat
        bx = (b[1] - pt_lon) * m_lon; by = (b[0] - pt_lat) * m_lat
        dx = bx - ax; dy = by - ay
        L2 = dx*dx + dy*dy
        if L2 == 0:
            d = math.hypot(ax, ay)
        else:
            t = max(0.0, min(1.0, -(ax*dx + ay*dy) / L2))
            d = math.hypot(ax + t*dx, ay + t*dy)
        if d < best:
            best = d
    return best


def main():
    powerline = load_powerline(KML_POWERLINE)

    # Apply relocations
    print('=== Applying relocations ===')
    for label, (ef, wf), nlat, nlon in RELOCATIONS:
        ground = terrain_amsl(nlat, nlon)
        for fn in [ef, wf]:
            p = os.path.join(PLAN_DIR, fn)
            plan = json.load(open(p))
            old = list(plan['mission']['plannedHomePosition'])
            plan['mission']['plannedHomePosition'] = [nlat, nlon, ground]
            minified_write(p, plan)
            print(f'  {label} {fn}: HOME ({old[0]:.6f},{old[1]:.6f},{old[2]:.0f}m) -> '
                  f'({nlat:.6f},{nlon:.6f},{ground:.0f}m)  drive {hav((old[0],old[1]),(nlat,nlon)):.0f} m')

    # VLOS re-check on all 6 relocated plans
    print(f'\n=== VLOS re-check (full precision) ===')
    print(f'{"Plan":<20}{"Pts":<6}{"VLOS%":<8}{"Status"}')
    for _, (ef, wf), *_ in RELOCATIONS:
        for fn in [ef, wf]:
            r = check_plan_vlos(os.path.join(PLAN_DIR, fn))
            tag = 'OK' if r['los_pct'] >= 99.99 else f"partial {r['worst_below_m']:.1f}m at {r['worst_dist_m']:.0f}m"
            print(f'{fn:<20}{r["path_pts"]:<6}{r["los_pct"]:<8.2f}{tag}')

    # Powerline-transect clearance check.
    # Distinguish:
    #  - TRANSECT positions = CorridorScan inner Items (sustained flight lines) — must satisfy >=19 m
    #  - NON-TRANSECT positions = standalone waypoints (fig-8, cross-line) + climb/RTL transit
    #    — brief crossings accepted by user
    print(f'\n=== Powerline lateral clearance check (>= {MIN_LATERAL_M:.1f} m required on transects) ===')
    print(f'{"Plan":<20}{"Transect pts":<14}{"Below floor":<13}{"Min m":<8}{"Status"}')
    for _, (ef, wf), *_ in RELOCATIONS:
        for fn in [ef, wf]:
            plan = json.load(open(os.path.join(PLAN_DIR, fn)))
            # Get ONLY the CorridorScan inner Items (the sustained transects)
            cs = next(it for it in plan['mission']['items'] if it.get('complexItemType') == 'CorridorScan')
            inner = cs['TransectStyleComplexItem'].get('Items', [])
            transect_pts = []
            for it in inner:
                if it.get('command') == 16:
                    p = it['params']
                    if p[4] is not None and p[5] is not None and p[6] is not None:
                        transect_pts.append((p[4], p[5], p[6]))
            # Interpolate transect path at 10 m
            transect_interp = interpolate_path(transect_pts, 10.0) if transect_pts else []
            below = 0; min_d = float('inf')
            for la, lo, _ in transect_interp:
                d = pt_to_polyline_min_dist_m(la, lo, powerline)
                if d < min_d: min_d = d
                if d < MIN_LATERAL_M: below += 1
            tag = 'OK' if below == 0 else f'TRANSECT VIOLATION ({below})'
            print(f'{fn:<20}{len(transect_interp):<14}{below:<13}{min_d:<8.1f}{tag}')

    # Adjacent-pair coverage overlap check.
    # For each relocated pair, find pairs whose meeting points are within 2*TILE_LEN_M (= 3.6 km)
    # of the relocated HOME. Adjacent pairs' coverage may now overlap with the relocated drone's
    # transit zone.
    print(f'\n=== Adjacent-pair proximity check ===')
    # Build map: pair_num -> meeting_ll from CorridorScan polyline last point
    all_pairs = []
    for n in range(1, 10):
        ef = os.path.join(PLAN_DIR, f'Fergus{2*n+1}.plan')
        wf = os.path.join(PLAN_DIR, f'Fergus{2*n+2}.plan')
        if not (os.path.exists(ef) and os.path.exists(wf)): continue
        p = json.load(open(ef))
        cs = next(it for it in p['mission']['items'] if it.get('complexItemType') == 'CorridorScan')
        meet = tuple(cs['polyline'][-1])
        home = p['mission']['plannedHomePosition'][:2]
        all_pairs.append((n, tuple(home), meet))
    for label, (ef, wf), nlat, nlon in RELOCATIONS:
        rn = int(label.split()[1])
        rh = (nlat, nlon)
        print(f'\n{label} relocated HOME {rh} -- nearby pairs:')
        for n, h, m in all_pairs:
            if n == rn: continue
            d_to_meet = hav(rh, m)
            d_to_home = hav(rh, h)
            if d_to_meet < 4000 or d_to_home < 4000:
                tag = '<-- WITHIN 3.6 km, transit zones may overlap' if d_to_meet < 3600 else ''
                print(f'  Pair {n}: HOME {h} ({d_to_home:.0f} m), meeting {m} ({d_to_meet:.0f} m) {tag}')


if __name__ == '__main__':
    main()
