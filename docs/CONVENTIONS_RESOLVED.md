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

## Resolved at the start of Section 3 (questions from review 02)

13. OIS spot date (review 02, rule 2): the discount curve is built with spot = as_of (T+0), not the market's T+2. Accepted; the difference on a 5Y CDS upfront is under 0.1 bp. Section 7 lists this as a known source of sub-0.1 bp difference before hunting elsewhere.
14. Rates sources (review 02, Against the plan 1 and 2): BlueGamma 1Y to 30Y and CME Term SOFR 1M to 6M, valuation date 15 Sep 2026, accepted as the project's single snapshot. Not verified items 1 and 2 (fixed-leg convention of the source, 0.5 bp rounding) accepted as stated.

## Resolved at the start of Section 4 (questions from review 03)

15. Hazard continuity (review 03, Against the plan 1): the plan's word "right-continuous" was a slip. The hazard is flat on (t_{i-1}, t_i], so hazard(t_i) = λ_i and hazard(t_i + ε) = λ_{i+1}, continuous from the left. Code and tests stand; the wording of Section 3 criterion 5 in BUILD_PLAN.md is edited to match.
16. Survival curve calendar shift (Against the plan 2): pillars on or before the new as_of are dropped, hazards between the same dates unchanged. Accepted.
17. Discount curve tenor shift (Not verified 2): node dates move by days, no re-bootstrap. Section 8 theta-rolldown uses this path and says so in its docstring.
18. Pillar dates on the snapshot date: standard_pillar_dates(15 Sep 2026) puts the 6M pillar on 20 Dec 2026, 96 days out. Section 6's data note states this next to each curve file.

## Resolved at the start of Section 5 (questions from review 04)

19. Leg integration limits (review 04, Against the plan 1 to 3): QuantLib IsdaCdsEngine's end-of-day reading stands. Protection integrates from t(max(step_in, as_of + 1) − 1 day); coupon on survival uses Q(pay − 1 day); accrual on default runs from max(accrual_start, effective start) − 1 day to pay − 1 day with origin t(accrual_start − 1 day) − 0.5/365 under the half-day bias. BUILD_PLAN.md Section 4 rules are read this way; edit the "(t_stepin, T]" phrase in Section 4 to say so.
20. Credit triangle (Against the plan 6): stated with act/365F daily fractions; the act/360 version equals λ(1 − R)·360/365, asserted exactly.
21. Par spread definition for Section 7 (Against the plan 9): par spread is PV_prot / (A_coupon + A_accrual) at the valuation date. Section 7 compares leg NPVs and fairUpfront against QuantLib, never fairSpread, which is the clean-value spread.
22. Coupon inclusion on seasoned trades (Not verified 2): a coupon paying after as_of is included. QuantLib excludes one paying on as_of + 1 by default; Section 8's oracle tests set QuantLib's includeReferenceDateEvents / includeSettlementDateFlows to match, or avoid valuation dates the day before a payment, and state which.
23. LegValues carries pv_protection as a fourth field. Accepted.

## Resolved at the start of Section 6 (questions from review 05)

24. Par spread definition, reversing item 21 (review 05, Against the plan 1): `par_spread_bp` is the clean-value spread PV_prot / (A − accrued_fraction / D), the spread at which `clean_upfront_pct` is zero. It is QuantLib's `fairSpread` and what the ISDA C bootstrap fits with `isPriceClean = TRUE`. The former dirty quantity PV_prot / A is kept as `dirty_par_spread_bp` on `Valuation`, not on `PriceResult`. The conversions calibrate the flat hazard to the clean spread. Section 6's objective per pillar is f(λ_i) = D·(PV_prot − s_i·A) + s_i·accrued_fraction = 0. Section 7 compares par spreads against `fairSpread` and the bootstrap against `ql.SpreadCdsHelper`. Section 6 criterion 2 expects every λ_i within 3% of 1.67% on the flat 100 bp curve, which the clean definition gives (1.680 to 1.681%) and the dirty one does not.
25. Upfront quotes are clean (Against the plan 2): inception_cash = value/100 − c·accrued_days₀/360. Accepted.
26. `upfront_to_quoted_spread` is one Brent on the hazard (Against the plan 3). Accepted.
27. `price(state, trade, *, calendar, engine, half_day_bias)` keyword arguments (Against the plan 4); no calendar field on `CDSTrade`. Accepted.
28. `price` raises when `trade.recovery` differs from `state.recovery.R(0)` (Against the plan 5). Accepted; Section 8's rec01 replaces both.
29. Seasoned `accrued_days` counts to as_of + 1 (Against the plan 6). Accepted; Section 8 computes JTD's accrued to the valuation date from the schedule.

## Resolved at the start of Section 7 (questions from review 06)

30. HY_steep levels (review 06, Against the plan 1): kept as committed (150 … 500, 560, 600). Section 6 criterion 3 is rewritten to "every λ_i > 0; HY strictly increasing through 5Y; the 7Y and 10Y forward hazards sit below the 5Y one and the test pins them". docs/DATA_NOTE.md states next to HY_steep that the long-end dip is what a flattening spread curve implies, not a fitting artefact.
31. Fallbacks apply only when the sequential fit raises; method records what ran (Against the plan 2). Accepted.
32. Table 1 shows distressed_arb under the upfront fallback only (Against the plan 3). Accepted.
33. BootstrapResult fields, market_state, pillar_trade, the legs.py rename, scripts/make_curves.py, chart drawn from the exact step, report generators taking BootstrapResults, curve files carrying as_of, full-precision upfronts (Against the plan 4 to 12). All accepted.
34. Committed outputs are rounded to 10 decimal places when written (cds/report.py write_table and the chart CSV). Tests that check an output is current compare it to a regeneration numerically, with absolute tolerance 1e-9 on every numeric column and exact match on text columns, never as raw file text. Reason: byte-identical floats are not portable across numpy and pandas builds; the two "is current" tests fail on a machine with numpy 2.4.4.

## Resolved at the start of Section 8 (questions from review 07)

35. Section 7 criterion 2 (review 07, Against the plan 1 and 3): restated as the matched-node comparison. Our sequential fit with the survival curve's nodes on QuantLib's dates (adjusted maturity + 1 day) against QuantLib's node hazards, |Δλ_i| ≤ 0.5 bp of hazard on every pillar of every curve; the on-our-grid rows (`trade = "bootstrap"`) stay in Table 2 as information, and Table 2 is kept exactly as committed in Section 7 (16 hazard rows per curve, the two distressed on-our-grid rows reading `False` against the 0.5 bp bar). BUILD_PLAN.md Section 7 criterion 2 is rewritten to say so.
36. `SpreadCdsHelper(settlementDays = 1)` (Against the plan 2): accepted. In QuantLib 1.43 the helper's argument is the protection start (evaluation date + that many calendar days, our step-in); the swap it builds keeps `cashSettlementDays = 3`, our T+3.
37. Against the plan 4 to 8 accepted as stated: the `pv_protection` (1 bp of notional) and `risky_annuity` (0.01 per unit spread, `QL_ANNUITY_ABS_TOL`) tolerances; `cs01_usd` as the only CS01 metric in Table 2 with the bp-of-notional numbers in the review; Table 5 at 100 bp on IG and 500 bp on HY and distressed; `OUTPUT_ABS_TOL` and `assert_output_current` in `tests/conftest.py` with the Markdown files compared as text; `rounded()` writing `0.0` for a `-0.0`.
38. `assert_output_current` compares each float within max(`OUTPUT_ABS_TOL`, `OUTPUT_ABS_TOL` × |committed value|), i.e. 1e-9 absolute or 1e-9 relative, whichever is larger, so a column in currency (a CS01 or an MTM on $10m, written to 10 decimal places) is held to its last printed digits rather than to an absolute 1e-9 it cannot carry. Amends item 34; text columns are still compared exactly.

## Resolved at the start of Section 9 (questions from review 08)

39. Items 35 to 38 stand as committed; the bracketed note above them (saying they were written from the prompt's summary of the Section 07 approval) is removed.
40. rec01 and IR01 hold the conventional spreads fixed and re-bootstrap, the same reading as CS01, on every curve including upfront-quoted ones (review 08, Against the plan 2).
41. Section 8 criterion 5: IR01 on the IG 5Y par trade under $200; on the distressed 5Y upfront trade over $300 in absolute value; on the distressed 10Y over $500. `IR01_DISTRESSED_MIN_USD = 300` and a new `IR01_DISTRESSED_10Y_MIN_USD = 500` (Against the plan 3).
42. The off-market trade is s_par + 200 bp on IG (290 bp) for criterion 2 and Chart 2; s_par − 200 bp on HY (300 bp) is the second test case. Chart 2's CSV keeps the 6 columns (Against the plan 4 and 5).
43. Chart 2 panel (b) stays on one axis; each legend label ends with its slope in $ per recovery point, computed from the CSV (Against the plan 6).
44. JTD uses the trade's unwind value, i.e. `price()` with `quote = None`, for every trade; the inception cash of an upfront-quoted trade is sunk (Against the plan 8).
45. `OUTPUT_ABS_TOL = 1e-6`: `assert_output_current` compares within max(1e-6, 1e-6 × |committed|). Reason: difference columns (Table 2 diff, Table 3 cs01_2y) are differences of $10m-scale values and carry a 1e-9 noise floor across numpy builds regardless of their own size; nothing in the outputs is meaningful past 1e-6. Amends item 38.

Items 39 to 45 are recorded here; the code changes for 43, 44 and 45 are applied in the Section 09 pre-step.
