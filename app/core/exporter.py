"""Executive PDF export engine (ReportLab + matplotlib static images).

Produces a leadership-ready PDF.  The report is assembled from selectable
*sections* so the Reports page can export a single module or a comprehensive
report.  Fully local — no network, no external services, and no bundled browser
binary (charts are rasterised with matplotlib, not kaleido/Chromium).
"""
from __future__ import annotations

import io
import re
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
from ..ui import pdf_charts as pc
from . import analytics, segments, insights as insights_mod
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

# Section keys exposed on the Reports page.
SECTION_LIBRARY = [
    ("categories", "Migration category dashboards (EOS Gen-1/Gen-2, All AVS, Azure Native)"),
    ("inconsistency", "Data inconsistency review"),
    ("overview", "Portfolio Overview (status, regions, delivery health)"),
    ("approved", "Nominations Approved (trend & regional)"),
    ("closed", "Nominations Closed (closure rate & aging)"),
    ("eos", "EOS Migration Status"),
    ("trends", "Nomination Trends"),
    ("avs_azure", "AVS → Azure Native"),
    ("insights", "Insights"),
    ("tables", "Key operational tables"),
]
SECTION_KEYS = [k for k, _ in SECTION_LIBRARY]


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


def _kpi_table(kpis: dict, ss, unit: str) -> Table:
    rows = [
        [unit.title(), fmt_int(kpis["nominations"]), "Accounts", fmt_int(kpis["accounts"])],
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


def _img(png: bytes, width_cm=17.0):
    """Wrap PNG bytes (from app.ui.pdf_charts) in a ReportLab Image, aspect-preserved."""
    img = Image(io.BytesIO(png))
    ratio = (img.imageHeight / img.imageWidth) if img.imageWidth else 0.36
    img.drawWidth = width_cm * cm
    img.drawHeight = width_cm * cm * ratio
    return img


def _strip(text: str) -> str:
    """Convert markdown bold (**x**) to ReportLab bold tags."""
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", str(text))


# --------------------------------------------------------------------------- #
# Section builders — each returns a list of flowables
# --------------------------------------------------------------------------- #
def _sec_overview(con, where, ss) -> list:
    out = [Paragraph("Portfolio Overview", ss["H1"]),
           Paragraph("Scope: AVS Migration Nominations (onboarding to AVS).", ss["Muted"])]
    status = analytics.count_by(con, where, "migration_status_label")
    if not status.empty:
        out += [Paragraph("By Migration Status", ss["H2"]),
                _img(pc.donut_png(status, "category", "count", height_px=320)), Spacer(1, 0.2 * cm)]
    reg = analytics.count_by(con, where, "region_geo")
    if not reg.empty:
        out += [Paragraph("By Region", ss["H2"]),
                _img(pc.bar_png(reg, "category", "count", horizontal=True, height_px=290))]
    out.append(PageBreak())
    return out


def _sec_approved(con, where, ss) -> list:
    w = analytics._where_and(where, '"is_approved" = TRUE')
    out = [Paragraph("Nominations Approved", ss["H1"])]
    trend = analytics.timeseries(con, w, "approval_date", "month")
    if not trend.empty:
        out += [Paragraph("Monthly Approval Trend", ss["H2"]),
                _img(pc.line_png(trend, "period", "value", area=True, height_px=300))]
    reg = analytics.count_by(con, w, "region_geo")
    if not reg.empty:
        out += [Paragraph("Approvals by Region", ss["H2"]),
                _img(pc.bar_png(reg, "category", "count", horizontal=True, height_px=270))]
    out.append(PageBreak())
    return out


def _sec_closed(con, where, ss) -> list:
    out = [Paragraph("Nominations Closed", ss["H1"])]
    cr = analytics.closure_rate_by(con, where, "region_geo")
    if not cr.empty:
        out += [Paragraph("Closure Rate by Region", ss["H2"]),
                _img(pc.bar_png(cr, "category", "closure_rate", horizontal=True, height_px=270))]
    aging = analytics.aging_buckets(con, where, only_open=True)
    if not aging.empty:
        out += [Paragraph("Age of Open Nominations", ss["H2"]),
                _img(pc.bar_png(aging.astype({"bucket": str}), "bucket", "count", height_px=270))]
    out.append(PageBreak())
    return out


def _sec_eos(con, where, ss) -> list:
    w = analytics._where_and(where, '"is_av36_eos" = TRUE')
    out = [Paragraph("EOS Migration Status", ss["H1"]),
           Paragraph("Scope: nominations with an AV36/EOS migration path.", ss["Muted"])]
    dist = analytics.count_by(con, w, "eos_status")
    if not dist.empty:
        out += [Paragraph("EOS Status Distribution", ss["H2"]),
                _img(pc.bar_png(dist, "category", "count", color_status=True, height_px=290))]
    pivot = analytics.crosstab(con, w, "region_geo", "eos_status")
    if not pivot.empty:
        out += [Paragraph("Region × EOS Status", ss["H2"]),
                _img(pc.heatmap_png(pivot, cmap="RdYlGn_r", height_px=300))]
    out.append(PageBreak())
    return out


def _sec_trends(con, where, ss) -> list:
    out = [Paragraph("Nomination Trends", ss["H1"])]
    ts = analytics.timeseries(con, where, "created_date", "month")
    if not ts.empty:
        out += [Paragraph("Monthly Volume", ss["H2"]),
                _img(pc.line_png(ts, "period", "value", area=True, height_px=290)),
                Paragraph("Cumulative", ss["H2"]),
                _img(pc.line_png(ts, "period", "cumulative", height_px=270, color="#5C2E91"))]
    out.append(PageBreak())
    return out


def _sec_avs_azure(con, where, ss) -> list:
    # ``where`` is already scoped to AVS → Azure Native by build_report.
    out = [Paragraph("AVS → Azure Native", ss["H1"]),
           Paragraph("Scope: offerings migrating away from AVS ('(From AVS)').", ss["Muted"])]
    tgt = analytics.count_by(con, where, "azure_target")
    if not tgt.empty:
        out += [Paragraph("Azure-Native Targets", ss["H2"]),
                _img(pc.donut_png(tgt, "category", "count", height_px=300))]
    stage = analytics.migration_stage_by_track(con, where, track_dim="migration_path")
    if not stage.empty:
        out += [Paragraph("Delivery Stage by Migration Path", ss["H2"]),
                _img(pc.grouped_bar_png(stage, "track", ["started", "in_progress", "completed"],
                                        height_px=290))]
    out.append(PageBreak())
    return out


def _sec_insights(con, where, ss) -> list:
    fact = analytics.select_all(con, where)
    ins = insights_mod.generate_insights(fact)
    out = [Paragraph("Insights", ss["H1"])]
    for it in ins:
        c = _SEV_COLOR.get(it.severity, _PRIMARY)
        out.append(Paragraph(f'<font color="#{c.hexval()[2:]}">&#9632;</font> '
                             f'<b>{it.title}.</b> {_strip(it.detail)}', ss["Body2"]))
        out.append(Spacer(1, 0.12 * cm))
    out.append(PageBreak())
    return out


def _sec_tables(con, where, ss) -> list:
    out = [Paragraph("Operational Detail", ss["H1"])]
    cr = analytics.closure_rate_by(con, where, "region_geo")
    if not cr.empty:
        cr = cr.rename(columns={"category": "Region", "total": "Total", "closed": "Closed",
                                "closure_rate": "Closure %"})
        out += [Paragraph("Closure Rate by Region", ss["H2"]),
                _df_table(cr.head(12), ss, col_widths=[7 * cm, 3 * cm, 3 * cm, 4 * cm]),
                Spacer(1, 0.4 * cm)]
    cols = ["customer_name", "migration_path", "region_geo", "eos_status", "aging_days"]
    longest = analytics.fetch_rows(con, analytics._where_and(where, '"is_open" = TRUE'),
                                   cols, "aging_days", True, 10)
    if not longest.empty:
        longest = longest.rename(columns={"customer_name": "Customer", "migration_path": "Path",
                                          "region_geo": "Region", "eos_status": "Status",
                                          "aging_days": "Age (d)"})
        out += [Paragraph("Longest-Open Nominations", ss["H2"]),
                _df_table(longest, ss,
                          col_widths=[5 * cm, 4.5 * cm, 3.5 * cm, 2.5 * cm, 1.5 * cm])]
    return out


def _sec_categories(ctx, ss, categories, start=None, end=None) -> list:
    """One block per selected migration category: headline metrics + monthly trend."""
    from . import kpi as kpi_mod
    story = [Paragraph("Migration Categories", ss["H1"])]
    for category in categories:
        pop = segments.population(ctx.fact, category)
        label = segments.CATEGORY_LABELS.get(category, category)
        story.append(Paragraph(label, ss["H2"]))
        if pop.empty:
            story.append(Paragraph("No nominations in this category.", ss["Muted"]))
            continue
        waves = kpi_mod.wave_index(pop)
        rows = [
            ["Metric", "Value"],
            ["New engagements (unique TPIDs)",
             fmt_int(kpi_mod.new_engagements(pop, start, end, firsts=waves.first).value)],
            ["Migrations ended (unique TPIDs)",
             fmt_int(kpi_mod.migration_ends(pop, start, end, lasts=waves.last).value)],
            ["Hosts migrated (Total Cores)",
             fmt_int(kpi_mod.hosts_migrated(pop, start, end).value)],
            ["Nominations approved",
             fmt_int(kpi_mod.nominations_approved(pop, start, end).value)],
            ["Total ACR", fmt_currency(kpi_mod.current_acr(pop))],
        ]
        story += [_df_table(pd.DataFrame(rows[1:], columns=rows[0]), ss), Spacer(1, 0.3 * cm)]

        trend, _ = kpi_mod.monthly_unique_tpids(pop, "approval_date", start, end,
                                                firsts=waves.first)
        if not trend.empty:
            table = trend[["period", "Nominations", "Cumulative"]].rename(
                columns={"period": "Month"})
            story += [Paragraph("Nominations per month", ss["Body2"]),
                      _df_table(table, ss), Spacer(1, 0.4 * cm)]
    story.append(PageBreak())
    return story


def _sec_inconsistency(ctx, ss) -> list:
    """Tag vs. EOS-path disagreements, with the offending accounts listed."""
    issues = segments.eos_consistency(ctx.fact)
    story = [Paragraph("Data Inconsistency Review", ss["H1"])]
    labels = {"tagged_without_eos_path": "Tagged Gen-1/Gen-2, no EOS migration path",
              "eos_path_without_tag": "EOS migration path, no generation tag"}
    if not any(len(df) for df in issues.values()):
        story += [Paragraph("No inconsistencies found — generation tags and EOS "
                            "migration paths agree throughout.", ss["Body2"]), PageBreak()]
        return story
    for key, frame in issues.items():
        story.append(Paragraph(f"{labels[key]} — {fmt_int(len(frame))} row(s)", ss["H2"]))
        if frame.empty:
            story.append(Paragraph("None.", ss["Muted"]))
            continue
        cols = [c for c in ("tpid", "customer_name", "phase", "migration_path", "tags")
                if c in frame.columns]
        story += [_df_table(frame[cols].head(25), ss), Spacer(1, 0.4 * cm)]
    story.append(PageBreak())
    return story


_SECTION_FN = {
    "overview": _sec_overview, "approved": _sec_approved, "closed": _sec_closed,
    "eos": _sec_eos, "trends": _sec_trends, "avs_azure": _sec_avs_azure,
    "insights": _sec_insights, "tables": _sec_tables,
}


# --------------------------------------------------------------------------- #
# Public builders
# --------------------------------------------------------------------------- #
def build_report(ctx, where: str = "", scope_label: str = "All data",
                 sections: list[str] | None = None, table: str | None = None,
                 unit_label: str = "Nominations", *, title: str = "AVS Migration Analytics",
                 subtitle: str = "Executive Report", period_label: str = "",
                 categories: list[str] | None = None,
                 date_window: tuple | None = None) -> bytes:
    """Build a PDF containing the selected sections (cover + summary always).

    ``title`` / ``subtitle`` / ``period_label`` appear on the cover, ``categories``
    chooses which migration dashboards the "categories" section renders, and
    ``date_window`` is the (start, end) pair those metrics are measured over.
    """
    if table:
        analytics.use_table(table)
    sections = sections or SECTION_KEYS
    ss = _styles()
    con = ctx.con
    # The cover/summary KPIs reflect the primary AVS-onboarding scope; the
    # AVS → Azure Native section reports the "(From AVS)" offerings separately.
    primary_where = analytics.apply_scope(where, "primary")
    fact = analytics.select_all(con, primary_where)
    kpis = headline_kpis(fact)
    ins = insights_mod.generate_insights(fact)

    story: list = []
    # Cover
    story += [Spacer(1, 5 * cm),
              Paragraph(title, ss["CoverTitle"]),
              Paragraph(subtitle, ss["CoverSub"]),
              Spacer(1, 0.8 * cm),
              Paragraph(f"Scope: {scope_label}", ss["CoverSub"])]
    if period_label:
        story.append(Paragraph(f"Reporting period: {period_label}", ss["CoverSub"]))
    story += [
              Paragraph(f"Dataset: {ctx.filename} &nbsp;·&nbsp; As-of "
                        f"{pd.Timestamp(ctx.as_of):%d %b %Y}", ss["CoverSub"]),
              Paragraph(f"Generated {datetime.now():%d %b %Y, %H:%M}", ss["CoverSub"]),
              PageBreak()]

    # Executive summary (always)
    story.append(Paragraph("Executive Summary", ss["H1"]))
    summary = (
        f"This report covers <b>{fmt_int(kpis['nominations'])}</b> {unit_label.lower()} "
        f"across <b>{fmt_int(kpis['accounts'])}</b> accounts. "
        f"<b>{fmt_int(kpis['approved'])}</b> approved · "
        f"<b>{fmt_int(kpis['closed'])}</b> closed "
        f"(closure rate <b>{kpis['closure_rate']:.0f}%</b>) · "
        f"<b>{fmt_int(kpis['open'])}</b> in flight. "
        f"Total ACR <b>{fmt_currency(kpis['total_acr'])}</b> across "
        f"<b>{fmt_int(kpis['total_cores'])}</b> cores; median open age "
        f"<b>{kpis['median_age_days']:.0f} days</b>.")
    story += [Paragraph(summary, ss["Body2"]), Spacer(1, 0.4 * cm),
              Paragraph("Key Metrics", ss["H2"]), _kpi_table(kpis, ss, unit_label),
              Spacer(1, 0.4 * cm), Paragraph("Top Insights", ss["H2"])]
    for it in ins[:6]:
        c = _SEV_COLOR.get(it.severity, _PRIMARY)
        story.append(Paragraph(f'<font color="#{c.hexval()[2:]}">&#9632;</font> '
                               f'<b>{it.title}.</b> {_strip(it.detail)}', ss["Body2"]))
        story.append(Spacer(1, 0.1 * cm))
    story.append(PageBreak())

    # Selected sections — each scoped to its reporting motion so "(From AVS)"
    # offerings only ever appear in the AVS → Azure Native section.
    start, end = date_window or (None, None)
    for key in sections:
        if key == "categories":
            story += _sec_categories(ctx, ss, categories or list(segments.CATEGORY_LABELS),
                                     start, end)
            continue
        if key == "inconsistency":
            story += _sec_inconsistency(ctx, ss)
            continue
        fn = _SECTION_FN.get(key)
        if fn:
            sec_scope = "from_avs" if key == "avs_azure" else "primary"
            sec_where = analytics.apply_scope(where, sec_scope)
            try:
                story += fn(con, sec_where, ss)
            except Exception:  # a thin slice shouldn't break the whole report
                continue

    # Drop a trailing page break for tidiness
    while story and isinstance(story[-1], PageBreak):
        story.pop()

    buf = io.BytesIO()
    doc = BaseDocTemplate(buf, pagesize=A4, topMargin=1.6 * cm, bottomMargin=1.4 * cm,
                          leftMargin=1.6 * cm, rightMargin=1.6 * cm,
                          title="AVS Migration Analytics")
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="main")
    doc.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=_header_footer)])
    doc.build(story)
    return buf.getvalue()


# Backwards-compatible comprehensive export.
def build_executive_pdf(ctx, where: str = "", scope_label: str = "All data",
                        table: str | None = None, unit_label: str = "Nominations") -> bytes:
    return build_report(ctx, where, scope_label, SECTION_KEYS, table, unit_label)
