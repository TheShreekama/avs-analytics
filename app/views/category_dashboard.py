"""The standard dashboard, rendered once per migration category.

EOS Migration (combined, Gen-1, Gen-2), All AVS Migrations and AVS → Azure
Native all follow the same structure, so they share this module and differ only
in which population they select:

  1. **Executive Summary** — new engagements, migrations completed, hosts
     migrated, on-track accounts, ACR claimed.
  2. **Current Pipeline** — nominations by state (On-Track / Completed only),
     on-track accounts by stage.
  3. **Regional breakdown** — where the category sits geographically, by status.
  4. **Blocked & waiting accounts** — accounts stopped on a blocking Current
     State, reported apart from every metric above.
  5. **Detailed Data** — every record behind the numbers, groupable and exportable.

Month-over-month trends are **not** here: they live under Trend Analysis, one
page per measure with every category on it, so a measure can be read across the
portfolio rather than a category at a time.  See :mod:`app.views.trend_analysis`.

Every chart is selectable: clicking a bar or slice opens the records that
produced it.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from app import state
from app.config import EOS_MATRIX_START_FY, FY_START_MONTH
from app.core import exporter, glossary, kpi, metrics, segments
from app.core.metrics import fmt_currency, fmt_int
from app.ui import charts, components, drilldown
from app.ui.theme import banner, page_header, section, subheading

THIS_FY = "This FY"

#: Separates the two halves of a stacked-bar selection ("Americas · Completed").
#: A clicked segment names a region *and* a stage, and the records carry the same
#: composite so a click filters to exactly that pair.
_REGION_STAGE_JOIN = " · "

#: Categories broad enough for a region cut to say something. The two generation
#: pages are subsets of EOS Migration (All), which already carries it.
_REGIONAL_BREAKDOWN = (segments.CAT_EOS_ALL, segments.CAT_ALL_AVS,
                       segments.CAT_AVS_NATIVE)

#: The EOS pages — the only ones that report the deployment still planned.
_EOS_CATEGORIES = (segments.CAT_EOS_ALL, segments.CAT_EOS_GEN1, segments.CAT_EOS_GEN2)

#: The two broad motions that also report their largest accounts by ACR.  The
#: generation pages are subsets of EOS Migration (All) and would repeat much of
#: its list; these two are whole portfolios, and "where is the money" is the
#: question their reviews open with.
_TOP_ACCOUNT_CATEGORIES = (segments.CAT_ALL_AVS, segments.CAT_AVS_NATIVE)

# The AVS → Azure Native motion moves *cores* to Azure-native services; the AVS
# categories move *hosts*.  Both are the Total Cores column — only the noun differs.
def _unit(category: str) -> str:
    if category == segments.CAT_AVS_NATIVE:
        return "Cores Migrated"
    return "Hosts Migrated"


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
        _population_note(ctx, category, fact)

    if fact.empty:
        components.empty_state(f"No nominations fall into **{label}**.")
        _why_empty(ctx, category)
        return

    # One wave sort for the whole page: every metric below reuses it.
    waves = kpi.wave_index(fact)
    unit_label = _unit(category)
    _executive_summary(ctx, fact, waves, start, end, key, unit_label, category,
                       shown, preset)
    if category == segments.CAT_EOS_ALL:
        _generation_matrix(ctx, fact, key)
    _pipeline(fact, waves, key)
    if category in _TOP_ACCOUNT_CATEGORIES:
        _top_accounts(fact, waves, key)
    if category == segments.CAT_AVS_NATIVE:
        _offering_and_target(fact, key)
    if category in _REGIONAL_BREAKDOWN:
        _regional_breakdown(fact, waves, key)
    _blocked_accounts(fact, waves, key)
    _detailed_data(fact, waves, start, end, key, shown)


# --------------------------------------------------------------------------- #
#: The matrix blocks: (generation tag, heading).  Every EOS account is refreshing
#: away from ageing Gen-1 hardware, so the tag names the generation it lands ON
#: and the "Gen1 to" half of each heading is the constant.
_MATRIX_BLOCKS = ((segments.GEN_1, "Gen1 to Gen1"),
                  (segments.GEN_2, "Gen1 to Gen2"))


def _generation_matrix(ctx, fact: pd.DataFrame, key: str) -> None:
    """The programme's month-by-month grid, one block per target generation.

    Deliberately outside the page's reporting-period control: this grid runs
    from a fixed July start to today, showing every month in between whether or
    not anything happened in it, because a month with no nominations is itself
    the number being reported.
    """
    section("Monthly programme matrix", help=glossary.EOS_MATRIX,
            period="Fixed — July onwards, every month shown")
    start = metrics.named_fiscal_year_start(EOS_MATRIX_START_FY, FY_START_MONTH)
    st.caption(f"From **{start:%b %Y}** to **{ctx.as_of:%b %Y}**, every month "
               "included, each fiscal year closing with its own total column. "
               "Blocks are the generation each account is refreshing on to — all "
               "EOS accounts are coming from Gen-1 hardware. *Migration start* "
               "and *migration end* come from the **manual EOS tracking sheet** "
               "wherever it covers an account, and otherwise from the export: "
               "start derived (earliest wave reading On Track or Done → Actual "
               "Start Date, else Planned Start, else Nom. Approval), end from "
               "the latest wave completing. *Engagement end* repeats *migration "
               "end*, the closest the export comes to it.")
    for generation, title in _MATRIX_BLOCKS:
        block = fact[fact["generation"] == generation]
        accounts = segments.tpid_key(block).nunique() if not block.empty else 0
        subheading(title)
        st.caption(f"**{fmt_int(accounts)}** accounts tagged "
                   f"**AVS Migration - {generation.replace('-', '')}** · "
                   f"**{fmt_int(len(block))}** nomination waves.")
        months = kpi.matrix_month_span(block, start, ctx.as_of)
        grid = kpi.monthly_matrix(block, months, fy_start_month=FY_START_MONTH)
        components.show_table(grid)
        st.download_button(
            f"⬇️ Export {title} to CSV", grid.to_csv(index=False).encode("utf-8"),
            file_name=f"eos-matrix-{generation.lower().replace('-', '')}.csv",
            mime="text/csv", key=f"{key}_matrix_{generation}")


def _population_note(ctx, category: str, fact: pd.DataFrame) -> None:
    tpids = fmt_int(segments.tpid_key(fact).nunique()) if not fact.empty else "0"
    bits = [f"<b>{tpids}</b> TPIDs · <b>{fmt_int(len(fact))}</b> nomination waves"]
    if category in (segments.CAT_EOS_ALL, segments.CAT_EOS_GEN1, segments.CAT_EOS_GEN2):
        bits.append("scope from the <b>AVS Migration - Gen1/Gen2</b> tag on any wave, "
                    "or the <b>AV36/AV36P/AV52 - EOS</b> path when untagged")
    if category == segments.CAT_EOS_ALL and not fact.empty:
        split = (fact.drop_duplicates("tpid_key")["generation"]
                 .value_counts().rename({segments.GEN_UNCLASSIFIED: "no generation tag"}))
        bits.append(" · ".join(f"<b>{fmt_int(v)}</b> {k}" for k, v in split.items()))
    banner(" · ".join(bits))


def _why_empty(ctx, category: str) -> None:
    """Show what the file actually contains when a category selects nothing."""
    st.markdown("**Why is this empty?**")
    fact = ctx.fact
    untagged = segments.population(fact, segments.CAT_EOS_UNCLASSIFIED)
    if category in _EOS_CATEGORIES and not untagged.empty:
        # The likeliest reason an EOS page is empty: accounts in scope by
        # migration path that no wave ever tagged with a generation.  EOS is
        # reported by generation, so they are not counted here.
        count = fmt_int(segments.tpid_key(untagged).nunique())
        banner(f"<b>{count}</b> account(s) are in EOS scope through an "
               "<b>AV36/AV36P/AV52 - EOS</b> migration path but carry no "
               "<b>AVS Migration - Gen1/Gen2</b> tag on any wave. EOS is "
               "reported by generation, so they are excluded from this page and "
               "from every EOS total — they are listed on <b>Data → Data "
               "Inconsistency</b>, and tagging them at source brings them "
               "straight in.")
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
    engagements = kpi.new_engagements(fact, start, end, approvals=waves.approval)
    completed = kpi.migrations_completed(fact, start, end, lasts=waves.last)
    hosts = kpi.hosts_migrated(fact, start, end)
    on_track = kpi.on_track_accounts(fact, lasts=waves.last)
    acr = kpi.acr_claimed(fact, start, end)
    pipeline = kpi.acr_pipeline(fact)
    planned = kpi.nodes_planned(fact)

    cores_help = (glossary.CORES_MIGRATED if category == segments.CAT_AVS_NATIVE
                  else glossary.HOSTS_MIGRATED)
    tiles = [
        {"label": "New Engagements", "value": fmt_int(engagements.value),
         "sub": "unique TPIDs, Wave-1 approval", "help": glossary.NEW_ENGAGEMENTS},
        {"label": "Migrations Completed", "value": fmt_int(completed.value),
         "sub": "latest wave done, none on track", "tone": "good",
         "help": glossary.MIGRATIONS_COMPLETED},
        {"label": unit_label, "value": fmt_int(hosts.value),
         "sub": "sum of Total Cores", "help": cores_help},
        {"label": "On-Track Accounts", "value": fmt_int(on_track.value), "tone": "warn",
         "sub": "any wave on track — now", "help": glossary.ON_TRACK_ACCOUNTS},
        {"label": "ACR Claimed", "value": fmt_currency(acr.value),
         "sub": "waves ended in the period", "help": glossary.ACR_CLAIMED},
        {"label": "ACR Pipeline", "value": fmt_currency(pipeline.value),
         "sub": "eligible waves — now", "help": glossary.ACR_PIPELINE},
    ]
    panels = [
        ("New Engagements", engagements, "new-engagements"),
        ("Migrations Completed", completed, "migrations-completed"),
        (unit_label, hosts, "hosts-migrated"),
        ("On-Track Accounts", on_track, "on-track"),
        ("ACR Claimed", acr, "acr-claimed"),
        ("ACR Pipeline", pipeline, "acr-pipeline"),
    ]
    # Planned deployment is an EOS measure: only that programme reports the
    # nodes still to go alongside the nodes already deployed.
    if category in _EOS_CATEGORIES:
        tiles.append({"label": "Nodes Deployment Planned",
                      "value": fmt_int(planned.value),
                      "sub": "Total Cores, eligible waves",
                      "help": glossary.NODES_PLANNED})
        panels.append(("Nodes Deployment Planned", planned, "nodes-planned"))
    components.kpi_row(tiles)
    with st.expander(f"🔎 Records behind these tiles — {period_label}"):
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


def _pipeline(fact: pd.DataFrame, waves: kpi.WaveIndex, key: str) -> None:
    # Deliberately not given the reporting period: this section answers "where
    # does the pipeline stand right now", which no date window should narrow.
    section("Current pipeline", help=glossary.PIPELINE,
            period="Current state — not filtered by the reporting period")
    st.caption("Every account in this category read across all of its waves, "
               "whatever its nomination date. On-Track and Completed only — "
               "blocked and waiting accounts are reported below, under "
               "**Blocked & waiting accounts**. Pick a state "
               "below the doughnut, or click a bar or table row, to open the "
               "accounts behind it.")
    states, state_rows = kpi.by_state(fact, lasts=waves.last)
    stages, stage_rows = kpi.on_track_by_stage(fact, lasts=waves.last)

    subheading("Nominations by state", help=glossary.BY_STATE,
               period="Current state — not filtered by the reporting period")
    if states.empty:
        components.empty_state("No On-Track or Completed accounts to report.")
    else:
        fig = charts.donut(states, "category", "count", height=320)
        counts = dict(zip(states["category"], states["count"]))
        picked: list[str] = []
        left, right = st.columns([3, 2])
        with left:
            drilldown.selectable_chart(fig, key=f"{key}_state")
            # The chips are the donut's click target: Streamlit reports no
            # selection points for a pie trace, so the slice itself cannot
            # filter however it is configured.
            picked += drilldown.selectable_slices(
                list(states["category"]), key=f"{key}_state_pills", counts=counts)
        with right:
            picked += drilldown.selectable_table(
                states.rename(columns={"category": "State", "count": "Accounts",
                                       "acr": "ACR"}),
                key=f"{key}_state_table", bucket_col="State")
        drilldown.drilldown(state_rows.assign(bucket=state_rows["state"]), "bucket",
                            picked, key=f"{key}_state", what="accounts")

    _reconciliation(fact, waves, key)

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


def _top_accounts(fact: pd.DataFrame, waves: kpi.WaveIndex, key: str) -> None:
    """The ten accounts carrying the most ACR, and the records behind them.

    Not narrowed by the reporting period, like the pipeline above it: the
    question is where this category's money sits, which a window would answer
    only for the window.  ACR is summed across every wave of an account, so the
    order is the account-level one the reconciliation and the account records
    both use.
    """
    section(f"Top {kpi.TOP_ACCOUNTS} accounts by ACR",
            help=glossary.TOP_ACCOUNTS_ACR,
            period="All time — not filtered by the reporting period")
    summary, rows = kpi.top_accounts_by_acr(fact, approvals=waves.approval,
                                            lasts=waves.last)
    if summary.empty:
        components.empty_state("No account in this category carries any ACR.")
        return
    total = float(pd.to_numeric(fact.get("total_acr"), errors="coerce").sum())
    shown = float(summary["acr"].sum())
    share = f" — **{shown / total:.0%}** of the category's ACR" if total else ""
    st.caption(f"Total ACR summed across every wave of each account. These "
               f"**{fmt_int(len(summary))}** accounts carry "
               f"**{fmt_currency(shown)}**{share}. Click a bar or a table row "
               f"to open the account behind it.")
    fig = charts.bar(summary, "category", "acr", horizontal=True, currency=True,
                     height=380)
    drilldown.chart_with_drilldown(
        fig, rows.assign(bucket=rows["account_label"]), "bucket",
        key=f"{key}_topacr", what="accounts",
        summary=summary.rename(columns={"category": "Account", "acr": "Total ACR",
                                        "count": "Waves"}),
        summary_bucket="Account")


def _reconciliation(fact: pd.DataFrame, waves: kpi.WaveIndex, key: str) -> None:
    """Where every account sits — the chart above plus everything it leaves out.

    "The doughnut shows 32 of my 36 accounts, where are the other four?" is a
    fair question, and this is the answer: every account resolves to exactly one
    state, so these rows add up, and the last column says where each is
    reported — including the states reported nowhere, and why.
    """
    rows, accounts = exporter.reconciliation(fact, waves)
    if rows.empty:
        return
    with st.expander(f"🔎 Where every account sits ({fmt_int(accounts)} accounts)"):
        st.caption("Each account is in exactly one row, so these add up. The "
                   "doughnut above shows the first two rows; the rest are "
                   "reported where this says.")
        components.show_table(rows)


def _regional_breakdown(fact: pd.DataFrame, waves: kpi.WaveIndex, key: str) -> None:
    """Where the category sits geographically, by migration status.

    Account-grain (each TPID's latest wave), so an account with five waves is one
    account here rather than five rows — which is what the state chart above it
    counts too.

    **One** chart: the stacked bar that used to sit beside the heatmap carried
    the same region × stage counts, and two pictures of one cut is one too many.
    The heatmap keeps the numbers in its cells; the summary beside it is what a
    reader clicks to open the accounts, since a heatmap cell cannot be selected
    in Streamlit.
    """
    section("Regional breakdown", help=glossary.REGIONAL_BREAKDOWN,
            period="Current state — not filtered by the reporting period")
    st.caption("Accounts at their latest wave, by WW Region and migration status — "
               "the four in-flight stages and Completed only. Stages are shown by "
               "their code, with the key below the chart. Pick a row of the "
               "summary to open exactly the accounts in that region *and* that "
               "stage.")
    rows = waves.last
    if rows.empty or "region_geo" not in rows.columns:
        components.empty_state("No regional data to report.")
        return
    rows = rows[kpi.reported_stages(rows)]
    if rows.empty:
        components.empty_state(
            "No accounts are in a reported migration stage — every account here "
            "is deferred or cancelled.")
        return
    stages_short, stage_key = kpi.stage_labels(rows)
    rows = rows.assign(
        _status=stages_short,
        _region=rows["region_geo"].astype("string")
                                  .replace({"": pd.NA}).fillna("Unknown"))
    pivot = pd.crosstab(rows["_status"], rows["_region"])
    heat = pd.crosstab(rows["_region"], rows["_status"])

    c1, c2 = st.columns([3, 2])
    with c1:
        st.plotly_chart(charts.heatmap(heat, title="WW Region × status heatmap"),
                        width="stretch")
    with c2:
        # Long form, one row per region/stage pair: the selectable stand-in for
        # clicking a heatmap cell, which Streamlit reports no points for.
        pairs = (heat.stack().rename("Accounts").reset_index()
                 .rename(columns={"_region": "WW Region", "_status": "Stage"}))
        pairs = pairs[pairs["Accounts"] > 0]
        pairs["Region · Stage"] = (pairs["WW Region"].astype(str)
                                   + _REGION_STAGE_JOIN
                                   + pairs["Stage"].astype(str))
        picked = drilldown.selectable_table(
            pairs[["WW Region", "Stage", "Accounts", "Region · Stage"]],
            key=f"{key}_region_table", bucket_col="Region · Stage")

    if stage_key:
        st.caption("**Stage key** — " + " · ".join(
            f"**{short}** {name}" for short, name in stage_key))

    records = rows.assign(
        bucket=rows["_region"].astype(str) + _REGION_STAGE_JOIN
        + rows["_status"].astype(str))
    drilldown.drilldown(records, "bucket", picked, key=f"{key}_region",
                        what="accounts")
    drilldown.data_expander(
        pivot.reset_index().rename(columns={"_status": "Stage"}),
        f"{key}_region_grid", label="Underlying data — stage × WW Region",
        caption="Account counts per migration stage and WW Region: the numbers "
                "the heatmap above is drawn from.")


def _blocked_accounts(fact: pd.DataFrame, waves: kpi.WaveIndex, key: str) -> None:
    """Accounts that have stopped — blocked, or waiting on a follow-up.

    Deliberately a section of its own rather than extra slices on the pipeline
    chart: these accounts are neither delivering nor delivered, so folding them
    into either number would misstate both.  What they are is where a programme
    review spends its time, so the Current State that stopped each one is the
    breakdown and the programme's own **Status Summary** is on every row.
    """
    section(exporter.BLOCKED_TITLE, help=glossary.BLOCKED_ACCOUNTS,
            period="Current state — not filtered by the reporting period")
    st.caption("Every account that is neither On-Track nor Completed, grouped "
               "by why. The blocking Current States — **Blocked**, **Blocked - "
               "Account team**, **Blocked - Customer**, **Blocked - Partner / "
               "ISD**, **Waiting action on follow up date** — with **Deferred "
               "By Customer** and **Cancelled / Archived** broken out by "
               "Migration Status, since those are decisions rather than "
               "blockages. They are in **none** of the metrics above, and those "
               "metrics are in none of these numbers.")
    summary, rows = kpi.blocked_accounts(fact, lasts=waves.last)
    if rows.empty:
        components.empty_state("Nothing has stopped — every account here is "
                               "On-Track or Completed.")
        return
    acr = pd.to_numeric(rows.get("total_acr"), errors="coerce").sum()
    components.kpi_row([
        {"label": "Stopped Accounts", "value": fmt_int(rows["tpid_key"].nunique()),
         "tone": "warn", "sub": "not in any metric above"},
        {"label": "ACR Held Up", "value": fmt_currency(acr), "tone": "warn",
         "sub": "summed over those accounts"},
        {"label": "Reasons", "value": fmt_int(len(summary)),
         "sub": "distinct reasons they are stopped"},
    ])

    c1, c2 = st.columns([3, 2])
    with c1:
        picked = drilldown.selectable_chart(
            charts.bar(summary, "category", "count", color_status=True,
                       title="Accounts by reason"), key=f"{key}_blocked")
    with c2:
        picked += drilldown.selectable_table(
            summary.rename(columns={"category": "Reason",
                                    "count": "Accounts", "acr": "ACR"}),
            key=f"{key}_blocked_table", bucket_col="Reason")
    drilldown.drilldown(rows.assign(bucket=rows["blocked_state"]), "bucket",
                        picked, key=f"{key}_blocked_rows", what="accounts",
                        unit_col="total_acr",
                        columns=kpi.BLOCKED_DRILLDOWN_COLUMNS)

    left, right = st.columns(2)
    with left:
        subheading("Waves behind these accounts")
        st.caption("An account blocked on its fifth wave is a different problem "
                   "from one blocked on its first.")
        components.show_table(kpi.wave_profile(fact, rows).rename(
            columns={"category": "Waves", "count": "Accounts"}))
    with right:
        if "region_geo" in rows.columns:
            subheading("By WW Region")
            st.caption("Where the stopped accounts sit.")
            region = pd.crosstab(
                rows["region_geo"].astype("string").replace({"": pd.NA}).fillna("Unknown"),
                rows["blocked_state"])
            st.plotly_chart(charts.heatmap(region, title="WW Region × reason",
                                           height=300), width="stretch")


def _offering_and_target(fact: pd.DataFrame, key: str) -> None:
    """The AVS → Azure Native cut, on all three of its own columns.

    **Factory Offering and Primary Migration Path are different columns.** The
    offering says which factory delivers the work (SQL, Windows, Linux, OSS DB
    Nominations); the path says what moves where ("SQL Server MI Migration
    (From AVS)"), and the Azure-native target is read from it.  Each gets its
    own chart, because one never stood for the other.

    Lives here rather than on the status report because this is the page that
    owns the motion — one place to read it, not two.
    """
    section("By offering, path & target", help=glossary.OFFERING_AND_TARGET,
            period="Every nomination in this category — not filtered by the "
                   "reporting period")
    st.caption("The **Factory Offering** that delivers the work, the **Primary "
               "Migration Path** that says what moves where, and the "
               "Azure-native service the path lands on. Click a bar or slice to "
               "open the nominations behind it.")
    offerings = _count_by(fact, "factory_offering")
    paths = _count_by(fact, "migration_path")
    targets = _count_by(fact, "azure_target")
    c1, c2 = st.columns(2)
    with c1:
        picked_offering = drilldown.selectable_chart(
            charts.bar(offerings, "category", "count", horizontal=True,
                       title="Nominations by Factory Offering"),
            key=f"{key}_offering")
    with c2:
        picked_target = drilldown.selectable_chart(
            charts.donut(targets, "category", "count", title="Azure-native targets"),
            key=f"{key}_target")
    picked_path = drilldown.selectable_chart(
        charts.bar(paths, "category", "count", horizontal=True,
                   title="Nominations by Primary Migration Path"),
        key=f"{key}_path")
    drilldown.drilldown(fact, "factory_offering", picked_offering,
                        key=f"{key}_offering_rows", what="nominations by offering",
                        max_rows=500)
    drilldown.drilldown(fact, "migration_path", picked_path,
                        key=f"{key}_path_rows", what="nominations by migration path",
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
    st.caption("**One row per account (TPID)** — never one row per wave. Each row "
               "reads as where that account stands now: wave-specific fields and "
               "Current State from its latest wave, **Total ACR summed across every "
               "wave**, and the nomination approval date from its earliest wave.")
    limit = st.checkbox("Limit to the reporting period", value=start is not None,
                        key=f"{key}_limit", disabled=start is None,
                        help="Keeps only accounts whose nomination approval date "
                             "(earliest wave) falls inside the selected window.")
    rows = kpi.account_detail(fact, approvals=waves.approval, lasts=waves.last)
    if limit and start is not None:
        rows = rows[kpi.in_window(rows["approval_date"], start, end)]
        if rows.empty:
            components.empty_state(
                "No accounts were nominated inside the reporting period. Widen the "
                "period above, or untick **Limit to the reporting period**.")
            return
    drilldown.pivot_explorer(rows, key=f"{key}_pivot")
    frame = kpi.drilldown_frame(rows).rename(
        columns={"phase": kpi.LATEST_WAVE_COLUMN})
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
