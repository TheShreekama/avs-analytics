"""Report 5 — AVS Nomination Trends (volume over time)."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from app import state
from app.config import SCOPE_PRIMARY
from app.core import analytics
from app.core.metrics import fmt_int, pct_delta
from app.ui import charts, components
from app.ui.theme import page_header, section


def render() -> None:
    ctx = state.ensure_context()
    table = state.active_table()
    analytics.use_table(table)
    page_header("AVS Nomination Trends",
                "Nomination volume over time with growth, peaks, troughs and seasonality.")
    components.data_quality_banner(ctx)
    components.banner_note("<b>Scope:</b> AVS Migration Nominations (onboarding to AVS).")

    filters, where = components.filter_sidebar(
        ctx, ["region_geo", "migration_path", "migration_status_label"],
        date_field="created_date", table=table, scope=SCOPE_PRIMARY)

    con = ctx.con
    view = st.radio("View", ["Monthly", "Quarterly", "Yearly"], horizontal=True, key="nt_view")
    gmap = {"Monthly": "month", "Quarterly": "quarter", "Yearly": "year"}
    ts = analytics.timeseries(con, where, "created_date", gmap[view])
    if ts.empty:
        components.empty_state("No nominations with creation dates in the current selection.")
        return

    # Headline trend stats
    total = int(ts["value"].sum())
    peak = ts.loc[ts["value"].idxmax()]
    trough = ts.loc[ts["value"].idxmin()]
    growth = pct_delta(ts["value"].iloc[-1], ts["value"].iloc[0]) if len(ts) > 1 else None
    components.kpi_row([
        {"label": "Total Nominations", "value": fmt_int(total)},
        {"label": f"Peak {view[:-2] if view!='Yearly' else 'Year'}",
         "value": fmt_int(int(peak["value"])), "sub": _fmt_period(peak["period"], view)},
        {"label": "Trough", "value": fmt_int(int(trough["value"])),
         "sub": _fmt_period(trough["period"], view)},
        {"label": "First→Last Growth",
         "value": (f"{growth:+.0f}%" if growth is not None else "—"),
         "tone": "good" if (growth or 0) >= 0 else "bad"},
    ])
    st.write("")

    section(f"{view} nomination volume")
    chart_type = st.radio("Chart", ["Area", "Line", "Bar"], horizontal=True, key="nt_chart")
    if chart_type == "Bar":
        fig = charts.bar(ts.assign(period=ts["period"].apply(lambda p: _fmt_period(p, view))),
                         "period", "value")
    else:
        fig = charts.line(ts, "period", "value", area=(chart_type == "Area"))
    # annotate peak & trough
    fig.add_annotation(x=peak["period"], y=peak["value"], text="Peak", showarrow=True,
                       arrowhead=2, ay=-30, font=dict(color="#107C41"))
    if trough["period"] != peak["period"]:
        fig.add_annotation(x=trough["period"], y=trough["value"], text="Trough", showarrow=True,
                           arrowhead=2, ay=30, font=dict(color="#C4314B"))
    st.plotly_chart(fig, width="stretch")

    section("Cumulative growth")
    st.plotly_chart(charts.line(ts, "period", "cumulative", area=True, color="#5C2E91",
                                title="Cumulative nominations"), width="stretch")

    section("Trend by dimension")
    dim = st.selectbox("Break down by", ["region_geo", "migration_path", "migration_status_label"],
                       format_func=lambda x: x.replace("_", " ").title(), key="nt_dim")
    grain = gmap[view]
    sql = f'''SELECT date_trunc('{grain}', created_date) AS period, "{dim}" AS series,
              COUNT(*) AS value FROM {table} {where if where else ''}
              {"AND" if where else "WHERE"} created_date IS NOT NULL
              GROUP BY 1,2 ORDER BY 1'''
    long = con.execute(sql).fetchdf()
    if not long.empty:
        long["period"] = pd.to_datetime(long["period"])
        st.plotly_chart(charts.multi_line(long, "period", "series", "value", area=False),
                        width="stretch")

    # Seasonality (month-of-year profile) for monthly view
    if view == "Monthly" and state.active_frame(ctx)["created_date"].notna().sum() >= 12:
        section("Seasonality (month-of-year profile)")
        sql2 = f'''SELECT EXTRACT(month FROM created_date) AS m, COUNT(*) AS value
                   FROM {table} {where if where else ''}
                   {"AND" if where else "WHERE"} created_date IS NOT NULL GROUP BY 1 ORDER BY 1'''
        seas = con.execute(sql2).fetchdf()
        if not seas.empty:
            names = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
            seas["month"] = seas["m"].astype(int).map(lambda i: names[i-1])
            st.plotly_chart(charts.bar(seas, "month", "value", title="Nominations by calendar month"),
                            width="stretch")


def _fmt_period(p, view: str) -> str:
    ts = pd.Timestamp(p)
    if view == "Yearly":
        return f"{ts.year}"
    if view == "Quarterly":
        return f"Q{(ts.month-1)//3 + 1} {ts.year}"
    return ts.strftime("%b %Y")
