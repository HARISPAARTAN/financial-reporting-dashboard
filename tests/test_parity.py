"""Umbrella section 7: the replica's numbers come from kaldora.json, and kaldora.json equals the reference.

tests/js/pnl.test.mjs recomputes the headline states with web/assets/pnl.js from the facts; this file proves that
the committed file is a fresh build, that its facts are the reference's fact table to the cent and that its headline
agrees with the reference reached along other paths (yearly sums, the matrix columns, the waterfall total).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import build_replica_data as brd
from reference import MONTHS, SCENARIOS, Ctx, period

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def replica() -> dict:
    return json.loads(brd.REPLICA.read_text(encoding="utf-8"))


def close(a: float | None, b: float | None) -> bool:
    return (a is None and b is None) or (a is not None and b is not None and abs(a - b) <= 1e-9)


def test_committed_file_equals_a_fresh_build(ref, tmp_path):
    out = tmp_path / "kaldora.json"
    out.write_bytes(brd.dumps(brd.build(ref)).encode("utf-8"))
    assert out.read_bytes() == brd.REPLICA.read_bytes()


def test_meta_has_the_file_hashes_and_no_timestamps(replica):
    meta = replica["meta"]
    assert meta["seed"] == 43 and meta["lastActual"] == "2025-09" and meta["months"] == MONTHS
    assert sorted(meta["files"]) == sorted(brd.make_data.FILES)
    assert "2026" not in json.dumps(meta)  # the build date is never written
    assert 60_000 <= brd.REPLICA.stat().st_size <= 200_000


def test_facts_equal_the_reference_fact_table_to_the_cent(ref, replica):
    cells = 0
    for row in ref.facts.itertuples():
        assert replica["facts"][row.scenario][f"{row.cost_centre}|{row.account}"][row.t] == row.cents
    for scenario in SCENARIOS:
        for values in replica["facts"][scenario].values():
            assert len(values) == MONTHS
            cells += sum(v is not None for v in values)
    assert cells == len(ref.facts) == 6936


def test_headline_lines_equal_the_reference(ref, replica):
    s1 = replica["headline"]["S1"]["lines"]
    assert s1["REV"]["actual"] == ref.revenue(Ctx(period(2025)))
    assert close(s1["GPM"]["actual"], ref.gross_margin_pct(Ctx(period(2025, 1, 9))))
    assert close(s1["EBITDAM"]["actual"], ref.ebitda_margin_pct(Ctx(period(2025))))
    assert s1["EBITDA"]["budgetClosed"] == ref.budget(Ctx(period(2025, 1, 9), line="EBITDA"))
    assert s1["EBIT"]["fullYearOutlook"] == ref.outlook(Ctx(period(2025), line="EBIT"))
    for key, line in s1.items():
        if line["actual"] is not None and not isinstance(line["actual"], float):
            assert line["variance"] == line["actual"] - line["budgetClosed"], key
    s2 = replica["headline"]["S2"]["lines"]
    assert s2["REV"]["actual"] == ref.revenue(Ctx(period(2024)))
    assert s2["EBITDA"]["budget"] == ref.budget(Ctx(period(2024), line="EBITDA"))


def test_waterfall_and_departments_add_up(replica):
    s1 = replica["headline"]["S1"]
    steps = s1["waterfall"]
    assert steps["REV"] + steps["COS"] + steps["OPEX"] + steps["DA"] == steps["total"]
    assert steps["total"] == s1["lines"]["EBIT"]["variance"]
    assert sum(s1["departments"].values()) == s1["lines"]["EBITDA"]["variance"]
    assert len(s1["departments"]) == 6


def test_matrix_rows_of_s3(ref, replica):
    rows = replica["headline"]["S3"]["rows"]
    top = {r["line"]: r["cells"] for r in rows if r["subgroup"] is None}
    assert list(top) == list(ref.layout)
    ccs = frozenset({"CC10", "CC20"})
    assert top["REV"][12] == ref.actual(Ctx(period(2025, 1, 6), ccs, "REV"))  # YTD: January to June
    assert top["REV"][13] == ref.outlook(Ctx(period(2025), ccs, "REV"))
    assert top["REV"][:3] == [None, None, None] and top["REV"][6:12] == [None] * 6
    revenue = [r for r in rows if r["line"] == "REV" and r["subgroup"] and not r["account"]]
    assert [r["subgroup"] for r in revenue] == ["Contract revenue", "Project and ad-hoc revenue", "Other revenue"]


def test_trend_of_s4_sums_to_the_yearly_values(replica):
    s4, s2 = replica["headline"]["S4"], replica["headline"]["S2"]["lines"]
    assert sum(s4["actual"][12:24]) == s2["EBITDA"]["actual"]
    assert sum(s4["budget"][12:24]) == s2["EBITDA"]["budget"]
    assert s4["actual"][33:] == [None] * 3 and s4["forecast"][:33] == [None] * 33
