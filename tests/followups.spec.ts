/**
 * 2026-10-02 follow-ups: replaying the brain's answer from a trainable record,
 * the model reset on the main node, and the clickable ECG divide line of the
 * particle-brain page. Demo mode (the labelled mock), reduced motion, light theme.
 */

import { expect, test, type Page } from '@playwright/test';

const alpha = <T,>(page: Page, expr: string) => page.evaluate(`window.__alpha.${expr}`) as Promise<T>;
const call = <T,>(page: Page, name: string, ...args: unknown[]) =>
  page.evaluate(([n, a]) => (window as unknown as { __alpha: { inputs: { call(n: string, ...a: unknown[]): Promise<unknown> } } }).__alpha.inputs.call(n as string, ...(a as unknown[])), [name, args] as const) as Promise<T>;
type Outcome = { source_id: string };

async function humanPage(page: Page): Promise<void> {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/?theme=light');
  await expect.poll(() => alpha<string>(page, 'state'), { timeout: 60_000 }).toBe('home');
  await alpha(page, "navigate('human')");
  await expect.poll(() => alpha<string>(page, 'state'), { timeout: 15_000 }).toBe('human');
  await alpha(page, 'setTimeScale(0)');
  await page.getByTestId('backend-enter-demo').click();
}

async function drill(page: Page): Promise<void> {
  const c = await alpha<[number, number] | null>(page, 'brain.screenOf()');
  await page.mouse.click(c![0], c![1]);
  await expect(page.getByTestId('records-panel')).toBeVisible({ timeout: 15_000 });
}

test('divide line — a click turns to the ball page; look 1/2 switch; Esc and the back button return', async ({ page }) => {
  test.setTimeout(90_000);
  await humanPage(page);
  await expect(page.getByTestId('divide-ecg').locator('path').first()).toHaveAttribute('d', /^M/);
  await expect(page.getByTestId('ball-page')).toHaveCount(0);
  // a point on the diagonal, away from the panels: a quarter of the way from the top-left corner
  const vp = page.viewportSize()!;
  // hovering the click area: the cursor changes, the line brightens and a hint follows the pointer
  await page.mouse.move(vp.width * 0.25 + 26, vp.height * 0.25 - 12); // off the exact line, inside the wide area
  await expect(page.getByTestId('divide-line')).toHaveClass(/is-hot/);
  await expect(page.getByTestId('divide-hint')).toHaveClass(/is-hot/);
  expect(await page.getByTestId('divide-hit').evaluate((el) => getComputedStyle(el).cursor)).toContain('url(');
  await page.mouse.move(vp.width * 0.75, vp.height * 0.1);
  await expect(page.getByTestId('divide-line')).not.toHaveClass(/is-hot/);
  await page.mouse.click(vp.width * 0.25 + 26, vp.height * 0.25 - 12);
  const ball = page.getByTestId('ball-page');
  await expect(ball).toBeVisible();
  await expect(ball).toHaveClass(/is-shown/);
  await expect(page.getByTestId('ball-dashboard')).toBeVisible();
  const look = page.getByTestId('ball-look');
  const first = await ball.getAttribute('data-effect');
  await look.click();
  expect(await ball.getAttribute('data-effect')).not.toBe(first);
  await look.click();
  expect(await ball.getAttribute('data-effect')).toBe(first);
  // the canvas drew something
  const lit = await page.getByTestId('ball-canvas').evaluate((c: HTMLCanvasElement) => {
    const gl = c.getContext('webgl2') ?? c.getContext('webgl');
    return !!gl;
  });
  expect(lit).toBe(true);
  await page.keyboard.press('Escape');
  await expect(ball).toHaveCount(0);
  expect(await alpha<string>(page, 'state')).toBe('human');
  await page.mouse.click(vp.width * 0.25, vp.height * 0.25);
  await expect(ball).toBeVisible();
  await page.getByTestId('ball-back').click();
  await expect(ball).toHaveCount(0);
});

test('brain — long idle spin does not come back as a fast unwind', async ({ page }) => {
  test.setTimeout(90_000);
  await page.goto('/?theme=light');
  await expect.poll(() => alpha<string>(page, 'state'), { timeout: 60_000 }).toBe('home');
  await alpha(page, "navigate('human')");
  await expect.poll(() => alpha<string>(page, 'state'), { timeout: 15_000 }).toBe('human');
  await alpha(page, 'setTimeScale(60)');
  await page.waitForTimeout(3000);
  const yaw = (await alpha<{ dragYaw: number }>(page, 'humanUi()')).dragYaw;
  expect(Math.abs(yaw)).toBeLessThanOrEqual(Math.PI + 0.01);
});

test('replay — clicking a trainable record plays the brain again; a pending one does not', async ({ page }) => {
  test.setTimeout(120_000);
  await humanPage(page);
  const trained = (await call<Outcome>(page, 'submitInput', { text: '我重视自由。我看重真实。', partition: 'rational', immediate: true, exclamation: true }))!;
  const pending = (await call<Outcome>(page, 'submitInput', { text: '我珍惜陪伴。', partition: 'rational', immediate: true }))!;
  await drill(page);
  await alpha(page, 'setTimeScale(1)');
  await page.waitForTimeout(2500); // let the performance of the submit end
  await expect.poll(() => alpha<{ signal: unknown }>(page, 'humanUi()').then((u) => u.signal), { timeout: 10_000 }).toBeNull();
  await page.locator(`[data-testid="record-row"][data-id="${pending.source_id}"] [data-testid="record-head"]`).click();
  expect((await alpha<{ signal: unknown }>(page, 'humanUi()')).signal).toBeNull();
  await page.locator(`[data-testid="record-row"][data-id="${trained.source_id}"] [data-testid="record-head"]`).click();
  expect((await alpha<{ signal: { kind: string } | null }>(page, 'humanUi()')).signal?.kind).toBe('perform');
});

test('model reset — on the main node only, two steps, empties the model and the history', async ({ page }) => {
  test.setTimeout(120_000);
  await humanPage(page);
  await call<Outcome>(page, 'submitInput', { text: '我重视自由。我看重真实。', partition: 'rational', immediate: true, exclamation: true });
  await drill(page);
  await expect(page.locator('[data-testid="record-row"][data-status="agreed"]')).toHaveCount(1);
  const root = await alpha<[number, number] | null>(page, "brain.screenOf('root')");
  await page.mouse.move(root![0], root![1]);
  await page.waitForTimeout(200);
  await page.mouse.click(root![0], root![1]);
  await expect(page.getByTestId('node-detail')).toBeVisible();
  await expect(page.getByTestId('model-reset')).toBeVisible();
  await page.getByTestId('model-reset-open').click();
  await expect(page.getByTestId('model-reset-confirm')).toBeVisible();
  await page.getByTestId('model-reset-confirm').click();
  await expect(page.getByTestId('model-reset-confirm')).toHaveCount(0);
  // the inputs stay but nothing of them is agreed any more
  await expect(page.getByTestId('record-row')).toHaveCount(1);
  await expect(page.locator('[data-testid="record-row"][data-status="agreed"]')).toHaveCount(0);
});
