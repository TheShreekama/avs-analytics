"""Column Mapping — map source headers to canonical fields; save/load mappings."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from app import state
from app.core import mapping as mapmod, schema
from app.ui import components
from app.ui.theme import banner, page_header, section


def render() -> None:
    ctx = state.ensure_context()
    page_header("Column Mapping",
                "Map your file's columns to the analytics schema. Save mappings for reuse.")

    saved = mapmod.load_saved_mappings()
    headers = ["—"] + list(ctx.raw.columns)
    cov = mapmod.mapping_coverage(ctx.mapping)

    # Top controls: load a saved mapping / coverage status
    section("Saved mappings")
    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        choice = st.selectbox("Load a saved mapping", ["(auto-mapped)"] + list(saved.keys()))
    with c2:
        if st.button("Apply", width="stretch") and choice != "(auto-mapped)":
            state.reload_with(mapping=mapmod.resolve_mapping(list(ctx.raw.columns), saved[choice]))
            st.success(f"Applied mapping '{choice}'.")
            st.rerun()
    with c3:
        if st.button("Re-auto-map", width="stretch"):
            state.reload_with(mapping=schema.auto_map(list(ctx.raw.columns)))
            st.rerun()

    if cov["ok"]:
        banner(f"✅ {cov['mapped']} of {cov['total']} fields mapped — all required fields present.")
    else:
        banner(f"⚠️ Missing required fields: {', '.join(cov['missing_required'])}.", "warn")

    # Editable mapping grid grouped by role
    section("Field mapping")
    st.caption("For each analytics field, pick the matching column from your file. "
               "Required fields are marked •.")
    new_map: dict[str, str | None] = dict(ctx.mapping)
    with st.form("mapping_form"):
        for role in schema.ROLES:
            fields = [f for f in schema.CANONICAL_FIELDS if f.role == role]
            st.markdown(f"**{role}**")
            grid = st.columns(2)
            for i, f in enumerate(fields):
                cur = ctx.mapping.get(f.key)
                idx = headers.index(cur) if cur in headers else 0
                label = f"{f.label} {'•' if f.required else ''}"
                with grid[i % 2]:
                    sel = st.selectbox(label, headers, index=idx, key=f"map_{f.key}",
                                       help=f.description or None)
                    new_map[f.key] = None if sel == "—" else sel
        submitted = st.form_submit_button("Apply mapping", type="primary")
    if submitted:
        state.reload_with(mapping={k: v for k, v in new_map.items() if v})
        st.success("Mapping applied.")
        st.rerun()

    # Save current mapping
    section("Save current mapping")
    s1, s2 = st.columns([2, 1])
    with s1:
        name = st.text_input("Mapping name", value="Default AVS export")
    with s2:
        st.write("")
        if st.button("💾 Save mapping", width="stretch"):
            mapmod.save_mapping(name, ctx.mapping)
            st.success(f"Saved mapping '{name}'.")

    # Preview
    section("Mapped preview (first 10 rows)")
    preview_cols = [k for k in schema.CANONICAL_BY_KEY if k in ctx.fact.columns][:14]
    components.show_table(ctx.fact[preview_cols].head(10))
