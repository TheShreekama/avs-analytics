"""Missing-value helpers that never raise on ``pd.NA``.

Every column arrives from the ingest layer as pandas' nullable ``string`` dtype,
whose missing marker is ``pd.NA`` — and ``pd.NA`` has no truth value.  Any
``if not value``, ``value in (...)`` or ``bool(mask)`` reached by a ``pd.NA``
raises ``TypeError: boolean value of NA is ambiguous``, which is what a partial
upload used to produce: a file without a *Primary Migration Path* column made
every row's path ``pd.NA``, and the direction classifier tested ``not path``
before it tested for missingness.

The two helpers below are the fix, and the reason they live in a leaf module of
their own: ``segments`` (which has no internal imports), ``cleaning`` and
``metrics`` all need them.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

#: Values that a source cell can carry while meaning "nothing was entered".
_BLANK_TEXT = {"", "nan", "none", "null", "<na>", "n/a", "na", "-", "--"}


def is_blank(value) -> bool:
    """True when a scalar is missing or is text that means "not entered".

    Safe for ``pd.NA``, ``None``, ``float('nan')``, ``pd.NaT`` and blank strings,
    in that order — the missingness test always comes *first*, so no caller ever
    puts a ``pd.NA`` into a boolean context.
    """
    if value is None or value is pd.NA or value is pd.NaT:
        return True
    try:
        missing = pd.isna(value)
    except (TypeError, ValueError):       # arrays, sets, and other odd cells
        return False
    if missing is True:
        return True
    if not isinstance(value, str):
        return False
    return value.strip().lower() in _BLANK_TEXT


def as_bool_mask(mask, index=None) -> pd.Series:
    """Coerce a possibly-nullable boolean mask to a plain ``bool`` Series.

    Comparisons between nullable columns propagate ``pd.NA`` ("Americas" != NA
    is NA, not True), so a mask built from them is ``boolean`` dtype rather than
    ``bool``.  Handing that to ``numpy`` raises the same ambiguity error.  A
    missing answer means "this row did not match", so ``pd.NA`` becomes False.
    """
    if not isinstance(mask, pd.Series):
        mask = pd.Series(mask, index=index)
    if mask.empty:
        return pd.Series(np.zeros(0, dtype=bool), index=mask.index)
    return mask.fillna(False).astype(bool)
