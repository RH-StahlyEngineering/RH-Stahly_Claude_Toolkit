"""Seam test (ticket 05): entry point on Toole writes into temp dirs standing in for the AMC Missions
and project Flight_Plans folders.   py tests/test_outputs_home.py
"""
import csv, json, math, os, re, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "..", "scripts", "camera_plan_set.py")
FIX = os.path.join(HERE, "fixtures")
TOOLE = json.load(open(os.path.join(FIX, "toole.json")))
PREV_HOME = (48.5044920, -111.8592034)   # previous Toole HOME, courthouse west lot
FAILS = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  ({detail})" if detail else ""))
    if not ok: FAILS.append(name)


def m_between(a, b):
    return math.hypot((a[0] - b[0]) * 111320, (a[1] - b[1]) * 111320 * math.cos(math.radians(a[0])))


def run(root, missions, fplans, reason=None, home=None):
    cfg = dict(name="TooleCH", limits=TOOLE["limits"], dem=os.path.join(FIX, "toole_dtm_v4.tif"),
               lidar=os.path.join(FIX, "toole_lidar_2020.npz"), payload="lr1_24mm", agl_ft=200, shutter=1000,
               blur_px=0.75, patterns=["nadir"], out_dir=os.path.join(root, "work"), save_to=[missions, fplans])
    if home: cfg["home"] = home
    if reason: cfg["supersede_reason"] = reason
    p = os.path.join(root, "cfg.json"); json.dump(cfg, open(p, "w"))
    r = subprocess.run([sys.executable, SCRIPT, p], capture_output=True, text=True)
    if r.returncode: print(r.stdout, r.stderr)
    return r.returncode, json.load(open(os.path.join(cfg["out_dir"], "TooleCH_report.json")))


def test_outputs_and_home():
    root = tempfile.mkdtemp()
    missions = os.path.join(root, "Missions")
    fplans = os.path.join(root, "proj", "3-To_Field", "Flight_Plans")   # missing: must be created
    os.makedirs(missions)
    other = os.path.join(missions, "OtherJob_nadir90.plan"); open(other, "w").write("x")
    other2 = os.path.join(missions, "TooleCHX_keep.plan"); open(other2, "w").write("y")
    rc, rep = run(root, missions, fplans)
    check("first run exit 0", rc == 0, rc)
    h = rep["home"]
    check("HOME suggested + needs confirmation", h["source"] == "suggested" and h["needs_confirmation"] is True, h)
    d = m_between((h["lat"], h["lon"]), PREV_HOME)
    check("suggested HOME within 40 m of previous (west lot)", d <= 40, f"{d:.1f} m, {h}")
    check("HOME clearance >= 10 m reported", h["clearance_m"] >= 10, h.get("clearance_m"))
    check("HOME flat (slope <= 5%)", h["slope_pct"] <= 5, h.get("slope_pct"))
    plans = sorted(f["file"] for f in rep["flights"])
    for d_ in (missions, fplans):
        have = sorted(f for f in os.listdir(d_) if f.startswith("TooleCH_") and f.endswith(".plan"))
        check(f"plans saved in {os.path.basename(d_)}", have == plans, have)
        for ext in ("kml", "csv", "md"):
            check(f"{os.path.basename(d_)} has TooleCH_flights.{ext}", os.path.exists(os.path.join(d_, f"TooleCH_flights.{ext}")))
    # table matches plans
    rows = list(csv.DictReader(open(os.path.join(fplans, "TooleCH_flights.csv"))))
    check("CSV one row per plan", sorted(r["plan"] for r in rows) == [p[:-5] for p in plans], [r["plan"] for r in rows])
    for r in rows:
        f = next(x for x in rep["flights"] if x["file"] == r["plan"] + ".plan")
        check(f"CSV {r['plan']} photos/minutes match", int(r["photos"]) == f["photos"] and float(r["minutes"]) == f["minutes"])
    md = open(os.path.join(fplans, "TooleCH_flights.md")).read()
    check("MD lists every plan + HOME confirm flag", all(p[:-5] in md for p in plans) and "CONFIRM" in md.upper())
    # KML matches plans
    kml = open(os.path.join(missions, "TooleCH_flights.kml")).read()
    for p in plans:
        plan = json.load(open(os.path.join(missions, p)))
        wps = [i["params"][4:7] for i in plan["mission"]["items"] if i["command"] == 16]
        m = re.search(r"<name>%s</name>.*?<coordinates>(.*?)</coordinates>" % re.escape(p[:-5]), kml, re.S)
        pts = [tuple(map(float, c.split(","))) for c in m.group(1).split()] if m else []
        ok = len(pts) == len(wps) and all(abs(a[0] - w[1]) < 1e-7 and abs(a[1] - w[0]) < 1e-7 and abs(a[2] - w[2]) < 0.01
                                          for a, w in zip(pts, wps))
        check(f"KML path {p} = plan waypoints", ok, f"{len(pts)} vs {len(wps)}")
    check("KML has HOME + limits", "HOME" in kml and "Survey limits" in kml)
    # rerun -> previous set moved to superseded, nothing deleted
    before = {f: open(os.path.join(missions, f), "rb").read() for f in os.listdir(missions) if f.startswith("TooleCH_")}
    rc, rep2 = run(root, missions, fplans, reason="speed change")
    check("rerun exit 0", rc == 0, rc)
    for d_ in (missions, fplans):
        sup = [s for s in os.listdir(d_) if s.startswith("superseded_")]
        check(f"{os.path.basename(d_)}: one superseded_<date>_<reason> dir",
              len(sup) == 1 and re.fullmatch(r"superseded_\d{8}_speed_change", sup[0]), sup)
        if d_ is missions and sup:
            moved = {f: open(os.path.join(d_, sup[0], f), "rb").read() for f in os.listdir(os.path.join(d_, sup[0]))}
            check("superseded holds whole previous set byte-identical", moved == before, sorted(moved))
    check("unrelated files untouched", open(other).read() == "x" and open(other2).read() == "y"
          and sorted(os.listdir(missions)) == sorted([os.path.basename(other), os.path.basename(other2)] + list(before)
                                                      + [s for s in os.listdir(missions) if s.startswith("superseded_")]))
    # given HOME -> used as-is, not flagged
    rc, rep3 = run(tempfile.mkdtemp(), os.path.join(root, "M2"), os.path.join(root, "F2"), home=TOOLE["home"])
    check("given HOME used, not flagged", rep3["home"]["source"] == "given" and not rep3["home"]["needs_confirmation"])


if __name__ == "__main__":
    test_outputs_and_home()
    print("ALL PASS" if not FAILS else f"{len(FAILS)} FAIL"); sys.exit(1 if FAILS else 0)
