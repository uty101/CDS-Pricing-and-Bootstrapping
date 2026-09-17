"""Table and chart generators (BUILD_PLAN.md Part D.3), one function per
output. Each takes the bootstrap results, writes its files under outputs/
and returns the DataFrame it wrote. scripts/make_outputs.py runs them; the
README embeds the files by path and computes nothing.

Section 6 owns Table 1 and Chart 1; later sections add their outputs here.

Table 1, outputs/tables/table_1_hazard_curves.csv (+ .md), one row per
(curve, pillar): the quote as committed, the conventional spread the
bootstrap fitted, the method ("bootstrap" or the fallback used), the pillar
hazard lambda_i in percent, the survival probability Q(t_i) at the pillar
and the cumulative default probability 1 - Q(t_i). For the "upfront"
fallback the survival is that of the pillar's own flat hazard.

Chart 1, outputs/charts/chart_1_survival_hazard.png (1600 x 900), two
panels: Q(t) and lambda(t) on 0 to 10 years for the curves given. The
hazard panel draws the exact step function (lambda_i on (t_{i-1}, t_i]);
the survival panel draws Q(t) daily. chart_1_survival_hazard.csv holds the
same two functions sampled on a monthly grid t = k / 12, k = 0..120.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402 - the backend must be chosen first

from cds.bootstrap import BootstrapResult
from cds.conventions import ACT365F_BASIS
from cds.schedule import year_fraction_act365f

__all__ = [
    "CHART_1_COLUMNS",
    "CHARTS_DIR",
    "TABLE_1_COLUMNS",
    "TABLES_DIR",
    "chart_1_survival_hazard",
    "markdown_table",
    "table_1_hazard_curves",
    "write_table",
]

ROOT = Path(__file__).resolve().parent.parent
TABLES_DIR = ROOT / "outputs" / "tables"
CHARTS_DIR = ROOT / "outputs" / "charts"

TABLE_1_COLUMNS = (
    "curve",
    "pillar",
    "maturity",
    "quote_kind",
    "quote",
    "coupon_bp",
    "conventional_spread_bp",
    "method",
    "hazard_pct",
    "survival_prob",
    "cum_default_prob",
)
CHART_1_COLUMNS = ("curve", "t_years", "hazard_pct", "survival_prob")

PERCENT = 100.0

# Chart geometry: 1600 x 900 pixels (Part D.3).
CHART_SIZE_PX = (1600, 900)
CHART_DPI = 100
CHART_YEARS = 10.0
MONTHS_PER_YEAR = 12

# Decimal places per column in the Markdown rendering; the CSV keeps full
# precision.
MD_DECIMALS = {
    "quote": 6,
    "coupon_bp": 0,
    "conventional_spread_bp": 6,
    "hazard_pct": 4,
    "survival_prob": 6,
    "cum_default_prob": 6,
    "t_years": 6,
}

# Chart colours: three categorical series in a fixed order (curve order as
# given), text in ink tones, hairline grey grid.
SERIES_COLOURS = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300")
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
GRID = "#d9d8d3"
SURFACE = "#fcfcfb"


def markdown_table(df: pd.DataFrame, decimals: dict[str, int] | None = None) -> str:
    """A GitHub-flavoured Markdown table of the frame, floats rounded per
    column (decimals), everything else str()."""
    decimals = MD_DECIMALS if decimals is None else decimals

    def cell(col: str, v) -> str:
        if isinstance(v, (float, np.floating)):
            if pd.isna(v):
                return ""
            return f"{v:.{decimals.get(col, 6)}f}"
        if v is None:
            return ""
        return str(v)

    header = "| " + " | ".join(df.columns) + " |"
    rule = "|" + "|".join("---" for _ in df.columns) + "|"
    rows = ["| " + " | ".join(cell(c, v) for c, v in zip(df.columns, row)) + " |" for row in df.itertuples(index=False, name=None)]
    return "\n".join([header, rule, *rows]) + "\n"


def write_table(df: pd.DataFrame, stem: Path) -> None:
    """stem.csv with a header row and stem.md rendered from the same frame."""
    stem.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(stem.with_suffix(".csv"), index=False, lineterminator="\n")
    stem.with_suffix(".md").write_text(markdown_table(df), encoding="utf-8", newline="\n")


def table_1_hazard_curves(results: Sequence[BootstrapResult], out_dir: Path = TABLES_DIR) -> pd.DataFrame:
    """Table 1: one row per (curve, pillar), columns TABLE_1_COLUMNS."""
    rows = []
    for r in results:
        for i, pillar in enumerate(r.quotes.pillars):
            q = r.quotes.quotes[i]
            q_t = r.survival_for_pillar(i).Q(year_fraction_act365f(r.quotes.as_of, r.pillar_dates[i]))
            rows.append(
                {
                    "curve": r.quotes.label,
                    "pillar": pillar,
                    "maturity": r.pillar_dates[i].isoformat(),
                    "quote_kind": q.kind,
                    "quote": float(q.value),
                    "coupon_bp": q.coupon_bp,
                    "conventional_spread_bp": r.conventional_spreads_bp[i],
                    "method": r.method,
                    "hazard_pct": PERCENT * r.pillar_hazards[i],
                    "survival_prob": q_t,
                    "cum_default_prob": 1.0 - q_t,
                }
            )
    df = pd.DataFrame(rows, columns=list(TABLE_1_COLUMNS))
    write_table(df, out_dir / "table_1_hazard_curves")
    return df


def _monthly_grid(results: Sequence[BootstrapResult]) -> pd.DataFrame:
    t = np.arange(0, int(CHART_YEARS * MONTHS_PER_YEAR) + 1) / MONTHS_PER_YEAR
    frames = []
    for r in results:
        if r.survival is None:
            raise ValueError(f"curve {r.quotes.label} has no joint survival curve (fallback 'upfront'); Chart 1 cannot draw it")
        frames.append(
            pd.DataFrame(
                {
                    "curve": r.quotes.label,
                    "t_years": t,
                    "hazard_pct": PERCENT * np.asarray(r.survival.hazard(t)),
                    "survival_prob": np.asarray(r.survival.Q(t)),
                }
            )
        )
    return pd.concat(frames, ignore_index=True)[list(CHART_1_COLUMNS)]


def _style_axis(ax, title: str, ylabel: str) -> None:
    ax.set_facecolor(SURFACE)
    ax.set_title(title, loc="left", color=INK, fontsize=13, pad=12)
    ax.set_xlabel("years from valuation date (act/365F)", color=INK_SECONDARY, fontsize=10)
    ax.set_ylabel(ylabel, color=INK_SECONDARY, fontsize=10)
    ax.set_xlim(0, CHART_YEARS)
    ax.grid(True, color=GRID, linewidth=1, linestyle="-")
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=INK_SECONDARY, labelsize=9)


def chart_1_survival_hazard(results: Sequence[BootstrapResult], out_dir: Path = CHARTS_DIR) -> pd.DataFrame:
    """Chart 1: Q(t) and lambda(t) on 0 to 10Y for the curves given; the
    monthly-grid data written next to it. Returns the data frame."""
    df = _monthly_grid(results)
    out_dir.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_dir / "chart_1_survival_hazard.csv", index=False, lineterminator="\n")

    fig, (ax_q, ax_h) = plt.subplots(1, 2, figsize=(CHART_SIZE_PX[0] / CHART_DPI, CHART_SIZE_PX[1] / CHART_DPI), dpi=CHART_DPI)
    fig.patch.set_facecolor(SURFACE)
    t_daily = np.arange(0, int(CHART_YEARS * ACT365F_BASIS) + 1) / ACT365F_BASIS
    for k, r in enumerate(results):
        colour = SERIES_COLOURS[k % len(SERIES_COLOURS)]
        label = r.quotes.label
        q = np.asarray(r.survival.Q(t_daily))
        ax_q.plot(t_daily, q, color=colour, linewidth=2, solid_joinstyle="round", solid_capstyle="round", label=label)
        ax_q.annotate(label, (CHART_YEARS, q[-1]), xytext=(6, 0), textcoords="offset points", color=INK, fontsize=9, va="center")
        # lambda_i holds on (t_{i-1}, t_i], a step that changes at each pillar
        # time; the last hazard is extrapolated flat to the edge of the chart.
        edges = np.array([0.0, *r.survival.pillar_times, CHART_YEARS])
        hazards = PERCENT * np.array([*r.survival.pillar_hazards, r.survival.pillar_hazards[-1], r.survival.pillar_hazards[-1]])
        ax_h.step(edges, hazards, where="post", color=colour, linewidth=2, label=label)
        ax_h.annotate(label, (CHART_YEARS, hazards[-1]), xytext=(6, 0), textcoords="offset points", color=INK, fontsize=9, va="center")

    _style_axis(ax_q, "Survival probability Q(t)", "Q(t)")
    _style_axis(ax_h, "Piecewise-constant hazard rate λ(t)", "hazard, % per year")
    ax_q.set_ylim(0, 1.02)
    ax_h.set_ylim(bottom=0)
    for ax in (ax_q, ax_h):
        ax.legend(frameon=False, loc="best", fontsize=9, labelcolor=INK)
    as_of = results[0].quotes.as_of.isoformat()
    fig.suptitle(f"Bootstrapped survival curves, valuation date {as_of}", x=0.02, ha="left", color=INK, fontsize=15)
    fig.subplots_adjust(left=0.06, right=0.90, top=0.86, bottom=0.11, wspace=0.32)
    fig.savefig(out_dir / "chart_1_survival_hazard.png", dpi=CHART_DPI, facecolor=SURFACE)
    plt.close(fig)
    return df
