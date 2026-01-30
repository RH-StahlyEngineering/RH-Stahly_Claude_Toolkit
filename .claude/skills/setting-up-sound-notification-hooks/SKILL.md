---
name: setting-up-sound-notification-hooks
description: Configures Claude Code hooks to play sound notifications when tasks complete or permissions are needed. Use when the user wants audio alerts, sound notifications, chimes, or bell sounds for Claude Code events.
---

# Setting Up Sound Notification Hooks

This skill helps configure Claude Code to play sound notifications when specific events occur, such as task completion or permission prompts.

## When to Use This Skill

Invoke this skill when the user:
- Wants sound notifications when Claude finishes a task
- Asks for audio alerts when permission is needed
- Mentions hooks, sounds, chimes, bells, or notifications
- Wants to know when Claude is waiting for input

## Configuration Location

Hooks are configured in the Claude Code settings file:

| Platform | Path |
|----------|------|
| Windows | `C:\Users\<username>\.claude\settings.json` |
| macOS | `~/.claude/settings.json` |
| Linux | `~/.claude/settings.json` |

## Available Hook Events

| Event | Triggers When |
|-------|---------------|
| `Stop` | Claude finishes a task and stops |
| `Notification` | Various notifications (can filter with `matcher`) |

### Notification Matchers

For `Notification` hooks, use `matcher` to filter:
- `permission_prompt` - Claude needs permission to proceed

## Sound Commands by Platform

### Windows (PowerShell)

```json
{
  "type": "command",
  "command": "powershell -c \"(New-Object Media.SoundPlayer 'C:\\Windows\\Media\\chimes.wav').PlaySync()\"",
  "timeout": 5
}
```

**Available Windows Sounds** (`C:\Windows\Media\`):
- `chimes.wav` - Pleasant completion chime
- `notify.wav` - Soft notification
- `tada.wav` - Celebratory fanfare
- `Windows Notify.wav` - Standard notification
- `Alarm01.wav` through `Alarm10.wav` - Various alarms
- `Ring01.wav` through `Ring10.wav` - Various rings

### macOS (afplay)

```json
{
  "type": "command",
  "command": "afplay /System/Library/Sounds/Glass.aiff",
  "timeout": 5
}
```

**Available macOS Sounds** (`/System/Library/Sounds/`):
- `Glass.aiff` - Soft glass tap
- `Ping.aiff` - Short ping
- `Pop.aiff` - Pop sound
- `Purr.aiff` - Soft purr
- `Submarine.aiff` - Sonar ping
- `Blow.aiff`, `Bottle.aiff`, `Frog.aiff`, `Funk.aiff`, `Hero.aiff`, `Morse.aiff`, `Tink.aiff`

### Linux (paplay/aplay)

```json
{
  "type": "command",
  "command": "paplay /usr/share/sounds/freedesktop/stereo/complete.oga",
  "timeout": 5
}
```

**Common Linux Sound Paths:**
- `/usr/share/sounds/freedesktop/stereo/complete.oga`
- `/usr/share/sounds/freedesktop/stereo/bell.oga`
- `/usr/share/sounds/freedesktop/stereo/message.oga`

## Complete Configuration Examples

### Windows - Full Setup

Add this to `settings.json`:

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "powershell -c \"(New-Object Media.SoundPlayer 'C:\\Windows\\Media\\chimes.wav').PlaySync()\"",
            "timeout": 5
          }
        ]
      }
    ],
    "Notification": [
      {
        "matcher": "permission_prompt",
        "hooks": [
          {
            "type": "command",
            "command": "powershell -c \"(New-Object Media.SoundPlayer 'C:\\Windows\\Media\\notify.wav').PlaySync()\"",
            "timeout": 5
          }
        ]
      }
    ]
  }
}
```

### macOS - Full Setup

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "afplay /System/Library/Sounds/Glass.aiff",
            "timeout": 5
          }
        ]
      }
    ],
    "Notification": [
      {
        "matcher": "permission_prompt",
        "hooks": [
          {
            "type": "command",
            "command": "afplay /System/Library/Sounds/Ping.aiff",
            "timeout": 5
          }
        ]
      }
    ]
  }
}
```

### Linux - Full Setup

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "paplay /usr/share/sounds/freedesktop/stereo/complete.oga",
            "timeout": 5
          }
        ]
      }
    ],
    "Notification": [
      {
        "matcher": "permission_prompt",
        "hooks": [
          {
            "type": "command",
            "command": "paplay /usr/share/sounds/freedesktop/stereo/bell.oga",
            "timeout": 5
          }
        ]
      }
    ]
  }
}
```

## Setup Steps

1. **Open settings file** at the path for your platform (see Configuration Location)

2. **Add the hooks section** using the appropriate example for your OS

3. **Test the sound command** in your terminal first:
   - Windows: `powershell -c "(New-Object Media.SoundPlayer 'C:\Windows\Media\chimes.wav').PlaySync()"`
   - macOS: `afplay /System/Library/Sounds/Glass.aiff`
   - Linux: `paplay /usr/share/sounds/freedesktop/stereo/complete.oga`

4. **Save the file** and restart Claude Code

5. **Verify** by running a simple task - you should hear the sound when it completes

## Customization

### Change the Sound

Replace the sound file path with any `.wav` (Windows), `.aiff` (macOS), or `.oga/.wav` (Linux) file.

### Adjust Timeout

The `timeout` value (in seconds) prevents hung processes. Default of 5 is usually sufficient.

### Add Multiple Sounds

You can chain multiple hooks for the same event:

```json
"Stop": [
  {
    "hooks": [
      { "type": "command", "command": "...", "timeout": 5 },
      { "type": "command", "command": "...", "timeout": 5 }
    ]
  }
]
```

## Troubleshooting

**No sound plays:**
- Test the command directly in terminal
- Check the sound file path exists
- Verify system volume is not muted
- Ensure JSON syntax is valid (no trailing commas)

**Sound cuts off:**
- Increase the `timeout` value
- Use `PlaySync()` on Windows (not `Play()`)

**Permission errors:**
- Check file permissions on the sound file
- On Linux, ensure pulseaudio/pipewire is running

## Validation Checklist

- [ ] Settings file exists at correct path
- [ ] JSON syntax is valid
- [ ] Sound command works in terminal
- [ ] Sound file path is correct for your OS
- [ ] Claude Code restarted after changes
- [ ] Sound plays on task completion
