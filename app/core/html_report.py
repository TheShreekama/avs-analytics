"""The dashboard as one self-contained, interactive HTML file.

The PDF in :mod:`app.core.exporter` is the printable record; this is the same
report as something you can *use* — the dashboard's charts still interactive,
the drill-downs still accordions, the tables still sortable and searchable — in
a single file small enough to attach to an email.

**Single file** is the whole design constraint.  There is no stylesheet to
fetch, no font to download, no chart library on a CDN: the Plotly bundle, the
CSS and the behaviour script are inlined, so the report opens from a mail
client's download folder on a machine with no network, which is exactly where it
will be read.

Every number comes from the same :mod:`app.core.kpi` calls the screen and the
PDF use, through the shared helpers in :mod:`app.core.exporter` — the three
reports cannot disagree because they are not three calculations.
"""
from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
from plotly.offline import get_plotlyjs

from ..config import FY_START_MONTH, EOS_MATRIX_START_FY
from ..ui import charts
from . import (analytics, exporter, html_style, insights as insights_mod, kpi,
               metrics, segments)
from .metrics import fmt_currency, fmt_int

#: Plotly config for every figure: interactive, but without the "download plot"
#: camera button, which cannot work usefully from an email attachment.
_PLOT_CONFIG = {"displaylogo": False, "responsive": True,
                "modeBarButtonsToRemove": ["lasso2d", "select2d"]}

#: Account rows written per report.  Far larger than the PDF's 300: an HTML
#: table scrolls and searches, so the limit is file size, not readability.
MAX_ACCOUNT_ROWS = 2000


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def esc(value) -> str:
    """One value as safe HTML text; missing becomes an empty cell."""
    if value is None or value is pd.NaT:
        return ""
    if isinstance(value, pd.Timestamp):
        return "" if pd.isna(value) else f"{value:%d %b %Y}"
    if isinstance(value, float) and pd.isna(value):
        return ""
    return html.escape(str(value), quote=True)


def plain(value) -> str:
    """One value as *unescaped* display text — dates formatted, missing blank.

    What :func:`esc` does minus the escaping, for the shared account formatter
    in :mod:`app.core.exporter`: the table renderer escapes every cell itself,
    so escaping here too would turn an "&" in an account name into "&amp;".
    """
    if value is None or value is pd.NaT:
        return ""
    if isinstance(value, pd.Timestamp):
        return "" if pd.isna(value) else f"{value:%d %b %Y}"
    if isinstance(value, float) and pd.isna(value):
        return ""
    return str(value)


def rich(text) -> str:
    """Escaped text with the insight engine's ``**bold**`` markers honoured.

    The insights are written once, in Markdown-ish bold, and rendered by both
    reports; escaping without this leaves literal asterisks on the page.
    """
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", esc(text))


def _slug(*parts: str) -> str:
    return "-".join(str(p) for p in parts if p)


@dataclass
class _Builder:
    """Accumulates the document body, the figure scripts and the contents list."""
    body: list[str]
    scripts: list[str]
    toc: list[tuple[str, str, bool]]      # (anchor, label, is_sub)
    figures: int = 0

    def write(self, markup: str) -> None:
        self.body.append(markup)

    def anchor(self, anchor: str, label: str, sub: bool = False) -> None:
        self.toc.append((anchor, label, sub))

    def figure(self, fig: go.Figure, height: int = 340,
               currency: bool = False) -> str:
        """One interactive chart: a div now, a Plotly.newPlot call at the end.

        Figures are emitted as data rather than as pre-rendered HTML so the
        4.8 MB Plotly bundle is written **once** for the whole document.
        ``currency`` puts money on the axis the way the tiles write it — $2M,
        $840K — rather than as 2,000,000.
        """
        self.figures += 1
        div = f"fig{self.figures}"
        fig.update_layout(template=go.layout.Template(html_style.plotly_template()),
                          height=height, autosize=True)
        fig.update_xaxes(automargin=True)
        fig.update_yaxes(automargin=True)
        # Legend above the plot: a monthly axis rotates its labels, and a
        # bottom legend then sits on top of them.
        fig.update_layout(legend={"orientation": "h", "yanchor": "bottom",
                                  "y": 1.02, "xanchor": "left", "x": 0})
        # A month with the only completion in it should read as one bar, not as
        # a block filling the plot; and a one-point series must not invent an
        # axis of 427…429 around its single value.
        # ``cliponaxis`` so a bar's value label is not cut off by the plot edge.
        fig.update_traces(width=0.62, cliponaxis=False, selector={"type": "bar"})
        fig.update_yaxes(rangemode="tozero")
        if currency:
            # SI suffixes with a $ prefix: "$2M", "$840k". Plotly writes "k"
            # lowercase, so the tick text is post-processed to "K" for the
            # thousands step, matching ``metrics.fmt_currency``.
            fig.update_yaxes(tickprefix="$", tickformat="~s")
            fig.update_traces(hovertemplate="%{x}: $%{y:,.0f}<extra></extra>")
        else:
            _integer_ticks(fig)
        payload = json.loads(pio.to_json(fig))
        self.scripts.append(
            f"Plotly.newPlot({json.dumps(div)}, {json.dumps(payload['data'])}, "
            f"{json.dumps(payload['layout'])}, {json.dumps(_PLOT_CONFIG)});")
        return f'<div class="chart" id="{div}"></div>'


def _integer_ticks(fig: go.Figure) -> None:
    """Whole-number ticks on any axis whose values are whole numbers.

    A count that only reaches 3 otherwise gets ticks every 0.5, which format as
    "3, 3, 2, 2, 1, 1, 0" — the same label twice, which reads as a rendering
    fault.  Each y-axis is judged on its own traces, so a chart pairing a
    3-nomination bar with a 400-account cumulative line does not get one axis's
    step imposed on the other.
    """
    per_axis: dict[str, list[float]] = {}
    for trace in fig.data:
        values = getattr(trace, "y", None)
        if values is None:
            continue
        axis = getattr(trace, "yaxis", None) or "y"
        bucket = per_axis.setdefault(axis, [])
        for value in values:
            # ``float()`` rather than an isinstance check: the values arrive as
            # numpy scalars, which are not Python ints or floats.
            try:
                number = float(value)
            except (TypeError, ValueError):
                continue
            if number == number:                                     # not NaN
                bucket.append(number)
    for axis, values in per_axis.items():
        if not values or any(v != int(v) for v in values):
            continue
        top = max(abs(v) for v in values)
        if top > 12:              # Plotly's own ticks are already whole here
            continue
        name = "yaxis" if axis == "y" else f"yaxis{axis[1:]}"
        if name in fig.layout:
            fig.layout[name].update(dtick=1, tick0=0)


# --------------------------------------------------------------------------- #
# Building blocks
# --------------------------------------------------------------------------- #
def _kpi_tiles(tiles: list[tuple[str, str, str]]) -> str:
    cells = "".join(
        f'<div class="kpi"><div class="label">{esc(label)}</div>'
        f'<div class="value">{esc(value)}</div>'
        f'<div class="unit">{esc(unit)}</div></div>'
        for label, value, unit in tiles)
    return f'<div class="kpis">{cells}</div>'


def _table(frame: pd.DataFrame, table_id: str, *, numeric: set[str] | None = None,
           row_head: bool = False, highlight: str = "") -> str:
    """A DataFrame as a sortable table.  Values are already display strings."""
    if frame.empty:
        return '<p class="empty">Nothing to show.</p>'
    numeric = numeric or set()
    columns = list(frame.columns)

    def classes(column: str, first: bool) -> str:
        bits = []
        if column in numeric:
            bits.append("num")
        if highlight and highlight in str(column):
            bits.append("fytot")
        if first and row_head:
            bits.append("rowhead")
        return f' class="{" ".join(bits)}"' if bits else ""

    head = "".join(f"<th{classes(c, i == 0)}>{esc(c)}</th>"
                   for i, c in enumerate(columns))
    rows = []
    for _, record in frame.iterrows():
        cells = []
        for index, column in enumerate(columns):
            value = esc(record[column])
            css = classes(column, index == 0)
            if not value and index and not css:
                css = ' class="blank"'
            elif not value and index:
                css = css[:-1] + ' blank"'
            cells.append(f"<td{css}>{value}</td>")
        rows.append(f"<tr>{''.join(cells)}</tr>")
    return (f'<div class="table-wrap"><table class="data" id="{table_id}">'
            f"<thead><tr>{head}</tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table></div>")


def _searchable_table(frame: pd.DataFrame, table_id: str, **kw) -> str:
    """A table with a search box above it, for the long account listings."""
    if frame.empty:
        return '<p class="empty">Nothing to show.</p>'
    tools = (f'<div class="tools">'
             f'<input type="search" data-filters="{table_id}" '
             f'placeholder="Filter these {fmt_int(len(frame))} rows…" '
             f'aria-label="Filter table">'
             f'<span class="count" data-count-for="{table_id}">'
             f'{fmt_int(len(frame))} rows</span></div>')
    return tools + _table(frame, table_id, **kw)


def _accordion(title: str, body: str, badge: str = "", open_: bool = False) -> str:
    tag = "<details class=\"acc\"" + (" open" if open_ else "") + ">"
    chip = f'<span class="badge">{esc(badge)}</span>' if badge else ""
    return (f"{tag}<summary>{esc(title)}{chip}</summary>"
            f'<div class="acc-body">{body}</div></details>')


def _records_accordion(title: str, rows: pd.DataFrame, table_id: str,
                       limit: int = 500) -> str:
    """The records behind a chart, formatted as the app's drill-down formats them.

    ``kpi.drilldown_frame`` is the same call the dashboard makes, so the columns,
    the ordering and the money formatting are identical on screen and in the file.
    """
    if rows is None or getattr(rows, "empty", True):
        return _accordion(title, '<p class="empty">No records behind this.</p>',
                          badge="0")
    frame = kpi.drilldown_frame(rows)
    if frame.empty:
        return _accordion(title, '<p class="empty">No records behind this.</p>',
                          badge="0")
    total = len(frame)
    shown = frame.head(limit).map(plain)
    note = ""
    if total > limit:
        note = (f'<p class="note">Showing the first {fmt_int(limit)} of '
                f"{fmt_int(total)} records.</p>")
    return _accordion(title, note + _searchable_table(shown, table_id),
                      badge=f"{fmt_int(total)} records")


def _card(title: str, note: str, body: str) -> str:
    head = f'<h3 class="block">{esc(title)}</h3>' if title else ""
    sub = f'<p class="note">{esc(note)}</p>' if note else ""
    return f'<div class="card">{head}{sub}{body}</div>'


# --------------------------------------------------------------------------- #
# Report sections
# --------------------------------------------------------------------------- #
def _population_line(spec, pop: pd.DataFrame) -> str:
    tpids = segments.tpid_key(pop).nunique() if not pop.empty else 0
    bits = [f"<b>{fmt_int(tpids)}</b> accounts (TPIDs)",
            f"<b>{fmt_int(len(pop))}</b> nomination waves"]
    if spec.key == "eos" and not pop.empty:
        split = (pop.drop_duplicates("tpid_key")["generation"].value_counts()
                 .rename({segments.GEN_UNCLASSIFIED: "no generation tag"}))
        bits += [f"<b>{fmt_int(v)}</b> {esc(k)}" for k, v in split.items()]
    return f'<div class="popline">{" &nbsp;·&nbsp; ".join(bits)}</div>'


def _summary(doc: _Builder, spec, pop, waves, start, end, period_label,
             fy_window=None, fy_label: str = "") -> None:
    """The headline tiles, over a This-FY row when the period is not This FY.

    The same two-row rule the dashboard's Executive Summary uses: selecting
    "This Month" answers how the month went but loses the year it sits in, so
    anything other than This FY gets the fiscal year above it.  Each row is
    measured over its own window — never one derived from the other.
    """
    if fy_window and fy_window[0] is not None:
        doc.write('<p class="note">Two periods: the fiscal year you are in, then '
                  "the period selected for this report. Each row is measured over "
                  "its own window.</p>"
                  f'<h4 class="sub">{esc(fy_label)}</h4>')
        _summary_row(doc, spec, pop, waves, fy_window[0], fy_window[1], fy_label)
        doc.write(f'<h4 class="sub">{esc(period_label)}</h4>')
    _summary_row(doc, spec, pop, waves, start, end, period_label)


def _summary_row(doc: _Builder, spec, pop, waves, start, end,
                 period_label: str) -> None:
    head = exporter.headline(pop, waves, start, end)
    doc.write(_kpi_tiles([
        ("New engagements", fmt_int(head["engagements"].value), period_label),
        ("Migrations completed", fmt_int(head["completed"].value), period_label),
        (spec.unit_label, fmt_int(head["hosts"].value), "Total Cores, completed"),
        ("On-track accounts", fmt_int(head["on_track"].value), "at latest wave — now"),
        ("ACR claimed", fmt_currency(head["acr"].value), period_label),
    ]))


def _trends(doc: _Builder, spec, pop, waves, start, end) -> None:
    """The four monthly measures, each a bar chart with a cumulative line."""
    noms, nom_rows = kpi.monthly_unique_tpids(pop, "approval_date", start, end,
                                              firsts=waves.first)
    acr, acr_rows = kpi.monthly_acr_claimed(pop, start, end)
    hosts, host_rows = kpi.monthly_hosts(pop, start, end)
    done, done_rows = kpi.monthly_migrations_completed(pop, start, end,
                                                       lasts=waves.last)
    series = [("Nominations per month (unique TPIDs)", noms, nom_rows,
               "Nominations", False),
              ("ACR claimed per month", acr, acr_rows, "ACR Claimed", True),
              (f"{spec.unit_label} per month (Total Cores)", hosts, host_rows,
               "Hosts", False),
              ("Migrations completed per month (unique TPIDs)", done, done_rows,
               "Migrations Completed", False)]
    drawn = []
    for title, table, rows, value_col, currency in series:
        if table.empty:
            continue
        fig = charts.trend_chart(table, "period", value_col, "Cumulative",
                                 height=300)
        slug = _slug("t", spec.key, value_col.lower().replace(" ", ""))
        body = doc.figure(fig, height=300, currency=currency)
        body += _accordion(
            f"Monthly numbers — {title}",
            _table(exporter.trend_table(table, value_col, currency), slug + "-m",
                   numeric={value_col, "Cumulative"}),
            badge=f"{fmt_int(len(table))} months")
        # The records behind the line, exactly as the app's drill-down shows
        # them: the accounts, not a second copy of the chart's own numbers.
        body += _records_accordion(f"Underlying accounts — {title}", rows,
                                   slug + "-r")
        drawn.append(f'<div><h4 class="sub">{esc(title)}</h4>{body}</div>')
    if not drawn:
        doc.write(_card("Trends — month over month", "",
                        '<p class="empty">No activity dated inside the reporting '
                        'period.</p>'))
        return
    doc.write(_card(
        "Trends — month over month",
        "Each measure over the reporting period, with its running total. Click a "
        "legend entry to hide a series; drag on the chart to zoom.",
        "".join(drawn)))


def _pipeline(doc: _Builder, spec, pop, waves) -> None:
    states, _ = kpi.by_state(pop, lasts=waves.last)
    stages, _ = kpi.on_track_by_stage(pop, lasts=waves.last)
    if states.empty:
        doc.write(_card("Current pipeline", "",
                        '<p class="empty">No On-Track or Completed accounts to '
                        'report.</p>'))
        return
    left = ('<div><h4 class="sub">Accounts by state</h4>'
            + doc.figure(charts.donut(states, "category", "count"), height=300)
            + "</div>")
    right = ""
    if not stages.empty:
        right = ('<div><h4 class="sub">On-track accounts by stage</h4>'
                 + doc.figure(charts.bar(stages, "category", "count",
                                         horizontal=True), height=300)
                 + "</div>")
    doc.write(_card(
        "Current pipeline",
        "Every account at its latest wave, whatever its nomination date. "
        "On-Track and Completed only — cancelled, blocked and waiting accounts "
        "are deliberately not charted here.",
        f'<div class="grid2">{left}{right}</div>'))


def _regional(doc: _Builder, spec, waves) -> None:
    """Where the category sits by WW Region, with stages named by their code.

    The full status names ("Validating Commitment & Initial Scope") are long
    enough that five of them on an axis leave the plot a sliver, so the axis
    carries the code and the key sits under the charts.  The two charts also get
    a full-width row of their own rather than sharing one — a stacked bar and a
    heatmap side by side in half a column each are unreadable.
    """
    pivot, heat, legend = exporter.region_status(waves.last)
    if pivot.empty:
        return
    body = ('<h4 class="sub">Migration status by WW Region</h4>'
            + doc.figure(charts.stacked_bar(pivot), height=430)
            + '<h4 class="sub">WW Region × status heatmap</h4>'
            + doc.figure(charts.heatmap(heat), height=430))
    if legend:
        body += ('<p class="note"><b>Stage key</b> — ' + " &nbsp;·&nbsp; ".join(
            f"<b>{esc(short)}</b> {esc(name)}" for short, name in legend) + "</p>")
    table = heat.copy()
    table["Total"] = table.sum(axis=1)
    table = table.reset_index().rename(
        columns={table.index.name or "index": "WW Region"})
    body += _accordion(
        "Underlying data — stage × WW Region",
        _table(table.map(lambda v: fmt_int(v) if isinstance(v, (int, float)) else v),
               _slug("rg", spec.key),
               numeric=set(table.columns[1:]), row_head=True),
        badge=f"{fmt_int(len(table))} regions")
    doc.write(_card(
        "Regional breakdown",
        "Accounts at their latest wave, by WW Region and migration status — one "
        "row per TPID, so this agrees with the state chart above rather than "
        "counting waves.", body))


def _offerings(doc: _Builder, spec, pop) -> None:
    """The AVS → Azure Native cut: which offering, which Azure-native service."""
    paths = exporter.labelled(pop, "migration_path")
    targets = exporter.labelled(pop, "azure_target")
    if paths.empty and targets.empty:
        return
    blocks = []
    if not paths.empty:
        blocks.append('<div><h4 class="sub">Nominations by migration path '
                      "(offering)</h4>"
                      + doc.figure(charts.bar(paths.head(12), "category", "count",
                                              horizontal=True), height=330) + "</div>")
    if not targets.empty:
        blocks.append('<div><h4 class="sub">Azure-native targets</h4>'
                      + doc.figure(charts.donut(targets, "category", "count"),
                                   height=330) + "</div>")
    doc.write(_card(
        "By offering & target",
        "Full offering names (the migration path) and the Azure-native service "
        "each lands on. Wave-level counts over every nomination in the report — "
        "not narrowed by the reporting period.",
        f'<div class="grid2">{"".join(blocks)}</div>'))


def _eos_matrix(doc: _Builder, ctx, pop) -> None:
    """The programme's month-by-month grid, exactly as the EOS dashboard shows it."""
    start = metrics.named_fiscal_year_start(EOS_MATRIX_START_FY, FY_START_MONTH)
    blocks = []
    for generation, title in ((segments.GEN_1, "Gen1 to Gen1"),
                              (segments.GEN_2, "Gen1 to Gen2")):
        block = pop[pop["generation"] == generation]
        months = kpi.matrix_month_span(block, start, ctx.as_of)
        grid = kpi.monthly_matrix(block, months, fy_start_month=FY_START_MONTH)
        accounts = segments.tpid_key(block).nunique() if not block.empty else 0
        blocks.append(
            f'<h4 class="sub">{esc(title)}</h4>'
            f'<p class="note"><b>{fmt_int(accounts)}</b> accounts tagged '
            f'<b>AVS Migration - {esc(generation.replace("-", ""))}</b> · '
            f'<b>{fmt_int(len(block))}</b> nomination waves.</p>'
            + _table(grid, _slug("mx", generation.lower().replace("-", "")),
                     numeric=set(grid.columns[1:]), row_head=True,
                     highlight="Total"))
    doc.write(_card(
        "Monthly programme matrix",
        f"From {start:%b %Y} to {ctx.as_of:%b %Y}, every month included, each "
        "fiscal year closing with its own total column. Blocks are the generation "
        "each account is refreshing on to — all EOS accounts are coming from "
        "Gen-1 hardware. Migration start is derived (earliest wave reading On "
        "Track or Done → Actual Start Date, else Planned Start, else Nom. "
        "Approval); engagement end is blank, as the export does not record it.",
        "".join(blocks)))


def _generations(doc: _Builder, doc_fact, spec, start, end) -> None:
    """Gen-1 and Gen-2 read against each other, and against the combined report."""
    rows = []
    for category in spec.breakdown:
        sub = segments.population(doc_fact, category)
        if sub.empty:
            continue
        waves = kpi.wave_index(sub)
        head = exporter.headline(sub, waves, start, end)
        rows.append({
            "Generation": segments.CATEGORY_LABELS[category],
            "Accounts (TPID)": fmt_int(segments.tpid_key(sub).nunique()),
            "Waves": fmt_int(len(sub)),
            "New engagements": fmt_int(head["engagements"].value),
            "Migrations completed": fmt_int(head["completed"].value),
            spec.unit_label: fmt_int(head["hosts"].value),
            "On-track": fmt_int(head["on_track"].value),
            "ACR claimed": fmt_currency(head["acr"].value),
        })
    if not rows:
        return
    frame = pd.DataFrame(rows)
    doc.write(_card(
        "By generation",
        "The two generation dashboards, side by side. Each is a subset of the "
        "report above, selected by the account's own Gen-1/Gen-2 tag.",
        _table(frame, _slug("gen", spec.key),
               numeric=set(frame.columns[1:]), row_head=True)))


def _insights(doc: _Builder, spec, pop) -> None:
    items = insights_mod.generate_insights(pop)[:8]
    if not items:
        return
    entries = "".join(
        f'<li class="{esc(str(item.severity).lower())}">'
        f'<b class="t">{esc(item.title)}</b>{rich(item.detail)}</li>'
        for item in items)
    doc.write(_card(
        "Insights",
        "Generated from this report's population by the same deterministic rules "
        "the Insights page uses.", f'<ul class="insights">{entries}</ul>'))


def _accounts(doc: _Builder, spec, pop, waves, max_rows: int) -> None:
    """The account records, at the grain every unique-TPID metric is counted at."""
    rows, layout, total = exporter.account_rows(pop, waves, spec.key == "eos")
    if rows.empty:
        doc.write(_card("Account records", "",
                        '<p class="empty">No accounts to list.</p>'))
        return
    shown = rows.head(max_rows)
    # ``plain`` not ``esc``: ``_table`` escapes every cell, and escaping twice
    # renders "Ação & Café" as "Ação &amp; Café".
    frame = exporter.format_accounts(shown, layout, escape=plain)
    note = ("One row per account at its latest wave — the grain every unique-TPID "
            "metric in this report is counted at. Sorted by region, largest ACR "
            "first; click any column header to re-sort.")
    if total > max_rows:
        note += (f" Showing the {fmt_int(max_rows)} largest of {fmt_int(total)} "
                 "accounts by ACR — export the full set as CSV from the app.")
    doc.write(_card("Account records", note, _searchable_table(
        frame, _slug("acct", spec.key),
        numeric={"Cores", "ACR", "Waves"})))


def _drilldown(doc: _Builder, spec, pop, waves, max_rows: int) -> None:
    """Everything behind the report, in accordions, closed until asked for.

    Each block is the *accounts* the chart counted — the same records the app's
    drill-down opens — with the summary counts alongside them.
    """
    states, state_rows = kpi.by_state(pop, lasts=waves.last)
    stages, stage_rows = kpi.on_track_by_stage(pop, lasts=waves.last)
    blocks = []
    if not states.empty:
        table = states.rename(columns={"category": "State", "count": "Accounts"})
        table["Accounts"] = table["Accounts"].map(fmt_int)
        blocks.append(_accordion(
            "Counts by state", _table(table, _slug("ds", spec.key),
                                      numeric={"Accounts"}, row_head=True),
            badge=f"{fmt_int(len(table))} states"))
        blocks.append(_records_accordion("Accounts by state", state_rows,
                                         _slug("dsr", spec.key)))
    if not stages.empty:
        table = stages.rename(columns={"category": "Stage", "count": "Accounts"})
        table["Accounts"] = table["Accounts"].map(fmt_int)
        blocks.append(_accordion(
            "Counts by stage", _table(table, _slug("dg", spec.key),
                                      numeric={"Accounts"}, row_head=True),
            badge=f"{fmt_int(len(table))} stages"))
        blocks.append(_records_accordion("On-track accounts by stage", stage_rows,
                                         _slug("dgr", spec.key)))
    if blocks:
        doc.write(_card("Supporting detail",
                        "The accounts behind each chart above, and the counts "
                        "they add up to.", "".join(blocks)))
    _accounts(doc, spec, pop, waves, max_rows)


# --------------------------------------------------------------------------- #
# Assembly
# --------------------------------------------------------------------------- #
def _this_fy(ctx, start, end) -> tuple[tuple | None, str]:
    """The fiscal year the as-of date sits in — unless that *is* the window.

    Mirrors the dashboard's Executive Summary, which puts a This-FY row above
    the selected period whenever they differ, so a month's numbers keep the year
    they sit in.  Returns ``(None, "")`` when the report already covers This FY.
    """
    span = metrics.date_preset_range(ctx.as_of, "This FY", FY_START_MONTH)
    if not span:
        return None, ""
    fy_start, fy_end = pd.Timestamp(span[0]).date(), pd.Timestamp(span[1]).date()
    same = (start is not None and end is not None
            and pd.Timestamp(start).date() == fy_start
            and pd.Timestamp(end).date() == fy_end)
    if same or (start is None and end is None):
        return None, ""
    label = (f"This FY ({metrics.fiscal_year_label(fy_start, FY_START_MONTH)}) — "
             f"{fy_start:%d %b %Y} → {fy_end:%d %b %Y}")
    return (fy_start, fy_end), label


def _report(doc: _Builder, ctx, fact: pd.DataFrame, spec, start, end,
            period_label: str, drilldown: bool, max_rows: int,
            fy_window=None, fy_label: str = "") -> None:
    pop = segments.population(fact, spec.category)
    anchor = f"rpt-{spec.key}"
    doc.anchor(anchor, spec.title)
    doc.write(f'<section class="report" id="{anchor}">'
              f'<div class="report-head"><h2>{esc(spec.title)}</h2>'
              f"<p>{esc(spec.blurb)}</p>"
              f'<div class="source">Source: {esc(spec.source)}</div>'
              f"{_population_line(spec, pop)}</div>")
    if pop.empty:
        doc.write('<div class="card"><p class="empty">No nominations fall into '
                  "this report for the current filters.</p></div></section>")
        return

    waves = kpi.wave_index(pop)
    _summary(doc, spec, pop, waves, start, end, period_label, fy_window, fy_label)
    if spec.key == "eos":
        _eos_matrix(doc, ctx, pop)
    _trends(doc, spec, pop, waves, start, end)
    _pipeline(doc, spec, pop, waves)
    if spec.key == "native":
        _offerings(doc, spec, pop)
    _regional(doc, spec, waves)
    if spec.breakdown:
        _generations(doc, fact, spec, start, end)
    _insights(doc, spec, pop)
    if drilldown:
        _drilldown(doc, spec, pop, waves, max_rows)
    doc.write('<p class="toplink"><a href="#top">↑ Back to contents</a></p>'
              "</section>")


def _inconsistency(doc: _Builder, ctx) -> None:
    """The appendix: everything the file contradicts itself on."""
    issues = segments.eos_consistency(ctx.fact)
    doc.anchor("appendix", "Appendix — Data inconsistency")
    doc.write('<section class="report" id="appendix">'
              '<div class="report-head"><h2>Appendix — Data inconsistency</h2>'
              "<p>Accounts whose generation tag and EOS migration path disagree. "
              "Both are legitimate ways into EOS scope; this makes the "
              "disagreement visible.</p></div>")
    blocks = []
    for name, frame in issues.items():
        label = str(name).replace("_", " ").capitalize()
        if frame is None or frame.empty:
            blocks.append(_accordion(label, '<p class="empty">Nothing flagged.</p>',
                                     badge="0"))
            continue
        # ``plain`` for the same reason as the account table: ``_table`` escapes.
        shown = frame.head(500).map(plain)
        blocks.append(_accordion(
            label, _searchable_table(shown, _slug("apx", name)),
            badge=f"{fmt_int(len(frame))} rows"))
    doc.write(_card("", "", "".join(blocks)))
    doc.write('<p class="toplink"><a href="#top">↑ Back to contents</a></p></section>')


def build_html_report(ctx, where: str = "", scope_label: str = "All data",
                      reports: list[str] | None = None, *,
                      title: str = "AVS Migration Analytics",
                      subtitle: str = "Management Report",
                      period_label: str = "All dates in the dataset",
                      date_window: tuple | None = None,
                      drilldown: bool = True,
                      appendices: list[str] | None = None,
                      max_account_rows: int = MAX_ACCOUNT_ROWS) -> bytes:
    """Render the whole report as one self-contained HTML file.

    Takes the same arguments as :func:`app.core.exporter.build_report` and
    selects the same populations through the same helpers, so the HTML and the
    PDF are two renderings of one report rather than two reports.
    """
    specs = [exporter._BY_KEY[k]
             for k in (reports if reports is not None else exporter.REPORT_KEYS)
             if k in exporter._BY_KEY]
    chosen = [a for a in (appendices or []) if a in dict(exporter.APPENDIX_LIBRARY)]
    start, end = date_window or (None, None)
    fy_window, fy_label = _this_fy(ctx, start, end)
    fact = analytics.select_all(ctx.con, where, table="fact")

    doc = _Builder(body=[], scripts=[], toc=[])
    for spec in specs:
        _report(doc, ctx, fact, spec, start, end, period_label, drilldown,
                max_account_rows, fy_window, fy_label)
    if "inconsistency" in chosen:
        _inconsistency(doc, ctx)
    if not specs and not chosen:
        doc.write('<div class="card"><p class="empty">No reports were '
                  "selected.</p></div>")

    # One pill only: the reporting period. Scope, as-of, dataset, account count
    # and generation time all appear elsewhere in the report or in the file name.
    chips = [f"Period: <b>{esc(period_label)}</b>"]
    return _document(title, subtitle, chips, doc).encode("utf-8")


def _document(title: str, subtitle: str, chips: list[str], doc: _Builder) -> str:
    """Wrap the assembled body in the page shell, inlining everything it needs."""
    toc = "".join(
        '<li><a href="#{}"{}>{}</a></li>'.format(
            anchor, ' class="sub"' if sub else "", esc(label))
        for anchor, label, sub in doc.toc)
    nav = (f'<nav class="toc"><h2>Contents</h2><ol>{toc}</ol>'
           '<div class="toc-tools">'
           '<button class="btn" id="expand-all" type="button">Expand all</button>'
           '<button class="btn" id="collapse-all" type="button">Collapse all</button>'
           '<button class="btn" id="toggle-width" type="button" '
           'aria-pressed="false">Wide</button>'
           "</div></nav>") if doc.toc else ""
    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)} — {esc(subtitle)}</title>
<style>{html_style.stylesheet()}</style>
</head>
<body>
<a id="top"></a>
<header class="cover"><div class="cover-inner">
  <h1>{esc(title)}</h1>
  <p class="sub">{esc(subtitle)}</p>
  <div class="chips">{"".join(f'<span class="chip">{c}</span>' for c in chips)}</div>
</div></header>
<div class="shell">
{nav}
<main>
{"".join(doc.body)}
</main>
</div>
<footer class="report-foot">
  Generated locally by AVS Migration Analytics. Every figure is counted per
  account at its latest wave, exactly as the Status Report pages count it.
  This file is self-contained — charts, styles and data are all inside it.
</footer>
<script>{get_plotlyjs()}</script>
<script>{chr(10).join(doc.scripts)}</script>
<script>{html_style.script()}</script>
</body></html>
"""
