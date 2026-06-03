// verify-timesheet.js — Post-entry verification sweep for Deltek timesheet
// Usage: Write expected entries to ~/.dev-browser/tmp/entries.json, then run:
//   dev-browser --connect --timeout 240 run verify-timesheet.js
//
// Re-opens every cell and confirms persisted hours + comment match expectations.
// Catches silent comment drops that bypass the entry script's pre-save verify.
//
// Entry shape (each entry in entries.json):
//   {
//     project_number: "3733-00226",   // for row matching
//     task_name: "Site Survey",       // for row matching
//     row_marker: "6.07",             // optional disambiguator
//     day: "Mon",                     // Sun..Sat
//     hours: 5.0,                     // expected (compared as formatted "5.00")
//     comment: "Field prep ..."       // expected (exact textContent match)
//   }

const tabs = await browser.listPages();
const deltekTab = tabs.find(t => t.url && t.url.includes('deltekfirst.com'));
if (!deltekTab) {
  console.log(JSON.stringify({ success: false, error: "no_deltek_tab" }));
} else {
  const page = await browser.getPage(deltekTab.id);

  const raw = await readFile("entries.json");
  const data = JSON.parse(raw);
  const entries = data.entries;
  const dayMap = { Sun: 0, Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6 };
  const results = [];

  async function closePopup() {
    const open = await page.evaluate(() => {
      const r = document.getElementById('regHrs');
      return !!(r && r.offsetParent !== null);
    });
    if (open) {
      await page.evaluate(() => {
        const banner = document.querySelector('.gridHeader, .timekeeper-header, .breadcrumbs');
        if (banner) banner.click();
      });
      await page.waitForTimeout(700);
    }
  }

  // Format expected hours like Deltek does ("5" -> "5.00", "0.5" -> "0.50", "9.25" -> "9.25")
  function fmt(h) {
    const n = Number(h);
    return n.toFixed(2);
  }

  for (const entry of entries) {
    await closePopup();

    // Find a VISIBLE matching row (skip hidden pinned-grid duplicates).
    // Prefer grid 0 (main project pane). Pinned/clone rows in grid 1 with offsetParent=null
    // would otherwise match the search and lead the script to click into nothing.
    await page.evaluate((args) => {
      const grids = document.querySelectorAll('.gridBody.absolute');
      // First pass: prefer visible row in grid 0
      const main = grids[0];
      if (main) {
        for (const r of main.querySelectorAll('tr')) {
          if (r.offsetParent === null) continue;
          const t = r.textContent;
          if (t.includes(args.proj) && t.includes(args.task) && (!args.marker || t.includes(args.marker))) {
            r.scrollIntoView({block: 'center'});
            return;
          }
        }
      }
      // Fallback: any visible matching row
      for (const g of grids) {
        for (const r of g.querySelectorAll('tr')) {
          if (r.offsetParent === null) continue;
          const t = r.textContent;
          if (t.includes(args.proj) && t.includes(args.task) && (!args.marker || t.includes(args.marker))) {
            r.scrollIntoView({block: 'center'});
            return;
          }
        }
      }
    }, { proj: entry.project_number, task: entry.task_name, marker: entry.row_marker });
    await page.waitForTimeout(500);

    await page.evaluate((args) => {
      const grids = document.querySelectorAll('.gridBody.absolute');
      const main = grids[0];
      if (main) {
        for (const r of main.querySelectorAll('tr')) {
          if (r.offsetParent === null) continue;
          const t = r.textContent;
          if (t.includes(args.proj) && t.includes(args.task) && (!args.marker || t.includes(args.marker))) {
            r.click();
            return;
          }
        }
      }
      for (const g of grids) {
        for (const r of g.querySelectorAll('tr')) {
          if (r.offsetParent === null) continue;
          const t = r.textContent;
          if (t.includes(args.proj) && t.includes(args.task) && (!args.marker || t.includes(args.marker))) {
            r.click();
            return;
          }
        }
      }
    }, { proj: entry.project_number, task: entry.task_name, marker: entry.row_marker });
    await page.waitForTimeout(700);

    const cellPos = await page.evaluate((args) => {
      // Find the y of the matching row in grid 0 first, so we can filter inputs to ONLY that row.
      const grids = document.querySelectorAll('.gridBody.absolute');
      let rowY = null;
      const findInGrid = (g) => {
        for (const r of g.querySelectorAll('tr')) {
          if (r.offsetParent === null) continue;
          const t = r.textContent;
          if (t.includes(args.proj) && t.includes(args.task) && (!args.marker || t.includes(args.marker))) {
            const rect = r.getBoundingClientRect();
            return Math.round(rect.y + rect.height/2);
          }
        }
        return null;
      };
      if (grids[0]) rowY = findInGrid(grids[0]);
      if (rowY === null) {
        for (const g of grids) { rowY = findInGrid(g); if (rowY !== null) break; }
      }
      const inputs = [];
      document.querySelectorAll('input.input-element.number_input').forEach(inp => {
        if (inp.offsetParent === null) return;
        const rect = inp.getBoundingClientRect();
        const cy = Math.round(rect.y + rect.height/2);
        // Filter to inputs whose y is within ±15px of the target row (one row tall).
        if (rowY !== null && Math.abs(cy - rowY) > 15) return;
        inputs.push({ x: Math.round(rect.x + rect.width/2), y: cy });
      });
      inputs.sort((a, b) => a.x - b.x);
      return inputs[args.di] || null;
    }, { di: dayMap[entry.day], proj: entry.project_number, task: entry.task_name, marker: entry.row_marker });

    if (!cellPos) {
      results.push({ ...entry, ok: false, reason: "no_cell" });
      continue;
    }

    await page.mouse.click(cellPos.x, cellPos.y);
    await page.waitForTimeout(800);

    const v = await page.evaluate(() => {
      const ce = document.getElementById('commentEntry');
      const reg = document.getElementById('regHrs');
      return { hours: reg ? reg.value : null, comment: ce ? ce.textContent : null };
    });

    const expHours = fmt(entry.hours);
    const expComment = entry.comment;
    const hoursOk = v.hours === expHours;
    const commentOk = v.comment === expComment;
    results.push({
      project_number: entry.project_number,
      task_name: entry.task_name,
      day: entry.day,
      expected: { hours: expHours, comment: expComment },
      actual: v,
      ok: hoursOk && commentOk,
      hoursOk,
      commentOk
    });
  }

  await closePopup();

  console.log(JSON.stringify({
    okCount: results.filter(r => r.ok).length,
    problemCount: results.filter(r => !r.ok).length,
    problems: results.filter(r => !r.ok),
    all: results
  }, null, 2));
}
