/**
 * Round 3 part 9 (D54-D57), the shared UI foundation under the entry and
 * records panels: the backend banner, the input store and its brain
 * performances, Escape layering. The panels' own behaviour is tested in their
 * own specs.
 *
 * The store is driven through the inspector (`window.__alpha.inputs.call`, the
 * same functions the panels call); what is asserted is what a panel will observe. Nothing here trains
 * anything: the only adapter is the labelled in-memory mock (D56).
 */

import { expect, test, type Page } from '@playwright/test';

const alpha = <T,>(page: Page, expr: string) => page.evaluate(`window.__alpha.${expr}`) as Promise<T>;

async function atHuman(page: Page): Promise<void> {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/?theme=light');
  await expect.poll(() => alpha<string>(page, 'state'), { timeout: 60_000 }).toBe('home');
  await alpha(page, "navigate('human')");
  await expect.poll(() => alpha<string>(page, 'state'), { timeout: 15_000 }).toBe('human');
  await alpha(page, 'setTimeScale(0)'); // a performance then stays readable
}

/** One `inputStore` action through the inspector (the same function the panels call). */
const call = <T,>(page: Page, name: string, ...args: unknown[]) =>
  page.evaluate(([n, a]) => (window as unknown as { __alpha: { inputs: { call(n: string, ...a: unknown[]): Promise<unknown> } } }).__alpha.inputs.call(n as string, ...(a as unknown[])), [name, args] as const) as Promise<T>;

/** The running performance of the brain, if any. The clock is frozen, so one lasts until the next. */
const performing = async (page: Page) => {
  const s = await alpha<{ kind: string; partition?: string; intensity?: number; seed?: number; fromCss: [number, number] | null } | null>(page, 'brain.signal()');
  return s && s.kind === 'perform' ? { partition: s.partition!, intensity: s.intensity!, seed: s.seed!, fromCss: s.fromCss } : null;
};

test('foundation — banner: unconnected by default, demo by hand, permanent strip, leaving clears', async ({ page }) => {
  test.setTimeout(90_000);
  await atHuman(page);
  const banner = page.getByTestId('backend-banner');
  await expect(banner).toContainText('后端未连接');
  expect(await alpha(page, 'backend.mode()')).toBe('unconnected');
  // a plain browser never connects by itself, and there is no retry without a desktop host
  await expect(page.getByTestId('backend-retry')).toHaveCount(0);

  await page.getByTestId('backend-enter-demo').click();
  expect(await alpha(page, 'backend.mode()')).toBe('demo');
  await expect(banner).toContainText('演示数据 · 未运行模型 · 刷新即清空');
  await expect(page.getByTestId('backend-enter-demo')).toHaveCount(0);

  await call(page, 'submitInput', { text: '今天很难过。', partition: 'emotional', immediate: true });
  expect((await alpha<unknown[]>(page, 'inputs.list()')).length).toBe(1);

  // with demo data present leaving asks once more (a stray click must not wipe it)
  await page.getByTestId('backend-leave-demo').click();
  expect(await alpha(page, 'backend.mode()')).toBe('demo');
  await page.getByTestId('backend-leave-demo').click();
  expect(await alpha(page, 'backend.mode()')).toBe('unconnected');
  expect(await alpha<unknown[]>(page, 'inputs.list()')).toEqual([]);
  await expect(banner).toContainText('后端未连接');
});

test('foundation — unconnected: actions fail into state, nothing is swallowed', async ({ page }) => {
  test.setTimeout(90_000);
  await atHuman(page);
  expect(await call(page, 'submitInput', { text: 'x', partition: 'rational', immediate: true })).toBeNull();
  const s = await alpha<{ error: { code: string; action: string } | null }>(page, 'inputs.state()');
  expect(s.error).toMatchObject({ code: 'UNAVAILABLE', action: 'submit' });
});

test("foundation — the brain performs only after a training event, in the input's own state", async ({ page }) => {
  test.setTimeout(90_000);
  await atHuman(page);
  await page.getByTestId('backend-enter-demo').click();
  const text = '今天我真的很难过，也有点失望。';
  type Outcome = { source_id: string; status: string; trained: boolean; previewState: string; effects: { action: string; delta: number; revision?: number }[]; confirm: boolean | null; immediate: boolean | null };
  type Review = { status: string; effects: { action: string; delta: number }[] };
  const intensityOf = (effects: { delta: number }[]) => Math.min(1, Math.max(0.25, 0.25 + 0.15 * effects.length + effects.reduce((s, e) => s + Math.abs(e.delta), 0) * 0.5));

  // T/F clicked false at input: disagreed, nothing performed, no preview
  const a = (await call<Outcome>(page, 'submitInput', { text, partition: 'emotional', immediate: false }))!;
  expect(a).toMatchObject({ status: 'disagreed', previewState: 'none', trained: false });
  expect(await performing(page)).toBeNull();

  // immediate true: pending, with a hypothetical preview (no revisions), nothing performed
  const b = (await call<Outcome>(page, 'submitInput', { text, partition: 'rational', immediate: true }))!;
  expect(b.status).toBe('pending');
  await expect.poll(async () => (await alpha<{ lastResult: { previewState: string } }>(page, 'inputs.state()')).lastResult.previewState).toBe('ready');
  const pv = (await alpha<{ cache: { preview: { effects: { revision?: number }[] } } }>(page, `inputs.get('${b.source_id}')`)).cache.preview;
  expect(pv.effects.length).toBeGreaterThan(0);
  expect(pv.effects.some((e) => e.revision !== undefined)).toBe(false);
  expect(await performing(page)).toBeNull();

  // confirm T: agreed with formal effects; the brain answers in the input's state; the stale preview is gone
  const c = (await call<Review>(page, 'confirm', b.source_id, true))!;
  expect(c.status).toBe('agreed');
  expect(c.effects.length).toBeGreaterThan(0);
  const p1 = await performing(page);
  expect(p1?.partition).toBe('rational');
  expect(p1!.fromCss).toBeNull(); // no row element is registered for it here: the brain's own corner
  expect(p1!.intensity).toBeCloseTo(intensityOf(c.effects), 6);
  const rec = await alpha<{ record: { status: string }; cache: { formalEffects: unknown[]; preview: unknown } }>(page, `inputs.get('${b.source_id}')`);
  expect(rec.record.status).toBe('agreed');
  expect(rec.cache.formalEffects).toHaveLength(c.effects.length);
  expect(rec.cache.preview).toBeNull();

  // F on the agreed one: disagreed, reversal effects, no new performance
  const d = (await call<Review>(page, 'confirm', b.source_id, false))!;
  expect(d.status).toBe('disagreed');
  expect(d.effects.length).toBeGreaterThan(0);
  expect(d.effects.every((e) => e.action === 'revoke')).toBe(true);
  expect((await performing(page))?.seed).toBe(p1!.seed);

  // the identical judgement again: a no-op, nothing performed
  const d2 = (await call<Review>(page, 'confirm', b.source_id, false))!;
  expect(d2.effects).toEqual([]);
  expect((await performing(page))?.seed).toBe(p1!.seed);
  expect((await alpha<{ cache: { lastWasNoop: boolean } }>(page, `inputs.get('${b.source_id}')`)).cache.lastWasNoop).toBe(true);

  // exclamation: trains at once, even with immediate false; formal effects in the result, no preview; the brain answers
  const e = (await call<Outcome>(page, 'submitInput', { text, partition: 'crazy', immediate: false, exclamation: true }))!;
  expect(e).toMatchObject({ status: 'agreed', trained: true, previewState: 'none', confirm: true, immediate: true });
  expect(e.effects.length).toBeGreaterThan(0);
  expect(e.effects.every((x) => x.revision !== undefined)).toBe(true);
  const p2 = await performing(page);
  expect(p2?.partition).toBe('crazy');
  // the lightning leaves from the entry form (the registered anchor), not from nowhere
  const box = (await page.getByTestId('entry-panel').boundingBox())!;
  expect(p2!.fromCss![0]).toBeCloseTo(box.x + box.width / 2, 0);
  expect(p2!.fromCss![1]).toBeCloseTo(box.y + box.height / 2, 0);
  expect(p2!.seed).not.toBe(p1!.seed);
  expect(p2!.intensity).toBeCloseTo(intensityOf(e.effects), 6);

  const records = await alpha<{ status: string; reason: string | null }[]>(page, 'inputs.list()');
  expect(records.map((r) => [r.status, r.reason])).toEqual([['agreed', null], ['disagreed', 'confirm_false'], ['disagreed', 'immediate_false']]);
});

test('foundation — a response that outlives its back end is dropped; Escape closes one layer at a time', async ({ page }) => {
  test.setTimeout(90_000);
  await atHuman(page);
  await page.getByTestId('backend-enter-demo').click();

  // the back end changes while the submit is on its way
  const stale = await page.evaluate(async () => {
    const a = (window as unknown as { __alpha: { inputs: { call(n: string, ...a: unknown[]): Promise<unknown> }; backend: { leaveDemo(): void } } }).__alpha;
    const p = a.inputs.call('submitInput', { text: '今天很开心。', partition: 'emotional', immediate: true });
    a.backend.leaveDemo();
    return p;
  });
  expect(stale).toBeNull();
  await page.waitForTimeout(100);
  const s = await alpha<{ lastResult: unknown }>(page, 'inputs.state()');
  expect(s.lastResult).toBeNull();
  expect(await alpha<unknown[]>(page, 'inputs.list()')).toEqual([]);

  await page.getByTestId('backend-enter-demo').click();
  const a = (await call<{ source_id: string }>(page, 'submitInput', { text: '今天很开心。', partition: 'emotional', immediate: true }))!;
  await call(page, 'refresh');
  await call(page, 'expand', a.source_id);
  await call(page, 'openEditor', a.source_id);
  const st = () => alpha<{ editingId: string | null; lastResult: unknown }>(page, 'inputs.state()');
  expect(await call(page, 'closeTopLayer', true)).toBe(true); // the editor
  expect((await st()).editingId).toBeNull();
  expect(await alpha(page, 'inputs.expanded()')).toBe(a.source_id);
  expect(await call(page, 'closeTopLayer', true)).toBe(true); // the open row
  expect(await alpha(page, 'inputs.expanded()')).toBeNull();
  expect((await st()).lastResult).not.toBeNull();
  expect(await call(page, 'closeTopLayer', true)).toBe(false); // the result panel is not on screen while drilled in
  expect(await call(page, 'closeTopLayer', false)).toBe(true); // entry visible: the result panel closes
  expect(await call(page, 'closeTopLayer')).toBe(false); // nothing left
});

test('foundation — Escape in the destination closes the result panel before leaving', async ({ page }) => {
  test.setTimeout(90_000);
  await atHuman(page);
  await page.getByTestId('backend-enter-demo').click();
  await call(page, 'submitInput', { text: '今天很开心。', partition: 'emotional', immediate: true });
  expect((await alpha<{ lastResult: unknown }>(page, 'inputs.state()')).lastResult).not.toBeNull();
  await page.keyboard.press('Escape');
  expect((await alpha<{ lastResult: unknown }>(page, 'inputs.state()')).lastResult).toBeNull();
  expect(await alpha(page, 'state')).toBe('human');
  await page.keyboard.press('Escape');
  await expect.poll(() => alpha<string>(page, 'state'), { timeout: 15_000 }).toBe('home');
});
