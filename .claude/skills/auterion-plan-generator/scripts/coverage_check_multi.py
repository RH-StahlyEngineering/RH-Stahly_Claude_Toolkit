"""Compute aggregate coverage of a target KML by a SET of .plan files (Survey or CorridorScan).

Uses Ryan's LiDAR FOV convention (skill canonical):
  - Total FOV = 90° → ground swath per pass = 2 · AGL (where AGL = DistanceToSurface)
  - Line spacing = AGL → 50% side overlap between adjacent passes
  - For an N-transect mission, OUTER coverage envelope perpendicular to flight =
    (N-1)/2 · AGL  + AGL  (= half corridor width + half outer swath)
    For CorridorWidth = 2·AGL (2 transects), envelope = AGL/2 + AGL = 1.5·AGL each side
    = 105.156 m for AGL=70.104 → total swath 210.3 m.

Algorithm:
  1. Parse each .plan: extract polyline (CorridorScan) or polygon (Survey) + AGL + CorridorWidth.
  2. Build a shapely polygon for each plan's actual GROUND coverage (corridor centerline
     buffered by the FOV envelope perpendicular + turnaround/end caps).
  3. Union all per-plan polygons → total covered area.
  4. Load target KML polygon.
  5. covered_area = target ∩ union;  uncovered_area = target − union.
  6. Report coverage % and write the uncovered area as a KML of polygons.

Project to local equirectangular meters frame anchored at the target centroid.
"""
import argparse
import glob
import json
import math
import os
import re
import sys
import xml.etree.ElementTree as ET

from shapely.geometry import Polygon, LineString, MultiPolygon, MultiLineString
from shapely.ops import unary_union, transform


def parse_kml_polygon(kml_path):
    tree = ET.parse(kml_path)
    root = tree.getroot()
    ns_pattern = re.compile(r'\{[^}]+\}')
    for elem in root.iter():
        elem.tag = ns_pattern.sub('', elem.tag)
    polys = []
    for poly in root.iter('Polygon'):
        outer = poly.find('outerBoundaryIs/LinearRing/coordinates')
        if outer is None:
            continue
        pts = []
        for tok in outer.text.strip().split():
            parts = tok.split(',')
            lon = float(parts[0]); lat = float(parts[1])
            pts.append((lat, lon))
        if pts and pts[0] == pts[-1]:
            pts = pts[:-1]
        # Inner rings (holes)
        holes = []
        for inner in poly.findall('innerBoundaryIs/LinearRing/coordinates'):
            hpts = []
            for tok in inner.text.strip().split():
                parts = tok.split(',')
                lon = float(parts[0]); lat = float(parts[1])
                hpts.append((lat, lon))
            if hpts and hpts[0] == hpts[-1]:
                hpts = hpts[:-1]
            holes.append(hpts)
        polys.append((pts, holes))
    return polys


def parse_plan_geometry(plan_path):
    """Return (kind, polyline_or_polygon, agl, corridor_width or None, turnaround)
    where kind is 'CorridorScan' or 'survey'."""
    p = json.load(open(plan_path))
    for it in p['mission']['items']:
        if it.get('complexItemType') == 'CorridorScan':
            tsi = it['TransectStyleComplexItem']
            return ('CorridorScan',
                    [tuple(pt) for pt in it['polyline']],
                    tsi['CameraCalc']['DistanceToSurface'],
                    it['CorridorWidth'],
                    tsi.get('TurnAroundDistance', 0))
        if it.get('complexItemType') == 'survey':
            tsi = it['TransectStyleComplexItem']
            return ('survey',
                    [tuple(pt) for pt in it['polygon']],
                    tsi['CameraCalc']['DistanceToSurface'],
                    None,
                    tsi.get('TurnAroundDistance', 0))
    raise ValueError(f"No survey/CorridorScan in {plan_path}")


def make_projection(ref_lat, ref_lon):
    mlat = 111132.0
    mlon = 111132.0 * math.cos(math.radians(ref_lat))
    def to_xy(lat, lon):
        return ((lon - ref_lon) * mlon, (lat - ref_lat) * mlat)
    def to_ll(x, y):
        return (ref_lat + y / mlat, ref_lon + x / mlon)
    return to_xy, to_ll


def corridorscan_coverage_polygon(polyline_ll, agl, corridor_width, turnaround_m, to_xy):
    """Build the ground-coverage polygon for one CorridorScan plan.

    LiDAR ground swath envelope = corridor_width/2 + agl/2 perpendicular each side
    (CorridorWidth/2 reaches the OUTERMOST transect line; that transect's ground
    swath extends another AGL/2 outward — FOV 90° → swath = 2·AGL).

    Along the polyline, the data swath extends to the polyline endpoints. We also
    add turnaround_m at each end as flat caps (drone is flying & LiDAR is on during
    the run-up/run-out near the turnaround start/end, so the swath extends a bit).
    Shapely's LineString.buffer() with cap_style='flat' on a polyline-extended-by-turnaround
    gives the correct envelope.
    """
    xy = [to_xy(*p) for p in polyline_ll]
    if len(xy) < 2:
        return None

    # Extend polyline at both ends by turnaround_m along the local tangent
    def extend(p, anchor, dist):
        dx = p[0] - anchor[0]; dy = p[1] - anchor[1]
        L = math.hypot(dx, dy)
        if L == 0: return p
        return (p[0] + dist * dx / L, p[1] + dist * dy / L)

    extended_xy = [extend(xy[0], xy[1], turnaround_m)] + list(xy[1:-1]) + [extend(xy[-1], xy[-2], turnaround_m)]
    # If polyline has only 2 points, the above still works:
    if len(xy) == 2:
        extended_xy = [extend(xy[0], xy[1], turnaround_m), extend(xy[-1], xy[-2], turnaround_m)]

    line = LineString(extended_xy)
    envelope_half = corridor_width / 2 + agl / 2
    return line.buffer(envelope_half, cap_style='flat', join_style='round')


def survey_coverage_polygon(polygon_ll, agl, to_xy):
    """Survey-type ground coverage. The skill convention: line spacing = AGL,
    swath = 2*AGL, 50% overlap. For a Survey defined as a polygon, the LiDAR
    ground coverage extends AGL/2 BEYOND the polygon boundary (because the outermost
    transect is AGL/2 inside the boundary and its swath extends AGL/2 outward).
    Approximate coverage = polygon dilated by AGL/2."""
    xy = [to_xy(*p) for p in polygon_ll]
    poly = Polygon(xy)
    return poly.buffer(agl / 2, join_style='mitre')


def coverage_to_kml(geom, to_ll, target_holes_ll, output_path, name='Uncovered'):
    """Write a Shapely Polygon/MultiPolygon (in meters) back to KML, using to_ll
    to convert vertices. target_holes_ll are holes in the original target KML
    that should be excluded from the output as well (already excluded from `geom`
    if computed correctly, but keep this hook for verification)."""
    polys = []
    if geom.is_empty:
        polys = []
    elif geom.geom_type == 'Polygon':
        polys = [geom]
    elif geom.geom_type == 'MultiPolygon':
        polys = list(geom.geoms)
    elif geom.geom_type == 'GeometryCollection':
        polys = [g for g in geom.geoms if g.geom_type == 'Polygon']
    else:
        raise ValueError(f"Unexpected geom type: {geom.geom_type}")

    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<kml xmlns="http://www.opengis.net/kml/2.2">',
             '<Document>',
             f'<name>{name}</name>',
             '<Style id="gap">',
             '<LineStyle><color>ff0000ff</color><width>2</width></LineStyle>',
             '<PolyStyle><color>5500ffff</color></PolyStyle>',
             '</Style>']
    for i, p in enumerate(polys):
        area_m2 = p.area
        area_ac = area_m2 / 4046.86
        lines.append(f'<Placemark>')
        lines.append(f'<name>Gap {i+1} ({area_ac:.2f} ac)</name>')
        lines.append(f'<styleUrl>#gap</styleUrl>')
        lines.append('<Polygon>')
        lines.append('<outerBoundaryIs><LinearRing><coordinates>')
        outer = list(p.exterior.coords)
        coords = ' '.join(f'{to_ll(x,y)[1]:.7f},{to_ll(x,y)[0]:.7f},0' for x,y in outer)
        lines.append(coords)
        lines.append('</coordinates></LinearRing></outerBoundaryIs>')
        for inner in p.interiors:
            lines.append('<innerBoundaryIs><LinearRing><coordinates>')
            ipts = list(inner.coords)
            icoords = ' '.join(f'{to_ll(x,y)[1]:.7f},{to_ll(x,y)[0]:.7f},0' for x,y in ipts)
            lines.append(icoords)
            lines.append('</coordinates></LinearRing></innerBoundaryIs>')
        lines.append('</Polygon>')
        lines.append('</Placemark>')
    lines.append('</Document></kml>')
    with open(output_path, 'wb') as f:
        f.write('\n'.join(lines).encode('utf-8'))
    return len(polys)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--target', required=True, help='Target KML polygon to cover')
    ap.add_argument('--plans-glob', required=True, action='append',
                    help='Glob pattern for .plan files (can be passed multiple times)')
    ap.add_argument('--out-gaps-kml', required=True, help='Where to write the uncovered gaps KML')
    args = ap.parse_args()

    # Load target
    target_list = parse_kml_polygon(args.target)
    if not target_list:
        print('No target polygon found', file=sys.stderr); sys.exit(1)
    print(f'Target polygons: {len(target_list)}')
    # Use first polygon (the corridor union has just one)
    target_outer_ll, target_holes_ll = target_list[0]
    print(f'Target outer ring: {len(target_outer_ll)} vertices')

    # Project anchor = centroid of target outer ring
    ref_lat = sum(p[0] for p in target_outer_ll) / len(target_outer_ll)
    ref_lon = sum(p[1] for p in target_outer_ll) / len(target_outer_ll)
    to_xy, to_ll = make_projection(ref_lat, ref_lon)

    target_xy = Polygon([to_xy(*p) for p in target_outer_ll],
                        [[to_xy(*p) for p in h] for h in target_holes_ll])
    target_area_m2 = target_xy.area
    target_area_ac = target_area_m2 / 4046.86
    print(f'Target area: {target_area_ac:.2f} acres = {target_area_m2:.0f} m^2')

    # Load all plans
    plan_files = []
    for pat in args.plans_glob:
        plan_files.extend(sorted(glob.glob(pat)))
    print(f'\nFound {len(plan_files)} .plan files:')
    coverage_polys = []
    for pp in plan_files:
        kind, geom_ll, agl, cw, ta = parse_plan_geometry(pp)
        if kind == 'CorridorScan':
            poly = corridorscan_coverage_polygon(geom_ll, agl, cw, ta, to_xy)
            envelope = cw/2 + agl/2 if cw else agl
            print(f'  {os.path.basename(pp):<22} {kind:<13} AGL={agl:6.2f} CW={cw:7.3f} TA={ta:5.2f}  envelope±{envelope:.1f}m')
        else:
            poly = survey_coverage_polygon(geom_ll, agl, to_xy)
            print(f'  {os.path.basename(pp):<22} {kind:<13} AGL={agl:6.2f}                          envelope±{agl/2:.1f}m')
        if poly is not None and not poly.is_empty:
            coverage_polys.append(poly)

    # Union all coverage polygons
    print(f'\nUnioning {len(coverage_polys)} coverage polygons...')
    coverage_union = unary_union(coverage_polys)
    print(f'Total coverage area (anywhere): {coverage_union.area/4046.86:.2f} acres')

    # Coverage within target
    covered = coverage_union.intersection(target_xy)
    covered_area_m2 = covered.area
    covered_area_ac = covered_area_m2 / 4046.86
    pct = 100.0 * covered_area_m2 / target_area_m2
    print(f'\nCovered (intersect target): {covered_area_ac:.2f} acres = {covered_area_m2:.0f} m^2')
    print(f'TARGET COVERAGE: {pct:.2f}%')

    # Uncovered = target - coverage
    uncovered = target_xy.difference(coverage_union)
    uncovered_area_m2 = uncovered.area
    uncovered_area_ac = uncovered_area_m2 / 4046.86
    print(f'Uncovered (target - coverage): {uncovered_area_ac:.2f} acres = {uncovered_area_m2:.0f} m^2')

    n = coverage_to_kml(uncovered, to_ll, target_holes_ll, args.out_gaps_kml,
                       name=f'Uncovered area ({uncovered_area_ac:.2f} ac, {pct:.2f}% covered)')
    print(f'\nWrote {n} uncovered polygons to {args.out_gaps_kml}')


if __name__ == '__main__':
    main()
