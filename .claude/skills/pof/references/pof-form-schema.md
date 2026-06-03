# POF Form Schema

**Form URL:** https://form.jotform.com/232545214343146
**Title:** SE&A PROJECT ORDER FORM
**Recon date:** 2026-06-03
**Form lines:** 93 · **Submit button:** `#input_35`

Single-page form. All inputs live in DOM simultaneously (no page-break navigation needed during fill). The Submit button id is `input_35` — **never click during fill**, Ryan clicks it himself after verify.

## Header

| Field | qid | Input id | Type | Required | Notes |
|---|---|---|---|---|---|
| Date | id_373 | `month_373`, `day_373`, `year_373` | tel triplet | no | Auto-fill today |
| PROJECT NUMBER (4-digit client) | id_314 | `input_314` | text | no | Leave blank if unknown |
| + 5-Digit Project Number | id_315 | `input_315` | text | no | Leave blank if unknown |
| PROJECT NAME | id_4 | `input_4` | text | **yes** | |
| PROJECT DESCRIPTION | id_5 | `input_5` | textarea | no | |
| PROJECT MANAGER | id_6 | `input_6` | text | **yes** | |
| EOR/SOR | id_8 | `input_8` | text | **yes** | |
| Form Preparer | id_441 | `input_441` | text | no | **Hardcode: Ryan Harbach** |
| ESTIMATE | id_319 | `input_319` | text | **yes** | $-prefixed |
| GIVEN TO CLIENT? | id_10 | `input_10` | select | no | Yes / No |
| PM Email (hidden) | id_456 | `input_456` | email | no | shown only when... unknown trigger |
| RATE TABLE | id_11 | `input_11` | select | **yes** | Standard Billing Rates / Professional Discounted Rates |
| BILLING TERMS | id_13 | `input_13` | select | **yes** | Lump Sum / Hourly |
| TIME TO BE MOVED TO PROJECT | id_14 | `input_14` | select | **yes** | No / 0500 Misc. / Proposal / Proposals & 0500 / Client Term Project |

## Client

| Field | qid | Input id | Type | Required |
|---|---|---|---|---|
| CLIENT NAME | id_15 | `input_15` | text | **yes** |
| CLIENT ADDRESS | id_16 | `input_16` | text | no |
| CLIENT ADDRESS 2 | id_18 | `input_18` | text | no |
| CITY, STATE, ZIP | id_20 | `input_20` | text | no |
| CONTACT NAME (first/last) | id_53 | `first_53`, `last_53` | text pair | no |
| PHONE | id_22 | `input_22_full` | tel | **yes** |
| CELL | id_54 | `input_54_full` | tel | no |
| EMAIL | id_329 | `input_329` | text | no |
| Is this a new client? | id_438 | `input_438_0`/`_1` | radio | no | Yes/No |
| Client Type (hidden) | id_439 | `input_439` | select | no | shown when new client = Yes. 16 options (Log and Timber, Architect, Expert Witness, Contractor, Energy, Developer, Other Engineering, Homeowner, Law Firm, Realtor, Telecom, School, Insurance, Municipality, County) |

## Project Classification

| Field | qid | Input id | Type | Required | Default for Ryan |
|---|---|---|---|---|---|
| OFFICE REVENUE LOCATION | id_85 | `input_85` | select | **yes** | **Helena, MT** |
| DEPARTMENT (Type of Work) | id_27 | `input_27` | select | **yes** | **Survey** |
| PROJECT FUNDING TYPE | id_28 | `input_28` | select | **yes** | Private / Public |
| Grant Funded? | id_437 | `input_437_0`/`_1` | radio | no | Yes / No |
| Move Proposal to Project Folder | id_440 | `input_440_0` | checkbox | no | |
| How do you want project structure in Deltek? | id_450 | `input_450_0`/`_1` | radio | no | Phase / Phase & Task |
| How do you want invoice (billing) setup? | id_451 | `input_451_0..3` + `other_451`/`input_451` | radio | no | Project / Phase / Task / Phase & Task / Other |

Office locations: Billings MT, Bozeman MT, Cody WY, Great Falls MT, Helena MT, Cowley WY.
Departments: Architecture, Bridges, GIS, Grants/Planning, Hydraulics, Municipal, Site Development, Structural, Subdivisions, Survey, Survey - Construction, Transportation, Other.

## Phase Table (rows 1–5)

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

## Footer

| Field | qid | Input id | Type |
|---|---|---|---|
| 5+ phases? Bidding template needed | id_68 | `input_68_0`/`_1` | radio (Yes/No) |
| FORMAL AGREEMENT? | id_12 | `input_12` | select (Yes / No / Forthcoming / Sent to Accounting via DocuSign) |
| Upload contract/agreement docs | id_378 | `input_378` | file | **skip during fill — Ryan uploads manually** |
| Google Map widget | id_446 | (iframe) | widget | **skip — manual** |
| Latitude | id_430 | `input_430` | number |
| Longitude | id_431 | `input_431` | number |
| Notes/Comments for Accounting | id_432 | `input_432` | textarea |
| Upload Bidding Spreadsheet | id_448 | `input_448` | file | **skip — Ryan uploads manually** |
| Submit | id_35 | `input_35` | button | **do not click — Ryan submits** |

## Hardcoded defaults (Ryan, Survey - GIS, Helena)

Applied by `fill-pof.js` unless `pof.json` overrides:

```json
{
  "form_preparer": "Ryan Harbach",
  "email_contact": "rharbach@seaeng.com",
  "office_location": "Helena, MT",
  "department": "Survey"
}
```
