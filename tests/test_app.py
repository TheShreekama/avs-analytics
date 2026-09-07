"""Smoke tests: render every report page under Streamlit's AppTest runtime.

Catches render-time errors (bad columns, malformed SQL, chart kwargs) across all
pages, in both counting modes, with the date filter widened to "All time" so the
populated code paths actually execute.

Run with:  python -m pytest tests/test_app.py -v
"""
import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from streamlit.testing.v1 import AppTest  # noqa: E402

_HARNESS = os.path.join(os.path.dirname(__file__), "_page_harness.py")
_HOME = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Home.py")

PAGES = [
    "overview",
    "insights_page", "methodology", "reports", "data_upload", "column_mapping",
    "data_inconsistency",
    # Status Report (one module, one entry point per migration category), in the
    # order the navigation lists them.
    "category_dashboard.all_avs",
    "category_dashboard.eos_all",
    "category_dashboard.eos_gen1", "category_dashboard.eos_gen2",
    "category_dashboard.avs_native",
    # Trend Analysis (one module, one entry point per measure).
    "trend_analysis.nominations", "trend_analysis.acr", "trend_analysis.nodes",
    "trend_analysis.cores", "trend_analysis.completed",
]

#: Every Trend Analysis page, as the harness names it.
TREND_PAGES = [p for p in PAGES if p.startswith("trend_analysis")]


def _render(page: str, mode: str) -> AppTest:
    os.environ.pop("AVS_AS_OF", None)
    os.environ["AVS_PAGE"] = page
    at = AppTest.from_file(_HARNESS, default_timeout=60)
    at.session_state["count_mode"] = mode
    at.run()
    # Widen every date preset to "All time" so the populated code paths actually
    # execute.  Reports carry their own period selector on the page ("<date field>
    # — reporting period"); the sidebar carries the global "Date range" they
    # default to, so both have to be widened.
    changed = False
    for sb in at.selectbox:
        label = (sb.label or "").lower()
        if label.endswith("range") or "reporting period" in label:
            if "All time" in list(sb.options):
                sb.set_value("All time")
                changed = True
    if changed:
        at.run()
    return at


def _sample_as_of() -> str:
    """Latest activity date in the bundled sample, as the sidebar would be set."""
    from app.config import SAMPLE_DATA
    from app.core import cleaning, loader, mapping
    raw = loader.read_raw_path(SAMPLE_DATA)
    fact, _ = cleaning.build_fact_frame(raw, mapping.resolve_mapping(list(raw.columns)))
    latest = max(fact[c].max() for c in ("approval_date", "created_date")
                 if fact[c].notna().any())
    return str(latest.date())


def _render_default(page: str, mode: str) -> AppTest:
    """Render a page with the *default* filter state (no widening).

    The as-of date is pinned to the sample's own activity, so this asserts the
    default *preset* shows data rather than asserting today's calendar overlaps
    a fixed sample file.
    """
    os.environ["AVS_AS_OF"] = _sample_as_of()
    os.environ["AVS_PAGE"] = page
    at = AppTest.from_file(_HARNESS, default_timeout=60)
    at.session_state["count_mode"] = mode
    at.run()
    return at


@pytest.mark.parametrize("page", PAGES)
@pytest.mark.parametrize("mode", ["Customer (deduplicated)", "Nomination (wave-level)"])
def test_page_renders_without_error(page, mode):
    at = _render(page, mode)
    assert not at.exception, f"{page} [{mode}] raised: {at.exception}"


# Regression: the default date preset used to be a one-week window, which left
# almost every page showing "No records match the current filters" on first open.
# Category dashboards and Trend Analysis pick their population by migration
# category rather than through the sidebar filters, so they render no "in view"
# summary for this test to read.
_REPORT_PAGES = [p for p in PAGES
                 if p not in ("methodology", "data_upload", "column_mapping",
                              "data_inconsistency")
                 and not p.startswith(("category_dashboard", "trend_analysis"))]


@pytest.mark.parametrize("page", _REPORT_PAGES)
@pytest.mark.parametrize("mode", ["Customer (deduplicated)", "Nomination (wave-level)"])
def test_page_has_records_with_default_filters(page, mode):
    at = _render_default(page, mode)
    assert not at.exception, f"{page} [{mode}] raised: {at.exception}"
    in_view = [m.value for m in at.sidebar.caption if "in view" in m.value]
    assert in_view, f"{page} [{mode}] rendered no filter summary"
    assert not any(c.startswith("**0** of") for c in in_view), \
        f"{page} [{mode}] is empty with default filters: {in_view}"


def test_full_app_boots_with_navigation():
    """Home.py wires every page, the sidebar and the global reporting period."""
    at = AppTest.from_file(_HOME, default_timeout=120)
    at.run()
    assert not at.exception, f"app failed to boot: {at.exception}"
    labels = [s.label for s in at.sidebar.selectbox]
    assert "Date range" in labels, f"global reporting period missing: {labels}"


def test_build_stamp_identifies_the_running_source():
    """The sidebar stamp must change when a source file changes."""
    from app import version
    built, fingerprint = version.build_stamp()
    assert len(fingerprint) == 6
    assert built != "unknown"
    assert version.version_line().startswith("v")


# Categories the bundled sample actually populates (an empty category returns
# early, before the sections that carry the explanations).
@pytest.mark.parametrize("page", ["category_dashboard.all_avs",
                                  "category_dashboard.avs_native"])
def test_titles_carry_an_explanation(page):
    """Every dashboard title offers an ⓘ explaining how its number is built."""
    at = _render_default(page, "Customer (deduplicated)")
    assert not at.exception, f"{page} raised: {at.exception}"
    marked = [m.value for m in at.markdown if "avs-info" in m.value]
    assert len(marked) >= 5, f"{page} has too few explained titles: {len(marked)}"
    assert any('title="' in m for m in marked)


@pytest.mark.parametrize("page", ["overview", "insights_page", "reports",
                                  "data_inconsistency"])
def test_every_report_offers_a_reporting_period(page):
    """The date range is chosen on the page, not hidden in the sidebar."""
    at = _render_default(page, "Customer (deduplicated)")
    assert not at.exception, f"{page} raised: {at.exception}"
    labels = [s.label for s in at.selectbox]
    assert any("reporting period" in (label or "").lower() for label in labels), \
        f"{page} has no in-page reporting period: {labels}"
    # ...and no page hides a second date control in the sidebar.
    assert not [s for s in at.sidebar.selectbox if (s.label or "").endswith("range")
                and s.label != "Date range"]


# The Status Report pages must let a reader get from any chart to its records.
_STATUS_REPORTS = ["category_dashboard.all_avs", "category_dashboard.avs_native"]


@pytest.mark.parametrize("page", _STATUS_REPORTS)
def test_status_reports_expose_their_underlying_data(page):
    """Every Status Report offers the records behind its charts, exportable."""
    at = _render(page, "Customer (deduplicated)")
    assert not at.exception, f"{page} raised: {at.exception}"
    # Each chart (or pair of charts) carries a panel holding the rows it was drawn
    # from.  Panels are titled "Underlying …" and every one exports to CSV.
    panels = [e.label for e in at.expander if "nderlying" in (e.label or "")]
    assert len(panels) >= 2, \
        f"{page} has too few underlying-data panels: {[e.label for e in at.expander]}"


def test_sidebar_no_longer_duplicates_the_inconsistency_report():
    """Data Inconsistency lives on its own page; the sidebar must not repeat it."""
    at = AppTest.from_file(_HOME, default_timeout=120)
    at.run()
    assert not at.exception, f"app failed to boot: {at.exception}"
    headings = " ".join(m.value for m in at.sidebar.markdown)
    assert "Data consistency" not in headings, \
        "the sidebar still renders the inconsistency panel"
    assert not [e for e in at.sidebar.expander if "no EOS path" in (e.label or "")]


def test_navigation_drops_the_unclassified_category_page():
    """EOS accounts with no generation tag are reported, not given a page."""
    from app.core import segments
    assert segments.CAT_EOS_UNCLASSIFIED not in segments.CATEGORY_LABELS
    assert not hasattr(__import__("app.views.category_dashboard", fromlist=["x"]),
                       "eos_unclassified")


def _with_period(page: str, preset: str) -> AppTest:
    """Render a category dashboard with its in-page reporting period set."""
    os.environ["AVS_AS_OF"] = _sample_as_of()
    os.environ["AVS_PAGE"] = page
    at = AppTest.from_file(_HARNESS, default_timeout=60)
    at.session_state["count_mode"] = "Customer (deduplicated)"
    at.run()
    for sb in at.selectbox:
        if "reporting period" in (sb.label or "").lower() and preset in list(sb.options):
            sb.set_value(preset)
    at.run()
    return at


def _tile_panels(at: AppTest) -> list[str]:
    return [e.label for e in at.expander if "Records behind these tiles" in (e.label or "")]


def test_this_fy_shows_one_summary_row():
    at = _with_period("category_dashboard.all_avs", "This FY")
    assert not at.exception, f"raised: {at.exception}"
    assert len(_tile_panels(at)) == 1, _tile_panels(at)


@pytest.mark.parametrize("preset", ["This month", "Last month", "This quarter", "All time"])
def test_other_periods_add_a_this_fy_row_above(preset):
    """Any period but This FY gets the fiscal year it sits in for context."""
    at = _with_period("category_dashboard.all_avs", preset)
    assert not at.exception, f"{preset} raised: {at.exception}"
    panels = _tile_panels(at)
    assert len(panels) == 2, f"{preset} rendered {panels}"
    # This FY first, then the selected period — each with its own records.
    assert "This FY" in panels[0]
    assert preset in panels[1]


def test_all_time_trends_split_by_fiscal_year():
    """The chart draws a line per FY and the table beside it lays them side by
    side, with a Total row — always, since the range is fixed at all time."""
    at = _render("trend_analysis.nominations", "Customer (deduplicated)")
    assert not at.exception, f"raised: {at.exception}"
    grid = at.dataframe[0].value
    assert list(grid.columns)[0] == "Month"
    years = [c for c in grid.columns if str(c).startswith("FY")]
    assert years, list(grid.columns)
    assert grid["Month"].iloc[-1] == "Total"


def test_sections_state_the_period_they_are_measured_over():
    at = _with_period("category_dashboard.all_avs", "This month")
    assert not at.exception, f"raised: {at.exception}"
    pills = [m.value for m in at.markdown if 'class="avs-period"' in m.value]
    assert pills, "no section states its reporting period"
    assert any("This month" in p for p in pills)
    # The pipeline is a snapshot and says so, rather than inheriting the period.
    assert any("not filtered by the reporting period" in p for p in pills), pills


def _sections(at: AppTest) -> list[str]:
    import re
    return [re.sub(r"<[^>]+>", "", m.value).replace("ⓘ", "")
            for m in at.markdown if 'class="avs-section"' in m.value]


@pytest.mark.parametrize("page", ["category_dashboard.eos_all",
                                  "category_dashboard.all_avs",
                                  "category_dashboard.avs_native"])
def test_broad_categories_carry_a_regional_breakdown(page):
    at = _render(page, "Customer (deduplicated)")
    assert not at.exception, f"{page} raised: {at.exception}"
    assert "Regional breakdown" in _sections(at), _sections(at)


def test_offering_and_target_lives_only_on_the_avs_native_page():
    """Exactly one page owns that cut of the data."""
    for page in ("category_dashboard.avs_native", "category_dashboard.all_avs"):
        sections = _sections(_render(page, "Customer (deduplicated)"))
        owns = page.endswith("avs_native")
        assert ("By offering & target" in sections) is owns, (page, sections)


def test_operational_status_is_gone_from_the_ui():
    """It was a delivery-health taxonomy easily mistaken for being EOS-specific;
    removed as its own report/column/filter. The engine still derives it
    internally (Risk, closure detection), just never displays it as a page,
    section, filter or table column any more."""
    assert not hasattr(
        __import__("app.views", fromlist=["eos_status"]), "eos_status")
    for page in ("overview", "insights_page", "reports",
                 "category_dashboard.avs_native", "category_dashboard.all_avs"):
        at = _render(page, "Customer (deduplicated)")
        assert not at.exception, f"{page} raised: {at.exception}"
        assert "Operational status" not in _sections(at), (page, _sections(at))
        assert "Operational Status" not in [s.label for s in at.selectbox], page


def test_the_generation_pages_do_not_repeat_the_regional_breakdown():
    """Gen-1/Gen-2 are subsets of EOS Migration (All), which already carries it."""
    at = _render("category_dashboard.eos_gen1", "Customer (deduplicated)")
    assert not at.exception, f"raised: {at.exception}"
    assert "Regional breakdown" not in _sections(at)


def test_regional_breakdown_ignores_the_counting_mode_toggle():
    """The regional cut counts accounts at their latest wave, never waves —
    whichever way the sidebar's Counting mode toggle is set."""
    tables = {}
    for mode in ("Customer (deduplicated)", "Nomination (wave-level)"):
        at = _render("category_dashboard.all_avs", mode)
        assert not at.exception, f"{mode} raised: {at.exception}"
        target = next((e for e in at.expander
                       if "stage × WW Region" in (e.label or "")), None)
        assert target is not None, f"{mode}: no regional-breakdown panel found"
        assert target.dataframe, f"{mode}: regional-breakdown panel has no table"
        tables[mode] = target.dataframe[0].value
    left, right = tables.values()
    pd.testing.assert_frame_equal(
        left.sort_values(list(left.columns)).reset_index(drop=True),
        right.sort_values(list(right.columns)).reset_index(drop=True))


def test_reports_page_offers_each_report_and_generates_a_pdf():
    """End to end through the page: tick the reports, press Generate, get a PDF."""
    from app.core import exporter
    at = _render("reports", "Customer (deduplicated)")
    assert not at.exception, f"raised: {at.exception}"
    labels = [c.label for c in at.checkbox]
    for spec in exporter.REPORTS:
        assert spec.title in labels, spec.title
    assert "Include drill-down sections" in labels

    generate = next((b for b in at.button if "Generate PDF" in (b.label or "")), None)
    assert generate is not None, "no Generate button on the Reports page"
    at = generate.click().run(timeout=300)
    assert not at.exception, f"generating raised: {at.exception}"
    pdf = at.session_state["_rep_pdf"]
    assert pdf[:4] == b"%PDF"


# --------------------------------------------------------------------------- #
# Trend Analysis: one page per measure, every category on it
# --------------------------------------------------------------------------- #
_EXPECTED_TREND_CATEGORIES = {
    "trend_analysis.nominations": ["All AVS Migrations", "EOS Migration",
                                   "EOS Migration — Gen-1", "EOS Migration — Gen-2",
                                   "AVS → Azure Native"],
    "trend_analysis.acr": ["All AVS Migrations", "EOS Migration",
                           "EOS Migration — Gen-1", "EOS Migration — Gen-2",
                           "AVS → Azure Native"],
    "trend_analysis.nodes": ["All AVS Migrations", "EOS Migration",
                             "EOS Migration — Gen-1", "EOS Migration — Gen-2"],
    "trend_analysis.cores": ["AVS → Azure Native"],
    "trend_analysis.completed": ["All AVS Migrations", "EOS Migration",
                                 "EOS Migration — Gen-1", "EOS Migration — Gen-2",
                                 "AVS → Azure Native"],
}


@pytest.mark.parametrize("page", TREND_PAGES)
def test_each_trend_page_covers_exactly_its_categories(page):
    """Nodes Deployed stops at the AVS motions; Cores Migrated is the (From AVS)
    one under the noun that fits it. Every other measure covers all five."""
    at = _render(page, "Customer (deduplicated)")
    assert not at.exception, f"{page} raised: {at.exception}"
    assert _sections(at) == _EXPECTED_TREND_CATEGORIES[page]


def test_nodes_and_cores_split_the_same_measure_by_motion():
    """Both read Total Cores; only the noun and the population differ."""
    from app.views import trend_analysis as ta
    nodes = next(m for m in ta.MEASURES if m.key == "nodes")
    cores = next(m for m in ta.MEASURES if m.key == "cores")
    assert nodes.display_col == "Nodes" and cores.display_col == "Cores"
    assert nodes.unit_col == cores.unit_col == "total_cores"
    from app.core import segments
    assert segments.CAT_AVS_NATIVE not in nodes.categories
    assert cores.categories == (segments.CAT_AVS_NATIVE,)


def test_trend_pages_reuse_the_dashboard_calculation_layer():
    """Moving the reports must not have changed a single number: each measure is
    the kpi.py call the category dashboards made, on the same population."""
    from app.core import kpi, segments
    from app.views import trend_analysis as ta
    from app.config import SAMPLE_DATA
    from app import state
    ctx = state.build_context(SAMPLE_DATA.name, SAMPLE_DATA.read_bytes(), is_sample=True)
    pop = segments.population(ctx.fact, segments.CAT_ALL_AVS)
    waves = kpi.wave_index(pop)
    expected = {
        "nominations": kpi.monthly_unique_tpids(pop, "approval_date", None, None,
                                                firsts=waves.first)[0],
        "acr": kpi.monthly_acr_claimed(pop, None, None)[0],
        "nodes": kpi.monthly_hosts(pop, None, None)[0],
        "completed": kpi.monthly_migrations_completed(pop, None, None,
                                                      lasts=waves.last)[0],
    }
    for key, want in expected.items():
        measure = next(m for m in ta.MEASURES if m.key == key)
        got, _ = measure.series(pop, waves, None, None, "approval_date")
        pd.testing.assert_frame_equal(got, want)


def test_trends_are_gone_from_the_migration_analytics_dashboards():
    """The reports moved to Trend Analysis; they must not remain in both places."""
    for page in ("category_dashboard.all_avs", "category_dashboard.eos_all",
                 "category_dashboard.avs_native"):
        at = _render(page, "Customer (deduplicated)")
        assert not at.exception, f"{page} raised: {at.exception}"
        sections = _sections(at)
        assert not any("Trends" in s for s in sections), (page, sections)
        assert "Trend basis" not in [r.label for r in at.radio], page


def test_the_old_trend_pages_are_gone():
    """Deleted outright, not renamed or hidden behind the navigation."""
    import importlib
    for name in ("nomination_trends", "approved_trends", "avs_to_azure"):
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module(f"app.views.{name}")


@pytest.mark.parametrize("page", TREND_PAGES)
def test_trend_pages_are_fixed_at_all_time(page):
    """The range is the whole (FY-floored) dataset, so there is no period picker
    to narrow it — that is the point of these reports."""
    at = _render(page, "Customer (deduplicated)")
    assert not at.exception, f"{page} raised: {at.exception}"
    assert not [s for s in at.selectbox
                if "reporting period" in (s.label or "").lower()], page
    banners = " ".join(m.value for m in at.markdown)
    assert "All time (FY25 onwards)" in banners, page


@pytest.mark.parametrize("page", TREND_PAGES)
def test_trend_records_are_split_one_table_per_fiscal_year(page):
    """Never one combined table: the fiscal year is the thing being compared."""
    at = _render(page, "Customer (deduplicated)")
    assert not at.exception, f"{page} raised: {at.exception}"
    panels = [e.label for e in at.expander if "Underlying" in (e.label or "")]
    assert panels, page
    # Every panel names exactly one fiscal year.
    import re
    for label in panels:
        assert len(re.findall(r"FY\d{2}", label)) == 1, label


# --------------------------------------------------------------------------- #
# Navigation shape
# --------------------------------------------------------------------------- #
def test_navigation_sections_and_order():
    """Status Report replaces both the old Migration Analytics heading and the
    old Status Reports section; Reports & Export sits under Data."""
    at = AppTest.from_file(_HOME, default_timeout=180).run()
    assert not at.exception, f"app failed to boot: {at.exception}"
    import re
    source = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "app", "main.py")).read()
    sections = re.findall(r'^\s{8}"([^"]+)": \[', source, re.M)
    assert "Status Report" in sections
    assert "Status Reports" not in sections and "Migration Analytics" not in sections
    # Reports & Export moved out of Executive and into Data.
    data_block = source.split('"Data": [')[1].split("],")[0]
    assert "reports.render" in data_block
    exec_block = source.split('"Executive": [')[1].split("],")[0]
    assert "reports.render" not in exec_block


def test_status_report_lists_categories_broadest_first():
    import re
    source = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "app", "main.py")).read()
    block = source.split('"Status Report": [')[1].split("],")[0]
    assert re.findall(r"category_dashboard\.(\w+)", block) == [
        "all_avs", "eos_all", "eos_gen1", "eos_gen2", "avs_native"]


def test_the_old_status_report_pages_are_gone():
    import importlib
    for name in ("accounts_status", "approved", "closed", "avs_native_status"):
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module(f"app.views.{name}")


# --------------------------------------------------------------------------- #
# Regional breakdown: no Accounts by region, clickable stacked bar
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("page", ["category_dashboard.all_avs",
                                  "category_dashboard.eos_all",
                                  "category_dashboard.avs_native"])
def test_accounts_by_region_is_gone(page):
    at = _render(page, "Customer (deduplicated)")
    assert not at.exception, f"{page} raised: {at.exception}"
    text = " ".join(m.value for m in at.markdown)
    assert "Accounts by region" not in text, page


def test_stacked_bar_segments_identify_a_region_and_a_stage():
    """A clicked segment names both halves, and the records carry the same key,
    so the drill-down can filter to exactly that pair."""
    import pandas as pd
    from app.ui import charts, drilldown
    from app.views.category_dashboard import _REGION_STAGE_JOIN
    pivot = pd.crosstab(
        pd.Series(["Completed", "Executing Migration", "Executing Migration"]),
        pd.Series(["Americas", "Americas", "EMEA"]))
    fig = charts.stacked_bar(pivot)
    labels = drilldown._trace_labels(fig)
    regions = [str(c) for c in pivot.columns]
    for curve, region in enumerate(regions):
        for idx, stage in enumerate(pivot.index):
            stage_label = drilldown._label_at(labels, {"curve_number": curve,
                                                       "point_index": idx})
            assert f"{region}{_REGION_STAGE_JOIN}{stage_label}" == \
                f"{region}{_REGION_STAGE_JOIN}{stage}"


def test_a_pie_slice_resolves_to_its_category():
    """A slice click can arrive carrying only its position; it must still name
    the state so the underlying accounts can be filtered to it."""
    import pandas as pd
    from app.ui import charts, drilldown
    states = pd.DataFrame({"category": ["On-Track", "Completed"], "count": [2, 1]})
    labels = drilldown._trace_labels(charts.donut(states, "category", "count"))
    assert [drilldown._label_at(labels, {"curve_number": 0, "point_index": i})
            for i in (0, 1)] == ["On-Track", "Completed"]


def test_selection_filters_the_records_it_names():
    """The end of the chain: a selected bucket narrows the drill-down rows."""
    import pandas as pd
    from app.ui import drilldown
    rows = pd.DataFrame({"bucket": ["Americas · Completed", "EMEA · Completed",
                                    "Americas · Executing Migration"],
                         "tpid": ["1", "2", "3"]})
    keys = rows["bucket"].map(drilldown.normalize_bucket)
    picked = [drilldown.normalize_bucket("Americas · Completed")]
    assert list(rows[keys.isin(picked)]["tpid"]) == ["1"]
