"""Parse perch placemarks from Ryan's RBH KML, verify they are at local DEM maxima
along the highway centerline, and save as a proper JSON for downstream use.
"""
import os, sys, re, math, json
SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SKILL_DIR, 'scripts'))

import dem_lookup
_explicit = os.path.expanduser('~/.claude/dem_cache/dem_ee0aa3a8a9d0.json')
if os.path.exists(_explicit):
    dem_lookup._explicit_meta_paths.insert(0, _explicit)
    dem_lookup._local_dem = None
    dem_lookup._local_meta = None

from dem_lookup import terrain_amsl
from shapely.geometry import Point, LineString
from coverage_check_multi import make_projection

RBH_KML = 'C:/Users/rharbach.STAHLY/Downloads/Fergus 50m11.5m simple layout (no jut-out)_RBH.kml'
HIGHWAY_KML = 'C:/Users/rharbach.STAHLY/Downloads/HighwayCenterline.kml'
OUT_JSON = 'C:/Users/rharbach.STAHLY/Downloads/Fergus_perches.json'

# B points from the layout JSON (known positions)
B_POINTS = {   # session index -> (lat, lon)
    1: (47.2598714, -109.3079366),
    2: (47.2742569, -109.2529805),
    3: (47.2992348, -109.2067982),
    4: (47.3162552, -109.1520484),
    5: (47.3279411, -109.0954950),
    6: (47.3364367, -109.0380549),
    7: (47.3360283, -108.9778331),
    8: (47.3332258, -108.9189678),
    9: (47.3501488, -108.8641817),
    10: (47.3503599, -108.8040065),
}


def load_linestring(path):
    txt = open(path, 'r', encoding='utf-8').read()
    m = re.search(r'<LineString[\s\S]*?<coordinates>([\s\S]+?)</coordinates>', txt)
    return [tuple(map(float, t.split(',')[:2][::-1])) for t in m.group(1).strip().split()]


def parse_perches_from_kml(path):
    """Extract perch lat/lon from the <Point><coordinates> element inside Placemarks
    named 'Perch'. Each Perch placemark also has a <Camera> or <LookAt> with the
    VIEWING angle Ryan was at when he placed the marker — that is NOT the marker's
    anchor coordinate. Use <Point> instead.
    """
    txt = open(path, 'r', encoding='utf-8').read()
    perches = []
    # Find each Placemark with <name>Perch</name>, then its <Point>/<coordinates>
    pattern = re.compile(
        r'<Placemark>\s*<name>Perch</name>.*?'
        r'<Point>.*?<coordinates>\s*([-\d.,]+?)\s*</coordinates>',
        re.DOTALL
    )
    for m in pattern.finditer(txt):
        parts = m.group(1).split(',')
        lon = float(parts[0]); lat = float(parts[1])
        perches.append((lat, lon))
    return perches


def main():
    highway = load_linestring(HIGHWAY_KML)
    perches = parse_perches_from_kml(RBH_KML)
    print(f'Found {len(perches)} perch placemarks in user KML')

    # Set up local projection
    ref_lat = sum(p[0] for p in highway) / len(highway)
    ref_lon = sum(p[1] for p in highway) / len(highway)
    m_lat = 111132.0
    m_lon = 111132.0 * math.cos(math.radians(ref_lat))
    def to_xy(lat, lon): return ((lon - ref_lon) * m_lon, (lat - ref_lat) * m_lat)
    def from_xy(x, y): return (ref_lat + y/m_lat, ref_lon + x/m_lon)

    hwy_xy = [to_xy(*p) for p in highway]
    hwy_line = LineString(hwy_xy)

    print(f'\n{"#":<4}{"Perch lat,lon":<28}{"On road?":<10}{"To road (m)":<13}'
          f'{"To B (m)":<11}{"Elev (m)":<10}{"+/- nearby road"}')

    perch_records = []
    for i, (lat, lon) in enumerate(perches, start=1):
        perch_xy = to_xy(lat, lon)
        # Distance from perch to road
        d_road = Point(perch_xy).distance(hwy_line)
        # Project onto road
        proj_d = hwy_line.project(Point(perch_xy))
        on_road = d_road < 50
        # Distance to corresponding B
        if i in B_POINTS:
            b_lat, b_lon = B_POINTS[i]
            b_xy = to_xy(b_lat, b_lon)
            d_to_b = math.hypot(perch_xy[0] - b_xy[0], perch_xy[1] - b_xy[1])
            b_along = hwy_line.project(Point(b_xy))
        else:
            d_to_b = float('nan'); b_along = None

        # DEM at perch
        try:
            perch_elev = terrain_amsl(lat, lon)
        except Exception:
            perch_elev = float('nan')

        # DEM along road in +/- 500m around the perch's projection
        # to verify it's a local max
        nearby_elevs = []
        for d in range(int(proj_d - 500), int(proj_d + 500), 50):
            if d < 0 or d > hwy_line.length: continue
            pt = hwy_line.interpolate(d)
            elat, elon = from_xy(pt.x, pt.y)
            try:
                e = terrain_amsl(elat, elon)
                nearby_elevs.append(e)
            except Exception:
                pass
        if nearby_elevs:
            mean_e = sum(nearby_elevs) / len(nearby_elevs)
            max_e = max(nearby_elevs)
            delta_vs_mean = perch_elev - mean_e
            delta_vs_max = perch_elev - max_e
            cmp_str = f'+{delta_vs_mean:.0f}m mean, {delta_vs_max:+.0f}m max'
        else:
            cmp_str = '(no nearby road data)'

        print(f'{i:<4}({lat:.5f},{lon:.5f}) {"YES" if on_road else "no":<10}'
              f'{d_road:<13.0f}{d_to_b:<11.0f}{perch_elev:<10.0f}{cmp_str}')

        perch_records.append({
            'session': i,
            'perch_lat': lat, 'perch_lon': lon,
            'dist_to_road_m': d_road,
            'dist_to_b_m': d_to_b,
            'perch_elev_m': perch_elev,
            'b_lat': B_POINTS.get(i, (None, None))[0],
            'b_lon': B_POINTS.get(i, (None, None))[1],
        })

    json.dump(perch_records, open(OUT_JSON, 'w'), indent=2)
    print(f'\nSaved {len(perch_records)} perch records: {OUT_JSON}')


if __name__ == '__main__':
    main()
