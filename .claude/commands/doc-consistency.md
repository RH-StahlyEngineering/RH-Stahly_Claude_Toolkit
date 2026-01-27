---
description: Check consistency between PRD and POST-MVP.md documents
allowed-tools: Read, Edit, Grep, Glob, TodoWrite
---

# Document Consistency Check

## Context

- PRD: @docs/prd.md
- Post-MVP: @docs/POST-MVP.md

## Your Task

Review POST-MVP.md for consistency with the current PRD state:

### Checks to Perform

1. **MVP Approach Notes**
   - Verify notes like "MVP uses X instead" are accurate
   - Check that MVP descriptions match actual PRD implementation
   - Update any outdated references

2. **Feature References**
   - Ensure section references to PRD are valid (e.g., "see prd.md section 5.1.4")
   - Verify feature names match between documents
   - Check cross-references are accurate

3. **Technical Consistency**
   - JXL vs EPSG references match PRD approach
   - Status model descriptions match (uploading/quoted/paid/processing/completed/error)
   - Upload approach (ZIP + JXL separate) matches PRD
   - Pricing approach matches PRD

4. **Scope Alignment**
   - Features listed as "moved from MVP" are actually not in MVP
   - Post-MVP features don't accidentally appear in PRD
   - Deferred items have appropriate notes

### Output

Create a summary of:
- Issues found and fixed
- Any remaining inconsistencies that need user input
- Confirmation of consistency after fixes

Commit any fixes with a descriptive message.
