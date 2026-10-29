// The P&L engine of the replica: the measures of spec section 7 on the facts of data/kaldora.json.
// Pure ES module without DOM access, tested by tests/js/pnl.test.mjs against the reference values in `headline`.
// Amounts are integer cents of profit contribution (income +, expense -), ratios are fractions, null is blank.
// A context is { months, ccs, line, subgroup, account }: month indices from 2023-01, the cost centres (null: all),
// and the P&L line, subgroup and account in scope (null: not in scope), as a matrix row puts them in scope.
import { fmt } from '../kit/kit.js';

export const SCENARIOS = ['Actual', 'Budget', 'Forecast'];
export const MONTH_NAMES = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
export const GROUP_LINES = ['REV', 'COS', 'OPEX', 'DA'];
export const FIRST_YEAR = 2023;
const PERSONNEL = new Set(['Direct personnel', 'Overhead personnel']);

/** Month indices of months `from` to `to` of a year (the Year select and the month range). */
export function period(year, from = 1, to = 12) {
  const out = [];
  for (let m = from; m <= to; m += 1) out.push((year - FIRST_YEAR) * 12 + m - 1);
  return out;
}

/** DATESYTD: January of the year of the last month in context up to that month. */
export function ytd(months) {
  if (!months.length) return [];
  const last = Math.max(...months);
  const out = [];
  for (let t = last - (last % 12); t <= last; t += 1) out.push(t);
  return out;
}

const divide = (a, b) => (a === null || b === null || b === 0 ? null : a / b);

export function createModel(data) {
  const lines = new Map(data.layout.map((l) => [l.key, l]));
  const accounts = data.accounts;
  const lastActual = data.meta.lastActualIndex;
  const facts = {};
  for (const s of SCENARIOS) {
    facts[s] = Object.entries(data.facts[s] ?? {}).map(([key, values]) => {
      const [cc, account] = key.split('|');
      return { cc, account, values };
    });
  }
  const pairs = new Set(Object.values(data.facts).flatMap((byPair) => Object.keys(byPair)));
  const accountsWhere = (test) => new Set(accounts.filter(test).map((a) => a.account));
  const lineAccounts = new Map([...lines.keys()].map((k) => [k, accountsWhere((a) => a.line === k)]));

  /** [Amount]: the signed sum of the fact rows in the cells ([scenario, month] pairs); null when there is none. */
  function amount(cells, ccs, accountSet) {
    let total = 0;
    let found = false;
    for (const [s, t] of cells) {
      for (const f of facts[s]) {
        if (!accountSet.has(f.account) || (ccs && !ccs.includes(f.cc))) continue;
        const v = f.values[t];
        if (v !== null && v !== undefined) {
          total += v;
          found = true;
        }
      }
    }
    return found ? total : null;
  }

  const scope = (ctx) =>
    accountsWhere((a) => (ctx.subgroup == null || a.subgroup === ctx.subgroup) && (ctx.account == null || a.account === ctx.account));
  const isRatio = (ctx) => ctx.line != null && lines.get(ctx.line).type === 'Ratio';
  const lineSign = (ctx) => (ctx.line == null ? 1 : lines.get(ctx.line).sign);
  const cells = (scenario, months) => months.map((t) => [scenario, t]);
  const ccsOf = (ctx) => ctx.ccs ?? null;

  /** [P&L Value]: Group lines in display sign, Subtotals as the signed sum below the bound, Ratios over revenue. */
  function pnlValue(ctx, inCells) {
    const accountsInScope = scope(ctx);
    if (ctx.line == null) return amount(inCells, ccsOf(ctx), accountsInScope);
    const line = lines.get(ctx.line);
    if (line.type === 'Group') {
      const mine = new Set([...lineAccounts.get(line.key)].filter((a) => accountsInScope.has(a)));
      const v = amount(inCells, ccsOf(ctx), mine);
      return v === null ? null : v * line.sign;
    }
    if (ctx.subgroup != null || ctx.account != null) return null;
    const upTo = amount(inCells, ccsOf(ctx), accountsWhere((a) => a.groupSort < line.bound));
    if (line.type === 'Subtotal') return upTo;
    return divide(upTo, amount(inCells, ccsOf(ctx), lineAccounts.get('REV')));
  }

  const actual = (ctx) => pnlValue(ctx, cells('Actual', ctx.months));
  const budget = (ctx) => pnlValue(ctx, cells('Budget', ctx.months));
  const forecast = (ctx) => pnlValue(ctx, cells('Forecast', ctx.months));
  const outlook = (ctx) =>
    pnlValue(ctx, ctx.months.map((t) => [t <= lastActual ? 'Actual' : 'Forecast', t]));
  const budgetClosed = (ctx) => budget({ ...ctx, months: ctx.months.filter((t) => t <= lastActual) });

  function variance(ctx) {
    const a = actual(ctx);
    const b = budgetClosed(ctx);
    if (a === null && b === null) return null;
    const diff = (a ?? 0) - (b ?? 0);
    return isRatio(ctx) ? diff * 100 : diff;
  }

  function variancePct(ctx) {
    if (isRatio(ctx)) return null;
    const b = budgetClosed(ctx);
    return divide(variance(ctx), b === null ? null : Math.abs(b));
  }

  function favourable(ctx) {
    const v = variance(ctx);
    if (v === null) return null;
    const p = variancePct(ctx);
    const neutral = isRatio(ctx) ? Math.abs(v) < 0.1 : p !== null && Math.abs(p) < 0.01;
    return neutral ? 0 : Math.sign(v * lineSign(ctx));
  }

  const favourableLabel = (ctx) => ({ 1: 'Fav.', [-1]: 'Unfav.', 0: 'On plan' })[favourable(ctx)] ?? null;

  function profitImpact(ctx) {
    if (isRatio(ctx)) return null;
    const v = variance(ctx);
    return v === null ? null : v * lineSign(ctx);
  }

  const fullYear = (ctx) => {
    const year = FIRST_YEAR + Math.floor(Math.max(...ctx.months) / 12);
    return { ...ctx, months: period(year) };
  };
  const fullYearOutlook = (ctx) => (ctx.months.length ? outlook(fullYear(ctx)) : null);
  const budgetFullYear = (ctx) => (ctx.months.length ? budget(fullYear(ctx)) : null);

  function pnlStatement(ctx, scenario = 'Actual') {
    if (scenario === 'Budget') return budget(ctx);
    if (scenario === 'Forecast') return outlook(ctx);
    return actual(ctx);
  }

  /** [P&L Matrix] in column 1 to 12 (a month), 13 (YTD) or 14 (Full year). */
  function pnlMatrix(ctx, column, scenario = 'Actual') {
    if (column <= 12) return pnlStatement({ ...ctx, months: ctx.months.filter((t) => t % 12 === column - 1) }, scenario);
    if (column === 13) return pnlStatement({ ...ctx, months: ytd(ctx.months) }, scenario);
    return scenario === 'Budget' ? budgetFullYear(ctx) : fullYearOutlook(ctx);
  }

  function personnelCost(ctx) {
    const v = amount(cells('Actual', ctx.months), ccsOf(ctx), accountsWhere((a) => PERSONNEL.has(a.subgroup)));
    return v === null ? null : -v;
  }

  /** Line, subgroup and account rows in matrix order for the cost centres in `ccs` (null: all). */
  function matrixRows(ccs = null) {
    const present = new Set([...pairs].filter((p) => !ccs || ccs.includes(p.split('|')[0])).map((p) => p.split('|')[1]));
    const out = [];
    for (const line of lines.values()) {
      out.push({ line: line.key, subgroup: null, account: null });
      if (line.type !== 'Group') continue;
      const mine = accounts.filter((a) => a.line === line.key && present.has(a.account)).sort((a, b) => a.sort - b.sort);
      const subgroups = [...new Set([...mine].sort((a, b) => a.subgroupSort - b.subgroupSort).map((a) => a.subgroup))];
      for (const subgroup of subgroups) {
        out.push({ line: line.key, subgroup, account: null });
        for (const a of mine.filter((x) => x.subgroup === subgroup)) out.push({ line: line.key, subgroup, account: a.account });
      }
    }
    return out;
  }

  return {
    lines,
    accounts,
    costCentres: data.cost_centres,
    lastActual,
    amount,
    isRatio,
    lineSign,
    pnlValue,
    actual,
    budget,
    forecast,
    outlook,
    budgetClosed,
    variance,
    variancePct,
    favourable,
    favourableLabel,
    profitImpact,
    fullYearOutlook,
    budgetFullYear,
    pnlStatement,
    pnlMatrix,
    revenue: (ctx) => actual({ ...ctx, line: 'REV' }),
    personnelCost,
    matrixRows,
  };
}

// ------------------------------------------------------------------ views (the replica tabs)

/** The filter context of a replica state { year, from, to, ccs, scenario }. */
export function contextOf(state, scopeOf = {}) {
  return { months: period(state.year, state.from, state.to), ccs: state.ccs?.length ? state.ccs : null, line: null, subgroup: null, account: null, ...scopeOf };
}

/** Per line: actual, budget, closed-month budget, full-year outlook and budget, variance, variance %, favourable. */
export function linesView(model, state) {
  const out = {};
  for (const key of model.lines.keys()) {
    const ctx = contextOf(state, { line: key });
    out[key] = {
      actual: model.actual(ctx),
      budget: model.budget(ctx),
      budgetClosed: model.budgetClosed(ctx),
      fullYearOutlook: model.fullYearOutlook(ctx),
      budgetFullYear: model.budgetFullYear(ctx),
      variance: model.variance(ctx),
      variancePct: model.variancePct(ctx),
      favourable: model.favourable(ctx),
    };
  }
  return out;
}

/** Profit impact of the four account groups and the EBIT variance as the total column. */
export function waterfallView(model, state) {
  const out = {};
  for (const key of GROUP_LINES) out[key] = model.profitImpact(contextOf(state, { line: key }));
  out.total = model.variance(contextOf(state, { line: 'EBIT' }));
  return out;
}

/** EBITDA profit impact per cost centre (the cost centres of the state, all six when none is chosen). */
export function departmentsView(model, state) {
  const out = {};
  for (const c of model.costCentres) {
    if (state.ccs?.length && !state.ccs.includes(c.code)) continue;
    out[c.code] = model.profitImpact(contextOf({ ...state, ccs: [c.code] }, { line: 'EBITDA' }));
  }
  return out;
}

/** The P&L statement: every row with its 14 columns (Jan to Dec, YTD, Full year); rows without a value are left out. */
export function statementView(model, state) {
  const ccs = state.ccs?.length ? state.ccs : null;
  const rows = [];
  for (const row of model.matrixRows(ccs)) {
    const ctx = contextOf(state, row);
    const cellsOfRow = [];
    for (let col = 1; col <= 14; col += 1) cellsOfRow.push(model.pnlMatrix(ctx, col, state.scenario ?? 'Actual'));
    if (cellsOfRow.some((v) => v !== null)) rows.push({ ...row, cells: cellsOfRow });
  }
  return rows;
}

/** 36 months of actual, budget and forecast for one line; ignores year and months, honours the cost centres. */
export function trendView(model, state) {
  const ccs = state.ccs?.length ? state.ccs : null;
  const out = { actual: [], budget: [], forecast: [] };
  for (let t = 0; t < 36; t += 1) {
    const ctx = { months: [t], ccs, line: state.line, subgroup: null, account: null };
    out.actual.push(model.actual(ctx));
    out.budget.push(model.budget(ctx));
    out.forecast.push(model.forecast(ctx));
  }
  return out;
}

// ------------------------------------------------------------------ formats (as the report's format strings)

const grouped = new Intl.NumberFormat('en-GB', { maximumFractionDigits: 0 });
const BLANK = '–';

/** "#,0,;(#,0,);0": EUR thousand, negatives in parentheses. */
export function kEur(cents) {
  if (cents === null || cents === undefined) return BLANK;
  if (cents === 0) return '0';
  const text = grouped.format(Math.round(Math.abs(cents) / 100000));
  return cents < 0 ? `(${text})` : text;
}

/** "+#,0,;-#,0,;0": a signed variance in EUR thousand. */
export function signedK(cents) {
  if (cents === null || cents === undefined) return BLANK;
  if (cents === 0) return '0';
  return `${cents < 0 ? '−' : '+'}${grouped.format(Math.round(Math.abs(cents) / 100000))}`;
}

export const pct = (x) => (x === null || x === undefined ? BLANK : fmt.pct(x));
export const signedPct = (x) => (x === null || x === undefined ? BLANK : `${x > 0 ? '+' : ''}${fmt.pct(x)}`);
/** A variance already in percentage points (the report multiplies ratio variances by 100). */
export const pp = (v) => (v === null || v === undefined ? BLANK : fmt.pp(v / 100));

/** A line value: a ratio line as a percentage, any other line in EUR thousand. */
export function lineValue(model, key, value) {
  return model.lines.get(key).type === 'Ratio' ? pct(value) : kEur(value);
}

/** A variance: pp on ratio lines, signed EUR thousand otherwise. */
export function lineVariance(model, key, value) {
  return model.lines.get(key).type === 'Ratio' ? pp(value) : signedK(value);
}

export const KPI_LINES = ['REV', 'GPM', 'EBITDA', 'EBITDAM', 'EBIT'];

/** The five KPI tiles of the P&L statement: value, delta against the closed-month budget and its kind. */
export function kpiView(model, state) {
  const all = linesView(model, state);
  return KPI_LINES.map((key) => {
    const line = all[key];
    const ratio = model.lines.get(key).type === 'Ratio';
    const delta = ratio ? pp(line.variance) : signedPct(line.variancePct);
    const kind = line.favourable === 1 ? 'up' : line.favourable === -1 ? 'down' : 'neutral';
    return { key, label: model.lines.get(key).line, value: lineValue(model, key, line.actual), delta: `${delta} vs budget`, kind };
  });
}
