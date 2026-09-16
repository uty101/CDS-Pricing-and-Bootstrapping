"""Section 1, criterion 7: repo hygiene.

Two checks. Every tracked text file is free of the five words CLAUDE.md
bans, except the sentence in CLAUDE.md that states the ban. And no module
under cds/ or scripts/ other than cds/conventions.py carries a day-count
basis or a recovery level as a literal; those come from conventions.py.
Test files are the independent oracle and are allowed literals.
"""

from __future__ import annotations

import re
import subprocess
import tokenize
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# Assembled from fragments so this file does not itself contain the words.
BANNED = tuple("".join(parts) for parts in [("rob", "ust"), ("resil", "ient"), ("rigor", "ous"), ("lever", "age"), ("ground", "ed")])
BANNED_RE = re.compile("|".join(BANNED), re.IGNORECASE)
RULE_SENTENCE = "Do not use the words"

TEXT_SUFFIXES = {".md", ".py", ".toml", ".csv", ".json", ".txt", ".cfg", ".ini", ".yml", ".yaml", ".html", ".gitignore", ""}
BINARY_SUFFIXES = {".docx", ".png", ".lock", ".pdf"}

# Literals that belong only in cds/conventions.py: a division by 360 or 365,
# an assignment of 360 or 365, or an assignment of a recovery level. Applied
# to code tokens only; strings and comments may name a day count in prose.
CONVENTION_LITERAL_RE = re.compile(r"(/\s*36[05]\b)|(=\s*36[05]\b)|(=\s*0\.(40|25|20)\b)")


def code_lines(path: Path) -> dict[int, str]:
    """Source lines with string and comment tokens removed."""
    out: dict[int, list[str]] = {}
    with path.open("rb") as fh:
        for tok in tokenize.tokenize(fh.readline):
            if tok.type in (tokenize.STRING, tokenize.COMMENT, tokenize.ENCODING):
                continue
            out.setdefault(tok.start[0], []).append(tok.string)
    return {n: " ".join(parts) for n, parts in out.items()}


def tracked_files() -> list[Path]:
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return [ROOT / line for line in out.splitlines() if line]


def test_no_banned_words_in_tracked_text_files() -> None:
    hits: list[str] = []
    for path in tracked_files():
        if path.suffix in BINARY_SUFFIXES or path.suffix not in TEXT_SUFFIXES:
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if RULE_SENTENCE in line and path.name == "CLAUDE.md":
                continue
            if BANNED_RE.search(line):
                hits.append(f"{path.relative_to(ROOT)}:{lineno}: {line.strip()}")
    assert not hits, "\n".join(hits)


@pytest.mark.parametrize("folder", ["cds", "scripts"])
def test_conventions_are_not_hard_coded_outside_conventions_py(folder: str) -> None:
    hits: list[str] = []
    for path in sorted((ROOT / folder).rglob("*.py")):
        if path.name == "conventions.py":
            continue
        for lineno, code in sorted(code_lines(path).items()):
            if CONVENTION_LITERAL_RE.search(code):
                hits.append(f"{path.relative_to(ROOT)}:{lineno}: {code.strip()}")
    assert not hits, "\n".join(hits)
