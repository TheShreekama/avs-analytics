"""Management report engine — the PDF the Reports page builds.

The document is deliberately two-part, so one file serves both a leadership
review and the questions that follow it:

* **Part 1 — Executive reports.** One page-set per migration motion (AVS
  Migrations, EOS Migrations, AVS to Azure Native), section for section as the
  interactive HTML report renders them: headline metrics over a This-FY row,
  the EOS programme matrix, every trend month by month and then fiscal year
  against fiscal year, the largest accounts by ACR, the pipeline, the regional
  cut, the generations, the insights, and the accounts that have stopped.  Each
  chart carries its own numbers underneath it.
* **Part 2 — Supporting detail.** What a printed report cannot click through
  to: the regional matrix, the pipeline counts and the account records, on
  landscape pages.

Every report links to its drill-down and every drill-down links back, as real
PDF destinations rather than styled text, alongside a clickable contents page
and a bookmark outline.

The numbers come from :mod:`app.core.kpi` and :mod:`app.core.segments` — the
same calculation layer the Status Report pages render, called the
same way — so a figure in the PDF and the same figure on screen cannot drift
apart.  Charts are rasterised with matplotlib (:mod:`app.ui.pdf_charts`), never
a bundled browser.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

import pandas as pd
from reportlab.lib.units import cm
from reportlab.platypus import KeepTogether, PageBreak, Paragraph

from ..config import EOS_MATRIX_START_FY, FY_START_MONTH
from ..ui import pdf_charts as pc
from . import (analytics, glossary, insights as insights_mod, kpi, metrics,
               pdf_kit as kit, segments)
from .metrics import fmt_currency, fmt_int


@dataclass(frozen=True)
class ReportSpec:
    """One primary report: its title, and the dashboards it is drawn from."""
    key: str
    title: str
    category: str
    source: str
    #: Extra categories consolidated into this report (EOS Gen-1 / Gen-2).
    breakdown: tuple[str, ...] = ()
    #: "Hosts Migrated" for the AVS motions, "Cores Migrated" leaving AVS.
    unit_label: str = "Hosts Migrated"
    blurb: str = ""


REPORTS: tuple[ReportSpec, ...] = (
    ReportSpec(
        "avs", "AVS Migrations", segments.CAT_ALL_AVS,
        "Status Report → All AVS Migrations",
        blurb="Every migration whose target platform is AVS — on-premises, VMG, "
              "AWS/VMC, AVS-to-AVS and EOS refreshes alike."),
    ReportSpec(
        "eos", "EOS Migrations", segments.CAT_EOS_ALL,
        "Status Report → EOS Migrations (All), EOS Gen-1, EOS Gen-2",
        breakdown=(segments.CAT_EOS_GEN1, segments.CAT_EOS_GEN2),
        blurb="Accounts refreshing ageing AVS hosts — in scope through an "
              "\"AVS Migration - Gen1/Gen2\" tag on any wave, or an "
              "\"AV36/AV36P/AV52 - EOS\" migration path when untagged."),
    ReportSpec(
        "native", "AVS to Azure Native", segments.CAT_AVS_NATIVE,
        "Status Report → AVS → Azure Native",
        unit_label="Cores Migrated",
        blurb="Migrations away from AVS to Azure-native services — the "
              "\"(From AVS)\" offerings. Reported here and nowhere else."),
)

@dataclass(frozen=True)
class ReportSections:
    """Which optional sections a report carries.

    Both are complete pieces of reporting that not every audience wants in the
    document: the blocked-accounts list is the review's working set, the
    insights are commentary.  The defaults are the ones the Reports page offers
    — **blocked in, insights out** — so a report built without asking for
    either is the one most people want.  Whether a section is *visible* on
    opening is a separate question, answered by the reader's own checkbox in
    the HTML report.
    """
    blocked: bool = True
    insights: bool = False


#: What a report calls itself when the caller says nothing.  Deliberately about
#: the subject — the migration programme — and never about the application that
#: rendered it or the export it was read from: a report circulated to leadership
#: should read as analysis, not as a tool's output.
DEFAULT_TITLE = "Migration Programme Report"
DEFAULT_SUBTITLE = "Management Report"

REPORT_KEYS = [r.key for r in REPORTS]
_BY_KEY = {r.key: r for r in REPORTS}

#: Optional appendices, offered alongside the three reports.
APPENDIX_LIBRARY = [("inconsistency", "Data inconsistency review "
                                      "(tag vs. EOS-path disagreements)")]
APPENDIX_KEYS = [k for k, _ in APPENDIX_LIBRARY]

#: Account rows printed per drill-down before the table is truncated.  Beyond
#: this a PDF stops being something anyone reads; the CSV export on the Reports
#: page is the right tool, and the truncation note says so.
MAX_DRILLDOWN_ROWS = 300

#: Shared with the HTML renderer, so both reports lay accounts out identically.
#: Account-table layout as (source column, header, relative width).  Widths are
#: scaled to the page, so adding the generation column for EOS narrows the rest
#: rather than running off the edge.
ACCOUNT_COLUMNS = [
    ("tpid", "TPID", 1.9),
    ("customer_name", "Customer", 4.3),
    ("region_geo", "WW Region", 1.8),
    ("migration_status_label", "Migration Status", 4.1),
    ("current_state", "Current State", 3.0),
    ("solution_architect", "Solution Architect", 3.0),
    ("assigned_pm", "Factory PM", 3.0),
    ("_waves", "Waves", 1.5),
    ("total_cores", "Cores", 1.4),
    ("total_acr", "ACR", 2.0),
]
GENERATION_COLUMN = ("generation", "Gen", 1.5)


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def _strip(text: str) -> str:
    """Markdown bold (**x**) as ReportLab bold, with markup characters escaped."""
    safe = str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", safe)


def _esc(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    if isinstance(value, pd.Timestamp):
        return "" if pd.isna(value) else f"{value:%d %b %Y}"
    text = str(value)
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def clean(series: pd.Series) -> pd.Series:
    """Blank/missing values as "Unknown", so a chart axis never loses a bar."""
    return series.astype("string").replace({"": pd.NA}).fillna("Unknown")


def labelled(fact: pd.DataFrame, column: str) -> pd.DataFrame:
    """Value counts for one column, biggest first — the shape charts expect."""
    if column not in fact.columns or fact.empty:
        return pd.DataFrame(columns=["category", "count"])
    return (clean(fact[column]).value_counts()
            .rename_axis("category").reset_index(name="count"))


def headline(pop: pd.DataFrame, waves: kpi.WaveIndex, start, end,
             all_time: pd.DataFrame | None = None) -> dict:
    """The dashboard tiles, computed exactly as the dashboard computes them.

    ``acr_pipeline`` and ``nodes_planned`` are the two forward-looking ones and
    are read over the **whole dataset**, never the reporting period: they answer
    what the approved, on-track work is worth and how many nodes it still has
    to deploy, and work nominated before the window is still work still to do.
    Pass ``all_time`` — the same population with the period dropped — and they
    are computed from it; without it they fall back to ``pop``, which is right
    when the caller has no period filter to drop (the dashboards read the whole
    category already).  Every other filter still binds: a report cut to one
    region reports that region's pipeline, not the portfolio's.

    ``nodes_planned`` is computed for every report but only shown on the EOS
    ones.
    """
    ahead = pop if all_time is None else all_time
    return {
        "engagements": kpi.new_engagements(pop, start, end,
                                           approvals=waves.approval),
        "completed": kpi.migrations_completed(pop, start, end, lasts=waves.last),
        "hosts": kpi.hosts_migrated(pop, start, end),
        "on_track": kpi.on_track_accounts(pop, lasts=waves.last),
        "acr": kpi.acr_claimed(pop, start, end),
        "acr_pipeline": kpi.acr_pipeline(ahead),
        "nodes_planned": kpi.nodes_planned(ahead),
    }


#: Which report shows the "Nodes Deployment Planned" tile.  The EOS programme
#: reports the deployment still to come; the other motions do not.
def shows_nodes_planned(spec: "ReportSpec") -> bool:
    return spec.key == "eos"


def eos_untagged_accounts(fact: pd.DataFrame) -> int:
    """Accounts in EOS scope by migration path with no generation tag on any wave.

    They are outside every EOS report (EOS is reported by generation), so the
    number is worth stating wherever an EOS report is thinner than a reader
    expects — an empty report that does not say why is a dead end.
    """
    untagged = segments.population(fact, segments.CAT_EOS_UNCLASSIFIED)
    return 0 if untagged.empty else int(segments.tpid_key(untagged).nunique())


#: What the blocked-accounts section is called, everywhere it appears.  Named
#: for what the reader is looking at — accounts that have stopped moving — not
#: for the reporting mechanism that leaves them out.
BLOCKED_TITLE = "Blocked, deferred & cancelled accounts"

BLOCKED_NOTE = (
    "Every account that is neither On-Track nor Completed, grouped by why. The "
    "blocking Current States — Blocked, Blocked - Account team, Blocked - "
    "Customer, Blocked - Partner / ISD, Waiting action on follow up date — with "
    "Deferred By Customer and Cancelled / Archived broken out by Migration "
    "Status, since those are decisions rather than blockages. None of them is "
    "in any metric above, and none of those metrics is in here, so the two add "
    "up to the report's accounts. Status Summary carries the programme's own "
    "note on each one."
)


#: Where an account in each state is reported, so the reconciliation says what
#: to do about a row rather than only naming it.
_STATE_HOME = {
    kpi.STATE_ON_TRACK: "Current pipeline (charted above)",
    kpi.STATE_COMPLETED: "Current pipeline (charted above)",
}


#: The order states read across the generation grid: the three a review asks
#: about first, then whatever else the file contains.
#: The total row of the generation grid — both generations together.
ALL_EOS_ROW = "All EOS"

GENERATION_STATE_ORDER = (kpi.STATE_ON_TRACK, kpi.STATE_COMPLETED,
                          kpi.STATE_BLOCKED, kpi.STATE_DEFERRED,
                          kpi.STATE_CANCELLED, kpi.STATE_OTHER)


def generation_status(pop: pd.DataFrame, waves: kpi.WaveIndex
                      ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Accounts by generation and state, at account grain.

    Generation down the side, state across the top — On-Track, Completed and
    Blocked first, because those are the three a review asks about, then any
    other state the file contains.  **Every** state is here on purpose: each
    account holds exactly one, so a generation's row adds up to the accounts in
    that generation and the grid reconciles with the report's own count rather
    than leaving a reader to wonder where the rest went.

    Returns ``(grid, rows)`` — the crosstab and the accounts behind it, each
    carrying ``_generation`` and ``state`` so a cell can open its own records.
    """
    _summary, rows = kpi.by_state(pop, lasts=waves.last, only=None)
    if rows.empty or "generation" not in rows.columns:
        return pd.DataFrame(), rows
    rows = rows.assign(_generation=clean(rows["generation"]))
    grid = pd.crosstab(rows["_generation"], rows["state"])
    order = ([s for s in GENERATION_STATE_ORDER if s in grid.columns]
             + [s for s in grid.columns if s not in GENERATION_STATE_ORDER])
    grid = grid[order]
    # The programme as a whole, on top of its generations: the question is
    # usually "how is EOS doing" before it is "how is Gen-2 doing", and a total
    # row means the reader adds nothing up by hand.
    grid.loc[ALL_EOS_ROW] = grid.sum()
    return grid, rows


def reconciliation(pop: pd.DataFrame, waves: kpi.WaveIndex) -> tuple[pd.DataFrame, int]:
    """Every account in the report, by state, with where each one is reported.

    The answer to "the charts show 32 of my 36 accounts — where are the other
    four?".  Each account resolves to exactly one state, so these rows sum to
    the report's own account count; what varies is **where** a state is
    reported — the two reported states above, and everything else in the
    blocked, deferred & cancelled section.

    Returns ``(rows, accounts)`` — the table, and the total it sums to.
    """
    lasts = waves.last
    if pop.empty or lasts.empty:
        return pd.DataFrame(columns=["State", "Accounts", "ACR", "Reported in"]), 0
    states = kpi.account_state(pop, lasts)
    frame = lasts.assign(_state=states,
                         _acr=pd.to_numeric(lasts.get("total_acr"), errors="coerce"))
    _summary, blocked = kpi.blocked_accounts(pop, lasts=lasts)
    in_section = set(blocked["tpid_key"]) if not blocked.empty else set()

    rows = []
    order = (kpi.STATE_ON_TRACK, kpi.STATE_COMPLETED, kpi.STATE_BLOCKED,
             kpi.STATE_OTHER, kpi.STATE_DEFERRED, kpi.STATE_CANCELLED)
    for state in order:
        part = frame[frame["_state"] == state]
        if part.empty:
            continue
        shown = int(part["tpid_key"].isin(in_section).sum())
        where = _STATE_HOME.get(state, "Not reported")
        if state not in _STATE_HOME:
            where = (BLOCKED_TITLE if shown == len(part) else
                     f"{BLOCKED_TITLE} ({fmt_int(shown)} of {fmt_int(len(part))})")
        rows.append({"State": state,
                     "Accounts": int(part["tpid_key"].nunique()),
                     "ACR": float(part["_acr"].sum()),
                     "Reported in": where})
    return pd.DataFrame(rows), int(frame["tpid_key"].nunique())


def blocked_tables(pop: pd.DataFrame, waves: kpi.WaveIndex) -> dict:
    """Everything the blocked-accounts section reports, built once for both renderers.

    The narrow cut (:func:`kpi.blocked_accounts`): accounts whose latest wave
    reads one of the blocking Current States and whose account state is neither
    reported (On-Track, Completed) nor closed out (Cancelled, Deferred).  The
    Current State *is* the reason, so it is the breakdown; the Status Summary
    column in the rows is the sentence behind it.

    Returns the summary, the WW Region cross-tab, the wave profile, the rows and
    the two totals; a caller renders whichever of them the data supports.
    """
    summary, rows = kpi.blocked_accounts(pop, lasts=waves.last)
    if rows.empty:
        return {"summary": summary, "rows": rows, "region": pd.DataFrame(),
                "waves": pd.DataFrame(), "acr": 0.0, "accounts": 0,
                "wave_count": 0}
    region = pd.DataFrame()
    if "region_geo" in rows.columns:
        region = pd.crosstab(clean(rows["region_geo"]), rows["blocked_state"])
    return {
        "summary": summary,
        "rows": rows,
        "region": region,
        "waves": kpi.wave_profile(pop, rows),
        "acr": float(pd.to_numeric(rows.get("total_acr"), errors="coerce").sum()),
        "accounts": int(rows["tpid_key"].nunique()),
        # Every wave those accounts own, not just the latest one each: an
        # account blocked on its fifth wave has five waves behind it.
        "wave_count": int(pop["tpid_key"].isin(rows["tpid_key"]).sum()),
    }


def _insight_lines(pop: pd.DataFrame, ss, limit: int = 14) -> list:
    out = []
    for item in insights_mod.generate_insights(pop)[:limit]:
        colour = kit.SEV_COLOR.get(item.severity, kit.PRIMARY)
        out.append(Paragraph(
            f'<font color="#{colour.hexval()[2:]}">&#9632;</font> '
            f'<b>{_esc(item.title)}.</b> {_strip(item.detail)}', ss["Body2"]))
        out.append(kit.spacer(0.1))
    return out


# --------------------------------------------------------------------------- #
# Trends — one definition, both renderers
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Trend:
    """One monthly measure: what it is called, its table, and its records.

    The four measures the Trend Analysis pages chart, assembled once here so the
    PDF and the HTML report cannot end up carrying different trends — or the
    same trend under two names.
    """
    key: str
    title: str
    value_col: str
    currency: bool
    table: pd.DataFrame
    rows: pd.DataFrame
    #: Which record date places a row in a month, for the fiscal-year split.
    date_col: str


def unit_noun(spec: "ReportSpec") -> str:
    """What a report calls the Total Cores column.

    The AVS motions deploy **Nodes**; only the "(From AVS)" motion moves
    **Cores** to Azure-native services.  One noun per report, decided here and
    used by both renderers' tiles and trend titles, so the two cannot disagree.
    """
    return "Cores" if spec.key == "native" else "Nodes"


def trends(pop: pd.DataFrame, waves: kpi.WaveIndex, start, end,
           spec: "ReportSpec", noun: str = "") -> list[Trend]:
    """Every month-over-month measure a report carries, in reporting order.

    ``noun`` overrides what the Total Cores column is called; left out, it is
    :func:`unit_noun`, which is what both renderers pass anyway.
    """
    noun = noun or unit_noun(spec)
    noms, nom_rows = kpi.monthly_unique_tpids(pop, "approval_date", start, end,
                                              waves=waves)
    acr, acr_rows = kpi.monthly_acr_claimed(pop, start, end)
    hosts, host_rows = kpi.monthly_hosts(pop, start, end)
    done, done_rows = kpi.monthly_migrations_completed(pop, start, end,
                                                       lasts=waves.last)
    return [
        Trend("nominations", "Nominations per month (unique TPIDs)",
              "Nominations", False, noms, nom_rows, "approval_date"),
        Trend("acr", "ACR claimed per month", "ACR Claimed", True, acr, acr_rows,
              "actual_end_date"),
        Trend("hosts", f"{spec.unit_label} per month (Total {noun})",
              "Hosts", False, hosts, host_rows, "actual_end_date"),
        Trend("completed", "Migrations completed per month (unique TPIDs)",
              "Migrations Completed", False, done, done_rows, "actual_end_date"),
    ]


def fiscal_year_split(trend: Trend, fy_start_month: int = FY_START_MONTH
                      ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """The same measure re-cut as one series per fiscal year, plus its grid.

    The "fiscal years side by side" view the Trend Analysis pages draw: the
    years laid over a shared Jul → Jun axis, where a single continuous line only
    ever gets longer.  Returns ``(split, grid)`` — long-form rows for the chart,
    and months down / fiscal years across with a Total row for the table.

    Every one of the twelve months is a row even when nothing happened in it: a
    quiet month is itself the finding, and dropping the row shifts the ones
    below it so the table stops lining up against the chart.
    """
    split = kpi.split_by_fiscal_year(trend.table, trend.value_col, fy_start_month)
    if split.empty:
        return split, pd.DataFrame()
    order = metrics.fiscal_month_order(fy_start_month)
    grid = split.pivot_table(index="fy_month", columns="fy",
                             values=trend.value_col, aggfunc="sum")
    grid = grid.reindex(order).fillna(0)
    grid.loc["Total"] = grid.sum()
    out = grid.reset_index().rename(columns={"fy_month": "Month"})
    out.columns.name = None
    fmt = fmt_currency if trend.currency else fmt_int
    for col in out.columns[1:]:
        out[col] = out[col].map(fmt)
    return split, out


#: What the fiscal-year comparison is called, and why it ignores the period.
FISCAL_YEARS_TITLE = "Fiscal years side by side"
FISCAL_YEARS_NOTE = (
    "The same four measures again, each fiscal year its own series over a "
    "shared July → June axis, so the years read against one another rather "
    "than stretching into one ever-longer line. **Read over the whole dataset, "
    "never the reporting period**: a year-on-year comparison cut to one month "
    "would have nothing to compare. Every month is shown, including the empty "
    "ones, and each series is the fiscal year it is labelled with."
)


def top_accounts_title(limit: int = kpi.TOP_ACCOUNTS) -> str:
    return f"Top {limit} accounts by ACR"


#: Which reports carry the largest-accounts cut.  The two broad motions: the
#: EOS report's generations would repeat much of the same list, and its own
#: question is which generation, not which account.
TOP_ACCOUNT_REPORTS = ("avs", "native")

TOP_ACCOUNTS_NOTE = (
    "The accounts this category's money sits in, largest first. Total ACR is "
    "summed across **every wave** of an account — an account with waves of 10M, "
    "15M and 20M is a 45M account — so the order is the account-level one the "
    "reconciliation and the account records both use. Accounts with no ACR are "
    "left out rather than listed as zeroes. **Read over the whole dataset, not "
    "the reporting period**: the question is where the money is, which a window "
    "would answer only for the window."
)


def shows_top_accounts(spec: "ReportSpec") -> bool:
    return spec.key in TOP_ACCOUNT_REPORTS


def top_accounts(pop: pd.DataFrame, waves: kpi.WaveIndex,
                 limit: int = kpi.TOP_ACCOUNTS) -> tuple[pd.DataFrame, pd.DataFrame]:
    """The largest accounts by ACR, and the account rows behind them."""
    return kpi.top_accounts_by_acr(pop, limit, approvals=waves.approval,
                                   lasts=waves.last)


def top_accounts_line(summary: pd.DataFrame, pop: pd.DataFrame) -> str:
    """One sentence stating what share of the category these accounts carry."""
    if summary.empty:
        return ""
    total = float(pd.to_numeric(pop.get("total_acr"), errors="coerce").sum())
    shown = float(summary["acr"].sum())
    share = f" — {shown / total:.0%} of the category's ACR" if total else ""
    return (f"These {fmt_int(len(summary))} accounts carry "
            f"{fmt_currency(shown)}{share}.")


def this_fiscal_year(as_of, start, end) -> tuple[tuple | None, str]:
    """The fiscal year *as_of* sits in — unless that is already the window.

    Mirrors the dashboards' Executive Summary, which puts a This-FY row above
    the selected period whenever the two differ, so a month's numbers keep the
    year they sit in.  Returns ``(None, "")`` only when the report already
    covers exactly This FY.

    **An unbounded period is not This FY.**  "All time" resolves to no window at
    all, and reading that as "nothing to compare against" is what used to drop
    the row from a report while the dashboard — which decides on the preset, not
    on the dates — still showed it.  All time spans several fiscal years, so the
    year you are in is exactly the context it loses.
    """
    span = metrics.date_preset_range(as_of, "This FY", FY_START_MONTH)
    if not span:
        return None, ""
    fy_start, fy_end = pd.Timestamp(span[0]).date(), pd.Timestamp(span[1]).date()
    same = (start is not None and end is not None
            and pd.Timestamp(start).date() == fy_start
            and pd.Timestamp(end).date() == fy_end)
    if same:
        return None, ""
    label = (f"This FY ({metrics.fiscal_year_label(fy_start, FY_START_MONTH)}) — "
             f"{fy_start:%d %b %Y} → {fy_end:%d %b %Y}")
    return (fy_start, fy_end), label


def trend_table(table: pd.DataFrame, value_col: str, currency: bool) -> pd.DataFrame:
    """A monthly trend as printable rows — Month, the measure, Cumulative last."""
    out = table.drop(columns=["month"]).rename(columns={"period": "Month"})
    values = [c for c in out.columns if c not in ("Month", "Cumulative")]
    out = out[["Month", *values, "Cumulative"]]
    fmt = fmt_currency if currency else fmt_int
    for col in [*values, "Cumulative"]:
        out[col] = out[col].map(fmt)
    if values and value_col != values[0]:
        out = out.rename(columns={values[0]: value_col})
    return out


def region_status(lasts: pd.DataFrame
                  ) -> tuple[pd.DataFrame, pd.DataFrame, list[tuple[str, str]]]:
    """Status × WW Region and WW Region × status, at account grain (latest wave).

    Restricted to the stages the dashboards break down by — the four in-flight
    ones plus Completed — so the PDF and the screen cannot disagree.  Stages are
    labelled by their code ("Stage 4"); the third return value is the legend
    that decodes them, since the full names are too long for an axis.
    """
    if lasts.empty or "region_geo" not in lasts.columns:
        return pd.DataFrame(), pd.DataFrame(), []
    lasts = lasts[kpi.reported_stages(lasts)]
    if lasts.empty:
        return pd.DataFrame(), pd.DataFrame(), []
    stages, legend = kpi.stage_labels(lasts)
    rows = lasts.assign(_status=stages, _region=clean(lasts["region_geo"]))
    return (pd.crosstab(rows["_status"], rows["_region"]),
            pd.crosstab(rows["_region"], rows["_status"]), legend)


# --------------------------------------------------------------------------- #
# Primary report
# --------------------------------------------------------------------------- #
def _population_line(spec: ReportSpec, pop: pd.DataFrame, ss) -> Paragraph:
    tpids = segments.tpid_key(pop).nunique() if not pop.empty else 0
    bits = [f"<b>{fmt_int(tpids)}</b> accounts (TPIDs)",
            f"<b>{fmt_int(len(pop))}</b> nomination waves"]
    if spec.key == "eos" and not pop.empty:
        split = (pop.drop_duplicates("tpid_key")["generation"].value_counts()
                 .rename({segments.GEN_UNCLASSIFIED: "no generation tag"}))
        bits += [f"<b>{fmt_int(v)}</b> {_esc(k)}" for k, v in split.items()]
    return Paragraph(" &nbsp;·&nbsp; ".join(bits), ss["Muted"])


def _summary_block(spec: ReportSpec, pop: pd.DataFrame, waves: kpi.WaveIndex,
                   start, end, ss, period_label: str,
                   all_time: pd.DataFrame | None = None,
                   fy_window=None, fy_label: str = "") -> list:
    """The headline tiles, over a This-FY row when the period is something else.

    The same two-row rule the dashboards and the HTML report use: selecting
    "This Month" answers how the month went but loses the year it sits in, so
    anything other than This FY gets the fiscal year above it.  Each row is
    measured over its own window — never one derived from the other.
    """
    out = [Paragraph("Executive summary", ss["H2"])]
    if fy_window and fy_window[0] is not None:
        out += [Paragraph("Two periods: the fiscal year you are in, then the "
                          "period selected for this report. Each row is measured "
                          "over its own window — except ACR Pipeline and any "
                          "planned deployment, which are read over the whole "
                          "dataset and so read the same on both rows.",
                          ss["Muted"]),
                kit.spacer(0.2),
                Paragraph(_esc(fy_label), ss["H3"]),
                kit.spacer(0.1),
                _summary_cards(spec, headline(pop, waves, fy_window[0],
                                              fy_window[1], all_time), ss),
                kit.spacer(0.3),
                Paragraph(_esc(period_label), ss["H3"]),
                kit.spacer(0.1)]
    else:
        out += [Paragraph(f"Reporting period: {_esc(period_label)}. On-Track is a "
                          "snapshot of where things stand now; <b>ACR Pipeline and "
                          "Nodes Deployment Planned are read over the whole "
                          "dataset</b> — work nominated before the window is still "
                          "work still to do. No date window narrows any of the "
                          "three.", ss["Muted"]),
                kit.spacer(0.2)]
    out.append(_summary_cards(spec, headline(pop, waves, start, end, all_time), ss))
    return out


def _summary_cards(spec: ReportSpec, metrics_: dict, ss):
    tiles = [
        ("New Engagements", fmt_int(metrics_["engagements"].value),
         "unique TPIDs, Wave-1 approval"),
        ("Migrations Completed", fmt_int(metrics_["completed"].value),
         "latest wave completed, no wave on track"),
        (spec.unit_label, fmt_int(metrics_["hosts"].value), "sum of Total Cores"),
        ("On-Track Accounts", fmt_int(metrics_["on_track"].value),
         "any wave on track — not period-bound"),
        ("ACR Claimed", fmt_currency(metrics_["acr"].value),
         "waves ended in the period"),
        ("ACR Pipeline", fmt_currency(metrics_["acr_pipeline"].value),
         "eligible waves, all time"),
    ]
    if shows_nodes_planned(spec):
        tiles.append(("Nodes Deployment Planned",
                      fmt_int(metrics_["nodes_planned"].value),
                      "Total Cores, eligible waves, all time"))
    return kit.kpi_cards(tiles, ss, per_row=3)


def _trend_block(pop: pd.DataFrame, waves: kpi.WaveIndex, start, end,
                 spec: ReportSpec, ss) -> list:
    """Every month-over-month measure, each with the numbers under its chart.

    The same four :func:`trends` builds for the HTML report, drawn with the same
    tables — the two reports are one report in two renderings, so a measure the
    screen shows is a measure this prints.
    """
    out = [Paragraph("Trends — month over month", ss["H2"]),
           Paragraph("Each measure over the reporting period, with its running "
                     "total tabulated beneath it.", ss["Muted"]), kit.spacer(0.15)]
    drawn = 0
    for trend in trends(pop, waves, start, end, spec, unit_noun(spec)):
        if trend.table.empty:
            continue
        drawn += 1
        colour = "#5C2E91" if trend.currency else "#0F6CBD"
        frame = trend_table(trend.table, trend.value_col, trend.currency)
        col = min(kit.CONTENT_WIDTH[kit.PORTRAIT] / 3, 5.5 * cm)
        out.append(KeepTogether([
            Paragraph(trend.title, ss["H3"]),
            kit.image(pc.line_png(trend.table, "period", trend.value_col,
                                  area=not trend.currency, color=colour,
                                  currency=trend.currency, height_px=250),
                      width_cm=16.6),
            kit.spacer(0.12),
            kit.df_table(frame, ss, col_widths=[col] * 3, align_right=[1, 2],
                         font_size=8),
        ]))
        out.append(kit.spacer(0.2))
    if not drawn:
        out.append(Paragraph("No activity dated inside the reporting period.",
                             ss["Muted"]))
    return out


def _fiscal_year_block(pop: pd.DataFrame, waves: kpi.WaveIndex,
                       spec: ReportSpec, ss) -> list:
    """The same measures again, fiscal year against fiscal year.

    ``pop`` is the population the reporting period never narrowed: a year-on-year
    comparison cut to one month has nothing to compare, so this reads the whole
    dataset while every other filter still binds.
    """
    out = [Paragraph(FISCAL_YEARS_TITLE, ss["H2"]),
           Paragraph(_strip(FISCAL_YEARS_NOTE), ss["Muted"]), kit.spacer(0.15)]
    drawn = 0
    for trend in trends(pop, waves, None, None, spec, unit_noun(spec)):
        split, grid = fiscal_year_split(trend)
        if split.empty or grid.empty:
            continue
        drawn += 1
        years = [str(y) for y in sorted(split["fy"].unique())]
        wide = split.pivot_table(index="fy_month", columns="fy",
                                 values=trend.value_col, aggfunc="sum")
        wide = wide.reindex(metrics.fiscal_month_order(FY_START_MONTH)).fillna(0)
        wide = wide.reset_index().rename(columns={"fy_month": "month"})
        wide.columns = [str(c) for c in wide.columns]
        widths = _grid_widths(grid, kit.CONTENT_WIDTH[kit.PORTRAIT])
        out.append(KeepTogether([
            Paragraph(trend.title, ss["H3"]),
            kit.image(pc.fy_lines_png(wide, "month", years,
                                      currency=trend.currency, height_px=250),
                      width_cm=16.6),
            kit.spacer(0.12),
            kit.df_table(grid, ss, col_widths=widths,
                         align_right=list(range(1, len(grid.columns))),
                         font_size=8),
        ]))
        out.append(kit.spacer(0.2))
    if not drawn:
        out.append(Paragraph("Nothing in this report is dated, so there is no "
                             "fiscal year to compare.", ss["Muted"]))
    return out


def _grid_widths(frame: pd.DataFrame, width: float) -> list[float]:
    """Column widths for a month × fiscal-year grid, first column wider."""
    others = max(len(frame.columns) - 1, 1)
    first = min(4.0 * cm, width * 0.3)
    rest = min((width - first) / others, 4.0 * cm)
    return [first] + [rest] * others


def _top_accounts_block(pop: pd.DataFrame, waves: kpi.WaveIndex,
                        ss) -> list:
    """The ten accounts carrying the most ACR, charted and listed."""
    summary, rows = top_accounts(pop, waves)
    out = [Paragraph(top_accounts_title(), ss["H2"]),
           Paragraph(_strip(TOP_ACCOUNTS_NOTE), ss["Muted"]), kit.spacer(0.15)]
    if summary.empty:
        out.append(Paragraph("No account in this category carries any ACR.",
                             ss["Muted"]))
        return out
    out.append(Paragraph(_esc(top_accounts_line(summary, pop)), ss["Body2"]))
    out.append(kit.spacer(0.12))
    out.append(KeepTogether([
        kit.image(pc.bar_png(summary, "category", "acr", horizontal=True,
                             currency=True, height_px=300), width_cm=16.6)]))
    printable = summary.rename(columns={"category": "Account", "acr": "Total ACR",
                                        "count": "Waves"})
    printable["Total ACR"] = printable["Total ACR"].map(fmt_currency)
    printable["Waves"] = printable["Waves"].map(fmt_int)
    out += [kit.spacer(0.2),
            kit.df_table(printable, ss, col_widths=[9.6 * cm, 3.5 * cm, 2.5 * cm],
                         align_right=[1, 2], font_size=8)]
    return out


def _matrix_block(ctx, pop: pd.DataFrame, ss) -> list:
    """The EOS programme's month-by-month grid, as the dashboard shows it.

    ``pop`` is deliberately the population the reporting period never narrowed:
    the grid runs from a fixed July start to the as-of date whatever window the
    rest of the report covers, because a month with no nominations is itself the
    number being reported.
    """
    start = metrics.named_fiscal_year_start(EOS_MATRIX_START_FY, FY_START_MONTH)
    out = [Paragraph("Monthly programme matrix", ss["H2"]),
           Paragraph(f"From {start:%b %Y} to {pd.Timestamp(ctx.as_of):%b %Y}, "
                     "every month included, each fiscal year closing with its "
                     "own total column — the whole programme, not narrowed by "
                     "the reporting period the rest of this report uses. Blocks "
                     "are the generation each account is refreshing on to; all "
                     "EOS accounts are coming from Gen-1 hardware. Migration "
                     "start and migration end are the manual EOS tracking "
                     "sheet's own dates wherever it covers an account, and "
                     "otherwise the export's. Engagement end repeats migration "
                     "end, the closest the export comes to it.", ss["Muted"]),
           kit.spacer(0.2)]
    width = kit.CONTENT_WIDTH[kit.PORTRAIT]
    for generation, title in ((segments.GEN_1, "Gen1 to Gen1"),
                              (segments.GEN_2, "Gen1 to Gen2")):
        block = pop[pop["generation"] == generation] if not pop.empty else pop
        accounts = segments.tpid_key(block).nunique() if not block.empty else 0
        months = kpi.matrix_month_span(block, start, ctx.as_of)
        grid = kpi.monthly_matrix(block, months, fy_start_month=FY_START_MONTH)
        # A month per column runs off a portrait page long before the matrix
        # does, so the grid prints on its own landscape spread.
        out += [Paragraph(f"{_esc(title)} — {fmt_int(accounts)} account(s), "
                          f"{fmt_int(len(block))} nomination wave(s)", ss["H3"]),
                kit.spacer(0.1),
                *_matrix_grid(grid, ss, width), kit.spacer(0.25)]
    return out


def _matrix_grid(grid: pd.DataFrame, ss, width: float) -> list:
    """The matrix as a printable table, sized so every month still fits."""
    if grid.empty:
        return [Paragraph("No months to report.", ss["Muted"])]
    first = min(4.6 * cm, width * 0.3)
    others = max(len(grid.columns) - 1, 1)
    rest = (width - first) / others
    return [kit.df_table(grid, ss, col_widths=[first] + [rest] * others,
                         align_right=list(range(1, len(grid.columns))),
                         font_size=5.6)]


def _pipeline_block(pop: pd.DataFrame, waves: kpi.WaveIndex, ss) -> list:
    states, _ = kpi.by_state(pop, lasts=waves.last)
    stages, _ = kpi.on_track_by_stage(pop, lasts=waves.last)
    out = [Paragraph("Current pipeline", ss["H2"]),
           Paragraph("Every account read across all of its waves, whatever its "
                     "nomination date. On-Track and Completed only — accounts "
                     "that have stopped are reported separately, under "
                     f"{BLOCKED_TITLE}.", ss["Muted"]), kit.spacer(0.15)]
    if states.empty:
        out.append(Paragraph("No On-Track or Completed accounts to report.",
                             ss["Muted"]))
    else:
        out.append(KeepTogether([
            Paragraph("Accounts by state", ss["H3"]),
            kit.image(pc.donut_png(states, "category", "count", height_px=260),
                      width_cm=16.6)]))
    if not stages.empty:
        out.append(kit.spacer(0.2))
        out.append(KeepTogether([
            Paragraph("On-track accounts by stage", ss["H3"]),
            kit.image(pc.bar_png(stages, "category", "count", horizontal=True,
                                 height_px=250), width_cm=16.6)]))
    out += _reconciliation_block(pop, waves, ss)
    return out


def _reconciliation_block(pop: pd.DataFrame, waves: kpi.WaveIndex, ss) -> list:
    """Where every account sits — so the charts above can be reconciled."""
    rows, accounts = reconciliation(pop, waves)
    if rows.empty:
        return []
    printable = rows.copy()
    printable["ACR"] = printable["ACR"].map(fmt_currency)
    printable["Accounts"] = printable["Accounts"].map(fmt_int)
    return [kit.spacer(0.25),
            KeepTogether([
                Paragraph("Where every account sits", ss["H3"]),
                Paragraph(f"All <b>{fmt_int(accounts)}</b> accounts in this report, "
                          "by state. Each account is in exactly one row, so these "
                          "add up — the charts above show the first two rows, and "
                          "the rest are reported where this says.", ss["Muted"]),
                kit.spacer(0.12),
                kit.df_table(printable, ss,
                             col_widths=[3.2 * cm, 2.0 * cm, 2.4 * cm, 9.0 * cm],
                             align_right=[1, 2], font_size=8)])]


def _regional_block(waves: kpi.WaveIndex, ss) -> list:
    """The regional cut as **one** chart.

    The stacked bar and the heatmap carried the same numbers — region against
    stage — so the bar has gone and the heatmap stands alone: it is the one that
    reads every region and every stage at once without a legend to decode.
    """
    pivot, heat, legend = region_status(waves.last)
    if pivot.empty:
        return []
    key = ("Stages: " + "; ".join(f"{short} = {name}" for short, name in legend)
           if legend else "")
    return [Paragraph("Regional breakdown", ss["H2"]),
            Paragraph("Accounts at their latest wave, by WW Region and migration "
                      "status — one row per TPID, so this agrees with the state "
                      "chart above rather than counting waves." +
                      (f" {_esc(key)}" if key else ""), ss["Muted"]),
            kit.spacer(0.15),
            KeepTogether([Paragraph("WW Region × status heatmap", ss["H3"]),
                          kit.image(pc.heatmap_png(heat, height_px=300),
                                    width_cm=16.6)])]


def _blocked_block(pop: pd.DataFrame, waves: kpi.WaveIndex, ss,
                   max_rows: int = 60) -> list:
    """Accounts that have stopped — blocked, or waiting on a follow-up.

    A section of its own, never folded into the metrics above it: an account
    nobody is moving is neither delivering nor delivered, so counting it in the
    On-Track/Completed story would misstate both.  It is also where a programme
    review spends its time, so the accounts are listed by name with the
    programme's own Status Summary against each — the reason, in the words
    whoever is working the account wrote.
    """
    tables = blocked_tables(pop, waves)
    out = [Paragraph(BLOCKED_TITLE, ss["H2"]),
           Paragraph(_esc(BLOCKED_NOTE), ss["Muted"]), kit.spacer(0.15)]
    if tables["rows"].empty:
        out.append(Paragraph("Nothing has stopped — every account here is "
                             "On-Track or Completed.", ss["Body2"]))
        return out

    out += [kit.kpi_cards([
        ("Stopped Accounts", fmt_int(tables["accounts"]), "not in any metric above"),
        ("ACR Held Up", fmt_currency(tables["acr"]), "sum over those accounts"),
        ("Waves Behind Them", fmt_int(tables["wave_count"]),
         "every wave of those accounts"),
    ], ss, per_row=3), kit.spacer(0.25)]

    states = tables["summary"].rename(columns={"category": "Reason",
                                               "count": "Accounts", "acr": "ACR"})
    states["ACR"] = states["ACR"].map(fmt_currency)
    states["Accounts"] = states["Accounts"].map(fmt_int)
    out.append(KeepTogether([
        Paragraph("By reason", ss["H3"]),
        kit.df_table(states, ss, col_widths=[8 * cm, 3 * cm, 3.5 * cm],
                     align_right=[1, 2], font_size=8)]))

    if not tables["region"].empty:
        out += [kit.spacer(0.25),
                KeepTogether([Paragraph("By WW Region", ss["H3"]),
                              kit.image(pc.heatmap_png(tables["region"],
                                                       height_px=260),
                                        width_cm=16.6)])]
    if not tables["waves"].empty:
        profile = tables["waves"].rename(columns={"category": "Waves",
                                                  "count": "Accounts"})
        profile["Accounts"] = profile["Accounts"].map(fmt_int)
        out += [kit.spacer(0.25),
                KeepTogether([Paragraph("Waves behind these accounts", ss["H3"]),
                              kit.df_table(profile, ss,
                                           col_widths=[11 * cm, 3.5 * cm],
                                           align_right=[1], font_size=8)])]
    out += [kit.spacer(0.25), *_blocked_accounts_table(tables["rows"], ss, max_rows)]
    return out


#: The blocked list, as (source column, header, relative width).  Status Summary
#: takes the space three other columns would, because it is the column that
#: answers the question the section is asking.
BLOCKED_COLUMNS = [
    ("tpid", "TPID", 1.6),
    ("customer_name", "Customer", 3.2),
    ("region_geo", "WW Region", 2.0),
    ("blocked_state", "Reason", 2.6),
    ("assigned_pm", "Factory PM", 2.4),
    ("total_acr", "ACR", 1.6),
    ("status_summary", "Status Summary", 7.0),
]


#: How much of a Status Summary the printed table carries before it is cut.
BLOCKED_SUMMARY_CHARS = 320


def _shorten(value, limit: int = BLOCKED_SUMMARY_CHARS) -> str:
    """A long note cut at a word boundary, marked so the cut is visible."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = " ".join(str(value).split())
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + " …"


def _blocked_accounts_table(rows: pd.DataFrame, ss, max_rows: int) -> list:
    """The blocked accounts by name, each with the note explaining why."""
    if rows.empty:
        return []
    ordered = rows.assign(
        _acr=pd.to_numeric(rows.get("total_acr"), errors="coerce").fillna(0)
    ).sort_values(["blocked_state", "_acr"], ascending=[True, False])
    shown = ordered.head(max_rows).copy()
    # A Status Summary runs to whatever length whoever wrote it needed; on a
    # fixed page one of them can take the room ten accounts would.  The HTML
    # report carries them whole — this is the printed extract.
    if "status_summary" in shown.columns:
        shown["status_summary"] = shown["status_summary"].map(_shorten)
    frame = format_accounts(shown, BLOCKED_COLUMNS)
    weights = [w for _, _, w in BLOCKED_COLUMNS]
    available = kit.CONTENT_WIDTH[kit.PORTRAIT]
    widths = [available * w / sum(weights) for w in weights]
    out = [Paragraph("The accounts, and why", ss["H3"])]
    if len(ordered) > max_rows:
        out.append(Paragraph(
            f"Showing the {fmt_int(max_rows)} largest of {fmt_int(len(ordered))} "
            f"by ACR, grouped by state.", ss["Muted"]))
    out.append(kit.df_table(frame, ss, col_widths=widths, align_right=[5],
                            font_size=6.5))
    return out


def _offering_block(pop: pd.DataFrame, ss) -> list:
    """The AVS → Azure Native cut, on all three of its own columns.

    Factory Offering and Primary Migration Path are different columns and are
    charted separately — the offering is which factory delivers the work, the
    path is what moves where.
    """
    offerings = labelled(pop, "factory_offering")
    paths = labelled(pop, "migration_path")
    targets = labelled(pop, "azure_target")
    if offerings.empty and paths.empty and targets.empty:
        return []
    out = [Paragraph("By offering, path & target", ss["H2"]),
           Paragraph("Three separate columns: the <b>Factory Offering</b> that "
                     "delivers the work, the <b>Primary Migration Path</b> that "
                     "says what moves where, and the Azure-native service the "
                     "path lands on. Wave-level counts over every nomination in "
                     "the report — not narrowed by the reporting period.",
                     ss["Muted"]), kit.spacer(0.15)]
    if not offerings.empty:
        out.append(KeepTogether([
            Paragraph("Nominations by Factory Offering", ss["H3"]),
            kit.image(pc.bar_png(offerings.head(12), "category", "count",
                                 horizontal=True, height_px=240), width_cm=16.6)]))
        out.append(kit.spacer(0.2))
    if not paths.empty:
        out.append(KeepTogether([
            Paragraph("Nominations by Primary Migration Path", ss["H3"]),
            kit.image(pc.bar_png(paths.head(12), "category", "count",
                                 horizontal=True, height_px=270), width_cm=16.6)]))
        out.append(kit.spacer(0.2))
    if not targets.empty:
        out.append(KeepTogether([
            Paragraph("Azure-native targets", ss["H3"]),
            kit.image(pc.donut_png(targets, "category", "count", height_px=260),
                      width_cm=16.6)]))
    return out


def _generation_block(fact: pd.DataFrame, spec: ReportSpec, start, end, ss) -> list:
    """Gen-1 and Gen-2 read against each other, and against the combined report.

    The two generation dashboards are subsets of EOS Migration (All); folding
    them in as a comparison keeps every metric they carry without repeating the
    whole report three times.
    """
    out = [Paragraph("Generation breakdown", ss["H2"]),
           Paragraph("Gen-1 and Gen-2 are subsets of the report above — an "
                     "\"AVS Migration - Gen1/Gen2\" tag on any wave sets the "
                     "generation. Accounts in scope by migration path with no tag "
                     "carry no generation and appear only in the combined total.",
                     ss["Muted"]), kit.spacer(0.2)]
    rows, monthly = [], {}
    for category in spec.breakdown:
        pop = segments.population(fact, category)
        label = segments.CATEGORY_LABELS[category]
        if pop.empty:
            rows.append([label, "0", "0", "0", "0", "0", fmt_currency(0)])
            continue
        waves = kpi.wave_index(pop)
        m = headline(pop, waves, start, end)
        rows.append([
            label,
            fmt_int(segments.tpid_key(pop).nunique()),
            fmt_int(m["engagements"].value),
            fmt_int(m["completed"].value),
            fmt_int(m["hosts"].value),
            fmt_int(m["on_track"].value),
            fmt_currency(m["acr"].value),
        ])
        trend, _ = kpi.monthly_unique_tpids(pop, "approval_date", start, end,
                                            waves=waves)
        if not trend.empty:
            monthly[label] = trend.set_index("period")["Nominations"]

    frame = pd.DataFrame(rows, columns=[
        "Generation", "Accounts", "New Engagements", "Completed",
        spec.unit_label.replace(" Migrated", ""), "On-Track", "ACR Claimed"])
    out.append(kit.df_table(
        frame, ss, col_widths=[4.4 * cm, 2.0 * cm, 2.7 * cm, 2.0 * cm, 1.9 * cm,
                               1.8 * cm, 2.6 * cm],
        align_right=[1, 2, 3, 4, 5, 6], font_size=8))

    # The report's own population, not the loop's: the grid cuts every account
    # in the report by generation, which is what makes its rows add up.
    whole = segments.population(fact, spec.category)
    grid, _rows = generation_status(whole, kpi.wave_index(whole))
    if not grid.empty:
        out += [kit.spacer(0.3),
                KeepTogether([
                    Paragraph("Accounts by generation and state", ss["H3"]),
                    Paragraph("One row per account, every state included — so a "
                              "generation's row adds up to its accounts and "
                              "nothing goes missing between the two.",
                              ss["Muted"]),
                    kit.spacer(0.12),
                    kit.image(pc.heatmap_png(grid, height_px=220), width_cm=16.6)]),
                kit.spacer(0.2),
                *_matrix_table(grid, "Generation", ss,
                               kit.CONTENT_WIDTH[kit.PORTRAIT])]

    if len(monthly) > 1:
        wide = pd.DataFrame(monthly).fillna(0).reset_index()
        wide = wide.rename(columns={"period": "month"})
        out += [kit.spacer(0.3),
                KeepTogether([
                    Paragraph("Nominations per month by generation", ss["H3"]),
                    kit.image(pc.grouped_bar_png(
                        wide, "month", [c for c in wide.columns if c != "month"],
                        height_px=270), width_cm=16.6)])]
    for category in spec.breakdown:
        out += _generation_pipeline(fact, category, ss)
    return out


def _generation_pipeline(fact: pd.DataFrame, category: str, ss) -> list:
    """One generation's current pipeline, as the numbers behind its dashboard."""
    pop = segments.population(fact, category)
    label = segments.CATEGORY_LABELS[category]
    if pop.empty:
        return [kit.spacer(0.25),
                Paragraph(f"{_esc(label)} — no nominations in scope.", ss["Muted"])]
    waves = kpi.wave_index(pop)
    states, _ = kpi.by_state(pop, lasts=waves.last)
    stages, _ = kpi.on_track_by_stage(pop, lasts=waves.last)
    block = [Paragraph(f"{_esc(label)} — current pipeline", ss["H3"])]
    if states.empty and stages.empty:
        block.append(Paragraph("No On-Track or Completed accounts to report.",
                               ss["Muted"]))
        return [kit.spacer(0.25), KeepTogether(block)]
    widths = [8 * cm, 3 * cm, 3.5 * cm]
    for frame, first_col in ((states, "State"), (stages, "Stage")):
        if frame.empty:
            continue
        printable = frame.rename(columns={"category": first_col, "count": "Accounts",
                                          "acr": "ACR"})
        printable["ACR"] = printable["ACR"].map(fmt_currency)
        printable["Accounts"] = printable["Accounts"].map(fmt_int)
        block += [kit.spacer(0.15),
                  kit.df_table(printable, ss, col_widths=widths, align_right=[1, 2],
                               font_size=8)]
    return [kit.spacer(0.25), KeepTogether(block)]


def _report_section(ctx, fact: pd.DataFrame, spec: ReportSpec, ss, start, end,
                    period_label: str, with_drilldown: bool,
                    sections: ReportSections,
                    all_time: pd.DataFrame | None = None,
                    fy_window=None, fy_label: str = "") -> list:
    """One report, section for section as the HTML report renders it.

    The two are one report in two renderings, so the order here is the order
    there: summary (over a This-FY row when the period is something else), the
    EOS programme matrix, the trends, the fiscal-year comparison, the largest
    accounts, the pipeline, the offering cut, the regional cut, the generations,
    the insights, and the accounts that have stopped last.
    """
    pop = segments.population(fact, spec.category)
    # The forward-looking tiles, the programme matrix and the fiscal-year
    # comparison all read the whole programme rather than the window.
    ahead = None if all_time is None else segments.population(all_time, spec.category)
    links = [("View drill-down →", f"dd_{spec.key}")] if with_drilldown else []
    links.append(("Contents", "toc"))

    story = [kit.Anchor(f"rpt_{spec.key}", spec.title, level=1),
             kit.nav_bar(ss, spec.title, links),
             kit.spacer(0.15),
             Paragraph(_esc(spec.blurb), ss["Body2"]),
             kit.spacer(0.1),
             _population_line(spec, pop, ss),
             kit.spacer(0.3)]
    if pop.empty:
        story.append(Paragraph("No nominations fall into this report for the "
                               "current filters.", ss["Body2"]))
        untagged = eos_untagged_accounts(fact) if spec.key == "eos" else 0
        if untagged:
            story += [kit.spacer(0.15), Paragraph(
                f"<b>{fmt_int(untagged)}</b> account(s) are in EOS scope through "
                f"their migration path but carry no \"AVS Migration - "
                f"Gen1/Gen2\" tag on any wave. EOS is reported by generation, so "
                f"they are not counted here; they are listed in the data "
                f"inconsistency review, and adding the tag at source brings them "
                f"into this report.", ss["Body2"])]
        if spec.breakdown:
            story += [kit.spacer(0.35), *_generation_block(fact, spec, start, end, ss)]
        story.append(kit.page_break())
        return story

    waves = kpi.wave_index(pop)
    # The whole-dataset population, for everything a reporting period must not
    # narrow; it falls back to the report's own population when the caller has
    # no period to drop.
    whole = pop if ahead is None else ahead
    whole_waves = waves if whole is pop else kpi.wave_index(whole)

    blocks = [_summary_block(spec, pop, waves, start, end, ss, period_label,
                             ahead, fy_window, fy_label)]
    if spec.key == "eos":
        blocks.append(_matrix_block(ctx, whole, ss))
    blocks.append(_trend_block(pop, waves, start, end, spec, ss))
    blocks.append(_fiscal_year_block(whole, whole_waves, spec, ss))
    if shows_top_accounts(spec):
        blocks.append(_top_accounts_block(whole, whole_waves, ss))
    blocks.append(_pipeline_block(pop, waves, ss))
    if spec.key == "native":
        blocks.append(_offering_block(pop, ss))
    blocks.append(_regional_block(waves, ss))
    if spec.breakdown:
        blocks.append(_generation_block(fact, spec, start, end, ss))
    for block in blocks:
        if block:
            story += [*block, kit.spacer(0.35)]
    if sections.insights:
        story += [Paragraph("Insights", ss["H2"]),
                  Paragraph("Derived from this report's own population by "
                            "deterministic rules — no model, no estimate: each "
                            "one states the figures it is read from.",
                            ss["Muted"]),
                  kit.spacer(0.15),
                  *_insight_lines(pop, ss), kit.spacer(0.35)]
    # Last, as in the HTML report: the accounts none of the above counts.
    if sections.blocked:
        story += [*_blocked_block(pop, waves, ss), kit.spacer(0.35)]
    story.append(kit.page_break())
    return story


# --------------------------------------------------------------------------- #
# Drill-down
# --------------------------------------------------------------------------- #
def account_rows(pop: pd.DataFrame, waves: kpi.WaveIndex,
                  include_generation: bool) -> tuple[pd.DataFrame, list, int]:
    """One printable row per account, plus the column layout and the total.

    Built through :func:`kpi.account_detail`, the same mixed-grain rules the
    dashboard's Detailed Data uses — latest wave for state, ACR summed across
    every wave — so the PDF and the screen cannot report different ACR for the
    same account.
    """
    detail = kpi.account_detail(pop, approvals=waves.approval, lasts=waves.last)
    if detail.empty:
        return pd.DataFrame(), [], 0
    wave_counts = pop.groupby("tpid_key").size()
    rows = detail.assign(_waves=detail["tpid_key"].map(wave_counts).fillna(1))
    rows["_acr_sort"] = pd.to_numeric(rows.get("total_acr"), errors="coerce").fillna(0)
    rows["_region_sort"] = clean(rows["region_geo"]) if "region_geo" in rows else "Unknown"
    rows = rows.sort_values(["_region_sort", "_acr_sort"], ascending=[True, False])

    layout = list(ACCOUNT_COLUMNS)
    if include_generation:
        layout.insert(3, GENERATION_COLUMN)
    return rows, layout, len(rows)


def format_accounts(rows: pd.DataFrame, layout: list, escape=None) -> pd.DataFrame:
    """Account rows as display strings, escaped for the target being rendered."""
    escape = _esc if escape is None else escape
    out = {}
    for source, header, _ in layout:
        if source == "total_acr":
            values = pd.to_numeric(rows.get(source), errors="coerce").map(
                lambda v: "" if pd.isna(v) else fmt_currency(v))
        elif source in ("total_cores", "_waves"):
            values = pd.to_numeric(rows.get(source), errors="coerce").map(
                lambda v: "" if pd.isna(v) else fmt_int(v))
        elif source in rows.columns:
            values = rows[source].map(escape)
        else:
            values = pd.Series([""] * len(rows), index=rows.index)
        out[header] = values
    return pd.DataFrame(out)


def _accounts_table(pop: pd.DataFrame, waves: kpi.WaveIndex, spec: ReportSpec,
                    ss, max_rows: int) -> list:
    rows, layout, total = account_rows(pop, waves, spec.key == "eos")
    if rows.empty:
        return [Paragraph("Account records", ss["H2"]),
                Paragraph("No accounts to list.", ss["Muted"])]

    available = kit.CONTENT_WIDTH[kit.LANDSCAPE]
    weights = [w for _, _, w in layout]
    widths = [available * w / sum(weights) for w in weights]
    out = [Paragraph("Account records", ss["H2"]),
           Paragraph("One row per account at its latest wave — the grain every "
                     "unique-TPID metric in the report is counted at. Grouped by "
                     "region, largest ACR first.", ss["Muted"])]
    shown = rows.head(max_rows)
    if total > max_rows:
        out.append(Paragraph(
            f"Showing the {fmt_int(max_rows)} largest of {fmt_int(total)} accounts "
            f"by ACR; the remainder are available as a CSV extract.", ss["Muted"]))
    out.append(kit.spacer(0.2))

    for region, group in shown.groupby("_region_sort", sort=True):
        block = [Paragraph(f"{_esc(region)} — {fmt_int(len(group))} account(s)",
                           ss["H3"]),
                 kit.df_table(format_accounts(group, layout), ss, col_widths=widths,
                              align_right=[len(layout) - 3, len(layout) - 2,
                                           len(layout) - 1])]
        # Keep a region's heading with at least the head of its table.
        out.append(KeepTogether(block) if len(group) <= 12 else block[0])
        if len(group) > 12:
            out.append(block[1])
        out.append(kit.spacer(0.3))
    return out


def _matrix_table(pivot: pd.DataFrame, index_name: str, ss, width: float) -> list:
    """A crosstab as a printable table with a totals column."""
    if pivot.empty:
        return []
    frame = pivot.copy()
    frame["Total"] = frame.sum(axis=1)
    frame = frame.reset_index()
    frame.columns = [index_name] + [str(c) for c in frame.columns[1:]]
    for col in frame.columns[1:]:
        frame[col] = frame[col].map(fmt_int)
    # A three-region matrix stretched across a landscape page reads as three
    # enormous columns, so cap the data columns rather than filling the frame.
    others = len(frame.columns) - 1
    first = min(6.5 * cm, width * 0.35)
    rest = min((width - first) / max(others, 1), 3.4 * cm)
    return [kit.df_table(frame, ss, col_widths=[first] + [rest] * others,
                         align_right=list(range(1, len(frame.columns))), font_size=8)]


def _drilldown_section(fact: pd.DataFrame, spec: ReportSpec, ss, start, end,
                       period_label: str, max_rows: int) -> list:
    pop = segments.population(fact, spec.category)
    title = f"{spec.title} — Drill-Down"
    width = kit.CONTENT_WIDTH[kit.LANDSCAPE]
    story = kit.turn(kit.LANDSCAPE)
    story += [kit.Anchor(f"dd_{spec.key}", title, level=1),
              kit.nav_bar(ss, title, [(f"← Back to {spec.title}", f"rpt_{spec.key}"),
                                      ("Contents", "toc")], width=width),
              kit.spacer(0.15),
              Paragraph(f"The detail behind the <b>{_esc(spec.title)}</b> report: "
                        f"the regional matrix, the pipeline counts and the "
                        f"account records, at the grain every unique-TPID metric "
                        f"is counted at. Each trend's own monthly numbers are "
                        f"printed under its chart in the report itself. "
                        f"Reporting period {_esc(period_label)}.", ss["Body2"]),
              kit.spacer(0.3)]
    if pop.empty:
        story.append(Paragraph("No nominations fall into this report for the current "
                               "filters, so there is nothing to drill into.",
                               ss["Body2"]))
        return story

    waves = kpi.wave_index(pop)
    pivot, _heat, _legend = region_status(waves.last)
    if not pivot.empty:
        story += [Paragraph("Accounts by migration status and WW Region", ss["H2"]),
                  Paragraph("Account counts (each TPID's latest wave) — the numbers "
                            "the regional charts are drawn from.", ss["Muted"]),
                  kit.spacer(0.2),
                  *_matrix_table(pivot, "Migration Status", ss, width)]

    story += _pipeline_tables(pop, waves, ss, width)
    story += [kit.spacer(0.3), *_accounts_table(pop, waves, spec, ss, max_rows)]
    return story


def _pipeline_tables(pop: pd.DataFrame, waves: kpi.WaveIndex, ss,
                     width: float) -> list:
    states, _ = kpi.by_state(pop, lasts=waves.last)
    stages, _ = kpi.on_track_by_stage(pop, lasts=waves.last)
    out = [Paragraph("Pipeline detail", ss["H2"]),
           Paragraph("Accounts at their latest wave, by state and — for those on "
                     "track — by the stage they are in.", ss["Muted"]),
           kit.spacer(0.2)]
    for title, frame, first_col in (("Accounts by state", states, "State"),
                                    ("On-track accounts by stage", stages, "Stage")):
        if frame.empty:
            continue
        printable = frame.rename(columns={"category": first_col, "count": "Accounts",
                                          "acr": "ACR"})
        printable["ACR"] = printable["ACR"].map(fmt_currency)
        printable["Accounts"] = printable["Accounts"].map(fmt_int)
        col = min(width / 3, 5.5 * cm)
        out.append(KeepTogether([
            Paragraph(title, ss["H3"]),
            kit.df_table(printable, ss, col_widths=[col] * 3, align_right=[1, 2],
                         font_size=8)]))
        out.append(kit.spacer(0.25))
    return out


# --------------------------------------------------------------------------- #
# Appendix
# --------------------------------------------------------------------------- #
def _appendix_inconsistency(ctx, ss) -> list:
    """Tag vs. EOS-path disagreements, with the offending rows listed."""
    issues = segments.eos_consistency(ctx.fact)
    labels = {"tagged_without_eos_path": "Tagged Gen-1/Gen-2, no EOS migration path",
              "eos_path_without_tag": "EOS migration path, no generation tag"}
    story = [kit.Anchor("appendix_inconsistency", "Data inconsistency review", level=1),
             kit.nav_bar(ss, "Data inconsistency review", [("Contents", "toc")]),
             kit.spacer(0.15),
             Paragraph("Both are legitimate ways into EOS scope — this lists where "
                       "the generation tag and the migration path disagree, so the "
                       "disagreement is visible rather than silently resolved.",
                       ss["Body2"]),
             kit.spacer(0.3)]
    if not any(len(df) for df in issues.values()):
        story.append(Paragraph("No inconsistencies found — generation tags and EOS "
                               "migration paths agree throughout.", ss["Body2"]))
        return story
    for key, frame in issues.items():
        story.append(Paragraph(f"{labels[key]} — {fmt_int(len(frame))} row(s)",
                               ss["H2"]))
        if frame.empty:
            story += [Paragraph("None.", ss["Muted"]), kit.spacer(0.25)]
            continue
        cols = [c for c in ("tpid", "customer_name", "phase", "migration_path", "tags")
                if c in frame.columns]
        printable = frame[cols].head(40).rename(columns={
            "tpid": "TPID", "customer_name": "Customer", "phase": "Phase",
            "migration_path": "Migration Path", "tags": "Tags"})
        for col in printable.columns:
            printable[col] = printable[col].map(_esc)
        story += [kit.df_table(printable, ss, font_size=7.5), kit.spacer(0.3)]
    return story


_APPENDIX_FN = {"inconsistency": _appendix_inconsistency}


# --------------------------------------------------------------------------- #
# Methodology
# --------------------------------------------------------------------------- #
def _methodology(ss) -> list:
    """How every figure in this report was calculated, from the shared text.

    The same words the HTML report and the Methodology page carry
    (:data:`app.core.glossary.REPORT_METHODOLOGY`), so a rule cannot be
    documented three ways — and in plain English rather than as formulas,
    because the people a report is circulated to should not have to decode a
    rule before they can check a number.
    """
    story = [kit.Anchor("methodology", "Methodology & logic", level=1),
             kit.nav_bar(ss, "Methodology & logic", [("Contents", "toc")]),
             kit.spacer(0.15),
             Paragraph("How every figure in this report is calculated, in "
                       "ordinary words — the rules as implemented, not as "
                       "intended.", ss["Body2"]),
             kit.spacer(0.3)]
    for heading, items in glossary.REPORT_METHODOLOGY:
        story.append(Paragraph(_esc(heading), ss["H2"]))
        for item in items:
            if isinstance(item, glossary.Definition):
                # Title and steps stay on one page: a figure's name on its own
                # at the foot of a page is a heading with nothing under it.
                block = [Paragraph(_esc(item.title), ss["H3"]), kit.spacer(0.06)]
                block += [Paragraph(_strip(line), ss["Rule"], bulletText="\u2022")
                          for line in item.body]
                story += [KeepTogether(block), kit.spacer(0.18)]
            else:
                story += [Paragraph(_strip(item), ss["Body2"]), kit.spacer(0.1)]
        story.append(kit.spacer(0.25))
    return story


# --------------------------------------------------------------------------- #
# Document assembly
# --------------------------------------------------------------------------- #
def _cover(ctx, ss, title: str, subtitle: str, scope_label: str,
           period_label: str, reports: list[ReportSpec], with_drilldown: bool) -> list:
    covered = ", ".join(r.title for r in reports) or "—"
    story = [kit.spacer(4.2),
             Paragraph(_esc(title), ss["CoverTitle"]),
             Paragraph(_esc(subtitle), ss["CoverSub"]),
             kit.spacer(1.0),
             Paragraph(f"<b>{_esc(covered)}</b>", ss["CoverSub"]),
             kit.spacer(0.6),
             Paragraph(f"Scope: {_esc(scope_label)}", ss["CoverSub"]),
             Paragraph(f"Reporting period: {_esc(period_label)}", ss["CoverSub"]),
             Paragraph(f"As-of {pd.Timestamp(ctx.as_of):%d %b %Y}", ss["CoverSub"]),
             Paragraph(f"Generated {datetime.now():%d %b %Y, %H:%M}", ss["CoverSub"])]
    if with_drilldown:
        story += [kit.spacer(0.8),
                  Paragraph("Each report links to its supporting detail; every "
                            "drill-down links back. Use the bookmark pane in your "
                            "PDF viewer to move between sections.", ss["CoverSub"])]
    story.append(kit.page_break())
    return story


def _contents(ss) -> list:
    return [kit.Anchor("toc", "Contents", level=0, in_toc=False),
            Paragraph("Contents", ss["H1"]),
            kit.spacer(0.1),
            Paragraph("Every entry below is a link, as is each report's "
                      "\"View drill-down\" and each drill-down's \"Back to\" line.",
                      ss["Muted"]),
            kit.spacer(0.4),
            kit.contents(ss),
            kit.page_break()]


def _part(key: str, title: str, blurb: str, ss,
          index: list[tuple[str, str]] | None = None) -> list:
    """A part heading, optionally with a linked index of what the part holds.

    Part 2 has to start a page of its own — its drill-downs are landscape — so
    it earns that page back by listing its sections as links.
    """
    out = [kit.Anchor(key, title, level=0),
           Paragraph(title, ss["PartTitle"]),
           Paragraph(_esc(blurb), ss["Muted"]),
           kit.spacer(0.45)]
    for label, dest in index or []:
        out += [kit.link(label, dest, ss["Body2"]), kit.spacer(0.18)]
    return out


def build_story(ctx, where: str = "", scope_label: str = "All data",
                reports: list[str] | None = None, *,
                title: str = DEFAULT_TITLE,
                subtitle: str = DEFAULT_SUBTITLE,
                period_label: str = "All dates in the dataset",
                date_window: tuple | None = None,
                drilldown: bool = True,
                appendices: list[str] | None = None,
                sections: ReportSections | None = None,
                all_time_where: str | None = None,
                max_drilldown_rows: int = MAX_DRILLDOWN_ROWS) -> list:
    """Assemble the report as ReportLab flowables — cover, contents, both parts.

    Laying a flowable out consumes it, so each call returns a fresh story;
    :func:`build_report` builds one twice to resolve page numbers.
    """
    specs = [_BY_KEY[k] for k in (reports if reports is not None else REPORT_KEYS)
             if k in _BY_KEY]
    chosen = [a for a in (appendices or []) if a in _APPENDIX_FN]
    sections = sections or ReportSections()
    start, end = date_window or (None, None)
    fy_window, fy_label = this_fiscal_year(ctx.as_of, start, end)
    ss = kit.styles()
    fact = analytics.select_all(ctx.con, where, table="fact")
    # The same filters with the reporting period dropped — what ACR Pipeline and
    # Nodes Deployment Planned are read over, so a window narrows neither.
    all_time = (fact if all_time_where is None or all_time_where == where
                else analytics.select_all(ctx.con, all_time_where, table="fact"))

    story = _cover(ctx, ss, title, subtitle, scope_label, period_label, specs,
                   drilldown and bool(specs))
    story += _contents(ss)

    if specs:
        story += _part("part_reports", "Part 1 — Executive Reports",
                       "One page-set per migration motion: headline metrics, "
                       "trends, current pipeline, regional cut and insights.", ss)
        for spec in specs:
            story += _report_section(ctx, fact, spec, ss, start, end, period_label,
                                     drilldown, sections, all_time,
                                     fy_window, fy_label)

    if specs and drilldown:
        story += _part("part_detail", "Part 2 — Supporting Detail",
                       "The numbers behind each report, and the account records at "
                       "the grain every unique-TPID metric is counted at.", ss,
                       index=[(f"{s.title} — Drill-Down →", f"dd_{s.key}")
                              for s in specs])
        for spec in specs:
            story += _drilldown_section(fact, spec, ss, start, end, period_label,
                                        max_drilldown_rows)

    if specs:
        # Drill-downs leave the document on landscape pages; everything after
        # them reads as portrait like the rest of the report.
        if drilldown:
            story += kit.turn(kit.PORTRAIT)
        story += _part("part_method", "Methodology & Logic",
                       "The rules behind every number above.", ss)
        story += _methodology(ss)

    if chosen:
        # The methodology above already turned the document back to portrait.
        story += _part("part_appendix", "Appendix",
                       "Consistency checks on the records behind this report.", ss)
        for key in chosen:
            story += _APPENDIX_FN[key](ctx, ss)

    while story and isinstance(story[-1], PageBreak):
        story.pop()
    return story


def build_report(ctx, where: str = "", scope_label: str = "All data",
                 reports: list[str] | None = None, **kw) -> bytes:
    """Build the management report PDF.

    ``reports`` selects from :data:`REPORT_KEYS`; ``where`` is the sidebar filter,
    applied to the wave-level rows before the categories are selected, so the PDF
    honours the same filters as the app.

    The reports always read wave-level rows and deduplicate through
    :mod:`app.core.kpi`, exactly as the Status Report pages do — the
    sidebar's counting-mode toggle changes neither, which is what keeps the two
    reporting the same numbers.
    """
    title = kw.get("title", DEFAULT_TITLE)
    # The running header carries the report's own title and subtitle — nothing
    # about the application that rendered it or the file it was read from.
    running = kw.get("subtitle", DEFAULT_SUBTITLE) or title
    return kit.build(
        lambda: build_story(ctx, where, scope_label, reports, **kw), running, title,
        brand=title)
