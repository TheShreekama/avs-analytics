"""Insights & Export — full deterministic insights + one-click PDF/CSV export."""
from __future__ import annotations

from datetime import datetime

import streamlit as st

from app import state
from app.core import analytics, exporter, insights as insights_mod
from app.ui import components
from app.ui.theme import page_header, section


_SEV_ICON = {"positive": "✅", "info": "ℹ️", "warning": "⚠️", "critical": "🚩"}


def render() -> None:
    ctx = state.ensure_context()
    page_header("Insights & Executive Export",
                "Deterministic, rule-based insights derived directly from the data — no AI, no cloud.")
    components.data_quality_banner(ctx)

    filters, where = components.filter_sidebar(
        ctx, ["ww_region", "factory_offering", "eos_status"], date_field="created_date")

    fact = analytics.select_all(ctx.con, where)
    if fact.empty:
        components.empty_state()
        return
    ins = insights_mod.generate_insights(fact)

    # Export controls
    section("Executive report")
    c1, c2, c3 = st.columns([1, 1, 2])
    scope = "Filtered view" if where else "All data"
    with c1:
        if st.button("📄 Generate PDF report", type="primary", width="stretch"):
            with st.spinner("Rendering executive PDF…"):
                pdf = exporter.build_executive_pdf(ctx, where, scope)
                st.session_state["_pdf_bytes"] = pdf
                st.session_state["_pdf_name"] = f"AVS_Executive_Report_{datetime.now():%Y%m%d_%H%M}.pdf"
    with c2:
        if st.session_state.get("_pdf_bytes"):
            st.download_button("⬇️ Download PDF", st.session_state["_pdf_bytes"],
                               file_name=st.session_state.get("_pdf_name", "report.pdf"),
                               mime="application/pdf", width="stretch")
    with c3:
        csv = insights_mod.insights_to_frame(ins).to_csv(index=False).encode("utf-8")
        st.download_button("⬇️ Export insights (CSV)", csv,
                           file_name="avs_insights.csv", mime="text/csv")
        data_csv = fact.to_csv(index=False).encode("utf-8")
        st.download_button("⬇️ Export cleaned data (CSV)", data_csv,
                           file_name="avs_clean_data.csv", mime="text/csv")
    st.caption(f"Report scope: **{scope}** · {len(fact):,} nominations · "
               f"as-of {ctx.as_of:%d %b %Y}. The PDF includes summary, KPIs, charts, "
               "insights and key tables.")

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
