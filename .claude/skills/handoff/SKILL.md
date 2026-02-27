---
name: handoff
description: Hand off rich session context between Claude Code sessions. Use "give" to save, "take" to load.
argument-hint: <give|take> [notes]
disable-model-invocation: true
allowed-tools: [Read, Write, Edit, Bash, Glob, Grep, AskUserQuestion]
---

# Handoff — Transfer Context Between Sessions

You manage handoffs of rich session context between Claude Code sessions.

## Subcommand Resolution

Parse `$ARGUMENTS[0]` for the subcommand:
- If `$ARGUMENTS[0]` is **"give"** → run the Give workflow
- If `$ARGUMENTS[0]` is **"take"** → run the Take workflow
- If **no argument provided** → infer from context:
  - If this session has done meaningful work (modified files, commits, task progress) → assume **give**
  - If this is a fresh session with no prior work → assume **take**
  - If ambiguous → ask the user with `AskUserQuestion`

---

## Give Workflow

**Goal:** Capture the current session's full context into a rich handoff file that lets the next session start immediately without re-exploring.

### Step 1: Gather Context Automatically

Run these in parallel:
- `git branch --show-current`
- `git status --short`
- `git log -10 --oneline`
- `git diff --stat` (unstaged changes summary)
- `git diff --cached --stat` (staged changes summary)
- Check for any active task list

### Step 2: Notes

If `$ARGUMENTS[1+]` were provided, use them as the user's notes section. If not provided, skip notes — do NOT prompt for them.

### Step 3: Build the Handoff File

Write to `.claude/handoffs/HANDOFF-{YYYY-MM-DD}-{HHmmss}-{branch}.md` with this structure:

```markdown
# Handoff: {branch} — {date}

## Branch & Git State
- **Branch:** {branch}
- **Status:**
{git status output}
- **Recent Commits:**
{last 10 commits}
- **Uncommitted Changes:**
{diff stat for staged + unstaged}

## What Was Done
{Summarize the work completed in this session — be specific about what changed and why.
Include function names, file paths, and behavioral changes.}

## What's Next
{Remaining tasks, open questions, known issues. Be specific enough that the next session
can pick up without asking "where were we?"}

## Key Files & Code
{For each important file touched or discussed, include:
- The file path
- The relevant code verbatim (entire functions/classes if they're central to the work)
- Brief annotation of what this code does and why it matters}

## Decision History
{What approaches were considered? What was ruled out and why?
What constraints or user preferences shaped the decisions?}

## User Notes
{Contents of $ARGUMENTS[1+], or omit this section if none provided}
```

**Important:** Be generous with code inclusion. The next session should have ~20% of its context pre-loaded with useful material. Include full function bodies, not just file paths. Include type definitions, config snippets, test examples — anything the next session would otherwise spend turns reading.

### Step 4: Confirm

Print the full path to the handoff file:
```
Handoff saved to: .claude/handoffs/HANDOFF-{name}.md
```

---

## Take Workflow

**Goal:** Load a previously saved handoff and absorb its context, then move it to the `taken/` archive.

### Step 1: Find Available Handoffs

Glob for `.claude/handoffs/HANDOFF-*.md` (do NOT include files in the `taken/` subdirectory).

### Step 2: Select

- **0 found** → Report: "No handoffs available in `.claude/handoffs/`"
- **1 found** → Use it directly, no confirmation needed
- **>1 found** → List all available handoffs showing filename, date, and branch. Use `AskUserQuestion` to let the user choose. This confirmation is **required**, not optional.

### Step 3: Load

Read the selected handoff file and present its contents. Treat this as your session context — you now know the branch state, what was done, what's next, the key code, and the decision history.

### Step 4: Archive

Move the consumed handoff file to `.claude/handoffs/taken/`:
```bash
mv .claude/handoffs/HANDOFF-{name}.md .claude/handoffs/taken/
```

### Step 5: Confirm

Print:
```
Handoff loaded and archived to: .claude/handoffs/taken/HANDOFF-{name}.md
Ready to continue where the previous session left off.
```

Then briefly summarize what you absorbed: the branch, what was done, and what's next.
