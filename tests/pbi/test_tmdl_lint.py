"""Offline lint of the TMDL model against spec sections 4.3 to 4.5, 2 and 7: tables, columns, relationships,
parameters, staging queries, measures, the role and the reconciliation checks."""

import re
from pathlib import Path

import pytest

import reference
from pbir import PROJECT
from tmdl import load_model

pytestmark = pytest.mark.pbi
MODEL_DIR = Path(__file__).resolve().parents[2] / PROJECT["folder"] / f"{PROJECT['name']}.SemanticModel" / "definition"
H = True  # hidden
# table -> column -> (data type, hidden, sort-by column)
COLUMNS = {
    "FactGL": {
        "Date": ("dateTime", H, None),
        "Cost centre": ("string", H, None),
        "Account": ("string", H, None),
        "Scenario": ("string", H, None),
        "Amount": ("decimal", H, None),
    },
    "DimDate": {
        "Date": ("dateTime", False, None),
        "Year": ("int64", False, None),
        "Quarter": ("string", False, None),
        "Month number": ("int64", False, None),
        "Month": ("string", False, "Month number"),
        "Month start": ("dateTime", False, None),
        "Year-month": ("string", False, None),
    },
    "DimAccount": {
        "Account": ("string", H, None),
        "Account name": ("string", False, None),
        "Account label": ("string", False, "Sort"),
        "Group": ("string", False, "Group sort"),
        "Group sort": ("int64", H, None),
        "Subgroup": ("string", False, "Subgroup sort"),
        "Subgroup sort": ("int64", H, None),
        "Sign": ("int64", H, None),
        "Sort": ("int64", H, None),
        "Line key": ("string", H, None),
    },
    "DimPnLLine": {
        "Line key": ("string", H, None),
        "Line": ("string", False, "Sort"),
        "Line type": ("string", False, None),
        "Group": ("string", H, None),
        "Bound": ("int64", H, None),
        "Sign": ("int64", H, None),
        "Sort": ("int64", H, None),
    },
    "DimCostCentre": {
        "Cost centre": ("string", H, None),
        "Name": ("string", False, "Sort"),
        "Type": ("string", False, None),
        "Head name": ("string", False, None),
        "Head email": ("string", False, None),
        "Sort": ("int64", H, None),
    },
    "DimScenario": {"Scenario": ("string", False, "Scenario sort"), "Scenario sort": ("int64", H, None)},
    "Security": {"User email": ("string", False, None), "Cost centre": ("string", False, None)},
    "PnLColumn": {"Column": ("string", False, "Sort"), "Sort": ("int64", H, None)},
    "ReconCheck": {
        "Id": ("string", False, "Sort"),
        "Label": ("string", False, None),
        "Kind": ("string", False, None),
        "Sort": ("int64", H, None),
    },
    "_Measures": {"Anchor": ("int64", H, None)},
}
RELATIONSHIPS = {
    ("FactGL.Date", "DimDate.Date"),
    ("FactGL.Account", "DimAccount.Account"),
    ("FactGL.Cost centre", "DimCostCentre.Cost centre"),
    ("FactGL.Scenario", "DimScenario.Scenario"),
    ("DimAccount.Line key", "DimPnLLine.Line key"),
}
STAGING = {
    "src_GL": "gl_actuals.csv",
    "src_Budget": "budget.xlsx",
    "src_Accounts": "chart_of_accounts.csv",
    "src_CostCentres": "cost_centres.csv",
    "src_Layout": "pnl_layout.csv",
    "src_Security": "security.csv",
}
AMOUNT = 'IF([Is ratio line], "0.0 %", "#,0,;(#,0,);0")'
VARIANCE = 'IF([Is ratio line], "+0.0"" pp"";-0.0"" pp"";0.0"" pp""", "+#,0,;-#,0,;0")'
CHECK = 'SWITCH(SELECTEDVALUE(ReconCheck[Kind]), "ratio", "0.0000", "count", "#,0", "#,0.00")'
TEXT = None  # a text result has no format string
# measure -> (display folder, format string, or AMOUNT / VARIANCE / CHECK for a format string definition, hidden)
MEASURES = {
    "Amount": ("Base", "#,0.00", False),
    "Last actual date": ("Base", "d mmm yyyy", False),
    "Is ratio line": ("Base", '"TRUE";"TRUE";"FALSE"', False),
    "Line sign": ("Base", "0", False),
    "P&L Value": ("Base", AMOUNT, False),
    "Actual": ("Scenarios", AMOUNT, False),
    "Budget": ("Scenarios", AMOUNT, False),
    "Forecast": ("Scenarios", AMOUNT, False),
    "Outlook": ("Scenarios", AMOUNT, False),
    "Budget (closed months)": ("Scenarios", AMOUNT, False),
    "P&L Statement": ("Scenarios", AMOUNT, False),
    "P&L Matrix": ("Scenarios", AMOUNT, False),
    "Variance": ("Variance", VARIANCE, False),
    "Variance %": ("Variance", "+0.0 %;-0.0 %;0.0 %", False),
    "Favourable": ("Variance", "0", False),
    "Profit impact": ("Variance", "+#,0,;-#,0,;0", False),
    "Outlook vs budget": ("Variance", VARIANCE, False),
    "Favourable label": ("Variance", TEXT, False),
    "Actual YTD": ("Time", AMOUNT, False),
    "Budget YTD": ("Time", AMOUNT, False),
    "Outlook YTD": ("Time", AMOUNT, False),
    "Full-year outlook": ("Time", AMOUNT, False),
    "Budget full year": ("Time", AMOUNT, False),
    "Revenue": ("Lines", "#,0,;(#,0,);0", False),
    "Gross margin %": ("Lines", "0.0 %", False),
    "EBITDA margin %": ("Lines", "0.0 %", False),
    "Opex % of revenue": ("Lines", "0.0 %", False),
    "Personnel cost": ("Lines", "#,0,;(#,0,);0", False),
    "Personnel cost % of revenue": ("Lines", "0.0 %", False),
    "Favourable colour": ("Formatting", TEXT, H),
    "Row tint": ("Formatting", TEXT, H),
    "Rows": ("Info", "#,0", False),
    "Data as of": ("Info", TEXT, False),
    "Selected department": ("Info", TEXT, False),
    "Department head": ("Info", TEXT, False),
    "Check value": ("Info", CHECK, H),
}
DEFINITIONS = {  # spec section 7, flattened
    "Amount": "SUM(FactGL[Amount])",
    "Last actual date": 'EOMONTH(CALCULATE(MAX(FactGL[Date]), REMOVEFILTERS(), DimScenario[Scenario] = "Actual"), 0)',
    "Is ratio line": 'SELECTEDVALUE(DimPnLLine[Line type]) = "Ratio"',
    "Line sign": "SELECTEDVALUE(DimPnLLine[Sign], 1)",
    "P&L Value": (
        "VAR _type = SELECTEDVALUE(DimPnLLine[Line type]) VAR _bound = SELECTEDVALUE(DimPnLLine[Bound]) "
        "VAR _detail = ISINSCOPE(DimAccount[Subgroup]) || ISINSCOPE(DimAccount[Account label]) "
        "VAR _upTo = CALCULATE([Amount], REMOVEFILTERS(DimPnLLine), DimAccount[Group sort] < _bound) "
        'VAR _rev = CALCULATE([Amount], REMOVEFILTERS(DimPnLLine), DimPnLLine[Line key] = "REV") '
        'RETURN SWITCH(_type, "Group", [Amount] * [Line sign], "Subtotal", IF(NOT _detail, _upTo), '
        '"Ratio", IF(NOT _detail, DIVIDE(_upTo, _rev)), [Amount])'
    ),
    "Actual": 'CALCULATE([P&L Value], DimScenario[Scenario] = "Actual")',
    "Budget": 'CALCULATE([P&L Value], DimScenario[Scenario] = "Budget")',
    "Forecast": 'CALCULATE([P&L Value], DimScenario[Scenario] = "Forecast")',
    "Outlook": (
        "VAR _last = [Last actual date] VAR _cells = FILTER(CROSSJOIN(ALL(DimScenario[Scenario]), "
        'VALUES(DimDate[Date])), (DimScenario[Scenario] = "Actual" && DimDate[Date] <= _last) '
        '|| (DimScenario[Scenario] = "Forecast" && DimDate[Date] > _last)) RETURN CALCULATE([P&L Value], _cells)'
    ),
    "Budget (closed months)": (
        "VAR _last = [Last actual date] "
        "RETURN CALCULATE([Budget], FILTER(VALUES(DimDate[Date]), DimDate[Date] <= _last))"
    ),
    "P&L Statement": (
        'SWITCH(SELECTEDVALUE(DimScenario[Scenario], "Actual"), "Budget", [Budget], "Forecast", [Outlook], [Actual])'
    ),
    "P&L Matrix": (
        "VAR _col = SELECTEDVALUE(PnLColumn[Sort]) RETURN SWITCH(TRUE(), ISBLANK(_col), BLANK(), "
        "_col <= 12, CALCULATE([P&L Statement], KEEPFILTERS(DimDate[Month number] = _col)), "
        "_col = 13, CALCULATE([P&L Statement], DATESYTD(DimDate[Date])), "
        'IF(SELECTEDVALUE(DimScenario[Scenario], "Actual") = "Budget", [Budget full year], [Full-year outlook]))'
    ),
    "Variance": (
        "VAR _a = [Actual] VAR _b = [Budget (closed months)] "
        "RETURN IF(NOT (ISBLANK(_a) && ISBLANK(_b)), (_a - _b) * IF([Is ratio line], 100, 1))"
    ),
    "Variance %": "IF(NOT [Is ratio line], DIVIDE([Variance], ABS([Budget (closed months)])))",
    "Favourable": (
        "VAR _v = [Variance] VAR _p = [Variance %] "
        "VAR _neutral = IF([Is ratio line], ABS(_v) < 0.1, NOT ISBLANK(_p) && ABS(_p) < 0.01) "
        "RETURN IF(NOT ISBLANK(_v), IF(_neutral, 0, SIGN(_v * [Line sign])))"
    ),
    "Profit impact": "IF(NOT [Is ratio line], [Variance] * [Line sign])",
    "Outlook vs budget": "([Full-year outlook] - [Budget full year]) * IF([Is ratio line], 100, 1)",
    "Favourable label": (
        'VAR _f = [Favourable] RETURN IF(NOT ISBLANK(_f), SWITCH(_f, 1, "Fav.", -1, "Unfav.", "On plan"))'
    ),
    "Actual YTD": "IF(MIN(DimDate[Date]) <= [Last actual date], CALCULATE([Actual], DATESYTD(DimDate[Date])))",
    "Budget YTD": "CALCULATE([Budget], DATESYTD(DimDate[Date]))",
    "Outlook YTD": "CALCULATE([Outlook], DATESYTD(DimDate[Date]))",
    "Full-year outlook": (
        "VAR _y = MAX(DimDate[Year]) RETURN CALCULATE([Outlook], REMOVEFILTERS(DimDate), DimDate[Year] = _y)"
    ),
    "Budget full year": (
        "VAR _y = MAX(DimDate[Year]) RETURN CALCULATE([Budget], REMOVEFILTERS(DimDate), DimDate[Year] = _y)"
    ),
    "Revenue": 'CALCULATE([Actual], REMOVEFILTERS(DimPnLLine), DimPnLLine[Line key] = "REV")',
    "Gross margin %": 'CALCULATE([Actual], REMOVEFILTERS(DimPnLLine), DimPnLLine[Line key] = "GPM")',
    "EBITDA margin %": 'CALCULATE([Actual], REMOVEFILTERS(DimPnLLine), DimPnLLine[Line key] = "EBITDAM")',
    "Opex % of revenue": (
        'DIVIDE(CALCULATE([Actual], REMOVEFILTERS(DimPnLLine), DimPnLLine[Line key] = "OPEX"), [Revenue])'
    ),
    "Personnel cost": (
        'CALCULATE(-[Amount], REMOVEFILTERS(DimPnLLine), DimScenario[Scenario] = "Actual", '
        'DimAccount[Subgroup] IN {"Direct personnel", "Overhead personnel"})'
    ),
    "Personnel cost % of revenue": "DIVIDE([Personnel cost], [Revenue])",
    "Rows": "COUNTROWS(FactGL)",
    "Selected department": 'SELECTEDVALUE(DimCostCentre[Name], "All departments")',
    "Department head": "SELECTEDVALUE(DimCostCentre[Head name])",
}
ROLE = {
    "Security": "Security[User email] = LOWER(USERPRINCIPALNAME())",
    "DimCostCentre": (
        "DimCostCentre[Cost centre] IN CALCULATETABLE(VALUES(Security[Cost centre]), "
        "Security[User email] = LOWER(USERPRINCIPALNAME()))"
    ),
}
# the filters of each reconciliation branch (spec section 10), on one line
CHECK_BRANCHES = {
    "R1": "CALCULATE([Rows], REMOVEFILTERS())",
    "R2": "CALCULATE([Revenue], REMOVEFILTERS(), DimDate[Year] = 2023)",
    "R3": 'CALCULATE([Actual], REMOVEFILTERS(), DimDate[Year] = 2024, DimPnLLine[Line key] = "EBITDA")',
    "R4": (
        "CALCULATE([Actual], REMOVEFILTERS(), DimDate[Year] = 2025, DimDate[Month number] <= 9, "
        'DimPnLLine[Line key] = "EBIT")'
    ),
    "R5": "CALCULATE([Gross margin %], REMOVEFILTERS(), DimDate[Year] = 2025, DimDate[Month number] <= 9)",
    "R6": 'CALCULATE([Budget], REMOVEFILTERS(), DimDate[Year] = 2025, DimPnLLine[Line key] = "REV")',
    "R7": 'CALCULATE([Budget (closed months)], REMOVEFILTERS(), DimDate[Year] = 2025, DimPnLLine[Line key] = "EBITDA")',
    "R8": 'CALCULATE([Forecast], REMOVEFILTERS(), DimDate[Year] = 2025, DimPnLLine[Line key] = "REV")',
    "R9": 'CALCULATE([Full-year outlook], REMOVEFILTERS(), DimDate[Year] = 2025, DimPnLLine[Line key] = "EBIT")',
    "R10": (
        "CALCULATE([Variance], REMOVEFILTERS(), DimDate[Year] = 2025, DimDate[Month number] <= 9, "
        'DimPnLLine[Line key] = "EBITDA", DimCostCentre[Cost centre] = "CC30")'
    ),
    "R11": (
        "CALCULATE([Actual], REMOVEFILTERS(), DimDate[Year] = 2025, DimDate[Month number] <= 9, "
        'DimPnLLine[Line key] = "OPEX")'
    ),
    "R12": "CALCULATE([Personnel cost % of revenue], REMOVEFILTERS(), DimDate[Year] = 2024)",
    "R13": (
        "CALCULATE([Revenue], REMOVEFILTERS(), DimDate[Year] = 2025, DimDate[Month number] <= 9, "
        'DimCostCentre[Cost centre] = "CC30")'
    ),
}
REF = re.compile(r"(?:'([^']+)'|(?<![\w\]'])([A-Za-z_][A-Za-z0-9_]*))\[([^\]]+)\]")
UNQUALIFIED = re.compile(r"(?<![\w'\]])\[([^\]]+)\]")
FILE_CALL = re.compile(r"(?:File\.Contents|Folder\.Files)\(([^)]*)\)")


def flat(dax: str) -> str:
    """DAX on one line with single spaces, so a test can look for a phrase whatever the line breaks."""
    return re.sub(r"\s+", " ", re.sub(r"([({])\s+", r"\1", re.sub(r"\s+([)}])", r"\1", dax))).strip()


@pytest.fixture(scope="module")
def model():
    return load_model(MODEL_DIR)


def test_ten_tables_columns_types_and_sort_columns(model):
    assert set(model.tables) == set(COLUMNS) and len(COLUMNS) == 10
    for table, columns in COLUMNS.items():
        assert set(model.tables[table].columns) == set(columns), table
        for name, (data_type, hidden, sort_by) in columns.items():
            col = model.tables[table].columns[name]
            assert (col.data_type, col.is_hidden, col.sort_by_column) == (data_type, hidden, sort_by), (table, name)
            assert col.summarize_by == "none", (table, name)
    assert model.tables["Security"].is_hidden
    assert not [t for t, tab in model.tables.items() if tab.is_hidden and t != "Security"]


def test_date_table(model):
    date = model.tables["DimDate"]
    assert date.data_category == "Time" and date.columns["Date"].is_key
    source = date.partition_source or ""
    assert "StartDate" in source and "EndDate" in source and '"MMM"' in source


def test_relationships_many_to_one_single_direction(model):
    assert {(r.from_column, r.to_column) for r in model.relationships} == RELATIONSHIPS
    for r in model.relationships:
        assert r.cross_filtering_behavior in (None, "oneDirection") and r.is_active, r.name
        table, column = r.from_column.split(".", 1)
        assert model.tables[table].columns[column].is_hidden, r.from_column
    assert not [r for r in model.relationships if "Security" in r.from_column + r.to_column]


def test_model_settings_and_parameters(model):
    assert model.culture == "en-US" and model.discourage_implicit_measures
    assert model.compatibility_level == 1606
    assert model.annotations.get("__PBI_TimeIntelligenceEnabled") == "0"
    params = {name: e for name, e in model.expressions.items() if not name.startswith("src_")}
    assert set(params) == {"DataFolder", "StartDate", "EndDate"}
    assert params["DataFolder"].expression.startswith('"C:\\financial-reporting-dashboard\\data\\" meta')
    assert params["StartDate"].expression.startswith("#date(2023, 1, 1) meta")
    assert params["EndDate"].expression.startswith("#date(2025, 12, 31) meta")
    assert all("IsParameterQuery = true" in p.expression for p in params.values())


def test_each_staging_query_reads_exactly_one_file(model):
    staging = {name: e for name, e in model.expressions.items() if name.startswith("src_")}
    assert set(staging) == set(STAGING)
    for name, file in STAGING.items():
        source = staging[name].expression
        assert FILE_CALL.findall(source) == [f'DataFolder & "{file}"'], name
        assert not [other for other in STAGING if other != name and other in source], name  # no query references
        for typed in re.findall(r"Table\.TransformColumnTypes\((?:[^()]|\([^()]*\))*\)", source):
            assert typed.endswith('"en-US")'), (name, typed[:60])
    budget = flat(staging["src_Budget"].expression)
    assert 'Excel.Workbook(File.Contents(DataFolder & "budget.xlsx"), null, true)' in budget
    assert "Table.Skip(data, 3)" in budget
    assert 'Table.UnpivotOtherColumns(Kept, {"Cost centre", "Account"}, "Month", "Value")' in budget
    assert 'Text.BeforeDelimiter(sheet, " ")' in budget and 'Text.AfterDelimiter(sheet, " ")' in budget
    gl = flat(staging["src_GL"].expression)
    assert 'Table.AddColumn(Dated, "Amount", each -[amount], Currency.Type)' in gl


def test_tables_only_reference_the_staging_queries(model):
    for name, table in model.tables.items():
        source = table.partition_source or ""
        assert not FILE_CALL.findall(source), name
        assert "C:\\" not in source and "E:\\" not in source, name
    fact = flat(model.tables["FactGL"].partition_source)
    assert 'Table.NestedJoin(src_Budget, {"Account"}, src_Accounts, {"Account"}, "Chart", JoinKind.LeftOuter)' in fact
    assert "each [Value] * [Sign], Currency.Type" in fact and "Table.Combine({src_GL, Planned})" in fact
    plain = {"DimPnLLine": "src_Layout", "DimCostCentre": "src_CostCentres", "Security": "src_Security"}
    for name, staged in plain.items():
        assert flat(model.tables[name].partition_source) == f"let Source = {staged} in Source", name
    assert "#table(" in model.tables["DimScenario"].partition_source
    assert '{"Full year", 14}' in model.tables["PnLColumn"].partition_source


def test_recon_checks_equal_the_python_list(model):
    source = model.tables["ReconCheck"].partition_source
    rows = re.findall(r'\{"(R\d+)", "([^"]+)", "(amount|ratio|count)", (\d+)\}', source)
    assert [(i, label, kind) for i, label, kind, _ in rows] == list(reference.CHECKS)
    assert [int(n) for *_, n in rows] == list(range(1, 14))


def test_36_measures_with_description_folder_and_format(model):
    measures = model.tables["_Measures"].measures
    assert set(measures) == set(MEASURES) and len(MEASURES) == 36
    for name, (folder, fmt, hidden) in MEASURES.items():
        m = measures[name]
        assert m.description and m.display_folder == folder and m.is_hidden == hidden, name
        if fmt in (AMOUNT, VARIANCE, CHECK):
            assert m.format_string is None and flat(m.format_string_definition or "") == fmt, name
        else:
            raw = m.format_string or ""
            stored = (raw[1:-1].replace('""', '"') if raw.startswith('"') else raw) or None
            assert stored == fmt and m.format_string_definition is None, name


def test_measure_definitions_of_section_7(model):
    m = {name: flat(x.expression) for name, x in model.tables["_Measures"].measures.items()}
    for name, dax in DEFINITIONS.items():
        assert m[name] == dax, name
    assert m["Data as of"].startswith("VAR _forecast = CALCULATE(MAX(FactGL[Date]), REMOVEFILTERS(), DimScenario")
    assert '"Actuals through " & FORMAT([Last actual date], "mmm yyyy", "en-US")' in m["Data as of"]


def test_check_value_branches_follow_section_10(model):
    dax = flat(model.tables["_Measures"].measures["Check value"].expression)
    assert dax.startswith("VAR _id = SELECTEDVALUE(ReconCheck[Id]) RETURN SWITCH(_id, ")
    for cid, branch in CHECK_BRANCHES.items():
        assert f'"{cid}", {branch}' in dax, cid
    assert dax.count("REMOVEFILTERS()") == 13


def test_role_filters_verbatim(model):
    assert [r.name for r in model.roles] == ["Department head"]
    role = model.roles[0]
    assert role.model_permission == "read"
    assert {t: flat(e) for t, e in role.table_permissions.items()} == ROLE


def _expressions(model):
    out = [(f"measure {m.name}", m.expression) for m in model.tables["_Measures"].measures.values()]
    out += [(f"format {m.name}", m.format_string_definition) for m in model.tables["_Measures"].measures.values()]
    out += [(f"role {t}", e) for r in model.roles for t, e in r.table_permissions.items()]
    return [(where, dax) for where, dax in out if dax]


def test_dax_references_resolve(model):
    cols = {(t, c) for t, tab in model.tables.items() for c in tab.columns}
    measures = {m for tab in model.tables.values() for m in tab.measures}
    for where, dax in _expressions(model):
        for quoted, bare, item in REF.findall(dax):
            table = quoted or bare
            assert (table, item) in cols, (where, table, item)
        for item in UNQUALIFIED.findall(REF.sub("", dax)):
            assert item in measures, (where, item)


def test_no_table_level_isfiltered(model):
    """ISFILTERED on a whole table is TRUE under the role's filter on a hidden key column and blanks the measure."""
    table_level = re.compile(r"ISFILTERED\s*\(\s*'?[^'\[\]()]+'?\s*\)", re.IGNORECASE)
    for where, dax in _expressions(model):
        assert not table_level.search(dax), where


def test_mutation_unknown_column_is_caught(model):
    bad = [("measure X", "SUM(FactGL[Amonut])")]
    cols = {(t, c) for t, tab in model.tables.items() for c in tab.columns}
    missing = [(w, t or b, i) for w, dax in bad for t, b, i in REF.findall(dax) if ((t or b), i) not in cols]
    assert missing == [("measure X", "FactGL", "Amonut")]
