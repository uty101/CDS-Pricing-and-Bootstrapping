# Conventions resolved

Answers to BUILD_PLAN.md Part B. Committed before Section 1 starts. Where an answer differs from the plan's recommendation it says so; otherwise the recommendation stands as written.

1. Accrual start: reading (b), the IMM date on or before the step-in date. Matches QuantLib's `previousTwentieth(protectionStart)` and the ISDA fee leg.
2. Accrued rebate: seller rebates the buyer; days = step-in minus accrual start, act/360. Tested against QuantLib's `accrualRebate` in Section 5.
3. PVs stated at the cash settlement date (T+3) for every field of `PriceResult`. No separate valuation-date PV.
4. Rates snapshot: ICE Swap Rate USD SOFR 1Y to 30Y plus CME Term SOFR for 1M, 3M and 6M, each row labelled with its source. Snapshot date is the date of the Section 2 session. Record page URL and the date read in the file and in `docs/DATA_NOTE.md`.
5. Accrual dates adjusted (Following), last period ends on unadjusted maturity plus 1 day, exactly as `MakeCreditDefaultSwap`.
6. Distressed curve: keep the 3 named curves as specified. If the distressed curve fits with all hazards positive, Section 6 commits `distressed_arb.json` for the arbitrage test, built by raising the 6M pillar in 500 bp steps until f(0) changes sign, and Table 1 shows all 4. The review file records the f(0) rows for both.
7. Theta: change in the side's dirty MTM between the 2 valuation dates plus any coupon cash flow paid or received in (t0, t1].
8. Seasoned trades: the plan's reading. `par_spread_bp` quotes are running-spread contracts with `coupon_bp` equal to the quote, `upfront_pct` quotes carry the inception cash, `quote=None` is the current unwind value.
9. Holiday calendar: committed CSV generated once from QuantLib's joint US/UK settlement calendar, generator script committed, no QuantLib import at runtime.

## Plan correction, applied before Section 1 started

Section 9, acceptance criterion 2 had the sign of spread convexity backwards. The protection buyer's MTM is (s − c)·A(s) and the risky annuity A falls as s rises, so the buyer's MTM is concave in spread: the buyer is short convexity and `pnl_spread_gamma` is negative for a +100 bp parallel move (CS01 shrinks as spreads widen). Checked on a flat-hazard textbook model: second difference of V(s) at s = 100 bp and 500 bp, c = 100 bp, R = 40%, r = 4%, T = 5 is negative in both cases. Criterion 2 now reads: `pnl_spread_gamma` is negative for the protection buyer on a +100 bp parallel move, and the docstring states the reason (annuity shrinks with spread). Committed as `Section 01: plan correction (gamma sign)`.

## Housekeeping

`Project Outline/11_CDS_Pricing_Bootstrap.docx` removed from the repo root; the copy under `docs/` is the one referenced.

## Resolved at the start of Section 2 (questions from review 01)

10. First accrual date (review 01, Not verified item 1): the QuantLib step-back rule stands. It differs from the ISDA C library reading only when the step-in date is a weekend 20th, i.e. only for weekend trade dates, which do not occur in practice. All illustrative trades from Section 5 on use business-day trade dates, and price() raises ValueError on a trade date that is not a business day on the trade's calendar (implemented in Section 5, not now).
11. quarterly_2009 coupon schedules (item 2): not checked against DateGeneration.CDS; accepted, the pre-2015 rule is only used for the maturity comparison.
12. Quote and CDSTrade invariants (item 4): enforced in Section 5 as the plan says.
