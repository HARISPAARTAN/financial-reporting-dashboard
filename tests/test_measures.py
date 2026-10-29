"""Spec section 10: docs/reconciliation.md lists R1 to R13 with the values of tools/reference.py, and every Desktop
value, once entered, matches within the tolerance: amounts 0.01 EUR, ratios 0.00005, counts exact."""

from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path

import pytest

import reference

DOC = Path(__file__).resolve().parents[1] / "docs" / "reconciliation.md"
# Id | Check | Kind | Definition | Python | Desktop | Difference
ROW = re.compile(r"^\| (R\d+) \| ([^|]+?) \| (amount|count|ratio) \| [^|]+ \| ([^|]+?) \|([^|]*)\|([^|]*)\|$", re.M)
SESSION = re.compile(r"^Desktop session: (.+)$", re.M)
TOLERANCE = {"amount": Decimal("0.01"), "ratio": Decimal("0.00005"), "count": Decimal(0)}


def rows() -> list[tuple[str, str, str, str, str, str]]:
    return [tuple(cell.strip() for cell in row) for row in ROW.findall(DOC.read_text(encoding="utf-8"))]


def number(text: str) -> Decimal:
    return Decimal(text.replace(",", ""))


def matches(kind: str, python: str, desktop: str) -> bool:
    return abs(number(desktop) - number(python)) <= TOLERANCE[kind]


def test_the_table_lists_r1_to_r13_with_the_reference_labels():
    assert [(rid, label, kind) for rid, label, kind, *_ in rows()] == list(reference.CHECKS)


def test_python_column_equals_the_reference(ref):
    values = reference.checks(ref)
    assert {rid: python for rid, _, _, python, _, _ in rows()} == {
        cid: reference.shown(cid, value) for cid, value in values.items()
    }


def test_desktop_values_match_within_the_tolerance():
    entered = [row for row in rows() if row[4]]
    if not entered:
        pytest.skip("Desktop values not read yet")
    assert len(entered) == len(reference.CHECKS), "read all 13 values in one session"
    assert not SESSION.search(DOC.read_text(encoding="utf-8")).group(1).startswith("not yet"), "date the session"
    for rid, _, kind, python, desktop, difference in entered:
        assert matches(kind, python, desktop), (rid, python, desktop)
        assert number(difference) == number(desktop) - number(python), (rid, difference)


@pytest.mark.parametrize(
    ("kind", "python", "desktop", "ok"),
    [
        ("amount", "42245201.08", "42,245,201.08", True),
        ("amount", "42245201.08", "42245201.09", True),
        ("amount", "42245201.08", "42245201.10", False),
        ("count", "6936", "6,936", True),
        ("count", "6936", "6935", False),
        ("ratio", "0.210652", "0.2107", True),
        ("ratio", "0.210652", "0.2106", False),
    ],
)
def test_tolerance_rules(kind, python, desktop, ok):
    assert matches(kind, python, desktop) is ok
