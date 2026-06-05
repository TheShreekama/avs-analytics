"""Executive Overview — the landing dashboard."""
from __future__ import annotations

import streamlit as st

from app import state
from app.core import analytics, insights as insights_mod
from app.core.metrics import fmt_currency, fmt_int, headline_kpis
from app.ui import charts, components
from app.ui.theme import page_header, section


def render() -> None:
    ctx = state.ensure_context()
    table = state.active_table()
    analytics.use_table(table)
    unit = state.unit_label().title()
    page_header("Executive Overview",
                "Portfolio-wide view of AVS migration nominations, approvals and delivery health.")
    components.data_quality_banner(ctx)

    filters, where = components.filter_sidebar(
        ctx, ["ww_region", "factory_offering", "migration_status_label", "eos_status"],
        date_field="created_date", table=table)

    fact = analytics.select_all(ctx.con, where)
    if fact.empty:
        components.empty_state()
        return
    k = headline_kpis(fact)

    components.kpi_row([
        {"label": unit, "value": fmt_int(k["nominations"]), "sub": f'{fmt_int(k["accounts"])} accounts'},
        {"label": "Approved", "value": fmt_int(k["approved"]), "tone": "good"},
        {"label": "Closed", "value": fmt_int(k["closed"]),
         "sub": f'{k["closure_rate"]:.0f}% closure rate', "tone": "good"},
        {"label": "Open / In-flight", "value": fmt_int(k["open"]),
         "sub": f'{k["median_age_days"]:.0f}d median age', "tone": "warn"},
        {"label": "Total ACR", "value": fmt_currency(k["total_acr"]), "sub": f'{fmt_int(k["total_cores"])} cores'},
        {"label": "Data Quality", "value": fmt_int(k["dq_rows"]),
         "sub": "rows flagged", "tone": "bad" if k["dq_rows"] else "good"},
    ])
    st.write("")

    # Row 1: status donut + region bar
    section("Migration status & regional distribution")
    c1, c2 = st.columns(2)
    with c1:
        status = analytics.count_by(ctx.con, where, "migration_status_label")
        st.plotly_chart(charts.donut(status, "category", "count",
                                     title="Nominations by Migration Status"),
                        width="stretch")
    with c2:
        reg = analytics.distinct_count_by(ctx.con, where, "ww_region", "tpid")
        st.plotly_chart(charts.bar(reg, "category", "count", horizontal=True,
                                   title="Accounts by Region"), width="stretch")

    # Row 2: stacked status x region + EOS heatmap
    section("Delivery health")
    c3, c4 = st.columns(2)
    with c3:
        pivot = analytics.crosstab(ctx.con, where, "ww_region", "eos_status")
        if not pivot.empty:
            cols = [c for c in ["On Track", "Completed", "At Risk", "Delayed", "Blocked", "Cancelled"]
                    if c in pivot.columns]
            st.plotly_chart(charts.stacked_bar(pivot[cols], title="Operational status by region"),
                            width="stretch")
    with c4:
        pivot2 = analytics.crosstab(ctx.con, where, "factory_offering", "eos_status")
        if not pivot2.empty:
            st.plotly_chart(charts.heatmap(pivot2, title="Track × status heatmap"),
                            width="stretch")

    # Trend
    section("Nomination volume over time")
    ts = analytics.timeseries(ctx.con, where, "created_date", "month")
    if not ts.empty:
        st.plotly_chart(charts.line(ts, "period", "value", area=True,
                                    title="Nominations created per month"),
                        width="stretch")

    # Top insights
    section("Top insights")
    ins = insights_mod.generate_insights(fact)
    components.insight_cards(ins[:6], columns=3)
    st.caption("See **Insights & Export** for the full insights engine and one-click PDF.")
