---
name: search-claude-history
description: "Search Claude Code conversation history across two sources: (1) raw JSONL session transcripts under ~/.claude/projects/, and (2) handoff emails archived in the Outlook subfolder Inbox/Claude Code Sessions. Use when the user wants to find a past conversation, search session history, recall what was discussed, find a specific session by topic, look up outstanding tasks from prior sessions, or asks 'what did we talk about'. Triggers on: search history, find session, past conversation, session search, conversation history, 'did we discuss', 'remember when we', 'what was the state of X', 'outstanding items from last week'."
---

# Search Claude Code Conversation History

Search past Claude Code sessions by keywords with noise filtering and relevance ranking.

Two data sources are searched by default, results merged and tagged:

| Source | What's in it | Strength |
|---|---|---|
| `[jsonl]` | Raw session transcripts in `~/.claude/projects/<project>/<session-id>.jsonl` | Full play-by-play, every message |
| `[handoff]` | Session-handoff emails in Outlook subfolder `Inbox/Claude Code Sessions` (subject `Claude Code session: <topic> (session XXXXXXXX)`) | Curated state at session end — story, current facts, outstanding items |

JSONL is live truth; handoffs are point-in-time snapshots. When scores are close, JSONL ranks first.

## Usage

Run the bundled script:

```bash
python <skill-dir>/scripts/search_sessions.py <keywords...> [flags]
```

### Flags

| Flag | Description |
|------|-------------|
| `--project <name>` | Filter JSONL search to projects matching substring (default: inferred from CWD; underscores/hyphens normalized) |
| `--all-projects` | Search all JSONL projects |
| `--user-only` | Search only user messages in JSONL (default: searches all roles) |
| `--any` | OR logic instead of AND |
| `--limit N` | Max results (default: 10) |
| `-v, --verbose` | Show matching message/body excerpts |
| `--no-handoffs` | Skip the Outlook handoff source; search JSONL only |
| `--handoffs-only` | Search ONLY the Outlook folder; skip JSONL transcripts |

### Search Tips

- **Start with the most unique token you can find** — a project name, job ID, task ID, error code, or specific number will often hit in one shot. One unique keyword beats three generic ones.
  - Good: `"courthouse-ada"`, `"b8498a9"`, `"0.0312"`
  - Bad: `"sweep"`, `"dense"`, `"depth maps"` (too common across sessions)
- If you don't have a unique identifier, use 2-3 specific keywords with AND logic.
- Avoid common words that appear in CLAUDE.md or skill definitions.
- Keywords are matched as substrings (case-insensitive). "code review" matches "code-review".
- **All-roles search (default)** searches both user and assistant messages — finds solutions Claude proposed, not just what the user typed.
- **`--user-only`** restricts to user messages only, useful if results are too noisy or you want to find what the user specifically said.

### Resuming Found Sessions

After finding a session: `claude --resume <session-id>`

### When to lean on handoffs vs JSONL

- **Looking up outstanding work** — search handoffs (`--handoffs-only` if you want only that view). The handoff email's "Outstanding / to revisit" section is the authoritative todo list at the end of each session.
- **Looking for the play-by-play** — use JSONL. Handoffs are curated and skip the iteration.
- **"When did I last work on X"** — both sources. Handoff's `[topic]` field often matches the user's mental name for the work better than the JSONL `title` field (which is just the first user message).
- **A session has no handoff email** — that's fine; many quick sessions don't get a handoff. JSONL is always there.

### Outlook handoff source — operational notes

- Reads from `Inbox/Claude Code Sessions` (configurable via `HANDOFF_FOLDER_NAME` constant in the script). The auto-file rule that puts emails there is named `Auto-file Claude Code sessions` and matches subject containing `Claude Code session:`.
- Uses `pywin32` COM to read the folder. Requires Outlook running on Windows. Falls back gracefully (stderr note, empty list) if pywin32 isn't installed or COM is unreachable.
- Parses `Session ID:`, `Host:`, and the `Claude Code session: <topic> (session XXXXXXXX)` subject pattern. Search runs against the full plain-text body, so any keyword in the story / state / outstanding sections is findable.
- A handoff email from a different host (e.g. another laptop) is still searchable from this machine as long as the mailbox is the same — the `Host:` field tells you where the transcript actually lives.

## Fallback

If the script is unavailable, search manually:

1. Find project dirs: `ls ~/.claude/projects/`
2. Grep JSONL files: `grep -l "keyword" ~/.claude/projects/<project>/*.jsonl`
3. Parse JSON with Python, filtering user messages > 1500 chars (system injections)
4. For handoffs: open Outlook → `Inbox/Claude Code Sessions` and use Outlook's native search bar.
