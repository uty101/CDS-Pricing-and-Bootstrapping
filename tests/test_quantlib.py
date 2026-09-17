"""Section 7: the pricer, the bootstrap and the 5Y CS01 against QuantLib
(BUILD_PLAN.md Section 7, criteria 1 to 4), and Tables 2 and 5.

The comparisons are the rows cds.validation.quantlib_check computes; Table 2
is written from the same rows, so the test and the committed table cannot
disagree. QuantLib's flags are those in the module docstring there:
IsdaCdsEngine(Taylor, HalfDayBias, Piecewise), CDS2015 schedules on
WeekendsOnly, Actual360 coupons with the last period including the maturity,
Actual365Fixed curves, the helper's settlementDays = 1 (our step-in) and the
contract's cashSettlementDays = 3.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pandas as pd
import pytest

from cds import report
from cds.bootstrap import BootstrapResult, bootstrap, market_curve_quotes_from_file
from cds.calendars import adjust_following
from cds.conventions import PILLARS
from cds.curves import DiscountCurve, discount_curve_from_file
from cds.validation import quantlib_check as qc
from tests.conftest import (
    BOOTSTRAP_REPRICE_BP,
    PRICER_IDENTITY_ABS_TOL,
    QL_ANNUITY_ABS_TOL,
    QL_CS01_ABS_USD,
    QL_CS01_REL_TOL,
    QL_HAZARD_BP,
    QL_PAR_SPREAD_BP,
    QL_UPFRONT_BP,
    assert_output_current,
)
from tests.test_legs import RATES_FILE

ROOT = Path(__file__).resolve().parent.parent
CURVES_DIR = ROOT / "data" / "curves"
NAMED_CURVES = ("IG_flat", "HY_steep", "distressed_inverted")

BP_PER_UNIT = 1e4
PERCENT = 100.0

# Criterion 2, the bar not met (review 07, Against the plan): on the
# distressed curve the hazard QuantLib's curve carries over our 1Y and 2Y
# pillar intervals differs from ours by 0.54 and 0.51 bp against the 0.5 bp
# bar, because QuantLib's nodes sit 2 days after the 6M and 1Y maturities
# (both 20ths are Sundays) and the hazard drops 6 points across them. With
# our fit moved onto QuantLib's nodes every pillar agrees to solver
# precision, which is the test below this one.
DISTRESSED_NODE_OFFSET_PILLARS = ("1Y", "2Y")

# The helper's settlementDays that reproduces our step-in; 3 (the cash
# settlement lag) would start protection two days late, and the test shows
# the 6M hazard is then off by more than the bar on every curve.
HELPER_SETTLEMENT_DAYS = 1
WRONG_SETTLEMENT_DAYS = 3

ONE_DAY = timedelta(days=1)


@pytest.fixture(scope="module")
def discount() -> DiscountCurve:
    return discount_curve_from_file(RATES_FILE)


@pytest.fixture(scope="module")
def results(discount: DiscountCurve) -> dict[str, BootstrapResult]:
    return {label: bootstrap(market_curve_quotes_from_file(CURVES_DIR / f"{label}.json"), discount) for label in NAMED_CURVES}


@pytest.fixture(scope="module")
def rows(results: dict[str, BootstrapResult], discount: DiscountCurve) -> list[qc.Row]:
    return qc.validation_rows(results, discount)


def _rows(rows: list[qc.Row], **match) -> list[qc.Row]:
    return [r for r in rows if all(getattr(r, k) == v for k, v in match.items())]


def test_table_2_tolerances_are_the_plans() -> None:
    assert qc.TOL_UPFRONT_BP == QL_UPFRONT_BP
    assert qc.TOL_PAR_SPREAD_BP == QL_PAR_SPREAD_BP
    assert qc.TOL_HAZARD_BP == QL_HAZARD_BP
    assert qc.TOL_ANNUITY == QL_ANNUITY_ABS_TOL
    assert qc.TOL_CS01_REL == QL_CS01_REL_TOL and qc.TOL_CS01_USD == QL_CS01_ABS_USD
    assert qc.QL_FLAGS["numerical_fix"] == "Taylor"
    assert qc.QL_FLAGS["accrual_bias"] == "HalfDayBias"
    assert qc.QL_FLAGS["forwards_in_coupon_period"] == "Piecewise"
    assert qc.QL_FLAGS["helper_settlement_days"] == HELPER_SETTLEMENT_DAYS


# --- criterion 1: the pricer ---------------------------------------------------


@pytest.mark.parametrize("label,tenor,coupon_bp", qc.TRADES, ids=[f"{c}-{t}-c{k:g}" for c, t, k in qc.TRADES])
def test_pricer_matches_quantlib_on_our_curves(rows: list[qc.Row], label: str, tenor: str, coupon_bp: float) -> None:
    trade = qc.trade_label(tenor, coupon_bp)
    by_metric = {r.metric: r for r in _rows(rows, curve=label, trade=trade)}
    assert set(by_metric) == {"clean_upfront_pct", "par_spread_bp", "pv_protection", "risky_annuity", *({"cs01_usd"} if tenor == qc.CS01_TENOR else set())}
    assert abs(by_metric["clean_upfront_pct"].diff) <= QL_UPFRONT_BP  # bp of notional
    assert abs(by_metric["par_spread_bp"].diff) <= QL_PAR_SPREAD_BP
    assert abs(by_metric["pv_protection"].diff) <= QL_UPFRONT_BP  # bp of notional
    assert abs(by_metric["risky_annuity"].diff) <= QL_ANNUITY_ABS_TOL
    for metric in ("clean_upfront_pct", "par_spread_bp", "pv_protection", "risky_annuity"):
        assert by_metric[metric].passed


# --- criterion 2: the bootstrap ------------------------------------------------


@pytest.mark.parametrize("label", NAMED_CURVES)
def test_bootstrap_hazards_match_quantlib_on_our_pillar_grid(rows: list[qc.Row], label: str) -> None:
    """QuantLib's curve read on our pillar intervals against our hazards;
    the distressed 1Y and 2Y excess over the bar is pinned."""
    hazard_rows = _rows(rows, curve=label, trade="bootstrap")
    assert [r.metric for r in hazard_rows] == [f"hazard_pct_{p}" for p in PILLARS]
    failing = tuple(p for p, r in zip(PILLARS, hazard_rows) if not r.passed)
    if label == "distressed_inverted":
        assert failing == DISTRESSED_NODE_OFFSET_PILLARS
        for p, r in zip(PILLARS, hazard_rows):
            assert abs(r.diff) <= (QL_HAZARD_BP if p not in failing else 2 * QL_HAZARD_BP), p
    else:
        assert failing == ()
        assert max(abs(r.diff) for r in hazard_rows) <= QL_HAZARD_BP
    own = _rows(rows, curve=label, metric="clean_upfront_pct")
    own = [r for r in own if r.trade.endswith("_own_bootstrap")]
    assert len(own) == 1 and abs(own[0].diff) <= QL_UPFRONT_BP and own[0].passed


@pytest.mark.parametrize("label", NAMED_CURVES)
def test_bootstrap_matches_quantlib_with_the_nodes_matched(rows: list[qc.Row], results: dict[str, BootstrapResult], discount: DiscountCurve, label: str) -> None:
    """Our sequential fit with its nodes on QuantLib's dates (adjusted
    maturity + 1 day) against QuantLib's node hazards: every pillar within
    the bar, on every curve, and in fact to solver precision."""
    matched = _rows(rows, curve=label, trade="bootstrap_quantlib_nodes")
    assert [r.metric for r in matched] == [f"hazard_pct_{p}" for p in PILLARS]
    assert max(abs(r.diff) for r in matched) <= QL_HAZARD_BP
    assert max(abs(r.diff) for r in matched) <= BOOTSTRAP_REPRICE_BP  # the two fits are the same fit
    assert all(r.passed for r in matched)
    r = results[label]
    theirs = qc.ql_bootstrap(r.quotes, discount, r.conventional_spreads_bp, r.pillar_dates)
    assert theirs.node_dates == tuple(adjust_following(d) + ONE_DAY for d in r.pillar_dates)
    assert all(d != n for d, n in zip(r.pillar_dates, theirs.node_dates))


@pytest.mark.parametrize("label", NAMED_CURVES)
def test_helper_settlement_days_is_the_step_in_not_the_cash_settlement(results: dict[str, BootstrapResult], discount: DiscountCurve, label: str) -> None:
    r = results[label]
    right = qc.ql_bootstrap(r.quotes, discount, r.conventional_spreads_bp, r.pillar_dates, settlement_days=HELPER_SETTLEMENT_DAYS)
    wrong = qc.ql_bootstrap(r.quotes, discount, r.conventional_spreads_bp, r.pillar_dates, settlement_days=WRONG_SETTLEMENT_DAYS)
    assert abs(BP_PER_UNIT * (right.pillar_hazards[0] - r.pillar_hazards[0])) <= BOOTSTRAP_REPRICE_BP  # 6M has no node before it
    assert abs(BP_PER_UNIT * (wrong.pillar_hazards[0] - r.pillar_hazards[0])) > QL_HAZARD_BP


# --- criterion 3: CS01 ---------------------------------------------------------


@pytest.mark.parametrize("label", NAMED_CURVES)
def test_5y_cs01_matches_quantlib(rows: list[qc.Row], label: str) -> None:
    (row,) = _rows(rows, curve=label, metric="cs01_usd")
    assert row.tolerance == max(QL_CS01_REL_TOL * abs(row.ours), QL_CS01_ABS_USD)
    assert abs(row.diff) <= row.tolerance and row.passed
    assert row.ours > 0.0  # the buyer gains when the spread widens
    # In bp of notional: the same comparison, the same verdict.
    assert abs(row.diff) / row.ours <= QL_CS01_REL_TOL or abs(row.diff) <= QL_CS01_ABS_USD


# --- criterion 4: Tables 2 and 5 -----------------------------------------------


def test_table_2_is_current_and_every_row_has_pass(rows: list[qc.Row], tmp_path: Path) -> None:
    fresh = report.table_2_quantlib_validation(rows, out_dir=tmp_path)
    assert tuple(fresh.columns) == report.TABLE_2_COLUMNS
    assert fresh["pass"].dtype == bool and fresh["pass"].notna().all()
    committed = report.TABLES_DIR / "table_2_quantlib_validation.csv"
    assert_output_current(tmp_path / "table_2_quantlib_validation.csv", committed)
    assert (tmp_path / "table_2_quantlib_validation.md").read_text(encoding="utf-8") == committed.with_suffix(".md").read_text(encoding="utf-8")
    table = pd.read_csv(committed)
    assert set(table["metric"]) >= {"clean_upfront_pct", "par_spread_bp", "cs01_usd", "pv_protection", "risky_annuity"}
    assert all(m.startswith("hazard_pct_") for m in table["metric"] if m not in {"clean_upfront_pct", "par_spread_bp", "cs01_usd", "pv_protection", "risky_annuity"})
    failing = table.loc[~table["pass"], ["curve", "trade", "metric"]].itertuples(index=False, name=None)
    assert set(failing) == {("distressed_inverted", "bootstrap", f"hazard_pct_{p}") for p in DISTRESSED_NODE_OFFSET_PILLARS}


def test_table_5_is_current_and_the_textbook_spread_is_the_triangle(results: dict[str, BootstrapResult], discount: DiscountCurve, tmp_path: Path) -> None:
    fresh = report.table_5_isda_vs_textbook([results[k] for k in NAMED_CURVES], discount, out_dir=tmp_path)
    assert tuple(fresh.columns) == report.TABLE_5_COLUMNS
    assert len(fresh) == len(NAMED_CURVES) * len(report.TABLE_5_TENORS)
    committed = report.TABLES_DIR / "table_5_isda_vs_textbook.csv"
    assert_output_current(tmp_path / "table_5_isda_vs_textbook.csv", committed)
    assert (tmp_path / "table_5_isda_vs_textbook.md").read_text(encoding="utf-8") == committed.with_suffix(".md").read_text(encoding="utf-8")
    for row in fresh.itertuples(index=False):
        r = results[row.curve]
        i = PILLARS.index(row.tenor)
        # The ISDA par spread of a pillar contract is the pillar's conventional spread.
        assert abs(row.isda_par_spread_bp - r.conventional_spreads_bp[i]) <= BOOTSTRAP_REPRICE_BP
        # The textbook spread is the triangle at the flat hazard calibrated on
        # the ISDA path, which sits above the act/360 clean spread (review 06).
        assert row.textbook_par_spread_bp > row.isda_par_spread_bp
        assert abs(row.diff_par_bp - (row.isda_par_spread_bp - row.textbook_par_spread_bp)) < PRICER_IDENTITY_ABS_TOL
        assert abs(row.diff_bp - BP_PER_UNIT / PERCENT * (row.isda_clean_upfront_pct - row.textbook_upfront_pct)) < PRICER_IDENTITY_ABS_TOL
