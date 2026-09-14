"""Plain-language explanations shown behind every ⓘ marker.

One place for "what exactly does this number mean", written against the columns
of the nominations export, so the tooltip on a dashboard, the Methodology page
and the code all say the same thing.
"""
from __future__ import annotations

from . import segments

# --------------------------------------------------------------------------- #
# Metrics
# --------------------------------------------------------------------------- #
NEW_ENGAGEMENTS = (
    "Unique customers (TPIDs) whose FIRST wave was approved inside the reporting "
    "period.\n"
    "• Takes each TPID's Wave-1 row (lowest Phase/Wave number).\n"
    "• Keeps it when its Nom. Approval Date falls in the period.\n"
    "• Counts each TPID once — later waves of the same account never add to it."
)

MIGRATIONS_COMPLETED = (
    "Unique customers (TPIDs) whose migration finished inside the period.\n"
    "• Takes each TPID's LATEST wave (highest Phase/Wave number).\n"
    "• That wave's Migration Status must be '7 - Completed'.\n"
    "• Dated by its Actual End Date.\n"
    "An account with Wave 7 completed but Wave 8 still running is NOT counted — "
    "completion always follows the latest wave."
)

HOSTS_MIGRATED = (
    "Sum of the Total Cores column — treated as nodes/hosts — over every wave "
    "record that is '7 - Completed' with an Actual End Date inside the period.\n"
    "This is deliberately NOT a customer count: an account with three completed "
    "waves contributes the cores of all three. Each source record is counted once."
)

CORES_MIGRATED = HOSTS_MIGRATED.replace("nodes/hosts", "cores")

ON_TRACK_ACCOUNTS = (
    "Customers (TPIDs) whose LATEST wave is genuinely in flight. BOTH must "
    "hold:\n"
    "1. Migration Status is one of the four in-flight codes — '1 - Validating "
    "Commitment & Initial Scope', '2 - Executing Pre-Requisites', '3 - Finalize "
    "Scope', '4 - Executing Migration'. A wave that is '5 - Deferred by "
    "Customer', '6 - Cancelled / Archived' or '7 - Completed' is never on "
    "track, whatever its Current State says.\n"
    "2. Current State reads 'On Track' / 'On-Track'. 'Blocked - Customer', "
    "'Blocked - Account team' and 'Waiting action on follow up date' are not on "
    "track, whatever the status says.\n"
    "Where Current State is blank the status alone decides, so an unmapped "
    "column cannot empty the pipeline.\n"
    "This tile is a snapshot of where the category stands now — the reporting "
    "period does not narrow it."
)

ACR_CLAIMED = (
    "ACR of every wave whose ACTUAL END DATE falls inside the reporting period.\n"
    "• Wave-level, not account-level: if Waves 2 and 3 of one account and Wave 5 "
    "of another ended inside the window, all three waves' Total ACR is summed.\n"
    "• A wave that ended outside the window contributes nothing, even when a "
    "sibling wave of the same account ended inside it.\n"
    "• A wave with no Actual End Date has not claimed and is never counted.\n"
    "Shown as $1.2M / $840.0K. Across a multi-month period the trend chart splits "
    "the same total by the month each wave ended."
)

# --------------------------------------------------------------------------- #
# Sections
# --------------------------------------------------------------------------- #
ACR_PIPELINE = (
    "The ACR carried by every ELIGIBLE WAVE — the approved, unblocked, "
    "unfinished work, and therefore the commercial value still to land.\n"
    "Eligibility is judged per WAVE, and all three conditions must hold: the "
    "wave's latest Migration Status is NOT '7 - Completed', '5 - Deferred by "
    "Customer' or '6 - Cancelled / Archived'; the nomination is APPROVED; and "
    "its Current State does NOT contain 'Blocked'. Any single exclusion drops "
    "the wave.\n"
    "It is a snapshot of where things stand: the reporting period does not "
    "narrow it. Distinct from ACR Claimed, which is value already realised by "
    "waves that ended inside the period — a wave is in one or the other, never "
    "both."
)

NODES_PLANNED = (
    "The deployment still to come: the sum of TOTAL CORES over the same "
    "eligible waves the ACR Pipeline is built from — status not completed, "
    "deferred or cancelled; nomination approved; Current State not blocked.\n"
    "Reported as NODES because that is what the AVS motions deploy, from the "
    "Total Cores column that records them. Read against Hosts Migrated, which "
    "is the deployment already delivered.\n"
    "Shown on the EOS reports only — that programme is the one that plans a "
    "node refresh."
)

EXCLUDED_ACCOUNTS = (
    "Accounts whose state is neither On-Track nor Completed: blocked, "
    "deferred, cancelled / archived, or waiting on a follow-up.\n"
    "They are reported HERE AND NOWHERE ELSE. None of them is counted in the "
    "headline tiles, the trends, the pipeline chart or the regional cut, and "
    "none of those numbers appears in this section — every account resolves to "
    "exactly one state, so the two cuts partition the population with nothing "
    "double-counted and nothing dropped.\n"
    "The stated reason is read from Migration Status for cancelled and "
    "deferred accounts — the column that took them out — and from Current "
    "State for the rest, which is where the reason lives. Nothing is inferred: "
    "an account with neither reads 'Not stated'."
)

EXECUTIVE_SUMMARY = (
    "Headline numbers for this migration category over the selected reporting "
    "period. Every tile has its own ⓘ, and 'Records behind these tiles' opens the "
    "exact rows each number came from."
)

TRENDS = (
    "Month-by-month movement for ONE measure, in every migration category — so "
    "the measure can be read across the portfolio rather than a category at a "
    "time. Each category is its own section, over the single reporting period "
    "selected at the top of the page.\n"
    "Each table's final column is Cumulative — the running total of the months "
    "shown, never a different population. Click a bar or a table row to open "
    "that month's records.\n"
    "Over 'All time' the shape changes: each fiscal year becomes its own line "
    "on a shared Jul → Jun axis, so the years read against one another instead "
    "of stretching into one ever-longer series. There is no Cumulative column "
    "in that view — a running total across unrelated fiscal years would not "
    "mean anything. Points are keyed 'FY27 Sep', since every year has a "
    "September."
)

TREND_NOMINATIONS = (
    "Unique customers (TPIDs) per month, placed in the month of their Wave-1 date "
    "(approval or creation, per the Trend basis above). Each TPID appears in one "
    "month only."
)

TREND_ACR = (
    "ACR claimed per month: each wave's Total ACR placed in the month of its "
    "Actual End Date. An account with waves ending in two months appears in "
    "both, each time for that wave's ACR only — the months add up to the ACR "
    "Claimed tile above."
)

TREND_HOSTS = (
    "Nodes deployed per month — the Total Cores column, by Actual End Date, over "
    "wave records whose Migration Status is '7 - Completed'. Record-level, not a "
    "customer count: an account with three completed waves contributes all three."
)

#: The same column and the same rule, under the noun the AVS → Azure Native
#: motion uses: it moves cores to Azure-native services rather than nodes to AVS.
TREND_CORES = TREND_HOSTS.replace("Nodes deployed", "Cores migrated")

TREND_COMPLETED = (
    "Completed migrations per month: unique TPIDs whose latest wave is "
    "'7 - Completed', placed in the month of that wave's Actual End Date."
)

PIPELINE = (
    "Where the category stands RIGHT NOW, taken from each customer's latest "
    "wave. Deliberately independent of the reporting period: every account in "
    "the category is here, whatever its nomination date and whichever window is "
    "selected above. Narrowing a snapshot by a historical window would answer a "
    "question nobody asked."
)

BY_STATE = (
    "Customers by current state, from each TPID's latest wave. Only two states "
    "are reported:\n"
    "• Completed — that wave's Migration Status is '7 - Completed'.\n"
    "• On-Track — that wave is in flight (Migration Status 1-4) AND its Current "
    "State reads 'On Track'.\n"
    "Cancelled accounts, and accounts sitting in a blocked or waiting state, are "
    "deliberately left out, so the chart shows live and finished work only — the "
    "slices will not add up to every account in the category.\n"
    "ACR is the latest wave's Total ACR."
)

BY_STAGE = (
    "ALL on-track customers — in-flight Migration Status (1-4) with Current "
    "State reading On-Track — whatever the reporting period says, grouped by "
    "the stage of their latest wave (the Migration "
    "Status label, e.g. 'Executing Pre-Requisites', 'Migration In Progress'), with "
    "the account count and ACR for each stage."
)

REGIONAL_BREAKDOWN = (
    "Where the category sits geographically, by migration status. Counted at "
    "ACCOUNT grain — each TPID's latest wave — so an account with five waves is "
    "one account here, matching the state chart above it — and counted that way "
    "regardless of the sidebar's Counting mode toggle.\n"
    "Click a segment of the stacked bar to open exactly the accounts in that "
    "region AND that stage: a segment names both, so the drill-down filters on "
    "the pair rather than on the region alone.\n"
    "Only the stages a migration progresses through are shown: '1 - Validating "
    "Commitment & Initial Scope', '2 - Executing Pre-Requisites', '3 - Finalize "
    "Scope', '4 - Executing Migration' and '7 - Completed'. Deferred ('5') and "
    "Cancelled / Archived ('6') are left out, so the chart is not padded with "
    "work nobody is doing — the counts here will therefore be lower than the "
    "category's total account count.\n"
    "A snapshot: the reporting period does not narrow it."
)

OFFERING_AND_TARGET = (
    "Which '(From AVS)' offering each nomination is, by its full Primary "
    "Migration Path ('SQL Server MI Migration (From AVS)'), and which "
    "Azure-native service it lands on. Wave-level counts over every nomination "
    "in the category, not narrowed by the reporting period."
)

DETAILED_DATA = (
    "One row per ACCOUNT (TPID) — an account with five waves is one row, never "
    "five. Each field comes from the wave that answers for it:\n"
    "• Most Recent / Latest Wave, and every wave-specific field (migration "
    "status, Current State, region, cores, actual dates, owners) — from the "
    "account's LATEST wave, so the row reads as where it stands now.\n"
    "• Total ACR — summed across EVERY wave of the account. Waves of 10M, 15M "
    "and 20M show as 45M; the latest wave's 20M alone would understate it.\n"
    "• Nom. Approval Date — from the EARLIEST wave (lowest wave number), the "
    "same Wave-1 rule the New Engagements tile counts on, because that is when "
    "the account was nominated.\n"
    "Group it to read subtotals, then export to CSV."
)

REPORTING_PERIOD = (
    "The window every metric on this page is measured over. 'Global range' follows "
    "the sidebar setting; any other choice overrides it for this page only. "
    "Windows are anchored on the reporting as-of date in the sidebar, which "
    "defaults to today — so This FY is the fiscal year you are currently in, "
    "covering the whole year (1 Jul → 30 Jun) rather than year-to-date.\n"
    "Two choices change what the page shows, not just what it filters:\n"
    "• Anything OTHER than This FY adds a This-FY row above the executive "
    "summary, so a month or a quarter is read against the year it sits in. The "
    "two rows are computed independently, each from its own window with its own "
    "records.\n"
    "• 'All time' splits every trend into one line per fiscal year.\n"
    "The Current pipeline section ignores this setting entirely: it is a "
    "snapshot of where accounts stand now."
)

# --------------------------------------------------------------------------- #
# Category populations
# --------------------------------------------------------------------------- #
GENERATION_RULE = (
    "The Tags column decides both scope and generation, per customer (TPID) "
    "across ALL of its waves:\n"
    "• ONE wave tagged 'AVS Migration - Gen1' makes the whole account an EOS "
    "Migration account, generation Gen-1.\n"
    "• 'AVS Migration - Gen2' likewise makes it Gen-2.\n"
    "• Gen-1 wins when both tags appear on different waves.\n"
    "Tags arrive glued together with no separator ('Qualify and AccelerateAVS "
    "Migration - Gen1'), so the marker is matched inside the cell — spacing, "
    "hyphen vs en dash and neighbouring tags cannot hide it."
)

EOS_POPULATION = (
    "An account is an EOS Migration account when either:\n"
    "1. ANY of its waves carries an 'AVS Migration - Gen1' or 'AVS Migration - "
    "Gen2' tag — that tag also sets the account's generation; or\n"
    "2. no wave carries either tag, but the Primary Migration Path (or Factory / "
    "Linked Offering) reads as EOS, e.g. 'AV36/AV36P/AV52 - EOS' — in scope, but "
    "with no generation.\n"
    "Either way one qualifying wave brings every wave of the account with it."
)

EOS_UNTAGGED = (
    "EOS accounts that got here through the offering fallback: no wave carries an "
    "'AVS Migration - Gen1/Gen2' tag, but the migration path reads as EOS (e.g. "
    "'AV36/AV36P/AV52 - EOS'). They count on the EOS Migration dashboard, but with "
    "no generation to report — never folded into Gen-1 or Gen-2. The records are "
    "listed on Data → Data Inconsistency."
)

CATEGORY_HELP = {
    segments.CAT_EOS_ALL: (
        "Every EOS Migration account in one view — Gen-1, Gen-2 and any account in "
        "scope through its migration path with no generation tag. The two generation "
        "pages are subsets of this one; the untagged accounts have no page of their "
        "own and are listed on Data → Data Inconsistency instead.\n\n" + EOS_POPULATION
    ),
    segments.CAT_EOS_GEN1: f"{EOS_POPULATION}\n\n{GENERATION_RULE}",
    segments.CAT_EOS_GEN2: f"{EOS_POPULATION}\n\n{GENERATION_RULE}",
    segments.CAT_ALL_AVS: (
        "Every nomination whose TARGET platform is AVS, whatever it migrates "
        "from — on-premises, VMG, AWS/VMC, AVS-to-AVS and EOS refreshes. "
        "Derived from the Primary Migration Path and Factory Offering. Paths "
        "reading '(From AVS)' are excluded and reported only under AVS → Azure "
        "Native, since those are leaving AVS rather than onboarding to it."
    ),
    segments.CAT_AVS_NATIVE: (
        "Nominations migrating AWAY from AVS to Azure-native services — the "
        "offerings whose Primary Migration Path contains '(From AVS)', e.g. "
        "'SQL Server MI Migration (From AVS)'.\n"
        "This motion is reported HERE AND NOWHERE ELSE. It is excluded from All "
        "AVS Migrations (which is onboarding TO AVS) and from every EOS "
        "category (which is refreshing ageing AVS hosts) — not even an 'AVS "
        "Migration - Gen1/Gen2' tag pulls a (From AVS) account into them."
    ),
}


EOS_MATRIX = (
    "The EOS programme's month-by-month grid, split by the generation an "
    "account is refreshing ON TO.\n"
    "Every EOS account is coming FROM Gen-1 hardware — that is what puts it in "
    "scope — so the two blocks are read as 'Gen1 to …' and are selected by the "
    "account's own generation tag: 'Gen1 to Gen1' is every account tagged 'AVS "
    "Migration - Gen1', 'Gen1 to Gen2' every account tagged '- Gen2'. Accounts "
    "in EOS scope by migration path with no generation tag on any wave belong "
    "to neither block; they are listed under Data → Data Inconsistency.\n"
    "Rows use the same calculations as the rest of the report: new engagements "
    "are unique TPIDs in the month of their Wave-1 approval date; migration "
    "ends are unique TPIDs whose LATEST wave is '7 - Completed', in the month "
    "of its Actual End Date; hosts migrated is the sum of Total Cores over "
    "every completed wave record, never a count of accounts.\n"
    "MIGRATION START is derived, since the export has no such field: an "
    "account's earliest wave whose Current State reads 'On Track' or 'Done' — "
    "the first wave actually under way — and from it the Actual Start Date, "
    "falling back to Planned Start Date and then to Nom. Approval Date. An "
    "account with no such wave has not started and is not counted.\n"
    "ENGAGEMENT END repeats the migration-end figure. The export marks when a "
    "wave ended but not an engagement closure distinct from its last wave "
    "completing, so an account whose latest wave has completed is the closest "
    "the data comes to an engagement that ended — the two rows therefore carry "
    "the same values by construction, not by coincidence.\n"
    "Each fiscal year closes with its own TOTAL column, summing that year's "
    "months. Every measure places a TPID in exactly one month, so a year's "
    "total is the sum of its months with nothing double-counted."
)


# --------------------------------------------------------------------------- #
# The methodology printed inside the reports themselves
# --------------------------------------------------------------------------- #
#: "Methodology & logic" as (heading, paragraphs), shared by the PDF, the HTML
#: report and the Methodology page, so the three cannot document the same rule
#: three different ways.  ``**bold**`` markers are rendered by both exporters.
#:
#: This describes the implementation, not an intention: every rule below is one
#: a function in ``app/core`` actually applies, named so a reader can go and
#: check it.
REPORT_METHODOLOGY: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Accounts, waves and the latest wave", (
        "An **account is a TPID**, and a TPID can hold several waves "
        "(Wave-1, Wave-2 …). Account names are never used for matching — the "
        "same account is spelled differently between source systems.",
        "A TPID's **latest wave** is its highest wave number (ties broken by "
        "creation date), and its **Wave-1** is its lowest. Each field is read "
        "from the wave that answers for it: current status, region and stage "
        "from the latest wave; the nomination approval date from Wave-1; "
        "**Total ACR summed across every wave**.",
        "Every unique-TPID metric counts an account **once**, however many "
        "waves it has, so no multi-wave account is ever double-counted.",
    )),
    ("On-Track vs. Completed — the account classification", (
        "A **wave** is on track when both halves hold: its Migration Status is "
        "one of the four in-flight codes (**1 - Validating Commitment & Initial "
        "Scope**, **2 - Executing Pre-Requisites**, **3 - Finalize Scope**, "
        "**4 - Executing Migration**) **and** its Current State reads *On "
        "Track*. A blank Current State falls back to the status alone.",
        "An account is **On-Track when ANY of its waves is on track** — not "
        "only its latest one. Work still running on an earlier wave is work "
        "still running.",
        "An account is **Completed only when both** conditions hold: its "
        "**latest wave is 7 - Completed**, **and none of its waves is on "
        "track**. An account whose latest wave has completed while another wave "
        "is on track is therefore classified **On-Track**, not Completed.",
        "The remaining precedence, applied to the latest wave once the "
        "on-track test has failed: **Cancelled / Archived**, then **Blocked** "
        "(Current State contains *Blocked*), then **Deferred** "
        "(**5 - Deferred by Customer**), then **Other** (waiting on a "
        "follow-up, or a state the export does not name).",
        "Every account resolves to **exactly one** state, so the reported cut "
        "and the excluded cut partition the population: nothing is counted "
        "twice and nothing is lost.",
    )),
    ("Accounts outside the reported pipeline", (
        "Blocked, deferred, cancelled / archived and waiting accounts are "
        "**reported in their own section and nowhere else**. They are not in "
        "the headline metrics, not in the state chart, not in the trends and "
        "not in the regional cut.",
        "**New Engagements is the one deliberate exception**, and it is not an "
        "exclusion at all: an account that was nominated and approved inside the "
        "period is counted there whatever became of it afterwards, because "
        "intake is a historical fact and a figure that moved when an account got "
        "blocked would be reporting something else. No metric that reads an "
        "account's *state* — completions, on-track accounts, the state chart, "
        "ACR Pipeline, Nodes Deployment Planned — counts them.",
        "That section reports what the data supports about them: how many "
        "accounts, the ACR they hold up, their state distribution, their WW "
        "Region distribution, the reason each one carries (Migration Status "
        "for cancelled and deferred accounts, since that is the column that "
        "took them out; Current State for the rest) and how many waves sit "
        "behind them. No reason is inferred — a blank reads *Not stated*.",
    )),
    ("EOS reporting — Gen-1 and Gen-2 only", (
        "An account is in **EOS scope** when any of its waves carries an "
        "**AVS Migration - Gen1** or **AVS Migration - Gen2** tag; that tag "
        "also fixes the generation, and Gen-1 wins if both appear. Failing any "
        "tag, an **AV36/AV36P/AV52 - EOS** migration path or offering brings "
        "the account into scope with **no generation**.",
        "**EOS reports cover Gen-1 and Gen-2 only.** An account in scope by "
        "path with no generation tag is excluded from every EOS total, chart, "
        "calculation and insight — EOS is reported by generation, and an "
        "ungenerationed account would make the combined figure disagree with "
        "the sum of its two blocks.",
        "Those accounts are **not discarded**: they remain AVS migrations, and "
        "they are listed under **Data Inconsistency** so the missing tag can be "
        "fixed at source, after which they report like any other EOS account.",
    )),
    ("ACR Pipeline", (
        "**ACR Pipeline** is the ACR of every **eligible wave** — the approved, "
        "unblocked, unfinished work. Eligibility is judged **per wave**, and a "
        "wave must satisfy **all three** conditions:",
        "1. its latest **Migration Status is not** *7 - Completed*, "
        "*5 - Deferred by Customer* or *6 - Cancelled / Archived*;",
        "2. the **nomination is approved**; and",
        "3. its **Current State does not contain *Blocked***.",
        "Any single exclusion drops the wave. The figure is a snapshot of "
        "where things stand — the reporting period does not narrow it — and it "
        "is deliberately separate from **ACR Claimed**, which is ACR already "
        "realised by waves that ended inside the period.",
    )),
    ("Nodes Deployment Planned (EOS reports)", (
        "**Nodes Deployment Planned** sums the **Total Cores** column over the "
        "**same eligible waves** the ACR Pipeline is built from — the identical "
        "three conditions, applied per wave.",
        "It is reported on the **EOS reports only**, and presented as "
        "**Nodes**: the AVS motions deploy nodes, and Total Cores is the column "
        "that records them. It answers what is still to be deployed, where "
        "*Hosts Migrated* answers what already has been.",
    )),
    ("The other measures", (
        "**New Engagements** — unique TPIDs whose **Wave-1** nomination "
        "approval date falls in the period.",
        "**Migrations Completed** — unique TPIDs classified Completed by the "
        "rule above, dated by their latest wave's Actual End Date.",
        "**Hosts / Cores Migrated** — the **sum of Total Cores over completed "
        "wave records** in the period, each source record counted once. "
        "Deliberately a wave-level measure and not an account count: a "
        "completed wave deployed its nodes whatever the account's overall "
        "state now is.",
        "**ACR Claimed** — the ACR of **every wave** whose Actual End Date "
        "falls inside the period, so one account can claim in several months; a "
        "wave that never ended never claims.",
        "**Cumulative** is the running total of the months displayed, computed "
        "from the same population as the monthly values.",
    )),
    ("Periods, regions and money", (
        "The reporting period narrows the period-bound measures only. "
        "**On-Track, ACR Pipeline, Nodes Deployment Planned, the current "
        "pipeline, the regional cut and the excluded-accounts section are "
        "snapshots** and say so under their own titles.",
        "The **regional breakdown** counts accounts at their latest wave — one "
        "row per TPID — over the stages a migration progresses through (the "
        "four in-flight ones plus Completed). It is drawn as a **single "
        "heatmap**: the stacked bar beside it carried the same numbers, and one "
        "reading of a figure is better than two.",
        "**Money is written in K and M** — $12.5K, $125K, $1.25M — in tiles, "
        "tables, chart axes and chart tooltips alike, so the same amount reads "
        "the same way wherever it appears.",
    )),
)
