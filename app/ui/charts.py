"""Plotly chart factory with consistent executive styling.

Every figure shares a clean template (no gridline clutter, corporate palette,
readable fonts) and can be rendered to PNG for the PDF export.
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

from ..config import CATEGORICAL_SEQUENCE, PALETTE, STATUS_COLORS
from ..core.metrics import fmt_compact_currency

_FONT = dict(family="Segoe UI, sans-serif", color=PALETTE["ink"], size=13)


def _base_layout(fig: go.Figure, height: int = 360, title: str | None = None,
                 showlegend: bool = True, int_y: bool = True) -> go.Figure:
    fig.update_layout(
        height=height,
        # An explicit empty string, never None: `title=None` serialises as
        # `"title": {}`, and Plotly.js then draws a title element whose text is
        # undefined — which is exactly what it prints, top-left of every chart.
        title=dict(text=title or "", font=dict(size=15, color=PALETTE["ink"])),
        font=_FONT,
        margin=dict(l=10, r=10, t=40 if title else 16, b=10),
        paper_bgcolor="white",
        plot_bgcolor="white",
        legend=dict(orientation="h", yanchor="bottom", y=-0.22, xanchor="center", x=0.5),
        showlegend=showlegend,
        colorway=CATEGORICAL_SEQUENCE,
    )
    fig.update_xaxes(showgrid=False, zeroline=False, linecolor=PALETTE["border"])
    fig.update_yaxes(showgrid=True, gridcolor="#EEF1F5", zeroline=False)
    if int_y:
        # Counts are whole numbers — never label the value axis with decimals.
        fig.update_yaxes(tickformat=",d")
    return fig


def money_labels(values) -> list[str]:
    """Money values as the short strings a tooltip should show — $12.5K, $1.25M.

    Computed in Python rather than left to a Plotly number format, because
    Plotly's SI notation writes a lowercase "k" and no currency symbol: a hover
    reading "1250000" or "1.25k" is not what the tiles and tables say, and a
    report that writes the same amount two ways is a report someone has to
    reconcile.  Passed to a trace as ``customdata`` and read back by its
    ``hovertemplate``.
    """
    return [fmt_compact_currency(v) for v in pd.Series(list(values)).tolist()]


def _color_for(values) -> list[str]:
    return [STATUS_COLORS.get(str(v), CATEGORICAL_SEQUENCE[i % len(CATEGORICAL_SEQUENCE)])
            for i, v in enumerate(values)]


def donut(df: pd.DataFrame, names: str, values: str, title: str | None = None,
          height: int = 340, currency: bool = False) -> go.Figure:
    """A doughnut.  ``currency`` writes the slice values as money ($1.25M)."""
    fig = go.Figure(go.Pie(
        labels=df[names], values=df[values], hole=0.62,
        marker=dict(colors=_color_for(df[names]), line=dict(color="white", width=2)),
        textinfo="percent", textfont=dict(size=12),
        customdata=money_labels(df[values]) if currency else None,
        hovertemplate=("%{label}: %{customdata} (%{percent})<extra></extra>"
                       if currency else "%{label}: %{value} (%{percent})<extra></extra>"),
    ))
    total = df[values].sum()
    centre = fmt_compact_currency(total) if currency else f"{int(total):,}"
    fig.add_annotation(text=f"<b>{centre}</b><br>total", showarrow=False,
                       font=dict(size=16, color=PALETTE["ink"]))
    return _base_layout(fig, height, title)


def bar(df: pd.DataFrame, x: str, y: str, title: str | None = None, horizontal: bool = False,
        color_status: bool = False, height: int = 360, text: bool = True,
        currency: bool = False) -> go.Figure:
    """A bar chart.  ``currency`` writes the values — bar labels, hover and the
    value axis alike — as money in K/M rather than as raw numbers."""
    colors = _color_for(df[x if horizontal else x]) if color_status else PALETTE["primary"]
    money = money_labels(df[y]) if currency else None
    labels = (money if currency else df[y]) if text else None
    if horizontal:
        fig = go.Figure(go.Bar(
            y=df[x], x=df[y], orientation="h", marker_color=colors,
            text=labels, textposition="outside", customdata=money,
            hovertemplate=("%{y}: %{customdata}<extra></extra>" if currency
                           else "%{y}: %{x}<extra></extra>")))
        fig.update_yaxes(autorange="reversed")
        fig = _base_layout(fig, height, title, showlegend=False, int_y=False)
        # value axis is horizontal here
        fig.update_xaxes(**(dict(tickprefix="$", tickformat="~s") if currency
                            else dict(tickformat=",d")))
        return fig
    fig = go.Figure(go.Bar(
        x=df[x], y=df[y], marker_color=colors,
        text=labels, textposition="outside", customdata=money,
        hovertemplate=("%{x}: %{customdata}<extra></extra>" if currency
                       else "%{x}: %{y}<extra></extra>")))
    fig = _base_layout(fig, height, title, showlegend=False, int_y=not currency)
    if currency:
        fig.update_yaxes(tickprefix="$", tickformat="~s")
    return fig


def stacked_bar(pivot: pd.DataFrame, title: str | None = None, height: int = 380,
                horizontal: bool = False, percent: bool = False) -> go.Figure:
    """Stacked bar from a pivot (index=category rows, columns=series)."""
    fig = go.Figure()
    data = pivot.copy()
    if percent:
        data = data.div(data.sum(axis=1).replace(0, 1), axis=0) * 100
    for col in data.columns:
        color = STATUS_COLORS.get(str(col))
        if horizontal:
            fig.add_bar(y=data.index.astype(str), x=data[col], name=str(col),
                        orientation="h", marker_color=color)
        else:
            fig.add_bar(x=data.index.astype(str), y=data[col], name=str(col),
                        marker_color=color)
    fig.update_layout(barmode="stack")
    if horizontal:
        fig.update_yaxes(autorange="reversed")
    return _base_layout(fig, height, title)


def grouped_bar(df: pd.DataFrame, x: str, series: list[str], title: str | None = None,
                height: int = 360) -> go.Figure:
    fig = go.Figure()
    for i, s in enumerate(series):
        fig.add_bar(x=df[x], y=df[s], name=s.replace("_", " ").title(),
                    marker_color=STATUS_COLORS.get(s.title(), CATEGORICAL_SEQUENCE[i]))
    fig.update_layout(barmode="group")
    return _base_layout(fig, height, title)


def heatmap(pivot: pd.DataFrame, title: str | None = None, height: int = 400,
            colorscale: str = "Blues") -> go.Figure:
    fig = go.Figure(go.Heatmap(
        z=pivot.values, x=[str(c) for c in pivot.columns], y=[str(i) for i in pivot.index],
        colorscale=colorscale, text=pivot.values, texttemplate="%{text}",
        textfont=dict(size=11), hovertemplate="%{y} · %{x}: %{z}<extra></extra>",
        colorbar=dict(thickness=12)))
    fig = _base_layout(fig, height, title, showlegend=False)
    fig.update_yaxes(showgrid=False)
    return fig


def line(df: pd.DataFrame, x: str, y: str, title: str | None = None, height: int = 360,
         area: bool = False, markers: bool = True, color: str | None = None,
         name: str | None = None) -> go.Figure:
    fig = go.Figure()
    add_line(fig, df, x, y, area=area, markers=markers, color=color, name=name or y)
    return _base_layout(fig, height, title, showlegend=name is not None)


def add_line(fig: go.Figure, df: pd.DataFrame, x: str, y: str, area: bool = False,
             markers: bool = True, color: str | None = None, name: str = "",
             currency: bool = False) -> None:
    color = color or PALETTE["primary"]
    fig.add_scatter(
        x=df[x], y=df[y], mode="lines+markers" if markers else "lines", name=name,
        line=dict(color=color, width=2.5), marker=dict(size=6),
        fill="tozeroy" if area else None,
        fillcolor=_rgba(color, 0.12) if area else None,
        customdata=money_labels(df[y]) if currency else None,
        hovertemplate=(f"{name}: %{{customdata}}<extra></extra>" if currency
                       else f"{name}: %{{y}}<extra></extra>"))


def multi_line(df: pd.DataFrame, x: str, series_col: str, y: str, title: str | None = None,
               height: int = 380, area: bool = False) -> go.Figure:
    fig = go.Figure()
    for i, (key, g) in enumerate(df.groupby(series_col)):
        color = STATUS_COLORS.get(str(key), CATEGORICAL_SEQUENCE[i % len(CATEGORICAL_SEQUENCE)])
        add_line(fig, g, x, y, area=area, color=color, name=str(key))
    return _base_layout(fig, height, title)


def fy_lines(df: pd.DataFrame, x: str, series_col: str, y: str, x_order: list[str],
             title: str | None = None, height: int = 360,
             currency: bool = False) -> go.Figure:
    """One line per fiscal year over a shared Jul→Jun month axis.

    Used when the reporting period is "All time": laying the fiscal years on top
    of one another is what makes year-over-year movement readable, where a single
    continuous line just gets longer.  The x-axis is categorical so that a click
    returns the month label exactly as drawn.
    """
    fig = go.Figure()
    for i, key in enumerate(sorted(df[series_col].unique())):
        g = df[df[series_col] == key]
        add_line(fig, g, x, y, color=CATEGORICAL_SEQUENCE[i % len(CATEGORICAL_SEQUENCE)],
                 name=str(key), currency=currency)
    fig = _base_layout(fig, height, title, int_y=not currency)
    fig.update_xaxes(type="category", categoryorder="array", categoryarray=x_order)
    if currency:
        fig.update_yaxes(tickprefix="$", tickformat="~s")
    return fig


def sankey(nodes: list[str], links: list[tuple[int, int, float]],
           title: str | None = None, height: int = 460,
           node_colors: list[str] | None = None) -> go.Figure:
    src, tgt, val = zip(*links) if links else ([], [], [])
    fig = go.Figure(go.Sankey(
        arrangement="snap",
        node=dict(label=nodes, pad=16, thickness=16,
                  color=node_colors or CATEGORICAL_SEQUENCE[0],
                  line=dict(color="white", width=0.5)),
        link=dict(source=list(src), target=list(tgt), value=list(val),
                  color="rgba(15,108,189,0.25)"),
    ))
    fig.update_layout(height=height, font=_FONT, paper_bgcolor="white",
                      margin=dict(l=10, r=10, t=40 if title else 10, b=10),
                      title=dict(text=title or "", font=dict(size=15)))
    return fig


def gauge(value: float, title: str, suffix: str = "%", max_val: float = 100,
          height: int = 240, thresholds=(50, 80)) -> go.Figure:
    color = PALETTE["bad"] if value < thresholds[0] else (
        PALETTE["warn"] if value < thresholds[1] else PALETTE["good"])
    fig = go.Figure(go.Indicator(
        mode="gauge+number", value=value,
        number=dict(suffix=suffix, font=dict(size=28)),
        title=dict(text=title, font=dict(size=14)),
        gauge=dict(axis=dict(range=[0, max_val]), bar=dict(color=color),
                   bgcolor="#F0F2F5", borderwidth=0)))
    fig.update_layout(height=height, font=_FONT, margin=dict(l=20, r=20, t=50, b=10),
                      paper_bgcolor="white")
    return fig


def _rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"

# Note: static image rendering for the PDF lives in app/ui/pdf_charts.py
# (matplotlib).  Plotly figures here are only rendered interactively in the
# browser, so no bundled image-export engine (kaleido/Chromium) is needed.


def trend_chart(df: pd.DataFrame, x: str, value_col: str, cumulative_col: str | None = None,
                currency: bool = False, height: int = 320,
                title: str | None = None) -> go.Figure:
    """Monthly bars plus a cumulative line — the shape every trend section uses.

    Bars (not line points) carry the monthly value because they are far easier to
    click for a drill-down, and the x-axis is forced to ``category`` so Plotly
    hands the period back exactly as written ("2026-06") instead of re-parsing it
    into a date.
    """
    # Money hovers read the tiles' own notation ($1.25M) rather than Plotly's
    # raw number: the same amount must not read two ways in one report.
    value = "%{customdata}" if currency else "%{y:,.0f}"
    fig = go.Figure()
    fig.add_bar(x=df[x], y=df[value_col], name=value_col,
                marker_color=PALETTE["primary"],
                customdata=money_labels(df[value_col]) if currency else None,
                hovertemplate=f"%{{x}}<br>{value_col}: {value}<extra></extra>")
    if cumulative_col and cumulative_col in df.columns:
        fig.add_scatter(x=df[x], y=df[cumulative_col], name=cumulative_col, yaxis="y2",
                        mode="lines+markers", line=dict(color=PALETTE["good"], width=2.5),
                        marker=dict(size=6),
                        customdata=(money_labels(df[cumulative_col]) if currency
                                    else None),
                        hovertemplate=f"%{{x}}<br>{cumulative_col}: {value}<extra></extra>")
    _base_layout(fig, height, title, showlegend=True, int_y=not currency)
    fig.update_xaxes(type="category")
    axis_fmt = dict(tickprefix="$", tickformat="~s") if currency else dict(tickformat=",d")
    fig.update_yaxes(**axis_fmt)
    if cumulative_col and cumulative_col in df.columns:
        fig.update_layout(yaxis2=dict(overlaying="y", side="right", showgrid=False,
                                      **axis_fmt))
    return fig
