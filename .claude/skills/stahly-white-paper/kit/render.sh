#!/bin/sh
# Build docx -> fix footer -> PDF -> 100 dpi page PNGs -> mechanical checks. Run from the paper folder.
cd "$(dirname "$0")" && node build.js && python fixfooter.py PAPER.docx && soffice --headless --convert-to pdf PAPER.docx >/dev/null 2>&1 && rm -f pg-*.png && pdftoppm -png -r 100 PAPER.pdf pg && ls pg-*.png | wc -l && python check_pdf.py PAPER.pdf
