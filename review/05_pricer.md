# Review — Section 05 — the pricer, the flat-hazard conversions and the textbook model

Date: 2026-09-16   Commit: b9857c1   Tests: 279/279 (216 from Sections 1 to 4 including the 8 added in this session's pre-commit, 63 new; 0 skipped)

Three commits. `42f12f5 Section 05: resolved Section 4 questions` (items 19 to 23 in `docs/CONVENTIONS_RESOLVED.md`, the `(t_stepin, T]` phrase in BUILD_PLAN.md Section 4 rewritten to the end-of-day limits, and the weekend-maturity QuantLib oracle cases in `tests/test_legs.py`, all green before any Section 5 code), `b9857c1 Section 05: pricer` (code and tests), and this review.

## What changed

- `cds/pricer.py` (new) — `price(state, trade, *, calendar, engine, half_day_bias) -> PriceResult`; `value(discount, survival, recovery, trade, as_of, ...) -> Valuation` (the per-unit-notional numbers before side and notional; `price` and the conversions both go through it); `accrued_days(schedule, as_of)`; `cash_settle_date(as_of, calendar)`; `clean_par_spread_bp(state, trade)`; `implied_flat_hazard(discount, trade, quoted_spread_bp)`; `quoted_spread_to_upfront(discount, trade, quoted_spread_bp)`; `upfront_to_quoted_spread(discount, trade, upfront_pct)`; constants `HAZARD_BOUNDS = (0.0, 5.0)`, `HAZARD_XTOL = 1e-12`, `SIDE_SIGN`.
- `cds/textbook.py` (new) — `annuity`, `protection_pv`, `par_spread_bp`, `implied_hazard`, `survival`, `upfront_pct`. Imports `math` only.
- `tests/conftest.py` — ten constants: `PAR_UPFRONT_BP = 0.01`, `PAR_UPFRONT_USD = 1.0`, `PAR_SPREAD_REPRICE_BP = 1e-9`, `CONVERSION_ROUNDTRIP_BP = 1e-6` (the plan's four bars), `PRICER_IDENTITY_ABS_TOL = 1e-12`, `QL_ACCRUED_ABS_USD = 1e-6`, `TEXTBOOK_ABS_TOL = 1e-12`, `FLAT_HAZARD_SOLVE_ABS_TOL = 1e-9`, `CLEAN_SPREAD_TENOR_RANGE_BP = 0.1`, `QL_PRICER_ABS_TOL = 1e-9`, each with its one-line reason.
- `tests/test_pricer.py` (53 tests) — the plan's criteria 1 to 7, quote and side handling, seasoned-trade accrued, and a QuantLib oracle on `fairUpfront`, `fairSpread`, `accrualRebate` and `couponLegNPV`.
- `tests/test_textbook.py` (10 tests) — criterion 8 and the no-import rule.
- `docs/CONVENTIONS_RESOLVED.md` items 19 to 23; `BUILD_PLAN.md` Section 4, the merged-grid sentence; `tests/test_legs.py`, 8 oracle cases on Sunday maturities.

**Rules stated in full.** Symbols as in SPEC section 6; leg values from Section 4 per unit notional at `as_of`; c = coupon_bp / 10⁴; t_settle = `as_of` + 3 business days on the trade's calendar; D = 1 / P(t_settle) with t in act/365F years from `as_of`.

1. `par_spread_bp` = 10⁴ · PV_prot / A, A = annuity_coupon + annuity_accrual, at the valuation date (item 21). Independent of the coupon.
2. `U_dirty` = D · (PV_prot − c · A), the buyer's value per unit notional at settlement.
3. `accrued_days` = the days from the start of the accrual period containing `as_of` + 1 to `as_of` + 1. For `as_of` = trade date this is the schedule's `accrued_days` (step-in − accrual start, Section 1). `accrued` = c · N · accrued_days / 360, a cash amount on the settlement date, not discounted.
4. `clean_upfront_pct` = 100 · (U_dirty + accrued / N). `mtm` = side_sign · N · (U_dirty − inception_cash), side_sign +1 for `buy`, −1 for `sell`; inception_cash = 0 for `quote=None` and for a `par_spread_bp` quote (whose value must equal `coupon_bp`), and = value / 100 − c · accrued_days₀ / 360 for an `upfront_pct` quote, accrued_days₀ the schedule's (Against the plan 2).
5. `risky_annuity` = D · A, `pv_protection` = D · PV_prot, `pv_premium` = D · c · A, `cash_settle_date` = t_settle. Every field at settlement (item 3).
6. `clean_par_spread_bp` = 10⁴ · PV_prot / (A − accrued_fraction / D), accrued_fraction = accrued_days / 360: the spread at which `clean_upfront_pct` is zero. This is QuantLib's `fairSpread` (oracle rows below) and is not the plan's par spread; it is exposed as a function, not a `PriceResult` field.
7. Conversions: `implied_flat_hazard` is Brent on λ ∈ [0, 5], xtol 1e-12, for `par_spread_bp`(single pillar at the trade's maturity, hazard λ, recovery `trade.recovery`, valued on `discount.as_of`) = quoted spread. `quoted_spread_to_upfront` = `clean_upfront_pct` at that λ. `upfront_to_quoted_spread` = Brent on λ for `clean_upfront_pct`(λ) = upfront, then `par_spread_bp` at the root (Against the plan 3). Both raise outside the reachable range.
8. `price` raises `ValueError` if `state.as_of` and the three curves' `as_of` are not one date; if `trade.recovery` ≠ `state.recovery.R(0)`; if the trade date is not a business day on the calendar (item 10); if `as_of` < trade date; on a non-positive notional or negative coupon; on a `par_spread_bp` quote whose value ≠ `coupon_bp`; on an `upfront_pct` quote without `coupon_bp` or with one ≠ the trade's (item 12).
9. Textbook: k = λ + r, A = (1 − e^{−kT}) / k (T when k = 0, `expm1` otherwise), PV_prot = (1 − R) λ A, s_par = 10⁴ λ (1 − R), upfront = 100 · (PV_prot − c A). No schedule, no day count, no accrued.

## Findings

The base contract unless stated: trade date = `as_of` = 15 Sep 2026, 5Y maturity 20 Jun 2031, step-in 16 Sep, cash settle 18 Sep 2026, accrual start 22 Jun 2026, 86 accrued days, N = 10,000,000, coupon 100 bp, buyer. Flat curve: 1% hazard on the standard pillars, R = 0.40; steep and inverted as in Section 4. Discount: the Section 2 snapshot. Legs at `as_of` (the Section 4 numbers, unchanged): A = 4.4662902914, PV_prot = 0.0251616918. P(t_settle) = 0.999676765387 at t = 3/365, so D = 1.000323339127; accrued fraction 86/360 = 0.2388888889.

**Claim (criteria 1 and 2): at the par coupon the dirty upfront is zero, the par spread reprices, and the clean upfront is the accrued.** Under item 21 the par spread is s_par = 56.336892836 bp. The plan's wording, "clean_upfront_pct within 0.01 bp of zero" and "U_dirty + accrued under $1", holds at the clean-value spread s_clean = 59.519382629 bp instead; both are tested and both rows are here (Against the plan 1).
Numbers: at c = s_par, mtm = +0.000000 $ against `PAR_UPFRONT_USD = 1`, par spread reprices to 0 against `PAR_SPREAD_REPRICE_BP = 1e-9`, clean_upfront_pct = 0.1345825773 = 100 · accrued / N exactly. At c = s_clean, clean_upfront_pct = −0.0000000000 against `PAR_UPFRONT_BP = 0.01` bp of notional (1e-4 %), mtm + accrued = −0.000000 $ against $1.
Rows (coupon, mtm $, clean_upfront_pct, accrued $, mtm + accrued $, par_spread_bp, pv_protection, pv_premium):

| 100 (base) | −195,075.166667 | −1.7118627778 | 23,888.888889 | −171,186.277778 | 56.336892836 | 0.0251698275 | 0.0446773442 |
| s_par = 56.336893 | +0.000000 | +0.1345825773 | 13,458.257733 | +13,458.257733 | 56.336892836 | 0.0251698275 | 0.0251698275 |
| s_clean = 59.519383 | −14,218.519184 | −0.0000000000 | 14,218.519184 | −0.000000 | 56.336892836 | 0.0251698275 | 0.0265916794 |

At c = s_par, pv_protection = pv_premium to 1e-12; the buyer's mtm is the dirty value, zero, and what the quote screen would show is +13.46 bp of notional, the rebate the buyer receives. At c = s_clean the buyer pays nothing clean and receives the accrued at settlement, so mtm = −accrued.

**Claim: the clean-value spread is one number across tenors on a flat hazard and the dirty par spread is not.** (Not a criterion; the evidence for question 1.)
Number: s_clean ranges 59.487671 to 59.522989 bp from 6M to 10Y (0.035 bp, against `CLEAN_SPREAD_TENOR_RANGE_BP = 0.1`); s_par ranges 31.208270 to 57.712480 bp. The last two columns are the single flat hazard that gives a 100 bp spread on that tenor alone, i.e. what the first pillar of a Section 6 bootstrap, or `fallback="upfront"`, would return for a flat 100 bp curve under each definition.
Rows (tenor, maturity, coupons, accrued days, A, accrued/D, s_par dirty bp, s_clean bp, ratio, λ for dirty 100 bp, λ for clean 100 bp):

| 6M | 2026-12-20 | 2 | 86 | 0.502357 | 0.238812 | 31.208270 | 59.487671 | 1.9062 | 3.2088% | 1.6810% |
| 1Y | 2027-06-20 | 4 | 86 | 0.992019 | 0.238812 | 45.175812 | 59.499242 | 1.3171 | 2.2161% | 1.6807% |
| 2Y | 2028-06-20 | 8 | 86 | 1.936912 | 0.238812 | 52.174884 | 59.512479 | 1.1406 | 1.9185% | 1.6803% |
| 5Y | 2031-06-20 | 20 | 86 | 4.466290 | 0.238812 | 56.336893 | 59.519383 | 1.0565 | 1.7767% | 1.6801% |
| 10Y | 2036-06-20 | 40 | 86 | 7.851264 | 0.238812 | 57.712480 | 59.522989 | 1.0314 | 1.7345% | 1.6800% |

The 6M contract pays two full coupons (182 days) for 96 days of protection, and the dirty par spread is the spread that makes those two coupons worth the protection: 31 bp for a name whose credit-triangle spread is 60 bp. The clean-value spread nets the 86 rebated days out of the annuity and lands on 59.5 bp on every tenor; the 0.035 bp range is the discounting of the one-day coupon lag. Section 6 criterion 2 (a flat 100 bp curve gives every λ_i within 3% of 1.67%) is met by the last column and not the one before it.

**Claim (criterion 3): quoted spread → upfront → quoted spread round-trips to 1e-6 bp.**
Number: worst |Δ| = 4.3e-10 bp against `CONVERSION_ROUNDTRIP_BP = 1e-6`, 6 cases. λ_flat is the same at both coupons for a given spread, as it must be (the coupon enters only the upfront).
Rows (quoted bp, coupon bp, λ_flat, clean upfront %, recovered bp, Δ bp):

| 45 | 100 | 0.0079856786 | −2.22905815 | 45.000000000 | −3.6e-13 |
| 45 | 500 | 0.0079856786 | −19.22220837 | 45.000000000 | −3.4e-13 |
| 250 | 100 | 0.0445698451 | +6.46727158 | 250.000000000 | +4.3e-10 |
| 250 | 500 | 0.0445698451 | −9.18619338 | 250.000000000 | +8.4e-11 |
| 1200 | 100 | 0.2193022785 | +32.95707855 | 1200.000000000 | −4.0e-10 |
| 1200 | 500 | 0.2193022785 | +22.01511059 | 1200.000000000 | −1.0e-10 |

Also checked: the upfront is monotone in the quoted spread on (0, 45, 100, 250, 1200) bp; a zero spread gives λ = 0 exactly; a 99% upfront (above 1 − R) raises; on the flat curve the conversion at the curve's own par spread returns λ = 0.01 to `FLAT_HAZARD_SOLVE_ABS_TOL = 1e-9` and `price()`'s clean upfront to 0.01 bp of notional (the flat-hazard conversion is exact on a flat curve). Each conversion is one or two Brent solves of about 40 leg evaluations; six conversions took 0.12 s.

**Claim (criterion 4): raising every hazard 10% raises the buyer's mtm and lowers the seller's, on all three curves.**
Number: 3 curves, buyer Δ > 0 and seller Δ < 0 in every row; buyer + seller = 0 to 1e-12 · N; clean_upfront_pct is the same for both sides.
Rows (curve, R, buyer mtm base, buyer mtm up, Δ buyer, seller mtm base, seller mtm up, Δ seller, s_par base, s_par up):

| flat | 0.40 | −195,075.17 | −169,574.11 | +25,501.06 | +195,075.17 | +169,574.11 | −25,501.06 | 56.3369 | 61.9629 |
| steep | 0.25 | +734,653.60 | +842,157.57 | +107,503.97 | −734,653.60 | −842,157.57 | −107,503.97 | 272.1596 | 298.6544 |
| inverted | 0.20 | +3,808,712.28 | +4,082,967.63 | +274,255.35 | −3,808,712.28 | −4,082,967.63 | −274,255.35 | 1348.7623 | 1489.1346 |

**Claim (criterion 5): `accrued` = coupon/10⁴ · N · accrued_days/360 and accrued_days equals QuantLib's on the 16 trade dates.**
Number: 16 of 16 schedule-level rows match `ql.CreditDefaultSwap(...).accrualRebate().amount()` to under 1e-9 $ against `QL_ACCRUED_ABS_USD = 1e-6`; `price().accrued` matches on the 11 business-day trade dates and `price()` raises on the 5 weekend ones (item 10; Against the plan 8). QuantLib's rebate date equals our cash settle date on all 16.
Rows (trade date, weekday, 5Y maturity, accrual start, step-in, accrued days, ours $, QuantLib $, Δ, rebate date = cash settle, price()):

| 2015-12-18 | Fri | 2020-12-20 | 2015-09-21 | 2015-12-19 | 89 | 24,722.2222 | 24,722.2222 | +1.3e-10 | 2015-12-23 | accrued 24,722.2222, settle 2015-12-23 |
| 2016-03-19 | Sat | 2020-12-20 | 2015-12-21 | 2016-03-20 | 90 | 25,000.0000 | 25,000.0000 | +5.3e-10 | 2016-03-23 | raises (weekend trade date) |
| 2016-03-20 | Sun | 2021-06-20 | 2016-03-21 | 2016-03-21 | 0 | 0.0000 | 0.0000 | 0 | 2016-03-23 | raises (weekend trade date) |
| 2016-03-21 | Mon | 2021-06-20 | 2016-03-21 | 2016-03-22 | 1 | 277.7778 | 277.7778 | +4.0e-10 | 2016-03-24 | accrued 277.7778, settle 2016-03-24 |
| 2016-09-19 | Mon | 2021-06-20 | 2016-09-20 | 2016-09-20 | 0 | 0.0000 | 0.0000 | 0 | 2016-09-22 | accrued 0.0000, settle 2016-09-22 |
| 2016-09-20 | Tue | 2021-12-20 | 2016-09-20 | 2016-09-21 | 1 | 277.7778 | 277.7778 | +4.0e-10 | 2016-09-23 | accrued 277.7778, settle 2016-09-23 |
| 2020-02-29 | Sat | 2024-12-20 | 2019-12-20 | 2020-03-01 | 72 | 20,000.0000 | 20,000.0000 | −1.8e-11 | 2020-03-04 | raises (weekend trade date) |
| 2020-12-20 | Sun | 2025-12-20 | 2020-12-21 | 2020-12-21 | 0 | 0.0000 | 0.0000 | 0 | 2020-12-23 | raises (weekend trade date) |
| 2020-12-31 | Thu | 2025-12-20 | 2020-12-21 | 2021-01-01 | 11 | 3,055.5556 | 3,055.5556 | −3.4e-11 | 2021-01-05 | accrued 3,055.5556, settle 2021-01-05 |
| 2021-01-04 | Mon | 2025-12-20 | 2020-12-21 | 2021-01-05 | 15 | 4,166.6667 | 4,166.6667 | −6.5e-10 | 2021-01-07 | accrued 4,166.6667, settle 2021-01-07 |
| 2024-02-29 | Thu | 2028-12-20 | 2023-12-20 | 2024-03-01 | 72 | 20,000.0000 | 20,000.0000 | −1.8e-11 | 2024-03-05 | accrued 20,000.0000, settle 2024-03-05 |
| 2024-06-19 | Wed | 2029-06-20 | 2024-06-20 | 2024-06-20 | 0 | 0.0000 | 0.0000 | 0 | 2024-06-24 | accrued 0.0000, settle 2024-06-24 |
| 2024-06-20 | Thu | 2029-06-20 | 2024-06-20 | 2024-06-21 | 1 | 277.7778 | 277.7778 | +4.0e-10 | 2024-06-25 | accrued 277.7778, settle 2024-06-25 |
| 2025-09-20 | Sat | 2030-12-20 | 2025-06-20 | 2025-09-21 | 93 | 25,833.3333 | 25,833.3333 | −4.9e-10 | 2025-09-24 | raises (weekend trade date) |
| 2026-06-19 | Fri | 2031-06-20 | 2026-03-20 | 2026-06-20 | 92 | 25,555.5556 | 25,555.5556 | −8.9e-10 | 2026-06-24 | accrued 25,555.5556, settle 2026-06-24 |
| 2026-09-16 | Wed | 2031-06-20 | 2026-06-22 | 2026-09-17 | 87 | 24,166.6667 | 24,166.6667 | −6.7e-10 | 2026-09-21 | accrued 24,166.6667, settle 2026-09-21 |

The 1e-10 residues are QuantLib's `rate × yearFraction × notional` against our `coupon × N × days / 360` in a different order. The same run on the 6M maturities gives the one single-period standard trade in the set, 2016-09-19 6M (maturity 2016-12-20, 1 coupon, accrual start 2016-09-20, 0 days): ours 0.0000, QuantLib 0.0000, so the `Actual360(True)` last-period day count does not enter the rebate on any standard trade.

**Claim (criterion 6): every settlement amount is the valuation amount divided by P(t_settle).**
Number: 4 quantities on the snapshot curve, Δ ≤ 3.5e-18 against `PRICER_IDENTITY_ABS_TOL = 1e-12`; with D fixed at 2 by construction (a one-node curve at P(18 Sep 2026) = 0.5, flat forward after) the ratios are 2.000000000000.
Rows (quantity, at valuation from the legs, / P(t_settle), price(), Δ):

| PV_prot | 0.025161691752 | 0.025169827511 | 0.025169827511 | 0 |
| A | 4.466290291395 | 4.467734417800 | 4.467734417800 | 0 |
| c · A | 0.044662902914 | 0.044677344178 | 0.044677344178 | 0 |
| U_dirty = mtm / N | −0.019501211162 | −0.019507516667 | −0.019507516667 | +3.5e-18 |
| D = 2 curve: A | 0.0632062630 | 0.1264125261 | 0.1264125261 | ratio 2.000000000000 |
| D = 2 curve: PV_prot | 0.0000711382 | 0.0001422763 | 0.0001422763 | ratio 2.000000000000 |

**Claim (criterion 7): `price` raises when the `as_of` disagree.** Four cases: `state.as_of` moved a day; the survival, the recovery, the discount each moved a day (tenor mode) with the others fixed. All raise `ValueError`. The legs already raise on the three curves (Section 4 rule 7); `price` checks `state.as_of` against them first with its own message.

**Claim (criterion 8): textbook s_par = λ(1 − R) to 1e-12; the annuity tends to T at r = 0, λ → 0.**
Number: Δ = 0 on all five cases against `TEXTBOOK_ABS_TOL = 1e-12`; annuity(0, 0, 5) = 5.0 exactly, annuity(1e-14, 0, 5) = 4.999999999999875, and PV_prot / A reproduces the triangle to 1e-8 bp (1e-12 relative). The module's import lines contain no `cds` name (asserted on the source).
Rows (λ, R, r, T, A, PV_prot, s_par bp, λ(1 − R) bp, Δ, upfront % at c = 100):

| 0.0167 | 0.40 | 0.04 | 5 | 4.3537368229 | 0.0436244430 | 100.2000000000 | 100.2000000000 | 0 | +0.008707 |
| 0.01 | 0.40 | 0.04 | 5 | 4.4239843386 | 0.0265439060 | 60.0000000000 | 60.0000000000 | 0 | −1.769594 |
| 0.08 | 0.25 | 0.04 | 5 | 3.7599030325 | 0.2255941820 | 600.0000000000 | 600.0000000000 | 0 | +18.799515 |
| 0.30 | 0.20 | 0.04 | 5 | 2.4038719881 | 0.5769292771 | 2400.0000000000 | 2400.0000000000 | 0 | +55.289056 |
| 0.0 | 0.40 | 0.04 | 5 | 4.5317311731 | 0.0000000000 | 0.0000000000 | 0.0000000000 | 0 | −4.531731 |

For orientation only (Section 7 owns Table 5): the textbook 5Y annuity at λ = 1% and r = the snapshot's act/365F zero rate to 20 Jun 2031 (4.513%) is 4.190015 against the ISDA path's 4.467734 at settlement, which carries 86 days of a full first coupon (0.239) and discrete quarterly payment; the textbook par spread is 60.0000 bp against the ISDA path's 56.3369 dirty and 59.5194 clean.

**Claim: the clean upfront, the clean-value spread, the accrued and the annuity are QuantLib's `IsdaCdsEngine` numbers.** (Beyond the plan's list; the Section 4 review predicted any Section 7 gap would be in the pricer, so this is the check. `fairUpfront` is QuantLib's clean upfront at the T+3 settlement date; `fairSpread` its clean-value spread; the plan's `par_spread_bp` is deliberately not compared, item 21.)
Number: 12 cases (3 curves × 6M, 1Y, 5Y, 10Y), worst |Δ upfront| under 1e-9 %, worst |Δ spread| = 2.7e-10 bp, against `QL_PRICER_ABS_TOL = 1e-9`.
Rows (curve, tenor, fairSpread QuantLib bp, clean_par_spread_bp ours, Δ bp, par_spread_bp item 21, fairUpfront QuantLib %, clean_upfront_pct ours):

| flat | 6M | 59.487671296 | 59.487671296 | −6.6e-12 | 31.208270 | −0.106802798 | −0.106802798 |
| flat | 1Y | 59.499241586 | 59.499241586 | −3.7e-12 | 45.175812 | −0.305153292 | −0.305153292 |
| flat | 5Y | 59.519382629 | 59.519382629 | −8.7e-13 | 56.336893 | −1.711862778 | −1.711862778 |
| flat | 10Y | 59.522989048 | 59.522989048 | −7.8e-13 | 57.712480 | −3.082289591 | −3.082289591 |
| steep | 6M | 74.359589120 | 74.359589120 | −8.3e-12 | 39.010337 | −0.067595908 | −0.067595908 |
| steep | 1Y | 122.686585631 | 122.686585631 | −7.7e-12 | 93.115947 | 0.170658705 | 0.170658705 |
| steep | 5Y | 288.298971919 | 288.298971919 | −4.4e-12 | 272.159564 | 7.585424920 | 7.585424920 |
| steep | 10Y | 393.062106401 | 393.062106401 | −5.5e-12 | 379.246359 | 19.217754904 | 19.217754904 |
| inverted | 6M | 2378.408631135 | 2378.408631135 | −2.7e-10 | 1225.582927 | 5.786375578 | 5.786375578 |
| inverted | 1Y | 2130.083523995 | 2130.083523995 | −1.4e-10 | 1577.510393 | 13.844979692 | 13.844979692 |
| inverted | 5Y | 1463.380826241 | 1463.380826241 | −2.9e-11 | 1348.762275 | 38.326011711 | 38.326011711 |
| inverted | 10Y | 1209.303041566 | 1209.303041566 | −2.1e-11 | 1143.370531 | 45.955080643 | 45.955080643 |

So the pricer's settlement discounting, accrued and clean/dirty split are QuantLib's to 1e-9; Section 7's 1 bp bar on upfront has nothing left to absorb on the pricer layer. The `par_spread_bp` column is the one number in this table QuantLib does not produce.

**Claim: quotes and sides do what item 8 says.**
- A trade quoted at its own clean upfront, valued at inception, has mtm = +0.00e+00 (identity, against 1e-12 · N). The unquoted mtm is the dirty cash: −195,075.1667 = clean −1.71186278% · N − accrued 23,888.8889. Reading `value/100` literally as the plan writes it would give mtm = −23,888.89 on the trade date (Against the plan 2).
- A running-spread quote of 250 bp on the steep curve: mtm = +94,561.14 = N · D · (PV_prot − 0.025 · A) (identity), par 272.1596 bp, clean_upfront_pct +1.542834 (the current unwind level, unaffected by the quote). A 250 bp `par_spread_bp` quote on a 100 bp coupon raises; an `upfront_pct` quote without `coupon_bp`, or with 500 on a 100 bp trade, raises; `recovery=0.25` on the R = 0.40 state raises; a Saturday trade date raises; `as_of` before the trade date raises; notional 0 raises.
- `side="sell"` negates mtm and nothing else: the other seven fields are equal for the two sides on the inverted curve at coupon 500 (asserted field by field).

**Claim: for a seasoned trade the accrued and the settlement date follow the valuation date.** (Section 8 needs both; only the arithmetic is checked here, Not verified 1.)
Rows (as_of, step-in = as_of + 1, period start, accrued days, cash settle) for the base 5Y trade:

| 2026-09-15 | 2026-09-16 | 2026-06-22 | 86 | 2026-09-18 |
| 2026-09-19 | 2026-09-20 (Sun) | 2026-06-22 | 90 | 2026-09-23 |
| 2026-09-20 | 2026-09-21 | 2026-09-21 | 0 | 2026-09-23 |
| 2026-09-21 | 2026-09-22 | 2026-09-21 | 1 | 2026-09-24 |
| 2026-10-15 | 2026-10-16 | 2026-09-21 | 25 | 2026-10-20 |
| 2026-12-19 | 2026-12-20 (Sun) | 2026-09-21 | 90 | 2026-12-23 |
| 2026-12-20 | 2026-12-21 | 2026-12-21 | 0 | 2026-12-23 |
| 2031-06-19 | 2031-06-20 | 2031-03-20 | 92 | 2031-06-24 |

`price()` at `as_of` = 15 Oct 2026 (curves shifted in calendar mode): accrued 6,944.4444 $ (25 days), cash settle 20 Oct 2026, mtm −175,476.94, clean_upfront_pct −1.685325, par 58.546694 bp. `accrued_days` raises for `as_of` on or after maturity.

## Before / after

Weekend maturities, added to `tests/test_legs.py` in the pre-commit as the prompt asked (review 04, Not verified 4): the 6M and 1Y pillars of this snapshot, 20 Dec 2026 and 20 Jun 2027, both Sundays, so the last coupon pays on the Monday and the last accrual integral ends on the Sunday. Flat and inverted curves, both bias settings, `QL_LEGS_ABS_TOL = 1e-12`. All 8 pass; worst |ΔA| = 3.7e-14.
Rows (maturity, curve, bias, coupons, last pay, A QuantLib, A ours, Δ, pv_protection QuantLib, ours, Δ):

| 2026-12-20 | flat | half | 2 | 2026-12-21 | 0.5023568182 | 0.5023568182 | +1.9e-14 | 0.0015677687 | 0.0015677687 | +2.2e-19 |
| 2026-12-20 | flat | none | 2 | 2026-12-21 | 0.5023531891 | 0.5023531891 | +1.9e-14 | 0.0015677687 | 0.0015677687 | +2.2e-19 |
| 2026-12-20 | inverted | half | 2 | 2026-12-21 | 0.4926952439 | 0.4926952439 | +1.8e-14 | 0.0603838879 | 0.0603838879 | 0 |
| 2026-12-20 | inverted | none | 2 | 2026-12-21 | 0.4925904108 | 0.4925904108 | +1.8e-14 | 0.0603838879 | 0.0603838879 | 0 |
| 2027-06-20 | flat | half | 4 | 2027-06-21 | 0.9920189404 | 0.9920189404 | +3.7e-14 | 0.0044815261 | 0.0044815261 | +8.7e-19 |
| 2027-06-20 | flat | none | 4 | 2027-06-21 | 0.9920085665 | 0.9920085665 | +3.7e-14 | 0.0044815261 | 0.0044815261 | +8.7e-19 |
| 2027-06-20 | inverted | half | 4 | 2027-06-21 | 0.9205818724 | 0.9205818724 | +3.3e-14 | 0.1452227472 | 0.1452227472 | +2.8e-17 |
| 2027-06-20 | inverted | none | 4 | 2027-06-21 | 0.9203297496 | 0.9203297496 | +3.3e-14 | 0.1452227472 | 0.1452227472 | +2.8e-17 |

The existing oracle test and the new one share one QuantLib construction (`_quantlib_legs` in `tests/test_legs.py`); the 12 Section 4 cases are unchanged.

| metric | before (review 04) | after |
|---|---|---|
| tests | 208 | 279 (208 + 8 weekend maturities + 53 pricer + 10 textbook) |
| 5Y flat A at as_of | 4.4662902914 | 4.4662902914 |
| 5Y flat PV_prot at as_of | 0.0251616918 | 0.0251616918 |
| 5Y flat par spread bp | 56.336893 | 56.336893 (`par_spread_bp`); 59.519383 (`clean_par_spread_bp`, new) |
| 5Y flat clean upfront at coupon 100 | — | −1.71186278 % (= QuantLib fairUpfront) |
| 5Y flat accrued, N = 10m | — | $23,888.89 (86 days; = QuantLib accrualRebate) |

## Not verified

- **Seasoned trades against QuantLib.** `accrued_days`, `cash_settle_date` and the legs' coupon inclusion are exercised at `as_of` = 15 Oct 2026 and the arithmetic is asserted, but no seasoned `price()` is compared with QuantLib at a moved `evaluationDate`. Item 22 assigns that to Section 8, which must also decide whether a coupon paying on `as_of` + 1 is in (ours) or out (QuantLib's default).
- **The clean/dirty split for a seasoned trade quoted upfront.** `inception_cash` subtracts the accrued of the trade's own schedule; the identity test is at inception only. A seasoned upfront-quoted trade is arithmetic on the same two numbers.
- **Conversions on a seasoned trade** (`trade.trade_date` before `discount.as_of`): the code allows it; nothing calls it. Section 6 converts contracts dated `as_of`.
- **The `us_uk` calendar through `price()`**: the `calendar` argument is passed to the schedule and the settlement date; only "weekends" is exercised.
- **A trade in the last coupon period with accrued days > 0.** No standard maturity produces one (the shortest first period the roll rule allows is a full quarter starting at the step-in date, accrued 0, as the 2016-09-19 6M row shows). For a hand-built 3-month IMM maturity QuantLib's `Actual360(True)` may count one more day than our `accrued_days`; not checked because no plan trade reaches it.
- **Textbook against the ISDA path at a flat-hazard-equivalent λ** (Table 5): Section 7.
- **The upper Brent bound.** `implied_flat_hazard` raises when the quoted spread exceeds the par spread at λ = 5; the raise is not tested because the spread needed is above 25,000 bp.

## Open

Nothing tried and unexplained.

## Against the plan

1. **The plan's criteria 1 and 2 hold for the clean-value spread, not for the par spread item 21 fixed.** Item 21 makes `par_spread_bp` = PV_prot / A with the dirty annuity. At that coupon the dirty upfront is zero (row: mtm +0.000000 $) and the clean upfront is the accrued (+0.1345825773 % = 13.46 bp of notional), so "clean_upfront_pct within 0.01 bp of zero" and "U_dirty + accrued under $1" cannot hold with 86 accrued days. Both hold at the clean-value spread 59.519383 bp (rows above), which is the spread at which the buyer pays no upfront, QuantLib's `fairSpread`, and, in the ISDA C library, the spread `JpmcdsCdsBootstrap` fits with `isPriceClean = TRUE`. The tests assert the item 21 identities at `par_spread_bp` and the plan's two criteria at `clean_par_spread_bp`, and both spreads are reported. Three consequences follow, which item 21 did not weigh: (a) on a flat 1% curve the dirty par spread is 31 / 45 / 52 / 56 / 58 bp on 6M / 1Y / 2Y / 5Y / 10Y while the clean-value spread is 59.5 bp on every tenor, so a market par-spread quote read as a dirty par spread is a different contract on every tenor; (b) Section 6 criterion 2 (flat 100 bp curve → every λ_i within 3% of 1.67%) gives 1.680 to 1.681% under the clean definition and 3.21% at the 6M pillar under the dirty one (rows above); (c) Section 7's bootstrap comparison against `ql.SpreadCdsHelper` (which solves `fairSpread` = quote) would differ by the same 5.6% of spread at 5Y and 91% at 6M, far past `QL_HAZARD_BP = 0.5`. Recommendation: reverse item 21: `par_spread_bp` = the clean-value spread PV_prot / (A − accrued_fraction / D), the conversions calibrate to it, and the Section 6 objective becomes f(λ_i) = PV_prot − s_i · (A − accrued_fraction / D), equivalently D · (PV_prot − s_i · A) + s_i · accrued_fraction = 0. In this code the change is the body of `Valuation.par_spread_bp` (and its docstrings); every test that names the dirty identity would be rewritten to the clean one. Does the reviewer reverse item 21?
2. **`inception_cash` for an `upfront_pct` quote is value / 100 minus the accrued rebated at inception**, not the plan's literal value / 100. The plan says elsewhere that the quoted upfront is clean and the cash paid is dirty (Part A.3, Part B item 2), and `Quote(kind="upfront_pct")` is the same object Section 6 will fill with clean upfronts from `quoted_spread_to_upfront`; reading the trade's quote as the dirty amount paid would make the same field mean two things. With the clean reading a trade quoted at its own clean upfront has mtm 0 on its trade date (tested); with the literal reading it would show −$23,888.89 on the base trade. Accept?
3. **`upfront_to_quoted_spread` is one Brent on the hazard, not a Brent on the spread wrapped around the forward conversion.** The root is the same (the map λ → (s_par, clean upfront) is monotone, so s = s_par(λ*) with U_clean(λ*) = upfront), and it costs about 40 leg evaluations instead of about 1,600. The round-trip rows are the check. Accept?
4. **`price` takes keyword-only `calendar`, `engine`, `half_day_bias`** with the defaults "weekends", "isda", True; the plan's signature is `price(state, trade)`. `CDSTrade` (Part D.1) has no calendar field, so the calendar has to arrive as an argument for the `us_uk` option to exist at all. Accept, or add a `calendar` field to `CDSTrade` through this list?
5. **`price` uses the state's `RecoveryCurve` for the legs and raises if `trade.recovery` differs from it.** The plan gives both objects a recovery. The state's is what Section 8 bumps and re-bootstraps (Part C item 5 needs the pricing R and the bootstrap R to move together); the trade's is what the conversions use, where there is no state. Raising on a mismatch means nothing is silently ignored; Section 8's rec01 will `replace()` both. The alternative, `price` reading `trade.recovery` and ignoring `state.recovery`, would let a bumped state price at the old R. Which does the reviewer want?
6. **`accrued_days` for a seasoned trade** counts from the start of the period containing `as_of` + 1 to `as_of` + 1 (rows above). The `PriceResult.accrued` comment, "accrual start to step-in", is the `as_of` = trade date case of this. Part C item 2 (JTD) wants the accrued "to the valuation date", one day less; Section 8 computes that itself from the schedule. Accept?
7. **Five of the 16 trade dates are weekends** (19 and 20 Mar 2016, 29 Feb 2020, 20 Dec 2020, 20 Sep 2025), where `price()` raises by item 10. Criterion 5's "accrued_days equals QuantLib's for the 16 trade dates" is met at the schedule level on all 16 and through `price()` on the 11 business days; the test asserts the raise on the other five.
8. **Extra public names**: `Valuation`, `value`, `accrued_days`, `cash_settle_date`, `clean_par_spread_bp`, `implied_flat_hazard`, `HAZARD_BOUNDS`; in `textbook`, `survival`, `implied_hazard`, `upfront_pct`. `implied_flat_hazard` is what Section 6's `fallback="upfront"` and Section 7's Table 5 ("the same flat-hazard-equivalent λ") need.
9. **Two tests beyond the plan's list** with their own constants: the QuantLib `fairUpfront` / `fairSpread` / `accrualRebate` / `couponLegNPV` oracle (12 cases, `QL_PRICER_ABS_TOL`) and the flat-hazard tenor comparison (`CLEAN_SPREAD_TENOR_RANGE_BP`, plus a local `DIRTY_6M_FRACTION = 0.6` stated with its reason in the test file). QuantLib is imported in the tests only.
10. **Ten tolerance constants** added to `tests/conftest.py`, more than the plan's table lists for this section; each identity that is a single multiplication shares `PRICER_IDENTITY_ABS_TOL`.
11. **Item 10's business-day check is on the trade date only.** `as_of` may be any calendar date, since Section 8's thetas move it by calendar days with no adjustment (Part D.2); the settlement date is `as_of` + 3 business days whatever `as_of` is.
12. `cds/__init__.py`'s module list still says "None exist yet" (reviews 03 and 04); not in this section's list, left for Section 10.
13. The untracked `11_CDS_Pricing_Bootstrap.docx` at the repo root, noted since review 01, is still there.

## Reviewer reads (max 6, in order)

1. `cds/pricer.py` — the module docstring (rules 1 to 9 above), then `Valuation` (`par_spread_bp` against `clean_par_spread_bp` is question 1 in eight lines), `price`, and the three conversion functions.
2. `tests/test_pricer.py` — `test_par_coupon_gives_zero_dirty_upfront_and_reprices_the_par_spread`, `test_clean_par_coupon_gives_zero_clean_upfront` and `test_clean_par_spread_is_the_same_on_every_tenor_for_a_flat_hazard` (the evidence for question 1), then `test_clean_upfront_and_clean_spread_match_quantlib` at the end.
3. `docs/CONVENTIONS_RESOLVED.md` items 19 to 23 as committed; `BUILD_PLAN.md` Section 4, the rewritten merged-grid sentence.
4. `tests/conftest.py` — the ten new constants and their reasons.
5. `cds/textbook.py` — six functions, one import.
6. `tests/test_legs.py` — `_quantlib_legs` and `test_legs_match_quantlib_on_weekend_maturities`.
