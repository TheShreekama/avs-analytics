"""DuckDB-backed aggregations and trend builders.

All reporting queries run as SQL against an in-memory table so the app stays
responsive at the 500k-row / 100-column target.  Two tables are available:
``fact`` (one row per wave/nomination) and ``customer`` (one row per customer,
deduplicated across waves).  Every helper takes an optional ``table`` argument;
when omitted it uses the module's *current table*, which a report sets once via
``use_table`` based on the global counting-mode toggle.  Tests and the exporter
can still pass ``table=`` explicitly.

Filters are compiled to a single reusable WHERE clause; charts/tables call the
small helper functions here.
"""
from __future__ import annotations

import pandas as pd

_CURRENT_TABLE = "fact"


def use_table(name: str | None) -> None:
    """Set the default table for subsequent queries in this script run."""
    global _CURRENT_TABLE
    _CURRENT_TABLE = name or "fact"


def _t(table: str | None) -> str:
    return table or _CURRENT_TABLE


def current_table() -> str:
    """The table name reports are currently querying (per the counting mode)."""
    return _CURRENT_TABLE


def _q(val: str) -> str:
    """Quote a literal for SQL, escaping embedded single quotes."""
    return "'" + str(val).replace("'", "''") + "'"


def build_where(filters: dict | None) -> str:
    """Compile a filters dict into a SQL WHERE clause (returns '' if empty).

    Recognised keys:
      * ``<column>: [values]``         -> column IN (...)
      * ``_date: {col, start, end, include_null?}`` -> inclusive date range on a
        column; ``include_null`` keeps rows whose date is missing (they are
        excluded by a range filter otherwise)
      * ``_flags: {col: bool}``        -> boolean column equals value
    """
    if not filters:
        return ""
    clauses: list[str] = []
    for key, val in filters.items():
        if key == "_date" and val and val.get("col"):
            col, start, end = val["col"], val.get("start"), val.get("end")
            parts = []
            if start is not None:
                parts.append(f'"{col}" >= {_q(pd.Timestamp(start).date())}')
            if end is not None:
                parts.append(f'"{col}" <= {_q(pd.Timestamp(end).date())}')
            if parts:
                clause = "(" + " AND ".join(parts) + ")"
                if val.get("include_null"):
                    clause = f'({clause} OR "{col}" IS NULL)'
                clauses.append(clause)
        elif key == "_flags" and val:
            for col, flag in val.items():
                clauses.append(f'"{col}" = {str(bool(flag)).upper()}')
        elif isinstance(val, (list, tuple, set)) and len(val):
            inlist = ", ".join(_q(v) for v in val)
            clauses.append(f'"{key}" IN ({inlist})')
    return ("WHERE " + " AND ".join(clauses)) if clauses else ""


def _where_and(where: str, extra: str) -> str:
    if not extra:
        return where
    return f"{where} AND {extra}" if where else f"WHERE {extra}"


# --------------------------------------------------------------------------- #
# Reporting scope (primary AVS onboarding vs AVS → Azure Native)
# --------------------------------------------------------------------------- #
def scope_clause(scope: str | None) -> str:
    """SQL predicate for a reporting scope (``''`` when unscoped).

    ``primary``  -> AVS Migration Nominations (onboarding); excludes "(From AVS)".
    ``from_avs`` -> AVS → Azure Native only ("(From AVS)" offerings).
    """
    if scope == "primary":
        return '"is_from_avs" = FALSE'
    if scope == "from_avs":
        return '"is_from_avs" = TRUE'
    return ""


def apply_scope(where: str, scope: str | None) -> str:
    """AND the scope predicate onto an existing WHERE clause."""
    return _where_and(where, scope_clause(scope))


# --------------------------------------------------------------------------- #
# Generic aggregations
# --------------------------------------------------------------------------- #
def count_by(con, where: str, dim: str, top: int | None = None,
             dropna: bool = False, table: str | None = None) -> pd.DataFrame:
    extra = "" if dropna is False else f'"{dim}" IS NOT NULL'
    sql = f'SELECT "{dim}" AS category, COUNT(*) AS count FROM {_t(table)} ' \
          f'{_where_and(where, extra)} GROUP BY 1 ORDER BY 2 DESC'
    df = con.execute(sql).fetchdf()
    if top:
        df = df.head(top)
    return df


def distinct_count_by(con, where: str, dim: str, distinct_col: str,
                      table: str | None = None) -> pd.DataFrame:
    sql = f'SELECT "{dim}" AS category, COUNT(DISTINCT "{distinct_col}") AS count ' \
          f'FROM {_t(table)} {where} GROUP BY 1 ORDER BY 2 DESC'
    return con.execute(sql).fetchdf()


def sum_by(con, where: str, dim: str, measure: str, table: str | None = None) -> pd.DataFrame:
    sql = f'SELECT "{dim}" AS category, COALESCE(SUM("{measure}"),0) AS total ' \
          f'FROM {_t(table)} {where} GROUP BY 1 ORDER BY 2 DESC'
    return con.execute(sql).fetchdf()


def crosstab(con, where: str, row_dim: str, col_dim: str, table: str | None = None) -> pd.DataFrame:
    """Row×col count matrix (for heatmaps / stacked bars)."""
    sql = f'SELECT "{row_dim}" AS row, "{col_dim}" AS col, COUNT(*) AS count ' \
          f'FROM {_t(table)} {where} GROUP BY 1, 2'
    long = con.execute(sql).fetchdf()
    if long.empty:
        return long
    return long.pivot_table(index="row", columns="col", values="count",
                            aggfunc="sum", fill_value=0)


def timeseries(con, where: str, date_col: str, grain: str = "month", extra_where: str = "",
               distinct_col: str | None = None, table: str | None = None) -> pd.DataFrame:
    """Counts over time bucketed by grain (day/week/month/quarter/year)."""
    grain = grain.lower()
    bucket = f'date_trunc({_q(grain)}, "{date_col}")'
    measure = f'COUNT(DISTINCT "{distinct_col}")' if distinct_col else "COUNT(*)"
    w = _where_and(where, f'"{date_col}" IS NOT NULL')
    w = _where_and(w, extra_where) if extra_where else w
    sql = f'SELECT {bucket} AS period, {measure} AS value FROM {_t(table)} {w} ' \
          f'GROUP BY 1 ORDER BY 1'
    df = con.execute(sql).fetchdf()
    if not df.empty:
        df["period"] = pd.to_datetime(df["period"])
        df["cumulative"] = df["value"].cumsum()
    return df


def fetch_rows(con, where: str, columns: list[str], order_by: str | None = None,
               desc: bool = True, limit: int = 100, table: str | None = None) -> pd.DataFrame:
    cols = ", ".join(f'"{c}"' for c in columns)
    order = f' ORDER BY "{order_by}" {"DESC" if desc else "ASC"}' if order_by else ""
    sql = f'SELECT {cols} FROM {_t(table)} {where}{order} LIMIT {int(limit)}'
    return con.execute(sql).fetchdf()


def scalar(con, where: str, expr: str, table: str | None = None) -> float:
    sql = f"SELECT {expr} FROM {_t(table)} {where}"
    res = con.execute(sql).fetchone()
    return res[0] if res and res[0] is not None else 0


def total_rows(con, where: str, table: str | None = None) -> int:
    return int(scalar(con, where, "COUNT(*)", table=table))


def select_all(con, where: str = "", table: str | None = None) -> pd.DataFrame:
    """Fetch the filtered frame (for insights / pandas-side calculations)."""
    return con.execute(f"SELECT * FROM {_t(table)} {where}").fetchdf()


# --------------------------------------------------------------------------- #
# Report-specific builders
# --------------------------------------------------------------------------- #
#: Operational age bands, oldest last.  ``aging_buckets`` (SQL) and
#: ``aging_bucket`` (pandas) must always agree, so both read this list.
AGING_BUCKETS = ["0-30 days", "31-60 days", "61-90 days", "91-180 days",
                 "180+ days", "Unknown"]


def aging_bucket(days) -> pd.Series:
    """``aging_buckets`` applied to a pandas column, so a chart can drill down."""
    d = pd.to_numeric(days, errors="coerce")
    out = pd.Series("180+ days", index=d.index, dtype="object")
    out[d <= 180] = "91-180 days"
    out[d <= 90] = "61-90 days"
    out[d <= 60] = "31-60 days"
    out[d <= 30] = "0-30 days"
    out[d.isna()] = "Unknown"
    return out


def aging_buckets(con, where: str, only_open: bool = True, table: str | None = None) -> pd.DataFrame:
    """Distribution of open-item age into operational buckets."""
    extra = '"is_open" = TRUE' if only_open else ""
    w = _where_and(where, extra) if extra else where
    sql = f"""
        SELECT bucket, COUNT(*) AS count FROM (
            SELECT CASE
                WHEN "aging_days" IS NULL THEN 'Unknown'
                WHEN "aging_days" <= 30  THEN '0-30 days'
                WHEN "aging_days" <= 60  THEN '31-60 days'
                WHEN "aging_days" <= 90  THEN '61-90 days'
                WHEN "aging_days" <= 180 THEN '91-180 days'
                ELSE '180+ days'
            END AS bucket
            FROM {_t(table)} {w}
        ) GROUP BY 1
    """
    df = con.execute(sql).fetchdf()
    df["bucket"] = pd.Categorical(df["bucket"], categories=AGING_BUCKETS, ordered=True)
    return df.sort_values("bucket").reset_index(drop=True)


def closure_rate_by(con, where: str, dim: str, table: str | None = None) -> pd.DataFrame:
    """Closure rate (%) per dimension value."""
    sql = f"""
        SELECT "{dim}" AS category,
               COUNT(*) AS total,
               SUM(CASE WHEN "is_closed" THEN 1 ELSE 0 END) AS closed,
               ROUND(100.0 * SUM(CASE WHEN "is_closed" THEN 1 ELSE 0 END)
                     / NULLIF(COUNT(*),0), 1) AS closure_rate
        FROM {_t(table)} {where} GROUP BY 1 ORDER BY closure_rate DESC
    """
    return con.execute(sql).fetchdf()


def approval_rate_by(con, where: str, dim: str, table: str | None = None) -> pd.DataFrame:
    sql = f"""
        SELECT "{dim}" AS category,
               COUNT(*) AS total,
               SUM(CASE WHEN "is_approved" THEN 1 ELSE 0 END) AS approved,
               ROUND(100.0 * SUM(CASE WHEN "is_approved" THEN 1 ELSE 0 END)
                     / NULLIF(COUNT(*),0), 1) AS approval_rate
        FROM {_t(table)} {where} GROUP BY 1 ORDER BY approval_rate DESC
    """
    return con.execute(sql).fetchdf()


def sankey_avs_to_azure(con, where: str, table: str | None = None,
                        track_dim: str = "factory_offering") -> pd.DataFrame:
    """Flows for the AVS→Azure-Native Sankey: track -> target -> stage."""
    w = _where_and(where, '"migration_direction" = \'AVS → Azure Native\'')
    w = _where_and(w, '"azure_target" IS NOT NULL')
    sql = f"""
        SELECT "{track_dim}" AS track,
               "azure_target" AS target,
               CASE WHEN "is_closed" THEN 'Completed'
                    WHEN "actual_start_date" IS NOT NULL THEN 'In Progress'
                    ELSE 'Started' END AS stage,
               COUNT(*) AS count
        FROM {_t(table)} {w}
        GROUP BY 1, 2, 3
    """
    return con.execute(sql).fetchdf()


def migration_stage_by_track(con, where: str, table: str | None = None,
                             track_dim: str = "factory_offering") -> pd.DataFrame:
    """Started / In Progress / Completed counts per migration track."""
    sql = f"""
        SELECT "{track_dim}" AS track,
               SUM(CASE WHEN "is_open" AND "actual_start_date" IS NULL THEN 1 ELSE 0 END) AS started,
               SUM(CASE WHEN "is_open" AND "actual_start_date" IS NOT NULL THEN 1 ELSE 0 END) AS in_progress,
               SUM(CASE WHEN "is_closed" THEN 1 ELSE 0 END) AS completed,
               COUNT(*) AS total
        FROM {_t(table)} {where} GROUP BY 1 ORDER BY total DESC
    """
    return con.execute(sql).fetchdf()


def distinct_values(con, col: str, table: str | None = None, where: str = "") -> list:
    """Distinct non-null values of a column, optionally restricted by a scope/where."""
    w = _where_and(where, f'"{col}" IS NOT NULL')
    sql = f'SELECT DISTINCT "{col}" AS v FROM {_t(table)} {w} ORDER BY 1'
    return [r[0] for r in con.execute(sql).fetchall()]


def date_bounds(con, col: str, table: str | None = None) -> tuple:
    res = con.execute(f'SELECT MIN("{col}"), MAX("{col}") FROM {_t(table)}').fetchone()
    return res[0], res[1]
