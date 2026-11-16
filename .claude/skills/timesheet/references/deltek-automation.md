# Deltek automation reference

Consult when a step in SKILL.md fails or a new script is needed. SKILL.md's Enter steps are the procedure; this file holds the reasons and the edge cases.

## Setup: debug Chrome and tab connection

**Prerequisites**: `dev-browser` installed (`npm i -g dev-browser`), Chrome running with `--remote-debugging-port=9222` AND a separate `--user-data-dir`, user logged into Deltek.

**CRITICAL — Chrome must be launched with a separate profile.** Chrome 130+ silently rejects `--remote-debugging-port` against the default user profile (security restriction). The CDP TCP socket may bind but `/json/version` returns 404 and `dev-browser --connect` hangs on the WS handshake. The `chrome://inspect` "Discover" toggle is for finding remote devices, not for exposing CDP locally — it does NOT fix this. Workflow when CDP isn't responding:
2. Relaunch with a dedicated debug profile (preserves user's main Chrome): `Start-Process "C:\Users\rharbach\AppData\Local\Google\Chrome\Application\chrome.exe" -ArgumentList "--remote-debugging-port=9222","--remote-allow-origins=*","--user-data-dir=C:\Users\rharbach\.chrome-debug-profile","https://seaeng.deltekfirst.com/SeaEng/app/"`
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


## Lessons (failure modes seen on real runs)

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

13. **Duplicate rows (same proj+phase+task): use `row_index`.** `enter-timesheet.js` accepts an optional `row_index` (grid 0 `<tr>` index) that overrides text matching. Get indices from a grid-0 dump after the copies are saved. `verify-timesheet.js` does NOT support it — verify those cells with an inline script.

14. **Verify with a real mouse click on the row, not `r.click()`.** On 2026-10-05 a JS `row.click()` during verify sometimes left the previous row selected, so the popup showed the previous row's hours/comment (5 of 14 false failures). Clicking the row's 2nd `<td>` with `page.mouse.click` after `scrollIntoView` fixed all of them. Cross-check hours independently by reading grid 3 `<td>` text per row index — that ignores selection state.

15. **`add-line.js` returns `no_lookup_dialog`** for multi-word searches ("West of Havre"), and often for projects already on the sheet. Use `scripts/add-line-v2.js` (`add2.json`: `[{"s","phase","task"}]`). It reloads per row, waits 4 s for the lookup dialog, retypes a stale filter, and selects project, phase and task by mousedown/up on each `<td>`, then Select and Save. A full project number (e.g. `2108-00925`) as `s` works reliably. Some overhead projects have tasks you might not expect (Education 0000-00007 → 6.02). If Select stays disabled, a task is required.

16. **Bottom-of-grid rows (`popup_not_open`/`row_not_found`).** Newly added rows land at the bottom. The left pane scrolls but the right pane's day inputs don't line up with the row, so the click misses. `scripts/enter-timesheet.js` handles this by default: it sets `page.setViewportSize({width:1900,height:1600})`, selects the row with a real click, then real-clicks the day input at its own coordinates. JS-dispatched clicks did NOT open the popup here. (enter-bottom-rows.js was merged into enter-timesheet.js on 2026-11-16.)

17. **Fast hours check: `scripts/grid-dump.js`.** It prints each row's grid-3 hours and the grid-5 daily totals. Compare against the JSON's per-day sums before running the slow comment sweep.

18. **Copy Previous Timesheet:** the dropdown needs a real `page.mouse.click` on `.tap-target`, then a real click on the `<li>` (e.g. `10/25/2026 - 10/31/2026`). JS `.click()` leaves Copy disabled. Click Copy, then Save right away.

19. **Session expiry:** Deltek logs out overnight (the page shows `User ID  Password`). Stop and ask Ryan to log in, then `page.goto` the timesheet URL again.

20. **Screenshots time out** when the debug Chrome window is hidden or behind other windows. Read state from the DOM instead (`document.body.innerText`, grid dumps).

21. **Submit** is a `<span>` "Submit" (top right). Clicking it opens "Confirm Electronic Signature" with a password box. **Ryan types his password himself.** Never fill it. Submit only when he asks, then reload and confirm `Timesheet Status: Submitted` plus the grid-5 totals.


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
