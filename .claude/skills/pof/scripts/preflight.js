// preflight.js — verify POF form is loaded and required-id set matches schema
const tabs = await browser.listPages();
const jot = tabs.find(t => (t.url||'').includes('form.jotform.com/232545214343146'));
if (!jot) { console.log(JSON.stringify({ ok: false, error: "JotForm tab not found" })); return; }
const page = await browser.getPage(jot.id);

const EXPECTED = [
  "input_4","input_6","input_8","input_319","input_11","input_13","input_14",
  "input_15","input_22_full","input_85","input_27","input_28","input_12","input_35"
];

const result = await page.evaluate((expected) => {
  const missing = expected.filter(id => !document.getElementById(id));
  const submitVisible = !!document.getElementById('input_35');
  const fieldCount = document.querySelectorAll('.form-line').length;
  return { missing, submitVisible, fieldCount };
}, EXPECTED);

console.log(JSON.stringify({ ok: result.missing.length === 0, ...result }));
