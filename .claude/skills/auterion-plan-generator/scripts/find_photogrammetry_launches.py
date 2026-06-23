"""Minimum-launch set-cover for photogrammetry missions with a 3-mi
operator-to-drone radius (Part 107.33 with Visual Observer = 2-person crew).

Problem statement (per Ryan):
  - Drone must remain within 3 mi (4828.03 m) of its operator at all times.
  - Operator must maintain 100% VLOS to drone (bare-earth terrain check).
  - 10 mission area polygons must be fully covered.
  - Find the MINIMUM number of launch points satisfying both constraints.

Algorithm (greedy set-cover, log(n) approximation to optimal):
  1. Sample all 10 polygons into a single point set (polygon vertices + interior
     grid at 300m + edge midpoints).  Each sample = a drone position at
     terrain_amsl + AGL.
  2. Generate candidate launch positions on a 500m grid over a 1.5km-buffered
     union of the polygons.
  3. For each candidate, compute its coverage set = area points that are
     (a) within 3 mi euclidean AND (b) bare-earth VLOS clear.
  4. Greedy: at each step pick the candidate covering the most still-uncovered
     points; remove from universe; repeat until universe is empty (or no
     candidate covers anything new).
"""
import os, sys, math, re, json, time

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SKILL_DIR, 'scripts'))
import dem_lookup
# Force the wider corridor DEM (dem_ee0aa3a8a9d0 covers 47.227-47.379 / -109.387 to -108.784);
# the skill-bundled fergus_dem.tif (47.24-47.36 / -109.38 to -108.8) doesn't cover the SW
# corner candidates this script samples. Pitfall #15.
_explicit = os.path.expanduser('~/.claude/dem_cache/dem_ee0aa3a8a9d0.json')
if os.path.exists(_explicit):
    dem_lookup._explicit_meta_paths.insert(0, _explicit)
    dem_lookup._local_dem = None
    dem_lookup._local_meta = None
from dem_lookup import terrain_amsl
from los_check import los_line_clear, OPERATOR_EYE_M
from coverage_check_multi import make_projection
from generate_fergus_pair1 import load_centerline
from shapely.geometry import Polygon, Point, LineString
from shapely.ops import unary_union

DOWNLOAD = 'C:/Users/rharbach.STAHLY/Downloads'
OUT_KML  = f'{DOWNLOAD}/Fergus_photogrammetry_launches_400ft_centerline.kml'
CENTERLINE_KML = f'{DOWNLOAD}/HighwayCenterline.kml'

AGL                  = 121.92   # 400 ft AGL — Ryan's photogrammetry flight altitude (NOT the 40 m skill default)
RADIUS_MI            = 3.0
RADIUS_M             = RADIUS_MI * 1609.344
AREA_SAMPLE_GRID_M   = 300.0
CANDIDATE_GRID_M     = 200.0    # finer grid since centerline-60m strip is narrow
CANDIDATE_BUFFER_M   = 1500.0
LOS_LINE_SAMPLES     = 50
EARLY_STOP_DELTA     = 1        # stop greedy if best new coverage < this many points

# Launch must be within 60 m perpendicular distance of the highway centerline.
# Operators can stand on the highway shoulder / immediate roadside but not on private
# rangeland without coordination. See feedback-photogrammetry-3mi-radius-2person.
CENTERLINE_MAX_M     = 60.0


def parse_polygon(path):
    with open(path, 'r', encoding='utf-8') as f: txt = f.read()
    m = re.search(r'<Polygon[\s\S]*?<outerBoundaryIs>[\s\S]*?<coordinates>([\s\S]+?)</coordinates>', txt)
    if not m: raise ValueError(f'no polygon in {path}')
    pts = []
    for tok in m.group(1).strip().split():
        lon, lat = tok.split(',')[:2]
        pts.append((float(lat), float(lon)))
    if pts and pts[0] == pts[-1]: pts = pts[:-1]
    return pts


def sample_polygon(poly_xy, grid_m):
    """Yield (x,y) sample positions: polygon vertices + edge midpoints + interior grid."""
    yield from ((x, y) for x, y in poly_xy.exterior.coords)
    coords = list(poly_xy.exterior.coords)
    for i in range(len(coords) - 1):
        a, b = coords[i], coords[i + 1]
        yield ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    minx, miny, maxx, maxy = poly_xy.bounds
    x = minx + grid_m / 2
    while x < maxx:
        y = miny + grid_m / 2
        while y < maxy:
            if poly_xy.contains(Point(x, y)):
                yield (x, y)
            y += grid_m
        x += grid_m


def candidates_around(geom, grid_m, buffer_m):
    """Grid candidate launches inside the buffered union."""
    big = geom.buffer(buffer_m)
    minx, miny, maxx, maxy = big.bounds
    pts = []
    x = minx
    while x <= maxx:
        y = miny
        while y <= maxy:
            if big.contains(Point(x, y)):
                pts.append((x, y))
            y += grid_m
        x += grid_m
    return pts


def main():
    t0 = time.time()
    # Load all 10 polygons
    polys_ll = []
    for n in range(1, 11):
        path = f'{DOWNLOAD}/Fergus Hilger-Roy — area {n}.kml'
        polys_ll.append((n, parse_polygon(path)))

    # Local equirect projection anchored at the centroid of all polygon vertices
    all_lats = [p[0] for _, poly in polys_ll for p in poly]
    all_lons = [p[1] for _, poly in polys_ll for p in poly]
    ref_lat = sum(all_lats) / len(all_lats)
    ref_lon = sum(all_lons) / len(all_lons)
    to_xy, to_ll = make_projection(ref_lat, ref_lon)

    # Project polygons + union for buffer computations
    polys_xy = []
    for n, poly_ll in polys_ll:
        poly_xy = Polygon([to_xy(*p) for p in poly_ll])
        polys_xy.append((n, poly_xy, poly_ll))
    union_xy = unary_union([p for _, p, _ in polys_xy])
    total_area_ac = union_xy.area / 4046.86
    print(f'Total area to cover: {total_area_ac:.0f} ac across 10 polygons')
    print(f'3-mile coverage radius: {RADIUS_M:.0f} m')

    # === STEP 1: sample area points ===
    area_pts = []   # list of (x, y, lat, lon, terrain_amsl, drone_amsl)
    for n, poly_xy, _ in polys_xy:
        for x, y in sample_polygon(poly_xy, AREA_SAMPLE_GRID_M):
            lat, lon = to_ll(x, y)
            ground = terrain_amsl(lat, lon)
            area_pts.append((x, y, lat, lon, ground, ground + AGL, n))
    print(f'Area sample points: {len(area_pts)}  (drone positions at AGL {AGL} m)')

    # === STEP 2: candidate launches ===
    cands_xy_raw = candidates_around(union_xy, CANDIDATE_GRID_M, CANDIDATE_BUFFER_M)
    # Filter to within CENTERLINE_MAX_M of the highway centerline (Hwy 81)
    centerline_ll = load_centerline(CENTERLINE_KML)
    centerline_xy_line = LineString([to_xy(*p) for p in centerline_ll])
    cands_xy = [(x, y) for (x, y) in cands_xy_raw
                if centerline_xy_line.distance(Point(x, y)) <= CENTERLINE_MAX_M]
    print(f'Candidate launches: {len(cands_xy_raw)} raw -> {len(cands_xy)} after centerline filter '
          f'(within {CENTERLINE_MAX_M:.0f} m of HighwayCenterline.kml)')

    # Pre-compute candidate ground elevations + lat/lon
    print(f'Pre-computing candidate ground elevations ...')
    cands = []  # (x, y, lat, lon, ground)
    for cx, cy in cands_xy:
        clat, clon = to_ll(cx, cy)
        cands.append((cx, cy, clat, clon, terrain_amsl(clat, clon)))

    # === STEP 3: coverage sets ===
    # For each candidate compute the set of area-point indices it covers.
    print(f'Computing coverage sets (this is the expensive step) ...')
    coverage_sets = []  # list of (cand_idx, set_of_area_pt_indices)
    n_area = len(area_pts)
    n_cands = len(cands)
    progress_step = max(1, n_cands // 20)
    pair_checks = 0
    los_checks = 0
    for ci, (cx, cy, clat, clon, cground) in enumerate(cands):
        if ci % progress_step == 0:
            print(f'  candidate {ci}/{n_cands}  pairs_checked={pair_checks}  LOS_checks={los_checks}')
        eye_amsl = cground + OPERATOR_EYE_M
        covered = []
        for pi, (px, py, plat, plon, _pground, pamsl, _n) in enumerate(area_pts):
            d = math.hypot(cx - px, cy - py)
            pair_checks += 1
            if d > RADIUS_M:
                continue
            clear, _, _ = los_line_clear((clat, clon), eye_amsl, (plat, plon), pamsl,
                                         samples=LOS_LINE_SAMPLES)
            los_checks += 1
            if clear:
                covered.append(pi)
        coverage_sets.append(set(covered))
    print(f'Coverage sets built in {time.time()-t0:.0f}s: '
          f'{pair_checks} distance checks, {los_checks} LOS checks')

    # === STEP 4: greedy set-cover ===
    uncovered = set(range(n_area))
    selected = []
    while uncovered:
        # Pick the candidate that covers most still-uncovered points; tiebreak by
        # higher elevation (natural VLOS hedge) and shorter mean distance to covered pts.
        best_ci = None
        best_new = 0
        best_elev = -math.inf
        for ci, cov in enumerate(coverage_sets):
            n_new = len(cov & uncovered)
            if n_new > best_new or (n_new == best_new and cands[ci][4] > best_elev):
                best_ci = ci
                best_new = n_new
                best_elev = cands[ci][4]
        if best_ci is None or best_new < EARLY_STOP_DELTA:
            break
        selected.append((best_ci, coverage_sets[best_ci] & uncovered))
        uncovered -= coverage_sets[best_ci]
        cx, cy, clat, clon, cground = cands[best_ci]
        print(f'  Launch #{len(selected)}: ({clat:.6f}, {clon:.6f}) elev {cground:.0f} m  '
              f'covers {best_new} new area pts  -> {n_area-len(uncovered)}/{n_area} '
              f'({100*(n_area-len(uncovered))/n_area:.2f}%) covered')

    print(f'\n=== Greedy result: {len(selected)} launches, '
          f'{100*(n_area-len(uncovered))/n_area:.2f}% area coverage ===')
    if uncovered:
        print(f'  WARNING: {len(uncovered)} points cannot be covered by ANY candidate '
              f'(no candidate gives 100% VLOS within 3 mi to those points).')
        # List the affected areas
        uncov_areas = {}
        for pi in uncovered:
            n = area_pts[pi][6]
            uncov_areas[n] = uncov_areas.get(n, 0) + 1
        for n, cnt in sorted(uncov_areas.items()):
            total_n = sum(1 for p in area_pts if p[6] == n)
            print(f'  Area {n}: {cnt}/{total_n} points uncovered ({100*cnt/total_n:.1f}%)')

    # === Report ===
    print(f'\n=== Recommended launches ===')
    print(f'{"#":<4}{"Lat":<12}{"Lon":<13}{"Elev":<7}{"Covers":<8}{"Areas served"}')
    print('-' * 80)
    for i, (ci, new_pts) in enumerate(selected, 1):
        cx, cy, clat, clon, cground = cands[ci]
        areas_served = sorted({area_pts[pi][6] for pi in new_pts})
        n_pts_this = len(new_pts)
        print(f'  {i:<4}{clat:<12.6f}{clon:<13.6f}{cground:<7.0f}{n_pts_this:<8}{areas_served}')

    # === KML output ===
    print(f'\nBuilding KML at {OUT_KML} ...')
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<kml xmlns="http://www.opengis.net/kml/2.2">',
             '<Document>',
             '<name>Fergus photogrammetry launches (3-mi VLOS set cover)</name>',
             f'<description><![CDATA[Minimum-launch set cover for 10 photogrammetry '
             f'areas. Each launch covers area points within {RADIUS_MI} mi euclidean AND with '
             f'100% bare-earth VLOS from operator eye (ground + {OPERATOR_EYE_M} m). '
             f'Greedy result: <b>{len(selected)} launches covering '
             f'{100*(n_area-len(uncovered))/n_area:.2f}%</b> of sampled area points.]]></description>',
             '<Style id="area"><LineStyle><color>ff00ffff</color><width>2</width></LineStyle>'
             '<PolyStyle><color>3300ffff</color></PolyStyle></Style>',
             '<Style id="launchOK"><IconStyle><color>ff00ff00</color><scale>1.5</scale>'
             '<Icon><href>http://maps.google.com/mapfiles/kml/paddle/grn-stars-lv.png</href></Icon></IconStyle>'
             '<LabelStyle><color>ff00ff00</color><scale>1.1</scale></LabelStyle></Style>',
             '<Style id="circle"><LineStyle><color>aa00ff00</color><width>2</width></LineStyle>'
             '<PolyStyle><color>2200ff00</color></PolyStyle></Style>',
             '<Style id="uncov"><IconStyle><color>ff0000ff</color><scale>0.6</scale>'
             '<Icon><href>http://maps.google.com/mapfiles/kml/shapes/cross-hairs.png</href></Icon></IconStyle></Style>']

    # Mission area polygons
    lines.append('<Folder><name>Mission area polygons</name>')
    for n, poly_xy, poly_ll in polys_xy:
        coords = ' '.join(f'{p[1]:.7f},{p[0]:.7f},0' for p in poly_ll)
        ac = poly_xy.area / 4046.86
        lines.append('<Placemark>')
        lines.append(f'<name>Area {n} ({ac:.0f} ac)</name>')
        lines.append('<styleUrl>#area</styleUrl>')
        lines.append(f'<Polygon><outerBoundaryIs><LinearRing><coordinates>{coords}</coordinates></LinearRing></outerBoundaryIs></Polygon>')
        lines.append('</Placemark>')
    lines.append('</Folder>')

    # Launches with 3-mi circles
    lines.append('<Folder><name>Recommended launches</name>')
    for i, (ci, new_pts) in enumerate(selected, 1):
        cx, cy, clat, clon, cground = cands[ci]
        areas_served = sorted({area_pts[pi][6] for pi in new_pts})
        lines.append('<Placemark>')
        lines.append(f'<name>Launch {i}</name>')
        lines.append(f'<description><![CDATA[<b>Launch {i}</b><br/>'
                     f'Lat: {clat:.6f}<br/>Lon: {clon:.6f}<br/>'
                     f'Ground elev: {cground:.0f} m AMSL<br/>'
                     f'Covers {len(new_pts)} area points<br/>'
                     f'Serves areas: {areas_served}]]></description>')
        lines.append('<styleUrl>#launchOK</styleUrl>')
        lines.append(f'<Point><coordinates>{clon:.7f},{clat:.7f},0</coordinates></Point>')
        lines.append('</Placemark>')
        # Approximate 3-mi circle polygon (32-gon around launch)
        circ = []
        for k in range(33):
            theta = 2 * math.pi * k / 32
            dx = RADIUS_M * math.cos(theta); dy = RADIUS_M * math.sin(theta)
            cl, ln = to_ll(cx + dx, cy + dy)
            circ.append(f'{ln:.7f},{cl:.7f},0')
        lines.append('<Placemark>')
        lines.append(f'<name>Launch {i} 3-mi radius</name>')
        lines.append('<styleUrl>#circle</styleUrl>')
        lines.append(f'<Polygon><outerBoundaryIs><LinearRing><coordinates>{" ".join(circ)}</coordinates></LinearRing></outerBoundaryIs></Polygon>')
        lines.append('</Placemark>')
    lines.append('</Folder>')

    # Uncovered points (if any)
    if uncovered:
        lines.append('<Folder><name>Uncovered points (no launch achieves 100% VLOS within 3 mi)</name>')
        for pi in sorted(uncovered):
            _x, _y, plat, plon, _g, _a, n = area_pts[pi]
            lines.append('<Placemark>')
            lines.append(f'<name>Area {n} uncovered pt</name>')
            lines.append('<styleUrl>#uncov</styleUrl>')
            lines.append(f'<Point><coordinates>{plon:.7f},{plat:.7f},0</coordinates></Point>')
            lines.append('</Placemark>')
        lines.append('</Folder>')

    lines.append('</Document></kml>')
    with open(OUT_KML, 'wb') as f:
        f.write('\n'.join(lines).encode('utf-8'))
    print(f'Wrote {OUT_KML}  ({len(selected)} launches, {len(uncovered)} uncovered pts)')
    print(f'Total elapsed: {time.time()-t0:.0f}s')


if __name__ == '__main__':
    main()
