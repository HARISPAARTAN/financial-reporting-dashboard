"""The pandas reference on the mini fixture, every value computed by hand (amounts in cents).

Fixture (natural sign, EUR): revenue 4000 (CC10) actual 1,100 and 900, budget 1,000 a month, forecast 950 for March;
direct wages 5000 (CC10) actual 700 and 695, budget 700, forecast 690; salaries 6000 actual CC10 200 and 200, CC80
none in January and 40 in February; budget CC10 200 a month, CC80 300 in January and March and none in February;
forecast CC10 200, CC80 300. Actuals run to February 2025, so March is the open month.
"""

import pytest

from reference import Ctx, period

Q1 = period(2025, 1, 3)
JAN, FEB, MAR = period(2025, 1, 1), period(2025, 2, 2), period(2025, 3, 3)
CC80 = frozenset({"CC80"})


def test_both_sign_conversions(mini):
    facts = mini.facts.set_index(["scenario", "t", "cost_centre", "account"])["cents"]
    assert facts[("Actual", 24, "CC10", "4000")] == 110_000  # ledger -1,100.00 (credit) -> income +
    assert facts[("Actual", 24, "CC10", "5000")] == -70_000  # ledger 700.00 (debit) -> expense -
    assert facts[("Budget", 24, "CC10", "4000")] == 100_000  # natural 1,000 x sign +1
    assert facts[("Budget", 24, "CC10", "5000")] == -70_000  # natural 700 x sign -1
    assert len(mini.facts) == 22 and mini.last_actual == 25


def test_group_subtotal_and_ratio_lines(mini):
    assert mini.actual(Ctx(Q1, line="REV")) == 200_000
    assert mini.actual(Ctx(Q1, line="COS")) == 139_500  # costs shown positive
    assert mini.actual(Ctx(Q1, line="GP")) == 60_500
    assert mini.actual(Ctx(Q1, line="GPM")) == pytest.approx(0.3025)
    assert mini.actual(Ctx(Q1, line="OPEX")) == 44_000
    assert mini.actual(Ctx(Q1, line="EBITDA")) == 16_500
    assert mini.actual(Ctx(Q1, line="EBITDAM")) == pytest.approx(0.0825)
    assert mini.actual(Ctx(Q1, line="DA")) is None  # no account posts there
    assert mini.actual(Ctx(Q1, line="EBIT")) == 16_500
    assert mini.actual(Ctx(Q1)) == 16_500  # no line in context: the EBIT contribution


def test_account_and_subgroup_rows(mini):
    assert mini.actual(Ctx(Q1, line="COS", subgroup="Direct personnel")) == 139_500
    assert mini.actual(Ctx(Q1, line="COS", subgroup="Direct personnel", account="5000")) == 139_500
    assert mini.actual(Ctx(Q1, line="REV", subgroup="Direct personnel")) is None
    assert mini.actual(Ctx(Q1, line="GP", subgroup="Direct personnel")) is None  # subtotals hide their children
    assert mini.actual(Ctx(Q1, line="GPM", account="5000")) is None
    rows = [(c.line, c.subgroup, c.account) for c in mini.matrix_rows()]
    assert rows[:3] == [("REV", None, None), ("REV", "Contract revenue", None), ("REV", "Contract revenue", "4000")]
    assert rows[3] == ("COS", None, None) and len(rows) == 16


def test_closed_month_budget_and_the_outlook_split(mini):
    assert mini.budget(Ctx(Q1, line="REV")) == 300_000
    assert mini.budget_closed(Ctx(Q1, line="REV")) == 200_000  # March is not closed
    assert mini.outlook(Ctx(Q1, line="REV")) == 295_000  # actual January and February, forecast March
    assert mini.outlook(Ctx(Q1, line="GPM")) == pytest.approx((60_500 + 95_000 - 69_000) / 295_000)
    assert mini.full_year_outlook(Ctx(FEB, line="EBITDA")) == -7_500  # 16,500 actual and -24,000 forecast
    assert mini.budget_full_year(Ctx(FEB, line="EBITDA")) == -30_000
    assert mini.outlook_vs_budget(Ctx(FEB, line="EBITDA")) == 22_500
    assert mini.outlook_vs_budget(Ctx(FEB, line="EBITDAM")) == pytest.approx((-7_500 / 295_000 + 0.1) * 100)


def test_variance_in_display_sign_and_pp_on_ratio_lines(mini):
    assert mini.variance(Ctx(Q1, line="REV")) == 0
    assert mini.variance(Ctx(Q1, line="COS")) == -500
    assert mini.variance(Ctx(Q1, line="OPEX")) == -26_000
    assert mini.variance(Ctx(Q1, line="GPM")) == pytest.approx(0.25)  # pp: 30.25 % against 30.00 %
    assert mini.variance_pct(Ctx(Q1, line="GPM")) is None
    assert mini.variance(Ctx(Q1, line="EBITDAM")) == pytest.approx(13.25)
    assert mini.variance(Ctx(Q1, line="DA")) is None


def test_variance_pct_against_a_negative_budget(mini):
    assert mini.budget_closed(Ctx(Q1, line="EBITDA")) == -10_000
    assert mini.variance(Ctx(Q1, line="EBITDA")) == 26_500
    assert mini.variance_pct(Ctx(Q1, line="EBITDA")) == pytest.approx(2.65)  # divided by the absolute budget
    assert mini.favourable(Ctx(Q1, line="EBITDA")) == 1


def test_favourable_and_the_neutral_band(mini):
    assert mini.favourable(Ctx(Q1, line="REV")) == 0  # exactly on budget
    assert mini.favourable(Ctx(Q1, line="COS")) == 0  # -0.36 %: within 1 %
    assert mini.favourable(Ctx(Q1, line="GP")) == 0  # +0.83 %
    assert mini.favourable(Ctx(Q1, line="GPM")) == 1  # +0.25 pp: outside 0.1 pp
    assert mini.favourable(Ctx(Q1, line="OPEX")) == 1  # a cost below budget
    assert mini.favourable(Ctx(Q1, line="DA")) is None
    assert mini.favourable_label(Ctx(Q1, line="COS")) == "On plan"
    assert mini.favourable_label(Ctx(Q1, line="OPEX")) == "Fav."
    assert mini.favourable_label(Ctx(Q1, line="DA")) is None


def test_zero_budget_and_blank_actual(mini):
    zero_budget = Ctx(FEB, CC80, "OPEX")
    assert mini.budget_closed(zero_budget) is None and mini.actual(zero_budget) == 4_000
    assert mini.variance(zero_budget) == 4_000 and mini.variance_pct(zero_budget) is None
    assert mini.favourable(zero_budget) == -1 and mini.favourable_label(zero_budget) == "Unfav."
    blank_actual = Ctx(JAN, CC80, "OPEX")
    assert mini.actual(blank_actual) is None and mini.budget_closed(blank_actual) == 30_000
    assert mini.variance(blank_actual) == -30_000 and mini.variance_pct(blank_actual) == pytest.approx(-1.0)
    assert mini.favourable(blank_actual) == 1


def test_profit_impact_adds_up_to_the_ebit_variance(mini):
    impacts = {k: mini.profit_impact(Ctx(Q1, line=k)) for k in ("REV", "COS", "OPEX", "DA")}
    assert impacts == {"REV": 0, "COS": 500, "OPEX": 26_000, "DA": None}
    assert sum(v for v in impacts.values() if v is not None) == mini.variance(Ctx(Q1, line="EBIT"))
    assert mini.profit_impact(Ctx(Q1, line="GPM")) is None


def test_year_to_date_and_full_year(mini):
    assert mini.actual_ytd(Ctx(FEB, line="REV")) == 200_000
    assert mini.actual_ytd(Ctx(MAR, line="REV")) is None  # March starts after the last actual date
    assert mini.budget_ytd(Ctx(MAR, line="REV")) == 300_000
    assert mini.outlook_ytd(Ctx(MAR, line="REV")) == 295_000
    assert mini.full_year_outlook(Ctx(JAN, line="REV")) == 295_000
    assert mini.budget_full_year(Ctx(JAN, line="REV")) == 300_000


@pytest.mark.parametrize(
    ("scenario", "expected"),
    [
        ("Actual", [110_000, 90_000, None, None, 200_000, 295_000]),
        ("Budget", [100_000, 100_000, 100_000, None, 300_000, 300_000]),
        ("Forecast", [110_000, 90_000, 95_000, None, 295_000, 295_000]),
    ],
)
def test_every_pnl_matrix_column(mini, scenario, expected):
    ctx = Ctx(Q1, line="REV")
    assert [mini.pnl_matrix(ctx, col, scenario) for col in (1, 2, 3, 4, 13, 14)] == expected
    assert all(mini.pnl_matrix(ctx, col, scenario) is None for col in range(4, 13))


def test_matrix_ytd_runs_from_january_to_the_end_of_the_month_range(mini):
    ctx = Ctx(FEB, line="REV")
    assert mini.pnl_matrix(ctx, 1, "Actual") is None  # January is outside the range
    assert mini.pnl_matrix(ctx, 13, "Actual") == 200_000  # but inside the YTD


def test_lines_ratios_and_rows(mini):
    ctx = Ctx(Q1)
    assert mini.revenue(ctx) == 200_000
    assert mini.gross_margin_pct(ctx) == pytest.approx(0.3025)
    assert mini.opex_pct(ctx) == pytest.approx(0.22)
    assert mini.personnel_cost(ctx) == 183_500
    assert mini.personnel_pct(ctx) == pytest.approx(0.9175)
    assert mini.rows({("Actual", t) for t in Q1}) == 7
    assert mini.revenue(Ctx(Q1, CC80)) is None and mini.opex_pct(Ctx(Q1, CC80)) is None
