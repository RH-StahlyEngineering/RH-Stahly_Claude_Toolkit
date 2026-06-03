---
name: timesheet
description: Manage Deltek Vantagepoint timesheets — record time from natural language and enter it into the browser. Use this skill whenever the user mentions timesheets, logging hours, recording time, entering time, filling out a timesheet, tracking hours for the week, or anything related to time entry for work projects. Also use when the user describes what they worked on and wants it captured for their timesheet.
---

# Timesheet Skill

This skill has two modes that work together:

1. **Record** — Parse natural language descriptions of work into structured time entries, saved to a weekly file
2. **Enter** — Read the weekly file and enter the data into Deltek Vantagepoint via Chrome MCP browser automation

These modes are modular. Recording can happen without entering, and entering reads from the recorded file. Each week gets its own file.

---

## Key Paths

All paths are hardcoded so this skill works from any conversation:

- **Base directory**: `C:\Users\rharbach.STAHLY\OneDrive - Stahly Engineering\Claude_Code_Timesheets_Deltek`
- **Project CSV** (source of truth for known projects): `{base}/timesheet_projects.csv`
- **Weekly time files**: `{base}/timesheets/YYYY-MM-DD.json` where the date is the **Saturday ending date** of the week
- **Operational reference** (Deltek browser automation details): read `references/deltek-guide.md` in this skill's directory when entering time

Create the `timesheets/` subdirectory if it doesn't exist.

---

## Core Rules

These apply to both modes:

1. **All arithmetic must be done programmatically** — use `python3 -c` or a script for any calculation (hours splitting, totals, subtraction). Never do mental math.
2. **Ryan is salaried** — all hours go in REGULAR, never OVERTIME.
3. **Ryan is a surveyor** — if there's only one survey-related phase/task for a project, use it without asking.
4. **Every entry requires a comment** — no exceptions.
5. **Never assume phase or task** unless previously established or there's only one survey option.
6. **Use as few keywords as possible** in all searches and lookups.
7. **Daily total hours are locked once established** — when Ryan provides start/stop times for a day (e.g., "7:30 to 6:00"), that defines the total hours for that day. That total NEVER changes unless Ryan explicitly requests it (e.g., "add an hour", "I actually worked until 7"). When Ryan later mentions meetings or other tasks within that day (e.g., "I had a 1 hour meeting"), **subtract** those hours from the main task for that day — do NOT add them on top. The start/stop times are the source of truth for total daily hours.
8. **Enter what you can before asking** — if some entries map cleanly to existing rows and others are blocked on a question (unknown project number, ambiguous phase, etc.), enter the unblocked ones first via `enter-timesheet.js`, then ask Ryan about the blocked ones. Never pause the whole timesheet to wait on one question. Mark the blocked entries' `status` as `pending` and the entered ones as `entered`, so the next pass only touches what's left.

---

## Mode 1: Record Time

**When to use**: The user describes work they did in natural language. They might say things like "I worked 8 hours on 8th Ave Monday doing Virtual Surveyor processing" or "subtract 1.5 hours from Thursday for an IT meeting."

### Required files to read before starting:
1. **Read `{base}/timesheet_projects.csv`** — this is the project lookup table. You need it to match user descriptions to project numbers.
2. **Read the weekly file** `{base}/timesheets/YYYY-MM-DD.json` if it exists — to see what's already been recorded this week.

### Step 1: Determine the week

Get the current date via `date +%Y-%m-%d`. Ask the user which week if ambiguous — users often fill in the previous week, not the current one. Calculate the Saturday ending date for that week (weeks run Sunday through Saturday).

### Step 2: Load or create the weekly file

Check if `timesheets/YYYY-MM-DD.json` exists. If it does, load it. If not, create a new one with this structure:

```json
{
  "week_ending": "2026-04-18",
  "week_start": "2026-04-12",
  "entries": [],
  "recorded_at": "2026-04-19T10:30:00"
}
```

### Step 3: Parse the user's input

Turn natural language into structured entries. For each piece of work described:

1. **Identify the project** — look it up in `timesheet_projects.csv` by name or keyword match. If not found:
   - Ask the user: "I can't find that project in the CSV. Do you know the project number, or should I look it up when entering the timesheet?"
   - If the user provides a number, use it and add to CSV for future reference
   - If unknown, record it with `"project_number": "LOOKUP_NEEDED"` and `"project_search": "keyword"` so the Enter mode knows to search for it

2. **Calculate hours programmatically** — if the user says "subtract 1.5 hours from Thursday's 8th Ave and add to IT", run `python3 -c "print(14 - 1.5)"` to get the new value. When the user says "subtract," that means pull hours from one existing entry and create/add to another.

3. **Resolve phase and task** — use known mappings first (see Common Mappings below). If unknown, record `"phase": "LOOKUP_NEEDED"` — it will be resolved during entry.

4. **Write the comment** — frame for managers, not for diary purposes.

   **Audience:** office manager, department manager, project manager. The comment exists to inform them what work Ryan did to contribute to the project. Nothing else.

   **Include:** the specific work or deliverable (e.g. "Topographic field survey on 8th Ave NW", "Survey drafting and data processing", "Fergus Electric proposal preparation"), and any external coordination that's project-relevant ("coordination with Melanie and HDR", "meeting with Matt Pool").

   **Exclude:**
   - Time-of-day or scheduling details ("9-6:30 minus 1 hr break", "evening session 8:30 PM - 12:15 AM"). The hours field captures duration; the time of day is irrelevant to a manager.
   - Personal/process narration ("I worked on", "spent time"). State the work directly.
   - Conversational asides or filler.

   **Voice:** noun-phrase or past-tense, project-first. Examples:
   - ✓ "Field preparation for 8th Ave NW topographic survey"
   - ✓ "Delivered 8th Ave NW survey to client"
   - ✗ "Survey drafting (9-6:30 minus 1 hr break, plus evening 8:30 PM - 12:15 AM)" — schedule details
   - ✗ "Did some drafting" — vague, not project-anchored

### Step 4: Write entries to the weekly file

Each entry in the `entries` array looks like:

```json
{
  "project_number": "3733-00226",
  "project_name": "Great Falls: 8th Ave NW - 11th-14th St",
  "task_name": "Survey Proposals",
  "phase": "0001",
  "task": "",
  "day": "Thu",
  "hours": 12.5,
  "comment": "Virtual Surveyor processing",
  "status": "pending"
}
```

Valid days: `Sun`, `Mon`, `Tue`, `Wed`, `Thu`, `Fri`, `Sat`

If an entry already exists for the same project+phase+task+day, **update it** (replace hours and append to comment) rather than creating a duplicate.

If the user says to modify an existing entry (reduce hours, change comment), update the existing entry in-place.

**Evening / "after work" additions:** When Ryan reports late additions like *"on Monday I worked 1.5 hrs on Douglas after work"* or *"this evening I spent another 2 hrs on 8th Ave"*, those hours **roll into that day's existing entry for the same project**, not a separate row. A timesheet cell holds one value per project+phase+task+day, so consolidate hours and concatenate comments. Daily totals will increase to reflect the additional time (this is one of the few cases where a previously-locked daily total is meant to grow — Ryan is explicitly extending the day).

### Step 5: Confirm with the user

After parsing, show a summary table of what was recorded:

```
Day  | Project              | Hours | Comment
-----|----------------------|-------|--------
Mon  | General Overhead/IT  | 8.0   | Transported Puget machines...
Tue  | General Overhead/IT  | 7.0   | Puget machine setup...
```

### Common Project/Task Mappings

These are known shortcuts — use them without asking:

| Shorthand | Project | Phase | Task | Default Comment |
|-----------|---------|-------|------|-----------------|
| IT | 0000-00001 General Overhead | 0006 | 6.04 | (describe work) |
| PTO / Personal Time / medical or personal appointment | 0000-00200 Personal Time | — | — | PTO |
| Holiday | 0000-00300 Holiday | — | — | (name of holiday) |
| Staff Meeting / scheduling meeting | 0000-00001 General Overhead | 0006 | 6.01 | (describe meeting) |
| Vehicle maintenance (oil change, etc.) / UAV equipment troubleshooting / total station setup / similar equipment work | 0000-00001 General Overhead | 0006 | 6.06 | (describe equipment task) |
| Category Development / R&D / innovation discussion / remote sensing update meeting | 0000-00005 R&D/Innovation | 0006 | 6.02 | (describe R&D topic) |
| DroneMapper AI development / Imperfect Data Handling work | 0000-00029 Overhead: DroneMapper AI | 0006 | — | (describe dev work) |
| Leadership / weekly survey leadership meeting | 0000-00010 Leadership/Management | 0006 | — | (describe leadership work) |
| Fergus Electric proposal / Great Falls Marketing & Proposals survey work | 0000-00826 Sales Admin, Proposals & Term Client OH | 0006 | 6.07 | (describe proposal) |

### Phase/Task Numbering

`3.01` means Phase 3 (`0003`), Task 01. The number before the decimal is the phase, after is the task. So if the user says "put it on 3.01" that tells you both the phase and task.

---

## Mode 2: Enter Time into Deltek

**When to use**: The user says something like "enter my timesheet," "fill out the timesheet," or "push my hours to Deltek."

**Two methods available** (prefer dev-browser for speed):

### Method A: dev-browser (PREFERRED — ~10x faster)

**Prerequisites**: `dev-browser` installed (`npm i -g dev-browser`), Chrome running with `--remote-debugging-port=9222` AND a separate `--user-data-dir`, user logged into Deltek.

**CRITICAL — Chrome must be launched with a separate profile.** Chrome 130+ silently rejects `--remote-debugging-port` against the default user profile (security restriction). The CDP TCP socket may bind but `/json/version` returns 404 and `dev-browser --connect` hangs on the WS handshake. The `chrome://inspect` "Discover" toggle is for finding remote devices, not for exposing CDP locally — it does NOT fix this. Workflow when CDP isn't responding:
1. Kill all Chrome processes: `Get-Process chrome | Stop-Process -Force`
2. Relaunch with a dedicated debug profile (preserves user's main Chrome): `Start-Process "C:\Program Files\Google\Chrome\Application\chrome.exe" -ArgumentList "--remote-debugging-port=9222","--remote-allow-origins=*","--user-data-dir=C:\Users\rharbach.STAHLY\.chrome-debug-profile","https://seaeng.deltekfirst.com/SeaEng/app/"`
3. Verify CDP: `Invoke-WebRequest http://127.0.0.1:9222/json/version` must return JSON, not 404.
4. The user re-logs into Deltek in the new window (the debug profile is separate so cookies don't carry over).

**Reference**: Read `references/dev-browser-guide.md` for full API details.

**CRITICAL — tab connection rules:**
- **Always pass the actual Chrome tab ID** (e.g. `"6AB701491EB391C5F58A1E51358FF48A"`) to `browser.getPage()`. Get it once via `browser.listPages()` and reuse it.
- **NEVER use a name-only string like `"deltek"`** as the only argument — that creates a NEW BLANK TAB instead of reusing the existing one. This wastes time and confuses the user.
- If you must use a named alias, pass BOTH ID and name: `browser.getPage(tabId, "deltek")`.

**CRITICAL — discover what's on the timesheet via DOM, not screenshots:**
Before asking the user about phase/task or whether a project is on the timesheet, **extract every row from `.gridBody.absolute` directly via `page.evaluate()` and search the resulting array.** Screenshots can clip rows; cell-by-cell DOM extraction can't. Filter the row list by project number, project name keyword, phase, or task name. Only ask the user if the project genuinely isn't on the timesheet, or if multiple matching phases exist and the comment doesn't disambiguate.

```javascript
// Pattern: dump every row, then filter by substring
const allRows = await page.evaluate(() => {
  const out = [];
  document.querySelectorAll('.gridBody.absolute').forEach((g, gIdx) => {
    g.querySelectorAll('tr').forEach((r, rIdx) => {
      const cells = Array.from(r.querySelectorAll('td')).map(td => td.textContent.trim());
      if (cells.some(c => c)) out.push({ grid: gIdx, row: rIdx, cells });
    });
  });
  return out;
});
// Then: allRows.filter(r => r.cells.some(c => c.includes("3733")))
```

#### Step 1: Prepare entries

Read the weekly JSON file. Add a `task_name` field to each entry for precise row matching (e.g. "Information Technology (IT)" not just "General Overhead").

#### Step 2: Navigate to the timesheet

```bash
dev-browser --connect --timeout 15 <<'EOF'
const tabs = await browser.listPages();
const deltekTab = tabs.find(t => t.url && t.url.includes('deltekfirst.com'));
const page = await browser.getPage(deltekTab.id);
await page.goto("https://seaeng.deltekfirst.com/SeaEng/app/#!Timekeeper/view/0/0/00133%7C{YYYY-MM-DD}%7C00/presentation", { waitUntil: "domcontentloaded" });
await page.waitForTimeout(2000);
console.log(JSON.stringify({ title: await page.title() }));
EOF
```

If the timesheet is empty (Status: Missing), use Chrome MCP to do the Copy Previous Timesheet workflow (the caret dropdown requires the JavaScript workaround — see `references/deltek-guide.md`). Then return to dev-browser for entry.

#### Step 2.5: Pre-flight check — verify all rows exist (REQUIRED)

Before writing entries to Deltek, confirm every `(project_number, task_name)` combo in `entries.json` already exists as a visible row on the live timesheet. The entry script does NOT add rows — it only fills cells in existing rows. Missing rows have to be added FIRST via `+Add Line`.

```bash
dev-browser --connect --timeout 30 run scripts/preflight.js
```

The script returns `{ allPresent, missing: [...] }`. If `missing` is non-empty:

1. For each missing row, ask the user (if needed) which phase/task to use, OR infer from context (e.g. user said "field work" → look for a Topo/Site/Field Survey phase).
2. Use `scripts/add-line.js` to add each missing row in one batch:

```bash
dev-browser --connect --timeout 10 <<'EOF'
await writeFile("add-line.json", JSON.stringify({
  rows: [
    { project_search: "3963", phase_text: "Engineering Survey" },
    { project_search: "3797", phase_text: "Topo Survey" }
  ]
}));
console.log("written");
EOF

dev-browser --connect --timeout 120 run scripts/add-line.js
```

Re-run preflight to confirm `allPresent: true` before proceeding to Step 3.

#### Step 3: Write entries file and run the script

```bash
# Write entries to dev-browser temp
dev-browser --connect --timeout 10 <<'EOF'
await writeFile("entries.json", JSON.stringify({
  entries: [
    { project_name: "Leadership/Management", task_name: "Leadership/Management", day: "Mon", hours: 1.0, comment: "Weekly meeting", status: "pending" }
  ]
}));
console.log("written");
EOF

# Run the entry script
dev-browser --connect --timeout 60 run scripts/enter-timesheet.js
```

The script returns JSON with success/failure per entry. Update the weekly file status based on results.

#### Step 4: Handle errors

If the script reports errors (row not found, popup not open), fall back to Chrome MCP for those specific entries, or write a targeted inline script to handle the edge case.

#### Step 5: VERIFY EVERY CELL — required final sweep

After the entry script reports success, **do not stop**. The entry script's per-step "verify before save" checks pass-through state at the moment of save, but Deltek can silently drop comments after save in edge cases (observed: HR Recruitment row dropped a comment despite the verify passing). The only trustworthy verification is to **re-open every cell and read its persisted hours + comment**.

For each entered entry, re-open the cell and check `regHrs.value` matches expected hours and `commentEntry.textContent` matches expected comment. Use the dedicated verify script:

```bash
# Reuses the same entries.json that the entry script consumed
dev-browser --connect --timeout 240 run scripts/verify-timesheet.js
```

The script returns `{ okCount, problemCount, problems, all }`. If `problemCount > 0`, re-enter the failing cells and run the sweep again until `problemCount === 0`. Note: `regHrs.value` is formatted (e.g. `"0.50"` not `"0.5"`) — the script handles this with `Number(h).toFixed(2)`.

This sweep is REQUIRED for any timesheet entry session. A reported "entered" status from the entry script is necessary but not sufficient — silent comment drops have been observed in the wild (e.g. HR Recruitment row dropped a comment despite the pre-save verify passing).

#### Step 5: Critical lessons (learned the hard way — don't repeat)

These are the failure modes that hit on a real run. The script in `scripts/enter-timesheet.js` already accounts for them; if you write inline, be sure you do too:

1. **Pop-up persists between entries.** After you enter hours and click `Save`, the cell editor pop-up does NOT auto-close. The next row click silently fails because the popup is still open. **Before each new row click, check `document.getElementById('regHrs')?.offsetParent` and if visible, dismiss the popup by clicking a non-cell area** (e.g. `.gridHeader`, `.timekeeper-header`, or `.breadcrumbs`). Then `waitForTimeout(800)`.

2. **Rows scroll out of view.** The grid only renders visible rows in the viewport, but `querySelectorAll('tr')` still returns hidden rows whose textContent matches. However, a `.click()` on an off-screen row may not register the row as "selected" (the day inputs won't appear). **Always `scrollIntoView({ block: 'center' })` BEFORE the click**, then `waitForTimeout(500)`, then re-find and click. Without this, you'll get `row_not_found` even when the row clearly exists in the DOM.

3. **Consolidate before entering.** A timesheet cell holds ONE value and ONE comment — not multiple entries. If the weekly JSON has two `pending` entries for the same project+task+day (e.g. two IT meetings on Monday), or one `entered` + one `pending` for the same cell (e.g. existing 0.5 from prior session + new 1.5 to add), **sum the hours and concatenate the comments BEFORE running the entry script**. Otherwise the second entry overwrites the first.

4. **Match rows by `project_number` AND `task_name` (and a row marker if needed).** Some task names appear multiple times across phases (e.g. "Survey Proposals" exists at 1.07, 3.07, and 6.07). Pass an extra `row_marker` field like `"6.07"` to disambiguate. The matcher in the script accepts this.

5. **Daily totals are the source of truth for verification.** After all entries, read grid 5 (totals) and confirm Mon/Tue/Wed/Thu/Fri/Sat totals against the JSON's expected per-day sums. The week total appears once in the totals cells.

6. **Always use the actual tab ID, not a name alias.** See the Critical tab connection rules above. This is the #1 silent failure mode.

7. **Skip hidden rows when matching.** Deltek's grid 1 (the "pinned/selected" pane) often holds CLONE rows with the same project text but `offsetParent === null` (hidden because the underlying data lives in grid 0). A naive search of `t.includes(args.proj) && t.includes(args.task)` will match the hidden clone, return early, and leave the real grid 0 row un-clicked. Symptom: hours/comment read empty during verify, even though `dayCells` extracted directly from grid 3 show the right values. Fix: always `if (r.offsetParent === null) continue;` when iterating rows for click/scroll, and prefer `grids[0]` over later grids.

8. **Row pinning eats subsequent matches for the SAME row — reload to reset.** When the entry script enters multiple cells on the same row (e.g. R&D 6.02 across Tue/Wed/Thu/Fri), Deltek progressively moves that row from grid 0 into grid 1 (pinned/selected) where it becomes hidden. After ~2 successful entries on a row, the 3rd matching attempt returns `row_not_found` because grid 0's row at that index is now an empty placeholder and grid 1's copy is `offsetParent === null`. Symptom on a clean run: `enter-timesheet.js` reports "entered" for the first few cells of a heavy row but later cells fail with `row_not_found` or `day_cell_not_found`. **Fix:** when this happens, `await page.reload()` + `waitForTimeout(6000)` to reset the pinning state, then re-run `enter-timesheet.js` with just the failed entries. A reload-per-heavy-row is cheap; trying to un-pin via clicking other rows is unreliable.

9. **Verify-script false positives on hidden pinned rows.** `verify-timesheet.js` has a known issue: when the target row is hidden in grid 1 (pinning), `rowY` lookup fails and the script falls back to reading whatever 7 day-inputs are currently rendered — which belong to the LAST selected row (often the previous IT entry). Symptom: verify reports a row as having the previous entry's hours/comment, but the actual cell value (read directly from `grid3` TD textContent) is correct. **Fix:** when verify reports problems for a row that was heavily used during entry, reload the page first and re-run verify. If problems persist after reload, they're real.

10. **Viewport-edge cell inputs need JS-dispatched mouse events.** When the Chrome window is shorter than ~950px (e.g. a 50%-zoom timesheet on a smaller monitor), the day cell input row sits at y≈912 — exactly at or below the viewport bottom edge. `page.mouse.click(x, 912)` silently fails because Chrome treats the click as off-screen (`elementsFromPoint(x, 912)` returns `[]`). **Fix:** dispatch the click directly on the DOM element instead:
    ```js
    await page.evaluate(() => {
      const inputs = Array.from(document.querySelectorAll('input.input-element.number_input'))
        .filter(i => i.offsetParent !== null);
      inputs.sort((a,b) => a.getBoundingClientRect().x - b.getBoundingClientRect().x);
      const wed = inputs[3]; // Sun=0..Sat=6
      const r = wed.getBoundingClientRect();
      const cx = r.x + r.width/2, cy = r.y + r.height/2;
      wed.dispatchEvent(new MouseEvent('mousedown', {bubbles: true, clientX: cx, clientY: cy}));
      wed.dispatchEvent(new MouseEvent('mouseup',   {bubbles: true, clientX: cx, clientY: cy}));
      wed.dispatchEvent(new MouseEvent('click',     {bubbles: true, clientX: cx, clientY: cy}));
    });
    ```
    This works regardless of viewport size. Better long-term: have the user widen the Chrome window OR use Ctrl+- to zoom out one notch before automating. If you see "popup did not open" with input coordinates near the viewport bottom, this is the cause.

11. **Survey proposals get separate rows, even when proj+phase+task match.** Per Ryan's rule (see [[feedback-survey-proposals-separate-lines]]), each distinct proposal under Sales Admin 0000-00826 (e.g. Wamsutter, Fergus Electric) must occupy its own timesheet row. To add a second row at the same proj+phase+task: open the Options menu (kebab icon, `button.rowTools_menuBtn` at x≈1863 in the right pane) of the existing 6.07 row and click **Copy** (menu items are labeled `Insert` / `Copy` / `Delete`, NOT "Insert new row" / "Copy row" / "Delete row" as older versions had). Save immediately. After reload, both rows are independently addressable by grid 0 row index. Note: row matching by `project_number + task_name + row_marker` will hit only the FIRST match — use direct grid-row-index dispatch when two rows share all three.

12. **Options menu items renamed.** The Options menu items are now `Insert`, `Copy`, `Delete` (not `Insert new row`, `Copy row`, `Delete row`). Update any selector searches.

### Method B: Chrome MCP (FALLBACK — for edge cases)

Use Chrome MCP browser tools when dev-browser can't handle something:
- Copy Previous Timesheet workflow (Kendo dropdown caret workaround)
- Phase/task lookups (magnifying glass dialog)
- Adding new project rows ("+ Add Line")
- Any dialog interaction that needs visual inspection

See `references/deltek-guide.md` for full Chrome MCP automation details.

### Handling Modifications

To modify an already-entered value via dev-browser:

```bash
dev-browser --connect --timeout 20 <<'EOF'
const page = await browser.getPage("deltek");
// Click row, click day cell, update value, save
await page.evaluate(() => { /* find and click row */ });
await page.mouse.click(cellX, cellY); // open popup
await page.evaluate((newHours) => {
  const reg = document.getElementById('regHrs');
  reg.focus(); reg.select();
  reg.value = String(newHours);
  reg.dispatchEvent(new Event('change', { bubbles: true }));
}, 8.0);
// Save...
EOF
```

---

## Writing dev-browser Scripts for Deltek

When you need to build a new script or modify the existing one, follow these patterns. This is how Deltek's Kendo UI grid works:

### Deltek DOM Structure

The timesheet has **6 grid panes** (`.gridBody.absolute`):
- Grid 0: Left pane — project rows (scrollable)
- Grid 1: Left pane — pinned/selected project rows
- Grid 2: Cell editor popup area
- Grid 3: Right pane — day cells matching grid 0
- Grid 4: Right pane — day cells matching grid 1
- Grid 5: Totals row

### Finding and clicking a project row

```javascript
await page.evaluate((searchText) => {
  const grids = document.querySelectorAll('.gridBody.absolute');
  for (const grid of grids) {
    for (const row of grid.querySelectorAll('tr')) {
      if (row.textContent.includes(searchText)) {
        row.click();
        return;
      }
    }
  }
}, "Staff Meetings"); // Use task name for specificity
```

### Finding day cell positions

When a row is selected, 7 inputs with class `input-element number_input` appear (Sun-Sat, sorted by x position):

```javascript
const cells = await page.evaluate(() => {
  const inputs = [];
  document.querySelectorAll('input.input-element.number_input').forEach(inp => {
    if (inp.offsetParent !== null) {
      const rect = inp.getBoundingClientRect();
      inputs.push({ x: Math.round(rect.x + rect.width/2), y: Math.round(rect.y + rect.height/2), value: inp.value });
    }
  });
  return inputs.sort((a, b) => a.x - b.x); // [Sun, Mon, Tue, Wed, Thu, Fri, Sat]
});
```

### Opening the cell editor popup

**Must use `page.mouse.click(x, y)`** — DOM click events don't trigger the Kendo popup:

```javascript
await page.mouse.click(cells[1].x, cells[1].y); // Monday
await page.waitForTimeout(600);
```

### Stable field selectors in the popup

| Field | Selector | Notes |
|-------|----------|-------|
| REGULAR hours | `document.getElementById('regHrs')` | Stable ID — set `.value` + dispatch input/change/blur |
| OVERTIME hours | `document.getElementById('ovtHrs')` | Stable ID |
| Total hours | `document.getElementById('totHrs')` | Read-only |
| **Comment (authoritative storage)** | `document.getElementById('commentEntry')` | **`<div contenteditable="true">` — set `.textContent` + dispatch InputEvent. THIS is what Deltek reads on Save.** |
| Comment dropdown filter (display only) | `document.querySelector('input[name="commentDdwn"]')` | Filters the past-comments dropdown list — **setting `.value` here does NOT save the comment**, even though the input briefly shows the text. Mirror to it for visual consistency, but `commentEntry` is what counts. |

**Comment field gotcha (learned the hard way):** Setting `.value` on `input[name="commentDdwn"]` makes the field LOOK populated and Save proceeds without complaint, but Deltek persists an empty comment. The visible filter input is wired to a hidden contenteditable `<div id="commentEntry">` that holds the real value. Always write to `commentEntry.textContent` AND dispatch an `InputEvent` with `bubbles: true` so the framework registers the change. Verify with `document.getElementById('commentEntry').textContent === expectedComment` BEFORE clicking Save.

### Setting field values

Hours: set `.value` + dispatch events. Comment: set `textContent` on the contenteditable div + dispatch `InputEvent`:

```javascript
await page.evaluate((hours, comment) => {
  // Hours
  const reg = document.getElementById('regHrs');
  reg.focus(); reg.select();
  reg.value = String(hours);
  reg.dispatchEvent(new Event('input', { bubbles: true }));
  reg.dispatchEvent(new Event('change', { bubbles: true }));
  reg.dispatchEvent(new Event('blur', { bubbles: true }));

  // Comment — write to the AUTHORITATIVE contenteditable div, not the filter input
  const ce = document.getElementById('commentEntry');
  ce.focus();
  ce.textContent = comment;
  ce.dispatchEvent(new InputEvent('input', { bubbles: true, data: comment, inputType: 'insertText' }));
  ce.dispatchEvent(new Event('change', { bubbles: true }));
  ce.dispatchEvent(new Event('blur', { bubbles: true }));

  // Mirror to the filter input for visual consistency (optional)
  const f = document.querySelector('input[name="commentDdwn"]');
  if (f) {
    f.value = comment;
    f.dispatchEvent(new Event('input', { bubbles: true }));
    f.dispatchEvent(new Event('change', { bubbles: true }));
  }
}, 8.0, "Field survey work");

// VERIFY before Save — Deltek will silently save no comment if commentEntry is empty
const commentSet = await page.evaluate((c) => document.getElementById('commentEntry').textContent === c, "Field survey work");
if (!commentSet) throw new Error("comment did not stick");
```

### Saving

```javascript
await page.evaluate(() => {
  for (const el of document.querySelectorAll('span')) {
    if (el.textContent.trim() === 'Save' && el.offsetParent !== null) {
      el.click();
      return;
    }
  }
});
await page.waitForTimeout(1000);
```

### Taking screenshots for verification

```javascript
const buf = await page.screenshot();
const path = await saveScreenshot(buf, "timesheet-verify.png");
console.log(path); // Claude reads this file to verify
```

### Reading page state (AI snapshot)

```javascript
const snap = await page.snapshotForAI();
console.log(snap.full); // Accessibility tree — find refs, labels, values
```

---

## Updating the Project CSV

When a new project is encountered and confirmed by the user, add it to `timesheet_projects.csv` so future recordings can find it. The CSV has three columns: `Project Number`, `Project Name`, `Notes`.

---

## Weekly File Lifecycle

1. **Created** when user first records time for a new week
2. **Updated** as user adds/modifies entries throughout the week  
3. **Entries marked "entered"** after being pushed to Deltek
4. **Kept as a record** — don't delete old weekly files, they serve as a log
