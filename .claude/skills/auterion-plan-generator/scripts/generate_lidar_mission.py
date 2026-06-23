"""
Generate a canonical LiDAR mission .plan from a base file + per-mission variables.

The canonical structure (per SKILL.md):
    1. cmd 530 (mission options)
    2. cmd 178 (set speed — the ONLY speed change)
    3. Climb to flight altitude at HOME
    4-14. Figure-8 #1 (11 wps, 10 legs)
    15. Survey (terrain-follow, Manual camera)
    16-17. Cross-line (2 wps, extended past polygon edges)
    18-28. Figure-8 #2
    29. Return to HOME

Total: 29 items. First WP and last WP share lat/lon (= HOME).

Standalone waypoint altitudes are DEM-baked via USGS 3DEP because AMC does NOT
recompute terrain for standalone waypoints on file open (see known-pitfalls.md #1).

Constants are sourced from constants-and-variables.md and applied here.
Variables must be supplied by the caller.

Usage (as a script, simple case):
    python generate_lidar_mission.py \
        --base /path/to/RBH_modified.plan \
        --out  /path/to/new_mission.plan \
        --home-lat 47.153512 --home-lon -109.461364 \
        --agl 40 --speed 8 --cross-margin 25

Usage (as a module — preferred for KML-driven flows):
    from generate_lidar_mission import build_mission
    build_mission(base_plan_path, out_path,
                  home=(lat, lon),
                  agl_target=40.0,
                  speed=8.0,
                  cross_margin=25.0,
                  polygon=None,        # if None, reuse base file's polygon
                  figure8_duration=15.0)
"""
import argparse
import json
import math
import os
import sys
import time

# Allow importing siblings when run as a script
sys.path.insert(0, os.path.dirname(__file__))
from dem_lookup import terrain_amsl  # noqa: E402
from figure8 import fig8_waypoints  # noqa: E402

# === CONSTANTS (hold across all missions; see constants-and-variables.md) ===
TERRAIN_CLIMB_RATE = 3.0     # m/s
TERRAIN_DESCENT_RATE = 3.0   # m/s
GLOBAL_ALT_MODE = 3          # Calc-Above-Terrain — required for terrain-follow


def _make_wp(lat, lon, amsl, frame=0):
    return {'autoContinue': True, 'command': 16, 'doJumpId': 0, 'frame': frame,
            'groupTag': 0, 'params': [0, 0, 0, None, lat, lon, amsl],
            'type': 'SimpleItem'}


def _make_speed_set(speed):
    return {'MISSION_ITEM_ID': '0', 'autoContinue': True, 'command': 178,
            'doJumpId': 0, 'frame': 2, 'groupTag': 0,
            'params': [1, speed, -1, 0, 0, 0, 0], 'type': 'SimpleItem'}


def _dem_bake_fig8(wps, agl_target):
    """Replace each waypoint's altitude with terrain_amsl + agl_target.

    Mutates the wps list in place.
    """
    for w in wps:
        lat, lon = w['params'][4], w['params'][5]
        w['params'][6] = terrain_amsl(lat, lon) + agl_target
    return wps


def build_mission(base_plan_path: str, out_path: str, *,
                  home: tuple,
                  agl_target: float = 40.0,
                  speed: float = 8.0,
                  cross_margin: float = 25.0,
                  polygon=None,
                  figure8_duration: float = 15.0,
                  cross_axis: str = 'auto'):
    """Build a canonical LiDAR mission .plan.

    Args:
        base_plan_path: existing .plan file that contains a survey item.
                        Used as the source of the survey block (camera, polygon,
                        terrain settings) and top-level mission constants.
        out_path: where to write the new minified .plan
        home: (lat, lon) — required, user-defined per mission
        agl_target: meters above terrain for all standalone waypoints
        speed: m/s, constant throughout mission
        cross_margin: meters to extend cross-line past each polygon edge
        polygon: optional list of [lat, lon] vertices to replace the base survey polygon.
                 If None, the base file's polygon is preserved.
        figure8_duration: target flight time per figure-8, seconds
        cross_axis: 'auto' (perpendicular to survey angle), 'ns', or 'ew'

    Returns: dict with summary stats.
    """
    plan = json.load(open(base_plan_path))
    m = plan['mission']
    items = m['items']

    # Locate the survey item
    survey = next((it for it in items if it.get('complexItemType') == 'survey'), None)
    if survey is None:
        raise ValueError(f"No survey item found in {base_plan_path}")

    ts = survey['TransectStyleComplexItem']

    # Apply constants to the survey
    ts['FlightSpeed'] = speed
    ts['TerrainAdjustMaxClimbRate'] = TERRAIN_CLIMB_RATE
    ts['TerrainAdjustMaxDescentRate'] = TERRAIN_DESCENT_RATE
    m['globalPlanAltitudeMode'] = GLOBAL_ALT_MODE

    # Override polygon if requested
    if polygon is not None:
        survey['polygon'] = [list(v) for v in polygon]
        # AMC will regenerate the inner Items array on open (Behavior A)
        # so we don't need to recompute transects here.

    poly = survey['polygon']
    lats = [p[0] for p in poly]
    lons = [p[1] for p in poly]
    lat_min, lat_max = min(lats), max(lats)
    lon_min, lon_max = min(lons), max(lons)
    lat_mid = (lat_min + lat_max) / 2
    lon_mid = (lon_min + lon_max) / 2

    # Cross-line orientation is now always derived from survey.angle in the
    # cross-line placement block below — the legacy cross_axis arg is ignored.
    # (kept in the signature for backwards compatibility)

    # === Build standalone waypoints (DEM-baked) ===
    home_lat, home_lon = home
    print(f"Sampling USGS 3DEP terrain (AGL target {agl_target} m)...", file=sys.stderr)
    t0 = time.time()

    climb_wp = _make_wp(home_lat, home_lon, terrain_amsl(home_lat, home_lon) + agl_target)
    fig8_a = fig8_waypoints(home_lat, home_lon, 0,
                            speed=speed, duration=figure8_duration)
    _dem_bake_fig8(fig8_a, agl_target)

    # === Cross-line placement: exactly perpendicular to flight lines ===
    # Computed in the flight-frame (rotated by -angle so flight direction is +y,
    # perpendicular is +x). Cross-line is a line of constant y, spanning the
    # polygon's perpendicular extent + cross_margin on each end.
    #
    # Position along flight (y in flight frame):
    #   Primary  — one AGL from the survey exit waypoint, toward polygon center
    #              (Reading A)
    #   Fallback — one AGL inside the polygon edge (along-flight) nearest HOME,
    #              ranked by along-flight distance, ensuring it crosses transects
    #              and isn't on the edge.

    angle_deg = survey.get('angle', 0)
    poly_lat_c = sum(p[0] for p in poly) / len(poly)
    poly_lon_c = sum(p[1] for p in poly) / len(poly)
    _mlat = 111132.0
    _mlon = 111132.0 * math.cos(math.radians(poly_lat_c))
    def _to_local(la, lo):
        return ((lo - poly_lon_c) * _mlon, (la - poly_lat_c) * _mlat)
    def _from_local(x, y):
        return (poly_lat_c + y / _mlat, poly_lon_c + x / _mlon)
    _th = -math.radians(angle_deg)
    _c, _s = math.cos(_th), math.sin(_th)
    def _to_flight(x, y):  return ( _c*x + _s*y, -_s*x + _c*y)
    def _from_flight(xf, yf): return ( _c*xf - _s*yf,  _s*xf + _c*yf)

    poly_local = [_to_local(*p) for p in poly]
    poly_flight = [_to_flight(*p) for p in poly_local]
    perp_min = min(p[0] for p in poly_flight)
    perp_max = max(p[0] for p in poly_flight)
    along_min = min(p[1] for p in poly_flight)
    along_max = max(p[1] for p in poly_flight)
    along_mid = (along_min + along_max) / 2

    inner_wps = [s for s in ts.get('Items', []) if s.get('command') == 16]
    using_fallback = not inner_wps

    if inner_wps:
        exit_lat = inner_wps[-1]['params'][4]
        exit_lon = inner_wps[-1]['params'][5]
        _, exit_along = _to_flight(*_to_local(exit_lat, exit_lon))
        if exit_along > along_mid:
            cross_along = exit_along - agl_target
        else:
            cross_along = exit_along + agl_target
    else:
        # Fallback when survey has no inner Items: place cross-line one AGL inside the
        # FAR polygon edge (along-flight axis) from HOME. The drone naturally enters the
        # survey on the HOME-near side and exits on the FAR side; cross-line one AGL
        # inside the FAR edge gives Reading-A-equivalent placement and a transit that
        # makes the mission duration sit in [8,10] for typical tile geometries.
        _, home_along = _to_flight(*_to_local(home_lat, home_lon))
        if abs(home_along - along_min) < abs(home_along - along_max):
            cross_along = along_max - agl_target   # HOME near min → cross at far (max)
        else:
            cross_along = along_min + agl_target   # HOME near max → cross at far (min)

    # Cross-line endpoints in flight frame, then back to lat/lon
    cs_perp = perp_min - cross_margin
    ce_perp = perp_max + cross_margin
    cs_loc = _from_flight(cs_perp, cross_along)
    ce_loc = _from_flight(ce_perp, cross_along)
    cs_lat, cs_lon = _from_local(*cs_loc)
    ce_lat, ce_lon = _from_local(*ce_loc)

    # Pick the end nearest HOME as fig-8 #2 center (= where the return-to-HOME leg starts)
    home_x, home_y = _to_local(home_lat, home_lon)
    d_cs = math.hypot(cs_loc[0] - home_x, cs_loc[1] - home_y)
    d_ce = math.hypot(ce_loc[0] - home_x, ce_loc[1] - home_y)
    if d_ce <= d_cs:
        # Cross-line flies cs -> ce, fig-8 #2 at ce
        cross_start = _make_wp(cs_lat, cs_lon, terrain_amsl(cs_lat, cs_lon) + agl_target)
        cross_end   = _make_wp(ce_lat, ce_lon, terrain_amsl(ce_lat, ce_lon) + agl_target)
        fig8_b_center = (ce_lat, ce_lon)
    else:
        cross_start = _make_wp(ce_lat, ce_lon, terrain_amsl(ce_lat, ce_lon) + agl_target)
        cross_end   = _make_wp(cs_lat, cs_lon, terrain_amsl(cs_lat, cs_lon) + agl_target)
        fig8_b_center = (cs_lat, cs_lon)

    if using_fallback:
        print(f"  [info] no inner survey Items yet — used HOME-nearest-edge fallback "
              f"for cross-line position (one AGL inset along flight direction).",
              file=sys.stderr)

    fig8_b = fig8_waypoints(fig8_b_center[0], fig8_b_center[1], 0,
                            speed=speed, duration=figure8_duration)
    _dem_bake_fig8(fig8_b, agl_target)

    exit_wp = _make_wp(home_lat, home_lon, terrain_amsl(home_lat, home_lon) + agl_target)

    print(f"DEM sampling done in {time.time()-t0:.1f}s", file=sys.stderr)

    # === Assemble ===
    header_530 = items[0]   # preserve user's cmd 530
    speed_set = _make_speed_set(speed)

    new_items = ([header_530, speed_set, climb_wp]
                 + fig8_a
                 + [survey, cross_start, cross_end]
                 + fig8_b
                 + [exit_wp])

    # Renumber doJumpIds sequentially
    for n, it in enumerate(new_items, start=1):
        it['doJumpId'] = n

    m['items'] = new_items
    m['plannedHomePosition'] = [home_lat, home_lon, m.get('plannedHomePosition', [0, 0, 0])[2]]

    # Write minified (binary mode to guarantee LF only)
    with open(out_path, 'wb') as f:
        f.write(json.dumps(plan, separators=(',', ':')).encode('utf-8'))

    # Verification stats
    n_178 = sum(1 for it in new_items if it.get('command') == 178)
    n_16 = sum(1 for it in new_items if it.get('command') == 16)
    alts = [it['params'][6] for it in new_items if it.get('command') == 16]
    first = next(it for it in new_items if it.get('command') == 16)
    return {
        'items': len(new_items),
        'speed_changes': n_178,
        'waypoints': n_16,
        'amsl_range': (min(alts), max(alts)),
        'first_eq_last': (first['params'][4], first['params'][5]) == (exit_wp['params'][4], exit_wp['params'][5]),
        'cross_bearing_deg': (survey.get('angle', 0) + 90) % 360,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--base', required=True, help='Base .plan file to derive constants and survey from')
    ap.add_argument('--out', required=True, help='Output .plan path')
    ap.add_argument('--home-lat', type=float, required=True)
    ap.add_argument('--home-lon', type=float, required=True)
    ap.add_argument('--agl', type=float, default=40.0, help='Target AGL meters (default 40)')
    ap.add_argument('--speed', type=float, default=8.0, help='Constant speed m/s (default 8)')
    ap.add_argument('--cross-margin', type=float, default=25.0,
                    help='Cross-line extension past polygon edges, meters (default 25)')
    ap.add_argument('--fig8-duration', type=float, default=15.0,
                    help='Figure-8 flight time seconds (default 15)')
    ap.add_argument('--cross-axis', choices=['auto', 'ns', 'ew'], default='auto')
    args = ap.parse_args()

    stats = build_mission(args.base, args.out,
                          home=(args.home_lat, args.home_lon),
                          agl_target=args.agl,
                          speed=args.speed,
                          cross_margin=args.cross_margin,
                          figure8_duration=args.fig8_duration,
                          cross_axis=args.cross_axis)

    print(f"\nWrote {args.out}")
    print(f"  items: {stats['items']} (expected 29)")
    print(f"  speed changes: {stats['speed_changes']} (expected 1)")
    print(f"  waypoints: {stats['waypoints']}")
    print(f"  AMSL range: {stats['amsl_range'][0]:.2f} -> {stats['amsl_range'][1]:.2f} m"
          f"  (spread {stats['amsl_range'][1]-stats['amsl_range'][0]:.2f} m)")
    print(f"  first WP == last WP: {stats['first_eq_last']}")
    print(f"  cross-line axis: {stats['cross_axis']}")
    print("\nNext: open in desktop AMC to regenerate survey transects, save, then push to controller.")


if __name__ == '__main__':
    main()
