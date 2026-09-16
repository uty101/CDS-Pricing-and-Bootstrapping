"""The public objects, fixed by BUILD_PLAN.md Part D.1. No logic lives here.

Fields may be added later only through "Against the plan" in a review file.
Time t is act/365 fixed years from MarketState.as_of. Every curve carries its
own as_of; price() (Section 5) raises if the three curves in a MarketState
disagree on it. Quote invariants (coupon_bp required for upfront_pct quotes,
one kind per curve) are checked by the pricer and the bootstrap, not here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal, Protocol

from cds.conventions import DEFAULT_NOTIONAL, RECOVERY_SENIOR

QuoteKind = Literal["par_spread_bp", "upfront_pct"]
Side = Literal["buy", "sell"]


@dataclass(frozen=True, kw_only=True)
class Quote:
    kind: QuoteKind
    value: float
    coupon_bp: float | None = None  # required when kind is upfront_pct


@dataclass(frozen=True, kw_only=True)
class CDSTrade:
    trade_date: date
    maturity: date  # unadjusted IMM date
    notional: float = DEFAULT_NOTIONAL
    coupon_bp: float  # 100.0 or 500.0 for standard contracts
    side: Side  # protection buyer or seller
    recovery: float = RECOVERY_SENIOR  # assumed recovery
    quote: Quote | None = None  # the traded level, for MTM of seasoned trades


@dataclass(frozen=True, kw_only=True)
class MarketCurveQuotes:
    """Input to the bootstrap: one quote per pillar, all of one kind."""

    as_of: date
    pillars: tuple[str, ...]
    quotes: tuple[Quote, ...]
    recovery: float
    label: str


class DiscountCurve(Protocol):
    as_of: date

    def df(self, t: float) -> float: ...

    def forward(self, t1: float, t2: float) -> float: ...


class SurvivalCurve(Protocol):
    as_of: date
    pillar_times: tuple[float, ...]
    pillar_hazards: tuple[float, ...]

    def Q(self, t: float) -> float: ...  # noqa: N802 - the spec's symbol

    def hazard(self, t: float) -> float: ...


class RecoveryCurve(Protocol):
    as_of: date

    def R(self, t: float) -> float: ...  # noqa: N802 - the spec's symbol


@dataclass(frozen=True, kw_only=True)
class MarketState:
    as_of: date
    discount: DiscountCurve
    survival: SurvivalCurve
    recovery: RecoveryCurve
    quotes: MarketCurveQuotes


@dataclass(frozen=True, kw_only=True)
class PriceResult:
    """Every amount is stated at cash_settle_date (docs/CONVENTIONS_RESOLVED.md item 3)."""

    mtm: float  # side's dirty value net of inception cash, currency
    clean_upfront_pct: float  # buyer pays, % of notional, current unwind level
    accrued: float  # currency, accrual start to step-in
    par_spread_bp: float
    risky_annuity: float  # A, per unit notional per unit spread
    pv_protection: float  # PV_prot, per unit notional
    pv_premium: float  # c * A, per unit notional
    cash_settle_date: date


@dataclass(frozen=True, kw_only=True)
class RiskReport:
    """Field names are exactly the Table 3 columns (BUILD_PLAN.md Section 8).
    All amounts in currency for the trade's side."""

    mtm: float
    cs01_6m: float
    cs01_1y: float
    cs01_2y: float
    cs01_3y: float
    cs01_4y: float
    cs01_5y: float
    cs01_7y: float
    cs01_10y: float
    cs01_bucket_sum: float
    cs01_parallel: float
    cs01_central_6m: float
    cs01_central_1y: float
    cs01_central_2y: float
    cs01_central_3y: float
    cs01_central_4y: float
    cs01_central_5y: float
    cs01_central_7y: float
    cs01_central_10y: float
    cs01_central_parallel: float
    rec01: float
    rec01_hazard_fixed: float
    ir01: float
    jtd: float
    theta_calendar_1d: float
    theta_rolldown_1d: float
    theta_calendar_1m: float
    theta_rolldown_1m: float


@dataclass(frozen=True, kw_only=True)
class ExplainResult:
    """Field names are exactly the Table 4 columns (BUILD_PLAN.md Section 9)."""

    pnl_full: float
    pnl_spread_first_order: float
    pnl_spread_gamma: float
    pnl_recovery: float
    pnl_rates: float
    pnl_theta: float
    pnl_cross: float
    residual: float
    residual_pct_of_total: float
