"""Report 4 — EOS Migration Nomination Status.

Tracks the derived operational/EOS taxonomy (On Track, Completed, At Risk,
Delayed, Blocked, Cancelled) with a Region × Status heatmap and aging analysis.
The status is derived from Current State + Milestone Status + Migration Status
code + planned-end vs as-of date (see core/cleaning.py).

Every chart opens the records behind it: click a status, an age band or a table
row and those nominations appear underneath, with a CSV export.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from app import state
from app.config import EOS_STATUS_ORDER
from app.core import analytics, insights as insights_mod
from app.core.metrics import fmt_int
from app.ui import charts, components, drilldown
from app.ui.theme import banner, page_header, section


def render() -> None:
    ctx = state.ensure_context()
    table = state.active_table()
    analytics.use_table(table)
    unit = state.unit_label()
    page_header("EOS Migration Status",
                "Operational health of EOS (End-of-Support) migration nominations.")
    components.data_quality_banner(ctx)
    scope = ("each customer counts once if <b>any</b> wave is an EOS migration; "
             "status follows the customer's <b>last wave</b>") if state.is_customer_mode() else \
            "every wave that is an EOS migration"
    banner(f"<b>Scope:</b> EOS Migration nominations — {scope}. "
           "Operational status is derived from Current State, Milestone Status, Migration Status code "
           "and planned-end vs as-of date.")

    date_filter = components.page_date_filter(
        ctx, "eos", "planned_end_date", table=table, scope=None)
    filters, where = components.filter_sidebar(
        ctx, ["region_geo", "eos_status", "migration_path"], table=table, date_filter=date_filter)
    # Restrict the report to the EOS Migration population — the same definition the
    # EOS dashboards use, so the two never disagree.
    where = analytics._where_and(where, '"is_eos_population" = TRUE')

    con = ctx.con
    n_av36 = analytics.total_rows(con, where)
    if n_av36 == 0:
        components.empty_state(
            "No EOS Migration nominations in the current selection. (An account is EOS "
            "when any wave carries an AVS Migration - Gen1/Gen2 tag, or — untagged — its "
            "migration path reads AV36/AV36P/AV52 - EOS.)")
        return

    # Status KPI tiles in canonical order
    counts = {r["category"]: int(r["count"])
              for _, r in analytics.count_by(con, where, "eos_status").iterrows()}
    items = []
    for s in EOS_STATUS_ORDER:
        tone = {"Completed": "good", "On Track": "good", "At Risk": "warn",
                "Delayed": "warn", "Blocked": "bad", "Cancelled": ""}.get(s, "")
        items.append({"label": s, "value": fmt_int(counts.get(s, 0)), "tone": tone})
    components.kpi_row(items)
    st.caption(f"**{fmt_int(n_av36)}** EOS Migration {unit} in scope "
               f"(status taken from each account's last wave).")
    st.write("")

    # One fetch of the EOS population in scope; every drill-down below reads it.
    records = analytics.select_all(con, where)

    section("Status distribution")
    st.caption("Click a slice or a bar to open the nominations in that status.")
    dist = analytics.count_by(con, where, "eos_status")
    drilldown.charts_with_drilldown(
        [charts.donut(dist, "category", "count", title="Operational status share"),
         charts.bar(dist, "category", "count", color_status=True,
                    title="Operational status counts")],
        records, "eos_status", key="eos_dist", what="nominations", max_rows=500)

    section("Region vs operational status")
    pivot = analytics.crosstab(con, where, "region_geo", "eos_status")
    if not pivot.empty:
        ordered = [c for c in EOS_STATUS_ORDER if c in pivot.columns]
        st.plotly_chart(charts.heatmap(pivot[ordered], colorscale="RdYlGn_r",
                                       title="Risk concentration by region"),
                        width="stretch")
        drilldown.data_expander(
            pivot[ordered].reset_index().rename(columns={"row": "Region"}),
            "eos_region_table", label="Underlying data — region × status",
            caption="Nomination counts per region and operational status.")

    section("Status trend over time")
    sql = f'''SELECT date_trunc('month', created_date) AS period, eos_status,
              COUNT(*) AS value FROM {table} {where} AND created_date IS NOT NULL
              GROUP BY 1,2 ORDER BY 1'''
    long = con.execute(sql).fetchdf()
    c3, c4 = st.columns(2)
    with c3:
        if not long.empty:
            st.plotly_chart(charts.multi_line(long, "period", "eos_status", "value",
                                              title="Operational status by month"),
                            width="stretch")
    with c4:
        pivot2 = analytics.crosstab(con, where, "migration_path", "eos_status")
        if not pivot2.empty:
            ordered2 = [c for c in EOS_STATUS_ORDER if c in pivot2.columns]
            st.plotly_chart(charts.stacked_bar(pivot2[ordered2], horizontal=True,
                                               title="Operational status by migration path"),
                            width="stretch")
    if not long.empty:
        drilldown.data_expander(
            long.assign(period=pd.to_datetime(long["period"]).dt.strftime("%Y-%m"))
                .rename(columns={"period": "Month", "eos_status": "Operational Status",
                                 "value": "Nominations"}),
            "eos_trend_table", label="Underlying data — status by month")
    if not pivot2.empty:
        drilldown.data_expander(
            pivot2[ordered2].reset_index().rename(columns={"row": "Migration Path"}),
            "eos_path_table", label="Underlying data — status by migration path")

    section("Aging analysis (open items)")
    st.caption("Click an age band to open the nominations sitting in it.")
    aging = analytics.aging_buckets(con, where, only_open=True)
    open_rows = records[records["is_open"].astype(bool)] if "is_open" in records else records
    if aging.empty or open_rows.empty:
        components.empty_state("Nothing is still open in the current selection.")
    else:
        fig = charts.bar(aging.astype({"bucket": str}), "bucket", "count",
                         title="Age of open nominations")
        fig.update_xaxes(type="category")
        drilldown.chart_with_drilldown(
            fig, open_rows.assign(bucket=analytics.aging_bucket(open_rows["aging_days"])),
            "bucket", key="eos_aging", what="open nominations", max_rows=500,
            summary=aging.astype({"bucket": str}).rename(
                columns={"bucket": "Age band", "count": "Open nominations"}),
            summary_bucket="Age band")

    section("At-risk, delayed and blocked items")
    risk = records[records["eos_status"].isin(["At Risk", "Delayed", "Blocked"])]
    if risk.empty:
        st.success("✅ Nothing at risk, delayed or blocked in the current selection.")
    else:
        cols = [c for c in ("customer_name", "region_geo", "eos_status",
                            "migration_status_label", "total_acr", "aging_days")
                if c in risk.columns]
        frame = risk[cols].sort_values("aging_days", ascending=False)
        components.show_table(frame.head(50), height=340)
        if len(frame) > 50:
            st.caption(f"Showing the 50 oldest of {fmt_int(len(frame))} — "
                       "the CSV export has them all.")
        st.download_button("⬇️ Export to CSV", frame.to_csv(index=False).encode("utf-8"),
                           file_name="eos-at-risk.csv", mime="text/csv", key="eos_risk_csv")

    section("Operational insights")
    ins = [i for i in insights_mod.generate_insights(records)
           if i.category in ("EOS Risk", "Backlog", "Closures")]
    components.insight_cards(ins, columns=2)
