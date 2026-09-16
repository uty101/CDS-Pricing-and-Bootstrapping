# Review — Section 02 — the SOFR OIS discount curve

Date: 2026-09-16   Commit: 6fa5fa7   Tests: 138/138 (113 from Section 1, 25 new; 0 skipped)

Two commits again, code then review, so the review can cite the code sha.
The session opened with `d555969 Section 02: resolved Section 1 questions`,
which appended items 10 to 12 to `docs/CONVENTIONS_RESOLVED.md` from the
user's prompt.

## What changed

- `cds/curves.py` (new) — `DiscountCurve`, a frozen dataclass of `(as_of, node_dates, node_dfs)` plus the inputs it was solved from (`tenors`, `par_rates_pct`, `calendar`, kept for Section 8's IR01). `df(t)`, `forward(t1, t2)`, `zero_rate(t)`, `df_on(date)`. `bootstrap_ois(as_of, tenors, par_rates_pct, calendar)`, `ois_payment_dates`, `par_rate_from_curve`, `read_rates_file`, `discount_curve_from_file`. Survival and recovery curves are Section 3.
- `data/rates/sofr_ois_2026-09-15.json` (new) — 13 tenors, 1M to 30Y, with `source`, `source_url`, `snapshot_taken`, `note`, plus `source_by_tenor` and `source_urls`.
- `data/rates/README.md`, `docs/DATA_NOTE.md` — the snapshot recorded: what each row is, where it was read, and the ICE Swap Rate substitution (below).
- `tests/conftest.py` — two constants: `CURVE_IDENTITY_ABS_TOL = 1e-12` (interpolation identities are exact in exact arithmetic) and `QL_DISCOUNT_ABS_TOL = 1e-10` (two bootstraps of the same equations agree to solver precision).
- `tests/test_discount.py` (25 tests) — the plan's five criteria, hand solutions of the 1Y and 2Y nodes, date and construction checks, and a QuantLib oracle.
- `docs/CONVENTIONS_RESOLVED.md` — items 10 to 12 (committed first, d555969).

**Rules stated in full.**

1. Nodes sit at each OIS maturity, the last payment date of the tenor. Time is act/365F years from `as_of`. Between nodes ln P(t) is linear in t (a flat continuously compounded forward per interval). Before the first node ln P is linear from (0, 0), which is a flat forward at the first node's zero rate. Beyond the last node the last interval's forward is extrapolated flat.
2. An OIS of tenor T with par rate K, annual fixed act/360 payments on T_1..T_m (anniversaries of the spot date rolled Following on the weekend-only calendar; a single payment at T under one year) satisfies K·Σ_k Δ_k P(T_k) = 1 − P(T_m). Spot date = `as_of` (T+0).
3. Nodes are solved shortest tenor first with `scipy.optimize.brentq` on P(T_m) in [1e-8, 2], xtol 1e-14. A payment date between the previous node and the node being solved is interpolated log-linearly against the unknown, so the built curve reprices each input with its own interpolation and nothing is re-solved afterwards.
4. `forward(t1, t2) = (ln P(t1) − ln P(t2)) / (t2 − t1)`, continuously compounded; `zero_rate(t) = −ln P(t)/t`.
5. `read_rates_file` raises if `as_of`, `tenors`, `par_rates_pct`, `source`, `source_url`, `snapshot_taken` or `note` is missing or empty, or if the file is not `annual` / `act/360`, the only convention `bootstrap_ois` implements.

## Findings

**Claim: the built curve reprices every input OIS to its par rate.**
Number: 13 tenors, worst |Δ| = 1.4e-10 bp (the 1M node; every other tenor is under 2e-12 bp), against the bar `OIS_REPRICE_BP = 0.01`.
Rows — the node table (par rate in %, zero rate continuously compounded act/365F, forward over the interval from the previous node):

| tenor | par rate % | node date | t (act/365F) | P | zero % | forward % | reprice diff (bp) |
|---|---|---|---|---|---|---|---|
| 1M | 3.88572 | 2026-10-15 | 0.082192 | 0.9967723514 | 3.93332 | 3.93332 | -1.4e-10 |
| 3M | 3.97991 | 2026-12-15 | 0.249315 | 0.9900398741 | 4.01502 | 4.05520 | -2.1e-12 |
| 6M | 4.12897 | 2027-03-15 | 0.495890 | 0.9796626505 | 4.14346 | 4.27331 | 7.1e-13 |
| 1Y | 4.30000 | 2027-09-15 | 1.000000 | 0.9582240914 | 4.26736 | 4.38925 | -3.6e-13 |
| 2Y | 4.48000 | 2028-09-15 | 2.002740 | 0.9148088391 | 4.44592 | 4.62399 | -8.9e-14 |
| 3Y | 4.56000 | 2029-09-17 | 3.008219 | 0.8727178257 | 4.52570 | 4.68462 | 1.8e-13 |
| 4Y | 4.55000 | 2030-09-16 | 4.005479 | 0.8346006851 | 4.51386 | 4.47816 | -2.7e-13 |
| 5Y | 4.55000 | 2031-09-15 | 5.002740 | 0.7978931667 | 4.51314 | 4.51022 | 0.0 |
| 7Y | 4.56000 | 2033-09-15 | 7.005479 | 0.7284299233 | 4.52309 | 4.54793 | 8.9e-14 |
| 10Y | 4.60000 | 2036-09-15 | 10.008219 | 0.6330764890 | 4.56789 | 4.67241 | 8.9e-14 |
| 15Y | 4.70000 | 2041-09-16 | 15.013699 | 0.4945695590 | 4.68950 | 4.93266 | -1.7e-12 |
| 20Y | 4.74000 | 2046-09-17 | 20.019178 | 0.3872854260 | 4.73842 | 4.88516 | -1.1e-12 |
| 30Y | 4.66000 | 2056-09-15 | 30.021918 | 0.2520147449 | 4.59087 | 4.29557 | -8.9e-14 |

Reading the table: the 1M zero rate (3.933%) sits above its par rate (3.886%) because par is act/360 simple and the zero is act/365F continuous, 3.886 × 365/360 = 3.940 less a little for compounding. The 3Y and 4Y nodes land on Mon 17 Sep 2029 and Mon 16 Sep 2030 because 15 Sep falls on a weekend in both years; the 15Y and 20Y likewise. The 20Y to 30Y forward (4.296%) is below the 20Y zero because the 30Y par rate (4.66%) is under the 20Y (4.74%); this forward is what the curve extrapolates beyond 30Y. The 1Y and 2Y nodes were also solved by hand in the tests: P(1Y) = 1/(1 + K·Δ) and P(2Y) = (1 − K·Δ_1·P_1)/(1 + K·Δ_2), both equal to the solver's to 1e-12.

**Claim: ln P is linear between adjacent nodes.**
Number: 13 intervals (including [0, 1M]), 7 points each, worst |second difference of ln P| = 2.2e-16 against the bar 1e-12.
Rows (worst second difference per interval, in node order): 1.1e-16, 5.1e-17, 1.1e-16, 8.3e-17, 1.4e-16, 6.9e-17, 1.7e-16, 1.7e-16, 1.7e-16, 1.7e-16, 2.2e-16, 2.2e-16, 2.2e-16. Before the first node, P(t) = exp(−z_1·t) with z_1 = 3.93332% at 7 points to 1e-12.

**Claim: the forward beyond the last node is the last interval's forward, and P is monotone.**
Number: f(20Y, 30Y) = 4.295567%; on the four intervals (30Y, 30.5Y), (30.5Y, 35Y), (35Y, 45Y), (45Y, 60Y) the forward differs from it by at most 1.4e-16. On the daily grid of 21,901 points from 0 to 60Y every step of P is ≤ 0 (largest step −8.2e-6, the first day); P(60Y) = 0.069530.

**Claim: `forward(t1, t2)` reproduces P(t2)/P(t1) = exp(−f·(t2 − t1)).**
Number: 8 pairs, worst |Δ| = 1.1e-16 against the bar 1e-12.
Rows (t1, t2, f, Δ): (0, 0.5, 4.1455%, 0); (2.5, 7.3, 4.5477%, 0); (9.99, 10.01, 4.6956%, 1.1e-16); (25, 45, 4.2956%, −5.6e-17); (35, 60, 4.2956%, 0). The last two straddle and lie beyond the 30Y node and return the extrapolated forward.

**Claim: the curve is the same one QuantLib builds from the same inputs.** (Not a plan criterion; added because the reprice test alone cannot tell a wrong-but-self-consistent bootstrap from a right one.)
Number: `ql.PiecewiseLogLinearDiscount(as_of, helpers, Actual365Fixed())` with 13 `ql.OISRateHelper(0, tenor, rate, ql.Sofr(), …, Following, Annual, WeekendsOnly())`: every pillar date equal to ours, |ΔP| ≤ 1.5e-13 at all 13 nodes and ≤ 1.9e-13 on 50 points from 0.01 to 40Y (past the last node, with extrapolation on), against the bar 1e-10.
Rows (tenor, QuantLib P, ours, Δ):

| 1M | 0.9967723514 | 0.9967723514 | -5.6e-15 |
| 1Y | 0.9582240914 | 0.9582240914 | 1.1e-16 |
| 5Y | 0.7978931667 | 0.7978931667 | 0.0 |
| 10Y | 0.6330764890 | 0.6330764890 | 1.2e-13 |
| 30Y | 0.2520147449 | 0.2520147449 | -1.5e-13 |

**Claim: the data file carries its provenance and the test reads it.**
Number: 4 required string fields non-empty, 13 rows each with a `source_by_tenor` label, `as_of = 2026-09-15`, `snapshot_taken = 2026-09-16`; a copy of the file with `source_url` blanked raises `ValueError` naming the field.
Rows (tenor, rate, label):

| 1M | 3.88572 | CME Term SOFR 1M, 15 Sep 2026 fixing, read from global-rates.com |
| 6M | 4.12897 | CME Term SOFR 6M, 15 Sep 2026 fixing, read from global-rates.com |
| 1Y | 4.30 | BlueGamma USD SOFR swap rate 1Y, 15 Sep 2026 close |
| 5Y | 4.55 | BlueGamma USD SOFR swap rate 5Y, 15 Sep 2026 close |
| 30Y | 4.66 | BlueGamma USD SOFR swap rate 30Y, 15 Sep 2026 close |

Cross-check between the two sources: BlueGamma's own 1M and 3M rows read 3.89 and 3.98, the Term SOFR fixings rounded to 2 dp. Its 12M Term SOFR counterpart is 4.38538 against BlueGamma's 1Y of 4.30, an 8.5 bp gap, which is the Term-SOFR-over-OIS basis at 1Y plus rounding; the 1Y row is taken from BlueGamma, per convention 4's split.

## Before / after

Nothing numerical existed before this section. The first state is the node table above. Two things the reviewer may want to hold onto for Section 4 and Section 7: the 5Y discount factor 0.7978931667 (t = 5.002740) and the 20Y to 30Y forward 4.295567% that the curve extrapolates.

## Not verified

- **Whether the sources' own conventions are the annual-fixed act/360 OIS the bootstrap assumes.** BlueGamma says "mids built from interdealer broker and exchange quotes" and does not state the fixed-leg frequency or day count; Term SOFR is a simple act/360 term rate, not an OIS. Both are close to the assumed convention; a difference of annual versus semi-annual fixed at 5Y is about 5 bp of rate. What would settle it: BlueGamma's methodology page (behind a sign-up) or an ICE Swap Rate fixing, whose convention is published (annual act/360 versus compounded SOFR).
- **The 0.5 bp rounding on the 1Y to 30Y rows** (2 dp on the page). Not fixable from the free page; a 0.5 bp rate error moves a 5Y CDS upfront by roughly 0.5 bp × annuity × spread/rate sensitivity, well under the Section 7 bar of 1 bp.
- **Behaviour on holiday calendars.** `bootstrap_ois` takes `calendar` and the tests use the default weekend-only one throughout, as the plan specifies. The `us_uk` path is exercised by nothing here.
- **Negative rates.** The Brent bracket allows P up to 2, so negative par rates would solve, but no test uses one.
- **Whether QuantLib's `OISRateHelper` with `ql.Sofr()` rolls anniversaries on `WeekendsOnly()` or on SOFR's own calendar.** The pillar dates matched ours on all 13 tenors for this `as_of`, which is the evidence; a different `as_of` where a US holiday falls on an anniversary would tell the two apart.

## Open

Nothing tried and unexplained.

## Against the plan

1. **ICE Swap Rate replaced by BlueGamma for 1Y to 30Y.** `docs/CONVENTIONS_RESOLVED.md` item 4 names ICE Swap Rate. On 16 Sep 2026 ice.com published no USD SOFR fixings on a free page: the ICE Swap Rate page carries methodology PDFs and holiday calendars, the report centre's IBA category lists only a monthly volume report, and the values are licensed. The plan's Part A.2 row 2 asks for "a published swap-rate page", which BlueGamma's is. Every row is labelled with its source in the file. If the reviewer would rather the 1Y to 30Y rows came from elsewhere, the file is the only thing that changes; the code and tests do not depend on the numbers.
2. **Snapshot dated 15 Sep 2026, one day before the session.** Convention 4 says the snapshot date is the date of the Section 2 session. At the time of reading (10:20 New York) the 16 Sep 11:00 fixing had not happened and the Term SOFR republisher showed 15 Sep as its latest, so the last complete set is 15 Sep. `as_of` in the file is 2026-09-15 and `snapshot_taken` is 2026-09-16. Every illustrative curve from Section 6 on is therefore valued on 15 Sep 2026 (a Tuesday, a business day, so convention 10 is satisfied).
3. **Two extra fields in the rates file**, `source_by_tenor` and `source_urls`, beyond the Part D.3 format, so that convention 4's "each row labelled with its source" is in the file rather than only in the README.
4. **One test beyond the plan's list**, the QuantLib oracle, with its own constant `QL_DISCOUNT_ABS_TOL`. QuantLib is imported in the test only, as in Section 1.
5. **`DiscountCurve` carries `tenors`, `par_rates_pct`, `calendar`, `node_times`, `zero_rate`, `df_on`** beyond the protocol's `as_of`, `df`, `forward` and the plan's `node_dates`, `node_dfs`. The first three are what Section 8 needs to rebuild for IR01 ("the discount curve keeps its input par rates"); the rest are conveniences. `with_as_of` is Section 3's, as the plan places it.
6. **`df(t)` accepts an array as well as a float** and returns an array in that case. The protocol says float; the array path is used by the 21,901-point monotonicity test and will be what Section 9's vectorised legs call.
7. The stray `11_CDS_Pricing_Bootstrap.docx` at the repo root, noted in review 01, is still there and still untracked.

## Reviewer reads (max 6, in order)

1. `data/rates/sofr_ois_2026-09-15.json` — the numbers, the labels, and the `note` that records the substitution.
2. `cds/curves.py` — the docstring's par equation and interpolation rule, then `bootstrap_ois` (the log-linear interpolation against the unknown node) and `_log_linear`.
3. `tests/test_discount.py` — criteria 1 to 5 in order, the two by-hand nodes, and the QuantLib oracle at the end.
4. `docs/DATA_NOTE.md` — the Section 2 paragraph, which is what the README will cite.
5. `tests/conftest.py` — the two new constants and their reasons.
