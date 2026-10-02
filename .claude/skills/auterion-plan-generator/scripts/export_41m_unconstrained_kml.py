"""Export the 18 unconstrained 41m highway-centerline plans as a KML for visual review."""
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
from los_check import extract_flight_path, interpolate_path
from coverage_check_multi import make_projection, parse_plan_geometry, parse_kml_polygon

PLAN_DIR = 'C:/Users/rharbach.STAHLY/Documents/Auterion Mission Control/Missions'
KML_HIGHWAY    = 'C:/Users/rharbach.STAHLY/Downloads/HighwayCenterline.kml'
KML_POWERLINE  = 'C:/Users/rharbach.STAHLY/Downloads/Hilger-Roy existing line — joined.kml'
TARGET_KML     = 'C:/Users/rharbach.STAHLY/Downloads/Fergus Hilger-Roy — corridor union.kml'
OUT_KML        = 'C:/Users/rharbach.STAHLY/Downloads/Fergus_41m_highway_centerline_unconstrained.kml'

PLANS = [f'Fergus{n}.plan' for n in range(3, 21)]
AGL = 41.0
TURNAROUND_M = 60.96
HALF_LS_M = 20.5

# 18-color palette (KML uses aabbggrr; here we use ffXXYYZZ where XXYYZZ is BGR hex)
PALETTE = [
    'ff00aaff', 'ffff00aa', 'ff00ffaa', 'ffaaff00',
    'ffff5500', 'ff5500ff', 'ff00ff55', 'ffff00ff',
    'ff00ffff', 'ffff5555', 'ff5555ff', 'ff55ff55',
    'ffaa55aa', 'ff55aaaa', 'ffaaaa55', 'ffaa00aa',
    'ff00aa00', 'ffaaaaaa',
]
PLAN_COLORS = {fn: PALETTE[i] for i, fn in enumerate(PLANS)}


def load_linestring(path):
    txt = open(path, 'r', encoding='utf-8').read()
    m = re.search(r'<LineString[\s\S]*?<coordinates>([\s\S]+?)</coordinates>', txt)
    return [tuple(map(float, t.split(',')[:2][::-1])) for t in m.group(1).strip().split()]


def kml_coords_from_latlon_list(latlons):
    return ' '.join(f'{lon:.7f},{lat:.7f},0' for (lat, lon) in latlons)


def make_back_projection(ref_lat, ref_lon):
    m_lat = 111132.0
    m_lon = 111132.0 * math.cos(math.radians(ref_lat))
    def from_xy(x_m, y_m):
        return (ref_lat + y_m / m_lat, ref_lon + x_m / m_lon)
    return from_xy


def perp_offset(polyline_ll, offset_m, ref_lat):
    m_lat = 111132.0
    m_lon = 111132.0 * math.cos(math.radians(ref_lat))
    out = []
    for i, (la, lo) in enumerate(polyline_ll):
        if i == 0:
            dx = (polyline_ll[1][1] - lo) * m_lon
            dy = (polyline_ll[1][0] - la) * m_lat
        elif i == len(polyline_ll) - 1:
            dx = (lo - polyline_ll[i-1][1]) * m_lon
            dy = (la - polyline_ll[i-1][0]) * m_lat
        else:
            dx = (polyline_ll[i+1][1] - polyline_ll[i-1][1]) * m_lon
            dy = (polyline_ll[i+1][0] - polyline_ll[i-1][0]) * m_lat
        L = math.hypot(dx, dy)
        if L < 0.01:
            out.append((la, lo)); continue
        px = -dy / L; py = dx / L
        new_lat = la + (offset_m * py) / m_lat
        new_lon = lo + (offset_m * px) / m_lon
        out.append((new_lat, new_lon))
    return out


def main():
    plan_geoms = {}
    flight_paths = {}
    for fn in PLANS:
        p = os.path.join(PLAN_DIR, fn)
        kind, geom, agl, cw, ta = parse_plan_geometry(p)
        plan_geoms[fn] = geom
        plan = json.load(open(p))
        fp = extract_flight_path(plan)
        fp_interp = interpolate_path(fp, 5.0)
        flight_paths[fn] = [(la, lo) for (la, lo, _) in fp_interp]

    all_pts = []
    for fn, geom in plan_geoms.items():
        all_pts.extend(geom)
    ref_lat = sum(p[0] for p in all_pts) / len(all_pts)
    ref_lon = sum(p[1] for p in all_pts) / len(all_pts)
    to_xy, _ = make_projection(ref_lat, ref_lon)
    from_xy = make_back_projection(ref_lat, ref_lon)

    highway = load_linestring(KML_HIGHWAY)
    powerline = load_linestring(KML_POWERLINE)
    target_outer, target_holes = parse_kml_polygon(TARGET_KML)[0]

    swaths_ll = {}
    inner_transects_ll = {}
    for fn, geom in plan_geoms.items():
        xy = [to_xy(*p) for p in geom]
        def extend_pt(p_end, p_prev, dist):
            dx = p_end[0] - p_prev[0]; dy = p_end[1] - p_prev[1]
            L = math.hypot(dx, dy)
            if L == 0: return p_end
            return (p_end[0] + dist*dx/L, p_end[1] + dist*dy/L)
        ext = [extend_pt(xy[0], xy[1], TURNAROUND_M)] + xy[1:-1] + [extend_pt(xy[-1], xy[-2], TURNAROUND_M)]
        if len(xy) == 2:
            ext = [extend_pt(xy[0], xy[1], TURNAROUND_M), extend_pt(xy[-1], xy[-2], TURNAROUND_M)]
        line = LineString(ext)
        sw = line.buffer(AGL + AGL/2, cap_style='flat', join_style='round')
        if sw.geom_type == 'Polygon':
            ext_ll = [from_xy(x, y) for (x, y) in sw.exterior.coords]
        else:
            ext_ll = [from_xy(x, y) for (x, y) in list(sw.geoms)[0].exterior.coords]
        swaths_ll[fn] = ext_ll

        right = perp_offset(geom, +HALF_LS_M, ref_lat)
        left  = perp_offset(geom, -HALF_LS_M, ref_lat)
        inner_transects_ll[fn] = (left, right)

    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<kml xmlns="http://www.opengis.net/kml/2.2">',
           '<Document>',
           '<name>Fergus 41m Highway-Centerline Unconstrained (18 plans)</name>',
           '<description>18 plans at 41m AGL/14m/s/3.6km tile/polyline=highway. '
           'Wire-clearance NOT enforced. ~74% target-area coverage, ~194 min total flight time.</description>']

    for fn, clr in PLAN_COLORS.items():
        out.extend([
            f'<Style id="path_{fn}"><LineStyle><color>{clr}</color><width>3</width></LineStyle></Style>',
            f'<Style id="swath_{fn}"><LineStyle><color>{clr}</color><width>1</width></LineStyle>'
            f'<PolyStyle><color>40{clr[2:]}</color></PolyStyle></Style>',
            f'<Style id="poly_{fn}"><LineStyle><color>{clr}</color><width>2</width></LineStyle></Style>',
            f'<Style id="tran_{fn}"><LineStyle><color>80{clr[2:]}</color><width>1</width></LineStyle></Style>',
        ])
    out.extend([
        '<Style id="hwy"><LineStyle><color>ff00ffff</color><width>2</width></LineStyle></Style>',
        '<Style id="wire"><LineStyle><color>ff0000ff</color><width>3</width></LineStyle></Style>',
        '<Style id="target"><LineStyle><color>ff00ff00</color><width>2</width></LineStyle>'
        '<PolyStyle><color>2000ff00</color></PolyStyle></Style>',
        '<Style id="launch"><IconStyle><scale>1.2</scale>'
        '<Icon><href>http://maps.google.com/mapfiles/kml/paddle/grn-stars.png</href></Icon></IconStyle></Style>',
        '<Style id="meet"><IconStyle><scale>1.0</scale>'
        '<Icon><href>http://maps.google.com/mapfiles/kml/paddle/wht-circle.png</href></Icon></IconStyle></Style>',
    ])

    out.append('<Folder><name>Target corridor union (1621 ac)</name>')
    holes_kml = ''
    for h in target_holes:
        holes_kml += f'<innerBoundaryIs><LinearRing><coordinates>{kml_coords_from_latlon_list(h)}</coordinates></LinearRing></innerBoundaryIs>'
    out.append(f'<Placemark><name>Target (1621 ac)</name><styleUrl>#target</styleUrl>'
               f'<Polygon><outerBoundaryIs><LinearRing><coordinates>{kml_coords_from_latlon_list(target_outer)}</coordinates></LinearRing></outerBoundaryIs>{holes_kml}</Polygon></Placemark>')
    out.append('</Folder>')

    out.append('<Folder><name>Highway centerline</name>')
    out.append(f'<Placemark><name>Hwy 81</name><styleUrl>#hwy</styleUrl>'
               f'<LineString><coordinates>{kml_coords_from_latlon_list(highway)}</coordinates></LineString></Placemark>')
    out.append('</Folder>')

    out.append('<Folder><name>Powerline</name>')
    out.append(f'<Placemark><name>Hilger-Roy (28.15 mi)</name><styleUrl>#wire</styleUrl>'
               f'<LineString><coordinates>{kml_coords_from_latlon_list(powerline)}</coordinates></LineString></Placemark>')
    out.append('</Folder>')

    out.append('<Folder><name>Plan swaths (123 m wide, translucent)</name>')
    for fn in PLANS:
        out.append(f'<Placemark><name>{fn} swath</name><styleUrl>#swath_{fn}</styleUrl>'
                   f'<Polygon><outerBoundaryIs><LinearRing><coordinates>{kml_coords_from_latlon_list(swaths_ll[fn])}</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>')
    out.append('</Folder>')

    out.append('<Folder><name>Plan polylines</name>')
    for fn in PLANS:
        out.append(f'<Placemark><name>{fn}</name><styleUrl>#poly_{fn}</styleUrl>'
                   f'<LineString><coordinates>{kml_coords_from_latlon_list(plan_geoms[fn])}</coordinates></LineString></Placemark>')
    out.append('</Folder>')

    out.append('<Folder><name>Inner transects (+/-20.5 m)</name>')
    for fn in PLANS:
        left, right = inner_transects_ll[fn]
        out.append(f'<Placemark><name>{fn} L</name><styleUrl>#tran_{fn}</styleUrl>'
                   f'<LineString><coordinates>{kml_coords_from_latlon_list(left)}</coordinates></LineString></Placemark>')
        out.append(f'<Placemark><name>{fn} R</name><styleUrl>#tran_{fn}</styleUrl>'
                   f'<LineString><coordinates>{kml_coords_from_latlon_list(right)}</coordinates></LineString></Placemark>')
    out.append('</Folder>')

    out.append('<Folder><name>Flight paths</name>')
    for fn in PLANS:
        out.append(f'<Placemark><name>{fn}</name><styleUrl>#path_{fn}</styleUrl>'
                   f'<LineString><coordinates>{kml_coords_from_latlon_list(flight_paths[fn])}</coordinates></LineString></Placemark>')
    out.append('</Folder>')

    out.append('<Folder><name>Launches + meeting points</name>')
    for fn in PLANS:
        plan = json.load(open(os.path.join(PLAN_DIR, fn)))
        home = plan['mission']['plannedHomePosition']
        out.append(f'<Placemark><name>{fn} launch</name><styleUrl>#launch</styleUrl>'
                   f'<Point><coordinates>{home[1]:.7f},{home[0]:.7f},0</coordinates></Point></Placemark>')
        meet = plan_geoms[fn][-1]
        out.append(f'<Placemark><name>{fn} meeting</name><styleUrl>#meet</styleUrl>'
                   f'<Point><coordinates>{meet[1]:.7f},{meet[0]:.7f},0</coordinates></Point></Placemark>')
    out.append('</Folder>')

    out.append('</Document></kml>')
    open(OUT_KML, 'w', encoding='utf-8').write('\n'.join(out))
    print(f'Wrote KML: {OUT_KML}')
    print(f'Size: {os.path.getsize(OUT_KML)} bytes')


if __name__ == '__main__':
    main()
