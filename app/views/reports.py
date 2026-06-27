"""Reports — build a PDF for selected modules or a comprehensive report."""
from __future__ import annotations

from datetime import datetime

import streamlit as st

from app import state
from app.core import analytics, exporter
from app.core.metrics import fmt_int
from app.ui import components
from app.ui.theme import page_header, section


def render() -> None:
    ctx = state.ensure_context()
    table = state.active_table()
    analytics.use_table(table)
    unit = state.unit_label().title()
    page_header("Reports & PDF Export",
                "Generate an executive PDF — choose specific modules or a comprehensive report. "
                "Everything is rendered locally.")
    components.data_quality_banner(ctx)

    # No reporting scope here: the PDF splits primary vs AVS→Azure per-section,
    # so the sidebar filters stay scope-agnostic (region / status only).
    filters, where = components.filter_sidebar(
        ctx, ["region_geo", "eos_status"], date_field="created_date", table=table)
    scope = "Filtered view" if where else "All data"
    n = analytics.total_rows(ctx.con, where)

    section("What to include")
    mode = st.radio("Report type", ["Comprehensive (all modules)", "Choose specific modules"],
                    horizontal=True)
    if mode.startswith("Comprehensive"):
        selected = exporter.SECTION_KEYS
        st.caption("Includes: cover, executive summary, KPIs, and every report module below.")
        st.write(" · ".join(label for _, label in exporter.SECTION_LIBRARY))
    else:
        st.caption("Pick the modules to include. Cover, executive summary and KPIs are always included.")
        cols = st.columns(2)
        selected = []
        for i, (key, label) in enumerate(exporter.SECTION_LIBRARY):
            with cols[i % 2]:
                if st.checkbox(label, value=key in ("overview", "insights"), key=f"sec_{key}"):
                    selected.append(key)
        if not selected:
            st.info("Select at least one module (or switch to Comprehensive).")

    section("Generate")
    c1, c2 = st.columns([1, 2])
    with c1:
        disabled = not selected
        if st.button("📄 Generate PDF", type="primary", width="stretch", disabled=disabled):
            with st.spinner("Rendering executive PDF…"):
                pdf = exporter.build_report(ctx, where, scope, selected, table=table,
                                            unit_label=unit)
                st.session_state["_rep_pdf"] = pdf
                st.session_state["_rep_name"] = (
                    f"AVS_Report_{datetime.now():%Y%m%d_%H%M}.pdf")
            st.success("Report ready — download below.")
    with c2:
        if st.session_state.get("_rep_pdf"):
            st.download_button("⬇️ Download PDF", st.session_state["_rep_pdf"],
                               file_name=st.session_state.get("_rep_name", "report.pdf"),
                               mime="application/pdf", width="stretch")
    st.caption(f"Scope: **{scope}** · **{fmt_int(n)}** {unit.lower()} · "
               f"as-of {ctx.as_of:%d %b %Y} · counting mode: **{state.count_mode()}**.")

    # Data exports
    section("Data exports (CSV)")
    d1, d2 = st.columns(2)
    with d1:
        frame = analytics.select_all(ctx.con, where)
        st.download_button("⬇️ Cleaned data (current view)",
                           frame.to_csv(index=False).encode("utf-8"),
                           file_name="avs_clean_data.csv", mime="text/csv", width="stretch")
    with d2:
        from app.core import insights as insights_mod
        ins = insights_mod.generate_insights(analytics.select_all(ctx.con, where))
        st.download_button("⬇️ Insights",
                           insights_mod.insights_to_frame(ins).to_csv(index=False).encode("utf-8"),
                           file_name="avs_insights.csv", mime="text/csv", width="stretch")
