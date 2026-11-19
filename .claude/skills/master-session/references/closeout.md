# Landed sessions and closeout

Section names in this file are SKILL.md's. Every script command here is run from this skill's folder in the full form `python -X utf8 -I scripts/state.py <command>`; a bare `landed ...`, `closeout ...` or `handoff` is a `state.py` command. The store refuses a step out of order and names the step that comes first.

## A landed session's four steps

**How it lands.** Its PR numbers are on its running row (`running add <session> --pr <n>`, from its "PR opened: #n" line or your own `gh pr list --head <branch>`). When every one of them is merged it has landed: `merges.py list` records the merge and names the session on the GONE line, and so does `prs drop <n>` after your own merge. A PR closed unmerged is dropped with `prs drop <n> --closed` and lands nothing. A session with a second PR still open has not landed. A PR that merged before you recorded it on its session: `running add <session> --pr <n>`, then `prs drop <n>` once more.

**1. Cleanup.** Read-only checks, yours to run:

- `git -C <repo> worktree list`: its worktree is not listed;
- `git -C <repo> branch --list <branch>`: empty;
- `gh api repos/<owner>/<name>/branches/<branch>`: 404.

All gone: `landed <session> cleanup`. Something is left: tell the session, in one message, to remove what you name and report; end the turn, and check again on its turn-end note. Remove nothing yourself. A worktree or branch a ticket links to, or another session's, stays (RH's after-merge rule).

**2. Retro.** `cleanup` makes `/mattpocock-skills:retro` the session's owed command, shown as "command not sent" like a route command. Send it as the whole message, confirm it ran (`references/pocock-flow.md`, Sending), then `running sent <session>`. Only a build session gets a retro (`--kind build`, `diagnosing-bugs` runs included); any other landed session goes from cleanup to archive.

**3. Candidates.** The session reports its retro's candidates to you. Write each on the Retro candidates issue (below), then `landed <session> candidates <n> --issue <number>`, with `<n>` the candidates the retro reported, repeats included (0 when it found none; `--issue` is needed once). Implement none, tell no session to implement one, and ask RH nothing about them: they are his question at closeout.

**4. Archive.** `archive_session`, move the roster row to Archive (Ledger), then `landed <session> archived --title "<title>"`. The store drops the running row and adds the digest line `archived: <title>`; RH sees it under "Since I asked" with your next question. Then run `lead.py` again.

**The session is gone** (RH deleted it, it cannot be reached): `landed <session> archived --title "<title>" --skip "<why>"`. The digest line carries the reason.

## The Retro candidates issue

One open pinned issue per repo, titled "Retro candidates", like the Focus list issue. None exists: create it with that title and pin it. You write it without asking RH (Control model).

- **One line per candidate** in the body: `- <the change, in one line> (<kind>) ×<count>: <session title>, <date>`. Kind is the retro's own category: navigation, automated check, coding standard, steering file, tool economy, information access.
- **A repeat adds to the count.** The same change proposed again: raise `×<count>` on its line and append `; <session title>, <date>`. No second line.
- **The store keeps only the issue number and a count**: the candidates reported since RH last saw the list, repeats included. It feeds the one-line reminder and nothing else, so set it by hand only when it is plainly off (you took over with no count): `retro --issue <number> --count <n>`.

## Closeout, step by step

Start: `closeout start --words "<RH's message, word for word>"`. Run it only on his own words in this session; a session's suggestion, a full context or a long day is not one.

**1. Start nothing new.** `room` and `lead.py` say closeout is on and allow no start. START NOW rows, RH's go and grills wait for the next master. Running sessions keep running: answer their reports, send owed commands, put a hard stop to RH with `ask --displace` as always.

**2. Retro question.** Read the issue. Ask RH ONE question (`ask --closeout --short ... --explain ... --explain-short ... --pick ...`; add `--displace` when another question is open): the full explanation lists every open candidate as one line with its count, repeats first, and says which you would fix now and why. While it waits on him you may stop. On his answer: `answered`; add a comment on the issue quoting him with the time; move every line you asked about under a heading `## Decided <date>` marked `fix` or `no`, so the open list is empty; then `closeout done question` (the count goes back to 0). No open candidate: `closeout done question --skip "no candidates"`.

**3. Retro fixes.** One new sub-session for everything he chose, in the repo the fixes change: Plan mode steps 4 to 6, pointer brief (the chosen lines, the issue number, done criteria), "Received.", then the route's command per `references/pocock-flow.md`, Route commands; ask-matt decides the route. Record it like any start (`running add <session> --kind build --command "<line>"`, `running sent` once confirmed), then `closeout done fixes --session <session>`. It is the one start closeout makes. Its PR joins RH's pile like any other; hard stops stay his. He chose none: `closeout done fixes --skip "RH chose none"`.

**4. Landed sessions.** Take every landed session through its four steps (above); candidates that arrive now go on the issue for the next closeout. A landed session whose retro has not reported yet: end the turn and come back on its turn-end note. None left: `closeout done landed`.

**5. State, ledger, handoff note.**

- State file: every running session, waiting PR and waiting session is recorded as it is now. Check each running session's last state at its source (Verify before relaying).
- Ledger: roster and decisions current, committed.
- Handoff note: `C:\Users\rharbach\Desktop\RH-Master-Ledger\.scratch\handoffs\<YYYY-MM-DD>-<HHMM>.md`. Paste what `handoff` prints, then replace every `TO ADD` line with the fact, from the source and not from memory: each running session's last verified state with the time; every timer, monitor or scheduled task you set, with what it watches; RH's hand-over words if he named the next master, word for word. Commit it with the ledger (`ledger: closeout handoff`).
- Then `closeout done handoff --file <the note's path>`. The store keeps the path under `handoff_note`.

**6. Final line.** Your closing message is exactly: `Closeout done. Compact me or start a new master.` Then `closeout done said`. From here the Stop hook asks nothing of you.

## After the compact, or as the new master

Read `state.py show` and the note under `handoff_note` first (Start here). Set each timer in the note again, subscribe to the running sessions if you are a new master (One master), then `closeout end` (a new master's `take` clears the mark itself) and run `lead.py`.
