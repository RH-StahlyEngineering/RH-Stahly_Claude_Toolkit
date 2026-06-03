"""
Stahly Engineering & Associates branded proposal builder.

Refactored from the Hilger-to-Roy `build_branded_proposal.py` to be content-agnostic:
- All content arrives via a JSON file (--content). See references/content_schema.md.
- Office directory loaded from references/offices.json.
- Brand constants kept in this file; must be reconciled with references/brand_spec.md.
- Layout numbers kept in this file (cover composition is locked per brand spec).

USAGE
    python build.py --content content.json --out out.pdf [--cover-photo path.jpg]
                    [--skill-dir <path>] [--draft|--final|--version v1]
                    [--writeback-docx source.docx]

ENV
    STAHLY_PROPOSAL_OUT   Override --out (handy when target is locked by a viewer)
"""
from __future__ import annotations
import argparse
import json
import os
import sys
from pathlib import Path
from datetime import datetime

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

from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor, Color
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER, TA_JUSTIFY
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer, KeepTogether,
    Table, TableStyle,
)
from reportlab.platypus.flowables import Flowable
from reportlab.pdfgen import canvas as pdfcanvas
from PIL import Image as PILImage


# ============================================================
# BRAND CONSTANTS (reconciled with references/brand_spec.md)
# ============================================================

STAHLY_BLUE  = HexColor("#00548C")   # Pantone 7462C
STAHLY_TAN   = HexColor("#BABAB1")   # Pantone 413C
STAHLY_CREAM = HexColor("#E9E6E1")   # Pantone P189-1C
STAHLY_TAN_TINT = HexColor("#EFEEE9")
STAHLY_WHITE = HexColor("#FFFFFF")
STAHLY_BLACK = HexColor("#000000")

PAGE_W, PAGE_H = LETTER  # 612 × 792 pt
MARGIN_TOP = 1.0 * inch
MARGIN_BOT = 0.55 * inch         # body frame bottom edge above top of footer band
MARGIN_L = 0.85 * inch
MARGIN_R = 0.85 * inch
FOOTER_BAND_H = 0.80 * inch      # taller than v1.0 so text inside the band sits ≥ 0.5" from page bottom
SAFE_MARGIN = 0.50 * inch        # minimum distance from page edge to any text or logo content


# ============================================================
# FONT REGISTRATION
# ============================================================

def register_fonts():
    """Rockwell + Arial per Stahly brand. System fonts on Stahly Windows machines."""
    win = Path("C:/Windows/Fonts")
    pdfmetrics.registerFont(TTFont("Rockwell",        str(win / "ROCK.TTF")))
    pdfmetrics.registerFont(TTFont("Rockwell-Bold",   str(win / "ROCKB.TTF")))
    pdfmetrics.registerFont(TTFont("Rockwell-Italic", str(win / "ROCKI.TTF")))
    pdfmetrics.registerFont(TTFont("Rockwell-BoldIt", str(win / "ROCKBI.TTF")))
    pdfmetrics.registerFont(TTFont("Arial",           str(win / "arial.ttf")))
    pdfmetrics.registerFont(TTFont("Arial-Bold",      str(win / "arialbd.ttf")))
    pdfmetrics.registerFont(TTFont("Arial-Italic",    str(win / "ariali.ttf")))
    pdfmetrics.registerFont(TTFont("Arial-BoldIt",    str(win / "arialbi.ttf")))
    from reportlab.pdfbase.pdfmetrics import registerFontFamily
    registerFontFamily("Arial",    normal="Arial",    bold="Arial-Bold",
                       italic="Arial-Italic",    boldItalic="Arial-BoldIt")
    registerFontFamily("Rockwell", normal="Rockwell", bold="Rockwell-Bold",
                       italic="Rockwell-Italic", boldItalic="Rockwell-BoldIt")


# ============================================================
# PARAGRAPH STYLES
# ============================================================

def make_styles():
    return {
        "H1": ParagraphStyle("H1", fontName="Rockwell-Bold", fontSize=15, leading=19,
                             textColor=STAHLY_BLUE, spaceBefore=24, spaceAfter=2),
        "H2": ParagraphStyle("H2", fontName="Arial-Bold", fontSize=11, leading=14,
                             textColor=STAHLY_BLACK, spaceBefore=8, spaceAfter=2),
        "Body": ParagraphStyle("Body", fontName="Arial", fontSize=11, leading=14,
                               textColor=STAHLY_BLACK, spaceAfter=6, alignment=TA_JUSTIFY),
        "BodyLeft": ParagraphStyle("BodyLeft", fontName="Arial", fontSize=11, leading=14,
                                   textColor=STAHLY_BLACK, spaceAfter=6, alignment=TA_LEFT),
        "Bullet": ParagraphStyle("Bullet", fontName="Arial", fontSize=11, leading=14,
                                 textColor=STAHLY_BLACK, leftIndent=22, bulletIndent=8,
                                 spaceAfter=2, bulletFontName="Arial-Bold", bulletFontSize=11),
        "AddrSmall": ParagraphStyle("AddrSmall", fontName="Arial", fontSize=10, leading=13,
                                    textColor=STAHLY_BLACK, spaceAfter=2),
        "DeliverableTitle": ParagraphStyle("DeliverableTitle", fontName="Arial-Bold", fontSize=11,
                                           leading=14, textColor=STAHLY_BLUE, spaceBefore=6, spaceAfter=1),
        "SignClose": ParagraphStyle("SignClose", fontName="Arial", fontSize=11, leading=14,
                                    textColor=STAHLY_BLACK, spaceAfter=2),
        "SignFirm": ParagraphStyle("SignFirm", fontName="Arial-Bold", fontSize=11, leading=14,
                                   textColor=STAHLY_BLACK, spaceAfter=2),
    }


# ============================================================
# CUSTOM FLOWABLES
# ============================================================

class H1WithRule(Flowable):
    """H1 heading with a Stahly Blue underline rule + breathing room above.

    SPACE_ABOVE reclaimed from 22 → 16pt to keep the fee table on the same page
    as the rest of the fee section in dense LiDAR proposals. Across ~7 H1s in a
    typical proposal this claws back ~0.58" of vertical real estate."""
    SPACE_ABOVE = 10
    RULE_GAP = 5

    def __init__(self, text, styles, width=None):
        super().__init__()
        self.text = text
        self.styles = styles
        self.width = width

    def wrap(self, availWidth, availHeight):
        self.width = self.width or availWidth
        self._para = Paragraph(self.text, self.styles["H1"])
        _, ph = self._para.wrap(self.width, availHeight)
        self.height = self.SPACE_ABOVE + ph + self.RULE_GAP
        return self.width, self.height

    def draw(self):
        c = self.canv
        rule_y = 0
        para_y = rule_y + self.RULE_GAP
        self._para.drawOn(c, 0, para_y)
        c.setStrokeColor(STAHLY_BLUE)
        c.setLineWidth(0.75)
        c.line(0, rule_y, self.width, rule_y)


def _round_100(x):
    """Round to nearest $100 — used by the fee-table renderer."""
    return int(round(x / 100.0)) * 100


def _human_date(iso):
    """ISO date YYYY-MM-DD → 'Month D, YYYY'. Pass through if already non-ISO."""
    try:
        d = datetime.strptime(iso, "%Y-%m-%d")
        return d.strftime("%B %-d, %Y") if os.name != "nt" else d.strftime("%B %#d, %Y")
    except (ValueError, TypeError):
        return iso


def _fmt_money(x):
    return "—" if x == 0 else f"${x:,}"


def build_fee_table(section, styles):
    """Render a phase-broken fee table. Computes the grand total in code from
    per-line $100-rounded values; never trusts a hand-typed total.

    Auto-collapses to a 2-column (Phase | Subtotal) table when every phase has
    $0 expenses — matches the bid-workbook convention where labor and direct
    expenses are bundled at the line-item level."""
    pheader   = ParagraphStyle("FeeH",  fontName="Arial-Bold", fontSize=11, leading=13, textColor=STAHLY_WHITE)
    pheader_r = ParagraphStyle("FeeHR", fontName="Arial-Bold", fontSize=11, leading=13, textColor=STAHLY_WHITE, alignment=TA_RIGHT)
    pheader_c = ParagraphStyle("FeeHC", fontName="Arial-Bold", fontSize=11, leading=13, textColor=STAHLY_WHITE, alignment=TA_CENTER)
    pcell     = ParagraphStyle("FeeC",  fontName="Arial",      fontSize=11, leading=13, textColor=STAHLY_BLACK)
    pcell_r   = ParagraphStyle("FeeCR", fontName="Arial",      fontSize=11, leading=13, textColor=STAHLY_BLACK, alignment=TA_RIGHT)
    pcell_c   = ParagraphStyle("FeeCC", fontName="Arial",      fontSize=11, leading=13, textColor=STAHLY_BLACK, alignment=TA_CENTER)
    ptotal    = ParagraphStyle("FeeT",  fontName="Arial-Bold", fontSize=11, leading=13, textColor=STAHLY_BLUE)
    ptotal_r  = ParagraphStyle("FeeTR", fontName="Arial-Bold", fontSize=11, leading=13, textColor=STAHLY_BLUE, alignment=TA_RIGHT)
    ptotal_big = ParagraphStyle("FeeTB",fontName="Rockwell-Bold", fontSize=13, leading=15, textColor=STAHLY_BLUE, alignment=TA_RIGHT)

    # Pre-compute rounded values and decide if we can collapse the Expenses column
    rounded_rows = []
    total_labor = total_exp = 0
    for ph in section["phases"]:
        labor = _round_100(ph.get("labor", 0))
        exp   = _round_100(ph.get("expenses", 0))
        sub   = labor + exp
        total_labor += labor
        total_exp   += exp
        rounded_rows.append({"name": ph["name"], "basis": ph.get("basis", ""), "labor": labor, "exp": exp, "sub": sub})
    grand = total_labor + total_exp
    show_split = total_exp > 0  # collapse to single-column when all expenses are 0
    # Auto-detect mixed-basis fee structure (e.g. some phases lump-sum, one T&M NTE).
    # When any phase declares a `basis`, add a centered Basis column so the client
    # can see fee structure row-by-row without inferring from the lead paragraph.
    show_basis = any(r["basis"] for r in rounded_rows)

    if show_split:
        if show_basis:
            data = [[
                Paragraph("Phase", pheader),
                Paragraph("Basis", pheader_c),
                Paragraph("Labor", pheader_r),
                Paragraph("Expenses", pheader_r),
                Paragraph("Subtotal", pheader_r),
            ]]
            for r in rounded_rows:
                data.append([
                    Paragraph(r["name"], pcell),
                    Paragraph(r["basis"] or "", pcell_c),
                    Paragraph(_fmt_money(r["labor"]), pcell_r),
                    Paragraph(_fmt_money(r["exp"]),   pcell_r),
                    Paragraph(_fmt_money(r["sub"]),   pcell_r),
                ])
            data.append([
                Paragraph("<b>TOTAL</b>", ptotal),
                Paragraph("", pcell_c),
                Paragraph(_fmt_money(total_labor), ptotal_r),
                Paragraph(_fmt_money(total_exp),   ptotal_r),
                Paragraph(_fmt_money(grand),       ptotal_big),
            ])
            col_widths = [2.40 * inch, 1.05 * inch, 1.00 * inch, 1.00 * inch, 1.35 * inch]
        else:
            data = [[
                Paragraph("Phase", pheader),
                Paragraph("Labor", pheader_r),
                Paragraph("Expenses", pheader_r),
                Paragraph("Subtotal", pheader_r),
            ]]
            for r in rounded_rows:
                data.append([
                    Paragraph(r["name"], pcell),
                    Paragraph(_fmt_money(r["labor"]), pcell_r),
                    Paragraph(_fmt_money(r["exp"]),   pcell_r),
                    Paragraph(_fmt_money(r["sub"]),   pcell_r),
                ])
            data.append([
                Paragraph("<b>TOTAL</b>", ptotal),
                Paragraph(_fmt_money(total_labor), ptotal_r),
                Paragraph(_fmt_money(total_exp),   ptotal_r),
                Paragraph(_fmt_money(grand),       ptotal_big),
            ])
            col_widths = [3.10 * inch, 1.10 * inch, 1.10 * inch, 1.50 * inch]
    else:
        if show_basis:
            data = [[
                Paragraph("Phase", pheader),
                Paragraph("Basis", pheader_c),
                Paragraph("Subtotal", pheader_r),
            ]]
            for r in rounded_rows:
                data.append([
                    Paragraph(r["name"], pcell),
                    Paragraph(r["basis"] or "", pcell_c),
                    Paragraph(_fmt_money(r["sub"]), pcell_r),
                ])
            data.append([
                Paragraph("<b>TOTAL</b>", ptotal),
                Paragraph("", pcell_c),
                Paragraph(_fmt_money(grand), ptotal_big),
            ])
            col_widths = [3.45 * inch, 0.85 * inch, 2.50 * inch]
        else:
            # 2-column collapsed layout — labor + expenses bundled per workbook
            data = [[
                Paragraph("Phase", pheader),
                Paragraph("Subtotal", pheader_r),
            ]]
            for r in rounded_rows:
                data.append([
                    Paragraph(r["name"], pcell),
                    Paragraph(_fmt_money(r["sub"]), pcell_r),
                ])
            data.append([
                Paragraph("<b>TOTAL</b>", ptotal),
                Paragraph(_fmt_money(grand), ptotal_big),
            ])
            col_widths = [4.30 * inch, 2.50 * inch]

    tbl = Table(data, colWidths=col_widths, repeatRows=1)
    style = TableStyle([
        ('BACKGROUND',     (0, 0), (-1, 0), STAHLY_BLUE),
        ('VALIGN',         (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING',    (0, 0), (-1, -1), 6),
        ('RIGHTPADDING',   (0, 0), (-1, -1), 6),
        # Data-row padding tightened (5 → 3) so a 6-phase Basis-column table
        # fits the available vertical budget on the Fees page without bumping
        # to a fresh page. TOTAL row keeps its 8pt for visual weight.
        ('TOPPADDING',     (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING',  (0, 0), (-1, -1), 3),
        ('LINEBELOW',      (0, 0), (-1, 0), 0.75, STAHLY_BLUE),
        ('LINEBELOW',      (0, 1), (-1, -2), 0.25, STAHLY_TAN),
        ('BACKGROUND',     (0, -1), (-1, -1), STAHLY_CREAM),
        ('LINEABOVE',      (0, -1), (-1, -1), 0.75, STAHLY_BLUE),
        ('TOPPADDING',     (0, -1), (-1, -1), 8),
        ('BOTTOMPADDING',  (0, -1), (-1, -1), 8),
    ])
    for i in range(1, len(data) - 1):
        if i % 2 == 0:
            style.add('BACKGROUND', (0, i), (-1, i), STAHLY_TAN_TINT)
    tbl.setStyle(style)

    section["_rendered"] = {
        "rows": rounded_rows,
        "total_labor": total_labor,
        "total_exp":   total_exp,
        "grand_total": grand,
    }
    return tbl


def build_comparison_table(section, styles):
    """Generic comparison table — for Option B savings breakdowns, scope-vs-
    fee tradeoffs, year-over-year comparisons, anywhere you need a small
    Stahly-branded table that isn't a phase-broken fee table.

    Section schema:
        {
          "type": "comparison_table",
          "title": "...",                  # H1 (rendered by dispatcher)
          "lead": "...",                   # optional intro paragraph
          "columns": ["Item", "Baseline", "Option B", "Delta"],
          "rows": [["...", "$14,304", "$0", "−$14,304"], ...],
          "footer_row": ["Net delta", "", "", "−$13,000"]   # optional, rendered as bold cream row
        }

    All cells are strings — caller pre-formats numbers, signs, percentages.
    First column is left-aligned, remaining columns right-aligned.
    Stahly Blue header, alternating Stahly Tan tint body rows, optional
    Stahly Cream footer row. Column widths are evenly distributed across
    the available 6.8" body width, with the first column getting 2× the
    width of the others (since the description column is wider than numbers).
    """
    pheader   = ParagraphStyle("CmpH",  fontName="Arial-Bold", fontSize=11, leading=13, textColor=STAHLY_WHITE)
    pheader_r = ParagraphStyle("CmpHR", fontName="Arial-Bold", fontSize=11, leading=13, textColor=STAHLY_WHITE, alignment=TA_RIGHT)
    pcell     = ParagraphStyle("CmpC",  fontName="Arial",      fontSize=11, leading=13, textColor=STAHLY_BLACK)
    pcell_r   = ParagraphStyle("CmpCR", fontName="Arial",      fontSize=11, leading=13, textColor=STAHLY_BLACK, alignment=TA_RIGHT)
    pfooter   = ParagraphStyle("CmpF",  fontName="Arial-Bold", fontSize=11, leading=13, textColor=STAHLY_BLUE)
    pfooter_r = ParagraphStyle("CmpFR", fontName="Arial-Bold", fontSize=11, leading=13, textColor=STAHLY_BLUE, alignment=TA_RIGHT)

    columns = section["columns"]
    rows    = section["rows"]
    footer  = section.get("footer_row")

    # Header
    data = [
        [Paragraph(columns[0], pheader)] +
        [Paragraph(col, pheader_r) for col in columns[1:]]
    ]
    # Body
    for row in rows:
        data.append(
            [Paragraph(row[0], pcell)] +
            [Paragraph(str(cell), pcell_r) for cell in row[1:]]
        )
    # Optional footer
    if footer:
        data.append(
            [Paragraph(f"<b>{footer[0]}</b>", pfooter)] +
            [Paragraph(f"<b>{cell}</b>", pfooter_r) for cell in footer[1:]]
        )

    # Column widths: first column wider, rest evenly distribute the remaining 6.8"
    total_w = 6.8 * inch
    n_other = len(columns) - 1
    first_w = total_w * 0.40  # 40% for the description column
    other_w = (total_w - first_w) / max(n_other, 1)
    col_widths = [first_w] + [other_w] * n_other

    tbl = Table(data, colWidths=col_widths, repeatRows=1)
    style = TableStyle([
        ('BACKGROUND',     (0, 0), (-1, 0), STAHLY_BLUE),
        ('VALIGN',         (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING',    (0, 0), (-1, -1), 6),
        ('RIGHTPADDING',   (0, 0), (-1, -1), 6),
        ('TOPPADDING',     (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING',  (0, 0), (-1, -1), 5),
        ('LINEBELOW',      (0, 0), (-1, 0), 0.75, STAHLY_BLUE),
    ])
    body_end = len(data) - (1 if footer else 0)
    # Tan-tint alternating rows in body
    for i in range(1, body_end):
        if i % 2 == 0:
            style.add('BACKGROUND', (0, i), (-1, i), STAHLY_TAN_TINT)
        style.add('LINEBELOW', (0, i), (-1, i), 0.25, STAHLY_TAN)
    # Footer row: cream background + thick blue rule above
    if footer:
        style.add('BACKGROUND', (0, -1), (-1, -1), STAHLY_CREAM)
        style.add('LINEABOVE', (0, -1), (-1, -1), 0.75, STAHLY_BLUE)
        style.add('TOPPADDING', (0, -1), (-1, -1), 8)
        style.add('BOTTOMPADDING', (0, -1), (-1, -1), 8)
    tbl.setStyle(style)
    return tbl


class SignatureBlock(Flowable):
    """Sign-off block: optional signature image + signature line + name + title + Stahly Blue contact lines.

    If signature_image is provided (transparent PNG; see references/signature_prep.md),
    it is composited above the signature line so the proposal looks signed without
    requiring a DocuSign envelope on the proposal itself.

    Height is computed from the actual content (number of contact lines)
    plus the SIGNING_ROOM constant. Caller can override SIGNING_ROOM for
    tighter or looser layouts. This replaces the hardcoded 1.30" / 1.20" /
    0.85" magic numbers that historically required hand-tuning every time
    the proposal got close to a page-break boundary.
    """

    # Vertical-layout constants (in points). Adjust SIGNING_ROOM if a project
    # needs more or less ink space above the signature line.
    SIGNING_ROOM_DEFAULT = 0.50 * inch   # space above the signature line
    NAME_GAP   = 16                       # px between line and printed name
    TITLE_GAP  = 30                       # px between line and italic title
    FIRST_CONTACT_GAP = 44                # px between line and first contact row
    CONTACT_LEADING   = 11                # px between contact rows
    BOTTOM_PAD = 4                        # buffer below the last contact row

    def __init__(self, name, title, contact_lines=None, signature_image=None,
                 width=None, signing_room=None):
        super().__init__()
        self.name = name
        self.title = title
        self.contact_lines = contact_lines or []
        self.signature_image = signature_image  # Path or None
        self.width = width
        self.signing_room = signing_room if signing_room is not None else self.SIGNING_ROOM_DEFAULT

        # Geometry (top-to-bottom inside the flowable):
        #   signing_room  →  signature line  →  name  →  title  →  contact lines  →  bottom pad
        # line_y is measured from the bottom of the flowable. We compute it from
        # how much space the below-line content needs.
        below_line = (
            self.FIRST_CONTACT_GAP
            + max(0, len(self.contact_lines) - 1) * self.CONTACT_LEADING
            + self.BOTTOM_PAD
        )
        self._line_y = below_line  # absolute y of the signature line inside the flowable
        self.height = self.signing_room + self._line_y

    def wrap(self, availWidth, availHeight):
        self.width = self.width or availWidth
        return self.width, self.height

    def draw(self):
        c = self.canv
        line_y = self._line_y
        # 1) Optional signature image composited above the line (transparent PNG).
        #    Sized to ~1.6" wide so it sits centered-ish on the 2.5" signature line.
        if self.signature_image and Path(str(self.signature_image)).exists():
            try:
                pil = PILImage.open(str(self.signature_image))
                sig_w = 1.6 * inch
                ar = pil.size[1] / pil.size[0]
                sig_h = sig_w * ar
                # Baseline of signature sits just above the line so it reads as "on" the line.
                sig_x = 0.10 * inch
                sig_y = line_y - 0.06 * inch
                c.drawImage(str(self.signature_image), sig_x, sig_y,
                            sig_w, sig_h, preserveAspectRatio=True, mask='auto')
            except Exception as e:
                print(f"Warning: signature image not rendered: {e}", file=sys.stderr)
        # 2) Signature line
        c.setStrokeColor(STAHLY_BLACK); c.setLineWidth(0.5)
        c.line(0, line_y, 2.5 * inch, line_y)
        # 3) Printed name + title + Stahly Blue contact lines below the line
        c.setFillColor(STAHLY_BLACK)
        c.setFont("Arial-Bold", 12); c.drawString(0, line_y - self.NAME_GAP, self.name)
        c.setFont("Arial-Italic", 11); c.drawString(0, line_y - self.TITLE_GAP, self.title)
        c.setFont("Arial", 10); c.setFillColor(STAHLY_BLUE)
        y = line_y - self.FIRST_CONTACT_GAP
        for line in self.contact_lines:
            c.drawString(0, y, line); y -= self.CONTACT_LEADING


# ============================================================
# COVER PAGE — drawn directly on a canvas
# ============================================================

def draw_cover(c: pdfcanvas.Canvas, ctx, assets, offices_ordered, corridor_map_path=None):
    """Cover: stripes → title → photo → cream firm-name band → blue address band → tan tagline band.
    The bottom three bands are flush against each other per brand spec."""
    W, H = PAGE_W, PAGE_H

    # Bottom-up stack (flush). Tagline band sized so its italic text sits >= SAFE_MARGIN from page bottom.
    TAGLINE_H = 0.80 * inch
    ADDR_H    = 0.90 * inch
    CREAM_H   = 2.10 * inch
    tagline_top_y = TAGLINE_H
    addr_top_y    = tagline_top_y
    addr_top_edge = addr_top_y + ADDR_H
    cream_top_y   = addr_top_edge + CREAM_H

    # 1. Masthead stripes
    stripe_h = 8
    c.setFillColor(STAHLY_BLUE)
    c.rect(0, H - stripe_h, W, stripe_h, stroke=0, fill=1)
    c.setFillColor(STAHLY_TAN)
    c.rect(0, H - 2 * stripe_h - 2, W, stripe_h, stroke=0, fill=1)

    # 2. Title block
    title_x = 0.85 * inch
    title_top = H - 0.85 * inch
    c.setFillColor(STAHLY_BLUE)
    # Project name — split to 2 lines if user provided "\n", else 1
    parts = ctx["project_name"].split("\n", 1)
    c.setFont("Rockwell-Bold", 24)
    c.drawString(title_x, title_top, parts[0])
    next_y = title_top - 30
    if len(parts) > 1:
        c.drawString(title_x, next_y, parts[1])
        next_y -= 26
    # Subtitle
    if ctx.get("project_subtitle"):
        c.setFont("Rockwell-Italic", 13)
        c.drawString(title_x, next_y, ctx["project_subtitle"])
        next_y -= 36
    # "A proposal to:" + client + date
    c.setFont("Rockwell", 18); c.drawString(title_x, next_y, "A proposal to:")
    next_y -= 24
    c.setFont("Rockwell-Bold", 18); c.drawString(title_x, next_y, ctx["client_name"])
    next_y -= 22
    c.setFont("Rockwell-Italic", 12); c.drawString(title_x, next_y, _human_date(ctx["date"]))

    # 3. Project photo below title block, centered
    if corridor_map_path and Path(corridor_map_path).exists():
        try:
            pil = PILImage.open(corridor_map_path)
            photo_max_w = 6.6 * inch
            # Zone shifted up by 0.05" so gap above photo (date → photo) equals gap below
            # photo (photo → blue rule on cream band).
            photo_zone_top = H - 3.05 * inch
            photo_zone_bot = cream_top_y + 0.15 * inch
            photo_zone_h = photo_zone_top - photo_zone_bot
            ratio = min(photo_max_w / pil.size[0], photo_zone_h / pil.size[1])
            pw, ph = pil.size[0] * ratio, pil.size[1] * ratio
            px = (W - pw) / 2
            # Vertical placement: center the rendered image inside the
            # available photo zone. Earlier builds added a +0.375" upward
            # offset to "equalize visual whitespace" between the title block
            # above and the cream band below, but the offset overran the
            # zone top edge for taller images (3.5"+) and pushed the photo
            # into the title block. True vertical centering inside
            # photo_zone_h is the locked behavior.
            py = photo_zone_bot + (photo_zone_h - ph) / 2
            c.drawImage(str(corridor_map_path), px, py, pw, ph,
                        preserveAspectRatio=True, mask='auto')
            c.setStrokeColor(STAHLY_TAN); c.setLineWidth(0.75)
            c.rect(px, py, pw, ph, stroke=1, fill=0)
        except Exception as e:
            print(f"Warning: cover photo not rendered: {e}", file=sys.stderr)

    # 4. Cream firm-name band
    c.setFillColor(STAHLY_CREAM)
    c.rect(0, cream_top_y - CREAM_H, W, CREAM_H, stroke=0, fill=1)
    # Top rule only (bottom edge meets address band)
    c.setFillColor(STAHLY_BLUE)
    c.rect(0, cream_top_y, W, 1.5, stroke=0, fill=1)
    # Firm-name text (vertically centered)
    text_baseline = cream_top_y - CREAM_H / 2
    c.setFillColor(STAHLY_BLUE)
    c.setFont("Rockwell", 18)
    c.drawString(0.85 * inch, text_baseline + 32, "Stahly Engineering & Associates")
    c.setFont("Rockwell-Bold", 28)
    c.drawString(0.85 * inch, text_baseline + 2, "Professional Services")
    c.drawString(0.85 * inch, text_baseline - 32, "Proposal")
    # Hero logo right side, transparent on cream
    hero_logo = assets["hero_logo"]
    if hero_logo.exists():
        target_h = CREAM_H - 0.45 * inch
        pil_logo = PILImage.open(hero_logo)
        ar = pil_logo.size[1] / pil_logo.size[0]
        logo_h = target_h
        logo_w = logo_h / ar
        logo_x = W - 0.85 * inch - logo_w
        logo_y = cream_top_y - CREAM_H + (CREAM_H - logo_h) / 2
        c.drawImage(str(hero_logo), logo_x, logo_y, logo_w, logo_h,
                    preserveAspectRatio=True, mask='auto')

    # 5. Address band — full-width Stahly Blue. Text columns are inset within SAFE_MARGIN
    #    so outermost office text stays at least 0.5" from page edges.
    c.setFillColor(STAHLY_BLUE)
    c.rect(0, addr_top_y, W, ADDR_H, stroke=0, fill=1)
    inner_w = W - 2 * SAFE_MARGIN
    n = len(offices_ordered)
    col_w = inner_w / n
    c.setFillColor(STAHLY_TAN)
    for i, off in enumerate(offices_ordered):
        cx = SAFE_MARGIN + col_w * i + col_w / 2
        c.setFont("Arial", 9)
        c.drawCentredString(cx, addr_top_y + ADDR_H - 0.25 * inch, off["street"])
        c.drawCentredString(cx, addr_top_y + ADDR_H - 0.42 * inch, off["city_state_zip"])
        c.drawCentredString(cx, addr_top_y + ADDR_H - 0.59 * inch, off["phone"])

    # 6. Tagline band — full-width Stahly Tan. Tagline text baseline at SAFE_MARGIN so
    #    the italic Rockwell text body sits at least 0.5" from the page bottom.
    c.setFillColor(STAHLY_TAN)
    c.rect(0, 0, W, TAGLINE_H, stroke=0, fill=1)
    c.setFillColor(STAHLY_BLUE)
    c.setFont("Rockwell-Italic", 14)
    c.drawCentredString(W / 2, SAFE_MARGIN + 4, "Engineering Excellence for More Than 50 Years")

    c.showPage()


# ============================================================
# BODY PAGE FOOTER
# ============================================================

def make_footer_drawer(assets, total_pages_holder):
    """Returns a function the PageTemplate uses to draw the footer on every body page.
    Footer band background bleeds to page edges; text and logo sit inside the SAFE_MARGIN."""
    def draw_footer(c: pdfcanvas.Canvas, doc):
        W = PAGE_W
        # Band background — bleeds full width
        c.setFillColor(STAHLY_TAN)
        c.rect(0, 0, W, FOOTER_BAND_H, stroke=0, fill=1)
        # Text baseline positioned so the text body sits >= SAFE_MARGIN from page bottom
        text_baseline_y = SAFE_MARGIN + 4        # ~0.55" — text body rises from here
        c.setFillColor(STAHLY_WHITE)
        c.setFont("Rockwell", 11)
        c.drawString(SAFE_MARGIN + 0.35 * inch, text_baseline_y, "Proposal for Services")
        c.setFont("Rockwell-Italic", 11)
        page_num = c.getPageNumber()
        total = total_pages_holder["total"]
        c.drawRightString(W - 1.55 * inch, text_baseline_y, f"Page {page_num} of {total}")
        # Footer logo — sized to sit inside the band with text-baseline alignment, fully in safe area
        footer_logo = assets["footer_logo"]
        if footer_logo.exists():
            pil = PILImage.open(footer_logo)
            ar = pil.size[1] / pil.size[0]
            lw = 0.75 * inch
            lh = lw * ar
            # Vertically center the logo inside the band; horizontally place inside SAFE_MARGIN
            logo_x = W - SAFE_MARGIN - lw
            logo_y = (FOOTER_BAND_H - lh) / 2
            c.drawImage(str(footer_logo), logo_x, logo_y, lw, lh,
                        preserveAspectRatio=True, mask='auto')
    return draw_footer


# ============================================================
# CONTENT → FLOWABLES
# ============================================================

def section_to_flowables(section, styles, ctx, contact_lines):
    """Map a content-schema section to ReportLab flowables."""
    t = section["type"]
    out = []
    if t == "intro":
        out.append(KeepTogether([
            H1WithRule(section["title"], styles),
            Spacer(1, 0.08 * inch),
            Paragraph(section["body"], styles["Body"]),
        ]))
    elif t == "subsection_group":
        out.append(H1WithRule(section["title"], styles))
        out.append(Spacer(1, 0.08 * inch))
        if section.get("lead"):
            out.append(Paragraph(section["lead"], styles["BodyLeft"]))
        for sub in section["subs"]:
            block = [Paragraph(sub["title"], styles["H2"])]
            # body may be a single string (one paragraph) or a list of strings
            # (multiple paragraphs). The list form is the right call when a
            # subsection's content covers multiple distinct ideas that read
            # better with paragraph breaks — keeps the prose scannable instead
            # of dumping a 250-word wall of text.
            body = sub["body"]
            if isinstance(body, list):
                for i, para in enumerate(body):
                    if i > 0:
                        block.append(Spacer(1, 0.06 * inch))
                    block.append(Paragraph(para, styles["Body"]))
            else:
                block.append(Paragraph(body, styles["Body"]))
            for b in sub.get("bullets", []):
                block.append(Paragraph(b, styles["Bullet"], bulletText="•"))
            out.append(KeepTogether(block))
    elif t == "bullet_list":
        h = section.get("h_level", "H1")
        if h == "H1":
            out.append(H1WithRule(section["title"], styles))
            out.append(Spacer(1, 0.08 * inch))
        else:
            out.append(Paragraph(section["title"], styles["H2"]))
        if section.get("lead"):
            out.append(Paragraph(section["lead"], styles["Body"]))
        for b in section["bullets"]:
            out.append(Paragraph(b, styles["Bullet"], bulletText="•"))
    elif t == "deliverables_list":
        first = section["items"][0]
        head_block = [H1WithRule(section["title"], styles),
                      Spacer(1, 0.08 * inch)]
        if section.get("lead"):
            head_block.append(Paragraph(section["lead"], styles["Body"]))
        head_block.extend([Paragraph(first["title"], styles["DeliverableTitle"]),
                           Paragraph(first["body"], styles["Body"])])
        out.append(KeepTogether(head_block))
        for item in section["items"][1:]:
            out.append(KeepTogether([
                Paragraph(item["title"], styles["DeliverableTitle"]),
                Paragraph(item["body"], styles["Body"]),
            ]))
    elif t == "assumptions_group":
        out.append(H1WithRule(section["title"], styles))
        out.append(Spacer(1, 0.08 * inch))
        for g in section["groups"]:
            out.append(Paragraph(g["title"], styles["H2"]))
            for b in g["bullets"]:
                out.append(Paragraph(b, styles["Bullet"], bulletText="•"))
    elif t == "paragraph":
        out.append(H1WithRule(section["title"], styles))
        out.append(Spacer(1, 0.08 * inch))
        out.append(Paragraph(section["body"], styles["Body"]))
    elif t == "paragraph_group":
        out.append(KeepTogether([
            H1WithRule(section["title"], styles),
            Spacer(1, 0.08 * inch),
            Paragraph(section["paragraphs"][0], styles["Body"]),
        ]))
        for p in section["paragraphs"][1:]:
            out.append(Paragraph(p, styles["Body"]))
    elif t == "fee_table":
        tbl = build_fee_table(section, styles)
        # Group H1 + lead + table together so the Fees section moves as a unit.
        # If the section doesn't fit on the current page, the whole thing bumps
        # rather than orphaning the H1+lead with the table on the next page.
        # The unit-rate caption flows naturally after — it's one italic line
        # that stays with the table whenever the table places with any space
        # below it. We deliberately do NOT include the caption in this group:
        # making the block any larger triggered cascade-bumps that stranded
        # the signature ceremony onto its own page.
        block_items = [H1WithRule(section["title"], styles), Spacer(1, 0.08 * inch)]
        if section.get("lead"):
            block_items.append(Paragraph(section["lead"], styles["Body"]))
            block_items.append(Spacer(1, 0.10 * inch))
        block_items.append(tbl)
        out.append(KeepTogether(block_items))
        wb_pull = section.get("_workbook_pull")
        rate_basis = (
            wb_pull["grand_rounded_1k"]
            if (wb_pull and wb_pull.get("grand_rounded_1k"))
            else section["_rendered"]["grand_total"]
        )
        # Unit-rate footer — line-item dollars are rounded to nearest $100 (in the table
        # rows above); per-mile rate is rounded to nearest $10 because single-dollar
        # precision on a per-mile fee implies false precision and reads worse than a
        # cleaner round number. When workbook is the source, base the per-mile rate on
        # the ROUNDUP total so the unit rate is consistent with the displayed bid.
        if section.get("corridor_miles"):
            rate = rate_basis / section["corridor_miles"]
            rate_rounded = int(round(rate / 10.0)) * 10
            rate_str = f"${rate_rounded:,} per mile"
            out.append(Spacer(1, 0.06 * inch))
            out.append(Paragraph(
                f"<i>Equivalent unit rate: {rate_str} across {section['corridor_miles']} miles of corridor.</i>",
                styles["BodyLeft"]))
        out.append(Spacer(1, 0.12 * inch))
    elif t == "comparison_table":
        out.append(H1WithRule(section["title"], styles))
        out.append(Spacer(1, 0.08 * inch))
        if section.get("lead"):
            out.append(Paragraph(section["lead"], styles["Body"]))
            out.append(Spacer(1, 0.10 * inch))
        out.append(build_comparison_table(section, styles))
        out.append(Spacer(1, 0.12 * inch))
    elif t == "fee_callout":
        # Simple 3-row callout
        out.append(H1WithRule(section["title"], styles))
        out.append(Spacer(1, 0.08 * inch))
        if section.get("lead"):
            out.append(Paragraph(section["lead"], styles["Body"]))
        for k, v in section.get("rows", []):
            out.append(Paragraph(f"<b>{k}:</b> {v}", styles["BodyLeft"]))
    elif t == "signature_block":
        # The entire signing ceremony (thanks → Sincerely → firm name →
        # signature image → line → name → title → contact lines) is one
        # semantic unit and must render on the same page. Splitting the
        # ceremony — e.g. "Sincerely" + firm name on one page with the
        # signature on the next — is the worst visual outcome for a
        # client-facing proposal. Wrap the whole sequence in KeepTogether.
        block = []
        if section.get("thanks"):
            block.append(Paragraph(section["thanks"], styles["Body"]))
        block.append(Spacer(1, 0.15 * inch))
        block.append(Paragraph("Sincerely,", styles["SignClose"]))
        block.append(Paragraph("<b>STAHLY ENGINEERING &amp; ASSOCIATES</b>", styles["SignFirm"]))
        # 0.35" gap between firm-name line and signature image so the signature
        # and everything below it (name / title / contact) sit clearly separated
        # from the "STAHLY ENGINEERING & ASSOCIATES" line. Earlier 0.10" was too
        # tight — the signature image visually collided with the firm name.
        block.append(Spacer(1, 0.35 * inch))
        block.append(SignatureBlock(ctx["signatory_name"], ctx["signatory_title"],
                                    contact_lines=contact_lines,
                                    signature_image=ctx.get("signatory_signature_image") or None))
        out.append(KeepTogether(block))
    else:
        raise ValueError(f"Unknown section type: {t}")
    return out


# ============================================================
# OFFICES + SIGNATORY RESOLUTION
# ============================================================

def load_offices(skill_dir: Path):
    path = skill_dir / "references" / "offices.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["offices"]


def ordered_offices(offices_dict):
    return sorted(offices_dict.values(), key=lambda o: o["address_band_order"])


def resolve_signatory(offices_dict, office_name, signatory_name):
    if office_name not in offices_dict:
        raise ValueError(f"Office not in directory: {office_name}")
    off = offices_dict[office_name]
    for s in off["signatories"]:
        if s["name"] == signatory_name:
            return {
                "name": s["name"],
                "title": s["title"],
                "email": s.get("email", ""),
                "signature_image": s.get("signature_image", ""),  # relative to skill_dir; resolved by caller
                "office": office_name,
                "office_street": off["street"],
                "office_city_state_zip": off["city_state_zip"],
                "office_phone": off["phone"],
            }
    available = [s["name"] for s in off["signatories"]]
    raise ValueError(f"Signatory '{signatory_name}' not in {office_name} office. Known: {available}")


def signatory_contact_lines(sig):
    return [
        f"Stahly Engineering & Associates, {sig['office']} Office",
        f"{sig['office_street']}  |  {sig['office_city_state_zip']}",
        f"{sig['office_phone']}" + (f"  |  {sig['email']}" if sig["email"] else ""),
    ]


# ============================================================
# BUILD ENGINE
# ============================================================

def two_pass_build(ctx, sections, assets, offices_ordered, contact_lines, out_path: Path, corridor_map: Path | None):
    """Render cover separately, body once for page count, body again with correct totals, then merge."""
    register_fonts()
    styles = make_styles()

    cover_path = out_path.with_suffix(".cover.pdf")
    body_path  = out_path.with_suffix(".body.pdf")

    # Cover
    c = pdfcanvas.Canvas(str(cover_path), pagesize=LETTER)
    draw_cover(c, ctx, assets, offices_ordered, corridor_map)
    c.save()

    # Body — pass 1 (placeholder page count)
    body_p1 = body_path.with_suffix(".p1.pdf")
    holder1 = {"total": 99}
    _build_body(sections, styles, ctx, assets, contact_lines, body_p1, holder1)
    from pypdf import PdfReader, PdfWriter
    body_pages = len(PdfReader(str(body_p1)).pages)

    # Body — pass 2 (correct page count)
    holder2 = {"total": body_pages}
    _build_body(sections, styles, ctx, assets, contact_lines, body_path, holder2)

    # Merge cover + body
    w = PdfWriter()
    for p in PdfReader(str(cover_path)).pages: w.add_page(p)
    for p in PdfReader(str(body_path)).pages:  w.add_page(p)
    with out_path.open("wb") as f:
        w.write(f)

    # Cleanup intermediates
    for tmp in [cover_path, body_path, body_p1]:
        if tmp.exists():
            tmp.unlink()
    return body_pages + 1  # total pages including cover


def _build_body(sections, styles, ctx, assets, contact_lines, path, total_pages_holder):
    doc = BaseDocTemplate(
        str(path), pagesize=LETTER,
        leftMargin=MARGIN_L, rightMargin=MARGIN_R,
        topMargin=MARGIN_TOP, bottomMargin=MARGIN_BOT + FOOTER_BAND_H,
    )
    frame = Frame(
        MARGIN_L, MARGIN_BOT + FOOTER_BAND_H,
        PAGE_W - MARGIN_L - MARGIN_R,
        PAGE_H - MARGIN_TOP - MARGIN_BOT - FOOTER_BAND_H,
        id="body", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0,
    )
    doc.addPageTemplates([PageTemplate(id="Body", frames=[frame],
                                       onPage=make_footer_drawer(assets, total_pages_holder))])
    story = []
    # Top-of-page-2 meta block (plain Arial, body indent)
    a = ctx["addressee"]
    story.append(Paragraph(f"<b>Date:</b>  {_human_date(ctx['date'])}", styles["AddrSmall"]))
    story.append(Paragraph(f"<b>To:</b>  {a['name']}", styles["AddrSmall"]))
    story.append(Paragraph(a["org"], styles["AddrSmall"]))
    story.append(Paragraph(a["street"], styles["AddrSmall"]))
    story.append(Paragraph(a["city_state_zip"], styles["AddrSmall"]))
    story.append(Paragraph(f"<b>RE:</b>  {ctx['re_line']}", styles["AddrSmall"]))
    story.append(Spacer(1, 0.12 * inch))
    for sec in sections:
        story.extend(section_to_flowables(sec, styles, ctx, contact_lines))
    doc.build(story)


# ============================================================
# LOG FILE
# ============================================================

def write_log(out_path: Path, content_path: Path, ctx, sections, total_pages, cover_photo, writeback_docx, workbook=None):
    log_path = out_path.with_name(out_path.stem + "_log.md")
    fee_summary = ""
    workbook_summary = ""
    for sec in sections:
        if sec["type"] == "fee_table" and "_rendered" in sec:
            r = sec["_rendered"]
            fee_summary = (
                f"  Labor: ${r['total_labor']:,}\n"
                f"  Expenses: ${r['total_exp']:,}\n"
                f"  **Grand total (sum of $100-rounded line items): ${r['grand_total']:,}**\n"
            )
        if sec["type"] == "fee_table" and "_workbook_pull" in sec:
            wp = sec["_workbook_pull"]
            workbook_summary = (
                f"  Workbook: `{wp['path']}`\n"
                f"  Sheet: `{wp['sheet']}`\n"
                f"  Workbook raw total: ${wp['grand_raw']:,.2f}\n"
                f"  Workbook ROUNDUP-to-$1K total: ${wp['grand_rounded_1k']:,}\n"
            )
    lines = [
        f"# {out_path.stem} — Branded Proposal Production Log",
        "",
        f"**Built:** {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"**Skill:** stahly-proposal (v1.1)",
        f"**Content source:** `{content_path}`",
        f"**Output PDF:** `{out_path}` ({total_pages} pages)",
        f"**Workbook:** `{workbook}`" if workbook else "**Workbook:** (none — fee_table phases came from content JSON)",
        f"**Writeback docx:** `{writeback_docx}`" if writeback_docx else "**Writeback docx:** (none)",
        "",
        "## Identification",
        f"- Project: **{ctx['project_name']}**",
        f"- Client: {ctx['client_name']}",
        f"- Date: {ctx['date']}",
        f"- Office: {ctx['office']}",
        f"- Signatory: {ctx['signatory_name']}",
        "",
        "## Brand compliance",
        "- Stahly Blue #00548C · Tan #BABAB1 · Cream #E9E6E1 (Identity Guide 2025)",
        "- Headlines: Rockwell Bold · Body: Arial Regular",
        "- Cover hero logo: `assets/StahlyLogo_EO_official.png` (transparent)",
        "- Footer logo: `assets/StahlyLogo_Artboard1_official.png` (transparent)",
        "",
        "## Fee math",
        fee_summary if fee_summary else "  (no fee table in this proposal)",
        "",
        "## Workbook lineage",
        workbook_summary if workbook_summary else "  (fee_table came from content JSON, not workbook)",
        "",
        "## Cover photo",
        f"- {cover_photo}" if cover_photo else "- (none — clean blue/cream cover)",
        "",
        "## Reproduction",
        "```",
        f'python build.py --content "{content_path}" --out "{out_path}"' +
        (f' --cover-photo "{cover_photo}"' if cover_photo else "") +
        (f' --workbook "{workbook}"' if workbook else "") +
        (f' --writeback-docx "{writeback_docx}"' if writeback_docx else ""),
        "```",
        "",
        "## QA checklist",
        f"Render PNGs with `scripts/render_qa.py` and walk through `references/qa_checklist.md` before declaring final.",
    ]
    log_path.write_text("\n".join(lines), encoding="utf-8")
    return log_path


# ============================================================
# CLI
# ============================================================

def _apply_workbook_pull(sections, workbook_path: str) -> None:
    """Replace the fee_table section's `phases` with phase data read live from
    the Stahly bid workbook. Preserves the section's title/lead/corridor_miles
    from the content JSON. Raises if there is no fee_table section to populate.

    Prints a side-by-side comparison if the content JSON already contained
    phases — surfaces drift between intake and workbook so the user can catch
    a stale content JSON.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from bid_workbook import fee_table_payload, read_workbook  # local import

    fee_section = next((s for s in sections if s.get("type") == "fee_table"), None)
    if fee_section is None:
        raise ValueError(
            "--workbook was provided but the content JSON has no fee_table section. "
            "Add a `fee_table` section to the JSON (title/lead/corridor_miles are "
            "carried through; phases will be replaced by the workbook)."
        )

    audit = read_workbook(workbook_path)
    if audit["warnings"]:
        print("Workbook audit warnings (fix before finalizing):", file=sys.stderr)
        for w in audit["warnings"]:
            print(f"  - {w}", file=sys.stderr)

    pulled = fee_table_payload(workbook_path)

    # Drift report: compare intake phases (if any) against workbook phases
    intake_phases = fee_section.get("phases") or []
    if intake_phases:
        intake_total = sum(int(p.get("labor", 0)) + int(p.get("expenses", 0)) for p in intake_phases)
        workbook_total = sum(int(p["labor"]) + int(p["expenses"]) for p in pulled["phases"])
        if abs(intake_total - workbook_total) >= 1:
            print(
                f"NOTE: intake fee_table total (${intake_total:,}) differs from "
                f"workbook (${workbook_total:,}). Using workbook.",
                file=sys.stderr,
            )

    fee_section["phases"] = pulled["phases"]
    fee_section["_workbook_pull"] = {
        "path": audit["metadata"]["workbook_path"],
        "sheet": audit["metadata"]["sheet_name"],
        "grand_raw": audit["totals"]["grand"],
        "grand_rounded_1k": audit["totals"]["rounded_1k"],
    }


def main():
    ap = argparse.ArgumentParser(description="Build a Stahly branded proposal PDF.")
    ap.add_argument("--content", required=True, help="Path to the content JSON (see content_schema.md).")
    ap.add_argument("--out", required=True, help="Output PDF path.")
    ap.add_argument("--cover-photo", default=None, help="Optional cover photo image path.")
    ap.add_argument("--skill-dir", default=None, help="Skill directory (default: this script's grandparent).")
    ap.add_argument("--writeback-docx", default=None, help="Optional source docx to update with intake overrides (writeback).")
    ap.add_argument(
        "--workbook",
        default=None,
        help="Optional Stahly bid workbook (.xlsx). When set, fee_table phases are "
             "pulled live from the workbook instead of from the content JSON. "
             "The content JSON's fee_table section still supplies title/lead/corridor_miles.",
    )
    args = ap.parse_args()

    out_path = Path(os.environ.get("STAHLY_PROPOSAL_OUT", args.out))
    if not out_path.suffix:
        out_path = out_path.with_suffix(".pdf")
    skill_dir = Path(args.skill_dir) if args.skill_dir else Path(__file__).resolve().parent.parent
    content_path = Path(args.content)

    # Load content
    content = json.loads(content_path.read_text(encoding="utf-8"))
    sections = content.pop("sections")
    ctx = content

    # Workbook pull (v1.1) — replaces fee_table phases with live workbook data
    if args.workbook:
        _apply_workbook_pull(sections, args.workbook)

    # Load offices + resolve signatory
    offices = load_offices(skill_dir)
    sig = resolve_signatory(offices, ctx["office"], ctx["signatory_name"])
    # Honor an explicit signatory_title in the content JSON if provided; fall
    # back to the office-wide title in offices.json. Per-proposal overrides
    # are needed when a signatory's title varies by deliverable (e.g. the
    # contract sig block uses one form, the proposal sig block uses another).
    ctx["signatory_title"] = ctx.get("signatory_title") or sig["title"]
    # Stash the signing limit for the post-build authority check.
    ctx["_signatory_signing_limit"] = sig.get("signing_limit")
    # Resolve signature image path relative to skill_dir; pass to SignatureBlock via ctx
    if sig.get("signature_image"):
        sig_path = skill_dir / sig["signature_image"]
        ctx["signatory_signature_image"] = str(sig_path) if sig_path.exists() else ""
        if not sig_path.exists():
            print(f"Warning: signature image not found at {sig_path}", file=sys.stderr)
    else:
        ctx["signatory_signature_image"] = ""
    contact_lines = signatory_contact_lines(sig)

    # Assets
    assets = {
        "hero_logo":   skill_dir / "assets" / "StahlyLogo_EO_official.png",
        "footer_logo": skill_dir / "assets" / "StahlyLogo_Artboard1_official.png",
    }
    for k, p in assets.items():
        if not p.exists():
            raise FileNotFoundError(f"Required asset missing: {p}\nContact Marketing (marketing@seaeng.com) for official logo files.")

    # Cover photo
    cover_photo = args.cover_photo or (ctx.get("cover_photo", {}) or {}).get("path")
    if cover_photo and not Path(cover_photo).exists():
        print(f"Warning: cover photo not found: {cover_photo}", file=sys.stderr)
        cover_photo = None

    # Build
    out_path.parent.mkdir(parents=True, exist_ok=True)
    offices_ord = ordered_offices(offices)
    total_pages = two_pass_build(
        ctx, sections, assets, offices_ord, contact_lines, out_path,
        Path(cover_photo) if cover_photo else None,
    )

    # Log
    log = write_log(out_path, content_path, ctx, sections, total_pages, cover_photo, args.writeback_docx, workbook=args.workbook)

    # Echo fee math + paths
    grand_total = None
    for sec in sections:
        if sec["type"] == "fee_table" and "_rendered" in sec:
            r = sec["_rendered"]
            grand_total = r["grand_total"]
            print(f"Fee math: Labor ${r['total_labor']:,}  Expenses ${r['total_exp']:,}  Total ${r['grand_total']:,}")
            # Margin-tracking line — when a bid workbook was pulled, the
            # workbook's raw total is the internal effort estimate; the
            # displayed grand total may differ (lump-sum rounding or an
            # intentional absorb to land within a signing-authority cap).
            # Surface the delta so the user knows how much margin the
            # displayed price already absorbs.
            wp = sec.get("_workbook_pull") or {}
            wb_raw = wp.get("grand_raw")
            if wb_raw and abs(wb_raw - r["grand_total"]) >= 100:
                delta = wb_raw - r["grand_total"]
                sign = "absorbed" if delta > 0 else "headroom"
                print(
                    f"  Internal effort estimate: ${wb_raw:,.0f}  /  Displayed: ${r['grand_total']:,}  /  "
                    f"Delta: ${abs(delta):,.0f} {sign}"
                )
        if sec["type"] == "fee_table" and "_workbook_pull" in sec:
            wp = sec["_workbook_pull"]
            print(
                f"Workbook lineage: {wp['sheet']!r} -> "
                f"raw ${wp['grand_raw']:,.0f} / rounded ${wp['grand_rounded_1k']:,}"
            )
    # Signing-authority check — warn if the chosen signatory's signing_limit
    # is below the displayed grand total. Prevents the "we built the PDF then
    # noticed the office manager couldn't actually sign it" cycle.
    limit = ctx.get("_signatory_signing_limit")
    if limit is not None and grand_total is not None and grand_total > limit:
        sig_name = ctx.get("signatory_name", "(unknown)")
        sig_title = ctx.get("signatory_title", "(unknown)")
        print(
            f"\n!!! SIGNING AUTHORITY WARNING !!!\n"
            f"  Grand total ${grand_total:,} EXCEEDS the signing limit of ${limit:,} for\n"
            f"  {sig_name} ({sig_title}).\n"
            f"  Either reduce the total to within the limit, or change the signatory to\n"
            f"  someone with sufficient authority (e.g. the CFO). Update offices.json\n"
            f"  signing_limit values if Stahly's authority matrix has changed.\n",
            file=sys.stderr,
        )
    print(f"PDF: {out_path}  ({total_pages} pages)")
    print(f"Log: {log}")
    if args.writeback_docx:
        print(f"NOTE: --writeback-docx supplied but the writeback engine isn't wired into v1.0 build.py yet.")
        print(f"      Use scripts/apply_docx_writeback.py (planned v1.1) or apply edits manually for now.")

if __name__ == "__main__":
    main()
