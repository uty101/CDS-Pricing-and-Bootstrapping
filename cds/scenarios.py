"""The scenario grid: full revaluation of a trade under spread, recovery
and rates scenarios, one re-bootstrap per scenario and one vectorised leg
call for the whole grid (BUILD_PLAN.md Section 9, SPEC 6.8).

A Scenario transforms the market inputs of a MarketState:

    s_i'  = s_i * spread_multiplier + spread_shifts_bp[i]     per pillar, bp
    R'    = recovery (None keeps the curve's R)
    r_k'  = r_k + rate_shift_bp / 100                         every OIS par rate, percent

with s_i the conventional spread of pillar i (the quote of a par-spread
curve, the flat-hazard conversion of the upfront otherwise, as cds.risk
reads every bump: docs/CONVENTIONS_RESOLVED.md item 40). The scenario
state is the bootstrap of the eight s_i' as par-spread quotes at R' on the
discount curve rebuilt from the shifted par rates: one Brent per pillar,
looped over scenarios (scenario_states). Nothing is bumped after the
bootstrap; every scenario is a full revaluation.

The standard grid (standard_grid), for a curve at recovery R:

    spread_x<m>      every s_i times m, m in SPREAD_MULTIPLIERS (0.5 to 4; x1 is the base)
    recovery_<R'>    R' = R times 0.5 and 0.25 (0.40 -> 0.20 -> 0.10 on IG), spreads fixed
    steepen_35bp     +0, +5, ..., +35 bp across the 8 pillars, linear in pillar index
    flatten_35bp     the negative
    rates_+100bp, rates_-100bp   every OIS par input
    combined         spreads x2, R times 0.5, rates -100 bp

and the Chart 3 sweep (sweep_grid) is spread_x<m> for m from 0.5 to 4 in
steps of 0.05, 71 scenarios.

Revaluation (revalue). Every scenario state shares the base state's
valuation date, pillar dates and discount node dates, so the merged
integration grid of cds.legs is the same for all of them; the hazards,
node discount factors and recoveries are stacked into a
cds.legs.CurveArrays and priced with one leg_values call, which returns
leg values of shape (n_scenarios,). The pricer's formulas
(cds.pricer.Valuation: D = 1 / P(t_settle), U_dirty = D (PV_prot - c A),
mtm = side N (U_dirty - inception_cash)) are then applied on the arrays,
the trade valued at each scenario's recovery as rec01 does. The inception
cash is scenario-free, so it is read off the base state once:
side N inception = side N U_dirty(base) - mtm(base), mtm(base) from
price(). Symbols follow docs/SPEC.md section 6.

run() returns one row per scenario with the scenario's inputs (the
multiplier, the recovery, the rate shift and the eight spreads it was
bootstrapped from), the trade's mtm, pnl_full = mtm - mtm(base), the
scenario par spread and clean upfront (RUN_COLUMNS). A scenario whose
bootstrap raises (spread_x4 on HY and distressed, whose 10Y and 5Y pillars
sit past what any positive hazard reaches) is, with on_error = "skip" (the
default), written with status = the class of the error the bootstrap
raised and nan in the value columns; status = "ok" otherwise. With
on_error = "raise" the error propagates naming the scenario
(docs/CONVENTIONS_RESOLVED.md item 50).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

import numpy as np
import pandas as pd

from cds.bootstrap import bootstrap, conventional_spreads_bp, market_state
from cds.conventions import DEFAULT_CALENDAR, PILLARS
from cds.legs import CurveArrays, Engine, df_rows, leg_values
from cds.pricer import SIDE_SIGN, Valuation, price, value
from cds.risk import bumped_discount, spread_quotes
from cds.schedule import year_fraction_act365f
from cds.types import CDSTrade, MarketState

__all__ = [
    "CHART_3_MULTIPLIERS",
    "RATE_SHIFTS_BP",
    "RECOVERY_RATIOS",
    "ON_ERROR",
    "RUN_COLUMNS",
    "RUN_VALUE_COLUMNS",
    "SPREAD_MULTIPLIERS",
    "STATUS_OK",
    "STEEPEN_STEP_BP",
    "Scenario",
    "combined_scenario",
    "error_status",
    "flatten_scenario",
    "parallel_scenario",
    "rates_scenario",
    "recovery_scenario",
    "revalue",
    "run",
    "scenario_spreads_bp",
    "scenario_state",
    "scenario_states",
    "spread_scenario",
    "standard_grid",
    "steepen_scenario",
    "sweep_grid",
]

PERCENT = 100.0

# The grid of BUILD_PLAN.md Section 9.
SPREAD_MULTIPLIERS = (0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0)
RECOVERY_RATIOS = (0.5, 0.25)
STEEPEN_STEP_BP = 5.0
RATE_SHIFTS_BP = (100.0, -100.0)
COMBINED = {"spread_multiplier": 2.0, "recovery_ratio": 0.5, "rate_shift_bp": -100.0}

# Chart 3: x0.5 to x4 in 0.05 steps, 71 scenarios.
CHART_3_MULTIPLIERS = tuple(round(0.5 + 0.05 * k, 2) for k in range(71))

OnError = Literal["raise", "skip"]
ON_ERROR = ("raise", "skip")
STATUS_OK = "ok"

RUN_COLUMNS = (
    "scenario",
    "status",
    "spread_multiplier",
    "recovery",
    "rate_shift_bp",
    *(f"spread_{p.lower()}_bp" for p in PILLARS),
    "mtm",
    "pnl_full",
    "par_spread_bp",
    "clean_upfront_pct",
)

# The columns written as nan when a scenario does not bootstrap; the
# scenario's inputs (multiplier, recovery, rate shift, spreads) are known
# without a bootstrap and are written.
RUN_VALUE_COLUMNS = ("mtm", "pnl_full", "par_spread_bp", "clean_upfront_pct")


@dataclass(frozen=True, kw_only=True)
class Scenario:
    """One transformation of the market inputs; see the module docstring.
    spread_shifts_bp has one entry per pillar (None: no shift); recovery
    None keeps the curve's R."""

    name: str
    spread_multiplier: float = 1.0
    spread_shifts_bp: tuple[float, ...] | None = None
    recovery: float | None = None
    rate_shift_bp: float = 0.0

    def __post_init__(self) -> None:
        if self.spread_multiplier < 0.0:
            raise ValueError(f"spread multiplier {self.spread_multiplier} is negative")
        if self.recovery is not None and not (0.0 <= self.recovery <= 1.0):
            raise ValueError(f"recovery {self.recovery} is not in [0, 1]")


def _fmt(x: float) -> str:
    return f"{x:g}"


def spread_scenario(multiplier: float) -> Scenario:
    return Scenario(name=f"spread_x{_fmt(multiplier)}", spread_multiplier=multiplier)


def parallel_scenario(shift_bp: float) -> Scenario:
    """Every pillar's spread + shift_bp (the explain test cases)."""
    return Scenario(name=f"parallel_{shift_bp:+g}bp", spread_shifts_bp=(shift_bp,) * len(PILLARS))


def recovery_scenario(recovery: float) -> Scenario:
    return Scenario(name=f"recovery_{_fmt(recovery)}", recovery=recovery)


def _linear_shifts(step_bp: float) -> tuple[float, ...]:
    return tuple(step_bp * i for i in range(len(PILLARS)))


def steepen_scenario(step_bp: float = STEEPEN_STEP_BP) -> Scenario:
    """+0 at 6M rising by step_bp per pillar to +7 step_bp at 10Y."""
    return Scenario(name=f"steepen_{_fmt(step_bp * (len(PILLARS) - 1))}bp", spread_shifts_bp=_linear_shifts(step_bp))


def flatten_scenario(step_bp: float = STEEPEN_STEP_BP) -> Scenario:
    return Scenario(name=f"flatten_{_fmt(step_bp * (len(PILLARS) - 1))}bp", spread_shifts_bp=_linear_shifts(-step_bp))


def rates_scenario(shift_bp: float) -> Scenario:
    return Scenario(name=f"rates_{shift_bp:+g}bp", rate_shift_bp=shift_bp)


def combined_scenario(base_recovery: float) -> Scenario:
    return Scenario(name="combined", spread_multiplier=COMBINED["spread_multiplier"], recovery=base_recovery * COMBINED["recovery_ratio"], rate_shift_bp=COMBINED["rate_shift_bp"])


def standard_grid(base_recovery: float) -> tuple[Scenario, ...]:
    """The Section 9 grid for a curve at base_recovery, 14 scenarios."""
    return (
        *(spread_scenario(m) for m in SPREAD_MULTIPLIERS),
        *(recovery_scenario(base_recovery * ratio) for ratio in RECOVERY_RATIOS),
        steepen_scenario(),
        flatten_scenario(),
        *(rates_scenario(bp) for bp in RATE_SHIFTS_BP),
        combined_scenario(base_recovery),
    )


def sweep_grid(multipliers: tuple[float, ...] = CHART_3_MULTIPLIERS) -> tuple[Scenario, ...]:
    """The Chart 3 sweep."""
    return tuple(spread_scenario(m) for m in multipliers)


def scenario_spreads_bp(scenario: Scenario, spreads_bp: tuple[float, ...]) -> tuple[float, ...]:
    """s_i * multiplier + shift_i per pillar."""
    shifts = (0.0,) * len(spreads_bp) if scenario.spread_shifts_bp is None else scenario.spread_shifts_bp
    if len(shifts) != len(spreads_bp):
        raise ValueError(f"scenario {scenario.name!r} has {len(shifts)} spread shifts for {len(spreads_bp)} pillars")
    out = tuple(s * scenario.spread_multiplier + b for s, b in zip(spreads_bp, shifts))
    if any(s < 0.0 for s in out):
        raise ValueError(f"scenario {scenario.name!r} gives a negative spread: {out}")
    return out


def _kwargs(calendar: str, engine: Engine, half_day_bias: bool) -> dict:
    return {"calendar": calendar, "engine": engine, "half_day_bias": half_day_bias}


def scenario_state(
    state: MarketState,
    scenario: Scenario,
    *,
    spreads_bp: tuple[float, ...] | None = None,
    calendar: str = DEFAULT_CALENDAR,
    engine: Engine = "isda",
    half_day_bias: bool = True,
) -> MarketState:
    """The state under the scenario: the transformed spreads bootstrapped as
    par-spread quotes at the scenario's recovery on the shifted discount
    curve. spreads_bp are the base conventional spreads, computed here if
    not given."""
    kw = _kwargs(calendar, engine, half_day_bias)
    if spreads_bp is None:
        spreads_bp = conventional_spreads_bp(state.quotes, state.discount, **kw)
    discount = state.discount if scenario.rate_shift_bp == 0.0 else bumped_discount(state.discount, scenario.rate_shift_bp)
    recovery = state.quotes.recovery if scenario.recovery is None else scenario.recovery
    quotes = spread_quotes(state.quotes, scenario_spreads_bp(scenario, spreads_bp), recovery)
    try:
        result = bootstrap(quotes, discount, **kw)
    except ValueError as err:
        raise ValueError(f"scenario {scenario.name!r} does not bootstrap: {err}") from err
    return market_state(result, discount)


def scenario_states(
    state: MarketState,
    grid: tuple[Scenario, ...],
    *,
    spreads_bp: tuple[float, ...] | None = None,
    calendar: str = DEFAULT_CALENDAR,
    engine: Engine = "isda",
    half_day_bias: bool = True,
) -> list[MarketState]:
    """One bootstrap per scenario; the discount curve is rebuilt once per
    distinct rate shift. Raises on the first scenario that does not
    bootstrap, naming it."""
    out = _scenario_states_or_errors(state, grid, spreads_bp=spreads_bp, calendar=calendar, engine=engine, half_day_bias=half_day_bias)
    for item in out:
        if isinstance(item, Exception):
            raise item
    return out


def _scenario_states_or_errors(
    state: MarketState,
    grid: tuple[Scenario, ...],
    *,
    spreads_bp: tuple[float, ...] | None,
    calendar: str,
    engine: Engine,
    half_day_bias: bool,
) -> list[MarketState | ValueError]:
    """scenario_states, with the ValueError a failing bootstrap raised in
    the place of its state."""
    kw = _kwargs(calendar, engine, half_day_bias)
    if spreads_bp is None:
        spreads_bp = conventional_spreads_bp(state.quotes, state.discount, **kw)
    discounts = {0.0: state.discount}
    out: list[MarketState | ValueError] = []
    for scenario in grid:
        if scenario.rate_shift_bp not in discounts:
            discounts[scenario.rate_shift_bp] = bumped_discount(state.discount, scenario.rate_shift_bp)
        shifted = replace(state, discount=discounts[scenario.rate_shift_bp])
        try:
            out.append(scenario_state(shifted, replace(scenario, rate_shift_bp=0.0), spreads_bp=spreads_bp, **kw))
        except ValueError as err:
            out.append(err)
    return out


def error_status(err: BaseException) -> str:
    """The status written for a scenario that did not bootstrap: the class
    of the error the bootstrap raised (BootstrapArbitrageError for a pillar
    that needs a negative hazard, ValueError for one past the hazard cap),
    read through the wrapper scenario_state adds."""
    inner = err.__cause__ if err.__cause__ is not None else err
    return type(inner).__name__


def _check_states(state: MarketState, states: list[MarketState]) -> None:
    for k, s in enumerate(states):
        if s.as_of != state.as_of:
            raise ValueError(f"scenario state {k} is dated {s.as_of}; the base is {state.as_of}")
        if s.survival.pillar_dates != state.survival.pillar_dates:
            raise ValueError(f"scenario state {k} has other pillar dates than the base")
        if s.discount.node_dates != state.discount.node_dates:
            raise ValueError(f"scenario state {k} has other discount node dates than the base")


def revalue(
    state: MarketState,
    trade: CDSTrade,
    states: list[MarketState],
    *,
    calendar: str = DEFAULT_CALENDAR,
    engine: Engine = "isda",
    half_day_bias: bool = True,
) -> Valuation:
    """The trade on every scenario state in one vectorised leg call: a
    Valuation whose legs, d_settle and hence dirty_upfront, clean_upfront
    and par_spread_bp are arrays of shape (len(states),). The trade is
    valued at each state's recovery."""
    _check_states(state, states)
    kw = _kwargs(calendar, engine, half_day_bias)
    base = value(state.discount, state.survival, state.recovery, trade, state.as_of, **kw)
    arrays = CurveArrays(
        hazards=np.array([s.survival.pillar_hazards for s in states]),
        node_dfs=np.array([s.discount.node_dfs for s in states]),
        recoveries=np.array([s.recovery.R(0.0) for s in states]),
    )
    legs = leg_values(state.discount, state.survival, state.recovery, base.schedule, state.as_of, half_day_bias=half_day_bias, engine=engine, arrays=arrays)
    t_settle = year_fraction_act365f(state.as_of, base.settle)
    d_settle = 1.0 / df_rows(state.discount.node_times, arrays.node_dfs, np.array([t_settle]))[:, 0]
    return replace(base, legs=legs, d_settle=d_settle)


def _mtm_array(state: MarketState, trade: CDSTrade, valuation: Valuation, kw: dict) -> np.ndarray:
    """side N U_dirty less the side's inception cash, read off the base state."""
    base = value(state.discount, state.survival, state.recovery, trade, state.as_of, **kw)
    sign_n = SIDE_SIGN[trade.side] * trade.notional
    inception = sign_n * base.dirty_upfront - price(state, trade, **kw).mtm
    return sign_n * valuation.dirty_upfront - inception


def run(
    state: MarketState,
    trade: CDSTrade,
    grid: tuple[Scenario, ...],
    *,
    states: list[MarketState] | None = None,
    spreads_bp: tuple[float, ...] | None = None,
    on_error: OnError = "skip",
    calendar: str = DEFAULT_CALENDAR,
    engine: Engine = "isda",
    half_day_bias: bool = True,
) -> pd.DataFrame:
    """One row per scenario, columns RUN_COLUMNS. states, if given, are the
    grid's scenario states already built (scenario_states), and every one
    is priced. Otherwise the states are bootstrapped here and a scenario
    that does not bootstrap is written with its error's class in status
    and nan in RUN_VALUE_COLUMNS (on_error = "skip", the default) or
    propagates (on_error = "raise")."""
    if on_error not in ON_ERROR:
        raise ValueError(f"unknown on_error {on_error!r}; expected one of {ON_ERROR}")
    kw = _kwargs(calendar, engine, half_day_bias)
    if spreads_bp is None:
        spreads_bp = conventional_spreads_bp(state.quotes, state.discount, **kw)
    if states is None:
        built = _scenario_states_or_errors(state, grid, spreads_bp=spreads_bp, **kw)
        if on_error == "raise":
            for item in built:
                if isinstance(item, Exception):
                    raise item
    else:
        built = list(states)
    if len(built) != len(grid):
        raise ValueError(f"{len(built)} states for {len(grid)} scenarios")
    priced = [k for k, item in enumerate(built) if not isinstance(item, Exception)]
    valuation = revalue(state, trade, [built[k] for k in priced], **kw) if priced else None
    mtm = _mtm_array(state, trade, valuation, kw) if priced else np.array([])
    base_mtm = price(state, trade, **kw).mtm
    base_recovery = state.quotes.recovery
    rows = []
    for k, (scenario, item) in enumerate(zip(grid, built)):
        row = {
            "scenario": scenario.name,
            "status": STATUS_OK if not isinstance(item, Exception) else error_status(item),
            "spread_multiplier": scenario.spread_multiplier,
            "recovery": base_recovery if scenario.recovery is None else scenario.recovery,
            "rate_shift_bp": scenario.rate_shift_bp,
            **{f"spread_{p.lower()}_bp": s_i for p, s_i in zip(PILLARS, scenario_spreads_bp(scenario, spreads_bp))},
            **{c: float("nan") for c in RUN_VALUE_COLUMNS},
        }
        if not isinstance(item, Exception):
            j = priced.index(k)
            row.update(
                {
                    "recovery": item.recovery.R(0.0),
                    **{f"spread_{p.lower()}_bp": q.value for p, q in zip(PILLARS, item.quotes.quotes)},
                    "mtm": float(mtm[j]),
                    "pnl_full": float(mtm[j] - base_mtm),
                    "par_spread_bp": float(valuation.par_spread_bp[j]),
                    "clean_upfront_pct": float(PERCENT * valuation.clean_upfront[j]),
                }
            )
        rows.append(row)
    return pd.DataFrame(rows, columns=list(RUN_COLUMNS))
