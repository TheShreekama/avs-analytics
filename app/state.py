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

from .config import SAMPLE_DATA
from .core import cleaning, loader, mapping as mapmod

CTX_KEY = "avs_ctx"


@dataclass
class DataContext:
    filename: str
    signature: str
    raw: pd.DataFrame
    mapping: dict
    fact: pd.DataFrame
    report: dict
    as_of: pd.Timestamp
    con: duckdb.DuckDBPyConnection
    is_sample: bool = False


# --------------------------------------------------------------------------- #
# Cached heavy steps
# --------------------------------------------------------------------------- #
@st.cache_data(show_spinner=False, max_entries=4)
def _read_raw(signature: str, name: str, data: bytes) -> pd.DataFrame:
    return loader.read_raw(name, data)


@st.cache_data(show_spinner=False, max_entries=6)
def _build_fact(signature: str, mapping_json: str, as_of_str: str,
                _raw: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    mp = json.loads(mapping_json)
    as_of = pd.Timestamp(as_of_str) if as_of_str else None
    return cleaning.build_fact_frame(_raw, mp, as_of)


@st.cache_resource(show_spinner=False, max_entries=4)
def _make_con(cache_key: str, _fact: pd.DataFrame) -> duckdb.DuckDBPyConnection:
    return loader.make_connection(_fact)


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def build_context(filename: str, data: bytes, mapping: dict | None = None,
                  as_of: pd.Timestamp | None = None, is_sample: bool = False) -> DataContext:
    signature = loader.file_signature(filename, data)
    raw = _read_raw(signature, filename, data)
    if mapping is None:
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
    fact, report = _build_fact(signature, mapping_json, as_of_str, raw)
    cache_key = f"{signature}:{hash(mapping_json)}:{as_of_str}"
    con = _make_con(cache_key, fact)

    return DataContext(filename=filename, signature=signature, raw=raw, mapping=mapping,
                       fact=fact, report=report, as_of=report["as_of"], con=con,
                       is_sample=is_sample)


def set_context(ctx: DataContext) -> None:
    st.session_state[CTX_KEY] = ctx


def get_context() -> DataContext | None:
    return st.session_state.get(CTX_KEY)


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
        # raw bytes for a user upload are stashed on the context's session entry
        data = st.session_state.get("avs_raw_bytes")
        new = build_context(ctx.filename, data, mapping=mapping or ctx.mapping,
                            as_of=as_of if as_of is not None else ctx.as_of)
    set_context(new)
    return new
