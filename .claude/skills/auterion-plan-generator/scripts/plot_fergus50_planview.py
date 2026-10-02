"""Plot Fergus50_S09_AB plan in plan view."""
import json
import re
import math
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon, Rectangle
from matplotlib.lines import Line2D

PLAN = r"C:/Users/rharbach.STAHLY/Documents/Auterion Mission Control/Missions/Fergus50_S09_AB.plan"
KML = r"C:/Users/rharbach.STAHLY/Downloads/HighwayCenterline.kml"
OUT = r"C:/Users/rharbach.STAHLY/Downloads/Fergus50_S09_AB_v4_planview.png"

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

# index helper
def W(i):
    return np.array([wp_xy[i][1], wp_xy[i][2]])

# ---------- corridor swath: highway buffered ±75 m, from A_along to B_along ----------
# Approximate A_along = nearest highway point to item 2 (K1); B_along = nearest highway point to item 18 (anchor / last survey WP).
def nearest_idx(target_xy, line_xy):
    d2 = np.sum((line_xy - target_xy) ** 2, axis=1)
    return int(np.argmin(d2))

A_xy = W(2)   # K1
B_xy = W(18)  # anchor / last survey WP
idx_A = nearest_idx(A_xy, hwy_xy)
idx_B = nearest_idx(B_xy, hwy_xy)
i0, i1 = sorted([idx_A, idx_B])
seg = hwy_xy[i0:i1 + 1]

# buffer ±75 m via per-segment normals
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
anchor = W(18)
t1_start = anchor
t1_end = W(19)
tangent1_len = float(np.linalg.norm(t1_end - t1_start))

arc_pts = np.array([W(i) for i in range(19, 31)])  # 12 pts
# Arc radius: fit circle by algebraic least squares
def fit_circle(pts):
    x, y = pts[:, 0], pts[:, 1]
    A = np.column_stack([2 * x, 2 * y, np.ones(len(x))])
    b = x * x + y * y
    sol, *_ = np.linalg.lstsq(A, b, rcond=None)
    cx, cy, c = sol
    r = math.sqrt(c + cx * cx + cy * cy)
    return cx, cy, r
cx, cy, arc_radius = fit_circle(arc_pts)

closing_end = W(31)
closing_len = float(np.linalg.norm(closing_end - anchor))

# Transect direction (perp_left of survey direction)
trans_dir = (closing_end - anchor) / closing_len
trans_perp = np.array([-trans_dir[1], trans_dir[0]])  # 90° CCW
fov_width = 100.0
fov_length = closing_len
mid = (anchor + closing_end) / 2.0
fov_corners = np.array([
    mid + trans_dir * (fov_length / 2) + trans_perp * (fov_width / 2),
    mid + trans_dir * (fov_length / 2) - trans_perp * (fov_width / 2),
    mid - trans_dir * (fov_length / 2) - trans_perp * (fov_width / 2),
    mid - trans_dir * (fov_length / 2) + trans_perp * (fov_width / 2),
])

# ---------- plot ----------
fig, (axL, axR) = plt.subplots(1, 2, figsize=(20, 9))

# style table per spec
STYLE = {
    "k": dict(color="orange", marker="o", ls="None", ms=8, mec="black", mew=0.5),
    "fig8": dict(color="purple", marker="s", ls="None", ms=7, mec="black", mew=0.5),
    "survey": dict(color="blue", marker="^", ls="None", ms=9, mec="black", mew=0.5),
    "arc": dict(color="green", marker="D", ls="None", ms=7, mec="black", mew=0.5),
    "closing": dict(color="red", marker="v", ls="None", ms=10, mec="black", mew=0.5),
    "loiter": dict(color="black", marker="*", ls="None", ms=16),
}

def scatter(ax, idxs, style):
    xs = [wp_xy[i][1] for i in idxs]
    ys = [wp_xy[i][2] for i in idxs]
    ax.plot(xs, ys, **style)
    return xs, ys

def label_pts(ax, idxs, dx=15, dy=15, fontsize=7, color="black"):
    for i in idxs:
        x, y = wp_xy[i][1], wp_xy[i][2]
        ax.annotate(str(i), (x, y), xytext=(dx, dy), textcoords="offset points",
                    fontsize=fontsize, color=color)

# ===== LEFT: full corridor view =====
# corridor swath
axL.add_patch(Polygon(corridor_poly, closed=True, facecolor="0.6", alpha=0.3,
                     edgecolor="0.4", linewidth=0.5, label="corridor swath ±75 m"))
# highway
axL.plot(hwy_xy[:, 0], hwy_xy[:, 1], "-", color="gold", linewidth=0.8,
         label="highway centerline")

# waypoints by group
scatter(axL, [2, 3], STYLE["k"])
scatter(axL, list(range(4, 15)), STYLE["fig8"])
scatter(axL, list(range(15, 19)), STYLE["survey"])
scatter(axL, list(range(19, 31)), STYLE["arc"])
scatter(axL, [31], STYLE["closing"])
scatter(axL, [32], STYLE["loiter"])
label_pts(axL, list(range(2, 33)), dx=8, dy=8, fontsize=7)

axL.set_title("Full plan view (Fergus50_S09_AB)")
axL.set_xlabel("East (m) from highway centroid")
axL.set_ylabel("North (m) from highway centroid")
axL.set_aspect("equal")
axL.grid(True, alpha=0.3)
# legend
legend_handles = [
    Line2D([0], [0], **STYLE["k"], label="K1/K2 (kinematic line)"),
    Line2D([0], [0], **STYLE["fig8"], label="Figure-8 (items 4–14)"),
    Line2D([0], [0], **STYLE["survey"], label="Sparse survey (15–18)"),
    Line2D([0], [0], **STYLE["arc"], label="Teardrop arc (19–30)"),
    Line2D([0], [0], **STYLE["closing"], label="Closing transect end (31)"),
    Line2D([0], [0], **STYLE["loiter"], label="LOITER (32)"),
    Line2D([0], [0], color="gold", lw=1.0, label="highway centerline"),
]
axL.legend(handles=legend_handles, loc="upper left", fontsize=8)

# ===== RIGHT: zoomed teardrop + closing =====
# corridor swath rectangle in zoom area
# Build a rectangle: use the segment of highway near anchor; we will draw the
# corridor polygon overall and let zoom clip it.
axR.add_patch(Polygon(corridor_poly, closed=True, facecolor="0.7", alpha=0.3,
                     edgecolor="0.4", linewidth=0.5))
axR.plot(hwy_xy[:, 0], hwy_xy[:, 1], "-", color="gold", linewidth=0.8)

# Mark ±75 m extents with a label near anchor
# Determine highway tangent at anchor
nearest_anchor = nearest_idx(anchor, hwy_xy)
if nearest_anchor + 1 < len(hwy_xy):
    htan = hwy_xy[nearest_anchor + 1] - hwy_xy[max(nearest_anchor - 1, 0)]
else:
    htan = hwy_xy[nearest_anchor] - hwy_xy[nearest_anchor - 1]
htan = htan / np.linalg.norm(htan)
hperp_left = np.array([-htan[1], htan[0]])
plus75 = hwy_xy[nearest_anchor] + hperp_left * 75
minus75 = hwy_xy[nearest_anchor] - hperp_left * 75
axR.plot(*plus75, marker="x", color="dimgray", ms=8)
axR.plot(*minus75, marker="x", color="dimgray", ms=8)
axR.annotate("+75 m", plus75, xytext=(6, 6), textcoords="offset points",
             fontsize=7, color="dimgray")
axR.annotate("-75 m", minus75, xytext=(6, 6), textcoords="offset points",
             fontsize=7, color="dimgray")

# Survey path (15-18) blue line
spath = np.array([W(i) for i in range(15, 19)])
axR.plot(spath[:, 0], spath[:, 1], "-", color="blue", lw=1.0, label="survey path (15→18)")
scatter(axR, list(range(15, 19)), STYLE["survey"])
label_pts(axR, list(range(15, 19)), dx=8, dy=8, fontsize=8)

# Tangent-1: anchor (18) -> 19 dashed green
axR.plot([anchor[0], t1_end[0]], [anchor[1], t1_end[1]],
         "--", color="green", lw=1.4, label="tangent-1 (18→19)")

# Arc samples 19-30 green diamonds + solid green connecting line
axR.plot(arc_pts[:, 0], arc_pts[:, 1], "-", color="green", lw=1.2)
axR.plot(arc_pts[:, 0], arc_pts[:, 1], **STYLE["arc"])
label_pts(axR, list(range(19, 31)), dx=6, dy=6, fontsize=7, color="darkgreen")

# Tangent-2 + closing transect: single red line from item 30 to item 31
p30 = W(30)
p31 = W(31)
axR.plot([p30[0], p31[0]], [p30[1], p31[1]], "-", color="red", lw=1.6,
         label="tangent-2 + closing transect (30→31)")
scatter(axR, [31], STYLE["closing"])
label_pts(axR, [31], dx=8, dy=8, fontsize=8, color="darkred")

# FOV footprint rectangle
axR.add_patch(Polygon(fov_corners, closed=True, facecolor="green", alpha=0.18,
                     edgecolor="green", linewidth=0.8,
                     label="LiDAR FOV (100 m wide)"))

# LOITER
scatter(axR, [32], STYLE["loiter"])
label_pts(axR, [32], dx=8, dy=8, fontsize=8)

# Anchor annotation
axR.annotate("ANCHOR (last survey WP)", anchor,
             xytext=(20, -25), textcoords="offset points",
             fontsize=9, color="black", weight="bold",
             arrowprops=dict(arrowstyle="->", color="black", lw=0.8))

# Zoom extent ±200 m around anchor
axR.set_xlim(anchor[0] - 200, anchor[0] + 200)
axR.set_ylim(anchor[1] - 200, anchor[1] + 200)
axR.set_title("Closing maneuvers zoom")
axR.set_xlabel("East (m) from highway centroid")
axR.set_ylabel("North (m) from highway centroid")
axR.set_aspect("equal")
axR.grid(True, alpha=0.3)
axR.legend(loc="upper left", fontsize=8)

plt.tight_layout()
plt.savefig(OUT, dpi=150)
plt.close()

import os
size = os.path.getsize(OUT)
print(f"PNG written: {OUT}")
print(f"PNG size: {size} bytes ({size/1024:.1f} KB)")
print(f"tangent-1 length: {tangent1_len:.2f} m")
print(f"arc radius (fit): {arc_radius:.2f} m  (center=({cx:.2f},{cy:.2f}))")
print(f"closing transect length: {closing_len:.2f} m")
print(f"FOV footprint: width={fov_width:.0f} m  length={fov_length:.2f} m")
