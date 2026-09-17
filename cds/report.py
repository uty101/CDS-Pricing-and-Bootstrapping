"""Table and chart generators (BUILD_PLAN.md Part D.3), one function per
output. Each takes the bootstrap results, writes its files under outputs/
and returns the DataFrame it wrote. scripts/make_outputs.py runs them; the
README embeds the files by path and computes nothing.

Section 6 owns Table 1 and Chart 1, Section 7 Tables 2 and 5; later
sections add their outputs here.

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

Table 2, outputs/tables/table_2_quantlib_validation.csv (+ .md), long
format, one row per (curve, trade, metric) from cds.validation.quantlib_check:
ours, QuantLib's, the difference in the stated unit, the tolerance and
whether the row passes. The rows are computed by the validation module and
handed in; this module only writes them.

Table 5, outputs/tables/table_5_isda_vs_textbook.csv (+ .md): for 1Y, 5Y
and 10Y on each curve, the ISDA-path clean upfront and par spread from the
bootstrapped curve against the textbook model (cds.textbook: continuous
premium and discounting, flat hazard, no schedule) fed the flat-hazard
equivalent of the pillar's conventional spread (cds.pricer.implied_flat_hazard
on the pillar contract) and the discount curve's continuously compounded
act/365F zero rate to the maturity. diff_bp is in bp of notional,
diff_par_bp in bp of spread, both ISDA minus textbook.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402 - the backend must be chosen first

from cds import textbook
from cds.bootstrap import BootstrapResult, market_state, pillar_trade
from cds.conventions import ACT365F_BASIS
from cds.pricer import implied_flat_hazard, price
from cds.schedule import year_fraction_act365f

__all__ = [
    "CHART_1_COLUMNS",
    "CHARTS_DIR",
    "OUTPUT_DECIMALS",
    "TABLE_1_COLUMNS",
    "TABLE_2_COLUMNS",
    "TABLE_5_COLUMNS",
    "TABLE_5_COUPONS_BP",
    "TABLE_5_TENORS",
    "TABLES_DIR",
    "chart_1_survival_hazard",
    "markdown_table",
    "rounded",
    "table_1_hazard_curves",
    "table_2_quantlib_validation",
    "table_5_isda_vs_textbook",
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
TABLE_2_COLUMNS = ("curve", "trade", "metric", "ours", "quantlib", "diff", "unit", "tolerance", "pass")
TABLE_5_COLUMNS = (
    "curve",
    "tenor",
    "coupon_bp",
    "isda_clean_upfront_pct",
    "textbook_upfront_pct",
    "diff_bp",
    "isda_par_spread_bp",
    "textbook_par_spread_bp",
    "diff_par_bp",
)

# Table 5: the tenors compared and the coupon each curve is priced at (the
# Section 7 trades' coupons: 100 bp on IG, 500 bp on HY and distressed).
TABLE_5_TENORS = ("1Y", "5Y", "10Y")
TABLE_5_COUPONS_BP = {"IG_flat": 100.0, "HY_steep": 500.0, "distressed_inverted": 500.0}
BP_PER_UNIT = 1e4

PERCENT = 100.0

# Chart geometry: 1600 x 900 pixels (Part D.3).
CHART_SIZE_PX = (1600, 900)
CHART_DPI = 100
CHART_YEARS = 10.0
MONTHS_PER_YEAR = 12

# Every float column of a committed output is rounded to this many decimal
# places when written (docs/CONVENTIONS_RESOLVED.md item 34): byte-identical
# floats are not portable across numpy and pandas builds, and 1e-10 is far
# below every tolerance in the plan. Tests compare a regeneration with the
# committed file numerically, never as text.
OUTPUT_DECIMALS = 10

# Decimal places per column in the Markdown rendering.
MD_DECIMALS = {
    "quote": 6,
    "coupon_bp": 0,
    "conventional_spread_bp": 6,
    "hazard_pct": 4,
    "survival_prob": 6,
    "cum_default_prob": 6,
    "t_years": 6,
    "ours": 9,
    "quantlib": 9,
    "diff": 6,
    "tolerance": 3,
    "isda_clean_upfront_pct": 6,
    "textbook_upfront_pct": 6,
    "diff_bp": 4,
    "isda_par_spread_bp": 6,
    "textbook_par_spread_bp": 6,
    "diff_par_bp": 4,
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


def rounded(df: pd.DataFrame) -> pd.DataFrame:
    """The frame with every float column rounded to OUTPUT_DECIMALS places:
    what every committed CSV holds (item 34). A difference that rounds to
    zero is written as 0.0, not -0.0."""
    out = df.round(OUTPUT_DECIMALS)
    floats = out.select_dtypes(include="float").columns
    out[floats] = out[floats] + 0.0
    return out


def write_table(df: pd.DataFrame, stem: Path) -> None:
    """stem.csv with a header row and stem.md rendered from the same frame,
    both from the rounded frame."""
    stem.parent.mkdir(parents=True, exist_ok=True)
    df = rounded(df)
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


def table_2_quantlib_validation(rows: Sequence, out_dir: Path = TABLES_DIR) -> pd.DataFrame:
    """Table 2 from the validation rows (cds.validation.quantlib_check.Row),
    columns TABLE_2_COLUMNS; Row.passed becomes the pass column."""
    df = pd.DataFrame(
        [
            {
                "curve": r.curve,
                "trade": r.trade,
                "metric": r.metric,
                "ours": r.ours,
                "quantlib": r.quantlib,
                "diff": r.diff,
                "unit": r.unit,
                "tolerance": r.tolerance,
                "pass": bool(r.passed),
            }
            for r in rows
        ],
        columns=list(TABLE_2_COLUMNS),
    )
    write_table(df, out_dir / "table_2_quantlib_validation")
    return df


def table_5_isda_vs_textbook(
    results: Sequence[BootstrapResult],
    discount,
    coupons_bp: dict[str, float] | None = None,
    tenors: Sequence[str] = TABLE_5_TENORS,
    out_dir: Path = TABLES_DIR,
) -> pd.DataFrame:
    """Table 5: the ISDA path against the textbook model, columns
    TABLE_5_COLUMNS (see the module docstring for the textbook inputs)."""
    coupons_bp = TABLE_5_COUPONS_BP if coupons_bp is None else coupons_bp
    rows = []
    for r in results:
        quotes = r.quotes
        state = market_state(r, discount)
        coupon_bp = coupons_bp[quotes.label]
        for tenor in tenors:
            i = quotes.pillars.index(tenor)
            trade = pillar_trade(quotes, i, coupon_bp)
            isda = price(state, trade)
            s_i = r.conventional_spreads_bp[i]
            hazard = implied_flat_hazard(discount, trade, s_i)
            t_mat = year_fraction_act365f(quotes.as_of, trade.maturity)
            rate = discount.zero_rate(t_mat)
            tb_upfront = textbook.upfront_pct(hazard, rate, t_mat, quotes.recovery, coupon_bp)
            tb_spread = textbook.par_spread_bp(hazard, quotes.recovery)
            rows.append(
                {
                    "curve": quotes.label,
                    "tenor": tenor,
                    "coupon_bp": coupon_bp,
                    "isda_clean_upfront_pct": isda.clean_upfront_pct,
                    "textbook_upfront_pct": tb_upfront,
                    "diff_bp": BP_PER_UNIT / PERCENT * (isda.clean_upfront_pct - tb_upfront),
                    "isda_par_spread_bp": isda.par_spread_bp,
                    "textbook_par_spread_bp": tb_spread,
                    "diff_par_bp": isda.par_spread_bp - tb_spread,
                }
            )
    df = pd.DataFrame(rows, columns=list(TABLE_5_COLUMNS))
    write_table(df, out_dir / "table_5_isda_vs_textbook")
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
    rounded(df).to_csv(out_dir / "chart_1_survival_hazard.csv", index=False, lineterminator="\n")

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
