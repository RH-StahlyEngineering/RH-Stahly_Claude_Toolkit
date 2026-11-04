---
name: utility-locate
description: Montana 811 utility locates for Stahly survey jobs. Covers writing the ticket description from the survey-limits exhibit, the blind-locator test, entering the ticket in ITIC, and filing the responses.
---

# Utility locate (Montana 811 / ITIC)

The deliverable is a locate ticket that a utility locator can mark correctly without calling RH. That depends almost entirely on the **written description**. Locators often never see the attachment, and they never see the yellow polygon drawn in ITIC. The ITIC map only decides which utility members get notified.

## Inputs

Find these before starting. Ask RH only for what you can't find.
- **Survey-limits exhibit.** Usually `Documents\Survey\_AI\Exhibit_A_Survey_Limits.png`, or the exhibit in the proposal or SOW. It is the source of truth for the area. First decide what kind of exhibit it is:
  - **Area outline** (a closed limit around a topo or design area): treat it as a generous limit. Marking extra area is fine, missing area is not.
  - **Lines to stake or survey** (ROW lines, a boundary, an alignment): the locate area is the strip those lines bound or follow, for example the ROW itself. Keep it tight: the strip plus about 10 ft at each end and beside each line.
- **Scope of work.** Says what the survey covers: streets, frontages, buildings. Look in the project `_AI\STATE.md` or the proposal folder.
- **Project folder.** Locate responses go to `<project>\Survey_GIS_Data\4-Utility_Locates\`.
- **RH's contact.** Ryan Harbach, Stahly Engineering, 406-604-4647.

## Step 1: Write the description from the exhibit

Write the description from the exhibit, not from the text ITIC generates for each parcel. ITIC's per-parcel lines ("MARK ENTIRE PROPERTY…") are a formality. Leave them at the top of each ticket and put the real description after them.

How to write it:
- **Flat facts in ALL CAPS:** what to mark and where, nothing more.
- **Write it so the map isn't needed.** Assume the attachment never arrives, but still say "MAP ATTACHED (EXHIBIT A)" once.
- **Anchor to things visible on site or on an aerial:** named streets, intersections, back of walk, front walls of buildings, parking lots, alleys, and "first avenue east of 5th Ave S". House numbers and lot lines are invisible to a locator with an aerial. Use them only next to a visible anchor.
- **Give distances where an edge isn't a visible feature,** for example "ABOUT 100 FT DEEP" or "ABOUT 20 FT PAST SOUTH BACK OF WALK".
- **Name the block by its four bounding streets,** then list exceptions. That is clearer than building the area up from pieces.
- **Keep it to about 4 numbered items.** RH finds 8 too many. Group the streets that share the same treatment.
- **Call out the city by name** for water, sanitary sewer and storm sewer in the streets and alley: mains, services, valves, manholes, inlets. City utilities are the ones that matter most for design.
- **Say how far services go:** services to every building in the area, and services to buildings outside the area only up to the area limit.
- **End with "SURVEY FOR DESIGN. NO EXCAVATION."** and the contact line.
- **If ITIC splits the job into N tickets,** start each one with "TICKET n OF N. ALL N TICKETS COVER ONE AREA. MARK THE FULL AREA BELOW ON EVERY TICKET."
- **Private lines** (site lighting, irrigation, building to building) are not located by 811. Don't promise them. Assume they're unknown in the field.

A worked example that passed the blind test is in `references/example_toole_courthouse.md`.

## Step 2: Blind-locator test, every time the description changes

Run this after every edit. RH expects it, and it reliably catches descriptions that read fine to the author but not to a stranger.

1. Get a **blank aerial** of the area: the same kind of image as the exhibit, with no limits drawn. The proposal `source\vmap.PNG` often works. Copy it alone into a clean folder, `scratchpad\blind\aerial.png`, so the test agent can't see any other files.
2. Fit the exhibit's red line onto that aerial: `python scripts/fit_exhibit.py exhibit.png aerial.png --ex "x,y x,y ..." --ae "x,y x,y ..." --red-vertices "x,y ..." -o ref_poly.json`.
   - Pick 3–5 control points visible in both images: intersection centers, a fountain, building corners. Gridded copies help (`--grid` writes them).
   - Read the red polygon's corners from the exhibit.
   - Check `ref_on_aerial.png` by eye before trusting it.
3. Spawn a general-purpose subagent with **only** the ticket text and the aerial path. Use `references/blind_test_prompt.md`. It must save `area.json`, a single polygon in pixels.
4. Score it: `python scripts/accept.py ref_poly.json area.json --aerial aerial.png`.
   - **Area outline passes** at overlap (IoU) ≥ 0.85 with ≤ 5% missed. The script's PASS/FAIL uses this rule.
   - **Strip (lines to stake) passes** at ≤ 5% missed with ≤ 50% extra. On a narrow strip even a small margin drags overlap down, so ignore the overlap number there.
   - Look at the overlay PNG too. "Accepted" means it looks like the exhibit, not only that the numbers pass.
5. If it fails, look at where the outlines differ and fix those edges with a visible anchor or a distance. Re-test. Don't stop until it passes.

**If you can't spawn a subagent** (for example, you are a subagent yourself), don't skip the test silently and don't play the blind locator yourself, because you already know the answer. Hand back the draft marked **"UNTESTED – blind-locator test still needed"**, with the paths of the exhibit and a blank aerial if you found one, so the main session can run the test before anything is entered in ITIC.

## Step 3: Fill the ticket in ITIC

Use the app's built-in browser, not Chrome, because ITIC sessions are tied to a tab.
- RH logs in himself. Never type the password.
- Go to My Tickets → Create job ticket → **Engineering ticket** (survey and design, no excavation).
- **Map.** Search the address, then zoom in until the excavation tools appear.
  - Use the **Property (Parcel)** tool: tap parcels, check "Entire property". "Road right of way" activates after that, so set its dropdown to "Both road rights of way of the dig street".
  - Build the area only from the Parcel, Street and Route tools. Locators hate the "Other" freehand polygon.
  - The map drives which members get notified, so cover the area generously. Detail goes in the text.
- ITIC may split the job into several tickets. Accept the split.
- **Step 2 (Write instructions).**
  - Each ticket tab asks "Is area marked in white?". Answer No unless RH white-lined. Click every ticket tab so its "V" warning clears, or the tickets can't be submitted.
  - "Apply information to all tickets" does **not** copy Location of work or Remarks. Write them into every ticket. With the JS tool, set every `[name=location]` / `[name=remarks1]` and fire `input` and `change` events.
  - **Location of work:** keep ITIC's per-parcel line, then a blank line, then the full description.
  - **Remarks:** "FULL AREA DESCRIPTION IN LOCATION OF WORK. MAP ATTACHED (EXHIBIT A)."
  - **Type of work:** 48 characters max. RH's wording: "PRE-SURVEY TO DESIGN IMPROVEMENTS".
  - **Work being done for:** the client.
  - The start date fills in automatically from the submit date.
  - **Attachment:** the browser tools can't pick files, so RH attaches the exhibit himself on each ticket. ITIC doesn't list the attachment afterwards, which is normal.
- **Step 3 (Review & submit).**
  - Submit only when RH explicitly says to.
  - After submitting, record the notified members, ticket count, status and start date.

## Step 4: Record and archive

- Update the project `_AI\STATE.md`: ticket count, status, start date, members notified, and that the description passed the blind test (with its score).
- Ticket numbers arrive by email. Archive the positive responses to `Survey_GIS_Data\4-Utility_Locates\`, with the ticket number in the file name, using the stahly-outlook skill.
