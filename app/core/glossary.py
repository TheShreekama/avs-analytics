"""Plain-language explanations shown behind every ⓘ marker.

One place for "what exactly does this number mean", written against the columns
of the nominations export, so the tooltip on a dashboard, the Methodology page
and the code all say the same thing.
"""
from __future__ import annotations

from typing import NamedTuple

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
    "Customers (TPIDs) with ANY wave genuinely in flight. A WAVE is on track "
    "when ALL THREE hold:\n"
    "1. Nomination Status = 'Approved'. An unapproved nomination is not on "
    "track however it is progressing — nothing has been committed to yet.\n"
    "2. Migration Status IN ('1 - Validating Commitment & Initial Scope', "
    "'2 - Executing Pre-Requisites', '3 - Finalize Scope', '4 - Executing "
    "Migration'). A wave that is '5 - Deferred by Customer', '6 - Cancelled / "
    "Archived' or '7 - Completed' is never on track, whatever its Current "
    "State says.\n"
    "3. Current State = 'On Track' — and nothing else. 'Blocked - Customer', "
    "'Blocked - Account team' and 'Waiting action on follow up date' are not "
    "on track, whatever the status says.\n"
    "A BLANK Current State is NOT on track. The column is how the programme "
    "says an engagement is moving; a wave nobody has said that about is "
    "ignored rather than counted.\n"
    "The account counts when ANY of its waves is on track — work still running "
    "on an earlier wave is work still running — and the record behind it is "
    "the latest of those on-track waves.\n"
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
    "The ACR carried by every ELIGIBLE WAVE — the approved, on-track work, and "
    "therefore the commercial value still to land.\n"
    "A wave is eligible when ALL FOUR hold, judged on the wave itself:\n"
    "1. Factory Offering = 'AVS Migration Nominations' (the AVS and EOS "
    "reports), or Primary Migration Path CONTAINS 'From AVS' (the AVS → Azure "
    "Native report). They are different columns, and each motion is scoped by "
    "the one that defines it.\n"
    "2. Nomination Status = 'Approved'.\n"
    "3. Current State = 'On Track' — and nothing else.\n"
    "4. Migration Status NOT IN ('5 - Deferred By Customer', '6 - Cancelled / "
    "Archived').\n"
    "Any single failure drops the wave.\n"
    "It is read over the WHOLE DATASET, never the reporting period: work "
    "nominated before the window is still work still to do. Every other filter "
    "still binds — a report cut to one region reports that region's pipeline.\n"
    "Distinct from ACR Claimed, which is value already realised by waves that "
    "ended inside the period."
)

NODES_PLANNED = (
    "The deployment still to come: SUM(Total Cores) over the SAME eligible "
    "waves the ACR Pipeline is built from — Factory Offering = 'AVS Migration "
    "Nominations' (or a '(From AVS)' path), Nomination Status = 'Approved', "
    "Current State = 'On Track', and Migration Status not '5 - Deferred By "
    "Customer' or '6 - Cancelled / Archived'.\n"
    "Reported as NODES because that is what the AVS motions deploy, from the "
    "Total Cores column that records them. Read against Hosts Migrated, which "
    "is the deployment already delivered.\n"
    "Like ACR Pipeline it is read over the WHOLE DATASET, never the reporting "
    "period.\n"
    "Shown on the EOS reports only — that programme is the one that plans a "
    "node refresh."
)

BLOCKED_ACCOUNTS = (
    "Accounts that have stopped: their latest wave's CURRENT STATE reads "
    "Blocked, Blocked - Account team, Blocked - Customer, Blocked - Partner / "
    "ISD, or Waiting action on follow up date.\n"
    "They are reported HERE AND NOWHERE ELSE. None of them is counted in the "
    "headline tiles, the trends, the pipeline chart or the regional cut, and "
    "none of those numbers appears in this section.\n"
    "CANCELLED AND DEFERRED ACCOUNTS ARE NOT HERE. They are out of the "
    "reported pipeline too, but a cancelled or deferred engagement is a "
    "decision someone has already taken, not work that has stopped — and this "
    "section is the one a review can act on. A wave cancelled while its "
    "Current State still reads 'Blocked' is reported as the cancellation it "
    "is.\n"
    "The Current State is the breakdown, because the state IS the reason; the "
    "STATUS SUMMARY column on every row is the programme's own note on what "
    "the account is waiting for."
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
    "Customers by state, read across ALL of an account's waves. Only two "
    "states are reported:\n"
    "• On-Track — ANY wave has Nomination Status = 'Approved', is in flight "
    "(Migration Status 1-4) AND its Current State = 'On Track' (an unapproved "
    "nomination or a blank state is not on track).\n"
    "• Completed — the LATEST wave's Migration Status is '7 - Completed' AND "
    "no wave of the account is on track.\n"
    "Cancelled, deferred, blocked and waiting accounts are deliberately left "
    "out, so the chart shows live and finished work only — the slices will not "
    "add up to every account in the category. The blocked and waiting ones are "
    "reported in their own section.\n"
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
    "Three separate columns, charted separately because they answer different "
    "questions:\n"
    "• FACTORY OFFERING — which factory delivers the work: 'SQL Migration "
    "Nominations', 'Windows Migration Nominations', 'AVS Migration "
    "Nominations'.\n"
    "• PRIMARY MIGRATION PATH — what moves where: 'SQL Server MI Migration "
    "(From AVS)', 'Onprem to AVS'. A path containing '(From AVS)' is what puts "
    "a wave in this motion.\n"
    "• AZURE-NATIVE TARGET — the service the path lands on, read from the path.\n"
    "Wave-level counts over every nomination in the category, not narrowed by "
    "the reporting period."
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
class Rule(NamedTuple):
    """One rule, written as the rule rather than described in a sentence.

    ``lines`` are rendered in a monospaced block, aligned as written, so a
    reader checks a number against the columns and values it was actually read
    from — not against a paragraph they have to translate back into logic.
    """
    title: str
    lines: tuple[str, ...]


#: "Methodology & logic" as (heading, items), where an item is either a
#: paragraph of context or a :class:`Rule`.  Shared by the PDF, the HTML report
#: and the Methodology page, so one rule cannot be documented three ways.
#:
#: Every rule below is one a function in ``app/core`` actually applies, named so
#: a reader can go and check it.  Column names and values are written exactly as
#: the export writes them.
REPORT_METHODOLOGY: tuple[tuple[str, tuple], ...] = (
    ("Accounts, waves and the latest wave", (
        "An **account is a TPID**, and a TPID can hold several waves. Account "
        "names are never used for matching — the same account is spelled "
        "differently between source systems.",
        Rule("Which wave answers for what", (
            "latest wave   = the account's highest wave number",
            "                (ties broken by Nom. Created Date)",
            "Wave-1        = its lowest wave number",
            "",
            "current status, region, stage, dates, owners  ← latest wave",
            "Nom. Approval Date (New Engagements)          ← Wave-1",
            "Total ACR (account level)                     ← SUM over ALL waves",
        )),
        "Every unique-TPID metric counts an account **once**, however many "
        "waves it has, so no multi-wave account is ever double-counted.",
    )),
    ("Account state — On-Track vs. Completed", (
        Rule("A WAVE is On Track when ALL THREE hold", (
            'Nomination Status  =   "Approved"',
            'Migration Status   IN  ("1 - Validating Commitment & Initial Scope",',
            '                        "2 - Executing Pre-Requisites",',
            '                        "3 - Finalize Scope",',
            '                        "4 - Executing Migration")',
            'Current State      =   "On Track"         -- and nothing else',
        )),
        "An **unapproved nomination is not On Track** however it is "
        "progressing — nothing has been committed to yet — and a **blank "
        "Current State is not On Track** either: the column is how the "
        "programme says an engagement is moving, so a wave nobody has said "
        "that about is ignored rather than counted. Both land in *Other*.",
        Rule("The ACCOUNT's state, first match wins", (
            "On-Track   ← ANY wave of the account is On Track (above)",
            'Completed  ← latest wave Migration Status = "7 - Completed"',
            "             AND no wave of the account is On Track",
            'Cancelled  ← latest wave Migration Status = "6 - Cancelled / Archived"',
            'Blocked    ← latest wave Current State CONTAINS "Blocked"',
            'Deferred   ← latest wave Migration Status = "5 - Deferred By Customer"',
            "Other      ← everything else",
        )),
        "So an account whose **latest wave has completed while another wave is "
        "still On Track is On-Track**, not Completed — it is still delivering. "
        "Every account resolves to exactly one state, so the reported cut "
        "(On-Track, Completed) and everything else partition the population: "
        "nothing is counted twice and nothing is lost.",
    )),
    ("Blocked & waiting accounts", (
        Rule("Include an ACCOUNT when BOTH hold", (
            "account state        IN  (Blocked, Other)",
            "latest wave",
            '  Current State      IN  ("Blocked",',
            '                          "Blocked - Account team",',
            '                          "Blocked - Customer",',
            '                          "Blocked - Partner / ISD",',
            '                          "Waiting action on follow up date")',
        )),
        "**Cancelled and deferred accounts are not in it.** They are outside "
        "the reported pipeline as well, but a cancelled or deferred engagement "
        "is a decision already taken rather than work that has stopped — so a "
        "wave cancelled while its Current State still reads *Blocked* is "
        "reported as the cancellation it is.",
        "The section is reported **apart from every metric above** and nowhere "
        "else: not in the headline tiles, the trends, the state chart or the "
        "regional cut. The Current State is the breakdown, because the state "
        "*is* the reason, and every row carries the export's **Status "
        "Summary** — the programme's own note on what the account is waiting "
        "for.",
        "**New Engagements is the one deliberate exception** to that "
        "separation: an account approved inside the period is counted there "
        "whatever became of it afterwards, because intake is a historical fact "
        "and a figure that moved when an account got blocked would be "
        "reporting something else.",
    )),
    ("ACR Pipeline and Nodes Deployment Planned", (
        Rule("A WAVE is eligible when ALL FOUR hold", (
            '1. Factory Offering        =        "AVS Migration Nominations"  '
            '   -- AVS + EOS reports',
            '   Primary Migration Path  CONTAINS "From AVS"                   '
            '   -- AVS → Azure Native report',
            '2. Nomination Status       =        "Approved"',
            '3. Current State           =        "On Track"                   '
            '   -- and nothing else',
            '4. Migration Status        NOT IN   ("5 - Deferred By Customer",',
            '                                     "6 - Cancelled / Archived")',
        )),
        Rule("What is then summed over those waves", (
            "ACR Pipeline             = SUM(Total ACR)",
            "Nodes Deployment Planned = SUM(Total Cores)   -- EOS reports only",
        )),
        "Judged **per wave**, on the wave's own columns; any one failure drops "
        "it. **Factory Offering and Primary Migration Path are different "
        "columns** — the offering says which factory delivers the work, the "
        "path says what moves where — and each motion is scoped by the one "
        "that defines it.",
        "**Both are read over the whole dataset, never the reporting period.** "
        "Work nominated before the window is still work still to do, so a "
        "narrower period cannot shrink the pipeline. Every *other* filter still "
        "binds: a report cut to one region reports that region's pipeline, not "
        "the portfolio's. ACR Pipeline is therefore disjoint from **ACR "
        "Claimed**, which is value already realised by waves that have ended "
        "inside the period.",
    )),
    ("EOS reporting — Gen-1 and Gen-2 only", (
        Rule("An account's EOS scope and generation", (
            'IF   ANY wave Tags CONTAINS "AVS Migration - Gen1"  → Gen-1',
            'ELIF ANY wave Tags CONTAINS "AVS Migration - Gen2"  → Gen-2',
            'ELIF ANY wave Primary Migration Path / Factory Offering /',
            '     Linked Offering matches "AV36 / AV36P / AV52 - EOS"',
            "                                                    → EOS scope,",
            "                                                      NO generation",
            "ELSE                                                → not EOS",
            "",
            "EOS report population = accounts with generation IN (Gen-1, Gen-2)",
        )),
        "Gen-1 wins when a single account carries both tags. Tags arrive "
        "concatenated (*\"Qualify and AccelerateAVS Migration - Gen1\"*), so "
        "the marker is matched inside the cell whatever the spacing or dashes.",
        "**An account in EOS scope with no generation tag is excluded from "
        "every EOS total, chart, calculation and insight** — EOS is reported by "
        "generation, and an ungenerationed account would make the combined "
        "figure disagree with the sum of its two blocks. It is not discarded: "
        "it stays in **All AVS Migrations** and is listed under **Data "
        "Inconsistency**, and tagging it at source brings it straight in.",
    )),
    ("The other measures", (
        Rule("Counted per account (unique TPIDs)", (
            "New Engagements      = COUNT(DISTINCT TPID)",
            "                       WHERE Wave-1 Nom. Approval Date IN period",
            "Migrations Completed = COUNT(DISTINCT TPID)",
            "                       WHERE account state = Completed",
            "                       AND latest wave Actual End Date IN period",
            "On-Track Accounts    = COUNT(DISTINCT TPID)",
            "                       WHERE account state = On-Track   -- no period",
        )),
        Rule("Counted per wave (never a TPID count)", (
            'Hosts / Cores Migrated = SUM(Total Cores)',
            '                         WHERE Migration Status = "7 - Completed"',
            "                         AND Actual End Date IN period",
            "ACR Claimed            = SUM(Total ACR)",
            "                         WHERE Actual End Date IN period",
        )),
        "Hosts / Cores Migrated is deliberately wave-level: a completed wave "
        "deployed its nodes whatever the account's overall state is now. ACR "
        "Claimed is wave-level for the same reason — one account can claim in "
        "several months, and a wave that never ended never claims.",
        "**Cumulative** is the running total of the months displayed, computed "
        "from the same population as the monthly values.",
    )),
    ("Periods, regions and money", (
        "The reporting period narrows the period-bound measures only. "
        "**On-Track Accounts, the current pipeline, the regional cut and the "
        "blocked-accounts section are snapshots** of where things stand now, "
        "and **ACR Pipeline and Nodes Deployment Planned are read over the "
        "whole dataset**. All of them say so under their own titles.",
        "Selecting any period other than the current fiscal year adds a **This "
        "FY row above it**, each row measured over its own window — including "
        "over *All time*, which spans several fiscal years and so loses the one "
        "you are in.",
        "The **regional breakdown** counts accounts at their latest wave — one "
        "row per TPID — over the stages a migration progresses through (the "
        "four in-flight ones plus Completed). It is drawn as a **single "
        "heatmap**: the stacked bar beside it carried the same numbers.",
        "**Money is written in K and M** — $12.5K, $125K, $1.25M — in tiles, "
        "tables, chart axes and chart tooltips alike, so the same amount reads "
        "the same way wherever it appears.",
    )),
)
