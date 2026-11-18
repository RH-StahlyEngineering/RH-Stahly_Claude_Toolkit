# Surveyor's precision and bearing notation

## Default rounding for plat output

| Quantity | Precision |
|---|---|
| Bearings | Nearest second (DMS), `N XX°XX'XX" E` format |
| Distances | 0.01 ft |
| State Plane coordinates | 0.0001 ft |
| Areas | 0.0001 acre (or 1 sq ft, whichever the user requests) |

Internal computation runs at full IEEE 754 double precision. Rounding happens only at the report boundary.

## Bearing notation

- Surveyor's bearings: angle from N/S axis, 0–90°, with quadrant letters `N`/`S` (first) and `E`/`W` (last). Example: `N 03°04'10" W`.
- Azimuth (clockwise from north, 0–360°) is used internally for modular arithmetic but never shown to the user.
- `Parse-Bearing` (in `lib/bearing_math.ps1`) accepts loose forms like `N3-4-10W`, `N 3 04 10 W`, `N 03°04'10.03" W`, etc.

## Closure / mapcheck conventions

A *closed polyline* has zero closure error by construction (start vertex = end vertex). The useful mapcheck instead:

1. Compute exact bearings/distances at full double precision.
2. Round bearings to nearest second and distances to 0.01 ft.
3. Re-inverse from POB using the rounded values.
4. The residual is the "deed reader's" closure error -- this is what survey reviewers check.

Precision ratio = perimeter / closure-error magnitude. Idaho minimum standard for boundary surveys is **1:10,000**. Excellent surveys are 1:50,000 or better. The reference parcel today (handle 15053) reports around 1:400,000.

## Vertex-coincidence tolerance

- **Coincident**: distance < 0.005 ft (~1/16 inch). This is the practical "same vertex" threshold.
- **Near-miss**: 0.005 ≤ distance ≤ 2.0 ft. Almost always indicates snap drift between adjoining polylines that needs reconciliation.
- **Unrelated**: distance > 2.0 ft. Different vertex; don't flag.

## Shared edges between adjoining parcels

Adjoining parcels wind in **opposite directions** around their shared boundary. A shared edge has bearings 180° apart in the raw data. The skill's `Bearing-DiffSeconds` and `Audit-SharedEdges` both correctly treat this as a match, not a 180° error.

## When acreage matters to the second decimal

Idaho deed acreages are typically stated to four decimal places (e.g., 20.0100). To hit this exactly:
- Target area in sq ft: 20.0100 × 43,560 = 871,635.6000.
- Acceptable residual: < 0.5 sq ft (so the rounded acreage matches).
- The `Solve-PerpShift-ForArea` solver typically achieves residuals < 1e-3 sq ft (machine precision against the constraint).
