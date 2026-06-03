---
name: pof
description: Fill out Stahly Engineering's JotForm Project Order Form (POF) at https://form.jotform.com/232545214343146 from a structured pof.json. Survey - GIS specific. Use when the user says "new POF", "fill out the POF", "project order form", "start a POF for <client>", or otherwise asks to open/file/start the JotForm POF for a new Stahly survey project. Two modes — Gather (conversational intake to pof.json) and Fill (preflight → fill → verify → user clicks Submit).
---

# Project Order Form (POF) — Survey - GIS

Fills https://form.jotform.com/232545214343146 in a live Chrome tab via `dev-browser`. Modeled after `skills/timesheet`: Gather → preflight → fill → verify → hand off the Submit click to Ryan.

## Where pof.json lives

Per-project, inside the bid folder:

```
\\Stahly\marketing\Scope-Schedule-Budget\Survey - GIS\<YYYY>\<City>\<NNN-Project_Name>\pof.json
```

Cities seen in `2026/`: Billings, Bozeman, Cody, Great Falls, Helena. Projects numbered `001-...`, `002-...`, etc.

On first run for a project, ask Ryan for year + city + project (or infer from his working directory / recent conversation), then create `pof.json` if absent or load the existing one.

## Hardcoded defaults

`fill-pof.js` applies these unless `pof.json` provides a value:

| Field | Default |
|---|---|
| `form_preparer` | Ryan Harbach |
| `email_contact` (Ryan's, for header email field if used) | rharbach@seaeng.com |
| `office_location` | Helena, MT |
| `department` | Survey |

`project_manager` and `eor_sor` are **asked** every time — usually Ryan but not always. Phone, client info, estimate, etc. always come from conversation.

## pof.json shape

Flat object plus a `rows[]` array for the phase table (1–5 rows). All values are strings as the form expects them, or booleans for checkboxes. Empty / missing keys are skipped by the filler.

```json
{
  "date_month": "06", "date_day": "03", "date_year": "2026",
  "project_number_4digit": "3797",
  "project_number_5digit": "",
  "project_name": "Helena Example Topo",
  "project_description": "Topographic survey of 5 acres for site design.",
  "project_manager": "Ryan Harbach",
  "eor_sor": "Ryan Harbach",
  "form_preparer": "Ryan Harbach",
  "estimate": "$8,500",
  "given_to_client": "Yes",
  "rate_table": "Standard Billing Rates",
  "billing_terms": "Lump Sum",
  "time_to_be_moved_to_project": "Proposal",
  "client_name": "Acme Co",
  "client_address1": "123 Main St",
  "client_address2": "",
  "client_city_state_zip": "Helena, MT 59601",
  "contact_first": "Jane", "contact_last": "Doe",
  "phone": "4065551234",
  "cell": "",
  "email": "jane@acme.com",
  "is_new_client": "No",
  "client_type": "",
  "office_location": "Helena, MT",
  "department": "Survey",
  "funding_type": "Private",
  "grant_funded": "No",
  "move_proposal_to_project_folder": true,
  "deltek_structure": "Phase",
  "invoice_setup": "Project",
  "rows": [
    { "phase": "01", "task": "", "start": "6/3/2026", "end": "7/1/2026",
      "labor": "$8000", "expenses": "$500", "total": "$8500",
      "pay": "Lump Sum", "eor": "Ryan Harbach", "dept": "Survey" }
  ],
  "more_than_5": "No",
  "formal_agreement": "Yes",
  "latitude": "",
  "longitude": "",
  "notes_for_accounting": ""
}
```

Allowed values for selects/radios are in `references/pof-form-schema.md`. The most-used ones:
- `rate_table`: `Standard Billing Rates` | `Professional Discounted Rates`
- `billing_terms`, `rows[].pay`: `Lump Sum` | `Hourly`
- `time_to_be_moved_to_project`: `No` | `0500 Misc.` | `Proposal` | `Proposals & 0500` | `Client Term Project`
- `department`, `rows[].dept`: see schema (Survey is the surveyor default; Survey - Construction is the other common one)
- `funding_type`: `Private` | `Public`
- `formal_agreement`: `Yes` | `No` | `Forthcoming` | `Sent to Accounting via DocuSign`
- `is_new_client`, `grant_funded`, `more_than_5`: `Yes` | `No`
- `deltek_structure`: `Phase` | `Phase & Task`
- `invoice_setup`: `Project` | `Phase` | `Task` | `Phase & Task`

## Phase 0 — Prerequisites (run every session)

These match the timesheet skill's environment; this skill reuses the same debug profile and CDP setup. PowerShell preferred.

1. **dev-browser on PATH.** `dev-browser --version` should print a version. If missing: `npm i -g dev-browser`. On Windows, the global shim lives in `C:\Users\rharbach\AppData\Roaming\npm` — that path must be in `PATH` for `dev-browser` to resolve from the Bash tool. Quick fix in a Bash session: `export PATH="/c/Users/rharbach/AppData/Roaming/npm:$PATH"`.
2. **CDP on :9222.** `Invoke-WebRequest http://127.0.0.1:9222/json/version` must return JSON. If 404 or refused, kill Chrome and relaunch with the debug profile (Chrome 130+ silently rejects `--remote-debugging-port` against the default profile):
   ```powershell
   Get-Process chrome -ErrorAction SilentlyContinue | Stop-Process -Force
   Start-Process "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe" `
     -ArgumentList "--remote-debugging-port=9222","--remote-allow-origins=*",`
     "--user-data-dir=C:\Users\rharbach\.chrome-debug-profile",`
     "https://form.jotform.com/232545214343146"
   ```
   On the timesheet machine the profile sits at `C:\Users\rharbach.STAHLY\.chrome-debug-profile` — use whichever home dir matches.
3. **JotForm tab present.** `browser.listPages()` must contain a tab whose URL includes `form.jotform.com/232545214343146`. If Chrome launched but the URL arg didn't take (first-run dialog interferes), navigate the existing tab: `await page.goto("https://form.jotform.com/232545214343146", { waitUntil: "domcontentloaded" })`.

Bail if any check fails. Don't proceed to Fill with a half-broken environment.

## Mode 1 — Gather

Build `pof.json` conversationally. Read existing `pof.json` first if it's there.

- **Apply hardcoded defaults silently** (form_preparer, office_location, department, Ryan's email if relevant).
- **Always ask** for the project-specific blocks: project_name, description, PM, EOR/SOR, estimate, billing terms, client info, phases.
- **Enter what you can before asking** — if Ryan provides most info but one row's department is ambiguous, fill the rest, mark blocked entries clearly, then ask only the open question. (Timesheet rule 8.)
- **No mental math.** Any total = labor + expenses goes through `python3 -c`. (Timesheet rule 1.)
- **For "rows":** one entry per phase. Survey - GIS Phase 01 (Boundary), 02 (Topo), 03 (Construction Stakeout), etc. — leave `task` blank unless Ryan splits the phase into tasks.

Save `pof.json` after each substantive edit so an interruption doesn't lose state.

## Mode 2 — Fill

```bash
# Preflight: confirm form is loaded and key inputs exist
dev-browser --connect --timeout 15 run "%USERPROFILE%/.claude/skills/pof/scripts/preflight.js"

# Stage pof.json into dev-browser temp (script reads from there)
dev-browser --connect --timeout 10 <<'EOF'
const fs = await import('fs/promises');
const pof = JSON.parse(await fs.readFile("\\\\Stahly\\marketing\\Scope-Schedule-Budget\\Survey - GIS\\2026\\Helena\\001-Ford_FMT_Research\\pof.json", "utf8"));
await writeFile("pof.json", JSON.stringify({ pof }));
console.log("staged");
EOF

# Fill every mapped field. Skips empty values. Does NOT click Submit.
dev-browser --connect --timeout 120 run "%USERPROFILE%/.claude/skills/pof/scripts/fill-pof.js"

# Re-read every persisted value and confirm it matches pof.json
dev-browser --connect --timeout 60 run "%USERPROFILE%/.claude/skills/pof/scripts/verify-pof.js"
```

(On Bash, use `~/.claude/skills/pof/scripts/...` instead of `%USERPROFILE%/...`.)

`verify-pof.js` returns `{ ok, mismatchCount, mismatches }`. If `mismatchCount > 0`, re-run `fill-pof.js` (idempotent) and re-verify. If a specific field keeps mismatching, inspect by running an inline `page.evaluate(() => document.getElementById('<id>').value)`.

When verify is clean, tell Ryan **what was filled**, **point him at the live tab**, and **stop**. Do not click `#input_35` (Submit). Ryan uploads any contracts/spreadsheets and the Google Map widget manually, then submits.

## Lessons carried over from `skills/timesheet`

These are hard rules — not suggestions:

1. **Always pass the actual Chrome tab ID** to `browser.getPage()`. The scripts already use `tabs.find(...)` to get the live JotForm tab id; never replace with a name alias.
2. **Discover via DOM, not screenshots.** Field state lives in `document.getElementById(...)`. Screenshots clip.
3. **Set value + dispatch input/change/blur** for text/textarea/tel/select. Click + change for radio. Click only when checked state needs to flip for checkbox.
4. **`scrollIntoView({block:'center'})` before clicking radios/checkboxes.** Off-screen clicks silently no-op.
5. **Verify-after-fill is mandatory.** A `filled` status is necessary but not sufficient.
6. **Stop before the irreversible step.** Submit is the user's click, always.
7. **CDP failure recovery:** kill Chrome, relaunch with debug profile, re-verify `127.0.0.1:9222/json/version`.
8. **Enter what you can before asking** (Gather mode).
9. **All arithmetic programmatic** — `python3 -c "print(...)"`, never mental math.

## File uploads & the map widget

`input_378` (contract uploads) and `input_448` (bidding spreadsheet) are file inputs. The Google Map widget at qid `id_446` lives in an iframe. **The skill does not fill these.** Tell Ryan to handle them manually before submitting — he can also paste latitude/longitude into `input_430` / `input_431` if he already has them.

## Form quirks discovered during recon

- The form is single-page despite the multiple `.form-pagebreak*` selectors that appeared in early recon (those were back/next button residuals from JotForm's editor). All 93 form-lines are present in the live DOM simultaneously — no pagination needed during fill.
- `id_456` (PM Email) and `id_439` (Client Type) are hidden until parent radios trigger them. The filler will silently fail to find them if their parent isn't set first. Order matters: set `is_new_client` before `client_type`.
- `input_14` (TIME TO BE MOVED TO PROJECT) options include both `Proposal` and `Proposals & 0500` — distinct values. Match exactly.
- `input_398` and `input_418` (Row 3 / Row 5 Department) are missing `Architecture` as an option (rows 1/2/4 have it). Confirmed in recon — defect in the form, not the schema. If Ryan needs Architecture on rows 3 or 5, use a different row.
