"""Render a PDF to per-page PNGs for visual QA. Walk references/qa_checklist.md against these."""
import argparse, sys
from pathlib import Path
import pypdfium2 as pdfium

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

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", help="PDF path")
    ap.add_argument("--out-dir", default=None, help="Output directory (default: pdf's folder + /qa_renders)")
    ap.add_argument("--scale", type=float, default=144/72, help="Render scale (default 2x = 144 DPI)")
    args = ap.parse_args()
    pdf_path = Path(args.pdf)
    out_dir = Path(args.out_dir) if args.out_dir else pdf_path.parent / "qa_renders"
    out_dir.mkdir(exist_ok=True, parents=True)
    pdf = pdfium.PdfDocument(pdf_path)
    for i in range(len(pdf)):
        pil = pdf[i].render(scale=args.scale).to_pil()
        pil.save(out_dir / f"p{i+1:02d}.png")
    print(f"Rendered {len(pdf)} page(s) to {out_dir}")

if __name__ == "__main__":
    main()
