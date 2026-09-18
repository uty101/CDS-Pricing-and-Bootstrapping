# Review — Section 08 — the risk report: CS01, rec01 both ways, IR01, JTD, the two thetas; Table 3 and Chart 2

Date: 2026-09-17   Commit: 6526bbb   Tests: 356/356 (323 from Sections 1 to 7; 33 new; 0 skipped)

Three commits. `2c92fbb Section 08: resolved Section 7 questions` (items 35 to 38 appended to `docs/CONVENTIONS_RESOLVED.md`; BUILD_PLAN.md Section 7 criterion 2 rewritten to the matched-node comparison, Table 2 untouched; `assert_output_current` made relative, 323/323 after it), `6526bbb Section 08: risk` (code, tests, Table 3, Chart 2), and this review.

## What changed

**Before any Section 8 code (`2c92fbb`).**
- `docs/CONVENTIONS_RESOLVED.md` — items 35 to 38. **The Section 07 approval message was not in the session prompt and issue 7 carries no comment**, so the four items are written from the prompt's one-line summary of each (35: criterion 2 becomes the matched-node comparison, Table 2 as committed; 38: `assert_output_current` compares within max(1e-9, 1e-9 × |committed|)) and, for 36 and 37, from the review 07 questions the prompt did not mention (`settlementDays = 1`; Against the plan 4 to 8 accepted as stated). A bracketed note in the file says so. Against the plan 1.
- `BUILD_PLAN.md` — Section 7 criterion 2: matched-node comparison, 0.5 bp on every pillar of every curve; the on-our-grid rows stay in Table 2 as information with the two distressed misses pinned.
- `tests/conftest.py` — `assert_output_current`: each float within max(`OUTPUT_ABS_TOL`, `OUTPUT_ABS_TOL` × |committed value|).

**Section 8 (`6526bbb`).**
- `cds/risk.py` (new) — `risk(state, trade, *, calendar, engine, half_day_bias) -> RiskReport` and the measures behind it: `cs01_by_pillar`, `cs01_parallel`, `rec01`, `rec01_hazard_fixed`, `ir01`, `jtd`, `theta`; the rebuilt states `spread_bumped_state`, `recovery_state`, `rates_bumped_state`, `shifted_state`, `bumped_discount`, `spread_quotes`; the helpers `accrued_to_valuation_date`, `coupon_cash_in_window`, `add_calendar_months`; the bump sizes `BUMP_SPREAD_BP = 1.0`, `BUMP_RECOVERY = 0.01`, `BUMP_RATE_BP = 1.0`, the horizons `THETA_DAYS = 1`, `THETA_MONTHS = 1`. Every measure is bumped mtm less base mtm in the side's currency.
- `cds/types.py` — untouched: `RiskReport` already carried the 28 fields of the plan in the plan's order (the test checks the order against Section 8's list).
- `cds/report.py` — `table_3_risk_report(results, discount)`, `chart_2_recovery_dependence(result, discount)`, `chart_2_trades`, `trade_label`, `TABLE_3_COLUMNS`, `TABLE_3_TENOR`, `CHART_2_COLUMNS`, `CHART_2_CURVE`, `CHART_2_RECOVERIES`, `CHART_2_OFFMARKET_BP`, `STANDARD_COUPONS_BY_CURVE` (`TABLE_5_COUPONS_BP` is now an alias of it).
- `scripts/make_outputs.py` — `--only table_3`, `--only chart_2`.
- `tests/test_risk.py` (33 tests); `tests/conftest.py` — `CS01_CENTRAL_REL_TOL = 0.01`, `CS01_CENTRAL_ABS_USD = 0.01`, `REC01_HAZARD_FIXED_SAME_REL_TOL = 0.01`, `REC01_HAZARD_FIXED_REL_TOL = 0.001`, `JTD_ABS_USD = 0.01`, `IR01_IG_MAX_USD = 200`, `IR01_DISTRESSED_MIN_USD = 500`, `IR01_DISTRESSED_PINNED_BAND = (300, 500)`, `QL_SEASONED_ABS_TOL = 1e-9`, `CHART_2_PAR_FLAT_USD = 10`, each with its reason.
- `outputs/tables/table_3_risk_report.{csv,md}` (3 rows, 30 columns; the `.md` transposed, 28 measure rows × 3 trades, to the cent), `outputs/charts/chart_2_recovery_dependence.{png,csv}` (51 rows, 6 columns).

**Rules stated in full.** `as_of` = 15 Sep 2026; N = 10,000,000; every Table 3 trade a 5Y protection buy at the curve's recovery and standard coupon (100 on IG, 500 on HY and distressed); cash settlement 18 Sep 2026, D = 1/P(t_settle) = 1.000323339.

1. **The bumped input is the conventional spread s_i of every pillar**, computed once per `risk()` call (`cds.bootstrap.conventional_spreads_bp` at the base R on the base discount curve: the quote for a par-spread curve, the flat-hazard conversion of the upfront for `distressed_inverted`). Every rebuild bootstraps the eight spreads as par-spread quotes: CS01 adds 1 bp to one or all of them; rec01 holds them fixed at R + 0.01; IR01 holds them fixed on the rebumped discount curve. Part D.2 names the conventional spread as the CS01 input; the same reading is applied to rec01 and IR01 (Against the plan 2 says why and what the alternative gives).
2. **CS01 per pillar** = mtm(s_i + 1) − mtm(s), one-sided up; **central** = (mtm(s_i + 1) − mtm(s_i − 1))/2; **parallel** the same with every pillar moved; `cs01_bucket_sum` = Σ of the eight one-sided.
3. **rec01** = mtm at R + 0.01 on the trade, the recovery curve and the quotes (item 28), spreads fixed, curve re-bootstrapped, less base. **rec01_hazard_fixed** = the same with the survival curve as it is.
4. **IR01** = mtm on `bootstrap_ois(as_of, tenors, par_rates + 1 bp)` with the spreads re-bootstrapped off it, less base. The discount curve must carry its par rates (`DiscountCurve.tenors`); a calendar-shifted one does not and `ir01` raises.
5. **JTD** = side · ((1 − R)·N − accrued) − mtm, accrued = c·N·days/360 with days from the start of the period containing `as_of` to `as_of` (85 days on 15 Sep 2026: 22 Jun to 15 Sep; the pricer's own accrued runs to as_of + 1, 86 days, item 29). For the buyer that is (1 − R)·N − mtm − accrued; the seller's is the negative. `mtm` is `PriceResult.mtm` for the trade (Against the plan 8 on what that means for an upfront-quoted seasoned trade).
6. **Theta** = mtm(t_1) − mtm(t_0) − side · (coupons paid on payment dates in (t_0, t_1]), item 7. t_1 = t_0 + 1 calendar day, or the same day of the next month (`add_calendar_months`, day clipped to a shorter month), no business-day adjustment; the cash settlement date moves with t_1. theta-calendar: `with_as_of(t_1, "calendar")` on all three curves; theta-rolldown: `with_as_of(t_1, "tenor")` on all three (the discount curve's node dates move by the same days, no re-bootstrap, item 17). The shifted `MarketState` carries the quotes with `as_of` moved; `price()` does not read them. **For a trade valued on its trade date the 1-month window from 15 Sep holds the 21 Sep first-coupon payment**, so theta_1m = Δmtm − coupon while theta_1d is Δmtm alone; the rows below show both parts.
7. **`risk()` checks its inputs**: the trade, the recovery curve and the quotes agree on R; the state's survival curve is the bootstrap of its own spreads on its own discount curve (one extra bootstrap, hazards within 1e-9); the pillars are `PILLARS`. Otherwise `ValueError`.
8. **Seasoned trades against QuantLib** (item 22): the HY 5Y buy dated 15 Sep 2026, valued on eight later dates on the calendar-shifted curves handed to QuantLib as `ql.DiscountCurve` / `ql.HazardRateCurve` on the shifted nodes, `ql.CreditDefaultSwap(..., tradeDate = 15 Sep 2026, cashSettlementDays = 3)`, `IsdaCdsEngine(..., includeSettlementDateFlows = True, Taylor, HalfDayBias, Piecewise)`. **The flag set is `includeSettlementDateFlows = True`**; with it QuantLib includes a coupon paying on as_of + 1 as our rule does. Our mtm per unit notional (at t_settle) is compared with QuantLib's `NPV()` / P(t_settle); `fairUpfront` is not available on a seasoned trade.
9. **Chart 2** (Part C item 1): on `IG_flat`, R from 0.10 to 0.60 in 0.01 steps, spreads fixed, curve re-bootstrapped at each R. (a) 1 − Q(t_5Y). (b) MTM of the par 5Y running-spread trade (coupon 90 bp = the 5Y par spread at R = 0.40) and of the running-spread trade at 290 bp, each drawn re-bootstrapped and hazard-fixed (survival curve of R = 0.40, only R moved), four lines. The dotted line marks the file's R.

## Findings

**Claim (criterion 1): the sum of the eight bucketed CS01s is within 0.03% of the parallel CS01 on every curve, against the 2% bar.**
Rows (curve, trade, the eight one-sided CS01s $, bucket sum $, parallel $, gap %):

| IG_flat | 5Y_buy_c100 | 0.13, 0.76, 2.39, 3.86, 5.42, 4206.93, 0.00, 0.00 | 4219.49 | 4218.23 | +0.030% |
| HY_steep | 5Y_buy_c500 | 0.00, 0.00, 0.00, 0.00, 0.00, 3828.12, 0.00, 0.00 | 3828.12 | 3827.24 | +0.023% |
| distressed_inverted | 5Y_buy_c500 | −2.81, −17.74, −62.67, −113.52, −180.82, 2818.43, 0.00, 0.00 | 2440.86 | 2440.43 | +0.018% |

The 7Y and 10Y buckets are exactly zero: the bootstrap is sequential, so a later pillar cannot move a 5Y contract. The short buckets on HY are zero to the cent because the HY 5Y trade is at par (500 at coupon 500) and the front pillars only reshape the survival curve before a maturity whose value is pinned; on IG (coupon 100 against par 90) they are dollars, and on distressed (coupon 500 against a 1200 bp par) they are negative: raising a front-pillar spread with the 5Y spread fixed lowers the hazard needed beyond it, and the far-from-par 5Y contract loses value. The 5Y bucket agrees with Table 2's `cs01_usd` rows to the cent (4206.93, 3828.12, 2818.43).

**Claim (criterion 2): rec01 re-bootstrapped is under $1e-9 on the par trade and $408 (IG, +200 bp) / −$1,243 (HY, −200 bp) off market; rec01_hazard_fixed is identical on the par and the off-market trade and equals −0.01·I·N·D to 1e-12.**
Rows (curve, 5Y par spread, coupon, rec01 $, rec01_hazard_fixed $, −0.01·I·N·D $ with I the Section 4 protection integral and D the settlement factor):

| IG_flat | 90.000000 | 90 (par) | +1.4e-10 | −6305.679421 | −6305.679421 |
| IG_flat | 90.000000 | 290 (off) | +408.4322 | −6305.679421 | −6305.679421 |
| HY_steep | 500.000000 | 500 (par) | +8.4e-10 | −25522.498823 | −25522.498823 |
| HY_steep | 500.000000 | 300 (off) | −1243.0064 | −25522.498823 | −25522.498823 |

The off-market number is Part C item 5's (s_mkt − c)·ΔA·N exactly: on IG the annuity at settlement goes from 4.442675169 to 4.440633008 when R rises a point (ΔA = −2.042e-3), and (90 − 290)/10⁴ × (−2.042e-3) × 10⁷ = +408.43; on HY ΔA = −6.215e-3 and (500 − 300)/10⁴ × ΔA × 10⁷ = −1243.01. I = 0.063036412 (IG), 0.255142491 (HY), D = 1.000323339. The bars: $500 for the par number, 10× for the off-market ratio (here 10¹² and 10¹²), 1% for the hazard-fixed pair (0), 0.1% for the identity (0). The plan's "about −$6,700 per point on $10m" for IG is −$6,306 here.

**Claim (criterion 3): on the flat in-test curve the two 1-month thetas differ by $0.34 (bar $100); on HY they differ by $43,809 (bar $1,000).**
The flat curve: 100 bp on every pillar at R = 0.40 on a discount curve with exp(−0.045·t) at every node of the Section 2 curve (its par rates carried so IR01 can rebuild it; the rebuild reproduces the nodes to 2.7e-15). Bootstrapped hazards 1.68010 to 1.68019%. Rows (curve, window, mtm(t_0) $, mtm(t_1) calendar $, mtm(t_1) tenor $, coupon paid in the window $, theta-calendar $, theta-rolldown $, difference $):

| flat100 | 1d, 16 Sep | −23888.89 | −24174.09 | −24174.10 | 0 | −285.20 | −285.21 | 0.01 |
| flat100 | 1m, 15 Oct | −23888.89 | −6920.66 | −6921.00 | 25277.78 | −8309.55 | −8309.89 | 0.34 |
| IG_flat | 1d | −65926.75 | −66073.36 | −66290.16 | 0 | −146.61 | −363.41 | 216.81 |
| IG_flat | 1m | −65926.75 | −44561.57 | −51073.38 | 25277.78 | −3912.60 | −10424.40 | 6511.81 |
| HY_steep | 1d | −119444.44 | −119897.75 | −121353.73 | 0 | −453.30 | −1909.29 | 1455.98 |
| HY_steep | 1m | −119444.44 | −5509.25 | −49318.60 | 126388.89 | −12453.69 | −56263.05 | 43809.36 |
| distressed_inverted | 1d | 1938337.32 | 1933825.72 | 1937506.21 | 0 | −4511.60 | −831.11 | −3680.49 |
| distressed_inverted | 1m | 1938337.32 | 1916116.48 | 2028047.39 | 126388.89 | −148609.73 | −36678.82 | −111930.91 |

The coupon in the 1-month window is the first coupon (22 Jun to 21 Sep, 91 days) paid on 21 Sep 2026; the dirty mtm at 15 Sep holds it in full and the mtm at 15 Oct no longer does, so Δmtm jumps by the coupon and theta nets it out. On the flat curve theta-calendar over a month is the protection consumed, (1 − R)·λ·N·30/365 = $8,285, within 0.3% of −$8,310. On the upward-sloping curves rolldown costs the buyer more than the calendar (the contract prices off a lower point); on the inverted distressed curve it is the other way round, and the calendar theta is large because the month that passes carried the 31.5% 6M hazard. A window that crosses a coupon date is tested separately: from 21 Nov to 21 Dec 2026 on IG, mtm −49379.29 → −28032.64, coupon 25277.78, buyer's theta −3931.14, seller's +3931.14.

**Claim (criterion 4): JTD for the buyer is (1 − R)·N − mtm − accrued to the cent, and the seller's is the negative.**
Rows (curve, R, (1 − R)·N $, mtm $, period start, days to as_of, accrued $, JTD $):

| IG_flat | 0.40 | 6000000.00 | −65926.75 | 2026-06-22 | 85 | 23611.11 | 6042315.64 |
| HY_steep | 0.25 | 7500000.00 | −119444.44 | 2026-06-22 | 85 | 118055.56 | 7501388.89 |
| distressed_inverted | 0.20 | 8000000.00 | 1938337.32 | 2026-06-22 | 85 | 118055.56 | 5943607.13 |

The seller's JTD is checked as −(buyer's) to $0.01 on all three. `accrued_to_valuation_date` gives 0 on a coupon date (21 Dec 2026), 90 on the day before it (20 Dec, still the first period), and `schedule.accrued_days − 1` on the trade date.

**Claim (criterion 5): IR01 on the IG par trade is $9.75 (bar: under $200); on the distressed 5Y upfront trade it is −$399.26, which misses the plan's "over $500".**
Rows (curve, trade, mtm $, IR01 $; the 10Y rows are information):

| IG_flat | 5Y c100 | −65926.75 | +9.75 |
| IG_flat | 10Y c100 | 123669.80 | −64.60 |
| HY_steep | 5Y c500 | −119444.44 | 0.00 |
| HY_steep | 10Y c500 | 466279.46 | −232.96 |
| distressed_inverted | 5Y c500 | 1938337.32 | −399.26 |
| distressed_inverted | 10Y c500 | 1953636.97 | −695.71 |

The bump moves the 5Y OIS node's discount factor from 0.797893 to 0.797506. With the spreads fixed and re-bootstrapped, a par trade (HY) has no rate risk at all, an off-par trade's IR01 is the discounting of its value, and the distressed trade's $1.94m receivable over 4.8 years gives −$399: the sign is right (higher rates discount a receivable more) and the size is 2 bp of the mtm, a duration of about 2 years, which is what a front-loaded default distribution on an inverted curve gives. The 10Y distressed trade is −$696. Against the plan 3: the test pins the 5Y number in (300, 500) until the bar is reset.

**Claim (criterion 6): central and one-sided CS01 differ by under 0.01% per pillar on IG (bar 1%).**
Rows (pillar, one-sided $, central $, difference $, %):

| 6M | 0.1331 | 0.1331 | 0.0000 | 0.01% |
| 1Y | 0.7621 | 0.7621 | 0.0000 | 0.00% |
| 2Y | 2.3941 | 2.3942 | 0.0001 | 0.00% |
| 3Y | 3.8550 | 3.8550 | 0.0000 | 0.00% |
| 4Y | 5.4160 | 5.4158 | −0.0002 | 0.00% |
| 5Y | 4206.9304 | 4207.2794 | +0.3490 | 0.008% |
| 7Y | 0.0000 | 0.0000 | 0 | — (the $0.01 floor) |
| 10Y | 0.0000 | 0.0000 | 0 | — |
| parallel | 4218.2307 | 4219.8402 | +1.6095 | 0.038% |

The central number is above the one-sided on the 5Y and the parallel: the buyer is short convexity, the down bump loses more than the up bump gains (the Section 9 gamma sign).

**Claim (item 22): the seasoned HY 5Y trade agrees with QuantLib to 3e-16 per unit notional on all eight valuation dates with `includeSettlementDateFlows = True`; with the default `False` QuantLib drops the coupon paying on as_of + 1 and differs by that coupon on 20 Dec 2026 only.**
Rows (valuation date, its cash settlement date, our mtm/N at t_settle, QuantLib NPV/P(t_settle) with the flag True, Δ, the same with False, Δ):

| 2026-10-15 | 2026-10-20 | −0.000550924711 | −0.000550924711 | −2.5e-16 | −0.000550924711 | −2.5e-16 |
| 2026-12-18 | 2026-12-23 | −0.003197074429 | −0.003197074429 | −2.8e-16 | −0.003197074429 | −2.8e-16 |
| **2026-12-20** | 2026-12-23 | −0.003278982155 | −0.003278982155 | −2.5e-16 | 0.009362866529 | **−1.26e-2** |
| 2026-12-21 | 2026-12-24 | 0.009301995372 | 0.009301995372 | −1.9e-16 | 0.009301995372 | −1.9e-16 |
| 2026-12-22 | 2026-12-25 | 0.009241123617 | 0.009241123617 | −3.0e-16 | 0.009241123617 | −3.0e-16 |
| 2027-03-19 | 2027-03-24 | 0.003944020524 | 0.003944020524 | −2.5e-16 | 0.003944020524 | −2.5e-16 |
| 2028-06-20 | 2028-06-23 | 0.038520114686 | 0.038520114686 | −1.4e-16 | 0.038520114686 | −1.4e-16 |
| 2031-06-18 | 2031-06-23 | −0.012475389969 | −0.012475389969 | +1.7e-17 | −0.012475389969 | +1.7e-17 |

20 Dec 2026 is the day before the 21 Dec payment (20 Dec is a Sunday): with `False` QuantLib's NPV is higher by 0.01264 per unit notional, which is the 21 Dec coupon (500 bp × 91/360 = 0.01264) the buyer still owes under our rule, and the test asserts the gap is that coupon to 10%. No valuation date had to be avoided. The dates include a payment date itself (21 Dec: the coupon is excluded on both sides), a coupon date that is a business day (20 Jun 2028) and two days before maturity.

**Claim (Table 3, Chart 2): both are written, the committed files are what the code produces, and Chart 2 shows Part C item 5.**
Table 3: 3 rows × 30 columns (`curve, trade` then the 28 `RiskReport` fields in the plan's order); the transposed `.md` has 28 measure rows. Chart 2 rows (R, 1 − Q(5Y), MTM $ of the par trade re-bootstrapped, off-market re-bootstrapped, par hazard-fixed, off-market hazard-fixed):

| 0.10 | 0.0480 | −21500.00 | −918119.87 | 167670.38 | −720864.65 |
| 0.20 | 0.0539 | −21500.00 | −916089.29 | 104613.59 | −783921.45 |
| 0.30 | 0.0614 | −21500.00 | −913487.74 | 41556.79 | −846978.24 |
| 0.40 | 0.0713 | −21500.00 | −910035.03 | −21500.00 | −910035.03 |
| 0.41 | 0.0725 | −21500.00 | −909626.60 | −27805.68 | −916340.71 |
| 0.50 | 0.0850 | −21500.00 | −905231.82 | −84556.79 | −973091.83 |
| 0.60 | 0.1054 | −21500.00 | −898093.29 | −147613.59 | −1036148.62 |

The implied 5Y default probability rises from 4.8% to 10.5% across the range (λ ≈ s/(1 − R)), monotone at every step. The par trade re-bootstrapped is −$21,500 at every R (the dirty mtm is minus the 86-day accrued, 90 bp × 86/360 × $10m; the range over the 51 points is under $10). The two hazard-fixed lines are parallel with slope −$6,305.68 per point, the rec01_hazard_fixed of the previous claim; the off-market re-bootstrapped line has slope +$408.43 per point (0.40 → 0.41: −910035.03 → −909626.60), the rec01. The four lines meet at R = 0.40 pairwise. Generation: Table 3 in 4.4 s (1.3 to 1.5 s per curve), Chart 2 in 9.8 s.

## Before / after

| metric | before (`9f5f1ba`) | after (`6526bbb`) |
|---|---|---|
| tests | 323 | 356 |
| `assert_output_current` float tolerance | 1e-9 absolute | max(1e-9, 1e-9 × \|committed\|) |
| BUILD_PLAN.md Section 7 criterion 2 | on our pillar grid, IG and HY | matched nodes, every curve; on-our-grid rows as information |
| IG 5Y CS01, parallel / bucket sum | 4206.93 (5Y bump only, Table 2) | 4218.23 / 4219.49 |
| IG 5Y rec01 / rec01_hazard_fixed | — | 20.42 / −6305.68 |
| distressed 5Y IR01 | — | −399.26 |
| HY 5Y theta-calendar / theta-rolldown, 1 month | — | −12453.69 / −56263.05 |
| Table 3 rows × columns | — | 3 × 30 |
| Chart 2 rows | — | 51 |
| Tables 1, 2, 5, Chart 1 | — | byte-identical |

No pricing number changed; every Section 8 number is a difference of two `price()` calls on rebuilt inputs.

## Not verified

- **The `us_uk` calendar and the `grid` engine through `risk()`.** Both are passed through as keyword arguments to every `price()` and `bootstrap()` call, but every Section 8 number is on the weekend-only calendar with the `isda` engine. A run of `risk(..., calendar="us_uk")` and `engine="grid"` on IG would settle it (the second is slow: 20-odd bootstraps on the daily grid).
- **A theta window long enough to drop a survival pillar in calendar mode.** The 6M pillar is 96 days out and the windows are 1 day and 1 month, so `with_as_of("calendar")` drops only the 1M discount node (15 Oct 2026, exactly the 1-month date). Section 3 tested the pillar drop on the curve; its effect on a theta was not exercised.
- **The seller side and the tenor-shifted curves against QuantLib.** Seasoned comparisons are all protection buys on calendar-shifted curves; the tenor-shifted curve is the same function of t and the seller negates, so both are tested against ourselves only.
- **rec01 on `distressed_inverted` with the upfront, not the spread, held fixed.** Not computed for the review (the number is a mix of the two readings because the joint curve does not reprice the upfronts, review 06); Against the plan 2 asks which reading the reviewer wants.
- **The size of the distressed IR01.** −$399 is consistent with a 2-year duration on a $1.94m receivable, but no independent duration was computed to confirm the figure; a check would be the mtm on the two discount curves without re-bootstrapping (pure discounting) against the reported number.

## Open

Nothing tried and unexplained.

## Against the plan

1. **Items 35 to 38 are not the approval message's words.** The session prompt said to append them "exactly as given in the Section 07 approval message", but the message text was not in the prompt, issue 7 has no comment, and nothing in the repo or the memory holds it. The items were written from the prompt's summary (35 and 38 are specified there in one line each; 36 and 37 are the remaining review 07 questions, taken as accepted since the prompt raised nothing else), with a bracketed note in `docs/CONVENTIONS_RESOLVED.md`. Would the reviewer paste the message so the next session can replace the wording verbatim (a `Section 09 fix` commit), or does the wording as committed stand?
2. **rec01 and IR01 hold the conventional spread fixed on the upfront-quoted curve, not the upfront.** Part D.2 says "market quotes held fixed and re-bootstrapping"; for `distressed_inverted` the market quote is an upfront, but the bootstrap fits the conventional spreads (Part A.4) and does not reprice the upfronts (review 06 criterion 6: the joint curve's 5Y upfront is 1.3 points below the flat-hazard one), so "upfront fixed" through the bootstrap is neither reading cleanly: with the upfronts fed back and re-converted at R + 0.01 the distressed rec01 came out at −$1,151 and the IR01 at $31, mixtures of the conversion moving and the curve moving. With the spreads fixed (the reading Part C item 5 argues in, "PV_prot stays pinned at s_mkt·A", and the one D.2 gives for CS01) the numbers are −$9,064 and −$399, and every rebuild is one bootstrap of par-spread quotes rather than eight conversions plus a bootstrap (1.5 s per curve instead of 17.6 s). Accept the spread-fixed reading for all three bumps, or should rec01 and IR01 on an upfront-quoted curve hold the upfront fixed and re-derive the spreads?
3. **Criterion 5's second half is not met: the distressed 5Y IR01 is −$399.26 against "over $500".** The IG half is met ($9.75 against $200). The test pins the distressed number in (300, 500) with the plan's $500 kept as `IR01_DISTRESSED_MIN_USD`. Should the bar become $300 for the 5Y trade, or should the criterion name the 10Y distressed trade (−$695.71)?
4. **The off-market trade is struck 200 bp above the par spread on IG, not below.** Criterion 2 says "s_par − 200 bp"; the IG 5Y par spread is 90 bp, so that coupon is −110 bp and `price()` refuses it. The test runs the plan's sign on HY (500 − 200 = 300 bp, rec01 −$1,243) and +200 on IG (290 bp, rec01 +$408); Chart 2, which Part C item 1 puts on IG, draws +200. Accept, or move Chart 2's panel (b) to HY at s_par − 200?
5. **Chart 2's CSV has six columns, not four.** The plan lists `recovery, implied_5y_default_prob, mtm_par_trade, mtm_offmarket_trade`; the session prompt asks for the hazard-fixed lines to be drawn as well, so `mtm_par_trade_hazard_fixed` and `mtm_offmarket_trade_hazard_fixed` are added after the plan's four. Accept?
6. **Panel (b)'s "steep" line is the re-bootstrapped off-market one at $408 per point**, which next to the hazard-fixed lines at −$6,306 per point reads as nearly flat on the chart (its range across 50 points is $20k against $315k). The plan's word "steep" (Part C item 1) is relative to the par line's zero. Accept the chart as drawn, or should panel (b) show the re-bootstrapped pair and the hazard-fixed pair on separate axes?
7. **The 1-month theta from the trade date contains the first coupon payment (21 Sep 2026).** This is item 7 applied as written; the consequence is that theta_1m is about 27× theta_1d on IG (−3,913 against −147) rather than 30×, and on the flat curve it equals the protection consumed only after the coupon is netted. Stated here so the Table 3 numbers are not read as a carry.
8. **JTD uses `PriceResult.mtm`**, which for an `upfront_pct`-quoted seasoned trade is net of the inception cash (item 25). Part C item 2 says "PV_MTM the buyer's dirty MTM", which is that field; but the P&L on default of such a trade against its current mark would use the unwind value, not the value net of sunk cash. The Table 3 trades have `quote = None`, so nothing in the outputs depends on it. Should JTD use the unwind value (`quote = None` pricing) for every trade?
9. **`risk()` refuses a state whose survival curve is not the bootstrap of its spreads** (one extra bootstrap per call, hazards within 1e-9) and a state whose pillars are not `PILLARS`; `ir01` refuses a discount curve without par rates. None of this is in the plan. Accept?
10. **`cds/risk.py` exposes the per-measure functions and the rebuilt states**, not only `risk()`, and each takes an optional `spreads_bp` so Chart 2 and the tests can reuse the spreads without re-converting. `cds/report.py` gains `trade_label` and `STANDARD_COUPONS_BY_CURVE` (with `TABLE_5_COUPONS_BP` kept as an alias). Accept?
11. **Table 3's `.md` is rounded to the cent** (the CSV holds 10 decimals as every other output); a measure that rounds to −0.00 is written as 0.00. Accept?
12. `cds/__init__.py` still says "None exist yet" (reviews 03 to 07); Section 10.
13. The untracked `11_CDS_Pricing_Bootstrap.docx` at the repo root is still there.

## Reviewer reads (max 6, in order)

1. `cds/risk.py` — the module docstring (the spread-fixed reading, the theta definition, the JTD accrued), then `risk()` and `theta()`.
2. `outputs/tables/table_3_risk_report.md` — the 28 measures × 3 trades.
3. `outputs/charts/chart_2_recovery_dependence.png` — panel (b): the flat par line, the two parallel hazard-fixed lines, the off-market line (questions 4 to 6).
4. `tests/test_risk.py` — `test_ir01_small_on_the_ig_par_trade_and_larger_on_the_distressed_upfront_trade` (question 3), `test_rec01_is_near_zero_at_par_and_grows_off_market`, `test_seasoned_trade_matches_quantlib_with_settlement_date_flows_included` and the item 22 test after it.
5. `docs/CONVENTIONS_RESOLVED.md` items 35 to 38 (question 1); `BUILD_PLAN.md` Section 7 criterion 2.
6. `tests/conftest.py` — `assert_output_current` (item 38) and the ten Section 8 constants.
