"""Project every JXL target into the photos of a held job's snapshot (read-only).

Run: metashape.exe -r project_targets.py --psz <job>.snapshot.psz --jxl <staged.jxl> --out targets.json

Writes {"targets": {name: [[photo_label, photo_path, u, v], ...]}, "auto": {marker: {...}}}:
every photo whose frame holds the target's surveyed position (15 px margin), and each
auto-detected "point N" marker mapped to its nearest target. Opens the snapshot read-only.
"""
import argparse, json, math, sys
import xml.etree.ElementTree as ET
import Metashape

ap = argparse.ArgumentParser()
ap.add_argument("--psz", required=True)
ap.add_argument("--jxl", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--prefixes", default="AT,GCP,CP")
ap.add_argument("--margin", type=float, default=15.0)
a = ap.parse_args([x for x in sys.argv[1:] if x != "--"])

prefixes = tuple(p.strip().upper() for p in a.prefixes.split(","))
targets = {}
for pt in ET.parse(a.jxl).getroot().iter("Point"):
    g, code = pt.find("Grid"), (pt.findtext("Code") or "").strip().upper()
    if g is not None and g.findtext("East") and code.startswith(prefixes):
        # JXL Grid values are metres.
        targets[pt.findtext("Name")] = (float(g.findtext("East")), float(g.findtext("North")), float(g.findtext("Elevation")))

res = {"targets": {}, "auto": {}}
try:
    doc = Metashape.Document()
    doc.open(a.psz, read_only=True, ignore_lock=True)
    ch = doc.chunk
    wkt = ch.crs.wkt.lower()
    to_m = 1200 / 3937 if "us survey" in wkt else (0.3048 if "foot" in wkt else 1.0)
    T = ch.transform.matrix
    for name, (e, n, z) in targets.items():
        p = T.inv().mulp(ch.crs.unproject(Metashape.Vector([e / to_m, n / to_m, z / to_m])))
        hits = []
        for cam in ch.cameras:
            if cam.transform is None:
                continue
            uv = cam.project(p)
            m = a.margin
            if uv is not None and m <= uv.x < cam.sensor.width - m and m <= uv.y < cam.sensor.height - m:
                hits.append([cam.label, cam.photo.path, round(uv.x, 1), round(uv.y, 1)])
        res["targets"][name] = hits
    for mk in ch.markers:
        if mk.position is None:
            continue
        g = ch.crs.project(T.mulp(mk.position))
        best = min(targets, key=lambda k: math.hypot(g.x - targets[k][0] / to_m, g.y - targets[k][1] / to_m))
        d = math.hypot(g.x - targets[best][0] / to_m, g.y - targets[best][1] / to_m)
        res["auto"][mk.label] = {"nearest": best, "dist_crs_units": round(d, 3),
                                 "n_proj": sum(1 for _c, pr in mk.projections.items() if pr is not None)}
except Exception as ex:
    res["error"] = repr(ex)
json.dump(res, open(a.out, "w", encoding="utf-8"), indent=1)
Metashape.app.quit()
