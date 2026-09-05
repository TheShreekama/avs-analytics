"""The standard dashboard, rendered once per migration category.

EOS Migration (combined, Gen-1, Gen-2), All AVS Migrations and AVS → Azure
Native all follow the same structure, so they share this module and differ only
in which population they select:

  1. **Executive Summary** — new engagements, migrations completed, hosts
     migrated, on-track accounts, ACR claimed.
  2. **Trends** — nomination count, ACR claimed, hosts and completions month over
     month, each table ending in a Cumulative column.
  3. **Current Pipeline** — nominations by state (On-Track / Completed only),
     on-track accounts by stage.
  4. **Detailed Data** — every record behind the numbers, groupable and exportable.

Every chart is selectable: clicking a month, bar or slice opens the records that
produced it.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from app import state
from app.config import FY_START_MONTH
from app.core import glossary, kpi, metrics, segments
from app.core.metrics import fmt_currency, fmt_int
from app.ui import charts, components, drilldown, trends
from app.ui.theme import page_header, section, subheading

THIS_FY = "This FY"
ALL_TIME = "All time"

#: Categories broad enough for a region cut to say something. The two generation
#: pages are subsets of EOS Migration (All), which already carries it.
_REGIONAL_BREAKDOWN = (segments.CAT_EOS_ALL, segments.CAT_ALL_AVS,
                       segments.CAT_AVS_NATIVE)

# The AVS → Azure Native motion moves *cores* to Azure-native services; the AVS
# categories move *hosts*.  Both are the Total Cores column — only the noun differs.
def _unit(category: str) -> tuple[str, str]:
    if category == segments.CAT_AVS_NATIVE:
        return "Cores Migrated", "Cores"
    return "Hosts Migrated", "Hosts"


_DESCRIPTIONS = {
    segments.CAT_EOS_ALL:
        "Every EOS Migration account combined — Gen-1, Gen-2 and any account in "
        "scope by migration path with no generation tag (those are listed under "
        "Data → Data Inconsistency).",
    segments.CAT_EOS_GEN1:
        "Accounts with an \"AVS Migration - Gen1\" tag on any wave — one tagged wave "
        "brings the whole account in.",
    segments.CAT_EOS_GEN2:
        "Accounts with an \"AVS Migration - Gen2\" tag on any wave — one tagged wave "
        "brings the whole account in.",
    segments.CAT_ALL_AVS:
        "Every migration whose target platform is AVS — on-premises, VMG, AWS/VMC, "
        "AVS-to-AVS and EOS refreshes alike.",
    segments.CAT_AVS_NATIVE:
        "Migrations away from AVS to Azure-native services (the '(From AVS)' offerings).",
}


def render(category: str) -> None:
    ctx = state.ensure_context()
    label = segments.CATEGORY_LABELS[category]
    page_header(label, _DESCRIPTIONS.get(category, ""),
                help=glossary.CATEGORY_HELP.get(category))
    components.data_quality_banner(ctx)

    fact = segments.population(ctx.fact, category)
    key = f"cat_{category}"

    # Reporting window: the global one unless this report overrides it.
    top = st.columns([2, 3])
    with top[0]:
        start, end, shown, preset = components.report_date_range(ctx, key)
    with top[1]:
        components.population_note(category, fact)

    if fact.empty:
        components.empty_state(f"No nominations fall into **{label}**.")
        _why_empty(ctx, category)
        return

    # One wave sort for the whole page: every metric below reuses it.
    waves = kpi.wave_index(fact)
    unit_label, unit_short = _unit(category)
    _executive_summary(ctx, fact, waves, start, end, key, unit_label, category,
                       shown, preset)
    _trends(fact, waves, start, end, key, unit_label, unit_short, shown, preset)
    _pipeline(fact, waves, key)
    if category == segments.CAT_AVS_NATIVE:
        _offering_and_target(fact, key)
    if category in _REGIONAL_BREAKDOWN:
        _regional_breakdown(fact, waves, key)
    _detailed_data(fact, waves, start, end, key, shown)


# --------------------------------------------------------------------------- #
def _why_empty(ctx, category: str) -> None:
    """Show what the file actually contains when a category selects nothing."""
    st.markdown("**Why is this empty?**")
    fact = ctx.fact
    accounts = fact.drop_duplicates("tpid_key")
    gen = (accounts["generation"].value_counts(dropna=False)
           .rename_axis("Generation").reset_index(name="Accounts (TPID)"))
    eos = int(accounts["is_eos_population"].sum())
    st.caption(f"This file has **{len(accounts)}** accounts, of which **{eos}** are EOS "
               f"Migration accounts — an **AVS Migration - Gen1/Gen2** tag on any wave, "
               f"or failing that an **AV36/AV36P/AV52 - EOS** migration path:")
    components.show_table(gen)
    tags = (fact["tags"].astype("string").fillna("(blank)").value_counts().head(8)
            .rename_axis("Tags").reset_index(name="Rows"))
    st.caption("Most common Tags values in the file:")
    components.show_table(tags)
    st.caption("If Tags is blank or unmapped, open **Column Mapping** and point the "
               "Tags field at the right column, then come back.")


def _executive_summary(ctx, fact: pd.DataFrame, waves: kpi.WaveIndex, start, end,
                       key: str, unit_label: str, category: str,
                       shown: str, preset: str) -> None:
    """Headline tiles for the selected period, over a This-FY row when they differ.

    Selecting "This Month" answers "how did this month go?" but loses the year it
    sits in, so anything other than This FY gets the fiscal year above it for
    context.  The two rows are computed independently — each from its own window,
    with its own records — never one derived from the other.
    """
    fy_start, fy_end = _this_fy(ctx)
    show_fy_row = preset != THIS_FY and fy_start is not None

    section("Executive summary", help=glossary.EXECUTIVE_SUMMARY,
            period=None if show_fy_row else shown)
    if show_fy_row:
        st.caption("Two periods: the fiscal year you are in, then the period you "
                   "selected. Each row is measured over its own window.")
        _summary_row(fact, waves, fy_start, fy_end, f"{key}_fy", unit_label, category,
                     _fy_label(ctx))
    _summary_row(fact, waves, start, end, key, unit_label, category, shown)


def _summary_row(fact: pd.DataFrame, waves: kpi.WaveIndex, start, end, key: str,
                 unit_label: str, category: str, period_label: str) -> None:
    """One period's tiles, with the records behind them."""
    subheading(period_label)
    engagements = kpi.new_engagements(fact, start, end, firsts=waves.first)
    completed = kpi.migrations_completed(fact, start, end, lasts=waves.last)
    hosts = kpi.hosts_migrated(fact, start, end)
    on_track = kpi.on_track_accounts(fact, lasts=waves.last)
    acr = kpi.acr_claimed(fact, start, end)

    cores_help = (glossary.CORES_MIGRATED if category == segments.CAT_AVS_NATIVE
                  else glossary.HOSTS_MIGRATED)
    components.kpi_row([
        {"label": "New Engagements", "value": fmt_int(engagements.value),
         "sub": "unique TPIDs, Wave-1 approval", "help": glossary.NEW_ENGAGEMENTS},
        {"label": "Migrations Completed", "value": fmt_int(completed.value),
         "sub": "latest wave completed", "tone": "good",
         "help": glossary.MIGRATIONS_COMPLETED},
        {"label": unit_label, "value": fmt_int(hosts.value),
         "sub": "sum of Total Cores", "help": cores_help},
        {"label": "On-Track Accounts", "value": fmt_int(on_track.value), "tone": "warn",
         "sub": "current — not period-bound", "help": glossary.ON_TRACK_ACCOUNTS},
        {"label": "ACR Claimed", "value": fmt_currency(acr.value),
         "sub": "waves ended in the period", "help": glossary.ACR_CLAIMED},
    ])
    with st.expander(f"🔎 Records behind these tiles — {period_label}"):
        panels = [
            ("New Engagements", engagements, "new-engagements"),
            ("Migrations Completed", completed, "migrations-completed"),
            (unit_label, hosts, "hosts-migrated"),
            ("On-Track Accounts", on_track, "on-track"),
            ("ACR Claimed", acr, "acr-claimed"),
        ]
        for tab, (title, metric, name) in zip(st.tabs([p[0] for p in panels]), panels):
            with tab:
                frame = kpi.drilldown_frame(metric.records)
                if frame.empty:
                    st.info(f"No records behind **{title}** for this period.")
                    continue
                components.show_table(frame, height=320)
                st.download_button("⬇️ Export to CSV",
                                   frame.to_csv(index=False).encode("utf-8"),
                                   file_name=f"{key}-{name}.csv", mime="text/csv",
                                   key=f"{key}_{name}_csv")


def _this_fy(ctx):
    """The fiscal year the reporting as-of date sits in."""
    rng = metrics.date_preset_range(ctx.as_of, THIS_FY, FY_START_MONTH)
    return (rng[0].date(), rng[1].date()) if rng else (None, None)


def _fy_label(ctx) -> str:
    fy_start, fy_end = _this_fy(ctx)
    if fy_start is None:
        return THIS_FY
    return (f"This FY ({metrics.fiscal_year_label(fy_start, FY_START_MONTH)}) — "
            f"{fy_start:%d %b %Y} → {fy_end:%d %b %Y}")


def _trends(fact: pd.DataFrame, waves: kpi.WaveIndex, start, end, key: str,
            unit_label: str, unit_short: str, shown: str, preset: str) -> None:
    """All four month-over-month trends for this category.

    The Trend Analysis pages draw the same four one at a time, one category per
    page, from the same :mod:`app.ui.trends` component — so a number shown in
    both places is computed once.  Only the Total Cores heading differs: "Cores
    Migrated" on the Azure-native page, "Hosts Migrated" on the AVS ones.
    """
    by_fy = preset == ALL_TIME
    section("Trends — month over month", help=glossary.TRENDS, period=shown)
    trends.guidance(by_fy)
    date_col = trends.basis_selector(key)

    titles = {trends.HOSTS: f"{unit_label} (Total Cores)"}
    columns = {trends.HOSTS: unit_short}
    for name in trends.ALL_TRENDS:
        result = trends.compute(name, fact, waves, start, end, date_col=date_col)
        trends.render_trend(result, key=key, title=titles.get(name),
                            display_col=columns.get(name), shown=shown, by_fy=by_fy)
        st.write("")


def _pipeline(fact: pd.DataFrame, waves: kpi.WaveIndex, key: str) -> None:
    # Deliberately not given the reporting period: this section answers "where
    # does the pipeline stand right now", which no date window should narrow.
    section("Current pipeline", help=glossary.PIPELINE,
            period="Current state — not filtered by the reporting period")
    st.caption("Every account in this category at its latest wave, whatever its "
               "nomination date. Click a slice, bar or table row to open the "
               "accounts behind it.")
    states, state_rows = kpi.by_state(fact, lasts=waves.last)
    stages, stage_rows = kpi.on_track_by_stage(fact, lasts=waves.last)

    subheading("Nominations by state", help=glossary.BY_STATE,
               period="Current state — not filtered by the reporting period")
    if states.empty:
        components.empty_state("No On-Track or Completed accounts to report.")
    else:
        fig = charts.donut(states, "category", "count", height=320)
        drilldown.chart_with_drilldown(
            fig, state_rows.assign(bucket=state_rows["state"]), "bucket",
            key=f"{key}_state", what="accounts",
            summary=states.rename(columns={"category": "State", "count": "Accounts",
                                           "acr": "ACR"}),
            summary_bucket="State")

    subheading("On-track nominations by stage", help=glossary.BY_STAGE,
               period="All On-Track accounts — not filtered by the reporting period")
    if stages.empty:
        components.empty_state("No on-track accounts to report.")
    else:
        fig = charts.bar(stages, "category", "count", horizontal=True, height=320)
        drilldown.chart_with_drilldown(
            fig, stage_rows.assign(bucket=stage_rows["stage"]), "bucket",
            key=f"{key}_stage", what="accounts",
            summary=stages.rename(columns={"category": "Stage", "count": "Accounts",
                                           "acr": "ACR"}),
            summary_bucket="Stage")


def _regional_breakdown(fact: pd.DataFrame, waves: kpi.WaveIndex, key: str) -> None:
    """Where the category sits geographically, by migration status.

    Account-grain (each TPID's latest wave), so an account with five waves is one
    account here rather than five rows — which is what the state chart above it
    counts too.
    """
    section("Regional breakdown", help=glossary.REGIONAL_BREAKDOWN,
            period="Current state — not filtered by the reporting period")
    st.caption("Accounts at their latest wave, by region and migration status. "
               "Click a bar to open the accounts behind it.")
    rows = waves.last
    if rows.empty or "region_geo" not in rows.columns:
        components.empty_state("No regional data to report.")
        return
    rows = rows.assign(
        _status=rows["migration_status_label"].astype("string")
                                              .replace({"": pd.NA}).fillna("Unknown"),
        _region=rows["region_geo"].astype("string")
                                  .replace({"": pd.NA}).fillna("Unknown"))
    pivot = pd.crosstab(rows["_status"], rows["_region"])
    heat = pd.crosstab(rows["_region"], rows["_status"])

    c1, c2 = st.columns(2)
    with c1:
        mode = st.radio("View", ["Counts", "Share %"], horizontal=True,
                        key=f"{key}_region_mode", label_visibility="collapsed")
        st.plotly_chart(charts.stacked_bar(pivot, title="Migration status by region",
                                           percent=(mode == "Share %")),
                        width="stretch")
    with c2:
        st.plotly_chart(charts.heatmap(heat, title="Region × status heatmap"),
                        width="stretch")

    counts = (rows.groupby("_region", as_index=False)
                  .agg(count=("tpid_key", "nunique"))
                  .rename(columns={"_region": "category"})
                  .sort_values("count", ascending=False))
    fig = charts.bar(counts, "category", "count", horizontal=True, height=300,
                     title="Accounts by region")
    drilldown.chart_with_drilldown(
        fig, rows.assign(bucket=rows["_region"]), "bucket",
        key=f"{key}_region", what="accounts",
        summary=counts.rename(columns={"category": "Region", "count": "Accounts"}),
        summary_bucket="Region")
    drilldown.data_expander(
        pivot.reset_index().rename(columns={"_status": "Migration Status"}),
        f"{key}_region_grid", label="Underlying data — status × region",
        caption="Account counts per migration status and region: the numbers "
                "both charts above are drawn from.")


def _offering_and_target(fact: pd.DataFrame, key: str) -> None:
    """The AVS → Azure Native cut: which offering, which Azure service.

    Lives here rather than on the status report because this is the page that
    owns the motion — one place to read it, not two.
    """
    section("By offering & target", help=glossary.OFFERING_AND_TARGET,
            period="Every nomination in this category — not filtered by the "
                   "reporting period")
    st.caption("Full offering names (the migration path), and the Azure-native "
               "service each one lands on. Click a bar or slice to open the "
               "nominations behind it.")
    paths = _count_by(fact, "migration_path")
    targets = _count_by(fact, "azure_target")
    c1, c2 = st.columns(2)
    with c1:
        picked_path = drilldown.selectable_chart(
            charts.bar(paths, "category", "count", horizontal=True,
                       title="Nominations by migration path (offering)"),
            key=f"{key}_offering")
    with c2:
        picked_target = drilldown.selectable_chart(
            charts.donut(targets, "category", "count", title="Azure-native targets"),
            key=f"{key}_target")
    drilldown.drilldown(fact, "migration_path", picked_path,
                        key=f"{key}_offering_rows", what="nominations by offering",
                        max_rows=500)
    drilldown.drilldown(fact, "azure_target", picked_target,
                        key=f"{key}_target_rows", what="nominations by target",
                        max_rows=500)


def _count_by(fact: pd.DataFrame, column: str) -> pd.DataFrame:
    """Nomination counts per value of ``column``, biggest first."""
    values = (fact[column].astype("string").replace({"": pd.NA}).fillna("Unknown")
              if column in fact.columns else pd.Series(dtype="string"))
    return (values.value_counts().rename_axis("category").reset_index(name="count")
            if not values.empty else pd.DataFrame(columns=["category", "count"]))


def _detailed_data(fact: pd.DataFrame, waves: kpi.WaveIndex, start, end, key: str,
                   shown: str) -> None:
    section("Detailed data", help=glossary.DETAILED_DATA, period=shown)
    st.caption("Every record in this category, inheriting the filters and reporting "
               "period above. Group it, read the subtotals, then export.")
    c1, c2 = st.columns([2, 2])
    grain = c1.radio("Grain", ["Accounts (unique TPID)", "Nomination waves"],
                     horizontal=True, key=f"{key}_grain",
                     help="Unique-TPID metrics never show a TPID twice; switch to "
                          "wave level to see the underlying source records.")
    limit = c2.checkbox("Limit to the reporting period", value=start is not None,
                        key=f"{key}_limit", disabled=start is None,
                        help="Keeps only records approved inside the selected window.")
    rows = waves.last if grain.startswith("Accounts") else fact
    if limit and start is not None:
        rows = rows[kpi.in_window(rows["approval_date"], start, end)]
        if rows.empty:
            components.empty_state(
                "No records were approved inside the reporting period. Widen the "
                "period above, or untick **Limit to the reporting period**.")
            return
    drilldown.pivot_explorer(rows, key=f"{key}_pivot")
    frame = kpi.drilldown_frame(rows)
    components.show_table(frame, height=420)
    st.download_button("⬇️ Export to CSV", frame.to_csv(index=False).encode("utf-8"),
                       file_name=f"{key}-detail.csv", mime="text/csv",
                       key=f"{key}_detail_csv")


# --------------------------------------------------------------------------- #
# Page entry points (st.Page needs a distinct callable per page)
# --------------------------------------------------------------------------- #
def eos_all() -> None:
    render(segments.CAT_EOS_ALL)


def eos_gen1() -> None:
    render(segments.CAT_EOS_GEN1)


def eos_gen2() -> None:
    render(segments.CAT_EOS_GEN2)


def all_avs() -> None:
    render(segments.CAT_ALL_AVS)


def avs_native() -> None:
    render(segments.CAT_AVS_NATIVE)
