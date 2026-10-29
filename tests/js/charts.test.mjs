// node --test tests/js: the chart options of web/assets/charts.js (pure functions, no DOM) on the S1 state.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

import { axisK, departmentBars, favourableColour, monthLabels, stackParts, trend, waterfall, waterfallSteps } from '../../web/assets/charts.js';
import { GROUP_LINES, contextOf, createModel, departmentsView, trendView, waterfallView } from '../../web/assets/pnl.js';

const data = JSON.parse(readFileSync(new URL('../../web/assets/data/kaldora.json', import.meta.url), 'utf8'));
const model = createModel(data);
const S1 = data.headline.S1.state;
const C = { ok: '#0f0', warn: '#ff0', muted: '#888', border: '#333', accent: '#fa0', text: '#fff', chart: ['#c80', '#08c'] };
const groups = GROUP_LINES.map((key) => ({ key, name: model.lines.get(key).line }));

test('stackParts covers both sides and a column that crosses zero', () => {
  assert.deepEqual(stackParts(10, 25), { base: 10, near: 15, far: 0 });
  assert.deepEqual(stackParts(25, 10), { base: 10, near: 15, far: 0 });
  assert.deepEqual(stackParts(-10, -25), { base: -10, near: -15, far: 0 });
  assert.deepEqual(stackParts(-10, 5), { base: 0, near: 5, far: -10 });
  assert.deepEqual(stackParts(0, -7), { base: 0, near: -7, far: 0 });
});

test('the waterfall of S1 walks from 0 to the EBIT variance through the four account groups', () => {
  const view = waterfallView(model, S1);
  const steps = waterfallSteps(view, groups);
  assert.deepEqual(steps.map((s) => s.name), ['Revenue', 'Cost of services', 'Operating expenses', 'Depreciation and amortisation', 'EBIT variance']);
  assert.equal(steps[3].end, view.total);
  assert.equal(steps[4].start, 0);
  assert.equal(steps[4].end, data.headline.S1.lines.EBIT.variance);
  for (let i = 1; i < 4; i += 1) assert.equal(steps[i].start, steps[i - 1].end);
  assert.deepEqual(steps.map((s) => s.kind).slice(0, 4), steps.slice(0, 4).map((s) => (s.value < 0 ? 'decrease' : 'increase')));
  const option = waterfall(steps, C, { motion: false });
  assert.equal(option.series.length, 3);
  assert.equal(option.series[0].itemStyle.color, 'transparent');
  assert.equal(waterfall(steps, C, { motion: false, narrow: true }).xAxis.axisLabel.rotate, 35);
  assert.deepEqual(option.series[1].data.map((d) => d.itemStyle.color), steps.map((s) => ({ increase: C.ok, decrease: C.warn, total: C.accent })[s.kind]));
  steps.forEach((s, i) => {
    const total = option.series[0].data[i] + (option.series[1].data[i].value ?? 0) + (option.series[2].data[i].value ?? 0);
    const top = Math.abs(s.start) > Math.abs(s.end) ? s.start : s.end;
    const crosses = Math.min(s.start, s.end) < 0 && Math.max(s.start, s.end) > 0;
    if (!crosses) assert.ok(Math.abs(total - top / 100000) < 1e-9, `${s.name}: ${total}`);
  });
});

test('the department bars of S1: six bars, coloured by favourable, the selection dims the others', () => {
  const impacts = departmentsView(model, S1);
  const rows = model.costCentres.map((cc) => ({
    code: cc.code,
    name: cc.name,
    impact: impacts[cc.code],
    flag: model.favourable(contextOf({ ...S1, ccs: [cc.code] }, { line: 'EBITDA' })),
  }));
  const option = departmentBars(rows, C, { selected: 'CC30', motion: false });
  const bars = option.series[0].data;
  assert.equal(bars.length, 6);
  assert.deepEqual(option.yAxis.data, ['Cleaning Services', 'Technical Maintenance', 'Security Services', 'Catering', 'Administration', 'Sales & Marketing']);
  assert.deepEqual(bars.map((b) => b.itemStyle.opacity), [0.35, 0.35, 1, 0.35, 0.35, 0.35]);
  rows.forEach((r, i) => {
    assert.equal(bars[i].itemStyle.color, favourableColour(r.flag, C));
    assert.equal(bars[i].value, r.impact / 100000);
  });
  assert.deepEqual(rows.map((r) => r.impact), model.costCentres.map((cc) => data.headline.S1.departments[cc.code]));
});

test('the trend draws Actual solid, Budget dashed and Forecast dotted over 36 months', () => {
  const view = trendView(model, { line: 'EBITDA', ccs: [] });
  const option = trend(view, { ratio: false }, C, false);
  assert.deepEqual(option.series.map((s) => [s.name, s.lineStyle.type, s.lineStyle.color]), [
    ['Actual', 'solid', C.chart[0]],
    ['Budget', 'dashed', C.muted],
    ['Forecast', 'dotted', C.accent],
  ]);
  assert.equal(option.xAxis.data.length, 36);
  assert.equal(option.xAxis.data[0], 'Jan 2023');
  assert.equal(option.xAxis.data[35], 'Dec 2025');
  assert.equal(option.series[0].data[35], null); // no actuals after September 2025
  assert.equal(option.series[2].data[0], null); // the forecast holds October to December 2025 only
  assert.equal(option.series[0].data[0], data.headline.S4.actual[0] / 100000);
  const ratio = trend(trendView(model, { line: 'GPM', ccs: [] }), { ratio: true }, C, false);
  assert.ok(ratio.series[0].data[0] > 0.15 && ratio.series[0].data[0] < 0.3);
});

test('labels and colours', () => {
  assert.deepEqual(monthLabels(2), ['Jan 2023', 'Feb 2023']);
  assert.equal(axisK(1234), '1,234');
  assert.equal(axisK(-1234), '−1,234');
  assert.deepEqual([1, -1, 0, null].map((f) => favourableColour(f, C)), [C.ok, C.warn, C.muted, C.border]);
});
