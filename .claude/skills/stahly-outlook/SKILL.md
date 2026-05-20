---
name: stahly-outlook
description: Stahly Engineering email workflows on top of the Outlook MCP — bulk inbox triage with action-bucket classification, .msg archiving of utility locates into Stahly project folders, drafting receipts to stahlyaccounting@seaeng.com, project-based email lookup by job number. Use when the user wants to organize their Stahly Outlook inbox, archive 811 locate emails to a project's Survey_GIS_Data/4-Utility_Locates folder, forward receipts to accounting (drafts only — never auto-send), find all emails related to a given Stahly project (e.g. 3797-00826), or run a bulk mark-read sweep with classification subagents. Layers Stahly conventions on top of the generic plugin:outlook skill which handles MCP primitives. Triggers on phrases like "triage my inbox", "archive the locates for project X", "draft accounting forwards", "find emails about project Y", "clear noise from my inbox", "process my unread mail".
---

# Stahly Outlook

Stahly-flavored workflows on top of the `outlook-classic-mcp` plugin. The generic plugin's bundled `outlook` skill covers MCP primitives (tool catalog, EntryID conventions, date formatting, gotchas). This skill layers in the operational patterns specific to Stahly Engineering & Associates: project folder layout, locate-archive rules, accounting forwarding, internal sender heuristics, and a battle-tested bulk-triage pipeline.

## Upstream skill

For MCP tool catalog, parameter shapes, and generic gotchas, defer to:
`~/.claude/plugins/cache/outlook-classic-mcp/outlook/<version>/skills/outlook/SKILL.md`

The upstream skill covers: folder reference syntax, EntryID handling, ISO-8601 date formatting, `response_format` choice, recurrence, filesystem path sandbox, read-vs-write side effects, and Exchange DN sender quirks. Read it the first time you reach for a tool whose shape you don't remember.

## Hard rules

These come from operator memories — link, don't restate:

- `[[email_send_permission]]` — **NEVER call `outlook_send_mail`, `outlook_reply_mail`, or `outlook_forward_mail` without per-email user approval.** Drafts via `save_only=true` are fine (they don't send).
- `[[accounting_inbox]]` — Receipts/invoices forward to `stahlyaccounting@seaeng.com`. Don't mark these as read until they've been forwarded.
- `[[email_geo_vendor_marketing]]` — Geospatial/survey vendor mail (Blue Marble, Geo Week, Aerotas, DJI, Trimble, ROCK, AirWorks, Mapbox, MARLS, etc.) is professionally valuable. Don't bulk mark-read; surface unsubscribe links instead and leave the cluster unread.
- `[[utility_locate_archiving]]` — Only external ticketing-system senders (`mt@occinc.com`, `cl_irth_comm@irth.com`, Charter ROC, ELM Utility, Montana811) belong in a project's locate folder. Skip internal forwards/chats.

## Stahly mail environment quirks

Stahly runs **on-premises Exchange** at `https://mail.seaeng.com/owa/` — NOT Exchange Online / M365. This rules out several API paths that would otherwise be obvious:

- **Microsoft Graph API does not apply.** Graph's mail/rules endpoints require Exchange Online mailboxes. Don't try `/me/mailFolders/inbox/messageRules` — even if you can auth, the mailbox isn't there.
- **Even if you tried Graph anyway**, the Stahly tenant admin has user-self-consent disabled for unfamiliar apps. The "Microsoft Graph Command Line Tools" public client (`14d82eec-204b-4c2f-b7e8-296a70dab67e`) requires admin approval and the user can't grant it themselves. Same for Azure PowerShell, Azure CLI, and other common bypass apps.
- **EWS is up** at `https://mail.seaeng.com/EWS/Exchange.asmx` with `WWW-Authenticate: Negotiate`, but the HTTP/mail.seaeng.com Kerberos SPN isn't reachable (SPNEGO/SSPI fails with `WinError -2146893053` "specified target is unknown or unreachable"). NTLM via `requests_ntlm` fails with empty creds (401). EWS is only viable if the user provides their AD password to the script, which generally isn't worth the friction.
- **The local Outlook COM typelib has a broken cross-reference.** `gencache.EnsureDispatch("Outlook.Application")` fails on Python 3.14 with `TYPE_E_ELEMENTNOTFOUND` ("Element not found") at `itypeinfo.GetRefTypeInfo`. PowerShell PIA (`Microsoft.Office.Interop.Outlook`) fails identically on the typelib reference. Consequence: any code that needs to *set* `Rule.Actions.MoveToFolder.Folder` will silently fail — the assignment doesn't take, `Save()` then throws "One or more rules cannot be saved because of invalid actions or conditions." Confirmed in Python and PowerShell. **Don't burn time fighting this; route around it.**

### What still works on Stahly mail

| Need | How |
|---|---|
| Read inbox, move items, mark read/flag, save .msg | pywin32 COM (no Folder property setter on actions) ✅ |
| Create/modify rule **conditions** (SenderAddress lists, etc.) | pywin32 COM ✅ |
| Create rule **actions that take a Folder** (move-to-folder) | OWA browser automation via dev-browser → mail.seaeng.com ⚠️ |
| Delete rules | pywin32 COM ✅ |
| Execute rules on existing mail | `rule.Execute(False, folder, False, 0)` via pywin32 ✅ |
| Outlook MCP tools | All still work for single-item / approval-gated work ✅ |

### OWA browser automation pattern (for move-to-folder rules)

When a rule needs `MoveToFolder.Folder`, drive OWA's Rules UI instead. The skill `[[dev-browser:dev-browser]]` ships a Playwright-backed CLI. Pattern:

1. `await page.goto("https://mail.seaeng.com/owa/<user>@seaeng.com/?path=/options/inboxrules")` — note the on-prem path. M365 paths (`outlook.office.com/mail/options/mail/rules`) redirect with a "best performance" hint pointing at the on-prem URL — go straight to on-prem.
2. User signs in **once** in the dev-browser-managed Chromium (named instance `--browser owa` persists session across script runs).
3. Click `button[title="Add"]:not([disabled])` to open the rule dialog.
4. Fill Name field: `page.mouse.click(400, 184)` then `keyboard.type(name)`. The Name input has empty `aria-label` and only matches `input[type="text"]` on the visible Name row — `.first()` may pick a hidden input; use coordinates.
5. Set condition: open "Select one..." → hover `"It includes these words"` → click `"in the sender's address..."` → in the words sub-dialog, for each address: `fill(addr)` then `keyboard.press('Enter')` (commits to chips list) → click the **lowest-positioned OK button** (sub-dialog OK).
6. Set action: open second "Select one..." → hover `"Move, copy, or delete"` → click `"Move the message to folder..."` → folder picker dialog opens → click each path segment (`"Inbox"`, then `"Geo Week News"`) → click lowest-positioned OK.
7. Click main dialog OK → click `button[title="Save"]:not([disabled])`.

Reset state after a failure with `await page.goto(rules_url)` — Escape doesn't always clean modal stacks.

Required pre-step: any folder used as a move target must already exist. Create via pywin32 first:
```python
inbox = ns.GetDefaultFolder(6)
new = inbox.Folders.Add("Geo Week News")  # raises if exists; iterate first to check
```

## Server-side inbox rules (currently live)

These 6 server-side rules are deployed on the user's Exchange mailbox and run automatically on incoming mail. They were created via OWA browser automation (move-to-folder actions); the IT rule's senders were later trimmed via pywin32. **Don't recreate them; understand them.**

| # | Rule | Sender match | Action |
|--:|---|---|---|
| 1 | Auto-file Geo Week News | `info@geo-week.com`, `editor@geoweeknews.com` | move → `Inbox/Geo Week News` |
| 2 | Junk Panera receipts | `panera@m2.panerabread.com` | move → `Junk Email` |
| 3 | Junk cold marketing | 7 senders (Liqoxo PMP, CPI Bathrooms, Canva product, Warp feedback, Survival Med, Passport to Paradise, Autodesk marketing) | move → `Junk Email` |
| 4 | Auto-file IT system noise | `vaultmanager@seaeng.com`, `helpdesk@getsystems.net`, `noreply@barracuda.com` | move → `Inbox/IT` |
| 5 | Auto-file BuildingConnected | `@buildingconnected.com` | move → `Inbox/BuildingConnected` |
| 6 | Auto-file 811 Locates | `@occinc.com`, `@irth.com`, `@elmutility.com`, `@montana811.org`, `roc-northwest@charter.com`, `ed.mcfadden@charter.com` | move → `Inbox/811 Locates` |

### What the IT rule deliberately does NOT include

SpamTitan daily quarantine digests (`spamtitan@avataracloud.com`), Avatara case responses from `ccarpenter@avataracloud.com` and `jguntli@avataracloud.com` — these stay in the main inbox because the user needs to see them (quarantine releases, real support cases). Don't add them back to the IT rule without asking.

### What's NOT a Stahly noise sender even though it looks like one

- `4066014069@blackfootlife.com` — looks like a foreign-domain phishing vector but is actually a real Stahly phone-system voicemail forward. Leave alone.
- `support@survivalmedonline.org` — borderline fearmail; user opted to junk-rule it (rule 3) rather than treat as phishing.
- `quarantine@ess.barracudanetworks.com` — Barracuda quarantine notifications (different sender from `noreply@barracuda.com` which is product marketing). NOT in any rule; user wants to see these.

### Inbox subfolder map (after rules)

```
Inbox/
  811 Locates/         ← rule 6, live ticket workflow (also .msg archive source)
  BuildingConnected/   ← rule 5, GC bid invites
  IT/                  ← rule 4, Vault/GetSystems/Barracuda-marketing noise
  Geo Week News/       ← rule 1, curated industry reading
  UAVs/                ← pre-existing, user-managed
  (other pre-existing project folders — Equipment, Subdivisions, etc.)
```

When archiving locates (`Workflow: utility locate .msg archive`), source mail from **Inbox/811 Locates** rather than the main Inbox — that's where rule 6 deposits them now.

## Stahly project folder convention

Live data lives under the `\\stahly\PROJECTS\` share:

```
\\stahly\PROJECTS\<client-num>-<Client_Name>\-<job-num>_<Location>\
    DWG\
    Deliverables\
    Documents\
    Quality_Control\
    Received\
    Survey_GIS_Data\
        4-Utility_Locates\        ← .msg archive target
```

Project numbers look like `3797-00826` where `3797` is the client and `00826` is the job. The folder slug uses lowercase street designators (`1210_9th_street_S`) — paths are case-insensitive on Windows but match the slug to avoid surprise.

## When to use MCP tool calls vs. Python COM

Performance matters once you cross ~20 items. Decision:

| Operation | Path |
|---|---|
| Single item, interactive (search, get, draft) | MCP tool — clean approval gates, structured returns |
| Bulk read / mark-read / flag / save-as / delete (> 20 items) | Python via `pywin32` directly (`win32com.client`). 50× faster |
| Full-text body search across many emails | Python COM iterator (the MCP `outlook_search_mails` with `scope=subject_body` throws COM error 0x80020009 on some queries) |
| Approval-gated user-facing actions | MCP tool — the trail is visible in conversation |

### Python COM idiom (memorize this shape)

```python
import win32com.client
outlook = win32com.client.Dispatch("Outlook.Application")
ns = outlook.GetNamespace("MAPI")

# By EntryID:
item = ns.GetItemFromID(entry_id)

# Or scan the inbox:
inbox = ns.GetDefaultFolder(6)  # 6 = olFolderInbox
items = inbox.Items
items.Sort("[ReceivedTime]", True)  # newest first
for item in items:
    if item.Class != 43:    # 43 = MailItem
        continue
    ...

# Common writes:
item.UnRead = False; item.Save()
item.FlagStatus = 2; item.FlagRequest = "Follow up"; item.Save()
item.SaveAs(path, 3)         # 3 = olMSG
item.Display()               # opens in Outlook window (does NOT send)
```

Always wrap stdout in `sys.stdout.reconfigure(encoding='utf-8', errors='replace')` — emoji in subjects will crash cp1252 console otherwise.

## Workflow: bulk inbox triage

Used for hundreds-to-thousand unread inboxes. Stage-gated; user approves each tier.

1. **Fetch unread** — `outlook_list_mails(folder='inbox', unread_only=true, limit=100)` paginated. Each ≥100-item response saves to a tool-results file (won't fit inline).
2. **Cluster by sender** — dispatch a subagent to read all page files, aggregate by `from_address`, derive category buckets *from the data* (don't impose preset categories). Output to `~/Desktop/outlook-clusters.json` with senders grouped + `disposition_hint` per category.
3. **Present categories** — show counts + hints. Get user approval before any action. Respect `[[email_geo_vendor_marketing]]` — don't blanket-clear geo cluster.
4. **Importance triage** (action-oriented buckets):
   - `ACTION_NEEDED` — deadline, account risk, expiring quote, ticket needing response, hardware failure
   - `HUMAN_REPLY` — real correspondence to read
   - `FORWARD_TO_ACCOUNTING` — receipts/invoices (per `[[accounting_inbox]]`)
   - `LIVE_WORK` — 811 locates, dig tickets, utility coordination
   - `GEO_VENDOR_KEEP` — industry mail the user reads at leisure
   - `SAFE_TO_MARK_READ` — informational, expired alerts, fluff
   - `LEAVE_ALONE` — borderline phishing kept for user, ambiguous
5. **Bulk mark-read approved buckets** via Python COM (see idiom above). Operations on 500+ emails finish in seconds.
6. **Flag ACTION_NEEDED** with `FlagStatus = 2` + `FlagRequest = "Follow up"` so they cluster in Outlook's flagged view.
7. **Extract unsubscribe URLs** for the bulk-noise senders. Property accessor for the `List-Unsubscribe` header:
   ```python
   PROP = "http://schemas.microsoft.com/mapi/string/{00020386-0000-0000-C000-000000000046}/List-Unsubscribe"
   header = mail.PropertyAccessor.GetProperty(PROP)
   urls = re.findall(r'<(https?://[^>]+)>', header or '')
   ```
   Fallback: scan `HTMLBody` for `href="...unsubscribe..."` patterns.

## Workflow: utility locate .msg archive

Trigger: "archive the locates for [project number or address]".

1. **Find the project folder** — pattern is `\\stahly\PROJECTS\<client>-*\-<job>_*\Survey_GIS_Data\4-Utility_Locates\`. Confirm it exists. If the locate subfolder doesn't exist, ask before creating.
2. **Identify the ticket number** — usually in inbox emails from `mt@occinc.com` with subject `"Ticket: <8-digit-number>"`. If the user gave an address, search for that address in subjects; the ticket # appears in the resulting OCC email body.
3. **Pull every email referencing that ticket #** within a reasonable date window (typically the 30-60 day window around when the ticket was placed). Filter by ticket # in subject + first 3000 chars of body.
4. **Filter to external ticketing senders only** per `[[utility_locate_archiving]]`:
   - Include: `@occinc.com`, `@irth.com`, `roc@chartercom.com`, Montana811, ELM Utility
   - Exclude: Anyone with an Exchange DN sender, anyone `@seaeng.com`, Teams notifications (`no-reply@teams.mail.microsoft`)
5. **SaveAs** each email as `.msg` with filename pattern:
   `YYYY-MM-DD_HHMM_<SenderShort>_<sanitized-subject>.msg`
   - Truncate to ~140 chars total
   - SenderShort: `OCC`, `CenturyLink`, `Charter`, `ELM`, etc.
   - Sanitize: strip `<>:"/\|?*` and collapse whitespace to underscores
6. **Skip-don't-overwrite** existing files. Report saved + skipped counts.

## Workflow: draft receipts to accounting

Trigger: "draft my pending accounting forwards" or "forward this receipt to accounting".

**Per `[[email_send_permission]]` — DRAFTS ONLY. Never call `outlook_send_mail` without explicit per-email user approval.**

1. Identify receipts (SaaS invoices, payment confirmations, expense receipts). Common senders: Supabase `invoice+statements@supabase.com`, Anthropic `invoice+statements@mail.anthropic.com`, Construkted, DocuSign completion notices, parking receipts.
2. For each receipt, call `outlook_send_mail` **with `save_only=true`**:
   - `to`: `stahlyaccounting@seaeng.com`
   - `subject`: `FW: <original subject>` (prefix project number if known: `FW: <proj#> | <orig subj>`)
   - `body`: short prose ("Receipt for [vendor] [amount] — [project# if applicable].")
   - `attachments`: the original email's attachments (download via `outlook_save_attachments` first to a sandbox path, then attach)
   - **Alternative**: use the existing `send-outlook-email` skill's Display-first HTML pattern for full signature preservation.
3. Tell the user where the drafts landed (Drafts folder, count, what to review). They click Send manually.
4. Do not mark the original receipts as read until the user confirms sends — they may want to reference them.

## Workflow: project email lookup

Trigger: "find emails about project 3797-00826" or "what's the email status of [project]".

1. Search by project number in subjects and addresses (`3797-00826`, `1210 9th`, etc.). Use `outlook_search_mails` with `scope='subject'` for stability; the `subject_body` scope hits COM errors on some inboxes.
2. Cross-reference Sent folder too (`folder='sent'`) — half the project trail is outbound.
3. Build a timeline: oldest to newest, columns: date, sender, subject, has_attachments, brief.
4. Highlight any unread items needing action (action-need indicators: deadlines, "DUE", quote-expiring, action-required).

## Workflow: end-of-week inbox snapshot

Trigger: "give me an inbox snapshot" or via `/schedule` cron.

1. Total unread, flagged, drafts.
2. Items still flagged for follow-up older than 7 days.
3. New external project correspondence since last snapshot.
4. Expiring quotes / renewal deadlines in next 14 days (search body for "expire", "renewal", "due by").
5. Write markdown to `~/Desktop/inbox-snapshot-YYYY-MM-DD.md`.

## Subagent patterns

Dispatch a subagent when:
- Importance triage of >100 emails — keeps the body text out of the main context
- Cluster-by-sender across multiple paginated page files — they aggregate; only the clustered output (small) comes back
- Per-email semantic analysis ("which of these need action?")

Prompt template anatomy:
- Hand the subagent **file paths**, not raw data (the tool-results files exceed inline limits)
- Specify the output JSON schema explicitly so you can parse on return
- Cap the printed summary (under 400 words) so the response is itself small
- Pass user-preference reminders verbatim (e.g. "geo vendor marketing is valuable — don't bulk-classify as noise")
- For analysis-only subagents say `"do NOT call any MCP tools; you're analysis-only"` — subagents don't auto-load MCP tools and ToolSearching them from a fresh context wastes time

## Performance numbers (reference)

From real sessions:

**First triage pass (947 unread → 169 unread):**
- 932 emails fetched via paginated MCP calls: ~30s
- Cluster subagent over 10 page files: ~90s
- Bulk mark-read 677 emails via Python COM: **14.5s** (vs ~10 minutes if done via MCP)
- Bulk mark-read 54 SAFE items via Python COM: 1.4s
- Flag 14 ACTION_NEEDED items via Python COM: <1s
- Save 7 .msg files via Python COM: ~3s

**Rules sweep (200 unread → 124 unread in main + 615 items relocated to subfolders):**
- 6 server-side rules executed against existing inbox via `rule.Execute(False, inbox, False, 0)`: ~5s total
- Geo Week News rule moved 125 items; IT moved 239; 811 Locates moved 161; BuildingConnected moved 51; Junk cold marketing moved 35; Junk Panera moved 4

The Python COM bypass is the workhorse. The MCP shines for single-item, interactive, approval-gated work. Server-side rules carry future mail with zero ongoing cost.

## Rule management cheatsheet

```python
# List, modify, run, delete rules via pywin32
import pythoncom, win32com.client
from win32com.client import VARIANT
outlook = win32com.client.Dispatch("Outlook.Application")
ns = outlook.GetNamespace("MAPI")
rules = ns.DefaultStore.GetRules()

# Modify SenderAddress condition (works fine)
for i in range(1, rules.Count + 1):
    r = rules.Item(i)
    if r.Name == "Auto-file 811 Locates":
        v = VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_BSTR, ("@occinc.com", "@irth.com"))
        r.Conditions.SenderAddress.Address = v
        r.Conditions.SenderAddress.Enabled = True
rules.Save(False)

# Run rules on existing inbox (Execute on each rule)
inbox = ns.GetDefaultFolder(6)
for name in ["Auto-file Geo Week News", "Junk Panera receipts", ...]:
    for i in range(1, rules.Count + 1):
        r = rules.Item(i)
        if r.Name == name:
            r.Execute(False, inbox, False, 0)  # ShowProgress, Folder, IncludeSub, Option(0=all/1=read/2=unread)
            break

# Delete by name
for i in range(rules.Count, 0, -1):  # descending so indices don't shift
    if rules.Item(i).Name == "OldRuleName":
        rules.Remove(i)
rules.Save(False)
```

**Creating a new move-to-folder rule via pywin32 will FAIL** (the `Save()` throws "invalid actions or conditions" because the Folder assignment didn't take). Use the OWA browser pattern above. Delete and condition modifications work fine.

## Cross-skill bridges

- `[[send-outlook-email]]` — the lower-level drafting primitive (signature-preserving HTML pattern). For one-off drafts, prefer that skill.
- `[[claude-toolkit]]` — push updates to this skill via `/claude-toolkit push skills/stahly-outlook`.
- AutoCAD work — locate emails parsed via this skill can feed an attribute table generation step. See `[[stahly_cad_environment]]` for CAD conventions.

## Setup verification

The Outlook MCP requires:
- Windows 10/11 with classic Outlook (`OUTLOOK.EXE`), not the new Outlook (`olk.exe`)
- The `outlook-classic-mcp` plugin installed (`/plugin install outlook@outlook-classic-mcp`)
- Restart Claude Code after install so MCP server loads
- Python 3.10+ with `pywin32` for the bulk-COM path

Quick smoke test: `outlook_whoami` → confirms mailbox binding. `outlook_list_folders(max_depth=1)` → confirms folder tree.
