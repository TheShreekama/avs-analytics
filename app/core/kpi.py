"""Requirement-defined metrics, computed at TPID grain with their source records.

Every metric here follows the rules in the requirements document to the letter:

* **Unique-TPID metrics** (new engagements, migration starts/ends) count a
  qualifying TPID exactly once, no matter how many waves it has.
* **Hosts migrated** is deliberately *not* a TPID count: it sums ``Total Cores``
  over the qualifying wave records, each counted once.
* **Migration completion always evaluates the latest wave** of a TPID.  A TPID
  with Wave 7 completed and Wave 8 outstanding is not a completed migration.
* **On-Track** is read from the *Current State* column of the latest wave, not
  inferred from "not finished": a blocked or waiting account is not on track.
* **ACR claimed** is wave-level and period-bound: every wave whose *Actual End
  Date* falls in the window contributes its ACR, so one account can claim in
  several months.
* **Cumulative** is the running total of the months actually displayed, never a
  separate population.

Each function returns a :class:`Metric` carrying both the number and the rows
behind it, so any chart or tile can drop straight into a drill-down table
without recomputing (and without the table and the number ever disagreeing).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from . import metrics, segments

# Columns offered in every drill-down table, in this order (missing ones are skipped).
DRILLDOWN_COLUMNS = [
    "tpid", "customer_name", "solution_architect", "assigned_pm",
    "migration_category", "generation", "source_platform",
    "target_platform", "phase", "avs_sku", "migration_status_label", "approval_date",
    "actual_start_date", "actual_end_date", "total_cores", "total_acr",
    "current_state", "eos_status", "region_geo", "migration_path",
]

COMPLETED_CODE = 7
STATE_ON_TRACK = "On-Track"
STATE_COMPLETED = "Completed"
STATE_CANCELLED = "Cancelled"
STATE_OTHER = "Other"

#: The only two states reported on the pipeline chart.  Cancelled accounts and
#: accounts sitting in a blocked/waiting state are deliberately not shown there.
REPORTED_STATES = (STATE_ON_TRACK, STATE_COMPLETED)

#: "On Track", "On-Track", "on  track" — the Current State column is free text.
_ON_TRACK_PATTERN = r"on\s*-?\s*track"

#: Migration Status codes that describe a migration still in flight:
#: 1 - Validating Commitment & Initial Scope, 2 - Executing Pre-Requisites,
#: 3 - Finalize Scope, 4 - Executing Migration.  Everything else is deferred (5),
#: cancelled (6) or completed (7) and can never be On-Track.
IN_FLIGHT_CODES = (1, 2, 3, 4)


@dataclass
class WaveIndex:
    """A population's first and latest wave per TPID, computed once.

    Sorting 500k waves takes ~0.7s, and a dashboard needs these frames half a
    dozen times, so a view builds this once and hands it to every metric.
    """
    first: pd.DataFrame
    last: pd.DataFrame


def wave_index(fact: pd.DataFrame) -> WaveIndex:
    return WaveIndex(first=first_wave(fact), last=latest_wave(fact))


@dataclass
class Metric:
    """A metric value plus the records that produced it."""
    value: float
    unit: str
    records: pd.DataFrame = field(default_factory=pd.DataFrame)

    @property
    def count(self) -> int:
        return int(self.value)


# --------------------------------------------------------------------------- #
# Wave selection
# --------------------------------------------------------------------------- #
def _ordered(fact: pd.DataFrame) -> pd.DataFrame:
    """Rows sorted so that a TPID's waves run first → last."""
    df = fact.copy()
    if "tpid_key" not in df.columns:
        df["tpid_key"] = segments.tpid_key(df)
    df["_wave_order"] = df["wave_num"].fillna(9_999)
    df["_date_order"] = df["created_date"].fillna(pd.Timestamp.max)
    return df.sort_values(["tpid_key", "_wave_order", "_date_order"])


def first_wave(fact: pd.DataFrame) -> pd.DataFrame:
    """One row per TPID: its Wave-1 (lowest wave number)."""
    if fact.empty:
        return fact
    return _ordered(fact).groupby("tpid_key", as_index=False, sort=False).first()


def latest_wave(fact: pd.DataFrame) -> pd.DataFrame:
    """One row per TPID: its most recent wave."""
    if fact.empty:
        return fact
    return _ordered(fact).groupby("tpid_key", as_index=False, sort=False).last()


def is_completed(df: pd.DataFrame) -> pd.Series:
    """Migration Status = "7 - Completed" (by code, or by label when uncoded)."""
    if df.empty:
        return pd.Series(dtype=bool)
    code = pd.to_numeric(df.get("migration_status_code"), errors="coerce")
    label = df.get("migration_status_label", pd.Series("", index=df.index))
    return (code.eq(COMPLETED_CODE)
            | label.astype("string").str.contains("complete", case=False, na=False)).fillna(False)


def in_window(dates: pd.Series, start, end) -> pd.Series:
    d = pd.to_datetime(dates, errors="coerce")
    mask = d.notna()
    if start is not None:
        mask &= d >= pd.Timestamp(start)
    if end is not None:
        mask &= d <= pd.Timestamp(end)
    return mask


# --------------------------------------------------------------------------- #
# Headline metrics
# --------------------------------------------------------------------------- #
def new_engagements(fact: pd.DataFrame, start=None, end=None,
                    firsts: pd.DataFrame | None = None) -> Metric:
    """Unique TPIDs whose **Wave-1** nomination approval date falls in the period."""
    if fact.empty:
        return Metric(0, "customers")
    firsts = first_wave(fact) if firsts is None else firsts
    hit = firsts[in_window(firsts["approval_date"], start, end)]
    return Metric(len(hit), "customers", hit)


def migrations_completed(fact: pd.DataFrame, start=None, end=None,
                         lasts: pd.DataFrame | None = None) -> Metric:
    """Unique TPIDs whose **latest** wave is completed, dated by its actual end.

    A TPID whose last wave is still running is not counted, even when earlier
    waves are complete.
    """
    if fact.empty:
        return Metric(0, "customers")
    lasts = latest_wave(fact) if lasts is None else lasts
    done = lasts[is_completed(lasts)]
    hit = done[in_window(done["actual_end_date"], start, end)]
    return Metric(len(hit), "customers", hit)


def migration_starts(fact: pd.DataFrame, start=None, end=None) -> Metric:
    """Unique TPIDs whose first actual start date falls in the period."""
    if fact.empty:
        return Metric(0, "customers")
    df = _ordered(fact)
    starts = (df.dropna(subset=["actual_start_date"])
                .groupby("tpid_key", as_index=False, sort=False).first())
    hit = starts[in_window(starts["actual_start_date"], start, end)]
    return Metric(len(hit), "customers", hit)


def hosts_migrated(fact: pd.DataFrame, start=None, end=None) -> Metric:
    """Sum of Total Cores (nodes/hosts) over completed wave records in the period.

    Explicitly *not* a unique-TPID count: every qualifying wave record contributes
    its own hosts, and each source record is counted once.
    """
    if fact.empty:
        return Metric(0, "hosts")
    rows = fact[is_completed(fact)]
    rows = rows[in_window(rows["actual_end_date"], start, end)]
    rows = _dedupe_records(rows)
    total = float(pd.to_numeric(rows.get("total_cores"), errors="coerce").sum())
    return Metric(total, "hosts", rows)


def acr_claimed(fact: pd.DataFrame, start=None, end=None) -> Metric:
    """ACR of every **wave** whose Actual End Date falls inside the period.

    Claiming is wave-level, not account-level: if Waves 2 and 3 of one account
    and Wave 5 of another ended inside the window, all three waves' ACR is
    summed.  A wave that ended outside the window contributes nothing, even when
    a sibling wave of the same account did end inside it.
    """
    if fact.empty:
        return Metric(0.0, "ACR")
    rows = _dedupe_records(fact[in_window(fact["actual_end_date"], start, end)])
    total = float(pd.to_numeric(rows.get("total_acr"), errors="coerce").sum())
    return Metric(total, "ACR", rows)


def on_track_accounts(fact: pd.DataFrame,
                      lasts: pd.DataFrame | None = None) -> Metric:
    """Accounts whose **latest** wave reads On-Track in the Current State column.

    Independent of the reporting period: this is where the pipeline stands now.
    """
    if fact.empty:
        return Metric(0, "customers")
    lasts = latest_wave(fact) if lasts is None else lasts
    rows = lasts[state_of(lasts) == STATE_ON_TRACK]
    return Metric(len(rows), "customers", rows)


def _dedupe_records(df: pd.DataFrame) -> pd.DataFrame:
    """Drop repeated source records so nothing is counted twice."""
    if df.empty or "task_id" not in df.columns:
        return df
    keyed = df[df["task_id"].notna()]
    unkeyed = df[df["task_id"].isna()]
    return pd.concat([keyed.drop_duplicates(subset=["task_id"]), unkeyed])


# --------------------------------------------------------------------------- #
# Month-over-month trends (each with a Cumulative final column)
# --------------------------------------------------------------------------- #
def _month(dates: pd.Series) -> pd.Series:
    return pd.to_datetime(dates, errors="coerce").dt.to_period("M")


def monthly_unique_tpids(fact: pd.DataFrame, date_col: str = "approval_date",
                         start=None, end=None, firsts: pd.DataFrame | None = None
                         ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Unique TPIDs per month, each TPID counted once in the month of its Wave-1 date."""
    if firsts is None:
        firsts = first_wave(fact) if not fact.empty else fact
    if firsts.empty:
        return _empty_trend("Nominations"), firsts
    rows = firsts[in_window(firsts[date_col], start, end)].copy()
    rows["month"] = _month(rows[date_col])
    summary = (rows.groupby("month", as_index=False)
                   .agg(value=("tpid_key", "nunique")))
    return _finish_trend(summary, "Nominations"), rows


def monthly_acr_claimed(fact: pd.DataFrame, start=None, end=None
                        ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """ACR claimed per month, by the **Actual End Date** of each qualifying wave."""
    metric = acr_claimed(fact, start, end)
    rows = metric.records.copy()
    if rows.empty:
        return _empty_trend("ACR Claimed"), rows
    rows["month"] = _month(rows["actual_end_date"])
    rows["_acr"] = pd.to_numeric(rows.get("total_acr"), errors="coerce")
    summary = rows.groupby("month", as_index=False).agg(value=("_acr", "sum"))
    return _finish_trend(summary, "ACR Claimed"), rows


def monthly_hosts(fact: pd.DataFrame, start=None, end=None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Hosts (Total Cores) completed per month, by actual end date."""
    if fact.empty:
        return _empty_trend("Hosts"), fact
    rows = _dedupe_records(fact[is_completed(fact)])
    rows = rows[in_window(rows["actual_end_date"], start, end)].copy()
    if rows.empty:
        return _empty_trend("Hosts"), rows
    rows["month"] = _month(rows["actual_end_date"])
    rows["_cores"] = pd.to_numeric(rows["total_cores"], errors="coerce")
    summary = rows.groupby("month", as_index=False).agg(value=("_cores", "sum"))
    return _finish_trend(summary, "Hosts"), rows


def monthly_migrations_completed(fact: pd.DataFrame, start=None, end=None,
                                 lasts: pd.DataFrame | None = None
                                 ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Completed migrations per month (unique TPIDs, latest wave completed)."""
    done = migrations_completed(fact, start, end, lasts)
    rows = done.records.copy()
    if rows.empty:
        return _empty_trend("Migrations Completed"), rows
    rows["month"] = _month(rows["actual_end_date"])
    summary = rows.groupby("month", as_index=False).agg(value=("tpid_key", "nunique"))
    return _finish_trend(summary, "Migrations Completed"), rows


def _empty_trend(label: str) -> pd.DataFrame:
    return pd.DataFrame(columns=["month", "period", label, "Cumulative"])


def _finish_trend(summary: pd.DataFrame, label: str) -> pd.DataFrame:
    """Order months, add a readable period label and the Cumulative final column."""
    if summary.empty:
        return _empty_trend(label)
    summary = summary.dropna(subset=["month"]).sort_values("month")
    summary["period"] = summary["month"].astype(str)
    summary = summary.rename(columns={"value": label})
    # Cumulative reflects only the months displayed, and is always the last column.
    summary["Cumulative"] = summary[label].cumsum()
    summary["month"] = summary["month"].dt.to_timestamp()
    return summary[["month", "period", label, "Cumulative"]].reset_index(drop=True)


# --------------------------------------------------------------------------- #
# Fiscal-year split (the "All time" view of every trend)
# --------------------------------------------------------------------------- #
#: How a point on an FY-split chart names itself, so a click can find its rows.
def fy_bucket(fy: str, month_name: str) -> str:
    return f"{fy} {month_name}"


def split_by_fiscal_year(table: pd.DataFrame, value_col: str,
                         fy_start_month: int = 7) -> pd.DataFrame:
    """A monthly trend re-cut as one series per fiscal year.

    Over "All time" a single continuous line just gets longer; laying the fiscal
    years on top of one another over a shared Jul→Jun axis is what makes
    year-over-year movement readable.  Returns long-form rows
    (fy, fy_month, bucket, value), never a cumulative column: cumulative across
    unrelated years is meaningless.
    """
    if table is None or table.empty:
        return pd.DataFrame(columns=["fy", "fy_month", "bucket", value_col])
    out = table.copy()
    months = pd.to_datetime(out["month"])
    out["fy"] = [metrics.fiscal_year_label(m, fy_start_month) for m in months]
    out["fy_month"] = months.dt.strftime("%b")
    out["bucket"] = [fy_bucket(f, m) for f, m in zip(out["fy"], out["fy_month"])]
    return out[["fy", "fy_month", "bucket", value_col]].reset_index(drop=True)


def label_fiscal_year(rows: pd.DataFrame, date_col: str,
                      fy_start_month: int = 7) -> pd.DataFrame:
    """Tag records with the FY-split chart's bucket, so a click can filter them."""
    if rows is None or rows.empty:
        return rows if rows is not None else pd.DataFrame()
    out = rows.copy()
    dates = pd.to_datetime(out[date_col], errors="coerce")
    out["fy"] = [metrics.fiscal_year_label(d, fy_start_month) if pd.notna(d) else ""
                 for d in dates]
    out["fy_month"] = dates.dt.strftime("%b").fillna("")
    out["bucket"] = [fy_bucket(f, m) if f else "" for f, m in zip(out["fy"], out["fy_month"])]
    return out


# --------------------------------------------------------------------------- #
# Current pipeline
# --------------------------------------------------------------------------- #
def in_flight(df: pd.DataFrame) -> pd.Series:
    """Migration Status is one of the four in-flight codes (1, 2, 3, 4).

    A migration that is deferred, cancelled or completed is not in flight, so it
    can never be On-Track however its Current State reads.
    """
    if df.empty:
        return pd.Series(dtype=bool)
    code = pd.to_numeric(df.get("migration_status_code"), errors="coerce")
    return code.isin(IN_FLIGHT_CODES).fillna(False)


def state_of(df: pd.DataFrame) -> pd.Series:
    """Current state of one-row-per-TPID latest-wave records.

    Read from the latest wave, in this order:

    1. **Completed** — the wave's Migration Status is "7 - Completed".
    2. **Cancelled** — the wave resolved to a cancelled/archived status.
    3. **On-Track** — BOTH conditions hold:
       * Migration Status is one of the four in-flight codes — "1 - Validating
         Commitment & Initial Scope", "2 - Executing Pre-Requisites",
         "3 - Finalize Scope", "4 - Executing Migration"; and
       * Current State reads "On Track"/"On-Track".
    4. **Other** — everything else.  A wave deferred ("5 - Deferred by
       Customer") is not on track however its Current State reads; nor is one
       whose Current State says "Blocked - Customer" or "Waiting action on
       follow up date" however its status reads.

    A row whose Current State is blank falls back to the status alone, so a file
    that never got that column mapped still reports a pipeline rather than an
    empty one.
    """
    if df.empty:
        return pd.Series(dtype="object")
    completed = is_completed(df)
    cancelled = df.get("eos_status", pd.Series("", index=df.index)) \
        .eq(STATE_CANCELLED).fillna(False)
    moving = in_flight(df)

    raw = (df["current_state"].astype("string").str.strip()
           if "current_state" in df.columns
           else pd.Series(pd.NA, index=df.index, dtype="string"))
    unstated = raw.isna() | raw.eq("")
    reads_on_track = raw.str.contains(_ON_TRACK_PATTERN, case=False, na=False, regex=True)

    out = pd.Series(STATE_OTHER, index=df.index, dtype="object")
    out[moving & (reads_on_track | unstated)] = STATE_ON_TRACK
    out[cancelled] = STATE_CANCELLED
    out[completed] = STATE_COMPLETED
    return out


def by_state(fact: pd.DataFrame, lasts: pd.DataFrame | None = None,
             only: tuple[str, ...] | None = REPORTED_STATES
             ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Account count and ACR by current state, from each TPID's latest wave.

    ``only`` restricts both the summary and the drill-down rows to the states
    worth reporting — On-Track and Completed — so cancelled, blocked and waiting
    accounts do not pad the chart.  Pass ``only=None`` for every state.
    """
    if lasts is None:
        lasts = latest_wave(fact) if not fact.empty else fact
    if lasts.empty:
        return pd.DataFrame(columns=["category", "count", "acr"]), lasts
    rows = lasts.copy()
    rows["state"] = state_of(rows)
    if only:
        rows = rows[rows["state"].isin(only)]
    if rows.empty:
        return pd.DataFrame(columns=["category", "count", "acr"]), rows
    rows["_acr"] = pd.to_numeric(rows.get("total_acr"), errors="coerce")
    summary = (rows.groupby("state", as_index=False)
                   .agg(count=("tpid_key", "nunique"), acr=("_acr", "sum"))
                   .rename(columns={"state": "category"})
                   .sort_values("count", ascending=False))
    return summary.reset_index(drop=True), rows


def on_track_by_stage(fact: pd.DataFrame,
                      lasts: pd.DataFrame | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """On-track accounts grouped by their current migration stage, with ACR."""
    if lasts is None:
        lasts = latest_wave(fact) if not fact.empty else fact
    if lasts.empty:
        return pd.DataFrame(columns=["category", "count", "acr"]), lasts
    rows = lasts.copy()
    rows["state"] = state_of(rows)
    rows = rows[rows["state"] == STATE_ON_TRACK].copy()
    if rows.empty:
        return pd.DataFrame(columns=["category", "count", "acr"]), rows
    rows["stage"] = (rows["migration_status_label"].astype("string")
                     .replace({"": pd.NA}).fillna("Unknown"))
    rows["_acr"] = pd.to_numeric(rows.get("total_acr"), errors="coerce")
    summary = (rows.groupby("stage", as_index=False)
                   .agg(count=("tpid_key", "nunique"), acr=("_acr", "sum"))
                   .rename(columns={"stage": "category"})
                   .sort_values("count", ascending=False))
    return summary.reset_index(drop=True), rows


# --------------------------------------------------------------------------- #
# Drill-down helper
# --------------------------------------------------------------------------- #
def drilldown_frame(records: pd.DataFrame) -> pd.DataFrame:
    """Trim underlying records to the agreed drill-down columns."""
    if records is None or records.empty:
        return pd.DataFrame(columns=[c for c in DRILLDOWN_COLUMNS])
    cols = [c for c in DRILLDOWN_COLUMNS if c in records.columns]
    return records[cols].reset_index(drop=True)
