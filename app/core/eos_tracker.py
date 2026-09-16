"""The manual EOS tracking sheet, read as an overlay on the FDO dataset.

The FDO export is the system of record for *nominations* — who owns the account,
which factory delivers it, what it is worth.  The EOS programme keeps its own
spreadsheet alongside it, maintained by hand, which is the system of record for
three things the export either does not carry or carries less reliably:

* **Target SDDC Generation** — whether an account is landing on Gen-1 or Gen-2
  hardware.  In the export this has to be inferred from an "AVS Migration -
  Gen1/Gen2" tag that is often missing; here it is stated.
* **Migration Start Date** — a real date, rather than the
  earliest-started-wave derivation :func:`app.core.kpi.migration_start_dates`
  has to fall back on.
* **Actual Migration End Date** — likewise, when the migration actually ended.

The sheet is keyed on **TPID and nothing else**: every other detail an EOS
report needs — Factory PM, Solution Architect, region, offering, ACR, waves —
is looked up in the FDO dataset by that TPID, so the tracker never has to repeat
(or contradict) them.  A TPID the FDO dataset does not hold is reported as
unmatched rather than invented: without a nomination behind it there is no
offering, no ACR and no wave to report on.

Nothing here overwrites a number.  The tracker *leads* and the export *follows*:
each overlay column is carried beside the derived one, and the rules in
:mod:`app.core.kpi` and :mod:`app.core.cleaning` take the tracker's answer when
it has one and their own when it does not.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import pandas as pd

from . import segments
from .nulls import as_bool_mask, is_blank


@dataclass(frozen=True)
class TrackerField:
    """One column of the tracking sheet, and how to recognise it."""
    key: str
    label: str
    source_default: str
    dtype: str = "text"              # text | date | number | generation
    synonyms: tuple[str, ...] = field(default_factory=tuple)
    required: bool = False
    description: str = ""


#: The columns the EOS programme's sheet is read for.  Everything else in the
#: file is left alone — the sheet carries working columns the reports have no
#: use for, and a tracker that grows a column must not stop loading.
TRACKER_FIELDS: tuple[TrackerField, ...] = (
    TrackerField("tpid", "TPID", "TPID", "text", ("t-pid", "top parent id"),
                 required=True,
                 description="The only key. Every other account detail is looked "
                             "up in the FDO dataset by it."),
    TrackerField("customer_name", "Customer", "Customer", "text",
                 ("customer name", "account", "account name", "company")),
    TrackerField("region", "Region", "Region", "text",
                 ("ww region", "geo", "area")),
    TrackerField("migration_status", "Migration Status", "Migration Status", "text",
                 ("status", "programme status")),
    TrackerField("current_state", "Current State", "Current State", "text",
                 ("state", "rag")),
    TrackerField("target_generation", "Target SDDC Generation",
                 "Target SDDC Generation", "generation",
                 ("sddc generation", "target generation", "generation",
                  "target sddc gen"),
                 description="Gen1 or Gen2 — the generation the account is "
                             "landing on. Decides the account's generation "
                             "wherever it is filled in."),
    TrackerField("sddcs_in_scope", "Total SDDCs in Scope for Migration",
                 "Total SDDCs in Scope for Migration", "number",
                 ("sddcs in scope", "total sddcs", "sddc in scope",
                  "sddcs in scope for migration")),
    TrackerField("sddcs_migrated", "Number of SDDCs Migrated",
                 "Number of SDDCs Migrated", "number",
                 ("sddcs migrated", "no of sddcs migrated", "sddc migrated")),
    TrackerField("migration_start_date", "Migration Start Date",
                 "Migration Start Date", "date",
                 ("start date", "actual migration start date",
                  "migration start")),
    TrackerField("migration_end_date", "Actual Migration End Date",
                 "Actual Migration End Date", "date",
                 ("migration end date", "actual migration end", "end date",
                  "actual end date", "completion date")),
)

TRACKER_BY_KEY = {f.key: f for f in TRACKER_FIELDS}

#: The columns the overlay writes onto the fact frame, prefixed so nothing can
#: be mistaken for an FDO column.  ``eos_tracked`` says the TPID was found in
#: the sheet at all, which is what every "does the tracker answer for this
#: account" test reads.
TRACKED_FLAG = "eos_tracked"
OVERLAY_COLUMNS: dict[str, str] = {
    "target_generation": "eos_target_generation",
    "migration_start_date": "eos_start_date",
    "migration_end_date": "eos_end_date",
    "sddcs_in_scope": "eos_sddcs_in_scope",
    "sddcs_migrated": "eos_sddcs_migrated",
    "migration_status": "eos_tracker_status",
    "current_state": "eos_tracker_state",
    "region": "eos_tracker_region",
    "customer_name": "eos_tracker_customer",
}

#: Where an account's generation was decided, carried per row so a reader can
#: see which accounts the tracker is answering for.
GENERATION_SOURCE = "generation_source"
SOURCE_TRACKER = "EOS tracker"
SOURCE_TAGS = "Tags"
SOURCE_NONE = "Not stated"


# --------------------------------------------------------------------------- #
# Header matching
# --------------------------------------------------------------------------- #
def _norm(value) -> str:
    text = str(value).lower().strip()
    text = re.sub(r"[\(\)\[\]\.,/\-_#]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def auto_map(headers: list[str]) -> dict[str, str | None]:
    """Tracker key -> the header that carries it, or None.

    Exact match first, then a normalised match against the expected header, the
    label or any synonym, then a contains-style fallback.  The same three-step
    shape :func:`app.core.schema.auto_map` uses, kept separate because the
    tracking sheet is a different document with a vocabulary of its own.
    """
    normalised = {h: _norm(h) for h in headers}
    used: set[str] = set()
    out: dict[str, str | None] = {}
    for f in TRACKER_FIELDS:
        match = None
        for h in headers:
            if h not in used and str(h).strip().lower() == f.source_default.lower():
                match = h
                break
        if match is None:
            targets = {_norm(f.source_default), _norm(f.label),
                       *(_norm(s) for s in f.synonyms)}
            for h, nh in normalised.items():
                if h not in used and nh in targets:
                    match = h
                    break
        if match is None:
            targets = [_norm(f.source_default), *(_norm(s) for s in f.synonyms)]
            for h, nh in normalised.items():
                if h in used:
                    continue
                if f.dtype == "date" and "date" not in nh:
                    continue
                if any(t and (t in nh or nh in t) for t in targets):
                    match = h
                    break
        if match is not None:
            used.add(match)
        out[f.key] = match
    return out


# --------------------------------------------------------------------------- #
# Generation
# --------------------------------------------------------------------------- #
#: "Gen1", "GEN 2", "Target Gen-1" — the sheet is filled in by hand, so the
#: marker is matched against the cell stripped to letters and digits.
_GEN_MARKERS = ((segments.GEN_1, "gen1"), (segments.GEN_2, "gen2"))


def normalise_generation(value) -> str | None:
    """"Gen1"/"Gen2" as the generation the rest of the app names them, or None.

    A cell nobody filled in, or one carrying something the programme does not
    recognise as a generation, returns ``None`` — which is what sends the
    account back to the Tags rule rather than putting it in a made-up bucket.
    """
    if is_blank(value):
        return None
    compact = re.sub(r"[^a-z0-9]", "", str(value).lower())
    for generation, marker in _GEN_MARKERS:
        if marker in compact:
            return generation
    return None


# --------------------------------------------------------------------------- #
# Reading the sheet
# --------------------------------------------------------------------------- #
def build_tracker(raw: pd.DataFrame,
                  mapping: dict[str, str | None] | None = None
                  ) -> tuple[pd.DataFrame, dict]:
    """The tracking sheet as one tidy row per TPID, plus a report on the read.

    A sheet can hold several rows for one account — one per SDDC, or one per
    update — so the rows are rolled up the way the programme reads them:

    * **Target SDDC Generation** — the first generation stated; Gen-1 wins when
      an account's rows disagree, matching :func:`app.core.segments.classify_generation`,
      and the disagreement is reported rather than silently resolved.
    * **Migration Start Date** — the **earliest** stated: the migration started
      when its first piece did.
    * **Actual Migration End Date** — the **latest** stated: it ended when its
      last piece did.
    * **SDDC counts** — summed across the account's rows.
    * Everything else — the first non-blank value.

    Nothing is second-guessed: an account the sheet gives an end date is an
    account the programme says has ended.  Where that sits oddly against its own
    SDDC counts — an end date with migrations still outstanding — the account is
    counted as the sheet states and listed under :func:`inconsistencies`, which
    is where a disagreement belongs.

    Returns ``(tracker, report)``; ``tracker`` is indexed by nothing and carries
    ``tpid_key`` so it joins straight onto the fact frame.
    """
    report: dict = {"rows": int(len(raw)), "accounts": 0, "unmapped": [],
                    "extra_columns": [], "generation_conflicts": [],
                    "no_generation": 0, "with_start": 0, "with_end": 0}
    if raw is None or raw.empty:
        return _empty_tracker(), report

    # Imported here, not at the top: ``cleaning`` imports this module to apply
    # the overlay, so a module-level import back into it would be circular.
    from .cleaning import parse_date_series, parse_number_series

    mapping = auto_map(list(raw.columns)) if mapping is None else mapping
    report["mapping"] = dict(mapping)
    report["unmapped"] = [f.key for f in TRACKER_FIELDS if not mapping.get(f.key)]
    claimed = {v for v in mapping.values() if v}
    report["extra_columns"] = [str(c) for c in raw.columns if c not in claimed]
    if not mapping.get("tpid"):
        raise ValueError(
            "The EOS tracking sheet has no TPID column. TPID is the only key the "
            "sheet is joined on, so without it nothing can be matched to the FDO "
            f"dataset. Columns found: {', '.join(map(str, raw.columns))}.")

    tidy = pd.DataFrame(index=raw.index)
    for f in TRACKER_FIELDS:
        src = mapping.get(f.key)
        values = (raw[src].astype("string") if src and src in raw.columns
                  else pd.Series(pd.NA, index=raw.index, dtype="string"))
        if f.dtype == "date":
            tidy[f.key] = parse_date_series(values)
        elif f.dtype == "number":
            tidy[f.key] = parse_number_series(values)
        elif f.dtype == "generation":
            tidy[f.key] = values.map(normalise_generation).astype("object")
        else:
            tidy[f.key] = values.str.strip().replace({"": pd.NA})

    tidy = tidy[tidy["tpid"].notna()]
    if tidy.empty:
        return _empty_tracker(), report
    # The tracker is keyed on TPID alone; ``tpid_key`` gives it the same key the
    # fact frame groups on, so the join needs no special case for a blank TPID
    # (there are none — the rows above were dropped).
    tidy["tpid_key"] = tidy["tpid"].astype("string").str.strip()

    grouped = tidy.groupby("tpid_key", sort=False)
    out = pd.DataFrame(index=grouped.size().index)
    out["tpid"] = grouped["tpid"].first()
    out["tracker_rows"] = grouped.size()
    for key in ("customer_name", "region", "migration_status", "current_state"):
        out[key] = grouped[key].first()
    out["target_generation"] = grouped["target_generation"].apply(_one_generation)
    out["migration_start_date"] = grouped["migration_start_date"].min()
    out["migration_end_date"] = grouped["migration_end_date"].max()
    for key in ("sddcs_in_scope", "sddcs_migrated"):
        out[key] = grouped[key].sum(min_count=1)
    out = out.reset_index()

    conflicts = [str(k) for k, values in grouped["target_generation"]
                 if len({v for v in values if v}) > 1]
    report.update({
        "accounts": int(len(out)),
        "generation_conflicts": conflicts,
        "no_generation": int(out["target_generation"].isna().sum()),
        "with_start": int(out["migration_start_date"].notna().sum()),
        "with_end": int(out["migration_end_date"].notna().sum()),
    })
    return out, report


def _one_generation(values) -> object:
    """One generation for an account, Gen-1 winning when its rows disagree."""
    found = {v for v in values if v}
    for generation, _marker in _GEN_MARKERS:
        if generation in found:
            return generation
    return None


def _empty_tracker() -> pd.DataFrame:
    return pd.DataFrame(columns=["tpid_key", "tpid", "tracker_rows",
                                 *(f.key for f in TRACKER_FIELDS if f.key != "tpid")])


# --------------------------------------------------------------------------- #
# The overlay
# --------------------------------------------------------------------------- #
def apply_to_fact(fact: pd.DataFrame, tracker: pd.DataFrame | None
                  ) -> tuple[pd.DataFrame, dict]:
    """Join the tracker onto the fact frame, carrying its columns beside the export's.

    Every tracker column arrives prefixed (``eos_start_date``,
    ``eos_target_generation`` …) and **nothing the export said is overwritten
    here** — the rules that read them decide, one by one, which source answers:
    :mod:`app.core.cleaning` for the generation, :mod:`app.core.kpi` for the
    programme matrix's start and end dates.  Keeping both on the row is what
    lets a drill-down show a date and say where it came from.

    Returns ``(fact, report)``; the report names the TPIDs on each side of the
    join that the other does not have.
    """
    out = fact.copy()
    matched: set[str] = set()
    if tracker is None or tracker.empty or fact.empty:
        out[TRACKED_FLAG] = False
        for column in OVERLAY_COLUMNS.values():
            if column not in out.columns:
                out[column] = _blank_like(column, out.index)
        return out, {"matched_accounts": 0, "unmatched_tpids": [],
                     "untracked_accounts": 0}

    keys = out["tpid_key"] if "tpid_key" in out.columns else segments.tpid_key(out)
    indexed = tracker.set_index("tpid_key")
    for key, column in OVERLAY_COLUMNS.items():
        out[column] = (keys.map(indexed[key]) if key in indexed.columns
                       else _blank_like(column, out.index))
    for column in ("eos_start_date", "eos_end_date"):
        out[column] = pd.to_datetime(out[column], errors="coerce")
    for column in ("eos_sddcs_in_scope", "eos_sddcs_migrated"):
        out[column] = pd.to_numeric(out[column], errors="coerce")
    # Text columns as the nullable ``string`` dtype the rest of the frame uses:
    # an object column of Nones is what makes DuckDB guess, and guess wrong.
    for column in ("eos_target_generation", "eos_tracker_status",
                   "eos_tracker_state", "eos_tracker_region",
                   "eos_tracker_customer"):
        out[column] = out[column].astype("string")
    out[TRACKED_FLAG] = keys.isin(set(indexed.index)).to_numpy()

    matched = set(keys) & set(indexed.index)
    unmatched = [str(t) for t in tracker.loc[
        ~tracker["tpid_key"].isin(matched), "tpid"].tolist()]
    report = {
        "matched_accounts": len(matched),
        # A TPID the programme is tracking that the FDO dataset has never heard
        # of: it cannot be reported on — there is no offering, no ACR and no
        # wave behind it — so it is named rather than quietly dropped.
        "unmatched_tpids": unmatched,
        "untracked_accounts": int(keys[~keys.isin(matched)].nunique()),
    }
    return out, report


def _blank_like(column: str, index) -> pd.Series:
    if column in ("eos_start_date", "eos_end_date"):
        return pd.Series(pd.NaT, index=index, dtype="datetime64[ns]")
    if column in ("eos_sddcs_in_scope", "eos_sddcs_migrated"):
        return pd.Series(pd.NA, index=index, dtype="Float64").astype("float64")
    return pd.Series(pd.NA, index=index, dtype="string")


def resolve_generation(fact: pd.DataFrame, tagged: pd.Series) -> tuple[pd.Series, pd.Series]:
    """The generation to report per row, and where each one came from.

    **Target SDDC Generation decides it wherever the tracker states one** — that
    column is the programme saying, in its own sheet, which generation an
    account is landing on.  Only where the tracker is silent (or has never heard
    of the account) does the existing rule stand: the "AVS Migration -
    Gen1/Gen2" tag on any of the account's waves, and Unclassified when there is
    no tag either.
    """
    tagged = tagged.astype("string")
    if "eos_target_generation" not in fact.columns:
        source = pd.Series(SOURCE_TAGS, index=fact.index, dtype="string")
        source[tagged == segments.GEN_UNCLASSIFIED] = SOURCE_NONE
        return tagged, source

    stated = fact["eos_target_generation"].astype("string")
    # ``as_bool_mask`` first: a column of <NA> compared against anything is
    # <NA>, and ``Series.where`` on that raises rather than choosing a side.
    known = as_bool_mask(stated.isin((segments.GEN_1, segments.GEN_2)), fact.index)
    generation = tagged.where(~known, stated)
    source = pd.Series(SOURCE_TAGS, index=fact.index, dtype="string")
    source[~known & (tagged == segments.GEN_UNCLASSIFIED)] = SOURCE_NONE
    source[known] = SOURCE_TRACKER
    return generation, source


def summary(fact: pd.DataFrame) -> pd.DataFrame:
    """What the tracker changed, as a table — one row per generation source."""
    if fact.empty or GENERATION_SOURCE not in fact.columns:
        return pd.DataFrame(columns=["Generation decided by", "Accounts (TPID)"])
    accounts = fact.drop_duplicates("tpid_key")
    counts = (accounts[GENERATION_SOURCE].value_counts()
              .rename_axis("Generation decided by")
              .reset_index(name="Accounts (TPID)"))
    return counts


def inconsistencies(fact: pd.DataFrame, tracker: pd.DataFrame | None,
                    overlay: dict | None = None) -> dict[str, pd.DataFrame]:
    """Where the tracking sheet and the FDO dataset disagree.

    Four disagreements worth seeing before trusting an EOS number, each a frame
    of the rows behind it:

    ``unmatched_tpids``
        In the tracking sheet, nowhere in the FDO dataset. Nothing can be
        reported for them — no offering, no ACR, no waves — so they are absent
        from every report until the nomination exists.
    ``untracked_eos_accounts``
        In EOS scope by tag or migration path, but not in the tracking sheet.
        Their generation, start and end dates fall back to the export.
    ``generation_disagrees``
        The sheet says one generation and the account's own Gen-1/Gen-2 tag says
        the other. The sheet wins (that is the rule) — this is where to see
        which accounts it overrode.
    ``ended_with_sddcs_outstanding``
        An Actual Migration End Date alongside fewer SDDCs migrated than in
        scope. Reported as the sheet states it; listed here because the two
        cells cannot both be right.
    """
    blank = pd.DataFrame()
    out = {"unmatched_tpids": blank, "untracked_eos_accounts": blank,
           "generation_disagrees": blank, "ended_with_sddcs_outstanding": blank}
    if tracker is None or tracker.empty:
        return out

    unmatched = set((overlay or {}).get("unmatched_tpids") or [])
    if unmatched:
        out["unmatched_tpids"] = tracker[
            tracker["tpid"].astype(str).isin(unmatched)].reset_index(drop=True)

    if not fact.empty and TRACKED_FLAG in fact.columns:
        accounts = fact.drop_duplicates("tpid_key")
        cols = [c for c in ("tpid", "customer_name", "generation", "tags",
                            "migration_path", "factory_offering")
                if c in accounts.columns]
        in_scope = accounts[accounts["is_eos_population"].astype(bool)
                            & ~accounts[TRACKED_FLAG].astype(bool)]
        if not in_scope.empty:
            out["untracked_eos_accounts"] = in_scope[cols].reset_index(drop=True)

        if "eos_target_generation" in accounts.columns and "tags" in accounts.columns:
            tagged = accounts["tags"].map(
                lambda v: segments.generation_from_tags([v]))
            stated = accounts["eos_target_generation"]
            clash = stated.notna() & tagged.notna() & (stated != tagged)
            if clash.any():
                rows = accounts[clash].assign(
                    tracker_generation=stated[clash], tag_generation=tagged[clash])
                keep = [c for c in ("tpid", "customer_name", "tracker_generation",
                                    "tag_generation", "tags") if c in rows.columns]
                out["generation_disagrees"] = rows[keep].reset_index(drop=True)

    scope = pd.to_numeric(tracker.get("sddcs_in_scope"), errors="coerce")
    done = pd.to_numeric(tracker.get("sddcs_migrated"), errors="coerce")
    if scope is not None and done is not None:
        odd = (tracker["migration_end_date"].notna() & scope.notna()
               & done.notna() & (done < scope))
        if bool(odd.any()):
            out["ended_with_sddcs_outstanding"] = tracker[odd].reset_index(drop=True)
    return out
