"""Canonical schema for the AVS nominations dataset.

The source export (see ``sample_data/avs_raw_data.csv``) carries ~88 columns,
many of them empty or belonging to an unrelated Copilot/Foundry schema.  We map
the columns we actually report on to stable *canonical* field keys.  Every report
in the app references canonical keys only, so a renamed source column is handled
by re-mapping in one place (the Column Mapping screen) rather than touching code.

``auto_map`` matches incoming headers to canonical fields using exact, normalised
and synonym matching, so the sample schema (and close variants) map with zero
user effort.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


# Logical data types drive cleaning + which widgets a field can power.
DTYPE_TEXT = "text"
DTYPE_CATEGORY = "category"
DTYPE_DATE = "date"
DTYPE_NUMBER = "number"
DTYPE_CURRENCY = "currency"
DTYPE_ID = "id"


@dataclass(frozen=True)
class CanonicalField:
    key: str                       # internal stable name (snake_case)
    label: str                     # human label shown in UI
    source_default: str            # default source header in the sample export
    dtype: str
    role: str                      # grouping for the mapping screen
    synonyms: tuple = field(default_factory=tuple)
    required: bool = False
    description: str = ""


# --------------------------------------------------------------------------- #
# Canonical field catalogue
# --------------------------------------------------------------------------- #
CANONICAL_FIELDS: list[CanonicalField] = [
    # --- Identity -------------------------------------------------------- #
    CanonicalField("task_id", "Task ID", "Task ID", DTYPE_ID, "Identity",
                   ("task", "nomination id", "taskid"), required=True,
                   description="Unique nomination/task identifier (primary key)."),
    CanonicalField("tpid", "TPID", "TPID", DTYPE_ID, "Identity",
                   ("t-pid", "top parent id"),
                   description="Top-parent account id; an account may have many tasks."),
    CanonicalField("account_id", "Account ID", "Account ID", DTYPE_ID, "Identity",
                   ("acct id",)),
    CanonicalField("customer_name", "Customer Name", "Customer Name", DTYPE_TEXT, "Identity",
                   ("customer", "account name", "company"), required=True),
    CanonicalField("msx_opportunity_id", "MSX Opportunity ID", "MSX Opportunity ID",
                   DTYPE_ID, "Identity", ("opportunity id", "msx opp")),

    # --- Migration track ------------------------------------------------- #
    CanonicalField("factory_offering", "Factory Offering (Track)", "Factory Offering",
                   DTYPE_CATEGORY, "Migration Track",
                   ("offering", "factory", "nomination type", "workload track"),
                   required=True,
                   description="Migration track, e.g. AVS / SQL / OSSDB / Windows / Linux."),
    CanonicalField("phase", "Phase / Wave", "Phase", DTYPE_CATEGORY, "Migration Track",
                   ("wave", "sprint", "batch")),
    CanonicalField("migration_path", "Primary Migration Path", "Primary Migration Path",
                   DTYPE_CATEGORY, "Migration Track",
                   ("migration path", "path", "scenario", "primary path"),
                   description="Source→target path; '(From AVS)' implies AVS→Azure-Native."),
    CanonicalField("linked_task_id", "Linked Task ID", "Linked Task ID", DTYPE_ID,
                   "Migration Track", ("linked task",)),
    CanonicalField("linked_offering", "Linked Offering", "Linked Offering Name",
                   DTYPE_CATEGORY, "Migration Track", ("linked offering", "linked nomination")),

    # --- Geography ------------------------------------------------------- #
    CanonicalField("ww_region", "WW Region", "WW Region", DTYPE_CATEGORY, "Geography",
                   ("worldwide region", "ww", "global region", "geo"), required=True,
                   description="Worldwide super-region (Americas / ASIA / EMEA …)."),
    CanonicalField("region", "Region", "Region", DTYPE_CATEGORY, "Geography",
                   ("sub region", "subsidiary", "geo region")),
    CanonicalField("area", "Area", "Area", DTYPE_CATEGORY, "Geography",
                   ("sales area", "district")),
    CanonicalField("eou", "EOU", "EOU", DTYPE_CATEGORY, "Geography",
                   ("end of unit", "operating unit")),
    CanonicalField("customer_segment", "Customer Segment", "Customer Segment",
                   DTYPE_CATEGORY, "Geography", ("segment", "sub segment")),

    # --- Nomination status / approval ------------------------------------ #
    CanonicalField("nomination_status", "Nomination Status", "Nomination Status",
                   DTYPE_CATEGORY, "Nomination", ("nom status", "approval status"),
                   required=True),
    CanonicalField("created_date", "Nom. Created Date", "Nom. Created Date", DTYPE_DATE,
                   "Nomination", ("created date", "nomination created", "submitted date"),
                   required=True),
    CanonicalField("approval_date", "Nom. Approval Date", "Nom. Approval Date", DTYPE_DATE,
                   "Nomination", ("approval date", "approved date", "date approved")),
    CanonicalField("decline_date", "Nom. Decline Date", "Nom. Decline Date", DTYPE_DATE,
                   "Nomination", ("decline date", "declined date", "rejection date")),
    CanonicalField("decline_reason", "Decline / On-Hold Reason",
                   "Nomination Declined/On Hold reason", DTYPE_TEXT, "Nomination",
                   ("decline reason", "hold reason", "rejection reason")),
    CanonicalField("created_by", "Created By", "Nom. Created By", DTYPE_TEXT, "Nomination",
                   ("nominator", "submitted by")),
    CanonicalField("fcs_flag", "FCS Flag", "FCS Flag", DTYPE_CATEGORY, "Nomination",
                   ("fcs", "fasttrack flag")),
    CanonicalField("fcs_stage", "FCS Stage", "FCS Stage Name", DTYPE_CATEGORY, "Nomination",
                   ("fcs stage", "fasttrack stage")),

    # --- Migration / delivery status ------------------------------------- #
    CanonicalField("migration_status", "Migration Status", "Migration Status",
                   DTYPE_CATEGORY, "Delivery Status",
                   ("delivery status", "engagement status", "project status"),
                   required=True,
                   description="Coded pipeline stage, e.g. '7 - Completed'."),
    CanonicalField("milestone_status", "Milestone Status", "Milestone Status",
                   DTYPE_CATEGORY, "Delivery Status", ("milestone",)),
    CanonicalField("current_state", "Current State", "Current State", DTYPE_CATEGORY,
                   "Delivery Status", ("state", "operational state", "rag")),
    CanonicalField("sales_stage", "Sales Stage (MSX)", "Sales Stage Name - MSX",
                   DTYPE_CATEGORY, "Delivery Status", ("sales stage", "msx stage")),
    CanonicalField("commitment_status", "MSX Commitment", "MSX Commitment Status",
                   DTYPE_CATEGORY, "Delivery Status", ("commitment", "committed")),
    CanonicalField("intake_owner", "Intake Owner", "Intake Owner Name", DTYPE_TEXT,
                   "Delivery Status", ("intake", "coordinator")),

    # --- Dates / schedule ------------------------------------------------ #
    CanonicalField("next_followup_date", "Next Follow-up", "Next Follow-up Date", DTYPE_DATE,
                   "Schedule", ("follow up", "followup", "next action")),
    CanonicalField("actual_start_date", "Actual Start", "Actual Start Date", DTYPE_DATE,
                   "Schedule", ("start date", "actual start")),
    CanonicalField("actual_end_date", "Actual End", "Actual End Date", DTYPE_DATE,
                   "Schedule", ("end date", "completion date", "actual end", "closed date")),
    CanonicalField("planned_start_date", "Planned Start", "Planned Start Date", DTYPE_DATE,
                   "Schedule", ("planned start", "baseline start")),
    CanonicalField("planned_end_date", "Planned End", "Planned End Date", DTYPE_DATE,
                   "Schedule", ("planned end", "target date", "due date", "baseline end")),
    CanonicalField("eta_date", "ETA", "ETA Date", DTYPE_DATE, "Schedule",
                   ("eta", "estimated completion")),

    # --- People ---------------------------------------------------------- #
    CanonicalField("assigned_pm", "Factory PM", "Assigned To (Factory PM)", DTYPE_TEXT,
                   "People", ("pm", "project manager", "factory pm", "assigned to")),
    CanonicalField("solution_architect", "Solution Architect", "Solution Architect",
                   DTYPE_TEXT, "People", ("architect", "sa")),

    # --- Commercial metrics --------------------------------------------- #
    CanonicalField("total_cores", "Total Cores", "Total Cores", DTYPE_NUMBER, "Commercial",
                   ("cores", "core count", "vcores")),
    CanonicalField("total_acr", "Total ACR", "Total ACR", DTYPE_CURRENCY, "Commercial",
                   ("acr", "annual contract revenue", "consumed revenue", "revenue", "acv")),
    CanonicalField("unified_flag", "Support Tier", "Unified Flag", DTYPE_CATEGORY,
                   "Commercial", ("unified", "support level", "support tier")),
    CanonicalField("tags", "Tags", "Tags", DTYPE_CATEGORY, "Commercial", ("tag", "labels")),
]

CANONICAL_BY_KEY = {f.key: f for f in CANONICAL_FIELDS}
REQUIRED_KEYS = [f.key for f in CANONICAL_FIELDS if f.required]
DATE_KEYS = [f.key for f in CANONICAL_FIELDS if f.dtype == DTYPE_DATE]
CURRENCY_KEYS = [f.key for f in CANONICAL_FIELDS if f.dtype == DTYPE_CURRENCY]
NUMBER_KEYS = [f.key for f in CANONICAL_FIELDS if f.dtype == DTYPE_NUMBER]
ROLES = list(dict.fromkeys(f.role for f in CANONICAL_FIELDS))


# --------------------------------------------------------------------------- #
# Header matching
# --------------------------------------------------------------------------- #
def _norm(s: str) -> str:
    """Normalise a header for fuzzy comparison."""
    s = str(s).lower().strip()
    s = re.sub(r"[\(\)\[\]\.,/\-_]+", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def default_mapping() -> dict[str, str]:
    """Canonical-key -> default source header (the sample schema)."""
    return {f.key: f.source_default for f in CANONICAL_FIELDS}


def auto_map(headers: list[str]) -> dict[str, Optional[str]]:
    """Best-effort map of canonical key -> matched source header.

    Strategy per field: exact match on the default header, then normalised
    match against the default header or any synonym, then a contains-style
    fallback.  Returns ``None`` for fields with no confident match.
    """
    norm_headers = {h: _norm(h) for h in headers}
    used: set[str] = set()
    result: dict[str, Optional[str]] = {}

    for f in CANONICAL_FIELDS:
        match: Optional[str] = None

        # 1) exact (case-insensitive) match on the canonical default header
        for h in headers:
            if h in used:
                continue
            if h.strip().lower() == f.source_default.strip().lower():
                match = h
                break

        # 2) normalised match against default header + synonyms
        if match is None:
            targets = {_norm(f.source_default), _norm(f.label), *(_norm(s) for s in f.synonyms)}
            for h, nh in norm_headers.items():
                if h in used:
                    continue
                if nh in targets:
                    match = h
                    break

        # 3) token-contains fallback (synonym appears inside the header)
        if match is None:
            targets = [_norm(f.source_default), *(_norm(s) for s in f.synonyms)]
            for h, nh in norm_headers.items():
                if h in used:
                    continue
                if any(t and (t in nh or nh in t) for t in targets):
                    match = h
                    break

        if match is not None:
            used.add(match)
        result[f.key] = match

    return result
