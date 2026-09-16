"""The premium and protection legs of a CDS, in two engines (BUILD_PLAN.md Section 4).

Symbols follow docs/SPEC.md section 6: P(t) discount factor, Q(t) survival
probability, R recovery, coupon periods j with accrual fractions Delta_j
(act/360), all times u act/365F years from the valuation date as_of.

    PV_prem = s * A,   A = annuity_coupon + annuity_accrual        (SPEC 6.2)
    annuity_coupon  = sum_j Delta_j * P(t_j^pay) * Q(t_j^obs)
    annuity_accrual = sum_j int_{period j} (u - tstart_j) * P(u) * (-dQ(u)) * 365/360
    PV_prot = (1 - R) * protection,  protection = int_{t_0}^{T} P(u) (-dQ(u))   (SPEC 6.3)

Integration limits and observation dates follow QuantLib's IsdaCdsEngine
(ql/pricingengines/credit/isdacdsengine.cpp, 1.43), which is the Section 7
oracle and is written to reproduce the ISDA C library. In that reading every
date is an end-of-day observation, so "the start of a day" is the end of the
day before:

- effective protection start = max(step_in, as_of + 1 day); the protection
  integral runs from the day before it (t_0 = 0 for a new trade valued on
  its trade date) to the unadjusted maturity T.
- coupon j pays Delta_j on its payment date and is observed to survive to
  the day before that payment date, t_j^obs = t(pay_j - 1). Only coupons
  paying after as_of count; the first coupon is a full coupon and the
  accrued before step-in is rebated in cash by the pricer (Section 5).
- accrual on default for coupon j runs from max(accrual_start_j, effective
  start) - 1 day to pay_j - 1 day, and the accrued fraction at u is
  (u - tstart_j) * 365/360 with tstart_j = t(accrual_start_j - 1) minus
  half a day when half_day_bias is on (the ISDA model's accrual bias,
  QuantLib's HalfDayBias). The 365/360 converts act/365F time to an
  act/360 fraction, as the ISDA model does.

isda engine. The grid is the union of {protection start, T}, the discount
nodes, the survival pillars and every accrual-integral boundary, so hazard
lambda and forward f are constant on each interval (a, b]. With
hhat = ln Q(a) - ln Q(b) = lambda * tau, fhat = ln P(a) - ln P(b) = f * tau,
x = hhat + fhat = (lambda + f) * tau and tau = b - a:

    int_a^b P(u) (-dQ(u)) = P(a) Q(a) lambda/(lambda + f) (1 - e^{-x})
                          = hhat/x * (P(a)Q(a) - P(b)Q(b))
    int_a^b (u - tstart) P(u) (-dQ(u)) = s_0 * [above] + hhat/x * tau * ((P(a)Q(a) - P(b)Q(b))/x - P(b)Q(b))

with s_0 = a - tstart. When |x| < TAYLOR_THRESHOLD both use their series
(QuantLib's Taylor fix), which also covers x = 0.

grid engine. Points every grid_days calendar days from the protection start
to T, plus every accrual-integral boundary. Protection
sum_k P(u_k) [Q(u_{k-1}) - Q(u_k)]; accrual on default
sum_k (u_mid,k - tstart_j) * 365/360 * P(u_k) [Q(u_{k-1}) - Q(u_k)] with the
midpoint accrual; coupon on survival as above. The error against the closed
form is first order in the step.

Both engines return LegValues per unit notional at the valuation date; the
pricer divides by P(t_settle) to state amounts at cash settlement.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

import numpy as np

from cds.conventions import ACT360_BASIS, ACT365F_BASIS
from cds.schedule import Schedule, year_fraction_act365f
from cds.types import DiscountCurve, RecoveryCurve, SurvivalCurve

__all__ = [
    "ENGINES",
    "Engine",
    "LegValues",
    "TAYLOR_THRESHOLD",
    "leg_values",
    "par_spread_bp",
    "protection_start_date",
]

Engine = Literal["isda", "grid"]
ENGINES = ("isda", "grid")

# Below this |x| = |(lambda + f) * tau| the closed forms lose digits to
# cancellation and the series are used instead (QuantLib's Taylor fix).
TAYLOR_THRESHOLD = 1e-4

# Basis points per unit of spread.
BP_PER_UNIT = 10_000.0

# act/365F time to act/360 accrual fraction: (u - tstart) * 365/360.
ACCRUAL_TIME_SCALE = ACT365F_BASIS / ACT360_BASIS

# The ISDA half-day accrual bias, in act/365F years.
HALF_DAY = 0.5 / ACT365F_BASIS

ONE_DAY = timedelta(days=1)


@dataclass(frozen=True)
class LegValues:
    """Leg values per unit notional at the valuation date.

    annuity_coupon and annuity_accrual are per unit of spread (A is their
    sum, so PV_prem = s * A). protection is the default integral without
    recovery, so PV_prot = (1 - R) * protection for a flat recovery;
    pv_protection applies (1 - R(t)) at the start of each interval and is
    the number the pricer uses.
    """

    annuity_coupon: float
    annuity_accrual: float
    protection: float
    pv_protection: float

    @property
    def annuity(self) -> float:
        """A = annuity_coupon + annuity_accrual, SPEC 6.2."""
        return self.annuity_coupon + self.annuity_accrual


def par_spread_bp(values: LegValues) -> float:
    """s_par = PV_prot / A (SPEC 6.4), in basis points."""
    return BP_PER_UNIT * values.pv_protection / values.annuity


def protection_start_date(as_of: date, step_in: date) -> date:
    """The day whose end the protection integral starts from: the day before
    max(step_in, as_of + 1). For a new trade valued on its trade date this
    is as_of itself."""
    return max(step_in, as_of + ONE_DAY) - ONE_DAY


@dataclass(frozen=True)
class _AccrualPeriod:
    """One coupon period's accrual-on-default integral: (t_start, t_end] and
    the time its accrual is measured from."""

    t_start: float
    t_end: float
    tstart: float


def _check_as_of(as_of: date, discount: DiscountCurve, survival: SurvivalCurve, recovery: RecoveryCurve) -> None:
    dates = {discount.as_of, survival.as_of, recovery.as_of}
    if dates != {as_of}:
        raise ValueError(f"curve as_of {sorted(dates)} do not all equal the valuation date {as_of}")


def _accrual_periods(schedule: Schedule, as_of: date, half_day_bias: bool) -> list[_AccrualPeriod]:
    """The accrual-on-default integrals, one per coupon period that is still
    accruing at the effective protection start."""
    effective_start = max(schedule.step_in, as_of + ONE_DAY)
    out: list[_AccrualPeriod] = []
    for acc_start, pay in zip(schedule.accrual_start, schedule.payment):
        start = max(acc_start, effective_start) - ONE_DAY
        end = pay - ONE_DAY
        if end <= start:
            continue
        tstart = year_fraction_act365f(as_of, acc_start - ONE_DAY) - (HALF_DAY if half_day_bias else 0.0)
        out.append(_AccrualPeriod(year_fraction_act365f(as_of, start), year_fraction_act365f(as_of, end), tstart))
    return out


def _coupon_on_survival(schedule: Schedule, as_of: date, discount: DiscountCurve, survival: SurvivalCurve) -> float:
    """sum_j Delta_j P(t_j^pay) Q(t(pay_j - 1)) over coupons paying after as_of."""
    total = 0.0
    for frac, pay in zip(schedule.accrual_fraction, schedule.payment):
        if pay <= as_of:
            continue
        total += frac * discount.df(year_fraction_act365f(as_of, pay)) * survival.Q(year_fraction_act365f(as_of, pay - ONE_DAY))
    return total


def _grid_times(
    as_of: date,
    d_prot0: date,
    t_maturity: float,
    periods: list[_AccrualPeriod],
    engine: Engine,
    discount: DiscountCurve,
    survival: SurvivalCurve,
    grid_days: int,
) -> np.ndarray:
    """Sorted unique times covering the protection and accrual integrals.

    isda: the curve nodes, so each interval has one hazard and one forward.
    grid: every grid_days days from the protection start. Both include the
    integral boundaries."""
    t_prot0 = year_fraction_act365f(as_of, d_prot0)
    t_end = max([t_maturity, *(p.t_end for p in periods)])
    points = {t_prot0, t_maturity, t_end}
    for p in periods:
        points.update((p.t_start, p.t_end))
    if engine == "isda":
        points.update(t for t in discount.node_times if t_prot0 < t < t_end)  # type: ignore[attr-defined]
        points.update(t for t in survival.pillar_times if t_prot0 < t < t_end)
    else:
        if grid_days < 1:
            raise ValueError("grid_days must be at least 1")
        n_days = round((t_end - t_prot0) * ACT365F_BASIS)
        points.update(year_fraction_act365f(as_of, d_prot0 + timedelta(days=k)) for k in range(0, n_days + 1, grid_days))
    return np.array(sorted(t for t in points if t_prot0 <= t <= t_end))


def _isda_intervals(a: np.ndarray, b: np.ndarray, pa: np.ndarray, pb: np.ndarray, qa: np.ndarray, qb: np.ndarray):
    """Per interval (a, b]: I = int P(-dQ) and J = int (u - a) P(-dQ), closed form."""
    tau = b - a
    hhat = np.log(qa) - np.log(qb)
    fhat = np.log(pa) - np.log(pb)
    x = hhat + fhat
    paqa, pbqb = pa * qa, pb * qb
    small = np.abs(x) < TAYLOR_THRESHOLD
    # Guard the divisions; the small branch overwrites these entries.
    xs = np.where(small, 1.0, x)
    i_exact = hhat / xs * (paqa - pbqb)
    j_exact = hhat / xs * tau * ((paqa - pbqb) / xs - pbqb)
    x2 = x * x
    # (1 - e^{-x})/x and (1 - (1 + x)e^{-x})/x^2 as series, the orders QuantLib uses.
    i_series = hhat * paqa * (1.0 - x / 2.0 + x2 / 6.0 - x2 * x / 24.0 + x2 * x2 / 120.0)
    j_series = hhat * paqa * tau * (0.5 - x / 3.0 + x2 / 8.0 - x2 * x / 30.0)
    return np.where(small, i_series, i_exact), np.where(small, j_series, j_exact)


def _grid_intervals(a: np.ndarray, b: np.ndarray, pa: np.ndarray, pb: np.ndarray, qa: np.ndarray, qb: np.ndarray):
    """Per interval: P at the end of the step times the default probability
    in it; J with the midpoint accrual (u_mid - a)."""
    dq = qa - qb
    i_grid = pb * dq
    return i_grid, 0.5 * (b - a) * i_grid


def leg_values(
    discount: DiscountCurve,
    survival: SurvivalCurve,
    recovery: RecoveryCurve,
    schedule: Schedule,
    as_of: date,
    half_day_bias: bool = True,
    engine: Engine = "isda",
    grid_days: int = 1,
) -> LegValues:
    """Both legs per unit notional at as_of. See the module docstring for
    the formulas and the integration limits."""
    if engine not in ENGINES:
        raise ValueError(f"unknown engine {engine!r}; expected one of {ENGINES}")
    _check_as_of(as_of, discount, survival, recovery)
    if schedule.maturity <= as_of:
        raise ValueError(f"maturity {schedule.maturity} is not after the valuation date {as_of}")

    d_prot0 = protection_start_date(as_of, schedule.step_in)
    t_maturity = year_fraction_act365f(as_of, schedule.maturity)
    periods = _accrual_periods(schedule, as_of, half_day_bias)
    times = _grid_times(as_of, d_prot0, t_maturity, periods, engine, discount, survival, grid_days)

    a, b = times[:-1], times[1:]
    pa, pb = discount.df(a), discount.df(b)
    qa, qb = survival.Q(a), survival.Q(b)
    per_interval = _isda_intervals if engine == "isda" else _grid_intervals
    i_k, j_k = per_interval(a, b, pa, pb, qa, qb)

    # Protection: intervals up to T, with (1 - R) at each interval start.
    in_prot = b <= t_maturity
    protection = float(np.sum(i_k[in_prot]))
    pv_protection = float(np.sum((1.0 - np.asarray(recovery.R(a[in_prot]))) * i_k[in_prot]))

    # Accrual on default: int (u - tstart) P (-dQ) = (a - tstart) * I + J per interval.
    accrual = 0.0
    for p in periods:
        lo = np.searchsorted(times, p.t_start)
        hi = np.searchsorted(times, p.t_end)
        sel = slice(lo, hi)
        accrual += float(np.sum((a[sel] - p.tstart) * i_k[sel] + j_k[sel]))
    accrual *= ACCRUAL_TIME_SCALE

    return LegValues(
        annuity_coupon=_coupon_on_survival(schedule, as_of, discount, survival),
        annuity_accrual=accrual,
        protection=protection,
        pv_protection=pv_protection,
    )
