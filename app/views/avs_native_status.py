"""Status Report — AVS → Azure Native nominations.

This is the dedicated home for offerings whose migration path is "(From AVS)"
(SQL / OSS DB / Windows / Linux migrations away from AVS to Azure-native
services).  These nominations are intentionally **excluded from every other
status report** so the primary "AVS Migration Nominations" reporting stays
focused on onboarding to AVS.  Trend analysis for these lives on the
**AVS → Azure Native Migration Trends** page.
"""
from __future__ import annotations

import streamlit as st

from app import state
from app.config import EOS_STATUS_ORDER, SCOPE_FROM_AVS
from app.core import analytics
from app.core.metrics import fmt_currency, fmt_int
from app.ui import charts, components
from app.ui.theme import banner, page_header, section

_TRACK = "migration_path"   # full offering names, e.g. "SQL Server MI Migration (From AVS)"


def render() -> None:
    ctx = state.ensure_context()
    table = state.active_table()
    analytics.use_table(table)
    unit = state.unit_label().title()
    page_header("AVS → Azure Native — Status",
                "Status of migrations away from AVS to Azure-native services "
                "(the '(From AVS)' offerings).")
    components.data_quality_banner(ctx)
    banner("<b>Scope:</b> only offerings whose migration path is <b>(From AVS)</b> — "
           "SQL DB / MI / IaaS, OSS DB, Windows, Linux, Oracle DB@Azure, AKS. "
           "These are reported here and on the AVS → Azure Native <b>Trends</b> page only.")

    filters, where = components.filter_sidebar(
        ctx, ["region_geo", "migration_path", "azure_target",
              "migration_status_label", "eos_status"],
        date_field="created_date", table=table, scope=SCOPE_FROM_AVS)

    con = ctx.con
    total = analytics.total_rows(con, where)
    if total == 0:
        components.empty_state("No AVS → Azure Native nominations in the current selection.")
        return

    accounts = int(analytics.scalar(con, where, "COUNT(DISTINCT tpid)"))
    closed = analytics.total_rows(con, analytics._where_and(where, '"is_closed" = TRUE'))
    open_n = analytics.total_rows(con, analytics._where_and(where, '"is_open" = TRUE'))
    acr = analytics.scalar(con, where, "COALESCE(SUM(total_acr),0)")
    comp_rate = round(100 * closed / total, 1) if total else 0
    components.kpi_row([
        {"label": unit, "value": fmt_int(total), "sub": f"{fmt_int(accounts)} accounts"},
        {"label": "Completed", "value": fmt_int(closed), "tone": "good"},
        {"label": "Open / In-flight", "value": fmt_int(open_n), "tone": "warn"},
        {"label": "Completion Rate", "value": f"{comp_rate:.0f}%",
         "tone": "good" if comp_rate >= 50 else "warn"},
        {"label": "Total ACR", "value": fmt_currency(acr)},
    ])
    st.write("")

    section("By offering & target")
    c1, c2 = st.columns(2)
    with c1:
        trk = analytics.count_by(con, where, _TRACK)
        st.plotly_chart(charts.bar(trk, "category", "count", horizontal=True,
                                   title="Nominations by migration path (offering)"),
                        width="stretch")
    with c2:
        tgt = analytics.count_by(con, where, "azure_target")
        st.plotly_chart(charts.donut(tgt, "category", "count",
                                     title="Azure-native targets"), width="stretch")

    section("Operational status")
    c3, c4 = st.columns(2)
    with c3:
        # x-axis = operational status; bars stacked by region.
        pivot = analytics.crosstab(con, where, "eos_status", "region_geo")
        if not pivot.empty:
            order = [s for s in EOS_STATUS_ORDER if s in pivot.index]
            st.plotly_chart(charts.stacked_bar(pivot.reindex(order),
                                               title="Operational status by region"),
                            width="stretch")
    with c4:
        # offering (full name) × status heatmap
        heat = analytics.crosstab(con, where, _TRACK, "eos_status")
        if not heat.empty:
            cols = [c for c in EOS_STATUS_ORDER if c in heat.columns]
            st.plotly_chart(charts.heatmap(heat[cols] if cols else heat,
                                           title="Migration path × status heatmap"),
                            width="stretch")

    section("Migration status pipeline")
    pipe = analytics.crosstab(con, where, "migration_status_label", "region_geo")
    if not pipe.empty:
        st.plotly_chart(charts.stacked_bar(pipe, title="Migration status by region"),
                        width="stretch")

    section("Nomination records")
    cols = ["task_id", "customer_name", "region_geo", "migration_path", "azure_target",
            "migration_status_label", "eos_status", "total_acr", "created_date"]
    cols = [c for c in cols if c in ctx.fact.columns]
    rows = analytics.fetch_rows(con, where, cols, "created_date", True, 500)
    components.show_table(rows, height=420)
    st.caption(f"Showing up to 500 of {fmt_int(total)} records.")
