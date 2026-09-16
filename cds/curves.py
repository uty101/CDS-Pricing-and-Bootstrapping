"""The curves: DiscountCurve (Section 2), SurvivalCurve and RecoveryCurve (Section 3).

DiscountCurve (BUILD_PLAN.md Part A.2, rows 1 and 2)

The curve is a set of nodes (t_i, P_i) with t in act/365F years from as_of
and P the discount factor. Between nodes ln P(t) is linear in t, which is the
same as a flat continuously compounded forward rate on each interval; this is
the ISDA model's interpolation (JpmcdsZeroPrice, JPMCDS_FLAT_FORWARDS) and
what QuantLib's IsdaCdsEngine expects. Before the first node the forward is
flat at the first node's zero rate, i.e. ln P is linear from (0, 1) to
(t_1, P_1). Beyond the last node the last interval's forward is extrapolated
flat.

bootstrap_ois builds the nodes from SOFR OIS par rates. An OIS of tenor T
with annual fixed act/360 payments on dates T_1..T_m and par rate K satisfies

    K * sum_k Delta_k * P(T_k) = 1 - P(T_m),   Delta_k = act/360(T_{k-1}, T_k),

the right-hand side being the value of the compounded floating leg. Tenors
under one year pay once, at T. Payment dates are the anniversaries of the
spot date rolled Following on the weekend-only calendar, and the spot date is
as_of itself (T+0), as docs/DATA_NOTE.md states. Nodes are solved one tenor at
a time, shortest first; a payment date that falls between the previous node
and the node being solved is interpolated log-linearly against the unknown,
so the built curve reprices every input with its own interpolation.

SurvivalCurve (BUILD_PLAN.md Part A.2 row 3, SPEC section 6.1)

Piecewise-constant hazard lambda_i on the pillar interval (t_{i-1}, t_i],
t_0 = 0, t_i act/365F years from as_of to pillar date i:

    Q(t) = exp(-sum_i lambda_i * (t_i - t_{i-1}))   summed over the intervals up to t,
    hazard(t) = lambda_i for t in (t_{i-1}, t_i],
    density(t) = -dQ/dt = hazard(t) * Q(t).

Beyond the last pillar the last hazard is extrapolated flat. hazard(0) is
lambda_1. The closed right end of each interval matches QuantLib's
backward-flat HazardRateCurve, which Section 7 hands the same pillars to.

RecoveryCurve

R(t), flat by default: RecoveryCurve.flat(R, as_of) returns the constant at
every t. No section needs a term structure of recovery.

with_as_of(new_as_of, mode) on all three curves, for Section 8's two thetas:
mode "calendar" keeps every node on its calendar date and recomputes times
from the new as_of (nodes that fall on or before the new date are dropped;
the hazards and the discount factor ratios between surviving nodes are
unchanged); mode "tenor" shifts every node date by the same number of days,
so times and hazards are unchanged and the curve is the same function of t.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Callable, Literal

import numpy as np
from scipy.optimize import brentq

from cds.calendars import adjust_following
from cds.conventions import DEFAULT_CALENDAR, PILLARS
from cds.schedule import standard_maturity, year_fraction_act360, year_fraction_act365f

__all__ = [
    "DiscountCurve",
    "RecoveryCurve",
    "ShiftMode",
    "SurvivalCurve",
    "bootstrap_ois",
    "discount_curve_from_file",
    "ois_payment_dates",
    "par_rate_from_curve",
    "read_rates_file",
    "standard_pillar_dates",
]

# The two ways a curve moves to a later valuation date (BUILD_PLAN.md Part C
# item 3): nodes fixed on their calendar dates, or fixed in tenor.
ShiftMode = Literal["calendar", "tenor"]
SHIFT_MODES = ("calendar", "tenor")


def _check_mode(mode: str) -> None:
    if mode not in SHIFT_MODES:
        raise ValueError(f"unknown shift mode {mode!r}; expected one of {SHIFT_MODES}")

MONTHS_PER_YEAR = 12

# Bounds and tolerance for the Brent solve of each node's discount factor.
# P is in (0, 2): the upper bound leaves room for negative rates.
DF_LOWER = 1e-8
DF_UPPER = 2.0
DF_XTOL = 1e-14


def _add_months(d: date, months: int) -> date:
    """d shifted by whole months, day clipped to the end of the target month."""
    total = d.year * MONTHS_PER_YEAR + (d.month - 1) + months
    year, month = divmod(total, MONTHS_PER_YEAR)
    month += 1
    next_month_start = date(year + (month == 12), month % 12 + 1, 1)
    days_in_month = (next_month_start - date(year, month, 1)).days
    return date(year, month, min(d.day, days_in_month))


def _tenor_months(tenor: str) -> int:
    unit = tenor[-1].upper()
    n = int(tenor[:-1])
    if unit == "M":
        return n
    if unit == "Y":
        return n * MONTHS_PER_YEAR
    raise ValueError(f"unknown tenor {tenor!r}; expected like '3M' or '5Y'")


def ois_payment_dates(as_of: date, tenor: str, calendar: str = DEFAULT_CALENDAR) -> tuple[date, ...]:
    """Fixed-leg payment dates of an OIS traded spot on as_of: annual
    anniversaries rolled Following, or a single payment at T under one year."""
    months = _tenor_months(tenor)
    if months <= 0:
        raise ValueError(f"tenor {tenor!r} is not positive")
    if months < MONTHS_PER_YEAR:
        return (adjust_following(_add_months(as_of, months), calendar),)
    if months % MONTHS_PER_YEAR:
        raise ValueError(f"tenor {tenor!r} over one year must be a whole number of years")
    years = months // MONTHS_PER_YEAR
    return tuple(adjust_following(_add_months(as_of, MONTHS_PER_YEAR * k), calendar) for k in range(1, years + 1))


def _log_linear(t: np.ndarray, times: np.ndarray, log_dfs: np.ndarray) -> np.ndarray:
    """ln P(t) by linear interpolation of the nodes (times, log_dfs), which
    start at (0, 0); flat forward extrapolation beyond the last node."""
    idx = np.searchsorted(times, t, side="right")
    idx = np.clip(idx, 1, len(times) - 1)
    t0, t1 = times[idx - 1], times[idx]
    w = (t - t0) / (t1 - t0)
    return log_dfs[idx - 1] + w * (log_dfs[idx] - log_dfs[idx - 1])


@dataclass(frozen=True)
class DiscountCurve:
    """Log-linear discount curve. Times are act/365F years from as_of.

    node_dates and node_dfs are the bootstrapped nodes (the OIS maturities).
    tenors and par_rates_pct are the inputs the nodes were solved from, kept
    so Section 8 can bump them and rebuild for IR01.
    """

    as_of: date
    node_dates: tuple[date, ...]
    node_dfs: tuple[float, ...]
    tenors: tuple[str, ...] = ()
    par_rates_pct: tuple[float, ...] = ()
    calendar: str = DEFAULT_CALENDAR
    node_times: tuple[float, ...] = field(init=False)
    _times: np.ndarray = field(init=False, repr=False, compare=False)
    _log_dfs: np.ndarray = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not self.node_dates:
            raise ValueError("a discount curve needs at least one node")
        if len(self.node_dates) != len(self.node_dfs):
            raise ValueError("node_dates and node_dfs differ in length")
        if any(d1 <= d0 for d0, d1 in zip((self.as_of, *self.node_dates), self.node_dates)):
            raise ValueError("node_dates must be strictly increasing and after as_of")
        if any(p <= 0 for p in self.node_dfs):
            raise ValueError("discount factors must be positive")
        times = tuple(year_fraction_act365f(self.as_of, d) for d in self.node_dates)
        object.__setattr__(self, "node_times", times)
        object.__setattr__(self, "_times", np.array((0.0, *times)))
        object.__setattr__(self, "_log_dfs", np.log(np.array((1.0, *self.node_dfs))))

    def df(self, t: float) -> float:
        """P(t). t = 0 gives 1; negative t is an error."""
        arr = np.asarray(t, dtype=float)
        if np.any(arr < 0):
            raise ValueError("t must be non-negative")
        out = np.exp(_log_linear(arr, self._times, self._log_dfs))
        return float(out) if out.ndim == 0 else out

    def forward(self, t1: float, t2: float) -> float:
        """Continuously compounded forward f on (t1, t2): ln(P(t1)/P(t2)) / (t2 - t1).
        Constant on each node interval, which is the flat forward the isda
        engine uses per merged-grid interval."""
        if t2 <= t1:
            raise ValueError("t2 must be after t1")
        return (math.log(self.df(t1)) - math.log(self.df(t2))) / (t2 - t1)

    def zero_rate(self, t: float) -> float:
        """Continuously compounded act/365F zero rate: -ln P(t) / t."""
        if t <= 0:
            raise ValueError("t must be positive")
        return -math.log(self.df(t)) / t

    def df_on(self, d: date) -> float:
        """P at a calendar date."""
        return self.df(year_fraction_act365f(self.as_of, d))

    def with_as_of(self, new_as_of: date, mode: ShiftMode) -> DiscountCurve:
        """The curve seen from a later valuation date.

        "calendar": nodes stay on their dates; those on or before new_as_of
        are dropped and the survivors are divided by P(new_as_of), so every
        ratio P(d2)/P(d1) between surviving nodes, and every forward, is
        unchanged. The input par rates no longer describe the nodes and are
        not carried. "tenor": every node date moves by (new_as_of - as_of)
        days, so node_times and node_dfs are unchanged and the inputs are
        kept.
        """
        _check_mode(mode)
        if mode == "tenor":
            shift = new_as_of - self.as_of
            return DiscountCurve(
                as_of=new_as_of,
                node_dates=tuple(d + shift for d in self.node_dates),
                node_dfs=self.node_dfs,
                tenors=self.tenors,
                par_rates_pct=self.par_rates_pct,
                calendar=self.calendar,
            )
        if new_as_of < self.as_of:
            raise ValueError("calendar mode needs new_as_of on or after as_of")
        p_new = self.df_on(new_as_of)
        kept = [(d, p / p_new) for d, p in zip(self.node_dates, self.node_dfs) if d > new_as_of]
        if not kept:
            raise ValueError("no discount node is after the new as_of")
        return DiscountCurve(
            as_of=new_as_of,
            node_dates=tuple(d for d, _ in kept),
            node_dfs=tuple(p for _, p in kept),
            calendar=self.calendar,
        )


def standard_pillar_dates(as_of: date) -> tuple[date, ...]:
    """The pillar dates of a curve valued on as_of: the standard maturities
    of the tenors in PILLARS (BUILD_PLAN.md Part A.2 row 3)."""
    return tuple(standard_maturity(as_of, tenor) for tenor in PILLARS)


@dataclass(frozen=True)
class SurvivalCurve:
    """Piecewise-constant hazard curve. Times are act/365F years from as_of.

    pillar_hazards[i] is lambda_i, flat on (t_{i-1}, t_i] with t_0 = 0 and
    t_i the act/365F time to pillar_dates[i]. Hazards are annualised
    intensities (0.01 is 1% a year), never in bp.
    """

    as_of: date
    pillar_dates: tuple[date, ...]
    pillar_hazards: tuple[float, ...]
    pillar_times: tuple[float, ...] = field(init=False)
    _times: np.ndarray = field(init=False, repr=False, compare=False)
    _hazards: np.ndarray = field(init=False, repr=False, compare=False)
    _cum_hazard: np.ndarray = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not self.pillar_dates:
            raise ValueError("a survival curve needs at least one pillar")
        if len(self.pillar_dates) != len(self.pillar_hazards):
            raise ValueError("pillar_dates and pillar_hazards differ in length")
        if any(d1 <= d0 for d0, d1 in zip((self.as_of, *self.pillar_dates), self.pillar_dates)):
            raise ValueError("pillar_dates must be strictly increasing and after as_of")
        if any(not math.isfinite(h) for h in self.pillar_hazards):
            raise ValueError("hazards must be finite")
        if any(h < 0 for h in self.pillar_hazards):
            raise ValueError("hazards must be non-negative")
        times = tuple(year_fraction_act365f(self.as_of, d) for d in self.pillar_dates)
        hazards = np.array(self.pillar_hazards, dtype=float)
        nodes = np.array((0.0, *times))
        # H_i = sum_{k<=i} lambda_k (t_k - t_{k-1}), the cumulative hazard at pillar i; H_0 = 0.
        cum = np.concatenate(([0.0], np.cumsum(hazards * np.diff(nodes))))
        object.__setattr__(self, "pillar_times", times)
        object.__setattr__(self, "pillar_hazards", tuple(float(h) for h in hazards))
        object.__setattr__(self, "_times", nodes)
        object.__setattr__(self, "_hazards", hazards)
        object.__setattr__(self, "_cum_hazard", cum)

    @classmethod
    def flat(cls, as_of: date, hazard: float, pillar_dates: tuple[date, ...] | None = None) -> SurvivalCurve:
        """One hazard on every pillar; the standard pillars unless given."""
        dates = standard_pillar_dates(as_of) if pillar_dates is None else tuple(pillar_dates)
        return cls(as_of=as_of, pillar_dates=dates, pillar_hazards=tuple(float(hazard) for _ in dates))

    def _interval(self, t: np.ndarray) -> np.ndarray:
        """0-based index i of the interval (t_{i-1}, t_i] holding t; t = 0
        and t beyond the last pillar map to the first and last interval."""
        idx = np.searchsorted(self._times[1:], t, side="left")
        return np.clip(idx, 0, len(self._hazards) - 1)

    def cumulative_hazard(self, t: float) -> float:
        """H(t) = -ln Q(t) = sum over the intervals up to t of lambda_i * length."""
        arr = np.asarray(t, dtype=float)
        if np.any(arr < 0):
            raise ValueError("t must be non-negative")
        i = self._interval(arr)
        out = self._cum_hazard[i] + self._hazards[i] * (arr - self._times[i])
        return float(out) if out.ndim == 0 else out

    def Q(self, t: float) -> float:  # noqa: N802 - the spec's symbol
        """Survival probability Q(t) = exp(-H(t)); Q(0) = 1."""
        out = np.exp(-np.asarray(self.cumulative_hazard(t)))
        return float(out) if out.ndim == 0 else out

    def hazard(self, t: float) -> float:
        """lambda(t): lambda_i for t in (t_{i-1}, t_i], lambda_1 at t = 0, the
        last hazard beyond the last pillar."""
        arr = np.asarray(t, dtype=float)
        if np.any(arr < 0):
            raise ValueError("t must be non-negative")
        out = self._hazards[self._interval(arr)]
        return float(out) if out.ndim == 0 else out

    def density(self, t: float) -> float:
        """Default density -dQ/dt = lambda(t) * Q(t)."""
        out = np.asarray(self.hazard(t)) * np.asarray(self.Q(t))
        return float(out) if out.ndim == 0 else out

    def Q_on(self, d: date) -> float:  # noqa: N802 - the spec's symbol
        """Q at a calendar date."""
        return self.Q(year_fraction_act365f(self.as_of, d))

    def with_as_of(self, new_as_of: date, mode: ShiftMode) -> SurvivalCurve:
        """The curve seen from a later valuation date.

        "calendar": pillars stay on their dates; those on or before
        new_as_of are dropped and the rest keep their hazards, so
        Q(d2)/Q(d1) between any two surviving pillar dates is unchanged.
        "tenor": every pillar date moves by (new_as_of - as_of) days, so
        pillar_times and pillar_hazards are unchanged.
        """
        _check_mode(mode)
        if mode == "tenor":
            shift = new_as_of - self.as_of
            return SurvivalCurve(
                as_of=new_as_of,
                pillar_dates=tuple(d + shift for d in self.pillar_dates),
                pillar_hazards=self.pillar_hazards,
            )
        if new_as_of < self.as_of:
            raise ValueError("calendar mode needs new_as_of on or after as_of")
        kept = [(d, h) for d, h in zip(self.pillar_dates, self.pillar_hazards) if d > new_as_of]
        if not kept:
            raise ValueError("no pillar is after the new as_of")
        return SurvivalCurve(
            as_of=new_as_of,
            pillar_dates=tuple(d for d, _ in kept),
            pillar_hazards=tuple(h for _, h in kept),
        )


@dataclass(frozen=True)
class RecoveryCurve:
    """Recovery rate R(t). Flat: the same fraction of notional at every t."""

    as_of: date
    recovery: float

    def __post_init__(self) -> None:
        if not (0.0 <= self.recovery <= 1.0):
            raise ValueError(f"recovery {self.recovery!r} is not in [0, 1]")

    @classmethod
    def flat(cls, recovery: float, as_of: date) -> RecoveryCurve:
        return cls(as_of=as_of, recovery=float(recovery))

    def R(self, t: float) -> float:  # noqa: N802 - the spec's symbol
        """R(t): the constant, for a float or an array of t."""
        arr = np.asarray(t, dtype=float)
        if np.any(arr < 0):
            raise ValueError("t must be non-negative")
        out = np.full_like(arr, self.recovery)
        return float(out) if out.ndim == 0 else out

    def with_as_of(self, new_as_of: date, mode: ShiftMode) -> RecoveryCurve:
        """A flat recovery is the same in both modes; only as_of changes."""
        _check_mode(mode)
        return RecoveryCurve(as_of=new_as_of, recovery=self.recovery)


def _par_rate(as_of: date, pay_dates: tuple[date, ...], df_at: Callable[[date], float]) -> float:
    """K = (1 - P(T_m)) / sum_k Delta_k P(T_k) for the given payment dates."""
    starts = (as_of, *pay_dates[:-1])
    annuity = sum(year_fraction_act360(d0, d1) * df_at(d1) for d0, d1 in zip(starts, pay_dates))
    return (1.0 - df_at(pay_dates[-1])) / annuity


def bootstrap_ois(
    as_of: date,
    tenors: tuple[str, ...] | list[str],
    par_rates_pct: tuple[float, ...] | list[float],
    calendar: str = DEFAULT_CALENDAR,
) -> DiscountCurve:
    """Solve the discount factor at each OIS maturity, shortest tenor first.

    For tenor m with payment dates T_1..T_m and unknown P_m = P(T_m), the
    fixed-leg annuity uses the built curve for dates up to the previous node
    and log-linear interpolation between the previous node and (T_m, P_m)
    for the dates in between. Brent on P_m solves
    K * sum_k Delta_k P(T_k) - (1 - P_m) = 0.
    """
    if len(tenors) != len(par_rates_pct):
        raise ValueError("tenors and par_rates_pct differ in length")
    if not tenors:
        raise ValueError("no tenors to bootstrap")
    schedule = [ois_payment_dates(as_of, tenor, calendar) for tenor in tenors]
    maturities = [dates[-1] for dates in schedule]
    if any(m1 <= m0 for m0, m1 in zip(maturities, maturities[1:])):
        raise ValueError("tenors must be in strictly increasing maturity order")

    node_dates: list[date] = []
    node_dfs: list[float] = []
    for pay_dates, rate_pct in zip(schedule, par_rates_pct):
        rate = rate_pct / 100.0
        t_m = year_fraction_act365f(as_of, pay_dates[-1])
        t_prev = year_fraction_act365f(as_of, node_dates[-1]) if node_dates else 0.0
        log_prev = math.log(node_dfs[-1]) if node_dfs else 0.0
        built = DiscountCurve(as_of=as_of, node_dates=tuple(node_dates), node_dfs=tuple(node_dfs)) if node_dates else None

        def df_at(d: date, p_m: float) -> float:
            t = year_fraction_act365f(as_of, d)
            if t <= t_prev:
                return built.df(t) if built is not None else 1.0
            w = (t - t_prev) / (t_m - t_prev)
            return math.exp(log_prev + w * (math.log(p_m) - log_prev))

        def objective(p_m: float) -> float:
            return _par_rate(as_of, pay_dates, lambda d: df_at(d, p_m)) - rate

        p_solved = brentq(objective, DF_LOWER, DF_UPPER, xtol=DF_XTOL)
        node_dates.append(pay_dates[-1])
        node_dfs.append(float(p_solved))

    return DiscountCurve(
        as_of=as_of,
        node_dates=tuple(node_dates),
        node_dfs=tuple(node_dfs),
        tenors=tuple(tenors),
        par_rates_pct=tuple(float(r) for r in par_rates_pct),
        calendar=calendar,
    )


def par_rate_from_curve(curve: DiscountCurve, tenor: str) -> float:
    """The OIS par rate (in percent) the curve implies for a tenor; used to
    check that the bootstrap reprices its inputs."""
    pay_dates = ois_payment_dates(curve.as_of, tenor, curve.calendar)
    return 100.0 * _par_rate(curve.as_of, pay_dates, curve.df_on)


def read_rates_file(path: str | Path) -> dict:
    """The rates snapshot as written in BUILD_PLAN.md Part D.3."""
    with Path(path).open(encoding="utf-8") as fh:
        data = json.load(fh)
    for key in ("as_of", "tenors", "par_rates_pct", "source", "source_url", "snapshot_taken", "note"):
        if key not in data or data[key] in ("", None, []):
            raise ValueError(f"rates file {path} is missing {key!r}")
    if data["fixed_frequency"] != "annual" or data["fixed_day_count"] != "act/360":
        raise ValueError(f"rates file {path} is not annual act/360, which is the only convention bootstrap_ois implements")
    return data


def discount_curve_from_file(path: str | Path, calendar: str = DEFAULT_CALENDAR) -> DiscountCurve:
    data = read_rates_file(path)
    return bootstrap_ois(date.fromisoformat(data["as_of"]), data["tenors"], data["par_rates_pct"], calendar)
