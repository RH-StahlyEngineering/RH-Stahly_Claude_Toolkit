"""Seam test: opt-in orbits through the camera_plan_set entry point (Toole fixture).
Checks only the JSON report and the written .plan files.   py tests/test_orbits.py
"""
import json, math, os, subprocess, sys, tempfile
import numpy as np
from pyproj import Transformer

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "..", "scripts", "camera_plan_set.py")
FIX = os.path.join(HERE, "fixtures")
TOOLE = json.load(open(os.path.join(FIX, "toole.json")))
LIDAR = os.path.join(FIX, "toole_lidar_2020.npz")
CH = [48.504522, -111.858807]   # courthouse centroid
FAILS = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  ({detail})" if detail else ""))
    if not ok: FAILS.append(name)


def run(out, **extra):
    cfg = dict(name="TooleCH", limits=TOOLE["limits"], home=TOOLE["home"], dem=os.path.join(FIX, "toole_dtm_v4.tif"),
               payload="lr1_24mm", agl_ft=200, shutter=1000, blur_px=0.75, out_dir=out, **extra)
    p = os.path.join(out, "cfg.json"); json.dump(cfg, open(p, "w"))
    r = subprocess.run([sys.executable, SCRIPT, p], capture_output=True, text=True)
    if r.returncode: print(r.stdout, r.stderr)
    return r.returncode, json.load(open(os.path.join(out, "TooleCH_report.json")))


def test_default_has_no_orbits():
    out = tempfile.mkdtemp()
    rc, rep = run(out)
    check("default: exit 0", rc == 0, rc)
    check("default: no orbit files", not [f for f in os.listdir(out) if "orbit" in f])
    check("default: no orbit flights", not [f for f in rep["flights"] if f["pattern"] == "orbit"])


def test_orbit_r40_raised():
    out = tempfile.mkdtemp()
    orb = dict(center=CH, radius_m=40, height_m=20, roi_height_m=6.5)
    rc, rep = run(out, patterns=["nadir", "orbit"], lidar=LIDAR, orbits=[orb])
    check("orbit: exit 0", rc == 0, rc)
    of = [f for f in rep["flights"] if f["pattern"] == "orbit"]
    check("orbit: one orbit flight", len(of) == 1, len(of))
    f = of[0]
    plan = json.load(open(os.path.join(out, f["file"])))
    it = plan["mission"]["items"]
    cmds = [i["command"] for i in it]
    i195, i197 = cmds.index(195), cmds.index(197)
    ring = [i for i in it[i195 + 1:i197] if i["command"] == 16]
    check("orbit: 195 before ring, 197 after", len(ring) >= 24, len(ring))
    check("orbit: no wp between 195 and first ring wp other than ring", cmds[i195 + 1:i197].count(16) == len(ring))
    roi = it[i195]["params"]
    fw = Transformer.from_crs(4326, 32612, always_xy=True)
    cx, cy = fw.transform(roi[5], roi[4])
    rs = [math.hypot(*np.subtract(fw.transform(w["params"][5], w["params"][4]), (cx, cy))) for w in ring]
    r = float(np.mean(rs)); dz = ring[0]["params"][6] - roi[6]
    want = -math.degrees(math.atan2(dz, r))
    p205 = [i["params"][0] for i in it if i["command"] == 205]
    check("orbit: radius ~40", abs(r - 40) < 1, round(r, 2))
    check("orbit: cmd 205 within 1 deg of atan(dz/r)", len(p205) == 1 and abs(p205[0] - want) <= 1, (p205, round(want, 1)))
    check("orbit: pitch in filename", f"p{abs(round(p205[0]))}" in f["file"], f["file"])
    # independent clearance check: lidar (non-noise) within 15 m of each ring wp
    d = np.load(LIDAR); keep = ~np.isin(d["cls"], (7, 18))
    lx, ly = fw.transform(d["lon"][keep], d["lat"][keep]); lz = d["z_m"][keep]
    worst = min(w["params"][6] - lz[np.hypot(lx - x, ly - y) <= 15].max()
                for w in ring for x, y in [fw.transform(w["params"][5], w["params"][4])])
    check("orbit: clearance >= 10 m over lidar within 15 m", worst >= 10 - 0.05, round(worst, 2))
    check("orbit: raise reported", f.get("raised_m", 0) > 0 and f["height_m"] > 20, (f.get("raised_m"), f.get("height_m")))


if __name__ == "__main__":
    test_default_has_no_orbits(); test_orbit_r40_raised()
    print("ALL PASS" if not FAILS else f"{len(FAILS)} FAIL"); sys.exit(1 if FAILS else 0)
