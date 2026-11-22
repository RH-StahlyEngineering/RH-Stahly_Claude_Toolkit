"""Control index: a map of prior Stahly control/monument records by locator.

  control_index.py index <root>... --db <file>
  control_index.py search (<lat> <lon> | --kml FILE | --job NNNN-XXXXX) --db <file> [--radius MI] [--all]

Stores pointers only (source, job, name, code, description, kind, flags, ~10 m locator).
Never survey values: read those from the source file.
"""
import argparse
import json
import math
import os
import re
import sqlite3
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kinds import classify, condition_flags  # noqa: E402

LOCATOR_DECIMALS = 4  # ~11 m N-S, ~7 m E-W at Montana latitudes
LOCATOR_LABEL = "locator only"
KIND_RANK = {"control": 0, "monument": 1, "other": 2}

SCHEMA = """
CREATE TABLE IF NOT EXISTS records (
  source_path TEXT, job_number TEXT, point_name TEXT, recorded TEXT,
  feature_code TEXT, description TEXT, kind TEXT, flags TEXT,
  lat REAL, lon REAL, coord_system TEXT, date TEXT);
CREATE INDEX IF NOT EXISTS records_src ON records(source_path);
CREATE TABLE IF NOT EXISTS files (source_path TEXT PRIMARY KEY, status TEXT, error TEXT);
"""

JOB_RE = re.compile(r"[\\/]A?(\d{4})-[^\\/]*[\\/]-([0-9A-Za-z]{5})")


def job_number(path):
    m = JOB_RE.search(path)
    return f"{m.group(1)}-{m.group(2)}" if m else None


def split_code(recorded):
    """Stahly convention: 'CODE [CODE..] /description'. First '/' splits."""
    code, sep, desc = recorded.partition("/")
    return code.strip(), desc.strip() if sep else ""


# ---------- JXL ----------

def _f(el, path):
    t = el.findtext(path)
    return float(t) if t not in (None, "") else None


def _grid_transformer(root):
    """pyproj transformer grid(m) -> lon/lat from the job's last ProjectionRecord, or None."""
    projs = root.findall("./FieldBook/ProjectionRecord/Projection")
    proj = next((p for p in reversed(projs) if p.findtext("Type") not in (None, "NotSet")), None)
    if proj is None:
        return None
    t = proj.findtext("Type")
    g = lambda k: proj.findtext(k)  # noqa: E731
    common = f"+lat_0={g('CentralLatitude')} +lon_0={g('CentralLongitude')} +x_0={g('FalseEasting')} +y_0={g('FalseNorthing')} +ellps=GRS80 +units=m +no_defs"
    if t == "Lambert1Parallel":
        p4 = f"+proj=lcc +lat_1={g('CentralLatitude')} +k_0={g('Scale')} {common}"
    elif t == "Lambert2Parallel":
        p4 = f"+proj=lcc +lat_1={g('NorthParallel')} +lat_2={g('SouthParallel')} {common}"
    elif t == "TransverseMercator":
        p4 = f"+proj=tmerc +k_0={g('Scale')} {common}"
    else:
        return None
    from pyproj import Transformer
    return Transformer.from_crs(p4, "EPSG:4326", always_xy=True)


def parse_jxl(path):
    root = ET.parse(path).getroot()
    cs = root.find("./FieldBook/CoordinateSystemRecord[SystemName!='']")
    coord_system = " / ".join(filter(None, [cs.findtext("SystemName"), cs.findtext("ZoneName")])) if cs is not None else None
    tf = None
    for pt in root.findall("./Reductions/Point"):
        recorded = pt.findtext("Code") or ""
        lat, lon = _f(pt, "WGS84/Latitude"), _f(pt, "WGS84/Longitude")
        if lat is None:
            n, e = _f(pt, "Grid/North"), _f(pt, "Grid/East")
            if n is None:
                continue
            tf = tf or _grid_transformer(root)
            if tf is None:
                continue
            lon, lat = tf.transform(e, n)
        yield {
            "point_name": pt.findtext("Name"), "recorded": recorded,
            "lat": round(lat, LOCATOR_DECIMALS), "lon": round(lon, LOCATOR_DECIMALS),
            "coord_system": coord_system, "date": root.get("TimeStamp"),
        }


# ---------- commands ----------

def connect(db):
    con = sqlite3.connect(db, timeout=30)
    con.executescript(SCHEMA)
    return con


def cmd_index(args):
    con = connect(args.db)
    for top in args.roots:
        for dirpath, _, files in os.walk(top):
            for fn in files:
                if not fn.lower().endswith(".jxl"):
                    continue
                path = os.path.join(dirpath, fn)
                try:
                    rows = list(parse_jxl(path))
                except Exception as exc:  # noqa: BLE001 - every parse failure is reported, not hidden
                    with con:
                        con.execute("DELETE FROM records WHERE source_path=?", (path,))
                        con.execute("INSERT OR REPLACE INTO files VALUES (?,?,?)", (path, "failed", str(exc)))
                    continue
                job = job_number(path)
                with con:
                    con.execute("DELETE FROM records WHERE source_path=?", (path,))
                    for r in rows:
                        code, desc = split_code(r["recorded"])
                        con.execute(
                            "INSERT INTO records VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                            (path, job, r["point_name"], r["recorded"], code, desc,
                             classify(code, desc), json.dumps(condition_flags(r["recorded"])),
                             r["lat"], r["lon"], r["coord_system"], r["date"]))
                    con.execute("INSERT OR REPLACE INTO files VALUES (?,?,?)", (path, "ok", None))
    con.close()


def miles_between(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * 3958.7613 * math.asin(math.sqrt(a))


def read_kml_polygons(path):
    """Outer rings of every Polygon in a KML, as [(lon, lat), ...]."""
    rings = []
    for el in ET.parse(path).getroot().iter():
        if el.tag.rsplit("}", 1)[-1] != "Polygon":
            continue
        for c in el.iter():
            if c.tag.rsplit("}", 1)[-1] == "outerBoundaryIs":
                text = next((x.text for x in c.iter() if x.tag.rsplit("}", 1)[-1] == "coordinates"), "") or ""
                ring = [tuple(map(float, t.split(",")[:2])) for t in text.split()]
                if len(ring) >= 3:
                    rings.append(ring)
    if not rings:
        sys.exit(f"no polygon found in {path}")
    return rings


def miles_to_polygons(lat, lon, rings):
    """0 inside any ring, else miles to the nearest edge (local flat projection, fine at site scale)."""
    my = 69.0
    mx = 69.0 * math.cos(math.radians(lat))
    best = math.inf
    for ring in rings:
        pts = [((x - lon) * mx, (y - lat) * my) for x, y in ring]
        inside = False
        for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
            if (y1 > 0) != (y2 > 0) and 0 < (x2 - x1) * (0 - y1) / (y2 - y1) + x1:
                inside = not inside
            dx, dy = x2 - x1, y2 - y1
            t = max(0.0, min(1.0, -(x1 * dx + y1 * dy) / (dx * dx + dy * dy))) if dx or dy else 0.0
            best = min(best, math.hypot(x1 + t * dx, y1 + t * dy))
        if inside:
            return 0.0
    return best


COLS = "source_path, job_number, point_name, recorded, feature_code, description, kind, flags, lat, lon, coord_system, date"


def _candidates(con, args):
    """(query echo, rows, distance fn or None) for the chosen search mode."""
    if args.job:
        rows = con.execute(f"SELECT {COLS} FROM records WHERE job_number=?", (args.job,)).fetchall()
        return {"job": args.job}, rows, None
    if args.kml:
        rings = read_kml_polygons(args.kml)
        pts = [p for r in rings for p in r]
        lats, lons = [p[1] for p in pts], [p[0] for p in pts]
        query = {"kml": args.kml, "radius_mi": args.radius}
        dist = lambda lat, lon: miles_to_polygons(lat, lon, rings)  # noqa: E731
        box = (min(lats), max(lats), min(lons), max(lons))
    else:
        if args.lat is None or args.lon is None:
            sys.exit("search needs <lat> <lon>, --kml or --job")
        query = {"lat": args.lat, "lon": args.lon, "radius_mi": args.radius}
        dist = lambda lat, lon: miles_between(args.lat, args.lon, lat, lon)  # noqa: E731
        box = (args.lat, args.lat, args.lon, args.lon)
    dlat = args.radius / 69.0 + 0.001
    dlon = dlat / max(math.cos(math.radians(max(abs(box[0]), abs(box[1])))), 0.01)
    rows = con.execute(f"SELECT {COLS} FROM records WHERE lat BETWEEN ? AND ? AND lon BETWEEN ? AND ?",
                       (box[0] - dlat, box[1] + dlat, box[2] - dlon, box[3] + dlon)).fetchall()
    return query, rows, dist


SAME_MARK_CELLS = 1  # locator cells (1e-4 deg) apart that still count as one mark


def _mark_number(name):
    m = re.search(r"\d+", name or "")
    return m.group().lstrip("0") or "0" if m else None


def _same_mark(a, b):
    """Same kind, adjacent locator cell, and same point number (CP60 ~ 60R) or same description."""
    tol = SAME_MARK_CELLS * 10 ** -LOCATOR_DECIMALS + 1e-9
    if a["kind"] != b["kind"]:
        return False
    if abs(a["locator"]["lat"] - b["locator"]["lat"]) > tol or abs(a["locator"]["lon"] - b["locator"]["lon"]) > tol:
        return False
    na, nb = _mark_number(a["point_name"]), _mark_number(b["point_name"])
    desc = lambda r: " ".join(r["description"].upper().split())  # noqa: E731
    return (na is not None and na == nb) or (desc(a) != "" and desc(a) == desc(b))


def group_duplicates(results):
    """Collapse copies of one mark found in several records; every copy listed in `sources`."""
    groups = []
    for r in results:
        g = next((g for g in groups if any(_same_mark(r, m) for m in g)), None)
        (g.append(r) if g is not None else groups.append([r]))
    out = []
    for g in groups:
        primary = max(g, key=lambda r: (len(r["description"]), -(r["distance_mi"] or 0)))
        merged = dict(primary)
        merged["distance_mi"] = min((r["distance_mi"] for r in g), default=None) if primary["distance_mi"] is not None else None
        merged["flags"] = sorted({f for r in g for f in r["flags"]})
        merged["sources"] = [{k: r[k] for k in ("source_path", "job_number", "point_name", "recorded", "date", "coord_system")}
                             for r in g]
        out.append(merged)
    return out


def cmd_search(args):
    con = connect(args.db)
    query, rows, dist = _candidates(con, args)
    results = []
    for (src, job, name, recorded, code, desc, kind, flags, lat, lon, cs, date) in rows:
        if kind == "other" and not args.all:
            continue
        d = None
        if dist is not None:
            d = dist(lat, lon)
            if d > args.radius:
                continue
            d = round(d, 3)
        results.append({
            "kind": kind, "distance_mi": d, "point_name": name, "feature_code": code,
            "description": desc, "recorded": recorded, "flags": json.loads(flags),
            "job_number": job, "source_path": src, "coord_system": cs, "date": date,
            "locator": {"lat": lat, "lon": lon, "label": LOCATOR_LABEL},
        })
    results = group_duplicates(results)
    results.sort(key=lambda r: (KIND_RANK[r["kind"]], r["distance_mi"] or 0, r["point_name"] or ""))
    failed = [{"source_path": p, "error": e} for p, e in con.execute("SELECT source_path, error FROM files WHERE status='failed'")]
    json.dump({"query": query, "results": results, "unparsed_files": failed}, sys.stdout, indent=1)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("index", help="crawl roots for .jxl files into the control index")
    i.add_argument("roots", nargs="+")
    i.add_argument("--db", required=True, help="SQLite control index file")
    s = sub.add_parser("search", help="records within a radius, ranked kind then distance (JSON)")
    s.add_argument("lat", type=float, nargs="?")
    s.add_argument("lon", type=float, nargs="?")
    s.add_argument("--kml", help="limits KML: radius measured from the polygon edge (0 inside)")
    s.add_argument("--job", help="job number, e.g. 2071-07D26: every record of that job")
    s.add_argument("--radius", type=float, default=1.0, help="miles (default 1)")
    s.add_argument("--all", action="store_true", help="include kind 'other' (non-control points)")
    s.add_argument("--db", required=True)
    args = ap.parse_args(argv)
    {"index": cmd_index, "search": cmd_search}[args.cmd](args)


if __name__ == "__main__":
    main()
