"""The survival curve bootstrapped from CDS quotes (BUILD_PLAN.md Section 6).

Symbols follow docs/SPEC.md section 6. A curve has pillars i = 1..n with
standard maturities t_i from the valuation date as_of, one quote per pillar
(all par spreads, or all upfronts at one stated coupon), and a recovery R.
Each pillar's quote is first turned into a conventional spread s_i: the
quote itself for a par_spread_bp curve, or upfront_to_quoted_spread (the
flat-hazard conversion of cds.pricer, on the pillar's own maturity) for an
upfront_pct curve.

Sequential bootstrap (Part A.4, SPEC 6.5). Hazards are solved one pillar at
a time, shortest first, earlier pillars held fixed. For pillar i the unknown
is lambda_i on (t_{i-1}, t_i] and the objective is the clean value, per unit
notional at the cash settlement date, of a protection-buyer contract from
as_of to t_i paying coupon s_i (docs/CONVENTIONS_RESOLVED.md item 24):

    f(lambda_i) = D * (PV_prot(lambda_1..lambda_i) - s_i * A(lambda_1..lambda_i))
                  + s_i * accrued_fraction

with D = 1 / P(t_settle) and accrued_fraction = accrued_days / 360 as in
cds.pricer, so that f = 0 exactly when the contract's par spread (the
clean-value spread, QuantLib's fairSpread) equals s_i. Nothing beyond t_i
enters f, so later pillars cannot change earlier hazards. The root is found
with scipy's brentq on HAZARD_BOUNDS = [0, 5] to xtol 1e-12.

Arbitrage detection. f is increasing in lambda_i. Before Brent, f(0) is
evaluated: f(0) < 0 means that with no default risk on the new interval the
protection leg is still worth less than s_i buys, so a positive lambda_i is
needed and Brent proceeds; f(0) >= 0 means the earlier pillars already
deliver at least as much protection as s_i pays for, the root would be at
or below zero, and BootstrapArbitrageError(pillar, spread_bp, f_at_zero) is
raised unless a fallback is named. The fallbacks replace the joint curve:

    "flat_from_shortest"  one flat hazard fitted to the shortest pillar
                          (implied_flat_hazard), used on every pillar;
    "upfront"             each pillar priced off its own flat hazard, as an
                          upfront-quoted market does, with no joint curve.

A fallback is used only when the sequential fit raises; a curve that fits
returns method "bootstrap" whatever fallback was named.

Curve files (Part D.3) are read by market_curve_quotes_from_file; every file
carries source and note fields saying the levels are illustrative.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal

from scipy.optimize import brentq

from cds.conventions import DEFAULT_CALENDAR, PILLARS
from cds.curves import RecoveryCurve, SurvivalCurve
from cds.legs import Engine
from cds.pricer import HAZARD_BOUNDS, HAZARD_XTOL, implied_flat_hazard, upfront_to_quoted_spread, value
from cds.schedule import standard_maturity
from cds.types import CDSTrade, DiscountCurve, MarketCurveQuotes, MarketState, Quote

__all__ = [
    "FALLBACKS",
    "BootstrapArbitrageError",
    "HazardCapError",
    "BootstrapResult",
    "Fallback",
    "Method",
    "bootstrap",
    "conventional_spreads_bp",
    "market_curve_quotes_from_file",
    "market_state",
    "pillar_trade",
    "read_curve_file",
    "write_curve_file",
]

Fallback = Literal["flat_from_shortest", "upfront"]
FALLBACKS = ("flat_from_shortest", "upfront")
Method = Literal["bootstrap", "flat_from_shortest", "upfront"]

CURVE_FILE_KEYS = (
    "label",
    "as_of",
    "recovery",
    "quote_kind",
    "coupon_bp",
    "pillars",
    "quotes",
    "conventional_spread_bp",
    "source",
    "note",
)


class HazardCapError(ValueError):
    """Raised at the first pillar whose conventional spread is above what the
    largest hazard the solver brackets (HAZARD_BOUNDS[1], 500% a year)
    reaches: the objective is still negative at the cap, so there is no
    root in the bracket. pillar is the label ("10Y"), index its 0-based
    position, spread_bp the conventional spread, cap the hazard bound."""

    def __init__(self, pillar: str, spread_bp: float, cap: float, index: int) -> None:
        self.pillar = pillar
        self.spread_bp = spread_bp
        self.cap = cap
        self.index = index
        super().__init__(f"pillar {pillar} at {spread_bp:.4f} bp is above what a hazard of {cap} reaches")


class BootstrapArbitrageError(ValueError):
    """Raised at the first pillar whose conventional spread cannot be fitted
    with a non-negative hazard. pillar is the label ("2Y"), index its 0-based
    position, spread_bp the conventional spread, f_at_zero the objective at
    lambda_i = 0 (per unit notional, positive here)."""

    def __init__(self, pillar: str, spread_bp: float, f_at_zero: float, index: int) -> None:
        self.pillar = pillar
        self.spread_bp = spread_bp
        self.f_at_zero = f_at_zero
        self.index = index
        super().__init__(
            f"pillar {pillar} at {spread_bp:.4f} bp needs a negative hazard: the clean value at lambda = 0 is "
            f"{f_at_zero:+.6e} per unit notional, so the earlier pillars already deliver more protection than "
            f"the spread pays for. Fallbacks: bootstrap(..., fallback='flat_from_shortest') fits one flat hazard "
            f"to the shortest pillar; fallback='upfront' prices each pillar off its own flat hazard."
        )


@dataclass(frozen=True)
class BootstrapResult:
    """What bootstrap() returns.

    survival is the joint curve on the pillars (method "bootstrap" or
    "flat_from_shortest") and None for the "upfront" fallback, which has no
    joint curve; survival_for_pillar(i) is the curve pillar i is priced on
    in every case. pillar_hazards is what Table 1 shows: lambda_i of the
    joint curve, the single flat hazard repeated, or the pillar's own flat
    hazard. f_at_zero holds f(0) for each pillar the sequential fit reached
    (None after the failing one); arbitrage_pillar names the failing pillar
    when a fallback was used.
    """

    quotes: MarketCurveQuotes
    pillar_dates: tuple[date, ...]
    conventional_spreads_bp: tuple[float, ...]
    method: Method
    pillar_hazards: tuple[float, ...]
    survival: SurvivalCurve | None
    f_at_zero: tuple[float | None, ...]
    arbitrage_pillar: str | None = None

    def survival_for_pillar(self, i: int) -> SurvivalCurve:
        if self.survival is not None:
            return self.survival
        return SurvivalCurve(as_of=self.quotes.as_of, pillar_dates=(self.pillar_dates[i],), pillar_hazards=(self.pillar_hazards[i],))


def _check_quotes(quotes: MarketCurveQuotes) -> None:
    """One kind per curve, coupon on upfront quotes, pillars known and in
    order (docs/CONVENTIONS_RESOLVED.md item 12)."""
    if not quotes.pillars:
        raise ValueError("a curve needs at least one pillar")
    if len(quotes.pillars) != len(quotes.quotes):
        raise ValueError("pillars and quotes differ in length")
    unknown = [p for p in quotes.pillars if p not in PILLARS]
    if unknown:
        raise ValueError(f"unknown pillars {unknown}; expected from {PILLARS}")
    order = [PILLARS.index(p) for p in quotes.pillars]
    if order != sorted(set(order)):
        raise ValueError(f"pillars {quotes.pillars} are not in increasing order without repeats")
    kinds = {q.kind for q in quotes.quotes}
    if len(kinds) != 1:
        raise ValueError(f"a curve's quotes must be of one kind, got {sorted(kinds)}")
    kind = kinds.pop()
    if kind == "upfront_pct":
        coupons = {q.coupon_bp for q in quotes.quotes}
        if None in coupons or len(coupons) != 1:
            raise ValueError("upfront_pct quotes need one coupon_bp shared by every pillar")
    elif kind != "par_spread_bp":
        raise ValueError(f"unknown quote kind {kind!r}")
    if not (0.0 <= quotes.recovery <= 1.0):
        raise ValueError(f"recovery {quotes.recovery!r} is not in [0, 1]")


def pillar_trade(quotes: MarketCurveQuotes, i: int, coupon_bp: float, maturity: date | None = None) -> CDSTrade:
    """A protection-buyer contract from as_of to pillar i at the given coupon,
    with the curve's recovery: what the objective and the conversions price."""
    if maturity is None:
        maturity = standard_maturity(quotes.as_of, quotes.pillars[i])
    return CDSTrade(trade_date=quotes.as_of, maturity=maturity, coupon_bp=coupon_bp, side="buy", recovery=quotes.recovery)


def conventional_spreads_bp(quotes: MarketCurveQuotes, discount: DiscountCurve, **kwargs) -> tuple[float, ...]:
    """s_i per pillar: the quote for par_spread_bp curves, the flat-hazard
    conversion of the upfront at the stated coupon otherwise."""
    _check_quotes(quotes)
    out = []
    for i, q in enumerate(quotes.quotes):
        if q.kind == "par_spread_bp":
            out.append(float(q.value))
        else:
            out.append(upfront_to_quoted_spread(discount, pillar_trade(quotes, i, q.coupon_bp), q.value, **kwargs))
    return tuple(out)


def _sequential(
    quotes: MarketCurveQuotes,
    discount: DiscountCurve,
    pillar_dates: tuple[date, ...],
    spreads: tuple[float, ...],
    f_at_zero: list[float],
    kwargs: dict,
) -> list[float]:
    """The sequential fit: the hazards, one per pillar. f(0) of every pillar
    reached is appended to f_at_zero, which the caller owns, so the values
    survive the BootstrapArbitrageError raised at the first pillar with
    f(0) >= 0."""
    as_of = quotes.as_of
    recovery = RecoveryCurve.flat(quotes.recovery, as_of)
    lo, hi = HAZARD_BOUNDS
    hazards: list[float] = []
    for i, (pillar, s_i) in enumerate(zip(quotes.pillars, spreads)):
        trade = pillar_trade(quotes, i, s_i, pillar_dates[i])
        dates = pillar_dates[: i + 1]

        def objective(hazard: float) -> float:
            survival = SurvivalCurve(as_of=as_of, pillar_dates=dates, pillar_hazards=(*hazards, hazard))
            return value(discount, survival, recovery, trade, as_of, **kwargs).clean_upfront

        f0 = objective(lo)
        f_at_zero.append(f0)
        if f0 >= 0.0:
            raise BootstrapArbitrageError(pillar, s_i, f0, i)
        if objective(hi) < 0.0:
            raise HazardCapError(pillar, s_i, hi, i)
        hazards.append(float(brentq(objective, lo, hi, xtol=HAZARD_XTOL)))
    return hazards


def bootstrap(
    quotes: MarketCurveQuotes,
    discount: DiscountCurve,
    fallback: Fallback | None = None,
    *,
    calendar: str = DEFAULT_CALENDAR,
    engine: Engine = "isda",
    half_day_bias: bool = True,
) -> BootstrapResult:
    """The survival curve that reprices every pillar's conventional spread
    (see the module docstring). Raises BootstrapArbitrageError when a pillar
    needs a negative hazard and no fallback is named."""
    if fallback is not None and fallback not in FALLBACKS:
        raise ValueError(f"unknown fallback {fallback!r}; expected one of {FALLBACKS} or None")
    if quotes.as_of != discount.as_of:
        raise ValueError(f"quotes as_of {quotes.as_of} differs from the discount curve's {discount.as_of}")
    kwargs = {"calendar": calendar, "engine": engine, "half_day_bias": half_day_bias}
    spreads = conventional_spreads_bp(quotes, discount, **kwargs)
    pillar_dates = tuple(standard_maturity(quotes.as_of, p) for p in quotes.pillars)
    n = len(pillar_dates)

    f_at_zero: list[float] = []
    try:
        hazards = _sequential(quotes, discount, pillar_dates, spreads, f_at_zero, kwargs)
    except BootstrapArbitrageError as err:
        if fallback is None:
            raise
        reached: tuple[float | None, ...] = (*f_at_zero, *([None] * (n - len(f_at_zero))))
        if fallback == "flat_from_shortest":
            flat = implied_flat_hazard(discount, pillar_trade(quotes, 0, spreads[0], pillar_dates[0]), spreads[0], **kwargs)
            return BootstrapResult(
                quotes=quotes,
                pillar_dates=pillar_dates,
                conventional_spreads_bp=spreads,
                method="flat_from_shortest",
                pillar_hazards=(flat,) * n,
                survival=SurvivalCurve(as_of=quotes.as_of, pillar_dates=pillar_dates, pillar_hazards=(flat,) * n),
                f_at_zero=reached,
                arbitrage_pillar=err.pillar,
            )
        per_pillar = tuple(
            implied_flat_hazard(discount, pillar_trade(quotes, i, s_i, pillar_dates[i]), s_i, **kwargs) for i, s_i in enumerate(spreads)
        )
        return BootstrapResult(
            quotes=quotes,
            pillar_dates=pillar_dates,
            conventional_spreads_bp=spreads,
            method="upfront",
            pillar_hazards=per_pillar,
            survival=None,
            f_at_zero=reached,
            arbitrage_pillar=err.pillar,
        )

    return BootstrapResult(
        quotes=quotes,
        pillar_dates=pillar_dates,
        conventional_spreads_bp=spreads,
        method="bootstrap",
        pillar_hazards=tuple(hazards),
        survival=SurvivalCurve(as_of=quotes.as_of, pillar_dates=pillar_dates, pillar_hazards=tuple(hazards)),
        f_at_zero=tuple(f_at_zero),
    )


def market_state(result: BootstrapResult, discount: DiscountCurve) -> MarketState:
    """The MarketState price() and the later sections take, from a result
    that has a joint curve."""
    if result.survival is None:
        raise ValueError("the 'upfront' fallback has no joint survival curve, so there is no MarketState to build")
    as_of = result.quotes.as_of
    return MarketState(
        as_of=as_of,
        discount=discount,
        survival=result.survival,
        recovery=RecoveryCurve.flat(result.quotes.recovery, as_of),
        quotes=result.quotes,
    )


def read_curve_file(path: str | Path) -> dict:
    """The curve file as written in BUILD_PLAN.md Part D.3, checked for its
    keys, its source and note, and one quote kind."""
    with Path(path).open(encoding="utf-8") as fh:
        data = json.load(fh)
    missing = [k for k in CURVE_FILE_KEYS if k not in data]
    if missing:
        raise ValueError(f"curve file {path} is missing {missing}")
    for key in ("label", "as_of", "source", "note"):
        if not data[key]:
            raise ValueError(f"curve file {path} has an empty {key!r}")
    if data["quote_kind"] not in ("par_spread_bp", "upfront_pct"):
        raise ValueError(f"curve file {path} has quote_kind {data['quote_kind']!r}")
    if data["quote_kind"] == "upfront_pct":
        if data["coupon_bp"] is None:
            raise ValueError(f"curve file {path} is upfront-quoted without a coupon_bp")
        if not data["conventional_spread_bp"] or len(data["conventional_spread_bp"]) != len(data["quotes"]):
            raise ValueError(f"curve file {path} is upfront-quoted without one conventional_spread_bp per pillar")
    elif data["conventional_spread_bp"] is not None:
        raise ValueError(f"curve file {path} is spread-quoted but carries conventional_spread_bp")
    if len(data["pillars"]) != len(data["quotes"]):
        raise ValueError(f"curve file {path} has {len(data['pillars'])} pillars and {len(data['quotes'])} quotes")
    return data


def market_curve_quotes_from_file(path: str | Path) -> MarketCurveQuotes:
    data = read_curve_file(path)
    coupon = data["coupon_bp"]
    return MarketCurveQuotes(
        as_of=date.fromisoformat(data["as_of"]),
        pillars=tuple(data["pillars"]),
        quotes=tuple(Quote(kind=data["quote_kind"], value=float(v), coupon_bp=None if coupon is None else float(coupon)) for v in data["quotes"]),
        recovery=float(data["recovery"]),
        label=data["label"],
    )


def write_curve_file(
    path: str | Path,
    quotes: MarketCurveQuotes,
    *,
    conventional_spread_bp: tuple[float, ...] | None,
    source: str,
    note: str,
) -> None:
    """Write a MarketCurveQuotes in the Part D.3 format. Spread-quoted
    curves store conventional_spread_bp as null."""
    _check_quotes(quotes)
    kind = quotes.quotes[0].kind
    coupon = quotes.quotes[0].coupon_bp
    if kind == "par_spread_bp" and conventional_spread_bp is not None:
        raise ValueError("a spread-quoted curve stores conventional_spread_bp as null")
    if kind == "upfront_pct" and (conventional_spread_bp is None or len(conventional_spread_bp) != len(quotes.quotes)):
        raise ValueError("an upfront-quoted curve stores one conventional_spread_bp per pillar")
    data = {
        "label": quotes.label,
        "as_of": quotes.as_of.isoformat(),
        "recovery": quotes.recovery,
        "quote_kind": kind,
        "coupon_bp": coupon,
        "pillars": list(quotes.pillars),
        "quotes": [q.value for q in quotes.quotes],
        "conventional_spread_bp": None if conventional_spread_bp is None else list(conventional_spread_bp),
        "source": source,
        "note": note,
    }
    with Path(path).open("w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, indent=1)
        fh.write("\n")
