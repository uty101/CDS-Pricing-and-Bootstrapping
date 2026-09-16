# CDS Pricing and Hazard Rate Bootstrapping

An ISDA-convention single-name CDS pricing library: a term structure of market
CDS quotes is bootstrapped into a piecewise-constant hazard rate curve, a CDS
is priced from that curve (premium leg, protection leg, accrual on default,
IMM schedule, fixed coupon with upfront), and the library produces the risk
report a credit structuring desk expects: CS01 by pillar, rec01, IR01,
jump-to-default, theta, and a P&L explain under spread, recovery and rate
shocks. Everything is validated against QuantLib's `IsdaCdsEngine`. The
curves are illustrative; the library is the deliverable.

**Status: in progress.** The work is split into sections, one per session,
listed in [BUILD_PLAN.md](BUILD_PLAN.md). Each section ends with a review file
under [review/](review/). Nothing here is priced yet.

Spec: [docs/SPEC.md](docs/SPEC.md). Data provenance: [docs/DATA_NOTE.md](docs/DATA_NOTE.md).
