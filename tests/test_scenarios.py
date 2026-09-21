"""Section 9: the scenario grid (BUILD_PLAN.md Section 9, criteria 3 and
4), cds.scenarios and the cds.legs array path.

The states are the Section 6 curves bootstrapped on the Section 2 discount
curve. The vectorised revaluation is compared with the scalar pricer on
every scenario it prices; the timing criterion is measured here.
"""

from __future__ import annotations

import time
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from cds import report
from cds.bootstrap import BootstrapResult, bootstrap, market_curve_quotes_from_file, market_state, pillar_trade
from cds.conventions import DEFAULT_NOTIONAL, PILLARS
from cds.curves import DiscountCurve, discount_curve_from_file, par_rate_from_curve
from cds.legs import CurveArrays, df_rows, leg_values, survival_rows
from cds.pricer import price, value
from cds.risk import rec01
from cds.scenarios import (
    CHART_3_MULTIPLIERS,
    RUN_COLUMNS,
    RUN_VALUE_COLUMNS,
    SPREAD_MULTIPLIERS,
    STATUS_OK,
    Scenario,
    combined_scenario,
    flatten_scenario,
    parallel_scenario,
    rates_scenario,
    recovery_scenario,
    revalue,
    run,
    scenario_spreads_bp,
    scenario_state,
    scenario_states,
    spread_scenario,
    standard_grid,
    steepen_scenario,
    sweep_grid,
)
from cds.schedule import cds_schedule
from cds.types import CDSTrade
from tests.conftest import BOOTSTRAP_REPRICE_BP, GRID_SECONDS, LEGS_VECTOR_ABS_TOL, OIS_REPRICE_BP, PRICER_IDENTITY_ABS_TOL
from tests.test_legs import RATES_FILE

ROOT = Path(__file__).resolve().parent.parent
CURVES_DIR = ROOT / "data" / "curves"
NAMED_CURVES = ("IG_flat", "HY_steep", "distressed_inverted")
COUPONS_BP = report.STANDARD_COUPONS_BY_CURVE

# Criterion 4: five random scenarios (a multiplier, a parallel shift, a
# recovery and a rates shift), drawn once with a fixed seed so the rows in
# the review can be reproduced; the ranges keep every curve bootstrappable.
RANDOM_SEED = 20260921
N_RANDOM = 5

# The x4 spread scenario does not bootstrap on HY (the 10Y pillar at 2400
# bp needs a forward hazard above the 500% bound: the hazard-cap ValueError)
# or on distressed (the 5Y pillar at 4800 bp needs a negative hazard:
# BootstrapArbitrageError); review 09 records both. run() writes the row
# with the error's class as its status (item 50).
FAILING = {"HY_steep": {"spread_x4": "ValueError"}, "distressed_inverted": {"spread_x4": "BootstrapArbitrageError"}}


@pytest.fixture(scope="module")
def discount() -> DiscountCurve:
    return discount_curve_from_file(RATES_FILE)


@pytest.fixture(scope="module")
def results(discount: DiscountCurve) -> dict[str, BootstrapResult]:
    return {label: bootstrap(market_curve_quotes_from_file(CURVES_DIR / f"{label}.json"), discount) for label in NAMED_CURVES}


def _five_year(r: BootstrapResult, coupon_bp: float, side: str = "buy") -> CDSTrade:
    return replace(pillar_trade(r.quotes, r.quotes.pillars.index("5Y"), coupon_bp), side=side)


def _random_grid() -> tuple[Scenario, ...]:
    rng = np.random.default_rng(RANDOM_SEED)
    out = []
    for k in range(N_RANDOM):
        out.append(
            Scenario(
                name=f"random_{k}",
                spread_multiplier=float(rng.uniform(0.6, 2.0)),
                spread_shifts_bp=(float(rng.uniform(-10.0, 30.0)),) * len(PILLARS),
                recovery=float(rng.uniform(0.1, 0.6)),
                rate_shift_bp=float(rng.uniform(-150.0, 150.0)),
            )
        )
    return tuple(out)


# --- the grid ----------------------------------------------------------------------------


def test_standard_grid_is_the_plans_fourteen_scenarios() -> None:
    grid = standard_grid(0.40)
    names = [g.name for g in grid]
    assert names == ["spread_x0.5", "spread_x0.75", "spread_x1", "spread_x1.5", "spread_x2", "spread_x3", "spread_x4", "recovery_0.2", "recovery_0.1", "steepen_35bp", "flatten_35bp", "rates_+100bp", "rates_-100bp", "combined"]
    assert [g.spread_multiplier for g in grid[:7]] == list(SPREAD_MULTIPLIERS)
    assert grid[7].recovery == 0.20 and grid[8].recovery == 0.10
    assert grid[9].spread_shifts_bp == (0.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0, 35.0)
    assert grid[10].spread_shifts_bp == tuple(-x for x in grid[9].spread_shifts_bp)
    assert (grid[11].rate_shift_bp, grid[12].rate_shift_bp) == (100.0, -100.0)
    combined = grid[13]
    assert (combined.spread_multiplier, combined.recovery, combined.rate_shift_bp) == (2.0, 0.20, -100.0)
    assert [g.name for g in standard_grid(0.25)][7:9] == ["recovery_0.125", "recovery_0.0625"]
    assert len(sweep_grid()) == 71 and CHART_3_MULTIPLIERS[0] == 0.5 and CHART_3_MULTIPLIERS[-1] == 4.0
    assert all(b - a == pytest.approx(0.05) for a, b in zip(CHART_3_MULTIPLIERS, CHART_3_MULTIPLIERS[1:]))
    assert all(len(set(g.name for g in grid)) == len(grid) for grid in (standard_grid(0.40), sweep_grid()))


def test_scenario_spreads_apply_the_multiplier_then_the_shift() -> None:
    spreads = (45.0, 50.0, 60.0, 70.0, 80.0, 90.0, 105.0, 120.0)
    assert scenario_spreads_bp(spread_scenario(2.0), spreads) == tuple(2.0 * s for s in spreads)
    assert scenario_spreads_bp(steepen_scenario(), spreads) == (45.0, 55.0, 70.0, 85.0, 100.0, 115.0, 135.0, 155.0)
    assert scenario_spreads_bp(flatten_scenario(), spreads) == (45.0, 45.0, 50.0, 55.0, 60.0, 65.0, 75.0, 85.0)
    assert scenario_spreads_bp(parallel_scenario(10.0), spreads) == tuple(s + 10.0 for s in spreads)
    assert scenario_spreads_bp(combined_scenario(0.40), spreads) == tuple(2.0 * s for s in spreads)
    assert scenario_spreads_bp(rates_scenario(100.0), spreads) == spreads
    with pytest.raises(ValueError):
        scenario_spreads_bp(Scenario(name="short", spread_shifts_bp=(1.0,)), spreads)
    with pytest.raises(ValueError):
        scenario_spreads_bp(flatten_scenario(step_bp=20.0), spreads)  # 10Y 120 - 140 < 0
    with pytest.raises(ValueError):
        Scenario(name="bad", recovery=1.5)


def test_scenario_state_is_the_bootstrap_of_the_transformed_inputs(results: dict[str, BootstrapResult], discount: DiscountCurve) -> None:
    r = results["IG_flat"]
    state = market_state(r, discount)
    combined = scenario_state(state, combined_scenario(r.quotes.recovery), spreads_bp=r.conventional_spreads_bp)
    assert combined.as_of == state.as_of and combined.recovery.R(0.0) == 0.20 and combined.quotes.recovery == 0.20
    assert tuple(q.value for q in combined.quotes.quotes) == tuple(2.0 * s for s in r.conventional_spreads_bp)
    assert combined.discount.par_rates_pct == tuple(x - 1.0 for x in discount.par_rates_pct)
    assert combined.discount.node_dates == discount.node_dates and combined.survival.pillar_dates == state.survival.pillar_dates
    # The scenario curve reprices its own spreads: the 5Y par spread is 180 bp.
    assert price(combined, replace(_five_year(r, 100.0), recovery=0.20)).par_spread_bp == pytest.approx(180.0, abs=BOOTSTRAP_REPRICE_BP)
    # The base scenario is the base state.
    base = scenario_state(state, spread_scenario(1.0), spreads_bp=r.conventional_spreads_bp)
    assert base.survival.pillar_hazards == state.survival.pillar_hazards  # the same inputs, the same Brent solves
    assert base.discount is state.discount
    # Rates rebuilt once per distinct shift.
    states = scenario_states(state, (rates_scenario(100.0), rates_scenario(100.0), rates_scenario(-100.0)), spreads_bp=r.conventional_spreads_bp)
    assert states[0].discount is states[1].discount and states[2].discount is not states[0].discount


@pytest.mark.parametrize("label", NAMED_CURVES)
def test_the_grid_runs_on_every_curve_and_skips_the_scenarios_it_cannot_bootstrap(results: dict[str, BootstrapResult], discount: DiscountCurve, label: str) -> None:
    """Item 50: run() with the default on_error = "skip" writes every
    scenario of the standard grid; the ones that do not bootstrap carry
    the error's class in status and nan in the value columns, and
    on_error = "raise" propagates the error naming the scenario."""
    r = results[label]
    state = market_state(r, discount)
    trade = _five_year(r, COUPONS_BP[label])
    grid = standard_grid(r.quotes.recovery)
    failing = FAILING.get(label, {})
    for name in failing:
        with pytest.raises(ValueError, match=name):
            scenario_state(state, next(g for g in grid if g.name == name), spreads_bp=r.conventional_spreads_bp)
        with pytest.raises(ValueError, match=name):
            run(state, trade, grid, spreads_bp=r.conventional_spreads_bp, on_error="raise")
    df = run(state, trade, grid, spreads_bp=r.conventional_spreads_bp)
    assert tuple(df.columns) == RUN_COLUMNS and list(df["scenario"]) == [g.name for g in grid]
    by = df.set_index("scenario")
    assert dict(by.loc[list(failing), "status"]) == failing
    assert (by["status"] == STATUS_OK).sum() == len(grid) - len(failing)
    for name in failing:
        assert by.loc[name, list(RUN_VALUE_COLUMNS)].isna().all()
        # The inputs are still written: x4 spreads, the curve's R, no rate shift.
        assert by.loc[name, "spread_5y_bp"] == 4.0 * r.conventional_spreads_bp[5] and by.loc[name, "recovery"] == r.quotes.recovery
    assert df.loc[df["status"] == STATUS_OK, list(RUN_VALUE_COLUMNS)].notna().all().all()
    ok = tuple(g for g in grid if g.name not in failing)
    by = by.loc[[g.name for g in ok]]
    with pytest.raises(ValueError):
        run(state, trade, ok, spreads_bp=r.conventional_spreads_bp, on_error="ignore")
    assert abs(by.loc["spread_x1", "pnl_full"]) < PRICER_IDENTITY_ABS_TOL * DEFAULT_NOTIONAL
    # The buyer gains as spreads widen, monotone in the multiplier.
    spread_rows = by.loc[[g.name for g in ok if g.name.startswith("spread_x")]]
    assert (np.diff(spread_rows["pnl_full"].to_numpy()) > 0).all()
    assert (spread_rows["par_spread_bp"].to_numpy() == pytest.approx(spread_rows["spread_multiplier"].to_numpy() * r.conventional_spreads_bp[5], abs=BOOTSTRAP_REPRICE_BP))
    # Steepen raises the 5Y spread by 25 bp and the buyer gains; flatten the reverse.
    assert by.loc["steepen_35bp", "pnl_full"] > 0.0 > by.loc["flatten_35bp", "pnl_full"]
    assert by.loc["steepen_35bp", "spread_5y_bp"] == r.conventional_spreads_bp[5] + 25.0
    # The recovery scenario carries the opposite sign of rec01 (R falls); zero on the HY par trade.
    r01 = rec01(state, trade, spreads_bp=r.conventional_spreads_bp)
    rec_name = f"recovery_{r.quotes.recovery * 0.5:g}"
    if abs(r01) > 1.0:
        assert np.sign(by.loc[rec_name, "pnl_full"]) == -np.sign(r01)  # R falls
    else:
        assert abs(by.loc[rec_name, "pnl_full"]) < 1.0
    assert by.loc[rec_name, "recovery"] == 0.5 * r.quotes.recovery
    assert by.loc["rates_+100bp", "rate_shift_bp"] == 100.0


# --- criterion 4: the vectorised legs equal the scalar path -----------------------


@pytest.mark.parametrize("label", NAMED_CURVES)
def test_vectorised_legs_equal_the_scalar_path_on_five_random_scenarios(results: dict[str, BootstrapResult], discount: DiscountCurve, label: str) -> None:
    r = results[label]
    state = market_state(r, discount)
    trade = _five_year(r, COUPONS_BP[label])
    grid = _random_grid()
    states = scenario_states(state, grid, spreads_bp=r.conventional_spreads_bp)
    assert len(states) == N_RANDOM
    v = revalue(state, trade, states)
    schedule = cds_schedule(trade.trade_date, trade.maturity)
    for k, s in enumerate(states):
        scalar = leg_values(s.discount, s.survival, s.recovery, schedule, s.as_of)
        for field in ("annuity_coupon", "annuity_accrual", "protection", "pv_protection"):
            assert abs(getattr(v.legs, field)[k] - getattr(scalar, field)) <= LEGS_VECTOR_ABS_TOL, (grid[k].name, field)
        scalar_v = value(s.discount, s.survival, s.recovery, replace(trade, recovery=s.recovery.R(0.0)), s.as_of)
        assert abs(v.d_settle[k] - scalar_v.d_settle) <= LEGS_VECTOR_ABS_TOL
        assert abs(v.dirty_upfront[k] - scalar_v.dirty_upfront) <= LEGS_VECTOR_ABS_TOL
        assert abs(v.par_spread_bp[k] - scalar_v.par_spread_bp) <= LEGS_VECTOR_ABS_TOL * 1e4
    df = run(state, trade, grid, states=states, spreads_bp=r.conventional_spreads_bp)
    for k, s in enumerate(states):
        assert df.loc[k, "mtm"] == pytest.approx(price(s, replace(trade, recovery=s.recovery.R(0.0))).mtm, abs=LEGS_VECTOR_ABS_TOL * DEFAULT_NOTIONAL)


def test_vectorised_legs_equal_the_scalar_path_on_the_grid_engine_too(results: dict[str, BootstrapResult], discount: DiscountCurve) -> None:
    r = results["IG_flat"]
    state = market_state(r, discount)
    trade = _five_year(r, 100.0)
    states = scenario_states(state, (spread_scenario(2.0), rates_scenario(50.0)), spreads_bp=r.conventional_spreads_bp)
    v = revalue(state, trade, states, engine="grid")
    schedule = cds_schedule(trade.trade_date, trade.maturity)
    for k, s in enumerate(states):
        scalar = leg_values(s.discount, s.survival, s.recovery, schedule, s.as_of, engine="grid")
        assert abs(v.legs.pv_protection[k] - scalar.pv_protection) <= LEGS_VECTOR_ABS_TOL
        assert abs(v.legs.annuity[k] - scalar.annuity) <= LEGS_VECTOR_ABS_TOL


def test_row_readers_reproduce_the_curve_classes(results: dict[str, BootstrapResult], discount: DiscountCurve) -> None:
    state = market_state(results["HY_steep"], discount)
    t = np.linspace(0.0, 12.0, 241)  # through the last node and beyond it
    hazards = np.array([state.survival.pillar_hazards, tuple(2.0 * h for h in state.survival.pillar_hazards)])
    q = survival_rows(state.survival.pillar_times, hazards, t)
    assert q.shape == (2, len(t))
    assert np.abs(q[0] - state.survival.Q(t)).max() <= LEGS_VECTOR_ABS_TOL
    doubled = replace(state.survival, pillar_hazards=tuple(2.0 * h for h in state.survival.pillar_hazards))
    assert np.abs(q[1] - doubled.Q(t)).max() <= LEGS_VECTOR_ABS_TOL
    dfs = np.array([discount.node_dfs, tuple(p**2 for p in discount.node_dfs)])
    p = df_rows(discount.node_times, dfs, t)
    assert np.abs(p[0] - discount.df(t)).max() <= LEGS_VECTOR_ABS_TOL
    squared = DiscountCurve(as_of=discount.as_of, node_dates=discount.node_dates, node_dfs=tuple(x**2 for x in discount.node_dfs))
    assert np.abs(p[1] - squared.df(t)).max() <= LEGS_VECTOR_ABS_TOL


def test_curve_arrays_and_leg_values_check_their_shapes(results: dict[str, BootstrapResult], discount: DiscountCurve) -> None:
    state = market_state(results["IG_flat"], discount)
    trade = _five_year(results["IG_flat"], 100.0)
    schedule = cds_schedule(trade.trade_date, trade.maturity)
    h, p = np.array([state.survival.pillar_hazards]), np.array([discount.node_dfs])
    with pytest.raises(ValueError):
        CurveArrays(hazards=h, node_dfs=p, recoveries=np.array([0.4, 0.4]))
    with pytest.raises(ValueError):
        CurveArrays(hazards=-h, node_dfs=p, recoveries=np.array([0.4]))
    with pytest.raises(ValueError):
        leg_values(state.discount, state.survival, state.recovery, schedule, state.as_of, arrays=CurveArrays(hazards=h[:, :-1], node_dfs=p, recoveries=np.array([0.4])))
    with pytest.raises(ValueError):
        leg_values(state.discount, state.survival, state.recovery, schedule, state.as_of, arrays=CurveArrays(hazards=h, node_dfs=p[:, :-1], recoveries=np.array([0.4])))
    # The n = 1 case is the scalar path.
    one = leg_values(state.discount, state.survival, state.recovery, schedule, state.as_of, arrays=CurveArrays(hazards=h, node_dfs=p, recoveries=np.array([0.4])))
    scalar = leg_values(state.discount, state.survival, state.recovery, schedule, state.as_of)
    assert one.pv_protection.shape == (1,) and abs(one.pv_protection[0] - scalar.pv_protection) <= LEGS_VECTOR_ABS_TOL
    # revalue refuses a state on other nodes; run refuses a state count that is not the grid's.
    fewer_nodes = DiscountCurve(as_of=discount.as_of, node_dates=discount.node_dates[1:], node_dfs=discount.node_dfs[1:])
    with pytest.raises(ValueError):
        revalue(state, trade, [replace(state, discount=fewer_nodes)])
    with pytest.raises(ValueError):
        run(state, trade, (spread_scenario(2.0),), states=[state, state])


# --- criterion 3: the grid in seconds ------------------------------------------------------


def test_sweep_plus_table_4_grid_revalues_in_under_ten_seconds(results: dict[str, BootstrapResult], discount: DiscountCurve) -> None:
    """71 sweep scenarios plus the 14 of the standard grid on IG: one
    bootstrap each, then one vectorised revaluation per grid."""
    r = results["IG_flat"]
    state = market_state(r, discount)
    trade = _five_year(r, 100.0)
    grids = (sweep_grid(), standard_grid(r.quotes.recovery))
    assert sum(len(g) for g in grids) == 85
    start = time.perf_counter()
    frames = [run(state, trade, g, spreads_bp=r.conventional_spreads_bp) for g in grids]
    elapsed = time.perf_counter() - start
    assert elapsed < GRID_SECONDS, elapsed
    assert len(frames[0]) == 71 and len(frames[1]) == 14
    assert (frames[0]["status"] == STATUS_OK).all() and (frames[1]["status"] == STATUS_OK).all()  # every IG scenario bootstraps
    # The sweep passes through the base with zero P&L and is increasing in the multiplier.
    sweep = frames[0].set_index("spread_multiplier")
    assert abs(sweep.loc[1.0, "pnl_full"]) < PRICER_IDENTITY_ABS_TOL * DEFAULT_NOTIONAL
    assert (np.diff(frames[0]["pnl_full"].to_numpy()) > 0).all()


def test_flat_discount_scenario_rates_reprice(results: dict[str, BootstrapResult], discount: DiscountCurve) -> None:
    """The rates scenario's discount curve reprices the shifted par rates."""
    r = results["IG_flat"]
    state = market_state(r, discount)
    up = scenario_state(state, rates_scenario(100.0), spreads_bp=r.conventional_spreads_bp).discount
    for tenor, rate in zip(discount.tenors, discount.par_rates_pct):
        assert par_rate_from_curve(up, tenor) == pytest.approx(rate + 1.0, abs=OIS_REPRICE_BP / 100.0)  # bp to percent


def test_make_outputs_knows_table_4_and_chart_3() -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location("make_outputs", ROOT / "scripts" / "make_outputs.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert {"table_4", "chart_3"} <= set(module.OUTPUTS)
