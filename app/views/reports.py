"""Reports & Export — build the management PDF and the CSV extracts."""
from __future__ import annotations

from datetime import datetime

import streamlit as st

from app import state
from app.core import analytics, exporter, segments
from app.core.metrics import fmt_int
from app.ui import components
from app.ui.theme import page_header, section, subheading


def render() -> None:
    ctx = state.ensure_context()
    table = state.active_table()
    analytics.use_table(table)
    unit = state.unit_label().title()
    page_header("Reports & Export",
                "A management report in two parts: the three migration reports up "
                "front, the detail behind them after. Everything renders locally.",
                help="The cover and contents are always included. Sidebar filters "
                     "and the reporting period below both apply to the report's "
                     "contents.")
    components.data_quality_banner(ctx)

    # Each report selects its own migration category, so the sidebar exposes
    # region only — scope is never something the reader has to set by hand.
    date_filter = components.page_date_filter(ctx, "rep", "created_date", table=table)
    filters, where = components.filter_sidebar(
        ctx, ["region_geo"], table=table, date_filter=date_filter)
    scope_label = "Filtered view" if where else "All data"
    n = analytics.total_rows(ctx.con, where)
    window = ((date_filter["start"], date_filter["end"]) if date_filter else (None, None))
    period_label = (f"{window[0]:%d %b %Y} → {window[1]:%d %b %Y}"
                    if window[0] else "All dates in the dataset")

    # ---------------------------------------------------------------- reports
    section("1 · Reports to include",
            help="Each report mirrors its Migration Analytics dashboard — the same "
                 "population, the same metrics, computed by the same code.")
    cols = st.columns(3)
    selected: list[str] = []
    for col, spec in zip(cols, exporter.REPORTS):
        with col:
            if st.checkbox(spec.title, value=True, key=f"rep_r_{spec.key}"):
                selected.append(spec.key)
            st.caption(spec.source)

    subheading("Supporting detail")
    d1, d2 = st.columns([2, 3])
    with d1:
        drilldown = st.checkbox(
            "Include drill-down sections", value=True, key="rep_drill",
            help="Part 2 of the PDF: the monthly numbers, the regional matrix and "
                 "the account records behind each report, on landscape pages. "
                 "Each report links to its drill-down and back.")
    with d2:
        max_rows = st.slider(
            "Account rows per drill-down", 50, 1000, exporter.MAX_DRILLDOWN_ROWS, 50,
            key="rep_rows", disabled=not drilldown,
            help="Accounts are listed largest-ACR first within each region. Beyond "
                 "this many the table is truncated with a note — export the full "
                 "set as CSV below.")

    subheading("Appendix")
    appendices: list[str] = []
    for key, label in exporter.APPENDIX_LIBRARY:
        if st.checkbox(label, value=False, key=f"rep_a_{key}"):
            appendices.append(key)

    # ------------------------------------------------------------ cover text
    section("2 · Cover")
    c1, c2 = st.columns(2)
    title = c1.text_input("Report title", value="AVS Migration Analytics",
                          key="rep_title")
    subtitle = c2.text_input("Subtitle", value="Management Report", key="rep_subtitle")

    # -------------------------------------------------------------- generate
    section("3 · Generate")
    st.caption(f"**{scope_label}** · **{fmt_int(n)}** {unit.lower()} · period "
               f"**{period_label}** · as-of {ctx.as_of:%d %b %Y} · "
               f"{len(selected)} report(s)"
               f"{' + drill-down' if drilldown and selected else ''}.")
    st.caption("Every figure is counted per account at its latest wave, exactly as "
               "the Migration Analytics dashboards count it — the sidebar's "
               "counting mode does not change the report.")
    g1, g2 = st.columns([1, 2])
    with g1:
        if st.button("📄 Generate PDF", type="primary", width="stretch",
                     disabled=not (selected or appendices)):
            with st.spinner("Rendering PDF…"):
                st.session_state["_rep_pdf"] = exporter.build_report(
                    ctx, where, scope_label, selected,
                    title=title or "AVS Migration Analytics",
                    subtitle=subtitle, period_label=period_label,
                    date_window=window, drilldown=drilldown,
                    appendices=appendices, max_drilldown_rows=max_rows)
                st.session_state["_rep_name"] = (
                    f"AVS_Report_{datetime.now():%Y%m%d_%H%M}.pdf")
            st.success("Report ready — download below.")
    with g2:
        if st.session_state.get("_rep_pdf"):
            st.download_button("⬇️ Download PDF", st.session_state["_rep_pdf"],
                               file_name=st.session_state.get("_rep_name", "report.pdf"),
                               mime="application/pdf", width="stretch")
    if not (selected or appendices):
        st.info("Tick at least one report above.")

    # ------------------------------------------------------------ data export
    section("4 · Data exports (CSV)")
    st.caption("The same filters and reporting period, as data.")
    frame = analytics.select_all(ctx.con, where)
    e1, e2, e3 = st.columns(3)
    with e1:
        st.download_button("⬇️ Cleaned data (current view)",
                           frame.to_csv(index=False).encode("utf-8"),
                           file_name="avs_clean_data.csv", mime="text/csv",
                           width="stretch")
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
