#!/usr/bin/env python3
"""Entity modification operations for DXF files."""

import sys
import json
import argparse
from fnmatch import fnmatch
import ezdxf


def flatten_entities(filepath, output_path, layer_pattern=None):
    """Set Z=0 for all LINE, LWPOLYLINE, and POLYLINE entities."""
    doc = ezdxf.readfile(filepath)
    msp = doc.modelspace()
    modified = {'LINE': 0, 'LWPOLYLINE': 0, 'POLYLINE': 0}

    for entity in msp:
        if layer_pattern and not fnmatch(entity.dxf.layer, layer_pattern):
            continue

        etype = entity.dxftype()
        if etype == 'LINE':
            s, e = entity.dxf.start, entity.dxf.end
            entity.dxf.start = (s.x, s.y, 0)
            entity.dxf.end = (e.x, e.y, 0)
            modified['LINE'] += 1
        elif etype == 'LWPOLYLINE':
            entity.dxf.elevation = 0
            modified['LWPOLYLINE'] += 1
        elif etype == 'POLYLINE':
            for v in entity.vertices:
                loc = v.dxf.location
                v.dxf.location = (loc.x, loc.y, 0)
            modified['POLYLINE'] += 1

    doc.saveas(output_path)
    return modified


def move_to_layer(filepath, from_layer, to_layer, output_path):
    """Move all entities from one layer to another."""
    doc = ezdxf.readfile(filepath)
    msp = doc.modelspace()
    moved_count = 0

    for entity in msp:
        if fnmatch(entity.dxf.layer, from_layer):
            entity.dxf.layer = to_layer
            moved_count += 1

    doc.saveas(output_path)
    return moved_count


def delete_entities_on_layer(filepath, layer_pattern, output_path):
    """Delete all entities on matching layers."""
    doc = ezdxf.readfile(filepath)
    msp = doc.modelspace()

    to_delete = [e for e in msp if fnmatch(e.dxf.layer, layer_pattern)]
    count = len(to_delete)

    for entity in to_delete:
        msp.delete_entity(entity)

    doc.saveas(output_path)
    return count


def change_entity_layer(filepath, handle, new_layer, output_path):
    """Change layer for a specific entity by handle."""
    doc = ezdxf.readfile(filepath)
    msp = doc.modelspace()

    for entity in msp:
        if entity.dxf.handle == handle:
            entity.dxf.layer = new_layer
            doc.saveas(output_path)
            return True
    return False


def main():
    parser = argparse.ArgumentParser(description='DXF entity modification')
    subparsers = parser.add_subparsers(dest='command', required=True)

    # Flatten command
    flatten_parser = subparsers.add_parser('flatten', help='Set Z=0 for entities')
    flatten_parser.add_argument('filepath', help='Path to DXF file')
    flatten_parser.add_argument('--output', required=True, help='Output file path')
    flatten_parser.add_argument('--layer', help='Layer pattern to filter (optional)')

    # Move-layer command
    move_parser = subparsers.add_parser('move-layer', help='Move entities between layers')
    move_parser.add_argument('filepath', help='Path to DXF file')
    move_parser.add_argument('--from', dest='from_layer', required=True, help='Source layer pattern')
    move_parser.add_argument('--to', dest='to_layer', required=True, help='Target layer')
    move_parser.add_argument('--output', required=True, help='Output file path')

    # Delete command
    delete_parser = subparsers.add_parser('delete', help='Delete entities on layer')
    delete_parser.add_argument('filepath', help='Path to DXF file')
    delete_parser.add_argument('--layer', required=True, help='Layer pattern')
    delete_parser.add_argument('--output', required=True, help='Output file path')

    # Change-layer command
    change_parser = subparsers.add_parser('change-layer', help='Change layer for entity by handle')
    change_parser.add_argument('filepath', help='Path to DXF file')
    change_parser.add_argument('--handle', required=True, help='Entity handle')
    change_parser.add_argument('--layer', required=True, help='New layer')
    change_parser.add_argument('--output', required=True, help='Output file path')

    args = parser.parse_args()

    if args.command == 'flatten':
        modified = flatten_entities(args.filepath, args.output, args.layer)
        total = sum(modified.values())
        print(f"Flattened {total} entities: {modified['LINE']} LINE, {modified['LWPOLYLINE']} LWPOLYLINE, {modified['POLYLINE']} POLYLINE")
        print(f"Saved to: {args.output}")

    elif args.command == 'move-layer':
        count = move_to_layer(args.filepath, args.from_layer, args.to_layer, args.output)
        print(f"Moved {count} entities from '{args.from_layer}' to '{args.to_layer}'")
        print(f"Saved to: {args.output}")

    elif args.command == 'delete':
        count = delete_entities_on_layer(args.filepath, args.layer, args.output)
        print(f"Deleted {count} entities on layer '{args.layer}'")
        print(f"Saved to: {args.output}")

    elif args.command == 'change-layer':
        if change_entity_layer(args.filepath, args.handle, args.layer, args.output):
            print(f"Changed layer for {args.handle} to '{args.layer}'")
            print(f"Saved to: {args.output}")
        else:
            print(f"Entity {args.handle} not found")
            sys.exit(1)


if __name__ == '__main__':
    main()
