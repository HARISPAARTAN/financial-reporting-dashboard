# Reconciliation

Every check is computed twice: in Python by `tools/reference.py` (pandas on the files in `data/`, amounts as integer
cents) and in Power BI Desktop by the measure `[Check value]` on the hidden page Reconciliation, which ignores every
slicer (`docs/desktop-validation.md`). `tests/test_measures.py` recomputes the Python column and compares each Desktop
value as soon as it is entered.

Tolerance: amounts ± 0.01 EUR, ratios ± 0.00005, counts exact. The page shows amounts with two decimals, ratios with
four and counts as whole numbers. Difference is Desktop minus Python.

Desktop session: 2026-11-02, Power BI Desktop 2.159.883.0 (Microsoft Store); the Desktop column is read from the Reconciliation page after the refresh, with no role applied.

| Id | Check | Kind | Definition | Python | Desktop | Difference |
|---|---|---|---|---|---|---|
| R1 | Fact rows | count | rows of `FactGL`: the actual balances plus the unpivoted budget and forecast cells | 6936 | 6,936 | 0 |
| R2 | Actual revenue 2023 | amount | `[Actual]` on Revenue, January to December 2023 | 42245201.08 | 42,245,201.08 | 0.00 |
| R3 | Actual EBITDA 2024 | amount | `[Actual]` on EBITDA, January to December 2024 | 2530119.48 | 2,530,119.48 | 0.00 |
| R4 | Actual EBIT Jan to Sep 2025 | amount | `[Actual]` on EBIT, January to September 2025 | 884336.53 | 884,336.53 | 0.00 |
| R5 | Actual gross margin % Jan to Sep 2025 | ratio | `[Actual]` on Gross margin %, January to September 2025 | 0.210652 | 0.2107 | 0.000048 |
| R6 | Budget revenue 2025, full year | amount | `[Budget]` on Revenue, January to December 2025 | 45678300.00 | 45,678,300.00 | 0.00 |
| R7 | Budget EBITDA 2025, closed months | amount | `[Budget (closed months)]` on EBITDA, 2025: the budget of January to September | 1971300.00 | 1,971,300.00 | 0.00 |
| R8 | Forecast revenue Oct to Dec 2025 | amount | `[Forecast]` on Revenue, 2025: the forecast sheet holds October to December | 11158800.00 | 11,158,800.00 | 0.00 |
| R9 | Full-year outlook EBIT 2025 | amount | `[Full-year outlook]` on EBIT, 2025: actuals to September plus the forecast after it | 1116536.53 | 1,116,536.53 | 0.00 |
| R10 | EBITDA variance Jan to Sep 2025, Security Services | amount | `[Variance]` on EBITDA, January to September 2025, cost centre CC30 | 132162.19 | 132,162.19 | 0.00 |
| R11 | Actual operating expenses Jan to Sep 2025 | amount | `[Actual]` on Operating expenses (display sign), January to September 2025 | 5451712.82 | 5,451,712.82 | 0.00 |
| R12 | Personnel cost % of revenue 2024 | ratio | `[Personnel cost % of revenue]`, January to December 2024 | 0.712626 | 0.7126 | -0.000026 |
| R13 | Revenue Jan to Sep 2025, Security Services | amount | `[Actual]` on Revenue, January to September 2025, cost centre CC30: what the head of Security Services sees under the role | 6434851.01 | 6,434,851.01 | 0.00 |

The Python column is the output of `uv run python tools/reference.py`. The Desktop column is read from the
Reconciliation page with no role applied.
