"""Plot Fergus50_S09_AB v7 plan view (R=50 m circle -> perpendicular transect -> LOITER).

v7 from v6:
  - Closing arc is now a CONSTANT-R=50 m circle (not a log spiral).
  - 270 deg CW sweep, ending at the corridor right edge perpendicular.
  - Followed by a 200 m straight perpendicular transect across the corridor.
"""
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
OUT = r"C:/Users/rharbach.STAHLY/Downloads/Fergus50_S09_AB_v7_planview.png"

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


# ---------- corridor swath: highway buffered +/- 75 m, from A_along to B_along ----------
def nearest_idx(target_xy, line_xy):
    d2 = np.sum((line_xy - target_xy) ** 2, axis=1)
    return int(np.argmin(d2))


A_xy = W(2)   # K1
B_anchor_xy = W(18)  # Last survey WP - the "B" anchor along the highway
idx_A = nearest_idx(A_xy, hwy_xy)
idx_B = nearest_idx(B_anchor_xy, hwy_xy)
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
last_survey = W(18)
t1_end = W(19)          # tangent-1 end / arc entry
arc_end = W(28)         # arc end (corridor right edge)
transect_end = W(29)    # straight perp transect end
loiter = W(30)          # LOITER, same as 29

tangent1_len = float(np.linalg.norm(t1_end - last_survey))

# Arc points: items 19..28 (10 WPs total: 19 entry, 20..27 intermediates, 28 end)
arc_pts = np.array([W(i) for i in range(19, 29)])
arc_len = float(np.sum(np.linalg.norm(np.diff(arc_pts, axis=0), axis=1)))


# ---------- fit a circle to arc points (algebraic least squares) ----------
def fit_circle(pts):
    """Kasa algebraic least-squares circle fit. Returns (cx, cy, R)."""
    x = pts[:, 0]
    y = pts[:, 1]
    A = np.column_stack([2 * x, 2 * y, np.ones_like(x)])
    b = x ** 2 + y ** 2
    sol, *_ = np.linalg.lstsq(A, b, rcond=None)
    cx, cy, c = sol
    R = math.sqrt(c + cx ** 2 + cy ** 2)
    return cx, cy, R


cx, cy, R_fit = fit_circle(arc_pts)
radii = np.linalg.norm(arc_pts - np.array([cx, cy]), axis=1)
R_mean = float(np.mean(radii))
R_std = float(np.std(radii))

# Transect 28 -> 29
transect_vec = transect_end - arc_end
transect_len = float(np.linalg.norm(transect_vec))
transect_dir = transect_vec / transect_len

# Highway tangent at the nearest highway point to item 28 -> perp_left_B
idx_hwy_28 = nearest_idx(arc_end, hwy_xy)
if idx_hwy_28 + 1 < len(hwy_xy):
    tan_B = hwy_xy[idx_hwy_28 + 1] - hwy_xy[max(idx_hwy_28 - 1, 0)]
else:
    tan_B = hwy_xy[idx_hwy_28] - hwy_xy[idx_hwy_28 - 1]
tan_B = tan_B / np.linalg.norm(tan_B)
# Match the direction of travel along the corridor
travel_dir = (B_anchor_xy - A_xy)
travel_dir = travel_dir / np.linalg.norm(travel_dir)
if np.dot(tan_B, travel_dir) < 0:
    tan_B = -tan_B
perp_left_B = np.array([-tan_B[1], tan_B[0]])
perp_right_B = -perp_left_B

cos_angle_transect_to_perp_left = float(np.dot(transect_dir, perp_left_B))


# Perpendicular distances of item 28 and item 29 from highway centerline
def perp_dist_signed(point, hwy_line):
    idx = nearest_idx(point, hwy_line)
    if idx + 1 < len(hwy_line):
        t = hwy_line[idx + 1] - hwy_line[max(idx - 1, 0)]
    else:
        t = hwy_line[idx] - hwy_line[idx - 1]
    t = t / np.linalg.norm(t)
    if np.dot(t, travel_dir) < 0:
        t = -t
    p_right = np.array([t[1], -t[0]])  # right normal
    vec = point - hwy_line[idx]
    return float(np.dot(vec, p_right))


perp_dist_28 = perp_dist_signed(arc_end, hwy_xy)
perp_dist_29 = perp_dist_signed(transect_end, hwy_xy)

# LiDAR FOV footprint along the transect:
# 100 m wide (perpendicular to transect direction, = aligned with tan_B)
# 200 m long (along transect direction).
fov_width = 100.0
fov_length = 200.0
trans_perp = np.array([-transect_dir[1], transect_dir[0]])  # 90 CCW of transect_dir
mid = (arc_end + transect_end) / 2.0
fov_corners = np.array([
    mid + transect_dir * (fov_length / 2) + trans_perp * (fov_width / 2),
    mid + transect_dir * (fov_length / 2) - trans_perp * (fov_width / 2),
    mid - transect_dir * (fov_length / 2) - trans_perp * (fov_width / 2),
    mid - transect_dir * (fov_length / 2) + trans_perp * (fov_width / 2),
])

# ---------- plot ----------
fig, (axL, axR) = plt.subplots(1, 2, figsize=(20, 9))

STYLE = {
    "k":       dict(color="orange", marker="o", ls="None", ms=8,  mec="black", mew=0.5),
    "fig8":    dict(color="purple", marker="s", ls="None", ms=7,  mec="black", mew=0.5),
    "survey":  dict(color="blue",   marker="^", ls="None", ms=9,  mec="black", mew=0.5),
    "arc":     dict(color="green",  marker="D", ls="None", ms=7,  mec="black", mew=0.5),
    "transect_end": dict(color="red", marker="v", ls="None", ms=11, mec="black", mew=0.5),
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
scatter(axL, list(range(19, 29)), STYLE["arc"])
scatter(axL, [29], STYLE["transect_end"])
scatter(axL, [30], STYLE["loiter"])
label_pts(axL, list(range(2, 31)), dx=6, dy=6, fontsize=6)

axL.set_title("Full plan view (Fergus50_S09_AB v7 - R=50 m circle + 200 m perp transect)")
axL.set_xlabel("East (m) from highway centroid")
axL.set_ylabel("North (m) from highway centroid")
axL.set_aspect("equal")
axL.grid(True, alpha=0.3)

legend_handles = [
    Line2D([0], [0], **STYLE["k"],            label="K1/K2 (kinematic line, 2-3)"),
    Line2D([0], [0], **STYLE["fig8"],         label="Figure-8 (4-14)"),
    Line2D([0], [0], **STYLE["survey"],       label="Sparse survey (15-18)"),
    Line2D([0], [0], **STYLE["arc"],          label="R=50 m circle (19-28)"),
    Line2D([0], [0], **STYLE["transect_end"], label="Transect end (29)"),
    Line2D([0], [0], **STYLE["loiter"],       label="LOITER (30)"),
    Line2D([0], [0], color="gold", lw=1.0,    label="highway centerline"),
    Line2D([0], [0], color="0.5", lw=4, alpha=0.4, label="corridor swath +/-75 m"),
]
axL.legend(handles=legend_handles, loc="upper left", fontsize=8)

# ===== RIGHT: zoomed closing block (R=50 m circle + perp transect) =====
axR.add_patch(Polygon(corridor_poly, closed=True, facecolor="0.7", alpha=0.3,
                      edgecolor="0.4", linewidth=0.5))
axR.plot(hwy_xy[:, 0], hwy_xy[:, 1], "-", color="gold", linewidth=0.8)

# +/- 75 m perp gridline at the highway point nearest item 18 (last survey)
nearest_18 = nearest_idx(last_survey, hwy_xy)
plus75 = hwy_xy[nearest_18] - perp_left_B * 75    # perp_right (corridor right edge)
minus75 = hwy_xy[nearest_18] + perp_left_B * 75   # perp_left
axR.plot([minus75[0], plus75[0]], [minus75[1], plus75[1]],
         linestyle=":", color="dimgray", lw=0.8)
axR.plot(*plus75, marker="x", color="dimgray", ms=8)
axR.plot(*minus75, marker="x", color="dimgray", ms=8)
axR.annotate("+75 m (perp_right)", plus75, xytext=(6, -12), textcoords="offset points",
             fontsize=7, color="dimgray")
axR.annotate("-75 m (perp_left)", minus75, xytext=(6, 6), textcoords="offset points",
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

# Arc (19..28) green solid polyline with diamond markers
axR.plot(arc_pts[:, 0], arc_pts[:, 1], "-", color="green", lw=1.4,
         label="R=50 m circle arc (19->28)")
axR.plot(arc_pts[:, 0], arc_pts[:, 1], **STYLE["arc"])
label_pts(axR, list(range(19, 29)), dx=6, dy=6, fontsize=7, color="darkgreen")

# LiDAR FOV footprint (drawn first so the transect line overlays it)
axR.add_patch(Polygon(fov_corners, closed=True, facecolor="green", alpha=0.18,
                      edgecolor="green", linewidth=0.8,
                      label="LiDAR FOV (100 m x 200 m)"))

# Perpendicular transect (28 -> 29) red solid
axR.plot([arc_end[0], transect_end[0]], [arc_end[1], transect_end[1]],
         "-", color="red", lw=1.8, label="perp transect (28->29)")
scatter(axR, [29], STYLE["transect_end"])
label_pts(axR, [29], dx=8, dy=8, fontsize=8, color="darkred")

# LOITER (item 30) - black star at item 29 position
scatter(axR, [30], STYLE["loiter"])
label_pts(axR, [30], dx=10, dy=-12, fontsize=8)

# Targeted annotations
axR.annotate("last survey WP", last_survey,
             xytext=(-110, -25), textcoords="offset points",
             fontsize=9, color="blue", weight="bold",
             arrowprops=dict(arrowstyle="->", color="blue", lw=0.8))
axR.annotate("tangent-1 end", t1_end,
             xytext=(25, 12), textcoords="offset points",
             fontsize=9, color="darkgreen", weight="bold",
             arrowprops=dict(arrowstyle="->", color="darkgreen", lw=0.8))
axR.annotate("arc end (corridor right edge)", arc_end,
             xytext=(-180, -30), textcoords="offset points",
             fontsize=9, color="darkgreen", weight="bold",
             arrowprops=dict(arrowstyle="->", color="darkgreen", lw=0.8))
axR.annotate("transect end", transect_end,
             xytext=(25, 10), textcoords="offset points",
             fontsize=9, color="darkred", weight="bold",
             arrowprops=dict(arrowstyle="->", color="darkred", lw=0.8))

# Zoom: +/-250 m around the LAST SURVEY WP (item 18)
axR.set_xlim(last_survey[0] - 250, last_survey[0] + 250)
axR.set_ylim(last_survey[1] - 250, last_survey[1] + 250)
axR.set_title("R=50 m circle -> perp transect (zoom)")
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
print(f"tangent-1 length  (18->19):           {tangent1_len:.2f} m")
print(f"arc fit (Kasa):  cx={cx:.2f}  cy={cy:.2f}  R_fit={R_fit:.4f} m")
print(f"arc radii mean / std (19..28 vs fit center): {R_mean:.4f} / {R_std:.4f} m")
print(f"arc length (19->...->28):             {arc_len:.2f} m")
print(f"straight transect (28->29):           {transect_len:.2f} m")
print(f"cos(transect_dir, perp_left_B):       {cos_angle_transect_to_perp_left:.6f}")
print(f"item 28 perp dist from hwy (right+):  {perp_dist_28:.2f} m")
print(f"item 29 perp dist from hwy (right+):  {perp_dist_29:.2f} m")
crosses_right = (perp_dist_28 - 75) * (perp_dist_29 - 75) < 0 or perp_dist_28 > 75 or perp_dist_29 > 75
crosses_left  = (perp_dist_28 + 75) * (perp_dist_29 + 75) < 0 or perp_dist_28 < -75 or perp_dist_29 < -75
print(f"transect crosses +75 (right) edge: {crosses_right}")
print(f"transect crosses -75 (left)  edge: {crosses_left}")
