"""Plot Fergus50_S09_AB v5 plan view (logarithmic spiral teardrop)."""
import json
import re
import math
import os
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon
from matplotlib.lines import Line2D

PLAN = r"C:/Users/rharbach.STAHLY/Documents/Auterion Mission Control/Missions/Fergus50_S09_AB.plan"
KML = r"C:/Users/rharbach.STAHLY/Downloads/HighwayCenterline.kml"
OUT = r"C:/Users/rharbach.STAHLY/Downloads/Fergus50_S09_AB_v5_planview.png"

# ---------- load plan ----------
with open(PLAN) as f:
    plan = json.load(f)
items = plan["mission"]["items"]
wp = []  # (idx, lat, lon)
for i, it in enumerate(items):
    if i < 2:
        wp.append((i, None, None))
        continue
    p = it.get("params", [])
    wp.append((i, p[4], p[5]))

# ---------- load KML highway ----------
with open(KML) as f:
    txt = f.read()
coords_block = re.search(r"<coordinates>(.*?)</coordinates>", txt, re.DOTALL).group(1)
hwy = []
for tok in coords_block.strip().split():
    parts = tok.split(",")
    lon, lat = float(parts[0]), float(parts[1])
    hwy.append((lat, lon))

# ---------- projection reference: mean of highway points ----------
ref_lat = sum(p[0] for p in hwy) / len(hwy)
ref_lon = sum(p[1] for p in hwy) / len(hwy)
M_PER_DEG_LAT = 111320.0
m_per_deg_lon = M_PER_DEG_LAT * math.cos(math.radians(ref_lat))


def proj(lat, lon):
    e = (lon - ref_lon) * m_per_deg_lon
    n = (lat - ref_lat) * M_PER_DEG_LAT
    return e, n


hwy_xy = np.array([proj(*p) for p in hwy])  # (N,2): east, north
wp_xy = []
for i, lat, lon in wp:
    if lat is None:
        wp_xy.append((i, None, None))
    else:
        e, n = proj(lat, lon)
        wp_xy.append((i, e, n))


def W(i):
    return np.array([wp_xy[i][1], wp_xy[i][2]])


# ---------- corridor swath: highway buffered ±75 m, from A_along to B_along ----------
def nearest_idx(target_xy, line_xy):
    d2 = np.sum((line_xy - target_xy) ** 2, axis=1)
    return int(np.argmin(d2))


A_xy = W(2)   # K1
B_xy = W(29)  # anchor
idx_A = nearest_idx(A_xy, hwy_xy)
idx_B = nearest_idx(B_xy, hwy_xy)
i0, i1 = sorted([idx_A, idx_B])
seg = hwy_xy[i0:i1 + 1]


def buffer_polygon(line, dist):
    left, right = [], []
    for k in range(len(line)):
        if k == 0:
            tx = line[1] - line[0]
        elif k == len(line) - 1:
            tx = line[-1] - line[-2]
        else:
            tx = line[k + 1] - line[k - 1]
        L = np.linalg.norm(tx)
        if L < 1e-9:
            continue
        tx /= L
        nx = np.array([-tx[1], tx[0]])  # left normal
        left.append(line[k] + nx * dist)
        right.append(line[k] - nx * dist)
    return np.array(left + right[::-1])


corridor_poly = buffer_polygon(seg, 75.0)

# ---------- geometry computations ----------
anchor = W(29)               # item 29
last_survey = W(18)          # item 18
t1_end = W(19)               # tangent-1 end / spiral entry
spiral_end = W(28)           # item 28
closing_end = W(30)          # item 30
loiter = W(31)               # item 31

tangent1_len = float(np.linalg.norm(t1_end - last_survey))
tangent2_len = float(np.linalg.norm(anchor - spiral_end))
closing_len = float(np.linalg.norm(closing_end - anchor))

# Spiral arc points: items 19 .. 28
spiral_pts = np.array([W(i) for i in range(19, 29)])
spiral_arc_len = float(np.sum(np.linalg.norm(np.diff(spiral_pts, axis=0), axis=1)))

# R_start ~ tangent-1 (offset of entry from last_survey along tan_B)
R_start = tangent1_len
# R_end ~ distance from anchor to spiral end
R_end = tangent2_len

# Closing transect FOV footprint (100 m wide × 126.5 m long)
trans_dir = (closing_end - anchor) / closing_len
trans_perp = np.array([-trans_dir[1], trans_dir[0]])  # 90° CCW
fov_width = 100.0
fov_length = 126.5
mid = (anchor + closing_end) / 2.0
fov_corners = np.array([
    mid + trans_dir * (fov_length / 2) + trans_perp * (fov_width / 2),
    mid + trans_dir * (fov_length / 2) - trans_perp * (fov_width / 2),
    mid - trans_dir * (fov_length / 2) - trans_perp * (fov_width / 2),
    mid - trans_dir * (fov_length / 2) + trans_perp * (fov_width / 2),
])

# ---------- plot ----------
fig, (axL, axR) = plt.subplots(1, 2, figsize=(20, 9))

STYLE = {
    "k":       dict(color="orange", marker="o", ls="None", ms=8,  mec="black", mew=0.5),
    "fig8":    dict(color="purple", marker="s", ls="None", ms=7,  mec="black", mew=0.5),
    "survey":  dict(color="blue",   marker="^", ls="None", ms=9,  mec="black", mew=0.5),
    "spiral":  dict(color="green",  marker="D", ls="None", ms=7,  mec="black", mew=0.5),
    "anchor":  dict(color="gold",   marker="*", ls="None", ms=18, mec="black", mew=0.8),
    "closing": dict(color="red",    marker="v", ls="None", ms=11, mec="black", mew=0.5),
    "loiter":  dict(color="black",  marker="*", ls="None", ms=16),
}


def scatter(ax, idxs, style):
    xs = [wp_xy[i][1] for i in idxs]
    ys = [wp_xy[i][2] for i in idxs]
    ax.plot(xs, ys, **style)
    return xs, ys


def label_pts(ax, idxs, dx=8, dy=8, fontsize=7, color="black"):
    for i in idxs:
        x, y = wp_xy[i][1], wp_xy[i][2]
        ax.annotate(str(i), (x, y), xytext=(dx, dy), textcoords="offset points",
                    fontsize=fontsize, color=color)


# ===== LEFT: full corridor view =====
axL.add_patch(Polygon(corridor_poly, closed=True, facecolor="0.6", alpha=0.3,
                      edgecolor="0.4", linewidth=0.5))
axL.plot(hwy_xy[:, 0], hwy_xy[:, 1], "-", color="gold", linewidth=0.8)

scatter(axL, [2, 3], STYLE["k"])
scatter(axL, list(range(4, 15)), STYLE["fig8"])
scatter(axL, list(range(15, 19)), STYLE["survey"])
scatter(axL, list(range(19, 29)), STYLE["spiral"])
scatter(axL, [29], STYLE["anchor"])
scatter(axL, [30], STYLE["closing"])
scatter(axL, [31], STYLE["loiter"])
label_pts(axL, list(range(2, 32)), dx=6, dy=6, fontsize=6)

axL.set_title("Full plan view (Fergus50_S09_AB v5 - log spiral teardrop)")
axL.set_xlabel("East (m) from highway centroid")
axL.set_ylabel("North (m) from highway centroid")
axL.set_aspect("equal")
axL.grid(True, alpha=0.3)

legend_handles = [
    Line2D([0], [0], **STYLE["k"],       label="K1/K2 (kinematic line, 2-3)"),
    Line2D([0], [0], **STYLE["fig8"],    label="Figure-8 (4-14)"),
    Line2D([0], [0], **STYLE["survey"],  label="Sparse survey (15-18)"),
    Line2D([0], [0], **STYLE["spiral"],  label="Spiral arc (19-28)"),
    Line2D([0], [0], **STYLE["anchor"],  label="Anchor / tangent-2 end (29)"),
    Line2D([0], [0], **STYLE["closing"], label="Closing transect end (30)"),
    Line2D([0], [0], **STYLE["loiter"],  label="LOITER (31)"),
    Line2D([0], [0], color="gold", lw=1.0, label="highway centerline"),
    Line2D([0], [0], color="0.5", lw=4, alpha=0.4, label="corridor swath +/-75 m"),
]
axL.legend(handles=legend_handles, loc="upper left", fontsize=8)

# ===== RIGHT: zoomed teardrop + closing transect =====
axR.add_patch(Polygon(corridor_poly, closed=True, facecolor="0.7", alpha=0.3,
                      edgecolor="0.4", linewidth=0.5))
axR.plot(hwy_xy[:, 0], hwy_xy[:, 1], "-", color="gold", linewidth=0.8)

# +/-75 m perp gridlines at the highway point nearest the anchor
nearest_anchor = nearest_idx(anchor, hwy_xy)
if nearest_anchor + 1 < len(hwy_xy):
    htan = hwy_xy[nearest_anchor + 1] - hwy_xy[max(nearest_anchor - 1, 0)]
else:
    htan = hwy_xy[nearest_anchor] - hwy_xy[nearest_anchor - 1]
htan = htan / np.linalg.norm(htan)
hperp_left = np.array([-htan[1], htan[0]])
plus75 = hwy_xy[nearest_anchor] + hperp_left * 75
minus75 = hwy_xy[nearest_anchor] - hperp_left * 75
axR.plot([minus75[0], plus75[0]], [minus75[1], plus75[1]],
         linestyle=":", color="dimgray", lw=0.8)
axR.plot(*plus75, marker="x", color="dimgray", ms=8)
axR.plot(*minus75, marker="x", color="dimgray", ms=8)
axR.annotate("+75 m", plus75, xytext=(6, 6), textcoords="offset points",
             fontsize=7, color="dimgray")
axR.annotate("-75 m", minus75, xytext=(6, 6), textcoords="offset points",
             fontsize=7, color="dimgray")

# Survey path (15-18) blue thin line + triangles
spath = np.array([W(i) for i in range(15, 19)])
axR.plot(spath[:, 0], spath[:, 1], "-", color="blue", lw=1.0,
         label="survey path (15->18)")
scatter(axR, list(range(15, 19)), STYLE["survey"])
label_pts(axR, list(range(15, 19)), dx=8, dy=8, fontsize=8)

# Tangent-1 (18 -> 19) green dashed
axR.plot([last_survey[0], t1_end[0]], [last_survey[1], t1_end[1]],
         "--", color="green", lw=1.6, label="tangent-1 (18->19)")

# Spiral arc (19..28) green solid polyline with diamond markers
axR.plot(spiral_pts[:, 0], spiral_pts[:, 1], "-", color="green", lw=1.4,
         label="log spiral arc (19->28)")
axR.plot(spiral_pts[:, 0], spiral_pts[:, 1], **STYLE["spiral"])
label_pts(axR, list(range(19, 29)), dx=6, dy=6, fontsize=7, color="darkgreen")

# Tangent-2 (28 -> 29 = anchor) green dashed
axR.plot([spiral_end[0], anchor[0]], [spiral_end[1], anchor[1]],
         "--", color="green", lw=1.6, label="tangent-2 (28->29)")

# Closing transect FOV footprint (drawn first so polyline overlays it)
axR.add_patch(Polygon(fov_corners, closed=True, facecolor="green", alpha=0.18,
                      edgecolor="green", linewidth=0.8,
                      label="LiDAR FOV (100 m x 126.5 m)"))

# Closing transect (29 -> 30) red solid
axR.plot([anchor[0], closing_end[0]], [anchor[1], closing_end[1]],
         "-", color="red", lw=1.8, label="closing transect (29->30)")
scatter(axR, [30], STYLE["closing"])
label_pts(axR, [30], dx=8, dy=8, fontsize=8, color="darkred")

# Anchor (item 29) - gold star
scatter(axR, [29], STYLE["anchor"])

# LOITER (item 31)
scatter(axR, [31], STYLE["loiter"])
label_pts(axR, [31], dx=10, dy=-12, fontsize=8)

# Targeted annotations per spec
axR.annotate("last survey WP", last_survey,
             xytext=(-90, -25), textcoords="offset points",
             fontsize=9, color="blue", weight="bold",
             arrowprops=dict(arrowstyle="->", color="blue", lw=0.8))
axR.annotate("tangent-1 end", t1_end,
             xytext=(25, 10), textcoords="offset points",
             fontsize=9, color="darkgreen", weight="bold",
             arrowprops=dict(arrowstyle="->", color="darkgreen", lw=0.8))
axR.annotate("spiral end", spiral_end,
             xytext=(-90, 10), textcoords="offset points",
             fontsize=9, color="darkgreen", weight="bold",
             arrowprops=dict(arrowstyle="->", color="darkgreen", lw=0.8))
axR.annotate("ANCHOR", anchor,
             xytext=(25, -28), textcoords="offset points",
             fontsize=10, color="black", weight="bold",
             arrowprops=dict(arrowstyle="->", color="black", lw=0.8))

axR.set_xlim(anchor[0] - 200, anchor[0] + 200)
axR.set_ylim(anchor[1] - 200, anchor[1] + 200)
axR.set_title("Spiral teardrop + closing transect (zoom)")
axR.set_xlabel("East (m) from highway centroid")
axR.set_ylabel("North (m) from highway centroid")
axR.set_aspect("equal")
axR.grid(True, alpha=0.3)
axR.legend(loc="upper left", fontsize=8)

plt.tight_layout()
plt.savefig(OUT, dpi=150)
plt.close()

size = os.path.getsize(OUT)
print(f"PNG written: {OUT}")
print(f"PNG size: {size} bytes ({size/1024:.1f} KB)")
print(f"tangent-1 length:   {tangent1_len:.2f} m   (= spiral R_start)")
print(f"spiral arc length:  {spiral_arc_len:.2f} m  (sum of 19->20->...->28)")
print(f"spiral R_start (18->19 dist):     {R_start:.2f} m")
print(f"spiral R_end (anchor->item 28):   {R_end:.2f} m")
print(f"tangent-2 length:   {tangent2_len:.2f} m")
print(f"closing transect:   {closing_len:.2f} m")
