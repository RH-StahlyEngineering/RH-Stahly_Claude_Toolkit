#!/usr/bin/env python3
"""Extract COGO points from DXF files (INSERT entities on survey layers)."""

import sys
import json
import argparse
from fnmatch import fnmatch
import ezdxf


def extract_cogo_points(filepath, layer_pattern='V-*'):
    """Extract COGO points (INSERT entities) matching layer pattern."""
    doc = ezdxf.readfile(filepath)
    msp = doc.modelspace()
    points = []

    for insert in msp.query('INSERT'):
        if fnmatch(insert.dxf.layer, layer_pattern):
            points.append({
                'layer': insert.dxf.layer,
                'x': insert.dxf.insert.x,
                'y': insert.dxf.insert.y,
                'z': insert.dxf.insert.z,
                'block': insert.dxf.name,
                'handle': insert.dxf.handle,
                'attrs': {a.dxf.tag: a.dxf.text for a in insert.attribs} if insert.has_attrib else {}
            })
    return points


def main():
    parser = argparse.ArgumentParser(description='Extract COGO points from DXF')
    parser.add_argument('filepath', help='Path to DXF file')
    parser.add_argument('--layer', default='V-*', help='Layer pattern (default: V-*)')
    parser.add_argument('--json', action='store_true', help='Output as JSON')
    parser.add_argument('--csv', action='store_true', help='Output as CSV')
    args = parser.parse_args()

    points = extract_cogo_points(args.filepath, args.layer)

    if args.json:
        print(json.dumps(points, indent=2))
    elif args.csv:
        print("layer,x,y,z,block,handle")
        for p in points:
            print(f"{p['layer']},{p['x']},{p['y']},{p['z']},{p['block']},{p['handle']}")
    else:
        print(f"Found {len(points)} COGO points matching '{args.layer}':\n")
        for p in points:
            print(f"  [{p['handle']}] {p['layer']}: ({p['x']:.3f}, {p['y']:.3f}, {p['z']:.3f}) block={p['block']}")
            if p['attrs']:
                for tag, val in p['attrs'].items():
                    print(f"      {tag}: {val}")


if __name__ == '__main__':
    main()
