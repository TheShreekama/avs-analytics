"""Requirement-defined metrics, computed at TPID grain with their source records.

Every metric here follows the rules in the requirements document to the letter:

* **Unique-TPID metrics** (new engagements, migration starts/ends) count a
  qualifying TPID exactly once, no matter how many waves it has.
* **Hosts migrated** is deliberately *not* a TPID count: it sums ``Total Cores``
  over the qualifying wave records, each counted once.
* **Migration completion evaluates the latest wave *and* every other wave.**  A
  TPID is Completed only when its latest wave is completed **and none** of its
  waves is On Track; a TPID with Wave 7 completed and Wave 8 outstanding is not
  a completed migration, and neither is one whose latest wave completed while an
  earlier wave is still running.
* **On-Track** is read from the *Current State* column, not inferred from "not
  finished": a blocked or waiting account is not on track.  **Any** On-Track
  wave makes the account On-Track, whatever its latest wave says.
* **Accounts that are neither** — blocked, deferred, cancelled/archived or
  waiting — are reported on their own (:func:`excluded_accounts`) and never
  mixed into the On-Track/Completed numbers.
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

from . import metrics, segments, statuses

# Columns offered in every drill-down table, in this order (missing ones are skipped).
#: ``factory_offering`` and ``migration_path`` are **two different columns** and
#: both are carried: the Factory Offering names which factory delivers the work
#: ("AVS Migration Nominations", "SQL Migration Nominations"), the Primary
#: Migration Path names what is moving where ("Onprem to AVS", "SQL Server MI
#: Migration (From AVS)").  Reporting one as if it were the other loses the
#: distinction every scope rule in this module turns on.
DRILLDOWN_COLUMNS = [
    "tpid", "customer_name", "solution_architect", "assigned_pm",
    "migration_category", "generation", "source_platform",
    "target_platform", "phase", "avs_sku", "migration_status_label", "approval_date",
    "actual_start_date", "actual_end_date", "reported_end_date", "end_date_source",
    "total_cores", "total_acr",
    "current_state", "region_geo", "factory_offering", "migration_path",
]

COMPLETED_CODE = 7
DEFERRED_CODE = 5
CANCELLED_CODE = 6
STATE_ON_TRACK = "On-Track"
STATE_COMPLETED = "Completed"
STATE_CANCELLED = "Cancelled"
STATE_DEFERRED = "Deferred"
STATE_BLOCKED = "Blocked"
STATE_ON_HOLD = "On Hold"
STATE_OTHER = "Other"

#: The only two states reported on the pipeline chart.  Cancelled accounts and
#: accounts sitting in a blocked/waiting state are deliberately not shown there.
REPORTED_STATES = (STATE_ON_TRACK, STATE_COMPLETED)

#: The Current State values that mean "this account is stopped" — the only ones
#: the blocked-accounts section reports.  Written exactly as the export writes
#: them; matched through :func:`_state_key`, so spacing, dash style and case in
#: the file cannot hide one ("Blocked – Partner/ISD" is the same state).
BLOCKED_STATES: tuple[str, ...] = (
    "Blocked",
    "Blocked - Account team",
    "Blocked - Customer",
    "Blocked - Partner / ISD",
    "Waiting action on follow up date",
)

#: Everything the primary reports leave out: an account in one of these states
#: is neither delivering nor delivered, so it is reported separately (see
#: :func:`excluded_accounts`) rather than padding the On-Track/Completed cut.
#: The two sets are complementary and never overlap — every account resolves to
#: exactly one state — so nothing is counted twice and nothing is dropped.
EXCLUDED_STATES = (STATE_BLOCKED, STATE_ON_HOLD, STATE_DEFERRED, STATE_CANCELLED,
                   STATE_OTHER)

#: "On Track", "On-Track", "on  track" — the Current State column is free text.
_ON_TRACK_PATTERN = r"on\s*-?\s*track"

#: Current State values that mean the migration is under way or finished — the
#: waves a *migration start* can be read from.  Matched against the raw column,
#: not the derived state: a wave reading "Done" has started by definition,
#: whatever its Migration Status code says.
_STARTED_STATE_PATTERN = _ON_TRACK_PATTERN + r"|done|complete"

#: Migration Status codes that describe a migration still in flight:
#: 1 - Validating Commitment & Initial Scope, 2 - Executing Pre-Requisites,
#: 3 - Finalize Scope, 4 - Executing Migration.  Everything else is deferred (5),
#: cancelled (6) or completed (7) and can never be On-Track.
IN_FLIGHT_CODES = (1, 2, 3, 4)


@dataclass
class WaveIndex:
    """A population's first, latest and approval wave per TPID, computed once.

    Sorting 500k waves takes ~0.7s, and a dashboard needs these frames half a
    dozen times, so a view builds this once and hands it to every metric.

    ``approval`` is the wave a nomination is *dated* by — see
    :func:`dated_wave`.  It is a frame of its own rather than a column on
    ``first`` because the wave that carries the approval date is not always
    Wave-1, and a drill-down has to be able to show which wave it was.
    """
    first: pd.DataFrame
    last: pd.DataFrame
    approval: pd.DataFrame = field(default_factory=pd.DataFrame)


def wave_index(fact: pd.DataFrame) -> WaveIndex:
    ordered = _ordered(fact) if not fact.empty else fact
    return WaveIndex(first=_first_of(ordered), last=_last_of(ordered),
                     approval=_dated_wave_of(ordered, "approval_date"))


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
    """Rows sorted so that a TPID's waves run first → last.

    A frame with no wave number at all — the customer rollup, which is already
    one row per account — sorts on the creation date alone rather than failing:
    first and latest wave of a one-row account are that row either way.
    """
    df = fact.copy()
    if "tpid_key" not in df.columns:
        df["tpid_key"] = segments.tpid_key(df)
    waves = df["wave_num"] if "wave_num" in df.columns else pd.Series(
        pd.NA, index=df.index, dtype="Float64")
    created = df["created_date"] if "created_date" in df.columns else pd.Series(
        pd.NaT, index=df.index)
    df["_wave_order"] = waves.fillna(9_999)
    df["_date_order"] = created.fillna(pd.Timestamp.max)
    return df.sort_values(["tpid_key", "_wave_order", "_date_order"])


def first_wave(fact: pd.DataFrame) -> pd.DataFrame:
    """One row per TPID: its Wave-1 (lowest wave number)."""
    if fact.empty:
        return fact
    return _first_of(_ordered(fact))


def latest_wave(fact: pd.DataFrame) -> pd.DataFrame:
    """One row per TPID: its most recent wave."""
    if fact.empty:
        return fact
    return _last_of(_ordered(fact))


def _first_of(ordered: pd.DataFrame) -> pd.DataFrame:
    """The account's Wave-1 row itself — every cell from that one wave.

    ``GroupBy.first()`` would fill each column independently from the first wave
    that has a value for it, which quietly builds a row no wave ever had: Wave-1's
    task id next to Wave-3's approval date.  Where a *date* is meant to fall
    through to a later wave that is now :func:`dated_wave`'s job, stated as a
    rule and carrying the wave it read.
    """
    if ordered.empty:
        return ordered
    return ordered.groupby("tpid_key", sort=False).head(1).reset_index(drop=True)


def _last_of(ordered: pd.DataFrame) -> pd.DataFrame:
    """The account's latest wave, column-wise.

    Deliberately still ``GroupBy.last()``: where the latest wave leaves a cell
    blank — a completed wave with no Actual End Date, a wave nobody restated the
    Current State on — the account's own most recent answer stands in, and every
    state, stage and closure rule in this module has been read against that.
    """
    if ordered.empty:
        return ordered
    out = ordered.groupby("tpid_key", as_index=False, sort=False).last()
    # …except the Migration Status, which is one fact told in several columns
    # and must come whole from the latest wave itself.  Filled column by
    # column, a tracking-sheet stage (which carries no number) picked up an
    # earlier export wave's code, and "Executing Migration" was labelled Stage 7.
    status = [c for c in _STATUS_COLUMNS if c in ordered.columns]
    if status:
        tails = (ordered.groupby("tpid_key", sort=False).tail(1)
                 .set_index("tpid_key")[status])
        keys = out["tpid_key"]
        for column in status:
            out[column] = keys.map(tails[column]).to_numpy()
    return out


#: The columns that together state a wave's Migration Status.
_STATUS_COLUMNS = ("migration_status", "migration_status_code",
                   "migration_status_label", "status_class", "status_source")


def dated_wave(fact: pd.DataFrame, column: str = "approval_date") -> pd.DataFrame:
    """One row per TPID: the earliest wave that actually carries *column*.

    The rule the programme states for **New Engagements**: read *Nom. Approval
    Date* from **Wave-1, whatever state or status that wave is in** — an
    unapproved, blocked or cancelled Wave-1 still dates the engagement — and
    move on to the next wave **only** when Wave-1's date is missing, then the
    one after that, until a wave has one.

    The returned row is the wave the date came from, not a Wave-1 row wearing a
    later wave's date: a drill-down that counts an account from Wave-3's
    approval has to be able to name Wave-3.  An account with no such date
    anywhere keeps its Wave-1 row (with the date still blank), so it is present
    to be listed and simply falls outside every dated window.
    """
    if fact.empty:
        return fact
    return _dated_wave_of(_ordered(fact), column)


def _dated_wave_of(ordered: pd.DataFrame, column: str) -> pd.DataFrame:
    if ordered.empty or column not in ordered.columns:
        return _first_of(ordered)
    dated = ordered[ordered[column].notna()]
    rows = _first_of(dated)
    # Accounts with the date nowhere: kept on their Wave-1 row rather than
    # dropped, so the frame stays one row per TPID and nothing silently leaves
    # the population between one metric and the next.
    missing = _first_of(ordered)
    if not rows.empty:
        missing = missing[~missing["tpid_key"].isin(set(rows["tpid_key"]))]
    if missing.empty:
        return rows
    if rows.empty:
        return missing
    return pd.concat([rows, missing], ignore_index=True)


def is_completed(df: pd.DataFrame) -> pd.Series:
    """Migration Status is completed: the export's "7 - Completed" or the
    tracking sheet's "Completed" (read through ``status_class``)."""
    return statuses.is_class(df, statuses.COMPLETED)


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
                    approvals: pd.DataFrame | None = None) -> Metric:
    """Unique TPIDs approved inside the period, dated by their **Wave-1** approval.

    Two conditions, both read from the **same wave** — the one that answers for
    the account's nomination, so the row a drill-down shows carries the date and
    the status a reader is checking:

    1. its *Nom. Approval Date* falls inside the period, and
    2. its *Nomination Status* reads **Approved** (:func:`is_nomination_approved`
       — the column itself, not an approval date standing in for it).

    **Which wave answers is decided by the date alone.**  Wave-1 does, whatever
    its *Migration Status* or *Current State* says: a cancelled or blocked
    Wave-1 still dates the engagement.  Only when Wave-1 has no *Nom. Approval
    Date* at all does the rule move on to the next wave, and the next, until one
    carries a date (:func:`dated_wave`).  The status is then read from **that**
    wave — it is not a search for an approved wave, so an account whose dating
    wave was declined is not counted at all, rather than quietly counted on a
    later wave's date.

    An account with no approval date on any wave has never been nominated as far
    as this metric can tell, and is not counted either.
    """
    if fact.empty:
        return Metric(0, "customers")
    approvals = dated_wave(fact, "approval_date") if approvals is None else approvals
    hit = approvals[in_window(approvals["approval_date"], start, end)
                    & is_nomination_approved(approvals)]
    return Metric(len(hit), "customers", hit)


def migrations_completed(fact: pd.DataFrame, start=None, end=None,
                         lasts: pd.DataFrame | None = None) -> Metric:
    """Unique TPIDs classified **Completed**, dated by their latest wave's end.

    Completed means both halves of the rule: the account's latest wave is
    completed **and none** of its waves is On Track.  A TPID whose last wave is
    still running is not counted, even when earlier waves are complete; nor is
    one whose latest wave completed while an earlier wave is still on track —
    that account is still delivering, and is counted as On-Track instead.
    """
    if fact.empty:
        return Metric(0, "customers")
    lasts = latest_wave(fact) if lasts is None else lasts
    done = lasts[account_state(fact, lasts) == STATE_COMPLETED].copy()
    dates, sources = completion_dates(fact, done["tpid_key"])
    done["completion_date"] = dates.to_numpy()
    done["reported_end_date"] = done["completion_date"]
    done["end_date_source"] = sources.to_numpy()
    hit = done[in_window(done["completion_date"], start, end)]
    return Metric(len(hit), "customers", hit)


#: Where a completed wave's end date is read from — the first one filled in.
#: The export's Actual End Date leads; a completed wave nobody dated still
#: finished, so the nearest date the export does hold stands in for it.
END_DATE_CHAIN: tuple[tuple[str, str], ...] = (
    ("actual_end_date", "Actual End Date"),
    ("planned_end_date", "Planned End Date"),
    ("actual_start_date", "Actual Start Date"),
    ("planned_start_date", "Planned Start Date"),
    ("approval_date", "Nom. Approval Date"),
    ("created_date", "Nom. Created Date"),
)


def end_dates(df: pd.DataFrame, fallback=True) -> tuple[pd.Series, pd.Series]:
    """Per row: the end date to report it by, and the column it came from.

    The **Actual End Date as the FDO export records it** (``fdo_actual_end_date``
    — never a date the EOS tracking sheet filled in), then, where *fallback*
    holds for the row, :data:`END_DATE_CHAIN` in order.  *fallback* is a bool
    or a per-row mask: completed waves fall back, anything else is dated by its
    own Actual End Date or not at all.
    """
    date = pd.Series(pd.NaT, index=df.index, dtype="datetime64[ns]")
    source = pd.Series(pd.NA, index=df.index, dtype="object")
    if df.empty:
        return date, source
    mask = (pd.Series(bool(fallback), index=df.index) if isinstance(fallback, bool)
            else pd.Series(as_bool(fallback), index=df.index))
    for position, (column, label) in enumerate(END_DATE_CHAIN):
        if position == 0 and "fdo_actual_end_date" in df.columns:
            column = "fdo_actual_end_date"
        if column not in df.columns:
            continue
        values = pd.to_datetime(df[column], errors="coerce")
        take = date.isna() & values.notna()
        if position:
            take &= mask
        date = date.where(~take, values)
        source = source.where(~take, label)
    return date, source


def as_bool(mask) -> list[bool]:
    return [bool(v) if not pd.isna(v) else False for v in mask]


def completion_dates(fact: pd.DataFrame, keys: pd.Series
                     ) -> tuple[pd.Series, pd.Series]:
    """When each completed account finished, read from its **latest wave itself**.

    That wave's Actual End Date as the FDO export records it, else its Planned
    End Date, Actual Start Date, Planned Start Date, Nom. Approval Date and Nom.
    Created Date, in that order (:data:`END_DATE_CHAIN`).  Never the tracking
    sheet's Actual Migration End Date (that dates the matrix's *migration end*
    row), so Migrations Completed and the matrix's *engagement end* are one
    rule and always reconcile.  Returned aligned to *keys*.
    """
    latest = (_ordered(fact).groupby("tpid_key", sort=False).tail(1)
              .set_index("tpid_key"))
    rows = latest.reindex(pd.Index(keys))
    dates, sources = end_dates(rows, True)
    return (pd.Series(dates.to_numpy(), index=keys.index),
            pd.Series(sources.to_numpy(), index=keys.index))


def migration_starts(fact: pd.DataFrame, start=None, end=None) -> Metric:
    """Unique TPIDs whose first actual start date falls in the period."""
    if fact.empty:
        return Metric(0, "customers")
    df = _ordered(fact)
    starts = (df.dropna(subset=["actual_start_date"])
                .groupby("tpid_key", as_index=False, sort=False).first())
    hit = starts[in_window(starts["actual_start_date"], start, end)]
    return Metric(len(hit), "customers", hit)


#: The label a date carries when the EOS tracking sheet supplied it, rather
#: than the export's own columns.  Printed in the drill-down beside the date, so
#: a reader can see which source answered for each account.
TRACKER_START_SOURCE = "EOS tracker — Migration Start Date"
TRACKER_END_SOURCE = "EOS tracker — Actual Migration End Date"
FDO_END_SOURCE = "Actual End Date (latest wave)"


def migration_start_dates(fact: pd.DataFrame) -> pd.DataFrame:
    """One row per TPID: the date its migration started, and where that came from.

    **The manual EOS tracking sheet answers first.**  Where it gives an account
    a *Migration Start Date*, that is the date: it is the programme stating when
    the migration began, rather than the export being read for a clue about it.

    Only for an account the sheet does not cover — or does not date — is the
    date derived, exactly as it always has been, because the export has no
    "migration started" field: take the account's **earliest wave whose Current
    State reads "On Track" or "Done"** — the first wave that was actually under
    way — and read its **Actual Start Date**, falling back to **Planned Start
    Date** and then to **Nom. Approval Date** when the earlier ones are blank.

    An account with neither has not started and is not counted.  The returned
    frame carries ``migration_start_date`` and ``start_date_source`` (which
    column, in which document, the date came from), so a reader can see how firm
    the number is rather than having to trust it.
    """
    if fact.empty:
        return fact
    derived = _derived_start_dates(fact)
    tracked = _tracked_dates(fact, "eos_start_date", "migration_start_date",
                             "start_date_source", TRACKER_START_SOURCE)
    return _prefer(tracked, derived, "migration_start_date")


def _derived_start_dates(fact: pd.DataFrame) -> pd.DataFrame:
    started = _started_state(fact)
    rows = _ordered(fact[started])
    if rows.empty:
        return rows
    # That one wave's own dates — never a blank cell filled from a later wave.
    firsts = _first_of(rows)

    out = firsts.copy()
    out["migration_start_date"] = pd.NaT
    out["start_date_source"] = pd.NA
    for column, label in (("actual_start_date", "Actual Start Date"),
                          ("planned_start_date", "Planned Start Date"),
                          ("approval_date", "Nom. Approval Date")):
        if column not in out.columns:
            continue
        value = pd.to_datetime(out[column], errors="coerce")
        fill = out["migration_start_date"].isna() & value.notna()
        out.loc[fill, "migration_start_date"] = value[fill]
        out.loc[fill, "start_date_source"] = label
    return out[out["migration_start_date"].notna()].reset_index(drop=True)


def migration_end_dates(fact: pd.DataFrame,
                        lasts: pd.DataFrame | None = None) -> pd.DataFrame:
    """One row per TPID: the date its migration ended, and where that came from.

    The same two-source rule as :func:`migration_start_dates`.  **The manual EOS
    tracking sheet answers first**: an *Actual Migration End Date* in the sheet
    is the programme saying the migration ended, whatever state the nomination
    export was last left in.  Every other account falls back to the export's own
    rule — the account is **Completed** (:func:`account_state`) and is dated by
    its latest wave's *Actual End Date* — so an installation with no tracking
    sheet reports exactly what it reported before there was one.
    """
    if fact.empty:
        return fact
    done = migrations_completed(fact, None, None, lasts).records
    derived = pd.DataFrame()
    if not done.empty:
        derived = done.assign(
            migration_end_date=done["completion_date"],
            end_date_source=[FDO_END_SOURCE if src == "Actual End Date"
                             else f"{src} (latest wave, no Actual End Date)"
                             for src in done["end_date_source"]])
        derived = derived[derived["migration_end_date"].notna()]
    tracked = _tracked_dates(fact, "eos_end_date", "migration_end_date",
                             "end_date_source", TRACKER_END_SOURCE)
    return _prefer(tracked, derived, "migration_end_date")


def engagement_end_dates(fact: pd.DataFrame,
                         lasts: pd.DataFrame | None = None) -> pd.DataFrame:
    """One row per TPID: when its engagement ended, from the FDO export alone.

    The same rule the All AVS report uses for a completed migration: the account
    is **Completed** (:func:`account_state`) and is dated by its latest wave's
    **Actual End Date** — as the export records it, never the tracking sheet's
    Actual Migration End Date (that one dates *migration end*).  An account with
    no Actual End Date in the export has no engagement end to report.
    """
    if fact.empty:
        return fact
    done = migrations_completed(fact, None, None, lasts).records
    if done.empty:
        return done
    # The very date Migrations Completed is counted by, so the two reconcile.
    rows = done.assign(engagement_end_date=done["completion_date"])
    return rows[rows["engagement_end_date"].notna()].reset_index(drop=True)


def monthly_engagement_ends(fact: pd.DataFrame, start=None, end=None,
                            lasts: pd.DataFrame | None = None
                            ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Unique TPIDs per month by the export's engagement end (latest wave)."""
    return _monthly_by_date(engagement_end_dates(fact, lasts), "engagement_end_date",
                            "Engagements Ended", start, end)


def _tracked_dates(fact: pd.DataFrame, column: str, date_name: str,
                   source_name: str, label: str) -> pd.DataFrame:
    """One row per TPID the EOS tracking sheet dates, from its own column."""
    if column not in fact.columns:
        return pd.DataFrame()
    dates = pd.to_datetime(fact[column], errors="coerce")
    rows = fact[dates.notna()]
    if rows.empty:
        return pd.DataFrame()
    rows = latest_wave(rows)
    return rows.assign(**{date_name: pd.to_datetime(rows[column], errors="coerce"),
                          source_name: label}).reset_index(drop=True)


def _prefer(primary: pd.DataFrame, fallback: pd.DataFrame,
            date_name: str) -> pd.DataFrame:
    """*primary*'s row for every TPID it has, *fallback*'s for the rest."""
    if primary is None or primary.empty:
        return (fallback if fallback is not None and not fallback.empty
                else pd.DataFrame(columns=[date_name]))
    if fallback is None or fallback.empty:
        return primary.reset_index(drop=True)
    rest = fallback[~fallback["tpid_key"].isin(set(primary["tpid_key"]))]
    if rest.empty:
        return primary.reset_index(drop=True)
    return pd.concat([primary, rest], ignore_index=True)


def _started_state(df: pd.DataFrame) -> pd.Series:
    """Waves whose Current State says the work is under way or finished."""
    if df.empty or "current_state" not in df.columns:
        return pd.Series(False, index=df.index)
    return (df["current_state"].astype("string")
            .str.contains(_STARTED_STATE_PATTERN, case=False, regex=True, na=False))


def monthly_migration_starts(fact: pd.DataFrame, start=None, end=None
                             ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Unique TPIDs per month by their migration start date (tracker first)."""
    return _monthly_by_date(migration_start_dates(fact), "migration_start_date",
                            "Migration Starts", start, end)


def monthly_migration_ends(fact: pd.DataFrame, start=None, end=None,
                           lasts: pd.DataFrame | None = None
                           ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Unique TPIDs per month by their migration end date (tracker first).

    The programme matrix's *migration end* row.  It is deliberately **not**
    :func:`monthly_migrations_completed`: that one is the export's own measure,
    which the trends and the headline tiles report, and it stays exactly as it
    was.  This one lets the EOS tracking sheet's *Actual Migration End Date*
    answer where it has one, which is what the matrix is asked to show.
    """
    return _monthly_by_date(migration_end_dates(fact, lasts), "migration_end_date",
                            "Migrations Completed", start, end)


def _monthly_by_date(rows: pd.DataFrame, date_col: str, label: str,
                     start, end) -> tuple[pd.DataFrame, pd.DataFrame]:
    if rows is None or rows.empty or date_col not in rows.columns:
        return _empty_trend(label), (rows if rows is not None else pd.DataFrame())
    rows = rows[in_window(rows[date_col], start, end)].copy()
    if rows.empty:
        return _empty_trend(label), rows
    rows["month"] = _month(rows[date_col])
    summary = rows.groupby("month", as_index=False).agg(value=("tpid_key", "nunique"))
    return _finish_trend(summary, label), rows


def hosts_migrated(fact: pd.DataFrame, start=None, end=None) -> Metric:
    """Sum of Total Cores (nodes/hosts) over completed wave records in the period.

    Explicitly *not* a unique-TPID count: every qualifying wave record contributes
    its own hosts, and each source record is counted once.
    """
    if fact.empty:
        return Metric(0, "hosts")
    rows = _with_end_dates(fact[is_completed(fact)])
    rows = rows[in_window(rows["reported_end_date"], start, end)]
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
    rows = _with_end_dates(fact)
    rows = _dedupe_records(rows[in_window(rows["reported_end_date"], start, end)])
    total = float(pd.to_numeric(rows.get("total_acr"), errors="coerce").sum())
    return Metric(total, "ACR", rows)


def _with_end_dates(rows: pd.DataFrame) -> pd.DataFrame:
    """Waves carrying the date they are reported by (:func:`end_dates`): a
    completed wave falls back along :data:`END_DATE_CHAIN`; any other wave
    counts only on its own Actual End Date."""
    if rows.empty:
        return rows.assign(reported_end_date=pd.Series(dtype="datetime64[ns]"),
                           end_date_source=pd.Series(dtype="object"))
    dates, sources = end_dates(rows, is_completed(rows))
    return rows.assign(reported_end_date=dates, end_date_source=sources)


def on_track_accounts(fact: pd.DataFrame,
                      lasts: pd.DataFrame | None = None) -> Metric:
    """Accounts with **any** wave reading On-Track in the Current State column.

    Independent of the reporting period: this is where the pipeline stands now.
    The record behind each account is the *latest of its on-track waves* — the
    wave the work is actually happening on — so the drill-down shows the stage
    the account is in rather than a completed wave it has already left behind.
    """
    if fact.empty:
        return Metric(0, "customers")
    rows = on_track_wave(fact, lasts=lasts)
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
                         start=None, end=None, waves: "WaveIndex | None" = None
                         ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Unique TPIDs per month, each counted once in the month of its Wave-1 date.

    The same population :func:`new_engagements` counts: Wave-1's date whatever
    that wave's *Migration Status* or *Current State*, falling through to the
    next wave only when Wave-1 carries no date, and only where that wave's
    *Nomination Status* reads **Approved**.  Only the column placing an account
    in a month changes with ``date_col``.
    """
    if waves is not None and date_col == "approval_date":
        dated = waves.approval
    else:
        dated = dated_wave(fact, date_col) if not fact.empty else fact
    if dated.empty:
        return _empty_trend("Nominations"), dated
    # The same population :func:`new_engagements` counts, so the trend and the
    # tile above it cannot disagree — only the date placing each account in a
    # month changes with the basis.
    rows = dated[in_window(dated[date_col], start, end)
                 & is_nomination_approved(dated)].copy()
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
    rows["month"] = _month(rows["reported_end_date"])
    rows["_acr"] = pd.to_numeric(rows.get("total_acr"), errors="coerce")
    summary = rows.groupby("month", as_index=False).agg(value=("_acr", "sum"))
    return _finish_trend(summary, "ACR Claimed"), rows


def monthly_hosts(fact: pd.DataFrame, start=None, end=None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Hosts (Total Cores) completed per month, by actual end date."""
    if fact.empty:
        return _empty_trend("Hosts"), fact
    rows = _dedupe_records(_with_end_dates(fact[is_completed(fact)]))
    rows = rows[in_window(rows["reported_end_date"], start, end)].copy()
    if rows.empty:
        return _empty_trend("Hosts"), rows
    rows["month"] = _month(rows["reported_end_date"])
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
    rows["month"] = _month(rows["completion_date"])
    summary = rows.groupby("month", as_index=False).agg(value=("tpid_key", "nunique"))
    return _finish_trend(summary, "Migrations Completed"), rows


# --------------------------------------------------------------------------- #
# Monthly matrix (the EOS programme's month-by-month grid)
# --------------------------------------------------------------------------- #
#: The rows of the matrix, in the order the programme reports them.
MATRIX_ROWS: tuple[str, ...] = (
    "Total number of new engagement",
    "Total number of migration start",
    "Total number of migration end",
    "Total number of engagement end",
    "Number of hosts migrated",
)

#: Rows that repeat another row.  None any more: *engagement end* used to
#: repeat *migration end*, but migration end now takes the EOS tracking sheet's
#: date where it has one, while engagement end is always the export's own —
#: the latest wave's Actual End Date on a completed account
#: (:func:`engagement_end_dates`).  With no sheet the two rows still agree.
MATRIX_ROWS_MIRRORED: dict[str, str] = {}

#: Rows with no answer at all — none, now that engagement end mirrors migration
#: end and migration start is derived (see ``migration_start_dates``).
MATRIX_ROWS_UNAVAILABLE: frozenset[str] = frozenset()

#: How a month is labelled across the top ("Jul-25").
MATRIX_MONTH_FORMAT = "%b-%y"


def month_span(start, end) -> list[pd.Period]:
    """Every calendar month from *start* to *end* inclusive, gaps included.

    The matrix shows a column for a month with nothing in it — an empty month is
    the finding, and a grid that silently skips one cannot be read across.
    """
    first = pd.Period(pd.Timestamp(start), freq="M")
    last = pd.Period(pd.Timestamp(end), freq="M")
    if last < first:
        last = first
    return list(pd.period_range(first, last, freq="M"))


def matrix_month_span(fact: pd.DataFrame, start, as_of=None) -> list[pd.Period]:
    """The months a matrix over *fact* should cover: *start* → the last of use.

    Runs to whichever is later, the as-of month or the latest month any of the
    matrix's own dates reaches, so the grid never stops before today and never
    hides a completion dated ahead of it.
    """
    end = pd.Period(pd.Timestamp(as_of if as_of is not None else pd.Timestamp.today()),
                    freq="M")
    for col in ("approval_date", "actual_end_date", "eos_end_date",
                "eos_start_date"):
        if col in fact.columns:
            months = _month(fact[col]).dropna()
            if not months.empty and months.max() > end:
                end = months.max()
    return month_span(start, end.to_timestamp())


def monthly_matrix(fact: pd.DataFrame, months: list[pd.Period],
                   waves: "WaveIndex | None" = None,
                   fy_start_month: int = 7) -> pd.DataFrame:
    """The five programme measures as rows, one column per month plus FY totals.

    Every number comes from the same functions the dashboards and trends use —
    new engagements from Wave-1 approval dates, hosts from Total Cores over
    completed records — so the grid reconciles with the rest of the report by
    construction.  Each fiscal year closes with its own total column.

    The two date rows are the programme's own: **migration start** and
    **migration end** take the manual EOS tracking sheet's *Migration Start
    Date* and *Actual Migration End Date* for every account it covers, and fall
    back to the export's derivation for the rest
    (:func:`migration_start_dates`, :func:`migration_end_dates`).  With no
    tracking sheet loaded the fallbacks are all there is, and the grid reads
    exactly as it did before the sheet existed.
    """
    if waves is None:
        waves = wave_index(fact)

    engagements, _ = monthly_unique_tpids(fact, "approval_date", waves=waves)
    starts, _ = monthly_migration_starts(fact)
    ends, _ = monthly_migration_ends(fact, lasts=waves.last)
    closed, _ = monthly_engagement_ends(fact, lasts=waves.last)
    hosts, _ = monthly_hosts(fact)
    by_row = {
        "Total number of new engagement": _by_period(engagements, "Nominations"),
        "Total number of migration start": _by_period(starts, "Migration Starts"),
        "Total number of migration end": _by_period(ends, "Migrations Completed"),
        "Total number of engagement end": _by_period(closed, "Engagements Ended"),
        "Number of hosts migrated": _by_period(hosts, "Hosts"),
    }

    data = {}
    for label in MATRIX_ROWS:
        if label in MATRIX_ROWS_UNAVAILABLE:
            data[label] = [None] * len(months)
            continue
        counts = by_row.get(MATRIX_ROWS_MIRRORED.get(label, label), {})
        data[label] = [float(counts.get(str(m), 0)) for m in months]
    return _matrix_frame(data, months, fy_start_month)


def _matrix_frame(data: dict[str, list], months: list[pd.Period],
                  fy_start_month: int) -> pd.DataFrame:
    """Lay the measures out as rows, with a total column closing each fiscal year.

    The totals sit *inside* the month sequence rather than all at the end, so
    each fiscal year reads as its own block: Jul → Jun, then that year's total,
    then the next year.  Every measure is a per-month count of distinct things
    (a TPID lands in exactly one month; cores are summed), so a year's total is
    simply the sum of its months.
    """
    labels = [m.strftime(MATRIX_MONTH_FORMAT) for m in months]
    fy = [metrics.fiscal_year_label(m.to_timestamp(), fy_start_month) for m in months]

    columns: list[str] = []
    values: dict[str, list] = {label: [] for label in data}
    for index, (month_label, year) in enumerate(zip(labels, fy)):
        columns.append(month_label)
        for label, series in data.items():
            values[label].append(series[index])
        closes_year = index == len(months) - 1 or fy[index + 1] != year
        if not closes_year:
            continue
        columns.append(f"{year} Total")
        for label, series in data.items():
            spans = [series[i] for i, y in enumerate(fy) if y == year]
            total = None if any(v is None for v in spans) else sum(spans)
            values[label].append(total)

    out = pd.DataFrame(
        [[_matrix_cell(v) for v in values[label]] for label in data], columns=columns)
    out.insert(0, "Measure", list(data))
    return out


def _matrix_cell(value) -> str:
    """A matrix cell: a thousands-separated integer, or blank for "not known"."""
    return "" if value is None else f"{int(round(value)):,}"


def _by_period(table: pd.DataFrame, value_col: str) -> dict[str, float]:
    """A monthly trend table as {"2025-07": value}."""
    if table.empty or value_col not in table.columns:
        return {}
    return {str(p): v for p, v in zip(table["period"], table[value_col])}


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
    return statuses.is_class(df, statuses.IN_FLIGHT)


def reported_stages(df: pd.DataFrame) -> pd.Series:
    """Rows sitting in one of the migration stages the reports break down by.

    The six stages worth a regional cut are the four in-flight ones —
    "1 - Validating Commitment & Initial Scope", "2 - Executing
    Pre-Requisites", "3 - Finalize Scope", "4 - Executing Migration" — plus
    "7 - Completed".  Deferred ("5") and Cancelled / Archived ("6") are not
    stages a migration is progressing through, so they are left out rather than
    padding every chart with work nobody is doing.
    """
    if df.empty:
        return pd.Series(dtype=bool)
    return (in_flight(df) | is_completed(df)).fillna(False)


def is_on_track_wave(df: pd.DataFrame) -> pd.Series:
    """Per **wave**: is this wave on track right now?

    All three have to hold::

        Nomination Status  =   "Approved"
        Migration Status   IN  (1, 2, 3, 4)        -- in flight
        Current State      =   "On Track"          -- and nothing else

    An unapproved nomination is not on track however it is progressing: nothing
    has been committed to yet.  A completed, deferred or cancelled wave is not
    on track whatever its Current State says.  **A blank Current State is not
    on track either**: the column is how the programme says an engagement is
    moving, and a wave nobody has said that about is ignored rather than
    counted — it lands in *Other*, so no On-Track number rests on an empty cell.

    The state match is exact once punctuation and case are normalised, so "On
    Track", "On-Track" and "on  track" are the same state and "On Track - at
    risk" is not.
    """
    if df.empty:
        return pd.Series(dtype=bool)
    return (is_nomination_approved(df)
            & in_flight(df)
            & _is_state(df, ON_TRACK_STATE)).fillna(False)


def _current_state(df: pd.DataFrame) -> pd.Series:
    if "current_state" not in df.columns:
        return pd.Series(pd.NA, index=df.index, dtype="string")
    return df["current_state"].astype("string").str.strip()


def is_blocked(df: pd.DataFrame) -> pd.Series:
    """Current State says the work is blocked ("Blocked - Customer")."""
    if df.empty:
        return pd.Series(dtype=bool)
    return _current_state(df).str.contains("blocked", case=False, na=False).fillna(False)


def account_acr(fact: pd.DataFrame) -> pd.Series:
    """**Total ACR** per account (indexed by ``tpid_key``): summed across every
    wave **except those whose Current State is Blocked** — money held up behind
    a blocked wave is not money the account is bringing in.  NaN for an account
    with no ACR on any counted wave."""
    if fact.empty:
        return pd.Series(dtype="float64")
    acr = pd.to_numeric(fact.get("total_acr"), errors="coerce")
    acr = acr.where(~is_blocked(fact).to_numpy())
    return acr.groupby(_keys(fact).to_numpy()).sum(min_count=1)


def held_up_acr(fact: pd.DataFrame) -> pd.Series:
    """ACR per account across **every** wave, blocked ones included — what a
    stopped account holds up, for the blocked, deferred & cancelled section."""
    if fact.empty:
        return pd.Series(dtype="float64")
    acr = pd.to_numeric(fact.get("total_acr"), errors="coerce")
    return acr.groupby(_keys(fact).to_numpy()).sum(min_count=1)


def _state_key(values: pd.Series) -> pd.Series:
    """A Current State value reduced to what identifies it.

    Lower-cased, with every run of non-alphanumerics collapsed to one space, so
    "Blocked - Partner / ISD", "blocked – partner/isd" and "Blocked  Partner
    ISD" are one state rather than three.
    """
    return (values.astype("string").str.lower()
            .str.replace(r"[^a-z0-9]+", " ", regex=True).str.strip())


#: The blocking vocabulary, keyed for matching.
_BLOCKED_KEYS = {k: label for k, label in
                 zip(_state_key(pd.Series(list(BLOCKED_STATES))), BLOCKED_STATES)}


#: The one Current State that means "this wave is moving".
ON_TRACK_STATE = "On Track"


def _is_state(df: pd.DataFrame, *states: str) -> pd.Series:
    """Rows whose Current State is exactly one of *states*, punctuation aside."""
    if df.empty:
        return pd.Series(dtype=bool)
    wanted = {_state_key(pd.Series([s]))[0] for s in states}
    return _state_key(_current_state(df)).isin(wanted).fillna(False)


def is_blocking_state(df: pd.DataFrame) -> pd.Series:
    """Rows whose Current State is one of :data:`BLOCKED_STATES`."""
    if df.empty:
        return pd.Series(dtype=bool)
    return _state_key(_current_state(df)).isin(_BLOCKED_KEYS).fillna(False)


def is_deferred(df: pd.DataFrame) -> pd.Series:
    """Migration Status is "5 - Deferred by Customer" (by code, or by label)."""
    return statuses.is_class(df, statuses.DEFERRED)


def is_on_hold(df: pd.DataFrame) -> pd.Series:
    """Migration Status is the tracking sheet's "On Hold"."""
    return statuses.is_class(df, statuses.ON_HOLD)


def is_cancelled(df: pd.DataFrame) -> pd.Series:
    """Migration Status is "6 - Cancelled / Archived" (by code, label or status)."""
    if df.empty:
        return pd.Series(dtype=bool)
    out = statuses.is_class(df, statuses.CANCELLED)
    if "eos_status" in df.columns:
        out = out | df["eos_status"].eq(STATE_CANCELLED)
    return out.fillna(False)


def _keys(df: pd.DataFrame) -> pd.Series:
    return df["tpid_key"] if "tpid_key" in df.columns else segments.tpid_key(df)


def account_state(fact: pd.DataFrame,
                  lasts: pd.DataFrame | None = None) -> pd.Series:
    """The state of each **account**, aligned to the one-row-per-TPID *lasts*.

    Read across every wave the account owns, not just its last one — which is
    what separates an account that has finished from one whose final wave
    happens to be finished:

    1. **On-Track** — **any** wave of the account is on track
       (:func:`is_on_track_wave`).  This wins over everything else: an account
       with Wave 7 completed and Wave 8 on track is still delivering, and so is
       one whose *latest* wave completed while an earlier wave runs on.
    2. **Completed** — the latest wave is ``7 - Completed`` **and** no wave is
       on track.  Both conditions, never one.
    3. **Cancelled** — the latest wave resolved to cancelled / archived.
    4. **Blocked** — the latest wave's Current State reads *Blocked*.
    5. **Deferred** — the latest wave is ``5 - Deferred by Customer``.
    6. **Other** — everything else: waiting on a follow-up, or a state the
       export does not name.

    Every account resolves to exactly one state, so the reported cut
    (On-Track + Completed) and the excluded cut (:data:`EXCLUDED_STATES`)
    partition the population with nothing double-counted and nothing lost.
    """
    lasts = latest_wave(fact) if lasts is None else lasts
    if lasts.empty:
        return pd.Series(dtype="object")
    on_track_by_account = (is_on_track_wave(fact).groupby(_keys(fact)).any()
                           if not fact.empty else pd.Series(dtype=bool))
    any_on_track = (_keys(lasts).map(on_track_by_account)
                    .fillna(False).astype(bool))

    # Assigned in reverse precedence: each line overrides the ones above it.
    out = pd.Series(STATE_OTHER, index=lasts.index, dtype="object")
    out[is_deferred(lasts)] = STATE_DEFERRED
    out[is_on_hold(lasts)] = STATE_ON_HOLD
    out[is_blocked(lasts)] = STATE_BLOCKED
    out[is_cancelled(lasts)] = STATE_CANCELLED
    out[is_completed(lasts)] = STATE_COMPLETED
    out[any_on_track.to_numpy()] = STATE_ON_TRACK
    # Where the EOS tracking sheet states the account's status or state, it
    # decides — whatever the export's waves say.
    stated = tracker_account_state(lasts)
    return out.where(stated.isna(), stated)


def tracker_account_state(lasts: pd.DataFrame) -> pd.Series:
    """The account state the EOS tracking sheet gives, or NA where it is silent.

    Read from the sheet's **Migration Status** and **Current State**, the first
    of these to hold deciding:

    1. **Cancelled** — Migration Status "Cancelled".
    2. **On Hold** — Migration Status "On Hold".
    3. **Completed** — Migration Status "Completed", or Current State
       "Completed".
    4. **Blocked** — Current State "Blocked".
    5. **On-Track** — Current State "On Track" with the migration in flight
       (stages 1-5) or no stage stated.
    6. **Other** — anything else the sheet states (a stage with no state).

    An account the sheet does not cover, or covers with neither column filled
    in, comes back NA and keeps the export's answer.
    """
    out = pd.Series(pd.NA, index=lasts.index, dtype="object")
    if lasts.empty or "eos_status_class" not in lasts.columns:
        return out
    cls = lasts["eos_status_class"].astype("string")
    state = (lasts["eos_tracker_state"].astype("string")
             if "eos_tracker_state" in lasts.columns
             else pd.Series(pd.NA, index=lasts.index, dtype="string"))
    stated = (cls.notna() | state.notna()).to_numpy()
    out[stated] = STATE_OTHER
    moving = (cls.isna() | cls.eq(statuses.IN_FLIGHT)).fillna(False)
    out[(state.eq("On Track").fillna(False) & moving).to_numpy()] = STATE_ON_TRACK
    out[state.eq("Blocked").fillna(False).to_numpy()] = STATE_BLOCKED
    out[(cls.eq(statuses.COMPLETED) | state.eq("Completed")).fillna(False).to_numpy()] \
        = STATE_COMPLETED
    out[cls.eq(statuses.ON_HOLD).fillna(False).to_numpy()] = STATE_ON_HOLD
    out[cls.eq(statuses.CANCELLED).fillna(False).to_numpy()] = STATE_CANCELLED
    return out


def state_of(df: pd.DataFrame) -> pd.Series:
    """The state of a frame read **on its own rows**, with no cross-wave view.

    Kept for callers holding a single frame (a wave-level status distribution,
    say).  Anything reporting an *account* uses :func:`account_state` instead,
    because "is any other wave of this account on track" cannot be answered from
    one row.  The taxonomy is the same: Completed → Cancelled → Blocked →
    Deferred → On-Track → Other.
    """
    if df.empty:
        return pd.Series(dtype="object")
    out = pd.Series(STATE_OTHER, index=df.index, dtype="object")
    out[is_deferred(df)] = STATE_DEFERRED
    out[is_on_hold(df)] = STATE_ON_HOLD
    out[is_blocked(df)] = STATE_BLOCKED
    out[is_on_track_wave(df)] = STATE_ON_TRACK
    out[is_cancelled(df)] = STATE_CANCELLED
    out[is_completed(df)] = STATE_COMPLETED
    return out


def on_track_wave(fact: pd.DataFrame,
                  lasts: pd.DataFrame | None = None) -> pd.DataFrame:
    """One row per on-track account: the **latest of its on-track waves**.

    Not the account's latest wave — an account can be on track on Wave 8 while
    Wave 9 is a completed follow-up — so the row shows the wave the work is
    actually on, and with it the stage that wave has reached.
    """
    if fact.empty:
        return fact
    # Select first, then sort: only the on-track waves need ordering, and
    # sorting the whole population to throw most of it away costs half a second
    # on a 100k-wave portfolio.
    rows = fact[is_on_track_wave(fact)]
    picked = (_ordered(rows).groupby("tpid_key", as_index=False, sort=False).last()
              if not rows.empty else rows)
    # The tracking sheet can put an account on track with no wave the export
    # would call on track (its nomination still unapproved, say); the account
    # is still on track, and its latest wave is the row that says where.
    lasts = latest_wave(fact) if lasts is None else lasts
    stated = tracker_account_state(lasts)
    keys = _keys(lasts)
    on = set(keys[stated.eq(STATE_ON_TRACK).fillna(False).to_numpy()])
    off = set(keys[(stated.notna() & stated.ne(STATE_ON_TRACK)).fillna(False).to_numpy()])
    if not picked.empty and off:
        picked = picked[~picked["tpid_key"].isin(off)]
    have = set(picked["tpid_key"]) if not picked.empty else set()
    extra = lasts[keys.isin(on - have).to_numpy()]
    if extra.empty:
        return picked
    if picked.empty:
        return extra.reset_index(drop=True)
    return pd.concat([picked, extra], ignore_index=True)


def stage_labels(df: pd.DataFrame) -> tuple[pd.Series, list[tuple[str, str]]]:
    """Short axis labels ("Stage 4") and the legend that decodes them.

    The migration statuses are long — "Validating Commitment & Initial Scope" is
    36 characters — and five of them on one axis leave the plot itself a sliver.
    The Migration Status column already numbers them ("4 - Executing Migration"),
    so the axis carries the number and the full name moves to a legend beneath.

    Returns ``(labels, legend)`` where legend is ``[("Stage 4", "Executing
    Migration"), …]`` ordered by code.  A row with no code keeps its full label,
    so nothing is hidden behind a number that has no key.
    """
    if df.empty:
        return pd.Series(dtype="object"), []
    code = pd.to_numeric(df.get("migration_status_code"), errors="coerce")
    full = (df.get("migration_status_label", pd.Series("", index=df.index))
            .astype("string").replace({"": pd.NA}).fillna("Unknown"))
    # A stage the tracking sheet supplied has no code (its values carry no
    # number), so it keeps its own wording on the axis: "Executing Migration".
    short = pd.Series(
        [f"Stage {int(c)}" if pd.notna(c) else f for c, f in zip(code, full)],
        index=df.index, dtype="object")
    pairs = {}
    for c, sh, fu in zip(code, short, full):
        if pd.notna(c) and sh not in pairs:
            pairs[sh] = (int(c), str(fu))
    legend = [(sh, name) for sh, (_c, name) in
              sorted(pairs.items(), key=lambda kv: kv[1][0])]
    return short, legend


def by_state(fact: pd.DataFrame, lasts: pd.DataFrame | None = None,
             only: tuple[str, ...] | None = REPORTED_STATES
             ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Account count and ACR by current state, one row per TPID.

    The state is :func:`account_state` — read across every wave — while the row
    behind it stays the account's latest wave, which is the row that says where
    the account is now.  ``only`` restricts both the summary and the drill-down
    rows to the states worth reporting — On-Track and Completed — so cancelled,
    blocked and waiting accounts do not pad the chart; they are reported on
    their own through :func:`excluded_accounts`.  Pass ``only=None`` for every
    state.
    """
    if lasts is None:
        lasts = latest_wave(fact) if not fact.empty else fact
    if lasts.empty:
        return pd.DataFrame(columns=["category", "count", "acr"]), lasts
    rows = lasts.copy()
    rows["state"] = account_state(fact, lasts)
    if only:
        rows = rows[rows["state"].isin(only)]
    if rows.empty:
        return pd.DataFrame(columns=["category", "count", "acr"]), rows
    rows["total_acr"] = rows["tpid_key"].map(account_acr(fact)).to_numpy()
    rows["_acr"] = pd.to_numeric(rows["total_acr"], errors="coerce")
    summary = (rows.groupby("state", as_index=False)
                   .agg(count=("tpid_key", "nunique"), acr=("_acr", "sum"))
                   .rename(columns={"state": "category"})
                   .sort_values("count", ascending=False))
    return summary.reset_index(drop=True), rows


#: How many accounts the "largest by ACR" cut shows.  Ten is the number a
#: review reads off a slide: enough to see the shape of the concentration,
#: short enough that every bar keeps a legible label.
TOP_ACCOUNTS = 10


def top_accounts_by_acr(fact: pd.DataFrame, limit: int = TOP_ACCOUNTS,
                        approvals: pd.DataFrame | None = None,
                        lasts: pd.DataFrame | None = None
                        ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """The largest accounts by ACR, and the account rows behind them.

    ACR is summed across **every wave** of an account, which is the account-level
    figure :func:`account_detail` reports and the one the reconciliation adds up
    — an account that claimed 10M, 15M and 20M over three waves is a 45M
    account, and ranking it on its latest wave's 20M would put it in the wrong
    place in the order.

    Accounts with no ACR at all are left out rather than listed as zeroes: the
    question is which accounts the money is in, and a row of zeroes answers a
    different one.  Returns ``(summary, rows)`` — ``category``/``acr``/``count``
    for the chart, and one full account row each for the table beneath it.
    """
    if fact.empty:
        return pd.DataFrame(columns=["category", "acr", "count"]), fact
    detail = account_detail(fact, approvals=approvals, lasts=lasts)
    if detail.empty:
        return pd.DataFrame(columns=["category", "acr", "count"]), detail
    rows = detail.copy()
    rows["_acr"] = pd.to_numeric(rows.get("total_acr"), errors="coerce").fillna(0.0)
    rows = rows[rows["_acr"] > 0]
    if rows.empty:
        return pd.DataFrame(columns=["category", "acr", "count"]), rows
    rows = rows.sort_values("_acr", ascending=False).head(int(limit))
    rows["account_label"] = _account_labels(rows)
    waves = fact.groupby("tpid_key").size()
    rows["_waves"] = rows["tpid_key"].map(waves).fillna(1)
    summary = pd.DataFrame({
        "category": rows["account_label"].to_numpy(),
        "acr": rows["_acr"].to_numpy(),
        "count": rows["_waves"].astype("int64").to_numpy(),
    })
    return summary.reset_index(drop=True), rows.reset_index(drop=True)


def _account_labels(rows: pd.DataFrame) -> pd.Series:
    """A label per account that no two accounts can share.

    Customer names repeat between subsidiaries and arrive spelled differently
    between worksheets, so the label carries the TPID — which is what the whole
    application matches on — and a chart bar therefore names exactly one
    account.
    """
    names = rows["customer_name"].astype("string").str.strip().replace({"": pd.NA})
    tpids = rows["tpid"].astype("string").str.strip().replace({"": pd.NA})
    names = names.fillna("Unknown")
    return pd.Series(
        [name if pd.isna(tpid) else f"{name} ({tpid})"
         for name, tpid in zip(names, tpids)], index=rows.index, dtype="object")


def on_track_by_stage(fact: pd.DataFrame,
                      lasts: pd.DataFrame | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """On-track accounts grouped by the stage of their on-track wave, with ACR."""
    rows = on_track_wave(fact, lasts=lasts)
    if rows is None or rows.empty:
        return pd.DataFrame(columns=["category", "count", "acr"]), (
            rows if rows is not None else pd.DataFrame())
    rows = rows.copy()
    rows["stage"] = (rows["migration_status_label"].astype("string")
                     .replace({"": pd.NA}).fillna("Unknown"))
    rows["_acr"] = pd.to_numeric(rows.get("total_acr"), errors="coerce")
    summary = (rows.groupby("stage", as_index=False)
                   .agg(count=("tpid_key", "nunique"), acr=("_acr", "sum"))
                   .rename(columns={"stage": "category"})
                   .sort_values("count", ascending=False))
    return summary.reset_index(drop=True), rows


# --------------------------------------------------------------------------- #
# Accounts the primary reports leave out
# --------------------------------------------------------------------------- #
def excluded_accounts(fact: pd.DataFrame, lasts: pd.DataFrame | None = None
                      ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Accounts in none of the reported states, summarised and with their rows.

    The complement of :func:`by_state`: every account whose
    :func:`account_state` is blocked, deferred, cancelled/archived or otherwise
    unreported.  Kept apart from the On-Track/Completed numbers on purpose —
    these accounts are not delivering and not delivered, and folding them in
    would overstate both — but kept *visible*, because an account nobody is
    working on is exactly the one a programme review needs to see.

    Returns ``(summary, rows)`` where summary is state × accounts × ACR and rows
    are the accounts' latest waves carrying a ``state`` column.
    """
    if lasts is None:
        lasts = latest_wave(fact) if not fact.empty else fact
    if lasts.empty:
        return pd.DataFrame(columns=["category", "count", "acr"]), lasts
    rows = lasts.copy()
    rows["state"] = account_state(fact, lasts)
    rows = rows[rows["state"].isin(EXCLUDED_STATES)]
    if rows.empty:
        return pd.DataFrame(columns=["category", "count", "acr"]), rows
    rows["total_acr"] = rows["tpid_key"].map(held_up_acr(fact)).to_numpy()
    rows["_acr"] = pd.to_numeric(rows["total_acr"], errors="coerce")
    summary = (rows.groupby("state", as_index=False)
                   .agg(count=("tpid_key", "nunique"), acr=("_acr", "sum"))
                   .rename(columns={"state": "category"})
                   .sort_values("count", ascending=False))
    return summary.reset_index(drop=True), rows


#: How a stopped account is labelled when the Current State is not one of the
#: stated blocking values: by the Migration Status that took it out.
DEFERRED_LABEL = "Deferred By Customer"
ON_HOLD_LABEL = "On Hold"
CANCELLED_LABEL = "Cancelled / Archived"
UNSTATED_LABEL = "Not stated"


def blocked_state_label(rows: pd.DataFrame) -> pd.Series:
    """Why each stopped account is stopped, in one label, first match winning::

        "Cancelled / Archived"   ← Migration Status = "6 - Cancelled / Archived"
                                   (or the tracking sheet's "Cancelled")
        "On Hold"                ← the tracking sheet's "On Hold"
        "Deferred By Customer"   ← Migration Status = "5 - Deferred By Customer"
        one of BLOCKED_STATES    ← Current State says so, in its canonical spelling
        "Not approved"           ← Nomination Status is not "Approved"
        "Not stated"             ← Current State is blank or unmapped
        the Current State itself ← anything else the file says

    The two Migration Statuses come **first on purpose**: they are decisions the
    customer has taken, and an account deferred while its Current State still
    reads "Blocked - Customer" is deferred.  Nothing is inferred — an account
    with nothing recorded reads *Not stated* rather than being given a reason.
    """
    if rows.empty:
        return pd.Series(dtype="object")
    current = _current_state(rows).replace({"": pd.NA})
    # Categoricals are filled with "Unknown" as the file is read; that is the
    # absence of a state, not a state.
    current = current.mask(current.str.casefold().eq("unknown"))
    canonical = _state_key(current).map(_BLOCKED_KEYS)

    out = canonical.fillna(current).astype("object")
    unapproved = ~is_nomination_approved(rows) & canonical.isna()
    out[unapproved.to_numpy()] = "Not approved"
    out = pd.Series(out, index=rows.index).fillna(UNSTATED_LABEL)
    out[is_deferred(rows).to_numpy()] = DEFERRED_LABEL
    out[is_on_hold(rows).to_numpy()] = ON_HOLD_LABEL
    out[is_cancelled(rows).to_numpy()] = CANCELLED_LABEL
    return out


def blocked_accounts(fact: pd.DataFrame, lasts: pd.DataFrame | None = None
                     ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Every account that is neither On-Track nor Completed, and why.

    The complement of :func:`by_state`, and the section the reports show: an
    account is here when its :func:`account_state` is one of
    :data:`EXCLUDED_STATES` — blocked, waiting, deferred, cancelled or a state
    nobody has recorded.  Nothing here is counted in a headline metric above it,
    and nothing above it is counted here, so the two cuts partition the
    population and the reports reconcile.

    The breakdown is **why** each account has stopped
    (:func:`blocked_state_label`): the blocking Current States as the programme
    words them, with *Deferred By Customer* and *Cancelled / Archived* broken
    out by Migration Status, since those are decisions rather than blockages
    and a review reads them differently.

    Returns ``(summary, rows)`` where summary is reason × accounts × ACR and
    rows are the accounts' latest waves carrying ``state`` (the derived account
    state) and ``blocked_state`` (the reason).
    """
    empty = pd.DataFrame(columns=["category", "count", "acr"])
    if lasts is None:
        lasts = latest_wave(fact) if not fact.empty else fact
    if lasts.empty:
        return empty, lasts
    rows = lasts.copy()
    rows["state"] = account_state(fact, lasts)
    rows = rows[rows["state"].isin(EXCLUDED_STATES)]
    if rows.empty:
        return empty, rows
    rows["blocked_state"] = blocked_state_label(rows)
    rows["total_acr"] = rows["tpid_key"].map(held_up_acr(fact)).to_numpy()
    rows["_acr"] = pd.to_numeric(rows["total_acr"], errors="coerce")
    summary = (rows.groupby("blocked_state", as_index=False)
                   .agg(count=("tpid_key", "nunique"), acr=("_acr", "sum"))
                   .rename(columns={"blocked_state": "category"})
                   .sort_values("count", ascending=False))
    return summary.reset_index(drop=True), rows


def wave_profile(fact: pd.DataFrame, rows: pd.DataFrame) -> pd.DataFrame:
    """How many waves the given accounts carry — 1 wave, 2 waves, 3+.

    A blocked account on its fifth wave is a different problem from one blocked
    on its first, so the section reports the shape of the work behind it.
    """
    if fact.empty or rows is None or rows.empty:
        return pd.DataFrame(columns=["category", "count"])
    counts = fact.groupby(_keys(fact)).size()
    waves = _keys(rows).map(counts).fillna(1).astype(int)
    buckets = waves.map(lambda n: f"{n} wave" if n == 1 else
                        (f"{n} waves" if n < 3 else "3+ waves"))
    order = {"1 wave": 0, "2 waves": 1, "3+ waves": 2}
    out = (buckets.value_counts().rename_axis("category").reset_index(name="count"))
    return out.sort_values("category", key=lambda c: c.map(order).fillna(9)
                           ).reset_index(drop=True)


# --------------------------------------------------------------------------- #
# Pipeline ahead: the waves still to deliver
# --------------------------------------------------------------------------- #
#: The Factory Offering that *is* the AVS onboarding motion.  Pipeline is
#: counted over that offering's waves only — the other offerings on an AVS
#: account (SQL, Windows, Linux, OSS DB) are different factories' work.
PIPELINE_OFFERING = "AVS Migration Nominations"

#: What a migration path says when the wave is leaving AVS for Azure-native
#: services — the AVS → Azure Native motion's own pipeline scope.
PIPELINE_FROM_AVS = "from avs"

#: Migration Statuses that take a wave out of the forward pipeline.
PIPELINE_EXCLUDED_STATUSES = ("5 - Deferred By Customer", "6 - Cancelled / Archived",
                              "On Hold", "Cancelled")
PIPELINE_EXCLUDED_CODES = (DEFERRED_CODE, CANCELLED_CODE)


#: Which motion a pipeline figure is read for.
MOTION_AVS = "avs"          # All AVS Migrations and every EOS report
MOTION_NATIVE = "native"    # AVS → Azure Native, and nothing else


def mentions_from_avs(fact: pd.DataFrame) -> pd.Series:
    """Waves whose **Primary Migration Path** says "From AVS".

    The path and nothing else: "From AVS" is never written in an offering
    name.  It belongs to AVS → Azure Native and to nothing else, so the AVS
    and EOS figures leave such a wave out.
    """
    if fact.empty or "migration_path" not in fact.columns:
        return pd.Series(False, index=fact.index, dtype=bool)
    return (fact["migration_path"].astype("string")
            .str.contains(PIPELINE_FROM_AVS, case=False, na=False)
            .fillna(False).astype(bool))


def in_pipeline_scope(fact: pd.DataFrame, motion: str | None = None) -> pd.Series:
    """Waves the pipeline is counted over, by motion::

        AVS and EOS reports      Factory Offering = "AVS Migration Nominations"
                                 and no "From AVS" in the path
        AVS → Azure Native       Primary Migration Path contains "From AVS"

    ``motion`` names the report (:data:`MOTION_AVS` / :data:`MOTION_NATIVE`);
    left None, a mixed frame is read as the union of the two, each motion by its
    own rule — which is what the insights, run over the whole file, want.
    """
    if fact.empty:
        return pd.Series(dtype=bool)
    offering = (fact["factory_offering"].astype("string").str.strip()
                if "factory_offering" in fact.columns
                else pd.Series(pd.NA, index=fact.index, dtype="string"))
    path = (fact["migration_path"].astype("string")
            if "migration_path" in fact.columns
            else pd.Series(pd.NA, index=fact.index, dtype="string"))
    leaving = mentions_from_avs(fact)
    is_avs_motion = (offering.str.casefold().eq(PIPELINE_OFFERING.casefold())
                     .fillna(False).astype(bool) & ~leaving)
    native = path.str.contains(PIPELINE_FROM_AVS, case=False, na=False).fillna(False)
    if motion == MOTION_AVS:
        return is_avs_motion
    if motion == MOTION_NATIVE:
        return native.astype(bool)
    return (is_avs_motion | native).astype(bool)


def is_nomination_approved(df: pd.DataFrame) -> pd.Series:
    """``Nomination Status = "Approved"`` — the column, not an inference.

    Deliberately stricter than ``is_approved`` (which also accepts an approval
    *date* on a nomination whose status never said so): the pipeline is defined
    on the status column, so that is what it reads.
    """
    if df.empty:
        return pd.Series(dtype=bool)
    status = (df["nomination_status"].astype("string").str.strip()
              if "nomination_status" in df.columns
              else pd.Series(pd.NA, index=df.index, dtype="string"))
    return status.str.casefold().eq("approved").fillna(False)


def eligible_pipeline_waves(fact: pd.DataFrame, motion: str | None = None) -> pd.Series:
    """The waves the forward pipeline is counted over.

    A wave counts when **all four** hold::

        1. Factory Offering       =        "AVS Migration Nominations"   -- AVS + EOS reports
           Primary Migration Path CONTAINS "From AVS"                    -- AVS → Azure Native
        2. Nomination Status      =        "Approved"
        3. Current State          =        "On Track"                    -- and nothing else
        4. Migration Status       NOT IN   ("5 - Deferred By Customer",
                                            "6 - Cancelled / Archived",
                                            "On Hold", "Cancelled")

    For an account the EOS tracking sheet covers, the wave's Current State and
    Migration Status are the sheet's (see
    :func:`app.core.eos_tracker.apply_status`).

    Judged **per wave**, on the wave's own columns.  Any one failure drops it,
    so nothing blocked, waiting, deferred, cancelled or unapproved is ever
    counted as pipeline — and neither is a wave on an offering this motion does
    not deliver.
    """
    if fact.empty:
        return pd.Series(dtype=bool)
    excluded = statuses.is_class(fact, *statuses.STOPPED) | is_cancelled(fact)
    return (in_pipeline_scope(fact, motion)
            & is_nomination_approved(fact)
            & _is_state(fact, ON_TRACK_STATE)
            & ~excluded).fillna(False)


def acr_pipeline(fact: pd.DataFrame, motion: str | None = None) -> Metric:
    """ACR carried by every eligible wave — the commercial value still to land.

    Wave-level by construction (see :func:`eligible_pipeline_waves`), and not
    period-bound: this is what the approved, unblocked, unfinished work is
    worth as things stand.
    """
    if fact.empty:
        return Metric(0.0, "ACR")
    rows = _dedupe_records(fact[eligible_pipeline_waves(fact, motion)])
    total = float(pd.to_numeric(rows.get("total_acr"), errors="coerce").sum())
    return Metric(total, "ACR", rows)


def nodes_planned(fact: pd.DataFrame) -> Metric:
    """Total Cores across every eligible wave, reported as **Nodes**.

    The same eligibility rule as :func:`acr_pipeline`, summing the Total Cores
    column instead of the ACR — the deployment still to come, as opposed to the
    deployment already delivered that *Hosts Migrated* counts.
    """
    if fact.empty:
        return Metric(0, "nodes")
    # An EOS figure: read as the AVS motion always, so no "From AVS" wave —
    # whatever population it is handed — can deploy a node here.
    rows = _dedupe_records(fact[eligible_pipeline_waves(fact, MOTION_AVS)])
    total = float(pd.to_numeric(rows.get("total_cores"), errors="coerce").sum())
    return Metric(total, "nodes", rows)


# --------------------------------------------------------------------------- #
# Drill-down helper
# --------------------------------------------------------------------------- #
#: The wave number column, renamed for the account view so a reader knows the
#: row shows the account's latest wave rather than an arbitrary one.
LATEST_WAVE_COLUMN = "Most Recent / Latest Wave"

#: The blocked-accounts drill-down, as its own column list rather than the
#: general one plus an extra.  It answers a different question — *why has this
#: account stopped, and who is on it* — so it drops the platform and category
#: columns and keeps **Status Summary** in view, which is the whole point of the
#: table and would otherwise sit twenty columns to the right.
BLOCKED_DRILLDOWN_COLUMNS = [
    "tpid", "customer_name", "region_geo", "blocked_state",
    "migration_status_label", "factory_offering", "migration_path", "phase",
    "solution_architect", "assigned_pm", "total_cores", "total_acr",
    "status_summary",
]


def account_detail(fact: pd.DataFrame, approvals: pd.DataFrame | None = None,
                   lasts: pd.DataFrame | None = None) -> pd.DataFrame:
    """One row per TPID, showing the account's current state.

    Each field comes from the wave that actually answers for it, which is not
    the same wave throughout:

    * **Wave-specific fields** (status, current state, region, cores, dates,
      owners) — the account's **latest** wave, so the row reads as where the
      account stands now.
    * **Total ACR** — summed across every wave of the account **except blocked
      ones** (:func:`account_acr`).  An account that claimed 10M, 15M and 20M
      over three waves has committed 45M; showing the last wave's 20M would
      understate it.
    * **Nomination approval date** — Wave-1's, because that is when the account
      was nominated, not when its latest wave was; when Wave-1 carries no
      approval date the rule falls through to the next wave that does
      (:func:`dated_wave`), so the column reads the same here as in the New
      Engagements tile.
    """
    if fact.empty:
        return fact
    approvals = (dated_wave(fact, "approval_date") if approvals is None
                 else approvals)
    lasts = latest_wave(fact) if lasts is None else lasts

    out = lasts.copy()
    out["total_acr"] = out["tpid_key"].map(account_acr(fact))
    dates = approvals.set_index("tpid_key")["approval_date"]
    out["approval_date"] = out["tpid_key"].map(dates)
    return out.reset_index(drop=True)


def drilldown_frame(records: pd.DataFrame,
                    columns: list[str] | None = None) -> pd.DataFrame:
    """Trim underlying records to the agreed drill-down columns.

    ``columns`` overrides that list for a drill-down answering a different
    question — :data:`BLOCKED_DRILLDOWN_COLUMNS` for the blocked accounts, which
    leads with why each one has stopped.
    """
    columns = list(columns if columns is not None else DRILLDOWN_COLUMNS)
    if records is None or records.empty:
        return pd.DataFrame(columns=columns)
    cols = [c for c in columns if c in records.columns]
    return records[cols].reset_index(drop=True)


# --------------------------------------------------------------------------- #
# Programme summary — where each account's migration has got to
# --------------------------------------------------------------------------- #
PHASE_COMPLETED = "Completed"
PHASE_IN_PROGRESS = "In progress"
PHASE_PLANNING = "In planning"

#: FDO Migration Status codes, by phase: stage 4 "Executing Migration" is in
#: progress; stage 2 "Executing Pre-requisites" and stage 3 "Finalize Scope" are
#: planning.  Stage 1 is neither.
IN_PROGRESS_CODES = (4,)
PLANNING_CODES = (2, 3)
#: The EOS tracking sheet's own statuses, by the same phases.  Its stages carry
#: no number, so they are read by name: "Executing Migration" is the export's
#: stage 4 and "Sign-off Pending" follows it (the move is done, the sign-off is
#: not); "Planning & Prerequisites" and "Ready for Migration" come before it.
IN_PROGRESS_SHEET_STATUSES = ("Executing Migration", "Sign-off Pending")
PLANNING_SHEET_STATUSES = ("Planning & Prerequisites", "Ready for Migration")


def wave_phase(df: pd.DataFrame) -> pd.Series:
    """Per wave: In progress, In planning, or NA — read from its Migration Status.

    An export stage by its number, a tracking-sheet stage by its name.  Only a
    wave still in flight has a phase; a completed, deferred, cancelled or
    on-hold wave has none.
    """
    out = pd.Series(pd.NA, index=df.index, dtype="object")
    if df.empty:
        return out
    code = pd.to_numeric(df.get("migration_status_code"), errors="coerce")
    label = df.get("migration_status_label",
                   pd.Series(pd.NA, index=df.index)).astype("string")
    sheet = (df["status_source"].eq(statuses.SOURCE_TRACKER).fillna(False)
             if "status_source" in df.columns
             else pd.Series(False, index=df.index)).astype(bool) & code.isna()
    moving = statuses.is_class(df, statuses.IN_FLIGHT).to_numpy()
    planning = (code.isin(PLANNING_CODES)
                | (sheet & label.isin(PLANNING_SHEET_STATUSES).fillna(False)))
    progress = (code.isin(IN_PROGRESS_CODES)
                | (sheet & label.isin(IN_PROGRESS_SHEET_STATUSES).fillna(False)))
    out[planning.to_numpy() & moving] = PHASE_PLANNING
    out[progress.to_numpy() & moving] = PHASE_IN_PROGRESS
    return out


def account_phase(fact: pd.DataFrame) -> pd.Series:
    """Per account (indexed by ``tpid_key``): Completed, In progress, In planning
    or NA, the first of these to hold:

    1. **Completed** — the account state is Completed (:func:`account_state`).
    2. **In progress** — any wave is at stage 4 (or the sheet's "Executing
       Migration" / "Sign-off Pending").
    3. **In planning** — any wave is at stage 2 or 3 (or the sheet's
       "Planning & Prerequisites" / "Ready for Migration").

    Current State plays no part: a Blocked wave at stage 4 is still in progress.
    Everything else (stage 1, deferred, on hold, cancelled) has no phase.
    """
    if fact.empty:
        return pd.Series(dtype="object")
    keys = _keys(fact)
    lasts = latest_wave(fact)
    out = pd.Series(pd.NA, index=pd.Index(_keys(lasts).unique(), name="tpid_key"),
                    dtype="object")
    phase = wave_phase(fact)
    planning = set(keys[phase.eq(PHASE_PLANNING).fillna(False).to_numpy()])
    progress = set(keys[phase.eq(PHASE_IN_PROGRESS).fillna(False).to_numpy()])
    state = pd.Series(account_state(fact, lasts).to_numpy(), index=_keys(lasts).to_numpy())
    done = set(state.index[state.eq(STATE_COMPLETED).to_numpy()])
    out[out.index.isin(planning)] = PHASE_PLANNING
    out[out.index.isin(progress)] = PHASE_IN_PROGRESS
    out[out.index.isin(done)] = PHASE_COMPLETED
    return out


def nominated_since(fact: pd.DataFrame, start) -> pd.DataFrame:
    """The rows of every account whose **first** nomination is on or after *start*.

    An account's nomination date is its earliest wave's **Nom. Approval Date**,
    else its **Nom. Created Date** (:func:`app.core.cleaning.nomination_date`).
    An account with neither date on any wave cannot be placed, and is left out.
    """
    if fact.empty:
        return fact
    from .cleaning import nomination_date
    first = nomination_date(fact).groupby(_keys(fact)).min()
    keep = set(first.index[(first >= pd.Timestamp(start)).fillna(False).to_numpy()])
    return fact[_keys(fact).isin(keep).to_numpy()]
