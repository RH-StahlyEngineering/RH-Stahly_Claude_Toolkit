# Driving the Pocock flow

Section names in this file are SKILL.md's. You move each sub-session along its route (Plan mode step 2) by sending Pocock commands through peer-slash, on your own judgment (Control model), except `implement` and `implement-spec`, which wait for the gate below. The commands are `mattpocock-skills:<skill>` (the `/` form is the slash command); nothing else is reachable, so never send `/compact` or `/clear`.

## Sending

- **Where it works.** Proven only for local sessions you reach by `local_…` id, started after the peer-slash mod reached 0.3.4. Remote Control and cloud peers are unproven: ask RH to run the command there himself. A session opened before the mod update needs a restart by RH first.
- **When.** Only to an idle session: wait for its turn-end note (Peer protocol, Waiting). One command per message. A session you started is idle within seconds: its start brief asks only for "Received." (Plan mode step 4), and what it replied does not matter.
- **Shape.** The message is the command line only (Peer protocol).
- **Confirm it ran.** After the receiver's turn ends, check `list_events` or its turn-end note for a command row or the skill's first output. If the command arrived as plain text instead, tell RH which session needs a restart. Never ask the receiver to act as if the command ran, or to call the Skill tool for a manual-only skill. For a session's owed command (below), record the confirmation: `running sent <session>`.

## Route commands

Every session you start on a Pocock route is owed one command: the second message it gets, sent when its start turn ends. Record it at the start (`running add <session> ... --command "<line>"`); the Stop hook holds you until it is confirmed run.

| Route (`--kind`) | Owed command line |
|---|---|
| Standalone ready issues (`build`) | `/mattpocock-skills:tdd <issue refs>`; for a bug `/mattpocock-skills:diagnosing-bugs <issue ref>` |
| Tickets under a spec (`build`) | `/mattpocock-skills:implement-spec <spec path>`, or `/mattpocock-skills:implement <ticket path>` for one ticket. Only past the implement gate: until it holds, start no session |
| Triage (`triage`) | `/mattpocock-skills:triage` |
| Grill (`grill`) | `/mattpocock-skills:grill-with-docs` |
| Foggy effort (`wayfinder`) | `/mattpocock-skills:wayfinder` |
| Design question (`prototype`) | `/mattpocock-skills:prototype` |

## Grilling route

One session holds grill, spec and tickets:

1. Start turn ends: send its owed command, `/mattpocock-skills:grill-with-docs` (Route commands). RH answers the grill in that session.
2. Grill reported done: verify the decision homes it names exist (Verify before relaying), then send `/mattpocock-skills:to-spec` to the **same** session.
3. Spec reported written: send `/mattpocock-skills:to-tickets` to the same session, and ask RH one question: approve the spec at `<path>`? For a grill taken from the plan, also start the spec check (`references/leading.md`, Freeze and grills).
4. Tickets reported written: that session is done with this effort.
5. **Implementation in a fresh session.** Once the gate holds, start a new sub-session (Plan mode steps 4 and 5, `use_worktree: true`). Its pointer brief names the spec path, the tickets folder, the tracker, and the branch holding them (have the grilling session commit them first if they are not). Add it to the roster. When its start turn ends, send its owed command (Route commands): `implement-spec` for a ticket graph, `implement` for one ticket.

## The implement gate

Send `implement` or `implement-spec` only when all three hold, each checked by you, not taken from a session's report:

- the spec came out of a grill-with-docs that finished with RH answering;
- RH's own words approve that spec, read in the session's transcript or sent to you (quote them with the time);
- the tickets exist in the tracker.

A session's "shall I implement?" is not the gate: answer "hold". Missing any one: hold and ask RH for it. Once all three hold, sending is your call, not a second ask.

## Other commands

`code-review` when a branch needs a review outside an implement run (implement already reviews its own work), e.g. after a fix round, before you ask RH to approve a merge.
