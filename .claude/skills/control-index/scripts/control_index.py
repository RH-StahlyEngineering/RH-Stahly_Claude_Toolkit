"""Control index: a map of prior Stahly control/monument records by locator.

  control_index.py index <root>... --db <file>
  control_index.py search <lat> <lon> --db <file> [--radius MI] [--all]

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


def cmd_search(args):
    con = connect(args.db)
    dlat = args.radius / 69.0 + 0.001
    dlon = dlat / max(math.cos(math.radians(args.lat)), 0.01)
    rows = con.execute(
        "SELECT source_path, job_number, point_name, recorded, feature_code, description, kind, flags, lat, lon, coord_system, date "
        "FROM records WHERE lat BETWEEN ? AND ? AND lon BETWEEN ? AND ?",
        (args.lat - dlat, args.lat + dlat, args.lon - dlon, args.lon + dlon)).fetchall()
    results = []
    for (src, job, name, recorded, code, desc, kind, flags, lat, lon, cs, date) in rows:
        if kind == "other" and not args.all:
            continue
        d = miles_between(args.lat, args.lon, lat, lon)
        if d > args.radius:
            continue
        results.append({
            "kind": kind, "distance_mi": round(d, 3), "point_name": name, "feature_code": code,
            "description": desc, "recorded": recorded, "flags": json.loads(flags),
            "job_number": job, "source_path": src, "coord_system": cs, "date": date,
            "locator": {"lat": lat, "lon": lon, "label": LOCATOR_LABEL},
        })
    results.sort(key=lambda r: (KIND_RANK[r["kind"]], r["distance_mi"]))
    failed = [{"source_path": p, "error": e} for p, e in con.execute("SELECT source_path, error FROM files WHERE status='failed'")]
    json.dump({"query": {"lat": args.lat, "lon": args.lon, "radius_mi": args.radius},
               "results": results, "unparsed_files": failed}, sys.stdout, indent=1)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("index", help="crawl roots for .jxl files into the control index")
    i.add_argument("roots", nargs="+")
    i.add_argument("--db", required=True, help="SQLite control index file")
    s = sub.add_parser("search", help="records within a radius, ranked kind then distance (JSON)")
    s.add_argument("lat", type=float)
    s.add_argument("lon", type=float)
    s.add_argument("--radius", type=float, default=1.0, help="miles (default 1)")
    s.add_argument("--all", action="store_true", help="include kind 'other' (non-control points)")
    s.add_argument("--db", required=True)
    args = ap.parse_args(argv)
    {"index": cmd_index, "search": cmd_search}[args.cmd](args)


if __name__ == "__main__":
    main()
