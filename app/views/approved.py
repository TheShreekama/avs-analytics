"""Report 2 — AVS Nominations Approved.

Approval velocity, trend and regional comparison.  Every chart drills into the
approved nominations behind it: click a month, a region or a migration path and
those records appear underneath with a CSV export.
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

# (DuckDB date_trunc unit, pandas period alias, label format, table heading).
# Day and week labels are deliberately *not* ISO: a category axis hands the label
# straight back on click, and "2026-06-01" would be re-read as the month June.
_GRAINS = {
    "Daily":   ("day", "D", "%d %b %Y", "Day"),
    "Weekly":  ("week", "W", "w/c %d %b %Y", "Week commencing"),
    "Monthly": ("month", "M", "%Y-%m", "Month"),
}


def _categorical(fig):
    """Plot period labels verbatim, so a click returns the label that was drawn."""
    fig.update_xaxes(type="category")
    return fig


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

    date_filter = components.page_date_filter(
        ctx, "app", "approval_date", table=table, scope=SCOPE_PRIMARY)
    filters, where = components.filter_sidebar(
        ctx, ["region_geo", "migration_path", "migration_status_label"], table=table,
        scope=SCOPE_PRIMARY, date_filter=date_filter)

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
    st.caption("Click a point **or a table row** to open the nominations approved "
               "in that period.")
    grain = st.radio("Granularity", list(_GRAINS), index=2, horizontal=True, key="ap_grain")
    sql_grain, alias, fmt, heading = _GRAINS[grain]
    ts = analytics.timeseries(con, appr_where, "approval_date", sql_grain)
    if ts.empty:
        components.empty_state("No approval dates in the current selection.")
    else:
        ts = ts.assign(bucket=pd.to_datetime(ts["period"]).dt.strftime(fmt))
        rows = fact.assign(
            bucket=pd.to_datetime(fact["approval_date"], errors="coerce")
                     .dt.to_period(alias).dt.start_time.dt.strftime(fmt))
        summary = ts[["bucket", "value", "cumulative"]].rename(
            columns={"bucket": heading, "value": "Approved", "cumulative": "Cumulative"})
        drilldown.charts_with_drilldown(
            [_categorical(charts.line(ts, "bucket", "value", area=True,
                                      title=f"{grain} approvals")),
             _categorical(charts.line(ts, "bucket", "cumulative",
                                      title="Cumulative approvals", color="#107C41"))],
            rows, "bucket", key="ap_trend", what="approved nominations", max_rows=500)
        drilldown.data_expander(summary, "ap_trend_table",
                                label=f"Underlying data — {grain.lower()} totals",
                                caption="Cumulative runs over the periods shown.")

    section("Regional & path comparison")
    st.caption("Click a bar to open the nominations behind it.")
    reg = analytics.count_by(con, appr_where, "region_geo")
    trk = analytics.count_by(con, appr_where, "migration_path")
    c3, c4 = st.columns(2)
    with c3:
        picked_region = drilldown.selectable_chart(
            charts.bar(reg, "category", "count", horizontal=True,
                       title="Approvals by region"), key="ap_region")
    with c4:
        picked_path = drilldown.selectable_chart(
            charts.bar(trk, "category", "count", horizontal=True,
                       title="Approvals by migration path"), key="ap_path")
    drilldown.drilldown(fact, "region_geo", picked_region, key="ap_region_rows",
                        what="approvals by region", max_rows=500)
    drilldown.drilldown(fact, "migration_path", picked_path, key="ap_path_rows",
                        what="approvals by migration path", max_rows=500)

    section("Approval latency")
    med = analytics.scalar(con, appr_where, "MEDIAN(approval_latency_days)")
    avg = analytics.scalar(con, appr_where, "AVG(approval_latency_days)")
    components.kpi_row([
        {"label": "Median Latency", "value": f"{med:.0f} d" if med else "—",
         "sub": "created → approved"},
        {"label": "Average Latency", "value": f"{avg:.0f} d" if avg else "—"},
    ])
    if "approval_latency_days" in fact.columns:
        latency = (fact.assign(_days=pd.to_numeric(fact["approval_latency_days"],
                                                   errors="coerce"))
                       .groupby("region_geo", as_index=False)
                       .agg(Nominations=("_days", "size"),
                            **{"Median latency (days)": ("_days", "median"),
                               "Average latency (days)": ("_days", "mean")})
                       .rename(columns={"region_geo": "Region"})
                       .round(1))
        st.plotly_chart(charts.bar(latency, "Region", "Median latency (days)",
                                   horizontal=True,
                                   title="Median approval latency by region"),
                        width="stretch")
        drilldown.data_expander(latency, "ap_latency",
                                label="Underlying data — latency by region",
                                caption="Created → approved, over the same selection.")

    section("Approved nominations in the selected range")
    cols = ["task_id", "customer_name", "region_geo", "migration_path",
            "migration_status_label", "approval_date", "approval_latency_days", "total_acr"]
    cols = [c for c in cols if c in fact.columns]
    frame = fact[cols].sort_values("approval_date", ascending=False)
    components.show_table(frame.head(500), height=360)
    if len(frame) > 500:
        st.caption(f"Showing the first 500 of {fmt_int(len(frame))} records — "
                   "the CSV export has them all.")
    st.download_button("⬇️ Export all records to CSV",
                       frame.to_csv(index=False).encode("utf-8"),
                       file_name="approved-nominations.csv", mime="text/csv",
                       key="ap_records_csv")
