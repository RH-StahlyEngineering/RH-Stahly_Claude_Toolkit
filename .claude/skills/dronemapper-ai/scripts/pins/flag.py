"""Decide which pins the saddle fit can settle and which go to RH (the data-driven review subset).

Run: python -I flag.py --out flags.json \
       --job "mcd|C:\\metashape-root\\intake\\<job>|refined.json|targets.json|6" [--job ...]
       [--tri tri_mcd.json --tri tri_rf.json]

--job fields: tag | intake dir | refine.py output | project_targets.py output | half-size of
the panel in px (about a quarter of its width: 6 for ~20 px panels, 16 for ~60 px).
--tri (optional, triangulate.py output of the auto pins) adds the disagreement check.

A photo goes to RH when: no saddle; the panel is shadowed (its light pair or dark pair
differ by more than 0.30 of the light/dark contrast); it is blurred (steepest brightness step
under 0.2 of the contrast per pixel); its centre is within 150 px of the frame edge; the fit
is more than 12 px from the surveyed projection (wrong object); pick and fit disagree by more
than 4 px; or the fit sits more than 1.5 px from the target's triangulated position.
Thresholds come from RH's 19 placements on SB536 (2026-11-20): together they caught every fit
RH moved by more than 1.4 px, and both photos RH marked not usable.
Writes {pin_id: {"job", "target", "photo", "fit", "reasons": [...]}}; empty reasons = auto.
"""
import argparse, json, math
import numpy as np
from PIL import Image, ImageFilter

ASYM_MAX, SHARP_MIN, EDGE_PX, FAR_PX, DISAGREE_PX, TRI_PX = 0.30, 0.20, 150, 12, 4, 1.5

ap = argparse.ArgumentParser()
ap.add_argument("--out", required=True)
ap.add_argument("--job", action="append", required=True)
ap.add_argument("--tri", action="append", default=[])
a = ap.parse_args()


def panel_quality(path, u, v, r):
    """(asymmetry, sharpness) of the panel around the junction (u, v), radius r."""
    im = Image.open(path).convert("L")
    w, h = im.size
    L, T = int(u) - r - 2, int(v) - r - 2
    box = (L, T, L + 2 * r + 5, T + 2 * r + 5)
    a_ = np.asarray(im.crop(box).filter(ImageFilter.GaussianBlur(0.8)), dtype=float)
    raw = np.asarray(im.crop(box), dtype=float)
    ys, xs = np.mgrid[0:a_.shape[0], 0:a_.shape[1]]
    dx, dy = xs - (u - L), ys - (v - T)
    ring = (np.abs(dx) > 2) & (np.abs(dy) > 2) & (np.abs(dx) < r) & (np.abs(dy) < r)
    q = [a_[ring & (dx > 0) & (dy < 0)].mean(), a_[ring & (dx < 0) & (dy < 0)].mean(),
         a_[ring & (dx < 0) & (dy > 0)].mean(), a_[ring & (dx > 0) & (dy > 0)].mean()]
    light, dark = ((q[0], q[2]), (q[1], q[3])) if q[0] + q[2] > q[1] + q[3] else ((q[1], q[3]), (q[0], q[2]))
    contrast = max(1.0, (sum(light) - sum(dark)) / 2)
    gy, gx = np.gradient(raw)
    near = (np.abs(dx) < r * 0.6) & (np.abs(dy) < r * 0.6)
    sharp = float(np.percentile(np.hypot(gx, gy)[near], 95)) / contrast
    return max(abs(light[0] - light[1]), abs(dark[0] - dark[1])) / contrast, sharp, (w, h)


tri = {}
for p in a.tri:
    for t, r in json.load(open(p, encoding="utf-8")).items():
        if isinstance(r, dict):
            for lab, e in r.get("errs", {}).items():
                tri[(t, lab)] = e
out = {}
for spec in a.job:
    tag, intake, refp, projp, half = spec.split("|")
    ref = json.load(open(refp, encoding="utf-8"))
    proj = {t: {h[0]: (h[2], h[3]) for h in hs} for t, hs in json.load(open(projp, encoding="utf-8"))["targets"].items()}
    for t, pk in ref.items():
        for lab, r in pk.items():
            reasons = []
            fu, fv = r["saddle"]
            if not r["ok"]:
                reasons.append("no saddle")
            else:
                asym, sharp, (w, h) = panel_quality(rf"{intake}\{lab}.jpg", fu, fv, int(half))
                if asym > ASYM_MAX:
                    reasons.append(f"shadowed ({asym:.2f})")
                if sharp < SHARP_MIN:
                    reasons.append(f"blurred ({sharp:.2f})")
                if min(fu, fv, w - fu, h - fv) < EDGE_PX:
                    reasons.append("near frame edge")
                pp = proj.get(t, {}).get(lab)
                if pp and math.hypot(fu - pp[0], fv - pp[1]) > FAR_PX:
                    reasons.append("far from projection (wrong object?)")
            if math.hypot(r["pick"][0] - fu, r["pick"][1] - fv) > DISAGREE_PX:
                reasons.append(f"pick and fit disagree >{DISAGREE_PX} px")
            if tri.get((t, lab), 0) > TRI_PX:
                reasons.append(f"fit {tri[(t, lab)]:.1f} px off the other photos")
            out[f"{tag}_{t}_{lab}"] = {"job": tag, "target": t, "photo": lab, "fit": r["saddle"], "reasons": reasons}
json.dump(out, open(a.out, "w", encoding="utf-8"), indent=1)
n = sum(1 for v in out.values() if v["reasons"])
print(f"{len(out)} pins: {len(out) - n} auto, {n} for RH")
