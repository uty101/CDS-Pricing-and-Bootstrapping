"""Generate data/calendars/us_uk_holidays.csv from QuantLib, once.

Joint calendar of the US (Settlement) and UK (Settlement) calendars, holidays
listed for 2000 to 2060, weekends excluded. Run with `uv run python
scripts/make_calendar.py`; the CSV is committed and the library reads it
without importing QuantLib.
"""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

import QuantLib as ql

FIRST_YEAR = 2000
LAST_YEAR = 2060
OUT = Path(__file__).resolve().parent.parent / "data" / "calendars" / "us_uk_holidays.csv"


def main() -> None:
    cal = ql.JointCalendar(
        ql.UnitedStates(ql.UnitedStates.Settlement),
        ql.UnitedKingdom(ql.UnitedKingdom.Settlement),
    )
    holidays = ql.Calendar.holidayList(
        cal, ql.Date(1, 1, FIRST_YEAR), ql.Date(31, 12, LAST_YEAR), False
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["date"])
        for d in holidays:
            w.writerow([date(d.year(), d.month(), d.dayOfMonth()).isoformat()])
    print(f"wrote {len(holidays)} holidays to {OUT}")


if __name__ == "__main__":
    main()
