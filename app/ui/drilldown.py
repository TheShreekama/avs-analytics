"""Interactive charts whose data points open the records behind them.

Selecting a month, bar, slice or legend entry shows the rows that produced that
number — the same records the metric counted, never a recomputed lookalike — with
a CSV export.  Metrics in ``core.kpi`` hand back their source rows for exactly
this purpose, so a table can never disagree with the chart above it.
"""
from __future__ import annotations

import re

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ..core import kpi
from ..core.metrics import fmt_currency, fmt_int
from .components import format_money, show_table


_MONTHISH = re.compile(r"^\d{4}[-/]\d{1,2}")


def normalize_bucket(value) -> str:
    """Comparable form of a chart label or table cell.

    Plotly can hand a month back as a full date ("2026-06-01") even when the axis
    was written "2026-06", so anything month-shaped is reduced to YYYY-MM before
    matching. Everything else compares as trimmed text.
    """
    if value is None:
        return ""
    text = str(value).strip()
    if _MONTHISH.match(text):
        ts = pd.to_datetime(text, errors="coerce")
        if not pd.isna(ts):
            return ts.to_period("M").strftime("%Y-%m")
    return text


def selectable_chart(fig: go.Figure, key: str,
                     curve_labels: list[str] | None = None) -> list[str]:
    """Render a chart and return the x-values / labels the user selected.

    ``curve_labels`` names each trace, for a chart whose x-axis alone is
    ambiguous: on an FY-split trend every year has a "Sep", so a click there
    only identifies a month once the line it belongs to is named too.  The
    selection then reads "FY27 Sep", matching the bucket on the records.
    """
    event = st.plotly_chart(fig, width="stretch", key=key, on_select="rerun",
                            selection_mode=("points", "box", "lasso"))
    points = (event or {}).get("selection", {}).get("points", []) or []
    picked: list[str] = []
    labels = _trace_labels(fig)
    for pt in points:
        value = pt.get("label")
        if value is None:
            value = pt.get("x")
        if value is None:
            # A pie slice can come back carrying only its position. Read the
            # category off the figure it was drawn from rather than losing the
            # click.
            value = _label_at(labels, pt)
        value = normalize_bucket(value)
        if value and curve_labels:
            curve = pt.get("curve_number")
            if isinstance(curve, int) and 0 <= curve < len(curve_labels):
                value = f"{curve_labels[curve]} {value}"
        if value and value not in picked:
            picked.append(value)
    return picked


def _trace_labels(fig: go.Figure) -> list[list[str]]:
    """Each trace's category labels, in the order they were plotted."""
    out = []
    for trace in fig.data:
        values = getattr(trace, "labels", None)
        if values is None:
            values = getattr(trace, "x", None)
        out.append([str(v) for v in values] if values is not None else [])
    return out


def _label_at(labels: list[list[str]], point: dict) -> str | None:
    """The category a selected point refers to, by trace and position."""
    curve = point.get("curve_number", 0)
    index = point.get("point_index")
    if index is None:
        index = point.get("point_number")
    if not isinstance(curve, int) or not isinstance(index, int):
        return None
    if 0 <= curve < len(labels) and 0 <= index < len(labels[curve]):
        return labels[curve][index]
    return None


def selectable_table(df: pd.DataFrame, key: str, bucket_col: str) -> list[str]:
    """Render a summary table whose rows can be clicked to drill into them.

    Returns the bucket values of the selected rows, so clicking the June row of a
    monthly table opens exactly the records that made up June's number.
    """
    if df.empty or bucket_col not in df.columns:
        show_table(df)
        return []
    df = format_money(df)
    event = st.dataframe(df, width="stretch", hide_index=True, key=key,
                         on_select="rerun", selection_mode="multi-row")
    rows = []
    try:
        rows = list(event.selection.rows)          # type: ignore[union-attr]
    except AttributeError:
        rows = list((event or {}).get("selection", {}).get("rows", []) or [])
    picked = []
    for i in rows:
        if 0 <= i < len(df):
            value = normalize_bucket(df.iloc[i][bucket_col])
            if value and value not in picked:
                picked.append(value)
    return picked


def drilldown(records: pd.DataFrame, bucket_col: str, selected: list[str], *,
              key: str, what: str = "records", unit_col: str | None = None,
              max_rows: int | None = None) -> None:
    """Show the rows behind the selected chart points (all rows when none picked).

    ``bucket_col`` is the column matching the chart's x-axis / label, so a click
    on "2026-07" or "Executing Migration" filters straight to those records.
    """
    table = records
    if selected and records is not None and bucket_col in getattr(records, "columns", []):
        keys = records[bucket_col].map(normalize_bucket)
        wanted = [normalize_bucket(v) for v in selected]
        table = records[keys.isin(wanted)]
        caption = f"Showing **{', '.join(str(v) for v in selected)}**"
    else:
        caption = "Click a bar, slice or table row above to drill into it"

    frame = kpi.drilldown_frame(table)
    with st.expander(f"🔎 Underlying {what} ({fmt_int(len(frame))} rows)",
                     expanded=bool(selected)):
        st.caption(caption)
        if frame.empty:
            st.info("No records for this selection.")
            return
        if unit_col and unit_col in table.columns:
            total = pd.to_numeric(table[unit_col], errors="coerce").sum()
            label = "ACR" if unit_col in ("total_acr", "acr") else unit_col.replace("_", " ")
            amount = fmt_currency(total) if label == "ACR" else fmt_int(total)
            st.caption(f"Total **{label}** in this selection: **{amount}**")
        shown = frame if max_rows is None or len(frame) <= max_rows else frame.head(max_rows)
        if len(shown) < len(frame):
            st.caption(f"Showing the first {fmt_int(len(shown))} of "
                       f"{fmt_int(len(frame))} rows — the CSV export has them all.")
        show_table(shown, height=min(420, 60 + 35 * min(len(shown), 10)))
        st.download_button("⬇️ Export to CSV", frame.to_csv(index=False).encode("utf-8"),
                           file_name=f"{key}.csv", mime="text/csv", key=f"{key}_csv")


def chart_with_drilldown(fig: go.Figure, records: pd.DataFrame, bucket_col: str, *,
                         key: str, what: str = "records", unit_col: str | None = None,
                         summary: pd.DataFrame | None = None,
                         summary_bucket: str | None = None,
                         summary_width: list | None = None,
                         max_rows: int | None = None,
                         curve_labels: list[str] | None = None) -> None:
    """A chart and its summary table, either of which drills into the same records.

    Clicking a bar selects that month; clicking the matching table row does the
    same thing, so the number in the table and the records below always agree.
    """
    picked: list[str] = []
    if summary is not None and summary_bucket:
        left, right = st.columns(summary_width or [3, 2])
        with left:
            picked += selectable_chart(fig, key=key, curve_labels=curve_labels)
        with right:
            picked += selectable_table(summary, key=f"{key}_table", bucket_col=summary_bucket)
    else:
        picked += selectable_chart(fig, key=key, curve_labels=curve_labels)
    drilldown(records, bucket_col, picked, key=key, what=what, unit_col=unit_col,
              max_rows=max_rows)


def data_expander(frame: pd.DataFrame, key: str, *, label: str = "Underlying data",
                  caption: str | None = None, height: int | None = None) -> None:
    """The numbers behind a chart that has no record-level bucket to click.

    Cross-tabs, heatmaps and rate charts are aggregates of aggregates; what a
    reader needs there is the table the chart was drawn from, exportable.
    """
    if frame is None or frame.empty:
        return
    with st.expander(f"🔎 {label} ({fmt_int(len(frame))} rows)"):
        if caption:
            st.caption(caption)
        show_table(frame, height=height)
        st.download_button("⬇️ Export to CSV", frame.to_csv(index=False).encode("utf-8"),
                           file_name=f"{key}.csv", mime="text/csv", key=f"{key}_csv")


def charts_with_drilldown(figs: list[go.Figure], records: pd.DataFrame, bucket_col: str, *,
                          key: str, what: str = "records", unit_col: str | None = None,
                          max_rows: int | None = None) -> None:
    """A row of charts that all read the same column, sharing one drill-down.

    Two views of one breakdown (a donut of nominations and a bar of accounts by
    the same status) should not each grow their own records table underneath —
    clicking either one filters the single table below both.
    """
    picked: list[str] = []
    for i, (col, fig) in enumerate(zip(st.columns(len(figs)), figs)):
        with col:
            picked += selectable_chart(fig, key=f"{key}_{i}")
    drilldown(records, bucket_col, picked, key=key, what=what, unit_col=unit_col,
              max_rows=max_rows)


def pivot_explorer(records: pd.DataFrame, key: str,
                   default_group: str = "generation") -> None:
    """Optional pivot-style view: regroup the same records without leaving the page.

    Rows are aggregated to unique TPIDs and ACR/hosts subtotals, with the source
    records available underneath, so aggregated values and wave-level rows are
    never confused for one another.
    """
    if records is None or records.empty:
        st.info("No records to explore.")
        return
    options = [c for c in ("generation", "migration_status_label", "current_state",
                           "region_geo", "source_platform", "target_platform",
                           "customer_name", "phase", "avs_sku")
               if c in records.columns]
    if not options:
        return
    index = options.index(default_group) if default_group in options else 0
    group = st.selectbox("Group by", options, index=index, key=f"{key}_group",
                         format_func=lambda c: c.replace("_", " ").title())
    df = records.copy()
    df["_acr"] = pd.to_numeric(df.get("total_acr"), errors="coerce")
    df["_cores"] = pd.to_numeric(df.get("total_cores"), errors="coerce")
    key_col = "tpid_key" if "tpid_key" in df.columns else "tpid"
    summary = (df.groupby(group, dropna=False, as_index=False)
                 .agg(**{"Accounts (unique TPID)": (key_col, "nunique"),
                         "Nominations": (key_col, "size"),
                         "Hosts (Total Cores)": ("_cores", "sum"),
                         "ACR": ("_acr", "sum")})
                 .sort_values("Accounts (unique TPID)", ascending=False))
    total = pd.DataFrame([{
        group: "TOTAL",
        "Accounts (unique TPID)": df[key_col].nunique(),
        "Nominations": len(df),
        "Hosts (Total Cores)": df["_cores"].sum(),
        "ACR": df["_acr"].sum(),
    }])
    show_table(pd.concat([summary, total], ignore_index=True))
    st.caption("Aggregated values — the rows above each subtotal are the unique "
               "TPIDs in that group; expand the drill-down for wave-level records.")
