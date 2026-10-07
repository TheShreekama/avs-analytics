"""What a Migration Status *means*, whichever document it was written in.

Two documents state a migration's status, each with its own numbering:

* the **FDO export** — ``1 - Validating Commitment & Initial Scope`` …
  ``4 - Executing Migration``, ``5 - Deferred By Customer``,
  ``6 - Cancelled / Archived``, ``7 - Completed``;
* the **EOS tracking sheet** — ``Kick-Off Awaited`` … ``5. Sign-off
  Pending``, ``Completed``, ``On Hold``, ``Cancelled``.

The numbers collide (6 is *Cancelled* in one and *Completed* in the other), so
no rule may test a number.  Every row instead carries ``status_class`` — one of
the classes below — and every rule reads that.  The number and the wording stay
on the row for display, beside ``status_source``, which says which document
answered.
"""
from __future__ import annotations

import pandas as pd

#: Still moving through the stages: FDO 1-4, tracker 1-5.
IN_FLIGHT = "in_flight"
#: Finished: FDO 7, tracker 6.
COMPLETED = "completed"
#: Paused by the customer: FDO 5 "Deferred By Customer".
DEFERRED = "deferred"
#: Paused: tracker 7 "On Hold".
ON_HOLD = "on_hold"
#: Stopped for good: FDO 6 "Cancelled / Archived", tracker 8 "Cancelled".
CANCELLED = "cancelled"
#: Blank, or a status neither vocabulary names.
UNKNOWN = "unknown"

#: The classes a migration is no longer progressing in.
STOPPED = (DEFERRED, ON_HOLD, CANCELLED)
#: Closed for good — a wave in one of these is history, not work in hand.
CLOSED = (COMPLETED, CANCELLED)

SOURCE_FDO = "FDO export"
SOURCE_TRACKER = "EOS tracker"

#: FDO Migration Status codes, by class.
FDO_IN_FLIGHT_CODES = (1, 2, 3, 4)
FDO_DEFERRED_CODE = 5
FDO_CANCELLED_CODE = 6
FDO_COMPLETED_CODE = 7


def fdo_status_class(code: pd.Series, label: pd.Series) -> pd.Series:
    """The class of each FDO Migration Status, by its code or else its wording."""
    code = pd.to_numeric(code, errors="coerce")
    text = label.astype("string").str.lower().fillna("")
    out = pd.Series(UNKNOWN, index=code.index, dtype="object")
    out[text.str.contains("defer", na=False).to_numpy()] = DEFERRED
    out[text.str.contains("cancel|archiv", regex=True, na=False).to_numpy()] = CANCELLED
    out[text.str.contains("complete", na=False).to_numpy()] = COMPLETED
    out[code.isin(FDO_IN_FLIGHT_CODES).fillna(False).to_numpy()] = IN_FLIGHT
    out[code.eq(FDO_DEFERRED_CODE).fillna(False).to_numpy()] = DEFERRED
    out[code.eq(FDO_CANCELLED_CODE).fillna(False).to_numpy()] = CANCELLED
    out[code.eq(FDO_COMPLETED_CODE).fillna(False).to_numpy()] = COMPLETED
    return out


def status_class(df: pd.DataFrame) -> pd.Series:
    """``status_class`` off a frame, worked out from the FDO code where absent.

    Frames built by :func:`app.core.cleaning.build_fact_frame` (and every table
    DuckDB serves from them) carry the column; a frame assembled by hand for a
    one-off check may not, and is read the way the export alone would be.
    """
    if df.empty:
        return pd.Series(dtype="object")
    if "status_class" in df.columns:
        return df["status_class"].astype("object").where(
            df["status_class"].notna(), UNKNOWN)
    label = df.get("migration_status_label",
                   df.get("migration_status", pd.Series("", index=df.index)))
    return fdo_status_class(df.get("migration_status_code",
                                   pd.Series(pd.NA, index=df.index)), label)


def is_class(df: pd.DataFrame, *classes: str) -> pd.Series:
    if df.empty:
        return pd.Series(dtype=bool)
    return status_class(df).isin(classes).astype(bool)
