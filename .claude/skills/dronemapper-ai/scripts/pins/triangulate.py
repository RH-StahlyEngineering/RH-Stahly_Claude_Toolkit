"""Triangulate each target from its pins and report per-pin reprojection error (in memory, read-only).

Run: metashape.exe -r triangulate.py --psz <job>.snapshot.psz --pins pins.json --out tri.json

pins.json: {target: {photo_label: [u, v]}}. Writes {target: {"rms_px", "max_px", "errs": {photo: px},
"position_crs": [x, y, z]}}. Agreement is not correctness: pins that share one bias (every pick
on the same dark corner) still agree. Review the crops by eye (the pin page) before writing.
"""
import argparse, json, math, sys
import Metashape

ap = argparse.ArgumentParser()
ap.add_argument("--psz", required=True)
ap.add_argument("--pins", required=True)
ap.add_argument("--out", required=True)
a = ap.parse_args([x for x in sys.argv[1:] if x != "--"])
pins = json.load(open(a.pins, encoding="utf-8"))
res = {}
try:
    doc = Metashape.Document()
    doc.open(a.psz, read_only=True, ignore_lock=True)  # never saved
    ch = doc.chunk
    cams = {c.label: c for c in ch.cameras}
    for t, pk in pins.items():
        m = ch.addMarker()
        for lab, (u, v) in pk.items():
            m.projections[cams[lab]] = Metashape.Marker.Projection(Metashape.Vector([u, v]), True)
        p = m.position
        g = ch.crs.project(ch.transform.matrix.mulp(p))
        errs = {}
        for lab, (u, v) in pk.items():
            q = cams[lab].project(p)
            errs[lab] = round(math.hypot(q.x - u, q.y - v), 2)
        res[t] = {"rms_px": round(math.sqrt(sum(e * e for e in errs.values()) / len(errs)), 2),
                  "max_px": max(errs.values()), "errs": errs, "position_crs": [g.x, g.y, g.z]}
except Exception as ex:
    res["error"] = repr(ex)
json.dump(res, open(a.out, "w", encoding="utf-8"), indent=1)
Metashape.app.quit()
