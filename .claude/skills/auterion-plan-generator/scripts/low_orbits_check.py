"""Readback check for a low_orbits.py plan. Reads yaw (WP param4) and gimbal pitch (cmd 205) back out of
the .plan, casts each photo's centre ray, and reports (1) how far the ray points from its subject
(must be ~0 deg: subject centred) and (2) whether the ray reaches the subject or hits something first.
Writes <name>_check_top.png (aerial with rays) and <name>_check_profile.png.

Usage:  py low_orbits_check.py config.json
"""
import json, math, os, sys, io, urllib.request
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt

src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "low_orbits.py"), encoding="utf8").read()
exec(src.split("subjects = {}")[0])          # same config, grids and helpers as the builder
out = os.path.join(C["out_dir"], C["name"])
plan = json.load(open(out + ".plan")); dbg = json.load(open(out + "_dbg.json"))
pitch = -90; trig = False; shots = []
for it in plan["mission"]["items"]:
    c = it["command"]
    if c == 205: pitch = it["params"][0]
    elif c == 206: trig = it["params"][0] > 0
    elif c == 16 and trig:
        x, y = ll2utm.transform(it["params"][5], it["params"][4]); shots.append((x, y, it["params"][6], it["params"][3], pitch))
subj = []; groups = []
for k, st in dbg["subjects"].items():
    seq = st[1:] + [st[0]]; subj += [(s["sx"], s["sy"], s["sz"]) for s in seq]; groups += [k] * len(seq)
assert len(subj) == len(shots), (len(subj), len(shots))
off, reach = [], []
for (x, y, zz, yaw, pit), s in zip(shots, subj):
    d = np.array([math.sin(math.radians(yaw)) * math.cos(math.radians(pit)), math.cos(math.radians(yaw)) * math.cos(math.radians(pit)), math.sin(math.radians(pit))])
    v = np.array(s) - np.array([x, y, zz]); rng = np.linalg.norm(v)
    off.append(math.degrees(math.acos(np.clip(np.dot(d, v) / rng, -1, 1))))
    blocked = any(surf(*(np.array([x, y, zz]) + t * d)[:2]) > (zz + t * d[2]) + 0.3 for t in np.arange(1.0, rng - 2.0, 0.5))
    reach.append(not blocked)
groups = np.array(groups); off = np.array(off); reach = np.array(reach)
rep = {k: dict(photos=int((groups == k).sum()), max_off_centre_deg=round(float(off[groups == k].max()), 2),
               centre_ray_reaches_subject_pct=round(100 * float(reach[groups == k].mean()), 0)) for k in dbg["subjects"]}
print(json.dumps(rep, indent=1))
# ---- top view on an aerial whose extent is read back from the server (it stretches to fit) ----
xs = [s[0] for s in shots] + [dbg["home"][0]]; ys = [s[1] for s in shots] + [dbg["home"][1]]
lo0, la0 = utm2ll.transform(min(xs) - 30, min(ys) - 30); lo1, la1 = utm2ll.transform(max(xs) + 30, max(ys) + 30)
w = int(min(1600, (lo1 - lo0) / 2.5e-6)); h = int(w * (la1 - la0) / (lo1 - lo0))  # server returns 500 past ~2.5e-6 deg/px
# size matches the bbox aspect in degrees, so the server returns exactly the requested extent
url = f"https://services.arcgisonline.com/arcgis/rest/services/World_Imagery/MapServer/export?bbox={lo0},{la0},{lo1},{la1}&bboxSR=4326&imageSR=4326&size={w},{h}&format=png&f=image"
import subprocess  # urllib gets HTTP 500 from this server where curl succeeds
im = Image.open(io.BytesIO(subprocess.run(["curl", "-s", url], capture_output=True, check=True).stdout)).convert("RGB"); W_, H_ = im.size
ex = dict(xmin=lo0, xmax=lo1, ymin=la0, ymax=la1)
def px(xu, yu): lo, la = utm2ll.transform(xu, yu); return ((lo - ex["xmin"]) / (ex["xmax"] - ex["xmin"]) * W_, (ex["ymax"] - la) / (ex["ymax"] - ex["ymin"]) * H_)
dr = ImageDraw.Draw(im); f = ImageFont.truetype("arialbd.ttf", 20)
for (x, y, *_), s, r, g in zip(shots, subj, reach, groups):
    a, b = px(x, y), px(s[0], s[1]); dr.line([a, b], fill=(255, 255, 255) if r else (255, 60, 60), width=1)
    dr.ellipse([a[0] - 4, a[1] - 4, a[0] + 4, a[1] + 4], fill=(0, 255, 255) if g == "building" else (255, 200, 0), outline=(0, 0, 0))
hp = px(*dbg["home"][:2]); dr.rectangle([hp[0] - 9, hp[1] - 9, hp[0] + 9, hp[1] + 9], outline=(255, 0, 255), width=4)
dr.text((10, H_ - 30), "white = centre ray reaches subject, red = something in front; magenta = HOME", fill=(255, 255, 255), font=f, stroke_width=3, stroke_fill=(0, 0, 0))
im.save(out + "_check_top.png")
fig, axs = plt.subplots(len(dbg["subjects"]), 1, figsize=(11, 3.3 * len(dbg["subjects"])), squeeze=False)
for a_, k in zip(axs[:, 0], dbg["subjects"]):
    S = [s for s, g in zip(shots, groups) if g == k]; T = [s for s, g in zip(subj, groups) if g == k]; n = np.arange(len(S))
    a_.plot(n, [s[2] for s in S], "b-", label="drone"); a_.plot(n, [float(dtm(s[0], s[1])) for s in S], "g-", label="ground")
    a_.plot(n, [maxsurf_near(s[0], s[1]) for s in S], "k:", label="max surface + hazards"); a_.plot(n, [t[2] for t in T], "r.", label="aim")
    a2 = a_.twinx(); a2.plot(n, [s[4] for s in S], "m--", lw=.8); a2.set_ylabel("pitch", color="m"); a_.set_title(k); a_.legend(fontsize=7)
fig.tight_layout(); fig.savefig(out + "_check_profile.png", dpi=110)
