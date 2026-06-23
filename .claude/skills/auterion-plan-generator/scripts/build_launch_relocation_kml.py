"""Generate a Google Earth KML showing each problem launch's original position,
its scouted VLOS-clean alternative, and an arrow connecting them. Also includes
flight paths and corridor union for context."""
import os, sys, json, re

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SKILL_DIR, 'scripts'))
from los_check import extract_flight_path, interpolate_path

PLAN_DIR = 'C:/Users/rharbach.STAHLY/Documents/Auterion Mission Control/Missions'
CORRIDOR_KML = 'C:/Users/rharbach.STAHLY/Downloads/Fergus Hilger-Roy — corridor union.kml'
OUT_KML = 'C:/Users/rharbach.STAHLY/Downloads/Fergus_launch_relocations.kml'

# (pair_label, files, original_ll, original_ground_m, original_vlos_pct,
#  alt_ll, alt_ground_m, alt_vlos_pct, drive_m, recommendation)
CASES = [
    ('Pair 6 (L6)', ('Fergus13.plan', 'Fergus14.plan'),
     (47.27476, -109.25332), 1360, 79.07,
     (47.276110, -109.249341), 1370, 100.00,
     336, 'Use visual observer at proposed spot if you can; otherwise relocate'),
    ('Pair 7 (L7)', ('Fergus15.plan', 'Fergus16.plan'),
     (47.26383, -109.28697), 1375, 99.22,
     (47.265180, -109.290948), 1361, 100.00,
     336, 'DO NOT RELOCATE - 1.9m block over <1% of flight is operationally insignificant'),
    ('Pair 8 (L8)', ('Fergus17.plan', 'Fergus18.plan'),
     (47.25977, -109.31117), 1331, 64.77,
     (47.259770, -109.313159), 1347, 100.00,
     150, 'RECOMMENDED - cheapest move (150m), biggest VLOS gain'),
    ('Pair 9 (L9)', ('Fergus19.plan', 'Fergus20.plan'),
     (47.26004, -109.34256), 1286, 100.00,
     (47.26004, -109.34256), 1286, 100.00,
     0, 'NO ACTION NEEDED - 100% VLOS at full precision'),
]


def load_corridor_polygon(path):
    """Parse the first Polygon outer ring from a KML."""
    with open(path, 'r', encoding='utf-8') as f:
        txt = f.read()
    m = re.search(r'<Polygon[\s\S]*?<outerBoundaryIs>[\s\S]*?<coordinates>([\s\S]*?)</coordinates>', txt)
    if not m: return []
    return m.group(1).strip().split()


def fmt(p):
    return f'{p[1]:.7f},{p[0]:.7f},0'


def main():
    # Load corridor outline
    corridor_tokens = load_corridor_polygon(CORRIDOR_KML)

    lines = []
    lines.append('<?xml version="1.0" encoding="UTF-8"?>')
    lines.append('<kml xmlns="http://www.opengis.net/kml/2.2">')
    lines.append('<Document>')
    lines.append('<name>Fergus launch relocations (VLOS analysis)</name>')
    lines.append('<description>Original launches vs scouted VLOS-clean alternatives. '
                 'Red icon = original (has VLOS issues). Green icon = proposed alternative '
                 '(100% VLOS verified at full precision). Yellow arrow shows direction and '
                 'distance from original to proposed.</description>')

    # Styles
    lines.append('''<Style id="origStyle">
  <IconStyle><color>ff0000ff</color><scale>1.4</scale>
    <Icon><href>http://maps.google.com/mapfiles/kml/pal4/icon44.png</href></Icon>
  </IconStyle>
  <LabelStyle><color>ff0000ff</color><scale>1.0</scale></LabelStyle>
</Style>''')
    lines.append('''<Style id="altStyle">
  <IconStyle><color>ff00ff00</color><scale>1.4</scale>
    <Icon><href>http://maps.google.com/mapfiles/kml/pal4/icon24.png</href></Icon>
  </IconStyle>
  <LabelStyle><color>ff00ff00</color><scale>1.0</scale></LabelStyle>
</Style>''')
    lines.append('''<Style id="arrowStyle">
  <LineStyle><color>ff00ffff</color><width>4</width></LineStyle>
  <PolyStyle><color>5500ffff</color></PolyStyle>
</Style>''')
    lines.append('''<Style id="flightPathStyle">
  <LineStyle><color>aa808080</color><width>1</width></LineStyle>
</Style>''')
    lines.append('''<Style id="corridorStyle">
  <LineStyle><color>ff808080</color><width>2</width></LineStyle>
  <PolyStyle><color>22808080</color></PolyStyle>
</Style>''')
    lines.append('''<Style id="noActionStyle">
  <IconStyle><color>ff80ff80</color><scale>1.0</scale>
    <Icon><href>http://maps.google.com/mapfiles/kml/pal4/icon56.png</href></Icon>
  </IconStyle>
  <LabelStyle><color>ff80ff80</color><scale>1.0</scale></LabelStyle>
</Style>''')

    # Corridor union as backdrop
    if corridor_tokens:
        lines.append('<Folder><name>Context</name>')
        lines.append('<Placemark><name>Fergus Hilger-Roy corridor union</name>')
        lines.append('<styleUrl>#corridorStyle</styleUrl>')
        lines.append('<Polygon><outerBoundaryIs><LinearRing><coordinates>')
        lines.append(' '.join(corridor_tokens))
        lines.append('</coordinates></LinearRing></outerBoundaryIs></Polygon>')
        lines.append('</Placemark>')
        lines.append('</Folder>')

    # Per-pair folder
    for label, (ef, wf), orig, o_elev, o_pct, alt, a_elev, a_pct, drive, recommend in CASES:
        lines.append(f'<Folder><name>{label} - {ef[:-5]} + {wf[:-5]}</name>')
        lines.append(f'<description><![CDATA[{recommend}]]></description>')

        # Original launch
        is_no_action = (drive == 0)
        orig_style = 'noActionStyle' if is_no_action else 'origStyle'
        lines.append('<Placemark>')
        lines.append(f'<name>{label} ORIGINAL ({o_pct:.1f}% VLOS)</name>')
        lines.append(f'<description><![CDATA[<b>Original launch (from HomePoints.kml)</b><br/>'
                     f'Lat: {orig[0]:.6f}<br/>Lon: {orig[1]:.6f}<br/>'
                     f'Ground elev: {o_elev} m AMSL<br/>'
                     f'VLOS: <b>{o_pct:.1f}%</b><br/><br/>'
                     f'<b>Recommendation:</b> {recommend}]]></description>')
        lines.append(f'<styleUrl>#{orig_style}</styleUrl>')
        lines.append(f'<Point><coordinates>{fmt(orig)}</coordinates></Point>')
        lines.append('</Placemark>')

        # Alternative launch (only if different)
        if drive > 0:
            lines.append('<Placemark>')
            lines.append(f'<name>{label} PROPOSED ({a_pct:.1f}% VLOS)</name>')
            lines.append(f'<description><![CDATA[<b>Scouted alternative</b><br/>'
                         f'Lat: {alt[0]:.6f}<br/>Lon: {alt[1]:.6f}<br/>'
                         f'Ground elev: {a_elev} m AMSL ({a_elev - o_elev:+d} m vs original)<br/>'
                         f'Drive from original: {drive} m<br/>'
                         f'VLOS: <b>{a_pct:.1f}%</b><br/><br/>'
                         f'<b>Recommendation:</b> {recommend}]]></description>')
            lines.append('<styleUrl>#altStyle</styleUrl>')
            lines.append(f'<Point><coordinates>{fmt(alt)}</coordinates></Point>')
            lines.append('</Placemark>')

            # Arrow line from original to proposed
            lines.append('<Placemark>')
            lines.append(f'<name>{label} relocation arrow ({drive} m, {a_elev - o_elev:+d} m elev)</name>')
            lines.append('<styleUrl>#arrowStyle</styleUrl>')
            lines.append('<LineString><tessellate>1</tessellate><coordinates>')
            lines.append(f'{fmt(orig)} {fmt(alt)}')
            lines.append('</coordinates></LineString>')
            lines.append('</Placemark>')

        # Flight paths from both tiles (interpolated, simplified)
        try:
            east = json.load(open(os.path.join(PLAN_DIR, ef)))
            west = json.load(open(os.path.join(PLAN_DIR, wf)))
            combined = extract_flight_path(east) + extract_flight_path(west)
            interp = interpolate_path(combined, 50.0)
            if interp:
                lines.append('<Placemark>')
                lines.append(f'<name>{label} flight paths (combined east + west)</name>')
                lines.append('<styleUrl>#flightPathStyle</styleUrl>')
                lines.append('<LineString><tessellate>1</tessellate><altitudeMode>absolute</altitudeMode><coordinates>')
                lines.append(' '.join(f'{p[1]:.7f},{p[0]:.7f},{p[2]:.1f}' for p in interp))
                lines.append('</coordinates></LineString>')
                lines.append('</Placemark>')
        except Exception as e:
            print(f'Warning: could not load flight paths for {label}: {e}')

        lines.append('</Folder>')

    lines.append('</Document></kml>')

    with open(OUT_KML, 'wb') as f:
        f.write('\n'.join(lines).encode('utf-8'))

    print(f'Wrote {OUT_KML}')
    print(f'  Cases: {len(CASES)}')


if __name__ == '__main__':
    main()
