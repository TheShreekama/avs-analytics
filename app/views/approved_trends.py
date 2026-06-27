"""Report 6 — AVS Nominations Approved Trend Analysis.

Multi-year approval analysis: YoY, MoM, cumulative and growth rates — all from
actual data (no forecasting).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from app import state
from app.config import SCOPE_PRIMARY
from app.core import analytics
from app.core.metrics import fmt_int, pct_delta
from app.ui import charts, components
from app.ui.theme import page_header, section


def render() -> None:
    ctx = state.ensure_context()
    table = state.active_table()
    analytics.use_table(table)
    page_header("Approved Trend Analysis",
                "Year-over-year and month-over-month approval trends from actual data.")
    components.data_quality_banner(ctx)
    if state.is_customer_mode():
        components.banner_note("Customer mode: each account contributes once at its "
                               "<b>Wave-1</b> approval date.")

    filters, where = components.filter_sidebar(
        ctx, ["region_geo", "migration_path"], date_field=None,
        table=table, scope=SCOPE_PRIMARY)

    con = ctx.con
    window = st.radio("Analysis window", ["Last 1 Year", "Last 2 Years", "Last 3 Years", "All"],
                      index=2, horizontal=True, key="at_win")
    years = {"Last 1 Year": 1, "Last 2 Years": 2, "Last 3 Years": 3, "All": None}[window]

    appr_where = analytics._where_and(where, '"approval_date" IS NOT NULL')
    if years:
        cutoff = (pd.Timestamp(ctx.as_of) - pd.DateOffset(years=years)).date()
        appr_where = analytics._where_and(appr_where, f'"approval_date" >= \'{cutoff}\'')

    monthly = analytics.timeseries(con, appr_where, "approval_date", "month")
    if monthly.empty:
        components.empty_state("No approvals with dates in the selected window.")
        return

    yearly = analytics.timeseries(con, appr_where, "approval_date", "year")
    total = int(monthly["value"].sum())
    yoy = pct_delta(yearly["value"].iloc[-1], yearly["value"].iloc[-2]) if len(yearly) > 1 else None
    mom = pct_delta(monthly["value"].iloc[-1], monthly["value"].iloc[-2]) if len(monthly) > 1 else None
    cagr = _cagr(yearly) if len(yearly) > 1 else None

    components.kpi_row([
        {"label": "Approved (window)", "value": fmt_int(total)},
        {"label": "Latest YoY", "value": (f"{yoy:+.0f}%" if yoy is not None else "—"),
         "tone": "good" if (yoy or 0) >= 0 else "bad"},
        {"label": "Latest MoM", "value": (f"{mom:+.0f}%" if mom is not None else "—"),
         "tone": "good" if (mom or 0) >= 0 else "bad"},
        {"label": "Avg Annual Growth", "value": (f"{cagr:+.0f}%" if cagr is not None else "—")},
    ])
    st.write("")

    section("Monthly approvals & cumulative")
    c1, c2 = st.columns([1.4, 1])
    with c1:
        st.plotly_chart(charts.line(monthly, "period", "value", area=True,
                                    title="Approvals per month"), width="stretch")
    with c2:
        st.plotly_chart(charts.line(monthly, "period", "cumulative", color="#107C41",
                                    title="Cumulative approvals"), width="stretch")

    section("Year-over-year comparison")
    c3, c4 = st.columns(2)
    with c3:
        yr = yearly.copy()
        yr["year"] = yr["period"].dt.year.astype(str)
        yr["growth"] = yr["value"].pct_change() * 100
        st.plotly_chart(charts.bar(yr, "year", "value", title="Approvals per year"),
                        width="stretch")
    with c4:
        # Month-of-year lines per year (overlay) for MoM seasonality
        m = monthly.copy()
        m["year"] = m["period"].dt.year.astype(str)
        m["month"] = m["period"].dt.month
        st.plotly_chart(charts.multi_line(m, "month", "year", "value",
                                          title="Monthly profile by year"),
                        width="stretch")

    section("Year-over-year table")
    yr_tbl = yearly.copy()
    yr_tbl["Year"] = yr_tbl["period"].dt.year
    yr_tbl["Approved"] = yr_tbl["value"]
    yr_tbl["YoY Growth %"] = (yr_tbl["value"].pct_change() * 100).round(1)
    yr_tbl["Cumulative"] = yr_tbl["cumulative"]
    components.show_table(yr_tbl[["Year", "Approved", "YoY Growth %", "Cumulative"]])

    section("Approvals by region over time")
    grain = "year" if years and years > 1 else "month"
    sql = f'''SELECT date_trunc('{grain}', approval_date) AS period, region_geo AS series,
              COUNT(*) AS value FROM {table} {appr_where} GROUP BY 1,2 ORDER BY 1'''
    long = con.execute(sql).fetchdf()
    if not long.empty:
        long["period"] = pd.to_datetime(long["period"])
        st.plotly_chart(charts.multi_line(long, "period", "series", "value"),
                        width="stretch")


def _cagr(yearly: pd.DataFrame):
    """Compound annual growth rate across the yearly series."""
    vals = yearly["value"].to_numpy(dtype=float)
    if len(vals) < 2 or vals[0] <= 0:
        return None
    periods = len(vals) - 1
    return (np.power(vals[-1] / vals[0], 1 / periods) - 1) * 100
