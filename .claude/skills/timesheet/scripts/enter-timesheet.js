// enter-timesheet.js — fill timesheet cells from entries.json. Rows must already exist (run preflight.js first).
// Usage: dev-browser --connect --timeout 400 run enter-timesheet.js
// entries.json: { entries: [{ project_number, task_name, row_marker?, row_index?, day, hours, comment, status }] }
//   row_marker: extra text the row must contain (e.g. "6.07") when task_name is ambiguous
//   row_index:  grid 0 <tr> index; overrides text matching when rows share proj+phase+task
// Skips entries with status "entered". Output: { total, entered, failed, results: [{...entry, status}] }
// Why it works: a 1900x1600 viewport keeps the day inputs on screen, a reload per cell resets row pinning,
// and real mouse clicks on the row and the day input open the Kendo popup (JS clicks do not).
const tabs = await browser.listPages();
const page = await browser.getPage(tabs.find(t => t.url && t.url.includes('deltekfirst.com')).id);
await page.setViewportSize({ width: 1900, height: 1600 });
const D = { Sun: 0, Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6 };
const todo = JSON.parse(await readFile("entries.json")).entries.filter(e => e.status !== "entered");
const results = [];

// One cell holds one value: unconsolidated duplicates would overwrite each other.
const cellKey = (e) => [e.project_number, e.task_name, e.row_marker || "", e.row_index ?? "", e.day].join("|");
const counts = new Map();
for (const e of todo) counts.set(cellKey(e), (counts.get(cellKey(e)) || 0) + 1);

const rowCenter = (a) => page.evaluate((a) => {
  const rows = [...document.querySelectorAll('.gridBody.absolute')[0].querySelectorAll('tr')];
  const r = a.idx != null ? rows[a.idx]
    : rows.find(r => r.offsetParent && r.textContent.includes(a.p) && r.textContent.includes(a.t) && (!a.m || r.textContent.includes(a.m)));
  if (!r || !r.textContent.includes(a.p)) return null;
  r.scrollIntoView({ block: 'center' });
  const b = r.querySelectorAll('td')[1].getBoundingClientRect();
  return { x: b.x + b.width / 2, y: b.y + b.height / 2 };
}, a);

for (const e of todo) {
  if (counts.get(cellKey(e)) > 1) { results.push({ ...e, status: "duplicate_cell_consolidate_first" }); continue; }
  const a = { p: e.project_number, t: e.task_name, m: e.row_marker || "", idx: e.row_index ?? null };
  await page.reload(); await page.waitForTimeout(6000);
  if (!(await rowCenter(a))) { results.push({ ...e, status: "row_not_found" }); continue; }
  await page.waitForTimeout(500);
  const rc = await rowCenter(a);
  await page.mouse.click(rc.x, rc.y); await page.waitForTimeout(1000);
  const ip = await page.evaluate((di) => {
    const ins = [...document.querySelectorAll('input.input-element.number_input')].filter(i => i.offsetParent)
      .sort((a, b) => a.getBoundingClientRect().x - b.getBoundingClientRect().x);
    if (!ins[di]) return null;
    const r = ins[di].getBoundingClientRect();
    return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
  }, D[e.day]);
  if (!ip) { results.push({ ...e, status: "day_cell_not_found" }); continue; }
  await page.mouse.click(ip.x, ip.y); await page.waitForTimeout(1000);
  if (!(await page.evaluate(() => !!document.getElementById('regHrs')?.offsetParent))) {
    results.push({ ...e, status: "popup_not_open" }); continue;
  }
  // Hours in REGULAR; comment into #commentEntry (the contenteditable Deltek saves), mirrored to the filter input.
  await page.evaluate((a) => {
    const reg = document.getElementById('regHrs');
    reg.focus(); reg.select(); reg.value = String(a.h);
    ['input', 'change', 'blur'].forEach(t => reg.dispatchEvent(new Event(t, { bubbles: true })));
    const ce = document.getElementById('commentEntry');
    ce.focus(); ce.textContent = a.c;
    ce.dispatchEvent(new InputEvent('input', { bubbles: true, data: a.c, inputType: 'insertText' }));
    ['change', 'blur'].forEach(t => ce.dispatchEvent(new Event(t, { bubbles: true })));
    const f = document.querySelector('input[name="commentDdwn"]');
    if (f) { f.value = a.c; f.dispatchEvent(new Event('input', { bubbles: true })); }
  }, { h: e.hours, c: e.comment });
  if (!(await page.evaluate((c) => document.getElementById('commentEntry').textContent === c, e.comment))) {
    results.push({ ...e, status: "comment_did_not_stick" }); continue;
  }
  await page.evaluate(() => { const s = [...document.querySelectorAll('span')].find(el => el.textContent.trim() === 'Save' && el.offsetParent); s && s.click(); });
  await page.waitForTimeout(2500);
  results.push({ ...e, status: "entered" });
}
const entered = results.filter(r => r.status === "entered").length;
console.log(JSON.stringify({ total: todo.length, entered, failed: results.length - entered, results }, null, 2));
