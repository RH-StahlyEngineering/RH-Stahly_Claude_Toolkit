"""Stahly manhole / inlet note sheets (.docx) from a job file.

    python mh_sheet.py job.json [--only 12260,12141] [--final]

job.json holds the job settings and one record per structure (schema: references/data_schema.md).
Page 1 = Stahly Manhole Note Template, revised (double-height blanks, fixed 3x3 pipe-box grid, plan
view at the template's circle size). Page 2 = field photo, turned to true north when its orientation
is known. With --final, any value never given prints NOT RECORDED; without it, it stays blank so a
draft shows what is still to collect.

Geometry rules (from RH, 2026-11):
- "top of pipe" is measured to the OUTSIDE top. invert = top + wall + ID; ID = invert - top - wall.
  Wall thickness comes from the field (per pipe or job default); never invented.
- Directions are field directions; field north -> true north by job.field_north_az (deg). Pipes,
  lid and photo all rotate by it. Plan view and photo are drawn to true north.
- Unknown sizes are drawn dashed and labelled "?" - never as a guessed size.
"""
import argparse, io, json, math, os, sys
from PIL import Image, ImageDraw, ImageFont
from docx import Document
from docx.shared import Twips, Pt, Emu, Inches
from docx.enum.table import WD_ROW_HEIGHT_RULE, WD_CELL_VERTICAL_ALIGNMENT as VA
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_LINE_SPACING
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from docx.text.paragraph import Paragraph

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "..", "assets", "stahly_manhole_template.docx")
ROW, CIRC = 540, 2428875               # blank-row height (twips); template circle size (EMU), fixed
IMG_H, IMG_W = 1200, 1500              # plan image px; extra width on the left for street labels
AZ = {"N": 0, "NNE": 22.5, "NE": 45, "ENE": 67.5, "E": 90, "ESE": 112.5, "SE": 135, "SSE": 157.5,
      "S": 180, "SSW": 202.5, "SW": 225, "WSW": 247.5, "W": 270, "WNW": 292.5, "NW": 315, "NNW": 337.5}
CELL = {"NW": (0, 0), "N": (0, 1), "NE": (0, 2), "W": (1, 0), "E": (1, 2), "SW": (2, 0), "S": (2, 1), "SE": (2, 2)}
COLW = (2900, 5000, 2900)
NR = "NOT RECORDED"
INLETS = ("curb_inlet", "grate_inlet", "combo_inlet")
KIND_LABEL = {"storm_mh": "Storm MH", "sanitary_mh": "Sanitary MH", "curb_inlet": "Curb inlet",
              "grate_inlet": "Grate inlet", "combo_inlet": "Combo inlet"}
FONT = "arialbd.ttf"

def fnum(v):
    try: return float(v)
    except (TypeError, ValueError): return None

def true_dir(d, fn):  # field direction -> nearest 16-point true direction (what the sheet shows)
    a = (AZ[d] + fn) % 360; return min(AZ, key=lambda k: abs((AZ[k] - a + 180) % 360 - 180))

def cell8(d):  # nearest of the 8 grid cells for a 16-point direction
    a = AZ[d]; return min(CELL, key=lambda k: abs((AZ[k] - a + 180) % 360 - 180))

# ---------- derived values ----------
def derive(s, job):
    """Fill computed invert / size from raw measurements; record how in s['_calc']."""
    calc = []
    if "kind" not in s:                                   # field-form record: kind from its description
        dsc = (s.get("desc") or "").lower()
        s["kind"] = next((k for k, v in KIND_LABEL.items() if v.lower() == dsc), "storm_mh")
    if s.get("dia_ft") is None and s["kind"] not in INLETS and fnum(str(s.get("size") or "").split(" ")[0]):
        s["dia_ft"] = fnum(str(s["size"]).split(" ")[0])
    if not s.get("lid") and s.get("ecc"): s["lid"] = s["ecc"]
    po = s.pop("photo_orient", None)
    if po and s.get("photo"): s["photo"].setdefault("orientation", "field_north_up" if po == "up in photo" else "unknown")
    for k in ("type", "grade", "cntr"):                   # form placeholders that mean "not given"
        if str(s.get(k) or "").strip().lower() in ("not recorded", ""): s[k] = None
    for p in s.get("pipes", []):
        for k in ("type", "drop", "size", "invert"):
            if str(p.get(k) or "").strip().lower() in ("not recorded", ""): p[k] = None
    for p in s.get("pipes", []):
        wall = fnum(p.get("wall", job.get("default_wall_ft")))
        inv, top, size = fnum(p.get("invert")), fnum(p.get("top")), fnum(p.get("size"))
        if p.get("slant") and inv is None:               # tape run at an angle: vertical = sqrt(s^2 - h^2)
            sl, h = fnum(p["slant"].get("s")), fnum(p["slant"].get("h"))
            if sl and h is not None and sl > h:
                inv = round(math.sqrt(sl * sl - h * h), 2); p["invert"] = f"{inv:.2f}"
                calc.append(f"{p.get('dir','OUT')} invert {inv:.2f} from slant {sl} / horizontal {h}")
        if inv is None and top is not None and size and wall is not None:
            inv = round(top + wall + size / 12, 2); p["invert"] = f"{inv:.2f}"; p["_inv_calc"] = True
            calc.append(f"{p.get('dir','OUT')} invert {inv:.2f} = top {top:.2f} + wall {wall:.2f} + {size:g} in ID")
        if size is None and inv is not None and top is not None and wall is not None:
            idin = (inv - top - wall) * 12; p["size"] = f"{round(idin):d}"; p["_size_calc"] = True
            calc.append(f"{p.get('dir','OUT')} size {idin:.1f} in = (invert {inv:.2f} - top {top:.2f} - wall {wall:.2f}) x 12")
    fn_ = float(job.get("field_north_az", 0))
    s["_calc"] = [c.replace(c.split(" ")[0], true_dir(c.split(" ")[0], fn_), 1) if c.split(" ")[0] in AZ else c for c in calc]
    return s

# ---------- plan view ----------
def plan_png(s, job):
    fn = float(job.get("field_north_az", 0))
    im = Image.new("RGBA", (IMG_W, IMG_H), (0, 0, 0, 0)); dr = ImageDraw.Draw(im)
    R = (IMG_H - 350) / 2; cx, cy = IMG_W - IMG_H / 2, IMG_H / 2
    f = ImageFont.truetype(FONT, 54); blk = (0, 0, 0, 255)
    inlet = s["kind"] in INLETS
    dia = fnum(s.get("dia_ft"))
    if inlet:                                         # rectangle, long side along field E-W, rotated to true north
        L_, W_ = fnum(s.get("box_l_ft")) or 0, fnum(s.get("box_w_ft")) or 0
        ftpx = (2 * R) / max(L_, W_, 1) if L_ and W_ else None
        hl, hw = (L_ * ftpx / 2, W_ * ftpx / 2) if ftpx else (R, R * 0.6)
        pts = [(-hl, -hw), (hl, -hw), (hl, hw), (-hl, hw)]
        a = math.radians(fn); ca, sa = math.cos(a), math.sin(a)
        poly = [(cx + x * ca - y * sa, cy + x * sa + y * ca) for x, y in pts]
        dr.polygon(poly, outline=blk, width=8)             # unknown box size: drawn at a generic shape, no callout
        Rw = max(hl, hw)
    else:
        dr.ellipse([cx - R, cy - R, cx + R, cy + R], outline=blk, width=8)
        lid = (s.get("lid") or "").split()
        if dia and lid and lid[0].lower().startswith("ecc") and len(lid) > 1 and lid[1] in AZ:
            r = R * 2.0 / dia; a = math.radians(AZ[lid[1]] + fn); off = R - r - 30
            lx, ly = cx + off * math.sin(a), cy - off * math.cos(a)
        elif dia: r = R * 2.0 / dia; lx, ly = cx, cy
        else: r = None
        if r:
            for k in range(0, 48, 2): dr.arc([lx - r, ly - r, lx + r, ly + r], 7.5 * k, 7.5 * (k + 1), fill=blk, width=7)
        Rw = R
    scale = (R / (dia * 6)) if (dia and not inlet) else (ftpx / 12 if inlet and ftpx else None)   # px per inch
    for p in s.get("pipes", []):
        if p.get("dir") not in AZ: continue
        a = math.radians(AZ[p["dir"]] + fn); sn, cs = math.sin(a), math.cos(a)
        size = fnum(p.get("size"))
        half = size / 2 * scale if (size and scale) else 0   # unknown size: centreline only
        proj = fnum(p.get("proj")) or 0
        ri = Rw - proj * scale if scale else Rw
        if inlet:                                     # distance from centre to the box edge along this pipe
            loc = math.radians(AZ[p["dir"]]); ux, uy = math.sin(loc), math.cos(loc)
            Rw = min(hl / abs(ux) if abs(ux) > 1e-6 else 1e9, hw / abs(uy) if abs(uy) > 1e-6 else 1e9)
            ri = Rw - proj * scale if scale else Rw
        x1, y1 = cx + (Rw + 95) * sn, cy - (Rw + 95) * cs
        ends = []
        for dx in ((-half, half) if half else (0,)):
            ox, oy = dx * cs, dx * sn
            a0 = math.sqrt(max(Rw * Rw - dx * dx, 0)) if not inlet else Rw; st = min(ri, a0)
            p0, p1 = (cx + st * sn + ox, cy - st * cs + oy), (x1 + ox, y1 + oy)
            dr.line([p0, p1], fill=blk, width=6); ends.append((p0, st < a0 - 1))
        if len(ends) == 2 and ends[0][1] and ends[1][1]: dr.line([ends[0][0], ends[1][0]], fill=blk, width=6)
        lab = true_dir(p["dir"], fn); bw = dr.textlength(lab, font=f)
        tx, ty = cx + (Rw + 135) * sn, cy - (Rw + 135) * cs
        dr.text((min(max(tx - bw / 2, 4), IMG_W - bw - 4), min(max(ty - 30, 4), IMG_H - 64)), lab, fill=blk, font=f)
    dr.polygon([(60, 20), (35, 95), (85, 95)], fill=(200, 0, 0, 255)); dr.text((42, 100), "N", fill=(200, 0, 0, 255), font=f)
    slots = iter([(230, 1080), (200, 330), (230, 700)])
    for st_ in s.get("streets", []):
        if st_.get("side") is not None:                # true azimuth from the structure toward the street centreline
            sa_ = math.radians(float(st_["side"])); dd = Rw + 230
            slot = (cx + dd * math.sin(sa_), cy - dd * math.cos(sa_))
        else: slot = next(slots)                       # structure sits in this street: open space on the left
        fs = ImageFont.truetype(FONT, 66); txt = st_["name"].upper(); tw = int(dr.textlength(txt, font=fs)) + 20
        t = Image.new("RGBA", (tw, 80), (0, 0, 0, 0)); ImageDraw.Draw(t).text((10, 5), txt, fill=blk, font=fs)
        t = t.rotate(90 - (float(st_["bearing"]) % 180), expand=True)      # baseline along the street, reads left to right
        x0 = min(max(int(slot[0] - t.width / 2), 0), IMG_W - t.width); y0 = min(max(int(slot[1] - t.height / 2), 0), IMG_H - t.height)
        im.alpha_composite(t, (x0, y0))                # kept fully inside the image
    b = io.BytesIO(); im.save(b, "PNG"); b.seek(0); return b

def dashed(dr, p0, p1, w, on=24, off=16):
    L = math.dist(p0, p1); n = int(L // (on + off)) + 1
    for i in range(n):
        a, b = i * (on + off) / L, min((i * (on + off) + on) / L, 1)
        dr.line([(p0[0] + (p1[0] - p0[0]) * a, p0[1] + (p1[1] - p0[1]) * a), (p0[0] + (p1[0] - p0[0]) * b, p0[1] + (p1[1] - p0[1]) * b)], fill=(0, 0, 0, 255), width=w)

# ---------- docx ----------
def borders(tbl, on):
    b = OxmlElement("w:tblBorders")
    for x in ("top", "left", "bottom", "right", "insideH", "insideV"):
        e = OxmlElement(f"w:{x}"); e.set(qn("w:val"), "single" if on else "nil"); e.set(qn("w:sz"), "4"); e.set(qn("w:color"), "000000"); b.append(e)
    tbl._tbl.tblPr.append(b)

def box(cell, lines, cols, w, size=11):
    cell.paragraphs[0]._p.getparent().remove(cell.paragraphs[0]._p)
    t = cell.add_table(rows=(len(lines) + cols - 1) // cols, cols=cols); borders(t, True); t.alignment = 1
    for k, txt in enumerate(lines):
        r = t.rows[k // cols]; r.height = Twips(ROW); r.height_rule = WD_ROW_HEIGHT_RULE.AT_LEAST
        c = r.cells[k % cols]; c.width = Twips(w); c.vertical_alignment = VA.BOTTOM
        c.paragraphs[0].add_run(txt).font.size = Pt(size)
    cell.add_paragraph()

def setcell(cell, text):
    p = cell.paragraphs[0]
    for r in p.runs: r.text = ""
    (p.runs[0] if p.runs else p.add_run()).text = text

def val(v, final):
    if v is None or str(v).strip() == "": return NR if final else ""
    return str(v)

def sheet(s, job, out, final):
    doc = Document(TEMPLATE); body = doc.element.body; kids = list(body)
    tbls = [k for k in kids if k.tag == qn("w:tbl")]
    add = next(k for k in kids if k.tag == qn("w:p") and "ADDITIONAL NOTES" in "".join(t.text or "" for t in k.iter(qn("w:t"))))
    for k in kids[kids.index(tbls[2]):kids.index(add)]:
        if not (k.tag == qn("w:p") and k.find(".//" + qn("w:pBdr")) is not None): body.remove(k)
    pt = doc.tables[0].rows[1].cells
    setcell(pt[0], s["point"]); setcell(pt[1], s.get("desc") or KIND_LABEL.get(s["kind"], s["kind"]))
    for c in pt: c.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
    inlet = s["kind"] in INLETS
    size_txt = (f"{s['box_l_ft']} x {s['box_w_ft']} FT BOX" if s.get("box_l_ft") and s.get("box_w_ft") else val(None, final)) if inlet \
        else (f"{s['dia_ft']} FT DIA" if s.get("dia_ft") else val(None, final))
    lid = s.get("lid") or ""
    notes = [s.get("notes") or ""] + s.get("_calc", [])
    notes.append(f"Measure-downs from {job.get('measure_from') or 'rim'}.")   # RH: rim is the default
    for row in doc.tables[1].rows:
        c = row.cells[0]; t = c.text
        if t.startswith("SIZE="): setcell(c, "SIZE= " + size_txt.upper())
        elif "CONCENTRIC" in t and "ECCENTRIC" in t:
            if inlet: setcell(c, "           GRATE/OPENING SIDE: " + val(s.get("opening_side"), final))
            else:
                conc, eccd = lid.lower().startswith("conc"), lid.lower().startswith("ecc")
                side = f" (LID {true_dir(lid.split()[1], float(job.get('field_north_az', 0)))})" if eccd and len(lid.split()) > 1 and lid.split()[1] in AZ else ""
                setcell(c, "           " + ("[X] " if conc else "[  ] ") + "CONCENTRIC" + " " * 40 + ("[X] " if eccd else "[  ] ") + "ECCENTRIC" + side)
        elif t.startswith("TYPE="): setcell(c, "TYPE= " + val(s.get("type"), final).upper())
        elif "GRADE RINGS" in t: c.paragraphs[0].add_run("  " + val(s.get("grade"), final))
        elif t.startswith("OTHER NOTES"): c.paragraphs[0].add_run("  " + " ".join(n.rstrip(".") + "." for n in notes if n)).font.size = Pt(9)
    L = doc.add_table(rows=3, cols=3); borders(L, False); L.alignment = 1
    for row in L.rows:
        for c, w in zip(row.cells, COLW): c.width = Twips(w)
    used = set(); mdown = job.get("measure_downs", {}).get(s["kind"], True)
    for p in s.get("pipes", []):
        if p.get("dir") in AZ:
            td = true_dir(p["dir"], float(job.get("field_north_az", 0))); rc = CELL[cell8(td)]
        else:                                          # direction not given: labelled by role, not drawn in plan
            td = (p.get("dir") or "OUT").upper(); rc = (1, 2)
        if rc in used: rc = next(k for k in ((0, 0), (0, 2), (2, 0), (2, 2), (0, 1), (2, 1), (1, 0), (1, 2)) if k not in used)
        used.add(rc)
        if not p.get("invert") and p.get("top"): inv = f"TOP {p['top']}"     # invert not reachable: show what was measured
        else: inv = val(p.get("invert"), final and mdown) + (" (CALC)" if p.get("_inv_calc") else "")
        size = (f"{p['size']}\"" if p.get("size") else val(None, final)) + (" (CALC)" if p.get("_size_calc") else "")
        lines = [f"I/{td}= {inv}", f"SIZE= {size}", "TYPE= " + val(p.get("type"), final).upper(), "DROP: " + val(p.get("drop"), final).upper()]
        r_, c_ = rc
        if c_ == 1: box(L.cell(r_, c_), lines, 2, 2400)
        elif r_ == 1: box(L.cell(r_, c_), lines, 1, 2700)
        else: box(L.cell(r_, c_), lines, 2, 1400, 10)
    free = next((k for k in ((2, 0), (0, 0), (2, 2), (0, 2)) if k not in used), None)
    if free: box(L.cell(*free), ["I/CNTR STRUCTURE=", val(s.get("cntr"), final and mdown)], 1, 2700)
    cp = L.cell(1, 1).paragraphs[0]; cp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cp.add_run().add_picture(plan_png(s, job), width=Emu(int(CIRC * IMG_W / IMG_H)))
    for (r_, c_) in ((1, 0), (1, 2), (1, 1)): L.cell(r_, c_).vertical_alignment = VA.CENTER
    for pe_ in L._tbl.iter(qn("w:p")):
        p = Paragraph(pe_, L._parent); fmt = p.paragraph_format
        fmt.space_before = Pt(0); fmt.space_after = Pt(0); fmt.line_spacing_rule = WD_LINE_SPACING.SINGLE
        if not p.text.strip() and pe_.find(".//" + qn("w:drawing")) is None: fmt.line_spacing = Pt(1)
    k2 = list(body); ai = k2.index(add)
    anchor = next((k for k in reversed(k2[:ai]) if k.tag == qn("w:p") and k.find(".//" + qn("w:pBdr")) is not None), add)
    anchor.addprevious(L._tbl)
    ph = s.get("photo")
    if ph and ph.get("path") and final and ph.get("orientation") in (None, "unknown"):
        print(f"  {s['point']}: photo left off - orientation unknown, so it can't be turned to true north. Ask the crew.")
        ph = None
    if ph and ph.get("path"):
        doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
        img, cap = photo_true(ph, job)
        h = doc.add_paragraph(); h.alignment = WD_ALIGN_PARAGRAPH.CENTER
        h.add_run(f"{'INLET' if inlet else 'MH'} {s['point']} - FIELD PHOTO (looking down; {cap})").bold = True
        ip = doc.add_paragraph(); ip.alignment = WD_ALIGN_PARAGRAPH.CENTER
        w, hh = img.size; sc = min(7.0 / (w / 100), 8.6 / (hh / 100))
        b = io.BytesIO(); img.save(b, "JPEG", quality=85); b.seek(0)
        ip.add_run().add_picture(b, width=Inches(w / 100 * sc))
    doc.save(out)

def photo_true(ph, job):
    """Turn the photo to true north. orientation: 'field_north_up' | degrees field north is clockwise of photo-up | None."""
    img = Image.open(ph["path"]).convert("RGB"); o = ph.get("orientation")
    if o is None or o == "unknown": return img, "orientation as taken, not rotated"
    rot = (0 if o == "field_north_up" else float(o)) + float(job.get("field_north_az", 0))
    r = img.rotate(-rot, expand=True, fillcolor=(255, 255, 255))
    d = ImageDraw.Draw(r); f = ImageFont.truetype(FONT, 90); x, y = r.width - 170, 40
    d.polygon([(x, y), (x - 50, y + 150), (x + 50, y + 150)], fill=(220, 0, 0)); d.text((x - 32, y + 160), "N", fill=(220, 0, 0), font=f)
    return r, "rotated to true north"

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("job"); ap.add_argument("--only"); ap.add_argument("--final", action="store_true")
    ap.add_argument("--out"); a = ap.parse_args()
    job = json.load(open(a.job, encoding="utf8"))
    out = a.out or job["out_dir"]; os.makedirs(out, exist_ok=True)
    only = set(a.only.split(",")) if a.only else None
    for s in job["structures"]:
        if only and s["point"] not in only: continue
        derive(s, job)
        pre = "INLET" if s["kind"] in INLETS else "MH"
        fp = os.path.join(out, f"{pre}_{s['point']}.docx"); sheet(s, job, fp, a.final); print("wrote", fp)

if __name__ == "__main__":
    main()
