---
name: stahly-white-paper
description: Write and build a branded Stahly Engineering white paper, internal guide, SOP, standard, or technical procedure doc (PDF). Use when drafting, restructuring, branding, revising from redlines, or reviewing a Stahly white paper or internal guidance document.
---

# Stahly white paper

Goal: a paper the reader can **follow**, **follow accurately**, and enjoy, in Stahly brand. Six gates, in order: **Intake → Draft → Build → QA → Revise → Publish**.

## 1. Intake
Pin down, asking RH only what you cannot infer:
- **Reader**: who, novice or expert in this topic.
- **Job**: the one decision or task the paper drives, as one sentence. This is the **scope line**; it outranks every review comment and persona note.
- **Doc type**: explanation, how-to/procedure, reference, or tutorial. A mixed paper gets one section per type.
- **Sources**: the one decisions doc (and code/finding files) every claim must trace to. Keep it a single current-state doc: rewrite superseded entries in place, history in a changelog at the bottom, so reviewers never need "newest section wins". Unsourced claim → ask RH, never invent.
- Title, subtitle, author, date, version, and the master location the published copy goes to.

Done when all five bullets have a concrete answer.

## 2. Draft
Apply every rule in [`references/writing_rules.md`](references/writing_rules.md). Procedures and warnings carry the accuracy rules; they are the high-stakes sections. When RH asks for graphics first: one **master figure** that tells the whole story (see `kit/figure_example.py`), at most two small companion figures, words after.

Done when every rule there is applied or consciously waived (note waivers for RH), and every section passes the scope line.

## 3. Build
Brand source of truth: `C:\Users\rharbach\.claude\skills\stahly-proposal\references\brand_spec.md` (colors, fonts, logo, layout, refusals). Logos: that skill's `assets/`; offices: its `references/offices.json`. White-paper deltas and LibreOffice gotchas: [`references/brand_deltas.md`](references/brand_deltas.md).

Start from `kit/`: `build_example.js` (docx-js: cover, footer, H1/H2, tables, callouts, CAUTION, figures, internal links), `fixfooter.py` (footer field fix; pass the paper title), `render.sh` (docx → PDF → 100 dpi PNGs → `check_pdf.py`), `figure_example.py` (PIL figures in brand colors). Keep body text in one content block (or file) and edit it with scripts written by the Write tool; Windows paths and `\u` escapes break inline `python -c`, heredocs and `sed`.

## 4. QA
`check_pdf.py` must show 0 FAIL before any reviewer runs; fix mechanical layout yourself, it is cheaper than a review round. Before the first build, write a static criteria list (template: `kit/criteria_example.md`): brand, content (sources + writing_rules), quality, purpose fit (scope line). Later approved changes go in a new lettered section that wins over older ones; never edit criteria mid-loop. Dispatch a fresh independent reviewer subagent each round on the page PNGs, 200 dpi renders, `pdffonts` and the sources; fix and re-review until every item passes. Optional reader check: `kit/persona_field_reader.md` with `{JOB}` filled in; treat its notes as input, filter them through the scope line, and ask RH before acting.

Then recommend a walkthrough: 2–5 real readers do the task from the paper while someone watches. Strongest single error-catcher; RH arranges it.

## 5. Revise from redlines
RH marks up PDFs in Revu. Read annotations with PyMuPDF (`page.annots()`: type, rect, content) and render the page with a wide clip so comments in the margin show. Confirm which version was marked up (cover version) before mapping comments. Bump the version, log new decisions in the sources doc, add a criteria section, rebuild, re-run QA, then save a versioned copy to Downloads and open it in Revu.

## 6. Publish
On RH's OK only: copy the final PDF and .docx (versioned names, older versions kept) to the master location from Intake, verify the copy's cover version, and update the sources doc's location note. If RH wants an announcement, draft it with `send-outlook-email` (draft only, attach the published PDF, link its master path) and remind RH to delete any stale earlier draft.
