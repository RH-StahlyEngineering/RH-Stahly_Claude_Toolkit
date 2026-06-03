// verify-pof.js — re-read every field from the live form and compare to pof.json.
// Tolerates form-side reformatting: phone auto-format, date zero-padding, $-prefix on money.

const raw = await readFile("pof.json");
const { pof } = JSON.parse(raw);

const tabs = await browser.listPages();
const jot = tabs.find(t => (t.url||'').includes('form.jotform.com/232545214343146'));
if (!jot) throw new Error("JotForm tab not found");
const page = await browser.getPage(jot.id);

const FIELDS = [
  ["date_month","month_373","text"],["date_day","day_373","text"],["date_year","year_373","text"],
  ["project_number_4digit","input_314","text"],["project_number_5digit","input_315","text"],
  ["project_name","input_4","text"],["project_description","input_5","textarea"],
  ["project_manager","input_6","text"],["eor_sor","input_8","text"],
  ["form_preparer","input_441","text"],["estimate","input_319","money"],
  ["given_to_client","input_10","select"],["pm_email","input_456","text"],
  ["rate_table","input_11","select"],["billing_terms","input_13","select"],
  ["time_to_be_moved_to_project","input_14","select"],
  ["client_name","input_15","text"],["client_address1","input_16","text"],
  ["client_address2","input_18","text"],["client_city_state_zip","input_20","text"],
  ["contact_first","first_53","text"],["contact_last","last_53","text"],
  ["phone","input_22_full","tel"],["cell","input_54_full","tel"],["email","input_329","text"],
  ["is_new_client","q438_isThis","radio"],["client_type","input_439","select"],
  ["office_location","input_85","select"],["department","input_27","select"],
  ["funding_type","input_28","select"],["grant_funded","q437_grantFunded","radio"],
  ["move_proposal_to_project_folder","input_440_0","checkbox"],
  ["deltek_structure","q450_howDo","radio"],["invoice_setup","q451_howDo451","radio"],
  ["more_than_5","q68_ifYou","radio"],["formal_agreement","input_12","select"],
  ["latitude","input_430","text"],["longitude","input_431","text"],
  ["notes_for_accounting","input_432","textarea"],
];

const ROW_KEYS = ["phase","task","start","end","labor","expenses","total","pay","eor","dept"];
const ROW_IDS = [
  ["input_255","input_256","input_257","input_258","input_376","input_377","input_320","input_260","input_261","input_262"],
  ["input_379","input_380","input_381","input_382","input_383","input_384","input_385","input_386","input_387","input_388"],
  ["input_389","input_390","input_391","input_392","input_393","input_394","input_395","input_396","input_397","input_398"],
  ["input_399","input_400","input_401","input_402","input_403","input_404","input_405","input_406","input_407","input_408"],
  ["input_409","input_410","input_411","input_412","input_413","input_414","input_415","input_416","input_417","input_418"],
];
const ROW_KINDS = ["text","text","date","date","money","money","money","select","text","select"];

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

// Normalizers — strip format the form may auto-apply so comparisons aren't false positives.
function normalize(value, kind) {
  if (value === null || value === undefined) return value;
  const s = String(value);
  if (kind === "tel") return s.replace(/\D/g, "");                         // (406) 538-3465  ->  4065383465
  if (kind === "money") return s.replace(/[$,\s]/g, "");                   // $78,900 -> 78900
  if (kind === "date") {
    // accept M/D/YYYY and MM/DD/YYYY as equivalent
    const m = s.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
    return m ? `${m[1].padStart(2,'0')}/${m[2].padStart(2,'0')}/${m[3]}` : s;
  }
  return s;
}

const ok = [];
const mismatches = [];

for (const [key, id, kind] of FIELDS) {
  const expected = pof[key];
  if (expected === undefined || expected === null || expected === "") continue;

  const got = await page.evaluate(({ id, kind }) => {
    if (kind === "radio") {
      const chosen = Array.from(document.querySelectorAll(`input[type=radio][name="${id}"]`)).find(r => r.checked);
      return chosen ? chosen.value : null;
    }
    if (kind === "checkbox") {
      const el = document.getElementById(id);
      return el ? el.checked : null;
    }
    const el = document.getElementById(id);
    return el ? el.value : null;
  }, { id, kind });

  let pass;
  if (kind === "checkbox") {
    const expectedBool = (expected === true || expected === "true" || expected === "Yes" || expected === "yes" || expected === 1);
    pass = got === expectedBool;
  } else {
    pass = normalize(got, kind) === normalize(expected, kind);
  }

  if (pass) ok.push({ key, id, kind, value: got });
  else mismatches.push({ key, id, kind, expected, got, normExpected: normalize(expected, kind), normGot: normalize(got, kind) });
}

console.log(JSON.stringify({
  ok: mismatches.length === 0,
  okCount: ok.length,
  mismatchCount: mismatches.length,
  mismatches
}, null, 2));
