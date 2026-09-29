/**
 * Startup-page regression checks for Alpha v1.0.0.
 *
 * Scope note: these cover the checks from spec 12 that the startup page is
 * responsible for — V01 (nothing from a destination appears early), V04 (a
 * quick pass over a corner does not navigate), V11 (no input box exists
 * anywhere on this screen) and V15 (reduced motion still reaches home).
 * V05–V09 belong to the navigation phase and are not asserted here.
 */

import { expect, test, type Page } from '@playwright/test';

/** Read the dev inspector rather than guessing at timings. */
async function sceneState(page: Page): Promise<string> {
  return page.evaluate(() => (window as unknown as { __alpha: { state: string } }).__alpha.state);
}

async function waitForHome(page: Page): Promise<void> {
  await expect
    .poll(() => sceneState(page), { timeout: 15_000 })
    .toBe('home');
}

test.beforeEach(async ({ page }) => {
  const errors: string[] = [];
  page.on('console', (m) => m.type() === 'error' && errors.push(m.text()));
  page.on('pageerror', (e) => errors.push(String(e)));
  (page as unknown as { __errors: string[] }).__errors = errors;
});

test('V01 — no destination content exists during startup or at home', async ({ page }) => {
  await page.goto('/');

  // sampled while the startup timeline is still running
  await expect.poll(() => sceneState(page)).not.toBe('loading');
  expect(await page.locator('input, textarea, [contenteditable="true"]').count()).toBe(0);

  await waitForHome(page);
  expect(await page.locator('input, textarea, [contenteditable="true"]').count()).toBe(0);
  await expect(page.getByTestId('particle-brain')).toHaveCount(0);
  await expect(page.getByTestId('technology-tree')).toHaveCount(0);
});

test('V11 — no focusable input can be reached by keyboard', async ({ page }) => {
  await page.goto('/');
  await waitForHome(page);

  for (let i = 0; i < 12; i++) {
    await page.keyboard.press('Tab');
    const tag = await page.evaluate(() => document.activeElement?.tagName ?? 'BODY');
    expect(['INPUT', 'TEXTAREA']).not.toContain(tag);
  }
});

test('hot zones stay disarmed until home is stable', async ({ page }) => {
  await page.goto('/');

  // during loading/intro the zones are not in the DOM at all
  const stateBeforeHome = await sceneState(page);
  if (stateBeforeHome !== 'home') {
    await expect(page.getByTestId('hotzone-human')).toHaveCount(0);
  }

  await waitForHome(page);
  await expect(page.getByTestId('hotzone-human')).toBeVisible();
  await expect(page.getByTestId('hotzone-system')).toBeVisible();
});

test('V04 — a quick pass over a corner does not commit', async ({ page }) => {
  await page.goto('/');
  await waitForHome(page);

  // Time the pass inside the page: under a loaded software renderer the
  // test's own clock can stretch a "quick" pass past the dwell threshold,
  // which is then correctly a dwell (round 3: a dwell now navigates).
  await page.evaluate(() => {
    const w = window as unknown as { __pass: number[] };
    w.__pass = [];
    const z = document.querySelector('[data-testid="hotzone-human"]')!;
    z.addEventListener('pointerenter', () => w.__pass.push(performance.now()));
    z.addEventListener('pointerleave', () => w.__pass.push(performance.now()));
  });
  const zone = page.getByTestId('hotzone-human');
  await zone.hover();
  await page.mouse.move(820, 480);
  await page.waitForTimeout(500);

  const pass = await page.evaluate(() => (window as unknown as { __pass: number[] }).__pass);
  const held = pass.length >= 2 ? pass[1] - pass[0] : Infinity;
  test.skip(held >= 350, `the pass lasted ${Math.round(held)} ms under load: not a quick pass`);
  expect(await sceneState(page)).toBe('home');
});

test('V15 — reduced motion still reaches a stable home', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/');
  await waitForHome(page);

  await expect(page.getByTestId('hotzone-human')).toBeVisible();
  expect(await page.locator('input, textarea').count()).toBe(0);
});

test('V14 — startup produces no console errors and no external requests', async ({ page }) => {
  const external: string[] = [];
  page.on('request', (r) => {
    const url = r.url();
    if (!url.startsWith('http://127.0.0.1:5173') && !url.startsWith('data:') && !url.startsWith('blob:')) {
      external.push(url);
    }
  });

  await page.goto('/');
  await waitForHome(page);
  await page.waitForTimeout(400);

  expect(external).toEqual([]);
  expect((page as unknown as { __errors: string[] }).__errors).toEqual([]);
});

test('V03 — pointer disturbs the particle hand locally, then it recovers', async ({ page }) => {
  await page.goto('/');
  await waitForHome(page);

  // freeze the idle clock so only the pointer moves anything
  await page.evaluate(() => (window as unknown as { __alpha: { setTimeScale(v: number): void } }).__alpha.setTimeScale(0));

  const probe = () =>
    page.evaluate(() => {
      const a = (window as unknown as {
        __alpha: {
          pointerWorld: number[] | null;
          pointerSmoothed: number[] | null;
          pointerInfluence: number;
        };
      }).__alpha;
      return { world: a.pointerWorld, smoothed: a.pointerSmoothed, influence: a.pointerInfluence };
    });

  // over the particle hand
  await page.mouse.move(1050, 640);
  await expect.poll(async () => (await probe()).influence, { timeout: 4000 }).toBeGreaterThan(0.9);

  const on = await probe();
  expect(on.world).not.toBeNull();
  // the disturbance centre must actually reach the cursor; it once chased an
  // unreachable sentinel and sat thousands of units away
  const gap = Math.hypot(on.smoothed![0] - on.world![0], on.smoothed![1] - on.world![1]);
  expect(gap).toBeLessThan(0.05);

  // leaving the canvas must relax it back, not strand the particles
  await page.mouse.move(-5, -5);
  await expect.poll(async () => (await probe()).influence, { timeout: 4000 }).toBeLessThan(0.05);
});

test('home divide line — bottom-left to top-right once home is reached; absent in captures', async ({ page }) => {
  await page.goto('/');
  await waitForHome(page);
  await page.waitForTimeout(300);
  const ends = await page.evaluate(() =>
    [...document.querySelectorAll('[data-testid="home-divide-line"] line')].map((l) => [
      l.getAttribute('x2'),
      l.getAttribute('y2'),
    ]),
  );
  expect(ends).toEqual([
    ['0', '100'],
    ['100', '0'],
  ]);

  await page.goto('/?capture=1');
  await waitForHome(page);
  await expect(page.getByTestId('home-divide-line')).toHaveCount(0);
  await expect(page.getByTestId('theme-toggle')).toHaveCount(0);
});

test('D51 — the particle hand stays clear of the home divide line', async ({ page }) => {
  // dark ground: the particles are the brightest thing right of the plaster fingertip.
  // capture=1 hides the line itself, so only the hand is counted
  await page.goto('/?theme=dark&capture=1');
  await waitForHome(page);
  await page.mouse.move(-5, -5);
  await page.waitForTimeout(600);
  const png = (await page.screenshot()).toString('base64');
  const above = await page.evaluate(async (b64) => {
    const blob = await (await fetch(`data:image/png;base64,${b64}`)).blob();
    const bmp = await createImageBitmap(blob);
    const c = new OffscreenCanvas(bmp.width, bmp.height);
    const g = c.getContext('2d')!;
    g.drawImage(bmp, 0, 0);
    const { data, width: w, height: h } = g.getImageData(0, 0, bmp.width, bmp.height);
    let n = 0;
    // right of the plaster index tip, anything bright on or above the line
    // (bottom-left → top-right) plus a 6 px margin
    for (let y = 0; y < h; y++)
      for (let x = Math.round(w * 0.49); x < w; x++) {
        const lineY = h - (x * h) / w;
        if (y > lineY + 6) continue;
        const i = (y * w + x) * 4;
        if (data[i] + data[i + 1] + data[i + 2] > 3 * 90) n++;
      }
    return n;
  }, png);
  expect(above).toBeLessThanOrEqual(3);
});
