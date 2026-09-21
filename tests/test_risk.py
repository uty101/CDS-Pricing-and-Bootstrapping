"""Section 8: the risk report (BUILD_PLAN.md Section 8, criteria 1 to 6),
Table 3 and Chart 2.

The states are the Section 6 curves bootstrapped on the Section 2 discount
curve; every measure is cds.risk's. Seasoned trades are priced against
QuantLib's IsdaCdsEngine (imported in the test only) at valuation dates
after the trade date, with includeSettlementDateFlows = True so that a
coupon paying on as_of + 1 is included as our rule has it
(docs/CONVENTIONS_RESOLVED.md item 22).
"""

from __future__ import annotations

import math
from dataclasses import fields, replace
from datetime import date, timedelta
from pathlib import Path

import matplotlib.image
import pandas as pd
import pytest

from cds import report
from cds.bootstrap import BootstrapResult, bootstrap, market_curve_quotes_from_file, market_state, pillar_trade
from cds.conventions import ACT360_BASIS, DEFAULT_NOTIONAL, PILLARS, RECOVERY_SENIOR
from cds.curves import DiscountCurve, discount_curve_from_file, par_rate_from_curve
from cds.pricer import cash_settle_date, price, value
from cds.risk import (
    BUMP_RECOVERY,
    accrued_to_valuation_date,
    add_calendar_months,
    coupon_cash_in_window,
    cs01_by_pillar,
    ir01,
    jtd,
    rec01,
    rec01_hazard_fixed,
    risk,
    shifted_state,
    theta,
)
from cds.schedule import cds_schedule
from cds.types import CDSTrade, MarketCurveQuotes, Quote, RiskReport
from tests.conftest import (
    CHART_2_PAR_FLAT_USD,
    CS01_CENTRAL_ABS_USD,
    CS01_CENTRAL_REL_TOL,
    CS01_SUM_REL_TOL,
    IR01_DISTRESSED_10Y_MIN_USD,
    IR01_DISTRESSED_MIN_USD,
    IR01_IG_MAX_USD,
    JTD_ABS_USD,
    PRICER_IDENTITY_ABS_TOL,
    QL_SEASONED_ABS_TOL,
    REC01_HAZARD_FIXED_REL_TOL,
    REC01_HAZARD_FIXED_SAME_REL_TOL,
    REC01_OFFMARKET_MULT,
    REC01_PAR_USD,
    THETA_FLAT_USD,
    THETA_STEEP_USD,
    assert_output_current,
    assert_output_value,
)
from tests.test_legs import RATES_FILE

ROOT = Path(__file__).resolve().parent.parent
CURVES_DIR = ROOT / "data" / "curves"
NAMED_CURVES = ("IG_flat", "HY_steep", "distressed_inverted")
COUPONS_BP = report.STANDARD_COUPONS_BY_CURVE

BP_PER_UNIT = 1e4
PERCENT = 100.0
ONE_DAY = timedelta(days=1)

# Criterion 2: the off-market running-spread trades. The plan says s_par -
# 200 bp; on IG the 5Y par spread is 90 bp, so the IG trade is struck 200
# bp above and the HY one (par 500 bp) 200 bp below.
OFFMARKET = (("IG_flat", +200.0), ("HY_steep", -200.0))

# Criterion 3: the in-test flat curve, 100 bp on every pillar, R = 0.40, on
# a discount curve with one continuously compounded rate at every node.
FLAT_SPREAD_BP = 100.0
FLAT_RATE = 0.045

# Item 22: seasoned valuation dates for the HY 5Y trade dated 15 Sep 2026,
# whose payment dates are 21 Sep 2026, 21 Dec 2026 (20 Dec is a Sunday),
# 22 Mar 2027, ... The list includes the day before a payment date (20 Dec
# 2026, the item 22 case), the payment date itself, the day after, a
# coupon date that is a business day, and two days before maturity.
SEASONED_DATES = (
    date(2026, 10, 15),
    date(2026, 12, 18),
    date(2026, 12, 20),
    date(2026, 12, 21),
    date(2026, 12, 22),
    date(2027, 3, 19),
    date(2028, 6, 20),
    date(2031, 6, 18),
)
DAY_BEFORE_PAYMENT = date(2026, 12, 20)

# Table 3 and Chart 2 geometry.
CHART_SIZE = (900, 1600)  # rows, columns of the PNG


@pytest.fixture(scope="module")
def discount() -> DiscountCurve:
    return discount_curve_from_file(RATES_FILE)


@pytest.fixture(scope="module")
def results(discount: DiscountCurve) -> dict[str, BootstrapResult]:
    return {label: bootstrap(market_curve_quotes_from_file(CURVES_DIR / f"{label}.json"), discount) for label in NAMED_CURVES}


@pytest.fixture(scope="module")
def reports(results: dict[str, BootstrapResult], discount: DiscountCurve) -> dict[str, RiskReport]:
    return {label: risk(market_state(r, discount), _five_year(r, COUPONS_BP[label])) for label, r in results.items()}


def _five_year(r: BootstrapResult, coupon_bp: float, side: str = "buy") -> CDSTrade:
    return replace(pillar_trade(r.quotes, r.quotes.pillars.index("5Y"), coupon_bp), side=side)


def _running(trade: CDSTrade, coupon_bp: float) -> CDSTrade:
    """A running-spread contract at coupon_bp (Part B item 8)."""
    return replace(trade, coupon_bp=coupon_bp, quote=Quote(kind="par_spread_bp", value=coupon_bp))


def _flat_discount(discount: DiscountCurve) -> DiscountCurve:
    """exp(-r t) at every node of the Section 2 curve, carrying the par
    rates it implies so IR01 can rebuild it (bootstrap_ois reproduces the
    nodes from those rates)."""
    dfs = tuple(math.exp(-FLAT_RATE * t) for t in discount.node_times)
    bare = DiscountCurve(as_of=discount.as_of, node_dates=discount.node_dates, node_dfs=dfs)
    pars = tuple(par_rate_from_curve(bare, tenor) for tenor in discount.tenors)
    return DiscountCurve(as_of=discount.as_of, node_dates=discount.node_dates, node_dfs=dfs, tenors=discount.tenors, par_rates_pct=pars)


@pytest.fixture(scope="module")
def flat(discount: DiscountCurve):
    """The criterion 3 state and its 5Y trade at coupon 100."""
    flat_discount = _flat_discount(discount)
    quotes = MarketCurveQuotes(as_of=discount.as_of, pillars=PILLARS, quotes=tuple(Quote(kind="par_spread_bp", value=FLAT_SPREAD_BP) for _ in PILLARS), recovery=RECOVERY_SENIOR, label="flat100")
    r = bootstrap(quotes, flat_discount)
    return market_state(r, flat_discount), _five_year(r, FLAT_SPREAD_BP)


# --- criterion 1: bucketed CS01 against parallel --------------------------------


@pytest.mark.parametrize("label", NAMED_CURVES)
def test_cs01_bucket_sum_is_within_2pct_of_parallel(reports: dict[str, RiskReport], label: str) -> None:
    rep = reports[label]
    buckets = [getattr(rep, f"cs01_{p.lower()}") for p in PILLARS]
    assert abs(rep.cs01_bucket_sum - sum(buckets)) < PRICER_IDENTITY_ABS_TOL * DEFAULT_NOTIONAL
    assert abs(rep.cs01_bucket_sum - rep.cs01_parallel) <= CS01_SUM_REL_TOL * abs(rep.cs01_parallel)
    assert rep.cs01_parallel > 0.0  # the buyer gains when spreads widen
    # A sequential bootstrap: pillars beyond the 5Y maturity cannot move the trade.
    assert rep.cs01_7y == 0.0 and rep.cs01_10y == 0.0
    assert rep.cs01_5y > 0.0


# --- criterion 2: rec01 at par and off market -----------------------------------


@pytest.mark.parametrize("label,offset_bp", OFFMARKET, ids=[f"{c}{o:+g}" for c, o in OFFMARKET])
def test_rec01_is_near_zero_at_par_and_grows_off_market(results: dict[str, BootstrapResult], discount: DiscountCurve, label: str, offset_bp: float) -> None:
    r = results[label]
    state = market_state(r, discount)
    s_par = price(state, _five_year(r, COUPONS_BP[label])).par_spread_bp
    par, off = _running(_five_year(r, s_par), s_par), _running(_five_year(r, s_par), s_par + offset_bp)
    spreads = r.conventional_spreads_bp
    rec_par, rec_off = rec01(state, par, spreads_bp=spreads), rec01(state, off, spreads_bp=spreads)
    assert abs(rec_par) < REC01_PAR_USD
    assert abs(rec_off) >= REC01_OFFMARKET_MULT * abs(rec_par)
    # (s_mkt - c) dA N: the sign follows the side of the strike.
    assert (rec_off > 0.0) == (offset_bp > 0.0)
    hf_par, hf_off = rec01_hazard_fixed(state, par), rec01_hazard_fixed(state, off)
    assert abs(hf_par - hf_off) <= REC01_HAZARD_FIXED_SAME_REL_TOL * abs(hf_par)
    v = value(discount, state.survival, state.recovery, par, state.as_of)
    expected = -BUMP_RECOVERY * v.legs.protection * v.d_settle * par.notional  # -0.01 I N, at the settlement date
    assert abs(hf_par - expected) <= REC01_HAZARD_FIXED_REL_TOL * abs(expected)
    assert hf_par < 0.0


def test_rec01_hazard_fixed_negates_for_the_seller(results: dict[str, BootstrapResult], discount: DiscountCurve) -> None:
    r = results["IG_flat"]
    state = market_state(r, discount)
    buy, sell = _five_year(r, 100.0), _five_year(r, 100.0, side="sell")
    assert rec01_hazard_fixed(state, buy) == -rec01_hazard_fixed(state, sell)


# --- criterion 3: the two thetas ---------------------------------------------------


def test_thetas_agree_on_a_flat_curve_and_differ_on_hy(flat, reports: dict[str, RiskReport]) -> None:
    state, trade = flat
    rep = risk(state, trade)
    assert abs(rep.theta_calendar_1m - rep.theta_rolldown_1m) <= THETA_FLAT_USD
    assert abs(rep.theta_calendar_1d - rep.theta_rolldown_1d) <= THETA_FLAT_USD
    assert abs(reports["HY_steep"].theta_calendar_1m - reports["HY_steep"].theta_rolldown_1m) > THETA_STEEP_USD
    # Rolling down an upward-sloping curve costs the buyer more than the calendar alone.
    assert reports["HY_steep"].theta_rolldown_1m < reports["HY_steep"].theta_calendar_1m < 0.0
    assert reports["IG_flat"].theta_rolldown_1m < reports["IG_flat"].theta_calendar_1m < 0.0
    # On the flat curve the two thetas are the protection consumed: (1 - R) lambda N dt, to a few percent.
    t_1m = add_calendar_months(state.as_of, 1)
    consumed = -(1.0 - RECOVERY_SENIOR) * state.survival.pillar_hazards[0] * trade.notional * (t_1m - state.as_of).days / 365.0
    assert abs(rep.theta_calendar_1m - consumed) < 0.05 * abs(consumed)


def test_theta_is_the_dirty_mtm_change_plus_the_coupon_in_the_window(results: dict[str, BootstrapResult], discount: DiscountCurve) -> None:
    """A window that crosses a payment date: 21 Nov to 21 Dec 2026 holds the
    21 Dec coupon; the buyer's theta subtracts it and the seller's adds it."""
    r = results["IG_flat"]
    buy, sell = _five_year(r, 100.0), _five_year(r, 100.0, side="sell")
    t0, t1 = date(2026, 11, 21), date(2026, 12, 21)
    state = shifted_state(market_state(r, discount), t0, "calendar")
    schedule = cds_schedule(buy.trade_date, buy.maturity)
    cash = coupon_cash_in_window(buy, schedule, t0, t1)
    assert cash == pytest.approx(0.01 * DEFAULT_NOTIONAL * schedule.accrual_fraction[1])
    assert schedule.payment[1] == t1 and coupon_cash_in_window(buy, schedule, t0, t1 - ONE_DAY) == 0.0
    later = shifted_state(state, t1, "calendar")
    d_mtm = price(later, buy).mtm - price(state, buy).mtm
    assert theta(state, buy, t1, "calendar") == pytest.approx(d_mtm - cash)
    assert theta(state, sell, t1, "calendar") == pytest.approx(-(d_mtm - cash))
    with pytest.raises(ValueError):
        theta(state, buy, t0, "calendar")


def test_shift_modes_move_the_curves_as_part_c_item_3_says(results: dict[str, BootstrapResult], discount: DiscountCurve) -> None:
    state = market_state(results["HY_steep"], discount)
    t1 = add_calendar_months(state.as_of, 1)
    cal, ten = shifted_state(state, t1, "calendar"), shifted_state(state, t1, "tenor")
    assert cal.as_of == ten.as_of == cal.discount.as_of == cal.survival.as_of == cal.recovery.as_of == t1
    assert cal.survival.pillar_dates == state.survival.pillar_dates  # nodes on their dates
    assert ten.survival.pillar_dates == tuple(d + (t1 - state.as_of) for d in state.survival.pillar_dates)  # nodes at their tenors
    assert ten.survival.pillar_hazards == state.survival.pillar_hazards and ten.discount.node_dfs == state.discount.node_dfs
    assert cal.discount.node_dates == tuple(d for d in state.discount.node_dates if d > t1)  # the 1M node has passed
    assert cal.quotes.as_of == ten.quotes.as_of == t1


def test_add_calendar_months_keeps_the_day_and_clips() -> None:
    assert add_calendar_months(date(2026, 9, 15), 1) == date(2026, 10, 15)
    assert add_calendar_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_calendar_months(date(2026, 12, 15), 1) == date(2027, 1, 15)
    assert add_calendar_months(date(2026, 9, 15), 12) == date(2027, 9, 15)


# --- criterion 4: JTD -------------------------------------------------------------------


@pytest.mark.parametrize("label", NAMED_CURVES)
def test_jtd_is_loss_given_default_less_mtm_less_accrued(results: dict[str, BootstrapResult], discount: DiscountCurve, reports: dict[str, RiskReport], label: str) -> None:
    r = results[label]
    state = market_state(r, discount)
    buy, sell = _five_year(r, COUPONS_BP[label]), _five_year(r, COUPONS_BP[label], side="sell")
    schedule = cds_schedule(buy.trade_date, buy.maturity)
    days = accrued_to_valuation_date(schedule, state.as_of)
    assert days == (state.as_of - schedule.accrual_start[0]).days == 85  # 22 Jun to 15 Sep 2026
    accrued = buy.coupon_bp / BP_PER_UNIT * buy.notional * days / ACT360_BASIS
    expected = (1.0 - buy.recovery) * buy.notional - reports[label].mtm - accrued
    assert abs(reports[label].jtd - expected) <= JTD_ABS_USD
    assert abs(jtd(state, sell) + reports[label].jtd) <= JTD_ABS_USD


def test_jtd_uses_the_unwind_value_so_the_inception_cash_of_an_upfront_trade_is_sunk(results: dict[str, BootstrapResult], discount: DiscountCurve) -> None:
    """Item 44: the distressed 5Y buy at coupon 500, quoted as an upfront,
    valued a month after its trade date on the calendar-shifted curves.
    Two inception upfronts 5 points apart move PriceResult.mtm by 5% of
    notional and JTD by nothing; both JTDs equal the quote = None number."""
    r = results["distressed_inverted"]
    as_of = add_calendar_months(r.quotes.as_of, 1)
    state = shifted_state(market_state(r, discount), as_of, "calendar")
    unquoted = _five_year(r, 500.0)
    paid_20 = replace(unquoted, quote=Quote(kind="upfront_pct", value=20.0, coupon_bp=500.0))
    paid_25 = replace(unquoted, quote=Quote(kind="upfront_pct", value=25.0, coupon_bp=500.0))
    mtm_20, mtm_25 = price(state, paid_20).mtm, price(state, paid_25).mtm
    assert mtm_20 - mtm_25 == pytest.approx(0.05 * DEFAULT_NOTIONAL)  # the inception cash differs by 5 points
    assert jtd(state, paid_20) == pytest.approx(jtd(state, paid_25), abs=JTD_ABS_USD)
    assert jtd(state, paid_20) == pytest.approx(jtd(state, unquoted), abs=JTD_ABS_USD)
    schedule = cds_schedule(unquoted.trade_date, unquoted.maturity)
    accrued = 500.0 / BP_PER_UNIT * DEFAULT_NOTIONAL * accrued_to_valuation_date(schedule, as_of) / ACT360_BASIS
    assert jtd(state, paid_20) == pytest.approx((1.0 - unquoted.recovery) * DEFAULT_NOTIONAL - price(state, unquoted).mtm - accrued, abs=JTD_ABS_USD)
    assert jtd(state, replace(paid_20, side="sell")) == pytest.approx(-jtd(state, paid_20), abs=JTD_ABS_USD)


def test_accrued_to_valuation_date_stops_at_as_of_where_the_pricer_goes_one_day_on(results: dict[str, BootstrapResult]) -> None:
    trade = _five_year(results["IG_flat"], 100.0)
    schedule = cds_schedule(trade.trade_date, trade.maturity)
    assert accrued_to_valuation_date(schedule, trade.trade_date) == schedule.accrued_days - 1
    assert accrued_to_valuation_date(schedule, date(2026, 12, 21)) == 0  # the period starting 21 Dec
    assert accrued_to_valuation_date(schedule, date(2026, 12, 20)) == 90  # still the first period
    assert accrued_to_valuation_date(schedule, schedule.accrual_start[0] - ONE_DAY) == 0


# --- criterion 5: IR01 ----------------------------------------------------------------


def test_ir01_small_on_the_ig_par_trade_and_larger_on_the_distressed_upfront_trades(results: dict[str, BootstrapResult], discount: DiscountCurve, reports: dict[str, RiskReport]) -> None:
    """Criterion 5 as rewritten (item 41): under $200 on the IG 5Y par
    trade, over $300 on the distressed 5Y upfront trade, over $500 on the
    distressed 10Y."""
    ig, distressed = reports["IG_flat"].ir01, reports["distressed_inverted"].ir01
    assert abs(ig) < IR01_IG_MAX_USD
    assert abs(distressed) > IR01_DISTRESSED_MIN_USD
    assert distressed < 0.0  # the buyer holds a $1.94m receivable; higher rates discount it more
    r = results["distressed_inverted"]
    ten_year = replace(pillar_trade(r.quotes, r.quotes.pillars.index("10Y"), 500.0), side="buy")
    distressed_10y = ir01(market_state(r, discount), ten_year, spreads_bp=r.conventional_spreads_bp)
    assert abs(distressed_10y) > IR01_DISTRESSED_10Y_MIN_USD
    assert distressed_10y < distressed < 0.0  # the longer receivable has the larger duration


def test_ir01_rebuilds_the_discount_curve_from_its_par_rates(results: dict[str, BootstrapResult], discount: DiscountCurve) -> None:
    r = results["IG_flat"]
    state = market_state(r, discount)
    trade = _five_year(r, 100.0)
    assert ir01(state, trade, spreads_bp=r.conventional_spreads_bp) == pytest.approx(ir01(state, trade))
    bare = DiscountCurve(as_of=discount.as_of, node_dates=discount.node_dates, node_dfs=discount.node_dfs)
    with pytest.raises(ValueError):
        ir01(replace(state, discount=bare), trade)


# --- criterion 6: central against one-sided CS01 --------------------------------


def test_central_cs01_is_within_1pct_of_one_sided_on_ig(reports: dict[str, RiskReport]) -> None:
    rep = reports["IG_flat"]
    for p in PILLARS:
        one_sided, central = getattr(rep, f"cs01_{p.lower()}"), getattr(rep, f"cs01_central_{p.lower()}")
        assert abs(central - one_sided) <= max(CS01_CENTRAL_REL_TOL * abs(one_sided), CS01_CENTRAL_ABS_USD), p
    assert abs(rep.cs01_central_parallel - rep.cs01_parallel) <= CS01_CENTRAL_REL_TOL * abs(rep.cs01_parallel)
    # The buyer is short convexity: the down bump loses more than the up bump gains.
    assert rep.cs01_central_5y > rep.cs01_5y


# --- the report as a whole ----------------------------------------------------------


def test_risk_report_fields_are_the_plans_in_order() -> None:
    names = [f.name for f in fields(RiskReport)]
    assert names[:10] == ["mtm", *(f"cs01_{p.lower()}" for p in PILLARS), "cs01_bucket_sum"]
    assert names[10:20] == ["cs01_parallel", *(f"cs01_central_{p.lower()}" for p in PILLARS), "cs01_central_parallel"]
    assert names[20:] == ["rec01", "rec01_hazard_fixed", "ir01", "jtd", "theta_calendar_1d", "theta_rolldown_1d", "theta_calendar_1m", "theta_rolldown_1m"]
    assert report.TABLE_3_COLUMNS == ("curve", "trade", *names)


def test_seller_report_is_the_negative_of_the_buyers(results: dict[str, BootstrapResult], discount: DiscountCurve, reports: dict[str, RiskReport]) -> None:
    r = results["HY_steep"]
    sell = risk(market_state(r, discount), _five_year(r, 500.0, side="sell"))
    for f in fields(RiskReport):
        assert getattr(sell, f.name) == pytest.approx(-getattr(reports["HY_steep"], f.name), abs=PRICER_IDENTITY_ABS_TOL * DEFAULT_NOTIONAL), f.name


def test_risk_refuses_a_state_that_is_not_its_own_bootstrap(results: dict[str, BootstrapResult], discount: DiscountCurve) -> None:
    r = results["IG_flat"]
    state = market_state(r, discount)
    trade = _five_year(r, 100.0)
    scaled = replace(state.survival, pillar_hazards=tuple(1.01 * h for h in state.survival.pillar_hazards))
    with pytest.raises(ValueError):
        risk(replace(state, survival=scaled), trade)
    with pytest.raises(ValueError):
        risk(state, replace(trade, recovery=0.41))
    with pytest.raises(ValueError):
        cs01_by_pillar(state, trade, spreads_bp=r.conventional_spreads_bp[:-1])


# --- item 22: seasoned trades against QuantLib ------------------------------------


def _ql_npv_per_notional(state, trade: CDSTrade, include_settlement_date_flows: bool) -> float:
    """QuantLib's NPV of the trade on our curves at state.as_of, divided by
    P(t_settle) so it is stated where our mtm is."""
    import QuantLib as ql

    def to_ql(d: date) -> ql.Date:
        return ql.Date(d.day, d.month, d.year)

    as_of = state.as_of
    ql.Settings.instance().evaluationDate = to_ql(as_of)
    ql_discount = ql.DiscountCurve([to_ql(as_of), *map(to_ql, state.discount.node_dates)], [1.0, *state.discount.node_dfs], ql.Actual365Fixed())
    ql_discount.enableExtrapolation()
    hazards = state.survival.pillar_hazards
    ql_hazard = ql.HazardRateCurve([to_ql(as_of), *map(to_ql, state.survival.pillar_dates)], [hazards[0], *hazards], ql.Actual365Fixed())
    ql_hazard.enableExtrapolation()
    schedule = cds_schedule(trade.trade_date, trade.maturity)
    ql_schedule = ql.Schedule(to_ql(schedule.step_in), to_ql(trade.maturity), ql.Period("3M"), ql.WeekendsOnly(), ql.Following, ql.Unadjusted, ql.DateGeneration.CDS2015, False)
    cds = ql.CreditDefaultSwap(
        ql.Protection.Buyer if trade.side == "buy" else ql.Protection.Seller, 1.0, trade.coupon_bp / BP_PER_UNIT, ql_schedule, ql.Following, ql.Actual360(), True, True,
        to_ql(schedule.step_in), ql.FaceValueClaim(), ql.Actual360(True), True, to_ql(trade.trade_date), 3,
    )
    cds.setPricingEngine(
        ql.IsdaCdsEngine(
            ql.DefaultProbabilityTermStructureHandle(ql_hazard), trade.recovery, ql.YieldTermStructureHandle(ql_discount),
            include_settlement_date_flows, ql.IsdaCdsEngine.Taylor, ql.IsdaCdsEngine.HalfDayBias, ql.IsdaCdsEngine.Piecewise,
        )
    )
    return cds.NPV() / state.discount.df_on(cash_settle_date(as_of))


@pytest.mark.parametrize("as_of", SEASONED_DATES, ids=[d.isoformat() for d in SEASONED_DATES])
def test_seasoned_trade_matches_quantlib_with_settlement_date_flows_included(results: dict[str, BootstrapResult], discount: DiscountCurve, as_of: date) -> None:
    """The HY 5Y buy valued after its trade date on the calendar-shifted
    curves: our mtm per unit notional equals QuantLib's NPV / P(t_settle)
    with includeSettlementDateFlows = True on every date, including the
    day before a payment date."""
    r = results["HY_steep"]
    trade = _five_year(r, 500.0)
    state = shifted_state(market_state(r, discount), as_of, "calendar")
    ours = price(state, trade).mtm / trade.notional
    assert abs(ours - _ql_npv_per_notional(state, trade, True)) < QL_SEASONED_ABS_TOL
    if as_of != DAY_BEFORE_PAYMENT:
        assert abs(ours - _ql_npv_per_notional(state, trade, False)) < QL_SEASONED_ABS_TOL


def test_quantlib_default_flag_drops_the_coupon_paying_on_as_of_plus_one(results: dict[str, BootstrapResult], discount: DiscountCurve) -> None:
    """Item 22: with includeSettlementDateFlows = False QuantLib excludes the
    coupon paying on as_of + 1; our rule includes it, and the gap is that
    coupon's discounted survival-weighted amount, a full quarter of 500 bp."""
    r = results["HY_steep"]
    trade = _five_year(r, 500.0)
    state = shifted_state(market_state(r, discount), DAY_BEFORE_PAYMENT, "calendar")
    schedule = cds_schedule(trade.trade_date, trade.maturity)
    assert schedule.payment[1] == DAY_BEFORE_PAYMENT + ONE_DAY
    ours = price(state, trade).mtm / trade.notional
    gap = _ql_npv_per_notional(state, trade, False) - ours
    coupon = trade.coupon_bp / BP_PER_UNIT * schedule.accrual_fraction[1]
    assert 0.9 * coupon < gap < 1.1 * coupon  # the buyer's mtm is lower by the coupon it still owes


# --- Table 3 and Chart 2 ------------------------------------------------------------


def test_table_3_is_current_and_has_the_fixed_columns(results: dict[str, BootstrapResult], discount: DiscountCurve, reports: dict[str, RiskReport], tmp_path: Path) -> None:
    fresh = report.table_3_risk_report([results[k] for k in NAMED_CURVES], discount, out_dir=tmp_path)
    assert tuple(fresh.columns) == report.TABLE_3_COLUMNS
    assert list(fresh["curve"]) == list(NAMED_CURVES)
    assert list(fresh["trade"]) == ["5Y_buy_c100", "5Y_buy_c500", "5Y_buy_c500"]
    committed = report.TABLES_DIR / "table_3_risk_report.csv"
    assert_output_current(tmp_path / "table_3_risk_report.csv", committed)
    # The table's currency columns are the report's fields, under the output rule (item 52).
    for row in fresh.itertuples(index=False):
        for f in fields(RiskReport):
            assert_output_value(getattr(row, f.name), getattr(reports[row.curve], f.name), f"{row.curve} {f.name}")
    # The Markdown is rendered wide, one column per trade, from the frame just written; its layout is checked, not its text.
    md = (tmp_path / "table_3_risk_report.md").read_text(encoding="utf-8").splitlines()
    assert md[0].startswith("| measure |") and md[2].startswith("| mtm |") and len(md) == 2 + len(fields(RiskReport))
    # Table 3's 5Y CS01 is Table 2's cs01_usd row, ours, on every curve (one output against another: item 52's rule).
    table_2 = pd.read_csv(report.TABLES_DIR / "table_2_quantlib_validation.csv")
    cs01_rows = table_2[table_2["metric"] == "cs01_usd"].set_index("curve")
    assert set(cs01_rows.index) == set(NAMED_CURVES)
    table_3 = pd.read_csv(committed).set_index("curve")
    for curve in NAMED_CURVES:
        assert_output_value(table_3.loc[curve, "cs01_5y"], cs01_rows.loc[curve, "ours"], f"table 3 cs01_5y against table 2 on {curve}")


def test_chart_2_is_current_1600_by_900_and_shows_the_rec01_point(results: dict[str, BootstrapResult], discount: DiscountCurve, tmp_path: Path) -> None:
    r = results[report.CHART_2_CURVE]
    fresh = report.chart_2_recovery_dependence(r, discount, out_dir=tmp_path)
    assert tuple(fresh.columns) == report.CHART_2_COLUMNS
    assert list(fresh["recovery"]) == [round(0.10 + 0.01 * k, 2) for k in range(51)]
    committed = report.CHARTS_DIR / "chart_2_recovery_dependence.csv"
    assert_output_current(tmp_path / "chart_2_recovery_dependence.csv", committed)
    png = matplotlib.image.imread(report.CHARTS_DIR / "chart_2_recovery_dependence.png")
    assert png.shape[:2] == CHART_SIZE
    # (a) the implied default probability rises with R: lambda ~ s / (1 - R).
    pd_ = fresh["implied_5y_default_prob"].to_numpy()
    assert (pd_[1:] > pd_[:-1]).all()
    # (b) the par trade re-bootstrapped is flat; the hazard-fixed lines share the slope -I N per point.
    assert fresh["mtm_par_trade"].max() - fresh["mtm_par_trade"].min() < CHART_2_PAR_FLAT_USD
    par, off = report.chart_2_trades(r, discount)
    state = market_state(r, discount)
    base = fresh.set_index("recovery")
    step = base.loc[0.41, "mtm_par_trade_hazard_fixed"] - base.loc[0.40, "mtm_par_trade_hazard_fixed"]
    assert step == pytest.approx(rec01_hazard_fixed(state, par), rel=REC01_HAZARD_FIXED_REL_TOL)
    step_off = base.loc[0.41, "mtm_offmarket_trade_hazard_fixed"] - base.loc[0.40, "mtm_offmarket_trade_hazard_fixed"]
    assert step_off == pytest.approx(step, rel=REC01_HAZARD_FIXED_SAME_REL_TOL)
    assert_output_value(base.loc[0.41, "mtm_offmarket_trade"] - base.loc[0.40, "mtm_offmarket_trade"], rec01(state, off, spreads_bp=r.conventional_spreads_bp), "chart 2 off-market step against rec01")
    # At the file's R the two readings meet.
    assert_output_value(base.loc[0.40, "mtm_par_trade"], base.loc[0.40, "mtm_par_trade_hazard_fixed"], "chart 2 at R = 0.40")
    assert par.coupon_bp == pytest.approx(90.0) and off.coupon_bp == pytest.approx(90.0 + report.CHART_2_OFFMARKET_BP)
    # Item 43: the legend slopes come from the CSV; the hazard-fixed lines are linear, so the fit is the 1-point step.
    slopes = report.chart_2_slopes(pd.read_csv(committed))
    assert set(slopes) == set(report.CHART_2_COLUMNS[2:])
    assert slopes["mtm_par_trade_hazard_fixed"] == pytest.approx(step, rel=REC01_HAZARD_FIXED_REL_TOL)
    assert slopes["mtm_offmarket_trade_hazard_fixed"] == pytest.approx(step, rel=REC01_HAZARD_FIXED_REL_TOL)
    assert abs(slopes["mtm_par_trade"]) < CHART_2_PAR_FLAT_USD
    assert slopes["mtm_offmarket_trade"] > 0.0


def test_make_outputs_knows_table_3_and_chart_2() -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location("make_outputs", ROOT / "scripts" / "make_outputs.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert {"table_3", "chart_2"} <= set(module.OUTPUTS)


def test_output_tables_are_written_by_the_generators_only() -> None:
    """The committed Table 3 CSV is the rounded frame: every float has at
    most OUTPUT_DECIMALS places."""
    table = pd.read_csv(report.TABLES_DIR / "table_3_risk_report.csv", dtype=str)
    for col in report.TABLE_3_COLUMNS[2:]:
        for cell in table[col]:
            assert len(cell.split(".")[-1]) <= report.OUTPUT_DECIMALS if "." in cell else True
