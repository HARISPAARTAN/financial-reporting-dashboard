// Screenshots of the replica (umbrella section 12): the three tabs at 1440 x 900 and 390 x 844 in the dark and the
// light theme, plus the views of docs/screenshots/SHOTLIST.md. The run fails on any request that leaves the served
// address, on a console error or page error, and on horizontal scrolling of the page. With URL=<address of the
// published page> it photographs that page instead of the local copy.
// Usage (from the repository root, Node 22):
//   PLAYWRIGHT_FROM=<package.json of a folder that has playwright installed> OUT=<folder outside the repository> \
//     node tools/checks/shots.mjs
// It also writes thumb-1440.jpg (the P&L statement at 1440 x 900, dark) for the portfolio hub; THUMB_QUALITY sets
// the JPEG quality (default 80).
import fs from 'node:fs';
import path from 'node:path';

import { clickBar, load, open, overflow, playwright, serve } from './browser.mjs';

const REPO = path.resolve('.');
const OUT = process.env.OUT ? path.resolve(process.env.OUT) : null;
if (!OUT) {
  console.error('shots: set OUT (a folder outside the repository)');
  process.exit(2);
}
if (OUT === REPO || OUT.startsWith(REPO + path.sep)) {
  console.error('shots: OUT must lie outside the repository');
  process.exit(2);
}
fs.mkdirSync(OUT, { recursive: true });
const { chromium } = playwright('shots');
const { base, close } = await serve();

const TABS = ['pnl', 'variance', 'trend'];
const SIZES = [
  [1440, 900],
  [390, 844],
];
const problems = [];
let shots = 0;

async function shot(page, where, name, fullPage = true) {
  const wide = await overflow(page);
  if (wide > 1) problems.push(`${where}: ${name} scrolls sideways by ${wide} px`);
  await page.screenshot({ path: path.join(OUT, `${name}.png`), fullPage });
  shots += 1;
}

async function interact(view, steps) {
  try {
    await steps(view.page);
  } catch (error) {
    problems.push(`${view.where}: interaction failed: ${error.message.split('\n')[0]}`);
  }
  await view.context.close();
}

const browser = await chromium.launch({ channel: 'chrome', headless: true });
try {
  for (const theme of ['dark', 'light']) {
    for (const size of SIZES) {
      const { context, page, where } = await open(browser, base, theme, size, problems);
      for (const tab of TABS) {
        await load(page, base, tab);
        await shot(page, where, `${theme}-${size[0]}-${tab}`);
      }
      await context.close();
    }
  }
  const wide = await open(browser, base, 'dark', SIZES[0], problems);
  await interact(wide, async (page) => {
    await load(page, base, 'pnl');
    await shot(page, wide.where, '11-replica-1440', false);
    await page.screenshot({ path: path.join(OUT, 'thumb-1440.jpg'), type: 'jpeg', quality: Number(process.env.THUMB_QUALITY ?? 80) });
    await page.click('#pnl-table .rowtoggle >> text=Revenue');
    await page.waitForTimeout(250);
    await shot(page, wide.where, 'dark-1440-pnl-revenue-expanded');
    await load(page, base, 'variance');
    await clickBar(page, '#chart-departments', 2);
    await shot(page, wide.where, 'dark-1440-variance-security-services');
  });
  const narrow = await open(browser, base, 'dark', SIZES[1], problems);
  await interact(narrow, async (page) => {
    await load(page, base, 'pnl');
    await shot(page, narrow.where, '12-replica-390', false);
    await page.click('#show-months');
    await page.waitForTimeout(250);
    await shot(page, narrow.where, 'dark-390-pnl-months');
  });
} finally {
  await browser.close();
  close();
}

for (const problem of problems) console.log(`FAIL ${problem}`);
console.log(`shots: ${shots} screenshots of ${process.env.URL ?? 'web/'} in ${OUT}, ${problems.length} problems`);
process.exit(problems.length ? 1 : 0);
