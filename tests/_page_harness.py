"""Test harness: render a single page under the Streamlit runtime.

Used by the AppTest-based smoke test (tests/test_app.py).  The page to render is
selected via the AVS_PAGE environment variable.
"""
import importlib
import os
import sys

import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

st.set_page_config(layout="wide")
from app.ui.theme import inject_css  # noqa: E402
from app import state  # noqa: E402

inject_css()
state.ensure_context()

# The as-of date now defaults to *today*, so a test working with the bundled
# sample (whose activity sits in an earlier fiscal year) pins it the way a user
# would with the sidebar's "Reporting as-of date" control.
as_of = os.environ.get("AVS_AS_OF")
if as_of and str(state.get_context().as_of.date()) != as_of:
    import pandas as pd
    state.reload_with(as_of=pd.Timestamp(as_of))

# "overview" renders app.views.overview.render(); "category_dashboard.eos_gen1"
# renders that module's named entry point (the category dashboards share a module).
page = os.environ.get("AVS_PAGE", "overview")
module, _, func = page.partition(".")
mod = importlib.import_module(f"app.views.{module}")
getattr(mod, func or "render")()
