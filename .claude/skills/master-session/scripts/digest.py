"""Turn Claude Code session transcripts into short RH/assistant text digests.

Usage: python digest.py --out DIR local_<id> [local_<id> ...]
Resolves each id to its transcript, keeps RH/assistant text only, writes DIR/<title>.txt.
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

SYSTEM_PREFIXES = ("<system-reminder>", "<local-command", "<command-")
TRUNC_MARK = " [...truncated]"
LIMITS = {"user": 1500, "assistant": 1200}  # chars kept per message, by speaker


def _text(content):
    """RH/assistant text of a message, with system blocks dropped one by one."""
    if isinstance(content, str):
        blocks = [content]
    elif isinstance(content, list):
        blocks = [
            b["text"]
            for b in content
            if isinstance(b, dict) and b.get("type") == "text" and isinstance(b.get("text"), str)
        ]
    else:
        return ""
    kept = (b.strip() for b in blocks)
    return "\n".join(t for t in kept if t and not t.startswith(SYSTEM_PREFIXES))


def _row(raw, limits):
    """One digest line for a transcript line, or None to skip it."""
    entry = json.loads(raw)
    if not isinstance(entry, dict):
        return None
    kind = entry.get("type")
    if kind not in limits or entry.get("isSidechain") or entry.get("isMeta"):
        return None
    message = entry.get("message")
    if not isinstance(message, dict):
        return None
    text = _text(message.get("content"))
    if not text:
        return None
    if len(text) > limits[kind]:
        text = text[: limits[kind]] + TRUNC_MARK
    ts = entry.get("timestamp")
    ts = ts[:16] if isinstance(ts, str) else ""
    return f"[{ts}] {'RH' if kind == 'user' else 'AI'}: {text}"


def _default_sessions_root():
    return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "Claude" / "claude-code-sessions"


def _default_projects_root():
    return Path.home() / ".claude" / "projects"


def session_record(session_id, sessions_root=None):
    """The desktop app's record for a `local_…` id, or None."""
    sessions_root = Path(sessions_root or _default_sessions_root())
    if not session_id.startswith("local_") or not sessions_root.is_dir():
        return None
    for f in sessions_root.rglob(f"{session_id}.json"):
        try:
            record = json.loads(f.read_text(encoding="utf-8", errors="replace"))
        except ValueError:
            continue
        if isinstance(record, dict):
            return record
    return None


def resolve_transcript(session_id, sessions_root=None, projects_root=None, record=None):
    """Transcript path for a `local_…` or CLI session id; None if not found.

    Pass `record` (from session_record) to skip a second lookup.
    """
    projects_root = Path(projects_root or _default_projects_root())
    if record is None:
        record = session_record(session_id, sessions_root) or {}
    cli_id = record.get("cliSessionId") or session_id.removeprefix("local_")
    if not isinstance(cli_id, str) or not projects_root.is_dir():
        return None
    matches = list(projects_root.glob(f"*/{cli_id}.jsonl"))
    if not matches:
        return None
    return max(matches, key=lambda p: p.stat().st_mtime)


def digest_transcript(path, limits=LIMITS):
    rows = []
    with Path(path).open(encoding="utf-8", errors="replace") as f:
        for raw in f:
            try:
                row = _row(raw, limits)
            except ValueError:
                continue
            if row:
                rows.append(row)
    return rows


def _safe_name(title):
    return re.sub(r"[^\w-]+", "_", title).strip("_")[:50] or "session"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ids", nargs="+", help="session ids (local_... or CLI ids)")
    parser.add_argument("--out", required=True, help="folder for <title>.txt digests")
    parser.add_argument("--sessions-root", help="desktop app claude-code-sessions folder")
    parser.add_argument("--projects-root", help="~/.claude/projects folder")
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for sid in args.ids:
        record = session_record(sid, args.sessions_root) or {}
        path = resolve_transcript(sid, args.sessions_root, args.projects_root, record=record)
        if path is None:
            print(f"UNRESOLVED {sid}")
            continue
        title = record.get("title") if isinstance(record.get("title"), str) else sid
        rows = digest_transcript(path)
        target = out / f"{_safe_name(title)}.txt"
        if target.exists():
            target = out / f"{_safe_name(title)}_{sid[-8:]}.txt"
        target.write_text(f"# {title} ({sid})\n" + "\n\n".join(rows) + "\n", encoding="utf-8")
        print(f"OK {sid} -> {target} ({len(rows)} msgs, {sum(map(len, rows)) // 1000}k chars)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
