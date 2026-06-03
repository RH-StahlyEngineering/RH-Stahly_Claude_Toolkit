# Stahly Bid Workbook — Locked Spec (2026 template)

The Stahly bid workbook is a phase-based labor-and-expense estimating template.
Stahly's Marketing/Survey department maintains the master, and the file lives
at the path resolved by `canonical.resolve("bid_template")`. This spec mirrors
the layout in the 2026 template. The fingerprint described here must match
before any bid-workbook script will operate on a file; if a workbook fails the
fingerprint check, the scripts halt — they do not attempt to adapt.

## Source of truth

Resolve via `canonical.resolve("bid_template")` — never hardcode the path.
Companion docs live at the same resolver IDs:
- `bid_template_instructions` — Stahly's official "how to use" docx
- `labor_rate_sheet_standard` — current-year PDF rate sheet (Standard rates)
- `labor_rate_sheet_discounted` — current-year PDF rate sheet (Professionally
  Discounted rates)

## Cell color semantics (per Stahly's "Bidding Spreadsheet Instructions")

The template uses fill color to encode editability:

| Fill | Meaning | Script behavior |
|---|---|---|
| **Green** | Fillable input | Safe to write. Pre-flight `cell.Formula` anyway. |
| **Orange** | Drop-down (data validation list) | Writes must use a value from the list, or use the **labor-code override pattern** (see below). |
| Other / no fill | Formula or label | **Do not overwrite.** Refuse the write and surface the formula. |

The Excel-COM write helpers in `bid_workbook.py` enforce this — they refuse
to write to a cell whose `.Formula` starts with `=`.

### Labor-code override pattern

The template's row 3 (staff names) is a drop-down sourced from the `Employee
List` hidden sheet. The cell below it in row 6 (the labor-code lookup) is a
formula that INDEX/MATCHes the labor code for the selected staffer.

You can **type a bare labor code** (e.g. `LSI2`, `LPS4`) into the row-6 cell
to override the auto-lookup. This is the right move when bidding "someone at
this level, person TBD" or when bidding a person at a different level than
their current code. The rate formula in row 7 will pick up the new code.

When the override is used, **leave the row-3 staff name blank or set it to a
placeholder** — the rate is sourced from row 6 regardless once an explicit
labor code is in place.

## 2026 template layout

### Sheets

The 2026 template ships with four sheets:

| Sheet | State | Purpose |
|---|---|---|
| `Bid Sheet Template` | visible | The active bid layout. Fingerprint targets this sheet. |
| `Percent Project Setup Mosaic` | visible | Alternate layout where staff entries are percentages of work, not hours. Used for Mosaic project setup, not for fees. |
| `Rate Sheet` | hidden | Labor codes × rate columns (Standard / Professionally Discounted, per year). Source for the row-7 rate lookup. |
| `Employee List` | hidden | Staff name → labor code mapping. Source for the row-3 drop-down. |

The hidden sheets back the drop-downs and rate lookups. **Do not unhide
them by deleting them or by removing data**; use `bid_unhide.py` to make
them visible for review and re-hide before saving for delivery.

### Sheet identification (fingerprint)

A workbook is recognized as a Stahly 2026 bid workbook if **a single sheet**
satisfies all of the following:

1. Cell **B7** equals `Project Tasks` (case-insensitive, trailing whitespace OK).
2. Cell **B152** starts with `Total Project Costs`.
3. Cell **B153** starts with `TOTAL PROJECT FEE`.
4. Row **3** has at least one non-empty staff name in **G–Q** (11 staff slots).
5. Row **7** in at least one of G–Q is a formula referencing `'Rate Sheet'`.
6. Cell **A7** contains `Phase - Blue` (label that distinguishes from older
   templates).

If multiple sheets match, prefer the leftmost. If none match, fail loudly.

### Row layout (locked)

The 2026 template has **12 phase blocks**, each 12 rows (header + 10 task rows + subtotal):

| Row(s) | Contents |
|---|---|
| 1 | Client Name (col F = input) |
| 2 | Project Name (col F = input) |
| 3 | Staff names in cols G–Q (drop-down); Prepared By (C3), Checked By (E3) |
| 4 | Date (col C) |
| 5 | Sub-header labels |
| 6 | Rate code lookups (one per staff column); also Rate-Sheet selector (C6) |
| 7 | Resolved $/hr rates (formulas); also Mileage Rate (T7) and Per Diem Rate (V7) |
| 8 / 9–18 / 19 | Phase 1 header / 10 task rows / subtotal |
| 20 / 21–30 / 31 | Phase 2 |
| 32 / 33–42 / 43 | Phase 3 |
| 44 / 45–54 / 55 | Phase 4 |
| 56 / 57–66 / 67 | Phase 5 |
| 68 / 69–78 / 79 | Phase 6 |
| 80 / 81–90 / 91 | Phase 7 |
| 92 / 93–102 / 103 | Phase 8 |
| 104 / 105–114 / 115 | Phase 9 |
| 116 / 117–126 / 127 | Phase 10 |
| 128 / 129–138 / 139 | Phase 11 |
| 140 / 141–150 / 151 | Phase 12 |
| 152 | Total Project Costs (= R152 + Z152) |
| 153 | TOTAL PROJECT FEE — `=ROUNDUP(F152,-3)` (nearest $1,000) |

### Column layout (locked)

| Col | Contents | Type |
|---|---|---|
| A | Phase number (1–12) | label |
| B | Phase / Task description | input |
| C | Task Manager (drop-down); Phase 1 metadata at C3, C6 | input/drop-down |
| D | Start date | input |
| E | Finish date; Checked By at E3 | input |
| F | Task / Phase total cost (= R + Z) | **formula** |
| G–Q | 11 staff columns — hours per task per staff | input |
| R | Labor subtotal per row (formula) | **formula** |
| S | Mileage (miles) | input |
| T | Mileage rate ($/mi) — T7 is the rate; T9+ are computed | T7 input, others formula |
| U | Per diem days | input |
| V | Per diem rate ($/day) — V7 is the rate; V9+ are computed | V7 input, others formula |
| W | GPS/UAV equipment fee | input |
| X | Consultant (formula auto-adds 5%) | input |
| Y | Other miscellaneous expense | input |
| Z | Expense subtotal (formula) | **formula** |

**Staff column count:** the 2026 template has **G–Q (11 slots)**. Earlier
templates used G–K (5 slots). Scripts must enumerate G–Q.

Mileage rate (T7) defaults to `$0.75/mi`; per diem rate (V7) defaults to
`$58/day` (was `$54` in earlier templates — confirm against the resolved Rate
Sheet PDF every year). Both are **input cells** — safe to override per project.

### GPS / equipment day rates

The Rate Sheet PDF documents equipment per-unit/per-day rates. The current-year
rates from `labor_rate_sheet_standard`:

| Equipment | Rate |
|---|---|
| GPS Per Unit | `$30/hr` or `$225/day` |
| UAV/Drone | Project-specific (inquire) |
| Scanner | `$250/half day`, `$500/day` |
| Densometer eGauge | `$110/half day`, `$160/day` |
| Construction UAV Progress Photo | `$150/day` |

These get entered in **column W** of the task row. The verifier in
`verify_assets.py` checks scope-language → equipment-line coverage (e.g. if
the SOW mentions OPUS / GNSS / RTK, expect a GPS day rate; if it mentions
lidar / scanner, expect a scanner rate).

## Hidden expansion

The template hides rows and columns for layout brevity. Two patterns:

- **Hidden task rows** within each phase block. Right-click a row number →
  Unhide to expose. Phase 1's hidden rows are typically 12–18 (i.e. tasks 4–10
  are hidden by default). Use `bid_unhide.py` to expose programmatically.
- **Hidden staff columns** past column M. Columns N–Q are typically hidden;
  unhide to see additional staff slots.

When the user needs more than 10 tasks in a phase, the instructions advise
**inserting rows** within the block. Stahly's official guidance says inserts
"continue to be accounted for in the total formulas," but the F-column total
formulas use `OFFSET` and **silently break if a row is inserted at the wrong
position**. Scripts in this skill must NOT insert rows; use the existing 10
slots, unhide hidden rows, and ask the user to do row inserts manually in
Excel if needed.

## Formula structure (must be preserved)

### Per-task formulas

```
F<row> = =R<row>+Z<row>             (task total = labor + expenses)
R<row> = =+SUM(G*G7 + H*H7 + ... + Q*Q7)   (labor; multiplies hours × rate)
T<row> = =SUM(S<row>*$T$7)          (mileage cost)
V<row> = =SUM(U<row>*$V$7)          (per diem cost)
Z<row> = =SUM(Y + (X*1.05) + W + V + T)    (expense subtotal; consultant ×1.05)
```

### Per-phase subtotal formulas (rows 19, 31, 43, …, 151)

```
B<sub> = =B<header>&"Total"                       (or &" Total" with a leading space; varies)
F<sub> = =SUM(F<first>:OFFSET(F<sub>,-1,0))       (phase total)
G<sub> through Z<sub> = =SUM(<col><first>:OFFSET(<col><sub>,-1,0))
X<sub> = =SUM(X<first>:OFFSET(X<sub>,-1,0))*1.05  (consultant marked up)
```

### Grand totals

```
B152 = "Total Project Costs"
F152 = =R152+Z152
G152..Z152 = =+SUM(G19+G31+G43+G55+G67+G79+G91+G103+G115+G127+G139+G151)
B153 = "TOTAL PROJECT FEE (Rounded to nearest 1,000)"
F153 = =ROUNDUP(F152,-3)
```

The **ROUNDUP-to-$1K rule** by display context:

- **Internal displays** (audit CLI output via `bid_audit.py`, paired
  `*_log.md` files, diff snapshots): show **both** the raw number (F152
  computed sum) AND the ROUNDUP-to-$1K number (F153). The dual display
  matters when bidding decisions are being made internally — it tells the
  PM the negotiating range between the "real" cost and the rounded ask.
- **Client-facing displays** (proposal PDF fee table, contract attachments,
  cover emails): show **only one** number — the $100-rounded sum of line
  items computed by `build.py`. Showing both the $100-rounded total and the
  ROUNDUP-to-$1K total in the same PDF produces visual noise the client
  doesn't need and invites questions about which number is "real."

If the user wants different rounding for the internal bid (nearest $100
instead of $1K, for instance), change the `-3` to `-2` in F153; do not
hand-type a number into F153.

## Rate lookup

```
G7 = =IFERROR(
        INDEX('Rate Sheet'!$C$2:$J$92,
              MATCH(G$6, 'Rate Sheet'!$A$2:$A$92, 0),
              MATCH($C$6, 'Rate Sheet'!$C$1:$J$1, 0)),
        0)
```

Row 6 holds the labor code (resolved from row-3 staff name OR overridden by
the labor-code override pattern above). C6 holds the rate-sheet column
selector — typically `"2026 Standard Rates"`, drop-down sourced from
`Employee List!G1:J1`.

**Silent-underbid traps** (scripts must warn):
1. Row-3 name blank + hours present → rate resolves to 0 → free labor.
2. Row-3 name present but row-6 labor code unmapped (or row-7 IFERROR fires)
   → rate 0 → silent free labor.
3. Rate Sheet read returned a stale fallback table → published rates moved.

## Pre-existing template defects (do not flag)

The pristine 2026 template ships with **64 #N/A errors** on hidden
`Employee List` rows 74–81 (VLOOKUPs against empty employee slots). These are
benign and Stahly-owned — the skill must **not** treat them as a build
failure. The verifier baselines them against the pristine template and only
alerts on NEW errors.

## Billing patterns

### Pre-proposal scoping / kickoff hours

Hours expended on a project **before the proposal is signed** (initial
client meeting, internal kickoff, scoping calls, equipment procurement
research, site visit if applicable) are legitimately billable. The
convention:

- **Bid them in the workbook** under Phase 1 (or whatever phase
  represents project setup / mobilization). They contribute to the fee
  the same as any other hours.
- **Do not enumerate them in the proposal narrative.** The client sees
  the Phase 1 total only — they don't see "8 hours of kickoff calls
  that happened before you signed."
- Phase 1 description in the proposal can be generic: "Project Setup",
  "Mobilization", "Project Initiation". The bid workbook task description
  (column B) can be more specific for internal traceability — Stahly
  sees that, the client never does.

This is not a hack; it's standard professional services practice. The
work happened, the time has value, the bid reflects it. The proposal
just doesn't break it out.

## Hard rules for scripts

1. **Resolve paths via `canonical.resolve()`.** Never hardcode UNC paths.
2. **Use Excel COM for writes when the workbook has x14 data validations.**
   The 2026 template has them in spades; `openpyxl` strips the
   `x14:dataValidations` extension on save, which deletes every drop-down in
   the workbook. The `bid_workbook.write_*` helpers run via late-binding COM.
   Reads (`read_workbook`, `compute_total`, `fee_table_payload`) stay on
   openpyxl — read-only is safe.
3. **Work on a local copy.** UNC paths through Python ZIP / COM are fragile.
   The write helpers copy to `%TEMP%`, edit, then push back.
4. **Pre-flight every write.** Read `cell.Formula`; refuse if it starts with
   `=`. Never overwrite a formula.
5. **Use `cell.Value = None` to clear merged cells.** `ClearContents` fails
   on merge components.
6. **Use `datetime.datetime`** for any date cell, never `datetime.date`
   (COM rejects the latter).
7. **Never delete rows or columns.** OFFSET subtotal formulas break.
8. **Never insert rows or columns** (same reason — see "Hidden expansion"
   above for the supported workflow).
9. **Display both raw and ROUNDUP-to-$1K totals in INTERNAL output only**
    (audit CLI, log files, diffs). Client-facing output (proposal PDF,
    cover emails, contracts) shows only the single $100-rounded sum of line
    items — never the dual display.
10. **Warn loudly on the silent-underbid traps.**
11. **Auto-detect the bid sheet by fingerprint.** Never accept a hardcoded
    sheet name.
12. **Refuse to operate on a workbook that fails the fingerprint check.**
13. **No silent fallback when the workbook can't be opened.** Surface the
    error so the user can act (close Excel, fix the path, etc.).

## Fee-table payload for build.py

`bid_workbook.fee_table_payload()` returns:

```json
{
  "type": "fee_table",
  "title": "Fees for Professional Services",
  "lead": "The fee for the described work is based on the following…",
  "phases": [
    {"name": "Project Setup", "labor": 1336, "expenses": 0},
    {"name": "Round 1 Baseline + Monumentation", "labor": 10180, "expenses": 1957},
    ...
  ]
}
```

Phase names come from each phase block's header row (e.g. B8, B20, …, B140).
Empty phases (zero labor + zero expense) are omitted — a 12-phase template
used for a 7-phase project will yield a 7-phase payload, not a 12-phase one.
Labor and expenses are unrounded integers (rounded by `build.py`).
