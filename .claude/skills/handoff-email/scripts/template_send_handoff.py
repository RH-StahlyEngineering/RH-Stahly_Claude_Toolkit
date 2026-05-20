"""
Template handoff-email script. Copy this file, fill in the FIELDS section,
save the copy in a temp directory, and run with `python <copy.py>`.

Never call mail.Send(). Always mail.Display() so the user reviews first.
"""
import win32com.client
import re

# ===========================================================
# FIELDS -- fill these in for the specific handoff
# ===========================================================
SESSION_ID      = "<paste full session id here>"
TOPIC           = "<short topic/job number, e.g. '3898-00125 parcel editing'>"
HOSTNAME        = "<the computer name from $env:COMPUTERNAME>"
WORKING_DIR     = r"<absolute path, e.g. C:\Users\rharbach>"
TRANSCRIPT_DIR  = rf"C:\Users\rharbach\.claude\projects\C--Users-rharbach\{SESSION_ID}"
RECIPIENT       = "rharbach@seaeng.com"

# Each entry is one bullet. Use raw strings for Windows paths.
# Note in the bullet whether a path is on a network share (reachable from
# other machines) vs local disk (only reachable from HOSTNAME).
ARTIFACT_PATHS = [
    # r"C:\Users\rharbach\AppData\Local\Temp\<dir>\<file>   (local)",
    # r"\\stahly\PROJECTS\<job>\<...>   (network share)",
]

# 3-6 bullets: the arc of the session. What we set out to do, what changed
# mid-session, what surprised us, what got rejected and why. Skip the
# mechanical detours -- "explain it to a colleague over coffee," not
# "play me the tape."
STORY = [
    # "Started with goal X based on assumption Y",
    # "Discovered Y was wrong because of Z, pivoted to approach W",
    # "Tried W; it produced the result that's now in the drawing",
]

# Current-fact bullets. "X is now Y", not "I did X".
STATE = [
    # "Polyline 15053 (20-ac parcel) is at exactly 20.0100 ac",
    # "Topology between the 3 V-BNDY-PARCEL polylines is clean",
]

# Actionable bullets: what specifically needs to happen next.
OUTSTANDING = [
    # "Save the drawing in AutoCAD if you want the edits to persist",
]

# Optional. Bold-flagged in the email. Use ONLY for non-obvious state.
HIDDEN_STATE_WARNINGS = [
    # "Drawing 3898-00125_COS.dwg has unsaved edits in AutoCAD on STAHLY-RH01",
]

# Optional. Titles of memory files added/updated this session.
MEMORY_UPDATES = [
    # "AutoCAD COM from PowerShell 7 (autocad_com_powershell.md)",
]
# ===========================================================

SHORT_ID = SESSION_ID[:8]
SUBJECT = f"Claude Code session: {TOPIC} (session {SHORT_ID})"


def li_block(items):
    return "".join(f"<li>{x}</li>" for x in items)


def code_li_block(items):
    return "".join(f"<li><code>{x}</code></li>" for x in items)


artifact_html = code_li_block(ARTIFACT_PATHS) if ARTIFACT_PATHS else "<li>(none)</li>"
story_html = li_block(STORY) if STORY else "<li>(nothing notable)</li>"
state_html = li_block(STATE) if STATE else "<li>(nothing applicable)</li>"
outstanding_html = li_block(OUTSTANDING) if OUTSTANDING else "<li>(nothing outstanding)</li>"
warnings_block = (
    f"<p><b>&#9888; Hidden state to know about:</b></p><ul>{li_block(HIDDEN_STATE_WARNINGS)}</ul>"
    if HIDDEN_STATE_WARNINGS
    else ""
)
memory_block = (
    f"<p><b>Memory updates from this session:</b></p><ul>{li_block(MEMORY_UPDATES)}</ul>"
    if MEMORY_UPDATES
    else ""
)

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

# Outlook signature-preserving pattern (NEVER auto-send)
outlook = win32com.client.Dispatch("Outlook.Application")
mail = outlook.CreateItem(0)
mail.To = RECIPIENT
mail.Subject = SUBJECT
mail.Display()                                  # loads the default signature

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

# Intentionally NO mail.Send() -- user reviews and sends manually.
