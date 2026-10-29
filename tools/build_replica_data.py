"""Build web/assets/data/kaldora.json, the data of the replica, with tools/reference.py.

kaldora.json holds:
  meta          seed, SHA-256 of the six data files, first month, last actual month (no timestamps)
  accounts      the chart of accounts with label, group sort, subgroup sort and line key
  layout        the ten P&L lines
  cost_centres  code, name and type of the six cost centres
  facts         per scenario, "CC10|4000" -> 36 monthly amounts from 2023-01 in integer cents, signed as profit
                contribution (income +, expense -), null where the model has no row
  headline      the reference values of the states S1 to S4 (spec section 10); tests/js/pnl.test.mjs recomputes
                them with web/assets/pnl.js from the facts, tests/test_parity.py checks them against the reference

Usage (from the repository root):
    uv run python tools/build_replica_data.py           # write the file
    uv run python tools/build_replica_data.py --check   # exit 1 if it differs from a fresh build
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import make_data
import reference as ref
from reference import SCENARIOS, Ctx, period

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
REPLICA = ROOT / "web" / "assets" / "data" / "kaldora.json"
GROUP_LINES = ("REV", "COS", "OPEX", "DA")
STATES = {
    "S1": {"year": 2025, "from": 1, "to": 12, "ccs": [], "scenario": "Actual"},
    "S2": {"year": 2024, "from": 1, "to": 12, "ccs": [], "scenario": "Actual"},
    "S3": {"year": 2025, "from": 4, "to": 6, "ccs": ["CC10", "CC20"], "scenario": "Forecast"},
    "S4": {"line": "EBITDA", "ccs": []},
}


def _ccs(state: dict[str, Any]) -> frozenset[str] | None:
    return frozenset(state["ccs"]) if state["ccs"] else None


def _ctx(state: dict[str, Any], **scope: Any) -> Ctx:
    return Ctx(period(state["year"], state["from"], state["to"]), _ccs(state), **scope)


def lines(model: ref.Reference, state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out = {}
    for key in model.layout:
        ctx = _ctx(state, line=key)
        out[key] = {
            "actual": model.actual(ctx),
            "budget": model.budget(ctx),
            "budgetClosed": model.budget_closed(ctx),
            "fullYearOutlook": model.full_year_outlook(ctx),
            "budgetFullYear": model.budget_full_year(ctx),
            "variance": model.variance(ctx),
            "variancePct": model.variance_pct(ctx),
            "favourable": model.favourable(ctx),
        }
    return out


def headline(model: ref.Reference) -> dict[str, Any]:
    s1, s2, s3, s4 = (STATES[k] for k in ("S1", "S2", "S3", "S4"))
    waterfall = {key: model.profit_impact(_ctx(s1, line=key)) for key in GROUP_LINES}
    waterfall["total"] = model.variance(_ctx(s1, line="EBIT"))
    months = _ctx(s1).months
    centres = model.cost_centres["cost_centre"]
    departments = {cc: model.profit_impact(Ctx(months, frozenset({cc}), "EBITDA")) for cc in centres}
    rows = []
    scenario = s3["scenario"]
    for row in model.matrix_rows(_ccs(s3)):
        ctx = _ctx(s3, line=row.line, subgroup=row.subgroup, account=row.account)
        cells = [model.pnl_matrix(ctx, col, scenario) for col in range(1, 15)]
        if any(v is not None for v in cells):
            rows.append({"line": row.line, "subgroup": row.subgroup, "account": row.account, "cells": cells})
    trend = {}
    for name in ("actual", "budget", "forecast"):
        measure = getattr(model, name)
        trend[name] = [measure(Ctx(frozenset({t}), _ccs(s4), s4["line"])) for t in range(ref.MONTHS)]
    s2_lines = {k: {"actual": v["actual"], "budget": v["budget"]} for k, v in lines(model, s2).items()}
    return {
        "S1": {"state": s1, "lines": lines(model, s1), "waterfall": waterfall, "departments": departments},
        "S2": {"state": s2, "lines": s2_lines},
        "S3": {"state": s3, "rows": rows},
        "S4": {"state": s4, **trend},
    }


def build(model: ref.Reference, data: Path = DATA) -> dict[str, Any]:
    files = {name: hashlib.sha256((data / name).read_bytes()).hexdigest() for name in make_data.FILES}
    accounts = [
        {
            "account": r.account,
            "name": r.name,
            "label": r.label,
            "group": r.group,
            "groupSort": int(r.group_sort),
            "subgroup": r.subgroup,
            "subgroupSort": int(r.subgroup_sort),
            "sign": int(r.sign),
            "sort": int(r.sort),
            "line": r.line_key,
        }
        for r in model.accounts.itertuples()
    ]
    layout = [
        {
            "key": line.key,
            "line": line.name,
            "type": line.type,
            "group": line.group or None,
            "bound": line.bound,
            "sign": line.sign,
            "sort": line.sort,
        }
        for line in model.layout.values()
    ]
    centres = [{"code": r.cost_centre, "name": r.name, "type": r.type} for r in model.cost_centres.itertuples()]
    facts: dict[str, dict[str, list[int | None]]] = {}
    for s, scenario in enumerate(SCENARIOS):
        facts[scenario] = {
            f"{cc}|{acc}": [int(v) if m else None for v, m in zip(model.cube[s, p], model.mask[s, p], strict=True)]
            for p, (cc, acc) in enumerate(model.pairs)
            if model.mask[s, p].any()
        }
    meta = {
        "seed": make_data.SEED,
        "files": files,
        "firstMonth": f"{ref.FIRST_YEAR}-01",
        "months": ref.MONTHS,
        "lastActual": f"{ref.year_of(model.last_actual)}-{model.last_actual % 12 + 1:02d}",
        "lastActualIndex": model.last_actual,
    }
    return {
        "meta": meta,
        "accounts": accounts,
        "layout": layout,
        "cost_centres": centres,
        "facts": facts,
        "headline": headline(model),
    }


def dumps(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build web/assets/data/kaldora.json from the data files.")
    parser.add_argument("--data", type=Path, default=DATA)
    parser.add_argument("--check", action="store_true", help="compare a fresh build with the committed file")
    args = parser.parse_args(argv)
    text = dumps(build(ref.load(args.data), args.data))
    rel = REPLICA.relative_to(ROOT).as_posix()
    if args.check:
        if not REPLICA.exists() or REPLICA.read_text(encoding="utf-8") != text:
            print(f"FAIL {rel} differs from a fresh build")
            return 1
        print(f"{rel} ({len(text.encode()):,} bytes) matches a fresh build")
        return 0
    REPLICA.parent.mkdir(parents=True, exist_ok=True)
    REPLICA.write_bytes(text.encode("utf-8"))
    print(f"wrote {rel} ({len(text.encode()):,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
