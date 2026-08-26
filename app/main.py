"""AVS Migration Analytics — application assembly.

This module is imported by the root-level ``Home.py`` entry point, which is what
``streamlit run`` executes.  Keeping the entry at the repo root ensures the
``app`` package is importable and avoids Streamlit's automatic ``pages/``
discovery (our report views live in ``app/views`` and are wired up explicitly
via ``st.navigation``).
"""
from __future__ import annotations

import pandas as pd
import streamlit as st


_BOOT_LOGGED = False


def run() -> None:
    # set_page_config must be the first Streamlit command executed.
    st.set_page_config(page_title="AVS Migration Analytics", page_icon="📈",
                       layout="wide", initial_sidebar_state="expanded")

    from app import state
    from app.config import APP_NAME, APP_TAGLINE
    from app.version import build_stamp, version_line
    from app.ui.theme import inject_css
    from app.views import (accounts_status, approved, approved_trends, avs_native_status,
                           avs_to_azure, category_dashboard, closed, column_mapping,
                           data_upload, eos_status, insights_page, methodology,
                           nomination_trends, overview, reports)

    global _BOOT_LOGGED
    if not _BOOT_LOGGED:                    # once per server start, into the console
        print(f"AVS Migration Analytics — {version_line()}", flush=True)
        _BOOT_LOGGED = True

    inject_css()
    ctx = state.ensure_context()
    _sidebar_brand(ctx, state, APP_NAME, APP_TAGLINE)

    # url_path must be explicit & unique because every view's callable is `render`.
    nav = st.navigation({
        "Executive": [
            st.Page(overview.render, title="Overview", icon=":material/dashboard:",
                    url_path="overview", default=True),
            st.Page(insights_page.render, title="Insights",
                    icon=":material/lightbulb:", url_path="insights"),
            st.Page(reports.render, title="Reports & Export",
                    icon=":material/picture_as_pdf:", url_path="reports"),
        ],
        "Migration Analytics": [
            st.Page(category_dashboard.eos_gen1, title="EOS Migration — Gen-1",
                    icon=":material/memory:", url_path="eos-gen1"),
            st.Page(category_dashboard.eos_gen2, title="EOS Migration — Gen-2",
                    icon=":material/developer_board:", url_path="eos-gen2"),
            st.Page(category_dashboard.eos_unclassified,
                    title="EOS Migration — Unclassified",
                    icon=":material/help_outline:", url_path="eos-unclassified"),
            st.Page(category_dashboard.all_avs, title="All AVS Migrations",
                    icon=":material/cloud:", url_path="all-avs"),
            st.Page(category_dashboard.avs_native, title="AVS → Azure Native",
                    icon=":material/cloud_sync:", url_path="avs-native"),
        ],
        "Status Reports": [
            st.Page(accounts_status.render, title="Accounts by Migration Status",
                    icon=":material/donut_large:", url_path="accounts-by-status"),
            st.Page(approved.render, title="Nominations Approved", icon=":material/task_alt:",
                    url_path="approved"),
            st.Page(closed.render, title="Nominations Closed", icon=":material/check_circle:",
                    url_path="closed"),
            st.Page(eos_status.render, title="EOS Migration Status",
                    icon=":material/warning:", url_path="eos-status"),
            st.Page(avs_native_status.render, title="AVS → Azure Native Status",
                    icon=":material/cloud_sync:", url_path="avs-native-status"),
        ],
        "Trend Analysis": [
            st.Page(nomination_trends.render, title="Nomination Trends",
                    icon=":material/timeline:", url_path="nomination-trends"),
            st.Page(approved_trends.render, title="Approved Trend Analysis",
                    icon=":material/trending_up:", url_path="approved-trends"),
            st.Page(avs_to_azure.render, title="AVS → Azure Native Trends",
                    icon=":material/swap_horiz:", url_path="avs-to-azure"),
        ],
        "Data": [
            st.Page(data_upload.render, title="Data & Upload", icon=":material/upload_file:",
                    url_path="data-upload"),
            st.Page(column_mapping.render, title="Column Mapping",
                    icon=":material/table_chart:", url_path="column-mapping"),
        ],
        "Reference": [
            st.Page(methodology.render, title="Methodology & Logic",
                    icon=":material/menu_book:", url_path="methodology"),
        ],
    })

    nav.run()
    st.sidebar.divider()
    built, fingerprint = build_stamp()
    st.sidebar.caption(f"**Build {built}** · `{fingerprint}`  \n"
                       f"{version_line().split(' · ')[0]} · Runs locally · No data "
                       f"leaves this machine")


def _sidebar_brand(ctx, state, app_name: str, tagline: str) -> None:
    st.sidebar.markdown(
        f"<div style='padding:6px 0 2px 0'>"
        f"<div style='font-size:1.25rem;font-weight:800;color:#0A4C86'>📈 {app_name}</div>"
        f"<div style='font-size:.78rem;color:#5C6470'>{tagline}</div></div>",
        unsafe_allow_html=True)
    st.sidebar.divider()

    src = "Sample dataset" if ctx.is_sample else ctx.filename
    n_cust = len(ctx.customer)
    st.sidebar.markdown(
        f"**Dataset:** {src}  \n**Waves:** {len(ctx.fact):,} · **Accounts:** {n_cust:,}")
    cur = pd.Timestamp(ctx.as_of).date()
    new_asof = st.sidebar.date_input("Reporting as-of date", value=cur,
                                     help="Anchors all date-range presets and the "
                                          "This-Week/Month/Quarter/YTD windows.")
    if pd.Timestamp(new_asof) != pd.Timestamp(ctx.as_of):
        state.reload_with(as_of=pd.Timestamp(new_asof))
        st.rerun()

    from app.ui import components
    components.global_date_controls(ctx)
    components.consistency_panel(ctx, sidebar=True)

    st.sidebar.radio(
        "Counting mode", [state.MODE_CUSTOMER, state.MODE_WAVE], key=state.MODE_KEY,
        help="Customer mode deduplicates waves: each customer counts once, with the "
             "approval date from Wave-1 and status from the last wave. Wave-level counts "
             "every nomination row.")
    st.sidebar.divider()
