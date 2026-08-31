"""Status Report — AVS → Azure Native nominations.

This is the dedicated home for offerings whose migration path is "(From AVS)"
(SQL / OSS DB / Windows / Linux migrations away from AVS to Azure-native
services).  These nominations are intentionally **excluded from every other
status report** so the primary "AVS Migration Nominations" reporting stays
focused on onboarding to AVS.  Trend analysis for these lives on the
**AVS → Azure Native Migration Trends** page.

Every chart opens the records behind it, with a CSV export.

The **offering / Azure-target** cut lives on **Migration Analytics → AVS →
Azure Native**, next to this motion's metrics and trends; this page keeps the
delivery pipeline and the record list.
"""
from __future__ import annotations

import streamlit as st

from app import state
from app.config import SCOPE_FROM_AVS
from app.core import analytics
from app.core.metrics import fmt_currency, fmt_int
from app.ui import charts, components, drilldown
from app.ui.theme import banner, page_header, section


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

    date_filter = components.page_date_filter(
        ctx, "ans", "created_date", table=table, scope=SCOPE_FROM_AVS)
    filters, where = components.filter_sidebar(
        ctx, ["region_geo", "migration_path", "azure_target",
              "migration_status_label"], table=table, scope=SCOPE_FROM_AVS, date_filter=date_filter)

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

    # One fetch of the selected records; every drill-down below reads from it.
    records = analytics.select_all(con, where)

    components.banner_note(
        "<b>By offering &amp; target</b> now lives on <b>Migration Analytics → "
        "AVS → Azure Native</b>, alongside this motion's metrics and trends — "
        "one place to read it rather than two.")

    section("Migration status pipeline")
    st.caption("Click a bar to open the nominations at that stage.")
    stages = analytics.count_by(con, where, "migration_status_label")
    if not stages.empty:
        pipe = analytics.crosstab(con, where, "migration_status_label", "region_geo")
        fig = charts.stacked_bar(pipe, title="Migration status by region")
        fig.update_xaxes(type="category")
        drilldown.chart_with_drilldown(
            fig, records, "migration_status_label", key="ans_pipe",
            what="nominations", max_rows=500,
            summary=stages.rename(columns={"category": "Migration Status",
                                           "count": "Nominations"}),
            summary_bucket="Migration Status")
        drilldown.data_expander(
            pipe.reset_index().rename(columns={"row": "Migration Status"}),
            "ans_pipe_grid", label="Underlying data — status × region",
            caption="Nomination counts per migration status and region.")

    section("Nomination records")
    st.caption("Every record in the current selection.")
    cols = ["task_id", "customer_name", "region_geo", "migration_path", "azure_target",
            "migration_status_label", "total_acr", "created_date"]
    cols = [c for c in cols if c in records.columns]
    frame = records[cols].sort_values("created_date", ascending=False)
    components.show_table(frame.head(500), height=420)
    if len(frame) > 500:
        st.caption(f"Showing the first 500 of {fmt_int(len(frame))} records — "
                   "the CSV export has them all.")
    st.download_button("⬇️ Export all records to CSV",
                       frame.to_csv(index=False).encode("utf-8"),
                       file_name="avs-native-records.csv", mime="text/csv",
                       key="ans_records_csv")
