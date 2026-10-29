// Behaviour of the replica in Chrome (spec section 10). In the default state the five KPI tiles show what
// web/assets/pnl.js computes for the headline state S1 of kaldora.json; expanding Revenue shows its three subgroups
// and is remembered; Budget shows the budget full year of Revenue; the Variance tab draws six department bars, and a
// click on the Security Services bar scopes the waterfall to it; Reset clears the stored view; at 390 px the P&L
// table hides the months until "Show months" is pressed and keeps its Full year column inside the table box, and the
// page never scrolls sideways. The run also fails on
// console errors, page errors and requests that leave the served address.
// Usage (from the repository root, Node 22):
//   PLAYWRIGHT_FROM=<package.json of a folder that has playwright installed> node tools/checks/replica.mjs
import fs from 'node:fs';

import { createModel, kpiView } from '../../web/assets/pnl.js';
import { clickBar, load, open, overflow, playwright, serve } from './browser.mjs';

const KEY = 'pf.financial-reporting-dashboard.v1';
const data = JSON.parse(fs.readFileSync('web/assets/data/kaldora.json', 'utf8'));
const expected = kpiView(createModel(data), data.headline.S1.state);
const { chromium } = playwright('replica');
const { base, close } = await serve();
const problems = [];
let checks = 0;
const expect = (ok, message) => {
  checks += 1;
  if (!ok) problems.push(message);
};
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

const browser = await chromium.launch({ channel: 'chrome', headless: true });
try {
  const wide = await open(browser, base, 'dark', [1440, 900], problems);
  const { page } = wide;
  await load(page, base, 'pnl');
  const values = await page.$$eval('#pnl-tiles .pf-kpi__value', (els) => els.map((e) => e.textContent));
  const deltas = await page.$$eval('#pnl-tiles .pf-kpi__delta', (els) => els.map((e) => e.lastChild.textContent));
  expect(same(values, expected.map((t) => t.value)), `KPI values ${values.join(' | ')}`);
  expect(same(deltas, expected.map((t) => t.delta)), `KPI deltas ${deltas.join(' | ')}`);
  await page.click('#pnl-table .rowtoggle >> text=Revenue');
  await page.waitForTimeout(250);
  const subgroups = await page.$$eval('#pnl-table tr[data-level="1"][data-line="REV"]', (rows) => rows.length);
  expect(subgroups === 3, `Revenue shows ${subgroups} subgroups, expected 3`);
  const stored = await page.evaluate((key) => JSON.parse(localStorage.getItem(key) ?? 'null'), KEY);
  expect(same(stored?.expanded, ['REV']), `stored view ${JSON.stringify(stored)}`);
  await page.click('#scenario button[data-scenario="Budget"]');
  await page.waitForTimeout(250);
  const fullYear = await page.$eval('#pnl-table tr[data-level="0"][data-line="REV"] td:last-child', (td) => td.textContent);
  expect(fullYear === '45,678', `Revenue full year under Budget is ${fullYear}, expected 45,678`);
  await load(page, base, 'variance');
  const bars = await page.evaluate(
    () => globalThis.echarts.getInstanceByDom(document.getElementById('chart-departments')).getOption().series[0].data.length,
  );
  expect(bars === 6, `the Variance tab draws ${bars} bars, expected 6`);
  await clickBar(page, '#chart-departments', 2);
  const scope = await page.textContent('#waterfall-sub');
  expect(scope === 'Security Services', `a click on the Security Services bar scopes the waterfall to ${scope}`);
  await page.click('#reset');
  await page.waitForTimeout(250);
  const afterReset = await page.evaluate((key) => localStorage.getItem(key), KEY);
  expect(afterReset === null, `Reset left the stored view ${afterReset}`);
  await wide.context.close();

  const narrow = await open(browser, base, 'dark', [390, 844], problems);
  await load(narrow.page, base, 'pnl');
  const visibleMonths = () =>
    narrow.page.$$eval('#pnl-table thead th.m', (ths) => ths.filter((th) => th.getClientRects().length > 0).length);
  const before = await visibleMonths();
  expect(before === 0, `${before} month columns visible at 390 px before Show months`);
  const fullYearIn = await narrow.page.evaluate(() => {
    const th = [...document.querySelectorAll('#pnl-table thead th')].find((cell) => cell.textContent === 'Full year');
    return th.getBoundingClientRect().right - document.getElementById('pnl-wrap').getBoundingClientRect().right;
  });
  expect(fullYearIn <= 1, `the Full year column ends ${fullYearIn} px beyond the table box at 390 px`);
  await narrow.page.click('#show-months');
  await narrow.page.waitForTimeout(250);
  const after = await visibleMonths();
  expect(after === 12, `${after} month columns visible after Show months, expected 12`);
  const sideways = await overflow(narrow.page);
  expect(sideways <= 1, `the page scrolls sideways by ${sideways} px at 390 px`);
  await narrow.context.close();
} finally {
  await browser.close();
  close();
}

for (const problem of problems) console.log(`FAIL ${problem}`);
console.log(`replica: ${checks} checks, ${problems.length} problems`);
process.exit(problems.length ? 1 : 0);
