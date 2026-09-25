// Scratch (D10): full-mode home captures for several tiers / seeds.
// Usage: node shot-seeds.mjs <out-dir> <query>... (e.g. "tier=medium&seed=1")
import { chromium } from '@playwright/test';
const [out, ...queries] = process.argv.slice(2);
const browser = await chromium.launch({ headless: true, executablePath: process.env.ALPHA_CHROMIUM || undefined });
const page = await browser.newPage({ viewport: { width: 1644, height: 957 }, deviceScaleFactor: 1 });
for (const q of queries) {
  await page.goto(`http://127.0.0.1:5173/?${q}`);
  await page.waitForFunction(() => window.__alpha?.state === 'home', null, { timeout: 60_000 });
  await page.mouse.move(-5, -5);
  await page.waitForTimeout(800);
  await page.evaluate(() => window.__alpha.setTimeScale(0));
  await page.waitForTimeout(200);
  const d = await page.evaluate(() => window.__alpha.particleDigest);
  await page.screenshot({ path: `${out}/${q.replace(/[=&]/g, '_')}.png` });
  console.log(q, JSON.stringify(d));
}
await browser.close();
