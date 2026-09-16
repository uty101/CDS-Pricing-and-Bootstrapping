"""Section 4: the premium and protection legs (BUILD_PLAN.md Section 4, criteria 1 to 5).

The isda engine (closed form per merged-grid interval) against the grid
engine (daily grid), the credit triangle in the continuous limit, first-order
convergence of the grid, the half-day accrual bias, non-negativity and
monotonicity in the hazards. QuantLib's IsdaCdsEngine is the oracle at the
end, imported in the test only.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest

from cds.conventions import ACT360_BASIS, ACT365F_BASIS, RECOVERY_HY_INDEX, RECOVERY_SENIOR, RECOVERY_SUBORDINATED
from cds.curves import DiscountCurve, RecoveryCurve, SurvivalCurve, discount_curve_from_file, standard_pillar_dates
from cds.legs import (
    TAYLOR_THRESHOLD,
    LegValues,
    _isda_intervals,
    dirty_par_spread_bp,
    leg_values,
    protection_start_date,
)
from cds.schedule import Schedule, cds_schedule, standard_maturity, year_fraction_act360, year_fraction_act365f
from tests.conftest import (
    CREDIT_TRIANGLE_BP,
    CURVE_IDENTITY_ABS_TOL,
    GRID_CONVERGENCE_RATIO,
    HALF_DAY_BIAS_BP,
    PAR_SPREAD_ENGINE_AGREEMENT_BP,
    QL_LEGS_ABS_TOL,
)

RATES_FILE = Path(__file__).resolve().parent.parent / "data" / "rates" / "sofr_ois_2026-09-15.json"
AS_OF = date(2026, 9, 15)  # the Section 2 snapshot date; also the trade date

# Criterion 1: the three test curves, hazards per pillar and recovery.
CURVES = {
    "flat": ((0.01,) * 8, RECOVERY_SENIOR),
    "steep": ((0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08), RECOVERY_HY_INDEX),
    "inverted": ((0.30, 0.25, 0.20, 0.16, 0.13, 0.11, 0.09, 0.08), RECOVERY_SUBORDINATED),
}

# Criterion 2: the credit triangle inputs and the horizon of the daily schedule.
TRIANGLE_HAZARD = 0.0167
TRIANGLE_RECOVERY = RECOVERY_SENIOR
TRIANGLE_YEARS = 5

# Criterion 5: the hazard bump, 10 bp as an intensity.
HAZARD_BUMP = 0.001

# Extra: the series and the closed form must agree either side of the switch.
# At x = 1e-4 the closed form's J bracket cancels to x^2 of its terms, so its
# own precision is about 1e-16 / x^2 = 1e-8; the series is the accurate side.
TAYLOR_CONTINUITY_REL_TOL = 1e-7


@pytest.fixture(scope="module")
def discount() -> DiscountCurve:
    return discount_curve_from_file(RATES_FILE)


@pytest.fixture(scope="module")
def schedule_5y() -> Schedule:
    return cds_schedule(AS_OF, standard_maturity(AS_OF, "5Y"))


@pytest.fixture(scope="module")
def schedule_10y() -> Schedule:
    return cds_schedule(AS_OF, standard_maturity(AS_OF, "10Y"))


def _curve(name: str, hazards: tuple[float, ...] | None = None) -> tuple[SurvivalCurve, RecoveryCurve]:
    base, recovery = CURVES[name]
    survival = SurvivalCurve(as_of=AS_OF, pillar_dates=standard_pillar_dates(AS_OF), pillar_hazards=hazards or base)
    return survival, RecoveryCurve.flat(recovery, AS_OF)


def _legs(discount: DiscountCurve, name: str, schedule: Schedule, **kwargs) -> LegValues:
    survival, recovery = _curve(name)
    return leg_values(discount, survival, recovery, schedule, AS_OF, **kwargs)


# --- criterion 1: the two engines agree -------------------------------------
# Compared on the dirty par spread PV_prot / A, a property of the legs alone;
# the reported par spread is the clean-value one (item 24), which adds the
# settlement factor and the accrued and is the pricer's to test.


@pytest.mark.parametrize("name", list(CURVES))
@pytest.mark.parametrize("half_day_bias", [True, False])
def test_isda_and_grid_dirty_par_spreads_agree(discount: DiscountCurve, schedule_5y: Schedule, name: str, half_day_bias: bool) -> None:
    isda = _legs(discount, name, schedule_5y, half_day_bias=half_day_bias, engine="isda")
    grid = _legs(discount, name, schedule_5y, half_day_bias=half_day_bias, engine="grid", grid_days=1)
    assert abs(dirty_par_spread_bp(isda) - dirty_par_spread_bp(grid)) < PAR_SPREAD_ENGINE_AGREEMENT_BP


# --- criterion 2: the credit triangle ----------------------------------------


def _daily_schedule(year_fraction) -> Schedule:
    """A coupon every calendar day from as_of for TRIANGLE_YEARS, fractions
    from the given day count: the continuous-premium limit."""
    days = [AS_OF + timedelta(days=k) for k in range(ACT365F_BASIS * TRIANGLE_YEARS + 1)]
    return Schedule(
        trade_date=AS_OF,
        maturity=days[-1],
        step_in=AS_OF + timedelta(days=1),
        cash_settle=AS_OF + timedelta(days=3),
        accrual_start=tuple(days[:-1]),
        accrual_end=tuple(days[1:]),
        payment=tuple(days[1:]),
        accrual_fraction=tuple(year_fraction(d0, d1) for d0, d1 in zip(days[:-1], days[1:])),
        accrual_start_date=AS_OF,
        accrued_days=1,
        calendar="weekends",
    )


@pytest.fixture(scope="module")
def zero_rate_curve() -> DiscountCurve:
    return DiscountCurve(as_of=AS_OF, node_dates=(AS_OF + timedelta(days=ACT365F_BASIS * 10),), node_dfs=(1.0,))


@pytest.mark.parametrize("engine", ["isda", "grid"])
def test_credit_triangle_in_the_continuous_limit(zero_rate_curve: DiscountCurve, engine: str) -> None:
    """Zero rates, daily coupons with act/365F fractions (so premium time and
    curve time agree), no accrual on default: s_par = lambda (1 - R)."""
    survival = SurvivalCurve.flat(AS_OF, TRIANGLE_HAZARD)
    recovery = RecoveryCurve.flat(TRIANGLE_RECOVERY, AS_OF)
    legs = leg_values(zero_rate_curve, survival, recovery, _daily_schedule(year_fraction_act365f), AS_OF, half_day_bias=False, engine=engine)
    s_bp = 1e4 * legs.pv_protection / legs.annuity_coupon
    assert abs(s_bp - 1e4 * TRIANGLE_HAZARD * (1.0 - TRIANGLE_RECOVERY)) < CREDIT_TRIANGLE_BP


def test_act360_accrual_against_act365f_time_scales_the_dirty_par_spread(zero_rate_curve: DiscountCurve) -> None:
    """The intended mixing (Part A.1): act/360 coupon fractions on act/365F
    curve time make every coupon 365/360 larger, so the par spread is exactly
    360/365 of the act/365F one."""
    survival = SurvivalCurve.flat(AS_OF, TRIANGLE_HAZARD)
    recovery = RecoveryCurve.flat(TRIANGLE_RECOVERY, AS_OF)
    s = {}
    for label, yf in (("act360", year_fraction_act360), ("act365f", year_fraction_act365f)):
        legs = leg_values(zero_rate_curve, survival, recovery, _daily_schedule(yf), AS_OF, half_day_bias=False)
        s[label] = legs.pv_protection / legs.annuity_coupon
    assert abs(s["act360"] / s["act365f"] - ACT360_BASIS / ACT365F_BASIS) < CURVE_IDENTITY_ABS_TOL


# --- criterion 3: the grid converges at first order --------------------------


@pytest.mark.parametrize("half_day_bias", [True, False])
def test_grid_error_halves_when_the_step_halves(discount: DiscountCurve, schedule_5y: Schedule, half_day_bias: bool) -> None:
    s_isda = dirty_par_spread_bp(_legs(discount, "steep", schedule_5y, half_day_bias=half_day_bias))
    s_1 = dirty_par_spread_bp(_legs(discount, "steep", schedule_5y, half_day_bias=half_day_bias, engine="grid", grid_days=1))
    s_2 = dirty_par_spread_bp(_legs(discount, "steep", schedule_5y, half_day_bias=half_day_bias, engine="grid", grid_days=2))
    ratio = abs(s_2 - s_isda) / abs(s_1 - s_isda)
    lo, hi = GRID_CONVERGENCE_RATIO
    assert lo <= ratio <= hi


# --- criterion 4: the half-day bias ------------------------------------------


def test_half_day_bias_is_small_and_raises_the_annuity(discount: DiscountCurve, schedule_5y: Schedule) -> None:
    on = _legs(discount, "flat", schedule_5y, half_day_bias=True)
    off = _legs(discount, "flat", schedule_5y, half_day_bias=False)
    assert on.annuity_accrual > off.annuity_accrual
    assert on.annuity_coupon == off.annuity_coupon
    assert on.protection == off.protection
    assert abs(dirty_par_spread_bp(on) - dirty_par_spread_bp(off)) < HALF_DAY_BIAS_BP
    assert dirty_par_spread_bp(on) < dirty_par_spread_bp(off)


# --- criterion 5: signs and monotonicity -------------------------------------


@pytest.mark.parametrize("name", list(CURVES))
@pytest.mark.parametrize("engine", ["isda", "grid"])
def test_legs_are_non_negative(discount: DiscountCurve, schedule_5y: Schedule, name: str, engine: str) -> None:
    legs = _legs(discount, name, schedule_5y, engine=engine)
    assert legs.annuity_coupon > 0.0
    assert legs.annuity_accrual > 0.0
    assert legs.protection > 0.0
    assert legs.pv_protection > 0.0
    assert legs.annuity == legs.annuity_coupon + legs.annuity_accrual


@pytest.mark.parametrize("name", list(CURVES))
def test_protection_rises_with_every_pillar_hazard(discount: DiscountCurve, schedule_10y: Schedule, name: str) -> None:
    """A 10Y contract, so every pillar interval is inside the protection period."""
    base_hazards, _ = CURVES[name]
    base = _legs(discount, name, schedule_10y)
    for i in range(len(base_hazards)):
        bumped_hazards = tuple(h + (HAZARD_BUMP if k == i else 0.0) for k, h in enumerate(base_hazards))
        survival, recovery = _curve(name, bumped_hazards)
        bumped = leg_values(discount, survival, recovery, schedule_10y, AS_OF)
        assert bumped.protection > base.protection, f"pillar {i}"
        assert bumped.pv_protection > base.pv_protection, f"pillar {i}"


def test_pillars_beyond_maturity_do_not_move_a_5y_contract(discount: DiscountCurve, schedule_5y: Schedule) -> None:
    base_hazards, _ = CURVES["steep"]
    base = _legs(discount, "steep", schedule_5y)
    for i in (6, 7):  # the 7Y and 10Y pillars
        bumped_hazards = tuple(h + (HAZARD_BUMP if k == i else 0.0) for k, h in enumerate(base_hazards))
        survival, recovery = _curve("steep", bumped_hazards)
        bumped = leg_values(discount, survival, recovery, schedule_5y, AS_OF)
        assert bumped == base


# --- construction and identities ---------------------------------------------


def test_pv_protection_is_one_minus_r_times_protection(discount: DiscountCurve, schedule_5y: Schedule) -> None:
    for name, (_, recovery) in CURVES.items():
        legs = _legs(discount, name, schedule_5y)
        assert abs(legs.pv_protection - (1.0 - recovery) * legs.protection) < CURVE_IDENTITY_ABS_TOL


def test_protection_start_is_the_valuation_date_for_new_and_seasoned_trades() -> None:
    assert protection_start_date(AS_OF, AS_OF + timedelta(days=1)) == AS_OF
    assert protection_start_date(AS_OF, AS_OF - timedelta(days=100)) == AS_OF
    # a forward-starting protection begins the day before its step-in
    assert protection_start_date(AS_OF, AS_OF + timedelta(days=10)) == AS_OF + timedelta(days=9)


def test_series_and_closed_form_agree_at_the_switch() -> None:
    """Either side of |x| = TAYLOR_THRESHOLD the two branches give the same
    interval integrals to the closed form's own precision there."""
    tau, hazard = 1e-3, 0.05
    pa, qa = 0.9, 0.95
    out = {}
    for label, forward in (("series", TAYLOR_THRESHOLD / tau - hazard - 1e-9), ("exact", TAYLOR_THRESHOLD / tau - hazard + 1e-9)):
        pb, qb = pa * np.exp(-forward * tau), qa * np.exp(-hazard * tau)
        i_k, j_k = _isda_intervals(np.array([0.0]), np.array([tau]), np.array([pa]), np.array([pb]), np.array([qa]), np.array([qb]))
        out[label] = (float(i_k[0]), float(j_k[0]))
    for k in range(2):
        assert abs(out["series"][k] / out["exact"][k] - 1.0) < TAYLOR_CONTINUITY_REL_TOL


def test_zero_hazard_and_zero_rate_give_zero_protection_without_nan(zero_rate_curve: DiscountCurve, schedule_5y: Schedule) -> None:
    survival = SurvivalCurve.flat(AS_OF, 0.0)
    recovery = RecoveryCurve.flat(RECOVERY_SENIOR, AS_OF)
    for engine in ("isda", "grid"):
        legs = leg_values(zero_rate_curve, survival, recovery, schedule_5y, AS_OF, engine=engine)
        assert legs.protection == 0.0 and legs.annuity_accrual == 0.0
        assert abs(legs.annuity_coupon - sum(schedule_5y.accrual_fraction)) < CURVE_IDENTITY_ABS_TOL


def test_rejects_bad_inputs(discount: DiscountCurve, schedule_5y: Schedule) -> None:
    survival, recovery = _curve("flat")
    with pytest.raises(ValueError):
        leg_values(discount, survival, recovery, schedule_5y, AS_OF, engine="midpoint")
    with pytest.raises(ValueError):
        leg_values(discount, survival, recovery, schedule_5y, AS_OF, engine="grid", grid_days=0)
    with pytest.raises(ValueError):
        leg_values(discount, survival, recovery, schedule_5y, AS_OF + timedelta(days=1))
    with pytest.raises(ValueError):
        leg_values(discount, survival.with_as_of(AS_OF + timedelta(days=1), "tenor"), recovery, schedule_5y, AS_OF)
    late = AS_OF + timedelta(days=ACT365F_BASIS * 6)
    shifted = (discount.with_as_of(late, "calendar"), survival.with_as_of(late, "calendar"), recovery.with_as_of(late, "calendar"))
    with pytest.raises(ValueError):
        leg_values(*shifted, schedule_5y, late)


# --- oracle: QuantLib's IsdaCdsEngine ----------------------------------------

# Weekend maturities (review 04, Not verified 4): the 6M and 1Y pillars of
# this snapshot both fall on a Sunday, so the last accrual integral ends at
# pay - 1 = maturity, and the final coupon pays on the Monday after.
WEEKEND_MATURITIES = (date(2026, 12, 20), date(2027, 6, 20))


def _quantlib_legs(discount: DiscountCurve, name: str, maturity: date, half_day_bias: bool) -> tuple[float, float]:
    """QuantLib's (A, PV_prot) for the same trade: couponLegNPV / spread is
    the dirty annuity with accrual on default; defaultLegNPV is (1 - R) times
    the default integral. Flags: Taylor, HalfDayBias or NoBias, Piecewise, as
    Section 7 will use."""
    import QuantLib as ql

    def to_ql(d: date) -> ql.Date:
        return ql.Date(d.day, d.month, d.year)

    hazards, recovery_rate = CURVES[name]
    survival, _ = _curve(name)
    schedule = cds_schedule(AS_OF, maturity)

    ql.Settings.instance().evaluationDate = to_ql(AS_OF)
    ql_discount = ql.DiscountCurve([to_ql(AS_OF), *map(to_ql, discount.node_dates)], [1.0, *discount.node_dfs], ql.Actual365Fixed())
    ql_discount.enableExtrapolation()
    ql_hazard = ql.HazardRateCurve([to_ql(AS_OF), *map(to_ql, survival.pillar_dates)], [hazards[0], *hazards], ql.Actual365Fixed())
    ql_hazard.enableExtrapolation()
    spread = 0.01
    ql_schedule = ql.Schedule(
        to_ql(schedule.step_in), to_ql(maturity), ql.Period("3M"), ql.WeekendsOnly(), ql.Following, ql.Unadjusted, ql.DateGeneration.CDS2015, False
    )
    cds = ql.CreditDefaultSwap(
        ql.Protection.Buyer, 1.0, spread, ql_schedule, ql.Following, ql.Actual360(), True, True,
        to_ql(schedule.step_in), ql.FaceValueClaim(), ql.Actual360(True), True, to_ql(AS_OF),
    )
    bias = ql.IsdaCdsEngine.HalfDayBias if half_day_bias else ql.IsdaCdsEngine.NoBias
    cds.setPricingEngine(
        ql.IsdaCdsEngine(
            ql.DefaultProbabilityTermStructureHandle(ql_hazard), recovery_rate, ql.YieldTermStructureHandle(ql_discount),
            False, ql.IsdaCdsEngine.Taylor, bias, ql.IsdaCdsEngine.Piecewise,
        )
    )
    return -cds.couponLegNPV() / spread, cds.defaultLegNPV()  # the buyer pays the coupon leg


def _assert_legs_match_quantlib(discount: DiscountCurve, name: str, maturity: date, half_day_bias: bool) -> None:
    survival, recovery = _curve(name)
    ours = leg_values(discount, survival, recovery, cds_schedule(AS_OF, maturity), AS_OF, half_day_bias=half_day_bias)
    annuity_ql, protection_ql = _quantlib_legs(discount, name, maturity, half_day_bias)
    assert abs(ours.annuity - annuity_ql) < QL_LEGS_ABS_TOL
    assert abs(ours.pv_protection - protection_ql) < QL_LEGS_ABS_TOL


@pytest.mark.parametrize("tenor", ["5Y", "10Y"])
@pytest.mark.parametrize("name", list(CURVES))
@pytest.mark.parametrize("half_day_bias", [True, False])
def test_legs_match_quantlib_isda_engine(discount: DiscountCurve, tenor: str, name: str, half_day_bias: bool) -> None:
    _assert_legs_match_quantlib(discount, name, standard_maturity(AS_OF, tenor), half_day_bias)


@pytest.mark.parametrize("maturity", WEEKEND_MATURITIES, ids=lambda d: d.isoformat())
@pytest.mark.parametrize("name", ["flat", "inverted"])
@pytest.mark.parametrize("half_day_bias", [True, False])
def test_legs_match_quantlib_on_weekend_maturities(discount: DiscountCurve, maturity: date, name: str, half_day_bias: bool) -> None:
    """The unadjusted maturity is a Sunday: the last coupon pays on the
    Monday and its accrual integral ends on the Sunday, one day past the
    protection end."""
    assert maturity.weekday() == 6  # Sunday
    _assert_legs_match_quantlib(discount, name, maturity, half_day_bias)
