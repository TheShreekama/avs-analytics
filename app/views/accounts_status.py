"""Report 1 — Accounts by Migration Status.

Every chart on this page opens the records behind it: click a status, a region or
a table row and the nominations that produced that number appear underneath, with
a CSV export.  Charts drawn from a cross-tab (which has no single record-level
bucket to click) expose the cross-tab itself instead.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from app import state
from app.config import SCOPE_PRIMARY
from app.core import analytics, kpi
from app.core.metrics import fmt_int
from app.ui import charts, components, drilldown
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
        ctx, ["region_geo", "migration_status_label", "migration_path"], table=table,
        scope=SCOPE_PRIMARY, date_filter=date_filter)

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
        {"label": "Regions", "value": fmt_int(int(analytics.scalar(
            con, where, "COUNT(DISTINCT region_geo)")))},
    ])
    st.write("")

    # One fetch of the selected records; every drill-down below reads from it.
    records = analytics.select_all(con, where)

    section("Status distribution")
    st.caption("Click a slice or a bar to open the nominations behind it.")
    status = analytics.count_by(con, where, "migration_status_label")
    acct = analytics.distinct_count_by(con, where, "migration_status_label", "tpid")
    drilldown.charts_with_drilldown(
        [charts.donut(status, "category", "count", title="Nominations by migration status"),
         charts.bar(acct, "category", "count", horizontal=True,
                    title="Accounts by migration status")],
        records, "migration_status_label", key="acc_status", what="nominations",
        max_rows=500)

    section("Regional breakdown")
    st.caption("Accounts at their latest wave, in the four in-flight stages or "
               "Completed — deduplicated by TPID regardless of the Counting mode "
               "toggle in the sidebar, so this always matches the Migration "
               "Analytics dashboards rather than following whichever mode happens "
               "to be selected.")
    # Always the raw wave-level table, collapsed to one row per TPID's latest wave
    # here — never the SQL "customer"/"fact" table the Counting mode toggle picks,
    # so a reader who switches that toggle to wave-level never sees this section
    # start counting nomination waves.
    latest = kpi.latest_wave(analytics.select_all(con, where, table="fact"))
    latest = latest[kpi.reported_stages(latest)] if not latest.empty else latest
    if latest.empty:
        components.empty_state("No regional data to report.")
    else:
        pivot = pd.crosstab(latest["migration_status_label"], latest["region_geo"])
        heat = pd.crosstab(latest["region_geo"], latest["migration_status_label"])
        c3, c4 = st.columns(2)
        with c3:
            mode = st.radio("View", ["Counts", "Share %"], horizontal=True, key="as_mode",
                            label_visibility="collapsed")
            st.plotly_chart(
                charts.stacked_bar(pivot, title="Migration status by region",
                                   percent=(mode == "Share %")),
                width="stretch")
        with c4:
            st.plotly_chart(charts.heatmap(heat, title="Region × status heatmap"),
                            width="stretch")
        drilldown.data_expander(
            pivot.reset_index().rename(columns={"migration_status_label": "Migration Status"}),
            "acc_pivot", label="Underlying data — status × region",
            caption="Account counts (each TPID's latest wave) per migration status "
                    "and region: the numbers both charts above are drawn from.")

    section("Grouped breakdown")
    dim = st.selectbox("Group accounts by",
                       ["region_geo", "customer_segment", "migration_path", "phase"],
                       format_func=lambda x: x.replace("_", " ").title(), key="as_dim")
    breakdown = analytics.crosstab(con, where, dim, "migration_status_label")
    if not breakdown.empty:
        breakdown = (breakdown.assign(Total=breakdown.sum(axis=1))
                              .sort_values("Total", ascending=False)
                              .reset_index().rename(columns={"row": dim}))
        components.show_table(breakdown)
        st.download_button("⬇️ Export to CSV",
                           breakdown.to_csv(index=False).encode("utf-8"),
                           file_name=f"accounts-by-{dim}.csv", mime="text/csv",
                           key="acc_breakdown_csv")
    st.caption("Click a bar in **Status distribution** above to see the records; "
               "this table is the same population, grouped a different way.")

    section("Nomination records")
    st.caption("Every record in the current selection.")
    cols = ["task_id", "customer_name", "region_geo", "migration_path",
            "migration_status_label", "current_state", "total_acr",
            "created_date"]
    cols = [c for c in cols if c in records.columns]
    frame = records[cols]
    components.show_table(frame.head(500), height=420)
    if len(frame) > 500:
        st.caption(f"Showing the first 500 of {fmt_int(len(frame))} records — "
                   "the CSV export has them all.")
    st.download_button("⬇️ Export all records to CSV",
                       frame.to_csv(index=False).encode("utf-8"),
                       file_name="accounts-by-status-records.csv", mime="text/csv",
                       key="acc_records_csv")
