"""Build an enriched KML visualizing which of 7 recommended launches covers each
sampled drone position in the 10 Fergus Hilger-Roy photogrammetry mission areas.

Sample each area polygon at 200 m grid + polygon vertices + edge midpoints.
For every sample point, find the NEAREST launch within 3 mi (4828 m) that has
100% bare-earth VLOS to (sample, terrain+AGL) from (launch, terrain+2 m).
Color-code the launch + its 3-mi circle + its assigned sample points.

Outputs to C:/Users/rharbach.STAHLY/Downloads/Fergus_photogrammetry_launches_enriched.kml
"""
import os
import sys
import math
import re
import xml.etree.ElementTree as ET

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

# Pre-load wider DEM cache BEFORE importing dem_lookup's lazy loader logic
WIDER_DEM_META = os.path.join(
    os.path.expanduser('~'), '.claude', 'dem_cache', 'dem_ee0aa3a8a9d0.json'
)
import dem_lookup  # noqa: E402
# Prepend wider DEM so it beats the small fergus_dem.tif skill bundle
dem_lookup._explicit_meta_paths.insert(0, WIDER_DEM_META)
from dem_lookup import terrain_amsl  # noqa: E402
from los_check import los_line_clear, OPERATOR_EYE_M  # noqa: E402
from shapely.geometry import Polygon, Point  # noqa: E402

DOWNLOAD = 'C:/Users/rharbach.STAHLY/Downloads'
OUT_KML = f'{DOWNLOAD}/Fergus_photogrammetry_launches_enriched.kml'

AGL = 40.0
RADIUS_MI = 3.0
RADIUS_M = RADIUS_MI * 1609.344  # 4828.032
SAMPLE_GRID_M = 200.0
LOS_LINE_SAMPLES = 50

# (lat, lon, ground_amsl_m, [areas served])
LAUNCHES = [
    (47.264746, -109.327031, 1323, [1, 2]),
    (47.332234, -109.068256, 1160, [5, 6, 7]),
    (47.332234, -108.942185, 1069, [7, 8, 9]),
    (47.305239, -109.207596, 1219, [3, 4, 5]),
    (47.336733, -108.836021, 1028, [9, 10]),
    (47.264746, -109.273949, 1401, [2, 3]),
    (47.327734, -109.141244, 1244, [5]),
]

# Distinct hues per launch (KML color is AABBGGRR hex)
# Pure colors picked for visual separability on Google Earth's sat imagery.
LAUNCH_COLORS = [
    # (label, line_AABBGGRR, fill_AABBGGRR for circle, icon_paddle_href)
    ('red',     'ff0000ff', '440000ff', 'http://maps.google.com/mapfiles/kml/paddle/red-stars.png'),
    ('blue',    'ffff0000', '44ff0000', 'http://maps.google.com/mapfiles/kml/paddle/blu-stars.png'),
    ('green',   'ff00aa00', '4400aa00', 'http://maps.google.com/mapfiles/kml/paddle/grn-stars.png'),
    ('yellow',  'ff00ffff', '4400ffff', 'http://maps.google.com/mapfiles/kml/paddle/ylw-stars.png'),
    ('magenta', 'ffff00ff', '44ff00ff', 'http://maps.google.com/mapfiles/kml/paddle/pink-stars.png'),
    ('cyan',    'ffffff00', '44ffff00', 'http://maps.google.com/mapfiles/kml/paddle/ltblu-stars.png'),
    ('orange',  'ff0080ff', '440080ff', 'http://maps.google.com/mapfiles/kml/paddle/orange-stars.png'),
]


def parse_polygon(path):
    with open(path, 'r', encoding='utf-8') as f:
        txt = f.read()
    m = re.search(
        r'<Polygon[\s\S]*?<outerBoundaryIs>[\s\S]*?<coordinates>([\s\S]+?)</coordinates>',
        txt,
    )
    if not m:
        raise ValueError(f'no polygon in {path}')
    pts = []
    for tok in m.group(1).strip().split():
        lon, lat = tok.split(',')[:2]
        pts.append((float(lat), float(lon)))
    if pts and pts[0] == pts[-1]:
        pts = pts[:-1]
    return pts


def make_projection(ref_lat, ref_lon):
    mlat = 111132.0
    mlon = 111132.0 * math.cos(math.radians(ref_lat))

    def to_xy(lat, lon):
        return ((lon - ref_lon) * mlon, (lat - ref_lat) * mlat)

    def to_ll(x, y):
        return (ref_lat + y / mlat, ref_lon + x / mlon)

    return to_xy, to_ll


def sample_polygon(poly_xy, grid_m):
    """Yield (x,y) sample positions: vertices + edge midpoints + interior grid."""
    seen = set()

    def emit(p):
        key = (round(p[0], 1), round(p[1], 1))
        if key in seen:
            return
        seen.add(key)
        return True

    coords = list(poly_xy.exterior.coords)
    # vertices (skip duplicate closing vertex)
    for x, y in coords[:-1] if coords[0] == coords[-1] else coords:
        if emit((x, y)):
            yield (x, y)
    # edge midpoints
    for i in range(len(coords) - 1):
        a, b = coords[i], coords[i + 1]
        mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        if emit((mx, my)):
            yield (mx, my)
    # interior grid
    minx, miny, maxx, maxy = poly_xy.bounds
    x = minx + grid_m / 2
    while x < maxx:
        y = miny + grid_m / 2
        while y < maxy:
            if poly_xy.contains(Point(x, y)):
                if emit((x, y)):
                    yield (x, y)
            y += grid_m
        x += grid_m


def circle_polygon_ll(lat, lon, radius_m, segments=32):
    """Approximate a geodetic circle as a 32-gon. Returns list of (lat,lon)."""
    mlat = 111132.0
    mlon = 111132.0 * math.cos(math.radians(lat))
    pts = []
    for i in range(segments + 1):
        a = 2 * math.pi * i / segments
        dx = radius_m * math.cos(a)
        dy = radius_m * math.sin(a)
        pts.append((lat + dy / mlat, lon + dx / mlon))
    return pts


def main():
    print('=== Building enriched per-launch coverage KML ===')
    print(f'AGL: {AGL} m, radius: {RADIUS_M:.0f} m ({RADIUS_MI} mi)')
    print(f'Operator eye: ground + {OPERATOR_EYE_M} m')

    # --- 1. Load polygons ---
    polys_ll = []
    for n in range(1, 11):
        path = f'{DOWNLOAD}/Fergus Hilger-Roy — area {n}.kml'
        polys_ll.append((n, parse_polygon(path)))
    print(f'Loaded {len(polys_ll)} area polygons')

    # --- 2. Local projection ---
    all_lats = [p[0] for _, poly in polys_ll for p in poly]
    all_lons = [p[1] for _, poly in polys_ll for p in poly]
    ref_lat = sum(all_lats) / len(all_lats)
    ref_lon = sum(all_lons) / len(all_lons)
    to_xy, to_ll = make_projection(ref_lat, ref_lon)

    polys_xy = []
    for n, poly_ll in polys_ll:
        poly_xy = Polygon([to_xy(lat, lon) for lat, lon in poly_ll])
        polys_xy.append((n, poly_xy))

    # --- 3. Sample each polygon at 200 m grid + vertices + edges ---
    area_pts = []  # list of dicts
    for n, poly_xy in polys_xy:
        ct = 0
        for x, y in sample_polygon(poly_xy, SAMPLE_GRID_M):
            lat, lon = to_ll(x, y)
            ground = terrain_amsl(lat, lon)
            area_pts.append({
                'x': x, 'y': y, 'lat': lat, 'lon': lon,
                'ground': ground, 'drone_amsl': ground + AGL,
                'area': n,
            })
            ct += 1
        print(f'  area {n}: {ct} sample points')
    print(f'Total sample points: {len(area_pts)}')

    # --- 4. Project launches ---
    launches = []
    for i, (lat, lon, ground_known, areas) in enumerate(LAUNCHES, start=1):
        x, y = to_xy(lat, lon)
        ground = terrain_amsl(lat, lon)
        launches.append({
            'idx': i,
            'lat': lat, 'lon': lon,
            'x': x, 'y': y,
            'ground': ground,
            'op_amsl': ground + OPERATOR_EYE_M,
            'areas': areas,
        })

    # --- 5. Assign each sample point to nearest VLOS-clear launch within 3 mi ---
    assignments = [None] * len(area_pts)  # launch idx (1..7) or None
    vlos_cache = {}  # (pt_idx, lnch_idx) -> bool

    for pi, pt in enumerate(area_pts):
        # Rank launches by euclidean distance
        ranked = []
        for L in launches:
            dx = pt['x'] - L['x']
            dy = pt['y'] - L['y']
            d = math.hypot(dx, dy)
            if d <= RADIUS_M:
                ranked.append((d, L))
        ranked.sort(key=lambda t: t[0])
        # Pick the closest VLOS-clear one
        for d, L in ranked:
            key = (pi, L['idx'])
            if key in vlos_cache:
                clear = vlos_cache[key]
            else:
                clear, _, _ = los_line_clear(
                    (L['lat'], L['lon']), L['op_amsl'],
                    (pt['lat'], pt['lon']), pt['drone_amsl'],
                    samples=LOS_LINE_SAMPLES,
                )
                vlos_cache[key] = clear
            if clear:
                assignments[pi] = L['idx']
                break
        if pi % 200 == 0 and pi > 0:
            print(f'  assigned {pi}/{len(area_pts)} ...')

    # --- 6. Bucket points by launch / uncovered ---
    buckets = {L['idx']: [] for L in launches}
    uncovered = []
    for pi, pt in enumerate(area_pts):
        a = assignments[pi]
        if a is None:
            uncovered.append(pt)
        else:
            buckets[a].append(pt)

    # --- 7. Print summary table ---
    print()
    print('Launch assignment summary')
    print('-' * 60)
    print(f'{"Launch":<8}{"Areas served":<22}{"#points assigned"}')
    print('-' * 60)
    points_per_launch = []
    for L in launches:
        n_pts = len(buckets[L['idx']])
        points_per_launch.append(n_pts)
        print(f'  {L["idx"]:<6}{str(L["areas"]):<22}{n_pts}')
    print('-' * 60)
    print(f'  Uncovered: {len(uncovered)}')
    print(f'  Total assigned: {sum(points_per_launch)}')

    # --- 8. Build KML ---
    lines = []
    lines.append('<?xml version="1.0" encoding="UTF-8"?>')
    lines.append('<kml xmlns="http://www.opengis.net/kml/2.2">')
    lines.append('<Document>')
    lines.append('<name>Fergus photogrammetry launches - per-point coverage</name>')
    desc = (
        f'<![CDATA[Per-point coverage assignment for the 7-launch set cover '
        f'over 10 Fergus Hilger-Roy photogrammetry areas. Each sampled drone '
        f'position (200 m grid + vertices + edge midpoints) at terrain + '
        f'{AGL:.0f} m AGL is assigned to its nearest launch within '
        f'{RADIUS_MI:.1f} mi ({RADIUS_M:.0f} m) that has 100% bare-earth VLOS '
        f'from operator eye at ground + {OPERATOR_EYE_M:.0f} m. '
        f'<b>{sum(points_per_launch)}/{len(area_pts)} points assigned, '
        f'{len(uncovered)} uncovered.</b>]]>'
    )
    lines.append(f'<description>{desc}</description>')

    # Styles: area polygon style + uncovered + per-launch (star + circle + dot)
    lines.append(
        '<Style id="area"><LineStyle><color>ff00ffff</color><width>2</width>'
        '</LineStyle><PolyStyle><color>3300ffff</color></PolyStyle></Style>'
    )
    lines.append(
        '<Style id="uncov"><IconStyle><color>ff0000ff</color><scale>0.7</scale>'
        '<Icon><href>http://maps.google.com/mapfiles/kml/shapes/cross-hairs.png'
        '</href></Icon></IconStyle><LabelStyle><scale>0</scale></LabelStyle></Style>'
    )
    for i, L in enumerate(launches):
        name, line_c, fill_c, paddle = LAUNCH_COLORS[i]
        # Launch star
        lines.append(
            f'<Style id="launch{L["idx"]}"><IconStyle><color>{line_c}</color>'
            f'<scale>1.4</scale><Icon><href>{paddle}</href></Icon></IconStyle>'
            f'<LabelStyle><color>{line_c}</color><scale>1.0</scale></LabelStyle></Style>'
        )
        # 3-mi circle (translucent fill, opaque outline)
        lines.append(
            f'<Style id="circle{L["idx"]}"><LineStyle><color>{line_c}</color>'
            f'<width>2</width></LineStyle><PolyStyle><color>{fill_c}</color>'
            f'</PolyStyle></Style>'
        )
        # Small dot for assigned sample points (no label)
        lines.append(
            f'<Style id="pt{L["idx"]}"><IconStyle><color>{line_c}</color>'
            f'<scale>0.4</scale><Icon>'
            f'<href>http://maps.google.com/mapfiles/kml/shapes/placemark_circle.png'
            f'</href></Icon></IconStyle><LabelStyle><scale>0</scale></LabelStyle></Style>'
        )

    # --- Area polygons folder ---
    lines.append('<Folder><name>Mission area polygons</name>')
    for n, poly_ll in polys_ll:
        coords = ' '.join(f'{lon:.7f},{lat:.7f},0' for lat, lon in poly_ll)
        # close ring
        first_lat, first_lon = poly_ll[0]
        coords += f' {first_lon:.7f},{first_lat:.7f},0'
        lines.append('<Placemark>')
        lines.append(f'<name>Area {n}</name>')
        lines.append('<styleUrl>#area</styleUrl>')
        lines.append(
            '<Polygon><outerBoundaryIs><LinearRing><coordinates>'
            + coords +
            '</coordinates></LinearRing></outerBoundaryIs></Polygon>'
        )
        lines.append('</Placemark>')
    lines.append('</Folder>')

    # --- One folder per launch ---
    for i, L in enumerate(launches):
        name, line_c, fill_c, paddle = LAUNCH_COLORS[i]
        n_pts = len(buckets[L['idx']])
        folder_name = (
            f'Launch {L["idx"]} ({name}) — serves areas {L["areas"]} '
            f'— {n_pts} pts'
        )
        lines.append(f'<Folder><name>{folder_name}</name>')

        # Launch placemark
        launch_desc = (
            f'<![CDATA[<b>Launch {L["idx"]}</b><br/>'
            f'Lat: {L["lat"]:.6f}<br/>Lon: {L["lon"]:.6f}<br/>'
            f'Ground elev: {L["ground"]:.0f} m AMSL<br/>'
            f'Operator eye: {L["op_amsl"]:.0f} m AMSL<br/>'
            f'Serves areas: {L["areas"]}<br/>'
            f'Assigned points: {n_pts}]]>'
        )
        lines.append('<Placemark>')
        lines.append(f'<name>Launch {L["idx"]}</name>')
        lines.append(f'<description>{launch_desc}</description>')
        lines.append(f'<styleUrl>#launch{L["idx"]}</styleUrl>')
        lines.append(f'<Point><coordinates>{L["lon"]:.7f},{L["lat"]:.7f},0</coordinates></Point>')
        lines.append('</Placemark>')

        # 3-mi circle (32-gon)
        ring_pts = circle_polygon_ll(L['lat'], L['lon'], RADIUS_M, segments=32)
        circ_coords = ' '.join(f'{lon:.7f},{lat:.7f},0' for lat, lon in ring_pts)
        lines.append('<Placemark>')
        lines.append(f'<name>Launch {L["idx"]} 3-mi radius</name>')
        lines.append(f'<styleUrl>#circle{L["idx"]}</styleUrl>')
        lines.append(
            '<Polygon><outerBoundaryIs><LinearRing><coordinates>'
            + circ_coords +
            '</coordinates></LinearRing></outerBoundaryIs></Polygon>'
        )
        lines.append('</Placemark>')

        # Assigned sample points subfolder
        lines.append(f'<Folder><name>Assigned points ({n_pts})</name>')
        for pt in buckets[L['idx']]:
            lines.append('<Placemark>')
            lines.append(f'<name>A{pt["area"]}</name>')
            lines.append(f'<styleUrl>#pt{L["idx"]}</styleUrl>')
            lines.append(
                f'<Point><coordinates>{pt["lon"]:.7f},{pt["lat"]:.7f},0</coordinates></Point>'
            )
            lines.append('</Placemark>')
        lines.append('</Folder>')

        lines.append('</Folder>')

    # --- Uncovered folder ---
    if uncovered:
        lines.append(f'<Folder><name>Uncovered points ({len(uncovered)})</name>')
        for pt in uncovered:
            lines.append('<Placemark>')
            lines.append(f'<name>A{pt["area"]} uncov</name>')
            lines.append('<styleUrl>#uncov</styleUrl>')
            lines.append(
                f'<Point><coordinates>{pt["lon"]:.7f},{pt["lat"]:.7f},0</coordinates></Point>'
            )
            lines.append('</Placemark>')
        lines.append('</Folder>')

    lines.append('</Document>')
    lines.append('</kml>')

    # --- Write file (binary, UTF-8, LF only, no BOM) ---
    blob = '\n'.join(lines).encode('utf-8')
    with open(OUT_KML, 'wb') as f:
        f.write(blob)
    file_bytes = len(blob)

    # --- Validate XML ---
    try:
        ET.parse(OUT_KML)
        xml_ok = True
    except Exception as e:
        xml_ok = False
        print(f'XML PARSE ERROR: {e}')

    print()
    print(f'Wrote {OUT_KML}')
    print(f'  size: {file_bytes} bytes')
    print(f'  XML valid: {xml_ok}')

    return {
        'out_path': OUT_KML,
        'launches': len(launches),
        'area_polygons': len(polys_ll),
        'assigned_points_total': sum(points_per_launch),
        'points_per_launch': points_per_launch,
        'xml_self_check_valid': xml_ok,
        'file_bytes': file_bytes,
        'uncovered': len(uncovered),
        'total_samples': len(area_pts),
    }


if __name__ == '__main__':
    result = main()
    print()
    print('RESULT:', result)
