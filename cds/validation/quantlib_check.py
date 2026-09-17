"""The same trades and curves through QuantLib's IsdaCdsEngine and
SpreadCdsHelper bootstrap (BUILD_PLAN.md Section 7). Three comparisons, each
isolating one layer, every one a row of Table 2:

Pricer. QuantLib is handed our curves as they are: ql.DiscountCurve on our
node dates and discount factors with Actual365Fixed (log-linear, the
ISDA interpolation) and ql.HazardRateCurve on our pillar dates and hazards
with Actual365Fixed (backward-flat, so lambda_i holds on (t_{i-1}, t_i] as
in cds.curves). The contract is ql.CreditDefaultSwap(side, N, upfront = 0,
spread = c, schedule, Following, Actual360(), settlesAccrual = True,
paysAtDefaultTime = True, protectionStart = step-in, claim = FaceValueClaim,
lastPeriodDayCounter = Actual360(True), rebatesAccrual = True, tradeDate =
as_of, cashSettlementDays = 3) on ql.Schedule(step-in, maturity, 3M,
WeekendsOnly, Following, Unadjusted, CDS2015), priced with
ql.IsdaCdsEngine(prob, R, disc, includeSettlementDateFlows = False,
NumericalFix = Taylor, AccrualBias = HalfDayBias, ForwardsInCouponPeriod =
Piecewise). Compared, all per unit notional at the cash settlement date:
clean upfront in % (fairUpfront, which QuantLib already states there), par
spread in bp (fairSpread, the clean-value spread of item 24), PV_prot
(-defaultLegNPV / P(t_settle)) and the risky annuity A
(-couponLegNPV / c / P(t_settle)).

Bootstrap. One ql.SpreadCdsHelper per pillar at the pillar's conventional
spread: tenor = the pillar, settlementDays = 1, WeekendsOnly, Quarterly,
Following, CDS2015, Actual360, the curve file's recovery, our discount
curve, settlesAccrual = True, paysAtDefaultTime = True, startDate = none,
lastPeriodDayCounter = Actual360(True), rebatesAccrual = True, model =
CreditDefaultSwap.ISDA (which is IsdaCdsEngine with Taylor, HalfDayBias,
Piecewise). settlementDays is 1, not 3, because the helper sets protection
start = evaluation date + settlementDays calendar days (our step-in, T+1)
and leaves the cash settlement at the CreditDefaultSwap default of 3
business days (our T+3): with 3 the protection would start two days late.
The helpers go into ql.PiecewiseFlatHazardRate(as_of, helpers,
Actual365Fixed()), QuantLib's evaluation date being as_of.

QuantLib puts each pillar's node at the adjusted maturity plus one day (the
helper's latestDate, incremented for the ISDA model), one to three days
after our node on the maturity itself, so its node hazards are not directly
ours. The comparison is therefore made on our pillar grid: from QuantLib's
survival curve, hazard_i = -ln(Q(t_i) / Q(t_{i-1})) / (t_i - t_{i-1}), the
constant hazard QuantLib's curve carries over our interval (t_{i-1}, t_i].
To show that the node placement is the whole of the difference, a second
set of rows repeats our sequential fit (the same objective, cds.pricer's
clean upfront at the conventional spread, the same contracts) with the
survival curve's nodes on QuantLib's dates instead of the maturities, and
compares those hazards with QuantLib's node hazards directly. The 5Y
contract is then priced on each side's own bootstrapped curve.

CS01. The 5Y conventional spread is bumped by 1 bp, both sides re-bootstrap
from the bumped spreads and reprice the 5Y contract; CS01 in currency is
N times the change in clean upfront per unit notional (the accrued does not
move with the spread, so this is the change in the dirty value too).

The trades (Section 7): 5Y buy at coupon 100 on IG_flat, 1Y and 10Y buy at
coupon 100 on IG_flat, 5Y buy at coupon 500 on HY_steep and on
distressed_inverted; N = 10,000,000; every trade at the curve's recovery.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date

import QuantLib as ql
from scipy.optimize import brentq

from cds.bootstrap import BootstrapResult, bootstrap, market_state, pillar_trade
from cds.conventions import CASH_SETTLE_BUSINESS_DAYS, DEFAULT_NOTIONAL, STEP_IN_DAYS
from cds.curves import DiscountCurve, RecoveryCurve, SurvivalCurve
from cds.pricer import HAZARD_BOUNDS, HAZARD_XTOL, cash_settle_date, price, value
from cds.schedule import cds_schedule, year_fraction_act365f
from cds.types import CDSTrade, MarketCurveQuotes, Quote

__all__ = [
    "BUMP_BP",
    "QL_FLAGS",
    "TRADES",
    "QLBootstrap",
    "QLPrice",
    "Row",
    "bootstrap_rows",
    "cs01_rows",
    "cs01_tolerance_usd",
    "from_ql",
    "hazards_on_grid",
    "pricer_rows",
    "ql_bootstrap",
    "ql_cds",
    "ql_discount_curve",
    "ql_engine",
    "ql_hazard_curve",
    "ql_price",
    "sequential_on_nodes",
    "to_ql",
    "validation_rows",
]

BP_PER_UNIT = 1e4
PERCENT = 100.0

# The IsdaCdsEngine flags, by name, so the review can quote them.
QL_FLAGS = {
    "numerical_fix": "Taylor",
    "accrual_bias": "HalfDayBias",
    "forwards_in_coupon_period": "Piecewise",
    "include_settlement_date_flows": False,
    "schedule_rule": "CDS2015",
    "calendar": "WeekendsOnly",
    "coupon_day_count": "Actual360",
    "last_period_day_count": "Actual360(includeLastDay=True)",
    "curve_day_count": "Actual365Fixed",
    "helper_settlement_days": STEP_IN_DAYS,
    "cash_settlement_days": CASH_SETTLE_BUSINESS_DAYS,
    "helper_model": "CreditDefaultSwap.ISDA",
}

# The Section 7 trades: (curve label, tenor, coupon in bp). Every trade is a
# protection buy on DEFAULT_NOTIONAL at the curve's recovery.
TRADES = (
    ("IG_flat", "5Y", 100.0),
    ("IG_flat", "1Y", 100.0),
    ("IG_flat", "10Y", 100.0),
    ("HY_steep", "5Y", 500.0),
    ("distressed_inverted", "5Y", 500.0),
)
CS01_TENOR = "5Y"

# The CS01 comparison bumps the 5Y conventional spread by this much.
BUMP_BP = 1.0

# Tolerances (BUILD_PLAN.md Section 7 criteria; the constants in
# tests/conftest.py hold the same values with their reasons and the tests
# assert against those). Held here too so Table 2 carries them.
TOL_UPFRONT_BP = 1.0  # clean upfront and PV_prot, bp of notional
TOL_PAR_SPREAD_BP = 0.5  # par spread, bp
TOL_HAZARD_BP = 0.5  # pillar hazard, bp of hazard
TOL_ANNUITY = 0.01  # risky annuity per unit spread: 1 bp of notional at a 100 bp coupon
TOL_CS01_REL = 0.01  # CS01: 1% of the CS01 ...
TOL_CS01_USD = 50.0  # ... or $50, whichever is larger


@dataclass(frozen=True)
class Row:
    """One Table 2 row. diff = ours - quantlib in the stated diff unit;
    passed is |diff| <= tolerance."""

    curve: str
    trade: str
    metric: str
    ours: float
    quantlib: float
    diff: float
    unit: str
    tolerance: float
    passed: bool


def _row(curve: str, trade: str, metric: str, ours: float, quantlib: float, diff: float, unit: str, tolerance: float) -> Row:
    return Row(curve, trade, metric, ours, quantlib, diff, unit, tolerance, abs(diff) <= tolerance)


def to_ql(d: date) -> ql.Date:
    return ql.Date(d.day, d.month, d.year)


def from_ql(d: ql.Date) -> date:
    return date(d.year(), d.month(), d.dayOfMonth())


def trade_label(tenor: str, coupon_bp: float) -> str:
    return f"{tenor}_buy_c{coupon_bp:g}"


# --- QuantLib objects from ours -----------------------------------------------


def ql_discount_curve(discount: DiscountCurve) -> ql.YieldTermStructureHandle:
    """Our nodes as a log-linear ql.DiscountCurve on Actual365Fixed time."""
    curve = ql.DiscountCurve([to_ql(discount.as_of), *map(to_ql, discount.node_dates)], [1.0, *discount.node_dfs], ql.Actual365Fixed())
    curve.enableExtrapolation()
    return ql.YieldTermStructureHandle(curve)


def ql_hazard_curve(survival: SurvivalCurve) -> ql.DefaultProbabilityTermStructureHandle:
    """Our pillars as a backward-flat ql.HazardRateCurve: hazard_i on
    (t_{i-1}, t_i], with the first hazard repeated at as_of."""
    hazards = survival.pillar_hazards
    curve = ql.HazardRateCurve([to_ql(survival.as_of), *map(to_ql, survival.pillar_dates)], [hazards[0], *hazards], ql.Actual365Fixed())
    curve.enableExtrapolation()
    return ql.DefaultProbabilityTermStructureHandle(curve)


def ql_schedule(step_in: date, maturity: date) -> ql.Schedule:
    return ql.Schedule(to_ql(step_in), to_ql(maturity), ql.Period("3M"), ql.WeekendsOnly(), ql.Following, ql.Unadjusted, ql.DateGeneration.CDS2015, False)


def ql_cds(trade: CDSTrade, as_of: date, notional: float = 1.0) -> ql.CreditDefaultSwap:
    """The contract as the module docstring lists it, valued on as_of."""
    schedule = cds_schedule(trade.trade_date, trade.maturity)
    side = ql.Protection.Buyer if trade.side == "buy" else ql.Protection.Seller
    return ql.CreditDefaultSwap(
        side,
        notional,
        trade.coupon_bp / BP_PER_UNIT,
        ql_schedule(schedule.step_in, trade.maturity),
        ql.Following,
        ql.Actual360(),
        True,  # settlesAccrual
        True,  # paysAtDefaultTime
        to_ql(schedule.step_in),
        ql.FaceValueClaim(),
        ql.Actual360(True),  # last period includes the maturity date
        True,  # rebatesAccrual
        to_ql(as_of),  # tradeDate
        CASH_SETTLE_BUSINESS_DAYS,
    )


def ql_engine(probability: ql.DefaultProbabilityTermStructureHandle, recovery: float, discount: ql.YieldTermStructureHandle) -> ql.IsdaCdsEngine:
    return ql.IsdaCdsEngine(probability, recovery, discount, False, ql.IsdaCdsEngine.Taylor, ql.IsdaCdsEngine.HalfDayBias, ql.IsdaCdsEngine.Piecewise)


@dataclass(frozen=True)
class QLPrice:
    """QuantLib's numbers for one contract, per unit notional at the cash
    settlement date, in the units of PriceResult."""

    clean_upfront_pct: float
    par_spread_bp: float
    pv_protection: float
    risky_annuity: float
    accrued: float  # per unit notional


def ql_price(discount: DiscountCurve, probability: ql.DefaultProbabilityTermStructureHandle, recovery: float, trade: CDSTrade, as_of: date) -> QLPrice:
    """Price the trade on a QuantLib survival curve (ours converted, or
    QuantLib's own bootstrap) and our discount curve."""
    ql.Settings.instance().evaluationDate = to_ql(as_of)
    cds = ql_cds(trade, as_of)
    cds.setPricingEngine(ql_engine(probability, recovery, ql_discount_curve(discount)))
    p_settle = discount.df_on(cash_settle_date(as_of))
    return QLPrice(
        clean_upfront_pct=PERCENT * cds.fairUpfront(),
        par_spread_bp=BP_PER_UNIT * cds.fairSpread(),
        pv_protection=cds.defaultLegNPV() / p_settle,
        risky_annuity=-cds.couponLegNPV() / (trade.coupon_bp / BP_PER_UNIT) / p_settle,
        accrued=cds.accrualRebate().amount(),
    )


# --- QuantLib's own bootstrap ---------------------------------------------------


@dataclass(frozen=True)
class QLBootstrap:
    """ql.PiecewiseFlatHazardRate from SpreadCdsHelpers. node_dates and
    node_hazards are QuantLib's own nodes (adjusted maturity + 1 day);
    pillar_hazards are the hazards its curve carries over our pillar
    intervals; pillar_survival is Q at our pillar dates."""

    curve: ql.DefaultProbabilityTermStructureHandle
    node_dates: tuple[date, ...]
    node_hazards: tuple[float, ...]
    pillar_dates: tuple[date, ...]
    pillar_hazards: tuple[float, ...]
    pillar_survival: tuple[float, ...]


def hazards_on_grid(as_of: date, pillar_dates: tuple[date, ...], survival_at: tuple[float, ...]) -> tuple[float, ...]:
    """The constant hazard per pillar interval implied by survival
    probabilities at the pillar dates: -ln(Q_i / Q_{i-1}) / (t_i - t_{i-1})."""
    out = []
    q_prev, t_prev = 1.0, 0.0
    for d, q in zip(pillar_dates, survival_at):
        t = year_fraction_act365f(as_of, d)
        out.append(-math.log(q / q_prev) / (t - t_prev))
        q_prev, t_prev = q, t
    return tuple(out)


def ql_bootstrap(
    quotes: MarketCurveQuotes,
    discount: DiscountCurve,
    spreads_bp: tuple[float, ...],
    pillar_dates: tuple[date, ...],
    settlement_days: int = STEP_IN_DAYS,
) -> QLBootstrap:
    """QuantLib's bootstrap of the conventional spreads, flags as in the
    module docstring. settlement_days is the helper's argument (protection
    start = as_of + settlement_days calendar days); the default is our
    step-in and the test shows what 3 would do."""
    as_of = quotes.as_of
    ql.Settings.instance().evaluationDate = to_ql(as_of)
    disc = ql_discount_curve(discount)
    helpers = [
        ql.SpreadCdsHelper(
            ql.QuoteHandle(ql.SimpleQuote(s / BP_PER_UNIT)),
            ql.Period(tenor),
            settlement_days,  # protection start = as_of + settlement_days calendar days
            ql.WeekendsOnly(),
            ql.Quarterly,
            ql.Following,
            ql.DateGeneration.CDS2015,
            ql.Actual360(),
            quotes.recovery,
            disc,
            True,  # settlesAccrual
            True,  # paysAtDefaultTime
            ql.Date(),  # startDate: none, the helper derives the schedule
            ql.Actual360(True),
            True,  # rebatesAccrual
            ql.CreditDefaultSwap.ISDA,
        )
        for tenor, s in zip(quotes.pillars, spreads_bp)
    ]
    curve = ql.PiecewiseFlatHazardRate(to_ql(as_of), helpers, ql.Actual365Fixed())
    curve.enableExtrapolation()
    nodes = curve.nodes()[1:]  # the first node is as_of itself
    survival_at = tuple(curve.survivalProbability(to_ql(d)) for d in pillar_dates)
    return QLBootstrap(
        curve=ql.DefaultProbabilityTermStructureHandle(curve),
        node_dates=tuple(from_ql(d) for d, _ in nodes),
        node_hazards=tuple(float(h) for _, h in nodes),
        pillar_dates=tuple(pillar_dates),
        pillar_hazards=hazards_on_grid(as_of, pillar_dates, survival_at),
        pillar_survival=survival_at,
    )


def sequential_on_nodes(quotes: MarketCurveQuotes, discount: DiscountCurve, spreads_bp: tuple[float, ...], node_dates: tuple[date, ...]) -> tuple[float, ...]:
    """Our sequential bootstrap (cds.bootstrap's objective: the clean upfront
    of the pillar contract at its conventional spread) with the survival
    curve's nodes on node_dates rather than on the pillar maturities. Used
    only to match QuantLib's node placement for the comparison."""
    as_of = quotes.as_of
    recovery = RecoveryCurve.flat(quotes.recovery, as_of)
    lo, hi = HAZARD_BOUNDS
    hazards: list[float] = []
    for i, s_i in enumerate(spreads_bp):
        trade = pillar_trade(quotes, i, s_i)
        dates = node_dates[: i + 1]

        def objective(hazard: float) -> float:
            survival = SurvivalCurve(as_of=as_of, pillar_dates=dates, pillar_hazards=(*hazards, hazard))
            return value(discount, survival, recovery, trade, as_of).clean_upfront

        hazards.append(float(brentq(objective, lo, hi, xtol=HAZARD_XTOL)))
    return tuple(hazards)


def _spread_quotes(quotes: MarketCurveQuotes, spreads_bp: tuple[float, ...]) -> MarketCurveQuotes:
    """The curve restated as par-spread quotes at the given spreads: how a
    bump to a conventional spread is fed back to the bootstrap."""
    return MarketCurveQuotes(
        as_of=quotes.as_of,
        pillars=quotes.pillars,
        quotes=tuple(Quote(kind="par_spread_bp", value=float(s)) for s in spreads_bp),
        recovery=quotes.recovery,
        label=quotes.label,
    )


# --- the three comparisons, as rows -------------------------------------------


def pricer_rows(result: BootstrapResult, discount: DiscountCurve, tenor: str, coupon_bp: float) -> list[Row]:
    """Pricer comparison: our bootstrapped curve handed to QuantLib, one
    trade, four metrics."""
    quotes = result.quotes
    state = market_state(result, discount)
    trade = pillar_trade(quotes, quotes.pillars.index(tenor), coupon_bp)
    ours = price(state, trade)
    theirs = ql_price(discount, ql_hazard_curve(result.survival), quotes.recovery, trade, quotes.as_of)
    label = trade_label(tenor, coupon_bp)
    return [
        _row(quotes.label, label, "clean_upfront_pct", ours.clean_upfront_pct, theirs.clean_upfront_pct, BP_PER_UNIT / PERCENT * (ours.clean_upfront_pct - theirs.clean_upfront_pct), "bp_of_notional", TOL_UPFRONT_BP),
        _row(quotes.label, label, "par_spread_bp", ours.par_spread_bp, theirs.par_spread_bp, ours.par_spread_bp - theirs.par_spread_bp, "bp", TOL_PAR_SPREAD_BP),
        _row(quotes.label, label, "pv_protection", ours.pv_protection, theirs.pv_protection, BP_PER_UNIT * (ours.pv_protection - theirs.pv_protection), "bp_of_notional", TOL_UPFRONT_BP),
        _row(quotes.label, label, "risky_annuity", ours.risky_annuity, theirs.risky_annuity, ours.risky_annuity - theirs.risky_annuity, "per_unit_spread", TOL_ANNUITY),
    ]


def bootstrap_rows(result: BootstrapResult, discount: DiscountCurve, coupon_bp: float) -> tuple[list[Row], QLBootstrap]:
    """Bootstrap comparison: one hazard row per pillar on our pillar grid
    ("bootstrap"), one per pillar with our fit moved onto QuantLib's nodes
    ("bootstrap_quantlib_nodes"), in percent with the diff in bp of hazard,
    and the 5Y clean upfront priced on each side's own curve."""
    quotes = result.quotes
    theirs = ql_bootstrap(quotes, discount, result.conventional_spreads_bp, result.pillar_dates)
    rows = [
        _row(quotes.label, "bootstrap", f"hazard_pct_{pillar}", PERCENT * ours, PERCENT * ql_h, BP_PER_UNIT * (ours - ql_h), "bp_of_hazard", TOL_HAZARD_BP)
        for pillar, ours, ql_h in zip(quotes.pillars, result.pillar_hazards, theirs.pillar_hazards)
    ]
    on_nodes = sequential_on_nodes(quotes, discount, result.conventional_spreads_bp, theirs.node_dates)
    rows += [
        _row(quotes.label, "bootstrap_quantlib_nodes", f"hazard_pct_{pillar}", PERCENT * ours, PERCENT * ql_h, BP_PER_UNIT * (ours - ql_h), "bp_of_hazard", TOL_HAZARD_BP)
        for pillar, ours, ql_h in zip(quotes.pillars, on_nodes, theirs.node_hazards)
    ]
    trade = pillar_trade(quotes, quotes.pillars.index(CS01_TENOR), coupon_bp)
    ours_5y = price(market_state(result, discount), trade).clean_upfront_pct
    theirs_5y = ql_price(discount, theirs.curve, quotes.recovery, trade, quotes.as_of).clean_upfront_pct
    rows.append(_row(quotes.label, trade_label(CS01_TENOR, coupon_bp) + "_own_bootstrap", "clean_upfront_pct", ours_5y, theirs_5y, BP_PER_UNIT / PERCENT * (ours_5y - theirs_5y), "bp_of_notional", TOL_UPFRONT_BP))
    return rows, theirs


def cs01_tolerance_usd(cs01_usd: float) -> float:
    """1% of the CS01 or $50, whichever is larger."""
    return max(TOL_CS01_REL * abs(cs01_usd), TOL_CS01_USD)


def cs01_rows(result: BootstrapResult, discount: DiscountCurve, coupon_bp: float, notional: float = DEFAULT_NOTIONAL) -> list[Row]:
    """CS01 comparison: bump the 5Y conventional spread by BUMP_BP,
    re-bootstrap on both sides, reprice the 5Y buy."""
    quotes = result.quotes
    i = quotes.pillars.index(CS01_TENOR)
    trade = pillar_trade(quotes, i, coupon_bp)
    base = result.conventional_spreads_bp
    bumped = tuple(s + (BUMP_BP if k == i else 0.0) for k, s in enumerate(base))

    ours_base = price(market_state(result, discount), trade).clean_upfront_pct
    ours_bumped = price(market_state(bootstrap(_spread_quotes(quotes, bumped), discount), discount), trade).clean_upfront_pct
    ours_cs01 = notional / PERCENT * (ours_bumped - ours_base)

    ql_base = ql_price(discount, ql_bootstrap(quotes, discount, base, result.pillar_dates).curve, quotes.recovery, trade, quotes.as_of).clean_upfront_pct
    ql_bumped = ql_price(discount, ql_bootstrap(quotes, discount, bumped, result.pillar_dates).curve, quotes.recovery, trade, quotes.as_of).clean_upfront_pct
    ql_cs01 = notional / PERCENT * (ql_bumped - ql_base)
    return [_row(quotes.label, trade_label(CS01_TENOR, coupon_bp), "cs01_usd", ours_cs01, ql_cs01, ours_cs01 - ql_cs01, "usd", cs01_tolerance_usd(ours_cs01))]


def validation_rows(results: dict[str, BootstrapResult], discount: DiscountCurve) -> list[Row]:
    """Every Table 2 row: the pricer rows for each trade in TRADES, then per
    curve the bootstrap rows and the CS01 row at that curve's 5Y coupon."""
    rows: list[Row] = []
    for label, tenor, coupon_bp in TRADES:
        rows.extend(pricer_rows(results[label], discount, tenor, coupon_bp))
    for label, tenor, coupon_bp in TRADES:
        if tenor != CS01_TENOR:
            continue
        rows.extend(bootstrap_rows(results[label], discount, coupon_bp)[0])
        rows.extend(cs01_rows(results[label], discount, coupon_bp))
    return rows
