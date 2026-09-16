"""Section 1: schedule against QuantLib as an independent oracle.

Every date the library produces is compared with a date QuantLib produced
from the same inputs, never with a date this code produced earlier. The one
tolerance, DAY_COUNT_ABS_TOL, is imported from tests/conftest.py: accrual
fractions are ratios of integers, so 1e-12 is float noise.
"""

from __future__ import annotations

import csv
from datetime import date, timedelta

import pytest
import QuantLib as ql

from cds import calendars
from cds.conventions import PILLARS
from conftest import DAY_COUNT_ABS_TOL
from cds.schedule import (
    cds_schedule,
    imm_dates_between,
    is_imm_date,
    next_imm,
    previous_imm,
    standard_maturity,
    year_fraction_act360,
    year_fraction_act365f,
)

# The 16 trade dates from BUILD_PLAN.md Section 1: both sides of 20 Mar and
# 20 Sep, a year end, two leap days, 20ths that fall on a Saturday and a
# Sunday, the 19th/20th of a non-roll IMM month, and today.
TRADE_DATES = [
    date(2015, 12, 18),
    date(2016, 3, 19),
    date(2016, 3, 20),
    date(2016, 3, 21),
    date(2016, 9, 19),
    date(2016, 9, 20),
    date(2020, 2, 29),
    date(2020, 12, 20),
    date(2020, 12, 31),
    date(2021, 1, 4),
    date(2024, 2, 29),
    date(2024, 6, 19),
    date(2024, 6, 20),
    date(2025, 9, 20),
    date(2026, 6, 19),
    date(2026, 9, 16),
]

RULES = {
    "semiannual_2015": ql.DateGeneration.CDS2015,
    "quarterly_2009": ql.DateGeneration.CDS,
}


def to_ql(d: date) -> ql.Date:
    return ql.Date(d.day, d.month, d.year)


def from_ql(d: ql.Date) -> date:
    return date(d.year(), d.month(), d.dayOfMonth())


def ql_calendar(name: str) -> ql.Calendar:
    if name == "weekends":
        return ql.WeekendsOnly()
    return ql.JointCalendar(
        ql.UnitedStates(ql.UnitedStates.Settlement),
        ql.UnitedKingdom(ql.UnitedKingdom.Settlement),
    )


def ql_schedule(trade: date, maturity: date, calendar: str) -> ql.Schedule:
    step_in = to_ql(trade + timedelta(days=1))
    return ql.Schedule(
        step_in,
        to_ql(maturity),
        ql.Period("3M"),
        ql_calendar(calendar),
        ql.Following,
        ql.Unadjusted,
        ql.DateGeneration.CDS2015,
        False,
    )


# --- criteria 1 and 2: standard maturities under both roll rules -------------


@pytest.mark.parametrize("roll_rule", list(RULES))
@pytest.mark.parametrize("trade", TRADE_DATES, ids=str)
def test_standard_maturity_matches_quantlib(trade: date, roll_rule: str) -> None:
    for tenor in PILLARS:
        ours = standard_maturity(trade, tenor, roll_rule)
        oracle = from_ql(ql.cdsMaturity(to_ql(trade), ql.Period(tenor), RULES[roll_rule]))
        assert ours == oracle, f"{trade} {tenor} {roll_rule}: {ours} != {oracle}"


def test_maturity_check_count() -> None:
    # 16 dates x 8 tenors x 2 rules = 256 oracle comparisons above.
    assert len(TRADE_DATES) * len(PILLARS) * len(RULES) == 256


# --- criterion 3: coupon dates and settlement dates -------------------------


@pytest.mark.parametrize("calendar", ["weekends", "us_uk"])
@pytest.mark.parametrize("trade", TRADE_DATES, ids=str)
def test_coupon_dates_match_quantlib_5y(trade: date, calendar: str) -> None:
    maturity = standard_maturity(trade, "5Y")
    ours = cds_schedule(trade, maturity, calendar)
    oracle = [from_ql(d) for d in ql_schedule(trade, maturity, calendar)]
    assert list(ours.accrual_start) == oracle[:-1]
    assert list(ours.accrual_end[:-1]) == oracle[1:-1]
    assert ours.accrual_end[-1] == maturity == oracle[-1]
    adj = [calendars.adjust_following(d, calendar) for d in oracle[1:]]
    assert list(ours.payment) == adj
    assert ours.step_in == trade + timedelta(days=1)
    settle = ql_calendar(calendar).advance(to_ql(trade), ql.Period(3, ql.Days))
    assert ours.cash_settle == from_ql(settle)
    assert ours.accrued_days == (ours.step_in - oracle[0]).days
    assert ours.accrued_days >= 0


@pytest.mark.parametrize("tenor", ["6M", "10Y"])
@pytest.mark.parametrize(
    "trade",
    [date(2016, 3, 19), date(2020, 12, 20), date(2024, 6, 19), date(2026, 9, 16)],
    ids=str,
)
def test_coupon_dates_match_quantlib_other_tenors(trade: date, tenor: str) -> None:
    maturity = standard_maturity(trade, tenor)
    ours = cds_schedule(trade, maturity)
    oracle = [from_ql(d) for d in ql_schedule(trade, maturity, "weekends")]
    assert list(ours.accrual_start) + [maturity] == oracle


# --- criterion 4: accrual fractions -----------------------------------------


@pytest.mark.parametrize("calendar", ["weekends", "us_uk"])
@pytest.mark.parametrize("trade", TRADE_DATES, ids=str)
def test_accrual_fractions_match_quantlib(trade: date, calendar: str) -> None:
    maturity = standard_maturity(trade, "5Y")
    ours = cds_schedule(trade, maturity, calendar)
    dates = list(ql_schedule(trade, maturity, calendar))
    act360 = ql.Actual360()
    act360_last = ql.Actual360(True)
    n = len(dates) - 1
    for j in range(n):
        dc = act360_last if j == n - 1 else act360
        oracle = dc.yearFraction(dates[j], dates[j + 1])
        assert abs(ours.accrual_fraction[j] - oracle) < DAY_COUNT_ABS_TOL, (trade, j)


# --- criterion 5: the two day counts ----------------------------------------


def test_day_counts_on_a_leap_year() -> None:
    d0, d1 = date(2024, 1, 1), date(2025, 1, 1)
    assert year_fraction_act365f(d0, d1) == 366 / 365
    assert year_fraction_act360(d0, d1) == 366 / 360
    assert year_fraction_act365f(d0, d1) != year_fraction_act360(d0, d1)


# --- criterion 6: rejections ------------------------------------------------


def test_rejects_unknown_tenor_and_non_imm_maturity() -> None:
    with pytest.raises(ValueError):
        standard_maturity(date(2026, 9, 16), "8Y")
    with pytest.raises(ValueError):
        standard_maturity(date(2026, 9, 16), "5Y", roll_rule="monthly")
    with pytest.raises(ValueError):
        cds_schedule(date(2026, 9, 16), date(2031, 6, 21))
    with pytest.raises(ValueError):
        cds_schedule(date(2026, 9, 16), date(2026, 6, 20))
    with pytest.raises(ValueError):
        cds_schedule(date(2026, 9, 16), date(2031, 6, 20), calendar="target")


# --- IMM helpers, checked against the definition, not against each other ----


def test_imm_helpers() -> None:
    assert previous_imm(date(2026, 9, 20)) == date(2026, 9, 20)
    assert previous_imm(date(2026, 9, 19)) == date(2026, 6, 20)
    assert previous_imm(date(2026, 1, 5)) == date(2025, 12, 20)
    assert next_imm(date(2026, 9, 20)) == date(2026, 12, 20)
    assert next_imm(date(2026, 9, 19)) == date(2026, 9, 20)
    assert imm_dates_between(date(2026, 1, 1), date(2026, 12, 31)) == [
        date(2026, 3, 20),
        date(2026, 6, 20),
        date(2026, 9, 20),
        date(2026, 12, 20),
    ]
    assert is_imm_date(date(2026, 12, 20)) and not is_imm_date(date(2026, 11, 20))


# --- the committed holiday file agrees with the QuantLib calendar it came from


def test_holiday_file_matches_quantlib_joint_calendar() -> None:
    with calendars.HOLIDAY_FILE.open(newline="", encoding="utf-8") as fh:
        listed = [date.fromisoformat(r["date"]) for r in csv.DictReader(fh)]
    cal = ql_calendar("us_uk")
    oracle = [
        from_ql(d)
        for d in ql.Calendar.holidayList(cal, ql.Date(1, 1, 2000), ql.Date(31, 12, 2060), False)
    ]
    assert listed == oracle
    # And every weekday of one year is classified the same way.
    d = date(2026, 1, 1)
    while d.year == 2026:
        assert calendars.is_business_day(d, "us_uk") == cal.isBusinessDay(to_ql(d)), d
        d += timedelta(days=1)


def test_weekend_calendar_ignores_holidays() -> None:
    assert calendars.is_business_day(date(2026, 7, 3), "weekends")  # US holiday, a Friday
    assert not calendars.is_business_day(date(2026, 7, 3), "us_uk")
    assert calendars.adjust_following(date(2026, 6, 20), "weekends") == date(2026, 6, 22)
    assert calendars.add_business_days(date(2026, 9, 16), 3) == date(2026, 9, 21)
