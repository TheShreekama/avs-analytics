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
#: "Methodology & logic" as (heading, paragraphs).  Shared by the PDF, the HTML
#: report and the Methodology page, so one rule cannot be documented three ways.
#:
#: **Written as plain English, not as formulas.**  A report is read by whoever
#: it is circulated to — account teams, programme managers, the leadership it is
#: written for — and a block of pseudo-SQL asks them to decode a rule before
#: they can check a number.  So every rule below is a sentence.  Column names
#: and the values a cell actually holds are still quoted where a reader would
#: need them to go and look ("Current State", "7 - Completed"), because that is
#: what turns a description into something checkable; nothing else is.
#:
#: Each section says the same thing the code does.  Where the two could drift,
#: a test holds them together.
REPORT_METHODOLOGY: tuple[tuple[str, tuple], ...] = (
    ("Reading this report — three words it uses", (
        "**Account** — one customer. Reports count customers, not rows: an "
        "account with five pieces of work in flight is still one account.",
        "**Wave** — one piece of work for that account. A migration is usually "
        "delivered in waves, so one account can have several, each with its own "
        "status and dates.",
        "**ACR** — the annual revenue the work is expected to bring in, as the "
        "export records it. Money is written short throughout: $12.5K is twelve "
        "and a half thousand, $1.25M is one and a quarter million.",
        "Everything below is read from the columns of the export — *Migration "
        "Status*, *Current State*, *Nomination Status* and so on. Those names "
        "are quoted where you would need them to go and check a number against "
        "the file. Nothing is estimated or inferred: if the export does not say "
        "it, the report does not claim it.",
    )),
    ("Which wave a number comes from", (
        "An account's waves rarely agree with each other — one may be finished "
        "while the next has not started — so each figure is read from the wave "
        "that can answer for it.",
        "**Where the account stands now** — its status, its stage, its region, "
        "its dates and the people on it — comes from its **most recent wave**, "
        "the one with the highest wave number. Where two waves share a number, "
        "the one created later is treated as the more recent.",
        "**When the account joined the programme** comes from its **first "
        "wave** — the lowest wave number — and specifically from that wave's "
        "*Nom. Approval Date*, **whatever state or status the wave is in**. A "
        "first wave that was later cancelled, blocked or never approved still "
        "dates the engagement, because the account joined when it joined. Only "
        "when the first wave has no approval date at all does the report look "
        "at the next wave, and the one after that, until it finds one. An "
        "account with no approval date anywhere is not counted as having "
        "joined.",
        "**The account's money** is every wave's *Total ACR* added together. An "
        "account with waves worth 10M, 15M and 20M is a 45M account; reading "
        "only its most recent wave would understate it by more than half.",
        "Every account-level figure counts an account **once**, however many "
        "waves it has, so nothing is double-counted.",
    )),
    ("Is an account moving, or finished?", (
        "Two questions a report has to answer honestly: which accounts are "
        "being worked on right now, and which are done. Both are read from what "
        "the programme itself has recorded, never from \"it has not finished, "
        "so it must be moving\".",
        "**A single wave counts as on track only when three things are all "
        "true.** Its *Nomination Status* says it has been **approved**. Its "
        "*Migration Status* is one of the four stages that mean the work is "
        "under way — validating the commitment and initial scope, executing "
        "pre-requisites, finalising scope, or executing the migration. And its "
        "*Current State* says **\"On Track\"**, in those words and nothing "
        "else.",
        "If nobody has said it is on track — the *Current State* is blank — the "
        "report does not say so either. The same goes for work nobody has "
        "approved yet: it may be progressing, but nothing has been committed "
        "to. Both are left out rather than counted. A wave that has already "
        "finished, or that the customer has deferred or cancelled, is not on "
        "track either, whatever its *Current State* still reads.",
        "**An account is then given one state, and the first of these to fit "
        "is the one it gets.** It is *On-Track* if **any** of its waves is on "
        "track by the test above. It is *Completed* only when its most recent "
        "wave reads **\"7 - Completed\"** and none of its other waves is "
        "still on track. Failing both, its most recent wave decides: "
        "*Cancelled* when that wave reads \"6 - Cancelled / Archived\", "
        "*Blocked* when its *Current State* mentions being blocked, *Deferred* "
        "when it reads \"5 - Deferred By Customer\", and *Other* for anything "
        "left.",
        "That order is the difference that matters: an account whose latest "
        "wave has finished while an earlier one is still being worked on is "
        "**still being delivered**, so it is counted as On-Track rather than "
        "Completed. Every account lands in exactly one state, which is what "
        "lets the numbers add up.",
    )),
    ("Accounts that have stopped", (
        "Work that has stalled is worth more attention than work that is going "
        "well, so every account that is neither moving nor finished is reported "
        "on its own, grouped by why it stopped.",
        "**Every account that is neither On-Track nor Completed is here** — "
        "that is the whole test for being included, so this section and the "
        "charts above it add up to the report's own account count.",
        "**Each one is labelled with the reason, and the first reason that fits "
        "is the one shown.** A *Migration Status* of \"6 - Cancelled / "
        "Archived\" makes it cancelled; \"5 - Deferred By Customer\" makes "
        "it deferred. Failing those, the *Current State* is the reason in its "
        "own words — blocked, blocked on the account team, on the customer or "
        "on a partner, or waiting on a follow-up date. Failing that, an "
        "unapproved nomination is labelled as not approved, and an account with "
        "nothing recorded at all is labelled as such rather than guessed at.",
        "**Cancelled and deferred accounts are named by their Migration "
        "Status**, not by their Current State: somebody has decided those, and "
        "an account deferred while its state still reads *Blocked - Customer* "
        "is deferred. A review reads a decision differently from a blockage.",
        "This section is reported **apart from every other figure** and nowhere "
        "else: not in the headline tiles, the trends, the state chart or the "
        "regional cut. Every row carries the programme's own **Status "
        "Summary**, the note saying what the account is waiting for.",
        "One figure deliberately still counts them: **New Engagements**. An "
        "account approved during the period joined the programme then, whatever "
        "happened afterwards, and a number that changed when an account got "
        "blocked would be answering a different question.",
    )),
    ("Where every account sits", (
        "A chart that shows some accounts and not others invites the question "
        "\"where are the rest?\". Each report answers it with a table under "
        "the pipeline: every state, how many accounts are in it, and where "
        "those accounts are reported.",
        "Two rows are charted — On-Track and Completed — and every other row "
        "is in the stopped-accounts section, whatever stopped it. Nothing is "
        "reported nowhere.",
        "Because every account is in exactly one state, the rows add up to the "
        "report's own account count. If the charts appear to be missing "
        "accounts, that table is where they are.",
    )),
    ("What is still to come — ACR Pipeline and Nodes", (
        "The headline figures otherwise look backwards: what has been "
        "delivered, what has been claimed. These two look forward — the value "
        "and the hardware still to land.",
        "**A wave is counted here only when all four of these hold.** It "
        "belongs to the motion this report covers: for the AVS and EOS reports "
        "that means a *Factory Offering* of **\"AVS Migration Nominations\"**, "
        "and for the AVS → Azure Native report a *Primary Migration Path* that "
        "says the work is moving **\"From AVS\"**. Its *Nomination Status* "
        "says it has been **\"Approved\"**. Its *Current State* says **\"On "
        "Track\"** and nothing else. And the customer has neither deferred it "
        "(\"5 - Deferred By Customer\") nor cancelled it (\"6 - Cancelled / "
        "Archived\").",
        "**ACR Pipeline** adds up the *Total ACR* on those waves. On the EOS "
        "reports, **Nodes Deployment Planned** adds up the *Total Cores* on the "
        "same waves — the hardware that work still has to deploy.",
        "Work that has already finished is not in either figure, and does not "
        "need to be excluded by name: a finished wave reads *Done* rather than "
        "*On Track*, so the third condition leaves it out on its own.",
        "**Factory Offering and Primary Migration Path are different "
        "columns.** The offering says which team delivers the work; the path "
        "says what is moving where. Each report is scoped by the one that "
        "defines it, so an AVS report does not count another factory's work.",
        "**Both figures cover the whole dataset, not the reporting period.** "
        "Work nominated before the window is still work still to do, so "
        "narrowing the dates cannot shrink the pipeline. Every other filter "
        "still applies: a report cut to one region shows that region's "
        "pipeline.",
    )),
    ("EOS by generation", (
        "The EOS reports also cut their accounts by generation against state: "
        "how much of Gen-1 is finished, how much of Gen-2 is still running, how "
        "much of either has stopped. Every state is a column, and an **All "
        "EOS** row adds the generations together, so the grid reads as the "
        "programme first and its generations second — and each row totals the "
        "accounts it covers.",
    )),
    ("EOS reporting — Gen-1 and Gen-2 only", (
        "EOS accounts are those refreshing ageing AVS hardware, and the "
        "programme reports them by which generation they are moving on to. An "
        "account whose generation nobody recorded therefore cannot be reported "
        "under either.",
        "**The programme's own EOS tracking sheet decides the generation "
        "wherever it states one.** Its *Target SDDC Generation* column reading "
        "Gen1 or Gen2 settles the matter, because that is the programme saying "
        "in its own document which generation the account is landing on.",
        "**Failing that, the account's tags decide it.** A tag reading \"AVS "
        "Migration - Gen1\" on any one of its waves makes the whole account "
        "Gen-1, and \"AVS Migration - Gen2\" makes it Gen-2; if both appear "
        "on different waves, Gen-1 wins.",
        "**Failing both, the offering can still put an account in scope but "
        "cannot name its generation.** A migration path, factory offering or "
        "linked offering reading \"AV36/AV36P/AV52 - EOS\" means the account "
        "is doing EOS work — but with no generation recorded anywhere, there is "
        "no block to report it under, so the EOS reports leave it out. Those "
        "accounts are **not discarded**: they stay in All AVS Migrations and "
        "are listed under **Data Inconsistency**, and adding the tag at source "
        "brings them straight in. Counting them in the combined total meanwhile "
        "would make that total disagree with the sum of its own two blocks.",
        "The **EOS tracking sheet is joined on by TPID**, and by TPID alone: "
        "every other detail on an account — Factory PM, Solution Architect, "
        "region, offering, ACR, waves — is looked up in the FDO dataset, so the "
        "sheet never has to repeat or contradict them. A TPID in the sheet that "
        "the FDO dataset does not hold has no nomination behind it and so "
        "appears in no report; it is named under **Data Inconsistency** "
        "instead.",
        "**The month-by-month programme matrix takes its two dates from the "
        "sheet as well, wherever it has them.** A *Migration Start Date* in the "
        "sheet is when the migration started, and an *Actual Migration End "
        "Date* is when it ended. For any account the sheet does not cover, the "
        "export answers instead: the start is taken from the earliest wave "
        "somebody recorded as on track or done — its actual start date, or "
        "failing that its planned start, or failing that its approval date — "
        "and the end is the date the account's most recent wave completed. A "
        "report built with no tracking sheet at all therefore reads exactly as "
        "it did before there was one.",
    )),
    ("The other headline figures", (
        "**Three figures count customers, each one once.** *New Engagements* is "
        "how many accounts were approved inside the period, dated by the "
        "approval on their first wave as described above. *Migrations "
        "Completed* is how many accounts finished inside it, counting only "
        "accounts whose state is Completed and dating each by the day its most "
        "recent wave ended. *On-Track Accounts* is how many are being worked on "
        "right now — a snapshot, so no reporting period narrows it.",
        "**Two figures count work rather than customers.** *Hosts Migrated* "
        "(called *Cores Migrated* on the AVS → Azure Native report) adds up the "
        "*Total Cores* on every wave that reads \"7 - Completed\" and ended "
        "inside the period. *ACR Claimed* adds up the *Total ACR* on every wave "
        "that ended inside the period, whatever state the account is in now.",
        "These two are counted per wave on purpose: a finished wave deployed "
        "its hardware and claimed its money whatever the account is doing now, "
        "and one account can claim in several months. A wave with no end date "
        "has not claimed and never counts.",
        "**Cumulative**, the last column of every trend table, is the running "
        "total of the months actually shown — not a separate figure counted a "
        "different way.",
    )),
    ("Periods, regions and money", (
        "The reporting period narrows the figures that are about a span of "
        "time. **On-Track Accounts, the current pipeline, the regional cut and "
        "the stopped accounts are snapshots** of where things stand today, and "
        "**ACR Pipeline and Nodes Deployment Planned cover the whole "
        "dataset** — each says so under its own title.",
        "Selecting any period other than the current fiscal year adds a **This "
        "FY row above it**, each measured over its own window, so a month's "
        "numbers keep the year they sit in. *All time* gets that row too: it "
        "spans several fiscal years, so it loses the one you are in.",
        "**The fiscal-year comparison covers the whole dataset**, whatever "
        "period the rest of the report is cut to. Laying one year against "
        "another is the point of it, and a comparison narrowed to a single "
        "month would have nothing to compare.",
        "The **regional breakdown** counts accounts once each, at their most "
        "recent wave, over the stages a migration passes through. It is one "
        "heatmap: a second chart of the same numbers is one too many.",
        "**Money is written short** — $12.5K, $125K, $1.25M — in tiles, tables, "
        "chart axes and chart tooltips alike, so the same amount reads the same "
        "way wherever it appears.",
    )),
)
