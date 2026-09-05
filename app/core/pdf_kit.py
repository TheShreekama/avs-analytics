"""ReportLab layout primitives for the management report.

Separates *how the page is drawn* from *what it says*: this module owns styles,
page furniture, navigation (bookmarks, outline, contents, cross-links) and the
table/KPI building blocks; :mod:`app.core.exporter` owns the report content.

Navigation is real PDF machinery, not styled text — ``bookmarkPage`` named
destinations, ``addOutlineEntry`` for the viewer's bookmark pane, and
``<a href="#dest">`` link annotations.  Page numbers in the contents and the
"Page 3 of 24" footer are resolved by building the document more than once, so
they stay correct however much the content grows.
"""
from __future__ import annotations

import io
from datetime import datetime

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (BaseDocTemplate, Flowable, Frame, Image, NextPageTemplate,
                                PageBreak, PageTemplate, Paragraph, Spacer, Table,
                                TableStyle)
from reportlab.platypus.tableofcontents import TableOfContents

from ..config import APP_NAME, APP_VERSION, PALETTE

PORTRAIT = "portrait"
LANDSCAPE = "landscape"

PRIMARY = colors.HexColor(PALETTE["primary"])
PRIMARY_DARK = colors.HexColor(PALETTE["primary_dark"])
INK = colors.HexColor(PALETTE["ink"])
MUTED = colors.HexColor(PALETTE["muted"])
BORDER = colors.HexColor(PALETTE["border"])
BAND = colors.HexColor("#F5F7FA")
SEV_COLOR = {"positive": colors.HexColor(PALETTE["good"]),
             "warning": colors.HexColor(PALETTE["warn"]),
             "critical": colors.HexColor(PALETTE["bad"]),
             "info": PRIMARY}

_MARGIN = 1.5 * cm
_TOP_MARGIN = 2.0 * cm
_BOTTOM_MARGIN = 1.5 * cm

#: Usable text width on each orientation, for sizing tables and images.
CONTENT_WIDTH = {PORTRAIT: A4[0] - 2 * _MARGIN,
                 LANDSCAPE: landscape(A4)[0] - 2 * _MARGIN}


# --------------------------------------------------------------------------- #
# Styles
# --------------------------------------------------------------------------- #
def styles():
    ss = getSampleStyleSheet()
    # Leading is inherited, so every style that grows the font size has to set
    # its own or the next paragraph prints through the descenders.
    ss.add(ParagraphStyle("CoverTitle", parent=ss["Title"], fontSize=30, leading=36,
                          textColor=PRIMARY_DARK, alignment=TA_CENTER, spaceAfter=8))
    ss.add(ParagraphStyle("CoverSub", parent=ss["BodyText"], fontSize=13,
                          textColor=MUTED, alignment=TA_CENTER, leading=19))
    ss.add(ParagraphStyle("PartTitle", parent=ss["Title"], fontSize=20, leading=25,
                          textColor=PRIMARY_DARK, alignment=TA_LEFT, spaceAfter=3))
    ss.add(ParagraphStyle("H1", parent=ss["Title"], fontSize=19, leading=23,
                          textColor=PRIMARY_DARK, alignment=TA_LEFT, spaceAfter=2,
                          spaceBefore=0))
    ss.add(ParagraphStyle("H2", parent=ss["Heading2"], fontSize=12.5,
                          textColor=PRIMARY_DARK, spaceBefore=12, spaceAfter=5))
    ss.add(ParagraphStyle("H3", parent=ss["Heading3"], fontSize=10.5, textColor=INK,
                          spaceBefore=8, spaceAfter=3))
    ss.add(ParagraphStyle("Body2", parent=ss["BodyText"], fontSize=9.5, leading=13.5,
                          textColor=INK, spaceAfter=0))
    ss.add(ParagraphStyle("Muted", parent=ss["BodyText"], fontSize=8.5, leading=12,
                          textColor=MUTED, spaceAfter=0))
    ss.add(ParagraphStyle("Nav", parent=ss["BodyText"], fontSize=8.5, leading=12,
                          textColor=PRIMARY, alignment=TA_RIGHT, spaceAfter=0))
    ss.add(ParagraphStyle("Cell", parent=ss["BodyText"], fontSize=7.5, leading=9.5,
                          textColor=INK, spaceAfter=0))
    ss.add(ParagraphStyle("CellHead", parent=ss["BodyText"], fontSize=7.5, leading=9.5,
                          textColor=colors.white, spaceAfter=0))
    ss.add(ParagraphStyle("TOC1", parent=ss["BodyText"], fontSize=11, leading=20,
                          textColor=PRIMARY_DARK, fontName="Helvetica-Bold"))
    ss.add(ParagraphStyle("TOC2", parent=ss["BodyText"], fontSize=9.5, leading=16,
                          textColor=INK, leftIndent=14))
    return ss


# --------------------------------------------------------------------------- #
# Navigation
# --------------------------------------------------------------------------- #
class Anchor(Flowable):
    """A named PDF destination, plus its bookmark-pane and contents entries.

    Zero height, so it can sit immediately above the heading it names without
    disturbing the layout.  ``level`` drives the indent in both the viewer's
    outline and the contents page; ``in_toc=False`` registers a destination that
    links can target without listing it in the contents.
    """

    def __init__(self, key: str, title: str, level: int = 0, in_toc: bool = True):
        super().__init__()
        self.key, self.title, self.level, self.in_toc = key, title, level, in_toc
        self.width = self.height = 0

    def draw(self) -> None:
        self.canv.bookmarkPage(self.key)
        # The key must stay a str: handed bytes, ReportLab labels the outline
        # entry with the key instead of the title.
        self.canv.addOutlineEntry(self.title, self.key, self.level, 0)


def link(text: str, dest: str, style, bold: bool = True) -> Paragraph:
    """A clickable internal link to a named destination."""
    body = f"<b>{text}</b>" if bold else text
    return Paragraph(f'<a href="#{dest}" color="#{PRIMARY.hexval()[2:]}">{body}</a>', style)


def nav_bar(ss, title: str, links: list[tuple[str, str]],
            width: float | None = None) -> Table:
    """A section heading with its cross-links ranged right on the same line.

    ``links`` is a list of (label, destination) pairs — "View drill-down →",
    "← Back to AVS Migrations", "Contents".  ``width`` must match the page the
    bar is drawn on, or the rule under it stops short of the margin.
    """
    width = width or CONTENT_WIDTH[PORTRAIT]
    chips = " &nbsp;·&nbsp; ".join(
        f'<a href="#{dest}" color="#{PRIMARY.hexval()[2:]}"><b>{label}</b></a>'
        for label, dest in links)
    row = [Paragraph(title, ss["H1"]), Paragraph(chips, ss["Nav"])]
    heading = min(11.2 * cm, width * 0.62)
    t = Table([row], colWidths=[heading, width - heading])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, -1), 1.2, PRIMARY),
    ]))
    return t


def contents(ss) -> TableOfContents:
    toc = TableOfContents()
    toc.levelStyles = [ss["TOC1"], ss["TOC2"]]
    toc.dotsMinLevel = 0
    return toc


# --------------------------------------------------------------------------- #
# Page furniture
# --------------------------------------------------------------------------- #
class ReportDoc(BaseDocTemplate):
    """Two-pass document: resolves contents page numbers and the page total.

    ``multiBuild`` already re-runs the story until the contents stop moving, so
    the page count from the previous pass is available to the footer — which is
    what makes "Page 3 of 24" and the contents' page numbers agree with the
    document that actually comes out, however much the content grows.
    """

    def __init__(self, buf, header_title: str, **kw):
        super().__init__(buf, pagesize=A4, topMargin=_TOP_MARGIN,
                         bottomMargin=_BOTTOM_MARGIN, leftMargin=_MARGIN,
                         rightMargin=_MARGIN, **kw)
        self.header_title = header_title
        self.total_pages = 0
        self._section = ""
        portrait_frame = Frame(_MARGIN, _BOTTOM_MARGIN, A4[0] - 2 * _MARGIN,
                               A4[1] - _TOP_MARGIN - _BOTTOM_MARGIN, id="p")
        land = landscape(A4)
        landscape_frame = Frame(_MARGIN, _BOTTOM_MARGIN, land[0] - 2 * _MARGIN,
                                land[1] - _TOP_MARGIN - _BOTTOM_MARGIN, id="l")
        self.addPageTemplates([
            # Drawn at page *end*: the running section label then names what the
            # page actually holds, not the section that preceded it.
            PageTemplate(id=PORTRAIT, frames=[portrait_frame], pagesize=A4,
                         onPageEnd=self._furniture),
            PageTemplate(id=LANDSCAPE, frames=[landscape_frame], pagesize=land,
                         onPageEnd=self._furniture),
        ])

    def beforeDocument(self) -> None:
        # multiBuild lays the story out repeatedly on this same document, so the
        # running section label has to start each pass empty or the cover
        # inherits the last section of the previous pass.
        self._section = ""

    def afterFlowable(self, flowable) -> None:
        if isinstance(flowable, Anchor):
            if flowable.level == 0:
                self._section = flowable.title
            if flowable.in_toc:
                self.notify("TOCEntry",
                            (flowable.level, flowable.title, self.page, flowable.key))

    def _furniture(self, canvas, doc) -> None:
        w, h = canvas._pagesize
        canvas.saveState()
        canvas.setFillColor(PRIMARY)
        canvas.rect(0, h - 0.95 * cm, w, 0.95 * cm, fill=1, stroke=0)
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 9)
        canvas.drawString(_MARGIN, h - 0.62 * cm, APP_NAME)
        canvas.setFont("Helvetica", 8)
        canvas.drawRightString(w - _MARGIN, h - 0.62 * cm, self.header_title)

        canvas.setStrokeColor(BORDER)
        canvas.setLineWidth(0.5)
        canvas.line(_MARGIN, 1.05 * cm, w - _MARGIN, 1.05 * cm)
        canvas.setFillColor(MUTED)
        canvas.setFont("Helvetica", 7)
        canvas.drawString(_MARGIN, 0.68 * cm,
                          f"{APP_NAME} v{APP_VERSION} · generated "
                          f"{datetime.now():%d %b %Y %H:%M}")
        if self._section:
            canvas.drawCentredString(w / 2, 0.68 * cm, self._section)
        total = f" of {self.total_pages}" if self.total_pages else ""
        canvas.drawRightString(w - _MARGIN, 0.68 * cm, f"Page {doc.page}{total}")
        canvas.restoreState()


def build(make_story, header_title: str, doc_title: str) -> bytes:
    """Render the document, resolving contents page numbers and the page total.

    ``make_story`` is called once per build and must return a *fresh* list of
    flowables: laying a flowable out consumes it (tables record where they
    split, paragraphs cache their wrap), so the same objects cannot be built
    twice.  The first build settles the contents entries and tells us how long
    the report runs; the second prints that total in every footer.  Adding
    "of 24" to a footer cannot change the flow, so both builds are the same
    length.
    """
    def _doc(buf) -> ReportDoc:
        return ReportDoc(buf, header_title, title=doc_title, author=APP_NAME,
                         subject=header_title)

    probe = _doc(io.BytesIO())
    probe.multiBuild(make_story())

    buf = io.BytesIO()
    final = _doc(buf)
    final.total_pages = probe.page
    final.multiBuild(make_story())
    return buf.getvalue()


# --------------------------------------------------------------------------- #
# Content blocks
# --------------------------------------------------------------------------- #
def kpi_cards(tiles: list[tuple[str, str, str]], ss, per_row: int = 3,
              width: float | None = None) -> Table:
    """A grid of KPI cards: (label, value, note) each in its own bordered cell."""
    width = width or CONTENT_WIDTH[PORTRAIT]
    cells = [Paragraph(
        f'<font color="#{MUTED.hexval()[2:]}" size=7.5>{label.upper()}</font><br/>'
        f'<font color="#{PRIMARY_DARK.hexval()[2:]}" size=17><b>{value}</b></font><br/>'
        f'<font color="#{MUTED.hexval()[2:]}" size=7>{note}</font>', ss["Body2"])
        for label, value, note in tiles]
    rows = [cells[i:i + per_row] for i in range(0, len(cells), per_row)]
    if rows and len(rows[-1]) < per_row:
        rows[-1] += [""] * (per_row - len(rows[-1]))
    t = Table(rows, colWidths=[width / per_row] * per_row)
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, BORDER),
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t


def df_table(df: pd.DataFrame, ss, col_widths=None, align_right: list[int] | None = None,
             font_size: float = 7.5) -> Table:
    """A readable data table: white-on-primary header, zebra rows, repeated header."""
    head = [Paragraph(f"<b>{c}</b>", _sized(ss["CellHead"], font_size)) for c in df.columns]
    cell = _sized(ss["Cell"], font_size)
    body = [[Paragraph("" if pd.isna(v) else str(v), cell) for v in row]
            for row in df.values.tolist()]
    t = Table([head] + body, colWidths=col_widths, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), PRIMARY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, BAND]),
        ("LINEBELOW", (0, 0), (-1, -1), 0.3, BORDER),
        ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 4.5), ("RIGHTPADDING", (0, 0), (-1, -1), 4.5),
    ]
    for col in align_right or []:
        style.append(("ALIGN", (col, 1), (col, -1), "RIGHT"))
    t.setStyle(TableStyle(style))
    # A table narrower than the frame centres itself by default, which reads as
    # a drifting column against left-aligned headings.
    t.hAlign = "LEFT"
    return t


def _sized(base: ParagraphStyle, size: float) -> ParagraphStyle:
    if size == base.fontSize:
        return base
    return ParagraphStyle(f"{base.name}{size}", parent=base, fontSize=size,
                          leading=size * 1.28)


def image(png: bytes, width_cm: float = 17.0):
    """PNG bytes from :mod:`app.ui.pdf_charts` as an aspect-preserved Image."""
    img = Image(io.BytesIO(png))
    ratio = (img.imageHeight / img.imageWidth) if img.imageWidth else 0.36
    img.drawWidth = width_cm * cm
    img.drawHeight = width_cm * cm * ratio
    img.hAlign = "LEFT"
    return img


def spacer(cm_height: float = 0.35) -> Spacer:
    return Spacer(1, cm_height * cm)


def page_break() -> PageBreak:
    return PageBreak()


def turn(orientation: str) -> list:
    """Start a new page in the given orientation.

    ``NextPageTemplate`` only takes effect at the following page break, so the
    two always travel together.
    """
    return [NextPageTemplate(orientation), PageBreak()]
