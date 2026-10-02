"""Build comparison KML for Options A and B, plus a comparison printout.

Option A (BLUE markers): keep 18 original 3.6km plans, scout RPIC observer spots
  - Pairs 4, 7, 9: RPIC found within 100m of corridor (from earlier scout)
  - Pairs 5, 6, 8: NO 100% VLOS found within 3 km (infeasible at original tile length)

Option B (GREEN swaths): shorten tiles for pairs 5, 6, 8 to give 100% VLOS from launch
  - Pairs 1-4, 7, 9: unchanged 3.6km tiles
  - Pairs 5, 6, 8: shortened per-direction tile lengths
  - Pairs 4, 7, 9 still need RPIC observer points (same as option A)
"""
import os, sys, json, re, math

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SKILL_DIR, 'scripts'))

import dem_lookup
_explicit = os.path.expanduser('~/.claude/dem_cache/dem_ee0aa3a8a9d0.json')
if os.path.exists(_explicit):
    dem_lookup._explicit_meta_paths.insert(0, _explicit)
    dem_lookup._local_dem = None
    dem_lookup._local_meta = None

from shapely.geometry import LineString, Polygon
from shapely.ops import unary_union
from coverage_check_multi import make_projection, parse_plan_geometry, parse_kml_polygon
from estimate_flight_time import estimate as AMC_minutes

PLAN_DIR = 'C:/Users/rharbach.STAHLY/Documents/Auterion Mission Control/Missions'
KML_HIGHWAY    = 'C:/Users/rharbach.STAHLY/Downloads/HighwayCenterline.kml'
KML_POWERLINE  = 'C:/Users/rharbach.STAHLY/Downloads/Hilger-Roy existing line — joined.kml'
TARGET_KML     = 'C:/Users/rharbach.STAHLY/Downloads/Fergus Hilger-Roy — corridor union.kml'
RPIC_JSON_V2   = 'C:/Users/rharbach.STAHLY/Downloads/Fergus_41m_rpic_observer_points.json'   # v2 scout for pairs 4, 7, 9
AB_JSON        = 'C:/Users/rharbach.STAHLY/Downloads/Fergus_41m_options_AB.json'
OUT_KML        = 'C:/Users/rharbach.STAHLY/Downloads/Fergus_41m_options_AB_comparison.kml'

AGL = 41.0
TURNAROUND_M = 60.96

ORIGINAL_PLANS = [f'Fergus{n}.plan' for n in range(3, 21)]
# Option B uses different files for pairs 5, 6, 8
OPTION_B_PLANS = []
for n in range(1, 10):
    e_idx = 2*n + 1; w_idx = 2*n + 2
    if n in (5, 6, 8):
        OPTION_B_PLANS.append(f'Fergus{e_idx}_short.plan')
        OPTION_B_PLANS.append(f'Fergus{w_idx}_short.plan')
    else:
        OPTION_B_PLANS.append(f'Fergus{e_idx}.plan')
        OPTION_B_PLANS.append(f'Fergus{w_idx}.plan')


def load_linestring(path):
    txt = open(path, 'r', encoding='utf-8').read()
    m = re.search(r'<LineString[\s\S]*?<coordinates>([\s\S]+?)</coordinates>', txt)
    return [tuple(map(float, t.split(',')[:2][::-1])) for t in m.group(1).strip().split()]


def coords(latlons):
    return ' '.join(f'{lon:.7f},{lat:.7f},0' for (lat, lon) in latlons)


def make_back_projection(ref_lat, ref_lon):
    m_lat = 111132.0
    m_lon = 111132.0 * math.cos(math.radians(ref_lat))
    def from_xy(x_m, y_m):
        return (ref_lat + y_m / m_lat, ref_lon + x_m / m_lon)
    return from_xy


def polyline_to_swath_ll(geom_ll, to_xy, from_xy):
    xy = [to_xy(*p) for p in geom_ll]
    def extend_pt(p_end, p_prev, dist):
        dx = p_end[0] - p_prev[0]; dy = p_end[1] - p_prev[1]
        L = math.hypot(dx, dy)
        if L == 0: return p_end
        return (p_end[0] + dist*dx/L, p_end[1] + dist*dy/L)
    if len(xy) < 2: return None, None
    ext = [extend_pt(xy[0], xy[1], TURNAROUND_M)] + xy[1:-1] + [extend_pt(xy[-1], xy[-2], TURNAROUND_M)]
    if len(xy) == 2:
        ext = [extend_pt(xy[0], xy[1], TURNAROUND_M), extend_pt(xy[-1], xy[-2], TURNAROUND_M)]
    line = LineString(ext)
    sw = line.buffer(AGL + AGL/2, cap_style='flat', join_style='round')
    if sw.geom_type == 'Polygon':
        ext_ll = [from_xy(x, y) for (x, y) in sw.exterior.coords]
    else:
        ext_ll = [from_xy(x, y) for (x, y) in list(sw.geoms)[0].exterior.coords]
    return ext_ll, sw


def main():
    rpic_v2 = {r['pair']: r for r in json.load(open(RPIC_JSON_V2))}
    ab = json.load(open(AB_JSON))
    # ab is a dict with string keys "5", "6", "8"

    # Project to local meters using highway centroid
    highway = load_linestring(KML_HIGHWAY)
    powerline = load_linestring(KML_POWERLINE)
    target_outer, target_holes = parse_kml_polygon(TARGET_KML)[0]
    ref_lat = sum(p[0] for p in target_outer) / len(target_outer)
    ref_lon = sum(p[1] for p in target_outer) / len(target_outer)
    to_xy, _ = make_projection(ref_lat, ref_lon)
    from_xy = make_back_projection(ref_lat, ref_lon)
    target_poly = Polygon([to_xy(*p) for p in target_outer],
                          [[to_xy(*p) for p in h] for h in target_holes])
    target_ac = target_poly.area / 4046.86

    # Geometries for original 18 plans
    orig_swaths_xy = []
    orig_swaths_ll = {}
    orig_geoms = {}
    for fn in ORIGINAL_PLANS:
        kind, geom, _, _, _ = parse_plan_geometry(os.path.join(PLAN_DIR, fn))
        orig_geoms[fn] = geom
        ll, xy = polyline_to_swath_ll(geom, to_xy, from_xy)
        if ll is None: continue
        orig_swaths_ll[fn] = ll
        orig_swaths_xy.append(xy)
    orig_union = unary_union(orig_swaths_xy)
    orig_covered_ac = orig_union.intersection(target_poly).area / 4046.86
    orig_total_minutes = sum(AMC_minutes(os.path.join(PLAN_DIR, fn))['amc'] for fn in ORIGINAL_PLANS)

    # Geometries for Option B set
    b_swaths_xy = []
    b_swaths_ll = {}
    b_geoms = {}
    b_minutes = 0.0
    for fn in OPTION_B_PLANS:
        p = os.path.join(PLAN_DIR, fn)
        if not os.path.exists(p):
            continue   # tile that couldn't get 100% VLOS at any shortened length
        kind, geom, _, _, _ = parse_plan_geometry(p)
        b_geoms[fn] = geom
        ll, xy = polyline_to_swath_ll(geom, to_xy, from_xy)
        if ll is None: continue
        b_swaths_ll[fn] = ll
        b_swaths_xy.append(xy)
        try: b_minutes += AMC_minutes(p)['amc']
        except: pass
    b_union = unary_union(b_swaths_xy)
    b_covered_ac = b_union.intersection(target_poly).area / 4046.86

    # ----- Comparison printout -----
    print('=' * 88)
    print(f'{"":<6}{"Option A (3.6km, RPIC observers)":<42}{"Option B (shortened pairs 5,6,8)":<42}')
    print('=' * 88)
    print(f'{"Plans":<6}{"18 plans (all 3.6 km tiles)":<42}{f"{sum(1 for p in OPTION_B_PLANS if os.path.exists(os.path.join(PLAN_DIR, p)))} plans (12 full + shorter pair 5/6/8)":<42}')
    print(f'{"Time":<6}{f"{orig_total_minutes:.1f} min total":<42}{f"{b_minutes:.1f} min total":<42}')
    print(f'{"Cover":<6}{f"{orig_covered_ac:.0f} ac = {100*orig_covered_ac/target_ac:.2f}% target":<42}'
          f'{f"{b_covered_ac:.0f} ac = {100*b_covered_ac/target_ac:.2f}% target":<42}')
    print(f'{"Pairs":<6}{"4, 7, 9 RPIC observer SCOUTED":<42}{"4, 7, 9 RPIC observer NEEDED (same)":<42}')
    print(f'{"":<6}{"5, 6, 8: INFEASIBLE (no 100% LOS pt)":<42}{"5, 6, 8: 100% VLOS from LAUNCH (shortened)":<42}')
    print('=' * 88)
    print()
    print('Pairs 5, 6, 8 details under Option B:')
    for n in (5, 6, 8):
        b = ab[str(n)]['option_b']
        e_len = b['e_len_m']; w_len = b['w_len_m']
        e_s = f'{e_len:.0f} m' if e_len else 'no plan (even 150m blocked)'
        w_s = f'{w_len:.0f} m' if w_len else 'no plan (even 150m blocked)'
        print(f'  Pair {n}: East tile = {e_s}, West tile = {w_s}  (was 3600+3600 m)')

    # ----- Build KML -----
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>',
           '<name>Fergus 41m Options A vs B</name>',
           '<description>Comparison of two ways to handle the 3 pairs whose drones go out of VLOS:\n'
           'OPTION A (BLUE): keep 3.6km tiles, find RPIC observer locations. INFEASIBLE for pairs 5,6,8.\n'
           'OPTION B (GREEN): shorten tiles for pairs 5,6,8 so drone stays within VLOS from launch.\n\n'
           f'Total coverage: A = {100*orig_covered_ac/target_ac:.2f}% of target, B = {100*b_covered_ac/target_ac:.2f}% of target.\n'
           f'Flight time: A = {orig_total_minutes:.0f} min, B = {b_minutes:.0f} min.</description>']

    out.extend([
        '<Style id="target"><LineStyle><color>ff00ff00</color><width>2</width></LineStyle>'
        '<PolyStyle><color>2000ff00</color></PolyStyle></Style>',
        '<Style id="hwy"><LineStyle><color>ff00ffff</color><width>2</width></LineStyle></Style>',
        '<Style id="wire"><LineStyle><color>ff0000ff</color><width>3</width></LineStyle></Style>',
        '<Style id="orig_swath"><LineStyle><color>ffaaaaaa</color><width>1</width></LineStyle>'
        '<PolyStyle><color>30aaaaaa</color></PolyStyle></Style>',
        '<Style id="b_swath"><LineStyle><color>ff00ff44</color><width>2</width></LineStyle>'
        '<PolyStyle><color>6000ff44</color></PolyStyle></Style>',
        '<Style id="b_orig_swath"><LineStyle><color>ffaaaaaa</color><width>1</width></LineStyle>'
        '<PolyStyle><color>30aaaaaa</color></PolyStyle></Style>',
        '<Style id="rpic"><IconStyle><scale>1.4</scale>'
        '<Icon><href>http://maps.google.com/mapfiles/kml/paddle/blu-stars.png</href></Icon></IconStyle></Style>',
        '<Style id="launch"><IconStyle><scale>1.1</scale>'
        '<Icon><href>http://maps.google.com/mapfiles/kml/paddle/orange-circle.png</href></Icon></IconStyle></Style>',
        '<Style id="infeasible"><IconStyle><scale>1.3</scale><color>ff0000ff</color>'
        '<Icon><href>http://maps.google.com/mapfiles/kml/paddle/red-stars.png</href></Icon></IconStyle></Style>',
    ])

    # Context layers
    out.append('<Folder><name>Context</name>')
    holes_kml = ''
    for h in target_holes:
        holes_kml += f'<innerBoundaryIs><LinearRing><coordinates>{coords(h)}</coordinates></LinearRing></innerBoundaryIs>'
    out.append(f'<Placemark><name>Target corridor union (1622 ac)</name><styleUrl>#target</styleUrl>'
               f'<Polygon><outerBoundaryIs><LinearRing><coordinates>{coords(target_outer)}</coordinates></LinearRing></outerBoundaryIs>{holes_kml}</Polygon></Placemark>')
    out.append(f'<Placemark><name>Hwy 81 centerline</name><styleUrl>#hwy</styleUrl>'
               f'<LineString><coordinates>{coords(highway)}</coordinates></LineString></Placemark>')
    out.append(f'<Placemark><name>Hilger-Roy powerline</name><styleUrl>#wire</styleUrl>'
               f'<LineString><coordinates>{coords(powerline)}</coordinates></LineString></Placemark>')
    out.append('</Folder>')

    # OPTION A folder
    out.append(f'<Folder><name>OPTION A (BLUE) — keep 3.6km tiles + RPIC observer points</name>'
               f'<description>{orig_covered_ac:.0f} ac covered ({100*orig_covered_ac/target_ac:.1f}% of target), '
               f'{orig_total_minutes:.0f} min flight time. Pairs 4,7,9 have RPIC points within 100m of corridor. '
               f'Pairs 5,6,8 are INFEASIBLE at 3.6km tile length (no 100% VLOS point within 3 km).</description>')
    # Original 18 swaths
    out.append('<Folder><name>Original 18 plan swaths</name>')
    for fn in ORIGINAL_PLANS:
        ll = orig_swaths_ll.get(fn)
        if not ll: continue
        out.append(f'<Placemark><name>{fn}</name><styleUrl>#orig_swath</styleUrl>'
                   f'<Polygon><outerBoundaryIs><LinearRing><coordinates>{coords(ll)}</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>')
    out.append('</Folder>')
    # RPIC observer points for pairs 4, 7, 9 (already scouted with corridor filter)
    out.append('<Folder><name>RPIC observer points (BLUE stars) - pairs 4, 7, 9</name>')
    for pair_n in (4, 7, 9):
        r = rpic_v2.get(pair_n)
        if not r or not r.get('rpic'):
            continue
        rp = r['rpic']
        out.append(f'<Placemark><name>RPIC pair {pair_n} (Fergus{2*pair_n+1}/{2*pair_n+2})</name>'
                   f'<description>Distance from launch: {rp["dist_from_launch_m"]:.0f} m. '
                   f'Ground elev: {rp["ground_amsl_m"]:.0f} m AMSL.</description>'
                   f'<styleUrl>#rpic</styleUrl>'
                   f'<Point><coordinates>{rp["lon"]:.7f},{rp["lat"]:.7f},0</coordinates></Point></Placemark>')
    out.append('</Folder>')
    # Infeasible markers at pair 5, 6, 8 launches
    out.append('<Folder><name>INFEASIBLE under Option A (RED stars) - pairs 5, 6, 8</name>')
    for pair_n in (5, 6, 8):
        a = ab[str(pair_n)]
        L = a['launch']
        out.append(f'<Placemark><name>Pair {pair_n} INFEASIBLE under Option A</name>'
                   f'<description>No 100% VLOS RPIC point found within 3 km of launch. '
                   f'Use Option B (shortened tiles) instead.</description>'
                   f'<styleUrl>#infeasible</styleUrl>'
                   f'<Point><coordinates>{L["lon"]:.7f},{L["lat"]:.7f},0</coordinates></Point></Placemark>')
    out.append('</Folder>')
    out.append('</Folder>')   # close OPTION A

    # OPTION B folder
    out.append(f'<Folder><name>OPTION B (GREEN) — shorten pairs 5, 6, 8 tiles for VLOS-from-launch</name>'
               f'<description>{b_covered_ac:.0f} ac covered ({100*b_covered_ac/target_ac:.1f}% of target), '
               f'{b_minutes:.0f} min flight time. Pairs 4,7,9 still need RPIC observer points '
               f'(same as Option A). Pairs 5,6,8 use SHORTER tiles flyable 100% from launch.</description>')
    # Unchanged pairs gray swaths
    out.append('<Folder><name>Unchanged 12 plan swaths (pairs 1-4, 7, 9)</name>')
    for fn in OPTION_B_PLANS:
        if fn.endswith('_short.plan'): continue
        ll = orig_swaths_ll.get(fn)
        if not ll: continue
        out.append(f'<Placemark><name>{fn}</name><styleUrl>#b_orig_swath</styleUrl>'
                   f'<Polygon><outerBoundaryIs><LinearRing><coordinates>{coords(ll)}</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>')
    out.append('</Folder>')
    # Shortened pair swaths in GREEN
    out.append('<Folder><name>SHORTENED swaths (GREEN) - pairs 5, 6, 8</name>')
    for fn in OPTION_B_PLANS:
        if not fn.endswith('_short.plan'): continue
        ll = b_swaths_ll.get(fn)
        if not ll: continue
        out.append(f'<Placemark><name>{fn}</name><styleUrl>#b_swath</styleUrl>'
                   f'<Polygon><outerBoundaryIs><LinearRing><coordinates>{coords(ll)}</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>')
    out.append('</Folder>')
    # RPIC pts still needed (pairs 4, 7, 9)
    out.append('<Folder><name>RPIC observer points (BLUE stars) - pairs 4, 7, 9 still needed</name>')
    for pair_n in (4, 7, 9):
        r = rpic_v2.get(pair_n)
        if not r or not r.get('rpic'): continue
        rp = r['rpic']
        out.append(f'<Placemark><name>RPIC pair {pair_n} (Fergus{2*pair_n+1}/{2*pair_n+2})</name>'
                   f'<description>Same RPIC point as Option A. '
                   f'Distance from launch: {rp["dist_from_launch_m"]:.0f} m. '
                   f'Ground: {rp["ground_amsl_m"]:.0f} m AMSL.</description>'
                   f'<styleUrl>#rpic</styleUrl>'
                   f'<Point><coordinates>{rp["lon"]:.7f},{rp["lat"]:.7f},0</coordinates></Point></Placemark>')
    out.append('</Folder>')
    out.append('</Folder>')   # close OPTION B

    # Launches
    out.append('<Folder><name>All launches</name>')
    from option_a_b_scout import load_launches
    launches = load_launches('C:/Users/rharbach.STAHLY/Downloads/HomePoints.kml')
    launches.sort(key=lambda L: -L[1])
    for i, (la, lo) in enumerate(launches, start=1):
        out.append(f'<Placemark><name>L{i} (pair {i})</name><styleUrl>#launch</styleUrl>'
                   f'<Point><coordinates>{lo:.7f},{la:.7f},0</coordinates></Point></Placemark>')
    out.append('</Folder>')

    out.append('</Document></kml>')
    open(OUT_KML, 'w', encoding='utf-8').write('\n'.join(out))
    print(f'\nWrote KML: {OUT_KML}')
    print(f'Size: {os.path.getsize(OUT_KML)} bytes')


if __name__ == '__main__':
    main()
