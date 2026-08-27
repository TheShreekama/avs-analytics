"""Smoke tests: render every report page under Streamlit's AppTest runtime.

Catches render-time errors (bad columns, malformed SQL, chart kwargs) across all
pages, in both counting modes, with the date filter widened to "All time" so the
populated code paths actually execute.

Run with:  python -m pytest tests/test_app.py -v
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from streamlit.testing.v1 import AppTest  # noqa: E402

_HARNESS = os.path.join(os.path.dirname(__file__), "_page_harness.py")
_HOME = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Home.py")

PAGES = [
    "overview", "accounts_status", "approved", "closed", "eos_status",
    "nomination_trends", "approved_trends", "avs_to_azure", "avs_native_status",
    "insights_page", "methodology", "reports", "data_upload", "column_mapping",
    "data_inconsistency",
    # Category dashboards (one module, one entry point per migration category).
    "category_dashboard.eos_all",
    "category_dashboard.eos_gen1", "category_dashboard.eos_gen2",
    "category_dashboard.eos_unclassified", "category_dashboard.all_avs",
    "category_dashboard.avs_native",
]


def _render(page: str, mode: str) -> AppTest:
    os.environ.pop("AVS_AS_OF", None)
    os.environ["AVS_PAGE"] = page
    at = AppTest.from_file(_HARNESS, default_timeout=60)
    at.session_state["count_mode"] = mode
    at.run()
    # Widen any date-range preset to "All time" so charts/tables populate, then re-run.
    changed = False
    for sb in at.selectbox:
        if sb.label and sb.label.endswith("range"):
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
