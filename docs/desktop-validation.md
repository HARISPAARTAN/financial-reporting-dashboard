# Power BI Desktop validation

The one validation session in Power BI Desktop, as a checklist. The person in Desktop does all the clicking and typing; the reviewer reads the screen captures (`tools/checks/capture_screen.ps1`). Any credentials dialog is answered by the person in Desktop; this project reads local files only, so none is expected.

## Before the session

- Every offline test is green: `uv run pytest -q` (the TOM parse test with `uv run --group pbi pytest tests/pbi/test_tmdl_tom.py -q` after `uv run python tools/pbi/copy_tom.py --from <folder with the six assemblies>`).
- No Desktop cache exists: `find pbip -name cache.abf` prints nothing.
- The report equals its source: `uv run python tools/pbi/build_report.py` followed by `git status --short pbip` prints nothing.
- The Python column of `docs/reconciliation.md` is filled and `tests/test_measures.py` passes.

## Source of the report

- **Until the first save in Desktop**, `tools/pbi/pages.json` and `tools/pbi/build_report.py` generate the report files (pages, visuals, bookmarks, `report.json`); a fix to the report goes there and the files are generated again. The TMDL files are edited directly.
- **After the first save**, the files Desktop wrote are the source. `build_report.py` is not run again: it would overwrite Desktop's normalisation and every fix made in the session. The lint tests keep running on the saved files.

## Addresses for View as

| Who | Address | Sees |
|---|---|---|
| Head of Operations | `mariesophie.pokorny@kaldora.example` | Cleaning Services, Technical Maintenance, Security Services, Catering |
| Head of Security Services | `kerstin.schaller@kaldora.example` | Security Services |

Both come from `data/security.csv`; a regenerated data set with other names changes them (see [handover](handover.md#updating-faker-or-numpy)).

## Steps

1. Close all Desktop windows. Open `E:\GITGUB\financial-reporting-dashboard\pbip\FinancialReportingDashboard.pbip`. If Desktop asks for the preview features `Power BI Project (.pbip) save option` and `Store semantic model using TMDL format`: File, Options and settings, Options, Preview features, tick both, OK, restart Desktop and open the project again.
2. An error dialog (for example "Unable to open document", "TMDL Format Error" or a PBIR schema error with a file name): copy its text unchanged to the reviewer and close Desktop without saving. The error loop below applies.
3. Home, Transform data, Edit parameters: `DataFolder` must name the clone's `data\` folder with a trailing backslash (`E:\GITGUB\financial-reporting-dashboard\data\`). OK, Apply changes, then Home, Refresh. No credentials are involved; if a privacy-level dialog appears, set every listed source (the data files) to Organizational. Every table loads; for a table that fails, copy its error text to the reviewer.
4. Model view: five relationships are drawn (`FactGL` to `DimDate`, `DimAccount`, `DimCostCentre` and `DimScenario`; `DimAccount` to `DimPnLLine`); `DimDate`, Table tools: Mark as date table is set on `Date`; `Security`, `PnLColumn` and `ReconCheck` have no relationship.
5. Report view, page Reconciliation (hidden in view mode, shown with a hidden icon in Desktop). Capture the table (13 rows, R1 to R13) and the card `Fact rows` (6,936), and enter the values in the Desktop column of `docs/reconciliation.md`. R7 must read 1,971,300.00; 7,977,000.00 means the closed-month budget lost the Year filter. Fix a mismatch in the DAX first and read the page again; take the screenshots afterwards.
6. The default state of every page (Ctrl+click on Reset first if a slicer moved). Open P&L statement, Variance analysis, Trend, Opex, Department detail (from its page tab: all departments) and Info, then the page Line tooltip and the model view; capture each.
7. Interactions, each captured: on P&L statement, expand Revenue and Operating expenses with the + icons of the matrix; on Variance analysis, a click on a waterfall column (only the matrix follows it; the bars and the tiles are set to no filtering), then right-click on the Security Services bar, Drill through, Department detail, and Back; on Trend, the pointer resting on a month of "Monthly actual, budget and forecast", so the tooltip page shows; Ctrl+click on Reset on each page that has it.
8. Row-level security: Modeling, View as, Other user = the Head of Operations address above, tick `Department head`, OK. Open P&L statement: the Department slicer lists the four operating departments, and Revenue shows `33,883`, EBITDA `5,687` with `-4.9 %`. Capture it. Repeat with the head of Security Services: one department, Revenue `6,435` (R13). Capture it, then Stop viewing.
9. Note Desktop's version (Help, About) for the session line of `docs/reconciliation.md`. File, Save; close Desktop. Then follow "After the session".

## What to check on the pages

Expected tiles on P&L statement in the default state (Year 2025, months 1 to 12, all departments, Scenario Actual): Revenue `33,883` with `-1.1 %`, Gross margin % `21.1 %` with `-0.6 pp`, EBITDA `1,686` with `-14.5 %`, EBITDA margin % `5.0 %` with `-0.8 pp`, EBIT `884` with `-24.7 %`; the delta cards in the warning colour. No visual may show "Can't display the visual" or a red error icon; otherwise choose "See details" and copy the text to the reviewer.

Some formatting objects are written from the published schemas but only Desktop shows whether it applies them. Each has a fallback in Desktop; a fallback used is noted for the commit message.

| Check | Expected | Fallback in Desktop |
|---|---|---|
| Amounts | EUR thousand without a unit suffix (`33,883`, negatives in parentheses), margins as `21.1 %` | Format, the visual's values or callout, Display units None |
| P&L matrix (P&L statement) | stepped layout, + and - icons, the ten lines collapsed, subtotals of subgroups above their accounts, no grand total row or column | Format, Row headers, +/- icons on; Layout Stepped; Subtotals, Row subtotals position Top; Grand total, Rows and Columns off |
| Row tint | Gross profit, the margins, EBITDA and EBIT on the tinted background, the group lines on the surface | Format, Cell elements, Background color, fx, Field value, `Row tint` |
| Variance colours | `Variance`, `Variance %` and `Status` in the ok colour when favourable, the warning colour when unfavourable, muted on plan (Variance analysis, Opex, Department detail) | Format, Cell elements, Font color, fx, Field value, `Favourable colour` |
| KPI deltas | the `vs budget` card under each value card, its text in the favourable colour, nothing cut off | Format, Callout value, Color, fx, Field value, `Favourable colour`; resize the two cards inside the tile |
| Department bars (Variance analysis) | six bars with data labels: Cleaning Services and Catering in the warning colour, Technical Maintenance and Security Services in the ok colour, Administration and Sales & Marketing muted | Format, Bars, Color, fx, Field value, `Favourable colour` |
| Waterfall (Variance analysis) | four account groups and the total column (Desktop captions it Total); increases ok, decreases warning, the total in the muted colour | Format, Sentiment colors: Increase, Decrease and Total |
| Trend lines | Actual solid, Budget dashed and muted, Forecast dotted in the fourth series colour | Format, Lines, series Budget Line style Dashed, series Forecast Line style Dotted |
| Treemap (Opex) | the five opex subgroups with their accounts | Build, Category `Subgroup`, Details `Account label` |
| Largest opex overspends (Opex) | ten rows, one per account, ranked by the signed `Variance`, overspends first | Filters pane, Account label, Top N 10 by Variance |
| Slicer row | Year lists 2023 to 2025 with 2025 selected; Months is a slider from 1 to 12; Scenario is a tile slicer with Actual selected; Trend has Department and P&L line (EBITDA) only | Format, Slicer settings, Style and Single select |
| Sync groups | a department chosen on P&L statement is chosen on Variance analysis, Trend and Opex; Year and Months follow on the pages that have them | View, Sync slicers, tick the pages for the group |
| Scenario slicer | Budget changes the matrix only, not the tiles | Format, Edit interactions, the tiles None |
| Drill-through | Department detail shows the department and its head after the drill, the Back button returns | Page Department detail, Build, Drill through, `Name`, Keep all filters off |
| Tooltip page | a pointer on a department bar or a month of the monthly trend shows five cards | Format, Tooltips, Type Report page, Page Line tooltip |
| Reset buttons | Ctrl+click restores Year 2025, Months 1 to 12, all departments, Scenario Actual, P&L line EBITDA, the matrices collapsed | set the slicers, Bookmarks pane, the page's bookmark, Update |

## Error loop

Applies until the first save in Desktop, while `build_report.py` is still the source.

1. The person in Desktop passes on Desktop's error text unchanged.
2. The reviewer finds the file and the line and fixes the cause: `tools/pbi/pages.json` or `tools/pbi/build_report.py` for report files, then generates them again; the TMDL files directly for the model. Generated report files are never edited by hand. Once Desktop has saved the report, the saved PBIR file is fixed directly instead.
3. The reviewer runs `uv run pytest tests/pbi -q` and the TOM test, and adds a regression check to the matching lint test when the kind of error is new.
4. The person in Desktop opens the project again (or chooses "Apply external changes" in Desktop's notification bar) and continues where it failed. After three rounds without progress on the same error, the session stops and the error texts are reported.

## After the session

1. `git status`: no `.pbi/` file may be staged (`localSettings.json`, `cache.abf`, `editorSettings.json` and `unappliedChanges.json` are git-ignored); another one that appears belongs in `.gitignore`, not in the commit. New `.platform` files from Desktop are committed.
2. Review `git diff pbip`: only formatting and Desktop metadata may change (line endings, property order, `lineageTag`s, the linguistic metadata in `cultures/en-US.tmdl`, `diagramLayout.json`, the theme files as formatted JSON, newer `$schema` versions). Any change of content (a renamed object, a removed visual, changed DAX, a changed data type) is a finding to explain in the commit message.
3. Run the offline tests on the saved files. If Desktop wrote a `$schema` version that is not vendored, add its URL to `unpublished` in `tools/pbi/schema_versions.json` (the schema test skips those files); vendoring the newer schema is a separate step with its own download approval. Adapt a lint test only to the formatting, never weaken what it checks.
4. Copy the screenshots of `docs/screenshots/SHOTLIST.md` into `docs/screenshots/`, fill the Desktop column of `docs/reconciliation.md` (with the session date), and commit with `chore(pbi): files as saved by Power BI Desktop; screenshots and reconciliation`.
