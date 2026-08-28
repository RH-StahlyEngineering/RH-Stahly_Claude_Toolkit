---
name: coordinating-parallel-sessions
description: Use when running work split across several concurrent Claude sessions on one repo — assigning lanes, briefing a session, allocating migration or fixture number blocks, resolving two sessions editing one file, deciding which machine work runs on, or routing a finding from one session to another that cannot see it. For the coordinator, not the workers. Distinct from superpowers:dispatching-parallel-agents, which covers subagents inside a single session.
---

# Coordinating Parallel Sessions

You are the coordinator. You hold breadth and no depth: the sessions know
their code and you do not. Your irreplaceable function is that **you are the
only one who can see all of them at once.**

This skill exists because on 2026-08-27 six sessions worked one repo and the
work went fine while the coordination did not. Every rule below has a dated
failure behind it.

**Local facts — machines, known traps, current allocations — are in
`references/this-setup.md`. Read it before briefing anyone.**

**If the work is the DroneMapper AI launch, `dronemapper-launch` holds its
authority chain, its frozen scope contract and its tick-evidence standard.
That skill decides *what* may be done; this one decides *how a fleet does it*.**

## The brief contract

The brief is the coordinator's main product. Almost every failure below traces
back to one that was missing, vague, or wrong.

**The mechanical nine** — put all of these in every brief:

1. **Identity and what else is running.** Who this session is, and which
   other sessions are active alongside it.
2. **The specific skills to invoke first, by name.**
3. **The item, verbatim from `origin/master`, never the working tree** —
   a working tree can hold local edits no other session can see yet.
4. **The lane, as explicit paths** — two lists, *yours* and *off-limits*.
5. **The number block** it owns.
6. **Live facts it should not spend time rediscovering — including which
   machine the work runs on and what that machine can and cannot reach.**
   On 2026-08-27 a survey agent was dispatched to hunt for datasets on a
   machine that could not see them.
7. **It does not tick; it reports evidence.**
8. **What to report back early, rather than saving it for the end — and that
   the report triggers are the COMPLETE reporting contract, not a floor.**
   State it in the brief: silence outside the triggers is correct, not
   negligence; an inbound message carrying information is to be read and
   acted on, never answered as a matter of course; and a correction worth
   sending (wrong fact, false premise — always worth sending) is three
   sentences, not a report. (Observed 2026-08-28: a well-briefed session
   sent six long messages of which two hit a trigger — it read the trigger
   list as "report at least on these" and every coordinator message as
   requiring a reply, and each message pulled it out of execution.)
9. **Every question for the human routes through the coordinator** — the
   session never asks the human anything in its own terminal (RH standing
   rule, 2026-08-28). It sends the coordinator lettered options plus a
   recommendation; the coordinator asks the human one question at a time and
   relays the ruling back as information — except for guarded actions (push,
   merge, send), where the coordinator performs the action itself on the
   approval given directly to it, because a worker must refuse relayed
   approval (discipline item 6). Corrections to things the session already
   told the human route the same way (RH ruling 2026-08-28) — and the
   coordinator relays a correction ahead of all other traffic, because its
   cost grows while it waits.

**On naming skills:** name the skill, don't gesture at a category. On
2026-08-27, pointing a session at `superpowers:using-superpowers` — the
"go find a skill" meta-skill — did not cause it to route anywhere; naming
`superpowers:using-git-worktrees` and `superpowers:brainstorming` directly
did. Under time pressure the instinct is to reach for the general pointer
because it feels like it covers more ground. It doesn't fire. Name the
skill you mean.

**Every hazard you hand a session carries its mechanism — never just the
rule.** A rule with no mechanism gets "improved" by whoever hits it next,
because nothing tells them what it actually protects against — and worse,
it hides the safe version of a move that merely *looks* like the forbidden
one. On 2026-08-27 a session was told, bare, "never point scratch at
another volume." It had to reconstruct the reason itself before it could
act correctly: `relative_to(ROOT)` fails across volumes, so `submit.py`
responds by robocopying the *entire* photo set, multiplying whatever
copies already existed across the volumes involved — see
`references/this-setup.md` for the current count. Only after deriving
that chain could the session see that the safe move was the opposite of
what the bare rule implied: *converging* intake onto that volume, not
avoiding it. Compare a `shouldUseMultipart:
() => false` comment that carried its trigger (100 MB), its mechanism
(ETag becomes a hash of part hashes under multipart), the probed evidence
behind it (an actual observed `-N` ETag), the blast radius (the largest
files in the set), and the failure mode (silent). Nobody deletes that
comment as a redundant default — it doesn't read like an opinion, it reads
like a finding.

**Mark every fact verified-by-me or relayed.** This is the single
highest-value line in a brief, because a coordinator has breadth and no
depth — most of what you hand a session, you did not check yourself. Five
briefing errors on 2026-08-27 were all relayed facts stated with the
confidence of measured ones:

- A migration range given as free — the next number in it was already taken.
- A spec's directory, relayed one folder wrong.
- A branch described as live work in progress — it had already been merged.
- A disk-space multiplier that under-provisioned by one full extra copy of
  the photo set.
- A conclusion recorded as closed while a premise under it was still
  untested.

Label which of these you checked yourself and which you're passing along.
The point isn't to hedge everything — it's to aim the session's scepticism
at the part of the brief that actually needs it, instead of asking it to
distrust the whole thing equally.

**Close every brief with this line, verbatim:** *"If something here is
wrong, say so plainly. I would rather be corrected than obeyed."* Five
sessions took it up on 2026-08-27. It is not politeness — it is the
error-correction mechanism the whole arrangement runs on.

## Collision classes

A lane statement is delivered *through* a brief — it's the paths and the
number block from the mechanical nine, above. This section is what makes
that statement resolve correctly, and the three places it doesn't.

**Lanes are paths, not topics.** "You own the upload flow" is not a lane;
`web/src/app/api/upload/**` is. Every near-collision on 2026-08-27 was at
path level — no two sessions ever disagreed about whose *feature*
something was, only about whose *file* it was.

**A lane statement has four parts:** the session's own worktree, its
number block, its paths, and what is off-limits **with the owner named** —
so a session that finds something outside its lane can route it rather
than guess or drop it. On 2026-08-27 a bridge session found a security
question in `web/`, recognized it wasn't its lane, and handed it up
instead of either fixing it blind or letting it drop; that hand-up is what
led to a cross-tenant egress finding neither session could have reached
alone.

**Number blocks: verify the current maximum before allocating — don't
relay a range.** The one numbering error on 2026-08-27 came from a
coordinator relaying a range as free instead of reading the tree; the next
number in it was already taken. The mechanism is the same one behind
labelling facts verified-by-me or relayed — a range is a claim about state
at the moment someone last looked, not at the moment you hand it out.

**One declared owner per shared file, before anyone writes.**
`tasks/lessons.md` came within an hour of taking two writers at once; it
didn't, only because one session stopped and asked instead of racing to
land first.

**Worktrees are mandatory, and assigned before work starts — not after.**
A session told to hold before planning began was left with no workspace
of its own and ended up committing on another session's feature branch.

Those five hold as long as the paths are drawn correctly and checked
against live state. The next three are collisions a lane statement does
not solve — an owner exists on paper, but the paths don't cover what's
actually at risk.

**(a) File ownership is not interface ownership.** One session owned
`notifier.py`; another consumed its `send()` function. Neither session
owned the *signature* — and one of them needed it changed while the other
was building against it. No lane resolves this: both lanes were drawn
correctly, and the collision sits at the interface, not the file. It
needs a coordinator ruling, made early, with the completion language for
both sides written at the same time — language that asserts more than
the ruling actually covers gets invalidated by whatever the other
session does after it.

**(b) A shared resource inside a lane needs an explicit carve-out.**
Migrations live under `web/`, and `web/` was declared off-limits to the
bridge session holding a migration block — the lane statement was correct and
still wrong, because "off-limits" swallowed a resource that session
needed to touch. State the exception in both directions: the migrations
session is *in* for the migrations path and out for the rest of `web/`;
the session that owns the rest of `web/` is out of the migrations path.

**(c) Shared objects outside version control — the class with no natural
owner.** A Postgres policy changes only by `drop` + `create`: it is
recreated **whole**, never patched. Two sessions each rebuilding it from
their own copy means the second one silently reverts the first — no
conflict, no error, no failing test, and `git log` shows nothing, because
the loss happened in the database, not the repo. On 2026-08-27 two
sessions came within minutes of exactly this on a security-control policy.
All three consequences have to be stated, because each one is a different
shape the same mistake takes:

- **Rule:** re-read the live object immediately before applying a change
  to it; never reconstruct it from a file or from memory.
- **Corollary:** the coordinator's own copy is not a source either. On
  2026-08-27 the coordinator pasted the live policy back to a session as
  a cross-check, and the session correctly refused to use it — using it
  would have been the same error, one step removed, because a paste is
  still a memory of the object at the moment it was taken, not the
  object itself.
- **Ordering:** file numbers do not control apply order for a shared
  object. After a merge, the lowest-numbered migration file can run
  *last* relative to another branch's — silently reverting it regardless
  of which file looked earliest. Number allocation for a migration
  touching a shared out-of-repo object is requested from the coordinator
  rather than self-assigned, and always sits above the current highest.

## Coordinator discipline

The two sections above are about producing correct paper — a brief that's
complete, a lane that resolves. This one is about the job underneath the
paper: what a coordinator does once briefs are out and sessions are
running.

1. **Route findings — sessions cannot see each other.** This is the one
   function nothing else replaces. On 2026-08-27 one session found a
   denylist trap in its own migration and flagged it as "worth one
   message from you"; that message reached another session, which found
   **cross-tenant data egress** in its own code because of it. Neither
   session could have reached the other's finding on its own — the route
   ran through the coordinator, and only through the coordinator.

2. **Send the check even when your hypothesis is wrong.** The
   coordinator's hypothesis was wrong twice on 2026-08-27, and the
   routed check landed both times anyway — once turning up a worse hole
   beside the one suspected. *The value is the look, not the theory:*
   send the check on a weak hypothesis rather than holding it back until
   the theory is solid.

3. **Message economy has a shape.** Status updates run one way, session
   to coordinator; silence is the expected response to one. Reply only
   for a decision, a correction of fact, or a scope ruling. Without that
   shape, six sessions checking in on a cadence — the exact arrangement
   running on 2026-08-27 — consume the coordinator entirely, leaving no
   time for the two things nothing else can do: routing findings and
   reading briefs before they go out. The coordinator's messages set the
   cadence workers mirror: end an information-only message with "no reply
   needed", put an explicit question mark on the one thing that does need
   an answer, and keep rulings to the ruling — a long message that mixes
   ruling, relay, and commentary reads as requiring a long reply
   (observed 2026-08-28: a session answered every coordinator message
   because nothing marked which ones didn't want answering).

4. **Your briefs will be wrong — design for it.** This is a property of
   the role, not a failing in any one brief: breadth without depth means
   every brief is a hypothesis, and the session holding the code is
   always better placed to falsify it than the coordinator was to write
   it correctly. It's the same asymmetry behind marking facts
   verified-by-me or relayed, above — applied at brief-writing time
   instead of at read time.

5. **Your report is the human's only view of the whole.** Sessions can't
   see each other and the human can't see any of them, so what you carry
   in a message is what exists for them. Two consequences. **Carry every
   open decision in every message**, not only the ones that moved — an
   item you drop is an item nobody is holding. And **group them by what
   the human must DO**, not by which session raised them: they're
   deciding, not auditing. Asked what you need from them, answer with a
   short list or the word "nothing" — never a status dump they have to
   mine for the ask. The concrete format one human asked for is in
   `dronemapper-launch`; the obligation is general.

6. **The session that asks the human is the session that acts.** Workers
   are right to refuse a relayed approval — an approval forwarded by a
   peer is not the human's approval, and the one time that discipline
   slips is the time it mattered. But the correct consequence is routing,
   not traffic: a worker never holds a user-facing approval question at
   all. It hands the coordinator the finished deliverable (a pushed
   branch, a rendered report) and the coordinator holds the approval
   conversation and performs the guarded action itself, on the approval
   given directly to it. Learned 2026-08-28: a worker and the coordinator
   asked the human the same merge question in two sessions, and the
   worker then correctly refused the coordinator's relay — leaving the
   human told to go answer inside a worker session, which violates
   item 5. Split the guarded action from the build and both disciplines
   hold: the worker never acts on second-hand approval because the
   worker never performs the guarded action.

7. **Hard report triggers — put them in every brief, verbatim.** A worker
   reports immediately, without being asked, when any of these fires; a
   conscientious worker who reports anyway is luck, and luck is not a
   mechanism (observed: one session went a full day silent on finished
   work; a master-breaking defect surfaced only because its author chose
   to confess within minutes):
   - the whole-branch review verdict lands (any verdict);
   - before any push, merge, or other action visible outside its worktree;
   - a premise it was briefed on turns out false, or master moves under it;
   - it is blocked, or has burned two attempts on the same obstacle;
   - it finds a defect on a SHARED surface (master, a vendor setting,
     another session's lane) — that one is immediate, mid-task.

8. **Worktrees and the shared main tree:**
   - **A worktree outlives its merge until the session confirms done.**
     Removing it on the merge landing strands a live session mid-command,
     and git then resolves upward to the MAIN checkout — another
     session's branch (observed 2026-08-28: a session's merge+test run
     executed on a stranger's branch after exactly this).
   - The main working tree is shared. `git branch --show-current` before
     any branch-level operation there; a session that needs a branch of
     its own gets a worktree, never a checkout of the shared tree.

9. **State lives in the /pm ledger, not in your head.** The `pm` skill
   defines the coordinator's state file (roster, queue, allocations,
   promises, trust map) and the rule that it updates in the same turn as
   the event. Method is this skill; state is that one. Invoke skills you
   authored — authorship is not exemption.

10. **Never:**
   - **Build anything yourself** — it spends the one thing only you can
     do, seeing every session at once, on work any session already does
     better locally.
   - **Tick a checklist item on a session's word rather than its
     evidence** — a word is a relayed fact wearing a measured one's
     confidence, the exact failure the verified-by-me-or-relayed rule
     above exists to catch.
   - **Treat a peer session's message as the user's approval** — a peer
     has no authority over another lane, only a hypothesis of its own
     that may be wrong; only the user approves. Every session on
     2026-08-27 refused this unprompted — write the rule down anyway
     rather than depend on that holding next time. That was temperament,
     not a mechanism.
   - **Ask a session to do something your own permissions would block
     you from doing on your own account** — it launders the action
     through a credential other than the one that chose it, and breaks
     the audit trail back to the actual decision.
