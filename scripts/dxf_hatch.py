#!/usr/bin/env python3
"""Hatch creation for closed polylines in DXF files."""

import sys
import json
import argparse
from fnmatch import fnmatch
import ezdxf


def find_closed_polylines(filepath, layer_pattern=None):
    """Find all closed LWPOLYLINE entities."""
    doc = ezdxf.readfile(filepath)
    msp = doc.modelspace()
    results = []

    for pline in msp.query('LWPOLYLINE'):
        if layer_pattern and not fnmatch(pline.dxf.layer, layer_pattern):
            continue
        if pline.is_closed:
            points = list(pline.get_points(format='xy'))
            results.append({
                'handle': pline.dxf.handle,
                'layer': pline.dxf.layer,
                'vertex_count': len(points),
                'elevation': pline.dxf.elevation
            })
    return results


def hatch_closed_polylines(filepath, output_path, layer_pattern=None, pattern='SOLID', color=256):
    """Create SOLID hatches inside all closed polylines."""
    doc = ezdxf.readfile(filepath)
    msp = doc.modelspace()
    hatched = 0

    for pline in msp.query('LWPOLYLINE'):
        if layer_pattern and not fnmatch(pline.dxf.layer, layer_pattern):
            continue
        if not pline.is_closed:
            continue

        points = list(pline.get_points(format='xy'))
        hatch = msp.add_hatch(color=color)
        hatch.dxf.layer = pline.dxf.layer
        hatch.set_pattern_fill(pattern)
        hatch.paths.add_polyline_path(points, is_closed=True)
        hatched += 1

    doc.saveas(output_path)
    return hatched


def hatch_by_handle(filepath, handle, output_path, pattern='SOLID', color=256):
    """Create hatch for a specific closed polyline by handle."""
    doc = ezdxf.readfile(filepath)
    msp = doc.modelspace()

    for pline in msp.query('LWPOLYLINE'):
        if pline.dxf.handle == handle:
            if not pline.is_closed:
                return False, "Polyline is not closed"

            points = list(pline.get_points(format='xy'))
            hatch = msp.add_hatch(color=color)
            hatch.dxf.layer = pline.dxf.layer
            hatch.set_pattern_fill(pattern)
            hatch.paths.add_polyline_path(points, is_closed=True)

            doc.saveas(output_path)
            return True, "Hatch created"

    return False, "Handle not found"


def main():
    parser = argparse.ArgumentParser(description='DXF hatch operations')
    subparsers = parser.add_subparsers(dest='command', required=True)

    # List command
    list_parser = subparsers.add_parser('list', help='List closed polylines')
    list_parser.add_argument('filepath', help='Path to DXF file')
    list_parser.add_argument('--layer', help='Layer pattern to filter')
    list_parser.add_argument('--json', action='store_true', help='Output as JSON')

    # Hatch-all command
    hatch_all_parser = subparsers.add_parser('hatch-all', help='Hatch all closed polylines')
    hatch_all_parser.add_argument('filepath', help='Path to DXF file')
    hatch_all_parser.add_argument('--output', required=True, help='Output file path')
    hatch_all_parser.add_argument('--layer', help='Layer pattern to filter')
    hatch_all_parser.add_argument('--pattern', default='SOLID', help='Hatch pattern (default: SOLID)')
    hatch_all_parser.add_argument('--color', type=int, default=256, help='Color (256=ByLayer)')

    # Hatch command
    hatch_parser = subparsers.add_parser('hatch', help='Hatch specific polyline by handle')
    hatch_parser.add_argument('filepath', help='Path to DXF file')
    hatch_parser.add_argument('--handle', required=True, help='Polyline handle')
    hatch_parser.add_argument('--output', required=True, help='Output file path')
    hatch_parser.add_argument('--pattern', default='SOLID', help='Hatch pattern')
    hatch_parser.add_argument('--color', type=int, default=256, help='Color (256=ByLayer)')

    args = parser.parse_args()

    if args.command == 'list':
        results = find_closed_polylines(args.filepath, args.layer)
        if args.json:
            print(json.dumps(results, indent=2))
        else:
            print(f"Found {len(results)} closed polylines:")
            for r in results:
                print(f"  [{r['handle']}] {r['layer']}: {r['vertex_count']} vertices, elev={r['elevation']}")

    elif args.command == 'hatch-all':
        count = hatch_closed_polylines(args.filepath, args.output, args.layer, args.pattern, args.color)
        print(f"Created {count} hatches")
        print(f"Saved to: {args.output}")

    elif args.command == 'hatch':
        success, msg = hatch_by_handle(args.filepath, args.handle, args.output, args.pattern, args.color)
        if success:
            print(f"Created hatch for {args.handle}")
            print(f"Saved to: {args.output}")
        else:
            print(f"Error: {msg}")
            sys.exit(1)


if __name__ == '__main__':
    main()
