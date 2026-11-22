"""CSV point exports (control-index #7), e.g. TBC "Export to CAD": name,N,E,Z,desc.

A CSV carries no coordinate system, so it is indexed only when a sibling project (.vce/.jxl anywhere in the
same job folder tree) supplies one. Units are confirmed by matching point names shared with that project
(international/US survey foot or metre); without a shared point the file is skipped, never guessed.
"""
import csv
import os
import statistics

UNITS = {"ift": 0.3048, "usft": 1200 / 3937, "m": 1.0}
UNIT_TOLERANCE_M = 10.0


class Skipped(Exception):
    """File deliberately not indexed; the message says why. Listed in search output."""


def _job_root(path, job_number):
    job, root, d = job_number(path), None, os.path.dirname(path)
    if job is None:
        return None
    while job_number(os.path.join(d, "x")) == job:
        root, parent = d, os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return root


def _rows(path):
    with open(path, newline="", encoding="utf-8-sig", errors="replace") as f:
        for rec in csv.reader(f):
            if len(rec) < 3:
                continue
            try:
                n, e = float(rec[1]), float(rec[2])
            except ValueError:
                continue  # header / non-point line
            yield rec[0].strip(), n, e, (rec[4].strip() if len(rec) > 4 else "")


def _unit(rows, pts):
    shared = [(n, e, pts[name]) for name, n, e, _ in rows if name in pts]
    if not shared:
        return None
    best = None
    for unit, f in UNITS.items():
        err = statistics.median(((n * f - gn) ** 2 + (e * f - ge) ** 2) ** 0.5 for n, e, (gn, ge) in shared)
        if err < UNIT_TOLERANCE_M and (best is None or err < best[1]):
            best = (f, err)
    return best and best[0]


def parse_csv(path, contexts, job_number, locator_decimals=4):
    """contexts: {ext: fn(project path) -> (Grid or None, {name: (N, E) metres})}."""
    rows = list(_rows(path))
    if not rows:
        raise Skipped("no point rows (expected name,N,E,Z,desc)")
    root = _job_root(path, job_number)
    if root is None:
        raise Skipped("not in a job folder: no sibling project to give the coordinate system")
    tried = []
    for dirpath, _dirs, files in os.walk(root):
        for fn in sorted(files):
            ext = os.path.splitext(fn)[1].lower()
            if ext not in contexts:
                continue
            try:
                grid, pts = contexts[ext](os.path.join(dirpath, fn))
            except Exception:  # noqa: BLE001 - an unreadable sibling just isn't a context
                continue
            if grid is None:
                continue
            tried.append(fn)
            f = _unit(rows, pts)
            if f is None:
                continue
            for name, n, e, desc in rows:
                lat, lon = grid.to_latlon(n * f, e * f)
                yield {"point_name": name, "recorded": desc,
                       "lat": round(lat, locator_decimals), "lon": round(lon, locator_decimals),
                       "coord_system": grid.coord_system, "date": None, "flags": list(grid.flags)}
            return
    raise Skipped("coordinate system unknown: no sibling project" if not tried else
                  f"coordinate system/units unconfirmed: no points shared with {', '.join(tried)}")
