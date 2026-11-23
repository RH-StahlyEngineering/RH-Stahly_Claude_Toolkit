"""Subject-aimed low oblique orbits (camera). Builds one .plan with a rounded-rectangle orbit around a
building and/or an ellipse around a long feature (wall, embankment). Every photo station aims the camera
(vehicle yaw = WP param4, gimbal pitch = cmd 205 before the WP) at the nearest subject point, at slant_m.

Usage:  py low_orbits.py config.json
Config keys (lat/lon in WGS84/NAD83 degrees, heights in metres):
  las            path to a LAS/LAZ with ground (class 2) and surface returns
  las_epsg       horizontal EPSG of the LAS (z assumed NAVD88; z_units "ft" or "m")
  z_units        "ft" | "m"
  out_dir, name  output folder and plan name (writes <name>.plan, <name>_report.json, <name>_dbg.json)
  home           [lat, lon]  = the spot the pilot will actually take off from (pitfall #20)
  slant_m        camera-to-subject distance (default 30.48 = 100 ft)
  speed          m/s for EVERY speed field (default 2.0)
  trigger_s      camera minimum interval (default 2.0); photo spacing = speed * trigger_s
  clear_m        clearance over the hazard-raised surface within clear_r of the path (default 8)
  clear_r        horizontal search radius for clearance (default 5)
  min_agl        floor above ground (default 15; wires are not in lidar)
  building       {"center": [lat, lon], "search_r": 25}  -> footprint box from lidar building returns
  line           {"points": [[lat, lon], ...], "halfwidth_m": 3, "theta_deg": 35}  -> ellipse
  hazards        [{"name": "pole", "lat": .., "lon": .., "height_m": 12, "buffer_m": 6}, ...]
                 height above ground; the surface is raised to ground + height inside buffer_m
                 (towers, power poles, light poles, trees taller than the lidar shows)
  tree_growth_m  added to every non-ground lidar return (default 2; lidar age, growth since flown)
"""
import json, math, os, sys
import numpy as np, laspy
from pyproj import Transformer
from scipy import ndimage
from scipy.spatial import ConvexHull

C = json.load(open(sys.argv[1]))
SLANT = C.get("slant_m", 30.48); SPEED = C.get("speed", 2.0); SPACING = SPEED * C.get("trigger_s", 2.0)
CLEAR_M = C.get("clear_m", 8.0); CLEAR_R = C.get("clear_r", 5.0); MIN_AGL = C.get("min_agl", 15.0)
GROW = C.get("tree_growth_m", 2.0)
HOME = C["home"]

ll2utm = Transformer.from_crs(4326, 32612 if HOME[1] < -108 else 32613, always_xy=True)
utm2ll = Transformer.from_crs(ll2utm.target_crs, 4326, always_xy=True)
L = laspy.read(C["las"])
zf = 0.3048 if C.get("z_units", "ft") == "ft" else 1.0
X, Y = Transformer.from_crs(C["las_epsg"], ll2utm.target_crs, always_xy=True).transform(np.asarray(L.x), np.asarray(L.y))
z = np.asarray(L.z) * zf; cls = np.asarray(L.classification)
ok = (cls != 7) & (cls != 18); X, Y, z, cls = X[ok], Y[ok], z[ok], cls[ok]
x0, y0 = X.min(), Y.min(); nx, ny = int(X.max() - x0) + 1, int(Y.max() - y0) + 1
ix, iy = (X - x0).astype(int), (Y - y0).astype(int)
g = cls == 2
tmp = np.full((ny, nx), np.inf); np.minimum.at(tmp, (iy[g], ix[g]), z[g]); tmp[np.isinf(tmp)] = np.nan
DTM = tmp[tuple(ndimage.distance_transform_edt(np.isnan(tmp), return_distances=False, return_indices=True))]
hag0 = z - DTM[iy, ix]
DSM = np.full((ny, nx), np.nan); zs = np.where(g | (cls == 6) | (hag0 < 3), z, z + GROW)   # grow tall vegetation, not buildings, walls or curbs
np.fmax.at(DSM, (iy, ix), zs); SURF = np.where(np.isnan(DSM), DTM, DSM)

def cell(xu, yu): return (np.clip((np.asarray(yu) - y0).astype(int), 0, ny - 1), np.clip((np.asarray(xu) - x0).astype(int), 0, nx - 1))
def dtm(xu, yu): i, j = cell(xu, yu); return DTM[i, j]
def surf(xu, yu): i, j = cell(xu, yu); return SURF[i, j]

# hazards raise the surface: cylinder of ground + height, radius buffer
for hz in C.get("hazards", []):
    hx_, hy_ = ll2utm.transform(hz["lon"], hz["lat"]); r = hz.get("buffer_m", 6.0)
    jj, ii = np.meshgrid(np.arange(nx), np.arange(ny))
    m = np.hypot(jj + 0.5 - (hx_ - x0), ii + 0.5 - (hy_ - y0)) <= r
    SURF[m] = np.maximum(SURF[m], DTM[m] + hz["height_m"])

def maxsurf_near(xu, yu, r=CLEAR_R):
    i, j = cell(xu, yu); k = int(math.ceil(r)); return float(np.nanmax(SURF[max(i - k, 0):i + k + 1, max(j - k, 0):j + k + 1]))

def resample(poly, step):
    poly = np.asarray(poly); s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(poly, axis=0), axis=1))]
    n = max(int(round(s[-1] / step)), 8); t = np.linspace(0, s[-1], n, endpoint=False)
    return np.c_[np.interp(t, s, poly[:, 0]), np.interp(t, s, poly[:, 1])]

def stations(path, nearest, zfun):
    out = []
    for p in path:
        sp = nearest(*p); sz = zfun(sp); dh = float(np.linalg.norm(p - sp))
        alt = sz + math.sqrt(max(SLANT ** 2 - dh ** 2, 1.0))
        out.append(dict(x=p[0], y=p[1], alt=alt, sx=sp[0], sy=sp[1], sz=sz, dh=dh,
                        yaw=(math.degrees(math.atan2(sp[0] - p[0], sp[1] - p[1])) + 360) % 360))
    return out

def lift(st):
    """Raise each station to clearance and the AGL floor, smooth the climbs, then re-solve pitch."""
    need = np.array([max(s["alt"], maxsurf_near(s["x"], s["y"]) + CLEAR_M, float(dtm(s["x"], s["y"])) + MIN_AGL) for s in st])
    n = len(need); need = np.array([need[[(i - 1) % n, i, (i + 1) % n]].max() for i in range(n)])
    for s, a in zip(st, need):
        s["alt"] = float(a); s["pitch"] = -math.degrees(math.atan2(a - s["sz"], s["dh"]))
    return st

subjects = {}
if "building" in C:
    b = C["building"]; BX, BY = ll2utm.transform(b["center"][1], b["center"][0])
    hag = z - dtm(X, Y); near = np.hypot(X - BX, Y - BY) < b.get("search_r", 25)
    sel = near & (cls == 6) & (hag > 3)
    if sel.sum() < 300: sel = near & (hag > 4) & (cls != 2)
    P = np.c_[X[sel], Y[sel]]; h = P[ConvexHull(P).vertices]; best = None
    for k in range(len(h)):
        e = h[(k + 1) % len(h)] - h[k]; a = math.atan2(e[1], e[0])
        R = np.array([[math.cos(a), math.sin(a)], [-math.sin(a), math.cos(a)]]); q = P @ R.T
        lo_, hi_ = np.percentile(q, 1, 0), np.percentile(q, 99, 0)
        if best is None or np.prod(hi_ - lo_) < best[0]: best = (np.prod(hi_ - lo_), lo_, hi_, R)
    _, lo_, hi_, Rb = best; cen = ((lo_ + hi_) / 2) @ Rb; half = (hi_ - lo_) / 2
    corners = np.array([[lo_[0], lo_[1]], [hi_[0], lo_[1]], [hi_[0], hi_[1]], [lo_[0], hi_[1]]]) @ Rb
    base = float(np.nanmedian(dtm(*corners.T))); roof = float(np.percentile(z[sel], 90)); aim = (base + roof) / 2
    def bnear(px, py): return np.clip((np.array([px, py]) - cen) @ Rb.T, -half, half) @ Rb + cen
    best_st = None
    for deg in range(30, 71, 5):   # lowest pitch whose orbit clears everything at constant height
        d = SLANT * math.cos(math.radians(deg)); pts = []
        for qx, qy, a0 in [(half[0], half[1], 0), (-half[0], half[1], 90), (-half[0], -half[1], 180), (half[0], -half[1], 270)]:
            pts += [[qx + d * math.cos(math.radians(a)), qy + d * math.sin(math.radians(a))] for a in np.linspace(a0, a0 + 90, 19)]
        st = stations(resample(np.array(pts + [pts[0]]) @ Rb + cen, SPACING), bnear, lambda sp: aim)
        if all(s["alt"] - maxsurf_near(s["x"], s["y"]) >= CLEAR_M and s["alt"] - dtm(s["x"], s["y"]) >= MIN_AGL for s in st):
            best_st = st; break
    st = lift(best_st or st)
    subjects["building"] = dict(st=st, theta=deg, info=dict(box_m=[round(2 * half[0], 1), round(2 * half[1], 1)], base=round(base, 2), roof=round(roof, 2)))

if "line" in C:
    ln = C["line"]; pts = np.array([ll2utm.transform(lo, la) for la, lo in ln["points"]])
    seg = np.diff(pts, axis=0); slen = np.linalg.norm(seg, axis=1)
    def lnear(px, py):
        p = np.array([px, py]); best = None
        for a, v, l in zip(pts[:-1], seg, slen):
            t = np.clip(np.dot(p - a, v) / l ** 2, 0, 1); q = a + t * v; dd = np.linalg.norm(p - q)
            if best is None or dd < best[0]: best = (dd, q)
        return best[1]
    ax = pts[-1] - pts[0]; wl = np.linalg.norm(ax); wu = ax / wl; wn = np.array([-wu[1], wu[0]]); wc = (pts[0] + pts[-1]) / 2
    def lz(pt):
        ss = np.linspace(-8, 8, 33); gz = dtm(pt[0] + ss * wn[0], pt[1] + ss * wn[1]); return float((np.nanmin(gz) + np.nanmax(gz)) / 2)
    th = math.radians(ln.get("theta_deg", 35)); d = SLANT * math.cos(th)
    t = np.linspace(0, 2 * math.pi, 721); A_, B_ = wl / 2 + d, d + ln.get("halfwidth_m", 3.0)
    ell = wc + (A_ * np.cos(t))[:, None] * wu + (B_ * np.sin(t))[:, None] * wn
    subjects["line"] = dict(st=lift(stations(resample(ell, SPACING), lnear, lz)), theta=ln.get("theta_deg", 35), info=dict(length_m=round(wl, 1)))

# ---- plan ----
hx, hy = ll2utm.transform(HOME[1], HOME[0]); hz0 = float(dtm(hx, hy))
items = []
def add(it): it.update(MISSION_ITEM_ID=str(len(items)), groupTag=0, autoContinue=True, doJumpId=len(items) + 1, type="SimpleItem"); items.append(it)
def wp(xu, yu, alt, yaw=None):
    lo, la = utm2ll.transform(xu, yu)
    add(dict(command=16, frame=0, params=[0, 0, 0, yaw, la, lo, round(alt, 2)], Altitude=round(alt - float(dtm(xu, yu)), 2), AltitudeMode=3, AMSLAltAboveTerrain=round(alt, 2)))
def gimbal(p): add(dict(command=205, frame=2, params=[round(p, 1), 0, 0, 0, 0, 0, 2]))
def trig(dd): add(dict(command=206, frame=2, params=[dd, 0, 1, 0, 0, 0, 0]))
add(dict(command=530, frame=2, params=[0, 2, None, None, None, None, None]))
add(dict(command=178, frame=2, params=[1, SPEED, -1, 0, 0, 0, 0]))
transit = max(max(s["alt"] for s in v["st"]) for v in subjects.values()) + 5
wp(hx, hy, transit)
for v in subjects.values():
    st = v["st"]; wp(st[0]["x"], st[0]["y"], transit, st[0]["yaw"])
    gimbal(st[0]["pitch"]); wp(st[0]["x"], st[0]["y"], st[0]["alt"], st[0]["yaw"]); trig(SPACING)
    for s in st[1:] + [st[0]]: gimbal(s["pitch"]); wp(s["x"], s["y"], s["alt"], s["yaw"])
    trig(0); wp(st[0]["x"], st[0]["y"], transit, st[0]["yaw"])
gimbal(-90); wp(hx, hy, transit)
plan = {"fileType": "Plan", "version": 1, "groundStation": "QGroundControl",
        "geoFence": {"circles": [], "polygons": [], "version": 2}, "rallyPoints": {"points": [], "version": 2},
        "mission": {"version": 2, "vehicleType": 2, "firmwareType": 12, "cruiseSpeed": SPEED, "hoverSpeed": SPEED,
                    "globalPlanAltitudeMode": 3, "plannedHomePosition": [HOME[0], HOME[1], round(hz0, 2)], "items": items}}
out = os.path.join(C["out_dir"], C["name"])
open(out + ".plan", "wb").write(json.dumps(plan, separators=(",", ":")).encode())

def plen(st): p = np.array([[s["x"], s["y"]] for s in st]); return float(np.sum(np.linalg.norm(np.diff(np.r_[p, p[:1]], axis=0), axis=1)))
rep = dict(home=dict(lat=HOME[0], lon=HOME[1], ground_m=round(hz0, 2), ground_ft=round(hz0 / 0.3048, 1)), speed=SPEED, spacing_m=SPACING,
           transit_above_home_m=round(transit - hz0, 1), items=len(items),
           est_min=round((1.05 * sum(plen(v["st"]) for v in subjects.values()) / SPEED + 120) / 60, 1))
for k, v in subjects.items():
    st = v["st"]
    rep[k] = dict(v["info"], theta_deg=v["theta"], photos=len(st),
                  slant_m=[round(min(math.hypot(s["dh"], s["alt"] - s["sz"]) for s in st), 1), round(max(math.hypot(s["dh"], s["alt"] - s["sz"]) for s in st), 1)],
                  pitch=[round(min(s["pitch"] for s in st), 1), round(max(s["pitch"] for s in st), 1)],
                  above_home_m=[round(min(s["alt"] for s in st) - hz0, 1), round(max(s["alt"] for s in st) - hz0, 1)],
                  min_clear_m=round(min(s["alt"] - maxsurf_near(s["x"], s["y"]) for s in st), 1),
                  min_agl_m=round(min(s["alt"] - float(dtm(s["x"], s["y"])) for s in st), 1))
json.dump(rep, open(out + "_report.json", "w"), indent=1)
json.dump(dict(subjects={k: v["st"] for k, v in subjects.items()}, home=[hx, hy, hz0], config=sys.argv[1]), open(out + "_dbg.json", "w"))
print(json.dumps(rep, indent=1))
