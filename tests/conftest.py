"""Shared fixtures: the committed data loaded once, and the hand-computed mini data set (tests/fixtures/mini)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

import reference

ROOT = Path(__file__).resolve().parents[1]
MINI = ROOT / "tests" / "fixtures" / "mini"


@pytest.fixture(scope="session")
def ref() -> reference.Reference:
    return reference.load(ROOT / "data")


@pytest.fixture(scope="session")
def mini() -> reference.Reference:
    """3 accounts, 2 cost centres, January to March 2025: actuals to February, the forecast for March. The budget
    comes as the unpivoted table (natural sign) that src_Budget produces from the workbook."""
    plan = pd.read_csv(MINI / "budget.csv", dtype={"cost_centre": str, "account": str})
    return reference.Reference.from_frames(reference.read_gl(MINI / "gl_actuals.csv"), plan, *reference.read_dims(MINI))
