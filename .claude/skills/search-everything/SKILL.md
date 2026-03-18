---
name: search-everything
description: "Build voidtools Everything search queries and run searches via es.exe CLI. Use when the user asks to find files, search for files by name/size/date/content, build Everything queries, or mentions voidtools/Everything. Also use when Claude needs to locate files on Windows quickly. Triggers: 'find files', 'search everything', 'everything query', 'voidtools', 'locate file', 'search syntax', 'duplicate files', 'large files', 'recent files'."
---

# Everything Search

## Quick Query Building

Everything uses **substring matching by default** — no wildcards needed for partial matches.

| Operator | Meaning | Example |
|----------|---------|---------|
| space | AND | `foo bar` |
| `\|` | OR | `foo\|bar` |
| `!` | NOT | `!temp` |
| `<>` | Group | `<foo bar>\|baz` |
| `""` | Exact | `"my file"` |

## Common Functions

```
ext:py;js;ts          Extensions (semicolon-delimited)
size:>10mb            Size filter (kb/mb/gb)
size:1mb..100mb       Size range
dm:today              Modified today (also: yesterday, thisweek, thismonth)
dc:2024               Created in 2024
path:Agisoft          Path contains "Agisoft"
parent:c:\projects    Direct children only
content:license       Search inside files (slow)
dupe:                 Duplicate filenames
sizedupe:             Duplicate file sizes
pic:                  Image files
width:>1920           Image width
folder: empty:        Empty folders
file: size:0          Empty files
```

Prefix modifiers: `case:` `regex:` `wholeword:` `file:` `folder:`

Comparison: `func:value` `func:>val` `func:<val` `func:start..end`

Full syntax reference: [references/syntax.md](references/syntax.md)

## Scripts

Run directly or import `run_query`/`find_es_exe` from `es_search`.

| Script | Usage | What it does |
|--------|-------|-------------|
| `es_search.py` | `es_search.py "*.py path:Agisoft"` | Run raw Everything query |
| `find_dupes.py` | `find_dupes.py --by size --path C:\Projects` | Find duplicate files |
| `find_large.py` | `find_large.py 100mb --ext zip` | Find large files |
| `find_recent.py` | `find_recent.py --since thisweek --ext py` | Recently modified files |
| `find_by_ext.py` | `find_by_ext.py py,js,ts --path C:\src` | Find by extension |
| `search_content.py` | `search_content.py "license" --ext py` | Search file contents |
| `find_empty.py` | `find_empty.py --type folders` | Find empty files/folders |
| `find_images.py` | `find_images.py --min-width 1920` | Find images by properties |
| `count_by_ext.py` | `count_by_ext.py C:\Projects` | Count files by extension |

All scripts require `es.exe` (Everything CLI). If missing, they print install instructions.

All support `-n` for max results and `--path` for scope (except count_by_ext which takes path as positional).
