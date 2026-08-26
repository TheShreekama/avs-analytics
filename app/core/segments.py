"""Migration categories, platform classification and Gen-1/Gen-2 generations.

Three orthogonal classifications drive every dashboard:

* **Migration category** — which report a nomination belongs to.  Derived from the
  migration path and offering: what platform it is coming *from* and going *to*.
  A path containing "(From AVS)" targets Azure-native services; everything else
  whose target is AVS (on-premises, VMG, AWS/VMC, AVS-to-AVS, EOS refresh) is an
  AVS migration.
* **EOS population** — the TPIDs in scope for the EOS Migration reports, read off
  the export's own EOS markers on the offering / migration path.  There is one
  dataset: nothing here depends on a second worksheet.
* **Generation** — Gen-1 / Gen-2 / Unclassified, decided per **TPID** from the Tags
  of *all* its waves (host SKUs as a fallback) — never per wave, never by name.

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

# The Tags column is the authoritative generation signal.  Several tags are
# concatenated into one cell with no separator — "Qualify and AccelerateAVS
# Migration - Gen1", "InternalAVS Migration - Gen2", "Qualify and AccelerateFCS
# On Hold Reach OutAVS Migration - Gen1" — so the marker is matched against the
# cell stripped of everything but letters and digits.  That way spacing, dashes
# (hyphen or en dash) and neighbouring tags cannot hide it.
_GEN_TAG_MARKERS = ((GEN_1, "avsmigrationgen1"), (GEN_2, "avsmigrationgen2"))


def _compact(value) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def generation_from_tags(tag_values) -> str | None:
    """Generation from the Tags column, or None when no generation tag is present.

    Gen-1 wins when a TPID carries both markers across its waves, matching the
    SKU precedence.
    """
    found = set()
    for value in tag_values:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            continue
        compact = _compact(value)
        for gen, marker in _GEN_TAG_MARKERS:
            if marker in compact:
                found.add(gen)
    for gen, _marker in _GEN_TAG_MARKERS:
        if gen in found:
            return gen
    return None


def sku_codes(value) -> set[str]:
    """Normalised SKU codes found in a raw SKU cell ("AV36P Node" -> {'av36p'})."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return set()
    return {"av" + m.group(1).lower() for m in _SKU_TOKEN_RE.finditer(str(value))}


def classify_generation(sku_values, tag_values=None) -> str:
    """Gen-1 / Gen-2 / Unclassified for one TPID, across all of its waves.

    Precedence:
      1. **Tags** decide it: any wave tagged "AVS Migration - Gen1" -> Gen-1,
         "AVS Migration - Gen2" -> Gen-2 (Gen-1 wins if both appear).
      2. With no generation tag anywhere, fall back to the host SKUs: any wave
         carrying AV36 / AV36P / AV48 / AV52 -> Gen-1; only-AV64 -> Gen-2.
      3. Otherwise -> **Unclassified**, reported separately and never silently
         folded into a generation.
    """
    tagged = generation_from_tags(tag_values or [])
    if tagged:
        return tagged
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
    df = fact.assign(_key=tpid_key(fact))
    tags = df["tags"] if "tags" in df.columns else pd.Series("", index=df.index)
    df = df.assign(_tags=tags)
    return df.groupby("_key").apply(
        lambda g: classify_generation(g["avs_sku"].tolist(), g["_tags"].tolist()),
        include_groups=False)


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
def eos_population(fact: pd.DataFrame) -> pd.Series:
    """Per-row membership of the EOS population.

    Everything comes from the single nominations export: a row is EOS when its
    migration path, factory offering or linked offering carries an AV36 / AV36P /
    AV52 / AV64 / EOS / EGS / end-of-support marker.
    """
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
