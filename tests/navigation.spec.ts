/**
 * Round 3 navigation checks, both sides (log-v3.md; spec 12 V05–V09, V12).
 *
 * Interaction is driven with real pointer and keyboard input; the dev
 * inspector is used only to read state and to freeze the clock for the
 * pixel comparison, never to trigger what is being tested — except V12's
 * repeated round trips, which call the same navigate() a dwell calls.
 */

import { expect, test, type Page } from '@playwright/test';

type Alpha = {
  state: string;
  progress: number;
  setTimeScale(v: number): void;
  navigate(to: 'human' | 'system' | 'home'): boolean;
  treeUi(): { selected: string | null; hovered: string | null };
  tree: { screenOf(id: string): [number, number] | null };
  humanUi(): {
    focused: boolean;
    selected: string | null;
    reply: string | null;
    focusP: number;
    growP: number;
    dragYaw: number;
  };
  brain: { screenOf(id?: string): [number, number] | null };
};

/** Run `fn` against window.__alpha in the page (the function is serialised). */
const alpha = <T,>(page: Page, fn: (a: Alpha) => T) =>
  page.evaluate(`(${fn.toString()})(window.__alpha)`) as Promise<T>;

async function state(page: Page): Promise<string> {
  return page.evaluate(() => (window as unknown as { __alpha: Alpha }).__alpha.state);
}

async function waitFor(page: Page, s: string, timeout = 60_000): Promise<void> {
  await expect.poll(() => state(page), { timeout }).toBe(s);
}

async function dwell(page: Page, testId: string): Promise<void> {
  const box = await page.getByTestId(testId).boundingBox();
  if (!box) throw new Error(`${testId} is not on screen`);
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.waitForTimeout(600);
}

test.beforeEach(async ({ page }) => {
  const errors: string[] = [];
  page.on('console', (m) => m.type() === 'error' && errors.push(m.text()));
  page.on('pageerror', (e) => errors.push(String(e)));
  (page as unknown as { __errors: string[] }).__errors = errors;
});

test('V08 human — dwell top-left travels to the brain, dwell bottom-right returns', async ({ page }) => {
  test.setTimeout(90_000); // two full-length transitions on a software renderer
  await page.goto('/');
  await waitFor(page, 'home');
  await expect(page.getByTestId('particle-brain')).toHaveCount(0);

  await dwell(page, 'hotzone-human');
  await expect.poll(() => state(page)).toMatch(/toHuman|human/);
  // mid-flight: the destination exists but cannot take focus yet
  await waitFor(page, 'human', 10_000);

  const input = page.getByTestId('human-input');
  await expect(input).toBeVisible();
  await input.click();
  await input.fill('今天有点累');
  await page.keyboard.press('Enter');
  await expect.poll(async () => (await alpha(page, (a) => a.humanUi())).reply ?? '').toContain('原型演示');

  // at the destination only the opposite corner is live
  await expect(page.getByTestId('hotzone-human')).toHaveCount(0);
  await dwell(page, 'hotzone-system');
  await waitFor(page, 'home', 10_000);
  await expect(page.getByTestId('particle-brain')).toHaveCount(0);
  expect(await page.locator('input, textarea').count()).toBe(0);
  expect((page as unknown as { __errors: string[] }).__errors).toEqual([]);
});

test('V09 — repeated requests during a transition do not re-enter it', async ({ page }) => {
  await page.goto('/');
  await waitFor(page, 'home');
  await dwell(page, 'hotzone-human');
  await expect.poll(() => state(page)).toBe('toHuman');
  const p0 = await alpha(page, (a) => a.progress);
  expect(await alpha(page, (a) => a.navigate('human'))).toBe(false);
  expect(await alpha(page, (a) => a.navigate('home'))).toBe(false);
  // progress kept moving forward: the running transition was not restarted
  await page.waitForTimeout(300);
  expect(await alpha(page, (a) => a.progress)).toBeGreaterThan(p0);
  await waitFor(page, 'human', 10_000);
});

test('brain — click drills in, a node opens its detail, Escape backs out step by step', async ({ page }) => {
  test.setTimeout(90_000);
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/');
  await waitFor(page, 'home');
  await dwell(page, 'hotzone-human');
  await waitFor(page, 'human', 10_000);

  const c = await alpha(page, (a) => a.brain.screenOf());
  await page.mouse.click(c![0], c![1]);
  await expect.poll(async () => (await alpha(page, (a) => a.humanUi())).growP, { timeout: 15_000 }).toBe(1);
  expect((await alpha(page, (a) => a.humanUi())).focused).toBe(true);

  const n = await alpha(page, (a) => a.brain.screenOf('n05'));
  await page.mouse.move(n![0], n![1]);
  await page.waitForTimeout(200);
  await page.mouse.click(n![0], n![1]);
  await expect(page.getByTestId('node-detail')).toContainText('示例记录 05');

  await page.keyboard.press('Escape');
  await expect(page.getByTestId('node-detail')).toHaveCount(0);
  await page.keyboard.press('Escape');
  await expect.poll(async () => (await alpha(page, (a) => a.humanUi())).focusP, { timeout: 15_000 }).toBe(0);
  await page.keyboard.press('Escape');
  await waitFor(page, 'home', 10_000);
});

test('V12 — ten round trips land on the same home frame', async ({ page }) => {
  test.setTimeout(180_000);
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/');
  await waitFor(page, 'home');
  await alpha(page, (a) => a.setTimeScale(0));
  await page.mouse.move(-5, -5); // off the canvas: no pointer disturbance at all
  // the reference frame is taken after one return, so the idle clock (reset on
  // arriving home, frozen here) is at the same value in both frames
  await alpha(page, (a) => a.navigate('human'));
  await waitFor(page, 'human', 10_000);
  await alpha(page, (a) => a.navigate('home'));
  await waitFor(page, 'home', 10_000);
  await expect.poll(() => alpha(page, (a) => (a as unknown as { pointerInfluence: number }).pointerInfluence)).toBe(0);
  const before = await page.screenshot();

  for (let i = 0; i < 10; i++) {
    expect(await alpha(page, (a) => a.navigate('human'))).toBe(true);
    await waitFor(page, 'human', 10_000);
    expect(await alpha(page, (a) => a.navigate('home'))).toBe(true);
    await waitFor(page, 'home', 10_000);
  }
  await expect.poll(() => alpha(page, (a) => (a as unknown as { pointerInfluence: number }).pointerInfluence)).toBe(0);
  await page.waitForTimeout(300);
  const after = await page.screenshot();
  expect(after.equals(before)).toBe(true);
});

test('V08 system — dwell bottom-right grows the tree from the right hand, dwell top-left returns', async ({ page }) => {
  test.setTimeout(90_000); // two full-length transitions on a software renderer
  await page.goto('/');
  await waitFor(page, 'home');
  await expect(page.getByTestId('technology-tree')).toHaveCount(0);

  await dwell(page, 'hotzone-system');
  await waitFor(page, 'system', 10_000);
  await expect(page.getByTestId('technology-tree')).toBeVisible();
  // natural language has one entrance only, on the human side (IDEA §4)
  expect(await page.locator('input, textarea').count()).toBe(0);
  await expect(page.getByTestId('hotzone-system')).toHaveCount(0);

  await dwell(page, 'hotzone-human');
  await waitFor(page, 'home', 10_000);
  await expect(page.getByTestId('technology-tree')).toHaveCount(0);
  expect((page as unknown as { __errors: string[] }).__errors).toEqual([]);
});

test('tree — a node opens its detail, a linked record can be followed, Escape closes then returns', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/');
  await waitFor(page, 'home');
  await dwell(page, 'hotzone-system');
  await waitFor(page, 'system', 10_000);

  const n = await alpha(page, (a) => a.tree.screenOf('n07'));
  await page.mouse.move(n![0], n![1]);
  await expect.poll(async () => (await alpha(page, (a) => a.treeUi())).hovered).toBe('n07');
  await page.mouse.click(n![0], n![1]);
  const detail = page.getByTestId('node-detail');
  await expect(detail).toContainText('示例记录 07');
  await detail.getByRole('button', { name: '示例记录 15' }).click();
  await expect(detail).toContainText('示例记录 15');

  await page.keyboard.press('Escape');
  await expect(detail).toHaveCount(0);
  await page.keyboard.press('Escape');
  await waitFor(page, 'home', 10_000);
});

test('V12 system — ten round trips land on the same home frame', async ({ page }) => {
  test.setTimeout(180_000);
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/');
  await waitFor(page, 'home');
  await alpha(page, (a) => a.setTimeScale(0));
  await page.mouse.move(-5, -5);
  const trip = async () => {
    expect(await alpha(page, (a) => a.navigate('system'))).toBe(true);
    await waitFor(page, 'system', 10_000);
    expect(await alpha(page, (a) => a.navigate('home'))).toBe(true);
    await waitFor(page, 'home', 10_000);
  };
  await trip();
  await expect.poll(() => alpha(page, (a) => (a as unknown as { pointerInfluence: number }).pointerInfluence)).toBe(0);
  const before = await page.screenshot();
  for (let i = 0; i < 10; i++) await trip();
  await page.waitForTimeout(300);
  const after = await page.screenshot();
  expect(after.equals(before)).toBe(true);
});

test('brain — drag turns the resting brain without drilling in; the divide line splits the view', async ({ page }) => {
  test.setTimeout(90_000);
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/');
  await waitFor(page, 'home');
  await expect(page.getByTestId('divide-line')).toHaveCount(0);
  await dwell(page, 'hotzone-human');
  await waitFor(page, 'human', 10_000);

  // D45: corner to corner once arrived
  const ends = await page.evaluate(() =>
    [...document.querySelectorAll('[data-testid="divide-line"] line')].map((l) => [
      l.getAttribute('x2'),
      l.getAttribute('y2'),
    ]),
  );
  expect(ends).toEqual([
    ['0', '0'],
    ['100', '100'],
  ]);

  // D42: a drag rotates and does not count as a click
  const c = (await alpha(page, (a) => a.brain.screenOf()))!;
  const yaw0 = (await alpha(page, (a) => a.humanUi())).dragYaw;
  await page.mouse.move(c[0], c[1]);
  await page.mouse.down();
  for (let i = 1; i <= 8; i++) await page.mouse.move(c[0] + i * 12, c[1]);
  await page.mouse.up();
  const after = await alpha(page, (a) => a.humanUi());
  expect(after.dragYaw).toBeGreaterThan(yaw0 + 0.3);
  expect(after.focused).toBe(false);

  // a plain click still drills in
  await page.mouse.click(c[0], c[1]);
  await expect.poll(async () => (await alpha(page, (a) => a.humanUi())).focused).toBe(true);
});
