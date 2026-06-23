"""
Check that a .plan's survey covers a target KML polygon.

Assumes Ryan's LiDAR convention:
  - Total FOV = 90°
  - Ground swath = 2 · AGL (where AGL = DistanceToSurface)
  - Line spacing = AGL → 50% side overlap

Method:
  1. Parse KML target polygon (lat/lon)
  2. Parse .plan: survey polygon, transect angle, DistanceToSurface (AGL)
  3. Project both polygons to a local east-north meters frame
  4. Rotate so transect lines are horizontal
  5. Generate transect lines (parallel horizontal lines spaced AGL apart,
     clipped to the survey polygon x-extent)
  6. Each transect covers a strip of width 2·AGL perpendicular to flight direction
  7. Grid-sample target polygon, check each point against strip union
  8. Report coverage percentage and uncovered regions

Usage:
    python coverage_check.py mission.plan target.kml [--grid 1.0]
"""
import argparse
import json
import math
import os
import re
import sys
import xml.etree.ElementTree as ET


# ===== KML parsing =====

def parse_kml_polygon(kml_path: str):
    """Return list of [lat, lon] vertices from the first Polygon outer ring in a KML."""
    tree = ET.parse(kml_path)
    root = tree.getroot()
    # KML uses default namespace; strip it for simple xpath
    ns_pattern = re.compile(r'\{[^}]+\}')
    for elem in root.iter():
        elem.tag = ns_pattern.sub('', elem.tag)
    coords_elem = None
    for poly in root.iter('Polygon'):
        outer = poly.find('outerBoundaryIs')
        if outer is not None:
            coords_elem = outer.find('LinearRing/coordinates')
            if coords_elem is not None:
                break
    if coords_elem is None:
        # Fallback: first <coordinates> anywhere
        for c in root.iter('coordinates'):
            coords_elem = c
            break
    if coords_elem is None:
        raise ValueError(f"No coordinates found in {kml_path}")
    pts = []
    for tok in coords_elem.text.strip().split():
        parts = tok.split(',')
        lon = float(parts[0]); lat = float(parts[1])
        pts.append([lat, lon])
    # Drop closing duplicate vertex if present
    if pts[0] == pts[-1]:
        pts = pts[:-1]
    return pts


# ===== .plan parsing =====

def parse_plan_survey(plan_path: str):
    """Return (polygon, angle_deg, agl) from a .plan file's first survey item."""
    p = json.load(open(plan_path))
    for it in p['mission']['items']:
        if it.get('complexItemType') == 'survey':
            return (it['polygon'],
                    it.get('angle', 0),
                    it['TransectStyleComplexItem']['CameraCalc']['DistanceToSurface'])
    raise ValueError(f"No survey item in {plan_path}")


# ===== Local east-north projection =====

def make_projection(ref_lat, ref_lon):
    """Return (to_xy, to_ll) functions for a local equirectangular projection."""
    mlat = 111132.0
    mlon = 111132.0 * math.cos(math.radians(ref_lat))
    def to_xy(lat, lon):
        return ((lon - ref_lon) * mlon, (lat - ref_lat) * mlat)
    def to_ll(x, y):
        return (ref_lat + y / mlat, ref_lon + x / mlon)
    return to_xy, to_ll


# ===== Rotation =====

def rotate(pt, angle_rad):
    x, y = pt
    c, s = math.cos(angle_rad), math.sin(angle_rad)
    return (c*x + s*y, -s*x + c*y)


# ===== Polygon math =====

def point_in_polygon(pt, poly):
    """Ray-cast point-in-polygon for a 2D (x,y) polygon."""
    x, y = pt
    n = len(poly); inside = False
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]; xj, yj = poly[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-30) + xi):
            inside = not inside
        j = i
    return inside


def polygon_bbox(poly):
    xs = [p[0] for p in poly]; ys = [p[1] for p in poly]
    return min(xs), min(ys), max(xs), max(ys)


# ===== Coverage =====

def coverage(plan_path, kml_path, grid_m=1.0):
    """Compute coverage of KML polygon by .plan's survey transect strips."""
    target_ll = parse_kml_polygon(kml_path)
    survey_ll, angle_deg, agl = parse_plan_survey(plan_path)

    # Reference point for local projection = centroid of survey polygon
    ref_lat = sum(p[0] for p in survey_ll) / len(survey_ll)
    ref_lon = sum(p[1] for p in survey_ll) / len(survey_ll)
    to_xy, to_ll = make_projection(ref_lat, ref_lon)

    # Project, then rotate so transect lines run along +x (horizontal)
    angle_rad = math.radians(angle_deg)
    # AMC angle convention: angle is direction of transect line from north, clockwise.
    # We want transects horizontal in rotated frame → rotate by -(90° - angle) = angle - 90°.
    # Empirically: angle=270 means E-W lines, which we want horizontal. 270 - 90 = 180 — no.
    # Use the angle directly: rotate by -angle so the survey-defined transect direction
    # ends up along +x.
    rot = -angle_rad

    survey_xy  = [rotate(to_xy(*p), rot) for p in survey_ll]
    target_xy  = [rotate(to_xy(*p), rot) for p in target_ll]

    # Transect lines: horizontal lines at y = y_min + agl/2 + k*agl, for k = 0,1,...
    sx0, sy0, sx1, sy1 = polygon_bbox(survey_xy)
    # First line is half-swath inside the polygon edge; subsequent lines spaced agl apart.
    # We want lines such that adjacent swaths exactly tile the polygon at line spacing agl.
    # With swath = 2*agl and spacing = agl → 50% overlap → first line at sy0 + 0 (edge), then sy0 + agl, etc.
    # But conservative: first at sy0 + agl/2 (so the strip's outer edge touches polygon edge).
    # Different planners differ; we'll test both and use whichever matches better.
    transect_ys = []
    y = sy0 + agl / 2.0
    while y <= sy1 + 1e-6:
        transect_ys.append(y)
        y += agl
    # Each transect covers y ± agl (swath = 2*agl).
    # A point is covered if ANY transect's strip includes it AND it's inside survey polygon.

    # Grid-sample target polygon
    tx0, ty0, tx1, ty1 = polygon_bbox(target_xy)
    nx = max(2, int(math.ceil((tx1 - tx0) / grid_m)))
    ny = max(2, int(math.ceil((ty1 - ty0) / grid_m)))
    total = 0; covered = 0; uncovered_pts = []
    for i in range(nx + 1):
        for j in range(ny + 1):
            px = tx0 + i * grid_m
            py = ty0 + j * grid_m
            if not point_in_polygon((px, py), target_xy):
                continue
            total += 1
            # Inside target. Is it covered by any strip AND inside survey?
            in_survey = point_in_polygon((px, py), survey_xy)
            in_strip = False
            if in_survey:
                for ty in transect_ys:
                    if abs(py - ty) <= agl + 1e-6:
                        in_strip = True; break
            if in_strip:
                covered += 1
            else:
                uncovered_pts.append((px, py))

    return {
        'agl': agl,
        'angle_deg': angle_deg,
        'swath_m': 2 * agl,
        'line_spacing_m': agl,
        'transect_count': len(transect_ys),
        'target_pts_total': total,
        'target_pts_covered': covered,
        'coverage_pct': 100.0 * covered / total if total else 0.0,
        'uncovered_pts_xy': uncovered_pts,
        'rot': rot,
        'to_ll': to_ll,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('plan', help='.plan file with the survey')
    ap.add_argument('kml', help='KML file with target coverage polygon')
    ap.add_argument('--grid', type=float, default=1.0, help='Grid spacing in meters (default 1.0)')
    args = ap.parse_args()

    r = coverage(args.plan, args.kml, grid_m=args.grid)

    print(f"=== Coverage check ===")
    print(f"plan: {os.path.basename(args.plan)}")
    print(f"target: {os.path.basename(args.kml)}")
    print(f"AGL: {r['agl']:.2f} m  -> swath {r['swath_m']:.2f} m, line spacing {r['line_spacing_m']:.2f} m (50% overlap)")
    print(f"Transect angle: {r['angle_deg']:.1f}°")
    print(f"Transect count (computed): {r['transect_count']}")
    print(f"Target sampled at {args.grid:.2f} m grid: {r['target_pts_total']} points")
    print(f"Covered: {r['target_pts_covered']} / {r['target_pts_total']}")
    print(f"COVERAGE: {r['coverage_pct']:.2f}%")
    if r['uncovered_pts_xy']:
        print(f"\nUncovered points: {len(r['uncovered_pts_xy'])}")
        # Convert a few uncovered points back to lat/lon for the user
        c, s = math.cos(-r['rot']), math.sin(-r['rot'])
        to_ll = r['to_ll']
        sample = r['uncovered_pts_xy'][::max(1, len(r['uncovered_pts_xy'])//5)][:5]
        print("Sample uncovered locations (lat, lon):")
        for x, y in sample:
            # un-rotate back
            ux = c*x + s*y
            uy = -s*x + c*y
            lat, lon = to_ll(ux, uy)
            print(f"  ({lat:.6f}, {lon:.6f})")
    else:
        print("\nAll sampled target points covered.")


if __name__ == '__main__':
    main()
