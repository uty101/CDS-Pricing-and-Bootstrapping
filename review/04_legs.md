# Review — Section 04 — the premium and protection legs, both engines

Date: 2026-09-16   Commit: 2689bf0   Tests: 208/208 (169 from Sections 1 to 3, 39 new; 0 skipped)

Four commits. The session opened with `5960ed0 Section 04: resolved Section 3
questions` (items 15 to 18 appended to `docs/CONVENTIONS_RESOLVED.md` from the
user's prompt) and `27031a0 Section 04: plan wording, Section 3 criterion 5
(item 15)`, which changed the one word in BUILD_PLAN.md that item 15 asked
for: criterion 5 now reads "continuous from the left at the pillars (λ_i flat
on (t_{i−1}, t_i])". The two edits were meant as one commit; the plan edit
missed the first because `python` on this machine is not on the path outside
`uv run`, and the rule against rewriting history made it a second commit
rather than an amend. Then `2689bf0 Section 04: legs` (code and tests) and
this review.

## What changed

- `cds/legs.py` (new) — `LegValues(annuity_coupon, annuity_accrual, protection, pv_protection)` with an `annuity` property; `leg_values(discount, survival, recovery, schedule, as_of, half_day_bias=True, engine="isda", grid_days=1)`; `par_spread_bp(values)`; `protection_start_date(as_of, step_in)`; the constants `TAYLOR_THRESHOLD = 1e-4`, `ENGINES`. Module constants `ACCRUAL_TIME_SCALE = 365/360` and `HALF_DAY = 0.5/365` are built from `conventions.py`'s two bases, not literals.
- `tests/conftest.py` — three constants: `GRID_CONVERGENCE_RATIO = (1.9, 2.1)` (the plan's band for criterion 3), `HALF_DAY_BIAS_BP = 0.02` (the plan's bar for criterion 4), `QL_LEGS_ABS_TOL = 1e-12` (QuantLib evaluates the same closed form on the same grid; float noise).
- `tests/test_legs.py` (39 tests) — the plan's five criteria, the day-count mixing, identities, input checks, the series-versus-closed-form switch, and a QuantLib `IsdaCdsEngine` oracle on both legs.
- `docs/CONVENTIONS_RESOLVED.md` — items 15 to 18. `BUILD_PLAN.md` — one line, Section 3 criterion 5.

**Rules stated in full.** Symbols as in SPEC section 6; every time is act/365F years from `as_of`.

1. `annuity_coupon` = Σ_j Δ_j · P(t(pay_j)) · Q(t(pay_j − 1 day)), over coupons with pay_j > as_of. Δ_j is the schedule's act/360 fraction (last period + 1 day, Section 1). The first coupon is a full coupon; the accrued before step-in is the pricer's business (Section 5).
2. `protection` = ∫_{t_0}^{T} P(u)(−dQ(u)) with t_0 = t(max(step_in, as_of + 1 day) − 1 day) and T = t(unadjusted maturity). For a new trade valued on its trade date t_0 = 0. `pv_protection` = the same integral with (1 − R(a)) applied at the start a of each grid interval; for a flat recovery it equals (1 − R)·`protection` exactly.
3. `annuity_accrual` = Σ_j ∫_{s_j}^{e_j} (u − tstart_j) P(u)(−dQ(u)) · 365/360, with s_j = t(max(accrual_start_j, effective start) − 1 day), e_j = t(pay_j − 1 day), tstart_j = t(accrual_start_j − 1 day) − 0.5/365 when `half_day_bias` is on, and periods with e_j ≤ s_j skipped. The 365/360 turns act/365F time into an act/360 accrual fraction.
4. `isda` engine: grid = {t_0, T} ∪ discount node times ∪ survival pillar times ∪ {s_j, e_j}, so λ and f are constant on each interval (a, b]. With hhat = ln Q(a) − ln Q(b), fhat = ln P(a) − ln P(b), x = hhat + fhat, τ = b − a: I = hhat/x · (P(a)Q(a) − P(b)Q(b)) and J = hhat/x · τ · ((P(a)Q(a) − P(b)Q(b))/x − P(b)Q(b)); the accrual integrand over the interval is (a − tstart_j)·I + J. When |x| < 1e-4: I = hhat·P(a)Q(a)·(1 − x/2 + x²/6 − x³/24 + x⁴/120) and J = hhat·P(a)Q(a)·τ·(1/2 − x/3 + x²/8 − x³/30), the orders QuantLib uses (its protection series has the x⁴ term, its accrual series does not). Same expressions as the plan's P(a)Q(a)·λ/k·(1 − e^{−kτ}) and P(a)Q(a)·λ·[s_0(1 − e^{−kτ})/k + (1 − (1 + kτ)e^{−kτ})/k²] with k = λ + f, kτ = x, λτ = hhat.
5. `grid` engine: points every `grid_days` calendar days from the protection start date, plus every s_j, e_j and T; I = P(b)·(Q(a) − Q(b)), accrual = ((a + b)/2 − tstart_j)·I, the midpoint rule of the plan. Coupon on survival as rule 1.
6. `par_spread_bp` = 10⁴ · pv_protection / (annuity_coupon + annuity_accrual). Values are per unit notional at `as_of`; the pricer divides by P(t_settle).
7. `leg_values` raises `ValueError` on an unknown engine, `grid_days < 1`, a maturity on or before `as_of`, or any curve whose `as_of` differs from the valuation date (the check the plan gives `price()` in Section 5, applied here as well because the legs are where the times are computed).

Rules 1 to 3 are QuantLib's `IsdaCdsEngine` reading of the ISDA model, taken from `ql/pricingengines/credit/isdacdsengine.cpp` (1.43), which was read for this section. They differ from the plan's letter in three places, all under "Against the plan" below.

## Findings

The contract for every row unless stated: trade date = `as_of` = 15 Sep 2026, 5Y standard maturity 20 Jun 2031, step-in 16 Sep 2026, cash settle 18 Sep 2026, first accrual date 22 Jun 2026 (20 Jun 2026 is a Saturday), accrued days 86, 20 coupon periods, Δ = 91/360 for the first three, 93/360 for the last (92 days + 1). The three curves on the standard pillars from 15 Sep 2026 (6M 20 Dec 2026, then 20 June 2027 to 2036), hazards as intensities: flat 1% at R = 0.40; steep 1%, 2%, …, 8% at R = 0.25; inverted 30%, 25%, 20%, 16%, 13%, 11%, 9%, 8% at R = 0.20. Discount curve: the Section 2 SOFR OIS snapshot. Merged grid for the 5Y contract: 32 points for the `isda` engine (t = 0, 0.013699 (20 Sep, end of the first accrual integral), 0.082192 (1M node), 0.249315 (3M node), 0.263014 (6M pillar), …, 4.761644 (19 Jun 2031), 4.764384 (T)); 1,740 points for the daily grid.

**Leg values per curve per engine** (the plan's rows for this section; per unit notional at 15 Sep 2026, bias "half" = `half_day_bias=True`):

| curve | R | bias | engine | annuity_coupon | annuity_accrual | A | protection | pv_protection | s_par bp |
|---|---|---|---|---|---|---|---|---|---|
| flat | 0.40 | half | isda | 4.4609180213 | 0.0053722701 | 4.4662902914 | 0.0419361529 | 0.0251616918 | 56.336893 |
| flat | 0.40 | half | grid | 4.4609180213 | 0.0053719397 | 4.4662899610 | 0.0419335629 | 0.0251601378 | 56.333418 |
| flat | 0.40 | none | isda | 4.4609180213 | 0.0053140547 | 4.4662320760 | 0.0419361529 | 0.0251616918 | 56.337627 |
| flat | 0.40 | none | grid | 4.4609180213 | 0.0053137279 | 4.4662317492 | 0.0419335629 | 0.0251601378 | 56.334152 |
| steep | 0.25 | half | isda | 4.2461352991 | 0.0197684861 | 4.2659037853 | 0.1548008688 | 0.1161006516 | 272.159564 |
| steep | 0.25 | half | grid | 4.2461352991 | 0.0197672655 | 4.2659025647 | 0.1547912436 | 0.1160934327 | 272.142720 |
| steep | 0.25 | none | isda | 4.2461352991 | 0.0195536368 | 4.2656889359 | 0.1548008688 | 0.1161006516 | 272.173272 |
| steep | 0.25 | none | grid | 4.2461352991 | 0.0195524296 | 4.2656877287 | 0.1547912436 | 0.1160934327 | 272.156426 |
| inverted | 0.20 | half | isda | 2.9834064347 | 0.0655975678 | 3.0490040025 | 0.5140476969 | 0.4112381575 | 1348.762275 |
| inverted | 0.20 | half | grid | 2.9834064347 | 0.0655936496 | 3.0490000843 | 0.5140163837 | 0.4112131070 | 1348.681849 |
| inverted | 0.20 | none | isda | 2.9834064347 | 0.0648837637 | 3.0482901984 | 0.5140476969 | 0.4112381575 | 1349.078108 |
| inverted | 0.20 | none | grid | 2.9834064347 | 0.0648798890 | 3.0482863237 | 0.5140163837 | 0.4112131070 | 1348.997644 |

The coupon-on-survival column is the same in both engines (same formula), the bias only moves `annuity_accrual`, and `pv_protection` = 0.6, 0.75, 0.8 times `protection` on the three curves.

**Claim (criterion 1): `isda` and `grid` (1 day) par spreads agree to 0.1 bp on all three curves, both bias settings.**
Number: worst |Δ| = 0.080 bp (inverted) against the bar `PAR_SPREAD_ENGINE_AGREEMENT_BP = 0.1`; 6 checks.
Rows (curve, bias, s_isda bp, s_grid bp, Δ):

| flat | half | 56.336893 | 56.333418 | −0.003475 |
| flat | none | 56.337627 | 56.334152 | −0.003475 |
| steep | half | 272.159564 | 272.142720 | −0.016845 |
| steep | none | 272.173272 | 272.156426 | −0.016846 |
| inverted | half | 1348.762275 | 1348.681849 | −0.080426 |
| inverted | none | 1349.078108 | 1348.997644 | −0.080464 |

The grid is always low: it takes P at the end of each day, so every day's default probability is discounted a day too far, a relative error of about f/(2·365) = 5.5e-5 on the protection leg, which is 0.074 bp on a 1349 bp spread. That is the whole gap, and it is the reason the inverted curve sits at 80% of the bar: the bar scales with the spread, and the plan's daily grid was specified for it.

**Claim (criterion 2): with zero rates, daily coupons and no accrual on default, s_par = λ(1 − R) to 0.5 bp for λ = 1.67%, R = 0.40.**
Number: |Δ| = 0.0023 bp against the bar `CREDIT_TRIANGLE_BP = 0.5`, both engines. The daily schedule is built in the test: a coupon every calendar day from 15 Sep 2026 for 5·365 days, fractions act/365F (so premium time and curve time agree, which is what makes the triangle an identity), a flat discount curve of P ≡ 1, `half_day_bias=False`, and s = pv_protection / annuity_coupon (the accrual term is left out, not switched off: the engine has no flag for it and `LegValues` reports the two annuity parts separately).
Rows (fractions, engine, annuity_coupon, pv_protection, s bp, λ(1 − R) bp, Δ):

| act/365F | isda | 4.79705066 | 0.04806535 | 100.19771 | 100.20000 | −0.00229 |
| act/365F | grid | 4.79705066 | 0.04806535 | 100.19771 | 100.20000 | −0.00229 |
| act/360 | isda | 4.86367636 | 0.04806535 | 98.82514 | 100.20000 | −1.37486 |
| act/360 | grid | 4.86367636 | 0.04806535 | 98.82514 | 100.20000 | −1.37486 |

The residual 0.0023 bp is the one-day observation lag of the coupon (Q at pay − 1 makes the sum a left Riemann sum of ∫Q). The act/360 rows are the day-count mixing Part A.1 says this section tests: the same daily schedule with act/360 fractions gives a par spread of exactly 360/365 of the act/365F one (ratio to 1e-12, `test_act360_accrual_against_act365f_time_scales_the_par_spread`), i.e. 1.37 bp lower on a 100 bp name, because every coupon is 365/360 larger while the curve times are unchanged.

**Claim (criterion 3): the grid's error against the closed form halves when the step halves.**
Number: ratio |s_grid(2d) − s_isda| / |s_grid(1d) − s_isda| = 1.9885 with the bias on and 1.9885 off, against the band `GRID_CONVERGENCE_RATIO = (1.9, 2.1)`; steep curve, 5Y. The 4-day/2-day ratio (not a criterion) is 1.9854.
Rows (bias, s_isda, s_grid 1d, 2d, 4d, error 1d, error 2d, ratio 2d/1d, ratio 4d/2d):

| half | 272.159564 | 272.142720 | 272.126070 | 272.093062 | −0.016845 | −0.033495 | 1.9885 | 1.9854 |
| none | 272.173272 | 272.156426 | 272.139774 | 272.106764 | −0.016846 | −0.033498 | 1.9885 | 1.9854 |

The ratio is a little under 2 because the 20 coupon boundaries are inserted whatever the step, so the coarse grids carry a few 1-day steps the fine grid does not need.

**Claim (criterion 4): the half-day bias changes the 5Y par spread on the flat curve by under 0.02 bp and in the direction of a larger annuity.**
Number: Δs = −0.000734 bp against the bar `HALF_DAY_BIAS_BP = 0.02`; ΔA = +5.82e-5 (A 4.4662320760 → 4.4662902914), all of it in `annuity_accrual` (0.0053140547 → 0.0053722701); `annuity_coupon` and `protection` are bit-identical between the two settings. Half a day of extra accrual on every default over five years is (0.5/365)·(365/360)·Σ P(−dQ) ≈ 0.00139 · 0.0419 = 5.8e-5, which is the number.

**Claim (criterion 5): both legs are non-negative, and the protection leg rises when any pillar hazard is bumped +10 bp.**
Number: 6 non-negativity checks (3 curves × 2 engines, every field strictly positive); 24 monotonicity checks (3 curves × 8 pillars) on a **10Y** contract (maturity 20 Jun 2036), every Δ > 0. The plan's 5Y contract would give exactly zero for the 7Y and 10Y pillars, whose intervals start after 20 Jun 2031; that is tested separately (`test_pillars_beyond_maturity_do_not_move_a_5y_contract`: the `LegValues` are equal as dataclasses).
Rows (curve, base pv_protection, Δ pv_protection per bumped pillar 6M … 10Y):

| flat | 0.04531159 | +1.45e-4 | +2.70e-4 | +5.24e-4 | +4.97e-4 | +4.74e-4 | +4.52e-4 | +8.42e-4 | +1.12e-3 |
| steep | 0.25766994 | +1.28e-4 | +2.38e-4 | +4.54e-4 | +4.22e-4 | +3.94e-4 | +3.69e-4 | +6.73e-4 | +8.76e-4 |
| inverted | 0.50081586 | +7.76e-5 | +1.41e-4 | +2.64e-4 | +2.40e-4 | +2.21e-4 | +2.06e-4 | +3.74e-4 | +4.87e-4 |

The pattern is the interval lengths (6M: 0.26Y, 1Y: 0.5Y, then 1Y each, 7Y and 10Y: 2Y and 3Y) times (1 − R)·P·Q on the interval, falling with the curve level as survival to the interval falls.

**Claim: the two branches at the Taylor switch agree.** (Not a criterion.)
Number: at x = (λ + f)τ = 1e-4 ± 1e-9 with τ = 1e-3, λ = 5%, the series and the closed form give I to 7.5e-13 relative and J to 5.0e-9 relative, against the bar `TAYLOR_CONTINUITY_REL_TOL = 1e-7` set in the test file. The J gap is the closed form's own rounding, not the series': its bracket (P(a)Q(a) − P(b)Q(b))/x − P(b)Q(b) is a difference of two numbers near 0.855 whose result is 4e-5, so it keeps about 1e-16/x² = 1e-8 of relative precision at the switch. This is the reason the series exists, and 1e-4 is where QuantLib switches. Also checked: λ = 0 on a zero-rate curve (x = 0 on every interval) gives protection and accrual exactly 0 with no NaN, and annuity_coupon equal to ΣΔ_j (`test_zero_hazard_and_zero_rate_give_zero_protection_without_nan`).

**Claim: the legs are QuantLib's `IsdaCdsEngine` legs.** (Not a plan criterion for this section; Section 7 owns the full comparison. Added because rules 1 to 3 were taken from the engine's source, and the check is what shows they were taken correctly.) `ql.CreditDefaultSwap(Buyer, 1.0, 100 bp, Schedule(step_in, maturity, 3M, WeekendsOnly, Following, Unadjusted, CDS2015), Following, Actual360(), settlesAccrual=True, paysAtDefaultTime=True, protectionStart=step_in, FaceValueClaim, Actual360(True), rebatesAccrual=True, tradeDate)` priced with `IsdaCdsEngine(HazardRateCurve, R, DiscountCurve(LogLinear), Taylor, HalfDayBias|NoBias, Piecewise)`; compared: `−couponLegNPV()/spread` against `A` and `defaultLegNPV()` against `pv_protection`.
Number: 12 cases (3 curves × 5Y, 10Y × 2 bias settings), worst |ΔA| = 9.1e-14, worst |Δ pv_protection| = 1.1e-16, against the bar `QL_LEGS_ABS_TOL = 1e-12`.
Rows (tenor, curve, bias, A QuantLib, A ours, Δ, pv_protection QuantLib, ours, Δ):

| 5Y | flat | half | 4.4662902914 | 4.4662902914 | +5.3e-14 | 0.0251616918 | 0.0251616918 | +6.9e-18 |
| 5Y | steep | none | 4.2656889359 | 4.2656889359 | +5.0e-14 | 0.1161006516 | 0.1161006516 | −2.8e-17 |
| 5Y | inverted | half | 3.0490040025 | 3.0490040025 | +4.5e-14 | 0.4112381575 | 0.4112381575 | +5.6e-17 |
| 10Y | flat | none | 7.8511594458 | 7.8511594458 | +9.1e-14 | 0.0453115935 | 0.0453115935 | +6.9e-18 |
| 10Y | steep | half | 6.7942627659 | 6.7942627659 | +8.3e-14 | 0.2576699415 | 0.2576699415 | +5.6e-17 |
| 10Y | inverted | none | 4.3793017097 | 4.3793017097 | +6.3e-14 | 0.5008158582 | 0.5008158582 | −1.1e-16 |

The 1e-14 on A is the accumulation order of 20 to 40 coupon terms. The agreement is to the float, on both bias settings, which means the three day-convention choices under "Against the plan" are QuantLib's and not a rounding coincidence: a one-day change in any of them moves the inverted-curve annuity by about 1e-3.

## Before / after

Nothing numerical existed before this section for the legs. Curves and schedules from Sections 1 to 3 are unchanged (their tests pass on the same objects). Numbers to hold onto for Section 5: on the flat 1% / R = 0.40 curve the 5Y contract from 15 Sep 2026 has A = 4.4662902914, PV_prot = 0.0251616918 per unit notional at the valuation date, par spread 56.336893 bp (with the half-day bias, `isda`). For Section 7: the legs already match `IsdaCdsEngine` to 1e-13, so any Section 7 gap of the plan's size (0.5 bp) will be in the pricer's settlement discounting, accrued or upfront conversion, not the legs.

## Not verified

- **The first-order convergence on the flat and inverted curves.** Criterion 3 names the steep curve and the test follows it; the 1-day and 2-day errors on the other two are in the criterion 1 rows and the scratch run (flat 1.988, inverted 1.988) but not asserted. What would settle it: parametrise the test over the three curves.
- **Seasoned trades (as_of after the trade date).** `protection_start_date` and `_accrual_periods` implement QuantLib's `max(protectionStart, evalDate + 1)` and skip coupons with pay ≤ as_of, and the pure-function cases are tested, but no leg value for a trade valued after its trade date is compared with anything. Section 8's thetas are the first use. What would settle it: the QuantLib oracle test with `Settings.evaluationDate` moved a month past the trade date. Note QuantLib's own coupon inclusion rule is `hasOccurred(effectiveProtectionStart)` with `includeSettlementDateFlows` unset, which excludes a coupon paying on as_of + 1 as well; ours counts it. A coupon on the day after the valuation date does not occur for the plan's dates (the 1-day and 1-month thetas from 15 Sep 2026 sit at 16 Sep and 15 Oct; the next payment is 21 Dec 2026), and which is right is a Section 8 question.
- **Recovery term structures.** `pv_protection` applies (1 − R(a)) at each interval start as the plan says; only the flat curve exists, so this is tested as the identity (1 − R)·protection.
- **Weekend maturities.** When the unadjusted maturity is a Saturday, QuantLib's accrual integral for the last period ends at pay − 1 = Sunday = maturity + 1, one day past the protection end; the grid covers it (`t_end = max(T, e_last)`) and the sums use index ranges, but no test has such a maturity (20 Jun 2031 is a Friday; 20 Jun 2036 a Friday). What would settle it: the oracle test on a maturity of 20 Dec 2031 (a Saturday) or 20 Sep 2031 (a Saturday).
- **The `us_uk` calendar path.** Unchanged from the earlier reviews' lists; the legs take whatever payment dates the schedule carries.
- **Negative x in the Taylor branch.** The series is used for |x| < 1e-4, so a large negative x (negative rates exceeding the hazard over an interval) takes the closed form, which is right; QuantLib's condition is `fhphh < 1E-4` unsigned, so it would use the series there. Only a curve with rates below −λ would tell them apart, and none exists in this repo.

## Open

Nothing tried and unexplained.

## Against the plan

1. **Protection integrates from the valuation date, not from step-in.** The plan says the merged grid is "restricted to (t_stepin, T]". QuantLib's `IsdaCdsEngine` (the Section 7 oracle, which the plan says to follow where its reading of the ISDA model is in its source) starts the protection integral at `effectiveProtectionStart − 1` with `effectiveProtectionStart = max(protectionStart, evalDate + 1)`, i.e. at the end of the day before step-in: for a new trade, the valuation date, t = 0. The ISDA model observes every date at end of day, so "protection from the start of the step-in day" is the end of the day before. One day of hazard is 3e-5 of protection on the flat curve (0.004 bp of par spread) but 8e-4 on a 30% hazard (3 bp on the distressed curve of Section 6), which is past the 0.5 bp bar Section 7 has to meet. Implemented as QuantLib does; the oracle rows show the match. Does the reviewer accept QuantLib's limits as the ISDA reading, or want the plan's (t_stepin, T] and a Section 7 tolerance to absorb the difference?
2. **The coupon on survival takes Q one day before the payment date**, Q(t(pay_j − 1)), not Q(t_j^acc_end) as the plan writes. Same source and reason. For the standard schedule the two dates differ by one day (accrual end = payment date for every period but the last, where accrual end is the unadjusted maturity and payment is the adjusted one). On the inverted curve the difference is 1.4e-3 of the annuity, 2 bp of par spread; on the flat curve 0.003 bp.
3. **The accrual-on-default integral's limits and origin are QuantLib's**: from max(accrual_start, effective start) − 1 day to pay − 1 day, with the accrual measured from t(accrual_start − 1 day) minus the half day. The plan's "s_0 = a − t_{j−1} (+ 0.5/365 if half_day_bias)" has the same sign (the accrued time grows by half a day; QuantLib subtracts the half day from tstart) and the same 365/360 scaling; the one-day shifts of the origin and the limits are the ISDA end-of-day convention again. Together items 1 to 3 are what makes the oracle rows agree to 1e-13.
4. **`LegValues` has a fourth field, `pv_protection`.** The plan gives three, `(annuity_coupon, annuity_accrual, protection)`, with PV_prot = (1 − R)·protection, and separately says "recovery enters only as (1 − R(t)) at the interval start". With the signature taking a `RecoveryCurve`, the engine is the place that can apply R(t) per interval, so it reports both: `protection` (no recovery, the plan's field) and `pv_protection` (with it). `par_spread_bp` uses the second. The Part D.1 objects in `types.py` are untouched.
5. **The 10Y contract for the monotonicity checks** (criterion 5 says "8 checks per curve"; on the plan's 5Y contract two of the eight would be equalities, see the criterion 5 rows). The 5Y case is tested as the equality it is.
6. **The credit-triangle schedule uses act/365F daily fractions.** The plan's criterion 2 asks for a "daily coupon schedule (continuous premium)" and s = λ(1 − R) to 0.5 bp. With the contract's act/360 fractions on act/365F curve time the identity is off by the factor 360/365, 1.37 bp at 100 bp: not a bug, the mixing Part A.1 calls intended. The test therefore uses act/365F fractions for the identity and a second test asserts the 360/365 factor exactly. If the reviewer would rather the criterion be met with act/360 fractions, the bar would need to be 1.4 bp or the identity restated as λ(1 − R)·360/365.
7. **The as_of check is in `leg_values` as well as (later) in `price()`.** The plan puts it in Section 5's `price`. The legs compute every time from `as_of`, so a curve on another date would silently give wrong times; raising here costs nothing and Section 5 will still raise at its own level.
8. **Extra public names**: `par_spread_bp`, `protection_start_date`, `LegValues.annuity`, `TAYLOR_THRESHOLD`, `ENGINES`. The test imports the private `_isda_intervals` for the switch check.
9. **One test beyond the plan's list**, the QuantLib oracle, with its own constant `QL_LEGS_ABS_TOL`. QuantLib is imported in the test only, as in Sections 1 to 3. It uses the Section 7 flags (`Taylor`, `HalfDayBias`/`NoBias`, `Piecewise`) and compares leg NPVs, not `fairSpread` — QuantLib's `fairSpread` divides by `couponLegNPV + accrualRebateNPV`, i.e. it is the spread at which the *clean* value is zero, about 5% away from PV_prot/A on this trade (86 days of accrued); Section 7 should compare `fairUpfront` or the leg NPVs, not `fairSpread`, and the plan's "0.5 bp of par spread" should be read against PV_prot/A computed from QuantLib's legs.
10. **`grid_days` is honoured only by the `grid` engine**; the `isda` engine ignores it, as the plan implies.
11. `cds/__init__.py`'s module list still says "None exist yet" (review 03 item 7). Not in this section's file list; left for Section 10.
12. The stray `11_CDS_Pricing_Bootstrap.docx` at the repo root, noted in reviews 01 to 03, is still there and still untracked.

## Reviewer reads (max 6, in order)

1. `cds/legs.py` — the module docstring (the three day conventions and the two closed forms), then `_accrual_periods`, `_isda_intervals`, and the accrual loop at the end of `leg_values`.
2. `tests/test_legs.py` — criteria 1 to 5 in file order, then `test_legs_match_quantlib_isda_engine` at the end (the construction of the QuantLib trade is the thing to check against Section 7's plan).
3. `tests/conftest.py` — the three new constants and their reasons.
4. `docs/CONVENTIONS_RESOLVED.md` — items 15 to 18 as committed; `BUILD_PLAN.md` Section 3 criterion 5, the one-line edit.
