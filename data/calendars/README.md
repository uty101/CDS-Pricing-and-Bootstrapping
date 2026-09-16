# data/calendars

`us_uk_holidays.csv`: one column `date`, ISO format, every weekday holiday
2000 to 2060 of the joint US (Settlement) and UK (Settlement) calendars as
QuantLib 1.43 defines them. Generated once by `scripts/make_calendar.py`
(Section 1); `cds/calendars.py` reads it and never imports QuantLib.

Source: QuantLib's `UnitedStates(Settlement)` and `UnitedKingdom(Settlement)`
calendars, joined with `JointCalendar` (holidays of either). Note: for dates
far in the future QuantLib applies the current statutory rules; one-off
holidays (a coronation, a funeral) are only present where QuantLib lists
them. Optional; the default calendar is weekend-only, as in the ISDA model.
