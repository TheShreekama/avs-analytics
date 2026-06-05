"""Core-engine tests validated against the bundled sample dataset.

Run with:  python -m pytest tests/test_core.py -v
"""
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import SAMPLE_DATA
from app.core import analytics, cleaning, insights, loader, mapping, metrics, schema


@pytest.fixture(scope="module")
def raw():
    return loader.read_raw_path(SAMPLE_DATA)


@pytest.fixture(scope="module")
def built(raw):
    mp = mapping.resolve_mapping(list(raw.columns))
    fact, report = cleaning.build_fact_frame(raw, mp)
    con = loader.make_connection(fact)
    return mp, fact, report, con


# --------------------------------------------------------------------------- #
# Mapping
# --------------------------------------------------------------------------- #
def test_sample_loads(raw):
    assert raw.shape[0] == 11          # 11 data rows (10 distinct accounts)
    assert raw.shape[1] == 88          # 88 columns


def test_auto_map_covers_required(raw):
    mp = mapping.resolve_mapping(list(raw.columns))
    cov = mapping.mapping_coverage(mp)
    assert cov["ok"], f"missing required: {cov['missing_required']}"
    assert mp["task_id"] == "Task ID"
    assert mp["total_acr"] == "Total ACR"


def test_auto_map_synonyms():
    # renamed headers should still map via synonyms
    mp = schema.auto_map(["Task ID", "Customer", "WW", "Offering", "Created Date",
                          "Approved Date", "Delivery Status", "Nom Status", "ACR"])
    assert mp["customer_name"] == "Customer"
    assert mp["ww_region"] == "WW"
    assert mp["total_acr"] == "ACR"


# --------------------------------------------------------------------------- #
# Cleaning / derivations
# --------------------------------------------------------------------------- #
def test_dates_parsed(built):
    _, fact, _, _ = built
    assert fact["created_date"].notna().all()
    assert pd.api.types.is_datetime64_any_dtype(fact["approval_date"])


def test_currency_indian_grouping():
    s = pd.Series(["$1,92,000", "$2,50,992", "$1,694,000", "$0", "05-31-2025", ""])
    out = cleaning.parse_currency_series(s)
    assert out.iloc[0] == 192000
    assert out.iloc[1] == 250992
    assert out.iloc[2] == 1694000
    assert out.iloc[3] == 0
    assert np.isnan(out.iloc[4])       # a date is not a number
    assert np.isnan(out.iloc[5])


def test_contaminated_cores_nulled(built):
    _, fact, report, _ = built
    # the FORTUNE BRANDS row has "$22,968" in Total Cores -> must be nulled + flagged
    assert report["dq"].get("contaminated_numeric", 0) >= 1
    assert fact["total_cores"].max() < 1000   # 22968 must NOT survive


def test_ww_region_normalized(built):
    _, fact, _, _ = built
    assert set(fact["ww_region"].unique()) <= {
        "Americas - Enterprise", "ASIA - Enterprise", "EMEA - Enterprise", "Unknown"}
    # no numeric-prefixed values remain
    assert not fact["ww_region"].str.match(r"^\d").any()


def test_migration_direction_and_target(built):
    _, fact, _, _ = built
    assert (fact["migration_direction"] == "AVS → Azure Native").sum() == 6
    assert (fact["migration_direction"] == "Onboard to AVS").sum() == 4
    fromavs = fact[fact["migration_direction"] == "AVS → Azure Native"]
    assert fromavs["azure_target"].notna().all()


def test_eos_status_taxonomy(built):
    _, fact, _, _ = built
    valid = {"On Track", "Completed", "At Risk", "Delayed", "Blocked", "Cancelled"}
    assert set(fact["eos_status"].unique()) <= valid
    assert (fact["eos_status"] == "Completed").sum() == 5


def test_approval_closure_flags(built):
    _, fact, _, _ = built
    assert fact["is_approved"].sum() == 11     # all sample rows approved
    assert fact["is_closed"].sum() == 5
    assert (fact["is_open"] & fact["is_closed"]).sum() == 0   # mutually exclusive


def test_data_quality_flags(built):
    _, fact, report, _ = built
    assert report["dq_rows"] >= 5
    assert "dirty_region" in report["dq"]
    assert "bad_segment" in report["dq"]       # 'Approved' leaked into Customer Segment


def test_migration_status_split(built):
    _, fact, _, _ = built
    assert (fact["migration_status_code"] == 7).any()
    assert "Completed" in fact["migration_status_label"].values


# --------------------------------------------------------------------------- #
# Analytics (DuckDB)
# --------------------------------------------------------------------------- #
def test_build_where_escaping():
    w = analytics.build_where({"ww_region": ["O'Brien", "Americas - Enterprise"]})
    assert "O''Brien" in w                      # single quotes escaped


def test_count_by_and_filter(built):
    _, _, _, con = built
    total = analytics.total_rows(con, "")
    assert total == 11
    w = analytics.build_where({"ww_region": ["Americas - Enterprise"]})
    assert analytics.total_rows(con, w) == 7


def test_timeseries(built):
    _, _, _, con = built
    ts = analytics.timeseries(con, "", "created_date", "month")
    assert not ts.empty
    assert ts["value"].sum() == 11
    assert (ts["cumulative"].diff().dropna() >= 0).all()   # monotonic


def test_sankey_only_from_avs(built):
    _, _, _, con = built
    flow = analytics.sankey_avs_to_azure(con, "")
    assert flow["count"].sum() == 6


# --------------------------------------------------------------------------- #
# Metrics + insights
# --------------------------------------------------------------------------- #
def test_period_counts(built):
    _, fact, report, _ = built
    counts = metrics.count_in_periods(fact["approval_date"], report["as_of"])
    assert counts["ytd"] >= counts["quarter"] >= counts["month"] >= counts["week"]


def test_currency_formatting():
    assert metrics.fmt_currency(2_522_121) == "$2.52M"
    assert metrics.fmt_currency(0) == "$0"


def test_insights_generated(built):
    _, fact, _, _ = built
    ins = insights.generate_insights(fact)
    assert len(ins) >= 8
    cats = {i.category for i in ins}
    assert "Data Quality" in cats
    assert any(i.severity == "critical" for i in ins)   # DQ issues exist in sample


def test_insights_empty_safe():
    empty = pd.DataFrame(columns=["tpid", "ww_region", "is_approved"])
    out = insights.generate_insights(empty)
    assert len(out) == 1   # graceful "no data" message
