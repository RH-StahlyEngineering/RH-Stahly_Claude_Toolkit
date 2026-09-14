---
name: open-items
description: Use when RH wants to see, answer, or track his open decisions and actions as a file instead of chat — invoked as /open-items (refresh the answer sheet), /open-items plain (English briefing), or when RH says "answers are in the file" / "updated the file" after editing it. The sheet is the durable ledger; chat is where it's announced. For the coordinator session.
---

# Open Items

Decisions asked in chat scroll away and get lost; RH ruled that open items live in a
**file he answers inline**, opened in Notepad++. This skill is the flow that worked on
2026-08-28 (OPEN-ITEMS-2026-08-28.md), made repeatable.

## The file

- Location: `.claude/handoffs/OPEN-ITEMS-<YYYY-MM-DD>.md` — a new date starts a new
  file; within a day, refresh the same file. The plain-register variant is
  `OPEN-ITEMS-PLAIN.md` (overwritten freely; the dated sheet is the ledger).
- Always open it in Notepad++ after writing:
  `& "C:\Users\rharbach\Apps\Notepad++\notepad++.exe" <path>`

## Mode 1 — `/open-items`: write or refresh the answer sheet

Structure, in this order (grouping is by **what RH must do**, never by which session
raised an item — the reporting discipline in `dronemapper-launch` § "How to report to
RH" governs, and this file is that discipline in durable form):

1. **DECISIONS** — one block per open decision:
   - Plain-English context, 2–5 lines: what it is, why it's being asked, what each
     answer costs. No bare IDs — an ID may appear, but the sentence must work without it.
   - `RECOMMEND:` — always present, always a concrete answer. (A = recommended is the
     chat convention; here the recommendation is written out.)
   - `ANSWER:` — blank line for RH.
2. **ACTIONS** — things only RH can physically do (dashboard clicks, test sends,
   signatures), each with context and a `DONE? :` line.
3. **ASSIGNED — no answer needed** — work already routed to sessions, listed so RH sees
   it exists without being asked anything.
4. **PARKED BY YOUR RULING** — decided items awaiting their moment, so he sees them
   without re-deciding.
5. **FINISHED** — items closed since the last refresh. **Items never vanish; they move
   here.** An item silently dropped is an item nobody is holding.

Rules:
- Every open decision appears in every refresh, not only the ones that moved.
- A new decision arising mid-work gets **appended to the current sheet** and mentioned
  in one chat line ("added X to the sheet") — never asked only in chat.
- Anything with a deadline names the date in its heading.

## Mode 2 — RH says "answers are in the file" (or saves and says "updated")

1. Read the sheet; treat every filled `ANSWER:`/`DONE?:` as RH's ruling, verbatim —
   including side-remarks inside an answer (a correction embedded in "yes, close,
   however..." is a NEW work item; extract it, route it, and say so).
2. **Execute every answer** — file the issue, send the work order, run the amendment
   ritual, whatever the answer implies. An answer consumed but not acted on is worse
   than one never asked.
3. Rewrite the sheet to LEAD with an execution-status block: each answer → what it
   caused → CLOSED / DONE-pending-build / routed-to-whom. Keep RH's original answers
   visible below.
4. If an answer is ambiguous, execute everything unambiguous first, then put the one
   clarifying question back in the sheet, not in a chat volley.

## Mode 3 — `/open-items plain`: the English briefing

A separate register for orientation rather than answering. Three sections:
- **THINGS ONLY YOU CAN DO** — numbered, each with what it means and whether it's
  blocked (and by what).
- **THINGS THE SESSIONS ARE BUILDING** — one short paragraph per thread, in merge
  order, "nothing needed from you" stated explicitly.
- **THE BIG PICTURE** — the ordered path from here to the deadline, numbered.
Close with **FINISHED TODAY** so progress is visible, not just debt.
Register rules: no unexplained IDs, no vendor jargon without a gloss, every item says
who is holding it. This is a briefing — it contains no ANSWER: lines.

## Cross-references

- `dronemapper-launch` — the authority chain and the "How to report to RH" grouping
  this skill implements; launch-scope answers executed from the sheet still go through
  that skill's amendment ritual and three-surface mirror.
- `coordinating-parallel-sessions` — coordinator discipline item 5 ("your report is
  the human's only view") is the principle; this skill is its file-shaped instrument.
- `ux-triage` — UX observations RH logs get bucketed there; the resulting pre-launch
  items surface on this sheet as DECISIONS or ASSIGNED.
