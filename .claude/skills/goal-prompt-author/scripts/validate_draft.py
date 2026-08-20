"""
validate_draft.py — score a /goal draft against the canonical structure.

Usage:
    python validate_draft.py --input <path>           # validate a file
    python validate_draft.py --stdin                  # validate from stdin
    cat my_goal.txt | python validate_draft.py --stdin

Output:
    A checklist showing which components are present + any anti-patterns detected.
    Exit code 0 if no critical gaps; 1 if missing required components.

Required components:
    - VERIFIABLE END STATE (measurable + checkable)
    - Stated check (an actual command, not just prose)
    - CONSTRAINTS section
    - SCOPE BOUND section
    - ABORT CONDITIONS section (recommended; not strictly required for simple goals)
"""

import sys
import re
import argparse

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


# === USER-EDITABLE CONSTANTS ===

# Substrings whose absence triggers a "missing component" finding
REQUIRED_HEADERS = [
    ("VERIFIABLE END STATE", "Missing the explicit end state. Add a `VERIFIABLE END STATE` section."),
    ("CONSTRAINTS", "No CONSTRAINTS listed. At minimum specify read/write boundaries."),
    ("SCOPE BOUND", "No SCOPE BOUND — task can burn indefinitely. Add a turn or wall-clock cap."),
]

OPTIONAL_HEADERS = [
    ("ABORT CONDITIONS", "Consider adding ABORT CONDITIONS for known failure modes."),
    ("PRE-FLIGHT", "If the task depends on specific tooling, add a PRE-FLIGHT to halt cleanly when missing."),
    ("ARCHITECTURE", "For multi-phase tasks, name the phases briefly."),
    ("REFERENCE DATA", "If existing docs/schemas could help the runner, point at them by path."),
]

# Anti-pattern detectors (regex => description)
ANTI_PATTERNS = [
    (r"\b(make|fix|improve)\s+\w+\s+(better|production-ready|cleaner|nicer)\b",
     "Aspirational language detected ('make X better' / 'production-ready'). Replace with a measurable end state."),
    (r"\btests?\s+(should\s+)?pass\b",
     "Implicit verification: 'tests pass' is not specific enough. Spell out the exact command, e.g. `pytest -x tests/auth exits 0`."),
    (r"\bthe\s+bug\s+is\s+fixed\b",
     "Implicit verification: 'the bug is fixed'. Spell out HOW to verify (e.g., 'rerun the repro script and confirm exit 0')."),
    (r"\bshould\s+(work|be\s+working)\b",
     "Vague: 'should work'. Replace with a measurable condition."),
    (r"\boutput\s+(is|looks)\s+(correct|right|good)\b",
     "Subjective verification: 'output looks correct'. Specify what correct output IS."),
    (r"\b(refactor|migrate|clean\s*up)\b.*\b(codebase|module|project)\b",
     "Broad scope ('refactor the codebase'). Specify exactly which files/areas and what NOT to touch."),
    (r"\bAND\s+\b.*\bAND\s+\b",
     "Multiple AND clauses suggest multiple independent goals. Consider splitting into separate /goal invocations."),
]


def check_stated_command(text):
    """Look for evidence of a literal command in the goal text."""
    patterns = [
        r"`[^`\n]+`",           # backtick-wrapped command
        r"python\s+-c\s+\"",    # python one-liner
        r"\b(pytest|npm|cargo|go|mvn|ruff|black|mypy|tsc|jest|mocha)\b",
        r"exits?\s+0",
        r"(returns|prints)\s+\d",
    ]
    for p in patterns:
        if re.search(p, text, re.IGNORECASE):
            return True
    return False


def check_scope_bound_specifics(text):
    """If SCOPE BOUND exists, does it specify a concrete cap?"""
    m = re.search(r"SCOPE\s*BOUND.*?(?=\n[A-Z]{3,}|\Z)", text, re.DOTALL | re.IGNORECASE)
    if not m:
        return False
    block = m.group(0)
    return bool(re.search(r"\b\d+\s+(turn|wave|minute|hour|second)", block, re.IGNORECASE))


MAX_GOAL_CHARS = 4000   # Hard limit enforced by Claude Code's /goal command


def measure_goal_condition(text):
    """
    Measure the length of the /goal condition (everything after the literal '/goal ' prefix
    if present, otherwise the whole text). Returns (length_chars, body_text).
    """
    stripped = text.strip()
    if stripped.startswith("/goal "):
        body = stripped[len("/goal "):]
    elif stripped.startswith("/goal\n"):
        body = stripped[len("/goal\n"):]
    else:
        body = stripped
    return len(body), body


def suggest_shrink(body):
    """Heuristic suggestions to reduce length while preserving structure."""
    suggestions = []
    # Long inline architecture
    if "ARCHITECTURE" in body.upper():
        arch_block = re.search(r"ARCHITECTURE[\s\S]*?(?=\n[A-Z]{3,}|\Z)", body, re.IGNORECASE)
        if arch_block and len(arch_block.group(0)) > 400:
            suggestions.append("ARCHITECTURE section is long. Replace with a one-line reference to a design doc by absolute path.")
    # Long inline reference data
    if "REFERENCE DATA" in body.upper():
        ref_block = re.search(r"REFERENCE\s*DATA[\s\S]*?(?=\n[A-Z]{3,}|\Z)", body, re.IGNORECASE)
        if ref_block and len(ref_block.group(0)) > 300:
            suggestions.append("REFERENCE DATA section is long. List only paths, not summaries — the runner will read the files itself.")
    # Many constraints
    constraint_block = re.search(r"CONSTRAINTS[\s\S]*?(?=\n[A-Z]{3,}|\Z)", body, re.IGNORECASE)
    if constraint_block:
        bullets = [l for l in constraint_block.group(0).split("\n") if l.strip().startswith(("-", "*", "•"))]
        if len(bullets) > 8:
            suggestions.append(f"{len(bullets)} constraints listed. Group related ones into single bullets, or move to a CONSTRAINTS.md the goal references.")
    # Long abort conditions
    abort = re.search(r"ABORT\s*CONDITIONS[\s\S]*?(?=\n[A-Z]{3,}|\Z)", body, re.IGNORECASE)
    if abort and len(abort.group(0)) > 500:
        suggestions.append("ABORT CONDITIONS section is long. Keep 3-5 specific failure modes; drop generic 'something goes wrong' phrasing.")
    # Pre-flight inlined
    if "PRE-FLIGHT" in body.upper() and len(body) > MAX_GOAL_CHARS:
        suggestions.append("If PRE-FLIGHT exists, move its steps to a script (e.g., `python health_check.py`) the goal references in a single line.")
    # Long preamble
    first_para_end = body.find("\n\n")
    if first_para_end > 0 and first_para_end > 200:
        suggestions.append("Opening sentence is long. Aim for one short sentence summarizing the task; details go in VERIFIABLE END STATE.")
    return suggestions


def validate(text):
    findings = []
    has_critical_gap = False

    # Character count check — /goal hard limit is 4000 chars
    body_len, body = measure_goal_condition(text)
    if body_len > MAX_GOAL_CHARS:
        over = body_len - MAX_GOAL_CHARS
        findings.append(("CHAR_LIMIT", f"Length: {body_len}",
                         f"OVER LIMIT by {over} chars. /goal condition is capped at {MAX_GOAL_CHARS} characters."))
        for s in suggest_shrink(body):
            findings.append(("SHRINK_HINT", "Reduce length", s))
        has_critical_gap = True
    elif body_len > MAX_GOAL_CHARS * 0.9:
        findings.append(("CHAR_WARN", f"Length: {body_len}",
                         f"Close to limit ({MAX_GOAL_CHARS}). Consider trimming."))
    else:
        findings.append(("PRESENT", f"Length: {body_len}/{MAX_GOAL_CHARS}",
                         f"{(body_len/MAX_GOAL_CHARS)*100:.0f}% of limit"))

    # Required headers
    for header, msg in REQUIRED_HEADERS:
        if header not in text.upper():
            findings.append(("MISSING_REQUIRED", header, msg))
            has_critical_gap = True
        else:
            findings.append(("PRESENT", header, "ok"))

    # Optional headers
    for header, msg in OPTIONAL_HEADERS:
        if header not in text.upper():
            findings.append(("MISSING_OPTIONAL", header, msg))
        else:
            findings.append(("PRESENT", header, "ok"))

    # Stated command check
    if not check_stated_command(text):
        findings.append(("WEAK", "Stated check",
                         "No literal command detected (backticks, exit code, or known test runner). "
                         "Spell out the verification command."))
        has_critical_gap = True
    else:
        findings.append(("PRESENT", "Stated check", "ok — at least one literal command/check detected"))

    # Scope bound specifics
    if "SCOPE BOUND" in text.upper() and not check_scope_bound_specifics(text):
        findings.append(("WEAK", "Scope bound", "SCOPE BOUND section exists but has no concrete cap (N turns/minutes)."))

    # Anti-patterns — but skip implicit-verification flags if a literal command is already present
    # (they're contextual prose, not the actual verification claim)
    has_command = check_stated_command(text)
    implicit_verification_patterns = {
        r"\btests?\s+(should\s+)?pass\b",
        r"\bthe\s+bug\s+is\s+fixed\b",
        r"\bshould\s+(work|be\s+working)\b",
        r"\boutput\s+(is|looks)\s+(correct|right|good)\b",
    }
    for pattern, msg in ANTI_PATTERNS:
        if pattern in implicit_verification_patterns and has_command:
            continue  # contextual mention, not a problem
        if re.search(pattern, text, re.IGNORECASE):
            findings.append(("ANTI_PATTERN", pattern[:40], msg))

    return findings, has_critical_gap


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", help="Path to /goal draft file")
    ap.add_argument("--stdin", action="store_true", help="Read draft from stdin")
    args = ap.parse_args()

    if args.input:
        with open(args.input, "r", encoding="utf-8") as f:
            text = f.read()
    elif args.stdin:
        text = sys.stdin.read()
    else:
        ap.print_help()
        sys.exit(2)

    findings, has_critical_gap = validate(text)

    print("=== /goal draft validation ===\n")
    by_category = {}
    for cat, name, msg in findings:
        by_category.setdefault(cat, []).append((name, msg))

    if by_category.get("PRESENT"):
        print("Present:")
        for name, _ in by_category["PRESENT"]:
            print(f"  ✓ {name}")
        print()

    if by_category.get("CHAR_LIMIT"):
        print("CRITICAL — /goal condition exceeds the 4000-character limit:")
        for name, msg in by_category["CHAR_LIMIT"]:
            print(f"  ✗ {name}: {msg}")
        print()

    if by_category.get("SHRINK_HINT"):
        print("How to shrink (apply these to get under 4000 chars):")
        for _, msg in by_category["SHRINK_HINT"]:
            print(f"  • {msg}")
        print()

    if by_category.get("CHAR_WARN"):
        print("Char-count warning:")
        for name, msg in by_category["CHAR_WARN"]:
            print(f"  ⚠ {name}: {msg}")
        print()

    if by_category.get("MISSING_REQUIRED"):
        print("CRITICAL — Missing required components:")
        for name, msg in by_category["MISSING_REQUIRED"]:
            print(f"  ✗ {name}: {msg}")
        print()

    if by_category.get("WEAK"):
        print("WEAK — Components present but weak:")
        for name, msg in by_category["WEAK"]:
            print(f"  ⚠ {name}: {msg}")
        print()

    if by_category.get("MISSING_OPTIONAL"):
        print("Recommended additions:")
        for name, msg in by_category["MISSING_OPTIONAL"]:
            print(f"  • {name}: {msg}")
        print()

    if by_category.get("ANTI_PATTERN"):
        print("Anti-patterns detected:")
        for _, msg in by_category["ANTI_PATTERN"]:
            print(f"  ! {msg}")
        print()

    if has_critical_gap:
        print("Draft has critical gaps — see CRITICAL items above.")
        sys.exit(1)
    else:
        print("Draft looks good (or has only minor recommendations).")
        sys.exit(0)


if __name__ == "__main__":
    main()
