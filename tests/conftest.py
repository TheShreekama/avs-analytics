"""Shared test setup.

``analytics`` keeps a module-level *current table* so a report can set the
counting grain once and every helper follows it.  That is per-script-run state in
Streamlit, but in a test session it survives from one test to the next: a test
that renders a page in customer mode would otherwise leave later tests querying a
``customer`` table their connection never registered.  Reset it around each test
so suites pass in any order.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core import analytics  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_current_table():
    analytics.use_table("fact")
    yield
    analytics.use_table("fact")
