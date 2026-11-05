"""Build a camera plan set (photogrammetry) on a custom DEM.

    py camera_plan_set.py config.json

config.json keys:
  name         plan-name prefix, e.g. "TooleCH"
  limits       [[lon, lat], ...] survey limits polygon (WGS84)
  home         [lat, lon]; omit to have one suggested (plan_outputs.suggest_home), flagged to confirm
  lidar        optional .npz (lon, lat, z_m, cls) giving obstacles for the HOME suggestion
  dem          GeoTIFF path, EPSG:4326, heights in metres (orthometric)
  payload      preset key in payloads.json (e.g. "lr1_24mm")
  agl_ft       flight height above the DEM
  shutter      1/x s (e.g. 1000)
  blur_px      motion-blur limit, pixels
  speed_margin fly this fraction slower than the blur limit allows (default 0.15)
  side_pct     nadir side overlap (default 80)
  buffer_m     nadir grid buffer around limits (default 25)
  patterns     list, default ["nadir"]; also "oblA" (along block axis), "oblB" (across);
               "orbit" is opt-in (see orbits.py for its keys)
  oblique_pitch gimbal pitch for oblA/oblB (default -45; goes in the file name)
  runout_m     oblique run-out past the limits (default 35)
  building     optional {"centroid": [lat, lon]} or {"footprint": [[lon, lat] x4]} -> wall check (walls.py; needs lidar)
  viz3d        optional true or {"nth": 10, "lidar": true} -> <name>_3D.html (viz3d.py)
  out_dir      output folder
  save_to      optional folders to save the set into (AMC Missions, project 3-To_Field/Flight_Plans; created if
               missing); a previous set of the same name moves to superseded_<YYYYMMDD>_<reason>/
  supersede_reason  tag for that folder (default "rerun")
Writes <name>_nadir90[_k].plan (plain waypoints, terrain-baked AMSL), <name>_flights.kml/.csv/.md
and <name>_report.json.
Exit 2 with a "refused" report (and no plans) when any flight path leaves the DEM.
"""
import json, math, os, sys
import numpy as np
import tifffile
import plan_outputs
from pyproj import Transformer
from shapely.geometry import Polygon, LineString

HERE = os.path.dirname(os.path.abspath(__file__))
FT = 0.3048
TRACK_TOL_M, MIN_WP_SPACING_M, MAX_WP_SPACING_M = 1.0, 10.0, 80.0


# ---------------- DEM ----------------
class Dem:
    def __init__(self, path):
        with tifffile.TiffFile(path) as tf:
            pg = tf.pages[0]
            tags = {t.name: t.value for t in pg.tags.values()}
            self.a = pg.asarray().astype(float)
        nod = tags.get("GDAL_NODATA")
        sx, sy = tags["ModelPixelScaleTag"][:2]
        tp = tags["ModelTiepointTag"]
        self.lo0, self.la0, self.dx, self.dy = tp[3] - tp[0] * sx, tp[4] + tp[1] * sy, sx, sy
        bad = ~np.isfinite(self.a) | (self.a < -9000)
        if nod is not None:
            try:
                bad |= self.a == float(str(nod).strip("\x00 "))
            except ValueError:
                pass
        self.valid = ~bad
        self.path = path

    def _rc(self, lo, la):
        return (self.la0 - np.asarray(la)) / self.dy - 0.5, (np.asarray(lo) - self.lo0) / self.dx - 0.5

    def inside(self, lo, la):
        r, c = self._rc(lo, la)
        H, W = self.a.shape
        ok = (r >= 0) & (c >= 0) & (r <= H - 1) & (c <= W - 1)
        ri = np.clip(np.round(r).astype(int), 0, H - 1)
        ci = np.clip(np.round(c).astype(int), 0, W - 1)
        return ok & self.valid[ri, ci]

    def at(self, lo, la):
        r, c = self._rc(lo, la)
        H, W = self.a.shape
        c0 = np.clip(np.floor(c).astype(int), 0, W - 2)
        r0 = np.clip(np.floor(r).astype(int), 0, H - 2)
        fc = np.clip(c - c0, 0, 1)
        fr = np.clip(r - r0, 0, 1)
        A = self.a
        return (A[r0, c0] * (1 - fc) * (1 - fr) + A[r0, c0 + 1] * fc * (1 - fr)
                + A[r0 + 1, c0] * (1 - fc) * fr + A[r0 + 1, c0 + 1] * fc * fr)


# ---------------- site / projection ----------------
class Site:
    def __init__(self, limits, home, dem):
        clo = float(np.mean([p[0] for p in limits]))
        cla = float(np.mean([p[1] for p in limits]))
        epsg = (32600 if cla >= 0 else 32700) + int((clo + 180) // 6) + 1
        self.fw = Transformer.from_crs(4326, epsg, always_xy=True)
        self.bw = Transformer.from_crs(epsg, 4326, always_xy=True)
        self.dem = dem
        self.poly = Polygon([self.fw.transform(*p) for p in limits])
        if home is not None:
            self.set_home(home)

    def set_home(self, home):
        self.home = (float(home[0]), float(home[1]))
        self.hx, self.hy = self.fw.transform(home[1], home[0])
        self.home_ground = float(self.ground(self.hx, self.hy))

    def ll(self, x, y):
        lo, la = self.bw.transform(x, y)
        return la, lo

    def ground(self, x, y):
        lo, la = self.bw.transform(np.asarray(x, float), np.asarray(y, float))
        return self.dem.at(lo, la)

    def inside(self, x, y):
        lo, la = self.bw.transform(np.asarray(x, float), np.asarray(y, float))
        return self.dem.inside(lo, la)


def block_axis(poly):
    """Unit vectors: u along the long side of the minimum rotated rectangle, v across it."""
    c = list(poly.minimum_rotated_rectangle.exterior.coords)
    e = [np.subtract(c[i + 1], c[i]) for i in range(2)]
    d = max(e, key=np.linalg.norm)
    u = d / np.linalg.norm(d)
    if u[0] < 0:
        u = -u
    return u, np.array([-u[1], u[0]])


# ---------------- camera ----------------
def camera_settings(pl, cfg):
    agl = cfg["agl_ft"] * FT
    gsd = pl["pixel_um"] * 1e-6 * agl / (pl["focal_mm"] * 1e-3)
    across = pl["sensor_w_mm"] / pl["focal_mm"] * agl   # long side across-track
    along = pl["sensor_h_mm"] / pl["focal_mm"] * agl
    v = round(cfg["blur_px"] * gsd * cfg["shutter"] * (1 - cfg.get("speed_margin", 0.15)), 1)
    trig = round(v * pl["min_trigger_s"], 2)
    side = cfg.get("side_pct", 80)
    return dict(agl_m=agl, gsd_m=gsd, fp_across_m=across, fp_along_m=along, speed_mps=v, trigger_m=trig,
                blur_px=v / cfg["shutter"] / gsd, forward_pct=100 * (1 - trig / along), side_pct=side,
                spacing_m=across * (1 - side / 100))


# ---------------- path building ----------------
def densify(site, a, b, agl):
    """Waypoints a->b at ground+agl: fewest points (10-80 m apart) keeping the straight-line
    interpolation within TRACK_TOL_M of ground+agl (minimax error, then excess, then count)."""
    p0, p1 = np.array(a, float), np.array(b, float)
    L = float(np.linalg.norm(p1 - p0))
    n = max(1, int(math.ceil(L)))
    step = L / n
    P = p0 + np.outer(np.linspace(0, 1, n + 1), p1 - p0)
    tgt = site.ground(P[:, 0], P[:, 1]) + agl
    if L < 2 * MIN_WP_SPACING_M:
        sel = [0, n]
    else:
        mn = int(math.ceil(MIN_WP_SPACING_M / step))
        mx = int(MAX_WP_SPACING_M / step)
        INF = (1e9, 1e9, 1e9)
        best = [INF] * (n + 1)
        prev = [-1] * (n + 1)
        best[0] = (0.0, 0.0, 0)
        for i in range(n + 1):
            if best[i] == INF:
                continue
            for j in range(i + mn, min(n, i + mx) + 1):
                if n - j and n - j < mn:
                    continue
                dev = np.abs(tgt[i] + (tgt[j] - tgt[i]) * np.arange(j - i + 1) / (j - i) - tgt[i:j + 1])
                e = math.ceil(max(TRACK_TOL_M, float(dev.max())) * 10) / 10
                c = (max(best[i][0], e), best[i][1] + float(np.clip(dev - TRACK_TOL_M, 0, None).sum()), best[i][2] + 1)
                if c < best[j]:
                    best[j] = c
                    prev[j] = i
        sel = [n]
        while sel[-1] != 0:
            sel.append(prev[sel[-1]])
        sel = sel[::-1]
    return [(P[q, 0], P[q, 1], float(tgt[q])) for q in sel]


def grid_lines(poly, u, v, spacing, runout):
    """Parallel lines along u, centred across v: (offset, s0, s1) clipped to poly, extended by runout."""
    T = [float(np.dot(c, v)) for c in poly.exterior.coords]
    S = [float(np.dot(c, u)) for c in poly.exterior.coords]
    t0, t1 = min(T), max(T)
    n = int(math.ceil((t1 - t0) / spacing)) + 1
    tc = (t0 + t1) / 2
    out = []
    for k in range(n):
        t = tc + (k - (n - 1) / 2) * spacing
        x = LineString([v * t + u * (min(S) - 10), v * t + u * (max(S) + 10)]).intersection(poly)
        if x.is_empty:
            continue
        cs = [float(np.dot(c, u)) for g in getattr(x, "geoms", [x]) for c in g.coords]
        out.append((t, min(cs) - runout, max(cs) + runout))
    return out


def line_flight(site, lines, u, v, agl, trig, k0=0):
    """HOME -> serpentine lines (206 on/off at line ends) -> HOME.
    Returns nav [(x, y, amsl)], plan body items, photo count, turn count."""
    H = (site.hx, site.hy)
    segs, cur = [], H
    for i, (t, s0, s1) in enumerate(lines):
        a, b = tuple(v * t + u * s0), tuple(v * t + u * s1)
        if (k0 + i) % 2:
            a, b = b, a
        segs += [("transit", cur, a), ("line", a, b)]
        cur = b
    segs.append(("transit", cur, H))
    home_wp = (site.hx, site.hy, site.home_ground + agl)
    nav, body, photos = [home_wp], [wp_item(site, *home_wp)], 0
    for typ, a, b in segs:
        full = densify(site, a, b, agl)
        if typ == "line":
            body.append(simple(206, [trig, 0, 1, 0, 0, 0, 0]))
            # photos per line from the 3D (terrain-following) path length between its waypoints
            photos += int(sum(math.dist(p, q) for p, q in zip(full[:-1], full[1:])) / trig) + 1
        pts = full[1:]
        if b == H:
            pts[-1] = home_wp
        for q in pts:
            nav.append(q)
            body.append(wp_item(site, *q))
        if typ == "line":
            body.append(simple(206, [0, 0, 0, 0, 0, 0, 0]))
    return nav, body, photos, max(0, 2 * len(lines) - 1)


# ---------------- plan items ----------------
def simple(cmd, params, frame=2):
    return {"autoContinue": True, "command": cmd, "doJumpId": 0, "frame": frame, "groupTag": 0,
            "params": params, "type": "SimpleItem"}


def wp_item(site, x, y, amsl):
    if abs(x - site.hx) < 1e-6 and abs(y - site.hy) < 1e-6:
        la, lo = site.home
    else:
        la, lo = site.ll(x, y)
    agl = amsl - float(site.ground(x, y))
    it = simple(16, [0, 0, 0, None, round(la, 8), round(lo, 8), round(amsl, 2)], 0)
    it.update(AMSLAltAboveTerrain=round(amsl, 2), Altitude=round(agl, 2), AltitudeMode=3)
    return it


def build_plan(site, speed, pitch, body):
    items = [simple(530, [0, 2, None, None, None, None, None]), simple(178, [1, speed, -1, 0, 0, 0, 0]),
             simple(205, [pitch, 0, 0, 0, 0, 0, 2])] + body
    for i, it in enumerate(items):
        it["doJumpId"] = i + 1
        it["MISSION_ITEM_ID"] = str(i)
    return {"fileType": "Plan", "geoFence": {"circles": [], "polygons": [], "version": 2},
            "groundStation": "QGroundControl",
            "mission": {"cruiseSpeed": 15, "firmwareType": 12, "globalPlanAltitudeMode": 3, "hoverSpeed": 10,
                        "items": items, "plannedHomePosition": [site.home[0], site.home[1], round(site.home_ground, 2)],
                        "vehicleType": 2, "version": 2},
            "rallyPoints": {"points": [], "version": 2}, "version": 1}


# ---------------- metrics ----------------
def flight_minutes(nav, speed, n_turns, tm):
    d = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(nav[:-1], nav[1:]))
    return (tm["distance_factor"] * d / speed + tm["turn_s"] * n_turns) / 60 + tm["overhead_min"], d


def sample_path(nav, step=1.0):
    X, Y, Z = [], [], []
    for a, b in zip(nav[:-1], nav[1:]):
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        s = np.linspace(0, 1, max(1, int(L / step)) + 1)
        X.append(a[0] + s * (b[0] - a[0]))
        Y.append(a[1] + s * (b[1] - a[1]))
        Z.append(a[2] + s * (b[2] - a[2]))
    return np.concatenate(X), np.concatenate(Y), np.concatenate(Z)


def tracking(site, nav, agl):
    """(max |alt - (DEM + agl)| along the flown path, min height above DEM)."""
    X, Y, Z = sample_path(nav)
    g = site.ground(X, Y)
    e = np.abs(Z - g - agl)
    return float(e.max()), float((Z - g).min())


def tracking_misses(site, nav, agl, tol=TRACK_TOL_M):
    """Stretches of the flown path where |alt - (DEM + agl)| > tol, each with its min clearance."""
    X, Y, Z = sample_path(nav)
    g = site.ground(X, Y)
    bad = np.abs(Z - g - agl) > tol
    out, i = [], 0
    while i < len(bad):
        if bad[i]:
            j = i
            while j < len(bad) and bad[j]:
                j += 1
            out.append(dict(length_m=j - i, max_err_m=round(float(np.abs(Z[i:j] - g[i:j] - agl).max()), 2),
                            min_clearance_m=round(float((Z[i:j] - g[i:j]).min()), 1)))
            i = j
        else:
            i += 1
    return out


# ---------------- patterns (ticket 03 adds oblique grids, ticket 07 orbits) ----------------
def split_by_battery(site, lines, u, v, cam, limit_min, tm):
    """Greedy: consecutive lines per flight while estimated minutes stay under the payload limit."""
    def est(a, b):
        nav, _, _, nt = line_flight(site, lines[a:b], u, v, cam["agl_m"], cam["trigger_m"], a)
        return flight_minutes(nav, cam["speed_mps"], nt, tm)[0]
    groups, i = [], 0
    while i < len(lines):
        j = i + 1
        while j < len(lines) and est(i, j + 1) < limit_min:
            j += 1
        groups.append((i, j))
        i = j
    return groups


def pattern_nadir(site, cam, cfg, limit_min, tm):
    u, v = block_axis(site.poly)
    area = site.poly.buffer(cfg.get("buffer_m", 25.0), join_style=2)
    lines = grid_lines(area, u, v, cam["spacing_m"], 0.0)
    groups = split_by_battery(site, lines, u, v, cam, limit_min, tm)
    base = f"{cfg['name']}_nadir90"
    return [dict(name=base if len(groups) == 1 else f"{base}_{q + 1}", pattern="nadir", pitch=-90, u=u, v=v,
                 lines=lines[a:b], k0=a, n_total=len(lines)) for q, (a, b) in enumerate(groups)]


def oblique_overlap(pl, cam, pitch, far_clip_m=300.0):
    """Per look direction (every second line looks the same way): forward overlap along the look
    and side overlap measured at the near edge (narrowest strip). Far-edge rays clipped at far_clip_m."""
    agl, f = cam["agl_m"], pl["focal_mm"]
    tilt = math.radians(90 + pitch)                       # off-nadir angle (-45 -> 45 deg)
    hfa = math.atan(pl["sensor_h_mm"] / 2 / f)            # half FOV along the look
    near = agl * math.tan(tilt - hfa)
    ctr = agl * math.tan(tilt)
    far = min(agl * math.tan(tilt + hfa) if tilt + hfa < math.pi / 2 else math.inf, far_clip_m)
    w_near = pl["sensor_w_mm"] * (agl / math.cos(tilt - hfa)) / math.hypot(pl["sensor_h_mm"] / 2, f)
    fwd_fp = min(2 * (ctr - near), far - near)
    return dict(near_m=round(near, 1), centre_m=round(ctr, 1), far_m=round(far, 1), near_width_m=round(w_near, 1),
                forward_pct=round(100 * (1 - cam["trigger_m"] / fwd_fp), 1),
                side_pct_near_edge=round(100 * (1 - 2 * cam["spacing_m"] / w_near), 1))


def _pattern_oblique(key, along):
    def pattern(site, cam, cfg, limit_min, tm):
        u0, v0 = block_axis(site.poly)
        u, v = (u0, v0) if along else (v0, -u0)
        buf = cfg.get("buffer_m", 25.0)
        area = site.poly.buffer(buf, join_style=2)
        runout = cfg.get("runout_m", 35.0)
        lines = grid_lines(area, u, v, cam["spacing_m"], max(0.0, runout - buf))
        groups = split_by_battery(site, lines, u, v, cam, limit_min, tm)
        pitch = cfg.get("oblique_pitch", -45)
        base = f"{cfg['name']}_{key}{abs(int(round(pitch)))}"
        return [dict(name=base if len(groups) == 1 else f"{base}_{q + 1}", pattern=key, pitch=pitch, u=u, v=v,
                     lines=lines[a:b], k0=a, n_total=len(lines)) for q, (a, b) in enumerate(groups)]
    return pattern


PATTERNS = {"nadir": pattern_nadir, "oblA": _pattern_oblique("oblA", True), "oblB": _pattern_oblique("oblB", False)}
from orbits import pattern_orbit  # noqa: E402  (opt-in; needs cfg "lidar" + "orbits")
PATTERNS["orbit"] = pattern_orbit


# ---------------- optional QA (walls.py, viz3d.py) ----------------
def building_qa(site, cfg, pl, plan_paths):
    """cfg "building" -> wall_check (+ QA PNG); cfg "viz3d" (true or {nth, lidar}) -> 3D HTML."""
    rep, L, b = {}, None, None
    if not (cfg.get("building") or cfg.get("viz3d")):
        return rep
    import walls
    if cfg.get("lidar"):
        L = walls.load_lidar(site, cfg["lidar"])
    if cfg.get("building"):
        if L is None:
            raise SystemExit("building wall check needs cfg 'lidar' (1 m surface model)")
        png = f"{cfg['name']}_walls_QA.png"
        wc = walls.wall_check(site, L, cfg["building"], plan_paths, pl, os.path.join(cfg["out_dir"], png))
        b = wc.pop("_box")
        rep["wall_check"] = dict(qa_png=png, **wc)
    if cfg.get("viz3d"):
        import viz3d
        v = cfg["viz3d"] if isinstance(cfg["viz3d"], dict) else {}
        rep["viz3d"] = viz3d.write_3d(site, plan_paths, pl, os.path.join(cfg["out_dir"], f"{cfg['name']}_3D.html"),
                                      L=L if v.get("lidar", True) else None, building=b, nth=v.get("nth", 10))
    return rep


# ---------------- entry ----------------
def build_camera_plan_set(cfg):
    table = json.load(open(os.path.join(HERE, "payloads.json")))
    pl, tm = table["payloads"][cfg["payload"]], table["time_model"]
    if pl["type"] != "camera":
        raise SystemExit(f"payload {cfg['payload']} is not a camera")
    out = cfg["out_dir"]
    os.makedirs(out, exist_ok=True)
    rep_path = os.path.join(out, f"{cfg['name']}_report.json")
    dem = Dem(cfg["dem"])
    site = Site(cfg["limits"], None, dem)
    cam = camera_settings(pl, cfg)
    limit = pl["flight_limit_min"]
    base = dict(name=cfg["name"], payload=pl.get("name", cfg["payload"]),
                config={k: v for k, v in cfg.items() if k != "out_dir"})

    def refuse(reason, ext):
        rep = dict(status="refused", reason=reason, **base, dem_extent=ext)
        json.dump(rep, open(rep_path, "w", newline="\n"), indent=1)
        return rep, 2

    if cfg.get("home"):
        home = dict(lat=cfg["home"][0], lon=cfg["home"][1], source="given", needs_confirmation=False)
    else:
        sug = plan_outputs.suggest_home(site.fw, site.bw, cfg["limits"], dem, cfg.get("lidar"))
        if sug is None:
            return refuse("No HOME given and no open, flat spot found near the limits; give one.", None)
        home = dict(sug, source="suggested", needs_confirmation=True)
    if not site.inside(*site.fw.transform(home["lon"], home["lat"])):
        return refuse("HOME is outside the DEM's valid area.", dict(ok=False, dem=dem.path, home_inside=False))
    site.set_home((home["lat"], home["lon"]))
    home["ground_m"] = round(site.home_ground, 2)
    specs = [s for p in cfg.get("patterns", ["nadir"]) for s in PATTERNS[p](site, cam, cfg, limit, tm)]
    built = [(s, *(s["built"] if "built" in s else
                   line_flight(site, s["lines"], s["u"], s["v"], cam["agl_m"], cam["trigger_m"], s["k0"]))) for s in specs]
    # DEM-extent check over every flight path (1 m samples) before anything is written
    outside = total = 0
    for _, nav, *_ in built:
        X, Y, _ = sample_path(nav)
        outside += int((~site.inside(X, Y)).sum())
        total += len(X)
    ext = dict(ok=outside == 0, dem=dem.path, home_inside=True, path_samples=total, samples_outside=outside)
    if outside:
        return refuse(f"Flight path leaves the DEM: {outside} of {total} 1-m path samples fall outside its valid area. "
                      "Supply a DEM covering the limits plus buffer/run-outs and HOME.", ext)
    flights, navs = [], {}
    for s, nav, body, photos, nt in built:
        fn = s["name"] + ".plan"
        plan = build_plan(site, cam["speed_mps"], s["pitch"], body)
        with open(os.path.join(out, fn), "wb") as f:
            f.write(json.dumps(plan, separators=(",", ":")).encode())
        navs[s["name"]] = [tuple(i["params"][4:7]) for i in body if i["command"] == 16]
        mins, dist = flight_minutes(nav, cam["speed_mps"], nt, tm)
        if "report" in s:   # non-grid patterns (orbits) report their own geometry
            flights.append(dict(file=fn, pattern=s["pattern"], pitch_deg=s["pitch"], photos=photos,
                                waypoints=sum(i["command"] == 16 for i in body), distance_m=round(dist, 1),
                                minutes=round(mins, 1), limit_min=limit, within_limit=mins <= limit, **s["report"]))
            continue
        err, clr = tracking(site, nav, cam["agl_m"])
        a = s["k0"]
        flights.append(dict(file=fn, pattern=s["pattern"], pitch_deg=s["pitch"],
                            lines=f"{a + 1}-{a + len(s['lines'])} of {s['n_total']}", n_lines=len(s["lines"]),
                            waypoints=sum(i["command"] == 16 for i in body), photos=photos,
                            distance_m=round(dist, 1), minutes=round(mins, 1), limit_min=limit,
                            within_limit=mins <= limit, terrain_tracking_max_err_m=round(err, 2),
                            min_clearance_above_dem_m=round(clr, 1),
                            terrain_tracking_misses=tracking_misses(site, nav, cam["agl_m"])))
    n_ph = sum(f["photos"] for f in flights)
    obl = {}
    for s in specs:
        if s["pattern"].startswith("obl") and s["pattern"] not in obl:
            ov = oblique_overlap(pl, cam, s["pitch"])
            obl[s["pattern"]] = [dict(look_bearing_deg=round(math.degrees(math.atan2(*d)) % 360, 1), **ov)
                                 for d in (s["u"], -s["u"])]
    extra = dict(overlap_by_look=obl, runout_m=cfg.get("runout_m", 35.0), far_clip_m=300.0) if obl else {}
    rep = dict(status="ok", **base, home=home, dem_extent=ext, **extra,
               speed_mps=cam["speed_mps"], speed_mph=round(cam["speed_mps"] * 2.23694, 1),
               agl_m=round(cam["agl_m"], 2), gsd_mm=round(cam["gsd_m"] * 1000, 2), blur_px=round(cam["blur_px"], 2),
               trigger_m=cam["trigger_m"], trigger_s=pl["min_trigger_s"],
               forward_overlap_pct=round(cam["forward_pct"], 1), side_overlap_pct=round(cam["side_pct"], 1),
               line_spacing_m=round(cam["spacing_m"], 2), flights=flights, batteries=len(flights),
               total_minutes=round(sum(f["minutes"] for f in flights), 1), photos=n_ph,
               gb=round(n_ph * pl.get("mb_per_photo", 0) / 1000, 1),
               clearance_note="Clearance is above the DEM (bare earth) only; obstacles need a surface-model check.",
               assumptions=f"Trigger: fixed {pl['min_trigger_s']:g} s interval set as cmd 206 distance. "
                           "Gimbal: cmd 205 pitch support unconfirmed - check on the first leg.")
    rep.update(building_qa(site, cfg, pl, [os.path.join(out, f["file"]) for f in flights]))
    outs = plan_outputs.summaries(rep, cfg["limits"], navs)
    for fn, txt in outs.items():
        with open(os.path.join(out, fn), "w", newline="\n") as f:
            f.write(txt)
    if cfg.get("save_to"):
        sup = plan_outputs.save_set(out, [f["file"] for f in flights] + list(outs), cfg["name"], cfg["save_to"],
                                    cfg.get("supersede_reason", "rerun"))
        rep["saved"] = [dict(folder=d, superseded_to=v) for d, v in sup.items()]
    json.dump(rep, open(rep_path, "w", newline="\n"), indent=1)
    return rep, 0


if __name__ == "__main__":
    rep, rc = build_camera_plan_set(json.load(open(sys.argv[1])))
    print(json.dumps({k: rep[k] for k in rep if k not in ("config", "flights")}, indent=1))
    for f in rep.get("flights", []):
        print(f)
    sys.exit(rc)
