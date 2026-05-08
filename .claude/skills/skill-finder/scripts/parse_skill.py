#!/usr/bin/env python3
"""Walk all known Claude Code skill locations and emit structured JSON to stdout.

Locations searched:
  ~/.claude/skills/<name>/SKILL.md                                      -> active_global
  <cwd>/.claude/skills/<name>/SKILL.md                                  -> active_project
  ~/.claude/plugins/<plugin>/skills/<name>/SKILL.md                     -> plugin
  ~/.claude/plugins/marketplaces/<mkt>/plugins/<plugin>/skills/<name>/SKILL.md -> marketplace_cache

Output: JSON array of {name, description, path, source_type, plugin, invocation, body_preview}.
"""

import json
import sys
from pathlib import Path

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


def parse_frontmatter(text):
    """Return (frontmatter_dict, body_str). Empty dict if no frontmatter."""
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    fm_text = parts[1]
    body = parts[2]
    if HAS_YAML:
        try:
            data = yaml.safe_load(fm_text) or {}
            if not isinstance(data, dict):
                data = {}
        except yaml.YAMLError:
            data = _fallback_parse(fm_text)
    else:
        data = _fallback_parse(fm_text)
    return data, body


def _fallback_parse(fm_text):
    """Minimal parser for top-level key: value pairs when PyYAML is unavailable."""
    data = {}
    current_key = None
    for raw in fm_text.splitlines():
        line = raw.rstrip()
        if not line or line.startswith("#"):
            continue
        if line.startswith(" ") and current_key:
            data[current_key] = data[current_key] + " " + line.strip()
            continue
        if ":" in line:
            k, _, v = line.partition(":")
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            data[k] = v
            current_key = k
    return data


def is_under(child: Path, parent: Path) -> bool:
    """Compatibility wrapper for Path.is_relative_to (Python 3.9+) and older."""
    try:
        return child.resolve().is_relative_to(parent.resolve())
    except AttributeError:
        try:
            child.resolve().relative_to(parent.resolve())
            return True
        except ValueError:
            return False
    except ValueError:
        return False


def classify(skill_path: Path, home: Path, cwd: Path):
    """Determine (source_type, plugin, marketplace) for a SKILL.md path.

    Layouts recognized (under ~/.claude/plugins/):
      cache/<mkt>/<plugin>/<version>/skills/<skill>/SKILL.md     -> plugin (installed)
      marketplaces/<mkt>/skills/<skill>/SKILL.md                 -> marketplace_listing
      marketplaces/<mkt>/plugins/<plugin>/skills/<skill>/SKILL.md -> marketplace_listing
    """
    home_skills = home / ".claude" / "skills"
    project_skills = cwd / ".claude" / "skills"
    plugins_root = home / ".claude" / "plugins"
    cache_root = plugins_root / "cache"
    marketplaces_root = plugins_root / "marketplaces"

    if is_under(skill_path, project_skills):
        return "active_project", None, None

    if is_under(skill_path, home_skills):
        return "active_global", None, None

    if is_under(skill_path, cache_root):
        try:
            parts = skill_path.resolve().relative_to(cache_root.resolve()).parts
        except ValueError:
            return "plugin", None, None
        marketplace = parts[0] if len(parts) > 0 else None
        plugin = parts[1] if len(parts) > 1 else None
        return "plugin", plugin, marketplace

    if is_under(skill_path, marketplaces_root):
        try:
            parts = skill_path.resolve().relative_to(marketplaces_root.resolve()).parts
        except ValueError:
            return "marketplace_listing", None, None
        marketplace = parts[0] if len(parts) > 0 else None
        plugin = None
        if len(parts) > 2 and parts[1] == "plugins":
            plugin = parts[2]
        return "marketplace_listing", plugin, marketplace

    return "unknown", None, None


def build_invocation(name: str, plugin):
    if plugin:
        return f"/{plugin}:{name}"
    return f"/{name}"


def discover():
    home = Path.home()
    cwd = Path.cwd()
    roots = [
        home / ".claude" / "skills",
        cwd / ".claude" / "skills",
        home / ".claude" / "plugins",
    ]
    seen = set()
    skills = []
    for root in roots:
        if not root.exists():
            continue
        for skill_md in root.rglob("SKILL.md"):
            try:
                resolved = skill_md.resolve()
            except OSError:
                continue
            if resolved in seen:
                continue
            seen.add(resolved)
            try:
                text = skill_md.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            fm, body = parse_frontmatter(text)
            source_type, plugin, marketplace = classify(skill_md, home, cwd)
            name = fm.get("name") or skill_md.parent.name
            desc = fm.get("description", "") or ""
            if isinstance(desc, list):
                desc = " ".join(str(x) for x in desc)
            skills.append({
                "name": str(name),
                "description": str(desc),
                "path": str(skill_md),
                "source_type": source_type,
                "plugin": plugin,
                "marketplace": marketplace,
                "invocation": build_invocation(str(name), plugin),
                "body_preview": body[:1000].strip(),
            })
    return skills


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    skills = discover()
    json.dump(skills, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
