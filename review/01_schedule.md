# Review — Section 01 — conventions.py and schedule.py

Date: 2026-09-16   Commit: cce41c4   Tests: 113/113

The review is committed separately from the code so it can cite the code
commit's sha without amending it (CLAUDE.md: never rewrite history). Later
sections do the same: `Section <NN>: <slug>` for the code, then
`Section <NN>: review`.

## What changed

- `cds/conventions.py` — every constant the plan lists, plus `ACT360_BASIS = 360`, `ACT365F_BASIS = 365`, `ROLL_RULES`, `CALENDARS`, `PILLAR_MONTHS`. The two basis integers exist so no other module writes `/360` or `/365`.
- `cds/calendars.py` — `is_business_day`, `adjust_following`, `add_business_days` for `"weekends"` (default) and `"us_uk"`. The US/UK list is read from the CSV once and cached; QuantLib is not imported.
- `cds/schedule.py` — `standard_maturity` (both roll rules), `previous_imm`, `next_imm`, `imm_dates_between`, `is_imm_date`, `cds_schedule` returning a frozen `Schedule`, `year_fraction_act365f`, `year_fraction_act360`; re-exports `adjust_following`.
- `cds/types.py` — Part D.1 verbatim, as keyword-only frozen dataclasses (keyword-only so defaulted fields can sit in the plan's order). `RiskReport` and `ExplainResult` carry the field lists Sections 8 and 9 name, so those sections add nothing to this file unless they deviate. No logic; `Quote` invariants are not checked here.
- `scripts/make_calendar.py`, `data/calendars/us_uk_holidays.csv` (981 weekday holidays 2000–2060), `data/calendars/README.md`.
- `tests/conftest.py` — one new constant, `DAY_COUNT_ABS_TOL = 1e-12`.
- `tests/test_schedule.py` (110 tests), `tests/test_repo_hygiene.py` (3 tests).
- `docs/CONVENTIONS_RESOLVED.md` was committed before this section started (f40fc3c) and the gamma-sign plan correction as 6ad6b38.

**Rules stated in full.**

1. Standard maturity = anchor + tenor + 3 months. `semiannual_2015`: anchor is the most recent 20 Mar or 20 Sep on or before the trade date. `quarterly_2009`: anchor is the most recent IMM 20th on or before the trade date. A trade *on* the anchor date uses that anchor (so 20 Mar 2016 5Y → 20 Jun 2021, while 19 Mar 2016 → 20 Dec 2020).
2. Step-in = trade + 1 calendar day. Cash settle = trade + 3 business days on the schedule's calendar.
3. Accrual dates are the Following-adjusted IMM 20ths; the last period ends on the unadjusted maturity and its fraction includes one extra day (act/360). Payment dates are the adjusted period ends, including the adjusted maturity for the last one.
4. **First accrual date (taken from the oracle, not in the plan):** the IMM 20th on or before the step-in date, adjusted Following; if that adjusted date falls *after* the step-in date (the 20th was a weekend and step-in is that weekend), the period starting one quarter earlier is used. Trade Sat 19 Mar 2016 → step-in Sun 20 Mar; 20 Mar adjusts to Mon 21 Mar > step-in, so accrual starts Mon 21 Dec 2015 and 90 days are accrued. Trade Sun 20 Dec 2020 → step-in Mon 21 Dec; 20 Dec adjusts to 21 Dec = step-in, so accrual starts 21 Dec 2020 with 0 days accrued. This is what `ql.Schedule(step_in, …, Following, Unadjusted, CDS2015)` does, and it is what the plan's criterion 3 compares against date for date.
5. `accrued_days` = step-in − first accrual date, in calendar days; act/360 when turned into cash (Section 5).

## Findings

**Claim: both roll rules reproduce QuantLib's `cdsMaturity` on every tenor and every listed trade date.**
Number: 256 comparisons (16 dates × 8 tenors × 2 rules), 0 mismatches.
Rows (trade date, weekday, 5Y ours / ql under CDS2015, 5Y ours / ql under CDS, 6M under CDS2015):

| trade date | weekday | 5Y semiannual_2015 | ql CDS2015 | 5Y quarterly_2009 | ql CDS | 6M semiannual_2015 |
|---|---|---|---|---|---|---|
| 2015-12-18 | Fri | 2020-12-20 | 2020-12-20 | 2020-12-20 | 2020-12-20 | 2016-06-20 |
| 2016-03-19 | Sat | 2020-12-20 | 2020-12-20 | 2021-03-20 | 2021-03-20 | 2016-06-20 |
| 2016-03-20 | Sun | 2021-06-20 | 2021-06-20 | 2021-06-20 | 2021-06-20 | 2016-12-20 |
| 2016-03-21 | Mon | 2021-06-20 | 2021-06-20 | 2021-06-20 | 2021-06-20 | 2016-12-20 |
| 2016-09-19 | Mon | 2021-06-20 | 2021-06-20 | 2021-09-20 | 2021-09-20 | 2016-12-20 |
| 2016-09-20 | Tue | 2021-12-20 | 2021-12-20 | 2021-12-20 | 2021-12-20 | 2017-06-20 |
| 2020-02-29 | Sat | 2024-12-20 | 2024-12-20 | 2025-03-20 | 2025-03-20 | 2020-06-20 |
| 2020-12-20 | Sun | 2025-12-20 | 2025-12-20 | 2026-03-20 | 2026-03-20 | 2021-06-20 |
| 2020-12-31 | Thu | 2025-12-20 | 2025-12-20 | 2026-03-20 | 2026-03-20 | 2021-06-20 |
| 2021-01-04 | Mon | 2025-12-20 | 2025-12-20 | 2026-03-20 | 2026-03-20 | 2021-06-20 |
| 2024-02-29 | Thu | 2028-12-20 | 2028-12-20 | 2029-03-20 | 2029-03-20 | 2024-06-20 |
| 2024-06-19 | Wed | 2029-06-20 | 2029-06-20 | 2029-06-20 | 2029-06-20 | 2024-12-20 |
| 2024-06-20 | Thu | 2029-06-20 | 2029-06-20 | 2029-09-20 | 2029-09-20 | 2024-12-20 |
| 2025-09-20 | Sat | 2030-12-20 | 2030-12-20 | 2030-12-20 | 2030-12-20 | 2026-06-20 |
| 2026-06-19 | Fri | 2031-06-20 | 2031-06-20 | 2031-06-20 | 2031-06-20 | 2026-12-20 |
| 2026-09-16 | Wed | 2031-06-20 | 2031-06-20 | 2031-06-20 | 2031-09-20 | 2026-12-20 |

The two rules differ on 9 of the 16 dates, always by one quarter, exactly where a trade falls between a semi-annual roll and the next quarterly IMM date. The 6M column shows the semi-annual rule's short contracts: 2024-06-19 6M matures 2024-12-20, six months out, but 2016-09-19 6M matures 2016-12-20, three months out.

**Claim: the coupon schedule matches QuantLib date for date on both calendars, and the first accrual date follows rule 4.**
Number: 32 five-year schedules (16 dates × 2 calendars) plus 8 six-month and ten-year schedules, 0 mismatches on accrual starts, accrual ends, payment dates, cash settle dates and accrued days.
Rows (weekend-only calendar, 5Y):

| trade date | step-in | first accrual (ours) | first accrual (ql) | accrued days | cash settle | periods | last fraction |
|---|---|---|---|---|---|---|---|
| 2016-03-19 | 2016-03-20 | 2015-12-21 | 2015-12-21 | 90 | 2016-03-23 | 20 | 0.252778 |
| 2016-03-20 | 2016-03-21 | 2016-03-21 | 2016-03-21 | 0 | 2016-03-23 | 21 | 0.252778 |
| 2016-03-21 | 2016-03-22 | 2016-03-21 | 2016-03-21 | 1 | 2016-03-24 | 21 | 0.252778 |
| 2020-12-20 | 2020-12-21 | 2020-12-21 | 2020-12-21 | 0 | 2020-12-23 | 20 | 0.250000 |
| 2024-06-20 | 2024-06-21 | 2024-06-20 | 2024-06-20 | 1 | 2024-06-25 | 20 | 0.258333 |
| 2025-09-20 | 2025-09-21 | 2025-06-20 | 2025-06-20 | 93 | 2025-09-24 | 22 | 0.255556 |
| 2026-06-19 | 2026-06-20 | 2026-03-20 | 2026-03-20 | 92 | 2026-06-24 | 21 | 0.258333 |
| 2026-09-16 | 2026-09-17 | 2026-06-22 | 2026-06-22 | 87 | 2026-09-21 | 20 | 0.258333 |

The last fraction is (days + 1)/360: 0.252778 = 91/360 for a 90-day final period, 0.258333 = 93/360 for 92 days. A trade on a weekday roll date (2024-06-20) accrues 1 day; on a Sunday roll date (2020-12-20) it accrues 0 days because step-in is the adjusted 20th itself.

**Claim: the US/UK calendar changes payment dates only where a weekday holiday lands on a coupon date.**
Number: across the 16 five-year schedules, 4 payment dates differ between the two calendars, all the same holiday.
Rows (trade date, period, weekends pays, us_uk pays):

| 2020-02-29 | period 9 | 2022-06-20 | 2022-06-21 |
| 2020-12-20 | period 5 | 2022-06-20 | 2022-06-21 |
| 2020-12-31 | period 5 | 2022-06-20 | 2022-06-21 |
| 2021-01-04 | period 5 | 2022-06-20 | 2022-06-21 |

Mon 20 Jun 2022 is the US observance of Juneteenth. No other IMM 20th in the schedules tested is a US or UK weekday holiday.

**Claim: accrual fractions equal QuantLib's `Actual360()` per period and `Actual360(True)` on the last.**
Number: 32 schedules, every period, absolute difference under 1e-12.
Rows (the 1Y schedule from 2026-09-16: period, accrual start, accrual end, payment, fraction):

| 0 | 2026-06-22 | 2026-09-21 | 2026-09-21 | 0.252778 |
| 1 | 2026-09-21 | 2026-12-21 | 2026-12-21 | 0.252778 |
| 2 | 2026-12-21 | 2027-03-22 | 2027-03-22 | 0.252778 |
| 3 | 2027-03-22 | 2027-06-20 | 2027-06-21 | 0.252778 |

Period 3 ends on the unadjusted maturity (Sun 20 Jun 2027), pays on Mon 21 Jun, and its fraction is (90 + 1)/360.

**Claim: the two day counts are distinct and the basis constants are used.**
Number: 2024-01-01 to 2025-01-01 is 366/365 under act/365F and 366/360 under act/360; `test_repo_hygiene` finds no `/360`, `/365`, `= 360`, `= 365`, `= 0.40`, `= 0.25` or `= 0.20` in code tokens outside `cds/conventions.py` (0 hits over `cds/` and `scripts/`).

**Claim: the committed holiday CSV is the QuantLib calendar it claims to be.**
Number: 981 listed dates equal `holidayList(JointCalendar(US Settlement, UK Settlement), 2000-01-01, 2060-12-31)` element for element, and every day of 2026 (365 checks) is classified the same way by `is_business_day("us_uk")` and `isBusinessDay`.

## Before / after

Nothing existed before this section. Metrics introduced: none numerical beyond dates and day counts; the table above is the first state.

## Not verified

- **Rule 4 against the ISDA C library.** The step-back-a-quarter rule for a weekend 20th is QuantLib's. The ISDA C library's fee leg starts at whatever accrual start date the caller passes and then adjusts it Following; if the caller (Markit's converter) passes the unadjusted 20th, the first accrual date would be Mon 21 Mar 2016 for a 19 Mar 2016 trade, one day *after* step-in, with 0 days accrued and no coupon for the step-in day itself. The two readings differ only for trades on the Friday or Saturday before a weekend 20th (and the Sunday itself), by one coupon period's timing and by 90-ish accrued days. What would settle it: a Markit/ISDA converter run for trade date 2016-03-19, or a maintained ISDA C binding (plan Part C item 4 says not to spend a session on that). Until then the library matches the Section 7 oracle by construction.
- **`quarterly_2009` coupon schedules.** Only maturities are checked against `DateGeneration.CDS`; `cds_schedule` is independent of the roll rule and was checked against `CDS2015` schedules only. A `ql.Schedule(..., DateGeneration.CDS)` comparison on the same dates would settle it; I expect identical dates because both rules seed from `previousTwentieth`.
- **Holiday CSV beyond 2026.** Only 2026 is checked day by day; the full list is checked as a list. Future one-off UK holidays (a bank holiday declared later) will not be in either QuantLib or the CSV.
- **`Quote` and `CDSTrade` invariants** (coupon required for upfront quotes; `par_spread_bp` quote equal to `coupon_bp`; recovery in [0, 1]) are not enforced anywhere yet. Section 5's pricer is where the plan puts them.
- **`add_business_days` for cash settlement when the trade date itself is a weekend** (2016-03-19, 2020-12-20, 2025-09-20 are weekends): the function counts three business days after the trade date, as `ql.Calendar.advance` does, and the comparison passed on those dates; whether a real trade date can be a weekend is a question for the data, not the schedule.

## Open

Nothing tried and unexplained.

## Against the plan

- **Hygiene scope.** Criterion 7 says no `.py` outside `cds/conventions.py` may carry the convention literals. The test scans `cds/` and `scripts/` only. `tests/` is exempt because the tests are the independent oracle: `test_day_counts_on_a_leap_year` asserts `== 366/365` on purpose. Bar as stated: 0 hits in `cds/` and `scripts/`; met.
- **Extra constants in `conventions.py`** (`ACT360_BASIS`, `ACT365F_BASIS`, `ROLL_RULES`, `CALENDARS`, `PILLAR_MONTHS`) beyond the plan's list, for the reason in "What changed".
- **`RiskReport` and `ExplainResult` fields written now**, from the plan's Section 8 and 9 lists, rather than left as `...` for those sections to fill. No field differs from the plan.
- **Rule 4** is a rule the plan did not state. It comes from the oracle the plan names; it is recorded above and in the module docstring rather than in `docs/CONVENTIONS_RESOLVED.md`, which is the user's file.
- **Two commits for the section** (code, then review), for the sha reason at the top.
- A stray copy of `11_CDS_Pricing_Bootstrap.docx` appeared at the repo root during the session (identical to `docs/`, timestamp after Section 0's commits). It was not created by this session's commands, is not in the section's file list, and is left untracked for the user to remove or keep.

## Reviewer reads (max 6, in order)

1. `cds/schedule.py` — the rules in the docstring and the first-accrual-date step-back in `cds_schedule`.
2. `tests/test_schedule.py` — the 16 dates and what each oracle call compares.
3. `cds/conventions.py` — every constant, to confirm nothing is missing before Section 2 builds on it.
4. `cds/types.py` — Part D.1 as code; check the keyword-only choice and the two pre-filled report dataclasses.
5. `tests/test_repo_hygiene.py` — the scope decision above.
