# Review — Section 07 — the pricer, the bootstrap and the 5Y CS01 against QuantLib; Tables 2 and 5

Date: 2026-09-17   Commit: a67d26c   Tests: 323/323 (303 from Sections 1 to 6; 20 new; 0 skipped)

Four commits. `87a9589 Section 07: resolved Section 6 questions` (items 30 to 34 appended to `docs/CONVENTIONS_RESOLVED.md`, as given in the session prompt), `4ba0b8a Section 07: items 30 and 34` (outputs rounded on write, the two "is current" tests made numeric, Section 6 criterion 3 and the DATA_NOTE line rewritten, before any Section 7 code), `a67d26c Section 07: quantlib validation` (code, tests, Tables 2 and 5), and this review.

## What changed

**Items 30 and 34, applied first (`4ba0b8a`).**
- `cds/report.py` — `OUTPUT_DECIMALS = 10`; `rounded(df)` rounds every float column and turns a `-0.0` into `0.0`; `write_table` and the Chart 1 CSV write the rounded frame. Table 1 and Chart 1 regenerated (the CSVs changed in their trailing digits only; the PNG is byte-identical).
- `tests/conftest.py` — `OUTPUT_ABS_TOL = 1e-9` and `assert_output_current(fresh_csv, committed_csv)`: same columns, same row count, text columns equal, float columns within the tolerance. `tests/test_bootstrap.py` — the two "is current" tests use it; the Table 1 Markdown is still compared as text, since it is rendered from the rounded frame at fewer decimals.
- `BUILD_PLAN.md` Section 6 criterion 3 and `docs/DATA_NOTE.md` next to HY_steep, the item 30 wording.

**Section 7 (`a67d26c`).**
- `cds/validation/__init__.py`, `cds/validation/quantlib_check.py` (new) — the only QuantLib import in `cds/`. `Row` (a Table 2 row), `pricer_rows`, `bootstrap_rows`, `cs01_rows`, `validation_rows`; the QuantLib builders `ql_discount_curve`, `ql_hazard_curve`, `ql_cds`, `ql_engine`, `ql_price`, `ql_bootstrap`; `sequential_on_nodes` (our fit on QuantLib's node dates); `hazards_on_grid`; `QL_FLAGS`, `TRADES`, `BUMP_BP`, the `TOL_*` constants.
- `cds/report.py` — `table_2_quantlib_validation(rows)`, `table_5_isda_vs_textbook(results, discount)`, `TABLE_2_COLUMNS`, `TABLE_5_COLUMNS`, `TABLE_5_TENORS`, `TABLE_5_COUPONS_BP`.
- `scripts/make_outputs.py` — `--only table_2`, `--only table_5`; QuantLib imported inside `make_table_2` only.
- `tests/test_quantlib.py` (20 tests); `tests/conftest.py` — `QL_ANNUITY_ABS_TOL = 0.01`, `QL_CS01_REL_TOL = 0.01`, `QL_CS01_ABS_USD = 50.0`.
- `outputs/tables/table_2_quantlib_validation.{csv,md}` (74 rows, 72 pass), `outputs/tables/table_5_isda_vs_textbook.{csv,md}` (9 rows).

**Rules stated in full.** `as_of` = 15 Sep 2026 = QuantLib's `Settings.evaluationDate` throughout; N = 10,000,000; every trade a protection buy at the curve file's recovery; cash settlement 18 Sep 2026, P(t_settle) = 0.999676765.

1. Every QuantLib flag used. Curves: `ql.DiscountCurve(dates, dfs, Actual365Fixed())` on our node dates and discount factors (log-linear), `ql.HazardRateCurve(dates, hazards, Actual365Fixed())` on our pillar dates with the first hazard repeated at `as_of` (backward-flat: λ_i on (t_{i−1}, t_i]), both with extrapolation on. Schedule: `ql.Schedule(step_in, maturity, 3M, WeekendsOnly, Following, Unadjusted, DateGeneration.CDS2015, endOfMonth = False)`. Contract: `ql.CreditDefaultSwap(Protection.Buyer, N, spread = c, schedule, Following, Actual360(), settlesAccrual = True, paysAtDefaultTime = True, protectionStart = step_in, FaceValueClaim(), lastPeriodDayCounter = Actual360(True), rebatesAccrual = True, tradeDate = as_of, cashSettlementDays = 3)`. Engine: `ql.IsdaCdsEngine(prob, R, disc, includeSettlementDateFlows = False, NumericalFix = Taylor, AccrualBias = HalfDayBias, ForwardsInCouponPeriod = Piecewise)`. Helper: `ql.SpreadCdsHelper(quote, Period(tenor), settlementDays = 1, WeekendsOnly, Quarterly, Following, CDS2015, Actual360(), R, disc, settlesAccrual = True, paysAtDefaultTime = True, startDate = Date(), lastPeriodDayCounter = Actual360(True), rebatesAccrual = True, model = CreditDefaultSwap.ISDA)`, which QuantLib prices with `IsdaCdsEngine(…, Taylor, HalfDayBias, Piecewise)` (its `resetEngine`, read from the 1.43 source). Curve: `ql.PiecewiseFlatHazardRate(as_of, helpers, Actual365Fixed())`.
2. Pricer comparison, per unit notional at the cash settlement date: `clean_upfront_pct` against 100·`fairUpfront()` (QuantLib states it at the settlement date already); `par_spread_bp` against 10⁴·`fairSpread()` (the clean-value spread, item 24); `pv_protection` against `defaultLegNPV()` / P(t_settle); `risky_annuity` against −`couponLegNPV()` / c / P(t_settle). Differences in bp of notional, bp, bp of notional and per unit spread; tolerances 1.0, 0.5, 1.0, 0.01.
3. Bootstrap comparison. QuantLib's node for pillar i is its helper's `latestDate` = Following-adjusted maturity + 1 day (the `++latestDate_` for the ISDA model), 1 to 2 days after our node on the maturity itself. Two sets of rows: `trade = "bootstrap"`, our λ_i against the hazard QuantLib's curve carries over our interval, −ln(Q_QL(t_i)/Q_QL(t_{i−1}))/(t_i − t_{i−1}); `trade = "bootstrap_quantlib_nodes"`, our sequential fit (the same objective and contracts, the survival curve's nodes moved to QuantLib's dates) against QuantLib's node hazards. Both in percent, differences in bp of hazard, tolerance 0.5. Then the 5Y contract priced on each side's own bootstrapped curve (`trade = "<5Y>_own_bootstrap"`, `clean_upfront_pct`, tolerance 1 bp of notional).
4. CS01 comparison: the 5Y conventional spread + 1 bp, both sides re-bootstrap from the eight spreads (an upfront-quoted curve is fed back as par-spread quotes at its conventional spreads, Part D.2), the 5Y buy repriced; CS01 = N·Δ(clean upfront per unit notional) on each side (the accrued does not move, so this is the dirty change too). Tolerance max(1% of ours, $50).
5. Table 5: for 1Y, 5Y, 10Y on each curve at the Section 7 coupon (100 on IG, 500 on HY and distressed): ISDA `clean_upfront_pct` and `par_spread_bp` of the pillar contract on the full bootstrapped curve; the textbook model at λ_flat = `implied_flat_hazard` of the pillar's conventional spread on the pillar contract, r = the discount curve's continuously compounded act/365F zero rate to the maturity, T = act/365F years to the maturity, the same R and coupon. `diff_bp` in bp of notional, `diff_par_bp` in bp, both ISDA minus textbook.

## Findings

**Claim (criterion 1): the pricer agrees with QuantLib on our curves to float precision on every trade.**
Number: 20 rows (5 trades × 4 metrics), worst |Δ clean upfront| = 1.0e-11 % of notional = 1.0e-9 bp against `QL_UPFRONT_BP = 1.0`; worst |Δ par spread| = 3.1e-12 bp against 0.5; worst |Δ PV_prot| = 1.1e-12 per unit notional; worst |Δ A| = 9.1e-14 against 0.01. Every row passes.
Rows (curve, trade, ours, QuantLib, Δ):

| IG_flat | 5Y_buy_c100 | clean_upfront_pct | −0.420378628044 | −0.420378628044 | −6.3e-12 |
| IG_flat | 5Y_buy_c100 | par_spread_bp | 90.000000000000 | 90.000000000002 | −1.4e-12 |
| IG_flat | 5Y_buy_c100 | pv_protection | 0.037834076524 | 0.037834076524 | −6.9e-14 |
| IG_flat | 5Y_buy_c100 | risky_annuity | 4.442675169333 | 4.442675169333 | +5.2e-14 |
| IG_flat | 1Y_buy_c100 | clean_upfront_pct | −0.376993187402 | −0.376993187402 | −4.7e-12 |
| IG_flat | 1Y_buy_c100 | par_spread_bp | 49.999999999993 | 49.999999999997 | −3.1e-12 |
| IG_flat | 1Y_buy_c100 | pv_protection | 0.003769931874 | 0.003769931874 | +4.3e-15 |
| IG_flat | 1Y_buy_c100 | risky_annuity | 0.992875263693 | 0.992875263693 | +3.7e-14 |
| IG_flat | 10Y_buy_c100 | clean_upfront_pct | 1.475586889354 | 1.475586889354 | −1.0e-11 |
| IG_flat | 10Y_buy_c100 | par_spread_bp | 120.000000000001 | 120.000000000003 | −1.7e-12 |
| IG_flat | 10Y_buy_c100 | pv_protection | 0.088535213361 | 0.088535213361 | −2.8e-13 |
| IG_flat | 10Y_buy_c100 | risky_annuity | 7.616823335659 | 7.616823335659 | +9.1e-14 |
| HY_steep | 5Y_buy_c500 | clean_upfront_pct | 0.000000000000 | 0.000000000000 | −3.9e-12 |
| HY_steep | 5Y_buy_c500 | par_spread_bp | 500.000000000000 | 500.000000000001 | −9.7e-13 |
| HY_steep | 5Y_buy_c500 | pv_protection | 0.191418741172 | 0.191418741172 | 0 |
| HY_steep | 5Y_buy_c500 | risky_annuity | 4.067263712322 | 4.067263712322 | +6.2e-15 |
| distressed_inverted | 5Y_buy_c500 | clean_upfront_pct | 20.577817596545 | 20.577817596545 | −3.9e-12 |
| distressed_inverted | 5Y_buy_c500 | par_spread_bp | 1200.000000000266 | 1200.000000000269 | −2.7e-12 |
| distressed_inverted | 5Y_buy_c500 | pv_protection | 0.352762587369 | 0.352762587369 | −1.1e-12 |
| distressed_inverted | 5Y_buy_c500 | risky_annuity | 3.178577116966 | 3.178577116966 | +4.0e-15 |

This is the review 05 oracle on the bootstrapped curves instead of hand-built ones; nothing in the pricer layer differs from QuantLib.

**Claim (criterion 2): the bootstraps agree to within 0.06 bp of hazard on every pillar of IG and HY; on distressed_inverted the 1Y and 2Y pillars miss the 0.5 bp bar by 0.04 and 0.01 bp, and the whole of the difference on every curve is where the node sits.**
Number, on our pillar grid: IG worst |Δ| = 0.0039 bp, HY 0.0518 bp, distressed 0.5417 bp (1Y) and 0.5116 bp (2Y), all others ≤ 0.1241 bp. With the nodes matched: worst |Δ| = 4.7e-9 bp on any pillar of any curve, against `BOOTSTRAP_REPRICE_BP = 0.01` (the test asserts this, not only the 0.5 bar). Q at the pillar dates differs by at most 2.5e-6 (IG), 1.3e-5 (HY), 5.3e-5 (distressed).
Rows (pillar, our maturity node, QuantLib's node, our λ %, QuantLib's λ on our interval %, Δ bp | our λ on QuantLib's nodes %, QuantLib's node λ %, Δ bp | Q_ours(t_i), Q_QL(t_i)):

IG_flat:

| 6M | 2026-12-20 | 2026-12-22 | 0.756456 | 0.756456 | +0.0000 | 0.756456329 | 0.756456329 | +9.0e-12 | 0.99801239 | 0.99801239 |
| 1Y | 2027-06-20 | 2027-06-22 | 0.885454 | 0.885472 | −0.0018 | 0.886905858 | 0.886905858 | −1.2e-11 | 0.99361574 | 0.99361565 |
| 2Y | 2028-06-20 | 2028-06-21 | 1.141963 | 1.142003 | −0.0039 | 1.143404335 | 1.143404335 | +5.4e-10 | 0.98230282 | 0.98230235 |
| 3Y | 2029-06-20 | 2029-06-21 | 1.497227 | 1.497258 | −0.0030 | 1.498229741 | 1.498229741 | −5.6e-10 | 0.96770507 | 0.96770431 |
| 4Y | 2030-06-20 | 2030-06-21 | 1.865280 | 1.865313 | −0.0033 | 1.866321576 | 1.866321576 | +2.7e-12 | 0.94982196 | 0.94982090 |
| 5Y | 2031-06-20 | 2031-06-21 | 2.248001 | 2.248037 | −0.0036 | 2.249085953 | 2.249085953 | +2.0e-12 | 0.92870816 | 0.92870679 |
| 7Y | 2033-06-20 | 2033-06-21 | 2.515082 | 2.515110 | −0.0028 | 2.515474914 | 2.515474914 | +9.0e-13 | 0.88308724 | 0.88308544 |
| 10Y | 2036-06-20 | 2036-06-21 | 2.818022 | 2.818056 | −0.0034 | 2.818332064 | 2.818332064 | +5.1e-11 | 0.81143650 | 0.81143402 |

HY_steep:

| 6M | 2026-12-20 | 2026-12-22 | 2.017257 | 2.017257 | +0.0000 | 2.017257387 | 2.017257387 | +4.1e-11 | 0.99470839 | 0.99470839 |
| 1Y | 2027-06-20 | 2027-06-22 | 3.053053 | 3.053253 | −0.0200 | 3.064764226 | 3.064764226 | +1.4e-09 | 0.97968018 | 0.97967920 |
| 2Y | 2028-06-20 | 2028-06-21 | 5.133993 | 5.134510 | −0.0517 | 5.145882562 | 5.145882562 | −7.4e-10 | 0.93052187 | 0.93051612 |
| 3Y | 2029-06-20 | 2029-06-21 | 7.293709 | 7.294103 | −0.0394 | 7.300004368 | 7.300004368 | −2.4e-10 | 0.86506833 | 0.86505957 |
| 4Y | 2030-06-20 | 2030-06-21 | 8.689566 | 8.689894 | −0.0327 | 8.693711898 | 8.693711898 | +2.3e-10 | 0.79307106 | 0.79306044 |
| 5Y | 2031-06-20 | 2031-06-21 | 10.851143 | 10.851660 | −0.0518 | 10.857588875 | 10.857588875 | −1.1e-09 | 0.71151849 | 0.71150528 |
| 7Y | 2033-06-20 | 2033-06-21 | 10.616481 | 10.616576 | −0.0095 | 10.616246235 | 10.616246235 | +7.3e-10 | 0.57523631 | 0.57522452 |
| 10Y | 2036-06-20 | 2036-06-21 | 10.586269 | 10.586356 | −0.0087 | 10.586328350 | 10.586328350 | −7.6e-10 | 0.41859457 | 0.41858490 |

distressed_inverted (the two rows over the bar in bold):

| 6M | 2026-12-20 | 2026-12-22 | 31.534460 | 31.534460 | +0.0000 | 31.534459554 | 31.534459554 | +6.6e-10 | 0.92040642 | 0.92040642 |
| **1Y** | 2027-06-20 | 2027-06-22 | 25.487858 | 25.482441 | **+0.5417** | 25.415196622 | 25.415196622 | −1.2e-10 | 0.81055986 | 0.81058175 |
| **2Y** | 2028-06-20 | 2028-06-21 | 17.870113 | 17.864997 | **+0.5116** | 17.823512474 | 17.823512474 | +1.4e-09 | 0.67758463 | 0.67763770 |
| 3Y | 2029-06-20 | 2029-06-21 | 9.961718 | 9.961022 | +0.0695 | 9.939422027 | 9.939422027 | −1.8e-09 | 0.61333869 | 0.61339098 |
| 4Y | 2030-06-20 | 2030-06-21 | 9.665771 | 9.667011 | −0.1241 | 9.666262916 | 9.666262916 | −1.9e-09 | 0.55682977 | 0.55687035 |
| 5Y | 2031-06-20 | 2031-06-21 | 4.733508 | 4.733588 | −0.0079 | 4.720036564 | 4.720036564 | +4.7e-09 | 0.53108628 | 0.53112456 |
| 7Y | 2033-06-20 | 2033-06-21 | 6.099481 | 6.100649 | −0.1168 | 6.102540315 | 6.102540315 | −1.3e-09 | 0.47001649 | 0.47003936 |
| 10Y | 2036-06-20 | 2036-06-21 | 6.693340 | 6.693839 | −0.0499 | 6.694379086 | 6.694379086 | +1.8e-09 | 0.38443864 | 0.38445159 |

Why the distressed 1Y misses by 0.04 bp: 20 Dec 2026 and 20 Jun 2027 are both Sundays, so QuantLib's 6M and 1Y nodes are 22 Dec and 22 Jun, two days after ours, and the hazard falls 6 points across the 6M node. QuantLib's curve runs the 31.5% 6M hazard for two extra days, so its 1Y contract needs 25.415% on the rest of the year where ours needs 25.488% from day one; averaged over our (20 Dec, 20 Jun] interval that is 25.482% against our 25.488%. The two curves are different piecewise-constant functions that reprice the same eight contracts; neither is wrong. The causes were checked in the Part C item 4 order: schedule (the helper's `earliestDate` is 22 Jun 2026 and its maturities are ours: the 6M hazard, which has no node before it, agrees to 9e-12 bp on every curve), day count (the pricer rows above), accrual-on-default (same), interpolation (this: the node placement, and with it matched the fit agrees to 5e-9 bp), model (nothing left). Against the plan 1.

**Claim (criterion 2, the 5Y price on each side's own bootstrap): within 0.12 bp of notional.**
Rows (curve, trade, ours %, QuantLib % on its own curve, Δ bp of notional, bar 1.0):

| IG_flat | 5Y_buy_c100 | −0.420378628 | −0.420380476 | +0.000185 |
| HY_steep | 5Y_buy_c500 | 0.000000000 | 0.000000000 | −0.000000 |
| distressed_inverted | 5Y_buy_c500 | 20.577817597 | 20.576702232 | +0.111536 |

The HY row is zero on both sides by construction (the 5Y quote is 500 bp at coupon 500; both curves reprice it). The distressed 0.11 bp is the node placement again: the 5Y contract at coupon 500 on an inverted curve is far from par, so the small differences in Q along the way show up in its upfront.

**Claim (criterion 3): the 5Y CS01 agrees to under $0.17 on $10m on every curve.**
Number: worst |Δ| = $0.165 against max(1% of CS01, $50) = $50 on every curve (1% of the CS01 is $28 to $42, so $50 binds).
Rows (curve, trade, our CS01 $, QuantLib's $, Δ $, ours in bp of notional, QuantLib's in bp of notional):

| IG_flat | 5Y_buy_c100 | 4206.930352 | 4206.940278 | −0.009925 | 4.206930 | 4.206940 |
| HY_steep | 5Y_buy_c500 | 3828.119732 | 3828.216058 | −0.096327 | 3.828120 | 3.828216 |
| distressed_inverted | 5Y_buy_c500 | 2818.426931 | 2818.591550 | −0.164620 | 2.818427 | 2.818592 |

**Claim: `settlementDays = 1` is the helper argument that reproduces our contract; 3 would start protection two days late.**
Number: with 1, the 6M hazard (which has no earlier node and so is free of the node-placement effect) agrees to 9e-12 bp on every curve; with 3, it is off by 1.62 bp (IG), 4.31 bp (HY) and 64.9 bp (distressed) against the 0.5 bp bar. Read from the 1.43 source: `CdsHelper::initializeDates` sets `protectionStart_ = evaluationDate_ + settlementDays_` (calendar days) and `SpreadCdsHelper::resetEngine` builds the swap with `tradeDate = evaluationDate_` and the `CreditDefaultSwap` default `cashSettlementDays = 3`, so one argument cannot be both T+1 and T+3, and 1 is the one that matches the contract (our step-in), the cash settlement being 3 by default anyway. Against the plan 2.
Rows (curve, pillar, our λ %, QuantLib's node λ % with settlementDays = 3, Δ bp):

| IG_flat | 6M | 0.756456 | 0.772622 | +1.6166 |
| IG_flat | 1Y | 0.885454 | 0.886723 | +0.1269 |
| HY_steep | 6M | 2.017257 | 2.060307 | +4.3050 |
| HY_steep | 1Y | 3.053053 | 3.064260 | +1.1207 |
| distressed_inverted | 6M | 31.534460 | 32.183650 | +64.9190 |
| distressed_inverted | 1Y | 25.487858 | 25.409243 | −7.8615 |

(The 1Y rows with `settlementDays = 3` also carry the node-placement offset; the 6M rows are the clean comparison.)

**Claim (criterion 4): Tables 2 and 5 are written, every Table 2 row has a `pass` value, and the committed files are what the code produces.**
Table 2: 74 rows = 20 pricer + 3 × (8 + 8 hazard + 1 own-bootstrap + 1 CS01); 72 pass; the 2 that do not are exactly (`distressed_inverted`, `bootstrap`, `hazard_pct_1Y`) and (`…`, `hazard_pct_2Y`), which the test pins. Columns `curve, trade, metric, ours, quantlib, diff, unit, tolerance, pass`. Table 5: 9 rows, columns as the plan. Both regenerated in the test and compared numerically to 1e-9 (item 34). `validation_rows` runs in 0.73 s.

**Claim (Table 5): the textbook model overstates the par spread by 0.4 to 19 bp and misprices the upfront by up to 145 bp of notional; the gaps are the four conventions the ISDA path has and the textbook does not.**
Rows (curve, tenor, coupon, ISDA clean upfront %, textbook upfront %, Δ bp of notional, ISDA par spread, textbook par spread, Δ bp):

| IG_flat | 1Y | 100 | −0.376993 | −0.370420 | −0.6573 | 50.000000 | 50.420679 | −0.4207 |
| IG_flat | 5Y | 100 | −0.420379 | −0.384020 | −3.6358 | 90.000000 | 90.727550 | −0.7276 |
| IG_flat | 10Y | 100 | 1.475587 | 1.510754 | −3.5167 | 120.000000 | 120.963985 | −0.9640 |
| HY_steep | 1Y | 500 | −2.247990 | −2.213245 | −3.4745 | 200.000000 | 201.688833 | −1.6888 |
| HY_steep | 5Y | 500 | 0.000000 | 0.150802 | −15.0802 | 500.000000 | 504.087502 | −4.0875 |
| HY_steep | 10Y | 500 | 5.857239 | 5.886742 | −2.9503 | 600.000000 | 604.888966 | −4.8890 |
| distressed_inverted | 1Y | 500 | 11.547532 | 11.623698 | −7.6166 | 2200.000000 | 2219.488678 | −19.4887 |
| distressed_inverted | 5Y | 500 | 20.577818 | 21.969193 | −139.1376 | 1200.000000 | 1209.987990 | −9.9880 |
| distressed_inverted | 10Y | 500 | 20.730814 | 22.180715 | −144.9901 | 950.000000 | 957.811464 | −7.8115 |

The par spread gap is the credit triangle at the ISDA-calibrated flat hazard against the ISDA clean spread: 0.8% of the spread (365/360 minus the discounting and accrual-on-default terms, review 06). The upfront gap on IG and HY is that 0.8% of coupon times the annuity plus the schedule (a full first coupon, the accrued rebate, quarterly rather than continuous premium). On distressed the gap is 1.4 points: the textbook's single flat hazard cannot see the inverted front end, and the 5Y and 10Y upfronts from the full curve are 1.3 to 1.5 points below the flat-hazard ones (review 06 criterion 6 showed the same 1.3 points between the curve and the flat conversion). The test asserts every ISDA par spread is the pillar's conventional spread and every textbook spread is above it.

## Before / after

| metric | before (`1228a3a`) | after (`a67d26c`) |
|---|---|---|
| tests | 303 | 323 |
| Table 1 hazard_pct, IG 5Y, as committed | 2.2480012529... (17 sig. fig.) | 2.2480012529 (10 decimals) |
| Chart 1 t_years, k = 1 | 0.08333333333333333 | 0.0833333333 |
| Chart 1 PNG | — | byte-identical |
| Table 2 rows / pass | — | 74 / 72 |
| Table 5 rows | — | 9 |
| IG 5Y clean upfront, ours / QuantLib | −0.420379 % | −0.420378628044 / −0.420378628044 |
| IG 5Y CS01, ours / QuantLib | — | $4,206.93 / $4,206.94 |
| HY 5Y hazard, ours / QuantLib (our grid) / QuantLib (its node) | 10.851143 % | 10.851143 / 10.851660 / 10.857589 % |

No pricing number changed in this section; the pricer, bootstrap and outputs are the Section 6 ones, rounded on write.

## Not verified

- **The ISDA C library.** Part C item 4 makes it optional; no Python binding was tried, as the plan says not to spend a session on a build. QuantLib's `IsdaCdsEngine` is documented as reproducing it and is the only reference here.
- **The QuantLib bootstrap on `distressed_arb` under a fallback.** Criterion 2 says "whichever of the curve or its fallback fits"; the distressed curve itself fits, so the fallbacks were not compared. QuantLib's helper would refuse the arbitrage curve (a negative hazard) rather than fall back; not run.
- **The `us_uk` calendar through QuantLib.** Every comparison is on the weekend-only calendar, as the contracts are. A `ql.JointCalendar` comparison would settle the holiday path; not run (the calendar itself was generated from QuantLib in Section 1).
- **Seller-side pricing against QuantLib.** `ql_cds` takes the side, but every Section 7 trade is a buy; `price` negates for a seller (tested in Section 5 against itself, not against QuantLib).
- **QuantLib's `PiecewiseFlatHazardRate` accuracy.** Its default bootstrap accuracy is 1e-12 in the hazard; the matched-node agreement of 5e-9 bp suggests both solvers are at that precision, but QuantLib's tolerance was not set explicitly.
- **Table 5's textbook zero rate.** `discount.zero_rate(T)` is the continuously compounded act/365F rate to the maturity; the textbook model discounts at that single rate, which is the plan's instruction, not a claim that it is the best flat rate for the comparison.

## Open

Nothing tried and unexplained.

## Against the plan

1. **Criterion 2 is not met on `distressed_inverted` at 1Y and 2Y: 0.5417 and 0.5116 bp of hazard against 0.5, on our pillar grid.** IG and HY meet it everywhere (worst 0.0518 bp). The cause is where QuantLib places its nodes (adjusted maturity + 1 day, 22 Dec and 22 Jun against our 20 Dec and 20 Jun, both Sundays) under a 6-point hazard drop; with our fit moved onto QuantLib's nodes every pillar of every curve agrees to 5e-9 bp, and Table 2 carries both comparisons (`trade = "bootstrap"` and `"bootstrap_quantlib_nodes"`). The test asserts the bar on IG and HY, pins the two distressed rows as the only failing rows in Table 2 (and under 2 × the bar), and asserts the matched-node agreement to `BOOTSTRAP_REPRICE_BP` on all three curves. Does the reviewer accept the two rows as explained, or should criterion 2 be restated as the matched-node comparison (in which case the on-our-grid rows stay in Table 2 as information and the `pass` column would read against a bar the reviewer sets)?
2. **`SpreadCdsHelper(settlementDays = 1)`, not 3.** The session prompt said "settlementDays matching our T+3". In QuantLib 1.43 the helper's `settlementDays` sets the protection start (evaluation date + that many calendar days) and the swap it builds keeps `cashSettlementDays = 3` by default; 1 reproduces our step-in and 3 starts protection on 18 Sep, off by 1.6 to 65 bp of hazard at 6M (rows above). The evaluation date is 15 Sep 2026 and the cash settlement is T+3 as the prompt says; only the helper argument differs. Accept?
3. **Table 2 has 16 hazard rows per curve, not 8**, the second eight being the matched-node comparison (`trade = "bootstrap_quantlib_nodes"`); the plan's metric names are kept (`hazard_pct_<pillar>`) and the `trade` column tells them apart. Accept, or move the matched-node rows to this review only?
4. **The pricer rows carry a `pv_protection` tolerance of 1 bp of notional and a `risky_annuity` tolerance of 0.01 per unit spread** (`QL_ANNUITY_ABS_TOL`, new in `tests/conftest.py`; 0.01 is 1 bp of notional at a 100 bp coupon). The plan fixes tolerances for the upfront, the par spread, the hazards and the CS01 but not for the two legs. Accept?
5. **`cs01_usd` is the only CS01 metric in Table 2**; the plan asks for the comparison "in currency and in bp of notional" and fixes the metric set without a bp-of-notional name. The bp-of-notional numbers are in this review (CS01 / N × 10⁴) and the test makes the same comparison both ways. Accept, or add a `cs01_bp_notional` metric?
6. **Table 5's coupons are 100 bp on IG and 500 bp on HY and distressed** (the Section 7 trades' coupons); the plan lists a `coupon_bp` column without saying which. Accept?
7. **`OUTPUT_ABS_TOL` and `assert_output_current` live in `tests/conftest.py`** (item 34 says the tolerance is 1e-9; the helper is the one place the comparison is written). The Markdown files of Tables 1, 2 and 5 are still compared as text, since they are rendered from the rounded frame at 3 to 9 decimals and cannot differ once the CSVs agree. Accept?
8. **`rounded()` writes `0.0` for a difference that rounds to `-0.0`** (Table 2's `diff` column would otherwise show `-0.0` on the pricer rows). Accept?
9. `cds/__init__.py` still says "None exist yet" (reviews 03 to 06); Section 10.
10. The untracked `11_CDS_Pricing_Bootstrap.docx` at the repo root is still there.

## Reviewer reads (max 6, in order)

1. `cds/validation/quantlib_check.py` — the module docstring (every flag, the node-placement paragraph, the `settlementDays` paragraph), then `ql_bootstrap`, `sequential_on_nodes`, `bootstrap_rows`.
2. `outputs/tables/table_2_quantlib_validation.md` — the 74 rows; the two `False` rows are the distressed `bootstrap` 1Y and 2Y (question 1), and the `bootstrap_quantlib_nodes` rows below them are the same pillars matched.
3. `tests/test_quantlib.py` — `test_bootstrap_hazards_match_quantlib_on_our_pillar_grid` (the pinned rows), `test_bootstrap_matches_quantlib_with_the_nodes_matched`, `test_helper_settlement_days_is_the_step_in_not_the_cash_settlement` (question 2).
4. `outputs/tables/table_5_isda_vs_textbook.md` — the 9 rows.
5. `cds/report.py` — `OUTPUT_DECIMALS`, `rounded`, `write_table` (item 34), `table_5_isda_vs_textbook`; `tests/conftest.py` — `assert_output_current`.
6. `docs/CONVENTIONS_RESOLVED.md` items 30 to 34; `BUILD_PLAN.md` Section 6 criterion 3; `docs/DATA_NOTE.md` next to HY_steep.
