"""AVS Migration Analytics — Streamlit application entry point.

Run with:  streamlit run app/main.py
(or double-click the packaged launcher, which does this for you).
"""
from __future__ import annotations

import streamlit as st

# set_page_config must be the first Streamlit call.
st.set_page_config(page_title="AVS Migration Analytics", page_icon="📈",
                   layout="wide", initial_sidebar_state="expanded")

import pandas as pd

from app import state
from app.config import APP_NAME, APP_TAGLINE, APP_VERSION
from app.ui.theme import inject_css
from app.pages import (accounts_status, approved, approved_trends, avs_to_azure,
                       closed, column_mapping, data_upload, eos_status, insights_page,
                       nomination_trends, overview)


def _sidebar_brand(ctx) -> None:
    st.sidebar.markdown(
        f"<div style='padding:6px 0 2px 0'>"
        f"<div style='font-size:1.25rem;font-weight:800;color:#0A4C86'>📈 {APP_NAME}</div>"
        f"<div style='font-size:.78rem;color:#5C6470'>{APP_TAGLINE}</div></div>",
        unsafe_allow_html=True)
    st.sidebar.divider()

    # Active dataset + as-of control
    src = "Sample dataset" if ctx.is_sample else ctx.filename
    st.sidebar.markdown(f"**Dataset:** {src}  \n**Rows:** {len(ctx.fact):,}")
    lo = pd.Timestamp(ctx.as_of).date()
    new_asof = st.sidebar.date_input("Reporting as-of date", value=lo,
                                     help="Anchors This-Week/Month/Quarter/YTD windows.")
    if pd.Timestamp(new_asof) != pd.Timestamp(ctx.as_of):
        state.reload_with(as_of=pd.Timestamp(new_asof))
        st.rerun()
    st.sidebar.divider()


def main() -> None:
    inject_css()
    ctx = state.ensure_context()
    _sidebar_brand(ctx)

    nav = st.navigation({
        "Executive": [
            st.Page(overview.render, title="Overview", icon=":material/dashboard:", default=True),
            st.Page(insights_page.render, title="Insights & Export", icon=":material/lightbulb:"),
        ],
        "Status Reports": [
            st.Page(accounts_status.render, title="Accounts by Migration Status",
                    icon=":material/donut_large:"),
            st.Page(approved.render, title="Nominations Approved", icon=":material/task_alt:"),
            st.Page(closed.render, title="Nominations Closed", icon=":material/check_circle:"),
            st.Page(eos_status.render, title="AV36 EOS Status", icon=":material/warning:"),
        ],
        "Trend Analysis": [
            st.Page(nomination_trends.render, title="Nomination Trends", icon=":material/timeline:"),
            st.Page(approved_trends.render, title="Approved Trend Analysis",
                    icon=":material/trending_up:"),
            st.Page(avs_to_azure.render, title="AVS → Azure Native", icon=":material/swap_horiz:"),
        ],
        "Data": [
            st.Page(data_upload.render, title="Data & Upload", icon=":material/upload_file:"),
            st.Page(column_mapping.render, title="Column Mapping", icon=":material/table_chart:"),
        ],
    })

    nav.run()
    st.sidebar.divider()
    st.sidebar.caption(f"v{APP_VERSION} · Runs locally · No data leaves this machine")


main()
