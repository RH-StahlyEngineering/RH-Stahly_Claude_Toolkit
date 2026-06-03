# Contract fill spec

How the `stahly-proposal` skill fills a Stahly Professional Services Agreement
template and staples a proposal PDF behind it. Companion to `scripts/fill_contract.py`.

## Content JSON shape

```jsonc
{
  // ---- Project identification ----
  "agreement_date": "2026-05-14",              // ISO date, renders as "May 14, 2026"
  "project_slug": "Hilger_to_Roy",             // used in output filenames

  // ---- Sections A / B / C of the contract ----
  // A is a short identifier (one sentence). B and C are typically reference-only
  // ("As described in the attached Stahly Engineering Professional Services Proposal
  //  dated <date>, which is incorporated by reference.") so the contract stays clean
  // and fee/scope detail lives only in the proposal.
  "project_description": "Roy Substation to Hilger Substation LiDAR corridor survey.",
  "services_text":       "As described in the attached Stahly Engineering Professional Services Proposal dated May 14, 2026, which is incorporated by reference.",
  "compensation_text":   "As described in the attached Stahly Engineering Professional Services Proposal dated May 14, 2026, which is incorporated by reference.",

  // ---- Client (CLIENT side of signature block) ----
  "client": {
    "legal_name":   "Fergus Electric Cooperative, Inc.",  // Use the legal entity name from MT SOS (or equivalent state registry); bare form (no descriptor) per Ryan
    "address":      "84423 US Highway 87, Lewistown, MT 59457",
    "signer_name":  "Melanie Foran, P.E.",
    "signer_title": "Engineer"
  },

  // ---- Consultant (Stahly side) ----
  "consultant": {
    "office":           "Great Falls",                        // looked up in offices.json (controls the consultant's office address in the header)
    "signatory_name":   "Aaron Kensinger, P.E.",
    // Short-form title for the contract sig block. The long form
    // ("Great Falls Regional Manager / Senior Engineer") overflows the
    // 3.5" column and bleeds into the CLIENT column. Long form is fine
    // on the proposal sign-off; the contract gets the short form.
    "signatory_title":  "Great Falls Regional Manager",
    "pm_contact":       "Ryan Harbach, P.L.S.",
    "pm_email":         "rharbach@seaeng.com"
  }
}
```

## Output files

For `agreement_date = "2026-05-14"` and `project_slug = "Hilger_to_Roy"`, the script writes
four artifacts to the output directory (defaults to the proposal PDF's parent folder):

| File | Purpose |
|---|---|
| `20260514_Hilger_to_Roy_Contract_for_DocuSign.docx` | filled contract (editable source) |
| `20260514_Hilger_to_Roy_Contract_for_DocuSign.pdf` | filled contract as PDF |
| `20260514_Hilger_to_Roy_Contract_AND_Proposal_for_DocuSign.pdf` | combined: contract pages + proposal pages, ready for the DocuSign envelope |
| `20260514_Hilger_to_Roy_Contract_for_DocuSign_log.md` | paired production log (same convention as the proposal) |

Skip the stapling step with `--no-staple` if you just need the contract by itself.

## Visual gotchas baked in (proven via 5 iterations on Hilger-to-Roy)

The default Stahly contract template fills "easily" but produces a visibly jumbled
signature block if you don't apply these three fixes. The skill enforces all three.

### 1. Two-column tab-stop alignment for the sig block

**Problem:** Template tab stops are 0.5" defaults. When the CONSULTANT title is long,
the second column (CLIENT side) gets pushed to a later default tab stop, and the
Name:/Title: labels for CLIENT no longer line up under the "CLIENT:" header.

**Fix:** force a single LEFT-aligned tab stop at **3.5"** on every sig-block row
(CONSULTANT:/CLIENT:, By:, Name:, Title:). The right column then always starts at
the same x-position regardless of how long the left-column content is.

```python
def set_two_column_tab(para, x_inches=3.5):
    ts = para.paragraph_format.tab_stops
    ts.clear_all()
    ts.add_tab_stop(Inches(x_inches), WD_TAB_ALIGNMENT.LEFT)
```

### 2. PM/Contact + Email on separate lines, at 10pt, with a hard spacer above

**Problem:** the template's original PM/Contact paragraph runs PM and Email on one
full-width line. The Email portion lands in the CLIENT column area visually,
making it look like the email is "in" the client block.

**Fix:**
- PM/Contact on one line (left-aligned, single column)
- Email Address on the line below (soft line break — `run.add_break()`)
- **10pt font** so it reads as secondary metadata, distinct from the 12pt sig block
- **An explicit empty paragraph** above the PM block (NOT just `paragraph_format.space_before`)

The empty-paragraph spacer is non-negotiable. Word can collapse adjacent
`space_after`/`space_before` to the max of the two; if the preceding paragraph already
has a non-zero `space_after`, the PM block's `space_before` may be silently absorbed
and the visual gap stays tight. An empty paragraph element in the document XML
occupies a full line regardless of surrounding styles.

```python
from docx.oxml import OxmlElement

def insert_empty_paragraph_before(para):
    empty = OxmlElement("w:p")
    para._element.addprevious(empty)
```

### 3. Use short-form titles in the contract sig block

Long titles overflow the column even with the 3.5" tab fix:
- ✗ "Great Falls Regional Manager / Senior Engineer" — bleeds past tab
- ✓ "Great Falls Regional Manager" — fits cleanly

The proposal sign-off can use the full long form (different layout). The contract
uses the short form. Keep both in `offices.json` if needed (`title` for proposal,
maybe a `contract_title` field if it ever becomes a per-signatory concern).

## Approval checklist (visual QA, mandatory)

Render the filled contract to PNGs and walk the checklist before declaring final.
Per the SKILL.md see-then-edit rule:

- [ ] Header sentence wraps cleanly; legal entity name + addresses both present
- [ ] Section A reads as a single short project-identifier sentence (no fee, no scope)
- [ ] Sections B and C reference the proposal by date and say "incorporated by reference"
- [ ] CONSULTANT:/CLIENT: headers align vertically with the Name:/Title: labels below them
- [ ] No content from CONSULTANT column bleeds into the CLIENT column area
- [ ] PM/Contact block is visibly **separated** from the sig block above by a full blank line
- [ ] PM/Contact font is visibly **smaller** than the Name/Title rows above it (10pt vs 12pt)
- [ ] Email Address sits on its own line below PM/Contact (not concatenated)
- [ ] By: signature lines on both sides are blank (DocuSign fields will be placed there at signing)
- [ ] Date in header matches the date on the proposal
- [ ] Project Manager/Contact email is the right person (often differs from the signatory)

## Process discipline

The fill script does **not** modify the master template under
`\\Stahly\stahly standards\...`. It copies the template to the project folder
first and edits only the project copy. This is enforced — the script uses
`shutil.copy2(template, project_output)` and writes back to the project output,
never the source template.

## Failure modes & recovery

| Symptom | Cause | Fix |
|---|---|---|
| Build script can't open template | Path typo, or `\\Stahly` share not mapped on this machine | Check `--template` arg or VPN/network state |
| docx → pdf step fails | Word not installed, or busy with another doc | Close all Word windows; retry. Headless Word automation needs a clean Word process. |
| Stapled PDF write fails with PermissionError | Stapled PDF currently open in a viewer | Close the viewer; re-run. Or write to a versioned name and rename manually after. |
| Sig block still looks jumbled | Tab stop wasn't applied to all 4 sig rows | Confirm `set_two_column_tab(p)` is called on each of CONSULTANT/CLIENT, By:, Name:, Title: rows |
| PM/Email run together on one line | Soft line break wasn't added correctly | `r.add_break()` must be on a separate run inside the same paragraph as the PM/Contact text |
| Gap above PM block looks tight | `paragraph_format.space_before` collapsed | Use `insert_empty_paragraph_before(p)` — explicit empty para is bulletproof |
