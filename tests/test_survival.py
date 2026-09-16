"""Section 3: the survival and recovery curves (BUILD_PLAN.md Section 3, criteria 1 to 6).

Q(t) = exp(-sum_i lambda_i (t_i - t_{i-1})) with lambda_i flat on
(t_{i-1}, t_i], flat extrapolation beyond the last pillar, density
lambda(t) Q(t), and the two with_as_of modes on the survival and discount
curves. QuantLib's backward-flat HazardRateCurve is the oracle at the end,
imported in the test only.
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest
from scipy.integrate import quad

from cds.conventions import ACT365F_BASIS, PILLARS, RECOVERY_HY_INDEX, RECOVERY_SENIOR
from cds.curves import (
    DiscountCurve,
    RecoveryCurve,
    SurvivalCurve,
    discount_curve_from_file,
    standard_pillar_dates,
)
from cds.schedule import standard_maturity
from tests.conftest import CURVE_IDENTITY_ABS_TOL, DENSITY_INTEGRAL_ABS_TOL, QL_SURVIVAL_ABS_TOL

RATES_FILE = Path(__file__).resolve().parent.parent / "data" / "rates" / "sofr_ois_2026-09-15.json"
AS_OF = date(2026, 9, 15)  # the Section 2 snapshot date

# Criterion 1: 50 points from 0 to 15Y, past the 10Y pillar.
FLAT_POINTS = 50
FLAT_HORIZON_YEARS = 15.0
FLAT_HAZARD = 0.0167  # about 100 bp / (1 - 0.40)

# Criterion 2: the three-pillar curve, pillars at exactly 1, 3 and 5 act/365F years.
THREE_PILLAR_YEARS = (1, 3, 5)
THREE_PILLAR_HAZARDS = (0.01, 0.02, 0.03)

# Criterion 3: horizons for the density integral; 12 is past the last pillar.
DENSITY_HORIZONS = (2.5, 5.0, 12.0)

# Criterion 4: the shift, in calendar days.
SHIFT_DAYS = 30

# Criterion 5: a step just past a pillar.
EPS = 1e-9

# A steep curve, 1% to 8%, on the standard pillars; the shape Section 4 uses.
STEEP_HAZARDS = (0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08)


def _exact_days(years: int) -> date:
    return AS_OF + timedelta(days=ACT365F_BASIS * years)


@pytest.fixture(scope="module")
def flat() -> SurvivalCurve:
    return SurvivalCurve.flat(AS_OF, FLAT_HAZARD)


@pytest.fixture(scope="module")
def three() -> SurvivalCurve:
    return SurvivalCurve(
        as_of=AS_OF,
        pillar_dates=tuple(_exact_days(y) for y in THREE_PILLAR_YEARS),
        pillar_hazards=THREE_PILLAR_HAZARDS,
    )


@pytest.fixture(scope="module")
def steep() -> SurvivalCurve:
    return SurvivalCurve(as_of=AS_OF, pillar_dates=standard_pillar_dates(AS_OF), pillar_hazards=STEEP_HAZARDS)


@pytest.fixture(scope="module")
def discount() -> DiscountCurve:
    return discount_curve_from_file(RATES_FILE)


# --- construction -----------------------------------------------------------


def test_standard_pillar_dates_are_the_standard_maturities() -> None:
    dates = standard_pillar_dates(AS_OF)
    assert len(dates) == len(PILLARS)
    assert dates == tuple(standard_maturity(AS_OF, p) for p in PILLARS)
    assert dates[0] == date(2026, 12, 20) and dates[-1] == date(2036, 6, 20)


def test_pillar_times_are_act365f_from_as_of(steep: SurvivalCurve) -> None:
    for d, t in zip(steep.pillar_dates, steep.pillar_times):
        assert t == (d - AS_OF).days / ACT365F_BASIS


def test_three_pillar_times_are_whole_years(three: SurvivalCurve) -> None:
    assert three.pillar_times == tuple(float(y) for y in THREE_PILLAR_YEARS)


# --- criterion 1: flat hazard ----------------------------------------------


def test_flat_hazard_gives_exponential_survival(flat: SurvivalCurve) -> None:
    ts = np.linspace(0.0, FLAT_HORIZON_YEARS, FLAT_POINTS)
    assert ts[-1] > flat.pillar_times[-1]
    worst = 0.0
    for t in ts:
        worst = max(worst, abs(flat.Q(float(t)) - math.exp(-FLAT_HAZARD * t)))
    assert worst < CURVE_IDENTITY_ABS_TOL
    # the vectorised path agrees with the scalar one
    assert np.max(np.abs(flat.Q(ts) - np.exp(-FLAT_HAZARD * ts))) < CURVE_IDENTITY_ABS_TOL


def test_q_at_zero_is_one(flat: SurvivalCurve, three: SurvivalCurve, steep: SurvivalCurve) -> None:
    for curve in (flat, three, steep):
        assert curve.Q(0.0) == 1.0
        assert curve.cumulative_hazard(0.0) == 0.0


# --- criterion 2: three-pillar curve -----------------------------------------


def test_three_pillar_survival_at_four_years(three: SurvivalCurve) -> None:
    expected = math.exp(-(0.01 * 1 + 0.02 * 2 + 0.03 * 1))
    assert abs(three.Q(4.0) - expected) < CURVE_IDENTITY_ABS_TOL


@pytest.mark.parametrize(
    "t,expected_log",
    [
        (0.5, 0.01 * 0.5),
        (1.0, 0.01 * 1),
        (3.0, 0.01 * 1 + 0.02 * 2),
        (5.0, 0.01 * 1 + 0.02 * 2 + 0.03 * 2),
        (8.0, 0.01 * 1 + 0.02 * 2 + 0.03 * 2 + 0.03 * 3),  # flat beyond 5Y
    ],
)
def test_three_pillar_cumulative_hazard_by_hand(three: SurvivalCurve, t: float, expected_log: float) -> None:
    assert abs(three.cumulative_hazard(t) - expected_log) < CURVE_IDENTITY_ABS_TOL
    assert abs(three.Q(t) - math.exp(-expected_log)) < CURVE_IDENTITY_ABS_TOL


# --- criterion 3: density integrates to the default probability ------------


def _integrate_density(curve: SurvivalCurve, horizon: float) -> float:
    """quad on each pillar interval up to the horizon, so the integrand is smooth on every piece."""
    knots = [t for t in (0.0, *curve.pillar_times) if t < horizon] + [horizon]
    total = 0.0
    for a, b in zip(knots, knots[1:]):
        value, _ = quad(curve.density, a, b, epsabs=1e-13, epsrel=1e-13)
        total += value
    return total


@pytest.mark.parametrize("horizon", DENSITY_HORIZONS)
def test_density_integrates_to_one_minus_q(steep: SurvivalCurve, three: SurvivalCurve, horizon: float) -> None:
    for curve in (steep, three):
        assert abs(_integrate_density(curve, horizon) - (1.0 - curve.Q(horizon))) < DENSITY_INTEGRAL_ABS_TOL


def test_density_is_hazard_times_survival(steep: SurvivalCurve) -> None:
    ts = np.linspace(0.0, 12.0, 25)
    assert np.max(np.abs(steep.density(ts) - steep.hazard(ts) * steep.Q(ts))) < CURVE_IDENTITY_ABS_TOL


# --- criterion 4: with_as_of ------------------------------------------------


def test_calendar_shift_keeps_q_ratios_between_pillar_dates(steep: SurvivalCurve) -> None:
    new_as_of = AS_OF + timedelta(days=SHIFT_DAYS)
    shifted = steep.with_as_of(new_as_of, "calendar")
    assert shifted.as_of == new_as_of
    assert shifted.pillar_dates == steep.pillar_dates
    assert shifted.pillar_hazards == steep.pillar_hazards
    worst = 0.0
    for d1, d2 in zip(steep.pillar_dates, steep.pillar_dates[1:]):
        before = steep.Q_on(d2) / steep.Q_on(d1)
        after = shifted.Q_on(d2) / shifted.Q_on(d1)
        worst = max(worst, abs(after - before))
    assert worst < CURVE_IDENTITY_ABS_TOL
    # times shrink by exactly the shift
    for t_old, t_new in zip(steep.pillar_times, shifted.pillar_times):
        assert abs((t_old - t_new) - SHIFT_DAYS / ACT365F_BASIS) < CURVE_IDENTITY_ABS_TOL


def test_calendar_shift_keeps_q_ratio_at_arbitrary_dates(steep: SurvivalCurve) -> None:
    """The ratio holds between any two dates after the new as_of, not only at pillars."""
    new_as_of = AS_OF + timedelta(days=SHIFT_DAYS)
    shifted = steep.with_as_of(new_as_of, "calendar")
    d1, d2 = AS_OF + timedelta(days=100), AS_OF + timedelta(days=1700)
    assert abs(shifted.Q_on(d2) / shifted.Q_on(d1) - steep.Q_on(d2) / steep.Q_on(d1)) < CURVE_IDENTITY_ABS_TOL


def test_tenor_shift_keeps_times_and_hazards(steep: SurvivalCurve) -> None:
    new_as_of = AS_OF + timedelta(days=SHIFT_DAYS)
    shifted = steep.with_as_of(new_as_of, "tenor")
    assert shifted.as_of == new_as_of
    assert shifted.pillar_dates == tuple(d + timedelta(days=SHIFT_DAYS) for d in steep.pillar_dates)
    for t_old, t_new in zip(steep.pillar_times, shifted.pillar_times):
        assert abs(t_old - t_new) < CURVE_IDENTITY_ABS_TOL
    for h_old, h_new in zip(steep.pillar_hazards, shifted.pillar_hazards):
        assert abs(h_old - h_new) < CURVE_IDENTITY_ABS_TOL
    ts = np.linspace(0.0, 12.0, 25)
    assert np.max(np.abs(shifted.Q(ts) - steep.Q(ts))) < CURVE_IDENTITY_ABS_TOL


def test_calendar_shift_drops_pillars_on_or_before_the_new_date(steep: SurvivalCurve) -> None:
    first = steep.pillar_dates[0]
    on = steep.with_as_of(first, "calendar")
    assert on.pillar_dates == steep.pillar_dates[1:]
    assert on.pillar_hazards == steep.pillar_hazards[1:]
    day_before = steep.with_as_of(first - timedelta(days=1), "calendar")
    assert day_before.pillar_dates == steep.pillar_dates
    with pytest.raises(ValueError):
        steep.with_as_of(steep.pillar_dates[-1], "calendar")


def test_shift_rejects_bad_mode_and_backward_calendar_shift(steep: SurvivalCurve, discount: DiscountCurve) -> None:
    with pytest.raises(ValueError):
        steep.with_as_of(AS_OF, "roll")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        steep.with_as_of(AS_OF - timedelta(days=1), "calendar")
    with pytest.raises(ValueError):
        discount.with_as_of(AS_OF - timedelta(days=1), "calendar")


def test_discount_calendar_shift_keeps_df_ratios_and_drops_passed_nodes(discount: DiscountCurve) -> None:
    new_as_of = AS_OF + timedelta(days=45)  # past the 1M node (15 Oct 2026)
    shifted = discount.with_as_of(new_as_of, "calendar")
    assert shifted.as_of == new_as_of
    assert shifted.node_dates == discount.node_dates[1:]
    assert shifted.tenors == () and shifted.par_rates_pct == ()
    worst = 0.0
    for d1, d2 in zip(shifted.node_dates, shifted.node_dates[1:]):
        worst = max(worst, abs(shifted.df_on(d2) / shifted.df_on(d1) - discount.df_on(d2) / discount.df_on(d1)))
    assert worst < CURVE_IDENTITY_ABS_TOL
    # forwards between the same dates are unchanged, including from the new as_of to the first surviving node
    for d1, d2 in ((new_as_of, shifted.node_dates[0]), (date(2028, 1, 1), date(2029, 1, 1)), (date(2040, 1, 1), date(2050, 1, 1))):
        f_old = discount.forward((d1 - AS_OF).days / ACT365F_BASIS, (d2 - AS_OF).days / ACT365F_BASIS)
        f_new = shifted.forward((d1 - new_as_of).days / ACT365F_BASIS, (d2 - new_as_of).days / ACT365F_BASIS)
        assert abs(f_old - f_new) < CURVE_IDENTITY_ABS_TOL
    assert shifted.df(0.0) == 1.0


def test_discount_tenor_shift_keeps_times_dfs_and_inputs(discount: DiscountCurve) -> None:
    new_as_of = AS_OF + timedelta(days=45)
    shifted = discount.with_as_of(new_as_of, "tenor")
    assert shifted.as_of == new_as_of
    assert shifted.node_dates == tuple(d + timedelta(days=45) for d in discount.node_dates)
    assert shifted.node_times == discount.node_times
    assert shifted.node_dfs == discount.node_dfs
    assert shifted.tenors == discount.tenors and shifted.par_rates_pct == discount.par_rates_pct


# --- criterion 5: hazard at the pillars -------------------------------------


def test_hazard_at_pillar_is_that_intervals_hazard_and_just_after_is_the_next(three: SurvivalCurve, steep: SurvivalCurve) -> None:
    for curve in (three, steep):
        hazards = curve.pillar_hazards
        for i, t_i in enumerate(curve.pillar_times):
            assert curve.hazard(t_i) == hazards[i]
            expected_after = hazards[i + 1] if i + 1 < len(hazards) else hazards[i]
            assert curve.hazard(t_i + EPS) == expected_after
        assert curve.hazard(0.0) == hazards[0]
        assert curve.hazard(curve.pillar_times[-1] + 20.0) == hazards[-1]


# --- criterion 6: negative hazards ------------------------------------------


def test_negative_hazard_raises() -> None:
    dates = standard_pillar_dates(AS_OF)
    with pytest.raises(ValueError):
        SurvivalCurve(as_of=AS_OF, pillar_dates=dates, pillar_hazards=(0.01,) * 7 + (-0.01,))
    with pytest.raises(ValueError):
        SurvivalCurve(as_of=AS_OF, pillar_dates=dates, pillar_hazards=(-1e-12,) + (0.01,) * 7)


def test_zero_hazard_is_allowed_and_gives_no_default() -> None:
    curve = SurvivalCurve.flat(AS_OF, 0.0)
    assert curve.Q(7.0) == 1.0


def test_bad_pillars_raise() -> None:
    dates = standard_pillar_dates(AS_OF)
    with pytest.raises(ValueError):
        SurvivalCurve(as_of=AS_OF, pillar_dates=(), pillar_hazards=())
    with pytest.raises(ValueError):
        SurvivalCurve(as_of=AS_OF, pillar_dates=dates, pillar_hazards=(0.01,) * 7)
    with pytest.raises(ValueError):
        SurvivalCurve(as_of=AS_OF, pillar_dates=(dates[1], dates[0]), pillar_hazards=(0.01, 0.01))
    with pytest.raises(ValueError):
        SurvivalCurve(as_of=dates[0], pillar_dates=dates, pillar_hazards=(0.01,) * 8)
    with pytest.raises(ValueError):
        SurvivalCurve(as_of=AS_OF, pillar_dates=dates, pillar_hazards=(math.nan,) + (0.01,) * 7)
    with pytest.raises(ValueError):
        SurvivalCurve.flat(AS_OF, 0.01).Q(-1.0)


# --- Q is a survival probability ---------------------------------------------


def test_q_is_non_increasing_and_in_unit_interval(steep: SurvivalCurve) -> None:
    ts = np.arange(0, 20 * ACT365F_BASIS + 1) / ACT365F_BASIS
    q = steep.Q(ts)
    assert q[0] == 1.0
    assert np.all(np.diff(q) <= 0.0)
    assert np.all(q > 0.0) and np.all(q <= 1.0)


# --- recovery curve -----------------------------------------------------------


def test_flat_recovery_returns_the_constant() -> None:
    curve = RecoveryCurve.flat(RECOVERY_SENIOR, AS_OF)
    assert curve.as_of == AS_OF
    for t in (0.0, 0.5, 5.0, 30.0):
        assert curve.R(t) == RECOVERY_SENIOR
    assert np.all(curve.R(np.linspace(0.0, 10.0, 11)) == RECOVERY_SENIOR)
    assert RecoveryCurve.flat(RECOVERY_HY_INDEX, AS_OF).R(5.0) == RECOVERY_HY_INDEX


def test_recovery_shift_keeps_the_level_in_both_modes() -> None:
    curve = RecoveryCurve.flat(RECOVERY_SENIOR, AS_OF)
    new_as_of = AS_OF + timedelta(days=SHIFT_DAYS)
    for mode in ("calendar", "tenor"):
        shifted = curve.with_as_of(new_as_of, mode)
        assert shifted.as_of == new_as_of and shifted.R(3.0) == RECOVERY_SENIOR


def test_recovery_outside_unit_interval_raises() -> None:
    with pytest.raises(ValueError):
        RecoveryCurve.flat(-0.01, AS_OF)
    with pytest.raises(ValueError):
        RecoveryCurve.flat(1.01, AS_OF)
    with pytest.raises(ValueError):
        RecoveryCurve.flat(RECOVERY_SENIOR, AS_OF).R(-1.0)


# --- QuantLib oracle ----------------------------------------------------------


def test_survival_matches_quantlib_backward_flat_hazard_curve(steep: SurvivalCurve, three: SurvivalCurve) -> None:
    """ql.HazardRateCurve(dates, hazards, Actual365Fixed()) is backward-flat:
    hazards[i] applies on (dates[i-1], dates[i]], with dates[0] the reference
    date, and the last hazard extrapolates. Handing it (as_of, pillars) with
    (lambda_1, lambda_1, ..., lambda_n) is the Section 7 construction."""
    import QuantLib as ql

    for curve in (steep, three):
        as_of = ql.Date(curve.as_of.day, curve.as_of.month, curve.as_of.year)
        ql.Settings.instance().evaluationDate = as_of
        dates = [as_of] + [ql.Date(d.day, d.month, d.year) for d in curve.pillar_dates]
        hazards = [curve.pillar_hazards[0], *curve.pillar_hazards]
        oracle = ql.HazardRateCurve(dates, hazards, ql.Actual365Fixed())
        oracle.enableExtrapolation()
        rows = []
        for t in np.linspace(0.0, 14.0, 50):
            rows.append((float(t), oracle.survivalProbability(float(t)), curve.Q(float(t))))
        worst = max(abs(q_ql - q_ours) for _, q_ql, q_ours in rows)
        assert worst < QL_SURVIVAL_ABS_TOL, rows
        for d in curve.pillar_dates:
            q_ql = oracle.survivalProbability(ql.Date(d.day, d.month, d.year))
            assert abs(q_ql - curve.Q_on(d)) < QL_SURVIVAL_ABS_TOL
        for t_i, lam in zip(curve.pillar_times, curve.pillar_hazards):
            assert abs(oracle.hazardRate(t_i) - lam) < QL_SURVIVAL_ABS_TOL
