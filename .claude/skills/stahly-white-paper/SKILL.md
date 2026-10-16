---
name: stahly-white-paper
description: Write and build a branded Stahly Engineering white paper, internal guide, SOP, or technical procedure doc (PDF). Use when drafting, restructuring, branding, or reviewing a Stahly white paper or internal guidance document.
---

# Stahly white paper

Goal: a paper the reader can **follow**, **follow accurately**, and enjoy, in Stahly brand. Four gates, in order: **Intake → Draft → Build → QA**.

## 1. Intake
Pin down, asking RH only what you cannot infer:
- **Reader**: who, novice or expert in this topic.
- **Job**: the one decision or task the paper drives.
- **Doc type**: explanation, how-to/procedure, reference, or tutorial. A mixed paper gets one section per type.
- Title, subtitle, author, date.

Done when all four bullets have a concrete answer.

## 2. Draft
Apply every rule in [`references/writing_rules.md`](references/writing_rules.md). Procedures and warnings carry the accuracy rules; they are the high-stakes sections.

Done when every rule there is applied or consciously waived (note waivers for RH).

## 3. Build
Brand source of truth: `C:\Users\rharbach\.claude\skills\stahly-proposal\references\brand_spec.md` (colors, fonts, logo, layout, refusals). Logos: that skill's `assets/`; offices: its `references/offices.json`. White-paper deltas and LibreOffice gotchas: [`references/brand_deltas.md`](references/brand_deltas.md).

Build docx → PDF via LibreOffice.

## 4. QA
Before the first build, write a static criteria list: brand (brand_spec + deltas), content (writing_rules), quality. Dispatch independent reviewer subagents on the rendered page images plus `pdffonts` output; fix and re-review until every item passes.

Then recommend a walkthrough: 2–5 real readers do the task from the paper while someone watches. Strongest single error-catcher; RH arranges it.
