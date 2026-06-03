// preflight.js — Pre-flight check before running enter-timesheet.js
// Verifies each (project_number, task_name) in entries.json exists as a visible row
// on the live Deltek timesheet. Lists any rows that need to be added via +Add Line.
//
// Usage: dev-browser --connect --timeout 30 run preflight.js
//
// Output: { allPresent, missing: [...] }
// If missing is non-empty, add those rows BEFORE running enter-timesheet.js.

const tabs = await browser.listPages();
const deltekTab = tabs.find(t => t.url && t.url.includes('deltekfirst.com'));
if (!deltekTab) {
  console.log(JSON.stringify({ success: false, error: "no_deltek_tab" }));
} else {
  const page = await browser.getPage(deltekTab.id);
  const data = JSON.parse(await readFile("entries.json"));

  // Unique (project, task, marker) combos
  const combos = new Map();
  for (const e of data.entries) {
    const key = `${e.project_number}|${e.task_name}|${e.row_marker || ""}`;
    if (!combos.has(key)) combos.set(key, e);
  }

  const checks = await page.evaluate((keys) => {
    const grids = document.querySelectorAll('.gridBody.absolute');
    const result = [];
    for (const key of keys) {
      const [proj, task, marker] = key.split('|');
      let found = false;
      for (const g of grids) {
        for (const r of g.querySelectorAll('tr')) {
          if (r.offsetParent === null) continue;
          const t = r.textContent;
          if (t.includes(proj) && t.includes(task) && (!marker || t.includes(marker))) {
            found = true;
            break;
          }
        }
        if (found) break;
      }
      result.push({ key, found });
    }
    return result;
  }, Array.from(combos.keys()));

  const missing = checks.filter(c => !c.found).map(c => {
    const [project_number, task_name, row_marker] = c.key.split('|');
    return { project_number, task_name, row_marker: row_marker || undefined };
  });

  console.log(JSON.stringify({
    totalCombos: combos.size,
    presentCount: checks.filter(c => c.found).length,
    missingCount: missing.length,
    allPresent: missing.length === 0,
    missing
  }, null, 2));
}
