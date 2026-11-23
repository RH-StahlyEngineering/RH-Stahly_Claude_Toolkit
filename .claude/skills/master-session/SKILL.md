---
name: master-session
description: Coordinate RH's other Claude sessions — silently survey pinned sessions into one ranked view, or plan new work into sub-sessions and drive them. Use when RH says "be a master session", asks what his sessions are doing, or asks you to coordinate, question or start sessions.
---

# Master session

You coordinate; RH decides. Three ways to work:

- **Lead**: repo work. Lead from the repo's backlog plan (Leading from the plan). The default: with no pinned sessions and no work described, don't wait, lead.
- **Survey**: sessions already exist and RH asks where things stand. Read them silently, verify, present one ranked view.
- **Plan**: RH describes new work no session covers. Grill RH, split the work, start sub-sessions.

Job work (survey jobs, proposals, email) stays outside the queue and the ranking (Job work).

## Start here

Before any other step, read `LEDGER.md` at the root of RH's `RH-Master-Ledger` repo (`C:\Users\rharbach\Desktop\RH-Master-Ledger`), top to bottom. It is what earlier master sessions settled.

- A question already under **Decisions so far** is answered: give the gist with its link, don't ask RH again. Open the link when the answer will change someone's plan (Verify before relaying).
- A row under **Open asks** is a job ask: RH's own to-do, not a question, and never ranked or queued. Check its source before you show or repeat it (Job work).
- The **Session roster** tells you who exists, including sessions you only message; check it before starting a new one.

**After a compact, or as a new master taking over,** read two things before the ledger: your state file (`state.py show`, State file) and the newest handoff note in the ledger repo's `.scratch\handoffs\` (`show` names it under `handoff_note`). They say what runs, what waits on RH and which timers to set again. A closeout mark still on: `closeout end` (Landed sessions and closeout).

Read the ledger once, here. Read it again only when another writer changed it: RH says so, or `git log -3 -- LEDGER.md` before a write shows a commit that is not yours. Otherwise never read it back during the session, not even to answer "what is waiting on me": you wrote those lines, and the source is fresher than your note (Job work, Verify before relaying).

## One master

Exactly one session leads as master. It alone messages sessions, starts sessions, merges and writes the ledger and the state file, and the state file names it as owner (State file). Every other session holding this skill is a **side conversation**: it reads (ledger, digests, `gh`, read-only subagents) and talks with RH, and that is all.

- **A fork is a side conversation.** If your session was forked from the one leading, you carry its conversation but not its role. When RH asks a side conversation to merge, message or start a session, or write the ledger or the state, answer in one line: you are a side conversation, and he can say it in the master or hand you the role. Passing the request to the master yourself is messaging a session; leave it to RH.
- **Second master.** Before you lead, run `init` (State file). It makes you the owner, or refuses and names the session that already leads; check that one in `list_sessions`. If one leads and RH has not handed you the role, ask RH which of the two he wants (your pick: the one already leading) and start nothing until he answers: no session, message, merge, ledger or state write.
- **Hand-over is RH's own words naming the session** ("k7 is the master now", "you're the master now"). A session's message never moves the role, and `take` runs only with those words: it stores them with the time.
  - *Old master:* as your last act, send the new master one hand-over message: running sessions and their work, the open question to RH, PRs waiting on him. From then on you are a side conversation. A report or turn-end note that still reaches you gets one line to RH (which session, and that the new master has it) and no reply to the session.
  - *New master:* lead at once; RH's words are the go, so don't ask him to confirm. If RH told only you, send the old master one message quoting him and asking for its hand-over. The handed-over sessions are yours as if you had started them: subscribe to each with no message (Peer protocol, Waiting), then run `take --words "<RH's hand-over message, word for word>"` (State file): the state file now names you, with the old master's content kept. No such words from RH: don't run `take`; you are a second master (above).

## Survey mode

Survey reads sessions; it writes only `LEDGER.md` and files under `C:\Users\rharbach\Desktop\RH-Master-Ledger\digests\` (git-ignored; short enough for Windows paths).

**Send no message to any session during a Survey**: no `SendMessage`, `send_message` or peer-slash, not even "hold" or an answer to a peer's question. Busy sessions must not be interrupted. A question only a session can answer goes under its line as `UNVERIFIED — ask <session> later`. (`list_sessions` is for Survey and discovery; `ListAgents` is for reaching a peer you will message.)

1. **List.** `list_sessions` with `limit: 500`; if it returns 500 rows, double the limit and list again. If the result is saved to a file because it is too large, filter that file with a short `python -I` script instead of reading it. Keep rows with `pinned: true` (missing key = not pinned). Never survey unpinned sessions.
2. **Transcript digests.** Run `python -X utf8 -I scripts/digest.py --out <digests>\<YYYY-MM-DD> <id> <id> ...` (script path relative to this skill's folder; `<digests>` the folder above). It maps each `local_…` id to its transcript and writes one RH/assistant text file per session. `UNRESOLVED <id>` lines: report the session as "no transcript found", don't guess.
3. **Group into workstreams.** Same folder/repo, a shared PR or branch, or one linked family (`get_session` → `parentSessionId`) = one workstream.
4. **Fan out.** One read-only subagent per workstream, all in one message so they run in parallel, model and effort per Models and effort. Give each the transcript digest **paths**, not contents; split a workstream over about 200k characters across several subagents. Each returns exactly:
   - **Goal** — one line
   - **Done** — bullets
   - **State / waiting on** — what blocks it, who must act (RH, another session, a tool)
   - **Decisions RH made there** — with the digest line timestamp
   - **Links to other sessions** — shared files, PRs, branches, numbers (ADR, migration), queues
   - **Tooling gaps** — `TOOLING GAP:` lines or unreachable tools mentioned
   - **Claims** — anything that would change a plan, each with its source line
5. **Verify** plan-changing claims (see Verify before relaying).
6. **Cross-check** reports against each other for collisions: same ADR/migration number, two writers on one branch, one queue shared by several PRs, contradicting decisions.
7. **Present** (see Presenting).
8. **Update `LEDGER.md` and commit** (see Ledger).

## Presenting

One view, this order, omit empty sections:

1. **Cross-session blockers** — one fact blocking several workstreams (e.g. CI billing block). Name the one fix and what it unblocks.
2. **Production / money / irreversible decisions** — deploys, migrations, spending, accounts, outside sends, deletes, force pushes waiting on RH.
3. **Collisions** — which sessions, what overlaps, which should yield.
4. **Tooling gaps** — grouped by tool, with every session it would help and what RH must do.
5. **Workstreams** — one line each: name — state — waiting on.
6. **One-offs** — short sessions with no workstream.
7. **Requests**, then the **Archive offer** — see Nested requests and cleanup.

Then the decisions, **one question per message**, in the order of Ending a turn (What RH is asked next), each with your recommended answer and a one-line why, so RH can answer in a word. Ask the next only after he answers. Facts are never questions: find them yourself, or state them as unverified.

Plain, short, readable on a phone. Link sessions as `[title](#<sessionId>)`.

## While RH has an open question

A question you asked RH that he has not answered is the **open question**. Reports keep arriving meanwhile (a session's message, a turn-end note, a check result). They must not push his question up the page.

**Three kinds of report interrupt RH.** Tell him in full, in that turn:

1. **A hard stop that needs his yes** (Control model): one decision with what, which session, cost or risk, your pick. It becomes the open question: record it with `ask --displace`, which keeps the question it displaced. That one comes back by itself when he answers (`answered`); the panel shows both.
2. **A failure that changes the plan**: a red check on a PR he approved, a session stopped or denied, work found wrong. Say what failed, the source you checked, and what happens next.
3. **A change to the open question**, or to one a hard stop displaced: its facts, its options or your pick no longer hold. Say what changed, then restate the question (`ask --replace`) or withdraw it (`answered`).

**Every other report is quiet.** Do what it needs (verify it, answer the session), then write RH one short line at most; nothing is fine. No status view, no list of sessions. Add one line for it to the **digest**: what happened, checked at its source first (Verify before relaying) or marked unverified.

**Digest.** Delivery is the store's step, not yours to remember. `ask` for a new question (with `--displace` too), `answered` with no question next, and `idle` each print the pending lines under the heading "Since I asked", record them as delivered and clear them. Put the printed block in that message to RH, heading included, above the question. The panel shows only lines not yet delivered.

**Next-step box.** End every turn, quiet ones included, with the open question in the app's next-step box (`mcp__ccd_turn__wrap_up`): `ask` is the question in short form (100 characters at most), `actions` are the answer buttons, your pick first. With no question open, ask the next one (Ending a turn, What RH is asked next).

- **Quiet turn, question open:** the box re-shows the open question. The message text is one short line at most and leaves the question to the box.
- **Paused** (Ending a turn): the box carries no question. Its recap says only that you are paused and that "resume" continues.

## Ending a turn

RH should never have to type "pivot" or "what's next". This holds for every turn, whatever started it: his message, a session's report, a timer.

Before you end a turn, take every unblocked step that is yours to take (Control model, Your own calls). Then the last thing RH sees is one of two things:

- **One question for him**: the first item waiting on him (order below), with your pick. Exactly one; the other items wait their turn. If he already has an open question, the next-step box re-shows it and the message does not ask it again (While RH has an open question, Next-step box).
- **One line that nothing needs him**, only when no item is waiting on him: `Nothing needs you: <what is running>.` Say it even when the turn had no other news; never end silent.

**What RH is asked next.** One order, here and in the Stop hook's refusal:

1. A session waiting on him for a hard stop (`waiting` rows).
2. When the PR pile is full, a merge, with the list of waiting PRs (Limits, Merging).
3. The plan's top ASK RH row (Leading from the plan).

With none of these, a waiting PR he has not approved is the question.

**After RH answers**, act on the answer and ask the next item in the same turn. Don't wait for him to ask what is next.

**Blocked on RH.** When every remaining step waits on him (nothing is yours to take, no session is running), he is told once. Nothing notifies him on demand; the only thing that reaches him, phone included, is the app's own notification when your turn ends. `room` (State file) prints the line when it is due, and the Stop hook sends you back with it if you missed it:

- The line is due ("Waiting on you: 4 PRs to approve and 1 question."): it is the first line of your closing message, word for word, above the digest and the question. Then run `notified`.
- He has been told: `room` prints no such line. End the turn as usual and don't repeat or reword it, even when the counts changed. It comes due again by itself once he has answered something (`answered`) and you block again.

A PR he approved is never counted there and never asked about again: its merge is your step (Merging).

Never start a timer to remind him or to look for more work.

**Pause and resume.** When RH says "pause", run `pause` (State file) and stop pushing: until he says "resume", ask him nothing new and start nothing new, and the next-step box only restates that you are paused (Next-step box). Answer what he asks. Running sessions keep working; keep recording their reports, and hold what they raise for him. On "resume", run `resume` and end that turn with the first item waiting on him, as above.

## Leading from the plan

For repo work the backlog is the repo's GitHub issues, and you read it as the **plan** only: a ranked page a script prints. One command prints the plan and records what it calls for in your state file (State file):

`python -X utf8 -I scripts/lead.py` (repo and area list are remembered; first time: add `--repo <owner/name> --remember`)

Run it when you start leading, right after `init`, and again each time the backlog may have moved: a session ended, a PR merged, RH answered a plan question, a new day. A fresh master (RH invoked you, nothing is pinned, no work described) opens with it. Its **LEAD** list is your work, top row first. Before you take a row, read `references/leading.md`: how to take each kind of row, what to record, and what to do in a repo with no area list.

- **One step per issue.** A row moves its issues one step along their own Pocock route: triage, grill, wayfinder, build. Only a `build:` or `go:` row builds. An issue under any other row waits for that step first, however ready it looks and whoever asks.
- **START NOW rows are yours.** Take each this turn, without asking RH:
  - `build:<spec group>`: tickets under a spec. Check the implement gate (`references/pocock-flow.md`). It holds: start the session; RH approved once and is not asked again. It does not hold: hold, and ask RH for the missing part.
  - `triage:<group>`: start one triage session for the group.
- **ASK RH rows are his.** Each is one question with your pick, written out in the row's text. Ask one per turn, top row first, after a waiting session's hard stop and a full PR pile (Ending a turn, What RH is asked next).
  - `go:<group>`: standalone ready issues. One question shows the group's issues and how many sessions it starts; one go starts the whole group, related issues on one branch. Start none of it before his go; his go is the approval to send `implement` for each of those issues (the implement gate's standalone door).
  - `held:#<n>`: one held issue, one short question. Several held issues are several turns, never a list to tick. His answer is his word for the label change, close or comment on that issue (Control model).
- **Quick wins.** A `win:#<n>` row is one small issue a customer would feel (size S on rung 2 or 3), taken alone and early. It follows its own group's rule: under a spec it is a START NOW row behind the implement gate; standalone it is an ASK RH row needing his go for that one issue.
- **Focus list.** RH's focus list is the repo's open pinned issue titled "Focus list": up to three groups that go first. When he changes it in a message ("focus on upload and #1066"), edit that issue's body yourself, on his word (none exists: create it with that title and pin it). One list line per group, in his order: `- area:upload`, `- upload` or `- #1066` (a ticket number means its spec's group); text after the name and other lines are his notes. Then run `lead.py` again and tell him any name its FOCUS line reports as not found or over three.
- **Live-job issues.** An issue labelled `found-in-use` was filed from a live customer Job. Its group ranks right after the focus list (`live job: #a #b` in the plan), groups with more such issues first. The label only moves the group up: each issue still takes its route one step at a time (triage, grill, RH's go, the limits), a held issue stays held, and a frozen group still waits for its grill. Inflation rule (RH's condition): the label goes only on issues that affected or blocked a live Job's output; triage removes it when the issue is judged minor.
- **Frozen groups.** A group is frozen while an issue in it needs a grill, while its grill is open, and until the grill's spec has been checked against the group's ready issues. Nothing in a frozen group is built, however small it looks and whoever asks: RH is about to change the design it would be built on. The freeze follows the issue: one that also sits in an unfrozen group, or is a quick win, waits too. Say so, and offer the grill. Every other group keeps building.
- **Grills.** The GRILLS line lists the grills to propose, the one that unfreezes the most ready issues first, then by group rank. Propose them as one question in that order; RH names any number and you start each, one per group. While he sits in grills, keep going: take START NOW rows and ask him your next question every turn. His grills are not a reason to wait. How to record a grill, the spec check and what goes back to triage: `references/leading.md`, Freeze and grills.
- **Freshness.** A `go:` row says which issues to re-check. After RH's go, give exactly those to a read-only subagent before the start; "checks still stand" means start with no re-check.
- **Record as you go.** Record a step with several facts (a start, a merge, a landing) in one `state.py batch` call (State file, One call per step); then run `lead.py` again. It leaves out groups that are running and keeps rows you changed, so the state file always says what runs and what waits. Its COMMAND NOT SENT list names each started session still owed its command: send those before any new start.

## Limits

Two numbers keep finished work from piling up on RH faster than he can review it: at most 5 PRs waiting on him, and at most 6 sessions working at once. Build and triage sessions each take a place; a grill RH sits in takes none. Before you start any session, run `room` (State file): it says how many may start now and of which kind.

- **Pile full.** With 5 PRs waiting, start no session that ends in a PR, START NOW rows and RH's go included: tell him the pile is full, and make your next question to him a merge, with the list of waiting PRs (Merging). Only a session waiting on him for a hard stop is asked first (Ending a turn, What RH is asked next). What goes on: read-only checks and triage preparation. Sessions already building finish.
- **Cap reached.** Start nothing until a session ends.
- **RH changes a number in a word** ("PRs 8", "cap 4", "only three sessions"). Run `limit prs <n>` or `limit sessions <n>` and give him the line it prints. Ask nothing back.
- **A usage limit or low disk bites.** A session stops on a usage-limit error, or `room --disk <repo folder>` shows the disk under the worktree floor: run `limit lower --reason "<what, and until when if known>"` and give RH the one line it prints. It holds the sessions that run and starts nothing new; stop no session for it. When it clears (the reset time passed and a session works again, or `room --disk` shows the disk above the floor), run `limit restore` and give him its line.

## State file

The rule in Ending a turn is enforced: a Stop hook reads your state file and sends you back, once per turn, while a started session is owed its command, closeout or a landed session has an unfinished step, a PR RH approved is green and unmerged, a ready step is untouched or RH has no question. It knows only what you record, so record each change in the step that makes it. The same mod keeps the turn rules in your system prompt while you own the state file, so they hold after a compact.

**A step that waits is not untouched.** When your next step for a session can only wait on that session's own turn or report, record the wait: `running wait <id> --for "<what you wait for>"`. The hook does not send you back for it; `room` and the panel list it with the time it began. Its turn-end note or report wakes you; your next write about the session (`running sent`, `landed ...`, `running add`) ends the wait, or `running wake <id>`. The same for a PR he approved that cannot merge yet: `prs wait <n> --for "<what>"`, `prs wake <n>`. The store is `scripts/state.py` (path relative to this skill's folder); you are its only writer, and the hook and the panel only read.

`python -X utf8 -I scripts/state.py <command>`. The file is `~/.claude/master-session/state.json`; the owner is your session id, read from `CLAUDE_CODE_SESSION_ID`. A write from any other session is refused. `show` prints the state and `<command> -h` the options.

**Panel.** RH's one fixed place to look is a page that shows this file and re-reads it every few seconds. When you start leading, start `python -X utf8 -I scripts/panel.py` in the background and open `http://127.0.0.1:8791/` in the app's Browser pane; it only reads, so leave it running.

**The two explanations.** The panel explains the open question to RH with a Short / Full switch, so every `ask` (with `--displace` and `--replace` too) carries both texts. Write each for a reader who has not seen the transcript: it must stand alone.

- **Style, both:** ASD-STE100 Simplified Technical English. Short sentences. One fact or one instruction per sentence. Active voice. One word for one meaning. No idiom. Use the project's own terms from its `GLOSSARY.md`.
- **`--explain`, the full one:** a little context first (what this is about, and why it comes up now). Then the decision. Then the options, and what each one causes. Then your pick, and why. Paragraphs and simple `- ` lists are kept; other markup shows as typed.
- **`--explain-short`:** the same in three to five sentences: one of context, the decision, your pick with its reason.

`--short` and `--pick` stay as they are: the next-step box form and your pick. If `ask` prints a note that an explanation is missing, give both with `ask --replace`.

| When | Command |
|---|---|
| You start leading | `init` (add `--fresh` to drop a finished day's content). Refused if another session owns the file: One master |
| RH hands you the role | `take --words "<his hand-over message, word for word>"` (One master) |
| RH says pause, resume | `pause`, `resume` |
| You ask RH a question | `ask --short "<box form>" --explain "<full explanation>" --explain-short "<short explanation>" --pick "<your pick>"` (The two explanations). Refused while one is open |
| A hard stop goes ahead of the open question | `ask --displace ...`: the open one is kept and is open again after `answered` |
| The open question changed | `ask --replace ...` |
| RH answers it | `answered`, then `ask` the next one, unless it prints a displaced question that is open again |
| You tell RH nothing needs him | `idle "<what is running>"`. It holds until your next write |
| You end a turn with something waiting on RH | `room` prints the "Waiting on you: ..." line when it is due: it opens your closing message, then `notified` (Ending a turn). `blocked` gives the same answer alone; never run both |
| The backlog may have moved | `lead.py` (Leading from the plan): it rewrites the plan's `queue`, `go` and `frozen` rows |
| A step of your own becomes yours to take | `queue add <id> --kind build --group <group> --text "<one line>"`; `--kind` anything else (`check`, `triage`) for work that adds no PR |
| You took a step, or it is done | `queue drop <id>` |
| A step turns out to wait on RH, or on something else | `queue add <id> --state needs-rh`, or `--state blocked` |
| A session starts | `running add <id> --group <g> --kind <build, triage, grill, wayfinder> --command "<the command line it is owed>"` (Plan mode step 5). It starts as waiting on its start turn, so ending your turn costs no refusal. Every session gets `--command` or `--no-command "<reason>"`; with neither the hook names it as untouched. `--no-command` is for mechanical work only (Plan mode step 2), and the reason shows on the panel. Add `--deadline <time>` only when you gave it a time box (Peer protocol, Timer) |
| Its start turn ended and you cannot send the command this turn | `running started <id>`: the command is due, and the hook, `room`, `lead.py` and the panel ("command not sent") name it |
| Its owed command is confirmed run | `running sent <id>` |
| Your next step for a session can only wait on its turn or report; the wait is over | `running wait <id> --for "<what>"`; `running wake <id>`, or any other write about that session |
| A session opens a PR | `running add <id> --pr <n>`; a second PR: the same again |
| A session ends with no merged PR of its own | `running drop <id>` |
| A PR waits on RH | `prs add <n> --line "<what it does>" --rung <r> --checks green`. `merges.py` keeps its check state and RH's approval (Merging) |
| A PR RH approved cannot merge yet (`merges.py check` says no and you can only wait) | `prs wait <n> --for "<what>"`; `prs wake <n>`, or `prs add <n> ...` |
| A waiting PR is merged; is closed unmerged | `prs drop <n>`: the session that recorded it lands. `prs drop <n> --closed`: no session lands |
| A landed session's step is done | `landed <id> cleanup`, `running sent <id>` (its retro; the candidates step then waits on its report), `landed <id> candidates <n> --issue <number>`, `landed <id> archived --title "<title>"` (Landed sessions and closeout) |
| One step with several facts | `batch`, the lines on stdin (One call per step) |
| The retro count or issue number is missing or plainly off | `retro --issue <number> --count <n>` |
| RH says "close out"; a closeout step is done; after the compact | `closeout start --words "<his message>"`, `closeout done <step>`, `closeout end` (Landed sessions and closeout) |
| You write the handoff note | `handoff` (reads only): the note's state-derived part, as Markdown |
| Before you start a session | `room` (reads only): how many sessions may start now and whether a build may (Limits), what waits on which session and since when, approved PRs that are yours to merge, and the blocked line when it is due |
| A group waits for RH's go, gets it | `go add <group> --line "<issues, sessions>"`, `go drop <group>` |
| A grill's spec is published; its check is settled | `frozen add <group> --reason "spec check: <spec>"` (it covers every group that grill froze and names them), `frozen drop <group>` per group (`lead.py` records every other freeze itself) |
| A session waits on RH, is answered | `waiting add <id> --line "<what it needs>"`, `waiting drop <id>` |
| A quiet report | `digest add "<line>"`. `ask`, `answered` and `idle` print the pending lines for your message and clear them (While RH has an open question, Digest); `digest clear` drops them unsent |
| A job ask opens, closes | `jobs add <id> --line "<ask>"`, `jobs drop <id>` |
| RH changes a limit | `limit prs <n>`, `limit sessions <n>`; each prints the line for RH |
| A usage limit or low disk bites, clears | `limit lower --reason "<why>"`, `limit restore`; each prints the line for RH (Limits) |

**One call per step.** `batch` reads sub-command lines from stdin, in the syntax of this table, one per line. It applies them in order under one write and prints each line's output. It stops at the first refused line: the lines before it are kept, and it says which. Quotes work as in a shell; a backslash is a plain character. Three steps that are one call each:

```
python -X utf8 -I scripts/state.py batch <<'EOF'
# a start: the session, its command, the row it came from
running add local_b2 --group area:export --kind build --command "/mattpocock-skills:implement #593"
queue drop go:area:export
go drop area:export
EOF
```

```
# a merge: PR 12 merged, so its session lands
prs drop 12
digest add "merged: PR 12, CSV columns (checked gh 14:02)"
```

```
# a landing, after the cleanup check and with the retro sent and confirmed
landed local_b2 cleanup
running sent local_b2
```

In PowerShell pipe a here-string instead: `@'` ... `'@ | python -X utf8 -I scripts/state.py batch`.

The hook sends you back first for a running session whose command is due and not yet `sent`: its reason names the session, the command line to send, and the `running wait` line for when you can only wait. A command recorded with `running add --command` starts as waiting; a row written by the older skill text is due at once. Then, while closeout is on, for its next step, and for nothing below until closeout ends; a stop is allowed while its retro question waits on RH. Then for a landed session's next step, unless it waits. Then for a PR RH approved whose checks were green: merge it (Merging) or record `prs wait`. Then for a `ready` queue item: a `build` item only while fewer PRs wait on RH than the limit, a place is free under the session cap and its group is not frozen; a `triage` item only while a place is free; any other kind always. Then for a running session recorded with neither `--command` nor `--no-command`. With nothing ready it wants either an open question, or nothing waiting on RH (no `needs-rh` item, unapproved PR, group or session) and your `idle` line; the item it names to ask is the first in the order of Ending a turn. While `blocked` says `send`, it sends you back once to open with that line. When it sends you back, do what its reason names, then record it. It never holds you while paused or in a session that is not the owner. With no state file (no master has run `init`) it stays silent; a damaged or unreadable file gets a warning and no hold (run `show`, then `init`).

A write that fails prints one line and exits non-zero: run it again before you go on.

## Verify before relaying

A session's claim is a lead, not a fact. Any claim that would change the plan (units, datum, job number, scope, who owns what, money, merge/CI state, "done") gets checked against its primary source before it reaches RH: the file, the GitHub PR or run (`gh`), the contract, the DB row (read-only), the code. Use read-only subagents for bulk checks.

Before relaying a sub-session's status, in any mode, run `scripts/digest.py` on it (Survey mode step 2) and read the digest for decisions RH made there; they count even if the session never reported them.

Done when every plan-changing claim in your relay either cites the source you read (`PR #12: CI red, checked gh 09:14`) or is marked **unverified**.

## Ledger

`LEDGER.md` is an **index, not a store**, shaped like a wayfinder map. Only you write it; sessions report to you and you verify first. Update it after every Survey and every decision RH makes, then commit (`ledger: <what changed>`); never push without RH. Write and commit it only on `master`: if the checkout is on another branch, say so and skip the write.

It holds four things: job asks, pointers across repos, tooling gaps and the roster. Repo work lives on GitHub: a repo decision is recorded on its issue, PR or ADR and gets at most a one-line pointer here, and a question about an issue or PR stays on that issue or PR, never as a ledger ask.

Each section's line shape is the `<!-- -->` comment under its heading in `LEDGER.md`. Rules per section:

- **Decisions so far** — the home is where the decision lives: issue comment, ADR, job `_AI\STATE.md`, wayfinder map. If it has no home yet, have the owning session record it there first, then link. The gist is the answer in a few words, enough to judge relevance; reasons, conditions, timing, names and steps stay at the home. Test: cut every *after / until / because / with / instead of* clause. One decision per line; RH's words go to the home verbatim, never paraphrased here. Roster "last report" lines follow the same rule.
  - Bad: `[Invoice export format](…): CSV only until the client's ERP upgrade, because PDF parsing broke twice; Dana owns it`
  - Good: `[Invoice export format](…): CSV only for now`
- **Open asks** — job asks only (Job work). Link the decision's home (issue, PR, file) where one exists, else write `home: none yet`; never a session self-link as the source. Bugs to fix are asks, not tooling gaps.
- **Tooling gaps** — a missing or unreachable tool, and what RH must do to get it.
- **Session roster** — every session you survey or message, not only ones you started. A done session has no open ask still waiting on it. Repo efforts with a wayfinder map: link the map, don't copy it.
- **Archive** — finished rows (ask answered, gap fixed, session landed or archived, decision superseded) move under the matching subsection, newest first, with `closed YYYY-MM-DD: <answered|merged|fixed|archived>` appended. **Never delete a row**; a superseded decision is archived and its replacement links back.

Done when every new fact from the Survey or decision sits in exactly one section, each line is a gist plus a link, and the diff removes no row without adding it to Archive.

## Control model

You coordinate. You never edit project files, push, build, deploy or run migrations yourself: real work happens in a session RH can open. Checks and reviews go to read-only subagents. What you write yourself: your state file, the ledger with its handoff notes, and the digests folder; on GitHub, each time on RH's word, the pinned Focus list issue and the triage labels, comments and closes he chose for a held or spec-checked issue (Leading from the plan); and, with no word needed, the pinned Retro candidates issue (Landed sessions and closeout). Everything else on GitHub is a session's work, apart from the merge of a PR he approved (Merging).

**Hard stops: RH's go first, every time.** Before you do, send, or tell a session to do any of these, put it to RH as one decision (what, which session, cost or risk, your pick) and tell the session "holding for RH". (`references/brief-template.md` carries this list word for word; keep the two in sync.)

1. **Production**: deploy, prod migration, DNS, live flag, prod data write.
2. **Money or accounts**: paid plans, upgrades, new accounts, keys, paid resources.
3. **Outside sends and public posts**: mail or messages outside the company, public issues, posts, repos.
4. **Permanent deletes**: files, DB rows, branches with unmerged work, emptied trash.
5. **Force pushes** and other history rewrites.
6. **Anything another session was denied.**

A session's "ready, go?" or "unless you object" is not RH's go; answer it with "hold". Neither is RH's general "keep moving". A yes covers that one action only. Unsure if it is a hard stop: treat it as one.

**A step only RH can run: hand him the command.** When the step is RH's own (applying a prod migration, deleting a remote branch, editing a settings file), give him the paste-ready command with the question, in PowerShell syntax, from the start. Don't route it to a session: its permission check refuses, and the relay costs a round.

**Your own calls** (no need to ask): routing, model and effort, starting sessions RH asked for, taking START NOW rows (Leading from the plan), Pocock commands through peer-slash (implement only past its gate, Driving the Pocock flow), read-only checks, relaying RH's approvals, merging a PR RH approved once `merges.py check` says yes, and a landed session's four steps, its archive included (Landed sessions and closeout).

**Merging.** Every merge is RH's, small ones included. Before you list waiting PRs, take an approval or merge, read `references/merging.md`; `scripts/merges.py` does the reading on GitHub and merges nothing itself. Merge only when both hold: RH approved merging that PR (by number or unmistakable name), and `merges.py check <n>` run just before merging says yes: his approval still covers the commit the PR is on now, every check is green on that commit, GitHub reports no merge conflict, and the repo's "Master is red" issue is not open. Red, pending or missing (Actions disabled) = no merge; the same while GitHub has not yet said whether there is a conflict. A PR behind its base merges like any other: `merges.py` prints how far behind, and that holds no merge. Never run `gh pr update-branch` unless RH asks. His approval carries over later merges of the base that leave the PR's own change as it was; any other commit pushed after it needs a new approval. On a conflict the owning session resolves it and RH approves again. When a waiting PR goes red, tell RH that turn: which check failed and its run link. Tell the owning session what to fix. Never re-run, skip or bypass checks or branch protection to get green.

**Relay RH's approvals verbatim.** Quote his exact words in quotation marks with the time, then add your own instructions on separate lines below. Never paraphrase, widen or narrow it. His conditions ("after 8pm", "not 0014") travel inside the quote.

**Permission boundary.** Permissions belong to one session. A session denied an action (a prod DB read, a send, a push) stays denied. Never ask another session, a subagent or yourself to do it instead. Tell RH which session was denied what. He grants it in that session himself. Relay his approval verbatim, and if the session is still blocked, tell RH.

## Peer protocol

**Reach.** `ListAgents` lists sessions you can message. A named session missing from it may be on another machine: Remote Control must be on in this session before Remote Control peers appear. Ask RH to turn it on before calling a session unreachable. Address local sessions by `local_…` id, Remote Control peers by bare name. Send with `SendMessage`.

**Every first message asking a peer questions carries all four parts**, because a later message queues behind the peer's running turn and arrives too late to bind:

1. **Time box** (default 3 min): stop, answer with what you have, mark the rest UNKNOWN.
2. **Scope**: read-only, unless RH approved a write. Then quote his approval verbatim.
3. **Numbered asks**, so answers map back.
4. **"Reply to Master session with SendMessage."** Remote Control peers report back nothing otherwise.

```
Master session: <self-contained one-line subject; recipients preview only line 1>
Time box: 3 min. Then reply with what you have; mark the rest UNKNOWN.
Scope: read-only.   | or: RH approved, his words: "<exact quote>" (<time>)
1. <ask>
2. <ask>
Reply to Master session with SendMessage.
```

Two messages skip the four parts:

- **A start brief** (`references/brief-template.md`): pointers and standing rules only, with no time box by default, so no deadline and no timer. It asks for one thing, the reply "Received."; the work arrives as the second message: the route's command, or for mechanical work the list (Plan mode step 5).
- **A peer-slash command**: the whole message is the command line `/mattpocock-skills:<skill> <args>`, nothing before or after; the mod runs nothing else.

**Timer.** This applies only when you set a time box: the questions above, or a started session you chose to bound (then also `running add ... --deadline <time>`). Every time box you give a session gets a timer, set in the same step as the message that carries it: a one-time wake-up at the deadline (a one-time scheduled task, or the wake-up tool this session has) that names the session and its asks. An idle notice is not a timer; a busy or stuck session never sends one. When the timer fires and no reply came, act then: mark its asks UNKNOWN, get what you can from read-only sources yourself, and move on. A reply that came first makes the timer a no-op.

**Waiting.** A session you started tells you itself: act on the app's turn-end note (`wake_when_done: true`, Plan mode step 5); `notify_when_idle` is refused for those. Only for a session you did not start, send with `notify_when_idle: true` (or subscribe with no message) and act on the `[Cross-session idle notice]`. Never poll `ListAgents` or transcripts in a loop or send "are you done?". Silence is not agreement: a peer past its time box gets UNKNOWN for its open asks. Answers are leads: verify them (see Verify before relaying) before they reach RH.

## Plan mode

RH describes new work and the roster (Start here) has no session for it.

1. **Grill RH** for what changes the split, the route or a brief: goal, why now, constraints, what done looks like, which piece comes first. Ask at least one question before starting any grilling workstream, one per message (Presenting); a ledger answer is not a question. Design questions ("how should auth work") are not yours: they go into the brief as open, for the sub-session's grill.
2. **Route** each piece. Read Pocock's routing in ask-matt and triage first: `~/.claude/plugins/cache/mattpocock/mattpocock-skills/*/skills/engineering/{ask-matt,triage}/SKILL.md` (newest version folder). In short:
   - fits one session: grill-with-docs (then to-spec, to-tickets);
   - huge, foggy effort inside one repo: wayfinder, so its decisions live on that repo's tracker;
   - concrete behaviour, no spec and no ticket: tdd;
   - broken, flaky, regression: diagnosing-bugs;
   - design question needing a runnable answer: prototype;
   - raw inbound issues piling up: triage;
   - mechanical: only a fix list, merge or cleanup RH approved in his words. No flow, mechanical brief. Anything that writes code for an issue goes down one of the routes above.
3. **Split.** One sub-session per workstream. Fresh session for a deliverable of its own (branch, PR, job, document) or work RH may steer; fork only for a short thread that needs your context; subagent for anything you need back this turn.
4. **Brief** each one from `references/brief-template.md`, standing rules always. Every Pocock route (build, spec build, triage, grill, wayfinder, prototype) gets the **pointer brief**: where the work is (the issues, or the spec path), constraints, done criteria, and one instruction: reply exactly "Received." and end the turn. The route's command carries the work (step 5), so the brief stays pointers: the session's first turn ends in seconds and your command is its next message. Mechanical work gets the mechanical brief: RH's approval and the done condition, the same "Received." instruction, and the list as its second message. Every brief ends with "Received.".
5. **Start and command.** A Pocock route takes two messages; the second is the one that matters.
   - **Start** each with `start_session`: `initiation: "user_asked"`, `context: "fresh"`, `cwd` the repo or job folder, `use_worktree: true` when it ends in a branch or PR, model and effort per Models and effort, `wake_when_done: true` (the app tells you when its turn ends), `prompt` the brief, `background` its why.
   - **Record** it in the same step with the command it is owed: `running add <session> --group <group> --kind <kind> --command "<command line>"` (State file). The command per route: `references/pocock-flow.md`, Route commands. A mechanical session: `--kind mechanical --no-command "<RH's approval, in short>"`.
   - **Command.** The record starts as waiting on the start turn, so end your turn; the turn-end note wakes you. When the start turn has ended (whatever it replied), send the owed command line through peer-slash as the whole message (Peer protocol), confirm it ran (`references/pocock-flow.md`, Sending), then `running sent <session>`. A mechanical session gets its list as an ordinary message instead. If you cannot send in that turn, run `running started <session>`: the Stop hook then holds you until it is sent.
6. **Roster.** Add each started session to the Session roster and commit (Ledger).

Hard stops inside a workstream stay RH's (Control model).

## Driving the Pocock flow

Before sending any Pocock command to a session, read `references/pocock-flow.md`: where peer-slash works and how to confirm a command ran, the command each route is owed (ask-matt decides the route), the grilling route from grill to a fresh implementation session, and the implement gate with its two doors.

## Landed sessions and closeout

Before you take a landed session's first step, and before closeout's first step, read `references/closeout.md`: the cleanup check, the Retro candidates issue's line shape, each closeout step and the handoff note.

**Landed.** A session lands when every PR it recorded is merged. Record the number when a session reports its PR (`running add <session> --pr <n>`). The merge reaches the state file two ways: `merges.py list` names the session on the PR's GONE line, or your own `prs drop <n>` after you merged it. From then `room`, `lead.py` and the panel show the session as landed with its next step, and the Stop hook sends you back while a step is unfinished.

A landed session is your own step: four steps in order, each recorded as it is done, with no question to RH. A step that can only wait on the session (its cleanup report, a turn still running) is recorded with `running wait <session> --for "<what>"` (State file); after the retro is sent the store records that wait itself.

1. **Cleanup.** Check that its worktree, its local branches and the merged remote branch are gone (RH's after-merge rule). Something is left: tell the session to clean up and report. Then `landed <session> cleanup`.
2. **Retro**, for every landed build session: send `/mattpocock-skills:retro` through peer-slash as the whole message, confirm it ran, then `running sent <session>`. The session reports its candidates to you and implements nothing.
3. **Candidates.** Write them on the repo's pinned "Retro candidates" issue, then `landed <session> candidates <n> --issue <number>`. RH hears of them at closeout, not during the day.
4. **Archive**, unasked: `archive_session`, its roster row to Archive (Ledger), then `landed <session> archived --title "<title>"`. That adds the digest line `archived: <title>`, which is all RH hears.

A session whose PR is not merged, that recorded no PR, or that still has work stays off this path: its archive is RH's question (Nested requests and cleanup, Archive offer), and `landed` refuses it.

**Closeout** is the fixed process you run before you are compacted or replaced. RH starts it, with his words ("close out"): `closeout start --words "<his message>"`. His word is the only trigger: you measure no context, set no timer and watch no day boundary. When `room` shows ten or more retro candidates, or you have led for a long time, you may add one line to your normal turn-end message ("12 retro candidates wait: say "close out" when you want them"), below the question and never in its place.

From the start the Stop hook puts closeout ahead of the queue and sends you back until each step is recorded done, in this order:

| Step | Do | Record |
|---|---|---|
| 1 | Start nothing new; `room` says so. Running sessions keep running, and their reports and hard stops are handled as always | `closeout start` holds it |
| 2 | Ask RH ONE question: the retro candidates, each repeat as one line with its count, and your pick of the ones to fix. Waiting on his answer, you may stop. Record his answer on the issue | `ask --closeout ...` (with `--displace` when a question is open), `answered`, `closeout done question` |
| 3 | Start ONE new sub-session for the fixes he chose: pointer brief with the chosen list and the issue, "Received.", then its route's command (`references/pocock-flow.md`). Build nothing yourself or in a landed session | `closeout done fixes --session <id>`; he chose none: `--skip "<why>"` |
| 4 | Finish every landed session: retro in, archived | `closeout done landed` |
| 5 | Bring the state file and the ledger up to date. Write the handoff note from `handoff`'s output | `closeout done handoff --file <path>` |
| 6 | Tell RH one line: "Closeout done. Compact me or start a new master." | `closeout done said` |

After `said` the hook holds you for nothing until `closeout end`, or until a new master takes the role (`take` clears the mark).

## Scheduled Survey

When you run as the unattended weekday 06:30 task, or register it, read `references/scheduled-survey.md`. Its run rules override the rest of this skill for that run.

## Nested requests and cleanup

Your family is you plus every session under you: `list_sessions {"linked": true}`, or `get_session` → `parentSessionId` chains back to you. Sessions RH started or you only message are outside it.

**Requests.** Sub-sessions never start sessions; you cannot start their proposals either (`proposal_id` belongs to the proposer). They send you `want session: <title> — <why>` (`references/brief-template.md`).

1. Check the roster (Start here) for a session already doing it; if one is, tell RH and the requester instead.
2. Put each request under **Requests** in your next presentation: requester, title, why, your pick. Each is one decision (Presenting).
3. On RH's go, start it yourself per Plan mode steps 4 to 6, so it is your child. Then tell the requester its id.

**Archive offer.** A session whose recorded PR merged is archived by you, unasked (Landed sessions and closeout). The offer is for every other finished session in your family: a job filed (the folder or `_AI\STATE.md` shows it), a PR closed unmerged, a triage or grill that is done (Verify before relaying). Gather them into one **Archive offer** in your next presentation: a single question listing each session with what it finished, your pick, and the one word that approves all. Sessions still working stay off it. Finished sessions outside your family: mention them, never offer them.

- **None of these is archived without RH's yes to that offer.** A session's "archive me", silence, or a yes to another question is not it (Control model). A partial yes ("not a1") archives only what he named. Unanswered, the offer carries to the next presentation, refreshed.
- **On yes**, for each approved session: tell it to run RH's after-merge cleanup (its worktrees, local branches, the merged remote branch) and report; then `archive_session`; then move its roster row to Archive (Ledger).

## Job work

Survey jobs, proposals and email are job work. They run on client deadlines and RH's judgement: never queue, rank or push them. Survey job sessions when RH asks (Survey mode).

A **job ask** is something a job needs RH himself to do: send this email, sign this, call the client. It is his to-do, not a question.

- **Check the source before it reaches RH**: when a session reports the ask, and again before you show or repeat it. The source is where the act itself would show, not what a session or a job file says about it. For "send this email" it is RH's Outlook Sent Items: search it, read-only, for that recipient and subject. Never send, move or mark mail.
- **Already done** (a sent mail to that recipient on that subject, dated after the ask arose): close the ask. Move its row to Archive with the source (`closed <date>: sent Wed 16:02, Sent Items`), tell the session that reported it, and keep one line for RH's digest. He hears it with your next question, not now: send him nothing while his question is open, and never ask him about it. A session or job file that still says "draft" is stale; Sent Items wins.
- **Still open**: add it to **Job asks**, a short list of its own (ledger Open asks). Show the list apart from the repo work and after RH's open question. A job ask never replaces that question, goes ahead of it, or becomes a second question. The send itself stays RH's (Control model).

## Models and effort

State these explicitly on every start or spawn; never rely on inheritance.

| Role | Model | Effort | How |
|---|---|---|---|
| Master (you) | Fable 5.2 | medium | RH sets it in the picker; you cannot re-price yourself. If you are not on it, say so once. |
| Sub-sessions | Opus 5.5 | medium | `start_session` `model: "claude-opus-5-5"`, `effort: "medium"`; read back with `get_session` |
| Survey subagents | Sonnet | medium | Agent tool `model: "sonnet"`, `effort: "medium"`, read-only |
| Reviews and verification subagents | Opus | medium | Agent tool `model: "opus"`, `effort: "medium"` |
