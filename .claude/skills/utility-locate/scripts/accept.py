"""Score a blind locator's polygon against the exhibit polygon (both in aerial pixels).

usage: accept.py ref_poly.json area.json --aerial aerial.png
PASS = IoU >= 0.85 and missed area <= 5% of the reference. Extra area outside the
red line is allowed (the red line is a liberal limit). Writes <area>_vs_exhibit.png.
"""
import argparse, json
import numpy as np
from PIL import Image, ImageDraw

ap = argparse.ArgumentParser()
ap.add_argument('ref'); ap.add_argument('area'); ap.add_argument('--aerial', required=True)
ap.add_argument('--iou', type=float, default=0.85); ap.add_argument('--miss', type=float, default=0.05)
a = ap.parse_args()
im = Image.open(a.aerial).convert('RGB'); W, H = im.size
ref = [tuple(p) for p in json.load(open(a.ref))]; loc = [tuple(p) for p in json.load(open(a.area))]
def mask(p):
    m = Image.new('1', (W, H), 0); ImageDraw.Draw(m).polygon(p, fill=1); return np.array(m)
r, l = mask(ref), mask(loc)
iou = (r & l).sum() / (r | l).sum(); miss = (r & ~l).sum() / r.sum(); extra = (l & ~r).sum() / r.sum()
ok = iou >= a.iou and miss <= a.miss
print(f'IoU {iou:.3f}  missed {miss:.1%}  extra {extra:.1%}  -> {"PASS" if ok else "FAIL"}')
d = ImageDraw.Draw(im)
d.polygon(ref, outline=(255, 0, 0), width=4); d.polygon(loc, outline=(0, 255, 255), width=3)
out = a.area.rsplit('.', 1)[0] + '_vs_exhibit.png'; im.save(out); print('overlay:', out)
