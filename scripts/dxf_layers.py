#!/usr/bin/env python3
"""Layer operations for DXF files."""

import sys
import json
import argparse
from collections import Counter
import ezdxf


def list_layers(filepath, with_counts=False):
    """List all layers with properties and optional entity counts."""
    doc = ezdxf.readfile(filepath)
    layers = []

    entity_counts = {}
    if with_counts:
        msp = doc.modelspace()
        entity_counts = Counter(e.dxf.layer for e in msp)

    for layer in doc.layers:
        info = {
            'name': layer.dxf.name,
            'color': layer.dxf.color,
            'linetype': layer.dxf.linetype,
            'is_on': layer.is_on(),
            'is_frozen': layer.is_frozen(),
            'is_locked': layer.is_locked()
        }
        if with_counts:
            info['entity_count'] = entity_counts.get(layer.dxf.name, 0)
        layers.append(info)

    return layers


def create_layer(filepath, layer_name, output_path, color=7, linetype='Continuous'):
    """Create a new layer."""
    doc = ezdxf.readfile(filepath)

    if layer_name in doc.layers:
        return False, "Layer already exists"

    doc.layers.add(layer_name, color=color, linetype=linetype)
    doc.saveas(output_path)
    return True, "Layer created"


def modify_layer(filepath, layer_name, output_path, color=None, linetype=None, on=None, frozen=None):
    """Modify layer properties."""
    doc = ezdxf.readfile(filepath)

    if layer_name not in doc.layers:
        return False, "Layer not found"

    layer = doc.layers.get(layer_name)

    if color is not None:
        layer.dxf.color = color
    if linetype is not None:
        layer.dxf.linetype = linetype
    if on is not None:
        layer.on = on
    if frozen is not None:
        if frozen:
            layer.freeze()
        else:
            layer.thaw()

    doc.saveas(output_path)
    return True, "Layer modified"


def delete_layer(filepath, layer_name, output_path, delete_entities=False):
    """Delete a layer (and optionally its entities)."""
    doc = ezdxf.readfile(filepath)

    if layer_name not in doc.layers:
        return False, "Layer not found", 0

    deleted_count = 0
    if delete_entities:
        msp = doc.modelspace()
        to_delete = [e for e in msp if e.dxf.layer == layer_name]
        deleted_count = len(to_delete)
        for entity in to_delete:
            msp.delete_entity(entity)

    doc.layers.remove(layer_name)
    doc.saveas(output_path)
    return True, "Layer deleted", deleted_count


def main():
    parser = argparse.ArgumentParser(description='DXF layer operations')
    subparsers = parser.add_subparsers(dest='command', required=True)

    # List command
    list_parser = subparsers.add_parser('list', help='List all layers')
    list_parser.add_argument('filepath', help='Path to DXF file')
    list_parser.add_argument('--counts', action='store_true', help='Include entity counts')
    list_parser.add_argument('--json', action='store_true', help='Output as JSON')

    # Create command
    create_parser = subparsers.add_parser('create', help='Create new layer')
    create_parser.add_argument('filepath', help='Path to DXF file')
    create_parser.add_argument('--name', required=True, help='Layer name')
    create_parser.add_argument('--output', required=True, help='Output file path')
    create_parser.add_argument('--color', type=int, default=7, help='Layer color (default: 7)')
    create_parser.add_argument('--linetype', default='Continuous', help='Line type')

    # Modify command
    modify_parser = subparsers.add_parser('modify', help='Modify layer properties')
    modify_parser.add_argument('filepath', help='Path to DXF file')
    modify_parser.add_argument('--name', required=True, help='Layer name')
    modify_parser.add_argument('--output', required=True, help='Output file path')
    modify_parser.add_argument('--color', type=int, help='New color')
    modify_parser.add_argument('--linetype', help='New line type')
    modify_parser.add_argument('--on', type=lambda x: x.lower() == 'true', help='Turn on/off (true/false)')
    modify_parser.add_argument('--frozen', type=lambda x: x.lower() == 'true', help='Freeze/thaw (true/false)')

    # Delete command
    delete_parser = subparsers.add_parser('delete', help='Delete layer')
    delete_parser.add_argument('filepath', help='Path to DXF file')
    delete_parser.add_argument('--name', required=True, help='Layer name')
    delete_parser.add_argument('--output', required=True, help='Output file path')
    delete_parser.add_argument('--delete-entities', action='store_true', help='Also delete entities on layer')

    args = parser.parse_args()

    if args.command == 'list':
        layers = list_layers(args.filepath, args.counts)
        if args.json:
            print(json.dumps(layers, indent=2))
        else:
            for lyr in layers:
                status = []
                if not lyr['is_on']:
                    status.append('OFF')
                if lyr['is_frozen']:
                    status.append('FROZEN')
                if lyr['is_locked']:
                    status.append('LOCKED')
                status_str = f" [{', '.join(status)}]" if status else ""
                count_str = f" ({lyr['entity_count']} entities)" if 'entity_count' in lyr else ""
                print(f"  {lyr['name']}: color={lyr['color']}, lt={lyr['linetype']}{status_str}{count_str}")

    elif args.command == 'create':
        success, msg = create_layer(args.filepath, args.name, args.output, args.color, args.linetype)
        print(msg)
        if success:
            print(f"Saved to: {args.output}")
        else:
            sys.exit(1)

    elif args.command == 'modify':
        success, msg = modify_layer(args.filepath, args.name, args.output,
                                    args.color, args.linetype, args.on, args.frozen)
        print(msg)
        if success:
            print(f"Saved to: {args.output}")
        else:
            sys.exit(1)

    elif args.command == 'delete':
        success, msg, count = delete_layer(args.filepath, args.name, args.output, args.delete_entities)
        print(msg)
        if success:
            if args.delete_entities:
                print(f"Deleted {count} entities")
            print(f"Saved to: {args.output}")
        else:
            sys.exit(1)


if __name__ == '__main__':
    main()
