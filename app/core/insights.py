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
            fastest = med.idxmin()
            out.append(Insight(
                "Closures", "Fastest-closing region",
                f"**{fastest}** closes nominations fastest "
                f"(median {med.min():.0f} days vs {med.median():.0f} overall).",
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
