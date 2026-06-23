"""
Geometry helpers for slicing a large KML into multiple mission tiles.

Used by the corridor-tiling driver (forthcoming). Stdlib + numpy only.

Includes:
  - sh_clip: Sutherland-Hodgman polygon clipping (subject ∩ convex clipper)
  - k_longest_bearing: length-weighted mean bearing of the k longest segments in a polygon
  - signed_area, ensure_ccw: winding-order utilities
  - decimate_polygon: drop vertices closer than min_dist (m)
  - polygon_intersection_area: area of intersection
  - point_in_polygon: ray-cast PIP
"""
import math


def signed_area(poly):
    """Signed shoelace area; positive = CCW, negative = CW."""
    n = len(poly); a = 0.0
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        a += x1 * y2 - x2 * y1
    return a / 2.0


def ensure_ccw(poly):
    """Return poly reversed if it's CW; otherwise unchanged. SH needs CCW clipper."""
    return list(poly) if signed_area(poly) > 0 else list(reversed(poly))


def sh_clip(subject, clipper):
    """Sutherland-Hodgman polygon clipping. Subject can be any orientation;
    clipper must be convex. Both are lists of (x, y) tuples in meters."""
    clipper = ensure_ccw(clipper)

    def inside(p, a, b):
        return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]) >= 0

    def intersect(p1, p2, a, b):
        x1, y1 = p1; x2, y2 = p2; x3, y3 = a; x4, y4 = b
        d = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
        if abs(d) < 1e-12: return p1
        t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / d
        return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))

    output = list(subject)
    n = len(clipper)
    for i in range(n):
        if not output: break
        a, b = clipper[i], clipper[(i + 1) % n]
        inp = output; output = []
        S = inp[-1]
        for E in inp:
            if inside(E, a, b):
                if not inside(S, a, b):
                    output.append(intersect(S, E, a, b))
                output.append(E)
            elif inside(S, a, b):
                output.append(intersect(S, E, a, b))
            S = E
    return output


def k_longest_bearing(polygon_xy, near_xy=None, radius=None, k=10):
    """Return length-weighted mean axis bearing (0..180 deg from north) of the
    k longest segments. Optionally filter by midpoint distance < radius from near_xy.

    Bearings are 'axis form' — direction-agnostic, so 0 ≡ 180.
    """
    edges = []
    n = len(polygon_xy)
    for i in range(n):
        a = polygon_xy[i]; b = polygon_xy[(i + 1) % n]
        if near_xy is not None and radius is not None:
            mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            if math.hypot(mid[0] - near_xy[0], mid[1] - near_xy[1]) > radius:
                continue
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(dx, dy)
        if L < 0.5: continue
        brg = math.degrees(math.atan2(dx, dy)) % 180
        edges.append((L, brg))
    edges.sort(reverse=True)
    top = edges[:k]
    if not top: return None
    total = sum(L for L, _ in top)
    return sum(L * b for L, b in top) / total


def decimate_polygon(poly, min_dist=2.0):
    """Drop vertices closer than min_dist meters to the previous kept vertex."""
    if not poly: return []
    out = [poly[0]]
    for p in poly[1:]:
        if math.hypot(p[0] - out[-1][0], p[1] - out[-1][1]) >= min_dist:
            out.append(p)
    return out


def point_in_polygon(pt, poly):
    """Ray-cast PIP for a 2D (x,y) polygon."""
    x, y = pt; n = len(poly); inside = False; j = n - 1
    for i in range(n):
        xi, yi = poly[i]; xj, yj = poly[j]
        if ((yi > y) != (yj > y)) and \
           (x < (xj - xi) * (y - yi) / (yj - yi + 1e-30) + xi):
            inside = not inside
        j = i
    return inside


def polygon_intersection_area(a, b):
    """Area of the intersection of two polygons (m^2). b must be convex."""
    clipped = sh_clip(a, b)
    return abs(signed_area(clipped)) if len(clipped) >= 3 else 0.0


# === Lat/lon ↔ meters helpers ===
EARTH_M_PER_DEG_LAT = 111132.0

def make_local_projection(ref_lat, ref_lon):
    """Return (to_xy, to_ll) for a local equirectangular projection."""
    mlon = EARTH_M_PER_DEG_LAT * math.cos(math.radians(ref_lat))
    def to_xy(lat, lon):
        return ((lon - ref_lon) * mlon, (lat - ref_lat) * EARTH_M_PER_DEG_LAT)
    def to_ll(x, y):
        return (ref_lat + y / EARTH_M_PER_DEG_LAT, ref_lon + x / mlon)
    return to_xy, to_ll


if __name__ == '__main__':
    # Self-test
    sq = [(0, 0), (10, 0), (10, 10), (0, 10)]
    print(f"square area: {abs(signed_area(sq))} (expect 100)")
    print(f"signed area: {signed_area(sq)} (CCW expect +50)")
    clipper = [(2, 2), (8, 2), (8, 8), (2, 8)]
    c = sh_clip(sq, clipper)
    print(f"clipped area: {abs(signed_area(c))} (expect 36)")
    poly = [(0, 0), (100, 5), (100, 15), (0, 10)]  # nearly horizontal
    brg = k_longest_bearing(poly, k=2)
    print(f"horizontal poly bearing: {brg:.1f} (expect near 90)")
