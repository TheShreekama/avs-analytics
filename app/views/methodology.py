"""Methodology — how every number on this dashboard is calculated.

A single, plain-language reference for the deterministic logic behind each
section.  Nothing here is AI-generated at runtime; every rule is implemented in
``app/core`` and is reproduced below so reviewers can audit it.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from app import state
from app.config import DATE_PRESETS, DEFAULT_DATE_PRESET, FY_START_MONTH
from app.core import glossary
from app.core.metrics import date_preset_range
from app.ui.theme import page_header, section


def render() -> None:
    ctx = state.ensure_context()
    page_header("Methodology & Logic",
                "Exactly how each metric, status and insight on this dashboard is computed — "
                "deterministic rules, no AI, no external calls.")
    scope = ctx.report.get("scope") or {}
    floor_label = scope.get("floor_fy", "FY25")
    floor_start = (f"{pd.Timestamp(scope['floor_start']):%d %b %Y}"
                   if scope.get("floor_start") is not None else "1 Jul 2024")

    # ------------------------------------------------------------------ #
    # The rules the reports themselves print.  Rendered from the same constant
    # the PDF and the HTML report read, so the page cannot document one thing
    # while the report states another.
    section("Every figure, and how it is worked out",
            help="Exactly the text the generated PDF and HTML reports carry in "
                 "their own Methodology & logic section.")
    st.caption("One entry per figure, under the name the reports give it. "
               "**Anything in bold is in the spreadsheet** — a column name "
               "written exactly as the file heads it, or a value written "
               "exactly as that column holds it — so any number here can be "
               "checked by opening the export and reading the same cell. "
               "Rendered from the same source the exported reports print, so "
               "this page and a circulated report cannot disagree.")
    for heading, items in glossary.REPORT_METHODOLOGY:
        st.markdown(f"##### {heading}")
        for item in items:
            if isinstance(item, glossary.Definition):
                st.markdown(f"**{item.title}**")
                for line in item.body:
                    st.markdown(f"> {line}")
            else:
                st.markdown(item)
    # The reporting floor above is stated in general terms because a circulated
    # report cannot know which file it will be read against.  This page can, so
    # it names the dataset's own floor underneath.
    st.caption(f"**In this dataset:** the reporting floor is **{floor_label}**, "
               f"from **{floor_start}**. Waves nominated before it were dropped "
               f"as the file was read, so no chart, table, total, insight, CSV "
               f"or export can include them.")

    # ------------------------------------------------------------------ #
    section("Reporting scope (what counts as an 'AVS nomination')")
    st.markdown(
        "The dashboard's **primary focus is AVS Migration Nominations** — accounts "
        "being *onboarded to AVS*. Work whose migration path says it is moving "
        "**'(From AVS)'** — away from AVS, onto an Azure-native service — is a "
        "different motion and is **kept to its own pages**:\n\n"
        "- **Primary reports** (Overview, Insights, and every Status Report page "
        "except the one below) leave that motion out entirely.\n"
        "- **Status Report → AVS → Azure Native** reports that motion and nothing "
        "else.\n"
        "- **Trend Analysis** reports each measure per migration category, so the "
        "two motions sit in separate sections of the same page rather than being "
        "mixed — and *Nodes Deployed* covers the AVS motions while *Cores "
        "Migrated* covers the (From AVS) one, the same Total Cores column under "
        "the noun that fits each.\n\n"
        "Which motion a nomination belongs to is read from its **Primary "
        "Migration Path**: a path that mentions moving *from AVS* is the "
        "**AVS → Azure Native** motion; a path that mentions moving *to AVS*, or "
        "that names an EGS, AV36 or ODAA offering, is **onboarding to AVS**.")

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
        "done/completed. (The report-level **On-Track / Completed** "
        "classification is stricter and reads every wave — see *Every figure, and "
        "how it is worked out* above.)\n"
        "    - **ACR / cores = summed** across the customer's waves.\n"
        "- **Nomination (wave-level)** — every wave/row counts (raw detail).\n\n"
        "**Deduplication keys on TPID**, never on the account name — the same account "
        "is spelled differently between worksheets and source systems. A row with no "
        "TPID at all falls back to its account name so it still rolls up to something "
        "rather than collapsing into every other untitled row; those rows are listed "
        "on **Data → Data Inconsistency**.")

    # ------------------------------------------------------------------ #
    section("Current state & the pipeline chart")
    st.markdown(
        "The account-state rule itself is stated above, under **The rules every "
        "report applies** — this section is what the *charts* then do with it.\n\n"
        "**Nominations by state shows only On-Track and Completed.** Blocked, "
        "deferred, cancelled and waiting accounts are deliberately left out, so "
        "the slices will **not** add up to every account in the category — the "
        "chart answers \"how much is live, how much is done\", not \"where is "
        "everything\".\n\n"
        "**Blocked & waiting accounts** is the section that reports what has "
        "stopped, on every dashboard and in both export formats (in the HTML "
        "report it sits behind a checkbox and is hidden until ticked). "
        "**Cancelled and deferred accounts are in no section**: they are out of "
        "the reported pipeline — no metric counts them — but a cancelled or "
        "deferred engagement is a decision already taken rather than work that "
        "has stopped.\n\n"
        "**An unapproved nomination is not On-Track**, and neither is a blank "
        "Current State. There is no fallback: the "
        "column is how the programme says an engagement is moving, and a wave "
        "nobody has said that about is ignored rather than counted — it lands "
        "in *Other* and appears in neither slice. (A file whose Current State "
        "column was never mapped therefore reports no on-track accounts at all, "
        "which is the honest answer; **Data → Column Mapping** is where to fix "
        "it.)\n\n"
        "**On-track by stage** groups on-track accounts by the Migration Status "
        "of the **on-track wave itself** — the wave the work is on — not of a "
        "later wave the account has already finished.\n\n"
        "*When the two columns disagree* — **Current State** says **Done** but "
        "**Migration Status** is not **7 - Completed** — the account is neither "
        "Completed nor "
        "On-Track and appears in neither slice. That is not a silent loss: those "
        "records are listed on **Data → Data Inconsistency** under *Current State "
        "contradicts Migration Status*, so the disagreeing column can be fixed at "
        "source.\n\n"
        "Note that the delivery-health status under *Delivery health, and Risk* "
        "above is a *different*, derived taxonomy feeding the Risk insight; the "
        "two are not interchangeable.")

    # ------------------------------------------------------------------ #
    section("Where each cut of the data lives")
    st.markdown(
        "One page owns each view, so the same numbers are not maintained in two "
        "places:\n\n"
        "- **Trend Analysis** owns every month-over-month trend, one page per "
        "measure with each migration category as a section on it: *Nomination "
        "Trends*, *ACR Trend*, *Nodes Deployed* (the AVS motions), *Cores "
        "Migrated* (AVS → Azure Native) and *Migrations Completed*. The "
        "Status Report pages deliberately carry **no** trends section — a "
        "measure is read across the portfolio in one place rather than a "
        "category at a time. Same calculations, same populations; only the "
        "page they sit on changed. Every trend is windowed from the reporting "
        "floor by **its own** date column, so no measure can chart a fiscal "
        "year before it.\n"
        "- **Status Report → AVS → Azure Native** owns that motion entirely — "
        "its metrics, pipeline, regional cut and **By offering & target** (full "
        "offering names and the Azure-native service each lands on).\n"
        "- **Regional breakdown** — *Migration status by region* and the "
        "*Region × status heatmap* — appears on **All AVS Migrations**, **EOS "
        "Migrations (All)** and **AVS → Azure Native**. The Gen-1 and Gen-2 "
        "pages are subsets of EOS Migrations (All) and do not repeat it. It "
        "counts **accounts** (each TPID's latest wave) regardless of the "
        "sidebar's Counting mode toggle, and shows only the stages a migration "
        "progresses through — the four in-flight ones plus Completed; "
        "**Deferred** and **Cancelled / Archived** are left out, so these counts "
        "are lower than the category's total accounts. It is **one chart**: the "
        "stacked bar that used to sit beside the heatmap carried the same region × "
        "stage counts, and two pictures of one cut is one too many. Selecting a "
        "row of the summary beside it (or clicking a heatmap cell in the HTML "
        "report) opens the accounts in that region *and* that stage — the pair "
        "names both halves, so the drill-down filters on both.\n\n"
        "- **Detailed data** on every Status Report page is **one row "
        "per account (TPID)** — never one row per wave. Each field comes from "
        "the wave that answers for it: *Most Recent / Latest Wave* and every "
        "wave-specific field (migration status, Current State, region, cores, "
        "actual dates, owners) from the account's **latest** wave; **Total ACR "
        "summed across every wave** (10M + 15M + 20M reads as 45M, not the last "
        "wave's 20M); and *Nom. Approval Date* from the **earliest** wave, the "
        "same Wave-1 rule New Engagements counts on. The PDF's account records "
        "are built by the same function, so the two cannot disagree.\n\n"
        "Every drill-down table names the **Solution Architect** and the "
        "**Factory PM** for each record, so a number leads to the person who "
        "owns it.")

    # ------------------------------------------------------------------ #
    section("How the reporting period changes a page")
    st.markdown(
        "The period selector at the top of every Status Report page does "
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
        "**ACR Pipeline and Nodes Deployment Planned ignore the period entirely.** "
        "They are read over the whole dataset — work nominated before the window is "
        "still work still to do — so they read the same on the This-FY row and the "
        "selected period's row. Every other sidebar filter still binds.\n\n"
        "**The pipeline section ignores the period.** *Current pipeline* — nominations by "
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
        "rule guards against thin data so it degrades gracefully on small slices — "
        "a rule with nothing to say says nothing, rather than padding the list "
        "with a zero.\n\n"
        "**Portfolio rules:** portfolio scope, largest region, highest/lowest "
        "approval-rate region, overall closure rate, fastest-closing region, "
        "approval velocity, oldest open nomination, most common migration status, "
        "risk hotspot, fastest-growing path, top Azure-native destination, ACR "
        "concentration, data-quality issues.\n\n"
        "**Programme rules** (read from the delivery columns — status, current "
        "state, planned vs actual dates, cores, waves):\n"
        "- **Pipeline** — ACR still to land and its share of claimed-plus-planned; "
        "which region carries most of it; nodes still to deploy against nodes "
        "already deployed.\n"
        "- **Excluded accounts** — how many accounts are neither on track nor "
        "completed and what share that is, the ACR held up behind them (and the "
        "largest single one), and the most common stated reason.\n"
        "- **Bottlenecks** — the in-flight stage holding the most waves and the "
        "ACR in it; the median days from approval to actual start.\n"
        "- **Delays** — waves past their planned end date with no actual end, by "
        "median days overdue and the furthest; and, for waves that did finish, the "
        "share that finished late with the median slip.\n"
        "- **Waves** — how many accounts run more than one wave, and how many have "
        "a completed latest wave while another wave is still on track (the "
        "classification rule, with its own count).\n"
        "- **Motions and EOS** — completion rates compared between the migration "
        "types, the Gen-1/Gen-2 mix of the EOS population with its node split, and "
        "EOS accounts excluded for want of a generation tag.")

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
        "generation tag vs. EOS path (both directions), **EOS accounts excluded from "
        "EOS reporting for want of a generation tag**, **Current State contradicting "
        "Migration Status**, unreadable dates, dates out of order, invalid Customer "
        "Segment, non-numeric values in numeric columns, regions needing cleaning, "
        "rows with no TPID and duplicate Task IDs. It is the single home for that "
        "detail; other pages only ever say whether there is anything to look at.")

    # ------------------------------------------------------------------ #
    section("Loading files — one dataset, one or many files")
    st.markdown(
        "A dataset can be **one file or several**. The source system exports per "
        "offering, so AVS nominations and the '(From AVS)' Azure-native ones often "
        "arrive separately; **Data → Data & Upload** takes them together and stacks "
        "them into a single dataset before anything else happens, so the mapping, "
        "cleaning, rollup, categories and every count see one portfolio.\n\n"
        "Headers are matched **case- and whitespace-insensitively** (`tpid ` and "
        "`TPID` are the same column), keeping the spelling from the file that "
        "introduced each column. A column one file does not have is simply blank for "
        "that file's rows — the same as an empty cell. Every row keeps a **Source "
        "File** value, and the upload page reports the row and account counts each "
        "file contributed after cleaning.\n\n"
        "**When an upload fails**, the page shows the whole diagnosis rather than one "
        "line: which file, which ingest stage (reading, combining, mapping, parsing, "
        "flooring, rolling up, registering), the exception, a plain-English likely "
        "cause, the line of application code that raised it, the row/column counts, "
        "which columns are empty and which fields are unmapped — plus the full "
        "traceback to paste into a bug report. Nothing is loaded on a failure; the "
        "previously active dataset is left untouched.")

    # ------------------------------------------------------------------ #
    section("The exported report")
    st.markdown(
        "**Reports & Export** builds the same report in two formats: a **PDF** to "
        "print or file, and a single **interactive HTML file** to email. Both "
        "select the same populations through the same code, so they cannot "
        "disagree.\n\n"
        "*The HTML export* is the dashboard as one self-contained file: charts you "
        "can hover, zoom and filter, drill-downs as accordions, tables you can sort "
        "and search, and a contents panel that follows you down the page. Charts, "
        "styles and data are all **inside the file** — nothing is fetched — so it "
        "opens from a mail client's download folder on a machine with no network, "
        "which is where it will be read. That is also why it is a few megabytes: "
        "the charting library has to travel with it.\n\n"
        "It follows the dashboard in the ways that matter. **Every chart, and every "
        "headline tile, opens the accounts behind it** — the same records the metric "
        "counted — and **clicking a chart filters them**: a bar on the nominations "
        "trend narrows the accounts to that month, a doughnut slice to that state, a "
        "stacked-bar segment or heatmap cell to that WW Region *and* stage. Clicking "
        "the same point again clears it, and the search box narrows whatever is "
        "showing. The **headline tiles are clickable too**: one accounts panel sits "
        "under the row and follows whichever tile you pick. Those are five separate "
        "lists rather than one filtered table because the metrics are counted at "
        "different grains — engagements per TPID at Wave-1, hosts over completed "
        "*wave* records — and merging them would have to pretend otherwise. "
        "The headline tiles gain a **This FY** row above them whenever the "
        "selected period is something else; money reads `$2M` / `$840K` on axes, "
        "in tiles and in **tooltips**. A **Wide** toggle sets the reading width, "
        "and the header carries one pill — the period.\n\n"
        "**Two sections are chosen when the report is built**, on Reports & "
        "Export: *Blocked & waiting accounts* (ticked by default) and "
        "*Insights* (unticked). Both apply to the PDF and the HTML alike.\n\n"
        "**Three things are then opt-in for the reader**, inside the HTML file: "
        "the blocked-accounts section and the **Methodology & logic** section "
        "each sit behind a **checkbox that starts unticked**, and the width "
        "toggle sets the reading width. The hiding is a CSS rule on the "
        "checkbox's own state, so a section is hidden from the first paint with "
        "no script having run — which is what makes it work in a file opened "
        "offline from a mail attachment. The data is always there; only its "
        "visibility is deferred. Methodology is reference material rather than "
        "reporting, so it is also **kept out of the contents list**.\n\n"
        "The methodology a report carries is the same text this page states, "
        "rendered from the same source, so a circulated report carries its own "
        "definitions.\n\n"
        "**A This-FY row sits above the selected period's row whenever the two "
        "differ** — the same rule the dashboards apply, including over *All "
        "time*, which spans several fiscal years and so loses the one you are "
        "in.\n\n"
        "**Neither the application nor the source file is named** anywhere in a "
        "generated report: not in the title, the cover, the page furniture, a "
        "section source line or the footer. A report is about the programme, and "
        "the default title says so (*Migration Programme Report*, editable "
        "before you generate).\n\n"
        "*The PDF* is built in two parts.\n\n"
        "*Part 1 — Executive reports.* One page-set per migration motion, "
        "carrying the same sections as the HTML report and in the same order: "
        "the headline tiles (over a This-FY row when the period is something "
        "else), the EOS programme matrix, each trend month by month and then "
        "fiscal year against fiscal year, the top ten accounts by ACR on the "
        "two broad motions, the current pipeline, the regional cut, the "
        "generation breakdown and the accounts that have stopped. Each report "
        "mirrors its Status Report page:\n\n"
        "| Report | Source |\n| --- | --- |\n"
        "| AVS Migrations | All AVS Migrations |\n"
        "| EOS Migrations | EOS Migrations (All), with Gen-1 and Gen-2 folded in "
        "as a generation breakdown |\n"
        "| AVS to Azure Native | AVS → Azure Native |\n\n"
        "*Part 2 — Supporting detail.* One drill-down per report, on landscape "
        "pages — what a printed page cannot open on demand: the status by region "
        "matrix behind the regional heatmap, the pipeline tables, and the account "
        "records grouped by region, largest ACR first. Long account lists are "
        "truncated with a note naming the total — the CSV export carries the "
        "rest. Each trend's own monthly numbers are printed under its chart in "
        "Part 1, so they are not repeated here.\n\n"
        "*Methodology & logic* closes the document, and the data-inconsistency "
        "appendix follows it when selected.\n\n"
        "Every report links to its drill-down and every drill-down links back, as "
        "real PDF destinations rather than styled text, alongside a clickable "
        "contents page and a bookmark outline.\n\n"
        "The PDF is built from the same calculations the dashboards use, on the "
        "same populations, so a figure cannot read one way on screen and "
        "another on the page. Like those dashboards it always counts accounts at "
        "their latest wave — the sidebar's **counting mode** does not change it. "
        "Sidebar filters and the reporting period do apply.")

    # ------------------------------------------------------------------ #
    section("Charts")
    st.markdown(
        "- Value axes are **integer-only** (counts have no decimals).\n"
        "- Regional breakdowns are a **single heatmap** — WW Region against "
        "migration status, counted per account at its latest wave, with the "
        "count written in each cell.\n"
        "- Heatmaps use a red→green scale for risk concentration.\n"
        "- All charts render locally; the PDF export rasterises them offline with "
        "matplotlib, so nothing ships a bundled browser.")

    st.divider()
    st.caption("All logic lives in app/core (schema, cleaning, rollup, analytics, "
               "metrics, insights). This page mirrors that code for auditability.")
