#!/usr/bin/env python
"""Search Claude Code conversation history stored as JSONL session files,
and optionally session-handoff emails archived in an Outlook subfolder."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Optional Outlook handoff support. Loaded lazily — if pywin32 isn't installed
# or Outlook isn't running, handoff search is silently disabled.
HANDOFF_FOLDER_NAME = "Claude Code Sessions"  # subfolder of Inbox

# Noise filters
SYSTEM_REMINDER_RE = re.compile(r"<system-reminder>.*?</system-reminder>", re.DOTALL)
NOISE_TAG_RE = re.compile(
    r"<(?:command-name|command-message|command-args|task-notification|local-command-caveat|"
    r"local-command-stdout)>.*?</(?:command-name|command-message|command-args|task-notification|"
    r"local-command-caveat|local-command-stdout)>",
    re.DOTALL,
)
SKILL_INJECTION_PREFIXES = (
    "# Prime Agent-OS",
    "## Roadmap Dependency Analyzer",
    "# Task List Creation Process",
    "## Update Roadmap Process",
    "## Project Narrative Generator",
    "Base directory for this skill:",
    "# Search Claude Code Conversation History",
    "# Spec Shaping Process",
    "# Spec Writing Process",
    "## Spec Implementation Process",
)
MAX_HUMAN_MSG_LEN = 1500  # Messages longer than this with known prefixes are system injections


@dataclass
class SessionInfo:
    session_id: str
    project: str
    file_path: Path
    timestamp: str = ""
    branch: str = ""
    slug: str = ""
    title: str = ""
    user_messages: list[str] = field(default_factory=list)
    all_messages: list[str] = field(default_factory=list)


@dataclass
class HandoffEmail:
    """A session-handoff email archived in Outlook (Inbox/Claude Code Sessions)."""
    entry_id: str
    session_id: str       # full UUID parsed from body (may be empty if unparsable)
    short_id: str         # 8-char prefix from subject "(session XXXXXXXX)"
    topic: str            # parsed from subject after "Claude Code session: "
    subject: str
    received: str         # ISO yyyy-mm-dd
    hostname: str = ""
    body_text: str = ""


SESSION_ID_RE = re.compile(r"\(session\s+([a-f0-9]{8})\)\s*$", re.IGNORECASE)
SESSION_ID_FULL_RE = re.compile(
    r"Session ID:\s*([a-f0-9-]{36})", re.IGNORECASE
)
HOST_RE = re.compile(r"Host:\s*([A-Z0-9_-]+)", re.IGNORECASE)


def clean_text(text: str) -> str:
    """Strip system-reminder tags and other noise from message text."""
    text = SYSTEM_REMINDER_RE.sub("", text)
    text = NOISE_TAG_RE.sub("", text)
    return text.strip()


def extract_text(content: object) -> str:
    """Extract plain text from JSONL message content (string or list)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                t = item.get("text", "")
                if t:
                    parts.append(t)
        return " ".join(parts)
    return str(content)


def is_noise(text: str, role: str = "user") -> bool:
    """Check if a message is actually a system/skill injection or not useful for search."""
    stripped = text.lstrip()
    if role == "user" and len(text) > MAX_HUMAN_MSG_LEN:
        for prefix in SKILL_INJECTION_PREFIXES:
            if stripped.startswith(prefix):
                return True
    # Pure tag-only messages after cleaning are noise
    return not stripped


def parse_session(file_path: Path, project: str) -> SessionInfo | None:
    """Parse a JSONL session file and extract metadata + messages."""
    session_id = file_path.stem
    # Skip subagent files
    if "subagents" in str(file_path):
        return None

    info = SessionInfo(
        session_id=session_id,
        project=project,
        file_path=file_path,
    )

    try:
        with open(file_path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue

                # Extract metadata from first user message
                if not info.timestamp and obj.get("timestamp"):
                    info.timestamp = obj["timestamp"]
                if not info.branch and obj.get("gitBranch"):
                    info.branch = obj["gitBranch"]
                if not info.slug and obj.get("slug"):
                    info.slug = obj["slug"]

                # Get message content
                msg = obj.get("message", obj)
                role = msg.get("role", obj.get("role", ""))
                content = msg.get("content", obj.get("content", ""))
                text = extract_text(content)
                if not text:
                    continue

                cleaned = clean_text(text)
                if not cleaned:
                    continue

                if is_noise(cleaned, role):
                    continue

                if role == "user":
                    info.user_messages.append(cleaned)
                    if not info.title:
                        info.title = cleaned[:150]
                info.all_messages.append(cleaned)
    except (OSError, PermissionError):
        return None

    if not info.user_messages:
        return None
    return info


def search_sessions(
    sessions: list[SessionInfo],
    keywords: list[str],
    use_or: bool = False,
    all_roles: bool = False,
) -> list[tuple[SessionInfo, float, list[str]]]:
    """Search sessions for keywords, return (session, score, matching_excerpts)."""
    results: list[tuple[SessionInfo, float, list[str]]] = []

    for session in sessions:
        messages = session.all_messages if all_roles else session.user_messages
        combined = "\n".join(messages).lower()

        # Check keyword presence
        keyword_hits = sum(1 for kw in keywords if kw.lower() in combined)

        if use_or and keyword_hits == 0:
            continue
        if not use_or and keyword_hits < len(keywords):
            continue

        # Score: fraction of keywords found * density
        score = keyword_hits / len(keywords)
        # Bonus for density (how many times keywords appear)
        total_hits = sum(combined.count(kw.lower()) for kw in keywords)
        score += min(total_hits / 20.0, 1.0)  # Cap density bonus at 1.0

        # Find matching excerpts
        excerpts: list[str] = []
        for msg in messages:
            msg_lower = msg.lower()
            if any(kw.lower() in msg_lower for kw in keywords):
                excerpt = msg[:400]
                if len(msg) > 400:
                    excerpt += "..."
                excerpts.append(excerpt)
                if len(excerpts) >= 3:
                    break

        results.append((session, score, excerpts))

    results.sort(key=lambda x: x[1], reverse=True)
    return results


def load_handoffs(folder_name: str = HANDOFF_FOLDER_NAME) -> list[HandoffEmail]:
    """Read all handoff emails from the Outlook subfolder via COM.

    Returns an empty list (with a stderr note) if Outlook/pywin32 are unavailable
    or the folder doesn't exist — so callers can skip gracefully.
    """
    try:
        import win32com.client  # noqa: WPS433 — optional dep
    except ImportError:
        print(
            "Note: pywin32 not installed — skipping Outlook handoff search.",
            file=sys.stderr,
        )
        return []

    try:
        outlook = win32com.client.Dispatch("Outlook.Application")
        ns = outlook.GetNamespace("MAPI")
        inbox = ns.GetDefaultFolder(6)  # olFolderInbox
    except Exception as ex:  # noqa: BLE001 — COM throws generic errors
        print(f"Note: Outlook COM unreachable ({ex}); skipping handoff search.", file=sys.stderr)
        return []

    target = None
    for f in inbox.Folders:
        if f.Name == folder_name:
            target = f
            break
    if target is None:
        return []

    out: list[HandoffEmail] = []
    items = target.Items
    items.Sort("[ReceivedTime]", True)  # newest first

    for item in items:
        try:
            if item.Class != 43:  # 43 = MailItem
                continue
            subject = item.Subject or ""
            body = item.Body or ""

            short_id = ""
            m = SESSION_ID_RE.search(subject)
            if m:
                short_id = m.group(1)

            full_id = ""
            m2 = SESSION_ID_FULL_RE.search(body)
            if m2:
                full_id = m2.group(1)

            topic = ""
            if subject.lower().startswith("claude code session:"):
                topic = subject[len("claude code session:"):].strip()
                # Strip "(session XXXXXXXX)" suffix
                topic = SESSION_ID_RE.sub("", topic).strip().rstrip("(").strip()

            hostname = ""
            mh = HOST_RE.search(body)
            if mh:
                hostname = mh.group(1)

            received = ""
            try:
                received = item.ReceivedTime.strftime("%Y-%m-%dT%H:%M:%S")
            except Exception:  # noqa: BLE001
                pass

            out.append(HandoffEmail(
                entry_id=item.EntryID,
                session_id=full_id,
                short_id=short_id,
                topic=topic,
                subject=subject,
                received=received,
                hostname=hostname,
                body_text=body,
            ))
        except Exception:  # noqa: BLE001 — skip malformed item, continue
            continue

    return out


def search_handoffs(
    handoffs: list[HandoffEmail],
    keywords: list[str],
    use_or: bool = False,
) -> list[tuple[HandoffEmail, float, list[str]]]:
    """Search handoff emails for keywords. Same scoring shape as search_sessions."""
    results: list[tuple[HandoffEmail, float, list[str]]] = []

    for h in handoffs:
        combined = (h.subject + "\n" + h.topic + "\n" + h.body_text).lower()
        keyword_hits = sum(1 for kw in keywords if kw.lower() in combined)

        if use_or and keyword_hits == 0:
            continue
        if not use_or and keyword_hits < len(keywords):
            continue

        score = keyword_hits / len(keywords)
        total_hits = sum(combined.count(kw.lower()) for kw in keywords)
        score += min(total_hits / 20.0, 1.0)

        # Build excerpts from body paragraphs that contain any keyword
        excerpts: list[str] = []
        paras = [p.strip() for p in re.split(r"\n\s*\n", h.body_text) if p.strip()]
        for p in paras:
            p_lower = p.lower()
            if any(kw.lower() in p_lower for kw in keywords):
                excerpt = p[:400]
                if len(p) > 400:
                    excerpt += "..."
                excerpts.append(excerpt)
                if len(excerpts) >= 3:
                    break

        results.append((h, score, excerpts))

    results.sort(key=lambda x: x[1], reverse=True)
    return results


def find_projects_dir() -> Path:
    """Find the ~/.claude/projects/ directory."""
    home = Path.home()
    projects = home / ".claude" / "projects"
    if not projects.exists():
        print(f"Error: {projects} not found", file=sys.stderr)
        sys.exit(1)
    return projects


def collect_sessions(
    projects_dir: Path,
    project_filter: str | None = None,
) -> list[SessionInfo]:
    """Collect all sessions, optionally filtered by project name."""
    sessions: list[SessionInfo] = []

    for project_dir in projects_dir.iterdir():
        if not project_dir.is_dir():
            continue

        project_name = project_dir.name
        if project_filter:
            # Normalize hyphens/underscores — CWD may use underscores while
            # Claude's project dirs use hyphens (e.g. Agisoft_Coding vs Agisoft-Coding)
            norm_filter = project_filter.lower().replace("_", "-").replace(" ", "-")
            norm_name = project_name.lower().replace("_", "-").replace(" ", "-")
            if norm_filter not in norm_name:
                continue

        for jsonl_file in project_dir.glob("*.jsonl"):
            session = parse_session(jsonl_file, project_name)
            if session:
                sessions.append(session)

    return sessions


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Search Claude Code conversation history",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  %(prog)s "over-engineer" "code-review"
  %(prog)s "marker detection" --project Agisoft
  %(prog)s "CLAUDE.md" --all-projects --verbose
  %(prog)s "bug" "fix" --any --limit 5""",
    )
    parser.add_argument("keywords", nargs="+", help="Keywords to search for (AND logic by default)")
    parser.add_argument("--project", help="Filter to projects matching this substring")
    parser.add_argument("--all-projects", action="store_true", help="Search all projects")
    parser.add_argument(
        "--user-only",
        action="store_true",
        help="Search only user messages (default: searches all roles)",
    )
    parser.add_argument(
        "--any", dest="use_or", action="store_true", help="Use OR logic instead of AND"
    )
    parser.add_argument("--limit", type=int, default=10, help="Max results (default: 10)")
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Show matching message excerpts"
    )
    parser.add_argument(
        "--no-handoffs",
        action="store_true",
        help="Skip the Outlook handoff-email search (default: search both JSONL + handoffs)",
    )
    parser.add_argument(
        "--handoffs-only",
        action="store_true",
        help="Search ONLY the Outlook handoff-email folder; skip JSONL transcripts",
    )

    args = parser.parse_args()

    projects_dir = find_projects_dir()

    # Default: current project if not --all-projects and no --project
    project_filter = args.project
    if not args.all_projects and not project_filter:
        # Try to infer from CWD
        cwd = Path.cwd().name
        project_filter = cwd

    if args.all_projects:
        project_filter = None

    joiner = " OR " if args.use_or else " AND "
    print(f"Searching for: {joiner.join(args.keywords)}")
    if project_filter:
        print(f"Project filter: {project_filter}")
    print()

    # Gather JSONL session results (unless --handoffs-only)
    jsonl_results: list[tuple[SessionInfo, float, list[str]]] = []
    if not args.handoffs_only:
        sessions = collect_sessions(projects_dir, project_filter)
        all_roles = not args.user_only
        jsonl_results = search_sessions(sessions, args.keywords, args.use_or, all_roles)
        print(f"Scanned {len(sessions)} JSONL sessions")

    # Gather handoff email results (unless --no-handoffs)
    handoff_results: list[tuple[HandoffEmail, float, list[str]]] = []
    if not args.no_handoffs:
        handoffs = load_handoffs()
        if handoffs:
            handoff_results = search_handoffs(handoffs, args.keywords, args.use_or)
            print(f"Scanned {len(handoffs)} handoff emails")

    # Merge tagged results
    merged: list[tuple[str, float, object, list[str]]] = []  # (source, score, info, excerpts)
    for s, score, exc in jsonl_results:
        merged.append(("jsonl", score, s, exc))
    for h, score, exc in handoff_results:
        # Bias: when scores are close, prefer JSONL (live truth over snapshot)
        merged.append(("handoff", score - 0.001, h, exc))
    merged.sort(key=lambda x: x[1], reverse=True)
    merged = merged[: args.limit]

    if not merged:
        print("\nNo matching sessions found.")
        return

    print(f"\nFound {len(merged)} matching results:\n")

    for i, (source, score, info, excerpts) in enumerate(merged, 1):
        if source == "jsonl":
            session = info  # type: ignore[assignment]
            date = session.timestamp[:10] if session.timestamp else "unknown"
            branch = f" [{session.branch}]" if session.branch else ""
            title = session.title[:100] if session.title else "(no title)"
            safe_title = title.encode("ascii", "replace").decode()
            print(f"  {i}. [{date}][jsonl]{branch} score={score:.2f}")
            print(f"     ID: {session.session_id}")
            print(f"     Project: {session.project}")
            print(f"     Title: {safe_title}")
            if session.slug:
                print(f"     Slug: {session.slug}")
        else:
            h = info  # type: ignore[assignment]
            date = h.received[:10] if h.received else "unknown"
            print(f"  {i}. [{date}][handoff] score={score:.2f}")
            if h.session_id:
                print(f"     ID: {h.session_id}")
            elif h.short_id:
                print(f"     ID (short): {h.short_id}")
            if h.hostname:
                print(f"     Host: {h.hostname}")
            topic = (h.topic or h.subject)[:100]
            safe_topic = topic.encode("ascii", "replace").decode()
            print(f"     Topic: {safe_topic}")

        if args.verbose and excerpts:
            print("     Excerpts:")
            for excerpt in excerpts:
                safe = excerpt.encode("ascii", "replace").decode()
                print(f"       > {safe}")
        print()

    print("Resume a session with: claude --resume <session-id>")


if __name__ == "__main__":
    main()
