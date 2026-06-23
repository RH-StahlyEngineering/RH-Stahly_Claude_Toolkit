"""
Dump a .plan file's structural summary for quick verification / debugging.

Usage:
    python inspect_plan.py path/to/mission.plan
"""
import json
import os
import sys


def inspect(path: str):
    p = json.load(open(path))
    m = p.get('mission', {})
    items = m.get('items', [])

    print(f"=== {os.path.basename(path)} ({os.path.getsize(path)} B) ===")
    # File format
    raw = open(path, 'rb').read()
    print(f"format: CRLF={raw.count(b'\\r\\n')}  pretty-printed={raw.count(b'\\n    ') > 0}")
    print()

    print("Top-level:")
    print(f"  fileType: {p.get('fileType')}   version: {p.get('version')}")
    print(f"  groundStation: {p.get('groundStation')}")
    print()

    print("Mission header:")
    print(f"  vehicleType:    {m.get('vehicleType')}    firmwareType: {m.get('firmwareType')}")
    print(f"  cruiseSpeed:    {m.get('cruiseSpeed')}    hoverSpeed:   {m.get('hoverSpeed')}")
    print(f"  globalPlanAltitudeMode: {m.get('globalPlanAltitudeMode')}")
    print(f"  plannedHomePosition: {m.get('plannedHomePosition')}")
    print(f"  item count: {len(items)}")
    print()

    # Count item types
    n_530 = sum(1 for it in items if it.get('command') == 530)
    n_178 = sum(1 for it in items if it.get('command') == 178)
    n_16 = sum(1 for it in items if it.get('command') == 16)
    n_20 = sum(1 for it in items if it.get('command') == 20)
    n_sv = sum(1 for it in items if it.get('complexItemType') == 'survey')
    n_cs = sum(1 for it in items if it.get('complexItemType') == 'CorridorScan')
    print(f"Item type counts: cmd530={n_530} cmd178={n_178} cmd16={n_16} cmd20(RTL)={n_20} survey={n_sv} corridor={n_cs}")
    if n_178 > 1:
        print(f"  WARNING: {n_178} cmd 178 items — canonical mission has exactly 1 (constant speed)")
    if n_cs:
        print("  WARNING: CorridorScan present — RC controller will reject")
    print()

    # First and last waypoint match check
    wp_items = [it for it in items if it.get('command') == 16]
    if wp_items:
        first = wp_items[0]['params']
        last = wp_items[-1]['params']
        same_xy = (first[4], first[5]) == (last[4], last[5])
        print(f"First WP: lat={first[4]:.6f} lon={first[5]:.6f} alt={first[6]}")
        print(f"Last  WP: lat={last[4]:.6f} lon={last[5]:.6f} alt={last[6]}")
        print(f"First == Last (closed mission): {same_xy}")
        print()

    # Standalone waypoint altitudes — flag if all identical (suspicious for terrain-follow)
    alts = [it['params'][6] for it in items if it.get('command') == 16]
    if alts:
        spread = max(alts) - min(alts)
        print(f"Standalone WP altitudes: {min(alts):.2f} -> {max(alts):.2f} m  (spread {spread:.2f} m)")
        if spread < 0.01 and m.get('globalPlanAltitudeMode') == 3:
            print("  WARNING: all standalone altitudes identical with terrain-follow mode")
            print("           — likely needs DEM-baking (see dem_lookup.py)")
        print()

    # Sequence
    print("Sequence:")
    for i, it in enumerate(items):
        if it.get('type') == 'SimpleItem':
            c = it.get('command')
            if c == 16:
                print(f"  {i:3d}: WP   frame={it.get('frame')} lat={it['params'][4]:.5f} lon={it['params'][5]:.5f} alt={it['params'][6]}")
            else:
                print(f"  {i:3d}: cmd {c}  params={it.get('params')}")
        else:
            print(f"  {i:3d}: {it.get('complexItemType')}")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    for path in sys.argv[1:]:
        inspect(path)
        print()
