---
name: configuring-status-line
description: Configures Claude Code status line settings in settings.json. Use when the user wants to set up, change, copy, or troubleshoot their status line configuration.
---

# Configuring Status Line

This skill helps configure Claude Code's status line settings, including setting up custom commands, copying configurations between machines, and troubleshooting status line issues.

## When to Use This Skill

Invoke this skill when the user:
- Wants to configure their status line
- Needs to copy status line settings to another machine
- Asks about status line options or settings
- Wants to troubleshoot status line issues
- Mentions keywords: status line, statusLine, ccstatusline

## Configuration Location

Status line settings are stored in the Claude Code settings file:

| Platform | Path |
|----------|------|
| Windows | `C:\Users\<username>\.claude\settings.json` |
| macOS | `~/.claude/settings.json` |
| Linux | `~/.claude/settings.json` |

## Status Line Types

### Type 1: Command-Based (Dynamic)

Runs an external command to generate the status line dynamically.

```json
{
  "statusLine": {
    "type": "command",
    "command": "npx ccstatusline@latest"
  }
}
```

**How it works:**
1. Claude Code executes the command
2. Passes session data (model, directory, context usage) as JSON via stdin
3. Command outputs formatted text
4. Text displays as the status line

**Requirements:**
- Node.js and npm must be installed (for npx commands)
- Command must be available in PATH

### Type 2: Static Text

Displays a fixed string.

```json
{
  "statusLine": {
    "type": "text",
    "text": "My Custom Status"
  }
}
```

### Type 3: Disabled

No status line displayed.

```json
{
  "statusLine": {
    "type": "disabled"
  }
}
```

## Setting Up on a New Machine

**Step 1:** Ensure the `.claude` directory exists in your home folder.

**Step 2:** Create or edit `settings.json` in that directory.

**Step 3:** Add the statusLine configuration:

```json
{
  "statusLine": {
    "type": "command",
    "command": "npx ccstatusline@latest"
  }
}
```

**Step 4:** If using a command that requires Node.js, verify installation:
```bash
node --version
npm --version
```

**Step 5:** Restart Claude Code for changes to take effect.

**Step 6:** Configure ccstatusline widgets (see next section).

## Configuring ccstatusline Widgets

The `ccstatusline` package has an interactive TUI for customizing which widgets display and how they appear.

### Running the Configuration TUI

```bash
npx ccstatusline@latest
```

This opens an interactive menu to select and configure widgets.

### Available Context Widgets

| Widget | Display | Example |
|--------|---------|---------|
| Context Length | Raw token count | `Ctx: 29.7k` |
| Context Percentage | Usage as percentage | `Ctx: 35.0%` |
| Context Percentage (usable) | Percentage accounting for 80% auto-compact threshold | `Ctx: 43.8%` |

### Switching Between Percentage and Tokens

If your status line shows tokens (e.g., `29.7k`) but you want percentage (e.g., `35.0%`):

1. Run `npx ccstatusline@latest`
2. Navigate to widget selection
3. Choose **Context Percentage** instead of **Context Length**
4. Press `l` to toggle between usage percentage and remaining percentage
5. Save and exit

The configuration persists after setup.

### Other ccstatusline Features

- **Powerline mode** - Beautiful powerline-style separators
- **Themes** - Built-in color themes
- **Git status** - Shows current branch and repo state
- **Model name** - Displays active Claude model
- **Session duration** - Time elapsed in session

For full documentation: https://github.com/sirmalloc/ccstatusline

## Copying Configuration Between Machines

**Option A: Copy just the statusLine setting**

Add this to the target machine's `settings.json`:
```json
{
  "statusLine": {
    "type": "command",
    "command": "npx ccstatusline@latest"
  }
}
```

**Option B: Copy entire settings.json**

Copy from:
- Windows: `C:\Users\<username>\.claude\settings.json`
- macOS/Linux: `~/.claude/settings.json`

To the same location on the target machine.

**Important:** If copying the entire file, review other settings (permissions, hooks) as they may be machine-specific.

## Troubleshooting

**Status line not appearing:**
- Verify `settings.json` exists and has valid JSON syntax
- Check the statusLine type is not "disabled"
- Restart Claude Code

**Command-based status line shows errors:**
- Verify Node.js is installed (for npx commands)
- Test the command manually in terminal
- Check command is in PATH

**Changes not taking effect:**
- Restart Claude Code after editing settings.json
- Verify JSON syntax is valid (no trailing commas, proper quotes)

**Context shows tokens instead of percentage (or vice versa):**
- Run `npx ccstatusline@latest` to open the configuration TUI
- Select the **Context Percentage** widget instead of **Context Length**
- Save configuration and restart Claude Code

## Validation Checklist

Before completing status line configuration:

- [ ] Settings file exists at correct path
- [ ] JSON syntax is valid
- [ ] statusLine object has required fields (type, and command/text if applicable)
- [ ] Required dependencies installed (Node.js for npx)
- [ ] Claude Code restarted to apply changes
- [ ] Status line displays correctly

## Example: Full Settings File

```json
{
  "statusLine": {
    "type": "command",
    "command": "npx ccstatusline@latest"
  }
}
```

This minimal configuration sets up a dynamic status line using the ccstatusline npm package.
