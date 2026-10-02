"""Final mission KML: 41m highway-centerline with PERCH concept + Option B fallback for Pair 8.

Plan set:
  - Pairs 1, 2, 3: Fergus3..8 at 3.6km, 100% VLOS from launch (no perch needed)
  - Pair 4:        Fergus9/10 at 3.6km, perch 100m from L4
  - Pair 5:        Fergus11/12 at 3.6km, perch 1836m from L5 (elevated)
  - Pair 6:        Fergus13/14 at 3.6km, perch 608m from L6
  - Pair 7:        Fergus15/16 at 3.6km, perch 608m from L7 (high hill)
  - Pair 8:        Fergus17_short/18_short (1200m east, 600m west) - no perch found, fallback
  - Pair 9:        Fergus19/20 at 3.6km, perch 608m from L9

KML legend:
  - Blue stars = perch points (RPIC standing position)
  - Orange circles = launch/landing points (VO + hot swap)
  - Gray translucent = unchanged 3.6km plan swaths
  - Green translucent = shortened pair 8 swaths
  - Red star = pair 8 launch (no perch found)
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
KML_LAUNCHES   = 'C:/Users/rharbach.STAHLY/Downloads/HomePoints.kml'
TARGET_KML     = 'C:/Users/rharbach.STAHLY/Downloads/Fergus Hilger-Roy — corridor union.kml'
PERCH_JSON     = 'C:/Users/rharbach.STAHLY/Downloads/Fergus_41m_perch_points.json'
AB_JSON        = 'C:/Users/rharbach.STAHLY/Downloads/Fergus_41m_options_AB.json'
OUT_KML        = 'C:/Users/rharbach.STAHLY/Downloads/Fergus_41m_FINAL_perch_set.kml'

AGL = 41.0
TURNAROUND_M = 60.96

# Final plan set: pair 8 uses shortened plans, all others use originals
FINAL_PLANS = []
for n in range(1, 10):
    e_idx = 2*n + 1; w_idx = 2*n + 2
    if n == 8:
        FINAL_PLANS.append(f'Fergus{e_idx}_short.plan')
        FINAL_PLANS.append(f'Fergus{w_idx}_short.plan')
    else:
        FINAL_PLANS.append(f'Fergus{e_idx}.plan')
        FINAL_PLANS.append(f'Fergus{w_idx}.plan')


def load_linestring(path):
    txt = open(path, 'r', encoding='utf-8').read()
    m = re.search(r'<LineString[\s\S]*?<coordinates>([\s\S]+?)</coordinates>', txt)
    return [tuple(map(float, t.split(',')[:2][::-1])) for t in m.group(1).strip().split()]


def load_launches(path):
    txt = open(path, 'r', encoding='utf-8').read()
    pms = re.findall(r'<Placemark[^>]*>([\s\S]*?)</Placemark>', txt)
    out = []
    for pm in pms:
        nm = re.search(r'<name>([^<]+)</name>', pm)
        pt = re.search(r'<Point[\s\S]*?<coordinates>([^<]+)</coordinates>', pm)
        if not (nm and pt): continue
        if 'launch' not in nm.group(1).strip().lower(): continue
        lon, lat = pt.group(1).strip().split(',')[:2]
        out.append((float(lat), float(lon)))
    return out


def coords(latlons):
    return ' '.join(f'{lon:.7f},{lat:.7f},0' for (lat, lon) in latlons)


def make_back_projection(ref_lat, ref_lon):
    m_lat = 111132.0
    m_lon = 111132.0 * math.cos(math.radians(ref_lat))
    def from_xy(x_m, y_m):
        return (ref_lat + y_m / m_lat, ref_lon + x_m / m_lon)
    return from_xy


def polyline_to_swath(geom_ll, to_xy, from_xy):
    xy = [to_xy(*p) for p in geom_ll]
    def extend_pt(pe, pp, d):
        dx = pe[0]-pp[0]; dy = pe[1]-pp[1]; L = math.hypot(dx, dy)
        return pe if L == 0 else (pe[0]+d*dx/L, pe[1]+d*dy/L)
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
    perches = {int(k): v for k, v in json.load(open(PERCH_JSON)).items()}
    ab = json.load(open(AB_JSON))

    highway = load_linestring(KML_HIGHWAY)
    powerline = load_linestring(KML_POWERLINE)
    launches = load_launches(KML_LAUNCHES)
    launches.sort(key=lambda L: -L[1])
    target_outer, target_holes = parse_kml_polygon(TARGET_KML)[0]
    ref_lat = sum(p[0] for p in target_outer) / len(target_outer)
    ref_lon = sum(p[1] for p in target_outer) / len(target_outer)
    to_xy, _ = make_projection(ref_lat, ref_lon)
    from_xy = make_back_projection(ref_lat, ref_lon)
    target_poly = Polygon([to_xy(*p) for p in target_outer],
                          [[to_xy(*p) for p in h] for h in target_holes])
    target_ac = target_poly.area / 4046.86

    # Compute final mission coverage + time
    swaths_xy = []
    swaths_ll = {}
    minutes = 0.0
    for fn in FINAL_PLANS:
        p = os.path.join(PLAN_DIR, fn)
        if not os.path.exists(p):
            print(f'!! MISSING: {fn}')
            continue
        kind, geom, _, _, _ = parse_plan_geometry(p)
        ll, xy = polyline_to_swath(geom, to_xy, from_xy)
        if ll is None: continue
        swaths_ll[fn] = ll
        swaths_xy.append(xy)
        try: minutes += AMC_minutes(p)['amc']
        except: pass
    union = unary_union(swaths_xy)
    covered_ac = union.intersection(target_poly).area / 4046.86

    print('=' * 80)
    print('FINAL MISSION SET (perch concept + pair 8 fallback)')
    print('=' * 80)
    print(f'Plans:               {len(FINAL_PLANS)} ({sum(1 for fn in FINAL_PLANS if not fn.endswith("_short.plan"))} full 3.6km + {sum(1 for fn in FINAL_PLANS if fn.endswith("_short.plan"))} shortened pair 8)')
    print(f'Total flight time:   {minutes:.1f} min ({minutes/60:.2f} hr)')
    print(f'Target coverage:     {covered_ac:.0f} ac of {target_ac:.0f} ac = {100*covered_ac/target_ac:.2f}%')
    print()
    print('PERCH ASSIGNMENTS (5 pairs):')
    print(f'{"Pair":<5}{"Plans":<22}{"Perch":<28}{"Dist from launch":<18}{"Elev gain"}')
    for n in (4, 5, 6, 7, 9):
        r = perches.get(n)
        if r and r.get('perch'):
            p = r['perch']
            perch_s = f'({p["lat"]:.5f},{p["lon"]:.5f})'
            dist_s = f'{p["dist_from_launch_m"]:.0f} m ({p["dist_from_launch_m"]/1609.34:.2f} mi)'
            elev_s = f'{p["elev_above_launch_m"]:+.0f} m'
            plans_s = f'Fergus{2*n+1}/{2*n+2}'
            print(f'{n:<5}{plans_s:<22}{perch_s:<28}{dist_s:<18}{elev_s}')
    print()
    print('LAUNCH-ONLY (3 pairs - no perch needed):')
    for n in (1, 2, 3):
        L = launches[n-1]
        plans_s = f'Fergus{2*n+1}/{2*n+2}'
        print(f'  Pair {n}: {plans_s} - VLOS from launch ({L[0]:.5f},{L[1]:.5f})')
    print()
    print('FALLBACK TO SHORTENED TILES (pair 8 - no perch within 1.5 mi):')
    b = ab['8']['option_b']
    print(f'  Pair 8: Fergus17_short.plan (east tile = {b["e_len_m"]:.0f} m)')
    print(f'          Fergus18_short.plan (west tile = {b["w_len_m"]:.0f} m)')
    print()

    # Comparison vs previous options
    # Re-load original 18 (need swaths)
    orig_plans = [f'Fergus{n}.plan' for n in range(3, 21)]
    orig_swaths_xy = []
    orig_minutes = 0.0
    for fn in orig_plans:
        p = os.path.join(PLAN_DIR, fn)
        kind, geom, _, _, _ = parse_plan_geometry(p)
        ll, xy = polyline_to_swath(geom, to_xy, from_xy)
        if ll is None: continue
        orig_swaths_xy.append(xy)
        try: orig_minutes += AMC_minutes(p)['amc']
        except: pass
    orig_union = unary_union(orig_swaths_xy)
    orig_covered_ac = orig_union.intersection(target_poly).area / 4046.86

    print('=' * 80)
    print(f'{"":<7}{"Option A":<24}{"Option B":<24}{"FINAL (perch+pair8 B)"}')
    print(f'{"Plans":<7}{"18 @ 3.6km":<24}{"18 mixed":<24}{f"{len(FINAL_PLANS)} mixed"}')
    print(f'{"Time":<7}{f"{orig_minutes:.0f} min":<24}{"149 min":<24}{f"{minutes:.0f} min"}')
    print(f'{"Cover":<7}{f"{100*orig_covered_ac/target_ac:.1f}%":<24}{"64.3%":<24}{f"{100*covered_ac/target_ac:.1f}%"}')
    print(f'{"VLOS":<7}{"3 pairs INFEASIBLE":<24}{"all from launch":<24}{"5 pairs need perch + 1 short"}')
    print('=' * 80)

    # Build KML
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>',
           '<name>Fergus 41m FINAL - Perch concept + pair 8 fallback</name>',
           f'<description>17 full 3.6km plans + 2 shortened pair 8 plans. '
           f'{100*covered_ac/target_ac:.1f}% target coverage, {minutes:.0f} min flight time. '
           f'5 pairs need a perch within 1.5 mi (RPIC drives there after takeoff); '
           f'3 pairs flyable from launch; 1 pair (#8) requires shortened tiles.</description>']

    out.extend([
        '<Style id="target"><LineStyle><color>ff00ff00</color><width>2</width></LineStyle>'
        '<PolyStyle><color>2000ff00</color></PolyStyle></Style>',
        '<Style id="hwy"><LineStyle><color>ff00ffff</color><width>2</width></LineStyle></Style>',
        '<Style id="wire"><LineStyle><color>ff0000ff</color><width>3</width></LineStyle></Style>',
        '<Style id="full"><LineStyle><color>ffaaaaaa</color><width>1</width></LineStyle>'
        '<PolyStyle><color>30aaaaaa</color></PolyStyle></Style>',
        '<Style id="short"><LineStyle><color>ff00ff44</color><width>2</width></LineStyle>'
        '<PolyStyle><color>6000ff44</color></PolyStyle></Style>',
        '<Style id="perch"><IconStyle><scale>1.5</scale>'
        '<Icon><href>http://maps.google.com/mapfiles/kml/paddle/blu-stars.png</href></Icon></IconStyle></Style>',
        '<Style id="launch"><IconStyle><scale>1.2</scale>'
        '<Icon><href>http://maps.google.com/mapfiles/kml/paddle/orange-circle.png</href></Icon></IconStyle></Style>',
        '<Style id="launch_perch"><IconStyle><scale>1.2</scale>'
        '<Icon><href>http://maps.google.com/mapfiles/kml/paddle/grn-circle.png</href></Icon></IconStyle></Style>',
        '<Style id="launch_short"><IconStyle><scale>1.3</scale>'
        '<Icon><href>http://maps.google.com/mapfiles/kml/paddle/red-circle.png</href></Icon></IconStyle></Style>',
    ])

    # Context
    holes_kml = ''
    for h in target_holes:
        holes_kml += f'<innerBoundaryIs><LinearRing><coordinates>{coords(h)}</coordinates></LinearRing></innerBoundaryIs>'
    out.append(f'<Placemark><name>Target corridor union (1622 ac)</name><styleUrl>#target</styleUrl>'
               f'<Polygon><outerBoundaryIs><LinearRing><coordinates>{coords(target_outer)}</coordinates></LinearRing></outerBoundaryIs>{holes_kml}</Polygon></Placemark>')
    out.append(f'<Placemark><name>Hwy 81</name><styleUrl>#hwy</styleUrl>'
               f'<LineString><coordinates>{coords(highway)}</coordinates></LineString></Placemark>')
    out.append(f'<Placemark><name>Hilger-Roy powerline</name><styleUrl>#wire</styleUrl>'
               f'<LineString><coordinates>{coords(powerline)}</coordinates></LineString></Placemark>')

    # Swaths
    out.append('<Folder><name>Mission swaths</name>')
    for fn in FINAL_PLANS:
        ll = swaths_ll.get(fn)
        if not ll: continue
        style = 'short' if fn.endswith('_short.plan') else 'full'
        out.append(f'<Placemark><name>{fn}</name><styleUrl>#{style}</styleUrl>'
                   f'<Polygon><outerBoundaryIs><LinearRing><coordinates>{coords(ll)}</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>')
    out.append('</Folder>')

    # Perches
    out.append('<Folder><name>Perches (BLUE stars) - RPIC drives here after takeoff</name>')
    for n in (4, 5, 6, 7, 9):
        r = perches.get(n)
        if not r or not r.get('perch'): continue
        p = r['perch']
        out.append(f'<Placemark><name>Perch pair {n} (Fergus{2*n+1}/{2*n+2})</name>'
                   f'<description>RPIC perch for hot-swap pair. '
                   f'{p["dist_from_launch_m"]:.0f} m ({p["dist_from_launch_m"]/1609.34:.2f} mi) from launch L{n}. '
                   f'Ground elev {p["ground_amsl_m"]:.0f} m AMSL ({p["elev_above_launch_m"]:+.0f} m vs launch).</description>'
                   f'<styleUrl>#perch</styleUrl>'
                   f'<Point><coordinates>{p["lon"]:.7f},{p["lat"]:.7f},0</coordinates></Point></Placemark>')
    out.append('</Folder>')

    # Launches (color-coded)
    out.append('<Folder><name>Launch / landing points</name>')
    for i, (la, lo) in enumerate(launches, start=1):
        if i in (1, 2, 3):
            style = 'launch'
            note = 'RPIC stays here - 100% VLOS from launch'
        elif i == 8:
            style = 'launch_short'
            note = 'NO PERCH within 1.5 mi - using SHORTENED tiles (Fergus17_short = 1200m east, Fergus18_short = 600m west)'
        else:
            style = 'launch_perch'
            note = 'RPIC drives to perch (see Blue star); VO stays here for landings + hot swaps'
        out.append(f'<Placemark><name>L{i} (pair {i})</name>'
                   f'<description>{note}</description>'
                   f'<styleUrl>#{style}</styleUrl>'
                   f'<Point><coordinates>{lo:.7f},{la:.7f},0</coordinates></Point></Placemark>')
    out.append('</Folder>')

    out.append('</Document></kml>')
    open(OUT_KML, 'w', encoding='utf-8').write('\n'.join(out))
    print(f'\nWrote KML: {OUT_KML}')


if __name__ == '__main__':
    main()
