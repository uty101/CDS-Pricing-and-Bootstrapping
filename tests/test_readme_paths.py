"""Section 10: the README and the results page (BUILD_PLAN.md Section 10,
criteria 1 to 4, and the session's rules).

Every path the README links or embeds exists; Table 2 is the first table;
the first screen says the curves are illustrative and the library is
validated against QuantLib; every table block in the README is the
committed .md file; the prose is under the word limit. results.html is
what scripts/make_results.py builds from the committed outputs, embeds
every committed table and chart exactly once, is under 5 MB and makes no
external request.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
RESULTS = ROOT / "outputs" / "results.html"
TABLES_DIR = ROOT / "outputs" / "tables"
CHARTS_DIR = ROOT / "outputs" / "charts"

# The session's README rules.
README_MAX_WORDS = 1500  # excluding the tables
FIRST_SCREEN_CHARS = 2000  # criterion 4: "in its first screen"
RESULTS_MAX_BYTES = 5_000_000  # criterion 3

LINK = re.compile(r"!?\[[^\]]*\]\(([^)\s#]+)(?:#[^)]*)?\)")


def _make_results():
    spec = importlib.util.spec_from_file_location("make_results", ROOT / "scripts" / "make_results.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _readme_without_tables(text: str) -> str:
    return _make_results().TABLE_MARKER.sub("", text)


# --- the README ------------------------------------------------------------------


def test_every_readme_path_exists() -> None:
    text = README.read_text(encoding="utf-8")
    paths = [p for p in LINK.findall(text) if not p.startswith(("http://", "https://"))]
    assert paths, "no relative links found"
    missing = [p for p in paths if not (ROOT / p).exists()]
    assert not missing, missing
    # The three chart PNGs are embedded as images.
    images = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", text)
    assert sorted(Path(p).name for p in images) == sorted(p.name for p in CHARTS_DIR.glob("*.png"))


def test_table_2_is_the_first_table_and_the_first_screen_states_the_framing() -> None:
    text = README.read_text(encoding="utf-8")
    m = _make_results()
    blocks = m.TABLE_MARKER.findall(text)
    assert blocks and blocks[0][0] == "table_2_quantlib_validation"
    first_screen = text[: text.index("<!-- table: table_2_quantlib_validation -->")]
    assert len(first_screen) <= FIRST_SCREEN_CHARS
    assert "illustrative" in first_screen and "QuantLib" in first_screen and "validated" in first_screen


def test_readme_table_blocks_are_the_committed_markdown_tables() -> None:
    """The README embeds the committed .md tables verbatim (synced by
    scripts/make_results.py); a block that drifts from its file fails."""
    text = README.read_text(encoding="utf-8")
    m = _make_results()
    assert m.sync_readme(text) == text
    stems = [stem for stem, _ in m.TABLE_MARKER.findall(text)]
    assert len(stems) == len(set(stems))
    for stem, body in m.TABLE_MARKER.findall(text):
        assert body.strip() == (TABLES_DIR / f"{stem}.md").read_text(encoding="utf-8").strip(), stem
    # Every committed table the results page shows but the README does not is the full Table 4 only.
    assert set(p.stem for p in TABLES_DIR.glob("*.md")) - set(stems) == {"table_4_pnl_explain_full"}


def test_readme_prose_is_under_the_word_limit() -> None:
    prose = _readme_without_tables(README.read_text(encoding="utf-8"))
    prose = re.sub(r"```.*?```", "", prose, flags=re.DOTALL)  # the three commands are not prose
    words = len(prose.split())
    assert words <= README_MAX_WORDS, words


def test_readme_has_no_plan_section_headers() -> None:
    """Written for a reader who has not seen the plan: no header names a
    section number or mirrors BUILD_PLAN.md's Part E titles."""
    headers = re.findall(r"^#{1,6} (.+)$", README.read_text(encoding="utf-8"), flags=re.MULTILINE)
    for h in headers:
        assert not re.match(r"Section \d", h), h
        assert not re.search(r"`[a-z_]+\.py`", h), h


# --- the results page -----------------------------------------------------------


def test_results_page_regenerates_to_the_committed_file() -> None:
    m = _make_results()
    fresh = m.build_results_html()
    committed = RESULTS.read_text(encoding="utf-8")
    assert fresh == committed


def test_results_page_embeds_every_committed_table_and_chart_once() -> None:
    m = _make_results()
    page = RESULTS.read_text(encoding="utf-8")
    table_ids = re.findall(r'<table id="([a-z0-9_]+)">', page)
    image_ids = re.findall(r'<img id="([a-z0-9_]+)" src="data:image/png;base64,', page)
    assert sorted(table_ids) == sorted(p.stem for p in TABLES_DIR.glob("*.md"))
    assert sorted(image_ids) == sorted(p.stem for p in CHARTS_DIR.glob("*.png"))
    assert len(table_ids) == len(set(table_ids)) and len(image_ids) == len(set(image_ids))
    tables, charts = m.embedded_stems()
    assert table_ids == tables and image_ids == charts
    # The README's order: Table 2 first, then Table 3 and Chart 2, Table 5, Table 4 and Chart 3, Table 1 and Chart 1.
    assert table_ids[0] == "table_2_quantlib_validation" and tables.index("table_3_risk_report") < tables.index("table_5_isda_vs_textbook") < tables.index("table_4_pnl_explain") < tables.index("table_1_hazard_curves")
    # Every table's rows are the committed .md file's rows.
    for stem in table_ids:
        header, rows = m.parse_markdown_table((TABLES_DIR / f"{stem}.md").read_text(encoding="utf-8"))
        assert page.count(f"outputs/tables/{stem}.csv, {len(rows)} rows") == 1


def test_results_page_is_self_contained() -> None:
    page = RESULTS.read_text(encoding="utf-8")
    assert RESULTS.stat().st_size <= RESULTS_MAX_BYTES
    assert "<script" not in page.lower()
    srcs = re.findall(r'src="([^"]+)"', page)
    assert srcs and all(s.startswith("data:image/png;base64,") for s in srcs)
    hrefs = re.findall(r'href="([^"]+)"', page)
    assert hrefs == [_make_results().REPO_URL]  # the one external link the plan allows
    assert "<link" not in page.lower() and "@import" not in page and "url(" not in page


def test_results_page_check_mode_passes_on_the_committed_files() -> None:
    assert _make_results().main(["--check"]) == 0


# --- housekeeping the section closes -----------------------------------------------


def test_package_docstring_lists_the_public_objects() -> None:
    import cds

    doc = cds.__doc__
    assert "None exist yet" not in doc
    for name in ("price", "bootstrap", "risk", "explain", "run", "CDSTrade", "MarketState", "PriceResult", "RiskReport", "ExplainResult"):
        assert name in doc, name


def test_stray_docx_is_ignored_not_tracked() -> None:
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "/11_CDS_Pricing_Bootstrap.docx" in ignore
