"""Seam test: the "build a camera plan set" entry point on the Toole fixture.
Checks only the JSON report and the written .plan files.   py tests/test_camera_plan_set.py
"""
import json, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "..", "scripts", "camera_plan_set.py")
FIX = os.path.join(HERE, "fixtures")
TOOLE = json.load(open(os.path.join(FIX, "toole.json")))
FAILS = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  ({detail})" if detail else ""))
    if not ok: FAILS.append(name)


def run(limits, home, out, patterns=("nadir",)):
    cfg = dict(name="TooleCH", limits=limits, home=home, dem=os.path.join(FIX, "toole_dtm_v4.tif"),
               payload="lr1_24mm", agl_ft=200, shutter=1000, blur_px=0.75, speed_margin=0.15,
               side_pct=80, patterns=list(patterns), out_dir=out)
    p = os.path.join(out, "cfg.json"); json.dump(cfg, open(p, "w"))
    r = subprocess.run([sys.executable, SCRIPT, p], capture_output=True, text=True)
    rep = json.load(open(os.path.join(out, "TooleCH_report.json")))
    return r.returncode, rep


def test_toole_nadir():
    out = tempfile.mkdtemp()
    rc, rep = run(TOOLE["limits"], TOOLE["home"], out)
    check("exit 0", rc == 0, rc)
    nad = [f for f in rep["flights"] if f["pattern"] == "nadir"]
    photos = sum(f["photos"] for f in nad)
    check("nadir photos 188 +-2", abs(photos - 188) <= 2, photos)
    check("each flight under 26 min", all(f["minutes"] < 26 for f in nad), [f["minutes"] for f in nad])
    check("terrain tracking <= 1 m", all(f["terrain_tracking_max_err_m"] <= 1.0 for f in nad),
          [f["terrain_tracking_max_err_m"] for f in nad])
    for f in nad:
        raw = open(os.path.join(out, f["file"]), "rb").read()
        plan = json.loads(raw); it = plan["mission"]["items"]
        check(f"{f['file']}: minified LF-only", b"\r" not in raw and b"\n" not in raw.strip() and b": " not in raw)
        check(f"{f['file']}: one cmd 178", sum(i["command"] == 178 for i in it) == 1)
        p205 = [i["params"][0] for i in it if i["command"] == 205]
        check(f"{f['file']}: cmd 205 matches name pitch", p205 == [-90] and "nadir90" in f["file"], p205)
        check(f"{f['file']}: starts 530,178,205", [i["command"] for i in it[:3]] == [530, 178, 205])
        w = [i for i in it if i["command"] == 16]
        h = TOOLE["home"]
        check(f"{f['file']}: HOME first and last",
              all(abs(x["params"][4] - h[0]) < 1e-7 and abs(x["params"][5] - h[1]) < 1e-7 for x in (w[0], w[-1])))
        c206 = [i["params"][0] for i in it if i["command"] == 206]
        check(f"{f['file']}: 206 on/off pairs", len(c206) % 2 == 0 and all(c206[k] > 0 and c206[k + 1] == 0 for k in range(0, len(c206), 2)))
        check(f"{f['file']}: no ComplexItem", all(i["type"] == "SimpleItem" for i in it))
    for k in ("gsd_mm", "blur_px", "forward_overlap_pct", "side_overlap_pct", "speed_mps", "dem_extent"):
        check(f"report has {k}", k in rep, k)
    check("dem extent ok", rep["dem_extent"]["ok"] is True)


def test_refuses_outside_dem():
    out = tempfile.mkdtemp()
    shifted = [[lo + 0.004, la] for lo, la in TOOLE["limits"]]
    rc, rep = run(shifted, [TOOLE["home"][0], TOOLE["home"][1] + 0.004], out)
    check("refusal: nonzero exit", rc != 0, rc)
    check("refusal: status refused + reason", rep["status"] == "refused" and "DEM" in rep["reason"], rep.get("reason"))
    check("refusal: no plan written", not [f for f in os.listdir(out) if f.endswith(".plan")])
    out = tempfile.mkdtemp()
    rc, rep = run([[lo + 0.002, la] for lo, la in TOOLE["limits"]], TOOLE["home"], out)
    check("refusal (HOME inside, grid leaves DEM)", rc != 0 and rep["status"] == "refused"
          and rep["dem_extent"]["samples_outside"] > 0 and "DEM" in rep["reason"], rep.get("reason"))
    check("refusal: no plan written (grid case)", not [f for f in os.listdir(out) if f.endswith(".plan")])


def test_toole_oblique():
    out = tempfile.mkdtemp()
    rc, rep = run(TOOLE["limits"], TOOLE["home"], out, ("nadir", "oblA", "oblB"))
    check("oblique: exit 0", rc == 0, rc)
    for pat, ref in (("oblA", 198), ("oblB", 221)):
        fl = [f for f in rep["flights"] if f["pattern"] == pat]
        ph = sum(f["photos"] for f in fl)
        check(f"{pat} photos {ref} +-2", abs(ph - ref) <= 2, ph)
        check(f"{pat} each flight under 26 min", fl and all(f["minutes"] < 26 for f in fl), [f["minutes"] for f in fl])
        for f in fl:
            check(f"{f['file']}: pitch -45 in name", f["file"].startswith(f"TooleCH_{pat}45") and f["pitch_deg"] == -45)
            it = json.loads(open(os.path.join(out, f["file"]), "rb").read())["mission"]["items"]
            check(f"{f['file']}: cmd 205 -45", [i["params"][0] for i in it if i["command"] == 205] == [-45])
            check(f"{f['file']}: tracking misses reported", "terrain_tracking_misses" in f
                  and "min_clearance_above_dem_m" in f, f.get("terrain_tracking_misses"))
        ov = rep["overlap_by_look"][pat]
        check(f"{pat}: 2 look directions with fwd+side", len(ov) == 2 and all(
            0 < d["forward_pct"] < 100 and 0 < d["side_pct_near_edge"] < 100 for d in ov), ov)
    looks = {d["look_bearing_deg"] for p in ("oblA", "oblB") for d in rep["overlap_by_look"][p]}
    check("4 distinct look directions", len(looks) == 4, sorted(looks))
    check("run-out default 35 m", rep["runout_m"] == 35.0)


if __name__ == "__main__":
    test_toole_nadir(); test_refuses_outside_dem(); test_toole_oblique()
    print("ALL PASS" if not FAILS else f"{len(FAILS)} FAIL"); sys.exit(1 if FAILS else 0)
