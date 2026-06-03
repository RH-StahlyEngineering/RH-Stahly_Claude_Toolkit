---
name: pof
description: Fill out Stahly Engineering's JotForm Project Order Form (POF) at https://form.jotform.com/232545214343146 from a structured pof.json. Survey - GIS specific. Also drives the chained Mosaic Planning Set Up Sheet that opens after POF Submit. Use when the user says "new POF", "fill out the POF", "project order form", "start a POF for <client>", or otherwise asks to open/file/start the JotForm POF for a new Stahly survey project.
---

# Project Order Form (POF) — Survey - GIS

Fills https://form.jotform.com/232545214343146 in a live Chrome tab via `dev-browser`. Modeled after `skills/timesheet`: Gather → preflight → fill → verify → hand off the Submit click to the user. **POF Submit chains to a second form** (Mosaic Planning Set Up Sheet at `form.jotform.com/231225238538051`) — see Mode 3 below.

## Where pof.json lives

Per-project, inside the bid folder:

```
\\Stahly\marketing\Scope-Schedule-Budget\Survey - GIS\<YYYY>\<City>\<NNN-Project_Name>\pof.json
```

Cities currently active: Billings, Bozeman, Great Falls, Helena. (Cody, WY closed in 2026 — don't pick it as an office location.) Projects numbered `001-...`, `002-...`, etc.

On first run for a project, ask the user for year + city + project (or infer from working directory / recent conversation), then create `pof.json` if absent or load the existing one.

## Hardcoded defaults

`fill-pof.js` applies these unless `pof.json` provides a value:

| Field | Default |
|---|---|
| `form_preparer` | Ryan Harbach |
| `pm_email` | rharbach@seaeng.com |
| `department` | Survey |

**`office_location` is NOT hardcoded** — derive at gather time from the project path's `<City>` segment (the city folder under `Survey - GIS/<YYYY>/`). A static Helena default was misleading for every non-Helena project; the path is the source of truth.

`project_manager`, `eor_sor`, estimate, billing terms, client info, phases, etc. are **always asked** (or derived from the bid workbook / proposal).

## pof.json shape

Flat object plus a `rows[]` array for the phase table (1–5 rows). Mosaic-specific extras (`mosaic_rows_use`, `rows[i].team`) are documented in the Mode 3 section. All values are strings as the form expects them, or booleans for checkboxes. Empty/missing keys are skipped by the filler.

```json
{
  "date_month": "06", "date_day": "03", "date_year": "2026",
  "project_number_4digit": "3186",
  "project_number_5digit": "",
  "project_name": "Hilger to Roy Substation LiDAR",
  "project_description": "LiDAR + photogrammetry corridor survey ...",
  "project_manager": "Ryan Harbach",
  "eor_sor": "Ryan Harbach, P.L.S.",
  "form_preparer": "Ryan Harbach",
  "pm_email": "rharbach@seaeng.com",
  "estimate": "$78,900",
  "given_to_client": "Yes",
  "rate_table": "Standard Billing Rates",
  "billing_terms": "Lump Sum",
  "time_to_be_moved_to_project": "Proposal",
  "client_name": "Fergus Electric Cooperative, Inc.",
  "client_address1": "84423 US Highway 87",
  "client_address2": "",
  "client_city_state_zip": "Lewistown, MT 59457",
  "contact_first": "Melanie", "contact_last": "Foran",
  "phone": "4065383465",
  "cell": "",
  "email": "mforan@ferguselectric.coop",
  "is_new_client": "No",
  "client_type": "",
  "office_location": "Great Falls, MT",
  "department": "Survey",
  "funding_type": "Private",
  "grant_funded": "No",
  "move_proposal_to_project_folder": true,
  "deltek_structure": "Phase",
  "invoice_setup": "Phase",
  "rows": [
    {
      "phase": "1. PM / Admin / QA-QC", "task": "",
      "start": "6/3/2026", "end": "8/10/2026",
      "labor": "5000", "expenses": "", "total": "5000",
      "pay": "Lump Sum", "eor": "Ryan Harbach", "dept": "Survey",
      "team": [{ "who": "Ryan Harbach", "hours": 30 }]
    }
  ],
  "more_than_5": "No",
  "formal_agreement": "Sent to Accounting via DocuSign",
  "latitude": "",
  "longitude": "",
  "notes_for_accounting": ""
}
```

Allowed values for selects/radios are in `references/pof-form-schema.md`. Most-used:
- `rate_table`: `Standard Billing Rates` | `Professional Discounted Rates`
- `billing_terms`, `rows[].pay`: `Lump Sum` | `Hourly`
- `time_to_be_moved_to_project`: `No` | `0500 Misc.` | `Proposal` | `Proposals & 0500` | `Client Term Project`
- `department`, `rows[].dept`: see schema (Survey is the surveyor default; Survey - Construction is the other common one)
- `funding_type`: `Private` | `Public`
- `formal_agreement`: `Yes` | `No` | `Forthcoming` | `Sent to Accounting via DocuSign`
- `is_new_client`, `grant_funded`, `more_than_5`: `Yes` | `No`
- `deltek_structure`: `Phase` | `Phase & Task`
- `invoice_setup`: `Project` | `Phase` | `Task` | `Phase & Task`

## Top-of-session rules (hard rules)

1. **All arithmetic programmatic.** Every total, percentage, or rounding goes through `python3 -c "..."` — never mental math. Mosaic and accounting reconcile against these numbers, so a single mental-math slip causes downstream cleanup.
2. **Submit is the user's click.** Never click `#input_35` (POF submit) or Mosaic's submit. Verify-after-fill is mandatory, but the user reviews on screen before submitting.
3. **Warn before POF Submit.** Submitting the POF redirects Chrome to the Mosaic form with all POF data passed as URL prefill. The user should know this is coming, especially because file uploads (`input_378` contract, `input_448` bid spreadsheet) need to happen before submit or they're lost. Surface the warning before they reach for Submit.
4. **dev-browser is QuickJS, not Node.** See `references/dev-browser-quirks.md`. No `import`, no `fs`, no `process`. Stage host files via the embed-JSON pattern in `references/staging-pattern.md`.
5. **Walk the POF as multi-page.** 4 pages (Header → Client → Phase rows → Final). Use `.form-pagebreak-next` to advance. Earlier docs called this single-page — wrong. The fill script populates all pages because they all exist in the DOM, but visual review must walk each page.
6. **5-row phase table is a hard limit.** When a project has 6+ phases, choose 5 rows to display and capture the overflow phase in `notes_for_accounting` as a labeled row-style block (Phase / Start Date / End Date / Labor Budget / Expenses/Sub Budget / Total Budget / Lump Sum/Hourly / EOR/SOR / Department). Don't combine phases unless they're truly the same work. Pick which 5 are highest-value for Accounting.

## Phase 0 — Prerequisites (run every session)

PowerShell preferred.

1. **dev-browser on PATH.** Run `dev-browser --help` (NOT `--version` — that flag doesn't exist) to confirm install. If missing: `npm i -g dev-browser`. On Windows, the global shim lives in `C:\Users\rharbach\AppData\Roaming\npm` — that path must be in `PATH` for `dev-browser` to resolve from Bash. Quick fix in a Bash session: `export PATH="/c/Users/rharbach/AppData/Roaming/npm:$PATH"`.
2. **CDP on :9222.** `Invoke-WebRequest http://127.0.0.1:9222/json/version` (or `curl -s http://127.0.0.1:9222/json/version`) must return JSON. If 404 or refused, kill Chrome and relaunch with the debug profile:
   ```powershell
   Get-Process chrome -ErrorAction SilentlyContinue | Stop-Process -Force
   Start-Process "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe" `
     -ArgumentList "--remote-debugging-port=9222","--remote-allow-origins=*",`
     "--user-data-dir=C:\Users\rharbach\.chrome-debug-profile",`
     "https://form.jotform.com/232545214343146"
   ```
3. **JotForm tab present.** Tab list should include a URL containing `form.jotform.com`. Use that broader filter (not the specific POF or Mosaic form ID) so the same code survives the POF→Mosaic chain.

Bail if any check fails.

## Mode 1 — Gather

Build `pof.json` conversationally. Read existing `pof.json` first if it's there.

- **Apply hardcoded defaults silently** (form_preparer, pm_email, department).
- **Derive office_location from the project path** (`Survey - GIS/<YYYY>/<City>/`) — don't ask.
- **Always ask** for project-specific items not derivable: project_name, description, PM, EOR/SOR, estimate, client info, phases.
- **Enter what you can before asking.** If most info is provided but one row's department is ambiguous, fill the rest, mark blocked entries, ask only the open question.
- **For 4-digit project number:** ask the PM if the client number is known. If not, leave blank.
- **For 5-digit project number: always blank.** Accounting assigns it after submission. Document this so users don't fabricate a value.
- **For `client_type` on rural electric / utility cooperatives:** use **"Energy"** — closest match in the form's dropdown (no "Utility Cooperative" option).
- **For `billing_terms` on mixed-basis projects** (some phases lump sum, some T&M NTE): `fill-pof.js` auto-derives the dominant-by-dollar choice from `rows[].pay` totals. Don't ask; just compute.
- **For `invoice_setup` when `deltek_structure=Phase` AND row pay types are mixed:** recommend "Phase" so T&M-NTE phases bill separately. Confirm with user.
- **For `rows`:** one entry per phase. Survey - GIS Phase 01 (Boundary), 02 (Topo), 03 (Construction Stakeout), etc. Leave `task` blank unless the user splits the phase. **All math programmatic** (totals, hours-to-percent for Mosaic).
- **Per-row `team` array** (for Mosaic): `[{who: "Name", hours: N}, ...]`. The skill derives Mosaic percentages from these. If you don't supply `team`, Mosaic just gets the row's `eor` as a single 100% assignee.
- **Workbook ↔ proposal alignment:** when Accounting will load workbook subtotals into Deltek as the project budget, the workbook needs to match the sold proposal $ per phase. If pre-award time is being moved into the project, the workbook row sized for that work must absorb those hours (don't cut it below the absorbed amount).
- **Pre-send workbook cleanup:** strip "Phase 1 (Revised ...)" wording from the bid workbook's project-name cell — accounting may misread it as the project's Phase 1 line. Bump the workbook header date to match the proposal date.

Save `pof.json` after each substantive edit so an interruption doesn't lose state.

## Mode 2 — POF Fill

```bash
export PATH="/c/Users/rharbach/AppData/Roaming/npm:$PATH"

# Preflight: confirm form is loaded and key inputs exist
dev-browser --connect --timeout 15 run "$USERPROFILE/.claude/skills/pof/scripts/preflight.js"

# Stage pof.json into dev-browser temp (see references/staging-pattern.md)
# Build a stage script via PowerShell preprocessing, then run it.
# Do NOT use the await-import-fs pattern; that fails in QuickJS.
powershell -NoProfile -Command "
  \$pof = Get-Content '\\\\Stahly\\...\\pof.json' -Raw;
  \$wrapped = '{\"pof\":' + \$pof + '}';
  \$esc = \$wrapped -replace '\\\\','\\\\\\\\' -replace '\"','\\\"' -replace [char]13,'\\r' -replace [char]10,'\\n';
  Set-Content \$env:TEMP\\stage_pof.js \"const payload = `\"\$esc`\"; await writeFile('pof.json', payload); console.log('staged');\" -NoNewline
"
dev-browser --connect --timeout 10 run "$TEMP/stage_pof.js"

# Fill every mapped field across all 4 POF pages. Skips empty values. Does NOT click Submit.
dev-browser --connect --timeout 120 run "$USERPROFILE/.claude/skills/pof/scripts/fill-pof.js"

# Re-read every persisted value and confirm it matches pof.json (with format normalization)
dev-browser --connect --timeout 60 run "$USERPROFILE/.claude/skills/pof/scripts/verify-pof.js"
```

`verify-pof.js` returns `{ ok, mismatchCount, mismatches }`. The verifier **normalizes** form auto-formatting:
- Phone fields: digits-only comparison (`4065551234` matches `(406) 555-1234`)
- Money fields: strip `$` and commas
- Date columns: accept `M/D/YYYY` as equivalent to zero-padded `MM/DD/YYYY`

If `mismatchCount > 0` after normalization, those are real defects. Re-run `fill-pof.js` (idempotent) and re-verify. If a specific field keeps mismatching, inspect via `page.evaluate(({id}) => document.getElementById(id).value, {id: '<input_id>'})`.

When verify is clean:
1. **Tell the user what was filled** + flag manual items they still need to do (file uploads, map widget).
2. **Warn them that Submit triggers the Mosaic chained form.** Make sure they've done the file uploads first.
3. Point them at the live tab. **Stop.** Submit is the user's click.

## Mode 3 — Mosaic Fill

After the user submits the POF, Chrome navigates to `https://form.jotform.com/231225238538051` (Mosaic Planning Set Up Sheet) with POF data as URL query prefill. A "Start Filling" cover page appears first; `fill-mosaic.js` auto-clicks it.

Mosaic is a single-page form (after the cover) with the same 5-row phase table structure as the POF — plus one **Configurable List widget per row** for additional team scheduling. The outer "Who" / "% of Budget" pair captures one person; the widget captures the rest. The two must sum to **100% per phase** across all staff.

```bash
# Same staging step as Mode 2 (pof.json must already be staged in dev-browser temp)
dev-browser --connect --timeout 120 run "$USERPROFILE/.claude/skills/pof/scripts/fill-mosaic.js"
dev-browser --connect --timeout 60 run "$USERPROFILE/.claude/skills/pof/scripts/verify-mosaic.js"
```

`fill-mosaic.js` reads per-row `team: [{who, hours}, ...]` from `pof.json`, derives percentages from hours, writes the largest-share person to the outer Who/% fields, and adds the rest to the widget. `verify-mosaic.js` checks that each phase's outer % + widget % entries sum to 100% (within ±1 for rounding).

**Row selection when project has more than 5 phases:** set `pof.mosaic_rows_use` to a list of `pof.rows` indices (1-based) you want to display. E.g., when Phase 1 is the lowest-value for Accounting and you have 6 phases, use `"mosaic_rows_use": ["2","3","4","5","6"]`. The dropped phase still belongs in the POF's `notes_for_accounting` (see Rule 6 above).

**Configurable List widget mechanics** (see `references/dev-browser-quirks.md` for the broader context):
- Widget is a cross-origin iframe at `widgets.jotform.io/configurableList/index.html?qid=<qid>`
- Reachable via `page.frames()` + `frame.evaluate()` (CDP bypasses same-origin)
- 3 text inputs per row: Who / % of Budget / # of Manhours (in DOM order, no IDs)
- "+ Add Row" button extends; hidden "x" remove buttons clickable via `.click()` even with `offsetParent==null`
- Per Amy at Accounting (2026-06-03): the default empty row is **data, not a header** — same format as Add-Row rows
- After clearing all rows, widget may have 0 rows; that's OK for phases with no additional team, but `fill-mosaic.js` adds 1 row back via Add Row for consistency with widgets on no-team phases

**Row position vs phase number:** widget qids (28, 37, 46, 55, 66) correspond to **row positions 1–5**, NOT project phase numbers. When phases are reordered (e.g., dropping Phase 1, shifting Phases 2–6 into Rows 1–5), the widget at qid 37 holds the Row-2 team — which is the project's Phase 3 in the example. Verify by reading the row's Phase field, never assume.

When Mosaic verify is clean, hand off the Mosaic submit to the user.

## Pre-send checklist (run before any Submit)

Walk these out loud to the user before they click POF Submit or Mosaic Submit:

- [ ] **Visual walk of every page** — verify dates, fees, names, percentages
- [ ] **File uploads done** (POF only): contract bundle to `input_378`, bid workbook to `input_448`
- [ ] **Lat/long pasted** or map widget set (POF only — `input_430`/`input_431`)
- [ ] **Per-phase percentages sum to 100%** (Mosaic only) — `verify-mosaic.js` confirms
- [ ] **Workbook matches the proposal** — phase subtotals within $100 rounding of displayed proposal $; if Accounting will load Deltek from workbook, this matters
- [ ] **Notes_for_accounting overflow phase captured** if project has > 5 phases (POF only)
- [ ] **User is aware that POF Submit triggers Mosaic** (POF only)

## File uploads & the map widget (POF)

`input_378` (contract uploads) and `input_448` (bidding spreadsheet) are file inputs. The Google Map widget at qid `id_446` lives in an iframe. **The skill does not fill these.** Tell the user to handle them manually before submitting — they can also paste latitude/longitude into `input_430` / `input_431` if they already have the coordinates.

## Lessons carried over from `skills/timesheet`

1. **Always pass the actual Chrome tab ID** to `browser.getPage()`. Scripts use `tabs.find(...)` — never replace with a name alias.
2. **Discover via DOM, not screenshots.** Field state lives in `document.getElementById(...)`. Screenshots clip.
3. **Set value + dispatch input/change/blur** for text/textarea/tel/select. Click + change for radio. Click only when checked state needs to flip for checkbox.
4. **`scrollIntoView({block:'center'})` before clicking** radios/checkboxes/remove buttons. Off-screen clicks silently no-op for non-iframe elements (iframe widget remove buttons work even when hidden — those are the exception).
5. **Verify-after-fill is mandatory.** A `filled` status is necessary but not sufficient.
6. **CDP failure recovery:** kill Chrome, relaunch with debug profile, re-verify `127.0.0.1:9222/json/version`.

## Form quirks discovered during recon + real fills

- **POF is multi-page (4 pages)**, not single-page. The `.form-pagebreak-next` buttons are real, not editor residuals.
- **POF Submit redirects to Mosaic** at `form.jotform.com/231225238538051`. Plan accordingly.
- **Row Start/End date columns use a MM/DD/YYYY mask.** `fill-pof.js` uses the `date_masked` kind: sends zero-padded `MMDDYYYY` per-character via keyboard events. Setting `.value="6/3/2026"` gets re-tokenized by the mask into `63/20/26__`.
- **Phone fields auto-format** (`4065551234` → `(406) 555-1234`). `verify-pof.js` normalizes to digits-only for comparison.
- **`id_456` PM Email is shown on multi-page POFs** (which the live form is). It was thought "hidden until parent radio triggers" — actually it's just on a later page. Default to `rharbach@seaeng.com`.
- **`id_439` Client Type is hidden until `is_new_client = Yes`** (real conditional). Set parent radio first or this select isn't in the DOM.
- **`input_398` and `input_418` (Row 3 / Row 5 Department) are missing `Architecture`** as an option that Rows 1/2/4 have. Form defect — use a different row if Architecture is needed there.
- **Mosaic widget remove buttons are hidden in the DOM** (`offsetParent==null`) but `.click()` still fires the handler. Don't gate row removal on visibility.
- **Mosaic "Phase Row N - Additional Team Scheduling"** widget qids (28, 37, 46, 55, 66) map to row POSITIONS, not phase numbers — see Mode 3 caveat.

## Reference docs

- `references/pof-form-schema.md` — full field map for POF + Mosaic forms, IDs, types, allowed values
- `references/staging-pattern.md` — how to get pof.json from the network share into the dev-browser sandbox
- `references/dev-browser-quirks.md` — QuickJS sandbox, CDP semantics, cross-origin iframe access, single-arg `page.evaluate`, hidden-button clicks
