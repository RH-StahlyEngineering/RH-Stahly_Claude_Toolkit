# MTEXT creation via COM (generic, all-purpose)

Anything in this file is universal — applies to any MText created from this skill, not just record-measurement labels. For the record-label-specific conventions on top of this, see `record_label_conventions.md`.

## Creating MText: the basic call

```powershell
$insertPt = New-Object 'double[]' 3
$insertPt[0] = $x; $insertPt[1] = $y; $insertPt[2] = 0
$mt = $doc.ModelSpace.AddMText($insertPt, $boxWidth, $content)
$mt.Layer    = '<layer name>'
$mt.StyleName = '<style name>'
$mt.Height   = $modelHeight        # model units
$mt.Rotation = $rotRad             # radians, CCW from +X axis
```

- `$boxWidth` is the MText bounding-box width in model units. MText wraps if content exceeds this; set generously (e.g. content-width × 2) to avoid surprise wrapping.
- Layer must exist (`$doc.Layers.Item(name)` throws if missing — add it first via `$doc.Layers.Add(name)`).

## Rotation: from a surveyor bearing to AutoCAD radians

AutoCAD MText rotation is measured CCW from the positive X-axis (east). Surveyor bearings are measured from north. The mapping:

| Bearing form | AutoCAD rotation |
|---|---|
| `N x°y'z" E` | `π/2 - bearing_rad`  (line points NE; rotation < 90°) |
| `N x°y'z" W` | `π/2 + bearing_rad`  (line points NW; rotation > 90°) |
| `S x°y'z" E` | `-π/2 - bearing_rad`  *or equivalently* `3π/2 - bearing_rad` |
| `S x°y'z" W` | `-π/2 + bearing_rad`  *or equivalently* `3π/2 + bearing_rad` |

For text that should read "along" a line — i.e., the bottom of the letters faces the same side of the line every time — use the *upward-reading* rotation. For near-N/S bearings that's `π/2 ± bearing_rad`; for near-E/W bearings the text will read horizontally regardless.

Example: bearing `N 03°53'52" W` → rotation = `π/2 + radians(3 + 53/60 + 52/3600)` = `1.6388 rad` = `93.8978°`.

## MText escape codes (the ones you'll actually use)

| Code | Meaning |
|---|---|
| `\A0;` `\A1;` `\A2;` | Vertical alignment for the whole MText — bottom / middle / top. Useful for `\A1;` so the insertion point is the visual middle of the text, not the lower-left. |
| `\Stop^bot;` | Stacked text using caret as separator. **For pure subscript:** `\S^N;` (empty above, `N` below). **For pure superscript:** `\SN^;`. |
| `\H<n>x;` | Relative height multiplier — `\H0.7x;` shrinks following text to 70% of current. Scoped use: `{\H0.7x;...}` so it doesn't leak. |
| `\H<n>;` | Absolute height. Avoid for annotative text. |
| `\W<n>;` | Width factor (e.g. `\W0.9;` to condense). |
| `\fName|b<0/1>|i<0/1>;` | Font + bold + italic switch mid-text. |
| `\C<aci>;` | Color (ACI 1–7). E.g. `\C1;` = red, `\C7;` = white/byblock. |
| `\T<factor>;` | Character-tracking factor — multiplier on the spacing between characters. `\T0.85;` packs characters 15% tighter so visible gaps close. Used in Stahly to close gaps in underscored fill-in fields and run-in CCR labels. **Always scope with `{...}`.** See the "Tracking" section below for the expansion math. |
| `\O...\o` | Overline open/close. |
| `\L...\l` | Underline open/close. |
| `\P` | Paragraph break (hard return). |
| `[char]9` (tab) | A literal tab character in the content. Honored by MText as advance-to-next-tab-stop. Useful for indenting list items / numbered sub-courses. |
| `{` `}` | Scope a run of formatting; everything inside resets at the closing brace. **Always wrap subscript/super/height/tracking/color tweaks in braces** so they don't leak into the rest of the string. |
| `%%D` `%%C` `%%P` | Legacy escapes for `°`, `Ø`, `±`. Still honored by MText. Prefer Unicode (`°` directly or `\U+00B0`) for new content; preserve `%%D` when editing existing text to avoid visual diff. |

## Tracking (`\T<factor>;`) — closing gaps in fill-in fields

`\T<factor>;` is a multiplier on character spacing. `1.0` is default; values `< 1` close gaps, `> 1` widen them. The Stahly convention for plat-certificate fill-in lines and CCR-tag labels is **`\T0.85;`** — characters touch with no visible gap.

When converting an existing fill-in field of N underscores at default tracking to a `\T0.85;` block while preserving total visual length:

```
new_count = round(N / 0.85)        # ≈ N × 1.176
```

Examples:

| Original (N) | At 0.85 (new count) |
|---|---|
| 2 | 2 |
| 5 | 6 |
| 7 | 8 |
| 10 | 12 |
| 14 | 16 |
| 17 | 20 |
| 22 | 26 |
| 30 | 35 |
| 38 | 45 |

Wrap the expanded run in braces so tracking doesn't leak:

```
... day of {\T0.85;________________}, ...
```

The same pattern works for any run of identical characters (dashes, dots, periods of a leader line) where you want the visual width preserved while the spacing visibly closes.

## Annotative text — the AutoCAD 2025 LMS-Tech limitation

`AcadMText.Annotative` is **not exposed via COM** on AutoCAD 2025 (LMS-Tech). Setting `$mt.Annotative = $true` throws *"The property 'Annotative' cannot be found on this object."*

**Workaround: use a text style that is itself annotative.** When you assign an annotative style, AutoCAD automatically:
- Marks the MText as annotative
- Attaches the *current* `CANNOSCALE` as the object's annotation scale

So the recipe is:
1. **Set `CANNOSCALE`** to the target annotation scale *before* creating the MText:
   ```powershell
   $origScale = $doc.GetVariable('CANNOSCALE')
   $doc.SetVariable('CANNOSCALE', '1" = 1000''')  # exact string per the scale list
   ```
2. **Create the MText** with an annotative style name (anything beginning with "Annotative" in this drawing's style list — common names: `Annotative Simplex`, `Annotative Italic-0.08`, `Annotative Simplex-0.08`).
3. **Set `Height` to the model display height at the current scale**, which is `paper_height × scale_factor`. For 0.08″ paper at 1″=1000′, that's `80` model units.
4. **Restore the previous `CANNOSCALE`** so you don't perturb the user's working scale.

If the style isn't annotative and you absolutely must add the scale list via COM, the only path is `$doc.SendCommand("...")` with the `_-OBJECTSCALE` command — but that's flaky (escape-sequence sensitive, hangs AutoCAD on bad input). Pick an annotative style and avoid it.

## CANNOSCALE parsing

`CANNOSCALE` is a string like `1" = 1000'`, `1:1000`, or `1"=100'`. To get the numeric scale factor for sizing calculations:

```powershell
function Get-ScaleFactor {
    param([string]$scaleName)
    # imperial:   1" = 1000'   or   1"=1000'
    if ($scaleName -match '1\s*["'']?\s*=\s*(\d+(?:\.\d+)?)\s*[''"]?') {
        return [double]$Matches[1]   # for 1" = 1000' returns 1000
    }
    # metric: 1:1000
    if ($scaleName -match '1\s*:\s*(\d+(?:\.\d+)?)') {
        return [double]$Matches[1]
    }
    throw "Cannot parse CANNOSCALE '$scaleName' as a numeric scale factor."
}
```

(See `lib/mtext_helpers.ps1` for the canonical implementation.)

## Height calculation

For an annotative MText whose **paper-plot height** should be `h_paper` (e.g. 0.08″), the model-units height at the current annotation scale is:

```
modelHeight = h_paper × scale_factor
```

Examples:
- Paper 0.08″ at 1″ = 1000′ → 80 model units (feet, if drawing is in feet).
- Paper 0.08″ at 1″ = 100′ → 8 model units.
- Paper 0.10″ at 1″ = 50′ → 5 model units.

## Insertion point and offsets

`$mt.InsertionPoint` is a double[3] (X, Y, Z). For positioning text alongside a line, see `record_label_conventions.md` — the "perpendicular offset scales with annotation scale" pattern shows up everywhere, not just on record labels.

## Editing existing MText (vs. recreating)

When a user has manually adjusted properties of an existing MText — style, height, width, attachment, insertion, position, paper-space vs model-space placement — the skill **MUST** edit the existing object's `TextString` property in place rather than deleting and re-adding. The user's customizations are otherwise lost.

```powershell
$mt = $doc.HandleToObject($handle)
$mt.TextString = $newContent      # changes content only; everything else preserved
```

This is the surgical pattern. Use it whenever the task is "fix the text on this MText" and not "create a new MText."

### Handle changes when an entity moves model ↔ paper space

When the user moves an MText (or any entity) from `ModelSpace` to a paper-space layout (or back), AutoCAD **deletes and recreates** the entity. The old handle becomes invalid; a new one appears in the destination block. Cached handles from earlier in a session become stale.

The skill detects this case by trying `HandleToObject($oldHandle)` and catching the failure. The recovery path is to **search by content** across all layouts. See the `Find-MTextByContent` helper in `lib/mtext_helpers.ps1`.

### Searching across layouts

`Doc.ModelSpace` is one of several places MText can live. The other places are paper-space layouts (`Doc.Layouts.Item(name).Block`). To find an entity whose handle has gone stale, iterate every layout's block:

```powershell
foreach ($lay in $doc.Layouts) {
    $blk = $lay.Block
    foreach ($e in $blk) {
        if ($e.ObjectName -eq 'AcDbMText' -and $e.TextString -match $pattern) {
            ...
        }
    }
}
```

A `Find-MTextByContent` helper in `lib/mtext_helpers.ps1` encapsulates this pattern. Use it whenever an existing handle stops resolving or when the user describes the MText by visible content rather than handle.

## Known gotchas

- **Don't expect `.Annotative` to round-trip.** On this build it's not COM-readable either; you can't query it. Trust the style assignment.
- **Setting `StyleName` *after* creation re-applies the style's defaults to anything you haven't explicitly set.** Set Height *after* StyleName, not before, or your height gets clobbered.
- **Setting `AttachmentPoint` resets `InsertionPoint`.** If you change attachment, re-set InsertionPoint.
- **`AddMText` requires a non-zero `boxWidth`.** A box width that's too small forces wrapping; too large is harmless.
- **Apostrophes inside MText content are fine** (just `'`), but **double quotes need to be doubled in PowerShell string literals** (`""`).
- **Moving an entity between model space and a paper-space layout changes its handle.** Cached handles from earlier in the session won't resolve; search by content (see `Find-MTextByContent`).
- **Annotative style names are decorative labels, not enforcing.** A style named `Annotative Italic-0.08` will happily render at paper height 0.10, 0.12, etc. The per-MText `Height` controls the actual size; the style name's numeric suffix is for human bookkeeping only.

## `GetBoundingBox` on MText — two failure modes you will hit

`GetBoundingBox` on an `AcadMText` does not always return the content height. The two failure modes are not theoretical — they recur on Stahly drawings and they have eaten hours.

### Failure mode A — the box returns the *box* height, not the *content* height (stretched-box bug)

A user can grip-stretch an MText's vertical extent beyond its rendered content (drag the bottom-middle grip down). The text inside the box stays the same; the box gets taller. `GetBoundingBox` then reports the BOX height, which is larger than the content.

**Symptom:** bbox height significantly exceeds `(paragraphs × LineSpacingDistance)`.

**Cure:** ask the user to "minimize each box" — open each MText editor, the box auto-shrinks to its content on close. Or, ask the user for the actual rendered height; they can read it off the AutoCAD Properties palette in seconds.

This is what produced our hour-long debate over whether a Certificate of Exemption was 0.65″, 1.5″, or 3.1″ tall. The original bbox of 3.1″ was after a grip-stretch; after minimization it dropped to 0.65″; later the user added content and it went back up to 1.5″.

### Failure mode B — the bbox returns near-zero, no matter what you do (broken-bbox bug)

Some MText return a degenerate bbox that captures only the title line (or nothing at all), even though the rendered content is many lines tall. Triggers we have observed:

- Leading paragraph-format code (`\pxql;`, `\pi-3,l4,t4;`).
- Title-block patterns where `\P` appears INSIDE the underline braces: `{\LCERTIFICATE OF EXEMPTION\P}(subtitle)`.
- MText immediately following a `\A1;` vertical-alignment code combined with the above.

**Symptom:** bbox height is much smaller than `(paragraphs × LineSpacingDistance)`.

**Cure:** can't fix from PowerShell COM. Regen, copy-and-measure, set TextString to itself, set Width to itself — none of these update the bbox. **Ask the user for the height.**

### The defensive pattern

`lib/mtext_helpers.ps1::Get-MTextContentHeight` returns both the bbox value and a paragraph-count estimate, and flags `BBoxLooksBroken` or `BoxLooksStretched` when they disagree by ≥ 2×. Use it whenever a layout decision depends on the height — never trust raw `GetBoundingBox` blindly for MText.

```powershell
$h = Get-MTextContentHeight -Doc $doc -Handle '18230'
if ($h.Verdict -ne 'OK') {
    Write-Warning "$($h.Recommend)"
}
$height = $h.BBoxHeight   # or ask user when verdict is bad
```

## Editing MText surgically — preserving the user's manual formatting

When fixing the *content* of an MText that the user has manually styled (specific paper height, custom Width, custom AttachmentPoint, placed in a paper-space layout at a specific position), edit `TextString` in place — never delete and recreate. The latter loses every property the user touched.

```powershell
$mt = $doc.HandleToObject($handle)
$mt.TextString = $newContent      # the only property to change
```

For moving the entity vertically or horizontally without changing content, use `lib/mtext_helpers.ps1::Set-EntityY` / `Set-EntityX`. They write `InsertionPoint` and leave everything else alone.

## AutoCAD COM goes transiently unresponsive — wait, retry, don't escalate

In a long session it is common to hit:

```
AutoCAD is running but no document is open. Open the target DWG, then retry.
```

This often does NOT mean what it says. It usually means:

- A modal dialog is open (Properties palette toolbar, Save dialog, error pop-up, OBJECTSCALE selection, SCALELISTEDIT).
- The user is mid-command in the AutoCAD UI.
- `Documents.Count` returns blank because the COM call is being rejected, not because there are zero documents.

**The pattern**: wait briefly, then retry. Do not assume the drawing has been closed. Do not move on to a recovery path. The user's instruction in our session: *"if I'm in a command sometimes it won't let you make edits. so if that happens again just wait 30 seconds and try again."*

If a retry after 30 seconds still fails, ASK the user to confirm the document is open and not in a modal command — don't keep retrying silently.

## PowerShell COM gotcha — verify position deltas after a move loop

PowerShell variable scoping in `foreach` loops with embedded function calls and hashtable lookups (`$H[$h]`) can silently fail under certain combinations, returning `$null`. In arithmetic, `$null` coerces to 0, so `$y = $y - $H[$h] - $Gleft` silently degenerates to `$y = $y - $Gleft` — wrong, but no error.

**Symptom**: a layout loop produces positions that subtract only some terms; items end up clustered at the top of the column instead of distributed.

**Defensive pattern**: after applying a position loop, READ the resulting positions back and verify against expectation. Don't trust your own loop's correctness — verify after.

```powershell
# After the loop, re-read and confirm:
foreach ($h in $col) {
    $actualY = $doc.HandleToObject($h).InsertionPoint[1]
    if ([Math]::Abs($actualY - $expected[$h]) -gt 0.01) {
        Write-Warning "h=$h  expected $($expected[$h]), got $actualY"
    }
}
```

For one-off layouts on a known small set of items, hardcoding the computed Y values explicitly (as we ended up doing for the column layout) is more reliable than relying on a loop and a hashtable. Verbosity beats silent corruption.

## Adding rows to a paper-space legend

Legends live in **paper space** (the sheet layout's `Block`), not model space. Find a neighbouring row by its text (e.g. `"PRIVATE UTILITY LOCATE"`), then copy that row's pieces with `.Copy()` + `.Move()` so style, height and layers match exactly. A Stahly legend row is typically three objects: the label MText (`G-ANNO`), a sample line on the real drawing layer, and a duplicate sample on `G-ANNO-LEGEND-NPLT`. Keep the column's row spacing (0.4" on the 24x36 TD).

- **Xref layers can't hold local objects.** If the sample's layer only exists as `<xref>|LAYER`, create a local layer of the same name and copy its color, linetype and lineweight.
- **Check the label clears the sample line** with `GetBoundingBox`. If it overlaps, wrap it to two lines with `\P`.
- **Two-line labels: re-centre vertically.** The sample line in a one-line row sits at the line's mid-height (insertion Y minus about 0.075" for 0.10" text). After wrapping, move the label **up** so the sample line runs through the middle of the gap between the two lines: shift by about half a line pitch (~0.08" for 0.10" text), or compute it from the bounding box so the sample Y equals the label's vertical centre. Then check it doesn't collide with the row above. RH had to fix this by hand on the first attempt (2026-11-18, TD legend easement rows).
