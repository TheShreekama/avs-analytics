"""Report 3 — AVS Nominations Closed."""
from __future__ import annotations

import streamlit as st

from app import state
from app.config import SCOPE_PRIMARY
from app.core import analytics
from app.core.metrics import fmt_int
from app.ui import charts, components
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
        ctx, ["region_geo", "migration_path", "eos_status"], table=table, scope=SCOPE_PRIMARY, date_filter=date_filter)

    con = ctx.con
    closed_where = analytics._where_and(where, '"is_closed" = TRUE')
    closed_fact = analytics.select_all(con, closed_where)

    section(f"Closed nominations — as of {ctx.as_of:%d %b %Y}")
    components.period_kpi_row(closed_fact["closure_date"], ctx.as_of, verb="Closed")
    st.write("")

    # rate gauge + summary
    total = analytics.total_rows(con, where)
    closed_n = len(closed_fact)
    rate = round(100 * closed_n / total, 1) if total else 0
    c0a, c0b = st.columns([1, 2])
    with c0a:
        st.plotly_chart(charts.gauge(rate, "Closure rate"), width="stretch")
    with c0b:
        med = analytics.scalar(con, closed_where, "MEDIAN(cycle_time_days)")
        avg = analytics.scalar(con, closed_where, "AVG(cycle_time_days)")
        open_n = analytics.total_rows(con, analytics._where_and(where, '"is_open" = TRUE'))
        components.kpi_row([
            {"label": "Closed", "value": fmt_int(closed_n), "tone": "good"},
            {"label": "Still Open", "value": fmt_int(open_n), "tone": "warn"},
            {"label": "Median Cycle Time", "value": f"{med:.0f} d" if med else "—"},
            {"label": "Avg Cycle Time", "value": f"{avg:.0f} d" if avg else "—"},
        ])

    section("Closure trend & rate by region")
    c1, c2 = st.columns(2)
    with c1:
        ts = analytics.timeseries(con, closed_where, "closure_date", "month")
        if not ts.empty:
            st.plotly_chart(charts.line(ts, "period", "value", area=True,
                                        title="Closures per month", color="#107C41"),
                            width="stretch")
        else:
            components.empty_state("No closure dates available in selection.")
    with c2:
        cr = analytics.closure_rate_by(con, where, "region_geo")
        if not cr.empty:
            st.plotly_chart(charts.bar(cr, "category", "closure_rate", horizontal=True,
                                       title="Closure rate by region (%)"),
                            width="stretch")

    section("Closure aging")
    aging = analytics.aging_buckets(con, where, only_open=True)
    if not aging.empty:
        st.plotly_chart(charts.bar(aging.astype({"bucket": str}), "bucket", "count",
                                   title="Age of open nominations", color_status=False),
                        width="stretch")

    section("Operational lists")
    c3, c4 = st.columns(2)
    with c3:
        st.markdown("**⏳ Longest-open nominations**")
        open_where = analytics._where_and(where, '"is_open" = TRUE')
        cols = ["customer_name", "migration_path", "region_geo", "eos_status", "aging_days"]
        cols = [c for c in cols if c in ctx.fact.columns]
        components.show_table(
            analytics.fetch_rows(con, open_where, cols, "aging_days", True, 15), height=380)
    with c4:
        st.markdown("**✅ Closed in selected range**")
        cols2 = ["customer_name", "migration_path", "region_geo", "cycle_time_days", "closure_date"]
        cols2 = [c for c in cols2 if c in ctx.fact.columns]
        components.show_table(
            analytics.fetch_rows(con, closed_where, cols2, "closure_date", True, 50), height=380)
