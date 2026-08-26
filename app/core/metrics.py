"""Time-period helpers and KPI calculations.

All period maths is anchored on an *as-of* date so the same dataset can be
reported "as of" any chosen day (defaults to the latest activity in the data).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class Period:
    label: str
    start: pd.Timestamp
    end: pd.Timestamp

    def contains(self, s: pd.Series) -> pd.Series:
        return (s >= self.start) & (s <= self.end)


def quarter_start(ts: pd.Timestamp) -> pd.Timestamp:
    q = (ts.month - 1) // 3
    return pd.Timestamp(year=ts.year, month=q * 3 + 1, day=1)


def standard_periods(as_of: pd.Timestamp) -> dict[str, Period]:
    """WTD / MTD / QTD / YTD windows ending on ``as_of``."""
    as_of = pd.Timestamp(as_of).normalize()
    week_start = as_of - pd.Timedelta(days=int(as_of.weekday()))  # Monday
    return {
        "week": Period("This Week", week_start, as_of),
        "month": Period("This Month", as_of.replace(day=1), as_of),
        "quarter": Period("This Quarter", quarter_start(as_of), as_of),
        "ytd": Period("Year-to-Date", as_of.replace(month=1, day=1), as_of),
    }


def fiscal_year_start(as_of: pd.Timestamp, fy_start_month: int = 7) -> pd.Timestamp:
    """Start of the fiscal year containing ``as_of`` (Microsoft FY starts July)."""
    as_of = pd.Timestamp(as_of)
    y = as_of.year if as_of.month >= fy_start_month else as_of.year - 1
    return pd.Timestamp(year=y, month=fy_start_month, day=1)


def fiscal_year_end(fy_start: pd.Timestamp) -> pd.Timestamp:
    """Last day of the fiscal year that begins on ``fy_start`` (30 Jun for a July FY)."""
    return pd.Timestamp(fy_start) + pd.DateOffset(years=1) - pd.Timedelta(days=1)


def date_preset_range(as_of: pd.Timestamp, name: str,
                      fy_start_month: int = 7) -> tuple[pd.Timestamp, pd.Timestamp] | None:
    """Resolve a named date-range preset to (start, end) anchored on ``as_of``.

    Returns ``None`` for "All time" / "Custom" (no fixed range).
    """
    as_of = pd.Timestamp(as_of).normalize()
    wk_start = as_of - pd.Timedelta(days=int(as_of.weekday()))  # Monday of this week
    if name == "This week":
        return wk_start, as_of
    if name == "Last week":
        return wk_start - pd.Timedelta(days=7), wk_start - pd.Timedelta(days=1)
    if name == "This month":
        return as_of.replace(day=1), as_of
    if name == "Last month":
        prev_end = as_of.replace(day=1) - pd.Timedelta(days=1)
        return prev_end.replace(day=1), prev_end
    if name == "This quarter":
        return quarter_start(as_of), as_of
    if name == "Last quarter":
        prev_end = quarter_start(as_of) - pd.Timedelta(days=1)
        return quarter_start(prev_end), prev_end
    if name == "Last 3 months":
        return as_of - pd.DateOffset(months=3) + pd.Timedelta(days=1), as_of
    if name == "Last 6 months":
        return as_of - pd.DateOffset(months=6) + pd.Timedelta(days=1), as_of
    if name == "This FY":
        # The whole fiscal year, not year-to-date: 1 Jul → 30 Jun.
        start = fiscal_year_start(as_of, fy_start_month)
        return start, fiscal_year_end(start)
    if name == "Last FY":
        start = fiscal_year_start(as_of, fy_start_month) - pd.DateOffset(years=1)
        return start, fiscal_year_end(start)
    if name == "Year to date":
        return as_of.replace(month=1, day=1), as_of
    return None  # All time / Custom


def count_in_periods(dates: pd.Series, as_of: pd.Timestamp) -> dict[str, int]:
    """Count non-null dates falling inside each standard period."""
    dates = pd.to_datetime(dates, errors="coerce")
    periods = standard_periods(as_of)
    return {name: int(p.contains(dates).sum()) for name, p in periods.items()}


def prior_equivalent_count(dates: pd.Series, as_of: pd.Timestamp, kind: str) -> int:
    """Count for the prior equivalent window (e.g. last month) for deltas."""
    dates = pd.to_datetime(dates, errors="coerce")
    as_of = pd.Timestamp(as_of).normalize()
    if kind == "month":
        prev_end = as_of.replace(day=1) - pd.Timedelta(days=1)
        start = prev_end.replace(day=1)
        end = min(prev_end, start + pd.Timedelta(days=as_of.day - 1))
    elif kind == "quarter":
        qs = quarter_start(as_of)
        prev_end = qs - pd.Timedelta(days=1)
        start = quarter_start(prev_end)
        end = min(prev_end, start + pd.Timedelta(days=(as_of - qs).days))
    elif kind == "week":
        start = as_of - pd.Timedelta(days=int(as_of.weekday()) + 7)
        end = start + pd.Timedelta(days=int(as_of.weekday()))
    elif kind == "ytd":
        prev = as_of.replace(year=as_of.year - 1)
        start = prev.replace(month=1, day=1)
        end = prev
    else:
        return 0
    return int(((dates >= start) & (dates <= end)).sum())


def pct_delta(curr: float, prior: float) -> float | None:
    if prior in (0, None) or pd.isna(prior):
        return None
    return round(100.0 * (curr - prior) / prior, 1)


# --------------------------------------------------------------------------- #
# Headline KPIs
# --------------------------------------------------------------------------- #
def headline_kpis(fact: pd.DataFrame) -> dict:
    """Top-of-dashboard KPI bundle."""
    n = len(fact)
    approved = int(fact["is_approved"].sum())
    closed = int(fact["is_closed"].sum())
    open_ = int(fact["is_open"].sum())
    accounts = int(fact["tpid"].nunique(dropna=True)) if "tpid" in fact else 0
    acr = float(fact["total_acr"].sum(skipna=True)) if "total_acr" in fact else 0.0
    cores = float(fact["total_cores"].sum(skipna=True)) if "total_cores" in fact else 0.0
    closure_rate = round(100 * closed / n, 1) if n else 0.0
    median_age = float(np.nanmedian(fact["aging_days"])) if fact["aging_days"].notna().any() else 0.0
    median_cycle = (float(np.nanmedian(fact["cycle_time_days"]))
                    if fact["cycle_time_days"].notna().any() else 0.0)
    return {
        "nominations": n,
        "accounts": accounts,
        "approved": approved,
        "closed": closed,
        "open": open_,
        "closure_rate": closure_rate,
        "total_acr": acr,
        "total_cores": cores,
        "median_age_days": median_age,
        "median_cycle_days": median_cycle,
        "dq_rows": int(fact["has_dq_issue"].sum()) if "has_dq_issue" in fact else 0,
    }


def fmt_currency(v: float) -> str:
    if v is None or pd.isna(v):
        return "—"
    a = abs(v)
    if a >= 1e9:
        return f"${v/1e9:.2f}B"
    if a >= 1e6:
        return f"${v/1e6:.2f}M"
    if a >= 1e3:
        return f"${v/1e3:.1f}K"
    return f"${v:,.0f}"


def fmt_int(v) -> str:
    if v is None or pd.isna(v):
        return "—"
    return f"{int(v):,}"
