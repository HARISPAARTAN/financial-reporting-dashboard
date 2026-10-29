# ADR 0003: The outlook and the closed-month budget

Status: accepted (2026-10-29)

## Context

In October the ledger holds actuals through September; the budget covers the whole year, and the forecast sheet adds October to December. Comparing nine months of actuals with twelve months of budget makes every line look far behind; adding forecast and actual months by hand in each measure duplicates the line logic, and the margin lines need the outlook revenue as their denominator, not the sum of two ratios.

## Decision

- `Last actual date` is the month end of the latest actual date, whatever the slicers.
- `Budget (closed months)` is the budget up to that date and is the basis of every comparison with actuals (`Variance`, `Variance %`, `Favourable`, `Profit impact`). The plain `Budget` stays complete for the trend and the full year.
- `Outlook` is the line value over one table of scenario and date pairs: Actual up to the last closed month, Forecast after it. `Full-year outlook` is the outlook of the whole year in context.
- The forecast scenario holds only the open months; choosing Forecast in the Scenario slicer shows the outlook.
- The P&L matrix takes its columns from the disconnected table `PnLColumn`: twelve months, YTD (January to the end of the month range) and Full year (the budget under the scenario Budget, the outlook otherwise).

## Consequences

- Variances are like for like, and the KPI tiles, the waterfall and the matrices agree on them.
- The ratio lines of the outlook are right without a second copy of the line logic, because the pair filter applies to the subtotal and to the revenue alike.
- A new month of actuals moves the comparison by itself; nothing in the report needs editing.
- A month range that ends before the last closed month compares only the months in range on both sides.

## Alternatives considered

- Comparing with the full-year budget: misleading before December.
- A forecast that repeats the actual months: the export and the workbook would hold the same months twice.
- Two measures for the outlook (an actual part plus a forecast part): wrong on the margin lines.
