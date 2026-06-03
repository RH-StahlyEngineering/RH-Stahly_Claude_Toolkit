# Content Schema — the locked proposal vocabulary

A Stahly proposal is composed of a fixed set of section types. New section types require either (a) a per-project-type schema in `schemas/` or (b) a new skill. The build script understands these types and renders them with the right H1/H2/bullet/table treatment.

## Section types (the "verbs")

| Type | Renders as | Use for |
|---|---|---|
| `intro` | Body paragraph(s) under an H1 (typically "Introduction") | Project framing, why this proposal exists |
| `subsection_group` | H1 + (optional lead-in paragraph) + N × H2 inline subheadings, each with body and optional bullets | Scope of Work with named subsections |
| `bullet_list` | H1 (or H2) + optional lead-in + bullets, ≤2 levels deep | Clarifications, exclusions, simple lists |
| `deliverables_list` | H1 + lead-in + N × bold-titled blocks with body | Deliverables section |
| `paragraph` | H1 + 1-N body paragraphs | Schedule, single-paragraph sections |
| `paragraph_group` | H1 + N body paragraphs (no H2s) | Changes in Scope, multi-paragraph closings |
| `fee_callout` | H1 + lead + 3-row callout (Unit / Length / Total) | Simple LS fee with optional unit equivalent |
| `fee_table` | H1 + lead + branded table (Phase/Labor/Expenses/Subtotal) + unit-rate footer | Phase-broken fees from workbook or intake |
| `assumptions_group` | H1 + N × H2 inline + bullets per group | Site Survey, Civil Design, etc. assumptions |
| `signature_block` | Closing paragraph + Sincerely + firm + sig line + name + title + contact | Sign-off page |
| `comparison_table` | H1 + lead + Stahly-branded table with N columns, optional bold cream footer row | Option-A-vs-Option-B savings breakdown, scope tradeoffs, side-by-side comparisons |
| `exhibit_landscape` | Standalone landscape page with image + "Exhibit X" label | Maps, big tables, panoramic figures |

## Standard order (in a single proposal)

1. Cover (auto-generated, not a section)
2. `intro` (1 paragraph minimum)
3. `subsection_group` — Scope of Work with subsections per proposal type (see `schemas/`)
4. `bullet_list` — Scope Clarifications (optional)
5. `deliverables_list` — Deliverables
6. `assumptions_group` — Assumptions
7. `paragraph` — Schedule
8. `fee_callout` OR `fee_table` — Fees for Professional Services
9. `paragraph_group` — Changes in the Identified Scope of Services
10. `signature_block` — Sign-off
11. `exhibit_landscape` × N (optional, at end)

## Content JSON structure (the "nouns")

The skill passes this JSON to `build.py --content content.json`:

```jsonc
{
  // ---- Required identification ----
  "project_name": "Hilger Substation to Roy Substation",   // splits to 2 lines if it overflows
  "project_subtitle": "LiDAR Survey – Approximately 28.1 Miles",
  "client_name": "Fergus Electric Cooperative",
  "date": "2026-05-12",
  "office": "Great Falls",                                  // looked up in offices.json
  "signatory_name": "Aaron Kensinger, P.E.",                // must exist in offices[office].signatories
  "re_line": "Hilger Substation to Roy Substation LiDAR Survey – Approximately 28.1 Miles",

  // ---- Required addressee block (top of page 2) ----
  "addressee": {
    "name": "Melanie Foran",
    "org": "Fergus Electric Cooperative",
    "street": "84423 US Highway 87",
    "city_state_zip": "Lewistown, MT 59457"
  },

  // ---- Optional cover photo ----
  "cover_photo": {
    "path": "C:/path/to/corridor_map.jpg",
    "caption": null,         // Reserved for body figures, not cover
    "annotations_ok": true   // Confirms baked-in map callouts / scale bars are acceptable
  },

  // ---- Body sections, in render order ----
  "sections": [
    {
      "type": "intro",
      "title": "Introduction",
      "body": "We appreciate the opportunity..."
    },
    {
      "type": "subsection_group",
      "title": "Scope of Work",
      "lead": "The scope of work will include:",
      "subs": [
        {"title": "Survey Corridor", "body": "The corridor extends..."},
        // Multi-paragraph body — use the list form when a subsection covers
        // multiple distinct ideas. The build engine renders each list element
        // as its own paragraph with a 0.06" spacer between. Use the string
        // form for single-paragraph bodies. verify_assets.py warns when a
        // single-string body exceeds 200 words and recommends switching to
        // the list form for readability.
        {"title": "Acquisition", "body": [
          "A combination of UAV LiDAR (Phoenix MiniRanger-3 Lite with Riegl miniVUX-3UAV) and high-resolution aerial imagery will be flown across the full corridor...",
          "Two LiDAR products will be derived: a fully classified point cloud at native density, and a thinned ground product at approximately 1 point per square meter...",
          "Classification will use a hybrid approach: ground classification performed in Phoenix Spatial Explorer Pro during point cloud generation..."
        ]},
        {"title": "Classification", "body": "The point cloud will be classified per HDR..."},
        {"title": "Ground Truthing", "body": "..."},
        {"title": "Orthophoto", "body": "..."}
      ]
    },
    {
      "type": "bullet_list",
      "title": "Scope Clarifications",
      "h_level": "H2",      // Inline H2 rather than top-level H1
      "bullets": ["Underground utility locates...", "Existing-line classification..."]
    },
    {
      "type": "deliverables_list",
      "title": "Deliverables",
      "lead": "The following deliverables will be provided...",
      "items": [
        {"title": "Classified Point Cloud", "body": "Classified LAS v1.4..."},
        {"title": "Classification Application Notes", "body": "..."}
      ]
    },
    {
      "type": "assumptions_group",
      "title": "Assumptions",
      "groups": [
        {"title": "Site Survey", "bullets": ["The site will be accessible...", "Existing horizontal and vertical control..."]}
      ]
    },
    {
      "type": "paragraph",
      "title": "Schedule",
      "body": "Fieldwork is expected to begin in May or June 2026..."
    },
    {
      "type": "fee_table",
      "title": "Fees for Professional Services",
      "lead": "The fee for the described work...",
      "phases": [
        // When `build.py --workbook <path>` is used, this array is replaced live
        // by the workbook's per-phase subtotals (auto-detected by structural
        // fingerprint). The title, lead, and corridor_miles are preserved from
        // this JSON. Otherwise, hand-typed phase numbers here are used.
        {"name": "1. PM / Admin / QA-QC", "labor": 6720, "expenses": 0},
        {"name": "2. Pre-field Prep", "labor": 5288, "expenses": 0}
      ],
      "corridor_miles": 28.132     // Used for the unit-rate footer
    },
    {
      "type": "paragraph_group",
      "title": "Changes in the Identified Scope of Services",
      "paragraphs": ["We have attempted to identify...", "If requested...", "Across the approximately 20 miles..."]
    },
    {
      "type": "signature_block",
      "thanks": "Thank you for this opportunity..."
    }
  ]
}
```

## `fee_table.phases` — supports `phase_template` for repeat-round projects

For projects where multiple phases are near-copies (e.g. quarterly monitoring
rounds, repeated structural inspections, multi-substation taps), use
`phase_template` inside the `phases` array to expand a single template into N
phases at build time:

```jsonc
"phases": [
  {"name": "Project Setup", "labor": 1336, "expenses": 0},
  {"name": "Round 1 Baseline + Monumentation", "labor": 10180, "expenses": 1957},
  {
    "phase_template": "Round {n} Quarterly Monitoring",
    "count": 4,
    "start_n": 2,
    "labor": 3937,
    "expenses": 753
  },
  {"name": "Final Summary Report", "labor": 1596, "expenses": 0}
]
```

The above expands to 7 phases at build time: Project Setup → Round 1 Baseline
+ Monumentation → Round 2 Quarterly Monitoring → Round 3 Quarterly Monitoring
→ Round 4 Quarterly Monitoring → Round 5 Quarterly Monitoring → Final Summary
Report. `{n}` is the round number; `start_n` is the first n (defaults to 1);
`count` is how many expansions.

When `--workbook` is used, the workbook's phase totals override the labor /
expenses in the template (template is only for the JSON-only path).

## `comparison_table` — shape

For two-or-more-option comparisons (Option B savings, scope variations, year-over-year). All cell values are strings — caller pre-formats currency, signs, percentages. First column is left-aligned; remaining columns right-aligned.

```jsonc
{
  "type": "comparison_table",
  "title": "Option B — Savings Breakdown",
  "lead": "Cost differences between the baseline scope and Option B:",
  "columns": ["Item", "Baseline", "Option B", "Delta"],
  "rows": [
    ["Ian Meneses (LST5) labor — 96 hr × $149/hr", "$14,304", "$0", "−$14,304"],
    ["Per diem (2 people → 1 person, all trips)",   "$696",    "$348", "−$348"],
    ["Hotel Trip 1 (2 rooms → 1 room)",            "$400",    "$200", "−$200"]
  ],
  "footer_row": ["Net delta (rounded to nearest $1,000)", "", "", "−$13,000"]
}
```

Renderer uses the same Stahly Blue header / Stahly Tan tint alternating-row treatment as `fee_table`. Footer row, if provided, gets a Stahly Cream background and a thick blue rule above (signals it's a summary).

Column widths: first column 40% of the 6.8″ body width; remaining columns evenly split the rest.

## General-purpose patterns

These patterns apply across all proposal types — surface them at intake
when the project shape matches.

### Multi-deliverable close-out (default: no separate summary)

When a project has N repeat-instance deliverables (quarterly monitoring
rounds, multi-phase inspections, multi-site campaigns), the default
should be **no separate final summary report**. The last instance becomes
the close-out and looks identical to the prior ones.

Why: ceremonial summary reports add labor cost without value if the
client's own engineer is going to roll up the data. Skipping the
summary also leaves the door open for a follow-on engagement (extension
of monitoring, formal analysis as a separate scope).

Override the default only when:
- The client explicitly asked for a final summary
- The contract requires a formal close-out for regulatory reasons
  (e.g., API 653 Annex B-formatted output, agency closeout)
- The proposal's value pitch depends on the synthesis ("we'll deliver
  a comprehensive trend analysis at year-end")

At intake, ask: "Is there a value in a separate final summary, or
should the last instance be the close-out?" Default the answer to
"last instance is close-out."

### Client-choice scope elements (offer both, let client pick)

When a scope element has **two or more acceptable methods** AND the
choice depends on client approval that hasn't been confirmed yet
(invasive vs non-invasive, destructive vs reversible, permanent vs
temporary), do **not** pick one in the proposal. Offer both, with
neutral language: **"either A or B, at the Client's election."**

Examples:
- Drilled-and-set survey nail vs. surface-bonded epoxy disc (when
  drilling into client asset is not yet approved)
- Permanent vs. temporary benchmark monumentation (when long-term
  ground rights aren't confirmed)
- Painted vs. flagged construction stakes (when ground markings
  may be objected to)
- Photographic documentation vs. notes-only (when site is
  security-sensitive)

The benefit: avoids locking the proposal into a method the client
will reject, which would force a contract amendment or re-bid.

Use a `subsection` or sub-bullet in the SOW. Example phrasing:

> Measurement marks will be installed at each of the eight stations
> using **one of the following methods, at the Client's election**:
> (a) drilled-and-set hardened survey nail with structural epoxy, or
> (b) surface-bonded survey disc using a non-expanding structural
> epoxy. Whichever method is selected, the same physical point will
> be re-occupied each round.

## Validation rules (enforced by `verify_assets.py`)

- `project_name`, `client_name`, `date`, `office`, `signatory_name`, `re_line`, `addressee` are required
- `office` must exist in `offices.json`
- `signatory_name` must exist in `offices[office].signatories`
- `date` must parse as YYYY-MM-DD and be within today − 30 to today + 90 days
- Every `subsection_group` must have ≥1 sub
- Every `deliverables_list` must have ≥1 item
- Every `fee_table` must have ≥1 phase with `labor ≥ 0`
- `cover_photo.path`, if given, must exist on disk and have AR ≥ 1.0 (landscape) or ≥ 0.9 (square-ish OK)
- Standard order in the JSON is recommended but not enforced — sections render in given order
