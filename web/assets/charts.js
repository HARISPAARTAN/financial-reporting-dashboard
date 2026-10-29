// ECharts options of the replica: pure functions from the views of pnl.js and the colour tokens to option objects
// (no DOM access), plus a small host that draws them with the kit's chart themes. Amounts arrive in cents of
// profit contribution and are shown in EUR thousand, as in the report; ratios arrive as fractions.
import { FIRST_YEAR, MONTH_NAMES, kEur, pct, signedK } from './pnl.js';

const MONO = '"JetBrains Mono", Consolas, monospace';
const thousand = (cents) => (cents === null || cents === undefined ? null : cents / 100000);
const escape = (text) => String(text).replace(/[&<>"']/g, (ch) => `&#${ch.charCodeAt(0)};`);
const grouped = new Intl.NumberFormat('en-GB', { maximumFractionDigits: 0 });
/** An axis label in EUR thousand: the value arrives in thousands already. */
export const axisK = (value) => (value < 0 ? `−${grouped.format(-value)}` : grouped.format(value));

/** "Jan 2023" to "Dec 2025": the 36 month labels of the trend. */
export function monthLabels(count = 36) {
  return Array.from({ length: count }, (_, t) => `${MONTH_NAMES[t % 12]} ${FIRST_YEAR + Math.floor(t / 12)}`);
}

/** The colour of a favourable flag as the report's [Favourable colour]: 1 ok, -1 warn, 0 muted, blank none. */
export function favourableColour(flag, c) {
  if (flag === 1) return c.ok;
  if (flag === -1) return c.warn;
  if (flag === 0) return c.muted;
  return c.border;
}

function base(c, motion) {
  return {
    animation: motion,
    grid: { left: 8, right: 16, top: 16, bottom: 8, containLabel: true },
    textStyle: { fontFamily: 'Inter, system-ui, sans-serif' },
    color: c.chart,
  };
}

/**
 * EBITDA profit impact per department as horizontal bars, coloured by favourable. rows: [{code, name, impact, flag}];
 * `selected` (a cost-centre code) dims the other bars while a bar filters the waterfall and the table; `narrow`
 * (a chart under 480 px) keeps three value-axis labels.
 */
export function departmentBars(rows, c, { selected = null, motion = true, narrow = false } = {}) {
  return {
    ...base(c, motion),
    grid: { left: 8, right: 64, top: 8, bottom: 8, containLabel: true },
    tooltip: {
      trigger: 'item',
      confine: true,
      formatter: (p) => `${escape(rows[p.dataIndex].name)}<br>EBITDA profit impact: <b>${signedK(rows[p.dataIndex].impact)}</b> EUR k`,
    },
    xAxis: { type: 'value', splitNumber: narrow ? 3 : 5, axisLabel: { formatter: axisK, hideOverlap: true } },
    yAxis: { type: 'category', inverse: true, data: rows.map((r) => r.name) },
    series: [
      {
        name: 'EBITDA profit impact',
        type: 'bar',
        barMaxWidth: 28,
        cursor: 'pointer',
        data: rows.map((r) => ({
          value: thousand(r.impact),
          code: r.code,
          itemStyle: {
            color: favourableColour(r.flag, c),
            opacity: selected === null || selected === r.code ? 1 : 0.35,
            borderRadius: r.impact < 0 ? [4, 0, 0, 4] : [0, 4, 4, 0],
          },
        })),
        label: { show: true, position: 'right', color: c.text, fontFamily: MONO, formatter: (p) => signedK(rows[p.dataIndex].impact) },
      },
    ],
  };
}

/**
 * The waterfall steps from budget EBIT to actual EBIT: one step per account group (its profit impact, in the order
 * given) and the EBIT variance as the total column. Each step runs from `start` to `end` in cents.
 */
export function waterfallSteps(view, groups) {
  const steps = [];
  let level = 0;
  for (const { key, name } of groups) {
    const value = view[key] ?? 0;
    steps.push({ key, name, value, start: level, end: level + value, kind: value < 0 ? 'decrease' : 'increase' });
    level += value;
  }
  const total = view.total ?? 0;
  steps.push({ key: 'total', name: 'EBIT variance', value: total, start: 0, end: total, kind: 'total' });
  return steps;
}

/**
 * A floating column from `start` to `end` as three stacked parts (ECharts stacks positive and negative values
 * separately): a transparent base, the visible part on the same side and, for a column that crosses zero, the
 * visible part on the other side.
 */
export function stackParts(start, end) {
  const low = Math.min(start, end);
  const high = Math.max(start, end);
  if (low >= 0) return { base: low, near: high - low, far: 0 };
  if (high <= 0) return { base: high, near: low - high, far: 0 };
  return { base: 0, near: high, far: low };
}

/** `narrow` (a chart under 480 px) turns the category labels so that the five names keep apart. */
export function waterfall(steps, c, { motion = true, narrow = false } = {}) {
  const colour = { increase: c.ok, decrease: c.warn, total: c.accent };
  const parts = steps.map((s) => stackParts(thousand(s.start), thousand(s.end)));
  const visible = (key) =>
    steps.map((s, i) => ({ value: parts[i][key] || null, itemStyle: { color: colour[s.kind] } }));
  return {
    ...base(c, motion),
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      confine: true,
      formatter: (params) => {
        const step = steps[params[0].dataIndex];
        return `${escape(step.name)}<br>Profit impact: <b>${signedK(step.value)}</b> EUR k`;
      },
    },
    grid: { left: 8, right: 16, top: 16, bottom: 4, containLabel: true },
    xAxis: {
      type: 'category',
      data: steps.map((s) => s.name),
      axisLabel: narrow ? { interval: 0, rotate: 35, fontSize: 11 } : { interval: 0, width: 84, overflow: 'break', lineHeight: 14 },
    },
    yAxis: { type: 'value', axisLabel: { formatter: axisK, hideOverlap: true } },
    series: [
      { name: 'base', type: 'bar', stack: 'steps', silent: true, itemStyle: { color: 'transparent' }, data: parts.map((p) => p.base) },
      { name: 'Profit impact', type: 'bar', stack: 'steps', barMaxWidth: 48, data: visible('near') },
      { name: 'Profit impact, below zero', type: 'bar', stack: 'steps', barMaxWidth: 48, data: visible('far') },
    ],
  };
}

/** Trend of one line: Actual solid (series colour 1), Budget dashed (muted), Forecast dotted (series colour 4). */
export function trend(view, { ratio = false } = {}, c, motion = true) {
  const scale = ratio ? (v) => v : thousand;
  const show = ratio ? pct : kEur;
  const line = (name, values, colour, type) => ({
    name,
    type: 'line',
    data: values.map(scale),
    connectNulls: false,
    symbol: 'none',
    lineStyle: { width: type === 'solid' ? 2.5 : 2, type, color: colour },
    itemStyle: { color: colour },
  });
  return {
    ...base(c, motion),
    legend: { top: 0, icon: 'roundRect', itemWidth: 14, itemHeight: 4, textStyle: { color: c.muted } },
    grid: { left: 8, right: 16, top: 36, bottom: 8, containLabel: true },
    tooltip: {
      trigger: 'axis',
      confine: true,
      formatter: (params) => {
        const list = Array.isArray(params) ? params : [params];
        const t = list[0].dataIndex;
        const rows = [view.actual, view.budget, view.forecast].map((values, i) => [['Actual', 'Budget', 'Forecast'][i], values[t]]);
        return [escape(list[0].axisValueLabel), ...rows.filter(([, v]) => v !== null).map(([n, v]) => `${n}: <b>${show(v)}</b>`)].join('<br>');
      },
    },
    xAxis: { type: 'category', data: monthLabels(view.actual.length), boundaryGap: false, axisLabel: { hideOverlap: true } },
    yAxis: { type: 'value', scale: ratio, axisLabel: { formatter: ratio ? (v) => pct(v) : axisK, hideOverlap: true } },
    series: [
      line('Actual', view.actual, c.chart[0], 'solid'),
      line('Budget', view.budget, c.muted, 'dashed'),
      line('Forecast', view.forecast, c.chart[3], 'dotted'),
    ],
  };
}

export function createChartHost(echarts, themes, mode) {
  const charts = new Map();
  let current = mode;
  const observer = typeof ResizeObserver === 'function'
    ? new ResizeObserver((entries) => entries.forEach((e) => charts.get(e.target)?.resize()))
    : null;
  return {
    draw(el, option, onClick) {
      let chart = charts.get(el);
      if (!chart) {
        chart = echarts.init(el, themes[current], { renderer: 'svg' });
        charts.set(el, chart);
        observer?.observe(el);
      }
      chart.setOption(option, { notMerge: true });
      chart.off('click');
      if (onClick) chart.on('click', onClick);
      chart.resize();
      return chart;
    },
    setMode(next) {
      if (next === current) return;
      current = next;
      for (const [el, chart] of charts) {
        observer?.unobserve(el);
        chart.dispose();
      }
      charts.clear();
    },
  };
}
