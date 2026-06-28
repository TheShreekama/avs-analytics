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
             area: bool = False, color: str | None = None,
             height_px: int = 330, width_px: int = 950) -> bytes:
    color = color or PALETTE["primary"]
    xs = pd.to_datetime(df[x]) if not pd.api.types.is_numeric_dtype(df[x]) else df[x]
    ys = df[y].astype(float)
    fig, ax = _new(width_px, height_px)
    ax.plot(xs, ys, color=color, linewidth=2.2, marker="o", markersize=4)
    if area:
        ax.fill_between(xs, ys, color=color, alpha=0.12)
    ax.yaxis.set_major_locator(MaxNLocator(integer=True))
    ax.grid(axis="y", color="#EEF1F5", linewidth=0.8)
    ax.set_axisbelow(True)
    _despine(ax)
    if not pd.api.types.is_numeric_dtype(df[x]):
        fig.autofmt_xdate(rotation=25)
    _title(ax, title)
    return _finish(fig)


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


def grouped_bar_png(df: pd.DataFrame, x: str, series: list[str], title: str | None = None,
                    height_px: int = 330, width_px: int = 950) -> bytes:
    cats = [str(v) for v in df[x].tolist()]
    n, m = len(cats), len(series)
    width = 0.8 / max(m, 1)
    fig, ax = _new(width_px, height_px)
    for i, s in enumerate(series):
        offs = [j + (i - (m - 1) / 2) * width for j in range(n)]
        ax.bar(offs, df[s].astype(float).tolist(), width=width,
               label=s.replace("_", " ").title(),
               color=STATUS_COLORS.get(s.title(), CATEGORICAL_SEQUENCE[i % len(CATEGORICAL_SEQUENCE)]))
    ax.set_xticks(range(n), cats, rotation=20, ha="right", fontsize=8)
    ax.yaxis.set_major_locator(MaxNLocator(integer=True))
    ax.grid(axis="y", color="#EEF1F5", linewidth=0.8)
    ax.set_axisbelow(True)
    ax.legend(frameon=False, fontsize=8, ncol=m, loc="upper center",
              bbox_to_anchor=(0.5, -0.12))
    _despine(ax)
    _title(ax, title)
    return _finish(fig)
