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
    "overview", "accounts_status", "approved", "closed",
    "nomination_trends", "approved_trends", "avs_to_azure", "avs_native_status",
    "insights_page", "methodology", "reports", "data_upload", "column_mapping",
    "data_inconsistency",
    # Category dashboards (one module, one entry point per migration category).
    "category_dashboard.eos_all",
    "category_dashboard.eos_gen1", "category_dashboard.eos_gen2",
    "category_dashboard.all_avs",
    "category_dashboard.avs_native",
]


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
_REPORT_PAGES = [p for p in PAGES
                 if p not in ("methodology", "data_upload", "column_mapping",
                              "data_inconsistency")
                 and not p.startswith("category_dashboard")]


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


@pytest.mark.parametrize("page", ["overview", "closed", "insights_page", "reports",
                                  "data_inconsistency", "approved_trends"])
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


# Status Reports must let a reader get from any chart to the records behind it.
_STATUS_REPORTS = ["accounts_status", "approved", "closed", "avs_native_status"]


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
    assert all("0 rows" not in label for label in panels), \
        f"{page} has an empty underlying-data panel: {panels}"


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
    """All time draws a line per FY, with the years side by side underneath."""
    at = _with_period("category_dashboard.all_avs", "All time")
    assert not at.exception, f"raised: {at.exception}"
    grids = [e.label for e in at.expander if "fiscal years side by side" in (e.label or "")]
    assert grids, [e.label for e in at.expander]
    # ...and a bounded period does not.
    month = _with_period("category_dashboard.all_avs", "This month")
    assert not [e for e in month.expander if "fiscal years side by side" in (e.label or "")]


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


def test_offering_and_target_lives_only_on_the_category_page():
    """It moved off the status report; exactly one page owns it now."""
    dashboard = _sections(_render("category_dashboard.avs_native",
                                  "Customer (deduplicated)"))
    assert "By offering & target" in dashboard, dashboard

    report = _sections(_render("avs_native_status", "Customer (deduplicated)"))
    assert "By offering & target" not in report, report


def test_operational_status_is_gone_from_the_ui():
    """It was a delivery-health taxonomy easily mistaken for being EOS-specific;
    removed as its own report/column/filter. The engine still derives it
    internally (Risk, closure detection), just never displays it as a page,
    section, filter or table column any more."""
    assert not hasattr(
        __import__("app.views", fromlist=["eos_status"]), "eos_status")
    for page in ("overview", "accounts_status", "closed", "avs_native_status",
                "avs_to_azure", "insights_page", "reports",
                "category_dashboard.avs_native"):
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
    """Accounts by Migration Status must never show wave counts here, whichever
    Counting mode the sidebar toggle is set to — it should always agree with
    the Migration Analytics dashboards' account-deduplicated regional cut."""
    tables = {}
    for mode in ("Customer (deduplicated)", "Nomination (wave-level)"):
        at = _render("accounts_status", mode)
        assert not at.exception, f"{mode} raised: {at.exception}"
        target = next((e for e in at.expander if "status × region" in (e.label or "")),
                      None)
        assert target is not None, f"{mode}: no regional-breakdown panel found"
        assert target.dataframe, f"{mode}: regional-breakdown panel has no table"
        tables[mode] = target.dataframe[0].value
    left, right = tables.values()
    pd.testing.assert_frame_equal(
        left.sort_values(list(left.columns)).reset_index(drop=True),
        right.sort_values(list(right.columns)).reset_index(drop=True))
