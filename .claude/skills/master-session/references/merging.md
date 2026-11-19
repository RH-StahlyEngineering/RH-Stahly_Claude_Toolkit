# Merging

Section names in this file are SKILL.md's. Every script command here is run from this skill's folder in the full form `python -X utf8 -I scripts/<script> <arguments>`: `python -X utf8 -I scripts/merges.py list --repo <owner/name>`, `python -X utf8 -I scripts/state.py prs drop <n>`. `merges.py` only reads GitHub and never merges; every command takes `--repo <owner/name>`.

## The waiting list

`merges.py list` reads every PR in the state file's `prs` rows on GitHub and prints one line each: number, rung, check state, what it does. A PR behind its base says so on its line (`green, 3 behind master`): that is information and asks nothing of you. Show RH those lines as printed, above the question, whenever a merge is what you ask him. It also writes each PR's check state back to the state file, and prints what needs you:

| Line | Do |
|---|---|
| `WENT RED  #n: <check> failed <link>` | Tell RH this turn, in one line with the check and the link, even while another question is open: his pile changed. Tell the owning session what to fix. The line prints once per PR. |
| `CONFLICT  #n: GitHub reports a merge conflict with <base>` | Tell the owning session to merge the base in and resolve it. The resolution is new work: when it is green, ask RH again. |
| `GONE  #n is merged (session <id> has landed, next: cleanup)` | `prs drop <n>`. The session that recorded the PR has landed: its steps are yours, unasked (SKILL.md Landed sessions and closeout). No session named: none recorded this PR. |
| `GONE  #n is closed` | `prs drop <n> --closed`. No session lands; a session named on the line still has work, or its archive is RH's question. |
| `MASTER IS RED  #n` | See Red master below. |
| `GATE PROBLEMS  comment on #n` | See Gate problems below. |

Run it at the start of a turn in which you will ask about, or act on, a waiting PR, and whenever a session reports a push to one.

## RH's approval

- **One message can approve several PRs** ("merge 12 and 14, not 15 yet"). Record it once, whole and unchanged: `merges.py approve 12 14 --words "<his whole message>"`, naming only the PRs it approves. A PR he left out or held back stays unapproved; ask about it in its turn.
- **Quote, never retell.** Anything you tell a session about the approval carries the line `approve` printed (`RH: "<his words>" (<time>)`), then your own instructions on separate lines below. His conditions ("after 8pm", "not 15") travel inside the quote and bind you.
- **An approval covers that PR's change as he saw it.** `approve` records the commit the PR is on with his words and the date and time. Not the next PR of the same session, and not a commit pushed later.
- **It carries over merges of the base.** When every commit since is a merge of the base and the PR's own change against its base is the same patch as before, his approval stands; `check` works that out from GitHub's compares and says `RH's approval of <commit> carries: only merges of <base> since.` Any other commit, or a compare that cannot be read, ends it.
- **Leave a behind PR alone.** Don't run `gh pr update-branch` before a merge question or before a merge; only when RH asks for it.

## Merging one PR

Run `merges.py check <n>` and merge only when it says `MERGE #n: yes`, in the same step, then `prs drop <n>`: that lands the session that recorded the PR (SKILL.md Landed sessions and closeout). It says yes when RH's approval still covers the commit the PR is on now, every check is green on that commit, GitHub reports no merge conflict, and master is not red. Anything else, a failed read of GitHub included, is a no. How far the PR is behind its base is printed in the yes and never makes a no.

- **`no`, checks red, pending or missing:** no merge. Red: tell RH which check and its link, and tell the owning session what to fix. Pending: wait for the session's or the app's next report, then check again; no timer. A carried approval changes nothing here: the checks must be green on the new commit.
- **`no`, his approval does not cover the commit it is on:** `check` names the two commits and why. When the reason is that the commits could not be read, run `check` once more. Otherwise read what was pushed (`gh pr view <n> --json commits`), tell RH in one line and ask again; on his yes run `approve` again.
- **`no`, merge conflict:** tell the owning session to merge the base in and resolve it. When it is green, tell RH what was resolved and ask again; on his yes run `approve` again.
- **`no`, GitHub has not said whether it conflicts:** it works that out shortly after a push. Run `check` again; never merge on a guess.
- Never re-run, skip or bypass a check or branch protection to get a yes.

## Red master

Some repos stop merges while their main branch is red (Agisoft_Coding ADR 0005): an issue titled "Master is red", labelled `master-red`, is open, and only the PR the CI owner labels `fixes-master` may merge.

- `merges.py` reads that issue. While it is open, `check` says no for every PR but the labelled fix, RH's approval or not. Tell RH once that merges are held and by which issue; his approvals stand and you merge when the issue closes.
- The fix still needs RH's approval and green checks like any PR.
- Never add or remove `fixes-master` or `master-red`, and never close the issue: they are the CI owner's.

## Gate problems

A gate problem is a check, hook or push gate that fails for a reason outside the change under test: the date, another PR, the machine, a test already red on master (ADR 0007).

- It goes to the issue `merges.py list` names on its `GATE PROBLEMS` line: the standing gate-problem issue, or the "Master is red" issue while that is open. Tell the session that met it to comment there with the symptom, the log and its branch, and to carry on with other work.
- Nobody but the CI owner changes gate files (workflows, hooks, the push gate, known-failure lists). Never tell a session to patch, skip or re-run its way past a gate, and don't do it yourself.
- No such issue in the repo: tell RH.
