// node --test tests/js: web/assets/pnl.js recomputes the headline states S1 to S4 of kaldora.json from its facts.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

import {
  createModel,
  departmentsView,
  kEur,
  kpiView,
  linesView,
  period,
  pp,
  signedK,
  signedPct,
  statementView,
  trendView,
  waterfallView,
  ytd,
} from '../../web/assets/pnl.js';

const data = JSON.parse(readFileSync(new URL('../../web/assets/data/kaldora.json', import.meta.url), 'utf8'));
const model = createModel(data);
const { S1, S2, S3, S4 } = data.headline;
const NBSP = String.fromCharCode(160); // the kit puts a no-break space before % and pp

function close(actual, expected, where) {
  if (expected === null || Number.isInteger(expected)) {
    assert.equal(actual, expected, where);
  } else {
    assert.ok(actual !== null && Math.abs(actual - expected) <= 1e-9, `${where}: ${actual} vs ${expected}`);
  }
}

function sameObject(actual, expected, where) {
  assert.deepEqual(Object.keys(actual), Object.keys(expected), where);
  for (const [key, value] of Object.entries(expected)) {
    if (value !== null && typeof value === 'object') sameObject(actual[key], value, `${where}.${key}`);
    else close(actual[key], value, `${where}.${key}`);
  }
}

test('periods and year to date', () => {
  assert.deepEqual(period(2025, 4, 6), [27, 28, 29]);
  assert.deepEqual(ytd([28, 29]), [24, 25, 26, 27, 28, 29]);
  assert.deepEqual(ytd([]), []);
  assert.equal(model.lastActual, 32);
});

test('S1: the ten lines of 2025', () => sameObject(linesView(model, S1.state), S1.lines, 'S1.lines'));

test('S1: waterfall steps and the six department impacts', () => {
  sameObject(waterfallView(model, S1.state), S1.waterfall, 'S1.waterfall');
  sameObject(departmentsView(model, S1.state), S1.departments, 'S1.departments');
});

test('S2: actual and budget of 2024', () => {
  const view = linesView(model, S2.state);
  for (const [key, line] of Object.entries(S2.lines)) {
    close(view[key].actual, line.actual, `S2.${key}.actual`);
    close(view[key].budget, line.budget, `S2.${key}.budget`);
  }
});

test('S3: every P&L matrix cell, scenario Forecast, April to June 2025, CC10 and CC20', () => {
  const rows = statementView(model, S3.state);
  assert.equal(rows.length, S3.rows.length);
  rows.forEach((row, i) => {
    const want = S3.rows[i];
    assert.deepEqual([row.line, row.subgroup, row.account], [want.line, want.subgroup, want.account], `row ${i}`);
    want.cells.forEach((v, c) => close(row.cells[c], v, `row ${i} column ${c + 1}`));
  });
});

test('S4: EBITDA trend over 36 months', () => {
  const view = trendView(model, S4.state);
  for (const name of ['actual', 'budget', 'forecast']) S4[name].forEach((v, t) => close(view[name][t], v, `S4.${name}[${t}]`));
});

test('formats follow the report format strings', () => {
  assert.equal(kEur(4504142983), '45,041');
  assert.equal(kEur(-123456789), '(1,235)');
  assert.equal(kEur(0), '0');
  assert.equal(kEur(null), '–');
  assert.equal(signedK(-29046347), '−290');
  assert.equal(signedK(1539151), '+15');
  assert.equal(signedPct(-0.0106), `−1.1${NBSP}%`);
  assert.equal(signedPct(0.25), `+25.0${NBSP}%`);
  assert.equal(pp(-0.637), `−0.6${NBSP}pp`);
  assert.equal(pp(0), `0.0${NBSP}pp`);
});

test('KPI tiles: values, deltas against the closed-month budget and their kind', () => {
  const tiles = kpiView(model, S1.state);
  assert.deepEqual(
    tiles.map((t) => t.key),
    ['REV', 'GPM', 'EBITDA', 'EBITDAM', 'EBIT'],
  );
  const rev = tiles[0];
  assert.equal(rev.value, kEur(S1.lines.REV.actual));
  assert.equal(rev.delta, `${signedPct(S1.lines.REV.variancePct)} vs budget`);
  assert.equal(rev.kind, S1.lines.REV.favourable === 1 ? 'up' : S1.lines.REV.favourable === -1 ? 'down' : 'neutral');
  assert.equal(tiles[1].delta, `${pp(S1.lines.GPM.variance)} vs budget`);
});

test('engine edge cases: blank lines, subtotal children, no line in context', () => {
  const months = period(2025, 1, 9);
  assert.equal(model.actual({ months, ccs: ['CC80'], line: 'REV', subgroup: null, account: null }), null);
  assert.equal(model.variancePct({ months, ccs: ['CC80'], line: 'GPM', subgroup: null, account: null }), null);
  assert.equal(model.actual({ months, ccs: null, line: 'GP', subgroup: 'Direct personnel', account: null }), null);
  const ebit = model.actual({ months, ccs: null, line: 'EBIT', subgroup: null, account: null });
  assert.equal(model.actual({ months, ccs: null, line: null, subgroup: null, account: null }), ebit);
});
