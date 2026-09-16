"""Section 2: the SOFR OIS discount curve (BUILD_PLAN.md Section 2, criteria 1 to 5).

The rates snapshot is data/rates/sofr_ois_2026-09-15.json. The tests check
that the bootstrap reprices its inputs, that the interpolation is log-linear
with flat forward extrapolation, that forward() is the DF ratio, and that
the data file carries its provenance fields.
"""

from __future__ import annotations

import json
import math
from datetime import date
from pathlib import Path

import numpy as np
import pytest

from cds.conventions import ACT360_BASIS, ACT365F_BASIS
from cds.curves import (
    DiscountCurve,
    bootstrap_ois,
    discount_curve_from_file,
    ois_payment_dates,
    par_rate_from_curve,
    read_rates_file,
)
from tests.conftest import CURVE_IDENTITY_ABS_TOL, OIS_REPRICE_BP, QL_DISCOUNT_ABS_TOL

RATES_FILE = Path(__file__).resolve().parent.parent / "data" / "rates" / "sofr_ois_2026-09-15.json"
TENORS = ["1M", "3M", "6M", "1Y", "2Y", "3Y", "4Y", "5Y", "7Y", "10Y", "15Y", "20Y", "30Y"]

# Criterion 2: five interior points per node interval.
INTERIOR_POINTS = 5
# Criterion 3: the daily monotonicity grid runs to 60 years, past the 30Y node.
GRID_YEARS = 60
# Criterion 3: extrapolation is checked at these years past the last node.
EXTRAPOLATION_OFFSETS = (0.5, 5.0, 10.0, 30.0)


@pytest.fixture(scope="module")
def rates() -> dict:
    return read_rates_file(RATES_FILE)


@pytest.fixture(scope="module")
def curve() -> DiscountCurve:
    return discount_curve_from_file(RATES_FILE)


# --- criterion 1: repricing ------------------------------------------------


def test_every_input_ois_reprices_to_its_par_rate(curve: DiscountCurve) -> None:
    rows = []
    for tenor, rate in zip(curve.tenors, curve.par_rates_pct):
        implied = par_rate_from_curve(curve, tenor)
        rows.append((tenor, rate, implied, (implied - rate) * 100.0))
    worst = max(abs(r[3]) for r in rows)
    assert worst < OIS_REPRICE_BP, rows


def test_sub_one_year_nodes_are_the_simple_discount_factor(curve: DiscountCurve) -> None:
    """A single-payment OIS gives P = 1 / (1 + K * Delta) directly, Delta act/360 from spot."""
    checked = 0
    for tenor, rate, df in zip(curve.tenors, curve.par_rates_pct, curve.node_dfs):
        if not tenor.endswith("M"):
            continue
        (pay,) = ois_payment_dates(curve.as_of, tenor)
        delta = (pay - curve.as_of).days / ACT360_BASIS
        assert df == pytest.approx(1.0 / (1.0 + rate / 100.0 * delta), abs=CURVE_IDENTITY_ABS_TOL), tenor
        checked += 1
    assert checked == 3


def test_one_year_node_by_hand(curve: DiscountCurve) -> None:
    """The 1Y OIS also pays once, so its node is 1 / (1 + K * Delta) as well."""
    i = curve.tenors.index("1Y")
    (pay,) = ois_payment_dates(curve.as_of, "1Y")
    delta = (pay - curve.as_of).days / ACT360_BASIS
    assert curve.node_dfs[i] == pytest.approx(1.0 / (1.0 + curve.par_rates_pct[i] / 100.0 * delta), abs=CURVE_IDENTITY_ABS_TOL)


def test_two_year_node_by_hand(curve: DiscountCurve) -> None:
    """With P(1Y) known, the 2Y par equation has one unknown:
    K (D1 P1 + D2 P2) = 1 - P2, so P2 = (1 - K D1 P1) / (1 + K D2)."""
    i1, i2 = curve.tenors.index("1Y"), curve.tenors.index("2Y")
    pay1, pay2 = ois_payment_dates(curve.as_of, "2Y")
    k = curve.par_rates_pct[i2] / 100.0
    d1 = (pay1 - curve.as_of).days / ACT360_BASIS
    d2 = (pay2 - pay1).days / ACT360_BASIS
    p1 = curve.node_dfs[i1]
    assert curve.node_dfs[i2] == pytest.approx((1.0 - k * d1 * p1) / (1.0 + k * d2), abs=CURVE_IDENTITY_ABS_TOL)


# --- criterion 2: log-linear between nodes ---------------------------------


def test_log_df_is_linear_between_adjacent_nodes(curve: DiscountCurve) -> None:
    knots = (0.0, *curve.node_times)
    worst = 0.0
    for t0, t1 in zip(knots, knots[1:]):
        ts = np.linspace(t0, t1, INTERIOR_POINTS + 2)
        log_dfs = np.array([math.log(curve.df(t)) for t in ts])
        second = np.diff(log_dfs, n=2)
        worst = max(worst, float(np.max(np.abs(second))))
    assert worst < CURVE_IDENTITY_ABS_TOL


def test_before_first_node_the_forward_is_the_first_zero_rate(curve: DiscountCurve) -> None:
    t1 = curve.node_times[0]
    z1 = -math.log(curve.node_dfs[0]) / t1
    for t in np.linspace(0.0, t1, INTERIOR_POINTS + 2):
        assert curve.df(t) == pytest.approx(math.exp(-z1 * t), abs=CURVE_IDENTITY_ABS_TOL)


# --- criterion 3: extrapolation and monotonicity ---------------------------


def test_forward_beyond_last_node_is_the_last_interval_forward(curve: DiscountCurve) -> None:
    t_last, t_prev = curve.node_times[-1], curve.node_times[-2]
    f_last = curve.forward(t_prev, t_last)
    points = [t_last + off for off in EXTRAPOLATION_OFFSETS]
    for a, b in zip((t_last, *points), points):
        assert abs(curve.forward(a, b) - f_last) < CURVE_IDENTITY_ABS_TOL


def test_df_is_non_increasing_on_a_daily_grid_to_60y(curve: DiscountCurve) -> None:
    ts = np.arange(0, GRID_YEARS * ACT365F_BASIS + 1) / ACT365F_BASIS
    dfs = curve.df(ts)
    assert dfs[0] == 1.0
    assert np.all(np.diff(dfs) <= 0.0)


# --- criterion 4: forward reproduces the DF ratio --------------------------


@pytest.mark.parametrize(
    "t1,t2",
    [(0.0, 0.5), (0.1, 0.2), (1.0, 2.0), (2.5, 7.3), (9.99, 10.01), (10.0, 15.0), (25.0, 45.0), (35.0, 60.0)],
)
def test_forward_reproduces_df_ratio(curve: DiscountCurve, t1: float, t2: float) -> None:
    f = curve.forward(t1, t2)
    assert curve.df(t2) / curve.df(t1) == pytest.approx(math.exp(-f * (t2 - t1)), abs=CURVE_IDENTITY_ABS_TOL)


# --- criterion 5: provenance fields ---------------------------------------


def test_rates_file_has_its_provenance_fields(rates: dict) -> None:
    for key in ("source", "source_url", "snapshot_taken", "note"):
        assert isinstance(rates[key], str) and rates[key].strip(), key
    assert rates["as_of"] == "2026-09-15"
    assert rates["snapshot_taken"] == "2026-09-16"
    assert rates["fixed_frequency"] == "annual"
    assert rates["fixed_day_count"] == "act/360"
    assert rates["tenors"] == TENORS
    assert len(rates["par_rates_pct"]) == len(rates["source_by_tenor"]) == len(TENORS)
    assert all(label.strip() for label in rates["source_by_tenor"])


def test_rates_file_missing_field_raises(tmp_path: Path, rates: dict) -> None:
    bad = dict(rates)
    bad["source_url"] = ""
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ValueError, match="source_url"):
        read_rates_file(path)


# --- construction and dates -------------------------------------------------


def test_payment_dates_roll_following_on_weekends(curve: DiscountCurve) -> None:
    """15 Sep 2029 is a Saturday, so the 3Y node is Mon 17 Sep 2029; the 2Y
    swap's first payment is the 1Y node date."""
    assert ois_payment_dates(curve.as_of, "3Y") == (date(2027, 9, 15), date(2028, 9, 15), date(2029, 9, 17))
    assert ois_payment_dates(curve.as_of, "2Y")[0] == curve.node_dates[curve.tenors.index("1Y")]
    assert ois_payment_dates(curve.as_of, "6M") == (date(2027, 3, 15),)


def test_as_of_and_node_times_are_act365f(curve: DiscountCurve) -> None:
    assert curve.as_of == date(2026, 9, 15)
    assert curve.tenors == tuple(TENORS)
    for d, t in zip(curve.node_dates, curve.node_times):
        assert t == (d - curve.as_of).days / ACT365F_BASIS


def test_negative_time_and_reversed_forward_raise(curve: DiscountCurve) -> None:
    with pytest.raises(ValueError):
        curve.df(-0.1)
    with pytest.raises(ValueError):
        curve.forward(2.0, 1.0)


def test_construction_checks() -> None:
    as_of = date(2026, 9, 15)
    with pytest.raises(ValueError):
        DiscountCurve(as_of=as_of, node_dates=(), node_dfs=())
    with pytest.raises(ValueError):
        DiscountCurve(as_of=as_of, node_dates=(date(2027, 9, 15), date(2027, 3, 15)), node_dfs=(0.9, 0.95))
    with pytest.raises(ValueError):
        DiscountCurve(as_of=as_of, node_dates=(date(2027, 9, 15),), node_dfs=(-0.1,))
    with pytest.raises(ValueError):
        bootstrap_ois(as_of, ["2Y", "1Y"], [4.0, 4.0])
    with pytest.raises(ValueError):
        bootstrap_ois(as_of, ["18M"], [4.0])


def test_month_end_anniversaries_clip_to_the_shorter_month() -> None:
    """A 31 Jan 2027 spot date has its 1M payment on Sun 28 Feb, rolled Following to Mon 1 Mar."""
    (pay,) = ois_payment_dates(date(2027, 1, 31), "1M")
    assert pay == date(2027, 3, 1)


def test_curve_keeps_its_inputs_and_a_bump_lowers_every_df(curve: DiscountCurve, rates: dict) -> None:
    """Section 8's IR01 rebuilds from the stored par rates; +1 bp everywhere lowers every node."""
    assert list(curve.par_rates_pct) == rates["par_rates_pct"]
    bumped = bootstrap_ois(curve.as_of, curve.tenors, [r + 0.01 for r in curve.par_rates_pct])
    assert bumped.node_dates == curve.node_dates
    assert all(b < p for b, p in zip(bumped.node_dfs, curve.node_dfs))


# --- oracle: QuantLib's OIS bootstrap on the same inputs ---------------------


QL_ORACLE_TIMES = 50  # points from 0.01 to 40Y, past the last node
QL_ORACLE_MAX_YEARS = 40.0


def test_matches_quantlib_log_linear_ois_bootstrap(curve: DiscountCurve) -> None:
    """ql.PiecewiseLogLinearDiscount from ql.OISRateHelper(SOFR, annual fixed
    act/360, 0 settlement days, weekend-only calendar) gives the same nodes
    and the same interpolation, including the flat extrapolation past 30Y."""
    import QuantLib as ql

    as_of = ql.Date(curve.as_of.day, curve.as_of.month, curve.as_of.year)
    ql.Settings.instance().evaluationDate = as_of
    helpers = [
        ql.OISRateHelper(
            0,
            ql.Period(tenor),
            ql.QuoteHandle(ql.SimpleQuote(rate / 100.0)),
            ql.Sofr(),
            ql.YieldTermStructureHandle(),
            False,
            0,
            ql.Following,
            ql.Annual,
            ql.WeekendsOnly(),
        )
        for tenor, rate in zip(curve.tenors, curve.par_rates_pct)
    ]
    oracle = ql.PiecewiseLogLinearDiscount(as_of, helpers, ql.Actual365Fixed())
    oracle.enableExtrapolation()

    for helper, d, p in zip(helpers, curve.node_dates, curve.node_dfs):
        assert helper.pillarDate().ISO() == d.isoformat()
        assert abs(oracle.discount(helper.pillarDate()) - p) < QL_DISCOUNT_ABS_TOL
    for t in np.linspace(0.01, QL_ORACLE_MAX_YEARS, QL_ORACLE_TIMES):
        assert abs(oracle.discount(float(t)) - curve.df(float(t))) < QL_DISCOUNT_ABS_TOL
