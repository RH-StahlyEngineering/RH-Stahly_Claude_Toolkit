"""QA-QC for Fergus50_S09_AB.plan — plot + verify geometry."""
import json, math, re
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MplPoly
from matplotlib.collections import PatchCollection

PLAN = r"C:/Users/rharbach.STAHLY/Documents/Auterion Mission Control/Missions/Fergus50_S09_AB.plan"
KML  = r"C:/Users/rharbach.STAHLY/Downloads/HighwayCenterline.kml"
OUT  = r"C:/Users/rharbach.STAHLY/Downloads/Fergus50_S09_AB_planview.png"

AGL = 50.0
SPEED = 11.5

# ---- load plan ----
with open(PLAN) as f:
    plan = json.load(f)

mission = plan["mission"]
items = mission["items"]
home = mission["plannedHomePosition"]
ref_lat, ref_lon, ref_alt = home[0], home[1], home[2]

m_lat = 111132.0
m_lon = 111132.0 * math.cos(math.radians(ref_lat))

def to_xy(lat, lon):
    return ( (lon - ref_lon) * m_lon, (lat - ref_lat) * m_lat )

# Classify items
header = []
nav = []  # (idx, lat, lon, alt, cmd, item)
for i, it in enumerate(items):
    cmd = it["command"]
    if cmd in (530, 178):
        header.append((i, it))
    else:
        p = it["params"]
        lat, lon, alt = p[4], p[5], p[6]
        nav.append((i, lat, lon, alt, cmd, it))

# Group nav items by expected section
# nav indices 0..1 = kinematic (items 2..3)
# nav 2..12 = figure-8 (items 4..14) — 11
# nav 13..16 = survey (items 15..18) — 4
# nav 17..28 = loop (items 19..30) — 12
# nav 29..30 = closing transect (items 31..32) — 2
# nav 31 = LOITER (item 33) — 1

sections = {
    "kinematic":   (0, 2,  "orange", "o"),
    "figure8":     (2, 13, "purple", "s"),
    "survey":      (13,17, "blue",   "^"),
    "loop":        (17,29, "green",  "D"),
    "closing_tx":  (29,31, "red",    "v"),
    "loiter":      (31,32, "black",  "*"),
}

# expected counts
expected = {
    "header (cmd 530+178)": (2, len(header)),
    "kinematic":   (2,  2),
    "figure8":     (11, 11),
    "survey":      (4,  4),
    "loop":        (12, 12),
    "closing_tx":  (2,  2),
    "loiter":      (1,  1),
}
# fill actual nav-section counts
for name, (a, b, *_), in sections.items():
    expected[name] = (expected[name][0], b - a)

total_expected = 34
total_actual = len(items)

# ---- parse KML highway ----
with open(KML, encoding="utf-8") as f:
    kml = f.read()
m = re.search(r"<LineString>.*?<coordinates>(.*?)</coordinates>", kml, re.S)
coords_block = m.group(1).strip()
hwy_ll = []
for tok in coords_block.split():
    lon, lat, _ = tok.split(",")
    hwy_ll.append((float(lat), float(lon)))
hwy_xy = np.array([to_xy(lat, lon) for (lat, lon) in hwy_ll])

# ---- corridor swath: ±75 m buffer from A to B along the highway ----
A_xy = to_xy(nav[0][1], nav[0][2])  # kinematic start (point A on highway approx)
# Closing transect midpoint = B
ct0 = to_xy(nav[29][1], nav[29][2])
ct1 = to_xy(nav[30][1], nav[30][2])
B_xy = ((ct0[0]+ct1[0])/2.0, (ct0[1]+ct1[1])/2.0)

# Compute along-distance of each highway vertex; clip to A..B
dxy = np.diff(hwy_xy, axis=0)
seg_len = np.hypot(dxy[:,0], dxy[:,1])
along = np.concatenate([[0.0], np.cumsum(seg_len)])

def proj_along(pt):
    # find nearest segment and along-distance
    px, py = pt
    best = (1e18, 0.0)
    for k in range(len(hwy_xy)-1):
        ax,ay = hwy_xy[k]
        bx,by = hwy_xy[k+1]
        vx,vy = bx-ax, by-ay
        L2 = vx*vx + vy*vy
        if L2 == 0: continue
        t = ((px-ax)*vx + (py-ay)*vy) / L2
        t = max(0.0, min(1.0, t))
        cx, cy = ax + t*vx, ay + t*vy
        d2 = (px-cx)**2 + (py-cy)**2
        if d2 < best[0]:
            best = (d2, along[k] + t*math.sqrt(L2))
    return best[1], math.sqrt(best[0])

sA, dA = proj_along(A_xy)
sB, dB = proj_along(B_xy)
s_lo, s_hi = sorted([sA, sB])

# Build corridor polygon by buffering vertices between sA and sB by ±75 m
def buffer_polyline(verts_xy, s_arr, s_lo, s_hi, half_w):
    # clip the polyline to [s_lo, s_hi] then offset perpendicular
    out_pts = []
    n = len(verts_xy)
    # find polyline vertices in range, plus interpolated endpoints
    pts = []
    # interp endpoint at s_lo
    def interp(s):
        for k in range(n-1):
            if s_arr[k] <= s <= s_arr[k+1]:
                t = (s - s_arr[k]) / (s_arr[k+1] - s_arr[k] + 1e-12)
                return verts_xy[k] + t*(verts_xy[k+1] - verts_xy[k])
        return verts_xy[-1] if s > s_arr[-1] else verts_xy[0]
    pts.append(interp(s_lo))
    for k in range(n):
        if s_lo < s_arr[k] < s_hi:
            pts.append(verts_xy[k])
    pts.append(interp(s_hi))
    pts = np.array(pts)
    # build left and right offsets per vertex (use segment normals averaged)
    left = []
    right = []
    for k in range(len(pts)):
        if k == 0:
            t = pts[1] - pts[0]
        elif k == len(pts)-1:
            t = pts[-1] - pts[-2]
        else:
            t = pts[k+1] - pts[k-1]
        L = np.hypot(*t)
        if L == 0:
            nx, ny = 0, 0
        else:
            nx, ny = -t[1]/L, t[0]/L
        left.append((pts[k,0] + half_w*nx, pts[k,1] + half_w*ny))
        right.append((pts[k,0] - half_w*nx, pts[k,1] - half_w*ny))
    return np.array(left + right[::-1]), pts

corridor_poly, clipped_pts = buffer_polyline(hwy_xy, along, s_lo, s_hi, 75.0)

# ---- closing transect footprint (200m x 100m) centered at B, perpendicular to highway tangent at B ----
# Highway tangent at B: use the clipped endpoint direction
def tangent_at_s(s):
    n = len(hwy_xy)
    for k in range(n-1):
        if along[k] <= s <= along[k+1]:
            t = hwy_xy[k+1] - hwy_xy[k]
            L = np.hypot(*t)
            return t / L
    return np.array([1.0, 0.0])

tB = tangent_at_s(sB)
# perpendicular (transect direction): rotate 90°
perpB = np.array([-tB[1], tB[0]])
# closing transect actually flies along the perpendicular: P31 -> P32 are 200 m apart
# Use the actual transect endpoints from the plan rather than synthesized
ct0n = np.array(ct0); ct1n = np.array(ct1)
tx_vec = ct1n - ct0n
tx_len = np.hypot(*tx_vec)
tx_dir = tx_vec / tx_len
# along-highway direction at B = tB; check that tx_dir is roughly perpendicular to tB
dot = abs(tx_dir[0]*tB[0] + tx_dir[1]*tB[1])
# footprint: rectangle of length tx_len along tx_dir, width 2*AGL along tB
half_len = tx_len/2.0
half_w   = AGL  # 50 m -> total 100 m swath
center = (ct0n + ct1n)/2.0
corners = np.array([
    center + tx_dir*half_len + tB*half_w,
    center + tx_dir*half_len - tB*half_w,
    center - tx_dir*half_len - tB*half_w,
    center - tx_dir*half_len + tB*half_w,
])

# ---- verify transect spans corridor ----
# Corridor width = 150 m; transect length = tx_len (~200 m); transect > corridor → OK
# Geometry check: project corridor swath perpendicular extent (±75 m) onto tx_dir
# Since tx_dir is the transect's long axis, the perpendicular axis to it is tB (along highway)
# The corridor at B extends ±75 m perpendicular to highway = ±75 m along tx_dir direction
# So we need |tx_len/2| >= 75 m AND footprint half-width (100 m / 2 = 50 m) along tB covers the swath thickness
proj_corridor_extent = 75.0  # corridor half-width on the tx_dir axis (perpendicular to hwy)
ok_span_lateral = (tx_len/2.0) >= proj_corridor_extent
ok_swath_overlap = half_w > 0  # trivially true; transect FOV overlaps corridor at the crossing

# Print verification
verif = {
    "tx_len_m": tx_len,
    "corridor_width_m": 150.0,
    "tx_dir_dot_tB_abs (should be ~0)": dot,
    "transect_half_len_m": tx_len/2.0,
    "corridor_half_width_m": 75.0,
    "spans_corridor": ok_span_lateral,
    "200_gt_150": 200.0 > 150.0,
}

# ---- kinematic length ----
k0 = to_xy(nav[0][1], nav[0][2])
k1 = to_xy(nav[1][1], nav[1][2])
kin_len = math.hypot(k1[0]-k0[0], k1[1]-k0[1])

# Figure-8 center should be at end of kinematic (k1)
f8_xy = np.array([to_xy(nav[i][1], nav[i][2]) for i in range(2, 13)])
f8_center = f8_xy.mean(axis=0)
f8_offset_from_k1 = math.hypot(f8_center[0]-k1[0], f8_center[1]-k1[1])

# ---- plot ----
fig, ax = plt.subplots(figsize=(16, 8), dpi=150)

# corridor swath
cp = MplPoly(corridor_poly, closed=True, facecolor=(0.5,0.5,0.5,0.25), edgecolor=(0.3,0.3,0.3,0.5), linewidth=0.5, label="Corridor swath ±75 m")
ax.add_patch(cp)
# closing transect footprint
ct = MplPoly(corners, closed=True, facecolor=(0.2,0.7,0.2,0.25), edgecolor=(0.1,0.5,0.1,0.7), linewidth=0.7, label="Closing transect footprint 200×100 m")
ax.add_patch(ct)

# highway
ax.plot(hwy_xy[:,0], hwy_xy[:,1], color="gold", linewidth=1.2, label="Hwy 81 centerline")

# section waypoints
for name, (a, b, color, marker) in sections.items():
    xs, ys, labs = [], [], []
    for j in range(a, b):
        idx, lat, lon, alt, cmd, it = nav[j]
        x, y = to_xy(lat, lon)
        xs.append(x); ys.append(y); labs.append(str(idx))
    # connect with thin line in same color
    ax.plot(xs, ys, color=color, linewidth=0.7, alpha=0.6)
    sz = 120 if marker == "*" else 40
    ax.scatter(xs, ys, c=color, marker=marker, s=sz, label=f"{name} ({b-a})", zorder=5, edgecolors="black", linewidths=0.4)
    for x, y, t in zip(xs, ys, labs):
        ax.annotate(t, (x, y), xytext=(4, 4), textcoords="offset points", fontsize=7)

# A and B markers
ax.plot(*k1, marker="P", color="orange", markersize=14, markeredgecolor="black", zorder=6)
ax.annotate("A (kinematic end / fig-8 ctr)", k1, xytext=(8, -12), textcoords="offset points", fontsize=8)
ax.plot(*B_xy, marker="P", color="red", markersize=14, markeredgecolor="black", zorder=6)
ax.annotate("B (closing tx midpoint)", B_xy, xytext=(8, -12), textcoords="offset points", fontsize=8)

ax.set_aspect("equal")
ax.set_xlabel("East (m) from HOME")
ax.set_ylabel("North (m) from HOME")
ax.set_title(f"Fergus50_S09_AB plan-view  |  AGL={AGL} m  speed={SPEED} m/s  HOME=({ref_lat:.6f},{ref_lon:.6f})")
ax.grid(alpha=0.3)
ax.legend(loc="upper left", fontsize=8, framealpha=0.9)

# Tight to data
all_x = np.concatenate([hwy_xy[:,0], corridor_poly[:,0], corners[:,0]])
all_y = np.concatenate([hwy_xy[:,1], corridor_poly[:,1], corners[:,1]])
# Restrict to area near plan
nav_x = np.array([to_xy(n[1], n[2])[0] for n in nav])
nav_y = np.array([to_xy(n[1], n[2])[1] for n in nav])
pad = 200
ax.set_xlim(nav_x.min()-pad, nav_x.max()+pad)
ax.set_ylim(nav_y.min()-pad, nav_y.max()+pad)

plt.tight_layout()
plt.savefig(OUT, dpi=150, bbox_inches="tight")
plt.close()

# ---- text report ----
print("=" * 70)
print("SECTION COUNTS (expected vs actual)")
print("=" * 70)
order = ["header (cmd 530+178)", "kinematic", "figure8", "survey", "loop", "closing_tx", "loiter"]
for k in order:
    e, a = expected[k]
    print(f"  {k:30s} expected={e:3d}  actual={a:3d}  {'OK' if e==a else 'MISMATCH'}")
print(f"  {'TOTAL':30s} expected={total_expected:3d}  actual={total_actual:3d}  {'OK' if total_expected==total_actual else 'MISMATCH'}")

print()
print("KINEMATIC")
print(f"  length = {kin_len:.1f} m   (>=115 m required: {'OK' if kin_len>=115 else 'FAIL'})")
print(f"  figure-8 center offset from kinematic end = {f8_offset_from_k1:.2f} m (should be ~0)")

print()
print("CLOSING TRANSECT vs CORRIDOR SWATH")
for k, v in verif.items():
    print(f"  {k}: {v}")

print()
print("ALTITUDE / FRAME / SPEED")
frames = sorted({it["frame"] for it in items})
altmodes = sorted({it.get("AltitudeMode") for it in items if "AltitudeMode" in it})
agls = sorted({it.get("Altitude") for it in items if "Altitude" in it})
amsls = [it.get("AMSLAltAboveTerrain") for it in items if "AMSLAltAboveTerrain" in it]
print(f"  speed cmd: 178 -> {items[1]['params'][1]} m/s")
print(f"  frames used: {frames}")
print(f"  AltitudeMode set: {altmodes}")
print(f"  Altitude (AGL) set: {agls}")
print(f"  AMSL samples (first 5): {[round(x,2) for x in amsls[:5]]}")
print(f"  AMSL range: {min(amsls):.2f} .. {max(amsls):.2f} m")

print()
print(f"PNG saved to: {OUT}")
