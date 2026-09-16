"""CDS pricing and hazard rate bootstrapping.

Modules, in the order BUILD_PLAN.md builds them. None exist yet.

    conventions   every day count, roll rule, coupon and recovery default (Section 1)
    schedule      IMM dates, standard maturities, accrual fractions, payment dates (Section 1)
    calendars     weekend-only and US/UK holiday calendars (Section 1)
    types         the public frozen dataclasses and curve protocols (Section 1)
    curves        DiscountCurve, SurvivalCurve, RecoveryCurve (Sections 2, 3)
    legs          premium and protection legs, isda and grid engines (Section 4)
    pricer        price(), par spread, upfront, flat-hazard conversion (Section 5)
    textbook      continuous-compounding model, comparison only (Section 5)
    bootstrap     sequential Brent per pillar, arbitrage detection (Section 6)
    report        table and chart generators (Sections 6 to 9)
    validation    QuantLib IsdaCdsEngine comparison (Section 7)
    risk          CS01, rec01, IR01, JTD, theta (Section 8)
    scenarios     vectorised scenario grid (Section 9)
    explain       P&L explain (Section 9)
"""
