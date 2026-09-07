"""Session/data-context management for the Streamlit app.

Holds the loaded dataset (raw frame, mapping, cleaned fact frame, DuckDB
connection, as-of date) in ``st.session_state`` and rebuilds it only when inputs
change.  Heavy steps are cached so page switches are instant.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

import duckdb
import pandas as pd
import streamlit as st

from .config import FY_START_MONTH, REPORTING_FLOOR_FY, SAMPLE_DATA
from .core import cleaning, loader, mapping as mapmod, rollup as rollupmod, segments

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

    @property
    def is_multi_file(self) -> bool:
        return self.sources is not None and len(self.sources) > 1


# --------------------------------------------------------------------------- #
# Cached heavy steps
# --------------------------------------------------------------------------- #
@st.cache_data(show_spinner=False, max_entries=4)
def _read_dataset(signature: str, files: tuple[tuple[str, bytes], ...]
                  ) -> tuple[pd.DataFrame, pd.DataFrame]:
    return loader.read_files(list(files))


@st.cache_data(show_spinner=False, max_entries=6)
def _build_fact(signature: str, mapping_json: str, as_of_str: str, filename: str,
                _raw: pd.DataFrame) -> tuple[pd.DataFrame, dict, pd.DataFrame]:
    mp = json.loads(mapping_json)
    as_of = pd.Timestamp(as_of_str) if as_of_str else None
    with loader.ingest_stage("clean", filename, _raw, mp):
        fact, report = cleaning.build_fact_frame(_raw, mp, as_of)
    # The reporting floor is applied here, before the rollup and before the
    # frames are registered with DuckDB, so every downstream page, query,
    # export and total sees an FY25-onwards dataset rather than filtering for
    # itself (and forgetting to, somewhere).
    with loader.ingest_stage("floor", filename, _raw, mp):
        fact, report["scope"] = cleaning.apply_reporting_floor(
            fact, REPORTING_FLOOR_FY, FY_START_MONTH)
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
                  as_of: pd.Timestamp | None = None, is_sample: bool = False) -> DataContext:
    """Build a context from a single file (the common case)."""
    return build_dataset([(filename, data)], mapping=mapping, as_of=as_of,
                         is_sample=is_sample)


def build_dataset(files: list[tuple[str, bytes]], mapping: dict | None = None,
                  as_of: pd.Timestamp | None = None,
                  is_sample: bool = False) -> DataContext:
    """Build a context from one or more files read as a single dataset.

    Several files are concatenated on their shared headers before anything else
    happens, so the mapping, cleaning, rollup and every report see one dataset —
    which is the point: an AVS export and an Azure-native export describe the
    same portfolio and have to be counted together.
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

    as_of_str = pd.Timestamp(as_of).isoformat() if as_of is not None else ""
    mapping_json = json.dumps(mapping, sort_keys=True)
    fact, report, customer = _build_fact(signature, mapping_json, as_of_str,
                                         label, raw)
    report["sources"] = sources
    cache_key = f"{signature}:{hash(mapping_json)}:{as_of_str}"
    with loader.ingest_stage("register", label, raw, mapping):
        con = _make_con(cache_key, fact, customer)

    return DataContext(filename=label, signature=signature, raw=raw, mapping=mapping,
                       fact=fact, customer=customer, report=report, as_of=report["as_of"],
                       con=con, is_sample=is_sample, sources=sources)


def set_context(ctx: DataContext) -> None:
    st.session_state[CTX_KEY] = ctx


def get_context() -> DataContext | None:
    return st.session_state.get(CTX_KEY)


RAW_FILES_KEY = "avs_raw_files"


def remember_files(files: list[tuple[str, bytes]]) -> None:
    """Stash the uploaded bytes so a re-map can rebuild without a re-upload."""
    st.session_state[RAW_FILES_KEY] = list(files)


def load_sample() -> DataContext:
    data = SAMPLE_DATA.read_bytes()
    ctx = build_context(SAMPLE_DATA.name, data, is_sample=True)
    set_context(ctx)
    return ctx


def ensure_context() -> DataContext:
    """Return the active context, loading the bundled sample on first run."""
    ctx = get_context()
    if ctx is None:
        ctx = load_sample()
    return ctx


def reload_with(mapping: dict | None = None, as_of: pd.Timestamp | None = None) -> DataContext:
    """Rebuild the current context with a new mapping and/or as-of date."""
    ctx = get_context()
    if ctx is None:
        return ensure_context()
    if ctx.is_sample:
        data = SAMPLE_DATA.read_bytes()
        new = build_context(ctx.filename, data, mapping=mapping or ctx.mapping,
                            as_of=as_of if as_of is not None else ctx.as_of, is_sample=True)
    else:
        # every uploaded file's bytes are stashed on the session, so a re-map
        # rebuilds the whole dataset without asking for the files again
        files = st.session_state.get(RAW_FILES_KEY) or []
        new = build_dataset(files, mapping=mapping or ctx.mapping,
                            as_of=as_of if as_of is not None else ctx.as_of)
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
