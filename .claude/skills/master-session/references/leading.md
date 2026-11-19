# Leading from the plan

Section names in this file are SKILL.md's. Every script command here is run from this skill's folder in the full form `python -X utf8 -I scripts/<script> <arguments>`: `python -X utf8 -I scripts/lead.py --repo <owner/name> --areas <file>`, `python -X utf8 -I scripts/state.py <command>`. A bare `running add ...` or `frozen drop ...` is a `state.py` command.

## Reading the plan

- **The plan is the whole read.** `lead.py` prints the plan (groups in ranked order, quick wins, held, parked), then the LEAD list. For one issue's detail, read that issue (`gh issue view <n>`). Listing the backlog yourself (`gh issue list`) fills your context with what the script already ranked.
- **Area list.** `--areas` is the repo's area list, a JSON file; the repo's `CLAUDE.md` or `docs/agents/` names it. `--base` is the branch merges land on (default `master`).
- **No area list in the repo.** `lead.py` stops and says so. For that turn only, list the open issues (`gh issue list --state open --json number,title,labels`), show them grouped by triage state, propose the one step you would take first as the turn's question (triage for an unlabelled or `needs-triage` issue, build for `ready-for-agent`), and start nothing before RH's go. Tell RH the repo needs an area list.
- **Not in a repo.** Ask RH which repo, as the turn's question.
- **Side conversation.** `lead.py` refuses a session that is not the owner. To read the plan there, run `python -X utf8 -I scripts/planner.py` with the same `--repo` and `--areas`; it writes nothing.
- **A run that fails.** An unreadable area list or snapshot, or a `gh` failure, prints one line and records nothing. Fix what it names and run it again; a `gh` failure that stays is a tooling gap for RH.

## The LEAD list

Rows come in the plan's ranked order: focus groups, groups with a rung 1 or 2 issue, the quick-wins lane, then the rest. START NOW rows are `ready` in the queue; ASK RH rows are `needs-rh`, and the first one is the next question for RH (its full text: `state.py show`) once no session waits on him for a hard stop and the PR pile is not full (Ending a turn, What RH is asked next). The Stop hook holds you while a START NOW row is untouched.

| Row | Take it by | Then record |
|---|---|---|
| `build:<spec group>` | Check the implement gate yourself (`references/pocock-flow.md`). It holds: start one fresh implementation session for the group (Grilling route step 5), then send it `/mattpocock-skills:implement-spec <spec path>`. No ask to RH. | `running add <session> --group <group> --kind build --command "/mattpocock-skills:implement-spec <spec path>"`, then `running sent <session>` |
| the same, gate does not hold | Start nothing. Ask RH for the missing part (usually: approve the spec at `<path>`?). | `queue add build:<group> --state needs-rh --text "<the question>"` |
| `go:<group>` | Ask the row's question: the issues, the number of sessions, what gets re-checked. On his go: re-check (below), then start that many sessions, related issues together, then send each `/mattpocock-skills:tdd <its issues>` (a bug: `diagnosing-bugs`). The implement commands stay behind their gate: these issues have no grilled spec. | per session `running add <session> --group <group> --kind build --command "/mattpocock-skills:tdd <its issues>"`, then `running sent <session>` |
| the same, RH says no or not now | Start nothing. | `queue add go:<group> --state blocked --text "RH: <his words>"` |
| `win:#<n>`, START NOW (a ticket under a spec) | As `build:<spec group>`, for that one ticket: the command is `/mattpocock-skills:implement <ticket path>`. | as `build:<spec group>` |
| `win:#<n>`, ASK RH (standalone) | As `go:<group>`, for that one issue: one question, one session, the same re-check. Set aside the same way (`queue add win:#<n> --state blocked ...`). | as `go:<group>` |
| `held:#<n>` | Ask the row's question. Act on his answer on the issue itself: a comment quoting him, and the label change or close he chose. | nothing: the next `lead.py` run reads the issue |
| `grill:<group>` | Propose it with the other waiting grills as one question (Freeze and grills). Start the ones RH names, then send each `/mattpocock-skills:grill-with-docs`. | per grill `running add <session> --group <group> --kind grill --command "/mattpocock-skills:grill-with-docs"`, then `running sent <session>` |
| `wayfinder:<group>` | Ask whether to start it. On yes, start it, then send `/mattpocock-skills:wayfinder`. | `running add <session> --group <group> --kind wayfinder --command "/mattpocock-skills:wayfinder"`, then `running sent <session>` |
| `spec-check:<group>` | A grill's spec is published: check the row's issues against it (Freeze and grills, After the spec). | `frozen drop <group>` once the check is settled |
| `triage:<group>` | Start one triage session for the group, then send `/mattpocock-skills:triage`. One group at a time: the next triage row appears when this session is done. | `running add <session> --group <group> --kind triage --command "/mattpocock-skills:triage"`, then `running sent <session>` |

**Every start in this table is two messages** (Plan mode steps 4 and 5). The first is the pointer brief: the row's issues or spec path, constraints, done criteria, standing rules, and the instruction to reply "Received." and end the turn. The second, sent when that start turn ends, is the command the row names, alone, through peer-slash; it carries the work. Record the session with `--command` when you start it and run `running sent` once you confirmed the command ran. Your question to RH may say "Build #593?"; the brief says where #593 is and leaves the building to the command.

Before a start, `state.py room` says whether it fits the limits (Limits): a `build:` row, a quick win or a go waits while the PR pile is full, and no session starts at the cap. `lead.py` prints the same lines under its list, and above it, under COMMAND NOT SENT, each started session whose command is not confirmed run: send those first. A started session gets no time box by default; add `--deadline <time>` only when you gave it one (Peer protocol, Timer).

**Quick wins.** The lane holds single issues of size S on rung 2 or 3, found-in-use and newest first. A win is offered once, as its own row, and left out of its group's row. It is held, blocked or frozen exactly as it would be in its group: a held one stays a `held:` question, one in a frozen group waits for the grill.

After any of these, run `lead.py` again. Done when every START NOW row is taken and RH has the first ASK RH row as his one question.

## Freeze and grills

**Frozen.** `lead.py` freezes a group (the state file's `frozen` list, with the reason) and gives it no `build:` or `go:` row:

- `grill needed: #n`: an issue in the group carries `grill:needed`;
- `grill open: <session>`: a grill session is recorded as running in the group, or in another group that shares the grilled issue;
- `spec check: <spec>`: the grill's spec is published and the group's ready issues are not yet checked against it.

Start nothing in a frozen group: no build, no "tiny" fix, not on RH's "just build it" either. The freeze is per issue: an issue that sits in a frozen group is not offered through its other group's row or as a quick win. Tell him in one line what freezes it and what unfreezes it. `unsorted` is never frozen: its issues share no area.

**Proposing.** The GRILLS line names the groups with a grill to propose, the one that unfreezes the most ready issues first and then by group rank, then the open ones. Ask one question that lists them in that order with each group's issues; your pick is the first. RH may name one, several or none. Each one he names: start a grilling session (Driving the Pocock flow, Grilling route) and record it as the `grill:` row above says. One he declines or leaves out: `queue add grill:<group> --state blocked --text "RH: <his words>"`, and bring it back (`queue drop grill:<group>`) when one of his grills ends, so the next proposal lists it again.

**One grill per group.** `state.py` refuses a second `running add ... --kind grill` in a group with one open. Do not record it under another group or kind. Tell RH the first grill is open there and that the second comes after its spec is checked; two specs written side by side in one group can contradict each other.

**While grills are open.** RH answers each grill in its own session. You keep leading: unfrozen groups build up to the limits, and every turn still ends with your own next question for him (the next ASK RH row), not with "waiting for your grills".

**After the spec.** When a grilling session reports its spec written (Grilling route step 3):

1. Record it, in this order: `frozen add <group> --reason "spec check: <spec issue or path>"` first, while the grill is still recorded as running. It puts the same spec check on every group that grill froze (a grilled issue can sit in several) and prints their names. Then, when the session is done with its tickets, `running drop <session>`. Run `lead.py`.
2. Each frozen group gets its own `spec-check:<group>` row, yours to take now; steps 2 to 4 run per group. Give exactly the issues it names, with the spec, to one read-only subagent (Models and effort, verification). It answers per issue `unchanged`, or `changed` with how: contradicts the spec, replaced by it, or partly covered.
3. All unchanged: `frozen drop <group>`, run `lead.py`; the group's ready work is offered again.
4. Some changed: ask RH one question naming each changed issue with how it changed; your pick is back to `needs-triage`. Record `queue add spec-check:<group> --state needs-rh --text "<the question>"`. Change no label before he answers. On his word, per issue he names: set `needs-triage` with a comment quoting him and the spec; leave alone the ones he keeps. Then `frozen drop <group>` and run `lead.py`.

If the row says nothing is ready to check, drop the freeze. If the grilled issue still carries `grill:needed` after its spec is published, the group stays frozen as `grill needed`: have the grilling session remove the label.

## Re-check at build time

The overnight check stands when nothing merged into the group's files and no spec was published in its area since the issue's checked commit. `lead.py` works that out; the `go:` row says `checks still stand` or `re-check #a #b first`.

- **Checks still stand:** start on RH's go with no re-check.
- **Re-check:** after his go and before the start, give only the named issues to one read-only subagent (Models and effort, verification). Ask per issue: is it still true against the code on the base branch, is it already done, did a later spec replace it? It answers `still true`, `done`, `partly done` or `replaced by #<n>`, with the file or issue it read.
- **Still true:** start it with the group.
- **Anything else:** leave that issue out of the start and put it to RH as one held question; the rest of the group starts.

## What waits without a question

The WAITING line counts what is nobody's step now:

- **No Verdict yet:** ready issues the overnight check has not reached. They wait for it; they are not questions and not started.
- **`ready-for-human`:** RH's own work. Show it when he asks.
- **Set aside:** rows you marked `blocked`. `queue drop <id>` brings one back at the next run.

## What `lead.py` keeps

It rewrites the plan's rows (`build:`, `go:`, `win:`, `held:`, `grill:`, `wayfinder:`, `triage:`, `spec-check:`) and the `go` and `frozen` lists on every run. It keeps a `spec check:` freeze until you drop it, every row you added under another id, and any plan row whose state you changed, exactly as you set it. A group with a row in `running` gets no build, go or triage row, so record a session's end (`running drop <session>`) before the run that should offer the group again.
