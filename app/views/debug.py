"""Debug — what the app read, and what it decided, for the data loaded right now.

Built to be photographed or copied: the whole diagnosis is one plain-text block
at the top (with a copy button), and the tables below it show the same facts in
full.  Nothing here changes a number.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from app import state
from app.core import diagnostics as dg
from app.ui.theme import banner, page_header, section


def render() -> None:
    ctx = state.ensure_context()
    page_header("Debug",
                "What was read from your files and what each rule made of it. "
                "Copy the block below — or photograph this page — and send it.")
    if ctx.is_sample:
        banner("⚠️ <b>The bundled SAMPLE dataset is loaded, not your file.</b> "
               "Uploads are kept only for the browser session: a page refresh or "
               "an app restart drops them. Upload the FDO Dataset and the EOS "
               "tracking sheet again on <b>Data & Upload</b>, then come back.",
               "warn")

    options = dg.example_tpids(ctx)
    cols = st.columns([2, 2, 3])
    with cols[0]:
        typed = st.text_input("Trace one TPID", key="debug_tpid",
                              placeholder="Type a TPID from your sheet")
    with cols[1]:
        picked = st.selectbox("…or pick one", ["—"] + options, key="debug_pick")
    tpid = typed.strip() or ("" if picked == "—" else picked)

    funnel = dg.eos_funnel(ctx)
    columns = dg.column_report(ctx)
    traced = dg.trace(ctx, tpid) if tpid else None

    section("1 · The whole diagnosis (copy or photograph this)")
    st.code(dg.summary_text(ctx, funnel, columns, traced), language=None,
            wrap_lines=True)

    section("2 · What is loaded")
    st.dataframe(pd.DataFrame(dg.loaded(ctx), columns=["", "Value"]),
                 width="stretch", hide_index=True)

    section("3 · EOS — from the file to the report")
    st.dataframe(funnel, width="stretch", hide_index=True)

    if traced:
        section(f"4 · Trace of TPID {tpid}")
        for line in traced["verdicts"]:
            st.markdown(f"- {line}")
        if not traced["waves"].empty:
            st.markdown("**Its rows in the FDO dataset** — dates as written in "
                        "your file → as read")
            st.dataframe(traced["waves"].T, width="stretch")
        if not traced["sheet"].empty:
            st.markdown("**Its row in the tracking sheet**")
            st.dataframe(traced["sheet"].T, width="stretch")

    section("5 · FDO columns as read")
    st.dataframe(columns, width="stretch", hide_index=True)
    tags = dg.tag_report(ctx)
    if not tags.empty:
        st.markdown("**Most common Tags values, and the generation each reads as**")
        st.dataframe(tags, width="stretch", hide_index=True)

    if ctx.has_tracker:
        section("6 · Tracking sheet")
        st.markdown("**TPIDs on each side, as written and as matched**")
        st.dataframe(dg.tpid_join(ctx), width="stretch", hide_index=True)
        read = ctx.tracker_report or {}
        for key, c in (read.get("date_checks") or {}).items():
            st.markdown(f"**{c['label']}** — column *{c['column'] or 'not found'}* · "
                        f"{c['parsed']} of {c['filled']} read")
            sample = c.get("sample")
            if sample is not None and not sample.empty:
                st.dataframe(sample.rename(columns={"raw": "Written",
                                                    "parsed": "Read as"}),
                             width="stretch", hide_index=True)
            if c["unparsed"]:
                st.caption("Not read: " + ", ".join(c["unparsed"]))
