---
name: search-claude-history
description: "Search Claude Code conversation history stored in ~/.claude/projects/ JSONL session files. Use when the user wants to find a past conversation, search session history, recall what was discussed, find a specific session by topic, or asks 'what did we talk about'. Triggers on: search history, find session, past conversation, session search, conversation history, 'did we discuss', 'remember when we'."
---

# Search Claude Code Conversation History

Search past Claude Code sessions by keywords with noise filtering and relevance ranking.

## Usage

Run the bundled script:

```bash
python <skill-dir>/scripts/search_sessions.py <keywords...> [flags]
```

### Flags

| Flag | Description |
|------|-------------|
| `--project <name>` | Filter to projects matching substring (default: inferred from CWD; underscores/hyphens normalized) |
| `--all-projects` | Search all projects |
| `--user-only` | Search only user messages (default: searches all roles) |
| `--any` | OR logic instead of AND |
| `--limit N` | Max results (default: 10) |
| `-v, --verbose` | Show matching message excerpts |

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

## Fallback

If the script is unavailable, search manually:

1. Find project dirs: `ls ~/.claude/projects/`
2. Grep JSONL files: `grep -l "keyword" ~/.claude/projects/<project>/*.jsonl`
3. Parse JSON with Python, filtering user messages > 1500 chars (system injections)
