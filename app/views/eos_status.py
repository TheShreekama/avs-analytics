"""Report 4 — EOS Migration Nomination Status.

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
           "EOS status is derived from Current State, Milestone Status, Migration Status code "
           "and planned-end vs as-of date.")

    filters, where = components.filter_sidebar(
        ctx, ["region_geo", "eos_status", "migration_path"],
        date_field="planned_end_date", table=table)
    # Restrict the whole report to EOS Migration nominations.
    where = analytics._where_and(where, '"is_av36_eos" = TRUE')

    con = ctx.con
    n_av36 = analytics.total_rows(con, where)
    if n_av36 == 0:
        components.empty_state(
            "No EOS Migration nominations in the current selection. (A nomination counts as "
            "an EOS migration when its migration path, factory offering or linked offering "
            "carries an AV36 / AV36P / AV52 / AV64 / EOS / EGS / end-of-support marker.)")
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
    pivot = analytics.crosstab(con, where, "region_geo", "eos_status")
    if not pivot.empty:
        ordered = [c for c in EOS_STATUS_ORDER if c in pivot.columns]
        st.plotly_chart(charts.heatmap(pivot[ordered], colorscale="RdYlGn_r",
                                       title="Risk concentration by region"),
                        width="stretch")

    section("Status trend over time")
    c3, c4 = st.columns(2)
    with c3:
        # build a status x month long frame via SQL (where always includes AV36 filter)
        sql = f'''SELECT date_trunc('month', created_date) AS period, eos_status,
                  COUNT(*) AS value FROM {table} {where} AND created_date IS NOT NULL
                  GROUP BY 1,2 ORDER BY 1'''
        long = con.execute(sql).fetchdf()
        if not long.empty:
            st.plotly_chart(charts.multi_line(long, "period", "eos_status", "value",
                                              title="EOS status by month"),
                            width="stretch")
    with c4:
        pivot2 = analytics.crosstab(con, where, "migration_path", "eos_status")
        if not pivot2.empty:
            ordered2 = [c for c in EOS_STATUS_ORDER if c in pivot2.columns]
            st.plotly_chart(charts.stacked_bar(pivot2[ordered2], horizontal=True,
                                               title="EOS status by migration path"),
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
        cols = ["customer_name", "region_geo", "eos_status", "aging_days"]
        cols = [c for c in cols if c in ctx.fact.columns]
        st.markdown("**🚩 At-risk / blocked items**")
        components.show_table(
            analytics.fetch_rows(con, risk_where, cols, "aging_days", True, 12), height=320)

    section("Operational insights")
    fact = analytics.select_all(con, where)
    ins = [i for i in insights_mod.generate_insights(fact)
           if i.category in ("EOS Risk", "Backlog", "Closures")]
    components.insight_cards(ins, columns=2)
