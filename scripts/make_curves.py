"""Write the illustrative curve files in data/curves/ (BUILD_PLAN.md Section 6).

The levels are the ones docs/DATA_NOTE.md records; they are stylised, not
observations. The two spread-quoted curves are written as given. The
distressed curve is written as upfront quotes at a 500 bp coupon, each
upfront being the flat-hazard conversion (cds.pricer.quoted_spread_to_upfront)
of the indicative spread on the committed discount curve, on the pillar's own
standard maturity, at the curve's recovery; the spreads are stored alongside
in conventional_spread_bp. distressed_arb is the distressed curve with the
6M pillar raised in 500 bp steps until the sequential bootstrap's f(0)
changes sign at some pillar (Part B item 6), written the same way.

The valuation date is the rates snapshot's as_of, read from the rates file.
Run with `uv run python scripts/make_curves.py`; every file is committed.
"""

from __future__ import annotations

from pathlib import Path

from cds.bootstrap import BootstrapArbitrageError, bootstrap, pillar_trade, write_curve_file
from cds.conventions import PILLARS, RECOVERY_HY_INDEX, RECOVERY_SENIOR, RECOVERY_SUBORDINATED, STANDARD_COUPONS_BP
from cds.curves import discount_curve_from_file
from cds.pricer import quoted_spread_to_upfront
from cds.types import MarketCurveQuotes, Quote

ROOT = Path(__file__).resolve().parent.parent
RATES_FILE = ROOT / "data" / "rates" / "sofr_ois_2026-09-15.json"
OUT_DIR = ROOT / "data" / "curves"

SOURCE = "illustrative"
ILLUSTRATIVE = (
    "Illustrative levels chosen in Section 0 (docs/DATA_NOTE.md); not an observation of any name on any date. "
    "Pillar dates are the standard maturities from as_of (the 6M pillar is 96 days out, docs/CONVENTIONS_RESOLVED.md item 18)."
)

IG_LEVELS_BP = (45.0, 50.0, 60.0, 70.0, 80.0, 90.0, 105.0, 120.0)
HY_LEVELS_BP = (150.0, 200.0, 300.0, 380.0, 440.0, 500.0, 560.0, 600.0)
DISTRESSED_LEVELS_BP = (2500.0, 2200.0, 1800.0, 1500.0, 1350.0, 1200.0, 1050.0, 950.0)
DISTRESSED_COUPON_BP = STANDARD_COUPONS_BP[1]  # 500

# distressed_arb: the 6M pillar is raised by this much per step until the
# bootstrap raises; the loop stops at the first level that does.
ARB_STEP_BP = 500.0
ARB_MAX_STEPS = 40


def spread_curve(label: str, levels: tuple[float, ...], recovery: float, as_of) -> MarketCurveQuotes:
    return MarketCurveQuotes(as_of=as_of, pillars=PILLARS, quotes=tuple(Quote(kind="par_spread_bp", value=v) for v in levels), recovery=recovery, label=label)


def upfront_curve(label: str, spreads: tuple[float, ...], recovery: float, discount) -> tuple[MarketCurveQuotes, tuple[float, ...]]:
    """The spreads converted pillar by pillar to clean upfronts at the coupon."""
    as_spreads = spread_curve(label, spreads, recovery, discount.as_of)
    upfronts = tuple(quoted_spread_to_upfront(discount, pillar_trade(as_spreads, i, DISTRESSED_COUPON_BP), s) for i, s in enumerate(spreads))
    quotes = MarketCurveQuotes(
        as_of=discount.as_of,
        pillars=PILLARS,
        quotes=tuple(Quote(kind="upfront_pct", value=u, coupon_bp=DISTRESSED_COUPON_BP) for u in upfronts),
        recovery=recovery,
        label=label,
    )
    return quotes, spreads


def arbitrage_levels(discount) -> tuple[tuple[float, ...], str, int]:
    """The distressed levels with the 6M pillar raised in ARB_STEP_BP steps
    until bootstrap() raises; returns the levels, the failing pillar and the
    number of steps taken."""
    for steps in range(1, ARB_MAX_STEPS + 1):
        levels = (DISTRESSED_LEVELS_BP[0] + ARB_STEP_BP * steps, *DISTRESSED_LEVELS_BP[1:])
        try:
            bootstrap(spread_curve("probe", levels, RECOVERY_SUBORDINATED, discount.as_of), discount)
        except BootstrapArbitrageError as err:
            return levels, err.pillar, steps
    raise RuntimeError(f"the distressed curve still fits with the 6M pillar {ARB_STEP_BP * ARB_MAX_STEPS} bp higher")


def main() -> None:
    discount = discount_curve_from_file(RATES_FILE)
    as_of = discount.as_of
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    write_curve_file(
        OUT_DIR / "IG_flat.json",
        spread_curve("IG_flat", IG_LEVELS_BP, RECOVERY_SENIOR, as_of),
        conventional_spread_bp=None,
        source=SOURCE,
        note="Investment-grade shape, par spreads in bp, 40% senior unsecured recovery. " + ILLUSTRATIVE,
    )
    write_curve_file(
        OUT_DIR / "HY_steep.json",
        spread_curve("HY_steep", HY_LEVELS_BP, RECOVERY_HY_INDEX, as_of),
        conventional_spread_bp=None,
        source=SOURCE,
        note="High-yield shape, par spreads in bp, 25% recovery. " + ILLUSTRATIVE,
    )

    distressed, spreads = upfront_curve("distressed_inverted", DISTRESSED_LEVELS_BP, RECOVERY_SUBORDINATED, discount)
    write_curve_file(
        OUT_DIR / "distressed_inverted.json",
        distressed,
        conventional_spread_bp=spreads,
        source=SOURCE,
        note=(
            f"Distressed inverted shape, 20% recovery, quoted as clean upfront in % of notional at a {DISTRESSED_COUPON_BP:.0f} bp coupon. "
            "The upfronts were derived in Section 6 from the indicative spreads in conventional_spread_bp with "
            "cds.pricer.quoted_spread_to_upfront (one flat hazard per pillar, on the pillar's own maturity) on "
            f"{RATES_FILE.name}, so Table 1 can show both. " + ILLUSTRATIVE
        ),
    )

    arb_levels, failing_pillar, steps = arbitrage_levels(discount)
    arb, arb_spreads = upfront_curve("distressed_arb", arb_levels, RECOVERY_SUBORDINATED, discount)
    write_curve_file(
        OUT_DIR / "distressed_arb.json",
        arb,
        conventional_spread_bp=arb_spreads,
        source=SOURCE,
        note=(
            f"The distressed_inverted curve with the 6M pillar raised from {DISTRESSED_LEVELS_BP[0]:.0f} to {arb_levels[0]:.0f} bp "
            f"({steps} steps of {ARB_STEP_BP:.0f} bp), the first level at which the sequential bootstrap needs a negative hazard "
            f"(at the {failing_pillar} pillar; BUILD_PLAN.md Part B item 6). Used only for the arbitrage-detection test and the "
            "fallback demonstration. Quoted and derived exactly as distressed_inverted.json. " + ILLUSTRATIVE
        ),
    )
    for path in sorted(OUT_DIR.glob("*.json")):
        print(path.relative_to(ROOT))


if __name__ == "__main__":
    main()
