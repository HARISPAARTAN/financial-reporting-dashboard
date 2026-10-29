// WCAG 2.x contrast of the replica's colours in both themes and of the report theme Kaldora Dark (adapted from the
// portfolio's contrast check to read web/kit/tokens.css). Text pairs need 4.5:1, chart and status colours on the card
// surface 3:1. The replica's variance texts and status pills and the report's [Favourable colour] font colours are
// text, so they need 4.5:1, also on the tinted subtotal rows ([Row tint]); color-mix in srgb mixes the encoded channels.
// Usage (from the repository root): node tools/checks/contrast.mjs
import fs from 'node:fs';

const css = fs.readFileSync('web/kit/tokens.css', 'utf8');
const split = css.indexOf(':root[data-theme="light"]');
if (split < 0) throw new Error('web/kit/tokens.css has no :root[data-theme="light"] block');
const vars = (text) =>
  Object.fromEntries([...text.matchAll(/--([\w-]+)\s*:\s*(#[0-9a-fA-F]{6})\b/g)].map((match) => [match[1], match[2]]));
const dark = vars(css.slice(0, split));
const themes = { dark, light: { ...dark, ...vars(css.slice(split)) } };
const styles = fs.readFileSync('web/assets/styles.css', 'utf8');
const pale = /:root\[data-theme="light"\] \{\s*--row-tint: color-mix\(in srgb, var\(--surface-2\) (\d+)%, var\(--surface\)\);/.exec(styles);
if (!pale) throw new Error('web/assets/styles.css has no light --row-tint');
const report = JSON.parse(
  fs.readFileSync('pbip/FinancialReportingDashboard.Report/StaticResources/RegisteredResources/kaldora-dark.json', 'utf8'),
);
const measures = fs.readFileSync('pbip/FinancialReportingDashboard.SemanticModel/definition/tables/_Measures.tmdl', 'utf8');
const hexesOf = (name) => {
  const start = measures.indexOf(`measure '${name}'`);
  if (start < 0) throw new Error(`_Measures.tmdl has no measure '${name}'`);
  const next = measures.indexOf('\n\tmeasure ', start + 1);
  return [...measures.slice(start, next < 0 ? undefined : next).matchAll(/"(#[0-9A-Fa-f]{6})"/g)].map((m) => m[1]);
};
const favourable = hexesOf('Favourable colour');
const [tint] = hexesOf('Row tint');

const channels = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
const toHex = (rgb) => `#${rgb.map((v) => Math.round(v).toString(16).padStart(2, '0')).join('').toUpperCase()}`;
const mix = (a, b, share) => toHex(channels(a).map((v, i) => (v * share + channels(b)[i] * (100 - share)) / 100));
function luminance(hex) {
  const [r, g, b] = channels(hex)
    .map((v) => v / 255)
    .map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}
function ratio(a, b) {
  const [high, low] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (high + 0.05) / (low + 0.05);
}

const TEXT = [
  ['text', 'bg'],
  ['text', 'surface'],
  ['text', 'surface-2'],
  ['muted', 'bg'],
  ['muted', 'surface'],
  ['muted', 'surface-2'],
  ['accent', 'bg'],
  ['accent', 'surface'],
  ['accent-fg', 'accent'],
  ['ok', 'surface'],
  ['warn', 'surface'],
  ['danger', 'surface'],
];
const ON_TINT = ['text', 'muted', 'ok', 'warn'];
const DATA = ['chart-1', 'chart-2', 'chart-3', 'chart-4', 'chart-5', 'chart-6', 'chart-7', 'chart-8', 'ok', 'warn', 'muted', 'accent'];

let checked = 0;
let failed = 0;
function check(mode, label, fg, bg, min) {
  checked += 1;
  const value = fg && bg ? ratio(fg, bg) : 0;
  const pass = value >= min;
  if (!pass) failed += 1;
  console.log(`${pass ? 'ok    ' : 'FAIL  '} ${mode.padEnd(6)} ${label.padEnd(40)} ${fg} / ${bg}  ${value.toFixed(2)}:1 (min ${min})`);
}

for (const [mode, t] of Object.entries(themes)) {
  for (const [fg, bg] of TEXT) check(mode, `--${fg} on --${bg}`, t[fg], t[bg], 4.5);
  const rowTint = mode === 'light' ? mix(t['surface-2'], t.surface, Number(pale[1])) : t['surface-2'];
  for (const fg of ON_TINT) check(mode, `--${fg} on --row-tint`, t[fg], rowTint, 4.5);
  for (const name of DATA) check(mode, `--${name} on --surface (data)`, t[name], t.surface, 3);
  for (const kind of ['ok', 'warn', 'muted']) {
    // .pf-pill: colour mix(pill 75 %, text) on mix(pill 18 %, surface)
    check(mode, `${kind} status pill`, mix(t[kind], t.text, 75), mix(t[kind], t.surface, 18), 4.5);
  }
}
const background = report.background;
for (const [label, fg] of [
  ['foreground', report.foreground],
  ['secondLevelElements', report.secondLevelElements],
  ...favourable.map((hex, i) => [`[Favourable colour] #${i + 1}`, hex]),
]) {
  check('report', `${label} on background`, fg, background, 4.5);
  check('report', `${label} on [Row tint]`, fg, tint, 4.5);
}
for (const [i, hex] of report.dataColors.entries()) check('report', `dataColors[${i}] on background`, hex, background, 3);
console.log(failed ? `contrast: ${failed} of ${checked} pairs below the minimum` : `contrast: ${checked} pairs ok`);
process.exit(failed ? 1 : 0);
