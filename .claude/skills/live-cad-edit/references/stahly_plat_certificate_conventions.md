# Stahly plat-certificate conventions

The text on Stahly COS sheets — the four certificate blocks (Examining Land Surveyor, County Treasurer, Clerk and Recorder, Surveyor), the Certificate of Exemption, the Survey Notes, the notary acknowledgements, the basis-of-bearings note — is mostly boilerplate that ships in the template. Editing it via this skill is a recurring task. This file captures the conventions, the recurring typos, and the canonical phrasings so cleanup is consistent.

---

## The certificate blocks (typical placement: paper space, `COS_1of2`)

Each certificate is its own MText on layer `G-ANNO-CERT`. Styles vary across templates — `simplex`, `Annotative Simplex-0.08`, `Annotative Italic-0.08` are all in active use. **Do not change the style of an existing certificate to "normalize" it.** Match what's there.

| Block | Purpose |
|---|---|
| Certificate of Examining Land Surveyor | MCA 76-3-611(2)(a). Signed by reviewing PLS. |
| Certificate of County Treasurer | MCA 76-3-611(1)(b). Confirms taxes paid. |
| Certificate of Clerk and Recorder | Records the COS file date/time. |
| Certificate of Surveyor | The licensee's certification of the survey itself. Signed by the PLS who supervised the work. |
| Certificate of Exemption | When the COS qualifies for subdivision exemption — typically common-boundary relocations, MCA 76-3-207(1)(a). Two paragraphs: subdivision exemption + DEQ review exemption (MCA 76-4-103). |

---

## Fill-in fields: the `_______` + `20__` convention

Date stubs, signature blanks, name blanks, license-number blanks all use runs of underscores. The year stub for in-template certificates reads `20__` and is filled in to the current year (e.g., `2026`) at the time of the COS.

When editing in bulk:

1. **Substitute the literal `20__` for the current year FIRST** (`text.Replace('20__', '2026')`). Running underscore-tracking before this replaces `__` with a tracked underscore block and the year-stub no longer matches.
2. **Wrap every run of 2+ underscores in `{\T0.85;...}`** with the count multiplied by 1/0.85 (≈ 1.176) so the original visual length is preserved while the gaps close. Use `Expand-UnderscoreTracking` in `lib/mtext_helpers.ps1`. See `mtext_creation.md` "Tracking" for the math.

The 0.85 tracking factor is the Stahly convention for fill-in fields; it matches the CCR-tag multileader convention elsewhere in the drawing.

### Order of operations matters

```
text = text.Replace('20__', '2026')              # 1. year stub
text = Expand-UnderscoreTracking $text 0.85      # 2. underscore runs
text = text.Replace('typo', 'fix')               # 3. specific typo fixes
```

If you swap steps 1 and 2 the year stub gets eaten by the underscore wrap.

---

## Recurring typos to fix (catch list)

These have shown up across multiple Stahly COS sheets — likely from the same template-of-templates. When asked to proofread certificate-area MText, sweep for these:

| Found | Correct | Where |
|---|---|---|
| `Decemeber` | `December` | SURVEY NOTES "Date of field work" |
| `resubdivison` | `resubdivision` | Certificate of Exemption, DEQ paragraph |
| `from the purpose of relocating common boundary lines` | `for the purpose of relocating common boundary lines` | Certificate of Exemption; matches MCA 76-3-207(1)(a) verbatim |
| `MCA.,` (period + comma) | `MCA.` | Certificate of Exemption, DEQ paragraph |
| `MCA that` (missing comma before "that") | `MCA, that` | Certificate of County Treasurer |
| `acknowledge that he/she executed` | `acknowledged that he/she executed` | Notary acknowledgement blocks (Orval Shaw, Jolene Shaw, etc.) |

There may be more — when proofreading, read every certificate carefully. These are just the ones already observed.

---

## Statutory wording — verbatim from MCA

The Certificate of Exemption paragraph quotes MCA 76-3-207(1)(a) directly. The exact verbatim text is:

> "division made outside of platted subdivision for the purpose of relocating common boundary lines between adjoining properties"

Do not rephrase. Do not substitute "from" for "for." The phrasing matches the statute exactly and a reviewer will catch a deviation.

## DEQ non-applicability — the "FURTHERMORE" paragraph (preferred over "exempt")

The DEQ provision in the Certificate of Exemption block has two valid framings, depending on whether each tract exceeds the 20-acre threshold in MCA 76-4-102:

| Framing | Legal basis | When to use |
|---|---|---|
| **Exemption** ("...exempt from review by DEQ pursuant to 76-4-103, MCA. 'Subdivision' means a division of land or land so divided that creates one or more parcels containing less than 20 acres...") | 76-4-103 (Applicability — the tracts ARE a subdivision but exempt from review) | Default Stahly template wording. Use when tracts < 20 acres but qualify for one of the 76-4-103 exemption categories. |
| **Non-applicability** ("...do not constitute a 'subdivision' as defined by § 76-4-102, MCA. Accordingly, the provisions of the Montana Sanitation in Subdivisions Act do not apply, and no review or approval by the Montana Department of Environmental Quality... is required for the division of this land.") | 76-4-102 (Definitions — the tracts are not a subdivision in the first place) | **Preferred when each resulting tract exceeds 20 acres exclusive of public roadways.** Legally stronger because it ties to a definitional non-applicability rather than to an exemption category. |

When the tracts are each > 20 acres, REPLACE the default-template paragraph 2 with the FURTHERMORE non-applicability paragraph plus the utilities disclaimer:

```
FURTHERMORE, Tract 1 and Tract 2, as shown hereon, each contain more than 20 acres, exclusive of public roadways, and therefore do not constitute a "subdivision" as defined by § 76-4-102, MCA. Accordingly, the provisions of the Montana Sanitation in Subdivisions Act do not apply, and no review or approval by the Montana Department of Environmental Quality under Title 76, Chapter 4, MCA is required for the division of this land.

Water supply and wastewater systems serving the subject tracts remain subject to applicable state and local laws and regulations.
```

Tighter one-sentence variant (for space-constrained sheets):

```
FURTHERMORE, Tract 1 and Tract 2 each contain more than 20 acres and are not a "subdivision" as defined by § 76-4-102, MCA; therefore, the Sanitation in Subdivisions Act does not apply and DEQ review is not required.
```

Use `§` (U+00A7) for the section sign — matches Montana statute citation style.

**Why non-applicability beats exemption when ≥ 20 acres:** "Exempt" implies the tracts ARE a subdivision but are released from review; if the exemption category is later challenged, the property is still a subdivision. The 76-4-102 definitional non-applicability says the tracts were never a subdivision under Title 76 Chapter 4 in the first place, so the question of exemption doesn't arise.

**Owner's acknowledgement structure remains unchanged.** The notary blocks (signature acknowledgements for each owner) sit below the Certificate of Exemption text; only the DEQ paragraph inside the certificate changes.

The original "We further certify that this survey is exempt from review by the Department of Environmental Quality pursuant to 76-4-103, MCA" paragraph is the Stahly template's legacy wording — preserve it on COS surveys where any resulting tract is < 20 acres.

---

## Casing — sentence case for body text, ALL CAPS for titles, legend, and basis of bearing

Stahly's COS sheets use a consistent casing scheme that you should preserve and apply to new content:

| Element | Case |
|---|---|
| Title blocks (`{\L...}` underlined headers like "CERTIFICATE OF EXEMPTION", "TRACT 1 LEGAL DESCRIPTION", "CERTIFICATE OF SURVEYOR", "SURVEY NOTES:") | ALL CAPS |
| BASIS OF BEARING block (title AND body, including coordinate values) | ALL CAPS |
| LEGEND block (title and all entries) | ALL CAPS |
| Section breakdown / detail callouts (sheet titles like "SECTION BREAKDOWN", "DETAIL A") | ALL CAPS |
| Certificate body text (Examining Surveyor, County Treasurer, Clerk and Recorder, Surveyor, Exemption) | Sentence case |
| Legal-description body text (Tract 1 / Tract 2 descriptions) | Sentence case with proper nouns capitalized — see the sentence-case scheme in `legal-description-wattles/rules/cadd-formatting-rules.md` |
| Notary acknowledgement blocks | Sentence case |
| Survey notes body | Sentence case |

The legal-description body sentence-case scheme is detailed in the wattles skill's CADD-formatting rules — the same table applies wherever a Stahly legal description is drafted, whether typed into a CADD MText, pasted into a deed, or stored in a project file.

**Do not "normalize" certificate text to ALL CAPS or to title case.** The mix above is the Stahly standard.

When proofreading after a paste-in from a non-Stahly source, sweep for case mismatches: a paragraph that arrived in ALL CAPS belongs in sentence case; a paragraph in random title case needs the same proper-noun rules applied as a body paragraph.

## Notary block — pre-fill the state when the survey is in Montana

When the COS is filed in Montana, the notary acknowledgement line should read `Notary Public for the State of Montana` rather than leaving the state blank. Don't ship the template as `Notary Public for the State of ___` for a Montana survey — the notary will sign as a Montana notary public for a Montana COS.

For surveys outside Montana, fill in the applicable state name explicitly. The skill does not auto-fill "Montana" unless it has confirmed the COS is being filed under Montana law.

## Verified statutory citations — recheck text periodically

The certificates and survey notes cite Montana statutes and administrative rules. Statutes and rules change between sessions; verbatim text drifts. When editing or reviewing a Stahly plat, **recheck each citation against the current authoritative source** before sign-off.

Authoritative sources:

- **MCA (Montana Code Annotated)**: `https://mca.legmt.gov/` — official Montana Legislature site. Linkable section-level URLs follow the pattern `https://mca.legmt.gov/bills/mca/title_0760/chapter_0030/part_0020/section_0070/0760-0030-0020-0070.html` for §76-3-207. Adjust title/chapter/part/section numbers in the path.
- **ARM (Administrative Rules of Montana)**: `https://rules.mt.gov/` — official Montana Secretary of State site. Search by rule number (e.g., `24.183.1104`). The Legal Information Institute (`https://www.law.cornell.edu/regulations/montana/`) mirrors the same text and is sometimes easier to deep-link.

### Citations confirmed as of 2026-06 — verbatim text on file

The following citations and verbatim quotations were verified against the official sources. **Re-verify whenever drafting a new COS**; these snapshots can age out.

| Citation | Where it appears in the Stahly template | Verbatim text |
|---|---|---|
| **ARM 24.183.1104(1)(f)(iii)(C)** | Survey Note #5 (boundary-relocation notation) | `"The area that is being removed from one tract of record and joined with another tract of record is not itself a tract of record. Said area shall not be available as a reference legal description in any subsequent real property transfer after the initial transfer associated with the [certificate of survey or amended plat] on which said area is described, unless said area is included with or excluded from adjoining tracts of record."` — resolve the bracketed alternative to "certificate of survey" for a COS. |
| **MCA 76-3-207(1)(a)** | Certificate of Exemption — subdivision exemption clause | `"divisions made outside of platted subdivisions for the purpose of relocating common boundary lines between adjoining properties"` — **plural** on both "divisions" and "subdivisions" in the verbatim statute. Stahly templates have historically used the singular form (`division made outside of platted subdivision`) for readability against the single-COS context. Both are recognized practice; verbatim discipline prefers plural. |
| **MCA 76-3-611(1)(b)** | Certificate of County Treasurer | County treasurer certification that all real property taxes and special assessments assessed and levied on the land have been paid. |
| **MCA 76-3-611(2)(a)** | Certificate of Examining Land Surveyor | "When the survey data shown on the plat or certificate of survey meets the conditions pursuant to this chapter, the examining land surveyor shall certify the compliance in a printed or stamped certificate on the plat or certificate of survey." |
| **MCA 76-3-101 through 76-3-625** | Certificate of Surveyor (the licensee's certification range) | Range bounds the Montana Subdivision and Platting Act. 76-3-625 ("Violations -- actions against governing body") is the highest-numbered section in Chapter 3. |
| **MCA 76-4-102** | Certificate of Exemption FURTHERMORE paragraph (Sanitation Act definitions) | Definition of "Subdivision" at subsection **(25)** for the 20-acre threshold: `"a division of land or land so divided that creates one or more parcels containing less than 20 acres, exclusive of public roadways, in order that the title to or possession of the parcels may be sold, rented, leased, or otherwise conveyed and includes any resubdivision, any condominium, townhome, or townhouse, or any parcel, regardless of size, that provides two or more permanent spaces for recreational camping vehicles or mobile homes."` Citing `§ 76-4-102(25), MCA` is tighter than `§ 76-4-102, MCA`. |

When you find a discrepancy between the template and the verbatim source, flag it to the user (don't silently change template language a senior surveyor has approved over many surveys). When the user authorizes the change, apply it and update this snapshot.

## County officials — where to look at filing time

Treasurer, Clerk-and-Recorder, and Examining Land Surveyor names change with elections. Don't hardcode or memorize them. Look them up at filing time.

### Authoritative sources (Montana)

- **Per-county website** — most accurate, most current. Common URL patterns:
  - `https://<countyname>countymt.org/departments/<role>/` (e.g., `petroleumcountymt.org/departments/treasurer/`, `petroleumcountymt.org/departments/county-clerk-and-recorder/`)
  - `https://<countyname>.mt.gov`
  - `https://www.co.<countyname>.mt.us`
- **Montana Association of Counties** — directory of county websites: `https://www.mtcounties.org/counties/county-websites/`. Useful when you don't know the per-county URL pattern.
- **Montana Secretary of State** — election results and current officeholders.

Avoid third-party aggregators (`countyoffice.org`, `usagencies.com`, etc.) — they're frequently stale and have repeatedly returned wrong names for Montana county officials. Always cross-check against the county's own page before typing a name into a certificate.

### Confirmed Petroleum County contacts (as of 2026-06)

- **Treasurer**: Krista Rowton — `krowton@petroleummt.gov` — `https://petroleumcountymt.org/departments/treasurer/`
- **Clerk and Recorder**: see `https://petroleumcountymt.org/departments/county-clerk-and-recorder/`

These are snapshots — re-verify at each COS filing.

## Vertical column layout — gaps, signatures, bounds

Stahly COS sheets place certificates and legal descriptions in two paper-space columns. The layout discipline that has emerged from real edits:

### Bounds

- **Top bound** of the body content area: bottom of the 24×36 header block (or the bottom of whichever fixed feature sits at the top, e.g., Survey Notes when it spans both columns).
- **Bottom bound, left column**: typically the bottom edge of the inner G-ANNO-TTLB sheet frame (the big cyan rectangle).
- **Bottom bound, right column**: top of the `TITLE BLOCK 24X36` block reference.
- The bottoms differ by column because the title block lives only under the right column.

When the user describes a bound by a relative offset ("X inches below the insertion of certificate Y"), translate it into an absolute Y and use that. Don't try to compute bounds from layout geometry — let the user tell you.

### Signature-line constraint — ≥ 1″ above

Any MText whose content STARTS with underscores (the Stahly notary / signature pattern, typically `{\T0.85;____...}`) must have **at least 1″ of vertical gap** between the bottom of the item above it and the top of the signature box. This rule reflects the practical need for the signer to write a name without the line above crowding the entry.

The skill identifies signature items by `TextString` matching `^\s*\{\\T[\d.]+;_+\}` (a tracked underscore run at the start). Helper `Get-MTextContentHeight` does not check this — the layout helper does.

### Equal-gap layout with the signature constraint

`lib/mtext_helpers.ps1::Compute-EqualSpacedColumn` solves the layout where:

- All gaps between adjacent items are equal.
- Optional top and bottom margins (each a multiplier of the gap).
- One designated item index must have a minimum gap above it (≥ 1″ for signatures).

Usage pattern from this session:

```powershell
$leftHeights  = 1.804, 4.9905, 7.7371, 2.6333   # 19BDF, 1994C, 19951, 1821C
$leftLayout = Compute-EqualSpacedColumn `
    -TopBound 19.8141 `
    -BottomBound 0.9798 `
    -ItemHeights $leftHeights `
    -TopFactor 0 `
    -BottomFactor 1     # top stays fixed, bottom margin = gap
# Apply with Set-EntityY in the order of $leftCol
```

### X-alignment within each column

All items in a column should share the same `InsertionPoint.X`. Use the topmost item as the reference and slide every item below it to the same X via `Set-EntityX`. This catches sub-1/100″ drift that accumulates from manual placement.

### Same gap across columns? It depends.

When both columns are equally constrained, a shared gap looks unified. When one column has much more slack than the other (right column with 5.6″ slack vs. left with 1.7″), forcing the same gap leaves the looser column with huge top/bottom margins ("clustered in the middle"). In that case, the realistic pattern is:

- Each column independently balanced (per-column equal gap).
- Both columns top-aligned at the same Y (the topmost item in each is at the same insertion Y).

Default to per-column natural balance unless the user explicitly wants the same gap across columns. The legal-description-wattles skill, by contrast, treats "same gap across columns" as the default for paired-tract drafting — that's a description-level convention, not a layout one.

## Things to leave alone

- **`BASIS OF BEARING` (singular).** Some sources prefer "BEARINGS" (plural). Stahly uses the singular. Do not pluralize without being asked.
- **`%%D` for degree symbols** in legacy text. Honored by MText; preserve when editing existing text to avoid visual diffs from the user's eye.
- **`sft` for survey feet** in coordinate/ellipsoid-height callouts. Stahly convention.
- **Style names with paper-height suffixes like `Annotative Italic-0.08`** even when used at a different paper height. The suffix is decorative; the style is reused at 0.08, 0.10, etc. See `mtext_creation.md` "Known gotchas."

---

## Indenting numbered courses in legal descriptions

Legal-description MText on the COS sheet (typically `COS_1of2`) often contains grouped sub-courses formatted as `(1) ...`, `(2) ...`, etc. To indent them one tab:

```powershell
$tab = [char]9
$mt.TextString = [regex]::Replace(
    $mt.TextString,
    '\\P(\(\d{1,2}\))',
    "\P$tab" + '$1'
)
```

MText honors a literal tab character (`[char]9`) and renders it as advance-to-next-tab-stop. The default tab stops are typically every 0.5″ paper-relative, which produces a clean one-tab indent without any paragraph-format escape codes.

---

## Surgical editing — preserve user's manual formatting

Plat certificates are heavily user-formatted: paragraph indents, paragraph-format codes (`\pi...;`, `\pxi...;`, `\pxql;`), width adjustments, position tweaks. **Always edit `TextString` in place.** Never delete-and-recreate, even if it looks easier.

```powershell
$mt = $doc.HandleToObject($handle)
$mt.TextString = $newContent
```

When the handle is stale (e.g. the user moved the MText between model and paper space), use `Find-MTextByContent` in `lib/mtext_helpers.ps1` to locate it by pattern.

---

## When in doubt: ask which sheet, which block

A working drawing for a survey project may carry the certificate text in any of:

- Model space (drafts, "before" snapshots, scratch).
- One paper-space layout per sheet (`COS_1of2`, `COS_2of2`, etc.).
- An `xref`'d certificate-block file (rare in Stahly).

Before editing, confirm which layout contains the working version. `Find-MTextByContent -Pattern 'CERTIFICATE OF EXAMINING'` will surface every copy across every layout so you can pick the right handle.
