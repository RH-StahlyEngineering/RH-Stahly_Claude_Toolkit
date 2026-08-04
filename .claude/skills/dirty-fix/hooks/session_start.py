#!/usr/bin/env python3
"""dirty-fix escort hook (SessionStart: startup | clear | compact).

Scans this project's store for SEALED, unconsumed bundles and injects the
handoff. State is derived from files in the bundle -- there is no registry to
desync, and deleting a bundle is a complete uninstall.

Silent and exit 0 when there is nothing to escort. Never blocks a session.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

EXPIRY_DAYS = 7


def emit(text):
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": text,
        }
    }))


def main():
    try:
        import df  # noqa
    except Exception:
        return 0

    start = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path.cwd())

    try:
        bundles = df.list_bundles(start)
    except Exception:
        return 0

    sealed = [b for b in bundles if b["state"] == "SEALED"]
    stalled = [b for b in bundles if b["state"] in ("FRAMING", "REDUCING", "LOOPING", "HARVESTED")]
    if not sealed and not stalled:
        return 0

    lines = []

    for b in sealed:
        spec = Path(b["repo"]) / "acceptance.md"
        if not spec.is_file():
            continue

        stale = ""
        lock = df.read_json(Path(b["repo"]) / "fixture.lock", {}) or {}
        src = lock.get("source")
        if src:
            try:
                p = Path(src)
                if not p.exists():
                    stale = (f"\n  STALE: the production source this fixture came from is gone "
                             f"({src}). Verify the fixture still represents production before "
                             f"trusting the gate.")
                else:
                    import time
                    age_days = (time.time() - spec.stat().st_mtime) / 86400
                    if p.stat().st_mtime > spec.stat().st_mtime:
                        stale = (f"\n  STALE: the production source has changed since this bundle "
                                 f"was sealed. Re-profile before trusting coverage.")
                    elif age_days > EXPIRY_DAYS:
                        stale = (f"\n  AGED: sealed {age_days:.0f} days ago. Confirm the fixture "
                                 f"still represents production.")
            except OSError:
                pass

        if b["sub_spike"]:
            lines.append(
                f"A dirty-fix SUB-SPIKE bundle is sealed: {b['slug']}\n"
                f"  Spec: {spec}\n"
                f"  It was cut mid-implementation. Return to the implementation it came from "
                f"and apply its acceptance checks there. Do NOT start a fresh design cycle "
                f"from it.{stale}")
            continue

        lines.append(
            f"An acceptance bundle from a prior /dirty-fix session is sealed and unconsumed.\n"
            f"\n"
            f"  Bundle: {b['slug']}\n"
            f"  Spec:   {spec}\n"
            f"  Gate:   {Path(b['repo']) / 'check.py'}{stale}\n"
            f"\n"
            f"Read the spec. It specifies a feature by input, output, and machine-checkable\n"
            f"acceptance criteria, and it is the requirements document for this work. Begin\n"
            f"the design/brainstorming phase from it.\n"
            f"\n"
            f"  - Do not read appendix-hacks.md. If you stall, say so and ask first.\n"
            f"  - The spec contains no implementation guidance by design. You are under no\n"
            f"    constraint as to approach.\n"
            f"  - 'What this fixture cannot prove' lists behaviors never exercised. Each is a\n"
            f"    design question to resolve, not an assumption to inherit.\n"
            f"  - The implementation plan's final task MUST run:\n"
            f"        python \"{Path(b['repo']) / 'check.py'}\" --candidate <output>\n"
            f"    Definition of done is exit 0, plus human sign-off on any criteria the spec\n"
            f"    lists as requiring it. Not your reading of the output.\n"
            f"  - When the work is escorted, mark it: df.py consume {b['slug']}")

    for b in stalled:
        lines.append(
            f"A dirty-fix bundle is unfinished: {b['slug']} [{b['state']}]\n"
            f"  Store: {b['store']}\n"
            f"  If /dirty-fix is invoked, resume this one -- do not start a new loop.")

    if lines:
        emit("=== dirty-fix ===\n\n" + "\n\n".join(lines))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)  # a broken escort must never break a session
