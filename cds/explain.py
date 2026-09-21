"""The P&L explain: the change in a trade's value between two market states
split into the first-order spread term, the spread gamma, the recovery,
rates and theta terms, the spread-recovery cross term and the unexplained
residual (BUILD_PLAN.md Section 9, SPEC 6.8).

explain(state_t0, state_t1, trade) returns an ExplainResult whose fields
are the Table 4 columns. With V the side's mtm from cds.pricer.price, the
sensitivities of cds.risk at t_0 in the side's currency, Delta s_i the
change in pillar i's conventional spread in bp (cds.bootstrap
.conventional_spreads_bp of each state's quotes: the quote of a par-spread
curve, the flat-hazard conversion of an upfront), Delta s the average of
the eight, Delta R the change in the assumed recovery in points (100 times
the change in R) and Delta r the change in the OIS par rates in bp (the
average over the tenors, a parallel move):

    pnl_full               = V(t_1) - V(t_0) - side * coupons paid on payment dates in (t_0, t_1]
    pnl_spread_first_order = sum_i cs01_i * Delta s_i
    pnl_spread_gamma       = 1/2 * Gamma * Delta s^2
    pnl_recovery           = rec01 * Delta R
    pnl_rates              = ir01 * Delta r
    pnl_theta              = theta_calendar over the date gap (0 when as_of is unchanged)
    pnl_cross              = C * Delta s * Delta R
    residual               = pnl_full - (the six above)
    residual_pct_of_total  = 100 * residual / pnl_full (nan when |pnl_full| is under EXPLAIN_ZERO_USD)

cs01_i is the one-sided per-pillar CS01 of RiskReport, rec01 the
re-bootstrapped recovery sensitivity (the desk number, item 40), ir01 the
parallel OIS bump; pnl_full includes the coupon cash of the window the way
theta does (docs/CONVENTIONS_RESOLVED.md item 7), so with a date gap the
whole P&L is measured against theta_calendar.

Gamma, sign convention. Gamma is the second derivative of the side's mtm
in the parallel spread, per bp squared, read as the central second
difference of the parallel bump at t_0:

    Gamma = V(s + 1) - 2 V(s) + V(s - 1)
          = 2 * (cs01_parallel - cs01_central_parallel)

since cs01_parallel = V(s + 1) - V(s) and cs01_central_parallel =
(V(s + 1) - V(s - 1)) / 2. For the protection buyer Gamma is negative:
the buyer's mtm is (s - c) A(s) and the risky annuity A falls as s rises,
so the mtm is concave in spread; the buyer is short convexity and CS01
shrinks as spreads widen, which is why the central CS01 sits above the
one-sided one (Section 8 criterion 6) and pnl_spread_gamma is negative for
the buyer on a +100 bp parallel move (Section 9 criterion 2, corrected in
docs/CONVENTIONS_RESOLVED.md). The seller's Gamma is the negative. Written
this way, 1/2 Gamma Delta s^2 carries the sign of the P&L directly;
"2 (central - one-sided)" is the same number with the opposite sign.

The cross term. C is the joint second difference per bp of spread and
point of recovery, from one extra bootstrap at (every s_i + 1 bp, R + 1
point) with the spreads held fixed and the curve re-bootstrapped, as rec01
and the parallel CS01 are:

    C = V(s + 1, R + 1) - V(s + 1, R) - V(s, R + 1) + V(s, R)
      = V(s + 1, R + 1) - V(s, R) - cs01_parallel - rec01.

Sensitivities. explain needs the risk report at t_0, Gamma and C, about
25 bootstraps; sensitivities(state_t0, trade) computes them once so a
grid of scenarios (Table 4, Chart 3) reuses them, and explain computes
them itself when not given.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

import numpy as np

from cds.bootstrap import bootstrap, conventional_spreads_bp, market_state
from cds.conventions import DEFAULT_CALENDAR
from cds.legs import Engine
from cds.pricer import SIDE_SIGN, price
from cds.risk import BUMP_RECOVERY, BUMP_SPREAD_BP, coupon_cash_in_window, risk, spread_quotes, theta
from cds.schedule import cds_schedule
from cds.types import CDSTrade, ExplainResult, MarketState, RiskReport

__all__ = [
    "EXPLAIN_ZERO_USD",
    "NODE_DF_ABS_TOL",
    "Sensitivities",
    "explain",
    "gamma_parallel",
    "rates_move_bp",
    "sensitivities",
    "spread_moves_bp",
]

PERCENT = 100.0

# Below this |pnl_full| the residual in percent of the total is not a
# number: the total is float noise (the x1 scenario).
EXPLAIN_ZERO_USD = 0.01

# A t_1 discount curve without par rates (a calendar-shifted one) is taken
# as an unchanged rates market when its node discount factors equal the
# calendar-shifted t_0 curve's to this; float noise on numbers near 1.
NODE_DF_ABS_TOL = 1e-12


@dataclass(frozen=True)
class Sensitivities:
    """What explain needs at t_0: the risk report, the base conventional
    spreads in bp, Gamma in $ per bp squared and the cross term C in $ per
    (bp times recovery point), all in the side's currency."""

    report: RiskReport
    spreads_bp: tuple[float, ...]
    gamma: float
    cross: float


def _kwargs(calendar: str, engine: Engine, half_day_bias: bool) -> dict:
    return {"calendar": calendar, "engine": engine, "half_day_bias": half_day_bias}


def gamma_parallel(report: RiskReport) -> float:
    """Gamma = 2 (cs01_parallel - cs01_central_parallel) = V(s+1) - 2V(s) + V(s-1)."""
    return 2.0 * (report.cs01_parallel - report.cs01_central_parallel)


def sensitivities(
    state: MarketState,
    trade: CDSTrade,
    *,
    report: RiskReport | None = None,
    spreads_bp: tuple[float, ...] | None = None,
    calendar: str = DEFAULT_CALENDAR,
    engine: Engine = "isda",
    half_day_bias: bool = True,
) -> Sensitivities:
    """The risk report (computed unless given), Gamma and the cross term C
    for the trade on the state."""
    kw = _kwargs(calendar, engine, half_day_bias)
    if spreads_bp is None:
        spreads_bp = conventional_spreads_bp(state.quotes, state.discount, **kw)
    if report is None:
        report = risk(state, trade, **kw)
    r_up = trade.recovery + BUMP_RECOVERY
    joint = market_state(bootstrap(spread_quotes(state.quotes, tuple(s + BUMP_SPREAD_BP for s in spreads_bp), r_up), state.discount, **kw), state.discount)
    v_joint = price(joint, replace(trade, recovery=r_up), **kw).mtm
    cross = v_joint - report.mtm - report.cs01_parallel - report.rec01
    return Sensitivities(report=report, spreads_bp=tuple(spreads_bp), gamma=gamma_parallel(report), cross=cross)


def spread_moves_bp(state_t0: MarketState, state_t1: MarketState, spreads_t0_bp: tuple[float, ...] | None = None, **kw) -> tuple[float, ...]:
    """Delta s_i: the change in each pillar's conventional spread, bp, the
    pillars matched by label."""
    if state_t0.quotes.pillars != state_t1.quotes.pillars:
        raise ValueError(f"the two states quote different pillars: {state_t0.quotes.pillars} and {state_t1.quotes.pillars}")
    s0 = conventional_spreads_bp(state_t0.quotes, state_t0.discount, **kw) if spreads_t0_bp is None else spreads_t0_bp
    s1 = conventional_spreads_bp(state_t1.quotes, state_t1.discount, **kw)
    return tuple(b - a for a, b in zip(s0, s1))


def rates_move_bp(state_t0: MarketState, state_t1: MarketState) -> float:
    """Delta r: the average change in the OIS par rates, bp. A t_1 curve
    without par rates counts as unchanged when its nodes are the
    calendar-shifted t_0 nodes; otherwise the move cannot be read and this
    raises."""
    d0, d1 = state_t0.discount, state_t1.discount
    if d1.tenors:
        if d1.tenors != d0.tenors:
            raise ValueError(f"the two discount curves have different tenors: {d0.tenors} and {d1.tenors}")
        return PERCENT * float(np.mean(np.array(d1.par_rates_pct) - np.array(d0.par_rates_pct)))
    shifted = d0.with_as_of(state_t1.as_of, "calendar")
    if shifted.node_dates == d1.node_dates and all(abs(a - b) <= NODE_DF_ABS_TOL for a, b in zip(shifted.node_dfs, d1.node_dfs)):
        return 0.0
    raise ValueError("state_t1's discount curve carries no par rates and is not the calendar-shifted t_0 curve, so the rates move cannot be read; build it with bootstrap_ois")


def explain(
    state_t0: MarketState,
    state_t1: MarketState,
    trade: CDSTrade,
    *,
    sensitivities_t0: Sensitivities | None = None,
    calendar: str = DEFAULT_CALENDAR,
    engine: Engine = "isda",
    half_day_bias: bool = True,
) -> ExplainResult:
    """The P&L of the trade from state_t0 to state_t1 and its explain; see
    the module docstring. The trade carries the t_0 recovery and is valued
    at t_1 with the t_1 state's recovery, as rec01 does."""
    kw = _kwargs(calendar, engine, half_day_bias)
    if state_t1.as_of < state_t0.as_of:
        raise ValueError(f"state_t1 ({state_t1.as_of}) is dated before state_t0 ({state_t0.as_of})")
    if trade.recovery != state_t0.recovery.R(0.0):
        raise ValueError(f"trade recovery {trade.recovery} differs from state_t0's {state_t0.recovery.R(0.0)}")
    sens = sensitivities(state_t0, trade, **kw) if sensitivities_t0 is None else sensitivities_t0
    rep = sens.report
    r1 = state_t1.recovery.R(0.0)
    v1 = price(state_t1, replace(trade, recovery=r1), **kw).mtm
    schedule = cds_schedule(trade.trade_date, trade.maturity, calendar)
    cash = coupon_cash_in_window(trade, schedule, state_t0.as_of, state_t1.as_of)
    pnl_full = v1 - rep.mtm - SIDE_SIGN[trade.side] * cash

    ds = spread_moves_bp(state_t0, state_t1, sens.spreads_bp, **kw)
    ds_parallel = float(np.mean(ds))
    d_recovery = PERCENT * (r1 - trade.recovery)
    d_rates = rates_move_bp(state_t0, state_t1)
    cs01 = (rep.cs01_6m, rep.cs01_1y, rep.cs01_2y, rep.cs01_3y, rep.cs01_4y, rep.cs01_5y, rep.cs01_7y, rep.cs01_10y)

    first_order = float(sum(c * d for c, d in zip(cs01, ds)))
    gamma = 0.5 * sens.gamma * ds_parallel**2
    recovery = rep.rec01 * d_recovery
    rates = rep.ir01 * d_rates
    theta_term = 0.0 if state_t1.as_of == state_t0.as_of else theta(state_t0, trade, state_t1.as_of, "calendar", **kw)
    cross = sens.cross * ds_parallel * d_recovery
    residual = pnl_full - (first_order + gamma + recovery + rates + theta_term + cross)
    pct = math.nan if abs(pnl_full) < EXPLAIN_ZERO_USD else PERCENT * residual / pnl_full
    return ExplainResult(
        pnl_full=pnl_full,
        pnl_spread_first_order=first_order,
        pnl_spread_gamma=gamma,
        pnl_recovery=recovery,
        pnl_rates=rates,
        pnl_theta=theta_term,
        pnl_cross=cross,
        residual=residual,
        residual_pct_of_total=pct,
    )
