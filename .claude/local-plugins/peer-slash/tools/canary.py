"""Create or remove the peer-slash canary skill.

The canary is a manual-only personal skill (disable-model-invocation: true) whose only
instruction is to reply with a random secret code. The code exists nowhere but in the
skill's own file, so a session that replies with it must have had the skill's text loaded.

  python canary.py create   -> writes ~/.claude/skills/peer-slash-canary/SKILL.md with a new code,
                               prints the code (give it to the checker, never to the receiver)
  python canary.py remove   -> deletes that skill folder
"""

import secrets
import shutil
import sys
from pathlib import Path

SKILL_DIR = Path.home() / ".claude" / "skills" / "peer-slash-canary"

TEMPLATE = """---
name: peer-slash-canary
description: Test skill for the peer-slash mod. Manual-only.
disable-model-invocation: true
---

This is a test of whether this skill was loaded as a real slash command.

Reply with exactly this line and nothing else:

{code} skill text received
"""


def create():
    code = "CANARY-" + secrets.token_hex(4).upper()
    SKILL_DIR.mkdir(parents=True, exist_ok=True)
    (SKILL_DIR / "SKILL.md").write_text(TEMPLATE.format(code=code), encoding="utf-8")
    print(code)


def remove():
    if SKILL_DIR.exists():
        shutil.rmtree(SKILL_DIR)
        print(f"removed {SKILL_DIR}")
    else:
        print("nothing to remove")


if __name__ == "__main__":
    {"create": create, "remove": remove}.get(sys.argv[1] if len(sys.argv) > 1 else "", lambda: sys.exit(__doc__))()
