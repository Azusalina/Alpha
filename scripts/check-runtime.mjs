/**
 * Runtime evidence for the startup page: frame timing, isolated pointer
 * disturbance, and the composition across window aspects (spec 12, V03/V10).
 *
 * Needs the dev server running. Set ALPHA_CHROMIUM to use a system browser.
 *
 *   npm run dev
 *   ALPHA_CHROMIUM=/usr/bin/chromium node scripts/check-runtime.mjs
 *
 * The frame timings are only valid for the renderer they were taken on — the
 * script prints which one that is. A software rasteriser result says nothing
 * about the Intel Xe target (spec 9).
 */

import { mkdir, writeFile } from 'node:fs/promises';
import { chromium } from '@playwright/test';

const URL = process.env.ALPHA_URL ?? 'http://127.0.0.1:5173';
const OUT = 'outputs/qa';
const FRAME = { width: 1644, height: 957 };
const executablePath = process.env.ALPHA_CHROMIUM || undefined;

const VIEWPORTS = [
  { w: 1644, h: 957, label: 'reference 1.718' },
  { w: 1920, h: 1080, label: '16:9' },
  { w: 1680, h: 1050, label: '16:10' },
  { w: 1280, h: 800, label: '16:10 small' },
  { w: 1024, h: 900, label: 'near square 1.14' },
];

const waitForHome = async (page) => {
  await page.waitForFunction(() => window.__alpha?.state === 'home', null, { timeout: 25_000 });
};

const main = async () => {
  await mkdir(OUT, { recursive: true });
  const browser = await chromium.launch({ executablePath, args: ['--no-sandbox'] });
  const report = {};

  // --- renderer identity and frame timing ---
  {
    const page = await browser.newPage({ viewport: FRAME, deviceScaleFactor: 1 });
    await page.goto(URL);
    await waitForHome(page);
    await page.waitForTimeout(1500);

    report.renderer = await page.evaluate(() => {
      const gl = document.querySelector('canvas').getContext('webgl2');
      const dbg = gl.getExtension('WEBGL_debug_renderer_info');
      return dbg ? gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER);
    });

    const samples = await page.evaluate(
      () =>
        new Promise((res) => {
          const t = [];
          let last = performance.now();
          const tick = () => {
            const n = performance.now();
            t.push(n - last);
            last = n;
            if (t.length < 180) requestAnimationFrame(tick);
            else res(t.slice(20)); // drop warm-up frames
          };
          requestAnimationFrame(tick);
        }),
    );
    const sorted = [...samples].sort((a, b) => a - b);
    const pct = (q) => +sorted[Math.floor(sorted.length * q)].toFixed(2);
    report.frameTiming = {
      samples: samples.length,
      median_ms: pct(0.5),
      p95_ms: pct(0.95),
      max_ms: +Math.max(...samples).toFixed(2),
      implied_fps: +(1000 / pct(0.5)).toFixed(1),
      note: 'valid only for the renderer named above',
    };
    await page.close();
  }

  // --- V03: pointer disturbance, with the idle clock frozen ---
  {
    const page = await browser.newPage({ viewport: FRAME, deviceScaleFactor: 1 });
    await page.goto(URL);
    await waitForHome(page);
    await page.evaluate(() => window.__alpha.setTimeScale(0));

    const shot = (n) => page.screenshot({ path: `${OUT}/pointer-${n}.png` });
    await page.mouse.move(200, 880);
    await page.waitForTimeout(1200);
    await shot('away');
    await page.mouse.move(1050, 640);
    await page.waitForTimeout(1200);
    await shot('near');
    await page.mouse.move(-5, -5);
    await page.waitForTimeout(1800);
    await shot('recovered');

    report.pointer = await page.evaluate(() => ({
      influenceAfterLeaving: window.__alpha.pointerInfluence,
    }));
    await page.close();
  }

  // --- V10: the composition across window aspects ---
  report.viewports = [];
  for (const v of VIEWPORTS) {
    const page = await browser.newPage({ viewport: { width: v.w, height: v.h }, deviceScaleFactor: 1 });
    await page.goto(URL);
    await waitForHome(page);
    await page.waitForTimeout(500);
    await page.screenshot({ path: `${OUT}/viewport-${v.w}x${v.h}.png` });
    const zone = await page.getByTestId('hotzone-system').boundingBox();
    report.viewports.push({
      label: v.label,
      size: [v.w, v.h],
      hotzoneReachable: Boolean(zone && zone.width > 40 && zone.height > 40),
    });
    await page.close();
  }

  await browser.close();
  await writeFile(`${OUT}/runtime-report.json`, JSON.stringify(report, null, 2) + '\n');
  console.log(JSON.stringify(report, null, 2));
};

main();
