# BUILD_PLAN.md — CDS Pricing and Hazard Rate Bootstrapping

One section per session. A session executes exactly one numbered section,
ends with `review/<NN>_<slug>.md`, all tests green, one commit
`Section <NN>: <slug>`, and a push to `main`. Then it stops.

The plan has five parts. Parts A to D fix the conventions, the corrections to
the spec, the public objects, the bump definitions and the output file
conventions, so that no section redefines them. Part E is the sections.

Symbol names follow `docs/SPEC.md` section 6: survival probability Q(t),
piecewise-constant hazard λ_i on pillar interval (t_{i−1}, t_i], discount
factor P(t), coupon dates t_1..t_n with accrual fractions Δ_j, spread s,
coupon c, recovery R, risky annuity A, PV_prem, PV_prot, par spread s_par.

---

## Part A — Conventions locked

Each convention names its source. Where I am not certain the rule is stated
correctly, it is repeated in Part B ("Conventions to confirm") rather than
guessed at.

Sources used throughout:

- **[ISDA-SM]** ISDA CDS Standard Model, documentation and C source
  (`cdsmodel.com`, the JPMorgan-contributed library, v1.8.2). The functions
  named below are the ones in that source.
- **[BigBang]** ISDA 2009 "Big Bang" protocol and the Standard North American
  Corporate (SNAC) contract specification (Markit, April 2009).
- **[Roll2015]** ISDA / Markit "Single Name CDS Roll Frequency Change",
  effective 20 December 2015: new contracts roll semi-annually.
- **[O'Kane]** D. O'Kane, *Modelling Single-name and Multi-name Credit
  Derivatives*, Wiley 2008, chapters 5 to 7 (CDS mechanics, valuation,
  bootstrapping). Note this book predates the Big Bang; it is the source for
  the schedule mechanics, the leg formulas and the bootstrap, not for fixed
  coupons or upfront conventions.
- **[QL]** QuantLib 1.43: `ql/instruments/creditdefaultswap.cpp`
  (`cdsMaturity`, `previousTwentieth`), `ql/time/schedule.cpp`
  (`DateGeneration::CDS`, `CDS2015`), `ql/pricingengines/credit/isdacdsengine.cpp`.
  QuantLib is also the Section 7 oracle, so where QuantLib's reading of the
  ISDA model is documented in its source, the plan follows it.

### A.1 Schedule

| Rule | Statement | Source |
|---|---|---|
| Coupon dates | 20 Mar, 20 Jun, 20 Sep, 20 Dec. Quarterly. Generated unadjusted. | [BigBang], [O'Kane] 5.4 |
| Payment dates | Each coupon date adjusted **Following** on a weekend-only calendar by default. A US/UK holiday calendar is an optional argument (`calendar="us_uk"`), loaded from a committed date list. | [ISDA-SM] `JpmcdsBusinessDay`, [QL] `MakeCreditDefaultSwap` uses `WeekendsOnly()` |
| Accrual dates | See Part B, item 5. Recommended reading: accrual periods run between the **adjusted** dates (same as payment dates) except the last, which ends on the **unadjusted** maturity. | [QL] `MakeCreditDefaultSwap`: `Schedule(..., Following, Unadjusted, CDS2015)` |
| Standard maturity, current rule | Semi-annual roll since 20 Dec 2015. Let the anchor be the most recent 20 Mar or 20 Sep on or before the trade date. Maturity of an n-year contract = anchor + n years + 3 months. So trades from 20 Mar to 19 Sep mature on 20 Jun; trades from 20 Sep to 19 Mar mature on 20 Dec. Confirmed against `ql.cdsMaturity(..., CDS2015)` in Section 0: 19 Mar 2016 5Y → 20 Dec 2020; 20 Mar 2016 5Y → 20 Jun 2021. A "6M" traded on 19 Sep 2024 matures 20 Dec 2024, three months out; this is the rule, not a bug. | [Roll2015], [QL] `cdsMaturity` |
| Standard maturity, pre-2015 rule | Quarterly roll, 2009 to 2015. Anchor = the most recent IMM 20th (Mar/Jun/Sep/Dec) on or before the trade date. Maturity = anchor + n years + 3 months. 19 Jun 2014 5Y → 20 Jun 2019; 20 Jun 2014 5Y → 20 Sep 2019 (confirmed in Section 0). Selected by `roll_rule="quarterly_2009"`; the default is `"semiannual_2015"`. QuantLib's flag for this is `DateGeneration.CDS` (not `OldCDS`, which is the pre-2009 long/short stub rule and is out of scope). | [BigBang], [QL] `cdsMaturity` |
| Accrual start | The coupon date on or immediately before the step-in date (see Part B item 1 for the trade-date reading). First coupon is a full coupon; the accrued from accrual start to the step-in date is rebated in cash at settlement (Part B item 2 for the direction). | [BigBang], [ISDA-SM] `JpmcdsCdsFeeLegMake` |
| Stubs | None arise for a standard contract: the maturity is always an IMM 20th and the first period starts on the previous IMM 20th, so every period is a full quarter. The generator raises `ValueError` on a maturity that is not an IMM 20th. | [BigBang] |
| Last period | Accrual for the last period includes the maturity date: one extra day. In QuantLib this is `lastPeriodDayCounter = Actual360(True)`. | [ISDA-SM] `JpmcdsCdsFeeLegMake` (`endDate + 1`), [QL] |
| Protection effective (step-in) | Trade date + 1 calendar day. | [BigBang], [ISDA-SM] `stepinDate` |
| Cash settlement | Trade date + 3 business days on the same calendar. | [BigBang], [QL] `cashSettlementDays=3` |
| Accrual day count | act/360. | [BigBang] |
| Curve time | act/365 fixed years from the valuation date, for both the discount curve and the survival curve. The ISDA model computes every curve time this way. Mixing act/360 accrual with act/365F time is the intended behaviour and is tested in Section 1 and Section 4. | [ISDA-SM] `JPMCDS_ACT_365F` in `JpmcdsZeroPrice`, [QL] `Actual365Fixed` in `IsdaCdsEngine` |

### A.2 Curves

| Rule | Statement | Source |
|---|---|---|
| Discount interpolation | Log-linear in P(t) between nodes, equivalently r·t linear in t (piecewise-flat forwards). Flat extrapolation of the last forward rate beyond the last node. Before the first node: flat forward at the first node's zero rate. | [ISDA-SM] `JpmcdsZeroPrice` / `JPMCDS_FLAT_FORWARDS`, [QL] `IsdaCdsEngine` requires a log-linear discount curve |
| Discount inputs | A committed snapshot of SOFR OIS par rates, tenors 1M to 30Y, bootstrapped with annual fixed act/360 payments (single payment for tenors under 1Y, money-market style). Source page and date recorded in the data file and `docs/DATA_NOTE.md`. FRED publishes overnight SOFR and backward-looking averages, not OIS par rates, so the snapshot comes from a published swap-rate page (Part B item 4). | SOFR OIS market convention; Markit/ISDA move of the standard model's rate inputs to SOFR (Oct 2022) |
| Survival curve | Piecewise-constant hazard λ_i on pillars 6M, 1Y, 2Y, 3Y, 4Y, 5Y, 7Y, 10Y, pillar dates = standard maturities for those tenors from the valuation date. Q(t) = exp(−Σ_i λ_i (t_i − t_{i−1})). Flat extrapolation of λ beyond 10Y. | [SPEC] 6.1, [O'Kane] 7.3, [ISDA-SM] `JpmcdsCleanSpreadCurve` |
| Recovery | A `RecoveryCurve` object, flat by default, R(t). Defaults: 0.40 senior unsecured, 0.20 subordinated, 0.25 HY index. | [SPEC] 4 |

### A.3 Pricing

| Rule | Statement | Source |
|---|---|---|
| Leg engines | Two engines with identical signatures. `isda`: closed form per interval of the merged grid (curve nodes ∪ coupon dates ∪ step-in ∪ maturity) assuming flat hazard and flat forward within each interval. `grid`: daily grid, sums as in SPEC 6.2 and 6.3. They must agree to 0.1 bp of par spread on all 3 curves. `isda` is the default. | [SPEC] 6.3, [ISDA-SM] `JpmcdsContingentLegPV`, `JpmcdsFeeLegPV` |
| Accrual on default | Paid. In the closed form the accrual time carries the ISDA half-day bias (the accrual start time is shifted by +0.5/365 year, [ISDA-SM] `FeePaymentPVWithTimeLine`: `t0 = ... + 0.5/365`). QuantLib names: `IsdaCdsEngine.HalfDayBias` (accrual bias), `IsdaCdsEngine.Piecewise` (forwards in coupon period: one flat forward per merged-grid interval, which is what our merged grid does), `IsdaCdsEngine.Taylor` (numerical fix: series expansion of (1 − e^{−kτ})/k when kτ is small). Section 7 uses exactly these three flags. | [ISDA-SM], [QL] |
| Quoted spread ↔ upfront | The ISDA flat-hazard conversion: a single hazard rate λ_flat calibrated so the contract's par spread equals the quoted spread, with the trade's recovery and the real discount curve, on the trade's own maturity. Upfront = PV_prot − c·A at that λ_flat. Reported as clean upfront in % of notional plus accrued in cash. The upfront from the full bootstrapped curve is reported next to it and the difference shown. Standard coupons 100 bp and 500 bp. | [BigBang], [ISDA-SM] `JpmcdsCdsoneUpfrontCharge` |
| Settlement discounting | PVs are stated at the cash settlement date, i.e. divided by P(t_settle), which is what the ISDA model's upfront charge and QuantLib's `IsdaCdsEngine` report (Part B item 3). | [ISDA-SM] `JpmcdsCdsPrice` (`cashSettleDate`), [QL] |
| Sign convention | The protection buyer's MTM is positive when spreads widen: buyer value = PV_prot − c·A (dirty). `side="sell"` negates. Stated once here, used everywhere. Notional default 10,000,000. | this plan |
| Clean versus dirty | Dirty value includes the full first coupon (accrual from accrual start). Clean = dirty + accrued, where accrued = c·N·(days from accrual start to step-in)/360 (Part B item 2). Clean upfront is the quoted number; the cash paid on the settlement date by the buyer is the dirty value. | [BigBang], [ISDA-SM] `JpmcdsCdsFeeLegAI` |

### A.4 Bootstrap

| Rule | Statement | Source |
|---|---|---|
| Inputs | Per pillar, either `par_spread_bp` or `upfront_pct` with a stated coupon, never mixed within one curve. Upfront quotes are converted to a conventional spread with the flat-hazard rule first (using the pillar's own maturity), then bootstrapped like spreads. The conventional spread is stored next to the upfront in the curve file and in Table 1. | [BigBang], [ISDA-SM] |
| Method | Sequential Brent per pillar on λ_i ∈ [0, 5], holding earlier pillars fixed. Objective f(λ_i) = D·(PV_prot(λ_1..λ_i) − s_i·A(λ_1..λ_i)) + s_i·accrued_fraction, the clean value at coupon s_i, for a contract maturing on pillar i, valued with the `isda` engine at the pillar's conventional spread and the curve's recovery (item 24; the Section 6 text spells it out). | [SPEC] 6.5, [O'Kane] 7.5, [ISDA-SM] `isPriceClean = TRUE` |
| Arbitrage detection | Before Brent, evaluate f(0). If the sign says the root would be negative (spread falls faster with maturity than any non-negative hazard allows), raise `BootstrapArbitrageError(pillar, spread_bp, f_at_zero)` and do not force a fit. The error's message names the standard fallbacks; `bootstrap(..., fallback="flat_from_shortest")` fits a single flat hazard to the shortest pillar, and `fallback="upfront"` prices each pillar off its own flat hazard (upfront-quoted pricing) without a joint curve. | [SPEC] 6.5 and 10 |

---

## Part B — Conventions to confirm

These are the rules I could not pin down from the sources with certainty, or
where the kickoff wording and the sources disagree. Each has a recommendation.
The user's answers are committed as `docs/CONVENTIONS_RESOLVED.md` at the
start of Section 1; Section 1 does not start without that file.

1. **Accrual start: coupon date on or before the trade date, or on or before
   the step-in date (T+1)?** The two differ only when the trade date is the
   19th of an IMM month. Trade 19 Mar: reading (a) starts accrual on 20 Dec,
   with a full coupon due the next day and 91 days of accrued rebated;
   reading (b) starts accrual on 20 Mar with 0 days accrued. QuantLib seeds
   the schedule from `previousTwentieth(protectionStart)`, i.e. reading (b),
   and the ISDA C library's fee leg starts at the IMM date on or before the
   step-in date. **Recommend (b).** The Section 1 oracle test passes the
   step-in date as the schedule's effective date, so the implementation must
   match whichever is chosen.

2. **Accrued rebate: direction and day count.** The kickoff says "protection
   buyer pays accrued rebate at trade". Under SNAC the buyer pays a full
   first coupon, so the *seller* pays the buyer the accrued for the days
   before protection started; the buyer's cash settlement is dirty value =
   clean upfront − accrued. The accrued day count in the ISDA model runs from
   the accrual start date up to but excluding the step-in date, so a trade
   on the roll date carries 1 day of accrued. **Recommend: seller rebates,
   days = step-in − accrual start.** Section 5 tests this against
   QuantLib's `accrualRebate` cash flow.

3. **Where PVs are stated.** ISDA and QuantLib state the upfront at the cash
   settlement date (T+3). The plan applies the same to `mtm`, so every
   number in `PriceResult` is a T+3 amount and Table 2 compares like with
   like. **Recommend: cash settlement date for everything; no separate
   valuation-date PV.**

4. **Rates snapshot source.** ICE Swap Rate publishes USD SOFR swap rates
   daily (1Y to 30Y, 11:00 NY fixing; annual fixed act/360 versus SOFR
   compounded). It does not publish 1M, 3M, 6M. For the short end the
   candidates are CME Term SOFR (forward-looking, close to OIS, freely
   published) or omitting sub-1Y tenors. **Recommend: ICE Swap Rate for 1Y
   to 30Y plus CME Term SOFR for 1M, 3M, 6M, each labelled in the file; the
   snapshot date is the date of the Section 2 session.** The difference
   between Term SOFR and OIS at 6M is a few bp and moves a 5Y CDS upfront by
   well under 0.1 bp.

5. **Accrual dates adjusted or unadjusted.** The kickoff says coupon dates
   are "unadjusted for scheduling" and payment dates adjusted. The ISDA C
   library and QuantLib's standard CDS both run the accrual periods between
   the adjusted dates (Following), with the last period ending on the
   unadjusted maturity + 1 day. Using unadjusted accrual dates moves a day
   of accrual between neighbouring periods a few times over a contract's
   life, worth under 0.1 bp, but it also changes the accrued at settlement
   when the previous IMM date fell on a weekend, which is visible in
   Table 2. **Recommend: adjusted accrual dates, unadjusted maturity + 1
   day, exactly as QuantLib's `MakeCreditDefaultSwap`.**

6. **Distressed curve may bootstrap without an arbitrage error.** A hand
   estimate of the sequential fit for the indicative distressed levels
   (2500 → 950 bp, R = 20%), using the annuity-weighted-average-hazard
   approximation with survival weights, gives forward hazards of roughly
   31%, 23%, 17%, 9%, 10%, 5%, 6%, 7% for the eight pillars: all positive.
   Discounting pushes the long hazards lower but probably not below zero.
   If Section 6 finds the curve fits, the plan's test "raises
   `BootstrapArbitrageError` at the pillar where it should" has no subject.
   **Recommend: keep the three named curves exactly as specified; if the
   distressed curve fits, Section 6 commits a fourth file,
   `distressed_arb.json`, which steepens the front end (6M raised in 500 bp
   steps until f(0) changes sign at some pillar) and is used only for the
   arbitrage test and the fallback demonstration.** Alternative: change the
   distressed levels themselves.

7. **Theta P&L definition.** Theta is reported as the change in the side's
   dirty MTM between the two valuation dates plus any coupon cash flow the
   side paid or received in (t_0, t_1]. For 1 day no coupon usually falls;
   for 1 month one may. **Recommend this definition**; the alternative
   (clean MTM change, coupons ignored) hides carry.

8. **Old-style running-spread trades.** For `CDSTrade.quote` of kind
   `par_spread_bp`, the plan reads the trade as a running-spread contract:
   `coupon_bp` must equal the quote value (the pricer raises otherwise),
   there was no upfront, and mtm = (PV_prot − s_traded·A)·N. For kind
   `upfront_pct` the buyer paid `value`% of notional at inception and
   mtm = (PV_prot − c·A − value/100)·N. For `quote=None`, mtm is the
   current unwind value (PV_prot − c·A)·N. **Recommend this reading**; it
   makes "a seasoned trade struck 200 bp off market" a running-spread
   contract at s_mkt ± 200 bp, which is the classic case for the recovery
   sensitivity point.

9. **Holiday calendar contents.** The optional US/UK calendar is a committed
   CSV `data/calendars/us_uk_holidays.csv`, generated once in Section 1 from
   QuantLib's `JointCalendar(UnitedStates(Settlement), UnitedKingdom(Settlement))`
   for 2000 to 2060, with the generator script committed. The library never
   imports QuantLib at runtime. **Recommend as stated**; the alternative is
   to hand-type the dates.

---

## Part C — Corrections to the spec

The plan adopts these. Where a section's output follows the corrected form,
the section says so.

1. **Chart 2 is misdescribed.** Implied 5Y default probability is not flat in
   recovery: from the credit triangle λ ≈ s/(1 − R), so the implied default
   probability rises steeply as R rises. What is flat near par is the
   *contract value*. Chart 2 becomes two panels: (a) implied 5Y default
   probability 1 − Q(5) against R from 10% to 60% for the IG curve, market
   quotes held fixed and the curve re-bootstrapped at each R; (b) MTM of a
   5Y contract against the same R range for a par trade (flat) and for a
   seasoned running-spread trade struck 200 bp off market (steep). The rec01
   interview point in spec section 9 is then supported by panel (b).

2. **JTD needs the accrued and a side.** JTD for the protection buyer is
   (1 − R)·N − PV_MTM − accrued coupon owed to the seller, with PV_MTM the
   buyer's dirty MTM and the accrued the coupon accrued from the current
   period's start to the valuation date (paid on default under accrual on
   default). The seller's number is the negative. R is the assumed recovery
   on the trade; realised recovery is unobservable, and the README says so.

3. **Theta has two definitions and both matter.** Theta-calendar: move the
   valuation date forward with the *dated* curves fixed: every curve node
   stays on its calendar date, so hazards and forward rates between the same
   dates are unchanged and the contract shortens. Theta-rolldown: move the
   valuation date forward with the curves fixed in *tenor* space: every node
   date shifts forward by the same amount, so the contract prices off a
   shorter point on the curve. Both at 1 calendar day and 1 calendar month.
   A steep curve makes the difference large; a flat curve makes it near
   zero, which Section 8 tests.

4. **Validation reference.** QuantLib's `IsdaCdsEngine` is the primary
   reference. The ISDA C library is optional and used only if a maintained
   Python binding installs cleanly in the Section 7 session; no session is
   spent fighting a build. Tolerance 1 bp of upfront and 0.5 bp of par
   spread on all 3 curves. If QuantLib disagrees by more, the likely causes
   in order: schedule (check first), day count, accrual-on-default flag,
   interpolation, then model.

5. **Which rec01 is near zero at par (a correction to the kickoff, not the
   spec).** The spec (6.7) is right: for a par contract the recovery
   sensitivity is near zero *because the bootstrapped hazard rises to
   compensate*, i.e. the number computed by holding market quotes fixed and
   re-bootstrapping. The kickoff's bump list labels the *hazard-fixed*
   number as the near-zero one; that is backwards. With the hazard curve
   held fixed, V = (1 − R)·I − c·A where I = ∫P(u)(−dQ(u)), so
   ∂V/∂R = −I·N per unit of R, independent of the coupon: on the IG curve
   that is about −$6,700 per point on $10m, and identical for the par and
   the off-market trade. With quotes fixed and the curve re-bootstrapped,
   PV_prot stays pinned at s_mkt·A, so V = (s_mkt − c)·A and
   rec01 = (s_mkt − c)·ΔA·N: zero at par, growing with |s_mkt − c|.
   Section 8 reports both, labelled `rec01` (re-bootstrapped, the desk
   number) and `rec01_hazard_fixed`, and its tests are written to the
   correct labels.

---

## Part D — Fixed definitions

### D.1 Public objects (`cds/types.py`, created in Section 1 with no logic)

Frozen dataclasses. Fields may be added later only through "Against the
plan" in a review file, never silently.

```python
@dataclass(frozen=True)
class Quote:
    kind: Literal["par_spread_bp", "upfront_pct"]
    value: float
    coupon_bp: float | None      # required when kind is upfront_pct

@dataclass(frozen=True)
class CDSTrade:
    trade_date: date
    maturity: date               # unadjusted IMM date
    notional: float              # 10_000_000.0 default
    coupon_bp: float             # 100.0 or 500.0
    side: Literal["buy", "sell"] # protection buyer or seller
    recovery: float              # assumed recovery, 0.40 default
    quote: Quote | None          # the traded level, for MTM of seasoned trades

@dataclass(frozen=True)
class MarketCurveQuotes:         # input to bootstrap
    as_of: date
    pillars: tuple[str, ...]     # ("6M","1Y","2Y","3Y","4Y","5Y","7Y","10Y")
    quotes: tuple[Quote, ...]
    recovery: float
    label: str                   # "IG_flat" etc.

class DiscountCurve(Protocol):   df(t: float) -> float;  forward(t1, t2) -> float;  as_of: date
class SurvivalCurve(Protocol):   Q(t) -> float;  hazard(t) -> float;  pillar_times, pillar_hazards;  as_of: date
class RecoveryCurve(Protocol):   R(t) -> float;  as_of: date

@dataclass(frozen=True)
class MarketState:
    as_of: date
    discount: DiscountCurve
    survival: SurvivalCurve
    recovery: RecoveryCurve
    quotes: MarketCurveQuotes

@dataclass(frozen=True)
class PriceResult:
    mtm: float                   # side's dirty value net of inception cash, at cash settle date, currency
    clean_upfront_pct: float     # buyer pays, % of notional, current unwind level
    accrued: float               # currency, accrual start to step-in
    par_spread_bp: float
    risky_annuity: float         # A, per unit notional per unit spread
    pv_protection: float         # PV_prot, per unit notional
    pv_premium: float            # c·A, per unit notional
    cash_settle_date: date

@dataclass(frozen=True)
class RiskReport:                # field names are exactly the Table 3 columns (Section 8)
    ...

@dataclass(frozen=True)
class ExplainResult:             # field names are exactly the Table 4 columns (Section 9)
    ...

price(state, trade) -> PriceResult
risk(state, trade) -> RiskReport
explain(state_t0, state_t1, trade) -> ExplainResult
```

Time `t` is act/365 fixed years from `state.as_of`. `as_of` is the
valuation date; it equals the trade date at inception and moves forward for
theta. Every curve carries its own `as_of` and `price` raises `ValueError`
if the 3 curves in a `MarketState` disagree on it. The curve protocols are
`typing.Protocol`s in `types.py`; the concrete classes live in `curves.py`.

The `DiscountCurve` concrete class also exposes `node_dates` and
`node_dfs`; `SurvivalCurve` exposes `pillar_dates`; both expose
`with_as_of(new_as_of, mode)` with `mode in {"calendar", "tenor"}` so
Section 8 can build the two thetas without reaching into internals. These
are concrete-class methods, not protocol members.

### D.2 Bump definitions (`cds/risk.py`, Section 8, no other conventions)

- **CS01 per pillar**: add 1 bp to that pillar's market quote (to the
  conventional spread for upfront-quoted curves), re-bootstrap, reprice.
  One-sided up. Report central (average of up and down) as a second column
  so the two can be compared once.
- **Parallel CS01**: add 1 bp to every pillar's market quote, re-bootstrap,
  reprice.
- **rec01**: recovery + 1 percentage point, holding market quotes fixed and
  re-bootstrapping (so the hazard curve moves). Also report the number
  holding the hazard curve fixed, labelled `rec01_hazard_fixed`. Per Part C
  item 5, `rec01` is the one near zero at par and the difference between the
  two is the interview point.
- **IR01**: add 1 bp to every OIS par input, rebuild the discount curve,
  reprice. Market CDS quotes held fixed and re-bootstrapped off the new
  discount curve.
- **JTD**: as defined in Part C item 2.
- **Theta**: as defined in Part C item 3 and Part B item 7, 1 calendar day
  and 1 calendar month, no weekend or holiday adjustment to the shift itself.
  The cash settlement date moves with the valuation date.

All bumps are on inputs, followed by a full rebuild of whatever depends on
the bumped input. Nothing bumps a hazard directly except
`rec01_hazard_fixed`, which bumps nothing but R.

### D.3 Output file conventions

Every table is `outputs/tables/table_<n>_<slug>.csv` with a header row and a
companion `.md` rendered from it. Every chart is
`outputs/charts/chart_<n>_<slug>.png` at 1600×900 with the data behind it
saved as `chart_<n>_<slug>.csv`. Column names are stated in the section that
produces the table and do not change afterwards. Section 10's README embeds
these files by path; it recomputes nothing.

Generators live in `cds/report.py` (one function per output, taking the
`MarketState`s and returning the DataFrame it wrote) and are run by
`scripts/make_outputs.py --only table_1` etc. Every output is committed.

Data file formats, fixed now:

`data/curves/<label>.json`
```json
{"label": "IG_flat", "as_of": "YYYY-MM-DD", "recovery": 0.40,
 "quote_kind": "par_spread_bp", "coupon_bp": null,
 "pillars": ["6M","1Y","2Y","3Y","4Y","5Y","7Y","10Y"],
 "quotes": [45, 50, 60, 70, 80, 90, 105, 120],
 "conventional_spread_bp": null,
 "source": "illustrative", "note": "..."}
```
`conventional_spread_bp` is a list for upfront-quoted curves, `null`
otherwise.

`data/rates/sofr_ois_<YYYY-MM-DD>.json`
```json
{"as_of": "YYYY-MM-DD", "fixed_frequency": "annual", "fixed_day_count": "act/360",
 "tenors": ["1M","3M","6M","1Y","2Y","3Y","4Y","5Y","7Y","10Y","15Y","20Y","30Y"],
 "par_rates_pct": [],
 "source": "", "source_url": "", "snapshot_taken": "YYYY-MM-DD",
 "note": ""}
```

The valuation date shared by all illustrative curves is the rates snapshot
date chosen in Section 2 (Part B item 4); Section 6 reads it from the rates
file rather than restating it.

---

## Part E — Sections

### Section 0 — Repo skeleton (this session)

**Purpose.** Put the plan, the rules, the spec and the empty structure in
place so every later session has the same starting point. No pricing code.

**Files.** `CLAUDE.md`, `BUILD_PLAN.md`, `README.md`, `pyproject.toml`,
`uv.lock`, `.python-version`, `.gitignore`, `docs/SPEC.md`,
`docs/11_CDS_Pricing_Bootstrap.docx`, `docs/DATA_NOTE.md`,
`review/TEMPLATE.md`, `cds/__init__.py`, `data/curves/README.md`,
`data/rates/README.md`, `tests/conftest.py`, `outputs/tables/.gitkeep`,
`outputs/charts/.gitkeep`.

**Acceptance.** `uv sync` succeeds with QuantLib importable (done: 1.43).
`uv run pytest -q` collects zero tests (exit code 5, "no tests collected",
is accepted for this section only). No review file: the session report to
the user stands in for it.

**Outputs.** None.

---

### Section 1 — `conventions.py` and `schedule.py`

**Purpose.** The IMM date generator, both roll rules, accrual fractions and
payment adjustment, tested against QuantLib as an independent oracle. Most
pricing errors are schedule errors, so this is done first and alone.

**Files.** `cds/conventions.py`, `cds/schedule.py`, `cds/types.py` (Part D.1,
no logic), `cds/calendars.py`, `data/calendars/us_uk_holidays.csv`,
`data/calendars/README.md`, `scripts/make_calendar.py`,
`tests/test_schedule.py`, `tests/test_repo_hygiene.py`,
`docs/CONVENTIONS_RESOLVED.md` (committed first, from the user's answers to
Part B).

**Rules implemented.** Everything in Part A.1, as resolved by Part B items
1, 2, 5 and 9. `conventions.py` holds, as named constants with a one-line
comment each: `ACCRUAL_DAY_COUNT = "act/360"`, `CURVE_DAY_COUNT = "act/365f"`,
`IMM_DAY = 20`, `IMM_MONTHS = (3, 6, 9, 12)`, `ROLL_MONTHS_2015 = (3, 9)`,
`STEP_IN_DAYS = 1`, `CASH_SETTLE_BUSINESS_DAYS = 3`,
`STANDARD_COUPONS_BP = (100.0, 500.0)`, `RECOVERY_SENIOR = 0.40`,
`RECOVERY_SUBORDINATED = 0.20`, `RECOVERY_HY_INDEX = 0.25`,
`DEFAULT_NOTIONAL = 10_000_000.0`, `DEFAULT_ROLL_RULE = "semiannual_2015"`,
`DEFAULT_CALENDAR = "weekends"`, `PILLARS = ("6M","1Y","2Y","3Y","4Y","5Y","7Y","10Y")`.

`schedule.py` exposes:
- `standard_maturity(trade_date, tenor, roll_rule=DEFAULT_ROLL_RULE) -> date`
- `imm_dates_between(start, end) -> list[date]`
- `previous_imm(d) -> date`, `next_imm(d) -> date`
- `cds_schedule(trade_date, maturity, calendar=DEFAULT_CALENDAR) -> Schedule`
  where `Schedule` is a frozen dataclass of `accrual_start: tuple[date, ...]`,
  `accrual_end: tuple[date, ...]`, `payment: tuple[date, ...]`,
  `accrual_fraction: tuple[float, ...]` (act/360, last period + 1 day),
  `step_in: date`, `cash_settle: date`, `accrual_start_date: date`,
  `accrued_days: int`.
- `year_fraction_act365f(d0, d1) -> float`, `year_fraction_act360(d0, d1) -> float`
- `adjust_following(d, calendar) -> date`

**Acceptance criteria.**
1. `standard_maturity` equals `ql.cdsMaturity(trade, tenor, ql.DateGeneration.CDS2015)`
   for all 8 tenors on each of these 16 trade dates (128 checks, 0
   mismatches): 2015-12-18, 2016-03-19, 2016-03-20, 2016-03-21, 2016-09-19,
   2016-09-20, 2020-02-29 (leap day), 2020-12-20 (a Sunday 20th), 2020-12-31,
   2021-01-04, 2024-02-29, 2024-06-19, 2024-06-20, 2025-09-20 (a Saturday
   20th), 2026-06-19, 2026-09-16.
2. The same 128 checks with `roll_rule="quarterly_2009"` against
   `ql.DateGeneration.CDS`, 0 mismatches.
3. For each of the 16 trade dates and the 5Y maturity, the coupon dates from
   `cds_schedule` equal `ql.Schedule(step_in, maturity, ql.Period("3M"),
   calendar, ql.Following, ql.Unadjusted, ql.DateGeneration.CDS2015, False)`
   date for date, for both the weekend-only calendar and the US/UK calendar,
   0 mismatches. Same for the 6M and 10Y maturities on 4 of the dates.
4. Accrual fractions equal QuantLib's `Actual360()` for every period except
   the last, and `Actual360(True)` for the last, to 1e-12, on the same
   schedules.
5. `year_fraction_act365f(2024-01-01, 2025-01-01) == 366/365` and
   `year_fraction_act360` of the same is `366/360`; the constants are used,
   not literals.
6. `standard_maturity` raises on a tenor not in `PILLARS`; `cds_schedule`
   raises on a maturity that is not an IMM 20th.
7. `tests/test_repo_hygiene.py` greps every tracked text file for the five
   banned words and fails on any hit other than the rule's own sentence in
   `CLAUDE.md` (the one permitted occurrence); it also checks that no `.py` outside
   `cds/conventions.py` contains the literals `/360`, `/365`, `0.40`, `0.25`,
   `0.20` used as conventions (the check is a regex on assignments and is
   allowed to be conservative).

**Tests.** `tests/test_schedule.py` (criteria 1 to 6),
`tests/test_repo_hygiene.py` (criterion 7). QuantLib is imported in the test
only.

**Outputs.** None. The review file lists the 16 trade dates with the
maturity from both rules and the oracle, as its rows.

---

### Section 2 — `curves.py` part 1: the discount curve

**Purpose.** Bootstrap the SOFR OIS snapshot into a log-linear discount
curve with `df(t)` and `forward(t1, t2)`, matching the ISDA model's
interpolation.

**Files.** `cds/curves.py` (the `DiscountCurve` concrete class and
`bootstrap_ois`), `data/rates/sofr_ois_<date>.json`, `data/rates/README.md`
(updated), `docs/DATA_NOTE.md` (snapshot recorded), `tests/test_discount.py`.

**Rules implemented.** Part A.2 rows 1 and 2, resolved by Part B item 4. An
OIS of tenor T with annual fixed act/360 payments on dates T_1..T_m (the
anniversaries of the spot date, rolled Following on the weekend-only
calendar; single payment at T for tenors under 1Y) and par rate K satisfies
K·Σ_k Δ_k P(T_k) = 1 − P(T_m), Δ_k act/360. Solve sequentially for P(T_m)
with log-linear interpolation between nodes for the intermediate P(T_k).
Spot date = as_of (T+0) for simplicity, stated in the data note; the ISDA
model itself values from the trade date. `df(t)` with t in act/365F years
from `as_of`; `forward(t1, t2) = ln(P(t1)/P(t2))/(t2 − t1)`, continuously
compounded, the flat-forward rate the `isda` engine uses per interval.

**Acceptance criteria.**
1. Repricing every input OIS (all tenors) with the built curve returns the
   par rate to within 0.01 bp (`OIS_REPRICE_BP`).
2. Between any two adjacent nodes, `ln df(t)` is linear in t: for 5 interior
   points per interval the second difference is under 1e-12.
3. Beyond the last node the forward rate equals the last interval's forward
   to 1e-12 (flat extrapolation); `df` is monotone non-increasing on a
   daily grid to 60Y.
4. `forward(t1, t2)` reproduces `df(t2)/df(t1) = exp(−f·(t2 − t1))` to 1e-12.
5. The data file has non-empty `source`, `source_url`, `snapshot_taken` and
   `note` fields, and the test reads them.

**Tests.** `tests/test_discount.py`.

**Outputs.** None. The review shows the node table (tenor, par rate, P,
zero rate act/365F, forward) as its rows.

---

### Section 3 — `curves.py` part 2: the survival and recovery curves

**Purpose.** `SurvivalCurve` with hazard pillars, `Q(t)`, `hazard(t)`,
default density, and `RecoveryCurve`; the `with_as_of` shifts Section 8
needs.

**Files.** `cds/curves.py` (extended), `tests/test_survival.py`.

**Rules implemented.** SPEC 6.1: Q(t) = exp(−Σ_i λ_i (t_i − t_{i−1})) with
λ_i flat on (t_{i−1}, t_i], t_0 = 0, flat extrapolation of λ beyond the
last pillar. Default density −dQ/dt = λ(t)·Q(t). `SurvivalCurve` is built
from `(as_of, pillar_dates, pillar_hazards)`; `pillar_times` are act/365F
from `as_of`. `RecoveryCurve.flat(R, as_of)`; `R(t)` returns the constant.
`with_as_of(new_as_of, mode="calendar")` keeps `pillar_dates` and recomputes
times (nodes fixed in date); `mode="tenor"` shifts every pillar date by
`(new_as_of − as_of)` days (nodes fixed in tenor). The same two modes on
`DiscountCurve` (calendar mode drops nodes that fall before the new
`as_of`; both modes keep the DF ratios between surviving nodes).

**Acceptance criteria.**
1. Flat hazard λ on all pillars gives `Q(t) == exp(−λt)` to 1e-12 at 50
   points from 0 to 15Y (past the last pillar).
2. For the three-pillar curve λ = (1%, 2%, 3%) on (1Y, 3Y, 5Y),
   `Q(4) == exp(−(0.01·1 + 0.02·2 + 0.03·1))` to 1e-12.
3. The density integrated numerically (scipy `quad`, per pillar interval)
   from 0 to T equals 1 − Q(T) to 1e-9 for T = 2.5, 5, 12.
4. `with_as_of(+30 days, "calendar")` leaves Q between any two pillar dates
   unchanged as a ratio, `Q(d2)/Q(d1)` equal to 1e-12; `"tenor"` leaves
   `pillar_times` and `pillar_hazards` unchanged to 1e-12.
5. `hazard(t)` is continuous from the left at the pillars (λ_i flat on
   (t_{i−1}, t_i]): `hazard(t_i)` is λ_i and `hazard(t_i + 1e-9)` is λ_{i+1}.
6. Negative hazards raise `ValueError` at construction.

**Tests.** `tests/test_survival.py`.

**Outputs.** None.

---

### Section 4 — `legs.py`: premium and protection legs, both engines

**Purpose.** The premium leg (risky annuity with accrual on default) and the
protection leg, in the ISDA closed form per interval and on a brute-force
daily grid, agreeing to 0.1 bp of par spread.

**Files.** `cds/legs.py`, `tests/test_legs.py`.

**Rules implemented.** SPEC 6.2 and 6.3 with symbols P(t), Q(t), Δ_j, R.
Both engines take `(discount, survival, recovery, schedule, as_of,
half_day_bias: bool, engine: Literal["isda","grid"], grid_days: int = 1)`
and return `LegValues(annuity_coupon, annuity_accrual, protection)` per unit
notional, as of the valuation date (the pricer applies `1/P(t_settle)`).
A = annuity_coupon + annuity_accrual; PV_prem = c·A;
PV_prot = (1 − R)·protection.

`isda` engine. Merged grid = {step-in} ∪ discount nodes ∪ survival pillars
∪ coupon accrual dates ∪ {maturity}, as act/365F times u_0 < ... < u_M
from `as_of`, restricted to (t_0, T] with t_0 = t(max(step-in, as_of + 1 day)
− 1 day), QuantLib's end-of-day reading of the ISDA model (0 for a new trade
valued on its trade date; docs/CONVENTIONS_RESOLVED.md item 19, which also
fixes the coupon-on-survival observation date at pay − 1 day and the
accrual-on-default limits and origin). On (a, b] with flat λ and flat
forward f = forward(a, b), k = λ + f, τ = b − a:
- protection: ∫_a^b P(u)λQ(u)du = P(a)Q(a)·λ/k·(1 − e^{−kτ})
- accrual on default for the coupon period starting at t_{j−1} that
  contains (a, b], with s_0 = a − t_{j−1} (+ 0.5/365 if `half_day_bias`):
  ∫_a^b (u − t_{j−1})P(u)λQ(u)du = P(a)Q(a)·λ·[ s_0·(1 − e^{−kτ})/k + (1 − (1 + kτ)e^{−kτ})/k² ]
  scaled by 365/360 to convert the act/365F time to an act/360 accrual
  fraction (the ISDA model does the same: accrual is act/360 while u is
  act/365F).
- when |kτ| < 1e-4 both brackets use their series to third order (QuantLib's
  `Taylor` fix).
- coupon on survival: Σ_j Δ_j P(t_j^pay) Q(t_j^acc_end).
Recovery enters only as (1 − R(t)) at the interval start; for a flat
`RecoveryCurve` this is exact.

`grid` engine. Daily points u_k from step-in to T (act/365F), plus every
coupon accrual date. Protection Σ_k P(u_k)[Q(u_{k−1}) − Q(u_k)];
accrual on default Σ_k (u_mid,k − t_{j−1})·(365/360)·P(u_k)[Q(u_{k−1}) − Q(u_k)]
with the midpoint accrual and the same optional half-day shift; coupon on
survival as above.

**Acceptance criteria.**
1. Par spread from `isda` and from `grid` (1-day) agree to within 0.1 bp
   (`PAR_SPREAD_ENGINE_AGREEMENT_BP`) for a 5Y contract on three test
   curves built in the test: flat 1% hazard at R = 0.40, steep (1% to 8%) at
   R = 0.25, inverted (30% to 8%) at R = 0.20, on the Section 2 discount
   curve; also with `half_day_bias=False` on both.
2. With a flat discount curve at zero rate, no accrual on default and a
   daily coupon schedule (continuous premium), the par spread equals
   λ(1 − R) to 0.5 bp (`CREDIT_TRIANGLE_BP`) for λ = 1.67%, R = 0.40.
3. Grid discretisation error against the closed form halves when the grid
   halves: |s_grid(2 days) − s_isda| / |s_grid(1 day) − s_isda| lies in
   [1.9, 2.1] on the steep curve, with the same half-day setting in both.
4. Turning `half_day_bias` on changes the 5Y par spread on the flat curve by
   under 0.02 bp and in the direction of a larger annuity (the review
   records the number).
5. Both legs are non-negative and the protection leg is monotone increasing
   in every λ_i (bump each pillar +10 bp, 8 checks per curve).

**Tests.** `tests/test_legs.py`.

**Outputs.** None. The review's rows are the leg values per curve per
engine.

---

### Section 5 — `pricer.py`: `price`, par spread, upfront, conversions

**Purpose.** `price(state, trade)`, the ISDA flat-hazard conversion between
quoted spread and upfront, clean versus dirty, accrued, cash settle
discounting, and the textbook model as a separate module for comparison.

**Files.** `cds/pricer.py`, `cds/textbook.py`, `tests/test_pricer.py`,
`tests/test_textbook.py`.

**Rules implemented.** SPEC 6.4 and Part A.3, resolved by Part B items 2, 3
and 8. With A and PV_prot from Section 4 and D = 1/P(t_settle):
- dirty buyer value per unit notional, at settlement: U_dirty = D·(PV_prot − c·A)
- accrued (per unit notional) = c·accrued_days/360, accrued_days from the
  schedule (Part B item 2); accrued_fraction = accrued_days/360
- clean_upfront_pct = 100·(U_dirty + accrued)
- s_par = PV_prot / (A − accrued_fraction / D) (per unit notional; in bp
  × 10⁴): the clean-value spread, the coupon at which clean_upfront_pct is
  zero, QuantLib's `fairSpread` (`docs/CONVENTIONS_RESOLVED.md` item 24,
  reversing item 21). The dirty quantity PV_prot / A, the coupon at which
  U_dirty is zero, is `Valuation.dirty_par_spread_bp`, not a `PriceResult`
  field.
- mtm = side_sign·N·(U_dirty − inception_cash), with inception_cash = 0 for
  `quote=None`, = `value/100` for an `upfront_pct` quote, and 0 for a
  `par_spread_bp` quote (with the pricer raising unless `coupon_bp ==
  quote.value`, Part B item 8)
- flat-hazard conversion `quoted_spread_to_upfront(discount, trade,
  quoted_spread_bp)`: Brent for λ_flat in [0, 5] such that
  s_par(λ_flat) = quoted spread on the trade's maturity, then U_clean at
  coupon c; `upfront_to_quoted_spread` is the inverse (Brent on the spread).
- `price` also returns `pv_protection`, `pv_premium = c·A`, `risky_annuity =
  A` (all per unit notional, at settlement), `cash_settle_date`.
- `price` raises `ValueError` if `state.discount.as_of`,
  `state.survival.as_of`, `state.recovery.as_of` and `state.as_of` differ.

`textbook.py`: continuous premium, continuous discounting at a flat rate r,
flat hazard λ, no accrual on default, no schedule:
PV_prot = (1 − R)·λ/(λ + r)·(1 − e^{−(λ+r)T}), A = (1 − e^{−(λ+r)T})/(λ + r),
s_par = λ(1 − R) exactly. It never imports `legs.py` or `schedule.py`.

**Acceptance criteria.**
1. For a flat-hazard survival curve built in the test (Section 6 is not
   built yet), `price` of a trade with `coupon_bp` equal to the curve's own
   5Y par spread (the clean-value spread, item 24) has `clean_upfront_pct`
   within 0.01 bp of zero and `par_spread_bp` equal to the input to 1e-9.
2. Upfront at the par coupon is zero: `U_dirty + accrued` is under $1 on
   $10m for that trade (mtm is dirty, so the check is on the clean amount).
   The companion identity at the dirty par spread PV_prot / A: `mtm` under
   $1 and `clean_upfront_pct` equal to the accrued in % of notional.
3. Round trip: quoted spread 250 bp → upfront at coupon 100 → quoted spread
   returns 250 bp to 1e-6 bp; same at coupon 500 and for 45 bp and 1200 bp.
4. Sign: raising every hazard by 10% raises the buyer's mtm and lowers the
   seller's, on all three test curves.
5. `accrued` equals `coupon_bp/1e4 · N · accrued_days/360` and
   `accrued_days` equals QuantLib's for the 16 trade dates of Section 1
   (`ql.CreditDefaultSwap(...).accrualRebate().amount()` with notional and
   coupon).
6. Cash settle discounting: `U_dirty` computed with `D` equals the same
   computed at valuation date divided by `P(t_settle)` to 1e-12; a test
   fixes D by construction.
7. `price` raises when the curves' `as_of` disagree.
8. Textbook: s_par = λ(1 − R) to 1e-12; at r = 0 and λ → 0 the annuity
   tends to T.

**Tests.** `tests/test_pricer.py`, `tests/test_textbook.py`.

**Outputs.** None. Review rows: the round-trip table (input spread, coupon,
upfront, recovered spread).

---

### Section 6 — `bootstrap.py`, the three illustrative curves, Table 1, Chart 1

**Purpose.** Sequential Brent per pillar with arbitrage detection and the
two fallbacks; the three committed curves; the first outputs.

**Files.** `cds/bootstrap.py`, `cds/report.py` (Table 1, Chart 1
generators), `scripts/make_outputs.py`, `data/curves/IG_flat.json`,
`data/curves/HY_steep.json`, `data/curves/distressed_inverted.json`,
(`data/curves/distressed_arb.json` if Part B item 6 says so),
`data/curves/README.md` (updated), `docs/DATA_NOTE.md` (curves recorded),
`tests/test_bootstrap.py`, `outputs/tables/table_1_hazard_curves.{csv,md}`,
`outputs/charts/chart_1_survival_hazard.{png,csv}`.

**Rules implemented.** Part A.4. `bootstrap(quotes: MarketCurveQuotes,
discount: DiscountCurve, fallback: None | "flat_from_shortest" | "upfront")
-> BootstrapResult(survival, conventional_spreads_bp, method, f_at_zero)`.
For pillar i: maturity = `standard_maturity(as_of, pillar)`; conventional
spread s_i = the quote if `par_spread_bp`, else
`upfront_to_quoted_spread` (Section 5) at the stated coupon; objective
f(λ_i) = D·(PV_prot(λ_1..λ_i) − s_i·A(λ_1..λ_i)) + s_i·accrued_fraction,
the clean value of the contract at coupon s_i (item 24: s_i is the
clean-value spread, so the root is where `clean_upfront_pct` is zero),
via the `isda` engine on a contract from `as_of` to maturity i at recovery
`quotes.recovery`. The sign test at zero: f(0) < 0 means that even with no
default risk in the new interval the protection leg already falls short of
the premium leg at s_i, so a positive λ_i is needed and Brent proceeds;
f(0) ≥ 0 means the earlier pillars already deliver more protection than
s_i pays for, the root would be at or below zero, and
`BootstrapArbitrageError(pillar=i, spread_bp=s_i, f_at_zero=f(0))` is
raised. Otherwise
`scipy.optimize.brentq` on [0, 5] with xtol 1e-12.

The distressed curve file stores `upfront_pct` at coupon 500 obtained by
converting the indicative spreads (2500, ..., 950) with
`quoted_spread_to_upfront` on the Section 2 discount curve, and stores the
spreads in `conventional_spread_bp`; the file's `note` says the upfronts
were derived that way in this section so Table 1 can show both.

**Acceptance criteria.**
1. Each bootstrapped curve reprices every pillar's conventional spread to
   within 0.01 bp (`BOOTSTRAP_REPRICE_BP`): 8 rows per curve.
2. Flat 100 bp at R = 0.40 (an in-test curve, all pillars 100) gives every
   λ_i within 3% (`FLAT_HAZARD_REL_TOL`) of 1.67%. This holds for the
   clean-value spread of item 24 (1.680 to 1.681%) and not for the dirty
   PV_prot / A (3.21% at 6M, review 05).
3. The IG and HY curves fit with every λ_i > 0; HY strictly increasing
   through 5Y; the 7Y and 10Y forward hazards sit below the 5Y one and
   the test pins them (`docs/CONVENTIONS_RESOLVED.md` item 30).
4. The distressed curve either (a) raises `BootstrapArbitrageError` naming
   the pillar and spread, or (b) fits, in which case `distressed_arb.json`
   raises; the test pins the pillar as a constant with the f(0) rows in the
   review. Whichever raises, `fallback="flat_from_shortest"` returns a
   single λ that reprices the 6M pillar to 0.01 bp, and `fallback="upfront"`
   returns per-pillar flat hazards that each reprice their own pillar to
   0.01 bp.
5. Upfront-quoted round trip: converting the distressed conventional spreads
   to upfronts and back reproduces the spreads to 1e-6 bp.
6. The 5Y upfront from the full bootstrapped curve and from the flat-hazard
   conversion of the 5Y quote differ by under 0.01 bp on an in-test flat
   curve and by more than 1 bp on HY; the difference is the reason both are
   reported.

**Tests.** `tests/test_bootstrap.py`.

**Outputs.**
- Table 1 `table_1_hazard_curves.csv`, one row per (curve, pillar):
  `curve, pillar, maturity, quote_kind, quote, coupon_bp,
  conventional_spread_bp, method, hazard_pct, survival_prob,
  cum_default_prob`. `method` is `bootstrap` or the fallback name.
- Chart 1 `chart_1_survival_hazard.png`: two panels, Q(t) and λ(t) on 0 to
  10Y for the three curves; data `chart_1_survival_hazard.csv` with
  `curve, t_years, hazard_pct, survival_prob` on a monthly grid.

---

### Section 7 — `validation/quantlib_check.py` and Table 2 (plus Table 5)

**Purpose.** The same trades and curves through `ql.IsdaCdsEngine` with the
matching flags. Done only when all three curves are within tolerance or the
residual is explained under "Open" with the rows.

**Files.** `cds/validation/__init__.py`, `cds/validation/quantlib_check.py`,
`cds/report.py` (Table 2, Table 5 generators), `tests/test_quantlib.py`,
`outputs/tables/table_2_quantlib_validation.{csv,md}`,
`outputs/tables/table_5_isda_vs_textbook.{csv,md}`.

**Rules implemented.** Three comparisons, each isolating one layer:
- **Pricer**: hand QuantLib our curves (`ql.DiscountCurve(node_dates,
  node_dfs, Actual365Fixed())`, which is log-linear;
  `ql.HazardRateCurve(pillar_dates, hazards, Actual365Fixed())`,
  backward-flat) and price the same
  `ql.CreditDefaultSwap(side, N, upfront=0, spread=c, schedule, Following,
  Actual360(), settlesAccrual=True, paysAtDefaultTime=True,
  protectionStart=step_in, upfrontDate=cash_settle, claim=None,
  lastPeriodDayCounter=Actual360(True), rebatesAccrual=True,
  tradeDate=trade, cashSettlementDays=3)` with
  `ql.IsdaCdsEngine(prob, R, disc, None, ql.IsdaCdsEngine.Taylor,
  ql.IsdaCdsEngine.HalfDayBias, ql.IsdaCdsEngine.Piecewise)`. Compare
  clean upfront (QuantLib's upfront NPV made clean with `accrualRebate`),
  par spread (`fairSpread()`) and the two legs.
- **Bootstrap**: `ql.PiecewiseFlatHazardRate` from `ql.SpreadCdsHelper`s
  built with `ql.CreditDefaultSwap.ISDA` as the pricing model and the same
  conventions, on our discount curve; compare hazards per pillar and the 5Y
  price.
- **CS01**: bump the 5Y quote 1 bp on both sides, re-bootstrap on both
  sides, compare the 5Y CS01 in currency and in bp of notional.
Trades: 5Y buy at coupon 100 (IG) and 500 (HY, distressed), plus 1Y and 10Y
at coupon 100 on IG, N = 10m, as_of = the snapshot date.

**Acceptance criteria.**
1. Pricer comparison: |Δ clean upfront| ≤ 1 bp of notional (`QL_UPFRONT_BP`)
   and |Δ par spread| ≤ 0.5 bp (`QL_PAR_SPREAD_BP`) on all three curves,
   every trade.
2. Bootstrap comparison, on matched nodes: our sequential fit with the
   survival curve's nodes on QuantLib's dates (adjusted maturity + 1 day)
   against QuantLib's node hazards, |Δ λ_i| ≤ 0.5 bp of hazard
   (`QL_HAZARD_BP`) on every pillar of every curve (distressed: whichever
   of the curve or its fallback fits). The on-our-grid rows (QuantLib's
   curve read over our pillar intervals) stay in Table 2 as information
   against the same bar; the two distressed rows that miss it by 0.04 and
   0.01 bp are the node placement and are pinned by the test
   (`docs/CONVENTIONS_RESOLVED.md` item 35).
3. CS01: |Δ| ≤ 1% of the CS01 or $50, whichever is larger, per curve.
4. Table 2 and Table 5 written; every row has a `pass` column.
If 1 fails, the causes are checked in the Part C item 4 order and each check
is a row in the review.

**Tests.** `tests/test_quantlib.py` (the comparisons above are the tests;
Table 2 is written from the same rows).

**Outputs.**
- Table 2 `table_2_quantlib_validation.csv`, long format:
  `curve, trade, metric, ours, quantlib, diff, unit, tolerance, pass` with
  `metric` in {`clean_upfront_pct`, `par_spread_bp`, `cs01_usd`,
  `pv_protection`, `risky_annuity`} and per-pillar `hazard_pct_<pillar>`
  rows for the bootstrap comparison.
- Table 5 `table_5_isda_vs_textbook.csv`: `curve, tenor, coupon_bp,
  isda_clean_upfront_pct, textbook_upfront_pct, diff_bp, isda_par_spread_bp,
  textbook_par_spread_bp, diff_par_bp` for 1Y, 5Y, 10Y on each curve, the
  textbook model fed the same flat-hazard-equivalent λ and the discount
  curve's zero rate to maturity.

---

### Section 8 — `risk.py`, Table 3, Chart 2

**Purpose.** CS01 by pillar and parallel, rec01 (both), IR01, JTD, both
thetas, exactly as Part D.2; the risk report and the corrected Chart 2.

**Files.** `cds/risk.py`, `cds/types.py` (`RiskReport` fields, listed
below; any difference from this list goes under "Against the plan"),
`cds/report.py` (Table 3, Chart 2), `tests/test_risk.py`,
`outputs/tables/table_3_risk_report.{csv,md}`,
`outputs/charts/chart_2_recovery_dependence.{png,csv}`.

**Rules implemented.** Part D.2 and Part C items 2, 3 and 5. `risk(state,
trade) -> RiskReport` with fields, all in currency for the trade's side:
`mtm, cs01_6m, cs01_1y, cs01_2y, cs01_3y, cs01_4y, cs01_5y, cs01_7y,
cs01_10y, cs01_bucket_sum, cs01_parallel, cs01_central_6m, cs01_central_1y,
cs01_central_2y, cs01_central_3y, cs01_central_4y, cs01_central_5y,
cs01_central_7y, cs01_central_10y, cs01_central_parallel, rec01,
rec01_hazard_fixed, ir01, jtd, theta_calendar_1d, theta_rolldown_1d,
theta_calendar_1m, theta_rolldown_1m`. Bumps rebuild from `state.quotes`
and the rates file referenced by `state.discount` (the discount curve keeps
its input par rates for IR01). Theta builds a new `MarketState` at
`as_of + shift` with `with_as_of` in the two modes and prices the same
trade; the coupon paid in the window, if any, is added with the side's sign.

**Acceptance criteria.**
1. `cs01_bucket_sum` is within 2% (`CS01_SUM_REL_TOL`) of `cs01_parallel` on
   all three curves. Not exactly: a bucketed bump changes one hazard and
   the survival at every later pillar is re-solved, so the sum of eight
   sequential re-bootstraps is not the joint re-bootstrap; the residual is
   second order in the bump.
2. `rec01` (re-bootstrapped) on a $10m 5Y trade struck at the market par
   spread (a running-spread trade with `coupon_bp = s_par`) is under $500
   (`REC01_PAR_USD`); on the running-spread trade struck at s_par − 200 bp
   it is at least 10× larger (`REC01_OFFMARKET_MULT`). `rec01_hazard_fixed`
   is the same for both trades to within 1% and equals −0.01·I·N·side to
   0.1%, where I is the undiscounted-recovery protection integral from
   Section 4.
3. `theta_calendar_1m` equals `theta_rolldown_1m` within $100
   (`THETA_FLAT_USD`) on an in-test flat curve (all pillars 100 bp, flat
   rates) and they differ by more than $1,000 (`THETA_STEEP_USD`) on HY at
   1 month.
4. `jtd` for the buyer equals (1 − R)·N − mtm − accrued_since_period_start
   to $0.01, and the seller's is the negative.
5. `ir01` on the IG par trade is under $200 in absolute value and on the
   distressed upfront trade over $500 (the review records both).
6. Central CS01 differs from one-sided by under 1% per pillar on IG.

**Tests.** `tests/test_risk.py`.

**Outputs.**
- Table 3 `table_3_risk_report.csv`: one row per curve for the 5Y $10m
  protection buy at the standard coupon (100 IG, 500 HY and distressed),
  columns `curve, trade` then the `RiskReport` field names in the order
  above. The `.md` renders it transposed (measures as rows) for reading.
- Chart 2 `chart_2_recovery_dependence.png`, two panels per Part C item 1;
  data `chart_2_recovery_dependence.csv` with `recovery, implied_5y_default_prob,
  mtm_par_trade, mtm_offmarket_trade` for R from 0.10 to 0.60 in steps of
  0.01 on the IG curve.

---

### Section 9 — `scenarios.py`, `explain.py`, Chart 3, Table 4

**Purpose.** The scenario grid vectorised with numpy, full revaluation
against first-order and first-plus-gamma, and the P&L explain with its
unexplained residual.

**Files.** `cds/scenarios.py`, `cds/explain.py`, `cds/types.py`
(`ExplainResult` fields, below), `cds/legs.py` (array support, see below),
`cds/report.py` (Chart 3, Table 4), `tests/test_scenarios.py`,
`tests/test_explain.py`, `outputs/charts/chart_3_pnl_vs_spread_shock.{png,csv}`,
`outputs/tables/table_4_pnl_explain.{csv,md}`,
`outputs/tables/table_4_pnl_explain_full.{csv,md}`.

**Rules implemented.** SPEC 6.8. A scenario is a transformation of
`MarketCurveQuotes`, the recovery and the OIS inputs:
- spread multipliers ×0.5, ×0.75, ×1.5, ×2, ×3, ×4 (Chart 3 sweeps
  ×0.5 to ×4 in 0.05 steps);
- recovery 0.40 → 0.20 and → 0.10 (IG; for HY 0.25 → 0.10);
- steepen: +0, +5, ..., +35 bp across the 8 pillars (linear in pillar
  index, 0 at 6M, +35 at 10Y); flatten: the negative;
- rates ±100 bp on every OIS input;
- combined: ×2, recovery → 0.20, rates −100.
`scenarios.run(state, trade, grid) -> DataFrame` re-bootstraps each
scenario (Brent per pillar, looped over scenarios) and then revalues the
whole grid with one vectorised call: `legs.py` accepts hazard arrays of
shape `(n_scenarios, n_pillars)` and returns leg values of shape
`(n_scenarios,)`. Section 4's scalar path is the `n_scenarios = 1` case;
this section is allowed to touch `legs.py` for that and nothing else.

`explain(state_t0, state_t1, trade) -> ExplainResult` with fields
`pnl_full, pnl_spread_first_order, pnl_spread_gamma, pnl_recovery,
pnl_rates, pnl_theta, pnl_cross, residual, residual_pct_of_total`:
- `pnl_spread_first_order = Σ_i cs01_i(t_0)·Δs_i` with Δs_i the change in
  the pillar's conventional spread in bp;
- `pnl_spread_gamma = ½·Γ·(Δs_parallel)²` with Γ from the central second
  difference of the parallel bump at t_0 (±1 bp) and Δs_parallel the
  average pillar move;
- `pnl_recovery = rec01·ΔR` in points; `pnl_rates = ir01·Δr` in bp;
- `pnl_theta = theta_calendar` over the actual date gap (0 if
  `as_of` is unchanged);
- `pnl_cross`: the spread-recovery cross term from a joint bump
  (V(s+1, R+1) − V(s+1, R) − V(s, R+1) + V(s, R))·Δs·ΔR;
- `residual = pnl_full − Σ(the rest)`.

**Acceptance criteria.**
1. Residual under 2% of `pnl_full` (`EXPLAIN_RESIDUAL_PCT`) for a 10 bp
   parallel move on IG and HY.
2. `pnl_spread_gamma` is negative for the protection buyer on a +100 bp
   parallel move, and the docstring states the reason: the buyer's MTM is
   (s − c)·A(s) and the risky annuity A falls as s rises, so the MTM is
   concave in spread; the buyer is short convexity and CS01 shrinks as
   spreads widen. (Corrected from "positive" in `docs/CONVENTIONS_RESOLVED.md`,
   checked there on the flat-hazard textbook model at s = 100 and 500 bp,
   c = 100 bp, R = 40%, r = 4%, T = 5.)
3. Full revaluation of the Chart 3 sweep (71 scenarios) plus the Table 4
   scenarios runs in under 10 seconds (`GRID_SECONDS`) wall clock, timed in
   the test.
4. The vectorised leg values equal the scalar path to 1e-12 for 5 random
   scenarios.
5. For the ×3 spread scenario the residual is material: over 5% of
   `pnl_full` on HY (the spec says this should be so; the review records
   the number).

**Tests.** `tests/test_scenarios.py`, `tests/test_explain.py`.

**Outputs.**
- Chart 3 `chart_3_pnl_vs_spread_shock.png`: buyer P&L of the 5Y IG trade
  against the spread multiplier, full revaluation, first-order, and
  first-plus-gamma; data `chart_3_pnl_vs_spread_shock.csv` with
  `spread_multiplier, pnl_full, pnl_first_order, pnl_second_order`.
- Table 4 `table_4_pnl_explain.csv`, six scenarios (×1.5, ×3, recovery →
  0.20, steepen, rates +100, combined) on the 5Y IG buy: `scenario,
  pnl_full, pnl_spread_first_order, pnl_spread_gamma, pnl_recovery,
  pnl_rates, pnl_theta, pnl_cross, residual, residual_pct_of_total`.
  `table_4_pnl_explain_full.csv` has every scenario in the grid, same
  columns.

---

### Section 10 — README and results page

**Purpose.** The README with Table 2 above the fold, the rec01 explanation,
the ISDA-versus-textbook comparison, a CDS-bond basis note with one worked
example, a sanity check of implied 5Y default probability against a public
cumulative default table, and a one-page results HTML generated from the
outputs. Nothing is recomputed in the README.

**Files.** `README.md` (rewritten), `scripts/basis_example.py`,
`scripts/implied_vs_historical.py`, `scripts/build_results_page.py`,
`data/defaults/cumulative_default_rates.csv`, `data/defaults/README.md`,
`docs/DATA_NOTE.md` (default table source recorded),
`outputs/tables/table_6_basis_example.{csv,md}`,
`outputs/tables/table_7_implied_vs_historical.{csv,md}`,
`outputs/results.html`, `tests/test_readme_paths.py`.

**Rules implemented.**
- Basis: for a hypothetical 5Y bond of the IG name priced to a Z-spread z
  (typed into the script with the price, coupon and the Section 2 curve),
  basis = CDS 5Y par spread − z, one worked row with the sign of the basis
  and one sentence each on the three usual reasons for a persistent basis
  (funding, cheapest-to-deliver, and the difference between par spread
  and a fixed-coupon contract's running cost).
- Implied versus historical: 1 − Q(5) from each curve against the 5Y
  cumulative default rate of the matching bucket in a public Moody's or S&P
  annual default study (IG_flat ↔ Baa/BBB, HY_steep ↔ B, distressed ↔
  Caa-C/CCC), with the ratio and one sentence on why risk-neutral exceeds
  historical.
- `build_results_page.py` reads every `outputs/tables/*.md` and
  `outputs/charts/*.png` and writes a single self-contained
  `outputs/results.html` (images embedded as data URIs) in the same
  generated-from-outputs pattern as project 1's `reports/results.md`.

**Acceptance criteria.**
1. Every path the README references exists (`tests/test_readme_paths.py`
   parses the Markdown links and image paths).
2. Table 2 appears before any other table in the README.
3. `results.html` under 5 MB, opens without external requests (no `http`
   in `src=` or `href=` except the repo link).
4. The README states, in its first screen, that the curves are illustrative
   and the library is validated against QuantLib.

**Tests.** `tests/test_readme_paths.py`.

**Outputs.** Table 6 `table_6_basis_example.csv`: `bond, price, coupon_pct,
maturity, z_spread_bp, cds_5y_par_spread_bp, basis_bp`. Table 7
`table_7_implied_vs_historical.csv`: `curve, rating_bucket, implied_5y_pd_pct,
historical_5y_pd_pct, ratio, source`. `outputs/results.html`.

---

## Tolerance constants (all in `tests/conftest.py`)

| Constant | Value | Used in | Reason |
|---|---|---|---|
| `OIS_REPRICE_BP` | 0.01 | S2 | a bootstrap must reprice its inputs to solver precision |
| `PAR_SPREAD_ENGINE_AGREEMENT_BP` | 0.1 | S4 | the spec's bar for the daily grid versus the closed form |
| `CREDIT_TRIANGLE_BP` | 0.5 | S4 | the triangle is exact only in the continuous limit; daily coupons leave a small residual |
| `BOOTSTRAP_REPRICE_BP` | 0.01 | S6 | same as OIS: solver precision |
| `FLAT_HAZARD_REL_TOL` | 0.03 | S6 | discounting and discrete coupons move λ from s/(1−R) by about 1 to 2% |
| `QL_UPFRONT_BP` | 1.0 | S7 | the spec's validation bar |
| `QL_PAR_SPREAD_BP` | 0.5 | S7 | the kickoff's validation bar |
| `QL_HAZARD_BP` | 0.5 | S7 | a pillar hazard is a spread-like quantity; same bar as par spread |
| `CS01_SUM_REL_TOL` | 0.02 | S8 | sequential re-bootstraps are not the joint one; second order in 1 bp |
| `REC01_PAR_USD` | 500 | S8 | bootstrap tolerance × annuity × notional is a few dollars; 500 leaves room |
| `REC01_OFFMARKET_MULT` | 10 | S8 | 200 bp off market times ΔA is hundreds to thousands of dollars |
| `THETA_FLAT_USD` | 100 | S8 | on a flat curve the two thetas differ only by the calendar-versus-tenor day count |
| `THETA_STEEP_USD` | 1000 | S8 | one month of roll-down on a 100 bp/yr slope on $10m is over $1,000 |
| `EXPLAIN_RESIDUAL_PCT` | 2.0 | S9 | the spec's "small for 10 bp moves" |
| `GRID_SECONDS` | 10.0 | S9 | the spec's "runs in seconds" |
