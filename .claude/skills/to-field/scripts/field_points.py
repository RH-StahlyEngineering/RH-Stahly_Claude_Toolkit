"""One point list -> data collector PNEZD + the field card's point table, so they always match.

Usage:  py field_points.py points.json [card.html]

points.json:
{
  "job": "2071-07D26",
  "grid": {"name": "RMTCRS Milk River", "crs": "EPSG:7094"   # or "proj4": "..." when the EPSG code is not in the local PROJ database (7094 is not); units come from the CRS
           , "units": "ift"},                                 # label only
  "vertical": "NAVD88 (GEOID18)",
  "points": [ {"name": "60", "lat": 48.50505063, "lon": -111.85508541, "elev_ft": 3284.449,
               "desc": "BASE FND 2in MDT ALUMC", "type": "base|ngs|target|control"} , ... ],
  "layers": { ... }   # used by mkkml.py
}
Writes <job>_field_pts_PNEZD.csv next to points.json. If card.html is given, replaces the content between
<!--PTS--> and <!--/PTS--> with a table row per point (name, lat, lon, grid N / E, elev, type).
"""
import json, os, re, sys
from pyproj import CRS, Transformer

def load(path):
    d = json.load(open(path, encoding="utf8"))
    g = d["grid"]
    crs = CRS.from_user_input(g.get("crs") or g["proj4"])
    tr = Transformer.from_crs(4326, crs, always_xy=True)
    unit = crs.axis_info[0].unit_conversion_factor  # metres per grid unit
    rows = []
    for p in d["points"]:
        e, n = tr.transform(p["lon"], p["lat"])
        rows.append(dict(p, N=n, E=e))
    return d, rows

def write_pnezd(d, rows, out_dir):
    out = os.path.join(out_dir, f"{d['job']}_field_pts_PNEZD.csv")
    with open(out, "w", newline="") as fh:
        for r in rows:
            fh.write(f"{r['name']},{r['N']:.3f},{r['E']:.3f},{r.get('elev_ft', 0):.3f},{r.get('desc', '')}\n")
    return out

def fill_card(card, d, rows):
    tr = "".join(
        f'<tr><td>{r["name"]}</td><td class="mono">{r["lat"]:.8f}</td><td class="mono">{r["lon"]:.8f}</td>'
        f'<td class="mono">{r["N"]:.2f} / {r["E"]:.2f}</td><td>{r.get("elev_ft", 0):.2f}</td><td>{r.get("type", "")}</td></tr>'
        for r in rows)
    s = open(card, encoding="utf8").read()
    if "<!--PTS-->" not in s:
        sys.exit(f"{card}: no <!--PTS--><!--/PTS--> markers")
    s = re.sub(r"<!--PTS-->.*?<!--/PTS-->", lambda m: "<!--PTS-->" + tr + "<!--/PTS-->", s, flags=re.S)
    open(card, "w", encoding="utf8").write(s)

if __name__ == "__main__":
    d, rows = load(sys.argv[1])
    print(write_pnezd(d, rows, os.path.dirname(os.path.abspath(sys.argv[1]))))
    if len(sys.argv) > 2:
        fill_card(sys.argv[2], d, rows); print("card table filled:", len(rows), "points")
