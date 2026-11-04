"""Fit an exhibit's limit polygon onto a blank aerial (affine from control points).

usage: fit_exhibit.py exhibit.png aerial.png --ex "x,y x,y x,y" --ae "x,y x,y x,y"
                      --red-vertices "x,y x,y ..." [-o ref_poly.json] [--grid]
--grid only writes ex_grid.png / ae_grid.png (50 px grid) to help pick points.
"""
import argparse, json, os
import numpy as np
from PIL import Image, ImageDraw

def pts(s): return np.array([[float(v) for v in p.split(',')] for p in s.split()])

def grid(src, dst):
    im = Image.open(src).convert('RGB'); d = ImageDraw.Draw(im)
    for x in range(0, im.size[0], 50):
        d.line([(x, 0), (x, im.size[1])], fill=(0, 255, 255) if x % 100 == 0 else (0, 120, 120))
        if x % 100 == 0: d.text((x + 2, 2), str(x), fill=(255, 255, 0))
    for y in range(0, im.size[1], 50):
        d.line([(0, y), (im.size[0], y)], fill=(0, 255, 255) if y % 100 == 0 else (0, 120, 120))
        if y % 100 == 0: d.text((2, y + 2), str(y), fill=(255, 255, 0))
    im.save(dst)

ap = argparse.ArgumentParser()
ap.add_argument('exhibit'); ap.add_argument('aerial')
ap.add_argument('--ex'); ap.add_argument('--ae'); ap.add_argument('--red-vertices')
ap.add_argument('-o', default='ref_poly.json'); ap.add_argument('--grid', action='store_true')
a = ap.parse_args()
out = os.path.dirname(os.path.abspath(a.o))
if a.grid:
    grid(a.exhibit, os.path.join(out, 'ex_grid.png')); grid(a.aerial, os.path.join(out, 'ae_grid.png'))
    raise SystemExit('wrote ex_grid.png, ae_grid.png')
ex, ae = pts(a.ex), pts(a.ae)
A = np.c_[ex, np.ones(len(ex))]
M = np.linalg.lstsq(A, ae, rcond=None)[0]
print('control-point residuals (px):', np.round(A @ M - ae, 1).tolist())
ref = [[round(float(v), 1) for v in np.r_[p, 1] @ M] for p in pts(a.red_vertices)]
json.dump(ref, open(a.o, 'w')); print('ref polygon:', ref)
im = Image.open(a.aerial).convert('RGB')
ImageDraw.Draw(im).polygon([tuple(p) for p in ref], outline=(255, 0, 0), width=4)
im.save(os.path.join(out, 'ref_on_aerial.png'))
