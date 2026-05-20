---
name: handoff-email
version: 1.0
description: Compose a standalone session-handoff email and open it as an Outlook draft (never auto-send). The email contains the operational identifiers needed to resume a Claude Code session (session ID, resume command, working directory, transcript path), a state-not-story summary of what got done, an actionable outstanding-items list, and references to any auto-memory updates made during the session. Use when the user wants to wrap up a session, send themselves a handoff, document a stopping point, hand off work to a teammate, or capture an actionable "here's where we are" note via email. Triggers on phrases like "send me a handoff email", "draft a session handoff", "email myself this session", "wrap up the session in an email", "send a handoff to <person>", "I want to be able to come back to this later", "remember where we left off in email form".
---

# handoff-email

The hammer: **compose a handoff email that future-you can act on in 30 seconds without re-reading the transcript.** Built on top of the same Outlook mechanics as `send-outlook-email`, but with a fixed structure tuned for Claude Code session handoffs.

## When to use

- *"Send me a handoff email about this session"*
- *"Wrap this up in an email so I can pick it back up Monday"*
- *"Draft a handoff to Sarah on the Woodford parcel work"*
- *"Email me where we left off"*
- Any time the user is closing out a working session and wants a durable, actionable artifact

## When NOT to use

- Generic email composition with no session-resume angle — use **send-outlook-email** instead.
- The user wants a *narrative* of what happened — that's a status report, not a handoff. Different shape (story, not state).
- The session involved no operational artifacts (no files modified, no commands worth re-running, no scripts created). A handoff email about nothing is noise.

## Operating principles (do not violate)

1. **Lead with the one identifier that unblocks everything.** The session ID and resume command come at the top, in their own block. If the recipient gets nothing else, they can still continue the work.
2. **Both story AND state.** State is what IS true now (actionable, scannable). Story is *why* things are the way they are (the arc, the pivots, what was learned). Both belong in the email, in their own sections. State without story leaves the recipient guessing about rationale; story without state leaves them with no way to act.
3. **Story is the arc, not the play-by-play.** 3–6 bullets covering the meaningful turns: what we set out to do, what surprised us, what we changed our minds about, what worked. NOT every command run or detour debugged — the transcript is for that.
4. **State is current-fact bullets.** Each one describes something that IS true at the end of the session: a value, a file's contents, a system's status. Not "I did X" but "X is now Y."
5. **Absolute paths, exact commands, exact handles.** No "the file we made earlier." Six weeks from now there's no shared context.
6. **The outstanding-items section is the most valuable part.** Make it actionable: what specifically needs to happen next, where the work was paused, what's not yet verified.
7. **Flag hidden state explicitly.** Unsaved drawings, uncommitted git changes, drafts not sent, processes still running. The #1 cause of handoff disasters is the recipient not knowing about a non-obvious state.
8. **Cite memory updates.** When the auto-memory system learned something durable during the session, list those entries by title so the recipient knows future sessions will know these without being re-told.
9. **Format for skimming.** Section headers (`<h3>` or bold lead-ins), bulleted lists, code formatting for paths/IDs/commands. The story section is allowed to push the email beyond one screen — but each bullet still has to earn its line.
10. **Never auto-send.** Always `mail.Display()`; never `mail.Send()`. The user reviews before sending. (Same rule as the parent `send-outlook-email` skill.)

## Required content sections (the checklist)

Every handoff email MUST include these, in this order, even if a section is "(nothing applicable)":

1. **Opening sentence** — one line: "Reference for resuming Claude Code session on \<job/topic\>, paused \<date\>."
2. **Operational identifiers** — session ID, resume command, **hostname** (the computer the session was on), working directory.
3. **How to resume** — numbered steps: (1) sign in to *hostname* if not already there, (2) open terminal, (3) `cd <dir>`, (4) `claude --resume <id>`. Even if it feels obvious. Future-you will thank present-you.
4. **Transcript location** — the JSONL session file path under `~/.claude/projects/` (on the named host).
5. **Working files / artifacts** — list of paths on disk that the session created or modified (scripts, reports, drawings, etc.). If anything is on a *network share* vs *local disk*, call that out — only network artifacts are reachable from other machines.
6. **The story (arc)** — 3–6 bullets covering the meaningful turns: what we set out to do, what changed mid-session, what surprised us, what got rejected and why. Skip the mechanical debugging detours. "Explain it to a colleague over coffee," not "play me the tape."
7. **The state (current facts)** — short bullets, each one a thing that IS true now. Values, file states, system statuses. Not "I did X" — "X is now Y."
8. **Outstanding / to revisit** — short bullets, actionable. Each bullet is something the recipient might need to do.
9. **Hidden state warnings** (only if applicable) — unsaved files, running processes, partial edits, etc. Use bold or a `⚠️`-style flag.
10. **Memory updates** (only if applicable) — list of memory file titles that were added/updated.

If the user specifies a recipient other than themselves, replace "future-you" framing with neutral "the recipient" framing throughout.

## Why the hostname matters

Different machines = different paths, different installed software, different network access. A session ID alone doesn't tell the recipient where the transcript lives or whether the artifacts are reachable. Always include the computer name so the recipient can decide: "do I need to remote into that machine, or can I resume from here?" Especially important when the user works across multiple computers — the next session might start on a different one.

## Defaults

- Recipient: `rharbach@seaeng.com` (the user) unless otherwise specified
- Subject template: `Claude Code session: <topic/job> (session <first-8-chars-of-id>)`
- Body style: Outlook default Calibri 11pt, signature preserved at the bottom

## Gathering the session ID and hostname

To find the current session ID, list the most-recently-modified subdirectory under `~/.claude/projects/`:

```powershell
Get-ChildItem "$env:USERPROFILE\.claude\projects\C--Users-rharbach" -Directory |
  Sort-Object LastWriteTime -Descending | Select-Object -First 3 | ForEach-Object { $_.Name }
```

The first result is the active session. The full transcript directory is `$env:USERPROFILE\.claude\projects\C--Users-rharbach\<session-id>\`.

To get the hostname (Windows):

```powershell
$env:COMPUTERNAME
```

Include both verbatim in the email — no abbreviating, no guessing.

## Implementation

Same Outlook signature-preserving HTML pattern as `send-outlook-email` (see that skill's SKILL.md for the canonical pattern). Specialized below for handoffs:

```python
# template -- copy, fill in, save as a one-off script, and run with `python <file>`
import win32com.client
import re

# ----- Fill these in for the specific handoff -----
SESSION_ID      = "fe65c105-d149-4066-8214-218a2fae5f32"
SHORT_ID        = SESSION_ID[:8]
TOPIC           = "<job number or topic, e.g., 3898-00125 parcel editing>"
HOSTNAME        = "<the computer name, e.g. STAHLY-RH01>"   # $env:COMPUTERNAME on Windows
WORKING_DIR     = r"C:\Users\rharbach"
TRANSCRIPT_DIR  = rf"C:\Users\rharbach\.claude\projects\C--Users-rharbach\{SESSION_ID}"
RECIPIENT       = "rharbach@seaeng.com"   # default

SUBJECT = f"Claude Code session: {TOPIC} (session {SHORT_ID})"

# ----- Build sections -----
artifact_paths = [
    r"C:\Users\rharbach\AppData\Local\Temp\<dir>\<file1>",
    # ... add as needed; note which are network vs local
]
# 3-6 bullets: the arc of the session. What we set out to do, what changed.
story_bullets = [
    "<set out to do X>",
    "<pivoted from Y to Z because ...>",
    "<learned that ...>",
]
# Current-fact bullets. "X is now Y", not "I did X".
state_bullets = [
    "<fact 1: what is true now>",
    "<fact 2>",
]
outstanding_bullets = [
    "<action 1: what specifically needs to happen next>",
    "<action 2>",
]
hidden_state_warnings = [
    # only if applicable, e.g.:
    # "Drawing 3898-00125_COS.dwg has unsaved edits in AutoCAD on STAHLY-RH01.",
]
memory_updates = [
    # only if applicable, e.g.:
    # "AutoCAD COM from PowerShell 7 (autocad_com_powershell.md)",
]

# ----- Compose the body HTML -----
def li_block(items):
    return "".join(f"<li>{x}</li>" for x in items)

artifact_html = li_block([f"<code>{p}</code>" for p in artifact_paths]) if artifact_paths else "<li>(none)</li>"
story_html        = li_block(story_bullets)        if story_bullets        else "<li>(nothing notable)</li>"
state_html        = li_block(state_bullets)        if state_bullets        else "<li>(nothing applicable)</li>"
outstanding_html  = li_block(outstanding_bullets)  if outstanding_bullets  else "<li>(nothing outstanding)</li>"
warnings_block    = f"<p><b>&#9888; Hidden state to know about:</b></p><ul>{li_block(hidden_state_warnings)}</ul>" if hidden_state_warnings else ""
memory_block      = f"<p><b>Memory updates from this session:</b></p><ul>{li_block(memory_updates)}</ul>" if memory_updates else ""

body_html = rf"""
<div style="font-family:Calibri,sans-serif; font-size:11pt; color:#000000;">

<p>Reference for resuming the Claude Code session on <b>{TOPIC}</b>.</p>

<p><b>Session ID:</b> <code>{SESSION_ID}</code><br>
<b>Host:</b> <code>{HOSTNAME}</code><br>
<b>Working directory:</b> <code>{WORKING_DIR}</code></p>

<p><b>How to resume:</b></p>
<ol>
  <li>Sign in to <code>{HOSTNAME}</code> if you're not already there.</li>
  <li>Open a terminal (PowerShell or your usual shell).</li>
  <li><code>cd {WORKING_DIR}</code></li>
  <li><code>claude --resume {SESSION_ID}</code></li>
</ol>
<p>Or run <code>claude --resume</code> with no argument and pick from the recent-sessions list &mdash; this one will be near the top.</p>

<p><b>Transcript location</b> (on <code>{HOSTNAME}</code>):<br>
<code>{TRANSCRIPT_DIR}</code></p>

<p><b>Working files / artifacts</b> (on <code>{HOSTNAME}</code> unless noted):</p>
<ul>{artifact_html}</ul>

<p><b>The story (what happened):</b></p>
<ul>{story_html}</ul>

<p><b>The state (what is true now):</b></p>
<ul>{state_html}</ul>

<p><b>Outstanding / to revisit:</b></p>
<ul>{outstanding_html}</ul>

{warnings_block}
{memory_block}

</div>
"""

# ----- Standard Outlook signature-preserving pattern (do not auto-send) -----
outlook = win32com.client.Dispatch("Outlook.Application")
mail = outlook.CreateItem(0)
mail.To = RECIPIENT
mail.Subject = SUBJECT
mail.Display()                 # load default signature

sig_html = mail.HTMLBody
if "<body" in sig_html.lower():
    m = re.search(r"<body[^>]*>", sig_html, re.IGNORECASE)
    if m:
        pos = m.end()
        mail.HTMLBody = sig_html[:pos] + body_html + sig_html[pos:]
    else:
        mail.HTMLBody = body_html + sig_html
else:
    mail.HTMLBody = body_html + sig_html

# NOTE: mail.Display() was already called above. NEVER call mail.Send().
```

Run the script directly: `python <file>` (NOT `python3` on Windows / MSYS2).

## Critical "do not" list

- **Never** call `mail.Send()`. Always `mail.Display()`.
- **Never** write the body HTML before calling `mail.Display()` once — the signature won't be loaded yet.
- **Never** use `re.sub(...)` to insert the body HTML — Windows paths in the body contain backslashes that break regex replacement. Use `re.search(...)` + slicing.
- **Never** inline-execute via `python -c` — multi-line strings with backslashes and triple-quotes are escaping nightmares in shell one-liners. Always write the script to a temp `.py` file.
- **Never** narrate the session journey. Bullets describe current state, not historical actions.
- **Never** invent file paths. If a path isn't real, omit the bullet rather than write a placeholder.

## Test the email before sending

Before any handoff email leaves Outlook, mentally check:

1. Could a teammate execute the resume command without asking any question?
2. Are all paths absolute and verified to exist?
3. Does the "outstanding" section name *actions*, not just topics?
4. Did I flag every piece of hidden state?
5. Does it fit in one screen at typical zoom?

If any answer is "no," the email isn't ready.
