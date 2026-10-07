"""The All EOS customers list — every customer running EOS SKUs.

A third upload, beside the FDO dataset and the manual EOS tracking sheet: one
row per customer, keyed on **TPID** (a customer name column is read when there
is one, for display only).  It answers one question — *which customers are on
end-of-support hardware?* — and is used for one report:

**AVS → Azure Native reports only the customers on this list.**  A customer the
FDO export shows moving off AVS ("From AVS" in the Primary Migration Path) who
is not on the list is left out of every figure; their From AVS waves are
dropped as the dataset is built (:func:`apply_to_fact`), so no page, export or
total can count them.  Nothing else changes: "From AVS" waves count in AVS →
Azure Native and nowhere else, so only that report can lose anything.

With no list loaded the report is exactly what it was before the list existed —
every From AVS customer is reported.

The file is read like the tracking sheet (:func:`app.core.eos_tracker.read_tracker_files`):
the header row is the first of 30 with a TPID header, a workbook's first sheet
with one is used, and TPIDs join as digits (``12,039,532`` = ``12039532``).
"""
from __future__ import annotations

import pandas as pd

from . import eos_tracker, segments

TITLE = "All EOS customers list"


def read_files(files: list[tuple[str, bytes]]) -> tuple[pd.DataFrame, list[dict]]:
    """Every file of the list, headed and stacked."""
    return eos_tracker.read_tracker_files(files)


def build_list(raw: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """One row per TPID on the list, and a report on the read."""
    empty = pd.DataFrame(columns=["tpid", "tpid_key", "customer_name"])
    report: dict = {"rows": int(len(raw)), "accounts": 0, "no_tpid_rows": 0,
                    "tpid_column": None, "customer_column": None}
    if raw is None or raw.empty:
        return empty, report
    mapping = eos_tracker.auto_map([str(c) for c in raw.columns])
    tpid_col, name_col = mapping.get("tpid"), mapping.get("customer_name")
    report.update(tpid_column=tpid_col, customer_column=name_col)
    if not tpid_col:
        return empty, report
    keys = segments.normalise_tpid(raw[tpid_col])
    frame = pd.DataFrame({
        "tpid": raw[tpid_col].astype("string").str.strip(),
        "tpid_key": keys,
        "customer_name": (raw[name_col].astype("string").str.strip()
                          if name_col else pd.Series(pd.NA, index=raw.index,
                                                     dtype="string")),
    })
    report["no_tpid_rows"] = int(frame["tpid_key"].isna().sum())
    frame = (frame[frame["tpid_key"].notna()]
             .drop_duplicates("tpid_key").reset_index(drop=True))
    report["accounts"] = int(len(frame))
    return frame, report


def apply_to_fact(fact: pd.DataFrame, customers: pd.DataFrame | None
                  ) -> tuple[pd.DataFrame, dict]:
    """Drop the From AVS waves of every customer the list does not name.

    Returns the fact frame and a report: how many accounts the list names, how
    many AVS → Azure Native accounts stay, and which ones were left out (with
    their names, for Data & Upload and the Debug page).  With no list, the
    frame comes back untouched.
    """
    report: dict = {"loaded": customers is not None, "listed_accounts": 0,
                    "native_kept": 0, "native_excluded": 0,
                    "excluded_rows": 0, "excluded": [], "not_in_fdo": 0}
    if customers is None or fact.empty or "is_from_avs" not in fact.columns:
        return fact, report
    listed = set(customers["tpid_key"].dropna())
    keys = fact["tpid_key"] if "tpid_key" in fact.columns else segments.tpid_key(fact)
    native = fact["is_from_avs"].astype(bool).to_numpy()
    on_list = keys.isin(listed).to_numpy()
    drop = native & ~on_list
    dropped = fact[drop]
    names = (dropped.drop_duplicates("tpid_key")
             [["tpid", "customer_name"]].astype("string")
             if not dropped.empty else pd.DataFrame(columns=["tpid", "customer_name"]))
    report.update(
        listed_accounts=len(listed),
        native_kept=int(keys[native & on_list].nunique()),
        native_excluded=int(dropped["tpid_key"].nunique()) if not dropped.empty else 0,
        excluded_rows=int(drop.sum()),
        excluded=[(str(t), "" if pd.isna(n) else str(n))
                  for t, n in zip(names["tpid"], names["customer_name"])],
        not_in_fdo=len(listed - set(keys)),
    )
    return fact[~drop].reset_index(drop=True), report


def scope_note(ctx) -> str:
    """One sentence for the AVS → Azure Native report: who it covers."""
    if not getattr(ctx, "has_eos_list", False):
        return ("No All EOS customers list is loaded, so every customer moving "
                "From AVS is reported.")
    rep = (getattr(ctx, "report", None) or {}).get("eos_list") or {}
    left = int(rep.get("native_excluded", 0))
    tail = (f" {left:,} customer(s) moving From AVS are not on the list and are "
            f"left out." if left else "")
    return (f"Only customers on the All EOS customers list "
            f"({int(rep.get('listed_accounts', 0)):,} TPIDs) are reported here."
            + tail)
