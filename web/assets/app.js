// The replica's page code: state, filters, tabs, the P&L table, tiles and charts. Every number comes from pnl.js
// (pure, tested against the Python reference by tests/js/pnl.test.mjs) and is formatted like the report.
import { createFilterBus, createStore, initTabs, mountBanner, mountThemeToggle, pill, renderKpi } from '../kit/kit.js';
import { registerThemes } from '../kit/echarts-theme.js';
import * as charts from './charts.js';
import {
  GROUP_LINES,
  MONTH_NAMES,
  SCENARIOS,
  contextOf,
  createModel,
  departmentsView,
  kpiView,
  lineValue,
  lineVariance,
  linesView,
  signedPct,
  statementView,
  trendView,
  waterfallView,
} from './pnl.js';

const REPO = 'https://github.com/HARISPAARTAN/financial-reporting-dashboard';
const TABS = ['pnl', 'variance', 'trend'];
const YEARS = [2023, 2024, 2025];
const STATUS = { 1: ['Fav.', 'ok'], [-1]: ['Unfav.', 'warn'], 0: ['On plan', 'muted'] };
const store = createStore('financial-reporting-dashboard');
const bus = createFilterBus(); // the department picked on the variance bars (not stored)
const $ = (id) => document.getElementById(id);
const motionQuery = typeof matchMedia === 'function' ? matchMedia('(prefers-reduced-motion: reduce)') : null;
const motion = () => !(motionQuery && motionQuery.matches);

let model;
let state;
let host;

const defaultState = () => ({ year: 2025, from: 1, to: 12, ccs: [], scenario: 'Actual', tab: 'pnl', expanded: [], line: 'EBITDA' });

function colours() {
  const css = getComputedStyle(document.documentElement);
  const token = (name) => css.getPropertyValue(`--${name}`).trim();
  return {
    text: token('text'),
    muted: token('muted'),
    border: token('border'),
    accent: token('accent'),
    ok: token('ok'),
    warn: token('warn'),
    chart: [1, 2, 3, 4, 5, 6, 7, 8].map((n) => token(`chart-${n}`)),
  };
}

// ---------------------------------------------------------------- state

function normalise(raw) {
  const d = defaultState();
  const s = raw && typeof raw === 'object' ? raw : {};
  const codes = model.costCentres.map((c) => c.code);
  const month = (v, fallback) => (Number.isInteger(v) && v >= 1 && v <= 12 ? v : fallback);
  let from = month(s.from, d.from);
  let to = month(s.to, d.to);
  if (from > to) [from, to] = [to, from];
  return {
    year: YEARS.includes(s.year) ? s.year : d.year,
    from,
    to,
    ccs: Array.isArray(s.ccs) ? codes.filter((c) => s.ccs.includes(c)) : d.ccs,
    scenario: SCENARIOS.includes(s.scenario) ? s.scenario : d.scenario,
    tab: TABS.includes(s.tab) ? s.tab : d.tab,
    expanded: Array.isArray(s.expanded) ? [...new Set(s.expanded.filter((k) => typeof k === 'string'))] : d.expanded,
    line: model.lines.has(s.line) ? s.line : d.line,
  };
}

function update(changes) {
  const next = { ...state, ...changes };
  if ('from' in changes && next.from > next.to) next.to = next.from;
  if ('to' in changes && next.to < next.from) next.from = next.to;
  state = normalise(next);
  store.save(state);
  render();
}

function tabFromHash() {
  const name = location.hash.replace('#', '');
  return TABS.includes(name) ? name : null;
}

// ---------------------------------------------------------------- filter bar

function closeMenus() {
  for (const menu of document.querySelectorAll('details.menu')) menu.open = false;
}

function checkbox(value, text, onChange) {
  const label = document.createElement('label');
  const input = document.createElement('input');
  input.type = 'checkbox';
  input.value = value;
  input.addEventListener('change', onChange);
  label.append(input, document.createTextNode(text));
  return label;
}

function buildFilters() {
  $('year').replaceChildren(...YEARS.map((y) => new Option(String(y), String(y))));
  $('year').addEventListener('change', (e) => update({ year: Number(e.target.value) }));
  for (const id of ['month-from', 'month-to']) {
    $(id).replaceChildren(...MONTH_NAMES.map((name, i) => new Option(name, String(i + 1))));
  }
  $('month-from').addEventListener('change', (e) => update({ from: Number(e.target.value) }));
  $('month-to').addEventListener('change', (e) => update({ to: Number(e.target.value) }));
  const list = $('department-list');
  const all = checkbox('all', 'All departments', (e) => update({ ccs: e.target.checked ? [] : state.ccs }));
  all.classList.add('menu__all');
  list.replaceChildren(
    all,
    ...model.costCentres.map((c) =>
      checkbox(c.code, c.name, () => {
        const chosen = [...list.querySelectorAll('input:checked')].map((i) => i.value).filter((v) => v !== 'all');
        update({ ccs: chosen.length === model.costCentres.length ? [] : chosen });
      }),
    ),
  );
  $('scenario').replaceChildren(
    ...SCENARIOS.map((name) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = name;
      button.dataset.scenario = name;
      button.addEventListener('click', () => update({ scenario: name }));
      return button;
    }),
  );
  $('line').replaceChildren(...[...model.lines.values()].map((l) => new Option(l.line, l.key)));
  $('line').addEventListener('change', (e) => update({ line: e.target.value }));
  $('reset').addEventListener('click', () => {
    closeMenus();
    bus.clear();
    store.clear();
    state = { ...defaultState(), tab: state.tab };
    render();
  });
  document.addEventListener('click', (e) => {
    for (const menu of document.querySelectorAll('details.menu[open]')) if (!menu.contains(e.target)) menu.open = false;
  });
  document.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape') return;
    const menu = document.querySelector('details.menu[open]');
    closeMenus();
    if (menu) menu.querySelector('summary').focus();
  });
}

function departmentLabel() {
  if (!state.ccs.length) return 'All departments';
  const names = model.costCentres.filter((c) => state.ccs.includes(c.code)).map((c) => c.name);
  return names.length <= 2 ? names.join(', ') : `${names.length} departments`;
}

function syncFilters() {
  $('year').value = String(state.year);
  $('month-from').value = String(state.from);
  $('month-to').value = String(state.to);
  const list = $('department-list');
  for (const input of list.querySelectorAll('input')) {
    input.checked = input.value === 'all' ? !state.ccs.length : state.ccs.includes(input.value);
  }
  $('department-label').textContent = departmentLabel();
  for (const button of $('scenario').children) {
    button.setAttribute('aria-pressed', String(button.dataset.scenario === state.scenario));
  }
  const pnl = state.tab === 'pnl';
  $('scenario').hidden = !pnl;
  $('scenario-note').hidden = pnl;
  $('line').value = state.line;
}

// ---------------------------------------------------------------- P&L statement

function tiles(el, list) {
  el.replaceChildren(
    ...list.map((data) => {
      const box = document.createElement('div');
      renderKpi(box, data);
      return box.firstElementChild;
    }),
  );
}

const lineKey = (row) => (row.subgroup === null ? row.line : `${row.line}|${row.subgroup}`);

function rowLabel(row) {
  if (row.account !== null) return model.accounts.find((a) => a.account === row.account).label;
  return row.subgroup ?? model.lines.get(row.line).line;
}

function visibleRows(rows) {
  const open = new Set(state.expanded);
  return rows.filter((row) => {
    if (row.subgroup === null) return true;
    if (row.account === null) return open.has(row.line);
    return open.has(row.line) && open.has(lineKey(row));
  });
}

function parentKeys(rows) {
  const keys = new Set();
  for (const row of rows) {
    if (row.subgroup !== null) keys.add(row.line);
    if (row.account !== null) keys.add(lineKey(row));
  }
  return keys;
}

function toggleRow(key) {
  const open = new Set(state.expanded);
  if (open.has(key)) open.delete(key);
  else open.add(key);
  update({ expanded: [...open] });
  // the render replaced the table body, so the keyboard focus goes back to the toggle of the same row
  for (const button of document.querySelectorAll('#pnl-table .rowtoggle')) {
    if (button.dataset.key === key) button.focus();
  }
}

function renderStatement() {
  const rows = statementView(model, state);
  const parents = parentKeys(rows);
  const months = [];
  for (let m = state.from; m <= state.to; m += 1) months.push(m);
  const head = $('pnl-table').tHead.rows[0];
  const th = (text, cls) => {
    const cell = document.createElement('th');
    cell.scope = 'col';
    cell.textContent = text;
    if (cls) cell.className = cls;
    return cell;
  };
  head.replaceChildren(th('Line'), ...months.map((m) => th(MONTH_NAMES[m - 1], 'pf-num m')), th('YTD', 'pf-num'), th('Full year', 'pf-num'));
  const body = $('pnl-table').tBodies[0];
  body.replaceChildren(
    ...visibleRows(rows).map((row) => {
      const tr = document.createElement('tr');
      const level = row.account !== null ? 2 : row.subgroup !== null ? 1 : 0;
      const type = model.lines.get(row.line).type;
      tr.dataset.level = String(level);
      tr.dataset.line = row.line;
      if (level === 0 && type !== 'Group') tr.className = 'is-sub';
      const label = document.createElement('th');
      label.scope = 'row';
      label.className = `lvl${level}`;
      const key = lineKey(row);
      if (level < 2 && parents.has(key)) {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'rowtoggle';
        button.dataset.key = key;
        button.setAttribute('aria-expanded', String(state.expanded.includes(key)));
        button.textContent = rowLabel(row);
        button.addEventListener('click', () => toggleRow(key));
        label.append(button);
      } else {
        label.textContent = rowLabel(row);
      }
      const values = [...months.map((m) => [row.cells[m - 1], 'pf-num m']), [row.cells[12], 'pf-num'], [row.cells[13], 'pf-num']];
      tr.append(
        label,
        ...values.map(([v, cls]) => {
          const td = document.createElement('td');
          td.className = cls;
          td.textContent = v === null ? '' : lineValue(model, row.line, v);
          return td;
        }),
      );
      return tr;
    }),
  );
  return parents;
}

function renderPnl() {
  tiles(
    $('pnl-tiles'),
    kpiView(model, state).map((t) => ({
      label: t.label,
      value: t.value,
      delta: { kind: t.kind, text: t.delta },
      caption: 'actual vs budget, closed months',
    })),
  );
  const parents = renderStatement();
  $('expand-all').onclick = () => update({ expanded: [...parents] });
  $('collapse-all').onclick = () => update({ expanded: [] });
}

// ---------------------------------------------------------------- variance

function departmentRows() {
  const impacts = departmentsView(model, state);
  return model.costCentres
    .filter((c) => c.code in impacts)
    .map((c) => ({
      code: c.code,
      name: c.name,
      impact: impacts[c.code],
      flag: model.favourable(contextOf({ ...state, ccs: [c.code] }, { line: 'EBITDA' })),
    }));
}

function renderVariance(c) {
  const selected = bus.get('department');
  const rows = departmentRows();
  const narrow = $('chart-departments').clientWidth < 480;
  host.draw($('chart-departments'), charts.departmentBars(rows, c, { selected, motion: motion(), narrow }), (p) => {
    const code = rows[p.dataIndex]?.code;
    if (code) bus.toggle('department', code);
  });
  const scoped = selected ? { ...state, ccs: [selected] } : state;
  const where = selected ? model.costCentres.find((cc) => cc.code === selected).name : departmentLabel().toLowerCase();
  $('waterfall-sub').textContent = where;
  $('variance-sub').textContent = `${where} · EUR thousand`;
  const groups = GROUP_LINES.map((key) => ({ key, name: model.lines.get(key).line }));
  const steps = charts.waterfallSteps(waterfallView(model, scoped), groups);
  host.draw($('chart-waterfall'), charts.waterfall(steps, c, { motion: motion(), narrow }));
  const lines = linesView(model, scoped);
  const cell = (text, cls = 'pf-num') => {
    const td = document.createElement('td');
    td.className = cls;
    if (typeof text === 'string') td.textContent = text;
    else td.append(text);
    return td;
  };
  $('variance-table').tBodies[0].replaceChildren(
    ...[...model.lines.values()].map((line) => {
      const v = lines[line.key];
      const tr = document.createElement('tr');
      if (line.type !== 'Group') tr.className = 'is-sub';
      const label = document.createElement('th');
      label.scope = 'row';
      label.textContent = line.line;
      const status = STATUS[v.favourable];
      tr.append(
        label,
        cell(v.actual === null ? '' : lineValue(model, line.key, v.actual)),
        cell(v.budgetClosed === null ? '' : lineValue(model, line.key, v.budgetClosed)),
        cell(v.variance === null ? '' : lineVariance(model, line.key, v.variance), `pf-num fav${v.favourable ?? ''}`),
        cell(v.variancePct === null ? '' : signedPct(v.variancePct), `pf-num fav${v.favourable ?? ''}`),
        cell(status ? pill(status[0], status[1]) : '', ''),
      );
      return tr;
    }),
  );
}

// ---------------------------------------------------------------- trend

function renderTrend(c) {
  const ratio = model.lines.get(state.line).type === 'Ratio';
  host.draw($('chart-trend'), charts.trend(trendView(model, state), { ratio }, c, motion()));
}

const RENDER = { pnl: renderPnl, variance: renderVariance, trend: renderTrend };

function render() {
  syncFilters();
  RENDER[state.tab](colours());
}

// ---------------------------------------------------------------- start

/** "2025-09" as "Sep 2025". */
const monthLabel = (yearMonth) => {
  const [year, month] = yearMonth.split('-').map(Number);
  return `${MONTH_NAMES[month - 1]} ${year}`;
};

/** The text of the "Data as of" pill: the last actual month and the last forecast month, both from `meta`. */
function dataAsOf(meta) {
  const [year, month] = meta.firstMonth.split('-').map(Number);
  const end = month - 1 + meta.months - 1;
  const last = `${year + Math.floor(end / 12)}-${(end % 12) + 1}`;
  return `Actuals through ${monthLabel(meta.lastActual)} · forecast through ${monthLabel(last)}`;
}

async function start() {
  mountBanner({ repoUrl: REPO });
  mountThemeToggle($('theme-toggle'));
  const app = $('app');
  let asOf;
  try {
    if (!globalThis.echarts) throw new Error('the chart library did not load');
    const response = await fetch('assets/data/kaldora.json');
    if (!response.ok) throw new Error(`kaldora.json answered ${response.status}`);
    const data = await response.json();
    model = createModel(data);
    asOf = dataAsOf(data.meta);
  } catch (error) {
    $('loading').className = 'app-error';
    $('loading').textContent = `The data could not be loaded (${error.message}). Reload the page to try again.`;
    app.dataset.state = 'error';
    return;
  }
  $('loading').remove();
  $('data-as-of').textContent = asOf;
  const themes = registerThemes(globalThis.echarts);
  host = charts.createChartHost(globalThis.echarts, themes, globalThis.pfTheme?.get() ?? 'dark');
  document.addEventListener('pf:theme', (e) => {
    host.setMode(e.detail.theme);
    render();
  });
  bus.subscribe(() => {
    if (state.tab === 'variance') render();
  });
  state = normalise(store.load());
  state.tab = tabFromHash() ?? state.tab;
  buildFilters();
  $('show-months').addEventListener('click', () => {
    const on = !$('pnl-wrap').classList.contains('show-months');
    $('pnl-wrap').classList.toggle('show-months', on);
    $('show-months').setAttribute('aria-pressed', String(on));
  });
  $('forget').addEventListener('click', () => {
    store.clear();
    state = { ...defaultState(), tab: state.tab };
    render();
  });
  const tabs = initTabs($('tabs'), {
    onChange: (id) => {
      const tab = id.replace('tab-', '');
      if (tab === state.tab) return;
      history.replaceState(null, '', `#${tab}`);
      bus.clear();
      update({ tab });
    },
  });
  window.addEventListener('hashchange', () => {
    const tab = tabFromHash();
    if (tab && tab !== state.tab) tabs.select(`tab-${tab}`);
  });
  tabs.select(`tab-${state.tab}`);
  if (!location.hash) history.replaceState(null, '', `#${state.tab}`);
  render();
  app.dataset.state = 'ready';
}

start();
