# Data note

What in this repo is illustrative, what is sourced, where from, and when. The
library is the deliverable; the data exist so the library has something to
run on. Every data file carries a `source` field and a `note` field that
repeat the relevant line below.

Free data is the weakness of this project (spec section 4). Single-name CDS
curves are not free; SOFR OIS par rates are published but not by FRED; the
default studies are free PDFs. The README states this framing: a pricing and
risk library validated against a reference implementation, run on
illustrative curves.

## Illustrative: CDS quote curves (`data/curves/`, Section 6)

Three stylised curves in bp on pillars 6M, 1Y, 2Y, 3Y, 4Y, 5Y, 7Y, 10Y.
The levels are chosen to look like an investment-grade name, a high-yield
name and a distressed name on an ordinary day; they are not observations of
any name on any date.

| label | quotes (bp) | recovery | quoted as |
|---|---|---|---|
| IG_flat | 45, 50, 60, 70, 80, 90, 105, 120 | 40% senior unsecured | par spread |
| HY_steep | 150, 200, 300, 380, 440, 500, 560, 600 | 25% HY | par spread |
| distressed_inverted | 2500, 2200, 1800, 1500, 1350, 1200, 1050, 950 | 20% | upfront at a 500 bp coupon |

The distressed curve is committed as upfront quotes. The upfronts are derived
in Section 6 from the spread levels above with the library's own flat-hazard
conversion on the committed discount curve; the conventional spreads are
stored in the same file so both are visible. If the distressed levels
bootstrap without a negative hazard, a fourth file `distressed_arb.json`
with a steeper front end is committed for the arbitrage-detection test
(BUILD_PLAN.md Part B item 6).

All curves share one valuation date: the date of the rates snapshot below.

Recovery assumptions are market convention, not data: 40% senior unsecured,
20% subordinated, 25% HY index (spec section 4). Realised recovery is
unobservable in advance; a 40% assumption on a name trading at 10 points
upfront is the wrong assumption, which is why the market quotes recovery
locks on distressed names.

## Sourced: SOFR OIS par rates (`data/rates/`, Section 2)

One snapshot of USD SOFR OIS par rates, tenors 1M to 30Y, annual fixed
act/360 against SOFR compounded. FRED publishes overnight SOFR
(`SOFR`) and the 30/90/180-day backward-looking averages, not OIS par
rates, so the snapshot is taken from a published swap-rate page.

Candidate sources, to be settled in `docs/CONVENTIONS_RESOLVED.md` (plan
Part B item 4):

- 1Y to 30Y: ICE Swap Rate, USD SOFR, 11:00 New York fixing.
- 1M, 3M, 6M: CME Term SOFR, labelled as a Term SOFR proxy for OIS.

Snapshot date, page URL and the date the page was read are recorded in the
file and here when Section 2 runs. Fields: `source`, `source_url`,
`snapshot_taken`, `note`.

Section 2 snapshot: `data/rates/sofr_ois_2026-09-15.json`, rates for
**15 September 2026**, read on **16 September 2026**.

- 1M, 3M, 6M: CME Term SOFR fixings for 15 Sep 2026 (3.88572, 3.97991,
  4.12897), read from global-rates.com
  (`https://www.global-rates.com/en/interest-rates/cme-term-sofr/`);
  cmegroup.com refuses automated reads. Term SOFR is a forward-looking term
  rate, not an OIS par rate; the gap is a few bp at 6M and moves a 5Y CDS
  upfront by well under 0.1 bp (plan Part B item 4).
- 1Y to 30Y: BlueGamma's public USD SOFR swap-rate page
  (`https://www.bluegamma.io/usd-swap-rates`), 15 Sep 2026 close (21:00
  London), mids built from interdealer broker and exchange quotes, shown to
  2 decimal places (so each rate carries up to 0.5 bp of rounding). **This is
  a substitution**: `docs/CONVENTIONS_RESOLVED.md` item 4 names ICE Swap Rate
  for these tenors, but on 16 Sep 2026 ice.com published no fixings on a
  free page (the ICE Swap Rate page carries methodology documents and the
  report centre lists only a monthly volume report), and the values are
  licensed. BlueGamma's 1M and 3M rows (3.89, 3.98) agree with the Term SOFR
  fixings to the rounding, which is the only cross-check available.
- The rates are the last complete set at the time of reading: the 16 Sep
  11:00 New York swap fixing had not happened. So the snapshot date, and the
  valuation date of every illustrative curve, is 15 Sep 2026, one day before
  the Section 2 session.
- Bootstrapped as annual fixed act/360 against compounded SOFR, single
  payment under 1Y, spot date = `as_of` (T+0), payment dates rolled Following
  on a weekend-only calendar. The sources' own conventions are close to but
  not stated as exactly this; the file's `note` says so.

## Sourced: historical cumulative default rates (`data/defaults/`, Section 10)

The 5Y cumulative default rate by rating bucket from one public annual
default study (Moody's "Annual Default Study" or S&P "Annual Global
Corporate Default And Rating Transition Study"), typed into a small CSV with
the study's name, year and exhibit number. Used once, for the sanity check of
implied against historical 5Y default probability in the README.

_Section 10 fills in:_ study ____, year ____, exhibit ____.

## Generated: holiday calendar (`data/calendars/`, Section 1)

US and UK holidays 2000 to 2060, generated once from QuantLib's
`JointCalendar(UnitedStates(Settlement), UnitedKingdom(Settlement))` by a
committed script. The library reads the CSV and never imports QuantLib at
runtime. Optional; the default calendar is weekend-only, as in the ISDA
model.

## Not data: the spec

`docs/SPEC.md` is a pandoc conversion of `docs/11_CDS_Pricing_Bootstrap.docx`
(pandoc 3.9, `-t gfm --wrap=none`), made in Section 0. The docx is the
original; the Markdown is for reading in the repo.
