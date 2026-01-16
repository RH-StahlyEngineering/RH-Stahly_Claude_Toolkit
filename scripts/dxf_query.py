#!/usr/bin/env python3
"""Query utilities for DXF files."""

import sys
import json
import argparse
from fnmatch import fnmatch
import ezdxf


def query_by_layer_pattern(filepath, layer_pattern):
    """Query entities matching layer pattern."""
    doc = ezdxf.readfile(filepath)
    msp = doc.modelspace()
    results = []

    for entity in msp:
        if fnmatch(entity.dxf.layer, layer_pattern):
            results.append({
                'type': entity.dxftype(),
                'layer': entity.dxf.layer,
                'handle': entity.dxf.handle
            })
    return results


def query_by_type(filepath, entity_types):
    """Query entities by type (e.g., 'LINE', 'CIRCLE', 'ARC')."""
    doc = ezdxf.readfile(filepath)
    msp = doc.modelspace()

    if isinstance(entity_types, str):
        entity_types = entity_types.split()

    query_str = ' '.join(entity_types)
    results = []
    for entity in msp.query(query_str):
        results.append({
            'type': entity.dxftype(),
            'layer': entity.dxf.layer,
            'handle': entity.dxf.handle
        })
    return results


def query_in_bbox(filepath, min_x, min_y, max_x, max_y):
    """Query entities within bounding box."""
    doc = ezdxf.readfile(filepath)
    msp = doc.modelspace()
    results = []

    for entity in msp:
        pt = None
        if hasattr(entity.dxf, 'insert'):
            pt = entity.dxf.insert
        elif hasattr(entity.dxf, 'start'):
            pt = entity.dxf.start
        elif hasattr(entity.dxf, 'center'):
            pt = entity.dxf.center

        if pt and min_x <= pt.x <= max_x and min_y <= pt.y <= max_y:
            results.append({
                'type': entity.dxftype(),
                'layer': entity.dxf.layer,
                'handle': entity.dxf.handle,
                'position': [pt.x, pt.y, pt.z if hasattr(pt, 'z') else 0]
            })
    return results


def get_entity_by_handle(filepath, handle):
    """Get entity details by handle."""
    doc = ezdxf.readfile(filepath)
    msp = doc.modelspace()

    for entity in msp:
        if entity.dxf.handle == handle:
            attrs = dict(entity.dxf.all_existing_dxf_attribs())
            # Convert Vec3 objects to lists for JSON serialization
            for k, v in attrs.items():
                if hasattr(v, 'x') and hasattr(v, 'y'):
                    attrs[k] = [v.x, v.y, v.z if hasattr(v, 'z') else 0]
            return {
                'type': entity.dxftype(),
                'layer': entity.dxf.layer,
                'handle': handle,
                'attributes': attrs
            }
    return None


def find_near_point(filepath, x, y, tolerance=10):
    """Find entities near a point."""
    doc = ezdxf.readfile(filepath)
    msp = doc.modelspace()
    results = []

    for entity in msp:
        pt = None
        if hasattr(entity.dxf, 'insert'):
            pt = entity.dxf.insert
        elif hasattr(entity.dxf, 'start'):
            pt = entity.dxf.start
        elif hasattr(entity.dxf, 'center'):
            pt = entity.dxf.center

        if pt:
            dist = ((pt.x - x)**2 + (pt.y - y)**2)**0.5
            if dist <= tolerance:
                results.append({
                    'type': entity.dxftype(),
                    'layer': entity.dxf.layer,
                    'handle': entity.dxf.handle,
                    'distance': dist,
                    'position': [pt.x, pt.y, pt.z if hasattr(pt, 'z') else 0]
                })

    return sorted(results, key=lambda r: r['distance'])


def main():
    parser = argparse.ArgumentParser(description='DXF query utilities')
    subparsers = parser.add_subparsers(dest='command', required=True)

    # Layer query
    layer_parser = subparsers.add_parser('layer', help='Query by layer pattern')
    layer_parser.add_argument('filepath', help='Path to DXF file')
    layer_parser.add_argument('--pattern', required=True, help='Layer pattern (e.g., V-*)')
    layer_parser.add_argument('--json', action='store_true', help='Output as JSON')

    # Type query
    type_parser = subparsers.add_parser('type', help='Query by entity type')
    type_parser.add_argument('filepath', help='Path to DXF file')
    type_parser.add_argument('--types', required=True, help='Entity types (e.g., "LINE CIRCLE ARC")')
    type_parser.add_argument('--json', action='store_true', help='Output as JSON')

    # Bbox query
    bbox_parser = subparsers.add_parser('bbox', help='Query within bounding box')
    bbox_parser.add_argument('filepath', help='Path to DXF file')
    bbox_parser.add_argument('--min-x', type=float, required=True)
    bbox_parser.add_argument('--min-y', type=float, required=True)
    bbox_parser.add_argument('--max-x', type=float, required=True)
    bbox_parser.add_argument('--max-y', type=float, required=True)
    bbox_parser.add_argument('--json', action='store_true', help='Output as JSON')

    # Handle query
    handle_parser = subparsers.add_parser('handle', help='Get entity by handle')
    handle_parser.add_argument('filepath', help='Path to DXF file')
    handle_parser.add_argument('--id', required=True, help='Entity handle')
    handle_parser.add_argument('--json', action='store_true', help='Output as JSON')

    # Near query
    near_parser = subparsers.add_parser('near', help='Find entities near point')
    near_parser.add_argument('filepath', help='Path to DXF file')
    near_parser.add_argument('--x', type=float, required=True)
    near_parser.add_argument('--y', type=float, required=True)
    near_parser.add_argument('--tolerance', type=float, default=10, help='Search radius')
    near_parser.add_argument('--json', action='store_true', help='Output as JSON')

    args = parser.parse_args()

    if args.command == 'layer':
        results = query_by_layer_pattern(args.filepath, args.pattern)
        if args.json:
            print(json.dumps(results, indent=2))
        else:
            print(f"Found {len(results)} entities matching '{args.pattern}':")
            for r in results[:50]:
                print(f"  [{r['handle']}] {r['type']} on {r['layer']}")
            if len(results) > 50:
                print(f"  ... and {len(results) - 50} more")

    elif args.command == 'type':
        results = query_by_type(args.filepath, args.types)
        if args.json:
            print(json.dumps(results, indent=2))
        else:
            print(f"Found {len(results)} entities of type '{args.types}':")
            for r in results[:50]:
                print(f"  [{r['handle']}] {r['type']} on {r['layer']}")
            if len(results) > 50:
                print(f"  ... and {len(results) - 50} more")

    elif args.command == 'bbox':
        results = query_in_bbox(args.filepath, args.min_x, args.min_y, args.max_x, args.max_y)
        if args.json:
            print(json.dumps(results, indent=2))
        else:
            print(f"Found {len(results)} entities in bbox:")
            for r in results[:50]:
                pos = r['position']
                print(f"  [{r['handle']}] {r['type']} at ({pos[0]:.2f}, {pos[1]:.2f})")
            if len(results) > 50:
                print(f"  ... and {len(results) - 50} more")

    elif args.command == 'handle':
        result = get_entity_by_handle(args.filepath, args.id)
        if result:
            if args.json:
                print(json.dumps(result, indent=2))
            else:
                print(f"Entity {args.id}:")
                print(f"  Type: {result['type']}")
                print(f"  Layer: {result['layer']}")
                print(f"  Attributes:")
                for k, v in result['attributes'].items():
                    print(f"    {k}: {v}")
        else:
            print(f"Entity {args.id} not found")
            sys.exit(1)

    elif args.command == 'near':
        results = find_near_point(args.filepath, args.x, args.y, args.tolerance)
        if args.json:
            print(json.dumps(results, indent=2))
        else:
            if results:
                print(f"Found {len(results)} entities near ({args.x}, {args.y}):")
                for r in results[:20]:
                    print(f"  [{r['handle']}] {r['type']} dist={r['distance']:.2f}")
            else:
                print(f"No entities found within {args.tolerance} units")


if __name__ == '__main__':
    main()
