"""Trend Analysis — one measure at a time, across every migration category.

The Migration Analytics dashboards used to carry a four-measure "Trends — month
over month" section each, which meant reading one measure across categories
required opening five pages and comparing by memory.  These reports invert that:
one page per measure, every category on it, so nomination volume (or ACR, or
nodes) can be read across the portfolio in one place.

The measures are the same four the dashboards computed, from the same
:mod:`app.core.kpi` functions on the same populations — this is a move, not a
reimplementation, and the dashboards no longer carry the section.

Every chart keeps its drill-down: clicking a bar, a line point or a table row
opens the records behind that month.  Over "All time" each measure still splits
into one line per fiscal year over a shared Jul → Jun axis.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import pandas as pd
import streamlit as st

from app import state
from app.config import FY_START_MONTH
from app.core import glossary, kpi, metrics, segments
from app.core.metrics import fmt_currency, fmt_int
from app.ui import charts, components, drilldown
from app.ui.theme import banner, page_header, section

ALL_TIME = "All time"

#: Every category, in the order the reports list them.
_ALL_CATEGORIES = (segments.CAT_ALL_AVS, segments.CAT_EOS_ALL, segments.CAT_EOS_GEN1,
                   segments.CAT_EOS_GEN2, segments.CAT_AVS_NATIVE)
#: The AVS motions only — "(From AVS)" moves cores, and is reported separately.
_AVS_CATEGORIES = _ALL_CATEGORIES[:-1]


@dataclass(frozen=True)
class Measure:
    """One trend measure, and the categories it is reported for.

    ``series`` is the :mod:`app.core.kpi` call that produces the monthly table
    and the records behind it, so no calculation lives here.
    """
    key: str
    title: str
    blurb: str
    help: str
    series: Callable[..., tuple[pd.DataFrame, pd.DataFrame]]
    value_col: str
    display_col: str
    row_date: str
    unit_col: str | None
    currency: bool
    what: str
    categories: tuple[str, ...] = _ALL_CATEGORIES
    #: Nomination counts can be dated by Wave-1 approval or creation.
    basis_toggle: bool = False


MEASURES: tuple[Measure, ...] = (
    Measure(
        "nominations", "Nomination Trends",
        "Unique customers (TPIDs) nominated per month, in every migration "
        "category. Each TPID is counted once, in the month of its Wave-1 date.",
        glossary.TREND_NOMINATIONS,
        lambda fact, waves, start, end, date_col: kpi.monthly_unique_tpids(
            fact, date_col, start, end, firsts=waves.first),
        "Nominations", "Nominations", "approval_date", None, False, "nominations",
        basis_toggle=True),
    Measure(
        "acr", "ACR Trend",
        "ACR claimed per month, in every migration category — each wave's Total "
        "ACR placed in the month its Actual End Date falls in.",
        glossary.TREND_ACR,
        lambda fact, waves, start, end, date_col: kpi.monthly_acr_claimed(
            fact, start, end),
        "ACR Claimed", "ACR Claimed", "actual_end_date", "total_acr", True,
        "claiming waves"),
    Measure(
        "nodes", "Nodes Deployed",
        "Nodes deployed per month (the Total Cores column) over wave records "
        "that are '7 - Completed', dated by Actual End Date.",
        glossary.TREND_HOSTS,
        lambda fact, waves, start, end, date_col: kpi.monthly_hosts(fact, start, end),
        "Hosts", "Nodes", "actual_end_date", "total_cores", False, "wave records",
        categories=_AVS_CATEGORIES),
    Measure(
        "cores", "Cores Migrated",
        "Cores migrated per month to Azure-native services — the same Total "
        "Cores column the AVS motions report as nodes, under the noun that fits "
        "this motion.",
        glossary.TREND_CORES,
        lambda fact, waves, start, end, date_col: kpi.monthly_hosts(fact, start, end),
        "Hosts", "Cores", "actual_end_date", "total_cores", False, "wave records",
        categories=(segments.CAT_AVS_NATIVE,)),
    Measure(
        "completed", "Migrations Completed",
        "Completed migrations per month, in every migration category — unique "
        "TPIDs whose latest wave is '7 - Completed', dated by its Actual End Date.",
        glossary.TREND_COMPLETED,
        lambda fact, waves, start, end, date_col: kpi.monthly_migrations_completed(
            fact, start, end, lasts=waves.last),
        "Migrations Completed", "Migrations Completed", "actual_end_date", None,
        False, "completed migrations"),
)

_BY_KEY = {m.key: m for m in MEASURES}


# --------------------------------------------------------------------------- #
def render(measure_key: str) -> None:
    measure = _BY_KEY[measure_key]
    ctx = state.ensure_context()
    page_header(measure.title, measure.blurb, help=glossary.TRENDS)
    components.data_quality_banner(ctx)

    top = st.columns([2, 3])
    with top[0]:
        start, end, shown, preset = components.report_date_range(
            ctx, f"ta_{measure.key}")
    with top[1]:
        names = " · ".join(segments.CATEGORY_LABELS[c] for c in measure.categories)
        banner(f"One period, every category: <b>{names}</b>. Click a bar, a point "
               f"or a table row to open the records behind that month.")

    date_col = "approval_date"
    if measure.basis_toggle:
        basis = st.radio(
            "Trend basis", ["Nomination approval date", "Nomination created date"],
            horizontal=True, key=f"ta_{measure.key}_basis",
            help="Which Wave-1 date places a TPID in a month. Applies to every "
                 "category below.")
        date_col = ("approval_date" if basis.startswith("Nomination approval")
                    else "created_date")

    if preset == ALL_TIME:
        st.caption("**All time** — each fiscal year is its own line over a shared "
                   "Jul → Jun axis, so the years read against one another. There is "
                   "no Cumulative column in that view: a running total across "
                   "unrelated fiscal years would not mean anything.")

    for category in measure.categories:
        _category_block(ctx, measure, category, start, end, shown, preset, date_col)


def _category_block(ctx, measure: Measure, category: str, start, end, shown: str,
                    preset: str, date_col: str) -> None:
    """One category's trend for this measure, with its drill-down."""
    label = segments.CATEGORY_LABELS[category]
    key = f"ta_{measure.key}_{category}"
    section(label, help=glossary.CATEGORY_HELP.get(category), period=shown)

    fact = segments.population(ctx.fact, category)
    if fact.empty:
        components.empty_state(f"No nominations fall into **{label}**.")
        return
    waves = kpi.wave_index(fact)
    table, rows = measure.series(fact, waves, start, end, date_col)
    if table.empty:
        components.empty_state(f"No {measure.what} in the selected period.")
        return

    tpids = fmt_int(segments.tpid_key(fact).nunique())
    st.caption(f"**{tpids}** accounts (TPIDs) · **{fmt_int(len(fact))}** nomination "
               f"waves in this category.")

    if preset == ALL_TIME:
        _fy_trend(table, rows, measure, key)
    else:
        fig = charts.trend_chart(table, "period", measure.value_col, "Cumulative",
                                 currency=measure.currency, height=320)
        drilldown.chart_with_drilldown(
            fig, _with_period(rows, measure.row_date), "period", key=key,
            what=measure.what, unit_col=measure.unit_col,
            summary=_display_trend(table, measure.display_col, measure.currency),
            summary_bucket="Month")
    st.write("")


def _fy_trend(table: pd.DataFrame, rows: pd.DataFrame, measure: Measure,
              key: str) -> None:
    """One line per fiscal year, with the same click-through to the records.

    A month label alone is ambiguous here — every year has a September — so the
    chart, the summary table and the records are all keyed on "FY27 Sep", and the
    line a point sits on is what tells the two Septembers apart.  The
    year-over-year grid lives in the underlying-data panel, where it can be read
    side by side without breaking that key.
    """
    split = kpi.split_by_fiscal_year(table, measure.value_col, FY_START_MONTH)
    if split.empty:
        components.empty_state(f"No {measure.what} to chart.")
        return
    years = sorted(split["fy"].unique())
    order = metrics.fiscal_month_order(FY_START_MONTH)

    fig = charts.fy_lines(split, "fy_month", "fy", measure.value_col, order,
                          currency=measure.currency, height=340)
    summary = split.rename(columns={"bucket": "Period", "fy": "FY", "fy_month": "Month",
                                    measure.value_col: measure.display_col})
    summary = summary[["Period", "FY", "Month", measure.display_col]]
    if measure.currency:
        summary[measure.display_col] = summary[measure.display_col].map(fmt_currency)
    drilldown.chart_with_drilldown(
        fig, kpi.label_fiscal_year(rows, measure.row_date, FY_START_MONTH), "bucket",
        key=f"{key}_fy", what=measure.what, unit_col=measure.unit_col,
        summary=summary, summary_bucket="Period", curve_labels=years)

    grid = split.pivot_table(index="fy_month", columns="fy",
                             values=measure.value_col, aggfunc="sum")
    grid = grid.reindex([m for m in order if m in grid.index]).fillna(0)
    totals = split.groupby("fy")[measure.value_col].sum()
    st.caption("Totals per fiscal year: " + " · ".join(
        f"**{fy}** {fmt_currency(v) if measure.currency else fmt_int(v)}"
        for fy, v in totals.items()))
    display = grid.copy()
    if measure.currency:
        for col in display.columns:
            display[col] = display[col].map(fmt_currency)
    drilldown.data_expander(
        display.reset_index().rename(columns={"fy_month": "Month"}),
        f"{key}_fy_grid", label="Underlying data — fiscal years side by side",
        caption="The same numbers as the chart, one column per fiscal year.")


def _with_period(rows: pd.DataFrame, date_col: str) -> pd.DataFrame:
    """Attach the chart's period label to the underlying rows for drill-down."""
    if rows is None or rows.empty:
        return pd.DataFrame()
    out = rows.copy()
    if "month" in out.columns:
        out["period"] = pd.to_datetime(out["month"].astype(str), errors="coerce") \
            .dt.to_period("M").astype(str)
    elif date_col in out.columns:
        out["period"] = pd.to_datetime(out[date_col], errors="coerce") \
            .dt.to_period("M").astype(str)
    return out


def _display_trend(table: pd.DataFrame, display_col: str | None = None,
                   currency: bool = False) -> pd.DataFrame:
    """Month, value and the Cumulative column — cumulative always last.

    Money is shown as $1.2M / $840.0K rather than a raw number.
    """
    out = table.drop(columns=["month"]).rename(columns={"period": "Month"})
    value_cols = [c for c in out.columns if c not in ("Month", "Cumulative")]
    out = out[["Month", *value_cols, "Cumulative"]]
    if currency:
        for col in [*value_cols, "Cumulative"]:
            out[col] = out[col].map(fmt_currency)
    if display_col and value_cols and display_col != value_cols[0]:
        out = out.rename(columns={value_cols[0]: display_col})
    return out


# --------------------------------------------------------------------------- #
# Page entry points (st.Page needs a distinct callable per page)
# --------------------------------------------------------------------------- #
def nominations() -> None:
    render("nominations")


def acr() -> None:
    render("acr")


def nodes() -> None:
    render("nodes")


def cores() -> None:
    render("cores")


def completed() -> None:
    render("completed")
