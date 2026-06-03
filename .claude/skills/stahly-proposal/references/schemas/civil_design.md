# Schema: Civil Design proposals

**Status:** stub — derived from City of Great Falls 8th Ave NW 11th–14th St proposal pattern, not yet production-tested through this skill. Promote to "locked" after first real proposal.

## Typical proposal flow

1. `intro`
2. `subsection_group` titled "Civil Engineering and Design Scope of Work" with subs lettered A/B/C/D, including:
   - **A. Preliminary Design & 50% Construction Documents** — PM tasks, MPWSS edition, 50% CD set contents (plans, reports, computations, specifications), 50% deliverable count
   - **B. Final Plan Set (100% CDs)** — attend coordination meeting, review/address 50% CD review comments, 100% CD set contents
   - **C. Bidding Services** — bid documents, addenda, RFI response, bid tabulation, recommend award
   - **D. Construction Administration Assistance** — usually time-and-materials, listed as separate basis from base lump sum
3. `bullet_list` "Deliverables" (often listed in-line with each subsection above, not as a separate section)
4. `paragraph` "Geotechnical Investigation" (often subcontracted to Terracon; specify boring count + scope)
5. `bullet_list` "Exclusions"
6. `paragraph` "Project Schedule and Deliverables"
7. `fee_callout` or simple list of phase fees (often by subsection A/B/C/D rather than by labor/expense)
8. `signature_block`

## Vocabulary

- "MPWSS" (Montana Public Works Standard Specifications), include the edition
- "50% CDs" / "100% CDs" — Construction Documents at each milestone
- "City of [X] supplements to MPWSS" if applicable
- "Notice to Proceed (NTP)" for schedule references

## Open questions to resolve before production use

- Standard fee structure: typically LS for design phases + T&M for construction admin — how to render in the table?
- Whether to include a dedicated bid item count table
- Geotech: included or excluded by default?
