"""Build outputs/results.html from the committed outputs, and keep the
README's table blocks equal to the committed Markdown tables
(BUILD_PLAN.md Section 10).

    uv run python scripts/make_results.py            # write outputs/results.html and sync README.md
    uv run python scripts/make_results.py --check    # exit 1 if either file would change

results.html is one self-contained page: every chart PNG under
outputs/charts/ is embedded as a base64 data URI, every table under
outputs/tables/ is rendered from its committed .md file, the sections run
in the README's order, and there is no JavaScript and no external request.
Nothing is computed here; the numbers are read from the files the
generators in cds.report wrote.

README.md carries the same tables inline so they render on GitHub. Each is
wrapped in a pair of markers,

    <!-- table: table_2_quantlib_validation -->
    ...
    <!-- end table -->

and sync_readme() replaces what sits between the markers with the
committed .md file's text, so the README never holds a table that differs
from outputs/tables/. tests/test_readme_paths.py checks both files are
what this script writes.
"""

from __future__ import annotations

import argparse
import base64
import html
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TABLES_DIR = ROOT / "outputs" / "tables"
CHARTS_DIR = ROOT / "outputs" / "charts"
README = ROOT / "README.md"
RESULTS = ROOT / "outputs" / "results.html"
REPO_URL = "https://github.com/uty101/CDS-Pricing-and-Bootstrapping"

TITLE = "CDS Pricing and Hazard Rate Bootstrapping: results"

# The sections of results.html in the README's order. Each item is
# ("table", stem) or ("chart", stem); every committed table and chart
# appears exactly once (the test checks against the directories).
SECTIONS: tuple[tuple[str, str, tuple[tuple[str, str], ...]], ...] = (
    (
        "What the library matches",
        "Every pricer number and every matched-node hazard agrees with QuantLib's IsdaCdsEngine "
        "inside the tolerance in the last columns. The two rows reading False are the distressed "
        "curve's 1Y and 2Y hazards on our own pillar grid, whose nodes sit one to three days from "
        "QuantLib's; on QuantLib's nodes (the bootstrap_quantlib_nodes rows) they agree to under 1e-8 bp.",
        (("table", "table_2_quantlib_validation"),),
    ),
    (
        "Recovery sensitivity read two ways",
        "rec01 with the spreads held fixed and the curve re-bootstrapped, against rec01 with the "
        "hazards held fixed. The legend of panel (b) carries the least-squares slope of each line "
        "in dollars per recovery point over the 51 rows of the chart's CSV.",
        (("table", "table_3_risk_report"), ("chart", "chart_2_recovery_dependence")),
    ),
    (
        "The ISDA path against the textbook model",
        "ISDA clean upfront and par spread of each pillar contract on the full bootstrapped curve, "
        "against the continuous-time model at the flat hazard implied by the same spread. "
        "Differences are ISDA minus textbook.",
        (("table", "table_5_isda_vs_textbook"),),
    ),
    (
        "The P&L explain",
        "The 5Y IG protection buy at a 100 bp coupon on $10m under the standard grid: full "
        "revaluation, first order from the per-pillar CS01s, the gamma, recovery, rates and cross "
        "terms, and what is left. The chart sweeps the spread multiplier from 0.5 to 4.",
        (("table", "table_4_pnl_explain"), ("table", "table_4_pnl_explain_full"), ("chart", "chart_3_pnl_vs_spread_shock")),
    ),
    (
        "The curves",
        "The three illustrative curves and the arbitrage test curve: quotes, bootstrapped forward "
        "hazards, survival and cumulative default probability at each pillar.",
        (("table", "table_1_hazard_curves"), ("chart", "chart_1_survival_hazard")),
    ),
)

# One CSS block, inline; no external stylesheet, no font request.
STYLE = """
body { font-family: Georgia, 'Times New Roman', serif; max-width: 1100px; margin: 2em auto; padding: 0 1em; color: #222; line-height: 1.45; }
h1 { font-size: 1.6em; } h2 { font-size: 1.25em; margin-top: 2em; border-bottom: 1px solid #ccc; }
p.note { color: #555; }
table { border-collapse: collapse; font-family: Consolas, 'Courier New', monospace; font-size: 12px; margin: 1em 0; }
th, td { border: 1px solid #ccc; padding: 2px 6px; text-align: right; white-space: nowrap; }
th { background: #f2f2f2; } td:first-child, th:first-child, td.text, th.text { text-align: left; }
div.scroll { overflow-x: auto; }
img { max-width: 100%; height: auto; display: block; margin: 1em 0; border: 1px solid #ddd; }
figcaption, p.source { font-size: 0.9em; color: #555; }
"""

TABLE_MARKER = re.compile(r"<!-- table: ([a-z0-9_]+) -->\n(.*?)<!-- end table -->", re.DOTALL)


def parse_markdown_table(text: str) -> tuple[list[str], list[list[str]]]:
    """The header cells and the body rows of a pipe table as write_table
    writes it: header, separator, rows."""
    lines = [line for line in text.strip().splitlines() if line.strip()]
    if len(lines) < 2 or not lines[0].startswith("|") or not set(lines[1]) <= set("|-: "):
        raise ValueError("not a pipe table")

    def cells(line: str) -> list[str]:
        return [c.strip() for c in line.strip().strip("|").split("|")]

    header = cells(lines[0])
    rows = [cells(line) for line in lines[2:]]
    for row in rows:
        if len(row) != len(header):
            raise ValueError(f"row has {len(row)} cells, header {len(header)}")
    return header, rows


NUMBER = re.compile(r"^-?\d+(\.\d+)?$")


def render_table(stem: str) -> str:
    """The committed .md table as an HTML table with the stem as its id.
    Text cells are left-aligned, numbers right-aligned; nothing is
    reformatted."""
    header, rows = parse_markdown_table((TABLES_DIR / f"{stem}.md").read_text(encoding="utf-8"))
    text_cols = [not all(NUMBER.match(row[j]) or row[j] == "" for row in rows) for j in range(len(header))]

    def cell(tag: str, j: int, value: str) -> str:
        cls = ' class="text"' if text_cols[j] else ""
        return f"<{tag}{cls}>{html.escape(value)}</{tag}>"

    out = [f'<div class="scroll"><table id="{stem}">', "<thead><tr>" + "".join(cell("th", j, h) for j, h in enumerate(header)) + "</tr></thead>", "<tbody>"]
    for row in rows:
        out.append("<tr>" + "".join(cell("td", j, v) for j, v in enumerate(row)) + "</tr>")
    out += ["</tbody></table></div>", f'<p class="source">outputs/tables/{stem}.csv, {len(rows)} rows</p>']
    return "\n".join(out)


def render_chart(stem: str) -> str:
    """The committed PNG as a data URI, with the stem as the image id."""
    png = (CHARTS_DIR / f"{stem}.png").read_bytes()
    uri = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
    return f'<figure><img id="{stem}" src="{uri}" alt="{stem}"><figcaption>outputs/charts/{stem}.png; data in {stem}.csv</figcaption></figure>'


def build_results_html() -> str:
    parts = [
        "<!DOCTYPE html>",
        '<html lang="en"><head><meta charset="utf-8">',
        f"<title>{html.escape(TITLE)}</title>",
        f"<style>{STYLE}</style></head><body>",
        f"<h1>{html.escape(TITLE)}</h1>",
        '<p class="note">Generated by scripts/make_results.py from the committed files under outputs/. '
        "The curves are illustrative (docs/DATA_NOTE.md); the library is validated against QuantLib. "
        f'Repository: <a href="{REPO_URL}">{REPO_URL}</a>. Valuation date 15 September 2026.</p>',
    ]
    for heading, note, items in SECTIONS:
        parts.append(f"<h2>{html.escape(heading)}</h2>")
        parts.append(f'<p class="note">{html.escape(note)}</p>')
        for kind, stem in items:
            parts.append(render_table(stem) if kind == "table" else render_chart(stem))
    parts.append("</body></html>\n")
    return "\n".join(parts)


def sync_readme(text: str) -> str:
    """The README with every marked table block replaced by the committed
    .md file's text."""

    def replace(match: re.Match) -> str:
        stem = match.group(1)
        table = (TABLES_DIR / f"{stem}.md").read_text(encoding="utf-8").strip()
        # Blank lines either side so GitHub closes the comment block before the table.
        return f"<!-- table: {stem} -->\n\n{table}\n\n<!-- end table -->"

    return TABLE_MARKER.sub(replace, text)


def embedded_stems() -> tuple[list[str], list[str]]:
    """The table and chart stems SECTIONS embeds, in order."""
    tables = [stem for _, _, items in SECTIONS for kind, stem in items if kind == "table"]
    charts = [stem for _, _, items in SECTIONS for kind, stem in items if kind == "chart"]
    return tables, charts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--check", action="store_true", help="exit 1 if results.html or README.md would change")
    args = parser.parse_args(argv)
    page = build_results_html()
    readme = sync_readme(README.read_text(encoding="utf-8"))
    changed = []
    if not RESULTS.exists() or RESULTS.read_text(encoding="utf-8") != page:
        changed.append(RESULTS)
    if README.read_text(encoding="utf-8") != readme:
        changed.append(README)
    if args.check:
        for path in changed:
            print(f"would change {path.relative_to(ROOT)}")
        return 1 if changed else 0
    RESULTS.write_text(page, encoding="utf-8", newline="\n")
    README.write_text(readme, encoding="utf-8", newline="\n")
    tables, charts = embedded_stems()
    print(f"{RESULTS.relative_to(ROOT)}: {len(tables)} tables, {len(charts)} charts, {RESULTS.stat().st_size / 1e6:.2f} MB")
    print(f"{README.relative_to(ROOT)}: {len(TABLE_MARKER.findall(readme))} table blocks synced")
    return 0


if __name__ == "__main__":
    sys.exit(main())
