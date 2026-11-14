"""PDF rendering of a case report (ABB-26 follow-up, ADR-0007).

Renders the same neutral ``blocks`` the Markdown and HTML renderers use, so the three documents cannot
disagree. Pure and offline: ReportLab only, bundled Bitstream Vera fonts, no network, no external
viewer. ``invariant=1`` removes the creation date and random document ID, so the same snapshot and the
same ReportLab version give the same bytes; the bytes are stored once with the report version (the API
never re-renders a stored version) and covered by ``pdf_sha256``.
"""
from __future__ import annotations

import io
import re
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.lib.fonts import addMapping
import reportlab

RENDERER = f"reportlab {reportlab.Version}"
_REGULAR, _BOLD = "CRVera", "CRVera-Bold"
_FONT_DIR = __import__("os").path.join(__import__("os").path.dirname(reportlab.__file__), "fonts")
_REPLACE = {"→": "->", "⅝": "5/8", "½": "1/2", "…": "...", "‑": "-", " ": " ", "≥": ">=", "≤": "<="}
_TOKEN = re.compile(r"\*\*(.+?)\*\*")
_registered = False


def _register() -> None:
    global _registered
    if _registered:
        return
    for name, file in ((_REGULAR, "Vera.ttf"), (_BOLD, "VeraBd.ttf")):
        pdfmetrics.registerFont(TTFont(name, f"{_FONT_DIR}/{file}"))
    addMapping(_REGULAR, 0, 0, _REGULAR)
    addMapping(_REGULAR, 1, 0, _BOLD)
    addMapping(_REGULAR, 0, 1, _REGULAR)
    addMapping(_REGULAR, 1, 1, _BOLD)
    _registered = True


def _clean(value: object) -> str:
    """Printable text the bundled font can draw; unsupported characters become '?', never boxes."""
    face = pdfmetrics.getFont(_REGULAR).face
    out = []
    for ch in str(value):
        ch = _REPLACE.get(ch, ch)
        for c in ch:
            out.append(c if c in "\n\t" or ord(c) in face.charToGlyph else "?")
    return "".join(out)


def _para(value: object, style: ParagraphStyle) -> Paragraph:
    text = escape(_clean(value)).replace("\n", "<br/>")
    return Paragraph(_TOKEN.sub(r"<b>\1</b>", text), style)


def render_pdf(blocks: list[tuple], title: str) -> bytes:
    _register()
    base = ParagraphStyle("base", fontName=_REGULAR, fontSize=9, leading=12, spaceAfter=4, wordWrap="CJK")
    styles = {
        "h1": ParagraphStyle("h1", parent=base, fontName=_BOLD, fontSize=18, leading=22, spaceAfter=8),
        "h2": ParagraphStyle("h2", parent=base, fontName=_BOLD, fontSize=13, leading=16, spaceBefore=12, spaceAfter=5),
        "h3": ParagraphStyle("h3", parent=base, fontName=_BOLD, fontSize=10.5, leading=13, spaceBefore=8, spaceAfter=3),
        "p": base,
        "cell": ParagraphStyle("cell", parent=base, fontSize=7.5, leading=9.5, spaceAfter=0),
        "head": ParagraphStyle("head", parent=base, fontName=_BOLD, fontSize=7.5, leading=9.5, spaceAfter=0),
        "li": ParagraphStyle("li", parent=base, leftIndent=10, bulletIndent=2, spaceAfter=2),
    }
    width = A4[0] - 30 * mm
    story: list = []
    for blk in blocks:
        kind = blk[0]
        if kind in ("h1", "h2", "h3", "p"):
            story.append(_para(blk[1], styles[kind]))
        elif kind == "kv":
            rows = [[_para(k, styles["head"]), _para(v, styles["cell"])] for k, v in blk[1]]
            t = Table(rows, colWidths=[width * 0.32, width * 0.68])
            t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.grey)]))
            story += [t, Spacer(1, 4)]
        elif kind == "ul":
            story += [Paragraph(f"&bull; {escape(_clean(x))}", styles["li"]) for x in blk[1]]
        elif kind == "table":
            _, headers, rows = blk
            n = len(headers)
            data = [[_para(h, styles["head"]) for h in headers]] + [[_para(c, styles["cell"]) for c in row] for row in rows]
            t = Table(data, colWidths=[width / n] * n, repeatRows=1)
            t.setStyle(TableStyle([
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8f0ea")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ]))
            story += [t, Spacer(1, 5)]
    footer_text = _clean(title)

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont(_REGULAR, 7)
        canvas.drawString(15 * mm, 8 * mm, footer_text)
        canvas.drawRightString(A4[0] - 15 * mm, 8 * mm, f"{doc.page}")
        canvas.restoreState()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=14 * mm,
                            bottomMargin=16 * mm, title=_clean(title), author="CropStory", subject="Case report",
                            invariant=1)
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()
