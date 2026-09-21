# Review — Section 10 — the README, the results page and closing

Date: 2026-09-22   Commit: 71b739f   Tests: 397/397 (386 after the pre-step; 11 new; 0 skipped)

Three commits. `767c4e9 Section 10: items 46 to 52` (the pre-step: items 50, 49 and 52 as the session prompt listed them; 386 → 386, one test renamed and widened), `71b739f Section 10: readme and results` (README, `scripts/make_results.py`, `outputs/results.html`, `tests/test_readme_paths.py`, `cds/__init__.py`, `.gitignore`, `docs/DATA_NOTE.md`; 386 → 397), and this review. Items 46 to 52 were already in `docs/CONVENTIONS_RESOLVED.md` (`42f2e9d`, before this session).

## What changed

**Pre-step (`767c4e9`).**
- Item 50: `cds/scenarios.py` `run(..., on_error="skip")`. `RUN_COLUMNS` gains `status` in second place; `RUN_VALUE_COLUMNS = (mtm, pnl_full, par_spread_bp, clean_upfront_pct)` are written `nan` for a scenario whose bootstrap raises, the inputs (multiplier, recovery, rate shift, the eight spreads) are still written, and `status` is the class of the error the bootstrap raised, read through the wrapper `scenario_state` adds (`error_status`). `on_error="raise"` propagates the first error naming the scenario; any other value is a `ValueError`. `scenario_states` is unchanged in behaviour (it raises) and shares `_scenario_states_or_errors` with `run`. `cds/report.py`: Chart 3 runs with `on_error="raise"` so a nan row cannot hide in the chart. Test `test_the_grid_runs_on_every_curve_and_skips_the_scenarios_it_cannot_bootstrap` runs the whole 14-scenario grid on every curve.
- Item 49: `tests/test_explain.py::test_x3_spread_scenario_residual_on_hy_is_material` asserts the first-order residual is over `EXPLAIN_X3_RESIDUAL_MIN_PCT = 5` and the residual after gamma is at most `(1 − EXPLAIN_X3_GAMMA_REMOVES_FRACTION) = 0.5` of it. `EXPLAIN_X3_PINNED_BAND` deleted.
- Item 52: `tests/conftest.py` `assert_output_value(actual, committed, what)`: one number under `assert_output_current`'s rule, |Δ| ≤ max(1e-6, 1e-6 |committed|). Used for Chart 3's ×3 row against Table 4 (three columns), Table 3's `cs01_5y` against Table 2's `cs01_usd` "ours" on every curve (new cross-check), Table 3's fields against the in-memory `RiskReport`, Chart 2's 1-point step against `rec01` and its R = 0.40 meeting point. Every `.md` text comparison deleted (Tables 1, 2, 3, 4, 4-full, 5); Table 3's wide-layout check reads the fresh rendering, not the committed file. The ten remaining bare `abs=` literals in the suite were moved to named constants (`SENSITIVITY_RECOMPUTE_ABS_USD = 1e-6`, `BOOTSTRAP_REPRICE_BP`, `OIS_REPRICE_BP / 100`) or made exact where the inputs are identical. **No test compares floats with a bare absolute tolerance or compares a `.md` file.** The one `1e-13` left in `tests/` is `quad`'s `epsabs`, an integrator setting, not a comparison.

**Section 10 (`71b739f`).**
- `README.md` rewritten: the paragraph on what the library is and what it matches, Table 2, how to run (three commands), four findings (rec01 both ways with Table 3 and Chart 2; ISDA against textbook with Table 5 and the four conventions; theta on `HY_steep` against `distressed_inverted` from Table 3's four theta rows; the P&L explain with Table 4, Chart 3 and the item 49 statement), the CDS–bond basis note with one worked example off Table 1, the default-study sanity check, conventions, limitations, the ten section reviews linked. Tables sit between `<!-- table: <stem> -->` / `<!-- end table -->` markers and are the committed `.md` files verbatim; the README computes nothing and restates no number a shown table carries.
- `scripts/make_results.py` (new): `build_results_html()` renders every `outputs/tables/*.md` (own pipe-table parser, `html.escape`, text columns left-aligned) and embeds every `outputs/charts/*.png` as a base64 data URI in `SECTIONS`, the README's order; one inline `<style>`, no `<script>`, no `<link>`, one `href` (the repo). `sync_readme()` refills the README's marker blocks from the files. `--check` exits 1 if either file would change.
- `outputs/results.html` (new, committed): 451,071 bytes, 6 tables, 3 charts.
- `tests/test_readme_paths.py` (new, 11 tests): every relative link and image path in the README exists; the three PNGs are embedded; Table 2 is the first table and the text before it (1,259 characters) says "illustrative", "validated" and "QuantLib"; every marker block equals its `.md` file and `sync_readme` is a no-op; the prose (tables and the code block excluded) is under 1,500 words; no header names a section number or a module; `results.html` regenerates byte-identical, embeds each committed table and chart exactly once in `SECTIONS`' order, is under 5 MB, has only data-URI `src`s, one `href`, no script, link, `@import` or `url(`; `--check` passes; `cds.__doc__` names the public objects and no longer says "None exist yet"; `.gitignore` lists the stray docx.
- `cds/__init__.py`: module docstring lists every module's public objects and a typical session; the "None exist yet" line is gone (reviews 03 to 09 carried it forward).
- `.gitignore`: `/11_CDS_Pricing_Bootstrap.docx` added with a comment; the file stays on disk, untracked, as the prompt asked.
- `docs/DATA_NOTE.md`: the "historical cumulative default rates" section filled in (study, date, exhibit, the five-year column, which figure the README uses and why the HY and distressed comparisons are not made).

**Rules stated in full.**
1. The README embeds committed outputs by path (images) or verbatim (tables, synced from the `.md` files) and computes nothing. A number appears in prose only where the table carrying it is not shown on the page or the sentence says where in a shown table to look.
2. `results.html` is built only from `outputs/tables/*.md` and `outputs/charts/*.png`; the test compares the committed page to a fresh build as text, so a regenerated table or chart that changes must be followed by `make_results.py` in the same commit (the same rule as `ui/lib/types.ts` in the neighbouring project, and `assert_output_current` here).

## Findings

**Claim (item 50): `run()` writes every scenario of the standard grid on every curve; the two that do not bootstrap carry the error's class and nan values.**
Rows (curve, scenario, status, `spread_5y_bp` written, recovery written, mtm, pnl_full), the 5Y buy at coupon 500 on each curve, from `run` with the default `on_error`:

| HY_steep | spread_x3 | ok | 1500.0 | 0.25 | 2915505.95 | 3034950.39 |
| HY_steep | spread_x4 | ValueError | 2000.0 | 0.25 | nan | nan |
| HY_steep | recovery_0.125 | ok | 500.0 | 0.125 | −119444.44 | 0.00 |
| distressed_inverted | spread_x3 | ok | 3600.0 | 0.20 | 5009327.47 | 3070990.16 |
| distressed_inverted | spread_x4 | BootstrapArbitrageError | 4800.0 | 0.20 | nan | nan |
| distressed_inverted | combined | ok | 2400.0 | 0.10 | 4298981.10 | 2360643.79 |

13 of 14 rows read `ok` on each; HY's `spread_x4` is the hazard-cap error (a plain `ValueError`: "pillar 10Y at 2400 bp is above what a hazard of 5.0 reaches"), distressed's is `BootstrapArbitrageError` (the 5Y pillar at 4800 bp needs a negative hazard). The test asserts both statuses by name, the nan pattern, that the inputs are still written (×4 of the 5Y spread, the curve's R), that `on_error="raise"` raises naming the scenario, and that `"ignore"` is refused. On IG all 71 + 14 rows read `ok` (asserted in the timing test). Table 4, Chart 3 and every committed output are byte-identical to before the pre-step (`git status` after regeneration clean; the `is current` tests pass).

**Claim (item 49): on HY ×3 first order alone leaves 26.1% of pnl_full unexplained and the gamma term removes 87.6% of that, against the bars "over 5%" and "at least half".**
Rows (curve, scenario, pnl_full $, first order $, gamma $, residual after gamma $, residual %, first-order-only residual %, fraction removed):

| HY_steep | spread_x3 | 3034950.39 | 3828119.73 | −694996.53 | −98172.81 | −3.235 | −26.135 | 0.876 |

The same numbers as review 09; only the assertion changed. The other terms are zero (spreads only), so residual = pnl_full − first order − gamma, which the test also asserts.

**Claim (item 52): the Chart 3 cross-check that missed by 6e-6 on $720k passes under the output rule, and Table 3's 5Y CS01 is Table 2's `cs01_usd` on every curve.**
Rows (pair, curve or multiplier, value A, value B, |Δ|, allowed = max(1e-6, 1e-6 |B|)):

| Chart 3 pnl_full vs Table 4 spread_x3 | ×3 | 717179.06 | 717179.06 | < 6e-6 | 0.717 |
| Chart 3 second order vs Table 4 first + gamma | ×3 | 720360.30 | 720360.30 | < 6e-6 | 0.720 |
| Table 3 cs01_5y vs Table 2 cs01_usd ours | IG_flat | 4206.9303523496 | 4206.930352350 | 0 | 0.0042 |
| Table 3 cs01_5y vs Table 2 cs01_usd ours | HY_steep | 3828.1197315514 | 3828.119731551 | 0 | 0.0038 |
| Table 3 cs01_5y vs Table 2 cs01_usd ours | distressed_inverted | 2818.426930644 | 2818.426930644 | 0 | 0.0028 |

Table 2 stores 9 decimals in the Markdown and 10 in the CSV; the test reads the CSVs. Suite after the pre-step: 386 passed on Python 3.11.15 (the count is unchanged because the grid test was rewritten in place).

**Claim (README): every path resolves, Table 2 is first, the framing is in the first screen, the prose is under the limit.**
Rows (check, value, bar):

| relative links and images in README.md | 23, all exist | every one exists |
| chart PNGs embedded | 3 of 3 | all three |
| first table block | table_2_quantlib_validation | Table 2 first |
| characters before Table 2 | 1,259 | ≤ 2,000 ("first screen"); contains "illustrative", "validated", "QuantLib" |
| table blocks, each equal to its `.md` | 5 (Tables 2, 3, 5, 4, 1) | `sync_readme` is a no-op |
| words excluding tables and the code block | 1,495 | < 1,500 |
| headers naming a section number or a `.py` | 0 | 0 |

The one committed table the README does not show is `table_4_pnl_explain_full` (the 14-row file); `results.html` shows it. The test pins that difference. Every number in the prose was checked against the table it points at: the two `False` rows (0.541651 and 0.511638 bp against 0.5 → "by 0.04 and 0.01 bp on a 25% and 18% hazard"), the matched-node agreement (largest `diff` 4.7e-9 bp of hazard → "under 1e-8 bp"), HY theta ratio 56263.05 / 12453.69 = 4.5 → "over four times", distressed 148609.73 / 36678.82 = 4.05 → "a factor of four", Table 4's spread-scenario residuals 0.14, 0.44, 0.19% → "under half a percent", the recovery row 105.72 on −302.71 → "$100 on $300", Chart 2 CSV row `0.4` `implied_5y_default_prob` 0.0712918 → 7.13% = Table 1 IG 5Y `cum_default_prob` 0.071292.

**Claim (results page): one file, offline, every output once, regenerates identically.**
Rows (check, value, bar):

| size | 451,071 bytes | ≤ 5,000,000 |
| `<table id=…>` | 6, in `SECTIONS` order: 2, 3, 5, 4, 4-full, 1 | the 6 committed `.md` files, once each |
| `<img id=… src="data:image/png;base64,…">` | 3: chart 2, chart 3, chart 1 | the 3 committed PNGs, once each |
| `src=` not a data URI | 0 | 0 |
| `href=` | 1, the repo URL | the repo link only |
| `<script`, `<link`, `@import`, `url(` | 0 | 0 |
| fresh `build_results_html()` == committed | True | byte-identical |
| tag nesting (html.parser walk) | balanced, nothing left open | — |
| `make_results.py --check` | exit 0 | 0 |

**Claim (default-study sanity check): the IG curve's implied 5Y default probability is 4.6 times S&P's BBB five-year cumulative rate.**
Source: S&P Global Ratings, *Default, Transition, and Recovery: 2020 Annual Global Corporate Default And Rating Transition Study*, 7 April 2021, Table 24 "Global Corporate Average Cumulative Default Rates (1981-2020) (%)", read from the PDF copy at allnews.ch (pages 56 to 58) on 22 September 2026 after the 2024 and 2025 editions on spglobal.com returned HTTP 403. Rows (rating, 1Y, 2Y, 3Y, 4Y, 5Y % as printed):

| AAA | 0.00 | 0.03 | 0.13 | 0.24 | 0.34 |
| A | 0.05 | 0.13 | 0.22 | 0.33 | 0.46 |
| BBB | 0.16 | 0.43 | 0.75 | 1.14 | 1.54 |
| BB | 0.63 | 1.93 | 3.46 | 4.99 | 6.43 |
| B | 3.34 | 7.80 | 11.75 | 14.89 | 17.35 |
| CCC/C | 28.30 | 38.33 | 43.42 | 46.36 | 48.58 |

Implied (Chart 2 CSV, R = 0.40): 7.13%. Ratio 7.13 / 1.54 = 4.63. The README says "four and a half times" and gives the risk-neutral against real-world sentence without explaining it away. The HY (28.85%) and distressed (46.89%) `cum_default_prob` from Table 1 are not compared in the README because the illustrative levels were not chosen to sit in a rating bucket; the B and CCC/C figures are in `docs/DATA_NOTE.md` for a reader who wants to.

**Claim (basis example): one row, sign stated.**
Rows (bond, price, coupon, maturity, z-spread bp, CDS 5Y par spread bp from Table 1, basis bp):

| hypothetical 5Y bond of the IG name | not stated | not stated | 20 Jun 2031 | 110 (assumed) | 90 (Table 1, IG_flat 5Y) | −20 |

The README states the definition (s_CDS − z), the sign's meaning, the three usual drivers (funding, cheapest-to-deliver, par spread against the fixed-coupon contract's running cost) and that the bond side is assumed. No Z-spread is computed: the library has no bond pricer and the plan's `basis_example.py` would have typed the number in (Against the plan 1).

## Before / after

| metric | before (`42f2e9d`) | after |
|---|---|---|
| tests | 386 | 397 |
| `run()` on a grid with a failing scenario | raises | row with `status`, nan values (`on_error="skip"`) |
| `RUN_COLUMNS` | 12 | 13 (`status` second) |
| HY ×3 test | pins residual in (2, 5)% | first order > 5%, gamma removes ≥ half |
| `.md` text comparisons in tests | 6 | 0 |
| bare `abs=` literals in tests (comparisons) | 10 | 0 |
| output-against-output checks under the output rule | Chart 3 ×3 (abs=1e-6) | Chart 3 ×3 (3 columns), Table 3 vs Table 2 (3 curves), Table 3 vs report, Chart 2 steps |
| README | 16-line status stub | 1,495 words + 5 tables + 3 charts |
| `outputs/results.html` | — | 451,071 bytes, 6 tables, 3 charts |
| `cds.__doc__` | "None exist yet" | public objects per module |
| `.gitignore` | 10 patterns | + the stray docx |
| committed outputs (CSV, PNG, MD) | — | byte-identical |

## Not verified

- **The README as GitHub renders it.** Checked: the Markdown is well formed, the tables are the generator's own pipe tables with a blank line either side of the HTML comment markers (so the comment block closes before the table starts), and every image path resolves. Not checked: the rendered page on github.com after the push, because the session cannot open a browser. The user opening the repo page and seeing five tables and three charts settles it; if a table renders as text, the cause will be the comment markers and the fix is to move them onto their own paragraph.
- **`results.html` in a browser.** The HTML parses with balanced tags and no external reference; it was not opened in a browser here. Double-clicking `outputs/results.html` offline settles it.
- **The word count's definition.** 1,495 counts whitespace-separated tokens after removing the table blocks and the code block; Markdown link targets count as part of their word. A different tokeniser could read 1,450 or 1,550. The test uses this definition.
- **The 2020 S&P figure against the current edition.** Later editions were not retrievable (HTTP 403). The BBB five-year rate in the 2024 edition is believed to be within a few tenths of a percent of 1.54; reading it would settle it and would not change the "four and a half times" sentence.

## Open

Nothing tried and unexplained.

## Against the plan

1. **The plan's files `scripts/basis_example.py`, `scripts/implied_vs_historical.py`, `data/defaults/cumulative_default_rates.csv`, `data/defaults/README.md`, Tables 6 and 7 were not created.** The session prompt replaced them with a one-paragraph basis note plus a prose worked example off Table 1, and a two-sentence default-study check with a web-sourced figure cited in the text; both are in the README, the source is in `docs/DATA_NOTE.md`. A Table 6 would have held one row of typed-in numbers and a Table 7 one row, which is the arithmetic the README does in a sentence. Accept the prose form, or should the two one-row tables be committed as well?
2. **`scripts/make_results.py`, not the plan's `scripts/build_results_page.py`**, as the prompt named it. It also syncs the README's table blocks (`sync_readme`), which the plan did not ask for: it is how "embeds by path and computes nothing" is made checkable for tables, which GitHub cannot include from a file. Accept?
3. **`tests/test_readme_paths.py` carries the results-page and housekeeping tests too** (11 tests), rather than a second file. Accept?
4. **Table 1 and Chart 1 are placed in the basis and default-study sections**, not in a section of their own, because the prompt's order had no slot for them and both sections point at them. Accept the placement?
5. **`RUN_COLUMNS` changed** (item 51 accepted the twelve; item 50 adds `status`). Placed second so a reader sees the row's validity before its values. Accept the position?
6. **`error_status` reports the hazard-cap failure as `ValueError`**, its class, as item 50 says ("status = the error class"). It is less informative than `BootstrapArbitrageError`; a named `HazardCapError(ValueError)` in `cds/bootstrap.py` would make the two failures distinguishable by class, but it is a Section 6 file. Leave as is, or add the class?
7. **The README's word limit is met with a 5-word margin** (1,495). Cutting further would have removed a pointer at a table. Accept?
8. **The default-study figure is from the 2020 edition**, not the latest. Stated in the README and the data note. Accept, or should the sentence be dropped until a current edition is read?

## Reviewer reads (max 6, in order)

1. `README.md` — the whole page, on github.com, checking that five tables and three charts render and that every sentence with a number points at a table that carries it.
2. `outputs/results.html` — open offline; the six tables and three charts in the README's order.
3. `scripts/make_results.py` — `SECTIONS`, `render_table`, `render_chart`, `sync_readme`.
4. `tests/test_readme_paths.py` — what the acceptance criteria are held to.
5. `cds/scenarios.py` — `run()` and `error_status` (item 50).
6. `tests/conftest.py` — `assert_output_value` (item 52) and the two new constants.
