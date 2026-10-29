# Handover

Notes for the person who runs the monthly close in the dashboard or changes it. Commands run from the repository root with uv; the Power BI steps need Power BI Desktop on Windows.

## Set up

```bash
uv sync
uv run python tools/make_data.py --check          # the committed data equal a fresh build
uv run pytest -q                                   # every offline test; the TOM test skips without build/tom
```

Open `pbip\FinancialReportingDashboard.pbip` in Power BI Desktop. Home, Transform data, Edit parameters: `DataFolder` must name this clone's `data\` folder with the trailing backslash (the default is `C:\financial-reporting-dashboard\data\`). OK, Apply changes, then Refresh. No credentials are involved: every source is a local file.

The optional TOM parse test needs Microsoft's Tabular Object Model assemblies and pythonnet:

```bash
uv sync --group pbi
uv run python tools/pbi/copy_tom.py --from <folder with the six Microsoft.AnalysisServices DLLs>
uv run --group pbi pytest tests/pbi/test_tmdl_tom.py -q
```

## Monthly close

1. Replace `data/gl_actuals.csv` with the new export: the same four columns (`period`, `cost_centre`, `account`, `amount`), every closed month from January 2023, amounts in ledger sign. `Last actual date` follows the latest month in the export, so the closed-month budget, the outlook and the header text move by themselves.
2. After the September close, add the sheet `Forecast <year>` to `data/budget.xlsx` with the layout of the budget sheets: the title in A1, the note in A2, row 3 empty, the header in row 4 with `Cost centre`, `Account`, `Account name` and the open months (`Oct`, `Nov`, `Dec`), then a total column; one row per cost centre and account. The forecast holds only the open months.
3. For a new year, add the sheet `Budget <year>` with all twelve months and extend `EndDate` (Edit parameters) to the 31 December of that year, so `DimDate` covers it.
4. Home, Refresh. The page Reconciliation shows the checks on the new data; they match `docs/reconciliation.md` only while the data files are the committed ones.
5. For this demo the files are generated: change the constants in `tools/make_data.py`, run `uv run python tools/make_data.py` and `uv run python tools/build_replica_data.py`, then update the bands in `tests/test_make_data.py` and the Python column of `docs/reconciliation.md` from the new run (`uv run python tools/reference.py`).

## Adding an account

Add a row to `data/chart_of_accounts.csv`: the account number, its name, the group (one of the four groups of `data/pnl_layout.csv`), its subgroup, the sign (+1 income, −1 expense) and the next `sort_order`. Refresh; the P&L lines pick it up through its group, and no measure changes ([ADR 0001](adr/0001-pnl-layout-and-sign-convention.md)). An account in the export that is missing from the chart of accounts has no line and shows only in the totals without a line in context, so add the account before its first posting. In the demo, add it to `ACCOUNTS` and `POSTING` in `tools/make_data.py` as well.

## Adding a cost centre

Add a row to `data/cost_centres.csv` (`cost_centre`, `name`, `type` Operating or Support, `head_name`, `head_email` in lower case, `sort_order`) and the head's row to `data/security.csv`. Add the cost centre's rows to the budget sheets. Refresh; the Department slicer and the department bars show it. In the demo, `COST_CENTRES` and `POSTING` in `tools/make_data.py` hold the same lists, and `tests/test_make_data.py` checks the six cost centres.

## Adding a Security row

`data/security.csv` holds one row per address and cost centre: `user_email` (the sign-in address in lower case, as Power BI reports it through `USERPRINCIPALNAME()`, lower-cased by the role) and `cost_centre`. A person for several departments has several rows, like the Head of Operations. Refresh; no model change is needed. Check it in Desktop: Modeling, View as, Other user = the new address, tick `Department head`, OK; the Department slicer lists only that person's departments. An address without a row sees no data.

In the Power BI service the role needs members: on the semantic model, More options, Security, role `Department head`, add the department heads or a group. Workspace members with edit rights see all data regardless of the role.

## Building the role-free copy

Publish to web cannot use a model with row-level security. The public variant drops the role and the `Security` table and keeps everything else:

```bash
uv run python tools/pbi/make_public_variant.py
```

It writes `build/public/FinancialReportingDashboard (public).pbip` with its model and report folders and a `README.txt`; `build/` is git-ignored. Open that copy in Desktop, refresh, and publish it, never the project under `pbip/`. Publishing is not part of this repository's scope.

## Changing the report

Until the first save in Power BI Desktop, the report is generated: edit `tools/pbi/pages.json` (or `tools/pbi/build_report.py`), run `uv run python tools/pbi/build_report.py` and `uv run pytest tests/pbi -q`. After the first save, the files Desktop wrote are the source: change the report in Desktop or in the PBIR files directly, and do not run `build_report.py` again; it would overwrite Desktop's files ([Desktop validation](desktop-validation.md)). The lint tests keep running on the saved files.

The model is edited in the TMDL files under `pbip/FinancialReportingDashboard.SemanticModel/definition/` or in Desktop. A changed measure changes `docs/measures.md` too (`tests/test_docs.py` compares the DAX) and, when its rule changes, `tools/reference.py` and the replica's `web/assets/pnl.js`.

## Changing the theme

The theme `Kaldora Dark` is generated from the kit's dark tokens: `uv run python tools/pbi/build_theme.py` writes `pbip/FinancialReportingDashboard.Report/StaticResources/RegisteredResources/kaldora-dark.json`; `--check` compares the content with a fresh build. The hex values in `Favourable colour` and `Row tint` must follow (`tests/pbi/test_theme.py` compares them). After the kit is updated (next section), run it again and check the contrast with `node tools/checks/contrast.mjs`.

## Updating portfolio-kit or ECharts

- Kit: with a newer tag in the local clone `E:\GITGUB\portfolio-kit`, run `uv run python tools/sync_kit.py --tag <tag>`, then `uv run python tools/sync_kit.py --check`, change the tag in `.github/workflows/ci.yml` (job `kit`), and run `node tools/checks/contrast.mjs` and the screenshots.
- ECharts: `web/vendor/echarts.min.js` is version 5.6.0 (Apache-2.0, licence in `web/vendor/LICENSE-echarts.txt`). A new version is a new download with its SHA-256 recorded in the commit message; the chart options live in `web/assets/charts.js`, and `tests/js/charts.test.mjs` and the screenshots show what changed.

## Updating Faker or numpy

Both are pinned in `pyproject.toml` (`faker==40.44.0`, `numpy==2.5.4`). Updating Faker changes the person names and e-mail addresses: regenerate the data and the replica data (`uv run python tools/make_data.py`, then `uv run python tools/build_replica_data.py`), and update the addresses in `docs/desktop-validation.md`. A numpy feature release can change the random streams and with them every number: regenerate, then update the bands and the reconciliation values. Dependabot ignores Faker and numpy feature releases for that reason.

## Checks before a push

```bash
uv run ruff check . && uv run ruff format --check .
uv run pytest -q
uv run python tools/make_data.py --check
uv run python tools/build_replica_data.py --check
uv run python tools/pbi/build_theme.py --check
node --test "tests/js/*.test.mjs"
node tools/checks/contrast.mjs
uv run python tools/check_page_weight.py
OFFLINE=1 node tools/checks/verify-site.mjs
uv run python tools/checks/scrub.py
PLAYWRIGHT_FROM=<package.json of a folder with playwright> node tools/checks/replica.mjs
PLAYWRIGHT_FROM=<package.json of a folder with playwright> OUT=<folder outside the repository> node tools/checks/shots.mjs
```

`replica.mjs` and `shots.mjs` serve `web/` on 127.0.0.1 and open the replica with the installed Chrome; both fail on any external request or console error, and `shots.mjs` also on sideways scrolling; the screenshots go to `OUT`.
