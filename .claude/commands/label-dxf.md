---
description: Label survey points from CSV (PNEZD format) with MULTILEADER annotations
argument-hint: <csv-path> [--scale N] [--from-csv <decisions.csv>]
allowed-tools: Bash(python:*), Read, Write
---

<objective>
Create MULTILEADER annotations for survey points from PNEZD CSV files at `$ARGUMENTS`.
Every point with "/" in the description MUST produce at least one label. No silent skipping.
</objective>

<context>
Survey data in PNEZD format: Point, Northing, Easting, Elevation, Description.
Points with "/" in description have CODE/COMMENT structure (e.g., "MISC/DRAIN", "SDI/CNTR COVER").
The CODE identifies the feature type (often shown by point style in CAD).
The COMMENT provides additional context that needs intelligent analysis.
</context>

<cardinal_rules>
These rules are MANDATORY and must be followed for every point.

<rule_1_no_skipping>
## Rule 1: All Slashed Points Get Labeled (MANDATORY)
Every point with "/" MUST produce at least one label.
- **NO SKIPPING** except TC/TD (trees) and CO (cleanouts) when not notable
- When in doubt, produce BOTH presentation AND drafter labels
- MISC points are NEVER skipped - they always serve a purpose
</rule_1_no_skipping>

<rule_2_ddie>
## Rule 2: DDIE (Duplicate-Descriptor-In-Error)
**Never label what the point style already shows.**
- EBOX already displays as electric box → do NOT label "ELEC BOX"
- SDI already displays as storm drain inlet → do NOT label "STORM DRAIN"
- Instead, analyze the COMMENT for its actual purpose
</rule_2_ddie>

<rule_3_comment_purpose>
## Rule 3: Don't-Be-Dumb (Comment Purpose Analysis)
Understand WHY each comment exists. Comments serve different purposes:

| Comment Type | Examples | Label Type | Format |
|--------------|----------|------------|--------|
| Location descriptor | CNTR, APPROX, SW COR, ON SIDE OF | Drafter | Plain language, lowercase |
| Feature identifier | DRAIN, HVAC, GB | Presentation | ALL CAPS |
| Drafting instruction | CONNECT TO, NORTH ONLY, EL ONLY | Drafter | As written or plain language |
| Measurement context | RIM @, COVER @, APPROX CNTR STRUCT | Drafter | Plain language explanation |

**Example Analysis:** `SDI/CNTR COVER @ APPROX CNTR STRUCT`
- CODE: SDI (storm drain inlet) → already has point style, don't duplicate
- COMMENT purpose: Describes WHERE the shot was taken (center of cover, approximately center of structure)
- **Presentation**: `RIM ELEV = 3509.05'` (the critical measurement)
- **Drafter**: "Approximately the center of the structure" (location context)
</rule_3_comment_purpose>

<rule_4_misc_never_skip>
## Rule 4: MISC Never Skipped
MISC codes ALWAYS have a comment and ALWAYS serve a purpose.
- Never skip MISC points
- When uncertain, err toward drafter (flags manual review)
- Don't skip "duplicate" MISC points - they may show extents of an object (e.g., multiple HVAC shots)
</rule_4_misc_never_skip>

<rule_5_dual_labels>
## Rule 5: Dual-Label Rule
Many points need BOTH presentation AND drafter labels:
- **Presentation**: What the end user needs to see (elevation, feature ID) - Layer G-ANNO, ByLayer, ALL CAPS
- **Drafter**: What the CAD technician needs to know (location context, instructions) - Layer 0, RED, lowercase
Each label serves a distinct purpose. When in doubt, create both.
</rule_5_dual_labels>

<rule_6_invalid_elevation>
## Rule 6: Invalid Elevation Override
**Survey qualifiers indicating missing elevation data override elevation-based labels.**

When a comment contains these qualifiers, the Z coordinate is INVALID - do NOT create elevation labels:
- `HZ ONLY`, `HORIZ ONLY` - horizontal only, no vertical
- `NO EL`, `NO ELEV`, `NO Z`, `NO VERT` - explicit no elevation
- `XY ONLY` - position only

**Applies to ALL codes that would normally trigger elevation labels:**
- FFB → do NOT create `FFB = {elev}'`
- SDI, CB, MHSS, MHSD, MH* → do NOT create `RIM ELEV = {elev}'`
- Any other elevation-dependent label

**Instead, create:**
- **Drafter note**: Plain language explanation (e.g., "horizontal only - no elevation")
- **Presentation (optional)**: If the comment has other notable info, label that

**Examples:**
- `MHSS/HZ ONLY` → ❌ `RIM ELEV = 0.00'` | ✅ Drafter: "horizontal only - no elevation"
- `FFB/GYM HZ ONLY` → ❌ `FFB = 0.00'` | ✅ Drafter: "gym, horizontal only - no elevation"
- `SDI/CNTR COVER NO EL` → ❌ `RIM ELEV` | ✅ Drafter: "center of cover, no elevation"
</rule_6_invalid_elevation>
</cardinal_rules>

<code_specific_rules>
## Code-Specific Label Formatting

### FFB (Finished Floor of Building)
Elevation is the critical attribute.
- **Presentation**: `FFB = {elevation}'` (e.g., `FFB = 3510.96'`)
- **Drafter**: Plain-language from comment (e.g., "gym", "outside of door")

### Structure Codes (SDI, CB, MHSS, MHSD, MH*, MHE, MHC, MHW)
All drainage structures get rim elevation labels.
- **Presentation**: `RIM ELEV = {elevation}'` (use Z coordinate, format to 2 decimal places)
- **Drafter**: Plain-language interpretation of location comment

### CP (Control Point)
- **Presentation**: `CP {point_num}` (e.g., `CP 10`)
- No drafter note needed (description is for monument record, not CAD)

### EBOX, TPED, TVPED, EPED (Utility Pedestals/Boxes)
Point style already identifies feature type - do NOT duplicate.
- Analyze COMMENT purpose:
  - Location descriptor (ON SIDE OF, CNTR) → Drafter note
  - Provider/type (AT&T, CHARTER) → Presentation label

### BH (Bore Hole)
- **Presentation**: Bore ID from comment (e.g., "BH-1", "BORE 3")

### SL, Signs
- **Presentation**: Sign type from comment (e.g., "STOP", "YIELD")

### WELL, MW (Monitoring Well)
- **Presentation**: Well ID from comment (e.g., "MW-3")

### FH, WV, GV (Fire Hydrant, Water Valve, Gas Valve)
- **Presentation**: Type + relevant details from comment

### TC, TD (Trees)
- Skip unless comment indicates something notable
- If notable, create presentation label with species/size

### CO (Cleanout)
- Skip unless comment indicates something notable
- If notable, create presentation label

### MISC (Miscellaneous)
Full semantic analysis required - NEVER skip.
- Feature identifier in comment → Presentation (ALL CAPS)
- Location/context in comment → Drafter (lowercase)
- Often needs BOTH labels

### Monuments (QF, SCF, BM, RM, etc.)
- **Presentation**: Natural language description per MT ARM 24.183.1101

### Empty after "/"
- **Presentation**: `UNKNOWN` (flag for review)
</code_specific_rules>

<workflow>
## Workflow

### Step 1: Parse CSV
Run the parsing script to extract points with "/" in their description:

```bash
python ~/.claude/skills/dxf/scripts/parse_csv_pnezd.py <csv-path>
```

**If this fails, STOP IMMEDIATELY. Analyze the error, explain it to the user, suggest a fix, and tell them to reprompt.**

### Step 2: Analyze Each Point
For each extracted point, apply the cardinal rules:

1. **Identify CODE** (before "/") - determines base handling rules
2. **Check for invalid elevation qualifiers** (HZ ONLY, NO EL, etc.) - if present, suppress elevation labels
3. **Analyze COMMENT** (after "/") - understand its PURPOSE:
   - Is it a location descriptor? → Drafter note
   - Is it a feature identifier? → Presentation label
   - Is it a drafting instruction? → Drafter note
   - Does it contain measurement context? → Drafter note
4. **Apply DDIE** - don't duplicate what point style shows
5. **Generate labels** - one or both as appropriate
6. **Never skip** unless TC/TD/CO and not notable

### Step 3: Create Decisions JSON
Write a JSON file with your labeling decisions. Points can have MULTIPLE entries (one per label):

```json
{
  "mleader_style": "Annotative-Simplex",
  "labels": [
    {
      "point_num": "4005",
      "position": {"x": 1000.0, "y": 2000.0, "z": 3510.957},
      "type": "presentation",
      "label_text": "FFB = 3510.96'"
    },
    {
      "point_num": "4005",
      "position": {"x": 1000.0, "y": 2000.0, "z": 3510.957},
      "type": "drafter",
      "label_text": "gym"
    }
  ]
}
```

Save to a temp file in the same directory as the source CSV.

### Step 3.5: Export Decision Table CSV
Always output a CSV alongside the JSON for human review.

**CSV Location**: Same directory as output, named `<basename>-decisions.csv`

**CSV Format** (one row per label):
```
# Decision table for survey point labeling. Edit Decision or Label_Text columns and re-run to apply corrections.
Point#,File,Code,Comment,Decision,Label_Text,Reasoning,Notes
```

Points with dual labels get TWO rows (one presentation, one drafter).

**Columns**:
- **Point#**: Survey point number
- **File**: Source file identifier
- **Code**: Feature code before "/"
- **Comment**: Text after "/"
- **Decision**: `presentation`, `drafter`, or `skip`
- **Label_Text**: The text that will appear on the label
- **Reasoning**: Brief explanation of why this decision was made
- **Notes**: Empty - for user corrections

### Step 4: Create Labels
Run the labeling script:

```bash
python ~/.claude/skills/dxf/scripts/create_labels.py <decisions.json> --scale N --output <output.dxf>
```

**If this fails, STOP IMMEDIATELY. Analyze the error, explain it to the user, suggest a fix, and tell them to reprompt.**
</workflow>

<options>
## Options

- `--scale N`: Scale factor (default: 20 for 1"=20') - multiplies paper-space dimensions
- `--output PATH`: Output file path (defaults to `<csv-basename>-LABELS.dxf`)
- `--from-csv PATH`: Skip analysis and use decisions from a corrected CSV file
</options>

<output>
## Output Files

Two files are always produced:

1. **DXF file** (`<basename>-LABELS.dxf`):
   - MULTILEADER annotations for each labeled point
   - Presentation labels: Layer G-ANNO, ByLayer color, ALL CAPS
   - Drafter notes: Layer 0, RED color, lowercase
   - Uses "Annotative-Simplex" MLEADER style

2. **Decision CSV** (`<basename>-decisions.csv`):
   - Complete table of all labeling decisions
   - One row per label (points with dual labels have two rows)
   - Includes reasoning for each classification
   - Editable for corrections
</output>

<correction_workflow>
## Correction Workflow

If initial labeling decisions need corrections:

1. Open the `-decisions.csv` file
2. Review the Decision and Label_Text columns
3. Make corrections:
   - Change `Decision` to `presentation`, `drafter`, or `skip`
   - Modify `Label_Text` as needed
   - Add/remove rows for dual labels
4. Save the corrected CSV
5. Re-run: `python ~/.claude/skills/dxf/scripts/create_labels.py --from-csv <corrected.csv> --output <output.dxf>`
</correction_workflow>

<verification>
## Self-Check Before Completion

Verify your decisions against the cardinal rules:
- [ ] Every slashed point has at least one label (except TC/TD/CO when not notable)
- [ ] No DDIE violations (didn't label what point style already shows)
- [ ] Comment purposes correctly identified (location vs feature vs instruction)
- [ ] No MISC points skipped
- [ ] Dual labels created where appropriate (elevation + context)
- [ ] FFB points have `FFB = {elev}'` format
- [ ] Structure codes have `RIM ELEV = {elev}'` format
- [ ] Invalid elevation qualifiers (HZ ONLY, NO EL, etc.) suppress elevation labels
</verification>

<error_handling>
## Error Handling

**CRITICAL**: If any Python script fails:
1. STOP IMMEDIATELY - do not continue
2. Read and analyze the error message
3. Explain to the user what failed and why
4. Suggest how to fix the skill/script
5. Tell the user to reprompt after the fix
</error_handling>
