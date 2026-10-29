// Shared by shots.mjs and replica.mjs: Playwright from PLAYWRIGHT_FROM (it is not a dependency of this repository),
// a static server for web/ on 127.0.0.1 (or URL=<address of the published page>), and pages that record every
// console error, page error and request that leaves the served address. Chrome comes from the local installation
// (channel "chrome"); nothing is downloaded.
import { createRequire } from 'node:module';
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';

const ROOT = path.resolve('web');
const TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json',
  '.woff2': 'font/woff2',
  '.txt': 'text/plain; charset=utf-8',
  '.md': 'text/markdown; charset=utf-8',
};

/** Playwright, loaded from the folder that PLAYWRIGHT_FROM names; exits with 2 when it is not set. */
export function playwright(script) {
  const from = process.env.PLAYWRIGHT_FROM;
  if (!from) {
    console.error(`${script}: set PLAYWRIGHT_FROM (the package.json of a folder that has playwright installed)`);
    process.exit(2);
  }
  return createRequire(from)('playwright');
}

/** Serves web/ on a free port of 127.0.0.1 unless URL is set; returns { base, close }. */
export async function serve() {
  const live = process.env.URL ? process.env.URL.replace(/\/+$/, '') : null;
  if (live) return { base: live, close: () => {} };
  const server = http.createServer((req, res) => {
    const route = decodeURIComponent(new URL(req.url, 'http://x').pathname);
    const file = path.join(ROOT, route.endsWith('/') ? `${route}index.html` : route);
    if (!file.startsWith(ROOT) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
      res.writeHead(404);
      res.end('not found');
      return;
    }
    res.writeHead(200, { 'content-type': TYPES[path.extname(file)] ?? 'application/octet-stream' });
    fs.createReadStream(file).pipe(res);
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  return { base: `http://127.0.0.1:${server.address().port}`, close: () => server.close() };
}

/** A new context and page in the given theme and viewport; `problems` collects what must fail the run. */
export async function open(browser, base, theme, [width, height], problems) {
  const context = await browser.newContext({ viewport: { width, height }, deviceScaleFactor: 1, reducedMotion: 'reduce' });
  await context.addInitScript((mode) => {
    try {
      localStorage.setItem('hh-theme', mode);
    } catch {
      // storage blocked: the theme follows the system preference
    }
  }, theme);
  const page = await context.newPage();
  const where = `${theme} ${width}`;
  page.on('console', (msg) => {
    if (msg.type() === 'error') problems.push(`${where}: console error: ${msg.text()}`);
  });
  page.on('pageerror', (err) => problems.push(`${where}: page error: ${err.message}`));
  page.on('request', (req) => {
    const url = req.url();
    if (!url.startsWith(base) && !url.startsWith('data:') && !url.startsWith('blob:')) problems.push(`${where}: external request ${url}`);
  });
  return { context, page, where };
}

/** Opens a tab (a new load or a hash change) and waits until the page has drawn it. */
export async function load(page, base, tab) {
  await page.goto(`${base}/index.html#${tab}`);
  await page.waitForSelector('#app[data-state="ready"]', { timeout: 20000 });
  await page.waitForSelector(`#tab-${tab}[aria-selected="true"]`, { timeout: 5000 });
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(250);
}

/** The sideways overflow of the page in pixels (0 when the page never scrolls sideways). */
export const overflow = (page) => page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);

/** A mouse click in the middle of bar `index` of the first series of the horizontal bar chart in `selector`. */
export async function clickBar(page, selector, index) {
  const point = await page.evaluate(
    ([sel, i]) => {
      const el = document.querySelector(sel);
      const chart = globalThis.echarts.getInstanceByDom(el);
      const value = chart.getOption().series[0].data[i].value;
      const [x, y] = chart.convertToPixel({ seriesIndex: 0 }, [value / 2, i]);
      const box = el.getBoundingClientRect();
      return { x: box.left + x, y: box.top + y };
    },
    [selector, index],
  );
  await page.mouse.click(point.x, point.y);
  await page.waitForTimeout(250);
}
