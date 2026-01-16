# DXF Structure Errors Reference

Common DXF errors encountered when writing Python scripts that generate or modify DXF files. Use this as a checklist when debugging DXF output issues.

## Handle Errors

### `eHandleInUse` / "Bad handle X: already in use"
**Cause**: Two or more entities share the same handle (group code 5).

**Fix**: Every entity in a DXF must have a unique hexadecimal handle. When creating entities programmatically:
- Use a counter starting high (e.g., `0x1000`) to avoid collisions with table entries
- Track all used handles and increment for each new entity
- Remember that BLOCK_RECORD entries have handles, and BLOCK/ENDBLK entities need DIFFERENT handles

**Example of conflict**:
```
BLOCK_RECORD handle: 1F
BLOCK handle: 1F      ← WRONG! Must be different, e.g., 30
ENDBLK handle: 1F     ← WRONG! Must be different, e.g., 31
```

**Correct pattern**:
```
BLOCK_RECORD
  5
1F                    ← Record handle
...
BLOCK
  5
30                    ← Block begin handle (different!)
330
1F                    ← Owner handle (points to record)
...
ENDBLK
  5
31                    ← Block end handle (different!)
330
1F                    ← Owner handle (points to record)
```

## Table Errors

### "Error in LTYPE Table - Linetype name with vertical bar"
**Cause**: Xref-dependent linetypes (containing `|` in names like `XREF|Continuous`) copied from source DXF.

**Fix**: Filter out any table entries where the name (group code 2) contains `|`:
- LTYPE entries
- LAYER entries
- STYLE entries
- DIMSTYLE entries
- BLOCK_RECORD entries

**Or**: Use minimal tables instead of copying from source files.

### "Error in APPID Table"
**Cause**: Missing required APPID entries or malformed APPID table structure.

**Fix**: Always include at minimum:
```
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
```

## Required DXF Tables

A valid DXF file requires these tables in the TABLES section (in order):
1. VPORT
2. LTYPE (must include ByBlock, ByLayer, Continuous)
3. LAYER (must include layer 0)
4. STYLE
5. VIEW
6. UCS
7. APPID (must include ACAD)
8. DIMSTYLE
9. BLOCK_RECORD (must include *Model_Space, *Paper_Space)

## Required Blocks

The BLOCKS section must include matching blocks for BLOCK_RECORD entries:
- `*Model_Space` block with BLOCK and ENDBLK
- `*Paper_Space` block with BLOCK and ENDBLK

## OBJECTS Section Errors

### "File lacks the NamedObject dictionary" / "Invalid or incomplete DXF input -- drawing discarded"

**Cause**: The OBJECTS section is missing or malformed. This is the most severe DXF structure error - AutoCAD will completely reject the file.

The OBJECTS section stores all **non-graphical objects** in a DXF (R13+) and is REQUIRED. The most critical element is the **NamedObject dictionary** (root dictionary), which must:
1. Be the **first object** in the OBJECTS section
2. Have owner handle **0** (group 330 = 0)
3. Contain at least an **ACAD_GROUP** entry

**Common causes**:
- OBJECTS section completely missing from output DXF
- Typo in section name (e.g., "OBJECKTS" instead of "OBJECTS")
- Root dictionary not first in section
- Root dictionary has wrong owner (must be 0)
- Missing ACAD_GROUP entry in root dictionary

**Fix**: Always include a minimal OBJECTS section:
```
  0
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
ENDSEC
```

**Key structure requirements**:
| Group Code | Purpose | Required Value |
|------------|---------|----------------|
| 0 | Entity type | DICTIONARY |
| 5 | Handle | Unique hex (e.g., C) |
| 330 | Owner handle | **0** for root dictionary |
| 100 | Subclass | AcDbDictionary |
| 281 | Clone flag | 1 (keep existing) |
| 3 | Entry name | ACAD_GROUP (required) |
| 350 | Entry handle | Points to ACAD_GROUP dictionary |

**Debugging**:
1. Open output DXF in text editor
2. Search for "OBJECTS" - verify section exists and is spelled correctly
3. First entity after `SECTION/2/OBJECTS` must be `0/DICTIONARY`
4. First dictionary must have `330/0` (owner is 0)
5. Must contain entry `3/ACAD_GROUP` with valid `350` handle reference

**Using ezdxf**: The library automatically manages the OBJECTS section:
```python
import ezdxf
doc = ezdxf.new('R2010')
# Root dictionary created automatically
doc.saveas('output.dxf')  # OBJECTS section properly structured
```

**Recovery**: If you have a corrupt file, try:
```python
from ezdxf import recover
doc, auditor = recover.readfile('corrupted.dxf')
auditor.print_error_report()
```

## Group Code Errors

### "DXF read error on line X"
**Cause**: Often a malformed group code/value pair. Common issues:

1. **Missing newline between group code and value**
   ```
   Wrong: 304CP 10
   Right: 304
          CP 10
   ```

2. **Negative group codes appearing unexpectedly**
   - Group codes should be positive integers (0-1071)
   - If you see `-417` or similar, text replacement corrupted a group code

3. **Wrong data type for group code**
   - Coordinates (10, 20, 30, etc.) expect floating point
   - Handles (5, 105) expect hex strings
   - Flags (70, 90, etc.) expect integers

### Text Content Corruption
**Cause**: When replacing text content (group 304), regex may accidentally match and corrupt nearby group codes.

**Critical Bug**: If you replace text BEFORE offsetting coordinates, text like "CP 10" will contain " 10\n" which matches coordinate offset patterns for group 10!

**Fix**: Always do text replacement LAST, after all coordinate modifications:
```python
# WRONG ORDER - text "CP 10" gets corrupted by coordinate offset
entity = replace_text(entity, "CP 10")  # Now contains " 10\n"
entity = offset_coordinates(entity)      # Matches " 10\n" in text!

# CORRECT ORDER - coordinates offset first, then text replaced
entity = offset_coordinates(entity)      # Original text doesn't match
entity = replace_text(entity, "CP 10")   # Safe to add text with numbers
```

**Also**: Be precise with regex patterns:
```python
# WRONG - too greedy, may match group codes
entity = re.sub(r'304\n[^\n]+\n', f'304\n{new_text}\n', entity)

# BETTER - check context or use more specific patterns
def replace_text(m):
    if 'LEADER' in m.group(0):  # Skip LEADER_LINE{ markers
        return m.group(0)
    return f'304\n{new_text}\n'
entity = re.sub(r'304\n[^\n]+\n', replace_text, entity, count=1)
```

## Coordinate Group Codes

When offsetting coordinates, ensure you handle ALL related groups:

| Purpose | X | Y | Z |
|---------|---|---|---|
| Points/Vertices | 10 | 20 | 30 |
| Other points | 11 | 21 | 31 |
| Text insertion | 12 | 22 | 32 |
| Direction vectors | 13 | 23 | 33 |
| Block reference | 110 | 120 | 130 |
| Block X-axis | 111 | 121 | 131 |
| Block Y-axis | 112 | 122 | 132 |

**Warning**: Don't offset direction vectors (11/21/31, 13/23/33, 111/121/131, 112/122/132) - these are unit vectors, not positions!

## MULTILEADER Rendering Issues

### MULTILEADERs exist but are invisible (selectable but no visual)

**Symptoms**:
- Ctrl+A highlights the entities
- ZOOM EXTENTS doesn't find them
- No text, leaders, or arrowheads visible
- Properties palette shows they exist

**Primary Cause**: Missing MLEADERSTYLE definition in OBJECTS section.

MULTILEADER entities reference an MLEADERSTYLE via group code 340. If the referenced style handle doesn't exist in the file's OBJECTS section, the entity cannot render.

**Fix**: Copy MLEADERSTYLE entities from source file to output OBJECTS section:

```python
def extract_mleaderstyles(dxf_content):
    """Extract MLEADERSTYLE entities from OBJECTS section."""
    styles = []
    pattern = r'(  0\nMLEADERSTYLE\n  5\n([0-9A-Fa-f]+)\n.*?)(?=  0\n[A-Z])'
    for match in re.finditer(pattern, dxf_content, re.DOTALL):
        styles.append(match.group(1))
    return styles
```

**Key MLEADERSTYLE references in MULTILEADER**:
| Group Code | Purpose |
|------------|---------|
| 340 | MLEADERSTYLE handle (after AcDbMLeader) |
| 343 | Text style handle |
| 344 | Block record handle (for block content) |

**Secondary Causes**:
- `leader_type` (group 170) = 0 (None) - leaders won't render
- `content_type` (group 172) = 0 (None) - content won't render
- Invalid plane vectors (groups 110, 111, 112) - all zeros
- Missing text style (group 343 points to non-existent STYLE)

**Debugging**:
1. Check group 340 in MULTILEADER - what handle does it reference?
2. Search OBJECTS section for `MLEADERSTYLE` with that handle
3. If missing, copy the style from source file
4. Also verify the ACAD_MLEADERSTYLE dictionary contains the style entry

## Binary Data (Group 310)

### MULTILEADER Binary Cache
MULTILEADER entities contain binary data in group 310 that caches rendering information. This data:
- Contains encoded coordinates and text
- Is regenerated by AutoCAD when inconsistent with CONTEXT_DATA
- Can be safely removed - AutoCAD will regenerate it

**Fix for MULTILEADER issues**: Remove all 310 groups and let AutoCAD regenerate:
```python
entity = re.sub(r'160\n[^\n]+\n(310\n[^\n]+\n)+', '160\n0\n', entity)
```

## Entity Owner References

### Group 330 (Owner Handle)
Entities should reference their owner (usually modelspace or a block):
```
330
1F     ← Handle of owner (e.g., *Model_Space block record)
```

If the owner handle doesn't exist, AutoCAD may reject the file.

## Debugging Tips

1. **Compare with working DXF**: Open a known-good DXF as text and compare structure
2. **Use line numbers**: DXF errors report line numbers - examine that exact location
3. **Check around the error**: Often the actual problem is a few lines before the reported line
4. **Validate incrementally**: Test with 1 entity before scaling to many
5. **Use ezdxf for reading**: Even if you write raw DXF, use `ezdxf.readfile()` to validate:
   ```python
   import ezdxf
   try:
       doc = ezdxf.readfile('output.dxf')
       print("Valid DXF")
   except Exception as e:
       print(f"Invalid: {e}")
   ```

## Safe Minimal DXF Template

When in doubt, generate a minimal DXF with:
- All required tables (even if empty)
- Unique handles starting from 0x100 for tables, 0x1000 for entities
- Only essential table entries (layer 0, ByLayer/ByBlock/Continuous linetypes, ACAD appid)
- *Model_Space and *Paper_Space blocks
- **OBJECTS section with root dictionary** (ACAD_GROUP entry required)

**Required section order**:
1. HEADER
2. CLASSES
3. TABLES
4. BLOCKS
5. ENTITIES
6. **OBJECTS** (often forgotten - causes "File lacks NamedObject dictionary" error!)
7. EOF

Avoid copying sections from complex source files - they often contain xref-dependent or application-specific entries that cause errors in standalone files.
