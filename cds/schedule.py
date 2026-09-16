"""IMM dates, standard maturities, and the coupon schedule of a standard CDS.

Rules (BUILD_PLAN.md Part A.1, resolved in docs/CONVENTIONS_RESOLVED.md):

- Coupon dates are the IMM 20ths (20 Mar, 20 Jun, 20 Sep, 20 Dec).
- Standard maturity: anchor + tenor + 3 months, where the anchor is the most
  recent 20 Mar / 20 Sep on or before the trade date (semi-annual rule since
  20 Dec 2015) or the most recent IMM 20th (quarterly rule, 2009 to 2015).
- Protection starts at trade date + 1 day (step-in). Cash settles at trade
  date + 3 business days.
- Accrual periods run between the Following-adjusted IMM dates, except the
  last, which ends on the unadjusted maturity and accrues one extra day.
  Accrual fractions are act/360.
- The first accrual date is the adjusted IMM 20th on or before the step-in
  date. When the adjusted 20th falls after the step-in date (the 20th was a
  weekend), the period before it is used instead. This is QuantLib's
  DateGeneration::CDS2015 behaviour, confirmed against ql.Schedule.
- Accrued at settlement covers the days from the first accrual date up to
  but excluding the step-in date.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from cds.calendars import add_business_days, adjust_following
from cds.conventions import (
    ACT360_BASIS,
    ACT365F_BASIS,
    CASH_SETTLE_BUSINESS_DAYS,
    DEFAULT_CALENDAR,
    DEFAULT_ROLL_RULE,
    IMM_DAY,
    IMM_MONTHS,
    PILLAR_MONTHS,
    PILLARS,
    ROLL_MONTHS_2015,
    ROLL_RULES,
    STEP_IN_DAYS,
)

__all__ = [
    "Schedule",
    "adjust_following",
    "cds_schedule",
    "imm_dates_between",
    "is_imm_date",
    "next_imm",
    "previous_imm",
    "standard_maturity",
    "year_fraction_act360",
    "year_fraction_act365f",
]

QUARTER_MONTHS = 3


def _add_months(d: date, months: int) -> date:
    """d shifted by a whole number of months; d is always a 20th here, so the
    day of month never overflows."""
    total = d.year * 12 + (d.month - 1) + months
    return date(total // 12, total % 12 + 1, d.day)


def is_imm_date(d: date) -> bool:
    return d.day == IMM_DAY and d.month in IMM_MONTHS


def previous_imm(d: date) -> date:
    """The latest IMM 20th on or before d."""
    candidate = date(d.year, d.month, IMM_DAY)
    if candidate > d:
        candidate = _add_months(candidate, -1)
    while candidate.month not in IMM_MONTHS:
        candidate = _add_months(candidate, -1)
    return candidate


def next_imm(d: date) -> date:
    """The earliest IMM 20th strictly after d."""
    return _add_months(previous_imm(d), QUARTER_MONTHS)


def imm_dates_between(start: date, end: date) -> list[date]:
    """IMM 20ths d with start <= d <= end, ascending."""
    out: list[date] = []
    d = previous_imm(start)
    if d < start:
        d = _add_months(d, QUARTER_MONTHS)
    while d <= end:
        out.append(d)
        d = _add_months(d, QUARTER_MONTHS)
    return out


def _roll_anchor(trade_date: date, roll_rule: str) -> date:
    """The most recent roll date on or before the trade date."""
    if roll_rule not in ROLL_RULES:
        raise ValueError(f"unknown roll rule {roll_rule!r}; expected one of {ROLL_RULES}")
    anchor = previous_imm(trade_date)
    if roll_rule == "semiannual_2015":
        while anchor.month not in ROLL_MONTHS_2015:
            anchor = _add_months(anchor, -QUARTER_MONTHS)
    return anchor


def standard_maturity(trade_date: date, tenor: str, roll_rule: str = DEFAULT_ROLL_RULE) -> date:
    """Unadjusted maturity of a new standard contract: anchor + tenor + 3 months."""
    if tenor not in PILLARS:
        raise ValueError(f"unknown tenor {tenor!r}; expected one of {PILLARS}")
    anchor = _roll_anchor(trade_date, roll_rule)
    return _add_months(anchor, PILLAR_MONTHS[tenor] + QUARTER_MONTHS)


def year_fraction_act365f(d0: date, d1: date) -> float:
    """Curve time: actual days / 365."""
    return (d1 - d0).days / ACT365F_BASIS


def year_fraction_act360(d0: date, d1: date) -> float:
    """Accrual fraction: actual days / 360."""
    return (d1 - d0).days / ACT360_BASIS


@dataclass(frozen=True)
class Schedule:
    """The dated cash-flow skeleton of one standard CDS.

    Period j accrues from accrual_start[j] to accrual_end[j] (act/360,
    accrual_fraction[j]) and pays on payment[j]. accrued_days is the number
    of days of the first period that fall before protection starts; the
    seller rebates them in cash on cash_settle.
    """

    trade_date: date
    maturity: date
    step_in: date
    cash_settle: date
    accrual_start: tuple[date, ...]
    accrual_end: tuple[date, ...]
    payment: tuple[date, ...]
    accrual_fraction: tuple[float, ...]
    accrual_start_date: date
    accrued_days: int
    calendar: str


def cds_schedule(trade_date: date, maturity: date, calendar: str = DEFAULT_CALENDAR) -> Schedule:
    if not is_imm_date(maturity):
        raise ValueError(f"maturity {maturity} is not an IMM 20th")
    if maturity <= trade_date:
        raise ValueError(f"maturity {maturity} is not after trade date {trade_date}")

    step_in = trade_date + timedelta(days=STEP_IN_DAYS)
    cash_settle = add_business_days(trade_date, CASH_SETTLE_BUSINESS_DAYS, calendar)

    # First accrual date: the adjusted IMM 20th on or before the step-in date,
    # stepping back a quarter when the adjustment pushes it past step-in.
    seed = previous_imm(step_in)
    if adjust_following(seed, calendar) > step_in:
        seed = _add_months(seed, -QUARTER_MONTHS)
    if seed >= maturity:
        raise ValueError(f"no coupon period between {seed} and maturity {maturity}")

    unadjusted = imm_dates_between(seed, maturity)
    starts, ends, pays, fracs = [], [], [], []
    last = len(unadjusted) - 2
    for j in range(len(unadjusted) - 1):
        start = adjust_following(unadjusted[j], calendar)
        if j == last:
            end = maturity  # unadjusted, and the period includes this day
            extra_days = 1
        else:
            end = adjust_following(unadjusted[j + 1], calendar)
            extra_days = 0
        starts.append(start)
        ends.append(end)
        pays.append(adjust_following(unadjusted[j + 1], calendar))
        fracs.append(((end - start).days + extra_days) / ACT360_BASIS)

    return Schedule(
        trade_date=trade_date,
        maturity=maturity,
        step_in=step_in,
        cash_settle=cash_settle,
        accrual_start=tuple(starts),
        accrual_end=tuple(ends),
        payment=tuple(pays),
        accrual_fraction=tuple(fracs),
        accrual_start_date=starts[0],
        accrued_days=(step_in - starts[0]).days,
        calendar=calendar,
    )
