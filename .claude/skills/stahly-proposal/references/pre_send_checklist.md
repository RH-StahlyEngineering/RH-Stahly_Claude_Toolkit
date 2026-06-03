# Pre-send "Cover Your Ass" checklist

**When to use:** Final pass before the proposal PDF leaves Stahly. This is content QA on top of the visual QA in `qa_checklist.md`. Visual QA catches "the table looks orphaned"; this catches "the table commits us to something we didn't mean."

Walk every item before declaring final. The proposal lands in front of the client as the formal commitment — anything ambiguous becomes their interpretation, not ours.

## Fee structure

- [ ] **Lump sum vs T&M is explicit per phase.** If any phase is T&M, the Basis column in the fee table labels it `T&M NTE`. Don't rely on the lead paragraph alone — the column makes it row-by-row.
- [ ] **Grand total matches the sum of $100-rounded line items.** `build.py` enforces this in code; verify the displayed total matches what `Fee math:` printed at build time.
- [ ] **Per-mile rate (if shown) is rounded to $10**, not exact-dollar. Exact-dollar implies false precision.
- [ ] **Expenses are broken out from labor on any phase where there are direct expenses.** Bundling expenses into labor reads as opaque.
- [ ] **No firm-fixed and T&M language conflict.** A phase shown as "Lump Sum" in the Basis column must not be described as T&M anywhere else in the proposal.

## Scope structure (additions vs removals)

- [ ] **Additional scope handled.** "Changes in the Identified Scope of Services" paragraph 1 names T&M billing for additions; paragraph 2 names lump-sum amendment process. Both should be present.
- [ ] **Removal mechanism present if any phase is T&M NTE.** See `references/clauses/scope_removal_clause.md`. The clause should be a separate paragraph in the Changes section.
- [ ] **Project-specific carve-outs explicit.** Items intentionally excluded from base scope (e.g., the opposite-side existing-line classification on Hilger-Roy) have a sentence explaining the carve-out and that a separate proposal can be issued for that work.

## Third-party preconditions

- [ ] **Schedule paragraph names every third-party deliverable that gates the start.** See `references/clauses/third_party_preconditions.md`. Don't promise dates without naming what has to happen first.
- [ ] **Assumptions section names the same preconditions** — the two locations should match.
- [ ] **Internal logistics are NOT in the proposal.** Equipment procurement, crew assignment, internal scheduling are Stahly's problem, not preconditions to call out to the client. See SKILL.md rule #8.

## Signatory + signing authority

- [ ] **Signatory's signing_limit covers the proposed grand total.** `build.py` warns if it doesn't. If the warning fires, either reduce the total or change the signatory.
- [ ] **Signatory's title is consistent between proposal and contract.** Per-proposal override is supported (`signatory_title` in content JSON) — check both files reference the same title.
- [ ] **Signature image is the right person's signature.** Easy mistake when reusing fixtures from a prior project.

## Date consistency

- [ ] **Cover date, page 2 meta block date, contract `agreement_date`, and contract `services_text`/`compensation_text` references all match.**
- [ ] **Schedule dates are absolute (specific calendar dates, not "by next month")** and consistent across the Schedule paragraph and any docx writeback.

## Internal-info leak audit

Walk SKILL.md rule #8. The most common leaks (and what to look for):

- [ ] **Equipment procurement language.** "Subject to receipt of...", "ordered upon execution", "lead time" — strip these.
- [ ] **Margin / signing-authority math.** "Within Aaron's signing authority", "$4K margin absorbed" — internal only, doesn't appear in proposal.
- [ ] **Soft commitments / hedge language.** "Tooling permitting", "best effort", "good faith" beyond what's necessary — strip.
- [ ] **Back-references to prior communications.** "Per HDR's confirmation", "as discussed on the April 23 call", "October 2025 proposal", "revised" — proposal stands alone.
- [ ] **Internal staff turnover or tool changes** beyond the named assumptions and deliverables.

## Cross-document consistency

- [ ] **Fee total in callout/table matches the bid workbook within reasonable rounding tolerance.** If you used `--workbook`, the build log records the workbook total; verify against the displayed.
- [ ] **Signatory listed in offices.json office matches the office on the proposal cover and addresses.**
- [ ] **HDR or other client feature codes (if applicable) match the published reference** — flag any unfamiliar codes with the user.
- [ ] **Methodology document (if separate) describes the same workflow as the proposal's Acquisition / Classification subsections.** Disagreements between methodology and proposal are landmines.

## Reading-as-the-client test

Final pass: read the proposal cover-to-cover as if you were the client. After every paragraph ask: *"would this make me wonder if Stahly is ready to do this work?"* If yes, the language is wrong even if the substance is right.

Don't promote the proposal to `_FINAL` or upload to DocuSign until every box is checked.
