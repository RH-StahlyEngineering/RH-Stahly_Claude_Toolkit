"""Build a KML from analyze.py's acq_data.json: trajectories (green=valid/red=invalid),
optional footprints (valid AERIAL), optional date filter and speed-band footprint masking.

Usage:
  python make_kml.py --acq <OUT>/acq_data.json --out <OUT>/acquisitions.kml \
      [--footprints --agl 50] [--speed-band 9.5 12.25 --sessions <PROCESSING_DIR>] \
      [--date-min 2026-06-30] [--ref LAT LON]
Speed-band footprints re-read the .nav (need --sessions); otherwise footprints buffer the
stored trajectory. All geometry is clampToGround.
"""
import argparse, os, json, glob
import phoenix_lib as P

STYLES = ('  <Style id="valid"><LineStyle><color>ff00ff00</color><width>3</width></LineStyle></Style>\n'
          '  <Style id="invalid"><LineStyle><color>ff0000ff</color><width>3</width></LineStyle></Style>\n'
          '  <Style id="fp"><LineStyle><color>ff0088ff</color><width>1</width></LineStyle>'
          '<PolyStyle><color>4d00aaff</color></PolyStyle></Style>\n'
          '  <Style id="ref"><IconStyle><color>ffff00ff</color><scale>1.3</scale></IconStyle></Style>')


def coords(pts):
    return " ".join(f"{o:.8f},{a:.8f},0" for a, o in pts)


def line_pm(name, style, pts):
    return (f'  <Placemark><name>{name}</name><styleUrl>#{style}</styleUrl>'
            f'<LineString><tessellate>1</tessellate><altitudeMode>clampToGround</altitudeMode>'
            f'<coordinates>{coords(pts)}</coordinates></LineString></Placemark>')


def footprint_pm(name, rings):
    polys = "".join(f'<Polygon><tessellate>1</tessellate><altitudeMode>clampToGround</altitudeMode>'
                    f'<outerBoundaryIs><LinearRing><coordinates>{coords(r)}</coordinates>'
                    f'</LinearRing></outerBoundaryIs></Polygon>' for r in rings)
    geom = polys if len(rings) == 1 else f'<MultiGeometry>{polys}</MultiGeometry>'
    return f'  <Placemark><name>{name}</name><styleUrl>#fp</styleUrl>{geom}</Placemark>'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--acq', required=True); ap.add_argument('--out', required=True)
    ap.add_argument('--footprints', action='store_true'); ap.add_argument('--agl', type=float, default=50.0)
    ap.add_argument('--speed-band', nargs=2, type=float); ap.add_argument('--sessions')
    ap.add_argument('--date-min'); ap.add_argument('--ref', nargs=2, type=float)
    a = ap.parse_args()
    acq = json.load(open(a.acq))
    body = []; nt = nf = 0
    for r in acq:
        if not r.get('has_nav'): continue
        if a.date_min and r.get('scan_start_utc', '')[:10] < a.date_min: continue
        s = r['session']
        body.append(line_pm(f"Trajectory {s}", 'valid' if r['valid'] else 'invalid', r['traj'])); nt += 1
        if a.footprints and r['valid'] and r['type'] == 'AERIAL':
            if a.speed_band and a.sessions:
                navs = glob.glob(os.path.join(a.sessions, s, '*.nav'))
                nav = P.parse_nav(navs[0]) if navs else None
                runs = P.speed_runs(nav['pts'], a.speed_band[0], a.speed_band[1]) if nav else []
                if not runs:
                    print(f"  note: {s} no in-band ({a.speed_band[0]}-{a.speed_band[1]} m/s) segments"); continue
                rings = P.footprint_rings(runs, a.agl)
            else:
                rings = P.footprint_rings(r['traj'], a.agl)
            body.append(footprint_pm(f"Footprint {s}", rings)); nf += 1
    if a.ref:
        body.append(f'  <Placemark><name>Reference point</name><styleUrl>#ref</styleUrl>'
                    f'<Point><coordinates>{a.ref[1]:.8f},{a.ref[0]:.8f},0</coordinates></Point></Placemark>')
    desc = "GREEN=valid, RED=invalid." + (f" Footprints = valid AERIAL, {a.agl:g}m AGL swath." if a.footprints else "")
    kml = ('<?xml version="1.0" encoding="UTF-8"?>\n<kml xmlns="http://www.opengis.net/kml/2.2"><Document>\n'
           f'  <name>Phoenix LiDAR acquisitions</name>\n  <description>{desc}</description>\n'
           + STYLES + '\n' + "\n".join(body) + '\n</Document></kml>')
    open(a.out, 'w', encoding='utf-8').write(kml)
    print(f"WROTE {a.out}  ({nt} trajectories, {nf} footprints)")


if __name__ == '__main__':
    main()
