"""Business-day calendars: weekend-only (the default) and joint US/UK.

The US/UK holiday list is read from data/calendars/us_uk_holidays.csv, which
scripts/make_calendar.py generated once from QuantLib. The library never
imports QuantLib.
"""

from __future__ import annotations

import csv
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

from cds.conventions import CALENDARS, DEFAULT_CALENDAR

HOLIDAY_FILE = Path(__file__).resolve().parent.parent / "data" / "calendars" / "us_uk_holidays.csv"

SATURDAY = 5
SUNDAY = 6


@lru_cache(maxsize=None)
def _us_uk_holidays() -> frozenset[date]:
    with HOLIDAY_FILE.open(newline="", encoding="utf-8") as fh:
        rows = csv.DictReader(fh)
        return frozenset(date.fromisoformat(row["date"]) for row in rows)


def _check(calendar: str) -> None:
    if calendar not in CALENDARS:
        raise ValueError(f"unknown calendar {calendar!r}; expected one of {CALENDARS}")


def is_business_day(d: date, calendar: str = DEFAULT_CALENDAR) -> bool:
    """True unless d is a Saturday, a Sunday, or (for "us_uk") a listed holiday."""
    _check(calendar)
    if d.weekday() in (SATURDAY, SUNDAY):
        return False
    if calendar == "us_uk" and d in _us_uk_holidays():
        return False
    return True


def adjust_following(d: date, calendar: str = DEFAULT_CALENDAR) -> date:
    """The first business day on or after d (the Following convention)."""
    while not is_business_day(d, calendar):
        d += timedelta(days=1)
    return d


def add_business_days(d: date, n: int, calendar: str = DEFAULT_CALENDAR) -> date:
    """d advanced by n business days; n = 0 returns d unchanged even on a weekend."""
    if n < 0:
        raise ValueError("n must be non-negative")
    while n > 0:
        d += timedelta(days=1)
        if is_business_day(d, calendar):
            n -= 1
    return d
