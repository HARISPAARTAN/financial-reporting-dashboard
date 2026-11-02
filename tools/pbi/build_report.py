"""Regenerate the PBIR report from tools/pbi/pages.json: pages, visuals, bookmarks, report.json and the page order.

    uv run python tools/pbi/build_report.py

Deterministic: fixed names (uuid5 of the project namespace, page id and role), sorted keys, two-space indent, UTF-8
without BOM, LF. Only page folders carrying the annotation PROJECT["generated"] are replaced; `bookmarks/` and
`report.json` are owned entirely by this script. Run it only until the first Desktop save; afterwards the files that
Desktop saved are the source (docs/desktop-validation.md).

Nothing in this module is specific to one report. tools/pbi/project.json names the PBIP, the stable-name namespace and
the theme; pages.json holds the layout:

- `header`: a title box ("{page}" is replaced by the page name) and further visuals shown on every page with a header;
- `slicers`: the slicer row; every slicer is synced across the pages by a group named after it; `default` ticks values
  and `only_with` lists only the values where that measure is not blank;
- `reset`: one Reset button per page with slicers; each applies its page's bookmark in the bookmark group `group`;
- `tiles`: the KPI row; a tile is a value card above a small card that binds the same measure with a visual filter on
  the calculation item named in `delta` (none: the value card fills the tile);
- `pages`: per page the slicer names, the tiles and the content visuals in the shape of Visual.from_template, plus the
  formatting keys handled in `_formatting`; a content visual with a `key` is named after it (else after its index);
- page keys: `drillthrough` ({"field": [entity, column]}: a drill-through page on that field that keeps every other
  filter), `hidden` (true: not shown in view mode), `back` (a Back button {"x", "y", "w", "h", "label"}) and
  `interactions` ([{"source", "targets", "type"}], each end "slicer:<name>", "tiles" or a visual's `key`, and "*" as
  targets for every other data visual of the page; type `NoFilter` unless given);
- a tile binds `measure` and, instead of the calculation items `item` and `delta`, may carry `filters` (visual filters
  of both cards), `delta_measure` (the measure of the card below), `delta_colour` and `colour_by` (measures whose value
  is the font colour of the delta card and of the value card).

Colour names in pages.json are portfolio-kit tokens (`accent`, `muted`, `ok`, `chart-2` ...), read from the tokens
file named in project.json, so the report and the web replica share one palette.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))  # lets `python tools/pbi/build_report.py` import its neighbours

from build_theme import dark_tokens  # noqa: E402
from pbir import PROJECT, SCHEMAS, Visual, _quoted, field_ref, projection, slicer_selection, stable_name  # noqa: E402

ROOT = HERE.parents[1]
REPORT = ROOT / PROJECT["folder"] / f"{PROJECT['name']}.Report"
DEFINITION = REPORT / "definition"
SPEC_PATH = HERE / "pages.json"
GENERATED = PROJECT["generated"]
LINE_CHARTS = {"lineChart", "lineClusteredColumnComboChart"}


def _lit(value: str) -> dict:
    return {"expr": {"Literal": {"Value": value}}}


def _text(value: str) -> dict:
    return _lit("'" + value.replace("'", "''") + "'")


def _solid(hexcode: str) -> dict:
    return {"solid": {"color": _lit("'" + hexcode + "'")}}


def _number(value: float) -> str:
    """A decimal literal as PBIR writes it: 1 -> "1D", 0.9 -> "0.9D"."""
    return f"{value:.15g}D"


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    path.write_bytes(text.encode("utf-8"))


def _column(entity: str, prop: str) -> dict:
    return {"Column": {"Expression": {"SourceRef": {"Entity": entity}}, "Property": prop}}


class Colours:
    """Kit token names to hex: `accent`, `muted`, `ok`, `warn`, `surface`, `chart-1` ... `chart-8`."""

    def __init__(self, tokens: dict[str, str]) -> None:
        self.tokens = tokens

    @classmethod
    def from_kit(cls) -> Colours:
        return cls(dark_tokens((ROOT / PROJECT["theme"]["tokens"]).read_text(encoding="utf-8")))

    def __call__(self, name: str) -> str:
        if name not in self.tokens:
            raise ValueError(f"colour {name!r} is not a kit token; known: {sorted(self.tokens)}")
        return self.tokens[name]


def _scope(entity: str, prop: str, value: str | bool | int | float) -> dict:
    """The data selector of one series value, typed like the column (text, number, true or false, date), in the shape
    Desktop writes for manual series colours."""
    right = {"Literal": {"Value": _quoted(value)}}
    return {"data": [{"scopeId": {"Comparison": {"ComparisonKind": 0, "Left": _column(entity, prop), "Right": right}}}]}


def _series(spec: dict, colours: Colours) -> dict:
    """Series colours and dashed lines by legend value: {"field": [entity, column], "colours": {value: token},
    "dashed": [value]}. JSON keys are text; for a number or true/false legend value write "colours" as pairs
    [[2025, token], ...]."""
    entity, prop = spec["field"]
    pairs = spec["colours"].items() if isinstance(spec["colours"], dict) else spec["colours"]
    fills = [
        {"properties": {"fill": _solid(colours(token))}, "selector": _scope(entity, prop, value)}
        for value, token in pairs
    ]
    out = {"dataPoint": fills}
    dashed = [
        {"properties": {"lineStyle": _lit("'dashed'")}, "selector": _scope(entity, prop, value)}
        for value in spec.get("dashed", [])
    ]
    if dashed:
        out["lineStyles"] = [{"properties": {"strokeWidth": _lit("2D"), "showMarker": _lit("false")}}, *dashed]
    return out


def _rule(spec: dict, colours: Colours) -> list[dict]:
    """Bar colours by rule: `pass` where the measure is at least `at_least`, `fail` below (blank stays uncoloured)."""
    entity, prop = spec["measure"]
    measure = {"Measure": {"Expression": {"SourceRef": {"Entity": entity}}, "Property": prop}}
    case = {
        "Condition": {
            "Comparison": {
                "ComparisonKind": 2,
                "Left": measure,
                "Right": {"Literal": {"Value": _number(spec["at_least"])}},
            }
        },
        "Value": {"Literal": {"Value": "'" + colours(spec["pass"]) + "'"}},
    }
    rule = {"Conditional": {"Cases": [case], "DefaultValue": {"Literal": {"Value": "'" + colours(spec["fail"]) + "'"}}}}
    return [
        {
            "properties": {"fill": {"solid": {"color": {"expr": rule}}}},
            "selector": {"data": [{"dataViewWildcard": {"matchingOption": 1}}]},
        }
    ]


def _constant_line(spec: dict, colours: Colours) -> list[dict]:
    """A constant line on the value axis (Analytics pane, "Constant line")."""
    return [
        {
            "properties": {
                "show": _lit("true"),
                "value": _lit(_number(spec["value"])),
                "lineColor": _solid(colours(spec["colour"])),
                "style": _lit("'dashed'"),
                "transparency": _lit("0D"),
            },
            "selector": {"id": "1"},
        }
    ]


def _gradient(spec: dict, colours: Colours) -> list[dict]:
    """Cell background by a three-colour scale on a matrix value: {"field": [...], "min": [value, token], "mid": ...,
    "max": ...}."""
    entity, prop, kind = spec["field"]

    def stop(key: str) -> dict:
        value, token = spec[key]
        return {
            "color": {"Literal": {"Value": "'" + colours(token) + "'"}},
            "value": {"Literal": {"Value": _number(value)}},
        }

    rule = {
        "linearGradient3": {
            "min": stop("min"),
            "mid": stop("mid"),
            "max": stop("max"),
            "nullColoringStrategy": {"strategy": {"Literal": {"Value": "'noColor'"}}},
        }
    }
    fill = {"solid": {"color": {"expr": {"FillRule": {"Input": field_ref(entity, prop, kind), "FillRule": rule}}}}}
    return [
        {
            "properties": {"backColor": fill},
            "selector": {
                "data": [{"dataViewWildcard": {"matchingOption": 1}}],
                "metadata": projection(entity, prop, kind)["queryRef"],
            },
        }
    ]


def _data_bars(spec: dict, colours: Colours) -> list[dict]:
    """Data bars behind the values of one table column."""
    entity, prop, kind = spec["field"]
    bars = {
        "positiveColor": _solid(colours(spec["colour"])),
        "negativeColor": _solid(colours("danger")),
        "axisColor": _solid(colours("border")),
        "reverseDirection": _lit("false"),
        "hideText": _lit("false"),
    }
    return [{"properties": {"dataBars": bars}, "selector": {"metadata": projection(entity, prop, kind)["queryRef"]}}]


WILDCARD = {"dataViewWildcard": {"matchingOption": 1}}  # every data point of the visual, totals excluded


def _by_measure(field: list[str]) -> dict:
    """A colour taken from a measure that returns a hex colour ("Format style: Field value")."""
    return {"solid": {"color": {"expr": field_ref(*field, "Measure")}}}


def _field_value_rules(spec: dict) -> list[dict]:
    """Font colour (`font_by`) and background (`back_by`) of matrix or table values from a measure:
    {"measure": [entity, measure], "fields": [[entity, measure], ...]} names the value fields it applies to."""
    out = []
    for key, prop in (("font_by", "fontColor"), ("back_by", "backColor")):
        rule = spec.get(key)
        for entity, name in rule["fields"] if rule else []:
            out.append(
                {
                    "properties": {prop: _by_measure(rule["measure"])},
                    "selector": {"data": [WILDCARD], "metadata": projection(entity, name, "Measure")["queryRef"]},
                }
            )
    return out


def _matrix(spec: dict, first_row: list[str]) -> dict:
    """Matrix layout: {"stepped": bool, "icons": bool, "subtotals": "Top" | "Bottom" | None}; column subtotals off, and
    no row grand total (a P&L has no meaningful one): Desktop has no switch for it, it is the subtotal of the first
    row level, written as per-level subtotals with `levelSubtotalEnabled` false for that level."""
    rows = {"stepped": _lit("true" if spec.get("stepped") else "false")}
    rows["showExpandCollapseButtons"] = _lit("true" if spec.get("icons") else "false")
    subtotals = spec.get("subtotals")
    totals = {
        "rowSubtotals": _lit("true" if subtotals else "false"),
        "columnSubtotals": _lit("false"),
    }
    items = [{"properties": totals}]
    if subtotals:
        totals["rowSubtotalsPosition"] = _lit(f"'{subtotals}'")
        totals["perRowLevel"] = _lit("true")
        items.append(
            {
                "properties": {"levelSubtotalEnabled": _lit("false")},
                "selector": {"metadata": f"{first_row[0]}.{first_row[1]}"},
            }
        )
    return {"rowHeaders": [{"properties": rows}], "subTotals": items}


def _lines(spec: list[dict], colours: Colours, line_chart: bool) -> dict:
    """Colour per measure of a chart with several measures and, on a line chart, the dash style:
    [{"field": [entity, measure], "colour": token, "style": "dashed" | "dotted"}]."""
    fills, styles = [], [{"properties": {"strokeWidth": _lit("2D"), "showMarker": _lit("false")}}]
    for line in spec:
        selector = {"metadata": projection(*line["field"], "Measure")["queryRef"]}
        fills.append({"properties": {"fill": _solid(colours(line["colour"]))}, "selector": selector})
        if line.get("style"):
            styles.append({"properties": {"lineStyle": _lit("'" + line["style"] + "'")}, "selector": selector})
    return {"dataPoint": fills, "lineStyles": styles} if line_chart else {"dataPoint": fills}


def _formatting(spec: dict, colours: Colours) -> dict:
    """The visual-level objects a spec asks for, merged in the order below; raw `objects` from the spec come last."""
    objects: dict = {}
    kind = spec["type"]
    roles = spec.get("roles", {})
    if kind == "card":
        labels = {"fontSize": _lit(f"{spec.get('label_size', 20)}D"), "labelDisplayUnits": _lit("1D")}
        if spec.get("label_colour"):
            labels["color"] = _solid(colours(spec["label_colour"]))
        objects["labels"] = [{"properties": labels}]
        objects["categoryLabels"] = [{"properties": {"show": _lit("true" if spec.get("category_label") else "false")}}]
    if kind == "slicer":
        mode = spec.get("mode", "Basic")
        objects["data"] = [{"properties": {"mode": _text(mode)}}]
        objects["general"] = [{"properties": {"selfFilterEnabled": _lit("false")}}]
        if spec.get("tiles"):
            objects["general"][0]["properties"]["orientation"] = _lit("1D")
        single = "true" if spec.get("single") else "false"
        objects["selection"] = [
            {
                "properties": {
                    "strictSingleSelect": _lit(single),
                    "singleSelect": _lit(single),
                    "selectAllCheckboxEnabled": _lit("true" if spec.get("select_all") else "false"),
                }
            }
        ]
    if kind in LINE_CHARTS or kind in {"clusteredBarChart", "columnChart", "clusteredColumnChart", "scatterChart"}:
        many = bool(roles.get("Series")) or len(roles.get("Y", [])) + len(roles.get("Y2", [])) > 1
        objects["legend"] = [{"properties": {"show": _lit("true" if many else "false"), "position": _lit("'Top'")}}]
        objects["labels"] = [{"properties": {"show": _lit("false")}}]
    if kind in LINE_CHARTS:
        objects["lineStyles"] = [{"properties": {"strokeWidth": _lit("2D"), "showMarker": _lit("false")}}]
    if "series" in spec:
        objects.update(_series(spec["series"], colours))
    if "secondary_axis" in spec:
        axis = spec["secondary_axis"]
        value_axis = {"secShow": _lit("false" if axis is False else "true")}
        if axis:
            value_axis.update({"secStart": _lit(_number(axis["start"])), "secEnd": _lit(_number(axis["end"]))})
        objects["valueAxis"] = [{"properties": value_axis}]
    if spec.get("axes") is False:
        objects["categoryAxis"] = [{"properties": {"show": _lit("false")}}]
        objects["valueAxis"] = [{"properties": {"show": _lit("false"), "gridlineShow": _lit("false")}}]
        objects["legend"] = [{"properties": {"show": _lit("false")}}]
    if "rule" in spec:
        objects["dataPoint"] = _rule(spec["rule"], colours)
    if "constant_line" in spec:
        objects["y1AxisReferenceLine"] = _constant_line(spec["constant_line"], colours)
    if "gradient" in spec:
        objects["values"] = _gradient(spec["gradient"], colours)
    if "data_bars" in spec:
        objects["columnFormatting"] = _data_bars(spec["data_bars"], colours)
    if spec.get("data_labels"):
        objects["labels"] = [{"properties": {"show": _lit("true")}}]
    if "label_colour_by" in spec:
        labels = objects.setdefault("labels", [{"properties": {}}])[0]["properties"]
        labels["color"] = _by_measure(spec["label_colour_by"])
    if "fill_by" in spec:
        fill = {"fill": _by_measure(spec["fill_by"])}
        objects["dataPoint"] = [{"properties": fill, "selector": {"data": [WILDCARD]}}]
    if "font_by" in spec or "back_by" in spec:
        objects.setdefault("values", []).extend(_field_value_rules(spec))
    if "sentiment" in spec:
        fills = {f"{part}Fill": _solid(colours(spec["sentiment"][part])) for part in ("increase", "decrease", "total")}
        objects["sentimentColors"] = [{"properties": fills}]
    if "matrix" in spec:
        objects.update(_matrix(spec["matrix"], roles["Rows"][0]))
    if "lines" in spec:
        objects.update(_lines(spec["lines"], colours, kind in LINE_CHARTS))
    for key, items in spec.get("objects", {}).items():
        objects[key] = items
    return objects


def _container(spec: dict, colours: Colours) -> dict | None:
    """Container objects: none for a bare visual (it sits directly on the canvas), the card look for a text card,
    the drill buttons in the header of a chart with a hierarchy."""
    if spec.get("bare"):
        bare = {key: [{"properties": {"show": _lit("false")}}] for key in ("background", "border", "dropShadow")}
        bare["padding"] = [{"properties": {side: _lit("0D") for side in ("bottom", "left", "right", "top")}}]
        return bare
    if spec.get("card"):
        return {
            "background": [
                {"properties": {"show": _lit("true"), "color": _solid(colours("surface")), "transparency": _lit("0D")}}
            ],
            "border": [
                {"properties": {"show": _lit("true"), "color": _solid(colours("border")), "radius": _lit("12D")}}
            ],
            "padding": [
                {"properties": {"left": _lit("16D"), "right": _lit("16D"), "top": _lit("12D"), "bottom": _lit("12D")}}
            ],
        }
    if spec.get("drill"):
        header = {
            "show": _lit("true"),
            "showDrillUpButton": _lit("true"),
            "showDrillToggleButton": _lit("true"),
            "showDrillDownLevelButton": _lit("true"),
            "showDrillDownExpandButton": _lit("false"),
            "showOptionsMenu": _lit("false"),
            "showFocusModeButton": _lit("false"),
        }
        return {"visualHeader": [{"properties": header}]}
    return None


def _paragraph(paragraph: str | dict, colours: Colours) -> str | dict:
    """A spec paragraph is a string or {"text", "size", "bold", "colour" (a token)}; the colour becomes hex."""
    if isinstance(paragraph, str):
        return {"text": paragraph, "colour": colours("text")}
    return {**paragraph, "colour": colours(paragraph.get("colour", "text"))}


def _visual(name: str, spec: dict, colours: Colours, sync_group: str | None = None) -> dict:
    """One visual from a spec entry (content, header or tile)."""
    if spec["type"] == "textbox":
        return Visual.textbox(
            name,
            spec["x"],
            spec["y"],
            spec["w"],
            spec["h"],
            [_paragraph(p, colours) for p in spec["paragraphs"]],
            font_size=spec.get("size", 11),
            container=_container(spec, colours),
            alt=spec["alt"],
        )
    roles = {role: [tuple(f) for f in fields] for role, fields in spec.get("roles", {}).items()}
    parameters = {
        role: {"parameter": tuple(p["parameter"]), "default": tuple(p["default"])}
        for role, p in spec.get("field_parameters", {}).items()
    }
    return Visual.from_template(
        spec["type"],
        name,
        spec["x"],
        spec["y"],
        spec["w"],
        spec["h"],
        spec.get("title"),
        roles,
        extra_objects=_formatting(spec, colours),
        alt=spec.get("alt"),
        sort=spec.get("sort"),
        top_n=spec.get("top_n"),
        field_parameters=parameters,
        subtitle=spec.get("subtitle"),
        title_hidden=spec.get("title_hidden", False),
        container=_container(spec, colours),
        filters=spec.get("filters"),
        tooltip_page=spec.get("tooltip_page"),
        sync_group=sync_group,
        selection=spec.get("selection"),
        expand=spec.get("expand"),
        collapse=spec.get("collapse"),
    )


def _slicer_spec(name: str, slicer: dict, row: dict) -> dict:
    spec = {
        "type": "slicer",
        "x": slicer["x"],
        "y": row["y"],
        "w": slicer["w"],
        "h": row["h"],
        "title": name,
        "mode": slicer["mode"],
        "roles": {"Values": [[*slicer["field"], "Column"]]},
    }
    if slicer.get("default"):
        spec["selection"] = {"field": slicer["field"], "values": slicer["default"]}
    if slicer.get("only_with"):
        spec["filters"] = [{"field": slicer["only_with"], "kind": "Measure", "op": ">", "value": 0}]
    for key in ("single", "tiles", "select_all"):
        if slicer.get(key):
            spec[key] = slicer[key]
    return spec


def tile_specs(page: dict, layout: dict) -> list[tuple[str, dict]]:
    """(key, card spec) for the KPI row: n tiles across the row width, each a value card and, with a `delta` or a
    `delta_measure`, the card beside it: Desktop's classic card needs about 80 px of height for a title and a value,
    so the two sit side by side in one row."""
    tiles = page.get("tiles", [])
    if not tiles:
        return []
    n = len(tiles)
    width = (layout["w"] - layout["gutter"] * (n - 1)) / n
    calc_entity, calc_column = layout.get("calculation") or (None, None)
    out = []
    for i, tile in enumerate(tiles):
        x = layout["x"] + i * (width + layout["gutter"])
        label = tile.get("label", tile["measure"])
        measure = [layout["measures"], tile["measure"], "Measure"]
        below = tile.get("delta") or tile.get("delta_measure")
        value_w = round(width * 0.56) if below else width
        value = {
            "type": "card",
            "x": x,
            "y": layout["y"],
            "w": value_w,
            "h": layout["h"],
            "title": label,
            "label_size": 16,
            "roles": {"Values": [measure]},
        }
        if tile.get("item"):
            value["filters"] = [{"field": [calc_entity, calc_column], "in": [tile["item"]]}]
        if tile.get("filters"):
            value["filters"] = tile["filters"]
        if tile.get("colour_by"):
            value["label_colour_by"] = [layout["measures"], tile["colour_by"]]
        out.append((f"tile{i}", value))
        if below:
            if tile.get("delta_measure"):
                bound = [layout["measures"], tile["delta_measure"], "Measure", layout["delta_label"]]
                filters = tile.get("filters", [])
            else:
                bound = [*measure, layout["delta_label"]]
                filters = [{"field": [calc_entity, calc_column], "in": [tile["delta"]]}]
            delta = {
                "type": "card",
                "x": x + value_w,
                "y": layout["y"],
                "w": width - value_w,
                "h": layout["h"],
                "title": f"{label} {layout['delta_label']}",
                "title_hidden": True,
                "label_size": 11,
                "category_label": True,
                "roles": {"Values": [bound]},
                "filters": filters,
            }
            if tile.get("delta_colour"):
                delta["label_colour_by"] = [layout["measures"], tile["delta_colour"]]
            out.append((f"tile{i}-delta", delta))
    return out


def content_name(page_id: str, index: int, visual: dict) -> str:
    """The stable name of a content visual: after its `key` if it has one, else after its position on the page."""
    return stable_name(page_id, visual["key"] if "key" in visual else str(index))


def page_visuals(page: dict, spec: dict, colours: Colours) -> list[dict]:
    """All visuals of a page in reading order (header, slicer row, tiles, content); z and tabOrder follow it."""
    pid = page["id"]
    ordered = []
    if page.get("header", True):
        title = spec["header"]["title"]
        text = title["text"].replace("{page}", page["displayName"])
        ordered.append(
            Visual.textbox(
                stable_name(pid, "header", "title"),
                title["x"],
                title["y"],
                title["w"],
                title["h"],
                [{"text": text, "size": title["size"], "bold": True, "colour": colours("text")}],
                container=_container({"bare": True}, colours),
                alt=text,
            )
        )
        for i, extra in enumerate(spec["header"]["visuals"]):
            ordered.append(_visual(stable_name(pid, "header", str(i)), extra, colours))
    for name in page.get("slicers", []):
        slicer = _slicer_spec(name, spec["slicers"][name], spec["slicer_row"])
        ordered.append(_visual(stable_name(pid, "slicer", name), slicer, colours, sync_group=name))
    note = page.get("slicer_note")
    if note:
        row = spec["slicer_row"]
        ordered.append(
            Visual.textbox(
                stable_name(pid, "slicer", "note"),
                note["x"],
                row["y"],
                note["w"],
                row["h"],
                [{"text": note["text"], "size": 10, "colour": colours("muted")}],
                container=_container({"bare": True}, colours),
                alt=note["text"],
            )
        )
    if page.get("slicers"):
        reset, row = spec["reset"], spec["slicer_row"]
        ordered.append(
            Visual.bookmark_button(
                stable_name(pid, "reset"),
                reset["x"],
                reset.get("y", row["y"]),
                reset["w"],
                reset.get("h", row["h"]),
                reset["label"],
                bookmark_name(pid),
                objects=_button_objects(reset, colours),
            )
        )
    back = page.get("back")
    if back:
        ordered.append(
            Visual.back_button(
                stable_name(pid, "back"),
                back["x"],
                back["y"],
                back["w"],
                back["h"],
                back["label"],
                objects=_button_objects(back, colours),
            )
        )
    for key, tile in tile_specs(page, spec["tiles"]):
        ordered.append(_visual(stable_name(pid, key), tile, colours))
    for index, visual in enumerate(page.get("visuals", [])):
        ordered.append(_visual(content_name(pid, index, visual), visual, colours))
    for position, visual in enumerate(ordered):
        visual["position"]["z"] = visual["position"]["tabOrder"] = position
    return ordered


def _button_objects(button: dict, colours: Colours) -> dict:
    """Label and outline of a Reset or Back button, with a hover state in the accent colour."""
    text = [
        {"properties": {"show": _lit("true")}},
        {
            "properties": {
                "text": _text(button["label"]),
                "fontColor": _solid(colours("text")),
                "fontSize": _lit("10D"),
            },
            "selector": {"id": "default"},
        },
        {"properties": {"fontColor": _solid(colours("accent"))}, "selector": {"id": "hover"}},
    ]
    outline = [
        {"properties": {"show": _lit("true")}},
        {
            "properties": {"lineColor": _solid(colours("border")), "roundEdge": _lit("8D")},
            "selector": {"id": "default"},
        },
        {"properties": {"lineColor": _solid(colours("accent"))}, "selector": {"id": "hover"}},
    ]
    return {"text": text, "outline": outline}


def bookmark_name(page_id: str) -> str:
    return stable_name("bookmark", page_id)


def _interactions(page: dict, spec: dict, visuals: list[dict]) -> list[dict]:
    """visualInteractions of a page from its `interactions` rules (see the module docstring)."""
    pid = page["id"]
    tiles = [stable_name(pid, key) for key, _ in tile_specs(page, spec["tiles"])]
    data = [v["name"] for v in visuals if "query" in v.get("visual", {})]

    def resolve(ref: str) -> list[str]:
        if ref == "tiles":
            return tiles
        if ref.startswith("slicer:"):
            return [stable_name(pid, "slicer", ref.split(":", 1)[1])]
        return [stable_name(pid, ref)]

    out = []
    for rule in page["interactions"]:
        (source,) = resolve(rule["source"])
        if rule["targets"] == "*":
            targets = [name for name in data if name != source]
        else:
            targets = [name for ref in rule["targets"] for name in resolve(ref)]
        unknown = sorted({source, *targets} - {v["name"] for v in visuals})
        if unknown:
            raise ValueError(f"interactions of {pid!r} name unknown visuals {unknown}")
        out += [{"source": source, "target": target, "type": rule.get("type", "NoFilter")} for target in targets]
    return out


def _page_json(page: dict, spec: dict, visuals: list[dict] | None = None) -> dict:
    data = {
        "$schema": SCHEMAS["page.json"],
        "name": page["id"],
        "displayName": page["displayName"],
        "displayOption": "FitToPage",
        "width": page.get("width", spec["canvas"]["width"]),
        "height": page.get("height", spec["canvas"]["height"]),
        "annotations": [{"name": GENERATED, "value": "tools/pbi/pages.json"}],
    }
    if page.get("type") == "Tooltip":
        data["type"] = "Tooltip"
        data["visibility"] = "HiddenInViewMode"
        data["pageBinding"] = {"name": stable_name(page["id"], "binding"), "type": "Tooltip"}
    if page.get("drillthrough"):
        field = _column(*page["drillthrough"]["field"])
        bound = stable_name(page["id"], "drillthrough")
        data["type"] = "Drillthrough"
        data["pageBinding"] = {
            "name": stable_name(page["id"], "binding"),
            "type": "Drillthrough",
            "referenceScope": "Default",
            "acceptsFilterContext": "None",
            "parameters": [{"name": stable_name(page["id"], "parameter"), "boundFilter": bound, "fieldExpr": field}],
        }
        data["filterConfig"] = {
            "filters": [{"name": bound, "field": field, "type": "Categorical", "howCreated": "Drillthrough"}]
        }
    if page.get("hidden"):
        data["visibility"] = "HiddenInViewMode"
    if page.get("interactions"):
        data["visualInteractions"] = _interactions(page, spec, visuals or [])
    return data


def _bookmark_json(page: dict, spec: dict, visuals: list[dict]) -> dict:
    """The Reset bookmark of a page: it applies only to the page's slicers and to the visuals whose spec has a `reset`
    key. Slicers with a `default` get that selection, every other slicer loses its filter (a single-select slicer then
    shows its first value), and a drill chart returns to its top level."""
    pid = page["id"]
    states: dict = {}
    for name in page["slicers"]:
        slicer = spec["slicers"][name]
        vname = stable_name(pid, "slicer", name)
        if slicer.get("default"):
            selection = slicer_selection(*slicer["field"], slicer["default"])
            objects = {"merge": {"general": [{"properties": {"filter": selection}}]}}
        else:
            objects = {"remove": [{"object": "general", "property": "filter"}]}
        states[vname] = {"singleVisual": {"visualType": "slicer", "objects": objects}}
    for index, visual in enumerate(page.get("visuals", [])):
        vname = content_name(pid, index, visual)
        if visual.get("reset") == "remove":
            states[vname] = {
                "singleVisual": {
                    "visualType": visual["type"],
                    "objects": {"remove": [{"object": "general", "property": "filter"}]},
                }
            }
        elif visual.get("reset") == "drill":
            top = visual["roles"]["Category"][0]
            states[vname] = {
                "singleVisual": {"visualType": visual["type"], "activeProjections": {"Category": [field_ref(*top)]}}
            }
        elif visual.get("reset") == "collapse":
            states[vname] = {"singleVisual": {"visualType": visual["type"], "expansionStates": []}}
    known = {v["name"] for v in visuals}
    missing = sorted(set(states) - known)
    if missing:
        raise ValueError(f"bookmark of {pid!r} targets unknown visuals {missing}")
    tpl = json.loads((HERE / "templates" / "bookmark.json").read_text(encoding="utf-8-sig"))
    tpl["$schema"] = SCHEMAS["bookmark.json"]
    tpl["name"] = bookmark_name(pid)
    tpl["displayName"] = f"{spec['reset']['label']} {page['displayName']}"
    tpl["explorationState"]["activeSection"] = pid
    tpl["explorationState"]["sections"] = {pid: {"visualContainers": states}}
    tpl["options"] = {"targetVisualNames": sorted(states), "applyOnlyToTargetVisuals": True}
    return tpl


def report_json() -> dict:
    """report.json: base theme, the project theme as registered resource, and the report settings."""
    base = SCHEMAS["baseTheme"]
    theme = PROJECT["theme"]["file"]
    return {
        "$schema": SCHEMAS["report.json"],
        "themeCollection": {
            "baseTheme": {
                "name": base["name"],
                "reportVersionAtImport": base["reportVersionAtImport"],
                "type": "SharedResources",
            },
            "customTheme": {
                "name": theme,
                "reportVersionAtImport": base["reportVersionAtImport"],
                "type": "RegisteredResources",
            },
        },
        "resourcePackages": [
            {
                "name": "SharedResources",
                "type": "SharedResources",
                "items": [{"name": base["name"], "path": f"BaseThemes/{base['name']}.json", "type": "BaseTheme"}],
            },
            {
                "name": "RegisteredResources",
                "type": "RegisteredResources",
                "items": [{"name": theme, "path": theme, "type": "CustomTheme"}],
            },
        ],
        "settings": {
            "allowChangeFilterTypes": True,
            "defaultDrillFilterOtherVisuals": True,
            "defaultFilterActionIsDataFilter": True,
            "exportDataMode": "AllowSummarized",
            "useDefaultAggregateDisplayName": True,
            "useEnhancedTooltips": True,
            "useStylableVisualContainerHeader": True,
        },
    }


def _remove_generated_pages() -> None:
    pages_dir = DEFINITION / "pages"
    for page_json in sorted(pages_dir.glob("*/page.json")):
        data = json.loads(page_json.read_text(encoding="utf-8-sig"))
        if any(a.get("name") == GENERATED for a in data.get("annotations", [])):
            shutil.rmtree(page_json.parent)


def main() -> int:
    spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    colours = Colours.from_kit()
    theme = REPORT / "StaticResources" / "RegisteredResources" / PROJECT["theme"]["file"]
    if not theme.is_file():
        raise FileNotFoundError(f"{theme} is missing: run tools/pbi/build_theme.py first")
    pages = spec["pages"]
    ids = [p["id"] for p in pages]
    if len(set(ids)) != len(ids):
        raise ValueError(f"duplicate page ids in pages.json: {ids}")
    _remove_generated_pages()
    bookmarks = []
    count = 0
    for page in pages:
        pdir = DEFINITION / "pages" / page["id"]
        visuals = page_visuals(page, spec, colours)
        write_json(pdir / "page.json", _page_json(page, spec, visuals))
        for v in visuals:
            write_json(pdir / "visuals" / v["name"] / "visual.json", v)
        count += len(visuals)
        if page.get("slicers"):
            bookmarks.append(_bookmark_json(page, spec, visuals))
    write_json(
        DEFINITION / "pages" / "pages.json",
        {"$schema": SCHEMAS["pages.json"], "pageOrder": ids, "activePageName": ids[0]},
    )
    bdir = DEFINITION / "bookmarks"
    if bdir.exists():
        shutil.rmtree(bdir)
    for data in bookmarks:
        write_json(bdir / f"{data['name']}.bookmark.json", data)
    group = {
        "name": stable_name("bookmark-group", spec["reset"]["group"]),
        "displayName": spec["reset"]["group"],
        "children": [b["name"] for b in bookmarks],
    }
    write_json(bdir / "bookmarks.json", {"$schema": SCHEMAS["bookmarks.json"], "items": [group]})
    write_json(DEFINITION / "report.json", report_json())
    print(
        f"wrote {len(pages)} pages, {count} visuals and {len(bookmarks)} bookmarks to "
        f"{DEFINITION.relative_to(ROOT).as_posix()}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
