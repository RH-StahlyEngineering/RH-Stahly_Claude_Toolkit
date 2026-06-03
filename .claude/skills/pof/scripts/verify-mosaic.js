// verify-mosaic.js — re-read every Mosaic phase row and confirm percentages sum to 100%.
//
// Reads pof.json from dev-browser temp. Uses pof.mosaic_rows_use (or first 5 rows
// from pof.rows) and pof.rows[i].team to determine expected staff allocations.

const raw = await readFile("pof.json");
const { pof } = JSON.parse(raw);

const tabs = await browser.listPages();
const jot = tabs.find(t => (t.url||'').includes('form.jotform.com'));
if (!jot) throw new Error("JotForm tab not found");
const page = await browser.getPage(jot.id);

const MOSAIC_ROWS = [
  { phase: 'input_20', who: 'input_25', pct: 'input_26', widgetQid: 28 },
  { phase: 'input_29', who: 'input_35', pct: 'input_36', widgetQid: 37 },
  { phase: 'input_39', who: 'input_44', pct: 'input_45', widgetQid: 46 },
  { phase: 'input_48', who: 'input_53', pct: 'input_54', widgetQid: 55 },
  { phase: 'input_58', who: 'input_64', pct: 'input_65', widgetQid: 66 },
];

async function getValue(id) {
  return await page.evaluate(({id}) => {
    const el = document.getElementById(id);
    return el ? el.value : null;
  }, {id});
}

async function getWidgetRows(qid) {
  const frames = await page.frames();
  for (const f of frames) {
    let u;
    try { u = typeof f.url === 'function' ? await f.url() : f.url; } catch { u = ''; }
    if (u && u.includes('qid=' + qid)) {
      return await f.evaluate(() => {
        const inputs = Array.from(document.querySelectorAll('input[type=text]'));
        const rows = [];
        for (let i = 0; i < inputs.length; i += 3) {
          rows.push({
            who: inputs[i]?.value || '',
            pct: inputs[i+1]?.value || '',
            hours: inputs[i+2]?.value || '',
          });
        }
        return rows;
      });
    }
  }
  return [];
}

const rowsAll = pof.rows || [];
const useIndices = (pof.mosaic_rows_use && Array.isArray(pof.mosaic_rows_use))
  ? pof.mosaic_rows_use.map(s => parseInt(s, 10) - 1)
  : rowsAll.slice(0, 5).map((_, i) => i);

const mismatches = [];
const phaseReports = [];

for (let rowSlot = 0; rowSlot < 5; rowSlot++) {
  const srcIdx = useIndices[rowSlot];
  if (srcIdx === undefined || !rowsAll[srcIdx]) continue;
  const ids = MOSAIC_ROWS[rowSlot];
  const phaseName = await getValue(ids.phase);
  const outerWho = await getValue(ids.who);
  const outerPctStr = await getValue(ids.pct);
  const outerPct = parseFloat(outerPctStr) || 0;
  const widgetRows = (await getWidgetRows(ids.widgetQid))
    .filter(r => r.who.trim() !== '');
  const widgetPctSum = widgetRows.reduce((s, r) => s + (parseFloat(r.pct) || 0), 0);
  const total = outerPct + widgetPctSum;

  const report = {
    rowSlot: rowSlot + 1,
    phaseName,
    outerWho,
    outerPct,
    widgetRows: widgetRows.map(r => ({who: r.who, pct: parseFloat(r.pct) || 0, hours: parseFloat(r.hours) || 0})),
    sumPct: total,
  };
  phaseReports.push(report);

  if (Math.abs(total - 100) > 1) {
    mismatches.push({
      rowSlot: rowSlot + 1, phaseName,
      sumPct: total, expected: 100,
      detail: `outer ${outerPct}% + widget (${widgetPctSum}% across ${widgetRows.length} extras) != 100%`,
    });
  }
}

console.log(JSON.stringify({
  ok: mismatches.length === 0,
  mismatchCount: mismatches.length,
  mismatches,
  phaseReports,
}, null, 2));
