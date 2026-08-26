"""Interactive charts whose data points open the records behind them.

Selecting a month, bar, slice or legend entry shows the rows that produced that
number — the same records the metric counted, never a recomputed lookalike — with
a CSV export.  Metrics in ``core.kpi`` hand back their source rows for exactly
this purpose, so a table can never disagree with the chart above it.
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ..core import kpi
from ..core.metrics import fmt_int
from .components import show_table


def selectable_chart(fig: go.Figure, key: str) -> list[str]:
    """Render a chart and return the x-values / labels the user selected."""
    event = st.plotly_chart(fig, width="stretch", key=key, on_select="rerun",
                            selection_mode=("points", "box", "lasso"))
    points = (event or {}).get("selection", {}).get("points", []) or []
    picked: list[str] = []
    for pt in points:
        value = pt.get("label", pt.get("x"))
        if value is None:
            continue
        value = str(value)
        if value not in picked:
            picked.append(value)
    return picked


def drilldown(records: pd.DataFrame, bucket_col: str, selected: list[str], *,
              key: str, what: str = "records", unit_col: str | None = None) -> None:
    """Show the rows behind the selected chart points (all rows when none picked).

    ``bucket_col`` is the column matching the chart's x-axis / label, so a click
    on "2026-07" or "Executing Migration" filters straight to those records.
    """
    table = records
    if selected and bucket_col in records.columns:
        keys = records[bucket_col].astype(str)
        table = records[keys.isin(selected)]
        caption = f"Showing **{', '.join(selected)}**"
    else:
        caption = "Click a point, bar or slice above to drill into it"

    frame = kpi.drilldown_frame(table)
    with st.expander(f"🔎 Underlying {what} ({fmt_int(len(frame))} rows)",
                     expanded=bool(selected)):
        st.caption(caption)
        if frame.empty:
            st.info("No records for this selection.")
            return
        if unit_col and unit_col in table.columns:
            total = pd.to_numeric(table[unit_col], errors="coerce").sum()
            st.caption(f"Total **{unit_col.replace('_', ' ')}** in this selection: "
                       f"**{fmt_int(total)}**")
        show_table(frame, height=min(420, 60 + 35 * min(len(frame), 10)))
        st.download_button("⬇️ Export to CSV", frame.to_csv(index=False).encode("utf-8"),
                           file_name=f"{key}.csv", mime="text/csv", key=f"{key}_csv")


def chart_with_drilldown(fig: go.Figure, records: pd.DataFrame, bucket_col: str, *,
                         key: str, what: str = "records",
                         unit_col: str | None = None) -> None:
    """A chart plus its drill-down table — the pairing used across the dashboards."""
    selected = selectable_chart(fig, key=key)
    drilldown(records, bucket_col, selected, key=key, what=what, unit_col=unit_col)


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
