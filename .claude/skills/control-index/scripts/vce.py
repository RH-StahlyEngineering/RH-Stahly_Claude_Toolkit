"""Read points from a Trimble Business Center .vce project without TBC (control-index #6).

A .vce is a ZIP. `FieldNames` maps numeric field ids -> names (ids differ per file, so everything is
resolved by name). `ObjectData` is a stream of objects `{<` oid ver type nfields, each a run of fields
`MF` u16-type u32-field-id value. Value types used here: 1 double, 2/3/5 u32, 4 string (7-bit varint
length), 7 double array (u32 1, u32 n, n doubles), 12 u32 array (u32 1, u32 n, n u32). Other types are
skipped by resyncing on the next `MF`. Format notes: control-index-notes/vce-format.md.
"""
import math
import re
import struct
import zipfile

OBJ_RE = re.compile(rb"\{<")
GEODETIC, GRID = 0, 2  # m_CoordSystem values: radians lat/lon, projected N/E metres
CHECK_CODES = {"CHK", "CHECK"}


def _field_names(raw):
    p, out = 4, {}
    while p < len(raw):
        n = raw[p]
        out[struct.unpack_from("<I", raw, p + 1 + n)[0]] = raw[p + 1:p + 1 + n].decode("latin1")
        p += 5 + n
    return out


def _varint(d, p):
    v = s = 0
    while True:
        b = d[p]
        p += 1
        v |= (b & 0x7F) << s
        s += 7
        if b < 0x80:
            return v, p


def _fields(d, a, b, names):
    """Yield (name, value) for the fields of one object span."""
    p = d.find(b"MF", a, b)
    while 0 <= p < b - 8:
        t, fid = struct.unpack_from("<HI", d, p + 2)
        q = p + 8
        name = names.get(fid)
        try:
            if t == 1:
                yield name, struct.unpack_from("<d", d, q)[0]
                q += 8
            elif t in (2, 3, 5):
                yield name, struct.unpack_from("<I", d, q)[0]
                q += 4
            elif t == 4:
                n, q = _varint(d, q)
                yield name, d[q:q + n].decode("latin1")
                q += n
            elif t in (7, 12):
                n = struct.unpack_from("<I", d, q + 4)[0]
                fmt = "d" if t == 7 else "I"
                yield name, struct.unpack_from(f"<{n}{fmt}", d, q + 8)
                q += 8 + n * struct.calcsize(fmt)
        except (struct.error, IndexError):
            pass
        p = d.find(b"MF", q, b)


def _csib_lcc(csib_text):
    """Coordinate system name + pyproj string from the CSIB blob (space-separated byte values)."""
    bs = bytes(int(x) for x in csib_text.split())
    head = bs[16:bs.find(b"\x00\x00Default")]  # "TNL CSIB" + 8-byte version double, then names
    names = [x.decode("latin1") for x in head.split(b"\x00") if x]
    system, zone = (names[0], names[-1]) if len(names) > 1 else ((names or [""])[0], "")
    i = bs.find(b"\x04" + zone.encode("latin1") + b"\x00\x00")  # projection type 4 = Lambert 1 parallel
    if not zone or i < 0:
        return " / ".join(filter(None, [system, zone])) or None, None
    lat0, lon0, fn, fe, k = struct.unpack_from("<5d", bs, i + len(zone) + 3)
    lat0, lon0 = math.degrees(lat0), math.degrees(lon0)
    p4 = (f"+proj=lcc +lat_1={lat0} +lat_0={lat0} +lon_0={lon0} +k_0={k} +x_0={fe} +y_0={fn} "
          "+ellps=GRS80 +units=m +no_defs")
    return f"{system} / {zone}", p4


def _stamp(ts):
    """'11/10/2026 12:41:26' -> '2026-11-10T12:41:26' (sortable); '01/01/0001' placeholders -> ''."""
    m = re.match(r"(\d\d)/(\d\d)/(\d{4}) (\S+)", ts or "")
    return "" if not m or m.group(3) == "0001" else f"{m.group(3)}-{m.group(1)}-{m.group(2)}T{m.group(4)}"


def parse_vce(path, locator_decimals=4):
    with zipfile.ZipFile(path) as z:
        d = z.read("ObjectData")
        names = _field_names(z.read("FieldNames"))
    starts = [m.start() for m in OBJ_RE.finditer(d)] + [len(d)]
    points, codes, obs, coord_system, p4 = {}, {}, [], None, None
    for a, b in zip(starts, starts[1:]):
        oid = struct.unpack_from("<I", d, a + 2)[0]
        fs = list(_fields(d, a, b, names))
        keys = {n for n, _ in fs}
        if "CSIB" in keys and p4 is None:
            coord_system, p4 = _csib_lcc(next(v for n, v in fs if n == "CSIB"))
        if {"m_FeatureCodeSchema", "m_Code"} <= keys:
            codes[oid] = next(v for n, v in fs if n == "m_Code")
        if {"m_LayerSerialC", "m_PointID"} <= keys:  # a point entity
            pt, cs = {"name": next(v for n, v in fs if n == "m_PointID")}, None
            for n, v in fs:
                if n == "m_CoordSystem":
                    cs = v
                elif n == "m_Position" and len(v) == 2:
                    pt.setdefault(cs, v)
            points[oid] = pt
        rec = None
        for n, v in fs:  # raw-data records (observations); several per object
            if n == "RawDataBase.Schema":
                rec = {"deps": (), "ts": "", "pid": None}
                obs.append(rec)
            elif rec is not None and n == "Dependencies":
                rec["deps"] = v
            elif rec is not None and n == "m_PointID" and rec["pid"] is None:
                rec["pid"] = v
            elif rec is not None and n == "m_TimeStampLocal":
                rec["ts"] = _stamp(v)
    # code + date per point: its own observations (record m_PointID == point name; other deps are
    # base stations/backsights), latest first, preferring a non-check code
    best = {}
    for r in obs:
        pids = [i for i in r["deps"] if i in points and points[i]["name"] == r["pid"]]
        cids = [i for i in r["deps"] if i in codes]
        for pid in pids[:1]:
            code = codes[cids[0]] if cids else ""
            rank = (code.strip().upper() not in CHECK_CODES and code != "", r["ts"])
            if pid not in best or rank > best[pid][0]:
                best[pid] = (rank, code, r["ts"])
    tf = None
    for oid, pt in points.items():
        if GEODETIC in pt:
            lat, lon = (math.degrees(x) for x in pt[GEODETIC])
        elif GRID in pt and p4:
            if tf is None:
                from pyproj import Transformer
                tf = Transformer.from_crs(p4, "EPSG:4326", always_xy=True)
            n, e = pt[GRID]
            lon, lat = tf.transform(e, n)
        else:
            continue
        _, code, ts = best.get(oid, (None, "", ""))
        yield {"point_name": pt["name"], "recorded": code,
               "lat": round(lat, locator_decimals), "lon": round(lon, locator_decimals),
               "coord_system": coord_system, "date": ts or None}
