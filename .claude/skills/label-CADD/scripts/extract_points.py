#!/usr/bin/env python3
"""
Extract survey points with "/" in descriptions from DXF file.
Outputs JSON for Claude to analyze and make labeling decisions.
"""

import sys
import json
import argparse
from pathlib import Path

try:
    import ezdxf
    from ezdxf.math import Vec3
except ImportError:
    print("Error: ezdxf library not installed. Run: pip install ezdxf", file=sys.stderr)
    sys.exit(1)


def extract_points_with_slash(doc):
    """Extract all points with '/' in their description from anonymous blocks."""
    points = []

    for block in doc.blocks:
        if not block.name.startswith('*U'):
            continue

        entities = list(block)
        mtexts = [e for e in entities if e.dxftype() == 'MTEXT']

        if len(mtexts) < 3:
            continue

        try:
            elev_text = mtexts[0].text if hasattr(mtexts[0], 'text') else None
            pnum_text = mtexts[1].text if hasattr(mtexts[1], 'text') else None
            desc_text = mtexts[2].text if hasattr(mtexts[2], 'text') else None

            if not all([elev_text, pnum_text, desc_text]):
                continue

            if '/' not in desc_text:
                continue

            # Parse code and comment
            parts = desc_text.split('/', 1)
            code = parts[0].strip().upper()
            comment = parts[1].strip() if len(parts) > 1 else ""

            points.append({
                'block_name': block.name,
                'point_num': pnum_text.strip(),
                'elevation': elev_text.strip(),
                'description': desc_text.strip(),
                'code': code,
                'comment': comment
            })
        except Exception as e:
            print(f"Warning: Could not process block {block.name}: {e}", file=sys.stderr)

    return points


def find_insert_positions(doc, block_names):
    """Find the positions of INSERT entities that reference the given block names."""
    msp = doc.modelspace()
    positions = {}

    for insert in msp.query('INSERT'):
        block_name = insert.dxf.name
        if block_name in block_names:
            pos = insert.dxf.insert
            positions[block_name] = {'x': pos.x, 'y': pos.y, 'z': pos.z}

    return positions


def find_mleader_style(doc):
    """Find the 'Annotative Simplex' style or fall back to first available."""
    # mleader_styles returns tuples of (name, style_object)
    style_names = [name for name, _ in doc.mleader_styles]

    # Look for Annotative Simplex (may have hyphen or space)
    for name in style_names:
        if 'annotative' in name.lower() and 'simplex' in name.lower():
            return name

    # Fall back to first non-Standard style
    for name in style_names:
        if name.lower() != 'standard':
            return name

    # Last resort: Standard
    return 'Standard'


def main():
    parser = argparse.ArgumentParser(
        description='Extract survey points with "/" in descriptions from DXF file.'
    )
    parser.add_argument('input_dxf', help='Input DXF file path')

    args = parser.parse_args()

    input_path = Path(args.input_dxf)
    if not input_path.exists():
        print(json.dumps({'error': f'Input file not found: {args.input_dxf}'}))
        sys.exit(1)

    try:
        doc = ezdxf.readfile(str(input_path))

        # Extract points
        points = extract_points_with_slash(doc)

        # Find positions
        block_names = set(p['block_name'] for p in points)
        positions = find_insert_positions(doc, block_names)

        # Add positions to points
        for point in points:
            if point['block_name'] in positions:
                point['position'] = positions[point['block_name']]
            else:
                point['position'] = None

        # Find MLEADER style
        mleader_style = find_mleader_style(doc)

        # Output JSON
        result = {
            'source_file': str(input_path.absolute()),
            'mleader_style': mleader_style,
            'point_count': len(points),
            'points': points
        }

        print(json.dumps(result, indent=2))

    except Exception as e:
        print(json.dumps({'error': str(e)}))
        sys.exit(1)


if __name__ == '__main__':
    main()
