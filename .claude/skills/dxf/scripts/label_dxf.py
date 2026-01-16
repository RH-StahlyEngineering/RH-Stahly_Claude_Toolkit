#!/usr/bin/env python3
"""
DXF Survey Labeling Tool

Creates multileader labels for survey points with "/" in descriptions.
Uses native MULTILEADER entities with proper annotative scaling.
Supports color coding (ByLayer for deliverable, Red for drafter notes)
and optional building footprint hatching.
"""

import sys
import argparse
from pathlib import Path

try:
    import ezdxf
    from ezdxf.math import Vec2, Vec3
except ImportError:
    print("Error: ezdxf library not installed. Run: pip install ezdxf", file=sys.stderr)
    sys.exit(1)

# Color constants
COLOR_BYLAYER = 256
COLOR_RED = 1

# Drafter note keywords - these indicate internal notes, not deliverable data
DRAFTER_KEYWORDS = [
    'NO HZ', 'EL ONLY', 'CONNECT TO', 'NORTH ONLY',
    'CNTR COVER', '@ APPROX', 'ON SIDE OF', 'ON PROP',
    'DOWN SPOUT', 'HVAC', 'DRAIN', '/GB', '/TOP', '/RIM',
    'MISC/', 'EBOX/', 'MHSS/', 'SDI/'
]

# Deliverable point types
DELIVERABLE_PREFIXES = ['CP/', 'FFB/GYM', 'FFB/OUTSIDE', 'CB/']


def is_drafter_note(desc):
    """Determine if a point description is a drafter note (Red) vs deliverable (ByLayer)."""
    desc_upper = desc.upper()

    for prefix in DELIVERABLE_PREFIXES:
        if desc_upper.startswith(prefix):
            if 'NO HZ' in desc_upper:
                return True
            return False

    for keyword in DRAFTER_KEYWORDS:
        if keyword in desc_upper:
            return True

    if desc_upper.startswith('MISC'):
        return True

    return False


def get_brief_label(point_num, elev, desc):
    """Generate a brief label based on point type."""
    desc_upper = desc.upper()

    if desc_upper.startswith('CP/'):
        return f"CP {point_num}"

    if desc_upper.startswith('FFB/'):
        return f"FFB ELEV: {elev}"

    if desc_upper.startswith('CB/'):
        if 'CHIMNEY' in desc_upper:
            return "CHIM"
        return "CB"

    code = desc.split('/')[0].strip()
    return code


def fix_xref_dependencies(doc):
    """Fix all xref-dependent table entries that have | in name but missing dependency flag."""
    XREF_DEPENDENT_FLAG = 16
    total_fixed = 0

    # Tables to check: (table_accessor, name)
    tables = [
        (doc.linetypes, 'linetypes'),
        (doc.styles, 'text styles'),
        (doc.layers, 'layers'),
        (doc.dimstyles, 'dimension styles'),
    ]

    for table, table_name in tables:
        fixed = 0
        for entry in table:
            if '|' in entry.dxf.name:
                if hasattr(entry.dxf, 'flags'):
                    if not (entry.dxf.flags & XREF_DEPENDENT_FLAG):
                        entry.dxf.flags |= XREF_DEPENDENT_FLAG
                        fixed += 1
        if fixed:
            print(f"Fixed {fixed} xref-dependent {table_name}")
            total_fixed += fixed

    return total_fixed


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

            points.append({
                'block_name': block.name,
                'point_num': pnum_text,
                'elevation': elev_text,
                'description': desc_text
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
            positions[block_name] = Vec3(pos.x, pos.y, pos.z)

    return positions


def create_multileader(msp, position, text, color, scale, layer='G-ANNO'):
    """Create a proper MULTILEADER using native style from the document.

    Args:
        msp: Modelspace
        position: Target position for leader arrow
        text: Label text content
        color: ACI color (256=ByLayer, 1=Red, etc.)
        scale: Scale factor (e.g., 40 for 1"=40') - multiplies paper-space dimensions
        layer: Layer name for the multileader

    Returns:
        The created multileader entity
    """
    # Use the Standard style from the source DXF
    builder = msp.add_multileader_mtext('Standard')

    # Set overall scaling - multiplies paper-space dimensions by scale factor
    # With scale=40, text at 0.1" paper height becomes 4.0 model units
    builder.set_overall_scaling(scale)

    # Set content - color None means ByLayer
    # char_height=0.1 is paper-space height (0.1 inches)
    content_color = None if color == COLOR_BYLAYER else color
    builder.set_content(
        content=text,
        color=content_color,
        char_height=0.1,  # Paper-space height (0.1" text)
    )

    # Create leader with offset relative to target
    # segment1 is in paper-space units, will be multiplied by scale
    target = Vec2(position.x, position.y)
    segment1 = Vec2(15, 10)  # Paper-space units

    builder.quick_leader(
        content=text,
        target=target,
        segment1=segment1
    )

    # Set layer on the multileader entity
    builder.multileader.dxf.layer = layer

    return builder.multileader


def hatch_eob_polyline(msp, scale):
    """Find and hatch the V-SITE-EOB building footprint polyline."""
    eob_polyline = None
    for entity in msp:
        if 'EOB' in entity.dxf.layer and entity.dxftype() == 'LWPOLYLINE':
            if entity.closed:
                eob_polyline = entity
                break

    if not eob_polyline:
        print("Warning: Could not find closed EOB polyline for hatching", file=sys.stderr)
        return None

    try:
        hatch = msp.add_hatch(color=256, dxfattribs={'layer': 'V-SITE-EOB'})
        hatch.set_pattern_fill('ANSI31', scale=scale)
        hatch.paths.add_polyline_path(
            list(eob_polyline.get_points(format='xy')),
            is_closed=True
        )
        print("Created hatch for EOB building footprint")
        return hatch
    except Exception as e:
        print(f"Warning: Could not create hatch: {e}", file=sys.stderr)
        return None


def label_dxf(input_path, output_path, scale, hatch_buildings):
    """Main labeling function."""
    print(f"Reading source DXF: {input_path}")
    doc = ezdxf.readfile(input_path)
    msp = doc.modelspace()

    # Fix xref-dependent linetype and style flags
    fix_xref_dependencies(doc)

    # Extract points
    print("\nExtracting points with '/' in description...")
    points = extract_points_with_slash(doc)
    print(f"Found {len(points)} points with '/' in description")

    # Find positions
    block_names = set(p['block_name'] for p in points)
    positions = find_insert_positions(doc, block_names)
    print(f"Found positions for {len(positions)} blocks")

    # Create labels using native MULTILEADER entities
    print(f"\nCreating MULTILEADER labels (scale={scale})...")
    created_count = 0
    deliverable_count = 0
    drafter_count = 0

    for point in points:
        block_name = point['block_name']
        if block_name not in positions:
            print(f"Warning: No position found for block {block_name}", file=sys.stderr)
            continue

        position = positions[block_name]
        desc = point['description']
        pnum = point['point_num']
        elev = point['elevation']

        if is_drafter_note(desc):
            color = COLOR_RED
            drafter_count += 1
        else:
            color = COLOR_BYLAYER
            deliverable_count += 1

        label = get_brief_label(pnum, elev, desc)

        try:
            create_multileader(msp, position, label, color, scale, layer='G-ANNO')
            created_count += 1
            color_name = 'RED' if color == COLOR_RED else 'BYLAYER'
            print(f"  Pt {pnum}: '{label}' - {color_name}")
        except Exception as e:
            print(f"  Warning: Could not create multileader for Pt {pnum}: {e}", file=sys.stderr)

    print(f"\nCreated {created_count} MULTILEADER labels:")
    print(f"  - Deliverable (ByLayer): {deliverable_count}")
    print(f"  - Drafter Notes (Red): {drafter_count}")

    # Hatch building footprint if requested
    if hatch_buildings:
        print("\nHatching building footprint...")
        hatch_eob_polyline(msp, scale)

    # Save output
    print(f"\nSaving output to: {output_path}")
    doc.saveas(output_path)
    print("Done!")

    return created_count


def main():
    parser = argparse.ArgumentParser(
        description='Label DXF survey files with MULTILEADER annotations for points with "/" in descriptions.'
    )
    parser.add_argument('input_dxf', help='Input DXF file path')
    parser.add_argument('--scale', type=float, default=20,
                       help='Annotative scale factor, e.g., 20 for 1"=20\' (default: 20)')
    parser.add_argument('--output', '-o', help='Output file path (default: auto-generated)')
    parser.add_argument('--hatch-buildings', action='store_true',
                       help='Hatch building footprint polygons on EOB layers')

    args = parser.parse_args()

    input_path = Path(args.input_dxf)
    if not input_path.exists():
        print(f"Error: Input file not found: {args.input_dxf}", file=sys.stderr)
        sys.exit(1)

    if args.output:
        output_path = Path(args.output)
    else:
        output_path = input_path.with_stem(input_path.stem + '-LABELS')

    try:
        count = label_dxf(str(input_path), str(output_path), args.scale, args.hatch_buildings)
        print(f"\nSummary: Created {count} MULTILEADER labels at scale 1\"={args.scale}'")
        print(f"Output: {output_path}")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
