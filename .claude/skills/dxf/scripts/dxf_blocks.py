#!/usr/bin/env python3
"""Block operations for DXF files."""

import sys
import json
import argparse
import ezdxf


def list_blocks(filepath):
    """List all block definitions (excluding anonymous blocks)."""
    doc = ezdxf.readfile(filepath)
    blocks = []

    for block in doc.blocks:
        if not block.name.startswith('*'):
            entities = list(block)
            entity_types = {}
            for e in entities:
                etype = e.dxftype()
                entity_types[etype] = entity_types.get(etype, 0) + 1

            blocks.append({
                'name': block.name,
                'base_point': [block.base_point.x, block.base_point.y, block.base_point.z],
                'entity_count': len(entities),
                'entity_types': entity_types
            })
    return blocks


def get_block_contents(filepath, block_name):
    """Get detailed contents of a block definition."""
    doc = ezdxf.readfile(filepath)

    if block_name not in doc.blocks:
        return None

    block = doc.blocks.get(block_name)
    entities = []
    for entity in block:
        info = {
            'type': entity.dxftype(),
            'layer': entity.dxf.layer,
            'handle': entity.dxf.handle
        }
        entities.append(info)

    return {
        'name': block_name,
        'base_point': [block.base_point.x, block.base_point.y, block.base_point.z],
        'entities': entities
    }


def list_inserts(filepath, block_name=None):
    """List all INSERT (block reference) entities."""
    doc = ezdxf.readfile(filepath)
    msp = doc.modelspace()
    inserts = []

    for insert in msp.query('INSERT'):
        if block_name and insert.dxf.name != block_name:
            continue

        inserts.append({
            'handle': insert.dxf.handle,
            'block': insert.dxf.name,
            'layer': insert.dxf.layer,
            'position': [insert.dxf.insert.x, insert.dxf.insert.y, insert.dxf.insert.z],
            'scale': [insert.dxf.xscale, insert.dxf.yscale, insert.dxf.zscale],
            'rotation': insert.dxf.rotation,
            'has_attribs': insert.has_attrib
        })
    return inserts


def insert_block(filepath, block_name, x, y, z, layer, output_path, scale=1.0, rotation=0):
    """Insert a block reference at specified location."""
    doc = ezdxf.readfile(filepath)

    if block_name not in doc.blocks:
        return False, "Block not found"

    msp = doc.modelspace()
    msp.add_blockref(
        block_name,
        insert=(x, y, z),
        dxfattribs={
            'layer': layer,
            'xscale': scale,
            'yscale': scale,
            'zscale': scale,
            'rotation': rotation
        }
    )

    doc.saveas(output_path)
    return True, "Block inserted"


def explode_block(filepath, handle, output_path):
    """Explode a block reference by handle."""
    doc = ezdxf.readfile(filepath)
    msp = doc.modelspace()

    for insert in msp.query('INSERT'):
        if insert.dxf.handle == handle:
            insert.explode()
            doc.saveas(output_path)
            return True, "Block exploded"

    return False, "Block reference not found"


def main():
    parser = argparse.ArgumentParser(description='DXF block operations')
    subparsers = parser.add_subparsers(dest='command', required=True)

    # List-defs command
    list_defs_parser = subparsers.add_parser('list-defs', help='List block definitions')
    list_defs_parser.add_argument('filepath', help='Path to DXF file')
    list_defs_parser.add_argument('--json', action='store_true', help='Output as JSON')

    # Get-def command
    get_def_parser = subparsers.add_parser('get-def', help='Get block definition contents')
    get_def_parser.add_argument('filepath', help='Path to DXF file')
    get_def_parser.add_argument('--name', required=True, help='Block name')
    get_def_parser.add_argument('--json', action='store_true', help='Output as JSON')

    # List-inserts command
    list_ins_parser = subparsers.add_parser('list-inserts', help='List block references')
    list_ins_parser.add_argument('filepath', help='Path to DXF file')
    list_ins_parser.add_argument('--block', help='Filter by block name')
    list_ins_parser.add_argument('--json', action='store_true', help='Output as JSON')

    # Insert command
    insert_parser = subparsers.add_parser('insert', help='Insert block reference')
    insert_parser.add_argument('filepath', help='Path to DXF file')
    insert_parser.add_argument('--block', required=True, help='Block name')
    insert_parser.add_argument('--x', type=float, required=True, help='X coordinate')
    insert_parser.add_argument('--y', type=float, required=True, help='Y coordinate')
    insert_parser.add_argument('--z', type=float, default=0, help='Z coordinate')
    insert_parser.add_argument('--layer', required=True, help='Target layer')
    insert_parser.add_argument('--scale', type=float, default=1.0, help='Scale factor')
    insert_parser.add_argument('--rotation', type=float, default=0, help='Rotation angle')
    insert_parser.add_argument('--output', required=True, help='Output file path')

    # Explode command
    explode_parser = subparsers.add_parser('explode', help='Explode block reference')
    explode_parser.add_argument('filepath', help='Path to DXF file')
    explode_parser.add_argument('--handle', required=True, help='Block reference handle')
    explode_parser.add_argument('--output', required=True, help='Output file path')

    args = parser.parse_args()

    if args.command == 'list-defs':
        blocks = list_blocks(args.filepath)
        if args.json:
            print(json.dumps(blocks, indent=2))
        else:
            print(f"Found {len(blocks)} block definitions:")
            for b in blocks:
                types_str = ', '.join(f"{k}:{v}" for k, v in b['entity_types'].items())
                print(f"  {b['name']}: {b['entity_count']} entities ({types_str})")

    elif args.command == 'get-def':
        block = get_block_contents(args.filepath, args.name)
        if block:
            if args.json:
                print(json.dumps(block, indent=2))
            else:
                print(f"Block: {block['name']}")
                print(f"Base point: {block['base_point']}")
                print(f"Entities ({len(block['entities'])}):")
                for e in block['entities']:
                    print(f"  [{e['handle']}] {e['type']} on {e['layer']}")
        else:
            print(f"Block '{args.name}' not found")
            sys.exit(1)

    elif args.command == 'list-inserts':
        inserts = list_inserts(args.filepath, args.block)
        if args.json:
            print(json.dumps(inserts, indent=2))
        else:
            print(f"Found {len(inserts)} block references:")
            for ins in inserts:
                pos = ins['position']
                print(f"  [{ins['handle']}] {ins['block']} at ({pos[0]:.2f}, {pos[1]:.2f}, {pos[2]:.2f}) layer={ins['layer']}")

    elif args.command == 'insert':
        success, msg = insert_block(args.filepath, args.block, args.x, args.y, args.z,
                                    args.layer, args.output, args.scale, args.rotation)
        print(msg)
        if success:
            print(f"Saved to: {args.output}")
        else:
            sys.exit(1)

    elif args.command == 'explode':
        success, msg = explode_block(args.filepath, args.handle, args.output)
        print(msg)
        if success:
            print(f"Saved to: {args.output}")
        else:
            sys.exit(1)


if __name__ == '__main__':
    main()
