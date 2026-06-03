# Third-party preconditions in the Schedule + Assumptions sections

**When to use:** Whenever the project's start or progress depends on a deliverable from a third party (not Stahly, not the client) — control survey from a surveying subconsultant, permits from a regulatory agency, sample data from a design engineer, ROW clearance from a landowner, equipment from a vendor. If the third party slips, the schedule slips and we need the proposal to make that dependency explicit, not implied.

**Why explicit:** A schedule paragraph that says "fieldwork begins June 22" without naming preconditions reads as a commitment from Stahly. If the precondition fails, the client may blame us for the slip even though we couldn't act. Naming the precondition shifts the dependency where it belongs.

**Pattern — two homes for the same precondition:**

1. **Schedule paragraph** — names the precondition inline with the date commitment.
2. **Assumptions section** — lists the precondition as an assumption Stahly is making about the world (separately from the schedule).

The two locations cover different reader contexts: someone scanning for "when does field start" sees the precondition in Schedule; someone auditing assumptions sees it in Assumptions.

**Sample language (Hilger-Roy, 2026-06-01):**

Schedule paragraph:
> Subject to notice to proceed by Friday, June 12, 2026, and receipt of survey control from Arrow Creek Surveying prior to the start of fieldwork, fieldwork is anticipated to begin Monday, June 22, 2026 and complete within four weeks. Survey deliverables are targeted for Monday, August 10, 2026, with best-effort delivery on Monday, August 3, 2026, weather permitting.

Site Survey assumption:
> Existing horizontal and vertical control will be provided by Arrow Creek Surveying prior to the start of fieldwork. Stahly will place its own aerial photo control targets at Arrow Creek's existing control points and will set additional secondary control where needed for full corridor coverage.

**Reusable template:**

Schedule paragraph: `Subject to [NTP CONDITION], and [PRECONDITION 1, framed as something the third party must deliver before we can proceed], [and ADDITIONAL PRECONDITIONS as needed], fieldwork is anticipated to begin [DATE] and complete within [DURATION]. [DELIVERABLE TIMING].`

Assumption bullet: `[THIRD PARTY] will [DELIVER X] prior to [STAHLY ACTION THAT REQUIRES IT]. Stahly will [WHAT WE'LL DO ONCE IT'S RECEIVED].`

**Common preconditions in Stahly proposals:**

| Project type | Common preconditions |
|---|---|
| LiDAR / aerial survey | Survey control from subconsultant; landowner access; airspace authorization; equipment availability |
| Topographic / boundary survey | Title research; monument retracement; client-provided base maps |
| Construction staking | Approved IFC drawings; permits from agency |
| Lidar with design engineer | Sample deliverable / feature-code legend from design engineer; PLS-CADD spec |
| Survey on federal land | NEPA clearance; cultural resource clearance; permit issuance |

**What NOT to put in:**

- Stahly's own internal logistics (equipment procurement, crew availability) — that's our problem to solve, not a client-facing precondition. See SKILL.md rule #8.
- Soft commitments without consequence ("weather permitting" is OK because it's framed as a natural condition; "subject to favorable conditions" is not OK because it's vague).
- Conditions that have already been satisfied at proposal time — those go in Assumptions only, not Schedule.
