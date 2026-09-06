"""Trend Analysis — one measure at a time, across every migration category.

The Status Report pages used to carry a four-measure "Trends — month
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
from app.config import FY_START_MONTH, REPORTING_FLOOR_FY
from app.core import glossary, kpi, metrics, segments
from app.core.metrics import fmt_currency, fmt_int
from app.ui import charts, components, drilldown
from app.ui.theme import banner, page_header, section

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

    floor = (ctx.report.get("scope") or {}).get("floor_fy", "the reporting floor")
    names = " · ".join(segments.CATEGORY_LABELS[c] for c in measure.categories)
    banner(f"Reporting range: <b>All time ({floor} onwards)</b> — the whole "
           f"dataset. Categories: <b>{names}</b>.")

    date_col = "approval_date"
    if measure.basis_toggle:
        basis = st.radio(
            "Trend basis", ["Nomination approval date", "Nomination created date"],
            horizontal=True, key=f"ta_{measure.key}_basis",
            help="Which Wave-1 date places a TPID in a month. Applies to every "
                 "category below.")
        date_col = ("approval_date" if basis.startswith("Nomination approval")
                    else "created_date")

    st.caption("Each fiscal year is its own line over a shared Jul → Jun axis, so "
               "the years read against one another, and the table beside the chart "
               "lays the same numbers out side by side. Click a point to narrow the "
               "records below to that month.")

    for category in measure.categories:
        _category_block(ctx, measure, category, date_col, reporting_floor(ctx))


def reporting_floor(ctx) -> pd.Timestamp:
    """The first day of the earliest fiscal year any trend may chart."""
    scope = ctx.report.get("scope") or {}
    start = scope.get("floor_start")
    return (pd.Timestamp(start) if start is not None
            else metrics.named_fiscal_year_start(REPORTING_FLOOR_FY, FY_START_MONTH))


def _category_block(ctx, measure: Measure, category: str, date_col: str,
                    floor_start: pd.Timestamp) -> None:
    """One category's trend for this measure, with the records behind it.

    Windowed from the reporting floor to the end of the data — "all time" means
    FY25 onwards, and every measure is bounded by *its own* date column.  The
    ingest floor alone is not enough here: it drops waves by nomination date,
    but a wave approved inside FY25 can still carry an earlier *created* date,
    which would put an FY24 column on the nomination trend.
    """
    label = segments.CATEGORY_LABELS[category]
    key = f"ta_{measure.key}_{category}"
    section(label, help=glossary.CATEGORY_HELP.get(category),
            period="All time — every fiscal year in the dataset")

    fact = segments.population(ctx.fact, category)
    if fact.empty:
        components.empty_state(f"No nominations fall into **{label}**.")
        return
    waves = kpi.wave_index(fact)
    table, rows = measure.series(fact, waves, floor_start, None, date_col)
    if table.empty:
        components.empty_state(f"No {measure.what} in this category.")
        return

    split = kpi.split_by_fiscal_year(table, measure.value_col, FY_START_MONTH)
    if split.empty:
        components.empty_state(f"No {measure.what} to chart.")
        return

    tpids = fmt_int(segments.tpid_key(fact).nunique())
    st.caption(f"**{tpids}** accounts (TPIDs) · **{fmt_int(len(fact))}** nomination "
               f"waves in this category.")

    years = sorted(split["fy"].unique())
    order = metrics.fiscal_month_order(FY_START_MONTH)
    fig = charts.fy_lines(split, "fy_month", "fy", measure.value_col, order,
                          currency=measure.currency, height=340)

    left, right = st.columns([3, 2])
    with left:
        picked = drilldown.selectable_chart(fig, key=key, curve_labels=years)
    with right:
        st.caption("Fiscal years side by side")
        components.show_table(_fy_grid(split, measure, order))

    _records_by_fiscal_year(rows, measure, key, picked)
    st.write("")


def _fy_grid(split: pd.DataFrame, measure: Measure, order: list[str]) -> pd.DataFrame:
    """Month rows, fiscal-year columns, and a Total row summing each year.

    The table beside the chart, rather than an expander below it: reading FY25
    against FY26 for a given month is the question these reports exist to answer,
    and a long-form (Period, FY, Month, value) list buries it.
    """
    grid = split.pivot_table(index="fy_month", columns="fy",
                             values=measure.value_col, aggfunc="sum")
    grid = grid.reindex([m for m in order if m in grid.index]).fillna(0)
    grid.loc["Total"] = grid.sum()
    out = grid.reset_index().rename(columns={"fy_month": "Month"})
    out.columns.name = None
    money = measure.currency
    for col in out.columns[1:]:
        out[col] = out[col].map(fmt_currency if money else fmt_int)
    return out


def _records_by_fiscal_year(rows: pd.DataFrame, measure: Measure, key: str,
                            picked: list[str]) -> None:
    """The records behind the chart, one table per fiscal year.

    Never one combined table: a row's fiscal year is the thing being compared
    here, so mixing the years back together in the drill-down would undo the
    split the chart just made.
    """
    labelled = kpi.label_fiscal_year(rows, measure.row_date, FY_START_MONTH)
    if labelled is None or labelled.empty:
        st.caption(f"No {measure.what} to list.")
        return
    if picked:
        wanted = {drilldown.normalize_bucket(v) for v in picked}
        labelled = labelled[labelled["bucket"].map(drilldown.normalize_bucket)
                            .isin(wanted)]
        st.caption(f"Showing **{', '.join(str(v) for v in picked)}** — "
                   "click the point again to clear.")
    else:
        st.caption(f"Underlying {measure.what}, one table per fiscal year. Click a "
                   "point on the chart to narrow them to a single month.")
    if labelled.empty:
        st.info("No records for this selection.")
        return

    for fy in sorted(y for y in labelled["fy"].unique() if y):
        block = labelled[labelled["fy"] == fy]
        frame = kpi.drilldown_frame(block)
        with st.expander(f"🔎 Underlying {measure.what} — {fy} "
                         f"({fmt_int(len(frame))} rows)", expanded=bool(picked)):
            if measure.unit_col and measure.unit_col in block.columns:
                total = pd.to_numeric(block[measure.unit_col], errors="coerce").sum()
                st.caption(f"{fy} total: **"
                           f"{fmt_currency(total) if measure.currency else fmt_int(total)}"
                           f"**")
            components.show_table(frame, height=320)
            st.download_button(
                "⬇️ Export to CSV", frame.to_csv(index=False).encode("utf-8"),
                file_name=f"{key}-{fy}.csv", mime="text/csv",
                key=f"{key}_{fy}_csv")


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
