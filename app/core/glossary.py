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

MIGRATION_ENDS = (
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

NOMINATIONS_APPROVED = (
    "Nomination records (wave rows) whose Nom. Approval Date falls inside the "
    "reporting period. Unlike the customer metrics this counts nominations, so an "
    "account with three approved waves contributes three."
)

ON_TRACK_ACCOUNTS = (
    "Customers (TPIDs) whose latest wave is neither completed nor cancelled — the "
    "live pipeline for this category."
)

TOTAL_ACR = (
    "Total ACR of the category: the Total ACR column summed across every wave in "
    "the current population. Shown as $1.2M / $840.0K."
)

# --------------------------------------------------------------------------- #
# Sections
# --------------------------------------------------------------------------- #
EXECUTIVE_SUMMARY = (
    "Headline numbers for this migration category over the selected reporting "
    "period. Every tile has its own ⓘ, and 'Records behind these tiles' opens the "
    "exact rows each number came from."
)

TRENDS = (
    "Month-by-month movement for this category. Each table's final column is "
    "Cumulative — the running total of the months shown, never a different "
    "population. Click a bar or a table row to open that month's records."
)

TREND_NOMINATIONS = (
    "Unique customers (TPIDs) per month, placed in the month of their Wave-1 date "
    "(approval or creation, per the Trend basis above). Each TPID appears in one "
    "month only."
)

TREND_ACR = (
    "ACR per month. Each TPID's Total ACR is summed across all of its waves and "
    "attributed to the single month of its Wave-1 date, so no account is counted "
    "twice."
)

TREND_HOSTS = (
    "Total Cores completed per month, by Actual End Date, over wave records whose "
    "Migration Status is '7 - Completed'. Record-level, not a customer count."
)

TREND_ENDS = (
    "Completed migrations per month: unique TPIDs whose latest wave is "
    "'7 - Completed', placed in the month of that wave's Actual End Date."
)

PIPELINE = (
    "Where the category stands right now, taken from each customer's latest wave "
    "— independent of the reporting period above."
)

BY_STATE = (
    "Customers by current state, from each TPID's latest wave:\n"
    "• Closed — that wave is '7 - Completed'.\n"
    "• Cancelled — the wave resolved to a cancelled status.\n"
    "• On-Track — anything still in flight.\n"
    "ACR is the account's Total ACR summed across its waves."
)

BY_STAGE = (
    "On-track customers grouped by the stage of their latest wave (the Migration "
    "Status label, e.g. 'Executing Pre-Requisites', 'Migration In Progress'), with "
    "the account count and ACR for each stage."
)

DETAILED_DATA = (
    "Every record behind this dashboard. 'Accounts' shows one row per TPID (its "
    "latest wave); 'Nomination waves' shows the underlying source rows. Group it "
    "to read subtotals, then export to CSV."
)

REPORTING_PERIOD = (
    "The window every metric on this page is measured over. 'Global range' follows "
    "the sidebar setting; any other choice overrides it for this page only. "
    "Windows are anchored on the reporting as-of date in the sidebar, which "
    "defaults to today — so This FY is the fiscal year you are currently in, "
    "covering the whole year (1 Jul → 30 Jun) rather than year-to-date."
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
    "'AV36/AV36P/AV52 - EOS'). In scope, but with no generation to report — never "
    "folded into Gen-1 or Gen-2."
)

CATEGORY_HELP = {
    segments.CAT_EOS_ALL: (
        "Every EOS Migration account in one view — Gen-1, Gen-2 and any account in "
        "scope through its migration path with no generation tag. The generation "
        "pages are subsets of this one.\n\n" + EOS_POPULATION
    ),
    segments.CAT_EOS_GEN1: f"{EOS_POPULATION}\n\n{GENERATION_RULE}",
    segments.CAT_EOS_GEN2: f"{EOS_POPULATION}\n\n{GENERATION_RULE}",
    segments.CAT_EOS_UNCLASSIFIED: f"{EOS_UNTAGGED}\n\n{GENERATION_RULE}",
    segments.CAT_ALL_AVS: (
        "Every nomination whose TARGET platform is AVS, whatever it migrates from "
        "— on-premises, VMG, AWS/VMC, AVS-to-AVS and EOS refreshes. Derived from "
        "the Primary Migration Path and Factory Offering; paths reading "
        "'(From AVS)' are excluded, since those leave AVS."
    ),
    segments.CAT_AVS_NATIVE: (
        "Nominations migrating AWAY from AVS to Azure-native services — the "
        "offerings whose Primary Migration Path contains '(From AVS)', e.g. "
        "'SQL Server MI Migration (From AVS)'."
    ),
}
