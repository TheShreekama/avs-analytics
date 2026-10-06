"""The EOS Programme Tracker report — the tracking sheet, reported on its own terms.

Every other EOS figure is the FDO export with the sheet laid over it, so an
account the export does not hold cannot appear in them.  This report starts
from the **sheet**: one row per account the programme is tracking, whether or
not the export has a nomination for it yet, with the export looked up by TPID
for what the sheet does not carry (the account's name and WW Region as the
export spells them, its Factory PM, ACR and cores).

Everything here is read from the sheet's own columns — **Migration Status**,
**Current State**, **Target SDDC Generation**, the SDDC counts and the two
dates — so these numbers answer "what does the programme say", and the other
EOS reports answer "what has been nominated and delivered".  The two meet in
the account state (:func:`app.core.kpi.tracker_account_state`), which both use.

Built once by :func:`build` and rendered three times — the dashboard page, the
PDF and the HTML report — so the three cannot drift.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from . import eos_tracker, kpi, segments, statuses

NOT_STATED = "Not stated"
TITLE = "EOS Programme Tracker"
BLURB = ("The manual EOS tracking sheet, account by account: where the programme "
         "says each migration is (Migration Status), how it is going (Current "
         "State), and how many SDDCs are done. Read from the sheet itself, so "
         "an account the FDO export does not hold yet is still here.")

#: Migration Status values in the order a migration moves through them.
STATUS_ORDER: tuple[str, ...] = tuple(st.text for st in eos_tracker.TRACKER_STATUSES)
STATE_ORDER: tuple[str, ...] = eos_tracker.TRACKER_STATES
GENERATION_ORDER = (segments.GEN_1, segments.GEN_2, NOT_STATED)

#: How long an account has been migrating, in the buckets the review reads.
AGE_BUCKETS: tuple[tuple[str, int, int], ...] = (
    ("0-30 days", 0, 30), ("31-90 days", 31, 90), ("91-180 days", 91, 180),
    ("181-365 days", 181, 365), ("Over a year", 366, 10**6))

#: The account list, as (column, header).
ACCOUNT_COLUMNS: tuple[tuple[str, str], ...] = (
    ("tpid", "TPID"), ("customer", "Customer"), ("ww_region", "WW Region"),
    ("generation", "Target Gen"), ("status", "Migration Status"),
    ("state", "Current State"), ("account_state", "Reported as"),
    ("sddcs_in_scope", "SDDCs in scope"), ("sddcs_migrated", "SDDCs migrated"),
    ("start", "Migration Start"), ("end", "Migration End"),
    ("days", "Days"), ("assigned_pm", "Factory PM"), ("total_acr", "ACR"),
    ("in_fdo", "In FDO"))


@dataclass
class Programme:
    """Everything the report shows, computed once."""
    accounts: pd.DataFrame
    tiles: dict = field(default_factory=dict)
    by_status: pd.DataFrame = field(default_factory=pd.DataFrame)
    by_state: pd.DataFrame = field(default_factory=pd.DataFrame)
    status_state: pd.DataFrame = field(default_factory=pd.DataFrame)
    sddcs: pd.DataFrame = field(default_factory=pd.DataFrame)
    region_status: pd.DataFrame = field(default_factory=pd.DataFrame)
    monthly: pd.DataFrame = field(default_factory=pd.DataFrame)
    ageing: pd.DataFrame = field(default_factory=pd.DataFrame)
    durations: pd.DataFrame = field(default_factory=pd.DataFrame)
    attention: pd.DataFrame = field(default_factory=pd.DataFrame)
    checks: pd.DataFrame = field(default_factory=pd.DataFrame)

    @property
    def empty(self) -> bool:
        return self.accounts.empty


def accounts(tracker: pd.DataFrame | None, fact: pd.DataFrame | None,
             as_of=None) -> pd.DataFrame:
    """One row per account in the sheet, with the export's details beside it.

    From the sheet: TPID, Migration Status, Current State, Target SDDC
    Generation, the SDDC counts and the two dates.  From the FDO export, by
    TPID, where it holds the account: the customer name and WW Region as the
    export writes them, Factory PM and Solution Architect from the latest wave,
    and ACR and Total Cores summed across every wave that is not a "(From AVS)"
    move.  The sheet's own Customer and Region stand in where the export has
    nothing.
    """
    if tracker is None or tracker.empty:
        return pd.DataFrame(columns=[c for c, _h in ACCOUNT_COLUMNS])
    acc = tracker.copy()
    acc["in_fdo"] = False
    for column in ("fdo_customer", "fdo_region", "assigned_pm",
                   "solution_architect", "fdo_generation"):
        acc[column] = pd.NA
    acc["total_acr"] = float("nan")
    acc["total_cores"] = float("nan")
    acc["waves"] = 0

    if fact is not None and not fact.empty:
        onboarding = fact[~fact["is_from_avs"].astype(bool)] \
            if "is_from_avs" in fact.columns else fact
        if not onboarding.empty:
            lasts = kpi.latest_wave(onboarding).set_index("tpid_key")
            sums = onboarding.assign(
                _acr=pd.to_numeric(onboarding.get("total_acr"), errors="coerce"),
                _cores=pd.to_numeric(onboarding.get("total_cores"), errors="coerce"),
            ).groupby("tpid_key").agg(acr=("_acr", "sum"), cores=("_cores", "sum"),
                                      waves=("_acr", "size"))
            key = acc["tpid_key"]
            acc["in_fdo"] = key.isin(set(lasts.index)).to_numpy()
            for src, dst in (("customer_name", "fdo_customer"),
                             ("region_geo", "fdo_region"),
                             ("assigned_pm", "assigned_pm"),
                             ("solution_architect", "solution_architect"),
                             ("generation", "fdo_generation")):
                if src in lasts.columns:
                    acc[dst] = key.map(lasts[src]).to_numpy()
            acc["total_acr"] = key.map(sums["acr"]).to_numpy()
            acc["total_cores"] = key.map(sums["cores"]).to_numpy()
            acc["waves"] = key.map(sums["waves"]).fillna(0).astype(int).to_numpy()

    acc["customer"] = _first_of(acc["fdo_customer"], acc.get("customer_name"))
    region = _first_of(acc["fdo_region"], acc.get("region"))
    acc["ww_region"] = region.mask(region.astype("string").str.casefold()
                                   .eq("unknown").fillna(False), pd.NA).fillna("Unknown")
    fdo_gen = acc["fdo_generation"].where(
        acc["fdo_generation"].isin((segments.GEN_1, segments.GEN_2)))
    acc["generation"] = _first_of(acc.get("target_generation"), fdo_gen).fillna(NOT_STATED)
    acc["status"] = acc["migration_status"].astype("object").where(
        acc["migration_status"].notna(), NOT_STATED)
    acc["state"] = acc["current_state"].astype("object").where(
        acc["current_state"].notna(), NOT_STATED)
    stated = kpi.tracker_account_state(pd.DataFrame({
        "eos_status_class": acc["status_class"].astype("string"),
        "eos_tracker_state": acc["current_state"].astype("string"),
    }, index=acc.index))
    acc["account_state"] = stated.fillna(NOT_STATED)

    scope = pd.to_numeric(acc["sddcs_in_scope"], errors="coerce")
    done = pd.to_numeric(acc["sddcs_migrated"], errors="coerce")
    acc["sddcs_outstanding"] = (scope - done.fillna(0)).clip(lower=0)
    acc["start"] = pd.to_datetime(acc["migration_start_date"], errors="coerce")
    acc["end"] = pd.to_datetime(acc["migration_end_date"], errors="coerce")
    today = pd.Timestamp(as_of).normalize() if as_of is not None \
        else pd.Timestamp.today().normalize()
    acc["days"] = (acc["end"].fillna(today) - acc["start"]).dt.days
    acc.loc[acc["days"] < 0, "days"] = pd.NA
    return acc.reset_index(drop=True)


def _first_of(*series) -> pd.Series:
    out = None
    for s in series:
        if s is None:
            continue
        s = s.astype("object").where(s.notna() & s.astype("string").str.strip()
                                     .ne("").fillna(False))
        out = s if out is None else out.where(out.notna(), s)
    return out


def _ordered_crosstab(rows: pd.DataFrame, index: str, columns: str,
                      index_order, column_order) -> pd.DataFrame:
    grid = pd.crosstab(rows[index], rows[columns])
    idx = [v for v in index_order if v in grid.index] + \
          [v for v in grid.index if v not in index_order]
    cols = [v for v in column_order if v in grid.columns] + \
           [v for v in grid.columns if v not in column_order]
    return grid.loc[idx, cols]


def _with_total(grid: pd.DataFrame) -> pd.DataFrame:
    if grid.empty:
        return grid
    grid = grid.copy()
    grid["Total"] = grid.sum(axis=1)
    return grid


def by_status(acc: pd.DataFrame) -> pd.DataFrame:
    """Accounts per Migration Status (in stage order), split by generation."""
    if acc.empty:
        return pd.DataFrame()
    return _with_total(_ordered_crosstab(acc, "status", "generation",
                                         (*STATUS_ORDER, NOT_STATED),
                                         GENERATION_ORDER))


def by_state(acc: pd.DataFrame) -> pd.DataFrame:
    """Accounts per Current State, split by generation."""
    if acc.empty:
        return pd.DataFrame()
    return _with_total(_ordered_crosstab(acc, "state", "generation",
                                         (*STATE_ORDER, NOT_STATED),
                                         GENERATION_ORDER))


def status_state(acc: pd.DataFrame) -> pd.DataFrame:
    """Migration Status down the side, Current State across: where they meet."""
    if acc.empty:
        return pd.DataFrame()
    return _ordered_crosstab(acc, "status", "state", (*STATUS_ORDER, NOT_STATED),
                             (*STATE_ORDER, NOT_STATED))


def region_status(acc: pd.DataFrame) -> pd.DataFrame:
    """WW Region down the side, Migration Status across."""
    if acc.empty:
        return pd.DataFrame()
    return _ordered_crosstab(acc, "ww_region", "status", (),
                             (*STATUS_ORDER, NOT_STATED))


def sddc_progress(acc: pd.DataFrame) -> pd.DataFrame:
    """SDDCs in scope, migrated and outstanding — per generation, then in total."""
    if acc.empty:
        return pd.DataFrame()
    rows = acc.assign(
        _scope=pd.to_numeric(acc["sddcs_in_scope"], errors="coerce"),
        _done=pd.to_numeric(acc["sddcs_migrated"], errors="coerce"),
        _left=pd.to_numeric(acc["sddcs_outstanding"], errors="coerce"))
    grouped = rows.groupby("generation").agg(
        accounts=("tpid_key", "nunique"), in_scope=("_scope", "sum"),
        migrated=("_done", "sum"), outstanding=("_left", "sum"))
    order = [g for g in GENERATION_ORDER if g in grouped.index] + \
            [g for g in grouped.index if g not in GENERATION_ORDER]
    grouped = grouped.loc[order]
    grouped.loc["All EOS"] = grouped.sum()
    grouped["complete_pct"] = (grouped["migrated"] / grouped["in_scope"]
                               .where(grouped["in_scope"] > 0) * 100).round(0)
    return grouped.rename_axis("generation").reset_index()


def monthly(acc: pd.DataFrame) -> pd.DataFrame:
    """Migrations started and ended per month, by the sheet's own two dates."""
    if acc.empty:
        return pd.DataFrame(columns=["month", "Started", "Ended"])
    started = acc["start"].dropna().dt.to_period("M").value_counts()
    ended = acc["end"].dropna().dt.to_period("M").value_counts()
    months = sorted(set(started.index) | set(ended.index))
    if not months:
        return pd.DataFrame(columns=["month", "Started", "Ended"])
    span = pd.period_range(months[0], months[-1], freq="M")
    return pd.DataFrame({
        "month": [str(m) for m in span],
        "Started": [int(started.get(m, 0)) for m in span],
        "Ended": [int(ended.get(m, 0)) for m in span],
    })


def _moving(acc: pd.DataFrame) -> pd.Series:
    return acc["status_class"].astype("string").eq(statuses.IN_FLIGHT).fillna(False)


def ageing(acc: pd.DataFrame) -> pd.DataFrame:
    """Migrations still in flight, by how long since their Migration Start Date."""
    if acc.empty:
        return pd.DataFrame(columns=["bucket", "accounts"])
    days = pd.to_numeric(acc.loc[_moving(acc) & acc["end"].isna(), "days"],
                         errors="coerce")
    out = [{"bucket": label,
            "accounts": int(days.between(lo, hi).sum())}
           for label, lo, hi in AGE_BUCKETS]
    out.append({"bucket": "No start date", "accounts":
                int((_moving(acc) & acc["end"].isna() & acc["start"].isna()).sum())})
    return pd.DataFrame(out)


def durations(acc: pd.DataFrame) -> pd.DataFrame:
    """Completed migrations: days from Migration Start Date to Actual End Date."""
    if acc.empty:
        return pd.DataFrame()
    done = acc[acc["status_class"].astype("string").eq(statuses.COMPLETED).fillna(False)
               & acc["start"].notna() & acc["end"].notna()]
    if done.empty:
        return pd.DataFrame()
    days = pd.to_numeric(done["days"], errors="coerce")
    grouped = done.assign(_days=days).groupby("generation")["_days"].agg(
        ["count", "median", "mean", "max"])
    grouped.loc["All EOS"] = [len(days), days.median(), days.mean(), days.max()]
    return grouped.round(0).rename(columns={
        "count": "accounts", "median": "median_days", "mean": "average_days",
        "max": "longest_days"}).rename_axis("generation").reset_index()


def attention(acc: pd.DataFrame) -> pd.DataFrame:
    """The accounts a review asks about first: Blocked, On Hold, then the
    longest-running in flight — most days first."""
    if acc.empty:
        return acc
    blocked = acc["state"].eq(eos_tracker.STATE_BLOCKED)
    held = acc["status_class"].astype("string").eq(statuses.ON_HOLD).fillna(False)
    rows = acc[blocked | held].copy()
    rows["why"] = ["Blocked" if b else "On Hold"
                   for b in blocked[blocked | held]]
    return rows.sort_values(["why", "days"], ascending=[True, False],
                            na_position="last").reset_index(drop=True)


def tiles(acc: pd.DataFrame) -> dict:
    """The headline numbers."""
    if acc.empty:
        return {}
    state = acc["account_state"]
    scope = float(pd.to_numeric(acc["sddcs_in_scope"], errors="coerce").sum())
    done = float(pd.to_numeric(acc["sddcs_migrated"], errors="coerce").sum())
    return {
        "accounts": int(len(acc)),
        "in_fdo": int(acc["in_fdo"].sum()),
        "on_track": int(state.eq(kpi.STATE_ON_TRACK).sum()),
        "blocked": int(state.eq(kpi.STATE_BLOCKED).sum()),
        "completed": int(state.eq(kpi.STATE_COMPLETED).sum()),
        "on_hold": int(state.eq(kpi.STATE_ON_HOLD).sum()),
        "cancelled": int(state.eq(kpi.STATE_CANCELLED).sum()),
        "sddcs_in_scope": scope,
        "sddcs_migrated": done,
        "sddc_pct": (done / scope * 100) if scope else None,
    }


def build(tracker: pd.DataFrame | None, fact: pd.DataFrame | None,
          as_of=None) -> Programme:
    """The whole report, computed once."""
    acc = accounts(tracker, fact, as_of)
    if acc.empty:
        return Programme(accounts=acc)
    return Programme(
        accounts=acc, tiles=tiles(acc), by_status=by_status(acc),
        by_state=by_state(acc), status_state=status_state(acc),
        sddcs=sddc_progress(acc), region_status=region_status(acc),
        monthly=monthly(acc), ageing=ageing(acc), durations=durations(acc),
        attention=attention(acc),
        checks=eos_tracker.status_state_disagreements(tracker))


def account_table(rows: pd.DataFrame, fmt_money, fmt_date=None) -> pd.DataFrame:
    """Accounts laid out for print or screen, every cell a display string."""
    if rows is None or rows.empty:
        return pd.DataFrame(columns=[h for _c, h in ACCOUNT_COLUMNS])
    fmt_date = fmt_date or (lambda v: "" if pd.isna(v) else pd.Timestamp(v).strftime("%d %b %Y"))
    out = pd.DataFrame(index=rows.index)
    for column, header in ACCOUNT_COLUMNS:
        values = rows[column] if column in rows.columns else pd.Series("", index=rows.index)
        if column in ("start", "end"):
            out[header] = values.map(fmt_date)
        elif column == "total_acr":
            out[header] = pd.to_numeric(values, errors="coerce").map(
                lambda v: "" if pd.isna(v) else fmt_money(v))
        elif column in ("sddcs_in_scope", "sddcs_migrated", "days"):
            out[header] = pd.to_numeric(values, errors="coerce").map(
                lambda v: "" if pd.isna(v) else f"{int(v):,}")
        elif column == "in_fdo":
            out[header] = values.map(lambda v: "Yes" if bool(v) else "No")
        else:
            out[header] = values.astype("object").where(values.notna(), "").astype(str)
    if "why" in rows.columns:
        out.insert(0, "Why", rows["why"].astype(str))
    return out.reset_index(drop=True)


def grid_frame(grid: pd.DataFrame, first: str) -> pd.DataFrame:
    """A crosstab as a printable frame, its index as the first column."""
    if grid is None or grid.empty:
        return pd.DataFrame()
    out = grid.copy()
    out.index = out.index.astype(str)
    out = out.rename_axis(first).reset_index()
    out.columns = [str(c) for c in out.columns]
    return out
