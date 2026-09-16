"""price(), the par spread, clean and dirty upfront, and the flat-hazard
conversions between a quoted spread and an upfront (BUILD_PLAN.md Section 5).

Symbols follow docs/SPEC.md section 6. Leg values come from cds.legs per
unit notional at the valuation date as_of: A = annuity_coupon +
annuity_accrual, PV_prot = pv_protection. With the coupon c = coupon_bp /
10^4, the cash settlement date t_settle = as_of + 3 business days, and
D = 1 / P(t_settle):

    U_dirty         = D * (PV_prot - c * A)          buyer value, per unit notional, at settlement
    accrued         = c * accrued_days / 360         per unit notional, cash on the settlement date
    clean_upfront   = 100 * (U_dirty + accrued)      in % of notional, the quoted number
    mtm             = side_sign * N * (U_dirty - inception_cash)
    s_par           = 10^4 * PV_prot / (A - accrued_fraction / D)     (SPEC 6.4, item 24)

Every amount in PriceResult is stated at the cash settlement date
(docs/CONVENTIONS_RESOLVED.md item 3). The buyer's cash on that date is the
dirty value: the seller rebates the accrued for the days of the first period
before protection started (item 2), and the buyer then pays the full first
coupon. accrued_days runs from the start of the coupon period that contains
as_of + 1 (the step-in date of a buyer entering on as_of) to as_of + 1; for
a trade valued on its trade date that is the schedule's accrued_days.

inception_cash is what the buyer paid on the trade's own settlement date
(item 8): 0 for quote=None (mtm is the current unwind value) and for a
par_spread_bp quote (a running-spread contract, whose coupon must equal the
quote); for an upfront_pct quote it is the quoted clean upfront less the
accrued rebated at inception, value / 100 - c * accrued_days_0 / 360, since
the quote is clean and the cash paid is dirty.

The par spread is the clean-value spread (docs/CONVENTIONS_RESOLVED.md
item 24): the coupon s at which clean_upfront is zero, i.e. at which the
buyer pays nothing on the settlement date beyond the accrued the seller
rebates. With accrued_fraction = accrued_days / 360, clean_upfront = 0 gives
D * (PV_prot - s * A) + s * accrued_fraction = 0, hence the formula above.
It is QuantLib's fairSpread and the spread the ISDA C bootstrap fits with
isPriceClean = TRUE; on a flat hazard it is one number on every tenor. The
dirty par spread PV_prot / A, the coupon at which U_dirty is zero, is kept
as Valuation.dirty_par_spread_bp and is not in PriceResult.

Flat-hazard conversions (Part A.3): quoted_spread_to_upfront finds the
single hazard lambda_flat in [0, 5] at which the trade's par spread (the
clean-value spread) equals the quoted spread, with the trade's recovery,
the given discount curve and the trade's own maturity, and returns the
clean upfront at the trade's coupon. upfront_to_quoted_spread is the
inverse: the lambda_flat at which the clean upfront equals the given one,
and the par spread there. Both use scipy's brentq; the second is one Brent
on lambda rather than a Brent on the spread around the first, which has the
same root (item 26).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from scipy.optimize import brentq

from cds.calendars import add_business_days, is_business_day
from cds.conventions import ACT360_BASIS, CASH_SETTLE_BUSINESS_DAYS, DEFAULT_CALENDAR
from cds.curves import RecoveryCurve, SurvivalCurve
from cds.legs import BP_PER_UNIT, Engine, LegValues, leg_values
from cds.legs import dirty_par_spread_bp as _legs_dirty_par_spread_bp
from cds.schedule import Schedule, cds_schedule, year_fraction_act365f
from cds.types import CDSTrade, DiscountCurve, MarketState, PriceResult
from cds.types import RecoveryCurve as RecoveryCurveProtocol
from cds.types import SurvivalCurve as SurvivalCurveProtocol

__all__ = [
    "HAZARD_BOUNDS",
    "Valuation",
    "accrued_days",
    "cash_settle_date",
    "implied_flat_hazard",
    "price",
    "quoted_spread_to_upfront",
    "upfront_to_quoted_spread",
    "value",
]

# The flat hazard is searched on this interval (BUILD_PLAN.md Part A.4 and
# Section 5): an intensity of 5 a year is far past any quoted spread.
HAZARD_BOUNDS = (0.0, 5.0)

# Brent tolerance on the hazard; 1e-12 in lambda is under 1e-8 bp of spread.
HAZARD_XTOL = 1e-12

PERCENT = 100.0
ONE_DAY = timedelta(days=1)

# The protection buyer's MTM is positive when spreads widen; the seller's is
# the negative (BUILD_PLAN.md Part A.3, "Sign convention").
SIDE_SIGN = {"buy": 1.0, "sell": -1.0}


def cash_settle_date(as_of: date, calendar: str = DEFAULT_CALENDAR) -> date:
    """as_of + 3 business days: the date every PriceResult amount is stated at.
    For a trade valued on its trade date this is the schedule's cash_settle."""
    return add_business_days(as_of, CASH_SETTLE_BUSINESS_DAYS, calendar)


def accrued_days(schedule: Schedule, as_of: date) -> int:
    """Days of coupon accrued before a buyer stepping in on as_of + 1 starts
    to accrue: from the start of the period containing as_of + 1 to as_of + 1.
    Equals schedule.accrued_days when as_of is the trade date."""
    step_in = as_of + ONE_DAY
    if step_in < schedule.accrual_start[0]:
        raise ValueError(f"valuation date {as_of} is before the first accrual period starts on {schedule.accrual_start[0]}")
    if step_in > schedule.maturity:
        raise ValueError(f"valuation date {as_of} is not before maturity {schedule.maturity}")
    start = max(s for s in schedule.accrual_start if s <= step_in)
    return (step_in - start).days


@dataclass(frozen=True)
class Valuation:
    """Everything price() derives, per unit notional, before the side and the
    notional are applied. Leg values are at as_of; amounts marked "at
    settlement" are multiplied by d_settle = 1 / P(t_settle)."""

    as_of: date
    schedule: Schedule
    legs: LegValues
    settle: date
    d_settle: float
    accrued_days: int
    accrued_fraction: float  # accrued_days / 360, per unit of coupon
    coupon: float  # c, per unit notional

    @property
    def par_spread_bp(self) -> float:
        """s_par = 10^4 * PV_prot / (A - accrued_fraction / D): the clean-value
        spread, at which clean_upfront is zero (item 24). QuantLib's fairSpread."""
        return BP_PER_UNIT * self.legs.pv_protection / (self.legs.annuity - self.accrued_fraction / self.d_settle)

    @property
    def dirty_par_spread_bp(self) -> float:
        """10^4 * PV_prot / A: the coupon at which dirty_upfront is zero. Kept
        for comparison; not the par spread the library reports."""
        return _legs_dirty_par_spread_bp(self.legs)

    @property
    def dirty_upfront(self) -> float:
        """U_dirty = D * (PV_prot - c * A), per unit notional at settlement."""
        return self.d_settle * (self.legs.pv_protection - self.coupon * self.legs.annuity)

    @property
    def accrued(self) -> float:
        """c * accrued_days / 360, per unit notional."""
        return self.coupon * self.accrued_fraction

    @property
    def clean_upfront(self) -> float:
        """U_dirty + accrued, per unit notional at settlement."""
        return self.dirty_upfront + self.accrued


def _check_trade(trade: CDSTrade, as_of: date, calendar: str) -> None:
    if not is_business_day(trade.trade_date, calendar):
        raise ValueError(f"trade date {trade.trade_date} is not a business day on the {calendar!r} calendar (item 10)")
    if as_of < trade.trade_date:
        raise ValueError(f"valuation date {as_of} is before the trade date {trade.trade_date}")
    if trade.notional <= 0.0:
        raise ValueError(f"notional {trade.notional!r} is not positive")
    if trade.coupon_bp < 0.0:
        raise ValueError(f"coupon {trade.coupon_bp!r} bp is negative")
    if trade.side not in SIDE_SIGN:
        raise ValueError(f"side {trade.side!r} is not one of {tuple(SIDE_SIGN)}")
    if not (0.0 <= trade.recovery <= 1.0):
        raise ValueError(f"recovery {trade.recovery!r} is not in [0, 1]")


def _check_quote(trade: CDSTrade) -> None:
    """Part B item 8 and docs/CONVENTIONS_RESOLVED.md item 12."""
    quote = trade.quote
    if quote is None:
        return
    if quote.kind == "par_spread_bp":
        if trade.coupon_bp != quote.value:
            raise ValueError(f"a par_spread_bp quote is a running-spread contract: coupon_bp {trade.coupon_bp} must equal the quote {quote.value}")
        if quote.coupon_bp is not None and quote.coupon_bp != quote.value:
            raise ValueError(f"par_spread_bp quote carries coupon_bp {quote.coupon_bp} that differs from its value {quote.value}")
    elif quote.kind == "upfront_pct":
        if quote.coupon_bp is None:
            raise ValueError("an upfront_pct quote needs coupon_bp")
        if quote.coupon_bp != trade.coupon_bp:
            raise ValueError(f"upfront_pct quote coupon_bp {quote.coupon_bp} differs from the trade's coupon_bp {trade.coupon_bp}")
    else:
        raise ValueError(f"unknown quote kind {quote.kind!r}")


def _inception_cash(trade: CDSTrade, schedule: Schedule) -> float:
    """What the buyer paid per unit notional on the trade's own settlement
    date: the clean upfront less the accrued rebated at inception."""
    quote = trade.quote
    if quote is None or quote.kind == "par_spread_bp":
        return 0.0
    accrued_at_inception = trade.coupon_bp / BP_PER_UNIT * schedule.accrued_days / ACT360_BASIS
    return quote.value / PERCENT - accrued_at_inception


def value(
    discount: DiscountCurve,
    survival: SurvivalCurveProtocol,
    recovery: RecoveryCurveProtocol,
    trade: CDSTrade,
    as_of: date,
    *,
    calendar: str = DEFAULT_CALENDAR,
    engine: Engine = "isda",
    half_day_bias: bool = True,
) -> Valuation:
    """The trade on the three curves at as_of, per unit notional, without a
    MarketState; price() and the conversions both go through here."""
    _check_trade(trade, as_of, calendar)
    schedule = cds_schedule(trade.trade_date, trade.maturity, calendar)
    legs = leg_values(discount, survival, recovery, schedule, as_of, half_day_bias=half_day_bias, engine=engine)
    settle = cash_settle_date(as_of, calendar)
    days = accrued_days(schedule, as_of)
    return Valuation(
        as_of=as_of,
        schedule=schedule,
        legs=legs,
        settle=settle,
        d_settle=1.0 / discount.df(year_fraction_act365f(as_of, settle)),
        accrued_days=days,
        accrued_fraction=days / ACT360_BASIS,
        coupon=trade.coupon_bp / BP_PER_UNIT,
    )


def price(
    state: MarketState,
    trade: CDSTrade,
    *,
    calendar: str = DEFAULT_CALENDAR,
    engine: Engine = "isda",
    half_day_bias: bool = True,
) -> PriceResult:
    """PriceResult for the trade on the market state, every amount at the
    cash settlement date. Raises if the curves' as_of disagree with the
    state's, if the trade's recovery is not the state's, on a trade date
    that is not a business day, or on an inconsistent quote."""
    dates = {state.as_of, state.discount.as_of, state.survival.as_of, state.recovery.as_of}
    if len(dates) != 1:
        raise ValueError(f"MarketState.as_of and the curves' as_of disagree: {sorted(dates)}")
    if trade.recovery != state.recovery.R(0.0):
        raise ValueError(f"trade recovery {trade.recovery} differs from the market state's {state.recovery.R(0.0)}")
    _check_quote(trade)
    v = value(state.discount, state.survival, state.recovery, trade, state.as_of, calendar=calendar, engine=engine, half_day_bias=half_day_bias)
    mtm = SIDE_SIGN[trade.side] * trade.notional * (v.dirty_upfront - _inception_cash(trade, v.schedule))
    return PriceResult(
        mtm=mtm,
        clean_upfront_pct=PERCENT * v.clean_upfront,
        accrued=trade.notional * v.accrued,
        par_spread_bp=v.par_spread_bp,
        risky_annuity=v.d_settle * v.legs.annuity,
        pv_protection=v.d_settle * v.legs.pv_protection,
        pv_premium=v.d_settle * v.coupon * v.legs.annuity,
        cash_settle_date=v.settle,
    )


def _flat_valuation(discount: DiscountCurve, trade: CDSTrade, hazard: float, **kwargs) -> Valuation:
    """The trade on a single flat hazard, with its own recovery, valued on
    the discount curve's as_of."""
    as_of = discount.as_of
    survival = SurvivalCurve(as_of=as_of, pillar_dates=(trade.maturity,), pillar_hazards=(hazard,))
    return value(discount, survival, RecoveryCurve.flat(trade.recovery, as_of), trade, as_of, **kwargs)


def implied_flat_hazard(discount: DiscountCurve, trade: CDSTrade, quoted_spread_bp: float, **kwargs) -> float:
    """lambda_flat in HAZARD_BOUNDS at which the trade's par spread (the
    clean-value spread, item 24) equals quoted_spread_bp (Brent). A zero
    spread gives a zero hazard."""
    if quoted_spread_bp < 0.0:
        raise ValueError(f"quoted spread {quoted_spread_bp} bp is negative")
    lo, hi = HAZARD_BOUNDS

    def objective(hazard: float) -> float:
        return _flat_valuation(discount, trade, hazard, **kwargs).par_spread_bp - quoted_spread_bp

    if objective(hi) < 0.0:
        raise ValueError(f"quoted spread {quoted_spread_bp} bp is above the par spread at the hazard bound {hi}")
    return float(brentq(objective, lo, hi, xtol=HAZARD_XTOL))


def quoted_spread_to_upfront(discount: DiscountCurve, trade: CDSTrade, quoted_spread_bp: float, **kwargs) -> float:
    """The ISDA flat-hazard conversion: the clean upfront, in % of notional,
    of the trade at its coupon when its par spread is quoted_spread_bp under
    a single flat hazard."""
    hazard = implied_flat_hazard(discount, trade, quoted_spread_bp, **kwargs)
    return PERCENT * _flat_valuation(discount, trade, hazard, **kwargs).clean_upfront


def upfront_to_quoted_spread(discount: DiscountCurve, trade: CDSTrade, upfront_pct: float, **kwargs) -> float:
    """The inverse of quoted_spread_to_upfront: the quoted spread in bp whose
    flat-hazard clean upfront at the trade's coupon is upfront_pct. One Brent
    on the hazard, then the par spread at the root."""
    lo, hi = HAZARD_BOUNDS

    def objective(hazard: float) -> float:
        return PERCENT * _flat_valuation(discount, trade, hazard, **kwargs).clean_upfront - upfront_pct

    f_lo, f_hi = objective(lo), objective(hi)
    if f_lo > 0.0 or f_hi < 0.0:
        raise ValueError(
            f"upfront {upfront_pct}% is outside the range [{upfront_pct + f_lo:.4f}, {upfront_pct + f_hi:.4f}] "
            f"reachable with a flat hazard in {HAZARD_BOUNDS}"
        )
    hazard = float(brentq(objective, lo, hi, xtol=HAZARD_XTOL))
    return _flat_valuation(discount, trade, hazard, **kwargs).par_spread_bp
