# This setup — machines, traps, allocations

**Facts true of these machines and this repo on 2026-08-27. The method in
SKILL.md outlives these; this file will rot. Re-verify before relying on any
figure here.**

## Machines — which work runs where

| | VG49 (dev workstation) | Puget 2 (production) |
|---|---|---|
| Sessions | all dev sessions | operations only |
| Sees `H:` (the NAS) | **no** | **yes** |
| Runs Metashape / the cluster | no | yes |
| Reach from a dev session | — | **none** — RDP only, and `SendMessage` to a dev session FAILS from there |

**H:, Z: and `\\10.7.76.32\Bil-NASData` are one 45.8 TB pool (2026-08-27),
not three destinations.** A file "moved to the NAS" from H: has not been
copied.

**A dev session cannot message the Puget session and the Puget session cannot
message back.** Relay by hand. Do not brief a session to expect a reply.

## Volumes on Puget 2 (measured 2026-08-27, and moving)

- `C:\metashape-root\projects` is an **NTFS junction to D:**. So is `geoids`.
  `bridge-scratch` is real C:. `intake` **does not exist** and will be created
  as real C:.
- The work therefore **spans both volumes**; any single-volume disk check is
  blind to half of it.
- **`Path.resolve()` collapses junctions**, so junctioning `intake` to D: makes
  `submit.py`'s `relative_to(ROOT)` fail and robocopy the entire photo set —
  two copies instead of one. The intuitive fix is the trap.
- Free space is **not stable**: a Dropbox sync consumed 6.4 GB of D: in 55
  minutes (~23 GB/h) on 2026-08-27 while three sessions reasoned about the
  number, and the C: pagefile grew to 71.9 GB mid-run on 2026-08-24 with no
  log line.

## Spawning named sessions (2026-08-28)

- Working pattern: `Start-Process wt -w 0 new-tab … claude -n <name>`. Trap: a
  session spawned FROM a session inherits `CLAUDE_CODE_CHILD_SESSION` and
  silently loses transcript persistence — so RH opens the terminal himself,
  and the coordinator briefs the new session by SendMessage.
- **Reachability rot (2026-08-28):** the "Puget cannot message / be messaged —
  relay by hand" rule above no longer always holds — a Remote Control Puget
  session accepted SendMessage from a dev session on 2026-08-28. Verify per
  session via ListAgents rather than assuming either direction.

## Tooling traps that report the wrong cause

- **`.claude/hooks/fix-lint-before-commit.sh` runs `ruff check src/ tests/` in
  the shell's PERSISTENT cwd.** After any `cd web`, it lints TypeScript, fails,
  and blocks the commit with what reads as a Python error on a branch with no
  Python. It fires on the *next commit*, so cause and symptom do not
  co-locate. Fix: `cd` back to the repo root before committing.
- **Never suppress `impeccable` with inline HTML comments.** They are not
  stripped; on 2026-08-27 one shipped an approver's initials and an internal
  path into customer email bodies, twice per message, because it sat in a
  shared layout. Suppressions go in a **committed** config — note the root
  `.impeccable/config.json` is **untracked**, so a suppression there never
  reaches CI. `impeccable detect` needs the trailing `.`; bare `detect` scans
  nothing and exits 0.

## Allocations (2026-08-27 — verify before reusing)

| Range | Holder |
|---|---|
| 0001–0012 | pre-existing on master |
| 0013–0019 | w6-dev (upload flow) |
| 0020–0029 | b1-b2-dev (bridge) |
| 0030–0039 | w7-dev (accounting) |
| 0040+ | unallocated |

This table is a snapshot from 2026-08-27, not a live registry — it is already
stale in a way that proves why it must be re-verified rather than trusted:
`b1-b2-dev`'s branch has since merged to master as `57211f1b` (fast-forward
from `413fb6dd`) and used none of its 0020–0029 block (verified 2026-08-27 by
the coordinator: `ls web/supabase/migrations/ | grep ^002` returned nothing,
and the suite at the merge tip passed 84, skipped 15, before it was pushed).
That's not corrected here, because correcting it would suggest the table is
worth keeping current by hand. It isn't. Read the tree before allocating,
every time — see SKILL.md, "verify the current maximum before allocating —
don't relay a range."

**Migrations touching the `jobs_member_insert_submitted` policy get
coordinator-allocated numbers, always above the current highest,
irrespective of block** — see SKILL.md, collision class (c).

## Shared files with declared owners

| File | Owner |
|---|---|
| `tasks/lessons.md` | the coordinator |
| `docs/launch/**` and its three mirror surfaces | the coordinator |
| `tools/bridge/notifier.py` | dmai-dev (the file; its *signature* needed a ruling) |
| `tests/tools/bridge/test_commercial_column_catalog.py` | b1-b2-dev |

This table has the same shelf life as the one above — declared owners are as
of 2026-08-27. Confirm with the coordinator before treating a file as
unowned or its listed owner as current.
