"""Static chart rendering for the PDF export — pure matplotlib, no browser.

The interactive dashboard uses Plotly (rendered as JavaScript in the browser),
but the PDF needs raster images.  We render those with matplotlib's headless
``Agg`` backend so the package never ships a bundled Chromium/`kaleido` binary —
which keeps the install friendly to strict corporate antivirus/EDR policies.

Every function takes the same small DataFrames the exporter already computes and
returns PNG bytes.  Styling mirrors the on-screen palette.
"""
from __future__ import annotations

import io

import matplotlib

matplotlib.use("Agg")  # headless: no display, no browser, no GUI toolkit

import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.ticker import MaxNLocator  # noqa: E402

from ..config import CATEGORICAL_SEQUENCE, PALETTE, STATUS_COLORS  # noqa: E402

_DPI = 150
plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 9,
    "axes.edgecolor": PALETTE["border"],
    "axes.linewidth": 0.8,
    "figure.facecolor": "white",
    "axes.facecolor": "white",
})


def _new(width_px: int, height_px: int):
    fig, ax = plt.subplots(figsize=(width_px / _DPI, height_px / _DPI), dpi=_DPI,
                           layout="constrained")
    return fig, ax


def _finish(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=_DPI, facecolor="white")
    plt.close(fig)
    return buf.getvalue()


def _colors_for(labels) -> list[str]:
    return [STATUS_COLORS.get(str(v), CATEGORICAL_SEQUENCE[i % len(CATEGORICAL_SEQUENCE)])
            for i, v in enumerate(labels)]


def _despine(ax, keep_left: bool = True) -> None:
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    if not keep_left:
        ax.spines["left"].set_visible(False)


def _title(ax, title: str | None) -> None:
    if title:
        ax.set_title(title, fontsize=11, color=PALETTE["ink"], loc="left", pad=8)


#: At most this many x tick labels: a three-year monthly series printed at 8pt
#: overlaps into an unreadable band long before then.
_MAX_TICKS = 14


def _category_ticks(ax, labels: list[str]) -> None:
    """Label every nth category so a long monthly axis stays readable."""
    step = -(-len(labels) // _MAX_TICKS) if labels else 1
    ticks = list(range(0, len(labels), max(step, 1)))
    ax.set_xticks(ticks, [labels[i] for i in ticks], rotation=25, ha="right",
                  fontsize=8)


# --------------------------------------------------------------------------- #
# Chart builders (mirror app/ui/charts.py signatures, return PNG bytes)
# --------------------------------------------------------------------------- #
def donut_png(df: pd.DataFrame, names: str, values: str, title: str | None = None,
              height_px: int = 330, width_px: int = 950) -> bytes:
    labels = [str(v) for v in df[names].tolist()]
    vals = [float(v) for v in df[values].tolist()]
    fig, ax = _new(width_px, height_px)
    wedges, _ = ax.pie(vals, colors=_colors_for(labels), startangle=90,
                       wedgeprops=dict(width=0.42, edgecolor="white", linewidth=1.5))
    total = int(sum(vals))
    ax.text(0, 0, f"{total:,}\ntotal", ha="center", va="center",
            fontsize=13, fontweight="bold", color=PALETTE["ink"])
    ax.legend(wedges, [f"{l}  ({int(v):,})" for l, v in zip(labels, vals)],
              loc="center left", bbox_to_anchor=(1.0, 0.5), frameon=False, fontsize=8)
    ax.set_aspect("equal")
    _title(ax, title)
    return _finish(fig)


def bar_png(df: pd.DataFrame, x: str, y: str, title: str | None = None,
            horizontal: bool = False, color_status: bool = False,
            height_px: int = 330, width_px: int = 950) -> bytes:
    cats = [str(v) for v in df[x].tolist()]
    vals = [float(v) for v in df[y].tolist()]
    colors = _colors_for(cats) if color_status else PALETTE["primary"]
    fig, ax = _new(width_px, height_px)
    if horizontal:
        bars = ax.barh(cats, vals, color=colors)
        ax.invert_yaxis()
        ax.xaxis.set_major_locator(MaxNLocator(integer=True))
        ax.bar_label(bars, fmt="%.0f", padding=3, fontsize=8)
        ax.grid(axis="x", color="#EEF1F5", linewidth=0.8)
    else:
        bars = ax.bar(cats, vals, color=colors)
        ax.yaxis.set_major_locator(MaxNLocator(integer=True))
        ax.bar_label(bars, fmt="%.0f", padding=3, fontsize=8)
        ax.grid(axis="y", color="#EEF1F5", linewidth=0.8)
        if max((len(c) for c in cats), default=0) > 6 or len(cats) > 6:
            plt.setp(ax.get_xticklabels(), rotation=25, ha="right")
    ax.set_axisbelow(True)
    _despine(ax)
    _title(ax, title)
    return _finish(fig)


def line_png(df: pd.DataFrame, x: str, y: str, title: str | None = None,
             area: bool = False, color: str | None = None, currency: bool = False,
             height_px: int = 330, width_px: int = 950) -> bytes:
    """A monthly trend line.

    The x column carries period labels ("2026-05"), plotted as evenly spaced
    categories rather than dates: a series with one month in it should show one
    point, not a lone marker adrift on a four-year date axis.
    """
    color = color or PALETTE["primary"]
    labels = [str(v) for v in df[x].tolist()]
    ys = df[y].astype(float).tolist()
    xs = list(range(len(labels)))
    fig, ax = _new(width_px, height_px)
    ax.plot(xs, ys, color=color, linewidth=2.2, marker="o", markersize=4)
    if area and len(xs) > 1:
        ax.fill_between(xs, ys, color=color, alpha=0.12)
    ax.set_xlim(-0.5, max(len(labels) - 0.5, 0.5))
    # Read counts and money from zero. Left to autoscale, a single-month series
    # gets a y-axis of 3.80…4.20 around its one value, which says nothing.
    if ys and min(ys) >= 0:
        ax.set_ylim(0, max(max(ys), 1) * 1.15)
    _category_ticks(ax, labels)
    if currency:
        ax.yaxis.set_major_formatter(lambda v, _pos: _money(v))
        ax.yaxis.set_major_locator(MaxNLocator(nbins=6))
    else:
        ax.yaxis.set_major_locator(MaxNLocator(integer=True, nbins=6))
    ax.grid(axis="y", color="#EEF1F5", linewidth=0.8)
    ax.set_axisbelow(True)
    _despine(ax)
    _title(ax, title)
    return _finish(fig)


def _money(value: float) -> str:
    """Axis-scale currency: $1.2M / $840K / $310."""
    v = float(value)
    for limit, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(v) >= limit:
            return f"${v / limit:,.1f}{suffix}"
    return f"${v:,.0f}"


def heatmap_png(pivot: pd.DataFrame, title: str | None = None, cmap: str = "Blues",
                height_px: int = 330, width_px: int = 950) -> bytes:
    fig, ax = _new(width_px, height_px)
    data = pivot.to_numpy(dtype=float)
    im = ax.imshow(data, cmap=cmap, aspect="auto")
    ax.set_xticks(range(len(pivot.columns)), [str(c) for c in pivot.columns],
                  rotation=20, ha="right", fontsize=8)
    ax.set_yticks(range(len(pivot.index)), [str(i) for i in pivot.index], fontsize=8)
    thresh = data.max() * 0.6 if data.size else 0
    for r in range(data.shape[0]):
        for c in range(data.shape[1]):
            v = data[r, c]
            ax.text(c, r, f"{int(v)}", ha="center", va="center", fontsize=8,
                    color="white" if v > thresh else PALETTE["ink"])
    fig.colorbar(im, ax=ax, shrink=0.8)
    _title(ax, title)
    return _finish(fig)


def stacked_bar_png(pivot: pd.DataFrame, title: str | None = None, percent: bool = False,
                    height_px: int = 330, width_px: int = 950) -> bytes:
    """Stacked bar from a pivot (index = bar, columns = stacked series)."""
    data = pivot.copy().astype(float)
    if percent:
        data = data.div(data.sum(axis=1).replace(0, 1), axis=0) * 100
    cats = [str(i) for i in data.index]
    fig, ax = _new(width_px, height_px)
    bottom = [0.0] * len(cats)
    for i, col in enumerate(data.columns):
        vals = data[col].tolist()
        ax.bar(cats, vals, bottom=bottom,
               color=STATUS_COLORS.get(str(col),
                                       CATEGORICAL_SEQUENCE[i % len(CATEGORICAL_SEQUENCE)]),
               label=str(col))
        bottom = [b + v for b, v in zip(bottom, vals)]
    if percent:
        ax.set_ylim(0, 100)
    else:
        ax.yaxis.set_major_locator(MaxNLocator(integer=True, nbins=6))
    ax.grid(axis="y", color="#EEF1F5", linewidth=0.8)
    ax.set_axisbelow(True)
    _category_ticks(ax, cats)
    ax.legend(frameon=False, fontsize=7.5, loc="center left", bbox_to_anchor=(1.0, 0.5))
    _despine(ax)
    _title(ax, title)
    return _finish(fig)


def grouped_bar_png(df: pd.DataFrame, x: str, series: list[str], title: str | None = None,
                    height_px: int = 330, width_px: int = 950) -> bytes:
    cats = [str(v) for v in df[x].tolist()]
    n, m = len(cats), len(series)
    width = 0.8 / max(m, 1)
    fig, ax = _new(width_px, height_px)
    for i, s in enumerate(series):
        offs = [j + (i - (m - 1) / 2) * width for j in range(n)]
        # The series name is the label as the caller wrote it — title-casing it
        # here turns "EOS Migration — Gen-1" into "Eos Migration — Gen-1".
        ax.bar(offs, df[s].astype(float).tolist(), width=width, label=str(s),
               color=STATUS_COLORS.get(str(s),
                                       CATEGORICAL_SEQUENCE[i % len(CATEGORICAL_SEQUENCE)]))
    _category_ticks(ax, cats)
    ax.yaxis.set_major_locator(MaxNLocator(integer=True, nbins=6))
    ax.grid(axis="y", color="#EEF1F5", linewidth=0.8)
    ax.set_axisbelow(True)
    # Above the plot: below it the legend lands on top of rotated month labels.
    ax.legend(frameon=False, fontsize=8, ncol=m, loc="lower center",
              bbox_to_anchor=(0.5, 1.0))
    _despine(ax)
    _title(ax, title)
    return _finish(fig)
