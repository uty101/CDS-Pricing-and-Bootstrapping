# data/curves

Illustrative CDS quote curves, one JSON file per curve, written in Section 6
of `BUILD_PLAN.md` by `scripts/make_curves.py`. The format is fixed in the
plan, Part D.3. Every file has a `source` field (`illustrative`) and a
`note` field stating that the levels are stylised and not an observation of
any name on any date. All four share the valuation date of the rates
snapshot, `2026-09-15`; pillar dates are the standard maturities from that
date (the 6M pillar is 20 Dec 2026, 96 days out).

| file | pillars 6M/1Y/2Y/3Y/4Y/5Y/7Y/10Y (bp) | recovery | quoted as |
|---|---|---|---|
| `IG_flat.json` | 45, 50, 60, 70, 80, 90, 105, 120 | 40% | par spread |
| `HY_steep.json` | 150, 200, 300, 380, 440, 500, 560, 600 | 25% | par spread |
| `distressed_inverted.json` | 2500, 2200, 1800, 1500, 1350, 1200, 1050, 950 | 20% | clean upfront in % of notional at a 500 bp coupon; the spreads are stored in `conventional_spread_bp` |
| `distressed_arb.json` | 6000, then as distressed | 20% | as `distressed_inverted` |

The distressed upfronts are `cds.pricer.quoted_spread_to_upfront` of the
spreads on `data/rates/sofr_ois_2026-09-15.json`, one flat hazard per pillar
on the pillar's own maturity, stored at full precision so that converting
back reproduces the spreads to 1e-6 bp (Section 6 criterion 5).

`distressed_arb.json` exists because the distressed curve as specified
bootstraps with every hazard positive (Part B item 6): it is the same curve
with the 6M pillar raised in 500 bp steps until the sequential bootstrap
needs a negative hazard, which happens at 6000 bp, at the 1Y pillar. It is
used only for the arbitrage-detection test and the fallback demonstration,
and appears in Table 1 under the `upfront` fallback.

Read a file with `cds.bootstrap.market_curve_quotes_from_file`; bootstrap it
with `cds.bootstrap.bootstrap`. See `docs/DATA_NOTE.md` for what is
illustrative and what is sourced.
