---
name: dxf
description: DXF file manipulation for Civil 3D survey drawings using ezdxf. Use when users need to read, analyze, or modify DXF files including extracting COGO points, editing text/multileaders, rescaling text, flattening entities, creating hatches, labeling survey points, or querying entities. Responds to natural language prompts about DXF operations.
---

# DXF Manipulation Skill

Manipulate AutoCAD DXF files for Civil 3D survey workflows using Python's ezdxf library.

## Quick Start

```bash
# Analyze structure
python scripts/dxf_analyze.py drawing.dxf

# Extract survey points
python scripts/dxf_cogo.py drawing.dxf --layer "V-*"

# Label survey points from CSV (PNEZD format)
python scripts/parse_csv_pnezd.py points.csv > points.json
# (analyze points and create decisions.json)
python scripts/create_labels.py decisions.json --scale 40 --output labeled.dxf

# Label survey points from DXF (1"=40' scale)
python scripts/label_dxf.py drawing.dxf --scale 40

# Rescale text (1"=20' to 1"=40')
python scripts/dxf_text.py rescale drawing.dxf --old-scale 20 --new-scale 40 --output scaled.dxf

# Flatten contours to Z=0
python scripts/dxf_modify.py flatten drawing.dxf --layer "V-TINN" --output flat.dxf

# Hatch closed polylines
python scripts/dxf_hatch.py hatch-all drawing.dxf --layer "V-*" --output hatched.dxf
```

## Available Scripts

| Script | Purpose |
|--------|---------|
| `dxf_analyze.py` | Structure analysis, entity/layer statistics, extents |
| `dxf_cogo.py` | Extract COGO points (INSERT entities on survey layers) |
| `dxf_text.py` | List, edit, rescale TEXT/MTEXT/MULTILEADER |
| `dxf_multileader.py` | List, find, edit multileaders |
| `dxf_modify.py` | Flatten entities, move between layers, delete |
| `dxf_hatch.py` | Find closed polylines, create hatches |
| `dxf_layers.py` | List, create, modify, delete layers |
| `dxf_blocks.py` | List blocks, insert references, explode |
| `dxf_query.py` | Query by layer pattern, type, bbox, handle, proximity |
| `label_dxf.py` | Auto-label survey points with MULTILEADER annotations |
| `parse_csv_pnezd.py` | Parse CSV files in PNEZD format to JSON |
| `create_labels.py` | Create MULTILEADER labels from decisions JSON |

Run any script with `--help` for full options.

## Key Concepts

### File Safety
All modification scripts save to a new output file. Original files are never overwritten.

### Scale Relationship
`model_height = paper_height * scale_factor`

When rescaling from 1"=20' to 1"=40', use `--old-scale 20 --new-scale 40`.

### Layer Conventions
Civil 3D survey layers follow `V-*` naming. See [references/layer-conventions.md](references/layer-conventions.md) for patterns.

### Entity Access
See [references/entity-patterns.md](references/entity-patterns.md) for ezdxf query patterns.

## Survey Point Labeling

### From CSV (PNEZD Format)

Parse CSV files with Point, Northing, Easting, Elevation, Description columns:

```bash
# Parse CSV to JSON (filters for "/" in description)
python scripts/parse_csv_pnezd.py points.csv

# Create labels (template-only mode - no source DXF needed)
python scripts/create_labels.py decisions.json --scale 40 --output labeled.dxf
```

### From DXF

The `label_dxf.py` script creates MULTILEADER annotations for survey points with "/" in descriptions.

### Usage
```bash
python scripts/label_dxf.py survey.dxf --scale 20
python scripts/label_dxf.py survey.dxf --scale 40 --hatch-buildings
python scripts/label_dxf.py input.dxf --output labeled_output.dxf
```

### Options
- `--scale N`: Scale factor (default: 20 for 1"=20') - multiplies paper-space dimensions
- `--output PATH`: Custom output file path (default: adds "-LABELS" suffix)
- `--hatch-buildings`: Hatch building footprints on EOB layers

### Color Classification
- **ByLayer (Deliverable):** Control points (CP), FFB with location info, CB (Corner of Building)
- **Red (Drafter Notes):** Instructions (NO HZ, EL ONLY), positioning notes, MISC points

### Label Types
| Type | Pattern | Example Label |
|------|---------|---------------|
| Control Point | `CP/*` | "CP 10" |
| Finished Floor | `FFB/*` | "FFB ELEV: 3510.96" |
| Corner of Building | `CB/*` | "CB" or "CHIM" |
| Other | `CODE/*` | First code before "/" |

## Natural Language Examples

| User Request | Action |
|--------------|--------|
| "What's in this DXF?" | Run `dxf_analyze.py` |
| "List the storm drain points" | Run `dxf_cogo.py --layer "V-STRM-*"` |
| "Change scale from 20 to 40" | Run `dxf_text.py rescale --old-scale 20 --new-scale 40` |
| "Flatten the contour polylines" | Run `dxf_modify.py flatten --layer "V-TINN"` |
| "Edit the label near X, Y" | Run `dxf_multileader.py find --x X --y Y`, then `edit` |
| "Hatch all closed polylines on layer X" | Run `dxf_hatch.py hatch-all --layer X` |
| "Find entities near this coordinate" | Run `dxf_query.py near --x X --y Y` |
| "Label the survey points at 40 scale" | Run `label_dxf.py drawing.dxf --scale 40` |
| "Label points from CSV file" | Run `parse_csv_pnezd.py`, analyze, then `create_labels.py` |

## Requirements

```bash
pip install ezdxf
```

## Limitations

- DXF only (no DWG)
- No rendering/visualization
- Civil 3D proxy objects (AECC_*) stored but not interpreted
