# ezdxf Entity Access Patterns

Quick reference for accessing DXF entities with ezdxf.

## Entity Query Patterns

| Entity | Query | Key Attributes |
|--------|-------|----------------|
| INSERT | `msp.query('INSERT')` | `.dxf.name`, `.dxf.insert`, `.dxf.layer`, `.attribs` |
| POLYLINE | `msp.query('POLYLINE')` | `.vertices`, `.is_closed` |
| LWPOLYLINE | `msp.query('LWPOLYLINE')` | `.get_points()`, `.dxf.elevation`, `.is_closed` |
| LINE | `msp.query('LINE')` | `.dxf.start`, `.dxf.end` |
| TEXT | `msp.query('TEXT')` | `.dxf.text`, `.dxf.height`, `.dxf.insert` |
| MTEXT | `msp.query('MTEXT')` | `.text`, `.dxf.char_height` |
| MULTILEADER | `msp.query('MULTILEADER')` | `.context.mtext.text`, `.context.leaders` |

## DXF File Sections

Sections appear in this order:
1. **HEADER** - System variables ($ACADVER, $LUNITS, etc.)
2. **CLASSES** - Custom object definitions (AECC_* for Civil 3D)
3. **TABLES** - LAYER, LTYPE, STYLE, DIMSTYLE, BLOCK_RECORD
4. **BLOCKS** - Block geometry definitions
5. **ENTITIES** - Model space geometry
6. **OBJECTS** - Dictionaries, layouts, non-graphical objects

## Scale Relationship

```
model_height = paper_height * scale_factor
```

For 1"=20' scale: `scale_factor = 20`

Example: 0.1" text at 1"=20' has model height of `0.1 * 20 = 2.0` units

## Multileader Text Conventions

- Line breaks: `\P` delimiter
- Typical utility label format: `DESCRIPTION\PRIM=elev'\PINV (dir)=elev'`

## Common Operations

### Read file
```python
doc = ezdxf.readfile(filepath)
msp = doc.modelspace()
```

### Save changes
```python
doc.saveas(output_path)
```

### Layer pattern matching
```python
from fnmatch import fnmatch
for entity in msp:
    if fnmatch(entity.dxf.layer, 'V-*'):
        # process entity
```
