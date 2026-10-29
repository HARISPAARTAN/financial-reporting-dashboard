"""Generate the Kaldora Facility Services data files: the ledger export, the budget workbook and four CSV files.

Usage (from the repository root):
    uv run python tools/make_data.py [--out data] [--check]

Seed 43 drives numpy.random.default_rng (the noise on the actuals) and NAME_SEED drives Faker (the seven people of
cost_centres.csv and security.csv), so every run writes the same bytes; NAME_SEED changes names and e-mail addresses
only, never a number. The workbook is a zip without compression whose entries and document properties carry the
fixed time 2025-10-06 00:00, so it is byte-identical on every platform. --check regenerates into a temporary folder
and compares the SHA-256 of all six files; it exits 1 on the first difference.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import io
import math
import re
import sys
import tempfile
import unicodedata
import zipfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from faker import Faker
from openpyxl import Workbook
from openpyxl.styles import Font

ROOT = Path(__file__).resolve().parents[1]
SEED = 43
NAME_SEED = 43  # raised only if a generated person name collides with the owner's never-committed banned list
EXPORT_TIME = dt.datetime(2025, 10, 6, 0, 0)
DOMAIN = "kaldora.example"
COMPANY = "Kaldora Facility Services"
YEARS = (2023, 2024, 2025)
MONTHS = 36  # 2023-01 to 2025-12
ACTUAL_MONTHS = 33  # 2023-01 to 2025-09, closed in the ledger
MONTH_NAMES = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
FILES = ("gl_actuals.csv", "budget.xlsx", "chart_of_accounts.csv", "cost_centres.csv", "pnl_layout.csv", "security.csv")

# ---------------------------------------------------------------- master data (spec 4.2 to 4.4)

REV, COS, OPEX, DA = "Revenue", "Cost of services", "Operating expenses", "Depreciation and amortisation"
# account, name, group, subgroup; the sign follows the group, the sort order is the position (1 to 40)
ACCOUNTS = (
    ("4000", "Cleaning contracts", REV, "Contract revenue"),
    ("4010", "Maintenance contracts", REV, "Contract revenue"),
    ("4020", "Security contracts", REV, "Contract revenue"),
    ("4030", "Catering contracts", REV, "Contract revenue"),
    ("4100", "Special cleaning and ad-hoc jobs", REV, "Project and ad-hoc revenue"),
    ("4110", "Repairs and call-outs", REV, "Project and ad-hoc revenue"),
    ("4120", "Event security", REV, "Project and ad-hoc revenue"),
    ("4130", "Event catering", REV, "Project and ad-hoc revenue"),
    ("4200", "Material recharges", REV, "Other revenue"),
    ("4900", "Revenue reductions", REV, "Other revenue"),
    ("5000", "Direct wages", COS, "Direct personnel"),
    ("5010", "Overtime and shift premiums", COS, "Direct personnel"),
    ("5020", "Employer social security, direct staff", COS, "Direct personnel"),
    ("5030", "Temporary staff", COS, "Direct personnel"),
    ("5100", "Cleaning agents and consumables", COS, "Materials and consumables"),
    ("5110", "Spare parts and technical materials", COS, "Materials and consumables"),
    ("5120", "Food and beverages", COS, "Materials and consumables"),
    ("5130", "Workwear and protective equipment", COS, "Materials and consumables"),
    ("5200", "Subcontracted services", COS, "Subcontractors"),
    ("5300", "Vehicle running costs", COS, "Vehicles and equipment"),
    ("5310", "Equipment rental and maintenance", COS, "Vehicles and equipment"),
    ("6000", "Salaries, management and administration", OPEX, "Overhead personnel"),
    ("6010", "Employer social security, salaried staff", OPEX, "Overhead personnel"),
    ("6020", "Training and recruitment", OPEX, "Overhead personnel"),
    ("6100", "Rent and service charges", OPEX, "Premises"),
    ("6110", "Energy and utilities", OPEX, "Premises"),
    ("6200", "IT services, licences and telecommunication", OPEX, "IT and communication"),
    ("6300", "Advertising and campaigns", OPEX, "Sales and marketing"),
    ("6310", "Trade fairs and events", OPEX, "Sales and marketing"),
    ("6320", "Sales commissions", OPEX, "Sales and marketing"),
    ("6400", "Insurance", OPEX, "Administration and other"),
    ("6410", "Legal, audit and consulting", OPEX, "Administration and other"),
    ("6420", "Office supplies and postage", OPEX, "Administration and other"),
    ("6430", "Travel expenses", OPEX, "Administration and other"),
    ("6450", "Bad debt expense", OPEX, "Administration and other"),
    ("6490", "Other operating expenses", OPEX, "Administration and other"),
    ("7000", "Depreciation of vehicles", DA, "Depreciation and amortisation"),
    ("7010", "Depreciation of machinery and equipment", DA, "Depreciation and amortisation"),
    ("7020", "Depreciation of IT and office equipment", DA, "Depreciation and amortisation"),
    ("7030", "Amortisation of software", DA, "Depreciation and amortisation"),
)
GROUP_SIGN = {REV: 1, COS: -1, OPEX: -1, DA: -1}
NAME = {acc: name for acc, name, _, _ in ACCOUNTS}
GROUP = {acc: group for acc, _, group, _ in ACCOUNTS}
SUBGROUP = {acc: subgroup for acc, _, _, subgroup in ACCOUNTS}
SIGN = {acc: GROUP_SIGN[group] for acc, group in GROUP.items()}
# line_key, line, line_type, group, bound, sign, sort_order (spec 4.3)
LAYOUT = (
    ("REV", "Revenue", "Group", REV, "", 1, 10),
    ("COS", "Cost of services", "Group", COS, "", -1, 20),
    ("GP", "Gross profit", "Subtotal", "", 30, 1, 30),
    ("GPM", "Gross margin %", "Ratio", "", 30, 1, 35),
    ("OPEX", "Operating expenses", "Group", OPEX, "", -1, 40),
    ("EBITDA", "EBITDA", "Subtotal", "", 50, 1, 50),
    ("EBITDAM", "EBITDA margin %", "Ratio", "", 50, 1, 55),
    ("DA", "Depreciation and amortisation", "Group", DA, "", -1, 60),
    ("EBIT", "EBIT", "Subtotal", "", 70, 1, 70),
    ("EBITM", "EBIT margin %", "Ratio", "", 70, 1, 75),
)
COST_CENTRES = (
    ("CC10", "Cleaning Services", "Operating"),
    ("CC20", "Technical Maintenance", "Operating"),
    ("CC30", "Security Services", "Operating"),
    ("CC40", "Catering", "Operating"),
    ("CC80", "Administration", "Support"),
    ("CC90", "Sales & Marketing", "Support"),
)
OPERATING = ("CC10", "CC20", "CC30", "CC40")
ALL_CC = tuple(cc for cc, _, _ in COST_CENTRES)
_POSTING_RULES = (
    (("4000", "4100"), ("CC10",)),
    (("4010", "4110"), ("CC20",)),
    (("4020", "4120"), ("CC30",)),
    (("4030", "4130"), ("CC40",)),
    (("4200",), ("CC10", "CC20")),
    (("4900", "5000", "5010", "5020", "5030", "5130"), OPERATING),
    (("5100",), ("CC10",)),
    (("5110",), ("CC20",)),
    (("5120",), ("CC40",)),
    (("5200", "5300"), ("CC10", "CC20", "CC30")),
    (("5310",), ("CC10", "CC20", "CC40")),
    (("6000", "6010", "6020", "6430", "6490"), ALL_CC),
    (("6100", "6110"), ("CC40", "CC80")),
    (("6200", "6400", "6410", "6450", "7030"), ("CC80",)),
    (("6300", "6310", "6320"), ("CC90",)),
    (("6420", "7020"), ("CC80", "CC90")),
    (("7000",), ("CC10", "CC20", "CC30")),
    (("7010",), ("CC10", "CC20", "CC40")),
)
# the 98 cost-centre and account pairs, sorted by cost centre and account (the row order of every budget sheet)
POSTING = tuple(sorted((cc, acc) for accounts, ccs in _POSTING_RULES for acc in accounts for cc in ccs))

# ---------------------------------------------------------------- plan model (spec 4.6)

SPRING_AUTUMN = (0.70, 0.80, 1.35, 1.40, 1.10, 0.90, 0.70, 0.60, 1.05, 1.25, 1.15, 1.00)
HEATING_COOLING = (1.30, 1.20, 0.95, 0.80, 0.80, 1.00, 1.20, 1.10, 0.80, 0.85, 0.95, 1.05)
EVENTS = (0.50, 0.60, 0.80, 0.90, 1.30, 1.50, 1.40, 1.30, 1.20, 0.80, 0.70, 1.00)
CANTEEN = (0.95, 1.05, 1.10, 1.05, 1.05, 1.05, 0.80, 0.70, 1.05, 1.10, 1.10, 1.00)
TEMP = (0.8, 0.8, 0.9, 0.9, 1.0, 1.1, 1.4, 1.5, 1.0, 0.9, 0.8, 0.9)
ENERGY = (1.35, 1.25, 1.10, 0.90, 0.80, 0.75, 0.75, 0.75, 0.85, 1.00, 1.15, 1.35)
FLAT = (1.0,) * 12
FAIRS = (0, 0, 0.40 * 12, 0, 0, 0, 0, 0, 0.30 * 12, 0.30 * 12, 0, 0)  # 6310: March 40 %, September and October 30 %
DECEMBER = (0,) * 11 + (12.0,)  # 6450: the whole year in December

REVENUE_2023 = {"CC10": 19_000_000, "CC20": 9_400_000, "CC30": 7_600_000, "CC40": 6_200_000}
CONTRACT = {"CC10": "4000", "CC20": "4010", "CC30": "4020", "CC40": "4030"}
AD_HOC = {"CC10": "4100", "CC20": "4110", "CC30": "4120", "CC40": "4130"}
MIX = {  # contract, ad-hoc, recharges (4200), reductions (4900) as shares of the department's revenue
    "CC10": (0.905, 0.075, 0.025, -0.005),
    "CC20": (0.72, 0.24, 0.05, -0.01),
    "CC30": (0.86, 0.15, 0.0, -0.01),
    "CC40": (0.80, 0.21, 0.0, -0.01),
}
SEASON = {"4030": CANTEEN, "4100": SPRING_AUTUMN, "4110": HEATING_COOLING, "4120": EVENTS, "4130": EVENTS}
CONTRACT_PRICE = (1.0, 1.05, 1.05 * 1.035)  # price steps each January
AD_HOC_GROWTH = 1.03
DIRECT = {  # direct personnel, materials, subcontractors, vehicles and equipment as shares of department revenue
    "CC10": (0.67, 0.045, 0.03, 0.025),
    "CC20": (0.48, 0.14, 0.09, 0.04),
    "CC30": (0.72, 0.015, 0.04, 0.025),
    "CC40": (0.42, 0.32, 0.0, 0.025),
}
PERSONNEL_SPLIT = {"5000": 0.72, "5010": 0.06, "5020": 0.19, "5030": 0.03}
PERSONNEL_FIXED = 0.75  # the rest follows the department's planned revenue index
MATERIALS = {
    "CC10": {"5100": 0.78, "5130": 0.22},
    "CC20": {"5110": 0.90, "5130": 0.10},
    "CC30": {"5130": 1.0},
    "CC40": {"5120": 0.94, "5130": 0.06},
}
SUBCONTRACTORS = {cc: {"5200": 1.0} for cc in ("CC10", "CC20", "CC30", "CC40")}
VEHICLES = {
    "CC10": {"5300": 0.6, "5310": 0.4},
    "CC20": {"5300": 0.7, "5310": 0.3},
    "CC30": {"5300": 1.0},
    "CC40": {"5310": 1.0},
}
DIRECT_SEASON = {"5030": TEMP, "5110": HEATING_COOLING, "5120": CANTEEN, "5300": ENERGY}
EVENT_OVERTIME = ("CC30", "CC40")  # 5010 follows EVENTS there
OVERHEAD_PERSONNEL = {"CC10": 350_000, "CC20": 350_000, "CC30": 350_000, "CC40": 350_000}
OVERHEAD_PERSONNEL |= {"CC80": 2_000_000, "CC90": 800_000}
OVERHEAD_SPLIT = {"6000": 0.78, "6010": 0.19, "6020": 0.03}
SALARIES = ("6000", "6010")  # follow the wage round; every other overhead grows 3 % a year
OVERHEAD_GROWTH = 1.03
TRAVEL = {"CC10": 0.30, "CC20": 0.25, "CC30": 0.15, "CC40": 0.10, "CC80": 0.10, "CC90": 0.10}
OVERHEADS = {  # (cost centre, account) -> EUR a year in 2023 and the monthly profile
    ("CC80", "6100"): (420_000, FLAT),
    ("CC40", "6100"): (120_000, FLAT),
    ("CC80", "6110"): (130_000, ENERGY),
    ("CC40", "6110"): (80_000, ENERGY),
    ("CC80", "6200"): (450_000, FLAT),
    ("CC90", "6300"): (200_000, FLAT),
    ("CC90", "6310"): (80_000, FAIRS),
    ("CC80", "6400"): (300_000, FLAT),
    ("CC80", "6410"): (200_000, FLAT),
    ("CC80", "6420"): (60_000, FLAT),
    ("CC90", "6420"): (20_000, FLAT),
    ("CC80", "6450"): (25_000, DECEMBER),
}
OVERHEADS |= {(cc, "6430"): (120_000 * share, FLAT) for cc, share in TRAVEL.items()}
OVERHEADS |= {(cc, "6490"): (100_000 / 6, FLAT) for cc in ALL_CC}
COMMISSION = 0.003  # 6320 (CC90): 0.3 % of the company's planned revenue of the month
DEPRECIATION = {  # EUR a year in 2023 and the split by cost centre; grows 3 % a year like the overheads
    "7000": (450_000, {"CC10": 0.4, "CC20": 0.4, "CC30": 0.2}),
    "7010": (350_000, {"CC10": 0.5, "CC20": 0.3, "CC40": 0.2}),
    "7020": (120_000, {"CC80": 0.7, "CC90": 0.3}),
    "7030": (80_000, {"CC80": 1.0}),
}
PLAN_WAGES = (1.0, 1.06, 1.06 * 1.04)  # wage level per year: the planned rounds of January 2024 and 2025
ACTUAL_WAGES = (1.0, 1.07, 1.07 * 1.04)  # E1: the 2024 round was 7 %; the 2025 budget starts from that level
IT_UPLIFT = 1.15  # E2: 6200 runs 15 % higher from October 2024; the 2025 budget carries the new run rate
SIGMA = {  # noise of the actuals by subgroup: epsilon ~ Normal(0, sigma); the other overheads 3 %
    "Contract revenue": 0.01,
    "Project and ad-hoc revenue": 0.06,
    "Other revenue": 0.06,
    "Direct personnel": 0.015,
    "Materials and consumables": 0.05,
    "Subcontractors": 0.08,
    "Vehicles and equipment": 0.04,
    "Depreciation and amortisation": 0.0,
}
OVERHEAD_SIGMA = 0.03


def sigma(account: str) -> float:
    return SIGMA.get(SUBGROUP[account], OVERHEAD_SIGMA)


@dataclass(frozen=True)
class Params:
    wages: tuple[float, float, float]
    it_from: int | None  # month index from which 6200 runs at IT_UPLIFT
    events: bool  # E2 to E7 (E1 is the wage level): actuals only


PLAN = Params(PLAN_WAGES, None, False)
BUDGET_2025 = Params(ACTUAL_WAGES, 24, False)
ACTUAL = Params(ACTUAL_WAGES, 21, True)


def _profile(annual: list[float], season: tuple[float, ...]) -> np.ndarray:
    """36 monthly values from three yearly amounts and a monthly index with mean 1."""
    return np.array([annual[t // 12] * season[t % 12] / 12 for t in range(MONTHS)])


def revenue_lines(p: Params) -> dict[tuple[str, str], np.ndarray]:
    """Revenue accounts in natural sign (EUR, 36 months), events included when p.events."""
    out: dict[tuple[str, str], np.ndarray] = {}
    for cc, total in REVENUE_2023.items():
        contract, ad_hoc, recharge, reduction = MIX[cc]
        c_acc, a_acc = CONTRACT[cc], AD_HOC[cc]
        lines = {
            c_acc: _profile([total * contract * CONTRACT_PRICE[y] for y in range(3)], SEASON.get(c_acc, FLAT)),
            a_acc: _profile([total * ad_hoc * AD_HOC_GROWTH**y for y in range(3)], SEASON[a_acc]),
        }
        if recharge:  # 4200 follows the department's ad-hoc account
            lines["4200"] = _profile([total * recharge * AD_HOC_GROWTH**y for y in range(3)], SEASON[a_acc])
        if p.events and cc == "CC10":
            lines[c_acc][27:] *= 0.94  # E5: a lost contract from April 2025
        if p.events and cc == "CC30":
            lines[a_acc][29:32] *= 1.45  # E6: summer event contracts, June to August 2025
        gross = sum(lines.values())
        lines["4900"] = gross * reduction / (contract + ad_hoc + recharge)  # a fixed share of the month's revenue
        out |= {(cc, acc): values for acc, values in lines.items()}
    return out


def department_revenue(lines: dict[tuple[str, str], np.ndarray]) -> dict[str, np.ndarray]:
    return {cc: sum(v for (c, _), v in lines.items() if c == cc) for cc in OPERATING}


def model(p: Params) -> dict[tuple[str, str], np.ndarray]:
    """Every posting pair in natural sign (revenue and costs positive, revenue reductions negative), EUR, 36 months."""
    out = revenue_lines(p)
    planned = department_revenue(revenue_lines(PLAN))  # the planned revenue index drives the variable costs
    for cc in OPERATING:
        rev = planned[cc]
        annual_rev = [rev[12 * y : 12 * y + 12].sum() for y in range(3)]
        personnel, materials, subcontractors, vehicles = DIRECT[cc]
        for acc, split in PERSONNEL_SPLIT.items():
            fixed = [PERSONNEL_FIXED * personnel * split * REVENUE_2023[cc] * p.wages[y] for y in range(3)]
            variable = (1 - PERSONNEL_FIXED) * personnel * split
            season = EVENTS if (acc == "5010" and cc in EVENT_OVERTIME) else DIRECT_SEASON.get(acc)
            if season:
                out[(cc, acc)] = _profile([fixed[y] + variable * annual_rev[y] for y in range(3)], season)
            else:
                out[(cc, acc)] = _profile(fixed, FLAT) + variable * rev
        for share, split in ((materials, MATERIALS), (subcontractors, SUBCONTRACTORS), (vehicles, VEHICLES)):
            for acc, part in split[cc].items():
                if not share:
                    continue
                season = DIRECT_SEASON.get(acc)
                if season:
                    out[(cc, acc)] = _profile([share * part * annual_rev[y] for y in range(3)], season)
                else:
                    out[(cc, acc)] = share * part * rev
    growth = tuple(OVERHEAD_GROWTH**y for y in range(3))
    for cc, total in OVERHEAD_PERSONNEL.items():
        for acc, split in OVERHEAD_SPLIT.items():
            level = p.wages if acc in SALARIES else growth
            out[(cc, acc)] = _profile([total * split * level[y] for y in range(3)], FLAT)
    for pair, (annual, season) in OVERHEADS.items():
        out[pair] = _profile([annual * growth[y] for y in range(3)], season)
    out[("CC90", "6320")] = COMMISSION * sum(planned.values())
    for acc, (annual, split) in DEPRECIATION.items():
        for cc, share in split.items():
            out[(cc, acc)] = _profile([annual * share * growth[y] for y in range(3)], FLAT)
    if p.it_from is not None:
        out[("CC80", "6200")][p.it_from :] *= IT_UPLIFT
    if p.events:
        out[("CC80", "6410")][[21, 22]] += 60_000  # E2: ERP migration, October and November 2024
        out[("CC80", "6450")][23] = 85_000  # E3: a large customer default, December 2024
        out[("CC40", "5120")][25:] *= 1.06  # E4: food prices from February 2025
        for acc in ("5000", "5010", "5020"):
            out[("CC10", acc)][29:] *= 0.95  # E5: fewer cleaning staff from June 2025
        out[("CC30", "5010")][29:32] *= 1.30  # E6: overtime and temporary staff for the summer events
        out[("CC30", "5030")][29:32] *= 1.25
        out[("CC20", "7000")][27:] *= 1.06  # E7: extra vans from April 2025
    if set(out) != set(POSTING):
        raise AssertionError(f"model pairs differ from POSTING: {sorted(set(out) ^ set(POSTING))}")
    return {pair: out[pair] for pair in POSTING}


def round_hundreds(value: float) -> int:
    """EUR to whole hundreds, half away from zero."""
    return int(math.copysign(math.floor(abs(value) / 100 + 0.5) * 100, value))


def to_cents(value: float) -> int:
    """EUR to integer cents, half away from zero."""
    return int(math.copysign(math.floor(abs(value) * 100 + 0.5), value))


def actuals(rng: np.random.Generator) -> dict[tuple[str, str], list[int]]:
    """Natural-sign actuals in cents for the 33 closed months: the actual model times (1 + epsilon)."""
    base = model(ACTUAL)
    out = {}
    for pair in POSTING:
        values = base[pair] * (1 + rng.normal(0.0, 1.0, MONTHS) * sigma(pair[1]))
        if pair == ("CC80", "6450"):
            values[23] = 85_000  # E3 is a booked amount, not an estimate
        out[pair] = [to_cents(v) for v in values[:ACTUAL_MONTHS]]
    return out


def budget() -> dict[tuple[str, str], list[int]]:
    """Natural-sign budget in EUR (whole hundreds), 36 months: the plan; the 2025 budget was made after 2024."""
    plan, plan_2025 = model(PLAN), model(BUDGET_2025)
    return {pair: [round_hundreds((plan if t < 24 else plan_2025)[pair][t]) for t in range(MONTHS)] for pair in POSTING}


FORECAST_FULL = {("CC10", "4000"): 0.94, ("CC10", "5000"): 0.95, ("CC10", "5010"): 0.95, ("CC10", "5020"): 0.95}
FORECAST_PLAIN = {("CC30", "4120"), ("CC30", "5010"), ("CC30", "5030")}


def forecast(
    actual: dict[tuple[str, str], list[int]], plan: dict[tuple[str, str], list[int]]
) -> dict[tuple[str, str], list[int]]:
    """Natural-sign forecast in EUR (whole hundreds) for October to December 2025, made after the September close:
    half of the year-to-date deviation is carried forward, E5 in full, the ended summer contracts not at all."""
    out = {}
    for pair in POSTING:
        a_ytd = sum(actual[pair][24:33]) / 100
        b_ytd = sum(plan[pair][24:33])
        if pair in FORECAST_FULL:
            factor = FORECAST_FULL[pair]
        elif pair in FORECAST_PLAIN or b_ytd == 0:
            factor = 1.0
        else:
            factor = 1 + 0.5 * (a_ytd / b_ytd - 1)
        out[pair] = [round_hundreds(plan[pair][t] * factor) for t in range(ACTUAL_MONTHS, MONTHS)]
    return out


# ---------------------------------------------------------------- people (Faker, NAME_SEED)

FOLD = (("Ä", "Ae"), ("Ö", "Oe"), ("Ü", "Ue"), ("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss"))


def ascii_fold(text: str) -> str:
    for source, target in FOLD:
        text = text.replace(source, target)
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


def email_for(first: str, last: str) -> str:
    parts = [re.sub(r"[^a-z0-9]+", "", ascii_fold(part).lower()) for part in (first, last)]
    return f"{parts[0]}.{parts[1]}@{DOMAIN}"


def people() -> list[tuple[str, str]]:
    """Seven people (name, e-mail): the heads of the six cost centres in order, then the Head of Operations."""
    fake = Faker("de_AT")
    fake.seed_instance(NAME_SEED)
    out: list[tuple[str, str]] = []
    while len(out) < len(COST_CENTRES) + 1:
        first, last = fake.first_name(), fake.last_name()
        email = email_for(first, last)
        if email not in {e for _, e in out}:
            out.append((f"{first} {last}", email))
    return out


# ---------------------------------------------------------------- writers


def period(t: int) -> str:
    return f"{YEARS[t // 12]}-{t % 12 + 1:02d}"


def ledger_text(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    return f"{sign}{abs(cents) // 100}.{abs(cents) % 100:02d}"


def write_csv(path: Path, columns: tuple[str, ...], rows: list[tuple[object, ...]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(columns)
        writer.writerows(rows)


def gl_rows(actual: dict[tuple[str, str], list[int]]) -> list[tuple[object, ...]]:
    """Ledger sign (debit +, credit -): ledger = -sign x natural; zero balances are not exported."""
    rows = []
    for t in range(ACTUAL_MONTHS):
        for cc, acc in POSTING:
            natural = actual[(cc, acc)][t]
            if natural:
                rows.append((period(t), cc, acc, ledger_text(-SIGN[acc] * natural)))
    return rows


MODIFIED = re.compile(rb"(<dcterms:modified[^>]*>)[^<]*(</dcterms:modified>)")
EXPORT_STAMP = EXPORT_TIME.strftime("%Y-%m-%dT%H:%M:%SZ").encode("ascii")


def _sheet(wb: Workbook, title: str, months: tuple[str, ...], total: str, rows: list[list[object]]) -> None:
    """A1 title, A2 note, row 3 empty, row 4 header, the pairs from row 5, then the Total row (spec 4.4)."""
    ws = wb.create_sheet(title)
    ws.append([f"{COMPANY} · {title}"])
    ws.append(["EUR · revenue and costs as positive amounts · revenue reductions negative"])
    ws.append([])
    ws.append(["Cost centre", "Account", "Account name", *months, total])
    ws["A1"].font = Font(bold=True, size=14)
    first, last = 5, 4 + len(rows)
    letters = [ws.cell(row=4, column=4 + i).column_letter for i in range(len(months) + 1)]
    for r, row in enumerate(rows, start=first):
        ws.append([*row, f"=SUM({letters[0]}{r}:{letters[-2]}{r})"])
    ws.append(["Total", None, None, *(f"=SUM({c}{first}:{c}{last})" for c in letters)])
    for cell in (*ws[4], *ws[last + 1]):
        cell.font = Font(bold=True)
    for row in ws.iter_rows(min_row=first, max_row=last + 1, min_col=4):
        for cell in row:
            cell.number_format = "#,##0"
    ws.column_dimensions["C"].width = 44


def write_budget(path: Path, plan: dict[tuple[str, str], list[int]], fc: dict[tuple[str, str], list[int]]) -> None:
    wb = Workbook()
    wb.remove(wb.active)
    wb.properties.creator = "Kaldora Controlling"
    wb.properties.lastModifiedBy = "Kaldora Controlling"
    wb.properties.created = EXPORT_TIME
    wb.properties.modified = EXPORT_TIME
    for y, year in enumerate(YEARS):  # zero months are empty cells
        rows = [
            [cc, acc, NAME[acc], *(v or None for v in plan[(cc, acc)][12 * y : 12 * y + 12])] for cc, acc in POSTING
        ]
        _sheet(wb, f"Budget {year}", MONTH_NAMES, "FY", rows)
    rows = [[cc, acc, NAME[acc], *(v or None for v in fc[(cc, acc)])] for cc, acc in POSTING]
    _sheet(wb, f"Forecast {YEARS[-1]}", MONTH_NAMES[9:], "Q4", rows)
    buffer = io.BytesIO()
    wb.save(buffer)
    # The same bytes on every run and platform: entries stored without compression (no zlib differences), a fixed
    # entry time, and the modified time pinned, which openpyxl sets to the current time while saving.
    stamp = EXPORT_TIME.timetuple()[:6]
    with (
        zipfile.ZipFile(io.BytesIO(buffer.getvalue())) as source,
        zipfile.ZipFile(path, "w", zipfile.ZIP_STORED) as target,
    ):
        for item in source.infolist():
            entry = zipfile.ZipInfo(item.filename, date_time=stamp)
            entry.compress_type = zipfile.ZIP_STORED
            entry.external_attr = 0o600 << 16
            data = source.read(item.filename)
            if item.filename == "docProps/core.xml":
                data = MODIFIED.sub(rb"\g<1>" + EXPORT_STAMP + rb"\g<2>", data)
            target.writestr(entry, data)


def generate(out: Path) -> None:
    rng = np.random.default_rng(SEED)
    actual = actuals(rng)
    plan = budget()
    fc = forecast(actual, plan)
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "gl_actuals.csv", ("period", "cost_centre", "account", "amount"), gl_rows(actual))
    write_budget(out / "budget.xlsx", plan, fc)
    write_csv(
        out / "chart_of_accounts.csv",
        ("account", "name", "group", "subgroup", "sign", "sort_order"),
        [(acc, name, group, sub, GROUP_SIGN[group], i) for i, (acc, name, group, sub) in enumerate(ACCOUNTS, 1)],
    )
    heads = people()
    write_csv(
        out / "cost_centres.csv",
        ("cost_centre", "name", "type", "head_name", "head_email", "sort_order"),
        [(cc, name, kind, *heads[i], i + 1) for i, (cc, name, kind) in enumerate(COST_CENTRES)],
    )
    write_csv(out / "pnl_layout.csv", ("line_key", "line", "line_type", "group", "bound", "sign", "sort_order"), LAYOUT)
    security = [(heads[i][1], cc) for i, (cc, _, _) in enumerate(COST_CENTRES)]
    security += [(heads[-1][1], cc) for cc in OPERATING]  # the Head of Operations
    write_csv(out / "security.csv", ("user_email", "cost_centre"), security)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compare(expected: Path, actual: Path) -> list[str]:
    problems = []
    for name in FILES:
        if not (actual / name).exists():
            problems.append(f"{name}: missing")
        elif digest(actual / name) != digest(expected / name):
            problems.append(f"{name}: SHA-256 differs from a fresh build")
    return problems


def shown_path(path: Path) -> str:
    """The path as printed: relative to the repository root when it lies inside it."""
    resolved = path.resolve()
    return resolved.relative_to(ROOT).as_posix() if resolved.is_relative_to(ROOT) else resolved.as_posix()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate the Kaldora Facility Services data files (seed 43).")
    parser.add_argument("--out", type=Path, default=ROOT / "data")
    parser.add_argument("--check", action="store_true", help="compare a fresh build with the files in --out")
    args = parser.parse_args(argv)
    shown = shown_path(args.out)
    if not args.check:
        generate(args.out)
        print(f"wrote {len(FILES)} files to {shown}")
        return 0
    with tempfile.TemporaryDirectory() as tmp:
        generate(Path(tmp))
        problems = compare(Path(tmp), args.out)
    for problem in problems:
        print(f"FAIL {problem}")
    if problems:
        return 1
    print(f"{shown} matches a fresh build ({len(FILES)} files, SHA-256)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
