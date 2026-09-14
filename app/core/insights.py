"""Deterministic, rule-based insights engine.

No AI, no external calls — every insight is derived directly from the fact frame
with transparent rules.  Each rule guards against thin data so it degrades
gracefully on small or filtered slices.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .metrics import fmt_currency, fmt_int

# severities map to colours/icons in the UI
POSITIVE, INFO, WARNING, CRITICAL = "positive", "info", "warning", "critical"


@dataclass
class Insight:
    category: str
    title: str
    detail: str
    severity: str = INFO
    metric: str = ""

    def as_dict(self) -> dict:
        return {"category": self.category, "title": self.title,
                "detail": self.detail, "severity": self.severity, "metric": self.metric}


def _rate_by(fact: pd.DataFrame, dim: str, flag: str, min_total: int = 3) -> pd.DataFrame:
    g = fact.groupby(dim, dropna=True).agg(total=(flag, "size"),
                                           hits=(flag, "sum")).reset_index()
    g = g[g["total"] >= min_total]
    if g.empty:
        return g
    g["rate"] = (100 * g["hits"] / g["total"]).round(1)
    return g


def generate_insights(fact: pd.DataFrame, region_dim: str = "region_geo") -> list[Insight]:
    out: list[Insight] = []
    n = len(fact)
    if n == 0:
        return [Insight("Data", "No data in current selection",
                        "Adjust filters to see insights.", INFO)]
    # Fall back gracefully if the preferred region column isn't present.
    if region_dim not in fact.columns:
        region_dim = "ww_region" if "ww_region" in fact.columns else fact.columns[0]

    # ---- Volume / coverage ------------------------------------------------ #
    accounts = fact["tpid"].nunique(dropna=True) if "tpid" in fact else n
    out.append(Insight(
        "Overview", "Portfolio scope",
        f"{fmt_int(n)} nominations across {fmt_int(accounts)} accounts and "
        f"{fact[region_dim].nunique()} regions.", INFO, fmt_int(n)))

    # ---- Top region by volume -------------------------------------------- #
    vol = fact[region_dim].value_counts()
    if not vol.empty:
        top_region, top_n = vol.index[0], int(vol.iloc[0])
        out.append(Insight(
            "Regions", "Largest region by volume",
            f"**{top_region}** leads with {fmt_int(top_n)} nominations "
            f"({top_n/n*100:.0f}% of total).", INFO, top_region))

    # ---- Approval rate: best & worst ------------------------------------- #
    appr = _rate_by(fact, region_dim, "is_approved")
    if not appr.empty and len(appr) >= 2:
        best = appr.sort_values("rate", ascending=False).iloc[0]
        worst = appr.sort_values("rate", ascending=True).iloc[0]
        out.append(Insight(
            "Approvals", "Highest approval-rate region",
            f"**{best[region_dim]}** has the highest approval rate at "
            f"{best['rate']:.0f}% ({fmt_int(best['hits'])}/{fmt_int(best['total'])}).",
            POSITIVE, f"{best['rate']:.0f}%"))
        if worst[region_dim] != best[region_dim]:
            sev = WARNING if worst["rate"] < 60 else INFO
            out.append(Insight(
                "Approvals", "Lowest approval-rate region",
                f"**{worst[region_dim]}** trails at {worst['rate']:.0f}% "
                f"({fmt_int(worst['hits'])}/{fmt_int(worst['total'])}) — review intake quality.",
                sev, f"{worst['rate']:.0f}%"))

    # ---- Closure rate & fastest-closing region --------------------------- #
    closed = int(fact["is_closed"].sum())
    out.append(Insight(
        "Closures", "Overall closure rate",
        f"{fmt_int(closed)} of {fmt_int(n)} nominations are closed "
        f"({closed/n*100:.0f}%).", POSITIVE if closed/n >= 0.5 else INFO,
        f"{closed/n*100:.0f}%"))

    closed_fact = fact[fact["is_closed"] & fact["cycle_time_days"].notna()]
    if len(closed_fact) >= 3:
        med = closed_fact.groupby(region_dim)["cycle_time_days"].median()
        med = med[closed_fact.groupby(region_dim).size() >= 2]
        if not med.empty:
            # ``med`` is one median per region, so the comparison figure is the
            # median *of those regional medians* — not the median across every
            # nomination, which is a different number.  Say which it is.
            fastest = med.idxmin()
            out.append(Insight(
                "Closures", "Fastest-closing region",
                f"**{fastest}** closes nominations fastest — a median cycle time "
                f"of {med.min():.0f} days, against {med.median():.0f} days for "
                f"the typical region. Regions with fewer than two closed "
                f"nominations are not ranked.",
                POSITIVE, f"{med.min():.0f}d"))

    # ---- Approval velocity ------------------------------------------------ #
    appr_lat = fact[fact["is_approved"] & fact["approval_latency_days"].notna()]
    appr_lat = appr_lat[appr_lat["approval_latency_days"] >= 0]
    if len(appr_lat) >= 3:
        med_all = float(appr_lat["approval_latency_days"].median())
        grp = appr_lat.groupby(region_dim)["approval_latency_days"]
        by_reg = grp.median()[grp.size() >= 2]
        slow = ""
        if not by_reg.empty:
            slow = f" Slowest region: **{by_reg.idxmax()}** ({by_reg.max():.0f}d median)."
        out.append(Insight(
            "Approvals", "Approval velocity",
            f"Median time from creation to approval is {med_all:.0f} days.{slow}",
            POSITIVE if med_all <= 14 else INFO, f"{med_all:.0f}d"))

    # ---- Oldest open nomination ------------------------------------------- #
    open_fact = fact[fact["is_open"]]
    if not open_fact.empty and open_fact["aging_days"].notna().any():
        oldest = open_fact.loc[open_fact["aging_days"].idxmax()]
        out.append(Insight(
            "Backlog", "Oldest open nomination",
            f"**{oldest.get('customer_name','?')}** "
            f"({oldest.get('factory_offering','?')}) has been open "
            f"{fmt_int(oldest['aging_days'])} days.", WARNING,
            f"{fmt_int(oldest['aging_days'])}d"))

    # ---- Most common migration status ------------------------------------ #
    if fact["migration_status_label"].notna().any():
        ms = fact["migration_status_label"].value_counts()
        out.append(Insight(
            "Pipeline", "Most common migration status",
            f"**{ms.index[0]}** is the most common stage "
            f"({fmt_int(int(ms.iloc[0]))} nominations, {ms.iloc[0]/n*100:.0f}%).",
            INFO, ms.index[0]))

    # ---- Risk hotspots ------------------------------------------------ #
    risk_states = {"At Risk", "Delayed", "Blocked"}
    fact_risk = fact[fact["eos_status"].isin(risk_states)]
    if not fact_risk.empty:
        hot = fact_risk[region_dim].value_counts()
        share = len(fact_risk) / n * 100
        out.append(Insight(
            "Risk", "Risk hotspot",
            f"**{hot.index[0]}** has the most at-risk/blocked/delayed items "
            f"({fmt_int(int(hot.iloc[0]))}). {share:.0f}% of the portfolio is in a risk state.",
            CRITICAL if share >= 20 else WARNING, fmt_int(int(hot.iloc[0]))))

    # ---- Migration growth by track (period over period) ------------------ #
    growth = _track_growth(fact)
    if growth is not None:
        track, cur, prev, pct = growth
        if pct is not None:
            sev = POSITIVE if pct >= 0 else WARNING
            arrow = "up" if pct >= 0 else "down"
            out.append(Insight(
                "Growth", "Fastest-growing migration track",
                f"**{track}** nominations are {arrow} {abs(pct):.0f}% "
                f"vs the prior period ({fmt_int(prev)} → {fmt_int(cur)}).",
                sev, f"{'+' if pct>=0 else ''}{pct:.0f}%"))

    # ---- AVS → Azure Native adoption ------------------------------------- #
    from_avs = fact[fact["migration_direction"] == "AVS → Azure Native"]
    if not from_avs.empty:
        tgt = from_avs["azure_target"].value_counts()
        comp = from_avs["is_closed"].mean() * 100
        out.append(Insight(
            "Azure Native", "Top Azure-native destination",
            f"**{tgt.index[0]}** is the most common AVS→Azure-Native target "
            f"({fmt_int(int(tgt.iloc[0]))} of {fmt_int(len(from_avs))}); "
            f"{comp:.0f}% of these migrations are complete.", INFO, tgt.index[0]))

    # ---- Commercial value ------------------------------------------------- #
    if fact["total_acr"].notna().any():
        acr_total = fact["total_acr"].sum()
        by_reg_acr = fact.groupby(region_dim)["total_acr"].sum().sort_values(ascending=False)
        if not by_reg_acr.empty and acr_total > 0:
            out.append(Insight(
                "Commercial", "ACR concentration",
                f"Total ACR is {fmt_currency(acr_total)}; **{by_reg_acr.index[0]}** "
                f"drives {fmt_currency(by_reg_acr.iloc[0])} "
                f"({by_reg_acr.iloc[0]/acr_total*100:.0f}%).", INFO, fmt_currency(acr_total)))

    # ---- Data quality ----------------------------------------------------- #
    dq_rows = int(fact["has_dq_issue"].sum()) if "has_dq_issue" in fact else 0
    if dq_rows:
        from collections import Counter
        notes = Counter()
        for s in fact.loc[fact["has_dq_issue"], "dq_flags"]:
            for part in str(s).split("; "):
                if part:
                    notes[part] += 1
        top = ", ".join(f"{k} ({v})" for k, v in notes.most_common(3))
        out.append(Insight(
            "Data Quality", "Data quality issues detected",
            f"{fmt_int(dq_rows)} of {fmt_int(n)} rows have quality issues. "
            f"Most common: {top}.", WARNING if dq_rows/n < 0.2 else CRITICAL,
            fmt_int(dq_rows)))
    else:
        out.append(Insight("Data Quality", "Clean dataset",
                           "No data quality issues detected in the current selection.",
                           POSITIVE, "0"))

    out += programme_insights(fact, region_dim)
    return out


# --------------------------------------------------------------------------- #
# Programme-management rules
# --------------------------------------------------------------------------- #
# Every rule below reads the same columns the reports are built from and is
# guarded twice over: on the columns being present at all (a partly-mapped file,
# or the customer rollup, carries fewer), and on there being enough rows for the
# statement to mean anything.  A rule with nothing to say says nothing — an
# insight list padded with "0 accounts are blocked" trains a reader to skip it.
# --------------------------------------------------------------------------- #
#: Rules need at least this many accounts before they generalise about a split.
_MIN_ACCOUNTS = 3


def _has(fact: pd.DataFrame, *columns: str) -> bool:
    return all(c in fact.columns for c in columns)


def _num(fact: pd.DataFrame, column: str) -> pd.Series:
    return pd.to_numeric(fact.get(column), errors="coerce")


def programme_insights(fact: pd.DataFrame,
                       region_dim: str = "region_geo") -> list[Insight]:
    """Migration-programme findings: pipeline, bottlenecks, delays and exclusions.

    Deliberately separate from the portfolio rules above — these read the
    *delivery* columns (migration status, current state, planned vs actual
    dates, cores, waves) rather than the nomination ones, and each says which
    figures it is derived from so a reader can check it against the tables.
    """
    from . import kpi, segments            # imported here: kpi imports metrics only

    out: list[Insight] = []
    if fact is None or fact.empty:
        return out
    if region_dim not in fact.columns:
        region_dim = "ww_region" if "ww_region" in fact.columns else ""

    # The frame is normally wave-level; the customer rollup hands over one row
    # per account already, in which case the latest wave of each account is
    # simply that row.  Either way the rules below read accounts.
    lasts = kpi.latest_wave(fact)
    states = (kpi.account_state(fact, lasts) if not lasts.empty
              else pd.Series(dtype=object))
    accounts = int(len(lasts))

    out += _pipeline_insights(fact, kpi, region_dim)
    out += _blocked_insights(fact, kpi, lasts, states, accounts)
    out += _bottleneck_insights(fact, kpi)
    out += _delay_insights(fact, kpi)
    out += _wave_insights(fact, kpi, lasts, states, accounts)
    out += _delivery_insights(fact, kpi, segments)
    return out


def _pipeline_insights(fact, kpi, region_dim: str) -> list[Insight]:
    """What the approved, unblocked, unfinished work is worth — and where it sits."""
    if not _has(fact, "migration_status_code", "is_approved", "current_state"):
        return []
    eligible = fact[kpi.eligible_pipeline_waves(fact)]
    if eligible.empty:
        return []
    out = []
    pipeline_acr = float(_num(eligible, "total_acr").sum())
    claimed = float(_num(fact[fact.get("actual_end_date").notna()], "total_acr").sum()
                    if "actual_end_date" in fact.columns else 0.0)
    if pipeline_acr > 0:
        share = (f" That is {pipeline_acr / (pipeline_acr + claimed) * 100:.0f}% of "
                 f"the ACR this portfolio has claimed and planned together."
                 if claimed + pipeline_acr > 0 else "")
        out.append(Insight(
            "Pipeline", "ACR still to land",
            f"**{fmt_currency(pipeline_acr)}** of ACR sits on "
            f"{fmt_int(len(eligible))} approved, unblocked, unfinished waves.{share}",
            INFO, fmt_currency(pipeline_acr)))
        if region_dim and region_dim in eligible.columns:
            by_region = (eligible.groupby(region_dim)["total_acr"].sum()
                         .sort_values(ascending=False))
            by_region = by_region[by_region > 0]
            if len(by_region) >= 2:
                top, value = by_region.index[0], float(by_region.iloc[0])
                out.append(Insight(
                    "Pipeline", "Where the pipeline is concentrated",
                    f"**{top}** carries {fmt_currency(value)} of it "
                    f"({value / pipeline_acr * 100:.0f}%), the largest share of any "
                    f"region — the exposure if that one region slips.",
                    WARNING if value / pipeline_acr >= 0.5 else INFO,
                    fmt_currency(value)))
    cores = float(_num(eligible, "total_cores").sum())
    delivered = 0.0
    if "actual_end_date" in fact.columns:
        done = fact[kpi.is_completed(fact) & fact["actual_end_date"].notna()]
        delivered = float(_num(done, "total_cores").sum())
    if cores > 0 and delivered > 0:
        out.append(Insight(
            "Pipeline", "Deployment still ahead",
            f"**{fmt_int(cores)}** nodes (Total Cores) are planned on those waves "
            f"against {fmt_int(delivered)} already deployed — "
            f"{cores / (cores + delivered) * 100:.0f}% of the programme's nodes "
            f"are still to come.", INFO, fmt_int(cores)))
    return out


def _blocked_insights(fact, kpi, lasts, states, accounts: int) -> list[Insight]:
    """Accounts that have stopped: how many, how much, and on what."""
    if lasts.empty or accounts == 0 or states.empty:
        return []
    summary, rows = kpi.blocked_accounts(fact, lasts=lasts)
    if rows.empty:
        return []
    stuck = int(rows["tpid_key"].nunique())
    share = stuck / accounts * 100
    out = [Insight(
        "Blocked", "Accounts that have stopped",
        f"**{fmt_int(stuck)}** of {fmt_int(accounts)} accounts ({share:.0f}%) "
        f"are blocked or waiting on a follow-up — "
        + ", ".join(f"{fmt_int(v)} on {k.lower()}"
                    for k, v in zip(summary["category"], summary["count"]))
        + ". They are reported separately and are in none of the figures above.",
        CRITICAL if share >= 25 else WARNING, fmt_int(stuck))]
    held = float(_num(rows, "total_acr").sum())
    if held > 0:
        top = rows.loc[_num(rows, "total_acr").idxmax()]
        out.append(Insight(
            "Blocked", "ACR held up behind a blocked account",
            f"**{fmt_currency(held)}** of ACR sits on those accounts; the "
            f"largest single one is **{top.get('customer_name', '?')}** at "
            f"{fmt_currency(_num(rows, 'total_acr').max())} "
            f"({str(top.get('blocked_state', '')).lower()}).",
            WARNING, fmt_currency(held)))
    if len(summary) and int(summary.iloc[0]["count"]) > 1:
        state, count = summary.iloc[0]["category"], int(summary.iloc[0]["count"])
        out.append(Insight(
            "Blocked", "Most common blocking state",
            f"**{state}** stops {fmt_int(count)} of the {fmt_int(stuck)} — the "
            f"single change that would return the most accounts to the reported "
            f"pipeline.", INFO, state))
    return out


def _bottleneck_insights(fact, kpi) -> list[Insight]:
    """Which stage the in-flight work is piled up in, and what it is worth."""
    if not _has(fact, "migration_status_label"):
        return []
    moving = fact[kpi.in_flight(fact)]
    if len(moving) < _MIN_ACCOUNTS:
        return []
    by_stage = moving.groupby("migration_status_label").agg(
        waves=("migration_status_label", "size"), acr=("total_acr", "sum"))
    by_stage = by_stage.sort_values("waves", ascending=False)
    stage, row = by_stage.index[0], by_stage.iloc[0]
    share = int(row["waves"]) / len(moving) * 100
    out = [Insight(
        "Bottleneck", "Where in-flight work is piled up",
        f"**{stage}** holds {fmt_int(int(row['waves']))} of the "
        f"{fmt_int(len(moving))} in-flight waves ({share:.0f}%), carrying "
        f"{fmt_currency(float(row['acr']))} of ACR.",
        WARNING if share >= 50 else INFO, fmt_int(int(row["waves"])))]
    if _has(fact, "approval_date", "actual_start_date"):
        lag = (pd.to_datetime(fact["actual_start_date"], errors="coerce")
               - pd.to_datetime(fact["approval_date"], errors="coerce")).dt.days
        lag = lag[lag >= 0]
        if len(lag) >= _MIN_ACCOUNTS:
            out.append(Insight(
                "Bottleneck", "Approval to start",
                f"Migrations begin a median of **{lag.median():.0f} days** after "
                f"approval (over {fmt_int(len(lag))} waves with both dates); a "
                f"quarter take longer than {lag.quantile(0.75):.0f} days.",
                WARNING if lag.median() > 90 else INFO, f"{lag.median():.0f}d"))
    return out


def _delay_insights(fact, kpi) -> list[Insight]:
    """Waves whose own plan has passed them by."""
    if not _has(fact, "planned_end_date", "actual_end_date"):
        return []
    planned = pd.to_datetime(fact["planned_end_date"], errors="coerce")
    ended = pd.to_datetime(fact["actual_end_date"], errors="coerce")
    as_of = pd.Timestamp.today().normalize()
    overdue = fact[planned.notna() & ended.isna() & (planned < as_of)]
    out = []
    if not overdue.empty:
        days = (as_of - pd.to_datetime(overdue["planned_end_date"],
                                       errors="coerce")).dt.days
        worst = overdue.loc[days.idxmax()]
        out.append(Insight(
            "Delays", "Past their planned end date",
            f"**{fmt_int(len(overdue))}** waves are past their planned end date "
            f"with no actual end recorded, by a median of {days.median():.0f} "
            f"days. The furthest overdue is **{worst.get('customer_name', '?')}** "
            f"at {fmt_int(days.max())} days.",
            CRITICAL if len(overdue) >= 10 else WARNING, fmt_int(len(overdue))))
    done = fact[planned.notna() & ended.notna()]
    if len(done) >= _MIN_ACCOUNTS:
        slip = (pd.to_datetime(done["actual_end_date"], errors="coerce")
                - pd.to_datetime(done["planned_end_date"], errors="coerce")).dt.days
        late = int((slip > 0).sum())
        out.append(Insight(
            "Delays", "Plan versus delivery",
            f"Of {fmt_int(len(done))} waves with both a planned and an actual end "
            f"date, **{fmt_int(late)}** finished late "
            f"({late / len(done) * 100:.0f}%), with a median slip of "
            f"{slip.median():+.0f} days.",
            WARNING if late / len(done) > 0.5 else POSITIVE, f"{slip.median():+.0f}d"))
    return out


def _wave_insights(fact, kpi, lasts, states, accounts: int) -> list[Insight]:
    """What having several waves does to an account."""
    if accounts < _MIN_ACCOUNTS or "tpid_key" not in fact.columns:
        return []
    # Wave-level rows count themselves; the rollup already carries the count.
    per_account = (_num(fact, "n_waves").fillna(1) if "n_waves" in fact.columns
                   else fact.groupby("tpid_key").size())
    multi = int((per_account > 1).sum())
    out = []
    if multi:
        out.append(Insight(
            "Waves", "Accounts running several waves",
            f"**{fmt_int(multi)}** of {fmt_int(accounts)} accounts "
            f"({multi / accounts * 100:.0f}%) carry more than one wave — up to "
            f"{fmt_int(int(per_account.max()))} — so every account-level figure "
            f"in this report counts them once, not once per wave.",
            INFO, fmt_int(multi)))
    # The classification rule this report turns on, stated with its own count.
    if not lasts.empty and not states.empty:
        completed_last = kpi.is_completed(lasts).to_numpy()
        still_running = ((states == kpi.STATE_ON_TRACK).to_numpy() & completed_last)
        held = int(still_running.sum())
        if held:
            out.append(Insight(
                "Waves", "Finished a wave, still delivering",
                f"**{fmt_int(held)}** account(s) have a completed latest wave but "
                f"another wave still on track, so they count as On-Track rather "
                f"than Completed — the classification rule that keeps a "
                f"part-finished account out of the completed total.",
                INFO, fmt_int(held)))
    return out


def _delivery_insights(fact, kpi, segments) -> list[Insight]:
    """Differences between the motions, and inside the EOS population."""
    out = []
    if "is_from_avs" in fact.columns and "tpid_key" in fact.columns:
        flag = fact["is_from_avs"].astype(bool)
        if flag.any() and (~flag).any():
            rates = {}
            for label, part in (("AVS → Azure Native", fact[flag]),
                                ("onboarding to AVS", fact[~flag])):
                waves_ = kpi.wave_index(part)
                total = part["tpid_key"].nunique()
                done = kpi.migrations_completed(part, None, None,
                                                lasts=waves_.last).count
                if total:
                    rates[label] = (done / total * 100, done, total)
            if len(rates) == 2:
                (a, (ra, da, ta)), (b, (rb, db, tb)) = sorted(
                    rates.items(), key=lambda kv: -kv[1][0])
                out.append(Insight(
                    "Motions", "Completion differs by migration type",
                    f"**{a}** has completed {ra:.0f}% of its accounts "
                    f"({fmt_int(da)}/{fmt_int(ta)}) against {rb:.0f}% for {b} "
                    f"({fmt_int(db)}/{fmt_int(tb)}).", INFO, f"{ra:.0f}%"))
    if "generation" in fact.columns and "is_eos_population" in fact.columns:
        eos = fact[fact["is_eos_population"].astype(bool)]
        if not eos.empty:
            per_gen = (eos.drop_duplicates("tpid_key")["generation"]
                       .value_counts())
            tagged = {g: int(per_gen.get(g, 0))
                      for g in (segments.GEN_1, segments.GEN_2)}
            if sum(tagged.values()):
                cores = (eos.groupby("generation")["total_cores"].sum()
                         if "total_cores" in eos.columns else pd.Series(dtype=float))
                extra = ""
                if not cores.empty:
                    extra = (" Nodes follow the same split: "
                             + ", ".join(
                                 f"{fmt_int(float(cores.get(g, 0)))} on "
                                 f"{g.replace('-', '')}"
                                 for g in (segments.GEN_1, segments.GEN_2)) + ".")
                out.append(Insight(
                    "EOS", "Generation mix of the EOS population",
                    f"**{fmt_int(tagged[segments.GEN_1])}** accounts are tagged "
                    f"Gen1 and {fmt_int(tagged[segments.GEN_2])} Gen2.{extra}",
                    INFO, fmt_int(sum(tagged.values()))))
            untagged = int(per_gen.get(segments.GEN_UNCLASSIFIED, 0))
            if untagged:
                out.append(Insight(
                    "EOS", "EOS accounts with no generation tag",
                    f"**{fmt_int(untagged)}** account(s) are in EOS scope through "
                    f"their migration path but carry no Gen1/Gen2 tag on any "
                    f"wave. They are excluded from EOS reporting and listed "
                    f"under Data Inconsistency — adding the tag at source brings "
                    f"them back in.", WARNING, fmt_int(untagged)))
    return out


def _track_growth(fact: pd.DataFrame):
    """Return (track, current, prior, pct) for the fastest-growing track.

    Compares the two most recent complete months present in the data.
    """
    sub = fact.dropna(subset=["created_month", "factory_offering"])
    if sub["created_month"].nunique() < 2:
        return None
    months = sorted(sub["created_month"].unique())
    cur_m, prev_m = months[-1], months[-2]
    cur = sub[sub["created_month"] == cur_m]["factory_offering"].value_counts()
    prev = sub[sub["created_month"] == prev_m]["factory_offering"].value_counts()
    best = None
    for track in set(cur.index) | set(prev.index):
        c, p = int(cur.get(track, 0)), int(prev.get(track, 0))
        pct = (100 * (c - p) / p) if p else (100.0 if c else 0.0)
        if best is None or (c + p) > (best[1] + best[2]):
            best = (track, c, p, round(pct, 1))
    return best


def insights_to_frame(insights: list[Insight]) -> pd.DataFrame:
    return pd.DataFrame([i.as_dict() for i in insights])
