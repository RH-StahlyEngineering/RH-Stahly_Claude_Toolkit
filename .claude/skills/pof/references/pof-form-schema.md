# POF Form Schema (+ Mosaic chained form)

**Form URL:** https://form.jotform.com/232545214343146
**Title:** SE&A PROJECT ORDER FORM
**Recon date:** 2026-06-03 (updated through real fill on 2026-06-03)
**Form lines:** 93 · **Submit button:** `#input_35`

**Multi-page form** (4 pages): Header → Client → Phase rows → Final/notes. Navigate via `.form-pagebreak-next` buttons. Don't trust earlier docs that called this single-page — that was a recon miss (the page-break buttons were misidentified as JotForm-editor residuals).

The Submit button id is `input_35` — **never click during fill**. Ryan clicks it himself after the visual verify pass. **Submit triggers a redirect to the chained Mosaic Planning Set Up Sheet** (see bottom of this doc).

## Header (page 1)

| Field | qid | Input id | Type | Required | Notes |
|---|---|---|---|---|---|
| Date | id_373 | `month_373`, `day_373`, `year_373` | tel triplet | no | Auto-fill today |
| PROJECT NUMBER (4-digit client) | id_314 | `input_314` | text | no | From PM / Stahly client list |
| + 5-Digit Project Number | id_315 | `input_315` | text | no | **Leave blank — Accounting assigns** |
| PROJECT NAME | id_4 | `input_4` | text | **yes** | |
| PROJECT DESCRIPTION | id_5 | `input_5` | textarea | no | |
| PROJECT MANAGER | id_6 | `input_6` | text | **yes** | |
| EOR/SOR | id_8 | `input_8` | text | **yes** | |
| Form Preparer | id_441 | `input_441` | text | no | **Default: Ryan Harbach** |
| ESTIMATE | id_319 | `input_319` | text | **yes** | $-prefixed (e.g. `$78,900`) |
| GIVEN TO CLIENT? | id_10 | `input_10` | select | no | Yes / No |
| PM Email | id_456 | `input_456` | email | no | Shown on **multi-page POFs** (which the live form is). **Default: rharbach@seaeng.com** |
| RATE TABLE | id_11 | `input_11` | select | **yes** | Standard Billing Rates / Professional Discounted Rates |
| BILLING TERMS | id_13 | `input_13` | select | **yes** | Lump Sum / Hourly. For mixed-basis projects, fill-pof.js auto-derives the **dominant-by-dollar** choice from `rows[].pay` totals. |
| TIME TO BE MOVED TO PROJECT | id_14 | `input_14` | select | **yes** | No / 0500 Misc. / Proposal / Proposals & 0500 / Client Term Project |

## Client (page 2)

| Field | qid | Input id | Type | Required | Notes |
|---|---|---|---|---|---|
| CLIENT NAME | id_15 | `input_15` | text | **yes** | |
| CLIENT ADDRESS | id_16 | `input_16` | text | no | |
| CLIENT ADDRESS 2 | id_18 | `input_18` | text | no | |
| CITY, STATE, ZIP | id_20 | `input_20` | text | no | |
| CONTACT NAME (first/last) | id_53 | `first_53`, `last_53` | text pair | no | |
| PHONE | id_22 | `input_22_full` | tel | **yes** | Form auto-formats `4065551234` → `(406) 555-1234`. `verify-pof.js` normalizes both sides to digits-only. |
| CELL | id_54 | `input_54_full` | tel | no | Same auto-format. |
| EMAIL | id_329 | `input_329` | text | no | |
| Is this a new client? | id_438 | `input_438_0`/`_1` | radio | no | Yes/No |
| Client Type (hidden) | id_439 | `input_439` | select | no | Shown when `is_new_client = Yes`. Options: Log and Timber, Architect, Expert Witness, Contractor, Energy, Developer, Other Engineering, Homeowner, Law Firm, Realtor, Telecom, School, Insurance, Municipality, County. **For rural electric / utility cooperatives, use "Energy" — closest match.** |

## Project Classification (page 3)

| Field | qid | Input id | Type | Required | Notes |
|---|---|---|---|---|---|
| OFFICE REVENUE LOCATION | id_85 | `input_85` | select | **yes** | Auto-derive from project path's city; do NOT hardcode a single-office default |
| DEPARTMENT (Type of Work) | id_27 | `input_27` | select | **yes** | **Default: Survey** |
| PROJECT FUNDING TYPE | id_28 | `input_28` | select | **yes** | Private / Public |
| Grant Funded? | id_437 | `input_437_0`/`_1` | radio | no | Yes / No |
| Move Proposal to Project Folder | id_440 | `input_440_0` | checkbox | no | Set true when proposal PDF already lives in the project folder |
| How do you want project structure in Deltek? | id_450 | `input_450_0`/`_1` | radio | no | Phase / Phase & Task |
| How do you want invoice (billing) setup? | id_451 | `input_451_0..3` + `other_451`/`input_451` | radio | no | Project / Phase / Task / Phase & Task / Other. **When `deltek_structure=Phase` AND row pay types are mixed, recommend Phase** (so T&M-NTE phases bill separately from lump-sum). |

**Office locations** (per the form's dropdown — confirm in form if Stahly opens/closes offices): Billings MT, Bozeman MT, Great Falls MT, Helena MT. *Cody, WY closed in 2026 — references to "Cody" or "Cowley WY" in older docs should be ignored.*

**Departments:** Architecture, Bridges, GIS, Grants/Planning, Hydraulics, Municipal, Site Development, Structural, Subdivisions, Survey, Survey - Construction, Transportation, Other.

## Phase Table (page 3, rows 1–5)

Each row has 9 columns. Column suffix on the qid changes per row.

| Column | Row 1 qid | Row 2 | Row 3 | Row 4 | Row 5 |
|---|---|---|---|---|---|
| Phases | id_255 | id_379 | id_389 | id_399 | id_409 |
| Tasks | id_256 | id_380 | id_390 | id_400 | id_410 |
| Start Date | id_257 | id_381 | id_391 | id_401 | id_411 |
| End Date | id_258 | id_382 | id_392 | id_402 | id_412 |
| Labor Budget | id_376 | id_383 | id_393 | id_403 | id_413 |
| Expenses/Sub Budget | id_377 | id_384 | id_394 | id_404 | id_414 |
| Total Budget | id_320 | id_385 | id_395 | id_405 | id_415 |
| Lump Sum/Hourly (select) | id_260 | id_386 | id_396 | id_406 | id_416 |
| EOR/SOR | id_261 | id_387 | id_397 | id_407 | id_417 |
| Dept (select) | id_262 | id_388 | id_398 | id_408 | id_418 |

Input ids follow the pattern `input_<qid_number>`. e.g. Row 1 Phases = `input_255`.

**Row date columns (Start/End) use a MM/DD/YYYY mask** — `fill-pof.js` uses the `date_masked` kind for these (sends zero-padded `MMDDYYYY` per-character via keyboard events). Setting `el.value="6/3/2026"` directly gets mangled to `63/20/26__`.

**Row 3 and Row 5 Department selects (`input_398`, `input_418`) are missing the "Architecture" option** that Rows 1, 2, 4 have. Form defect — use a different row if Architecture is needed there.

## Footer (page 4)

| Field | qid | Input id | Type | Notes |
|---|---|---|---|---|
| 5+ phases? Bidding template needed | id_68 | `input_68_0`/`_1` | radio | Yes/No |
| FORMAL AGREEMENT? | id_12 | `input_12` | select | Yes / No / Forthcoming / Sent to Accounting via DocuSign |
| Upload contract/agreement docs | id_378 | `input_378` | file | **Skip during fill — Ryan uploads manually** |
| Google Map widget | id_446 | (iframe) | widget | **Skip — manual; or paste lat/long below** |
| Latitude | id_430 | `input_430` | number | |
| Longitude | id_431 | `input_431` | number | |
| Notes/Comments for Accounting | id_432 | `input_432` | textarea | **Convention:** when a project has > 5 phases, capture overflow phase data here as a labeled row-style block matching the form's columns (Phase / Start Date / End Date / Labor Budget / Expenses/Sub Budget / Total Budget / Lump Sum/Hourly / EOR/SOR / Department). NOT free-form prose, NOT a workbook correlation table. |
| Upload Bidding Spreadsheet | id_448 | `input_448` | file | **Skip — Ryan uploads manually** |
| Submit | id_35 | `input_35` | button | **Do not click — Ryan submits. Note: Submit triggers Mosaic chained form.** |

## Hardcoded defaults (Ryan, Survey - GIS)

Applied by `fill-pof.js` unless `pof.json` overrides:

```json
{
  "form_preparer": "Ryan Harbach",
  "pm_email": "rharbach@seaeng.com",
  "department": "Survey"
}
```

Office location is intentionally NOT hardcoded — derive at gather time from the project path's city (`Survey - GIS/<YYYY>/<City>/<NNN>/`).

---

# Mosaic Planning Set Up Sheet (chained form)

**Form URL:** https://form.jotform.com/231225238538051
**Title:** Mosaic Planning Set Up Sheet
**Triggered by:** Clicking Submit on the POF (form `232545214343146`). The POF redirects to this URL with the POF data passed as query-string prefill.

The user lands on a "Start Filling" cover screen first. `fill-mosaic.js` auto-clicks it. After that the form is **single-page** (no Next buttons; just Submit).

## Mosaic header (auto-prefilled from POF query params)

| Field | Input id | Source |
|---|---|---|
| Date | `month_57`, `day_57`, `year_57` | POF date |
| Project Manager | `input_2` | POF `project_manager` |
| Project Number - 4 Digit Client Number | `input_17` | POF `project_number_4digit` |
| + 5 Digit Project Number | `input_18` | POF `project_number_5digit` (typically blank) |
| Project Name | `input_6` | POF `project_name` |

## Mosaic phase rows (5 rows, mirrors POF phase table)

| Column | Row 1 | Row 2 | Row 3 | Row 4 | Row 5 |
|---|---|---|---|---|---|
| Phase | `input_20` | `input_29` | `input_39` | `input_48` | `input_58` |
| Task | `input_21` | `input_31` | `input_40` | `input_49` | `input_60` |
| Est. Start Date | `input_22` | `input_32` | `input_41` | `input_50` | `input_61` |
| Est. End Date | `input_23` | `input_33` | `input_42` | `input_51` | `input_62` |
| Total Budget | `input_24` | `input_34` | `input_43` | `input_52` | `input_63` |
| Who | `input_25` | `input_35` | `input_44` | `input_53` | `input_64` |
| % of Budget | `input_26` | `input_36` | `input_45` | `input_54` | `input_65` |
| Phase Row N - Additional Team Scheduling (widget) | `id_28` (qid 28) | `id_37` (qid 37) | `id_46` (qid 46) | `id_55` (qid 55) | `id_66` (qid 66) |

**Column label inconsistency:** Row 1 calls the column "%Budget or #Hours"; Rows 2–5 call it "% of Budget". Same field, different labels.

**Row-position vs phase-number:** the widget qids correspond to **row positions** (1–5), not project phase numbers. When phases are reordered (e.g., dropping Phase 1 to fit a 6-phase project in 5 rows, so Phases 2–6 land in Rows 1–5), the widget at qid 37 is for the Phase in Row 2 — not the project's Phase 2. Always verify by reading the row's Phase field.

## Additional Team Scheduling widget (Configurable List)

Each Mosaic phase row has a widget below it for additional team members. The widget is a JotForm Configurable List rendered as a **cross-origin iframe** (`https://widgets.jotform.io/configurableList/index.html?qid=<qid>`).

**Reachable via `page.frames()` + `frame.evaluate()`** — CDP bypasses same-origin policy. See `references/dev-browser-quirks.md`.

Structure:
- 3 text columns per row: **Who / % of Budget / # of Manhours**
- "+ Add Row" button to extend
- Hidden "x" remove buttons per row (clickable via `.click()` even when `offsetParent==null`)
- Starts with 1 default empty row

**Amy at Accounting (2026-06-03) clarification:** the first widget row is NOT a header — it's a data row, same format as rows added via "+ Add Row". When a phase has multiple staff, the outer Who/% pair captures one person; the widget captures the rest.

**Sum-to-100% rule:** the outer "% of Budget" plus the widget rows' "% of Budget" entries should sum to 100% per phase. `verify-mosaic.js` enforces this.

## Mosaic Submit

There's a single Submit button on Mosaic — final step in the project setup chain. After Submit, Mosaic returns its own confirmation page.
