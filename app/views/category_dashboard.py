"""The standard dashboard, rendered once per migration category.

EOS Migration (Gen-1, Gen-2, Unclassified), All AVS Migrations and AVS → Azure
Native all follow the same structure, so they share this module and differ only
in which population they select:

  1. **Executive Summary** — new engagements, migrations ended, hosts migrated,
     nominations approved, on-track accounts, ACR.
  2. **Trends** — nomination count, ACR and hosts month over month, each table
     ending in a Cumulative column.
  3. **Current Pipeline** — nominations by state, on-track accounts by stage.
  4. **Detailed Data** — every record behind the numbers, groupable and exportable.

Every chart is selectable: clicking a month, bar or slice opens the records that
produced it.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from app import state
from app.core import glossary, kpi, segments
from app.core.metrics import fmt_currency, fmt_int
from app.ui import charts, components, drilldown
from app.ui.theme import banner, page_header, section, subheading

# The AVS → Azure Native motion moves *cores* to Azure-native services; the AVS
# categories move *hosts*.  Both are the Total Cores column — only the noun differs.
def _unit(category: str) -> tuple[str, str]:
    if category == segments.CAT_AVS_NATIVE:
        return "Cores Migrated", "Cores"
    return "Hosts Migrated", "Hosts"


_DESCRIPTIONS = {
    segments.CAT_EOS_GEN1:
        "Accounts with an \"AVS Migration - Gen1\" tag on any wave — one tagged wave "
        "brings the whole account in.",
    segments.CAT_EOS_GEN2:
        "Accounts with an \"AVS Migration - Gen2\" tag on any wave — one tagged wave "
        "brings the whole account in.",
    segments.CAT_EOS_UNCLASSIFIED:
        "EOS accounts matched by their migration path (\"AV36/AV36P/AV52 - EOS\") "
        "because no wave carries a generation tag. Never folded into a generation.",
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
        start, end, _shown = components.report_date_range(ctx, key)
    with top[1]:
        _population_note(ctx, category, fact)

    if fact.empty:
        components.empty_state(f"No nominations fall into **{label}**.")
        _why_empty(ctx, category)
        return

    # One wave sort for the whole page: every metric below reuses it.
    waves = kpi.wave_index(fact)
    unit_label, unit_short = _unit(category)
    _executive_summary(fact, waves, start, end, key, unit_label, category)
    _trends(fact, waves, start, end, key, unit_label, unit_short)
    _pipeline(fact, waves, key)
    _detailed_data(fact, waves, start, end, key)


# --------------------------------------------------------------------------- #
def _population_note(ctx, category: str, fact: pd.DataFrame) -> None:
    tpids = fmt_int(segments.tpid_key(fact).nunique()) if not fact.empty else "0"
    bits = [f"<b>{tpids}</b> TPIDs · <b>{fmt_int(len(fact))}</b> nomination waves"]
    if category in (segments.CAT_EOS_GEN1, segments.CAT_EOS_GEN2,
                    segments.CAT_EOS_UNCLASSIFIED):
        bits.append("scope from the <b>AVS Migration - Gen1/Gen2</b> tag on any wave, "
                    "or the <b>AV36/AV36P/AV52 - EOS</b> path when untagged")
    banner(" · ".join(bits))


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


def _executive_summary(fact: pd.DataFrame, waves: kpi.WaveIndex, start, end, key: str,
                       unit_label: str, category: str) -> None:
    section("Executive summary", help=glossary.EXECUTIVE_SUMMARY)
    engagements = kpi.new_engagements(fact, start, end, firsts=waves.first)
    ends = kpi.migration_ends(fact, start, end, lasts=waves.last)
    hosts = kpi.hosts_migrated(fact, start, end)
    approved = kpi.nominations_approved(fact, start, end)
    states, state_rows = kpi.by_state(fact, lasts=waves.last)
    on_track = int(states.loc[states["category"] == kpi.STATE_ON_TRACK, "count"].sum())

    cores_help = (glossary.CORES_MIGRATED if category == segments.CAT_AVS_NATIVE
                  else glossary.HOSTS_MIGRATED)
    components.kpi_row([
        {"label": "New Engagements", "value": fmt_int(engagements.value),
         "sub": "unique TPIDs, Wave-1 approval", "help": glossary.NEW_ENGAGEMENTS},
        {"label": "Migrations Ended", "value": fmt_int(ends.value),
         "sub": "latest wave completed", "tone": "good", "help": glossary.MIGRATION_ENDS},
        {"label": unit_label, "value": fmt_int(hosts.value),
         "sub": "sum of Total Cores", "help": cores_help},
        {"label": "Nominations Approved", "value": fmt_int(approved.value),
         "sub": "in the selected period", "help": glossary.NOMINATIONS_APPROVED},
        {"label": "On-Track Accounts", "value": fmt_int(on_track), "tone": "warn",
         "help": glossary.ON_TRACK_ACCOUNTS},
        {"label": "Total ACR", "value": fmt_currency(kpi.current_acr(fact)),
         "help": glossary.TOTAL_ACR},
    ])
    with st.expander("🔎 Records behind these tiles"):
        tabs = st.tabs(["New Engagements", "Migrations Ended", unit_label,
                        "Nominations Approved"])
        for tab, metric, name in zip(
                tabs, [engagements, ends, hosts, approved],
                ["new-engagements", "migrations-ended", "hosts-migrated", "approved"]):
            with tab:
                frame = kpi.drilldown_frame(metric.records)
                components.show_table(frame, height=320)
                st.download_button("⬇️ Export to CSV",
                                   frame.to_csv(index=False).encode("utf-8"),
                                   file_name=f"{key}-{name}.csv", mime="text/csv",
                                   key=f"{key}_{name}_csv")


def _trends(fact: pd.DataFrame, waves: kpi.WaveIndex, start, end, key: str,
            unit_label: str, unit_short: str) -> None:
    section("Trends — month over month", help=glossary.TRENDS)
    st.caption("Click a bar **or a row of the table** to open the records behind "
               "that month.")
    basis = st.radio(
        "Trend basis", ["Nomination approval date", "Nomination created date"],
        horizontal=True, key=f"{key}_basis",
        help="Which Wave-1 date places a TPID in a month.")
    date_col = "approval_date" if basis.startswith("Nomination approval") else "created_date"

    noms, nom_rows = kpi.monthly_unique_tpids(fact, date_col, start, end, firsts=waves.first)
    acr, acr_rows = kpi.monthly_acr(fact, date_col, start, end, firsts=waves.first)
    hosts, host_rows = kpi.monthly_hosts(fact, start, end)
    ends, end_rows = kpi.monthly_migration_ends(fact, start, end, lasts=waves.last)

    trends = [
        ("Nomination count (unique TPIDs)", noms, nom_rows, "Nominations", date_col,
         None, False, "nominations", glossary.TREND_NOMINATIONS),
        ("ACR", acr, acr_rows, "ACR", date_col, "total_acr", True, "TPID ACR records",
         glossary.TREND_ACR),
        (f"{unit_label} (Total Cores)", hosts, host_rows, "Hosts", "actual_end_date",
         "total_cores", False, "wave records", glossary.TREND_HOSTS),
        ("Migrations ended (unique TPIDs)", ends, end_rows, "Migrations Ended",
         "actual_end_date", None, False, "completed migrations", glossary.TREND_ENDS),
    ]
    for title, table, rows, value_col, row_date, unit_col, currency, what, help_text in trends:
        display_col = unit_short if value_col == "Hosts" else value_col
        subheading(title, help=help_text)
        if table.empty:
            components.empty_state(f"No {what} in the selected period.")
            continue
        fig = charts.trend_chart(table, "period", value_col, "Cumulative",
                                 currency=currency, height=320)
        drilldown.chart_with_drilldown(
            fig, _with_period(rows, row_date), "period",
            key=f"{key}_{value_col}".replace(" ", "_"), what=what, unit_col=unit_col,
            summary=_display_trend(table, display_col, currency), summary_bucket="Month")
        st.write("")


def _pipeline(fact: pd.DataFrame, waves: kpi.WaveIndex, key: str) -> None:
    section("Current pipeline", help=glossary.PIPELINE)
    st.caption("Click a slice, bar or table row to open the accounts behind it.")
    states, state_rows = kpi.by_state(fact, lasts=waves.last)
    stages, stage_rows = kpi.on_track_by_stage(fact, lasts=waves.last)

    subheading("Nominations by state", help=glossary.BY_STATE)
    if states.empty:
        components.empty_state("No accounts to report.")
    else:
        fig = charts.donut(states, "category", "count", height=320)
        drilldown.chart_with_drilldown(
            fig, state_rows.assign(bucket=state_rows["state"]), "bucket",
            key=f"{key}_state", what="accounts",
            summary=_money(states.rename(columns={"category": "State", "count": "Accounts",
                                                  "acr": "ACR"})),
            summary_bucket="State")

    subheading("On-track nominations by stage", help=glossary.BY_STAGE)
    if stages.empty:
        components.empty_state("No on-track accounts to report.")
    else:
        fig = charts.bar(stages, "category", "count", horizontal=True, height=320)
        drilldown.chart_with_drilldown(
            fig, stage_rows.assign(bucket=stage_rows["stage"]), "bucket",
            key=f"{key}_stage", what="accounts",
            summary=_money(stages.rename(columns={"category": "Stage", "count": "Accounts",
                                                  "acr": "ACR"})),
            summary_bucket="Stage")


def _detailed_data(fact: pd.DataFrame, waves: kpi.WaveIndex, start, end, key: str) -> None:
    section("Detailed data", help=glossary.DETAILED_DATA)
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
def _with_period(rows: pd.DataFrame, date_col: str) -> pd.DataFrame:
    """Attach the chart's period label to the underlying rows for drill-down."""
    if rows is None or rows.empty:
        return pd.DataFrame()
    out = rows.copy()
    if "month" in out.columns:
        out["period"] = pd.to_datetime(out["month"].astype(str), errors="coerce") \
            .dt.to_period("M").astype(str)
    elif date_col in out.columns:
        out["period"] = pd.to_datetime(out[date_col], errors="coerce") \
            .dt.to_period("M").astype(str)
    return out


def _display_trend(table: pd.DataFrame, display_col: str | None = None,
                   currency: bool = False) -> pd.DataFrame:
    """Month, value and the Cumulative column — cumulative always last.

    Money is shown as $1.2M / $840.0K rather than a raw number.
    """
    out = table.drop(columns=["month"]).rename(columns={"period": "Month"})
    value_cols = [c for c in out.columns if c not in ("Month", "Cumulative")]
    out = out[["Month", *value_cols, "Cumulative"]]
    if currency:
        for col in [*value_cols, "Cumulative"]:
            out[col] = out[col].map(fmt_currency)
    if display_col and value_cols and display_col != value_cols[0]:
        out = out.rename(columns={value_cols[0]: display_col})
    return out


def _money(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "ACR" in out.columns:
        out["ACR"] = out["ACR"].map(fmt_currency)
    return out


# --------------------------------------------------------------------------- #
# Page entry points (st.Page needs a distinct callable per page)
# --------------------------------------------------------------------------- #
def eos_gen1() -> None:
    render(segments.CAT_EOS_GEN1)


def eos_gen2() -> None:
    render(segments.CAT_EOS_GEN2)


def eos_unclassified() -> None:
    render(segments.CAT_EOS_UNCLASSIFIED)


def all_avs() -> None:
    render(segments.CAT_ALL_AVS)


def avs_native() -> None:
    render(segments.CAT_AVS_NATIVE)
