"""File ingestion and DuckDB-backed access.

Reads CSV / XLS / XLSX uploads into a raw string frame (so we control every
parse ourselves in ``cleaning``), then registers the cleaned fact frame in an
in-process DuckDB connection for fast SQL aggregation over large datasets.
"""
from __future__ import annotations

import hashlib
import io
import os
import re
import traceback
from contextlib import contextmanager
from dataclasses import dataclass
from typing import BinaryIO

import duckdb
import pandas as pd

from . import schema


SUPPORTED_EXT = (".csv", ".xlsx", ".xls")


def file_signature(name: str, data: bytes) -> str:
    """Stable hash of (filename, contents) for cache keys."""
    h = hashlib.sha256()
    h.update(name.encode("utf-8", "ignore"))
    h.update(data)
    return h.hexdigest()[:16]


def files_signature(files: list[tuple[str, bytes]]) -> str:
    """Stable hash of a whole multi-file dataset, for cache keys."""
    h = hashlib.sha256()
    for name, data in files:
        h.update(file_signature(name, data).encode("ascii"))
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


# --------------------------------------------------------------------------- #
# Ingest diagnostics
# --------------------------------------------------------------------------- #
# An upload that fails used to surface as one line — "Could not read the file:
# boolean value of NA is ambiguous" — which names neither the stage that broke,
# nor the file, nor the column.  Every ingest step is now wrapped in a named
# stage so a failure can say where it happened, what the likely cause is and
# which line of this codebase raised it.

#: Ingest stages, in the order ``state.build_context`` runs them.
STAGES: dict[str, str] = {
    "read": "Reading the file",
    "mapping": "Matching source columns to analytics fields",
    "clean": "Parsing and deriving columns",
    "floor": "Applying the reporting-year floor",
    "rollup": "Rolling waves up to one row per account",
    "combine": "Combining the uploaded files into one dataset",
    "register": "Loading the tables into DuckDB",
}

#: (substring of the error message, explanation) — first match wins.
_KNOWN_CAUSES: tuple[tuple[str, str], ...] = (
    ("boolean value of NA is ambiguous",
     "A column this step reads is empty or unmapped, so its values are missing "
     "(pd.NA) and some check treated a missing value as true/false. Check the "
     "unmapped fields listed below — on Column Mapping, map them or leave them "
     "blank deliberately — and report this message: it is a bug in the parsing "
     "code, not in your file."),
    ("No columns to parse from file",
     "The file has no header row — it is empty, or every line was skipped. Open "
     "it and confirm row 1 holds the column names."),
    ("Excel file format cannot be determined",
     "The extension does not match the contents: a .xls file that is really "
     ".xlsx (or a CSV renamed to .xlsx). Re-save it from Excel as 'Excel "
     "Workbook (.xlsx)' or 'CSV UTF-8'."),
    ("Unsupported format, or corrupt file",
     "The workbook could not be opened — it may be password-protected, a "
     ".xlsb/.xlsm variant, or truncated by the download. Re-save it as .xlsx."),
    ("codec can't decode",
     "The file is not UTF-8 text. Re-save the CSV as 'CSV UTF-8 "
     "(Comma delimited)' from Excel."),
    ("Duplicate column names",
     "Two source columns share a header. Rename one of them in the file."),
    ("out of memory",
     "The file is larger than the memory available. Split it and upload the "
     "parts as separate files."),
)


@dataclass(frozen=True)
class IngestFailure:
    """Everything known about one failed ingest, ready to be shown or logged."""
    filename: str
    stage: str
    exc_type: str
    message: str
    hint: str
    origin: str
    detail: dict[str, str]
    traceback: str

    @property
    def stage_label(self) -> str:
        return STAGES.get(self.stage, self.stage)

    def headline(self) -> str:
        return (f"{self.filename} failed while {self.stage_label.lower()} — "
                f"{self.exc_type}: {self.message}")

    def as_text(self) -> str:
        """The whole diagnosis as plain text, for copy-paste into a bug report."""
        fields = {"File": self.filename,
                  "Stage": f"{self.stage} ({self.stage_label})",
                  "Error": f"{self.exc_type}: {self.message}"}
        if self.origin:
            fields["Raised at"] = self.origin
        fields.update(self.detail)
        width = max(len(k) for k in fields) + 2
        lines = [f"{k + ':':<{width}}{v}" for k, v in fields.items()]
        if self.hint:
            lines += ["", "Likely cause:", self.hint]
        return "\n".join(lines) + "\n\n" + self.traceback


class IngestError(RuntimeError):
    """Raised in place of any exception thrown inside an ingest stage."""

    def __init__(self, failure: IngestFailure):
        super().__init__(failure.headline())
        self.failure = failure


def _short_path(path: str) -> str:
    """Repo-relative path, so the origin reads as ``app/core/cleaning.py``."""
    marker = f"{os.sep}app{os.sep}"
    if marker in path:
        return "app/" + path.split(marker, 1)[1].replace(os.sep, "/")
    return os.path.basename(path)


def _origin(exc: BaseException) -> str:
    """The innermost frame belonging to this app — where to start debugging.

    ``ingest_stage`` itself is skipped: its ``yield`` is on every traceback and
    names nothing.  Falls back to the true raise site when the exception came
    from inside a library with no app frame below it.
    """
    frames = traceback.extract_tb(exc.__traceback__)
    ours = [f for f in frames
            if f"{os.sep}app{os.sep}" in (f.filename or "") and f.name != "ingest_stage"]
    frame = (ours or frames or [None])[-1]
    if frame is None:
        return ""
    line = (frame.line or "").strip()
    return (f"{_short_path(frame.filename)}:{frame.lineno} in {frame.name}()"
            + (f"  →  {line}" if line else ""))


def explain(message: str) -> str:
    """A plain-English cause for a raw exception message, or ''."""
    low = message.lower()
    for needle, hint in _KNOWN_CAUSES:
        if needle.lower() in low:
            return hint
    return ""


def _listing(values: list[str], limit: int = 15) -> str:
    """A comma list, truncated — the unmapped set can run to forty names."""
    shown = ", ".join(map(str, values[:limit]))
    extra = len(values) - limit
    return f"{shown} (+{extra} more)" if extra > 0 else shown


def frame_detail(raw: pd.DataFrame | None,
                 mapping: dict[str, str | None] | None) -> dict[str, str]:
    """Facts about the data being ingested, worth knowing when it breaks."""
    detail: dict[str, str] = {}
    if raw is not None:
        detail["Rows"] = f"{len(raw):,}"
        detail["Columns"] = f"{len(raw.columns)}"
        empty = [str(c) for c in raw.columns
                 if not raw[c].astype("string").str.strip().replace({"": pd.NA}).notna().any()]
        if empty:
            detail["Empty columns"] = _listing(empty)
        if schema.SOURCE_FILE_COLUMN in raw.columns:
            files = [str(v) for v in raw[schema.SOURCE_FILE_COLUMN].dropna().unique()]
            detail["Files"] = _listing(files)
    if mapping is not None:
        unmapped = sorted(k for k, v in mapping.items() if not v)
        if unmapped:
            detail["Unmapped fields"] = _listing(unmapped)
    return detail


@contextmanager
def ingest_stage(stage: str, filename: str, raw: pd.DataFrame | None = None,
                 mapping: dict[str, str | None] | None = None):
    """Run one ingest step, converting any failure into an ``IngestError``.

    Nested stages keep the innermost diagnosis: the first stage to fail is the
    one that knows what it was doing.
    """
    try:
        yield
    except IngestError:
        raise
    except BaseException as exc:      # noqa: BLE001 - re-raised, richer
        raise IngestError(IngestFailure(
            filename=filename, stage=stage, exc_type=type(exc).__name__,
            message=str(exc) or "(no message)", hint=explain(str(exc)),
            origin=_origin(exc), detail=frame_detail(raw, mapping),
            traceback="".join(traceback.format_exception(exc)),
        )) from exc


# --------------------------------------------------------------------------- #
# Multi-file datasets
# --------------------------------------------------------------------------- #
# A dataset often arrives split across exports — one file of AVS nominations,
# another of "(From AVS)" Azure-native ones — because the source system exports
# per offering.  They are the same schema with different rows, so the files are
# concatenated into one raw frame rather than analysed separately: every
# category, rollup and count downstream then works exactly as it does for a
# single file.

def _normalise_header(col) -> str:
    """Header key for matching across files ("Total ACR " == "total  acr")."""
    return re.sub(r"\s+", " ", str(col)).strip().casefold()


def combine_raw(parts: list[tuple[str, pd.DataFrame]]
                ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Stack several raw frames into one, and describe what came from where.

    Headers are matched case- and whitespace-insensitively, keeping the spelling
    from the file that introduced each column; a column missing from a file is
    blank for that file's rows, which is exactly how ``cleaning`` already reads
    an empty cell.  Returns ``(raw, manifest)``.
    """
    if not parts:
        raise ValueError("No files to combine.")
    if len(parts) == 1:
        name, frame = parts[0]
        frame = frame.copy()
        frame[schema.SOURCE_FILE_COLUMN] = name
        return frame, pd.DataFrame([{
            "file": name, "rows": len(frame),
            "columns": len(frame.columns) - 1, "new_columns": len(frame.columns) - 1,
            "shared_columns": 0}])

    canonical: dict[str, str] = {}       # normalised header -> spelling to keep
    frames, manifest = [], []
    for name, frame in parts:
        renames, new = {}, 0
        for col in frame.columns:
            key = _normalise_header(col)
            if key not in canonical:
                canonical[key] = str(col)
                new += 1
            renames[col] = canonical[key]
        aligned = frame.rename(columns=renames)
        # Two headers in one file can normalise to the same name; keep the first.
        aligned = aligned.loc[:, ~aligned.columns.duplicated()]
        aligned[schema.SOURCE_FILE_COLUMN] = name
        frames.append(aligned)
        manifest.append({"file": name, "rows": len(aligned),
                         "columns": len(aligned.columns) - 1, "new_columns": new,
                         "shared_columns": len(aligned.columns) - 1 - new})

    combined = pd.concat(frames, ignore_index=True, sort=False)
    # Column order: first appearance across the files, with the marker last.
    order = [c for c in canonical.values() if c in combined.columns]
    combined = combined[order + [schema.SOURCE_FILE_COLUMN]]
    # A column absent from one file arrives as NaN; the rest of the pipeline
    # expects the all-string, blank-for-empty frame that ``read_raw`` produces.
    combined = combined.astype("string").fillna("")
    return combined, pd.DataFrame(manifest)


def read_files(files: list[tuple[str, bytes]]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Read and combine several uploads, naming the file that fails."""
    parts = []
    for name, data in files:
        with ingest_stage("read", name):
            parts.append((name, read_raw(name, data)))
    label = ", ".join(name for name, _ in files)
    with ingest_stage("combine", label):
        return combine_raw(parts)


def dataset_label(files: list[tuple[str, bytes]]) -> str:
    """Display name for a dataset assembled from one or more files."""
    if len(files) == 1:
        return files[0][0]
    return f"{len(files)} files: " + ", ".join(name for name, _ in files)
