"""Seam test: camera_plan_set entry point with a `building` and `viz3d` config on Toole.
Checks the report's wall check, the QA PNG, and the self-contained 3D HTML.   py tests/test_building_qa.py
"""
import json, os, re, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "..", "scripts", "camera_plan_set.py")
FIX = os.path.join(HERE, "fixtures")
TOOLE = json.load(open(os.path.join(FIX, "toole.json")))
CENTROID = [48.504522, -111.858807]
FAILS = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  ({detail})" if detail else ""))
    if not ok: FAILS.append(name)


def test_toole_walls_and_3d():
    out = tempfile.mkdtemp()
    cfg = dict(name="TooleCH", limits=TOOLE["limits"], home=TOOLE["home"], dem=os.path.join(FIX, "toole_dtm_v4.tif"),
               payload="lr1_24mm", agl_ft=200, shutter=1000, blur_px=0.75, speed_margin=0.15, side_pct=80,
               patterns=["nadir", "oblA", "oblB"], lidar=os.path.join(FIX, "toole_lidar_2020.npz"),
               building=dict(centroid=CENTROID), viz3d=True, out_dir=out,
               save_to=[os.path.join(out, "saved")])
    p = os.path.join(out, "cfg.json"); json.dump(cfg, open(p, "w"))
    r = subprocess.run([sys.executable, SCRIPT, p], capture_output=True, text=True)
    check("exit 0", r.returncode == 0, r.stderr[-800:])
    rep = json.load(open(os.path.join(out, "TooleCH_report.json")))
    wc = rep.get("wall_check", {})
    walls = wc.get("walls", [])
    check("4 walls reported", len(walls) == 4, [w.get("name") for w in walls])
    for w in walls:
        check(f"wall {w['name']} passes", w["pass"] and w["min_photos_per_point"] >= 3 and w["facing_oblique_photos"] >= 1,
              {k: w[k] for k in ("min_photos_per_point", "points_failing", "facing_oblique_photos")})
        check(f"wall {w['name']} lists directions", bool(w.get("directions")))
    check("roof passes", wc.get("roof", {}).get("pass") is True, wc.get("roof"))
    check("overall pass", wc.get("pass") is True)
    b = wc.get("building", {})
    check("box fitted, plausible size", 10 < min(b.get("dims_m", [0, 0])) and max(b.get("dims_m", [99, 99])) < 45, b.get("dims_m"))
    saved = os.path.join(out, "saved")
    for fn in ("TooleCH_walls_QA.png", "TooleCH_3D.html", "TooleCH_report.json"):
        check(f"save_to has {fn}", os.path.exists(os.path.join(saved, fn)))
    png = os.path.join(out, wc.get("qa_png", "missing"))
    check("QA PNG written", os.path.isfile(png) and open(png, "rb").read(4) == b"\x89PNG", png)
    v = rep.get("viz3d", {})
    html = os.path.join(out, v.get("file", "missing"))
    check("3D HTML written", os.path.isfile(html), html)
    if not os.path.isfile(html): return
    txt = open(html, encoding="utf-8").read()
    check("self-contained (no external script src)", not re.search(r'<script[^>]+src="http', txt) and "plotly" in txt.lower())
    mb = os.path.getsize(html) / 1e6
    check("HTML <= 15 MB", mb <= 15, f"{mb:.1f} MB")
    m = re.search(r'<script id="photo-counts" type="application/json">(.*?)</script>', txt, re.S)
    emb = json.loads(m.group(1)) if m else {}
    want = {f["file"]: f["photos"] for f in rep["flights"]}
    check("embedded photo counts match report", emb == want, (emb, want))


if __name__ == "__main__":
    test_toole_walls_and_3d()
    print("ALL PASS" if not FAILS else f"{len(FAILS)} FAIL"); sys.exit(1 if FAILS else 0)
