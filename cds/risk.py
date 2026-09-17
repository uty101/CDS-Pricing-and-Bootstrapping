"""The risk report: CS01 by pillar and parallel, rec01 both ways, IR01, JTD
and the two thetas (BUILD_PLAN.md Section 8, bump definitions Part D.2,
corrections Part C items 2, 3 and 5, theta definition Part B item 7).

Every measure is in currency for the trade's side: the bumped state is
built, the trade repriced with cds.pricer.price, and the measure is the
bumped mtm less the base mtm. Every bump is on an input, followed by a
full rebuild of what depends on it; nothing bumps a hazard directly except
rec01_hazard_fixed, which bumps nothing but R. The base is the state as
given, which must be the bootstrap of its own quotes on its own discount
curve (risk() checks this by re-bootstrapping once; a state built by
cds.bootstrap.market_state passes).

The market input every bump starts from is the curve's conventional
spread per pillar, s_i: the quote itself for a par-spread curve and the
flat-hazard conversion of the upfront (cds.bootstrap.conventional_spreads_bp,
at the base recovery on the base discount curve) for an upfront-quoted
one. That is what Part D.2 names as the bumped input for CS01 and what the
bootstrap fits (Part A.4: upfronts are converted first and then
bootstrapped like spreads; the joint curve reprices the spreads, not the
upfronts, review 06). rec01 and IR01 hold the same s_i fixed, so on an
upfront-quoted curve the upfront the curve implies moves with R and with
rates while the spread does not. The spreads are computed once per
risk() call and every rebuild bootstraps them as par-spread quotes.

Symbols follow docs/SPEC.md section 6: s_i the conventional spread of
pillar i, lambda_i its hazard, R recovery, A the risky annuity, PV_prot the
protection leg, P(t) the discount factor, N the notional, c the coupon.

CS01 per pillar. s_i + 1 bp, the other pillars unchanged, re-bootstrap,
reprice. For an upfront-quoted curve the bump is to the conventional spread
and the eight spreads are fed back as par-spread quotes. One-sided up;
cs01_central_<pillar> is (mtm(s_i + 1) - mtm(s_i - 1)) / 2. Parallel CS01
adds 1 bp to every pillar at once. cs01_bucket_sum is the sum of the eight
one-sided bumps; it is not the parallel number because a bucketed bump
re-solves every later pillar's hazard, and the residual is second order.

rec01. R + 1 percentage point on the trade, the market state's recovery
curve and the quotes (docs/CONVENTIONS_RESOLVED.md item 28), the market
conventional spreads held fixed and the curve re-bootstrapped, so the
hazards move to keep the spreads repriced. rec01_hazard_fixed bumps R on
the trade and the recovery curve only, the survival curve as it is. Part C
item 5: with the hazards fixed V = (1 - R) I - c A, so the bump is
-0.01 I N per side exactly, whatever the coupon; with the quotes fixed
PV_prot stays pinned at s_mkt A, V = (s_mkt - c) A, and the bump is
(s_mkt - c) dA N: zero for a par trade and growing with |s_mkt - c|.

IR01. Every OIS par rate in the discount curve's inputs + 1 bp, the
discount curve rebuilt with cds.curves.bootstrap_ois, the conventional
spreads held fixed and re-bootstrapped off the new discount curve, the
trade repriced.
The discount curve must carry its inputs (a DiscountCurve from
bootstrap_ois does; a calendar-shifted one does not).

JTD. Part C item 2: for the protection buyer (1 - R) N - mtm - accrued,
where mtm is the buyer's dirty mtm and accrued is the coupon accrued from
the start of the period containing the valuation date to the valuation
date itself, c N days / 360, paid on default under accrual on default
(item 29 counts the pricer's accrued to as_of + 1; this one stops at
as_of). The seller's number is the negative. R is the trade's assumed
recovery.

Theta. Part B item 7: the change in the side's dirty mtm from t_0 to t_1
plus the coupon cash the side paid (buyer, negative) or received (seller,
positive) on payment dates in (t_0, t_1]. The valuation date moves by 1
calendar day or 1 calendar month with no business-day adjustment; the cash
settlement date moves with it. Part C item 3 gives the two ways the curves
move: theta-calendar keeps every curve node on its calendar date
(with_as_of(t_1, "calendar") on all three curves: hazards and forwards
between the same dates unchanged, the contract shorter); theta-rolldown
keeps every node at its tenor (with_as_of(t_1, "tenor"): the discount
curve's node dates move by the same days with no re-bootstrap, item 17,
and the survival curve's pillar dates likewise). The shifted MarketState
carries the quotes with their as_of moved, for the record only; price()
does not read them.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta

from cds.bootstrap import bootstrap, conventional_spreads_bp, market_state
from cds.conventions import ACT360_BASIS, DEFAULT_CALENDAR, PILLARS
from cds.curves import DiscountCurve, RecoveryCurve, ShiftMode, bootstrap_ois
from cds.legs import BP_PER_UNIT, Engine
from cds.pricer import SIDE_SIGN, price
from cds.schedule import Schedule, cds_schedule
from cds.types import CDSTrade, MarketCurveQuotes, MarketState, Quote, RiskReport

__all__ = [
    "BUMP_RATE_BP",
    "BUMP_RECOVERY",
    "BUMP_SPREAD_BP",
    "THETA_DAYS",
    "THETA_MONTHS",
    "accrued_to_valuation_date",
    "add_calendar_months",
    "bumped_discount",
    "coupon_cash_in_window",
    "cs01_by_pillar",
    "cs01_parallel",
    "ir01",
    "jtd",
    "rec01",
    "rec01_hazard_fixed",
    "rates_bumped_state",
    "recovery_state",
    "risk",
    "shifted_state",
    "spread_bumped_state",
    "spread_quotes",
    "theta",
]

PERCENT = 100.0
ONE_DAY = timedelta(days=1)

# The bump sizes (Part D.2): 1 bp of spread, 1 percentage point of recovery,
# 1 bp of OIS par rate.
BUMP_SPREAD_BP = 1.0
BUMP_RECOVERY = 0.01
BUMP_RATE_BP = 1.0

# The theta horizons: 1 calendar day and 1 calendar month.
THETA_DAYS = 1
THETA_MONTHS = 1

# A state is accepted as the bootstrap of its quotes when every re-solved
# hazard is within this of the state's; the solver's xtol is 1e-12.
STATE_HAZARD_ABS_TOL = 1e-9

MONTHS_PER_YEAR = 12


def add_calendar_months(d: date, months: int) -> date:
    """d moved by whole calendar months, the day of month kept (clipped to
    the end of a shorter month), no business-day adjustment."""
    total = d.year * MONTHS_PER_YEAR + (d.month - 1) + months
    year, month = divmod(total, MONTHS_PER_YEAR)
    month += 1
    next_month_start = date(year + (month == MONTHS_PER_YEAR), month % MONTHS_PER_YEAR + 1, 1)
    days_in_month = (next_month_start - date(year, month, 1)).days
    return date(year, month, min(d.day, days_in_month))


def _kwargs(calendar: str, engine: Engine, half_day_bias: bool) -> dict:
    return {"calendar": calendar, "engine": engine, "half_day_bias": half_day_bias}


def _mtm(state: MarketState, trade: CDSTrade, kw: dict) -> float:
    return price(state, trade, **kw).mtm


def _spreads(state: MarketState, kw: dict, spreads_bp: tuple[float, ...] | None) -> tuple[float, ...]:
    """The conventional spreads the bumps start from: the ones given (risk()
    computes them once) or a fresh conversion of the state's quotes."""
    if spreads_bp is None:
        return conventional_spreads_bp(state.quotes, state.discount, **kw)
    if len(spreads_bp) != len(state.quotes.pillars):
        raise ValueError(f"{len(spreads_bp)} spreads for {len(state.quotes.pillars)} pillars")
    return tuple(spreads_bp)


def _check_state(state: MarketState, trade: CDSTrade, spreads_bp: tuple[float, ...], kw: dict) -> None:
    """The base state is the bootstrap of its quotes, and the trade, the
    recovery curve and the quotes agree on R."""
    r_state = state.recovery.R(0.0)
    if trade.recovery != r_state or state.quotes.recovery != r_state:
        raise ValueError(f"recovery differs between the trade ({trade.recovery}), the recovery curve ({r_state}) and the quotes ({state.quotes.recovery})")
    refit = bootstrap(spread_quotes(state.quotes, spreads_bp), state.discount, **kw).survival
    if refit.pillar_dates != state.survival.pillar_dates or any(abs(a - b) > STATE_HAZARD_ABS_TOL for a, b in zip(refit.pillar_hazards, state.survival.pillar_hazards)):
        raise ValueError("state.survival is not the bootstrap of state.quotes on state.discount; build the state with cds.bootstrap.market_state")


# --- the bumped states ----------------------------------------------------------


def spread_quotes(quotes: MarketCurveQuotes, spreads_bp: tuple[float, ...], recovery: float | None = None) -> MarketCurveQuotes:
    """The curve restated as par-spread quotes at spreads_bp, at its own
    recovery unless another is given: what every rebuild bootstraps."""
    return MarketCurveQuotes(
        as_of=quotes.as_of,
        pillars=quotes.pillars,
        quotes=tuple(Quote(kind="par_spread_bp", value=float(s)) for s in spreads_bp),
        recovery=quotes.recovery if recovery is None else recovery,
        label=quotes.label,
    )


def spread_bumped_state(state: MarketState, bumps_bp: tuple[float, ...], *, spreads_bp: tuple[float, ...] | None = None, **kw) -> MarketState:
    """The state re-bootstrapped with bumps_bp added to the conventional
    spreads, pillar by pillar."""
    spreads = _spreads(state, kw, spreads_bp)
    if len(bumps_bp) != len(spreads):
        raise ValueError(f"{len(bumps_bp)} bumps for {len(spreads)} pillars")
    bumped = spread_quotes(state.quotes, tuple(s + b for s, b in zip(spreads, bumps_bp)))
    return market_state(bootstrap(bumped, state.discount, **kw), state.discount)


def recovery_state(state: MarketState, recovery: float, *, hazard_fixed: bool, spreads_bp: tuple[float, ...] | None = None, **kw) -> MarketState:
    """The state at a different recovery: the conventional spreads held
    fixed and the curve re-bootstrapped, or (hazard_fixed) the survival
    curve as it is."""
    if hazard_fixed:
        return MarketState(as_of=state.as_of, discount=state.discount, survival=state.survival, recovery=RecoveryCurve.flat(recovery, state.as_of), quotes=replace(state.quotes, recovery=recovery))
    quotes = spread_quotes(state.quotes, _spreads(state, kw, spreads_bp), recovery)
    return market_state(bootstrap(quotes, state.discount, **kw), state.discount)


def bumped_discount(discount: DiscountCurve, bump_bp: float) -> DiscountCurve:
    """The discount curve rebuilt from its OIS par rates, each + bump_bp."""
    if not discount.tenors:
        raise ValueError("the discount curve carries no OIS par rates to bump (a calendar-shifted curve does not); IR01 needs one from bootstrap_ois")
    return bootstrap_ois(discount.as_of, discount.tenors, tuple(r + bump_bp / PERCENT for r in discount.par_rates_pct), discount.calendar)


def rates_bumped_state(state: MarketState, bump_bp: float, *, spreads_bp: tuple[float, ...] | None = None, **kw) -> MarketState:
    """The state on the discount curve rebuilt from its par rates + bump_bp,
    the conventional spreads held fixed and re-bootstrapped off it."""
    discount = bumped_discount(state.discount, bump_bp)
    quotes = spread_quotes(state.quotes, _spreads(state, kw, spreads_bp))
    return market_state(bootstrap(quotes, discount, **kw), discount)


def shifted_state(state: MarketState, new_as_of: date, mode: ShiftMode) -> MarketState:
    """The state seen from new_as_of with the three curves moved in the
    given mode (Part C item 3); the quotes carried with their as_of moved."""
    return MarketState(
        as_of=new_as_of,
        discount=state.discount.with_as_of(new_as_of, mode),
        survival=state.survival.with_as_of(new_as_of, mode),
        recovery=state.recovery.with_as_of(new_as_of, mode),
        quotes=replace(state.quotes, as_of=new_as_of),
    )


# --- the measures -----------------------------------------------------------------


def cs01_by_pillar(state: MarketState, trade: CDSTrade, bump_bp: float = BUMP_SPREAD_BP, *, spreads_bp: tuple[float, ...] | None = None, calendar: str = DEFAULT_CALENDAR, engine: Engine = "isda", half_day_bias: bool = True) -> tuple[float, ...]:
    """mtm(s_i + bump_bp) - mtm(s), one entry per pillar, the side's currency."""
    kw = _kwargs(calendar, engine, half_day_bias)
    spreads = _spreads(state, kw, spreads_bp)
    base = _mtm(state, trade, kw)
    n = len(spreads)
    out = []
    for i in range(n):
        bumps = tuple(bump_bp if k == i else 0.0 for k in range(n))
        out.append(_mtm(spread_bumped_state(state, bumps, spreads_bp=spreads, **kw), trade, kw) - base)
    return tuple(out)


def cs01_parallel(state: MarketState, trade: CDSTrade, bump_bp: float = BUMP_SPREAD_BP, *, spreads_bp: tuple[float, ...] | None = None, calendar: str = DEFAULT_CALENDAR, engine: Engine = "isda", half_day_bias: bool = True) -> float:
    """mtm(every s_i + bump_bp) - mtm(s)."""
    kw = _kwargs(calendar, engine, half_day_bias)
    spreads = _spreads(state, kw, spreads_bp)
    bumps = (bump_bp,) * len(spreads)
    return _mtm(spread_bumped_state(state, bumps, spreads_bp=spreads, **kw), trade, kw) - _mtm(state, trade, kw)


def _with_recovery(trade: CDSTrade, recovery: float) -> CDSTrade:
    return replace(trade, recovery=recovery)


def rec01(state: MarketState, trade: CDSTrade, bump: float = BUMP_RECOVERY, *, spreads_bp: tuple[float, ...] | None = None, calendar: str = DEFAULT_CALENDAR, engine: Engine = "isda", half_day_bias: bool = True) -> float:
    """mtm at R + bump with the spreads fixed and the curve re-bootstrapped,
    less the base mtm: the desk number, near zero for a par trade."""
    kw = _kwargs(calendar, engine, half_day_bias)
    r_up = trade.recovery + bump
    bumped = recovery_state(state, r_up, hazard_fixed=False, spreads_bp=spreads_bp, **kw)
    return _mtm(bumped, _with_recovery(trade, r_up), kw) - _mtm(state, trade, kw)


def rec01_hazard_fixed(state: MarketState, trade: CDSTrade, bump: float = BUMP_RECOVERY, *, calendar: str = DEFAULT_CALENDAR, engine: Engine = "isda", half_day_bias: bool = True) -> float:
    """mtm at R + bump with the survival curve as it is, less the base mtm:
    -bump * I * N per side, whatever the coupon (Part C item 5)."""
    kw = _kwargs(calendar, engine, half_day_bias)
    r_up = trade.recovery + bump
    return _mtm(recovery_state(state, r_up, hazard_fixed=True), _with_recovery(trade, r_up), kw) - _mtm(state, trade, kw)


def ir01(state: MarketState, trade: CDSTrade, bump_bp: float = BUMP_RATE_BP, *, spreads_bp: tuple[float, ...] | None = None, calendar: str = DEFAULT_CALENDAR, engine: Engine = "isda", half_day_bias: bool = True) -> float:
    """mtm on the discount curve rebuilt from its par rates + bump_bp, the
    spreads re-bootstrapped off it, less the base mtm."""
    kw = _kwargs(calendar, engine, half_day_bias)
    return _mtm(rates_bumped_state(state, bump_bp, spreads_bp=spreads_bp, **kw), trade, kw) - _mtm(state, trade, kw)


def accrued_to_valuation_date(schedule: Schedule, as_of: date) -> int:
    """Days of coupon accrued in the period containing as_of, from its start
    to as_of; 0 when as_of is before the first period starts."""
    starts = [s for s in schedule.accrual_start if s <= as_of]
    if not starts:
        return 0
    return (as_of - max(starts)).days


def jtd(state: MarketState, trade: CDSTrade, *, calendar: str = DEFAULT_CALENDAR, engine: Engine = "isda", half_day_bias: bool = True) -> float:
    """Part C item 2: side * ((1 - R) N - accrued to as_of) - mtm, i.e. for
    the buyer (1 - R) N - mtm - accrued and for the seller the negative."""
    kw = _kwargs(calendar, engine, half_day_bias)
    schedule = cds_schedule(trade.trade_date, trade.maturity, calendar)
    days = accrued_to_valuation_date(schedule, state.as_of)
    accrued = trade.coupon_bp / BP_PER_UNIT * trade.notional * days / ACT360_BASIS
    return SIDE_SIGN[trade.side] * ((1.0 - trade.recovery) * trade.notional - accrued) - _mtm(state, trade, kw)


def coupon_cash_in_window(trade: CDSTrade, schedule: Schedule, t0: date, t1: date) -> float:
    """The coupons the buyer pays on payment dates in (t0, t1], in currency,
    unsigned: c N Delta_j summed over those periods."""
    return sum(trade.coupon_bp / BP_PER_UNIT * trade.notional * frac for frac, pay in zip(schedule.accrual_fraction, schedule.payment) if t0 < pay <= t1)


def theta(state: MarketState, trade: CDSTrade, new_as_of: date, mode: ShiftMode, *, calendar: str = DEFAULT_CALENDAR, engine: Engine = "isda", half_day_bias: bool = True) -> float:
    """mtm at new_as_of (curves moved in the given mode) less mtm at as_of,
    less the coupons the buyer paid in between (the seller's sign is the
    opposite): item 7. mode "calendar" is theta-calendar, "tenor" is
    theta-rolldown (Part C item 3)."""
    kw = _kwargs(calendar, engine, half_day_bias)
    if new_as_of <= state.as_of:
        raise ValueError(f"theta needs a later valuation date; got {new_as_of} from {state.as_of}")
    schedule = cds_schedule(trade.trade_date, trade.maturity, calendar)
    later = _mtm(shifted_state(state, new_as_of, mode), trade, kw)
    cash = coupon_cash_in_window(trade, schedule, state.as_of, new_as_of)
    return later - _mtm(state, trade, kw) - SIDE_SIGN[trade.side] * cash


def risk(state: MarketState, trade: CDSTrade, *, calendar: str = DEFAULT_CALENDAR, engine: Engine = "isda", half_day_bias: bool = True) -> RiskReport:
    """Every measure of Part D.2 for the trade on the state, in the side's
    currency, as a RiskReport (its field names are the Table 3 columns)."""
    kw = _kwargs(calendar, engine, half_day_bias)
    if tuple(state.quotes.pillars) != PILLARS:
        raise ValueError(f"the risk report has one CS01 column per pillar in {PILLARS}; the state has {state.quotes.pillars}")
    spreads = conventional_spreads_bp(state.quotes, state.discount, **kw)
    _check_state(state, trade, spreads, kw)
    up = cs01_by_pillar(state, trade, BUMP_SPREAD_BP, spreads_bp=spreads, **kw)
    down = cs01_by_pillar(state, trade, -BUMP_SPREAD_BP, spreads_bp=spreads, **kw)
    central = tuple((u - d) / 2.0 for u, d in zip(up, down))
    parallel_up = cs01_parallel(state, trade, BUMP_SPREAD_BP, spreads_bp=spreads, **kw)
    parallel_down = cs01_parallel(state, trade, -BUMP_SPREAD_BP, spreads_bp=spreads, **kw)
    t_1d = state.as_of + timedelta(days=THETA_DAYS)
    t_1m = add_calendar_months(state.as_of, THETA_MONTHS)
    fields = {
        "mtm": _mtm(state, trade, kw),
        **{f"cs01_{p.lower()}": v for p, v in zip(PILLARS, up)},
        "cs01_bucket_sum": sum(up),
        "cs01_parallel": parallel_up,
        **{f"cs01_central_{p.lower()}": v for p, v in zip(PILLARS, central)},
        "cs01_central_parallel": (parallel_up - parallel_down) / 2.0,
        "rec01": rec01(state, trade, BUMP_RECOVERY, spreads_bp=spreads, **kw),
        "rec01_hazard_fixed": rec01_hazard_fixed(state, trade, BUMP_RECOVERY, **kw),
        "ir01": ir01(state, trade, BUMP_RATE_BP, spreads_bp=spreads, **kw),
        "jtd": jtd(state, trade, **kw),
        "theta_calendar_1d": theta(state, trade, t_1d, "calendar", **kw),
        "theta_rolldown_1d": theta(state, trade, t_1d, "tenor", **kw),
        "theta_calendar_1m": theta(state, trade, t_1m, "calendar", **kw),
        "theta_rolldown_1m": theta(state, trade, t_1m, "tenor", **kw),
    }
    return RiskReport(**fields)
