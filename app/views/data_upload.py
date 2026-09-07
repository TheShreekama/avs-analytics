"""Data & Upload — load one or more user files, or use the bundled sample.

A dataset can be assembled from several exports (the source system exports per
offering, so AVS and "(From AVS)" nominations often arrive as separate files);
they are stacked on their shared headers into one dataset.  When an upload
fails, the whole diagnosis is rendered on the page — stage, cause, origin and
traceback — because these machines have no console in view.
"""
from __future__ import annotations

import traceback

import pandas as pd
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
    st.caption("One file, or several that make up one dataset — an AVS export and "
               "an Azure-native export, say. Files are combined on their shared "
               "column headers and analysed together; every row remembers which "
               "file it came from.")
    ups = st.file_uploader("Choose file(s) (CSV, XLSX or XLS)", type=["csv", "xlsx", "xls"],
                           accept_multiple_files=True)
    cols = st.columns([1, 1, 3])
    with cols[0]:
        if st.button("Use sample dataset", width="stretch"):
            state.load_sample()
            st.success("Loaded the bundled sample dataset.")
            st.rerun()

    if ups:
        files = [(u.name, u.getvalue()) for u in ups]
        label = loader.dataset_label(files)
        try:
            new = state.build_dataset(files)
        except loader.IngestError as err:
            _failure_panel(err.failure)
            return
        except Exception as exc:  # noqa: BLE001 - anything the stages missed
            _failure_panel(loader.IngestFailure(
                filename=label, stage="read", exc_type=type(exc).__name__,
                message=str(exc), hint=loader.explain(str(exc)),
                origin="", detail={}, traceback=_format_exc(exc)))
            return
        state.remember_files(files)
        state.set_context(new)
        cov = mapmod.mapping_coverage(new.mapping)
        if cov["ok"]:
            banner(f"✅ Loaded <b>{label}</b> — {fmt_int(len(new.raw))} rows, "
                   f"{len(new.raw.columns)} columns. {cov['mapped']} fields auto-mapped.")
        else:
            banner(f"⚠️ Loaded <b>{label}</b>, but required fields are unmapped: "
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

    _sources_panel(ctx)

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
    components.consistency_summary(ctx)

    st.caption("A generation is read from a wave tagged **AVS Migration - Gen1** or "
               "**- Gen2** anywhere in the Tags cell. If everything lands in "
               "Unclassified, check the Tags values above — and that Tags is mapped "
               "on the Column Mapping page.")


def _format_exc(exc: BaseException) -> str:
    return "".join(traceback.format_exception(exc))


def _failure_panel(failure: loader.IngestFailure) -> None:
    """Everything known about a failed upload, on the page rather than in a log.

    The app runs on locked-down laptops with no console in view, so a failure
    has to be self-diagnosing: which file, which step, which line of this code,
    what it most likely means, and the raw traceback to paste into a bug report.
    """
    st.error(f"**Could not load {failure.filename}.** "
             f"It failed while **{failure.stage_label.lower()}**.")
    st.markdown(f"**{failure.exc_type}:** `{failure.message}`")
    if failure.hint:
        st.info(f"**Likely cause.** {failure.hint}")
    facts = {"File": failure.filename, "Stage": failure.stage_label}
    facts.update(failure.detail)
    if failure.origin:
        facts["Raised at"] = failure.origin
    components.show_table(pd.DataFrame(
        [{"Detail": k, "Value": v} for k, v in facts.items()]))
    with st.expander("🐞 Full traceback (copy this into a bug report)"):
        st.code(failure.as_text(), language="text")
    st.caption("Nothing was loaded — the previously active dataset is untouched. "
               "Fix the file (or the mapping) and upload again.")


def _sources_panel(ctx) -> None:
    """Which files this dataset was assembled from — only when there is more than one."""
    if ctx.sources is None or len(ctx.sources) < 2:
        return
    section("Files in this dataset")
    st.caption("Files are stacked on their shared headers. **New columns** are the "
               "ones a file introduced; a column another file does not have is "
               "simply blank for that file's rows.")
    components.show_table(ctx.sources.rename(columns={
        "file": "File", "rows": "Rows", "columns": "Columns",
        "new_columns": "New columns", "shared_columns": "Shared columns"}))
    if "source_file" in ctx.fact.columns:
        per_file = (ctx.fact.groupby("source_file")
                    .agg(**{"Nomination waves": ("tpid_key", "size"),
                            "Accounts (TPID)": ("tpid_key", "nunique")})
                    .rename_axis("File").reset_index())
        st.caption("After cleaning and the reporting-year floor:")
        components.show_table(per_file)
