---
name: timesheet
description: Manage Deltek Vantagepoint timesheets — record time from natural language and enter it into the browser. Use this skill whenever the user mentions timesheets, logging hours, recording time, entering time, filling out a timesheet, tracking hours for the week, or anything related to time entry for work projects. Also use when the user describes what they worked on and wants it captured for their timesheet.
---

# Timesheet Skill

This skill has two modes that work together:

1. **Record** — Parse natural language descriptions of work into structured time entries, saved to a weekly file
2. **Enter** — Read the weekly file and enter the data into Deltek Vantagepoint via Chrome MCP browser automation

These modes are modular. Recording can happen without entering, and entering reads from the recorded file. Each week gets its own file.

---

## Key Paths

All paths are hardcoded so this skill works from any conversation:

- **Base directory**: `C:\Users\rharbach\OneDrive - Stahly Engineering\Claude_Code_Timesheets_Deltek`
- **Project CSV** (source of truth for known projects): `{base}/timesheet_projects.csv`
- **Weekly time files**: `{base}/timesheets/YYYY-MM-DD.json` where the date is the **Saturday ending date** of the week
- **Operational reference** (Deltek browser automation details): read `references/deltek-guide.md` in this skill's directory when entering time

Create the `timesheets/` subdirectory if it doesn't exist.

---

## Core Rules

These apply to both modes:

1. **All arithmetic must be done programmatically** — use `python3 -c` or a script for any calculation (hours splitting, totals, subtraction). Never do mental math.
2. **Ryan is salaried** — all hours go in REGULAR, never OVERTIME.
3. **Ryan is a surveyor** — if there's only one survey-related phase/task for a project, use it without asking.
4. **Every entry requires a comment** — no exceptions.
5. **Never assume phase or task** unless previously established or there's only one survey option.
6. **Use as few keywords as possible** in all searches and lookups.
7. **Daily totals.** Start/stop times ("7:30 to 6:00") set that day's total. Mon–Fri with no times default to **8 h**. Sat/Sun default to 0 unless evidence or Ryan says otherwise; holidays go to 0000-00300. Work Ryan mentions later comes **out of** the day's total (subtract it from the main task), unless he says "in addition", "on top of" or a variant, in which case it adds and the total grows. "Set Thursday to 10" always wins.
8. **Enter what you can before asking** — if some entries map cleanly to existing rows and others are blocked on a question (unknown project number, ambiguous phase, etc.), enter the unblocked ones first via `enter-timesheet.js`, then ask Ryan about the blocked ones. Never pause the whole timesheet to wait on one question. Mark the blocked entries' `status` as `pending` and the entered ones as `entered`, so the next pass only touches what's left.

---

## Mode 1: Record Time

**When to use**: The user describes work they did in natural language. They might say things like "I worked 8 hours on 8th Ave Monday doing Virtual Surveyor processing" or "subtract 1.5 hours from Thursday for an IT meeting."

### Required files to read before starting:
1. **Read `{base}/timesheet_projects.csv`** — this is the project lookup table. You need it to match user descriptions to project numbers.
2. **Read the weekly file** `{base}/timesheets/YYYY-MM-DD.json` if it exists — to see what's already been recorded this week.

### Step 1: Determine the week

Get the current date via `date +%Y-%m-%d`. Ask the user which week if ambiguous — users often fill in the previous week, not the current one. Calculate the Saturday ending date for that week (weeks run Sunday through Saturday).

### Step 2: Load or create the weekly file

Check if `timesheets/YYYY-MM-DD.json` exists. If it does, load it. If not, create a new one with this structure:

```json
{
  "week_ending": "2026-04-18",
  "week_start": "2026-04-12",
  "entries": [],
  "recorded_at": "2026-04-19T10:30:00"
}
```

### Step 3: Parse the user's input

Turn natural language into structured entries. For each piece of work described:

1. **Identify the project** — look it up in `timesheet_projects.csv` by name or keyword match. If not found:
   - Ask the user: "I can't find that project in the CSV. Do you know the project number, or should I look it up when entering the timesheet?"
   - If the user provides a number, use it and add to CSV for future reference
   - If unknown, record it with `"project_number": "LOOKUP_NEEDED"` and `"project_search": "keyword"` so the Enter mode knows to search for it

2. **Calculate hours programmatically** — if the user says "subtract 1.5 hours from Thursday's 8th Ave and add to IT", run `python3 -c "print(14 - 1.5)"` to get the new value. When the user says "subtract," that means pull hours from one existing entry and create/add to another.

3. **Resolve phase and task** — use known mappings first (see Common Mappings below). If unknown, record `"phase": "LOOKUP_NEEDED"` — it will be resolved during entry.

4. **Write the comment** — frame for managers, not for diary purposes.

   **Audience:** project comments print on client **invoices**, so they must read polished: client deliverable work in professional terms. Recast R&D, learning, company-improvement or rework time as the project work it served (✗ "R&D on processing method" → ✓ "Photogrammetric processing and QA"). Staff names and tool names are fine. Overhead (0000-xxxxx) comments can be plain. Comment source order: Ryan's words, then his email text, then session evidence. Never mention AI/Claude.

   **Include:** the specific work or deliverable (e.g. "Topographic field survey on 8th Ave NW", "Survey drafting and data processing", "Fergus Electric proposal preparation"), and any external coordination that's project-relevant ("coordination with Melanie and HDR", "meeting with Matt Pool").

   **Exclude:**
   - Time-of-day or scheduling details ("9-6:30 minus 1 hr break", "evening session 8:30 PM - 12:15 AM"). The hours field captures duration; the time of day is irrelevant to a manager.
   - Personal/process narration ("I worked on", "spent time"). State the work directly.
   - Conversational asides or filler.

   **Voice:** noun-phrase or past-tense, project-first. Examples:
   - ✓ "Field preparation for 8th Ave NW topographic survey"
   - ✓ "Delivered 8th Ave NW survey to client"
   - ✗ "Survey drafting (9-6:30 minus 1 hr break, plus evening 8:30 PM - 12:15 AM)" — schedule details
   - ✗ "Did some drafting" — vague, not project-anchored

### Step 4: Write entries to the weekly file

Each entry in the `entries` array looks like:

```json
{
  "project_number": "3733-00226",
  "project_name": "Great Falls: 8th Ave NW - 11th-14th St",
  "task_name": "Survey Proposals",
  "phase": "0001",
  "task": "",
  "day": "Thu",
  "hours": 12.5,
  "comment": "Virtual Surveyor processing",
  "status": "pending"
}
```

Valid days: `Sun`, `Mon`, `Tue`, `Wed`, `Thu`, `Fri`, `Sat`

If an entry already exists for the same project+phase+task+day, **update it** (replace hours and append to comment) rather than creating a duplicate.

If the user says to modify an existing entry (reduce hours, change comment), update the existing entry in-place.

**Evening / "after work" additions:** When Ryan reports late additions like *"on Monday I worked 1.5 hrs on Douglas after work"* or *"this evening I spent another 2 hrs on 8th Ave"*, those hours **roll into that day's existing entry for the same project**, not a separate row. A timesheet cell holds one value per project+phase+task+day, so consolidate hours and concatenate comments. Daily totals will increase to reflect the additional time (this is one of the few cases where a previously-locked daily total is meant to grow — Ryan is explicitly extending the day).

### Step 5: Confirm with the user

After parsing, show a summary table of what was recorded:

```
Day  | Project              | Hours | Comment
-----|----------------------|-------|--------
Mon  | General Overhead/IT  | 8.0   | Transported Puget machines...
Tue  | General Overhead/IT  | 7.0   | Puget machine setup...
```

### Common Project/Task Mappings

These are known shortcuts — use them without asking:

| Shorthand | Project | Phase | Task | Default Comment |
|-----------|---------|-------|------|-----------------|
| IT | 0000-00001 General Overhead | 0006 | 6.04 | (describe work) |
| PTO / Personal Time / medical or personal appointment | 0000-00200 Personal Time | — | — | PTO |
| Holiday | 0000-00300 Holiday | — | — | (name of holiday) |
| Staff Meeting / scheduling meeting | 0000-00001 General Overhead | 0006 | 6.01 | (describe meeting) |
| Vehicle maintenance (oil change, etc.) / UAV equipment troubleshooting / total station setup / similar equipment work | 0000-00001 General Overhead | 0006 | 6.06 | (describe equipment task) |
| Category Development / R&D / innovation discussion / remote sensing update meeting | 0000-00005 R&D/Innovation | 0006 | 6.02 | (describe R&D topic) |
| DroneMapper AI development / Imperfect Data Handling work | 0000-00029 Overhead: DroneMapper AI | 0006 | — | (describe dev work) |
| Leadership / weekly survey leadership meeting | 0000-00010 Leadership/Management | 0006 | — | (describe leadership work) |
| Fergus Electric proposal / Great Falls Marketing & Proposals survey work | 0000-00826 Sales Admin, Proposals & Term Client OH | 0006 | 6.07 | (describe proposal) |
| Recruiting / offer letters / intern outreach | 0000-00003 Human Resources | 0006 | 6.001 Recruitment | (describe) |
| CE credits / MARLS / conference PDH paperwork | 0000-00007 Education and Learning | 0006 | 6.02 External education programs | (describe) |

DroneMapper AI's live Deltek row is phase **0007 Continuous Improvement** (no task), not 0006.

### Filling the week (Ryan's rules, agreed 2026-11-10)

Ryan invokes this skill so you do the **legwork**: fill every day to its total (Rule 7) from evidence, then present the whole proposed week once for review. Don't ask gap-by-gap.
- **Weekly per-project estimates** ("Taylor's ~5 h for the week") are targets. Spread them over the days the evidence supports; report any leftover.
- Evidence tied clearly to a project goes into the week marked **(from evidence)**. Evidence you can't tie to a project gets listed separately for Ryan to place.
- Time left with no evidence goes to that day's main project, marked **(no evidence)**.
- Evening/weekend DroneMapper/Agisoft coding stays off by default. Show its evidence hours once per week and ask.

### Field days: task split and units (agreed 2026-11-16)

Every field day gets a task split and units, both shown with the hours for Ryan's OK.

**Task split.** Look up the project's phases/tasks (CSV notes, or the live Deltek row dump). "Conventional" means non-UAV. If the project has a separate flight/UAV/aerial task (e.g. Toole 1.03 Control/Flight), propose splitting the day between it and the conventional task (e.g. 1.04 Conv. Pickup). If it has only one survey task, the whole day goes there.

**Units**, per field day:

| Work that day | Units |
|---|---|
| UAV flight | `GPSDY` 1 (base) + `UAVDY` 1 |
| Conventional | `TSDAY` 1 for total station, or `GPSDY` 1 for GPS rover; ask which |
| Every field day | round-trip crew mileage, unit `58` "Mileage Rate 2026 - Survey Crew", miles as quantity, route in the comment |

A rover day and a flight day together: ask whether that is 1 or 2 `GPSDY`.

Record units in the weekly file's `entries` like this:
```json
{"kind": "units", "project_number": "2071-07D26", "task_name": "Control/Flight", "phase": "0001", "task": "1.03",
 "unit": "UAVDY", "unit_name": "Drone daily", "qty": 1, "day": "Wed", "comment": "Drone for photogrammetry flight", "status": "pending"}
```

### Phase/Task Numbering

`3.01` means Phase 3 (`0003`), Task 01. The number before the decimal is the phase, after is the task. So if the user says "put it on 3.01" that tells you both the phase and task.

---

### Gathering evidence (every run, in this order)

1. **Calendar:** Teams meetings from the Outlook calendar (`outlook_list_events`). These are fixed time blocks; place them first.
2. **Sent mail:** `scripts/sent_mail_week.py` (Outlook COM). It's slow, about 2 min, so run it in the background.
3. **Chrome history:** work sites only; ignore personal browsing. Read the History SQLite file from a copy (Chrome locks the original).
4. **Claude sessions:** `scripts/session_activity.py` gives active windows per project per day from JSONL *message timestamps*. File mtimes are useless because syncs stamp them all the same. Resumed sessions span several days, so bucket by message time, not session start. Scratch-workspace sessions need their first prompt read to identify the project.
5. **Project folders:** file mtimes in `P:\<client>\-<job>\` (e.g. `_AI\STATE.md`, flight plans, control files) show what was produced. Files others downloaded show up too (record research on Toole CH wasn't Ryan's), so treat these as weaker evidence.
6. **Received mail:** last, for context only.

Then, optionally:
- **Let Ryan estimate:** publish an Artifact table of sent emails (number, time, to, subject, a collapsible body with quoted history and signature stripped, an hours input, a comments box, Copy output as `n: hrs | comment`). He fills it in and pastes it back. Also read artifact comments (ArtifactComments `read`).
- **Refine comments with subagents:** give each one the session dirs and entries for a project group, analysis only, returning JSON `[{project, day, comment}]`. Pass them the invoice-comment rule. Subagents also catch mis-attributed work (e.g. a "flight plan" session that was really a different project).

---

## Mode 2: Enter Time into Deltek

**When to use**: the user says "enter my timesheet", "push my hours to Deltek" or similar.

Scripts live in `scripts/` and run with `dev-browser --connect --timeout <s> run <script>` from that folder. They exchange files with dev-browser's temp dir via `writeFile`/`readFile`. When a step fails, or before writing a new script, read `references/deltek-automation.md`: it holds Chrome setup, the lessons from real runs, the DOM map and the Chrome MCP fallback.

1. **Connect.** `curl -s http://127.0.0.1:9222/json/version` must return JSON. Otherwise launch the debug Chrome; it runs beside Ryan's normal Chrome, so leave that open: `Start-Process "C:\Users\rharbach\AppData\Local\Google\Chrome\Application\chrome.exe" -ArgumentList "--remote-debugging-port=9222","--remote-allow-origins=*","--user-data-dir=C:\Users\rharbach\.chrome-debug-profile","<timesheet URL>"`. Get the Deltek tab's real ID from `browser.listPages()` and pass that ID to `browser.getPage()`; a name-only string opens a blank tab. If the page shows `User ID  Password`, stop until Ryan logs in. Done when the page text shows `Timesheet Status:`.
2. **Open the week.** `page.goto("https://seaeng.deltekfirst.com/SeaEng/app/#!Timekeeper/view/0/0/00133%7C{Saturday YYYY-MM-DD}%7C00/presentation")`, wait 7 s. If the status is `Missing`, run `copy-previous.js`. Done when the grid 0 row dump is non-empty.
3. **Prepare `entries.json`.** `{entries:[...]}` from the weekly file. Set each `task_name` to the exact Deltek task text from the row dump (e.g. "Information Technology (IT)"; for a row with no task, its phase name, e.g. "Site Survey", "Continuous Improvement"). Add `row_marker` (e.g. "6.07") where a task name repeats across phases. Consolidate: one entry per project+task+day, hours summed, comments joined.
4. **Preflight.** `preflight.js` returns `{allPresent, missing}`. Add missing rows with `add-line-v2.js` (`add2.json`: `[{"s":"<full project number>","phase":"<phase name>","task":"<task name>"}]`); trust its reload-based `allAdded`. Each distinct survey proposal under 0000-00826 gets its own row (Copy via the row's Options menu, then address it with `row_index`). Done when preflight reports `allPresent: true`.
5. **Enter.** `enter-timesheet.js` (timeout 400+, about 15 s per cell). It skips entries already `entered`, so re-run it on failures; for `row_not_found` go back to step 4.
6. **Verify.** `grid-dump.js`: the grid-5 daily totals equal the weekly file's per-day sums. Then `verify-timesheet.js` re-opens every cell for hours and comment; re-verify a failed cell alone before treating it as real (row pinning causes false failures). Done when every cell matches.
7. **Units.** Enter every `"kind": "units"` entry. Click the **Units** toggle (top right, beside Hours). Units rows are separate from hours rows: add missing ones with +Add Line, which shows Unit Table / Unit / Unit Name columns. Then fill the cells with the same popup flow as hours (quantity in `regHrs`'s place, comment in `#commentEntry`). No script covers this yet, so adapt `enter-timesheet.js` inline. Done when a Units-view dump shows every unit quantity on its day.
8. **Record.** Set `status: "entered"` on each entered entry in the weekly file. Submit belongs to Ryan: it asks for his password, which he types himself.

### Sync from Deltek

When Ryan has edited or submitted in Deltek himself (he says so, or the status is `Submitted`/`Approved`), read the week in both the Hours and Units views and rewrite the weekly file's rows, hours and unit quantities to match. Deltek wins. Keep the file's comments unless a cell's comment is re-read from its popup. Run this before any new entry on that week.

---

## Updating the Project CSV

When a new project is encountered and confirmed by the user, add it to `timesheet_projects.csv` so future recordings can find it. The CSV has three columns: `Project Number`, `Project Name`, `Notes`.

---

## Weekly File Lifecycle

1. **Created** when user first records time for a new week
2. **Updated** as user adds/modifies entries throughout the week  
3. **Entries marked "entered"** after being pushed to Deltek
4. **Kept as a record** — don't delete old weekly files, they serve as a log
