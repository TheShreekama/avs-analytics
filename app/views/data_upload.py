"""Data & Upload — load a user file or use the bundled sample."""
from __future__ import annotations

import streamlit as st

from app import state
from app.core import loader, mapping as mapmod, segments
from app.version import build_stamp
from app.core.metrics import fmt_int
from app.ui import components
from app.ui.theme import banner, page_header, section


def render() -> None:
    ctx = state.ensure_context()
    page_header("Data & Upload",
                "Load your AVS nominations export. Everything is processed locally on this machine.")
    built, fingerprint = build_stamp()
    banner(f"🧩 Running build <b>{built}</b> · fingerprint <code>{fingerprint}</code> — "
           f"the newest timestamp across this app's Python files. If it does not match "
           f"the copy you just installed, the Streamlit server is still running the old "
           f"code: stop it (Ctrl+C) and start it again.")

    section("Upload a dataset")
    up = st.file_uploader("Choose a file (CSV, XLSX or XLS)", type=["csv", "xlsx", "xls"],
                          accept_multiple_files=False)
    cols = st.columns([1, 1, 3])
    with cols[0]:
        if st.button("Use sample dataset", width="stretch"):
            state.load_sample()
            st.success("Loaded the bundled sample dataset.")
            st.rerun()

    if up is not None:
        data = up.getvalue()
        try:
            new = state.build_context(up.name, data)
        except Exception as exc:  # noqa: BLE001 - surface parse errors to the user
            st.error(f"Could not read the file: {exc}")
            return
        st.session_state["avs_raw_bytes"] = data
        state.set_context(new)
        cov = mapmod.mapping_coverage(new.mapping)
        if cov["ok"]:
            banner(f"✅ Loaded <b>{up.name}</b> — {fmt_int(len(new.raw))} rows, "
                   f"{len(new.raw.columns)} columns. {cov['mapped']} fields auto-mapped.")
        else:
            banner(f"⚠️ Loaded <b>{up.name}</b>, but required fields are unmapped: "
                   f"{', '.join(cov['missing_required'])}. Open <b>Column Mapping</b> to fix.", "warn")
        st.rerun()

    # Active dataset summary
    section("Active dataset")
    src = "Bundled sample" if ctx.is_sample else ctx.filename
    rep = ctx.report
    components.kpi_row([
        {"label": "Source", "value": src},
        {"label": "Rows", "value": fmt_int(len(ctx.fact))},
        {"label": "Source Columns", "value": fmt_int(len(ctx.raw.columns))},
        {"label": "Mapped Fields", "value": fmt_int(mapmod.mapping_coverage(ctx.mapping)["mapped"])},
        {"label": "DQ Rows", "value": fmt_int(rep.get("dq_rows", 0)),
         "tone": "warn" if rep.get("dq_rows") else "good"},
    ])

    if rep.get("duplicate_task_ids"):
        banner(f"⚠️ {rep['duplicate_task_ids']} duplicate Task IDs detected.", "warn")

    _classification_panel(ctx)

    section("Source column profile")
    st.caption("Fill rate and sample values for every column in the uploaded file. "
               "Empty columns are detected automatically and excluded from analytics.")
    fill = loader.column_fill_report(ctx.raw)
    st.dataframe(fill, width="stretch", height=420, hide_index=True,
                 column_config={"fill_pct": st.column_config.ProgressColumn(
                     "Fill %", min_value=0, max_value=100, format="%.0f%%")})


def _classification_panel(ctx) -> None:
    """What the classification actually made of this file.

    The categories hinge on three columns — Tags, Primary Migration Path and
    Factory Offering — so when a dashboard looks empty this is where you see why.
    """
    section("How this file was classified")
    fact = ctx.fact
    summary = segments.category_summary(fact)
    components.show_table(summary.rename(columns={
        "category": "Category", "tpids": "Accounts (TPID)", "nominations": "Nomination waves"}))

    gen = (fact.drop_duplicates("tpid_key")["generation"]
               .value_counts(dropna=False).rename_axis("Generation")
               .reset_index(name="Accounts (TPID)"))
    cols = st.columns(2)
    with cols[0]:
        st.markdown("**Generation split** (per TPID, from the Tags column)")
        components.show_table(gen)
    with cols[1]:
        st.markdown("**Most common Tags values**")
        tags = (fact["tags"].astype("string").fillna("(blank)")
                    .value_counts().head(10).rename_axis("Tags")
                    .reset_index(name="Rows"))
        components.show_table(tags)
    section("Data consistency — tag vs. EOS migration path")
    components.consistency_panel(ctx)

    st.caption("A generation is read from a wave tagged **AVS Migration - Gen1** or "
               "**- Gen2** anywhere in the Tags cell. If everything lands in "
               "Unclassified, check the Tags values above — and that Tags is mapped "
               "on the Column Mapping page.")
