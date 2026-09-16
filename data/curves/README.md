# data/curves

Illustrative CDS quote curves, one JSON file per curve, written in Section 6
of `BUILD_PLAN.md`. The format is fixed in the plan, Part D.3. Every file has
a `source` field and a `note` field stating that the levels are stylised.

Planned files:

| file | pillars 6M/1Y/2Y/3Y/4Y/5Y/7Y/10Y (bp) | recovery | quoted as |
|---|---|---|---|
| `IG_flat.json` | 45, 50, 60, 70, 80, 90, 105, 120 | 40% | par spread |
| `HY_steep.json` | 150, 200, 300, 380, 440, 500, 560, 600 | 25% | par spread |
| `distressed_inverted.json` | 2500, 2200, 1800, 1500, 1350, 1200, 1050, 950 | 20% | upfront at 500 bp coupon, conventional spread stored alongside |

See `docs/DATA_NOTE.md` for what is illustrative and what is sourced.
