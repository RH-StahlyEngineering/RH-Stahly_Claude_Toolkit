# Visual QA Checklist

This checklist is mandatory. Render the proposal to PNGs (`scripts/render_qa.py`), then walk through each page and check items off. **Do not declare the proposal complete until every box is `[x]` against a rendered PNG.** Text-only inspection is not enough — most of the issues this catches are invisible without looking.

Status convention: `[ ]` not yet checked · `[~]` applied in code, not yet visually verified · `[x]` visually verified against the current rendered PNG.

## Cover (p01)

- [ ] Masthead: thin Stahly Blue + thin Stahly Tan stripes at very top, clean alignment, no gaps
- [ ] Project title left-aligned, Rockwell Bold ~24pt, Stahly Blue, two-line break sensible if needed
- [ ] Project subtitle italic Rockwell, Stahly Blue, immediately below title
- [ ] "A proposal to:" Rockwell ~18pt, Stahly Blue
- [ ] Client name Rockwell Bold ~18pt, Stahly Blue, NOT touching the cover photo
- [ ] Date Rockwell Italic ~12pt Stahly Blue, below client name
- [ ] Cover photo (if present): centered below title block, max width 6.6″, with subtle Stahly Tan border
- [ ] Cover photo has no software UI / no red working markup (map callouts, scale bars, north arrows are OK)
- [ ] Cream firm-name band positioned below photo zone, full bleed width, with thin Stahly Blue rule along its top edge only
- [ ] Cream band: "Stahly Engineering & Associates" Rockwell 18pt + "Professional Services" + "Proposal" Rockwell Bold 28pt all left-aligned in Stahly Blue
- [ ] Cover logo right-aligned inside cream band, ≥0.10″ clearance to top blue rule and to band's left/right edges
- [ ] Logo NOT on a solid blue tile (transparent PNG on cream)
- [ ] Cream band's bottom edge is flush with the blue address band's top edge (no gap, no double-rule)
- [ ] Blue address band: 5 office columns evenly spaced, tan Arial 9pt, fully bleeds left and right
- [ ] Blue address band's bottom edge is flush with the tan tagline band's top edge (no gap)
- [ ] Tan tagline band at page bottom: white-italic Rockwell, "Engineering Excellence for More Than 50 Years" centered

## Page 2 (typically Introduction + Scope of Work)

- [ ] Address meta block at top: plain Arial, body indent, NO left accent rule
- [ ] Date in meta block matches the date on cover
- [ ] First H1 ("Introduction"): Rockwell Bold ~15pt Stahly Blue, with thin Stahly Blue rule beneath
- [ ] ≥22pt of breathing room above each subsequent H1
- [ ] H2 subheadings (Survey Corridor, Acquisition, etc.): Arial Bold 11pt black
- [ ] Body Arial 11pt black, justified, ≤2 levels of bullets
- [ ] Bullets use single `•` glyph, indented 0.25″
- [ ] Footer band tan, full bleed, on this page
- [ ] Footer "Page 1 of N" right-aligned in Rockwell Italic 11pt white
- [ ] Footer logo bottom-right, badge sized to fit cleanly above the band, no overlap with body text
- [ ] Body text never extends below MARGIN_BOT (≥0.50″ above footer band)

## Body pages (middle of proposal)

- [ ] Every H1 has Stahly Blue underline rule + ≥22pt above
- [ ] H1 + first paragraph stay together (no orphan H1 at page bottom)
- [ ] No body text overlaps footer logo on any page
- [ ] Page numbering is "Page N of M" with N and M correct (cover does not get a page number)
- [ ] Bullet lists kept to ≤2 levels deep
- [ ] If tables present: Stahly Blue header row, white Arial Bold 11pt header text, Stahly Tan-tint zebra body rows, Stahly Cream TOTAL row (if applicable)
- [ ] If fee table present: every line item rounded to nearest $100, TOTAL is the in-code sum of the rounded rows, $-figures in TOTAL right-aligned in Rockwell Bold ~13pt

## Signature page (typically last body page)

- [ ] Closing paragraph (Thank you / We look forward...)
- [ ] "Sincerely," + firm name STAHLY ENGINEERING & ASSOCIATES bold
- [ ] Signature line (0.5pt rule, ~2.5″ wide)
- [ ] Signatory printed name in Arial Bold 12pt below the signature line
- [ ] Signatory title in Arial Italic 11pt below the name
- [ ] Signatory contact lines (office, address, phone, email) in Arial 10pt Stahly Blue

## Exhibit pages (if present)

- [ ] Landscape orientation OK for exhibit content
- [ ] "Exhibit A" / "Exhibit B" / etc. label top-right corner in Rockwell Bold Stahly Blue
- [ ] Footer band present and rotated to match landscape orientation
- [ ] Footer page number visible (counted in `Page N of M`)
- [ ] Footer logo bottom-right of the rotated band

## Brand compliance (audit)

- [ ] Stahly Blue rendered as `#00548C` (pixel-sample any blue band to confirm)
- [ ] Stahly Tan rendered as `#BABAB1`
- [ ] Stahly Cream rendered as `#E9E6E1`
- [ ] Body type is Arial, not Cambria
- [ ] Headlines are Rockwell, no other slab-serif substitutes
- [ ] Logo files are the official transparent PNGs (no blue-tile composite, no Cambria-era assets)
- [ ] No off-brand reds anywhere except in cover photo annotations (which are content, not brand)

## Cross-document consistency

- [ ] Date matches across cover, page 2 meta block, and (if applicable) docx writeback
- [ ] Fee total in callout/table matches workbook total within reasonable rounding tolerance
- [ ] Schedule narrative duration matches any docx schedule paragraph
- [ ] Signatory in sign-off block matches the office chosen at intake
- [ ] HDR feature codes (if proposal is LiDAR) match HDR's published code list — flag any unfamiliar codes with the user
