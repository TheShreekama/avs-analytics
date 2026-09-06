"""Reusable Streamlit UI components shared across report pages."""
from __future__ import annotations

import html
import re

import pandas as pd
import streamlit as st

from ..config import (DATE_PRESETS, DEFAULT_DATE_PRESET, FY_START_MONTH,
                      GLOBAL_DATE_PRESETS)
from ..core import analytics, metrics, schema
from ..core.metrics import fmt_currency, fmt_int
from ..state import DataContext
from .theme import banner, info_mark as banner_info

# Render **bold** spans (markdown) inside HTML insight cards as <b> tags.
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")


def _md_bold(text: str) -> str:
    return _BOLD_RE.sub(r"<b>\1</b>", str(text))


# --------------------------------------------------------------------------- #
# KPI cards
# --------------------------------------------------------------------------- #
def kpi_row(items: list[dict]) -> None:
    """Render a row of KPI cards.

    Each item: {label, value, delta?(float pct), tone?('','good','warn','bad'),
    delta_label?, help?}.  ``help`` renders an ⓘ whose hover text explains how the
    number is calculated.
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
            f'<div class="kpi {tone}"><div class="label">{html.escape(str(it["label"]))}'
            f'{banner_info(it.get("help"))}</div>'
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
                f'<div class="detail">{_md_bold(ins.detail)}</div></div>',
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
        _bad_date_samples(rep)


def _bad_date_samples(rep: dict) -> None:
    """Show the actual values behind a "bad date" count, so the format is visible."""
    samples = rep.get("dq_samples", {}).get("bad_date") or []
    if not samples:
        return
    with st.expander("Which date values could not be read?"):
        for label, count, values in samples:
            shown = ", ".join(f"`{v}`" for v in values) or "—"
            st.markdown(f"**{label}** — {fmt_int(count)} row(s), e.g. {shown}")
        st.caption("Excel serial numbers, ISO stamps, month names and day-first or "
                   "month-first values are all read automatically. If a value above "
                   "still looks like a date, it is a format worth adding.")


# --------------------------------------------------------------------------- #
# Filter sidebar
# --------------------------------------------------------------------------- #
_FILTER_LABELS = {f.key: f.label for f in schema.CANONICAL_FIELDS}
_FILTER_LABELS.update({"region_geo": "Region", "migration_direction": "Direction",
                       "azure_target": "Azure Target", "eos_status": "Operational Status",
                       "migration_status_label": "Migration Status"})


def filter_sidebar(ctx: DataContext, fields: list[str], date_field: str | None = None,
                   key_prefix: str = "f", table: str = "fact",
                   scope: str | None = None,
                   date_filter: dict | None = None) -> tuple[dict, str]:
    """Render filter widgets in the sidebar; return (filters_dict, where_clause).

    ``fields`` are categorical column keys to expose as multiselects.
    ``date_filter`` is the reporting window chosen *on the page* by
    :func:`page_date_filter` — the date control lives with the report it dates,
    not in the sidebar, so there is one place to change a period rather than two.
    ``table`` selects the counting grain (``fact`` or ``customer``).
    ``scope`` (``primary`` | ``from_avs`` | ``None``) restricts every query — and
    the filter option lists — to that reporting scope, so "(From AVS)" offerings
    never leak into the primary reports (and vice-versa).
    """
    filters: dict = {}
    con = ctx.con
    frame = ctx.customer if table == "customer" else ctx.fact
    scope_where = analytics.apply_scope("", scope)
    st.sidebar.markdown("### 🔎 Filters")

    for key in fields:
        if key not in frame.columns:
            continue
        opts = analytics.distinct_values(con, key, table=table, where=scope_where)
        if not opts:
            continue
        sel = st.sidebar.multiselect(_FILTER_LABELS.get(key, key.replace("_", " ").title()),
                                     opts, key=f"{key_prefix}_{key}")
        if sel:
            filters[key] = sel

    if date_filter and date_filter.get("col") in frame.columns:
        filters["_date"] = date_filter

    where = analytics.apply_scope(analytics.build_where(filters), scope)
    n = analytics.total_rows(con, where, table=table)
    base_n = analytics.total_rows(con, scope_where, table=table)
    unit = "accounts" if table == "customer" else "nominations"
    st.sidebar.caption(f"**{fmt_int(n)}** of {fmt_int(base_n)} {unit} in view")

    _record_diagnostics(ctx, filters, scope_where, table, n, base_n, unit)
    if n == 0 and base_n:
        _empty_selection_help(filters, key_prefix)

    if st.sidebar.button("Reset filters", width="stretch", key=f"{key_prefix}_reset"):
        _clear_filter_state(key_prefix)
        st.rerun()

    return filters, where


# --------------------------------------------------------------------------- #
# Why-is-this-empty diagnostics
# --------------------------------------------------------------------------- #
# ``filter_sidebar`` stashes what the active filters removed so that a page's
# ``empty_state`` can tell the user *which* filter emptied the report (almost
# always the date window) instead of a bare "no records match".
_DIAG_KEY = "_avs_filter_diag"


def _clear_filter_state(key_prefix: str) -> None:
    for k in list(st.session_state.keys()):
        if k.startswith(key_prefix + "_"):
            del st.session_state[k]


def _record_diagnostics(ctx: DataContext, filters: dict, scope_where: str, table: str,
                        n: int, base_n: int, unit: str) -> None:
    """Measure each filter group's contribution and stash it for ``empty_state``."""
    con = ctx.con
    cats = {k: v for k, v in filters.items() if not k.startswith("_")}
    date_f = filters.get("_date")

    # Everything the user picked *except* the date window, so we can attribute
    # an empty result to the date range vs. the categorical selections.
    scope_pred = scope_where.replace("WHERE ", "", 1) if scope_where else ""
    cats_only = analytics._where_and(analytics.build_where(cats), scope_pred)
    n_cats_only = analytics.total_rows(con, cats_only, table=table)

    n_missing_date = 0
    if date_f and date_f.get("col"):
        col = date_f["col"]
        n_missing_date = analytics.total_rows(
            con, analytics._where_and(cats_only, f'"{col}" IS NULL'), table=table)

    st.session_state[_DIAG_KEY] = {
        "unit": unit, "n": n, "base_n": base_n,
        "n_cats_only": n_cats_only, "n_missing_date": n_missing_date,
        "date": dict(date_f) if date_f else None,
        "date_label": _FILTER_LABELS.get(date_f["col"], date_f["col"].replace("_", " ").title())
        if date_f else "",
        "categories": {_FILTER_LABELS.get(k, k.replace("_", " ").title()): list(v)
                       for k, v in cats.items()},
    }


def _empty_selection_help(filters: dict, key_prefix: str) -> None:
    """Sidebar warning when the current selection is empty."""
    diag = st.session_state.get(_DIAG_KEY, {})
    st.sidebar.warning(f"No {diag.get('unit', 'records')} match these filters.")
    if filters.get("_date") and diag.get("n_cats_only"):
        st.sidebar.caption("Widen the **reporting period** at the top of the page, or "
                           "clear the filters below.")


def page_date_filter(ctx: DataContext, key_prefix: str, date_field: str,
                     label: str | None = None, table: str = "fact",
                     scope: str | None = None, columns=None) -> dict | None:
    """The report's reporting-period control, rendered on the page.

    Follows the global sidebar window unless overridden here, and offers to keep
    records whose date is missing (a range filter drops them otherwise).  Returns
    a ``_date`` filter for :func:`filter_sidebar` / ``analytics.build_where``, or
    ``None`` when the window is unbounded.
    """
    from ..core import glossary
    label = label or _FILTER_LABELS.get(date_field, date_field.replace("_", " ").title())
    left, right = st.columns(columns or [2, 3])
    with left:
        start, end, _shown, _preset = report_date_range(
            ctx, key_prefix, f"{label} — reporting period")
    if start is None:
        with right:
            st.caption(glossary.REPORTING_PERIOD.split("\n")[0])
        return None

    include_null = False
    scope_where = analytics.apply_scope("", scope)
    missing = analytics.total_rows(
        ctx.con, analytics._where_and(scope_where, f'"{date_field}" IS NULL'), table=table)
    with right:
        if missing:
            include_null = st.checkbox(
                f"Include {fmt_int(missing)} with no {label.lower()}",
                key=f"{key_prefix}_nulls_{date_field}",
                help="A date range excludes records whose date is blank.")
    return {"col": date_field, "start": start, "end": end, "include_null": include_null}


# --------------------------------------------------------------------------- #
# Styled dataframe
# --------------------------------------------------------------------------- #
_NICE = {f.key: f.label for f in schema.CANONICAL_FIELDS}
_NICE.update({
    "eos_status": "Operational Status", "migration_direction": "Direction",
    "azure_target": "Azure Target",
    "aging_days": "Age (days)", "cycle_time_days": "Cycle Time (days)",
    "migration_status_label": "Migration Status", "dq_flags": "Data Quality Notes",
    "approval_latency_days": "Approval Latency (days)", "is_open": "Open", "is_closed": "Closed",
    "region_geo": "Region", "migration_path": "Migration Path (offering)",
})


#: Columns holding money.  Every table renders these as $1.2M / $840.0K rather
#: than a raw number — a rule applied here so no caller can forget it.
_MONEY_COLUMNS = {"total_acr", "acr", "acr_claimed", "total acr", "acr claimed",
                  "estimated_acr", "estimated acr"}


def _is_money(column: str) -> bool:
    return str(column).strip().lower() in _MONEY_COLUMNS


def format_money(df: pd.DataFrame) -> pd.DataFrame:
    """A copy of ``df`` with its money columns rendered as currency."""
    money = [c for c in df.columns if _is_money(c) and
             pd.api.types.is_numeric_dtype(df[c])]
    if not money:
        return df
    out = df.copy()
    for col in money:
        out[col] = out[col].map(fmt_currency)
    return out


def show_table(df: pd.DataFrame, height: int | None = None, hide_index: bool = True) -> None:
    disp = format_money(df)
    disp = disp.rename(columns={c: _NICE.get(c, c.replace("_", " ").title())
                                for c in disp.columns})
    kwargs = {"width": "stretch", "hide_index": hide_index}
    if height is not None:
        kwargs["height"] = height
    st.dataframe(disp, **kwargs)


def empty_state(msg: str = "No records match the current filters.") -> None:
    """Empty-result notice, explaining *which* filter emptied the report."""
    st.info(msg)
    hint = _empty_state_hint()
    if hint:
        st.caption(hint)


def _empty_state_hint() -> str:
    """Human explanation of the active filters, from the last sidebar render."""
    diag = st.session_state.get(_DIAG_KEY)
    if not diag or not diag.get("base_n"):
        return ""
    unit = diag["unit"]
    bits: list[str] = []
    date_f = diag.get("date")
    if date_f and date_f.get("start") is not None:
        start, end = date_f["start"], date_f["end"]
        bits.append(f"📅 **{diag['date_label']}** between **{start:%d %b %Y}** and "
                    f"**{end:%d %b %Y}** — only {fmt_int(diag['n'])} of "
                    f"{fmt_int(diag['n_cats_only'])} {unit} fall inside it"
                    + (f" ({fmt_int(diag['n_missing_date'])} have no "
                       f"{diag['date_label'].lower()} at all)"
                       if diag.get("n_missing_date") else ""))
    if diag.get("categories"):
        picked = "; ".join(f"**{k}**: {', '.join(str(x) for x in v)}"
                           for k, v in diag["categories"].items())
        bits.append(f"🔎 {picked}")
    if not bits:
        return ""
    return (" · ".join(bits)
            + f"  —  widen the range or press **Reset filters** in the sidebar to see all "
              f"{fmt_int(diag['base_n'])} {unit}.")


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


# --------------------------------------------------------------------------- #
# Date range: one global window, overridable per report
# --------------------------------------------------------------------------- #
GLOBAL_DATE_KEY = "global_date_preset"
GLOBAL_CUSTOM_KEY = "global_date_custom"
USE_GLOBAL = "Global range"


def global_date_controls(ctx: DataContext) -> None:
    """The application-wide reporting window, rendered once in the sidebar.

    Every report follows this window unless it overrides it with its own
    selector, so a single change re-dates the whole dashboard.
    """
    st.sidebar.markdown("### 📅 Reporting period")
    preset = st.sidebar.selectbox(
        "Date range", GLOBAL_DATE_PRESETS,
        index=GLOBAL_DATE_PRESETS.index(DEFAULT_DATE_PRESET), key=GLOBAL_DATE_KEY,
        help="Applies to every report. Individual reports can override it.")
    if preset == "Custom":
        lo, hi = analytics.date_bounds(ctx.con, "created_date")
        if lo is not None and hi is not None:
            lo, hi = pd.Timestamp(lo).date(), pd.Timestamp(hi).date()
            st.sidebar.date_input("Custom range", value=(lo, hi), min_value=lo, max_value=hi,
                                  key=GLOBAL_CUSTOM_KEY)
    start, end = resolve_range(ctx, preset, st.session_state.get(GLOBAL_CUSTOM_KEY))
    if start is not None:
        st.sidebar.caption(f"{start:%d %b %Y} → {end:%d %b %Y}")
    else:
        st.sidebar.caption("All dates in the dataset")


def resolve_range(ctx: DataContext, preset: str, custom=None):
    """Turn a preset name into a concrete (start, end) pair, or (None, None)."""
    if preset == "Custom":
        if isinstance(custom, (tuple, list)) and len(custom) == 2:
            return custom[0], custom[1]
        return None, None
    if preset == "All time":
        return None, None
    rng = metrics.date_preset_range(ctx.as_of, preset, FY_START_MONTH)
    return (rng[0].date(), rng[1].date()) if rng else (None, None)


def global_range(ctx: DataContext):
    preset = st.session_state.get(GLOBAL_DATE_KEY, DEFAULT_DATE_PRESET)
    return resolve_range(ctx, preset, st.session_state.get(GLOBAL_CUSTOM_KEY))


def report_date_range(ctx: DataContext, key_prefix: str, label: str = "Reporting period"):
    """Per-report date selector that defaults to the global window.

    Returns ``(start, end, description, preset)`` — dates are inclusive and
    ``None`` means unbounded.  ``description`` is for display ("This FY
    (global)"); ``preset`` is the resolved preset name on its own, which is what
    a report tests against to decide how to behave ("All time" splits its trends
    by fiscal year, anything but "This FY" gains a This-FY comparison row).
    """
    from ..core import glossary
    options = [USE_GLOBAL] + list(DATE_PRESETS)
    choice = st.selectbox(label, options, index=0, key=f"{key_prefix}_range",
                          help=glossary.REPORTING_PERIOD)
    if choice == USE_GLOBAL:
        preset = st.session_state.get(GLOBAL_DATE_KEY, DEFAULT_DATE_PRESET)
        start, end = global_range(ctx)
        shown = f"{preset} (global)"
    else:
        preset = choice
        custom = None
        if choice == "Custom":
            lo, hi = analytics.date_bounds(ctx.con, "created_date")
            if lo is not None and hi is not None:
                lo, hi = pd.Timestamp(lo).date(), pd.Timestamp(hi).date()
                custom = st.date_input("Custom range", value=(lo, hi), min_value=lo,
                                       max_value=hi, key=f"{key_prefix}_custom")
        start, end = resolve_range(ctx, choice, custom)
        shown = choice
    window = (f"{start:%d %b %Y} → {end:%d %b %Y}" if start is not None
              else "all dates in the dataset")
    st.caption(f"**{shown}** — {window}")
    return start, end, shown, preset


# --------------------------------------------------------------------------- #
# Data consistency: generation tag vs. EOS migration path
# --------------------------------------------------------------------------- #
def consistency_summary(ctx: DataContext) -> None:
    """A one-line verdict on tag vs. EOS-path agreement, pointing at the report.

    The records themselves live on the **Data Inconsistency** page, which is the
    single place that lists them — this is only the "is there anything to look
    at" signal shown where a file is loaded.
    """
    from ..core import segments
    issues = segments.eos_consistency(ctx.fact)
    total = sum(len(df) for df in issues.values())
    if not total:
        st.success("✅ Generation tags and EOS migration paths agree throughout.")
        return
    accounts = sum(int(df["tpid"].nunique()) if "tpid" in df.columns else len(df)
                   for df in issues.values())
    st.warning(f"{fmt_int(total)} row(s) across {fmt_int(accounts)} account(s) where "
               f"the generation tag and the EOS migration path disagree.")
    st.caption("Open **Data → Data Inconsistency** for the records, the reason each "
               "one is flagged, and a CSV export.")
