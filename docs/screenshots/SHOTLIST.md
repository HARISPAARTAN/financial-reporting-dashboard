# Screenshots

The images the READMEs show. Images 01 to 10 come from the Power BI Desktop session ([Desktop validation](../desktop-validation.md), steps 4 to 8): the report canvas only, without the title bar, the panes or a signed-in account, in the default state of each page (Year 2025, months 1 to 12, all departments, Scenario Actual) unless the row says otherwise. Images 11 and 12 come from `tools/checks/shots.mjs` (dark theme). PNG files, each at most 1 MB.

| File | Shows |
|---|---|
| `01-pnl-statement.png` | P&L statement: five KPI tiles against budget, the matrix with Revenue and Operating expenses expanded |
| `02-variance-analysis.png` | Variance analysis: the EBIT tiles, EBITDA variance by department, the waterfall from budget EBIT to actual EBIT, the variance matrix |
| `03-trend.png` | Trend: the monthly line of EBITDA with the tooltip page open over a month, the cumulative lines and the full year |
| `04-opex.png` | Opex: the tiles, the treemap by subgroup and account, opex by department, the largest variances |
| `05-department-detail.png` | Department detail after the drill-through from the Security Services bar |
| `06-info.png` | Info: what the report shows, the sign convention and definitions, the data files, the security note and the sources |
| `07-line-tooltip.png` | the tooltip page Line tooltip on its own (320 × 200): Actual, Budget (closed months), Variance, Variance %, Outlook |
| `08-model.png` | the model view with the five relationships |
| `09-rls-head-of-operations.png` | P&L statement under View as for the Head of Operations: the four operating departments |
| `10-reconciliation.png` | the hidden page Reconciliation with R1 to R13 |
| `11-replica-1440.png` | the HTML replica, P&L statement tab, at 1440 × 900 |
| `12-replica-390.png` | the HTML replica, P&L statement tab, at 390 × 844 |

Captured in the session but not committed: each page after Reset, a waterfall column filtering the matrix, and the P&L statement under View as for the head of Security Services.
