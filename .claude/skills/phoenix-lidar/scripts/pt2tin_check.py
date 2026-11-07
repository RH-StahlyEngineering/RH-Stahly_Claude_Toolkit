"""Independent vertical check: shot vs local ground-only TIN.

For each check shot, build a Delaunay TIN from ground-classified (class 2) points within --radius
(XY, file units) and interpolate Z at the shot. dZ = shot - cloud (positive = cloud low).

Usage:
  python pt2tin_check.py --laz cloud.laz --shots a.csv[:Label] [--shots b.csv[:Label] ...] \
      [--radius 3.28] --out results.csv
Shots CSV: PNEZD, no header (point,northing,easting,elev,desc) in the cloud's units/CRS.
Read-only on inputs. Shots with <3 ground points or outside the local TIN are reported, not dropped
silently (typical causes: unclassified cliff/bank, bridge deck).
"""
import argparse, csv, numpy as np, laspy
from scipy.spatial import cKDTree, Delaunay


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--laz', required=True); ap.add_argument('--out', required=True)
    ap.add_argument('--shots', action='append', required=True)
    ap.add_argument('--radius', type=float, default=3.28)
    a = ap.parse_args()
    shots = []
    for s in a.shots:
        path, _, lab = s.partition(':') if not s[1:3] == ':\\' else (s, '', '')
        if s[1:3] == ':\\' and s.count(':') > 1:
            path, lab = s.rsplit(':', 1)
        lab = lab or path.rsplit('\\', 1)[-1]
        for r in csv.reader(open(path)):
            if r and r[0].strip():
                shots.append((lab, r[0], float(r[1]), float(r[2]), float(r[3]), r[4] if len(r) > 4 else ''))
    las = laspy.read(a.laz)
    cls = np.asarray(las.classification); g = cls == 2
    X, Y, Z = np.asarray(las.x)[g], np.asarray(las.y)[g], np.asarray(las.z)[g]
    print('points', las.header.point_count, 'ground', int(g.sum()), 'Z offset', las.header.offsets[2])
    tree = cKDTree(np.c_[X, Y]); rows = []
    for lab, p, N, E, Zs, code in shots:
        idx = tree.query_ball_point([E, N], a.radius); zc = None; note = ''
        if len(idx) >= 3:
            try:
                tri = Delaunay(np.c_[X[idx], Y[idx]]); s = tri.find_simplex([E, N])
                if s >= 0:
                    T = tri.transform[s]; b = T[:2] @ (np.array([E, N]) - T[2]); w = np.r_[b, 1 - b.sum()]
                    zc = float(w @ Z[idx][tri.simplices[s]])
                else:
                    note = 'outside local TIN'
            except Exception:
                note = 'TIN failed'
        else:
            note = f'{len(idx)} ground pts within radius'
        dz = None if zc is None else Zs - zc
        rows.append([lab, p, N, E, Zs, code, len(idx), '' if zc is None else round(zc, 3), '' if dz is None else round(dz, 3), note])
    with open(a.out, 'w', newline='') as f:
        w = csv.writer(f); w.writerow(['source', 'point', 'northing', 'easting', 'z_shot', 'code', 'n_ground', 'z_tin', 'dZ_shot_minus_cloud', 'note']); w.writerows(rows)
    groups = {'ALL': [r[8] for r in rows if r[8] != '']}
    for r in rows:
        if r[8] != '': groups.setdefault(r[0], []).append(r[8])
    for k, v in groups.items():
        d = np.array(v, float); rm = np.sqrt((d ** 2).mean())
        print(f'{k}: n={len(d)} mean={d.mean():+.3f} std={d.std(ddof=1) if len(d) > 1 else 0:.3f} RMSEz={rm:.3f} NVA95={1.96 * rm:.3f} range {d.min():+.3f}..{d.max():+.3f}')
    for r in rows:
        if r[9]: print('NO RESULT', r[0], r[1], r[9])


if __name__ == '__main__':
    main()
