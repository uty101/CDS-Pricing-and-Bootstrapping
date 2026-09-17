"""Section 6: the sequential bootstrap, arbitrage detection, the fallbacks,
the committed curve files and the first outputs (BUILD_PLAN.md Section 6,
criteria 1 to 6).

The discount curve is the Section 2 snapshot; the curves are the committed
files in data/curves/ plus an in-test flat 100 bp curve. Every pillar hazard
is checked by repricing the pillar's contract with price() and comparing its
par spread (the clean-value spread, docs/CONVENTIONS_RESOLVED.md item 24)
with the conventional spread the bootstrap was given.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import matplotlib.image
import pandas as pd
import pytest

from cds import report
from cds.bootstrap import (
    FALLBACKS,
    BootstrapArbitrageError,
    bootstrap,
    conventional_spreads_bp,
    market_curve_quotes_from_file,
    market_state,
    pillar_trade,
    read_curve_file,
)
from cds.conventions import PILLARS, RECOVERY_SENIOR, STANDARD_COUPONS_BP
from cds.curves import DiscountCurve, RecoveryCurve, discount_curve_from_file
from cds.pricer import price, quoted_spread_to_upfront, upfront_to_quoted_spread
from cds.textbook import implied_hazard
from cds.types import MarketCurveQuotes, MarketState, Quote
from tests.conftest import (
    BOOTSTRAP_REPRICE_BP,
    CONVERSION_ROUNDTRIP_BP,
    FLAT_HAZARD_REL_TOL,
    PRICER_IDENTITY_ABS_TOL,
    UPFRONT_CURVE_VS_FLAT_BP,
    UPFRONT_CURVE_VS_FLAT_HY_MIN_BP,
    assert_output_current,
)
from tests.test_legs import RATES_FILE

ROOT = Path(__file__).resolve().parent.parent
CURVES_DIR = ROOT / "data" / "curves"
CURVE_FILES = ("IG_flat", "HY_steep", "distressed_inverted", "distressed_arb")
NAMED_CURVES = CURVE_FILES[:3]

BP_PER_UNIT = 1e4
PERCENT = 100.0

# Criterion 2: the in-test flat curve and the credit-triangle hazard it
# should give, s / (1 - R) = 100 bp / 0.6.
FLAT_SPREAD_BP = 100.0
FLAT_TRIANGLE_HAZARD = implied_hazard(FLAT_SPREAD_BP, RECOVERY_SENIOR)

# Criterion 4: the pillar at which distressed_arb needs a negative hazard,
# pinned with its f(0) in review 06 (the 6M pillar at 6000 bp, seven 500 bp
# steps above the distressed curve's 2500).
ARB_PILLAR = "1Y"
ARB_PILLAR_INDEX = 1
ARB_6M_SPREAD_BP = 6000.0
ARB_1Y_SPREAD_BP = 2200.0

# Criterion 3 (docs/CONVENTIONS_RESOLVED.md item 30): the HY curve's hazards
# rise strictly through this many pillars (6M to 5Y); the 7Y and 10Y forward
# hazards sit below the 5Y one, which is what a spread curve that flattens
# from 500 to 560 to 600 bp implies, and the test pins them.
HY_STRICTLY_INCREASING_THROUGH = 6


@pytest.fixture(scope="module")
def discount() -> DiscountCurve:
    return discount_curve_from_file(RATES_FILE)


@pytest.fixture(scope="module")
def curves() -> dict[str, MarketCurveQuotes]:
    return {label: market_curve_quotes_from_file(CURVES_DIR / f"{label}.json") for label in CURVE_FILES}


@pytest.fixture(scope="module")
def results(discount: DiscountCurve, curves: dict[str, MarketCurveQuotes]) -> dict:
    return {label: bootstrap(curves[label], discount) for label in NAMED_CURVES}


def _spread_curve(discount: DiscountCurve, levels, recovery: float = RECOVERY_SENIOR, label: str = "test") -> MarketCurveQuotes:
    return MarketCurveQuotes(
        as_of=discount.as_of,
        pillars=PILLARS[: len(levels)],
        quotes=tuple(Quote(kind="par_spread_bp", value=float(v)) for v in levels),
        recovery=recovery,
        label=label,
    )


def _flat_curve(discount: DiscountCurve) -> MarketCurveQuotes:
    return _spread_curve(discount, (FLAT_SPREAD_BP,) * len(PILLARS), label="flat100")


# --- criterion 1: every pillar reprices ------------------------------------


@pytest.mark.parametrize("label", NAMED_CURVES)
def test_each_pillar_reprices_its_conventional_spread(discount: DiscountCurve, results: dict, label: str) -> None:
    r = results[label]
    assert r.method == "bootstrap"
    state = market_state(r, discount)
    for i in range(len(PILLARS)):
        s_i = r.conventional_spreads_bp[i]
        repriced = price(state, pillar_trade(r.quotes, i, s_i)).par_spread_bp
        assert abs(repriced - s_i) < BOOTSTRAP_REPRICE_BP, (label, PILLARS[i])
        assert r.f_at_zero[i] < 0.0
        assert r.pillar_hazards[i] > 0.0
    assert r.survival.pillar_hazards == r.pillar_hazards
    assert r.survival.pillar_dates == r.pillar_dates


def test_earlier_pillars_are_fixed_by_the_shorter_curve(discount: DiscountCurve, curves: dict[str, MarketCurveQuotes]) -> None:
    """Sequential: nothing beyond t_i enters pillar i, so bootstrapping the
    first four pillars alone gives the same four hazards as the full curve."""
    full = bootstrap(curves["HY_steep"], discount)
    short = replace(curves["HY_steep"], pillars=PILLARS[:4], quotes=curves["HY_steep"].quotes[:4])
    part = bootstrap(short, discount)
    assert part.pillar_hazards == full.pillar_hazards[:4]


# --- criterion 2: flat 100 bp ------------------------------------------------


def test_flat_100bp_curve_gives_a_flat_hazard_near_the_credit_triangle(discount: DiscountCurve) -> None:
    r = bootstrap(_flat_curve(discount), discount)
    for i, hazard in enumerate(r.pillar_hazards):
        assert abs(hazard / FLAT_TRIANGLE_HAZARD - 1.0) < FLAT_HAZARD_REL_TOL, PILLARS[i]
    assert max(r.pillar_hazards) - min(r.pillar_hazards) < FLAT_HAZARD_REL_TOL * FLAT_TRIANGLE_HAZARD


# --- criterion 3: IG and HY shapes -------------------------------------------


def test_ig_and_hy_hazards_are_positive_and_hy_rises_through_5y(results: dict) -> None:
    ig, hy = results["IG_flat"].pillar_hazards, results["HY_steep"].pillar_hazards
    assert all(h > 0.0 for h in ig) and all(h > 0.0 for h in hy)
    front = hy[:HY_STRICTLY_INCREASING_THROUGH]
    assert all(a < b for a, b in zip(front, front[1:]))
    assert all(a < b for a, b in zip(ig, ig[1:]))  # IG happens to rise on every pillar too
    # Item 30: the 7Y and 10Y forward hazards sit below the 5Y one on the
    # 500 / 560 / 600 long end; the dip is pinned so it cannot change silently.
    assert hy[6] < hy[5] and hy[7] < hy[6]


# --- criterion 4: the distressed curve, the arbitrage curve, the fallbacks ---


def test_distressed_curve_fits_with_positive_hazards(results: dict) -> None:
    r = results["distressed_inverted"]
    assert r.method == "bootstrap"
    assert all(h > 0.0 for h in r.pillar_hazards)
    assert r.pillar_hazards[0] > r.pillar_hazards[1] > r.pillar_hazards[2]  # inverted front end


def test_distressed_arb_raises_at_the_pinned_pillar(discount: DiscountCurve, curves: dict[str, MarketCurveQuotes]) -> None:
    arb = curves["distressed_arb"]
    assert conventional_spreads_bp(arb, discount)[0] == pytest.approx(ARB_6M_SPREAD_BP, abs=CONVERSION_ROUNDTRIP_BP)
    with pytest.raises(BootstrapArbitrageError) as info:
        bootstrap(arb, discount)
    err = info.value
    assert err.pillar == ARB_PILLAR and err.index == ARB_PILLAR_INDEX
    assert err.spread_bp == pytest.approx(ARB_1Y_SPREAD_BP, abs=CONVERSION_ROUNDTRIP_BP)
    assert err.f_at_zero > 0.0
    for name in FALLBACKS:
        assert name in str(err)
    assert isinstance(err, ValueError)


def test_flat_from_shortest_fallback_reprices_the_6m_pillar(discount: DiscountCurve, curves: dict[str, MarketCurveQuotes]) -> None:
    r = bootstrap(curves["distressed_arb"], discount, fallback="flat_from_shortest")
    assert r.method == "flat_from_shortest"
    assert r.arbitrage_pillar == ARB_PILLAR
    assert len(set(r.pillar_hazards)) == 1
    assert r.f_at_zero[ARB_PILLAR_INDEX] > 0.0 and all(f is None for f in r.f_at_zero[ARB_PILLAR_INDEX + 1 :])
    state = market_state(r, discount)
    s_6m = r.conventional_spreads_bp[0]
    assert abs(price(state, pillar_trade(r.quotes, 0, s_6m)).par_spread_bp - s_6m) < BOOTSTRAP_REPRICE_BP
    # One hazard cannot reprice the rest of an inverted curve: the 1Y is far off.
    s_1y = r.conventional_spreads_bp[1]
    assert abs(price(state, pillar_trade(r.quotes, 1, s_1y)).par_spread_bp - s_1y) > BOOTSTRAP_REPRICE_BP


def test_upfront_fallback_reprices_each_pillar_off_its_own_flat_hazard(discount: DiscountCurve, curves: dict[str, MarketCurveQuotes]) -> None:
    r = bootstrap(curves["distressed_arb"], discount, fallback="upfront")
    assert r.method == "upfront"
    assert r.survival is None
    with pytest.raises(ValueError):
        market_state(r, discount)
    for i in range(len(PILLARS)):
        survival = r.survival_for_pillar(i)
        assert survival.pillar_dates == (r.pillar_dates[i],) and survival.pillar_hazards == (r.pillar_hazards[i],)
        state = MarketState(as_of=discount.as_of, discount=discount, survival=survival, recovery=RecoveryCurve.flat(r.quotes.recovery, discount.as_of), quotes=r.quotes)
        s_i = r.conventional_spreads_bp[i]
        assert abs(price(state, pillar_trade(r.quotes, i, s_i)).par_spread_bp - s_i) < BOOTSTRAP_REPRICE_BP, PILLARS[i]


@pytest.mark.parametrize("fallback", FALLBACKS)
def test_a_curve_that_fits_ignores_the_fallback(discount: DiscountCurve, curves: dict[str, MarketCurveQuotes], results: dict, fallback: str) -> None:
    r = bootstrap(curves["IG_flat"], discount, fallback=fallback)
    assert r.method == "bootstrap"
    assert r.pillar_hazards == results["IG_flat"].pillar_hazards
    assert r.arbitrage_pillar is None


def test_bootstrap_rejects_bad_inputs(discount: DiscountCurve, curves: dict[str, MarketCurveQuotes]) -> None:
    ig = curves["IG_flat"]
    with pytest.raises(ValueError):
        bootstrap(ig, discount, fallback="something_else")
    with pytest.raises(ValueError):
        bootstrap(replace(ig, as_of=ig.as_of + timedelta(days=1)), discount)
    mixed = replace(ig, quotes=(*ig.quotes[:-1], Quote(kind="upfront_pct", value=1.0, coupon_bp=100.0)))
    with pytest.raises(ValueError):
        bootstrap(mixed, discount)
    with pytest.raises(ValueError):
        bootstrap(replace(ig, quotes=tuple(Quote(kind="upfront_pct", value=1.0) for _ in ig.quotes)), discount)
    with pytest.raises(ValueError):
        bootstrap(replace(ig, pillars=("1Y", "6M", *PILLARS[2:])), discount)
    with pytest.raises(ValueError):
        bootstrap(replace(ig, pillars=("6M", "6M", *PILLARS[2:])), discount)


# --- criterion 5: the upfront-quoted round trip -------------------------------


def test_distressed_upfronts_round_trip_to_the_stored_spreads(discount: DiscountCurve, curves: dict[str, MarketCurveQuotes]) -> None:
    """The file's upfronts are quoted_spread_to_upfront of its stored
    spreads; converting back reproduces the spreads to 1e-6 bp."""
    for label in ("distressed_inverted", "distressed_arb"):
        data = read_curve_file(CURVES_DIR / f"{label}.json")
        quotes = curves[label]
        stored = tuple(float(s) for s in data["conventional_spread_bp"])
        for i, (q, s) in enumerate(zip(quotes.quotes, stored)):
            trade = pillar_trade(quotes, i, q.coupon_bp)
            assert abs(quoted_spread_to_upfront(discount, trade, s) - q.value) < PRICER_IDENTITY_ABS_TOL, (label, PILLARS[i])
            assert abs(upfront_to_quoted_spread(discount, trade, q.value) - s) < CONVERSION_ROUNDTRIP_BP, (label, PILLARS[i])
        assert max(abs(a - b) for a, b in zip(conventional_spreads_bp(quotes, discount), stored)) < CONVERSION_ROUNDTRIP_BP


# --- criterion 6: full-curve upfront against the flat-hazard conversion -------


def test_5y_upfront_from_the_curve_and_from_the_flat_conversion(discount: DiscountCurve, results: dict) -> None:
    """On a flat curve the single-hazard conversion is the curve, so the two
    5Y upfronts agree at both standard coupons (at coupon 100 both are zero
    by construction, the quote being 100 bp; coupon 500 is the real check).
    On HY the 5Y quote at coupon 100 differs by tens of bp of notional."""
    i_5y = PILLARS.index("5Y")
    flat = bootstrap(_flat_curve(discount), discount)
    for coupon_bp in STANDARD_COUPONS_BP:
        trade = pillar_trade(flat.quotes, i_5y, coupon_bp)
        from_curve = price(market_state(flat, discount), trade).clean_upfront_pct
        from_flat = quoted_spread_to_upfront(discount, trade, flat.conventional_spreads_bp[i_5y])
        assert abs(from_curve - from_flat) < UPFRONT_CURVE_VS_FLAT_BP / BP_PER_UNIT * PERCENT, coupon_bp

    hy = results["HY_steep"]
    trade = pillar_trade(hy.quotes, i_5y, STANDARD_COUPONS_BP[0])
    from_curve = price(market_state(hy, discount), trade).clean_upfront_pct
    from_flat = quoted_spread_to_upfront(discount, trade, hy.conventional_spreads_bp[i_5y])
    assert abs(from_curve - from_flat) > UPFRONT_CURVE_VS_FLAT_HY_MIN_BP / BP_PER_UNIT * PERCENT


# --- the committed curve files ------------------------------------------------


@pytest.mark.parametrize("label", CURVE_FILES)
def test_curve_files_are_illustrative_and_dated_to_the_snapshot(discount: DiscountCurve, label: str) -> None:
    data = read_curve_file(CURVES_DIR / f"{label}.json")
    assert data["source"] == "illustrative"
    assert "not an observation" in data["note"]
    assert data["label"] == label
    quotes = market_curve_quotes_from_file(CURVES_DIR / f"{label}.json")
    assert quotes.as_of == discount.as_of
    assert quotes.pillars == PILLARS
    assert len({q.kind for q in quotes.quotes}) == 1


def test_curve_file_levels_are_the_data_note_levels(curves: dict[str, MarketCurveQuotes]) -> None:
    assert tuple(q.value for q in curves["IG_flat"].quotes) == (45, 50, 60, 70, 80, 90, 105, 120)
    assert tuple(q.value for q in curves["HY_steep"].quotes) == (150, 200, 300, 380, 440, 500, 560, 600)
    assert curves["IG_flat"].recovery == 0.40 and curves["HY_steep"].recovery == 0.25 and curves["distressed_inverted"].recovery == 0.20
    distressed = read_curve_file(CURVES_DIR / "distressed_inverted.json")
    assert tuple(distressed["conventional_spread_bp"]) == (2500, 2200, 1800, 1500, 1350, 1200, 1050, 950)
    assert distressed["coupon_bp"] == 500.0
    arb = read_curve_file(CURVES_DIR / "distressed_arb.json")
    assert tuple(arb["conventional_spread_bp"]) == (ARB_6M_SPREAD_BP, 2200, 1800, 1500, 1350, 1200, 1050, 950)
    assert arb["quotes"][1:] == distressed["quotes"][1:]


def test_read_curve_file_rejects_broken_files(tmp_path: Path) -> None:
    good = read_curve_file(CURVES_DIR / "distressed_inverted.json")

    def write(changes: dict) -> Path:
        data = {**good, **changes}
        path = tmp_path / "curve.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    for changes in (
        {"note": ""},
        {"source": ""},
        {"coupon_bp": None},
        {"conventional_spread_bp": None},
        {"quote_kind": "par_spread_bp"},  # spread-quoted but carries conventional spreads
        {"quote_kind": "points"},
        {"pillars": good["pillars"][:-1]},
    ):
        with pytest.raises(ValueError):
            read_curve_file(write(changes))
    data = {k: v for k, v in good.items() if k != "recovery"}
    path = tmp_path / "missing.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError):
        read_curve_file(path)


# --- Table 1 and Chart 1 ------------------------------------------------------


def test_table_1_is_current_and_has_the_fixed_columns(discount: DiscountCurve, curves: dict[str, MarketCurveQuotes], tmp_path: Path) -> None:
    fresh = report.table_1_hazard_curves([bootstrap(curves[k], discount, fallback="upfront") for k in CURVE_FILES], out_dir=tmp_path)
    assert tuple(fresh.columns) == report.TABLE_1_COLUMNS
    assert len(fresh) == len(CURVE_FILES) * len(PILLARS)
    committed = report.TABLES_DIR / "table_1_hazard_curves.csv"
    assert_output_current(tmp_path / "table_1_hazard_curves.csv", committed)
    # The Markdown is rendered from the rounded frame at fewer decimals, so
    # the two renderings agree as text once the CSVs agree numerically.
    assert (tmp_path / "table_1_hazard_curves.md").read_text(encoding="utf-8") == committed.with_suffix(".md").read_text(encoding="utf-8")
    table = pd.read_csv(committed)
    assert set(table["method"]) == {"bootstrap", "upfront"}
    assert set(table.loc[table["curve"] == "distressed_arb", "method"]) == {"upfront"}
    assert (table["cum_default_prob"] + table["survival_prob"] - 1.0).abs().max() < PRICER_IDENTITY_ABS_TOL


def test_chart_1_is_current_and_1600_by_900(discount: DiscountCurve, results: dict, tmp_path: Path) -> None:
    fresh = report.chart_1_survival_hazard([results[k] for k in NAMED_CURVES], out_dir=tmp_path)
    assert tuple(fresh.columns) == report.CHART_1_COLUMNS
    assert len(fresh) == len(NAMED_CURVES) * (10 * 12 + 1)
    committed = report.CHARTS_DIR / "chart_1_survival_hazard.csv"
    assert_output_current(tmp_path / "chart_1_survival_hazard.csv", committed)
    image = matplotlib.image.imread(report.CHARTS_DIR / "chart_1_survival_hazard.png")
    assert image.shape[:2] == (900, 1600)
    ig = fresh[fresh["curve"] == "IG_flat"]
    assert ig["survival_prob"].iloc[0] == 1.0 and ig["survival_prob"].is_monotonic_decreasing
    assert (ig["hazard_pct"] > 0).all()


def test_chart_1_refuses_a_curve_without_a_joint_hazard_curve(discount: DiscountCurve, curves: dict[str, MarketCurveQuotes], tmp_path: Path) -> None:
    r = bootstrap(curves["distressed_arb"], discount, fallback="upfront")
    with pytest.raises(ValueError):
        report.chart_1_survival_hazard([r], out_dir=tmp_path)
