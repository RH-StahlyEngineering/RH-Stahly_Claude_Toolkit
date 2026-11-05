"""
Regression for photo_overlap.py against closed-form photogrammetry:
  flat ground : forward = 1 - B/G_along, side = 1 - W/G_across, GSD = H*pitch/f
  cross-slope : worst-position endlap at the uphill edge, h_e = AGL/(1 + s*tan_ac),
                endlap = 1 - B/(2*h_e*tan_al)
  seam        : two flights whose facing lines are 70 m apart -> seam sidelap 1 - 70/G_across
  rate limit  : a 5 m cmd-206 trigger at 8 m/s (0.625 s) is thinned to 1 image/s (8 m)
  python test_photo_overlap.py   -> PASS/FAIL per check, exit 1 on any FAIL
"""
import json, math, os, sys, tempfile, types
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import photo_overlap as P

LAT0, LON0, GROUND, AGL, SPACING, TRIG, SPEED = 47.0, -108.3, 900.0, 50.0, 50.0, 13.88, 8.0
SW, SH, F, PXW = 23.5, 15.6, 16.0, 6000
TAN_AC, TAN_AL = SW / 2 / F, SH / 2 / F


class PlaneDem:
    """z = GROUND + slope * y (y = metres north of the frame origin)."""
    def __init__(self, slope=0.0):
        self.s = slope
        self.m = {"tif_path": "synthetic"}

    def at_xy(self, x, y):
        return GROUND + self.s * np.asarray(y, float) + 0 * np.asarray(x, float)


def make_plan(n_lines=4, length=400.0, angle=90.0, offsets=None, slope=0.0, trig=TRIG, spacing=SPACING, along_shift=0.0):
    fr = P.Frame(LAT0, LON0)
    a = math.radians(angle); ux, uy = math.sin(a), math.cos(a); px, py = math.cos(a), -math.sin(a)
    offs = offsets if offsets is not None else [(k - (n_lines - 1) / 2) * spacing for k in range(n_lines)]
    items = []

    def wp(x, y):
        lat, lon = fr.ll(x, y)
        items.append({"command": 16, "frame": 0, "params": [0, 0, 0, None, float(lat), float(lon),
                                                             GROUND + slope * y + AGL]})
    for k, o in enumerate(offs):
        s0, s1 = (-length / 2 + along_shift, length / 2 + along_shift) if k % 2 == 0 else (length / 2 + along_shift, -length / 2 + along_shift)
        wp(o * px + s0 * ux, o * py + s0 * uy)
        items.append({"command": 206, "frame": 2, "params": [trig, 0, 1, 0, 0, 0, 0]})
        wp(o * px + s1 * ux, o * py + s1 * uy)
        items.append({"command": 206, "frame": 2, "params": [0, 0, 1, 0, 0, 0, 0]})
    lo, hi = min(offs) - 30, max(offs) + 30
    corners = [(-length / 2 - 30 + along_shift, lo), (length / 2 + 30 + along_shift, lo), (length / 2 + 30 + along_shift, hi), (-length / 2 - 30 + along_shift, hi)]
    poly = [list(map(float, fr.ll(c[1] * px + c[0] * ux, c[1] * py + c[0] * uy))) for c in corners]
    plan = {"fileType": "Plan", "mission": {"plannedHomePosition": [LAT0, LON0, GROUND], "items": [
        {"command": 178, "params": [1, SPEED, -1, 0, 0, 0, 0]},
        {"type": "ComplexItem", "complexItemType": "survey", "angle": angle, "polygon": poly,
         "TransectStyleComplexItem": {"Items": items, "FlightSpeed": SPEED, "Refly90Degrees": False,
                                      "CameraCalc": {"DistanceToSurface": AGL, "AdjustedFootprintSide": spacing}}}]}}
    fd, path = tempfile.mkstemp(suffix=".plan"); os.close(fd)
    json.dump(plan, open(path, "w"))
    return path


def run(paths, mode, orientation="across", slope=0.0, hull_target=False):
    pls = [P.load_plan(p) for p in paths]
    fr = P.Frame(LAT0, LON0)
    args = types.SimpleNamespace(orientation=orientation, shutter=1000.0)
    area = P.target_area(pls, None, fr)
    if hull_target:                       # stands in for --target <Exhibit A KML> spanning both tiles
        area = area.convex_hull
    return P.analyse("t", pls, mode, args, PlaneDem(slope), fr, P.CAMERAS["a6k-lite"], area)


def check(name, got, want, tol):
    ok = got is not None and abs(got - want) <= tol
    print(f"{'PASS' if ok else 'FAIL'}  {name}: got {got if got is None else round(got, 4)} want {want:.4f} (tol {tol})")
    return ok


def main():
    G_al, G_ac = 2 * AGL * TAN_AL, 2 * AGL * TAN_AC
    ok = True
    for ang in (90.0, 37.0):
        c = run([make_plan(angle=ang)], "plan")["combined"]
        ok &= check(f"flat forward worst (angle {ang})", c["forward"]["min"], 1 - TRIG / G_al, 0.005)
        ok &= check(f"flat forward area (angle {ang})", c["forward_area"]["median"], 1 - TRIG / G_al, 0.005)
        ok &= check(f"flat side median (angle {ang})", c["side"]["median"], 1 - SPACING / G_ac, 0.005)
        ok &= check(f"flat side min (angle {ang})", c["side"]["min"], 1 - SPACING / G_ac, 0.01)
    r = run([make_plan()], "plan")
    ok &= check("nadir GSD cm", r["gsd_nadir_cm"]["median"], 100 * AGL * (SW / PXW) / F, 0.002)
    ok &= check("forward, 1 s payload timer", run([make_plan()], "time:1")["combined"]["forward"]["median"],
                1 - SPEED / G_al, 0.005)
    c = run([make_plan()], "plan", orientation="along")["combined"]
    ok &= check("side, long side ALONG-track (negative = gap)", c["side"]["median"], 1 - SPACING / (2 * AGL * TAN_AL), 0.005)
    for s in (0.10, 0.20):
        c = run([make_plan(slope=s)], "plan", slope=s)["combined"]
        he = AGL / (1 + s * TAN_AC)
        ok &= check(f"cross-slope {s:.0%}: worst-position endlap (uphill edge)", c["forward"]["min"],
                    1 - TRIG / (2 * he * TAN_AL), 0.005)
    a = make_plan(offsets=[-125.0, -75.0, -25.0])
    b = make_plan(offsets=[45.0, 95.0, 145.0])
    c = run([a, b], "plan")["combined"]
    ok &= check("seam sidelap (lines 70 m apart across flights)", c["side_seams"]["median"], 1 - 70.0 / G_ac, 0.01)
    ok &= check("in-flight sidelap still 50 m", c["side"]["max"], 1 - SPACING / G_ac, 0.01)
    r = run([make_plan(trig=5.0)], "plan")
    ok &= check("rate limit: 5 m trigger thinned to 8 m", r["combined"]["forward"]["median"], 1 - SPEED / G_al, 0.005)
    ok &= check("rate limit flagged", float(len(r["rate_flags"])), 1.0, 0)
    # wide seam (82 m at 50 m spacing): must be reported as a GAP, not skipped as a block edge
    c = run([make_plan(offsets=[-125.0, -75.0, -25.0]), make_plan(offsets=[57.0, 107.0, 157.0])], "plan", hull_target=True)["combined"]
    ok &= check("82 m seam reported as gap", c["side_seams"]["min"], 1 - 82.0 / G_ac, 0.01)
    # photogrammetry spacing 29.4 m with a 50 m seam: true sidelap 1 - 50/G_ac
    c = run([make_plan(offsets=[-88.8, -59.4, -30.0], spacing=29.4),
             make_plan(offsets=[20.0, 49.4, 78.8], spacing=29.4)], "plan", hull_target=True)["combined"]
    ok &= check("50 m seam at 29.4 m spacing", c["side_seams"]["min"], 1 - 50.0 / G_ac, 0.01)
    # tiles re-angled 1 deg apart are ONE grid and their seam gap reaches the report
    r = run([make_plan(angle=90.0, offsets=[-125.0, -75.0, -25.0]), make_plan(angle=91.0, offsets=[55.0, 105.0, 155.0])], "plan", hull_target=True)
    ok &= check("90/91 deg tiles clustered into one direction", float(len(r["directions"])), 1.0, 0)
    ok &= check("90/91 deg seam gap visible (min < 0)", min(r["combined"]["side_seams"]["min"], 0.0), r["combined"]["side_seams"]["min"], 1e-9) and r["combined"]["side_seams"]["min"] < 0
    # staircase: second flight end-to-end and laterally offset on a 15 % slope -> no false GAP
    c = run([make_plan(slope=0.15), make_plan(slope=0.15, offsets=[-50.0, 0.0, 50.0, 100.0], along_shift=400.0)], "plan", slope=0.15)["combined"]
    ok &= check("staircase seam: no false gap (side min >= 0)", max(c["side"]["min"], 0.0), c["side"]["min"], 1e-9) and c["side"]["min"] >= 0
    print("ALL PASS" if ok else "FAILURES")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
