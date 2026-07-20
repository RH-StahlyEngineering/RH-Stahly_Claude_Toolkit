"""Enumerate Phoenix sessions, classify, parse trajectories + base RINEX, match each valid
mission to its best base, group into batches. Writes acq_data.json, matrix.csv, batches.json.

Usage:
  python analyze.py --sessions <PROCESSING_DIR> --bases <RINEX_DIR> [--bases <DIR2> ...] \
      [--control <control.csv> --control-points 1,2,5] [--policy furthest|avg] [--max-mi 10] \
      --out-dir <OUT>
"""
import argparse, os, glob, json, csv, math
import phoenix_lib as P


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--sessions', required=True)
    ap.add_argument('--bases', action='append', required=True)
    ap.add_argument('--control'); ap.add_argument('--control-points', default='')
    ap.add_argument('--policy', choices=['furthest', 'avg'], default='furthest')
    ap.add_argument('--max-mi', type=float, default=10.0)
    ap.add_argument('--out-dir', required=True)
    a = ap.parse_args()
    os.makedirs(a.out_dir, exist_ok=True)
    skips = []

    # control points (optional): number -> (lat,lon)
    control = {}
    if a.control and a.control_points:
        want = set(x.strip() for x in a.control_points.split(','))
        for row in csv.reader(open(a.control)):
            if row and row[0].strip() in want and len(row) >= 3:
                try:
                    control[row[0].strip()] = P.mt_stateplane_to_wgs84(float(row[1]), float(row[2]))
                except ValueError:
                    pass

    # bases: parse obs headers; label by nearest control point if available
    bases = []
    for d in a.bases:
        for fp in P.find_obs_files(d):
            h = P.read_rinex_header(fp)
            if not h:
                skips.append(f"BASE {os.path.basename(fp)}: header incomplete/zero pos"); continue
            label = h['file']
            if control:
                k = min(control, key=lambda c: P.haversine_mi(h['lat'], h['lon'], *control[c]))
                if P.haversine_mi(h['lat'], h['lon'], *control[k]) < 0.2:
                    label = f"CP{k}"; h['lat'], h['lon'] = control[k]  # snap to surveyed control
                else:
                    continue  # obs not on a named control point -> ignore
            h['label'] = label; bases.append(h)

    # sessions
    acq = []; rows = []
    for folder in sorted(glob.glob(os.path.join(a.sessions, '*'))):
        if not os.path.isdir(folder): continue
        c = P.classify_session(folder)
        rec = {'session': c['session'], 'type': c['type'], 'has_nav': False, 'valid': False}
        if c['nav']:
            nav = P.parse_nav(c['nav'])
            if nav:
                traj = [(la, lo) for _, la, lo in nav['pts']]; dt_ = P.decimate(traj)
                la = [x for x, _ in traj]; lo = [y for _, y in traj]
                rec.update({'has_nav': True, 'valid': c['valid_txt'],
                            'gps_start': nav['gps_start'], 'gps_end': nav['gps_end'],
                            'scan_start_utc': P.gps_to_utc_str(nav['gps_start']),
                            'scan_end_utc': P.gps_to_utc_str(nav['gps_end']),
                            'centroid': [sum(la) / len(la), sum(lo) / len(lo)],
                            'bbox': [min(la), max(la), min(lo), max(lo)], 'traj': dt_})
            else:
                skips.append(f"NAV {c['session']}: no position epochs")
        acq.append(rec)

    def baseline(b, traj):
        ds = [P.haversine_mi(b['lat'], b['lon'], la, lo) for la, lo in traj]
        return (max(ds) if a.policy == 'furthest' else sum(ds) / len(ds))

    # match valid missions to bases
    for rec in acq:
        if not (rec['valid'] and rec['has_nav']): continue
        gs, ge, traj = rec['gps_start'], rec['gps_end'], rec['traj']
        cands = [(baseline(b, traj), b) for b in bases if b['first_gps'] <= gs and b['last_gps'] >= ge]
        rec['base_brackets'] = 'YES' if cands else 'NO'
        if cands:
            mi, b = min(cands, key=lambda x: x[0])
            rec.update({'best_base': b['label'], 'best_base_file': b['file'], 'best_base_mi': round(mi, 2),
                        'has_working_rinex': 'YES' if mi < a.max_mi else 'NO'})
        else:
            rec.update({'best_base': '', 'best_base_file': '', 'best_base_mi': '', 'has_working_rinex': 'NO'})

    # matrix.csv (one row per valid mission)
    cols = ['session', 'type', 'scan_start_utc', 'scan_end_utc', 'centroid_lat', 'centroid_lon',
            'best_base', 'best_base_file', 'best_base_mi', 'base_brackets', 'has_working_rinex']
    with open(os.path.join(a.out_dir, 'matrix.csv'), 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader()
        for r in acq:
            if not r['valid']: continue
            w.writerow({'session': r['session'], 'type': r['type'],
                        'scan_start_utc': r.get('scan_start_utc', ''), 'scan_end_utc': r.get('scan_end_utc', ''),
                        'centroid_lat': round(r['centroid'][0], 6) if r.get('centroid') else '',
                        'centroid_lon': round(r['centroid'][1], 6) if r.get('centroid') else '',
                        'best_base': r.get('best_base', ''), 'best_base_file': r.get('best_base_file', ''),
                        'best_base_mi': r.get('best_base_mi', ''), 'base_brackets': r.get('base_brackets', ''),
                        'has_working_rinex': r.get('has_working_rinex', '')})

    # batches: <=3 per base FILE
    from collections import defaultdict
    grp = defaultdict(list)
    for r in acq:
        if r.get('best_base_file'):
            grp[(r['best_base'], r['best_base_file'])].append(r['session'])
    batches = []
    for (lbl, fn), lst in sorted(grp.items()):
        for i in range(0, len(lst), 3):
            batches.append({'base': lbl, 'file': fn, 'missions': lst[i:i + 3]})

    json.dump(acq, open(os.path.join(a.out_dir, 'acq_data.json'), 'w'))
    json.dump(batches, open(os.path.join(a.out_dir, 'batches.json'), 'w'), indent=1)
    if skips: open(os.path.join(a.out_dir, 'skips.log'), 'w').write('\n'.join(skips) + '\n')

    nv = sum(1 for r in acq if r['valid']); naer = sum(1 for r in acq if r['valid'] and r['type'] == 'AERIAL')
    nwork = sum(1 for r in acq if r.get('has_working_rinex') == 'YES')
    print(f"sessions={len(acq)} valid={nv} valid_aerial={naer} bases={len(bases)} "
          f"working_rinex={nwork} batches={len(batches)}")
    print(f"outputs -> {a.out_dir}: acq_data.json, matrix.csv, batches.json" + (", skips.log" if skips else ""))


if __name__ == '__main__':
    main()
