# Schema: LiDAR / Remote Sensing proposals

**Status:** locked from Hilger-to-Roy proposal (production-tested).

## Typical proposal flow

1. `intro` — "We appreciate the opportunity... LiDAR survey is required along the {corridor}..."
2. `subsection_group` titled "Scope of Work" with subs:
   - **Survey Corridor** — width, fence-to-fence framing, total acreage, extra survey areas
   - **Acquisition** — sensor (Phoenix MiniRanger-3 Lite + Riegl miniVUX-3UAV is standard), AGL, ground speed, native density, classification workflow note, coordinate system, vertical datum (NAVD 88 with **Geoid 18**)
   - **Classification** — explicit HDR feature code list with category labels (e.g., "200 (Ground), 210 (Water), 230 (Road)...")
   - **Ground Truthing** — ASPRS Edition 2 Version 2 (2024), NVA/VVA checkpoint counts, USGS LBS quality level
   - **Orthophoto** — ECW format, extent statement
3. `bullet_list` (H2) titled "Scope Clarifications" — what's excluded, same-side vs opposite-side existing-line classification, etc.
4. `deliverables_list` titled "Deliverables":
   - Classified Point Cloud (LAS v1.4, two products: native + thinned ground)
   - Classification Application Notes (PDF — how each HDR code was applied)
   - Orthophoto (ECW)
   - Ground Checkpoint Report (ASPRS-compliant)
5. `assumptions_group` titled "Assumptions" with a "Site Survey" group covering:
   - Site accessibility (no snow/ice)
   - Control (provided by survey subconsultant; **Stahly places its own aerial photo control targets on the existing network and sets secondary control as needed**)
6. `paragraph` titled "Schedule" — NTP, field weeks, deliverable weeks
7. `fee_table` titled "Fees for Professional Services" — phase breakdown with workbook-pull preferred
8. `paragraph_group` titled "Changes in the Identified Scope of Services" — standard amendment language + project-specific carve-outs (e.g., existing-line classification on the opposite-side stretch as a separate fee)
9. `signature_block`

## Required intake fields beyond the base

- Approximate corridor length in miles (used in `corridor_miles` for the unit-rate footer)
- HDR feature code list to include (defaults to the standard 21-code set)
- Coordinate system + horizontal/vertical datum (defaults to Montana State Plane + NAVD 88 / Geoid 18)
- Quality level claim (defaults to USGS QL0 per LBS V1.3; **note that QL0 means NVA ≤ 10 cm RMSEz at 95% confidence — a real commitment, not marketing language**)
- Whether substation TLS is in base scope or an add-on
- Existing-line classification carve-out language (same-side miles vs total miles)

## Vocabulary to use

- "fully classified at native density" vs "thinned ground product"
- "Conductor Attachment (540)" not "attachment point"
- "Existing horizontal and vertical control... Stahly will place its own aerial photo control targets"
- "USGS LBS V1.3" or "USGS LIDAR Base Specifications V1.3"

## Vocabulary to avoid

- "PLS-CADD ready" (use "classified per HDR's feature codes for downstream PLS-CADD workflows")
- "Drone" (use "UAV" in professional context)
- "Cleanup" or "fix" (use "manual review and refinement")
