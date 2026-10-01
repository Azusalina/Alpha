/**
 * Round 3 part 9 (D54-D57): the entry panel and its result, in the human
 * destination's upper-right area. Driven with real clicks and keys; the
 * inspector only reads state (inputs, brain.signal) and freezes the clock so a
 * performance stays readable. The only adapter is the labelled in-memory mock
 * (D56): nothing here trains anything.
 */

import { expect, test, type Page } from '@playwright/test';

const alpha = <T,>(page: Page, expr: string) => page.evaluate(`window.__alpha.${expr}`) as Promise<T>;

async function atHuman(page: Page, theme = 'light'): Promise<void> {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto(`/?theme=${theme}`);
  await expect.poll(() => alpha<string>(page, 'state'), { timeout: 60_000 }).toBe('home');
  await alpha(page, "navigate('human')");
  await expect.poll(() => alpha<string>(page, 'state'), { timeout: 15_000 }).toBe('human');
  await alpha(page, 'setTimeScale(0)'); // a performance then stays readable
}

async function atHumanDemo(page: Page, theme = 'light'): Promise<void> {
  await atHuman(page, theme);
  await page.getByTestId('backend-enter-demo').click(); // the real button
  await expect(page.getByTestId('backend-banner')).toHaveAttribute('data-mode', 'demo');
}

type Partition = 'rational' | 'emotional' | 'crazy';

interface Fill {
  partition?: Partition;
  kind?: 'diary' | 'chat' | 'philosophy';
  speaker?: string;
  text: string;
  immediate?: boolean;
  exclamation?: boolean;
}

/** Fill the form with real input events; nothing is submitted. */
async function fill(page: Page, f: Fill): Promise<void> {
  if (f.partition) await page.getByTestId(`entry-partition-${f.partition}`).check();
  if (f.kind) await page.getByTestId(`entry-kind-${f.kind}`).check();
  if (f.speaker !== undefined) await page.getByTestId('entry-speaker').fill(f.speaker);
  await page.getByTestId('human-input').fill(f.text);
  if (f.immediate) await page.getByTestId('entry-immediate').check();
  if (f.exclamation) await page.getByTestId('entry-exclamation').check();
}

async function write(page: Page, f: Fill): Promise<void> {
  await fill(page, f);
  await page.getByTestId('entry-submit').click();
  await expect(page.getByTestId('entry-result')).toBeVisible();
}

interface Rec {
  source_id: string;
  status: string;
  reason: string | null;
  immediate: boolean;
  confirm: boolean | null;
  exclamation: boolean;
  confirmed_by: string | null;
  source_ref: string | null;
  partition: string;
}
const records = (page: Page) => alpha<Rec[]>(page, 'inputs.list()');
const performing = async (page: Page) => {
  const s = await alpha<{ kind: string; partition?: string } | null>(page, 'brain.signal()');
  return s && s.kind === 'perform' ? s : null;
};
const themeName = (page: Page) => alpha<string>(page, 'themeName()');

const TEXT = '今天我真的很难过，也有点失望。';

test.beforeEach(async ({ page }) => {
  const errors: string[] = [];
  page.on('console', (m) => m.type() === 'error' && errors.push(m.text()));
  page.on('pageerror', (e) => errors.push(String(e)));
  (page as unknown as { __errors: string[] }).__errors = errors;
});

test.afterEach(async ({ page }) => {
  const errors = (page as unknown as { __errors: string[] }).__errors;
  expect(errors.filter((e) => !/WebGL|GL Driver|Download the React DevTools/.test(e))).toEqual([]);
});

test('entry — unconnected: banner, a draft can be written, but 写入 is disabled with the reason; the real button enters demo', async ({ page }) => {
  test.setTimeout(90_000);
  await atHuman(page);
  const panel = page.getByTestId('entry-panel');
  await expect(panel).toHaveClass(/human-panel__input/);
  await expect(page.getByTestId('backend-banner')).toContainText('后端未连接');
  await expect(page.getByTestId('entry-submit')).toBeDisabled();
  await expect(page.getByTestId('entry-reason')).toContainText('后端未连接');

  // a draft can be written (and is kept), but never sent
  await fill(page, { partition: 'rational', text: TEXT, immediate: true });
  await expect(page.getByTestId('entry-submit')).toBeDisabled();
  await page.getByTestId('human-input').press('Control+Enter');
  expect(await records(page)).toEqual([]);
  expect((await alpha<{ lastResult: unknown }>(page, 'inputs.state()')).lastResult).toBeNull();

  // the real banner button, not the inspector
  await page.getByTestId('backend-enter-demo').click();
  expect(await alpha(page, 'backend.mode()')).toBe('demo');
  await expect(page.getByTestId('backend-banner')).toContainText('演示数据 · 未运行模型');
  await expect(page.getByTestId('entry-reason')).toHaveCount(0);
  await expect(page.getByTestId('human-input')).toHaveValue(TEXT); // the draft survived
  await expect(page.getByTestId('entry-submit')).toBeEnabled();
});

test('entry — empty form: nothing is preselected, the judgement boxes start unchecked, the 癫狂 note is on the face', async ({ page }) => {
  test.setTimeout(90_000);
  await atHumanDemo(page);
  for (const p of ['rational', 'emotional', 'crazy']) await expect(page.getByTestId(`entry-partition-${p}`)).not.toBeChecked();
  await expect(page.getByTestId('entry-kind-diary')).toBeChecked();
  await expect(page.getByTestId('entry-immediate')).not.toBeChecked();
  await expect(page.getByTestId('entry-immediate')).toBeEnabled();
  await expect(page.getByTestId('entry-exclamation')).not.toBeChecked();
  await expect(page.getByTestId('entry-crazy-note')).toHaveText('癫狂：用户命名的情境状态，不是诊断');
  await expect(page.getByTestId('entry-exclamation-note')).toHaveText('仅当你强烈认同这是自己的想法：跳过大脑内的二次确认，直接用于训练');
  await expect(page.getByTestId('entry-count')).toHaveText('0 / 1,000,000');
  await expect(page.getByLabel('是否为真（当下）')).toBeVisible();
  await expect(page.getByTestId('entry-submit')).toBeDisabled();
  await expect(page.getByTestId('entry-validation-error')).toContainText(['请选择状态：理性、感性或癫狂', '内容不能为空']);

  // a state is required, and never guessed
  await page.getByTestId('human-input').fill('一句话。');
  await expect(page.getByTestId('entry-submit')).toBeDisabled();
  await page.getByTestId('entry-partition-crazy').check();
  await expect(page.getByTestId('entry-submit')).toBeEnabled();
  await expect(page.getByTestId('entry-count')).toHaveText('4 / 1,000,000');

  // code points, not UTF-16 units: an emoji counts once
  await page.getByTestId('human-input').fill('😀😀😀');
  await expect(page.getByTestId('entry-count')).toHaveText('3 / 1,000,000');
});

test('entry — rational + T (no exclamation) is pending: a hypothetical preview, evidence marked exactly even after an emoji; nothing trains', async ({ page }) => {
  test.setTimeout(90_000);
  await atHumanDemo(page);
  const text = `😀😀 ${TEXT}`;
  await write(page, { partition: 'rational', text, immediate: true });

  const result = page.getByTestId('entry-result');
  await expect(result).toHaveAttribute('data-status', 'pending');
  await expect(result).toHaveAttribute('data-partition', 'rational');
  await expect(result).toHaveAttribute('data-trained', 'false');
  await expect(page.getByTestId('entry-result-heading')).toBeFocused();
  await expect(page.getByTestId('entry-announce')).toContainText('待确认');
  await expect(page.getByTestId('status-chip')).toHaveText('待确认');
  await expect(page.getByTestId('entry-preview-note')).toHaveText('预览是假设值，可能过期；以确认后返回的正式结果为准');
  await expect(page.getByTestId('entry-pending-note')).toContainText('尚未用于训练：展开大脑，在右侧列表里再次判定 T/F 后才会训练');
  await expect(page.getByTestId('entry-open-brain')).toBeVisible();
  // the form collapsed to one line
  await expect(page.getByTestId('entry-form')).toHaveCount(0);
  await expect(page.getByTestId('entry-summary')).toContainText('理性');
  await expect(page.getByTestId('entry-summary')).toContainText('日记');

  // the preview: cues, the original text with the evidence marked, hypothetical effects
  await expect(page.getByTestId('effects-table')).toBeVisible();
  await expect(page.getByTestId('entry-cue').first()).toBeVisible();
  const rows = page.getByTestId('effect-row');
  const n = await rows.count();
  expect(n).toBeGreaterThan(0);
  await expect(page.getByTestId('effect-revision').first()).toContainText('预览 · 无修订号');
  await expect(page.getByTestId('effect-action').first()).toHaveText('预览');
  const evidence = await page.getByTestId('effect-evidence').allTextContents();
  const marks = page.getByTestId('hl-mark');
  await expect(marks).toHaveCount(n);
  const markTexts = await marks.allTextContents();
  expect([...markTexts].sort()).toEqual([...evidence].sort());
  // UTF-16 handling: the mark holds the code point slice, which a UTF-16 slice would miss by the emoji
  const cps = Array.from(text);
  for (let i = 0; i < n; i++) {
    const [s, e] = ((await marks.nth(i).getAttribute('data-span')) ?? '').split(',').map(Number);
    expect(s).toBeGreaterThanOrEqual(2);
    expect(cps.slice(s, e).join('')).toBe(markTexts[i]);
    expect(text.slice(s, e)).not.toBe(markTexts[i]);
  }
  // hovering a row lights its mark
  await rows.first().hover();
  await expect(marks.first()).toHaveClass(/is-active/);

  // nothing has trained; the brain did not perform
  const st = await alpha<{ lastResult: { previewState: string; trained: boolean } }>(page, 'inputs.state()');
  expect(st.lastResult).toMatchObject({ previewState: 'ready', trained: false });
  expect(await performing(page)).toBeNull();
  const [rec] = await records(page);
  expect(rec).toMatchObject({ status: 'pending', immediate: true, confirm: null, exclamation: false });
  expect(await alpha<unknown[]>(page, `inputs.call('loadEffects', '${rec.source_id}')`)).toEqual([]);

  // the button leads into the brain, where the list is
  await page.getByTestId('entry-open-brain').click();
  await expect.poll(async () => (await alpha<{ focused: boolean }>(page, 'humanUi()')).focused).toBe(true);
});

test('entry — T/F unchecked: saved as 不同意, no training, and no path to training is offered', async ({ page }) => {
  test.setTimeout(90_000);
  await atHumanDemo(page);
  await write(page, { partition: 'emotional', text: TEXT });
  const result = page.getByTestId('entry-result');
  await expect(result).toHaveAttribute('data-status', 'disagreed');
  await expect(page.getByTestId('status-chip')).toContainText('不同意');
  await expect(page.getByTestId('status-chip')).toHaveAttribute('data-reason', 'immediate_false');
  await expect(page.getByTestId('entry-saved-note')).toContainText('已保存，不用于训练（当下判断为否）。可在展开的大脑右侧列表里编辑或删除。');
  // the original is shown, but no preview, no cues, no effects, no "will train" wording
  await expect(page.getByTestId('hl-text')).toHaveText(TEXT);
  await expect(page.getByTestId('effects-table')).toHaveCount(0);
  await expect(page.getByTestId('entry-cue')).toHaveCount(0);
  await expect(page.getByTestId('entry-pending-note')).toHaveCount(0);
  await expect(page.getByTestId('entry-preview-note')).toHaveCount(0);

  const [rec] = await records(page);
  expect(rec).toMatchObject({ status: 'disagreed', reason: 'immediate_false', immediate: false, confirm: null, exclamation: false });
  // the model is unchanged: no effect was ever committed and the brain stayed still
  expect(await alpha<unknown[]>(page, `inputs.call('loadEffects', '${rec.source_id}')`)).toEqual([]);
  expect(await performing(page)).toBeNull();
});

test('entry — 断言为真: the immediate box is locked checked, unticking restores it, and the input is agreed at once with formal effects and a performance', async ({ page }) => {
  test.setTimeout(90_000);
  await atHumanDemo(page);
  const immediate = page.getByTestId('entry-immediate');
  const excl = page.getByTestId('entry-exclamation');

  // independent boxes: the exclamation does not need the immediate one; unticking gives the user's own choice back
  await excl.check();
  await expect(immediate).toBeChecked();
  await expect(immediate).toBeDisabled();
  await expect(page.getByTestId('entry-immediate-note')).toContainText('已由「断言为真」决定');
  await excl.uncheck();
  await expect(immediate).not.toBeChecked();
  await expect(immediate).toBeEnabled();
  await immediate.check();
  await excl.check();
  await expect(immediate).toBeChecked();
  await expect(immediate).toBeDisabled();
  await excl.uncheck();
  await expect(immediate).toBeChecked(); // the choice made before is what comes back
  await immediate.uncheck();

  // immediate was never ticked; the assertion alone makes it true
  await write(page, { partition: 'crazy', text: `😀 ${TEXT}`, exclamation: true });
  const result = page.getByTestId('entry-result');
  await expect(result).toHaveAttribute('data-status', 'agreed');
  await expect(result).toHaveAttribute('data-trained', 'true');
  await expect(page.getByTestId('status-chip')).toHaveText('已认可');
  // in demo mode the wording says it is not real training (D56)
  await expect(page.getByTestId('entry-trained-note')).toContainText('演示：已按你的断言标记为直接训练');
  await expect(page.getByTestId('entry-trained-note')).toContainText('不会真的训练');
  // formal effects: revision numbers, applied, no preview and no second confirmation
  await expect(page.getByTestId('effects-table')).toBeVisible();
  await expect(page.getByTestId('effect-revision').first()).toContainText(/#\d+/);
  await expect(page.getByTestId('effect-revision').first()).not.toContainText('预览');
  await expect(page.getByTestId('effect-action').first()).toHaveText('已应用');
  await expect(page.getByTestId('entry-preview-note')).toHaveCount(0);
  await expect(page.getByTestId('entry-pending-note')).toHaveCount(0);
  await expect(page.getByTestId('hl-mark').first()).toBeVisible();

  const [rec] = await records(page);
  expect(rec).toMatchObject({ status: 'agreed', immediate: true, confirm: true, exclamation: true, confirmed_by: 'exclamation' });
  // the brain answers in the input's own state
  expect(await performing(page)).toMatchObject({ kind: 'perform', partition: 'crazy' });
});

test('entry — the state changes the result and its mark', async ({ page }) => {
  test.setTimeout(90_000);
  await atHumanDemo(page);
  const colours: string[] = [];
  const labels = { rational: '理性', emotional: '感性', crazy: '癫狂' };
  for (const p of ['rational', 'emotional', 'crazy'] as const) {
    await write(page, { partition: p, text: TEXT });
    await expect(page.getByTestId('entry-result')).toHaveAttribute('data-partition', p);
    await expect(page.getByTestId('entry-result-partition')).toHaveText(labels[p]);
    colours.push(await page.getByTestId('entry-summary').locator('.state-dot').evaluate((el) => getComputedStyle(el).backgroundColor));
    await page.getByTestId('entry-again').click();
    await expect(page.getByTestId('entry-form')).toBeVisible();
    // the state, kind and speaker stay; the text and the judgements go
    await expect(page.getByTestId('human-input')).toHaveValue('');
    await expect(page.getByTestId(`entry-partition-${p}`)).toBeChecked();
  }
  expect(new Set(colours).size).toBe(3);
  expect((await records(page)).map((r) => r.partition)).toEqual(['crazy', 'emotional', 'rational']);
  // the choice marks differ as well (each state has its own colour)
  const ring = await page.getByTestId('entry-partition').locator('input').evaluateAll((els) => els.map((el) => getComputedStyle(el).borderTopColor));
  expect(new Set(ring).size).toBe(3);
});

test('entry — chat: the speaker is required, an unmatched one warns, a matched one is quiet; Enter is a newline, Ctrl+Enter writes', async ({ page }) => {
  test.setTimeout(90_000);
  await atHumanDemo(page);
  const chat = '小明: 你最近怎么样\n我: 今天很难过，也有点失望。\n小明: 抱抱你';
  await fill(page, { partition: 'emotional', kind: 'chat', text: chat });
  await expect(page.getByTestId('entry-speaker')).toBeVisible();
  await expect(page.getByText('每行「姓名: 内容」，只分析这位发言者')).toBeVisible();
  // blocked: no speaker
  await expect(page.getByTestId('entry-submit')).toBeDisabled();
  await expect(page.getByTestId('entry-validation-error')).toContainText('聊天记录必须指定“我”的发言者名称');

  // unmatched: a warning that predicts the back end, not a block
  await page.getByTestId('entry-speaker').fill('阿明');
  await expect(page.getByTestId('entry-submit')).toBeEnabled();
  await expect(page.getByTestId('entry-validation-warning')).toContainText('没有找到发言者「阿明」的行');

  // matched: quiet
  await page.getByTestId('entry-speaker').fill('我');
  await expect(page.getByTestId('entry-validation-warning')).toHaveCount(0);
  await expect(page.getByTestId('entry-validation-error')).toHaveCount(0);

  // Enter is a line break in the text; nothing is sent by it
  const input = page.getByTestId('human-input');
  await input.click();
  await page.keyboard.press('End');
  await page.keyboard.press('Enter');
  await page.keyboard.type('我: 好');
  await expect(input).toHaveValue(`${chat}\n我: 好`);
  expect(await records(page)).toEqual([]);
  // Ctrl+Enter writes
  await page.keyboard.press('Control+Enter');
  await expect(page.getByTestId('entry-result')).toBeVisible();
  const [rec] = await records(page);
  expect(rec).toMatchObject({ status: 'disagreed', partition: 'emotional' });
  expect(await alpha<{ detail: { text: string; self_speaker: string } }>(page, `inputs.get('${rec.source_id}').cache`)).toMatchObject({ detail: { text: `${chat}\n我: 好`, self_speaker: '我' } });
});

test('entry — files: a .txt fills the text and names its source; editing drops the name; bad files are refused in Chinese', async ({ page }) => {
  test.setTimeout(90_000);
  await atHumanDemo(page);
  const input = page.getByTestId('entry-file-input');
  const text = `😀 ${TEXT}\r\n第二行。`;

  const bom = Buffer.from([0xef, 0xbb, 0xbf]);
  await input.setInputFiles({ name: '日记.txt', mimeType: 'text/plain', buffer: Buffer.concat([bom, Buffer.from(text, 'utf8')]) });
  await expect(page.getByTestId('human-input')).toHaveValue(text.replace(/\r\n/g, '\n')); // the textarea API shows LF
  await expect(page.getByTestId('entry-file-name')).toHaveText(`来自 日记.txt · ${Array.from(text).length} 字符`);
  await expect(page.getByTestId('entry-count')).toHaveText(`${Array.from(text).length} / 1,000,000`);

  // a BOM is dropped, and what is sent is the file's own bytes (CRLF kept)
  await page.getByTestId('entry-partition-rational').check();
  await page.getByTestId('entry-submit').click();
  await expect(page.getByTestId('entry-result')).toBeVisible();
  const [rec] = await records(page);
  expect(rec.source_ref).toBe('日记.txt');
  const sent = await alpha<{ detail: { text: string } }>(page, `inputs.get('${rec.source_id}').cache`);
  expect(sent.detail.text).toBe(text);
  await page.getByTestId('entry-again').click();

  // bad files: nothing is filled, the reason is in Chinese
  await page.getByTestId('human-input').fill('草稿');
  await input.setInputFiles({ name: 'bad.txt', mimeType: 'text/plain', buffer: Buffer.from([0x66, 0xff, 0xfe, 0x67]) });
  await expect(page.getByTestId('entry-file-error')).toContainText('bad.txt');
  await expect(page.getByTestId('entry-file-error')).toContainText('UTF-8');
  await expect(page.getByTestId('human-input')).toHaveValue('草稿');
  await input.setInputFiles({ name: 'paper.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF-1.4') });
  await expect(page.getByTestId('entry-file-error')).toContainText('只能读取 .txt 或 .md 文件');
  await input.setInputFiles({ name: 'big.md', mimeType: 'text/markdown', buffer: Buffer.alloc(4_000_001, 0x61) });
  await expect(page.getByTestId('entry-file-error')).toContainText('超过');
  await expect(page.getByTestId('human-input')).toHaveValue('草稿');
  await expect(page.getByTestId('entry-file-name')).toHaveCount(0);

  // replacing a draft can be undone; typing afterwards drops the source name
  await input.setInputFiles({ name: 'note.md', mimeType: 'text/markdown', buffer: Buffer.from('# 标题\n今天很开心。', 'utf8') });
  await expect(page.getByTestId('entry-file-name')).toContainText('note.md');
  await expect(page.getByTestId('entry-file-error')).toHaveCount(0);
  await page.getByTestId('human-input').press('End');
  await page.keyboard.type('！');
  await expect(page.getByTestId('entry-file-name')).toHaveCount(0);
  await page.getByTestId('entry-file-undo').click();
  await expect(page.getByTestId('human-input')).toHaveValue('草稿');
});

test('entry — keys: T is text not a theme switch, Escape leaves the field first then closes the result; the draft survives drilling in', async ({ page }) => {
  test.setTimeout(90_000);
  await atHumanDemo(page, 'dark');
  const input = page.getByTestId('human-input');
  await input.click();
  await page.keyboard.type('tTt');
  await expect(input).toHaveValue('tTt');
  expect(await themeName(page)).toBe('dark');
  // a T that lands on one of the panel's own buttons is not a switch either
  await page.getByTestId('entry-file-button').focus();
  await page.keyboard.press('t');
  expect(await themeName(page)).toBe('dark');

  // Escape in a field with a draft only leaves the field: the destination stays
  await input.click();
  await page.keyboard.press('Escape');
  await expect(input).not.toBeFocused();
  expect(await alpha(page, 'state')).toBe('human');
  await expect(input).toHaveValue('tTt');

  // the draft survives going into the brain and back
  await page.getByTestId('brain-open').press('Enter');
  await expect.poll(async () => (await alpha<{ focused: boolean }>(page, 'humanUi()')).focused).toBe(true);
  await expect(page.getByTestId('entry-panel')).toHaveCount(0);
  await page.keyboard.press('Escape');
  await expect.poll(async () => (await alpha<{ focused: boolean }>(page, 'humanUi()')).focused).toBe(false);
  await expect(page.getByTestId('human-input')).toHaveValue('tTt');

  // result: focus on the heading, Escape closes it, the form is back with the text focused
  await write(page, { partition: 'rational', text: TEXT });
  await expect(page.getByTestId('entry-result-heading')).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(page.getByTestId('entry-result')).toHaveCount(0);
  expect(await alpha(page, 'state')).toBe('human');
  await expect(page.getByTestId('human-input')).toBeFocused();
  // and the 再写一份 button does the same
  await write(page, { partition: 'rational', text: TEXT });
  await page.getByTestId('entry-again').click();
  await expect(page.getByTestId('human-input')).toBeFocused();
});

test('entry — an error from the adapter is shown inline with its code and can be dismissed', async ({ page }) => {
  test.setTimeout(90_000);
  await atHumanDemo(page);
  // the same call the form makes, with an argument the back end refuses
  expect(await alpha(page, "inputs.call('submitInput', { text: 'x', partition: 'bogus', immediate: true })")).toBeNull();
  const err = page.getByTestId('entry-error');
  await expect(err).toBeVisible();
  await expect(err).toHaveAttribute('data-code', 'INVALID_ARGUMENT');
  await expect(page.getByTestId('entry-error-code')).toHaveText('INVALID_ARGUMENT');
  await expect(err).toContainText('无效的状态分区');
  await err.getByRole('button', { name: '关闭提示' }).click();
  await expect(err).toHaveCount(0);
});

test('entry — the panel stays above the divide line and scrolls inside at 1644x957 and 1280x800', async ({ page }) => {
  test.setTimeout(120_000);
  await atHumanDemo(page);
  const long = [
    '我很看重自由，我看重公平，我看重关怀，我看重真实，我看重安全，我看重成长，我看重成就，我看重陪伴。',
    '今天我很难过，也很失望，也有点开心，但是我生气。我想少联系他。',
  ].join('');
  const aboveLine = async (what: string) => {
    const vp = page.viewportSize()!;
    const box = (await page.getByTestId('entry-panel').boundingBox())!;
    // the divide line runs corner to corner; the panel's lower-left corner is what would cross it first
    expect(box.y + box.height, `${what}: bottom edge above the line at the panel's left edge`).toBeLessThanOrEqual((box.x * vp.height) / vp.width + 1);
    expect(box.x + box.width).toBeLessThanOrEqual(vp.width);
    expect(box.y).toBeGreaterThanOrEqual(0);
  };
  const submitVisible = async () => {
    const vp = page.viewportSize()!;
    const b = (await page.getByTestId('entry-submit').boundingBox())!;
    expect(b.y + b.height).toBeLessThanOrEqual(vp.height);
    await expect(page.getByTestId('entry-submit')).toBeInViewport();
  };

  for (const [w, h] of [[1644, 957], [1280, 800]] as const) {
    await page.setViewportSize({ width: w, height: h });
    await page.waitForTimeout(200);
    await page.getByTestId('entry-kind-chat').check(); // the tallest form
    await page.getByTestId('human-input').fill(long);
    await page.getByTestId('entry-partition-rational').check();
    await page.getByTestId('entry-speaker').fill('阿');
    await page.getByTestId('entry-immediate').check();
    await aboveLine(`form ${w}x${h}`);
    await submitVisible(); // 写入 never scrolls out of view
    await page.getByTestId('entry-kind-diary').check();
    await page.getByTestId('entry-submit').click();
    await expect(page.getByTestId('entry-result')).toBeVisible();
    await expect(page.getByTestId('effect-row').first()).toBeVisible();
    await aboveLine(`result ${w}x${h}`);
    // the result scrolls inside itself
    const s = await page.getByTestId('entry-result').evaluate((el) => ({ sh: el.scrollHeight, ch: el.clientHeight, ov: getComputedStyle(el).overflowY }));
    expect(s.ov).toBe('auto');
    if (w === 1280) expect(s.sh).toBeGreaterThan(s.ch);
    const scrolled = await page.getByTestId('entry-result').evaluate((el) => {
      el.scrollTop = el.scrollHeight;
      return el.scrollTop;
    });
    if (w === 1280) expect(scrolled).toBeGreaterThan(0);
    await aboveLine(`result scrolled ${w}x${h}`);
    await page.getByTestId('entry-again').click();
  }
});

test('entry — nothing leaves the machine: only same-origin dev-server requests', async ({ page }) => {
  test.setTimeout(90_000);
  const urls: string[] = [];
  page.on('request', (r) => urls.push(r.url()));
  await atHumanDemo(page);
  await write(page, { partition: 'rational', text: TEXT, immediate: true });
  await page.getByTestId('entry-again').click();
  await write(page, { partition: 'crazy', text: TEXT, exclamation: true });
  await page.getByTestId('entry-again').click();
  await page.getByTestId('entry-file-input').setInputFiles({ name: 'a.txt', mimeType: 'text/plain', buffer: Buffer.from('今天很开心。') });
  await expect(page.getByTestId('entry-file-name')).toBeVisible();
  const foreign = urls.filter((u) => !u.startsWith('http://127.0.0.1:5173/') && !u.startsWith('data:') && !u.startsWith('blob:'));
  expect(foreign).toEqual([]);
  // and the user's text is in no browser storage
  const stored = await page.evaluate(() => JSON.stringify([{ ...localStorage }, { ...sessionStorage }]));
  expect(stored).not.toContain('开心');
  expect(stored).not.toContain('难过');
});

test('entry — a pending result keeps its key message and 展开大脑 in view on a 1366x768 window, and fades when more is below (fix-ui)', async ({ page }) => {
  test.setTimeout(90_000);
  await page.setViewportSize({ width: 1366, height: 768 });
  await atHumanDemo(page);
  // a chat with several evidence rows: the result is taller than the panel
  const lines = ['我：我重视自由，也看重真实。', '她：你想好了吗', '我：今天我真的很难过，也有点失望。', '我：我珍惜陪伴，也重视公平。', '我：成长比成功重要，我很生气。'];
  await write(page, { partition: 'emotional', kind: 'chat', speaker: '我', text: lines.join('\n'), immediate: true });
  const result = page.getByTestId('entry-result');
  await expect(result).toHaveAttribute('data-status', 'pending');
  await expect(page.getByTestId('effect-row').first()).toBeVisible();

  // the note and the way on are inside the visible part of the scroll box, without scrolling
  const box = (await result.boundingBox())!;
  const note = (await page.getByTestId('entry-pending-note').boundingBox())!;
  const brain = (await page.getByTestId('entry-open-brain').boundingBox())!;
  expect(note.y).toBeGreaterThanOrEqual(box.y - 1);
  expect(brain.y + brain.height).toBeLessThanOrEqual(box.y + box.height + 1);
  expect(await result.evaluate((el) => el.scrollTop)).toBe(0);

  // when the result overflows, the bottom fades (a cue that there is more); at the end it does not
  const overflows = await result.evaluate((el) => el.scrollHeight > el.clientHeight + 6);
  if (overflows) {
    await expect(result).toHaveAttribute('data-more', 'true');
    await result.evaluate((el) => el.scrollTo(0, el.scrollHeight));
    await expect(result).not.toHaveAttribute('data-more', 'true');
  }
});
