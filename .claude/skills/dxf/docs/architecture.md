# Survey Label MULTILEADER System Architecture

---

## Architecture Decision Record (ADR)

**Date:** January 2025
**Status:** Accepted
**Decision:** Remove ezdxf-based DXF creation; require AutoCAD for all MULTILEADER creation

### Context

We attempted to create annotative MULTILEADER entities using Python's ezdxf library. This approach failed in production.

### Problems Encountered with ezdxf Approach

1. **Copy/paste broken** - Ctrl+C/V fails on ezdxf-created MLEADERs
2. **XREF issues** - DXF files cannot be used as external references without conversion
3. **Annotative scaling broken** - Shows wrong scale (2.0 instead of 4.0 at 1"=40')
4. **Leader lines don't scale** - Only text responds to annotative scale
5. **Extension dictionaries incomplete** - 4-level nested structure not generated correctly
6. **Missing binary cache** - Group 310 proxy graphics only AutoCAD can generate

### Root Cause

From ezdxf GitHub Issue #840: **Annotative MULTILEADER entities require proxy graphics regeneration** that ezdxf cannot perform. The annotative feature is undocumented in the DXF specification.

### Decision

- **Remove** all Python scripts that create or modify DXF files via ezdxf
- **Require** AutoCAD/Civil 3D installation for MULTILEADER creation
- **Use** AcCoreConsole + AutoLISP for headless batch processing
- **Keep** read-only ezdxf utilities for analysis and data extraction

### Consequences

- Users must have AutoCAD/Civil 3D installed
- Labels are created via native MLEADER command (guaranteed compatibility)
- No fallback for systems without AutoCAD
- Simpler codebase (removed 8 unreliable scripts)

### Deleted Files

| File | Reason |
|------|--------|
| `create_labels.py` | Created MLEADERs via ezdxf |
| `label_dxf.py` | Created labels via ezdxf |
| `dxf_multileader.py` | Modified MLEADERs via ezdxf |
| `dxf_hatch.py` | Created hatches via ezdxf |
| `dxf_blocks.py` | Modified blocks via ezdxf |
| `dxf_layers.py` | Modified layers via ezdxf |
| `dxf_modify.py` | Modified entities via ezdxf |
| `dxf_text.py` | Modified text via ezdxf |
| `mleader-template.dxf` | DXF template (using DWG now) |

---

## Problem Statement

The DXF-based approach to creating MULTILEADER entities has critical compatibility issues in AutoCAD:

1. **Cannot copy with Ctrl+C** - Copy/paste operations fail
2. **Cannot XREF DXF** - Must convert to DWG first for external references
3. **Annotative scaling broken** - Shows 2.0 instead of 4.0 model units at 1"=40'
4. **Leader lines don't scale** - Only text scales, leader remains fixed

### Technical Root Cause

The required elements that cannot be programmatically generated:
- **Proxy graphics (group 310)** - Binary data that AutoCAD regenerates internally
- **Extension dictionary chains** - 4-level nested structure for annotation scales
- **Context data synchronization** - MULTILEADER data must match ACDB_MLEADEROBJECTCONTEXTDATA_CLASS

No amount of DXF manipulation can produce entities that behave identically to native AutoCAD-created MLEADERs.

---

## Solution Architecture

### Key Insight

All users have Civil 3D (AutoCAD) installed. Instead of fighting the DXF format, we use AutoCAD directly via AcCoreConsole.

### Architecture

```
CSV (PNEZD) -> Claude Code -> decisions.json -> Python -> labels.csv -> AutoLISP -> OUTPUT.dwg
              (analysis)                      (convert)               (native)    (works!)
```

This approach uses AutoCAD's native MLEADER command, guaranteeing full compatibility.

### Separation of Concerns

| Component | Owner | Why |
|-----------|-------|-----|
| CSV parsing | Python | Fast, reliable, no CAD needed |
| Semantic analysis | Claude | AI excels at understanding "MISC/DRAIN ONE ST SW COR TOO" |
| Decision JSON | Python | Data interchange format |
| JSON to CSV | Python | LISP can easily parse CSV (native string ops) |
| MULTILEADER creation | AutoLISP | Native AutoCAD = guaranteed compatibility |
| Output format | DWG | Binary format, full fidelity |

---

## Data Flow

```
decisions.json -> Python -> labels.csv -> AutoLISP -> output.dwg
                    |
              (convert JSON to CSV)
```

### CSV Format for LISP

```csv
Point#,X,Y,Z,Label_Text,Type,Layer,Color
10,1614648.059,1147609.723,3508.736,CP 10,presentation,G-ANNO,256
2001,1615076.699,1147651.484,3509.052,RIM ELEV = 3509.05',presentation,G-ANNO,256
2001,1615076.699,1147651.484,3509.052,center of cover,drafter,0,1
```

### Why CSV Instead of JSON?

- AutoLISP has no native JSON parser
- CSV parsing is trivial with string operations
- Clear, human-readable format
- Easy to verify/debug

---

## File Structure

```
~/.claude/skills/dxf/
├── scripts/
│   ├── create_mleaders.lsp       # AutoLISP MULTILEADER generator
│   ├── create_labels_dwg.py      # Python wrapper for AcCoreConsole
│   ├── write_decisions_csv.py    # Export decisions to CSV for review
│   ├── parse_csv_pnezd.py        # Parse PNEZD CSV to JSON
│   ├── dxf_analyze.py            # Read-only: DXF structure analysis
│   ├── dxf_query.py              # Read-only: Query entities
│   ├── dxf_cogo.py               # Read-only: Extract COGO points
│   └── extract_points.py         # Read-only: Extract points from DXF
├── templates/
│   └── mleader-template.dwg      # DWG template with MLEADERSTYLE
├── docs/
│   ├── architecture.md           # This document
│   └── troubleshooting.md        # Troubleshooting guide
└── references/
    ├── entity-patterns.md        # ezdxf query patterns
    ├── layer-conventions.md      # Civil 3D layer naming
    └── multileader-structure.md  # MULTILEADER technical docs
```

---

## Component Details

### create_mleaders.lsp

AutoLISP script that:
1. Reads CSV file with label data
2. Creates MULTILEADER entities using the native `MLEADER` command
3. Sets layer and color per label type
4. Writes log file for status tracking

Key functions:
- `c:CREATE-MLEADERS` - Main command (interactive or from path)
- `c:MLEADER-BATCH` - Batch mode for AcCoreConsole

### create_labels_dwg.py

Python wrapper that:
1. Converts decisions.json to CSV format
2. Creates AcCoreConsole script file
3. Runs AcCoreConsole with template DWG
4. Falls back to manual script if AcCoreConsole unavailable

AcCoreConsole path search order:
1. `C:\Program Files\Autodesk\AutoCAD 2025\accoreconsole.exe`
2. `C:\Program Files\Autodesk\AutoCAD 2024\accoreconsole.exe`
3. `C:\Program Files\Autodesk\AutoCAD 2023\accoreconsole.exe`

### Template Files

The template provides:
- Pre-configured MLEADERSTYLE "Annotative-Simplex"
- Annotation scales (1"=20', 1"=40', etc.)
- Required text styles
- Layer definitions (G-ANNO, 0)

**Important**: Template DWG is preferred over DXF because:
- Preserves all proxy graphics and internal state
- Smaller file size (compressed)
- No round-trip conversion needed

---

## Fallback Strategy

### If AcCoreConsole Not Available

The Python wrapper generates a manual script:
- `<basename>-labels.csv` - Label data
- `<basename>-LABELS.scr` - Script with instructions

User follows manual steps in AutoCAD interactively.

### If AutoCAD Not Installed

**No fallback available.** AutoCAD/Civil 3D is required for MULTILEADER creation.

The ezdxf-based DXF approach was removed because it produced unreliable results (see ADR above).

---

## Verification Checklist

After creating labels with DWG approach, verify in Civil 3D:

- [ ] All MLEADERs visible at correct positions
- [ ] Ctrl+C copy works
- [ ] XREF works (attach to new drawing)
- [ ] At 1"=40' scale, text height = 4.0 model units (0.10" paper x 40)
- [ ] Layer assignment correct (G-ANNO vs 0)
- [ ] Color correct (ByLayer vs RED)
- [ ] Leader lines scale with annotative text

---

## References

- [ezdxf GitHub Issue #840](https://github.com/mozman/ezdxf/issues/840) - Annotative MULTILEADER limitations
- [AcCoreConsole documentation](https://help.autodesk.com/view/ACD/2024/ENU/?guid=GUID-0C7A4B64-B0B3-4F22-B4C6-80E8881F3CE0)
- [AutoLISP MLEADER command](https://help.autodesk.com/view/ACD/2024/ENU/?guid=GUID-1A9B0638-8EA0-4FD3-8F76-4B1D3A7B9DE0)

---

## GitHub Issue

Tracking: https://github.com/RH-StahlyEngineering/RH-Stahly_Claude_Toolkit/issues/1
