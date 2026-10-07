"""Session/data-context management for the Streamlit app.

Holds the loaded dataset (raw frame, mapping, cleaned fact frame, DuckDB
connection, as-of date) in ``st.session_state`` and rebuilds it only when inputs
change.  Heavy steps are cached so page switches are instant.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

import duckdb
import pandas as pd
import streamlit as st

from .config import (FY_START_MONTH, REPORTING_FLOOR_FY, SAMPLE_DATA,
                     SAMPLE_EOS_TRACKER)
from .core import (cleaning, eos_customers as eoslist, eos_tracker as trackermod, loader,
                   mapping as mapmod, rollup as rollupmod, segments)

CTX_KEY = "avs_ctx"
MODE_KEY = "count_mode"
MODE_CUSTOMER = "Customer (deduplicated)"
MODE_WAVE = "Nomination (wave-level)"


@dataclass
class DataContext:
    filename: str
    signature: str
    raw: pd.DataFrame
    mapping: dict
    fact: pd.DataFrame
    customer: pd.DataFrame
    report: dict
    as_of: pd.Timestamp
    con: duckdb.DuckDBPyConnection
    is_sample: bool = False
    #: One row per uploaded file (file, rows, columns, new/shared columns).
    sources: pd.DataFrame | None = None
    #: The manual EOS tracking sheet: one row per TPID, plus what it was read
    #: from.  ``None`` when no sheet was uploaded — every EOS rule then falls
    #: back to the FDO export exactly as it did before the sheet existed.
    tracker: pd.DataFrame | None = None
    tracker_raw: pd.DataFrame | None = None
    tracker_filename: str = ""
    tracker_signature: str = ""
    tracker_report: dict = field(default_factory=dict)
    #: The All EOS customers list: one row per TPID running EOS SKUs.  When it
    #: is loaded, AVS → Azure Native reports only the customers on it.
    eos_list: pd.DataFrame | None = None
    eos_list_filename: str = ""
    eos_list_signature: str = ""
    eos_list_report: dict = field(default_factory=dict)

    @property
    def is_multi_file(self) -> bool:
        return self.sources is not None and len(self.sources) > 1

    @property
    def has_tracker(self) -> bool:
        return self.tracker is not None and not self.tracker.empty

    @property
    def has_eos_list(self) -> bool:
        return self.eos_list is not None


# --------------------------------------------------------------------------- #
# Cached heavy steps
# --------------------------------------------------------------------------- #
@st.cache_data(show_spinner=False, max_entries=4)
def _read_dataset(signature: str, files: tuple[tuple[str, bytes], ...]
                  ) -> tuple[pd.DataFrame, pd.DataFrame]:
    return loader.read_files(list(files))


@st.cache_data(show_spinner=False, max_entries=4)
def _read_tracker(signature: str, files: tuple[tuple[str, bytes], ...],
                  dayfirst: bool | None = None
                  ) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """The EOS tracking sheet: its raw rows, one row per TPID, and the read report.

    The sheet is read by :func:`app.core.eos_tracker.read_tracker_files`, which
    finds the header row (a title above it is common in a hand-kept sheet) and,
    in a workbook, the sheet that holds the TPID column.
    """
    raw, notes = trackermod.read_tracker_files(list(files))
    label = loader.dataset_label(list(files))
    with loader.ingest_stage("tracker", label, raw):
        tracker, report = trackermod.build_tracker(raw, dayfirst=dayfirst)
    report["files"] = notes
    return raw, tracker, report


@st.cache_data(show_spinner=False, max_entries=4)
def _read_eos_list(signature: str, files: tuple[tuple[str, bytes], ...]
                   ) -> tuple[pd.DataFrame, dict]:
    """The All EOS customers list: one row per TPID, and the read report."""
    raw, notes = eoslist.read_files(list(files))
    label = loader.dataset_label(list(files))
    with loader.ingest_stage("eos list", label, raw):
        frame, report = eoslist.build_list(raw)
    report["files"] = notes
    return frame, report


@st.cache_data(show_spinner=False, max_entries=6)
def _build_fact(signature: str, mapping_json: str, as_of_str: str, filename: str,
                _raw: pd.DataFrame, tracker_signature: str = "",
                _tracker: pd.DataFrame | None = None,
                eos_list_signature: str = "",
                _eos_list: pd.DataFrame | None = None
                ) -> tuple[pd.DataFrame, dict, pd.DataFrame]:
    mp = json.loads(mapping_json)
    as_of = pd.Timestamp(as_of_str) if as_of_str else None
    with loader.ingest_stage("clean", filename, _raw, mp):
        fact, report = cleaning.build_fact_frame(_raw, mp, as_of, tracker=_tracker)
    # The reporting floor is applied here, before the rollup and before the
    # frames are registered with DuckDB, so every downstream page, query,
    # export and total sees an FY25-onwards dataset rather than filtering for
    # itself (and forgetting to, somewhere).
    with loader.ingest_stage("floor", filename, _raw, mp):
        fact, report["scope"] = cleaning.apply_reporting_floor(
            fact, REPORTING_FLOOR_FY, FY_START_MONTH)
    # AVS → Azure Native covers only the customers on the All EOS customers
    # list, when one is loaded: the others' From AVS waves leave here.
    with loader.ingest_stage("eos list", filename, _raw, mp):
        fact, report["eos_list"] = eoslist.apply_to_fact(fact, _eos_list)
    with loader.ingest_stage("rollup", filename, _raw, mp):
        customer = rollupmod.build_customer_rollup(fact, report["as_of"])
        report["rollup"] = rollupmod.rollup_summary(customer)
    return fact, report, customer


@st.cache_resource(show_spinner=False, max_entries=4)
def _make_con(cache_key: str, _fact: pd.DataFrame,
              _customer: pd.DataFrame) -> duckdb.DuckDBPyConnection:
    return loader.make_connection(_fact, _customer)


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def build_context(filename: str, data: bytes, mapping: dict | None = None,
                  as_of: pd.Timestamp | None = None, is_sample: bool = False,
                  tracker_files: list[tuple[str, bytes]] | None = None) -> DataContext:
    """Build a context from a single file (the common case)."""
    return build_dataset([(filename, data)], mapping=mapping, as_of=as_of,
                         is_sample=is_sample, tracker_files=tracker_files)


#: ``tracker_dayfirst`` left to the session's choice on Data & Upload.
_FROM_SESSION = object()
TRACKER_DATE_ORDER_KEY = "avs_tracker_dayfirst"


def tracker_date_order() -> bool | None:
    """How the session reads the sheet's ambiguous dates: day first (True),
    month first (False) or inferred per column (None, the default)."""
    try:
        return st.session_state.get(TRACKER_DATE_ORDER_KEY)
    except Exception:  # noqa: BLE001 - no Streamlit session (tests, scripts)
        return None


def set_tracker_date_order(dayfirst: bool | None) -> None:
    st.session_state[TRACKER_DATE_ORDER_KEY] = dayfirst


def build_dataset(files: list[tuple[str, bytes]], mapping: dict | None = None,
                  as_of: pd.Timestamp | None = None,
                  is_sample: bool = False,
                  tracker_files: list[tuple[str, bytes]] | None = None,
                  tracker_dayfirst: "bool | None | object" = _FROM_SESSION,
                  eos_list_files: list[tuple[str, bytes]] | None = None
                  ) -> DataContext:
    """Build a context from one or more files read as a single dataset.

    Several files are concatenated on their shared headers before anything else
    happens, so the mapping, cleaning, rollup and every report see one dataset —
    which is the point: an AVS export and an Azure-native export describe the
    same portfolio and have to be counted together.

    ``tracker_files`` are the **manual EOS tracking sheet**, which is a
    different document rather than another part of the dataset: it is keyed on
    TPID, carries the programme's own generation and dates, and is joined onto
    the FDO rows (see :mod:`app.core.eos_tracker`) rather than stacked with
    them.  Stacking it would put rows with no offering, no wave and no ACR into
    every count.  ``tracker_dayfirst`` fixes how the sheet's ambiguous dates
    ("03-02-2026") are read; None infers it from each column.
    """
    files = [(name, data) for name, data in files]
    if not files:
        raise ValueError("No files to load.")
    signature = loader.files_signature(files)
    label = loader.dataset_label(files)
    # Each step names itself, so a failure anywhere below reaches the upload
    # page as an IngestError carrying the stage, the origin and a diagnosis
    # rather than a bare exception message.
    raw, sources = _read_dataset(signature, tuple(files))
    if mapping is None:
        with loader.ingest_stage("mapping", label, raw):
            saved = mapmod.load_saved_mappings()
            # prefer a saved mapping whose columns fit; else auto-map
            chosen = None
            for _name, mp in saved.items():
                if all(v in raw.columns for v in mp.values()):
                    chosen = mp
                    break
            mapping = mapmod.resolve_mapping(list(raw.columns), chosen)

    tracker_files = [(name, data) for name, data in (tracker_files or [])]
    tracker = tracker_raw = None
    tracker_signature = tracker_label = tracker_key = ""
    tracker_report: dict = {}
    if tracker_files:
        tracker_signature = loader.files_signature(tracker_files)
        if tracker_dayfirst is _FROM_SESSION:
            tracker_dayfirst = tracker_date_order()
        # A different reading of the dates is a different tracker, so the
        # cached fact frame and connection are keyed on it too.
        tracker_key = tracker_signature + {None: "", True: ":df",
                                           False: ":mf"}[tracker_dayfirst]
        tracker_label = loader.dataset_label(tracker_files)
        tracker_raw, tracker, tracker_report = _read_tracker(
            tracker_signature, tuple(tracker_files), tracker_dayfirst)

    eos_list_files = [(name, data) for name, data in (eos_list_files or [])]
    eos_list = None
    eos_list_signature = eos_list_label = ""
    eos_list_report: dict = {}
    if eos_list_files:
        eos_list_signature = loader.files_signature(eos_list_files)
        eos_list_label = loader.dataset_label(eos_list_files)
        eos_list, eos_list_report = _read_eos_list(eos_list_signature,
                                                   tuple(eos_list_files))

    as_of_str = pd.Timestamp(as_of).isoformat() if as_of is not None else ""
    mapping_json = json.dumps(mapping, sort_keys=True)
    fact, report, customer = _build_fact(signature, mapping_json, as_of_str,
                                         label, raw, tracker_key, tracker,
                                         eos_list_signature, eos_list)
    report["sources"] = sources
    report["tracker_read"] = tracker_report
    cache_key = (f"{signature}:{hash(mapping_json)}:{as_of_str}:{tracker_key}:"
                 f"{eos_list_signature}")
    with loader.ingest_stage("register", label, raw, mapping):
        con = _make_con(cache_key, fact, customer)

    return DataContext(filename=label, signature=signature, raw=raw, mapping=mapping,
                       fact=fact, customer=customer, report=report, as_of=report["as_of"],
                       con=con, is_sample=is_sample, sources=sources,
                       tracker=tracker, tracker_raw=tracker_raw,
                       tracker_filename=tracker_label,
                       tracker_signature=tracker_signature,
                       tracker_report=tracker_report,
                       eos_list=eos_list, eos_list_filename=eos_list_label,
                       eos_list_signature=eos_list_signature,
                       eos_list_report=eos_list_report)


def set_context(ctx: DataContext) -> None:
    previous = st.session_state.get(CTX_KEY)
    if previous is not None and previous.signature != ctx.signature:
        # A custom date range is a pair of dates picked inside the *previous*
        # dataset's span; carried onto a new file it can quietly exclude every
        # row, so a different dataset starts from the presets again.
        for key in [k for k in st.session_state.keys()
                    if str(k) == "global_date_custom" or str(k).endswith("_custom")]:
            del st.session_state[key]
    st.session_state[CTX_KEY] = ctx


def get_context() -> DataContext | None:
    return st.session_state.get(CTX_KEY)


RAW_FILES_KEY = "avs_raw_files"
#: The last upload that failed, kept for the Debug page.
LAST_FAILURE_KEY = "avs_last_failure"
TRACKER_FILES_KEY = "avs_tracker_files"
EOS_LIST_FILES_KEY = "avs_eos_list_files"

#: Passed where ``None`` already means "no tracking sheet", so a caller can say
#: "leave the sheet alone" and "drop the sheet" as two different things.
KEEP = object()


def remember_files(files: list[tuple[str, bytes]],
                   tracker_files: list[tuple[str, bytes]] | None = KEEP,
                   eos_list_files: list[tuple[str, bytes]] | None = KEEP) -> None:
    """Stash the uploaded bytes so a re-map can rebuild without a re-upload."""
    st.session_state[RAW_FILES_KEY] = list(files)
    if tracker_files is not KEEP:
        st.session_state[TRACKER_FILES_KEY] = list(tracker_files or [])
    if eos_list_files is not KEEP:
        st.session_state[EOS_LIST_FILES_KEY] = list(eos_list_files or [])


def remembered_files() -> list[tuple[str, bytes]]:
    return list(st.session_state.get(RAW_FILES_KEY) or [])


def remembered_tracker_files() -> list[tuple[str, bytes]]:
    return list(st.session_state.get(TRACKER_FILES_KEY) or [])


def remembered_eos_list_files() -> list[tuple[str, bytes]]:
    return list(st.session_state.get(EOS_LIST_FILES_KEY) or [])


def sample_tracker_files() -> list[tuple[str, bytes]]:
    """The bundled EOS tracking sheet, as an upload would arrive."""
    return [(SAMPLE_EOS_TRACKER.name, SAMPLE_EOS_TRACKER.read_bytes())]


def load_sample(with_tracker: bool = False) -> DataContext:
    data = SAMPLE_DATA.read_bytes()
    tracker_files = sample_tracker_files() if with_tracker else None
    ctx = build_context(SAMPLE_DATA.name, data, is_sample=True,
                        tracker_files=tracker_files)
    remember_files([(SAMPLE_DATA.name, data)], tracker_files or [], [])
    set_context(ctx)
    return ctx


def ensure_context() -> DataContext:
    """Return the active context, loading the bundled sample on first run."""
    ctx = get_context()
    if ctx is None:
        ctx = load_sample()
    return ctx


def reload_with(mapping: dict | None = None, as_of: pd.Timestamp | None = None,
                tracker_files: list[tuple[str, bytes]] | None = KEEP,
                eos_list_files: list[tuple[str, bytes]] | None = KEEP) -> DataContext:
    """Rebuild the current context with a new mapping, as-of date and/or tracker.

    ``tracker_files`` left alone keeps whichever sheet is loaded; pass a list to
    replace it, or ``[]``/``None`` to build without one — which is what removing
    the file from the uploader has to mean.
    """
    ctx = get_context()
    if ctx is None:
        return ensure_context()
    keep_tracker = tracker_files is KEEP
    tracker_files = (remembered_tracker_files() if keep_tracker
                     else list(tracker_files or []))
    keep_list = eos_list_files is KEEP
    eos_list_files = (remembered_eos_list_files() if keep_list
                      else list(eos_list_files or []))
    if ctx.is_sample:
        files = [(ctx.filename, SAMPLE_DATA.read_bytes())]
    else:
        # every uploaded file's bytes are stashed on the session, so a re-map
        # rebuilds the whole dataset without asking for the files again
        files = remembered_files()
    new = build_dataset(files, mapping=mapping or ctx.mapping,
                        as_of=as_of if as_of is not None else ctx.as_of,
                        is_sample=ctx.is_sample, tracker_files=tracker_files,
                        eos_list_files=eos_list_files)
    if not keep_tracker:
        st.session_state[TRACKER_FILES_KEY] = list(tracker_files)
    if not keep_list:
        st.session_state[EOS_LIST_FILES_KEY] = list(eos_list_files)
    set_context(new)
    return new


# --------------------------------------------------------------------------- #
# Counting mode (customer-deduplicated vs wave-level)
# --------------------------------------------------------------------------- #
def count_mode() -> str:
    return st.session_state.get(MODE_KEY, MODE_CUSTOMER)


def is_customer_mode() -> bool:
    return count_mode() == MODE_CUSTOMER


def active_table() -> str:
    """DuckDB table for the current counting mode."""
    return "customer" if is_customer_mode() else "fact"


def active_frame(ctx: "DataContext") -> pd.DataFrame:
    return ctx.customer if is_customer_mode() else ctx.fact


def unit_label(plural: bool = True) -> str:
    """Human label for the counted unit under the current mode."""
    if is_customer_mode():
        return "accounts" if plural else "account"
    return "nominations" if plural else "nomination"
