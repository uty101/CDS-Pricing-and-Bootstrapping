# data/rates

The SOFR OIS par-rate snapshot the discount curve is bootstrapped from,
written in Section 2 of `BUILD_PLAN.md` as `sofr_ois_<YYYY-MM-DD>.json`.
The format is fixed in the plan, Part D.3: tenors 1M to 30Y, annual fixed
act/360, with `source`, `source_url`, `snapshot_taken` and `note` fields.
This repo's file adds `source_by_tenor` (one label per row, as
`docs/CONVENTIONS_RESOLVED.md` item 4 asks) and `source_urls` (one URL per
source).

## `sofr_ois_2026-09-15.json`

Rates for 15 September 2026, read on 16 September 2026. The date in the
file name is the date of the rates, which is also the valuation date every
illustrative curve in `data/curves/` uses (plan Part D.3).

| tenor | par rate % | source |
|---|---|---|
| 1M | 3.88572 | CME Term SOFR fixing, 15 Sep 2026, republished by global-rates.com |
| 3M | 3.97991 | same |
| 6M | 4.12897 | same |
| 1Y | 4.30 | BlueGamma USD SOFR swap page, 15 Sep 2026 close, 2 dp |
| 2Y | 4.48 | same |
| 3Y | 4.56 | same |
| 4Y | 4.55 | same |
| 5Y | 4.55 | same |
| 7Y | 4.56 | same |
| 10Y | 4.60 | same |
| 15Y | 4.70 | same |
| 20Y | 4.74 | same |
| 30Y | 4.66 | same |

`docs/CONVENTIONS_RESOLVED.md` item 4 names ICE Swap Rate for 1Y to 30Y.
On the day of the snapshot ice.com showed no fixings on a free page, so the
1Y to 30Y rows come from BlueGamma's public page instead; the substitution
is recorded in `docs/DATA_NOTE.md` and in `review/02_discount.md` under
"Against the plan". The 1M and 3M rows of the two sources agree to
BlueGamma's rounding (3.89 and 3.98), which is the only cross-check.

How the file is read: `cds.curves.discount_curve_from_file(path)` checks
the provenance fields are present, then calls `bootstrap_ois` with the
tenors and rates. The bootstrap treats every row as an OIS par rate with
annual fixed act/360 payments (a single payment under 1Y), spot date equal to
`as_of`, payment dates rolled Following on the weekend-only calendar.
