"""Independent pandas reference for the measures of spec section 7, in integer cents.

    uv run python tools/reference.py [--data data]     # prints R1 to R13, the Python column of docs/reconciliation.md

The files are read the way Power Query reads them (ADR 0002) and nothing is imported from tools/make_data.py: the
ledger export turns into profit contribution with `-amount`, the budget and forecast sheets are unpivoted like
`Table.UnpivotOtherColumns` and multiplied by the account sign. The facts become one integer-cent cube (scenario,
cost centre and account, 36 months from 2023-01) with a mask of the cells that have a row, so "blank" means "no
row" exactly as in DAX. A context names the months in the date filter, the cost centres, and the P&L line,
subgroup and account in scope (matrix rows); the measures follow the DAX of section 7 line by line.
"""

from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
FIRST_YEAR = 2023
MONTHS = 36
MONTH_NAMES = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
SCENARIOS = ("Actual", "Budget", "Forecast")
PERSONNEL = ("Direct personnel", "Overhead personnel")
Value = int | float | None  # cents for amounts, a fraction for ratio lines, None for blank


def t_of(year: int, month: int) -> int:
    return (year - FIRST_YEAR) * 12 + month - 1


def period(year: int, first: int = 1, last: int = 12) -> frozenset[int]:
    """The month indices of months first to last of a year (the Year slicer and the Months slider)."""
    return frozenset(t_of(year, m) for m in range(first, last + 1))


def year_of(t: int) -> int:
    return FIRST_YEAR + t // 12


def ytd(months: frozenset[int]) -> frozenset[int]:
    """DATESYTD: January of the year of the last month in context up to that month."""
    if not months:
        return frozenset()
    last = max(months)
    return frozenset(range(last - last % 12, last + 1))


def divide(a: Value, b: Value) -> float | None:
    return None if a is None or b is None or b == 0 else a / b


# ---------------------------------------------------------------- reading the files (Power Query, ADR 0002)


def cents(text: str) -> int:
    """A two-decimal amount of the export as integer cents, without passing through a float."""
    text = text.strip()
    sign = -1 if text.startswith("-") else 1
    whole, _, frac = text.lstrip("+-").partition(".")
    return sign * (int(whole) * 100 + int((frac + "00")[:2]))


def read_gl(path: Path) -> pd.DataFrame:
    """src_GL: period, cost centre, account and the ledger amount; Amount = -amount (profit contribution)."""
    gl = pd.read_csv(path, dtype=str, keep_default_na=False)
    year = gl["period"].str[:4].astype(int)
    month = gl["period"].str[5:7].astype(int)
    return pd.DataFrame(
        {
            "t": (year - FIRST_YEAR) * 12 + month - 1,
            "cost_centre": gl["cost_centre"],
            "account": gl["account"],
            "scenario": "Actual",
            "cents": [-cents(v) for v in gl["amount"]],
        }
    )


def read_budget(path: Path) -> pd.DataFrame:
    """src_Budget: every sheet from row 4, rows of a cost centre only, the month columns unpivoted, null and zero
    values dropped; scenario and year from the sheet name. Natural sign, EUR (scenario, year, month, cost_centre,
    account, value)."""
    sheets = pd.read_excel(path, sheet_name=None, header=3, dtype={"Cost centre": str, "Account": str})
    frames = []
    for name, sheet in sheets.items():
        scenario, year = name.split(" ", 1)
        keep = sheet[sheet["Cost centre"].fillna("").str.startswith("CC")]
        months = [c for c in keep.columns if c in MONTH_NAMES]
        long = keep[["Cost centre", "Account", *months]].melt(
            id_vars=["Cost centre", "Account"], var_name="Month", value_name="Value"
        )
        long = long[long["Value"].notna() & (long["Value"] != 0)]
        frames.append(
            pd.DataFrame(
                {
                    "scenario": scenario,
                    "year": int(year),
                    "month": [MONTH_NAMES.index(m) + 1 for m in long["Month"]],
                    "cost_centre": long["Cost centre"].to_numpy(),
                    "account": long["Account"].to_numpy(),
                    "value": long["Value"].to_numpy(),
                }
            )
        )
    return pd.concat(frames, ignore_index=True)


@dataclass(frozen=True)
class Line:
    key: str
    name: str
    type: str  # Group, Subtotal, Ratio
    group: str
    bound: int | None
    sign: int
    sort: int


@dataclass(frozen=True)
class Ctx:
    """A filter context: the months in the date filter (indices from 2023-01), the cost centres (None: all), and the
    P&L line, subgroup and account in scope (None: not in scope)."""

    months: frozenset[int]
    ccs: frozenset[str] | None = None
    line: str | None = None
    subgroup: str | None = None
    account: str | None = None


class Reference:
    def __init__(
        self,
        facts: pd.DataFrame,
        accounts: pd.DataFrame,
        layout: pd.DataFrame,
        cost_centres: pd.DataFrame,
    ) -> None:
        self.layout = {
            r.line_key: Line(
                r.line_key,
                r.line,
                r.line_type,
                r.group if isinstance(r.group, str) else "",
                None if pd.isna(r.bound) else int(r.bound),
                int(r.sign),
                int(r.sort_order),
            )
            for r in layout.sort_values("sort_order").itertuples()
        }
        group_line = {line.group: line for line in self.layout.values() if line.type == "Group"}
        acc = accounts.sort_values("sort_order").reset_index(drop=True)
        self.accounts = pd.DataFrame(
            {
                "account": acc["account"],
                "name": acc["name"],
                "label": acc["account"] + " " + acc["name"],
                "group": acc["group"],
                "group_sort": [group_line[g].sort for g in acc["group"]],
                "subgroup": acc["subgroup"],
                "subgroup_sort": acc.groupby("subgroup")["sort_order"].transform("min"),
                "sign": acc["sign"].astype(int),
                "sort": acc["sort_order"].astype(int),
                "line_key": [group_line[g].key for g in acc["group"]],
            }
        )
        self.cost_centres = cost_centres.sort_values("sort_order").reset_index(drop=True)
        self.facts = facts.reset_index(drop=True)
        pairs = sorted(set(zip(self.facts["cost_centre"], self.facts["account"], strict=True)))
        self.pairs = pairs
        self._pair_index = {pair: i for i, pair in enumerate(pairs)}
        self.cube = np.zeros((len(SCENARIOS), len(pairs), MONTHS), dtype=np.int64)
        self.mask = np.zeros_like(self.cube, dtype=bool)
        s = self.facts["scenario"].map(SCENARIOS.index).to_numpy()
        p = np.array([self._pair_index[k] for k in zip(self.facts["cost_centre"], self.facts["account"], strict=True)])
        t = self.facts["t"].to_numpy()
        if self.mask[s, p, t].any() or len(set(zip(s, p, t, strict=True))) != len(s):
            raise ValueError("more than one fact row for a scenario, cost centre, account and month")
        self.cube[s, p, t] = self.facts["cents"].to_numpy()
        self.mask[s, p, t] = True
        self._attr = self.accounts.set_index("account")
        self.last_actual = int(self.facts.loc[self.facts["scenario"] == "Actual", "t"].max())

    @classmethod
    def from_frames(
        cls,
        gl: pd.DataFrame,
        plan: pd.DataFrame,
        accounts: pd.DataFrame,
        layout: pd.DataFrame,
        cost_centres: pd.DataFrame,
    ) -> Reference:
        """FactGL: the budget and forecast rows times the account sign, combined with the actuals (ADR 0002)."""
        sign = accounts.set_index("account")["sign"].astype(int)
        values = plan["value"].to_numpy(dtype=float)
        plan_facts = pd.DataFrame(
            {
                "t": (plan["year"].astype(int) - FIRST_YEAR) * 12 + plan["month"].astype(int) - 1,
                "cost_centre": plan["cost_centre"].astype(str),
                "account": plan["account"].astype(str),
                "scenario": plan["scenario"].astype(str),
                "cents": [
                    int(round(v * 100)) * int(sign[a]) for v, a in zip(values, plan["account"].astype(str), strict=True)
                ],
            }
        )
        facts = pd.concat([gl, plan_facts], ignore_index=True)
        return cls(facts, accounts, layout, cost_centres)

    # ------------------------------------------------------------ the base measure

    def _pairs(self, ccs: frozenset[str] | None, accounts: set[str]) -> list[int]:
        return [i for i, (cc, acc) in enumerate(self.pairs) if acc in accounts and (ccs is None or cc in ccs)]

    def amount(self, cells: set[tuple[str, int]], ccs: frozenset[str] | None, accounts: set[str]) -> int | None:
        """[Amount]: the signed sum over the fact rows in the cells (scenario, month); None when there is no row."""
        rows = self._pairs(ccs, accounts)
        if not rows or not cells:
            return None
        total, found = 0, False
        for scenario, t in cells:
            s = SCENARIOS.index(scenario)
            m = self.mask[s, rows, t]
            if m.any():
                found = True
                total += int(self.cube[s, rows, t][m].sum())
        return total if found else None

    def rows(self, cells: set[tuple[str, int]], ccs: frozenset[str] | None = None) -> int:
        """[Rows]: COUNTROWS(FactGL) in the cells."""
        idx = self._pairs(ccs, set(self.accounts["account"]))
        return int(sum(self.mask[SCENARIOS.index(s), idx, t].sum() for s, t in cells))

    def _scope(self, ctx: Ctx) -> set[str]:
        """The accounts left by the subgroup and account in scope."""
        a = self.accounts
        keep = pd.Series(True, index=a.index)
        if ctx.subgroup is not None:
            keep &= a["subgroup"] == ctx.subgroup
        if ctx.account is not None:
            keep &= a["account"] == ctx.account
        return set(a.loc[keep, "account"])

    def _line_accounts(self, key: str) -> set[str]:
        return set(self.accounts.loc[self.accounts["line_key"] == key, "account"])

    def _below(self, bound: int) -> set[str]:
        return set(self.accounts.loc[self.accounts["group_sort"] < bound, "account"])

    def is_ratio(self, ctx: Ctx) -> bool:
        return ctx.line is not None and self.layout[ctx.line].type == "Ratio"

    def line_sign(self, ctx: Ctx) -> int:
        return 1 if ctx.line is None else self.layout[ctx.line].sign

    def pnl_value(self, ctx: Ctx, cells: set[tuple[str, int]]) -> Value:
        """[P&L Value] in the given scenario cells."""
        scope = self._scope(ctx)
        if ctx.line is None:
            return self.amount(cells, ctx.ccs, scope)  # no line in context: the EBIT contribution
        line = self.layout[ctx.line]
        if line.type == "Group":
            v = self.amount(cells, ctx.ccs, scope & self._line_accounts(line.key))
            return None if v is None else v * line.sign
        if ctx.subgroup is not None or ctx.account is not None:
            return None
        up_to = self.amount(cells, ctx.ccs, self._below(line.bound))
        if line.type == "Subtotal":
            return up_to
        return divide(up_to, self.amount(cells, ctx.ccs, self._line_accounts("REV")))

    # ------------------------------------------------------------ scenarios

    @staticmethod
    def cells(scenario: str, months: frozenset[int]) -> set[tuple[str, int]]:
        return {(scenario, t) for t in months}

    def actual(self, ctx: Ctx) -> Value:
        return self.pnl_value(ctx, self.cells("Actual", ctx.months))

    def budget(self, ctx: Ctx) -> Value:
        return self.pnl_value(ctx, self.cells("Budget", ctx.months))

    def forecast(self, ctx: Ctx) -> Value:
        return self.pnl_value(ctx, self.cells("Forecast", ctx.months))

    def outlook(self, ctx: Ctx) -> Value:
        """Actuals up to the last actual month, the forecast after it (one tuple filter, so ratios stay right)."""
        cells = {("Actual", t) for t in ctx.months if t <= self.last_actual}
        cells |= {("Forecast", t) for t in ctx.months if t > self.last_actual}
        return self.pnl_value(ctx, cells)

    def budget_closed(self, ctx: Ctx) -> Value:
        return self.budget(replace(ctx, months=frozenset(t for t in ctx.months if t <= self.last_actual)))

    # ------------------------------------------------------------ variance

    def variance(self, ctx: Ctx) -> Value:
        a, b = self.actual(ctx), self.budget_closed(ctx)
        if a is None and b is None:
            return None
        diff = (a or 0) - (b or 0)
        return diff * 100 if self.is_ratio(ctx) else diff

    def variance_pct(self, ctx: Ctx) -> float | None:
        if self.is_ratio(ctx):
            return None
        b = self.budget_closed(ctx)
        return divide(self.variance(ctx), None if b is None else abs(b))

    def favourable(self, ctx: Ctx) -> int | None:
        v = self.variance(ctx)
        if v is None:
            return None
        p = self.variance_pct(ctx)
        neutral = abs(v) < 0.1 if self.is_ratio(ctx) else (p is not None and abs(p) < 0.01)
        if neutral:
            return 0
        product = v * self.line_sign(ctx)
        return (product > 0) - (product < 0)

    def favourable_label(self, ctx: Ctx) -> str | None:
        f = self.favourable(ctx)
        return None if f is None else {1: "Fav.", -1: "Unfav.", 0: "On plan"}[f]

    def profit_impact(self, ctx: Ctx) -> Value:
        if self.is_ratio(ctx):
            return None
        v = self.variance(ctx)
        return None if v is None else v * self.line_sign(ctx)

    # ------------------------------------------------------------ time

    def full_year(self, ctx: Ctx) -> Ctx:
        return replace(ctx, months=period(year_of(max(ctx.months)))) if ctx.months else ctx

    def full_year_outlook(self, ctx: Ctx) -> Value:
        return self.outlook(self.full_year(ctx)) if ctx.months else None

    def budget_full_year(self, ctx: Ctx) -> Value:
        return self.budget(self.full_year(ctx)) if ctx.months else None

    def outlook_vs_budget(self, ctx: Ctx) -> Value:
        f, b = self.full_year_outlook(ctx), self.budget_full_year(ctx)
        if f is None and b is None:
            return None
        diff = (f or 0) - (b or 0)
        return diff * 100 if self.is_ratio(ctx) else diff

    def actual_ytd(self, ctx: Ctx) -> Value:
        if not ctx.months or min(ctx.months) > self.last_actual:
            return None
        return self.actual(replace(ctx, months=ytd(ctx.months)))

    def budget_ytd(self, ctx: Ctx) -> Value:
        return self.budget(replace(ctx, months=ytd(ctx.months)))

    def outlook_ytd(self, ctx: Ctx) -> Value:
        return self.outlook(replace(ctx, months=ytd(ctx.months)))

    def pnl_statement(self, ctx: Ctx, scenario: str = "Actual") -> Value:
        if scenario == "Budget":
            return self.budget(ctx)
        if scenario == "Forecast":
            return self.outlook(ctx)
        return self.actual(ctx)

    def pnl_matrix(self, ctx: Ctx, column: int, scenario: str = "Actual") -> Value:
        """[P&L Matrix] in column 1 to 12 (a month), 13 (YTD) or 14 (Full year)."""
        if column <= 12:
            months = frozenset(t for t in ctx.months if t % 12 == column - 1)
            return self.pnl_statement(replace(ctx, months=months), scenario)
        if column == 13:
            return self.pnl_statement(replace(ctx, months=ytd(ctx.months)), scenario)
        return self.budget_full_year(ctx) if scenario == "Budget" else self.full_year_outlook(ctx)

    # ------------------------------------------------------------ lines and ratios (actual, selected period)

    def _line(self, ctx: Ctx, key: str) -> Ctx:
        return replace(ctx, line=key)

    def revenue(self, ctx: Ctx) -> Value:
        return self.actual(self._line(ctx, "REV"))

    def gross_margin_pct(self, ctx: Ctx) -> Value:
        return self.actual(self._line(ctx, "GPM"))

    def ebitda_margin_pct(self, ctx: Ctx) -> Value:
        return self.actual(self._line(ctx, "EBITDAM"))

    def opex_pct(self, ctx: Ctx) -> float | None:
        return divide(self.actual(self._line(ctx, "OPEX")), self.revenue(ctx))

    def personnel_cost(self, ctx: Ctx) -> int | None:
        accounts = set(self.accounts.loc[self.accounts["subgroup"].isin(PERSONNEL), "account"])
        v = self.amount(self.cells("Actual", ctx.months), ctx.ccs, accounts)
        return None if v is None else -v

    def personnel_pct(self, ctx: Ctx) -> float | None:
        return divide(self.personnel_cost(ctx), self.revenue(ctx))

    # ------------------------------------------------------------ rows of the P&L matrix

    def matrix_rows(self, ccs: frozenset[str] | None = None) -> list[Ctx]:
        """Line, subgroup and account rows in matrix order (subtotals at the top), for the lines of the layout."""
        out = []
        a = self.accounts
        present = {acc for cc, acc in self.pairs if ccs is None or cc in ccs}
        for line in self.layout.values():
            out.append(Ctx(frozenset(), ccs, line.key))
            if line.type != "Group":
                continue
            mine = a[(a["line_key"] == line.key) & a["account"].isin(present)].sort_values("sort")
            for subgroup in mine.sort_values("subgroup_sort")["subgroup"].drop_duplicates():
                out.append(Ctx(frozenset(), ccs, line.key, subgroup))
                for acc in mine.loc[mine["subgroup"] == subgroup, "account"]:
                    out.append(Ctx(frozenset(), ccs, line.key, subgroup, acc))
        return out

    def label(self, account: str) -> str:
        return str(self._attr.loc[account, "label"])


def read_dims(folder: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """src_Accounts, src_Layout and src_CostCentres: chart of accounts, P&L layout and cost centres."""
    accounts = pd.read_csv(folder / "chart_of_accounts.csv", dtype={"account": str})
    layout = pd.read_csv(folder / "pnl_layout.csv", dtype={"group": str})
    cost_centres = pd.read_csv(folder / "cost_centres.csv", dtype=str, keep_default_na=False)
    cost_centres["sort_order"] = cost_centres["sort_order"].astype(int)
    return accounts, layout, cost_centres


def load(folder: Path = ROOT / "data") -> Reference:
    return Reference.from_frames(
        read_gl(folder / "gl_actuals.csv"), read_budget(folder / "budget.xlsx"), *read_dims(folder)
    )


# ---------------------------------------------------------------- reconciliation checks R1 to R13 (spec 10)

ALL_YEAR_2025 = period(2025)
CLOSED_2025 = period(2025, 1, 9)
CHECKS = (  # id, label, kind
    ("R1", "Fact rows", "count"),
    ("R2", "Actual revenue 2023", "amount"),
    ("R3", "Actual EBITDA 2024", "amount"),
    ("R4", "Actual EBIT Jan to Sep 2025", "amount"),
    ("R5", "Actual gross margin % Jan to Sep 2025", "ratio"),
    ("R6", "Budget revenue 2025, full year", "amount"),
    ("R7", "Budget EBITDA 2025, closed months", "amount"),
    ("R8", "Forecast revenue Oct to Dec 2025", "amount"),
    ("R9", "Full-year outlook EBIT 2025", "amount"),
    ("R10", "EBITDA variance Jan to Sep 2025, Security Services", "amount"),
    ("R11", "Actual operating expenses Jan to Sep 2025", "amount"),
    ("R12", "Personnel cost % of revenue 2024", "ratio"),
    ("R13", "Revenue Jan to Sep 2025, Security Services", "amount"),
)


def checks(ref: Reference) -> dict[str, int | float]:
    """R1 to R13 as Power BI shows them: amounts in EUR (two decimals), ratios as fractions, counts as integers."""
    cc30 = frozenset({"CC30"})
    every = frozenset(range(MONTHS))
    cents_values = {
        "R2": ref.revenue(Ctx(period(2023))),
        "R3": ref.actual(Ctx(period(2024), line="EBITDA")),
        "R4": ref.actual(Ctx(CLOSED_2025, line="EBIT")),
        "R6": ref.budget(Ctx(ALL_YEAR_2025, line="REV")),
        "R7": ref.budget_closed(Ctx(ALL_YEAR_2025, line="EBITDA")),
        "R8": ref.forecast(Ctx(ALL_YEAR_2025, line="REV")),
        "R9": ref.full_year_outlook(Ctx(ALL_YEAR_2025, line="EBIT")),
        "R10": ref.variance(Ctx(CLOSED_2025, cc30, "EBITDA")),
        "R11": ref.actual(Ctx(CLOSED_2025, line="OPEX")),
        "R13": ref.revenue(Ctx(CLOSED_2025, cc30)),
    }
    out: dict[str, int | float] = {"R1": sum(ref.rows(ref.cells(s, every)) for s in SCENARIOS)}
    out |= {k: v / 100 for k, v in cents_values.items()}
    out["R5"] = ref.gross_margin_pct(Ctx(CLOSED_2025))
    out["R12"] = ref.personnel_pct(Ctx(period(2024)))
    return {cid: out[cid] for cid, _, _ in CHECKS}


def shown(cid: str, value: int | float) -> str:
    kind = {c: k for c, _, k in CHECKS}[cid]
    if kind == "count":
        return str(int(value))
    if kind == "ratio":
        return f"{value:.6f}"
    return f"{value:.2f}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Print the reconciliation values R1 to R13 from the data files.")
    parser.add_argument("--data", type=Path, default=ROOT / "data")
    args = parser.parse_args(argv)
    ref = load(args.data)
    labels = {c: label for c, label, _ in CHECKS}
    for cid, value in checks(ref).items():
        print(f"{cid:<4} {shown(cid, value):>15}  {labels[cid]}")
    return 0 if math.isfinite(sum(checks(ref).values())) else 1


if __name__ == "__main__":
    sys.exit(main())
