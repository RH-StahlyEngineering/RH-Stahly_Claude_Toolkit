"""Layered KML from points.json (see field_points.py for the schema).

Usage:  py mkkml.py points.json
Folders: one per point type present (base, ngs, target, control, prior), each point clickable with a details
table (desc, lat/lon, grid N/E, elevation); plus "layers" from points.json:
  "layers": {"Survey limits": {"line": [[lon, lat], ...]},
             "Photo coverage": {"polygon": [[lon, lat], ...]},
             "Nadir plan": {"line": [...]}, ...}
Writes <job>_field.kml next to points.json.
"""
import html, json, os, sys
from field_points import load

STYLE = {"base": ("triangle.png", "ff0000ff", 1.3), "ngs": ("target.png", "ff00ffff", 1.2),
         "target": ("cross-hairs.png", "fff03dff", 1.1), "control": ("placemark_circle.png", "ff3c5aff", 0.9),
         "prior": ("placemark_circle.png", "ff3fd2ff", 0.7)}
TITLE = {"base": "Base control", "ngs": "NGS marks", "target": "Aerial targets", "control": "Site control",
         "prior": "Prior control"}
e = html.escape

def table(rows):
    return ('<table border="1" cellpadding="3" style="border-collapse:collapse;font:12px Arial">'
            + "".join(f"<tr><td><b>{e(k)}</b></td><td>{e(str(v))}</td></tr>" for k, v in rows) + "</table>")

def main(path):
    d, rows = load(path)
    g = d["grid"]
    styles = "".join(f'<Style id="{k}"><IconStyle><color>{c}</color><scale>{s}</scale><Icon><href>'
                     f'http://maps.google.com/mapfiles/kml/shapes/{i}</href></Icon></IconStyle></Style>'
                     for k, (i, c, s) in STYLE.items())
    styles += ('<Style id="line"><LineStyle><color>ff0000ff</color><width>3</width></LineStyle>'
               '<PolyStyle><fill>0</fill></PolyStyle></Style>')
    folders = []
    for t in STYLE:
        pts = [r for r in rows if r.get("type", "control") == t]
        if not pts:
            continue
        pm = "".join(
            f'<Placemark><name>{e(r["name"])}</name><styleUrl>#{t}</styleUrl><description><![CDATA['
            + table([("Desc", r.get("desc", "")), ("Lat", f'{r["lat"]:.8f}'), ("Lon", f'{r["lon"]:.8f}'),
                     (f'{g["name"]} N / E ({g.get("units", "")})', f'{r["N"]:.3f} / {r["E"]:.3f}'),
                     (f'Elev {d.get("vertical", "")}', r.get("elev_ft", "")), ("Note", r.get("note", ""))])
            + f']]></description><Point><coordinates>{r["lon"]:.8f},{r["lat"]:.8f},0</coordinates></Point></Placemark>'
            for r in pts)
        folders.append(f"<Folder><name>{e(TITLE[t])}</name>{pm}</Folder>")
    lay = []
    for name, geo in d.get("layers", {}).items():
        if "line" in geo:
            c = geo["line"]; tag = "LineString"
        else:
            c = geo["polygon"] + geo["polygon"][:1]; tag = "LinearRing"
        coords = " ".join(f"{x:.8f},{y:.8f},0" for x, y in c)
        body = (f"<LineString><tessellate>1</tessellate><coordinates>{coords}</coordinates></LineString>" if tag == "LineString"
                else f"<Polygon><outerBoundaryIs><LinearRing><coordinates>{coords}</coordinates></LinearRing></outerBoundaryIs></Polygon>")
        lay.append(f"<Placemark><name>{e(name)}</name><styleUrl>#line</styleUrl>{body}</Placemark>")
    if lay:
        folders.append("<Folder><name>Layers</name>" + "".join(lay) + "</Folder>")
    out = os.path.join(os.path.dirname(os.path.abspath(path)), f"{d['job']}_field.kml")
    open(out, "w", encoding="utf8").write(
        '<?xml version="1.0" encoding="UTF-8"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
        f'<name>{e(d["job"])} field</name>{styles}{"".join(folders)}</Document></kml>')
    print(out)

if __name__ == "__main__":
    main(sys.argv[1])
