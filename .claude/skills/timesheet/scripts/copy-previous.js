// copy-previous.js — fill an empty timesheet (Status: Missing) with the rows of the most recent earlier timesheet, then Save.
// Usage: navigate to the week's timesheet URL first, then: dev-browser --connect --timeout 90 run copy-previous.js
// Output: { status, copiedFrom, rows: ["idx: proj | ... | task", ...] }. Does nothing unless the status is Missing.
// Every click is a real page.mouse.click: JS .click() on the dropdown leaves Copy disabled.
const tabs = await browser.listPages();
const page = await browser.getPage(tabs.find(t => t.url && t.url.includes('deltekfirst.com')).id);
const status = await page.evaluate(() => (document.body.innerText.match(/Timesheet Status:\s*(\S+)/) || [])[1] || null);
const dumpRows = () => page.evaluate(() => {
  const g = document.querySelectorAll('.gridBody.absolute')[0];
  return g ? [...g.querySelectorAll('tr')].map((r, i) => i + ': ' + [...r.querySelectorAll('td')].map(td => td.textContent.trim()).filter(Boolean).join(' | ')).filter(s => s.length > 4) : [];
});
if (status !== 'Missing') {
  console.log(JSON.stringify({ status, copiedFrom: null, rows: await dumpRows() }));
} else {
  const center = (sel, text) => page.evaluate((a) => {
    const el = [...document.querySelectorAll(a.sel)].filter(e => e.offsetParent && (a.text ? e.textContent.trim() === a.text : true)).pop();
    if (!el) return null;
    const b = el.getBoundingClientRect();
    return { x: b.x + b.width / 2, y: b.y + b.height / 2, t: el.textContent.trim() };
  }, { sel, text });
  const click = async (p, wait) => { if (!p) return false; await page.mouse.click(p.x, p.y); await page.waitForTimeout(wait); return true; };
  await click(await center('span,a,button,div', 'Other Actions'), 1000);
  await click(await center('span,a,li,div', 'Copy Previous Timesheet'), 2000);
  await click(await center('.tap-target'), 1200);
  // The list is newest first; the first date-range item is last week.
  const li = await page.evaluate(() => {
    const l = [...document.querySelectorAll('li')].find(l => l.offsetParent && /\d+\/\d+\/\d{4} - /.test(l.textContent));
    if (!l) return null;
    const b = l.getBoundingClientRect();
    return { x: b.x + b.width / 2, y: b.y + b.height / 2, t: l.textContent.trim() };
  });
  if (!(await click(li, 1000))) {
    console.log(JSON.stringify({ status, error: 'no_previous_timesheet_in_dropdown' }));
  } else {
    await click(await center('span,button,a', 'Copy'), 4000);
    await click(await center('span,button,a', 'Save'), 4000);
    console.log(JSON.stringify({ status, copiedFrom: li.t, rows: await dumpRows() }));
  }
}
