# White paper review criteria — {TITLE} v{VERSION} run (STATIC — fixed {DATE}; never edit during the loop)

Reviewer: judge the rendered page images (100 + 200 dpi) and the PDF text against EVERY item. Report PASS/FAIL per item with page reference and a concrete fix for each FAIL. List optional polish separately. End with exactly "VERDICT: PASS" or "VERDICT: FAIL".
Sources of truth: {SOURCES_DOC} (current state), plus {CODE/FINDING FILES}. RH rulings listed in the lettered sections below count as sourced.
`kit/check_pdf.py` has already passed (fonts, page size, stranded H1, cover flush, figure text scale); re-check only what it cannot see.

## A. Brand (stahly-proposal brand_spec.md + brand_deltas.md)
A1. Brand colors only; red only for warnings.
A2. Rockwell for cover, H1 and footer; Arial for body.
A3. Official logo unaltered, clear space, no tile behind the badge.
A4. Locked cover composition, bands flush to the page bottom; cover shows "Version {VERSION}".
A5. Tan footer band with "Page N of M" in white Rockwell Italic; H1 Rockwell Bold blue with rule.
A6. US Letter portrait; ~0.85" side margins.

## B. Content (one item per fact the paper must state; write these from the sources doc)
B1. White paper, not a proposal; Author line = {AUTHOR, TITLE}.
B2–B9. {Each required fact, rule, name, path, number — specific and checkable.}
B10. No claim beyond the sources; no placeholder text; master/template locations and author given.

## C. Quality
C1. No overflow, clipping, overlaps, orphaned headings, or tables split with fewer than 2 rows on a side.
C2. Figures legible at print size (figure text ≥ ~7 pt).
C3. No large accidental blank areas (cover and end of document excepted).
C4. Plain language, concise; ≤ {N} body pages.
C5. Spelling clean; glossary terms consistent.

## D. Purpose fit
D1. Every section serves the scope line: {SCOPE LINE}. Out-of-scope procedure ({e.g. vendor software how-to}) stays out.
D2. Written to the reader as "you"; only clearly labelled sections address other roles.
D3. Internal cross-references (figures, sections) are clickable links that land on the right page.

## E. {Approved items from RH / reader round N — add a new lettered section per round; it wins over older items it conflicts with and names the items it supersedes.}
