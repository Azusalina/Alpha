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

  // round 3 part 9 (D54): the prototype's one-line box is the entry form's textarea now;
  // Enter is a line break in it, and nothing is sent until the form is submitted
  const input = page.getByTestId('human-input');
  await expect(input).toBeVisible();
  await expect(input).toHaveJSProperty('tagName', 'TEXTAREA');
  await input.click();
  await input.fill('今天有点累');
  await page.keyboard.press('Enter');
  await expect(input).toHaveValue('今天有点累\n');
  await expect(page.getByTestId('backend-banner')).toContainText('后端未连接');

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

/**
 * The DOM divide line draws from rAF ticks (HumanPanel) and lags the state flip
 * to 'home' when the machine is loaded: its two <line>s are back at the centre
 * (x2 = 50, zero length) only a few frames later. A fixed 300 ms was not enough
 * under load (the whole 2878-pixel frame difference was the diagonal), so the
 * screenshots wait for the line to be at rest, then two animation frames.
 */
async function dividerAtRest(page: Page): Promise<void> {
  await expect
    .poll(() => page.getByTestId('divide-line').locator('line').evaluateAll((ls) => ls.every((l) => l.getAttribute('x2') === '50' && l.getAttribute('y2') === '50')), { timeout: 15_000 })
    .toBe(true);
  await page.evaluate(() => new Promise<void>((r) => requestAnimationFrame(() => requestAnimationFrame(() => r()))));
}

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
  await dividerAtRest(page);
  const before = await page.screenshot();

  for (let i = 0; i < 10; i++) {
    expect(await alpha(page, (a) => a.navigate('human'))).toBe(true);
    await waitFor(page, 'human', 10_000);
    expect(await alpha(page, (a) => a.navigate('home'))).toBe(true);
    await waitFor(page, 'home', 10_000);
  }
  await expect.poll(() => alpha(page, (a) => (a as unknown as { pointerInfluence: number }).pointerInfluence)).toBe(0);
  await dividerAtRest(page);
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

test('tree — flat nodes: hover and click highlight, double click opens the page, Escape steps back', async ({ page }) => {
  test.setTimeout(90_000);
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/');
  await waitFor(page, 'home');
  await dwell(page, 'hotzone-system');
  await waitFor(page, 'system', 10_000);

  const n07 = page.getByTestId('tree-node-n07');
  await n07.hover();
  await expect.poll(async () => (await alpha(page, (a) => a.treeUi())).hovered).toBe('n07');
  await expect(n07).toHaveClass(/is-hot/);
  await n07.click();
  expect((await alpha(page, (a) => a.treeUi())).selected).toBe('n07');
  await expect(page.getByTestId('node-page')).toHaveCount(0);

  await n07.dblclick();
  const sheet = page.getByTestId('node-page');
  await expect(sheet).toContainText('示例记录 07');
  await sheet.getByRole('button', { name: '示例记录 15' }).click();
  await expect(sheet).toContainText('示例记录 15');

  await page.keyboard.press('Escape');
  await expect(sheet).toHaveCount(0);
  await page.keyboard.press('Escape');
  expect((await alpha(page, (a) => a.treeUi())).selected).toBeNull();
  await page.keyboard.press('Escape');
  await waitFor(page, 'home', 10_000);
});

test('tree — the root is attached to the particle hand wrist, and Enter opens a node', async ({ page }) => {
  test.setTimeout(90_000);
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/');
  await waitFor(page, 'home');
  await alpha(page, (a) => a.navigate('system'));
  await waitFor(page, 'system', 10_000);
  const root = await page.getByTestId('tree-node-n00').boundingBox();
  const wrist = await alpha(page, (a) => (a as unknown as { wristScreen(): [number, number] }).wristScreen());
  expect(Math.hypot(root!.x + root!.width / 2 - wrist[0], root!.y + root!.height / 2 - wrist[1])).toBeLessThan(3);

  await page.getByTestId('tree-node-n03').focus();
  await page.keyboard.press('Enter');
  await expect(page.getByTestId('node-page')).toContainText('示例记录 03');
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

test('brain perform — a performance per state, read back through the signal, and the resting frame returns exactly', async ({ page }) => {
  test.setTimeout(120_000);
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/?theme=light');
  await waitFor(page, 'home');
  await alpha(page, (a) => a.setTimeScale(0));
  await page.mouse.move(-5, -5);
  await alpha(page, (a) => a.navigate('human'));
  await waitFor(page, 'human');
  await page.waitForTimeout(600);
  // the canvas alone: every DOM overlay hidden
  await page.addStyleTag({ content: 'body *:not(canvas):not(:has(canvas)) { visibility: hidden !important; }' });
  await page.waitForTimeout(300);

  type Brain = {
    perform(p: string, i: number, seed?: number): void;
    signal(): { kind: string; partition?: string; intensity?: number; seed?: number; t: number } | null;
    setSignalTime(t: number): void;
    perfInfo(): { edges: number; shake: number };
  };
  const brain = <T,>(fn: (b: Brain) => T) =>
    page.evaluate(`(${fn.toString()})(window.__alpha.brain)`) as Promise<T>;

  const rest = await page.screenshot();

  const frames: Record<string, Buffer> = {};
  for (const partition of ['rational', 'emotional', 'crazy']) {
    await page.evaluate(`window.__alpha.brain.perform('${partition}', 1.4, 42)`);
    await page.waitForTimeout(200);
    const s = await brain((b) => b.signal());
    // D57: kind, state, strength (clamped to 0..1) and seed are readable
    expect(s).toMatchObject({ kind: 'perform', partition, intensity: 1, seed: 42 });
    await brain((b) => b.setSignalTime(0.6));
    await page.waitForTimeout(200);
    // rational and emotional run bolts along the net's edges; crazy is a light, with no bolts at all
    const edges = (await brain((b) => b.perfInfo())).edges;
    if (partition === 'crazy') expect(edges).toBe(0);
    else expect(edges).toBeGreaterThan(0);
    // with the clock frozen a captured time is one deterministic frame, and it differs from rest
    frames[partition] = await page.screenshot();
    expect(frames[partition].equals(rest)).toBe(false);
    expect(frames[partition].equals(await page.screenshot())).toBe(true);
    // past its life the performance ends and the brain is exactly what it was
    await brain((b) => b.setSignalTime(100));
    await page.waitForTimeout(300);
    expect(await brain((b) => b.signal())).toBeNull();
    expect((await page.screenshot()).equals(rest)).toBe(true);
  }
  // each state looks like itself, not like the others
  expect(frames.rational.equals(frames.emotional)).toBe(false);
  expect(frames.emotional.equals(frames.crazy)).toBe(false);

  // a new call while one runs replaces it
  await page.evaluate(`window.__alpha.brain.perform('rational', 0.5, 1)`);
  await page.waitForTimeout(100);
  await page.evaluate(`window.__alpha.brain.perform('crazy', 0.5, 2)`);
  await page.waitForTimeout(100);
  expect(await brain((b) => b.signal())).toMatchObject({ partition: 'crazy', seed: 2 });
});
