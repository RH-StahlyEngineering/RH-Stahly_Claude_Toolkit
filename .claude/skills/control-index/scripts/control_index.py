"""Control index: a map of prior Stahly control/monument records by locator.

  control_index.py index <root>... [--db <file>] [--budget SEC] [--max-files N]
  control_index.py search (<lat> <lon> | --kml FILE | --job NNNN-XXXXX) [--db <file>] [--radius MI] [--all]

Stores pointers only (source, job, name, code, description, kind, flags, ~10 m locator, mark group).
Never survey values: read those from the source file.
"""
import argparse
import json
import math
import os
import re
import sqlite3
import sys
import time
from pathlib import Path
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kinds import classify, condition_flags, mark_types  # noqa: E402
from exports import Skipped, parse_csv  # noqa: E402
from jxl import jxl_grid, parse_jxl  # noqa: E402
from vce import parse_vce, vce_grid  # noqa: E402

LOCATOR_M = 10.0  # locator grid spacing, metres (near-uniform N-S and E-W)
MARK_CELL_M = 1.0  # grouping bucket, metres: only decides same-mark, never output
SAME_MARK_M = 2.0  # copies of one mark: same kind and number/description within this distance
LOCATOR_LABEL = "locator only"
KIND_RANK = {"control": 0, "monument": 1, "other": 2}
SCHEMA_VERSION = "2"  # bump when stored values change: an older database is dropped and rebuilt
M_PER_DEG = 111320.0

TABLES = ("records", "files", "folders", "meta")
SCHEMA = """
CREATE TABLE IF NOT EXISTS records (
  source_path TEXT, job_number TEXT, point_name TEXT, recorded TEXT,
  feature_code TEXT, description TEXT, kind TEXT, flags TEXT,
  locator_lat REAL, locator_lon REAL, coord_system TEXT, date TEXT,
  mark_id INTEGER, mark_cell_n INTEGER, mark_cell_e INTEGER);
CREATE INDEX IF NOT EXISTS records_src ON records(source_path);
CREATE INDEX IF NOT EXISTS records_mark ON records(mark_cell_n, mark_cell_e);
CREATE INDEX IF NOT EXISTS records_mark_id ON records(mark_id);
CREATE TABLE IF NOT EXISTS files (source_path TEXT PRIMARY KEY, job_number TEXT, status TEXT, error TEXT);
CREATE TABLE IF NOT EXISTS folders (dir_path TEXT PRIMARY KEY, mtime REAL, status TEXT);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""

JOB_RE = re.compile(r"[\\/]A?(\d{4})-[^\\/]*[\\/]-([0-9A-Za-z]{5})")


def job_number(path):
    m = JOB_RE.search(path)
    return f"{m.group(1)}-{m.group(2)}" if m else None


def split_code(recorded):
    """Stahly convention: 'CODE [CODE..] /description'. First '/' splits."""
    code, sep, desc = recorded.partition("/")
    return code.strip(), desc.strip() if sep else ""


def metric_cell(lat, lon, size_m):
    """(row, col, k) of a near-square size_m grid. E-W scale k is the cosine of the whole-degree latitude
    band, so cells stay within ~1.5% of size_m and columns line up between rows."""
    k = math.cos(math.radians(round(lat)))
    return round(lat * M_PER_DEG / size_m), round(lon * M_PER_DEG * k / size_m), k


def locator(lat, lon):
    """Centre of the ~10 m locator cell holding (lat, lon)."""
    row, col, k = metric_cell(lat, lon, LOCATOR_M)
    return round(row * LOCATOR_M / M_PER_DEG, 6), round(col * LOCATOR_M / (M_PER_DEG * k), 6)


# ---------- commands ----------

CONFIG = Path(__file__).resolve().parent.parent / "config.json"


def resolve_db(flag):
    """--db flag, else CONTROL_INDEX_DB env, else `db` in the skill's config.json."""
    return flag or os.environ.get("CONTROL_INDEX_DB") or json.loads(CONFIG.read_text(encoding="utf-8"))["db"]


def connect(db):
    # Rollback journal, not WAL: the shared index may live on an SMB share where WAL is unsafe.
    # Each write is its own BEGIN IMMEDIATE transaction; overlapping runs wait on the lock.
    con = sqlite3.connect(db, timeout=120, isolation_level=None)
    con.execute("PRAGMA busy_timeout=120000")
    with write_txn(con):
        have = {n for (n,) in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        version = (con.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
                   if "meta" in have else None)
        if have & set(TABLES) and version != (SCHEMA_VERSION,):
            for t in TABLES:  # older layout: dropped; the next index run rebuilds it
                con.execute(f"DROP TABLE IF EXISTS {t}")
        for stmt in filter(str.strip, SCHEMA.split(";")):
            con.execute(stmt)
        con.execute("INSERT OR REPLACE INTO meta VALUES ('schema_version', ?)", (SCHEMA_VERSION,))
    return con


class write_txn:
    """BEGIN IMMEDIATE ... COMMIT (ROLLBACK on error)."""
    def __init__(self, con):
        self.con = con

    def __enter__(self):
        self.con.execute("BEGIN IMMEDIATE")

    def __exit__(self, et, *_):
        self.con.execute("ROLLBACK" if et else "COMMIT")


CONTEXTS = {".vce": vce_grid, ".jxl": jxl_grid}
PARSERS = {".jxl": parse_jxl, ".vce": parse_vce,
           ".csv": lambda p: parse_csv(p, CONTEXTS, job_number)}


def _mark_number(name):
    m = re.search(r"\d+", name or "")
    return (m.group().lstrip("0") or "0") if m else None


def _same_mark(name, desc, other_name, other_desc):
    """Same point number (CP60 ~ 60R) or same description, unless the descriptions name different monument
    types (MDT aluminum cap vs Stahly RPC). Kind and distance are checked by the caller."""
    ta, tb = mark_types(desc), mark_types(other_desc)
    if ta and tb and not ta & tb:
        return False
    norm = lambda d: " ".join(d.upper().split())  # noqa: E731
    num = _mark_number(name)
    return (num is not None and num == _mark_number(other_name)) or (norm(desc) != "" and norm(desc) == norm(other_desc))


def _assign_mark(con, kind, name, desc, cell_n, cell_e):
    """mark_id shared with existing copies of this mark (merging ids this copy bridges), else a new id."""
    reach = math.ceil(SAME_MARK_M / MARK_CELL_M)
    ids = {mid for mid, n, d, cn, ce in con.execute(
        "SELECT mark_id, point_name, description, mark_cell_n, mark_cell_e FROM records "
        "WHERE kind=? AND mark_cell_n BETWEEN ? AND ? AND mark_cell_e BETWEEN ? AND ?",
        (kind, cell_n - reach, cell_n + reach, cell_e - reach, cell_e + reach))
        if math.hypot(cn - cell_n, ce - cell_e) * MARK_CELL_M <= SAME_MARK_M and _same_mark(name, desc, n, d)}
    if not ids:
        return con.execute("SELECT COALESCE(MAX(mark_id), 0) + 1 FROM records").fetchone()[0]
    keep = min(ids)
    for other in ids - {keep}:
        con.execute("UPDATE records SET mark_id=? WHERE mark_id=?", (keep, other))
    return keep


def index_file(con, path):
    job = job_number(path)
    try:
        rows = list(PARSERS[os.path.splitext(path)[1].lower()](path))
    except Exception as exc:  # noqa: BLE001 - every parse failure is reported, not hidden
        with write_txn(con):
            con.execute("DELETE FROM records WHERE source_path=?", (path,))
            con.execute("INSERT OR REPLACE INTO files VALUES (?,?,?,?)",
                        (path, job, "skipped" if isinstance(exc, Skipped) else "failed", str(exc)))
        return
    with write_txn(con):
        con.execute("DELETE FROM records WHERE source_path=?", (path,))
        notes = [r["reason"] for r in rows if "skipped" in r]
        for r in rows:
            if "skipped" in r:
                continue
            code, desc = split_code(r["recorded"])
            kind = classify(code, desc)
            lat, lon = r["position"]
            cell_n, cell_e, _ = metric_cell(lat, lon, MARK_CELL_M)
            mark = _assign_mark(con, kind, r["point_name"], desc, cell_n, cell_e)
            con.execute(
                "INSERT INTO records VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (path, job, r["point_name"], r["recorded"], code, desc, kind,
                 json.dumps(condition_flags(r["recorded"]) + r.get("flags", [])),
                 *locator(lat, lon), r["coord_system"], r["date"], mark, cell_n, cell_e))
        con.execute("INSERT OR REPLACE INTO files VALUES (?,?,?,?)",
                    (path, job, "partial", "; ".join(notes)) if notes else (path, job, "ok", None))


def forget_missing(con, dirpath, present):
    """Drop records/files rows for indexed files directly in dirpath that no longer exist."""
    prefix = os.path.join(dirpath, "")
    known = [p for (p,) in con.execute("SELECT source_path FROM files WHERE source_path LIKE ? || '%'", (prefix,))
             if os.path.dirname(p) == dirpath]
    gone = [p for p in known if p not in present]
    if gone:
        with write_txn(con):
            for p in gone:
                con.execute("DELETE FROM records WHERE source_path=?", (p,))
                con.execute("DELETE FROM files WHERE source_path=?", (p,))


JOB_SEED_DEPTH = 4  # job folders: depth 2 under PROJECTS, 3 under Archives; one level of slack

# Subtrees that never hold TBC projects or exports; not descended into. TBC's own "<job> Files", HistoryLog,
# InternalData and ChangeLog folders hold photos and logs, not points.
SKIP_DIRS = re.compile(r"(?i)^(2-UAV|UAV|Photos?|Pictures|Images?|Imagery|Ortho.*|Lidar|LAS|DWG|DGN|"
                       r"HistoryLog|InternalData|ChangeLog|\..*)$|\sFiles$")


# TBC project internals inside a TBC folder: no points, many subfolders.
TBC_INTERNAL = re.compile(r"(?i)^(Adjust|Alignments|RoadLink.*|Reports|files)$|\.job$")


def walk(top):
    """os.walk without per-folder link and stat calls (slow on a network share): uses what scandir returns.
    Yields (dirpath, dirnames, filenames, mtime); prune dirnames in place to skip subtrees."""
    try:
        stack = [(top, os.stat(top).st_mtime)]
    except OSError:
        return
    while stack:
        d, mtime = stack.pop()
        try:
            entries = list(os.scandir(d))
        except OSError:
            continue
        subs = {e.name: e for e in entries if e.is_dir(follow_symlinks=False)}
        dirnames = list(subs)
        yield d, dirnames, [e.name for e in entries if e.name not in subs], mtime
        for name in reversed(dirnames):
            try:
                stack.append((subs[name].path, subs[name].stat(follow_symlinks=False).st_mtime))
            except OSError:
                pass


# Levels below a crawl root searched for a TBC folder (jobs sit 2 deep under PROJECTS, 3 under Archives;
# TBC folders 1-3 below the job). Folders named like TBC deeper than this are still entered.
SEARCH_DEPTH = 6


def in_tbc_folder(dirpath, top):
    """Stahly keeps TBC projects and exports under a folder named like "TBC" (1-TBC, TBC, TBC INFT TEMPLATE)."""
    return "tbc" in os.path.relpath(dirpath, top).lower()


def seed_job_folders(con, top):
    """Record each job folder under top as pending (if not yet known) so coverage counts folders the crawl
    has not reached yet; drop pending folders that no longer exist."""
    found, level = [], [top]
    for _ in range(JOB_SEED_DEPTH):
        deeper = []
        for d in level:
            try:
                subs = [e.path for e in os.scandir(d) if e.is_dir()]
            except OSError:
                continue
            for p in subs:
                is_job_root = job_number(os.path.join(p, "x")) and not job_number(os.path.join(d, "x"))
                (found if is_job_root else deeper).append(p)
        level = deeper
    prefix = os.path.join(top, "")
    stale = [p for (p,) in con.execute("SELECT dir_path FROM folders WHERE status='pending' AND dir_path LIKE ? || '%'",
                                         (prefix,)) if not os.path.isdir(p)]
    with write_txn(con):
        con.executemany("INSERT OR IGNORE INTO folders VALUES (?, NULL, 'pending')", [(p,) for p in found])
        con.executemany("DELETE FROM folders WHERE dir_path=?", [(p,) for p in stale])


def cmd_index(args):
    """Catch-up crawl. A folder whose date modified matches the stored one (status 'done') is skipped;
    a folder is marked done only after all its source files are written, so a stopped run resumes there."""
    con = connect(args.db)
    deadline = None if args.budget is None else time.monotonic() + args.budget
    stats = {"folders_read": 0, "folders_skipped": 0, "files_read": 0, "complete": True, "stopped": None}

    def out_of_time():
        if deadline is not None and time.monotonic() >= deadline:
            stats["stopped"] = "budget"
        elif args.max_files is not None and stats["files_read"] >= args.max_files:
            stats["stopped"] = "max_files"
        return stats["stopped"] is not None

    for top in args.roots:
        seed_job_folders(con, top)
    for top in args.roots:
        for dirpath, dirnames, files, mtime in walk(top):
            in_tbc = in_tbc_folder(dirpath, top)
            depth = 0 if dirpath == top else os.path.relpath(dirpath, top).count(os.sep) + 1
            # outside TBC folders, descend only to SEARCH_DEPTH looking for one; inside, skip TBC internals
            dirnames[:] = [d for d in dirnames if not SKIP_DIRS.search(d)
                           and (not TBC_INTERNAL.search(d) if in_tbc
                                else depth < SEARCH_DEPTH or "tbc" in d.lower())]
            row = con.execute("SELECT mtime, status FROM folders WHERE dir_path=?", (dirpath,)).fetchone()
            if row is None and not in_tbc:
                continue  # sources live only under a folder named like "TBC"; job seeds still get marked done
            try:  # a fresh stat: NTFS can lag a child folder's date in its parent's listing
                mtime = os.stat(dirpath).st_mtime
            except OSError:
                continue
            if row == (mtime, "done"):
                stats["folders_skipped"] += 1
                continue
            with write_txn(con):
                con.execute("INSERT OR REPLACE INTO folders VALUES (?,?,?)", (dirpath, mtime, "pending"))
            if out_of_time():  # leave this folder pending so coverage shows it
                break
            sources = [os.path.join(dirpath, fn) for fn in files if os.path.splitext(fn)[1].lower() in PARSERS]
            forget_missing(con, dirpath, set(sources))
            for path in sources:
                if out_of_time():
                    break
                index_file(con, path)
                stats["files_read"] += 1
            if stats["stopped"]:
                break
            with write_txn(con):
                con.execute("UPDATE folders SET status='done' WHERE dir_path=? AND mtime=?", (dirpath, mtime))
            stats["folders_read"] += 1
        if stats["stopped"]:
            break
    stats["complete"] = stats["stopped"] is None
    with write_txn(con):
        con.execute("INSERT OR REPLACE INTO meta VALUES ('last_run_complete', ?)", (str(stats["complete"]),))
        if stats["complete"]:
            con.execute("INSERT OR REPLACE INTO meta VALUES ('last_complete_run', ?)",
                        (time.strftime("%Y-%m-%dT%H:%M:%S"),))
    con.close()
    json.dump(stats, sys.stdout)


def coverage(con):
    meta = dict(con.execute("SELECT key, value FROM meta"))
    done, pending = (con.execute("SELECT COUNT(*) FROM folders WHERE status=?", (s,)).fetchone()[0]
                     for s in ("done", "pending"))
    return {"folders_indexed": done, "folders_pending": pending,
            "complete": meta.get("last_run_complete") == "True" and pending == 0,
            "last_complete_run": meta.get("last_complete_run")}


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


COLS = ("source_path, job_number, point_name, recorded, feature_code, description, kind, flags, "
        "locator_lat, locator_lon, coord_system, date, mark_id")


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
    rows = con.execute(f"SELECT {COLS} FROM records WHERE locator_lat BETWEEN ? AND ? AND locator_lon BETWEEN ? AND ?",
                       (box[0] - dlat, box[1] + dlat, box[2] - dlon, box[3] + dlon)).fetchall()
    return query, rows, dist


def group_duplicates(results):
    """Collapse copies of one mark (same mark_id, decided at index time); every copy listed in `sources`."""
    groups = {}
    for r in results:
        groups.setdefault(r.pop("mark_id"), []).append(r)
    out = []
    for g in groups.values():
        primary = max(g, key=lambda r: (len(r["description"]), -(r["distance_mi"] or 0)))
        merged = dict(primary)
        merged["distance_mi"] = min((r["distance_mi"] for r in g), default=None) if primary["distance_mi"] is not None else None
        merged["flags"] = sorted({f for r in g for f in r["flags"]})
        merged["sources"] = [{k: r[k] for k in ("source_path", "job_number", "point_name", "recorded", "date", "coord_system")}
                             for r in g]
        out.append(merged)
    return out


def _file_lists(con, jobs):
    """(failed, skipped/partial) files in the given jobs, plus whole-index totals of each."""
    rows = con.execute("SELECT source_path, job_number, status, error FROM files "
                       "WHERE status IN ('failed', 'skipped', 'partial')").fetchall()
    failed = [{"source_path": p, "error": e} for p, j, st, e in rows if st == "failed" and j in jobs]
    skipped = [{"source_path": p, "status": st, "reason": e} for p, j, st, e in rows if st != "failed" and j in jobs]
    n_failed = sum(st == "failed" for _, _, st, _ in rows)
    return failed, skipped, n_failed, len(rows) - n_failed


def cmd_search(args):
    con = connect(args.db)
    query, rows, dist = _candidates(con, args)
    results, jobs = [], {args.job} if args.job else set()
    for (src, job, name, recorded, code, desc, kind, flags, lat, lon, cs, date, mark) in rows:
        d = None
        if dist is not None:
            d = dist(lat, lon)
            if d > args.radius:
                continue
            d = round(d, 3)
        jobs.add(job)
        if kind == "other" and not args.all:
            continue
        results.append({
            "kind": kind, "distance_mi": d, "point_name": name, "feature_code": code,
            "description": desc, "recorded": recorded, "flags": json.loads(flags),
            "job_number": job, "source_path": src, "coord_system": cs, "date": date,
            "locator": {"lat": lat, "lon": lon, "label": LOCATOR_LABEL}, "mark_id": mark,
        })
    results = group_duplicates(results)
    results.sort(key=lambda r: (KIND_RANK[r["kind"]], r["distance_mi"] or 0, r["point_name"] or ""))
    failed, skipped, failed_total, skipped_total = _file_lists(con, jobs - {None})
    json.dump({"query": query, "results": results,
               "unparsed_files": failed, "unparsed_total": failed_total,
               "skipped_files": skipped, "skipped_total": skipped_total,
               "coverage": coverage(con)}, sys.stdout, indent=1)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("index", help="crawl roots for .jxl/.vce/.csv files into the control index")
    i.add_argument("roots", nargs="+")
    i.add_argument("--db", help="SQLite control index file (default: CONTROL_INDEX_DB env, then config.json)")
    i.add_argument("--budget", type=float, help="seconds; stop cleanly at the limit, next run resumes")
    i.add_argument("--max-files", type=int, help="stop after reading N source files, next run resumes")
    s = sub.add_parser("search", help="records within a radius, ranked kind then distance (JSON)")
    s.add_argument("lat", type=float, nargs="?")
    s.add_argument("lon", type=float, nargs="?")
    s.add_argument("--kml", help="limits KML: radius measured from the polygon edge (0 inside)")
    s.add_argument("--job", help="job number, e.g. 2071-07D26: every record of that job")
    s.add_argument("--radius", type=float, default=1.0, help="miles (default 1)")
    s.add_argument("--all", action="store_true", help="include kind 'other' (non-control points)")
    s.add_argument("--db")
    w = sub.add_parser("where-db", help="print the database path that would be used")
    w.add_argument("--db")
    args = ap.parse_args(argv)
    args.db = resolve_db(args.db)
    if args.cmd == "where-db":
        print(args.db)
        return
    {"index": cmd_index, "search": cmd_search}[args.cmd](args)


if __name__ == "__main__":
    main()
