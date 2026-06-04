"""Report 4 — AV36 EOS Nomination Status.

Tracks the derived operational/EOS taxonomy (On Track, Completed, At Risk,
Delayed, Blocked, Cancelled) with a Region × Status heatmap and aging analysis.
The status is derived from Current State + Milestone Status + Migration Status
code + planned-end vs as-of date (see core/cleaning.py).
"""
from __future__ import annotations

import streamlit as st

from app import state
from app.config import EOS_STATUS_ORDER, STATUS_COLORS
from app.core import analytics, insights as insights_mod
from app.core.metrics import fmt_int
from app.ui import charts, components
from app.ui.theme import banner, page_header, section


def render() -> None:
    ctx = state.ensure_context()
    page_header("AV36 EOS Nomination Status",
                "Operational health of EOS / AV36 migration nominations and risk hotspots.")
    components.data_quality_banner(ctx)
    banner("EOS status is derived from Current State, Milestone Status, Migration Status code "
           "and planned-end vs as-of date. Use the sidebar to focus on the AVS migration track.")

    filters, where = components.filter_sidebar(
        ctx, ["factory_offering", "ww_region", "region", "eos_status"],
        date_field="planned_end_date")

    con = ctx.con
    if analytics.total_rows(con, where) == 0:
        components.empty_state()
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
    st.write("")

    section("Status distribution")
    c1, c2 = st.columns(2)
    with c1:
        dist = analytics.count_by(con, where, "eos_status")
        st.plotly_chart(charts.donut(dist, "category", "count", title="EOS status share"),
                        width="stretch")
    with c2:
        st.plotly_chart(charts.bar(dist, "category", "count", color_status=True,
                                   title="EOS status counts"), width="stretch")

    section("Region vs EOS status (heatmap)")
    pivot = analytics.crosstab(con, where, "ww_region", "eos_status")
    if not pivot.empty:
        ordered = [c for c in EOS_STATUS_ORDER if c in pivot.columns]
        st.plotly_chart(charts.heatmap(pivot[ordered], colorscale="RdYlGn_r",
                                       title="Risk concentration by region"),
                        width="stretch")

    section("Status trend over time")
    c3, c4 = st.columns(2)
    with c3:
        # build a status x month long frame via SQL
        sql = f'''SELECT date_trunc('month', created_date) AS period, eos_status,
                  COUNT(*) AS value FROM fact {where if where else ''}
                  {"AND" if where else "WHERE"} created_date IS NOT NULL
                  GROUP BY 1,2 ORDER BY 1'''
        long = con.execute(sql).fetchdf()
        if not long.empty:
            st.plotly_chart(charts.multi_line(long, "period", "eos_status", "value",
                                              title="EOS status by month"),
                            width="stretch")
    with c4:
        pivot2 = analytics.crosstab(con, where, "factory_offering", "eos_status")
        if not pivot2.empty:
            ordered2 = [c for c in EOS_STATUS_ORDER if c in pivot2.columns]
            st.plotly_chart(charts.stacked_bar(pivot2[ordered2], horizontal=True,
                                               title="EOS status by track"),
                            width="stretch")

    section("Aging analysis (open & at-risk items)")
    aging = analytics.aging_buckets(con, where, only_open=True)
    c5, c6 = st.columns([1.3, 1])
    with c5:
        if not aging.empty:
            st.plotly_chart(charts.bar(aging.astype({"bucket": str}), "bucket", "count",
                                       title="Age of open nominations"),
                            width="stretch")
    with c6:
        risk_where = analytics._where_and(where, "eos_status IN ('At Risk','Delayed','Blocked')")
        cols = ["customer_name", "ww_region", "eos_status", "aging_days"]
        cols = [c for c in cols if c in ctx.fact.columns]
        st.markdown("**🚩 At-risk / blocked items**")
        components.show_table(
            analytics.fetch_rows(con, risk_where, cols, "aging_days", True, 12), height=320)

    section("Operational insights")
    fact = analytics.select_all(con, where)
    ins = [i for i in insights_mod.generate_insights(fact)
           if i.category in ("EOS Risk", "Backlog", "Closures")]
    components.insight_cards(ins, columns=2)
