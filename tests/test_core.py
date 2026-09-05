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


# --------------------------------------------------------------------------- #
# Customer rollup (wave deduplication)
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def customer(built):
    from app.core import rollup
    _, fact, report, _ = built
    return rollup.build_customer_rollup(fact, report["as_of"])


def test_rollup_dedups_customers(customer):
    # 11 waves collapse to 10 customers (Novanta has 2 waves)
    assert len(customer) == 10
    nov = customer[customer["customer_name"].str.contains("Novanta", case=False)]
    assert len(nov) == 1
    assert int(nov["n_waves"].iloc[0]) == 2


def test_rollup_av36_membership(customer):
    # exactly one customer (CHUBB) has an AV36/EOS path wave
    assert int(customer["is_av36_eos"].sum()) == 1
    assert customer.loc[customer["is_av36_eos"], "customer_name"].iloc[0].upper().startswith("CHUBB")


def test_rollup_avs_to_azure_dedup(customer):
    # 6 from-AVS waves but Novanta's two collapse -> 5 distinct customers
    assert int(customer["is_avs_to_azure"].sum()) == 5


def test_rollup_first_wave_approval(customer):
    # Novanta's first wave is the lowest wave number (Wave-2) -> 2025-11-12
    nov = customer[customer["customer_name"].str.contains("Novanta", case=False)].iloc[0]
    assert pd.Timestamp(nov["approval_date"]) == pd.Timestamp("2025-11-12")


def test_rollup_status_from_last_wave(customer):
    # Novanta's last wave (Wave-3) is blocked
    nov = customer[customer["customer_name"].str.contains("Novanta", case=False)].iloc[0]
    assert nov["eos_status"] == "Blocked"
    assert not bool(nov["is_closed"])


def test_av36_eos_path_detector():
    assert cleaning.is_av36_eos_path("AVS36 - EGS")
    assert cleaning.is_av36_eos_path("AV36 EOS Migration")
    assert not cleaning.is_av36_eos_path("SQL Server DB Migration (From AVS)")


# --------------------------------------------------------------------------- #
# Region geography + reporting scope
# --------------------------------------------------------------------------- #
def test_region_geo_strips_segment(built):
    _, fact, _, _ = built
    # ww_region keeps the full value; region_geo is geography only.
    assert set(fact["region_geo"].unique()) <= {"Americas", "EMEA", "ASIA", "Unknown"}
    assert (fact["ww_region"].str.contains(" - ")).any()       # segment retained in ww_region
    assert not (fact["region_geo"].str.contains(" - ")).any()  # but not in region_geo


def test_scope_clause():
    assert analytics.scope_clause("primary") == '"is_from_avs" = FALSE'
    assert analytics.scope_clause("from_avs") == '"is_from_avs" = TRUE'
    assert analytics.scope_clause(None) == ""


def test_scope_splits_offerings(built):
    _, _, _, con = built
    primary = analytics.total_rows(con, analytics.apply_scope("", "primary"))
    from_avs = analytics.total_rows(con, analytics.apply_scope("", "from_avs"))
    assert primary == 5 and from_avs == 6 and primary + from_avs == 11
    # primary scope is exactly the "AVS Migration Nominations" offering
    offerings = analytics.distinct_values(con, "factory_offering",
                                          where=analytics.apply_scope("", "primary"))
    assert offerings == ["AVS Migration Nominations"]
    # from-AVS scope never includes it
    from_offerings = analytics.distinct_values(con, "factory_offering",
                                               where=analytics.apply_scope("", "from_avs"))
    assert "AVS Migration Nominations" not in from_offerings


def test_scope_on_customer_table(built):
    from app.core import rollup
    _, fact, report, _ = built
    cust = rollup.build_customer_rollup(fact, report["as_of"])
    assert "is_from_avs" in cust.columns
    assert "region_geo" in cust.columns
    # uniform flag matches the AVS→Azure membership column
    assert bool((cust["is_from_avs"] == cust["is_avs_to_azure"]).all())


# --------------------------------------------------------------------------- #
# Date-range presets
# --------------------------------------------------------------------------- #
def test_date_preset_ranges():
    as_of = pd.Timestamp("2026-06-17")   # a Wednesday
    wk = metrics.date_preset_range(as_of, "This week")
    assert wk[0] == pd.Timestamp("2026-06-15") and wk[1] == as_of   # Monday-based
    lw = metrics.date_preset_range(as_of, "Last week")
    assert lw[0] == pd.Timestamp("2026-06-08") and lw[1] == pd.Timestamp("2026-06-14")
    lm = metrics.date_preset_range(as_of, "Last month")
    assert lm[0] == pd.Timestamp("2026-05-01") and lm[1] == pd.Timestamp("2026-05-31")
    # Microsoft FY starts in July: June 2026 is still FY2026 (started Jul 2025).
    fy = metrics.date_preset_range(as_of, "This FY", 7)
    assert fy[0] == pd.Timestamp("2025-07-01")
    assert metrics.date_preset_range(as_of, "All time") is None


def test_fiscal_year_start():
    assert metrics.fiscal_year_start(pd.Timestamp("2026-06-30"), 7) == pd.Timestamp("2025-07-01")
    assert metrics.fiscal_year_start(pd.Timestamp("2026-07-01"), 7) == pd.Timestamp("2026-07-01")


# --------------------------------------------------------------------------- #
# Robustness against real-world exports
# --------------------------------------------------------------------------- #
def test_eos_status_survives_uncoded_migration_status(raw):
    """A Migration Status with no numeric prefix must not break the build.

    ``migration_status_code`` is null for values like "Cancelled" / "On Hold",
    which makes every comparison a *nullable* boolean — ``np.select`` used to
    raise TypeError and take every page down with it.
    """
    mp = mapping.resolve_mapping(list(raw.columns))
    df = raw.copy()
    df[mp["migration_status"]] = ["Cancelled", "On Hold", ""] * 3 + ["7 - Completed", None]
    fact, _ = cleaning.build_fact_frame(df, mp)
    assert len(fact) == len(raw)
    assert fact["eos_status"].notna().all()
    assert set(fact["eos_status"]) <= {"Completed", "Cancelled", "Blocked", "At Risk",
                                       "Delayed", "On Track"}


def test_auto_map_does_not_claim_month_columns_as_dates():
    """Date fields only fall back onto headers that are actually dates."""
    headers = ["Task ID", "Customer Name", "Factory Offering", "WW Region",
               "Nomination Status", "Migration Status", "Nom. Created Date",
               "Milestone Estimated Completion Month"]
    m = schema.auto_map(headers)
    assert m["created_date"] == "Nom. Created Date"
    assert m["eta_date"] is None


# --------------------------------------------------------------------------- #
# Date parsing across export shapes
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("value,expected", [
    ("45855", "2025-07-17"),                    # unformatted Excel cell (serial day)
    ("45855.0", "2025-07-17"),
    ("2026-05-13", "2026-05-13"),
    ("05-13-2026", "2026-05-13"),
    ("13-May-2026", "2026-05-13"),
    ("May 13, 2026", "2026-05-13"),
    ("20260513", "2026-05-13"),
    ("2026-05-13 14:35:00", "2026-05-13"),      # time-of-day dropped: calendar day
    ("2026-05-13T00:00:00Z", "2026-05-13"),
    ("2026-05-13T00:00:00+05:30", "2026-05-13"),  # offset dropped, not shifted
])
def test_parse_date_series_formats(value, expected):
    got = cleaning.parse_date_series(pd.Series([value], dtype="string"))[0]
    assert got == pd.Timestamp(expected)


@pytest.mark.parametrize("values,expected", [
    (["13-05-2026", "01-06-2026"], ["2026-05-13", "2026-06-01"]),   # day-first column
    (["05-13-2026", "06-01-2026"], ["2026-05-13", "2026-06-01"]),   # month-first column
])
def test_parse_date_series_infers_order_per_column(values, expected):
    """An ambiguous d/m pair follows the column's evidence, not a per-value guess."""
    got = cleaning.parse_date_series(pd.Series(values, dtype="string"))
    assert list(got) == [pd.Timestamp(e) for e in expected]


def test_parse_date_series_rejects_non_dates():
    got = cleaning.parse_date_series(pd.Series(["N/A", "", "-", "Q3", "2026"], dtype="string"))
    assert got.isna().all()          # a bare year is a number, not a serial date


def test_excel_serial_dates_survive_the_full_build(raw):
    """A date column exported as serial numbers must not flag every row as bad."""
    mp = mapping.resolve_mapping(list(raw.columns))
    df = raw.copy()
    parsed = cleaning.parse_date_series(df[mp["created_date"]])
    df[mp["created_date"]] = [
        "" if pd.isna(d) else str((d.normalize() - pd.Timestamp("1899-12-30")).days)
        for d in parsed
    ]
    fact, report = cleaning.build_fact_frame(df, mp)
    assert report["dq"].get("bad_date", 0) == 0
    assert fact["created_date"].notna().sum() == int(parsed.notna().sum())
    assert list(fact["created_date"]) == list(parsed)


# --------------------------------------------------------------------------- #
# AV36 / EOS identification
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("value,expected", [
    ("AV36/AV36P/AV52 - EOS", True),
    ("AV36/AV36P/AV52 – EOS", True),       # en dash, as it appears in the export
    ("AVS36 - EGS", True),
    ("AV52 EOS Migration", True),
    ("AV36P", True),
    ("End of Support Refresh", True),
    ("Onprem to AVS", False),
    ("SQL Server MI Migration (From AVS)", False),
    ("Geospatial workload", False),        # "eos" inside a word is not a marker
])
def test_is_av36_eos_path(value, expected):
    assert cleaning.is_av36_eos_path(value) is expected


def test_eos_marker_found_on_factory_offering(raw):
    """The marker often lives on the offering, not the migration path."""
    mp = mapping.resolve_mapping(list(raw.columns))
    df = raw.copy()
    df[mp["migration_path"]] = "Onprem to AVS"
    df[mp["factory_offering"]] = "AV36/AV36P/AV52 - EOS"
    fact, _ = cleaning.build_fact_frame(df, mp)
    assert fact["is_av36_eos"].all()


# --------------------------------------------------------------------------- #
# Fiscal-year presets and chart drill-down matching
# --------------------------------------------------------------------------- #
def test_fiscal_year_presets_span_the_whole_year():
    as_of = pd.Timestamp("2027-07-01")
    start, end = metrics.date_preset_range(as_of, "This FY", 7)
    assert (start.date().isoformat(), end.date().isoformat()) == ("2027-07-01", "2028-06-30")
    start, end = metrics.date_preset_range(as_of, "Last FY", 7)
    assert (start.date().isoformat(), end.date().isoformat()) == ("2026-07-01", "2027-06-30")
    # Mid-year the window still covers the full fiscal year, not year-to-date.
    start, end = metrics.date_preset_range(pd.Timestamp("2027-12-15"), "This FY", 7)
    assert (start.date().isoformat(), end.date().isoformat()) == ("2027-07-01", "2028-06-30")


def test_drilldown_matches_plotly_month_labels():
    """Plotly can return a month as a full date; both forms must select the month."""
    from app.ui import drilldown
    assert drilldown.normalize_bucket("2026-06") == "2026-06"
    assert drilldown.normalize_bucket("2026-06-01") == "2026-06"
    assert drilldown.normalize_bucket(" 2026/06/15 ") == "2026-06"
    assert drilldown.normalize_bucket("Executing Migration") == "Executing Migration"
    assert drilldown.normalize_bucket(None) == ""


# --------------------------------------------------------------------------- #
# PDF export: sections, cover text and the reporting window
# --------------------------------------------------------------------------- #
def _ctx_for_export():
    from app import state
    from app.config import SAMPLE_DATA
    return state.build_context(SAMPLE_DATA.name, SAMPLE_DATA.read_bytes(), is_sample=True)


def _anchors(story) -> list[str]:
    from app.core import pdf_kit as kit
    return [f.key for f in story if isinstance(f, kit.Anchor)]


def _walk(node, seen=None):
    """Every Paragraph in a story, including those nested in tables/KeepTogether."""
    from reportlab.platypus import KeepTogether, Paragraph, Table
    out = []
    if isinstance(node, (list, tuple)):
        for item in node:
            out += _walk(item)
    elif isinstance(node, Paragraph):
        out.append(node)
    elif isinstance(node, KeepTogether):
        out += _walk(node._content)
    elif isinstance(node, Table):
        out += _walk(node._cellvalues)
    return out


def _hrefs(story) -> set[str]:
    """Destinations every internal link in the story points at."""
    import re
    return {m for p in _walk(story)
            for m in re.findall(r'href="#([^"]+)"', p.text)}


def _text(story) -> str:
    return " ".join(p.getPlainText() for p in _walk(story))


def test_report_builds_a_readable_pdf():
    from app.core import exporter
    ctx = _ctx_for_export()
    pdf = exporter.build_report(ctx, "", "All data",
                                title="Quarterly Review", subtitle="EOS programme",
                                period_label="01 Jul 2026 → 30 Jun 2027")
    assert pdf[:4] == b"%PDF"
    assert len(pdf) > 5000
    # Real navigation, not styled text: link annotations and a bookmark outline.
    assert b"/Link" in pdf and b"/Outlines" in pdf


def test_report_carries_the_three_primary_reports():
    from app.core import exporter
    ctx = _ctx_for_export()
    story = exporter.build_story(ctx)
    text = _text(story)
    for spec in exporter.REPORTS:
        assert f"rpt_{spec.key}" in _anchors(story), spec.key
        assert spec.title in text, spec.title
    assert "AVS Migrations" in text
    assert "EOS Migrations" in text
    assert "AVS to Azure Native" in text


def test_eos_report_consolidates_both_generations():
    """EOS Migrations must carry EOS (All) plus Gen-1 and Gen-2, not just the total."""
    from app.core import exporter, segments
    ctx = _ctx_for_export()
    text = _text(exporter.build_story(ctx, reports=["eos"]))
    assert "Generation breakdown" in text
    for category in (segments.CAT_EOS_GEN1, segments.CAT_EOS_GEN2):
        assert segments.CATEGORY_LABELS[category] in text, category


def test_every_report_links_to_its_drilldown_and_back():
    from app.core import exporter
    ctx = _ctx_for_export()
    story = exporter.build_story(ctx)
    anchors, links = set(_anchors(story)), _hrefs(story)
    for spec in exporter.REPORTS:
        assert f"rpt_{spec.key}" in anchors and f"dd_{spec.key}" in anchors
        assert f"dd_{spec.key}" in links, f"no drill-down link for {spec.key}"
        assert f"rpt_{spec.key}" in links, f"no back link for {spec.key}"
    assert "toc" in anchors and "toc" in links
    # Nothing may point at a destination the document does not define.
    assert links <= anchors, links - anchors


def test_dropping_the_drilldown_drops_its_links_too():
    from app.core import exporter
    ctx = _ctx_for_export()
    story = exporter.build_story(ctx, drilldown=False)
    anchors, links = set(_anchors(story)), _hrefs(story)
    assert not any(a.startswith("dd_") for a in anchors)
    assert links <= anchors, links - anchors


def test_selecting_one_report_excludes_the_others():
    from app.core import exporter
    ctx = _ctx_for_export()
    story = exporter.build_story(ctx, reports=["native"])
    anchors = _anchors(story)
    assert "rpt_native" in anchors
    assert "rpt_avs" not in anchors and "rpt_eos" not in anchors


def test_appendix_section_names_each_consistency_check():
    from app.core import exporter
    ctx = _ctx_for_export()
    text = _text(exporter.build_story(ctx, reports=[], appendices=["inconsistency"]))
    assert "Data inconsistency review" in text
    assert "no EOS migration path" in text and "no generation tag" in text


def test_report_figures_match_the_dashboard_calculation_layer():
    """The PDF must not recompute: its tiles are kpi.py's numbers, verbatim."""
    from app.core import exporter, kpi, segments
    ctx = _ctx_for_export()
    text = _text(exporter.build_story(ctx, reports=["avs"], drilldown=False))
    pop = segments.population(ctx.fact, segments.CAT_ALL_AVS)
    waves = kpi.wave_index(pop)
    expected = kpi.new_engagements(pop, None, None, firsts=waves.first).value
    on_track = kpi.on_track_accounts(pop, lasts=waves.last).value
    upper = text.upper()
    assert "NEW ENGAGEMENTS" in upper and "ON-TRACK ACCOUNTS" in upper
    assert f"{int(expected):,}" in text
    assert f"{int(on_track):,}" in text


def test_report_ignores_the_counting_mode_toggle():
    """The dashboards deduplicate through kpi.py whatever the sidebar toggle says,
    so the PDF must too — otherwise the same metric reads differently in the two
    places purely because of a radio button."""
    from app.core import analytics, exporter
    ctx = _ctx_for_export()
    rendered = {}
    for mode in ("customer", "fact"):
        analytics.use_table(mode)
        rendered[mode] = _text(exporter.build_story(ctx, reports=["avs"],
                                                    drilldown=False))
    analytics.use_table("fact")
    assert rendered["customer"] == rendered["fact"]


def test_report_survives_a_filter_that_selects_nothing():
    from app.core import exporter
    ctx = _ctx_for_export()
    where = "WHERE \"region_geo\" = 'Nowhere'"
    story = exporter.build_story(ctx, where)
    assert "No nominations fall into this report" in _text(story)
    pdf = exporter.build_report(ctx, where)
    assert pdf[:4] == b"%PDF"


def test_drilldown_truncates_large_account_sets_with_a_note():
    from app.core import exporter
    ctx = _ctx_for_export()
    text = _text(exporter.build_story(ctx, reports=["native"], max_drilldown_rows=1))
    assert "Showing the 1 largest" in text
    assert "CSV" in text
