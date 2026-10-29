# ADR 0001: A P&L layout table and one sign convention

Status: accepted (2026-10-29)

## Context

The ledger export uses the ledger sign: debit plus, credit minus, so revenue arrives negative and costs positive. The budget workbook holds every amount in natural sign: revenue and costs positive, revenue reductions negative. A management P&L shows costs as positive amounts, adds subtotals and margins between the groups, and must colour a variance as favourable when it raises profit, whether the line is income or cost. Account ranges in DAX (`Account < 5000`) or a bridge table per subtotal would tie the measures to the account numbers.

## Decision

- Every amount is stored once, as its contribution to profit: income plus, expense minus (`FactGL[Amount]`). Actuals become `−amount`, budget and forecast cells `value × sign` of their account.
- The layout is its own table, `DimPnLLine` (from `data/pnl_layout.csv`), joined to `DimAccount` by `Line key`. A Group line holds its accounts; a Subtotal is the signed sum of all accounts whose group sorts below its bound; a Ratio is that subtotal divided by Revenue.
- A Group line, its subgroups and its accounts show `signed × line sign`, so costs read positive; subtotals and ratios show the signed value.
- `Variance` is Actual − Budget in display sign; it is favourable when `Variance × line sign > 0`. `Profit impact = Variance × line sign` is the effect on EBIT, so the impacts of the four groups add up to the EBIT variance.
- Within 1 % of budget, or 0.1 pp on a margin line, counts as on plan.

## Consequences

- One rule colours every line: more revenue and less cost are both favourable, and a cost line over budget is unfavourable although its variance is positive.
- A new account needs a row in `chart_of_accounts.csv` with its group and sign, and nothing in DAX; a new subtotal is a row in `pnl_layout.csv` with its bound.
- The waterfall of the Variance page shows the profit impacts directly, and they reconcile to the EBIT variance.
- Readers learn one convention: the data model, the Info page and the replica's About section state it in the same words.

## Alternatives considered

- Storing the ledger sign and flipping it in every measure: each measure would repeat the sign logic, and a missed flip shows a wrong colour.
- Account ranges in the measures: they break with the first account outside a range.
- A calculation group for the lines: the line logic would move out of the model's tables, and the replica and the reference would need a second description of it.
