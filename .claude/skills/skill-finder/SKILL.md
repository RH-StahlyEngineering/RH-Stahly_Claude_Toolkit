---
name: skill-finder
description: Search across all Claude Code skills installed anywhere on the system - user-global, project-local, and bundled inside plugins (active and marketplace cache). Use when the user asks "what skills do I have for X", "find skills related to Y", "list skills that do Z", or wants to discover skills by topic/intent. Returns name, location, description, source type, and invocation syntax for matching skills. Make sure to use this skill whenever the user wants to discover, list, or search skills they may already have installed - it surfaces hidden plugin-bundled skills that aren't visible from the / menu.
disable-model-invocation: true
allowed-tools: Read, Glob, Grep, Bash
---

# Skill Finder

Local "Everything"-style search across every Claude Code skill installed on this machine, including skills bundled inside plugins that may not be visible from the `/` menu.

## When to use this skill

The user has invoked `/skill-finder`, optionally with a search term. Examples of intent:

- "What skills do I have for LiDAR?"
- "Find skills related to point clouds."
- "List all skills that work with PDFs."
- "What skills are bundled in plugins I have installed?"
- "Show me everything." (no filter — list all)

This skill is read-only. It does NOT invoke matching skills. It only reports them with their location, description, and invocation syntax.

## How to run

### Step 1 — Discover skills

Execute the parser script:

```bash
python "$HOME/.claude/skills/skill-finder/scripts/parse_skill.py"
```

The script walks four standard skill locations and emits a JSON array to stdout. Each entry has these fields:

- `name` — skill name (from frontmatter, falls back to parent directory name)
- `description` — full description from frontmatter
- `path` — absolute path to `SKILL.md`
- `source_type` — one of: `active_global`, `active_project`, `plugin`, `marketplace_listing`
- `plugin` — plugin namespace if applicable (else `null`)
- `marketplace` — marketplace name if the skill came from a marketplace install or listing (else `null`)
- `invocation` — slash-command form (`/skill-name` or `/plugin:skill-name`)
- `body_preview` — first 1000 characters of the body (used for content search)

### Step 2 — Filter (if the user provided a search term)

Match the term against `name`, `description`, and `body_preview` fields, case-insensitive.

- Multiple terms — match all (AND logic): `lidar processing` matches entries containing both "lidar" AND "processing".
- Quoted phrases — match the exact substring: `"point cloud"` matches the literal phrase.
- No filter — return everything.

If no matches are found, suggest 2–3 adjacent search terms based on what was found in the full set, and ask if the user wants to broaden the search.

### Step 3 — Format output

Group results by `source_type` in this order: `active_global`, `active_project`, `plugin`, `marketplace_listing`. Use the headers below verbatim. For each skill, show a one-line summary plus invocation and path.

```
=== Active Global (~/.claude/skills/) ===
- [skill-name] — first 150 chars of description
  Invoke: /skill-name
  Path: <absolute path>

=== Active Project (./.claude/skills/) ===
- [skill-name] — ...
  Invoke: /skill-name
  Path: ...

=== Plugins (installed) ===
- [plugin-name:skill-name] — ...
  Invoke: /plugin-name:skill-name
  Path: ...

=== Marketplace Cache (not necessarily installed) ===
- [plugin-name:skill-name] — ...
  Status: cached, may need install
  Path: ...
```

### Step 4 — Summary line

End with a count summary:

```
Found N skills (G global, P project, X in plugins, M in marketplace cache).
```

## Important rules

- **Never invoke any matching skill.** This is a discovery tool, not an execution tool. List, don't run.
- **Skip `skill-finder` itself** in the output, or clearly mark it as "(this skill)" if listing everything. Don't recurse.
- **Marketplace cache entries are not active.** Clearly distinguish them from installed plugin skills. The user may need to run `/plugin install <plugin>@<marketplace>` to enable them.
- **Plugin invocation syntax uses a colon namespace.** Use `/plugin:skill-name`, not `/skill-name`, for any skill found under `~/.claude/plugins/`.
- **Truncate descriptions in the summary view.** Use the first 150 characters followed by `…` if longer. The user can re-query with the skill name to read full content.
- **Fallback if Python or PyYAML are missing.** If the script fails to run, fall back to using `Glob` to list all `SKILL.md` files in the four locations, then `Read` each to extract the `name` and `description` from frontmatter manually. PyYAML is preferred but not strictly required.

## Search examples

| User input | Behavior |
|---|---|
| `/skill-finder lidar` | Match any skill containing "lidar" |
| `/skill-finder pdf forms` | Match skills containing both "pdf" AND "forms" |
| `/skill-finder "point cloud"` | Match the exact phrase "point cloud" |
| `/skill-finder` | List all skills grouped by source |

## Locations searched

| Source | Path | Source type |
|---|---|---|
| User-global skills | `~/.claude/skills/<name>/SKILL.md` | `active_global` |
| Project-local skills | `<cwd>/.claude/skills/<name>/SKILL.md` | `active_project` |
| Installed plugin skills | `~/.claude/plugins/cache/<mkt>/<plugin>/<version>/skills/<name>/SKILL.md` | `plugin` |
| Marketplace listings | `~/.claude/plugins/marketplaces/<mkt>/[plugins/<plugin>/]skills/<name>/SKILL.md` | `marketplace_listing` |

The `cache/` path is what's actually invocable — installed plugins are unpacked there. The `marketplaces/` path is the marketplace's own listing of what it offers; entries there may or may not be installed. The parser de-duplicates by resolved absolute path.
