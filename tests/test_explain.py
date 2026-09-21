"""Section 9: the P&L explain (BUILD_PLAN.md Section 9, criteria 1, 2 and
5), Table 4 and Chart 3.

The states are the Section 6 curves bootstrapped on the Section 2 discount
curve; the scenario states come from cds.scenarios and the sensitivities
from cds.explain.sensitivities, computed once per curve.
"""

from __future__ import annotations

import math
from dataclasses import fields, replace
from datetime import timedelta
from pathlib import Path

import matplotlib.image
import numpy as np
import pandas as pd
import pytest

from cds import report
from cds.bootstrap import BootstrapResult, bootstrap, market_curve_quotes_from_file, market_state, pillar_trade
from cds.conventions import DEFAULT_NOTIONAL, PILLARS
from cds.curves import DiscountCurve, discount_curve_from_file
from cds.explain import EXPLAIN_ZERO_USD, Sensitivities, explain, gamma_parallel, rates_move_bp, sensitivities, spread_moves_bp
from cds.pricer import price
from cds.risk import BUMP_RECOVERY, BUMP_SPREAD_BP, add_calendar_months, recovery_state, risk, shifted_state, spread_bumped_state, theta
from cds.scenarios import combined_scenario, parallel_scenario, rates_scenario, recovery_scenario, run, scenario_state, scenario_states, spread_scenario, standard_grid, sweep_grid
from cds.types import CDSTrade, ExplainResult
from tests.conftest import (
    EXPLAIN_RESIDUAL_PCT,
    EXPLAIN_X3_GAMMA_REMOVES_FRACTION,
    EXPLAIN_X3_RESIDUAL_MIN_PCT,
    PRICER_IDENTITY_ABS_TOL,
    SENSITIVITY_RECOMPUTE_ABS_USD,
    assert_output_current,
    assert_output_value,
)
from tests.test_legs import RATES_FILE

ROOT = Path(__file__).resolve().parent.parent
CURVES_DIR = ROOT / "data" / "curves"
CURVES = ("IG_flat", "HY_steep")
COUPONS_BP = report.STANDARD_COUPONS_BY_CURVE

# Criteria 1 and 2: the parallel moves.
SMALL_MOVE_BP = 10.0
LARGE_MOVE_BP = 100.0

# Chart 3 geometry.
CHART_SIZE = (900, 1600)
ONE_DAY = timedelta(days=1)


@pytest.fixture(scope="module")
def discount() -> DiscountCurve:
    return discount_curve_from_file(RATES_FILE)


@pytest.fixture(scope="module")
def results(discount: DiscountCurve) -> dict[str, BootstrapResult]:
    return {label: bootstrap(market_curve_quotes_from_file(CURVES_DIR / f"{label}.json"), discount) for label in CURVES}


def _five_year(r: BootstrapResult, coupon_bp: float, side: str = "buy") -> CDSTrade:
    return replace(pillar_trade(r.quotes, r.quotes.pillars.index("5Y"), coupon_bp), side=side)


@pytest.fixture(scope="module")
def sens(results: dict[str, BootstrapResult], discount: DiscountCurve) -> dict[str, Sensitivities]:
    return {label: sensitivities(market_state(r, discount), _five_year(r, COUPONS_BP[label]), spreads_bp=r.conventional_spreads_bp) for label, r in results.items()}


def _explain(results, discount, sens, label: str, scenario, side: str = "buy") -> ExplainResult:
    r = results[label]
    state = market_state(r, discount)
    trade = _five_year(r, COUPONS_BP[label], side)
    s1 = scenario_state(state, scenario, spreads_bp=r.conventional_spreads_bp)
    return explain(state, s1, trade, sensitivities_t0=sens[label] if side == "buy" else None)


# --- criterion 1: a 10 bp parallel move is explained to 2% -----------------------------


@pytest.mark.parametrize("label", CURVES)
def test_residual_under_2pct_on_a_10bp_parallel_move(results, discount, sens, label: str) -> None:
    e = _explain(results, discount, sens, label, parallel_scenario(SMALL_MOVE_BP))
    assert abs(e.residual_pct_of_total) < EXPLAIN_RESIDUAL_PCT
    assert e.residual == pytest.approx(e.pnl_full - (e.pnl_spread_first_order + e.pnl_spread_gamma + e.pnl_recovery + e.pnl_rates + e.pnl_theta + e.pnl_cross))
    assert e.residual_pct_of_total == pytest.approx(100.0 * e.residual / e.pnl_full)
    rep = sens[label].report
    assert e.pnl_spread_first_order == pytest.approx(SMALL_MOVE_BP * rep.cs01_bucket_sum)
    assert e.pnl_recovery == 0.0 and e.pnl_rates == 0.0 and e.pnl_theta == 0.0 and e.pnl_cross == 0.0
    assert e.pnl_full > 0.0  # the buyer gains when spreads widen


# --- criterion 2: the gamma sign --------------------------------------------------------------


@pytest.mark.parametrize("label", CURVES)
def test_gamma_is_negative_for_the_buyer_on_a_100bp_parallel_move(results, discount, sens, label: str) -> None:
    rep = sens[label].report
    # Gamma = V(s+1) - 2V(s) + V(s-1) = 2 (cs01_parallel - cs01_central_parallel): the central CS01
    # sits above the one-sided one, so Gamma is negative and the buyer is short convexity.
    assert sens[label].gamma == gamma_parallel(rep) == 2.0 * (rep.cs01_parallel - rep.cs01_central_parallel)
    assert sens[label].gamma < 0.0
    e = _explain(results, discount, sens, label, parallel_scenario(LARGE_MOVE_BP))
    assert e.pnl_spread_gamma < 0.0
    assert e.pnl_spread_gamma == pytest.approx(0.5 * sens[label].gamma * LARGE_MOVE_BP**2)
    # The full revaluation is below the first-order line: concave in spread.
    assert e.pnl_full < e.pnl_spread_first_order
    assert abs(e.residual) < abs(e.pnl_full - e.pnl_spread_first_order)  # the gamma term explains most of the gap
    # The seller's gamma is the negative.
    seller = _explain(results, discount, sens, label, parallel_scenario(LARGE_MOVE_BP), side="sell")
    assert seller.pnl_spread_gamma == pytest.approx(-e.pnl_spread_gamma, rel=1e-9)
    assert seller.pnl_full == pytest.approx(-e.pnl_full, abs=PRICER_IDENTITY_ABS_TOL * DEFAULT_NOTIONAL)


def test_gamma_from_the_report_is_the_second_difference_of_the_parallel_bump(results, discount, sens) -> None:
    r = results["IG_flat"]
    state = market_state(r, discount)
    trade = _five_year(r, 100.0)
    spreads = r.conventional_spreads_bp
    n = len(spreads)
    up = price(spread_bumped_state(state, (BUMP_SPREAD_BP,) * n, spreads_bp=spreads), trade).mtm
    down = price(spread_bumped_state(state, (-BUMP_SPREAD_BP,) * n, spreads_bp=spreads), trade).mtm
    base = price(state, trade).mtm
    assert sens["IG_flat"].gamma == pytest.approx(up - 2.0 * base + down, abs=SENSITIVITY_RECOMPUTE_ABS_USD)


# --- criterion 5: the x3 scenario on HY --------------------------------------------------


def test_x3_spread_scenario_residual_on_hy_is_material(results, discount, sens) -> None:
    """Criterion 5 as restated (item 49): first order alone leaves a
    residual over 5% of pnl_full (26%), and the gamma term removes at least
    half of it (leaving 3.2%)."""
    e = _explain(results, discount, sens, "HY_steep", spread_scenario(3.0))
    first_order_only = 100.0 * (e.pnl_full - e.pnl_spread_first_order) / e.pnl_full
    assert abs(first_order_only) > EXPLAIN_X3_RESIDUAL_MIN_PCT
    assert abs(e.residual_pct_of_total) <= (1.0 - EXPLAIN_X3_GAMMA_REMOVES_FRACTION) * abs(first_order_only)
    assert e.residual == pytest.approx(e.pnl_full - e.pnl_spread_first_order - e.pnl_spread_gamma)  # the other terms are zero
    assert e.pnl_full < e.pnl_spread_first_order and e.pnl_spread_gamma < 0.0


# --- the other terms ----------------------------------------------------------------------------------


def test_recovery_rates_and_cross_terms_carry_the_report_sensitivities(results, discount, sens) -> None:
    r = results["IG_flat"]
    rep = sens["IG_flat"].report
    rec = _explain(results, discount, sens, "IG_flat", recovery_scenario(0.20))
    assert rec.pnl_recovery == pytest.approx(rep.rec01 * -20.0) and rec.pnl_spread_first_order == 0.0 and rec.pnl_cross == 0.0
    rates = _explain(results, discount, sens, "IG_flat", rates_scenario(100.0))
    assert rates.pnl_rates == pytest.approx(rep.ir01 * 100.0) and rates.pnl_spread_first_order == 0.0
    assert abs(rates.residual) < abs(rates.pnl_full)
    combined = _explain(results, discount, sens, "IG_flat", combined_scenario(0.40))
    ds = np.mean(np.array(r.conventional_spreads_bp))  # x2: Delta s_i = s_i, the average
    assert combined.pnl_cross == pytest.approx(sens["IG_flat"].cross * ds * -20.0)
    assert combined.pnl_spread_gamma == pytest.approx(0.5 * sens["IG_flat"].gamma * ds**2)
    assert combined.pnl_recovery == rec.pnl_recovery and combined.pnl_rates == pytest.approx(-rates.pnl_rates)
    # The cross term is the joint second difference, computed here from its four values.
    state = market_state(r, discount)
    trade = _five_year(r, 100.0)
    spreads = r.conventional_spreads_bp
    r_up = trade.recovery + BUMP_RECOVERY
    joint = recovery_state(spread_bumped_state(state, (BUMP_SPREAD_BP,) * len(spreads), spreads_bp=spreads), r_up, hazard_fixed=False, spreads_bp=tuple(s + BUMP_SPREAD_BP for s in spreads))
    v_joint = price(joint, replace(trade, recovery=r_up)).mtm
    v_s = price(spread_bumped_state(state, (BUMP_SPREAD_BP,) * len(spreads), spreads_bp=spreads), trade).mtm
    v_r = price(recovery_state(state, r_up, hazard_fixed=False, spreads_bp=spreads), replace(trade, recovery=r_up)).mtm
    assert sens["IG_flat"].cross == pytest.approx(v_joint - v_s - v_r + rep.mtm, abs=SENSITIVITY_RECOMPUTE_ABS_USD)


def test_explain_pnl_full_is_the_vectorised_grids_pnl(results, discount, sens) -> None:
    r = results["IG_flat"]
    state = market_state(r, discount)
    trade = _five_year(r, 100.0)
    grid = standard_grid(0.40)
    states = scenario_states(state, grid, spreads_bp=r.conventional_spreads_bp)
    frame = run(state, trade, grid, states=states)
    for scenario, s1, pnl in zip(grid, states, frame["pnl_full"]):
        e = explain(state, s1, trade, sensitivities_t0=sens["IG_flat"])
        assert e.pnl_full == pytest.approx(pnl, abs=PRICER_IDENTITY_ABS_TOL * DEFAULT_NOTIONAL), scenario.name
    base = explain(state, states[2], trade, sensitivities_t0=sens["IG_flat"])  # spread_x1
    assert abs(base.pnl_full) < EXPLAIN_ZERO_USD and math.isnan(base.residual_pct_of_total)


def test_theta_term_over_a_date_gap(results, discount, sens) -> None:
    """t_1 one day and one month on: with the curves rolled in tenor the
    whole P&L is theta-rolldown, the explain's theta is theta-calendar and
    the residual their difference; with the curves fixed on their dates the
    residual is zero. The 1-month window holds the 21 Sep coupon."""
    r = results["IG_flat"]
    state = market_state(r, discount)
    trade = _five_year(r, 100.0)
    rep = sens["IG_flat"].report
    for t1, cal, roll in ((state.as_of + ONE_DAY, rep.theta_calendar_1d, rep.theta_rolldown_1d), (add_calendar_months(state.as_of, 1), rep.theta_calendar_1m, rep.theta_rolldown_1m)):
        tenor = explain(state, shifted_state(state, t1, "tenor"), trade, sensitivities_t0=sens["IG_flat"])
        assert tenor.pnl_theta == pytest.approx(cal) and tenor.pnl_full == pytest.approx(roll)
        assert tenor.pnl_spread_first_order == 0.0 and tenor.pnl_rates == 0.0 and tenor.pnl_recovery == 0.0
        assert tenor.residual == pytest.approx(roll - cal)
        calendar = explain(state, shifted_state(state, t1, "calendar"), trade, sensitivities_t0=sens["IG_flat"])
        assert calendar.pnl_full == pytest.approx(cal) and calendar.residual == pytest.approx(0.0, abs=SENSITIVITY_RECOMPUTE_ABS_USD)
        assert calendar.pnl_theta == pytest.approx(theta(state, trade, t1, "calendar"))
    with pytest.raises(ValueError):
        explain(shifted_state(state, state.as_of + ONE_DAY, "tenor"), state, trade)


def test_explain_refuses_a_rates_move_it_cannot_read_and_a_wrong_recovery(results, discount, sens) -> None:
    r = results["IG_flat"]
    state = market_state(r, discount)
    trade = _five_year(r, 100.0)
    t1 = state.as_of + ONE_DAY
    moved = shifted_state(state, t1, "calendar")
    bare = replace(moved, discount=DiscountCurve(as_of=t1, node_dates=moved.discount.node_dates, node_dfs=tuple(p * 0.999 for p in moved.discount.node_dfs)))
    with pytest.raises(ValueError):
        rates_move_bp(state, bare)
    assert rates_move_bp(state, moved) == 0.0
    up = scenario_state(state, rates_scenario(100.0), spreads_bp=r.conventional_spreads_bp)
    assert rates_move_bp(state, up) == pytest.approx(100.0)
    assert spread_moves_bp(state, up, r.conventional_spreads_bp) == (0.0,) * len(PILLARS)
    with pytest.raises(ValueError):
        explain(state, up, replace(trade, recovery=0.41))


def test_sensitivities_take_a_precomputed_report(results, discount, sens) -> None:
    r = results["HY_steep"]
    state = market_state(r, discount)
    trade = _five_year(r, 500.0)
    rep = risk(state, trade)
    fresh = sensitivities(state, trade, report=rep, spreads_bp=r.conventional_spreads_bp)
    assert fresh.report is rep and fresh.gamma == sens["HY_steep"].gamma and fresh.cross == pytest.approx(sens["HY_steep"].cross)
    assert fresh.spreads_bp == r.conventional_spreads_bp


def test_explain_result_fields_are_the_plans_in_order() -> None:
    names = [f.name for f in fields(ExplainResult)]
    assert names == ["pnl_full", "pnl_spread_first_order", "pnl_spread_gamma", "pnl_recovery", "pnl_rates", "pnl_theta", "pnl_cross", "residual", "residual_pct_of_total"]
    assert report.TABLE_4_COLUMNS == ("scenario", *names)
    assert report.CHART_3_COLUMNS == ("spread_multiplier", "pnl_full", "pnl_first_order", "pnl_second_order")


# --- Table 4 and Chart 3 --------------------------------------------------------------------


def test_table_4_is_current_and_has_the_fixed_columns(results, discount, sens, tmp_path: Path) -> None:
    r = results[report.TABLE_4_CURVE]
    rows = report.explain_grid(r, discount, sens=sens[report.TABLE_4_CURVE])
    six = report.table_4_pnl_explain(r, discount, out_dir=tmp_path, rows=rows)
    full = report.table_4_pnl_explain_full(r, discount, out_dir=tmp_path, rows=rows)
    assert tuple(six.columns) == tuple(full.columns) == report.TABLE_4_COLUMNS
    assert list(six["scenario"]) == list(report.TABLE_4_SCENARIOS) == ["spread_x1.5", "spread_x3", "recovery_0.2", "steepen_35bp", "rates_+100bp", "combined"]
    assert list(full["scenario"]) == [g.name for g in standard_grid(0.40)]
    for stem in ("table_4_pnl_explain", "table_4_pnl_explain_full"):
        committed = report.TABLES_DIR / f"{stem}.csv"
        assert_output_current(tmp_path / f"{stem}.csv", committed)
    # The six rows are the full table's rows.
    by = full.set_index("scenario")
    for row in six.itertuples(index=False):
        for f in fields(ExplainResult):
            a, b = getattr(row, f.name), by.loc[row.scenario, f.name]
            assert (math.isnan(a) and math.isnan(b)) or a == b
    assert math.isnan(by.loc["spread_x1", "residual_pct_of_total"])
    committed_full = pd.read_csv(report.TABLES_DIR / "table_4_pnl_explain_full.csv")
    assert committed_full["residual_pct_of_total"].isna().sum() == 1


def test_chart_3_is_current_1600_by_900_and_shows_the_concavity(results, discount, sens, tmp_path: Path) -> None:
    r = results[report.CHART_3_CURVE]
    fresh = report.chart_3_pnl_vs_spread_shock(r, discount, out_dir=tmp_path, sens=sens[report.CHART_3_CURVE])
    assert tuple(fresh.columns) == report.CHART_3_COLUMNS and len(fresh) == 71
    assert list(fresh["spread_multiplier"]) == [g.spread_multiplier for g in sweep_grid()]
    assert_output_current(tmp_path / "chart_3_pnl_vs_spread_shock.csv", report.CHARTS_DIR / "chart_3_pnl_vs_spread_shock.csv")
    png = matplotlib.image.imread(report.CHARTS_DIR / "chart_3_pnl_vs_spread_shock.png")
    assert png.shape[:2] == CHART_SIZE
    by = fresh.set_index("spread_multiplier")
    # First order is linear in the multiplier through zero at m = 1; the second-order line is below it away from 1.
    m = fresh["spread_multiplier"].to_numpy()
    slope = fresh["pnl_first_order"].to_numpy() / np.where(m == 1.0, np.nan, m - 1.0)
    assert np.nanstd(slope) < 1e-6 * np.nanmean(np.abs(slope))
    assert abs(by.loc[1.0, "pnl_first_order"]) < 1e-6 and abs(by.loc[1.0, "pnl_full"]) < PRICER_IDENTITY_ABS_TOL * DEFAULT_NOTIONAL
    assert (fresh["pnl_second_order"].to_numpy()[m != 1.0] < fresh["pnl_first_order"].to_numpy()[m != 1.0]).all()
    # Full revaluation is concave: below first order on both sides, and the gamma line is closer to it than first order is at every m.
    gap_first = np.abs(fresh["pnl_full"] - fresh["pnl_first_order"]).to_numpy()
    gap_second = np.abs(fresh["pnl_full"] - fresh["pnl_second_order"]).to_numpy()
    assert (fresh["pnl_full"].to_numpy()[m != 1.0] < fresh["pnl_first_order"].to_numpy()[m != 1.0]).all()
    assert (gap_second[m != 1.0] < gap_first[m != 1.0]).all()
    # The x3 row is Table 4's x3 explain (one output against another: item 52's rule).
    committed = pd.read_csv(report.TABLES_DIR / "table_4_pnl_explain.csv").set_index("scenario")
    assert_output_value(by.loc[3.0, "pnl_full"], committed.loc["spread_x3", "pnl_full"], "chart 3 x3 pnl_full against table 4")
    assert_output_value(by.loc[3.0, "pnl_first_order"], committed.loc["spread_x3", "pnl_spread_first_order"], "chart 3 x3 first order against table 4")
    assert_output_value(by.loc[3.0, "pnl_second_order"], committed.loc["spread_x3", "pnl_spread_first_order"] + committed.loc["spread_x3", "pnl_spread_gamma"], "chart 3 x3 second order against table 4")
