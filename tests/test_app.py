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

PAGES = [
    "overview", "accounts_status", "approved", "closed", "eos_status",
    "nomination_trends", "approved_trends", "avs_to_azure", "avs_native_status",
    "insights_page", "methodology", "reports", "data_upload", "column_mapping",
]


def _render(page: str, mode: str) -> AppTest:
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


@pytest.mark.parametrize("page", PAGES)
@pytest.mark.parametrize("mode", ["Customer (deduplicated)", "Nomination (wave-level)"])
def test_page_renders_without_error(page, mode):
    at = _render(page, mode)
    assert not at.exception, f"{page} [{mode}] raised: {at.exception}"
