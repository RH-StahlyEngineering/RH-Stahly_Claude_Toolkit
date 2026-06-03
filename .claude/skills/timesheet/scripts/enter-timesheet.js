// enter-timesheet.js — Fast timesheet entry via dev-browser
// Usage: Write entries to ~/.dev-browser/tmp/entries.json, then run:
//   dev-browser --connect --timeout 240 run enter-timesheet.js
//
// IMPORTANT: The Deltek timesheet must already be open in a Chrome tab.
// This script auto-discovers the tab by URL — DO NOT use a named alias for
// browser.getPage() (that creates a fresh blank tab).
//
// Entry shape (each entry in entries.json):
//   {
//     project_number: "3733-00226",       // required — for row matching
//     task_name: "Site Survey",           // required — for row matching
//     row_marker: "6.07",                 // optional — disambiguator if task_name is ambiguous
//     day: "Mon",                         // required — Sun..Sat
//     hours: 5.0,                         // required — replaces any existing value in the cell
//     comment: "Field prep for 8th Ave"   // required — replaces any existing comment
//   }
//
// CONSOLIDATE FIRST: This script writes ONE value per cell. If the source
// JSON has multiple entries for the same project+task+day, sum hours and
// merge comments BEFORE writing entries.json — the script does NOT do that.

const tabs = await browser.listPages();
const deltekTab = tabs.find(t => t.url && t.url.includes('deltekfirst.com'));
if (!deltekTab) {
  console.log(JSON.stringify({ success: false, error: "no_deltek_tab" }));
} else {
  const page = await browser.getPage(deltekTab.id);

  const raw = await readFile("entries.json");
  const data = JSON.parse(raw);
  const entries = data.entries.filter(e => !e.status || e.status === "pending");

  const dayMap = { Sun: 0, Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6 };
  const results = [];

  // Helper: dismiss the cell editor popup if open
  async function closePopup() {
    const open = await page.evaluate(() => {
      const r = document.getElementById('regHrs');
      return !!(r && r.offsetParent !== null);
    });
    if (open) {
      await page.evaluate(() => {
        const banner = document.querySelector('.gridHeader')
          || document.querySelector('.timekeeper-header')
          || document.querySelector('.breadcrumbs');
        if (banner) banner.click();
      });
      await page.waitForTimeout(800);
    }
  }

  for (const entry of entries) {
    try {
      // 1. Ensure popup is closed before clicking next row
      await closePopup();

      // 2. Scroll the target row into view, then click it.
      // CRITICAL: skip rows where offsetParent === null (hidden pinned/clone rows in grid 1).
      // Prefer grid 0 (main project pane). A hidden clone in grid 1 will match the search
      // text but clicking it does nothing — we'd silently end up entering data into the
      // wrong cell or reading empty data on verify.
      const found = await page.evaluate((args) => {
        const grids = document.querySelectorAll('.gridBody.absolute');
        const tryGrid = (g) => {
          if (!g) return false;
          for (const r of g.querySelectorAll('tr')) {
            if (r.offsetParent === null) continue;
            const txt = r.textContent;
            if (txt.includes(args.proj) && txt.includes(args.task) && (!args.marker || txt.includes(args.marker))) {
              r.scrollIntoView({ block: 'center', behavior: 'instant' });
              return true;
            }
          }
          return false;
        };
        if (tryGrid(grids[0])) return { found: true };
        for (const g of grids) if (tryGrid(g)) return { found: true };
        return { found: false };
      }, { proj: entry.project_number, task: entry.task_name, marker: entry.row_marker });

      if (!found.found) {
        results.push({ ...entry, status: "row_not_found" });
        continue;
      }
      await page.waitForTimeout(500);

      await page.evaluate((args) => {
        const grids = document.querySelectorAll('.gridBody.absolute');
        const tryGrid = (g) => {
          if (!g) return false;
          for (const r of g.querySelectorAll('tr')) {
            if (r.offsetParent === null) continue;
            const txt = r.textContent;
            if (txt.includes(args.proj) && txt.includes(args.task) && (!args.marker || txt.includes(args.marker))) {
              r.click();
              return true;
            }
          }
          return false;
        };
        if (tryGrid(grids[0])) return;
        for (const g of grids) if (tryGrid(g)) return;
      }, { proj: entry.project_number, task: entry.task_name, marker: entry.row_marker });
      await page.waitForTimeout(700);

      // 3. Find day cell coordinates and click via mouse (DOM click won't open Kendo popup)
      const dayIdx = dayMap[entry.day];
      const cellPos = await page.evaluate((di) => {
        const inputs = [];
        document.querySelectorAll('input.input-element.number_input').forEach(inp => {
          if (inp.offsetParent !== null) {
            const rect = inp.getBoundingClientRect();
            inputs.push({ x: Math.round(rect.x + rect.width/2), y: Math.round(rect.y + rect.height/2), value: inp.value });
          }
        });
        inputs.sort((a, b) => a.x - b.x);
        return inputs[di] || null;
      }, dayIdx);

      if (!cellPos) {
        results.push({ ...entry, status: "day_cell_not_found" });
        continue;
      }

      await page.mouse.click(cellPos.x, cellPos.y);
      await page.waitForTimeout(900);

      let popupOpen = await page.evaluate(() => {
        const el = document.getElementById('regHrs');
        return !!(el && el.offsetParent !== null);
      });
      if (!popupOpen) {
        // Retry once
        await page.mouse.click(cellPos.x, cellPos.y);
        await page.waitForTimeout(900);
        popupOpen = await page.evaluate(() => {
          const el = document.getElementById('regHrs');
          return !!(el && el.offsetParent !== null);
        });
        if (!popupOpen) {
          results.push({ ...entry, status: "popup_not_open" });
          continue;
        }
      }

      // 4. Fill REGULAR hours
      await page.evaluate((args) => {
        const reg = document.getElementById('regHrs');
        reg.focus(); reg.select();
        reg.value = String(args.hours);
        reg.dispatchEvent(new Event('input', { bubbles: true }));
        reg.dispatchEvent(new Event('change', { bubbles: true }));
        reg.dispatchEvent(new Event('blur', { bubbles: true }));
      }, { hours: entry.hours });
      await page.waitForTimeout(200);

      // 5. Fill comment — write to authoritative contenteditable div, NOT the filter input.
      // input[name="commentDdwn"] is just a dropdown filter; it filters the past-comments
      // list and looks like a comment field, but Save reads commentEntry.textContent.
      await page.evaluate((args) => {
        const ce = document.getElementById('commentEntry');
        if (ce) {
          ce.focus();
          ce.textContent = args.comment;
          ce.dispatchEvent(new InputEvent('input', { bubbles: true, data: args.comment, inputType: 'insertText' }));
          ce.dispatchEvent(new Event('change', { bubbles: true }));
          ce.dispatchEvent(new Event('blur', { bubbles: true }));
        }
        // Mirror to filter input for visual consistency only
        const f = document.querySelector('input[name="commentDdwn"]');
        if (f) {
          f.value = args.comment;
          f.dispatchEvent(new Event('input', { bubbles: true }));
          f.dispatchEvent(new Event('change', { bubbles: true }));
        }
      }, { comment: entry.comment });
      await page.waitForTimeout(300);

      // 6. VERIFY comment stuck before saving — Deltek silently saves blank if commentEntry is empty
      const commentOk = await page.evaluate((c) => {
        const ce = document.getElementById('commentEntry');
        return ce && ce.textContent === c;
      }, entry.comment);
      if (!commentOk) {
        results.push({ ...entry, status: "comment_not_set" });
        continue;
      }

      // 7. Save
      await page.evaluate(() => {
        for (const el of document.querySelectorAll('span')) {
          if (el.textContent.trim() === 'Save' && el.offsetParent !== null) {
            el.click();
            return;
          }
        }
      });
      await page.waitForTimeout(1500);

      results.push({ ...entry, status: "entered" });
    } catch (err) {
      results.push({ ...entry, status: "error", err: String(err) });
    }
  }

  // Final cleanup: close any lingering popup
  await closePopup();

  console.log(JSON.stringify({
    total: results.length,
    entered: results.filter(r => r.status === "entered").length,
    failed: results.filter(r => r.status !== "entered").length,
    results
  }, null, 2));
}
