"""Shared tolerance constants for the test suite.

Every numerical tolerance lives here with a one-line reason, and a test file
imports the ones it uses at its top. Values are those in BUILD_PLAN.md,
"Tolerance constants". No fixtures yet; sections add them as they need them.
"""

# Section 2: a bootstrap must reprice its inputs to solver precision.
OIS_REPRICE_BP = 0.01

# Section 4: the spec's bar for the daily grid versus the closed form.
PAR_SPREAD_ENGINE_AGREEMENT_BP = 0.1

# Section 4: the credit triangle is exact only in the continuous limit; daily
# coupons leave a small residual.
CREDIT_TRIANGLE_BP = 0.5

# Section 6: same as OIS, solver precision.
BOOTSTRAP_REPRICE_BP = 0.01

# Section 6: discounting and discrete coupons move lambda from s/(1-R) by
# about 1 to 2 percent.
FLAT_HAZARD_REL_TOL = 0.03

# Section 7: the spec's validation bar for upfront, in bp of notional.
QL_UPFRONT_BP = 1.0

# Section 7: the kickoff's validation bar for par spread.
QL_PAR_SPREAD_BP = 0.5

# Section 7: a pillar hazard is a spread-like quantity; same bar as par spread.
QL_HAZARD_BP = 0.5

# Section 7: the risky annuity per unit spread; 0.01 is 1 bp of notional at
# a 100 bp coupon, the same bar as the upfront.
QL_ANNUITY_ABS_TOL = 0.01

# Section 7: CS01 agrees to 1% of itself or $50, whichever is larger (the
# plan's criterion 3); the two bootstraps place their nodes 1 to 3 days apart.
QL_CS01_REL_TOL = 0.01
QL_CS01_ABS_USD = 50.0

# Section 8: sequential per-pillar re-bootstraps are not the joint one; the
# gap is second order in a 1 bp bump.
CS01_SUM_REL_TOL = 0.02

# Section 8: bootstrap tolerance x annuity x notional is a few dollars on a
# par trade; 500 leaves room.
REC01_PAR_USD = 500.0

# Section 8: 200 bp off market times the annuity's recovery sensitivity is
# hundreds to thousands of dollars on $10m.
REC01_OFFMARKET_MULT = 10.0

# Section 8: on a flat curve the two thetas differ only by the
# calendar-versus-tenor day count.
THETA_FLAT_USD = 100.0

# Section 8: one month of roll-down on a 100 bp/yr slope on $10m is over
# $1,000.
THETA_STEEP_USD = 1000.0

# Section 9: the spec's "small for 10 bp moves".
EXPLAIN_RESIDUAL_PCT = 2.0

# Section 9: the spec's "runs in seconds".
GRID_SECONDS = 10.0

# Section 1: accrual fractions are ratios of integers; 1e-12 is float noise.
DAY_COUNT_ABS_TOL = 1e-12

# Section 2: the interpolation identities (log-linearity, flat extrapolation,
# forward from the DF ratio) hold exactly in exact arithmetic; 1e-12 is float
# noise.
CURVE_IDENTITY_ABS_TOL = 1e-12

# Section 2: two bootstraps of the same par equations (ours and QuantLib's)
# agree to solver precision; 1e-10 in P is under 1e-7 bp of rate.
QL_DISCOUNT_ABS_TOL = 1e-10

# Section 3: the density integrated with scipy quad per pillar interval, on a
# smooth integrand, against 1 - Q(T); the plan's bar, far above quad's own
# error estimate.
DENSITY_INTEGRAL_ABS_TOL = 1e-9

# Section 3: QuantLib's backward-flat HazardRateCurve integrates the same
# piecewise-constant hazard over the same act/365F times; 1e-12 is float noise.
QL_SURVIVAL_ABS_TOL = 1e-12

# Section 4: the grid's error against the closed form is first order in the
# step, so halving the step halves it; the band allows for the coupon-date
# points that break the regular spacing.
GRID_CONVERGENCE_RATIO = (1.9, 2.1)

# Section 4: half a day of accrual on default over a 5Y contract at 1% hazard
# moves the par spread by about 0.001 bp; the plan's bar is 0.02.
HALF_DAY_BIAS_BP = 0.02

# Section 4: QuantLib's IsdaCdsEngine evaluates the same closed form on the
# same merged grid, so the leg values differ by float noise only.
QL_LEGS_ABS_TOL = 1e-12

# Section 5: at the par coupon (the clean-value spread, item 24) the clean
# upfront is zero up to float noise in the legs; the plan's bar is 0.01 bp of
# notional.
PAR_UPFRONT_BP = 0.01

# Section 5: the same identity in currency on $10m; the plan's "under $1".
PAR_UPFRONT_USD = 1.0

# Section 5: the par spread is a ratio of leg values, the settlement factor
# and the accrued, none of which depend on the coupon, so repricing at that
# coupon returns it to float precision; the plan's 1e-9 bp.
PAR_SPREAD_REPRICE_BP = 1e-9

# Section 5: spread -> upfront -> spread is two Brent solves with xtol 1e-12
# in the hazard, about 1e-8 bp of spread; the plan's 1e-6 bp.
CONVERSION_ROUNDTRIP_BP = 1e-6

# Section 5: settlement discounting, the accrued and the side sign are single
# multiplications of leg values; 1e-12 is float noise.
PRICER_IDENTITY_ABS_TOL = 1e-12

# Section 5: QuantLib's accrualRebate is the same integer day count times the
# same coupon and notional; 1e-6 currency on $10m is float noise.
QL_ACCRUED_ABS_USD = 1e-6

# Section 5: the textbook formulas are closed forms; 1e-12 is float noise.
TEXTBOOK_ABS_TOL = 1e-12

# Section 5: the flat-hazard solve is a Brent with xtol 1e-12 in the hazard;
# 1e-9 leaves room for the rounding of the par spread it inverts.
FLAT_HAZARD_SOLVE_ABS_TOL = 1e-9

# Section 5: a flat hazard has one credit-triangle spread and the clean-value
# spread sees it on every tenor up to the discounting of the one-day coupon
# lag; 0.03 bp between 6M and 10Y on the flat 1% curve, bar 0.1.
CLEAN_SPREAD_TENOR_RANGE_BP = 0.1

# Section 5: QuantLib's fairUpfront and fairSpread are the same leg values
# through the same settlement discounting and accrual rebate; the largest
# gap seen is 3e-10 bp (inverted 6M), from the order of the divisions.
QL_PRICER_ABS_TOL = 1e-9

# Section 6: on a flat curve the flat-hazard conversion is exact, so the 5Y
# upfront from the bootstrapped curve and from the single-hazard conversion
# of the 5Y quote agree to solver precision; the plan's 0.01 bp of notional.
UPFRONT_CURVE_VS_FLAT_BP = 0.01

# Section 6: on the steep HY curve the two 5Y upfronts differ by more than
# this, in bp of notional; the plan's "more than 1 bp", the reason both are
# reported.
UPFRONT_CURVE_VS_FLAT_HY_MIN_BP = 1.0

# Section 6 (docs/CONVENTIONS_RESOLVED.md items 34 and 38): a committed
# output is compared with its regeneration numerically, every float within
# max(OUTPUT_ABS_TOL, OUTPUT_ABS_TOL * |committed value|) and every text
# column exactly. The files hold 10 decimal places, so 1e-9 absolute is a
# full digit of slack over the rounding on a number of order 1, and 1e-9
# relative is the same slack on a number in currency on $10m.
OUTPUT_ABS_TOL = 1e-9


def assert_output_current(fresh_csv, committed_csv) -> None:
    """The two CSVs hold the same table: same columns in the same order, same
    row count, text columns equal, every float within
    max(OUTPUT_ABS_TOL, OUTPUT_ABS_TOL * |committed value|) (items 34 and
    38). Imported by every test that checks an output is current."""
    import pandas as pd

    fresh, committed = pd.read_csv(fresh_csv), pd.read_csv(committed_csv)
    assert list(fresh.columns) == list(committed.columns), (list(fresh.columns), list(committed.columns))
    assert len(fresh) == len(committed), (len(fresh), len(committed))
    for col in fresh.columns:
        a, b = fresh[col], committed[col]
        if pd.api.types.is_float_dtype(a) or pd.api.types.is_float_dtype(b):
            both_nan = a.isna() & b.isna()
            assert both_nan.equals(a.isna()) and both_nan.equals(b.isna()), col
            gap = (a[~both_nan] - b[~both_nan]).abs()
            allowed = (OUTPUT_ABS_TOL * b[~both_nan].abs()).clip(lower=OUTPUT_ABS_TOL)
            assert (gap <= allowed).all(), (col, float((gap - allowed).max()))
        else:
            assert a.equals(b), col
