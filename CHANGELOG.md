# Changelog

All notable changes to this project are listed here.

## Unreleased

- Seeded generator for the data of the fictional facility-services company Kaldora Facility Services: the monthly ledger export (3,178 balances from January 2023 to September 2025), the budget workbook with three budget sheets and the Q4 2025 forecast sheet, and four CSV files; `--check` compares a fresh build with the committed files.
- Power BI project (PBIP): a TMDL model with the facts of three scenarios, the P&L layout as its own table, 36 measures (closed-month budget, outlook, variance in display sign, favourable status, profit impact) and the role `Department head` with dynamic row-level security; a PBIR report with six content pages (one of them the drill-through page Department detail), a tooltip page, a hidden reconciliation page, synced slicers, reset bookmarks and the theme `Kaldora Dark` built from the portfolio-kit tokens.
- An independent pandas reference in integer cents and the reconciliation table R1 to R13.
- HTML replica on GitHub Pages with three tabs, the report's rules and filters, ECharts 5.6.0 and portfolio-kit v0.1.0; its P&L engine recomputes four reference states.
- Offline checks of the PBIP: JSON schemas, TMDL and PBIR lint, the role-free public variant, the theme's contrast.
- Docs: client brief, data model, measures, architecture, four ADRs, handover notes and the Desktop validation checklist.
