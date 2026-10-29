"""Offline lint of the PBIR report against spec section 6 and tools/pbi/pages.json. Each check is a function that
returns its problems, so the mutation tests at the end can prove that it bites."""

import copy
import json
import re
from pathlib import Path

import pytest

import build_theme
from build_report import bookmark_name, content_name, tile_specs
from pbir import PROJECT, QUERY_ONLY, ROLES, iter_fields, load_report, stable_name
from tmdl import load_model

pytestmark = pytest.mark.pbi
ROOT = Path(__file__).resolve().parents[2]
PBI = ROOT / PROJECT["folder"]
REPORT = PBI / f"{PROJECT['name']}.Report" / "definition"
MODEL = PBI / f"{PROJECT['name']}.SemanticModel" / "definition"
SPEC = json.loads((ROOT / "tools" / "pbi" / "pages.json").read_text(encoding="utf-8"))
SPEC_PAGES = {p["id"]: p for p in SPEC["pages"]}
PAGES = [
    "P&L statement",
    "Variance analysis",
    "Trend",
    "Opex",
    "Department detail",
    "Info",
    "Line tooltip",
    "Reconciliation",
]
RESET_PAGES = PAGES[:5]
SLICERS = {
    "P&L statement": ["Year", "Months", "Department", "Scenario"],
    "Variance analysis": ["Year", "Months", "Department"],
    "Trend": ["Department", "P&L line"],
    "Opex": ["Year", "Months", "Department"],
    "Department detail": ["Year", "Months"],
}
FOOTER = "Rebuilt from memory as a demo. The original client's name and data are not used."
SLICER_ROW = (SPEC["slicer_row"]["y"], SPEC["slicer_row"]["y"] + SPEC["slicer_row"]["h"])
TILE_ROW = (SPEC["tiles"]["y"], SPEC["tiles"]["y"] + SPEC["tiles"]["h"])
CONTENT_TOP = 212
FAVOURABLE = ("_Measures", "Favourable colour", "Measure")
TINT = ("_Measures", "Row tint", "Measure")


def lit(prop):
    return prop["expr"]["Literal"]["Value"]


def text_of(visual) -> str:
    paragraphs = (
        visual.raw["visual"].get("objects", {}).get("general", [{}])[0].get("properties", {}).get("paragraphs", [])
    )
    return "\n".join("".join(run["value"] for run in p["textRuns"]) for p in paragraphs)


def box(visual):
    p = visual.raw["position"]
    return p["x"], p["y"], p["x"] + p["width"], p["y"] + p["height"]


def tokens() -> dict[str, str]:
    return build_theme.dark_tokens((ROOT / "web" / "kit" / "tokens.css").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def report():
    return load_report(REPORT)


@pytest.fixture(scope="module")
def model():
    return load_model(MODEL)


def page(report, name):
    return next(p for p in report.pages if p.display_name == name)


def visual(report, page_name, key):
    pg = page(report, page_name)
    index, spec = next((i, v) for i, v in enumerate(SPEC_PAGES[pg.name]["visuals"]) if v.get("key") == key)
    return next(v for v in pg.visuals if v.name == content_name(pg.name, index, spec))


# --- checks ---------------------------------------------------------------------------------------------------------


def field_problems(raw, model, where=""):
    """Every Column and Measure node names an existing column or measure of that kind."""
    out = []
    for entity, prop, kind in iter_fields(raw):
        table = model.tables.get(entity)
        if table is None:
            out.append(f"{where}: unknown table {entity!r}")
        elif kind == "Level":
            out.append(f"{where}: {entity} has no hierarchies, {prop!r} is a level")
        elif prop not in (table.columns if kind == "Column" else table.measures):
            out.append(f"{where}: {entity}[{prop}] is used as a {kind} but the model has no such {kind.lower()}")
    return out


def layout_problems(pg):
    """Inside the canvas; slicers in the slicer row; no two visuals overlap."""
    out = []
    boxes = []
    for v in pg.visuals:
        x0, y0, x1, y1 = box(v)
        if x0 < 0 or y0 < 0 or x1 > pg.width or y1 > pg.height:
            out.append(f"{pg.display_name}: {v.title} leaves the canvas")
        if v.visual_type == "slicer" and (y0, y1) != SLICER_ROW:
            out.append(f"{pg.display_name}: slicer {v.title} is not in the slicer row")
        boxes.append((v.title or v.name, (x0, y0, x1, y1)))
    for i, (a, (ax0, ay0, ax1, ay1)) in enumerate(boxes):
        for b, (bx0, by0, bx1, by1) in boxes[i + 1 :]:
            if ax0 < bx1 and bx0 < ax1 and ay0 < by1 and by0 < ay1:
                out.append(f"{pg.display_name}: {a!r} overlaps {b!r}")
    return out


def tile_problems(pg, spec_page):
    """The KPI tiles sit in the KPI row before the content, bound to their measure, with their line filter."""
    out = []
    names = {v.name: v for v in pg.visuals}
    tab = {v.name: v.raw["position"].get("tabOrder", 0) for v in pg.visuals}
    content = [content_name(pg.name, i, v) for i, v in enumerate(spec_page.get("visuals", []))]
    first_content = min((tab[n] for n in content if n in tab), default=len(tab) + 1000)
    for key, tile in tile_specs(spec_page, SPEC["tiles"]):
        v = names.get(stable_name(pg.name, key))
        if v is None:
            out.append(f"{pg.display_name}: tile {key} is missing")
            continue
        if tab[v.name] > first_content:
            out.append(f"{pg.display_name}: tile {key} comes after the content in tab order")
        x0, y0, x1, y1 = box(v)
        if y0 < TILE_ROW[0] or y1 > TILE_ROW[1] or y1 > CONTENT_TOP:
            out.append(f"{pg.display_name}: tile {key} is outside the KPI row")
        measure = tuple(tile["roles"]["Values"][0][:3])
        bound = [f for f in iter_fields(v.raw["visual"]["query"]) if f[2] == "Measure"]
        if bound != [measure]:
            out.append(f"{pg.display_name}: tile {key} binds {bound}, expected {measure}")
        wanted = [f["in"] for f in tile.get("filters", [])]
        found = [
            [
                w["Literal"]["Value"].strip("'")
                for row in flt["filter"]["Where"][0]["Condition"]["In"]["Values"]
                for w in row
            ]
            for flt in v.raw.get("filterConfig", {}).get("filters", [])
        ]
        if found != wanted:
            out.append(f"{pg.display_name}: tile {key} filters {found}, expected {wanted}")
    return out


def sync_problems(report):
    out = []
    for pg in report.pages:
        for v in pg.visuals:
            if v.visual_type != "slicer":
                continue
            group = v.raw["visual"].get("syncGroup", {})
            if group != {"groupName": v.title, "fieldChanges": True, "filterChanges": True}:
                out.append(f"{pg.display_name}: slicer {v.title} has sync group {group}")
    return out


def reset_problems(report):
    """Each page with slicers has one Reset button whose bookmark is its page's bookmark in the group Reset filters."""
    out = []
    by_name = {b["name"]: b for b in report.bookmarks}
    for pg in report.pages:
        buttons = [v for v in pg.visuals if v.visual_type == "actionButton" and v.title == "Reset"]
        if pg.display_name not in RESET_PAGES:
            if buttons:
                out.append(f"{pg.display_name}: a Reset button on a page without slicers")
            continue
        if len(buttons) != 1:
            out.append(f"{pg.display_name}: {len(buttons)} Reset buttons")
            continue
        link = buttons[0].raw["visual"]["visualContainerObjects"]["visualLink"][0]["properties"]
        target = lit(link["bookmark"]).strip("'")
        if lit(link["type"]) != "'Bookmark'" or target != bookmark_name(pg.name):
            out.append(f"{pg.display_name}: Reset applies {target!r}")
        bm = by_name.get(target)
        if bm is None:
            out.append(f"{pg.display_name}: bookmark {target!r} does not exist")
            continue
        state = bm["explorationState"]
        if state["activeSection"] != pg.name or list(state["sections"]) != [pg.name]:
            out.append(f"{pg.display_name}: bookmark points at {state['activeSection']!r}")
            continue
        targets = set(bm["options"]["targetVisualNames"])
        restored = set(state["sections"][pg.name]["visualContainers"])
        if not bm["options"].get("applyOnlyToTargetVisuals") or targets != restored:
            out.append(f"{pg.display_name}: bookmark targets {sorted(targets)}")
        slicers = {v.name for v in pg.visuals if v.visual_type == "slicer"}
        if not slicers <= targets:
            out.append(f"{pg.display_name}: bookmark misses slicers {sorted(slicers - targets)}")
    if report.bookmark_groups != {
        "Reset filters": [bookmark_name(p.name) for p in report.pages if p.display_name in RESET_PAGES]
    }:
        out.append(f"bookmark groups are {report.bookmark_groups}")
    return out


def special_page_problems(report):
    """Line tooltip: a hidden 320 x 200 tooltip page; Department detail: drill-through on the department name;
    Reconciliation: hidden in view mode; the bar chart and the monthly trend show the tooltip page."""
    out = []
    tip = page(report, "Line tooltip")
    if (tip.page_type, tip.visibility, tip.width, tip.height) != ("Tooltip", "HiddenInViewMode", 320, 200):
        out.append("the tooltip page is not a hidden 320 x 200 tooltip page")
    detail = page(report, "Department detail")
    binding = detail.raw.get("pageBinding") or {}
    filters = detail.raw.get("filterConfig", {}).get("filters", [])
    if detail.page_type != "Drillthrough" or binding.get("type") != "Drillthrough" or detail.visibility:
        out.append("Department detail is not a visible drill-through page")
    if [list(iter_fields(f)) for f in detail.drillthrough_fields] != [[("DimCostCentre", "Name", "Column")]]:
        out.append(f"Department detail drills through {detail.drillthrough_fields}")
    if [f.get("howCreated") for f in filters] != ["Drillthrough"] or filters[0]["name"] != (
        binding.get("parameters") or [{}]
    )[0].get("boundFilter"):
        out.append("the drill-through filter is not bound to the page binding")
    if page(report, "Reconciliation").visibility != "HiddenInViewMode":
        out.append("Reconciliation is shown in view mode")
    for page_name, key in (("Variance analysis", "bars"), ("Trend", "monthly")):
        v = visual(report, page_name, key)
        props = v.raw["visual"]["visualContainerObjects"].get("visualTooltip", [{}])[0].get("properties", {})
        kind = lit(props["type"]) if "type" in props else None
        if kind != "'ReportPage'" or lit(props["section"]).strip("'") != tip.name:
            out.append(f"{page_name} {key}: no report-page tooltip {tip.name!r}")
    return out


def formatting_problems(report):
    """Variances, status texts, KPI deltas and department bars take their colour from [Favourable colour]; the value
    cells of the three P&L matrices take their background from [Row tint]; the waterfall uses the kit tokens."""
    out = []

    def colour_fields(raw, key, prop):
        entries = raw["visual"].get("objects", {}).get(key, [])
        return {
            (e.get("selector", {}).get("metadata"), tuple(next(iter_fields(e["properties"][prop]))))
            for e in entries
            if prop in e.get("properties", {})
        }

    for page_name, key in (("Variance analysis", "matrix"), ("Opex", "table"), ("Department detail", "matrix")):
        v = visual(report, page_name, key)
        found = {m for m, f in colour_fields(v.raw, "values", "fontColor") if f == FAVOURABLE}
        wanted = {"_Measures.Variance", "_Measures.Variance %"}
        if page_name != "Department detail":
            wanted.add("_Measures.Favourable label")
        if found != wanted:
            out.append(f"{page_name} {key}: font colour by Favourable colour on {sorted(found)}")
    for page_name in ("P&L statement", "Variance analysis", "Department detail"):
        v = visual(report, page_name, "matrix")
        tinted = {m for m, f in colour_fields(v.raw, "values", "backColor") if f == TINT}
        amounts = {
            p["queryRef"]
            for p in v.raw["visual"]["query"]["queryState"]["Values"]["projections"]
            if p["queryRef"] not in ("_Measures.Variance", "_Measures.Variance %", "_Measures.Favourable label")
        }
        if tinted != amounts:
            out.append(f"{page_name} matrix: Row tint on {sorted(tinted)}, expected {sorted(amounts)}")
    bars = visual(report, "Variance analysis", "bars")
    if colour_fields(bars.raw, "dataPoint", "fill") != {(None, FAVOURABLE)}:
        out.append("the department bars are not coloured by Favourable colour")
    for pg in report.pages:
        names = {v.name: v for v in pg.visuals}
        for key, _ in tile_specs(SPEC_PAGES[pg.name], SPEC["tiles"]):
            v = names[stable_name(pg.name, key)]
            if key.endswith("-delta") and {f for _, f in colour_fields(v.raw, "labels", "color")} != {FAVOURABLE}:
                out.append(f"{pg.display_name}: delta card {v.title!r} is not coloured by Favourable colour")
    t = tokens()
    waterfall = visual(report, "Variance analysis", "waterfall")
    fills = waterfall.raw["visual"]["objects"]["sentimentColors"][0]["properties"]
    colours = {k: lit(v["solid"]["color"]).strip("'") for k, v in fills.items()}
    if colours != {"increaseFill": t["ok"], "decreaseFill": t["warn"], "totalFill": t["accent"]}:
        out.append(f"waterfall colours {colours}")
    return out


def interaction_problems(report):
    """P&L statement: the Scenario slicer filters only the matrix and the matrix filters nothing; Variance analysis:
    the waterfall filters only the matrix and the matrix filters nothing."""
    out = []
    for page_name, rules in (
        ("P&L statement", {("slicer", "Scenario"): "tiles", ("visual", "matrix"): "*"}),
        ("Variance analysis", {("visual", "waterfall"): "bars+tiles", ("visual", "matrix"): "*"}),
    ):
        pg = page(report, page_name)
        found: dict[str, set[str]] = {}
        for rule in pg.raw.get("visualInteractions", []):
            if rule["type"] != "NoFilter":
                out.append(f"{page_name}: interaction type {rule['type']}")
            found.setdefault(rule["source"], set()).add(rule["target"])
        tiles = {stable_name(pg.name, key) for key, _ in tile_specs(SPEC_PAGES[pg.name], SPEC["tiles"])}
        data = {v.name for v in pg.visuals if "query" in v.raw["visual"]}
        for (kind, key), targets in rules.items():
            source = stable_name(pg.name, "slicer", key) if kind == "slicer" else visual(report, page_name, key).name
            if targets == "*":
                wanted = data - {source}
            elif targets == "tiles":
                wanted = tiles
            else:
                wanted = tiles | {visual(report, page_name, "bars").name}
            if found.get(source) != wanted:
                out.append(f"{page_name}: {key} does not filter exactly what section 6 says")
    return out


# --- the lint -------------------------------------------------------------------------------------------------------


def test_eight_pages_in_order_sizes_and_types(report):
    assert [p.display_name for p in report.pages] == PAGES
    assert [p.name for p in report.pages] == [p["id"] for p in SPEC["pages"]]
    types = {"Department detail": "Drillthrough", "Line tooltip": "Tooltip"}
    for pg in report.pages:
        size = (320, 200) if pg.display_name == "Line tooltip" else (1280, 720)
        assert ((pg.width, pg.height), pg.page_type) == (size, types.get(pg.display_name)), pg.display_name


def test_every_bound_field_exists(report, model):
    problems = [p for pg in report.pages for v in pg.visuals for p in field_problems(v.raw, model, v.title or v.name)]
    problems += [p for pg in report.pages for p in field_problems(pg.raw, model, pg.display_name)]
    problems += [p for b in report.bookmarks for p in field_problems(b, model, b["displayName"])]
    assert not problems, problems


def test_roles_are_valid_and_no_custom_visuals(report):
    allowed = {**ROLES, **QUERY_ONLY}
    for pg in report.pages:
        for v in pg.visuals:
            assert v.visual_type in allowed, (pg.display_name, v.visual_type)
            assert v.roles() <= allowed[v.visual_type], (pg.display_name, v.title, v.roles())
    assert not list(REPORT.parent.glob("**/CustomVisuals"))
    assert "publicCustomVisuals" not in (REPORT / "report.json").read_text(encoding="utf-8")


def test_layout_slicer_row_tiles_and_no_overlaps(report):
    problems = [p for pg in report.pages for p in layout_problems(pg)]
    problems += [p for pg in report.pages for p in tile_problems(pg, SPEC_PAGES[pg.name])]
    assert not problems, problems


def test_pages_have_their_slicers(report):
    for pg in report.pages:
        slicers = sorted((v for v in pg.visuals if v.visual_type == "slicer"), key=lambda v: box(v)[0])
        assert [v.title for v in slicers] == SLICERS.get(pg.display_name, []), pg.display_name


def test_slicer_modes_and_defaults(report):
    def slicer(page_name, title):
        return next(v for v in page(report, page_name).visuals if v.visual_type == "slicer" and v.title == title)

    def selection(v):
        return {k: lit(p) for k, p in v.raw["visual"]["objects"]["selection"][0]["properties"].items()}

    year = slicer("P&L statement", "Year")
    assert lit(year.raw["visual"]["objects"]["data"][0]["properties"]["mode"]) == "'Dropdown'"
    assert selection(year)["singleSelect"] == "true"
    assert '"2025L"' in json.dumps(year.raw["visual"]["objects"]["general"])
    months = slicer("P&L statement", "Months")
    assert lit(months.raw["visual"]["objects"]["data"][0]["properties"]["mode"]) == "'Between'"
    assert list(iter_fields(months.raw["visual"]["query"])) == [("DimDate", "Month number", "Column")]
    department = slicer("Opex", "Department")
    assert selection(department) == {
        "strictSingleSelect": "false",
        "singleSelect": "false",
        "selectAllCheckboxEnabled": "true",
    }
    scenario = slicer("P&L statement", "Scenario")
    assert lit(scenario.raw["visual"]["objects"]["general"][0]["properties"]["orientation"]) == "1D"
    assert "'Actual'" in json.dumps(scenario.raw["visual"]["objects"]["general"])
    line = slicer("Trend", "P&L line")
    assert selection(line)["singleSelect"] == "true" and "'EBITDA'" in json.dumps(line.raw["visual"]["objects"])


def test_sync_groups(report):
    assert not sync_problems(report)


def test_reset_buttons_target_their_page_bookmark(report):
    assert not reset_problems(report)


def test_reset_bookmarks_restore_the_default_state(report):
    def values(state):
        where = state["singleVisual"]["objects"]["merge"]["general"][0]["properties"]["filter"]["Where"]
        return [w["Literal"]["Value"] for row in where[0]["Condition"]["In"]["Values"] for w in row]

    removed = {"remove": [{"object": "general", "property": "filter"}]}
    for bm in report.bookmarks:
        pid = bm["explorationState"]["activeSection"]
        states = bm["explorationState"]["sections"][pid]["visualContainers"]
        defaults = {"Year": ["2025L"], "Scenario": ["'Actual'"], "P&L line": ["'EBITDA'"]}
        for name in SLICERS[next(p.display_name for p in report.pages if p.name == pid)]:
            state = states[stable_name(pid, "slicer", name)]
            if name in defaults:
                assert values(state) == defaults[name], (pid, name)
            else:
                assert state["singleVisual"]["objects"] == removed, (pid, name)
        for index, spec in enumerate(SPEC_PAGES[pid].get("visuals", [])):
            if spec.get("reset") == "collapse":
                state = states[content_name(pid, index, spec)]["singleVisual"]
                assert state == {"visualType": "pivotTable", "expansionStates": []}, pid
    assert len(report.bookmarks) == 5


def test_special_pages(report):
    assert not special_page_problems(report)


def test_formatting_is_bound_to_the_formatting_measures(report):
    assert not formatting_problems(report)


def test_visual_interactions(report):
    assert not interaction_problems(report)


def test_visuals_bind_what_section_6_says(report):
    def roles(page_name, key):
        state = visual(report, page_name, key).raw["visual"]["query"]["queryState"]
        return {role: [f[:2] for f in iter_fields(spec)] for role, spec in state.items()}

    rows = [("DimPnLLine", "Line"), ("DimAccount", "Subgroup"), ("DimAccount", "Account label")]
    assert roles("P&L statement", "matrix") == {
        "Rows": rows,
        "Columns": [("PnLColumn", "Column")],
        "Values": [("_Measures", "P&L Matrix")],
    }
    matrix = visual(report, "P&L statement", "matrix").raw["visual"]
    assert lit(matrix["objects"]["rowHeaders"][0]["properties"]["stepped"]) == "true"
    assert lit(matrix["objects"]["subTotals"][0]["properties"]["rowSubtotalsPosition"]) == "'Top'"
    assert "expansionStates" not in matrix  # collapsed by default
    assert roles("Variance analysis", "waterfall") == {
        "Category": [("DimPnLLine", "Line")],
        "Y": [("_Measures", "Profit impact")],
    }
    assert roles("Opex", "treemap") == {
        "Group": [("DimAccount", "Subgroup")],
        "Details": [("DimAccount", "Account label")],
        "Values": [("_Measures", "Actual")],
    }
    table = visual(report, "Opex", "table").raw
    topn = [f for f in table["filterConfig"]["filters"] if f["type"] == "TopN"]
    assert len(topn) == 1 and '"Top": 10' in json.dumps(topn[0]) and '"Property": "Variance"' in json.dumps(topn[0])
    trend = roles("Trend", "monthly")
    assert trend["Y"] == [("_Measures", "Actual"), ("_Measures", "Budget"), ("_Measures", "Forecast")]
    styles = visual(report, "Trend", "monthly").raw["visual"]["objects"]["lineStyles"]
    dashes = {e["selector"]["metadata"]: lit(e["properties"]["lineStyle"]) for e in styles if "selector" in e}
    assert dashes == {"_Measures.Budget": "'dashed'", "_Measures.Forecast": "'dotted'"}
    detail = page(report, "Department detail")
    back = [v for v in detail.visuals if v.visual_type == "actionButton" and v.title == "Back"]
    assert len(back) == 1
    assert lit(back[0].raw["visual"]["visualContainerObjects"]["visualLink"][0]["properties"]["type"]) == "'Back'"
    checks = visual(report, "Reconciliation", "checks")
    assert [f[:2] for f in iter_fields(checks.raw["visual"]["query"]["queryState"])] == [
        ("ReconCheck", "Id"),
        ("ReconCheck", "Label"),
        ("_Measures", "Check value"),
    ]


def test_alt_text_on_every_visual(report):
    missing = [(pg.display_name, v.visual_type, v.title) for pg in report.pages for v in pg.visuals if not v.alt_text]
    assert not missing, missing


def test_header_and_info_texts(report):
    for pg in report.pages:
        if pg.display_name == "Line tooltip":
            continue
        texts = [text_of(v) for v in pg.visuals if v.visual_type == "textbox"]
        assert f"Kaldora Facility Services · {pg.display_name}" in texts, pg.display_name
        cards = [v for v in pg.visuals if v.visual_type == "card" and v.title == "Data as of"]
        assert len(cards) == 1, pg.display_name
    info = "\n".join(text_of(v) for v in page(report, "Info").visuals if v.visual_type == "textbox")
    for phrase in (
        "Kaldora Facility Services is a fictional company and every number is invented.",
        FOOTER,
        "github.com/HARISPAARTAN/financial-reporting-dashboard",
        "harispaartan.github.io/financial-reporting-dashboard",
        "tools/make_data.py with seed 43",
        "debit plus, credit minus",
    ):
        assert phrase in info, phrase
    assert not re.search(r"https?://", info)
    assert "Security table" not in info  # true for the public variant too


def test_theme_registered_and_report_settings(report):
    assert report.theme_name == PROJECT["theme"]["file"]
    assert report.settings.get("defaultFilterActionIsDataFilter") is True
    theme = REPORT.parent / "StaticResources" / "RegisteredResources" / PROJECT["theme"]["file"]
    assert json.loads(theme.read_text(encoding="utf-8"))["name"] == PROJECT["theme"]["name"]


# --- mutations: each check catches a planted defect -----------------------------------------------------------------


def test_mutation_unknown_field_and_wrong_kind_are_caught(report, model):
    raw = visual(report, "Variance analysis", "bars").raw
    text = json.dumps(raw).replace('"Property": "Profit impact"', '"Property": "Profit impakt"')
    assert field_problems(json.loads(text), model)
    text = json.dumps(raw).replace('"Measure": {', '"Column": {')
    assert field_problems(json.loads(text), model)


def test_mutation_overlap_and_slicer_outside_the_row_are_caught(report):
    pg = copy.deepcopy(page(report, "P&L statement"))
    slicer = next(v for v in pg.visuals if v.title == "Year")
    slicer.raw["position"]["y"] = 120
    problems = layout_problems(pg)
    assert any("not in the slicer row" in p for p in problems) and any("overlaps" in p for p in problems)


def test_mutation_missing_sync_group_and_wrong_bookmark_are_caught(report):
    broken = copy.deepcopy(report)
    slicer = next(v for v in broken.pages[0].visuals if v.title == "Department")
    del slicer.raw["visual"]["syncGroup"]
    assert sync_problems(broken)
    button = next(v for v in broken.pages[1].visuals if v.visual_type == "actionButton")
    button.raw["visual"]["visualContainerObjects"]["visualLink"][0]["properties"]["bookmark"] = {
        "expr": {"Literal": {"Value": "'" + bookmark_name("pnl-statement") + "'"}}
    }
    assert reset_problems(broken)


def test_mutation_special_pages_are_caught(report):
    broken = copy.deepcopy(report)
    page(broken, "Line tooltip").visibility = None
    page(broken, "Reconciliation").visibility = None
    assert len(special_page_problems(broken)) == 2


def test_mutation_formatting_and_interactions_are_caught(report):
    broken = copy.deepcopy(report)
    bars = visual(broken, "Variance analysis", "bars")
    del bars.raw["visual"]["objects"]["dataPoint"]
    waterfall = visual(broken, "Variance analysis", "waterfall")
    waterfall.raw["visual"]["objects"]["sentimentColors"][0]["properties"]["totalFill"] = {
        "solid": {"color": {"expr": {"Literal": {"Value": "'#123456'"}}}}
    }
    assert len(formatting_problems(broken)) == 2
    page(broken, "P&L statement").raw["visualInteractions"].pop()
    assert interaction_problems(broken)


def test_generated_report_counts_positions_and_literals(report):
    """Pins the plan's fixed numbers that no other check holds: 87 visuals, the Back button at x 1052, filter
    aliases named f<n> and unique within a visual, and no exponent literal anywhere in the generated report."""
    assert len(list(REPORT.rglob("visual.json"))) == 87
    detail = page(report, "Department detail")
    back = [v for v in detail.visuals if v.visual_type == "actionButton" and v.title == "Back"]
    assert box(back[0])[0] == 1052
    exponent = re.compile(r"\d[eE][+-]\d")
    for path in REPORT.rglob("*.json"):
        text = path.read_text(encoding="utf-8")
        assert not exponent.search(text), path
        if path.name == "visual.json":
            aliases = re.findall(r'"Name": "(f\d+)"', text)
            assert len(aliases) == len(set(aliases)), path


def test_mutation_tile_without_its_line_filter_is_caught(report):
    pg = copy.deepcopy(page(report, "P&L statement"))
    tile = next(v for v in pg.visuals if v.name == stable_name("pnl-statement", "tile0"))
    del tile.raw["filterConfig"]
    assert tile_problems(pg, SPEC_PAGES["pnl-statement"])
