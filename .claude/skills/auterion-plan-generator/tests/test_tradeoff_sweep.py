"""Seam test: the trade-off sweep on the Toole fixture with RH's constraints.
   py tests/test_tradeoff_sweep.py
"""
import json, os, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import tradeoff_sweep as ts  # noqa: E402
import camera_plan_set as cps  # noqa: E402

FIX = os.path.join(HERE, "fixtures")
TOOLE = json.load(open(os.path.join(FIX, "toole.json")))
BASE = dict(name="TooleCH", limits=TOOLE["limits"], home=TOOLE["home"], dem=os.path.join(FIX, "toole_dtm_v4.tif"),
            payload="lr1_24mm")
RH = dict(max_gsd_mm=9.6, max_blur_px=1.0, min_fwd_pct=75.0, min_side_pct=70.0, min_obl_side_pct=55.0,
          max_batteries=4, require_obliques=True)
SWEEP = dict(agl_ft=[200], shutter=[1000], blur_px=[0.75, 1.0], speed_margin=[0.15], side_pct=[80],
             oblique=["normal"], runout_m=[35])
FAILS = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  ({detail})" if detail else ""))
    if not ok: FAILS.append(name)


def test_sweep():
    rows = ts.sweep(BASE, SWEEP, RH)
    pick = [r for r in rows if r["blur_px_limit"] == 0.75]
    one = [r for r in rows if r["blur_px_limit"] == 1.0]
    check("chosen row present", len(pick) == 1, len(pick))
    r = pick[0]
    check("chosen row passes", r["fails"] == "", r)
    check("1 px row fails on fwd", one and "fwd" in one[0]["fails"].split(), one and one[0]["fails"])
    check("ranked: passing first", rows[0]["fails"] == "")
    for k in ("batteries", "minutes", "photos", "gb", "speed_mps", "speed_mph"):
        check(f"row has {k}", k in r)
    # rebuild the chosen row with the builder
    out = tempfile.mkdtemp()
    rep, rc = cps.build_camera_plan_set(dict(ts.row_config(BASE, r), out_dir=out))
    check("rebuild exit 0", rc == 0, rc)
    for pat in ("nadir", "oblA", "oblB"):
        b = sum(f["photos"] for f in rep["flights"] if f["pattern"] == pat)
        check(f"{pat} photos sweep {r['photos_' + pat]} vs build {b} +-2", abs(b - r["photos_" + pat]) <= 2)
    check("batteries match", rep["batteries"] == r["grid_batteries"], (rep["batteries"], r["grid_batteries"]))


def test_csv_and_table():
    rows = [dict(a=1, fails=""), dict(a=2, fails="fwd")]
    p = os.path.join(tempfile.mkdtemp(), "s.csv")
    ts.write_csv(rows, p)
    check("csv written", open(p).read().splitlines()[0] == "a,fails")


if __name__ == "__main__":
    test_csv_and_table(); test_sweep()
    print("ALL PASS" if not FAILS else f"{len(FAILS)} FAIL"); sys.exit(1 if FAILS else 0)
