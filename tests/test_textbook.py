"""Section 5, criterion 8: the textbook model (BUILD_PLAN.md Section 5).

s_par = lambda (1 - R) exactly, the annuity tends to T as the rate and the
hazard go to zero, and the module stands alone: it imports neither the legs
nor the schedule.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from cds import textbook
from cds.conventions import RECOVERY_HY_INDEX, RECOVERY_SENIOR, RECOVERY_SUBORDINATED
from tests.conftest import TEXTBOOK_ABS_TOL

BP_PER_UNIT = 1e4

# The plan's example inputs, and a spread of hazards and recoveries.
CASES = [
    (0.0167, RECOVERY_SENIOR),
    (0.01, RECOVERY_SENIOR),
    (0.08, RECOVERY_HY_INDEX),
    (0.30, RECOVERY_SUBORDINATED),
    (0.0, RECOVERY_SENIOR),
]
RATE = 0.04
MATURITY = 5.0

# "lambda -> 0": a hazard small enough that lambda * T is at float noise.
TINY_HAZARD = 1e-14


@pytest.mark.parametrize("hazard, recovery", CASES)
def test_par_spread_is_the_credit_triangle(hazard: float, recovery: float) -> None:
    assert abs(textbook.par_spread_bp(hazard, recovery) - BP_PER_UNIT * hazard * (1.0 - recovery)) < TEXTBOOK_ABS_TOL
    pv_prot = textbook.protection_pv(hazard, RATE, MATURITY, recovery)
    annuity = textbook.annuity(hazard, RATE, MATURITY)
    assert abs(BP_PER_UNIT * pv_prot / annuity - textbook.par_spread_bp(hazard, recovery)) < TEXTBOOK_ABS_TOL * BP_PER_UNIT
    assert abs(textbook.implied_hazard(textbook.par_spread_bp(hazard, recovery), recovery) - hazard) < TEXTBOOK_ABS_TOL


def test_annuity_tends_to_maturity_as_rate_and_hazard_vanish() -> None:
    assert textbook.annuity(0.0, 0.0, MATURITY) == MATURITY
    assert abs(textbook.annuity(TINY_HAZARD, 0.0, MATURITY) - MATURITY) < TEXTBOOK_ABS_TOL
    assert abs(textbook.annuity(0.0, TINY_HAZARD, MATURITY) - MATURITY) < TEXTBOOK_ABS_TOL
    assert textbook.annuity(0.01, RATE, MATURITY) < MATURITY


def test_closed_forms() -> None:
    hazard, recovery = 0.02, RECOVERY_SENIOR
    k = hazard + RATE
    annuity = (1.0 - math.exp(-k * MATURITY)) / k
    assert abs(textbook.annuity(hazard, RATE, MATURITY) - annuity) < TEXTBOOK_ABS_TOL
    assert abs(textbook.protection_pv(hazard, RATE, MATURITY, recovery) - (1.0 - recovery) * hazard / k * (1.0 - math.exp(-k * MATURITY))) < TEXTBOOK_ABS_TOL
    assert abs(textbook.survival(hazard, MATURITY) - math.exp(-hazard * MATURITY)) < TEXTBOOK_ABS_TOL


def test_upfront_is_zero_at_the_par_spread_and_has_the_buyer_sign() -> None:
    hazard, recovery = 0.05, RECOVERY_HY_INDEX
    s_par = textbook.par_spread_bp(hazard, recovery)
    assert abs(textbook.upfront_pct(hazard, RATE, MATURITY, recovery, s_par)) < TEXTBOOK_ABS_TOL
    assert textbook.upfront_pct(hazard, RATE, MATURITY, recovery, s_par - 100.0) > 0.0
    assert textbook.upfront_pct(hazard, RATE, MATURITY, recovery, s_par + 100.0) < 0.0


def test_rejects_bad_inputs() -> None:
    with pytest.raises(ValueError):
        textbook.annuity(-0.01, RATE, MATURITY)
    with pytest.raises(ValueError):
        textbook.annuity(0.01, RATE, 0.0)
    with pytest.raises(ValueError):
        textbook.protection_pv(0.01, RATE, MATURITY, 1.5)
    with pytest.raises(ValueError):
        textbook.implied_hazard(100.0, 1.0)
    with pytest.raises(ValueError):
        textbook.survival(0.01, -1.0)


def test_textbook_imports_neither_legs_nor_schedule() -> None:
    lines = Path(textbook.__file__).read_text(encoding="utf-8").splitlines()
    imports = [line for line in lines if line.startswith(("import ", "from "))]
    assert imports and all("cds" not in line for line in imports), imports
