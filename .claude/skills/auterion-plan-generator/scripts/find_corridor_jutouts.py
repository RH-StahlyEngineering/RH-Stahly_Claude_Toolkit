"""Find jut-outs in the corridor union polygon as actual polygon features.

Method:
  1. Buffer the highway centerline by NOMINAL_HALF (= 75 m, the strip-swath half).
  2. Difference: corridor union polygon MINUS the highway buffer = the jut-out
     regions (polygon area outside the nominal swath).
  3. Each connected component of that difference is one jut-out.
  4. For each jut-out: centroid, bounding box, area, and the closest highway
     point + along-distance.

This is more correct than the 1D-sample approach because:
  - Centroid of a polygon ≠ position-of-max-perpendicular-extent
  - The "tip" (farthest vertex) ≠ the body center
  - Plateau-shaped jut-outs get the median index, not the leftmost
"""
import os, sys, math, json, re
SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SKILL_DIR, 'scripts'))

from shapely.geometry import LineString, Polygon, Point, MultiPolygon
from shapely.ops import unary_union
from coverage_check_multi import make_projection, parse_kml_polygon

KML_HIGHWAY = 'C:/Users/rharbach.STAHLY/Downloads/HighwayCenterline.kml'
TARGET_KML  = 'C:/Users/rharbach.STAHLY/Downloads/Fergus Hilger-Roy — corridor union.kml'
OUT_JSON    = 'C:/Users/rharbach.STAHLY/Downloads/Fergus_corridor_jutouts.json'

NOMINAL_HALF_M = 75.0      # strip swath half-width
MIN_JUTOUT_AREA_M2 = 5000  # ~1.2 acres minimum to count as a jut-out


def load_linestring(path):
    txt = open(path, 'r', encoding='utf-8').read()
    m = re.search(r'<LineString[\s\S]*?<coordinates>([\s\S]+?)</coordinates>', txt)
    return [tuple(map(float, t.split(',')[:2][::-1])) for t in m.group(1).strip().split()]


def main():
    highway = load_linestring(KML_HIGHWAY)
    target_outer, target_holes = parse_kml_polygon(TARGET_KML)[0]

    ref_lat = sum(p[0] for p in highway) / len(highway)
    ref_lon = sum(p[1] for p in highway) / len(highway)
    m_lat = 111132.0
    m_lon = 111132.0 * math.cos(math.radians(ref_lat))
    def to_xy(lat, lon): return ((lon - ref_lon) * m_lon, (lat - ref_lat) * m_lat)
    def from_xy(x, y): return (ref_lat + y/m_lat, ref_lon + x/m_lon)

    hwy_xy = [to_xy(*p) for p in highway]
    hwy_line = LineString(hwy_xy)
    target_poly = Polygon([to_xy(*p) for p in target_outer],
                          [[to_xy(*p) for p in h] for h in target_holes])

    # Cumulative along-highway distance for the closest-point projection later
    cum = [0.0]
    for i in range(1, len(hwy_xy)):
        dx = hwy_xy[i][0] - hwy_xy[i-1][0]
        dy = hwy_xy[i][1] - hwy_xy[i-1][1]
        cum.append(cum[-1] + math.hypot(dx, dy))
    total_hwy_len = cum[-1]
    print(f'Highway length: {total_hwy_len/1000:.2f} km')
    print(f'Target area: {target_poly.area / 4046.86:.1f} acres')

    # Step 1: buffer the highway by NOMINAL_HALF
    hwy_buffer = hwy_line.buffer(NOMINAL_HALF_M, cap_style='flat', join_style='round')

    # Step 2: target MINUS hwy_buffer = jut-out regions
    jut_region = target_poly.difference(hwy_buffer)

    # Step 3: split into connected components
    if jut_region.geom_type == 'Polygon':
        pieces = [jut_region]
    elif jut_region.geom_type == 'MultiPolygon':
        pieces = list(jut_region.geoms)
    else:
        pieces = []
    print(f'Jut-out region area (outside nominal {NOMINAL_HALF_M:.0f} m buffer): '
          f'{jut_region.area / 4046.86:.1f} acres in {len(pieces)} piece(s)')

    # Filter by minimum area
    pieces = [p for p in pieces if p.area >= MIN_JUTOUT_AREA_M2]
    print(f'After {MIN_JUTOUT_AREA_M2/4046.86:.1f}-acre minimum filter: {len(pieces)} jut-out(s)')

    # For each piece: centroid, along-distance, bbox
    def along_distance_of(xy):
        """Return cumulative along-highway distance for the closest point on hwy_line to xy."""
        p = Point(xy)
        proj = hwy_line.project(p)
        return proj

    def closest_hwy_point(xy):
        """Return (highway xy, tangent unit vec) at the closest point."""
        p = Point(xy)
        d = hwy_line.project(p)
        cp = hwy_line.interpolate(d)
        # tangent: tiny step forward
        eps = 0.5
        d2 = min(d + eps, hwy_line.length)
        cp2 = hwy_line.interpolate(d2)
        dx = cp2.x - cp.x; dy = cp2.y - cp.y
        L = math.hypot(dx, dy)
        if L == 0: return (cp.x, cp.y), (1, 0)
        return (cp.x, cp.y), (dx/L, dy/L)

    jutouts = []
    for piece in pieces:
        cx, cy = piece.centroid.x, piece.centroid.y
        along_m = along_distance_of((cx, cy))
        hwy_pt, hwy_tan = closest_hwy_point((cx, cy))
        # Compute perpendicular offset (signed): cross product of tangent and (centroid - hwy_pt)
        ox = cx - hwy_pt[0]; oy = cy - hwy_pt[1]
        cross = hwy_tan[0] * oy - hwy_tan[1] * ox
        side = 'LEFT' if cross > 0 else 'RIGHT'
        perp_dist = math.hypot(ox, oy)
        bbox = piece.bounds  # (minx, miny, maxx, maxy)
        # Bounding-box dimensions
        bbox_len_along = bbox[2] - bbox[0]
        bbox_len_perp = bbox[3] - bbox[1]
        c_lat, c_lon = from_xy(cx, cy)
        h_lat, h_lon = from_xy(hwy_pt[0], hwy_pt[1])
        jutouts.append({
            'centroid_ll': [c_lat, c_lon],
            'centroid_xy': [cx, cy],
            'along_m': along_m,
            'along_mi': along_m / 1609.34,
            'hwy_anchor_ll': [h_lat, h_lon],
            'hwy_anchor_xy': list(hwy_pt),
            'hwy_tangent': list(hwy_tan),
            'side': side,
            'perp_dist_m': perp_dist,
            'area_m2': piece.area,
            'area_ac': piece.area / 4046.86,
        })

    # Sort by along-distance
    jutouts.sort(key=lambda j: j['along_m'])

    print(f'\nJut-outs (sorted by along-distance, west-to-east):')
    print(f'{"#":<3}{"Along mi":<10}{"Area ac":<10}{"Side":<8}{"Perp m":<9}'
          f'{"Hwy anchor":<25}{"Centroid":<25}')
    for i, j in enumerate(jutouts, start=1):
        h = j['hwy_anchor_ll']; c = j['centroid_ll']
        print(f'{i:<3}{j["along_mi"]:<10.2f}{j["area_ac"]:<10.2f}{j["side"]:<8}{j["perp_dist_m"]:<9.0f}'
              f'({h[0]:.5f},{h[1]:.5f})  ({c[0]:.5f},{c[1]:.5f})')

    json.dump(jutouts, open(OUT_JSON, 'w'), indent=2)
    print(f'\nSaved {len(jutouts)} jut-outs to {OUT_JSON}')


if __name__ == '__main__':
    main()
