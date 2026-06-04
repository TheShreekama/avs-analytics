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

page = os.environ.get("AVS_PAGE", "overview")
mod = importlib.import_module(f"app.views.{page}")
mod.render()
