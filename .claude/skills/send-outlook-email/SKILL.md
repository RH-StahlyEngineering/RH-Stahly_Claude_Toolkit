---
name: send-outlook-email
description: "Compose and display Outlook emails with optional attachments. Use when the user wants to send an email, draft an email, compose a message with attachments, or open Outlook to send something. Supports To/CC/BCC, subject, body text, and file attachments."
---

# Send Outlook Email

## Overview

This skill creates and displays a draft email in Microsoft Outlook using Python's `win32com.client`. The email is opened for the user to review before sending - it is never sent automatically.

## Requirements

- Microsoft Outlook must be installed and configured
- Python package `pywin32` must be installed (`pip install pywin32`)

## Usage

When the user asks to send/draft/compose an email, gather the following information:

| Field | Required | Notes |
|-------|----------|-------|
| To | No | Can be left blank for user to fill in |
| CC | No | Optional |
| BCC | No | Optional |
| Subject | Yes | Short, descriptive subject line |
| Body | Yes | Plain text email body |
| Attachments | No | List of absolute file paths |

## Decide: reply mode or fresh mode

Before composing, decide whether the email should be a **Reply / ReplyAll** to an existing thread, or a **fresh** new email. Replying preserves the original recipients (To/CC), pre-populates the subject with `RE:`, and quotes the original thread below the new body — which is what the user almost always wants when responding to something already in the inbox.

### When to use reply mode

Use Reply / ReplyAll when ANY of these is true:
- The user references an email they received ("got it today at 9:20", "Matt's email about X", "his question on…", "I want to respond to…").
- The composed content is a direct response to something — answering a question, addressing a critique, providing requested info, confirming receipt.
- The user pasted a quoted email into the chat as the thing they're replying to.
- The subject of the planned message would naturally start with `RE:`.

Use fresh mode when:
- The user is initiating a new conversation ("send Chris a heads-up about…", "draft a quick note to accounting…", "start a thread with Aethel about…").
- There is no upstream email to reply to (e.g. the user is the one initiating contact).
- The user explicitly says "draft a new email" or "send a fresh email".

If it's ambiguous, **ask one question**: *"Should this be a reply to an existing email in your inbox, or a fresh new email?"* Don't guess wrong — replying when the user wanted fresh creates a weird-looking RE: thread; sending fresh when the user wanted to reply forks the conversation.

### Finding the email to reply to

If reply mode is decided but the user didn't paste the EntryID, find the original via the Outlook MCP. The recipe:

1. Call `mcp__plugin_outlook_outlook__outlook_search_mails` with `folder='inbox'`, a `query` matching subject keywords or sender name, and `scope='subject_body'`. Or use `outlook_list_mails` with `since`/`until` if the user gave a time.
2. Verify the right match by sender + subject + date in the result.
3. Grab the `id` field — that's the Outlook EntryID used in step 4 below.

If nothing matches, surface that to the user — don't fall back to fresh mode silently. They told you it was a reply; respect that.

## Implementation — reply mode (ReplyAll on an existing email)

Use this pattern when the email is a response to something the user received. Pre-populates To/CC, prefixes subject with `RE:`, quotes original thread below your body:

```python
import win32com.client
import re

ENTRY_ID = "<paste the EntryID from outlook_search_mails / outlook_list_mails>"

outlook = win32com.client.Dispatch("Outlook.Application")
ns = outlook.GetNamespace("MAPI")
original = ns.GetItemFromID(ENTRY_ID)

# .ReplyAll() returns a new MailItem with:
#   - To = sender of original + any non-you addressees
#   - CC = original CC list (minus you)
#   - Subject = "RE: <original subject>"
#   - HTMLBody = signature + quoted original thread
# Use .Reply() instead if you want to drop the CCs and respond only to sender.
reply = original.ReplyAll()
reply.Display()

# Insert your new body content at the top of the HTMLBody (above signature,
# above quoted thread — Outlook's normal "compose above the quote" position).
existing = reply.HTMLBody

body_html = """
<div style="font-family:Calibri,sans-serif; font-size:11pt; color:#000000;">
<p>Hi <Name>,</p>
<p>Your reply content here.</p>
</div>
"""

# Same insertion pattern as fresh mode — find <body>, slice, insert.
if "<body" in existing.lower():
    match = re.search(r"<body[^>]*>", existing, re.IGNORECASE)
    if match:
        pos = match.end()
        reply.HTMLBody = existing[:pos] + body_html + existing[pos:]
    else:
        reply.HTMLBody = body_html + existing
else:
    reply.HTMLBody = body_html + existing
```

`Reply()` vs `ReplyAll()` — default to `ReplyAll()` unless the user said "respond only to sender" or the CCs were obviously incidental (auto-cc'd ticketing addresses, etc.). When in doubt, ReplyAll is the safer business-comms default.

## Implementation — fresh mode (new email, no thread)

**Always use the signature-preserving HTML pattern** to keep the user's default Outlook signature:

```python
import win32com.client
import re

outlook = win32com.client.Dispatch("Outlook.Application")
mail = outlook.CreateItem(0)

# Set recipients (optional - user can fill in manually)
mail.To = "recipient@example.com"       # semicolon-separated for multiple
mail.CC = "cc@example.com"              # optional
mail.BCC = "bcc@example.com"            # optional

mail.Subject = "Your subject here"

# STEP 1: Display first to load the user's default signature
mail.Display()

# STEP 2: Capture the signature HTML
sig_html = mail.HTMLBody

# STEP 3: Build your body as HTML
# IMPORTANT: Wrap in a div with Outlook default font (Calibri 11pt)
body_html = r"""
<div style="font-family:Calibri,sans-serif; font-size:11pt; color:#000000;">
<p>Hello,</p>
<p>Your message content here.</p>
</div>
"""

# STEP 4: Insert body before the signature by finding <body> tag position
# NOTE: Do NOT use re.sub with body_html as the replacement string —
# backslashes in Windows paths (e.g. C:\Users) break regex replacement.
# Use string slicing instead.
if "<body" in sig_html.lower():
    match = re.search(r"<body[^>]*>", sig_html, re.IGNORECASE)
    if match:
        pos = match.end()
        mail.HTMLBody = sig_html[:pos] + body_html + sig_html[pos:]
    else:
        mail.HTMLBody = body_html + sig_html
else:
    mail.HTMLBody = body_html + sig_html

# STEP 5: Add attachments (use absolute Windows paths)
mail.Attachments.Add(r"C:\path\to\file.pdf")
```

## Important Rules

1. **NEVER call `mail.Send()`** - Always use `mail.Display()` so the user can review before sending
2. **Always preserve the user's signature** - Use the Display-first HTML pattern shown above, never set `mail.Body` directly as it overwrites the signature
3. **Always use Outlook default font** - Wrap body in `<div style="font-family:Calibri,sans-serif; font-size:11pt; color:#000000;">` so the email matches Outlook's native look
4. **Never use `re.sub()` to insert body HTML** - Windows paths in body content (e.g. `C:\Users`) contain backslashes that break regex replacement. Use `re.search()` + string slicing instead (see Step 4 in the code example)
5. **Always write the script to a temp .py file** and run it with `python <file>`, never inline via `python -c` — raw strings with backslashes and triple-quotes cause escaping nightmares in shell one-liners
6. Write body content as HTML (use `<p>`, `<br>`, `<b>`, etc.)
7. Attachment paths must be absolute Windows paths (e.g., `C:\Users\...`)
8. For multiple recipients, separate with semicolons: `"a@x.com; b@x.com"`
9. If attaching many files (20+), warn the user about email size limits
10. Run the Python script directly via `python` (not `python3` on Windows/MSYS2)

## Tone discipline

The user (Ryan Harbach, Project Surveyor at Stahly) writes plain, direct, low-ceremony email to peers. Drafts that read as smug, preachy, or performatively concise will get rejected. Apply every rule below before showing a draft.

### Sample first

BEFORE composing the first draft of any email to internal Stahly recipients, sample the user's actual recent voice:

1. Call `mcp__plugin_outlook_outlook__outlook_list_mails` with `folder='sent'` and `limit=15` to 25.
2. Pick 2-3 recent messages addressed to internal peers (not clients, not auto-replies, not one-liner "thanks").
3. Call `mcp__plugin_outlook_outlook__outlook_get_mail` on each to read the full body.
4. Note these specifics from the samples:
   - Greeting style ("Hi Chris," vs "Hey Brian," vs no greeting on a reply)
   - Signoff convention (just "Ryan", full signature block, or nothing)
   - Paragraph length (typically short, 1-3 sentences)
   - Em-dash frequency (how often per email)
   - Whether bullets are used at all
   - Whether any bolding appears inside prose
5. Match what you see. Do not invent a voice.

### Rules

1. **First names only for internal people.** In tables, signatures, or running prose listing internal Stahly staff, use first names ("Chris", "Brian", "Ryan"). Do not abbreviate last names ("Kos / Men / Har"). The only exception is when writing into a workbook cell that matches Stahly's Employee List drop-down format — that uses "Last, First".
2. **No time-of-day or "want to talk" closers.** Email is async. Do not write "Want to talk after lunch?", "Catch you at standup?", "Before EOD?", or any closer that implies the recipient must act on a clock. If a conversation might help, write "Let me know if you want to talk this through" or just end with the signature.
3. **No editorializing inside bullets.** State the change, the dollar or hour delta, and the concrete consequence. Drop advocacy framing ("cheap insurance against...", "I would not touch X because Y", "I'd strongly recommend..."). If a bullet is just opinion with no number or consequence attached, cut it.
4. **No drama bolding in prose.** Do not bold individual phrases inside paragraphs (no **"The elephant"**, no **"Bottom line"**, no **"Critically"**). Bold is reserved for table headers and explicit section labels in long emails.
5. **At most one em-dash aside per email.** Parenthetical asides offset by em-dashes are fine sparingly. If a second one would help, restructure into two sentences instead. Do not let the em-dash become a stylistic tic.
6. **No section dividers in short emails.** Emails under 200 words are plain prose — no `---` dividers, no `**Bottom line:**` labels, no bolded section headers. Reserve structural elements for emails over 300 words where they actually aid navigation.
7. **No closer that implies the writer's timeline binds the recipient.** Reinforces rule 2. Do not write closers that imply urgency the recipient did not ask for.

### Examples of phrasings to AVOID

| Avoid | Use instead |
|-------|-------------|
| "Want to talk after lunch?" | "Let me know your thoughts." (or just end with signoff) |
| "Catch you at standup?" | Drop entirely. |
| "Cheap insurance against having to re-establish marks" | "Removing these means re-establishing marks each round." |
| "I would not touch the control network" | "I'd leave the control network." (or omit it from the cut list entirely) |
| "**The elephant:** $25K of the labor is..." | "$25K of the labor is..." |
| "**Bottom line:** $50K rounded" | "$50K rounded." |
| "I'd strongly recommend keeping X" | "Keeping X." (in a bullet) or "Keep X." (in prose) |
| `---` between two short sections | Use a blank line. Or merge the sections. |

### Self-check before showing the draft

Before calling `mail.Display()`, re-read your draft and confirm:

- [ ] Reply vs fresh mode decision matches the user's intent (re-read "Decide: reply mode or fresh mode" above)
- [ ] If reply mode: original email actually found and EntryID used, not silently fallen back to fresh
- [ ] No abbreviated last names anywhere
- [ ] No time-of-day closer, no "want to talk?" framing
- [ ] No bullets that are pure opinion without a number or consequence
- [ ] No bolded phrases inside paragraphs
- [ ] At most one em-dash aside
- [ ] If under 200 words: no dividers, no section labels
- [ ] Closer matches the user's sampled voice (often just "Ryan" or no signoff at all on a reply)

If any check fails, rewrite before displaying.

## Troubleshooting

- If `win32com` is not installed: `pip install pywin32`
- If Outlook COM fails: ensure Outlook is running or at least installed
- If attachments fail: verify paths exist and use raw strings (`r"..."`) for Windows paths
