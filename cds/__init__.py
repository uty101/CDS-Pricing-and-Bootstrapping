"""CDS pricing and hazard rate bootstrapping.

Modules, in the order BUILD_PLAN.md built them, with the public objects a
user of the library reaches for. Symbols follow docs/SPEC.md section 6;
every convention lives in cds.conventions.

    conventions   every day count, roll rule, coupon, recovery and calendar default;
                  DEFAULT_NOTIONAL, DEFAULT_CALENDAR, CALENDARS, PILLARS
    schedule      cds_schedule, Schedule, standard_maturity, next_imm, previous_imm,
                  year_fraction_act360, year_fraction_act365f
    calendars     is_business_day, adjust_following, add_business_days (weekend-only and US/UK)
    types         CDSTrade, Quote, MarketCurveQuotes, MarketState, PriceResult, RiskReport,
                  ExplainResult; the DiscountCurve, SurvivalCurve and RecoveryCurve protocols
                  the curve classes in cds.curves satisfy
    curves        DiscountCurve, SurvivalCurve, RecoveryCurve, bootstrap_ois,
                  discount_curve_from_file, standard_pillar_dates
    legs          leg_values, LegValues, CurveArrays (the vectorised path), Engine ("isda" | "grid")
    pricer        price, value, Valuation, implied_flat_hazard, quoted_spread_to_upfront,
                  upfront_to_quoted_spread, cash_settle_date, accrued_days
    textbook      the continuous-compounding model, comparison only: par_spread_bp, upfront_pct,
                  annuity, protection_pv, implied_hazard
    bootstrap     bootstrap, BootstrapResult, BootstrapArbitrageError, market_state,
                  market_curve_quotes_from_file, conventional_spreads_bp, pillar_trade
    validation    quantlib_check: the QuantLib IsdaCdsEngine comparison behind Table 2
    risk          risk, cs01_by_pillar, cs01_parallel, rec01, rec01_hazard_fixed, ir01, jtd, theta;
                  the bump sizes BUMP_SPREAD_BP, BUMP_RECOVERY, BUMP_RATE_BP
    scenarios     Scenario, standard_grid, sweep_grid, scenario_state, revalue, run, RUN_COLUMNS
    explain       explain, sensitivities, Sensitivities, gamma_parallel
    report        the table and chart generators behind outputs/: table_1_hazard_curves to
                  table_5_isda_vs_textbook, chart_1_survival_hazard to chart_3_pnl_vs_spread_shock

A typical session: read a discount curve with discount_curve_from_file,
a quote curve with market_curve_quotes_from_file, bootstrap() them into a
BootstrapResult and market_state() into a MarketState; build a CDSTrade;
price() it for a PriceResult, risk() it for a RiskReport, run() a scenario
grid, explain() a move between two states.
"""
