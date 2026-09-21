"""Regenerate the committed outputs (BUILD_PLAN.md Part D.3).

    uv run python scripts/make_outputs.py                 # everything
    uv run python scripts/make_outputs.py --only table_1  # one output
    uv run python scripts/make_outputs.py --list

Reads the discount curve from the rates snapshot and every curve file in
data/curves/, bootstraps each (with the "upfront" fallback, so a curve that
needs a negative hazard is still tabulated, its method column saying so),
and hands the results to the generators in cds.report. The valuation date
is the rates file's as_of; a curve file dated otherwise is an error.

Table 1 lists every curve file; Chart 1 draws the three named curves (the
arbitrage curve has no joint hazard curve to draw). Table 2 (the QuantLib
comparison, Section 7), Table 5 (ISDA path against the textbook model) and
Table 3 (the risk report, Section 8) cover the three named curves; Chart 2
(recovery dependence), Table 4 (the P&L explain, Section 9, both files)
and Chart 3 (P&L against the spread multiplier) are on IG_flat.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from cds import report
from cds.bootstrap import BootstrapResult, bootstrap, market_curve_quotes_from_file
from cds.curves import discount_curve_from_file

ROOT = Path(__file__).resolve().parent.parent
RATES_FILE = ROOT / "data" / "rates" / "sofr_ois_2026-09-15.json"
CURVES_DIR = ROOT / "data" / "curves"

# Curve files in the order Table 1 lists them; Chart 1 draws the first three.
CURVE_FILES = ("IG_flat", "HY_steep", "distressed_inverted", "distressed_arb")
CHART_CURVES = CURVE_FILES[:3]


def load_results() -> dict[str, BootstrapResult]:
    discount = discount_curve_from_file(RATES_FILE)
    results = {}
    for label in CURVE_FILES:
        quotes = market_curve_quotes_from_file(CURVES_DIR / f"{label}.json")
        if quotes.as_of != discount.as_of:
            raise ValueError(f"{label}.json is dated {quotes.as_of}; the rates snapshot is {discount.as_of}")
        results[label] = bootstrap(quotes, discount, fallback="upfront")
    return results


def make_table_1(results: dict[str, BootstrapResult]) -> None:
    df = report.table_1_hazard_curves([results[k] for k in CURVE_FILES])
    print(f"table_1_hazard_curves: {len(df)} rows -> {report.TABLES_DIR}")


def make_chart_1(results: dict[str, BootstrapResult]) -> None:
    df = report.chart_1_survival_hazard([results[k] for k in CHART_CURVES])
    print(f"chart_1_survival_hazard: {len(df)} rows -> {report.CHARTS_DIR}")


def make_table_2(results: dict[str, BootstrapResult]) -> None:
    from cds.validation.quantlib_check import validation_rows  # QuantLib, imported only here

    df = report.table_2_quantlib_validation(validation_rows(results, discount_curve_from_file(RATES_FILE)))
    print(f"table_2_quantlib_validation: {len(df)} rows, {int(df['pass'].sum())} pass -> {report.TABLES_DIR}")


def make_table_5(results: dict[str, BootstrapResult]) -> None:
    df = report.table_5_isda_vs_textbook([results[k] for k in CHART_CURVES], discount_curve_from_file(RATES_FILE))
    print(f"table_5_isda_vs_textbook: {len(df)} rows -> {report.TABLES_DIR}")


def make_table_3(results: dict[str, BootstrapResult]) -> None:
    df = report.table_3_risk_report([results[k] for k in CHART_CURVES], discount_curve_from_file(RATES_FILE))
    print(f"table_3_risk_report: {len(df)} rows -> {report.TABLES_DIR}")


def make_chart_2(results: dict[str, BootstrapResult]) -> None:
    df = report.chart_2_recovery_dependence(results[report.CHART_2_CURVE], discount_curve_from_file(RATES_FILE))
    print(f"chart_2_recovery_dependence: {len(df)} rows -> {report.CHARTS_DIR}")


def make_table_4(results: dict[str, BootstrapResult]) -> None:
    """Both Table 4 files from one explain of the grid."""
    result, discount = results[report.TABLE_4_CURVE], discount_curve_from_file(RATES_FILE)
    rows = report.explain_grid(result, discount)
    df = report.table_4_pnl_explain(result, discount, rows=rows)
    full = report.table_4_pnl_explain_full(result, discount, rows=rows)
    print(f"table_4_pnl_explain: {len(df)} rows, table_4_pnl_explain_full: {len(full)} rows -> {report.TABLES_DIR}")


def make_chart_3(results: dict[str, BootstrapResult]) -> None:
    df = report.chart_3_pnl_vs_spread_shock(results[report.CHART_3_CURVE], discount_curve_from_file(RATES_FILE))
    print(f"chart_3_pnl_vs_spread_shock: {len(df)} rows -> {report.CHARTS_DIR}")


OUTPUTS = {
    "table_1": make_table_1,
    "chart_1": make_chart_1,
    "table_2": make_table_2,
    "table_3": make_table_3,
    "table_4": make_table_4,
    "table_5": make_table_5,
    "chart_2": make_chart_2,
    "chart_3": make_chart_3,
}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--only", action="append", choices=sorted(OUTPUTS), help="generate this output only (repeatable)")
    ap.add_argument("--list", action="store_true", help="list the outputs and exit")
    args = ap.parse_args(argv)
    if args.list:
        print("\n".join(OUTPUTS))
        return 0
    results = load_results()
    for name in args.only or list(OUTPUTS):
        OUTPUTS[name](results)
    return 0


if __name__ == "__main__":
    sys.exit(main())
