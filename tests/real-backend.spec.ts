/**
 * Round 3 part 9c: the UI against the REAL Python back end (back-end-core,
 * `python -m core.api`, JSON lines), through the same code path the desktop app
 * uses: `window.__TAURI_INTERNALS__.invoke('brain_call', { request })` →
 * `createTauriTransport` → `RemoteBrainAdapter`.
 *
 * What is real here: the whole front end (entry form, preview, record list, state
 * tab, brain performance) and the whole Python back end (rules, SQLite, two
 * judgements). What is FAKE: the Rust host (`src-tauri`) and the WebKitGTK
 * window. A Node-side function stands in for `brain_call`: it writes one request
 * line to a spawned Python process (fixed arguments like the host's:
 * `python -E -s -u -m core.api --db <temp db>`, cwd back-end-core) and returns
 * the response line. So this proves the front-end ↔ back-end contract, NOT the
 * native desktop acceptance (docs/DESKTOP_CHECK.md): that still has to be run on
 * the real window.
 *
 * Every test uses its own temporary database (never back-end-core/data) and
 * deletes it afterwards. Skipped when python3 or back-end-core is missing.
 */

import { spawn, spawnSync, type ChildProcessWithoutNullStreams } from 'node:child_process';
import { existsSync, mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { createInterface } from 'node:readline';

import { expect, test, type Page } from '@playwright/test';

const BACKEND = resolve(process.cwd(), 'back-end-core');
const haveBackend = existsSync(join(BACKEND, 'core', 'api.py')) && spawnSync('python3', ['--version']).status === 0;

test.skip(!haveBackend, 'python3 or back-end-core/core/api.py is not available');

interface Bridge {
  child: ChildProcessWithoutNullStreams;
  dir: string;
  /** Every request envelope the page sent, in order. */
  seen: { method: string; params: Record<string, unknown>; id: string }[];
  call(request: unknown): Promise<unknown>;
  close(): void;
}

/** A Python back end on a throw-away database, and a one-request-at-a-time exchange with it. */
function startBackend(): Bridge {
  const dir = mkdtempSync(join(tmpdir(), 'alpha-real-backend-'));
  const child = spawn('python3', ['-E', '-s', '-u', '-m', 'core.api', '--db', join(dir, 'brain.sqlite3')], {
    cwd: BACKEND,
    env: { ...process.env, PYTHONDONTWRITEBYTECODE: '1' },
    stdio: ['pipe', 'pipe', 'pipe'],
  });
  child.stderr.resume(); // drained and dropped, as the host does
  const lines = createInterface({ input: child.stdout });
  const waiting: ((line: string) => void)[] = [];
  lines.on('line', (line) => waiting.shift()?.(line));
  // the host runs requests one at a time: so does this
  let tail: Promise<unknown> = Promise.resolve();
  const bridge: Bridge = {
    child,
    dir,
    seen: [],
    call(request) {
      const run = async () => {
        const r = request as { id: string; method: string; params: Record<string, unknown> };
        bridge.seen.push({ method: r.method, params: r.params, id: r.id });
        const reply = new Promise<string>((ok) => waiting.push(ok));
        child.stdin.write(`${JSON.stringify(request)}\n`);
        return JSON.parse(await reply);
      };
      const result = tail.then(run, run);
      tail = result.catch(() => undefined);
      return result;
    },
    close() {
      child.stdin.end();
      child.kill();
      rmSync(dir, { recursive: true, force: true });
    },
  };
  return bridge;
}

const alpha = <T,>(page: Page, expr: string) => page.evaluate(`window.__alpha.${expr}`) as Promise<T>;

/** Make the page look like the Tauri webview: the global the transport looks for, answered by Python. */
async function asDesktop(page: Page, bridge: Bridge): Promise<void> {
  await page.exposeFunction('__brainCall', (request: unknown) => bridge.call(request));
  await page.addInitScript(() => {
    (window as unknown as { __TAURI_INTERNALS__: unknown }).__TAURI_INTERNALS__ = {
      invoke: (command: string, args: { request: unknown }) =>
        command === 'brain_call'
          ? (window as unknown as { __brainCall: (r: unknown) => Promise<unknown> }).__brainCall(args.request)
          : Promise.reject(new Error(`command ${command} not allowed`)),
    };
  });
}

async function atHuman(page: Page): Promise<void> {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/?theme=light');
  await expect.poll(() => alpha<string>(page, 'state'), { timeout: 60_000 }).toBe('home');
  await alpha(page, "navigate('human')");
  await expect.poll(() => alpha<string>(page, 'state'), { timeout: 15_000 }).toBe('human');
  await alpha(page, 'setTimeScale(0)');
  // no button was pressed: the app connected by itself, because a Tauri host exists
  await expect(page.getByTestId('backend-banner')).toHaveAttribute('data-mode', 'remote', { timeout: 20_000 });
}

async function drill(page: Page): Promise<void> {
  const c = await alpha<[number, number] | null>(page, 'brain.screenOf()');
  await page.mouse.click(c![0], c![1]);
  await expect(page.getByTestId('records-panel')).toBeVisible({ timeout: 15_000 });
}

interface Fill {
  partition: 'rational' | 'emotional' | 'crazy';
  text: string;
  kind?: 'diary' | 'chat' | 'philosophy';
  speaker?: string;
  immediate?: boolean;
  exclamation?: boolean;
}
async function write(page: Page, f: Fill): Promise<void> {
  await page.getByTestId(`entry-partition-${f.partition}`).check();
  if (f.kind) await page.getByTestId(`entry-kind-${f.kind}`).check();
  if (f.speaker !== undefined) await page.getByTestId('entry-speaker').fill(f.speaker);
  await page.getByTestId('human-input').fill(f.text);
  if (f.immediate) await page.getByTestId('entry-immediate').check();
  if (f.exclamation) await page.getByTestId('entry-exclamation').check();
  await page.getByTestId('entry-submit').click();
  await expect(page.getByTestId('entry-result')).toBeVisible({ timeout: 20_000 });
}

interface Rec {
  source_id: string;
  status: string;
  reason: string | null;
  immediate: boolean;
  confirm: boolean | null;
  exclamation: boolean;
  confirmed_by: string | null;
}

let bridge: Bridge;
test.beforeEach(async ({ page }) => {
  bridge = startBackend();
  await asDesktop(page, bridge);
  const errors: string[] = [];
  page.on('console', (m) => m.type() === 'error' && errors.push(m.text()));
  page.on('pageerror', (e) => errors.push(String(e)));
  (page as unknown as { __errors: string[] }).__errors = errors;
});
test.afterEach(async ({ page }) => {
  bridge.close();
  const errors = (page as unknown as { __errors: string[] }).__errors;
  expect(errors.filter((e) => !/WebGL|GL Driver|Download the React DevTools/.test(e))).toEqual([]);
});

const FAIR = '我重视自由。我看重真实。';

test('real back end — the app connects by itself, nothing is labelled demo, and the first request is a health probe', async ({ page }) => {
  test.setTimeout(120_000);
  await atHuman(page);
  const banner = page.getByTestId('backend-banner');
  await expect(banner).not.toContainText('演示数据');
  expect(bridge.seen[0].method).toBe('health');
  // the entry form is usable without ever entering demo
  await expect(page.getByTestId('entry-reason')).toHaveCount(0);
  await expect(page.getByTestId('backend-enter-demo')).toHaveCount(0);
});

test('real back end — submit, preview with the real rules, confirm in the brain, state, revoke; edit and delete are greyed out', async ({ page }) => {
  test.setTimeout(240_000);
  await atHuman(page);

  // 1. submit with immediate true: pending, the real preview (no mock rules, no 演示 tag)
  await write(page, { partition: 'rational', text: FAIR, kind: 'philosophy', immediate: true });
  await expect(page.getByTestId('entry-pending-note')).toBeVisible();
  const previewText = await page.getByTestId('entry-result').innerText();
  expect(previewText).not.toContain('mock.');
  expect(previewText).not.toContain('演示');
  await expect(page.getByTestId('effect-row')).toHaveCount(2);

  // the record exists on the back end with the two judgements
  const [rec] = await alpha<Rec[]>(page, 'inputs.list()');
  expect([rec.status, rec.immediate, rec.confirm, rec.exclamation]).toEqual(['pending', true, null, false]);

  // 2. drill in, confirm T: the formal effects carry revisions, the brain answers in its state
  await drill(page);
  const row = page.locator(`[data-testid="record-row"][data-id="${rec.source_id}"]`);
  await row.getByTestId('record-head').click();
  await row.getByTestId('act-confirm-true').click();
  await expect(row).toHaveAttribute('data-status', 'agreed', { timeout: 20_000 });
  const revs = await row.getByTestId('effect-revision').allTextContents();
  expect(revs.length).toBe(2);
  for (const r of revs) expect(r).toMatch(/修订 #\d+/);
  const sig = await alpha<{ kind: string; partition?: string } | null>(page, 'brain.signal()');
  expect(sig?.kind).toBe('perform');
  expect(sig?.partition).toBe('rational');

  // 3. the state tab shows the real numbers: net / (support + 4)
  await page.getByTestId('tab-state').click();
  const autonomy = page.locator('[data-testid="state-param"][data-partition="rational"][data-parameter="value.autonomy"]');
  await expect(autonomy).toHaveAttribute('data-observed', 'true');
  await expect(autonomy.locator('.ev__num')).toHaveText('0.2');
  await expect(page.locator('[data-testid="state-param"][data-partition="emotional"][data-parameter="value.autonomy"]')).toHaveAttribute('data-observed', 'false');
  await page.getByTestId('tab-records').click();

  // 4. revoke: not observed again
  await row.getByTestId('act-revoke').click();
  await expect(row).toHaveAttribute('data-status', 'revoked', { timeout: 20_000 });
  await page.getByTestId('tab-state').click();
  await expect(autonomy).toHaveAttribute('data-observed', 'false');
  await page.getByTestId('tab-records').click();
});

test('real back end — F3: exclamation trains at once and shows the formal effects; immediate F saves without training', async ({ page }) => {
  test.setTimeout(180_000);
  await atHuman(page);

  await write(page, { partition: 'emotional', text: '今天我真的很难过，也有点失望。', exclamation: true });
  await expect(page.getByTestId('entry-trained-note')).toBeVisible();
  const revs = await page.getByTestId('effect-revision').allTextContents();
  expect(revs.length).toBe(2);
  for (const r of revs) expect(r).toMatch(/修订 #\d+/);
  expect(await page.getByTestId('effect-row').count()).toBe(2);
  const sig = await alpha<{ kind: string; partition?: string } | null>(page, 'brain.signal()');
  expect(sig?.partition).toBe('emotional');
  // the request carried exactly the api.md fields (+ the two judgement fields the probe enabled)
  const submit = bridge.seen.filter((s) => s.method === 'submit').at(-1)!;
  expect(Object.keys(submit.params).sort()).toEqual(['exclamation', 'immediate', 'kind', 'partition', 'text']);
  expect(submit.params.exclamation).toBe(true);
  // exclamation is a submit that trained: the front end must not have asked for a preview of it
  expect(bridge.seen.map((s) => s.method)).not.toContain('preview');

  await page.getByTestId('entry-again').click();
  await write(page, { partition: 'rational', text: '我觉得成长比成功重要。', immediate: false });
  await expect(page.getByTestId('entry-saved-note')).toBeVisible();
  const recs = await alpha<Rec[]>(page, 'inputs.list()');
  const saved = recs.find((r) => r.status === 'disagreed')!;
  expect([saved.reason, saved.immediate, saved.confirm]).toEqual(['immediate_false', false, null]);
  // nothing of it trained: rational is still unobserved
  const state = (await bridge.call({ schema_version: 1, id: 'check-state', method: 'state', params: { partition: 'rational' } })) as {
    result: Record<string, { observed: boolean }>;
  };
  expect(Object.values(state.result).some((p) => p.observed)).toBe(false);
});

test('real back end — what the basic rules withhold is shown, with the reason, and a question trains nothing', async ({ page }) => {
  test.setTimeout(120_000);
  await atHuman(page);
  await write(page, { partition: 'rational', text: '我重视公平吗？“我重视自由。”', immediate: true });
  const notes = page.getByTestId('withheld-notes');
  await expect(notes).toBeVisible();
  const reasons = await notes.getByTestId('withheld-reason').allTextContents();
  expect(reasons).toEqual(expect.arrayContaining(['疑问句', '引号里的话']));
  await expect(page.getByTestId('effect-row')).toHaveCount(0);
  await expect(page.getByTestId('entry-result')).toContainText('未提取到可拟合的证据');
});

test('real back end — chat only reads the named speaker, and a span after an emoji highlights the exact evidence', async ({ page }) => {
  test.setTimeout(180_000);
  await atHuman(page);
  const text = '😀😀 她: 我重视安全。\n我: 我重视自由。\n她: 我重视成就。'; // the first line has an emoji before its colon, so it is not a chat line at all
  await write(page, { partition: 'rational', text, kind: 'chat', speaker: '我', immediate: true });
  // the preview loads after the write: wait for it. Only the named speaker's line counts.
  await expect(page.getByTestId('effect-row')).toHaveCount(1, { timeout: 20_000 });
  await expect(page.getByTestId('effect-row').first()).toContainText('value.autonomy');
  // the highlighted text is exactly the back end's evidence, found through the code point span
  const marks = await page.getByTestId('entry-result-text').locator('mark').allTextContents();
  const evidence = await page.getByTestId('effect-evidence').first().innerText();
  expect(marks.join('')).toBe(evidence.trim());
});

test('real back end — every request stays inside api.md: known methods, known fields, unique ids', async ({ page }) => {
  test.setTimeout(240_000);
  await atHuman(page);
  await write(page, { partition: 'rational', text: FAIR, kind: 'philosophy', immediate: true });
  await drill(page);
  const rec = (await alpha<Rec[]>(page, 'inputs.list()'))[0];
  const row = page.locator(`[data-testid="record-row"][data-id="${rec.source_id}"]`);
  await row.getByTestId('record-head').click();
  await row.getByTestId('act-confirm-false').click();
  await expect(row).toHaveAttribute('data-status', 'disagreed', { timeout: 20_000 });
  // edit and delete: present but not offered by this back end, and never sent
  await expect(row.getByTestId('record-unsupported')).toContainText('后端暂不支持');
  await expect(row.getByTestId('act-edit')).toBeDisabled();
  await expect(row.getByTestId('act-delete')).toBeDisabled();
  // F4: re-judging a confirm-false record to T works on the real back end
  await row.getByTestId('act-rejudge').click();
  await expect(row).toHaveAttribute('data-status', 'agreed', { timeout: 20_000 });

  const health = (await bridge.call({ schema_version: 1, id: 'check-health', method: 'health', params: {} })) as { result: { methods: string[] } };
  const known = new Set(health.result.methods);
  const ids = new Set<string>();
  for (const s of bridge.seen) {
    if (s.id.startsWith('check-')) continue;
    expect(known.has(s.method), s.method).toBe(true);
    expect(s.method).not.toMatch(/edit|delete/);
    expect(ids.has(s.id), `duplicate id ${s.id}`).toBe(false);
    ids.add(s.id);
  }
  expect(bridge.seen.map((s) => s.method)).toEqual(expect.arrayContaining(['health', 'submit', 'preview', 'review', 'input_page']));
});
