"""Extract content from a v3-style Stahly proposal docx into a JSON skeleton
that matches references/content_schema.md.

NOT fully automatic — does best-effort section detection. The user is expected to
review and fill in the per-type fields (subsection_group subs, fee_table phases,
etc.) before passing to build.py. Saves human time on the boilerplate.
"""
import argparse, json, re, sys
from pathlib import Path
from docx import Document

# Force UTF-8 on Windows so non-ASCII status glyphs (✗ ✓ ⚠ → — etc.) don't
# crash with UnicodeEncodeError on cp1252 consoles.
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        import codecs
        sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, "strict")
        sys.stderr = codecs.getwriter("utf-8")(sys.stderr.buffer, "strict")


def looks_like_h1(text: str) -> bool:
    """Heuristic: a single-line, all-caps paragraph is treated as an H1 from
    the old docx style. Also accept the bolded h1-style labels seen in v3 docx."""
    t = text.strip()
    if not t:
        return False
    common_h1s = ("INTRODUCTION", "SCOPE OF WORK", "ASSUMPTIONS", "SCHEDULE",
                  "FEES FOR PROFESSIONAL SERVICES", "CHANGES IN", "DELIVERABLES",
                  "EXCLUSIONS")
    if t.upper() == t and len(t.split()) <= 8:
        return True
    for h in common_h1s:
        if t.upper().startswith(h):
            return True
    return False


def extract(docx_path: Path):
    doc = Document(str(docx_path))
    paras = doc.paragraphs
    sections = []
    current = None

    def commit():
        nonlocal current
        if current:
            sections.append(current)
            current = None

    for p in paras:
        text = p.text.strip()
        if not text:
            continue
        if looks_like_h1(text):
            commit()
            title = text.title() if text.upper() == text else text
            current = {"type": "paragraph", "title": title, "body": ""}
            continue
        if current:
            current["body"] = (current["body"] + " " + text).strip()
        else:
            # Pre-Introduction text — likely the addressee/RE block; capture as meta
            pass

    commit()
    return sections


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("docx", help="Path to .docx")
    ap.add_argument("--out", default=None, help="Output JSON path (default: same name, .json)")
    args = ap.parse_args()
    docx_path = Path(args.docx)
    out_path = Path(args.out) if args.out else docx_path.with_suffix(".extracted.json")
    sections = extract(docx_path)
    skeleton = {
        "_warning": "Skeleton from extract_docx.py. Each section is typed 'paragraph'. "
                    "Convert to the correct type (subsection_group / deliverables_list / "
                    "fee_table / signature_block) per content_schema.md before building.",
        "project_name": "FIXME",
        "project_subtitle": "FIXME",
        "client_name": "FIXME",
        "date": "FIXME (YYYY-MM-DD)",
        "office": "FIXME (Bozeman|Billings|Helena|Great Falls|Cody)",
        "signatory_name": "FIXME",
        "re_line": "FIXME",
        "addressee": {"name": "FIXME", "org": "FIXME", "street": "FIXME", "city_state_zip": "FIXME"},
        "cover_photo": None,
        "sections": sections,
    }
    out_path.write_text(json.dumps(skeleton, indent=2), encoding="utf-8")
    print(f"Skeleton written: {out_path}")
    print(f"Extracted {len(sections)} section(s). Edit the JSON to add proper types + fill FIXMEs.")


if __name__ == "__main__":
    main()
