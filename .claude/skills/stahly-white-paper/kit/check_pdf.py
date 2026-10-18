"""Mechanical layout checks for a Stahly white paper PDF. Run after render.sh, before any reviewer.
Usage: python check_pdf.py PAPER.pdf      Exit code 1 if any FAIL.
Checks: fonts (Rockwell/Arial only), US Letter, H1 stranded near a page bottom,
figure text scale (27 px in a 1900 px figure must print >= ~7 pt), cover band flush,
large blank areas on non-final body pages.
"""
import sys, subprocess, fitz

pdf = sys.argv[1]
fails, warns = [], []

# fonts
out = subprocess.run(['pdffonts', pdf], capture_output=True, text=True).stdout.splitlines()[2:]
for line in out:
    name = line.split()[0] if line.split() else ''
    base = name.split('+')[-1]
    if base and not (base.startswith('Rockwell') or base.startswith('Arial')):
        fails.append(f'font: {base} embedded (only Rockwell/Arial allowed; likely a glyph fallback such as "·")')

d = fitz.open(pdf)
for p in d:
    n = p.number + 1
    w, h = p.rect.width, p.rect.height
    if (round(w), round(h)) != (612, 792):
        fails.append(f'p{n}: page is {w:.0f}x{h:.0f} pt, not US Letter')
    if n == 1:
        pix = p.get_pixmap(dpi=50, clip=fitz.Rect(0, h - 3, w, h))
        r, g, b = pix.pixel(pix.width // 2, pix.height - 1)
        if r > 245 and g > 245 and b > 245:
            fails.append('p1: white strip under the cover tagline band (cover table total must be 15840 - 6 twips)')
        continue
    blocks = p.get_text('dict')['blocks']
    lowest_text = 0
    for bl in blocks:
        if bl.get('type') != 0:
            continue
        for ln in bl['lines']:
            for sp in ln['spans']:
                y = sp['bbox'][3]
                if y < h - 60:  # ignore footer band
                    lowest_text = max(lowest_text, y)
                if 'Rockwell' in sp['font'] and 'Bold' in sp['font'] and sp['size'] >= 15 and sp['bbox'][1] > h * 0.82:
                    fails.append(f'p{n}: H1 "{sp["text"][:40]}" stranded near the page bottom')
    for img in p.get_image_info(xrefs=True):
        bw = img['bbox'][2] - img['bbox'][0]
        px = img.get('width') or 0
        if px >= 1000 and bw > 0:
            pt_27 = 27 * bw / px
            if pt_27 < 6.8:
                warns.append(f'p{n}: figure {px}px printed {bw:.0f}pt wide; 27 px text prints at {pt_27:.1f} pt (< 7 pt)')
    if n < len(d) and lowest_text and lowest_text < h * 0.62:
        warns.append(f'p{n}: text ends at {lowest_text / h:.0%} of the page; large blank area (check keep-with-next chains)')

for f in fails: print('FAIL', f)
for x in warns: print('WARN', x)
print('check_pdf: %d FAIL, %d WARN' % (len(fails), len(warns)))
sys.exit(1 if fails else 0)
