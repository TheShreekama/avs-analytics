"""Performance stress test — validates the 500k-row / 100-column target.

Generates a large synthetic dataset matching the sample schema, then times the
end-to-end cleaning build and representative report aggregations.

Run with:  python tests/stress_test.py [n_rows]
"""
import os
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import SAMPLE_DATA
from app.core import analytics, cleaning, loader, mapping


def synthesize(n: int) -> pd.DataFrame:
    base = loader.read_raw_path(SAMPLE_DATA)
    rng = np.random.default_rng(42)
    idx = rng.integers(0, len(base), size=n)
    big = base.iloc[idx].reset_index(drop=True).copy()

    # Vary dates across ~3 years and ids so aggregations are realistic.
    start = pd.Timestamp("2023-01-01")
    days = rng.integers(0, 1100, size=n)
    created = start + pd.to_timedelta(days, unit="D")
    approved = created + pd.to_timedelta(rng.integers(1, 40, size=n), unit="D")
    big["Nom. Created Date"] = created.strftime("%m-%d-%Y")
    big["Nom. Approval Date"] = approved.strftime("%m-%d-%Y")
    big["Task ID"] = (np.arange(n) + 100000).astype(str)
    big["TPID"] = (rng.integers(1, n // 3 + 2, size=n)).astype(str)
    # pad to 100+ columns to hit the column target
    for i in range(max(0, 100 - big.shape[1])):
        big[f"extra_col_{i}"] = ""
    return big


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 500_000
    print(f"=== AVS Analytics stress test: {n:,} rows ===")

    t0 = time.perf_counter()
    raw = synthesize(n)
    print(f"synthesize           {raw.shape[0]:,} x {raw.shape[1]} cols   "
          f"{time.perf_counter()-t0:6.2f}s")

    mp = mapping.resolve_mapping(list(raw.columns))

    t0 = time.perf_counter()
    fact, report = cleaning.build_fact_frame(raw, mp)
    print(f"build_fact_frame     {time.perf_counter()-t0:6.2f}s   "
          f"(dq_rows={report['dq_rows']:,})")

    t0 = time.perf_counter()
    con = loader.make_connection(fact)
    print(f"duckdb ingest        {time.perf_counter()-t0:6.2f}s")

    where = analytics.build_where({"ww_region": ["Americas - Enterprise"]})
    queries = [
        ("count_by status", lambda: analytics.count_by(con, "", "migration_status_label")),
        ("crosstab reg×eos", lambda: analytics.crosstab(con, "", "ww_region", "eos_status")),
        ("timeseries month", lambda: analytics.timeseries(con, "", "approval_date", "month")),
        ("closure_rate_by", lambda: analytics.closure_rate_by(con, "", "ww_region")),
        ("sankey", lambda: analytics.sankey_avs_to_azure(con, "")),
        ("filtered count", lambda: analytics.total_rows(con, where)),
        ("fetch 500 rows", lambda: analytics.fetch_rows(
            con, "", ["task_id", "customer_name", "total_acr"], "approval_date", True, 500)),
    ]
    print("--- query timings ---")
    worst = 0.0
    for name, fn in queries:
        t0 = time.perf_counter()
        fn()
        dt = time.perf_counter() - t0
        worst = max(worst, dt)
        print(f"  {name:20} {dt*1000:7.1f} ms")

    print(f"\nSlowest query: {worst*1000:.0f} ms")
    assert worst < 2.0, "a query took >2s — investigate"
    print("PASS: all aggregations responsive at scale.")


if __name__ == "__main__":
    main()
