# Schema: General Survey (boundary, ROW, topographic, ALTA, utility)

**Status:** stub — pattern derived from civil/survey reference proposal, not yet production-tested. Promote to "locked" after first real proposal.

## Typical proposal flow

1. `intro`
2. `subsection_group` titled "Survey Scope of Work" with relevant subs (include only those that apply):
   - **Boundary Retracement** — monuments to recover/set, alignment basis, dimensions
   - **ROW Line Staking** — stations of ROW lines, one-time vs reference stakes
   - **Topographic Survey** — contour interval, limits, target features
   - **Utility Survey** — sanitary/storm/water/gas/electric, sub-surface utility scope, OneCall coordination
   - **ALTA** (if ALTA/NSPS) — Table A items, certification
   - **Control** — vertical and horizontal datum, monuments to be set
3. `bullet_list` (H2) titled "Deliverables" inside the Survey Scope subsection group, or break out as its own H1
4. `bullet_list` (H1 or H2) titled "Exclusions"
5. (continue with rest of standard flow: Assumptions, Schedule, Fees, Changes, Signature)

## Vocabulary

- "Survey-grade orthophoto" not "drone map"
- "Land Surveyor in Charge" + P.L.S. credential
- "Plat" not "drawing"
- ASPRS Edition 2 Version 2 (2024) for any accuracy claims

## Open questions to resolve before production use

- Does the body need a dedicated "Field Methods" subsection or can it stay implicit?
- Standard schedule language for a topo survey (3-5 days field, 2-3 weeks deliverable)?
- Default fee mode — LS callout or per-acre/per-mile rate?
