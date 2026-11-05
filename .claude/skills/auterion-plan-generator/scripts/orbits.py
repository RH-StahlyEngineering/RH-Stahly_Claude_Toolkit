"""Opt-in orbit pattern for camera_plan_set (registered as PATTERNS["orbit"]).

cfg keys (only read when "orbit" is in cfg["patterns"]):
  lidar   .npz with lon, lat, z_m, cls (first returns; classes 7/18 = noise, dropped)
  orbits  [{center: [lat, lon], radius_m, height_m (ring above DEM at center),
            roi_height_m (aim point above DEM at center, default 6.5), n (waypoints, default 36)}]
Ring is flat at base + height_m; pitch = -atan(dz / r) to the aim point. Ring is raised (0.5 m steps)
until every ring point clears the highest lidar return within 15 m by >= 10 m; the raise is reported.
"""
import math
import numpy as np

CLEAR_M, CLEAR_R_M, NOISE = 10.0, 15.0, (7, 18)


def _lidar(site, path):
    d = np.load(path)
    k = ~np.isin(d["cls"], NOISE)
    x, y = site.fw.transform(d["lon"][k], d["lat"][k])
    return np.asarray(x), np.asarray(y), np.asarray(d["z_m"][k], float)


def _top_near(L, X, Y):
    lx, ly, lz = L
    out = []
    for x, y in zip(X, Y):
        m = (np.abs(lx - x) <= CLEAR_R_M) & (np.abs(ly - y) <= CLEAR_R_M)
        m[m] = np.hypot(lx[m] - x, ly[m] - y) <= CLEAR_R_M
        out.append(lz[m].max() if m.any() else -np.inf)
    return np.array(out)


def pattern_orbit(site, cam, cfg, limit_min, tm):
    import camera_plan_set as cps
    L = _lidar(site, cfg["lidar"])
    specs = []
    for o in cfg.get("orbits", []):
        cx, cy = site.fw.transform(o["center"][1], o["center"][0])
        base = float(site.ground(cx, cy))
        r, n = float(o["radius_m"]), int(o.get("n", 36))
        a0 = math.atan2(site.hy - cy, site.hx - cx)
        ang = a0 + 2 * math.pi * np.arange(n + 1) / n
        X, Y = cx + r * np.cos(ang), cy + r * np.sin(ang)
        # clearance on the ring itself, sampled every ~1 m
        s = np.linspace(0, 2 * math.pi, max(n, int(2 * math.pi * r)) + 1) + a0
        top = float(_top_near(L, cx + r * np.cos(s), cy + r * np.sin(s)).max())
        h0 = float(o["height_m"])
        need = top + CLEAR_M - base
        h = h0 if h0 >= need else math.ceil(need * 2) / 2
        amsl = base + h
        roi_amsl = base + float(o.get("roi_height_m", 6.5))
        pitch = round(-math.degrees(math.atan2(amsl - roi_amsl, r)), 1)
        trig = cam["trigger_m"]
        home_wp = (site.hx, site.hy, amsl)
        nav = [home_wp] + [(x, y, amsl) for x, y in zip(X, Y)] + [home_wp]
        rla, rlo = site.ll(cx, cy)
        body = [cps.wp_item(site, *home_wp),
                cps.simple(195, [0, 0, 0, 0, round(rla, 8), round(rlo, 8), round(roi_amsl, 2)], 0)]
        body += [cps.wp_item(site, *q) for q in nav[1:2]]
        body.append(cps.simple(206, [trig, 0, 1, 0, 0, 0, 0]))
        body += [cps.wp_item(site, *q) for q in nav[2:-1]]
        body += [cps.simple(206, [0, 0, 0, 0, 0, 0, 0]), cps.simple(197, [0, 0, 0, 0, 0, 0, 0]),
                 cps.wp_item(site, *home_wp)]
        photos = int(2 * math.pi * r / trig) + 1
        name = f"{cfg['name']}_orbit_r{r:g}_h{h:g}_p{abs(round(pitch))}"
        specs.append(dict(name=name, pattern="orbit", pitch=pitch, built=(nav, body, photos, 0),
                          report=dict(radius_m=r, height_m=h, requested_height_m=h0, raised_m=round(h - h0, 1),
                                      ring_amsl_m=round(amsl, 2), roi_amsl_m=round(roi_amsl, 2),
                                      min_lidar_clearance_m=round(amsl - top, 1),
                                      clearance_note=(f"Ring raised {h - h0:g} m (from {h0:g} to {h:g} m above base) "
                                                      f"for >= {CLEAR_M:g} m over lidar within {CLEAR_R_M:g} m.")
                                      if h > h0 else "Ring clears lidar by the required margin.")))
    return specs
