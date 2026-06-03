# Deltek Vantagepoint Timesheet — Browser Automation Guide

This reference contains everything needed to operate the Deltek Vantagepoint timesheet page via Chrome MCP. Read this when entering time into the browser.

## Table of Contents
1. [Login and Session](#login-and-session)
2. [URL Pattern and Navigation](#url-pattern-and-navigation)
3. [Timesheet Search](#timesheet-search)
4. [Copy Previous Timesheet Workflow](#copy-previous-timesheet-workflow)
5. [Grid Layout](#grid-layout)
6. [Entering Hours](#entering-hours)
7. [Stable Element References](#stable-element-references)
8. [Adding and Managing Rows](#adding-and-managing-rows)
9. [Phase and Task Lookup](#phase-and-task-lookup)
10. [Saving](#saving)
11. [Timesheet Statuses and Views](#timesheet-statuses-and-views)
12. [Chrome MCP Gotchas](#chrome-mcp-gotchas)

---

## Login and Session

- The user must log in manually — never enter passwords on their behalf
- User ID: RYANH, Database: SeaEng
- MFA may be required (verification code)
- Sessions can expire — if you see the login page, ask the user to log back in
- After login, the app may land on "Getting Started" — navigate to the timesheet URL directly

## URL Pattern and Navigation

**Direct URL pattern:**
```
https://seaeng.deltekfirst.com/SeaEng/app/#!Timekeeper/view/0/0/00133%7C{YYYY-MM-DD}%7C00/presentation
```

- The date is always the **Saturday at the end of the timesheet week**
- `%7C` is URL-encoded pipe (`|`)
- `00133` is Ryan's employee ID
- Example: for week 4/12-4/18/2026, use date `2026-04-18`

## Timesheet Search

- Use the **"Find timesheets"** search box below the "Timesheets" title
- Search uses **M/D format without year** (e.g. `4/12`). Including the year returns no results.
- The search matches any date in the timesheet range — use the **Sunday start date**
- Weeks run **Sunday to Saturday** (e.g. 4/12 - 4/18)
- After typing, a dropdown shows matching timesheets across all years — click the desired one
- After selecting, a "1 of N" pager appears to the right

## Copy Previous Timesheet Workflow

Use this when a timesheet is empty (Status: Missing):

1. Click **"Other Actions"** — use `find` to locate by name (right side of screen, to the right of Submit)
2. Click **"Copy Previous Timesheet"** — use `find` to locate the link
3. A "Copy a Timesheet" dialog appears with a dropdown field
4. **Open the dropdown via JavaScript** (MCP ref clicks don't work on this control):
   ```js
   const caret = document.querySelector('.tap-target');
   const rect = caret.getBoundingClientRect();
   const cx = rect.x + rect.width / 2;
   const cy = rect.y + rect.height / 2;
   caret.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, clientX: cx, clientY: cy }));
   caret.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, clientX: cx, clientY: cy }));
   caret.dispatchEvent(new MouseEvent('click', { bubbles: true, clientX: cx, clientY: cy }));
   ```
   Note: Simple `.click()` does NOT work. Must use full mousedown/mouseup/click sequence.
5. Use `find` to locate the first date option (most recent prior timesheet) and click it
6. Click the **"Copy"** button in the dialog
7. **Save immediately** — if you navigate away or click "No" on save dialog, the copy is lost

After copy:
- Status changes from "Missing" to "In Progress"
- "Save" button appears next to Submit
- Orange warning banner may appear about inactive/dormant lines not copied

**GOTCHA:** The "?" button in the dialog opens a hard-to-dismiss help overlay. Avoid clicking near it. If opened, use `read_page` to find the Close button (look for `ref_621`).

## Grid Layout

The grid has **two separate horizontal scroll panes**:

**Left pane** (wider): Project, Project Name, Client Name, Phase, Phase Name, Task, Task Name, Labor Code

**Right pane** (narrow at default zoom): Day columns (Sun-Sat), Regular, Overtime, Overtime-2, Total

**Full screen + Chrome zoom at 50%** makes all 7 day columns visible at once — strongly recommended.

Day columns: Sun, Mon, Tue, Wed, Thu, Fri, Sat (with dates like 4/12, 4/13, etc.)

Each row has an **"Options"** button (three dots / kebab menu — selector: `button.rowTools_menuBtn`, fixed at x≈1863 in the right pane) with menu items: **Insert**, **Copy**, **Delete** (current labels — older "Insert new row" / "Copy row" / "Delete row" wording is GONE). Click flow: select the row first, then click its Options button at the same y. The menu items render as `div.popupLabel` to the left of the button (around x≈1823). Use `Copy` to duplicate a row at the same proj+phase+task — Deltek allows duplicates here despite the "rows are unique" guidance elsewhere; save immediately after the copy to commit it.

## Entering Hours

### Opening a cell
Click on a day cell textbox (get refs via `read_page` after selecting a row). The cell editor popup opens with:
- **REGULAR** input (ref_555 — stable across all cells; `id="regHrs"`)
- **OVERTIME** input (`id="ovtHrs"`)
- **COMMENT** text area (ref_574 — stable across all cells) — red star means required
- Comment has a dropdown arrow and pencil icon

**Comment field internals (CRITICAL for dev-browser scripts):**
- Authoritative storage: `<div id="commentEntry" contenteditable="true">` — write `textContent` here, this is what Save reads
- Display/filter input: `<input name="commentDdwn">` — visible field; setting `.value` does NOT save (it only filters the past-comments dropdown). It mirrors the contenteditable's value automatically when populated by Deltek itself.
- If you set only the input, Save proceeds silently with NO comment, even though required-star is shown

### Entering a value
1. Use `find("REGULAR input")` to get the ref, then click it
2. Type the hours as a decimal (e.g. `8`, `1.5`, `0.25`)
3. Use `find("Comment textarea")` to get the ref, then click it
4. Type the comment text

### Editing an existing value
- To **replace**: use `find("REGULAR input")`, then **triple-click** the returned ref to select all, then type the new value. NEVER use Ctrl+A — it types the letter "a" instead of selecting.
- To **append to comment**: use `find("Comment textarea")`, click the ref, press Ctrl+End to move to end, type additional text

### Navigation
- Escape does NOT close the popup
- Clicking a different row closes the popup
- Click the next day cell ref to move to a different day on the same row

### Hours format
Decimal: 8.0, 0.25, 1.5 (not hours:minutes)

## Stable Element References

These refs do NOT change between cells or sessions:
- **REGULAR input**: ref_555
- **Comment textarea**: ref_574

Day column header refs (stable within session, use for `scroll_to`):
- ref_579 (Sun), ref_582 (Mon), ref_585 (Tue), ref_588 (Wed), ref_591 (Thu), ref_594 (Fri), ref_597 (Sat)

Day cell textbox refs **change when a different row is selected**:
- 7 sequential textboxes appear in table ref_326
- Pattern: 1st = Sun, 2nd = Mon, 3rd = Tue, 4th = Wed, 5th = Thu, 6th = Fri, 7th = Sat
- Do ONE `read_page` after selecting a row to get all 7 refs

## Adding and Managing Rows

### Adding a new project (Add Line workflow — full sequence)

The button text is exactly **`+Add Line`** (no space). It's a `<button class="btn primary total1">` at the bottom-left of the grid.

Full sequence:

1. **Click `+Add Line`**. A new empty row appears at the bottom of grid 0; the leftmost Project search input gets focus.
2. **Click the Project search field** (selector: `input.input-element.search-input.searchCol` — the one without the `locked` class. Find it via DOM and use `page.mouse.click(x,y)`.).
3. **Type 3-4 characters** of the project number or name (e.g. `3963`, or `Cushing`). Use `page.keyboard.type()` with a small delay (50-80ms per char) so Deltek can react. **Don't press Enter.**
4. **Wait ~2.5 seconds.** Deltek auto-opens a **Project/Phase/Task Lookup dialog** (`role="dialog"`). This is NOT a typeahead dropdown — it's a 3-pane modal with Project | Phase | Task grids side-by-side.
5. **Click the matching project row** in the Project pane (left). Use mouse coords from `tr.getBoundingClientRect()` since the dialog has its own grid.
6. **Click the matching phase row** in the Phase pane (middle). Phases auto-populate after the project click. If only one phase, you may still need to click it.
7. (Optional) **Click a task row** in the Task pane (right) if applicable. Often empty.
8. **Click the `Select` button** at the bottom-right of the dialog. The dialog closes; the row is now populated on the timesheet.
9. **Save** the timesheet to commit the new row before doing anything else.

**Hazard — accidental help dialog:** when typing in a new row's project field, an unrelated help dialog with class `ui-dialog-titlebar-close` may open (the cause is unclear; possibly a stray "?" focus or focus race). Symptom: `document.activeElement` becomes the close button of an unexpected dialog. Always check for any open `.ui-dialog` / `[role="dialog"]` after typing and dismiss with Escape or `.ui-dialog-titlebar-close.click()` before continuing. Re-do the type step after dismissing.

**Gotcha — task selection in the Lookup dialog needs mousedown/mouseup, not click:** The task grid (right pane) does NOT register a selection from `row.click()` or even `page.mouse.click(x, y)`. Symptom: the Select button stays `btn primary disabled` no matter how many times the script "clicks" the task row. Required pattern — click a TD cell inside the task row with a real mouse sequence:
```js
await page.mouse.move(x, y);     // x,y from td.getBoundingClientRect() of the task row's first <td>
await page.mouse.down();
await page.waitForTimeout(50);
await page.mouse.up();
```
Project and phase selection accept regular `page.mouse.click()` fine — only task selection is fussy. This is the same family of bug as the Copy-Previous caret dropdown, where Kendo controls ignore synthetic click events.

**Gotcha — "Find Project" filter persists across +Add Line attempts:** If a prior add-line opened the Lookup dialog and left a stale filter string (e.g. "Augusta"), the next +Add Line will open the same dialog showing the old search, and typing in the new row's project search input does NOT update the dialog's filter. Symptom: `no_matching_project_row` even though the project exists. Fix: after the dialog opens, look for an `input[placeholder="Find Project"]` inside the dialog and, if its `.value` doesn't match the desired search, triple-click + Delete it and re-type the search inside the dialog itself.

**Gotcha — project number search format:** The dialog's "Find Project" filter doesn't always match on exact project numbers like `0001-05325`. Searching by a name keyword (`Augusta`) or by the suffix alone (`05325`) is more reliable. When in doubt, search by name.

**Gotcha — new row only appears AFTER Save, not after Select:** Clicking Select closes the dialog but the new row isn't immediately visible in grid 0. It only renders after the surrounding Save persists. Wait ~3 seconds AFTER Save before re-checking the grid for the row, otherwise verification will report "save_unverified" on a row that did actually save.

**Use `add-line.js`** in `scripts/` for an automated version of this sequence — it handles dialog detection, phase preference matching, and Save.

### Rules
- **Never add a project that already exists** — use Options > Copy row instead
- Each row is unique at the **Project + Phase + Task** level
- To log time to a different phase/task on the same project, copy an existing row and change the phase/task
- Only use "+ Add Line" for projects not on the timesheet at all

## Phase and Task Lookup

- The **magnifying glass in the Phase field** opens a Phase/Task Lookup dialog that lets you select both phase AND task
- The button after the Task fields is the **Labor Code lookup** — avoid clicking it unless changing labor code
- **Faster alternative**: Type phase number directly into Phase field (e.g. `0006`) and task number into Task field (e.g. `6.07`). Preferred when values are known.
- **Phase/Task numbering**: `3.01` = Phase 0003, Task 01. Number before decimal = phase, after = task.
- **Never change the Labor Code** unless specifically requested

## Saving

- **Save after EVERY entry** — find "Save button" and click it after each day cell is filled
- Save is **disallowed if any entry is missing a comment**
- After saving, the "Save" button disappears; reappears when there are unsaved changes
- "Timesheet successfully saved" green banner confirms success
- **GOTCHA:** Clicking "No" on "Save Timesheet?" dialog discards ALL changes including copies

## Timesheet Statuses and Views

### Statuses
- **Missing** — empty, no rows
- **In Progress** — has rows, may or may not have hours
- **Posted** — submitted and approved, locked/read-only (lock icon next to name)

### Posted Timesheet
- No Save or Submit buttons
- Approval workflow section shows submitter (orange arrow) and approver (green check)
- Cells are read-only, Add Line is grayed out

### Hours vs Units Toggle
- Toggle buttons at upper right: **Hours** (default) | **Units**
- Units view has different columns (Unit Table, Unit, Unit Name) and separate rows from Hours
- Use Hours view for time entry

### Other Actions Menu
- Copy Previous Timesheet
- Copy from Plan
- Request New Absence
- Previous Absence Requests
- Floor Check
- Timesheet Settings
- Print

### Gear Icon (Grid Settings)
- Located at top-right of grid column headers
- Opens menu: Left Grid Settings, Right Grid Settings
- Controls which columns are visible in each scroll pane

## Chrome MCP Gotchas

1. **Always use `find` to locate elements by name/label** — coordinates are unreliable
2. **Deltek custom dropdowns** don't respond to MCP ref clicks or simple `.click()` — use full mousedown/mouseup/click event dispatch
3. **Save immediately after Copy Previous** — navigating away loses the copy
4. **Browser extension can disconnect** — if JS execution fails with connection error, ask user to reconnect
5. **Two separate scroll panes** — scrolling the left shows Phase/Task columns, scrolling the right shows day columns
6. **Right scroll pane JS**: `document.querySelectorAll('.gridBody.absolute')[1].scrollLeft = 0`
7. The help "?" icon is very close to dialog close "X" — use element names, not coordinates, near dialog headers
8. **Browser zoom**: Use `Ctrl+-` (repeat) for native Chrome zoom, NOT `document.body.style.zoom` CSS. The `zoom` action on the computer tool only crops a screenshot for inspection — it does NOT change the browser zoom. Set Chrome to 50% zoom so all 7 day columns are visible at once. Use `Ctrl+0` to reset zoom.
9. **Never use `Ctrl+A` in Deltek input fields** — it types the letter "a" instead of selecting all text. Always use **triple-click** on the REGULAR ref to select existing values before replacing them.
10. **Always use `find` refs for REGULAR and Comment fields** — never click by coordinates. Use `find("REGULAR input")` then click/triple-click the returned ref. Same for `find("Comment textarea")`.
11. **Minimize verification steps** — don't zoom in repeatedly to verify values. One `find("day cell textbox in selected row")` check after save is sufficient to confirm the value took.
