"""QA-QC of Fergus50_S09_AB.plan v2: confirm loop radius+inset+FOV-inside-corridor fixes."""
import json, math
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Circle, FancyArrow

PLAN = r"C:/Users/rharbach.STAHLY/Documents/Auterion Mission Control/Missions/Fergus50_S09_AB.plan"
OUT  = r"C:/Users/rharbach.STAHLY/Downloads/Fergus50_S09_AB_planview_v2.png"

with open(PLAN) as f:
    plan = json.load(f)

home_lat, home_lon, home_alt = plan["mission"]["plannedHomePosition"]
M_LAT = 111132.0
M_LON = 111132.0 * math.cos(math.radians(home_lat))

def to_xy(lat, lon):
    return ((lon - home_lon) * M_LON, (lat - home_lat) * M_LAT)

items = plan["mission"]["items"]
print(f"Total mission items: {len(items)}")

# Classify
sections = {
    "header":   items[0:2],      # 530, 178
    "kin":      items[2:4],      # 2 WPs
    "fig8":     items[4:15],     # 11 WPs
    "survey":   items[15:19],    # 4 WPs
    "loop":     items[19:31],    # 12 WPs
    "transect": items[31:33],    # 2 WPs
    "loiter":   items[33:34],    # 1
}
for k, v in sections.items():
    print(f"  {k:8s}: {len(v):3d} items")

def wp_xy(it):
    p = it["params"]
    return to_xy(p[4], p[5])

kin_xy   = [wp_xy(it) for it in sections["kin"]]
fig8_xy  = [wp_xy(it) for it in sections["fig8"]]
sur_xy   = [wp_xy(it) for it in sections["survey"]]
loop_xy  = [wp_xy(it) for it in sections["loop"]]
tran_xy  = [wp_xy(it) for it in sections["transect"]]
loi_xy   = [wp_xy(it) for it in sections["loiter"]]

# Define corridor: A = first survey WP (item 15), B = last survey WP (item 18)
A = np.array(sur_xy[0])
B = np.array(sur_xy[-1])
corridor_vec = B - A
corridor_len = np.linalg.norm(corridor_vec)
u_along = corridor_vec / corridor_len            # along corridor unit
u_perp  = np.array([-u_along[1], u_along[0]])    # perp (right-hand 90deg CCW)
# Determine "right" relative to flight A->B: u_perp as defined is CCW (left).
# We want right of travel = -u_perp. But the plan's "right half" was set up to have +25..+75 m positive.
# Let's pick u_perp sign so loop center has positive perp coordinate. We'll test both.
print(f"\nCorridor: A={A.round(1)}, B={B.round(1)}, len={corridor_len:.1f} m")
print(f"  u_along = {u_along.round(4)}")
print(f"  u_perp  = {u_perp.round(4)}")

def along_perp(p):
    d = np.array(p) - A
    return (np.dot(d, u_along), np.dot(d, u_perp))

# Loop center: centroid of 12 loop WPs
loop_arr = np.array(loop_xy)
loop_center = loop_arr.mean(axis=0)
loop_center_ap = along_perp(loop_center)
# Loop radius: mean distance from each loop WP to the centroid
loop_radii = np.linalg.norm(loop_arr - loop_center, axis=1)
loop_radius = loop_radii.mean()
print(f"\nLoop circle:")
print(f"  center  along={loop_center_ap[0]:+.2f} m, perp={loop_center_ap[1]:+.2f} m")
print(f"  radius (mean) = {loop_radius:.2f} m")
print(f"  radius (min)  = {loop_radii.min():.2f} m")
print(f"  radius (max)  = {loop_radii.max():.2f} m")

# Sign convention: if loop center's perp coordinate is negative, flip u_perp
# (the plan was designed with loop on RIGHT side at +25..+75; we want that
# convention to hold for reporting.)
if loop_center_ap[1] < 0:
    u_perp = -u_perp
    print("  [flipped u_perp so 'right of travel' is positive perp]")
    def along_perp(p):
        d = np.array(p) - A
        return (np.dot(d, u_along), np.dot(d, u_perp))
    loop_center_ap = along_perp(loop_center)
    print(f"  center  along={loop_center_ap[0]:+.2f} m, perp={loop_center_ap[1]:+.2f} m")

# Verify loop perp range
loop_aps = [along_perp(p) for p in loop_xy]
loop_perps = [ap[1] for ap in loop_aps]
loop_center_perp = loop_center_ap[1]
print(f"  perp range of loop WPs: [{min(loop_perps):.2f}, {max(loop_perps):.2f}] m")
print(f"  required: center perp_offset in [+25, +75]? {25 <= loop_center_perp <= 75}")

# Loop entirely within corridor's perpendicular extent [-75, +75]?
loop_perp_min = loop_center_perp - loop_radius
loop_perp_max = loop_center_perp + loop_radius
loop_inside_corridor_perp = (-75 <= loop_perp_min) and (loop_perp_max <= 75)
print(f"  loop perp extent = [{loop_perp_min:.2f}, {loop_perp_max:.2f}] m")
print(f"  loop fully within corridor perp [-75,+75]? {loop_inside_corridor_perp}")

# Closing transect:
T1 = np.array(tran_xy[0])
T2 = np.array(tran_xy[1])
T1_ap = along_perp(T1)
T2_ap = along_perp(T2)
print(f"\nClosing transect:")
print(f"  WP31  along={T1_ap[0]:+.2f} m, perp={T1_ap[1]:+.2f} m")
print(f"  WP32  along={T2_ap[0]:+.2f} m, perp={T2_ap[1]:+.2f} m")
T_mid = (T1 + T2) / 2
T_mid_ap = along_perp(T_mid)
T_len = np.linalg.norm(T2 - T1)
T_along_mid = T_mid_ap[0]
T_perp_mid = T_mid_ap[1]
print(f"  midpoint along={T_along_mid:+.2f} m, perp={T_perp_mid:+.2f} m")
print(f"  length = {T_len:.2f} m  (expected ~200 m)")
# Direction of transect
T_dir = (T2 - T1) / T_len
T_dir_along = np.dot(T_dir, u_along)
T_dir_perp  = np.dot(T_dir, u_perp)
print(f"  direction (along, perp) = ({T_dir_along:+.4f}, {T_dir_perp:+.4f})  (perpendicular if along~0)")

# B along position
B_along = corridor_len
print(f"  B along = {B_along:.2f} m")
print(f"  transect along offset from B = {T_along_mid - B_along:+.2f} m  (expected ~ -50 m)")

# FOV footprint: along ± 50 m, perp = transect perpendicular extent ± transect_length/2
# Since the transect is perpendicular to corridor, FOV is rectangle of:
#   along: [T_along_mid - 50, T_along_mid + 50]
#   perp:  [T_perp_mid - T_len/2, T_perp_mid + T_len/2]
FOV_along = (T_along_mid - 50, T_along_mid + 50)
FOV_perp  = (T_perp_mid - T_len/2, T_perp_mid + T_len/2)
print(f"  FOV along range: [{FOV_along[0]:+.1f}, {FOV_along[1]:+.1f}] m")
print(f"  FOV perp  range: [{FOV_perp[0]:+.1f}, {FOV_perp[1]:+.1f}] m")

# Corridor: along [0, B_along], perp [-75, +75]
COR_along = (0.0, B_along)
COR_perp  = (-75.0, 75.0)

# Intersection
def overlap(a, b):
    lo = max(a[0], b[0]); hi = min(a[1], b[1])
    return max(0.0, hi - lo)

inter_along = overlap(FOV_along, COR_along)
inter_perp  = overlap(FOV_perp,  COR_perp)
inter_area  = inter_along * inter_perp
fov_area    = (FOV_along[1] - FOV_along[0]) * (FOV_perp[1] - FOV_perp[0])
overlap_frac = inter_area / fov_area if fov_area > 0 else 0
print(f"  FOV area = {fov_area:.1f} m^2, inside-corridor = {inter_area:.1f} m^2")
print(f"  FOV overlap with corridor = {overlap_frac*100:.2f}%  (target 100%)")

# Loop tangency to survey path (perp = +25 m from highway, but A->B is the highway in our coord)
# survey path is the corridor centerline at perp = 0... so the survey path the user means
# is presumably the inbound transect at perp = +25 m (right-half survey lane).
# Geometry: circle center perp = loop_center_perp, radius = loop_radius.
# Line at perp = +25 distance from center = |loop_center_perp - 25|.
# Tangent if equal to loop_radius.
line_perp = 25.0
dist_to_line = abs(loop_center_perp - line_perp)
print(f"\nLoop vs survey lane (perp=+25 m):")
print(f"  |center_perp - 25| = {dist_to_line:.2f} m,  loop_radius = {loop_radius:.2f} m")
if abs(dist_to_line - loop_radius) < 0.5:
    print(f"  --> TANGENT to survey lane (touches at one point)")
elif dist_to_line > loop_radius:
    print(f"  --> Circle does NOT cross survey lane (separated by {dist_to_line - loop_radius:.2f} m)")
else:
    print(f"  --> Circle CROSSES survey lane (chord length {2*math.sqrt(loop_radius**2 - dist_to_line**2):.2f} m)")

# ---------------- PLOTTING ----------------
fig, (axL, axR) = plt.subplots(1, 2, figsize=(18, 9), dpi=150)

COLORS = dict(kin="darkorange", fig8="purple", sur="tab:blue", loop="tab:green",
              tran="tab:red", loi="black", cor="lightgray")

def plot_section(ax, pts, color, marker="o", label=None, lw=1.5, connect=True):
    if not pts: return
    xs, ys = zip(*pts)
    if connect:
        ax.plot(xs, ys, "-", color=color, lw=lw, label=label, zorder=3)
    ax.scatter(xs, ys, c=color, s=35, marker=marker, edgecolors="white",
               linewidths=0.7, zorder=4)

# ---- LEFT: full plan view ----
plot_section(axL, kin_xy,   COLORS["kin"],  label="Kinematic line")
plot_section(axL, fig8_xy,  COLORS["fig8"], label="Figure-8 calibration")
plot_section(axL, sur_xy,   COLORS["sur"],  label="Survey transect")
plot_section(axL, loop_xy,  COLORS["loop"], label="Closing loop")
plot_section(axL, tran_xy,  COLORS["tran"], label="Closing transect")
plot_section(axL, loi_xy,   COLORS["loi"],  marker="*", label="LOITER", connect=False)
# annotate A,B
axL.annotate("A (survey start)", A, xytext=(A[0]+30, A[1]-80), fontsize=8,
             arrowprops=dict(arrowstyle="->", color="gray"))
axL.annotate("B (survey end)", B, xytext=(B[0]+20, B[1]+60), fontsize=8,
             arrowprops=dict(arrowstyle="->", color="gray"))
# Corridor swath as faint band -- compute corners of corridor rect
def corridor_corners(a0, a1, p0, p1):
    """Return 4 corners in xy of (along,perp) rectangle."""
    pts = []
    for (a, p) in [(a0, p0), (a1, p0), (a1, p1), (a0, p1)]:
        xy = A + a*u_along + p*u_perp
        pts.append(xy)
    return np.array(pts)

cor_corners = corridor_corners(0, B_along, -75, 75)
from matplotlib.patches import Polygon
axL.add_patch(Polygon(cor_corners, closed=True, color=COLORS["cor"], alpha=0.4, zorder=1))
axL.set_aspect("equal")
axL.set_title("Fergus50_S09_AB v2 - Full plan view")
axL.set_xlabel("East (m) from home")
axL.set_ylabel("North (m) from home")
axL.grid(True, alpha=0.3)
axL.legend(loc="lower right", fontsize=8)

# ---- RIGHT: zoomed end ----
plot_section(axR, sur_xy[-2:], COLORS["sur"], label="Survey (last leg)")
plot_section(axR, loop_xy,     COLORS["loop"], label="Closing loop")
plot_section(axR, tran_xy,     COLORS["tran"], label="Closing transect")
plot_section(axR, loi_xy,      COLORS["loi"], marker="*", label="LOITER", connect=False)

# Number every waypoint in zoom
ALL = (
    [(idx+15, p) for idx, p in enumerate(sur_xy)] +
    [(idx+19, p) for idx, p in enumerate(loop_xy)] +
    [(idx+31, p) for idx, p in enumerate(tran_xy)] +
    [(33,     loi_xy[0])]
)
for n, p in ALL:
    axR.annotate(str(n), p, xytext=(5, 5), textcoords="offset points",
                 fontsize=7, color="black", zorder=5)

# Corridor swath (last ~500m of corridor) as translucent gray
end_start = max(0.0, B_along - 500.0)
cor_end_corners = corridor_corners(end_start, B_along, -75, 75)
axR.add_patch(Polygon(cor_end_corners, closed=True, color="gray", alpha=0.20,
                      label="Corridor swath (±75 m)", zorder=1))

# FOV rectangle: 100 m along × 200 m perp, centered on transect midpoint
fov_corners = corridor_corners(FOV_along[0], FOV_along[1], FOV_perp[0], FOV_perp[1])
axR.add_patch(Polygon(fov_corners, closed=True, color="tab:green", alpha=0.20,
                      label="Closing transect FOV (100 m × 200 m)", zorder=2))

# Dashed circle for loop
loop_circle = Circle(loop_center, loop_radius, fill=False, ec="tab:green",
                     ls="--", lw=1.5, label=f"Loop circle r={loop_radius:.1f} m", zorder=3)
axR.add_patch(loop_circle)

# Zoom: ±300 m around transect midpoint
zx, zy = T_mid
axR.set_xlim(zx - 300, zx + 300)
axR.set_ylim(zy - 300, zy + 300)
axR.set_aspect("equal")
axR.set_title("Closing geometry (zoom: ±300 m around closing transect mid)")
axR.set_xlabel("East (m) from home")
axR.set_ylabel("North (m) from home")
axR.grid(True, alpha=0.3)
axR.legend(loc="upper left", fontsize=8)

plt.tight_layout()
plt.savefig(OUT, dpi=150, bbox_inches="tight")
print(f"\nSaved: {OUT}")

# ---------------- SUMMARY ----------------
print("\n========== SUMMARY ==========")
print(f"Section counts (target 2/2/11/4/12/2/1, total 34):")
total = sum(len(v) for v in sections.values())
print(f"  header={len(sections['header'])} kin={len(sections['kin'])} fig8={len(sections['fig8'])} "
      f"survey={len(sections['survey'])} loop={len(sections['loop'])} "
      f"transect={len(sections['transect'])} loiter={len(sections['loiter'])} total={total}")
print(f"Loop center perp offset from highway: {loop_center_perp:+.2f} m  (target +25..+75)")
print(f"Loop radius:                          {loop_radius:.2f} m   (target 25)")
print(f"Loop perp extent:                     [{loop_perp_min:+.2f}, {loop_perp_max:+.2f}] m")
print(f"Loop fully inside corridor [-75,+75]? {loop_inside_corridor_perp}")
print(f"Transect along offset from B:         {T_along_mid - B_along:+.2f} m  (target -50)")
print(f"FOV overlap with corridor:            {overlap_frac*100:.2f}%  (target 100)")
print(f"Loop vs survey lane (perp=+25 m): center-to-line distance = {dist_to_line:.2f} m vs radius {loop_radius:.2f} m")
