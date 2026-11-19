# Scheduled Survey

A weekday 06:30 task runs the master unattended in Survey mode. Nobody is awake, so for that run the run rules below override the rest of the skill.

## Run rules

Your job: write the digest file, update the ledger, deliver the file to RH.

- **Write the digest file**, `<YYYY-MM-DD>.md` in the digests folder SKILL.md Survey mode names (overwrite today's): the ranked view in Presenting order, then:
  - `## Waiting on RH`: every decision, numbered, each with your pick and a one-line why, instead of asking them one at a time.
  - `## Not done (scheduled run)`: every action the skill would otherwise take now (a merge, even of an approved green PR; a "hold" or answer to a session; a start, archive or pin; any mail), instead of taking it. Survey mode's no-message rule holds.
- **Ledger guard.** Write `LEDGER.md` only if it has no uncommitted changes and SKILL.md Ledger's branch rule allows it; else leave it and say why. Commit only that file: `ledger: morning survey <date>`. Never push.
- **Deliver the file.** Send it with `SendUserFile` (status `proactive`) when that tool is available; otherwise give its full path. End with the ledger sha or why it was skipped, and the top of the ranked view.

## Registering the task

Registered by ticket 09, once the installed skill is v2. Call `mcp__scheduled-tasks__create_scheduled_task` with exactly these arguments. Do not register this task while `~/.claude/skills/master-session/` is still v1. The prompt reads the repo copy of the skill, but RH's other instructions still point at the installed one.

| Argument | Value |
|---|---|
| `taskId` | `master-session-morning-survey` |
| `title` | `Morning Survey (master session)` |
| `description` | `Weekday 6:30 Survey of RH's pinned sessions: ledger update plus a ranked digest file sent to RH. Messages, merges and asks nothing.` |
| `cronExpression` | `30 6 * * 1-5` (local time, Monday to Friday 06:30) |
| `notifyOnCompletion` | `true` |
| `prompt` | the block below, verbatim |

Notes for registering:

- The task runs only while the desktop app is open. If the app is closed at 06:30, the task runs on the next launch. Tell RH this.
- Dispatch can lag a few minutes because of load balancing.
- Register it from a session whose permission mode lets an unattended run read files, run `python` and `git commit` without a prompt. Otherwise the 06:30 run stalls at its first permission prompt with nobody awake.

### Prompt

```text
You are RH's master session, running unattended as the weekday 06:30 Morning Survey. RH is asleep. Nobody will answer a question, approve a prompt or read a message until he opens this run's result.

Read C:\Users\rharbach\Desktop\RH-Master-Ledger\skill\master-session\SKILL.md in full, then "Run rules" in references\scheduled-survey.md beside it. Run "Start here", then every step of "Survey mode", applying "Verify before relaying" and "Ledger". The run rules override the rest for this run: they say what to do instead of messaging, merging or asking, even where the skill, the ledger, a session or an earlier RH message would allow the action. The working folder is unknown: use absolute paths (the skill's folder is the one above).

Scheduled-only details:
- Reading is fine: transcripts, files, `gh pr view` / `gh pr checks` / `gh run view`, read-only DB queries.
- Ledger guard: `git -C C:\Users\rharbach\Desktop\RH-Master-Ledger status --porcelain LEDGER.md` and `git -C C:\Users\rharbach\Desktop\RH-Master-Ledger branch --show-current`. Commit: `git -C C:\Users\rharbach\Desktop\RH-Master-Ledger commit -m "ledger: morning survey <YYYY-MM-DD>" -- LEDGER.md`. No push, no stash, no other files.
- Final message: short, readable on a phone, and the count of items under "Waiting on RH". Never claim a commit or a file you did not make.
- If a step fails, finish the rest, and list the failure first in the digest file and the final message.
```
