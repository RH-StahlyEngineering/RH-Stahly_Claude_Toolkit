# Driving the Pocock flow

Section names in this file are SKILL.md's. You move each sub-session along its route (Plan mode step 2) by sending Pocock commands through peer-slash, on your own judgment (Control model), except `implement` and `implement-spec`, which wait for the gate below. The commands are `mattpocock-skills:<skill>` (the `/` form is the slash command); nothing else is reachable, so never send `/compact` or `/clear`.

## Sending

- **Where it works.** Proven only for local sessions you reach by `local_…` id, started after the peer-slash mod reached 0.3.4. Remote Control and cloud peers are unproven: ask RH to run the command there himself. A session opened before the mod update needs a restart by RH first.
- **When.** Only to an idle session: wait for its turn-end note (Peer protocol, Waiting). One command per message. A session you started is idle within seconds: its start brief asks only for "Received." (Plan mode step 4), and what it replied does not matter.
- **Shape.** The message is the command line only (Peer protocol).
- **Confirm it ran.** After the receiver's turn ends, check `list_events` or its turn-end note for a command row or the skill's first output. If the command arrived as plain text instead, tell RH which session needs a restart. Never ask the receiver to act as if the command ran, or to call the Skill tool for a manual-only skill. For a session's owed command (below), record the confirmation: `running sent <session>`.

## Route commands

**ask-matt decides the route.** Before choosing a command, read Pocock's ask-matt (path: Plan mode step 2) and the SKILL.md of the skill you are about to send. The table is the short form with RH's gates added on top (the implement gate, hard stops); it re-decides nothing. Where it disagrees with ask-matt, follow ask-matt and tell RH the mismatch.

Every session you start on a Pocock route is owed one command: the second message it gets, sent when its start turn ends. Record it at the start (`running add <session> ... --command "<line>"`); the Stop hook holds you until it is confirmed run.

| Route (`--kind`) | Owed command line |
|---|---|
| Standalone `ready-for-agent` issue (`build`) | `/mattpocock-skills:implement #<issue>`, past the implement gate's standalone door. A bug that needs diagnosis first: `/mattpocock-skills:diagnosing-bugs #<issue>` |
| Tickets under a spec (`build`) | `/mattpocock-skills:implement-spec <spec path>`, or per ticket `/mattpocock-skills:implement <ticket>` (Spec builds, below). Past the gate's spec door: until it holds, start no session |
| Concrete behaviour with no spec and no ticket (`build`) | `/mattpocock-skills:tdd` |
| Triage (`triage`) | `/mattpocock-skills:triage`. Raw inbound issues only: tickets `to-tickets` wrote are already agent-ready and stay out of triage |
| Grill (`grill`) | `/mattpocock-skills:grill-with-docs` |
| Foggy effort (`wayfinder`) | `/mattpocock-skills:wayfinder`. Map reported clear: send `/mattpocock-skills:to-spec` to that session, then go on at Grilling route step 3. The map never goes straight to implement |
| Design question (`prototype`) | `/mattpocock-skills:prototype` |

**One `implement`, one session.** ask-matt starts every `implement` in a fresh context, working from its ticket; peer-slash cannot send `/clear`, so each issue or ticket gets its own new session, the next one started when the previous run has finished (its work committed, its turn ended). Issues that share a branch (the related issues of a `go:` row): start the next session in the previous one's worktree (`cwd` that folder, `use_worktree: false`), so the group still ends in one PR.

### Spec builds: one run or per ticket

Past the spec door, choose:

- **`implement-spec <spec path>`** (default): the whole spec in one session, on one integration branch, as one PR.
- **`implement <ticket>` per ticket**, when the tickets must land separately: the spec or a ticket says each ticket is its own PR; a production step or other hard stop sits between tickets (migration, deploy, live flag, spending); or RH said so. Blockers first, one session and one PR per ticket. A ticket starts only when its blocker's PR is open and that run has finished; independent tickets may run side by side under the session cap (Limits). Each PR joins RH's pile as its own approval.

The spec and tickets do not settle which: ask RH once for that spec (your pick: `implement-spec`) and record his answer (Ledger).

## Grilling route

One session holds grill, spec and tickets:

1. Start turn ends: send its owed command, `/mattpocock-skills:grill-with-docs` (Route commands). RH answers the grill in that session.
2. Grill reported done: verify the decision homes it names exist (Verify before relaying), then send `/mattpocock-skills:to-spec` to the **same** session.
3. Spec reported written: send `/mattpocock-skills:to-tickets` to the same session, and ask RH one question: approve the spec at `<path>`? For a grill taken from the plan, also start the spec check (`references/leading.md`, Freeze and grills).
4. Tickets reported written: that session is done with this effort.
5. **Implementation in a fresh session.** Once the gate holds, start a new sub-session (Plan mode steps 4 and 5, `use_worktree: true`). Its pointer brief names the spec path, the tickets folder, the tracker, and the branch holding them (have the grilling session commit them first if they are not). Add it to the roster. When its start turn ends, send its owed command: `implement-spec`, or the first ticket's `implement` (Route commands, Spec builds).

## The implement gate

`implement` and `implement-spec` go out through one of two doors. Check each condition yourself; a session's report is not a check.

**Spec door** (`implement-spec <spec path>`, or `implement <ticket>` per ticket). All three hold:

- the spec came out of a grill-with-docs that finished with RH answering;
- RH's own words approve that spec, read in the session's transcript or sent to you (quote them with the time);
- the tickets exist in the tracker.

**Standalone door** (`implement #<issue>`, an issue under no spec). All three hold:

- the issue is `ready-for-agent` on the tracker;
- the plan does not hold it: it sits in a `go:` or `win:` row, not under `held:`, WAITING or a frozen group;
- RH's own words gave the go on that issue or its group (quote them with the time). His go is the approval; no spec is needed.

A session's "shall I implement?" is not the gate: answer "hold". A condition missing: hold and ask RH for it. Once a door's conditions hold, sending is your call, not a second ask.

## Other commands

- **`code-review`** when a branch needs a review outside an implement run (implement already reviews its own work), e.g. after a fix round, before you ask RH to approve a merge.
- **`retro`** goes to every landed build session (`diagnosing-bugs` sessions included): after its PR merged and its cleanup is confirmed, before you archive it (SKILL.md Landed sessions and closeout). Send `/mattpocock-skills:retro` to that same session, since retro reads the session it runs in. Its candidates change the agent's environment (checks, coding standards, steering files): the session reports them to you and implements none, you write them on the Retro candidates issue, and RH picks at closeout (`references/closeout.md`).
