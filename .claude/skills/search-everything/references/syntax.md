# Everything Search Syntax Cheat Sheet

Reference for voidtools Everything (https://www.voidtools.com) query syntax.

## Operators

| Syntax        | Meaning                              | Example                    |
|---------------|--------------------------------------|----------------------------|
| `space`       | AND (both terms must match)          | `foo bar`                  |
| `\|`          | OR (either term matches)             | `foo \| bar`               |
| `!`           | NOT (exclude term)                   | `foo !bar`                 |
| `< >`         | Grouping                             | `<foo \| bar> baz`         |
| `" "`         | Exact phrase / literal string        | `"hello world"`            |

Note: Substring matching is the default. Searching `report` matches `quarterly_report_v2.docx`.

## Wildcards

| Syntax | Meaning              | Example                          |
|--------|----------------------|----------------------------------|
| `*`    | Zero or more chars   | `*.txt` matches any `.txt` file  |
| `?`    | Exactly one char     | `file?.log` matches `file1.log`  |

Wildcards are unnecessary for simple substring searches. Use them when you need anchoring or pattern control.

## File Type Macros

| Macro      | Matches                                              |
|------------|------------------------------------------------------|
| `audio:`   | aac, flac, mp3, ogg, wav, wma, ...                  |
| `zip:`     | 7z, bz2, gz, rar, tar, zip, ...                     |
| `doc:`     | csv, doc, docx, odt, pdf, pptx, txt, xls, xlsx, ... |
| `exe:`     | bat, cmd, exe, msi, msp, scr, ...                   |
| `pic:`     | bmp, gif, ico, jpg, jpeg, png, svg, tif, webp, ...  |
| `video:`   | avi, flv, mkv, mov, mp4, mpg, webm, wmv, ...        |

## Modifiers

Modifiers change how the search is interpreted. Prefix with `no` to disable.

| Modifier       | Effect                              | Negation          |
|----------------|-------------------------------------|--------------------|
| `case:`        | Case-sensitive matching             | `nocase:`          |
| `file:`        | Match files only                    | `folder:`          |
| `folder:`      | Match folders only                  | `file:`            |
| `path:`        | Match against full path             | `nopath:`          |
| `regex:`       | Enable regex mode                   | `noregex:`         |
| `wholeword:`   | Match whole words only              | `nowholeword:`     |
| `wildcards:`   | Enable wildcard mode                | `nowildcards:`     |
| `diacritics:`  | Diacritic-sensitive matching        | `nodiacritics:`    |

Usage: place modifier before the search term, e.g. `case:README`.

## Functions

### Size

| Syntax              | Meaning                          |
|---------------------|----------------------------------|
| `size:1mb`          | Exactly 1 MB                     |
| `size:>100kb`       | Greater than 100 KB              |
| `size:1mb..10mb`    | Between 1 MB and 10 MB           |

Suffixes: `kb`, `mb`, `gb`, `tb`.

| Constant    | Range          |
|-------------|----------------|
| `empty`     | 0 KB           |
| `tiny`      | 0 - 10 KB      |
| `small`     | 10 - 100 KB    |
| `medium`    | 100 KB - 1 MB  |
| `large`     | 1 - 16 MB      |
| `huge`      | 16 - 128 MB    |
| `gigantic`  | > 128 MB       |

### Dates

| Function | Field         |
|----------|---------------|
| `dm:`    | Date modified  |
| `dc:`    | Date created   |
| `da:`    | Date accessed  |

Date formats: `YYYY`, `YYYY-MM`, `YYYY-MM-DD`. Ranges use `..` separator.

| Constant      | Meaning              |
|---------------|----------------------|
| `today`       | Today                |
| `yesterday`   | Yesterday            |
| `thisweek`    | Current week         |
| `lastweek`    | Previous week        |
| `thismonth`   | Current month        |
| `lastmonth`   | Previous month       |
| `thisyear`    | Current year         |
| `lastyear`    | Previous year        |

Example: `dm:2024-01..2024-06` matches files modified Jan-Jun 2024.

### Path / Location

| Function   | Meaning                                       | Example                          |
|------------|-----------------------------------------------|----------------------------------|
| `parent:`  | Direct children of folder (non-recursive)     | `parent:C:\Projects`             |
| `path:`    | Substring match against full path             | `path:node_modules`              |
| `child:`   | Folders containing a matching child file      | `child:package.json`             |
| `root:`    | Files/folders at root of a drive              | `root:`                          |
| `depth:`   | Limit results by folder depth                 | `depth:2..5`                     |

### Extension

| Function | Meaning                            | Example              |
|----------|------------------------------------|----------------------|
| `ext:`   | Match file extension(s), `;`-delimited | `ext:py;js;ts`  |

### Content (slow -- searches file contents)

| Function          | Encoding          |
|-------------------|--------------------|
| `content:`        | Auto-detect        |
| `ansicontent:`    | ANSI               |
| `utf8content:`    | UTF-8              |
| `utf16content:`   | UTF-16             |

Warning: Content search is significantly slower than filename search.

### Duplicates

| Function          | Duplicates by ...     |
|-------------------|-----------------------|
| `dupe:`           | Filename              |
| `sizedupe:`       | File size             |
| `dmdupe:`         | Date modified         |
| `dcdupe:`         | Date created          |
| `dadupe:`         | Date accessed         |
| `namepartdupe:`   | Name without extension|
| `attribdupe:`     | File attributes       |

### Image Properties

| Function         | Values / Meaning                         |
|------------------|------------------------------------------|
| `width:`         | Pixel width (e.g. `width:>1920`)         |
| `height:`        | Pixel height (e.g. `height:>1080`)       |
| `dimensions:`    | WxH (e.g. `dimensions:1920x1080`)        |
| `orientation:`   | `landscape` or `portrait`                |
| `bitdepth:`      | Bits per pixel (e.g. `bitdepth:24`)      |

### Filename

| Function      | Meaning                              | Example                |
|---------------|--------------------------------------|------------------------|
| `startwith:`  | Filename starts with string          | `startwith:IMG_`       |
| `endwith:`    | Filename ends with string            | `endwith:_final`       |
| `len:`        | Filename character length            | `len:>100`             |

### Folder Stats

| Function            | Meaning                                |
|---------------------|----------------------------------------|
| `childcount:`       | Number of direct children              |
| `childfilecount:`   | Number of direct child files           |
| `childfoldercount:` | Number of direct child folders         |
| `empty:`            | Empty folders (no children)            |

## Comparison Syntax

All functions that accept values support these comparison operators:

| Syntax                 | Meaning                |
|------------------------|------------------------|
| `function:value`       | Equal to               |
| `function:<value`      | Less than              |
| `function:>value`      | Greater than           |
| `function:<=value`     | Less than or equal     |
| `function:>=value`     | Greater than or equal  |
| `function:start..end`  | Range (inclusive)       |

## Regex

Enable with the `regex:` modifier. Uses standard regex syntax.

| Token  | Meaning                    |
|--------|----------------------------|
| `.`    | Any single character       |
| `^`    | Start of filename          |
| `$`    | End of filename            |
| `[]`   | Character class            |
| `*`    | Zero or more of preceding  |
| `+`    | One or more of preceding   |
| `?`    | Zero or one of preceding   |
| `{}`   | Quantifier                 |
| `\`    | Escape special character   |
| `\|`   | Alternation                |

Example: `regex:^IMG_\d{4}\.jpg$` matches `IMG_0001.jpg` through `IMG_9999.jpg`.

## Examples

```text
# Find Python files containing "config"
config ext:py

# Large log files (over 100 MB)
ext:log size:>100mb

# Files modified today in a specific project
dm:today path:C:\Projects\MyApp

# PDFs created this year
ext:pdf dc:thisyear

# Search inside Python files for "import torch"
ext:py content:"import torch"

# Find duplicate files by name
dupe:

# Landscape images wider than 4K
pic: width:>3840 orientation:landscape

# JavaScript or TypeScript files excluding node_modules
ext:js;ts !path:node_modules

# Empty folders anywhere on disk
folder: empty:

# Files between 1-10 MB modified in the last month, in Downloads
size:1mb..10mb dm:lastmonth path:Downloads

# Find folders that contain a Dockerfile
child:Dockerfile

# Case-sensitive search for README (exact)
case:"README.md" file:
```
