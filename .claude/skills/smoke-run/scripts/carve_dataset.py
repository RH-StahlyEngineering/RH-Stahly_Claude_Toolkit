"""Carve alignment-viable photo subsets from an existing PSX chunk for smoke tests.

Reads camera reference positions straight out of a PSX chunk (no Metashape
needed), compares them against JXL aerial-target coordinates, and copies
selected source photos into a flat folder.

Modes:
  sessions            List flight sessions with extent, spacing, and pass
                      structure (n*spacing vs corridor span) — run this FIRST.
  near --targets ...  Photos whose camera is within --radius of any named target.
  far  --min-dist ... Photos farther than min-dist from ALL targets (no-target set).
  session --names ... All photos of the named session prefixes, unthinned.

Lessons baked in (2026-07-22 Fergus smoke run):
  - JXL Grid values are METERS even when DisplaySettings says feet; PSX camera
    references may be in state-plane FEET. --cam-unit-ft (default) converts.
  - NEVER thin a single-pass session; selection here never thins.
  - Proximity-only picks create disconnected alignment islands; prefer
    `session` mode over `near` for the aligned set.

Usage:
  python carve_dataset.py sessions --psx PATH [--chunk-id N] --jxl PATH
  python carve_dataset.py session  --psx PATH --jxl PATH --names 20260619175,20260619182 --out C:\\smoke\\setA_gcp
  python carve_dataset.py near     --psx PATH --jxl PATH --targets 47,48,49,50 --radius 80 --out DIR
  python carve_dataset.py far      --psx PATH --jxl PATH --min-dist 500 --limit 20 --out DIR
"""

from __future__ import annotations

import argparse
import math
import os
import re
import shutil
import sys
import xml.etree.ElementTree as ET
import zipfile

FT = 0.3048


def load_targets(jxl_path: str) -> dict[str, tuple[float, float]]:
    root = ET.parse(jxl_path).getroot()
    red = root.find("Reductions")
    out: dict[str, tuple[float, float]] = {}
    if red is None:
        return out
    for p in red.findall("Point"):
        name = p.findtext("Name")
        e, n = p.findtext("Grid/East"), p.findtext("Grid/North")
        if name and e and n:
            out[name] = (float(e), float(n))  # meters
    return out


def load_cameras(psx_path: str, chunk_id: str | None, cam_unit_ft: bool):
    """Yield (label, easting_m, northing_m, source_photo_abspath)."""
    files_dir = os.path.splitext(psx_path)[0] + ".files"
    doc = zipfile.ZipFile(os.path.join(files_dir, "project.zip")).read("doc.xml").decode()
    if chunk_id is None:
        m = re.search(r'active_id="(\d+)"', doc)
        chunk_id = m.group(1) if m else "0"
    chunk_dir = os.path.join(files_dir, chunk_id)
    chunk_xml = zipfile.ZipFile(os.path.join(chunk_dir, "chunk.zip")).read("doc.xml").decode()
    frame_xml = zipfile.ZipFile(os.path.join(chunk_dir, "0", "frame.zip")).read("doc.xml").decode()
    cam_paths = dict(re.findall(r'<camera camera_id="(\d+)">\s*<photo path="([^"]+)"', frame_xml))
    base = os.path.abspath(os.path.join(chunk_dir, "0"))
    unit = FT if cam_unit_ft else 1.0
    root = ET.fromstring(chunk_xml)
    for c in root.findall(".//cameras//camera"):
        r = c.find("reference")
        if r is None or r.get("x") is None:
            continue
        p = cam_paths.get(c.get("id", ""))
        if not p:
            continue
        yield (
            c.get("label", "?"),
            float(r.get("x")) * unit,
            float(r.get("y")) * unit,
            os.path.normpath(os.path.join(base, p)),
        )


def session_key(label: str) -> str:
    """DJI_20260619175348_0201 -> 20260619175 (10-min flight-session bucket)."""
    m = re.match(r"[A-Za-z]+_(\d{11})", label)
    return m.group(1) if m else label[:15]


def copy_set(rows: list[tuple[str, str]], out_dir: str) -> None:
    os.makedirs(out_dir, exist_ok=True)
    missing = 0
    for _label, src in rows:
        if os.path.exists(src):
            shutil.copy2(src, out_dir)
        else:
            missing += 1
            print(f"MISSING {src}")
    print(f"copied {len(rows) - missing} photos to {out_dir} ({missing} missing)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=["sessions", "session", "near", "far"])
    ap.add_argument("--psx", required=True)
    ap.add_argument("--chunk-id", default=None, help="chunk dir id (default: active chunk)")
    ap.add_argument("--jxl", required=True)
    ap.add_argument("--cam-unit-ft", action="store_true", default=True)
    ap.add_argument("--cam-unit-m", dest="cam_unit_ft", action="store_false")
    ap.add_argument("--targets", default="", help="comma-separated target names (near mode)")
    ap.add_argument("--names", default="", help="comma-separated session prefixes (session mode)")
    ap.add_argument("--radius", type=float, default=80.0, help="meters (near mode)")
    ap.add_argument("--min-dist", type=float, default=500.0, help="meters (far mode)")
    ap.add_argument("--limit", type=int, default=0, help="cap photo count (far mode; 0=all)")
    ap.add_argument("--out", default="", help="destination folder (copy modes)")
    a = ap.parse_args()

    targets = load_targets(a.jxl)
    cams = list(load_cameras(a.psx, a.chunk_id, a.cam_unit_ft))
    if not cams:
        print("no referenced cameras found", file=sys.stderr)
        return 2

    def dmin(e: float, n: float, names=None) -> float:
        pts = [t for k, t in targets.items() if names is None or k in names]
        return min(math.hypot(e - te, n - tn) for te, tn in pts) if pts else float("inf")

    if a.mode == "sessions":
        by: dict[str, list] = {}
        for row in cams:
            by.setdefault(session_key(row[0]), []).append(row)
        for k in sorted(by):
            s = sorted(by[k])
            es, ns = [r[1] for r in s], [r[2] for r in s]
            steps = [math.hypot(s[i + 1][1] - s[i][1], s[i + 1][2] - s[i][2]) for i in range(len(s) - 1)]
            med = sorted(steps)[len(steps) // 2] if steps else 0.0
            span = math.hypot(max(es) - min(es), max(ns) - min(ns))
            track = sum(steps)
            passes = track / span if span > 1 else 0.0
            warn = "  SINGLE-PASS - NEVER THIN" if passes < 1.6 else ""
            print(
                f"{k}  n={len(s):4d}  E:{min(es):.0f}-{max(es):.0f}  N:{min(ns):.0f}-{max(ns):.0f}"
                f"  med-step={med:.1f}m  track/span={passes:.1f}{warn}"
            )
        return 0

    if not a.out:
        print("--out required for copy modes", file=sys.stderr)
        return 2

    if a.mode == "session":
        names = {x.strip() for x in a.names.split(",") if x.strip()}
        sel = [(r[0], r[3]) for r in cams if session_key(r[0]) in names]
    elif a.mode == "near":
        names = {x.strip() for x in a.targets.split(",") if x.strip()} or None
        sel = [(r[0], r[3]) for r in cams if dmin(r[1], r[2], names) <= a.radius]
    else:  # far
        rows = [(dmin(r[1], r[2]), r[0], r[3]) for r in cams]
        rows = sorted((x for x in rows if x[0] > a.min_dist), reverse=True)
        if a.limit:
            rows = rows[: a.limit]
        sel = [(label, p) for _d, label, p in rows]

    if not sel:
        print("selection is empty — check units/targets", file=sys.stderr)
        return 2
    copy_set(sorted(sel), a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
