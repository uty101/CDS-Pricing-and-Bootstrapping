# Review — Section 06 — the bootstrap, the four illustrative curves, Table 1 and Chart 1

Date: 2026-09-17   Commit: 99deeda   Tests: 303/303 (279 from Sections 1 to 5, unchanged in number by the item 24 rewrite; 24 new; 0 skipped)

Four commits. `98ed8a0 Section 06: resolved Section 5 questions` (items 24 to 29 appended to `docs/CONVENTIONS_RESOLVED.md`, as given in the session prompt; issue #5 had no comments), `4ec5b80 Section 06: item 24, clean par spread` (the par spread definition reversed, before any Section 6 code; before/after rows below), `99deeda Section 06: bootstrap` (code, data, outputs, tests), and this review.

## What changed

**Item 24, applied first (`4ec5b80`).**
- `cds/pricer.py` — `Valuation.par_spread_bp` is now 10⁴ · PV_prot / (A − accrued_fraction / D), the clean-value spread (QuantLib's `fairSpread`); the former body PV_prot / A is `Valuation.dirty_par_spread_bp`. The function `clean_par_spread_bp(state, trade)` is removed (it duplicated `price().par_spread_bp`). The conversions' code is unchanged: `implied_flat_hazard` calibrates to `par_spread_bp`, which is now the clean spread; `upfront_to_quoted_spread` returns it. Module docstring rewritten.
- `cds/legs.py` — `par_spread_bp(values)` renamed `dirty_par_spread_bp(values)`; body and value unchanged (PV_prot / A of the leg values, no settlement factor, no accrued). Outside the section's file list; the rename is the only change (Against the plan 5).
- `tests/test_pricer.py` — the three tests that asserted the dirty identity rewritten: `test_par_coupon_gives_zero_clean_upfront_and_reprices_the_par_spread` (criteria 1 and 2 at `par_spread_bp`), `test_dirty_par_coupon_gives_zero_dirty_upfront` (the companion identity at `dirty_par_spread_bp`), `test_par_spread_is_the_same_on_every_tenor_for_a_flat_hazard`; the QuantLib oracle now asserts `price().par_spread_bp` = `fairSpread`. `tests/test_legs.py` — the nine leg-level calls renamed, two test names, one comment. `tests/conftest.py` — two comments (`PAR_UPFRONT_BP`, `PAR_SPREAD_REPRICE_BP`) reworded; values unchanged.
- `BUILD_PLAN.md` — Section 5 rules (the s_par line) and criteria 1 and 2; Section 6 objective and criterion 2; Part A.4 Method row (Against the plan 9).

**Section 6 (`99deeda`).**
- `cds/bootstrap.py` (new) — `bootstrap(quotes, discount, fallback=None, *, calendar, engine, half_day_bias) -> BootstrapResult`; `BootstrapArbitrageError(pillar, spread_bp, f_at_zero, index)`; `BootstrapResult`; `conventional_spreads_bp`, `pillar_trade`, `market_state`, `read_curve_file`, `market_curve_quotes_from_file`, `write_curve_file`; `FALLBACKS = ("flat_from_shortest", "upfront")`.
- `cds/report.py` (new) — `table_1_hazard_curves(results, out_dir)`, `chart_1_survival_hazard(results, out_dir)`, `write_table`, `markdown_table`; `TABLE_1_COLUMNS`, `CHART_1_COLUMNS`, `TABLES_DIR`, `CHARTS_DIR`. Agg backend.
- `scripts/make_outputs.py` (new) — `--only table_1 | chart_1`, `--list`; loads the rates file and the four curve files, bootstraps each with `fallback="upfront"`, checks every curve's `as_of` is the rates file's.
- `scripts/make_curves.py` (new, Against the plan 6) — writes the four curve files; derives the distressed upfronts and finds the `distressed_arb` level.
- `data/curves/IG_flat.json`, `HY_steep.json`, `distressed_inverted.json`, `distressed_arb.json` (new); `data/curves/README.md` and `docs/DATA_NOTE.md` updated.
- `tests/test_bootstrap.py` (24 tests); `tests/conftest.py` — `UPFRONT_CURVE_VS_FLAT_BP = 0.01`, `UPFRONT_CURVE_VS_FLAT_HY_MIN_BP = 1.0`.
- `outputs/tables/table_1_hazard_curves.{csv,md}` (32 rows), `outputs/charts/chart_1_survival_hazard.{png,csv}` (363 rows).

**Rules stated in full.** Symbols as in SPEC section 6; `as_of` = the rates snapshot date 15 Sep 2026; pillar dates = `standard_maturity(as_of, tenor)`; D and accrued_fraction as in Section 5.

1. Conventional spread s_i: the quote for a `par_spread_bp` curve; `upfront_to_quoted_spread(discount, trade_i, upfront)` at the stated coupon for an `upfront_pct` curve, trade_i = a buyer contract from `as_of` to pillar i at the curve's recovery.
2. Objective for pillar i, earlier hazards fixed: f(λ_i) = D · (PV_prot − s_i · A) + s_i · accrued_fraction, the clean value per unit notional at settlement of trade_i at coupon s_i, = `value(...).clean_upfront` with the survival curve on pillars 1..i (item 24). f = 0 exactly when `price().par_spread_bp` = s_i. Nothing after t_i enters f (tested: the first four HY hazards from a four-pillar curve equal the full curve's).
3. Arbitrage: f(0) is evaluated first. f(0) < 0 → `brentq` on [0, 5], xtol 1e-12. f(0) ≥ 0 → `BootstrapArbitrageError(pillar, s_i, f(0), index)` whose message names both fallbacks. f(5) < 0 → `ValueError` (spread beyond the hazard bound).
4. Fallbacks apply only when the sequential fit raises (Against the plan 2): `"flat_from_shortest"` = `implied_flat_hazard` of the shortest pillar, one hazard on every pillar, a joint `SurvivalCurve`; `"upfront"` = `implied_flat_hazard` per pillar on its own maturity, `survival = None`, `survival_for_pillar(i)` the one-pillar flat curve. `method` records which.
5. `BootstrapResult(quotes, pillar_dates, conventional_spreads_bp, method, pillar_hazards, survival, f_at_zero, arbitrage_pillar)`; `f_at_zero` holds every f(0) the sequential fit evaluated, `None` past the failing pillar (Against the plan 4).
6. Curve files: Part D.3 format; `read_curve_file` requires every key, a non-empty `source`, `note`, `label`, `as_of`, one quote kind, `coupon_bp` and one `conventional_spread_bp` per pillar for upfront curves, `null` for spread curves.
7. Table 1: one row per (curve, pillar), columns exactly as the plan; `survival_prob` = Q(t_i) of `survival_for_pillar(i)`; `cum_default_prob` = 1 − that. Chart 1: Q(t) and λ(t) on 0 to 10Y for the three named curves; CSV on t = k/12, k = 0..120.

## Findings

The base numbers unless stated: discount = the Section 2 snapshot; `as_of` = 15 Sep 2026; pillar dates 20 Dec 2026, 20 Jun 2027, 20 Jun 2028, 20 Jun 2029, 20 Jun 2030, 20 Jun 2031, 20 Jun 2033, 20 Jun 2036 (act/365F times 0.263014, 0.761644, 1.764384, 2.764384, 3.764384, 4.764384, 6.767123, 9.769863); every pillar contract has 86 accrued days, D = 1.000323339127.

**Claim (criterion 1): each bootstrapped curve reprices every pillar's conventional spread to within 0.01 bp.**
Number: 24 rows (3 curves × 8 pillars), worst |Δ| = 6.7e-10 bp against `BOOTSTRAP_REPRICE_BP = 0.01`; every f(0) < 0, every λ_i > 0. A bootstrap takes 0.14 to 0.19 s for a spread curve and 0.43 s for the upfront curve (8 conversions first).
Rows (pillar, s_i bp, f(0) per unit notional, λ_i %, Q(t_i), `price().par_spread_bp` at coupon s_i, Δ bp):

IG_flat (R = 0.40):

| 6M | 45 | −1.187876e-03 | 0.756456 | 0.998012 | 45.000000000 | −1.5e-12 |
| 1Y | 50 | −2.588581e-03 | 0.885454 | 0.993616 | 50.000000000 | −6.6e-12 |
| 2Y | 60 | −6.460254e-03 | 1.141963 | 0.982303 | 60.000000000 | +3.3e-13 |
| 3Y | 70 | −7.964641e-03 | 1.497227 | 0.967705 | 70.000000000 | +5.7e-14 |
| 4Y | 80 | −9.324101e-03 | 1.865280 | 0.949822 | 80.000000000 | −2.8e-14 |
| 5Y | 90 | −1.053375e-02 | 2.248001 | 0.928708 | 90.000000000 | +4.8e-13 |
| 7Y | 105 | −2.148731e-02 | 2.515082 | 0.883087 | 105.000000000 | +2.8e-14 |
| 10Y | 120 | −3.046874e-02 | 2.818022 | 0.811436 | 120.000000000 | +1.3e-12 |

HY_steep (R = 0.25):

| 6M | 150 | −3.959586e-03 | 2.017257 | 0.994708 | 150.000000000 | +1.1e-11 |
| 1Y | 200 | −1.111078e-02 | 3.053053 | 0.979680 | 200.000000000 | −5.7e-13 |
| 2Y | 300 | −3.562448e-02 | 5.133993 | 0.930522 | 300.000000000 | +3.4e-13 |
| 3Y | 380 | −4.552561e-02 | 7.293709 | 0.865068 | 380.000000000 | +1.1e-13 |
| 4Y | 440 | −4.800797e-02 | 8.689566 | 0.793071 | 440.000000000 | −2.3e-13 |
| 5Y | 500 | −5.220446e-02 | 10.851143 | 0.711518 | 500.000000000 | +1.1e-13 |
| 7Y | 560 | −8.500342e-02 | 10.616481 | 0.575236 | 560.000000000 | 0 |
| 10Y | 600 | −9.111867e-02 | 10.586269 | 0.418595 | 600.000000000 | −3.4e-13 |

distressed_inverted (R = 0.20, upfront-quoted at 500 bp; s_i is the conversion of the stored upfront and equals the stored spread to 1e-9 bp, criterion 5 rows below):

| 6M | 2500 | −6.599310e-02 | 31.534460 | 0.920406 | 2500.000000001 | +2.4e-10 |
| 1Y | 2200 | −9.208625e-02 | 25.487858 | 0.810560 | 2200.000000000 | +4.6e-13 |
| 2Y | 1800 | −1.124790e-01 | 17.870113 | 0.677585 | 1800.000000001 | +6.7e-10 |
| 3Y | 1500 | −5.089647e-02 | 9.961718 | 0.613339 | 1500.000000000 | −2.3e-13 |
| 4Y | 1350 | −4.237240e-02 | 9.665771 | 0.556830 | 1350.000000001 | +2.3e-13 |
| 5Y | 1200 | −1.827997e-02 | 4.733508 | 0.531086 | 1200.000000000 | +3.1e-10 |
| 7Y | 1050 | −4.272156e-02 | 6.099481 | 0.470016 | 1050.000000000 | +2.8e-11 |
| 10Y | 950 | −5.570917e-02 | 6.693340 | 0.384439 | 950.000000000 | +4.6e-13 |

These 24 rows are Table 1's first 24 (the `hazard_pct`, `survival_prob` columns), which the test regenerates into a temporary directory and compares with the committed CSV and MD byte for byte.

**Claim (criterion 2): a flat 100 bp curve at R = 0.40 gives every λ_i within 3% of 1.67%.**
Number: λ_i from 1.679797% to 1.681039%, i.e. +0.79% to +0.86% above s / (1 − R) = 1.666667%, against `FLAT_HAZARD_REL_TOL = 0.03`; the spread across pillars is 0.0012 percentage points. Under the dirty definition the 6M pillar would have been 3.21% (review 05); item 24 is what makes this criterion hold.
Rows (pillar, f(0), λ_i %, λ_i / 1.666667 − 1, Q(t_i), repriced bp):

| 6M | −2.639724e-03 | 1.681039 | +0.862% | 0.995588 | 100.000000000 |
| 1Y | −4.901515e-03 | 1.680536 | +0.832% | 0.987281 | 100.000000000 |
| 2Y | −9.449808e-03 | 1.680041 | +0.802% | 0.970788 | 100.000000000 |
| 3Y | −8.845048e-03 | 1.679797 | +0.788% | 0.954617 | 100.000000000 |
| 4Y | −8.306157e-03 | 1.680103 | +0.806% | 0.938712 | 100.000000000 |
| 5Y | −7.809128e-03 | 1.680158 | +0.809% | 0.923072 | 100.000000000 |
| 7Y | −1.437095e-02 | 1.680055 | +0.803% | 0.892530 | 100.000000000 |
| 10Y | −1.856902e-02 | 1.679807 | +0.788% | 0.848627 | 100.000000000 |

The 0.8% excess over the triangle is the act/360 coupon on act/365F time (365/360 − 1 = 1.4%, review 04) partly offset by discounting and the accrual-on-default term; the review 05 flat-hazard column showed the same 1.680 to 1.681%.

**Claim (criterion 3): IG and HY fit with every λ_i > 0; HY is strictly increasing through the 5Y pillar and not beyond.**
Number: IG rises on every pillar (0.756 → 2.818%). HY rises 2.017 → 10.851% from 6M to 5Y, then **falls** to 10.616% at 7Y and 10.586% at 10Y. The plan's bar, "strictly increasing for HY", is not met at two of the seven steps (rows above; Against the plan 1). The test asserts positivity, the strict rise through 5Y, and pins the dip so it cannot change silently.
Why: the forward hazard on (5Y, 7Y] is what 560 bp at 7Y needs over and above the 500 bp already bought to 5Y. With A(7Y) ≈ 5.0 and A(5Y) ≈ 3.9 the extra premium is roughly 560 · 5.0 − 500 · 3.9 = 850 bp·yr for two years of protection on the surviving 71%, i.e. about 425 bp a year of spread on the forward, which at R = 0.25 is a forward hazard near 10.6%, below the 10.85% on (4Y, 5Y]. The specified long end (500 → 560 → 600) flattens faster than the front steepens. Alternatives, so the reviewer can choose without a re-run (levels → λ %):

| 500, 560, 600 (as specified) | 10.8511, 10.6165, 10.5863 | not increasing |
| 500, 570, 640 | 10.8511, 11.2889, 13.2358 | increasing |
| 500, 580, 660 | 10.8511, 11.9682, 14.3113 | increasing |

**Claim (criterion 4): the distressed curve fits (all λ_i > 0), so `distressed_arb.json` is committed and raises; the pinned pillar is 1Y; both fallbacks reprice as the plan says.**
Number: the distressed levels fit with hazards 31.5, 25.5, 17.9, 10.0, 9.7, 4.7, 6.1, 6.7% (rows above), close to Part B item 6's hand estimate (31, 23, 17, 9, 10, 5, 6, 7). Raising the 6M pillar in 500 bp steps, the 1Y f(0) crosses zero between 5500 and 6000 bp; at 6000 bp `bootstrap` raises `BootstrapArbitrageError(pillar="1Y", index=1, spread_bp=2200, f_at_zero=+2.327082e-03)`. The test pins `ARB_PILLAR = "1Y"`, `ARB_6M_SPREAD_BP = 6000`.
Rows (6M spread, outcome, 1Y f(0), 1Y λ %, 6M λ %):

| 2500 | fits | −9.208625e-02 | 25.4879 | 31.5345 |
| 3000 | fits | −7.793460e-02 | 21.7368 | 37.8451 |
| 3500 | fits | −6.401025e-02 | 17.9902 | 44.1571 |
| 4000 | fits | −5.030956e-02 | 14.2480 | 50.4703 |
| 4500 | fits | −3.682897e-02 | 10.5099 | 56.7848 |
| 5000 | fits | −2.356497e-02 | 6.7761 | 63.1006 |
| 5500 | fits | −1.051408e-02 | 3.0463 | 69.4176 |
| 6000 | raises at 1Y | +2.327082e-03 | — | 75.7359 |

The error message: "pillar 1Y at 2200.0000 bp needs a negative hazard: the clean value at lambda = 0 is +2.327082e-03 per unit notional, so the earlier pillars already deliver more protection than the spread pays for. Fallbacks: bootstrap(..., fallback='flat_from_shortest') fits one flat hazard to the shortest pillar; fallback='upfront' prices each pillar off its own flat hazard."

Fallbacks on `distressed_arb` (pillar, s_i, sequential f(0), `flat_from_shortest` λ %, its repriced spread, Δ bp, `upfront` λ %, its repriced spread, Δ bp, Q(t_i) under `upfront`):

| 6M | 6000 | −1.583834e-01 | 75.735882 | 6000.000000 | +1.5e-11 | 75.735882 | 6000.000000000 | +1.5e-11 | 0.819389 |
| 1Y | 2200 | +2.327082e-03 | 75.735882 | 6000.957094 | +3801 | 27.743608 | 2200.000000000 | +5.9e-12 | 0.809525 |
| 2Y | 1800 | not reached | 75.735882 | 6001.874811 | +4202 | 22.692859 | 1800.000000000 | +7.3e-12 | 0.670059 |
| 3Y | 1500 | not reached | 75.735882 | 6002.235599 | +4502 | 18.907604 | 1500.000000000 | −8.4e-12 | 0.592930 |
| 4Y | 1350 | not reached | 75.735882 | 6002.306453 | +4652 | 17.016055 | 1350.000000000 | −5.1e-11 | 0.527003 |
| 5Y | 1200 | not reached | 75.735882 | 6002.326671 | +4802 | 15.124850 | 1200.000000000 | −5.1e-11 | 0.486457 |
| 7Y | 1050 | not reached | 75.735882 | 6002.346876 | +4952 | 13.233634 | 1050.000000000 | −4.0e-11 | 0.408389 |
| 10Y | 950 | not reached | 75.735882 | 6002.354095 | +5052 | 11.972643 | 950.000000000 | +3.8e-12 | 0.310457 |

`flat_from_shortest` reprices the 6M pillar to 1.5e-11 bp and nothing else (the test asserts the 1Y is off by more than 0.01 bp; it is off by 3,801 bp, since one 75.7% hazard prices every tenor near 6000 bp); `upfront` reprices all eight to under 1e-10 bp. These eight `upfront` rows are Table 1's last eight (Against the plan 3). With either fallback named, `IG_flat` still returns `method = "bootstrap"` with the same hazards (tested for both).

**Claim (criterion 5): converting the distressed conventional spreads to upfronts and back reproduces the spreads to 1e-6 bp.**
Number: 16 rows (both upfront files), worst |Δ| = 5.4e-10 bp against `CONVERSION_ROUNDTRIP_BP = 1e-6`; the stored upfronts equal `quoted_spread_to_upfront` of the stored spreads exactly (Δ = 0, they were written by it; full precision kept for this reason, Against the plan 12), and `conventional_spreads_bp()` of each file equals the stored spreads to the same bar.
Rows (curve, pillar, stored spread, stored upfront %, spread → upfront, Δ, upfront → spread, Δ bp):

| distressed_inverted | 6M | 2500 | 5.069353685 | 5.069353685 | 0 | 2500.000000000 | +2.9e-10 |
| distressed_inverted | 1Y | 2200 | 11.601336707 | 11.601336707 | 0 | 2200.000000000 | +7.7e-12 |
| distressed_inverted | 2Y | 1800 | 18.410749268 | 18.410749268 | 0 | 1800.000000000 | +8.0e-12 |
| distressed_inverted | 3Y | 1500 | 20.558945590 | 20.558945590 | 0 | 1500.000000000 | −4.1e-10 |
| distressed_inverted | 4Y | 1350 | 22.141928122 | 22.141928122 | 0 | 1350.000000001 | +5.4e-10 |
| distressed_inverted | 5Y | 1200 | 21.869331837 | 21.869331837 | 0 | 1200.000000000 | −4.5e-11 |
| distressed_inverted | 7Y | 1050 | 21.868744539 | 21.868744539 | 0 | 1050.000000000 | −4.0e-11 |
| distressed_inverted | 10Y | 950 | 22.034981192 | 22.034981192 | 0 | 950.000000000 | +8.9e-12 |
| distressed_arb | 6M | 6000 | 13.182067790 | 13.182067790 | 0 | 6000.000000000 | +1.7e-11 |
| distressed_arb | 1Y to 10Y | as distressed | as distressed | as distressed | 0 | as distressed | as distressed |

The upfront rises with tenor to 4Y and is then flat near 22 points: on an inverted curve the extra protection bought by a longer contract is worth about what the extra 500 bp coupons cost.

**Claim (criterion 6): the 5Y upfront from the full bootstrapped curve and from the flat-hazard conversion of the 5Y quote differ by under 0.01 bp on a flat curve and by more than 1 bp on HY.**
Number: flat 100 bp curve, coupon 500: 0.0024 bp of notional against `UPFRONT_CURVE_VS_FLAT_BP = 0.01` (at coupon 100 both are zero by construction, the quote being 100 bp; the test checks both coupons). HY, coupon 100: 41.70 bp against `UPFRONT_CURVE_VS_FLAT_HY_MIN_BP = 1.0`.
Rows (curve, coupon bp, s_5Y bp, clean upfront % from the curve, λ_flat %, clean upfront % from the flat conversion, difference in bp of notional):

| flat100 | 100 | 100 | +0.000000 | 1.6801 | −0.000000 | +0.0000 |
| flat100 | 500 | 100 | −16.656332 | 1.6801 | −16.656356 | +0.0024 |
| IG_flat | 100 | 90 | −0.420379 | 1.5121 | −0.417996 | −0.2383 |
| IG_flat | 500 | 90 | −17.235524 | 1.5121 | −17.137833 | −9.7690 |
| HY_steep | 100 | 500 | +15.313499 | 6.7212 | +14.896516 | +41.6983 |
| HY_steep | 500 | 500 | +0.000000 | 6.7212 | −0.000000 | +0.0000 |
| distressed_inverted | 100 | 1200 | +32.336571 | 15.1248 | +34.366093 | −202.9522 |
| distressed_inverted | 500 | 1200 | +20.577818 | 15.1248 | +21.869332 | −129.1514 |

On the flat 100 bp curve the 0.0024 bp at coupon 500 is the difference between eight hazards of 1.6798 to 1.6810% and one of 1.6801%. On HY the full curve front-loads survival (2 to 5% in the first two years against a flat 6.7%), so a 100 bp coupon stream is worth more under the curve and the buyer pays 42 bp more upfront; on the inverted distressed curve the sign flips and the gap is 2 points. This is why Table 1 carries both the quote and the conventional spread and why Section 7 compares upfronts, not only spreads.

**Claim: the committed outputs are what the code produces, with the fixed columns.** Table 1: 32 rows, columns `curve, pillar, maturity, quote_kind, quote, coupon_bp, conventional_spread_bp, method, hazard_pct, survival_prob, cum_default_prob`; `method` is `bootstrap` on 24 rows and `upfront` on the 8 `distressed_arb` rows; `survival_prob + cum_default_prob = 1` to 1e-12 on every row. Chart 1 CSV: 363 rows (3 × 121), columns `curve, t_years, hazard_pct, survival_prob`; PNG 1600 × 900. The test regenerates both into a temporary directory and compares the text with the committed files.

## Before / after

Item 24, the 5Y flat par spread (flat 1% hazard, R = 0.40, coupon 100, the review 05 base contract):

| metric | before (`d6d4045`) | after (`4ec5b80`) |
|---|---|---|
| `price().par_spread_bp`, 5Y flat | 56.336893 (PV_prot / A) | 59.519383 (PV_prot / (A − accrued_fraction / D)) |
| `Valuation.dirty_par_spread_bp`, 5Y flat | — (was `par_spread_bp`) | 56.336893 |
| `clean_par_spread_bp(state, trade)` | 59.519383 | removed |
| `cds.legs.par_spread_bp(legs)` | 56.336893 | renamed `dirty_par_spread_bp`, 56.336893 |
| 5Y flat clean upfront at coupon 100 | −1.71186278 % | −1.71186278 % |
| clean upfront at c = 59.519383 | −0.0000000000 % | −0.0000000000 % (criterion 1 now at `par_spread_bp`) |
| mtm at c = 56.336893 | +0.000000 $ | +0.000000 $ (the companion identity) |
| tests | 279 | 279 |

The par spread per tenor on the flat curve, before → after (the review 05 tenor table, now the reported number):

| 6M | 31.208270 → 59.487671 |
| 1Y | 45.175812 → 59.499242 |
| 2Y | 52.174884 → 59.512479 |
| 5Y | 56.336893 → 59.519383 |
| 10Y | 57.712480 → 59.522989 |

Section 6 adds:

| metric | before | after |
|---|---|---|
| tests | 279 | 303 |
| curve files | 0 | 4 |
| Table 1 rows | — | 32 |
| Chart 1 rows | — | 363 |
| IG 5Y hazard | — | 2.248001 % |
| HY 5Y hazard | — | 10.851143 % |
| distressed 5Y hazard | — | 4.733508 % |
| IG 5Y clean upfront at coupon 100 | — | −0.420379 % |

## Not verified

- **The bootstrap against `ql.SpreadCdsHelper` / `PiecewiseFlatHazardRate`.** Section 7. Every pillar reprices under our own pricer, whose par spread is QuantLib's `fairSpread` to 1e-9 bp (review 05), so a QuantLib bootstrap on the same conventions should return the same hazards to well under `QL_HAZARD_BP = 0.5`; not run here.
- **A weekend or holiday `as_of`.** `bootstrap` goes through `value()`, whose trade-date check (item 10) raises for a non-business-day `as_of`. Section 8 re-bootstraps at the snapshot date only; the thetas shift curves, not the bootstrap. Not exercised.
- **The `ValueError` when a spread is above what λ = 5 reaches** (rule 3). Same as review 05's upper-bound note; the spread needed is above 25,000 bp.
- **A first pillar with f(0) ≥ 0.** Only a zero spread gives it (f(0) = −s_1 · (D · A − accrued_fraction) < 0 otherwise), and then `flat_from_shortest` would fit λ = 0. Not tested.
- **The pinned arbitrage level depends on the discount curve.** 6000 bp is where the 1Y f(0) crosses zero on this snapshot; a different snapshot could cross at 5500 or 6500 and the test constant would need regenerating with `scripts/make_curves.py`. The file's `note` says how it was found.
- **Chart 1's picture against its CSV.** The PNG draws the hazard as the exact step at the pillar times and Q(t) daily; the CSV is the same two functions on a monthly grid (Against the plan 7). The CSV is tested against a regeneration; the picture was looked at, not tested beyond its size.
- **Table 1's `distressed_arb` rows under `flat_from_shortest`.** Only the `upfront` fallback is in the committed table; the `flat_from_shortest` numbers are in this review only.

## Open

Nothing tried and unexplained.

## Against the plan

1. **Criterion 3's "strictly increasing for HY" is not met on the specified levels.** HY hazards 2.017, 3.053, 5.134, 7.294, 8.690, 10.851, **10.616, 10.586**%: the 7Y and 10Y forward hazards sit 0.23 and 0.26 percentage points below the 5Y one. The levels (150 … 500, 560, 600) are the plan's own from Section 0 (`docs/DATA_NOTE.md`), not the spec's, and `docs/CONVENTIONS_RESOLVED.md` item 6 says to keep the named curves as specified, so they were not changed. The test asserts every λ > 0, the strict rise through 5Y, and pins the dip. Raising the long end to 570 / 640 bp is the smallest 10 bp-rounded change that gives a strictly increasing curve (11.289, 13.236%). Does the reviewer keep the levels and drop "strictly increasing" from criterion 3, or change HY's 7Y and 10Y to 570 / 640 (which also changes Table 1, Chart 1, `docs/DATA_NOTE.md` and `data/curves/README.md`)?
2. **A fallback is used only when the sequential fit raises.** `bootstrap(quotes, discount, fallback=...)` on a curve that fits returns `method = "bootstrap"` and ignores the fallback, so `scripts/make_outputs.py` can run every file with `fallback="upfront"` and the `method` column says what happened. The alternative reading, the fallback as the method to use regardless, would need a separate argument to force it; nothing in the plan asks for that. Accept?
3. **Table 1 shows `distressed_arb` under the `upfront` fallback**, one row per (curve, pillar) as the plan fixes; the `flat_from_shortest` rows are in this review. The `upfront` rows are the more informative eight (per-pillar hazards rather than one number repeated). Accept, or add the `flat_from_shortest` rows as a fifth curve label?
4. **`BootstrapResult` carries more than the plan's four fields**: `quotes`, `pillar_dates`, `pillar_hazards`, `arbitrage_pillar`, and `survival_for_pillar(i)`; `survival` is `None` under the `upfront` fallback (there is no joint curve) and `market_state(result, discount)` raises then. Extra public names: `market_state`, `pillar_trade`, `conventional_spreads_bp`, `read_curve_file`, `market_curve_quotes_from_file`, `write_curve_file`, `FALLBACKS`. Sections 7 and 8 will use `market_state` and `pillar_trade`. Accept?
5. **`cds/legs.py` was touched for item 24** (outside the Section 6 file list): `par_spread_bp` → `dirty_par_spread_bp`, no change of value, so that the only thing called `par_spread_bp` in the library is the item 24 quantity. Accept?
6. **`scripts/make_curves.py` is an extra file.** The distressed upfronts and the `distressed_arb` level are derived numbers; the plan lists the files but not how they get written. Committing the generator (as Section 1 did for the calendar) makes the derivation reproducible. Accept?
7. **Chart 1's picture is drawn from the exact step and a daily Q(t), the CSV from the monthly grid the plan fixes.** Drawing from the monthly grid would put each hazard jump up to a month after its pillar date. Accept?
8. **The report generators take `BootstrapResult`s, not `MarketState`s** (Part D.3 says "taking the `MarketState`s"). Table 1 needs the conventional spreads, the method and the quotes, which a `MarketState` does not carry; `market_state()` turns a result into one for the sections that need it. Accept?
9. **Part A.4's Method row was edited** along with the four plan edits the prompt listed, so the locked convention and Section 6's text state the same objective. Accept?
10. **Criterion 6's flat-curve case at coupon 100 is zero on both sides by construction** (the quote is 100 bp), so the test checks coupons 100 and 500; the 500 row (0.0024 bp) is the evidence. Accept?
11. **Curve files carry `as_of`** (the Part D.3 format requires it) and `scripts/make_outputs.py` raises if it differs from the rates file's, rather than the files omitting the date. Accept?
12. **The distressed upfronts are stored at full precision** (15 significant figures), not rounded to market precision, so that criterion 5's 1e-6 bp round trip is a property of the file and not of a rounding. Accept?
13. `cds/__init__.py` still says "None exist yet" (reviews 03 to 05); Section 10.
14. The untracked `11_CDS_Pricing_Bootstrap.docx` at the repo root is still there.

## Reviewer reads (max 6, in order)

1. `cds/bootstrap.py` — the module docstring (rules 1 to 4), then `_sequential` (the objective is one line: `value(...).clean_upfront`), `bootstrap` (the fallback branch), `BootstrapArbitrageError`.
2. `outputs/tables/table_1_hazard_curves.md` and `outputs/charts/chart_1_survival_hazard.png` — the 32 rows and the picture; the HY 7Y/10Y dip is visible in both (question 1).
3. `tests/test_bootstrap.py` — `test_each_pillar_reprices_its_conventional_spread`, `test_ig_and_hy_hazards_are_positive_and_hy_rises_through_5y` (the pinned dip), `test_distressed_arb_raises_at_the_pinned_pillar` and the two fallback tests, `test_5y_upfront_from_the_curve_and_from_the_flat_conversion`.
4. `cds/pricer.py` — `Valuation.par_spread_bp` against `dirty_par_spread_bp` and the rewritten module docstring (item 24 as applied); `tests/test_pricer.py`, the two par-coupon tests.
5. `data/curves/distressed_arb.json` and `scripts/make_curves.py` — the `note` field and `arbitrage_levels`.
6. `docs/CONVENTIONS_RESOLVED.md` items 24 to 29; `BUILD_PLAN.md` Section 5 rules and criteria 1 to 2, Section 6 objective and criterion 2, Part A.4 Method row.
