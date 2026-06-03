// fill-pof.js — read pof.json from dev-browser temp, fill every mapped field.
// Reads {pof: {...}} from pof.json. Does NOT click Submit.

const raw = await readFile("pof.json");
const { pof } = JSON.parse(raw);

const tabs = await browser.listPages();
const jot = tabs.find(t => (t.url||'').includes('form.jotform.com/232545214343146'));
if (!jot) throw new Error("JotForm tab not found");
const page = await browser.getPage(jot.id);

// Field map: [key in pof.json, jotform input id, kind]
// kinds: text | textarea | select | radio | checkbox | tel | date3
const FIELDS = [
  ["date_month",                    "month_373",    "text"],
  ["date_day",                      "day_373",      "text"],
  ["date_year",                     "year_373",     "text"],
  ["project_number_4digit",         "input_314",    "text"],
  ["project_number_5digit",         "input_315",    "text"],
  ["project_name",                  "input_4",      "text"],
  ["project_description",           "input_5",      "textarea"],
  ["project_manager",               "input_6",      "text"],
  ["eor_sor",                       "input_8",      "text"],
  ["form_preparer",                 "input_441",    "text"],
  ["estimate",                      "input_319",    "text"],
  ["given_to_client",               "input_10",     "select"],
  ["pm_email",                      "input_456",    "text"],
  ["rate_table",                    "input_11",     "select"],
  ["billing_terms",                 "input_13",     "select"],
  ["time_to_be_moved_to_project",   "input_14",     "select"],
  ["client_name",                   "input_15",     "text"],
  ["client_address1",               "input_16",     "text"],
  ["client_address2",               "input_18",     "text"],
  ["client_city_state_zip",         "input_20",     "text"],
  ["contact_first",                 "first_53",     "text"],
  ["contact_last",                  "last_53",      "text"],
  ["phone",                         "input_22_full","tel"],
  ["cell",                          "input_54_full","tel"],
  ["email",                         "input_329",    "text"],
  ["is_new_client",                 "q438_isThis",  "radio"],
  ["client_type",                   "input_439",    "select"],
  ["office_location",               "input_85",     "select"],
  ["department",                    "input_27",     "select"],
  ["funding_type",                  "input_28",     "select"],
  ["grant_funded",                  "q437_grantFunded","radio"],
  ["move_proposal_to_project_folder","input_440_0", "checkbox"],
  ["deltek_structure",              "q450_howDo",   "radio"],
  ["invoice_setup",                 "q451_howDo451","radio"],
  ["more_than_5",                   "q68_ifYou",    "radio"],
  ["formal_agreement",              "input_12",     "select"],
  ["latitude",                      "input_430",    "text"],
  ["longitude",                     "input_431",    "text"],
  ["notes_for_accounting",          "input_432",    "textarea"],
];

const ROW_KEYS = ["phase","task","start","end","labor","expenses","total","pay","eor","dept"];
const ROW_IDS = [
  ["input_255","input_256","input_257","input_258","input_376","input_377","input_320","input_260","input_261","input_262"],
  ["input_379","input_380","input_381","input_382","input_383","input_384","input_385","input_386","input_387","input_388"],
  ["input_389","input_390","input_391","input_392","input_393","input_394","input_395","input_396","input_397","input_398"],
  ["input_399","input_400","input_401","input_402","input_403","input_404","input_405","input_406","input_407","input_408"],
  ["input_409","input_410","input_411","input_412","input_413","input_414","input_415","input_416","input_417","input_418"],
];
const ROW_KINDS = ["text","text","text","text","text","text","text","select","text","select"];

// Expand row fields onto the same shape FIELDS uses
const rows = pof.rows || [];
rows.forEach((row, i) => {
  if (i >= 5) return;
  ROW_KEYS.forEach((k, j) => {
    if (row[k] !== undefined && row[k] !== null && row[k] !== "") {
      FIELDS.push([`__row${i}_${k}`, ROW_IDS[i][j], ROW_KINDS[j]]);
      pof[`__row${i}_${k}`] = row[k];
    }
  });
});

const filled = [];
const skipped = [];
const errors = [];

for (const [key, id, kind] of FIELDS) {
  const val = pof[key];
  if (val === undefined || val === null || val === "") { skipped.push({ key, id, reason: "no value" }); continue; }

  try {
    const res = await page.evaluate(({ id, kind, val }) => {
      function fireTextEvents(el) {
        el.dispatchEvent(new Event('input',  { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
        el.dispatchEvent(new Event('blur',   { bubbles: true }));
      }
      if (kind === "text" || kind === "textarea" || kind === "tel") {
        const el = document.getElementById(id);
        if (!el) return { ok: false, error: "not found" };
        el.scrollIntoView({ block: "center" });
        el.focus();
        el.value = String(val);
        fireTextEvents(el);
        return { ok: true, persisted: el.value };
      }
      if (kind === "select") {
        const el = document.getElementById(id);
        if (!el) return { ok: false, error: "not found" };
        const target = Array.from(el.options).find(o => o.value === val || o.textContent.trim() === val);
        if (!target) return { ok: false, error: "option not found: " + val };
        el.scrollIntoView({ block: "center" });
        el.value = target.value;
        fireTextEvents(el);
        return { ok: true, persisted: el.value };
      }
      if (kind === "radio") {
        const radios = Array.from(document.querySelectorAll(`input[type=radio][name="${id}"]`));
        if (!radios.length) return { ok: false, error: "no radios for name " + id };
        const target = radios.find(r => r.value === val);
        if (!target) return { ok: false, error: "radio value not found: " + val + " options=" + radios.map(r=>r.value).join("|") };
        target.scrollIntoView({ block: "center" });
        target.click();
        target.dispatchEvent(new Event('change', { bubbles: true }));
        return { ok: true, persisted: target.value };
      }
      if (kind === "checkbox") {
        const el = document.getElementById(id);
        if (!el) return { ok: false, error: "not found" };
        const desired = (val === true || val === "true" || val === "Yes" || val === "yes" || val === 1);
        if (el.checked !== desired) {
          el.scrollIntoView({ block: "center" });
          el.click();
          el.dispatchEvent(new Event('change', { bubbles: true }));
        }
        return { ok: true, persisted: el.checked };
      }
      return { ok: false, error: "unknown kind " + kind };
    }, { id, kind, val });

    if (res.ok) filled.push({ key, id, kind, persisted: res.persisted });
    else errors.push({ key, id, kind, error: res.error });
  } catch (e) {
    errors.push({ key, id, kind, error: String(e) });
  }
}

console.log(JSON.stringify({
  filledCount: filled.length,
  errorCount: errors.length,
  skippedCount: skipped.length,
  filled, errors, skipped
}, null, 2));
