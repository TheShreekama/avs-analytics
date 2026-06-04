"""Executive theming: CSS injection and KPI-card rendering.

Keeps the look corporate and print-friendly — soft cards, restrained palette,
hidden Streamlit chrome — so it reads as a leadership dashboard, not a dev tool.
"""
from __future__ import annotations

import streamlit as st

from ..config import APP_NAME, PALETTE


def inject_css() -> None:
    st.markdown(
        f"""
        <style>
        :root {{
            --primary: {PALETTE['primary']};
            --primary-dark: {PALETTE['primary_dark']};
            --ink: {PALETTE['ink']};
            --muted: {PALETTE['muted']};
            --card: {PALETTE['card']};
            --border: {PALETTE['border']};
            --good: {PALETTE['good']};
            --warn: {PALETTE['warn']};
            --bad: {PALETTE['bad']};
        }}
        /* Page background + base font */
        .stApp {{ background: {PALETTE['bg']}; }}
        html, body, [class*="css"] {{
            font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif;
            color: var(--ink);
        }}
        /* Hide default chrome for an app-like feel */
        #MainMenu, header[data-testid="stHeader"], footer {{ visibility: hidden; }}
        .block-container {{ padding-top: 1.4rem; padding-bottom: 2rem; max-width: 1500px; }}

        /* Section heading */
        .avs-h1 {{ font-size: 1.7rem; font-weight: 700; color: var(--ink); margin: 0; }}
        .avs-sub {{ color: var(--muted); font-size: .95rem; margin-top: .1rem; margin-bottom: .6rem; }}
        .avs-section {{ font-size: 1.15rem; font-weight:700; color: var(--primary-dark);
            margin: 1.1rem 0 .4rem 0; padding-bottom:.3rem; border-bottom: 2px solid var(--border); }}

        /* KPI cards */
        .kpi-grid {{ display:flex; gap: 14px; flex-wrap: wrap; }}
        .kpi {{ background: var(--card); border:1px solid var(--border); border-radius: 12px;
            padding: 16px 18px; flex: 1; min-width: 150px;
            box-shadow: 0 1px 3px rgba(16,24,40,.06); border-top: 3px solid var(--primary); }}
        .kpi .label {{ font-size:.78rem; color: var(--muted); text-transform: uppercase;
            letter-spacing:.04em; font-weight:600; }}
        .kpi .value {{ font-size: 1.9rem; font-weight: 700; color: var(--ink); line-height:1.1; margin-top:4px; }}
        .kpi .delta {{ font-size:.8rem; font-weight:600; margin-top:2px; }}
        .kpi .delta.up {{ color: var(--good); }}
        .kpi .delta.down {{ color: var(--bad); }}
        .kpi .delta.flat {{ color: var(--muted); }}
        .kpi.good {{ border-top-color: var(--good); }}
        .kpi.warn {{ border-top-color: var(--warn); }}
        .kpi.bad {{ border-top-color: var(--bad); }}

        /* Insight cards */
        .insight {{ background: var(--card); border:1px solid var(--border);
            border-left: 4px solid var(--primary); border-radius: 8px; padding: 12px 14px;
            margin-bottom: 10px; box-shadow: 0 1px 2px rgba(16,24,40,.05); }}
        .insight.positive {{ border-left-color: var(--good); }}
        .insight.warning  {{ border-left-color: var(--warn); }}
        .insight.critical {{ border-left-color: var(--bad); }}
        .insight .title {{ font-weight: 700; font-size: .98rem; }}
        .insight .cat {{ font-size:.72rem; text-transform:uppercase; letter-spacing:.04em;
            color: var(--muted); font-weight:600; }}
        .insight .detail {{ color: #353A40; font-size:.9rem; margin-top:3px; }}

        /* Banner */
        .avs-banner {{ background: #EAF3FB; border:1px solid #BFDCF3; color: var(--primary-dark);
            border-radius:8px; padding:10px 14px; font-size:.9rem; margin-bottom: 10px; }}
        .avs-banner.warn {{ background:#FDF3E7; border-color:#F2D2A0; color:#8A5300; }}

        /* Sidebar */
        section[data-testid="stSidebar"] {{ background: #FFFFFF; border-right: 1px solid var(--border); }}
        section[data-testid="stSidebar"] .stHeading {{ color: var(--primary-dark); }}

        /* Dataframe tweaks */
        [data-testid="stDataFrame"] {{ border:1px solid var(--border); border-radius: 10px; }}
        .stTabs [data-baseweb="tab-list"] {{ gap: 4px; }}
        .stTabs [data-baseweb="tab"] {{ font-weight:600; }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def page_header(title: str, subtitle: str = "") -> None:
    st.markdown(f'<div class="avs-h1">{title}</div>', unsafe_allow_html=True)
    if subtitle:
        st.markdown(f'<div class="avs-sub">{subtitle}</div>', unsafe_allow_html=True)


def section(title: str) -> None:
    st.markdown(f'<div class="avs-section">{title}</div>', unsafe_allow_html=True)


def banner(text: str, kind: str = "info") -> None:
    cls = "avs-banner warn" if kind == "warn" else "avs-banner"
    st.markdown(f'<div class="{cls}">{text}</div>', unsafe_allow_html=True)
