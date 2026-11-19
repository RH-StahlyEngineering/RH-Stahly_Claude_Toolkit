# Sub-session brief template

The brief is the `prompt` of `start_session`; the why paragraph also goes in `background`. Pick one brief, then append the standing rules unchanged.

## Pointer brief (every Pocock route: build, spec build, triage, grill, wayfinder, prototype)

Pointers only: where the work is, its limits, what done is. The work itself arrives as the session's second message, the route's command (SKILL.md Plan mode step 5), and that command's own flow finds the design and the steps. So every line here points or limits; the one instruction is the last line. Quote RH where his words carry the intent.

```
Master session: <self-contained one-line subject>
Work: <the issue numbers, or the spec path with its tickets folder and branch; for new work with no issue, RH's goal and why in his words>
Constraints: <hard limits: repo, deadline, clients, hard stops that apply (see below)>
Decisions so far: <ledger gist + link to its home, one per line; "none">
Open for you to decide: <grill, wayfinder, prototype: the design questions left to this session; else omit>
Done looks like: <the checkable end, e.g. "PR open for #593 with green checks; report to Master">
First turn: reply exactly "Received." and end your turn. Read nothing and plan nothing yet. Your next message is a command; the work starts there.
```

Test before you send it: the brief names no file to change, no mechanism and no numbered step. A session that could start the work from the brief alone got too much.

## Mechanical brief (fix list, merge, cleanup)

Prescriptive, and the only brief that carries the work: no command follows it. RH's approval verbatim (SKILL.md Control model), the exact list, the steps, the done condition, what to skip and report.

```
Master session: <self-contained one-line subject>
Scope: RH approved, his words: "<exact quote>" (<time>)
1. <exact step>
2. <exact step>
Done: <checkable end state>. Anything off the list: stop and report it.
```

## Standing rules (append to every brief, unchanged)

The hard-stop list copies SKILL.md Control model word for word, because a sub-session never reads SKILL.md; keep the two in sync.

```
Rules for this session:
- Time box: none for the work itself. Report to Master at the end of each phase (grill, spec, tickets, fix) and whenever you are blocked.
- Report with SendMessage to Master session.
- Hard stops: before any of these, say "holding for RH" and report to Master; RH decides.
  1. Production: deploy, prod migration, DNS, live flag, prod data write.
  2. Money or accounts: paid plans, upgrades, new accounts, keys, paid resources.
  3. Outside sends and public posts: mail or messages outside the company, public issues, posts, repos.
  4. Permanent deletes: files, DB rows, branches with unmerged work, emptied trash.
  5. Force pushes and other history rewrites.
  6. Anything another session was denied.
- Parallel work: fork yourself only when the thread needs your context; otherwise use a subagent.
- New sessions: never start one or propose one with a card. Send Master one line: "want session: <title> — <why>". Master asks RH and starts it.
- Decisions RH makes with you directly: record them at their home (issue comment, ADR, STATE.md), then send Master one line: "RH decided: <gist> — <link>".
- Missing tools: whenever a CLI, MCP, plugin or connector would help but is unreachable, send Master: "TOOLING GAP: <tool> — would speed <task> — RH must <do what>".
```
