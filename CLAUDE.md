# CLAUDE.md — CDS Pricing and Hazard Rate Bootstrapping

Read this first, every session. Then read `BUILD_PLAN.md`, the previous
section's review file under `review/`, and `docs/CONVENTIONS_RESOLVED.md`
(the user's answers to the plan's "Conventions to confirm" list) before
writing anything.

The spec is `docs/SPEC.md` (a pandoc conversion of
`docs/11_CDS_Pricing_Bootstrap.docx`). `BUILD_PLAN.md` is the authority on what
gets built in which order and what "done" means for each section; where the
plan corrects the spec, the plan wins, and the plan says so explicitly in its
"Corrections to the spec" section.

## Global rules

- One section of BUILD_PLAN.md per session. Never start the next section without an explicit instruction in the session prompt.
- No code changes outside the current section's file list unless the section says so. If a bug in an earlier section blocks you, fix it, name it in "Against the plan", and add a regression test.
- Every section ends with `review/<NN>_<slug>.md` written from `review/TEMPLATE.md`, all tests green, and a push to `main`. A section with a review file whose "Not verified" section is empty is treated as not done.
- Every number reported in a review file has the rows behind it, shown in the file. An aggregate with no rows is not evidence.
- Conventions live in one place: `cds/conventions.py`. Nothing else hard codes a day count, a roll rule, a coupon or a recovery.
- No continuous-compounding shortcuts anywhere in the ISDA path. The textbook model is a separate, clearly named module used only for comparison.
- Tests use `pytest`. Numerical tolerances are stated in bp and written as constants at the top of the test file with a one-line reason.
- Dependencies: numpy, scipy, pandas, matplotlib, QuantLib (pip name `QuantLib`), pytest. Pin versions in `pyproject.toml`. No other pricing libraries.
- Data are illustrative. Every curve file in `data/` has a `source` field and a `note` field saying so. The library is the deliverable.
- Plain English in comments and docstrings. State the formula being implemented, with the symbol names matching `docs/SPEC.md` section 6.
- Do not use the words robust, resilient, rigorous, leverage, grounded anywhere in the repo.
- Python 3.11. Work on `main` directly. One commit per section, message `Section <NN>: <slug>`, plus fix commits `Section <NN> fix: <what>` if the review asks for changes. Never force push, never rewrite history, never delete a review file.
- If a dependency will not install (QuantLib wheels fail on the platform), stop the session, write the error in the review file under "Open", and report it. Do not substitute another library.
- A later session starts with exactly this prompt from the user and nothing else: `Execute Section <NN> of BUILD_PLAN.md.` Read CLAUDE.md, BUILD_PLAN.md, the previous section's review file, and the "Conventions to confirm" resolutions in `docs/CONVENTIONS_RESOLVED.md` before writing anything.

## How the rules are applied here

- Tolerance constants have one shared home, `tests/conftest.py`, each with a
  one-line reason. A test file imports the constants it uses at its top so the
  reader of that file still sees them there. Do not redefine a constant in a
  test file with a different value.
- "All tests green" means `uv run pytest -q` exits 0 with zero skips that were
  not already declared in the plan. A skipped QuantLib test is a failed
  section.
- The public objects in `cds/types.py` (`CDSTrade`, `Quote`,
  `MarketCurveQuotes`, `MarketState`, `PriceResult`, `RiskReport`,
  `ExplainResult`, the three curve protocols) are fixed by BUILD_PLAN.md
  section 3a. A field may be added only through "Against the plan" in the
  review file of the section that adds it.
- Bump definitions for every risk measure are fixed by BUILD_PLAN.md section
  3b. `cds/risk.py` implements those and no other conventions.
- Output file names and column names are fixed in the plan section that
  produces them and do not change afterwards. The README embeds output files
  by path and computes nothing.
- Sign convention, stated once: the protection buyer's MTM is positive when
  spreads widen. `side="sell"` negates. Notional default 10,000,000.
- Time `t` is act/365 fixed years from `MarketState.as_of`. Accrual is
  act/360. The two are never mixed; `cds/conventions.py` names both.
- Every curve object carries its own `as_of`; `price()` raises if the three
  curves in a `MarketState` disagree.

## Reviews and questions go to GitHub

The user reviews from the Claude app, not from the repo. So every section
ends with one more step after the push: post the review file as a GitHub
issue on `uty101/CDS-Pricing-and-Bootstrapping`, titled exactly as the
review's H1, labelled `review`, with a "Questions for the reviewer" list at
the top (every "Against the plan" item and every decision the user must
make, numbered, each ending in a question) and the full review file below
a rule. Use `uv run python scripts/gh_issue.py --title "..." --body-file
<file> --label review`; it reads the GitHub token git already stores and
never prints it. Any question that arises mid-section and cannot wait is
posted the same way, as its own issue. The next session reads the previous
section's issue comments before starting and commits the answers to
`docs/CONVENTIONS_RESOLVED.md` where they change a convention.

## Environment

- `uv` manages the environment. `uv sync` installs; `uv run pytest -q` tests.
  Python 3.11 is pinned in `.python-version`.
- Set `UV_LINK_MODE=copy` before `uv sync` on this machine; the uv cache and
  the repo are on different filesystems and hardlinking fails.
- QuantLib 1.43 wheels install on Windows/Python 3.11 — confirmed in
  Section 0. `ql.IsdaCdsEngine` exposes `HalfDayBias`, `NoBias`, `Piecewise`,
  `Flat`, `Taylor`, `NoFix`.
- Charts are written with matplotlib's `Agg` backend; nothing opens a window.

## Repo map

```
CLAUDE.md                 this file
BUILD_PLAN.md             the sections, one per session
README.md                 status; rewritten in Section 10
pyproject.toml            pinned dependencies
docs/SPEC.md              the spec (converted from the docx alongside it)
docs/DATA_NOTE.md         what is illustrative, what is sourced, from where
docs/CONVENTIONS_RESOLVED.md   the user's answers to "Conventions to confirm"
                          (committed at the start of Section 1)
review/TEMPLATE.md        the review file template; review/<NN>_<slug>.md per section
cds/                      the library; module names listed in cds/__init__.py
data/curves/              illustrative CDS quote files (Section 6)
data/rates/               the SOFR OIS snapshot (Section 2)
tests/                    pytest; conftest.py holds the tolerance constants
outputs/tables/           table_<n>_<slug>.csv + .md
outputs/charts/           chart_<n>_<slug>.png + .csv
```

## Working style

- Verify before concluding. If a number disagrees with QuantLib, the plan
  lists the likely causes in order (schedule, day count, accrual-on-default
  flag, interpolation, model). Check them in that order and show the rows.
- A review file is written for the reviewer, who reads it in a separate chat
  without the code open. Every claim carries its rows.
- When a section cannot be completed, stop, write what was tried under
  "Open", commit and push what exists, and say so. Do not start the next
  section to make progress.
