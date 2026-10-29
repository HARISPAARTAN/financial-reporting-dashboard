"""Optional: parse the TMDL folders with Microsoft's own TmdlSerializer (the parser Desktop uses).

Skipped unless build/tom/ holds the TOM client (tools/pbi/copy_tom.py) and pythonnet with a .NET runtime is
available (uv sync --group pbi). A TMDL syntax error fails here with the file, line and reason; Model.Validate()
reports semantic errors (unknown columns in DAX, broken sort-by columns, invalid relationships).
"""

import sys
from pathlib import Path

import pytest

import make_public_variant
from pbir import PROJECT

pytestmark = [pytest.mark.pbi, pytest.mark.tom]
ROOT = Path(__file__).resolve().parents[2]
LIB = ROOT / "build" / "tom"
PBIP = ROOT / PROJECT["folder"] / f"{PROJECT['name']}.pbip"
MODEL = PBIP.parent / f"{PROJECT['name']}.SemanticModel" / "definition"
TABLES = {
    "FactGL",
    "DimDate",
    "DimAccount",
    "DimPnLLine",
    "DimCostCentre",
    "DimScenario",
    "Security",
    "PnLColumn",
    "ReconCheck",
    "_Measures",
}


@pytest.fixture(scope="module")
def serializer():
    if not (LIB / "Microsoft.AnalysisServices.Tabular.dll").exists():
        pytest.skip("TOM client not in build/tom (uv run python tools/pbi/copy_tom.py --from <folder>)")
    try:
        from pythonnet import load

        try:
            load("coreclr")
        except RuntimeError:
            pass  # a runtime is already loaded in this process
        import clr
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"pythonnet or the .NET runtime is not available: {exc}")
    sys.path.append(str(LIB))
    clr.AddReference(str(LIB / "Microsoft.AnalysisServices.Tabular.dll"))
    from Microsoft.AnalysisServices.Tabular import TmdlSerializer

    return TmdlSerializer


def _errors(db) -> list[str]:
    result = db.Model.Validate()
    return [str(e.Message) for e in result.Errors] if result.ContainsErrors else []


def test_tom_parses_and_validates_the_model(serializer):
    db = serializer.DeserializeDatabaseFromFolder(str(MODEL))
    assert {t.Name for t in db.Model.Tables} == TABLES
    assert db.CompatibilityLevel == 1606
    assert len(list(db.Model.Relationships)) == 5
    assert _errors(db) == []


def test_tom_reads_the_measures_and_the_role(serializer):
    db = serializer.DeserializeDatabaseFromFolder(str(MODEL))
    tables = {t.Name: t for t in db.Model.Tables}
    measures = list(tables["_Measures"].Measures)
    assert len(measures) == 36
    assert all(str(m.Description) for m in measures)
    dynamic = {m.Name for m in measures if m.FormatStringDefinition is not None}
    assert dynamic == {
        "P&L Value",
        "P&L Statement",
        "P&L Matrix",
        "Actual",
        "Budget",
        "Forecast",
        "Outlook",
        "Budget (closed months)",
        "Variance",
        "Outlook vs budget",
        "Actual YTD",
        "Budget YTD",
        "Outlook YTD",
        "Full-year outlook",
        "Budget full year",
        "Check value",
    }
    assert str(tables["DimDate"].DataCategory) == "Time"
    roles = {r.Name: r for r in db.Model.Roles}
    assert list(roles) == ["Department head"]
    assert {p.Table.Name for p in roles["Department head"].TablePermissions} == {"Security", "DimCostCentre"}


def test_tom_parses_the_public_variant(serializer, tmp_path):
    pbip = make_public_variant.build(PBIP, tmp_path)
    folder = pbip.parent / pbip.name.replace(".pbip", ".SemanticModel") / "definition"
    db = serializer.DeserializeDatabaseFromFolder(str(folder))
    assert {t.Name for t in db.Model.Tables} == TABLES - {"Security"}
    assert len(list(db.Model.Roles)) == 0
    assert _errors(db) == []
