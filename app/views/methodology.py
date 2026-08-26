"""Methodology — how every number on this dashboard is calculated.

A single, plain-language reference for the deterministic logic behind each
section.  Nothing here is AI-generated at runtime; every rule is implemented in
``app/core`` and is reproduced below so reviewers can audit it.
"""
from __future__ import annotations

import streamlit as st

from app import state
from app.config import (DATE_PRESETS, DEFAULT_DATE_PRESET, EOS_STATUS_ORDER,
                        FY_START_MONTH)
from app.core.metrics import date_preset_range
from app.ui.theme import page_header, section


def render() -> None:
    ctx = state.ensure_context()
    page_header("Methodology & Logic",
                "Exactly how each metric, status and insight on this dashboard is computed — "
                "deterministic rules, no AI, no external calls.")

    # ------------------------------------------------------------------ #
    section("Reporting scope (what counts as an 'AVS nomination')")
    st.markdown(
        "The dashboard's **primary focus is AVS Migration Nominations** — accounts "
        "being *onboarded to AVS*. Offerings whose migration path contains "
        "**'(From AVS)'** (i.e. migrating *away* from AVS to an Azure-native service) "
        "are a different motion and are **quarantined to their own pages**:\n\n"
        "- **Primary reports** (Overview, Accounts by Status, Approved, Closed, "
        "EOS Migration, Nomination Trends, Approved Trends, Insights) show **only** "
        "`is_from_avs = FALSE`.\n"
        "- **AVS → Azure Native** (Status + Trends pages) show **only** "
        "`is_from_avs = TRUE`.\n\n"
        "`is_from_avs` is derived from the migration path: a path containing "
        "*“from avs”* → **AVS → Azure Native**; a path with *to avs / EGS / AV36 / "
        "ODAA* → **Onboard to AVS**.")

    # ------------------------------------------------------------------ #
    section("Counting modes & wave deduplication")
    st.markdown(
        "A customer can have several waves (Wave-1, Wave-2 …). The **sidebar toggle** "
        "switches how things are counted:\n\n"
        "- **Customer (deduplicated)** — *default*. Each customer counts **once**:\n"
        "    - **Category membership = ANY wave** (a customer is *EOS Migration* if any wave "
        "is AV36/EOS; *AVS → Azure Native* if any wave is from-AVS).\n"
        "    - **Approval & creation date = Wave-1** (lowest wave number).\n"
        "    - **Status, region & closure = the last wave**. Closed when the last wave is "
        "done/completed.\n"
        "    - **ACR / cores = summed** across the customer's waves.\n"
        "- **Nomination (wave-level)** — every wave/row counts (raw detail).\n\n"
        "Deduplication is by customer name (case-insensitive).")

    # ------------------------------------------------------------------ #
    section("Region")
    st.markdown(
        "The source `WW Region` combines geography and segment (e.g. "
        "*“Americas - Enterprise”*). Reports show **region as geography only** "
        "(**Americas / EMEA / ASIA**) — the part before the first “ - ”. The segment "
        "is preserved separately in **Customer Segment**. Any leading numeric prefix "
        "(e.g. *“1800 Americas”*) is stripped and flagged as a data-quality issue.")

    # ------------------------------------------------------------------ #
    section("Operational / EOS status")
    st.markdown(
        "`eos_status` is a single derived status, unified from several raw signals. "
        "The **first matching rule wins** (top to bottom):")
    st.table({
        "Status": ["Completed", "Cancelled", "Blocked", "At Risk", "Delayed",
                   "At Risk", "On Track"],
        "Derived when…": [
            "migration status code = 7, label/state says complete/done, milestone "
            "“completed”, or an actual end date exists",
            "code = 6, label says cancel/archive, or milestone “cancelled”",
            "Current State contains “blocked”",
            "deferred — code = 5 or label/state says “defer”",
            "has a planned-end date, no actual-end date, and planned-end is before the "
            "as-of date (schedule overdue)",
            "a follow-up date is past due, or Current State starts with “waiting”",
            "none of the above (default)",
        ],
    })
    st.caption(f"Display order: {' → '.join(EOS_STATUS_ORDER)}.")

    # ------------------------------------------------------------------ #
    section("Risk")
    st.markdown(
        "“**Risk**” = any nomination whose `eos_status` is **At Risk, Delayed or "
        "Blocked** (see the rules above). The *EOS risk hotspot* insight reports the "
        "region with the most such items, plus the **share of the portfolio** in any "
        "risk state. There is no scoring model — it is a direct count of those three "
        "statuses.")

    # ------------------------------------------------------------------ #
    section("Approval, closure, aging & cycle time")
    st.markdown(
        "- **Approved** — has an approval date, or Nomination Status contains “approv”.\n"
        "- **Closed** — migration status code = 7, Current State done/complete, "
        "milestone complete, or an actual end date exists.\n"
        "- **Open** — not closed and not cancelled.\n"
        "- **Aging (days)** — creation date → closure date (or the as-of date if still "
        "open). Negative values are dropped.\n"
        "- **Cycle time (days)** — creation → closure, **closed items only**.\n"
        "- **Approval latency (days)** — creation → approval.\n"
        "- **Closure rate** — closed ÷ total within the current selection.\n"
        "- **Fastest-closing region** — the region with the **lowest median cycle "
        "time** (regions with ≥2 closed items).\n"
        "- **Approval velocity** — the **median approval latency**, plus the slowest "
        "region by median latency.")

    # ------------------------------------------------------------------ #
    section("Migration categories & generations")
    st.markdown(
        "Each **Migration Analytics** dashboard reports one category, selected by "
        "the nomination's **target platform** and — for EOS — the TPID's SKU "
        "generation.\n\n"
        "- **All AVS Migrations** — every nomination whose target platform is AVS: "
        "on-premises, VMG, AWS/VMC, AVS-to-AVS and EOS refreshes.\n"
        "- **AVS → Azure Native** — the '(From AVS)' offerings, moving workloads off "
        "AVS onto Azure-native services.\n"
        "- **EOS Migration — Gen-1 / Gen-2 / Unclassified** — the EOS population, "
        "split by generation.\n\n"
        "**EOS population.** An account is an **EOS Migration** account when ANY of "
        "its waves carries an **\"AVS Migration - Gen1\"** or **\"AVS Migration - "
        "Gen2\"** tag — one tagged wave brings the whole account into scope, and the "
        "tag also sets its generation. When no wave carries either tag, the offering "
        "falls back to deciding it: a **Primary Migration Path** (or Factory / Linked "
        "Offering) reading **AV36/AV36P/AV52 - EOS** puts the account in scope with no "
        "generation. Everything comes from the single nominations export.\n\n"
        "**Generation is decided per TPID, across all of its waves:**\n"
        "1. Any wave tagged **\"AVS Migration - Gen1\"** → the account is **Gen-1**; "
        "**\"AVS Migration - Gen2\"** → **Gen-2**. Gen-1 wins if both appear on "
        "different waves. Tags arrive concatenated with no separator "
        "(*\"Qualify and AccelerateAVS Migration - Gen1\"*), so the marker is matched "
        "inside the cell regardless of spacing, dashes or neighbouring tags.\n"
        "2. No generation tag on any wave → no generation. If the account is in EOS "
        "scope through its migration path (*AV36/AV36P/AV52 - EOS*) it is listed on "
        "**EOS Migration — No generation tag**, never folded into a generation.")

    # ------------------------------------------------------------------ #
    section("Metric rules (unique TPIDs vs. hosts)")
    st.markdown(
        "**TPID is the authoritative identifier** for every join, lookup, "
        "classification and count. Account names differ between worksheets and "
        "source systems, so they are never used for matching.\n\n"
        "| Metric | Rule | Unit |\n"
        "| --- | --- | --- |\n"
        "| New Engagements | Unique TPIDs whose **Wave-1** nomination approval date "
        "falls in the period | Customers |\n"
        "| Migration Ends | Unique TPIDs whose **latest** wave is `7 - Completed`, "
        "dated by its Actual End Date | Customers |\n"
        "| Hosts Migrated | **Sum of Total Cores** over completed wave records — "
        "*not* a TPID count, each source record counted once | Hosts |\n"
        "| Nominations Approved | Nomination records approved in the period | "
        "Nominations |\n"
        "| Nomination Count (MoM) | Unique TPIDs per month, each counted once | "
        "Customers |\n"
        "| ACR (MoM) | Each TPID's ACR summed across its waves, landing in one month "
        "| Currency |\n\n"
        "A TPID whose **Wave 7 is completed but Wave 8 is not** is *not* a completed "
        "migration — completion always evaluates the latest wave.\n\n"
        "**Cumulative** is the final column of every trend table and is the running "
        "total of the months displayed, computed from the same population as the "
        "monthly values.")

    # ------------------------------------------------------------------ #
    section("Date ranges & time windows")
    fy_name = {1: "January", 4: "April", 7: "July", 10: "October"}.get(
        FY_START_MONTH, f"month {FY_START_MONTH}")
    presets = ", ".join(p for p in DATE_PRESETS if p not in ("Custom",))
    st.markdown(
        f"A **global reporting period** in the sidebar drives every report; each report "
        f"can override it with its own selector (default **{DEFAULT_DATE_PRESET}**): "
        f"{presets}, plus **Custom**. Ranges are anchored on the **reporting as-of "
        f"date** in the sidebar (which defaults to the latest activity date in your "
        f"data).\n\n"
        f"- **This/Last week** — Monday-based weeks.\n"
        f"- **This FY / Last FY** — the **whole** fiscal year starting 1 {fy_name} "
        f"(Microsoft FY), e.g. 1 Jul → 30 Jun — not year-to-date.\n"
        f"- **This/Last month**, **Last 3/6 months** — calendar-anchored on the as-of "
        f"date.\n\n"
        f"The This-Week / This-Month / This-Quarter / Year-to-Date KPI tiles compare "
        f"each window to the **prior equivalent** window for the delta arrows.\n\n"
        f"**Date values are read in whatever shape the export uses** — Excel serial "
        f"numbers (a date cell that was never formatted as a date, e.g. `45855`), ISO "
        f"stamps with or without a timezone, month names, and `d/m/y` triples in either "
        f"order (day-first vs month-first is inferred per column). Times of day are "
        f"dropped, since every date here is a calendar day. Values that still cannot be "
        f"read are counted in the data-quality banner, which lists examples.")
    with st.expander("Example: what each preset resolves to right now"):
        rows = {"Preset": [], "Start": [], "End": []}
        for p in DATE_PRESETS:
            if p in ("Custom", "All time"):
                continue
            r = date_preset_range(ctx.as_of, p, FY_START_MONTH)
            if r:
                rows["Preset"].append(p)
                rows["Start"].append(f"{r[0]:%d %b %Y}")
                rows["End"].append(f"{r[1]:%d %b %Y}")
        rows["Preset"].append("All time")
        rows["Start"].append("(no limit)")
        rows["End"].append("(no limit)")
        st.table(rows)
        st.caption(f"Anchored on the as-of date: {ctx.as_of:%d %b %Y}.")

    # ------------------------------------------------------------------ #
    section("AVS → Azure Native specifics")
    st.markdown(
        "- **Offering names are shown in full** (the migration path, e.g. *“SQL Server "
        "MI Migration (From AVS)”*) rather than the short factory offering.\n"
        "- **Azure-native target** is mapped from the path (SQL MI → *Azure SQL Managed "
        "Instance*, OSS DB → *Azure DB for PostgreSQL/MySQL*, etc.).\n"
        "- **Delivery stage**: *Completed* (closed) · *In Progress* (has an actual "
        "start date) · *Started* (open, not yet started).\n"
        "- The Sankey flows **path → Azure target → stage**.")

    # ------------------------------------------------------------------ #
    section("Insights engine (deterministic)")
    st.markdown(
        "Every insight is a transparent rule over the current selection (no AI). Each "
        "rule guards against thin data so it degrades gracefully on small slices. "
        "Insights include: portfolio scope, largest region, highest/lowest approval-"
        "rate region, overall closure rate, fastest-closing region, approval velocity, "
        "oldest open nomination, most common migration status, EOS risk hotspot, "
        "fastest-growing path, top Azure-native destination, ACR concentration, and "
        "data-quality issues.")

    # ------------------------------------------------------------------ #
    section("Data quality")
    st.markdown(
        "Cleaning records a per-row issue list and an aggregate count, surfaced in the "
        "data-quality banner and the **Insights** page. Detected issues include: "
        "numeric-prefixed regions, currency values contaminating count columns, dates "
        "landing in numeric columns, unparseable dates, approval-before-creation, "
        "missing creation dates, and invalid customer segments. Flagged values are "
        "**nulled rather than allowed to corrupt metrics**.")

    # ------------------------------------------------------------------ #
    section("Charts")
    st.markdown(
        "- Value axes are **integer-only** (counts have no decimals).\n"
        "- Operational-status bars put **status on the x-axis, stacked by region**.\n"
        "- Heatmaps use a red→green scale for risk concentration.\n"
        "- All charts render locally; the PDF export rasterises them offline.")

    st.divider()
    st.caption("All logic lives in app/core (schema, cleaning, rollup, analytics, "
               "metrics, insights). This page mirrors that code for auditability.")
