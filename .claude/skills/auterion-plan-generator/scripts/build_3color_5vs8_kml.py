"""Build a 3-color KML comparing 5-launch vs 8-launch coverage for Fergus photogrammetry.

Sample each of the 10 area polygons at a 300m grid + vertices + edge midpoints, run
VLOS+distance check from each candidate launch, classify each sample point by which
launch SET covers it, and emit color-coded placemarks.

Color key:
    GREEN -> BOTH (covered by 5-launch AND 8-launch sets)
    BLUE  -> ONLY 5-launch covers (should be 0 since 5 is a subset of 8)
    RED   -> ONLY 8-launch covers (the price of going 97.3% -> 100%)
"""
import math
import os
import re
import sys
import xml.etree.ElementTree as ET

# --- Setup paths -------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import dem_lookup
import los_check

# Prepend the large cached DEM (skill-bundled fergus_dem.tif is too small for SW area)
LARGE_DEM_META = os.path.expanduser("~/.claude/dem_cache/dem_ee0aa3a8a9d0.json")
if LARGE_DEM_META not in dem_lookup._explicit_meta_paths:
    dem_lookup._explicit_meta_paths.insert(0, LARGE_DEM_META)
dem_lookup._local_dem = None
dem_lookup._local_meta = None

from dem_lookup import terrain_amsl

# --- Constants ---------------------------------------------------------------
AGL_M = 121.92            # 400 ft
RADIUS_M = 4828.03        # 3 mi
OPERATOR_EYE_M = 2.0
GRID_M = 300.0
LOS_SAMPLES = 50

DOWNLOADS = r"C:/Users/rharbach.STAHLY/Downloads"
OUT_PATH = os.path.join(DOWNLOADS, "Fergus_photogrammetry_3color_5vs8.kml")
AREA_KML_FMT = os.path.join(DOWNLOADS, "Fergus Hilger-Roy — area {n}.kml")

# Launches in greedy order
LAUNCHES = [
    ("L1", 47.260247, -109.317742, 1350, [1, 2, 3]),
    ("L2", 47.332234, -109.065601, 1153, [5, 6, 7]),
    ("L3", 47.334033, -108.916971, 1049, [7, 8, 9]),
    ("L4", 47.301639, -109.200961, 1200, [3, 4, 5]),
    ("L5", 47.350230, -108.863889, 1025, [9, 10]),
    ("L6", 47.335833, -109.047023, 1152, [7]),
    ("L7", 47.323235, -109.129300, 1233, [5]),
    ("L8", 47.262047, -109.296509, 1394, [3]),
]


# --- Geometry helpers --------------------------------------------------------
def hav(a, b):
    R = 6371000.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dl = math.radians(b[1] - a[1])
    dp = p2 - p1
    x = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(x))


def parse_area_polygon(path):
    """Read a single-polygon KML and return list of (lat, lon) outer ring vertices."""
    tree = ET.parse(path)
    root = tree.getroot()
    ns = {"k": "http://www.opengis.net/kml/2.2"}
    coord_el = root.find(".//k:outerBoundaryIs/k:LinearRing/k:coordinates", ns)
    if coord_el is None:
        # Try without namespace
        coord_el = root.find(".//outerBoundaryIs/LinearRing/coordinates")
    if coord_el is None:
        raise RuntimeError(f"No outer ring coordinates in {path}")
    text = coord_el.text.strip()
    verts = []
    for tok in re.split(r"\s+", text):
        if not tok:
            continue
        parts = tok.split(",")
        lon = float(parts[0])
        lat = float(parts[1])
        verts.append((lat, lon))
    return verts


def point_in_poly(lat, lon, verts):
    """Ray-casting; verts is list of (lat, lon) in any winding."""
    n = len(verts)
    inside = False
    j = n - 1
    for i in range(n):
        yi, xi = verts[i]
        yj, xj = verts[j]
        if ((yi > lat) != (yj > lat)) and (lon < (xj - xi) * (lat - yi) / (yj - yi + 1e-30) + xi):
            inside = not inside
        j = i
    return inside


def bbox(verts):
    lats = [v[0] for v in verts]
    lons = [v[1] for v in verts]
    return min(lats), max(lats), min(lons), max(lons)


def sample_polygon(verts, step_m=GRID_M):
    """Grid samples inside polygon + vertices + edge midpoints, deduplicated."""
    lat_min, lat_max, lon_min, lon_max = bbox(verts)
    mid_lat = (lat_min + lat_max) / 2
    m_per_deg_lat = 111132.0
    m_per_deg_lon = 111132.0 * math.cos(math.radians(mid_lat))
    d_lat = step_m / m_per_deg_lat
    d_lon = step_m / m_per_deg_lon

    pts = set()

    def add(p):
        key = (round(p[0], 6), round(p[1], 6))
        pts.add(key)

    # Vertices
    for v in verts:
        add(v)
    # Edge midpoints
    n = len(verts)
    for i in range(n):
        a = verts[i]
        b = verts[(i + 1) % n]
        add(((a[0] + b[0]) / 2, (a[1] + b[1]) / 2))
    # Grid interior
    lat = lat_min
    while lat <= lat_max + 1e-9:
        lon = lon_min
        while lon <= lon_max + 1e-9:
            if point_in_poly(lat, lon, verts):
                add((lat, lon))
            lon += d_lon
        lat += d_lat

    return [(round(p[0], 6), round(p[1], 6)) for p in pts]


# --- KML emission ------------------------------------------------------------
KML_HEADER = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<kml xmlns="http://www.opengis.net/kml/2.2">\n'
)


def kml_style(sid, color_aabbggrr, scale="0.7", icon_href=None):
    icon_href = icon_href or "http://maps.google.com/mapfiles/kml/shapes/placemark_circle.png"
    return (
        f'<Style id="{sid}">'
        f'<IconStyle><color>{color_aabbggrr}</color><scale>{scale}</scale>'
        f'<Icon><href>{icon_href}</href></Icon></IconStyle>'
        f'<LabelStyle><scale>0</scale></LabelStyle>'
        f'</Style>'
    )


def kml_poly_style(sid, line_color, poly_color):
    return (
        f'<Style id="{sid}">'
        f'<LineStyle><color>{line_color}</color><width>2</width></LineStyle>'
        f'<PolyStyle><color>{poly_color}</color></PolyStyle>'
        f'</Style>'
    )


def placemark(name, lat, lon, style_id, desc=None):
    desc_xml = f"<description><![CDATA[{desc}]]></description>" if desc else ""
    return (
        f'<Placemark><name>{name}</name>{desc_xml}'
        f'<styleUrl>#{style_id}</styleUrl>'
        f'<Point><coordinates>{lon:.6f},{lat:.6f},0</coordinates></Point>'
        f'</Placemark>'
    )


def polygon_placemark(name, verts, style_id, desc=None):
    coords = " ".join(f"{lon:.6f},{lat:.6f},0" for lat, lon in verts)
    desc_xml = f"<description><![CDATA[{desc}]]></description>" if desc else ""
    return (
        f'<Placemark><name>{name}</name>{desc_xml}'
        f'<styleUrl>#{style_id}</styleUrl>'
        f'<Polygon><outerBoundaryIs><LinearRing>'
        f'<coordinates>{coords}</coordinates>'
        f'</LinearRing></outerBoundaryIs></Polygon>'
        f'</Placemark>'
    )


# --- Main --------------------------------------------------------------------
def main():
    # 1. Load all 10 polygons
    polys = {}
    for n in range(1, 11):
        p = AREA_KML_FMT.format(n=n)
        polys[n] = parse_area_polygon(p)
        print(f"Area {n}: {len(polys[n])} vertices")

    # 2. Sample each polygon
    all_samples = []  # list of (area_n, lat, lon)
    for n in range(1, 11):
        s = sample_polygon(polys[n])
        for lat, lon in s:
            all_samples.append((n, lat, lon))
        print(f"Area {n}: {len(s)} sample points")
    print(f"TOTAL sample points: {len(all_samples)}")

    # 3. Precompute launch ground AMSL
    launch_ground = {}
    for name, lat, lon, *_ in LAUNCHES:
        g = terrain_amsl(lat, lon)
        launch_ground[name] = g
        print(f"{name} ground = {g:.1f} m AMSL")

    # 4. Coverage per sample point per launch
    L5_NAMES = {"L1", "L2", "L3", "L4", "L5"}
    L8_NAMES = {l[0] for l in LAUNCHES}

    results = []  # list of (area_n, lat, lon, covered_by, category)
    n_both = n_only5 = n_only8 = n_uncovered = 0
    for idx, (area_n, lat, lon) in enumerate(all_samples):
        # Terrain at point
        try:
            t = terrain_amsl(lat, lon)
        except Exception as e:
            print(f"Terrain lookup failed for ({lat},{lon}): {e}")
            continue
        drone_amsl = t + AGL_M

        covering = []
        for name, llat, llon, *_ in LAUNCHES:
            d = hav((llat, llon), (lat, lon))
            if d > RADIUS_M:
                continue
            op_amsl = launch_ground[name] + OPERATOR_EYE_M
            clear, _below, _pt = los_check.los_line_clear(
                (llat, llon), op_amsl, (lat, lon), drone_amsl, samples=LOS_SAMPLES
            )
            if clear:
                covering.append(name)

        cov5 = any(c in L5_NAMES for c in covering)
        cov8 = any(c in L8_NAMES for c in covering)  # = bool(covering)
        if cov5 and cov8:
            cat = "BOTH"; n_both += 1
        elif cov5 and not cov8:
            cat = "ONLY 5"; n_only5 += 1
        elif cov8 and not cov5:
            cat = "ONLY 8"; n_only8 += 1
        else:
            cat = "neither"; n_uncovered += 1

        results.append((area_n, lat, lon, covering, cat))

        if (idx + 1) % 200 == 0:
            print(f"  ... {idx+1}/{len(all_samples)} processed")

    print(f"\nCategorization:")
    print(f"  BOTH      = {n_both}")
    print(f"  ONLY 5    = {n_only5}")
    print(f"  ONLY 8    = {n_only8}")
    print(f"  neither   = {n_uncovered}")
    print(f"  total     = {len(results)}")

    # 5. Build KML
    parts = [KML_HEADER, "<Document>"]
    parts.append("<name>Fergus photogrammetry coverage: 5-launch vs 8-launch</name>")
    summary = (
        f"Sample points: {len(results)} across 10 areas (300m grid + vertices + edge midpoints).\n"
        f"GREEN = covered by BOTH 5- and 8-launch sets ({n_both})\n"
        f"BLUE  = covered only by 5-launch set ({n_only5})\n"
        f"RED   = covered only by 8-launch set ({n_only8}) -- price of 100% vs 97.3% coverage\n"
        f"Uncovered: {n_uncovered}\n"
        f"AGL=121.92m, RADIUS=4828.03m (3 mi), VLOS=50 samples, operator eye=ground+2m"
    )
    parts.append(f"<description><![CDATA[{summary}]]></description>")

    # Styles (KML color = aabbggrr)
    parts.append(kml_style("s_both", "ff00cc00", "0.6"))      # green
    parts.append(kml_style("s_only5", "ffff4400", "0.7"))     # blue
    parts.append(kml_style("s_only8", "ff0000ff", "0.7"))     # red
    parts.append(kml_style("s_uncov", "ff888888", "0.5"))     # gray
    parts.append(kml_style(
        "s_launch_l5", "ff00ffff", "1.2",
        "http://maps.google.com/mapfiles/kml/shapes/placemark_circle_highlight.png",
    ))  # yellow-ish
    parts.append(kml_style(
        "s_launch_l8", "ff0000ff", "1.2",
        "http://maps.google.com/mapfiles/kml/shapes/placemark_circle_highlight.png",
    ))  # red
    parts.append(kml_poly_style("s_area", "ff00ccff", "3300ccff"))  # yellow line/fill

    # --- Folder: area polygons
    parts.append('<Folder><name>Area polygons</name><open>0</open>')
    for n in range(1, 11):
        parts.append(polygon_placemark(f"Area {n}", polys[n], "s_area",
                                       f"Photogrammetry area {n}"))
    parts.append("</Folder>")

    # --- Folder: BOTH
    parts.append(f'<Folder><name>Both (covered by both 5 and 8 launch sets) - {n_both}</name><open>0</open>')
    for area_n, lat, lon, covering, cat in results:
        if cat != "BOTH":
            continue
        desc = f"Area {area_n}; covered by: {','.join(covering)}"
        parts.append(placemark(f"A{area_n}", lat, lon, "s_both", desc))
    parts.append("</Folder>")

    # --- Folder: ONLY 5
    parts.append(f'<Folder><name>Only 5-launch covers (unexpected) - {n_only5}</name><open>1</open>')
    for area_n, lat, lon, covering, cat in results:
        if cat != "ONLY 5":
            continue
        desc = f"Area {area_n}; covered by: {','.join(covering)}"
        parts.append(placemark(f"A{area_n}", lat, lon, "s_only5", desc))
    parts.append("</Folder>")

    # --- Folder: ONLY 8
    parts.append(
        f'<Folder><name>Only 8-launch covers (these {n_only8} points are the price of 100% vs 97.3%)</name><open>1</open>'
    )
    for area_n, lat, lon, covering, cat in results:
        if cat != "ONLY 8":
            continue
        desc = f"Area {area_n}; covered by: {','.join(covering)}"
        parts.append(placemark(f"A{area_n}", lat, lon, "s_only8", desc))
    parts.append("</Folder>")

    # --- Folder: uncovered (debug — should be 0)
    if n_uncovered:
        parts.append(f'<Folder><name>Uncovered (debug) - {n_uncovered}</name><open>1</open>')
        for area_n, lat, lon, covering, cat in results:
            if cat != "neither":
                continue
            desc = f"Area {area_n}; NOT covered by any launch"
            parts.append(placemark(f"A{area_n}", lat, lon, "s_uncov", desc))
        parts.append("</Folder>")

    # --- Folder: launches
    parts.append('<Folder><name>Launches</name><open>1</open>')
    for name, lat, lon, alt, serves in LAUNCHES:
        sid = "s_launch_l5" if name in L5_NAMES else "s_launch_l8"
        group = "5-launch set" if name in L5_NAMES else "8-launch only"
        desc = f"{name} ({group}); ground ~{launch_ground[name]:.0f}m AMSL; serves areas {serves}"
        coords = f"{lon:.6f},{lat:.6f},0"
        parts.append(
            f'<Placemark><name>{name}</name>'
            f'<description><![CDATA[{desc}]]></description>'
            f'<styleUrl>#{sid}</styleUrl>'
            f'<Point><coordinates>{coords}</coordinates></Point>'
            f'</Placemark>'
        )
    parts.append("</Folder>")

    parts.append("</Document></kml>\n")
    kml_text = "".join(parts)

    # Write binary UTF-8, no BOM, no CRLF
    data = kml_text.replace("\r\n", "\n").encode("utf-8")
    with open(OUT_PATH, "wb") as f:
        f.write(data)
    n_bytes = os.path.getsize(OUT_PATH)
    print(f"\nWrote {OUT_PATH}  ({n_bytes} bytes)")

    # Validate XML
    try:
        ET.parse(OUT_PATH)
        xml_ok = True
        print("XML self-check: OK")
    except Exception as e:
        xml_ok = False
        print(f"XML self-check: FAILED: {e}")

    return {
        "out_path": OUT_PATH.replace("\\", "/"),
        "file_bytes": n_bytes,
        "xml_self_check_valid": xml_ok,
        "n_sample_points_total": len(results),
        "n_both": n_both,
        "n_only_5": n_only5,
        "n_only_8": n_only8,
        "n_uncovered": n_uncovered,
    }


if __name__ == "__main__":
    r = main()
    print("\nRESULT:")
    for k, v in r.items():
        print(f"  {k} = {v}")
