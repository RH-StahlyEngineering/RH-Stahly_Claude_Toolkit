# Closure-report PDF conventions

What the closure-report script does, what's tunable, and the conventions baked into the output.

## What it produces

A multi-page PDF (one parcel per page, plus a cover) containing for each parcel:

1. **Header** with the human-readable parcel name (e.g. "Tract 2", "COS 1999-02")
2. **Metadata strip**: handle, layer, vertex count
3. **Sketch** of the parcel: closed polyline, POB marker, first-leg direction arrow, sparse vertex labels, north arrow, scale bar
4. **Closure summary table**: POB coords, raw area, perimeter, dN/dE misclose, error distance, error bearing, precision (1:N)
5. **Course table**: numbered list of bearings + distances. Auto-splits into 2 columns when > 22 courses.

## The math: rounded-then-re-inversed closure

The closure number is **not** the raw polygon's machine-precision residual (which is zero for a CAD-closed polyline by construction). Instead:

1. Round each course's bearing to nearest second and each distance to 0.01 ft.
2. Re-inverse from the POB using the rounded values.
3. The vector between the re-inversed endpoint and the POB is the **closure error** that a deed reader would compute by hand.

This is what surveyors and reviewers actually check. A polyline that's geometrically closed in CAD can still have a meaningful "deed-level" misclosure because labels are rounded.

## POB selection — caller controls it

The script does NOT pick the POB. You pass the parcel data with vertices already in the desired order, and v[0] is the POB. Rotate / reverse before passing if needed.

Common POB conventions to specify when describing:
- NE corner, first leg south (typical for tracts described east-side-first)
- SW corner, first leg east
- A specific monument, first leg in a specific direction

Use the helper pattern from `tools/reorder_pobs.py` style logic (rotate the vertex list so the chosen POB is index 0, and reverse the array if the desired first-leg direction is opposite of the natural CCW traversal).

## Sketch layout decisions

The sketch builder picks figure aspect based on the parcel's bounding box:
- **Wide parcels** (aspect > 1.7): full-width sketch on top, closure table below
- **Tall or square parcels** (aspect ≤ 1.7): side-by-side, sketch on left, closure table on right

The **N arrow** lands in the corner farthest from the POB (so they never overlap):
- POB at NE → N arrow at NW
- POB at NW → N arrow at NE
- POB at SE → N arrow at NE (top, since N is up)
- POB at SW → N arrow at NW
- POB at top of frame → N arrow drops to bottom

The **scale bar** is centered along the bottom. It uses a 1-2-5 series step picked at roughly 1/5 of the X-range.

The **POB direction arrow** is sized at ~12% of the parcel's longer dimension and points toward the second vertex.

**Vertex labels** are placed with a collision-avoidance pass: only label a vertex if no previously-labeled vertex is within 6% of the parcel's longer dimension. Caps at ~12 labels. POB is always labeled (and skipped from the numeric labels since it has its own "POB" callout).

## Coordinates and units

The script assumes drawing units are **US Survey Feet** and that bearings are in standard surveyor's notation. Areas are reported in sq ft and acres (sq ft ÷ 43560).

## Required reference docs

The model should treat these as binding for output formatting:
- `references/plat_precision.md` — bearing/distance/coord rounding rules
- `references/stahly_layers.md` — naming conventions (e.g. parcel polylines live on `V-BNDY-PARCEL`)

## Defaults

| Setting | Default |
|---|---|
| Output path | `<workdir>/closure_report.pdf` |
| Page size | US Letter |
| Sketch resolution | 185 DPI PNG |
| Bearing precision in tables | nearest second |
| Distance precision in tables | 0.01 ft |
| Cover index columns | Header, Handle, Vertices, Raw Area (ac) |

All overridable via script parameters.

## When to use vs not

Use for:
- Mapcheck / closure reports for legal descriptions
- Pre-delivery QC on a set of parcels
- Plat review packages

Don't use for:
- A single-parcel one-off — `scripts/mapcheck.ps1` already prints to console
- Continuous live monitoring (the report is a snapshot)
- Anything where the model can't supply or compute a sensible POB ordering — fix the data first
