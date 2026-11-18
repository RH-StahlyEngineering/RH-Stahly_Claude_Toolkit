---
name: live-cad-edit
version: 1.3
description: Solve geometric constraint problems on parcel/line geometry in a live AutoCAD session and apply the result via COM. Use when the user wants to compute closure/mapcheck on a polyline, balance a parcel to an exact acreage, rotate boundary segments to a target bearing, verify topology between adjoining parcel polylines, apply coordinated multi-vertex moves, build a multi-parcel closure-report PDF (one sketch per parcel), or place an annotative record-measurement label (e.g. "GLO = 2673.00' (R1)" with subscript) on a line at the right bearing/scale/offset. NOT for drawing creation, layer/style/plot setup, block management, or anything that's a one-click AutoCAD command without a survey/topology/annotation constraint behind it. Triggers on phrases like "closure", "mapcheck", "inverse listing", "closure report PDF", "hit X acres exactly", "balance area", "verify topology", "shared vertices", "hold these bearings", "rotate to bearing", "perpendicular gap", "apply moves via COM", "edit polyline vertex", "add a GLO callout", "record measurement label", "label this line with a deed call", "annotative MText".
---

# live-cad-edit

The hammer: **given geometric constraints, compute exact coordinates and apply them to a running AutoCAD drawing**. Everything else stays in AutoCAD's UI.

## When to use

Invoke this skill when the user's request is fundamentally **"given these constraints, what should the geometry be?"** — and they want it applied. Common phrasings:

- *"Closure / mapcheck / inverse on polyline handle 15053"*
- *"Get this parcel to exactly 20.0100 acres without changing any bearings except by moving vertices X and Y"*
- *"Rotate these segments to bearing N 03°04'10" W and keep the area at 20.0100 ac"*
- *"Verify these three parcel polylines share vertices and that bearings/distances match across shared boundaries"*
- *"Snap this vertex onto that line"*
- *"What's the perpendicular gap between L8 and the section north line, sampled along L8?"*

## When NOT to use

- Creating a new drawing or template — that's AutoCAD's job.
- Layer states, plot styles, plotting, sheet setup, blocks, xrefs — UI work, no leverage from automation.
- Anything that's a single command in AutoCAD (OFFSET, ROTATE, FILLET, TRIM, STRETCH) with no acreage/bearing/topology constraint attached.
- Civil 3D *object* editing (Parcel objects, alignments, surfaces). On this machine only the Civil 3D Object Enabler is installed — those load as proxies and can't be edited via COM. Work with the underlying LWPolyline/Line/etc.
- DWG files that are NOT currently open in AutoCAD. This skill talks to a *running* AutoCAD instance.

### Constraint-driven geometry creation IS in scope

The "no drawing creation" rule has a meaningful exception: when the geometry to create is **parameter-driven and constraint-bearing**, it belongs here. Examples that fit:

- A circle approximated by an LWPolyline with exact N vertices and exact radius (tolerance disk, snap target, monument annotation).
- An annotative record-measurement label whose layer/style/rotation/offset/scale are all rule-driven from the line being labeled.
- A closed polyline drawn from a deed description (bearings + distances from a POB).

What still does *not* fit: pasting in arbitrary text, drawing a rectangle to outline a viewport, inserting a title-block — use AutoCAD's UI for those.

## Prerequisites the skill assumes

- AutoCAD 2025 is running with the target DWG open (and not in a modal command/dialog state — see retry note below).
- The skill is on Windows with PowerShell 7+.
- The user has identified the entities of interest by **hex handle** (visible in AutoCAD's Properties palette). Handle-based selection is precise and unambiguous.

## Document selection (when multiple DWGs are open)

If AutoCAD has only one document open, scripts auto-target it. If multiple are open, **the model must ask the user which one** before running anything, then pass `-Document` to every script in the chain. The skill will refuse to guess.

`-Document` accepts either:
- An integer index (0, 1, 2, ...) matching the position in `Documents`, OR
- A case-insensitive substring of the document name (e.g. `-Document 'COS'` matches `3898-00125_COS.dwg`).

The substring must match exactly one document; ambiguous matches throw with the candidate list. To enumerate open documents, the model can run this one-liner before invoking the skill:

```powershell
. "$env:USERPROFILE\.claude\skills\live-cad-edit\lib\com_bootstrap.ps1"
$acad = [Rot]::Get('AutoCAD.Application')
for ($i=0; $i -lt $acad.Documents.Count; $i++) { "[$i] $($acad.Documents.Item($i).Name)" }
```

A blank `FullName` indicates a never-saved drawing (e.g. `Drawing2.dwg`) — common for scratch work, but a footgun if the model picks it by accident.

## Operating principles (do not violate)

1. **Suggest, don't apply silently.** Every script that mutates geometry produces a target-state report and stops. The user reviews and explicitly says "apply" before any `apply_vertex_moves.ps1` runs.
2. **Always verify after applying.** Every apply script re-pulls state from AutoCAD and reports actual vs. expected (area, bearings, vertex coords).
3. **Identify entities by hex handle in all output.** Drafter can paste the handle into AutoCAD's Properties dialog to inspect.
4. **Never save the drawing on the user's behalf.** Edits are in-memory; user saves in AutoCAD manually.
5. **Surveyor precision in all output.** Bearings to nearest second, distances to 0.01 ft, coordinates to 0.0001 ft. Raw double-precision is for internal math only.
6. **Don't reimplement AutoCAD commands.** If the user asks for OFFSET or ROTATE without a constraint, redirect them to the native command.

## Layout

```
live-cad-edit/
  SKILL.md                       (this file)
  lib/
    com_bootstrap.ps1            COM attach with PS7 DllImport wrapper + retry helper
    bearing_math.ps1             Format-Bearing, Parse-Bearing, Azimuth-Deg
    geometry.ps1                 IntersectLines, PerpDist, Shoelace, Bulge helpers
    topology.ps1                 FindCoincident, AuditSharedEdges
    solvers.ps1                  Bisection, PerpShift-ForArea, BearingRotate-WithOffset
    mtext_helpers.ps1            Add-AnnotativeMText, Get-AnnoScaleFactor, Bearing-To-Rotation,
                                 Find-MTextByContent (search all layouts),
                                 Expand-UnderscoreTracking (wrap underscore runs in {\T0.85;...}
                                 preserving visible length),
                                 Set-EntityY / Set-EntityX (surgical insertion-point moves),
                                 Get-MTextContentHeight (bbox + paragraph-count estimate with
                                 broken-bbox / stretched-box verdict),
                                 Compute-EqualSpacedColumn (layout solver with signature-gap
                                 constraint, optional top/bottom margin multipliers)
  scripts/
    mapcheck.ps1                 closure / inverse / area / precision-ratio report (console)
    audit_topology.ps1           cross-polyline shared-vertex & shared-edge audit
    balance_area.ps1             perpendicular-shift solver: hold bearings, hit target acreage
    rotate_segments.ps1          rotate listed segments to target bearing + restore area
    apply_vertex_moves.ps1       coordinated multi-polyline vertex apply (last step only)
    closure_report.ps1           multi-parcel closure-report PDF wrapper (calls Python)
    build_closure_report.py      Python builder for the closure-report PDF
    add_record_label.ps1         annotative record-measurement label on a line (Stahly convention)
    add_circle_polyline.ps1      closed LWPolyline approximating a circle (snap target / tolerance disk)
  references/
    stahly_layers.md             NCS layer conventions used at Stahly
    plat_precision.md            surveyor rounding rules and bearing notation
    mtext_creation.md            generic MTEXT creation patterns + annotative gotchas + tracking escape +
                                 paper-space search + "moving entity changes handle" + surgical-edit pattern +
                                 adding paper-space legend rows (two-line label vertical centring)
    record_label_conventions.md  Stahly-specific record-measurement label conventions
    stahly_plat_certificate_conventions.md  Stahly certificate-block typo catch list, statutory
                                            verbatim phrasings, 20__/underscore-fill-in conventions,
                                            order-of-operations for bulk certificate edits
    closure_report_conventions.md  closure-report PDF structure and POB conventions
```

## Standard workflows

### Constraint-solve and edit (the original use case)

For most asks, the model should chain scripts in this order (each step output is reviewed before the next):

1. **`mapcheck.ps1 <handle>`** — get the current state. Always start here so the user sees what they're working with.
2. **One of:**
   - `balance_area.ps1 <handle> --target-ac <X> --movable-verts <list>` (hold bearings, hit acreage), OR
   - `rotate_segments.ps1 <handle> --bearings <list> --target-ac <X>` (combined), OR
   - `audit_topology.ps1 <handle1> <handle2> ...` (verification only, no edits).
3. **`apply_vertex_moves.ps1`** — only after user says "apply", and only with the explicit target coordinates from step 2.
4. **`audit_topology.ps1`** again to confirm topology is still clean after the apply.

### Build a closure-report PDF for N parcels

1. **`closure_report.ps1`** — pass each parcel's handle, human-readable name, and a POB strategy (`NE-South`, `NW-South`, `Vertex` with explicit `POBX`/`POBY`, etc.). The wrapper pulls vertices via COM, writes JSON, and invokes the Python builder.
2. Output PDF lands at `-OutPdf` (or `$env:TEMP\closure_report.pdf` by default).
3. If POB strategy is wrong, re-run with corrected `POBStrategy` / `FirstLeg` values — POB reordering is deterministic.
4. Defer formatting rules to `references/closure_report_conventions.md`.

### Add a record-measurement label to a line

1. Identify the line by hex handle (Properties palette in AutoCAD).
2. **`add_record_label.ps1 -LineHandle <h> -Measurement "GLO = 2673.00'" -ReferenceNumber 1`**
3. Optional tuning: `-PaperOffset 0.27` (default), `-OffsetSide right|left`, `-AlongFraction 0.5`, `-StyleName`, `-PaperHeight`.
4. The script sets CANNOSCALE only transiently — the user's working scale is restored after.
5. Defer formatting rules to `references/record_label_conventions.md` (italic style, subscript + 70% height trick, layer `V-BNDY-REC-TEXT`, the "outside the section" `-OffsetSide` decoder, and the chains × 66 conversion).

### Create a closed-polyline circle (snap target / tolerance disk)

1. **`add_circle_polyline.ps1 -CenterX <x> -CenterY <y> -Radius <r> -Vertices <N>`**
2. Use when the "circle" needs to behave like a polyline (vertices addressable via COM, closure-checkable via `audit_topology.ps1`). For an ordinary AcDbCircle, use AutoCAD's CIRCLE command.
3. Reports both the actual CAD area and the formula-derived polygon-vs-true-circle percentage so you know how tight the approximation is. At N = 500, the polygon area is within 0.4% of the true circle.

## Reference material to read on first invocation

These reference files encode conventions the model must follow. **Read the ones relevant to the task before producing output.** Treat them as binding for formatting and entity identification.

- **`references/plat_precision.md`** — Always-relevant. Surveyor's rounding rules (bearings to nearest second, distances to 0.01 ft, coords to 0.0001 ft), the closure / mapcheck definition (re-inverse rounded values, NOT raw), Idaho minimum closure (1:10,000), vertex-coincidence tolerance (0.005 ft), and the 180°-flip convention for shared edges between adjoining parcels.
- **`references/stahly_layers.md`** — Always-relevant. NCS layer conventions used in Stahly's drawings (`V-BNDY-PARCEL`, `V-BNDY-SECT`, etc.), how to identify the N 1/4 and S 1/4 corners from section-line junctions, and what kind of entity a "ROW line" typically is (plain `AcDbLine` on `V-BNDY-PARCEL`).
- **`references/mtext_creation.md`** — Read when creating any MText. Generic patterns for `AcadMText.AddMText`, escape codes (subscript `\S^N;`, alignment `\A1;`, relative-height `\H0.7x;`, scope braces), the AutoCAD 2025 LMS-Tech limitation that `.Annotative` isn't COM-settable (workaround: use an annotative style), CANNOSCALE parsing, and paper-vs-model height math.
- **`references/record_label_conventions.md`** — Read when adding a record-measurement / deed-call label. Layered on top of `mtext_creation.md` — Stahly-specific style (`Annotative Italic-0.08`), layer (`V-BNDY-REC-TEXT`), content format (`\A1;<measurement> (R{\H0.7x;\S^N;})`), the 70% subscript-height trick, and the "paper 0.27″ → model offset = 0.27 × scale_factor" perpendicular-offset default.
- **`references/closure_report_conventions.md`** — Read when building a closure-report PDF. Output structure (cover + one page per parcel), the rounded-then-re-inversed closure math, POB strategy strings (e.g. `NE-South`, `Vertex` with explicit POBX/POBY), sketch layout rules (POB and N-arrow placed in opposite corners; aspect-driven wide vs side-by-side layout), and tunable defaults.

## Known gotchas (encoded in `lib/com_bootstrap.ps1`)

- `$acad.ActiveDocument` is unreliable when AutoCAD focus is on a palette/dialog. Bootstrap returns `$acad.Documents.Item(0)`.
- COM calls fail with `RPC_E_CALL_REJECTED` (0x80010001) when AutoCAD is mid-command or has a dialog open. Bootstrap includes a retry helper that surfaces a clear "AutoCAD is busy" message rather than a cryptic HRESULT.
- PowerShell 7 dropped `[Marshal]::GetActiveObject` — bootstrap provides a `[Rot]::Get('AutoCAD.Application')` replacement via `Add-Type` + DllImport.
- PowerShell variables are **case-insensitive**. Scripts use distinctive names (`$pdata` for hashtables, never `$P` next to `$p`).
- LWPolyline vertex moves: read `$pl.Coordinates`, mutate flat double-array, assign back. There's no per-vertex setter.

## What's deliberately not in scope

- Bulge/arc support in mapcheck and topology (straight segments only). Curves trigger an explicit error.
- Civil 3D label parsing for "authoritative" bearings/distances.
- Headless / file-only mode (ezdxf + ODA File Converter).
- Multi-constraint nonlinear optimization. Current solvers are 1-parameter bisections.
- Saving the drawing automatically.
- Generic free-form annotation outside survey conventions — the MText capability is intentionally limited to record-measurement labels (and `lib/mtext_helpers.ps1::Add-AnnotativeMText` for direct calls). For unrelated text, use AutoCAD's UI.
- Setting `.Annotative` programmatically — AutoCAD 2025 LMS-Tech doesn't expose it via COM; always go through an annotative style instead.

If a user asks for something not covered, recommend the AutoCAD UI or open a feature conversation.

## Version history

- **v1.0** — initial release: mapcheck, audit_topology, balance_area, rotate_segments, apply_vertex_moves.
- **v1.1** — `Connect-AutoCAD` now supports `-Document` selector (integer index or name substring); required when multiple DWGs are open.
- **v1.2** — added closure-report PDF builder (`closure_report.ps1` + Python) and record-measurement label tool (`add_record_label.ps1`); new reference docs for MText creation, record-label conventions, and closure-report conventions.
- **v1.3** — `Add-AnnotativeMText` now defaults to AttachmentPoint = 5 (middle-center) and BoxWidth = 30 × height so record labels stay on one line; `add_record_label.ps1` rotation logic fixed to use the surveyor `π/2 ± bearing_rad` convention (no more clamp to horizontal for near-N/S lines); added `add_circle_polyline.ps1` for closed-polyline circle approximations; record-label conventions expanded with the "outside the section" offset-side decoder and the chains × 66 conversion.
- **v1.4** — record-label scale handling no longer throws when the requested CANNOSCALE name isn't registered in the drawing. New `-AnnoScaleFactor` numeric parameter on both `Add-AnnotativeMText` and `add_record_label.ps1` bypasses the name lookup. `ReferenceNumber=0` (now the default) creates a distance-only label without the `(R<N>)` subscript. `record_label_conventions.md` updated with the model-height-vs-scale-factor table, the "style name suffix is decorative" rule (`Annotative Italic-0.08` is reused at paper 0.08″ / 0.10″ / etc.), the significant-figures rule (label `209.2'` as `209.2'`, never pad to `209.20'`), and the manual SCALELISTEDIT+OBJECTSCALE follow-up users must run when the requested scale isn't registered.
- **v1.5** — added `Find-MTextByContent` (searches every layout, model + paper, for MText matching a pattern; recovery path when handles go stale because the user moved an entity model↔paper space) and `Expand-UnderscoreTracking` (wraps every `_{2,}` run in `{\T0.85;...}` with the count multiplied by 1/0.85 so the visible length is preserved while gaps close — the Stahly fill-in-field convention). `mtext_creation.md` expanded with: the `\T<factor>;` tracking escape and underscore-expansion math, tab characters in MText, searching across paper-space layouts, the moving-entity-changes-handle gotcha, and the surgical TextString-edit pattern (preserve user's manual style/width/position when fixing content). New `stahly_plat_certificate_conventions.md` reference captures the Stahly typo catch list (`Decemeber`, `resubdivison`, `from the purpose of relocating`, `MCA.,`, `acknowledge that he executed`), the MCA-statute verbatim phrasings to preserve, the `20__ → 2026` year-stub convention, and the order-of-operations rule (year-stub substitution BEFORE underscore-tracking wrap).
- **v1.6** — vertical-layout discipline added. New helpers in `mtext_helpers.ps1`: `Set-EntityY` / `Set-EntityX` (surgical insertion-point moves preserving every other property), `Get-MTextContentHeight` (returns both bbox value and paragraph-count estimate with a verdict flag: `OK`, `BBoxLooksBroken`, `BoxLooksStretched`, `BBoxUnusable`), and `Compute-EqualSpacedColumn` (solves equal-gap layout with configurable top/bottom margin multipliers and a minimum-gap-above-index constraint for signature lines). `mtext_creation.md` gains four new sections capturing failure modes that ate hours in real edits: the **stretched-box bug** (bbox returns box height after user grip-stretches; minimize each box to fix), the **broken-bbox bug** (leading `\pxql;` or `{\L...\P}(subtitle)` patterns produce degenerate bboxes; ask the user for the height), the **AutoCAD-COM-transiently-busy** pattern (`Documents.Count=` blank usually means a modal dialog is open, not that the document is closed — wait and retry, don't escalate), and the **PowerShell hashtable-lookup-in-foreach silently returns `$null`** gotcha (verify positions after the loop or hardcode the computed values). `stahly_plat_certificate_conventions.md` gains the **vertical column layout** section: bounds from header / sheet frame / title-block features, the **signature-line ≥ 1″ above** rule (any MText starting with `{\T...;_+}`), `Compute-EqualSpacedColumn` usage pattern, the same-X-within-column alignment discipline, and the per-column-vs-shared-gap trade-off.
- **v1.7** — `mtext_creation.md` gains **Adding rows to a paper-space legend**: legends are in paper space; copy a neighbouring row (label MText + sample line + NPLT duplicate) with `.Copy()`/`.Move()`; xref layers can't hold local objects (create a matching local layer); check the label clears the sample line; when a label wraps to two lines, move it up so the sample line runs through the vertical centre between the lines.
