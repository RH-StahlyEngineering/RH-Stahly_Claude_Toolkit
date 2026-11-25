"""Write reviewed pins into a held job's snapshot (a hand-edit on a live job: RH approves first).

Run: metashape.exe -r write_pins.py --psz <job>.snapshot.psz --pins pins.json --map 22="point 1",20="point 2" --out result.json

pins.json: {target: {photo_label: [u, v]}}. --map names the snapshot marker each target goes on;
a target with no auto marker gets a new marker under the label given (use the next free
"point N", never the JXL name, so marker_loading matches it). Every existing projection on a
mapped marker is dropped first. Reports tie points before and after and the pinned counts.
Back up the .snapshot.psz/.snapshot.json pair first, and afterwards set "bytes" in
.snapshot.json to the new file size, or the bridge dispatches fresh and realigns.
"""
import argparse, json, sys
import Metashape

ap = argparse.ArgumentParser()
ap.add_argument("--psz", required=True)
ap.add_argument("--pins", required=True)
ap.add_argument("--map", required=True)
ap.add_argument("--out", required=True)
a = ap.parse_args([x for x in sys.argv[1:] if x != "--"])
mapping = dict(kv.split("=", 1) for kv in a.map.split(","))
mapping = {k.strip(): v.strip().strip('"') for k, v in mapping.items()}
pins = json.load(open(a.pins, encoding="utf-8"))
res = {}
try:
    doc = Metashape.Document()
    doc.open(a.psz, read_only=False)
    ch = doc.chunk
    res["tie_points_before"] = len(ch.tie_points.points)
    cams = {c.label: c for c in ch.cameras}
    mk = {m.label: m for m in ch.markers}
    for t, label in mapping.items():
        m = mk.get(label)
        if m is None:
            m = ch.addMarker()
            m.label = label
        for cam in list(m.projections.keys()):
            m.projections[cam] = None
        for lab, (u, v) in pins[t].items():
            m.projections[cams[lab]] = Metashape.Marker.Projection(Metashape.Vector([u, v]), True)
    doc.save()
    d2 = Metashape.Document()
    d2.open(a.psz, read_only=True)
    c2 = d2.chunk
    res["tie_points_after"] = len(c2.tie_points.points)
    res["markers_after"] = {m.label: sum(1 for _c, p in m.projections.items() if p is not None and p.pinned)
                            for m in c2.markers}
except Exception as ex:
    res["error"] = repr(ex)
json.dump(res, open(a.out, "w", encoding="utf-8"), indent=1)
Metashape.app.quit()
