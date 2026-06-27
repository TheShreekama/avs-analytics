"""Central configuration: branding, colour palette, paths, and tunables.

Everything visual or behavioural that we might want to adjust in one place
lives here so the rest of the codebase stays declarative.
"""
from __future__ import annotations

import os
from pathlib import Path

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
APP_DIR = Path(__file__).resolve().parent
ROOT_DIR = APP_DIR.parent
SAMPLE_DATA = ROOT_DIR / "sample_data" / "avs_raw_data.csv"
ASSETS_DIR = APP_DIR / "assets"

# User-writable directory for saved column mappings / cached uploads.
# Kept next to the app so a portable (extracted ZIP) install stays self-contained.
USER_DATA_DIR = Path(os.environ.get("AVS_USER_DATA", ROOT_DIR / ".avs_data"))
MAPPINGS_FILE = USER_DATA_DIR / "column_mappings.json"

APP_NAME = "AVS Migration Analytics"
APP_TAGLINE = "Executive reporting for Azure VMware Solution migrations"
APP_VERSION = "1.0.0"

# --------------------------------------------------------------------------- #
# Colour palette  (Azure-inspired, executive / print friendly)
# --------------------------------------------------------------------------- #
PALETTE = {
    "primary": "#0F6CBD",      # Azure blue
    "primary_dark": "#0A4C86",
    "accent": "#50B0E8",
    "ink": "#1B1B1F",
    "muted": "#5C6470",
    "bg": "#F5F7FA",
    "card": "#FFFFFF",
    "border": "#E3E8EF",
    "good": "#107C41",         # green
    "warn": "#C77700",         # amber
    "bad": "#C4314B",          # red
    "neutral": "#8A8886",
}

# Ordered, semantic colour map for status-style categories.  Anything not in
# the map falls back to a categorical sequence.
STATUS_COLORS = {
    # operational / EOS taxonomy
    "Completed": "#107C41",
    "On Track": "#0F6CBD",
    "At Risk": "#C77700",
    "Delayed": "#D97706",
    "Blocked": "#C4314B",
    "Cancelled": "#8A8886",
    "Not Started": "#B0B8C4",
    "In Progress": "#50B0E8",
    "Started": "#7AC2F0",
    # nomination
    "Approved": "#107C41",
    "Pending": "#C77700",
    "Declined": "#C4314B",
    "On Hold": "#D97706",
}

# Plotly qualitative sequence for tracks / regions / paths.
CATEGORICAL_SEQUENCE = [
    "#0F6CBD", "#107C41", "#C77700", "#C4314B", "#7719AA",
    "#008272", "#5C2E91", "#CA5010", "#0078D4", "#498205",
    "#8764B8", "#E3008C", "#00B7C3", "#B146C2", "#FF8C00",
]

# EOS / operational status display order (used to order legends & axes).
EOS_STATUS_ORDER = ["On Track", "Completed", "At Risk", "Delayed", "Blocked", "Cancelled"]

# Migration-direction labels (derived from the migration path).
DIR_TO_AVS = "Onboard to AVS"
DIR_FROM_AVS = "AVS → Azure Native"
DIR_OTHER = "Other / Unclassified"

# --------------------------------------------------------------------------- #
# Reporting scope
# --------------------------------------------------------------------------- #
# The dashboard's primary focus is *AVS Migration Nominations* (onboarding to
# AVS).  Offerings whose migration path is "(From AVS)" — i.e. AVS → Azure
# Native — are quarantined to their own dedicated pages and never mixed into the
# primary status/trend reports.
SCOPE_PRIMARY = "primary"      # is_from_avs = FALSE  (AVS onboarding nominations)
SCOPE_FROM_AVS = "from_avs"    # is_from_avs = TRUE   (AVS → Azure Native)

# --------------------------------------------------------------------------- #
# Date-range presets (anchored on the reporting as-of date)
# --------------------------------------------------------------------------- #
# Microsoft fiscal year starts in July.
FY_START_MONTH = int(os.environ.get("AVS_FY_START_MONTH", "7"))

DATE_PRESETS = [
    "This week", "Last week", "This month", "Last month",
    "Last 3 months", "Last 6 months", "This FY", "All time", "Custom",
]
DEFAULT_DATE_PRESET = "Last week"

# Default network settings for the local server.
DEFAULT_PORT = int(os.environ.get("AVS_PORT", "8501"))


def ensure_user_dirs() -> None:
    """Create the user-data directory lazily (first write)."""
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
