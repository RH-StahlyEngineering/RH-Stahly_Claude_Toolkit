#!/usr/bin/env python
"""Search Claude Code conversation history stored as JSONL session files."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

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

    sessions = collect_sessions(projects_dir, project_filter)
    print(f"Scanned {len(sessions)} sessions")

    all_roles = not args.user_only
    results = search_sessions(sessions, args.keywords, args.use_or, all_roles)
    results = results[: args.limit]

    if not results:
        print("\nNo matching sessions found.")
        return

    print(f"Found {len(results)} matching sessions:\n")

    for i, (session, score, excerpts) in enumerate(results, 1):
        date = session.timestamp[:10] if session.timestamp else "unknown"
        branch = f" [{session.branch}]" if session.branch else ""
        title = session.title[:100] if session.title else "(no title)"

        safe_title = title.encode("ascii", "replace").decode()
        print(f"  {i}. [{date}]{branch} score={score:.2f}")
        print(f"     ID: {session.session_id}")
        print(f"     Project: {session.project}")
        print(f"     Title: {safe_title}")
        if session.slug:
            print(f"     Slug: {session.slug}")

        if args.verbose and excerpts:
            print("     Excerpts:")
            for excerpt in excerpts:
                safe = excerpt.encode("ascii", "replace").decode()
                print(f"       > {safe}")
        print()

    print("Resume a session with: claude --resume <session-id>")


if __name__ == "__main__":
    main()
