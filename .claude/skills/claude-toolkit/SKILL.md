---
name: claude-toolkit
description: Sync .claude assets with RH-Stahly_Claude_Toolkit GitHub repo. Pull agents, commands, skills from remote or push local changes.
disable-model-invocation: true
allowed-tools: Read, Write, Bash(gh *), Bash(git *), Bash(mkdir *), Bash(rm *), Bash(cp *), Bash(mktemp *), Bash(cat *), Bash(base64 *), Bash(sha256sum *), AskUserQuestion, Glob
context: conversation
agent: general-purpose
---

# Claude Toolkit Sync

Bidirectional sync between local `.claude` folder and the RH-Stahly_Claude_Toolkit GitHub repository.

## Understanding User Intent

**IMPORTANT:** Users can invoke this skill with natural language. You must interpret their intent and execute the appropriate action. Do NOT require exact command syntax.

**Examples of natural language requests:**
- "push the new skill" → PUSH action, infer path from recent context
- "push it" → PUSH action, infer path from conversation
- "upload my changes" → PUSH action
- "get the pdf skill" → PULL action, path = `skills/pdf`
- "download the meta-agent" → PULL action, path = `agents/meta-agent.md`
- "what's on the remote?" → LIST action
- "show me what skills are available" → LIST action, path = `skills`
- "compare my local changes" → DIFF action
- "sync everything" → SYNC action

**When the path is ambiguous:**
1. Check the conversation context for recently created/modified files
2. If still unclear, use AskUserQuestion to clarify

**When the action is ambiguous:**
1. Default to the most likely action based on context
2. If truly unclear, use AskUserQuestion with options

## Configuration

```
REMOTE_REPO="RH-StahlyEngineering/RH-Stahly_Claude_Toolkit"
REMOTE_BRANCH="master"
REMOTE_BASE=".claude"
GLOBAL_LOCAL_BASE="C:/Users/rharbach/.claude"
PROJECT_LOCAL_BASE=".claude"  # Relative to current working directory
SYNCABLE_FOLDERS="agents commands skills plugins"
```

## Actions

Determine which action to perform based on user intent:

---

### LIST (user wants to see what's on the remote)

List contents of the remote repository's `.claude` folder.

**Steps:**
1. Determine path from user request (e.g., "show me skills" → `skills`, "what's available" → root)
2. Execute API call:
   ```bash
   gh api repos/RH-StahlyEngineering/RH-Stahly_Claude_Toolkit/contents/.claude/$1 \
     --jq '.[] | "\(.type) \(.name)"'
   ```
3. Format output with icons:
   - `dir` → `📁`
   - `file` → `📄`
4. If API returns 404: Report "Path not found in remote repository"

**Output format:**
```
📁 Remote .claude/$1 contents:
─────────────────────────────────
📁 agents
📁 commands
📄 settings.json
📁 skills
```

---

### PULL (user wants to download/get something from remote)

Download file or folder from remote repository to local `.claude`.

**Steps:**
1. **Determine path**: Extract from user request or conversation context. If unclear, use AskUserQuestion to clarify what they want to pull.

2. **Determine type** (file or folder):
   ```bash
   response=$(gh api repos/RH-StahlyEngineering/RH-Stahly_Claude_Toolkit/contents/.claude/$1 2>&1)
   # If response is array → directory, if object with "content" → file
   ```

2.5. **Ask destination** (global vs project):
   Use AskUserQuestion: "Where should this asset be installed?"
   Options:
   - Global (`C:/Users/rharbach/.claude/`) - available in all projects
   - Project (`./.claude/`) - only available in current project

   Set `LOCAL_BASE` accordingly for remaining steps.

3. **Check for conflict**:
   - If local path exists at `$LOCAL_BASE/$1`:
   - Use AskUserQuestion: "Local file/folder already exists. Overwrite?"
   - Options: [Yes - overwrite, No - cancel]

4. **Pull file** (if single file):
   ```bash
   mkdir -p "$(dirname "$LOCAL_BASE/$1")"
   gh api repos/RH-StahlyEngineering/RH-Stahly_Claude_Toolkit/contents/.claude/$1 \
     --jq '.content' | base64 -d > "$LOCAL_BASE/$1"
   ```

5. **Pull folder** (if directory):
   ```bash
   # Get all files recursively
   gh api "repos/RH-StahlyEngineering/RH-Stahly_Claude_Toolkit/git/trees/master?recursive=1" \
     --jq '.tree[] | select(.path | startswith(".claude/'$1'")) | select(.type=="blob") | .path'
   ```
   For each file in the list:
   - Extract relative path (remove `.claude/` prefix)
   - Create parent directory
   - Download file content via API
   - Report progress: "📥 Pulling file 1/N: path/to/file.md"

6. **Handle partial failure**:
   - If any file fails, pause and ask user:
   - "X of Y files pulled successfully. Z files failed. Continue with remaining? (Yes = skip failed, No = stop)"

7. **Report success**: "✅ Successfully pulled $1 to $LOCAL_BASE"

---

### PUSH (user wants to upload/save something to remote)

Upload file or folder from local `.claude` to remote repository.

**Steps:**
1. **Determine path**:
   - Extract from user request (e.g., "push the pdf skill" → `skills/pdf`)
   - Check conversation context for recently created/modified files
   - If user says "push it" or "push the new skill", look back in conversation for what was just created
   - If still unclear, use AskUserQuestion to clarify

2. **Determine source** (global vs project):
   - Check if path exists in project `.claude/$1`
   - Check if path exists in global `C:/Users/rharbach/.claude/$1`
   - If exists in both, use AskUserQuestion: "Found in both locations. Push from?"
     Options:
     - Global (`C:/Users/rharbach/.claude/`)
     - Project (`./.claude/`)
   - If exists in only one, use that location
   - If exists in neither, report: "Local path not found: $1"
   - Set `$LOCAL_BASE` accordingly for remaining steps.

3. **Check for remote conflict**:
   ```bash
   gh api repos/RH-StahlyEngineering/RH-Stahly_Claude_Toolkit/contents/.claude/$1 2>/dev/null
   ```
   If exists and different content, use AskUserQuestion:
   - "Remote file already exists with different content. Overwrite?"
   - Options: [Yes - overwrite remote, No - cancel, Show diff]

4. **Execute git workflow**:
   ```bash
   # Create temp directory
   TEMP_DIR=$(mktemp -d)
   cd "$TEMP_DIR"

   # Clone repo (shallow)
   gh repo clone RH-StahlyEngineering/RH-Stahly_Claude_Toolkit . -- --depth 1

   # Ensure target directory exists
   mkdir -p ".claude/$(dirname "$1")"

   # Copy file(s)
   cp -r "$LOCAL_BASE/$1" ".claude/$1"

   # Commit and push
   git add ".claude/$1"
   git commit -m "Update $1 via claude-toolkit"
   git push origin master

   # Cleanup
   cd /
   rm -rf "$TEMP_DIR"
   ```

5. **Handle push rejection**:
   If `git push` fails with "rejected" or "non-fast-forward":
   - Abort the operation
   - Report: "Push rejected - remote has changes not in local"
   - Use AskUserQuestion with options:
     1. Pull remote changes first, then retry
     2. Force push (overwrite remote)
     3. Abort (investigate manually)

6. **Report success**: "✅ Successfully pushed $1 to remote repository"

---

### DIFF (user wants to compare local vs remote)

Compare local and remote `.claude` contents.

**Steps:**
1. **Determine scope**:
   - If user specifies a path (e.g., "compare my agents"): diff only that path
   - If user says "compare everything" or is vague: diff all syncable folders (agents, commands, skills, plugins)

2. **Build file lists**:
   - Local files: Use `find` or Glob on local path
   - Remote files: Use git trees API
   ```bash
   gh api "repos/RH-StahlyEngineering/RH-Stahly_Claude_Toolkit/git/trees/master?recursive=1" \
     --jq '.tree[] | select(.path | startswith(".claude/")) | select(.type=="blob") | .path'
   ```

3. **Compare each file**:
   For files in syncable folders:
   - **IDENTICAL**: Exists in both, same content (compare SHA hashes)
   - **MODIFIED**: Exists in both, different content
   - **LOCAL_ONLY**: Exists locally but not remote
   - **REMOTE_ONLY**: Exists remote but not locally

4. **Output format**:
   ```
   Diff: .claude/$1
   ═══════════════════════════════════════════════════════════
   Status      │ Path
   ────────────┼──────────────────────────────────────────────
   ✓ IDENTICAL │ agents/meta-agent.md
   ⚡ MODIFIED  │ commands/memo.md
   ← LOCAL     │ agents/custom-agent.md
   → REMOTE    │ skills/new-skill/SKILL.md
   ═══════════════════════════════════════════════════════════

   Summary: 5 identical, 2 modified, 1 local only, 3 remote only
   ```

5. **For MODIFIED files**, offer to show inline diff using AskUserQuestion

---

### SYNC (user wants full bidirectional sync)

Interactive bidirectional sync with conflict resolution.

**Steps:**
1. **Perform full diff** of all syncable folders (agents, commands, skills, plugins)

2. **Present summary**:
   ```
   Sync Analysis
   ═════════════════════════════════════════════
   ← Local only:  3 files  (can push to remote)
   → Remote only: 5 files  (can pull to local)
   ⚡ Modified:    2 files  (conflict - choose version)
   ✓ Identical:   12 files (no action needed)
   ═════════════════════════════════════════════
   ```

3. **Handle LOCAL_ONLY files**:
   Use AskUserQuestion: "Push 3 local-only files to remote?"
   Options: [Yes - push all, No - skip, Select - choose files]

4. **Handle REMOTE_ONLY files**:
   Use AskUserQuestion: "Pull 5 remote-only files to local?"
   Options: [Yes - pull all, No - skip, Select - choose files]

5. **Handle MODIFIED files (conflicts)**:
   For each conflicted file, use AskUserQuestion:
   "File: commands/memo.md has different content locally and remotely"
   Options:
   - Keep local (push to remote)
   - Keep remote (pull to local)
   - Show diff (then re-prompt)
   - Skip (leave both unchanged)

6. **Execute sync operations** based on user choices

7. **Report final summary**:
   ```
   Sync Complete
   ═════════════════════════════════════════════
   Pushed:  3 files
   Pulled:  4 files
   Skipped: 1 file
   Errors:  0
   ═════════════════════════════════════════════
   ```

---

## Error Handling

### Authentication Errors (401)
- Detect auth failure
- Run `gh auth login` interactively
- Retry the operation after successful auth

### Not Found (404)
- Report: "Path not found in remote repository"
- Suggest: "Use `/claude-toolkit list` to see available paths"

### Rate Limit (403)
- Report: "GitHub API rate limit reached"
- Suggest: "Wait 60 seconds and retry"

### Network Errors
- Report: "Network error occurred"
- Suggest: "Check connection and retry"

### Push Rejection
- Abort operation
- Show what's different on remote
- Ask user for resolution (pull first, force push, or abort)

### Partial Failures
- Pause and report progress
- Ask user whether to continue or rollback
- Show consequences of each choice

---

## Sync Scope

**Included** (portable .claude assets):
- `agents/` - Agent definitions
- `commands/` - Slash commands
- `skills/` - Skill packs with all supporting files
- `plugins/` - Plugin configurations

**Excluded** (local/non-portable):
- `settings.json`, `settings.local.json`
- `.credentials.json`
- `cache/`, `file-history/`, `paste-cache/`
- `plans/`, `todos/`, `tasks/`
- `projects/`
- `debug/`, `telemetry/`, `statsig/`
- `history.jsonl`, `stats-cache.json`
- Root-level scripts (`*.ps1`, `*.bat`, `*.sh`)

---

## Examples

**Natural language (preferred):**
```
/claude-toolkit what's on the remote?
/claude-toolkit show me the available skills
/claude-toolkit pull the pdf skill
/claude-toolkit get the meta-agent
/claude-toolkit push the new skill I just created
/claude-toolkit push it
/claude-toolkit upload my changes to commands
/claude-toolkit compare my local vs remote
/claude-toolkit sync everything
```

**Explicit paths (also supported):**
```
/claude-toolkit list
/claude-toolkit list agents
/claude-toolkit pull agents/meta-agent.md
/claude-toolkit pull skills/pdf
/claude-toolkit push commands/new-cmd.md
/claude-toolkit diff
/claude-toolkit diff agents
/claude-toolkit sync
```
