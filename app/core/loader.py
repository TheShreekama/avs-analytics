"""File ingestion and DuckDB-backed access.

Reads CSV / XLS / XLSX uploads into a raw string frame (so we control every
parse ourselves in ``cleaning``), then registers the cleaned fact frame in an
in-process DuckDB connection for fast SQL aggregation over large datasets.
"""
from __future__ import annotations

import hashlib
import io
from typing import BinaryIO

import duckdb
import pandas as pd


SUPPORTED_EXT = (".csv", ".xlsx", ".xls")


def file_signature(name: str, data: bytes) -> str:
    """Stable hash of (filename, contents) for cache keys."""
    h = hashlib.sha256()
    h.update(name.encode("utf-8", "ignore"))
    h.update(data)
    return h.hexdigest()[:16]


def read_raw(name: str, data: bytes) -> pd.DataFrame:
    """Read an uploaded file into a raw, all-string DataFrame.

    Everything is read as text; numeric/date parsing happens later in
    ``cleaning`` so we can detect and report contaminated values.
    """
    lower = name.lower()
    buf: BinaryIO = io.BytesIO(data)
    if lower.endswith(".csv"):
        # Robust CSV read: keep blanks as empty strings, all columns as str.
        return pd.read_csv(buf, dtype=str, keep_default_na=False, na_values=[],
                           skipinitialspace=False, engine="python", on_bad_lines="warn")
    if lower.endswith(".xlsx"):
        return pd.read_excel(buf, dtype=str, engine="openpyxl").fillna("")
    if lower.endswith(".xls"):
        return pd.read_excel(buf, dtype=str, engine="xlrd").fillna("")
    raise ValueError(f"Unsupported file type: {name}. Use CSV, XLSX or XLS.")


def read_raw_path(path) -> pd.DataFrame:
    with open(path, "rb") as fh:
        data = fh.read()
    return read_raw(str(path), data)


def make_connection(fact: pd.DataFrame,
                    customer: pd.DataFrame | None = None) -> duckdb.DuckDBPyConnection:
    """Create an in-memory DuckDB connection with the report tables registered.

    ``fact`` (one row per wave/nomination) is always created.  If a ``customer``
    rollup is supplied it is materialised as the ``customer`` table so reports
    can switch counting grain via the global toggle.
    """
    con = duckdb.connect(database=":memory:")
    con.register("fact_view", fact)
    con.execute("CREATE TABLE fact AS SELECT * FROM fact_view")
    con.unregister("fact_view")
    if customer is not None and not customer.empty:
        con.register("customer_view", customer)
        con.execute("CREATE TABLE customer AS SELECT * FROM customer_view")
        con.unregister("customer_view")
    return con


def column_fill_report(raw: pd.DataFrame) -> pd.DataFrame:
    """Per-column fill statistics for the raw frame (used by the mapping UI)."""
    rows = []
    n = len(raw)
    for c in raw.columns:
        s = raw[c].astype("string").str.strip().replace({"": pd.NA})
        nonblank = int(s.notna().sum())
        rows.append({
            "column": c,
            "non_blank": nonblank,
            "fill_pct": round(100 * nonblank / n, 1) if n else 0.0,
            "distinct": int(s.nunique()),
            "sample": " | ".join(map(str, s.dropna().unique()[:3])),
        })
    return pd.DataFrame(rows)
