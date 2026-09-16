"""Section 5: price(), par spread, upfront and the flat-hazard conversions
(BUILD_PLAN.md Section 5, criteria 1 to 7).

The curves are the Section 4 test curves on the Section 2 discount curve.
The par spread is the clean-value spread PV_prot / (A - accrued_fraction / D)
(docs/CONVENTIONS_RESOLVED.md item 24), at which the clean upfront is zero;
the dirty par spread PV_prot / A is checked alongside it as the coupon at
which the dirty value is zero. QuantLib is the oracle for the accrued rebate
and for fairSpread, imported in the test only.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta

import pytest

from cds.calendars import is_business_day
from cds.conventions import ACT360_BASIS, ACT365F_BASIS, DEFAULT_NOTIONAL, RECOVERY_SENIOR
from cds.curves import DiscountCurve, RecoveryCurve, SurvivalCurve, discount_curve_from_file, standard_pillar_dates
from cds.legs import leg_values
from cds.pricer import (
    accrued_days,
    cash_settle_date,
    implied_flat_hazard,
    price,
    quoted_spread_to_upfront,
    upfront_to_quoted_spread,
    value,
)
from cds.schedule import cds_schedule, standard_maturity
from cds.types import CDSTrade, MarketCurveQuotes, MarketState, Quote
from tests.conftest import (
    CLEAN_SPREAD_TENOR_RANGE_BP,
    CONVERSION_ROUNDTRIP_BP,
    FLAT_HAZARD_SOLVE_ABS_TOL,
    PAR_SPREAD_ENGINE_AGREEMENT_BP,
    PAR_SPREAD_REPRICE_BP,
    PAR_UPFRONT_BP,
    PAR_UPFRONT_USD,
    PRICER_IDENTITY_ABS_TOL,
    QL_ACCRUED_ABS_USD,
    QL_PRICER_ABS_TOL,
)
from tests.test_legs import AS_OF, CURVES, RATES_FILE
from tests.test_schedule import TRADE_DATES

BP_PER_UNIT = 1e4
PERCENT = 100.0

# Criterion 1: the flat-hazard curve built in the test.
FLAT_HAZARD = 0.01

# Criterion 3: the round-trip spreads and coupons.
ROUNDTRIP_SPREADS_BP = (45.0, 250.0, 1200.0)
ROUNDTRIP_COUPONS_BP = (100.0, 500.0)

# Criterion 4: the hazard multiplier.
HAZARD_UP = 1.10

# The 6M contract from 15 Sep 2026 pays two full coupons (182 days) for 96
# days of protection, so its dirty par spread is near half the clean-value
# par spread.
DIRTY_6M_FRACTION = 0.6

# Five of the 16 trade dates fall on a weekend; price() refuses them (item
# 10) and only the schedule-level accrued is compared with QuantLib there.
WEEKEND_TRADE_DATES = tuple(d for d in TRADE_DATES if not is_business_day(d))


@pytest.fixture(scope="module")
def discount() -> DiscountCurve:
    return discount_curve_from_file(RATES_FILE)


def _quotes(recovery: float) -> MarketCurveQuotes:
    """A placeholder MarketCurveQuotes: price() does not read it (Section 6 builds the real ones)."""
    return MarketCurveQuotes(as_of=AS_OF, pillars=("5Y",), quotes=(Quote(kind="par_spread_bp", value=100.0),), recovery=recovery, label="test")


def _state(discount: DiscountCurve, hazards: tuple[float, ...], recovery: float, as_of: date = AS_OF) -> MarketState:
    survival = SurvivalCurve(as_of=as_of, pillar_dates=standard_pillar_dates(as_of), pillar_hazards=hazards)
    return MarketState(as_of=as_of, discount=discount, survival=survival, recovery=RecoveryCurve.flat(recovery, as_of), quotes=_quotes(recovery))


def _flat_state(discount: DiscountCurve) -> MarketState:
    return _state(discount, (FLAT_HAZARD,) * 8, RECOVERY_SENIOR)


def _named_state(discount: DiscountCurve, name: str, scale: float = 1.0) -> MarketState:
    hazards, recovery = CURVES[name]
    return _state(discount, tuple(h * scale for h in hazards), recovery)


def _trade(tenor: str = "5Y", coupon_bp: float = 100.0, side: str = "buy", recovery: float = RECOVERY_SENIOR, quote: Quote | None = None, trade_date: date = AS_OF) -> CDSTrade:
    return CDSTrade(trade_date=trade_date, maturity=standard_maturity(trade_date, tenor), coupon_bp=coupon_bp, side=side, recovery=recovery, quote=quote)


# --- criteria 1 and 2: the par coupon ----------------------------------------


def test_par_coupon_gives_zero_clean_upfront_and_reprices_the_par_spread(discount: DiscountCurve) -> None:
    """Criteria 1 and 2: at c = s_par (the clean-value spread, item 24) the
    clean upfront is within 0.01 bp of zero, U_dirty + accrued is under $1 on
    $10m (mtm is dirty, so the check is on the clean amount), and the par
    spread reprices to 1e-9 bp."""
    state = _flat_state(discount)
    s_par = price(state, _trade()).par_spread_bp
    at_par = price(state, _trade(coupon_bp=s_par))
    assert abs(at_par.clean_upfront_pct) < PAR_UPFRONT_BP / BP_PER_UNIT * PERCENT
    assert abs(at_par.mtm + at_par.accrued) < PAR_UPFRONT_USD
    assert abs(at_par.par_spread_bp - s_par) < PAR_SPREAD_REPRICE_BP


def test_dirty_par_coupon_gives_zero_dirty_upfront(discount: DiscountCurve) -> None:
    """The companion identity: at c = PV_prot / A the dirty value is zero, so
    mtm is under $1, the clean upfront equals the accrued and the two legs
    are equal; the reported par spread is unchanged."""
    state = _flat_state(discount)
    s_dirty = value(discount, state.survival, state.recovery, _trade(), AS_OF).dirty_par_spread_bp
    at_dirty_par = price(state, _trade(coupon_bp=s_dirty))
    assert abs(at_dirty_par.mtm) < PAR_UPFRONT_USD
    assert abs(at_dirty_par.clean_upfront_pct - PERCENT * at_dirty_par.accrued / DEFAULT_NOTIONAL) < PRICER_IDENTITY_ABS_TOL
    assert abs(at_dirty_par.pv_protection - at_dirty_par.pv_premium) < PRICER_IDENTITY_ABS_TOL
    assert abs(at_dirty_par.par_spread_bp - price(state, _trade()).par_spread_bp) < PAR_SPREAD_REPRICE_BP
    assert s_dirty < at_dirty_par.par_spread_bp  # the dirty annuity carries 86 rebated days


def test_par_spread_is_the_same_on_every_tenor_for_a_flat_hazard(discount: DiscountCurve) -> None:
    """A flat hazard has one credit-triangle spread; the clean-value par
    spread sees it on every tenor, the dirty par spread does not (the 6M pays
    two full coupons for 96 days of protection)."""
    state = _flat_state(discount)
    clean = [price(state, _trade(tenor)).par_spread_bp for tenor in ("6M", "1Y", "5Y", "10Y")]
    dirty = [value(discount, state.survival, state.recovery, _trade(tenor), AS_OF).dirty_par_spread_bp for tenor in ("6M", "1Y", "5Y", "10Y")]
    assert max(clean) - min(clean) < CLEAN_SPREAD_TENOR_RANGE_BP
    assert dirty[0] < clean[0] * DIRTY_6M_FRACTION
    assert dirty == sorted(dirty)


# --- criterion 3: the flat-hazard round trip ---------------------------------


@pytest.mark.parametrize("coupon_bp", ROUNDTRIP_COUPONS_BP)
@pytest.mark.parametrize("spread_bp", ROUNDTRIP_SPREADS_BP)
def test_spread_to_upfront_and_back(discount: DiscountCurve, spread_bp: float, coupon_bp: float) -> None:
    trade = _trade(coupon_bp=coupon_bp)
    upfront = quoted_spread_to_upfront(discount, trade, spread_bp)
    assert abs(upfront_to_quoted_spread(discount, trade, upfront) - spread_bp) < CONVERSION_ROUNDTRIP_BP


def test_upfront_is_monotone_in_the_quoted_spread_and_zero_hazard_at_zero_spread(discount: DiscountCurve) -> None:
    trade = _trade(coupon_bp=100.0)
    upfronts = [quoted_spread_to_upfront(discount, trade, s) for s in (0.0, 45.0, 100.0, 250.0, 1200.0)]
    assert upfronts == sorted(upfronts)
    assert implied_flat_hazard(discount, trade, 0.0) == 0.0
    with pytest.raises(ValueError):
        upfront_to_quoted_spread(discount, trade, 99.0)


def test_conversion_at_the_flat_curve_par_spread_reproduces_the_curve_upfront(discount: DiscountCurve) -> None:
    """On a flat survival curve the flat-hazard conversion is exact: the
    implied hazard is the curve's, and the upfront is price()'s."""
    state = _flat_state(discount)
    trade = _trade(coupon_bp=100.0)
    result = price(state, trade)
    assert abs(implied_flat_hazard(discount, trade, result.par_spread_bp) - FLAT_HAZARD) < FLAT_HAZARD_SOLVE_ABS_TOL
    assert abs(quoted_spread_to_upfront(discount, trade, result.par_spread_bp) - result.clean_upfront_pct) < PAR_UPFRONT_BP / BP_PER_UNIT * PERCENT


# --- criterion 4: signs -------------------------------------------------------


@pytest.mark.parametrize("name", list(CURVES))
def test_wider_spreads_raise_the_buyer_and_lower_the_seller(discount: DiscountCurve, name: str) -> None:
    _, recovery = CURVES[name]
    base, up = _named_state(discount, name), _named_state(discount, name, HAZARD_UP)
    buy, sell = _trade(recovery=recovery, side="buy"), _trade(recovery=recovery, side="sell")
    assert price(up, buy).mtm > price(base, buy).mtm
    assert price(up, sell).mtm < price(base, sell).mtm
    assert abs(price(base, buy).mtm + price(base, sell).mtm) < PRICER_IDENTITY_ABS_TOL * DEFAULT_NOTIONAL
    assert price(base, buy).clean_upfront_pct == price(base, sell).clean_upfront_pct


# --- criterion 5: accrued against QuantLib -----------------------------------


def _quantlib_rebate(trade: date, maturity: date, notional: float, coupon_bp: float) -> float:
    import QuantLib as ql

    def to_ql(d: date) -> ql.Date:
        return ql.Date(d.day, d.month, d.year)

    step_in = trade + timedelta(days=1)
    ql.Settings.instance().evaluationDate = to_ql(trade)
    schedule = ql.Schedule(to_ql(step_in), to_ql(maturity), ql.Period("3M"), ql.WeekendsOnly(), ql.Following, ql.Unadjusted, ql.DateGeneration.CDS2015, False)
    cds = ql.CreditDefaultSwap(
        ql.Protection.Buyer, notional, coupon_bp / BP_PER_UNIT, schedule, ql.Following, ql.Actual360(), True, True,
        to_ql(step_in), ql.FaceValueClaim(), ql.Actual360(True), True, to_ql(trade),
    )
    return cds.accrualRebate().amount()


@pytest.mark.parametrize("trade_date", TRADE_DATES, ids=str)
def test_accrued_matches_quantlib_accrual_rebate(discount: DiscountCurve, trade_date: date) -> None:
    coupon_bp = 100.0
    maturity = standard_maturity(trade_date, "5Y")
    schedule = cds_schedule(trade_date, maturity)
    rebate = _quantlib_rebate(trade_date, maturity, DEFAULT_NOTIONAL, coupon_bp)
    assert abs(coupon_bp / BP_PER_UNIT * DEFAULT_NOTIONAL * accrued_days(schedule, trade_date) / ACT360_BASIS - rebate) < QL_ACCRUED_ABS_USD
    trade = _trade(coupon_bp=coupon_bp, trade_date=trade_date)
    if trade_date in WEEKEND_TRADE_DATES:
        with pytest.raises(ValueError):
            price(_state(discount.with_as_of(trade_date, "tenor"), (FLAT_HAZARD,) * 8, RECOVERY_SENIOR, trade_date), trade)
        return
    result = price(_state(discount.with_as_of(trade_date, "tenor"), (FLAT_HAZARD,) * 8, RECOVERY_SENIOR, trade_date), trade)
    assert abs(result.accrued - rebate) < QL_ACCRUED_ABS_USD
    assert abs(result.accrued - coupon_bp / BP_PER_UNIT * DEFAULT_NOTIONAL * schedule.accrued_days / ACT360_BASIS) < QL_ACCRUED_ABS_USD
    assert result.cash_settle_date == schedule.cash_settle


def test_five_of_the_sixteen_trade_dates_are_weekends() -> None:
    assert WEEKEND_TRADE_DATES == (date(2016, 3, 19), date(2016, 3, 20), date(2020, 2, 29), date(2020, 12, 20), date(2025, 9, 20))


# --- criterion 6: settlement discounting -------------------------------------


def test_settlement_amounts_are_valuation_amounts_over_p_settle(discount: DiscountCurve) -> None:
    state = _flat_state(discount)
    trade = _trade(coupon_bp=100.0)
    legs = leg_values(discount, state.survival, state.recovery, cds_schedule(AS_OF, trade.maturity), AS_OF)
    settle = cash_settle_date(AS_OF)
    p_settle = discount.df_on(settle)
    result = price(state, trade)
    assert result.cash_settle_date == settle == AS_OF + timedelta(days=3)
    assert abs(result.mtm / DEFAULT_NOTIONAL - (legs.pv_protection - 0.01 * legs.annuity) / p_settle) < PRICER_IDENTITY_ABS_TOL
    assert abs(result.risky_annuity - legs.annuity / p_settle) < PRICER_IDENTITY_ABS_TOL
    assert abs(result.pv_protection - legs.pv_protection / p_settle) < PRICER_IDENTITY_ABS_TOL
    assert abs(result.pv_premium - 0.01 * legs.annuity / p_settle) < PRICER_IDENTITY_ABS_TOL
    assert p_settle < 1.0


def test_d_fixed_by_construction(discount: DiscountCurve) -> None:
    """A curve with a known P at the settlement date: one node three days
    out at P = 0.5, so D = 2 exactly, then flat forward extrapolation."""
    settle = cash_settle_date(AS_OF)
    d_settle = 2.0
    curve = DiscountCurve(as_of=AS_OF, node_dates=(settle,), node_dfs=(1.0 / d_settle,))
    state = _state(curve, (FLAT_HAZARD,) * 8, RECOVERY_SENIOR)
    trade = _trade(coupon_bp=100.0)
    legs = leg_values(curve, state.survival, state.recovery, cds_schedule(AS_OF, trade.maturity), AS_OF)
    result = price(state, trade)
    assert abs(result.risky_annuity - d_settle * legs.annuity) < PRICER_IDENTITY_ABS_TOL
    assert abs(result.pv_protection - d_settle * legs.pv_protection) < PRICER_IDENTITY_ABS_TOL
    assert abs(result.mtm / DEFAULT_NOTIONAL - d_settle * (legs.pv_protection - 0.01 * legs.annuity)) < PRICER_IDENTITY_ABS_TOL


# --- criterion 7: as_of agreement ---------------------------------------------


def test_price_raises_when_as_of_disagree(discount: DiscountCurve) -> None:
    state = _flat_state(discount)
    later = AS_OF + timedelta(days=1)
    with pytest.raises(ValueError):
        price(replace(state, as_of=later), _trade())
    with pytest.raises(ValueError):
        price(replace(state, survival=state.survival.with_as_of(later, "tenor")), _trade())
    with pytest.raises(ValueError):
        price(replace(state, recovery=RecoveryCurve.flat(RECOVERY_SENIOR, later)), _trade())
    with pytest.raises(ValueError):
        price(replace(state, discount=discount.with_as_of(later, "tenor")), _trade())


# --- quotes, sides and seasoned trades ---------------------------------------


def test_upfront_quote_at_the_trades_own_clean_upfront_has_zero_mtm_at_inception(discount: DiscountCurve) -> None:
    """The quote is clean; the buyer paid it less the accrued rebate, and
    holds a position worth the dirty value: net zero on the trade date."""
    state = _flat_state(discount)
    unquoted = price(state, _trade(coupon_bp=100.0))
    quoted = _trade(coupon_bp=100.0, quote=Quote(kind="upfront_pct", value=unquoted.clean_upfront_pct, coupon_bp=100.0))
    result = price(state, quoted)
    assert abs(result.mtm) < PRICER_IDENTITY_ABS_TOL * DEFAULT_NOTIONAL
    assert result.clean_upfront_pct == unquoted.clean_upfront_pct
    assert abs(unquoted.mtm - (unquoted.clean_upfront_pct / PERCENT * DEFAULT_NOTIONAL - unquoted.accrued)) < PRICER_IDENTITY_ABS_TOL * DEFAULT_NOTIONAL


def test_running_spread_quote_is_the_dirty_value_at_the_traded_spread(discount: DiscountCurve) -> None:
    state = _named_state(discount, "steep")
    _, recovery = CURVES["steep"]
    traded_bp = 250.0
    trade = _trade(coupon_bp=traded_bp, recovery=recovery, quote=Quote(kind="par_spread_bp", value=traded_bp))
    result = price(state, trade)
    v = value(discount, state.survival, state.recovery, trade, AS_OF)
    assert abs(result.mtm - DEFAULT_NOTIONAL * v.d_settle * (v.legs.pv_protection - traded_bp / BP_PER_UNIT * v.legs.annuity)) < PRICER_IDENTITY_ABS_TOL * DEFAULT_NOTIONAL
    assert result.mtm > 0.0  # the steep curve's 5Y par spread is above 250 bp


def test_inconsistent_quotes_and_trades_raise(discount: DiscountCurve) -> None:
    state = _flat_state(discount)
    with pytest.raises(ValueError):
        price(state, _trade(coupon_bp=100.0, quote=Quote(kind="par_spread_bp", value=250.0)))
    with pytest.raises(ValueError):
        price(state, _trade(coupon_bp=100.0, quote=Quote(kind="upfront_pct", value=2.0)))
    with pytest.raises(ValueError):
        price(state, _trade(coupon_bp=100.0, quote=Quote(kind="upfront_pct", value=2.0, coupon_bp=500.0)))
    with pytest.raises(ValueError):
        price(state, _trade(recovery=0.25))
    with pytest.raises(ValueError):
        price(state, _trade(trade_date=date(2026, 9, 12)))  # a Saturday
    with pytest.raises(ValueError):
        price(state, _trade(trade_date=AS_OF + timedelta(days=1)))  # valued before the trade date
    with pytest.raises(ValueError):
        price(state, replace(_trade(), notional=0.0))


def test_sell_negates_mtm_only(discount: DiscountCurve) -> None:
    state = _named_state(discount, "inverted")
    _, recovery = CURVES["inverted"]
    buy, sell = price(state, _trade(coupon_bp=500.0, recovery=recovery)), price(state, _trade(coupon_bp=500.0, recovery=recovery, side="sell"))
    assert buy.mtm == -sell.mtm
    for field in ("clean_upfront_pct", "accrued", "par_spread_bp", "risky_annuity", "pv_protection", "pv_premium", "cash_settle_date"):
        assert getattr(buy, field) == getattr(sell, field)


def test_seasoned_trade_accrued_and_settlement_move_with_the_valuation_date(discount: DiscountCurve) -> None:
    trade = _trade(coupon_bp=100.0)
    schedule = cds_schedule(AS_OF, trade.maturity)
    assert accrued_days(schedule, AS_OF) == schedule.accrued_days == 86
    assert accrued_days(schedule, date(2026, 9, 20)) == 0  # step-in 21 Sep, the next period's first day
    assert accrued_days(schedule, date(2026, 9, 19)) == 90  # step-in 20 Sep, a Sunday: still the first period
    assert accrued_days(schedule, date(2026, 12, 19)) == 90  # 21 Sep to 20 Dec
    assert accrued_days(schedule, trade.maturity - timedelta(days=1)) == (trade.maturity - schedule.accrual_start[-1]).days
    later = date(2026, 10, 15)
    state = _state(discount.with_as_of(later, "calendar"), (FLAT_HAZARD,) * 8, RECOVERY_SENIOR, later)
    result = price(state, trade)
    assert result.cash_settle_date == cash_settle_date(later) == date(2026, 10, 20)
    assert abs(result.accrued - 0.01 * DEFAULT_NOTIONAL * 25 / ACT360_BASIS) < PRICER_IDENTITY_ABS_TOL * DEFAULT_NOTIONAL
    with pytest.raises(ValueError):
        accrued_days(schedule, trade.maturity)


def test_grid_engine_through_price_agrees_with_isda(discount: DiscountCurve) -> None:
    state = _named_state(discount, "steep")
    _, recovery = CURVES["steep"]
    trade = _trade(coupon_bp=500.0, recovery=recovery)
    assert abs(price(state, trade).par_spread_bp - price(state, trade, engine="grid").par_spread_bp) < PAR_SPREAD_ENGINE_AGREEMENT_BP


def test_curve_time_is_act365f_from_as_of(discount: DiscountCurve) -> None:
    """The settlement factor is P at (settle - as_of) / 365 years."""
    state = _flat_state(discount)
    v = value(discount, state.survival, state.recovery, _trade(), AS_OF)
    assert abs(v.d_settle - 1.0 / discount.df((v.settle - AS_OF).days / ACT365F_BASIS)) < PRICER_IDENTITY_ABS_TOL


# --- oracle: QuantLib's fairUpfront and fairSpread ----------------------------


@pytest.mark.parametrize("tenor", ["6M", "1Y", "5Y", "10Y"])
@pytest.mark.parametrize("name", list(CURVES))
def test_clean_upfront_and_par_spread_match_quantlib(discount: DiscountCurve, name: str, tenor: str) -> None:
    """fairUpfront is the clean upfront at the cash settlement date (T+3,
    WeekendsOnly), fairSpread the clean-value spread, which is our par spread
    (item 24); both are QuantLib's IsdaCdsEngine on the same curves, flags as
    in test_legs."""
    import QuantLib as ql

    def to_ql(d: date) -> ql.Date:
        return ql.Date(d.day, d.month, d.year)

    hazards, recovery = CURVES[name]
    state = _named_state(discount, name)
    trade = _trade(tenor, coupon_bp=100.0, recovery=recovery)
    schedule = cds_schedule(AS_OF, trade.maturity)
    ours = price(state, trade)

    ql.Settings.instance().evaluationDate = to_ql(AS_OF)
    ql_discount = ql.DiscountCurve([to_ql(AS_OF), *map(to_ql, discount.node_dates)], [1.0, *discount.node_dfs], ql.Actual365Fixed())
    ql_discount.enableExtrapolation()
    ql_hazard = ql.HazardRateCurve([to_ql(AS_OF), *map(to_ql, state.survival.pillar_dates)], [hazards[0], *hazards], ql.Actual365Fixed())
    ql_hazard.enableExtrapolation()
    ql_schedule = ql.Schedule(
        to_ql(schedule.step_in), to_ql(trade.maturity), ql.Period("3M"), ql.WeekendsOnly(), ql.Following, ql.Unadjusted, ql.DateGeneration.CDS2015, False
    )
    cds = ql.CreditDefaultSwap(
        ql.Protection.Buyer, 1.0, trade.coupon_bp / BP_PER_UNIT, ql_schedule, ql.Following, ql.Actual360(), True, True,
        to_ql(schedule.step_in), ql.FaceValueClaim(), ql.Actual360(True), True, to_ql(AS_OF),
    )
    cds.setPricingEngine(
        ql.IsdaCdsEngine(
            ql.DefaultProbabilityTermStructureHandle(ql_hazard), recovery, ql.YieldTermStructureHandle(ql_discount),
            False, ql.IsdaCdsEngine.Taylor, ql.IsdaCdsEngine.HalfDayBias, ql.IsdaCdsEngine.Piecewise,
        )
    )
    assert abs(ours.clean_upfront_pct - PERCENT * cds.fairUpfront()) < QL_PRICER_ABS_TOL
    assert abs(ours.par_spread_bp - BP_PER_UNIT * cds.fairSpread()) < QL_PRICER_ABS_TOL
    assert abs(ours.accrued - DEFAULT_NOTIONAL * cds.accrualRebate().amount()) < QL_ACCRUED_ABS_USD
    annuity_ql = -cds.couponLegNPV() / (trade.coupon_bp / BP_PER_UNIT)  # at the valuation date; ours is at settlement
    assert abs(ours.risky_annuity - annuity_ql / discount.df_on(ours.cash_settle_date)) < QL_PRICER_ABS_TOL
