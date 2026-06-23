"""
Estimate AMC-reported flight duration from a .plan file using a calibrated model.

Fit RMSE = 0.18 min over 7 hilger / CourthouseLidar plans (2026-06-17).
PX4 multirotor only — do NOT trust these coefficients for ArduPilot or fixed-wing.

    AMC_min = 1.05 · survey_min + 1.08 · corridor_min + 1.97 · transit_min

Naive time (Σ d/v) understates AMC by 20-25% because it misses climb/decel
overhead on transits. The transit ×1.97 multiplier captures that.

Usage:
    python estimate_flight_time.py path/to/mission.plan [more.plan ...]
    python estimate_flight_time.py *.plan
"""
import glob
import json
import math
import os
import sys

K_SURVEY = 1.05
K_CORRIDOR = 1.08
K_TRANSIT = 1.97


def _haversine(a, b):
    R = 6371000
    la1, lo1 = math.radians(a[0]), math.radians(a[1])
    la2, lo2 = math.radians(b[0]), math.radians(b[1])
    return 2 * R * math.asin(math.sqrt(
        math.sin((la2 - la1) / 2) ** 2
        + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2))


def _analytic_survey_seconds(survey_item, speed):
    """Estimate survey time analytically when AMC hasn't generated inner Items yet.

    Uses polygon perpendicular-to-flight extent / line_spacing to get transect
    count, polygon along-flight extent for each transect length, and
    TurnAroundDistance for turnaround overhead.

    Returns 0 if the survey appears already populated (caller should use
    inner-Items walk in that case).
    """
    poly = survey_item.get('polygon', [])
    if not poly:
        return 0.0
    ts = survey_item['TransectStyleComplexItem']
    angle_deg = survey_item.get('angle', 0)
    line_spacing = ts['CameraCalc']['DistanceToSurface']  # = AGL = line spacing per Ryan's convention
    turn_d = ts.get('TurnAroundDistance', 15.24)

    # Project polygon to local frame, rotate so flight direction is +x
    lat0 = sum(p[0] for p in poly) / len(poly)
    lon0 = sum(p[1] for p in poly) / len(poly)
    mlat = 111132.0
    mlon = 111132.0 * math.cos(math.radians(lat0))
    pts = [((p[1] - lon0) * mlon, (p[0] - lat0) * mlat) for p in poly]
    th = -math.radians(angle_deg)
    c, s = math.cos(th), math.sin(th)
    rot = [(c*x + s*y, -s*x + c*y) for x, y in pts]

    # After rotating local-frame XY by -angle, the AMC angle's flight direction maps to +y;
    # perpendicular (transect stack axis) is +x.
    xs = [p[0] for p in rot]; ys = [p[1] for p in rot]
    along_extent = max(ys) - min(ys)            # transect length (along flight)
    perp_extent  = max(xs) - min(xs)            # perpendicular: spans the transect stack

    n_transects = max(1, int(math.ceil(perp_extent / line_spacing)))
    # Approximate: all transects span the full along-extent of the polygon
    total_transect_dist = n_transects * along_extent
    turnaround_dist = (n_transects - 1) * turn_d
    return (total_transect_dist + turnaround_dist) / speed


def split_minutes(plan_path: str):
    """Return (survey_min, corridor_min, transit_min).

    Survey time uses inner Items when present; falls back to analytic estimate
    from polygon geometry when Items is empty (fresh polygon, pre-AMC).
    Transit uses the .plan's `cruiseSpeed` directly (matches AMC's displayed duration).
    """
    with open(plan_path) as f:
        plan = json.load(f)
    m = plan['mission']
    cruise = m.get('cruiseSpeed', 15)
    survey_s = corridor_s = transit_s = 0.0
    prev = None

    def walk(items, speed, bucket):
        nonlocal survey_s, corridor_s, transit_s, prev
        sp = None
        for s in items:
            if s.get('command') == 16:
                pt = (s['params'][4], s['params'][5])
                if sp:
                    d = _haversine(sp, pt)
                    if bucket == 'survey':
                        survey_s += d / speed
                    else:
                        corridor_s += d / speed
                sp = pt
        if sp:
            prev = sp

    for it in m['items']:
        if it.get('type') == 'SimpleItem' and it.get('command') == 16:
            pt = (it['params'][4], it['params'][5])
            if prev:
                transit_s += _haversine(prev, pt) / cruise
            prev = pt
        elif it.get('complexItemType') == 'survey':
            ts = it['TransectStyleComplexItem']
            inner = ts.get('Items', [])
            inner_wps = [s for s in inner if s.get('command') == 16]
            if inner_wps:
                walk(inner, ts.get('FlightSpeed', cruise), 'survey')
            else:
                # Fallback: analytic survey time
                survey_s += _analytic_survey_seconds(it, ts.get('FlightSpeed', cruise))
        elif it.get('complexItemType') == 'CorridorScan':
            ts = it['TransectStyleComplexItem']
            walk(ts.get('Items', []), ts.get('FlightSpeed', cruise), 'corridor')

    return survey_s / 60, corridor_s / 60, transit_s / 60


def estimate(plan_path: str):
    s, c, t = split_minutes(plan_path)
    naive = s + c + t
    amc = K_SURVEY * s + K_CORRIDOR * c + K_TRANSIT * t
    return dict(survey=s, corridor=c, transit=t, naive=naive, amc=amc)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    paths = []
    for a in sys.argv[1:]:
        paths.extend(glob.glob(a) or [a])
    print(f"{'Plan':<35} {'srv':>6} {'corr':>6} {'tran':>6} {'naive':>6} {'AMC est':>8}")
    print('-' * 72)
    for p in paths:
        try:
            r = estimate(p)
        except Exception as e:
            print(f"{os.path.basename(p):<35} ERROR: {e}")
            continue
        print(f"{os.path.basename(p):<35} {r['survey']:>6.1f} {r['corridor']:>6.1f} "
              f"{r['transit']:>6.1f} {r['naive']:>6.1f} {r['amc']:>7.1f}m")


if __name__ == '__main__':
    main()
