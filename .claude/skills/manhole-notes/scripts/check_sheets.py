"""Render each sheet through Word (not LibreOffice - it paginates differently) and report pages.

    python check_sheets.py <folder or .docx ...> [--png <dir>]

Prints page count per sheet (page 1 = form must stay 1 page; 2 with a photo) and writes PNGs for the
visual check. Also refuses to touch a file that is open in Word (Word's ~$ lock file is present).
"""
import argparse, glob, os, sys
import win32com.client

def locked(p):
    d, n = os.path.split(p)
    return os.path.exists(os.path.join(d, "~$" + n[2:])) or os.path.exists(os.path.join(d, "~$" + n[1:]))

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("paths", nargs="+"); ap.add_argument("--png")
    a = ap.parse_args()
    files = []
    for p in a.paths: files += sorted(glob.glob(os.path.join(p, "*.docx"))) if os.path.isdir(p) else [p]
    files = [f for f in files if not os.path.basename(f).startswith("~$")]
    w = win32com.client.DispatchEx("Word.Application"); w.Visible = False
    try:
        for f in files:
            if locked(f): print(f"OPEN IN WORD - close it first: {f}"); continue
            d = w.Documents.Open(os.path.abspath(f), ReadOnly=True); n = d.ComputeStatistics(2)
            pdf = None
            if a.png:
                os.makedirs(a.png, exist_ok=True); pdf = os.path.join(os.path.abspath(a.png), os.path.basename(f)[:-5] + ".pdf")
                d.ExportAsFixedFormat(pdf, 17)
            d.Close(False); print(f"{n} pages  {f}")
            if pdf:
                import fitz
                for i, pg in enumerate(fitz.open(pdf)): pg.get_pixmap(dpi=90).save(pdf[:-4] + f"_p{i+1}.png")
    finally: w.Quit()

if __name__ == "__main__":
    main()
