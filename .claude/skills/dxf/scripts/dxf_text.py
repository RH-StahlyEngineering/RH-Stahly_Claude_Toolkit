#!/usr/bin/env python3
"""Text entity manipulation for DXF files."""

import sys
import json
import argparse
import ezdxf


def get_all_text(filepath):
    """Extract all text content from TEXT, MTEXT, and MULTILEADER entities."""
    doc = ezdxf.readfile(filepath)
    msp = doc.modelspace()
    texts = []

    for text in msp.query('TEXT'):
        texts.append({
            'type': 'TEXT',
            'content': text.dxf.text,
            'layer': text.dxf.layer,
            'handle': text.dxf.handle,
            'height': text.dxf.height,
            'position': [text.dxf.insert.x, text.dxf.insert.y, text.dxf.insert.z]
        })

    for mtext in msp.query('MTEXT'):
        texts.append({
            'type': 'MTEXT',
            'content': mtext.text,
            'layer': mtext.dxf.layer,
            'handle': mtext.dxf.handle,
            'height': mtext.dxf.char_height,
            'position': [mtext.dxf.insert.x, mtext.dxf.insert.y, mtext.dxf.insert.z]
        })

    for mleader in msp.query('MULTILEADER'):
        ctx = mleader.context
        if ctx.mtext:
            texts.append({
                'type': 'MULTILEADER',
                'content': ctx.mtext.default_content,
                'layer': mleader.dxf.layer,
                'handle': mleader.dxf.handle,
                'height': ctx.char_height
            })

    return texts


def rescale_text(filepath, old_scale, new_scale, output_path):
    """Rescale all text entities by scale factor ratio."""
    doc = ezdxf.readfile(filepath)
    msp = doc.modelspace()
    factor = new_scale / old_scale
    modified = {'TEXT': 0, 'MTEXT': 0, 'MULTILEADER': 0}

    for text in msp.query('TEXT'):
        text.dxf.height *= factor
        modified['TEXT'] += 1

    for mtext in msp.query('MTEXT'):
        mtext.dxf.char_height *= factor
        modified['MTEXT'] += 1

    for mleader in msp.query('MULTILEADER'):
        ctx = mleader.context
        if ctx.mtext:
            ctx.char_height *= factor
            modified['MULTILEADER'] += 1

    doc.saveas(output_path)
    return modified


def edit_text_by_handle(filepath, handle, new_text, output_path):
    """Edit text content by entity handle."""
    doc = ezdxf.readfile(filepath)
    msp = doc.modelspace()
    found = False

    for text in msp.query('TEXT'):
        if text.dxf.handle == handle:
            text.dxf.text = new_text
            found = True
            break

    if not found:
        for mtext in msp.query('MTEXT'):
            if mtext.dxf.handle == handle:
                mtext.text = new_text
                found = True
                break

    if not found:
        for mleader in msp.query('MULTILEADER'):
            if mleader.dxf.handle == handle:
                ctx = mleader.context
                if ctx.mtext:
                    ctx.mtext.default_content = new_text
                    found = True
                break

    if found:
        doc.saveas(output_path)
    return found


def main():
    parser = argparse.ArgumentParser(description='DXF text manipulation')
    subparsers = parser.add_subparsers(dest='command', required=True)

    # List command
    list_parser = subparsers.add_parser('list', help='List all text entities')
    list_parser.add_argument('filepath', help='Path to DXF file')
    list_parser.add_argument('--json', action='store_true', help='Output as JSON')

    # Rescale command
    rescale_parser = subparsers.add_parser('rescale', help='Rescale text entities')
    rescale_parser.add_argument('filepath', help='Path to DXF file')
    rescale_parser.add_argument('--old-scale', type=float, required=True, help='Original scale (e.g., 20 for 1"=20\')')
    rescale_parser.add_argument('--new-scale', type=float, required=True, help='New scale')
    rescale_parser.add_argument('--output', required=True, help='Output file path')

    # Edit command
    edit_parser = subparsers.add_parser('edit', help='Edit text by handle')
    edit_parser.add_argument('filepath', help='Path to DXF file')
    edit_parser.add_argument('--handle', required=True, help='Entity handle')
    edit_parser.add_argument('--text', required=True, help='New text content')
    edit_parser.add_argument('--output', required=True, help='Output file path')

    args = parser.parse_args()

    if args.command == 'list':
        texts = get_all_text(args.filepath)
        if args.json:
            print(json.dumps(texts, indent=2))
        else:
            for t in texts:
                print(f"[{t['handle']}] {t['type']} on {t['layer']}: {t['content'][:50]}...")

    elif args.command == 'rescale':
        modified = rescale_text(args.filepath, args.old_scale, args.new_scale, args.output)
        print(f"Rescaled {modified['TEXT']} TEXT, {modified['MTEXT']} MTEXT, {modified['MULTILEADER']} MULTILEADER")
        print(f"Saved to: {args.output}")

    elif args.command == 'edit':
        if edit_text_by_handle(args.filepath, args.handle, args.text, args.output):
            print(f"Updated text for handle {args.handle}")
            print(f"Saved to: {args.output}")
        else:
            print(f"Handle {args.handle} not found")
            sys.exit(1)


if __name__ == '__main__':
    main()
