# Client brief

## The job post

> We are a facility-services company in Graz with four service lines (cleaning, technical maintenance, security, catering) and two support departments. Each month our controller exports the ledger balances by cost centre and account to CSV. The budget lives in an Excel workbook with one sheet per year, and after the September close we add a sheet with the Q4 forecast. We need a Power BI dashboard for management: income, expenses and margins as a proper P&L, actual versus budget by department and month, the year-end outlook, and a view of operating expenses. Department heads should see only their own department.

Rebuilt from memory as a demo. The original client's name and data are not used.

Kaldora Facility Services is a fictional company. Every account balance, budget value, person and number in this repository comes from the seeded generator `tools/make_data.py`; e-mail addresses use the reserved domain `kaldora.example`.

## Users and roles

| User | Sees | Access |
|---|---|---|
| Managing director, finance controller | all six departments | the full model (workspace members, outside the role) |
| Department heads, one per cost centre | their own cost centre | role `Department head` through the `Security` table |
| Head of Operations | the four operating cost centres | the same role, four rows in `Security` |
| Replica visitors | the three tabs of the HTML replica, all departments | the public Pages site, no login; the About section explains the role |

## The questions it answers

- Where does the year stand against budget: revenue, gross margin, EBITDA and EBIT for the closed months, by department and by month?
- Which department and which account group explain the gap between budget EBIT and actual EBIT?
- What does the year look like at the end: actuals to the last closed month plus the Q4 forecast, against the full-year budget?
- How did each line develop over three years, month by month, against budget and forecast?
- Where do the operating expenses go, and which accounts are furthest from budget?
- What does one department look like on its own, reached by a drill-through from any department bar?

## Scope

In scope:

- the generator and the committed data files (the ledger export, the budget workbook with the Q4 forecast sheet, four master-data CSV files);
- the Power BI project (PBIP): a TMDL model with 10 tables, 36 measures, three parameters and the role `Department head`; a PBIR report with six pages, a tooltip page, a hidden reconciliation page and the theme `Kaldora Dark`;
- an independent computation of the headline numbers in Python (`tools/reference.py`) and the reconciliation table;
- the HTML replica on GitHub Pages, built from the same reference;
- tests, CI, documentation, decision records and one validation session in Power BI Desktop;
- release v0.1.0 and a card on the portfolio site.

Out of scope: Publish to web and any deployment to the Power BI service (`tools/pbi/make_public_variant.py` already builds the role-free copy that Publish to web would need); balance sheet and cash flow; currencies other than EUR; overhead allocation to departments (the support departments report their own costs); a fiscal year other than the calendar year; journal-line detail (the export holds monthly balances); what-if planning or writeback; a mobile layout of the report.

## Acceptance criteria

1. `tools/make_data.py --check` is clean, the data files are committed and every band of the generator holds ([data model](data-model.md#generator)).
2. CI is green on `main`; Pages serves https://harispaartan.github.io/financial-reporting-dashboard/.
3. The PBIP opens, refreshes and renders every visual in Power BI Desktop without an error; the files Desktop saves are committed after a review of the diff.
4. The thirteen checks R1 to R13 of [the reconciliation](reconciliation.md) match between Python and Desktop.
5. Under View as, a department head sees one department and the Head of Operations four.
6. Screenshots of the report pages, the model and the replica sit in both READMEs; the Status sections claim only verified facts.
7. The local checks pass: scrub, links, contrast, screenshots at 1440 and 390 px without external requests or console errors, page weight at most 3 MB.
8. Release v0.1.0 with a changelog entry, an annotated tag and a GitHub Release, and the card on the portfolio site.
