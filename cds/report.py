"""Table and chart generators (BUILD_PLAN.md Part D.3), one function per
output. Each takes the bootstrap results, writes its files under outputs/
and returns the DataFrame it wrote. scripts/make_outputs.py runs them; the
README embeds the files by path and computes nothing.

Section 6 owns Table 1 and Chart 1, Section 7 Tables 2 and 5, Section 8
Table 3 and Chart 2, Section 9 Table 4 and Chart 3; later sections add
their outputs here.

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

Table 3, outputs/tables/table_3_risk_report.csv (+ .md): one row per curve
for the 5Y protection buy on DEFAULT_NOTIONAL at the standard coupon (100
bp on IG, 500 bp on HY and distressed), columns curve, trade, then every
RiskReport field in order (cds.risk.risk, BUILD_PLAN.md Part D.2). The
Markdown rendering is transposed, measures as rows and trades as columns,
to two decimal places of currency.

Chart 2, outputs/charts/chart_2_recovery_dependence.png (1600 x 900), two
panels on the IG curve for R from 0.10 to 0.60 in steps of 0.01 (Part C
item 1): (a) the implied 5Y default probability 1 - Q(t_5Y) with the
conventional spreads held fixed and the curve re-bootstrapped at each R;
(b) the MTM of the par 5Y running-spread trade (coupon = the 5Y par spread
at the file's recovery) and of the running-spread trade struck 200 bp
above it, each drawn twice: re-bootstrapped at each R (the desk number,
flat for the par trade) and with the hazard curve held at the file's
recovery (the slope -I N, the same for both). Each legend label of panel
(b) ends with the line's slope in $ per recovery point, the least-squares
slope of the column against R in points over the 51 rows of the data
file (chart_2_slopes; docs/CONVENTIONS_RESOLVED.md item 43). The data
file chart_2_recovery_dependence.csv holds recovery,
implied_5y_default_prob, mtm_par_trade, mtm_offmarket_trade,
mtm_par_trade_hazard_fixed, mtm_offmarket_trade_hazard_fixed.

Table 4, outputs/tables/table_4_pnl_explain.csv (+ .md): the P&L explain
(cds.explain.explain) of the 5Y IG protection buy at the standard coupon
for six scenarios of the Section 9 grid (TABLE_4_SCENARIOS: spreads x1.5,
x3, recovery to 0.20, steepen, rates +100 bp, combined), columns scenario
then every ExplainResult field in order. table_4_pnl_explain_full.csv
(+ .md) has every scenario of cds.scenarios.standard_grid, same columns.
Every scenario is one re-bootstrap; the sensitivities at t_0 are computed
once (cds.explain.sensitivities) and shared. A residual_pct_of_total that
is not a number (a scenario with no P&L) is written empty.

Chart 3, outputs/charts/chart_3_pnl_vs_spread_shock.png (1600 x 900): the
buyer's P&L of the same trade against the spread multiplier m from 0.5 to
4 in 0.05 steps (cds.scenarios.sweep_grid, every pillar's conventional
spread times m): the full revaluation (cds.scenarios.run), the first-order
explain sum_i cs01_i Delta s_i, and first order plus the gamma term
1/2 Gamma Delta s^2 with Gamma and Delta s as cds.explain defines them.
The data file chart_3_pnl_vs_spread_shock.csv holds spread_multiplier,
pnl_full, pnl_first_order, pnl_second_order (the last is first order plus
gamma).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402 - the backend must be chosen first

from cds import scenarios, textbook
from cds.bootstrap import BootstrapResult, market_state, pillar_trade
from cds.conventions import ACT365F_BASIS
from cds.explain import Sensitivities, explain, sensitivities
from cds.pricer import implied_flat_hazard, price
from cds.risk import recovery_state, risk
from cds.schedule import year_fraction_act365f
from cds.types import CDSTrade, ExplainResult, Quote, RiskReport

__all__ = [
    "CHART_1_COLUMNS",
    "CHART_2_COLUMNS",
    "CHART_2_CURVE",
    "CHART_2_OFFMARKET_BP",
    "CHART_2_RECOVERIES",
    "CHART_3_COLUMNS",
    "CHART_3_CURVE",
    "CHARTS_DIR",
    "OUTPUT_DECIMALS",
    "STANDARD_COUPONS_BY_CURVE",
    "TABLE_1_COLUMNS",
    "TABLE_2_COLUMNS",
    "TABLE_3_COLUMNS",
    "TABLE_3_TENOR",
    "TABLE_4_COLUMNS",
    "TABLE_4_CURVE",
    "TABLE_4_SCENARIOS",
    "TABLE_5_COLUMNS",
    "TABLE_5_COUPONS_BP",
    "TABLE_5_TENORS",
    "TABLES_DIR",
    "chart_1_survival_hazard",
    "chart_2_recovery_dependence",
    "chart_2_slopes",
    "chart_2_trades",
    "chart_3_pnl_vs_spread_shock",
    "explain_grid",
    "markdown_table",
    "rounded",
    "table_1_hazard_curves",
    "table_2_quantlib_validation",
    "table_3_risk_report",
    "table_4_pnl_explain",
    "table_4_pnl_explain_full",
    "table_4_trade",
    "table_5_isda_vs_textbook",
    "trade_label",
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

# The standard coupon each illustrative curve trades at: 100 bp on IG, 500
# bp on HY and distressed (the Section 7 trades, Table 3 and Table 5).
STANDARD_COUPONS_BY_CURVE = {"IG_flat": 100.0, "HY_steep": 500.0, "distressed_inverted": 500.0}

# Table 5: the tenors compared and the coupon each curve is priced at.
TABLE_5_TENORS = ("1Y", "5Y", "10Y")
TABLE_5_COUPONS_BP = STANDARD_COUPONS_BY_CURVE

# Table 3: the 5Y buy on each curve; the columns after curve and trade are
# the RiskReport fields in their declared order.
TABLE_3_TENOR = "5Y"
RISK_FIELDS = tuple(RiskReport.__dataclass_fields__)
TABLE_3_COLUMNS = ("curve", "trade", *RISK_FIELDS)

# Chart 2: the IG curve, R from 0.10 to 0.60 in 0.01 steps, and the
# off-market trade struck this many bp above the 5Y par spread (below would
# be a negative coupon on IG, whose 5Y par spread is 90 bp).
CHART_2_CURVE = "IG_flat"
CHART_2_RECOVERIES = tuple(round(0.10 + 0.01 * k, 2) for k in range(51))
CHART_2_OFFMARKET_BP = 200.0
CHART_2_COLUMNS = (
    "recovery",
    "implied_5y_default_prob",
    "mtm_par_trade",
    "mtm_offmarket_trade",
    "mtm_par_trade_hazard_fixed",
    "mtm_offmarket_trade_hazard_fixed",
)
THOUSAND = 1e3
BP_PER_UNIT = 1e4

# Table 4 and Chart 3: the 5Y IG buy at the standard coupon; the six Table 4
# scenarios by the names cds.scenarios gives them, the full table every
# scenario of the standard grid. The columns after scenario are the
# ExplainResult fields in their declared order.
TABLE_4_CURVE = "IG_flat"
CHART_3_CURVE = TABLE_4_CURVE
TABLE_4_SCENARIOS = ("spread_x1.5", "spread_x3", "recovery_0.2", "steepen_35bp", "rates_+100bp", "combined")
EXPLAIN_FIELDS = tuple(ExplainResult.__dataclass_fields__)
TABLE_4_COLUMNS = ("scenario", *EXPLAIN_FIELDS)
CHART_3_COLUMNS = ("spread_multiplier", "pnl_full", "pnl_first_order", "pnl_second_order")

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
    "recovery": 2,
    "implied_5y_default_prob": 6,
    "mtm_par_trade": 2,
    "mtm_offmarket_trade": 2,
    "mtm_par_trade_hazard_fixed": 2,
    "mtm_offmarket_trade_hazard_fixed": 2,
    **{f: 2 for f in EXPLAIN_FIELDS},
    "spread_multiplier": 2,
    "pnl_first_order": 2,
    "pnl_second_order": 2,
}

# Table 3's transposed Markdown: every measure is in currency.
TABLE_3_MD_DECIMALS = 2

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


def trade_label(tenor: str, coupon_bp: float) -> str:
    """The trade column of Tables 2 and 3: "<tenor>_buy_c<coupon>"."""
    return f"{tenor}_buy_c{coupon_bp:g}"


def table_3_risk_report(
    results: Sequence[BootstrapResult],
    discount,
    coupons_bp: dict[str, float] | None = None,
    out_dir: Path = TABLES_DIR,
) -> pd.DataFrame:
    """Table 3: the risk report of the 5Y buy at the standard coupon on each
    curve, columns TABLE_3_COLUMNS; the .md transposed."""
    coupons_bp = STANDARD_COUPONS_BY_CURVE if coupons_bp is None else coupons_bp
    rows = []
    for r in results:
        quotes = r.quotes
        coupon_bp = coupons_bp[quotes.label]
        trade = pillar_trade(quotes, quotes.pillars.index(TABLE_3_TENOR), coupon_bp)
        report = risk(market_state(r, discount), trade)
        rows.append({"curve": quotes.label, "trade": trade_label(TABLE_3_TENOR, coupon_bp), **{f: getattr(report, f) for f in RISK_FIELDS}})
    df = pd.DataFrame(rows, columns=list(TABLE_3_COLUMNS))
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = out_dir / "table_3_risk_report"
    rounded(df).to_csv(stem.with_suffix(".csv"), index=False, lineterminator="\n")
    # Measures as rows, rounded to the cent first so a -0.001 renders as 0.00, not -0.00.
    transposed = pd.DataFrame({"measure": list(RISK_FIELDS), **{f"{row['curve']} {row['trade']}": [round(row[f], TABLE_3_MD_DECIMALS) + 0.0 for f in RISK_FIELDS] for row in rows}})
    decimals = {c: TABLE_3_MD_DECIMALS for c in transposed.columns}
    stem.with_suffix(".md").write_text(markdown_table(transposed, decimals), encoding="utf-8", newline="\n")
    return df


def _running_spread_trade(trade: CDSTrade, coupon_bp: float, recovery: float | None = None) -> CDSTrade:
    """The trade as a running-spread contract at coupon_bp (a par_spread_bp
    quote equal to the coupon, Part B item 8), at another R if given."""
    return replace(trade, coupon_bp=coupon_bp, quote=Quote(kind="par_spread_bp", value=coupon_bp), recovery=trade.recovery if recovery is None else recovery)


def chart_2_trades(result: BootstrapResult, discount) -> tuple[CDSTrade, CDSTrade]:
    """The two Chart 2 trades on the curve: the 5Y running-spread trade at
    the curve's own 5Y par spread and the one struck CHART_2_OFFMARKET_BP
    above it, both protection buys on DEFAULT_NOTIONAL at the file's R."""
    quotes = result.quotes
    pillar = pillar_trade(quotes, quotes.pillars.index(TABLE_3_TENOR), STANDARD_COUPONS_BY_CURVE.get(quotes.label, STANDARD_COUPONS_BY_CURVE[CHART_2_CURVE]))
    s_par = price(market_state(result, discount), pillar).par_spread_bp
    return _running_spread_trade(pillar, s_par), _running_spread_trade(pillar, s_par + CHART_2_OFFMARKET_BP)


def _chart_2_rows(result: BootstrapResult, discount) -> pd.DataFrame:
    base = market_state(result, discount)
    par, offmarket = chart_2_trades(result, discount)
    t_5y = year_fraction_act365f(result.quotes.as_of, result.pillar_dates[result.quotes.pillars.index(TABLE_3_TENOR)])
    spreads = result.conventional_spreads_bp
    rows = []
    for recovery in CHART_2_RECOVERIES:
        refit = recovery_state(base, recovery, hazard_fixed=False, spreads_bp=spreads)
        fixed = recovery_state(base, recovery, hazard_fixed=True)
        par_r, off_r = replace(par, recovery=recovery), replace(offmarket, recovery=recovery)
        rows.append(
            {
                "recovery": recovery,
                "implied_5y_default_prob": 1.0 - refit.survival.Q(t_5y),
                "mtm_par_trade": price(refit, par_r).mtm,
                "mtm_offmarket_trade": price(refit, off_r).mtm,
                "mtm_par_trade_hazard_fixed": price(fixed, par_r).mtm,
                "mtm_offmarket_trade_hazard_fixed": price(fixed, off_r).mtm,
            }
        )
    return pd.DataFrame(rows, columns=list(CHART_2_COLUMNS))


def chart_2_slopes(df: pd.DataFrame) -> dict[str, float]:
    """The slope of each MTM column of the Chart 2 data in $ per recovery
    point: the least-squares slope against 100 R over every row. Exact for
    the hazard-fixed lines, which are linear in R; the fit over the range
    for the re-bootstrapped ones."""
    r_points = PERCENT * df["recovery"].to_numpy(dtype=float)
    return {col: float(np.polyfit(r_points, df[col].to_numpy(dtype=float), 1)[0]) for col in CHART_2_COLUMNS[2:]}


def chart_2_recovery_dependence(result: BootstrapResult, discount, out_dir: Path = CHARTS_DIR) -> pd.DataFrame:
    """Chart 2: implied 5Y default probability and the two trades' MTM
    against recovery on the given (IG) curve; the data written next to it.
    Panel (b)'s legend labels end with each line's slope from the data."""
    df = _chart_2_rows(result, discount)
    out_dir.mkdir(parents=True, exist_ok=True)
    rounded(df).to_csv(out_dir / "chart_2_recovery_dependence.csv", index=False, lineterminator="\n")
    par, offmarket = chart_2_trades(result, discount)
    base_r = result.quotes.recovery
    label = result.quotes.label
    slopes = chart_2_slopes(rounded(df))

    fig, (ax_pd, ax_mtm) = plt.subplots(1, 2, figsize=(CHART_SIZE_PX[0] / CHART_DPI, CHART_SIZE_PX[1] / CHART_DPI), dpi=CHART_DPI)
    fig.patch.set_facecolor(SURFACE)
    r_pct = PERCENT * df["recovery"].to_numpy()
    ax_pd.plot(r_pct, PERCENT * df["implied_5y_default_prob"].to_numpy(), color=SERIES_COLOURS[0], linewidth=2, label=f"{label}, spreads fixed, curve re-bootstrapped at each R")
    series = (
        ("mtm_par_trade", SERIES_COLOURS[0], "-", f"par trade, c = {par.coupon_bp:g} bp, re-bootstrapped (rec01)"),
        ("mtm_par_trade_hazard_fixed", SERIES_COLOURS[0], "--", f"par trade, c = {par.coupon_bp:g} bp, hazard fixed (rec01_hazard_fixed)"),
        ("mtm_offmarket_trade", SERIES_COLOURS[1], "-", f"off-market trade, c = {offmarket.coupon_bp:g} bp, re-bootstrapped"),
        ("mtm_offmarket_trade_hazard_fixed", SERIES_COLOURS[1], "--", f"off-market trade, c = {offmarket.coupon_bp:g} bp, hazard fixed"),
    )
    for col, colour, style, text in series:
        ax_mtm.plot(r_pct, df[col].to_numpy() / THOUSAND, color=colour, linewidth=2, linestyle=style, label=f"{text}: {slopes[col]:+,.0f} $/pt")
    _style_axis(ax_pd, "(a) Implied 5Y default probability 1 − Q(5Y)", "1 − Q(5Y), %")
    _style_axis(ax_mtm, "(b) MTM of the 5Y protection buy, $10m notional", "MTM, $ thousand")
    for ax in (ax_pd, ax_mtm):
        ax.axvline(PERCENT * base_r, color=INK_SECONDARY, linewidth=1, linestyle=":")
        ax.set_xlabel("assumed recovery R, %", color=INK_SECONDARY, fontsize=10)
        ax.set_xlim(PERCENT * CHART_2_RECOVERIES[0], PERCENT * CHART_2_RECOVERIES[-1])
        ax.legend(frameon=False, loc="best", fontsize=9, labelcolor=INK)
    ax_mtm.axhline(0.0, color=GRID, linewidth=1)
    as_of = result.quotes.as_of.isoformat()
    fig.suptitle(f"Recovery dependence on {label}, valuation date {as_of} (dotted: the file's R = {base_r:.0%})", x=0.02, ha="left", color=INK, fontsize=15)
    fig.subplots_adjust(left=0.06, right=0.98, top=0.86, bottom=0.11, wspace=0.24)
    fig.savefig(out_dir / "chart_2_recovery_dependence.png", dpi=CHART_DPI, facecolor=SURFACE)
    plt.close(fig)
    return df


def table_4_trade(result: BootstrapResult) -> CDSTrade:
    """The Table 4 and Chart 3 trade: the 5Y buy at the curve's standard
    coupon on DEFAULT_NOTIONAL, the curve's recovery."""
    quotes = result.quotes
    return pillar_trade(quotes, quotes.pillars.index(TABLE_3_TENOR), STANDARD_COUPONS_BY_CURVE[quotes.label])


def explain_grid(result: BootstrapResult, discount, grid: tuple[scenarios.Scenario, ...] | None = None, sens: Sensitivities | None = None) -> pd.DataFrame:
    """explain() of the Table 4 trade for every scenario of the grid (the
    standard grid at the curve's recovery unless given), columns
    TABLE_4_COLUMNS; the sensitivities at t_0 computed once unless given."""
    state = market_state(result, discount)
    trade = table_4_trade(result)
    if grid is None:
        grid = scenarios.standard_grid(result.quotes.recovery)
    if sens is None:
        sens = sensitivities(state, trade, spreads_bp=result.conventional_spreads_bp)
    states = scenarios.scenario_states(state, grid, spreads_bp=result.conventional_spreads_bp)
    rows = []
    for scenario, s in zip(grid, states):
        e = explain(state, s, trade, sensitivities_t0=sens)
        rows.append({"scenario": scenario.name, **{f: getattr(e, f) for f in EXPLAIN_FIELDS}})
    return pd.DataFrame(rows, columns=list(TABLE_4_COLUMNS))


def table_4_pnl_explain(result: BootstrapResult, discount, out_dir: Path = TABLES_DIR, rows: pd.DataFrame | None = None) -> pd.DataFrame:
    """Table 4: the six TABLE_4_SCENARIOS rows of explain_grid (computed
    unless rows, the full frame, is given), in that order."""
    full = explain_grid(result, discount) if rows is None else rows
    missing = [n for n in TABLE_4_SCENARIOS if n not in set(full["scenario"])]
    if missing:
        raise ValueError(f"the grid has no scenario named {missing}")
    df = full.set_index("scenario").loc[list(TABLE_4_SCENARIOS)].reset_index()[list(TABLE_4_COLUMNS)]
    write_table(df, out_dir / "table_4_pnl_explain")
    return df


def table_4_pnl_explain_full(result: BootstrapResult, discount, out_dir: Path = TABLES_DIR, rows: pd.DataFrame | None = None) -> pd.DataFrame:
    """Table 4, every scenario of the standard grid."""
    df = explain_grid(result, discount) if rows is None else rows
    write_table(df, out_dir / "table_4_pnl_explain_full")
    return df


def _chart_3_rows(result: BootstrapResult, discount, sens: Sensitivities | None = None) -> pd.DataFrame:
    state = market_state(result, discount)
    trade = table_4_trade(result)
    spreads = result.conventional_spreads_bp
    if sens is None:
        sens = sensitivities(state, trade, spreads_bp=spreads)
    grid = scenarios.sweep_grid()
    full = scenarios.run(state, trade, grid, spreads_bp=spreads)
    rep = sens.report
    cs01 = np.array([getattr(rep, f"cs01_{p.lower()}") for p in result.quotes.pillars])
    multipliers = np.array([sc.spread_multiplier for sc in grid])
    ds = np.outer(multipliers - 1.0, np.array(spreads))  # Delta s_i per scenario, bp
    first_order = ds @ cs01
    second_order = first_order + 0.5 * sens.gamma * ds.mean(axis=1) ** 2
    return pd.DataFrame(
        {
            "spread_multiplier": multipliers,
            "pnl_full": full["pnl_full"].to_numpy(),
            "pnl_first_order": first_order,
            "pnl_second_order": second_order,
        },
        columns=list(CHART_3_COLUMNS),
    )


def chart_3_pnl_vs_spread_shock(result: BootstrapResult, discount, out_dir: Path = CHARTS_DIR, sens: Sensitivities | None = None) -> pd.DataFrame:
    """Chart 3: the buyer's P&L against the spread multiplier, full
    revaluation against first order and first order plus gamma; the data
    written next to it."""
    df = _chart_3_rows(result, discount, sens)
    out_dir.mkdir(parents=True, exist_ok=True)
    rounded(df).to_csv(out_dir / "chart_3_pnl_vs_spread_shock.csv", index=False, lineterminator="\n")
    trade = table_4_trade(result)
    label = result.quotes.label
    m = df["spread_multiplier"].to_numpy()

    fig, ax = plt.subplots(figsize=(CHART_SIZE_PX[0] / CHART_DPI, CHART_SIZE_PX[1] / CHART_DPI), dpi=CHART_DPI)
    fig.patch.set_facecolor(SURFACE)
    series = (
        ("pnl_full", SERIES_COLOURS[0], "-", "full revaluation (one re-bootstrap per scenario)"),
        ("pnl_first_order", SERIES_COLOURS[1], "--", "first order: Σ CS01_i · Δs_i"),
        ("pnl_second_order", SERIES_COLOURS[2], "-.", "first order + ½ Γ Δs²"),
    )
    for col, colour, style, text in series:
        ax.plot(m, df[col].to_numpy() / THOUSAND, color=colour, linewidth=2, linestyle=style, label=text)
    _style_axis(ax, f"P&L of the 5Y protection buy on {label}, c = {trade.coupon_bp:g} bp, $10m notional", "P&L, $ thousand")
    ax.set_xlabel("spread multiplier m (every pillar's conventional spread × m)", color=INK_SECONDARY, fontsize=10)
    ax.set_xlim(m[0], m[-1])
    ax.axhline(0.0, color=GRID, linewidth=1)
    ax.axvline(1.0, color=INK_SECONDARY, linewidth=1, linestyle=":")
    ax.legend(frameon=False, loc="upper left", fontsize=10, labelcolor=INK)
    as_of = result.quotes.as_of.isoformat()
    fig.suptitle(f"Full revaluation against the explain, valuation date {as_of} (dotted: m = 1, the base)", x=0.02, ha="left", color=INK, fontsize=15)
    fig.subplots_adjust(left=0.07, right=0.98, top=0.86, bottom=0.11)
    fig.savefig(out_dir / "chart_3_pnl_vs_spread_shock.png", dpi=CHART_DPI, facecolor=SURFACE)
    plt.close(fig)
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
