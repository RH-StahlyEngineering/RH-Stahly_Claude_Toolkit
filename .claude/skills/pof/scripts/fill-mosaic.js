// fill-mosaic.js — fill the Mosaic Planning Set Up Sheet that the POF form chains to on submit.
//
// Mosaic form URL: https://form.jotform.com/231225238538051
// Triggered by: clicking Submit on the POF (https://form.jotform.com/232545214343146).
// Mosaic receives POF data as URL query params (prefill).
//
// This script reads pof.json from dev-browser temp, derives per-phase resource
// allocation from rows[], and fills the 5 phase rows + each Configurable List
// widget (Additional Team Scheduling) with the team breakdown.
//
// Required pof.json additions (beyond the POF schema):
//   rows[i].team: [
//     { who: "Ryan Harbach", hours: 42 },
//     { who: "Taylor Tennant", hours: 6 }
//   ]
// The script computes percentages from hours and writes the largest-share
// person to the outer "Who"/"% of Budget" fields; remaining people go into
// the Additional Team Scheduling widget.

const raw = await readFile("pof.json");
const { pof } = JSON.parse(raw);

const tabs = await browser.listPages();
const jot = tabs.find(t => (t.url||'').includes('form.jotform.com'));
if (!jot) throw new Error("JotForm tab not found");
const page = await browser.getPage(jot.id);

// Auto-click Start Filling if present
await page.evaluate(() => {
  const btn = Array.from(document.querySelectorAll('button'))
    .find(b => b.offsetParent && /start filling/i.test(b.textContent || ''));
  if (btn) btn.click();
});
await new Promise(r => setTimeout(r, 1200));

// Mosaic field IDs per row (positions 1-5). Phase column is special: row 1 = input_20, rows 2-5 = input_29/39/48/58.
const MOSAIC_ROWS = [
  { phase: 'input_20', start: 'input_22', end: 'input_23', total: 'input_24', who: 'input_25', pct: 'input_26', widgetQid: 28 },
  { phase: 'input_29', start: 'input_32', end: 'input_33', total: 'input_34', who: 'input_35', pct: 'input_36', widgetQid: 37 },
  { phase: 'input_39', start: 'input_41', end: 'input_42', total: 'input_43', who: 'input_44', pct: 'input_45', widgetQid: 46 },
  { phase: 'input_48', start: 'input_50', end: 'input_51', total: 'input_52', who: 'input_53', pct: 'input_54', widgetQid: 55 },
  { phase: 'input_58', start: 'input_61', end: 'input_62', total: 'input_63', who: 'input_64', pct: 'input_65', widgetQid: 66 },
];

// Helper to set masked date inputs (MM/DD/YYYY mask) via per-character keyboard events
async function setMaskedDate(id, dateStr) {
  if (!dateStr) return null;
  // Accept "MM/DD/YYYY" or "M/D/YYYY" — strip slashes and zero-pad
  const parts = String(dateStr).split('/');
  const mmddyyyy = parts.length === 3
    ? parts[0].padStart(2,'0') + parts[1].padStart(2,'0') + parts[2]
    : String(dateStr).replace(/\D/g,'');
  return await page.evaluate(({id, mmddyyyy}) => {
    const el = document.getElementById(id);
    if (!el) return {ok:false, reason:'not found'};
    el.scrollIntoView({block:'center'});
    el.focus();
    el.value = '';
    el.dispatchEvent(new Event('input', {bubbles:true}));
    for (const ch of mmddyyyy) {
      el.value = el.value + ch;
      el.dispatchEvent(new KeyboardEvent('keydown', {key: ch, bubbles:true}));
      el.dispatchEvent(new KeyboardEvent('keypress', {key: ch, bubbles:true}));
      el.dispatchEvent(new Event('input', {bubbles:true}));
      el.dispatchEvent(new KeyboardEvent('keyup', {key: ch, bubbles:true}));
    }
    el.dispatchEvent(new Event('change', {bubbles:true}));
    el.blur();
    return {ok:true, val: el.value};
  }, {id, mmddyyyy});
}

async function setText(id, value) {
  if (value === undefined || value === null || value === '') return null;
  return await page.evaluate(({id, value}) => {
    const el = document.getElementById(id);
    if (!el) return {ok:false, reason:'not found'};
    el.scrollIntoView({block:'center'});
    el.focus();
    el.value = String(value);
    el.dispatchEvent(new Event('input', {bubbles:true}));
    el.dispatchEvent(new Event('change', {bubbles:true}));
    el.blur();
    return {ok:true, val: el.value};
  }, {id, value: String(value)});
}

async function getWidgetFrame(qid) {
  const frames = await page.frames();
  for (const f of frames) {
    let u;
    try { u = typeof f.url === 'function' ? await f.url() : f.url; } catch { u = ''; }
    if (u && u.includes('qid=' + qid)) return f;
  }
  return null;
}

async function fillWidgetRow(widget, rowIndex, who, pct, hours) {
  return await widget.evaluate(({rowIndex, who, pct, hours}) => {
    const inputs = Array.from(document.querySelectorAll('input[type=text]'));
    const base = rowIndex * 3;
    if (inputs.length < base + 3) return {ok:false, reason:`only ${inputs.length} inputs available`};
    function set(el, val) {
      el.scrollIntoView({block:'center'});
      el.focus();
      el.value = String(val);
      el.dispatchEvent(new Event('input', {bubbles:true}));
      el.dispatchEvent(new Event('change', {bubbles:true}));
      el.blur();
    }
    set(inputs[base + 0], who);
    set(inputs[base + 1], pct);
    set(inputs[base + 2], hours);
    return {ok:true, vals: [inputs[base+0].value, inputs[base+1].value, inputs[base+2].value]};
  }, {rowIndex, who, pct, hours});
}

async function clickAddRow(widget) {
  return await widget.evaluate(() => {
    const btn = Array.from(document.querySelectorAll('button, a, [class*=add]'))
      .find(b => b.offsetParent && /add row/i.test(b.textContent || ''));
    if (!btn) return {ok:false};
    btn.click();
    return {ok:true};
  });
}

async function clearWidgetRows(widget) {
  return await widget.evaluate(() => {
    // Force-click every remove button (hidden buttons still work via .click())
    let safety = 30;
    while (safety-- > 0) {
      const rms = Array.from(document.querySelectorAll('[class*=remove]'))
        .filter(el => {
          const t = (el.textContent||'').trim();
          return t === 'x' || t === '×' || /remove/i.test(el.className);
        });
      if (!rms.length) break;
      try { rms[0].click(); } catch {}
    }
    // Blank any remaining inputs
    Array.from(document.querySelectorAll('input[type=text]')).forEach(el => {
      el.value = '';
      el.dispatchEvent(new Event('input', {bubbles:true}));
      el.dispatchEvent(new Event('change', {bubbles:true}));
    });
    return {remaining: document.querySelectorAll('input[type=text]').length};
  });
}

// Pick rows to display per Mosaic's 5-row limit. If pof.json supplies
// `mosaic_rows_use` (e.g., ["2","3","4","5","6"] when Phase 1 is dropped),
// use those indices from pof.rows; else default to first 5.
const rowsAll = pof.rows || [];
const useIndices = (pof.mosaic_rows_use && Array.isArray(pof.mosaic_rows_use))
  ? pof.mosaic_rows_use.map(s => parseInt(s, 10) - 1)
  : rowsAll.slice(0, 5).map((_, i) => i);

const results = [];

for (let rowSlot = 0; rowSlot < 5; rowSlot++) {
  const srcIdx = useIndices[rowSlot];
  if (srcIdx === undefined || !rowsAll[srcIdx]) { results.push({slot: rowSlot, status: 'no source row'}); continue; }
  const row = rowsAll[srcIdx];
  const ids = MOSAIC_ROWS[rowSlot];
  const result = {slot: rowSlot, phase: row.phase};

  // Derive per-staff allocation from row.team (or fall back to single Who from row.eor)
  const team = row.team && Array.isArray(row.team) ? row.team : [{who: row.eor || pof.project_manager, hours: 0}];
  const totalHrs = team.reduce((s, p) => s + (p.hours || 0), 0);
  const teamPct = team.map(p => ({
    who: p.who,
    hours: p.hours || 0,
    pct: totalHrs > 0 ? Math.round((p.hours / totalHrs) * 100) : (team.length === 1 ? 100 : 0),
  }));
  // Largest share -> outer "Who"/"%"; rest -> widget rows
  teamPct.sort((a, b) => b.hours - a.hours);
  const lead = teamPct[0];
  const extras = teamPct.slice(1);

  result.phaseSet = await setText(ids.phase, row.phase);
  result.startSet = await setMaskedDate(ids.start, row.start);
  result.endSet = await setMaskedDate(ids.end, row.end);
  result.totalSet = await setText(ids.total, row.total);
  result.whoSet = await setText(ids.who, lead.who);
  result.pctSet = await setText(ids.pct, String(lead.pct));

  // Widget rows for additional team members
  if (extras.length) {
    const w = await getWidgetFrame(ids.widgetQid);
    if (!w) { result.widget = {error: 'widget not found'}; }
    else {
      // Clear default empty row first, then add fresh rows
      await clearWidgetRows(w);
      await new Promise(r => setTimeout(r, 200));
      // Need one row per extra. Widget starts at 0 rows after clear; click Add once per extra.
      for (let i = 0; i < extras.length; i++) {
        await clickAddRow(w);
        await new Promise(r => setTimeout(r, 300));
      }
      const widgetResults = [];
      for (let i = 0; i < extras.length; i++) {
        const e = extras[i];
        widgetResults.push(await fillWidgetRow(w, i, e.who, String(e.pct), String(e.hours)));
      }
      result.widget = widgetResults;
    }
  } else {
    // No additional team — leave widget with its default empty row
    result.widget = 'none';
  }

  results.push(result);
}

console.log(JSON.stringify({rowsProcessed: results.length, results}, null, 2));
