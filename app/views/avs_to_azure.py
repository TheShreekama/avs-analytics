"""Report 7 — AVS to Azure Native Migration Trends."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from app.config import SCOPE_FROM_AVS
from app import state
from app.core import analytics
from app.core.metrics import fmt_int, pct_delta
from app.ui import charts, components
from app.ui.theme import banner, page_header, section

_TRACK = "migration_path"   # full offering names, e.g. "SQL Server MI Migration (From AVS)"


def render() -> None:
    ctx = state.ensure_context()
    table = state.active_table()
    analytics.use_table(table)
    unit = state.unit_label()
    page_header("AVS → Azure Native Migration Trends",
                "Migrations from AVS to Azure-native services: flow, adoption and completion.")
    components.data_quality_banner(ctx)
    scope = ("each customer counts once if <b>any</b> wave moves from AVS to an Azure-native "
             "target; status follows the last wave") if state.is_customer_mode() else \
            "every wave whose migration path moves <b>from AVS</b> to an Azure-native target"
    banner(f"<b>Scope:</b> {scope} (SQL DB/MI/IaaS, OSS DB, Azure VM, AKS, Oracle DB@Azure).")

    date_filter = components.page_date_filter(
        ctx, "a2a", "created_date", table=table, scope=SCOPE_FROM_AVS)
    filters, where = components.filter_sidebar(
        ctx, ["region_geo", "migration_path", "azure_target", "eos_status"], table=table, scope=SCOPE_FROM_AVS, date_filter=date_filter)

    con = ctx.con
    # The sidebar scope already constrains to AVS → Azure Native ("(From AVS)").
    base = where
    n = analytics.total_rows(con, base)
    if n == 0:
        components.empty_state("No AVS→Azure-Native migrations in the current selection.")
        return

    stage = analytics.migration_stage_by_track(con, base, track_dim=_TRACK)
    completed = int(stage["completed"].sum())
    in_prog = int(stage["in_progress"].sum())
    started = int(stage["started"].sum())
    comp_rate = round(100 * completed / n, 1) if n else 0
    components.kpi_row([
        {"label": "AVS→Azure Migrations", "value": fmt_int(n)},
        {"label": "Started", "value": fmt_int(started), "tone": "warn"},
        {"label": "In Progress", "value": fmt_int(in_prog)},
        {"label": "Completed", "value": fmt_int(completed), "tone": "good"},
        {"label": "Completion Rate", "value": f"{comp_rate:.0f}%",
         "tone": "good" if comp_rate >= 50 else "warn"},
    ])
    st.write("")

    section("Migration flow (AVS → target service → stage)")
    flow = analytics.sankey_avs_to_azure(con, base, track_dim=_TRACK)
    if not flow.empty:
        nodes, links, node_colors = _build_sankey(flow)
        st.plotly_chart(charts.sankey(nodes, links, node_colors=node_colors,
                                      title="AVS migration flows"),
                        width="stretch")

    section("Track & target distribution")
    c1, c2 = st.columns(2)
    with c1:
        trk = analytics.count_by(con, base, _TRACK)
        st.plotly_chart(charts.bar(trk, "category", "count", horizontal=True,
                                   title="Nominations by migration path (offering)"),
                        width="stretch")
    with c2:
        tgt = analytics.count_by(con, base, "azure_target")
        st.plotly_chart(charts.donut(tgt, "category", "count", title="Azure-native targets"),
                        width="stretch")

    section("Migration completion by track")
    if not stage.empty:
        st.plotly_chart(
            charts.grouped_bar(stage, "track", ["started", "in_progress", "completed"],
                               title="Delivery stage by track"),
            width="stretch")

    section("Adoption trend over time")
    c3, c4 = st.columns(2)
    with c3:
        ts = analytics.timeseries(con, base, "created_date", "month")
        if not ts.empty:
            st.plotly_chart(charts.line(ts, "period", "cumulative", area=True,
                                        title="Cumulative AVS→Azure nominations", color="#5C2E91"),
                            width="stretch")
    with c4:
        sql = f'''SELECT date_trunc('month', created_date) AS period, {_TRACK} AS series,
                  COUNT(*) AS value FROM {table} {base}
                  AND created_date IS NOT NULL GROUP BY 1,2 ORDER BY 1'''
        long = con.execute(sql).fetchdf()
        if not long.empty:
            long["period"] = pd.to_datetime(long["period"])
            st.plotly_chart(charts.multi_line(long, "period", "series", "value",
                                              title="Path adoption per month"),
                            width="stretch")

    # Insights
    section("Migration insights")
    _migration_insights(con, base, where, n, completed, stage)

    section("Backlog — open AVS→Azure migrations")
    open_where = analytics._where_and(base, '"is_open" = TRUE')
    cols = ["customer_name", "migration_path", "azure_target", "region_geo", "eos_status", "aging_days"]
    cols = [c for c in cols if c in ctx.fact.columns]
    components.show_table(analytics.fetch_rows(con, open_where, cols, "aging_days", True, 50),
                          height=360)


def _build_sankey(flow: pd.DataFrame):
    """Two-stage Sankey: track → target → stage."""
    tracks = sorted(flow["track"].dropna().unique())
    targets = sorted(flow["target"].dropna().unique())
    stages = ["Started", "In Progress", "Completed"]
    stages = [s for s in stages if s in set(flow["stage"])]
    nodes = tracks + targets + stages
    idx = {name: i for i, name in enumerate(nodes)}

    links = []
    tt = flow.groupby(["track", "target"])["count"].sum().reset_index()
    for _, r in tt.iterrows():
        links.append((idx[r["track"]], idx[r["target"]], float(r["count"])))
    ts = flow.groupby(["target", "stage"])["count"].sum().reset_index()
    for _, r in ts.iterrows():
        links.append((idx[r["target"]], idx[r["stage"]], float(r["count"])))

    from app.config import CATEGORICAL_SEQUENCE, STATUS_COLORS
    colors = []
    for i, name in enumerate(nodes):
        if name in stages:
            colors.append(STATUS_COLORS.get(name, "#888"))
        else:
            colors.append(CATEGORICAL_SEQUENCE[i % len(CATEGORICAL_SEQUENCE)])
    return nodes, links, colors


def _migration_insights(con, base, where, n, completed, stage) -> None:
    from app.core.insights import Insight
    cards: list[Insight] = []
    # Largest track
    if not stage.empty:
        largest = stage.sort_values("total", ascending=False).iloc[0]
        cards.append(Insight("Azure Native", "Largest migration track",
                             f"**{largest['track']}** is the largest with "
                             f"{fmt_int(int(largest['total']))} migrations.", "info"))
        # Highest completion-rate track
        s2 = stage[stage["total"] >= 1].copy()
        s2["rate"] = s2["completed"] / s2["total"] * 100
        best = s2.sort_values("rate", ascending=False).iloc[0]
        cards.append(Insight("Azure Native", "Highest completion-rate track",
                             f"**{best['track']}** leads completion at {best['rate']:.0f}% "
                             f"({fmt_int(int(best['completed']))}/{fmt_int(int(best['total']))}).",
                             "positive"))

    # Region driving adoption
    reg = analytics.count_by(con, base, "region_geo")
    if not reg.empty:
        cards.append(Insight("Azure Native", "Region driving adoption",
                             f"**{reg.iloc[0]['category']}** drives the most AVS→Azure migrations "
                             f"({fmt_int(int(reg.iloc[0]['count']))}).", "info"))
    # Backlog
    open_n = analytics.total_rows(con, analytics._where_and(base, '"is_open" = TRUE'))
    cards.append(Insight("Azure Native", "Migration backlog",
                         f"{fmt_int(open_n)} of {fmt_int(n)} AVS→Azure migrations are still open "
                         f"({open_n/n*100:.0f}%).", "warning" if open_n else "positive"))
    # Fastest growing (created month over month)
    g = _fastest_growth(con, base)
    if g:
        track, cur, prev, pct = g
        if pct is not None:
            cards.append(Insight("Azure Native", "Fastest-growing track",
                                 f"**{track}** is {'up' if pct>=0 else 'down'} {abs(pct):.0f}% "
                                 f"month-over-month ({fmt_int(prev)}→{fmt_int(cur)}).",
                                 "positive" if pct >= 0 else "warning"))

    components.insight_cards(cards, columns=2)


def _fastest_growth(con, base):
    sql = f'''SELECT created_month, {_TRACK} AS track, COUNT(*) AS c
              FROM {analytics.current_table()} {base}
              AND created_month IS NOT NULL GROUP BY 1,2'''
    df = con.execute(sql).fetchdf()
    if df.empty or df["created_month"].nunique() < 2:
        return None
    months = sorted(df["created_month"].unique())
    cur_m, prev_m = months[-1], months[-2]
    cur = df[df["created_month"] == cur_m].set_index("track")["c"]
    prev = df[df["created_month"] == prev_m].set_index("track")["c"]
    best = None
    for t in set(cur.index) | set(prev.index):
        c, p = int(cur.get(t, 0)), int(prev.get(t, 0))
        pct = pct_delta(c, p) if p else (100.0 if c else 0.0)
        if best is None or (c + p) > best[1] + best[2]:
            best = (t, c, p, round(pct, 1) if pct is not None else None)
    return best
