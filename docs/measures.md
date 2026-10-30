# Measures

The 36 measures of `_Measures` in `pbip/FinancialReportingDashboard.SemanticModel/definition/tables/_Measures.tmdl`, grouped by display folder. Each section gives the purpose (the measure's description in the model), the DAX exactly as in the TMDL (`tests/test_docs.py` compares them), the format and the folder. The rules behind them are in [the data model](data-model.md#pl-layout-and-sign-convention) and the decision records.

Formats: amounts use the dynamic format string `IF([Is ratio line], "0.0 %", "#,0,;(#,0,);0")`, which shows EUR thousand through the thousands scaler (the comma before the semicolon) with negatives in parentheses, and a percentage on the margin lines. Dynamic format strings need display units set to none, which the theme `Kaldora Dark` does for every visual. The `Check value` format follows `ReconCheck[Kind]`.

## Base

The building blocks: the signed amount, the last closed month, the line in context and the line value `P&L Value`, on which every scenario measure builds.

### Amount

Signed amount, EUR: income +, expense - (FactGL[Amount], profit contribution).

```dax
SUM(FactGL[Amount])
```

Folder `Base` · format `#,0.00`.

### Last actual date

Month end of the last closed month: the latest actual date, whatever the slicers.

```dax
EOMONTH(CALCULATE(MAX(FactGL[Date]), REMOVEFILTERS(), DimScenario[Scenario] = "Actual"), 0)
```

Folder `Base` · format `d mmm yyyy`.

### Is ratio line

TRUE on the margin lines (line type Ratio).

```dax
SELECTEDVALUE(DimPnLLine[Line type]) = "Ratio"
```

Folder `Base` · format `"""TRUE"";""TRUE"";""FALSE"""`.

### Line sign

Display sign of the line in context: +1 income and subtotals, -1 cost groups; 1 without a line.

```dax
SELECTEDVALUE(DimPnLLine[Sign], 1)
```

Folder `Base` · format `0`.

### P&L Value

Value of the P&L line in context: a group in display sign, a subtotal as the signed sum of the groups above it, a ratio as that subtotal over revenue; without a line the EBIT contribution.

```dax
VAR _type = SELECTEDVALUE(DimPnLLine[Line type])
VAR _bound = SELECTEDVALUE(DimPnLLine[Bound])
VAR _detail = ISINSCOPE(DimAccount[Subgroup]) || ISINSCOPE(DimAccount[Account label])
VAR _upTo = CALCULATE([Amount], REMOVEFILTERS(DimPnLLine), DimAccount[Group sort] < _bound)
VAR _rev = CALCULATE([Amount], REMOVEFILTERS(DimPnLLine), DimPnLLine[Line key] = "REV")
RETURN
    SWITCH(
        _type,
        "Group", [Amount] * [Line sign],
        "Subtotal", IF(NOT _detail, _upTo),
        "Ratio", IF(NOT _detail, DIVIDE(_upTo, _rev)),
        [Amount]
    )
```

Folder `Base` · format string definition `IF([Is ratio line], "0.0 %", "#,0,;(#,0,);0")`.

## Scenarios

One measure per scenario, the latest estimate, the closed-month budget and the two measures the P&L matrices show.

### Actual

P&L Value of the ledger actuals.

```dax
CALCULATE([P&L Value], DimScenario[Scenario] = "Actual")
```

Folder `Scenarios` · format string definition `IF([Is ratio line], "0.0 %", "#,0,;(#,0,);0")`.

### Budget

P&L Value of the budget of the year.

```dax
CALCULATE([P&L Value], DimScenario[Scenario] = "Budget")
```

Folder `Scenarios` · format string definition `IF([Is ratio line], "0.0 %", "#,0,;(#,0,);0")`.

### Forecast

P&L Value of the Q4 2025 forecast.

```dax
CALCULATE([P&L Value], DimScenario[Scenario] = "Forecast")
```

Folder `Scenarios` · format string definition `IF([Is ratio line], "0.0 %", "#,0,;(#,0,);0")`.

### Outlook

Latest estimate: actuals up to the last closed month, forecast after it.

```dax
VAR _last = [Last actual date]
VAR _cells =
    FILTER(
        CROSSJOIN(ALL(DimScenario[Scenario]), VALUES(DimDate[Date])),
        (DimScenario[Scenario] = "Actual" && DimDate[Date] <= _last)
            || (DimScenario[Scenario] = "Forecast" && DimDate[Date] > _last)
    )
RETURN CALCULATE([P&L Value], _cells)
```

Folder `Scenarios` · format string definition `IF([Is ratio line], "0.0 %", "#,0,;(#,0,);0")`.

### Budget (closed months)

Budget of the closed months only, the basis of every comparison with actuals.

```dax
VAR _last = [Last actual date]
RETURN CALCULATE([Budget], FILTER(VALUES(DimDate[Date]), DimDate[Date] <= _last))
```

Folder `Scenarios` · format string definition `IF([Is ratio line], "0.0 %", "#,0,;(#,0,);0")`.

### P&L Statement

The scenario picked in the Scenario slicer: Budget, Forecast (the outlook) or Actual.

```dax
SWITCH(
    SELECTEDVALUE(DimScenario[Scenario], "Actual"),
    "Budget", [Budget],
    "Forecast", [Outlook],
    [Actual]
)
```

Folder `Scenarios` · format string definition `IF([Is ratio line], "0.0 %", "#,0,;(#,0,);0")`.

### P&L Matrix

Cell of the P&L matrix: a month, YTD (January to the end of the month range) or the full year.

```dax
VAR _col = SELECTEDVALUE(PnLColumn[Sort])
RETURN
    SWITCH(
        TRUE(),
        ISBLANK(_col), BLANK(),
        _col <= 12, CALCULATE([P&L Statement], KEEPFILTERS(DimDate[Month number] = _col)),
        _col = 13, CALCULATE([P&L Statement], DATESYTD(DimDate[Date])),
        IF(SELECTEDVALUE(DimScenario[Scenario], "Actual") = "Budget", [Budget full year], [Full-year outlook])
    )
```

Folder `Scenarios` · format string definition `IF([Is ratio line], "0.0 %", "#,0,;(#,0,);0")`.

## Variance

Variances in display sign, their status and their effect on EBIT.

### Variance

Actual minus the budget of the closed months, in display sign; percentage points on ratio lines.

```dax
VAR _a = [Actual]
VAR _b = [Budget (closed months)]
RETURN IF(NOT (ISBLANK(_a) && ISBLANK(_b)), (_a - _b) * IF([Is ratio line], 100, 1))
```

Folder `Variance` · format string definition `IF([Is ratio line], "+0.0"" pp"";-0.0"" pp"";0.0"" pp""", "+#,0,;-#,0,;0")`.

### Variance %

Variance as a share of the absolute closed-month budget; blank on ratio lines.

```dax
IF(NOT [Is ratio line], DIVIDE([Variance], ABS([Budget (closed months)])))
```

Folder `Variance` · format `+0.0 %;-0.0 %;0.0 %`.

### Favourable

1 favourable, -1 unfavourable, 0 on plan (within 1 % or 0.1 pp); blank without a variance.

```dax
VAR _v = [Variance]
VAR _p = [Variance %]
VAR _neutral = IF([Is ratio line], ABS(_v) < 0.1, NOT ISBLANK(_p) && ABS(_p) < 0.01)
RETURN IF(NOT ISBLANK(_v), IF(_neutral, 0, SIGN(_v * [Line sign])))
```

Folder `Variance` · format `0`.

### Profit impact

Effect of the variance on EBIT: Variance times the line sign; the four group impacts add up to the EBIT variance.

```dax
IF(NOT [Is ratio line], [Variance] * [Line sign])
```

Folder `Variance` · format `+#,0,;-#,0,;0`.

### Outlook vs budget

Full-year outlook minus the full-year budget; percentage points on ratio lines.

```dax
([Full-year outlook] - [Budget full year]) * IF([Is ratio line], 100, 1)
```

Folder `Variance` · format string definition `IF([Is ratio line], "+0.0"" pp"";-0.0"" pp"";0.0"" pp""", "+#,0,;-#,0,;0")`.

### Favourable label

The status in words: Fav., Unfav. or On plan; blank without a variance.

```dax
VAR _f = [Favourable]
RETURN IF(NOT ISBLANK(_f), SWITCH(_f, 1, "Fav.", -1, "Unfav.", "On plan"))
```

Folder `Variance` · text.

## Time

Year to date and full year.

### Actual YTD

Actuals from January to the month in context; blank after the last closed month.

```dax
IF(MIN(DimDate[Date]) <= [Last actual date], CALCULATE([Actual], DATESYTD(DimDate[Date])))
```

Folder `Time` · format string definition `IF([Is ratio line], "0.0 %", "#,0,;(#,0,);0")`.

### Budget YTD

Budget from January to the month in context (the full plan path).

```dax
CALCULATE([Budget], DATESYTD(DimDate[Date]))
```

Folder `Time` · format string definition `IF([Is ratio line], "0.0 %", "#,0,;(#,0,);0")`.

### Outlook YTD

Outlook from January to the month in context.

```dax
CALCULATE([Outlook], DATESYTD(DimDate[Date]))
```

Folder `Time` · format string definition `IF([Is ratio line], "0.0 %", "#,0,;(#,0,);0")`.

### Full-year outlook

Outlook of the whole year in context: actuals to date plus the forecast.

```dax
VAR _y = MAX(DimDate[Year])
RETURN CALCULATE([Outlook], REMOVEFILTERS(DimDate), DimDate[Year] = _y)
```

Folder `Time` · format string definition `IF([Is ratio line], "0.0 %", "#,0,;(#,0,);0")`.

### Budget full year

Budget of the whole year in context.

```dax
VAR _y = MAX(DimDate[Year])
RETURN CALCULATE([Budget], REMOVEFILTERS(DimDate), DimDate[Year] = _y)
```

Folder `Time` · format string definition `IF([Is ratio line], "0.0 %", "#,0,;(#,0,);0")`.

## Lines

Actual values of single lines for the KPI tiles; they replace the line in context.

### Revenue

Actual revenue of the selected period, whatever the line in context.

```dax
CALCULATE([Actual], REMOVEFILTERS(DimPnLLine), DimPnLLine[Line key] = "REV")
```

Folder `Lines` · format `#,0,;(#,0,);0`.

### Gross margin %

Actual gross margin: gross profit over revenue.

```dax
CALCULATE([Actual], REMOVEFILTERS(DimPnLLine), DimPnLLine[Line key] = "GPM")
```

Folder `Lines` · format `0.0 %`.

### EBITDA margin %

Actual EBITDA margin: EBITDA over revenue.

```dax
CALCULATE([Actual], REMOVEFILTERS(DimPnLLine), DimPnLLine[Line key] = "EBITDAM")
```

Folder `Lines` · format `0.0 %`.

### Opex % of revenue

Actual operating expenses over revenue.

```dax
DIVIDE(CALCULATE([Actual], REMOVEFILTERS(DimPnLLine), DimPnLLine[Line key] = "OPEX"), [Revenue])
```

Folder `Lines` · format `0.0 %`.

### Personnel cost

Actual cost of both personnel subgroups (direct and overhead), as a positive amount.

```dax
CALCULATE(
    -[Amount],
    REMOVEFILTERS(DimPnLLine),
    DimScenario[Scenario] = "Actual",
    DimAccount[Subgroup] IN {"Direct personnel", "Overhead personnel"}
)
```

Folder `Lines` · format `#,0,;(#,0,);0`.

### Personnel cost % of revenue

Personnel cost over revenue.

```dax
DIVIDE([Personnel cost], [Revenue])
```

Folder `Lines` · format `0.0 %`.

## Formatting

Hidden measures that conditional formatting binds to; the hex values are the dark values of the kit tokens `ok`, `warn`, `muted` and `surface-2`, kept equal by `tests/pbi/test_theme.py`.

### Favourable colour

Font colour of a variance: ok when favourable, warn when unfavourable, muted on plan.

```dax
VAR _f = [Favourable]
RETURN IF(NOT ISBLANK(_f), SWITCH(_f, 1, "#3DDC97", -1, "#FACC15", "#93A1B0"))
```

Folder `Formatting` · text · hidden.

### Row tint

Background of the subtotal and ratio rows of the P&L matrices (kit token surface-2).

```dax
IF(
    SELECTEDVALUE(DimPnLLine[Line type]) IN {"Subtotal", "Ratio"}
        && NOT ISINSCOPE(DimAccount[Subgroup])
        && NOT ISINSCOPE(DimAccount[Account label]),
    "#182130"
)
```

Folder `Formatting` · text · hidden.

## Info

Header texts, cards and the reconciliation page.

### Rows

Rows of FactGL in the filter context.

```dax
COUNTROWS(FactGL)
```

Folder `Info` · format `#,0`.

### Data as of

Header text: the last closed month and the last forecast month, in English.

```dax
VAR _forecast = CALCULATE(MAX(FactGL[Date]), REMOVEFILTERS(), DimScenario[Scenario] = "Forecast")
RETURN "Actuals through " & FORMAT([Last actual date], "mmm yyyy", "en-US") & " · forecast through "
    & FORMAT(_forecast, "mmm yyyy", "en-US")
```

Folder `Info` · text.

### Selected department

The department in context, or All departments.

```dax
SELECTEDVALUE(DimCostCentre[Name], "All departments")
```

Folder `Info` · text.

### Department head

Head of the department in context; blank for several.

```dax
SELECTEDVALUE(DimCostCentre[Head name])
```

Folder `Info` · text.

### Check value

Value of the reconciliation check in context (ReconCheck[Id]); it ignores the slicers, not the role.

```dax
VAR _id = SELECTEDVALUE(ReconCheck[Id])
RETURN
    SWITCH(
        _id,
        "R1", CALCULATE([Rows], REMOVEFILTERS()),
        "R2", CALCULATE([Revenue], REMOVEFILTERS(), DimDate[Year] = 2023),
        "R3", CALCULATE([Actual], REMOVEFILTERS(), DimDate[Year] = 2024, DimPnLLine[Line key] = "EBITDA"),
        "R4", CALCULATE([Actual], REMOVEFILTERS(), DimDate[Year] = 2025, DimDate[Month number] <= 9, DimPnLLine[Line key] = "EBIT"),
        "R5", CALCULATE([Gross margin %], REMOVEFILTERS(), DimDate[Year] = 2025, DimDate[Month number] <= 9),
        "R6", CALCULATE([Budget], REMOVEFILTERS(), DimDate[Year] = 2025, DimPnLLine[Line key] = "REV"),
        "R7", CALCULATE([Budget (closed months)], REMOVEFILTERS(), DimDate[Year] = 2025, DimPnLLine[Line key] = "EBITDA"),
        "R8", CALCULATE([Forecast], REMOVEFILTERS(), DimDate[Year] = 2025, DimPnLLine[Line key] = "REV"),
        "R9", CALCULATE([Full-year outlook], REMOVEFILTERS(), DimDate[Year] = 2025, DimPnLLine[Line key] = "EBIT"),
        "R10", CALCULATE([Variance], REMOVEFILTERS(), DimDate[Year] = 2025, DimDate[Month number] <= 9,
            DimPnLLine[Line key] = "EBITDA", DimCostCentre[Cost centre] = "CC30"),
        "R11", CALCULATE([Actual], REMOVEFILTERS(), DimDate[Year] = 2025, DimDate[Month number] <= 9, DimPnLLine[Line key] = "OPEX"),
        "R12", CALCULATE([Personnel cost % of revenue], REMOVEFILTERS(), DimDate[Year] = 2024),
        "R13", CALCULATE([Revenue], REMOVEFILTERS(), DimDate[Year] = 2025, DimDate[Month number] <= 9,
            DimCostCentre[Cost centre] = "CC30")
    )
```

Folder `Info` · format string definition `SWITCH(SELECTEDVALUE(ReconCheck[Kind]), "ratio", "0.0000", "count", "#,0", "#,0.00")` · hidden.

## Role Department head

Department heads see only the cost centres listed for their sign-in address in Security. The role is the only one in the model; its members are assigned in the Power BI service and are not part of the repository. `Security` is hidden and has no relationship, so no relationship filters in both directions; the filter on `DimCostCentre` reaches `FactGL` through the normal relationship. Addresses are lower case on both sides. `REMOVEFILTERS` cannot clear a role filter, so `[Last actual date]` and `[Check value]` stay inside the role.

### Filter on Security

```dax
Security[User email] = LOWER(USERPRINCIPALNAME())
```

### Filter on DimCostCentre

```dax
DimCostCentre[Cost centre] IN CALCULATETABLE(VALUES(Security[Cost centre]), Security[User email] = LOWER(USERPRINCIPALNAME()))
```

## Choices in the DAX

- `Favourable label` and `Favourable colour` test for a blank status before `SWITCH`: in DAX a blank equals 0 in a comparison, so a plain `SWITCH` would show "On plan" and the muted colour on a row without any variance.
- `Favourable` counts a variance within 1 % of the closed-month budget, or within 0.1 pp on a margin line, as on plan (0). A line with a blank `Variance %` (a zero budget) is never on plan by that rule; it is favourable or unfavourable by its sign.
- `Outlook` filters one table of scenario and date pairs (Actual up to `[Last actual date]`, Forecast after it) instead of adding two measures, so the ratio lines divide the outlook subtotal by the outlook revenue, not two separate sums.
- `Budget (closed months)` keeps the dates that the Year and Months filters leave (`VALUES(DimDate[Date])`) up to `[Last actual date]`, the pattern `Outlook` uses, so a month range ending before September still compares the same months on both sides.
- `P&L Matrix` reads the column from the disconnected `PnLColumn` table; YTD runs from January to the last month of the month range, and Full year shows the budget under the scenario Budget and the outlook otherwise.
- `Personnel cost` is a positive amount (`-[Amount]` over both personnel subgroups), so `Personnel cost % of revenue` is a positive share of revenue.
- `Check value` holds one branch per reconciliation check, each a `CALCULATE` with `REMOVEFILTERS()` and the filters of the check ([reconciliation](reconciliation.md)); `REMOVEFILTERS` does not remove the role, so under View as the checks show the role's departments.
