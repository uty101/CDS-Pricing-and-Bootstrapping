Credit structuring project 1 of 3

**CDS Pricing and Hazard Rate Bootstrapping**

*ISDA-convention single-name CDS pricer with a bootstrapped survival curve, full risk report and P&L explain*

|  |  |  |  |  |
|----|----|----|----|----|
| **Priority** | **Data cost** | **Build time** | **Target roles** | **Feeds into** |
| Build first | Illustrative curves | 2 to 3 weeks | Credit structuring, credit trading, credit quant | Survival curves into CDO and repack |

**1. What this project is**

A single-name CDS pricing library: take a term structure of market CDS spreads, bootstrap a piecewise-constant hazard rate curve consistent with the ISDA standard model conventions, price a CDS from the survival curve (premium leg, protection leg, accrued on default), convert between running spread and upfront with a fixed coupon, and produce the risk report a structuring desk expects: CS01, recovery sensitivity, IR01, jump-to-default, theta, and a P&L explain under spread and recovery shocks.

This is the foundation of everything a credit-linked products desk does. If the bootstrapper is right and the conventions match the ISDA model, the structuring roles you are applying to will take the rest of your background seriously. If it is a textbook toy with continuous compounding and no accrual-on-default, they will not.

**2. What we are trying to find**

- Given a spread curve and a recovery assumption, what survival curve is implied, and how sensitive is it to the recovery input?

- How much does the ISDA convention set (fixed coupons, upfront, accrual on default, discrete integration on a daily grid) change prices versus the textbook continuous model?

- What is the P&L of a 5-year protection position under parallel and non-parallel spread moves, recovery moves and rate moves, and how well does the linear risk (CS01, rec01, IR01) explain it?

- What does the mark-to-market look like as the contract ages (theta and roll-down) with an unchanged curve?

**3. The task**

1.  Build a discount curve from SOFR OIS rates (FRED or a published curve), with the ISDA day-count and interpolation conventions (act/360, log-linear discount factors).

2.  Implement the survival curve as piecewise-constant hazard rates on the CDS maturity pillars (6M, 1Y, 2Y, 3Y, 5Y, 7Y, 10Y).

3.  Write the premium leg and protection leg pricers on a discrete grid (daily or weekly), including accrued premium on default and the IMM date schedule (20 Mar, Jun, Sep, Dec).

4.  Bootstrap: for each pillar, solve for the hazard rate that makes the par spread match the market spread, holding earlier pillars fixed. Use Brent's method.

5.  Add the fixed-coupon convention: quoted spread ↔ upfront conversion at 100 bp and 500 bp coupons, with the ISDA flat-hazard rule for the conversion.

6.  Risk: CS01 by bumping each pillar 1 bp and in parallel; rec01 by bumping recovery 1%; IR01 by bumping the discount curve; jump-to-default; theta over 1 day and 1 month.

7.  Scenario engine: spread ×1.5, ×2, ×3; recovery 40 → 20 → 10; steepening and flattening; combined shocks. Compare full revaluation with the first-order risk and report the unexplained P&L.

8.  Validate against a public reference: the ISDA standard model (the open-source C library or the Python wrapper) or against QuantLib's IsdaCdsEngine. Match to within 1 bp of upfront.

**4. Data**

|  |  |  |
|----|----|----|
| **Need** | **Source** | **Notes** |
| CDS spread curves | Not free at single-name level. Options: (a) worked examples from published papers and O'Kane's book with full curves; (b) index-level spreads for CDX IG/HY and iTraxx Main/Crossover from press and Markit daily commentary; (c) synthetic curves derived from bond OAS | Say which; the pricer is the deliverable, the data is illustrative |
| Discount curve | FRED SOFR and OIS-like series; published SOFR swap rates | Monthly snapshot is enough |
| Recovery assumptions | Market convention: 40% senior unsecured, 20% subordinated, 25% for HY index names | State the convention |
| Historical defaults for sanity checks | Moody's or S&P annual default studies (free PDFs) | Compare implied versus historical default probabilities |

Free data is the weakness here. The correct framing in the README is that this is a pricing and risk library validated against a reference implementation, run on illustrative curves. That is exactly how a desk would test it before connecting it to Markit.

**5. What you should learn**

- Reduced-form (intensity) credit modelling: hazard rate, survival probability, default density.

- CDS mechanics: premium leg, protection leg, accrual on default, IMM dates, the Big Bang conventions (fixed coupons, upfront, standard recovery).

- The ISDA standard model: what it fixes (flat hazard for conversion, act/360, daily integration) and why the market agreed to it.

- Bootstrapping as sequential root finding, and why piecewise-constant hazard rates can go negative on bad curves.

- The credit triangle (spread ≈ hazard × loss given default) and where it breaks.

- Risk measures a desk uses daily: CS01 by bucket, rec01, IR01, JTD, and the difference between spread DV01 and risky annuity.

- Basis: CDS versus bond spreads, and the reasons a negative or positive basis persists.

**6. Methods and the maths**

**6.1 Survival curve**

> Q(t) = exp( − ∫₀ᵗ λ(s) ds ) = exp( − Σ_i λ_i (t_i − t\_{i−1}) )
>
> *Piecewise-constant hazard λ_i on pillar intervals. Default density is −dQ/dt = λ(t) Q(t).*

**6.2 Premium leg (risky annuity)**

With coupon dates t_1..t_n, accrual fractions Δ_j, discount factors P(t) and spread s:

> PV_prem = s × \[ Σ_j Δ_j P(t_j) Q(t_j) + Σ_j ∫\_{t\_{j−1}}^{t_j} (u − t\_{j−1}) P(u) (−dQ(u)) \]
>
> *The second sum is accrued premium on default. The bracket is the risky annuity A(s-independent). On a discrete grid the integral becomes a sum over grid points with the midpoint accrual.*

**6.3 Protection leg**

> PV_prot = (1 − R) ∫₀ᵀ P(u) (−dQ(u)) ≈ (1 − R) Σ_k P(u_k) \[ Q(u\_{k−1}) − Q(u_k) \]
>
> *R is recovery. Use a fine grid (daily) so that discretisation error is under 0.1 bp; the ISDA model uses a closed form per interval assuming flat hazard and flat forward rate within it.*

**6.4 Par spread and upfront**

> s_par = PV_prot / A
>
> Upfront (buyer of protection pays) = PV_prot − c × A
>
> *c is the fixed coupon (100 or 500 bp). The ISDA conversion between quoted spread and upfront uses a single flat hazard rate calibrated to the quoted spread, not the full bootstrapped curve; implement both and show the difference.*

**6.5 Bootstrapping**

For pillar i with market spread s_i, solve

> f(λ_i) = PV_prot(λ_1..λ_i) − s_i × A(λ_1..λ_i) = 0
>
> *Brent on λ_i ∈ \[0, 5\]. If the solution is negative or the bracket fails, the curve is arbitrageable (spread falls too fast with maturity); flag it rather than forcing a fit.*

**6.6 The credit triangle and closed-form checks**

> s ≈ λ (1 − R)
>
> *Exact for a flat hazard, continuous premium and no discounting. Use it as a unit test: a flat 100 bp curve at 40% recovery should bootstrap to λ ≈ 1.67% with small corrections from discounting and discrete coupons.*

**6.7 Risk measures**

> CS01_i = V(s_i + 1bp) − V(s_i), CS01_par = V(s + 1bp ∀ pillars) − V(s)
>
> rec01 = V(R + 1%) − V(R)
>
> *Note that for a par CDS, recovery sensitivity is close to zero because the bootstrapped hazard rises to compensate; it becomes large for seasoned off-market contracts and for upfront trades. This is a good interview point.*
>
> JTD = (1 − R) × Notional − PV_MTM
>
> *Immediate default loss for the protection seller (or gain for the buyer) net of current mark.*
>
> IR01 = V(r + 1bp) − V(r)
>
> *Small for par CDS; larger for upfront trades because the upfront is a PV of a spread differential.*

**6.8 P&L explain**

> ΔV_actual = ΔV_spread + ΔV_recovery + ΔV_rates + ΔV_theta + cross terms + unexplained
>
> *First-order terms use the risk measures above; second-order for large spread moves via a gamma term ½ Γ_s Δs². Report the unexplained residual as a percentage of the total; it should be small for 10 bp moves and material for ×3 spread shocks.*

**7. Build instructions**

1.  cds/curves.py (discount and survival curves with interpolation), cds/schedule.py (IMM dates, day counts), cds/legs.py, cds/pricer.py, cds/bootstrap.py, cds/risk.py, cds/scenarios.py, tests/.

2.  Write the schedule generator first and test it against known IMM dates and stub rules; most pricing errors are schedule errors.

3.  Implement the flat-hazard closed form per interval used by the ISDA model, then the brute-force daily grid, and check they agree to 0.1 bp.

4.  Validate the whole pipeline against QuantLib's IsdaCdsEngine on 3 curves; put the comparison table in the README.

5.  Vectorise pricing across a scenario grid with numpy so the P&L explain runs in seconds.

6.  Keep recovery as a curve object even if flat, so a term structure of recovery can be added later.

7.  Expose price(curve, trade), risk(curve, trade) and explain(curve_t0, curve_t1, trade) as the public API.

**8. What the results should look like**

|  |  |
|----|----|
| **Output** | **Content** |
| Table 1 | Bootstrapped hazard rates and survival probabilities by pillar for 3 example curves (IG flat, HY steep, distressed inverted) |
| Table 2 | Validation versus QuantLib: upfront, par spread, CS01 for each curve; differences in bp |
| Chart 1 | Survival curve and hazard rate term structure for the 3 curves |
| Chart 2 | Implied 5-year default probability as a function of recovery assumption, showing the flatness near par and the steepness for an off-market contract |
| Table 3 | Risk report for a 5Y \$10m protection buy: CS01 by pillar, parallel CS01, rec01, IR01, JTD, 1-day and 1-month theta |
| Chart 3 | P&L versus parallel spread shock from −50% to +300%, full revaluation versus first-order and second-order approximations |
| Table 4 | P&L explain for 6 scenarios with the unexplained residual |

**9. Making it useful**

- The validation table against QuantLib is the credibility anchor; put it above the fold in the README.

- The rec01 result (near zero at par, large off-market) is a 2-minute interview answer that shows you understand the mechanics rather than the formula.

- The survival curve object is the input to the CDO model; the discount curve and schedule code are reused by the repack model. Build this one first.

- Add a short note on the CDS-bond basis with one worked example, since a structuring desk lives on that basis when building credit-linked notes.

**10. Where it will break**

- Conventions: a wrong stub rule, day count or accrual treatment produces errors of several bp that look like model differences. Test the schedule in isolation.

- Inverted distressed curves will fail to bootstrap with piecewise-constant hazards; show the failure and the standard fix (flat hazard from the shortest pillar, or upfront-quoted pricing).

- Recovery is not observable; a 40% assumption on a name trading at 10 points upfront is wrong, and the market quotes recovery locks for a reason. Mention it.

- The free data limitation: state clearly that the curves are illustrative and the library is what is being demonstrated.
