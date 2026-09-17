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
    "Unique customers (TPIDs) nominated inside the reporting period.\n"
    "• Reads the Nom. Approval Date of the TPID's Wave-1 row (lowest Phase/Wave "
    "number), WHATEVER state or status that wave is in — a cancelled, blocked "
    "or unapproved Wave-1 still dates the engagement.\n"
    "• Only when Wave-1 has no Nom. Approval Date does it move on to the next "
    "wave, and the next, until one carries a date.\n"
    "• Keeps the account when that date falls in the period.\n"
    "• Counts each TPID once — later waves of the same account never add to it.\n"
    "An account with no approval date on any wave is not counted."
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
    "Unique customers (TPIDs) per month, placed in the month of their Wave-1 date "
    "(approval or creation, per the Trend basis above) — whatever state that wave "
    "is in, falling through to the next wave only when Wave-1 leaves the date "
    "blank. Each TPID appears in one month only."
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
    "• Nom. Approval Date — from Wave-1 whatever its state, falling through to "
    "the next wave that carries one: the same rule the New Engagements tile "
    "counts on, because that is when the account was nominated.\n"
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
    """One named figure, and how it is worked out, in ordinary words.

    ``title`` is the figure exactly as the reports label it, so a reader who
    has a number in front of them can find its definition by name.  ``body`` is
    one or more paragraphs of plain English — never a formula: a report is read
    by the people it is circulated to, and a rule they have to decode before
    they can check a number is a rule they end up trusting instead.
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
        "report gives it. Each one says which accounts or which pieces of work "
        "it counts, which column it reads, and which date decides the period it "
        "falls in.",
        "**Anything in bold is in the spreadsheet**: either a column name, "
        "written exactly as the file heads it — **Nom. Approval Date**, "
        "**Migration Status**, **Total ACR** — or a value written exactly as "
        "that column holds it — **7 - Completed**, **On Track**, **AVS "
        "Migration Nominations**. Everything not in bold is description. So any "
        "number here can be checked by opening the export, finding the column "
        "and reading the same value the report read.",
        Definition("Account", (
            "One customer, identified by its **TPID**. Reports count customers, "
            "not spreadsheet rows: an account with five pieces of work in "
            "flight is still one account. **TPID** is what every count, match "
            "and lookup is keyed on — never the **Customer Name**, which is "
            "spelled differently between worksheets and source systems.",
        )),
        Definition("Wave", (
            "One piece of work for that account, one row of the export, "
            "numbered in the **Phase** column — **Wave 1**, **Wave 2** and so "
            "on. A migration is usually delivered in waves, so one account can "
            "have several, each with its own status, its own dates and its own "
            "**Total ACR**.",
            "The **first wave** of an account is the one with the lowest number "
            "in **Phase**; where two waves share a number, the one with the "
            "earlier **Nom. Created Date** is treated as the earlier wave. The "
            "**latest wave** is the one with the highest number.",
        )),
        Definition("ACR", (
            "The annual revenue a piece of work is expected to bring in, as the "
            "**Total ACR** column records it. Money is written short "
            "throughout: $12.5K is twelve and a half thousand, $1.25M is one "
            "and a quarter million.",
        )),
    )),
    ("Which wave a figure is read from", (
        "An account's waves rarely agree with each other — one may be finished "
        "while the next has not started — so each figure is read from the wave "
        "that can answer for it.",
        Definition("Read from the latest wave", (
            "Where the account stands **now**: its **Migration Status**, its "
            "**Current State**, its **WW Region**, its **Total Cores**, its "
            "**Actual Start Date** and **Actual End Date**, its **Assigned To "
            "(Factory PM)** and its **Solution Architect**.",
            "Where the latest wave leaves one of those cells empty, the "
            "account's own most recent answer for that column stands in, rather "
            "than the report showing a blank it could fill.",
        )),
        Definition("Read from the first wave", (
            "When the account joined the programme: its **Nom. Approval Date**, "
            "read from the first wave whatever state or status that wave is in. "
            "A first wave that was later cancelled, blocked or never approved "
            "still dates the engagement, because the account joined when it "
            "joined.",
            "Only when the first wave has no **Nom. Approval Date** at all does "
            "the report move on to the next wave, and the one after that, until "
            "it finds a wave that has one. An account with no **Nom. Approval "
            "Date** on any wave is not counted as having joined.",
        )),
        Definition("Read across every wave", (
            "An account's **Total ACR** is every one of its waves added "
            "together. An account with waves worth 10M, 15M and 20M is a 45M "
            "account; reading only its latest wave would understate it by more "
            "than half.",
            "Every account-level figure counts an account **once**, however "
            "many waves it has, so nothing is double-counted.",
        )),
    )),
    ("The headline figures", (
        Definition("New Engagements", (
            "The number of **distinct accounts (TPID)** whose **Nom. Approval "
            "Date** falls inside the reporting period.",
            "The date is taken from the account's **first wave** — the lowest "
            "**Phase** number — whatever that wave's **Nomination Status** or "
            "**Current State** says. If that wave has no **Nom. Approval "
            "Date**, the next wave that carries one supplies it instead.",
            "Each account is counted once, in one period only. Later waves of "
            "the same account never add to it, and an account with no **Nom. "
            "Approval Date** anywhere is not counted at all.",
            "It is the one figure that still counts accounts which have since "
            "stopped: an account approved during the period joined the "
            "programme then, whatever happened to it afterwards.",
        )),
        Definition("Migrations Completed", (
            "The number of **distinct accounts (TPID)** that finished inside "
            "the reporting period.",
            "An account counts as finished when its **latest wave** has a "
            "**Migration Status** of **7 - Completed** and **none** of its "
            "other waves is still on track. An account whose latest wave has "
            "finished while an earlier wave is still being worked on is still "
            "being delivered, so it is counted under On-Track Accounts instead.",
            "The account is placed in the period by the **Actual End Date** of "
            "that latest wave.",
        )),
        Definition("Hosts Migrated (Cores Migrated on AVS to Azure Native)", (
            "The **Total Cores** column added up across every **wave** whose "
            "**Migration Status** is **7 - Completed** and whose **Actual End "
            "Date** falls inside the reporting period.",
            "It counts the work, not the customers: an account with three "
            "completed waves contributes all three waves' cores. Each row of "
            "the export is counted once, by its **Task ID**, so a duplicated "
            "row cannot inflate it.",
            "It stays a wave-level figure on purpose. A wave that completed "
            "deployed its hardware, whatever the account as a whole is doing "
            "now — so this figure can move in a month when Migrations "
            "Completed does not.",
            "The AVS motions deploy nodes onto AVS and call it **Hosts "
            "Migrated**; the AVS to Azure Native motion moves cores to "
            "Azure-native services and calls it **Cores Migrated**. Same "
            "column, different noun.",
        )),
        Definition("On-Track Accounts", (
            "The number of **distinct accounts (TPID)** with at least one wave "
            "being worked on right now.",
            "A wave is on track when all three of these are true: its "
            "**Nomination Status** is **Approved**, its **Migration Status** is "
            "one of the four stages that mean the work is under way (**1 - "
            "Validating Commitment & Initial Scope**, **2 - Executing "
            "Pre-Requisites**, **3 - Finalize Scope**, **4 - Executing "
            "Migration**), and its **Current State** is **On Track** and "
            "nothing else.",
            "Any one such wave makes the whole account on track, whatever its "
            "latest wave says.",
            "It is a snapshot of where things stand today, so **no reporting "
            "period narrows it**.",
        )),
        Definition("ACR Claimed", (
            "The **Total ACR** column added up across every **wave** whose "
            "**Actual End Date** falls inside the reporting period, whatever "
            "state the account is in now.",
            "Claiming is wave-level, not account-level. If waves 2 and 3 of one "
            "account and wave 5 of another all ended inside the window, all "
            "three waves' **Total ACR** is counted. A wave that ended outside "
            "the window contributes nothing, even when a sibling wave of the "
            "same account ended inside it, and a wave with no **Actual End "
            "Date** has not claimed and never counts.",
        )),
        Definition("ACR Pipeline", (
            "The **Total ACR** added up across every wave that is still to "
            "land — the value of the approved work this report is responsible "
            "for that is moving right now.",
            "A wave is counted only when **all four** of these hold. It belongs "
            "to this report's motion: a **Factory Offering** of **AVS Migration "
            "Nominations** for the AVS and EOS reports, or a **Primary "
            "Migration Path** containing **From AVS** for the AVS to Azure "
            "Native report. Its **Nomination Status** is **Approved**. Its "
            "**Current State** is **On Track** and nothing else. And its "
            "**Migration Status** is neither **5 - Deferred By Customer** nor "
            "**6 - Cancelled / Archived**.",
            "Work that has already finished needs no exclusion of its own: a "
            "finished wave reads **Done** rather than **On Track**, so the "
            "third condition leaves it out.",
            "**The reporting period does not narrow this figure.** Work "
            "nominated before the window is still work still to do. Every other "
            "filter applies, so a report cut to one region shows that region's "
            "pipeline.",
        )),
        Definition("Nodes Deployment Planned (EOS reports only)", (
            "The **Total Cores** added up across exactly the same waves ACR "
            "Pipeline is read from — the hardware that approved, on-track work "
            "still has to deploy.",
            "Like ACR Pipeline, it is read over the whole dataset rather than "
            "the reporting period.",
        )),
        Definition("Cumulative", (
            "The last column of every monthly table: the running total of the "
            "months actually shown, added up as you read down. It is not a "
            "separate figure counted a different way, and it does not reach "
            "back before the first month on display.",
        )),
    )),
    ("How an account's state is decided", (
        "Every account is given exactly one state, which is what lets the "
        "charts and the stopped-accounts section add up to the report's own "
        "account count.",
        Definition("The order the state is decided in", (
            "The first of these to fit is the state the account gets. "
            "**On-Track** when any of its waves is on track by the three-part "
            "test under On-Track Accounts. **Completed** when its latest wave "
            "reads **7 - Completed** and no wave of the account is on track.",
            "Failing both, its latest wave decides: **Cancelled** when that "
            "wave's **Migration Status** is **6 - Cancelled / Archived**, "
            "**Blocked** when its **Current State** mentions being blocked, "
            "**Deferred** when its **Migration Status** is **5 - Deferred By "
            "Customer**, and **Other** for anything left.",
            "On-Track is tested before Completed on purpose: an account whose "
            "latest wave has finished while an earlier wave is still running is "
            "still being delivered.",
        )),
        Definition("What is not on track", (
            "A wave nobody has approved is not on track, however far along it "
            "looks: nothing has been committed to. A wave with a blank "
            "**Current State** is not on track either — that column is how the "
            "programme says an engagement is moving, and a wave nobody has said "
            "it about is left out rather than assumed. There is no fallback for "
            "either; both land in **Other**.",
            "A wave that has finished, been deferred or been cancelled is not "
            "on track whatever its **Current State** still reads, because its "
            "**Migration Status** is no longer one of the four in-flight "
            "stages.",
        )),
        Definition("Blocked, deferred and cancelled accounts", (
            "Every account that is neither On-Track nor Completed is reported "
            "in this section, and nowhere else. That is the whole test for "
            "being included, so this section and the pipeline charts above it "
            "add up to the report's accounts.",
            "Each account is labelled with why it stopped, and the first reason "
            "that fits is the one shown. A **Migration Status** of **6 - "
            "Cancelled / Archived** labels it cancelled and **5 - Deferred By "
            "Customer** labels it deferred — those are decisions somebody took, "
            "so the **Migration Status** wins over the **Current State** even "
            "when the state still reads **Blocked - Customer**.",
            "Failing those, the **Current State** is the reason in its own "
            "words: **Blocked**, **Blocked - Account team**, **Blocked - "
            "Customer**, **Blocked - Partner / ISD** or **Waiting action on "
            "follow up date**. Failing that, a nomination whose **Nomination "
            "Status** is not **Approved** is labelled as not approved, and an "
            "account with nothing recorded at all is labelled as such rather "
            "than guessed at.",
            "None of these accounts is in any other figure: not the headline "
            "tiles, the trends, the state chart or the regional cut. New "
            "Engagements is the one deliberate exception, for the reason given "
            "in its own entry. Every row carries the account's **Status "
            "Summary** — the programme's own note on what it is waiting for.",
        )),
        Definition("Where every account sits", (
            "A table under the pipeline lists every state, how many accounts "
            "are in it, how much **Total ACR** they carry, and where those "
            "accounts are reported. Two states are charted — On-Track and "
            "Completed — and every other state is in the stopped-accounts "
            "section.",
            "Because each account is in exactly one state, those rows add up to "
            "the report's own account count. It is the answer to "
            "the chart shows 32 of my 36 accounts, where are the other four.",
        )),
    )),
    ("Which report an account appears in", (
        "Each report covers one migration motion, decided per nomination from "
        "what it is moving and where it is moving to.",
        Definition("All AVS Migrations", (
            "Every nomination whose target platform is AVS — read from the "
            "**Primary Migration Path**, the **Factory Offering** and the "
            "**Linked Offering Name**. On-premises, VMG, AWS/VMC, AVS-to-AVS "
            "and EOS refreshes all land here.",
            "Every EOS account is included too, whatever its own path reads.",
        )),
        Definition("AVS to Azure Native", (
            "Nominations whose **Primary Migration Path** contains **From "
            "AVS** — work moving off AVS onto an Azure-native service, such as "
            "**SQL Server MI Migration (From AVS)** or **OSS DB Migration (From "
            "AVS)**.",
            "**Reported here and nowhere else.** This motion is leaving AVS, so "
            "counting it under All AVS Migrations (which is onboarding to AVS) "
            "or under EOS (which is refreshing ageing AVS hosts) would file it "
            "in the wrong story. Not even a Gen-1 or Gen-2 tag pulls one in.",
            "The Azure-native service each one lands on is read from the same "
            "**Primary Migration Path**: SQL MI, SQL Database, SQL on IaaS, "
            "PostgreSQL/MySQL, Windows or Linux virtual machines, Oracle "
            "Database@Azure or AKS.",
        )),
        Definition("EOS Migration", (
            "Accounts refreshing ageing AVS hardware, reported by the "
            "generation they are moving on to — Gen-1 and Gen-2, with a "
            "combined view and a page each.",
            "An account is in EOS scope when its generation is known (see "
            "below), or when any of its waves carries an EOS offering: a "
            "**Primary Migration Path**, **Factory Offering** or **Linked "
            "Offering Name** reading **AV36/AV36P/AV52 - EOS**. One qualifying "
            "wave brings the whole account in.",
        )),
        Definition("The generation (Gen-1 or Gen-2)", (
            "Decided per account, across all of its waves, by the first of "
            "these that answers.",
            "**The manual EOS tracking sheet first.** Its **Target SDDC "
            "Generation** column reading **Gen1** or **Gen2** settles it — that "
            "is the programme stating, in its own document, which generation "
            "the account is landing on.",
            "**Failing that, the Tags column.** A **Tags** value containing "
            "**AVS Migration - Gen1** on any one wave makes the whole account "
            "Gen-1, and **AVS Migration - Gen2** makes it Gen-2. Tags arrive "
            "run together with no separator, so the marker is matched inside "
            "the cell whatever sits either side of it. If both appear on "
            "different waves, Gen-1 wins.",
            "**Failing both, the account has no generation.** It may still be "
            "in EOS scope through its offering, but there is no block to report "
            "it under.",
        )),
        Definition("EOS accounts with no generation", (
            "An account in EOS scope through **AV36/AV36P/AV52 - EOS** with no "
            "**Target SDDC Generation** and no Gen-1 or Gen-2 **Tags** value is "
            "**left out of every EOS figure**. EOS is reported by generation, "
            "and counting an ungenerationed account in the combined total would "
            "make that total disagree with the sum of its own two blocks.",
            "It is not discarded: it stays inside All AVS Migrations, and it is "
            "listed on the Data Inconsistency review so the missing tag can be "
            "fixed at source — which brings it straight into the EOS reports.",
        )),
    )),
    ("The manual EOS tracking sheet", (
        "The EOS programme keeps its own spreadsheet beside the nominations "
        "export, and it is uploaded separately. Where it is loaded, it leads on "
        "three things; everything else still comes from the export.",
        Definition("How it is matched", (
            "On **TPID**, and on nothing else. Every other detail an EOS report "
            "needs — **Assigned To (Factory PM)**, **Solution Architect**, "
            "**WW Region**, **Factory Offering**, **Total ACR**, the waves — is "
            "looked up in the nominations export by that **TPID**, so the sheet "
            "never has to repeat or contradict them.",
            "A **TPID** in the sheet that the export has never heard of has no "
            "nomination behind it — no offering, no ACR, no wave — so it "
            "appears in no report. It is named on the Data Inconsistency "
            "review instead of being invented.",
        )),
        Definition("What it decides", (
            "**Target SDDC Generation** decides the account's generation, as "
            "described above. **Migration Start Date** and **Actual Migration "
            "End Date** supply the two date rows of the monthly programme "
            "matrix. **Total SDDCs in Scope for Migration** and **Number of "
            "SDDCs Migrated** are read and shown but feed no headline figure.",
            "Where the sheet is silent — a blank cell, or an account it does "
            "not cover — the export answers exactly as it did before there was "
            "a sheet. A report built with no sheet loaded at all is unchanged.",
        )),
    )),
    ("The EOS monthly programme matrix", (
        "A month-by-month grid in two blocks, **Gen1 to Gen1** and **Gen1 to "
        "Gen2**. Every EOS account is refreshing away from ageing Gen-1 "
        "hardware, so the constant half of each heading is where it is coming "
        "from, and the account's own generation names where it is landing.",
        "The grid ignores the reporting period the rest of the report uses. It "
        "runs from July 2025 to the current month — further if a completion is "
        "dated ahead of it — and shows **every** month in between, because a "
        "month with nothing in it is itself the number being reported. Each "
        "fiscal year closes with its own total column.",
        Definition("Total number of new engagement", (
            "Accounts, counted once each, in the month of the **Nom. Approval "
            "Date** that New Engagements reads.",
        )),
        Definition("Total number of migration start", (
            "Accounts, counted once each, in the month their migration began.",
            "The date is the tracking sheet's **Migration Start Date** wherever "
            "it has one. For an account the sheet does not cover, it is worked "
            "out from the export instead: take the earliest wave whose "
            "**Current State** reads **On Track** or **Done** — the first wave "
            "actually under way — and read its **Actual Start Date**, falling "
            "back to its **Planned Start Date**, and failing that its **Nom. "
            "Approval Date**. An account with no such wave has not started and "
            "is not counted.",
        )),
        Definition("Total number of migration end", (
            "Accounts, counted once each, in the month their migration ended.",
            "The date is the tracking sheet's **Actual Migration End Date** "
            "wherever it has one. For an account the sheet does not cover, it "
            "is the **Actual End Date** of the latest wave of an account that "
            "counts as finished — the same test Migrations Completed uses.",
        )),
        Definition("Total number of engagement end", (
            "The same figure as migration end. The export marks when a wave "
            "ended but has no separate closure date for the engagement itself, "
            "so an account whose latest wave has completed is the closest the "
            "data comes to an engagement that ended. The two rows carry "
            "identical values by construction, not by coincidence.",
        )),
        Definition("Number of hosts migrated", (
            "The **Total Cores** on every wave reading **7 - Completed**, added "
            "up in the month of each wave's **Actual End Date** — the same "
            "figure as Hosts Migrated, month by month.",
        )),
    )),
    ("Dates and durations the app works out", (
        "These are derived from the export's own dates rather than read from a "
        "column of their own. They drive the insights and the delivery-health "
        "wording; none of them changes a headline figure.",
        Definition("Approved, closed, open", (
            "An account or wave counts as **approved** when it has a **Nom. "
            "Approval Date**, or its **Nomination Status** contains approved.",
            "It counts as **closed** when its **Migration Status** reads **7 - "
            "Completed**, or its **Current State** says done or complete, or "
            "its **Milestone Status** says complete, or it simply has an "
            "**Actual End Date**. Anything neither closed nor cancelled is "
            "**open**.",
        )),
        Definition("Aging (days)", (
            "**Nom. Created Date** to the day the work closed — or to the "
            "reporting as-of date when it is still open. It answers how long "
            "this has been going on.",
            "A negative result means the dates contradict each other, so it is "
            "dropped rather than reported.",
        )),
        Definition("Cycle time (days)", (
            "**Nom. Created Date** to **Actual End Date**, for closed work "
            "only. It answers how long this took, so unfinished work is left "
            "out rather than counted as fast.",
        )),
        Definition("Approval latency (days)", (
            "**Nom. Created Date** to **Nom. Approval Date** — how long a "
            "nomination waited to be approved. The insights report the median "
            "across the selection, and the region with the slowest median.",
        )),
        Definition("Closure rate", (
            "Closed items divided by all items in the current selection, as a "
            "percentage.",
        )),
        Definition("Delivery health, and Risk", (
            "Each wave is given a health status from several columns at once, "
            "the first matching rule winning: **Completed**, then "
            "**Cancelled**, then **Blocked**, then **At Risk** when it is "
            "deferred, then **Delayed** when its **Planned End Date** has "
            "passed and there is no **Actual End Date**, then **At Risk** again "
            "when its **Next Follow-up Date** has passed or it is waiting, and "
            "otherwise **On Track**.",
            "**Risk** on the insights means any wave sitting in **At Risk**, "
            "**Delayed** or **Blocked**. It is a direct count of those three, "
            "with no scoring model behind it.",
            "This is a different thing from the account states above, which the "
            "pipeline charts use. The two are not interchangeable.",
        )),
    )),
    ("Trends, periods and the fiscal year", (
        Definition("The monthly trends", (
            "Four measures, each by the date that places it. Nominations per "
            "month puts each account in the month of the **Nom. Approval Date** "
            "New Engagements reads (or its **Nom. Created Date**, if you switch "
            "the basis). ACR claimed per month splits ACR Claimed by the "
            "**Actual End Date** of each claiming wave. Hosts and migrations "
            "completed per month do the same for their own figures.",
            "Every account appears in one month only on the account-level "
            "measures, so the months add back up to the tile above them.",
        )),
        Definition("Fiscal years side by side", (
            "The same four measures again, with each fiscal year drawn as its "
            "own line over a shared July-to-June axis, so the years can be read "
            "against one another. All twelve months are always listed, "
            "including the empty ones.",
            "**It covers the whole dataset, whatever period the rest of the "
            "report is cut to**: a year-on-year comparison narrowed to a single "
            "month would have nothing to compare. There is no cumulative column "
            "in this view — a running total across unrelated fiscal years would "
            "not mean anything.",
        )),
        Definition("Top 10 accounts by ACR", (
            "The ten accounts carrying the most **Total ACR**, largest first, "
            "on the All AVS Migrations and AVS to Azure Native reports.",
            "**Total ACR** is summed across every wave of an account, so the "
            "order is the account-level one. Accounts with no ACR are left out "
            "rather than listed as zeroes, and each bar is labelled with the "
            "**Customer Name** and its **TPID** so no two bars can be the same "
            "account. It covers the whole dataset, not the reporting period.",
        )),
        Definition("The reporting period, and the This FY row", (
            "The period narrows the figures that are about a span of time: New "
            "Engagements, Migrations Completed, Hosts Migrated, ACR Claimed and "
            "the monthly trends.",
            "It does **not** narrow On-Track Accounts, the current pipeline, "
            "the regional cut, the stopped accounts, ACR Pipeline, Nodes "
            "Deployment Planned, the programme matrix or the fiscal-year "
            "comparison. Each of those says so under its own title.",
            "Selecting any period other than the current fiscal year adds a "
            "**This FY** row of tiles above the selected one, so a month's "
            "numbers keep the year they sit in. The two rows are worked out "
            "independently, each from its own window. All time gets that row "
            "too, because it spans several fiscal years and so loses the one "
            "you are in.",
        )),
    )),
    ("Region, money and the reporting floor", (
        Definition("WW Region", (
            "Every regional grouping, filter and chart reads the **WW Region** "
            "column and is labelled with that name — the value the business "
            "reports on, such as **Americas - Enterprise**, **Americas SME&C** "
            "or **MS Elevate**. Nothing reduces it to a geography.",
            "A leading number on the value (as in 1800 Americas) is stripped "
            "and flagged on the Data Inconsistency review. **Customer "
            "Segment** is a separate column and is reported separately.",
            "The regional breakdown counts accounts once each, at their latest "
            "wave, over the stages a migration passes through — the four "
            "in-flight ones plus **7 - Completed**. Deferred and cancelled work "
            "is not a stage a migration progresses through, so it is left out, "
            "which is why these counts are lower than the report's total "
            "accounts.",
        )),
        Definition("Money", (
            "Written short — $12.5K, $125K, $1.25M — in tiles, tables, chart "
            "axes and chart tooltips alike, so the same amount reads the same "
            "way wherever it appears.",
        )),
        Definition("The reporting floor", (
            "Waves nominated before FY25 are dropped as the file is read, "
            "before anything is counted. A wave belongs to the fiscal year of "
            "its **Nom. Approval Date**, or its **Nom. Created Date** when it "
            "was never approved; a wave carrying neither cannot be shown to be "
            "out of scope, so it stays.",
            "This is why **All time** means FY25 onwards everywhere, in every "
            "chart, table, total and export.",
        )),
    )),
)
