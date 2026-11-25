"""Refine hand picks to the X-junction of a checker target by a quadratic saddle fit.

Run: python -I refine.py --intake <job intake dir> --picks picks.json --out refined.json [--half 5]

picks.json: {target: {photo_label: [u, v]}}. The junction is a saddle of the blurred
intensity: fit I = ax^2 + bxy + cy^2 + dx + ey + f over a (2*half+1)^2 window, step to
grad = 0, repeat. Writes {target: {photo: {"pick", "saddle", "moved_px", "ok"}}}; ok is false
when no saddle is found (the pick is then not on a junction). Use --half 5 for ~20 px
panels, 7 for ~60 px panels. Reads photos only.
"""
import argparse, json, math
import numpy as np
from PIL import Image, ImageFilter

ap = argparse.ArgumentParser()
ap.add_argument("--intake", required=True)
ap.add_argument("--picks", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--half", type=int, default=5)
a = ap.parse_args()
R = a.half
picks = json.load(open(a.picks, encoding="utf-8"))
out = {}
for t, pk in picks.items():
    out[t] = {}
    for lab, (u0, v0) in pk.items():
        im = Image.open(rf"{a.intake}\{lab}.jpg").convert("L")
        L, T = int(u0) - 30, int(v0) - 30
        arr = np.asarray(im.crop((L, T, L + 61, T + 61)).filter(ImageFilter.GaussianBlur(1.5)), dtype=float)
        x, y, ok = u0 - L, v0 - T, False
        for _ in range(20):
            xi, yi = int(round(x)), int(round(y))
            if not (R <= xi < 61 - R and R <= yi < 61 - R):
                ok = False
                break
            ys, xs = np.mgrid[-R:R + 1, -R:R + 1]
            X, Y = xs.ravel().astype(float), ys.ravel().astype(float)
            A = np.column_stack([X * X, X * Y, Y * Y, X, Y, np.ones_like(X)])
            ca, cb, cc, cd, ce, _f = np.linalg.lstsq(A, arr[yi - R:yi + R + 1, xi - R:xi + R + 1].ravel(), rcond=None)[0]
            H = np.array([[2 * ca, cb], [cb, 2 * cc]])
            if np.linalg.det(H) >= 0:  # not a saddle: no junction here
                ok = False
                break
            s = np.linalg.solve(H, -np.array([cd, ce]))
            nx, ny, ok = xi + s[0], yi + s[1], True
            done = math.hypot(nx - x, ny - y) < 0.01
            x, y = nx, ny
            if done:
                break
        u, v = L + x, T + y
        out[t][lab] = {"pick": [u0, v0], "saddle": [round(float(u), 2), round(float(v), 2)],
                       "moved_px": round(math.hypot(u - u0, v - v0), 2), "ok": ok}
json.dump(out, open(a.out, "w", encoding="utf-8"), indent=1)
for t in out:
    for lab, r in out[t].items():
        print(t, lab, r["saddle"], "moved", r["moved_px"], "ok" if r["ok"] else "NO SADDLE")
