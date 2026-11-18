# peer-slash

A Claude Code mod (a plugin with a hooks module) for the Claude desktop app and Claude Code.

When another Claude session sends this session a message whose **first text** is an allowlisted slash command, for example

    /mattpocock-skills:grill-me <args>

the mod runs that command in this session as if you had typed it. This lets a coordinating session start **manual-only skills** (`disable-model-invocation: true`), which a plain message from another session can never trigger on its own.

What the receiving session sees:

1. A grey "Prompt blocked by a hook" row whose details say: `Sent by "<sender session>", not typed by you: running /<command> as a command`. That is the plain-text copy of the message, dropped on purpose so the session does not answer it twice.
2. The command, shown as a typed command.
3. The skill's response.

The sender sees its message as delivered.

## What it allows

The allowlist is `ALLOWED` in `hooks/register.ts`:

- `mattpocock-skills:*`, Matt Pocock's skills plugin
- `peer-slash-canary`, the test skill made by `tools/canary.py`

Built-in commands such as `/clear` or `/compact` are never reachable unless you add them by name. To allow another plugin's skills, add a line such as `/^superpowers:[a-z0-9-]+$/`.

Limits: the command must be the first text in the message, and only one command runs per message.

## Install

Requires the Claude Code CLI (`claude`) on your PATH; the Claude desktop app uses the same plugins.

1. Put this folder at `~/.claude/local-plugins/peer-slash` (on Windows, `C:\Users\<you>\.claude\local-plugins\peer-slash`). With the claude-toolkit skill: `/claude-toolkit pull local-plugins/peer-slash` and choose Global.

   Or with git:

   ```bash
   git clone --depth 1 --filter=blob:none --sparse https://github.com/RH-StahlyEngineering/RH-Stahly_Claude_Toolkit toolkit
   git -C toolkit sparse-checkout set .claude/local-plugins/peer-slash
   ```

   then copy `toolkit/.claude/local-plugins/peer-slash` to `~/.claude/local-plugins/peer-slash`.

2. Register the folder as a local marketplace and install the plugin:

   ```bash
   claude plugin marketplace add ~/.claude/local-plugins/peer-slash
   claude plugin install peer-slash@local-mods
   ```

   (On Windows, use the full path: `claude plugin marketplace add "C:\Users\<you>\.claude\local-plugins\peer-slash"`.)

3. Start new sessions. Sessions already open pick it up only after a restart.

The plugin is read in place from that folder. After editing it, bump `version` in `.claude-plugin/plugin.json` and run `claude plugin update peer-slash@local-mods`.

Check it: `claude plugin list` should show `peer-slash@local-mods`, enabled, read from that folder.

Uninstall: `claude plugin uninstall peer-slash@local-mods`, then `claude plugin marketplace remove local-mods`.

## Testing it (tools/)

A pass/fail test that proves the skill ran as a real command, not through a workaround:

1. `python tools/canary.py create` writes a manual-only test skill `peer-slash-canary` whose only instruction is to reply with a random secret code, and prints that code. Keep the code to yourself.
2. Start a fresh session (the receiver) and tell it not to read any skill files or call the Skill tool.
3. From another session, send the receiver exactly `/peer-slash-canary RUN-<tag>`.
4. Run the checker on the receiver's transcript (`~/.claude/projects/<project>/<session>.jsonl`):

   ```bash
   python tools/check_skill_invocation.py --transcript <receiver.jsonl> --marker RUN-<tag> --skill peer-slash-canary --expect-code <code>
   ```

   Add `--sender-json <sender's desktop session record> --target <receiver session id>` to also check that the sender saw it delivered.

5. `python tools/canary.py remove` deletes the test skill.

PASS needs: a command row and the skill's text loaded by Claude Code, the receiver replying with the secret code, the code appearing nowhere but the skill text, the plain-text copy never reaching the receiver, and no sign the receiver read the skill file itself.
