# Stahly NCS layer conventions (parcel work)

The drawings this skill targets follow National CAD Standard (NCS) layer naming. Layers commonly seen in Stahly Certificate-of-Survey work:

| Layer | Contents |
|---|---|
| `V-BNDY-PARCEL` | Subject-parcel boundary polylines and connector lines (e.g. ROW deeded lines drawn between vertices). |
| `V-BNDY-ADJA` | Adjoining-parcel boundaries (informational, not edited). |
| `V-BNDY-SECT` | PLSS section lines and subdivision-line segments. |
| `V-BNDY-SECT-TEXT` | Annotation text/labels for section lines. |
| `V-BNDY-PARCEL-CBD-SECT` | Civil 3D parcel-segment labels for section-line distances/bearings. |
| `V-BNDY-ALIQ` | Aliquot subdivision lines (within a section). |
| `V-BNDY-OLD` | Superseded boundary lines kept for reference. |
| `V-CTRL-PLSS-FND` | Found PLSS monuments (typically `AeccDbCogoPoint` + block). |
| `V-CTRL-PLSS-SET` | Set monuments. |
| `V-POWR-OHE` | Overhead power lines (often referenced in parcel work). |
| `V-TINN-BNDY` | Survey TIN boundary (often a closed polyline). |

## Inferring landmarks from layer + geometry

- **N 1/4 corner / S 1/4 corner** of a section: usually the junction point of two `V-BNDY-SECT` lines on the section's north (or south) boundary, each ~2640 ft long with slightly different bearings (the section halves rarely match exactly).
- **Section corners**: endpoints of the longest `V-BNDY-SECT` lines, often confirmed by an `AeccDbCogoPoint` on `V-CTRL-PLSS-FND` nearby.
- **Midsection (N–S)**: not always drawn. When implicit, it's the line from the N 1/4 corner to the S 1/4 corner -- compute its bearing from those coordinates.
- **ROW lines**: typically drawn as plain `AcDbLine` on `V-BNDY-PARCEL` (NOT a dedicated ROW layer in many older Stahly drawings), connecting specific parcel-polyline vertices that lie on the right-of-way edge.

## Subject vs adjoining parcels

When the user says "the 20-ac parcel" or similar, they usually mean a closed polyline on `V-BNDY-PARCEL`. Adjoining parcels are typically on `V-BNDY-ADJA`. The skill's topology audit handles them all by handle regardless of layer -- but expect the user to identify which is "the subject" from context (deed name, acreage, project number).
