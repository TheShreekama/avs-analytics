"""Executive PDF export engine (ReportLab + Plotly/kaleido static images).

Produces a leadership-ready PDF: cover, executive summary, KPI grid, key charts,
deterministic insights, and key tables, with a generation timestamp.  Fully
local — no network, no external services.
"""
from __future__ import annotations

import io
from datetime import datetime

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (BaseDocTemplate, Frame, Image, PageBreak, PageTemplate,
                                Paragraph, Spacer, Table, TableStyle)

from ..config import APP_NAME, APP_VERSION, PALETTE
from ..ui import charts
from . import analytics, insights as insights_mod
from .metrics import fmt_currency, fmt_int, headline_kpis

_PRIMARY = colors.HexColor(PALETTE["primary"])
_PRIMARY_DARK = colors.HexColor(PALETTE["primary_dark"])
_INK = colors.HexColor(PALETTE["ink"])
_MUTED = colors.HexColor(PALETTE["muted"])
_BORDER = colors.HexColor(PALETTE["border"])
_SEV_COLOR = {"positive": colors.HexColor(PALETTE["good"]),
              "warning": colors.HexColor(PALETTE["warn"]),
              "critical": colors.HexColor(PALETTE["bad"]),
              "info": _PRIMARY}


def _styles():
    ss = getSampleStyleSheet()
    ss.add(ParagraphStyle("H1", parent=ss["Title"], textColor=_PRIMARY_DARK, fontSize=22,
                          spaceAfter=4, alignment=TA_LEFT))
    ss.add(ParagraphStyle("H2", parent=ss["Heading2"], textColor=_PRIMARY_DARK, fontSize=14,
                          spaceBefore=10, spaceAfter=6))
    ss.add(ParagraphStyle("Body2", parent=ss["BodyText"], fontSize=10, leading=14, textColor=_INK))
    ss.add(ParagraphStyle("Muted", parent=ss["BodyText"], fontSize=9, textColor=_MUTED))
    ss.add(ParagraphStyle("CoverTitle", parent=ss["Title"], fontSize=30, textColor=_PRIMARY_DARK,
                          alignment=TA_CENTER, spaceAfter=8))
    ss.add(ParagraphStyle("CoverSub", parent=ss["BodyText"], fontSize=13, textColor=_MUTED,
                          alignment=TA_CENTER))
    return ss


def _header_footer(canvas, doc):
    canvas.saveState()
    w, h = A4
    canvas.setFillColor(_PRIMARY)
    canvas.rect(0, h - 1.1 * cm, w, 1.1 * cm, fill=1, stroke=0)
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 10)
    canvas.drawString(1.6 * cm, h - 0.72 * cm, APP_NAME)
    canvas.setFont("Helvetica", 8)
    canvas.drawRightString(w - 1.6 * cm, h - 0.72 * cm, "Executive Report")
    canvas.setFillColor(_MUTED)
    canvas.setFont("Helvetica", 7.5)
    canvas.drawString(1.6 * cm, 0.7 * cm,
                      f"Generated {datetime.now():%Y-%m-%d %H:%M} · {APP_NAME} v{APP_VERSION}")
    canvas.drawRightString(w - 1.6 * cm, 0.7 * cm, f"Page {doc.page}")
    canvas.restoreState()


def _kpi_table(kpis: dict, ss) -> Table:
    rows = [
        ["Nominations", fmt_int(kpis["nominations"]), "Accounts", fmt_int(kpis["accounts"])],
        ["Approved", fmt_int(kpis["approved"]), "Closed", fmt_int(kpis["closed"])],
        ["Open / In-flight", fmt_int(kpis["open"]), "Closure Rate", f'{kpis["closure_rate"]:.0f}%'],
        ["Total ACR", fmt_currency(kpis["total_acr"]), "Total Cores", fmt_int(kpis["total_cores"])],
        ["Median Age (open)", f'{kpis["median_age_days"]:.0f} d', "Median Cycle Time",
         f'{kpis["median_cycle_days"]:.0f} d'],
    ]
    data = []
    for r in rows:
        data.append([Paragraph(f'<font color="#5C6470" size=8>{r[0]}</font><br/>'
                               f'<b><font size=13>{r[1]}</font></b>', ss["Body2"]),
                     Paragraph(f'<font color="#5C6470" size=8>{r[2]}</font><br/>'
                               f'<b><font size=13>{r[3]}</font></b>', ss["Body2"])])
    t = Table(data, colWidths=[8.4 * cm, 8.4 * cm])
    t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, _BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, _BORDER),
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
    ]))
    return t


def _df_table(df: pd.DataFrame, ss, col_widths=None, header_bg=_PRIMARY) -> Table:
    head = [Paragraph(f'<b><font color="white" size=8>{c}</font></b>', ss["Body2"])
            for c in df.columns]
    body = [[Paragraph(f'<font size=8>{"" if pd.isna(v) else v}</font>', ss["Body2"])
             for v in row] for row in df.values.tolist()]
    t = Table([head] + body, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), header_bg),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F7FA")]),
        ("GRID", (0, 0), (-1, -1), 0.4, _BORDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
    ]))
    return t


def _img(fig, width_cm=17.0, height_px=330, width_px=950):
    png = charts.to_png(fig, width=width_px, height=height_px, scale=2.0)
    img = Image(io.BytesIO(png))
    img.drawWidth = width_cm * cm
    img.drawHeight = width_cm * cm * (height_px / width_px)
    return img


def build_executive_pdf(ctx, where: str = "", scope_label: str = "All data") -> bytes:
    """Build the executive PDF and return the bytes."""
    ss = _styles()
    con = ctx.con
    fact = analytics.select_all(con, where)
    kpis = headline_kpis(fact)
    ins = insights_mod.generate_insights(fact)

    story: list = []

    # ---- Cover ---------------------------------------------------------- #
    story += [Spacer(1, 5 * cm),
              Paragraph("AVS Migration Analytics", ss["CoverTitle"]),
              Paragraph("Executive Summary Report", ss["CoverSub"]),
              Spacer(1, 0.8 * cm),
              Paragraph(f"Scope: {scope_label}", ss["CoverSub"]),
              Paragraph(f"Dataset: {ctx.filename} &nbsp;·&nbsp; As-of {pd.Timestamp(ctx.as_of):%d %b %Y}",
                        ss["CoverSub"]),
              Spacer(1, 0.3 * cm),
              Paragraph(f"Generated {datetime.now():%d %b %Y, %H:%M}", ss["CoverSub"]),
              PageBreak()]

    # ---- Executive summary --------------------------------------------- #
    story.append(Paragraph("Executive Summary", ss["H1"]))
    summary = (
        f"This report covers <b>{fmt_int(kpis['nominations'])}</b> AVS migration nominations "
        f"across <b>{fmt_int(kpis['accounts'])}</b> accounts. "
        f"<b>{fmt_int(kpis['approved'])}</b> are approved and "
        f"<b>{fmt_int(kpis['closed'])}</b> are closed "
        f"(closure rate <b>{kpis['closure_rate']:.0f}%</b>), with "
        f"<b>{fmt_int(kpis['open'])}</b> in flight. "
        f"Total ACR under management is <b>{fmt_currency(kpis['total_acr'])}</b> "
        f"across <b>{fmt_int(kpis['total_cores'])}</b> cores. "
        f"The median open-item age is <b>{kpis['median_age_days']:.0f} days</b>.")
    story += [Paragraph(summary, ss["Body2"]), Spacer(1, 0.4 * cm),
              Paragraph("Key Metrics", ss["H2"]), _kpi_table(kpis, ss), Spacer(1, 0.4 * cm)]

    # Top insights
    story.append(Paragraph("Key Insights", ss["H2"]))
    for ins_item in ins[:8]:
        c = _SEV_COLOR.get(ins_item.severity, _PRIMARY)
        story.append(Paragraph(
            f'<font color="#{c.hexval()[2:]}">&#9632;</font> '
            f'<b>{ins_item.title}.</b> {_strip(ins_item.detail)}', ss["Body2"]))
        story.append(Spacer(1, 0.12 * cm))
    story.append(PageBreak())

    # ---- Charts --------------------------------------------------------- #
    story.append(Paragraph("Portfolio Overview", ss["H1"]))

    status = analytics.count_by(con, where, "migration_status_label")
    if not status.empty:
        story += [Paragraph("Nominations by Migration Status", ss["H2"]),
                  _img(charts.donut(status, "category", "count", height=320)),
                  Spacer(1, 0.3 * cm)]

    reg = analytics.count_by(con, where, "ww_region")
    if not reg.empty:
        story += [Paragraph("Nominations by Region", ss["H2"]),
                  _img(charts.bar(reg, "category", "count", horizontal=True, height=300)),
                  Spacer(1, 0.3 * cm)]
    story.append(PageBreak())

    # EOS heatmap + approval trend
    pivot = analytics.crosstab(con, where, "ww_region", "eos_status")
    if not pivot.empty:
        story += [Paragraph("EOS Status by Region", ss["H2"]),
                  _img(charts.heatmap(pivot, height=300)), Spacer(1, 0.3 * cm)]

    trend = analytics.timeseries(con, where, "approval_date", "month")
    if not trend.empty:
        story += [Paragraph("Monthly Approval Trend", ss["H2"]),
                  _img(charts.line(trend, "period", "value", area=True, height=300)),
                  Spacer(1, 0.3 * cm)]
    story.append(PageBreak())

    # ---- Key tables ----------------------------------------------------- #
    story.append(Paragraph("Operational Detail", ss["H1"]))

    cr = analytics.closure_rate_by(con, where, "ww_region")
    if not cr.empty:
        cr = cr.rename(columns={"category": "Region", "total": "Total", "closed": "Closed",
                                "closure_rate": "Closure %"})
        story += [Paragraph("Closure Rate by Region", ss["H2"]),
                  _df_table(cr.head(10), ss, col_widths=[7 * cm, 3 * cm, 3 * cm, 4 * cm]),
                  Spacer(1, 0.4 * cm)]

    # Longest open
    open_cols = ["customer_name", "factory_offering", "ww_region", "eos_status", "aging_days"]
    open_cols = [c for c in open_cols if c in fact.columns]
    longest = analytics.fetch_rows(con, _open_where(where), open_cols, "aging_days", True, 8)
    if not longest.empty:
        longest = longest.rename(columns={"customer_name": "Customer", "factory_offering": "Track",
                                          "ww_region": "Region", "eos_status": "Status",
                                          "aging_days": "Age (d)"})
        story += [Paragraph("Longest-Open Nominations", ss["H2"]),
                  _df_table(longest, ss,
                            col_widths=[5 * cm, 4.5 * cm, 3.5 * cm, 2.5 * cm, 1.5 * cm])]

    doc_buf = io.BytesIO()
    doc = BaseDocTemplate(doc_buf, pagesize=A4, topMargin=1.6 * cm, bottomMargin=1.4 * cm,
                          leftMargin=1.6 * cm, rightMargin=1.6 * cm, title="AVS Migration Analytics")
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="main")
    doc.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=_header_footer)])
    doc.build(story)
    return doc_buf.getvalue()


def _open_where(where: str) -> str:
    return analytics._where_and(where, '"is_open" = TRUE')


def _strip(text: str) -> str:
    """Convert markdown bold (**x**) to ReportLab bold tags."""
    import re
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", str(text))
