"""Migration categories, platform classification and Gen-1/Gen-2 generations.

Three orthogonal classifications drive every dashboard:

* **Migration category** — which report a nomination belongs to.  Derived from the
  migration path and offering: what platform it is coming *from* and going *to*.
  A path containing "(From AVS)" targets Azure-native services; everything else
  whose target is AVS (on-premises, VMG, AWS/VMC, AVS-to-AVS, EOS refresh) is an
  AVS migration.
* **EOS population** — the TPIDs in scope for the EOS Migration reports.  When an
  EOS worksheet is supplied its TPID list is authoritative; without one the EOS
  markers on the offering/path are used instead.
* **Generation** — Gen-1 / Gen-2 / Unclassified, decided per **TPID** by looking at
  the SKUs across *all* of its waves (never per wave, never by account name).

Every rule here is TPID-first: account names differ between worksheets and source
systems, so they are never used for matching.
"""
from __future__ import annotations

import re

import pandas as pd

# --------------------------------------------------------------------------- #
# Migration categories
# --------------------------------------------------------------------------- #
CAT_EOS_GEN1 = "eos_gen1"
CAT_EOS_GEN2 = "eos_gen2"
CAT_EOS_UNCLASSIFIED = "eos_unclassified"
CAT_ALL_AVS = "all_avs"
CAT_AVS_NATIVE = "avs_native"

CATEGORY_LABELS = {
    CAT_EOS_GEN1: "EOS Migration — Gen-1",
    CAT_EOS_GEN2: "EOS Migration — Gen-2",
    CAT_EOS_UNCLASSIFIED: "EOS Migration — Unclassified",
    CAT_ALL_AVS: "All AVS Migrations",
    CAT_AVS_NATIVE: "AVS → Azure Native",
}

# --------------------------------------------------------------------------- #
# Platforms
# --------------------------------------------------------------------------- #
PLATFORM_AVS = "AVS"
PLATFORM_AZURE_NATIVE = "Azure Native"
PLATFORM_ONPREM = "On-Premises"
PLATFORM_VMG = "VMG"
PLATFORM_AWS = "AWS / VMC"
PLATFORM_OTHER = "Other"


def source_platform(*values) -> str:
    """Platform a nomination is migrating *from*."""
    text = " ".join(str(v) for v in values if v is not None).lower()
    if "from avs" in text or "avs to avs" in text:
        return PLATFORM_AVS
    if "vmg" in text:
        return PLATFORM_VMG
    if "aws" in text or "vmc" in text:
        return PLATFORM_AWS
    if "onprem" in text or "on prem" in text or "on-prem" in text or "on premises" in text:
        return PLATFORM_ONPREM
    if _has_eos_marker(text):
        return PLATFORM_AVS          # an EOS refresh moves off ageing AVS hosts
    return PLATFORM_OTHER


def target_platform(*values) -> str:
    """Platform a nomination is migrating *to* — the category driver."""
    text = " ".join(str(v) for v in values if v is not None).lower()
    if "from avs" in text:
        return PLATFORM_AZURE_NATIVE
    if "to avs" in text or "avs migration" in text or _has_eos_marker(text):
        return PLATFORM_AVS
    if "odaa" in text or "oracle" in text:
        return PLATFORM_AZURE_NATIVE
    if "avs" in text:
        return PLATFORM_AVS
    return PLATFORM_OTHER


def _has_eos_marker(text: str) -> bool:
    from .cleaning import is_av36_eos_path      # imported lazily: cleaning imports this module
    return is_av36_eos_path(text)


# --------------------------------------------------------------------------- #
# Generation (Gen-1 / Gen-2 / Unclassified) — decided per TPID, across all waves
# --------------------------------------------------------------------------- #
GEN_1 = "Gen-1"
GEN_2 = "Gen-2"
GEN_UNCLASSIFIED = "Unclassified"

GEN1_SKUS = ("av36p", "av36", "av48", "av52")     # longest first: AV36P before AV36
GEN2_SKUS = ("av64",)
_SKU_TOKEN_RE = re.compile(r"av\s*(36p|36|48|52|64)", re.I)


def sku_codes(value) -> set[str]:
    """Normalised SKU codes found in a raw SKU cell ("AV36P Node" -> {'av36p'})."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return set()
    return {"av" + m.group(1).lower() for m in _SKU_TOKEN_RE.finditer(str(value))}


def classify_generation(sku_values) -> str:
    """Gen-1 / Gen-2 / Unclassified for one TPID, from the SKUs of all its waves.

    Precedence (Section 6 of the requirements):
      1. Any wave carrying AV36, AV36P, AV48 or AV52 -> **Gen-1**, even when other
         SKUs are also present.
      2. Otherwise, when the only populated SKU across every wave is AV64 -> **Gen-2**.
      3. Otherwise (blank SKUs, or any combination the rules do not cover)
         -> **Unclassified**.  Never silently folded into Gen-1 or Gen-2.
    """
    found: set[str] = set()
    for value in sku_values:
        found |= sku_codes(value)
    if found & set(GEN1_SKUS):
        return GEN_1
    if found and found <= set(GEN2_SKUS):
        return GEN_2
    return GEN_UNCLASSIFIED


def generation_by_tpid(fact: pd.DataFrame) -> pd.Series:
    """Map of TPID -> generation, evaluating every wave belonging to the TPID."""
    if fact.empty or "avs_sku" not in fact.columns:
        return pd.Series(dtype="object")
    keys = tpid_key(fact)
    grouped = fact.assign(_key=keys).groupby("_key")["avs_sku"]
    return grouped.apply(lambda s: classify_generation(s.tolist()))


def tpid_key(fact: pd.DataFrame) -> pd.Series:
    """The authoritative grouping key: TPID, falling back to the account name.

    TPID is the identifier for every join, lookup and deduplication.  The name is
    used only when a row carries no TPID at all, so those rows still roll up to
    something rather than collapsing together.
    """
    tpid = fact["tpid"].astype("string").str.strip()
    tpid = tpid.replace({"": pd.NA, "nan": pd.NA, "0": pd.NA})
    name = fact["customer_name"].astype("string").str.strip().str.upper()
    return tpid.fillna("NAME:" + name.fillna("UNKNOWN"))


# --------------------------------------------------------------------------- #
# EOS population
# --------------------------------------------------------------------------- #
def eos_tpids_from_worksheet(df: pd.DataFrame) -> set[str]:
    """TPIDs listed in a supplied EOS worksheet (any column named like a TPID)."""
    for col in df.columns:
        if re.sub(r"[^a-z]", "", str(col).lower()) in ("tpid", "topparentid", "tpids"):
            vals = df[col].astype("string").str.strip()
            return {v for v in vals.dropna().unique() if v and v != "0"}
    return set()


def apply_eos_population(fact: pd.DataFrame, eos_tpids: set[str] | None) -> pd.Series:
    """Per-row membership of the EOS population.

    With an EOS worksheet, membership is exactly its TPID list (Section 6).
    Without one, the EOS markers already derived from the offering/path stand in,
    so the reports still work on a single-file upload.
    """
    if eos_tpids:
        return tpid_key(fact).isin(eos_tpids)
    return fact["is_av36_eos"].astype(bool)


# --------------------------------------------------------------------------- #
# Category populations
# --------------------------------------------------------------------------- #
def population(fact: pd.DataFrame, category: str) -> pd.DataFrame:
    """Rows belonging to a reporting category.

    ``all_avs`` is every nomination whose **target** platform is AVS, whatever the
    source; ``avs_native`` is the "(From AVS)" motion; the EOS categories are the
    EOS population split by the TPID's generation.
    """
    if fact.empty:
        return fact
    if category == CAT_ALL_AVS:
        return fact[fact["is_avs_target"].astype(bool)]
    if category == CAT_AVS_NATIVE:
        return fact[fact["is_from_avs"].astype(bool)]
    eos = fact[fact["is_eos_population"].astype(bool)]
    wanted = {CAT_EOS_GEN1: GEN_1, CAT_EOS_GEN2: GEN_2,
              CAT_EOS_UNCLASSIFIED: GEN_UNCLASSIFIED}.get(category)
    if wanted is None:
        return eos
    return eos[eos["generation"] == wanted]


def category_summary(fact: pd.DataFrame) -> pd.DataFrame:
    """TPID counts per category — used to show where the population sits."""
    rows = []
    for cat, label in CATEGORY_LABELS.items():
        pop = population(fact, cat)
        rows.append({"category": label,
                     "tpids": int(tpid_key(pop).nunique()) if not pop.empty else 0,
                     "nominations": int(len(pop))})
    return pd.DataFrame(rows)


def category_label_series(fact: pd.DataFrame) -> pd.Series:
    """A single readable category per row, for drill-down tables and exports.

    A row can legitimately sit in more than one category (an EOS refresh is also
    an AVS migration), so this reports the most specific one: the Azure-native
    motion first, then the EOS generation, then the general AVS population.
    """
    if fact.empty:
        return pd.Series(dtype="object")
    gen_label = {GEN_1: CATEGORY_LABELS[CAT_EOS_GEN1],
                 GEN_2: CATEGORY_LABELS[CAT_EOS_GEN2]}
    out = pd.Series("Other", index=fact.index, dtype="object")
    avs = fact["is_avs_target"].astype(bool)
    out[avs] = CATEGORY_LABELS[CAT_ALL_AVS]
    eos = fact["is_eos_population"].astype(bool)
    out[eos] = fact.loc[eos, "generation"].map(
        lambda g: gen_label.get(g, CATEGORY_LABELS[CAT_EOS_UNCLASSIFIED]))
    out[fact["is_from_avs"].astype(bool)] = CATEGORY_LABELS[CAT_AVS_NATIVE]
    return out
