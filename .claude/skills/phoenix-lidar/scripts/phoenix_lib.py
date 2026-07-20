"""Shared library for Phoenix LiDAR acquisition QA + base matching.
Read-only parsing of Phoenix .nav (NovAtel binary) and base-station RINEX headers,
coordinate transforms, validity classification, and the LiDAR footprint model.
See ../references/ for the format specs and the reasoning behind the conventions.
"""
import os, glob, struct, math, re, csv, datetime as dt

GPS0 = dt.datetime(1980, 1, 6)
LEAP = 18  # GPS-UTC leap seconds (constant since 2017-01-01)
# Generous all-of-Montana box to reject garbage/no-fix epochs while keeping real
# acquisitions in any MT location (Bozeman/Great Falls/Fergus all differ).
MT_BOX = (44.0, 49.5, -116.5, -103.5)  # latmin, latmax, lonmin, lonmax
POS_MSGS = {42, 1429, 423, 47, 507, 508, 1465}  # BESTPOS/BESTGNSSPOS/PSRPOS + INSPVA(X)


# ---------- geometry ----------
def haversine_mi(a1, o1, a2, o2):
    R = 6371.0088
    p1, p2 = math.radians(a1), math.radians(a2)
    dp = math.radians(a2 - a1); dl = math.radians(o2 - o1)
    x = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(x)) * 0.621371


def ecef2geo(X, Y, Z):
    a = 6378137.0; f = 1 / 298.257223563; e2 = f * (2 - f)
    lon = math.atan2(Y, X); p = math.hypot(X, Y); lat = math.atan2(Z, p * (1 - e2))
    for _ in range(8):
        N = a / math.sqrt(1 - e2 * math.sin(lat) ** 2); h = p / math.cos(lat) - N
        lat = math.atan2(Z, p * (1 - e2 * N / (N + h)))
    N = a / math.sqrt(1 - e2 * math.sin(lat) ** 2); h = p / math.cos(lat) - N
    return math.degrees(lat), math.degrees(lon), h


def mt_stateplane_to_wgs84(N_ft, E_ft):
    """Montana State Plane NAD83 US-ft (EPSG:2256) -> WGS84 lat/lon. Inverse Lambert CC (2SP)."""
    usft = 1200 / 3937; E = E_ft * usft; N = N_ft * usft
    a = 6378137.0; f = 1 / 298.257222101; e2 = 2 * f - f * f; e = math.sqrt(e2)
    p1, p2, p0, l0 = map(math.radians, (45, 49, 44.25, -109.5)); FE = 600000.0
    m = lambda p: math.cos(p) / math.sqrt(1 - e2 * math.sin(p) ** 2)
    t = lambda p: math.tan(math.pi / 4 - p / 2) / (((1 - e * math.sin(p)) / (1 + e * math.sin(p))) ** (e / 2))
    n = (math.log(m(p1)) - math.log(m(p2))) / (math.log(t(p1)) - math.log(t(p2)))
    F = m(p1) / (n * t(p1) ** n); rho0 = a * F * t(p0) ** n
    Ep = E - FE; rho = math.copysign(math.sqrt(Ep * Ep + (rho0 - N) ** 2), n); th = math.atan2(Ep, (rho0 - N))
    tt = (rho / (a * F)) ** (1 / n); phi = math.pi / 2 - 2 * math.atan(tt)
    for _ in range(6):
        phi = math.pi / 2 - 2 * math.atan(tt * (((1 - e * math.sin(phi)) / (1 + e * math.sin(phi))) ** (e / 2)))
    return math.degrees(phi), math.degrees(l0 + th / n)


def gps_to_utc_str(gps_sec):
    return (GPS0 + dt.timedelta(seconds=gps_sec - LEAP)).strftime('%Y-%m-%d %H:%M:%S')


# ---------- .nav (NovAtel binary) ----------
def parse_nav(path, box=MT_BOX):
    """Return dict: pts=[(gps_sec,lat,lon)], gps_start, gps_end, or None if no fix.
    Long header AA4412 + short header AA4413. Offsets per references/nav_and_rinex.md."""
    buf = open(path, 'rb').read(); n = len(buf); pts = []
    la0, la1, lo0, lo1 = box; i = 0
    while i + 16 <= n:
        if buf[i] == 0xAA and buf[i + 1] == 0x44 and buf[i + 2] == 0x12:
            hlen = buf[i + 3]; mid = struct.unpack_from('<H', buf, i + 4)[0]
            ml = struct.unpack_from('<H', buf, i + 8)[0]; tot = hlen + ml + 4
            if tot <= 0 or i + tot > n: i += 1; continue
            if mid in POS_MSGS:
                wk = struct.unpack_from('<H', buf, i + 14)[0]; ms = struct.unpack_from('<I', buf, i + 16)[0]
                d = i + hlen
                try:
                    if mid in (42, 1429, 423, 47):
                        lat, lon = struct.unpack_from('<d', buf, d + 8)[0], struct.unpack_from('<d', buf, d + 16)[0]
                    else:
                        lat, lon = struct.unpack_from('<d', buf, d + 12)[0], struct.unpack_from('<d', buf, d + 20)[0]
                    if la0 < lat < la1 and lo0 < lon < lo1 and 2000 < wk < 3000:
                        pts.append((wk * 604800 + ms / 1000.0, lat, lon))
                except struct.error:
                    pass
            i += tot
        elif buf[i] == 0xAA and buf[i + 1] == 0x44 and buf[i + 2] == 0x13:
            ml = buf[i + 3]; mid = struct.unpack_from('<H', buf, i + 4)[0]; tot = 12 + ml + 4
            if mid in POS_MSGS:
                wk = struct.unpack_from('<H', buf, i + 6)[0]; ms = struct.unpack_from('<I', buf, i + 8)[0]; d = i + 12
                try:
                    lat, lon = struct.unpack_from('<d', buf, d + 12)[0], struct.unpack_from('<d', buf, d + 20)[0]
                    if la0 < lat < la1 and lo0 < lon < lo1 and 2000 < wk < 3000:
                        pts.append((wk * 604800 + ms / 1000.0, lat, lon))
                except struct.error:
                    pass
            if tot <= 0 or i + tot > n: i += 1; continue
            i += tot
        else:
            i += 1
    if not pts:
        return None
    pts.sort(key=lambda x: x[0])
    return {'pts': pts, 'gps_start': pts[0][0], 'gps_end': pts[-1][0]}


def decimate(pts, target=2000):
    step = max(1, len(pts) // target)
    out = pts[::step]
    if out[-1] != pts[-1]:
        out.append(pts[-1])
    return out


def speed_runs(pts, vmin, vmax, hz=1.0):
    """List of in-band [(lat,lon),...] runs (>=2 pts). Resamples to ~hz for stable speed."""
    res = [pts[0]]
    for p in pts[1:]:
        if p[0] - res[-1][0] >= (1.0 / hz) * 0.9:
            res.append(p)
    runs = []; cur = []
    for i in range(1, len(res)):
        t0, a0, o0 = res[i - 1]; t1, a1, o1 = res[i]; d = t1 - t0
        if d <= 0: continue
        v = haversine_mi(a0, o0, a1, o1) / 0.000621371 / d  # meters/sec
        if vmin <= v <= vmax:
            if not cur: cur = [(a0, o0)]
            cur.append((a1, o1))
        else:
            if len(cur) >= 2: runs.append(cur)
            cur = []
    if len(cur) >= 2: runs.append(cur)
    return runs


# ---------- RINEX header ----------
def read_rinex_header(path):
    """Read only the header (stop at END OF HEADER). Return base pos + GPS-time window."""
    xyz = fg = lg = marker = rec = ant = None
    with open(path, 'r', errors='replace') as f:
        for _ in range(400):
            ln = f.readline()
            if not ln: break
            lab = ln[60:].strip()
            if lab == 'END OF HEADER': break
            body = ln[:60]
            if lab == 'APPROX POSITION XYZ': xyz = [float(v) for v in body.split()]
            elif lab == 'TIME OF FIRST OBS': fg = body.split()
            elif lab == 'TIME OF LAST OBS': lg = body.split()
            elif lab == 'MARKER NAME': marker = body.strip()
            elif lab == 'REC # / TYPE / VERS': rec = body.strip()
            elif lab == 'ANT # / TYPE': ant = body.strip()
    if not (xyz and fg and lg):
        return None
    def g(t): return (dt.datetime(int(t[0]), int(t[1]), int(t[2]), int(t[3]), int(t[4]), int(float(t[5]))) - GPS0).total_seconds()
    if abs(xyz[0]) < 1e5:  # near-zero autonomous position -> unusable
        return None
    lat, lon, ht = ecef2geo(*xyz)
    return {'file': os.path.basename(path), 'marker': marker, 'rec': rec, 'ant': ant,
            'lat': lat, 'lon': lon, 'ht': ht, 'first_gps': g(fg), 'last_gps': g(lg)}


def find_obs_files(d):
    return [f for f in glob.glob(os.path.join(d, '*')) if re.search(r'\.\d\do$', f, re.I)]


# ---------- session classification ----------
def classify_session(folder):
    """Return dict with session, type (AERIAL/MOBILE), valid (.txt + photo match), nav path."""
    s = os.path.basename(folder.rstrip('/\\'))
    txt = glob.glob(os.path.join(folder, '*.txt'))
    valid = False
    if txt:
        t = open(txt[0], 'r', errors='replace').read()
        m = re.search(r'events/photos recorded for CAM0:\s*(\d+)\s*/\s*(\d+)', t)
        valid = (m.group(1) == m.group(2)) if m else True
    typ = 'AERIAL' if glob.glob(os.path.join(folder, 'cam0', '*.jpg')) else 'MOBILE'
    navs = glob.glob(os.path.join(folder, '*.nav'))
    return {'session': s, 'type': typ, 'valid_txt': valid, 'nav': navs[0] if navs else None}


def decode_t04(name):
    """Trimble T04 filename -> {receiver, doy, session}. Format [4-char serial][3 DOY][1 session]."""
    b = os.path.splitext(os.path.basename(name))[0]
    m = re.match(r'^(.{4})(\d{3})(.)$', b)
    return {'receiver': m.group(1), 'doy': int(m.group(2)), 'session': m.group(3)} if m else None


# ---------- footprint ----------
def footprint_rings(runs_or_traj, agl=50.0):
    """Buffer trajectory (list of [(lat,lon)] runs, or a single [(lat,lon)] list) by 1.5*AGL.
    Returns list of exterior rings [[(lat,lon),...]]. Requires shapely."""
    from shapely.geometry import LineString, MultiPolygon
    runs = runs_or_traj if runs_or_traj and isinstance(runs_or_traj[0][0], (list, tuple)) else [runs_or_traj]
    allpts = [p for run in runs for p in run]
    lat0 = sum(a for a, o in allpts) / len(allpts); lon0 = sum(o for a, o in allpts) / len(allpts)
    k = 111320 * math.cos(math.radians(lat0))
    to_xy = lambda a, o: ((o - lon0) * k, (a - lat0) * 110540)
    to_ll = lambda x, y: (lat0 + y / 110540, lon0 + x / k)
    half = 1.5 * agl; rings = []
    for run in runs:
        if len(run) < 2: continue
        # simplify (~2 m) before buffering: dense/near-coincident vertices make buffer() pathologically
        # slow (seconds per line) with no visible change to the swath polygon.
        ls = LineString([to_xy(a, o) for a, o in run]).simplify(2.0, preserve_topology=False)
        g = ls.buffer(half, cap_style=1, join_style=1)
        polys = list(g.geoms) if isinstance(g, MultiPolygon) else [g]
        for p in polys:
            rings.append([to_ll(x, y) for x, y in p.exterior.coords])
    return rings
