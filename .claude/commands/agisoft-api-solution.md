---
description: Find and validate Agisoft Python API solutions using forum + docs
argument-hint: [problem description or error message]
allowed-tools: WebSearch, mcp__crawl4ai__crawl_url, Task, Read
---

You are solving an Agisoft Metashape **Python API** problem:

> $ARGUMENTS

Follow these three phases in order.

---

## Phase 1 — Forum Evidence Collection (Discovery)

Search the Agisoft forum for solutions related to the problem.

### Steps:

1. **Search**: Use `WebSearch` with query: `site:agisoft.com/forum $ARGUMENTS`

2. **Crawl**: For relevant thread URLs, use `mcp__crawl4ai__crawl_url` with `remove_overlay=true`
   - Note: WebFetch gets 403 blocked, must use crawl4ai

3. **Extract** from crawled content:
   - Code snippets (look for "Code:" blocks or code fences)
   - Responses from **Alexey Pasumansky** (Agisoft admin - highest authority)
   - Solutions confirmed as working ("this worked", "solved", "fixed it")
   - API method names, parameters, error messages
   - Post dates (year is sufficient)

### Prioritization:
1. Alexey Pasumansky replied → highest signal
2. User confirmed solution worked → verified
3. Recent posts (within 2 years) → more likely current API
4. Contains runnable code snippet

Preserve this information as **raw evidence** for the next phase.

---

## Phase 2 — Documentation Validation (Grounding)

**Invoke the agisoft-documentation-agent subagent:**

Use the `Task` tool with `subagent_type="agisoft-documentation-agent"` and provide:
- The original problem: `$ARGUMENTS`
- The extracted API symbols and methods from Phase 1
- Any version references found in forum posts

Ask the documentation agent to:
- Verify that referenced API methods exist in official documentation
- Confirm parameter names, accepted values, and defaults
- Identify version-dependent behavior or changes
- Clarify documented workflows related to the solution

**Constraint:** The documentation agent reads ONLY from `agisoft_documentation/` folder.

---

## Phase 3 — Synthesis & Python API Solutions

Produce a comprehensive answer that synthesizes **forum evidence + documentation grounding**.

### A) Recommended Python API Solution(s)

For each viable solution, provide:
- Clear description of what the solution does
- Classification:
  - ✓ **Admin-confirmed** (Alexey Pasumansky replied)
  - ✓ **User-verified** (working example posted)
  - ✓ **Documented** (found in official docs)
- Version constraints (if any)

### B) Python Code Examples

- Provide **clean, runnable Python snippets**
- Prefer examples that:
  - Came directly from forum posts, OR
  - Are minimal adaptations clearly supported by documentation
- **Never invent undocumented parameters**

### C) Evidence Traceability

For each solution, explicitly list:
- Forum thread title + URL
- Post author(s) and date(s)
- Documentation file(s) and section(s) used for validation

### D) Warnings / Caveats (if applicable)

- API changes across versions
- Deprecated methods
- Ambiguities or contradictions between forum advice and documentation
- If forum suggests something undocumented, state this explicitly

---

## Strict Constraints

- Forum discovery: ONLY from `site:agisoft.com/forum` searches (via `WebSearch` + `mcp__crawl4ai__crawl_url`)
- Documentation grounding: ONLY from `agisoft-documentation-agent` subagent (via `Task` tool)
- Do NOT hallucinate APIs, parameters, or behaviors
- If documentation contradicts forum advice, call that out clearly
- If something is mentioned in forums but not documented, say so explicitly
- If no forum results found: suggest alternative search terms
- If crawl fails: note the error and try next thread

---

**Goal:** Deliver a **trustworthy, version-aware Python API answer** that reflects both how Agisoft users actually solved the problem AND how Agisoft officially documents the behavior.
