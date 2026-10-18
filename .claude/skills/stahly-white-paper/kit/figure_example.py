# Master figure: the whole story on the folder tree.
from PIL import Image, ImageDraw, ImageFont
import os
HERE = os.path.dirname(os.path.abspath(__file__))
F = 'C:/Windows/Fonts/'
def font(sz, bold=False): return ImageFont.truetype(F + ('arialbd.ttf' if bold else 'arial.ttf'), sz)
BLUE, TAN, CREAM, NAVY, GRAY, LGRAY, WHITE, RED = '#00548C', '#BABAB1', '#E9E6E1', '#043348', '#787878', '#C7C8CA', '#FFFFFF', '#C00000'
BS = chr(92)

fN, fB, fS, fT, fH, fStep = font(30), font(30, True), font(27), font(26, True), font(33, True), font(30, True)

# made-by marks: script = filled rounded box, template = outlined square, you = circle
SCRIPT = {'NF': BLUE, 'VS': NAVY, 'DM': GRAY}
def mark(d, x, y, k):
    if k in SCRIPT:
        w = d.textlength(k, font=fT) + 18
        d.rounded_rectangle([x, y, x + w, y + 36], radius=8, fill=SCRIPT[k]); d.text((x + 9, y + 4), k, font=fT, fill=WHITE); return x + w + 8
    if k == 'TP':
        d.rectangle([x, y, x + 36, y + 36], outline=NAVY, width=3); d.text((x + 18, y + 18), 'T', font=fT, fill=NAVY, anchor='mm'); return x + 44
    if k == 'YOU':
        d.ellipse([x, y, x + 36, y + 36], outline=NAVY, width=3, fill=CREAM); d.text((x + 18, y + 18), 'Y', font=fT, fill=NAVY, anchor='mm'); return x + 44

def step(d, x, y, n):
    d.ellipse([x, y, x + 42, y + 42], fill=RED if n == 0 else BLUE); d.text((x + 21, y + 21), str(n), font=fStep, fill=WHITE, anchor='mm')

# rows: (level, name, step, contents, marks, kept, source, style)
P = '<Project_Number>' + BS
rows = [
    (0, P + 'Survey_GIS_Data' + BS + '2-UAV', None, '', [], '', None, 'root'),
    (1, 'Planning', None, 'KML, flight plan, airspace approval; the tools', ['TP'], 'stays', None, ''),
    (1, 'Checkin', None, 'everything captured in the field', ['TP'], '', None, ''),
    (2, '261015', 1, 'one folder per Flight: the date you flew (from the photos)', ['NF'], '', None, 'date'),
    (3, 'Photos', 1, 'drone photos only; card 2, 3 ... copied as C2_, C3_', ['NF'], '2 yr', 'USB/SD Card(s)', ''),
    (3, 'Lidar', 2, 'lidar drive as-is, incl. lidar-unit images', ['NF', 'YOU'], '2 yr', 'Lidar drive', ''),
    (3, 'Base_Logs', 2, 'base station logs, names kept (2 receivers: a subfolder each)', ['NF', 'YOU'], '2 yr', 'Base receiver', ''),
    (3, 'Ground_Control', 3, '261015_UAV_Targets.jxl + 261015_Ground_Truth.csv: keep them separate', ['NF', 'YOU'], 'stays', 'Data collector / TBC', 'warn'),
    (1, 'Processing', None, 'one shared project per software', ['TP'], '5 yr', None, ''),
    (2, 'Virtual_Surveyor', 4, '261015_Ground_Truth_VS.csv', ['TP', 'VS'], '', None, ''),
    (2, 'TBC', None, 'TBC project', ['TP'], '', None, ''),
    (2, 'Lidar', None, '261015_Camera_Positions_Phoenix.csv (or _ROCK)', ['TP', 'YOU'], '', None, ''),
    (2, 'KLAU_PPK', None, '261015_Camera_Positions_KLAU.csv', ['TP', 'YOU'], '', None, ''),
    (2, 'RTK', 1, '261015_Camera_Positions_RTK.csv (fixed-RTK photos)', ['TP', 'NF'], '', None, ''),
    (1, 'Deliverables', None, '', ['TP'], 'stays', None, ''),
    (2, '261015', None, 'same Flight name as Checkin', ['NF'], '', None, 'date'),
    (3, 'Ortho, DEM, Point_Cloud, Reports', 5, '261015_Ortho_Full.tif, 261015_DEM.tif ...', ['NF', 'DM'], '', 'DroneMapper', ''),
    (3, 'CAD', None, 'breaklines, surfaces', ['NF', 'YOU'], '', None, ''),
    (3, '_Archive_yymmdd', None, 'old results after a re-run, moved by hand', ['YOU'], '', None, 'arch'),
    (0, P + 'DWG' + BS + 'Backgrounds', 6, 'low-resolution ortho, loaded; full/50% linked from Deliverables', ['YOU'], '', None, 'root'),
]
X_SRC, X_TREE, X_STEP, X_TXT, X_MARK, X_KEPT, W = 6, 300, 905, 960, 1655, 1795, 1900
RH, IND, TOP = 66, 40, 112
H = TOP + RH * len(rows) + 520
img = Image.new('RGB', (W, H), WHITE); d = ImageDraw.Draw(img)

# header
d.rectangle([0, 0, W, 58], fill=BLUE)
for x, t in ((X_SRC + 10, 'From the field'), (X_TREE + 10, 'Folder'), (X_STEP - 30, 'Step'), (X_TXT, 'What goes in it'), (X_MARK, 'Made by'), (X_KEPT, 'Kept')):
    d.text((x, 12), t, font=fB, fill=WHITE)
y0 = TOP - 46
for i, (lvl, name, st, txt, marks, kept, src, sty) in enumerate(rows):
    y = y0 + i * RH
    band = CREAM if i % 2 == 0 else WHITE
    if sty == 'warn': band = '#F6E4E4'
    d.rectangle([X_TREE, y, W, y + RH], fill=band)
    d.line([X_TREE, y + RH, W, y + RH], fill=TAN, width=2)
    x = X_TREE + 14 + lvl * IND
    if lvl:
        d.line([x - 22, y + RH // 2, x - 4, y + RH // 2], fill=TAN, width=3)
    d.rectangle([x, y + 22, x + 30, y + 46], fill=CREAM, outline=TAN, width=2); d.rectangle([x, y + 17, x + 12, y + 23], fill=TAN)
    f = fB if sty in ('root', 'date') else fN
    if sty == 'root' or len(name) > 26: f = font(27, True) if sty == 'root' else font(27)
    col = BLUE if sty in ('root', 'date') else (GRAY if sty == 'arch' else NAVY)
    d.text((x + 40, y + 16), name, font=f, fill=col)
    if st: step(d, X_STEP, y + 12, st)
    tf = fS
    if d.textlength(txt, font=tf) > X_MARK - X_TXT - 20:
        # wrap onto two lines
        words, a, b = txt.split(' '), '', ''
        for w_ in words:
            if not b and d.textlength((a + ' ' + w_).strip(), font=tf) <= X_MARK - X_TXT - 20: a = (a + ' ' + w_).strip()
            else: b = (b + ' ' + w_).strip()
        d.text((X_TXT, y + 4), a, font=tf, fill=NAVY); d.text((X_TXT, y + 34), b, font=tf, fill=NAVY)
    else:
        d.text((X_TXT, y + 18), txt, font=tf, fill=NAVY)
    mx = X_MARK
    for m in marks: mx = mark(d, mx, y + 15, m)
    if kept: d.text((X_KEPT, y + 18), kept, font=fB if kept != 'stays' else fN, fill=BLUE if 'yr' in kept else NAVY)
    if src:
        d.rounded_rectangle([X_SRC, y + 6, X_SRC + 268, y + RH - 6], radius=10, fill=CREAM, outline=TAN, width=2)
        d.text((X_SRC + 14, y + 16), src, font=fS, fill=NAVY)
        d.line([X_SRC + 272, y + RH // 2, x - 12, y + RH // 2], fill=TAN, width=6)
        d.polygon([(x - 2, y + RH // 2), (x - 22, y + RH // 2 - 13), (x - 22, y + RH // 2 + 13)], fill=TAN)
# warn tag on ground control
gi = [i for i, r in enumerate(rows) if r[7] == 'warn'][0]
# legend + steps
y = y0 + len(rows) * RH + 26
x = 10
d.text((x, y), 'Made by:', font=fB, fill=NAVY); x += 150
for k, t in (('NF', 'New_Flight'), ('VS', 'Make_VS_Ground_Truth'), ('DM', 'Import_DroneMapper'), ('TP', 'in the template'), ('YOU', 'you put it there')):
    x = mark(d, x, y - 2, k); d.text((x, y), t, font=fS, fill=NAVY); x += d.textlength(t, font=fS) + 34
d.text((10, y + 52), 'Kept: 2 yr / 5 yr on PROJECTS, then moved to cold storage (offline). stays = no cold-storage move.', font=fS, fill=NAVY)
y += 52
steps = [(1, 'New_Flight: pick every USB/SD Card or folder for this Flight; it reads the date, asks for a label, copies the photos, writes the RTK file'),
         (2, 'Copy the lidar drive and base logs in by hand'),
         (3, 'Export targets + ground truth from TBC into Ground_Control (keep them separate)'),
         (4, 'Make_VS_Ground_Truth: makes the Virtual Surveyor copy'),
         (5, 'Download DroneMapper results (within 90 days), then Import_DroneMapper'),
         (6, 'Drafters: MAPIINSERT the orthos into the _AP.dwg, unload all but the small one, save')]
y += 62
for i, (n, t) in enumerate(steps):
    cx = 10; cy = y + i * 56
    step(d, cx, cy, n); d.text((cx + 54, cy + 6), t, font=fS, fill=NAVY)
img = img.crop((0, 0, W, y + 62 + 6 * 56 + 4))
img.save(os.path.join(HERE, 'fig17_master.png'))
print('master', img.size)

# ---------- need a label? ----------
W2, H2 = 1900, 330
im = Image.new('RGB', (W2, H2), WHITE); g = ImageDraw.Draw(im)
def box(x, y, w, h, t, fill, fg, f=font(33)):
    g.rounded_rectangle([x, y, x + w, y + h], radius=14, fill=fill, outline=NAVY if fill == WHITE else fill, width=3)
    g.multiline_text((x + w / 2, y + h / 2), t, font=f, fill=fg, anchor='mm', align='center', spacing=6)
def arrow(x1, y1, x2, y2, t=''):
    g.line([x1, y1, x2, y2], fill=TAN, width=6)
    if x2 > x1: g.polygon([(x2 + 4, y2), (x2 - 18, y2 - 12), (x2 - 18, y2 + 12)], fill=TAN)
    if t: g.text(((x1 + x2) / 2, y1 - 22), t, font=fT, fill=NAVY, anchor='mm')
box(1400, 95, 490, 160, 'Not sure? Add one.\nThe processor decides.', CREAM, NAVY, font(30))
box(10, 90, 620, 150, 'Will these datasets be processed\nseparately from the rest of\nthe day\u2019s data? (another area or camera)', WHITE, NAVY)
box(820, 30, 520, 110, 'Yes  \u2192  type a label in\nNew_Flight: 261015_B', BLUE, WHITE, fB)
box(820, 190, 520, 110, 'No  \u2192  no label\n261015', NAVY, WHITE, fB)
arrow(640, 140, 810, 85, ''); arrow(640, 195, 810, 245, '')
im.save(os.path.join(HERE, 'fig17_label.png'))
print('label ok')
