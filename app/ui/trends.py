"""Month-over-month trends: defined once, drawn identically everywhere.

Four trends are reported for every migration category — nomination count, ACR
claimed, hosts/cores deployed and completed migrations — and they appear in two
places:

* the **category dashboard**, which draws all four for one category, and
* the **Trend Analysis** pages, which draw one trend for one category per page.

Both go through :func:`compute` and :func:`render_trend` below, so the number,
the chart, the summary table and the drill-down come from one piece of code
wherever they are shown.  A caller chooses the *heading* — "Nodes Deployed",
"Cores Migrated", "Hosts Migrated (Total Cores)" are the same measurement under
different nouns — and nothing else.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import streamlit as st

from ..config import FY_START_MONTH
from ..core import glossary, kpi, metrics
from ..core.metrics import fmt_currency, fmt_int
from . import charts, components, drilldown
from .theme import subheading

#: The trends, by name.  A view names the one it wants; the spec says the rest.
NOMINATIONS = "nominations"
ACR = "acr"
HOSTS = "hosts"
COMPLETED = "completed"

#: Order the category dashboard draws them in.
ALL_TRENDS = (NOMINATIONS, ACR, HOSTS, COMPLETED)


@dataclass(frozen=True)
class TrendSpec:
    """What a trend measures — independent of the category it is drawn for."""
    name: str
    value_col: str          #: column the monthly summary carries the value under
    row_date: str           #: record date that places a row in a month
    unit_col: str | None    #: column a drill-down totals underneath the records
    currency: bool          #: money, so formatted $1.2M rather than 1,200,000
    what: str               #: what one underlying record is ("claiming waves")
    help: str               #: the ⓘ explanation, from the glossary
    title: str              #: heading used when the caller has no better one


SPECS: dict[str, TrendSpec] = {
    NOMINATIONS: TrendSpec(
        NOMINATIONS, "Nominations", "approval_date", None, False,
        "nominations", glossary.TREND_NOMINATIONS,
        "Nomination count (unique TPIDs)"),
    ACR: TrendSpec(
        ACR, "ACR Claimed", "actual_end_date", "total_acr", True,
        "claiming waves", glossary.TREND_ACR, "ACR claimed"),
    HOSTS: TrendSpec(
        HOSTS, "Hosts", "actual_end_date", "total_cores", False,
        "wave records", glossary.TREND_HOSTS, "Hosts Migrated (Total Cores)"),
    COMPLETED: TrendSpec(
        COMPLETED, "Migrations Completed", "actual_end_date", None, False,
        "completed migrations", glossary.TREND_COMPLETED,
        "Migrations completed (unique TPIDs)"),
}


@dataclass(frozen=True)
class TrendResult:
    """A computed trend: the monthly summary plus the records behind it."""
    spec: TrendSpec
    table: pd.DataFrame     #: month, period, <value_col>, Cumulative
    rows: pd.DataFrame      #: the source records, for the drill-down
    row_date: str           #: the date column those records are bucketed on


# --------------------------------------------------------------------------- #
# Numbers
# --------------------------------------------------------------------------- #
def compute(name: str, fact: pd.DataFrame, waves: kpi.WaveIndex, start=None, end=None,
            *, date_col: str = "approval_date") -> TrendResult:
    """Run one trend over a population — the only place these numbers come from.

    ``date_col`` applies to the nomination count alone: it is the Wave-1 date
    that places a TPID in a month.  The other three are dated by Actual End
    Date, which is what they measure.
    """
    spec = SPECS[name]
    if name == NOMINATIONS:
        table, rows = kpi.monthly_unique_tpids(fact, date_col, start, end,
                                               firsts=waves.first)
        return TrendResult(spec, table, rows, date_col)
    if name == ACR:
        table, rows = kpi.monthly_acr_claimed(fact, start, end)
    elif name == HOSTS:
        table, rows = kpi.monthly_hosts(fact, start, end)
    else:
        table, rows = kpi.monthly_migrations_completed(fact, start, end, lasts=waves.last)
    return TrendResult(spec, table, rows, spec.row_date)


# --------------------------------------------------------------------------- #
# Controls & guidance shared by every trend view
# --------------------------------------------------------------------------- #
def basis_selector(key: str, label: str = "Trend basis (nomination count only)",
                   help: str = "Which Wave-1 date places a TPID in a month. The "
                               "other three trends are dated by Actual End Date, "
                               "which is what they measure.") -> str:
    """The approval-vs-created radio, returning the date column it selects."""
    basis = st.radio(label, ["Nomination approval date", "Nomination created date"],
                     horizontal=True, key=f"{key}_basis", help=help)
    return "approval_date" if basis.startswith("Nomination approval") else "created_date"


def guidance(by_fy: bool) -> None:
    """How to read the chart below — the note differs over "All time"."""
    if by_fy:
        st.caption("**All time** — each fiscal year is its own line over a shared "
                   "Jul → Jun axis, so the years can be read against each other. "
                   "Click a point **or a table row** to open that month's records.")
    else:
        st.caption("Click a bar **or a row of the table** to open the records behind "
                   "that month.")


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #
def render_trend(result: TrendResult, *, key: str, title: str | None = None,
                 display_col: str | None = None, shown: str | None = None,
                 by_fy: bool = False, help: str | None = None) -> None:
    """One trend: heading, chart, summary table and the records behind them.

    ``title`` and ``display_col`` are presentation only — the AVS → Azure Native
    pages call the same Total Cores measurement "Cores Migrated" where the AVS
    categories call it "Hosts"/"Nodes Deployed".  Nothing about the computation
    changes with the noun.
    """
    spec = result.spec
    display_col = display_col or spec.value_col
    subheading(title or spec.title, help=help or spec.help, period=shown)
    if result.table.empty:
        components.empty_state(f"No {spec.what} in the selected period.")
        return
    if by_fy:
        _fy_trend(result, display_col, key)
        return
    fig = charts.trend_chart(result.table, "period", spec.value_col, "Cumulative",
                             currency=spec.currency, height=320)
    drilldown.chart_with_drilldown(
        fig, with_period(result.rows, result.row_date), "period",
        key=f"{key}_{spec.value_col}".replace(" ", "_"), what=spec.what,
        unit_col=spec.unit_col,
        summary=display_trend(result.table, display_col, spec.currency),
        summary_bucket="Month")


def _fy_trend(result: TrendResult, display_col: str, key: str) -> None:
    """One line per fiscal year, with the same click-through to the records.

    A month label alone is ambiguous here — every year has a September — so the
    chart, the summary table and the records are all keyed on "FY27 Sep", and
    the line a point sits on is what tells the two Septembers apart.  The
    year-over-year grid lives in the underlying-data panel, where it can be read
    side by side without breaking that key.
    """
    spec = result.spec
    value_col, currency = spec.value_col, spec.currency
    split = kpi.split_by_fiscal_year(result.table, value_col, FY_START_MONTH)
    if split.empty:
        components.empty_state(f"No {spec.what} to chart.")
        return
    years = sorted(split["fy"].unique())
    order = metrics.fiscal_month_order(FY_START_MONTH)

    fig = charts.fy_lines(split, "fy_month", "fy", value_col, order,
                          currency=currency, height=340)
    summary = split.rename(columns={"bucket": "Period", "fy": "FY", "fy_month": "Month",
                                    value_col: display_col})
    summary = summary[["Period", "FY", "Month", display_col]]
    if currency:
        summary[display_col] = summary[display_col].map(fmt_currency)
    drilldown.chart_with_drilldown(
        fig, kpi.label_fiscal_year(result.rows, result.row_date, FY_START_MONTH), "bucket",
        key=f"{key}_{value_col}_fy".replace(" ", "_"), what=spec.what,
        unit_col=spec.unit_col, summary=summary, summary_bucket="Period",
        curve_labels=years)

    grid = split.pivot_table(index="fy_month", columns="fy", values=value_col,
                             aggfunc="sum")
    grid = grid.reindex([m for m in order if m in grid.index]).fillna(0)
    totals = split.groupby("fy")[value_col].sum()
    st.caption("Totals per fiscal year: " + " · ".join(
        f"**{fy}** {fmt_currency(v) if currency else fmt_int(v)}"
        for fy, v in totals.items()) +
        " — no cumulative column here, because a running total across unrelated "
        "fiscal years would not mean anything.")
    display = grid.copy()
    if currency:
        for col in display.columns:
            display[col] = display[col].map(fmt_currency)
    drilldown.data_expander(
        display.reset_index().rename(columns={"fy_month": "Month"}),
        f"{key}_{value_col}_fy_grid".replace(" ", "_"),
        label="Underlying data — fiscal years side by side",
        caption="The same numbers as the chart, one column per fiscal year.")


# --------------------------------------------------------------------------- #
def with_period(rows: pd.DataFrame, date_col: str) -> pd.DataFrame:
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


def display_trend(table: pd.DataFrame, display_col: str | None = None,
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
