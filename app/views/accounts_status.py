"""Report 1 — Accounts by Migration Status."""
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
    page_header("Accounts by Migration Status",
                "Distribution of accounts and nominations across the migration pipeline.")
    components.data_quality_banner(ctx)
    components.banner_note("<b>Scope:</b> AVS Migration Nominations (onboarding to AVS).")

    date_filter = components.page_date_filter(
        ctx, "acc", "created_date", table=table, scope=SCOPE_PRIMARY)
    filters, where = components.filter_sidebar(
        ctx, ["region_geo", "migration_status_label", "migration_path"], table=table, scope=SCOPE_PRIMARY, date_filter=date_filter)

    con = ctx.con
    total = analytics.total_rows(con, where)
    if total == 0:
        components.empty_state()
        return
    accounts = int(analytics.scalar(con, where, "COUNT(DISTINCT tpid)"))
    statuses = int(analytics.scalar(con, where, "COUNT(DISTINCT migration_status_label)"))

    components.kpi_row([
        {"label": "Nominations", "value": fmt_int(total)},
        {"label": "Distinct Accounts", "value": fmt_int(accounts)},
        {"label": "Pipeline Stages", "value": fmt_int(statuses)},
        {"label": "Regions", "value": fmt_int(int(analytics.scalar(con, where, "COUNT(DISTINCT region_geo)")))},
    ])
    st.write("")

    section("Status distribution")
    c1, c2 = st.columns([1, 1.2])
    with c1:
        status = analytics.count_by(con, where, "migration_status_label")
        st.plotly_chart(charts.donut(status, "category", "count",
                                     title="Nominations by migration status"),
                        width="stretch")
    with c2:
        acct = analytics.distinct_count_by(con, where, "migration_status_label", "tpid")
        st.plotly_chart(charts.bar(acct, "category", "count", horizontal=True,
                                   title="Accounts by migration status"),
                        width="stretch")

    section("Regional breakdown")
    # x-axis = migration status; bars stacked by region.
    pivot = analytics.crosstab(con, where, "migration_status_label", "region_geo")
    c3, c4 = st.columns(2)
    with c3:
        if not pivot.empty:
            mode = st.radio("View", ["Counts", "Share %"], horizontal=True, key="as_mode",
                            label_visibility="collapsed")
            st.plotly_chart(
                charts.stacked_bar(pivot, title="Migration status by region",
                                   percent=(mode == "Share %")),
                width="stretch")
    with c4:
        # region × status heatmap
        heat = analytics.crosstab(con, where, "region_geo", "migration_status_label")
        if not heat.empty:
            st.plotly_chart(charts.heatmap(heat, title="Region × status heatmap"),
                            width="stretch")

    section("Drill-down")
    dim = st.selectbox("Group accounts by",
                       ["region_geo", "customer_segment", "migration_path", "phase"],
                       format_func=lambda x: x.replace("_", " ").title(), key="as_dim")
    breakdown = analytics.crosstab(con, where, dim, "migration_status_label")
    if not breakdown.empty:
        breakdown = breakdown.assign(Total=breakdown.sum(axis=1)).sort_values("Total", ascending=False)
        components.show_table(breakdown.reset_index().rename(columns={"row": dim}))

    section("Nomination records")
    cols = ["task_id", "customer_name", "region_geo", "migration_path",
            "migration_status_label", "eos_status", "current_state", "total_acr", "created_date"]
    cols = [c for c in cols if c in ctx.fact.columns]
    rows = analytics.fetch_rows(con, where, cols, "created_date", True, 500)
    components.show_table(rows, height=420)
    st.caption(f"Showing up to 500 of {fmt_int(total)} records.")
