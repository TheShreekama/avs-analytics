"""Report 3 — AVS Nominations Closed.

Closure velocity, closure rate by region and aging of what is still open.  Every
chart opens the records behind it: click a month, a region or an age band and
those nominations appear underneath, with a CSV export.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from app import state
from app.config import SCOPE_PRIMARY
from app.core import analytics
from app.core.metrics import fmt_int
from app.ui import charts, components, drilldown
from app.ui.theme import page_header, section


def render() -> None:
    ctx = state.ensure_context()
    table = state.active_table()
    analytics.use_table(table)
    page_header("AVS Nominations Closed",
                "Closure velocity, closure-rate by region, aging and operational insight.")
    components.data_quality_banner(ctx)
    if state.is_customer_mode():
        components.banner_note("Customer mode: an account is <b>closed</b> when its "
                               "<b>last wave</b> is done/completed.")

    date_filter = components.page_date_filter(
        ctx, "cls", "actual_end_date", table=table, scope=SCOPE_PRIMARY)
    filters, where = components.filter_sidebar(
        ctx, ["region_geo", "migration_path", "eos_status"], table=table,
        scope=SCOPE_PRIMARY, date_filter=date_filter)

    con = ctx.con
    closed_where = analytics._where_and(where, '"is_closed" = TRUE')
    open_where = analytics._where_and(where, '"is_open" = TRUE')
    closed_fact = analytics.select_all(con, closed_where)
    open_fact = analytics.select_all(con, open_where)

    section(f"Closed nominations — as of {ctx.as_of:%d %b %Y}")
    components.period_kpi_row(closed_fact["closure_date"], ctx.as_of, verb="Closed")
    st.write("")

    total = analytics.total_rows(con, where)
    closed_n = len(closed_fact)
    rate = round(100 * closed_n / total, 1) if total else 0
    c0a, c0b = st.columns([1, 2])
    with c0a:
        st.plotly_chart(charts.gauge(rate, "Closure rate"), width="stretch")
    with c0b:
        med = analytics.scalar(con, closed_where, "MEDIAN(cycle_time_days)")
        avg = analytics.scalar(con, closed_where, "AVG(cycle_time_days)")
        components.kpi_row([
            {"label": "Closed", "value": fmt_int(closed_n), "tone": "good"},
            {"label": "Still Open", "value": fmt_int(len(open_fact)), "tone": "warn"},
            {"label": "Median Cycle Time", "value": f"{med:.0f} d" if med else "—"},
            {"label": "Avg Cycle Time", "value": f"{avg:.0f} d" if avg else "—"},
        ])
    drilldown.data_expander(
        pd.DataFrame([{"Measure": "Nominations in selection", "Value": total},
                      {"Measure": "Closed", "Value": closed_n},
                      {"Measure": "Still open", "Value": len(open_fact)},
                      {"Measure": "Closure rate (%)", "Value": rate}]),
        "cls_rate", label="Underlying data — closure rate",
        caption="Closure rate is closed ÷ every nomination in the current selection.")

    section("Closure trend")
    st.caption("Click a point or a table row to open the nominations closed that month.")
    ts = analytics.timeseries(con, closed_where, "closure_date", "month")
    if ts.empty:
        components.empty_state("No closure dates available in the current selection.")
    else:
        ts = ts.assign(bucket=pd.to_datetime(ts["period"]).dt.strftime("%Y-%m"))
        rows = closed_fact.assign(
            bucket=pd.to_datetime(closed_fact["closure_date"], errors="coerce")
                     .dt.to_period("M").astype(str))
        fig = charts.line(ts, "bucket", "value", area=True, title="Closures per month",
                          color="#107C41")
        fig.update_xaxes(type="category")
        drilldown.chart_with_drilldown(
            fig, rows, "bucket", key="cls_trend", what="closed nominations",
            max_rows=500,
            summary=ts[["bucket", "value", "cumulative"]].rename(
                columns={"bucket": "Month", "value": "Closed", "cumulative": "Cumulative"}),
            summary_bucket="Month")

    section("Closure rate by region")
    st.caption("Click a bar to open every nomination — closed or not — in that region.")
    cr = analytics.closure_rate_by(con, where, "region_geo")
    if not cr.empty:
        picked = drilldown.selectable_chart(
            charts.bar(cr, "category", "closure_rate", horizontal=True,
                       title="Closure rate by region (%)"), key="cls_region")
        drilldown.data_expander(
            cr.rename(columns={"category": "Region", "total": "Nominations",
                               "closed": "Closed", "closure_rate": "Closure rate (%)"}),
            "cls_region_table", label="Underlying data — closure rate by region")
        drilldown.drilldown(analytics.select_all(con, where), "region_geo", picked,
                            key="cls_region_rows", what="nominations", max_rows=500)

    section("Aging of open nominations")
    st.caption("Click an age band to open the nominations sitting in it.")
    aging = analytics.aging_buckets(con, where, only_open=True)
    if aging.empty or not len(open_fact):
        components.empty_state("Nothing is still open in the current selection.")
    else:
        rows = open_fact.assign(bucket=analytics.aging_bucket(open_fact["aging_days"]))
        fig = charts.bar(aging.astype({"bucket": str}), "bucket", "count",
                         title="Age of open nominations", color_status=False)
        fig.update_xaxes(type="category")
        drilldown.chart_with_drilldown(
            fig, rows, "bucket", key="cls_aging", what="open nominations", max_rows=500,
            summary=aging.astype({"bucket": str}).rename(
                columns={"bucket": "Age band", "count": "Open nominations"}),
            summary_bucket="Age band")

    section("Operational lists")
    c3, c4 = st.columns(2)
    with c3:
        st.markdown("**⏳ Longest-open nominations**")
        cols = [c for c in ("customer_name", "migration_path", "region_geo",
                            "eos_status", "aging_days") if c in open_fact.columns]
        longest = open_fact[cols].sort_values("aging_days", ascending=False)
        components.show_table(longest.head(15), height=380)
        st.download_button("⬇️ Export open nominations",
                           longest.to_csv(index=False).encode("utf-8"),
                           file_name="open-nominations.csv", mime="text/csv",
                           key="cls_open_csv")
    with c4:
        st.markdown("**✅ Closed in the selected range**")
        cols2 = [c for c in ("customer_name", "migration_path", "region_geo",
                             "cycle_time_days", "closure_date") if c in closed_fact.columns]
        done = closed_fact[cols2].sort_values("closure_date", ascending=False)
        components.show_table(done.head(50), height=380)
        st.download_button("⬇️ Export closed nominations",
                           done.to_csv(index=False).encode("utf-8"),
                           file_name="closed-nominations.csv", mime="text/csv",
                           key="cls_closed_csv")
