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
    "Unique customers (TPIDs) approved inside the reporting period.\n"
    "• Uses the Nom. Approval Date of the TPID's first wave (lowest Phase/Wave "
    "number), WHATEVER Migration Status or Current State that wave is in — a "
    "cancelled or blocked first wave still dates the engagement.\n"
    "• Only when the first wave has no Nom. Approval Date does it move on to "
    "the next wave, and the next, until one carries a date.\n"
    "• That wave's Nomination Status must read 'Approved'.\n"
    "• Keeps the account when that date falls in the period.\n"
    "• Counts each TPID once — later waves of the same account never add to it.\n"
    "An account with no approval date on any wave, or whose dating wave was "
    "never approved, is not counted."
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
    "Every account that is neither On-Track nor Completed, grouped by WHY it "
    "has stopped:\n"
    "• The blocking CURRENT STATES, in the programme's own words — 'Blocked', "
    "'Blocked - Account team', 'Blocked - Customer', 'Blocked - Partner / "
    "ISD', 'Waiting action on follow up date'.\n"
    "• 'Deferred By Customer' and 'Cancelled / Archived', broken out by "
    "MIGRATION STATUS — those are decisions the customer has taken rather than "
    "work that is stuck, and a review reads them differently. The status wins "
    "over the Current State: an account deferred while its state still reads "
    "'Blocked - Customer' is reported as deferred.\n"
    "• 'Not approved' for a nomination whose status is not 'Approved', and "
    "'Not stated' where nothing has been recorded. Nothing is inferred.\n"
    "They are reported HERE AND NOWHERE ELSE: none of them is counted in the "
    "headline tiles, the trends, the pipeline chart or the regional cut, and "
    "none of those numbers appears in this section — so the two cuts add up to "
    "the report's accounts.\n"
    "The STATUS SUMMARY column on every row is the programme's own note on what "
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
    "The same accounts New Engagements counts — approved nominations — placed in "
    "the month of their first wave's date (approval or creation, per the Trend "
    "basis above). The wave's Migration Status and Current State do not affect "
    "which wave is read; a missing date falls through to the next wave. Each "
    "TPID appears in one month only."
)

TOP_ACCOUNTS_ACR = (
    "The ten accounts carrying the most ACR in this category, largest first.\n"
    "• One row per account (TPID), never per wave.\n"
    "• Total ACR is summed across EVERY wave the account has — an account with "
    "waves of 10M, 15M and 20M is a 45M account, and ranking it on its latest "
    "wave's 20M alone would place it wrongly.\n"
    "• Accounts with no ACR are left out rather than listed as zeroes.\n"
    "• Not narrowed by the reporting period: it answers where the money in this "
    "category is, which is a question about the whole category.\n"
    "Read it for concentration — how much of the category sits in a handful of "
    "accounts, and who they are."
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
    "• Nom. Approval Date — from the first wave whatever its Migration Status "
    "or Current State, falling through to the next wave that carries one: the "
    "same wave the New Engagements tile reads, because that is when the account "
    "was nominated.\n"
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
    "MIGRATION START and MIGRATION END take the manual EOS tracking sheet "
    "first, for every account it covers: its Migration Start Date and Actual "
    "Migration End Date are the programme stating when the work began and "
    "ended, in its own document. Only where the sheet is silent — or where no "
    "sheet is loaded — does the export answer, by the rules below.\n"
    "MIGRATION START is then derived, since the export has no such field: an "
    "account's earliest wave whose Current State reads 'On Track' or 'Done' — "
    "the first wave actually under way — and from it the Actual Start Date, "
    "falling back to Planned Start Date and then to Nom. Approval Date. An "
    "account with no such wave has not started and is not counted.\n"
    "MIGRATION END, without the sheet, is the account's latest wave completing "
    "('7 - Completed' with no wave still on track), in the month of its Actual "
    "End Date — the same measure the trends report.\n"
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
class Definition(NamedTuple):
    """One named figure, and the steps it is worked out by.

    ``title`` is the figure exactly as the reports label it, so a reader who
    has a number in front of them can find its definition by name.  ``body`` is
    a list of **short bullets, one step each** — which records qualify, which
    column is read, which date places it in a period, and what the unit is.

    Deliberately not paragraphs and deliberately not formulas: a reader checking
    a number wants the steps in the order they are applied, and a report is read
    by the people it is circulated to, not only by whoever wrote it.
    """
    title: str
    body: tuple[str, ...]


#: "Methodology & logic" as ``(heading, items)``, where an item is either a
#: paragraph of context or a :class:`Definition`.  Shared by the PDF, the HTML
#: report and the Methodology page, so one figure cannot be documented three
#: ways.
#:
#: **Bold marks something that is in the file**: a column name written exactly
#: as the spreadsheet heads it (**Nom. Approval Date**, **Current State**), or a
#: value written exactly as that column holds it (**7 - Completed**, **AVS
#: Migration Nominations**).  Everything else is description.  That convention
#: is what makes a definition checkable — a reader can open the export, find the
#: column, and see the same value the report read.
REPORT_METHODOLOGY: tuple[tuple[str, tuple], ...] = (
    ("How to read these definitions", (
        "Every figure in this report has an entry below, under the name the "
        "report gives it, set out as the steps it is worked out by.",
        "**Anything in bold is in the spreadsheet** — either a column name, "
        "written exactly as the file heads it, or a value written exactly as "
        "that column holds it. Everything else is description. So any number "
        "here can be checked by opening the export, finding the column and "
        "reading the same value the report read.",
        "**These definitions state the rule the application actually applies** "
        "— not the intended rule, not a simplification of it. Where a figure "
        "and its definition could drift apart, a test holds them together, and "
        "a rule that changes changes here in the same breath. A number you "
        "cannot reconcile against its own definition is worse than an "
        "undocumented one, because you would trust it.",
        Definition("Account", (
            "One customer, however many pieces of work it has in flight.",
            "Identified by **TPID**, which every count, match and lookup is "
            "keyed on.",
            "Never identified by **Customer Name**: the same account is spelled "
            "differently between worksheets and source systems.",
            "Unit: customer.",
        )),
        Definition("Wave", (
            "One piece of work for an account — one row of the export.",
            "Numbered in the **Phase** column: **Wave 1**, **Wave 2** and so on.",
            "The **first wave** is the lowest **Phase** number; ties are broken "
            "by the earlier **Nom. Created Date**.",
            "The **latest wave** is the highest **Phase** number.",
            "One account can have several, each with its own status, dates and "
            "**Total ACR**.",
        )),
        Definition("ACR", (
            "The annual revenue a piece of work is expected to bring in.",
            "Read from **Total ACR**, as the export records it.",
            "Written short throughout: $12.5K, $125K, $1.25M.",
            "Unit: currency.",
        )),
    )),
    ("Which wave a figure is read from", (
        "An account's waves rarely agree with each other — one may be finished "
        "while the next has not started — so each figure is read from the wave "
        "that can answer for it.",
        Definition("Read from the latest wave", (
            "Where the account stands now: **Migration Status**, **Current "
            "State**, **WW Region**, **Total Cores**, **Actual Start Date**, "
            "**Actual End Date**, **Assigned To (Factory PM)** and **Solution "
            "Architect**.",
            "Where the latest wave leaves one of those cells empty, the "
            "account's own most recent answer for that column stands in.",
        )),
        Definition("Read from the first wave", (
            "When the account joined the programme: its **Nom. Approval Date**.",
            "Read from the first wave whatever that wave's **Migration Status** "
            "or **Current State** says — a cancelled or blocked first wave "
            "still dates the engagement.",
            "Only when the first wave has no **Nom. Approval Date** at all does "
            "the rule move on to the next wave, and the one after that, until a "
            "wave carries one.",
        )),
        Definition("Read across every wave", (
            "An account's **Total ACR** is every one of its waves added "
            "together.",
            "Waves worth 10M, 15M and 20M make a 45M account; the latest wave "
            "alone would understate it by more than half.",
            "Every account-level figure counts an account once, however many "
            "waves it has.",
        )),
    )),
    ("The headline figures", (
        Definition("New Engagements", (
            "Use the **Nom. Approval Date** of the account's first wave.",
            "If that wave has no **Nom. Approval Date**, use the next wave that "
            "carries one.",
            "That wave's **Migration Status** and **Current State** do not "
            "matter — a cancelled or blocked first wave still dates the "
            "engagement.",
            "That wave's **Nomination Status** must be **Approved**.",
            "Count unique **TPID**s whose date falls in the reporting period.",
            "Count each qualifying **TPID** once; later waves never add to it.",
            "An account with no **Nom. Approval Date** on any wave is not "
            "counted.",
            "It is the one figure that still counts accounts which have since "
            "stopped.",
            "Unit: customer.",
        )),
        Definition("Migrations Completed", (
            "For each **TPID**, identify the latest **Phase** / wave record.",
            "That wave's **Migration Status** must be **7 - Completed**.",
            "No other wave of the account may still be on track — if an earlier "
            "wave is running, the account is still being delivered and is "
            "counted under On-Track Accounts instead.",
            "Use that wave's **Actual End Date** to decide the reporting period.",
            "Count each qualifying **TPID** once.",
            "Unit: customer.",
        )),
        Definition("Hosts Migrated (Cores Migrated on AVS to Azure Native)", (
            "Identify every wave whose **Migration Status** is **7 - "
            "Completed**.",
            "Use that wave's **Actual End Date** to decide the reporting period.",
            "Add up **Total Cores** over those waves.",
            "It counts the work, not the customers: an account with three "
            "completed waves contributes all three.",
            "Each row is counted once, by its **Task ID**, so a duplicated row "
            "cannot inflate it.",
            "The AVS motions call it **Hosts Migrated**; AVS to Azure Native "
            "calls it **Cores Migrated**. Same column, different noun.",
            "Unit: nodes (cores).",
        )),
        Definition("On-Track Accounts", (
            "A wave is on track when all three of these hold.",
            "Its **Nomination Status** is **Approved**.",
            "Its **Migration Status** is one of **1 - Validating Commitment & "
            "Initial Scope**, **2 - Executing Pre-Requisites**, **3 - Finalize "
            "Scope** or **4 - Executing Migration**.",
            "Its **Current State** is **On Track** and nothing else.",
            "Count unique **TPID**s with at least one such wave, whatever their "
            "latest wave says.",
            "A snapshot of where things stand now: no reporting period narrows "
            "it.",
            "Unit: customer.",
        )),
        Definition("ACR Claimed", (
            "Identify every wave whose **Actual End Date** falls in the "
            "reporting period, whatever state the account is in now.",
            "Add up **Total ACR** over those waves.",
            "Claiming is per wave, not per account: waves 2 and 3 of one "
            "account and wave 5 of another all count if all three ended in the "
            "window.",
            "A wave that ended outside the window contributes nothing, even "
            "when a sibling wave of the same account ended inside it.",
            "A wave with no **Actual End Date** has not claimed and never "
            "counts.",
            "Unit: currency.",
        )),
        Definition("ACR Pipeline", (
            "A wave qualifies when all four of these hold.",
            "It belongs to this report's motion: **Factory Offering** is **AVS "
            "Migration Nominations** for the AVS and EOS reports, or **Primary "
            "Migration Path** contains **From AVS** for the AVS to Azure Native "
            "report.",
            "Its **Nomination Status** is **Approved**.",
            "Its **Current State** is **On Track** and nothing else.",
            "Its **Migration Status** is neither **5 - Deferred By Customer** "
            "nor **6 - Cancelled / Archived**.",
            "Add up **Total ACR** over those waves.",
            "Finished work needs no exclusion of its own: a finished wave reads "
            "**Done** rather than **On Track**, so the third condition leaves "
            "it out.",
            "Read over the whole dataset — the reporting period does not narrow "
            "it, though every other filter applies.",
            "Unit: currency.",
        )),
        Definition("Nodes Deployment Planned (EOS reports only)", (
            "Use exactly the same four qualifying conditions as ACR Pipeline.",
            "Add up **Total Cores** over those waves instead of **Total ACR**.",
            "Read over the whole dataset, not the reporting period.",
            "Unit: nodes.",
        )),
        Definition("Cumulative", (
            "The last column of every monthly table.",
            "The running total of the months shown, added up as you read down.",
            "It does not reach back before the first month on display.",
        )),
    )),
    ("How an account's state is decided", (
        "Every account is given exactly one state, which is what lets the "
        "charts and the stopped-accounts section add up to the report's own "
        "account count.",
        Definition("The order the state is decided in", (
            "The first of these to fit is the state the account gets.",
            "**On-Track** — any wave of the account is on track by the "
            "three-part test above.",
            "**Completed** — the latest wave's **Migration Status** is **7 - "
            "Completed** and no wave of the account is on track.",
            "**Cancelled** — the latest wave's **Migration Status** is **6 - "
            "Cancelled / Archived**.",
            "**Blocked** — the latest wave's **Current State** mentions being "
            "blocked.",
            "**Deferred** — the latest wave's **Migration Status** is **5 - "
            "Deferred By Customer**.",
            "**Other** — anything left.",
            "On-Track is tested before Completed on purpose: an account whose "
            "latest wave has finished while an earlier wave is still running is "
            "still being delivered.",
        )),
        Definition("What is not on track", (
            "A wave nobody has approved is not on track, however far along it "
            "looks.",
            "A wave with a blank **Current State** is not on track either — "
            "that column is how the programme says an engagement is moving.",
            "There is no fallback for either; both land in **Other**.",
            "A finished, deferred or cancelled wave is not on track whatever "
            "its **Current State** still reads, because its **Migration "
            "Status** is no longer one of the four in-flight stages.",
        )),
        Definition("Blocked, deferred and cancelled accounts", (
            "Include every account that is neither On-Track nor Completed — "
            "that is the whole test.",
            "Label each one with why it stopped; the first reason that fits is "
            "the one shown.",
            "**Migration Status** of **6 - Cancelled / Archived** — cancelled.",
            "**Migration Status** of **5 - Deferred By Customer** — deferred. "
            "The **Migration Status** wins over the **Current State**, because "
            "somebody decided those.",
            "Otherwise the **Current State** in its own words: **Blocked**, "
            "**Blocked - Account team**, **Blocked - Customer**, **Blocked - "
            "Partner / ISD** or **Waiting action on follow up date**.",
            "Otherwise, a **Nomination Status** that is not **Approved** — not "
            "approved.",
            "Otherwise, nothing recorded — labelled as such rather than guessed "
            "at.",
            "None of these accounts is in any other figure. New Engagements is "
            "the one deliberate exception.",
            "Every row carries the account's **Status Summary**, the "
            "programme's own note on what it is waiting for.",
        )),
        Definition("Where every account sits", (
            "A table under the pipeline lists every state, its account count, "
            "its **Total ACR** and where those accounts are reported.",
            "Two states are charted — On-Track and Completed.",
            "Every other state is in the stopped-accounts section.",
            "Each account is in exactly one state, so the rows add up to the "
            "report's own account count.",
        )),
    )),
    ("Which report an account appears in", (
        "Each report covers one migration motion, decided per nomination from "
        "what it is moving and where it is moving to.",
        Definition("All AVS Migrations", (
            "Include every nomination whose target platform is AVS.",
            "Read from **Primary Migration Path**, **Factory Offering** and "
            "**Linked Offering Name**.",
            "On-premises, VMG, AWS/VMC, AVS-to-AVS and EOS refreshes all land "
            "here.",
            "Every EOS account is included too, whatever its own path reads.",
        )),
        Definition("AVS to Azure Native", (
            "Include nominations whose **Primary Migration Path** contains "
            "**From AVS**, such as **SQL Server MI Migration (From AVS)**.",
            "Reported here and nowhere else: this motion is leaving AVS, so "
            "counting it under All AVS Migrations or EOS would file it in the "
            "wrong story.",
            "Not even a Gen-1 or Gen-2 tag pulls one into another report.",
            "The Azure-native service each one lands on is read from the same "
            "**Primary Migration Path** — SQL MI, SQL Database, SQL on IaaS, "
            "PostgreSQL/MySQL, Windows or Linux virtual machines, Oracle "
            "Database@Azure or AKS.",
        )),
        Definition("EOS Migration", (
            "Include accounts refreshing ageing AVS hardware, reported by the "
            "generation they are moving on to.",
            "An account is in scope when its generation is known, or when any "
            "wave's **Primary Migration Path**, **Factory Offering** or "
            "**Linked Offering Name** reads **AV36/AV36P/AV52 - EOS**.",
            "One qualifying wave brings the whole account in.",
            "Reported as Gen-1 and Gen-2, with a combined view and a page each.",
        )),
        Definition("The generation (Gen-1 or Gen-2)", (
            "Decided per account across all of its waves, by the first of these "
            "that answers.",
            "The EOS tracking sheet's **Target SDDC Generation** reading "
            "**Gen1** or **Gen2**.",
            "Otherwise a **Tags** value containing **AVS Migration - Gen1** or "
            "**AVS Migration - Gen2** on any one wave; tags arrive run "
            "together, so the marker is matched inside the cell whatever sits "
            "either side of it.",
            "If both tags appear on different waves, Gen-1 wins.",
            "Otherwise the account has no generation.",
        )),
        Definition("EOS accounts with no generation", (
            "An account in EOS scope with no **Target SDDC Generation** and no "
            "Gen-1 or Gen-2 **Tags** value is left out of every EOS figure.",
            "EOS is reported by generation, and counting an ungenerationed "
            "account in the combined total would make it disagree with the sum "
            "of its own two blocks.",
            "It is not discarded: it stays inside All AVS Migrations.",
            "It is listed on the Data Inconsistency review, and adding the tag "
            "at source brings it straight into the EOS reports.",
        )),
    )),
    ("The manual EOS tracking sheet", (
        "The EOS programme keeps its own spreadsheet beside the nominations "
        "export, and it is uploaded separately. Where it is loaded, it leads on "
        "three things; everything else still comes from the export.",
        Definition("How it is matched", (
            "Matched on **TPID**, and on nothing else.",
            "**Assigned To (Factory PM)**, **Solution Architect**, **WW "
            "Region**, **Factory Offering**, **Total ACR** and the waves are "
            "all looked up in the nominations export by that **TPID**.",
            "So the sheet never has to repeat or contradict them.",
            "A **TPID** the export has never heard of has no nomination behind "
            "it and appears in no report — it is named on the Data "
            "Inconsistency review instead of being invented.",
        )),
        Definition("What it decides", (
            "**Target SDDC Generation** decides the account's generation.",
            "**Migration Start Date** and **Actual Migration End Date** supply "
            "the two date rows of the monthly programme matrix.",
            "**Total SDDCs in Scope for Migration** and **Number of SDDCs "
            "Migrated** are read and shown, but feed no headline figure.",
            "Where the sheet is silent, the export answers exactly as it did "
            "before there was a sheet.",
            "A report built with no sheet loaded is unchanged.",
        )),
    )),
    ("The EOS monthly programme matrix", (
        "A month-by-month grid in two blocks, **Gen1 to Gen1** and **Gen1 to "
        "Gen2**. Every EOS account is refreshing away from ageing Gen-1 "
        "hardware, so the constant half of each heading is where it is coming "
        "from, and the account's own generation names where it is landing.",
        "The grid ignores the reporting period the rest of the report uses. It "
        "runs from July 2025 to the current month — further if a completion is "
        "dated ahead of it — and shows every month in between, because a month "
        "with nothing in it is itself the number being reported. Each fiscal "
        "year closes with its own total column.",
        Definition("Total number of new engagement (monthly)", (
            "Use the same **Nom. Approval Date** rule as New Engagements.",
            "Count the unique **TPID** in that date's month, once only.",
            "Unit: customer.",
        )),
        Definition("Total number of migration start (monthly)", (
            "Use the tracking sheet's **Migration Start Date** wherever it has "
            "one.",
            "Otherwise, for each **TPID**, identify the earliest **Phase** / "
            "wave whose **Current State** reads **On Track** or **Done** — the "
            "first wave actually under way.",
            "Use that wave's **Actual Start Date**; if it is blank, its "
            "**Planned Start Date**; if that is blank too, its **Nom. Approval "
            "Date**.",
            "An account with no such wave has not started and is not counted.",
            "Count the unique **TPID** in that date's month, once only.",
            "Unit: customer.",
        )),
        Definition("Total number of migration end (monthly)", (
            "Use the tracking sheet's **Actual Migration End Date** wherever it "
            "has one.",
            "Otherwise, for each **TPID**, identify the latest **Phase** / wave "
            "record.",
            "That wave's **Migration Status** must be **7 - Completed**, and no "
            "other wave of the account may still be on track.",
            "Use that wave's **Actual End Date**.",
            "Count the unique **TPID** in that date's month, once only.",
            "Unit: customer.",
        )),
        Definition("Total number of engagement end (monthly)", (
            "Use exactly the same test and the same date as migration end.",
            "The export marks when a wave ended but has no separate closure "
            "date for the engagement itself.",
            "So the two rows carry identical values by construction, not by "
            "coincidence.",
            "Unit: customer.",
        )),
        Definition("Number of hosts migrated (monthly)", (
            "Identify every wave whose **Migration Status** is **7 - "
            "Completed**.",
            "Use its **Actual End Date** to decide the month.",
            "Add up **Total Cores** over those waves.",
            "Unit: nodes.",
        )),
    )),
    ("Dates and durations the app works out", (
        "These are derived from the export's own dates rather than read from a "
        "column of their own. They drive the insights and the delivery-health "
        "wording; none of them changes a headline figure.",
        Definition("Approved, closed, open", (
            "**Approved** — there is a **Nom. Approval Date**, or the "
            "**Nomination Status** contains approved.",
            "**Closed** — the **Migration Status** reads **7 - Completed**, or "
            "the **Current State** says done or complete, or the **Milestone "
            "Status** says complete, or there is an **Actual End Date**.",
            "**Open** — neither closed nor cancelled.",
        )),
        Definition("Aging (days)", (
            "Count from **Nom. Created Date** to the day the work closed.",
            "For work still open, count to the reporting as-of date instead.",
            "A negative result means the dates contradict each other, so it is "
            "dropped rather than reported.",
            "Unit: days.",
        )),
        Definition("Cycle time (days)", (
            "Count from **Nom. Created Date** to **Actual End Date**.",
            "Closed work only — unfinished work is left out rather than counted "
            "as fast.",
            "Unit: days.",
        )),
        Definition("Approval latency (days)", (
            "Count from **Nom. Created Date** to **Nom. Approval Date**.",
            "The insights report the median across the selection, and the "
            "region with the slowest median.",
            "Unit: days.",
        )),
        Definition("Closure rate", (
            "Divide the closed items by all items in the current selection.",
            "Unit: percentage.",
        )),
        Definition("Delivery health, and Risk", (
            "Each wave is given a health status, the first matching rule "
            "winning.",
            "**Completed**, then **Cancelled**, then **Blocked**.",
            "Then **At Risk** when the work is deferred.",
            "Then **Delayed** when the **Planned End Date** has passed and "
            "there is no **Actual End Date**.",
            "Then **At Risk** again when the **Next Follow-up Date** has passed "
            "or the wave is waiting.",
            "Otherwise **On Track**.",
            "**Risk** on the insights means any wave in **At Risk**, "
            "**Delayed** or **Blocked** — a direct count of those three, with "
            "no scoring model behind it.",
            "This is a different thing from the account states above, which the "
            "pipeline charts use.",
        )),
    )),
    ("Trends, periods and the fiscal year", (
        Definition("The monthly trends", (
            "Nominations per month — each account in the month of the **Nom. "
            "Approval Date** New Engagements reads, or its **Nom. Created "
            "Date** if you switch the basis.",
            "ACR claimed per month — ACR Claimed split by the **Actual End "
            "Date** of each claiming wave.",
            "Hosts and migrations completed per month — the same, for their own "
            "figures.",
            "Each account appears in one month only on the account-level "
            "measures, so the months add back up to the tile above them.",
        )),
        Definition("Fiscal years side by side", (
            "The same four measures, each fiscal year drawn as its own line "
            "over a shared July-to-June axis.",
            "All twelve months are always listed, including the empty ones.",
            "Read over the whole dataset whatever period the rest of the report "
            "is cut to: a year-on-year comparison narrowed to one month would "
            "have nothing to compare.",
            "No cumulative column here — a running total across unrelated "
            "fiscal years would not mean anything.",
        )),
        Definition("Top 10 accounts by ACR", (
            "Add up **Total ACR** across every wave of each account.",
            "Leave out accounts with no ACR rather than listing them as zeroes.",
            "Take the ten largest, biggest first.",
            "Label each bar with the **Customer Name** and its **TPID**, so no "
            "two bars can be the same account.",
            "Shown on the All AVS Migrations and AVS to Azure Native reports.",
            "Read over the whole dataset, not the reporting period.",
            "Unit: currency.",
        )),
        Definition("The reporting period, and the This FY row", (
            "The period narrows New Engagements, Migrations Completed, Hosts "
            "Migrated, ACR Claimed and the monthly trends.",
            "It does not narrow On-Track Accounts, the current pipeline, the "
            "regional cut, the stopped accounts, ACR Pipeline, Nodes Deployment "
            "Planned, the programme matrix or the fiscal-year comparison.",
            "Each of those says so under its own title.",
            "Selecting any period other than the current fiscal year adds a "
            "**This FY** row of tiles above the selected one, so a month's "
            "numbers keep the year they sit in.",
            "The two rows are worked out independently, each from its own "
            "window.",
            "All time gets that row too, because it spans several fiscal years "
            "and so loses the one you are in.",
        )),
    )),
    ("Region, money and the reporting floor", (
        Definition("WW Region", (
            "Every regional grouping, filter and chart reads the **WW Region** "
            "column and is labelled with that name.",
            "The value the business reports on, such as **Americas - "
            "Enterprise**, **Americas SME&C** or **MS Elevate** — nothing "
            "reduces it to a geography.",
            "A leading number on the value is stripped and flagged on the Data "
            "Inconsistency review.",
            "**Customer Segment** is a separate column, reported separately.",
            "The regional breakdown counts accounts once each, at their latest "
            "wave, over the four in-flight stages plus **7 - Completed** — "
            "deferred and cancelled work is not a stage a migration progresses "
            "through, so these counts are lower than the report's total "
            "accounts.",
        )),
        Definition("Money", (
            "Written short — $12.5K, $125K, $1.25M.",
            "The same in tiles, tables, chart axes and chart tooltips, so one "
            "amount reads the same way wherever it appears.",
        )),
        Definition("The reporting floor", (
            "Waves nominated before FY25 are dropped as the file is read, "
            "before anything is counted.",
            "A wave belongs to the fiscal year of its **Nom. Approval Date**, "
            "or its **Nom. Created Date** when it was never approved.",
            "A wave carrying neither cannot be shown to be out of scope, so it "
            "stays.",
            "This is why All time means FY25 onwards in every chart, table, "
            "total and export.",
        )),
    )),
)
