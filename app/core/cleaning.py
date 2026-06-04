"""Data cleaning & enrichment.

Takes the raw source frame plus a canonical->source column mapping and returns a
tidy *fact* frame keyed by canonical field names, with derived analytical
columns (migration direction, Azure-native target, EOS status, approval/closure
flags, aging) and a per-row data-quality flag list.

All transforms here were validated against the real sample export, including its
quirks: numeric-prefixed WW Region values, Indian-style currency grouping
("$1,92,000"), and a column-shifted row where a date landed in Total ACR.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from . import schema
from ..config import DIR_FROM_AVS, DIR_OTHER, DIR_TO_AVS

# Accepted date formats, tried in order.  The export uses MM-DD-YYYY.
_DATE_FORMATS = ("%m-%d-%Y", "%m/%d/%Y", "%Y-%m-%d", "%d-%m-%Y", "%m-%d-%y", "%m/%d/%y")

# Valid customer-segment vocabulary (anything else is flagged as contamination).
_VALID_SEGMENT_TOKENS = ("commercial", "public sector", "enterprise", "smc", "smb",
                         "strategic", "majors", "corporate", "government")


# --------------------------------------------------------------------------- #
# Scalar parsers
# --------------------------------------------------------------------------- #
def parse_date_series(s: pd.Series) -> pd.Series:
    """Parse a string series of dates trying several known formats."""
    s = s.astype("string").str.strip()
    s = s.replace({"": pd.NA, "nan": pd.NA, "NaT": pd.NA, "None": pd.NA})
    out = pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns]")
    remaining = s.notna()
    for fmt in _DATE_FORMATS:
        if not remaining.any():
            break
        parsed = pd.to_datetime(s[remaining], format=fmt, errors="coerce")
        out.loc[remaining] = parsed
        remaining = remaining & out.isna()
    # Final generic pass for anything still unparsed.
    if remaining.any():
        out.loc[remaining] = pd.to_datetime(s[remaining], errors="coerce")
    return out


def _clean_number_token(x) -> float:
    """Strip currency symbols / thousands separators (incl. Indian grouping).

    We reject values that look like a date (e.g. a column-shifted '05-31-2025')
    so they don't masquerade as a huge number.
    """
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return np.nan
    s = str(x).strip()
    if s == "" or s.lower() in ("nan", "none", "n/a", "na", "-"):
        return np.nan
    # Looks like a date -> not a number (contamination guard).
    if re.fullmatch(r"\d{1,2}[-/]\d{1,2}[-/]\d{2,4}", s):
        return np.nan
    neg = s.strip().startswith("(") and s.strip().endswith(")")
    s = re.sub(r"[^0-9.]", "", s)          # drop $, commas, spaces, parens, letters
    if s in ("", "."):
        return np.nan
    try:
        val = float(s)
        return -val if neg else val
    except ValueError:
        return np.nan


def parse_currency_series(s: pd.Series) -> pd.Series:
    return s.map(_clean_number_token).astype("float64")


def parse_number_series(s: pd.Series) -> pd.Series:
    return s.map(_clean_number_token).astype("float64")


def normalize_ww_region(s: pd.Series) -> pd.Series:
    """Strip leading numeric contamination ('1800 Americas - Enterprise')."""
    out = s.astype("string").str.replace(r"^\s*[\d,]+\s+", "", regex=True).str.strip()
    return out.replace({"": pd.NA})


def _wave_num(x) -> float:
    m = re.search(r"(\d+)", str(x))
    return float(m.group(1)) if m else np.nan


def split_migration_status(s: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Split a coded 'N - Label' status into (code:int, label:str)."""
    s = s.astype("string").str.strip()
    code = s.str.extract(r"^\s*(\d+)\s*-").iloc[:, 0]
    code = pd.to_numeric(code, errors="coerce")
    label = s.str.replace(r"^\s*\d+\s*-\s*", "", regex=True).str.strip()
    label = label.where(label.notna() & (label != ""), s)
    return code, label


# --------------------------------------------------------------------------- #
# Derived classifications
# --------------------------------------------------------------------------- #
def migration_direction(path: str) -> str:
    if not path or pd.isna(path):
        return DIR_OTHER
    p = str(path).lower()
    if "from avs" in p:
        return DIR_FROM_AVS
    if "to avs" in p or "egs" in p or "av36" in p or "avs36" in p or "odaa" in p:
        return DIR_TO_AVS
    return DIR_OTHER


def azure_native_target(path: str) -> str:
    """Map an 'AVS → Azure Native' path to its destination service."""
    p = str(path).lower()
    if "sql server mi" in p or "managed instance" in p:
        return "Azure SQL Managed Instance"
    if "sql server db" in p or "sql database" in p:
        return "Azure SQL Database"
    if "sql server iaas" in p or ("sql" in p and "iaas" in p):
        return "Azure VM (SQL on IaaS)"
    if "oss db" in p or "ossdb" in p or "postgre" in p or "mysql" in p:
        return "Azure DB for PostgreSQL/MySQL"
    if "windows server" in p or "windows" in p:
        return "Azure VM (Windows)"
    if "linux" in p:
        return "Azure VM / AKS (Linux)"
    if "odaa" in p or "oracle" in p:
        return "Oracle DB@Azure"
    if "aks" in p or "kubernetes" in p:
        return "Azure Kubernetes Service"
    return "Azure Native (Other)"


def _derive_eos_status(row: pd.Series, as_of: pd.Timestamp) -> str:
    """Unified operational/EOS status from several raw signals.

    Priority: terminal states first (Completed / Cancelled), then Blocked,
    then schedule-driven (Delayed / At Risk), else On Track.
    """
    code = row.get("migration_status_code")
    label = str(row.get("migration_status_label") or "").lower()
    state = str(row.get("current_state") or "").strip().lower()
    milestone = str(row.get("milestone_status") or "").strip().lower()
    aend = row.get("actual_end_date")
    pend = row.get("planned_end_date")
    followup = row.get("next_followup_date")

    completed = (
        code == 7 or "complete" in label or "done" in state
        or milestone == "completed" or pd.notna(aend)
    )
    if completed:
        return "Completed"
    if code == 6 or "cancel" in label or "archiv" in label or milestone == "cancelled":
        return "Cancelled"
    if state.startswith("blocked") or "blocked" in state:
        return "Blocked"
    if code == 5 or "defer" in label or "defer" in state:
        return "At Risk"
    # Schedule-driven risk
    if pd.notna(pend) and pd.isna(aend) and pend < as_of:
        return "Delayed"
    if pd.notna(followup) and followup < as_of:
        return "At Risk"
    if state.startswith("waiting"):
        return "At Risk"
    return "On Track"


# --------------------------------------------------------------------------- #
# Main entry point
# --------------------------------------------------------------------------- #
def build_fact_frame(
    raw: pd.DataFrame,
    mapping: dict[str, str | None],
    as_of: pd.Timestamp | None = None,
) -> tuple[pd.DataFrame, dict]:
    """Build the tidy fact frame + a cleaning report.

    ``mapping`` maps canonical key -> source column name (or None if unmapped).
    Returns ``(fact_df, report)`` where report summarises parse stats and any
    data-quality issues encountered.
    """
    n = len(raw)
    fact = pd.DataFrame(index=raw.index)
    report: dict = {"n_rows": n, "unmapped": [], "parse": {}, "dq": {}}

    # 1) Pull mapped source columns into canonical names (raw strings first).
    for f in schema.CANONICAL_FIELDS:
        src = mapping.get(f.key)
        if src and src in raw.columns:
            fact[f.key] = raw[src].astype("string")
        else:
            fact[f.key] = pd.Series(pd.NA, index=raw.index, dtype="string")
            if f.required:
                report["unmapped"].append(f.key)

    # Track per-row data-quality notes.
    dq_flags: list[list[str]] = [[] for _ in range(n)]

    def flag(mask: pd.Series, msg: str, bucket: str):
        idx = np.where(mask.to_numpy())[0]
        for i in idx:
            dq_flags[i].append(msg)
        if len(idx):
            report["dq"][bucket] = report["dq"].get(bucket, 0) + int(len(idx))

    # 2) Dates.
    for key in schema.DATE_KEYS:
        parsed = parse_date_series(fact[key])
        nonblank = fact[key].notna() & (fact[key].astype("string").str.strip() != "")
        bad = nonblank & parsed.isna()
        flag(bad, f"Unparseable date in '{schema.CANONICAL_BY_KEY[key].label}'", "bad_date")
        fact[key] = parsed
        report["parse"][key] = int(parsed.notna().sum())

    # 3) Currency + numeric (with contamination detection).
    for key in schema.CURRENCY_KEYS:
        raw_str = fact[key].astype("string")
        looks_date = raw_str.str.match(r"^\s*\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\s*$", na=False)
        flag(looks_date, f"Date value found in numeric field '{schema.CANONICAL_BY_KEY[key].label}'",
             "contaminated_numeric")
        fact[key] = parse_currency_series(raw_str)
    for key in schema.NUMBER_KEYS:
        raw_str = fact[key].astype("string")
        has_currency = raw_str.str.contains(r"\$", na=False)
        flag(has_currency, f"Currency value found in count field '{schema.CANONICAL_BY_KEY[key].label}'",
             "contaminated_numeric")
        # null out clearly-contaminated (currency in a core-count) values
        cleaned = parse_number_series(raw_str)
        cleaned = cleaned.where(~has_currency, np.nan)
        fact[key] = cleaned

    # 4) Region normalisation + segment validation.
    if "ww_region" in fact:
        fact["ww_region_raw"] = fact["ww_region"]
        cleaned_region = normalize_ww_region(fact["ww_region"])
        dirty = fact["ww_region"].notna() & (cleaned_region != fact["ww_region"].str.strip())
        flag(dirty, "WW Region had numeric prefix (cleaned)", "dirty_region")
        fact["ww_region"] = cleaned_region.fillna("Unknown")

    seg = fact["customer_segment"].astype("string").str.strip()
    seg_norm = seg.str.lower()
    bad_seg = seg.notna() & (seg != "") & ~seg_norm.apply(
        lambda v: any(tok in v for tok in _VALID_SEGMENT_TOKENS)
    )
    flag(bad_seg, "Invalid Customer Segment value", "bad_segment")
    fact["customer_segment"] = seg.where(~bad_seg, "Unknown").fillna("Unknown")

    # 5) Categorical tidy-ups & derived attributes.
    fact["wave_num"] = fact["phase"].map(_wave_num)
    fact["migration_direction"] = fact["migration_path"].map(migration_direction)
    fact["azure_target"] = np.where(
        fact["migration_direction"] == DIR_FROM_AVS,
        fact["migration_path"].map(azure_native_target),
        pd.NA,
    )
    code, label = split_migration_status(fact["migration_status"])
    fact["migration_status_code"] = code
    fact["migration_status_label"] = label.fillna("Unknown")

    # Fill key categoricals so group-bys never drop rows.
    for key in ["ww_region", "region", "area", "factory_offering", "migration_path",
                "nomination_status", "current_state", "milestone_status", "phase"]:
        fact[key] = fact[key].astype("string").replace({"": pd.NA}).fillna("Unknown")

    as_of = pd.Timestamp(as_of) if as_of is not None else _effective_today(fact)
    report["as_of"] = as_of

    # 6) Operational / EOS status.
    fact["eos_status"] = fact.apply(lambda r: _derive_eos_status(r, as_of), axis=1)

    # 7) Approval / closure / open flags + aging.
    fact["is_approved"] = (
        fact["approval_date"].notna()
        | fact["nomination_status"].str.contains("approv", case=False, na=False)
    )
    fact["is_declined"] = (
        fact["decline_date"].notna()
        | fact["nomination_status"].str.contains("declin|reject", case=False, na=False)
    )
    fact["is_closed"] = (
        (fact["migration_status_code"] == 7)
        | fact["current_state"].str.contains("done|complete", case=False, na=False)
        | fact["milestone_status"].str.contains("complete", case=False, na=False)
        | fact["actual_end_date"].notna()
    )
    fact["is_cancelled"] = fact["eos_status"] == "Cancelled"
    fact["is_open"] = ~fact["is_closed"] & ~fact["is_cancelled"]

    # Closure date: actual end, else approval+done fallback.
    fact["closure_date"] = fact["actual_end_date"]

    created = fact["created_date"]
    closed_or_now = fact["closure_date"].where(fact["is_closed"], as_of)
    fact["aging_days"] = (closed_or_now - created).dt.days
    fact.loc[fact["aging_days"] < 0, "aging_days"] = np.nan
    # cycle time only for closed items
    fact["cycle_time_days"] = np.where(
        fact["is_closed"] & fact["closure_date"].notna() & created.notna(),
        (fact["closure_date"] - created).dt.days, np.nan,
    )
    # approval latency (created -> approval)
    fact["approval_latency_days"] = (fact["approval_date"] - created).dt.days

    # Ordering sanity: approval before creation.
    bad_order = (fact["approval_date"].notna() & created.notna()
                 & (fact["approval_date"] < created))
    flag(bad_order, "Approval date precedes creation date", "date_order")

    # Missing critical dims.
    flag(fact["created_date"].isna(), "Missing creation date", "missing_created")

    # 8) Calendar helpers for trends (off created date).
    fact["created_year"] = created.dt.year
    fact["created_month"] = created.dt.to_period("M").astype("string")
    fact["created_quarter"] = created.dt.to_period("Q").astype("string")
    appr = fact["approval_date"]
    fact["approval_year"] = appr.dt.year
    fact["approval_month"] = appr.dt.to_period("M").astype("string")
    fact["approval_quarter"] = appr.dt.to_period("Q").astype("string")

    # 9) Attach the per-row DQ flags.
    fact["dq_flags"] = ["; ".join(f) for f in dq_flags]
    fact["has_dq_issue"] = fact["dq_flags"].str.len() > 0
    report["dq_rows"] = int(fact["has_dq_issue"].sum())

    # Duplicate task ids.
    if fact["task_id"].notna().any():
        dup = fact["task_id"].duplicated(keep=False) & fact["task_id"].notna()
        report["duplicate_task_ids"] = int(dup.sum())

    return fact, report


def _effective_today(fact: pd.DataFrame) -> pd.Timestamp:
    """Latest real activity date in the data (used as default 'as-of')."""
    cols = ["approval_date", "created_date", "actual_end_date", "actual_start_date"]
    candidates = [fact[c].max() for c in cols if c in fact and fact[c].notna().any()]
    if candidates:
        return max(candidates).normalize()
    return pd.Timestamp.today().normalize()
