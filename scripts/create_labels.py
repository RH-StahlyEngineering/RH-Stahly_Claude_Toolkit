#!/usr/bin/env python3
"""
Create MULTILEADER labels in a NEW DXF using raw DXF text manipulation.
Preserves template MULTILEADER structure for proper rendering.
Creates labels-only output (no source geometry).
"""

import sys
import json
import argparse
import re
from pathlib import Path

# Color constants
COLOR_BYLAYER = 256
COLOR_RED = 1


def read_dxf_as_text(filepath):
    """Read DXF file as text, trying different encodings."""
    for encoding in ['utf-8', 'cp1252', 'latin-1']:
        try:
            with open(filepath, 'r', encoding=encoding) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    raise ValueError(f"Could not read {filepath} with any encoding")


def find_multileader_template(dxf_content, layer_preference='G-ANNO'):
    """Find a MULTILEADER entity to use as template.

    Prefers entities on the specified layer with 'Annotative' style.
    Returns the entity text and parsed metadata.
    """
    # Find all MULTILEADER entities
    pattern = r'(  0\nMULTILEADER\n  5\n([0-9A-Fa-f]+)\n.*?)(?=  0\n[A-Z])'
    matches = list(re.finditer(pattern, dxf_content, re.DOTALL))

    if not matches:
        return None, None

    # Find one on preferred layer
    for match in matches:
        entity_text = match.group(1)
        handle = match.group(2)

        # Check layer
        layer_match = re.search(r'100\nAcDbEntity\n  8\n([^\n]+)', entity_text)
        if layer_match:
            layer = layer_match.group(1)
            if layer.upper() == layer_preference.upper():
                # Parse template metadata
                metadata = parse_template_metadata(entity_text)
                if metadata:
                    return entity_text, metadata

    # Fall back to first MULTILEADER
    entity_text = matches[0].group(1)
    metadata = parse_template_metadata(entity_text)
    return entity_text, metadata


def parse_template_metadata(entity_text):
    """Parse key coordinates and values from a MULTILEADER entity."""
    metadata = {}

    # Get handle
    handle_match = re.search(r'  5\n([0-9A-Fa-f]+)\n', entity_text)
    if handle_match:
        metadata['handle'] = handle_match.group(1)

    # Get layer
    layer_match = re.search(r'100\nAcDbEntity\n  8\n([^\n]+)', entity_text)
    if layer_match:
        metadata['layer'] = layer_match.group(1)

    # Get MLEADERSTYLE handle (340 after AcDbMLeader)
    # This is the main style reference for the entity
    mleaderstyle_match = re.search(r'100\nAcDbMLeader\n.*?340\n([0-9A-Fa-f]+)', entity_text, re.DOTALL)
    if mleaderstyle_match:
        metadata['mleaderstyle_handle'] = mleaderstyle_match.group(1)

    # Get text style handle (343 in CONTEXT_DATA or after 340)
    textstyle_match = re.search(r'343\n([0-9A-Fa-f]+)', entity_text)
    if textstyle_match:
        metadata['textstyle_handle'] = textstyle_match.group(1)

    # Get style handle (340 after LEADER section closes) - legacy
    style_match = re.search(r'301\n}\n340\n([0-9A-Fa-f]+)', entity_text)
    if style_match:
        metadata['style_handle'] = style_match.group(1)

    # Get arrow target from LEADER_LINE section
    # This is the point the arrow points to
    leader_line_match = re.search(
        r'304\nLEADER_LINE\{\n 10\n([^\n]+)\n 20\n([^\n]+)\n 30\n([^\n]+)',
        entity_text
    )
    if leader_line_match:
        metadata['arrow_target'] = {
            'x': float(leader_line_match.group(1)),
            'y': float(leader_line_match.group(2)),
            'z': float(leader_line_match.group(3))
        }

    # Get overall scale (group 40 in CONTEXT_DATA)
    scale_match = re.search(r'300\nCONTEXT_DATA\{\n 40\n([^\n]+)', entity_text)
    if scale_match:
        metadata['scale'] = float(scale_match.group(1))

    return metadata if 'arrow_target' in metadata else None


def extract_sections(dxf_content):
    """Extract main DXF sections."""
    sections = {}

    # Find HEADER section
    header_match = re.search(r'(  0\nSECTION\n  2\nHEADER\n.*?  0\nENDSEC)', dxf_content, re.DOTALL)
    if header_match:
        sections['HEADER'] = header_match.group(1)

    # Find CLASSES section
    classes_match = re.search(r'(  0\nSECTION\n  2\nCLASSES\n.*?  0\nENDSEC)', dxf_content, re.DOTALL)
    if classes_match:
        sections['CLASSES'] = classes_match.group(1)

    # Find TABLES section
    tables_match = re.search(r'(  0\nSECTION\n  2\nTABLES\n.*?  0\nENDSEC)', dxf_content, re.DOTALL)
    if tables_match:
        sections['TABLES'] = tables_match.group(1)

    # Find BLOCKS section
    blocks_match = re.search(r'(  0\nSECTION\n  2\nBLOCKS\n.*?  0\nENDSEC)', dxf_content, re.DOTALL)
    if blocks_match:
        sections['BLOCKS'] = blocks_match.group(1)

    # Find OBJECTS section
    objects_match = re.search(r'(  0\nSECTION\n  2\nOBJECTS\n.*?  0\nENDSEC)', dxf_content, re.DOTALL)
    if objects_match:
        sections['OBJECTS'] = objects_match.group(1)

    return sections


def extract_scale_objects(dxf_content):
    """Extract SCALE objects from ACAD_SCALELIST in OBJECTS section.

    Returns dict mapping scale_factor (int) -> (handle, entity_text)
    """
    scales = {}

    # SCALE entity pattern - captures handle and scale factor (group 141)
    pattern = r'(  0\nSCALE\n  5\n([0-9A-Fa-f]+)\n.*?141\n([0-9.]+)\n.*?)(?=  0\n[A-Z])'
    for match in re.finditer(pattern, dxf_content, re.DOTALL):
        entity_text = match.group(1)
        handle = match.group(2)
        scale_factor = float(match.group(3))
        scales[int(scale_factor)] = (handle, entity_text)

    return scales


def get_scale_handle(scales, scale_factor):
    """Get handle for a specific scale factor, or None if not found."""
    if scale_factor in scales:
        return scales[scale_factor][0]
    return None


def extract_extension_dict_chain(dxf_content, entity_handle):
    """Extract the extension dictionary chain for a MULTILEADER entity.

    The chain structure is:
    1. DICTIONARY (ext dict) - owned by entity, contains AcDbContextDataManager
    2. DICTIONARY (context mgr) - contains ACDB_ANNOTATIONSCALES
    3. DICTIONARY (annot scales) - contains *A1 entry
    4. ACDB_MLEADEROBJECTCONTEXTDATA_CLASS - the actual context data

    Returns dict with:
        - 'ext_dict_handle': handle of extension dictionary
        - 'context_mgr_handle': handle of context data manager dictionary
        - 'annot_scales_handle': handle of annotation scales dictionary
        - 'context_data_handle': handle of context data entity
        - 'scale_handle': handle of referenced SCALE object
        - 'ext_dict': extension dictionary entity text
        - 'context_mgr': context manager dictionary entity text
        - 'annot_scales': annotation scales dictionary entity text
        - 'context_data': context data entity text
    """
    result = {}

    # Find the MULTILEADER's XDICTIONARY reference
    ml_pattern = rf'MULTILEADER\n  5\n{entity_handle}\n102\n\{{ACAD_XDICTIONARY\n360\n([0-9A-Fa-f]+)\n'
    ml_match = re.search(ml_pattern, dxf_content)
    if not ml_match:
        return None

    ext_dict_handle = ml_match.group(1)
    result['ext_dict_handle'] = ext_dict_handle

    # Find extension dictionary (contains AcDbContextDataManager)
    ext_dict_pattern = rf'  0\nDICTIONARY\n  5\n{ext_dict_handle}\n.*?  3\nAcDbContextDataManager\n360\n([0-9A-Fa-f]+)\n.*?(?=  0\n[A-Z])'
    ext_dict_match = re.search(ext_dict_pattern, dxf_content, re.DOTALL)
    if ext_dict_match:
        result['context_mgr_handle'] = ext_dict_match.group(1)
        # Find the full entity
        full_pattern = rf'(  0\nDICTIONARY\n  5\n{ext_dict_handle}\n.*?)(?=  0\n[A-Z])'
        full_match = re.search(full_pattern, dxf_content, re.DOTALL)
        if full_match:
            result['ext_dict'] = full_match.group(1)

    # Find context manager dictionary (contains ACDB_ANNOTATIONSCALES)
    if 'context_mgr_handle' in result:
        ctx_mgr_handle = result['context_mgr_handle']
        ctx_mgr_pattern = rf'  0\nDICTIONARY\n  5\n{ctx_mgr_handle}\n.*?  3\nACDB_ANNOTATIONSCALES\n350\n([0-9A-Fa-f]+)\n.*?(?=  0\n[A-Z])'
        ctx_mgr_match = re.search(ctx_mgr_pattern, dxf_content, re.DOTALL)
        if ctx_mgr_match:
            result['annot_scales_handle'] = ctx_mgr_match.group(1)
            # Find the full entity
            full_pattern = rf'(  0\nDICTIONARY\n  5\n{ctx_mgr_handle}\n.*?)(?=  0\n[A-Z])'
            full_match = re.search(full_pattern, dxf_content, re.DOTALL)
            if full_match:
                result['context_mgr'] = full_match.group(1)

    # Find annotation scales dictionary (contains *A1 entry)
    if 'annot_scales_handle' in result:
        annot_handle = result['annot_scales_handle']
        annot_pattern = rf'  0\nDICTIONARY\n  5\n{annot_handle}\n.*?  3\n\*A\d+\n350\n([0-9A-Fa-f]+)\n.*?(?=  0\n[A-Z])'
        annot_match = re.search(annot_pattern, dxf_content, re.DOTALL)
        if annot_match:
            result['context_data_handle'] = annot_match.group(1)
            # Find the full entity
            full_pattern = rf'(  0\nDICTIONARY\n  5\n{annot_handle}\n.*?)(?=  0\n[A-Z])'
            full_match = re.search(full_pattern, dxf_content, re.DOTALL)
            if full_match:
                result['annot_scales'] = full_match.group(1)

    # Find the actual context data entity (ACDB_MLEADEROBJECTCONTEXTDATA_CLASS)
    if 'context_data_handle' in result:
        ctx_data_handle = result['context_data_handle']
        ctx_data_pattern = rf'(  0\nACDB_MLEADEROBJECTCONTEXTDATA_CLASS\n  5\n{ctx_data_handle}\n.*?)(?=  0\n[A-Z])'
        ctx_data_match = re.search(ctx_data_pattern, dxf_content, re.DOTALL)
        if ctx_data_match:
            result['context_data'] = ctx_data_match.group(1)
            # Extract SCALE reference (group 340 after AcDbAnnotScaleObjectContextData)
            scale_match = re.search(r'AcDbAnnotScaleObjectContextData\n340\n([0-9A-Fa-f]+)', result['context_data'])
            if scale_match:
                result['scale_handle'] = scale_match.group(1)

    return result if 'context_data' in result else None


def clone_extension_dict_chain(chain, new_entity_handle, dx, dy, dz,
                                new_text, new_scale_handle, handle_counter):
    """Clone the extension dictionary chain with new handles and updated values.

    Args:
        chain: dict from extract_extension_dict_chain()
        new_entity_handle: handle of the new MULTILEADER entity
        dx, dy, dz: coordinate offsets
        new_text: new text content
        new_scale_handle: handle of SCALE object for desired scale
        handle_counter: starting handle counter

    Returns:
        - new_ext_dict_handle: handle for entity's XDICTIONARY reference
        - objects_text: combined text of all cloned dictionary entities
        - handle_counter: updated counter
    """
    # Generate new handles for the chain
    new_ext_dict_handle = generate_handle(handle_counter)
    handle_counter += 1
    new_ctx_mgr_handle = generate_handle(handle_counter)
    handle_counter += 1
    new_annot_scales_handle = generate_handle(handle_counter)
    handle_counter += 1
    new_ctx_data_handle = generate_handle(handle_counter)
    handle_counter += 1

    objects_text = ""

    # Clone extension dictionary
    ext_dict = chain['ext_dict']
    ext_dict = re.sub(r'(  5\n)[0-9A-Fa-f]+\n', f'\\g<1>{new_ext_dict_handle}\n', ext_dict)
    ext_dict = re.sub(r'(330\n)[0-9A-Fa-f]+\n', f'\\g<1>{new_entity_handle}\n', ext_dict)  # Owner
    ext_dict = re.sub(r'(360\n)[0-9A-Fa-f]+\n', f'\\g<1>{new_ctx_mgr_handle}\n', ext_dict)  # AcDbContextDataManager ref
    # Remove ACAD_REACTORS block
    ext_dict = re.sub(r'102\n\{ACAD_REACTORS\n(330\n[0-9A-Fa-f]+\n)+102\n\}\n', '', ext_dict)
    objects_text += ext_dict

    # Clone context manager dictionary
    ctx_mgr = chain['context_mgr']
    ctx_mgr = re.sub(r'(  5\n)[0-9A-Fa-f]+\n', f'\\g<1>{new_ctx_mgr_handle}\n', ctx_mgr)
    ctx_mgr = re.sub(r'(330\n)[0-9A-Fa-f]+\n', f'\\g<1>{new_ext_dict_handle}\n', ctx_mgr)  # Owner
    ctx_mgr = re.sub(r'(350\n)[0-9A-Fa-f]+\n', f'\\g<1>{new_annot_scales_handle}\n', ctx_mgr)  # ACDB_ANNOTATIONSCALES ref
    # Remove ACAD_REACTORS block
    ctx_mgr = re.sub(r'102\n\{ACAD_REACTORS\n(330\n[0-9A-Fa-f]+\n)+102\n\}\n', '', ctx_mgr)
    objects_text += ctx_mgr

    # Clone annotation scales dictionary
    annot_scales = chain['annot_scales']
    annot_scales = re.sub(r'(  5\n)[0-9A-Fa-f]+\n', f'\\g<1>{new_annot_scales_handle}\n', annot_scales)
    annot_scales = re.sub(r'(330\n)[0-9A-Fa-f]+\n', f'\\g<1>{new_ctx_mgr_handle}\n', annot_scales)  # Owner
    annot_scales = re.sub(r'(350\n)[0-9A-Fa-f]+\n', f'\\g<1>{new_ctx_data_handle}\n', annot_scales)  # *A1 ref
    # Remove ACAD_REACTORS block
    annot_scales = re.sub(r'102\n\{ACAD_REACTORS\n(330\n[0-9A-Fa-f]+\n)+102\n\}\n', '', annot_scales)
    objects_text += annot_scales

    # Clone context data entity
    ctx_data = chain['context_data']
    ctx_data = re.sub(r'(  5\n)[0-9A-Fa-f]+\n', f'\\g<1>{new_ctx_data_handle}\n', ctx_data)
    ctx_data = re.sub(r'(330\n)[0-9A-Fa-f]+\n', f'\\g<1>{new_annot_scales_handle}\n', ctx_data)  # Owner
    # Update SCALE reference (first 340 after AcDbAnnotScaleObjectContextData)
    ctx_data = re.sub(
        r'(AcDbAnnotScaleObjectContextData\n340\n)[0-9A-Fa-f]+',
        f'\\g<1>{new_scale_handle}',
        ctx_data
    )
    # Remove ACAD_REACTORS block
    ctx_data = re.sub(r'102\n\{ACAD_REACTORS\n(330\n[0-9A-Fa-f]+\n)+102\n\}\n', '', ctx_data)

    # Offset coordinates in context data (same groups as MULTILEADER entity)
    def offset_group_in_text(text, group_code, offset_val):
        if len(group_code) >= 3:
            pattern = f'(\n{group_code}\n)([^\n]+)'
        else:
            pattern = f'( {group_code}\n)([^\n]+)'
        def replacer(m):
            return m.group(1) + offset_coordinate(m.group(2), offset_val)
        return re.sub(pattern, replacer, text)

    # Offset X coordinates
    for group in ['10', '12', '110']:
        ctx_data = offset_group_in_text(ctx_data, group, dx)
    # Offset Y coordinates
    for group in ['20', '22', '120']:
        ctx_data = offset_group_in_text(ctx_data, group, dy)
    # Offset Z coordinates
    for group in ['30', '32', '130']:
        ctx_data = offset_group_in_text(ctx_data, group, dz)

    # Replace text content (304 group)
    # CRITICAL: Pattern must match \n304\n to avoid matching coordinate values ending in "304"
    def replace_ctx_text(m):
        if 'LEADER' in m.group(0):
            return m.group(0)
        return f'\n304\n{new_text}\n'
    ctx_data = re.sub(r'\n304\n[^\n]+\n', replace_ctx_text, ctx_data, count=1)

    objects_text += ctx_data

    return new_ext_dict_handle, objects_text, handle_counter


def extract_mleaderstyles(dxf_content):
    """Extract MLEADERSTYLE entities and their dictionary from the OBJECTS section.

    Returns dict with:
        - 'styles': list of MLEADERSTYLE entity texts
        - 'dictionary': the ACAD_MLEADERSTYLE dictionary content
        - 'style_handles': dict mapping style names to handles (from entity group 3)
        - 'dict_name_to_handle': dict mapping handle -> dictionary entry name (for AutoCAD display)
    """
    result = {
        'styles': [],
        'dictionary': None,
        'style_handles': {},
        'dict_name_to_handle': {}  # Maps handle -> dictionary entry name (for AutoCAD display)
    }

    # Find all MLEADERSTYLE entities
    # Pattern: starts with "  0\nMLEADERSTYLE\n" and goes until next "  0\n" entity
    style_pattern = r'(  0\nMLEADERSTYLE\n  5\n([0-9A-Fa-f]+)\n.*?)(?=  0\n[A-Z])'
    for match in re.finditer(style_pattern, dxf_content, re.DOTALL):
        style_text = match.group(1)
        handle = match.group(2)
        result['styles'].append(style_text)

        # Try to find the style name (group 3 after AcDbMLeaderStyle)
        name_match = re.search(r'100\nAcDbMLeaderStyle\n.*?  3\n([^\n]+)', style_text, re.DOTALL)
        if name_match:
            result['style_handles'][name_match.group(1)] = handle

    # Find the ACAD_MLEADERSTYLE dictionary
    # It's a DICTIONARY entity that owns the MLEADERSTYLE entries
    dict_pattern = r'(  0\nDICTIONARY\n  5\n([0-9A-Fa-f]+)\n.*?(?:  3\n[^\n]*\n350\n[0-9A-Fa-f]+\n)+)'
    for match in re.finditer(dict_pattern, dxf_content, re.DOTALL):
        dict_text = match.group(1)
        # Check if this dictionary contains MLEADERSTYLE entries by looking for style handles
        for handle in [s.split('\n')[3] for s in result['styles']]:  # Get handles from styles
            if f'350\n{handle}\n' in dict_text:
                result['dictionary'] = dict_text
                result['dict_handle'] = match.group(2)
                # Extract name→handle mappings from dictionary entries
                # Pattern: "  3\n{name}\n350\n{handle}\n"
                entry_pattern = r'  3\n([^\n]+)\n350\n([0-9A-Fa-f]+)\n'
                for entry in re.finditer(entry_pattern, dict_text):
                    name = entry.group(1)
                    entry_handle = entry.group(2)
                    result['dict_name_to_handle'][entry_handle] = name
                break
        if result['dictionary']:
            break

    return result


def extract_text_style(dxf_content, style_handle):
    """Extract a specific text style from the TABLES section by handle.

    Returns the STYLE entity text or None if not found.
    """
    # Find the STYLE entity with the given handle
    pattern = rf'(  0\nSTYLE\n  5\n{style_handle}\n.*?)(?=  0\n)'
    match = re.search(pattern, dxf_content, re.DOTALL)
    if match:
        return match.group(1)
    return None


def generate_handle(counter):
    """Generate a unique hex handle."""
    return format(counter, 'X')


def offset_coordinate(value_str, offset):
    """Add offset to a coordinate value string."""
    try:
        value = float(value_str)
        new_value = value + offset
        # Preserve precision - use same format as original
        if '.' in value_str:
            decimals = len(value_str.split('.')[-1])
            return f"{new_value:.{decimals}f}"
        else:
            return str(int(new_value))
    except ValueError:
        return value_str


def create_label_entity(template, metadata, new_position, new_text, new_layer, new_color, new_handle, scale,
                        ext_dict_handle=None):
    """Create a new MULTILEADER entity from template with modifications.

    Args:
        template: Template entity text
        metadata: Parsed template metadata
        new_position: Dict with x, y, z for arrow target
        new_text: Label text content
        new_layer: Layer name (G-ANNO or 0)
        new_color: ACI color (256=ByLayer, 1=Red)
        new_handle: Unique hex handle string
        scale: Annotation scale factor
        ext_dict_handle: Optional handle of extension dictionary for annotative support.
                        If provided, XDICTIONARY reference is preserved with this handle.
                        If None, XDICTIONARY is removed (non-annotative fallback).

    Returns:
        Modified entity text
    """
    entity = template

    # Calculate offsets
    dx = new_position['x'] - metadata['arrow_target']['x']
    dy = new_position['y'] - metadata['arrow_target']['y']
    dz = new_position.get('z', 0) - metadata['arrow_target'].get('z', 0)

    # Remove binary data (310 groups) - AutoCAD will regenerate
    # The 310 data follows the 160 (shadow mode) group
    entity = re.sub(r'160\n[^\n]+\n(310\n[^\n]+\n)+', '160\n0\n', entity)

    # Replace handle
    entity = re.sub(r'(  5\n)[0-9A-Fa-f]+\n', f'\\g<1>{new_handle}\n', entity)

    # Handle XDICTIONARY reference
    if ext_dict_handle:
        # Preserve XDICTIONARY with new extension dictionary handle (for annotative support)
        entity = re.sub(
            r'(102\n\{ACAD_XDICTIONARY\n360\n)[0-9A-Fa-f]+(\n102\n\}\n)',
            f'\\g<1>{ext_dict_handle}\\g<2>',
            entity
        )
    else:
        # Remove XDICTIONARY reference - won't be valid without extension dict chain
        entity = re.sub(r'102\n\{ACAD_XDICTIONARY\n360\n[^\n]+\n102\n\}\n', '', entity)

    # Replace layer
    entity = re.sub(r'(100\nAcDbEntity\n  8\n)[^\n]+', f'\\g<1>{new_layer}', entity)

    # Add color after layer if not ByLayer
    if new_color != COLOR_BYLAYER:
        # Insert color (62) after layer line
        entity = re.sub(
            r'(100\nAcDbEntity\n  8\n[^\n]+\n)',
            f'\\g<1> 62\n{new_color}\n',
            entity
        )

    # Update scale (group 40 in CONTEXT_DATA)
    if scale != metadata.get('scale', 20):
        entity = re.sub(
            r'(300\nCONTEXT_DATA\{\n 40\n)[^\n]+',
            f'\\g<1>{float(scale)}',
            entity
        )

    # Offset coordinates BEFORE text replacement to avoid pattern conflicts
    # (text like "CP 10" contains " 10\n" which would match coordinate patterns)
    #
    # Only offset position coordinates, NOT direction vectors:
    # - 10/20/30: points, vertices, arrow targets (OFFSET THESE)
    # - 11/21/31: direction vectors - unit vectors, don't offset
    # - 12/22/32: text insertion point (OFFSET THESE)
    # - 13/23/33: direction vectors - unit vectors, don't offset
    # - 110/120/130: block reference point (OFFSET THESE)
    # - 111/121/131, 112/122/132: block axis vectors - don't offset

    # Helper to offset a specific group
    def offset_group(entity_text, group_code, offset_val):
        # DXF format: 2-digit codes have leading space " 10\n", 3-digit codes don't "110\n"
        if len(group_code) >= 3:
            # 3-digit codes: match newline before (no space)
            pattern = f'(\n{group_code}\n)([^\n]+)'
        else:
            # 1-2 digit codes: match space before
            pattern = f'( {group_code}\n)([^\n]+)'
        def replacer(m):
            return m.group(1) + offset_coordinate(m.group(2), offset_val)
        return re.sub(pattern, replacer, entity_text)

    # Offset X coordinates (10, 12, 110) - positions only, not direction vectors
    for group in ['10', '12', '110']:
        entity = offset_group(entity, group, dx)

    # Offset Y coordinates (20, 22, 120)
    for group in ['20', '22', '120']:
        entity = offset_group(entity, group, dy)

    # Offset Z coordinates (30, 32, 130)
    for group in ['30', '32', '130']:
        entity = offset_group(entity, group, dz)

    # Replace text content LAST (after coordinate offsets)
    # This prevents text like "CP 10" from being corrupted by coordinate offset patterns
    # The text is the first 304 group that doesn't contain "LEADER"
    #
    # CRITICAL: Pattern must match \n304\n (304 preceded by newline) to avoid matching
    # coordinate values that happen to end in "304" (e.g., 1614840.220786907477304)
    def replace_text(m):
        if 'LEADER' in m.group(0):
            return m.group(0)  # Keep LEADER_LINE{ markers
        return f'\n304\n{new_text}\n'

    entity = re.sub(r'\n304\n[^\n]+\n', replace_text, entity, count=1)

    return entity


def ensure_layer_in_tables(tables_section, layer_name, color=None):
    """Ensure a layer exists in the TABLES section."""
    # Check if layer already exists
    if re.search(f'  2\n{layer_name}\n', tables_section):
        return tables_section

    # Find where to insert (before ENDTAB of LAYER table)
    layer_table_match = re.search(
        r'(  0\nTABLE\n  2\nLAYER\n.*?)(  0\nENDTAB)',
        tables_section,
        re.DOTALL
    )

    if not layer_table_match:
        return tables_section

    # Find next available handle in table
    handles = re.findall(r'  5\n([0-9A-Fa-f]+)\n', layer_table_match.group(1))
    max_handle = max(int(h, 16) for h in handles) if handles else 0x100
    new_handle = format(max_handle + 1, 'X')

    # Create layer entry
    color_code = color if color else 7  # Default to white
    layer_entry = f"""  0
LAYER
  5
{new_handle}
100
AcDbSymbolTableRecord
100
AcDbLayerTableRecord
  2
{layer_name}
 70
     0
 62
{color_code}
  6
Continuous
"""

    # Insert layer
    insert_pos = layer_table_match.end(1)
    tables_section = tables_section[:insert_pos] + layer_entry + tables_section[insert_pos:]

    return tables_section


def clean_tables_section(tables_section):
    """Remove xref-dependent entries from TABLES section.

    Xref-dependent entries have '|' in their names and are invalid
    in standalone DXF files.
    """
    # Remove LTYPE entries with | in name
    # Pattern: find LTYPE entries and check if name (group 2) contains |
    def remove_xref_entries(section, entity_type):
        """Remove table entries where the name (group 2) contains |"""
        # Split into individual entries
        pattern = rf'(  0\n{entity_type}\n.*?)(?=  0\n)'

        def filter_entry(match):
            entry = match.group(1)
            # Check if name contains |
            name_match = re.search(r'  2\n([^\n]+)', entry)
            if name_match and '|' in name_match.group(1):
                return ''  # Remove this entry
            return entry

        return re.sub(pattern, filter_entry, section, flags=re.DOTALL)

    # Clean each table type that can have xref-dependent entries
    for table_type in ['LTYPE', 'LAYER', 'STYLE', 'DIMSTYLE', 'BLOCK_RECORD']:
        tables_section = remove_xref_entries(tables_section, table_type)

    return tables_section


def build_output_dxf(source_content, entities, source_path, template_metadata=None,
                     ext_dict_objects=None, scale_objects=None, template_content=None):
    """Build the output DXF file content.

    Args:
        source_content: Original DXF content (for extracting MLEADERSTYLE, etc.) - can be None
        entities: List of MULTILEADER entity texts
        source_path: Path to source file
        template_metadata: Parsed template metadata (optional)
        ext_dict_objects: Combined extension dictionary chain text for all entities (optional)
        scale_objects: Dict of scale_factor -> (handle, entity_text) to include (optional)
        template_content: Template DXF content for extracting additional objects (optional)
    """
    sections = extract_sections(source_content) if source_content else {}

    # Get or create minimal sections
    # Copy HEADER from source (has coordinate system info)
    header = sections.get('HEADER', create_minimal_header())
    # Use minimal CLASSES - source may have problematic entries
    classes = create_minimal_classes()
    # Use MINIMAL tables - source TABLES have xref-dependent entries that cause errors
    tables = create_minimal_tables()
    # Always use MINIMAL blocks - source blocks are huge and not needed
    blocks = create_minimal_blocks()

    # Extract MLEADERSTYLE from template if available, otherwise from source
    content_for_styles = template_content if template_content else source_content
    mleader_styles = extract_mleaderstyles(content_for_styles)

    # Build ENTITIES section
    entities_section = "  0\nSECTION\n  2\nENTITIES\n"
    for entity in entities:
        entities_section += entity
    entities_section += "  0\nENDSEC\n"

    # Create OBJECTS section with MLEADERSTYLE, SCALE objects, and extension dictionaries
    objects = create_objects_with_styles(mleader_styles, ext_dict_objects, scale_objects)

    # Build complete DXF
    output = ""
    output += header + "\n"
    output += classes + "\n"
    output += tables + "\n"
    output += blocks + "\n"
    output += entities_section
    output += objects + "\n"
    output += "  0\nEOF\n"

    return output


def create_minimal_header():
    """Create minimal HEADER section."""
    return """  0
SECTION
  2
HEADER
  9
$ACADVER
  1
AC1032
  9
$INSUNITS
 70
     1
  0
ENDSEC"""


def create_minimal_classes():
    """Create minimal CLASSES section with MULTILEADER and annotative context data classes."""
    return """  0
SECTION
  2
CLASSES
  0
CLASS
  1
MULTILEADER
  2
AcDbMLeader
  3
ACDB_MLEADER_CLASS
 90
        0
 91
        0
280
     0
281
     0
  0
CLASS
  1
ACDB_MLEADEROBJECTCONTEXTDATA_CLASS
  2
AcDbMLeaderObjectContextData
  3
ObjectDBX Classes
 90
     1153
 91
        2
280
     0
281
     0
  0
CLASS
  1
SCALE
  2
AcDbScale
  3
ObjectDBX Classes
 90
     1153
 91
       18
280
     0
281
     0
  0
ENDSEC"""


def create_minimal_tables():
    """Create minimal TABLES section with all required tables."""
    return """  0
SECTION
  2
TABLES
  0
TABLE
  2
VPORT
  5
8
100
AcDbSymbolTable
 70
     1
  0
VPORT
  5
29
100
AcDbSymbolTableRecord
100
AcDbViewportTableRecord
  2
*Active
 70
     0
 10
0.0
 20
0.0
 11
1.0
 21
1.0
 12
0.0
 22
0.0
 13
0.0
 23
0.0
 14
10.0
 24
10.0
 15
10.0
 25
10.0
 16
0.0
 26
0.0
 36
1.0
 17
0.0
 27
0.0
 37
0.0
 40
1.0
 41
1.0
 42
50.0
 43
0.0
 44
0.0
 50
0.0
 51
0.0
 71
     0
 72
   100
 73
     1
 74
     3
 75
     0
 76
     0
 77
     0
 78
     0
  0
ENDTAB
  0
TABLE
  2
LTYPE
  5
5
100
AcDbSymbolTable
 70
     3
  0
LTYPE
  5
14
100
AcDbSymbolTableRecord
100
AcDbLinetypeTableRecord
  2
ByBlock
 70
     0
  3

 72
    65
 73
     0
 40
0.0
  0
LTYPE
  5
15
100
AcDbSymbolTableRecord
100
AcDbLinetypeTableRecord
  2
ByLayer
 70
     0
  3

 72
    65
 73
     0
 40
0.0
  0
LTYPE
  5
16
100
AcDbSymbolTableRecord
100
AcDbLinetypeTableRecord
  2
Continuous
 70
     0
  3
Solid line
 72
    65
 73
     0
 40
0.0
  0
ENDTAB
  0
TABLE
  2
LAYER
  5
2
100
AcDbSymbolTable
 70
     2
  0
LAYER
  5
10
100
AcDbSymbolTableRecord
100
AcDbLayerTableRecord
  2
0
 70
     0
 62
     7
  6
Continuous
370
    -3
390
F
  0
LAYER
  5
11
100
AcDbSymbolTableRecord
100
AcDbLayerTableRecord
  2
G-ANNO
 70
     0
 62
     7
  6
Continuous
370
    -3
390
F
  0
ENDTAB
  0
TABLE
  2
STYLE
  5
3
100
AcDbSymbolTable
 70
     2
  0
STYLE
  5
20
100
AcDbSymbolTableRecord
100
AcDbTextStyleTableRecord
  2
Standard
 70
     0
 40
0.0
 41
1.0
 50
0.0
 71
     0
 42
0.2
  3
txt
  4

  0
STYLE
  5
21
100
AcDbSymbolTableRecord
100
AcDbTextStyleTableRecord
  2
Simplex
 70
     0
 40
0.0
 41
1.0
 50
0.0
 71
     0
 42
0.2
  3
simplex.shx
  4

  0
ENDTAB
  0
TABLE
  2
VIEW
  5
6
100
AcDbSymbolTable
 70
     0
  0
ENDTAB
  0
TABLE
  2
UCS
  5
7
100
AcDbSymbolTable
 70
     0
  0
ENDTAB
  0
TABLE
  2
APPID
  5
9
100
AcDbSymbolTable
 70
     1
  0
APPID
  5
12
100
AcDbSymbolTableRecord
100
AcDbRegAppTableRecord
  2
ACAD
 70
     0
  0
ENDTAB
  0
TABLE
  2
DIMSTYLE
  5
A
100
AcDbSymbolTable
 70
     1
100
AcDbDimStyleTable
  0
DIMSTYLE
105
27
100
AcDbSymbolTableRecord
100
AcDbDimStyleTableRecord
  2
Standard
 70
     0
  0
ENDTAB
  0
TABLE
  2
BLOCK_RECORD
  5
1
100
AcDbSymbolTable
 70
     2
  0
BLOCK_RECORD
  5
1F
100
AcDbSymbolTableRecord
100
AcDbBlockTableRecord
  2
*Model_Space
  0
BLOCK_RECORD
  5
1B
100
AcDbSymbolTableRecord
100
AcDbBlockTableRecord
  2
*Paper_Space
  0
ENDTAB
  0
ENDSEC"""


def create_minimal_blocks():
    """Create minimal BLOCKS section."""
    return """  0
SECTION
  2
BLOCKS
  0
BLOCK
  5
30
330
1F
100
AcDbEntity
  8
0
100
AcDbBlockBegin
  2
*Model_Space
 70
     0
 10
0.0
 20
0.0
 30
0.0
  3
*Model_Space
  1

  0
ENDBLK
  5
31
330
1F
100
AcDbEntity
  8
0
100
AcDbBlockEnd
  0
BLOCK
  5
32
330
1B
100
AcDbEntity
  8
0
100
AcDbBlockBegin
  2
*Paper_Space
 70
     0
 10
0.0
 20
0.0
 30
0.0
  3
*Paper_Space
  1

  0
ENDBLK
  5
33
330
1B
100
AcDbEntity
  8
0
100
AcDbBlockEnd
  0
ENDSEC"""


def create_minimal_objects():
    """Create minimal OBJECTS section with required NamedObject dictionary.

    The OBJECTS section is REQUIRED for valid DXF R13+ files.
    The root dictionary (NamedObject dictionary) must be the first object
    and must have owner handle 0. It must contain at least ACAD_GROUP entry.
    """
    return """  0
SECTION
  2
OBJECTS
  0
DICTIONARY
  5
C
330
0
100
AcDbDictionary
281
     1
  3
ACAD_GROUP
350
D
  3
ACAD_MLEADERSTYLE
350
E
  0
DICTIONARY
  5
D
330
C
100
AcDbDictionary
281
     1
  0
DICTIONARY
  5
E
330
C
100
AcDbDictionary
281
     1
  0
ENDSEC"""


def create_objects_with_styles(mleader_styles, ext_dict_objects=None, scale_objects=None):
    """Create OBJECTS section including MLEADERSTYLE entities, SCALE objects, and extension dictionaries.

    This is critical for MULTILEADER rendering - without the style definitions,
    the entities exist but are invisible.

    Args:
        mleader_styles: Dict from extract_mleaderstyles() containing:
            - 'styles': list of MLEADERSTYLE entity texts
            - 'dictionary': the MLEADERSTYLE dictionary (optional)
            - 'dict_handle': handle of the MLEADERSTYLE dictionary
        ext_dict_objects: Combined text of extension dictionary chains for annotative support (optional)
        scale_objects: Dict of scale_factor -> (handle, entity_text) for SCALE objects (optional)
    """
    if not mleader_styles.get('styles'):
        # No styles found, use minimal objects
        return create_minimal_objects()

    # Build the MLEADERSTYLE dictionary entries
    style_entries = ""
    dict_names = mleader_styles.get('dict_name_to_handle', {})
    for style_text in mleader_styles['styles']:
        # Get the handle from the style
        handle_match = re.search(r'  5\n([0-9A-Fa-f]+)\n', style_text)
        if handle_match:
            handle = handle_match.group(1)
            # Get dictionary name for this handle (preferred) or fall back to entity group 3
            # AutoCAD displays the dictionary entry name, not the internal group 3 name
            if handle in dict_names:
                name = dict_names[handle]
            else:
                name_match = re.search(r'100\nAcDbMLeaderStyle\n.*?  3\n([^\n]+)', style_text, re.DOTALL)
                name = name_match.group(1) if name_match else f"Style_{handle}"
            style_entries += f"  3\n{name}\n350\n{handle}\n"

    # Clean MLEADERSTYLE entities - remove ACAD_REACTORS blocks that reference
    # entities not in our output file
    cleaned_styles = []
    for style_text in mleader_styles['styles']:
        # Remove ACAD_REACTORS block - these reference entities not in our file
        cleaned = re.sub(r'102\n\{ACAD_REACTORS\n(330\n[0-9A-Fa-f]+\n)+102\n\}\n', '', style_text)
        # Update the owner to point to our MLEADERSTYLE dictionary (handle E)
        cleaned = re.sub(r'(  5\n[0-9A-Fa-f]+\n)330\n[0-9A-Fa-f]+\n', r'\g<1>330\nE\n', cleaned)
        cleaned_styles.append(cleaned)

    # Clean SCALE objects if provided
    cleaned_scales = []
    if scale_objects:
        for scale_factor, (handle, entity_text) in scale_objects.items():
            # Remove ACAD_REACTORS block
            cleaned = re.sub(r'102\n\{ACAD_REACTORS\n(330\n[0-9A-Fa-f]+\n)+102\n\}\n', '', entity_text)
            cleaned_scales.append(cleaned)

    # Build root dictionary entries - add ACAD_SCALELIST if we have scales
    root_dict_entries = """  3
ACAD_GROUP
350
D
  3
ACAD_MLEADERSTYLE
350
E"""
    if cleaned_scales:
        root_dict_entries += """
  3
ACAD_SCALELIST
350
B6"""

    # Build with style entries in dictionary E
    objects = f"""  0
SECTION
  2
OBJECTS
  0
DICTIONARY
  5
C
330
0
100
AcDbDictionary
281
     1
{root_dict_entries}
  0
DICTIONARY
  5
D
330
C
100
AcDbDictionary
281
     1
  0
DICTIONARY
  5
E
330
C
100
AcDbDictionary
281
     1
{style_entries}"""

    # Add the MLEADERSTYLE entities
    for style in cleaned_styles:
        objects += style

    # Add ACAD_SCALELIST dictionary and SCALE objects if provided
    if cleaned_scales:
        # Build scale list entries
        scale_list_entries = ""
        for scale_factor, (handle, _) in scale_objects.items():
            scale_name = f'1" = {scale_factor}\''
            scale_list_entries += f"  3\n{scale_name}\n350\n{handle}\n"

        # ACAD_SCALELIST dictionary
        objects += f"""  0
DICTIONARY
  5
B6
330
C
100
AcDbDictionary
281
     1
{scale_list_entries}"""

        # Add SCALE entities
        for cleaned in cleaned_scales:
            objects += cleaned

    # Add extension dictionary chains for annotative support
    if ext_dict_objects:
        objects += ext_dict_objects

    objects += "  0\nENDSEC"

    return objects


def main():
    parser = argparse.ArgumentParser(
        description='Create MULTILEADER labels using raw DXF text manipulation.'
    )
    parser.add_argument('input_dxf', nargs='?', default=None,
                       help='Source DXF file (optional if --template is provided)')
    parser.add_argument('decisions_json', help='JSON file with labeling decisions')
    parser.add_argument('--scale', type=float, default=20,
                       help='Annotative scale factor (default: 20)')
    parser.add_argument('--output', '-o', help='Output file path')
    parser.add_argument('--template', '-t',
                       help='Template DXF with annotative MULTILEADER (default: bundled template)')
    parser.add_argument('--no-annotative', action='store_true',
                       help='Disable annotative support (removes XDICTIONARY)')

    args = parser.parse_args()

    # Determine if we're in template-only mode (no source DXF)
    template_only_mode = args.input_dxf is None

    if template_only_mode:
        # Template-only mode: require --output since we have no input filename to derive from
        if not args.output:
            # Derive output from decisions_json filename
            decisions_base = Path(args.decisions_json).stem
            if decisions_base.endswith('-decisions'):
                decisions_base = decisions_base[:-10]  # Remove '-decisions' suffix
            args.output = decisions_base + '-LABELS.dxf'
            print(f"Template-only mode: output will be {args.output}", file=sys.stderr)
        input_path = None
    else:
        input_path = Path(args.input_dxf)
        if not input_path.exists():
            print(f"Error: Input file not found: {args.input_dxf}", file=sys.stderr)
            sys.exit(1)

    decisions_path = Path(args.decisions_json)
    if not decisions_path.exists():
        print(f"Error: Decisions file not found: {args.decisions_json}", file=sys.stderr)
        sys.exit(1)

    if args.output:
        output_path = Path(args.output)
    else:
        output_path = input_path.with_stem(input_path.stem + '-LABELS')

    try:
        # Load decisions
        with open(decisions_path, 'r') as f:
            decisions = json.load(f)

        # Read source DXF as text (or use template in template-only mode)
        if template_only_mode:
            print("Template-only mode: no source DXF", file=sys.stderr)
            dxf_content = None  # Will use template content below
        else:
            print(f"Reading source DXF: {input_path}", file=sys.stderr)
            dxf_content = read_dxf_as_text(str(input_path))

        # Find template MULTILEADER
        print("Finding MULTILEADER template...", file=sys.stderr)

        if not template_only_mode and dxf_content:
            template, metadata = find_multileader_template(dxf_content)
        else:
            # Template-only mode: will load from bundled template below
            template, metadata = None, None

        if not template or not metadata:
            if not template_only_mode:
                print("No MULTILEADER in source DXF, will use bundled template...", file=sys.stderr)

        if template and metadata:
            print(f"  Template handle: {metadata['handle']}", file=sys.stderr)
            print(f"  Template layer: {metadata['layer']}", file=sys.stderr)
            print(f"  Template scale: {metadata.get('scale', 'unknown')}", file=sys.stderr)
            print(f"  Arrow target: ({metadata['arrow_target']['x']:.2f}, {metadata['arrow_target']['y']:.2f})", file=sys.stderr)

        # Load template for annotative support if not disabled
        template_content = None
        ext_dict_chain = None
        scale_objects = None
        scale_handle = None

        if not args.no_annotative:
            # Determine template path
            if args.template:
                template_path = Path(args.template)
            else:
                # Use bundled template
                template_path = Path(__file__).parent.parent / 'templates' / 'mleader-template.dxf'

            if template_path.exists():
                print(f"\nLoading annotative template: {template_path}", file=sys.stderr)
                template_content = read_dxf_as_text(str(template_path))

                # Find template MULTILEADER in template file
                tpl_entity, tpl_metadata = find_multileader_template(template_content)
                if tpl_entity and tpl_metadata:
                    # Use template's MULTILEADER instead of source's
                    template = tpl_entity
                    metadata = tpl_metadata
                    print(f"  Using template MULTILEADER (handle: {metadata['handle']})", file=sys.stderr)

                    # Extract extension dictionary chain
                    ext_dict_chain = extract_extension_dict_chain(template_content, metadata['handle'])
                    if ext_dict_chain:
                        print(f"  Found extension dictionary chain for annotative support", file=sys.stderr)

                    # Extract scale objects
                    scale_objects = extract_scale_objects(template_content)
                    if scale_objects:
                        print(f"  Found {len(scale_objects)} scale objects: {list(scale_objects.keys())}", file=sys.stderr)

                    # Get scale handle for requested scale
                    scale_handle = get_scale_handle(scale_objects, int(args.scale))
                    if scale_handle:
                        print(f"  Using scale handle {scale_handle} for 1\"={int(args.scale)}'", file=sys.stderr)
                    else:
                        print(f"  Warning: No scale object for 1\"={int(args.scale)}', annotative may not work", file=sys.stderr)
            else:
                print(f"\nWarning: Template not found at {template_path}", file=sys.stderr)
                print("  Continuing without annotative support", file=sys.stderr)

        # Create labels
        entities = []
        ext_dict_objects = ""  # Combined extension dictionary objects for all entities
        handle_counter = 0x1000  # Start handles at 1000

        created_count = 0
        drafter_count = 0
        presentation_count = 0
        skipped_count = 0

        print(f"\nCreating labels at scale 1\"={args.scale}'...", file=sys.stderr)

        for label in decisions.get('labels', []):
            position = label.get('position')
            if not position:
                print(f"  Warning: No position for point {label.get('point_num')}", file=sys.stderr)
                skipped_count += 1
                continue

            text = label.get('label_text', '')
            if not text:
                skipped_count += 1
                continue

            label_type = label.get('type', 'presentation')

            if label_type == 'skip':
                skipped_count += 1
                continue

            if label_type == 'drafter':
                layer = '0'
                color = COLOR_RED
                drafter_count += 1
            else:
                layer = 'G-ANNO'
                color = COLOR_BYLAYER
                text = text.upper()  # ALL CAPS for presentation
                presentation_count += 1

            try:
                new_handle = generate_handle(handle_counter)
                handle_counter += 1

                # Clone extension dictionary chain for annotative support
                ext_dict_handle = None
                if ext_dict_chain and scale_handle:
                    dx = position['x'] - metadata['arrow_target']['x']
                    dy = position['y'] - metadata['arrow_target']['y']
                    dz = position.get('z', 0) - metadata['arrow_target'].get('z', 0)

                    ext_dict_handle, chain_objects, handle_counter = clone_extension_dict_chain(
                        chain=ext_dict_chain,
                        new_entity_handle=new_handle,
                        dx=dx, dy=dy, dz=dz,
                        new_text=text,
                        new_scale_handle=scale_handle,
                        handle_counter=handle_counter
                    )
                    ext_dict_objects += chain_objects

                entity = create_label_entity(
                    template=template,
                    metadata=metadata,
                    new_position=position,
                    new_text=text,
                    new_layer=layer,
                    new_color=color,
                    new_handle=new_handle,
                    scale=args.scale,
                    ext_dict_handle=ext_dict_handle
                )
                entities.append(entity)
                created_count += 1

                color_name = 'RED' if color == COLOR_RED else 'BYLAYER'
                annot_status = ' [annotative]' if ext_dict_handle else ''
                print(f"  Pt {label.get('point_num')}: '{text[:40]}' [{color_name}]{annot_status} -> {layer}", file=sys.stderr)
            except Exception as e:
                print(f"  Warning: Could not create label for Pt {label.get('point_num')}: {e}", file=sys.stderr)
                import traceback
                traceback.print_exc(file=sys.stderr)

        print(f"\nCreated {created_count} MULTILEADER labels:", file=sys.stderr)
        print(f"  - Presentation (G-ANNO): {presentation_count}", file=sys.stderr)
        print(f"  - Drafter (Layer 0, Red): {drafter_count}", file=sys.stderr)
        print(f"  - Skipped: {skipped_count}", file=sys.stderr)

        # Build output DXF
        print(f"\nBuilding output DXF...", file=sys.stderr)
        # In template-only mode, use template_content as the source for styles
        effective_source = dxf_content if dxf_content else template_content
        output_content = build_output_dxf(
            source_content=effective_source,
            entities=entities,
            source_path=input_path if input_path else output_path,
            template_metadata=metadata,
            ext_dict_objects=ext_dict_objects if ext_dict_objects else None,
            scale_objects=scale_objects,
            template_content=template_content
        )

        # Save output
        print(f"Saving to: {output_path}", file=sys.stderr)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(output_content)

        print("Done!", file=sys.stderr)

        # Output result as JSON for Claude to parse
        print(json.dumps({
            'success': True,
            'output_file': str(output_path.absolute()),
            'labels_created': created_count,
            'presentation_count': presentation_count,
            'drafter_count': drafter_count,
            'skipped_count': skipped_count,
            'labels_only': True
        }))

    except Exception as e:
        import traceback
        traceback.print_exc(file=sys.stderr)
        print(json.dumps({
            'success': False,
            'error': str(e)
        }))
        sys.exit(1)


if __name__ == '__main__':
    main()
