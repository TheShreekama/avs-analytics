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

from . import metrics, schema, segments
from .nulls import as_bool_mask, is_blank
from ..config import DIR_FROM_AVS, DIR_OTHER, DIR_TO_AVS

# Accepted date formats.  The export nominally uses MM-DD-YYYY, but real files
# arrive with day-first values, month names, ISO stamps and time-of-day suffixes.
# ``_DATE_FORMATS_MONTH_FIRST`` / ``_DAY_FIRST`` differ only in how they read an
# ambiguous d/m pair; which one leads is decided per column (see ``_prefers_day_first``).
_DATE_FORMATS_COMMON = (
    "%Y-%m-%d", "%Y/%m/%d", "%Y%m%d",
    "%d-%b-%Y", "%d %b %Y", "%d-%b-%y", "%b %d %Y", "%b %d, %Y", "%d %B %Y", "%B %d, %Y",
)
_DATE_FORMATS_MONTH_FIRST = ("%m-%d-%Y", "%m/%d/%Y", "%m.%d.%Y", "%m-%d-%y", "%m/%d/%y")
_DATE_FORMATS_DAY_FIRST = ("%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y", "%d-%m-%y", "%d/%m/%y")

# Excel / Google-Sheets serial day numbers, counted from 1899-12-30.  A date cell
# that was never *formatted* as a date exports as this bare number.
_EXCEL_EPOCH = pd.Timestamp("1899-12-30")
_EXCEL_SERIAL_MIN = 15000        # 1941-01-16 — below this it is a plain number, not a date
_EXCEL_SERIAL_MAX = 80000        # 2119-01-25

# A trailing midnight/time stamp we can drop before matching a date-only format.
_TIME_SUFFIX_RE = re.compile(
    r"[ T]\d{1,2}:\d{2}(:\d{2}(\.\d+)?)?\s*(am|pm)?\s*(z|[+-]\d{2}:?\d{2})?$", re.I)
# An all-numeric d/m/y triple, used to detect whether a column is day-first.
_DMY_RE = re.compile(r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})$")

# Valid customer-segment vocabulary (anything else is flagged as contamination).
_VALID_SEGMENT_TOKENS = ("commercial", "public sector", "enterprise", "smc", "smb",
                         "strategic", "majors", "corporate", "government")


# --------------------------------------------------------------------------- #
# Scalar parsers
# --------------------------------------------------------------------------- #
def _excel_serial_dates(s: pd.Series) -> pd.Series:
    """Convert bare Excel/Sheets serial day numbers to timestamps.

    An unformatted date cell exports as a number ("45855"), which no date format
    matches — the single biggest source of "unparseable date" rows in real files.
    """
    nums = pd.to_numeric(s, errors="coerce")
    out = pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns]")
    ok = nums.notna() & nums.between(_EXCEL_SERIAL_MIN, _EXCEL_SERIAL_MAX)
    if ok.any():
        days = pd.to_timedelta(nums[ok].astype("float64").round(), unit="D")
        out.loc[ok] = _EXCEL_EPOCH + days
    return out


def _prefers_day_first(s: pd.Series) -> bool:
    """Decide whether an all-numeric date column is day-first or month-first.

    A value whose first component exceeds 12 can only be a day; one whose second
    component exceeds 12 can only be a month-first date.  Whichever appears more
    often wins, so a whole column is read consistently instead of each value being
    guessed on its own (which silently turns 05-06 into May 6th in a UK-style file).
    """
    day_first = month_first = 0
    for val in s.dropna().unique()[:2000]:
        m = _DMY_RE.match(str(val))
        if not m:
            continue
        first, second = int(m.group(1)), int(m.group(2))
        if first > 12 >= second:
            day_first += 1
        elif second > 12 >= first:
            month_first += 1
    return day_first > month_first


def parse_date_series(s: pd.Series) -> pd.Series:
    """Parse a column of dates in whatever shape the export happens to use.

    Handles: real datetime values, Excel serial numbers, ISO stamps (with or
    without a timezone), month names, and d/m/y triples in either order — the
    order being inferred per column rather than per value.
    """
    if pd.api.types.is_datetime64_any_dtype(s):
        return pd.to_datetime(s, errors="coerce").dt.tz_localize(None) \
            if getattr(s.dtype, "tz", None) else pd.to_datetime(s, errors="coerce")

    s = s.astype("string").str.strip()
    s = s.replace({"": pd.NA, "nan": pd.NA, "NaT": pd.NA, "None": pd.NA, "null": pd.NA,
                   "N/A": pd.NA, "n/a": pd.NA, "NA": pd.NA, "-": pd.NA, "--": pd.NA})
    # A bare year carries no day or month; parsing it as the 1st of January would
    # invent precision, so leave it unparsed (and flagged) instead.
    s = s.mask(s.str.fullmatch(r"(19|20|21)\d{2}", na=False), pd.NA)
    out = pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns]")

    # 1) Excel serial numbers.
    out.loc[:] = _excel_serial_dates(s)
    remaining = s.notna() & out.isna()
    if not remaining.any():
        return out.dt.normalize()

    # 2) Known formats, with the ambiguous d/m pair ordered to suit the column.
    bare = s.where(~remaining, s.str.replace(_TIME_SUFFIX_RE, "", regex=True).str.strip())
    ambiguous = (_DATE_FORMATS_DAY_FIRST + _DATE_FORMATS_MONTH_FIRST
                 if _prefers_day_first(bare[remaining])
                 else _DATE_FORMATS_MONTH_FIRST + _DATE_FORMATS_DAY_FIRST)
    for fmt in _DATE_FORMATS_COMMON + ambiguous:
        if not remaining.any():
            return out.dt.normalize()
        out.loc[remaining] = pd.to_datetime(bare[remaining], format=fmt, errors="coerce")
        remaining = s.notna() & out.isna()

    # 3) Generic pass for anything left.  ``utc=True`` keeps mixed-timezone input
    #    from raising (it does so even under errors="coerce"); the offset is then
    #    dropped, since every date in this dataset is a calendar day.
    if remaining.any():
        try:
            generic = pd.to_datetime(s[remaining], errors="coerce", utc=True,
                                     format="mixed", dayfirst=_prefers_day_first(bare))
            out.loc[remaining] = generic.dt.tz_localize(None)
        except (ValueError, TypeError):
            pass
    return out.dt.normalize()


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


def geo_region(s: pd.Series) -> pd.Series:
    """Reduce a WW Region to its geography only.

    The export combines geography and segment ("Americas - Enterprise"); reports
    show region as the geography (Americas / EMEA / ASIA), with the segment kept
    separately in ``customer_segment``.  Takes the part before the first ' - '.
    """
    out = s.astype("string").str.split(r"\s*[-–]\s*", n=1, regex=True).str[0].str.strip()
    return out.replace({"": pd.NA}).fillna("Unknown")


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
    # Missingness is tested first and by ``is_blank``: an unmapped Primary
    # Migration Path column makes every value ``pd.NA``, and ``not pd.NA`` is a
    # TypeError, not False.
    if is_blank(path):
        return DIR_OTHER
    p = str(path).lower()
    if "from avs" in p:
        return DIR_FROM_AVS
    if "to avs" in p or "egs" in p or "av36" in p or "avs36" in p or "odaa" in p:
        return DIR_TO_AVS
    return DIR_OTHER


def azure_native_target(path: str) -> str:
    """Map an 'AVS → Azure Native' path to its destination service."""
    if is_blank(path):
        return "Azure Native (Other)"
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


# SKU-style markers may appear glued to other text ("AV36P-EGS"), so they are
# matched anywhere; the short words are matched as whole tokens only, so that a
# value like "Geospatial" cannot masquerade as an EOS nomination.
# Offering/path markers.  The real export writes "AV36/AV36P/AV52 - EOS"; AV64 is a
# host SKU that never appears in a migration path, and a string that did carry it
# would still match on the EOS token below.
_EOS_SKU_MARKERS = ("av36", "avs36", "av36p", "avs36p", "av52", "avs52",
                    "endofsupport", "endoflife")
_EOS_WORD_MARKERS = ("eos", "egs", "eol")


def is_av36_eos_path(*values) -> bool:
    """True if any value denotes an AV36 / EOS (End-of-Support) nomination.

    Real exports carry the marker in different places and spellings — "AVS36 - EGS"
    in the migration path, "AV36/AV36P/AV52 - EOS" as the factory offering — so
    every offering-ish field is checked, not just the migration path.
    """
    for value in values:
        text = str(value).lower()
        compact = re.sub(r"[^a-z0-9]", "", text)
        if any(k in compact for k in _EOS_SKU_MARKERS):
            return True
        tokens = set(re.split(r"[^a-z0-9]+", text))
        if tokens & set(_EOS_WORD_MARKERS):
            return True
    return False


def _as_bool(cond) -> np.ndarray:
    """Coerce a (possibly nullable) boolean condition to a plain numpy bool array.

    ``np.select`` rejects pandas' nullable ``boolean`` dtype, which any comparison
    against a column containing <NA> yields — e.g. a "Migration Status" with no
    numeric prefix ("Cancelled", "On Hold", blank) leaves ``migration_status_code``
    null, and ``code.eq(7)`` then carries <NA>.  Missing means "condition not met".
    """
    if isinstance(cond, pd.Series):
        return cond.fillna(False).to_numpy(dtype=bool)
    return np.asarray(cond, dtype=bool)


def derive_eos_status(fact: pd.DataFrame, as_of: pd.Timestamp) -> pd.Series:
    """Unified operational/EOS status from several raw signals (vectorised).

    Priority (first match wins): Completed → Cancelled → Blocked → deferred
    (At Risk) → schedule-overdue (Delayed) → waiting/follow-up overdue (At Risk)
    → On Track.  Vectorised with ``np.select`` so it scales to 500k+ rows.
    """
    code = fact["migration_status_code"]
    label = fact["migration_status_label"].astype("string").str.lower().fillna("")
    state = fact["current_state"].astype("string").str.strip().str.lower().fillna("")
    milestone = fact["milestone_status"].astype("string").str.strip().str.lower().fillna("")
    aend = fact["actual_end_date"]
    pend = fact["planned_end_date"]
    followup = fact["next_followup_date"]

    completed = (code.eq(7) | label.str.contains("complete", na=False)
                 | state.str.contains("done", na=False) | milestone.eq("completed")
                 | aend.notna())
    cancelled = (code.eq(6) | label.str.contains("cancel|archiv", regex=True, na=False)
                 | milestone.eq("cancelled"))
    blocked = state.str.contains("blocked", na=False)
    deferred = (code.eq(5) | label.str.contains("defer", na=False)
                | state.str.contains("defer", na=False))
    delayed = pend.notna() & aend.isna() & (pend < as_of)
    waiting = (followup.notna() & (followup < as_of)) | state.str.startswith("waiting", na=False)

    return pd.Series(np.select(
        [_as_bool(c) for c in (completed, cancelled, blocked, deferred, delayed, waiting)],
        ["Completed", "Cancelled", "Blocked", "At Risk", "Delayed", "At Risk"],
        default="On Track"), index=fact.index)


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
    report: dict = {"n_rows": n, "unmapped": [], "parse": {}, "dq": {}, "dq_samples": {}}

    # 1) Pull mapped source columns into canonical names (raw strings first).
    for f in schema.CANONICAL_FIELDS:
        src = mapping.get(f.key)
        if src and src in raw.columns:
            fact[f.key] = raw[src].astype("string")
        else:
            fact[f.key] = pd.Series(pd.NA, index=raw.index, dtype="string")
            if f.required:
                report["unmapped"].append(f.key)

    # Which file each row came from, when the dataset was assembled from
    # several uploads — the only way to answer "why is this account missing"
    # once the files have been concatenated.
    if schema.SOURCE_FILE_COLUMN in raw.columns:
        fact["source_file"] = raw[schema.SOURCE_FILE_COLUMN].astype("string")

    # Track per-row data-quality notes.
    dq_flags: list[list[str]] = [[] for _ in range(n)]

    def flag(mask: pd.Series, msg: str, bucket: str):
        # ``as_bool_mask`` first: a mask built from nullable columns carries
        # ``pd.NA`` wherever a comparison had nothing to compare, and numpy
        # cannot evaluate that.
        idx = np.where(as_bool_mask(mask, fact.index).to_numpy())[0]
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
        if bad.any():
            # Keep a few offending values: a bare count ("bad date: 1641") says
            # nothing about which format the parser is missing.
            samples = fact.loc[bad, key].dropna().unique()[:5]
            report["dq_samples"].setdefault("bad_date", []).append(
                (schema.CANONICAL_BY_KEY[key].label, int(bad.sum()),
                 [str(v) for v in samples]))
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
        # Geography-only region (Americas / EMEA / ASIA), segment dropped.
        fact["region_geo"] = geo_region(fact["ww_region"])

    seg = fact["customer_segment"].astype("string").str.strip()
    # ``apply`` hands <NA> straight to the lambda when the column is unmapped or
    # partly blank, so match on the filled text and gate on the original values.
    seg_norm = seg.str.lower().fillna("")
    bad_seg = seg.notna() & (seg != "") & ~seg_norm.map(
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
    # Wave-level flags used by the customer-rollup (dedup) layer.
    # Offering text repeats heavily across rows, so classify each distinct
    # combination once rather than per row (the 500k-row target).
    offering_text = (fact["migration_path"].fillna("") + " | "
                     + fact["factory_offering"].fillna("") + " | "
                     + fact["linked_offering"].fillna(""))
    eos_lookup = {v: is_av36_eos_path(v) for v in offering_text.unique()}
    fact["is_av36_eos"] = as_bool_mask(offering_text.map(eos_lookup), fact.index)
    fact["is_from_avs"] = (fact["migration_direction"] == DIR_FROM_AVS)
    fact["is_to_avs"] = (fact["migration_direction"] == DIR_TO_AVS)

    # Source / target platform, from the same distinct offering combinations.
    src_lookup = {v: segments.source_platform(v) for v in offering_text.unique()}
    tgt_lookup = {v: segments.target_platform(v) for v in offering_text.unique()}
    fact["source_platform"] = offering_text.map(src_lookup)
    fact["target_platform"] = offering_text.map(tgt_lookup)
    # "All AVS Migrations" = every nomination whose target platform is AVS,
    # whatever it is coming from (on-premises, VMG, AWS/VMC, AVS, EOS refresh).
    fact["is_avs_target"] = fact["target_platform"].eq(segments.PLATFORM_AVS)
    fact["avs_sku_codes"] = fact["avs_sku"].map(lambda v: " ".join(sorted(segments.sku_codes(v))))

    # TPID is the authoritative identifier for every join, lookup and count, and
    # the generation is decided from the SKUs of *all* waves belonging to it.
    fact["tpid_key"] = segments.tpid_key(fact)
    gen_by_tpid = segments.generation_by_tpid(fact)
    fact["generation"] = fact["tpid_key"].map(gen_by_tpid).fillna(segments.GEN_UNCLASSIFIED)
    # An "AVS Migration - Gen1/Gen2" tag on ANY wave makes the whole account an
    # EOS Migration account, so membership follows the generation.
    fact["is_eos_population"] = segments.eos_population(fact)
    fact["migration_category"] = segments.category_label_series(fact)
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
    fact["eos_status"] = derive_eos_status(fact, as_of)

    # 7) Approval / closure / open flags + aging.
    fact["is_approved"] = as_bool_mask(
        fact["approval_date"].notna()
        | fact["nomination_status"].str.contains("approv", case=False, na=False),
        fact.index)
    fact["is_declined"] = as_bool_mask(
        fact["decline_date"].notna()
        | fact["nomination_status"].str.contains("declin|reject", case=False, na=False),
        fact.index)
    fact["is_closed"] = (
        (fact["migration_status_code"] == 7)
        | fact["current_state"].str.contains("done|complete", case=False, na=False)
        | fact["milestone_status"].str.contains("complete", case=False, na=False)
        | fact["actual_end_date"].notna()
    )
    fact["is_cancelled"] = fact["eos_status"] == "Cancelled"
    fact["is_closed"] = as_bool_mask(fact["is_closed"], fact.index)
    fact["is_cancelled"] = as_bool_mask(fact["is_cancelled"], fact.index)
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


def nomination_date(fact: pd.DataFrame) -> pd.Series:
    """The date a wave is nominated on — its approval date, else its creation date.

    One definition, used both to place a wave in a fiscal year and to decide
    whether it is inside the reporting floor.
    """
    approved = pd.to_datetime(fact.get("approval_date"), errors="coerce")
    created = pd.to_datetime(fact.get("created_date"), errors="coerce")
    return approved.fillna(created)


def apply_reporting_floor(fact: pd.DataFrame, floor_fy: int,
                          fy_start_month: int = 7) -> tuple[pd.DataFrame, dict]:
    """Drop waves nominated before the reporting floor fiscal year.

    Applied as the file is read, so the floor is a property of the *data* rather
    than of any one page: every chart, table, total, rollup and export downstream
    inherits it, and "All time" means the floor onwards everywhere.

    A wave belongs to the fiscal year of its nomination date.  A wave carrying
    neither an approval nor a creation date cannot be shown to be out of scope,
    so it stays — the floor excludes what it can prove is old, never what it
    merely cannot date.
    """
    start = metrics.named_fiscal_year_start(floor_fy, fy_start_month)
    dated = nomination_date(fact)
    before = dated.notna() & (dated < start)
    summary = {
        "floor_fy": f"FY{int(floor_fy) % 100:02d}",
        "floor_start": start,
        "excluded_rows": int(before.sum()),
        "excluded_accounts": 0,
    }
    if summary["excluded_rows"] and "tpid_key" in fact.columns:
        dropped = fact.loc[before, "tpid_key"]
        kept = fact.loc[~before, "tpid_key"]
        summary["excluded_accounts"] = int(dropped[~dropped.isin(set(kept))].nunique())
    return fact.loc[~before].reset_index(drop=True), summary


def _effective_today(fact: pd.DataFrame) -> pd.Timestamp:
    """Default reporting as-of date: **today**.

    Deriving it from the data's latest activity date used to drag every window
    forward whenever a single row carried a far-future date — "This FY" would
    resolve to a fiscal year the business is not in yet.  Today is the honest
    anchor; the sidebar's as-of control still overrides it for a back-dated read.
    """
    return pd.Timestamp.today().normalize()
