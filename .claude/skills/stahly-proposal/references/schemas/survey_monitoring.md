# Schema: Survey Monitoring (settlement, dam, structure, slope, repeat-observation)

**Status:** stub — pattern derived from Aethel Wamsutter Tank Settlement
Monitoring (May 2026). Promote to "locked" after the second real proposal.

Covers any project where the deliverable is **repeat geodetic observation of
known points over time**, producing differential elevation/position data the
client uses to track movement. Typical projects:

- Above-ground storage tank settlement monitoring (API 653 Annex B input)
- Embankment dam crest/abutment monitoring
- Bridge pier or abutment settlement monitoring
- Building/foundation settlement (post-construction or distress)
- Slope movement / inclinometer + survey monitoring
- Subsidence monitoring (mining, groundwater drawdown)
- Construction settlement (pre-load period, fill placement)

## Typical proposal flow

1. `intro` — short narrative of the meeting/site and what's being requested
2. `subsection_group` titled "Project Understanding"
   - Site description (location, asset identity, year of installation)
   - Observed condition driving the monitoring (settlement, heave, tilt)
   - Stahly's role: data acquisition only (interpretation belongs to others)
3. `subsection_group` titled "Scope of Services" with subs:
   - **Mobilization & Control Establishment** (Round 1 only)
   - **Initial Baseline Survey** (Round 1)
   - **Repeat Monitoring Surveys** (Rounds 2–N)
   - **Equipment & Procedure**
   - **Measurement Marking Method**
   - **Stability Check Protocol**
   - **Deliverables (per round + final summary)**
4. `subsection_group` titled "Schedule"
5. `bullet_list` titled "Assumptions"
6. `bullet_list` titled "Exclusions"
7. (Standard close: Standard of Care, Fees, Changes, Signature)

## Vocabulary

- "Differential leveling" (not "level survey")
- "Loop closure" (not "loop error" or "misclose")
- "Settlement monitoring" (not "settlement survey")
- "Permanent benchmark monument" (not "control point")
- "Repeatable measurement point" (not "reference point")
- "Surveyor of Record" (the licensed PLS sealing each report; distinct from
  the PM)
- "Round 1 / Round 2 / ..." (not "Phase 1 / Phase 2 / ..." — the bid
  workbook uses Phase for billing structure, but the deliverable language
  uses Round to keep the client picture clean)
- "Differential change" between rounds (not "movement" — interpretation
  belongs to the client/engineer)
- "Data suitable for API 653 Annex B evaluation by others" (the disclaim
  phrasing when work informs API 653 settlement evaluation, used in the
  tank case)

## Default values to bake into intake / SOW

These are reasonable starting points for tank settlement monitoring. Adjust
per project; always present as defaults the user can override.

| Parameter | Default | Notes |
|---|---|---|
| Benchmark count | 3 | Two-BM minimum is the bare minimum; three lets you detect a moving control point via pairwise comparison |
| Benchmark depth | 48" steel rod driven to refusal | Berntsen catalog rod + cap |
| BM protection | T-post adjacent | Discourages disturbance |
| BM spatial diversity | Bearings + offsets vary; not all in suspected influence zone | Single localized ground movement should disturb ≤ 1 monument |
| Chime / measurement points | ≥ 8 around perimeter | Tank: ≥ 2 within reported settlement zone |
| Marking method | Drilled-and-set hardened survey nail in epoxy | Better repeatability than surface-bonded disc; no welding requirement |
| Instrument | Digital electronic level, bar-coded invar staves | E.g., Trimble DiNi |
| Loop closure target | **≤ 0.005 ft** (≈ 1/16") | Tank / structure monitoring needs to resolve sub-inch differential. Third-order leveling (0.01√setups) is too loose. |
| Redundancy | Two setups per point where geometry permits; reconcile > 0.005 ft on-site | |
| Crew size | 2 people | Instrument operator + rod runner |
| Datum | NAVD88 (Geoid18) via OPUS-Static on BM-1 (2-hr session min) | Local datum if OPUS coverage unavailable; document the choice |
| Round interval | Quarterly with ±2-week window | Adjust per client |
| Report turnaround | 10 business days from field date | |
| Reschedule allowance | 0 (T&M after window) or 1/round | Per client preference; default 0 |

## Stability check protocol (load-bearing — include verbatim or close)

For 3+ benchmark networks, the Round-over-Round stability check:

```
At start of each round, compute pairwise elevation differences between all
benchmarks (e.g. ΔBM₁₋₂, ΔBM₁₋₃, ΔBM₂₋₃) and compare against the Round 1
baseline differences:

  - If all pairwise differences agree to within 0.005 ft of baseline →
    network intact; reduce chime elevations normally.
  - If exactly one pairwise difference disagrees while the other two agree
    → the implicated monument is presumed disturbed and excluded from
    the round's reduction; remaining BMs are held as stable; document
    in the round report.
  - If two or more pairwise differences disagree → field work pauses
    pending consultation; no chime elevations are reported until the
    network is reconciled.
```

## OPUS knowledge

For absolute datum tie (NAVD88), use NGS OPUS:

- **OPUS-Static:** minimum 2 hours, max 48 hours. Standard service, available
  everywhere CONUS. Vertical: 2–5 cm at 95% confidence — coarser than the
  differential-level loop, but adequate for credentialing the absolute datum.
- **OPUS-RS (Rapid Static):** minimum 15 minutes, max 2 hours. Requires
  sufficient CORS station density (~250 km). Coverage map: NGS publishes it
  — verify before promising. Rural areas (e.g., Wamsutter, WY) are hit-or-miss.
- **OPUS-Projects:** for multi-day campaigns; not typically used for
  monitoring single-point setups.

**Important:** differential monitoring between rounds relies on the
diff-leveling closure (≤ 0.005 ft), not OPUS precision. OPUS exists to
credential the absolute datum, not to detect motion.

Default to OPUS-Static (2-hr) unless RS coverage has been verified.
Schedule it during Trip 1: deploy receiver on arrival → 2-hour static session
runs while crew sets BM-2 / BM-3 and starts chime nail installation → tear
down before driving home.

## Standard exclusions (boilerplate)

Always include unless explicitly added to scope:

- Interior tank/structure measurements (the API 653 Annex B *internal* floor
  survey is a separate scope)
- Structural plumbness, roundness, out-of-roundness (API 653 § 12)
- Roof elevation or roof drainage survey
- Structural, geotechnical, or fitness-for-service engineering
  interpretation of the elevation data
- API 653 inspector services, certified tank inspection, NDE
- Settlement modeling, planar/cosine settlement decomposition, or
  differential-settlement evaluation per API 653 Annex B
- Geotechnical investigation (borings, CPT, soil sampling)
- Hot work, welding, confined-space entry, hot-work permits, fall
  protection above 4 feet
- Re-establishment of monuments or measurement points damaged or removed
  between rounds (additional T&M after written authorization)
- Additional rounds beyond the contracted round count

## Disclaim phrasing for API 653 / engineering interpretation

> Services will be performed in accordance with the standard of care
> customary for professional land surveying services performed in the
> [State] at the time and location the services are rendered. Survey work
> will be performed under the responsible charge of a Professional Land
> Surveyor licensed in [State]. **No warranty, express or implied, is given
> as to the future performance of the [asset] or its foundation.** Data
> produced by this scope is suitable for API 653 Annex B evaluation by
> others if the client elects to perform such evaluation; that evaluation
> is not included.

## Open questions to resolve before locking the schema

- Standard contract language when the same engineer is both PM and SOR
  (Aethel case — Kosine wore both hats)?
- Do we need a "trigger-level" clause? (i.e., if total differential
  settlement exceeds X inches between rounds, Stahly notifies the client
  within Y business days outside the normal report cadence)
- Photography requirement at each measurement point — formalize as part
  of standard procedure?
- Standard escalation protocol when monument network fails the stability
  check (currently "pauses pending consultation" — by what mechanism
  exactly)?
