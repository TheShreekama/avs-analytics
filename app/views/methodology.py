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
        "**Deduplication keys on TPID**, never on the account name — the same account "
        "is spelled differently between worksheets and source systems. A row with no "
        "TPID at all falls back to its account name so it still rolls up to something "
        "rather than collapsing into every other untitled row; those rows are listed "
        "on **Data → Data Inconsistency**.")

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
        "on-premises, VMG, AWS/VMC, AVS-to-AVS and EOS refreshes. Every **EOS "
        "Migration** account is included here too, whatever its own path reads.\n"
        "- **AVS → Azure Native** — the '(From AVS)' offerings, moving workloads off "
        "AVS onto Azure-native services.\n"
        "- **EOS Migration** — every EOS account in one view. **Gen-1** and "
        "**Gen-2** are subsets of it, one page each.\n\n"
        "**EOS population.** An account is an **EOS Migration** account when ANY of "
        "its waves carries an **\"AVS Migration - Gen1\"** or **\"AVS Migration - "
        "Gen2\"** tag — one tagged wave brings the whole account into scope, and the "
        "tag also sets its generation. When no wave carries either tag, the offering "
        "falls back to deciding it: a **Primary Migration Path** (or Factory / Linked "
        "Offering) reading **AV36/AV36P/AV52 - EOS** puts the account in scope with no "
        "generation. Everything comes from the single nominations export.\n\n"
        "**Tag vs. path consistency.** A file can disagree with itself two ways: "
        "accounts **tagged Gen-1/Gen-2 with no EOS path** on any wave, and **waves on "
        "the EOS path whose account carries no tag**. Both are still in EOS scope — "
        "they are reported, with the offending records, on **Data → Data "
        "Inconsistency**, which is the single place that lists them.\n\n"
        "**Generation is decided per TPID, across all of its waves:**\n"
        "1. Any wave tagged **\"AVS Migration - Gen1\"** → the account is **Gen-1**; "
        "**\"AVS Migration - Gen2\"** → **Gen-2**. Gen-1 wins if both appear on "
        "different waves. Tags arrive concatenated with no separator "
        "(*\"Qualify and AccelerateAVS Migration - Gen1\"*), so the marker is matched "
        "inside the cell regardless of spacing, dashes or neighbouring tags.\n"
        "2. No generation tag on any wave → no generation. If the account is in EOS "
        "scope through its migration path (*AV36/AV36P/AV52 - EOS*) it still counts in "
        "**EOS Migration**, but is **never folded into Gen-1 or Gen-2** — the "
        "generation split on that page names it separately, and the records are listed "
        "on **Data → Data Inconsistency** so the missing tag can be fixed at source.")

    # ------------------------------------------------------------------ #
    section("Metric rules (unique TPIDs vs. records)")
    st.markdown(
        "**TPID is the authoritative identifier** for every join, lookup, "
        "classification and count. Account names differ between worksheets and "
        "source systems, so they are never used for matching.\n\n"
        "| Metric | Rule | Unit | Dated by |\n"
        "| --- | --- | --- | --- |\n"
        "| New Engagements | Unique TPIDs whose **Wave-1** row (lowest wave number) "
        "was approved inside the period | Customers | Nom. Approval Date |\n"
        "| Migrations Completed | Unique TPIDs whose **latest** wave is "
        "`7 - Completed` | Customers | Actual End Date |\n"
        "| Hosts / Cores Migrated | **Sum of Total Cores** over `7 - Completed` wave "
        "records — *not* a TPID count; each source record counted once | Hosts (Cores "
        "on AVS → Azure Native) | Actual End Date |\n"
        "| On-Track Accounts | Accounts whose **latest wave** reads *On Track* in the "
        "**Current State** column | Customers | *snapshot — not period-bound* |\n"
        "| ACR Claimed | **Sum of Total ACR over every wave** whose Actual End Date "
        "falls in the period | Currency | Actual End Date |\n"
        "| Nomination Count (MoM) | Unique TPIDs per month, each counted once, placed "
        "in the month of its Wave-1 date | Customers | Wave-1 approval or created "
        "date (your choice) |\n"
        "| ACR Claimed (MoM) | The same claiming waves, split by the month each one "
        "ended | Currency | Actual End Date |\n\n"
        "**Completion always evaluates the latest wave.** A TPID whose Wave 7 is "
        "completed but whose Wave 8 is still running is *not* a completed migration.\n\n"
        "**ACR Claimed is wave-level, not account-level.** If Waves 2 and 3 of one "
        "account and Wave 5 of another ended inside the window, all three waves' ACR "
        "is summed. A wave that ended outside the window contributes nothing, even "
        "when a sibling wave of the same account ended inside it; a wave with no "
        "Actual End Date has not claimed and never counts. Across a multi-month "
        "period the trend chart splits that same total by the month each wave ended, "
        "so the months add back up to the tile.\n\n"
        "**Cumulative** is the final column of every trend table and is the running "
        "total of the months displayed, computed from the same population as the "
        "monthly values.\n\n"
        "Money is shown as **$1.2M / $840.0K** wherever it appears — tiles, trend "
        "tables, drill-downs and detailed data alike.")

    # ------------------------------------------------------------------ #
    section("Current state & the pipeline chart")
    st.markdown(
        "**On-Track is read from the Current State column** of the account's latest "
        "wave — it is not inferred from \"not finished yet\". The precedence, first "
        "match winning:\n\n"
        "1. **Completed** — that wave's Migration Status is `7 - Completed`.\n"
        "2. **Cancelled** — the wave resolved to a cancelled/archived status.\n"
        "3. **On-Track** — Current State reads *On Track* / *On-Track*.\n"
        "4. **Other** — whatever else Current State says: *Blocked - Customer*, "
        "*Blocked - Account team*, *Waiting action on follow up date*. These are "
        "unfinished but **not on track**, and are counted in neither.\n\n"
        "**Nominations by state shows only On-Track and Completed.** Cancelled, "
        "blocked and waiting accounts are deliberately left out, so the slices will "
        "**not** add up to every account in the category — the chart answers \"how "
        "much is live, how much is done\", not \"where is everything\". The full "
        "breakdown is always available in **Detailed data** at the bottom of each "
        "dashboard, grouped by Current State.\n\n"
        "*Fallback:* where Current State is blank, an account that is neither "
        "completed nor cancelled falls back to On-Track, so an unmapped column cannot "
        "silently empty the pipeline. **On-track by stage** then groups those same "
        "accounts by the Migration Status label of their latest wave.\n\n"
        "*When the two columns disagree* — Current State says *Done* but Migration "
        "Status is not `7 - Completed` — the account is neither Completed nor "
        "On-Track and appears in neither slice. That is not a silent loss: those "
        "records are listed on **Data → Data Inconsistency** under *Current State "
        "contradicts Migration Status*, so the disagreeing column can be fixed at "
        "source.\n\n"
        "Note that `eos_status` (the section below) is a *different*, derived "
        "taxonomy used by the Status Reports; the two are not interchangeable.")

    # ------------------------------------------------------------------ #
    section("How the reporting period changes a page")
    st.markdown(
        "The period selector at the top of every Migration Analytics page does "
        "more than filter. **Each section states the window it is measured over, "
        "under its own title**, because they are not all the same one.\n\n"
        "**A This-FY row above the selected one.** When the selected period is "
        "anything other than *This FY*, the executive summary shows two rows: the "
        "fiscal year you are in, then the period you picked. A month or a quarter "
        "on its own loses the year it sits in, so the year is put back above it. "
        "The two rows are **computed independently** — each metric is recalculated "
        "from its own window, with its own underlying records behind its own "
        "drill-down — never one derived from the other. Selecting *This FY* shows "
        "the single row, since the two would be identical.\n\n"
        "**All time splits the trends by fiscal year.** Over a bounded window each "
        "trend is bars plus a cumulative line. Over *All time* that line just gets "
        "longer every year, so the shape changes instead: **one line per fiscal "
        "year on a shared Jul → Jun axis**, a colour each, which is what makes "
        "year-over-year movement readable. Nomination count, ACR claimed, hosts "
        "(cores) migrated and migrations completed all switch together. Two things "
        "follow from it:\n"
        "- **No Cumulative column** in that view — a running total across unrelated "
        "fiscal years would not mean anything. Per-FY totals are printed under the "
        "chart, and the years sit side by side in the underlying-data panel.\n"
        "- **Points are keyed `FY27 Sep`**, not `Sep`: every year has a September, "
        "so the line a point sits on is part of its identity. Click-through works "
        "the same as anywhere else.\n\n"
        "**The pipeline ignores the period.** *Current pipeline* — nominations by "
        "state and on-track by stage — is a snapshot of where accounts stand now. "
        "It shows **every** account in the category at its latest wave, whatever "
        "its nomination date and whichever window is selected, and says so under "
        "its title. Narrowing a snapshot by a historical window would answer a "
        "question nobody asked.")

    # ------------------------------------------------------------------ #
    section("Drill-down — every number opens its records")
    st.markdown(
        "No number on this dashboard is a dead end. Each metric is computed together "
        "with the rows that produced it, and those exact rows — never a recomputed "
        "lookalike — are what a drill-down shows, so a table can never disagree with "
        "the chart above it.\n\n"
        "- **Charts** are selectable: click a bar, slice, point or month and the "
        "records behind it open underneath.\n"
        "- **Summary tables** select the same buckets: clicking the June row does what "
        "clicking the June bar does.\n"
        "- **Cross-tabs and heatmaps** have no single record-level bucket to click, so "
        "they expose the table they were drawn from instead.\n"
        "- **Every panel exports to CSV**, and an export always contains the whole "
        "selection even when the on-screen table is capped for responsiveness.\n\n"
        "Chart labels are drawn on a **category axis** so a click returns the label "
        "exactly as written — otherwise a month written *2026-06* comes back as "
        "*2026-06-01* and matches nothing. On a fiscal-year-split chart the label "
        "alone is still ambiguous, so the trace a point belongs to is read too and "
        "the selection becomes *FY27 Sep*.")

    # ------------------------------------------------------------------ #
    section("Date ranges & time windows")
    fy_name = {1: "January", 4: "April", 7: "July", 10: "October"}.get(
        FY_START_MONTH, f"month {FY_START_MONTH}")
    presets = ", ".join(p for p in DATE_PRESETS if p not in ("Custom",))
    st.markdown(
        f"A **global reporting period** in the sidebar drives every report; each report "
        f"has its own selector at the top of the page that overrides it (default "
        f"**{DEFAULT_DATE_PRESET}**): "
        f"{presets}, plus **Custom**. Ranges are anchored on the **reporting as-of "
        f"date** in the sidebar (which defaults to **today**, so This FY follows the "
        f"calendar; change it there to report as of any other day).\n\n"
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
        "**nulled rather than allowed to corrupt metrics**.\n\n"
        "**Data → Data Inconsistency** is the report that lists them: every check with "
        "its count, the offending records and a CSV export, over the whole file — "
        "generation tag vs. EOS path (both directions), **Current State contradicting "
        "Migration Status**, unreadable dates, dates out of order, invalid Customer "
        "Segment, non-numeric values in numeric columns, regions needing cleaning, "
        "rows with no TPID and duplicate Task IDs. It is the single home for that "
        "detail; other pages only ever say whether there is anything to look at.")

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
