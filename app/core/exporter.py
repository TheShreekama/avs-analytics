"""Management report engine — the PDF the Reports page builds.

The document is deliberately two-part, so one file serves both a leadership
review and the questions that follow it:

* **Part 1 — Executive reports.** One page-set per migration motion (AVS
  Migrations, EOS Migrations, AVS to Azure Native): headline metrics, trends,
  pipeline, regional cut and insights.  Charts and summaries only.
* **Part 2 — Supporting detail.** The drill-down behind each report — the
  monthly numbers, the matrices the charts are drawn from, and the account
  records, on landscape pages.

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

from ..ui import pdf_charts as pc
from . import (analytics, glossary, insights as insights_mod, kpi,
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
        "engagements": kpi.new_engagements(pop, start, end, firsts=waves.first),
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
BLOCKED_TITLE = "Blocked & waiting accounts"

BLOCKED_NOTE = (
    "Accounts stopped on a stated blocking state — Blocked, Blocked - Account "
    "team, Blocked - Customer, Blocked - Partner / ISD, or Waiting action on "
    "follow up date. None of them is in any metric above, and none of those "
    "metrics is in here. Status Summary carries the programme's own note on "
    "why each one has stopped."
)


#: Where an account in each state is reported, so the reconciliation says what
#: to do about a row rather than only naming it.
_STATE_HOME = {
    kpi.STATE_ON_TRACK: "Current pipeline (charted above)",
    kpi.STATE_COMPLETED: "Current pipeline (charted above)",
    kpi.STATE_DEFERRED: "Not reported — deferred by the customer",
    kpi.STATE_CANCELLED: "Not reported — cancelled / archived",
    kpi.STATE_BLOCKED: "Not reported — Current State is not a stated blocking state",
    kpi.STATE_OTHER: "Not reported — no stated state (see Data Inconsistency)",
}


#: The order states read across the generation grid: the three a review asks
#: about first, then whatever else the file contains.
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
    return grid[order], rows


def reconciliation(pop: pd.DataFrame, waves: kpi.WaveIndex) -> tuple[pd.DataFrame, int]:
    """Every account in the report, by state, with where each one is reported.

    The answer to "the charts show 32 of my 36 accounts — where are the other
    four?".  Each account resolves to exactly one state, so these rows sum to
    the report's own account count; what varies is **where** a state is
    reported, and three of them are reported nowhere: a cancelled or deferred
    engagement is a decision already taken, and an account with no stated
    Current State cannot be said to be moving.

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
        if shown == len(part):
            where = BLOCKED_TITLE
        elif shown:
            where = f"{BLOCKED_TITLE} ({fmt_int(shown)} of {fmt_int(len(part))})"
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


def _summary_block(spec: ReportSpec, metrics_: dict, ss, period_label: str) -> list:
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
    return [Paragraph("Executive summary", ss["H2"]),
            Paragraph(f"Reporting period: {_esc(period_label)}. On-Track is a "
                      "snapshot of where things stand now; <b>ACR Pipeline and "
                      "Nodes Deployment Planned are read over the whole dataset</b> "
                      "— work nominated before the window is still work still to "
                      "do. No date window narrows any of the three.", ss["Muted"]),
            kit.spacer(0.2),
            kit.kpi_cards(tiles, ss, per_row=3)]


def _trend_block(pop: pd.DataFrame, waves: kpi.WaveIndex, start, end,
                 spec: ReportSpec, ss) -> list:
    noms, _ = kpi.monthly_unique_tpids(pop, "approval_date", start, end,
                                       firsts=waves.first)
    acr, _ = kpi.monthly_acr_claimed(pop, start, end)
    hosts, _ = kpi.monthly_hosts(pop, start, end)
    done, _ = kpi.monthly_migrations_completed(pop, start, end, lasts=waves.last)

    series = [
        ("Nominations per month (unique TPIDs)", noms, "Nominations", False),
        ("ACR claimed per month", acr, "ACR Claimed", True),
        (f"{spec.unit_label} per month (Total Cores)", hosts, "Hosts", False),
        ("Migrations completed per month (unique TPIDs)", done, "Migrations Completed",
         False),
    ]
    out = [Paragraph("Trends — month over month", ss["H2"]),
           Paragraph("Each measure over the reporting period. The running totals "
                     "behind these lines are tabulated in the drill-down.",
                     ss["Muted"]), kit.spacer(0.15)]
    drawn = 0
    for title, table, value_col, currency in series:
        if table.empty:
            continue
        drawn += 1
        colour = "#5C2E91" if currency else "#0F6CBD"
        out.append(KeepTogether([
            Paragraph(title, ss["H3"]),
            kit.image(pc.line_png(table, "period", value_col, area=not currency,
                                  color=colour, currency=currency, height_px=250),
                      width_cm=16.6),
        ]))
        out.append(kit.spacer(0.15))
    if not drawn:
        out.append(Paragraph("No activity dated inside the reporting period.",
                             ss["Muted"]))
    return out


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
        out.append(Paragraph("No accounts are blocked or waiting — every account "
                             "here is moving, finished, or closed out.",
                             ss["Body2"]))
        return out

    out += [kit.kpi_cards([
        ("Blocked Accounts", fmt_int(tables["accounts"]), "not in any metric above"),
        ("ACR Held Up", fmt_currency(tables["acr"]), "sum over those accounts"),
        ("Waves Behind Them", fmt_int(tables["wave_count"]),
         "every wave of those accounts"),
    ], ss, per_row=3), kit.spacer(0.25)]

    states = tables["summary"].rename(columns={"category": "Current State",
                                               "count": "Accounts", "acr": "ACR"})
    states["ACR"] = states["ACR"].map(fmt_currency)
    states["Accounts"] = states["Accounts"].map(fmt_int)
    out.append(KeepTogether([
        Paragraph("By current state", ss["H3"]),
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
    ("blocked_state", "Current State", 2.6),
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
                                            firsts=waves.first)
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


def _report_section(fact: pd.DataFrame, spec: ReportSpec, ss, start, end,
                    period_label: str, with_drilldown: bool,
                    sections: ReportSections,
                    all_time: pd.DataFrame | None = None) -> list:
    pop = segments.population(fact, spec.category)
    # The forward-looking tiles read the whole programme, not the window.
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
    blocks = [_summary_block(spec, headline(pop, waves, start, end, ahead), ss,
                             period_label),
              _trend_block(pop, waves, start, end, spec, ss),
              _pipeline_block(pop, waves, ss)]
    if spec.key == "native":
        blocks.append(_offering_block(pop, ss))
    blocks.append(_regional_block(waves, ss))
    if sections.blocked:
        blocks.append(_blocked_block(pop, waves, ss))
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
                  *_insight_lines(pop, ss)]
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
    detail = kpi.account_detail(pop, firsts=waves.first, lasts=waves.last)
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
                        f"the monthly numbers its charts are drawn from, the "
                        f"regional matrix, and the account records. "
                        f"Reporting period {_esc(period_label)}.", ss["Body2"]),
              kit.spacer(0.3)]
    if pop.empty:
        story.append(Paragraph("No nominations fall into this report for the current "
                               "filters, so there is nothing to drill into.",
                               ss["Body2"]))
        return story

    waves = kpi.wave_index(pop)
    story += [Paragraph("Monthly numbers", ss["H2"]),
              Paragraph("Every trend in the report, tabulated. Cumulative is the "
                        "running total of the months shown.", ss["Muted"]),
              kit.spacer(0.2)]
    story += _monthly_tables(pop, waves, start, end, spec, ss, width)

    pivot, _heat, _legend = region_status(waves.last)
    if not pivot.empty:
        story += [kit.spacer(0.3),
                  Paragraph("Accounts by migration status and WW Region", ss["H2"]),
                  Paragraph("Account counts (each TPID's latest wave) — the numbers "
                            "the regional charts are drawn from.", ss["Muted"]),
                  kit.spacer(0.2),
                  *_matrix_table(pivot, "Migration Status", ss, width)]

    story += [kit.spacer(0.3), *_pipeline_tables(pop, waves, ss, width)]
    story += [kit.spacer(0.3), *_accounts_table(pop, waves, spec, ss, max_rows)]
    return story


def _monthly_tables(pop: pd.DataFrame, waves: kpi.WaveIndex, start, end,
                    spec: ReportSpec, ss, width: float) -> list:
    noms, _ = kpi.monthly_unique_tpids(pop, "approval_date", start, end,
                                       firsts=waves.first)
    acr, _ = kpi.monthly_acr_claimed(pop, start, end)
    hosts, _ = kpi.monthly_hosts(pop, start, end)
    done, _ = kpi.monthly_migrations_completed(pop, start, end, lasts=waves.last)
    series = [("Nominations (unique TPIDs)", noms, "Nominations", False),
              ("ACR claimed", acr, "ACR Claimed", True),
              (spec.unit_label, hosts, "Hosts", False),
              ("Migrations completed (unique TPIDs)", done, "Migrations Completed",
               False)]
    out, printed = [], 0
    for title, table, value_col, currency in series:
        if table.empty:
            continue
        printed += 1
        frame = trend_table(table, value_col, currency)
        col = min(width / 3, 5.5 * cm)
        out.append(KeepTogether([
            Paragraph(title, ss["H3"]),
            kit.df_table(frame, ss, col_widths=[col] * 3, align_right=[1, 2],
                         font_size=8)]))
        out.append(kit.spacer(0.25))
    if not printed:
        out.append(Paragraph("No activity dated inside the reporting period.",
                             ss["Muted"]))
    return out


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
    documented three ways.
    """
    story = [kit.Anchor("methodology", "Methodology & logic", level=1),
             kit.nav_bar(ss, "Methodology & logic", [("Contents", "toc")]),
             kit.spacer(0.15),
             Paragraph("How every figure in this report is calculated — the "
                       "rules as implemented, not as intended.", ss["Body2"]),
             kit.spacer(0.3)]
    for heading, items in glossary.REPORT_METHODOLOGY:
        block = [Paragraph(_esc(heading), ss["H2"])]
        for item in items:
            if isinstance(item, glossary.Rule):
                block += [kit.spacer(0.05),
                          *kit.rule_block(item.title, item.lines, ss,
                                          plain=_strip(item.plain)),
                          kit.spacer(0.12)]
            else:
                block += [Paragraph(_strip(item), ss["Body2"]), kit.spacer(0.08)]
        story += [KeepTogether(block), kit.spacer(0.25)]
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
            story += _report_section(fact, spec, ss, start, end, period_label,
                                     drilldown, sections, all_time)

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
