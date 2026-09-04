"""Insights — full deterministic insights engine (PDF export lives on Reports)."""
from __future__ import annotations

import streamlit as st

from app import state
from app.config import SCOPE_PRIMARY
from app.core import analytics, insights as insights_mod
from app.ui import components
from app.ui.theme import page_header, section


def render() -> None:
    ctx = state.ensure_context()
    table = state.active_table()
    analytics.use_table(table)
    page_header("Insights",
                "Deterministic, rule-based insights derived directly from the data — no AI, no cloud.")
    components.data_quality_banner(ctx)

    date_filter = components.page_date_filter(
        ctx, "ins", "created_date", table=table, scope=SCOPE_PRIMARY)
    filters, where = components.filter_sidebar(
        ctx, ["region_geo", "migration_path"],
        table=table, scope=SCOPE_PRIMARY, date_filter=date_filter)

    fact = analytics.select_all(ctx.con, where)
    if fact.empty:
        components.empty_state()
        return
    ins = insights_mod.generate_insights(fact)
    st.caption(f"{len(fact):,} {state.unit_label()} in view · as-of {ctx.as_of:%d %b %Y} · "
               "Export a PDF from the **Reports** page.")

    # Insights grouped by category
    section("Insights")
    cats = list(dict.fromkeys(i.category for i in ins))
    tabs = st.tabs(["All"] + cats)
    with tabs[0]:
        components.insight_cards(ins, columns=2)
    for tab, cat in zip(tabs[1:], cats):
        with tab:
            components.insight_cards([i for i in ins if i.category == cat], columns=2)

    # Data quality detail
    if fact["has_dq_issue"].any():
        section("Data quality detail")
        dq = fact[fact["has_dq_issue"]][["task_id", "customer_name", "dq_flags"]]
        components.show_table(dq, height=300)
