"""Every convention the library uses, in one place.

Nothing outside this module hard codes a day count, a roll rule, a coupon, a
recovery or a notional. Sources for each rule are in BUILD_PLAN.md Part A and
the resolutions in docs/CONVENTIONS_RESOLVED.md.
"""

# Accrual on the premium leg is act/360 (SNAC).
ACCRUAL_DAY_COUNT = "act/360"
ACT360_BASIS = 360

# Time in the discount and survival curves is act/365 fixed (ISDA model).
CURVE_DAY_COUNT = "act/365f"
ACT365F_BASIS = 365

# Coupon dates fall on the 20th of March, June, September and December.
IMM_DAY = 20
IMM_MONTHS = (3, 6, 9, 12)

# Since 20 Dec 2015 new contracts roll semi-annually, on 20 Mar and 20 Sep.
ROLL_MONTHS_2015 = (3, 9)

# The roll rule for standard maturities: "semiannual_2015" (current) or
# "quarterly_2009" (the 2009 to 2015 rule, kept for comparison).
DEFAULT_ROLL_RULE = "semiannual_2015"
ROLL_RULES = ("semiannual_2015", "quarterly_2009")

# Protection starts the calendar day after the trade date.
STEP_IN_DAYS = 1

# Upfront and accrued rebate settle three business days after the trade.
CASH_SETTLE_BUSINESS_DAYS = 3

# Payment dates roll Following; the default calendar is weekend-only, as in
# the ISDA model. "us_uk" is the optional joint US/UK holiday calendar.
DEFAULT_CALENDAR = "weekends"
CALENDARS = ("weekends", "us_uk")

# Standard fixed coupons since the Big Bang.
STANDARD_COUPONS_BP = (100.0, 500.0)

# Recovery assumptions by market convention (spec section 4).
RECOVERY_SENIOR = 0.40
RECOVERY_SUBORDINATED = 0.20
RECOVERY_HY_INDEX = 0.25

# Notional of the reference trade.
DEFAULT_NOTIONAL = 10_000_000.0

# Survival curve pillars, and the months each tenor adds to the roll anchor.
PILLARS = ("6M", "1Y", "2Y", "3Y", "4Y", "5Y", "7Y", "10Y")
PILLAR_MONTHS = {"6M": 6, "1Y": 12, "2Y": 24, "3Y": 36, "4Y": 48, "5Y": 60, "7Y": 84, "10Y": 120}
