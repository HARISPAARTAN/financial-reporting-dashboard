"""The committed data files: determinism, structure, the bands and the seven events of spec section 4.6."""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import re
import zipfile
from pathlib import Path

import pandas as pd
import pytest
from openpyxl import load_workbook

import make_data
import reference
from reference import Ctx, period

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
WORKBOOK = DATA / "budget.xlsx"
SHEETS = ["Budget 2023", "Budget 2024", "Budget 2025", "Forecast 2025"]


def read_csv(name: str) -> list[dict[str, str]]:
    with (DATA / name).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def natural(ref: reference.Reference, scenario: str, pairs: list[tuple[str, str]], months: range) -> int:
    """Natural-sign sum in cents (revenue and costs positive) of some pairs and month indices."""
    total = 0
    for cc, acc in pairs:
        sign = int(ref.accounts.set_index("account").loc[acc, "sign"])
        value = ref.amount({(scenario, t) for t in months}, frozenset({cc}), {acc})
        total += (value or 0) * sign
    return total


# ---------------------------------------------------------------- determinism and files


def test_check_matches_a_fresh_build(capsys: pytest.CaptureFixture[str]) -> None:
    assert make_data.main(["--check"]) == 0
    assert "matches a fresh build" in capsys.readouterr().out


def test_two_runs_give_the_same_bytes(tmp_path: Path) -> None:
    for run in ("a", "b"):
        make_data.generate(tmp_path / run)
    for name in make_data.FILES:
        digests = {hashlib.sha256((tmp_path / run / name).read_bytes()).hexdigest() for run in ("a", "b")}
        assert len(digests) == 1, name


def test_workbook_entries_record_no_platform(tmp_path: Path) -> None:
    make_data.generate(tmp_path)
    for path in (WORKBOOK, tmp_path / "budget.xlsx"):
        with zipfile.ZipFile(path) as archive:
            assert {item.create_system for item in archive.infolist()} == {0}, path


def test_six_small_files_utf8_lf_without_bom() -> None:
    assert sorted(p.name for p in DATA.iterdir()) == sorted(make_data.FILES)
    for path in DATA.iterdir():
        assert path.stat().st_size <= 2_000_000, path.name
    for path in DATA.glob("*.csv"):
        raw = path.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf") and b"\r" not in raw, path.name
        raw.decode("utf-8")


def test_row_counts(ref: reference.Reference) -> None:
    gl = read_csv("gl_actuals.csv")
    assert len(gl) == 3178
    assert sorted({r["period"] for r in gl}) == [f"{y}-{m:02d}" for y in (2023, 2024, 2025) for m in range(1, 13)][:33]
    assert ref.facts["scenario"].value_counts().to_dict() == {"Actual": 3178, "Budget": 3468, "Forecast": 290}
    assert len(ref.facts) == 6936


def test_workbook_layout() -> None:
    wb = load_workbook(WORKBOOK)
    assert wb.sheetnames == SHEETS
    for name in SHEETS:
        ws = wb[name]
        months = make_data.MONTH_NAMES if name.startswith("Budget") else make_data.MONTH_NAMES[9:]
        total = "FY" if name.startswith("Budget") else "Q4"
        assert ws["A1"].value == f"Kaldora Facility Services · {name}"
        assert ws["A2"].value == "EUR · revenue and costs as positive amounts · revenue reductions negative"
        assert all(c.value is None for c in ws[3])
        assert [c.value for c in ws[4]] == ["Cost centre", "Account", "Account name", *months, total]
        assert ws.max_row == 103 and ws["A103"].value == "Total"
        last = ws.cell(row=4, column=3 + len(months)).column_letter
        assert ws.cell(row=5, column=4 + len(months)).value == f"=SUM(D5:{last}5)"
        assert ws.cell(row=103, column=4).value == "=SUM(D5:D102)"
        pairs = [(ws.cell(row=r, column=1).value, ws.cell(row=r, column=2).value) for r in range(5, 103)]
        assert pairs == list(make_data.POSTING)
        for row in ws.iter_rows(min_row=5, max_row=102, min_col=4, max_col=3 + len(months), values_only=True):
            assert all(v is None or (isinstance(v, int) and v != 0 and v % 100 == 0) for v in row)
    assert wb.properties.created == wb.properties.modified == dt.datetime(2025, 10, 6, 0, 0)


def test_workbook_zip_is_stored_with_fixed_times_and_formulas_without_values() -> None:
    with zipfile.ZipFile(WORKBOOK) as archive:
        for info in archive.infolist():
            assert info.compress_type == zipfile.ZIP_STORED, info.filename
            assert info.date_time == (2025, 10, 6, 0, 0, 0), info.filename
        sheet = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
    assert sheet.count("<f>") == 98 + 13 and "<v></v>" not in sheet
    assert not re.search(r"</f><v>", sheet)  # no cached formula values


def test_budget_reader_gives_98_rows_per_sheet() -> None:
    plan = reference.read_budget(WORKBOOK)
    sheets = pd.read_excel(WORKBOOK, sheet_name=None, header=3, dtype={"Cost centre": str, "Account": str})
    assert {name: int(s["Cost centre"].str.startswith("CC").sum()) for name, s in sheets.items()} == dict.fromkeys(
        SHEETS, 98
    )
    assert plan.groupby(["scenario", "year"]).size().to_dict() == {
        ("Budget", 2023): 1156,
        ("Budget", 2024): 1156,
        ("Budget", 2025): 1156,
        ("Forecast", 2025): 290,
    }


# ---------------------------------------------------------------- master data


def test_posting_map_and_the_ledger_pairs() -> None:
    assert len(make_data.POSTING) == 98 and len(set(make_data.POSTING)) == 98
    by_period: dict[str, set[tuple[str, str]]] = {}
    for r in read_csv("gl_actuals.csv"):
        by_period.setdefault(r["period"], set()).add((r["cost_centre"], r["account"]))
    for key, pairs in by_period.items():
        month = int(key[5:])
        expected = {
            p for p in make_data.POSTING if (p[1] != "6310" or month in (3, 9, 10)) and (p[1] != "6450" or month == 12)
        }
        assert pairs == expected, key


def test_chart_of_accounts_and_layout() -> None:
    accounts = read_csv("chart_of_accounts.csv")
    layout = read_csv("pnl_layout.csv")
    assert len(accounts) == 40 and [int(a["sort_order"]) for a in accounts] == list(range(1, 41))
    assert len({a["subgroup"] for a in accounts}) == 13
    groups = {r["group"]: int(r["sign"]) for r in layout if r["line_type"] == "Group"}
    for a in accounts:
        assert a["group"] in groups and int(a["sign"]) == groups[a["group"]], a["account"]
    assert [(r["line_key"], r["line_type"], r["bound"], r["sign"]) for r in layout] == [
        ("REV", "Group", "", "1"),
        ("COS", "Group", "", "-1"),
        ("GP", "Subtotal", "30", "1"),
        ("GPM", "Ratio", "30", "1"),
        ("OPEX", "Group", "", "-1"),
        ("EBITDA", "Subtotal", "50", "1"),
        ("EBITDAM", "Ratio", "50", "1"),
        ("DA", "Group", "", "-1"),
        ("EBIT", "Subtotal", "70", "1"),
        ("EBITM", "Ratio", "70", "1"),
    ]


def test_cost_centres_heads_and_security() -> None:
    centres = read_csv("cost_centres.csv")
    security = read_csv("security.csv")
    assert [(c["cost_centre"], c["name"], c["type"]) for c in centres] == list(make_data.COST_CENTRES)
    pattern = re.compile(r"[a-z]+\.[a-z]+@kaldora\.example")
    emails = [c["head_email"] for c in centres] + [s["user_email"] for s in security]
    assert all(pattern.fullmatch(e) for e in emails), emails
    assert len(security) == 10
    assert {(s["user_email"], s["cost_centre"]) for s in security[:6]} == {
        (c["head_email"], c["cost_centre"]) for c in centres
    }
    operations = {s["user_email"] for s in security[6:]}
    assert len(operations) == 1 and operations.isdisjoint(c["head_email"] for c in centres)
    assert [s["cost_centre"] for s in security[6:]] == ["CC10", "CC20", "CC30", "CC40"]


def test_no_phone_numbers_or_street_addresses() -> None:
    phone = re.compile(r"\+\d{2}|\(\d{2,4}\)|\b\d{3,4}[ /-]\d{4,}\b")
    street = re.compile(r"(?i)\b(stra(ss|ß)e|gasse|street|road|avenue|platz|weg)\b")
    for path in DATA.glob("*.csv"):
        text = path.read_text(encoding="utf-8")
        assert not phone.search(text), path.name
        assert not street.search(text), path.name


# ---------------------------------------------------------------- bands (spec 4.6)

YEARS = {2023: period(2023), 2024: period(2024), 2025: period(2025, 1, 9)}  # 2025: the closed months


@pytest.mark.parametrize("year", [2023, 2024, 2025])
def test_band_revenue_and_ebitda_against_budget(ref: reference.Reference, year: int) -> None:
    months = YEARS[year]
    revenue = ref.actual(Ctx(months, line="REV")) / ref.budget(Ctx(months, line="REV")) - 1
    assert -0.03 <= revenue <= 0.03
    for cc in ("CC10", "CC20", "CC30", "CC40"):
        ctx = Ctx(months, frozenset({cc}), "REV")
        assert -0.06 <= ref.actual(ctx) / ref.budget(ctx) - 1 <= 0.06, cc
    ebitda = ref.actual(Ctx(months, line="EBITDA")) / ref.budget(Ctx(months, line="EBITDA")) - 1
    assert -0.25 <= ebitda <= 0.25


def test_band_ebitda_jan_to_sep_2025_below_budget(ref: reference.Reference) -> None:
    assert ref.variance(Ctx(YEARS[2025], line="EBITDA")) < 0


@pytest.mark.parametrize("year", [2023, 2024, 2025])
def test_band_margins_and_personnel(ref: reference.Reference, year: int) -> None:
    ctx = Ctx(YEARS[year])
    assert 0.19 <= ref.gross_margin_pct(ctx) <= 0.26
    assert 0.04 <= ref.ebitda_margin_pct(ctx) <= 0.09
    assert 0.66 <= ref.personnel_pct(ctx) <= 0.75


# ---------------------------------------------------------------- events (actuals only)

WAGES = [(cc, acc) for cc, acc in make_data.POSTING if acc in ("5000", "5010", "5020", "6000", "6010")]


def test_e1_wage_round_2024(ref: reference.Reference) -> None:
    assert natural(ref, "Actual", WAGES, range(12, 24)) > natural(ref, "Budget", WAGES, range(12, 24))


def test_e2_erp_migration(ref: reference.Reference) -> None:
    for t in (21, 22):
        diff = natural(ref, "Actual", [("CC80", "6410")], range(t, t + 1)) - natural(
            ref, "Budget", [("CC80", "6410")], range(t, t + 1)
        )
        assert diff > 5_000_000, t  # more than EUR 50,000
    it = [("CC80", "6200")]
    assert natural(ref, "Actual", it, range(21, 24)) > 1.1 * natural(ref, "Budget", it, range(21, 24))


def test_e3_bad_debt_december_2024(ref: reference.Reference) -> None:
    assert natural(ref, "Actual", [("CC80", "6450")], range(23, 24)) == 8_500_000
    assert natural(ref, "Budget", [("CC80", "6450")], range(23, 24)) == 2_580_000


def test_e4_food_prices_2025(ref: reference.Reference) -> None:
    food = [("CC40", "5120")]
    assert natural(ref, "Actual", food, range(25, 33)) > 1.03 * natural(ref, "Budget", food, range(25, 33))


def test_e5_lost_cleaning_contract(ref: reference.Reference) -> None:
    contract = [("CC10", "4000")]
    assert natural(ref, "Actual", contract, range(27, 33)) < 0.97 * natural(ref, "Budget", contract, range(27, 33))
    staff = [("CC10", acc) for acc in ("5000", "5010", "5020")]
    assert natural(ref, "Actual", staff, range(29, 33)) < 0.97 * natural(ref, "Budget", staff, range(29, 33))


def test_e6_summer_event_contracts(ref: reference.Reference) -> None:
    for acc, floor in (("4120", 1.3), ("5010", 1.15), ("5030", 1.1)):
        pair = [("CC30", acc)]
        assert natural(ref, "Actual", pair, range(29, 32)) > floor * natural(ref, "Budget", pair, range(29, 32)), acc


def test_e7_extra_vans(ref: reference.Reference) -> None:
    vans = [("CC20", "7000")]
    assert natural(ref, "Actual", vans, range(27, 33)) > 1.05 * natural(ref, "Budget", vans, range(27, 33))


def test_forecast_follows_the_rule(ref: reference.Reference) -> None:
    for pair in make_data.POSTING:
        a_ytd = natural(ref, "Actual", [pair], range(24, 33))
        b_ytd = natural(ref, "Budget", [pair], range(24, 33))
        factor = make_data.FORECAST_FULL.get(pair)
        if factor is None:
            factor = 1.0 if pair in make_data.FORECAST_PLAIN or b_ytd == 0 else 1 + 0.5 * (a_ytd / b_ytd - 1)
        for t in range(33, 36):
            budget = natural(ref, "Budget", [pair], range(t, t + 1))
            forecast = natural(ref, "Forecast", [pair], range(t, t + 1))
            assert forecast == make_data.round_hundreds(budget / 100 * factor) * 100, (pair, t)
