"""Simple jut-out-free layout for the 50m/11.5m mission set.

Battery-limited strip layout:
  - 50 m AGL / 11.5 m/s / polyline = highway centerline
  - Per-line swath = 100 m, combined corridor = 150 m (2 transects)
  - 10 min battery / leg, ~2 min overhead -> ~5 km max survey distance
  - For 28.21 mi corridor at 2.82 mi (4.54 km) per strip: 10 strips, 11 A-points, 20 flights

Outputs:
  - 11 A-points evenly spaced along highway
  - 10 strips (strip i: A_i -> A_{i+1})
  - Cross-line at each A: canonical perpendicular to highway, length = CW + 2*margin = 200 m
  - Coverage area (strip swath ∩ target polygon)
  - PPSM math (per-pass and surveywide)
  - Flight time estimate
"""
import os, sys, math, json, re
SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SKILL_DIR, 'scripts'))

from shapely.geometry import LineString, Polygon
from shapely.ops import substring, unary_union
from coverage_check_multi import make_projection, parse_kml_polygon

KML_HIGHWAY = 'C:/Users/rharbach.STAHLY/Downloads/HighwayCenterline.kml'
TARGET_KML  = 'C:/Users/rharbach.STAHLY/Downloads/Fergus Hilger-Roy — corridor union.kml'
OUT_KML     = 'C:/Users/rharbach.STAHLY/Downloads/Fergus_simple_layout.kml'

AGL = 50.0
SPEED = 11.5
LINE_SPACING = AGL              # 50 m
PER_LINE_SWATH = 2 * AGL        # 100 m
COMBINED_SWATH = 3 * AGL        # 150 m (twice-covered zone = AGL wide; single-pass = 2*AGL total)
SWATH_HALF = COMBINED_SWATH / 2 # 75 m perpendicular from highway centerline
TWICE_HALF = AGL / 2            # 25 m perpendicular = inner zone covered by both transects
CROSS_MARGIN = 25.0
PPSM_PER_PASS_MIN = 21.0
PPSM_PER_PASS_AVG = 51.5
PPSM_PER_PASS_MAX = 85.1

N_STRIPS = 10                   # 10 strips at ~4.54 km each


def load_linestring(path):
    txt = open(path, 'r', encoding='utf-8').read()
    m = re.search(r'<LineString[\s\S]*?<coordinates>([\s\S]+?)</coordinates>', txt)
    return [tuple(map(float, t.split(',')[:2][::-1])) for t in m.group(1).strip().split()]


def coords(latlons):
    return ' '.join(f'{lon:.7f},{lat:.7f},0' for (lat, lon) in latlons)


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
    target_xy = Polygon([to_xy(*p) for p in target_outer],
                        [[to_xy(*p) for p in h] for h in target_holes])
    target_ac = target_xy.area / 4046.86
    hwy_len_m = hwy_line.length
    hwy_len_mi = hwy_len_m / 1609.34
    strip_len_m = hwy_len_m / N_STRIPS

    print(f'Highway: {hwy_len_mi:.2f} mi ({hwy_len_m/1000:.2f} km)')
    print(f'Target:  {target_ac:.1f} ac')
    print(f'Strips:  {N_STRIPS} × {strip_len_m/1000:.2f} km each ({strip_len_m/1609.34:.2f} mi)')

    # Build A-points: evenly spaced from 0 to hwy_len
    a_points = []
    for i in range(N_STRIPS + 1):
        along_m = i * strip_len_m
        pt = hwy_line.interpolate(min(along_m, hwy_len_m))
        lat, lon = from_xy(pt.x, pt.y)
        a_points.append({'idx': i+1, 'along_m': along_m, 'lat': lat, 'lon': lon, 'xy': (pt.x, pt.y)})
    n_a = len(a_points)

    # Cross-lines: canonical perpendicular at each launching A.
    # Convention: launch is A_i for strip i (A→B), so all of A_1..A_N_STRIPS launch.
    # A_{N_STRIPS+1} is just the hot-swap endpoint of strip N_STRIPS, no cross-line.
    cross_lines = []
    for a in a_points[:N_STRIPS]:
        d = a['along_m']
        eps = 0.5
        p1 = hwy_line.interpolate(max(0, d - eps))
        p2 = hwy_line.interpolate(min(hwy_len_m, d + eps))
        tx = p2.x - p1.x; ty = p2.y - p1.y
        L = math.hypot(tx, ty)
        if L > 0: tx, ty = tx/L, ty/L
        perp = (-ty, tx)
        half = (COMBINED_SWATH + 2 * CROSS_MARGIN) / 2  # 100 m total length
        ax, ay = a['xy']
        e1 = (ax + perp[0] * half, ay + perp[1] * half)
        e2 = (ax - perp[0] * half, ay - perp[1] * half)
        cross_lines.append({
            'a_idx': a['idx'],
            'end1_ll': from_xy(*e1),
            'end2_ll': from_xy(*e2),
            'len_m': 2 * half,
        })

    # Strip swaths (highway buffered ±75 m for each section)
    strip_swaths = []
    twice_zones = []
    for i in range(N_STRIPS):
        a_along = a_points[i]['along_m']
        b_along = a_points[i+1]['along_m']
        sub = substring(hwy_line, a_along, b_along)
        full_buf = sub.buffer(SWATH_HALF, cap_style='flat', join_style='round')
        twice_buf = sub.buffer(TWICE_HALF, cap_style='flat', join_style='round')
        strip_swaths.append(full_buf)
        twice_zones.append(twice_buf)

    full_union = unary_union(strip_swaths)
    twice_union = unary_union(twice_zones)
    full_ac = full_union.area / 4046.86
    twice_ac = twice_union.area / 4046.86
    once_ac = full_ac - twice_ac

    covered_in_target = full_union.intersection(target_xy)
    covered_ac = covered_in_target.area / 4046.86
    pct = 100 * covered_ac / target_ac
    twice_in_target = twice_union.intersection(target_xy)
    twice_in_target_ac = twice_in_target.area / 4046.86
    once_in_target_ac = covered_ac - twice_in_target_ac

    # PPSM math
    once_m2 = once_in_target_ac * 4046.86
    twice_m2 = twice_in_target_ac * 4046.86
    total_pts_min = once_m2 * PPSM_PER_PASS_MIN + twice_m2 * 2 * PPSM_PER_PASS_MIN
    total_pts_avg = once_m2 * PPSM_PER_PASS_AVG + twice_m2 * 2 * PPSM_PER_PASS_AVG
    total_pts_max = once_m2 * PPSM_PER_PASS_MAX + twice_m2 * 2 * PPSM_PER_PASS_MAX
    survey_avg_ppsm = total_pts_avg / (covered_ac * 4046.86)

    # Flight time estimate
    # Per leg: survey time + overhead
    # Overhead: takeoff/climb 30s + straight-line 30s + figure-8 45s + transit 30s + landing 30s = ~2.75 min
    # Survey time: strip_len / SPEED
    overhead_min = 2.75
    survey_min = strip_len_m / SPEED / 60
    leg_min = survey_min + overhead_min
    # 2 legs per session, N_STRIPS sessions
    total_min = 2 * N_STRIPS * leg_min

    print(f'\n=== Coverage ===')
    print(f'  Full swath area:        {full_ac:.1f} ac')
    print(f'    once-covered:         {once_ac:.1f} ac')
    print(f'    twice-covered:        {twice_ac:.1f} ac')
    print(f'  Covered inside target:  {covered_ac:.1f} ac of {target_ac:.1f} ac = {pct:.2f}%')
    print(f'    once-in-target:       {once_in_target_ac:.1f} ac ({100*once_in_target_ac/target_ac:.1f}% of target)')
    print(f'    twice-in-target:      {twice_in_target_ac:.1f} ac ({100*twice_in_target_ac/target_ac:.1f}% of target)')

    print(f'\n=== PPSM (50 m AGL / 11.5 m/s, 2·AGL·speed = {2*AGL*SPEED:.0f}, matches 70/8 baseline) ===')
    print(f'  Per-pass:               min {PPSM_PER_PASS_MIN}, avg {PPSM_PER_PASS_AVG}, max {PPSM_PER_PASS_MAX}')
    print(f'  Once-covered density:   {PPSM_PER_PASS_AVG:.0f} ppsm (avg)')
    print(f'  Twice-covered density:  {2*PPSM_PER_PASS_AVG:.0f} ppsm (avg)')
    print(f'  Surveywide avg PPSM:    {survey_avg_ppsm:.1f}')
    print(f'  Total points across target:')
    print(f'    Min:  {total_pts_min/1e6:.1f} M')
    print(f'    Avg:  {total_pts_avg/1e6:.1f} M')
    print(f'    Max:  {total_pts_max/1e6:.1f} M')

    print(f'\n=== Flight time ===')
    print(f'  Strips:        {N_STRIPS}')
    print(f'  Sessions:      {N_STRIPS} (A->B->A each)')
    print(f'  Flights:       {2*N_STRIPS} (= batteries)')
    print(f'  Per-leg time:  ~{leg_min:.1f} min ({survey_min:.1f} min survey + {overhead_min:.2f} min overhead)')
    print(f'  Total:         {total_min:.0f} min = {total_min/60:.2f} hr')

    # Build KML
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>',
           '<name>Fergus 50m/11.5m simple layout (no jut-out)</name>',
           f'<description>{N_STRIPS} strips at {strip_len_m/1000:.2f} km / {strip_len_m/1609.34:.2f} mi each. '
           f'{2*N_STRIPS} flights / batteries. {pct:.2f}% target coverage. '
           f'Surveywide avg {survey_avg_ppsm:.0f} ppsm. {total_min:.0f} min total flight time.</description>',
           '<Style id="target"><LineStyle><color>ff00ff00</color><width>2</width></LineStyle><PolyStyle><color>2000ff00</color></PolyStyle></Style>',
           '<Style id="hwy"><LineStyle><color>ff00ffff</color><width>2</width></LineStyle></Style>',
           '<Style id="strip_outer"><LineStyle><color>ffff8800</color><width>1</width></LineStyle><PolyStyle><color>40ff8800</color></PolyStyle></Style>',
           '<Style id="strip_twice"><LineStyle><color>ff00aaff</color><width>1</width></LineStyle><PolyStyle><color>6000aaff</color></PolyStyle></Style>',
           '<Style id="apoint"><IconStyle><scale>1.3</scale><Icon><href>http://maps.google.com/mapfiles/kml/paddle/grn-circle.png</href></Icon></IconStyle></Style>',
           '<Style id="bpoint"><IconStyle><scale>1.3</scale><Icon><href>http://maps.google.com/mapfiles/kml/paddle/orange-circle.png</href></Icon></IconStyle></Style>',
           '<Style id="perch"><IconStyle><scale>1.3</scale><Icon><href>http://maps.google.com/mapfiles/kml/paddle/blu-circle.png</href></Icon></IconStyle></Style>',
           '<Style id="xline"><LineStyle><color>ff8888ff</color><width>3</width></LineStyle></Style>']

    # Target
    holes_kml = ''
    for h in target_holes:
        holes_kml += f'<innerBoundaryIs><LinearRing><coordinates>{coords(h)}</coordinates></LinearRing></innerBoundaryIs>'
    out.append(f'<Placemark><name>Target corridor union ({target_ac:.0f} ac)</name><styleUrl>#target</styleUrl>'
               f'<Polygon><outerBoundaryIs><LinearRing><coordinates>{coords(target_outer)}</coordinates></LinearRing></outerBoundaryIs>{holes_kml}</Polygon></Placemark>')
    out.append(f'<Placemark><name>Hwy 81</name><styleUrl>#hwy</styleUrl><LineString><coordinates>{coords(highway)}</coordinates></LineString></Placemark>')

    # Strip swaths (outer 150 m wide)
    out.append('<Folder><name>Strip swaths (150 m wide, single-or-twice covered)</name>')
    for i in range(N_STRIPS):
        sw = strip_swaths[i]
        if sw.geom_type == 'Polygon':
            ext = list(sw.exterior.coords)
        else:
            ext = list(list(sw.geoms)[0].exterior.coords)
        ext_ll = [from_xy(x, y) for (x, y) in ext]
        out.append(f'<Placemark><name>Strip {i+1} swath</name><styleUrl>#strip_outer</styleUrl>'
                   f'<Polygon><outerBoundaryIs><LinearRing><coordinates>{coords(ext_ll)}</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>')
    out.append('</Folder>')

    # Twice-covered zones (50 m wide, inner)
    out.append('<Folder><name>Twice-covered zones (50 m wide, both transects)</name>')
    for i in range(N_STRIPS):
        sw = twice_zones[i]
        if sw.geom_type == 'Polygon':
            ext = list(sw.exterior.coords)
        else:
            ext = list(list(sw.geoms)[0].exterior.coords)
        ext_ll = [from_xy(x, y) for (x, y) in ext]
        out.append(f'<Placemark><name>Twice zone {i+1}</name><styleUrl>#strip_twice</styleUrl>'
                   f'<Polygon><outerBoundaryIs><LinearRing><coordinates>{coords(ext_ll)}</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>')
    out.append('</Folder>')

    # LAUNCHES (A1..A10) — green
    out.append('<Folder><name>LAUNCHES A1-A10 (where each session starts AND lands)</name>')
    for i in range(N_STRIPS):
        a = a_points[i]
        mi = a['along_m'] / 1609.34
        label = f'A{i+1} @ {mi:.2f} mi'
        desc = (f'Launch + return-landing for session {i+1}. PIC + drone + helper start here. '
                f'After session, drive ~4.5 km to A{i+2} = B{i+1}.')
        out.append(f'<Placemark><name>{label}</name><description>{desc}</description>'
                   f'<styleUrl>#apoint</styleUrl>'
                   f'<Point><coordinates>{a["lon"]:.7f},{a["lat"]:.7f},0</coordinates></Point></Placemark>')
    out.append('</Folder>')

    # HOT-SWAP POINTS (B1..B10) — orange
    out.append('<Folder><name>HOT-SWAP POINTS B1-B10 (where each session does its mid-mission battery swap)</name>')
    for i in range(N_STRIPS):
        b = a_points[i+1]
        mi = b['along_m'] / 1609.34
        label = f'B{i+1} @ {mi:.2f} mi'
        if i + 1 < N_STRIPS:
            dual = f' (also = A{i+2}, the next session\'s launch)'
        else:
            dual = ''
        desc = (f'Hot-swap point for session {i+1}. Helper pre-positions here before session starts. '
                f'PIC drives from A{i+1} ({a_points[i]["along_m"]/1609.34:.2f} mi) following the drone to a perch with view of B{i+1}. '
                f'Helper does hot swap, drone flies back to A{i+1}, helper drives back to A{i+1}.{dual}')
        out.append(f'<Placemark><name>{label}</name><description>{desc}</description>'
                   f'<styleUrl>#bpoint</styleUrl>'
                   f'<Point><coordinates>{b["lon"]:.7f},{b["lat"]:.7f},0</coordinates></Point></Placemark>')
    out.append('</Folder>')

    # PERCHES (P1..P10) — blue; loaded from user-curated JSON if present
    perches_json = 'C:/Users/rharbach.STAHLY/Downloads/Fergus_perches.json'
    if os.path.exists(perches_json):
        perches = json.load(open(perches_json))
        out.append('<Folder><name>PERCHES P1-P10 (PIC parks here at road hilltop to command landing at B)</name>')
        for p in perches:
            sess = p['session']
            label = f'P{sess} perch (for B{sess})'
            desc = (f'PIC parks here during A{sess}→B{sess} leg to command landing remotely while helper at B{sess} does hot swap. '
                    f'Local road hilltop, {p["dist_to_road_m"]:.0f} m from centerline, {p["dist_to_b_m"]:.0f} m from B{sess}, '
                    f'elev {p["perch_elev_m"]:.0f} m AMSL.')
            out.append(f'<Placemark><name>{label}</name><description>{desc}</description>'
                       f'<styleUrl>#perch</styleUrl>'
                       f'<Point><coordinates>{p["perch_lon"]:.7f},{p["perch_lat"]:.7f},0</coordinates></Point></Placemark>')
        out.append('</Folder>')

    # Cross-lines (perpendicular at each launching A)
    out.append('<Folder><name>Cross-lines (perpendicular to highway at each launch A)</name>')
    for c in cross_lines:
        out.append(f'<Placemark><name>X-line A{c["a_idx"]} ({c["len_m"]:.0f} m)</name>'
                   f'<styleUrl>#xline</styleUrl>'
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
