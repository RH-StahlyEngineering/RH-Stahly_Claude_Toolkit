"""Build two final KMLs:
  1. Fergus_all_coverage.kml — every .plan's ground swath, color-coded by category
     (original user pairs Fergus1-20 = blue; algorithmic gap-fill pairs Fergus21-38
     = green; standalone Fergus39 = orange). Includes HOME points and a merged
     total-coverage overlay.
  2. Fergus_uncovered_gaps_final.kml — what remains uncovered after Fergus1..39.
"""
import os, sys, json, math

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SKILL_DIR, 'scripts'))
from coverage_check_multi import (
    parse_kml_polygon, parse_plan_geometry, make_projection,
    corridorscan_coverage_polygon, coverage_to_kml,
)
from shapely.geometry import Polygon
from shapely.ops import unary_union

KML_TARGET = 'C:/Users/rharbach.STAHLY/Downloads/Fergus Hilger-Roy — corridor union.kml'
PLAN_DIR   = 'C:/Users/rharbach.STAHLY/Documents/Auterion Mission Control/Missions'
OUT_COVERAGE = 'C:/Users/rharbach.STAHLY/Downloads/Fergus_all_coverage.kml'
OUT_GAPS     = 'C:/Users/rharbach.STAHLY/Downloads/Fergus_uncovered_gaps_final.kml'


def categorize(n):
    if n <= 20:
        pair = (n + 1) // 2
        return 'user', f'Pair {pair}', 'ff0000ff', '5500aaff'  # red icon, orange fill
    elif n <= 38:
        pair = (n - 21) // 2 + 10
        return 'algo', f'Pair {pair} (gap-fill)', 'ff00ff00', '5500aa55'  # green icon, green fill
    else:
        return 'standalone', 'Fergus39 (Gap 25 standalone)', 'ff0080ff', '5500ddff'  # orange icon, yellow fill


def poly_to_kml_coords(poly, to_ll):
    """Convert a shapely Polygon (in meters) to KML coordinate strings.
    Returns (outer_coords, [inner_coords]) — strings ready to put in <coordinates>."""
    outer = ' '.join(f'{to_ll(x, y)[1]:.7f},{to_ll(x, y)[0]:.7f},0'
                     for x, y in poly.exterior.coords)
    inners = []
    for ring in poly.interiors:
        ic = ' '.join(f'{to_ll(x, y)[1]:.7f},{to_ll(x, y)[0]:.7f},0'
                      for x, y in ring.coords)
        inners.append(ic)
    return outer, inners


def write_polygon_placemark(name, description, style_id, poly_or_multi, to_ll, lines):
    polys = [poly_or_multi] if poly_or_multi.geom_type == 'Polygon' else list(poly_or_multi.geoms)
    for k, p in enumerate(polys):
        sfx = f' part {k+1}' if len(polys) > 1 else ''
        outer, inners = poly_to_kml_coords(p, to_ll)
        lines.append('<Placemark>')
        lines.append(f'<name>{name}{sfx}</name>')
        if description:
            lines.append(f'<description><![CDATA[{description}]]></description>')
        lines.append(f'<styleUrl>#{style_id}</styleUrl>')
        lines.append('<Polygon><outerBoundaryIs><LinearRing><coordinates>')
        lines.append(outer)
        lines.append('</coordinates></LinearRing></outerBoundaryIs>')
        for ic in inners:
            lines.append('<innerBoundaryIs><LinearRing><coordinates>')
            lines.append(ic)
            lines.append('</coordinates></LinearRing></innerBoundaryIs>')
        lines.append('</Polygon>')
        lines.append('</Placemark>')


def main():
    # Projection anchored at target centroid
    target_outer, target_holes = parse_kml_polygon(KML_TARGET)[0]
    ref_lat = sum(p[0] for p in target_outer) / len(target_outer)
    ref_lon = sum(p[1] for p in target_outer) / len(target_outer)
    to_xy, to_ll = make_projection(ref_lat, ref_lon)
    target_xy = Polygon([to_xy(*p) for p in target_outer],
                        [[to_xy(*p) for p in h] for h in target_holes])

    # Load every plan -> (n, category, coverage_polygon_meters, home_ll, polyline_ll)
    rows = []
    for n in list(range(1, 39)) + [39]:
        pp = os.path.join(PLAN_DIR, f'Fergus{n}.plan')
        kind, geom, agl, cw, ta = parse_plan_geometry(pp)
        if kind != 'CorridorScan': continue
        cov = corridorscan_coverage_polygon(geom, agl, cw, ta, to_xy)
        plan = json.load(open(pp))
        home = plan['mission']['plannedHomePosition']
        cat, pair_label, icon_color, fill_color = categorize(n)
        rows.append({
            'n': n, 'cat': cat, 'pair_label': pair_label,
            'icon_color': icon_color, 'fill_color': fill_color,
            'cov': cov, 'home': (home[0], home[1], home[2]),
            'polyline': geom, 'agl': agl,
        })

    # === KML #1: All coverage ===
    print(f'Building {OUT_COVERAGE}...')
    union = unary_union([r['cov'] for r in rows])
    union_in_target_ac = union.intersection(target_xy).area / 4046.86
    target_ac = target_xy.area / 4046.86

    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<kml xmlns="http://www.opengis.net/kml/2.2">',
             '<Document>',
             '<name>Fergus all coverage (91.51% of corridor union)</name>',
             f'<description><![CDATA[All {len(rows)} .plan files covering '
             f'{union_in_target_ac:.2f} ac of the {target_ac:.2f} ac corridor union target = '
             f'{100*union_in_target_ac/target_ac:.2f}%.<br/>'
             f'<b>Blue</b> = user-provided pairs (Fergus1-20)<br/>'
             f'<b>Green</b> = algorithmic gap-fill pairs (Fergus21-38)<br/>'
             f'<b>Orange</b> = standalone Gap 25 fill (Fergus39)]]></description>']

    # Styles
    style_defs = [
        ('userSwath',    'ff0000ff', '4400aaff', 1),
        ('algoSwath',    'ff00ff00', '4400aa55', 1),
        ('standaloneSwath','ff0080ff', '4400ddff', 1),
        ('userHome',    'ff0000ff', 'http://maps.google.com/mapfiles/kml/paddle/blu-square-lv.png'),
        ('algoHome',    'ff00ff00', 'http://maps.google.com/mapfiles/kml/paddle/grn-square-lv.png'),
        ('standaloneHome','ff0080ff','http://maps.google.com/mapfiles/kml/paddle/ylw-square-lv.png'),
        ('targetOutline','ff404040', '00000000', 3),
        ('unionStyle',  'ff408040', '40408040', 2),
    ]
    for d in style_defs:
        if len(d) == 4:
            sid, line_c, poly_c, width = d
            lines.append(f'<Style id="{sid}"><LineStyle><color>{line_c}</color><width>{width}</width></LineStyle>'
                         f'<PolyStyle><color>{poly_c}</color></PolyStyle></Style>')
        else:
            sid, line_c, icon_href = d
            lines.append(f'<Style id="{sid}"><IconStyle><color>{line_c}</color><scale>0.9</scale>'
                         f'<Icon><href>{icon_href}</href></Icon></IconStyle>'
                         f'<LabelStyle><color>{line_c}</color><scale>0.8</scale></LabelStyle></Style>')

    # Folder: Target outline (context)
    lines.append('<Folder><name>Target: Fergus Hilger-Roy corridor union</name>')
    write_polygon_placemark('Corridor union (target)', None, 'targetOutline', target_xy, to_ll, lines)
    lines.append('</Folder>')

    # Folder: Total coverage union (one big polygon = the 91.51%)
    lines.append('<Folder><name>Total coverage union (91.51% of target)</name>')
    union_clipped = union.intersection(target_xy)
    if not union_clipped.is_empty:
        write_polygon_placemark('Total coverage (Fergus1..39)',
                                f'{union_in_target_ac:.2f} ac = {100*union_in_target_ac/target_ac:.2f}% of target',
                                'unionStyle', union_clipped, to_ll, lines)
    lines.append('</Folder>')

    # Folder per category, with per-plan swath polygons
    for cat_key, folder_name, swath_style, home_style in [
        ('user', 'User-provided pairs (Fergus 1-20)', 'userSwath', 'userHome'),
        ('algo', 'Algorithmic gap-fill pairs (Fergus 21-38)', 'algoSwath', 'algoHome'),
        ('standalone', 'Standalone Gap 25 fill (Fergus 39)', 'standaloneSwath', 'standaloneHome'),
    ]:
        cat_rows = [r for r in rows if r['cat'] == cat_key]
        if not cat_rows: continue
        lines.append(f'<Folder><name>{folder_name}</name>')
        # Per-pair sub-folder
        by_pair = {}
        for r in cat_rows:
            by_pair.setdefault(r['pair_label'], []).append(r)
        for pair_label, prows in sorted(by_pair.items()):
            lines.append(f'<Folder><name>{pair_label}</name>')
            for r in prows:
                pname = f'Fergus{r["n"]}.plan'
                cov_clip = r['cov'].intersection(target_xy)
                cov_ac = cov_clip.area / 4046.86
                desc = f'{pname}<br/>HOME ({r["home"][0]:.6f}, {r["home"][1]:.6f}, {r["home"][2]:.0f} m)<br/>' \
                       f'AGL {r["agl"]:.2f} m  Polyline pts {len(r["polyline"])}<br/>' \
                       f'Coverage within target: {cov_ac:.2f} ac'
                if not cov_clip.is_empty:
                    write_polygon_placemark(f'{pname} swath ({cov_ac:.1f} ac)',
                                            desc, swath_style, cov_clip, to_ll, lines)
                # HOME placemark
                lines.append('<Placemark>')
                lines.append(f'<name>{pname} HOME</name>')
                lines.append(f'<description><![CDATA[{desc}]]></description>')
                lines.append(f'<styleUrl>#{home_style}</styleUrl>')
                lines.append(f'<Point><coordinates>{r["home"][1]:.7f},{r["home"][0]:.7f},0</coordinates></Point>')
                lines.append('</Placemark>')
                # Polyline (line)
                pl = ' '.join(f'{p[1]:.7f},{p[0]:.7f},0' for p in r['polyline'])
                lines.append('<Placemark>')
                lines.append(f'<name>{pname} centerline</name>')
                lines.append(f'<styleUrl>#{swath_style}</styleUrl>')
                lines.append(f'<LineString><tessellate>1</tessellate><coordinates>{pl}</coordinates></LineString>')
                lines.append('</Placemark>')
            lines.append('</Folder>')
        lines.append('</Folder>')

    lines.append('</Document></kml>')
    with open(OUT_COVERAGE, 'wb') as f:
        f.write('\n'.join(lines).encode('utf-8'))
    print(f'  Wrote {OUT_COVERAGE}')

    # === KML #2: Updated gaps ===
    print(f'Building {OUT_GAPS}...')
    uncovered = target_xy.difference(union)
    uncov_ac = uncovered.area / 4046.86
    cov_pct = 100 * (target_ac - uncov_ac) / target_ac
    n = coverage_to_kml(uncovered, to_ll, target_holes, OUT_GAPS,
                        name=f'Uncovered after Fergus1..39 ({uncov_ac:.2f} ac uncovered, {cov_pct:.2f}% covered)')
    print(f'  Wrote {OUT_GAPS}: {n} uncovered polygons, {uncov_ac:.2f} ac total')


if __name__ == '__main__':
    main()
