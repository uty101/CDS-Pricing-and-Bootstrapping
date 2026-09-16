"""The textbook CDS model, for comparison only (BUILD_PLAN.md Section 5).

Continuous premium, continuous discounting at a flat rate r, a flat hazard
lambda, no accrual on default, no schedule, no day counts. With
k = lambda + r and maturity T in years:

    A       = (1 - e^{-kT}) / k                      the risky annuity
    PV_prot = (1 - R) * lambda * A                   = (1 - R) lambda/k (1 - e^{-kT})
    s_par   = PV_prot / A = lambda (1 - R)           the credit triangle, exact
    upfront = PV_prot - c * A                        buyer value at coupon c

At k = 0 the annuity is T. This module never imports cds.legs or
cds.schedule; Section 7's Table 5 sets it against the ISDA path.
"""

from __future__ import annotations

import math

__all__ = [
    "annuity",
    "implied_hazard",
    "par_spread_bp",
    "protection_pv",
    "survival",
    "upfront_pct",
]

BP_PER_UNIT = 10_000.0
PERCENT = 100.0


def _check(hazard: float, rate: float, maturity: float) -> None:
    if hazard < 0.0:
        raise ValueError(f"hazard {hazard!r} is negative")
    if maturity <= 0.0:
        raise ValueError(f"maturity {maturity!r} years is not positive")
    if not math.isfinite(rate):
        raise ValueError(f"rate {rate!r} is not finite")


def survival(hazard: float, t: float) -> float:
    """Q(t) = e^{-lambda t}."""
    if hazard < 0.0 or t < 0.0:
        raise ValueError("hazard and t must be non-negative")
    return math.exp(-hazard * t)


def annuity(hazard: float, rate: float, maturity: float) -> float:
    """A = (1 - e^{-kT}) / k with k = lambda + r; T when k = 0."""
    _check(hazard, rate, maturity)
    k = hazard + rate
    if k == 0.0:
        return maturity
    return -math.expm1(-k * maturity) / k


def protection_pv(hazard: float, rate: float, maturity: float, recovery: float) -> float:
    """PV_prot = (1 - R) * lambda * A."""
    if not (0.0 <= recovery <= 1.0):
        raise ValueError(f"recovery {recovery!r} is not in [0, 1]")
    return (1.0 - recovery) * hazard * annuity(hazard, rate, maturity)


def par_spread_bp(hazard: float, recovery: float) -> float:
    """s_par = lambda (1 - R), in bp: the same for every r and T."""
    if hazard < 0.0:
        raise ValueError(f"hazard {hazard!r} is negative")
    if not (0.0 <= recovery <= 1.0):
        raise ValueError(f"recovery {recovery!r} is not in [0, 1]")
    return BP_PER_UNIT * hazard * (1.0 - recovery)


def implied_hazard(spread_bp: float, recovery: float) -> float:
    """lambda = s / (1 - R), the inverse of the triangle."""
    if spread_bp < 0.0:
        raise ValueError(f"spread {spread_bp!r} bp is negative")
    if not (0.0 <= recovery < 1.0):
        raise ValueError(f"recovery {recovery!r} is not in [0, 1)")
    return spread_bp / BP_PER_UNIT / (1.0 - recovery)


def upfront_pct(hazard: float, rate: float, maturity: float, recovery: float, coupon_bp: float) -> float:
    """Buyer value PV_prot - c * A in % of notional; no accrued, no
    settlement discounting, so clean and dirty coincide."""
    if coupon_bp < 0.0:
        raise ValueError(f"coupon {coupon_bp!r} bp is negative")
    return PERCENT * (protection_pv(hazard, rate, maturity, recovery) - coupon_bp / BP_PER_UNIT * annuity(hazard, rate, maturity))
