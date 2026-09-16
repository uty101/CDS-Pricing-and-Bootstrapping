# Review — Section 03 — the survival and recovery curves

Date: 2026-09-16   Commit: 87d828a   Tests: 169/169 (138 from Sections 1 and 2, 31 new; 0 skipped)

Two commits again, code then review. The session opened with
`529b35d Section 03: resolved Section 2 questions`, which appended items 13
and 14 to `docs/CONVENTIONS_RESOLVED.md` from the user's prompt and made
`tests/test_repo_hygiene.py` also skip `tokenize.FSTRING_MIDDLE` tokens
where the attribute exists (Python 3.12 splits f-strings into parts; the
`"act/360"` inside an error message in `cds/curves.py` is otherwise read as
code). The attribute is looked up with `getattr`, so on the pinned 3.11 the
skip tuple is unchanged; the suite was 138/138 on 3.11 before and after.

## What changed

- `cds/curves.py` (extended) — `SurvivalCurve`, a frozen dataclass of `(as_of, pillar_dates, pillar_hazards)` with `pillar_times` (act/365F) computed at construction; `Q(t)`, `cumulative_hazard(t)`, `hazard(t)`, `density(t)`, `Q_on(date)`, `SurvivalCurve.flat(as_of, hazard, pillar_dates=None)`; `RecoveryCurve` of `(as_of, recovery)` with `RecoveryCurve.flat(R, as_of)` and `R(t)`; `standard_pillar_dates(as_of)`; `with_as_of(new_as_of, mode)` on `DiscountCurve`, `SurvivalCurve` and `RecoveryCurve`, `mode in ("calendar", "tenor")`. `Q`, `hazard`, `density`, `R` accept an array as well as a float, as `df` already did.
- `tests/conftest.py` — two constants: `DENSITY_INTEGRAL_ABS_TOL = 1e-9` (the plan's bar for the quad integral) and `QL_SURVIVAL_ABS_TOL = 1e-12` (QuantLib integrates the same piecewise-constant hazard over the same act/365F times; float noise).
- `tests/test_survival.py` (31 tests) — the plan's six criteria, construction and validation checks, the discount curve's two shift modes, the recovery curve, and a QuantLib oracle.
- `docs/CONVENTIONS_RESOLVED.md` — items 13 and 14 (committed first, 529b35d).
- `tests/test_repo_hygiene.py` — the FSTRING_MIDDLE skip (same commit).

**Rules stated in full.**

1. Pillar i has date `pillar_dates[i]`, time t_i = act/365F years from `as_of`, and hazard λ_i, which is flat on (t_{i−1}, t_i] with t_0 = 0. Pillar dates must be strictly increasing and after `as_of`; hazards must be finite and non-negative (zero is allowed; a negative one raises `ValueError`).
2. Cumulative hazard H(t) = Σ_{k<i} λ_k (t_k − t_{k−1}) + λ_i (t − t_{i−1}) for t in (t_{i−1}, t_i]; Q(t) = exp(−H(t)); Q(0) = 1. Beyond the last pillar λ_n continues flat. Negative t raises.
3. `hazard(t)` = λ_i for t in (t_{i−1}, t_i]; `hazard(0)` = λ_1; beyond t_n it is λ_n. So `hazard(t_i)` = λ_i and `hazard(t_i + ε)` = λ_{i+1}, the values the plan's criterion 5 asks for. This is the closed-right-end convention of QuantLib's backward-flat `HazardRateCurve` (checked in the oracle test, rows below).
4. `density(t)` = λ(t)·Q(t) = −dQ/dt.
5. `RecoveryCurve.flat(R, as_of)`: `R(t)` returns the constant for any t ≥ 0; R must lie in [0, 1].
6. `with_as_of(new_as_of, "calendar")`: nodes stay on their dates; nodes on or before `new_as_of` are dropped; times are recomputed from `new_as_of`. For the survival curve the surviving hazards are unchanged. For the discount curve the surviving discount factors are divided by P_old(new_as_of), so every ratio P(d2)/P(d1) and every forward between the same two dates is unchanged; the `tenors` and `par_rates_pct` inputs are not carried because the nodes no longer sit at OIS maturities from the new date. `new_as_of` before `as_of` raises in this mode.
7. `with_as_of(new_as_of, "tenor")`: every node date moves by `(new_as_of − as_of)` days; times, hazards, discount factors and (for the discount curve) the inputs are unchanged, so the curve is the same function of t.
8. `standard_pillar_dates(as_of)` = `standard_maturity(as_of, p)` for p in `PILLARS`. On 15 Sep 2026 that is 20 Dec 2026, 20 Jun 2027, 20 Jun 2028, …, 20 Jun 2036 (the roll anchor is 20 Mar 2026, so the 6M pillar is three months out and every later pillar is a 20 June).

## Findings

The test curves: "flat" is λ = 1.67% on the eight standard pillars from 15 Sep 2026; "three" is λ = (1%, 2%, 3%) on pillars at exactly 1, 3 and 5 act/365F years (dates `as_of + 365·k` days: 15 Sep 2027, 14 Sep 2029, 14 Sep 2031; the 2028 leap day is why the last two are the 14th); "steep" is λ = 1% to 8% in 1% steps on the standard pillars, the shape Section 4 will reuse. The steep curve's pillar table, which is what the other rows are read against:

| pillar | date | t (act/365F) | λ % | Q | 1 − Q |
|---|---|---|---|---|---|
| 6M | 2026-12-20 | 0.263014 | 1 | 0.9973733188 | 0.0026266812 |
| 1Y | 2027-06-20 | 0.761644 | 2 | 0.9874763422 | 0.0125236578 |
| 2Y | 2028-06-20 | 1.764384 | 3 | 0.9582132453 | 0.0417867547 |
| 3Y | 2029-06-20 | 2.764384 | 4 | 0.9206411666 | 0.0793588334 |
| 4Y | 2030-06-20 | 3.764384 | 5 | 0.8757409670 | 0.1242590330 |
| 5Y | 2031-06-20 | 4.764384 | 6 | 0.8247417834 | 0.1752582166 |
| 7Y | 2033-06-20 | 6.767123 | 7 | 0.7168585685 | 0.2831414315 |
| 10Y | 2036-06-20 | 9.769863 | 8 | 0.5637773413 | 0.4362226587 |

**Claim (criterion 1): a flat hazard gives Q(t) = exp(−λt), past the last pillar.**
Number: 50 points from 0 to 15Y (last pillar at 9.77Y), worst |Δ| = 1.1e-16 against the bar `CURVE_IDENTITY_ABS_TOL = 1e-12`; the array path gives the same.
Rows (t, Q, exp(−λt), Δ):

| 0.000000 | 1.000000000000 | 1.000000000000 | 0 |
| 0.306122 | 0.994900800386 | 0.994900800386 | 0 |
| 3.061224 | 0.950162317003 | 0.950162317003 | 0 |
| 7.653061 | 0.880023979500 | 0.880023979500 | 0 |
| 10.102041 | 0.844758846061 | 0.844758846061 | 0 |
| 15.000000 | 0.778411480014 | 0.778411480014 | 0 |

**Claim (criterion 2): the three-pillar curve gives Q(4) = exp(−(0.01·1 + 0.02·2 + 0.03·1)).**
Number: |Δ| = 0 at t = 4; the cumulative hazard is also checked by hand at five other points, worst |Δ| = 0.
Rows (t, H by hand, H from the curve, Q, exp(−H), Δ):

| 0.5 | 0.005 | 0.005000000000 | 0.995012479193 | 0.995012479193 | 0 |
| 1.0 | 0.01 | 0.010000000000 | 0.990049833749 | 0.990049833749 | 0 |
| 3.0 | 0.05 | 0.050000000000 | 0.951229424501 | 0.951229424501 | 0 |
| 4.0 | 0.08 | 0.080000000000 | 0.923116346387 | 0.923116346387 | 0 |
| 5.0 | 0.11 | 0.110000000000 | 0.895834135297 | 0.895834135297 | 0 |
| 8.0 | 0.20 | 0.200000000000 | 0.818730753078 | 0.818730753078 | 0 |

The 8Y row is past the 5Y pillar and uses the extrapolated 3%: 0.11 + 0.03·3 = 0.20.

**Claim (criterion 3): the density integrates to 1 − Q(T).**
Number: `scipy.integrate.quad` per pillar interval (`epsabs = epsrel = 1e-13`), T = 2.5, 5, 12 on both the steep and the three-pillar curve, worst |Δ| = 5.6e-17 against the bar `DENSITY_INTEGRAL_ABS_TOL = 1e-9`.
Rows (curve, T, intervals integrated, ∫ density, 1 − Q(T), Δ, quad's own error estimate summed):

| steep | 2.5 | 4 | 0.069571074590 | 0.069571074590 | 1.4e-17 | 7.7e-16 |
| steep | 5.0 | 7 | 0.188749246533 | 0.188749246533 | 5.6e-17 | 2.1e-15 |
| steep | 12.0 | 9 | 0.528344696468 | 0.528344696468 | 0 | 5.9e-15 |
| three | 2.5 | 2 | 0.039210560848 | 0.039210560848 | −3.5e-17 | 4.4e-16 |
| three | 5.0 | 3 | 0.104165864703 | 0.104165864703 | −2.8e-17 | 1.2e-15 |
| three | 12.0 | 4 | 0.273850962926 | 0.273850962926 | 0 | 3.0e-15 |

The 12Y rows integrate past the last pillar, so the extrapolated hazard is exercised too. A second test checks `density(t) == hazard(t)·Q(t)` at 25 points to 1e-12.

**Claim (criterion 4, survival, calendar mode): shifting `as_of` by +30 days with nodes fixed in date leaves Q(d2)/Q(d1) unchanged between pillar dates.**
Number: 7 adjacent-pillar ratios on the steep curve, worst |Δ| = 1.1e-16 against the bar 1e-12; the same ratio between two arbitrary dates (24 Dec 2026, 12 May 2031) is 0.832414589543 on both curves. Pillar dates and hazards are identical before and after; each pillar time falls by exactly 30/365 (the first three: 0.263014 → 0.180822, 0.761644 → 0.679452, 1.764384 → 1.682192).
Rows (d1 → d2, Q(d2)/Q(d1) before, after, Δ):

| 2026-12-20 → 2027-06-20 | 0.990076958774 | 0.990076958774 | 1.1e-16 |
| 2027-06-20 → 2028-06-20 | 0.970365774180 | 0.970365774180 | 0 |
| 2028-06-20 → 2029-06-20 | 0.960789439152 | 0.960789439152 | 0 |
| 2029-06-20 → 2030-06-20 | 0.951229424501 | 0.951229424501 | 0 |
| 2030-06-20 → 2031-06-20 | 0.941764533584 | 0.941764533584 | 0 |
| 2031-06-20 → 2033-06-20 | 0.869191525148 | 0.869191525148 | 0 |
| 2033-06-20 → 2036-06-20 | 0.786455468374 | 0.786455468374 | 0 |

What does change, as it should: Q at the first pillar rises from 0.9973733 to 0.9981934 because 30 fewer days of 1% hazard lie between the new `as_of` and 20 Dec 2026.

**Claim (criterion 4, survival, tenor mode): shifting by +30 days with nodes fixed in tenor leaves `pillar_times` and `pillar_hazards` unchanged.**
Number: 8 pillars, |Δt| = 0 and |Δλ| = 0 exactly (the day counts are identical integers); Q on 25 points from 0 to 12Y agrees to 0.
Rows (pillar, date before, date after, t before, t after):

| 6M | 2026-12-20 | 2027-01-19 | 0.263014 | 0.263014 |
| 1Y | 2027-06-20 | 2027-07-20 | 0.761644 | 0.761644 |
| 5Y | 2031-06-20 | 2031-07-20 | 4.764384 | 4.764384 |
| 7Y | 2033-06-20 | 2033-07-20 | 6.767123 | 6.767123 |
| 10Y | 2036-06-20 | 2036-07-20 | 9.769863 | 9.769863 |

**Claim (criterion 4, discount, both modes): calendar mode drops passed nodes and keeps DF ratios and forwards; tenor mode keeps times, DFs and inputs.**
Number: shift +45 days (to 30 Oct 2026, past the 1M node of 15 Oct 2026). Calendar mode: 13 nodes → 12, every surviving P divided by P_old(30 Oct 2026) = 0.9951125914, worst |Δ| in adjacent-node ratios = 1.1e-16; forwards between the same dates agree to 3.5e-16; `tenors` and `par_rates_pct` are empty on the result. Tenor mode: `node_times`, `node_dfs`, `tenors`, `par_rates_pct` all equal to the original's (tuple equality); first node date 15 Oct → 29 Nov 2026.
Rows, calendar mode (node date, P before, P after, ratio after/before):

| 2026-12-15 | 0.9900398741 | 0.9949023685 | 1.0049114127 |
| 2027-09-15 | 0.9582240914 | 0.9629303253 | 1.0049114127 |
| 2031-09-15 | 0.7978931667 | 0.8018119494 | 1.0049114127 |
| 2036-09-15 | 0.6330764890 | 0.6361857889 | 1.0049114127 |
| 2056-09-15 | 0.2520147449 | 0.2532524934 | 1.0049114127 |

The constant ratio 1.0049114127 = 1/0.9951125914 is the point: one rescaling, so every ratio between nodes survives. Forward rows (d1 → d2, f before %, f after %, Δ): 30 Oct 2026 → 15 Dec 2026, 4.055205, 4.055205, −3.5e-16 (the new curve's first interval reproduces the old 1M–3M forward); 1 Jan 2028 → 1 Jan 2029, 4.641876, 4.641876, 3.5e-17; 1 Jan 2040 → 1 Jan 2050, 4.699274, 4.699274, 0.

**Claim (criterion 5): `hazard(t_i)` is λ_i and `hazard(t_i + 1e-9)` is λ_{i+1}.**
Number: 8 pillars on the steep curve and 3 on the three-pillar curve, all equal exactly; `hazard(0)` = λ_1 = 1%; `hazard(30)` = λ_8 = 8%.
Rows, steep (pillar, t_i, hazard(t_i) %, hazard(t_i + 1e-9) %):

| 6M | 0.263014 | 1 | 2 |
| 1Y | 0.761644 | 2 | 3 |
| 5Y | 4.764384 | 6 | 7 |
| 7Y | 6.767123 | 7 | 8 |
| 10Y | 9.769863 | 8 | 8 |

**Claim (criterion 6): negative hazards raise at construction.**
Number: 2 cases raise `ValueError` (−1% on the last pillar; −1e-12 on the first). Also raising: no pillars, length mismatch, pillars out of order, a pillar on `as_of`, a NaN hazard, negative t in `Q`, a recovery outside [0, 1], an unknown shift mode, a backward calendar shift. Zero hazard is allowed and gives Q(7) = 1 exactly.

**Claim: Q is a survival probability.**
Number: on a daily grid of 7,301 points from 0 to 20Y on the steep curve, Q(0) = 1, every step ≤ 0, every value in (0, 1].

**Claim: the curve is the one QuantLib builds from the same pillars.** (Not a plan criterion; added because Section 7 will hand QuantLib exactly this construction, `ql.HazardRateCurve([as_of, *pillar_dates], [λ_1, λ_1, …, λ_n], Actual365Fixed())`, and the closed-end convention of the intervals is the thing most likely to be silently different.)
Number: 50 points from 0 to 14Y on both curves (extrapolation on), worst |Δ Q| = 1.1e-16 against the bar `QL_SURVIVAL_ABS_TOL = 1e-12`; Q at every pillar date equal; `oracle.hazardRate(t_i)` = λ_i at every pillar on both curves, which confirms QuantLib also reads the interval as closed on the right.
Rows (curve, t, QuantLib Q, ours, Δ):

| steep | 0.285714 | 0.996920602373 | 0.996920602373 | 0 |
| steep | 2.000000 | 0.949224836503 | 0.949224836503 | 0 |
| steep | 10.000000 | 0.553492626056 | 0.553492626056 | 0 |
| steep | 14.000000 | 0.401918137438 | 0.401918137438 | −5.6e-17 |
| three | 4.857143 | 0.899681663262 | 0.899681663262 | 0 |
| three | 14.000000 | 0.683861409212 | 0.683861409212 | 1.1e-16 |

## Before / after

Nothing numerical existed before this section for the survival or recovery curves. The discount curve's node table from review 02 is unchanged (the `with_as_of` methods return new objects; the Section 2 tests still pass on the original). Two numbers to hold onto: on the steep test curve Q(5Y pillar, 20 Jun 2031) = 0.8247417834, and the calendar-shift rescaling for +45 days on the Section 2 discount curve is 1/0.9951125914.

## Not verified

- **Calendar mode when the new `as_of` passes the first pillar.** The drop rule is tested (a shift to exactly the 6M pillar date drops it, a day before keeps it, a shift to the last pillar raises), but no pricing consequence is checked; the surviving first interval keeps λ_2 from the new `as_of` to the 1Y pillar, which is what "hazards between the same dates are unchanged" requires. Section 8's 1-month theta never crosses a pillar from the snapshot date (6M pillar is 96 days out), so this path is not exercised by the plan's outputs. What would settle it: a Section 8 test shifting past the 6M pillar and checking Q(1Y pillar) against the original's Q(1Y)/Q(new_as_of).
- **Tenor mode on the discount curve keeps the old node dates shifted by days rather than re-bootstrapping the same par rates from the new date.** The plan says "shifts every pillar date", so that is what is implemented, and it gives an identical function of t. Re-bootstrapping from the new `as_of` would move nodes that land on weekends (the 3Y and 4Y nodes, for instance) by a day or two and change P at the fourth decimal of a basis point. Neither is wrong; the plan's reading is the one that makes theta-rolldown a pure curve-shape effect. Section 8 should state which one it uses.
- **The `us_uk` calendar path, negative rates, holiday behaviour** — unchanged from review 02's list; nothing here touches them.
- **Array inputs to `hazard` at exactly a pillar time.** `np.searchsorted(..., side="left")` gives the same answer for arrays as for floats and the vectorised `density` test passes through pillar times, but no test asserts the array path at `t_i` specifically.

## Open

Nothing tried and unexplained.

## Against the plan

1. **The plan calls criterion 5 "right-continuous"; the values it asks for are left-continuous.** λ_i flat on (t_{i−1}, t_i] means `hazard(t_i)` = λ_i and `hazard(t_i + ε)` = λ_{i+1}, which is a function continuous from the left at t_i. The code and the test implement the stated values, not the label, and the docstring says "closed right end". QuantLib's backward-flat `HazardRateCurve` returns the same values at the pillars (oracle rows). Is the reviewer content with the values as stated in the plan's criterion, with the word "right-continuous" treated as a slip?
2. **Calendar mode drops passed pillars on the survival curve too.** The plan states the drop rule only for `DiscountCurve` and says the survival curve "keeps `pillar_dates` and recomputes times". A pillar on or before the new `as_of` would have a non-positive time and the constructor rejects it, so keeping such a pillar is not possible; dropping it and keeping the remaining hazards is the only reading under which "nodes fixed in date" is well defined. For the 30-day shift the plan tests, no pillar is dropped and the result is exactly as the plan describes.
3. **Extra public names beyond the plan's list**: `cumulative_hazard(t)`, `Q_on(date)`, `SurvivalCurve.flat(...)`, `standard_pillar_dates(as_of)`, and array support on `Q`, `hazard`, `density`, `R`. The first is the quantity the closed form is built from; the others are the survival-side twins of `df_on`, `bootstrap_ois` and Section 2's array `df`, and Section 6 will need `standard_pillar_dates`. None changes a `types.py` protocol.
4. **`RecoveryCurve` is a dataclass with a `recovery` field, not a subclass or protocol variant.** The plan gives only `RecoveryCurve.flat(R, as_of)` and `R(t)`; a term structure would be a second class, not a change to this one.
5. **One test beyond the plan's list**, the QuantLib oracle, with its own constant `QL_SURVIVAL_ABS_TOL`. QuantLib is imported in the test only, as in Sections 1 and 2.
6. **`tests/test_repo_hygiene.py` was edited outside its section**, on the user's instruction in the session prompt (the FSTRING_MIDDLE skip). It is guarded with `getattr`, changes nothing on 3.11, and is in the housekeeping commit 529b35d, not the section commit.
7. `cds/__init__.py`'s docstring still says "None exist yet" for the module list. Not in this section's file list; left for Section 10's README pass unless the reviewer wants it fixed earlier.
8. The stray `11_CDS_Pricing_Bootstrap.docx` at the repo root, noted in reviews 01 and 02, is still there and still untracked.

## Reviewer reads (max 6, in order)

1. `cds/curves.py` — the module docstring's SurvivalCurve paragraph (the formula and the closed-end convention), then `SurvivalCurve.__post_init__` (the cumulative hazard at the pillars), `_interval` and `hazard`, then the two `with_as_of` methods.
2. `tests/test_survival.py` — criteria 1 to 6 in the order of the file, the discount-curve shift tests, and the QuantLib oracle at the end.
3. `tests/conftest.py` — the two new constants and their reasons.
4. `docs/CONVENTIONS_RESOLVED.md` — items 13 and 14 as committed.
5. `tests/test_repo_hygiene.py` — `NON_CODE_TOKEN_TYPES`, the one change outside the section.
