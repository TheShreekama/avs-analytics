"""Report 2 — AVS Nominations Approved."""
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
    page_header("AVS Nominations Approved",
                "Approval velocity across calendar windows, trends and regional comparison.")
    components.data_quality_banner(ctx)
    if state.is_customer_mode():
        components.banner_note("Customer mode: each account's approval date is its "
                               "<b>Wave-1</b> approval date.")

    filters, where = components.filter_sidebar(
        ctx, ["region_geo", "migration_path", "migration_status_label"],
        date_field="approval_date", table=table, scope=SCOPE_PRIMARY)

    con = ctx.con
    # restrict to approved items for this report
    appr_where = analytics._where_and(where, '"is_approved" = TRUE')
    fact = analytics.select_all(con, appr_where)
    if fact.empty:
        components.empty_state("No approved nominations match the current filters.")
        return

    section(f"Approved nominations — as of {ctx.as_of:%d %b %Y}")
    components.period_kpi_row(fact["approval_date"], ctx.as_of, verb="Approved")
    st.write("")

    section("Approval trend")
    grain = st.radio("Granularity", ["Daily", "Weekly", "Monthly"], index=2, horizontal=True,
                     key="ap_grain")
    gmap = {"Daily": "day", "Weekly": "week", "Monthly": "month"}
    ts = analytics.timeseries(con, appr_where, "approval_date", gmap[grain])
    if not ts.empty:
        c1, c2 = st.columns([1.4, 1])
        with c1:
            st.plotly_chart(charts.line(ts, "period", "value", area=True,
                                        title=f"{grain} approvals"), width="stretch")
        with c2:
            st.plotly_chart(charts.line(ts, "period", "cumulative",
                                        title="Cumulative approvals", color="#107C41"),
                            width="stretch")

    section("Regional & path comparison")
    c3, c4 = st.columns(2)
    with c3:
        reg = analytics.count_by(con, appr_where, "region_geo")
        st.plotly_chart(charts.bar(reg, "category", "count", horizontal=True,
                                   title="Approvals by region"), width="stretch")
    with c4:
        trk = analytics.count_by(con, appr_where, "migration_path")
        st.plotly_chart(charts.bar(trk, "category", "count", horizontal=True,
                                   title="Approvals by migration path"),
                        width="stretch")

    section("Approval latency")
    c5, c6 = st.columns([1, 1.4])
    med = analytics.scalar(con, appr_where, "MEDIAN(approval_latency_days)")
    avg = analytics.scalar(con, appr_where, "AVG(approval_latency_days)")
    with c5:
        components.kpi_row([
            {"label": "Median Latency", "value": f"{med:.0f} d" if med else "—",
             "sub": "created → approved"},
            {"label": "Average Latency", "value": f"{avg:.0f} d" if avg else "—"},
        ])
    with c6:
        lat = analytics.timeseries(con, appr_where, "approval_date", "month")
        st.plotly_chart(charts.bar(lat, "period", "value", title="Approved per month"),
                        width="stretch")

    section("Approved nominations in selected range")
    cols = ["task_id", "customer_name", "region_geo", "migration_path",
            "migration_status_label", "approval_date", "approval_latency_days", "total_acr"]
    cols = [c for c in cols if c in ctx.fact.columns]
    rows = analytics.fetch_rows(con, appr_where, cols, "approval_date", True, 500)
    components.show_table(rows, height=360)
    st.caption("Reflects the date range selected in the sidebar (most recent first).")
