---
name: dxf
description: DXF file analysis and survey point labeling for Civil 3D. Requires AutoCAD/Civil 3D for MULTILEADER creation. Use when users need to analyze DXF files, extract COGO points, query entities, or create survey point labels via AutoCAD.
---

# DXF Analysis & Survey Labeling Skill

Analyze AutoCAD DXF files and create survey point labels via AutoCAD/Civil 3D.

## Why AutoCAD is Required

Creating annotative MULTILEADER entities via Python (ezdxf) produces unreliable results:
- Copy/paste fails, XREF doesn't work, scaling breaks
- Root cause: Undocumented proxy graphics that only AutoCAD can generate

**Solution:** All label creation uses AutoCAD's native MLEADER command via AcCoreConsole.
See [docs/architecture.md](docs/architecture.md) for full rationale.

## Quick Start

```bash
# Analyze DXF structure
python scripts/dxf_analyze.py drawing.dxf

# Extract survey points
python scripts/dxf_cogo.py drawing.dxf --layer "V-*"

# Query entities
python scripts/dxf_query.py drawing.dxf --layer "V-STRM-*"

# Label survey points from CSV (PNEZD format) - requires AutoCAD
python scripts/parse_csv_pnezd.py points.csv > points.json
# (Claude analyzes points and creates decisions.json)
python scripts/create_labels_dwg.py decisions.json --scale 40 --output labeled.dwg
```

## Available Scripts

### Label Creation (requires AutoCAD/Civil 3D)

| Script | Purpose |
|--------|---------|
| `parse_csv_pnezd.py` | Parse CSV files in PNEZD format to JSON |
| `create_labels_dwg.py` | Create MLEADERs via AutoCAD (AcCoreConsole) |
| `write_decisions_csv.py` | Export decisions JSON to CSV for review |
| `create_mleaders.lsp` | AutoLISP script (called by create_labels_dwg.py) |

### Read-Only Analysis (no AutoCAD required)

| Script | Purpose |
|--------|---------|
| `dxf_analyze.py` | Structure analysis, entity/layer statistics, extents |
| `dxf_cogo.py` | Extract COGO points (INSERT entities on survey layers) |
| `dxf_query.py` | Query by layer pattern, type, bbox, handle, proximity |
| `extract_points.py` | Extract survey points from DXF blocks |

Run any script with `--help` for full options.

## Key Concepts

### Scale Relationship
`model_height = paper_height * scale_factor`

For 1"=40' scale, text height 0.10" paper = 4.0 model units.

### Layer Conventions
Civil 3D survey layers follow `V-*` naming. See [references/layer-conventions.md](references/layer-conventions.md) for patterns.

### Reference Documentation
- [references/entity-patterns.md](references/entity-patterns.md) - ezdxf query patterns
- [references/multileader-structure.md](references/multileader-structure.md) - MULTILEADER technical details
- [docs/architecture.md](docs/architecture.md) - Why AutoCAD is required

## Survey Point Labeling

### Workflow (requires AutoCAD/Civil 3D)

```bash
# 1. Parse CSV to JSON (filters for "/" in description)
python scripts/parse_csv_pnezd.py points.csv

# 2. Claude analyzes points and creates decisions.json with labeling decisions

# 3. Create labels via AutoCAD
python scripts/create_labels_dwg.py decisions.json --scale 40 --output labeled.dwg
```

### Options
- `--scale N`: Scale factor (default: 40 for 1"=40') - multiplies paper-space dimensions
- `--output PATH`: Custom output file path (default: adds "-LABELS" suffix)

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
| "Find entities near this coordinate" | Run `dxf_query.py near --x X --y Y` |
| "Label points from CSV file" | Run `parse_csv_pnezd.py`, analyze, then `create_labels_dwg.py` |

## Requirements

```bash
pip install ezdxf  # For read-only analysis scripts
```

**For label creation:** AutoCAD or Civil 3D must be installed (uses AcCoreConsole)

## Limitations

- **Label creation**: Requires AutoCAD/Civil 3D (AcCoreConsole)
- **DXF analysis**: Read-only via ezdxf (cannot create/modify DXF reliably)
- No rendering/visualization
- Civil 3D proxy objects (AECC_*) stored but not interpreted
