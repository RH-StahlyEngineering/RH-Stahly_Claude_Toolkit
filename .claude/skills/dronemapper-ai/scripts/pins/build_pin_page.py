"""Build the pin-review page (an Artifact) from one or more jobs' refined.json files.

Run: python -I build_pin_page.py --out pins.html --title "SB536 Target Pins" \
       --job "mcd|McDonald CR (Flight 106)|C:\\metashape-root\\intake\\<job>|refined.json" [--job ...]

Embeds a 96x96 crop around every candidate pin (pick and saddle fit) into
pin_page_template.html. Publish the result with the Artifact tool and
capabilities {"db": {}, "user": {}}. RH places each junction there; positions land in the
artifact's db collection "pins" (doc id <tag>_<target>_<photo>: u, v, status set|skip, note),
read back with ArtifactData action "list", collection "pins".
"""
import argparse, base64, io, json, os
from PIL import Image

ap = argparse.ArgumentParser()
ap.add_argument("--out", required=True)
ap.add_argument("--title", default="Target Pins")
ap.add_argument("--job", action="append", required=True, help="tag|display name|intake dir|refined.json")
ap.add_argument("--only", help="flag.py output: include only pins with reasons, showing them")
a = ap.parse_args()
flags = json.load(open(a.only, encoding="utf-8")) if a.only else None
H = 48
items = []
for spec in a.job:
    tag, name, intake, refp = spec.split("|")
    ref = json.load(open(refp, encoding="utf-8"))
    for t in sorted(ref):
        for lab in sorted(ref[t]):
            r = ref[t][lab]
            reasons = (flags or {}).get(f"{tag}_{t}_{lab}", {}).get("reasons", [])
            if flags is not None and not reasons:
                continue
            cu, cv = (r["pick"][0] + r["saddle"][0]) / 2, (r["pick"][1] + r["saddle"][1]) / 2
            L, T = int(round(cu)) - H, int(round(cv)) - H
            buf = io.BytesIO()
            Image.open(os.path.join(intake, lab + ".jpg")).convert("RGB").crop((L, T, L + 2 * H, T + 2 * H)).save(buf, "PNG", optimize=True)
            items.append({"id": f"{tag}_{t}_{lab}", "job": tag, "jobName": name, "target": t, "photo": lab,
                          "left": L, "top": T, "size": 2 * H, "pick": r["pick"], "fit": r["saddle"], "fitOk": bool(r["ok"]),
                          "reasons": reasons,
                          "score": 99.0 if not r["ok"] else round(((r["pick"][0] - r["saddle"][0]) ** 2 + (r["pick"][1] - r["saddle"][1]) ** 2) ** 0.5, 2),
                          "img": "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()})
items.sort(key=lambda x: -x["score"])  # most uncertain first
tpl = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "pin_page_template.html"), encoding="utf-8").read()
html = tpl.replace("/*PINS*/", "const PINS = " + json.dumps(items) + ";").replace("SB536 Target Pins", a.title)
open(a.out, "w", encoding="utf-8").write(html)
print(len(items), "crops ->", a.out)
