# Stahly Engineering — Brand Spec (Skill source of truth)

**Last reconciled against:** Stahly Engineering Identity Guide 2025, First Edition 3.2025
(`\\Stahly\marketing\Branding-Identity\01_Brand Identity Guide\Stahly Engineering Identity Guide 2025.pdf`)

This file is what the build script enforces. If Marketing reissues the Identity Guide, **update both this file AND the constants in `scripts/build.py`** in the same commit and bump the skill changelog in `README.md`.

---

## Primary palette

| Token | Pantone | RGB | Hex | Used for |
|---|---|---|---|---|
| **Stahly Blue** | 7462 C | 0 / 84 / 140 | `#00548C` | H1 headers, address band, cover title text, callout strokes |
| **Stahly Tan** | 413 C | 186 / 186 / 177 | `#BABAB1` | Footer band, tagline band, table borders |
| **Stahly Cream** | P 169-1 C | 232 / 229 / 226 | `#E9E6E1` | Cover firm-name band, fee table TOTAL row, callout fills |

## Complementary palette (sparing accent use only)

`#C65C27` rust · `#8C8040` olive · `#043348` deep navy · `#787878` mid gray · `#C7C8CA` light gray

**Red is NOT brand-approved.** If a contrast accent is needed for exhibits, use deep navy `#043348`.

## Typography

| Role | Family | Notes |
|---|---|---|
| Headlines / cover display | **Rockwell Bold** | Primary headline font. H1, cover banners, fee total. |
| Body text | **Arial Regular** | All standard body, captions, address band, deliverable descriptions. |
| Body bold | **Arial Bold** | H2 inline subheadings, table headers. |
| Italic emphasis | Arial Italic or Rockwell Italic | Tagline, "Equivalent unit rate" note, signatory title. |

**Off-brand fonts seen on legacy proposals:** Cambria. Do not use.

## Logo

| File | Use | Notes |
|---|---|---|
| `assets/StahlyLogo_EO_official.png` | Cover hero | 4501×4278, transparent, badge + "An Employee-Owned Company" tagline baked in |
| `assets/StahlyLogo_Artboard1_official.png` | Page footer | 480×361, transparent, same composition |

**Clear-space rule:** minimum clear space on all four sides equals the cap-height of the uppercase "S" in STAHLY (~12–15% of badge diameter). The build script enforces a 0.10″ clearance to band edges.

**Don't:**
- Tint, skew, torque, tilt, or stretch the logo
- Place on busy backgrounds
- Frame it
- Use STAHLY name in any non-Rockwell font
- Place a solid color tile behind the round badge (the badge already has its own blue ring; a tile competes with it)

## Layout standards (locked)

- Page size: US Letter (8.5″ × 11″), portrait body, landscape exhibits permitted
- Margins: 1.0″ top, 0.50″ bottom (clear of footer band), 0.85″ left and right
- Footer band: 0.55″ tall, Stahly Tan, on every page including exhibits
- Page number format: `Page N of M`, Rockwell Italic 11pt white in footer band
- H1 spacing above: 22pt of breathing room
- H1 underline rule: 0.75pt Stahly Blue, full body width

## Cover composition (locked — bottom-up stack)

Bands stack tight against each other from page bottom upward:

1. **Tagline band** (0.55″) — Stahly Tan, white italic Rockwell tagline "Engineering Excellence for More Than 50 Years"
2. **Address band** (0.90″) — Stahly Blue, FLUSH against tagline band, five office columns in tan Arial 9pt
3. **Cream firm-name band** (2.10″) — Stahly Cream, FLUSH against address band, with a thin Stahly Blue rule along its top edge. Firm name in Rockwell on the left, official logo on the right.
4. **Project photo zone** — between firm-name band and title block, 6.6″ max width
5. **Title block** — top of page, project name (Rockwell Bold 24pt Stahly Blue) + subtitle italic + "A proposal to:" + client name (Rockwell Bold 18pt Stahly Blue) + date (Rockwell Italic 12pt)
6. **Masthead stripes** — top edge, thin Stahly Blue + Stahly Tan bars

## What to refuse

| Request | Response |
|---|---|
| "Make Stahly Blue darker / lighter / different" | Escalate to Marketing |
| "Use [other font] for body" | Refuse — brand-locked |
| "Use the old logo we used to have" | Refuse — Marketing controls logo files |
| "Put a red accent here" | Refuse — red isn't in palette. Offer deep navy `#043348`. |
| "Add a [non-standard section] page" | Add as H1 inside existing structure if possible; new page templates require a new skill |
