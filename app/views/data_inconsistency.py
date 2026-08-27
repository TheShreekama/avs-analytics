"""Data Inconsistency — everything in the file that disagrees with itself.

A report like any other, over the real data: each check has a count, the offending
records, and a CSV export. The point is to see *which rows* to go and fix in the
source system, not just that a count is non-zero.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from app import state
from app.core import glossary, kpi, segments
from app.core.metrics import fmt_int
from app.ui import charts, components
from app.ui.theme import banner, page_header, section, subheading

_CHECK_HELP = {
    "tagged_without_eos_path": (
        "Accounts carrying an 'AVS Migration - Gen1/Gen2' tag whose waves never show "
        "an EOS migration path. They are EOS accounts on the strength of the tag "
        "alone — legitimate, but worth confirming the path was not simply missed."
    ),
    "eos_path_without_tag": (
        "Waves on the AV36/AV36P/AV52 - EOS migration path whose account carries no "
        "generation tag on any wave. In scope through the path, but no generation "
        "can be reported — they appear under 'EOS Migration — No generation tag'."
    ),
    "bad_date": (
        "Values in a date column that could not be read as a date. Excel serial "
        "numbers, ISO stamps, month names and day-first or month-first values are "
        "all handled, so anything listed here is a genuinely unusual value."
    ),
    "date_order": (
        "Records whose dates contradict each other — an approval before the "
        "nomination was created, or an end before its start."
    ),
    "bad_segment": (
        "Customer Segment values outside the expected vocabulary (Commercial, "
        "Public Sector, Enterprise, SMC/SMB, Majors, Corporate, Government)."
    ),
    "contaminated_numeric": (
        "Numeric columns holding something that is not a number — usually a "
        "column-shifted row where a date landed in Total ACR or Total Cores."
    ),
    "dirty_region": (
        "WW Region values that arrived with a numeric prefix ('1800 Americas - "
        "Enterprise'). These are cleaned automatically; listed for visibility."
    ),
    "missing_tpid": (
        "Rows with no TPID. TPID is the identifier every count and join relies on, "
        "so these rows fall back to the account name — which differs between "
        "worksheets and can split or merge accounts."
    ),
    "duplicate_task": (
        "The same Task ID appearing on more than one row. Hosts and ACR are summed "
        "over records, so a duplicated row inflates them."
    ),
}


def render() -> None:
    ctx = state.ensure_context()
    page_header("Data Inconsistency",
                "Where the export contradicts itself — with the records to fix.",
                help="Every check runs over the whole file. Counts are rows unless the "
                     "check is account-level, and each one exports to CSV.")
    fact = ctx.fact

    date_filter = components.page_date_filter(ctx, "dq", "created_date", table="fact")
    scoped = _apply_window(fact, date_filter)
    if date_filter:
        banner(f"Checks below run over <b>{fmt_int(len(scoped))}</b> of "
               f"<b>{fmt_int(len(fact))}</b> nomination waves in the selected period. "
               f"Classification checks always consider every wave of an account.")

    checks = _collect(ctx, fact, scoped)
    total = sum(len(df) for _, df in checks)

    section("Summary")
    if not total:
        st.success("✅ No inconsistencies found — tags, paths, dates and identifiers "
                   "all agree.")
        return

    summary = pd.DataFrame([{"Check": label, "Rows": len(df),
                             "Accounts (TPID)": (df["tpid"].nunique()
                                                 if "tpid" in df.columns else len(df))}
                            for label, df in checks if len(df)])
    c1, c2 = st.columns([2, 3])
    with c1:
        components.kpi_row([
            {"label": "Issues found", "value": fmt_int(total), "tone": "warn",
             "sub": f"across {len(summary)} check(s)"},
            {"label": "Accounts affected",
             "value": fmt_int(int(summary["Accounts (TPID)"].sum())), "tone": "warn"},
        ])
    with c2:
        st.plotly_chart(charts.bar(summary.rename(columns={"Check": "category",
                                                           "Rows": "count"}),
                                   "category", "count", horizontal=True, height=260),
                        width="stretch")
    components.show_table(summary)

    section("Records to fix")
    for label, frame in checks:
        if frame.empty:
            continue
        key = _key_for(label)
        subheading(f"{label} — {fmt_int(len(frame))} row(s)", help=_CHECK_HELP.get(key))
        components.show_table(kpi.drilldown_frame(frame)
                              if "generation" in frame.columns else frame,
                              height=min(360, 60 + 35 * min(len(frame), 8)))
        st.download_button("⬇️ Export to CSV", frame.to_csv(index=False).encode("utf-8"),
                           file_name=f"inconsistency-{key}.csv", mime="text/csv",
                           key=f"dq_dl_{key}")


# --------------------------------------------------------------------------- #
def _apply_window(fact: pd.DataFrame, date_filter: dict | None) -> pd.DataFrame:
    if not date_filter:
        return fact
    mask = kpi.in_window(fact[date_filter["col"]], date_filter["start"], date_filter["end"])
    if date_filter.get("include_null"):
        mask |= fact[date_filter["col"]].isna()
    return fact[mask]


_LABELS = {
    "tagged_without_eos_path": "Tagged Gen-1/Gen-2, no EOS path",
    "eos_path_without_tag": "EOS path, no generation tag",
    "bad_date": "Unreadable date values",
    "date_order": "Dates out of order",
    "bad_segment": "Invalid Customer Segment",
    "contaminated_numeric": "Non-numeric value in a numeric column",
    "dirty_region": "WW Region needed cleaning",
    "missing_tpid": "Rows with no TPID",
    "duplicate_task": "Duplicate Task IDs",
}


def _key_for(label: str) -> str:
    for key, text in _LABELS.items():
        if text == label:
            return key
    return label.lower().replace(" ", "-")


def _collect(ctx, fact: pd.DataFrame, scoped: pd.DataFrame) -> list[tuple[str, pd.DataFrame]]:
    """Every check, as (label, offending records)."""
    checks: list[tuple[str, pd.DataFrame]] = []

    # Classification: always over the whole file, since membership is per account.
    for key, frame in segments.eos_consistency(fact).items():
        checks.append((_LABELS[key], frame))

    # Data-quality flags raised during cleaning, resolved back to their rows.
    cols = [c for c in ("tpid", "customer_name", "phase", "migration_path",
                        "created_date", "approval_date", "actual_start_date",
                        "actual_end_date", "total_cores", "total_acr", "dq_flags")
            if c in scoped.columns]
    flags = {
        "bad_date": "Unparseable date",
        "date_order": "before",
        "bad_segment": "Invalid Customer Segment",
        "contaminated_numeric": "Non-numeric",
        "dirty_region": "numeric prefix",
    }
    if "dq_flags" in scoped.columns:
        text = scoped["dq_flags"].astype("string").fillna("")
        for key, needle in flags.items():
            hit = scoped[text.str.contains(needle, case=False, na=False)]
            checks.append((_LABELS[key], hit[cols]))

    # Identifiers.
    if "tpid" in scoped.columns:
        blank = scoped["tpid"].astype("string").str.strip()
        checks.append((_LABELS["missing_tpid"],
                       scoped[blank.isna() | (blank == "") | (blank == "0")][cols]))
    if "task_id" in scoped.columns:
        dupes = scoped[scoped["task_id"].notna() &
                       scoped["task_id"].duplicated(keep=False)]
        checks.append((_LABELS["duplicate_task"],
                       dupes.sort_values("task_id")[
                           [c for c in (["task_id"] + cols) if c in dupes.columns]]))
    return checks
