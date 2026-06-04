"""DuckDB-backed aggregations and trend builders.

All reporting queries run as SQL against the in-memory ``fact`` table so the app
stays responsive at the 500k-row / 100-column target.  Filters are compiled to a
single reusable WHERE clause; charts/tables call the small helper functions here.
"""
from __future__ import annotations

import duckdb
import pandas as pd


def _q(val: str) -> str:
    """Quote a literal for SQL, escaping embedded single quotes."""
    return "'" + str(val).replace("'", "''") + "'"


def build_where(filters: dict | None) -> str:
    """Compile a filters dict into a SQL WHERE clause (returns '' if empty).

    Recognised keys:
      * ``<column>: [values]``         -> column IN (...)
      * ``_date: {col, start, end}``   -> inclusive date range on a column
      * ``_flags: {col: bool}``        -> boolean column equals value
    """
    if not filters:
        return ""
    clauses: list[str] = []
    for key, val in filters.items():
        if key == "_date" and val and val.get("col"):
            col, start, end = val["col"], val.get("start"), val.get("end")
            if start is not None:
                clauses.append(f'"{col}" >= {_q(pd.Timestamp(start).date())}')
            if end is not None:
                clauses.append(f'"{col}" <= {_q(pd.Timestamp(end).date())}')
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
# Generic aggregations
# --------------------------------------------------------------------------- #
def count_by(con, where: str, dim: str, top: int | None = None,
             dropna: bool = False) -> pd.DataFrame:
    extra = "" if dropna is False else f'"{dim}" IS NOT NULL'
    sql = f'SELECT "{dim}" AS category, COUNT(*) AS count FROM fact ' \
          f'{_where_and(where, extra)} GROUP BY 1 ORDER BY 2 DESC'
    df = con.execute(sql).fetchdf()
    if top:
        df = df.head(top)
    return df


def distinct_count_by(con, where: str, dim: str, distinct_col: str) -> pd.DataFrame:
    sql = f'SELECT "{dim}" AS category, COUNT(DISTINCT "{distinct_col}") AS count ' \
          f'FROM fact {where} GROUP BY 1 ORDER BY 2 DESC'
    return con.execute(sql).fetchdf()


def sum_by(con, where: str, dim: str, measure: str) -> pd.DataFrame:
    sql = f'SELECT "{dim}" AS category, COALESCE(SUM("{measure}"),0) AS total ' \
          f'FROM fact {where} GROUP BY 1 ORDER BY 2 DESC'
    return con.execute(sql).fetchdf()


def crosstab(con, where: str, row_dim: str, col_dim: str) -> pd.DataFrame:
    """Row×col count matrix (for heatmaps / stacked bars)."""
    sql = f'SELECT "{row_dim}" AS row, "{col_dim}" AS col, COUNT(*) AS count ' \
          f'FROM fact {where} GROUP BY 1, 2'
    long = con.execute(sql).fetchdf()
    if long.empty:
        return long
    return long.pivot_table(index="row", columns="col", values="count",
                            aggfunc="sum", fill_value=0)


def timeseries(con, where: str, date_col: str, grain: str = "month",
               extra_where: str = "", distinct_col: str | None = None) -> pd.DataFrame:
    """Counts over time bucketed by grain (day/week/month/quarter/year)."""
    grain = grain.lower()
    bucket = f'date_trunc({_q(grain)}, "{date_col}")'
    measure = f'COUNT(DISTINCT "{distinct_col}")' if distinct_col else "COUNT(*)"
    w = _where_and(where, f'"{date_col}" IS NOT NULL')
    w = _where_and(w, extra_where) if extra_where else w
    sql = f'SELECT {bucket} AS period, {measure} AS value FROM fact {w} ' \
          f'GROUP BY 1 ORDER BY 1'
    df = con.execute(sql).fetchdf()
    if not df.empty:
        df["period"] = pd.to_datetime(df["period"])
        df["cumulative"] = df["value"].cumsum()
    return df


def fetch_rows(con, where: str, columns: list[str], order_by: str | None = None,
               desc: bool = True, limit: int = 100) -> pd.DataFrame:
    cols = ", ".join(f'"{c}"' for c in columns)
    order = f' ORDER BY "{order_by}" {"DESC" if desc else "ASC"}' if order_by else ""
    sql = f'SELECT {cols} FROM fact {where}{order} LIMIT {int(limit)}'
    return con.execute(sql).fetchdf()


def scalar(con, where: str, expr: str) -> float:
    sql = f"SELECT {expr} FROM fact {where}"
    res = con.execute(sql).fetchone()
    return res[0] if res and res[0] is not None else 0


def total_rows(con, where: str) -> int:
    return int(scalar(con, where, "COUNT(*)"))


# --------------------------------------------------------------------------- #
# Report-specific builders
# --------------------------------------------------------------------------- #
def aging_buckets(con, where: str, only_open: bool = True) -> pd.DataFrame:
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
            FROM fact {w}
        ) GROUP BY 1
    """
    df = con.execute(sql).fetchdf()
    order = ['0-30 days', '31-60 days', '61-90 days', '91-180 days', '180+ days', 'Unknown']
    df["bucket"] = pd.Categorical(df["bucket"], categories=order, ordered=True)
    return df.sort_values("bucket").reset_index(drop=True)


def closure_rate_by(con, where: str, dim: str) -> pd.DataFrame:
    """Closure rate (%) per dimension value."""
    sql = f"""
        SELECT "{dim}" AS category,
               COUNT(*) AS total,
               SUM(CASE WHEN "is_closed" THEN 1 ELSE 0 END) AS closed,
               ROUND(100.0 * SUM(CASE WHEN "is_closed" THEN 1 ELSE 0 END)
                     / NULLIF(COUNT(*),0), 1) AS closure_rate
        FROM fact {where} GROUP BY 1 ORDER BY closure_rate DESC
    """
    return con.execute(sql).fetchdf()


def approval_rate_by(con, where: str, dim: str) -> pd.DataFrame:
    sql = f"""
        SELECT "{dim}" AS category,
               COUNT(*) AS total,
               SUM(CASE WHEN "is_approved" THEN 1 ELSE 0 END) AS approved,
               ROUND(100.0 * SUM(CASE WHEN "is_approved" THEN 1 ELSE 0 END)
                     / NULLIF(COUNT(*),0), 1) AS approval_rate
        FROM fact {where} GROUP BY 1 ORDER BY approval_rate DESC
    """
    return con.execute(sql).fetchdf()


def sankey_avs_to_azure(con, where: str) -> pd.DataFrame:
    """Flows for the AVS→Azure-Native Sankey: track -> target -> stage."""
    w = _where_and(where, '"migration_direction" = \'AVS → Azure Native\'')
    sql = f"""
        SELECT "factory_offering" AS track,
               "azure_target" AS target,
               CASE WHEN "is_closed" THEN 'Completed'
                    WHEN "actual_start_date" IS NOT NULL THEN 'In Progress'
                    ELSE 'Started' END AS stage,
               COUNT(*) AS count
        FROM fact {w}
        GROUP BY 1, 2, 3
    """
    return con.execute(sql).fetchdf()


def migration_stage_by_track(con, where: str) -> pd.DataFrame:
    """Started / In Progress / Completed counts per migration track."""
    sql = f"""
        SELECT "factory_offering" AS track,
               SUM(CASE WHEN "is_closed" THEN 0
                        WHEN "actual_start_date" IS NULL THEN 1 ELSE 0 END) AS started,
               SUM(CASE WHEN "is_closed" THEN 0
                        WHEN "actual_start_date" IS NOT NULL THEN 1 ELSE 0 END) AS in_progress,
               SUM(CASE WHEN "is_closed" THEN 1 ELSE 0 END) AS completed,
               COUNT(*) AS total
        FROM fact {where} GROUP BY 1 ORDER BY total DESC
    """
    return con.execute(sql).fetchdf()


def select_all(con, where: str = "") -> pd.DataFrame:
    """Fetch the filtered fact frame (for insights / pandas-side calculations)."""
    return con.execute(f"SELECT * FROM fact {where}").fetchdf()


def distinct_values(con, col: str) -> list:
    sql = f'SELECT DISTINCT "{col}" AS v FROM fact WHERE "{col}" IS NOT NULL ORDER BY 1'
    return [r[0] for r in con.execute(sql).fetchall()]


def date_bounds(con, col: str) -> tuple:
    res = con.execute(f'SELECT MIN("{col}"), MAX("{col}") FROM fact').fetchone()
    return res[0], res[1]
