"""Build the session layout for the 50m/11.5m/jut-out-aligned plan.

Inputs:
  - Highway centerline KML (curve-following polyline)
  - Corridor union KML (target polygon)
  - Jut-outs JSON (polygon-based, with centroids — from find_corridor_jutouts.py v2)

Output:
  - JSON: 13 A-points (anchored to selected jut-outs + 2 intermediates)
  - JSON: 12 strips (A_i -> A_{i+1})
  - KML: target, highway, jut-outs (marked with size), A-points, CURVE-FOLLOWING
    strip swaths, cross-lines aimed at jut-out centroids (whatever angle that is)
"""
import os, sys, math, json, re
SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SKILL_DIR, 'scripts'))

from shapely.geometry import LineString, Polygon
from shapely.ops import substring
from coverage_check_multi import make_projection, parse_kml_polygon

KML_HIGHWAY = 'C:/Users/rharbach.STAHLY/Downloads/HighwayCenterline.kml'
TARGET_KML  = 'C:/Users/rharbach.STAHLY/Downloads/Fergus Hilger-Roy — corridor union.kml'
JUTOUTS_JSON = 'C:/Users/rharbach.STAHLY/Downloads/Fergus_corridor_jutouts.json'
OUT_JSON   = 'C:/Users/rharbach.STAHLY/Downloads/Fergus_session_layout.json'
OUT_KML    = 'C:/Users/rharbach.STAHLY/Downloads/Fergus_session_layout.kml'

AGL = 50.0
SWATH_HALF_M = 75.0     # 1.5 * AGL each side of polyline = strip swath half
CROSS_MARGIN_M = 25.0

# Layout: 1-based "selected jut-out idx" or None (for intermediate)
# Anchored to big jut-outs (>5 ac); intermediates fill gaps > ~3 mi.
LAYOUT = [
    {'jutout_idx': 1,    'note': 'big - Hilger end'},      # 0.00 mi  31.6 ac
    {'jutout_idx': 2,    'note': 'big'},                    # 1.02 mi  13.0 ac
    {'jutout_idx': 3,    'note': 'small filler'},           # 3.78 mi   1.6 ac
    {'jutout_idx': 4,    'note': 'big'},                    # 5.38 mi  18.0 ac
    {'jutout_idx': 7,    'note': 'medium filler'},          # 7.57 mi   1.5 ac
    {'along_mi': 10.57,  'note': 'intermediate'},           # gap fill
    {'jutout_idx': 8,    'note': 'medium filler'},          # 13.36 mi  2.3 ac
    {'jutout_idx': 11,   'note': 'big'},                    # 15.37 mi 41.4 ac
    {'jutout_idx': 12,   'note': 'small filler'},           # 17.66 mi  1.3 ac
    {'jutout_idx': 13,   'note': 'medium filler'},          # 19.93 mi  2.5 ac
    {'jutout_idx': 16,   'note': 'big - east of Roy'},      # 22.18 mi  8.9 ac
    {'along_mi': 25.18,  'note': 'intermediate'},           # gap fill
    {'jutout_idx': 19,   'note': 'big - Roy end'},          # 28.19 mi 51.5 ac
]


def load_linestring(path):
    txt = open(path, 'r', encoding='utf-8').read()
    m = re.search(r'<LineString[\s\S]*?<coordinates>([\s\S]+?)</coordinates>', txt)
    return [tuple(map(float, t.split(',')[:2][::-1])) for t in m.group(1).strip().split()]


def coords(latlons):
    return ' '.join(f'{lon:.7f},{lat:.7f},0' for (lat, lon) in latlons)


def main():
    highway = load_linestring(KML_HIGHWAY)
    target_outer, target_holes = parse_kml_polygon(TARGET_KML)[0]
    jutouts = json.load(open(JUTOUTS_JSON))

    ref_lat = sum(p[0] for p in highway) / len(highway)
    ref_lon = sum(p[1] for p in highway) / len(highway)
    m_lat = 111132.0
    m_lon = 111132.0 * math.cos(math.radians(ref_lat))
    def to_xy(lat, lon): return ((lon - ref_lon) * m_lon, (lat - ref_lat) * m_lat)
    def from_xy(x, y): return (ref_lat + y/m_lat, ref_lon + x/m_lon)

    hwy_xy = [to_xy(*p) for p in highway]
    hwy_line = LineString(hwy_xy)

    # Build A-points
    a_points = []
    for i, entry in enumerate(LAYOUT, start=1):
        if 'jutout_idx' in entry:
            jut = jutouts[entry['jutout_idx'] - 1]
            # A = highway anchor for the jut-out (closest point on highway to centroid)
            ax, ay = jut['hwy_anchor_xy']
            along_m = jut['along_m']
            a_points.append({
                'index': i,
                'along_mi': along_m / 1609.34,
                'along_m': along_m,
                'lat': jut['hwy_anchor_ll'][0],
                'lon': jut['hwy_anchor_ll'][1],
                'xy': [ax, ay],
                'jutout_idx': entry['jutout_idx'],
                'jutout_centroid_ll': jut['centroid_ll'],
                'jutout_centroid_xy': jut['centroid_xy'],
                'jutout_area_ac': jut['area_ac'],
                'jutout_side': jut['side'],
                'note': entry['note'],
            })
        else:
            along_m = entry['along_mi'] * 1609.34
            # Interpolate highway at this along-distance
            pt = hwy_line.interpolate(along_m)
            a_points.append({
                'index': i,
                'along_mi': entry['along_mi'],
                'along_m': along_m,
                'lat': from_xy(pt.x, pt.y)[0],
                'lon': from_xy(pt.x, pt.y)[1],
                'xy': [pt.x, pt.y],
                'jutout_idx': None,
                'jutout_centroid_ll': None,
                'jutout_centroid_xy': None,
                'jutout_area_ac': None,
                'jutout_side': None,
                'note': entry['note'],
            })

    # Strips
    strips = []
    for i in range(len(a_points) - 1):
        a = a_points[i]; b = a_points[i+1]
        strip_len_m = b['along_m'] - a['along_m']
        strips.append({
            'index': i+1,
            'a_idx': i+1, 'b_idx': i+2,
            'a_ll': [a['lat'], a['lon']],
            'b_ll': [b['lat'], b['lon']],
            'strip_len_m': strip_len_m,
            'strip_len_mi': strip_len_m / 1609.34,
            'jutout_idx_at_a': a['jutout_idx'],
        })

    # Cross-lines: aimed from A through jut-out centroid (whatever angle that is)
    # For intermediate A's (no jut-out): perpendicular to highway tangent at canonical length
    cross_lines = []
    for a in a_points:
        ax, ay = a['xy']
        # Highway tangent at A
        d = a['along_m']
        eps = 0.5
        dp1 = max(0, d - eps)
        dp2 = min(hwy_line.length, d + eps)
        p1 = hwy_line.interpolate(dp1); p2 = hwy_line.interpolate(dp2)
        tx = p2.x - p1.x; ty = p2.y - p1.y
        L = math.hypot(tx, ty)
        if L > 0: tx, ty = tx/L, ty/L
        perp = (-ty, tx)

        if a['jutout_idx'] is not None:
            # Aim from A through jut-out centroid
            cx, cy = a['jutout_centroid_xy']
            dirx = cx - ax; diry = cy - ay
            dist_to_centroid = math.hypot(dirx, diry)
            if dist_to_centroid > 0:
                ux = dirx / dist_to_centroid; uy = diry / dist_to_centroid
                # Extend past centroid by enough to clear the jut-out's perpendicular extent
                # Total length toward jut-out: ~2 * distance to centroid + margin
                forward_len = 2 * dist_to_centroid + CROSS_MARGIN_M
                # Back the other way: 75 m past the centerline
                back_len = 75.0
                end1 = (ax + ux * forward_len, ay + uy * forward_len)
                end2 = (ax - ux * back_len, ay - uy * back_len)
                # Compute angle relative to highway tangent
                dot = ux * tx + uy * ty
                angle_deg = math.degrees(math.acos(max(-1, min(1, dot))))
                cross_lines.append({
                    'a_idx': a['index'],
                    'end1_ll': list(from_xy(*end1)),
                    'end2_ll': list(from_xy(*end2)),
                    'cross_dir_xy': [ux, uy],
                    'aimed_at_jutout': a['jutout_idx'],
                    'cross_total_len_m': forward_len + back_len,
                    'angle_from_perp_deg': abs(90 - angle_deg),
                })
                continue
        # Canonical perpendicular at intermediate A's
        half = (2 * AGL + 2 * CROSS_MARGIN_M) / 2
        end1 = (ax + perp[0] * half, ay + perp[1] * half)
        end2 = (ax - perp[0] * half, ay - perp[1] * half)
        cross_lines.append({
            'a_idx': a['index'],
            'end1_ll': list(from_xy(*end1)),
            'end2_ll': list(from_xy(*end2)),
            'cross_dir_xy': list(perp),
            'aimed_at_jutout': None,
            'cross_total_len_m': 2 * half,
            'angle_from_perp_deg': 0.0,
        })

    # Save JSON
    json.dump({
        'a_points': [{k: v for k, v in a.items() if k != 'xy' and k != 'jutout_centroid_xy'} for a in a_points],
        'strips': strips,
        'cross_lines': cross_lines,
    }, open(OUT_JSON, 'w'), indent=2)
    print(f'Saved layout: {OUT_JSON}')

    print(f'\n=== {len(a_points)} A-points / {len(strips)} sessions / {2*len(strips)} flights ===')
    print(f'{"#":<4}{"Along mi":<10}{"Lat":<11}{"Lon":<11}{"Anchor":<8}{"Area ac":<10}'
          f'{"Strip mi":<10}{"X-line angle":<14}')
    for a in a_points:
        strip_mi = ''
        for s in strips:
            if s['a_idx'] == a['index']:
                strip_mi = f"{s['strip_len_mi']:.2f}"
                break
        jut = f'#{a["jutout_idx"]}' if a['jutout_idx'] else 'intermd.'
        area = f'{a["jutout_area_ac"]:.1f}' if a['jutout_area_ac'] else '-'
        cl = next(c for c in cross_lines if c['a_idx'] == a['index'])
        angle = f'{cl["angle_from_perp_deg"]:.0f}° off perp' if a['jutout_idx'] else 'perpendicular'
        print(f"{a['index']:<4}{a['along_mi']:<10.2f}{a['lat']:<11.5f}{a['lon']:<11.5f}{jut:<8}{area:<10}{strip_mi:<10}{angle:<14}")

    # Build KML
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>',
           '<name>Fergus 50m/11.5m Session Layout v2 — jut-out-aligned (polygon-based)</name>',
           '<description>13 A-points / 12 sessions / 24 flights at 50m/11.5m. '
           '11 of 13 cross-lines aimed at jut-out centroids (free angle); '
           '2 intermediate A-points have canonical perpendicular cross-lines. '
           'Strip swaths follow the highway curve (buffered ±75 m).</description>',
           '<Style id="target"><LineStyle><color>ff00ff00</color><width>2</width></LineStyle>'
           '<PolyStyle><color>2000ff00</color></PolyStyle></Style>',
           '<Style id="hwy"><LineStyle><color>ff00ffff</color><width>2</width></LineStyle></Style>',
           '<Style id="strip"><LineStyle><color>ffff8800</color><width>1</width></LineStyle>'
           '<PolyStyle><color>40ff8800</color></PolyStyle></Style>',
           '<Style id="apoint_jut"><IconStyle><scale>1.4</scale>'
           '<Icon><href>http://maps.google.com/mapfiles/kml/paddle/grn-stars.png</href></Icon></IconStyle></Style>',
           '<Style id="apoint_int"><IconStyle><scale>1.2</scale>'
           '<Icon><href>http://maps.google.com/mapfiles/kml/paddle/wht-circle.png</href></Icon></IconStyle></Style>',
           '<Style id="cross_jut"><LineStyle><color>ff00aaff</color><width>4</width></LineStyle></Style>',
           '<Style id="cross_int"><LineStyle><color>ff888888</color><width>2</width></LineStyle></Style>',
           '<Style id="jutout_big"><IconStyle><scale>1.2</scale><color>ff0000ff</color>'
           '<Icon><href>http://maps.google.com/mapfiles/kml/shapes/star.png</href></Icon></IconStyle></Style>',
           '<Style id="jutout_sm"><IconStyle><scale>0.7</scale><color>ff7777ff</color>'
           '<Icon><href>http://maps.google.com/mapfiles/kml/shapes/star.png</href></Icon></IconStyle></Style>']

    # Target
    holes_kml = ''
    for h in target_holes:
        holes_kml += f'<innerBoundaryIs><LinearRing><coordinates>{coords(h)}</coordinates></LinearRing></innerBoundaryIs>'
    out.append(f'<Placemark><name>Target corridor union</name><styleUrl>#target</styleUrl>'
               f'<Polygon><outerBoundaryIs><LinearRing><coordinates>{coords(target_outer)}</coordinates></LinearRing></outerBoundaryIs>{holes_kml}</Polygon></Placemark>')

    # Highway
    out.append(f'<Placemark><name>Hwy 81</name><styleUrl>#hwy</styleUrl>'
               f'<LineString><coordinates>{coords(highway)}</coordinates></LineString></Placemark>')

    # Strip swaths: buffer the highway segment between A_i and A_{i+1} by ±75 m
    out.append('<Folder><name>Strip swaths (highway buffered ±75 m, curve-following)</name>')
    for s in strips:
        a_along = a_points[s['a_idx']-1]['along_m']
        b_along = a_points[s['b_idx']-1]['along_m']
        # Extract substring of highway between a_along and b_along
        sub = substring(hwy_line, a_along, b_along)
        # Buffer by 75m, flat caps
        buf = sub.buffer(SWATH_HALF_M, cap_style='flat', join_style='round')
        if buf.geom_type == 'Polygon':
            ext = list(buf.exterior.coords)
        else:
            ext = list(list(buf.geoms)[0].exterior.coords)
        ext_ll = [from_xy(x, y) for (x, y) in ext]
        out.append(f'<Placemark><name>Strip {s["index"]} ({s["strip_len_mi"]:.2f} mi)</name>'
                   f'<styleUrl>#strip</styleUrl>'
                   f'<Polygon><outerBoundaryIs><LinearRing><coordinates>{coords(ext_ll)}</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>')
    out.append('</Folder>')

    # All jut-outs (big = star icon, small = smaller star) — placed at centroid
    out.append('<Folder><name>All jut-outs (red stars at centroid; selected as A-anchors get green A-paddles separately)</name>')
    for k, j in enumerate(jutouts, start=1):
        cen = j['centroid_ll']
        style = 'jutout_big' if j['area_ac'] >= 5 else 'jutout_sm'
        out.append(f'<Placemark><name>Jut-out #{k} ({j["area_ac"]:.1f} ac, {j["side"]})</name>'
                   f'<styleUrl>#{style}</styleUrl>'
                   f'<Point><coordinates>{cen[1]:.7f},{cen[0]:.7f},0</coordinates></Point></Placemark>')
    out.append('</Folder>')

    # A-points
    out.append('<Folder><name>A-points (launch/landing)</name>')
    for a in a_points:
        style = 'apoint_jut' if a['jutout_idx'] else 'apoint_int'
        label = f'A{a["index"]} @ {a["along_mi"]:.2f} mi'
        if a['jutout_idx']:
            desc = f'Anchored to jut-out #{a["jutout_idx"]} ({a["jutout_area_ac"]:.1f} ac, {a["jutout_side"]})'
        else:
            desc = f'Intermediate A (no jut-out within 3 mi)'
        out.append(f'<Placemark><name>{label}</name><description>{desc}</description><styleUrl>#{style}</styleUrl>'
                   f'<Point><coordinates>{a["lon"]:.7f},{a["lat"]:.7f},0</coordinates></Point></Placemark>')
    out.append('</Folder>')

    # Cross-lines — aimed at jut-out centroids (free angle) or canonical perpendicular at intermediates
    out.append('<Folder><name>Cross-lines (orange = aims at jut-out centroid; gray = canonical perpendicular)</name>')
    for c in cross_lines:
        style = 'cross_jut' if c['aimed_at_jutout'] else 'cross_int'
        if c['aimed_at_jutout']:
            label = f'X-line A{c["a_idx"]} → jut-out #{c["aimed_at_jutout"]} ({c["angle_from_perp_deg"]:.0f}° off perp)'
        else:
            label = f'X-line A{c["a_idx"]} (perpendicular)'
        out.append(f'<Placemark><name>{label}</name><styleUrl>#{style}</styleUrl>'
                   f'<LineString><coordinates>'
                   f'{c["end1_ll"][1]:.7f},{c["end1_ll"][0]:.7f},0 '
                   f'{c["end2_ll"][1]:.7f},{c["end2_ll"][0]:.7f},0'
                   f'</coordinates></LineString></Placemark>')
    out.append('</Folder>')

    out.append('</Document></kml>')
    open(OUT_KML, 'w', encoding='utf-8').write('\n'.join(out))
    print(f'\nWrote KML: {OUT_KML}')


if __name__ == '__main__':
    main()
