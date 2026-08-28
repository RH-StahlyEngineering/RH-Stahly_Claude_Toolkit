---
name: pm
description: Use when starting, resuming, or ending the DroneMapper coordinator (PM) session — /pm or /pm open after a clear, compaction, or new terminal; /pm closeout before ending a session or handing off. Also use whenever the coordinator cannot answer "who holds what right now" from memory, or before claiming any session, worktree, or launch state to RH.
---

# PM — prime the coordinator

A coordinator's method survives in skills; its **state** does not. This skill
reconstructs the state. (Baseline failure, observed in production 2026-08-28: a
coordinator fresh from /clear retains authority and method via `dronemapper-launch`
but loses the session roster, allocations, promises, and queue — and drops
undertakings silently, which is the exact failure the whole apparatus exists to
prevent.)

## The four reads, in order — never claim state before all four

1. **Goal** — `docs/launch/LAUNCH_PLAN.md` §1 (the 8 criteria + drop-dead date),
   via `git show origin/master:...`. The goal is why every other read matters.
2. **Checklist** — `origin/master:docs/launch/LAUNCH_CHECKLIST.md` (never the
   working tree). What is ticked, what is open, what was amended.
3. **RH's sheet** — `.claude/handoffs/OPEN-ITEMS-<latest date>.md`. What RH has
   been asked, answered, and is still holding. Governed by the `open-items` skill.
4. **The coordinator ledger** — `.claude/handoffs/PM-LEDGER.md`. Your half of the
   state: roster, assignments, allocations, promises, queue, trust map. The sheet
   is what RH holds; the ledger is what YOU hold.

Then: `git fetch origin` and `git worktree list` to reconcile the ledger against
reality — a commit or worktree you don't recognize is normal; read it before
building on it. Message any session the ledger marks IN-FLIGHT whose state you
need; never assume a stale entry is current.

## The ledger — maintain it as events happen, not at session end

`PM-LEDGER.md` sections (template below is the contract; keep every section,
even when empty):

- **ROSTER** — every live session: name, lane, current task, last-heard state.
- **QUEUE** — ordered merges/steps with the reason for the order.
- **ALLOCATIONS** — number blocks (migrations, fixtures), name claims, anything
  handed out that two sessions must not both use.
- **PROMISES** — every undertaking you have made that someone else relies on
  ("R1 brief carries X", "ping RH when Y"). An unrecorded promise is a dropped one.
- **PENDING FROM RH** — mirrors the sheet's open lines, one line each.
- **TRUST MAP** — key claims marked verified-by-me vs relayed, with date.
- **LESSONS BUFFER** — lessons awaiting their batch commit to `tasks/lessons.md`.

Update the ledger **in the same turn** as the event: a session briefed, a block
allocated, a promise made, a merge landed. A ledger updated "later" is a diary,
not an instrument. Compaction can strike at any turn; the ledger is what makes
that survivable.

## Modes — `/pm` (or `/pm open`) vs `/pm closeout`

**`/pm` / `/pm open`** — the four reads above, then reconcile, then **invoke
`coordinating-parallel-sessions`** (Skill tool) before briefing, redirecting, or
routing anything to any session. State without method is the mirror-image of the
baseline failure this skill fixes: a resumed coordinator holding a correct roster
but running briefs and routing from memory (observed 2026-08-28 — a full working
session of redirects before the method skill was loaded, and RH had to invoke it
himself). Its `references/this-setup.md` is also the pre-brief read for machine
reach and traps. Default mode.

**`/pm closeout`** — run before this coordinator session ends, hands off, or goes
quiet for the night. In order:

1. **Promises audit.** Walk the ledger's PROMISES: each is done (check it off with
   what closed it), still open (leave it, verify its trigger is stated), or newly
   discovered mid-audit (add it). An unchecked promise with no trigger is a drop
   waiting to happen — fix the entry, not the checkbox.
2. **Roster sweep.** For each session: still working (leave), done-and-merged
   (confirm its worktree/branch cleanup per `coordinating-parallel-sessions` — the
   worktree outlives the merge until its session confirms done), or silent past a
   report trigger (note it as OVERDUE with what it owes).
3. **Ledger refresh** — full rewrite with a new timestamp, so the next `/pm open`
   reads one coherent state, not a day of appends.
4. **Sheet refresh** via the `open-items` skill if any RH-facing line moved.
5. **Lessons buffer** — if it has grown past a handful of entries, commit the batch
   to `tasks/lessons.md` now rather than promising to; a buffer that survives two
   closeouts is a promise being broken slowly.
6. **One closing message to RH**: what's running unattended overnight (and who
   watches it), the first thing tomorrow's session should do, and the single
   sentence a fresh coordinator needs that the files can't carry. Keep it short —
   the files are the record; the message is the pointer.

Closeout does NOT delete anything, close terminals, or message workers "goodbye" —
sessions keep running; closeout is about the LEDGER being safe to resume from.

## Rules

- **Delegate depth to subagents, liberally** (RH instruction 2026-08-28 — the
  observed failure was the coordinator grepping a codebase itself mid-session).
  The coordinator's context is the fleet's only shared map; every file read and
  grep spent orienting yourself burns the context that holds the roster,
  promises, and rulings. Anything shaped "go find out X and report" — code recon
  before a ruling, locating a mechanism, verifying a claim across files,
  drafting a brief from sources — goes to a subagent (Explore for read-only
  sweeps, general-purpose for multi-step recon); you consume the conclusion.
  Keep in your own hands only: rulings, RH interaction, ledger writes, guarded
  actions (push/merge/send), and single-fact lookups whose address you already
  know.
- **Invoke skills you authored.** Authorship is not exemption; skills evolve and
  memory drifts. (Observed: the coordinator who wrote
  `coordinating-parallel-sessions` ran a day on remembered content.)
- The ledger records state, never method — method lives in
  `coordinating-parallel-sessions` (how to run sessions), `dronemapper-launch`
  (authority + scope), `open-items` (RH's interface).
- On resume, the ledger outranks your memory and the sheet outranks the ledger
  where they disagree about RH's rulings; `origin/master` outranks both about code.
- Replaces the retired `prime-agent-os` command (agent-os framework is retired).

## Ledger template

```markdown
# PM LEDGER — updated <timestamp> by <session>
## ROSTER
- <name> [<lane>] — <current task> — last heard <when>: <state>
## QUEUE
1. <step> — <why this order>
## ALLOCATIONS
- <what> → <who> (<date>)
## PROMISES
- [ ] <undertaking> — owed to <whom>, due <when/trigger>
## PENDING FROM RH
- <sheet line, one-liner>
## TRUST MAP
- <claim> — VERIFIED <date> / RELAYED from <who> <date>
## LESSONS BUFFER
- <one-line lesson> (<source>)
```
