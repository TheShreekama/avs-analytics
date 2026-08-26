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
from app.core import kpi, segments
from app.core.metrics import fmt_currency, fmt_int
from app.ui import charts, components, drilldown
from app.ui.theme import banner, page_header, section

_DESCRIPTIONS = {
    segments.CAT_EOS_GEN1:
        "End-of-support migrations for TPIDs on Gen-1 hosts (any wave carrying "
        "AV36, AV36P, AV48 or AV52).",
    segments.CAT_EOS_GEN2:
        "End-of-support migrations for TPIDs whose only populated SKU across every "
        "wave is AV64 (Gen-2).",
    segments.CAT_EOS_UNCLASSIFIED:
        "EOS TPIDs whose SKU values are blank or do not match the Gen-1 / Gen-2 "
        "rules. Shown separately — never folded into a generation.",
    segments.CAT_ALL_AVS:
        "Every migration whose target platform is AVS — on-premises, VMG, AWS/VMC, "
        "AVS-to-AVS and EOS refreshes alike.",
    segments.CAT_AVS_NATIVE:
        "Migrations away from AVS to Azure-native services (the '(From AVS)' offerings).",
}


def render(category: str) -> None:
    ctx = state.ensure_context()
    label = segments.CATEGORY_LABELS[category]
    page_header(label, _DESCRIPTIONS.get(category, ""))
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
        components.empty_state(
            f"No nominations fall into **{label}**. "
            "Check the Column Mapping page — the AVS SKU Type and Primary Migration "
            "Path columns drive this classification.")
        return

    # One wave sort for the whole page: every metric below reuses it.
    waves = kpi.wave_index(fact)
    _executive_summary(fact, waves, start, end, key)
    _trends(fact, waves, start, end, key)
    _pipeline(fact, waves, key)
    _detailed_data(fact, waves, start, end, key)


# --------------------------------------------------------------------------- #
def _population_note(ctx, category: str, fact: pd.DataFrame) -> None:
    tpids = fmt_int(segments.tpid_key(fact).nunique()) if not fact.empty else "0"
    bits = [f"<b>{tpids}</b> TPIDs · <b>{fmt_int(len(fact))}</b> nomination waves"]
    if category in (segments.CAT_EOS_GEN1, segments.CAT_EOS_GEN2,
                    segments.CAT_EOS_UNCLASSIFIED):
        source = ("the uploaded <b>EOS worksheet</b>" if ctx.eos_tpids
                  else "EOS markers on the offering / migration path "
                       "(upload an EOS worksheet on <b>Data &amp; Upload</b> to pin the "
                       "population to its TPID list)")
        bits.append(f"EOS population from {source}")
    banner(" · ".join(bits))


def _executive_summary(fact: pd.DataFrame, waves: kpi.WaveIndex, start, end, key: str) -> None:
    section("Executive summary")
    engagements = kpi.new_engagements(fact, start, end, firsts=waves.first)
    ends = kpi.migration_ends(fact, start, end, lasts=waves.last)
    hosts = kpi.hosts_migrated(fact, start, end)
    approved = kpi.nominations_approved(fact, start, end)
    states, state_rows = kpi.by_state(fact, lasts=waves.last)
    on_track = int(states.loc[states["category"] == kpi.STATE_ON_TRACK, "count"].sum())

    components.kpi_row([
        {"label": "New Engagements", "value": fmt_int(engagements.value),
         "sub": "unique TPIDs, Wave-1 approval"},
        {"label": "Migrations Ended", "value": fmt_int(ends.value),
         "sub": "latest wave completed", "tone": "good"},
        {"label": "Hosts Migrated", "value": fmt_int(hosts.value),
         "sub": "sum of Total Cores"},
        {"label": "Nominations Approved", "value": fmt_int(approved.value),
         "sub": "in the selected period"},
        {"label": "On-Track Accounts", "value": fmt_int(on_track), "tone": "warn"},
        {"label": "Total ACR", "value": fmt_currency(kpi.current_acr(fact))},
    ])
    with st.expander("🔎 Records behind these tiles"):
        tabs = st.tabs(["New Engagements", "Migrations Ended", "Hosts Migrated",
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


def _trends(fact: pd.DataFrame, waves: kpi.WaveIndex, start, end, key: str) -> None:
    section("Trends — month over month")
    basis = st.radio(
        "Trend basis", ["Nomination approval date", "Nomination created date"],
        horizontal=True, key=f"{key}_basis",
        help="Which Wave-1 date places a TPID in a month.")
    date_col = "approval_date" if basis.startswith("Nomination approval") else "created_date"

    noms, nom_rows = kpi.monthly_unique_tpids(fact, date_col, start, end, firsts=waves.first)
    acr, acr_rows = kpi.monthly_acr(fact, date_col, start, end, firsts=waves.first)
    hosts, host_rows = kpi.monthly_hosts(fact, start, end)

    for title, table, rows, value_col, unit_col, what in [
        ("Nomination count (unique TPIDs)", noms, nom_rows, "Nominations", None, "nominations"),
        ("ACR", acr, acr_rows, "ACR", "total_acr", "TPID ACR records"),
        ("Hosts migrated (Total Cores)", hosts, host_rows, "Hosts", "total_cores", "wave records"),
    ]:
        st.markdown(f"**{title}**")
        if table.empty:
            components.empty_state(f"No {what} in the selected period.")
            continue
        left, right = st.columns([3, 2])
        with left:
            fig = charts.line(table, "period", value_col, area=True, height=320)
            charts.add_line(fig, table, "period", "Cumulative")
            drilldown.chart_with_drilldown(
                fig, _with_period(rows, date_col if value_col != "Hosts" else "actual_end_date"),
                "period", key=f"{key}_{value_col}", what=what, unit_col=unit_col)
        with right:
            components.show_table(_display_trend(table), height=320)
        st.write("")


def _pipeline(fact: pd.DataFrame, waves: kpi.WaveIndex, key: str) -> None:
    section("Current pipeline")
    states, state_rows = kpi.by_state(fact, lasts=waves.last)
    stages, stage_rows = kpi.on_track_by_stage(fact, lasts=waves.last)

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Nominations by state**")
        if states.empty:
            components.empty_state("No accounts to report.")
        else:
            state_rows = state_rows.assign(bucket=state_rows["state"])
            fig = charts.donut(states, "category", "count", height=320)
            drilldown.chart_with_drilldown(fig, state_rows, "bucket",
                                           key=f"{key}_state", what="accounts")
            components.show_table(_money(states.rename(
                columns={"category": "State", "count": "Accounts", "acr": "ACR"})))
    with c2:
        st.markdown("**On-track nominations by stage**")
        if stages.empty:
            components.empty_state("No on-track accounts to report.")
        else:
            stage_rows = stage_rows.assign(bucket=stage_rows["stage"])
            fig = charts.bar(stages, "category", "count", horizontal=True, height=320)
            drilldown.chart_with_drilldown(fig, stage_rows, "bucket",
                                           key=f"{key}_stage", what="accounts")
            components.show_table(_money(stages.rename(
                columns={"category": "Stage", "count": "Accounts", "acr": "ACR"})))


def _detailed_data(fact: pd.DataFrame, waves: kpi.WaveIndex, start, end, key: str) -> None:
    section("Detailed data")
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


def _display_trend(table: pd.DataFrame) -> pd.DataFrame:
    """Month, value and the Cumulative column — cumulative always last."""
    out = table.drop(columns=["month"]).rename(columns={"period": "Month"})
    value_col = [c for c in out.columns if c not in ("Month", "Cumulative")]
    return out[["Month", *value_col, "Cumulative"]]


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
