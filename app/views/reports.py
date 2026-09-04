"""Reports & Export — assemble a PDF from the modules, period and categories you pick."""
from __future__ import annotations

from datetime import datetime

import streamlit as st

from app import state
from app.core import analytics, exporter, segments
from app.core.metrics import fmt_int
from app.ui import components
from app.ui.theme import page_header, section, subheading

_PRESET_BUNDLES = {
    "Executive pack": ["categories", "overview", "insights"],
    "Delivery review": ["overview", "approved", "closed", "tables"],
    "Data quality review": ["inconsistency", "tables"],
    "Everything": exporter.SECTION_KEYS,
}


def render() -> None:
    ctx = state.ensure_context()
    table = state.active_table()
    analytics.use_table(table)
    unit = state.unit_label().title()
    page_header("Reports & Export",
                "Build the PDF you need: pick the modules, the reporting period, the "
                "migration categories and the cover text. Everything renders locally.",
                help="The cover, executive summary and key metrics are always included. "
                     "Sidebar filters and the reporting period below both apply to the "
                     "report's contents.")
    components.data_quality_banner(ctx)

    # The report is scope-agnostic: each PDF section applies its own reporting
    # motion, so the sidebar exposes region/status only.
    date_filter = components.page_date_filter(ctx, "rep", "created_date", table=table)
    filters, where = components.filter_sidebar(
        ctx, ["region_geo"], table=table, date_filter=date_filter)
    scope_label = "Filtered view" if where else "All data"
    n = analytics.total_rows(ctx.con, where)
    window = ((date_filter["start"], date_filter["end"]) if date_filter else (None, None))
    period_label = (f"{window[0]:%d %b %Y} → {window[1]:%d %b %Y}"
                    if window[0] else "All dates in the dataset")

    # ---------------------------------------------------------------- modules
    section("1 · What to include",
            help="Start from a bundle, then tick or untick individual modules.")
    bundle = st.radio("Start from", list(_PRESET_BUNDLES), horizontal=True, key="rep_bundle")
    chosen = set(_PRESET_BUNDLES[bundle])
    cols = st.columns(2)
    selected: list[str] = []
    for i, (key, label) in enumerate(exporter.SECTION_LIBRARY):
        with cols[i % 2]:
            if st.checkbox(label, value=key in chosen, key=f"rep_sec_{key}_{bundle}"):
                selected.append(key)

    categories = list(segments.CATEGORY_LABELS)
    if "categories" in selected:
        subheading("Migration categories to include")
        categories = st.multiselect(
            "Categories", list(segments.CATEGORY_LABELS),
            default=[segments.CAT_EOS_GEN1, segments.CAT_EOS_GEN2,
                     segments.CAT_ALL_AVS, segments.CAT_AVS_NATIVE],
            format_func=lambda c: segments.CATEGORY_LABELS[c], key="rep_cats")

    # ------------------------------------------------------------ cover text
    section("2 · Cover")
    c1, c2 = st.columns(2)
    title = c1.text_input("Report title", value="AVS Migration Analytics", key="rep_title")
    subtitle = c2.text_input("Subtitle", value="Executive Report", key="rep_subtitle")

    # -------------------------------------------------------------- generate
    section("3 · Generate")
    st.caption(f"**{scope_label}** · **{fmt_int(n)}** {unit.lower()} · period "
               f"**{period_label}** · as-of {ctx.as_of:%d %b %Y} · counting mode "
               f"**{state.count_mode()}** · {len(selected)} module(s) selected.")
    g1, g2 = st.columns([1, 2])
    with g1:
        if st.button("📄 Generate PDF", type="primary", width="stretch",
                     disabled=not selected):
            with st.spinner("Rendering PDF…"):
                st.session_state["_rep_pdf"] = exporter.build_report(
                    ctx, where, scope_label, selected, table=table, unit_label=unit,
                    title=title or "AVS Migration Analytics",
                    subtitle=subtitle, period_label=period_label,
                    categories=categories, date_window=window)
                st.session_state["_rep_name"] = (
                    f"AVS_Report_{datetime.now():%Y%m%d_%H%M}.pdf")
            st.success("Report ready — download below.")
    with g2:
        if st.session_state.get("_rep_pdf"):
            st.download_button("⬇️ Download PDF", st.session_state["_rep_pdf"],
                               file_name=st.session_state.get("_rep_name", "report.pdf"),
                               mime="application/pdf", width="stretch")
    if not selected:
        st.info("Tick at least one module above.")

    # ------------------------------------------------------------ data export
    section("4 · Data exports (CSV)")
    st.caption("The same filters and reporting period, as data.")
    frame = analytics.select_all(ctx.con, where)
    e1, e2, e3 = st.columns(3)
    with e1:
        st.download_button("⬇️ Cleaned data (current view)",
                           frame.to_csv(index=False).encode("utf-8"),
                           file_name="avs_clean_data.csv", mime="text/csv", width="stretch")
    with e2:
        from app.core import insights as insights_mod
        ins = insights_mod.generate_insights(frame)
        st.download_button("⬇️ Insights",
                           insights_mod.insights_to_frame(ins).to_csv(index=False).encode("utf-8"),
                           file_name="avs_insights.csv", mime="text/csv", width="stretch")
    with e3:
        issues = segments.eos_consistency(ctx.fact)
        combined = "\n".join(f"# {k}\n{v.to_csv(index=False)}" for k, v in issues.items())
        st.download_button("⬇️ Data inconsistencies", combined.encode("utf-8"),
                           file_name="avs_inconsistencies.csv", mime="text/csv",
                           width="stretch")
