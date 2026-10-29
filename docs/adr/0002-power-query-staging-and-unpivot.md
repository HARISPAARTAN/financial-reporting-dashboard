# ADR 0002: Staging queries per file and the budget unpivot

Status: accepted (2026-10-29)

## Context

The budget workbook is made for people: a title, a note and an empty row above the header, one column per month, a total column and a total row as formulas, one sheet per year and a forecast sheet with three months. The model needs one row per scenario, month, cost centre and account. Power BI's privacy firewall refuses a query that both reads a source and references another query, and the folder of the data files moves with each clone.

## Decision

- Three parameters in `expressions.tmdl`: `DataFolder` (with the trailing backslash), `StartDate` and `EndDate`.
- One staging query per file, also in `expressions.tmdl` and not loaded: `src_GL`, `src_Budget`, `src_Accounts`, `src_CostCentres`, `src_Layout`, `src_Security`. Each touches exactly one file through `DataFolder`.
- `src_Budget` takes every sheet of the workbook, skips the three rows above the header, promotes the header, keeps the rows whose cost centre starts with `CC` (this drops the total row), keeps the cost centre, the account and the month columns (this drops `FY` and `Q4`), and unpivots the months with `Table.UnpivotOtherColumns`. Scenario and year come from the sheet name.
- The `FactGL` partition only references staging queries: the unpivoted budget merged with the accounts for the sign, combined with the actuals. Every column type conversion passes the culture en-US.

## Consequences

- The formulas without cached values in the workbook never reach the model; Power Query reads only the entered cells.
- A new year's budget or a new forecast is a new sheet with the same layout; no query changes.
- `tools/reference.py` repeats the same steps with pandas (`melt` for the unpivot), so a layout change breaks both readers the same way and the reconciliation shows it.
- The staging queries show in Desktop's query list as not loaded.

## Alternatives considered

- Reading the workbook in the `FactGL` partition directly: the partition would read a source and reference `src_GL`, which the privacy firewall refuses.
- A tidy budget export with one row per month: the workbook is the client's planning tool and stays as it is.
- Preparing the files in Python: the client would need Python for each refresh.
