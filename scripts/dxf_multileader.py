#!/usr/bin/env python3
"""Multileader operations for DXF files."""

import sys
import json
import argparse
import ezdxf


def list_multileaders(filepath):
    """List all multileader entities with their text and positions."""
    doc = ezdxf.readfile(filepath)
    msp = doc.modelspace()
    results = []

    for mleader in msp.query('MULTILEADER'):
        ctx = mleader.context
        leader_points = []
        for leader in ctx.leaders:
            for line in leader.lines:
                leader_points.extend([(v.x, v.y, v.z) for v in line.vertices])

        results.append({
            'handle': mleader.dxf.handle,
            'layer': mleader.dxf.layer,
            'text': ctx.mtext.default_content if ctx.mtext else '',
            'char_height': ctx.char_height,
            'leader_points': leader_points
        })
    return results


def find_near_coordinate(filepath, x, y, tolerance=50):
    """Find multileaders near a coordinate."""
    doc = ezdxf.readfile(filepath)
    msp = doc.modelspace()
    results = []

    for mleader in msp.query('MULTILEADER'):
        ctx = mleader.context
        for leader in ctx.leaders:
            for line in leader.lines:
                for pt in line.vertices:
                    if abs(pt.x - x) < tolerance and abs(pt.y - y) < tolerance:
                        results.append({
                            'handle': mleader.dxf.handle,
                            'text': ctx.mtext.default_content if ctx.mtext else '',
                            'layer': mleader.dxf.layer,
                            'distance': ((pt.x - x)**2 + (pt.y - y)**2)**0.5
                        })
                        break
    return sorted(results, key=lambda r: r['distance'])


def create_multileader(filepath, target_x, target_y, target_z, text_lines, output_path,
                       landing_x=None, landing_y=None, style='Standard'):
    """Create a multileader at specified coordinates."""
    doc = ezdxf.readfile(filepath)
    msp = doc.modelspace()

    # Default landing point offset if not specified
    if landing_x is None:
        landing_x = target_x + 10
    if landing_y is None:
        landing_y = target_y + 10

    content = '\\P'.join(text_lines)

    ml_builder = msp.add_multileader_mtext(style=style)
    ml_builder.set_content(content)
    ml_builder.add_leader_line(mleader.ConnectionSide.left, [(target_x, target_y, target_z)])
    ml_builder.build((landing_x, landing_y, target_z))

    doc.saveas(output_path)
    return True


def edit_multileader(filepath, handle, new_text, output_path):
    """Edit existing multileader text by handle."""
    doc = ezdxf.readfile(filepath)
    msp = doc.modelspace()

    for mleader in msp.query('MULTILEADER'):
        if mleader.dxf.handle == handle:
            ctx = mleader.context
            if ctx.mtext:
                ctx.mtext.default_content = new_text
                doc.saveas(output_path)
                return True
    return False


def main():
    parser = argparse.ArgumentParser(description='DXF multileader operations')
    subparsers = parser.add_subparsers(dest='command', required=True)

    # List command
    list_parser = subparsers.add_parser('list', help='List all multileaders')
    list_parser.add_argument('filepath', help='Path to DXF file')
    list_parser.add_argument('--json', action='store_true', help='Output as JSON')

    # Find command
    find_parser = subparsers.add_parser('find', help='Find multileaders near coordinate')
    find_parser.add_argument('filepath', help='Path to DXF file')
    find_parser.add_argument('--x', type=float, required=True, help='X coordinate')
    find_parser.add_argument('--y', type=float, required=True, help='Y coordinate')
    find_parser.add_argument('--tolerance', type=float, default=50, help='Search tolerance')
    find_parser.add_argument('--json', action='store_true', help='Output as JSON')

    # Edit command
    edit_parser = subparsers.add_parser('edit', help='Edit multileader text')
    edit_parser.add_argument('filepath', help='Path to DXF file')
    edit_parser.add_argument('--handle', required=True, help='Entity handle')
    edit_parser.add_argument('--text', required=True, help='New text (use \\P for line breaks)')
    edit_parser.add_argument('--output', required=True, help='Output file path')

    args = parser.parse_args()

    if args.command == 'list':
        results = list_multileaders(args.filepath)
        if args.json:
            print(json.dumps(results, indent=2))
        else:
            for r in results:
                text_preview = r['text'][:40].replace('\n', '\\P') if r['text'] else '(empty)'
                print(f"[{r['handle']}] {r['layer']}: {text_preview}...")

    elif args.command == 'find':
        results = find_near_coordinate(args.filepath, args.x, args.y, args.tolerance)
        if args.json:
            print(json.dumps(results, indent=2))
        else:
            if results:
                for r in results:
                    print(f"[{r['handle']}] dist={r['distance']:.1f}: {r['text'][:40]}...")
            else:
                print(f"No multileaders found within {args.tolerance} units of ({args.x}, {args.y})")

    elif args.command == 'edit':
        if edit_multileader(args.filepath, args.handle, args.text, args.output):
            print(f"Updated multileader {args.handle}")
            print(f"Saved to: {args.output}")
        else:
            print(f"Multileader {args.handle} not found")
            sys.exit(1)


if __name__ == '__main__':
    main()
