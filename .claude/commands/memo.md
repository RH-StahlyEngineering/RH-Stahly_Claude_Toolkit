---
description: Generate a Word memo from markdown file using template
argument-hint: [markdown-file-path]
allowed-tools: Read, Write, Glob, Bash, Skill
---

Generate a professional Word document memo from the markdown file at: $ARGUMENTS

## Step 1: Verify Template Exists

Check if the template exists at `memo_template/unpacked/word/document.xml` (relative to project root).

- If NOT found: Ask the user to provide the path to a `.docx` template file, then use the docx skill to unpack it to `memo_template/unpacked/`
- If found: Proceed to Step 2

## Step 2: Verify Output Directory

Check if `memo_outputs/` exists (relative to project root).

- If NOT found: Create it
- If found: Proceed to Step 3

## Step 3: Parse Markdown File

Read the markdown file provided by the user and extract:

1. **YAML front matter** (between `---` markers):
   - `date`: MM/DD/YYYY format
   - `to`: Recipient name
   - `subject`: Subject line

2. **Body content**: Everything after the second `---`
   - Identify headings (lines starting with `##`)
   - Identify numbered lists (lines starting with `1.`, `2.`, etc.)
   - Identify bold text (wrapped in `**`)
   - Regular paragraphs

## Step 4: Generate Word Document

Use the docx skill to:

1. Load the template from `memo_template/unpacked/`
2. Replace fields in the document:
   - Date field with extracted date
   - Subject field with subject line
   - Body content with proper formatting:
     - Headings as bold text
     - Numbered lists maintained
     - Bold text preserved
     - Paragraphs properly spaced
3. Handle XML special characters:
   - `–` (en-dash) → `&#8211;`
   - `—` (em-dash) → `&#8212;`
   - `½` (half symbol) → `&#189;`
   - `&` → `&amp;`
   - `<` → `&lt;`
   - `>` → `&gt;`
   - `"` `"` (curly quotes) → `&#8220;` `&#8221;`

## Step 5: Save Output

Generate the output filename:
- Extract the base name from the markdown file (without `.md` extension)
- Get today's date in YYYYMMDD format
- Combine as: `{BaseName}_{YYYYMMDD}.docx`

Save to: `memo_outputs/{BaseName}_{YYYYMMDD}.docx`

Use the pack script at `.claude/skills/docx/ooxml/scripts/pack.py` to create the final docx.

## Step 6: Confirm and Prompt for Review

Output the path to the generated document and prompt:

"Created: memo_outputs/{filename}

Please review the generated memo and let me know if you'd like any changes to the formatting or content."
