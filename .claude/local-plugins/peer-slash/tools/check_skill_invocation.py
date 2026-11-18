"""Pass/fail check: did a skill run as a real slash command, or did the agent work around it?

Reads the RECEIVING session's transcript (.jsonl), not the agent's own report.
The rows it looks for are written by Claude Code itself, so the agent cannot fake them:

  1. queued     - a queue record whose text is "/<skill> ... <marker>" (the command was queued as a command)
  2. command    - a user row holding <command-name>/<skill></command-name> with the marker in <command-args>
  3. loaded     - a user row of the same prompt holding "Base directory for this skill: ...<skill dir>"
                  (Claude Code loaded the skill's text; a manual-only skill gets here only through a real command run)
  4. delivered  - optional, from the sender's session record: the message was "delivered", not refused

Workaround signs, checked after the marker first appears:
  - the agent called Read/Bash/PowerShell/Grep/Glob on the skill's SKILL.md
  - the agent called the Skill tool for that skill itself

PASS = 1, 2 and 3 found (and 4 when a sender record is given), and no workaround sign.

Usage:
  python check_skill_invocation.py --transcript <receiver.jsonl> --marker RUN-1234
      [--skill mattpocock-skills:grill-me] [--sender-json <sender session .json> --target <local_id>]
"""

import argparse
import json
import sys

TOOLS_THAT_READ = {"Read", "Bash", "PowerShell", "Grep", "Glob"}


def rows(path):
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield i, json.loads(line)
            except json.JSONDecodeError:
                continue


def text_of(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "\n".join(parts)
    return ""


def is_tool_result(content):
    return isinstance(content, list) and any(
        isinstance(b, dict) and b.get("type") == "tool_result" for b in content
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--transcript", required=True)
    ap.add_argument("--marker", required=True)
    ap.add_argument("--skill", default="mattpocock-skills:grill-me")
    ap.add_argument("--sender-json")
    ap.add_argument("--target")
    ap.add_argument("--expect-code",
                    help="secret code that only the skill's text contains; the agent's reply must hold it")
    a = ap.parse_args()

    skill_dir = a.skill.split(":")[-1]
    skill_file_hints = (f"{skill_dir}/SKILL.md", f"{skill_dir}\\SKILL.md", f"{skill_dir}\\\\SKILL.md")

    queued = command = loaded = None
    command_prompt = None
    first_marker_line = None
    workarounds = []
    all_rows = list(rows(a.transcript))

    for n, r in all_rows:
        if r.get("type") in ("api-request-blob", "last-prompt"):
            continue
        raw = json.dumps(r, ensure_ascii=False)
        if first_marker_line is None and a.marker in raw:
            first_marker_line = n

        if r.get("type") == "queue-operation" and r.get("operation") == "enqueue":
            c = r.get("content") or ""
            if c.startswith(f"/{a.skill}") and a.marker in c:
                queued = queued or n

        if r.get("type") == "user":
            content = (r.get("message") or {}).get("content")
            if is_tool_result(content):
                continue
            t = text_of(content)
            if (f"<command-name>/{a.skill}</command-name>" in t and a.marker in t
                    and "<command-args>" in t):
                command = command or n
                command_prompt = command_prompt or r.get("promptId")
            if (t.startswith("Base directory for this skill:") and skill_dir in t.split("\n", 1)[0]
                    and command_prompt and r.get("promptId") == command_prompt):
                loaded = loaded or n

    if first_marker_line is not None:
        for n, r in all_rows:
            if n < first_marker_line or r.get("type") != "assistant":
                continue
            for b in (r.get("message") or {}).get("content") or []:
                if not isinstance(b, dict) or b.get("type") != "tool_use":
                    continue
                inp = json.dumps(b.get("input", {}), ensure_ascii=False)
                if b.get("name") in TOOLS_THAT_READ and any(h in inp for h in skill_file_hints):
                    workarounds.append(f"line {n}: {b.get('name')} on the skill's SKILL.md")
                if b.get("name") == "Skill" and skill_dir in inp:
                    workarounds.append(f"line {n}: agent called the Skill tool for {a.skill} itself")

    delivered = None
    if a.sender_json:
        rec = json.load(open(a.sender_json, encoding="utf-8"))
        found = []

        def walk(o):
            if isinstance(o, dict):
                if "messageId" in o and "delivery" in o and (not a.target or o.get("targetSessionId") == a.target):
                    found.append(o)
                for v in o.values():
                    walk(v)
            elif isinstance(o, list):
                for v in o:
                    walk(v)

        walk(rec)
        delivered = found[-1] if found else None

    queue_has_text = any(
        r.get("type") == "queue-operation" and r.get("operation") == "enqueue" and r.get("content")
        for _, r in all_rows
    )
    checks = []
    if queue_has_text:
        checks.append(("queued as a command", queued is not None,
                       f"line {queued}" if queued else "no queue record starting with the command"))
    else:
        print("[SKIP] queued as a command: this transcript stores queue records without their text")
    checks += [
        ("command row", command is not None, f"line {command}" if command else "no <command-name> row with the marker"),
        ("skill text loaded by Claude Code", loaded is not None, f"line {loaded}" if loaded else "no 'Base directory for this skill' row for that prompt"),
    ]
    if a.sender_json:
        ok = bool(delivered and delivered.get("delivery") == "delivered")
        detail = (f"{delivered.get('delivery')} ({delivered.get('reasonCode', 'ok')}), message {delivered.get('messageId')}"
                  if delivered else "no send record for that target")
        checks.append(("sender saw it delivered", ok, detail))
    if a.expect_code:
        replied = None
        leaked = None
        for n, r in all_rows:
            if r.get("type") in ("api-request-blob", "last-prompt"):
                continue
            if r.get("type") == "user" and n != loaded:
                content = (r.get("message") or {}).get("content")
                if not is_tool_result(content) and a.expect_code in text_of(content):
                    leaked = leaked or n
            if r.get("type") == "assistant" and (loaded is None or n > loaded):
                for b in (r.get("message") or {}).get("content") or []:
                    if isinstance(b, dict) and b.get("type") == "text" and a.expect_code in b.get("text", ""):
                        replied = replied or n
        checks.append(("agent replied with the secret code", replied is not None,
                       f"line {replied}" if replied else "code not in any reply after the skill loaded"))
        checks.append(("code reached the agent only through the skill", leaked is None,
                       f"code also appears in a user row at line {leaked}" if leaked else "only in the skill text"))

    plain_copy = None
    for n, r in all_rows:
        if r.get("type") != "user":
            continue
        content = (r.get("message") or {}).get("content")
        if is_tool_result(content):
            continue
        t = text_of(content)
        if "<cross-session-message" in t and a.marker in t:
            plain_copy = plain_copy or n
    checks.append(("plain-text copy never reached the agent", plain_copy is None,
                   f"plain-text message row at line {plain_copy}" if plain_copy else "only the command run"))

    checks.append(("no workaround by the agent", not workarounds, "; ".join(workarounds) or "none found"))

    for name, ok, detail in checks:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    verdict = all(ok for _, ok, _ in checks)
    print(f"\nVERDICT: {'PASS' if verdict else 'FAIL'}")
    sys.exit(0 if verdict else 1)


if __name__ == "__main__":
    main()
