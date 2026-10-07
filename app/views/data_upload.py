"""Data & Upload — load the FDO dataset and the manual EOS tracking sheet.

Two **different documents**, uploaded separately because they are not the same
kind of thing:

* The **FDO Dataset** is the nominations export, and can itself be assembled
  from several files (the source system exports per offering, so AVS and
  "(From AVS)" nominations often arrive apart); they are stacked on their shared
  headers into one dataset.
* The **manual EOS tracking sheet** is the programme's own spreadsheet, keyed on
  TPID.  It is *joined* onto the dataset rather than stacked with it, and
  supplies the answers the export cannot give as well: the Target SDDC
  Generation, the migration start and actual end dates, and — replacing the
  export's — each account's Migration Status and Current State.  Every
  other detail — Factory PM, Solution Architect, region, ACR — is looked up in
  the FDO dataset by TPID.  See :mod:`app.core.eos_tracker`.

When an upload fails, the whole diagnosis is rendered on the page — stage,
cause, origin and traceback — because these machines have no console in view.
"""
from __future__ import annotations

import traceback

import pandas as pd
import streamlit as st

from app import state
from app.core import eos_tracker, loader, mapping as mapmod, segments
from app.version import build_stamp
from app.core.metrics import fmt_int
from app.ui import components
from app.ui.theme import banner, page_header, section, subheading


def render() -> None:
    ctx = state.ensure_context()
    page_header("Data & Upload",
                "Load your AVS nominations export. Everything is processed locally on this machine.")
    built, fingerprint = build_stamp()
    banner(f"🧩 Running build <b>{built}</b> · fingerprint <code>{fingerprint}</code> — "
           f"the newest timestamp across this app's Python files. If it does not match "
           f"the copy you just installed, the Streamlit server is still running the old "
           f"code: stop it (Ctrl+C) and start it again.")

    section("1 · FDO Dataset")
    st.caption("The nominations export. One file, or several that make up one "
               "dataset — an AVS export and an Azure-native export, say. Files "
               "are combined on their shared column headers and analysed "
               "together; every row remembers which file it came from.")
    ups = st.file_uploader("FDO Dataset — choose file(s) (CSV, XLSX or XLS)",
                           type=["csv", "xlsx", "xls"], accept_multiple_files=True,
                           key="upload_fdo")

    section("2 · Manual EOS tracking sheet")
    st.caption("Optional, and a **different document**: the EOS programme's own "
               "sheet, keyed on **TPID**. It decides each account's generation "
               "(*Target SDDC Generation*), its *Migration Status* and "
               "*Current State* (replacing the export's), and supplies the "
               "*Migration Start Date* and *Actual Migration End Date*; "
               "everything else — Factory PM, Solution Architect, region, ACR "
               "— is looked up against the FDO dataset by TPID. A title row "
               "above the headers is fine, and in a workbook the sheet holding "
               "the TPID column is found. Columns it does not recognise are "
               "left alone.")
    tracker_ups = st.file_uploader(
        "EOS tracking sheet — choose file(s) (CSV, XLSX or XLS)",
        type=["csv", "xlsx", "xls"], accept_multiple_files=True, key="upload_eos")
    _date_order_control(ctx)

    cols = st.columns([1, 1, 3])
    with cols[0]:
        if st.button("Use sample dataset", width="stretch"):
            state.load_sample()
            st.success("Loaded the bundled sample dataset.")
            st.rerun()
    with cols[1]:
        if st.button("Sample + EOS tracker", width="stretch",
                     help="The bundled sample dataset with the bundled EOS "
                          "tracking sheet joined onto it — the quickest way to "
                          "see what the sheet changes."):
            state.load_sample(with_tracker=True)
            st.success("Loaded the bundled sample dataset and EOS tracking sheet.")
            st.rerun()

    files = [(u.name, u.getvalue()) for u in (ups or [])]
    tracker_files = [(u.name, u.getvalue()) for u in (tracker_ups or [])]
    if not _load_uploads(ctx, files, tracker_files):
        return

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

    _tracker_panel(ctx)

    _classification_panel(ctx)

    section("Source column profile")
    st.caption("Fill rate and sample values for every column in the uploaded file. "
               "Empty columns are detected automatically and excluded from analytics.")
    fill = loader.column_fill_report(ctx.raw)
    st.dataframe(fill, width="stretch", height=420, hide_index=True,
                 column_config={"fill_pct": st.column_config.ProgressColumn(
                     "Fill %", min_value=0, max_value=100, format="%.0f%%")})


def _load_uploads(ctx, files: list, tracker_files: list) -> bool:
    """Rebuild the context when what is attached to the uploaders has changed.

    Signatures are compared rather than "is anything attached", because a
    Streamlit uploader keeps handing its files back on every rerun: rebuilding
    on their mere presence reloads the dataset forever, and — now that there are
    two uploaders — would undo the other one's upload on every pass.  Removing a
    file from the sheet's uploader is a change too, and means *build without the
    sheet*.

    Returns False when the page should stop (an upload failed and the diagnosis
    is on screen); the previously active dataset is left untouched.
    """
    if not files and not tracker_files:
        return True
    signature = loader.files_signature(files) if files else ctx.signature
    tracker_signature = (loader.files_signature(tracker_files)
                         if tracker_files else "")
    if (signature, tracker_signature) == (ctx.signature, ctx.tracker_signature):
        return True

    label = loader.dataset_label(files) if files else ctx.filename
    try:
        if files:
            new = state.build_dataset(files, tracker_files=tracker_files)
            state.remember_files(files, tracker_files)
            state.set_context(new)
        else:
            # Only the sheet changed: keep the dataset that is loaded — which may
            # be the bundled sample — and rebuild it with the new sheet.
            new = state.reload_with(tracker_files=tracker_files)
    except loader.IngestError as err:
        _failure_panel(err.failure)
        return False
    except Exception as exc:  # noqa: BLE001 - anything the stages missed
        _failure_panel(loader.IngestFailure(
            filename=label, stage="read", exc_type=type(exc).__name__,
            message=str(exc), hint=loader.explain(str(exc)),
            origin="", detail={}, traceback=_format_exc(exc)))
        return False

    if files:
        cov = mapmod.mapping_coverage(new.mapping)
        if cov["ok"]:
            banner(f"✅ Loaded <b>{label}</b> — {fmt_int(len(new.raw))} rows, "
                   f"{len(new.raw.columns)} columns. {cov['mapped']} fields auto-mapped.")
        else:
            banner(f"⚠️ Loaded <b>{label}</b>, but required fields are unmapped: "
                   f"{', '.join(cov['missing_required'])}. Open <b>Column Mapping</b> "
                   f"to fix.", "warn")
    if new.has_tracker:
        read = new.tracker_report or {}
        overlay = (new.report.get("tracker") or {})
        banner(f"🧾 EOS tracking sheet <b>{new.tracker_filename}</b> — "
               f"{fmt_int(read.get('rows', 0))} rows covering "
               f"{fmt_int(read.get('accounts', 0))} accounts, of which "
               f"{fmt_int(overlay.get('matched_accounts', 0))} matched a TPID in "
               f"the FDO dataset.")
    st.rerun()
    return False


_DATE_ORDERS = {"Detect from the column": None,
                "Day first (DD-MM-YYYY)": True,
                "Month first (MM-DD-YYYY)": False}


def _date_order_control(ctx) -> None:
    """How the sheet's ambiguous dates are read — "03-02-2026" is either.

    Detected per column by default (a day above 12 settles it); when every date
    in a column could be either, the detection has nothing to go on, and this is
    where the reader says which the sheet means.
    """
    current = state.tracker_date_order()
    labels = list(_DATE_ORDERS)
    index = [_DATE_ORDERS[k] for k in labels].index(current)
    choice = st.radio("Dates in the tracking sheet are written", labels,
                      index=index, horizontal=True, key="tracker_date_order",
                      help="03-02-2026 is 3 February day-first and 2 March "
                           "month-first. Left on detect, the order is read off "
                           "the column itself; pick one if the dates below read "
                           "wrong.")
    wanted = _DATE_ORDERS[choice]
    if wanted != current:
        state.set_tracker_date_order(wanted)
        if ctx.has_tracker:
            state.reload_with()
            st.rerun()


def _tracker_panel(ctx) -> None:
    """What the EOS tracking sheet is answering for, and what it could not.

    The sheet is the reason an EOS number can differ from what the export alone
    would say, so the page states plainly which accounts it reached, which
    generations it decided, and which of its TPIDs the FDO dataset has never
    heard of — those can be reported on nowhere until the nomination exists.
    """
    section("Manual EOS tracking sheet")
    if not ctx.has_tracker:
        st.caption("No sheet loaded. Every EOS figure is read from the FDO "
                   "dataset alone: generation from the **AVS Migration - "
                   "Gen1/Gen2** tag, migration start derived from the earliest "
                   "wave under way, migration end from the latest wave "
                   "completing. Upload a sheet above to let the programme's own "
                   "dates and generations lead.")
        return

    read = ctx.tracker_report or {}
    overlay = ctx.report.get("tracker") or {}
    unmatched = overlay.get("unmatched_tpids") or []
    if read.get("accounts") and not overlay.get("matched_accounts"):
        banner("⚠️ <b>None of the sheet's TPIDs matched the FDO dataset</b>, so "
               "nothing in it reaches the EOS reports built on the export. "
               "Compare the TPIDs below with the FDO file's; the EOS Programme "
               "Tracker page still reports the sheet on its own.", "warn")
    components.kpi_row([
        {"label": "Sheet", "value": ctx.tracker_filename},
        {"label": "Accounts in sheet", "value": fmt_int(read.get("accounts", 0))},
        {"label": "Matched in FDO", "value": fmt_int(overlay.get("matched_accounts", 0))},
        {"label": "Not in FDO", "value": fmt_int(len(unmatched)),
         "tone": "warn" if unmatched else "good"},
        {"label": "Generation stated", "value": fmt_int(
            read.get("accounts", 0) - read.get("no_generation", 0))},
    ])
    st.caption(f"**{fmt_int(read.get('with_start', 0))}** accounts carry a "
               f"*Migration Start Date* and **{fmt_int(read.get('with_end', 0))}** "
               f"an *Actual Migration End Date*; the programme matrix uses those "
               f"and falls back to the FDO derivation for the rest.")

    _tracker_read_panel(ctx, read)

    subheading("Which document decided each generation")
    components.show_table(eos_tracker.summary(ctx.fact))

    extra = read.get("extra_columns") or []
    if extra:
        st.caption("Columns the sheet carries that the reports do not read: "
                   + ", ".join(f"**{c}**" for c in extra[:20])
                   + (f" (+{len(extra) - 20} more)" if len(extra) > 20 else "")
                   + ". They are left exactly as they are.")

    issues = eos_tracker.inconsistencies(ctx.fact, ctx.tracker, overlay)
    labels = {
        "unmatched_tpids": "In the sheet, not in the FDO dataset",
        "untracked_eos_accounts": "In EOS scope, not in the sheet",
        "generation_disagrees": "Sheet and tag disagree on the generation",
        "ended_with_sddcs_outstanding": "Ended, with SDDCs still outstanding",
        "status_state_disagree": "Migration Status and Current State disagree",
    }
    for key, label in labels.items():
        frame = issues.get(key)
        rows = 0 if frame is None or frame.empty else len(frame)
        with st.expander(f"{label} — {fmt_int(rows)} account(s)"):
            if rows:
                components.show_table(frame, height=260)
            else:
                st.caption("None.")


def _tracker_read_panel(ctx, read: dict) -> None:
    """How the sheet was read — where the headers were, which column fed each
    field, and every date and status the reader could not make sense of.

    A wrong-looking EOS number usually starts here: a column that was not
    found, or a date column read the wrong way round.
    """
    subheading("How the sheet was read")
    for note in read.get("files") or []:
        where = f"sheet **{note['sheet']}**, " if note.get("sheet") else ""
        st.caption(f"**{note['file']}** — {where}headers on row "
                   f"**{note.get('header_row') or '–'}**"
                   + (" — no TPID column found" if note.get("no_tpid_header") else ""))

    mapping = read.get("mapping") or {}
    checks = read.get("date_checks") or {}
    rows = []
    for f in eos_tracker.TRACKER_FIELDS:
        row = {"Field": f.label, "Column in your sheet": mapping.get(f.key) or "— not found —"}
        if f.key in checks:
            c = checks[f.key]
            row["Read"] = (f"{fmt_int(c['parsed'])} of {fmt_int(c['filled'])} "
                           f"filled cells read as dates")
        elif f.key == "migration_status":
            row["Read"] = (f"{fmt_int(read.get('with_status', 0))} accounts with a "
                           f"recognised status")
        elif f.key == "current_state":
            row["Read"] = (f"{fmt_int(read.get('with_state', 0))} accounts with a "
                           f"recognised state")
        else:
            row["Read"] = ""
        rows.append(row)
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    for key, c in checks.items():
        label = c["label"]
        with st.expander(f"{label} — how the dates were read "
                         f"({fmt_int(len(c['unparsed']))} value(s) not understood)"):
            sample = c.get("sample")
            if sample is not None and not sample.empty:
                st.caption("As written in the sheet, and the date it was read as:")
                st.dataframe(sample.rename(columns={"raw": "In the sheet",
                                                    "parsed": "Read as"}),
                             width="stretch", hide_index=True)
            if c["unparsed"]:
                st.caption("Not understood, so treated as blank: "
                           + ", ".join(f"`{v}`" for v in c["unparsed"]))

    unknown_status = read.get("unrecognised_status") or []
    unknown_state = read.get("unrecognised_state") or []
    if unknown_status or unknown_state:
        banner("⚠️ Values the sheet uses that are not in its vocabulary, so the "
               "export's answer stands for those accounts — "
               + (f"Migration Status: {', '.join(unknown_status[:12])}. "
                  if unknown_status else "")
               + (f"Current State: {', '.join(unknown_state[:12])}."
                  if unknown_state else ""), "warn")
    st.caption("Migration Status values read: "
               + ", ".join(f"*{st_.text}*" for st_ in eos_tracker.TRACKER_STATUSES)
               + ". Current State values read: "
               + ", ".join(f"*{v}*" for v in eos_tracker.TRACKER_STATES) + ".")


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
        st.markdown("**Generation split** (per TPID — the sheet's *Target SDDC "
                    "Generation* where it has one, else the Tags column)")
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
    # Remembered for the Debug page: a failed sheet upload otherwise leaves no
    # trace once the reader has moved on, and the reports simply lack the sheet.
    st.session_state[state.LAST_FAILURE_KEY] = {
        "when": pd.Timestamp.now().strftime("%d %b %Y %H:%M"),
        "file": failure.filename, "stage": failure.stage_label,
        "message": f"{failure.exc_type}: {failure.message}"[:300],
        "hint": failure.hint, "origin": failure.origin}
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
