# White-paper brand deltas

Everything here layers on top of stahly-proposal's `brand_spec.md`. Proposal-only content (fees, signatures, client block, "A proposal to:") stays out.

## Color roles
- Stahly Blue: H1s, rules, title, address band, table headers.
- Tan: footer band, tagline band, table borders.
- Cream: firm-name band, callout fills, zebra rows.
- Navy `#043348`: H2s, subtitle. Gray `#787878`: "WHITE PAPER" kicker.

## Cover
- Locked bottom-up stack from brand_spec: tagline band (0.55") → address band (0.90", offices from offices.json, closed offices excluded) → cream firm-name band (2.10").
- Title block: replace "A proposal to: client" with subtitle, author, date. "WHITE PAPER" kicker above title.
- Build the cover as one full-page table, exact row heights, in a zero-margin section, so bands stay flush.
- Logos: `StahlyLogo_EO_official.png` on cover, `StahlyLogo_Artboard1_official.png` in footer, unaltered.

## Body
- US Letter portrait, 0.85" side margins; H1 Rockwell Bold Stahly Blue + 0.75pt blue rule + space above; H2 Arial Bold navy.
- Tan footer band ~0.55" on every body page, `Page N of M` in white Rockwell Italic.

## LibreOffice gotchas
- **Glyph fallback**: Rockwell lacks "·" (middle dot); LibreOffice silently substitutes Segoe UI. Use "|" as separator. Verify `pdffonts` lists only Rockwell and Arial families.
- **Footer field formatting**: page-number fields sharing a run with text lose formatting (render black, upright). Post-process footer XML so each PAGE/NUMPAGES field has its own fully formatted run with a cached result (`kit/fixfooter.py`).
- **Keep-with-next before a table keeps the whole table**: it drags the entire table to the next page and leaves a gap. To keep a heading with its table, set keepNext on the first table row's paragraphs only (`keepFirst` in the kit), not on the intro paragraph.
- **Table splits**: rows `cantSplit`; a split must leave ≥ 2 rows on each side. Put a CAUTION as its own red row directly under the tool/step it concerns; it stays adjacent and splits cleanly.
- **Text extraction**: narrow two-column tables extract scrambled in `pdftotext -layout`; one-column rows ("**name** — description") extract in order. "→" and list bullets extract as blanks/U+FFFD; harmless on the page.
- **Cover flush**: the cover table must total 15840 − 6 twips; less leaves a white strip under the tagline band.
- **Curly apostrophes**: the build file mixes `’` and `’`; normalise to one before scripted find/replace.

## Figures
- Render PIL figures at 1900 px wide; at 6.8" print width, text ≥ 27 px is ≈ 7 pt (the legibility floor). Size the docx image from the PNG's own aspect ratio.
- Brand colors only; red (#C00000) only for warnings. Leave ≥ 10 px padding at every edge; check each figure at full size before building.
- Internal links: docx `Bookmark` on the target (caption or heading) + `InternalHyperlink`; external paths as `file://` links (they stay absolute).
