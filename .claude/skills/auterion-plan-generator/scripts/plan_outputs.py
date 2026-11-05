"""Outputs for a camera plan set (ticket 05): HOME suggestion, saving with supersede, KML/CSV/MD summaries."""
import csv, datetime, io, os, re, shutil
import numpy as np
from scipy.spatial import cKDTree
from shapely.geometry import Point, Polygon
from shapely import prepared

MIN_CLEAR_M, OBSTACLE_H_M, MAX_SLOPE_PCT, SEARCH_M, STEP_M = 10.0, 2.0, 5.0, 60.0, 2.0


# ---------------- HOME ----------------
def suggest_home(fw, bw, limits, dem, lidar_path=None):
    """Open, flat spot at or near the limits. Obstacles = lidar non-ground points > 2 m above the DEM
    (no lidar: none known, clearance unknown). Candidates on a 2 m grid within 60 m of the limits must have
    lidar ground returns within 3 m, >= 10 m clearance and <= 5% DEM slope; pick the one nearest the limits
    (inside = 0), then most clearance (whole metres), then flattest. Returns dict(lat, lon, clearance_m, slope_pct, dist_to_limits_m) or None."""
    poly = Polygon([fw.transform(*p) for p in limits])
    x0, y0, x1, y1 = poly.buffer(SEARCH_M).bounds
    gx, gy = np.meshgrid(np.arange(x0, x1, STEP_M), np.arange(y0, y1, STEP_M))
    gx, gy = gx.ravel(), gy.ravel()
    zone = prepared.prep(poly.buffer(SEARCH_M))
    keep = np.array([zone.contains(Point(a, b)) for a, b in zip(gx, gy)])
    gx, gy = gx[keep], gy[keep]

    def ground(x, y):
        lo, la = bw.transform(x, y)
        return dem.at(lo, la), dem.inside(lo, la)

    g, ok = ground(gx, gy)
    sl = np.zeros_like(gx)
    for dx, dy in ((5, 0), (0, 5)):
        ga, oa = ground(gx + dx, gy + dy); gb, ob = ground(gx - dx, gy - dy)
        ok &= oa & ob
        sl = np.maximum(sl, np.abs(ga - gb) / 10 * 100)
    ok &= sl <= MAX_SLOPE_PCT
    clear = np.full_like(gx, np.inf)
    if lidar_path:
        d = np.load(lidar_path)
        lx, ly = fw.transform(d["lon"], d["lat"])
        lg, lin = ground(lx, ly)
        hag = d["z_m"] - lg
        obs = (d["cls"] != 2) & lin & (hag > OBSTACLE_H_M)
        clear = cKDTree(np.c_[lx[obs], ly[obs]]).query(np.c_[gx, gy])[0]
        gnd = cKDTree(np.c_[lx[d["cls"] == 2], ly[d["cls"] == 2]]).query(np.c_[gx, gy])[0]
        ok &= gnd <= 3.0
    ok &= clear >= MIN_CLEAR_M
    if not ok.any():
        return None
    dist = np.array([poly.exterior.distance(Point(a, b)) if not poly.contains(Point(a, b)) else 0.0
                     for a, b in zip(gx, gy)])
    idx = np.flatnonzero(ok)
    i = idx[np.lexsort((sl[idx], -np.floor(clear[idx]), np.round(dist[idx])))][0]
    lo, la = bw.transform(gx[i], gy[i])
    return dict(lat=round(float(la), 7), lon=round(float(lo), 7),
                clearance_m=None if not np.isfinite(clear[i]) else round(float(clear[i]), 1),
                slope_pct=round(float(sl[i]), 1), dist_to_limits_m=round(float(dist[i]), 1))


# ---------------- summaries ----------------
COLS = ["plan", "pattern", "pitch_deg", "agl_m", "speed_mps", "lines", "waypoints", "photos", "minutes",
        "within_limit", "blur_px", "forward_overlap_pct", "side_overlap_pct", "min_clearance_above_dem_m"]


def _rows(rep):
    return [[f["file"][:-5], f["pattern"], f["pitch_deg"], rep["agl_m"], rep["speed_mps"], f["lines"], f["waypoints"],
             f["photos"], f["minutes"], f["within_limit"], rep["blur_px"], rep["forward_overlap_pct"],
             rep["side_overlap_pct"], f["min_clearance_above_dem_m"]] for f in rep["flights"]]


def _home_line(h):
    s = f"HOME: lat {h['lat']:.7f} lon {h['lon']:.7f}, ground {h['ground_m']:.2f} m"
    if h["needs_confirmation"]:
        c = "unknown (no lidar)" if h.get("clearance_m") is None else f"{h['clearance_m']} m"
        s += f" - SUGGESTED, CONFIRM IN FIELD (clearance to obstacles >2 m: {c}, slope {h['slope_pct']}%)"
    return s


def summaries(rep, limits, navs):
    """{filename: text} for <name>_flights.csv/.md/.kml. navs: {plan_name: [(lat, lon, amsl), ...]}."""
    name, rows, h = rep["name"], _rows(rep), rep["home"]
    b = io.StringIO(); w = csv.writer(b, lineterminator="\n"); w.writerow(COLS); w.writerows(rows)
    md = (f"# {name} camera flights\n\n{_home_line(h)}\n\n|" + "|".join(COLS) + "|\n|" + "---|" * len(COLS) + "\n"
          + "".join("|" + "|".join(str(c) for c in r) + "|\n" for r in rows)
          + f"\nTotal {rep['total_minutes']} min, {rep['photos']} photos, {rep['batteries']} batteries.\n")
    hn = "HOME (CONFIRM - suggested)" if h["needs_confirmation"] else "HOME"
    k = ['<?xml version="1.0" encoding="UTF-8"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
         f'<name>{name} flights</name>',
         f'<Placemark><name>{hn}</name><description>{_home_line(h)}</description><Point><coordinates>'
         f'{h["lon"]:.8f},{h["lat"]:.8f},0</coordinates></Point></Placemark>',
         '<Placemark><name>Survey limits</name><Style><LineStyle><color>ff0000ff</color><width>3</width></LineStyle>'
         '<PolyStyle><fill>0</fill></PolyStyle></Style><Polygon><outerBoundaryIs><LinearRing><coordinates>'
         + " ".join(f"{a},{c},0" for a, c in list(limits) + [limits[0]])
         + '</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>']
    cols = ["ff00ffff", "ff00ff00", "ffff8000", "ffff00ff", "ff0080ff"]
    for i, (n, nav) in enumerate(navs.items()):
        c = " ".join(f"{lo:.8f},{la:.8f},{z:.2f}" for la, lo, z in nav)
        k.append(f'<Placemark><name>{n}</name><Style><LineStyle><color>{cols[i % 5]}</color><width>2</width>'
                 f'</LineStyle></Style><LineString><altitudeMode>absolute</altitudeMode><coordinates>{c}'
                 '</coordinates></LineString></Placemark>')
    k.append("</Document></kml>")
    return {f"{name}_flights.csv": b.getvalue(), f"{name}_flights.md": md, f"{name}_flights.kml": "".join(k)}


# ---------------- saving ----------------
def _is_set_file(name, fn):
    return (fn.startswith(name + "_") and (fn.endswith(".plan") or fn in
            {f"{name}_flights.{e}" for e in ("csv", "md", "kml")} or fn == f"{name}_report.json"))


def save_set(src_dir, files, name, dests, reason="rerun", today=None):
    """Copy files (names in src_dir) to each dest (created if missing). An existing set of the same name
    (<name>_*.plan, <name>_flights.*, <name>_report.json) is first moved to superseded_<YYYYMMDD>_<reason>/.
    Nothing is deleted; other files are untouched. Returns {dest: superseded_dir or None}."""
    tag = re.sub(r"[^A-Za-z0-9]+", "_", reason).strip("_") or "rerun"
    day = (today or datetime.date.today()).strftime("%Y%m%d")
    out = {}
    for d in dests:
        os.makedirs(d, exist_ok=True)
        old = [f for f in os.listdir(d) if os.path.isfile(os.path.join(d, f)) and _is_set_file(name, f)]
        sup = None
        if old:
            sup, n = os.path.join(d, f"superseded_{day}_{tag}"), 2
            while os.path.exists(sup):
                sup, n = os.path.join(d, f"superseded_{day}_{tag}_{n}"), n + 1
            os.makedirs(sup)
            for f in old:
                shutil.move(os.path.join(d, f), os.path.join(sup, f))
        for f in files:
            shutil.copy2(os.path.join(src_dir, f), os.path.join(d, f))
        out[d] = sup
    return out
