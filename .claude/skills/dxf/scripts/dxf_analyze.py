#!/usr/bin/env python3
"""DXF structure analysis and statistics."""

import sys
import json
import argparse
from collections import Counter, defaultdict
import ezdxf


def analyze_structure(filepath):
    """Analyze DXF file structure and return comprehensive statistics."""
    doc = ezdxf.readfile(filepath)
    msp = doc.modelspace()

    by_type = defaultdict(int)
    by_layer = defaultdict(int)
    by_type_and_layer = defaultdict(lambda: defaultdict(int))

    min_x = min_y = min_z = float('inf')
    max_x = max_y = max_z = float('-inf')

    for entity in msp:
        etype = entity.dxftype()
        layer = entity.dxf.layer
        by_type[etype] += 1
        by_layer[layer] += 1
        by_type_and_layer[layer][etype] += 1

        # Track extents
        pt = None
        if hasattr(entity.dxf, 'insert'):
            pt = entity.dxf.insert
        elif hasattr(entity.dxf, 'start'):
            pt = entity.dxf.start
        elif hasattr(entity.dxf, 'center'):
            pt = entity.dxf.center

        if pt:
            min_x, max_x = min(min_x, pt.x), max(max_x, pt.x)
            min_y, max_y = min(min_y, pt.y), max(max_y, pt.y)
            if hasattr(pt, 'z'):
                min_z, max_z = min(min_z, pt.z), max(max_z, pt.z)

    return {
        'version': doc.dxfversion,
        'entity_counts': dict(by_type),
        'layer_counts': dict(by_layer),
        'by_type_and_layer': {k: dict(v) for k, v in by_type_and_layer.items()},
        'extents': {
            'min': [min_x if min_x != float('inf') else None,
                    min_y if min_y != float('inf') else None,
                    min_z if min_z != float('inf') else None],
            'max': [max_x if max_x != float('-inf') else None,
                    max_y if max_y != float('-inf') else None,
                    max_z if max_z != float('-inf') else None]
        },
        'header': {
            'text_style': doc.header.get('$TEXTSTYLE', 'Standard'),
            'dim_style': doc.header.get('$DIMSTYLE', 'Standard'),
            'current_layer': doc.header.get('$CLAYER', '0')
        }
    }


def main():
    parser = argparse.ArgumentParser(description='Analyze DXF file structure')
    parser.add_argument('filepath', help='Path to DXF file')
    parser.add_argument('--json', action='store_true', help='Output as JSON')
    args = parser.parse_args()

    result = analyze_structure(args.filepath)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"DXF Version: {result['version']}")
        print(f"\nEntity counts by type:")
        for etype, count in sorted(result['entity_counts'].items(), key=lambda x: -x[1]):
            print(f"  {etype}: {count}")
        print(f"\nEntity counts by layer:")
        for layer, count in sorted(result['layer_counts'].items(), key=lambda x: -x[1]):
            print(f"  {layer}: {count}")
        ext = result['extents']
        print(f"\nCoordinate extents:")
        print(f"  X: {ext['min'][0]} to {ext['max'][0]}")
        print(f"  Y: {ext['min'][1]} to {ext['max'][1]}")
        print(f"  Z: {ext['min'][2]} to {ext['max'][2]}")


if __name__ == '__main__':
    main()
