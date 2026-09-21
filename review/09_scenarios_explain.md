# Review — Section 09 — the scenario grid, the vectorised revaluation and the P&L explain; Table 4 and Chart 3

Date: 2026-09-21   Commit: dc55204   Tests: 386/386 (357 after the pre-step; 29 new; 0 skipped)

Three commits. `d2a3075 Section 09: resolved Section 8 questions` (items 39 to 45 in `docs/CONVENTIONS_RESOLVED.md`, committed before this session), `b1927d3 Section 09: items 43 to 45` (the pre-step: items 45, 44, 43 and 41 as the session prompt listed them; 356 → 357), `dc55204 Section 09: scenarios and explain` (code, tests, Table 4, Chart 3; 357 → 386), and this review.

## What changed

**Pre-step (`b1927d3`).**
- Item 45: `OUTPUT_ABS_TOL = 1e-6` in `tests/conftest.py`, comment rewritten to the item's reason; 356/356 before and after.
- Item 44: `cds/risk.py` `jtd()` prices every trade with `quote = None` (the unwind value); the docstring says the inception cash is sunk. New test: the distressed 5Y buy at coupon 500, valued on 15 Oct 2026 on the calendar-shifted curves, quoted as an upfront of 20 points and of 25 points; `PriceResult.mtm` differs by exactly 5% of notional ($500,000.00) and JTD by under $0.01, both equal to the `quote = None` number.
- Item 43: `cds/report.py` `chart_2_slopes(df)`: the least-squares slope of each MTM column against R in points over the 51 rows of the CSV; panel (b)'s legend labels end with it. Chart 2 PNG regenerated; CSV unchanged (git shows only the PNG modified). Slopes: par re-bootstrapped +0 $/pt (5e-10), par hazard-fixed −6,306, off-market re-bootstrapped +378, off-market hazard-fixed −6,306.
- Item 41: BUILD_PLAN.md Section 8 criterion 5 rewritten (IG 5Y under $200; distressed 5Y over $300; distressed 10Y over $500). `IR01_DISTRESSED_MIN_USD = 300`, new `IR01_DISTRESSED_10Y_MIN_USD = 500`, the pinned band removed; the test now also computes the distressed 10Y IR01 (−$695.71) and checks it is larger in absolute value than the 5Y's (−$399.26).

**Section 9 (`dc55204`).**
- `cds/scenarios.py` (new) — `Scenario(name, spread_multiplier, spread_shifts_bp, recovery, rate_shift_bp)`; the factories `spread_scenario`, `parallel_scenario`, `recovery_scenario`, `steepen_scenario`, `flatten_scenario`, `rates_scenario`, `combined_scenario`; `standard_grid(base_recovery)` (14 scenarios), `sweep_grid()` (71); `scenario_spreads_bp`, `scenario_state`, `scenario_states`, `revalue`, `run`; `RUN_COLUMNS`.
- `cds/explain.py` (new) — `explain(state_t0, state_t1, trade, *, sensitivities_t0) -> ExplainResult`; `Sensitivities(report, spreads_bp, gamma, cross)` and `sensitivities(state, trade)`; `gamma_parallel`, `spread_moves_bp`, `rates_move_bp`; `EXPLAIN_ZERO_USD = 0.01`, `NODE_DF_ABS_TOL = 1e-12`.
- `cds/legs.py` — `CurveArrays(hazards, node_dfs, recoveries)`, `df_rows`, `survival_rows`, and `leg_values(..., arrays=None)`: with arrays the fields of `LegValues` have shape `(n,)`. The scalar path is the code as it was (Against the plan 1).
- `cds/types.py` — untouched: `ExplainResult` already carried the nine fields of the plan in the plan's order (the test checks).
- `cds/report.py` — `table_4_pnl_explain`, `table_4_pnl_explain_full`, `explain_grid`, `table_4_trade`, `chart_3_pnl_vs_spread_shock`, `TABLE_4_CURVE`, `TABLE_4_SCENARIOS`, `TABLE_4_COLUMNS`, `CHART_3_CURVE`, `CHART_3_COLUMNS`.
- `scripts/make_outputs.py` — `--only table_4` (writes both files from one explain of the grid), `--only chart_3`.
- `tests/test_scenarios.py` (15 tests), `tests/test_explain.py` (14 tests); `tests/conftest.py` — `LEGS_VECTOR_ABS_TOL = 1e-12`, `EXPLAIN_X3_RESIDUAL_MIN_PCT = 5.0`, `EXPLAIN_X3_PINNED_BAND = (2.0, 5.0)`, each with its reason. `EXPLAIN_RESIDUAL_PCT` and `GRID_SECONDS` were already there.
- `outputs/tables/table_4_pnl_explain.{csv,md}` (6 rows), `outputs/tables/table_4_pnl_explain_full.{csv,md}` (14 rows), `outputs/charts/chart_3_pnl_vs_spread_shock.{png,csv}` (71 rows). Tables 1, 2, 3, 5 and Charts 1, 2 are byte-identical to before the section.

**Rules stated in full.** `as_of` = 15 Sep 2026; N = 10,000,000; the Table 4 and Chart 3 trade is the 5Y IG protection buy at coupon 100 bp, R = 0.40, `quote = None`; the tests also run HY (5Y buy at 500) and distressed (5Y buy at 500).

1. **A scenario transforms the inputs, never the curve.** s_i' = s_i × multiplier + shift_i on every pillar's conventional spread (item 40's reading, the same s_i every Section 8 bump starts from); R' = the scenario's recovery; every OIS par rate + shift. The scenario state is the bootstrap of the eight s_i' as par-spread quotes at R' on the discount curve rebuilt from the shifted par rates (`bootstrap_ois`): one Brent per pillar, looped over scenarios. Nothing is bumped after the bootstrap.
2. **The standard grid**, named as the `scenario` column reads: `spread_x0.5, spread_x0.75, spread_x1, spread_x1.5, spread_x2, spread_x3, spread_x4`; `recovery_0.2, recovery_0.1` (R × 0.5 and × 0.25 of the curve's R; on HY `recovery_0.125, recovery_0.0625`, Against the plan 3); `steepen_35bp` (+0, +5, ..., +35 bp, linear in pillar index, 0 at 6M), `flatten_35bp` (the negative); `rates_+100bp, rates_-100bp`; `combined` (× 2, R × 0.5, rates −100). The Chart 3 sweep is `spread_x0.5` to `spread_x4` in 0.05 steps.
3. **The vectorised revaluation.** Every scenario state shares the base's valuation date, pillar dates and discount node dates (`revalue` checks), so the merged integration grid of `cds.legs` is the same for all; the hazards `(n, 8)`, node discount factors `(n, 13)` and recoveries `(n,)` are stacked into a `CurveArrays` and priced with one `leg_values` call. P and Q are read from the stacked rows by `df_rows` and `survival_rows`, the same log-linear and piecewise-constant-hazard formulas the curve classes use. The pricer's formulas are then applied on the arrays through `cds.pricer.Valuation` (D = 1/P(t_settle) per scenario, U_dirty = D (PV_prot − c A), mtm = side N (U_dirty − inception)), the trade valued at each scenario's recovery as rec01 does; the inception cash, scenario-free, is read off the base state once as side N U_dirty(base) − mtm(base).
4. **The explain** (module docstring of `cds/explain.py` has the formulas): pnl_full = V(t_1) − V(t_0) − side · coupons paid in (t_0, t_1]; first order = Σ_i cs01_i · Δs_i with cs01_i the one-sided per-pillar CS01 of the t_0 `RiskReport` and Δs_i the change in pillar i's conventional spread in bp; gamma = ½ Γ Δs² with Δs the average of the eight Δs_i; recovery = rec01 · ΔR in points; rates = ir01 · Δr in bp, Δr the average change in the OIS par rates; theta = theta_calendar over the date gap (0 when as_of is unchanged); cross = C · Δs · ΔR; residual = pnl_full − the six; residual_pct_of_total = 100 · residual / pnl_full, `nan` when |pnl_full| < $0.01.
5. **Gamma, sign convention.** Γ = V(s+1) − 2V(s) + V(s−1) per bp² = 2 · (cs01_parallel − cs01_central_parallel), the second derivative of the side's mtm in the parallel spread, so that ½ Γ Δs² carries the sign of the P&L. It is negative for the buyer: mtm = (s − c) A(s) and A falls as s rises, so the mtm is concave in spread, the buyer is short convexity and CS01 shrinks as spreads widen; that is why Section 8's central CS01 sits above the one-sided one. The prompt's "2 · (central − one-sided)" is the same number with the opposite sign (Against the plan 2).
6. **The cross term.** C = V(s+1, R+1) − V(s+1, R) − V(s, R+1) + V(s, R) = V(s+1, R+1) − mtm − cs01_parallel − rec01, from one extra bootstrap at (every s_i + 1 bp, R + 1 point) with the spreads held fixed, the same reading as the parallel CS01 and rec01. On IG C = −$1.807 per bp·point, on HY −$6.228.
7. **`sensitivities(state, trade)`** computes the risk report, Γ and C once (about 25 bootstraps, 1.6 s on IG) so a grid reuses them; `explain` computes them itself when not given. Table 4 and Chart 3 share one.

## Findings

**Claim (criterion 1): a +10 bp parallel move is explained to 0.01% of pnl_full on IG and HY, against the 2% bar.**
Rows (curve, scenario, pnl_full $, first order $, gamma $, recovery + rates + theta + cross $, residual $, residual % of total):

| IG_flat | parallel_+10bp | 42037.86 | 42194.91 | −160.95 | 0 | 3.91 | +0.009% |
| HY_steep | parallel_+10bp | 38170.48 | 38281.20 | −113.50 | 0 | 2.78 | +0.007% |
| IG_flat | parallel_+100bp | 406299.42 | 421949.08 | −16095.28 | 0 | 445.63 | +0.11% |
| HY_steep | parallel_+100bp | 371716.65 | 382811.97 | −11350.47 | 0 | 255.15 | +0.07% |

First order on a parallel move is 10 × cs01_bucket_sum (IG 4219.49, HY 3828.12, review 08), asserted exactly. The residual on 10 bp is the third-order term: it scales by 114× (IG) and 92× (HY) from 10 to 100 bp, against 1000× for a cubic and 100× for a quadratic, the gamma being read at ±1 bp rather than at the move.

**Claim (criterion 2): Γ is negative for the buyer on both curves, pnl_spread_gamma is negative on +100 bp, and Γ from the report equals the explicit second difference of the parallel bump to $1e-6.**
Rows (curve, cs01_parallel $, cs01_central_parallel $, Γ = 2 (parallel − central) $/bp², V(s+1) − 2V(s) + V(s−1) recomputed from three `price()` calls $, gamma term on +100 bp $, the seller's):

| IG_flat | 4218.2307 | 4219.8402 | −3.2191 | −3.2191 | −16095.28 | +16095.28 |
| HY_steep | 3827.2400 | 3828.3751 | −2.2701 | −2.2701 | −11350.47 | +11350.47 |

On +100 bp the full revaluation sits below the first-order line (IG 406,299 against 421,949) and the gamma term is within 3% of the gap (−16,095 against −15,650 on IG, −11,350 against −11,095 on HY); the seller's pnl_full is the negative of the buyer's to 1e-5 $.

**Claim (criterion 3): the 71-scenario sweep plus the 14-scenario grid on IG revalues in 6.2 s, against the 10 s bar; the bootstraps are 99% of it.**
Rows (run, sweep bootstraps s, sweep vectorised revaluation s, grid bootstraps s, grid revaluation s, total s), three runs on this machine after the test's own (which passed at under 10 s):

| 0 | 5.29 | 0.007 | 1.00 | 0.007 | 6.31 |
| 1 | 5.10 | 0.007 | 1.02 | 0.005 | 6.13 |
| 2 | 5.18 | 0.007 | 1.02 | 0.005 | 6.21 |

One bootstrap is 70 ms (8 Brent solves, each about 20 `value()` calls). The vectorised revaluation of 71 scenarios takes 7 ms where 71 scalar `price()` calls take 74 ms: a 10× gain on 1% of the wall clock. The plan's design (vectorise the revaluation, loop the bootstraps) is what was built; the bar is met with a 38% margin and the sweep would still be under 10 s with a bootstrap 1.6× slower.

**Claim (criterion 4): the vectorised leg values equal the scalar path to 1.1e-16 per unit notional (bar 1e-12) on five random scenarios on every curve, and the mtm to 1e-9 $ on $10m.**
The five scenarios (seed 20260921; multiplier, parallel shift bp, R, rates bp): random_0 (1.6906, +0.16, 0.3415, −55.98); random_1 (1.4003, +29.56, 0.5625, −13.34); random_2 (1.3400, −1.71, 0.2843, +50.64); random_3 (1.1179, −4.18, 0.4151, −74.91); random_4 (1.6333, +25.98, 0.3209, +117.60). Rows (curve, scenario, A vectorised, PV_prot vectorised, max gap over the four leg fields, mtm vectorised $, mtm scalar $, gap $):

| IG_flat | random_0 | 4.430806057 | 0.063849505 | 0 | 195468.533550 | 195468.533550 | 0 |
| IG_flat | random_1 | 4.282373338 | 0.062913847 | 2.8e-17 | 200963.872208 | 200963.872208 | 0 |
| IG_flat | random_2 | 4.379833783 | 0.049232212 | 1.4e-17 | 54358.599706 | 54358.599706 | 7.3e-11 |
| HY_steep | random_0 | 3.710667854 | 0.293532243 | 5.6e-17 | 1080287.453925 | 1080287.453925 | 4.7e-10 |
| HY_steep | random_4 | 3.603651644 | 0.283532622 | 5.6e-17 | 1033935.509978 | 1033935.509978 | 5.8e-10 |
| distressed_inverted | random_1 | 2.065860900 | 0.312409746 | 1.1e-16 | 2091819.989902 | 2091819.989902 | 9.3e-10 |
| distressed_inverted | random_2 | 2.708615245 | 0.396711386 | 1.1e-16 | 2613760.976331 | 2613760.976331 | 9.3e-10 |

All 15 rows are in the test; the largest leg gap anywhere is 1.1e-16 and the largest mtm gap 9.3e-10 $. The same identity holds on the `grid` engine (two scenarios on IG) and for the n = 1 case against the scalar call. `df_rows` and `survival_rows` are also checked directly against `DiscountCurve.df` and `SurvivalCurve.Q` on 241 points through and beyond the last node, for the base curve and a doubled one, to 1e-12.

**Claim (criterion 5, not met): on HY the ×3 spread scenario leaves a residual of −3.23% of pnl_full after the gamma term, against the plan's "over 5%"; first order alone leaves 26.1%.**
Rows (curve, scenario, pnl_full $, first order $, gamma $, residual $, residual %, unexplained by first order alone %):

| HY_steep | spread_x3 | 3034950.39 | 3828119.73 | −694996.53 | −98172.81 | −3.23% | −26.1% |
| HY_steep | spread_x2 | 1700820.32 | 1914059.87 | −173749.13 | −39490.41 | −2.32% | −12.5% |
| HY_steep | spread_x0.5 | −1016936.55 | −957029.93 | −43437.28 | −16469.33 | +1.62% | +5.9% |
| IG_flat | spread_x3 | 717179.06 | 759029.22 | −38668.92 | −3181.24 | −0.44% | −5.8% |
| IG_flat | spread_x4 | 1046023.82 | 1138543.83 | −87005.06 | −5514.95 | −0.53% | −8.8% |

The residual is material in dollars ($98k on a $3.0m P&L) and its sign is the third-order one (the gamma read at ±1 bp overstates the curvature at +1000 bp, where CS01 has already shrunk), but 3.2% is under the bar. The number depends on the plan's definition of Δs for the gamma term as the *average* pillar move (782 bp on HY ×3, where the 5Y pillar itself moves 1000 bp); with the 5Y move the gamma term would be −1,135k and the residual +342k, +11%. The test pins the number in (2, 5)% and asserts the first-order-only figure is over 5% (Against the plan 4).

**Claim (Table 4): the six rows are written, every scenario of the grid is in the full file, and every term is the report's sensitivity times the input move.**
The six rows, on the 5Y IG buy (scenario, pnl_full $, first order $, gamma $, recovery $, rates $, cross $, residual $, %):

| spread_x1.5 | 187080.58 | 189757.30 | −2416.81 | 0 | 0 | 0 | −259.92 | −0.14 |
| spread_x3 | 717179.06 | 759029.22 | −38668.92 | 0 | 0 | 0 | −3181.24 | −0.44 |
| recovery_0.2 | −302.71 | 0 | 0 | −408.43 | 0 | 0 | 105.72 | −34.92 |
| steepen_35bp | 104674.53 | 105367.16 | −492.92 | 0 | 0 | 0 | −199.71 | −0.19 |
| rates_+100bp | 956.12 | 0 | 0 | 0 | 975.28 | 0 | −19.16 | −2.00 |
| combined | 381373.80 | 379514.61 | −9667.23 | −408.43 | −975.28 | 2800.65 | 10109.48 | 2.65 |

pnl_theta is 0.00 in every row (as_of unchanged). The recovery term is rec01 × (−20 points) = 20.4216 × −20 = −408.43 on a full revaluation of −302.71: the mtm is convex in R here (Chart 2's off-market re-bootstrapped line has the same shape), and the large percentage is on a $300 P&L; `recovery_0.1` reads −404.24 against −612.65 (−51.6%). rates_+100bp is ir01 × 100 = 975.28 against 956.12. The combined row's cross term is C × Δs × ΔR = −1.8069 × 77.5 × (−20) = +2800.65, Δs the average of the eight ×2 moves (45 to 120 bp); its residual, 2.65%, holds the second-order terms the explain has no column for (rates–spread, recovery–recovery). The full file (`table_4_pnl_explain_full.md`) adds the other eight rows; `spread_x1` is all zeros with an empty percentage. `explain`'s pnl_full equals `run`'s vectorised pnl_full to 1.3e-10 $ on every scenario of the grid (test).

**Claim (Chart 3): the full revaluation is concave in the multiplier, first order is a straight line through zero at ×1, and the gamma line is closer to the full revaluation than first order at every one of the 70 off-base points.**
Rows (multiplier, pnl_full $, first order $, first order + gamma $):

| 0.50 | −192515.72 | −189757.30 | −192174.11 |
| 0.75 | −95569.01 | −94878.65 | −95482.85 |
| 1.00 | 0.00 | 0.00 | 0.00 |
| 1.50 | 187080.58 | 189757.30 | 187340.50 |
| 2.00 | 368874.79 | 379514.61 | 369847.38 |
| 3.00 | 717179.06 | 759029.22 | 720360.30 |
| 4.00 | 1046023.82 | 1138543.83 | 1051538.76 |

The first-order slope is 379,514.61 $ per unit of multiplier at every point (standard deviation across the 70 ratios under 1e-6 of the mean); the ×3 row is Table 4's `spread_x3` to 1e-6 $. Generation: Table 4 (both files, one grid of 14 bootstraps plus the sensitivities) and Chart 3 (71 bootstraps plus the sensitivities) together in 12.2 s including the interpreter start.

**Claim (the theta term): with a date gap the explain's theta is theta-calendar, and the residual is exactly the rolldown-minus-calendar difference when the curves are rolled in tenor and zero when they are fixed on their dates.**
Rows (t_1, how the t_1 curves were built, pnl_full $, pnl_theta $, residual $), the 5Y IG buy from 15 Sep 2026:

| 2026-09-16 | tenor (rolled) | −363.41 | −146.61 | −216.81 |
| 2026-09-16 | calendar (fixed) | −146.61 | −146.61 | 0.00 |
| 2026-10-15 | tenor | −10424.40 | −3912.60 | −6511.81 |
| 2026-10-15 | calendar | −3912.60 | −3912.60 | 0.00 |

The four numbers are Table 3's `theta_rolldown_1d`, `theta_calendar_1d`, `theta_rolldown_1m`, `theta_calendar_1m` (review 08); the 1-month window holds the 21 Sep coupon, which pnl_full nets out as theta does. Δs, ΔR and Δr are all zero on both constructions (the quotes carry the same numbers; the calendar-shifted discount curve has no par rates and `rates_move_bp` reads it as unchanged after checking its nodes against the calendar-shifted t_0 curve to 1e-12).

**Claim: the grid runs on every curve except `spread_x4` on HY and distressed, which do not bootstrap; the failure names the scenario.**
Rows (curve, scenario, what the bootstrap reports):

| HY_steep | spread_x4 | pillar 10Y at 2400 bp is above what a hazard of 5.0 reaches (little survival mass left beyond 7Y at 2240 bp; the forward hazard needed is over 500%) |
| distressed_inverted | spread_x4 | pillar 5Y at 4800 bp needs a negative hazard: f(0) = +3.76e-3 per unit notional |

Every other scenario of the grid runs on both (13 rows each, in the test), including `flatten_35bp` on the inverted curve. On the HY 5Y trade at par the recovery and rates scenarios have zero P&L to 1e-9 $ (spreads fixed and re-bootstrapped, the trade at par: Part C item 5) and the explain writes their percentage as `nan`.

## Before / after

| metric | before (`16b3a48`) | after (`dc55204`) |
|---|---|---|
| tests | 356 | 386 |
| `OUTPUT_ABS_TOL` | 1e-9 | 1e-6 |
| JTD on an upfront-quoted seasoned trade | net of the inception cash | the unwind value (item 44) |
| Chart 2 panel (b) legend | trade and reading | + slope in $ per recovery point from the CSV |
| BUILD_PLAN.md Section 8 criterion 5 | distressed 5Y over $500 | 5Y over $300, 10Y over $500 |
| `leg_values` | scalar only | scalar, or `(n,)` with `CurveArrays` |
| IG 5Y Γ / C | — | −3.2191 $/bp² / −1.8069 $/(bp·pt) |
| IG 5Y, 10 bp parallel: residual | — | $3.91, 0.009% |
| HY 5Y, ×3: residual | — | −$98,172.81, −3.23% |
| sweep + grid, 85 scenarios | — | 6.2 s |
| Table 4 rows (six / full) | — | 6 / 14 |
| Chart 3 rows | — | 71 |
| Tables 1, 2, 3, 5, Charts 1, 2 (CSV) | — | byte-identical |

No pricing number changed: the scalar path of `leg_values` is the code it was, and every "is current" test of the earlier outputs passes unchanged.

## Not verified

- **The vectorised path on a curve with fewer than eight pillars or a discount curve on other tenors.** `CurveArrays` checks the counts against the base curves, but every test uses the standard eight pillars and the 13-tenor snapshot. A run on a 3-pillar in-test curve would settle it.
- **The `us_uk` calendar through `run` and `explain`.** Passed through to every `bootstrap` and `price` call; every number here is on the weekend-only calendar.
- **A date-gap explain with a market move at t_1** (spreads or rates changed on a later date). The theta rows above move only the date; a t_1 state bootstrapped fresh on 15 Oct 2026 from moved quotes would exercise `spread_moves_bp` and `rates_move_bp` together with theta. Not run because no Section builds a second-date market.
- **The size of the recovery-scenario residuals on IG** (−35% and −52% of a $300 and $400 P&L). Consistent with the convexity in R that Chart 2's re-bootstrapped off-market line shows, but a second-order recovery term was not computed to confirm the numbers.
- **The combined scenario's residual composition** (2.65%, $10,109). Believed to be the rates–spread and recovery–spread second-order terms the explain has no column for; not decomposed.

## Open

Nothing tried and unexplained.

## Against the plan

1. **The scalar path of `leg_values` is not literally the n = 1 case of the array path.** The plan says "Section 4's scalar path is the n_scenarios = 1 case"; the array branch is a second branch in the same function sharing the grid, the closed forms and the accrual loop, with `df_rows`/`survival_rows` in place of the curve methods, and the n = 1 call is tested equal to the scalar one to 1e-12. Rewriting the scalar path through the arrays would have changed Section 4 code that Sections 5 to 8 and QuantLib were validated on. Accept as built, or should the scalar path be routed through the array code?
2. **Γ's sign convention.** The prompt's "γ = 2·(central − one-sided)/1 bp" gives +3.22 on IG; the module defines Γ = V(s+1) − 2V(s) + V(s−1) = 2·(one-sided − central) = −3.22, the second derivative, so that ½ Γ Δs² is the P&L term with its own sign and criterion 2 (negative for the buyer) reads directly. Same magnitude, opposite sign. Accept the second-derivative convention?
3. **Recovery scenarios are ratios of the curve's R, not the plan's levels.** R × 0.5 and R × 0.25 give the plan's 0.20 and 0.10 on IG (and 0.10 and 0.05 on distressed) but 0.125 and 0.0625 on HY where the plan says "0.25 → 0.10"; the prompt allowed "the curve's R stepped down by the same ratios". Nothing in the outputs is on HY. Accept, or should HY's grid carry `recovery_0.1`?
4. **Criterion 5 is not met: the ×3 residual on HY is −3.23% after gamma, against "over 5%".** First order alone leaves 26.1%. The test pins the number in (2, 5)% with the plan's 5 kept as `EXPLAIN_X3_RESIDUAL_MIN_PCT` and asserts the first-order-only figure is over 5%. Should the criterion read "the residual after first order alone is over 5%" (met at 26%), should the bar become 2% for the residual after gamma, or should Δs in the gamma term be the 5Y pillar's move rather than the average (which gives +11%, but is not the plan's definition)?
5. **`spread_x4` does not bootstrap on HY or distressed**, so the standard grid runs whole only on IG. `run` raises naming the scenario; the tests run the other 13 on both curves. The plan's outputs are on IG only. Accept, or should `run` take an `on_error="skip"` and write the row as `nan`?
6. **Δs for the gamma and cross terms is the average of the eight pillar moves, as the plan defines it**, including the 7Y and 10Y pillars that cannot move a 5Y trade. On the multiplier scenarios the average (77.5 bp per unit of multiplier on IG) is below the 5Y move (90 bp). Stated so the gamma numbers are read as the plan's definition, not the trade's own convexity; question 4 asks whether to change it.
7. **`run()`'s columns are this section's choice** (the plan fixes Table 4 and Chart 3 only): `scenario, spread_multiplier, recovery, rate_shift_bp, spread_6m_bp … spread_10y_bp, mtm, pnl_full, par_spread_bp, clean_upfront_pct`. The eight spread columns document the scenario in full. Accept?
8. **`residual_pct_of_total` is `nan` (written empty) when |pnl_full| < $0.01**, i.e. the `spread_x1` row and, on the HY par trade, the recovery and rates rows. Accept?
9. **`rates_move_bp` reads a t_1 discount curve without par rates as an unchanged rates market** when its nodes are the calendar-shifted t_0 curve's to 1e-12, and raises otherwise. Needed for the theta test; a real second-date market would carry par rates. Accept?
10. **`explain` values the trade at t_1 with the t_1 state's recovery** (as rec01 does) and requires the trade's recovery to be the t_0 state's. Accept?
11. **`scripts/make_outputs.py` was edited** (not in the section's file list, as in Section 8): `--only table_4` writes both Table 4 files from one explain of the grid. Accept?
12. `cds/__init__.py` still says "None exist yet" (reviews 03 to 08); Section 10.
13. The untracked `11_CDS_Pricing_Bootstrap.docx` at the repo root is still there.

## Reviewer reads (max 6, in order)

1. `cds/explain.py` — the module docstring (the formulas, Γ's sign convention, the cross term), then `explain()`.
2. `outputs/tables/table_4_pnl_explain_full.md` — the 14 rows; the recovery and combined rows (questions 4 and 6).
3. `outputs/charts/chart_3_pnl_vs_spread_shock.png` — the three lines to ×4.
4. `cds/scenarios.py` — the module docstring (what a scenario transforms, the revaluation), then `revalue()` and `run()`.
5. `cds/legs.py` — `CurveArrays`, `df_rows`, `survival_rows` and the two branches in `leg_values` (question 1).
6. `tests/test_explain.py` — `test_x3_spread_scenario_residual_on_hy_is_material` (question 4) and `test_theta_term_over_a_date_gap`.
