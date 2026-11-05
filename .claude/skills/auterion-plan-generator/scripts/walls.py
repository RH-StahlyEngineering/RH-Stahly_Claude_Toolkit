"""Building-wall check for a camera plan set.

Building config (cfg["building"]):
  centroid   [lat, lon]  -> rectangle fitted from the lidar (cfg["lidar"]) around it, or
  footprint  [[lon, lat] x4] given corners;
  radius_m   search radius for the fit (default 25); roof_amsl optional override.
A sample point is seen by a photo when it is inside the frame, incidence <= 75 deg, and the ray is not
blocked by the building box or a 1 m lidar surface model (cells within 3 m of the box
are ignored: porches, steps and wall-hugging shrubs are not treated as walls). A wall passes when every point has >= 3 photos
from stations >= 15 deg apart and at least one oblique looks at the wall (heading within 45 deg of facing it).
"""
import json, math
import numpy as np
from scipy.spatial import ConvexHull
from scipy import ndimage

UP = np.array([0, 0, 1.0])
MAX_INC, MIN_PHOTOS, MIN_BASE_DEG, FACING_TOL = 75.0, 3, 15.0, 45.0


# ---------------- inputs ----------------
def load_lidar(site, path):
    d = np.load(path)
    c = d["cls"]
    keep = (c != 7) & (c != 18)
    x, y = site.fw.transform(d["lon"][keep], d["lat"][keep])
    return dict(x=np.asarray(x), y=np.asarray(y), z=d["z_m"][keep].astype(float), cls=c[keep])


def plan_photos(site, path):
    """Photo poses replayed from a .plan: (pos xyz, track xy, pitch, roi xyz|None) per photo.
    206 on fires at the current waypoint, then every trigger distance along the 3D path until 206 off."""
    it = json.load(open(path))["mission"]["items"]
    wps, ev = [], []
    for i in it:
        c, p = i["command"], i["params"]
        if c == 16:
            x, y = site.fw.transform(p[5], p[4]); wps.append((x, y, p[6]))
        elif c == 205: ev.append((len(wps) - 1, "pitch", p[0]))
        elif c == 206: ev.append((len(wps) - 1, "trig", p[0]))
        elif c == 197: ev.append((len(wps) - 1, "roi", None))
        elif c == 195:
            x, y = site.fw.transform(p[5], p[4]); ev.append((len(wps) - 1, "roi", (x, y, p[6])))
    wps = np.array(wps, float)
    evd = {}
    for k, ty, v in ev: evd.setdefault(max(k, 0), []).append((ty, v))
    out, pitch, roi, nxt, acc = [], -90.0, None, None, 0.0
    for k in range(len(wps)):
        for ty, v in evd.get(k, []):
            if ty == "pitch": pitch = v
            elif ty == "roi": roi = v
            elif ty == "trig":
                if v > 0:
                    out.append((wps[k], wps[min(k + 1, len(wps) - 1)] - wps[k], pitch, roi)); nxt, acc = v, 0.0
                else: nxt = None
        if k == len(wps) - 1 or nxt is None: continue
        a, b = wps[k], wps[k + 1]
        L = float(np.linalg.norm(b - a))
        if L == 0: continue
        s = nxt - acc
        while s <= L + 1e-9:
            out.append((a + (b - a) * s / L, b - a, pitch, roi)); s += nxt
        acc = L - (s - nxt)
    return out


def camera(pos, trk, pitch, roi):
    """Look axis, right and up unit vectors, compass heading of the look (None for nadir)."""
    h = np.array([trk[0], trk[1], 0.0])
    h = h / (np.linalg.norm(h) or 1)
    if roi is not None:
        ax = np.array(roi, float) - pos; ax /= np.linalg.norm(ax)
    else:
        p = math.radians(pitch); ax = math.cos(p) * h + math.sin(p) * UP
    rt = np.cross(h, UP) if abs(ax[2]) > 0.999 else np.cross(ax, UP)
    rt /= np.linalg.norm(rt)
    hdg = math.degrees(math.atan2(ax[0], ax[1])) % 360 if abs(ax[2]) < 0.999 else None
    return dict(pos=np.asarray(pos, float), ax=ax, rt=rt, uc=np.cross(rt, ax), hdg=hdg)


# ---------------- building fit ----------------
def _minbox(P):
    h = P[ConvexHull(P).vertices]
    best = None
    for i in range(len(h)):
        e = h[(i + 1) % len(h)] - h[i]
        a = math.atan2(e[1], e[0])
        R = np.array([[math.cos(a), math.sin(a)], [-math.sin(a), math.cos(a)]])
        q = h @ R.T
        mn, mx = q.min(0), q.max(0)
        if best is None or np.prod(mx - mn) < best[0]: best = (np.prod(mx - mn), R, mn, mx)
    return best[1:]


def fit_building(site, L, bcfg, cell=1.0):
    """Rectangle around the centroid from above-ground lidar on a 1 m max-z grid. Only smooth cells are kept
    (3x3 relief < 2.5 m: roof planes, not tree crowns), opened once to cut tree links,, and only the connected patch under the centroid."""
    if "footprint" in bcfg:
        C = np.array([site.fw.transform(lo, la) for lo, la in bcfg["footprint"]], float)
        cx, cy = C.mean(0)
    else:
        cx, cy = site.fw.transform(bcfg["centroid"][1], bcfg["centroid"][0])
    r = bcfg.get("radius_m", 25.0)
    near = np.hypot(L["x"] - cx, L["y"] - cy) < r + 3
    x, y, z = L["x"][near], L["y"][near], L["z"][near]
    hag = z - site.ground(x, y)
    n = int(2 * (r + 3) / cell) + 1
    j = ((x - cx + r + 3) / cell).astype(int).clip(0, n - 1)
    i = ((y - cy + r + 3) / cell).astype(int).clip(0, n - 1)
    G = np.full((n, n), -np.inf)
    np.maximum.at(G, (i, j), np.where(hag > 3, z, -np.inf))
    ok = np.isfinite(G)
    Gf = np.where(ok, G, np.nan)
    import warnings; warnings.simplefilter("ignore", RuntimeWarning)
    lo = ndimage.generic_filter(Gf, np.nanmin, 3, mode="constant", cval=np.nan)
    hi = ndimage.generic_filter(Gf, np.nanmax, 3, mode="constant", cval=np.nan)
    smooth = ok & ((hi - lo) < 2.5)
    smooth = ndimage.binary_closing(smooth, iterations=1) & ok
    lab, nl = ndimage.label(smooth)
    c0 = n // 2
    win = lab[c0 - 3:c0 + 4, c0 - 3:c0 + 4]
    ids = win[win > 0]
    pick = np.bincount(ids).argmax() if len(ids) else (np.bincount(lab[lab > 0]).argmax() if nl else 0)
    cells = ndimage.binary_opening((lab == pick) & (pick > 0))
    lab2, n2 = ndimage.label(cells)
    if n2: cells = lab2 == np.bincount(lab2[lab2 > 0]).argmax()
    if "footprint" not in bcfg:
        ii, jj = np.nonzero(cells)
        P = np.c_[cx - r - 3 + (jj + 0.5) * cell, cy - r - 3 + (ii + 0.5) * cell]
        R, mn, mx = _minbox(P)
        mn, mx = mn - cell / 2, mx + cell / 2
        C = np.array([[mn[0], mn[1]], [mx[0], mn[1]], [mx[0], mx[1]], [mn[0], mx[1]]]) @ R
    roof = bcfg.get("roof_amsl") or float(np.percentile(G[cells], 90)) if cells.any() else bcfg.get("roof_amsl")
    base = float(np.min(site.ground(C[:, 0], C[:, 1])))
    e = C[1] - C[0]
    a = math.atan2(e[1], e[0])
    R = np.array([[math.cos(a), math.sin(a)], [-math.sin(a), math.cos(a)]])
    q = C @ R.T
    return dict(corners=C, R=R, mn=q.min(0), mx=q.max(0), roof=float(roof), base=base,
                dims=sorted([float(np.linalg.norm(C[1] - C[0])), float(np.linalg.norm(C[2] - C[1]))]),
                n_cells=int(cells.sum()))


# ---------------- visibility ----------------
class Occluder:
    def __init__(self, L, b, half=250.0):
        self.b = b
        c = b["corners"].mean(0)
        self.x0, self.y0, self.n = c[0] - half, c[1] - half, int(2 * half)
        m = (np.abs(L["x"] - c[0]) < half) & (np.abs(L["y"] - c[1]) < half)
        j = (L["x"][m] - self.x0).astype(int).clip(0, self.n - 1)
        i = (L["y"][m] - self.y0).astype(int).clip(0, self.n - 1)
        D = np.full((self.n, self.n), -np.inf)
        np.maximum.at(D, (i, j), L["z"][m])
        self.D = D

    def blocked(self, cam, pts):
        """Per point: True if the camera->point ray is blocked by the box or a DSM cell (outside the box)."""
        b = self.b
        d = pts - cam["pos"]
        Ls = np.linalg.norm(d, axis=1)
        s = np.linspace(0, 1, 400)[None, :, None] * (1 - 0.6 / Ls)[:, None, None]
        Q = cam["pos"] + d[:, None, :] * s
        q = Q[..., :2] @ b["R"].T
        inbox = np.all((q > b["mn"] + 0.05) & (q < b["mx"] - 0.05), -1)
        box_hit = (inbox & (Q[..., 2] < b["roof"] - 0.05) & (Q[..., 2] > b["base"])).any(1)
        near_box = np.all((q > b["mn"] - 3) & (q < b["mx"] + 3), -1)
        far = np.hypot(Q[..., 0] - pts[:, None, 0], Q[..., 1] - pts[:, None, 1]) > 1.0
        i = np.floor(Q[..., 1] - self.y0).astype(int)
        j = np.floor(Q[..., 0] - self.x0).astype(int)
        ok = (i >= 0) & (i < self.n) & (j >= 0) & (j < self.n)
        hz = np.where(ok, self.D[i.clip(0, self.n - 1), j.clip(0, self.n - 1)], -np.inf)
        dsm_hit = ((hz > Q[..., 2] + 0.3) & far & ~near_box).any(1)
        return box_hit | dsm_hit


def seen(cam, pts, nrm, occ, f, sw, sh):
    d = pts - cam["pos"]
    zc = d @ cam["ax"]
    with np.errstate(all="ignore"):
        x = f * (d @ cam["rt"]) / zc; y = f * (d @ cam["uc"]) / zc
    ok = (zc > 0) & (np.abs(x) <= sw / 2) & (np.abs(y) <= sh / 2)
    cosi = (-d / np.linalg.norm(d, axis=1)[:, None]) @ nrm
    ok &= np.degrees(np.arccos(np.clip(cosi, -1, 1))) <= MAX_INC
    if ok.any():
        idx = np.flatnonzero(ok)
        ok[idx[occ.blocked(cam, pts[idx])]] = False
    return ok


def _sector(az): return "NESW"[int(((az + 45) % 360) // 90)]


def _point_pass(S, pts, cams):
    res = []
    for j in range(S.shape[1]):
        k = np.flatnonzero(S[:, j])
        if len(k) < MIN_PHOTOS: res.append(False); continue
        V = np.array([cams[i]["pos"] for i in k]) - pts[j]
        V /= np.linalg.norm(V, axis=1)[:, None]
        res.append(np.degrees(np.arccos(np.clip(V @ V.T, -1, 1))).max() >= MIN_BASE_DEG)
    return np.array(res)


# ---------------- entry ----------------
def wall_check(site, L, bcfg, plan_paths, pl, png_path):
    b = fit_building(site, L, bcfg)
    C, R, mn, mx, roof, base = b["corners"], b["R"], b["mn"], b["mx"], b["roof"], b["base"]
    occ = Occluder(L, b)
    f, sw, sh = pl["focal_mm"], pl["sensor_w_mm"], pl["sensor_h_mm"]
    cams = []
    for p in plan_paths:
        for ph in plan_photos(site, p):
            c = camera(*ph); c["plan"] = p; cams.append(c)
    cent = C.mean(0)
    walls = []
    for w in range(4):
        p0, p1 = C[w], C[(w + 1) % 4]
        Lw = float(np.linalg.norm(p1 - p0)); t = (p1 - p0) / Lw
        nrm = np.array([t[1], -t[0]])
        if nrm @ (p0 - cent) < 0: nrm = -nrm
        ss = np.linspace(1.5, Lw - 1.5, max(2, int(round(Lw / 3))))
        hs = [base + 1, (base + roof) / 2, roof - 1]
        pts = np.array([[*(p0 + s * t), h] for h in hs for s in ss])
        walls.append(dict(p0=p0, p1=p1, n=np.r_[nrm, 0], pts=pts, lev=np.repeat([0, 1, 2], len(ss)),
                          az=math.degrees(math.atan2(nrm[0], nrm[1])) % 360, L=Lw))
    u = np.linspace(mn[0] + 2, mx[0] - 2, 8); v = np.linspace(mn[1] + 2, mx[1] - 2, 8)
    U, V = np.meshgrid(u, v)
    roofp = np.c_[np.c_[U.ravel(), V.ravel()] @ R, np.full(U.size, roof)]
    out_walls = []
    for w in walls:
        S = np.array([seen(c, w["pts"], w["n"], occ, f, sw, sh) for c in cams])
        cnt = S.sum(0); pp = _point_pass(S, w["pts"], cams)
        sk = np.flatnonzero(S.any(1))
        dirs = {}
        for k in sk:
            key = "nadir" if cams[k]["hdg"] is None else "look " + _sector(cams[k]["hdg"])
            dirs[key] = dirs.get(key, 0) + 1
        facing = [k for k in sk if cams[k]["hdg"] is not None
                  and abs((cams[k]["hdg"] + 180 - w["az"] + 180) % 360 - 180) <= FACING_TOL]
        w.update(cnt=cnt, ok=bool(pp.all() and facing), name=_sector(w["az"]) + " face")
        out_walls.append(dict(name=w["name"], normal_az_deg=round(w["az"], 1), length_m=round(w["L"], 1),
                              points=len(cnt), min_photos_per_point=int(cnt.min()),
                              median_photos_per_point=float(np.median(cnt)), points_failing=int((~pp).sum()),
                              photos_seeing=len(sk), facing_oblique_photos=len(facing), directions=dirs,
                              min_by_level={lv: int(cnt[w["lev"] == i].min()) for i, lv in
                                            enumerate(("1 m", "mid", "roof-1 m"))}, **{"pass": w["ok"]}))
    rS = np.array([seen(c, roofp, UP, occ, f, sw, sh) for c in cams])
    rc = rS.sum(0); rp = _point_pass(rS, roofp, cams)
    roof_rep = {"points": len(rc), "min_photos_per_point": int(rc.min()), "median_photos_per_point": float(np.median(rc)),
                "points_failing": int((~rp).sum()), "pass": bool(rp.all())}
    _qa_png(png_path, C, roofp, rc, walls)
    lls = [site.ll(x, y) for x, y in C]
    return dict(_box=b, building=dict(corners_latlon=[[round(a, 7), round(o, 7)] for a, o in lls],
                              dims_m=[round(d, 1) for d in b["dims"]], roof_amsl=round(roof, 2),
                              base_amsl=round(base, 2), fit_cells=b["n_cells"],
                              source="footprint" if "footprint" in bcfg else "lidar fit (smooth above-ground cells)"),
                photos_checked=len(cams), walls=out_walls, roof=roof_rep,
                criteria=f"seen: in frame, incidence <= {MAX_INC:g} deg, not blocked by box or 1 m DSM; pass: every point "
                         f">= {MIN_PHOTOS} photos from stations >= {MIN_BASE_DEG:g} deg apart, >= 1 oblique facing the wall",
                **{"pass": bool(all(w["pass"] for w in out_walls) and roof_rep["pass"])})


def _qa_png(path, C, roofp, rc, walls):
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(13, 6), gridspec_kw=dict(width_ratios=[1.2, 1]))
    c0 = C.mean(0)
    vmax = max(6, max(int(w["cnt"].max()) for w in walls))
    a1.fill(*(np.r_[C, C[:1]] - c0).T, fc="#eee", ec="k")
    a1.scatter(*(roofp[:, :2] - c0).T, c=rc, cmap="RdYlGn", vmin=0, vmax=vmax, s=12, marker="s")
    sc = None
    for w in walls:
        off = w["n"][:2][None] * (1 + w["lev"][:, None] * 1.5)
        sc = a1.scatter(*(w["pts"][:, :2] + off - c0).T, c=w["cnt"], cmap="RdYlGn", vmin=0, vmax=vmax, s=40,
                        edgecolor="k", lw=.3)
        m_ = (w["p0"] + w["p1"]) / 2 + w["n"][:2] * 9 - c0
        a1.text(*m_, f"{w['name']}\nmin {w['cnt'].min()} {'PASS' if w['ok'] else 'FAIL'}", ha="center", va="center",
                fontsize=9, color="g" if w["ok"] else "r")
    a1.set_aspect("equal"); a1.margins(0.15); a1.set_xlabel("E (m from building centre)"); a1.set_ylabel("N (m)")
    a1.set_title("Photos per wall point (rows outward = 1 m, mid, roof-1 m; squares = roof)", fontsize=10)
    plt.colorbar(sc, ax=a1, label="photos seeing point")
    x = np.arange(4); wd = 0.35
    a2.bar(x - wd / 2, [w["cnt"].min() for w in walls], wd, label="min / point")
    a2.bar(x + wd / 2, [np.median(w["cnt"]) for w in walls], wd, label="median / point")
    a2.axhline(MIN_PHOTOS, color="r", ls="--", lw=1, label=f"threshold {MIN_PHOTOS}")
    a2.set_xticks(x, [w["name"] for w in walls]); a2.legend(fontsize=8); a2.set_title("Per-wall coverage")
    plt.tight_layout(); plt.savefig(path, dpi=110); plt.close(fig)
