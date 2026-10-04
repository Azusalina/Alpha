/**
 * Round 3 part 9 (D55), the RIGHT column of the drilled-in brain: the records
 * list (status, expand, judgements, revoke, edit, delete, filters) and the
 * model-state tab. Everything runs on the labelled in-memory mock (demo mode):
 * nothing here trains anything. Records are seeded through the same store
 * actions the entry form calls (`window.__alpha.inputs.call`), the panel itself
 * is driven with real clicks and keys.
 *
 * Reduced motion, light theme (acceptance pins ?theme=light). The sandbox
 * WebGL is SwiftShader: no frame time is asserted or reported here.
 */

import { expect, test, type Locator, type Page } from '@playwright/test';

const alpha = <T,>(page: Page, expr: string) => page.evaluate(`window.__alpha.${expr}`) as Promise<T>;
const call = <T,>(page: Page, name: string, ...args: unknown[]) =>
  page.evaluate(([n, a]) => (window as unknown as { __alpha: { inputs: { call(n: string, ...a: unknown[]): Promise<unknown> } } }).__alpha.inputs.call(n as string, ...(a as unknown[])), [name, args] as const) as Promise<T>;

type Rec = { source_id: string; status: string; reason: string | null; partition: string; immediate: boolean; confirm: boolean | null; exclamation: boolean };
type Effect = { parameter: string; revision?: number; after: number; support_after: number; evidence: string; span: [number, number]; partition: string };
type Outcome = { source_id: string; status: string; effects: Effect[] };

/** Into the human destination, drilled into the brain (the records column exists only there). */
async function drilledIn(page: Page, size?: { width: number; height: number }): Promise<void> {
  if (size) await page.setViewportSize(size);
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

const T_RATIONAL = '我重视自由。我看重真实。';
const T_EMOTION = '今天我真的很难过，也有点失望。';

/** One record of each status, the newest last submitted. Returns the ids. */
async function seedOneOfEach(page: Page) {
  const pending = (await call<Outcome>(page, 'submitInput', { text: T_RATIONAL, partition: 'rational', immediate: true }))!;
  const agreed = (await call<Outcome>(page, 'submitInput', { text: T_EMOTION, partition: 'emotional', immediate: false, exclamation: true }))!;
  const crazy = (await call<Outcome>(page, 'submitInput', { text: '我觉得成长比成功重要。', partition: 'crazy', immediate: false }))!;
  const cf = (await call<Outcome>(page, 'submitInput', { text: '我珍惜陪伴。', partition: 'rational', immediate: true }))!;
  await call(page, 'confirm', cf.source_id, false);
  const rv = (await call<Outcome>(page, 'submitInput', { text: '我重视公平。', partition: 'rational', immediate: true, exclamation: true }))!;
  await call(page, 'revoke', rv.source_id);
  return { pending, agreed, crazy, cf, rv };
}

const row = (page: Page, id: string): Locator => page.locator(`[data-testid="record-row"][data-id="${id}"]`);
const head = (page: Page, id: string): Locator => row(page, id).getByTestId('record-head');
const param = (page: Page, partition: string, parameter: string): Locator =>
  page.locator(`[data-testid="state-param"][data-partition="${partition}"][data-parameter="${parameter}"]`);

test('records — one of each status: rows, statuses, judgements, exclamation badge, filters and counts', async ({ page }) => {
  test.setTimeout(120_000);
  await drilledIn(page);
  const ids = await seedOneOfEach(page);
  await drill(page);

  const rows = page.getByTestId('record-row');
  await expect(rows).toHaveCount(5);
  // newest first
  expect(await rows.evaluateAll((els) => els.map((e) => e.getAttribute('data-id')))).toEqual([ids.rv.source_id, ids.cf.source_id, ids.crazy.source_id, ids.agreed.source_id, ids.pending.source_id]);

  const want: [string, string, string | null][] = [
    [ids.pending.source_id, 'pending', null],
    [ids.agreed.source_id, 'agreed', null],
    [ids.crazy.source_id, 'disagreed', 'immediate_false'],
    [ids.cf.source_id, 'disagreed', 'confirm_false'],
    [ids.rv.source_id, 'revoked', 'user_revoked'],
  ];
  for (const [id, status, reason] of want) {
    await expect(row(page, id)).toHaveAttribute('data-status', status);
    await expect(row(page, id).getByTestId('status-chip')).toHaveAttribute('data-status', status);
    await expect(row(page, id)).toHaveAttribute('data-reason', reason ?? '');
  }
  // the words of the statuses, and of the two judgements (当下 / 二次: T, F or —)
  await expect(row(page, ids.pending.source_id).getByTestId('status-chip')).toHaveText('待确认');
  await expect(row(page, ids.agreed.source_id).getByTestId('status-chip')).toHaveText('已认可');
  await expect(row(page, ids.crazy.source_id).getByTestId('status-chip')).toContainText('不同意');
  await expect(row(page, ids.rv.source_id).getByTestId('status-chip')).toContainText('已撤销');
  await expect(row(page, ids.pending.source_id).getByTestId('record-immediate')).toHaveText('当下 T');
  await expect(row(page, ids.pending.source_id).getByTestId('record-confirm')).toHaveText('二次 —');
  await expect(row(page, ids.crazy.source_id).getByTestId('record-immediate')).toHaveText('当下 F');
  await expect(row(page, ids.crazy.source_id).getByTestId('record-confirm')).toHaveText('二次 —');
  await expect(row(page, ids.cf.source_id).getByTestId('record-confirm')).toHaveText('二次 F');
  await expect(row(page, ids.agreed.source_id).getByTestId('record-confirm')).toHaveText('二次 T');
  // the "!" badge only where the submit asserted it (two of them, both T)
  await expect(page.getByTestId('record-exclamation')).toHaveCount(2);
  await expect(row(page, ids.agreed.source_id).getByTestId('record-exclamation')).toHaveCount(1);
  await expect(row(page, ids.pending.source_id).getByTestId('record-exclamation')).toHaveCount(0);
  // partition mark, code point count, excerpt
  await expect(row(page, ids.crazy.source_id).getByTestId('record-partition')).toHaveText('癫狂');
  await expect(row(page, ids.pending.source_id).getByTestId('record-chars')).toHaveText(String([...T_RATIONAL].length));
  await expect(row(page, ids.pending.source_id).getByTestId('record-excerpt')).toHaveText(T_RATIONAL);

  // filters and their counts
  const count = async (f: string) => Number(await page.getByTestId(`filter-count-${f}`).textContent());
  expect([await count('all'), await count('pending'), await count('agreed'), await count('disagreed'), await count('revoked')]).toEqual([5, 1, 1, 2, 1]);
  await page.getByTestId('filter-disagreed').click();
  await expect(rows).toHaveCount(2);
  expect(await rows.evaluateAll((els) => els.map((e) => e.getAttribute('data-status')))).toEqual(['disagreed', 'disagreed']);
  await page.getByTestId('filter-pending').click();
  await expect(rows).toHaveCount(1);
  await page.getByTestId('filter-revoked').click();
  await expect(rows).toHaveCount(1);
  await page.getByTestId('filter-all').click();
  await expect(rows).toHaveCount(5);
});

test('records — empty state and the unconnected state', async ({ page }) => {
  test.setTimeout(90_000);
  await drilledIn(page);
  await drill(page);
  await expect(page.getByTestId('backend-banner')).toContainText('演示');
  await expect(page.getByTestId('tab-records')).toBeVisible();
  await page.getByTestId('backend-leave-demo').click();
  await page.getByTestId('tab-state').click();
});

test('records — a pending row opens to its original text and a hypothetical preview; one row open at a time; the keyboard reaches it', async ({ page }) => {
  test.setTimeout(120_000);
  await drilledIn(page);
  const ids = await seedOneOfEach(page);
  await drill(page);

  const p = ids.pending.source_id;
  await expect(head(page, p)).toHaveAttribute('aria-expanded', 'false');
  await head(page, p).focus();
  await page.keyboard.press('Enter'); // the keyboard opens it too
  await expect(head(page, p)).toHaveAttribute('aria-expanded', 'true');
  const body = row(page, p).getByTestId('record-body');
  await expect(body.getByTestId('record-text')).toContainText(T_RATIONAL.replace(/\n/g, ''));
  // the preview: hypothetical, every effect marked 预览, no revision number
  await expect(body.getByTestId('record-preview-title')).toContainText('预览');
  await expect(body.getByTestId('effect-row')).toHaveCount(2);
  for (const a of await body.getByTestId('effect-action').allTextContents()) expect(a).toBe('预览');
  for (const r of await body.getByTestId('effect-revision').allTextContents()) expect(r).toContain('预览 · 无修订号');
  await expect(body.getByTestId('effect-rule').first()).toContainText('mock.');
  // a pending record is not in training: the state tab still has no evidence for it
  await expect(body.getByTestId('act-confirm-true')).toBeEnabled();
  await expect(body.getByTestId('act-confirm-false')).toBeEnabled();
  // the hover of an effect row lights its mark in the text
  await body.getByTestId('effect-row').first().hover();
  await expect(body.getByTestId('hl-mark').first()).toHaveClass(/is-active/);

  // one at a time
  await head(page, ids.agreed.source_id).click();
  await expect(head(page, ids.agreed.source_id)).toHaveAttribute('aria-expanded', 'true');
  await expect(head(page, p)).toHaveAttribute('aria-expanded', 'false');
  await expect(page.getByTestId('record-body')).toHaveCount(1);
  expect(await alpha(page, 'inputs.expanded()')).toBe(ids.agreed.source_id);
  // clicking the open row closes it
  await head(page, ids.agreed.source_id).click();
  await expect(page.getByTestId('record-body')).toHaveCount(0);
});

test('records — T trains: the row becomes 已认可 with formal effects, the state tab shows the numbers, the brain performs in that state', async ({ page }) => {
  test.setTimeout(120_000);
  await drilledIn(page);
  const pending = (await call<Outcome>(page, 'submitInput', { text: T_RATIONAL, partition: 'rational', immediate: true }))!;
  await drill(page);
  const id = pending.source_id;

  // before: no evidence, no bar, in the state tab
  await page.getByTestId('tab-state').click();
  await expect(param(page, 'rational', 'value.autonomy')).toHaveAttribute('data-observed', 'false');
  await expect(param(page, 'rational', 'value.autonomy').getByTestId('evidence-none')).toContainText('尚无证据');
  await expect(param(page, 'rational', 'value.autonomy').locator('.ev__bar')).toHaveCount(0);
  await page.getByTestId('tab-records').click();

  await head(page, id).click();
  const preview = await row(page, id).getByTestId('effect-row').count();
  expect(preview).toBe(2);
  await row(page, id).getByTestId('act-confirm-true').click();
  await expect(row(page, id)).toHaveAttribute('data-status', 'agreed');
  await expect(row(page, id).getByTestId('status-chip')).toHaveText('已认可');
  await expect(row(page, id).getByTestId('record-confirm')).toHaveText('二次 T');

  // the stale preview is gone; the review's own effects carry revisions
  await expect(row(page, id).getByTestId('record-preview-title')).toHaveCount(0);
  await expect(row(page, id).getByTestId('record-effects-title')).toContainText('演示');
  const revs = await row(page, id).getByTestId('effect-revision').allTextContents();
  expect(revs).toHaveLength(2);
  for (const r of revs) expect(r).toMatch(/修订 #\d+/);
  for (const a of await row(page, id).getByTestId('effect-action').allTextContents()) expect(a).toBe('已应用');
  await expect(row(page, id).getByTestId('act-revoke')).toBeVisible();
  await expect(row(page, id).getByTestId('act-confirm-true')).toHaveCount(0);

  // the brain answered, in the input's own state
  const sig = await alpha<{ kind: string; partition?: string } | null>(page, 'brain.signal()');
  expect(sig).not.toBeNull();
  expect(sig!.kind).toBe('perform');
  expect(sig!.partition).toBe('rational');

  // the state tab: from the adapter, with the right numbers (score = net / (support + 4))
  const st = await alpha<{ cache: { formalEffects: Effect[] } }>(page, `inputs.get('${id}')`);
  const eff = st.cache.formalEffects.find((e) => e.parameter === 'value.autonomy')!;
  expect(eff.after).toBeCloseTo(1 / 5, 6);
  await page.getByTestId('tab-state').click();
  const a = param(page, 'rational', 'value.autonomy');
  await expect(a).toHaveAttribute('data-observed', 'true');
  await expect(a.locator('.ev__bar')).toHaveCount(1);
  await expect(a.locator('.ev__num')).toHaveText('0.2');
  await expect(a.locator('.ev__support')).toHaveText('支持 1');
  await expect(a.getByTestId('evidence-none')).toHaveCount(0);
  await expect(a.getByTestId('state-revision')).toHaveText(`#${eff.revision}`);
  // the parameters of the last training are marked; the others are not
  await expect(a).toHaveAttribute('data-changed', 'true');
  await expect(a.getByTestId('state-changed')).toHaveText('刚变化');
  await expect(param(page, 'rational', 'value.truth')).toHaveAttribute('data-changed', 'true');
  await expect(param(page, 'rational', 'value.care')).toHaveAttribute('data-observed', 'false');
  await expect(param(page, 'rational', 'value.care')).toHaveAttribute('data-changed', 'false');
  // the other partitions know nothing
  await expect(param(page, 'emotional', 'value.autonomy')).toHaveAttribute('data-observed', 'false');
  await expect(page.locator('[data-testid="state-block"][data-partition="rational"] [data-testid="state-observed-count"]')).toHaveText('2 / 13 项有证据');
});

test('records — F disagrees; the actions become edit and delete, and a confirm-false row offers 改判为 T', async ({ page }) => {
  test.setTimeout(120_000);
  await drilledIn(page);
  const pending = (await call<Outcome>(page, 'submitInput', { text: T_RATIONAL, partition: 'rational', immediate: true }))!;
  await drill(page);
  const id = pending.source_id;
  await head(page, id).click();
  await row(page, id).getByTestId('act-confirm-false').click();
  await expect(row(page, id)).toHaveAttribute('data-status', 'disagreed');
  await expect(row(page, id)).toHaveAttribute('data-reason', 'confirm_false');
  await expect(row(page, id).getByTestId('status-chip')).toContainText('不同意');
  await expect(row(page, id).getByTestId('act-edit')).toBeVisible();
  await expect(row(page, id).getByTestId('act-delete')).toBeVisible();
  await expect(row(page, id).getByTestId('act-rejudge')).toBeVisible();
  await expect(row(page, id).getByTestId('act-confirm-true')).toHaveCount(0);
  // edit and delete are demo-only (F6): tagged 仅演示
  await expect(row(page, id).getByTestId('act-edit')).toContainText('仅演示');
  await expect(row(page, id).getByTestId('act-delete')).toContainText('仅演示');
  // F changed no parameter: said so, and the model stays without evidence
  await expect(row(page, id).getByTestId('record-no-change')).toBeVisible();
  // the preview is shown again (fresh), labelled hypothetical
  await expect(row(page, id).getByTestId('record-preview-title')).toContainText('假设');
  // 改判为 T trains after all
  await row(page, id).getByTestId('act-rejudge').click();
  await expect(row(page, id)).toHaveAttribute('data-status', 'agreed');
  await expect(row(page, id).getByTestId('act-revoke')).toBeVisible();
});

test('records — edit returns the record to 待确认 or 不同意 by the new immediate; Escape closes the editor, then the row', async ({ page }) => {
  test.setTimeout(120_000);
  await drilledIn(page);
  const ids = await seedOneOfEach(page);
  await drill(page);
  const id = ids.crazy.source_id; // disagreed, immediate_false
  await head(page, id).click();
  await row(page, id).getByTestId('act-edit').click();
  const ed = row(page, id).getByTestId('record-editor');
  await expect(ed).toBeVisible();
  await expect(ed.getByTestId('editor-text')).toBeFocused();
  await expect(ed.getByTestId('editor-immediate')).not.toBeChecked();

  // Escape: the editor first, the row second
  await page.keyboard.press('Escape');
  await expect(ed).toHaveCount(0);
  await expect(head(page, id)).toHaveAttribute('aria-expanded', 'true');
  await page.keyboard.press('Escape');
  await expect(head(page, id)).toHaveAttribute('aria-expanded', 'false');
  // the drill-in is still there (Escape did not leave it)
  await expect(page.getByTestId('records-panel')).toBeVisible();

  // edit, immediate now true: pending; the preview reflects the NEW text
  await head(page, id).click();
  await row(page, id).getByTestId('act-edit').click();
  await ed.getByTestId('editor-text').fill('我重视成长。');
  await ed.getByTestId('editor-immediate').check();
  await ed.getByTestId('editor-save').click();
  await expect(row(page, id)).toHaveAttribute('data-status', 'pending');
  await expect(row(page, id).getByTestId('record-immediate')).toHaveText('当下 T');
  await expect(row(page, id).getByTestId('record-confirm')).toHaveText('二次 —');
  await expect(row(page, id).getByTestId('record-facts')).toContainText('已编辑');
  await expect(row(page, id).getByTestId('record-text')).toContainText('我重视成长。');
  await expect(row(page, id).getByTestId('effect-row')).toHaveCount(1);
  await expect(row(page, id).getByTestId('effect-row')).toHaveAttribute('data-parameter', 'value.growth');

  // edit a pending-by-edit record is not offered; make a disagreed one and edit it while keeping immediate false
  const other = ids.cf.source_id; // confirm_false
  await head(page, other).click();
  await row(page, other).getByTestId('act-edit').click();
  await row(page, other).getByTestId('editor-text').fill('我珍惜陪伴，也珍惜自由。');
  await row(page, other).getByTestId('editor-immediate').uncheck();
  await row(page, other).getByTestId('editor-save').click();
  await expect(row(page, other)).toHaveAttribute('data-status', 'disagreed');
  await expect(row(page, other)).toHaveAttribute('data-reason', 'immediate_false');
  await expect(row(page, other).getByTestId('record-immediate')).toHaveText('当下 F');

  // the editor refuses empty text
  await row(page, other).getByTestId('act-edit').click();
  await row(page, other).getByTestId('editor-text').fill('   ');
  await expect(row(page, other).getByTestId('editor-error')).toContainText('内容不能为空');
  await expect(row(page, other).getByTestId('editor-save')).toBeDisabled();
});

test('records — delete is two-step, says it is unrecoverable in demo mode, and removes the row', async ({ page }) => {
  test.setTimeout(120_000);
  await drilledIn(page);
  const ids = await seedOneOfEach(page);
  await drill(page);
  const id = ids.crazy.source_id;
  await head(page, id).click();
  await row(page, id).getByTestId('act-delete').click();
  await expect(row(page, id)).toBeVisible(); // nothing is deleted by the first click
  await expect(row(page, id).getByTestId('delete-confirm')).toContainText('确认删除？');
  await expect(row(page, id).getByTestId('delete-confirm')).toContainText('演示模式下删除后不可恢复');
  // cancel keeps it
  await row(page, id).getByTestId('act-delete-cancel').click();
  await expect(row(page, id).getByTestId('delete-confirm')).toHaveCount(0);
  await expect(page.getByTestId('record-row')).toHaveCount(5);
  // confirm removes it
  await row(page, id).getByTestId('act-delete').click();
  await row(page, id).getByTestId('act-delete-confirm').click();
  await expect(row(page, id)).toHaveCount(0);
  await expect(page.getByTestId('record-row')).toHaveCount(4);
  expect((await alpha<Rec[]>(page, 'inputs.list()')).some((r) => r.source_id === id)).toBe(false);
  await expect(page.getByTestId('filter-count-all')).toHaveText('4');

  // a revoked record: read only plus delete, no edit, no T / F
  const rv = ids.rv.source_id;
  await head(page, rv).click();
  await expect(row(page, rv).getByTestId('act-delete')).toBeVisible();
  await expect(row(page, rv).getByTestId('act-edit')).toHaveCount(0);
  await expect(row(page, rv).getByTestId('act-confirm-true')).toHaveCount(0);
  await expect(row(page, rv).getByTestId('act-revoke')).toHaveCount(0);
  // its history is shown (approve then revoke), with revisions
  await expect(row(page, rv).getByTestId('record-effects-title')).toContainText('历史');
  const actions = await row(page, rv).getByTestId('effect-action').allTextContents();
  expect(actions).toContain('已应用');
  expect(actions).toContain('已撤销');
});

test('records — deleting an agreed record withdraws its contribution and removes its whole history', async ({ page }) => {
  test.setTimeout(120_000);
  await drilledIn(page);
  const ids = await seedOneOfEach(page);
  await drill(page);
  const id = ids.agreed.source_id; // emotional, trained: sadness and disappointment have evidence

  await page.getByTestId('tab-state').click();
  await expect(param(page, 'emotional', 'affect.sadness')).toHaveAttribute('data-observed', 'true');
  await page.getByTestId('tab-records').click();

  await head(page, id).click();
  await row(page, id).getByTestId('act-delete').click();
  // the confirmation says what will happen to a trained record
  await expect(row(page, id).getByTestId('delete-confirm')).toContainText('连同全部历史一起删除');
  await expect(row(page, id).getByTestId('delete-confirm')).toContainText('它对模型的贡献也会撤回');
  await row(page, id).getByTestId('act-delete-confirm').click();
  await expect(row(page, id)).toHaveCount(0);
  expect((await alpha<Rec[]>(page, 'inputs.list()')).some((r) => r.source_id === id)).toBe(false);

  // the model is what it was without that record: no evidence again
  await page.getByTestId('tab-state').click();
  await expect(param(page, 'emotional', 'affect.sadness')).toHaveAttribute('data-observed', 'false');
  await expect(param(page, 'emotional', 'affect.sadness').getByTestId('evidence-none')).toContainText('尚无证据');
  await expect(param(page, 'emotional', 'affect.disappointment')).toHaveAttribute('data-observed', 'false');
});

test('records — revoke: 已撤销, history kept, the parameter goes back to 尚无证据 without a bar', async ({ page }) => {
  test.setTimeout(120_000);
  await drilledIn(page);
  const agreed = (await call<Outcome>(page, 'submitInput', { text: T_EMOTION, partition: 'emotional', immediate: true, exclamation: true }))!;
  await drill(page);
  const id = agreed.source_id;

  await page.getByTestId('tab-state').click();
  const sad = param(page, 'emotional', 'affect.sadness');
  await expect(sad).toHaveAttribute('data-observed', 'true');
  await expect(sad.locator('.ev__bar')).toHaveCount(1);
  await page.getByTestId('tab-records').click();

  // an exclamation submit trained at once: formal effects, revisions, nothing pending
  await head(page, id).click();
  await expect(row(page, id).getByTestId('record-facts')).toContainText('断言为真');
  await expect(row(page, id).getByTestId('record-preview-title')).toHaveCount(0);
  await expect(row(page, id).getByTestId('effect-row')).toHaveCount(2);
  for (const r of await row(page, id).getByTestId('effect-revision').allTextContents()) expect(r).toMatch(/修订 #\d+/);

  await row(page, id).getByTestId('act-revoke').click();
  await expect(row(page, id)).toHaveAttribute('data-status', 'revoked');
  await expect(row(page, id).getByTestId('status-chip')).toContainText('已撤销');
  // the reversal effects of THIS revoke, with revisions
  // (the history of the record: the approval and, last, the reversal of THIS revoke, all with revisions)
  await expect(row(page, id).getByTestId('record-effects-title')).toContainText('历史');
  const actions = await row(page, id).getByTestId('effect-action').allTextContents();
  expect(actions.filter((a) => a === '已撤销')).toHaveLength(2);
  expect(actions.filter((a) => a === '已应用')).toHaveLength(2);
  // (and the hypothetical preview of re-agreeing, marked 预览, below it)
  expect(actions.filter((a) => a === '预览')).toHaveLength(2);
  expect((await row(page, id).getByTestId('effect-revision').allTextContents()).filter((r) => /修订 #\d+/.test(r))).toHaveLength(4);
  // a revoke never makes the brain perform again: it still shows the training's signal or none
  await page.getByTestId('tab-state').click();
  await expect(sad).toHaveAttribute('data-observed', 'false');
  await expect(sad.getByTestId('evidence-none')).toContainText('尚无证据');
  await expect(sad.locator('.ev__bar')).toHaveCount(0);
  await expect(page.locator('[data-testid="state-block"][data-partition="emotional"] [data-testid="state-observed-count"]')).toHaveText('尚无证据');
  // the revision tag of the reversal is the latest one
  await expect(sad.getByTestId('state-revision')).toHaveText(/#\d+/);
});

test('records — the evidence after an emoji is highlighted at its exact code point span', async ({ page }) => {
  test.setTimeout(120_000);
  await drilledIn(page);
  const text = '😀😀 今天先这样。我重视自由。';
  const o = (await call<Outcome>(page, 'submitInput', { text, partition: 'rational', immediate: true, exclamation: true }))!;
  expect(o.effects).toHaveLength(1);
  const e = o.effects[0];
  // the span counts code points, not UTF-16 units: the emoji before it are two code points each one unit of span
  expect([...text].slice(e.span[0], e.span[1]).join('')).toBe(e.evidence);
  expect(e.span[0]).toBeLessThan(text.indexOf(e.evidence)); // UTF-16 offset would be larger
  await drill(page);
  await head(page, o.source_id).click();
  const marks = row(page, o.source_id).getByTestId('record-text').getByTestId('hl-mark');
  await expect(marks).toHaveCount(1);
  await expect(marks).toHaveText(e.evidence);
  await expect(marks).toHaveAttribute('data-span', `${e.span[0]},${e.span[1]}`);
  await expect(row(page, o.source_id).getByTestId('hl-mismatch')).toHaveCount(0);
  await expect(row(page, o.source_id).getByTestId('effect-span')).toContainText(`[${e.span[0]}, ${e.span[1]})`);
});

test('records — the panel sits on the right, inside the view, scrolls itself, and does not overflow (1644x957 and 1280x800)', async ({ page }) => {
  test.setTimeout(150_000);
  for (const size of [
    { width: 1644, height: 957 },
    { width: 1280, height: 800 },
  ]) {
    await drilledIn(page, size);
    const ids = await seedOneOfEach(page);
    await drill(page);
    await head(page, ids.pending.source_id).click();
    const box = (await page.getByTestId('records-panel').boundingBox())!;
    expect(box.x).toBeGreaterThan(size.width * 0.6);
    expect(box.x + box.width).toBeLessThanOrEqual(size.width);
    expect(box.y).toBeGreaterThanOrEqual(0);
    expect(box.y + box.height).toBeLessThanOrEqual(size.height);
    expect(box.width).toBeLessThanOrEqual(25.5 * 16);
    const over = await page.getByTestId('tabpanel-records').evaluate((el) => ({ sw: el.scrollWidth, cw: el.clientWidth }));
    expect(over.sw).toBeLessThanOrEqual(over.cw);
    // the expanded row is longer than the panel: the panel scrolls, the page does not
    const doc = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth }));
    expect(doc.sw).toBeLessThanOrEqual(doc.cw);
    // the state tab too
    await page.getByTestId('tab-state').click();
    const over2 = await page.getByTestId('tabpanel-state').evaluate((el) => ({ sw: el.scrollWidth, cw: el.clientWidth, sh: el.scrollHeight, ch: el.clientHeight }));
    expect(over2.sw).toBeLessThanOrEqual(over2.cw);
    expect(over2.sh).toBeGreaterThan(over2.ch); // 3 x 13 parameters scroll inside
  }
});

test('records — the drill-in still works beside the panel: a node opens its detail in the left column and Escape backs out in order', async ({ page }) => {
  test.setTimeout(120_000);
  await drilledIn(page);
  const ids = await seedOneOfEach(page);
  await drill(page);
  await head(page, ids.pending.source_id).click();
  const n = await alpha<[number, number] | null>(page, "brain.screenOf('n05')");
  await page.mouse.move(n![0], n![1]);
  await page.waitForTimeout(200);
  await page.mouse.click(n![0], n![1]);
  await expect(page.getByTestId('node-detail')).toBeVisible();
  // Escape: the open row first, then the node, then the drill-in
  await page.keyboard.press('Escape');
  await expect(head(page, ids.pending.source_id)).toHaveAttribute('aria-expanded', 'false');
  await expect(page.getByTestId('node-detail')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByTestId('node-detail')).toHaveCount(0);
  await page.keyboard.press('Escape');
  await expect(page.getByTestId('records-panel')).toHaveCount(0, { timeout: 15_000 });
});

test('records — AbstainNote says 资料不足 for an abstain rank and nothing for a provisional one', async ({ page }) => {
  test.setTimeout(90_000);
  await page.goto('/?theme=light');
  await expect.poll(() => alpha<string>(page, 'state'), { timeout: 60_000 }).toBe('home');
  // The component is stateless (a pure function of its props returning host elements), so it is
  // rendered here without a second React: the element tree it returns is turned into DOM.
  const out = await page.evaluate(async () => {
    const mod = (await import(/* @vite-ignore */ ['', 'src', 'ui', 'shared', 'AbstainNote.tsx'].join('/'))) as { AbstainNote: (p: { result: unknown }) => unknown };
    type El = { type: string; props: Record<string, unknown> } | string | null | false | undefined | El[];
    const toDom = (el: El): Node | null => {
      if (el === null || el === undefined || el === false) return null;
      if (typeof el === 'string') return document.createTextNode(el);
      if (Array.isArray(el)) {
        const f = document.createDocumentFragment();
        for (const c of el) {
          const n = toDom(c);
          if (n) f.append(n);
        }
        return f;
      }
      const node = document.createElement(el.type);
      for (const [k, v] of Object.entries(el.props)) {
        if (k === 'children') continue;
        if (k === 'className') node.setAttribute('class', String(v));
        else if (typeof v === 'string') node.setAttribute(k, v);
      }
      const kids = toDom(el.props.children as El);
      if (kids) node.append(kids);
      return node;
    };
    const render = (result: unknown): string => {
      const el = mod.AbstainNote({ result }) as El;
      const d = document.createElement('div');
      const n = toDom(el);
      if (n) d.append(n);
      return d.innerHTML;
    };
    return {
      abstain: render({ status: 'abstain', reason: 'insufficient_confirmed_value_evidence', ranked: [] }),
      provisional: render({ status: 'provisional', basis: 'confirmed_value_alignment_only', not_a_probability: true, used_parameters: [], ranked: [] }),
      none: render(null),
    };
  });
  expect(out.abstain).toContain('资料不足');
  expect(out.abstain).toContain('data-testid="abstain-note"');
  expect(out.abstain).toContain('insufficient_confirmed_value_evidence');
  expect(out.provisional).toBe('');
  expect(out.none).toBe('');
});

test('records — a double click on T 认可为真 confirms once and never revokes; a revoked row can be agreed again (fix-ui)', async ({ page }) => {
  test.setTimeout(120_000);
  await drilledIn(page);
  // a record with no effects: the common 未提取到可拟合的证据 case, where the row has no table to push the buttons down
  const p = (await call<Outcome>(page, 'submitInput', { text: '今天天气不错。', partition: 'rational', immediate: true }))!;
  await drill(page);
  const id = p.source_id;
  await head(page, id).click();
  const centre = async (testid: string): Promise<[number, number]> => {
    const el = row(page, id).getByTestId(testid);
    await expect(el).toBeEnabled();
    const b = (await el.boundingBox())!;
    return [b.x + b.width / 2, b.y + b.height / 2];
  };
  const twice = async (testid: string, gap: number): Promise<void> => {
    const [x, y] = await centre(testid);
    await page.mouse.click(x, y);
    await page.waitForTimeout(gap);
    await page.mouse.click(x, y);
  };
  const settle = () => page.waitForTimeout(900); // SETTLE_MS (600) has passed

  // pending -> T twice at the same point (gaps of a real double click) -> agreed, not revoked
  await twice('act-confirm-true', 60);
  await expect(row(page, id)).toHaveAttribute('data-status', 'agreed');
  await settle();
  await expect(row(page, id)).toHaveAttribute('data-status', 'agreed');
  await expect(row(page, id).getByTestId('record-confirm')).toHaveText('二次 T');

  // an intentional revoke after the guard still works
  await row(page, id).getByTestId('act-revoke').click();
  await expect(row(page, id)).toHaveAttribute('data-status', 'revoked');
  await settle();

  // a revoked row can be agreed again (F4); a double click on it does not revoke again
  await expect(row(page, id).getByTestId('act-reagree')).toBeVisible();
  await twice('act-reagree', 0);
  await expect(row(page, id)).toHaveAttribute('data-status', 'agreed');
  await settle();
  await expect(row(page, id)).toHaveAttribute('data-status', 'agreed');
  await expect(row(page, id).getByTestId('act-revoke')).toBeEnabled();
});

test('records — demo wording never claims real training; T pressed on a record button does not switch the theme (fix-ui)', async ({ page }) => {
  test.setTimeout(120_000);
  await drilledIn(page);
  const ids = await seedOneOfEach(page);
  await drill(page);

  // the agreed row (exclamation) in demo: no "正在参与训练", no "已训练", no "训练模型"
  await head(page, ids.agreed.source_id).click();
  const body = row(page, ids.agreed.source_id);
  const text = await body.innerText();
  expect(text).not.toContain('正在参与训练');
  expect(text).not.toContain('已训练');
  expect(text).not.toContain('训练模型');
  expect(text).not.toContain('参与训练');
  await expect(body.getByTestId('record-effects-title')).toContainText('演示');

  await head(page, ids.pending.source_id).click();
  const t = row(page, ids.pending.source_id).getByTestId('act-confirm-true');
  // T on the focused button: the record stays pending and the theme stays light
  await t.focus();
  await page.keyboard.press('t');
  await page.keyboard.press('T');
  expect(await page.evaluate(() => document.documentElement.getAttribute('data-theme'))).toBe('light');
  await expect(row(page, ids.pending.source_id)).toHaveAttribute('data-status', 'pending');
});

test('records — a long unbroken source_ref wraps inside the panel and a row opened low in the list brings its actions into view (fix-ui)', async ({ page }) => {
  test.setTimeout(120_000);
  await drilledIn(page);
  const name = 'x'.repeat(124) + '.txt';
  const first = (await call<Outcome>(page, 'submitInput', { text: '我重视自由。', partition: 'rational', immediate: true, source_ref: name }))!;
  for (let i = 0; i < 8; i++) await call(page, 'submitInput', { text: `第 ${i} 条。我看重真实。`, partition: 'rational', immediate: true });
  await drill(page);
  // the oldest record is the last row of the list
  await head(page, first.source_id).scrollIntoViewIfNeeded();
  await head(page, first.source_id).click();
  const facts = row(page, first.source_id).getByTestId('record-facts');
  await expect(facts).toContainText('.txt');
  const over = await facts.evaluate((el) => el.scrollWidth - el.clientWidth);
  expect(over).toBeLessThanOrEqual(1);
  // its actions end up inside the list's scroll box
  const acts = row(page, first.source_id).getByTestId('record-actions');
  await expect(acts).toBeVisible();
  await expect
    .poll(async () => {
      const a = (await acts.boundingBox())!;
      const b = (await page.getByTestId('tabpanel-records').boundingBox())!;
      return a.y + a.height <= b.y + b.height + 1;
    })
    .toBe(true);
});
