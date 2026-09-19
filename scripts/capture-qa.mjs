/**
 * Capture the visual evidence the spec asks for (section 12, 视觉证据).
 *
 * Drives a real browser at the reference frame size and saves:
 *   - startup key frames at 0 / 25 / 50 / 75 / 100 %
 *   - the stable home screen
 *   - a pointer-disturbance pair on the particle hand
 *
 * Frame positioning uses the dev inspector, which the spec permits for
 * screenshots. Interaction acceptance still goes through real pointer events —
 * see tests/startup.spec.ts.
 *
 * Usage: npm run dev, then `node scripts/capture-qa.mjs`.
 */

import { mkdir } from 'node:fs/promises';
import { chromium } from '@playwright/test';

const URL = process.env.ALPHA_URL ?? 'http://127.0.0.1:5173';
const OUT = 'outputs/qa';
const FRAME = { width: 1644, height: 957 };

const shot = (page, name) => page.screenshot({ path: `${OUT}/${name}.png` });

const state = (page) => page.evaluate(() => window.__alpha.state);

async function waitForHome(page) {
  const deadline = Date.now() + 20_000;
  while (Date.now() < deadline) {
    if ((await state(page)) === 'home') return;
    await page.waitForTimeout(100);
  }
  throw new Error('scene never reached home');
}

const main = async () => {
  await mkdir(OUT, { recursive: true });
  const browser = await chromium.launch({
    headless: false,
    executablePath: process.env.ALPHA_CHROMIUM || undefined,
  });
  const page = await browser.newPage({ viewport: FRAME, deviceScaleFactor: 1 });

  const errors = [];
  page.on('console', (m) => m.type() === 'error' && errors.push(m.text()));
  page.on('pageerror', (e) => errors.push(String(e)));

  await page.goto(URL);
  await waitForHome(page);

  // startup key frames, scrubbed rather than raced against real time
  for (const p of [0, 0.25, 0.5, 0.75, 1]) {
    await page.evaluate((v) => window.__alpha.scrubStartup(v), p);
    await page.waitForTimeout(220);
    await shot(page, `startup-${String(Math.round(p * 100)).padStart(3, '0')}`);
  }

  await page.evaluate(() => window.__alpha.resumeStartup());
  await page.reload();
  await waitForHome(page);
  await page.waitForTimeout(600);
  await shot(page, 'home');

  // pointer disturbance on the particle hand, and recovery after leaving
  await page.mouse.move(1050, 640);
  await page.waitForTimeout(400);
  await shot(page, 'home-pointer-disturbance');
  await page.mouse.move(300, 880);
  await page.waitForTimeout(1200);
  await shot(page, 'home-pointer-recovered');

  await browser.close();

  if (errors.length) {
    console.error('console errors during capture:\n' + errors.join('\n'));
    process.exitCode = 1;
  } else {
    console.log(`captured startup key frames and home screens into ${OUT}/`);
  }
};

main();
