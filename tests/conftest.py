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
