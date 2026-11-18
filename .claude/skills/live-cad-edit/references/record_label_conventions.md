# Record-measurement label conventions (Stahly survey work)

Layered on top of generic MTEXT mechanics in `mtext_creation.md`. This file captures the conventions that turn a generic MText into a Stahly-style record-call.

A record-measurement label is the deed-call annotation along a section line or parcel line — e.g., `GLO = 2673.00' (R1)` — where `(R1)` is a subscripted reference to the legend's reference document index. Some labels carry only the distance — no `(R<N>)` subscript — when the legend reference is implicit from context.

## Style, layer, height

| Property | Value |
|---|---|
| Layer | `V-BNDY-REC-TEXT` |
| Text style | `Annotative Italic-0.08` (italic — the deed-call convention) |
| Paper text height | 0.08″ default; 0.10″ also common; ask the user when unclear |
| Vertical alignment escape | `\A1;` (middle) at the start |

Italic is the visual signal that this is a *record* call rather than a measured value. Roman/simplex is for measured. Don't mix them up — it's how plat reviewers tell at a glance which dimensions are deed and which are field.

**The style name's numeric suffix (`-0.08`) is decorative, not enforcing.** The same style `Annotative Italic-0.08` is reused at different paper heights (`0.08`, `0.10`, etc.) by varying the MText's per-object `Height` property. Don't read the style name as locking the paper height — set it explicitly per label.

### Model height = paper × scale factor

| Paper height | 1"=100' | 1"=200' | 1"=300' | 1"=500' | 1"=1000' |
|---|---|---|---|---|---|
| 0.08″ | 8 | 16 | 24 | 40 | 80 |
| 0.10″ | 10 | 20 | 30 | 50 | 100 |
| 0.12″ | 12 | 24 | 36 | 60 | 120 |

Use the table to set `Height` on the MText (model units). The annotative system displays the label at paper-height at any annotation scale included in the MText's object-scale list.

## Content format

```
\A1;<MEASUREMENT> (R{\H0.7x;\S^N;})
```

Or, for distance-only labels (no legend reference):

```
\A1;<MEASUREMENT>
```

Pattern:
- `\A1;` — middle alignment (so the insertion point is the visual center).
- `<MEASUREMENT>` — the labeled value. Common shapes:
  - `GLO = 2673.00'` (General Land Office reference distance)
  - `2673.00'` (simple distance only)
  - `N 03°53'52" W 2673.00'` (bearing + distance)
  - `209.2'` (record with significant figures honored — write `209.2'`, not `209.20'`)
- `(R{\H0.7x;\S^N;})` — the reference number, where `N` is the legend index (1, 2, 3, …). The braces scope the `\H0.7x;` (70% relative height) so the subscript ends up properly proportioned — without the size tweak, `\S^N;` alone renders the digit at the same height as the main text, which looks bad. **Omit this entire parenthetical when the label is distance-only.**

**The 70% relative-height trick is load-bearing** when the subscript is present. Bare `\S^N;` makes ugly oversized subscripts. Always wrap.

**Significant figures matter on record calls.** When the user supplies `209.2'` (one decimal), label it as `209.2'`. Do not pad to `209.20'` — that misrepresents the recorded precision.

## Annotation-scale handling (and the trap)

The `Add-AnnotativeMText` helper tries to set `CANNOSCALE` to the requested scale name before creating the MText, so the MText's annotation-scale list includes the right scale. This works only when the scale name is registered in the drawing's master scale list.

**When the requested scale is NOT registered** (common: `1" = 100'` may be missing from drawings created from older templates):

- The helper emits a Write-Warning and falls back to computing model height from either the parsed factor or an explicit `-AnnoScaleFactor` numeric override.
- The resulting MText has the correct physical size, but its annotation-scale list does NOT include the requested scale name — at any other annotation scale, AutoCAD won't know to display it.
- **The user must fix the scale assignment manually:**
  1. Run `SCALELISTEDIT` and `_Add` the missing scale (`1" = 100'`, ratio `1:100`).
  2. Select the new labels and run `OBJECTSCALE` (or use the Annotative Scale property in the Properties palette) to add the scale to each label's object-scale list.

Tell the user this in the report so they can fix it in one pass.

### Passing the scale to the script

- `-AnnoScale "1\" = 100'"` — by name. Works when the scale is registered. Falls back to the parsed factor + warning when it isn't.
- `-AnnoScaleFactor 100` — by numeric factor. Bypasses the name lookup entirely. Use when the scale isn't registered and you don't want the noisy warning. The annotation-scale assignment still needs the manual SCALELISTEDIT+OBJECTSCALE pass.

The two parameters work together: if both are supplied, the factor overrides the parsed name, but the name is still attempted on CANNOSCALE.

## Rotation

Matches the line being labeled. Use the *upward-reading* rotation for near-N/S lines:

```
rotation_rad = π/2 + bearing_rad      # for N..W and S..E (line points NW/SE)
rotation_rad = π/2 - bearing_rad      # for N..E and S..W (line points NE/SW)
```

(See `mtext_creation.md` for the full bearing-to-rotation table.)

For a near-E/W line, text reads horizontally — use rotation 0.

## Position: perpendicular offset from the line

Convention: place the label centered along the labeled line, offset perpendicularly to whichever side reads cleanly without colliding with other labels. The offset that "looks nice" varies with parcel density, but a strong default is:

**Paper offset ≈ 0.27″** → model offset = `0.27 × scale_factor`.

Examples of "looks nice" model offsets at the same paper offset of 0.27″:
- 1″ = 1000′  →  270 model-ft
- 1″ = 500′   →  135 model-ft
- 1″ = 100′   →  27 model-ft
- 1″ = 50′    →  13.5 model-ft

This is just a default — adjust for the specific plat. Accept a `-PaperOffset` parameter in the script so the user can tune.

## Direction of perpendicular offset

By convention, the label goes on the *outside* of the parcel (so it doesn't crowd the parcel's interior dimensions). For a section line, that means outside the section. The script's default places text on the *right side* of the line walking from start to end; flip with a sign change on the perpendicular vector.

### "Outside the section" decoder for section-line labels

When labeling a half-section side, "outside" depends on which side of the section the line is on and the direction it's drawn:

| Line role | Drawn direction (start → end) | Outside-the-section = | `-OffsetSide` |
|---|---|---|---|
| North section line | East (typical) | North | `left` |
| North section line | West | North | `right` |
| South section line | East | South | `right` |
| South section line | West | South | `left` |
| East section line | South (typical) | East | `left` |
| East section line | North | East | `right` |
| West section line | South | West | `right` |
| West section line | North | West | `left` |

Rule of thumb: walk along the line in the direction the start→end vector points; "outside the section" is whichever side puts the parcel interior behind your other shoulder.

## Attachment point and box width

Use `AttachmentPoint = 5` (middle-center) so the text's visual center sits at the insertion point regardless of the box width. The default `BoxWidth = modelHeight × 30` is enough for ~30 italic characters at the typical record-call length. Both are baked into `Add-AnnotativeMText` defaults; `add_record_label.ps1` inherits them.

## Distance-unit conversion

GLO deed calls are often in **chains** (Gunter's chain = 66 ft):

```
feet = chains × 66
```

Examples:
- 40 chains  = 2640.00 ft (a clean half-section)
- 40.13 ch   = 2648.58 ft
- 41.15 ch   = 2715.90 ft

When the user provides a value in chains, multiply by 66 and round to 0.01 ft before writing the label.

## Along-line position

Default to **midpoint** (50% of line length). Surveyors sometimes shift toward one end if the midpoint collides with another label — accept a `-AlongFraction` parameter (0.0 to 1.0).

## What the final MText looks like

```
Layer:      V-BNDY-REC-TEXT
Style:      Annotative Italic-0.08
Height:     80   (model — at CANNOSCALE = 1" = 1000')
Rotation:   93.8978°   (matches N 03°53'52" W)
Insertion:  (2,370,095.88, 1,001,955.57)   (midpoint of the labeled line + 270 ft east)
Content:    \A1;GLO = 2673.00' (R{\H0.7x;\S^1;})
```

That's an exact reproduction of a real Stahly record label that's been reviewed and shipped.

## When to use this vs a generic MText helper

Use `scripts/add_record_label.ps1` when the text is a record-deed-call alongside a line.

Use generic MText creation (`lib/mtext_helpers.ps1::Add-AnnotativeMText`) for everything else — leader notes, free-floating annotations, sheet titles, anything where the "Italic-0.08 + (R<N>) subscript" pattern doesn't fit.
