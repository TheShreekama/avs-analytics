"""EOS Programme Tracker — the manual EOS tracking sheet, reported on its own.

Every chart and table here is built by :mod:`app.core.eos_programme`, which the
PDF and HTML reports render too, so the page and the exports cannot disagree.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from app import state
from app.core import eos_programme as prog, glossary
from app.core.metrics import fmt_compact_currency, fmt_int
from app.ui import charts, components
from app.ui.theme import banner, page_header, section


def render() -> None:
    ctx = state.ensure_context()
    page_header(prog.TITLE,
                "Where the EOS programme's own sheet says every account is — "
                "status, state, SDDCs and dates.",
                help=glossary.PROGRAMME_TRACKER)
    if not ctx.has_tracker:
        components.empty_state(
            "No EOS tracking sheet is loaded. Upload one on **Data & Upload** "
            "(section 2) — or load **Sample + EOS tracker** there to see this "
            "page with the bundled example.")
        return

    report = prog.build(ctx.tracker, ctx.fact, ctx.as_of)
    if report.empty:
        components.empty_state("The tracking sheet has no rows with a TPID.")
        return
    t = report.tiles
    missing = t["accounts"] - t["in_fdo"]
    if missing:
        banner(f"ℹ️ <b>{fmt_int(missing)}</b> of the sheet's {fmt_int(t['accounts'])} "
               f"accounts have no nomination in the FDO dataset. They are "
               f"reported here from the sheet alone, and appear in no "
               f"FDO-based report until the nomination exists.")
    st.caption(f"{ctx.tracker_filename} · as-of {pd.Timestamp(ctx.as_of):%d %b %Y} · "
               "the reporting period and sidebar filters do not apply to this page.")

    pct = "–" if t["sddc_pct"] is None else f"{t['sddc_pct']:.0f}%"
    components.kpi_row([
        {"label": "Accounts tracked", "value": fmt_int(t["accounts"]),
         "help": "TPIDs in the tracking sheet."},
        {"label": "In FDO dataset", "value": fmt_int(t["in_fdo"]),
         "tone": "warn" if missing else "good"},
        {"label": "On Track", "value": fmt_int(t["on_track"]), "tone": "good"},
        {"label": "Blocked", "value": fmt_int(t["blocked"]),
         "tone": "bad" if t["blocked"] else ""},
        {"label": "Completed", "value": fmt_int(t["completed"])},
        {"label": "On Hold / Cancelled",
         "value": f"{fmt_int(t['on_hold'])} / {fmt_int(t['cancelled'])}"},
        {"label": "SDDCs migrated",
         "value": f"{fmt_int(t['sddcs_migrated'])} of {fmt_int(t['sddcs_in_scope'])}",
         "sub": f"{pct} complete"},
    ])

    section("Where the migrations are", help=_help("Accounts by Migration Status"))
    cols = st.columns([3, 2])
    with cols[0]:
        grid = report.by_status.drop(columns="Total", errors="ignore")
        st.plotly_chart(_counts(charts.stacked_bar(
            grid, title="Accounts by Migration Status", height=400),
            report.by_status["Total"].max()), width="stretch")
    with cols[1]:
        state_grid = report.by_state.drop(columns="Total", errors="ignore")
        st.plotly_chart(_counts(charts.stacked_bar(
            state_grid, title="Accounts by Current State", height=400),
            report.by_state["Total"].max()), width="stretch")
    cols = st.columns(2)
    with cols[0]:
        st.dataframe(prog.grid_frame(report.by_status, "Migration Status"),
                     width="stretch", hide_index=True)
    with cols[1]:
        st.dataframe(prog.grid_frame(report.by_state, "Current State"),
                     width="stretch", hide_index=True)

    section("Status against state",
            help=_help("Migration Status against Current State"))
    st.plotly_chart(_top_down(charts.heatmap(report.status_state,
                                             height=80 + 42 * len(report.status_state))),
                    width="stretch")
    if not report.checks.empty:
        banner(f"⚠️ {fmt_int(len(report.checks))} account(s) have a Migration "
               f"Status and Current State that contradict each other — listed "
               f"below and on Data Inconsistency.", "warn")
        components.show_table(report.checks)

    section("SDDC progress", help=_help("SDDC progress"))
    sddcs = report.sddcs
    if not sddcs.empty:
        cols = st.columns([3, 2])
        with cols[0]:
            plot = sddcs[sddcs["generation"] != "All EOS"]
            st.plotly_chart(_counts(charts.grouped_bar(
                plot, "generation", ["in_scope", "migrated", "outstanding"],
                title="SDDCs by generation", height=340), plot["in_scope"].max()),
                width="stretch")
        with cols[1]:
            st.dataframe(_sddc_table(sddcs), width="stretch", hide_index=True)

    section("Timeline", help=_help("Starts and completions by month"))
    cols = st.columns([3, 2])
    with cols[0]:
        if not report.monthly.empty:
            st.plotly_chart(_counts(charts.grouped_bar(
                report.monthly, "month", ["Started", "Ended"],
                title="Migrations started and ended by month", height=340),
                report.monthly[["Started", "Ended"]].to_numpy().max()),
                width="stretch")
        else:
            st.caption("The sheet carries no start or end dates.")
    with cols[1]:
        st.markdown("**In flight, by days since Migration Start Date**")
        st.dataframe(report.ageing.rename(columns={"bucket": "Days in migration",
                                                   "accounts": "Accounts"}),
                     width="stretch", hide_index=True)
        if not report.durations.empty:
            st.markdown("**Completed migrations, start to end (days)**")
            st.dataframe(_duration_table(report.durations), width="stretch",
                         hide_index=True)

    section("By WW Region")
    if not report.region_status.empty:
        st.plotly_chart(_top_down(charts.heatmap(
            report.region_status, height=100 + 42 * len(report.region_status))),
            width="stretch")

    section("Needs attention", help=_help("Needs attention"))
    if report.attention.empty:
        st.caption("No account is Blocked or On Hold.")
    else:
        st.dataframe(prog.account_table(report.attention, fmt_compact_currency),
                     width="stretch", hide_index=True)

    section("Every tracked account", help=_help("Accounts tracked"))
    rows = _filtered(report.accounts)
    table = prog.account_table(rows, fmt_compact_currency)
    st.dataframe(table, width="stretch", hide_index=True, height=420)
    st.download_button("Download these accounts (CSV)",
                       table.to_csv(index=False).encode("utf-8"),
                       file_name="eos_programme_tracker.csv", mime="text/csv")


def _counts(fig, top: float):
    """Whole-number ticks and the legend above the plot.

    With a handful of accounts the default tick spacing lands between whole
    numbers ("1, 1, 1"), and a legend below the plot sits on the rotated stage
    names.
    """
    if top and top <= 12:
        fig.update_yaxes(dtick=1, tickformat="d")
    fig.update_layout(legend=dict(orientation="h", yanchor="bottom", y=1.02,
                                  xanchor="right", x=1))
    return fig


def _top_down(fig):
    """A heatmap read the way its table is: first row at the top."""
    fig.update_yaxes(autorange="reversed")
    return fig


def _help(title: str) -> str | None:
    """The methodology entry for a figure, as hover text."""
    for _heading, items in glossary.REPORT_METHODOLOGY:
        for item in items:
            if isinstance(item, glossary.Definition) and item.title == title:
                return "\n".join(f"• {line.replace('**', '')}" for line in item.body)
    return None


def _filtered(acc: pd.DataFrame) -> pd.DataFrame:
    cols = st.columns(3)
    picks = {}
    for col, (key, label) in zip(cols, (("generation", "Target Gen"),
                                        ("status", "Migration Status"),
                                        ("state", "Current State"))):
        options = list(dict.fromkeys(acc[key].astype(str)))
        with col:
            picks[key] = st.multiselect(label, options, key=f"prog_{key}")
    for key, chosen in picks.items():
        if chosen:
            acc = acc[acc[key].astype(str).isin(chosen)]
    return acc


def _sddc_table(sddcs: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame({
        "Generation": sddcs["generation"],
        "Accounts": sddcs["accounts"].map(fmt_int),
        "In scope": sddcs["in_scope"].map(fmt_int),
        "Migrated": sddcs["migrated"].map(fmt_int),
        "Outstanding": sddcs["outstanding"].map(fmt_int),
        "Complete": sddcs["complete_pct"].map(
            lambda v: "–" if pd.isna(v) else f"{v:.0f}%"),
    })
    return out


def _duration_table(durations: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({
        "Generation": durations["generation"],
        "Accounts": durations["accounts"].map(fmt_int),
        "Median": durations["median_days"].map(fmt_int),
        "Average": durations["average_days"].map(fmt_int),
        "Longest": durations["longest_days"].map(fmt_int),
    })
