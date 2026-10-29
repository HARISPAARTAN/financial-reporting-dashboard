"""The documentation agrees with the code: README outline and facts in both languages, the DAX in docs/measures.md,
the tables and columns in docs/data-model.md, the decision records, the architecture diagram and the Desktop
checklist."""

import csv
import json
import re
from pathlib import Path

import pytest

import reference
from pbir import PROJECT
from tmdl import load_model

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
MODEL = ROOT / PROJECT["folder"] / f"{PROJECT['name']}.SemanticModel" / "definition"
PAGES = ROOT / "tools" / "pbi" / "pages.json"
FOOTER = "Rebuilt from memory as a demo. The original client's name and data are not used."
FENCE = "`" * 3
README_EN = [
    "Status",
    "Client brief",
    "Live demo",
    "What it does",
    "How it works",
    "Data model",
    "Getting started",
    "Project layout",
    "Decisions",
    "Compared with the original delivery",
    "Licence and data note",
]
README_DE = [
    "Status",
    "Kundenauftrag",
    "Live-Demo",
    "Was es kann",
    "So funktioniert es",
    "Datenmodell",
    "Erste Schritte",
    "Projektstruktur",
    "Entscheidungen",
    "Im Vergleich zur ursprünglichen Lieferung",
    "Lizenz und Hinweis zu den Daten",
]
ADRS = [
    "0001-pnl-layout-and-sign-convention.md",
    "0002-power-query-staging-and-unpivot.md",
    "0003-forecast-outlook-and-closed-months.md",
    "0004-pandas-reference-and-reconciliation-page.md",
]
SHOTS = [
    "01-pnl-statement.png",
    "02-variance-analysis.png",
    "03-trend.png",
    "04-opex.png",
    "05-department-detail.png",
    "06-info.png",
    "07-line-tooltip.png",
    "08-model.png",
    "09-rls-head-of-operations.png",
    "10-reconciliation.png",
    "11-replica-1440.png",
    "12-replica-390.png",
]


@pytest.fixture(scope="module")
def model():
    return load_model(MODEL)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def headings(text: str, level: int) -> list[str]:
    outside = re.sub(rf"{FENCE}.*?{FENCE}", "", text, flags=re.DOTALL)
    return re.findall(rf"^{'#' * level} (.+)$", outside, flags=re.MULTILINE)


def sections(text: str, level: int) -> dict[str, str]:
    parts = re.split(rf"^{'#' * level} ", text, flags=re.MULTILINE)[1:]
    return {part.split("\n", 1)[0].strip(): part for part in parts}


def code_lines(section: str) -> list[str]:
    """The lines of the first dax block of a section, each stripped (indentation is not compared)."""
    match = re.search(rf"{FENCE}dax\n(.*?)\n{FENCE}", section, flags=re.DOTALL)
    assert match, "no dax block"
    return [line.strip() for line in match.group(1).split("\n")]


def stripped(expression: str) -> list[str]:
    return [line.strip() for line in expression.split("\n")]


@pytest.mark.parametrize(("name", "outline"), [("README.md", README_EN), ("README.de.md", README_DE)])
def test_readme_follows_the_umbrella_outline(name, outline):
    text = read(ROOT / name)
    assert text.startswith("# Financial Reporting Dashboard\n")
    assert headings(text, 2) == outline
    for badge in ("actions/workflows/ci.yml/badge.svg", "actions/workflows/pages.yml/badge.svg", "img.shields.io"):
        assert badge in text, badge
    other = "README.de.md" if name == "README.md" else "README.md"
    assert f"]({other})" in text
    assert text.rstrip().endswith(FOOTER)
    for adr in ADRS:
        assert f"](docs/adr/{adr})" in text, adr


def test_readme_facts_match_the_project(model):
    text = read(ROOT / "README.md")
    pages = json.loads(read(PAGES))["pages"]
    tooltip = [p for p in pages if p.get("type") == "Tooltip"]
    canvas = [p for p in pages if p.get("type") != "Tooltip"]
    assert len(pages) == 8 and len(tooltip) == 1 and len(canvas) == 7
    assert "Eight report pages with the theme Kaldora Dark: six content pages and the hidden page" in text
    size = f"{tooltip[0]['width']} × {tooltip[0]['height']}"
    assert f"on a 1280 × 720 canvas, and the tooltip page Line tooltip on {size}" in text
    assert len(reference.CHECKS) == 13 and "the thirteen headline checks reconciled" in text
    assert f"{len(model.tables['_Measures'].measures)} measures in `_Measures`" in text
    for left_out in ("the Opex page", "the Department detail drill-through", "the tooltip page", "row-level security"):
        assert left_out in text.split("## Live demo", 1)[1].split("## ", 1)[0], left_out
    assert "the cumulative and full-year charts and the Year and Months filters" in text


def test_brief_is_the_same_in_the_readme_and_the_brief():
    quote = re.search(r"^> (.+)$", read(DOCS / "brief.md"), flags=re.MULTILINE).group(1)
    assert f"> {quote}" in read(ROOT / "README.md")
    assert FOOTER in read(DOCS / "brief.md")


def test_every_measure_is_documented_with_its_dax(model):
    doc = sections(read(DOCS / "measures.md"), 3)
    measures = model.tables["_Measures"].measures
    assert len(measures) == 36
    for name, measure in measures.items():
        assert name in doc, name
        assert code_lines(doc[name]) == stripped(measure.expression), f"{name}: the DAX differs from the TMDL"
        assert f"Folder `{measure.display_folder}`" in doc[name], name


def test_role_is_documented(model):
    doc = sections(read(DOCS / "measures.md"), 2)
    (role,) = model.roles
    filters = sections(doc[f"Role {role.name}"], 3)
    assert set(filters) == {f"Filter on {table}" for table in role.table_permissions}
    for table, expression in role.table_permissions.items():
        assert code_lines(filters[f"Filter on {table}"]) == stripped(expression), table


def test_data_model_lists_every_table_column_and_relationship(model):
    text = read(DOCS / "data-model.md")
    rows = {m.group(1): m.group(2) for m in re.finditer(r"^\| `([^`]+)` \| [^|]+ \| (.+) \|$", text, re.MULTILINE)}
    for name, table in model.tables.items():
        assert name in rows, name
        for column in table.columns:
            assert f"`{column}`" in rows[name], f"{name}[{column}]"
    pairs = set(re.findall(r"^\| `(\w+)\[([^\]]+)\]` \| `(\w+)\[([^\]]+)\]` \|$", text, flags=re.MULTILINE))
    expected = {(*r.from_column.split(".", 1), *r.to_column.split(".", 1)) for r in model.relationships}
    assert pairs == expected


def test_data_model_lists_every_data_file():
    text = read(DOCS / "data-model.md")
    for path in sorted((ROOT / "data").iterdir()):
        assert f"`data/{path.name}`" in text, path.name


def test_decision_records():
    found = sorted(p.name for p in (DOCS / "adr").glob("*.md"))
    assert found == ADRS
    for name in ADRS:
        text = read(DOCS / "adr" / name)
        assert text.startswith(f"# ADR {name[:4]}: ")
        assert re.search(r"^Status: accepted \(\d{4}-\d{2}-\d{2}\)$", text, flags=re.MULTILINE), name
        assert headings(text, 2)[:3] == ["Context", "Decision", "Consequences"], name


def test_architecture_diagram_is_self_contained():
    svg = read(DOCS / "architecture.svg")
    assert svg.startswith("<svg ") and "<title" in svg and "<desc" in svg
    assert "http://" not in svg.replace("http://www.w3.org/2000/svg", "") and "https://" not in svg
    assert "<image" not in svg and "@import" not in svg
    for label in ("tools/make_data.py", "Power Query", "TMDL model", "PBIR report", "Desktop session", "owner, local"):
        assert label in svg, label
    for label in ("tools/reference.py", "kaldora.json", "HTML replica", "Reconciliation R1 to R13"):
        assert label in svg, label


def test_docs_named_by_the_spec_exist():
    for name in ("brief.md", "data-model.md", "measures.md", "architecture.md", "handover.md"):
        assert (DOCS / name).is_file(), name
    for name in ("desktop-validation.md", "reconciliation.md", "screenshots/SHOTLIST.md"):
        assert (DOCS / name).is_file(), name
    handover = headings(read(DOCS / "handover.md"), 2)
    for heading in ("Monthly close", "Adding an account", "Adding a cost centre", "Adding a Security row"):
        assert heading in handover, heading
    assert "Building the role-free copy" in handover and "Updating Faker or numpy" in handover
    shotlist = read(DOCS / "screenshots" / "SHOTLIST.md")
    shots = re.findall(r"^\| `(\d\d-[a-z0-9-]+\.png)` \|", shotlist, flags=re.MULTILINE)
    assert shots == SHOTS


def test_desktop_checklist_is_neutral_and_names_the_view_as_addresses():
    text = read(DOCS / "desktop-validation.md")
    assert "assistant" not in text.lower()
    assert not re.search(r"\b\d+\s*(minutes|min)\b", text)
    assert headings(text, 2)[-1] == "After the session"
    steps = re.findall(r"^\d+\. ", sections(text, 2)["Steps"], flags=re.MULTILINE)
    assert len(steps) == 9
    with (ROOT / "data" / "security.csv").open(encoding="utf-8", newline="") as f:
        security = list(csv.DictReader(f))
    with (ROOT / "data" / "cost_centres.csv").open(encoding="utf-8", newline="") as f:
        heads = {row["cost_centre"]: row["head_email"] for row in csv.DictReader(f)}
    counts = {}
    for row in security:
        counts[row["user_email"]] = counts.get(row["user_email"], 0) + 1
    (operations,) = [email for email, n in counts.items() if n == 4]
    assert f"| Head of Operations | `{operations}` |" in text
    assert f"| Head of Security Services | `{heads['CC30']}` |" in text
