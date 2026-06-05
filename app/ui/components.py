"""Reusable Streamlit UI components shared across report pages."""
from __future__ import annotations

import html

import pandas as pd
import streamlit as st

from ..core import analytics, schema
from ..core.metrics import fmt_int
from ..state import DataContext
from .theme import banner


# --------------------------------------------------------------------------- #
# KPI cards
# --------------------------------------------------------------------------- #
def kpi_row(items: list[dict]) -> None:
    """Render a row of KPI cards.

    Each item: {label, value, delta?(float pct), tone?('','good','warn','bad'),
    delta_label?}.
    """
    cards = []
    for it in items:
        tone = it.get("tone", "")
        delta_html = ""
        d = it.get("delta")
        if d is not None:
            cls = "up" if d > 0 else ("down" if d < 0 else "flat")
            arrow = "▲" if d > 0 else ("▼" if d < 0 else "■")
            lbl = it.get("delta_label", "vs prior")
            delta_html = f'<div class="delta {cls}">{arrow} {abs(d):.0f}% {lbl}</div>'
        elif it.get("sub"):
            delta_html = f'<div class="delta flat">{html.escape(str(it["sub"]))}</div>'
        cards.append(
            f'<div class="kpi {tone}"><div class="label">{html.escape(str(it["label"]))}</div>'
            f'<div class="value">{html.escape(str(it["value"]))}</div>{delta_html}</div>')
    st.markdown(f'<div class="kpi-grid">{"".join(cards)}</div>', unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
# Insight cards
# --------------------------------------------------------------------------- #
def insight_cards(insights, columns: int = 2) -> None:
    cols = st.columns(columns)
    for i, ins in enumerate(insights):
        with cols[i % columns]:
            metric = f'<span style="float:right;font-weight:700;color:var(--primary-dark)">{html.escape(str(ins.metric))}</span>' if ins.metric else ""
            st.markdown(
                f'<div class="insight {ins.severity}"><div class="cat">{html.escape(ins.category)}</div>'
                f'<div class="title">{html.escape(ins.title)}{metric}</div>'
                f'<div class="detail">{ins.detail}</div></div>',
                unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
# Data-quality banner
# --------------------------------------------------------------------------- #
def data_quality_banner(ctx: DataContext) -> None:
    rep = ctx.report
    dq_rows = rep.get("dq_rows", 0)
    if ctx.is_sample:
        banner("📊 Showing the bundled <b>sample dataset</b>. Use "
               "<b>Data &amp; Upload</b> in the sidebar to load your own file.", "info")
    if dq_rows:
        parts = ", ".join(f"{k.replace('_',' ')}: {v}" for k, v in rep.get("dq", {}).items())
        banner(f"⚠️ <b>{dq_rows}</b> row(s) have data-quality issues "
               f"({parts}). See the <b>Insights</b> page for details.", "warn")


# --------------------------------------------------------------------------- #
# Filter sidebar
# --------------------------------------------------------------------------- #
_FILTER_LABELS = {f.key: f.label for f in schema.CANONICAL_FIELDS}


def filter_sidebar(ctx: DataContext, fields: list[str], date_field: str | None = "created_date",
                   key_prefix: str = "f", table: str = "fact") -> tuple[dict, str]:
    """Render filter widgets in the sidebar; return (filters_dict, where_clause).

    ``fields`` are canonical categorical keys to expose as multiselects.
    ``date_field`` (if given) adds a date-range filter on that column.
    ``table`` selects the counting grain (``fact`` or ``customer``).
    """
    filters: dict = {}
    con = ctx.con
    frame = ctx.customer if table == "customer" else ctx.fact
    st.sidebar.markdown("### 🔎 Filters")

    for key in fields:
        if key not in frame.columns:
            continue
        opts = analytics.distinct_values(con, key, table=table)
        if not opts:
            continue
        sel = st.sidebar.multiselect(_FILTER_LABELS.get(key, key), opts,
                                     key=f"{key_prefix}_{key}")
        if sel:
            filters[key] = sel

    if date_field and date_field in frame.columns:
        lo, hi = analytics.date_bounds(con, date_field, table=table)
        if lo is not None and hi is not None:
            lo, hi = pd.Timestamp(lo).date(), pd.Timestamp(hi).date()
            label = _FILTER_LABELS.get(date_field, date_field) + " range"
            rng = st.sidebar.date_input(label, value=(lo, hi), min_value=lo, max_value=hi,
                                        key=f"{key_prefix}_date_{date_field}")
            if isinstance(rng, (tuple, list)) and len(rng) == 2:
                filters["_date"] = {"col": date_field, "start": rng[0], "end": rng[1]}

    n = analytics.total_rows(con, analytics.build_where(filters), table=table)
    unit = "accounts" if table == "customer" else "nominations"
    st.sidebar.caption(f"**{fmt_int(n)}** of {fmt_int(len(frame))} {unit} in view")
    if st.sidebar.button("Reset filters", width="stretch", key=f"{key_prefix}_reset"):
        for k in list(st.session_state.keys()):
            if k.startswith(key_prefix + "_"):
                del st.session_state[k]
        st.rerun()

    return filters, analytics.build_where(filters)


# --------------------------------------------------------------------------- #
# Styled dataframe
# --------------------------------------------------------------------------- #
_NICE = {f.key: f.label for f in schema.CANONICAL_FIELDS}
_NICE.update({
    "eos_status": "EOS Status", "migration_direction": "Direction", "azure_target": "Azure Target",
    "aging_days": "Age (days)", "cycle_time_days": "Cycle Time (days)",
    "migration_status_label": "Migration Status", "dq_flags": "Data Quality Notes",
    "approval_latency_days": "Approval Latency (days)", "is_open": "Open", "is_closed": "Closed",
})


def show_table(df: pd.DataFrame, height: int | None = None, hide_index: bool = True) -> None:
    disp = df.rename(columns={c: _NICE.get(c, c.replace("_", " ").title()) for c in df.columns})
    kwargs = {"width": "stretch", "hide_index": hide_index}
    if height is not None:
        kwargs["height"] = height
    st.dataframe(disp, **kwargs)


def empty_state(msg: str = "No records match the current filters.") -> None:
    st.info(msg)


def banner_note(text: str) -> None:
    """Small informational banner (used for mode-specific hints)."""
    banner(text)


# --------------------------------------------------------------------------- #
# Period KPI row (WTD / MTD / QTD / YTD)
# --------------------------------------------------------------------------- #
def period_kpi_row(dates: pd.Series, as_of, verb: str = "") -> None:
    """Render This-Week/Month/Quarter/YTD counts with vs-prior deltas."""
    from ..core import metrics
    counts = metrics.count_in_periods(dates, as_of)
    defs = [("week", "This Week"), ("month", "This Month"),
            ("quarter", "This Quarter"), ("ytd", "Year-to-Date")]
    items = []
    for key, label in defs:
        cur = counts[key]
        prior = metrics.prior_equivalent_count(dates, as_of, key)
        delta = metrics.pct_delta(cur, prior)
        items.append({"label": f"{verb} {label}".strip(), "value": fmt_int(cur),
                      "delta": delta, "delta_label": "vs prior"})
    kpi_row(items)
