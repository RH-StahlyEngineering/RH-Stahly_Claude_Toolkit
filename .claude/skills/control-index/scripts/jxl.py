"""Read points from a Trimble .jxl job file (XML). Format notes: references/jxl-format.md."""
import xml.etree.ElementTree as ET

from vce import Grid


def _float_at(el, path):
    t = el.findtext(path)
    return float(t) if t not in (None, "") else None


def _coord_system_name(root):
    cs = root.find("./FieldBook/CoordinateSystemRecord[SystemName!='']")
    if cs is None:
        return None
    return " / ".join(filter(None, [cs.findtext("SystemName"), cs.findtext("ZoneName")])) or None


def _grid_transformer(root):
    """vce.Grid (grid m -> lat/lon) from the job's last ProjectionRecord, or None. Element names verified on
    real Lambert2Parallel (Parallel1/2) and TransverseMercator files; LocalSite KeyedInGroundScaleFactor
    (GroundScaleFactor about ProjectLocation) is undone like a .vce ground scale."""
    projs = root.findall("./FieldBook/ProjectionRecord/Projection")
    proj = next((p for p in reversed(projs) if p.findtext("Type") not in (None, "NotSet")), None)
    if proj is None:
        return None
    t = proj.findtext("Type")
    g = proj.findtext
    common = (f"+lat_0={g('CentralLatitude')} +lon_0={g('CentralLongitude')} +x_0={g('FalseEasting')} "
              f"+y_0={g('FalseNorthing')} +ellps=GRS80 +units=m +no_defs")
    if t == "Lambert1Parallel":
        p4 = f"+proj=lcc +lat_1={g('CentralLatitude')} +k_0={g('Scale')} {common}"
    elif t == "Lambert2Parallel":
        p4 = f"+proj=lcc +lat_1={g('Parallel1')} +lat_2={g('Parallel2')} {common}"
    elif t == "TransverseMercator":
        p4 = f"+proj=tmerc +k_0={g('Scale')} {common}"
    else:
        return None
    site = next((rec.find("LocalSite") for rec in root.findall("./FieldBook/ProjectionRecord")
                 if proj in list(rec)), None)
    scale, origin, offset = 1.0, None, False
    if site is not None and site.findtext("Type") == "KeyedInGroundScaleFactor":
        scale = _float_at(site, "GroundScaleFactor") or 1.0
        lat, lon = _float_at(site, "ProjectLocationLatitude"), _float_at(site, "ProjectLocationLongitude")
        origin = (lat, lon) if lat is not None and lon is not None else None
        offset = any(_float_at(site, k) for k in ("NorthingOffset", "EastingOffset",
                                                   "ProjectionOriginNorthingDelta", "ProjectionOriginEastingDelta"))
    return Grid(_coord_system_name(root), p4, scale, origin, offset_unverified=offset)


def parse_jxl(path):
    """Point records with unrounded positions (WGS84 when stored, else projected from the job's grid)."""
    root = ET.parse(path).getroot()
    coord_system = _coord_system_name(root)
    grid = None
    for pt in root.findall("./Reductions/Point"):
        flags = []
        lat, lon = _float_at(pt, "WGS84/Latitude"), _float_at(pt, "WGS84/Longitude")
        if lat is None:
            n, e = _float_at(pt, "Grid/North"), _float_at(pt, "Grid/East")
            if n is None:
                continue
            grid = grid or _grid_transformer(root)
            if grid is None:
                continue
            lat, lon = grid.to_latlon(n, e)
            flags = list(grid.flags)
        yield {"point_name": pt.findtext("Name"), "recorded": pt.findtext("Code") or "",
               "position": (lat, lon), "coord_system": coord_system, "date": root.get("TimeStamp"),
               "flags": flags}


def jxl_grid(path):
    """(Grid or None, {name: (N, E) metres}) -- context for CSV exports beside the job."""
    root = ET.parse(path).getroot()
    pts = {pt.findtext("Name"): (_float_at(pt, "Grid/North"), _float_at(pt, "Grid/East"))
           for pt in root.findall("./Reductions/Point") if _float_at(pt, "Grid/North") is not None}
    return _grid_transformer(root), pts
