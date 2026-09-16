# data/rates

The SOFR OIS par-rate snapshot the discount curve is bootstrapped from,
written in Section 2 of `BUILD_PLAN.md` as `sofr_ois_<YYYY-MM-DD>.json`.
The format is fixed in the plan, Part D.3: tenors 1M to 30Y, annual fixed
act/360, with `source`, `source_url`, `snapshot_taken` and `note` fields.

FRED publishes overnight SOFR and its backward-looking averages, not OIS par
rates, so the snapshot is taken from a published swap-rate page; the plan's
Part B item 4 names the candidates and `docs/DATA_NOTE.md` records the one
used.
