"""Trade-off sweep for a camera plan set: rank options against constraints before building.

    py tradeoff_sweep.py [out.csv]      -> ranked table on stdout + CSV (default tradeoff_sweep.csv)

Edit SITE, CONSTRAINTS, SWEEP and ORBITS below. Every row is laid out with camera_plan_set.py's own
functions (camera settings, grid lines, battery split, terrain-following waypoints, time model), so a
chosen row rebuilds to the same photos/batteries: pass row_config(SITE, row) to build_camera_plan_set.
Function API: sweep(site_cfg, sweep_values, constraints) -> ranked rows; evaluate(...); row_config(...).
"""
import csv, functools, itertools, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import camera_plan_set as cps  # noqa: E402

FIX = os.path.join(HERE, "..", "tests", "fixtures")
_toole = json.load(open(os.path.join(FIX, "toole.json")))
# ---- site (limits, HOME, DEM, payload) ----
SITE = dict(name="TooleCH", limits=_toole["limits"], home=_toole["home"],
            dem=os.path.join(FIX, "toole_dtm_v4.tif"), payload="lr1_24mm")
# ---- constraints (a row fails if any is violated) ----
CONSTRAINTS = dict(
    max_gsd_mm=9.6,         # nadir GSD (200 ft AGL or better)
    max_blur_px=1.0,        # nadir
    min_fwd_pct=75.0,       # nadir forward overlap (fixed 2 s trigger)
    min_side_pct=70.0,      # nadir side overlap
    min_obl_side_pct=55.0,  # oblique side overlap per look direction, near edge (builder model; chosen row = 57.7)
    max_batteries=4,        # grids + ORBITS
    require_obliques=True,
)
# ---- sweep values ----
SWEEP = dict(
    agl_ft=[150, 175, 200],
    shutter=[1000, 1250, 1600],          # 1/x s
    blur_px=[0.5, 0.75, 1.0],            # blur limit
    speed_margin=[0.15],
    side_pct=[70, 80],
    oblique=["none", "normal", "half"],  # half = oblique lines at half the nadir spacing
    runout_m=[35, 70],                   # oblique run-out
)
# ---- fixed add-on for the orbit flights (not swept; set batteries=0 to drop) ----
ORBITS = dict(batteries=1, minutes=7.5, photos=140)


@functools.lru_cache(maxsize=None)
def _site(limits, home, dem):
    return cps.Site([list(p) for p in limits], list(home), cps.Dem(dem))


def _payload(key):
    t = json.load(open(os.path.join(HERE, "payloads.json")))
    return t["payloads"][key], t["time_model"]


def row_config(site_cfg, row):
    """Builder config for a sweep row (add out_dir before building)."""
    pats = ["nadir"] + (["oblA", "oblB"] if row["oblique"] != "none" else [])
    return dict(site_cfg, agl_ft=row["agl_ft"], shutter=row["shutter"], blur_px=row["blur_px_limit"],
                speed_margin=row["speed_margin"], side_pct=row["side_pct"], patterns=pats,
                oblique_spacing=row["oblique"] if row["oblique"] != "none" else "normal",
                runout_m=row["runout_m"] if row["oblique"] != "none" else 35.0)


def _fails(r, c):
    checks = (("gsd", r["gsd_mm"] > c["max_gsd_mm"]), ("blur", r["blur_px"] > c["max_blur_px"]),
              ("fwd", r["fwd_pct"] < c["min_fwd_pct"]), ("side", r["side_pct"] < c["min_side_pct"]),
              ("obl_side", r["obl_side_pct"] != "" and r["obl_side_pct"] < c["min_obl_side_pct"]),
              ("batteries", r["batteries"] > c["max_batteries"]),
              ("no_obliques", c["require_obliques"] and r["oblique"] == "none"))
    return " ".join(k for k, bad in checks if bad)


def evaluate(site_cfg, agl_ft, shutter, blur_px, speed_margin, side_pct, oblique, runout_m, constraints,
             orbits=ORBITS):
    """One sweep row, laid out exactly as build_camera_plan_set would (no files written)."""
    pl, tm = _payload(site_cfg["payload"])
    site = _site(tuple(map(tuple, site_cfg["limits"])), tuple(site_cfg["home"]), site_cfg["dem"])
    row = dict(agl_ft=agl_ft, shutter=shutter, blur_px_limit=blur_px, speed_margin=speed_margin, side_pct=side_pct,
               oblique=oblique, runout_m=runout_m if oblique != "none" else "")
    cfg = row_config(site_cfg, row)
    cam = cps.camera_settings(pl, cfg)
    limit = pl["flight_limit_min"]
    photos, minutes, n = {"nadir": 0, "oblA": 0, "oblB": 0}, 0.0, 0
    for p in cfg["patterns"]:
        for s in cps.PATTERNS[p](site, cam, cfg, limit, tm):
            c = cps.oblique_cam(cam, cfg) if p != "nadir" else cam
            nav, _, ph, nt = cps.line_flight(site, s["lines"], s["u"], s["v"], c["agl_m"], c["trigger_m"], s["k0"])
            photos[p] += ph
            minutes += cps.flight_minutes(nav, cam["speed_mps"], nt, tm)[0]
            n += 1
    obl_side = (cps.oblique_overlap(pl, cps.oblique_cam(cam, cfg), cfg.get("oblique_pitch", -45))["side_pct_near_edge"]
                if oblique != "none" else "")
    total_ph = sum(photos.values()) + orbits["photos"]
    row.update(gsd_mm=round(cam["gsd_m"] * 1000, 2), blur_px=round(cam["blur_px"], 2),
               fwd_pct=round(cam["forward_pct"], 1), obl_side_pct=obl_side, speed_mps=cam["speed_mps"],
               speed_mph=round(cam["speed_mps"] * 2.23694, 1), grid_batteries=n,
               batteries=n + orbits["batteries"], minutes=round(minutes + orbits["minutes"]),
               photos=total_ph, photos_nadir=photos["nadir"], photos_oblA=photos["oblA"], photos_oblB=photos["oblB"],
               gb=round(total_ph * pl.get("mb_per_photo", 0) / 1000, 1))
    row["fails"] = _fails(row, constraints)
    return row


def sweep(site_cfg, sweep_values, constraints, orbits=ORBITS):
    """All combinations, ranked: passing first, then fewest batteries, best GSD, most side overlap, fewest minutes."""
    keys = ("agl_ft", "shutter", "blur_px", "speed_margin", "side_pct", "oblique", "runout_m")
    rows, seen = [], set()
    orig = cps.densify
    cps.densify = functools.lru_cache(maxsize=None)(orig)   # same function, memoised (repeat legs across splits)
    try:
        for combo in itertools.product(*(sweep_values[k] for k in keys)):
            a = dict(zip(keys, combo))
            if a["oblique"] == "none":
                a["runout_m"] = sweep_values["runout_m"][0]
            sig = tuple(a.values())
            if sig in seen:
                continue
            seen.add(sig)
            rows.append(evaluate(site_cfg, constraints=constraints, orbits=orbits, **a))
    finally:
        cps.densify = orig
    rows.sort(key=lambda r: (bool(r["fails"]), r["batteries"], r["gsd_mm"], -r["side_pct"], r["minutes"]))
    return rows


def write_csv(rows, path):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


COLS = ["agl_ft", "shutter", "blur_px_limit", "side_pct", "oblique", "runout_m", "gsd_mm", "speed_mps", "speed_mph",
        "blur_px", "fwd_pct", "obl_side_pct", "batteries", "minutes", "photos", "gb", "fails"]


def print_table(rows, n=25):
    t = [[("1/%d" % r[c]) if c == "shutter" else str(r[c]) for c in COLS] for r in rows[:n]]
    w = [max(len(c), *(len(x[i]) for x in t)) for i, c in enumerate(COLS)]
    print("  ".join(c.ljust(w[i]) for i, c in enumerate(COLS)))
    for x in t:
        print("  ".join(v.ljust(w[i]) for i, v in enumerate(x)))


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "tradeoff_sweep.csv"
    rows = sweep(SITE, SWEEP, CONSTRAINTS)
    write_csv(rows, out)
    print_table(rows)
    print(f"{sum(not r['fails'] for r in rows)} of {len(rows)} rows pass. Full table: {out}")
