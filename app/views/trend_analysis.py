"""Trend Analysis — one trend, one migration category, one page.

The section is organised by *what is being trended* rather than by report, so a
reader who wants "ACR claimed for Gen-2" goes straight to it:

    Trend Analysis
      Nomination Trends      All AVS · EOS (All) · EOS (Gen 1) · EOS (Gen 2) · AVS → Azure Native
      ACR Trend              (the same five)
      Nodes Deployed         All AVS · EOS (All) · EOS (Gen 1) · EOS (Gen 2)
      Cores Migrated         AVS → Azure Native
      Migrations Completed   (the same five)

Nothing here recomputes anything.  Every page selects its population with
``segments.population`` and draws it with :mod:`app.ui.trends` — the same
component the Migration Analytics category dashboards use for their
"Trends — month over month" section — so the number on a Trend Analysis page and
the number on the matching dashboard are produced by one piece of code.

"Nodes Deployed" and "Cores Migrated" are the same Total Cores measurement the
dashboards label "Hosts Migrated" / "Cores Migrated"; the AVS → Azure Native
motion moves cores to Azure-native services, the AVS categories deploy nodes.
Only the noun changes.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import streamlit as st

from app import state
from app.core import glossary, kpi, segments
from app.ui import components, trends
from app.ui.theme import page_header, section

#: Navigation group these pages sit under.
SECTION = "Trend Analysis"

ALL_TIME = "All time"

#: Nav title, URL slug and icon per migration category.  The icons match the
#: Migration Analytics dashboards, so a category is recognisable in both places.
_CATEGORY_NAV = {
    segments.CAT_ALL_AVS: ("All AVS Migrations", "all-avs", ":material/cloud:"),
    segments.CAT_EOS_ALL: ("EOS Migrations (All)", "eos-all", ":material/dns:"),
    segments.CAT_EOS_GEN1: ("EOS Migrations (Gen 1)", "eos-gen1", ":material/memory:"),
    segments.CAT_EOS_GEN2: ("EOS Migrations (Gen 2)", "eos-gen2",
                            ":material/developer_board:"),
    segments.CAT_AVS_NATIVE: ("AVS to Azure Native", "avs-native",
                              ":material/cloud_sync:"),
}

#: Onboarding-to-AVS categories, then the Azure-native motion after them.
_AVS_CATEGORIES = (segments.CAT_ALL_AVS, segments.CAT_EOS_ALL,
                   segments.CAT_EOS_GEN1, segments.CAT_EOS_GEN2)
_ALL_CATEGORIES = _AVS_CATEGORIES + (segments.CAT_AVS_NATIVE,)


@dataclass(frozen=True)
class TrendPage:
    """One page: a trend drawn for one migration category."""
    group: str
    category: str
    title: str                      #: nav title (the category)
    url_path: str
    icon: str
    entry: Callable[[], None]       #: the callable ``st.Page`` runs


@dataclass(frozen=True)
class TrendGroup:
    """One Trend Analysis report, offered for several migration categories."""
    key: str
    trend: str                      #: which trend in :mod:`app.ui.trends`
    title: str                      #: nav sub-section and page title
    description: str                #: the page's sub-title
    heading: str                    #: the heading over the chart
    categories: tuple[str, ...]
    column: str | None = None       #: renames the summary table's value column
    note: str | None = None         #: a clarifying caption, where the noun differs
    pages: list[TrendPage] = field(default_factory=list)


_NODES_NOTE = ("**Nodes Deployed** is the Total Cores summed over completed waves — "
               "the same measurement this category's Migration Analytics dashboard "
               "shows as *Hosts Migrated*.")
_CORES_NOTE = ("**Cores Migrated** is the Total Cores summed over completed waves — "
               "the AVS → Azure Native motion moves cores to Azure-native services "
               "rather than deploying AVS nodes.")

GROUPS: dict[str, TrendGroup] = {
    g.key: g for g in (
        TrendGroup(
            "nomination", trends.NOMINATIONS, "Nomination Trends",
            "Nominations month over month: unique customers (TPIDs) placed in the "
            "month of their Wave-1 date, with a running cumulative.",
            "Nomination count (unique TPIDs)", _ALL_CATEGORIES),
        TrendGroup(
            "acr", trends.ACR, "ACR Trend",
            "ACR claimed month over month: each wave's Total ACR placed in the "
            "month its Actual End Date falls in.",
            "ACR claimed", _ALL_CATEGORIES),
        TrendGroup(
            "nodes", trends.HOSTS, "Nodes Deployed",
            "Nodes deployed month over month: Total Cores over completed waves, "
            "by Actual End Date.",
            "Nodes Deployed (Total Cores)", _AVS_CATEGORIES,
            column="Nodes", note=_NODES_NOTE),
        TrendGroup(
            "cores", trends.HOSTS, "Cores Migrated",
            "Cores migrated to Azure-native services month over month: Total Cores "
            "over completed waves, by Actual End Date.",
            "Cores Migrated (Total Cores)", (segments.CAT_AVS_NATIVE,),
            column="Cores", note=_CORES_NOTE),
        TrendGroup(
            "completed", trends.COMPLETED, "Migrations Completed",
            "Completed migrations month over month: unique TPIDs whose latest wave "
            "is '7 - Completed', dated by that wave's Actual End Date.",
            "Migrations completed (unique TPIDs)", _ALL_CATEGORIES),
    )
}


# --------------------------------------------------------------------------- #
# The page
# --------------------------------------------------------------------------- #
def render(group_key: str, category: str) -> None:
    ctx = state.ensure_context()
    group = GROUPS[group_key]
    label, _slug, _icon = _CATEGORY_NAV[category]
    page_header(f"{group.title} — {label}", group.description,
                help=_page_help(group, category))
    components.data_quality_banner(ctx)

    fact = segments.population(ctx.fact, category)
    key = f"trend_{group_key}_{category}"

    # Reporting window: the global one unless this report overrides it.
    top = st.columns([2, 3])
    with top[0]:
        start, end, shown, preset = components.report_date_range(ctx, key)
    with top[1]:
        components.population_note(category, fact)

    if fact.empty:
        components.empty_state(
            f"No nominations fall into **{label}**. The **{label}** dashboard under "
            f"Migration Analytics explains what the file does contain.")
        return

    waves = kpi.wave_index(fact)
    by_fy = preset == ALL_TIME
    section(f"{group.title} — month over month", help=glossary.TRENDS, period=shown)
    if group.note:
        st.caption(group.note)
    trends.guidance(by_fy)

    # Only the nomination count has a choice of date; the rest are dated by the
    # Actual End Date they measure.
    date_col = "approval_date"
    if group.trend == trends.NOMINATIONS:
        date_col = trends.basis_selector(
            key, label="Trend basis",
            help="Which Wave-1 date places a TPID in a month.")

    result = trends.compute(group.trend, fact, waves, start, end, date_col=date_col)
    trends.render_trend(result, key=key, title=group.heading, display_col=group.column,
                        shown=shown, by_fy=by_fy)


def _page_help(group: TrendGroup, category: str) -> str:
    """The ⓘ on the page title: how the number is built, then who is in it."""
    return f"{trends.SPECS[group.trend].help}\n\n{glossary.CATEGORY_HELP[category]}"


# --------------------------------------------------------------------------- #
# Page entry points (st.Page needs a distinct callable per page)
# --------------------------------------------------------------------------- #
def _make_entry(group_key: str, category: str, name: str) -> Callable[[], None]:
    def entry() -> None:
        render(group_key, category)
    entry.__name__ = name
    entry.__qualname__ = name
    entry.__doc__ = (f"{SECTION} → {GROUPS[group_key].title} → "
                     f"{_CATEGORY_NAV[category][0]}.")
    return entry


for _group in GROUPS.values():
    for _category in _group.categories:
        _label, _slug, _icon = _CATEGORY_NAV[_category]
        _name = f"{_group.key}_{_slug.replace('-', '_')}"
        _entry = _make_entry(_group.key, _category, _name)
        globals()[_name] = _entry           # named, so tests can render one directly
        _group.pages.append(TrendPage(_group.key, _category, _label,
                                      f"trends-{_group.key}-{_slug}", _icon, _entry))
del _group, _category, _label, _slug, _icon, _name, _entry


def section_label(title: str) -> str:
    """The navigation header for one report.

    ``st.navigation`` is two levels deep, so the third level of the hierarchy
    (Trend Analysis → report → category) is folded into the section label: a
    muted "Trend Analysis" line above the report's own name.  Written on one
    line it is wider than the sidebar and truncates mid-word.
    """
    return f":gray[{SECTION}]  \n{title}"


def nav_pages() -> dict[str, list[st.Page]]:
    """The Trend Analysis navigation, as ``st.navigation`` sections."""
    return {section_label(group.title):
            [st.Page(page.entry, title=page.title, icon=page.icon,
                     url_path=page.url_path) for page in group.pages]
            for group in GROUPS.values()}


def all_pages() -> list[TrendPage]:
    """Every Trend Analysis page, in navigation order."""
    return [page for group in GROUPS.values() for page in group.pages]
