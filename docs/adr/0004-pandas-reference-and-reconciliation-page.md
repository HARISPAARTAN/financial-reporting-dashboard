# ADR 0004: A pandas reference and a hidden reconciliation page

Status: accepted (2026-10-29)

## Context

The headline numbers of the report must be checked against a computation that shares no code with Power BI, and the same numbers feed the reconciliation table, the measure test and the replica's data file. Reading values out of a running Desktop through ADOMD or TOM needs NuGet downloads, which this repository does not make; the reference must read the workbook without a download on the owner's machine or in CI.

## Decision

- `tools/reference.py` uses pandas: it reads the CSV files directly and the workbook through openpyxl, unpivots the budget with `melt`, converts every amount to integer cents and implements the line value, the scenarios, the outlook, the closed-month budget, the variance and the favourable flag as plain functions over a filter context. It is tested on its own against a small fixture whose values are worked out by hand (`tests/test_reference.py`).
- The model holds the table `ReconCheck` (the thirteen checks R1 to R13) and the hidden measure `Check value`, one branch per check, each a `CALCULATE` with `REMOVEFILTERS()` and the check's filters. The hidden page Reconciliation shows them in one table.
- In the Desktop session the values are read from one capture of that page into the Desktop column of `docs/reconciliation.md`; `tests/test_measures.py` compares both columns within tolerances (amounts ± 0.01 EUR, ratios ± 0.00005, counts exact).

## Consequences

- Totals are exact: sums of integer cents never round.
- The DAX and the Python code are written separately, so a shared misunderstanding of a rule would pass both; the hand-worked fixture and the written rules guard against that.
- The reconciliation needs Desktop once per change of the model, and the values are read from a capture; the test reports a misread value as a mismatch.
- Under View as the checks show the role's departments, because `REMOVEFILTERS` does not clear a role filter; R13 is the revenue the head of Security Services sees.

## Alternatives considered

- duckdb: reads xlsx only through an extension fetched on first use, a download on the owner's machine and in CI.
- ADOMD or TOM against Desktop: NuGet downloads.
- A saved DAX query: needs the DAX query view and a second capture; the page shows the same values in the report itself.
- Floating-point euros: totals would differ from Power BI's fixed decimal in the last cent.
