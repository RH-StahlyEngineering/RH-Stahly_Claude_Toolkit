"""
photo_overlap.py - effective photogrammetry overlap for one or more .plan files.

From the plan's own survey/corridor Items (the path AMC/PX4 will fly), with every image
footprint ray-cast onto the DEM:
  * nominal (flat-ground) forward / side overlap at the target AGL
  * EFFECTIVE forward overlap (endlap) - LINEAR, per consecutive photo pair, at 21 across-track
      positions; the pair's WORST position is the reported value (manned-spec convention:
      the minimum must hold at the highest relief - Pryor HRB Bull. 228; NJDOT; USACE EM
      1110-1-1000). The ASPRS Ed.2 Add. V area ratio is kept as a secondary figure.
  * EFFECTIVE side overlap (sidelap) - LINEAR, per photo, along the across-track chord through
      its nadir, against the NEAREST same-direction line actually imaged on each side at that
      along-track position (so seams between flights/tiles are measured correctly). Negative
      values are gaps. A side is a block edge (skipped) only when the gap lies outside the target area.
  * images per ground cell (multiplicity) with >=2/>=3/>=5/>=6 shares, lines and directions
  * per flight direction (each grid of a criss-cross) AND combined
  * GSD (nadir), worst-case motion blur, relief-within-frame, camera max-rate check
  * PASS/FAIL against source-backed overlap thresholds (see THRESHOLDS)

Camera: fixed nadir frame camera, pinhole. Default Phoenix A6K-Lite (Sony A6000 family:
23.5 x 15.6 mm, 6000 x 4000 px, 16 mm, max 1 image/s, 1/1000 s default shutter -
docs.phoenixlidar.com A6K-Lite specifications). Mount = sensor long side ACROSS-track (left-right
seen from above, flying forward) - confirmed by RH 2026-10-06.

Trigger (--trigger):
  auto     (default) the Phoenix Rover camera timer, --interval s (default 2.0: Phoenix docs say
           'The camera takes a photo every 2 seconds'; RH runs 1 or 2 s). The A6K-Lite is NOT fired by
           the autopilot - AMC's cmd 206 trigger-distance items are ignored unless --trigger plan.
  plan     autopilot cmd 206 (DO_SET_CAM_TRIGG_DIST): first shot at enable, then each time the
           distance from the last shot reaches the setting; not reset at bends (PX4 camera_trigger).
  time:S   payload timer every S s at the survey speed; photos in turns dropped.
  dist:M   payload distance trigger every M m along the photo legs.
Shots faster than the camera's max rate are thinned to what the camera can take (and flagged).

Usage:
  python photo_overlap.py A.plan [B.plan ...] [--use colorize|ortho|sfm] [--target area.kml]
         [--orientation across|along] [--trigger auto|plan|time:1.0|dist:10] [--interval 1.0]
         [--shutter 1000] [--dem-meta path.json] [--ground-offset 0.0] [--json out.json]
Several plans: each plan alone, then all combined (seams between flights are measured).

LIMITS (printed with every report):
  * camera exactly nadir - in-flight roll/pitch (~2 % overlap per degree, Pryor) not modelled
  * altitude between Items = linear AMSL interpolation (PX4 v1.14/1.15 behaviour)
  * ground = bare-earth DEM; canopy/buildings raise the surface -> less overlap there
  * standalone outer items (cross-line, figure-8) are not counted
"""
import argparse
import json
import math
import os
import sys
import xml.etree.ElementTree as ET

import numpy as np
import shapely
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dem_lookup  # noqa: E402

MLAT = 111132.0
CAMERAS = {"a6k-lite": dict(sensor_w=23.5, sensor_h=15.6, focal=16.0, px_w=6000, px_h=4000,
                            max_rate_hz=1.0, mount_note="long side ACROSS-track (RH confirmed 2026-10-06)")}
TRIG_DIST, IMG_START, IMG_STOP = 206, 2000, 2001
TURN_TOL = 20.0           # deg: legs/photos this far off a line direction are turns/connectors
MIN_LINE_LEN = 20.0       # m
N_ACROSS = 21             # across-track samples for linear endlap


# (name, forward_min, side_min, uses it applies to, source)
THRESHOLDS = [
    ("ASPRS Ed2 Add.III SfM", 0.75, 0.65, {"sfm"}, "publicdocuments.asprs.org/PositionalAccuracyStd-Ed2-V2"),
    ("ASPRS Ed2 Add.V UAS typical", 0.80, 0.60, {"ortho", "sfm"}, "same, Add. V A.5.4"),
    ("Pix4D general (per grid)", 0.75, 0.60, {"ortho", "sfm"}, "support.pix4d.com/hc/en-us/articles/202557459"),
    ("NDDOT UAS", 0.75, 0.75, {"sfm"}, "dot.nd.gov Surveying-UAS-Guidelines.pdf"),
    ("NCDOT UAS", 0.85, 0.80, {"sfm"}, "connect.ncdot.gov UAS Camera Requirements"),
    ("MDT Survey Manual 7.4 (manned)", 0.55, 0.30, {"ortho"}, "mdt.mt.gov Survey-Manual-Chapter-7.pdf"),
    ("USACE EM 1110-1-1000 relief floor", 0.55, 0.10, {"colorize", "ortho"}, "EM-1110-1-1000 (2002) ch.5"),
]
USE_NOTE = {
    "colorize": "ASPRS Add.V A.5.5: sidelap 'less strict' when imagery only colorizes lidar",
    "ortho": "orthophoto: ASPRS Add.V ~80/60 typical; MDT 7.7 says UAS overlap 'generally higher' than manned",
    "sfm": "stand-alone photogrammetry/SfM: ASPRS Add.III 75-85 % end / 65-75 % side",
}


# ----------------------------------------------------------------------------- geometry / DEM
class Frame:
    def __init__(self, lat0, lon0):
        self.lat0, self.lon0 = lat0, lon0
        self.mlon = MLAT * math.cos(math.radians(lat0))

    def xy(self, lat, lon):
        return (np.asarray(lon) - self.lon0) * self.mlon, (np.asarray(lat) - self.lat0) * MLAT

    def ll(self, x, y):
        return self.lat0 + np.asarray(y) / MLAT, self.lon0 + np.asarray(x) / self.mlon


class Dem:
    """Vectorised bilinear sampler over the dem_lookup raster (no HTTP fallback)."""

    def __init__(self, fr, ground_offset):
        dem_lookup._try_load_local_dem()
        if dem_lookup._local_dem is None or not dem_lookup._local_meta:
            raise SystemExit("no DEM raster loaded")
        self.a = np.asarray(dem_lookup._local_dem, dtype=float)
        self.m = dem_lookup._local_meta
        self.fr, self.off = fr, ground_offset

    def at_xy(self, x, y):
        lat, lon = self.fr.ll(x, y)
        m = self.m
        lat = np.asarray(lat, float); lon = np.asarray(lon, float)
        if (lat.min() < m["lat_min"] or lat.max() > m["lat_max"] or
                lon.min() < m["lon_min"] or lon.max() > m["lon_max"]):
            raise SystemExit("point outside DEM raster - widen the DEM bbox")
        fy = (m["lat_max"] - lat) / (m["lat_max"] - m["lat_min"]) * (m["rows"] - 1)
        fx = (lon - m["lon_min"]) / (m["lon_max"] - m["lon_min"]) * (m["cols"] - 1)
        y0 = np.clip(np.floor(fy).astype(int), 0, m["rows"] - 1); x0 = np.clip(np.floor(fx).astype(int), 0, m["cols"] - 1)
        y1 = np.minimum(y0 + 1, m["rows"] - 1); x1 = np.minimum(x0 + 1, m["cols"] - 1)
        dy, dx = fy - y0, fx - x0
        v = (self.a[y0, x0] * (1 - dx) * (1 - dy) + self.a[y0, x1] * dx * (1 - dy)
             + self.a[y1, x0] * (1 - dx) * dy + self.a[y1, x1] * dx * dy)
        if not np.all(np.isfinite(v)) or np.any(v < -100):
            raise SystemExit("DEM nodata under the flight - widen/replace the DEM")
        return v + self.off


def ang_diff180(a, b):
    return abs(((a - b + 90.0) % 180.0) - 90.0)


# ----------------------------------------------------------------------------- plan parsing
def load_plan(path):
    p = json.load(open(path, encoding="utf-8"))
    m = p["mission"]
    out = dict(name=os.path.basename(path), home=m["plannedHomePosition"], complex=[])
    for it in m["items"]:
        if it.get("type") != "ComplexItem":
            continue
        ts = it.get("TransectStyleComplexItem", {})
        if not ts.get("Items"):
            raise SystemExit(f"{out['name']}: complex item has no Items - open+save in AMC (or generate Items) first")
        cc = ts.get("CameraCalc", {})
        poly = it.get("polygon")
        if poly is None and it.get("polyline"):
            poly = ("polyline", it["polyline"], float(it.get("CorridorWidth", 0)))
        out["complex"].append(dict(kind=it.get("complexItemType"), angle=it.get("angle"), poly=poly,
                                   items=ts["Items"], speed=float(ts.get("FlightSpeed") or 0),
                                   agl=float(cc.get("DistanceToSurface") or 0),
                                   spacing=float(cc.get("AdjustedFootprintSide") or 0),
                                   refly90=bool(ts.get("Refly90Degrees"))))
    if not out["complex"]:
        raise SystemExit(f"{out['name']}: no Survey/CorridorScan complex item")
    sp = [i["params"][1] for i in m["items"] if i.get("command") == 178]
    out["cmd178"] = float(sp[0]) if sp else None
    return out


def walk_items(cx, home_alt, dem, fr):
    """Waypoints [x, y, z_amsl, trig_dist_after] in Items order."""
    wps, trig = [], 0.0
    for i in cx["items"]:
        c = i.get("command")
        if c == TRIG_DIST:
            trig = float(i["params"][0] or 0.0)
        elif c == 16:
            lat, lon, alt = i["params"][4], i["params"][5], i["params"][6]
            x, y = fr.xy(lat, lon)
            f = i.get("frame", 0)
            if f == 0:
                z = float(alt)
            elif f == 3:
                z = float(home_alt) + float(alt)
            elif f == 10:
                z = float(dem.at_xy(np.array([x]), np.array([y]))[0]) + float(alt)
            else:
                raise SystemExit(f"unsupported waypoint frame {f}")
            wps.append([float(x), float(y), z, trig])
        if wps:
            wps[-1][3] = trig
    return wps


def line_dirs(cx):
    a = cx["angle"]
    if a is None or cx["kind"] != "survey":
        return None
    d = [float(a) % 180.0]
    if cx["refly90"]:
        d.append((float(a) + 90.0) % 180.0)
    return d


def stations(tag, cx, wps, mode, step):
    """Exposure stations along the Items path.
    plan    : while cmd-206 distance > 0; first shot at enable; distance carried across bends.
    payload : every `step` m along the whole path (timer runs through turns); photos kept only
              on photo legs (trigger-on legs if the plan has cmd 206, else on-direction legs)."""
    dirs = line_dirs(cx)
    has_trig = any(w[3] > 0 for w in wps)
    out, carry, prev_photo, prev_hd, line_id = [], 0.0, False, None, 0
    for k in range(len(wps) - 1):
        x0, y0, z0, trig = wps[k]
        x1, y1, z1 = wps[k + 1][:3]
        L = math.hypot(x1 - x0, y1 - y0)
        if L < 1e-6:
            continue
        hd = math.atan2(x1 - x0, y1 - y0)
        hdeg = math.degrees(hd) % 180.0
        on_dir = (dirs is None) or min(ang_diff180(hdeg, d) for d in dirs) <= TURN_TOL
        if mode == "plan":
            photo, s_step = trig > 0, (trig if trig > 0 else None)
            if photo and s_step < step:
                s_step = step                       # camera max rate (step = min spacing)
        else:
            photo = (trig > 0) if has_trig else (on_dir and L >= MIN_LINE_LEN)
            s_step = step
        turned = prev_hd is not None and abs(((math.degrees(hd - prev_hd) + 180) % 360) - 180) > TURN_TOL
        if photo and (not prev_photo or turned):
            line_id += 1
        if mode == "plan":
            if photo and not prev_photo:
                carry = 0.0                         # PX4: shoot at enable
            if not photo:
                prev_photo, prev_hd = False, hd
                continue
        s = carry
        while s <= L + 1e-9:
            if photo:
                t = s / L
                out.append(dict(x=x0 + t * (x1 - x0), y=y0 + t * (y1 - y0), z=z0 + t * (z1 - z0),
                                hd=hd, hdeg=hdeg, line=f"{tag}#{line_id}", on_dir=on_dir))
            s += s_step
        carry = s - L
        prev_photo, prev_hd = photo, hd
    return out


# ----------------------------------------------------------------------------- ray casting
def cast(st, dem, sa, sc, tan_al, tan_ac, iters=6):
    """Ground points for image-plane fractions (sa along, sc across in [-1,1]) for all stations.
    Fixed-point on height above the hit point. Returns gx, gy, h (height above that point)."""
    X, Y, Z, H = st["X"], st["Y"], st["Z"], st["H"]
    ax, ay, cx_, cy_ = np.sin(H), np.cos(H), np.cos(H), -np.sin(H)
    h = Z - dem.at_xy(X, Y)
    for _ in range(iters):
        gx = X + h * (sa * tan_al * ax + sc * tan_ac * cx_)
        gy = Y + h * (sa * tan_al * ay + sc * tan_ac * cy_)
        h = np.maximum(Z - dem.at_xy(gx, gy), 0.5)
    return gx, gy, h


def ring_params(n_side=4):
    """Boundary of the image plane, counter-clockwise, n_side segments per edge."""
    t = np.linspace(-1, 1, n_side + 1)[:-1]
    return ([(-1, s) for s in t] + [(s, 1) for s in t] + [(1, -s) for s in t] + [(-s, -1) for s in t])


def footprints(stl, dem, tan_al, tan_ac):
    st = dict(X=np.array([s["x"] for s in stl]), Y=np.array([s["y"] for s in stl]),
              Z=np.array([s["z"] for s in stl]), H=np.array([s["hd"] for s in stl]))
    ring = ring_params()
    pts, hs = [], []
    for sa, sc in ring:
        gx, gy, h = cast(st, dem, sa, sc, tan_al, tan_ac)
        pts.append(np.stack([gx, gy], 1)); hs.append(h)
    pts = np.stack(pts, 1); hs = np.stack(hs, 1)
    h0 = st["Z"] - dem.at_xy(st["X"], st["Y"])
    terr = st["Z"][:, None] - hs
    # linear endlap samples: leading (sa=+1) and trailing (sa=-1) edges at N_ACROSS positions
    cs = np.linspace(-1, 1, N_ACROSS)
    lead = np.stack([np.stack(cast(st, dem, +1, c, tan_al, tan_ac)[:2], 1) for c in cs], 1)
    trail = np.stack([np.stack(cast(st, dem, -1, c, tan_al, tan_ac)[:2], 1) for c in cs], 1)
    # across-track edges at nadir along-position, for side overlap
    left = np.stack(cast(st, dem, 0, -1, tan_al, tan_ac)[:2], 1)
    right = np.stack(cast(st, dem, 0, +1, tan_al, tan_ac)[:2], 1)
    for i, s in enumerate(stl):
        s["fp"] = Polygon(pts[i]).buffer(0)
        s["h_nadir"] = float(h0[i]); s["h_min"] = float(hs[i].min())
        s["relief"] = float(terr[i].max() - terr[i].min())
        s["lead"], s["trail"], s["left"], s["right"] = lead[i], trail[i], left[i], right[i]
    return stl


# ----------------------------------------------------------------------------- metrics
def stats(v):
    v = np.asarray(v, float)
    if v.size == 0:
        return None
    return dict(n=int(v.size), min=float(v.min()), p05=float(np.percentile(v, 5)),
                median=float(np.median(v)), mean=float(v.mean()), max=float(v.max()))


def forward_overlap(stl):
    """Per consecutive pair: worst-position LINEAR endlap, centre-line endlap, ASPRS area ratio."""
    worst, centre, area, by = [], [], [], {}
    for s in stl:
        by.setdefault(s["line"], []).append(s)
    for ln in by.values():
        for a, b in zip(ln, ln[1:]):
            ux, uy = math.sin(a["hd"]), math.cos(a["hd"])
            ta = lambda p: (p[..., 0] - a["x"]) * ux + (p[..., 1] - a["y"]) * uy
            la, tr_a, tr_b = ta(a["lead"]), ta(a["trail"]), ta(b["trail"])
            e = (la - tr_b) / (la - tr_a)
            worst.append(float(e.min())); centre.append(float(e[N_ACROSS // 2]))
            if a["fp"].area > 0 and b["fp"].area > 0:
                ov = a["fp"].intersection(b["fp"]).area
                area.append(min(ov / a["fp"].area, ov / b["fp"].area))
    return worst, centre, area


def intervals(geom, org, dv):
    """1-D intervals (param along unit dv from org) of the line parts of geom on one chord.
    1-D because intersecting separately computed collinear 2-D segments is numerically empty."""
    out = []
    for g in getattr(geom, "geoms", [geom]):
        cs = list(getattr(g, "coords", []))
        if len(cs) >= 2:
            ts = [(c[0] - org[0]) * dv[0] + (c[1] - org[1]) * dv[1] for c in cs]
            out.append((min(ts), max(ts)))
    return out


def merge(iv):
    iv = sorted(iv); out = []
    for a, b in iv:
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def overlap_len(ia, ib):
    """Shared length; if the strips do not touch, minus the gap (gap reads as negative overlap)."""
    ov = sum(max(0.0, min(a1, b1) - max(a0, b0)) for a0, a1 in ia for b0, b1 in ib)
    if ov > 0 or not ia or not ib:
        return ov
    return -min(max(b0 - a1, a0 - b1) for a0, a1 in ia for b0, b1 in ib)


def side_overlap(stl, spacing, area):
    """Per photo and side: signed linear sidelap along the across-track chord through the photo's
    nadir (perpendicular to its heading).

    On each side, the footprints of every OTHER same-direction line (>= 3 photos) whose nadir is on
    that side are unioned along the chord. Sidelap = the part of this photo's chord covered by the
    union piece that contains this photo's edge (so grazing corner hits from one footprint cannot
    understate it). If no piece reaches the edge, the gap to the nearest piece is reported as a
    negative value, unless the gap lies outside the target area (= block edge, skipped). A side with
    no same-direction footprints on the chord is a block edge."""
    fps = [s["fp"] for s in stl]
    tree = shapely.STRtree(fps)
    n_in_line = {}
    for s in stl:
        n_in_line[s["line"]] = n_in_line.get(s["line"], 0) + 1
    vals, seams = [], []
    for s in stl:
        ux, uy = math.sin(s["hd"]), math.cos(s["hd"])
        dv = (uy, -ux)                                  # across-track (right)
        org = (s["x"], s["y"])
        ta = sorted(((p[0] - org[0]) * dv[0] + (p[1] - org[1]) * dv[1]) for p in (s["left"], s["right"]))
        la = ta[1] - ta[0]
        if la <= 0:
            continue
        reach = 4.0 * max(la, spacing)
        chord = LineString([(org[0] - dv[0] * reach, org[1] - dv[1] * reach),
                            (org[0] + dv[0] * reach, org[1] + dv[1] * reach)])
        per_side = {1: [], -1: []}
        for k in tree.query(chord):
            o = stl[k]
            if (o["line"] == s["line"] or n_in_line[o["line"]] < 3
                    or ang_diff180(o["hdeg"], s["hdeg"]) > TURN_TOL):
                continue
            t_o = (o["x"] - org[0]) * dv[0] + (o["y"] - org[1]) * dv[1]
            if abs(t_o) < 1.0:
                continue                                 # coincident line (duplicate pass), not a neighbour
            for a, b in intervals(o["fp"].intersection(chord), org, dv):
                per_side[1 if t_o > 0 else -1].append((a, b, o["line"]))
        plan = s["line"].split("#")[0]
        for side, ivs in per_side.items():
            if not ivs:
                continue                                 # nothing on this side: block edge
            ivs.sort()
            pieces = []                                  # [a, b, {lines}]
            for a, b, l in ivs:
                if pieces and a <= pieces[-1][1]:
                    pieces[-1][1] = max(pieces[-1][1], b); pieces[-1][2].add(l)
                else:
                    pieces.append([a, b, {l}])
            edge = ta[1] if side > 0 else ta[0]
            hit = [p for p in pieces if p[0] <= edge <= p[1]]
            if hit:
                p = hit[0]
                q = (min(ta[1], p[1]) - max(ta[0], p[0])) / la
            else:
                beyond = [p for p in pieces if (p[0] > edge if side > 0 else p[1] < edge)]
                if not beyond:
                    continue
                p = min(beyond, key=lambda p: (p[0] - edge) if side > 0 else (edge - p[1]))
                gap = (p[0] - edge) if side > 0 else (edge - p[1])
                tm = edge + side * gap / 2.0
                if area is not None and not area.is_empty and not area.contains(
                        Point(org[0] + dv[0] * tm, org[1] + dv[1] * tm)):
                    continue                             # gap outside the target: block edge
                q = -gap / la
            vals.append(q)
            if all(l.split("#")[0] != plan for l in p[2]):
                seams.append(q)
    return vals, seams


def target_area(plans, target_kml, fr):
    if target_kml:
        polys = []
        for el in ET.parse(target_kml).iter():
            if el.tag.endswith("coordinates") and el.text:
                pts = [tuple(map(float, t.split(",")[:2])) for t in el.text.split()]
                if len(pts) >= 4:
                    xs, ys = fr.xy([p[1] for p in pts], [p[0] for p in pts])
                    polys.append(Polygon(list(zip(xs, ys))).buffer(0))
        return unary_union(polys)
    parts = []
    for pl in plans:
        for cx in pl["complex"]:
            poly = cx["poly"]
            if isinstance(poly, tuple):
                _, line, w = poly
                xs, ys = fr.xy([q[0] for q in line], [q[1] for q in line])
                parts.append(LineString(list(zip(xs, ys))).buffer(w / 2.0, cap_style=2))
            elif poly:
                xs, ys = fr.xy([q[0] for q in poly], [q[1] for q in poly])
                parts.append(Polygon(list(zip(xs, ys))).buffer(0))
    return unary_union(parts)


def multiplicity(stl, area, n_dirs):
    if area.is_empty or not stl:
        return None
    step = max(1.0, math.sqrt(area.area / 250000.0))
    minx, miny, maxx, maxy = area.bounds
    gx, gy = np.meshgrid(np.arange(minx + step / 2, maxx, step), np.arange(miny + step / 2, maxy, step))
    ins = shapely.contains_xy(area, gx, gy)
    gx, gy = gx[ins], gy[ins]
    cnt = np.zeros(gx.size, np.int32)
    lids = sorted({s["line"] for s in stl}); li = {l: k for k, l in enumerate(lids)}
    fids = sorted({str(s["fam"]) for s in stl if s["fam"] is not None}); fi = {f: k for k, f in enumerate(fids)}
    seen_l = np.zeros((len(lids), gx.size), bool); seen_f = np.zeros((max(1, len(fids)), gx.size), bool)
    for s in stl:
        b = s["fp"].bounds
        m = (gx >= b[0]) & (gx <= b[2]) & (gy >= b[1]) & (gy <= b[3])
        if not m.any():
            continue
        idx = np.nonzero(m)[0]
        hit = idx[shapely.contains_xy(s["fp"], gx[idx], gy[idx])]
        cnt[hit] += 1
        seen_l[li[s["line"]], hit] = True
        if s["fam"] is not None:
            seen_f[fi[str(s["fam"])], hit] = True
    pct = lambda m: 100 * float(m.mean())
    return dict(cell_m=step, cells=int(gx.size), images=stats(cnt), zero=pct(cnt == 0),
                ge2=pct(cnt >= 2), ge3=pct(cnt >= 3), ge5=pct(cnt >= 5), ge6=pct(cnt >= 6),
                ge2_lines=pct(seen_l.sum(0) >= 2),
                ge2_dirs=(pct(seen_f.sum(0) >= 2) if n_dirs >= 2 else None))


def block_metrics(stl, area, spacing, n_dirs):
    w, c, a = forward_overlap(stl)
    side, seams = side_overlap(stl, spacing, area)
    return dict(photos=len(stl), lines=len({s["line"] for s in stl}),
                forward=stats(w), forward_centre=stats(c), forward_area=stats(a),
                side=stats(side), side_seams=stats(seams), multiplicity=multiplicity(stl, area, n_dirs))


# ----------------------------------------------------------------------------- driver
def analyse(name, plans, mode, args, dem, fr, cam, area):
    tan_long, tan_short = cam["sensor_w"] / 2 / cam["focal"], cam["sensor_h"] / 2 / cam["focal"]
    tan_ac, tan_al = (tan_long, tan_short) if args.orientation == "across" else (tan_short, tan_long)
    allst, nominal, rate_flags, groups = [], [], [], []
    for pl in plans:
        for ci, cx in enumerate(pl["complex"]):
            wps = walk_items(cx, pl["home"][2], dem, fr)
            speed = cx["speed"] or pl["cmd178"] or 8.0
            min_step = speed / cam["max_rate_hz"]
            trig = sorted({round(w[3], 3) for w in wps if w[3] > 0})
            if mode == "plan":
                want = trig[0] if trig else None
            elif mode.startswith("time:"):
                want = speed * float(mode.split(":")[1])
            else:
                want = float(mode.split(":")[1])
            if want is None:
                continue
            step = max(want, min_step)
            if want < min_step - 1e-6:
                rate_flags.append(f"{pl['name']}: asked {want:.2f} m = {want/speed:.2f} s/shot < camera max "
                                  f"{1/cam['max_rate_hz']:.2f} s -> thinned to {step:.2f} m (best case; "
                                  f"if the payload skips busy pulses spacing is {math.ceil(min_step/want)*want:.2f} m)")
            st = stations(f"{pl['name']}/{ci}", cx, wps, "plan" if mode == "plan" else "payload", step)
            groups.append((st, line_dirs(cx)))
            if cx["agl"]:
                G_al, G_ac = 2 * cx["agl"] * tan_al, 2 * cx["agl"] * tan_ac
                nominal.append(dict(plan=pl["name"], agl=cx["agl"], speed=speed, base_m=step,
                                    shot_s=step / speed, line_spacing_m=cx["spacing"],
                                    footprint_along_m=G_al, footprint_across_m=G_ac, forward=1 - step / G_al,
                                    side=(1 - cx["spacing"] / G_ac) if cx["spacing"] else None,
                                    gsd_cm=100 * cx["agl"] * (cam["sensor_w"] / cam["px_w"]) / cam["focal"],
                                    refly90=cx["refly90"]))
            allst.extend(st)
    if not allst:
        return dict(name=name, mode=mode, error="no photos (trigger never enabled?)")
    # flight-direction families: cluster every plan's grid angles within TURN_TOL (mod 180), so tiles
    # re-angled by a few degrees stay ONE grid (their seams then reach the per-grid table)
    clusters = []                                       # [sum_cos2, sum_sin2]
    for _, dirs in groups:
        for d in (dirs or []):
            r = math.radians(2 * d)
            for c in clusters:
                if ang_diff180(d, math.degrees(math.atan2(c[1], c[0])) / 2 % 180) <= TURN_TOL:
                    c[0] += math.cos(r); c[1] += math.sin(r); break
            else:
                clusters.append([math.cos(r), math.sin(r)])
    dirs_all = [round(math.degrees(math.atan2(c[1], c[0])) / 2 % 180, 1) for c in clusters]
    for st, dirs in groups:
        for s in st:
            if not dirs:
                s["fam"] = "corridor"
                continue
            f = min(dirs_all, key=lambda d: ang_diff180(s["hdeg"], d))
            s["fam"] = f if ang_diff180(s["hdeg"], f) <= TURN_TOL else None
    footprints(allst, dem, tan_al, tan_ac)
    spacing = float(np.median([n["line_spacing_m"] for n in nominal if n["line_spacing_m"]] or [50.0]))
    n_dirs = len(dirs_all)
    combined = block_metrics(allst, area, spacing, n_dirs)
    per_dir = {}
    if n_dirs >= 2:
        for d in dirs_all:
            sub = [s for s in allst if s["fam"] == d]
            if sub:
                per_dir[f"{d:.1f}"] = block_metrics(sub, area, spacing, 1)
    h = np.array([s["h_nadir"] for s in allst]); hmin = np.array([s["h_min"] for s in allst])
    pitch = cam["sensor_w"] / cam["px_w"] / 1000.0
    gsd = h * pitch / (cam["focal"] / 1000.0)
    gsd_min = hmin * pitch / (cam["focal"] / 1000.0)
    speed = nominal[0]["speed"] if nominal else 8.0
    rel = np.array([s["relief"] for s in allst]) / np.maximum(h, 1.0)
    return dict(name=name, mode=mode, orientation=args.orientation, nominal=nominal, rate_flags=rate_flags,
                directions=[round(d, 1) for d in dirs_all], combined=combined, per_direction=per_dir,
                agl_nadir_m=stats(h), gsd_nadir_cm=stats(100 * gsd),
                blur_worst_px=float((speed / args.shutter / gsd_min).max()),
                relief_gt10pct=100 * float((rel > 0.10).mean()), speed=speed)


def pct(s, key="median"):
    return "n/a" if not s else f"{100*s[key]:.0f}%"


def ov_line(label, s):
    if not s:
        return f"    {label:<34} n/a"
    return (f"    {label:<34} median {100*s['median']:4.0f}%  p5 {100*s['p05']:4.0f}%  min {100*s['min']:4.0f}%"
            f"{'   <- GAP' if s['min'] < 0 else ''}")


def block_lines(b, title):
    out = [f"  {title}: {b['photos']} photos, {b['lines']} lines"]
    out.append(ov_line("forward, linear worst-position", b["forward"]))
    out.append(ov_line("forward, centre line", b["forward_centre"]))
    out.append(ov_line("forward, area ratio (ASPRS Add.V)", b["forward_area"]))
    out.append(ov_line("side, linear at nadir chord", b["side"]))
    if b["side_seams"]:
        out.append(ov_line("side, across flight seams only", b["side_seams"]))
    m = b["multiplicity"]
    if m:
        im = m["images"]
        out.append(f"    images per {m['cell_m']:.0f} m cell: mean {im['mean']:.1f}, median {im['median']:.0f}, p5 {im['p05']:.0f}, "
                   f"min {im['min']:.0f} | 0: {m['zero']:.2f}%  >=2: {m['ge2']:.1f}%  >=3: {m['ge3']:.1f}%  "
                   f">=5 (NAIP): {m['ge5']:.1f}%  >5 (Pix4D green): {m['ge6']:.1f}%")
        extra = f"    seen from >=2 lines {m['ge2_lines']:.1f}%"
        if m["ge2_dirs"] is not None:
            extra += f"   from >=2 flight directions {m['ge2_dirs']:.1f}% (needs both grids flown + processed together)"
        out.append(extra)
    return out


def report(r, use):
    print(f"\n=== {r['name']}")
    if r.get("error"):
        print("  ", r["error"]); return
    trig = ("autopilot cmd 206 distance trigger (applies ONLY if the Astro trigger is wired to the payload)"
            if r["mode"] == "plan" else f"payload trigger {r['mode']} (Phoenix Rover setting - confirm in SpatialExplorer)")
    print(f"  trigger: {trig}")
    print(f"  camera: A6K-Lite, {CAMERAS['a6k-lite']['mount_note'] if r['orientation']=='across' else 'long side ALONG-track (user-set)'}")
    for f in r["rate_flags"]:
        print(f"  RATE FAIL: {f}")
    n = r["nominal"][0] if r["nominal"] else None
    if n:
        side = pct({"median": n["side"]}) if n["side"] is not None else "n/a"
        print(f"  nominal (flat, AGL {n['agl']:.0f} m): footprint {n['footprint_across_m']:.1f} across x {n['footprint_along_m']:.1f} along m, "
              f"base {n['base_m']:.2f} m ({n['shot_s']:.2f} s/shot), spacing {n['line_spacing_m']:.0f} m -> forward "
              f"{pct({'median': n['forward']})}, side {side}{'  [Refly90 criss-cross]' if n['refly90'] else ''}")
    a, g = r["agl_nadir_m"], r["gsd_nadir_cm"]
    bl = r["blur_worst_px"]
    print(f"  AGL at photos {a['min']:.1f}-{a['max']:.1f} m; nadir GSD {g['min']:.2f}-{g['max']:.2f} cm; worst blur "
          f"{bl:.2f} px @ 1/{SHUTTER:g} s, {r['speed']:.1f} m/s ({'PASS' if bl < 1 else 'FAIL'} <1 px ASPRS; "
          f"{'PASS' if bl <= 0.5 else 'FAIL'} <=0.5 px strict); frames with relief >10% of AGL: {r['relief_gt10pct']:.0f}%")
    if r["per_direction"]:
        for d, b in r["per_direction"].items():
            print("\n".join(block_lines(b, f"GRID {d} deg")))
        print("\n".join(block_lines(r["combined"], "COMBINED (all grids)")))
    else:
        print("\n".join(block_lines(r["combined"], "SURVEY")))
    # threshold table on the per-grid (or single) worst-position values
    blocks = r["per_direction"] or {"survey": r["combined"]}
    print(f"  thresholds (use = {use or 'UNSTATED - pass --use colorize|ortho|sfm'}; checked on each grid's p5):")
    if use:
        print(f"    note: {USE_NOTE[use]}")
    for name, fmin, smin, uses, src in THRESHOLDS:
        res = []
        for d, b in blocks.items():
            fo, so = b["forward"], b["side"]
            ok_f = fo is not None and fo["p05"] >= fmin
            ok_s = so is not None and so["p05"] >= smin
            res.append(f"{d}: N/A (single line)" if so is None else f"{d}: {'PASS' if ok_f and ok_s else 'FAIL'}")
        mark = "*" if use and use in uses else " "
        print(f"   {mark}{name:<34} {100*fmin:.0f}/{100*smin:.0f}  " + "  ".join(res) + f"   [{src}]")
    print("  LIMITS: nadir camera (no roll/pitch; ~2 %/deg), bare-earth DEM, linear altitude between Items, "
          "outer cross-line/fig-8 photos not counted")


SHUTTER = 1000.0


def main():
    global SHUTTER
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("plans", nargs="+")
    ap.add_argument("--use", choices=["colorize", "ortho", "sfm"])
    ap.add_argument("--target", help="KML polygon(s) for multiplicity (default: union of survey polygons)")
    ap.add_argument("--camera", default="a6k-lite", choices=sorted(CAMERAS))
    ap.add_argument("--orientation", default="across", choices=["across", "along"])
    ap.add_argument("--trigger", default="auto")
    ap.add_argument("--interval", type=float, default=2.0, help="Phoenix Rover camera interval (s) for auto mode; Phoenix docs: a photo every 2 s; RH: 1 or 2 s")
    ap.add_argument("--shutter", type=float, default=1000.0, help="shutter denominator (1000 = 1/1000 s)")
    ap.add_argument("--dem-meta", help="dem_lookup meta JSON (required file; default: ensure_dem_for_bbox 3 m)")
    ap.add_argument("--ground-offset", type=float, default=0.0, help="m added to the DEM to reach the plan datum")
    ap.add_argument("--no-combined", action="store_true")
    ap.add_argument("--json")
    args = ap.parse_args()
    SHUTTER = args.shutter

    plans = [load_plan(p) for p in args.plans]
    lats = [i["params"][4] for pl in plans for cx in pl["complex"] for i in cx["items"] if i.get("command") == 16]
    lons = [i["params"][5] for pl in plans for cx in pl["complex"] for i in cx["items"] if i.get("command") == 16]
    fr = Frame(float(np.mean(lats)), float(np.mean(lons)))
    if args.dem_meta:
        if not os.path.exists(args.dem_meta):
            raise SystemExit(f"--dem-meta not found: {args.dem_meta}")
        want_tif = json.load(open(args.dem_meta))["tif_path"]
        dem_lookup._explicit_meta_paths[:] = [args.dem_meta]
    else:
        pad = 0.006
        mp = dem_lookup.ensure_dem_for_bbox(min(lats) - pad, max(lats) + pad, min(lons) - pad, max(lons) + pad, resolution_m=3.0)
        want_tif = json.load(open(mp))["tif_path"]
        dem_lookup._explicit_meta_paths[:] = [mp]
    dem_lookup._local_dem = None; dem_lookup._local_meta = None
    dem = Dem(fr, args.ground_offset)
    if os.path.normcase(dem.m["tif_path"]) != os.path.normcase(want_tif):
        raise SystemExit(f"DEM fallback detected: loaded {dem.m['tif_path']}, expected {want_tif}")
    cam = CAMERAS[args.camera]
    print(f"DEM: {dem.m['tif_path']} ({dem.m.get('resolution_m', '?')} m), ground offset {args.ground_offset:+.3f} m")

    has_trig = any(i.get("command") == TRIG_DIST and (i["params"][0] or 0) > 0
                   for pl in plans for cx in pl["complex"] for i in cx["items"])
    modes = [f"time:{args.interval:g}"] if args.trigger == "auto" else [args.trigger]

    results = []
    for mode in modes:
        print(f"\n##### TRIGGER {mode}{'  (PRIMARY)' if mode == modes[0] else '  (SECONDARY)'} #####")
        group = [(pl["name"], [pl], target_area([pl], None, fr)) for pl in plans]
        if len(plans) > 1 and not args.no_combined:
            group.append((f"SITE COMBINED ({len(plans)} plans)", plans, target_area(plans, args.target, fr)))
        for name, pls, area in group:
            r = analyse(name, pls, mode, args, dem, fr, cam, area)
            report(r, args.use)
            results.append(r)
    if args.json:
        json.dump(results, open(args.json, "w"), indent=1, default=str)


if __name__ == "__main__":
    main()
