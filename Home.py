"""AVS Migration Analytics — Streamlit entry point.

Run locally with:  streamlit run Home.py
(the packaged launcher does this for you).

This file lives at the repository root so that:
  * the ``app`` package is importable, and
  * Streamlit does NOT auto-discover ``app/views/*`` as standalone pages
    (our navigation is defined explicitly in ``app/main.py``).
"""
import os
import sys

# Ensure the repo root (this file's directory) is importable regardless of CWD.
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.main import run  # noqa: E402

run()
