"""Optimize cross-line ANGLE and POSITION to maximize traversal through each
jut-out polygon. The cross-line does NOT have to pass through A — the drone
transits from A to the cross-line, flies it, then transits back to start the survey.

Algorithm:
  - For each A anchored to a jut-out, get that jut-out's polygon piece
  - Compute the polygon's oriented bounding box (OBB) — long axis = candidate angle
  - 2D search: angle [-15°, +15°] around OBB long-axis bearing,
                 perpendicular offset [-300m, +300m] from polygon centroid
    pick (angle, offset) that maximizes polygon intersection length
  - Position the cross-line at the polygon centroid + offset along perpendicular
  - Length = polygon intersection extent + 75 m margin each side
  - Report A-to-line transit distance (battery cost)
"""
import os, sys, math, json, re
SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SKILL_DIR, 'scripts'))

from shapely.geometry import LineString, Polygon, Point
from coverage_check_multi import make_projection, parse_kml_polygon

KML_HIGHWAY = 'C:/Users/rharbach.STAHLY/Downloads/HighwayCenterline.kml'
TARGET_KML  = 'C:/Users/rharbach.STAHLY/Downloads/Fergus Hilger-Roy — corridor union.kml'
JUTOUTS_JSON = 'C:/Users/rharbach.STAHLY/Downloads/Fergus_corridor_jutouts.json'
LAYOUT_JSON = 'C:/Users/rharbach.STAHLY/Downloads/Fergus_session_layout.json'

NOMINAL_HALF_M = 75.0
LINE_MARGIN_M  = 75.0   # extend cross-line 75 m past polygon entry/exit
ANGLE_SEARCH_DEG = 90   # +/- this from OBB long axis
ANGLE_STEP_DEG = 2
OFFSET_RANGE_M = 400
OFFSET_STEP_M  = 25


def load_linestring(path):
    txt = open(path, 'r', encoding='utf-8').read()
    m = re.search(r'<LineString[\s\S]*?<coordinates>([\s\S]+?)</coordinates>', txt)
    return [tuple(map(float, t.split(',')[:2][::-1])) for t in m.group(1).strip().split()]


def main():
    highway = load_linestring(KML_HIGHWAY)
    target_outer, target_holes = parse_kml_polygon(TARGET_KML)[0]
    jutouts = json.load(open(JUTOUTS_JSON))
    layout = json.load(open(LAYOUT_JSON))

    ref_lat = sum(p[0] for p in highway) / len(highway)
    ref_lon = sum(p[1] for p in highway) / len(highway)
    m_lat = 111132.0
    m_lon = 111132.0 * math.cos(math.radians(ref_lat))
    def to_xy(lat, lon): return ((lon - ref_lon) * m_lon, (lat - ref_lat) * m_lat)
    def from_xy(x, y): return (ref_lat + y/m_lat, ref_lon + x/m_lon)

    hwy_xy = [to_xy(*p) for p in highway]
    hwy_line = LineString(hwy_xy)
    target_xy = Polygon([to_xy(*p) for p in target_outer],
                        [[to_xy(*p) for p in h] for h in target_holes])

    # Per-jut-out polygon pieces
    jut_region = target_xy.difference(hwy_line.buffer(NOMINAL_HALF_M, cap_style='flat'))
    pieces = list(jut_region.geoms) if jut_region.geom_type == 'MultiPolygon' else [jut_region]
    pieces = [p for p in pieces if p.area >= 5000]
    pieces.sort(key=lambda p: hwy_line.project(p.centroid))
    jut_polys = {i+1: p for i, p in enumerate(pieces)}

    def obb_long_axis_bearing(poly):
        """Long-axis bearing (deg, 0-360 east-CCW) of the polygon's oriented bbox."""
        obb = poly.minimum_rotated_rectangle
        coords = list(obb.exterior.coords)
        edges = [(coords[i+1][0]-coords[i][0], coords[i+1][1]-coords[i][1])
                 for i in range(len(coords)-1)]
        edges_with_len = [(math.hypot(dx, dy), dx, dy) for dx, dy in edges]
        edges_with_len.sort(reverse=True)
        _, dx, dy = edges_with_len[0]
        return math.degrees(math.atan2(dy, dx)) % 180   # normalize to 0-180 (line, not vector)

    def optimize_2d(jut_poly, a_xy):
        """2D search over angle and perpendicular offset from centroid."""
        cx, cy = jut_poly.centroid.x, jut_poly.centroid.y
        base_angle = obb_long_axis_bearing(jut_poly)
        SEARCH_LEN = 3000   # very long candidate line

        best = (-1, base_angle, 0, None)  # (in_poly_len, angle, offset_perp, line_endpoints)

        for ang_delta in range(-ANGLE_SEARCH_DEG, ANGLE_SEARCH_DEG + 1, ANGLE_STEP_DEG):
            angle_deg = (base_angle + ang_delta) % 180
            rad = math.radians(angle_deg)
            ux, uy = math.cos(rad), math.sin(rad)
            # Perpendicular to the line direction
            perp_x, perp_y = -uy, ux
            for off in range(-OFFSET_RANGE_M, OFFSET_RANGE_M + 1, OFFSET_STEP_M):
                # Line center = polygon centroid + offset along perpendicular
                lcx = cx + off * perp_x
                lcy = cy + off * perp_y
                end1 = (lcx + ux * SEARCH_LEN, lcy + uy * SEARCH_LEN)
                end2 = (lcx - ux * SEARCH_LEN, lcy - uy * SEARCH_LEN)
                line = LineString([end1, end2])
                ix = line.intersection(jut_poly)
                if ix.is_empty: continue
                ix_len = ix.length
                if ix_len > best[0]:
                    # Trim line to polygon entry/exit + margin
                    if ix.geom_type == 'LineString':
                        ix_lines = [ix]
                    elif ix.geom_type == 'MultiLineString':
                        ix_lines = list(ix.geoms)
                    else:
                        continue
                    params = []
                    long_line = LineString([end2, end1])
                    for ll in ix_lines:
                        for pt in ll.coords:
                            params.append(long_line.project(Point(pt)))
                    entry_p = min(params)
                    exit_p = max(params)
                    sp = long_line.interpolate(max(0, entry_p - LINE_MARGIN_M))
                    ep = long_line.interpolate(min(long_line.length, exit_p + LINE_MARGIN_M))
                    best = (ix_len, angle_deg, off, ((sp.x, sp.y), (ep.x, ep.y)))
        return best

    # User-supplied baseline (for comparison)
    USER_LINES = {
        2:  ((-109.3492677668002, 47.25624077350952), (-109.3405840539773, 47.26071819868325)),
        4:  ((-109.2606642409302, 47.26704069186942), (-109.2624273985561, 47.26940077527197)),
    }
    def user_in_poly_len(a_idx, jut_poly):
        if a_idx not in USER_LINES: return None
        (lon1, lat1), (lon2, lat2) = USER_LINES[a_idx]
        u_line = LineString([to_xy(lat1, lon1), to_xy(lat2, lon2)])
        ix = u_line.intersection(jut_poly)
        return ix.length if not ix.is_empty else 0

    print(f'{"A":<4}{"Jut-out":<10}{"Angle":<10}{"Offset":<10}{"In-poly":<12}{"Length":<10}'
          f'{"A-to-line":<11}{"User in-poly":<14}')

    new_cross_lines = []
    for a in layout['a_points']:
        a_idx = a['index']
        jut_idx = a.get('jutout_idx')
        a_xy = to_xy(a['lat'], a['lon'])

        if jut_idx and jut_idx in jut_polys:
            jut_poly = jut_polys[jut_idx]
            ix_len, angle, offset, ep = optimize_2d(jut_poly, a_xy)
            sp, end_p = ep
            line_xy = LineString([sp, end_p])
            # A-to-line distance
            a_to_line = Point(a_xy).distance(line_xy)
            u_len = user_in_poly_len(a_idx, jut_poly)
            u_len_s = f'{u_len:.1f}' if u_len is not None else '-'
            print(f'{a_idx:<4}#{jut_idx:<9}{angle:<10.1f}{offset:<10.0f}{ix_len:<12.1f}'
                  f'{line_xy.length:<10.1f}{a_to_line:<10.0f}{u_len_s:<14}')
            new_cross_lines.append({
                'a_idx': a_idx,
                'end1_ll': list(from_xy(*sp)),
                'end2_ll': list(from_xy(*end_p)),
                'aimed_at_jutout': jut_idx,
                'cross_total_len_m': line_xy.length,
                'in_polygon_len_m': ix_len,
                'angle_from_east_deg': angle,
                'a_to_line_perpdist_m': a_to_line,
            })
        else:
            # Intermediate: keep canonical perpendicular through A
            old_cl = layout['cross_lines'][a_idx - 1]
            print(f'{a_idx:<4}intermd.  -         -         -           -         -         -')
            new_cross_lines.append({
                'a_idx': a_idx,
                'end1_ll': list(old_cl['end1_ll']),
                'end2_ll': list(old_cl['end2_ll']),
                'aimed_at_jutout': None,
                'cross_total_len_m': old_cl.get('cross_total_len_m', 150),
                'in_polygon_len_m': 0,
                'angle_from_east_deg': None,
                'a_to_line_perpdist_m': 0,
            })

    layout['cross_lines'] = new_cross_lines
    json.dump(layout, open(LAYOUT_JSON, 'w'), indent=2)
    print(f'\nUpdated layout JSON: {LAYOUT_JSON}')


if __name__ == '__main__':
    main()
