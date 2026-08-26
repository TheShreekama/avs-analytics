"""Customer-level rollup (deduplication across waves).

A customer (deduplicated by name) can have several waves (Wave-1, Wave-2 …).
Counting every wave double-counts the customer, so this module rolls waves up to
one row per customer using the business rules agreed with the user:

  * **First wave = Wave-1** (lowest wave number; ties broken by creation date).
    The customer's *approval date* and *creation date* come from the first wave.
  * **Status = last wave** (highest wave number). If the last wave is done/
    completed the customer is treated as closed; otherwise it follows the last
    wave's operational/EOS status.
  * **Category membership = any wave.** A customer is an "EOS Migration" nomination if
    *any* of its waves has an AV36/EOS migration path; likewise "AVS → Azure
    Native" if *any* wave is a from-AVS path.

The resulting frame mirrors the ``fact`` column names so every analytics query
works against it unchanged — we simply register it as the ``customer`` table and
point reports at it when "deduplicated" counting is selected.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import segments
from ..config import DIR_FROM_AVS, DIR_OTHER, DIR_TO_AVS
from .cleaning import _as_bool


def build_customer_rollup(fact: pd.DataFrame, as_of: pd.Timestamp) -> pd.DataFrame:
    if fact.empty:
        return fact.copy()

    df = fact.copy()
    # TPID is the authoritative identifier: account names differ between
    # worksheets and source systems, so they are never used for matching.
    df["customer_key"] = (df["tpid_key"] if "tpid_key" in df.columns
                          else segments.tpid_key(df))

    # Wave ordering: Wave-1 first → ascending wave number; missing waves last.
    df["_wave_order"] = df["wave_num"].fillna(9_999)
    df["_created_sort"] = df["created_date"].fillna(pd.Timestamp.max)
    df = df.sort_values(["customer_key", "_wave_order", "_created_sort"])

    g = df.groupby("customer_key", sort=False)
    first = g.first()
    last = g.last()

    out = pd.DataFrame(index=first.index)

    # Identity (one row per customer).
    out["customer_name"] = first["customer_name"]
    out["tpid"] = first["tpid"]
    out["account_id"] = first["account_id"]
    out["task_id"] = first["task_id"]          # representative
    out["n_waves"] = g.size()
    out["phase"] = last["phase"]               # current/last wave

    # First-wave dates.
    out["created_date"] = first["created_date"]
    out["approval_date"] = first["approval_date"]
    out["decline_date"] = first["decline_date"]

    # Last-wave status / dimensions ("current" state of the account).
    out["eos_status"] = last["eos_status"]
    out["current_state"] = last["current_state"]
    out["milestone_status"] = last["milestone_status"]
    out["migration_status_label"] = last["migration_status_label"]
    out["migration_status_code"] = last["migration_status_code"]
    out["ww_region"] = last["ww_region"]
    out["region_geo"] = last["region_geo"]
    out["region"] = last["region"]
    out["area"] = last["area"]
    out["customer_segment"] = last["customer_segment"]
    out["factory_offering"] = last["factory_offering"]
    out["migration_path"] = last["migration_path"]
    out["nomination_status"] = last["nomination_status"]
    out["fcs_flag"] = last["fcs_flag"]
    out["assigned_pm"] = last["assigned_pm"]
    out["closure_date"] = last["actual_end_date"]
    out["actual_end_date"] = last["actual_end_date"]          # alias for date filters
    out["planned_end_date"] = last["planned_end_date"]
    out["next_followup_date"] = last["next_followup_date"]
    out["actual_start_date"] = g["actual_start_date"].min()   # earliest execution start

    # Category membership = ANY wave.
    out["tpid_key"] = first.index.to_series().to_numpy()
    out["generation"] = last["generation"]          # one value per TPID by construction
    out["is_eos_population"] = g["is_eos_population"].any()
    out["migration_category"] = last["migration_category"]
    out["is_avs_target"] = g["is_avs_target"].any()
    out["source_platform"] = last["source_platform"]
    out["target_platform"] = last["target_platform"]
    out["avs_sku"] = g["avs_sku"].apply(_distinct_values)
    out["is_av36_eos"] = g["is_av36_eos"].any()
    out["is_avs_to_azure"] = g["is_from_avs"].any()
    out["is_from_avs"] = out["is_avs_to_azure"]   # uniform scope flag (matches fact)
    out["is_onboard"] = g["is_to_avs"].any()
    out["is_approved"] = g["is_approved"].any()
    out["is_declined"] = g["is_declined"].any()

    # Closure / open driven by the LAST wave's status.
    last_completed = (
        (last["eos_status"] == "Completed")
        | last["current_state"].astype("string").str.contains("done|complete", case=False, na=False)
        | (last["migration_status_code"] == 7)
    )
    last_cancelled = last["eos_status"] == "Cancelled"
    out["is_closed"] = last_completed.to_numpy()
    out["is_cancelled"] = last_cancelled.to_numpy()
    out["is_open"] = ~out["is_closed"] & ~out["is_cancelled"]

    # Representative migration direction + Azure-native target.
    out["migration_direction"] = np.select(
        [_as_bool(out["is_avs_to_azure"]), _as_bool(out["is_onboard"])],
        [DIR_FROM_AVS, DIR_TO_AVS], default=DIR_OTHER)
    from_avs = df[df["is_from_avs"]]
    if not from_avs.empty:
        last_target = from_avs.groupby("customer_key")["azure_target"].last()
        out["azure_target"] = pd.Series(out.index.map(last_target), index=out.index)
    else:
        out["azure_target"] = pd.NA
    out["azure_target"] = out["azure_target"].where(out["is_avs_to_azure"])

    # Summed commercial measures across the customer's waves.
    out["total_acr"] = g["total_acr"].sum(min_count=1)
    out["total_cores"] = g["total_cores"].sum(min_count=1)

    # Aging / cycle time from first creation to closure (or as-of for open).
    as_of = pd.Timestamp(as_of)
    closed_or_now = out["closure_date"].where(out["is_closed"], as_of)
    out["aging_days"] = (closed_or_now - out["created_date"]).dt.days
    out.loc[out["aging_days"] < 0, "aging_days"] = np.nan
    out["cycle_time_days"] = np.where(
        out["is_closed"] & out["closure_date"].notna() & out["created_date"].notna(),
        (out["closure_date"] - out["created_date"]).dt.days, np.nan)
    out["approval_latency_days"] = (out["approval_date"] - out["created_date"]).dt.days

    # Calendar helpers (mirror fact).
    out["created_year"] = out["created_date"].dt.year
    out["created_month"] = out["created_date"].dt.to_period("M").astype("string")
    out["created_quarter"] = out["created_date"].dt.to_period("Q").astype("string")
    out["approval_year"] = out["approval_date"].dt.year
    out["approval_month"] = out["approval_date"].dt.to_period("M").astype("string")
    out["approval_quarter"] = out["approval_date"].dt.to_period("Q").astype("string")

    # Aggregated data-quality flags for the customer.
    out["has_dq_issue"] = g["has_dq_issue"].any()
    out["dq_flags"] = g["dq_flags"].apply(_merge_flags).to_numpy()

    return out.reset_index(drop=True)


def _distinct_values(series: pd.Series) -> str:
    """Distinct non-blank values across a TPID's waves, e.g. every SKU it uses."""
    vals = {str(v).strip() for v in series.dropna() if str(v).strip()}
    return ", ".join(sorted(vals))


def _merge_flags(series: pd.Series) -> str:
    parts: set[str] = set()
    for v in series:
        for piece in str(v).split("; "):
            if piece:
                parts.add(piece)
    return "; ".join(sorted(parts))


def rollup_summary(customer: pd.DataFrame) -> dict:
    """Quick counts used by the UI to explain the dedup effect."""
    return {
        "customers": int(len(customer)),
        "av36_eos": int(customer["is_av36_eos"].sum()) if "is_av36_eos" in customer else 0,
        "avs_to_azure": int(customer["is_avs_to_azure"].sum()) if "is_avs_to_azure" in customer else 0,
        "multi_wave": int((customer["n_waves"] > 1).sum()) if "n_waves" in customer else 0,
    }
