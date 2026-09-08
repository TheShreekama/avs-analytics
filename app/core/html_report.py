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


@dataclass(frozen=True)
class _Tile:
    """One headline metric: what it reads, and the accounts it opens."""
    label: str
    value: str
    unit: str
    pane: str = ""
    badge: str = ""


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
               currency: bool = False, drill: str = "",
               mode: str = "x") -> str:
        """One interactive chart: a div now, a Plotly.newPlot call at the end.

        Figures are emitted as data rather than as pre-rendered HTML so the
        4.8 MB Plotly bundle is written **once** for the whole document.
        ``currency`` puts money on the axis the way the tiles write it — $2M,
        $840K — rather than as 2,000,000.  ``drill`` names the accounts table a
        click on this chart filters, and ``mode`` says how to read the bucket
        off the clicked point (see ``bucketOf`` in :mod:`app.core.html_style`).
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
        attrs = (f' data-drill="{drill}" data-drill-mode="{mode}"' if drill else "")
        return f'<div class="chart" id="{div}"{attrs}></div>'


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
def _kpi_tiles(tiles: list["_Tile"], group: str = "") -> str:
    """The headline row.  With a ``group`` the tiles select the accounts below.

    Each metric counts a different thing at a different grain — new engagements
    are Wave-1 rows per TPID, hosts are completed *wave* records — so the tiles
    switch between five tables rather than filtering one: a single merged table
    would have to pretend they share a grain.
    """
    cells = []
    for index, tile in enumerate(tiles):
        attrs = ""
        if group:
            attrs = (f' data-tile="{tile.pane}" data-tile-group="{group}"'
                     f' data-tile-label="{esc(tile.label)}"'
                     f' data-tile-count="{esc(tile.badge)}"'
                     f' role="button" tabindex="0"'
                     f' aria-pressed="{"true" if index == 0 else "false"}"')
        cells.append(f'<div class="kpi"{attrs}><div class="label">{esc(tile.label)}'
                     f'</div><div class="value">{esc(tile.value)}</div>'
                     f'<div class="unit">{esc(tile.unit)}</div></div>')
    return f'<div class="kpis">{"".join(cells)}</div>'


def _table(frame: pd.DataFrame, table_id: str, *, numeric: set[str] | None = None,
           row_head: bool = False, highlight: str = "",
           buckets: pd.Series | None = None) -> str:
    """A DataFrame as a sortable table.  Values are already display strings.

    ``buckets`` tags each row with the chart point it belongs to, so a click on
    the chart above can show just those rows.  It is computed in Python and
    written into the markup, so the browser only ever compares strings.
    """
    if frame.empty:
        return '<p class="empty">Nothing to show.</p>'
    numeric = numeric or set()
    columns = list(frame.columns)
    tags = ([f' data-bucket="{esc(b)}"' for b in buckets] if buckets is not None
            else [""] * len(frame))

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
    for position, (_, record) in enumerate(frame.iterrows()):
        cells = []
        for index, column in enumerate(columns):
            value = esc(record[column])
            css = classes(column, index == 0)
            if not value and index and not css:
                css = ' class="blank"'
            elif not value and index:
                css = css[:-1] + ' blank"'
            cells.append(f"<td{css}>{value}</td>")
        rows.append(f"<tr{tags[position]}>{''.join(cells)}</tr>")
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


def _accordion(title: str, body: str, badge: str = "", open_: bool = False,
               anchor: str = "") -> str:
    """One collapsible block.  ``anchor`` lets a chart click open it."""
    tag = ('<details class="acc"' + (f' id="{anchor}"' if anchor else "")
           + (" open" if open_ else "") + ">")
    chip = f'<span class="badge">{esc(badge)}</span>' if badge else ""
    return (f"{tag}<summary>{esc(title)}{chip}</summary>"
            f'<div class="acc-body">{body}</div></details>')


def _accounts_panel(title: str, rows: pd.DataFrame, table_id: str, *,
                    buckets=None, limit: int = 800, open_: bool = False) -> str:
    """The accounts behind a chart, in an accordion the chart can filter.

    ``buckets`` is a callable taking the (truncated) record frame and returning
    one bucket per row, matching what a click on the chart reports.  The rows
    are written once and filtered in the browser, so a click costs nothing.
    """
    if rows is None or getattr(rows, "empty", True):
        return _accordion(title, '<p class="empty">No accounts behind this.</p>',
                          badge="0")
    frame = kpi.drilldown_frame(rows)
    if frame.empty:
        return _accordion(title, '<p class="empty">No accounts behind this.</p>',
                          badge="0")
    total = len(frame)
    keep = frame.head(limit)
    tags = None
    if buckets is not None:
        tags = pd.Series(list(buckets(rows))[:len(keep)], index=keep.index)
    shown = keep.map(plain)

    note = ""
    if total > limit:
        note = (f'<p class="note">Showing the first {fmt_int(limit)} of '
                f"{fmt_int(total)} accounts.</p>")
    tools = (f'<div class="tools">'
             f'<input type="search" data-filters="{table_id}" '
             f'placeholder="Search these {fmt_int(len(shown))} rows…" '
             f'aria-label="Search accounts">'
             f'<span class="count" data-count-for="{table_id}">'
             f'{fmt_int(len(shown))} rows</span>'
             + (f'<button class="btn" data-drill-clear="{table_id}" hidden '
                f'type="button">Clear selection</button>' if tags is not None else "")
             + (f'<span class="drill-note" data-drill-note="{table_id}">Click a '
                "point on the chart above to filter these rows.</span>"
                if tags is not None else "")
             + "</div>")
    body = note + tools + _table(shown, table_id, buckets=tags)
    return _accordion(title, body, badge=f"{fmt_int(total)} accounts",
                      open_=open_, anchor=f"acc-{table_id}")


def _accounts_body(rows: pd.DataFrame, table_id: str, limit: int = 800
                   ) -> tuple[str, int]:
    """The searchable accounts table on its own, plus how many rows it stands for."""
    if rows is None or getattr(rows, "empty", True):
        return '<p class="empty">No accounts behind this.</p>', 0
    frame = kpi.drilldown_frame(rows)
    if frame.empty:
        return '<p class="empty">No accounts behind this.</p>', 0
    total = len(frame)
    shown = frame.head(limit).map(plain)
    note = (f'<p class="note">Showing the first {fmt_int(limit)} of '
            f"{fmt_int(total)} accounts.</p>" if total > limit else "")
    tools = (f'<div class="tools">'
             f'<input type="search" data-filters="{table_id}" '
             f'placeholder="Search these {fmt_int(len(shown))} rows…" '
             f'aria-label="Search accounts">'
             f'<span class="count" data-count-for="{table_id}">'
             f'{fmt_int(len(shown))} rows</span></div>')
    return note + tools + _table(shown, table_id), total


def _tile_accounts(group: str, panes: list[tuple[str, str, pd.DataFrame]]) -> str:
    """One accordion holding every tile's accounts, the tiles choosing which shows.

    Five accordions for five tiles was five clicks to compare two numbers; this
    is one panel that follows whichever tile is selected.
    """
    blocks, first_label, first_badge = [], "", "0"
    for index, (label, table_id, rows) in enumerate(panes):
        body, total = _accounts_body(rows, table_id)
        badge = f"{fmt_int(total)} accounts" if total else "0"
        if index == 0:
            first_label, first_badge = label, badge
        blocks.append(
            f'<div class="tile-pane" data-pane="{table_id}" '
            f'data-pane-group="{group}"{"" if index == 0 else " hidden"}>'
            f"{body}</div>")
    # One flex child, or the summary's gap opens a hole mid-sentence.
    summary = (f'<span>Accounts behind <b data-tile-title="{group}">'
               f"{esc(first_label)}</b></span>")
    return (f'<details class="acc tiles" id="acc-{group}"><summary>{summary}'
            f'<span class="badge" data-tile-badge="{group}">{first_badge}</span>'
            f'</summary><div class="acc-body">'
            '<p class="note">Pick a tile above to switch this to that metric\'s '
            "accounts — each one is counted at its own grain, so they are "
            "separate lists rather than one merged table.</p>"
            f'{"".join(blocks)}</div></details>')


def _drillable(doc: _Builder, *, heading: str, fig, rows: pd.DataFrame,
               buckets, table_id: str, mode: str = "x", height: int = 300,
               currency: bool = False, label: str = "") -> str:
    """A chart wired to the accounts beneath it — the report's unit of drill-down."""
    return (f'<h4 class="sub">{esc(heading)}</h4>'
            + doc.figure(fig, height=height, currency=currency,
                         drill=table_id, mode=mode)
            + _accounts_panel(label or f"Underlying accounts — {heading}",
                              rows, table_id, buckets=buckets))


def _card(title: str, note: str, body: str) -> str:
    head = f'<h3 class="block">{esc(title)}</h3>' if title else ""
    sub = f'<p class="note">{esc(note)}</p>' if note else ""
    return f'<div class="card">{head}{sub}{body}</div>'


# --------------------------------------------------------------------------- #
# Report sections
# --------------------------------------------------------------------------- #
def _unit_noun(spec) -> str:
    """What this report calls the Total Cores column.

    The AVS motions deploy **nodes**; only the "(From AVS)" motion moves cores
    to Azure-native services.  One noun per report, used by the tiles and the
    trend titles alike so the two never disagree.
    """
    return "Cores" if spec.key == "native" else "Nodes"


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
        _summary_row(doc, spec, pop, waves, fy_window[0], fy_window[1], fy_label,
                     slug="fy")
        doc.write(f'<h4 class="sub">{esc(period_label)}</h4>')
    _summary_row(doc, spec, pop, waves, start, end, period_label)


def _summary_row(doc: _Builder, spec, pop, waves, start, end,
                 period_label: str, slug: str = "") -> None:
    """One period's tiles, each with the accounts behind it.

    The same five metrics the dashboard's Executive Summary shows, and the same
    records under each — ``Metric.records`` is what the number was counted from,
    so the table can never disagree with the tile above it.
    """
    head = exporter.headline(pop, waves, start, end)
    noun = _unit_noun(spec)
    group = _slug("kpis", spec.key, slug)
    metrics_shown = [
        ("New engagements", "engagements", fmt_int(head["engagements"].value),
         period_label),
        ("Migrations completed", "completed", fmt_int(head["completed"].value),
         period_label),
        (spec.unit_label, "hosts", fmt_int(head["hosts"].value),
         f"Total {noun} deployed"),
        ("On-track accounts", "on_track", fmt_int(head["on_track"].value),
         "at latest wave — now"),
        ("ACR claimed", "acr", fmt_currency(head["acr"].value), period_label),
    ]
    panes, tiles = [], []
    for label, key, value, unit in metrics_shown:
        table_id = _slug("kpi", spec.key, slug, key)
        records = head[key].records
        count = len(kpi.drilldown_frame(records)) if not getattr(
            records, "empty", True) else 0
        panes.append((label, table_id, records))
        tiles.append(_Tile(label, value, unit, pane=table_id,
                           badge=f"{fmt_int(count)} accounts" if count else "0"))
    doc.write(_kpi_tiles(tiles, group=group))
    doc.write(_tile_accounts(group, panes))


def _by_month(rows: pd.DataFrame) -> list[str]:
    """Each record's month, written exactly as the chart's x-axis writes it."""
    return [str(m) for m in rows["month"]]


def _trends(doc: _Builder, spec, pop, waves, start, end) -> None:
    """The four monthly measures, each a bar chart with a cumulative line."""
    noms, nom_rows = kpi.monthly_unique_tpids(pop, "approval_date", start, end,
                                              firsts=waves.first)
    acr, acr_rows = kpi.monthly_acr_claimed(pop, start, end)
    hosts, host_rows = kpi.monthly_hosts(pop, start, end)
    done, done_rows = kpi.monthly_migrations_completed(pop, start, end,
                                                       lasts=waves.last)
    noun = _unit_noun(spec)
    series = [("Nominations per month (unique TPIDs)", noms, nom_rows,
               "Nominations", False),
              ("ACR claimed per month", acr, acr_rows, "ACR Claimed", True),
              (f"{spec.unit_label} per month (Total {noun})", hosts, host_rows,
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
        body = _drillable(doc, heading=title, fig=fig, rows=rows,
                          buckets=_by_month, table_id=slug + "-r",
                          height=300, currency=currency)
        body += _accordion(
            f"Monthly numbers — {title}",
            _table(exporter.trend_table(table, value_col, currency), slug + "-m",
                   numeric={value_col, "Cumulative"}),
            badge=f"{fmt_int(len(table))} months")
        drawn.append(f"<div>{body}</div>")
    if not drawn:
        doc.write(_card("Trends — month over month", "",
                        '<p class="empty">No activity dated inside the reporting '
                        'period.</p>'))
        return
    doc.write(_card(
        "Trends — month over month",
        "Each measure over the reporting period, with its running total. Click a "
        "bar or point to narrow the accounts beneath it to that month; click it "
        "again to clear. A legend entry hides a series; dragging zooms.",
        "".join(drawn)))


def _pipeline(doc: _Builder, spec, pop, waves) -> None:
    states, state_rows = kpi.by_state(pop, lasts=waves.last)
    stages, stage_rows = kpi.on_track_by_stage(pop, lasts=waves.last)
    if states.empty:
        doc.write(_card("Current pipeline", "",
                        '<p class="empty">No On-Track or Completed accounts to '
                        'report.</p>'))
        return
    # A pie reports the clicked slice by its label; a horizontal bar by its y.
    body = _drillable(doc, heading="Accounts by state",
                      fig=charts.donut(states, "category", "count"),
                      rows=state_rows, buckets=lambda r: list(r["state"]),
                      table_id=_slug("ps", spec.key), mode="label", height=320)
    if not stages.empty:
        body += _drillable(
            doc, heading="On-track accounts by stage",
            fig=charts.bar(stages, "category", "count", horizontal=True),
            rows=stage_rows, buckets=lambda r: list(r["stage"]),
            table_id=_slug("pg", spec.key), mode="y", height=320)
    doc.write(_card(
        "Current pipeline",
        "Every account at its latest wave, whatever its nomination date. "
        "On-Track and Completed only — cancelled, blocked and waiting accounts "
        "are deliberately not charted here. Click a slice or bar to narrow the "
        "accounts beneath it.", body))


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
    rows = _region_stage_rows(waves.last)
    # Both charts read the same pair, so both filter the same accounts: on the
    # stacked bar the region is the trace and the stage the x; on the heatmap
    # the region is the y and the stage the x.
    body = _drillable(doc, heading="Migration status by WW Region",
                      fig=charts.stacked_bar(pivot), rows=rows,
                      buckets=_by_region_stage, table_id=_slug("rb", spec.key),
                      mode="trace-x", height=430)
    body += _drillable(doc, heading="WW Region × status heatmap",
                       fig=charts.heatmap(heat), rows=rows,
                       buckets=_by_region_stage, table_id=_slug("rh", spec.key),
                       mode="y-x", height=430)
    if legend:
        body += ('<p class="note"><b>Stage key</b> — ' + " &nbsp;·&nbsp; ".join(
            f"<b>{esc(short)}</b> {esc(name)}" for short, name in legend) + "</p>")
    table = heat.copy()
    table["Total"] = table.sum(axis=1)
    table = table.reset_index().rename(
        columns={table.index.name or "index": "WW Region"})
    body += _accordion(
        "The counts — stage × WW Region",
        _table(table.map(lambda v: fmt_int(v) if isinstance(v, (int, float)) else v),
               _slug("rg", spec.key),
               numeric=set(table.columns[1:]), row_head=True),
        badge=f"{fmt_int(len(table))} regions")
    doc.write(_card(
        "Regional breakdown",
        "Accounts at their latest wave, by WW Region and migration status — one "
        "row per TPID, so this agrees with the state chart above rather than "
        "counting waves. Click a bar segment or a heatmap cell to narrow the "
        "accounts to that region and stage.", body))


#: Joins the two halves of a regional selection ("Americas - Enterprise · Stage 4").
#: The same separator the report's script writes, so the markup and the click
#: agree without either having to parse the other.
_REGION_STAGE_JOIN = " \u00b7 "


def _region_stage_rows(lasts: pd.DataFrame) -> pd.DataFrame:
    """The accounts both regional charts are drawn from, at latest-wave grain."""
    if lasts.empty or "region_geo" not in lasts.columns:
        return lasts
    rows = lasts[kpi.reported_stages(lasts)]
    if rows.empty:
        return rows
    stages, _legend = kpi.stage_labels(rows)
    return rows.assign(_stage=stages, _region=exporter.clean(rows["region_geo"]))


def _by_region_stage(rows: pd.DataFrame) -> list[str]:
    return [f"{r}{_REGION_STAGE_JOIN}{s}"
            for r, s in zip(rows["_region"], rows["_stage"])]


def _offerings(doc: _Builder, spec, pop) -> None:
    """The AVS → Azure Native cut: which offering, which Azure-native service."""
    paths = exporter.labelled(pop, "migration_path")
    targets = exporter.labelled(pop, "azure_target")
    if paths.empty and targets.empty:
        return
    body = ""
    if not paths.empty:
        body += _drillable(
            doc, heading="Nominations by migration path (offering)",
            fig=charts.bar(paths.head(12), "category", "count", horizontal=True),
            rows=pop, buckets=lambda r: list(exporter.clean(r["migration_path"])),
            table_id=_slug("op", spec.key), mode="y", height=340)
    if not targets.empty:
        body += _drillable(
            doc, heading="Azure-native targets",
            fig=charts.donut(targets, "category", "count"),
            rows=pop, buckets=lambda r: list(exporter.clean(r["azure_target"])),
            table_id=_slug("ot", spec.key), mode="label", height=340)
    doc.write(_card(
        "By offering & target",
        "Full offering names (the migration path) and the Azure-native service "
        "each lands on. Wave-level counts over every nomination in the report — "
        "not narrowed by the reporting period. Click a bar or slice to narrow "
        "the records beneath it.", body))


def _eos_matrix(doc: _Builder, ctx, pop) -> None:
    """The programme's month-by-month grid, exactly as the EOS dashboard shows it.

    ``pop`` is deliberately the population the reporting period never narrowed:
    like the dashboard's grid, this one runs from a fixed July start to the
    as-of date whatever period the rest of the report covers, because a month
    with no nominations is itself the number being reported.
    """
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
        "fiscal year closing with its own total column — the whole programme, "
        "not narrowed by the reporting period the rest of this report uses. "
        "Blocks are the generation each account is refreshing on to — all EOS "
        "accounts are coming from Gen-1 hardware. Migration start is derived "
        "(earliest wave reading On Track or Done → Actual Start Date, else "
        "Planned Start, else Nom. Approval); engagement end repeats migration "
        "end, the closest the export comes to it.",
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


def _report(doc: _Builder, ctx, fact: pd.DataFrame, all_time: pd.DataFrame, spec,
            start, end, period_label: str,
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
        # The matrix is the programme's own grid, so it is drawn from rows the
        # reporting period never touched — see :func:`_eos_matrix`.
        _eos_matrix(doc, ctx, segments.population(all_time, spec.category))
    _trends(doc, spec, pop, waves, start, end)
    _pipeline(doc, spec, pop, waves)
    if spec.key == "native":
        _offerings(doc, spec, pop)
    _regional(doc, spec, waves)
    if spec.breakdown:
        _generations(doc, fact, spec, start, end)
    _insights(doc, spec, pop)
    # No account list closes the report: every chart above already opens the
    # accounts it was drawn from, so a final table of all of them was the same
    # rows once more — and the bulk of the file.
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
                      all_time_where: str | None = None,
                      appendices: list[str] | None = None) -> bytes:
    """Render the whole report as one self-contained HTML file.

    Takes the same arguments as :func:`app.core.exporter.build_report` and
    selects the same populations through the same helpers, so the HTML and the
    PDF are two renderings of one report rather than two reports.

    ``all_time_where`` is the same filter clause with the reporting-period
    condition dropped.  Only the programme matrix reads it — that grid spans the
    whole programme by definition, so a period narrows every other number in the
    report but never it.  Defaults to ``where``, which is right when the caller
    has no period filter to drop.
    """
    specs = [exporter._BY_KEY[k]
             for k in (reports if reports is not None else exporter.REPORT_KEYS)
             if k in exporter._BY_KEY]
    chosen = [a for a in (appendices or []) if a in dict(exporter.APPENDIX_LIBRARY)]
    start, end = date_window or (None, None)
    fy_window, fy_label = _this_fy(ctx, start, end)
    fact = analytics.select_all(ctx.con, where, table="fact")
    all_time = (fact if all_time_where is None or all_time_where == where
                else analytics.select_all(ctx.con, all_time_where, table="fact"))

    doc = _Builder(body=[], scripts=[], toc=[])
    for spec in specs:
        _report(doc, ctx, fact, all_time, spec, start, end, period_label,
                fy_window, fy_label)
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
