/**
 * The adapter layer (src/backend, D54–D56), tested in plain Node: no page, no
 * dev server needed. Only the pure modules are imported (spans, text, mock,
 * remote, unavailable); `index.ts` and `store.ts` need React.
 *
 * Covers: spans over astral characters / CRLF / lone surrogates, the invariant
 * `evidence === codePointSlice(text, span)` for everything the mock emits, the
 * two-judgement state machine (mirroring engine.py: exclamation sets both true,
 * re-judging, restore of the frozen fit, no-op repeats) and the training gate,
 * `inputPage`, the remote adapter against a fake transport and its `probe`, the
 * Tauri `brain_call` shim against a fake `window.__TAURI_INTERNALS__`,
 * `backendStore.connectDesktopBackend`, the REAL Python back end through a
 * spawn-based Transport (skipped when python3 or back-end-core is unavailable),
 * `.txt` / `.md` reading, and `validateEntry`.
 */

import { spawn, spawnSync } from 'node:child_process';
import { existsSync, mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { expect, test } from '@playwright/test';
import { MockBrainAdapter, PORTED_PATTERNS, mockExtract, mockTranslate } from '../src/backend/mock';
import { RemoteBrainAdapter } from '../src/backend/remote';
import type { RequestEnvelope, ResponseEnvelope, Transport } from '../src/backend/remote';
import { backendStore } from '../src/backend/store';
import { BRAIN_COMMAND, createTauriTransport, unavailableEnvelope } from '../src/backend/tauriTransport';
import {
  CodePointIndex,
  codePointLength,
  codePointOffsetOfUtf16,
  codePointSlice,
  evidenceMatches,
  hasLoneSurrogate,
  highlight,
} from '../src/backend/spans';
import { MAX_FILE_BYTES, PY_WS, isBlank, isPyWhitespace, hasNul, normalizeForSubmit, pyLstrip, pyStrip, readTextFile, splitLines, validateEntry } from '../src/backend/text';
import {
  ADAPTER_METHODS,
  BACKEND_ERROR_CODES,
  BackendError,
  MAX_INPUT_CHARS,
  MOCK_RULE_PREFIX,
  PARAMETER_IDS,
  effectiveJudgement,
  isTrainable,
} from '../src/backend/types';
import type { BrainAdapter, InputRecord, ModelState, Translation } from '../src/backend/types';
import { UnavailableAdapter } from '../src/backend/unavailable';
import { langStore } from '../src/i18n/lang';

// the checks below were written against the Chinese wording
langStore.set('zh');

const RARE = '\u{20BB7}'; // 𠮷, one code point, two UTF-16 units
const EMOJI = '\u{1F600}';

async function codeOf(p: Promise<unknown>): Promise<string> {
  try {
    await p;
  } catch (e) {
    if (e instanceof BackendError) return e.code;
    throw e;
  }
  return 'RESOLVED';
}

// ---- spans ------------------------------------------------------------------------------

test.describe('spans', () => {
  test('code point length and slicing with astral characters', () => {
    const text = `${EMOJI}我${RARE}重视公平`;
    expect(text.length).toBe(9);
    expect(codePointLength(text)).toBe(7);
    expect(codePointSlice(text, [3, 7])).toBe('重视公平');
    // The naive slice is wrong: that is the bug this file exists to prevent.
    expect(text.slice(3, 7)).not.toBe('重视公平');
    expect(codePointSlice(text, [0, 1])).toBe(EMOJI);
    expect(codePointSlice(text, [2, 3])).toBe(RARE);
  });

  test('invalid spans slice to the empty string and never throw', () => {
    expect(codePointSlice('abc', [2, 2])).toBe('');
    expect(codePointSlice('abc', [3, 2])).toBe('');
    expect(codePointSlice('abc', [0, 4])).toBe('');
    expect(codePointSlice('abc', [-1, 2])).toBe('');
    expect(codePointSlice('abc', [0.5, 2])).toBe('');
    expect(codePointSlice('', [0, 1])).toBe('');
  });

  test('index maps both ways, O(1) forward, and floors an index inside a pair', () => {
    const text = `a${EMOJI}b${RARE}c`;
    const ix = new CodePointIndex(text);
    expect(ix.length).toBe(5);
    expect([0, 1, 2, 3, 4, 5].map((k) => ix.toUtf16(k))).toEqual([0, 1, 3, 4, 6, 7]);
    expect([0, 1, 2, 3, 4, 5, 6, 7].map((i) => ix.fromUtf16(i))).toEqual([0, 1, 1, 2, 3, 3, 4, 5]);
    expect(codePointOffsetOfUtf16(text, 4)).toBe(3);
    expect(codePointOffsetOfUtf16(text, 99)).toBe(5);
    expect(codePointOffsetOfUtf16(text, -3)).toBe(0);
    // Pure BMP text is the identity.
    const bmp = new CodePointIndex('你好');
    expect(bmp.toUtf16(1)).toBe(1);
    expect(bmp.fromUtf16(2)).toBe(2);
  });

  test('a large astral text stays correct', () => {
    const text = EMOJI.repeat(100_000) + 'X' + RARE.repeat(10);
    expect(codePointLength(text)).toBe(100_011);
    expect(codePointSlice(text, [100_000, 100_001])).toBe('X');
    expect(codePointSlice(text, [100_001, 100_003])).toBe(RARE + RARE);
  });

  test('CRLF counts as two code points and is kept', () => {
    const text = 'a\r\n我重视公平';
    expect(codePointLength(text)).toBe(8);
    expect(codePointSlice(text, [3, 8])).toBe('我重视公平');
    expect(splitLines(text).map((l) => l.bare)).toEqual(['a', '我重视公平']);
  });

  test('lone surrogates count as one code point and are detected', () => {
    const lone = `a\ud83db${'\ude00'}c`; // high surrogate, b, low surrogate: neither is paired
    expect(hasLoneSurrogate(lone)).toBe(true);
    expect(hasLoneSurrogate(`a${EMOJI}b`)).toBe(false);
    expect(codePointLength(lone)).toBe(5);
    expect(codePointSlice(lone, [1, 4])).toBe('\ud83db\ude00');
    expect(codePointSlice(lone, [2, 3])).toBe('b');
    expect(new CodePointIndex(lone).fromUtf16(3)).toBe(3);
    // A trailing lone high surrogate must not run past the end.
    expect(codePointLength('x\ud83d')).toBe(2);
    expect(codePointSlice('x\ud83d', [1, 2])).toBe('\ud83d');
  });

  test('highlight merges overlapping and touching spans and reports ids', () => {
    const text = `${EMOJI}0123456789`; // code points 0..10
    const segs = highlight(text, [[2, 4], [3, 6], [6, 8], [9, 10]]);
    expect(segs.map((s) => [s.text, s.marked, s.spanIds])).toEqual([
      [`${EMOJI}0`, false, []],
      ['123456', true, [0, 1, 2]],
      ['7', false, []],
      ['8', true, [3]],
      ['9', false, []],
    ]);
    expect(segs.map((s) => [s.start, s.end])).toEqual([[0, 2], [2, 8], [8, 9], [9, 10], [10, 11]]);
    expect(segs.map((s) => s.text).join('')).toBe(text);
  });

  test('highlight clamps, drops invalid spans, accepts named spans', () => {
    const text = 'abcdef';
    const segs = highlight(text, [
      { span: [4, 99], id: 'tail' },
      [3, 3], // empty
      [5, 2], // inverted
      [-5, 1], // clamped to [0,1]
      [10, 12], // outside
      [1.5, 3], // not integers
      { span: [2, 3], id: 'mid' },
    ]);
    expect(segs.map((s) => [s.text, s.marked, s.spanIds])).toEqual([
      ['a', true, [3]],
      ['b', false, []],
      ['c', true, ['mid']],
      ['d', false, []],
      ['ef', true, ['tail']],
    ]);
    expect(highlight('', [[0, 1]])).toEqual([]);
    expect(highlight('abc', [])).toEqual([{ text: 'abc', marked: false, spanIds: [], start: 0, end: 3 }]);
  });

  test('highlight cuts on code points, never inside a pair', () => {
    const text = `${RARE}${RARE}${RARE}`;
    const segs = highlight(text, [[1, 2]]);
    expect(segs.map((s) => s.text)).toEqual([RARE, RARE, RARE]);
    expect(segs.map((s) => s.marked)).toEqual([false, true, false]);
  });

  test('evidenceMatches verifies the back end claim', () => {
    const text = `${EMOJI}我重视公平`;
    expect(evidenceMatches(text, { span: [1, 6], evidence: '我重视公平' })).toBe(true);
    expect(evidenceMatches(text, { span: [2, 7], evidence: '我重视公平' })).toBe(false);
    // The UTF-16 reading of the same span disagrees, which is what the check catches.
    expect(text.slice(1, 6)).not.toBe('我重视公平');
    expect(evidenceMatches(text, { span: [1, 99], evidence: '我重视公平' })).toBe(false);
    expect(evidenceMatches(text, { span: [3, 3], evidence: '' })).toBe(false);
  });
});

// ---- mock: extraction invariants ---------------------------------------------------------

const SAMPLES: { name: string; text: string; kind: 'diary' | 'chat' | 'philosophy'; self?: string; expect: string[] }[] = [
  { name: 'diary with emoji first', text: `${EMOJI}今天我重视公平。我很难过。`, kind: 'diary', expect: ['value.fairness', 'affect.sadness'] },
  { name: 'diary CRLF with rare CJK', text: `第${RARE}行\r\n我重视自由。\r\n我很开心`, kind: 'diary', expect: ['value.autonomy', 'affect.happiness'] },
  {
    name: 'chat with emoji, CRLF, other speaker and an unlabeled line',
    text: `我: ${EMOJI} 我重视自由\r\n他: 我不重视公平\r\n随便一行\r\n我：今天我很难过\r\n`,
    kind: 'chat',
    self: '我',
    expect: ['value.autonomy', 'affect.sadness'],
  },
  { name: 'philosophy normative', text: `${RARE}${RARE}人应该诚实。`, kind: 'philosophy', expect: ['value.truth'] },
  { name: 'reduced contact intention', text: `${EMOJI}这周我不想主动联系他。`, kind: 'diary', expect: ['expression.less_initiative'] },
  { name: 'nothing to extract', text: `${EMOJI}今天下雨了，去了图书馆。`, kind: 'diary', expect: [] },
];

test.describe('mock extraction', () => {
  for (const s of SAMPLES) {
    test(`evidence equals the code point slice of its span: ${s.name}`, async () => {
      const m = new MockBrainAdapter();
      const pending = await m.submit({ text: s.text, partition: 'emotional', kind: s.kind, self_speaker: s.self, immediate: true });
      const preview = await m.preview(pending.source_id);
      expect(preview.effects.map((e) => e.parameter).sort()).toEqual([...s.expect].sort());
      for (const e of preview.effects) {
        expect(e.evidence).toBe(codePointSlice(s.text, e.span));
        expect(evidenceMatches(s.text, e)).toBe(true);
        expect(e.rule_id.startsWith(MOCK_RULE_PREFIX)).toBe(true);
        expect(e.revision).toBeUndefined();
        expect(e.action).toBe('preview');
      }
      const t: Translation = preview.translation;
      for (const c of [...t.cues, ...t.candidates]) expect(codePointSlice(s.text, c.span)).toBe(c.evidence);
      for (const k of t.skipped) expect(codePointSlice(s.text, k.span).length).toBeGreaterThan(0);
      expect(t.limitations).toContain('mock_rules_only');

      // The same holds for the formal effects of an approval and for the log.
      const review = await m.confirm(pending.source_id, true);
      for (const e of [...review.effects, ...(await m.effects(pending.source_id))]) {
        expect(e.evidence).toBe(codePointSlice(s.text, e.span));
        expect(e.action).toBe('approve');
        expect(typeof e.revision).toBe('number');
      }
    });
  }

  test('chat: only the self speaker counts, unlabeled lines are reported as skipped', async () => {
    const text = `我: ${EMOJI} 我重视自由\r\n他: 我不重视公平\r\n随便一行\r\n我：今天我很难过\r\n`;
    const m = new MockBrainAdapter();
    const { source_id } = await m.submit({ text, partition: 'rational', kind: 'chat', self_speaker: '我', immediate: true });
    const preview = await m.preview(source_id);
    const fairness = preview.effects.find((e) => e.parameter === 'value.fairness');
    expect(fairness).toBeUndefined();
    const autonomy = preview.effects.find((e) => e.parameter === 'value.autonomy');
    expect(autonomy?.evidence).toBe(`${EMOJI} 我重视自由`);
    expect(preview.translation.skipped.map((k) => codePointSlice(text, k.span))).toEqual(['随便一行']);
    // A different self speaker sees a different set of lines.
    expect(mockExtract(text, 'chat', '他').map((c) => [c.parameter, c.sign])).toEqual([['value.fairness', -1]]);
  });

  test('negative importance is a negative contribution, once per parameter, and topics alone do not count', () => {
    const neg = mockExtract('我不重视安全。', 'philosophy', null);
    expect(neg.map((c) => [c.parameter, c.sign, c.rule_id])).toEqual([['value.security', -1, 'mock.negated_value_statement']]);
    // Repeated mention: one contribution.
    expect(mockExtract('我重视公平。我坚持公平。', 'diary', null)).toHaveLength(1);
    // Contradiction in one source moves nothing.
    expect(mockExtract('我重视公平。我不重视公平。', 'diary', null)).toEqual([]);
    // A diary topic mention is not an endorsement; philosophy without wording is not either.
    expect(mockExtract('今天讨论了公平和自由。', 'diary', null)).toEqual([]);
    expect(mockExtract('今天讨论了公平和自由。', 'philosophy', null)).toEqual([]);
    // Negated and reported emotions are not the writer's.
    expect(mockExtract('我不难过。', 'diary', null)).toEqual([]);
    expect(mockExtract('他很难过。', 'diary', null)).toEqual([]);
  });

  test('score is net / (support + 4), per partition, with before/after and monotonic revisions', async () => {
    const m = new MockBrainAdapter();
    const a = await m.submit({ text: '我重视公平。', partition: 'rational', kind: 'philosophy', immediate: true, exclamation: true });
    const b = await m.submit({ text: '我重视公平。', partition: 'rational', kind: 'philosophy', immediate: true, exclamation: true });
    const c = await m.submit({ text: '我重视公平。', partition: 'crazy', kind: 'philosophy', immediate: true, exclamation: true });
    const first = a.effects![0];
    const second = b.effects![0];
    expect([first.before, first.after, first.support_before, first.support_after]).toEqual([0, 1 / 5, 0, 1]);
    expect([second.before, second.after, second.support_before, second.support_after]).toEqual([1 / 5, 2 / 6, 1, 2]);
    expect(second.delta).toBeCloseTo(2 / 6 - 1 / 5, 12);
    expect(c.effects![0].partition).toBe('crazy');
    expect(c.effects![0].support_after).toBe(1);
    const revisions = (await m.effects()).map((e) => e.revision as number);
    expect(revisions).toEqual([1, 2, 3]);
    const state = await m.state();
    expect(state.rational['value.fairness']).toEqual({ value: 2 / 6, support: 2, observed: true });
    expect(state.emotional['value.fairness']).toEqual({ value: 0, support: 0, observed: false });
    expect(state.crazy['value.fairness'].support).toBe(1);
  });

  test('mock identity: never trains, labelled, deterministic ids and clock', async () => {
    const m = new MockBrainAdapter({ now: () => '2026-01-01T00:00:00.000Z' });
    expect(m.info).toEqual({ kind: 'mock', label: '演示数据 · 未运行模型', trains: false });
    const a = await m.submit({ text: 'x', partition: 'rational', immediate: true });
    const b = await m.submit({ text: 'y', partition: 'rational', immediate: true });
    expect([a.source_id, b.source_id]).toEqual(['mock-0001', 'mock-0002']);
    expect((await m.inputGet('mock-0001')).created_at).toBe('2026-01-01T00:00:00.000Z');
    expect([...(await m.capabilities())].sort()).toEqual(
      ['confirm', 'effects', 'inputDelete', 'inputEdit', 'inputGet', 'inputList', 'inputPage', 'modelReset', 'preview', 'rank', 'revoke', 'state', 'submit'],
    );
  });

  test('rank abstains without evidence and is provisional with it', async () => {
    const m = new MockBrainAdapter();
    const options = [
      { id: 'A', impacts: { 'value.fairness': 0.5 } },
      { id: 'B', impacts: { 'value.fairness': -0.5 } },
    ];
    expect((await m.rank(options)).status).toBe('abstain');
    for (let i = 0; i < 2; i++) await m.submit({ text: '我重视公平。', partition: 'rational', kind: 'philosophy', immediate: true, exclamation: true });
    const r = await m.rank(options);
    expect(r.status).toBe('provisional');
    if (r.status === 'provisional') expect(r.ranked.map((x) => x.id)).toEqual(['A', 'B']);
    expect(await codeOf(m.rank([{ id: 'A', impacts: {} }]))).toBe('INVALID_ARGUMENT');
    expect(await codeOf(m.rank([{ id: 'A', impacts: { 'affect.anger': 1 } }, { id: 'B', impacts: {} }]))).toBe('INVALID_ARGUMENT');
  });
});

/**
 * Golden output of the real Python rules (`model.evidence.extract_contributions`
 * and `translator.translate`, back-end-core as of 2026-09-30), run once on
 * these texts. The mock is a port, so it must agree exactly on them; when the
 * back end's rules change this table is stale, not the mock wrong, and the
 * mock (a demo) is only expected to stay close, so refresh both together.
 */
const PY_GOLDEN: { text: string; kind: 'diary' | 'chat' | 'philosophy'; self: string | null; contrib: [string, number, string, number, number, string][]; cues: [string, number[]][]; skipped: number[][] }[] = [
  { text: "\ud83d\ude00\u4eca\u5929\u6211\u91cd\u89c6\u516c\u5e73\u3002\u6211\u5f88\u96be\u8fc7\u3002", kind: "diary", self: null,
    contrib: [["value.fairness", 1, "😀今天我重视公平", 0, 8, "explicit_value_statement"], ["affect.sadness", 1, "难过", 11, 13, "textual_emotion_cue"]],
    cues: [["sadness", [11, 13]]],
    skipped: [] },
  { text: "\u7b2c\ud842\udfb7\u884c\r\n\u6211\u91cd\u89c6\u81ea\u7531\u3002\r\n\u6211\u5f88\u5f00\u5fc3", kind: "diary", self: null,
    contrib: [["value.autonomy", 1, "我重视自由", 5, 10, "explicit_value_statement"], ["affect.happiness", 1, "开心", 15, 17, "textual_emotion_cue"]],
    cues: [["happiness", [15, 17]]],
    skipped: [] },
  { text: "\u6211: \ud83d\ude00 \u6211\u91cd\u89c6\u81ea\u7531\r\n\u4ed6: \u6211\u4e0d\u91cd\u89c6\u516c\u5e73\r\n\u968f\u4fbf\u4e00\u884c\r\n\u6211\uff1a\u4eca\u5929\u6211\u5f88\u96be\u8fc7\r\n", kind: "chat", self: "\u6211",
    contrib: [["value.autonomy", 1, "😀 我重视自由", 3, 10, "explicit_value_statement"], ["affect.sadness", 1, "难过", 35, 37, "textual_emotion_cue"]],
    cues: [["sadness", [35, 37]]],
    skipped: [[23, 27]] },
  { text: "\ud842\udfb7\ud842\udfb7\u4eba\u5e94\u8be5\u8bda\u5b9e\u3002", kind: "philosophy", self: null,
    contrib: [["value.truth", 1, "𠮷𠮷人应该诚实", 0, 7, "explicit_value_statement"]],
    cues: [],
    skipped: [] },
  { text: "\ud83d\ude00\u8fd9\u5468\u6211\u4e0d\u60f3\u4e3b\u52a8\u8054\u7cfb\u4ed6\u3002", kind: "diary", self: null,
    contrib: [["expression.less_initiative", 1, "😀这周我不想主动联系他", 0, 11, "contact_intention_cue"]],
    cues: [],
    skipped: [] },
  { text: "\u6211\u4e0d\u91cd\u89c6\u5b89\u5168\u3002", kind: "philosophy", self: null,
    contrib: [["value.security", -1, "我不重视安全", 0, 6, "negated_value_statement"]],
    cues: [],
    skipped: [] },
  { text: "\u6211\u91cd\u89c6\u516c\u5e73\uff0c\u4f46\u662f\u6211\u4e0d\u91cd\u89c6\u81ea\u7531\u3002\u4ed6\u5f88\u96be\u8fc7\uff0c\u6211\u5bf9\u4ed6\u5f88\u5931\u671b\u3002\u6211\u4e0d\u5f00\u5fc3\u3002", kind: "diary", self: null,
    contrib: [["value.fairness", 1, "我重视公平", 0, 5, "explicit_value_statement"], ["value.autonomy", -1, "我不重视自由", 8, 14, "negated_value_statement"], ["affect.disappointment", 1, "失望", 24, 26, "textual_emotion_cue"]],
    cues: [["contrast", [6, 8]], ["disappointment", [24, 26]], ["sadness", [17, 19]], ["happiness", [29, 31]]],
    skipped: [] },
  { text: "\u6211\u8ba4\u4e3a\u6210\u957f\u6bd4\u6210\u529f\u91cd\u8981\u3002\u6211\u4e0d\u8ba4\u4e3a\u5b89\u5168\u91cd\u8981\uff01", kind: "philosophy", self: null,
    contrib: [["value.growth", 1, "我认为成长比成功重要", 0, 10, "comparative_value_preference"], ["value.security", -1, "我不认为安全重要", 11, 19, "negated_value_statement"]],
    cues: [],
    skipped: [] },
  { text: "\u6211\uff1a\u6211\u53ef\u80fd\u6709\u70b9\u751f\u6c14\uff1b\u6211\u5c11\u4e3b\u52a8\u7ea6\u4ed6\n\u4ed6\uff1a\u597d\u5427\n\u6211\uff1a\u771f\u7684\u5f88\u4f24\u5fc3\uff0c\u4e5f\u8bb8", kind: "chat", self: "\u6211",
    contrib: [["affect.anger", 1, "生气", 7, 9, "textual_emotion_cue"], ["expression.less_initiative", 1, "我少主动约他", 10, 16, "contact_intention_cue"], ["affect.sadness", 1, "伤心", 27, 29, "textual_emotion_cue"]],
    cues: [["hedge", [3, 5]], ["anger", [7, 9]], ["hedge", [30, 32]], ["sadness", [27, 29]]],
    skipped: [] },
  // Added with the 2026-10-01 fixes: traditional 沒 / 沒那麼重要, and the clause a contact intention is narrowed to (guards.clause_span).
  // Output of the real rules on texts the assertion guards do not withhold (so no 沒那麼重要 here: its 麼 trips
  // the guard's question rule in the real back end; that pattern is covered by the source comparison below).
  { text: "\u6211\u6c92\u91cd\u8996\u81ea\u7531\u3002", kind: "diary", self: null,
    contrib: [["value.autonomy", -1, "我沒重視自由", 0, 6, "negated_value_statement"]],
    cues: [],
    skipped: [] },
  { text: "\u6211\u6c92\u91cd\u8996\u6210\u5c31\uff0c\u5bf9\u6211\u6765\u8bf4\u5f52\u5c5e\u503c\u5f97", kind: "philosophy", self: null,
    contrib: [["value.achievement", -1, "我沒重視成就", 0, 6, "negated_value_statement"], ["value.connection", 1, "对我来说归属值得", 7, 15, "explicit_value_statement"]],
    cues: [],
    skipped: [] },
  { text: "\u6211\u4e5f\u6c92\u6709\u91cd\u8996\u516c\u5e73\u3002", kind: "diary", self: null,
    contrib: [["value.fairness", -1, "我也沒有重視公平", 0, 8, "negated_value_statement"]],
    cues: [],
    skipped: [] },
  { text: "\u6211\u8fd9\u5468\u5f88\u5fd9\uff0c\u4e0d\u60f3\u4e3b\u52a8\u8054\u7cfb\u4ed6\uff0c\u4f46\u662f\u6211\u5f88\u60f3\u5ff5\u4ed6", kind: "diary", self: null,
    contrib: [],
    cues: [["contrast", [14, 16]]],
    skipped: [] },
  { text: "\ud842\udfb7\u6211\u8fd9\u5468\u4e0d\u60f3\u4e3b\u52a8\u8054\u7cfb\u4ed6\ud83c\udde8\ud83c\uddf3\u00e9\u6211\u575a\u6301\u771f\u5b9e", kind: "diary", self: null,
    contrib: [["expression.less_initiative", 1, "𠮷我这周不想主动联系他🇨🇳é我坚持真实", 0, 19, "contact_intention_cue"], ["value.truth", 1, "𠮷我这周不想主动联系他🇨🇳é我坚持真实", 0, 19, "explicit_value_statement"]],
    cues: [],
    skipped: [] },
  { text: "\u6211\u8fd9\u5468\u5f88\u5fd9\uff0c\u6211\u4e0d\u60f3\u4e3b\u52a8\u8054\u7cfb\u4ed6\uff0c\u4f46\u662f\u6211\u5f88\u60f3\u5ff5\u4ed6", kind: "diary", self: null,
    contrib: [["expression.less_initiative", 1, "我不想主动联系他", 6, 14, "contact_intention_cue"]],
    cues: [["contrast", [15, 17]]],
    skipped: [] },
  { text: "\ud83d\ude00\u6211\u5c11\u4e3b\u52a8\u7ea6\u4ed6\uff0c\u6211\u5f88\u5931\u671b\uff0c\u4f46\u662f\u6211\u5f88\u96be\u8fc7", kind: "diary", self: null,
    contrib: [["expression.less_initiative", 1, "😀我少主动约他", 0, 7, "contact_intention_cue"], ["affect.disappointment", 1, "失望", 10, 12, "textual_emotion_cue"], ["affect.sadness", 1, "难过", 17, 19, "textual_emotion_cue"]],
    cues: [["contrast", [13, 15]], ["disappointment", [10, 12]], ["sadness", [17, 19]]],
    skipped: [] },
  { text: "\u6211\uff1a\u6211\u8fd9\u5468\u5fd9, \u6211\u4e0d\u4f1a\u4e3b\u52a8\u8054\u7cfb\u5979\uff0c\u4e0d\u8fc7\u6211\u575a\u6301\u771f\u5b9e\n\u5979\uff1a\u597d", kind: "chat", self: "我",
    contrib: [["expression.less_initiative", 1, "我不会主动联系她", 8, 16, "contact_intention_cue"], ["value.truth", 1, "我坚持真实", 19, 24, "explicit_value_statement"]],
    cues: [["contrast", [17, 19]]],
    skipped: [] },
  { text: "\u6211\u5c11\u4e3b\u52a8\u7ea6\u4ed6\u800c\u662f\u7b49\u4ed6\uff0c\u6211\u5f88\u96be\u8fc7", kind: "diary", self: null,
    contrib: [["expression.less_initiative", 1, "我少主动约他", 0, 6, "contact_intention_cue"], ["affect.sadness", 1, "难过", 13, 15, "textual_emotion_cue"]],
    cues: [["sadness", [13, 15]]],
    skipped: [] },
];

test('mock extraction agrees with the Python rules on golden samples', () => {
  for (const g of PY_GOLDEN) {
    const got = mockExtract(g.text, g.kind, g.self).map((c) => [c.parameter, c.sign, c.evidence, c.span[0], c.span[1], c.rule_id.replace(MOCK_RULE_PREFIX, '')]);
    expect(got, g.text).toEqual(g.contrib);
    const t = mockTranslate(g.text, g.kind, g.self);
    expect(t.cues.map((c) => [c.value, [...c.span]]), g.text).toEqual(g.cues);
    expect(t.skipped.map((k) => [...k.span]), g.text).toEqual(g.skipped);
  }
});

// ---- mock: state machine -------------------------------------------------------------------

function mock(): MockBrainAdapter {
  let t = 0;
  return new MockBrainAdapter({ now: () => new Date(Date.UTC(2026, 8, 30, 12, 0, t++)) });
}
const FAIR = '我重视公平。';
const FREE = '我重视自由。';

test.describe('mock state machine', () => {
  test('immediate=false is disagreed at once; it cannot be reviewed but it can be previewed (F7)', async () => {
    const m = mock();
    const r = await m.submit({ text: FAIR, partition: 'rational', kind: 'philosophy', immediate: false });
    expect(r.status).toBe('disagreed');
    expect([r.immediate, r.confirm, r.exclamation, r.confirmed_by, r.reason]).toEqual([false, null, false, null, 'immediate_false']);
    const rec = await m.inputGet(r.source_id);
    expect([rec.reason, rec.confirm, rec.immediate, rec.confirmed_by, rec.exclamation]).toEqual(['immediate_false', null, false, null, false]);
    expect(await codeOf(m.confirm(r.source_id, true))).toBe('INVALID_ARGUMENT');
    expect(await codeOf(m.confirm(r.source_id, false))).toBe('INVALID_ARGUMENT');
    expect(await codeOf(m.revoke(r.source_id))).toBe('INVALID_ARGUMENT');
    // Preview works for EVERY input that is not agreed, and reports the input's own status.
    const before = await m.state();
    const preview = await m.preview(r.source_id);
    expect([preview.status, preview.immediate, preview.confirm, preview.reason]).toEqual(['disagreed', false, null, 'immediate_false']);
    expect(preview.hypothetical).toBe(true);
    expect(preview.effects).toHaveLength(1);
    expect(preview.effects[0].revision).toBeUndefined();
    expect(await m.state()).toEqual(before);
    expect(await m.inputGet(r.source_id)).toEqual(rec);
    expect(isTrainable(rec)).toBe(false);
    expect(await codeOf(m.submit({ text: FAIR, partition: 'rational', immediate: true, exclamation: 'yes' as never }))).toBe('INVALID_ARGUMENT');
  });

  test('exclamation sets BOTH judgements true, even when immediate is false, and trains at once (F3)', async () => {
    expect(effectiveJudgement(false, true)).toEqual({ immediate: true, confirm: true });
    expect(effectiveJudgement(true, true)).toEqual({ immediate: true, confirm: true });
    expect(effectiveJudgement(false, false)).toEqual({ immediate: false, confirm: null });
    expect(effectiveJudgement(true, false)).toEqual({ immediate: true, confirm: null });
    for (const immediate of [false, true]) {
      const m = mock();
      const r = await m.submit({ text: FAIR, partition: 'emotional', kind: 'philosophy', immediate, exclamation: true });
      expect([r.status, r.immediate, r.confirm, r.exclamation, r.confirmed_by, r.reason]).toEqual(['agreed', true, true, true, 'exclamation', null]);
      expect(r.effects).toHaveLength(1);
      expect(r.effects![0].revision).toBe(1);
      expect(r.effects![0].action).toBe('approve');
      expect(r.restored_fit).toBe(false);
      const rec = await m.inputGet(r.source_id);
      expect([rec.status, rec.immediate, rec.confirm, rec.exclamation, rec.confirmed_by]).toEqual(['agreed', true, true, true, 'exclamation']);
      expect(isTrainable(rec)).toBe(true);
      expect((await m.state()).emotional['value.fairness'].support).toBe(1);
      // The second confirmation is skipped; there is nothing left to preview.
      expect(await codeOf(m.preview(r.source_id))).toBe('INVALID_ARGUMENT');
      expect((await m.confirm(r.source_id, true)).effects).toEqual([]);
    }
  });

  test('pending -> confirm true -> agreed (manual) -> revoke -> revoked', async () => {
    const m = mock();
    const { source_id: id, status } = await m.submit({ text: FAIR, partition: 'rational', kind: 'philosophy', immediate: true });
    expect(status).toBe('pending');
    let rec = await m.inputGet(id);
    expect([rec.confirm, rec.reason, rec.reviewed_at]).toEqual([null, null, null]);

    // Preview is read-only and hypothetical.
    const before = await m.state();
    const list0 = await m.inputList();
    const preview = await m.preview(id);
    expect(preview.hypothetical).toBe(true);
    expect(preview.effects[0].revision).toBeUndefined();
    expect(await m.state()).toEqual(before);
    expect(await m.inputList()).toEqual(list0);
    expect(await m.effects()).toEqual([]);

    const review = await m.confirm(id, true);
    expect(review.status).toBe('agreed');
    expect(review.effects).toHaveLength(1);
    expect(review.effects[0].revision).toBe(1);
    rec = await m.inputGet(id);
    expect([rec.status, rec.confirm, rec.confirmed_by, rec.reason]).toEqual(['agreed', true, 'manual', null]);
    expect(isTrainable(rec)).toBe(true);
    // The formal effects are what the preview promised (nothing else changed in between).
    expect(review.effects[0].after).toBe(preview.effects[0].after);

    // An agreed input is not previewable and cannot be edited (it can be deleted: tested below).
    expect(await codeOf(m.preview(id))).toBe('INVALID_ARGUMENT');
    expect(await codeOf(m.inputEdit(id, { text: FREE, immediate: true }))).toBe('INVALID_ARGUMENT');
    expect((await m.inputGet(id)).text).toBe(FAIR);

    const revoked = await m.revoke(id);
    expect(revoked.status).toBe('revoked');
    expect(revoked.effects.map((e) => [e.action, e.revision])).toEqual([['revoke', 2]]);
    rec = await m.inputGet(id);
    expect([rec.status, rec.reason]).toEqual(['revoked', 'user_revoked']);
    expect(isTrainable(rec)).toBe(false);
    expect(await codeOf(m.revoke(id))).toBe('INVALID_ARGUMENT');
    // A revoked input may be previewed again (with its own status), edited and deleted.
    const again = await m.preview(id);
    expect([again.status, again.reason, again.effects.length]).toEqual(['revoked', 'user_revoked', 1]);
    expect((await m.inputEdit(id, { text: FREE, immediate: true })).status).toBe('pending');
    await m.inputDelete(id);
    expect(await codeOf(m.inputGet(id))).toBe('NOT_FOUND');
    expect(await m.effects()).toEqual([]);
  });

  test('confirm false, re-judging (F4), edit and delete', async () => {
    const m = mock();
    const { source_id: id } = await m.submit({ text: FAIR, partition: 'emotional', kind: 'philosophy', immediate: true });
    const no = await m.confirm(id, false);
    expect([no.status, no.effects]).toEqual(['disagreed', []]);
    let rec = await m.inputGet(id);
    // engine.py: a manual F records who said it (the DB trigger requires confirmed_by).
    expect([rec.reason, rec.confirm, rec.immediate, rec.confirmed_by]).toEqual(['confirm_false', false, true, 'manual']);
    expect((await m.state()).emotional['value.fairness'].observed).toBe(false);

    // Preview is allowed before re-judging; still hypothetical.
    expect((await m.preview(id)).effects[0].support_after).toBe(1);
    // Saying F again is a no-op; saying T is allowed and trains.
    const noop = await m.confirm(id, false);
    expect([noop.status, noop.effects]).toEqual(['disagreed', []]);
    const yes = await m.confirm(id, true);
    expect(yes.status).toBe('agreed');
    rec = await m.inputGet(id);
    expect([rec.confirm, rec.confirmed_by, rec.reason]).toEqual([true, 'manual', null]);
    expect((await m.state()).emotional['value.fairness'].support).toBe(1);

    // Edit after F: new text, immediate re-declared, second judgement reset.
    const other = await m.submit({ text: FAIR, partition: 'rational', kind: 'philosophy', immediate: true });
    await m.confirm(other.source_id, false);
    const edited = await m.inputEdit(other.source_id, { text: `${EMOJI}${FREE}`, immediate: true });
    expect([edited.status, edited.confirm, edited.reason, edited.char_count, edited.excerpt]).toEqual(['pending', null, null, 7, `${EMOJI}${FREE}`]);
    expect(edited.edited_at).not.toBeNull();
    expect((await m.inputGet(other.source_id)).text).toBe(`${EMOJI}${FREE}`);
    const flipped = await m.inputEdit(other.source_id, { text: FREE, immediate: false });
    expect([flipped.status, flipped.reason, flipped.confirm]).toEqual(['disagreed', 'immediate_false', null]);
    await m.inputDelete(other.source_id);
    expect(await codeOf(m.inputGet(other.source_id))).toBe('NOT_FOUND');
    expect(await codeOf(m.inputEdit('nope', { text: FREE, immediate: true }))).toBe('NOT_FOUND');
    expect(await codeOf(m.confirm('nope', true))).toBe('NOT_FOUND');
  });

  test('review semantics mirror engine.py: restore the frozen fit, reversal effects, no-op repeats', async () => {
    const m = mock();
    const text = `${FAIR}${'我坚持自由。'}`;
    const { source_id: id } = await m.submit({ text, partition: 'rational', kind: 'philosophy', immediate: true });
    const revision0 = (await m.inputPage()).revision;

    // Fresh approval: extracted and frozen.
    const first = await m.confirm(id, true);
    expect(first.restored_fit).toBe(false);
    expect(first.effects.map((e) => e.action)).toEqual(['approve', 'approve']);
    const agreedState = await m.state();
    const revision1 = (await m.inputPage()).revision;
    expect(revision1).toBeGreaterThan(revision0);

    // The same judgement again: no effects, no fit, no new revision, no duplicate event.
    const logLength = (await m.effects()).length;
    const same = await m.confirm(id, true);
    expect([same.status, same.effects, same.translator_effects]).toEqual(['agreed', [], []]);
    expect(same.restored_fit).toBeUndefined();
    expect(same.observed_terms).toBeUndefined();
    expect((await m.effects()).length).toBe(logLength);
    expect((await m.inputPage()).revision).toBe(revision1);
    expect(await m.state()).toEqual(agreedState);

    // F on an agreed input: reversal effects (action revoke) but the status is disagreed / confirm_false.
    const no = await m.confirm(id, false);
    expect([no.status, no.confirm, no.reason, no.confirmed_by, no.immediate]).toEqual(['disagreed', false, 'confirm_false', 'manual', true]);
    expect(no.effects.map((e) => [e.action, e.support_before, e.support_after])).toEqual([['revoke', 1, 0], ['revoke', 1, 0]]);
    expect((await m.state()).rational['value.fairness'].observed).toBe(false);
    expect(isTrainable(await m.inputGet(id))).toBe(false);
    // ... and saying F again is a no-op.
    const revision2 = (await m.inputPage()).revision;
    expect((await m.confirm(id, false)).effects).toEqual([]);
    expect((await m.inputPage()).revision).toBe(revision2);

    // T again restores the frozen contributions: same evidence, same spans, support 1 not 2.
    const back = await m.confirm(id, true);
    expect(back.restored_fit).toBe(true);
    expect(back.effects.map((e) => [e.parameter, e.evidence, e.span, e.rule_id])).toEqual(
      first.effects.map((e) => [e.parameter, e.evidence, e.span, e.rule_id]),
    );
    expect(back.effects.map((e) => e.support_after)).toEqual([1, 1]);
    expect(await m.state()).toEqual(agreedState);
    const rec = await m.inputGet(id);
    expect([rec.status, rec.confirm, rec.confirmed_by, rec.reason]).toEqual(['agreed', true, 'manual', null]);

    // A revoke removes it, keeps confirmed_by, and F on the revoked input is a no-op (status stays revoked).
    const rv = await m.revoke(id);
    expect([rv.status, rv.confirm, rv.reason, rv.confirmed_by]).toEqual(['revoked', false, 'user_revoked', 'manual']);
    expect(rv.effects.map((e) => e.action)).toEqual(['revoke', 'revoke']);
    const noopRevoked = await m.confirm(id, false);
    expect([noopRevoked.status, noopRevoked.reason, noopRevoked.effects]).toEqual(['revoked', 'user_revoked', []]);
    // T on the revoked input agrees it again (restore).
    const again = await m.confirm(id, true);
    expect([again.status, again.restored_fit, again.effects.length]).toEqual(['agreed', true, 2]);
    expect(await m.state()).toEqual(agreedState);

    // The effect history of this one input is complete and monotonic.
    const log = await m.effects(id);
    expect(log.map((e) => e.action)).toEqual(['approve', 'approve', 'revoke', 'revoke', 'approve', 'approve', 'revoke', 'revoke', 'approve', 'approve']);
    const revisions = log.map((e) => e.revision as number);
    expect(revisions).toEqual([...revisions].sort((a, b) => a - b));

    // A confirm_false input restored after an EDIT is a fresh fit of the new text (mock-only edit).
    await m.confirm(id, false);
    await m.inputEdit(id, { text: '我重视成长。', immediate: true });
    const fresh = await m.confirm(id, true);
    expect(fresh.restored_fit).toBe(false);
    expect(fresh.effects.map((e) => e.parameter)).toEqual(['value.growth']);
  });

  test('argument checks mirror the back end', async () => {
    const m = mock();
    expect(await codeOf(m.submit({ text: '   \n', partition: 'rational', immediate: true }))).toBe('INVALID_ARGUMENT');
    expect(await codeOf(m.submit({ text: 'x'.repeat(MAX_INPUT_CHARS + 1), partition: 'rational', immediate: true }))).toBe('INVALID_ARGUMENT');
    expect(await codeOf(m.submit({ text: 'x', partition: 'rational', kind: 'chat', immediate: true }))).toBe('INVALID_ARGUMENT');
    expect(await codeOf(m.submit({ text: 'x', partition: 'rational', kind: 'chat', self_speaker: ' ', immediate: true }))).toBe('INVALID_ARGUMENT');
    expect(await codeOf(m.submit({ text: 'a\ud83db', partition: 'rational', immediate: true }))).toBe('INVALID_ARGUMENT');
    expect(await codeOf(m.submit({ text: 'x', partition: 'nope' as never, immediate: true }))).toBe('INVALID_ARGUMENT');
    expect(await codeOf(m.inputList({ limit: 0 }))).toBe('INVALID_ARGUMENT');
    expect(await codeOf(m.inputList({ limit: 101 }))).toBe('INVALID_ARGUMENT');
  });

  test('list: newest first, filters, excerpt of 80 code points, exact text back', async () => {
    const m = mock();
    const long = `\ufeff${EMOJI.repeat(100)}\r\n尾`;
    const a = await m.submit({ text: long, partition: 'rational', immediate: true, source_ref: 'a.md' });
    const b = await m.submit({ text: FAIR, partition: 'emotional', kind: 'philosophy', immediate: false });
    await m.submit({ text: FREE, partition: 'rational', kind: 'philosophy', immediate: true });
    const all = await m.inputList();
    expect(all.map((r) => r.source_id)).toEqual(['mock-0003', 'mock-0002', 'mock-0001']);
    expect((await m.inputList({ limit: 2 })).length).toBe(2);
    expect((await m.inputList({ partition: 'emotional' })).map((r) => r.source_id)).toEqual([b.source_id]);
    expect((await m.inputList({ status: 'disagreed' })).map((r) => r.source_id)).toEqual([b.source_id]);
    const rowA = all.find((r) => r.source_id === a.source_id) as InputRecord;
    expect(codePointLength(rowA.excerpt)).toBe(80);
    expect(rowA.char_count).toBe(1 + 100 + 2 + 1);
    expect(rowA.source_ref).toBe('a.md');
    const detail = await m.inputGet(a.source_id);
    expect(detail.text).toBe(long);
    // A caller cannot corrupt the store through what it was handed.
    detail.text = 'changed';
    all[0].status = 'agreed';
    expect((await m.inputGet(a.source_id)).text).toBe(long);
    expect((await m.inputList())[0].status).toBe('pending');
  });

  test('latency option delays responses', async () => {
    const m = new MockBrainAdapter({ latencyMs: 30 });
    const t0 = Date.now();
    await m.state();
    expect(Date.now() - t0).toBeGreaterThanOrEqual(25);
  });
});

test.describe('training gate', () => {
  async function snapshot(m: MockBrainAdapter): Promise<{ state: string; trainable: string; records: InputRecord[]; observed: boolean }> {
    const records = await m.inputList({ limit: 100 });
    const state: ModelState = await m.state();
    const observed = Object.values(state).some((p) => PARAMETER_IDS.some((id) => p[id].observed));
    return {
      state: JSON.stringify(state),
      trainable: JSON.stringify(records.filter(isTrainable).map((r) => r.source_id).sort()),
      records,
      observed,
    };
  }

  test('the model changes exactly when the set of trainable inputs changes', async () => {
    const m = mock();
    // Every text yields at least one contribution, so a change of the set always moves the state.
    const ops: [string, () => Promise<unknown>][] = [
      ['submit F', () => m.submit({ text: FAIR, partition: 'rational', kind: 'philosophy', immediate: false })], // 1
      ['submit pending', () => m.submit({ text: FREE, partition: 'rational', kind: 'philosophy', immediate: true })], // 2
      ['preview pending', () => m.preview('mock-0002')],
      ['confirm on immediate-false (refused)', () => m.confirm('mock-0001', true)],
      ['preview immediate-false', () => m.preview('mock-0001')],
      ['confirm F', () => m.confirm('mock-0002', false)],
      ['preview after F', () => m.preview('mock-0002')],
      ['confirm F again (no-op)', () => m.confirm('mock-0002', false)],
      ['edit after F', () => m.inputEdit('mock-0002', { text: '我重视成长。', immediate: true })],
      ['edit F to immediate false', () => m.inputEdit('mock-0001', { text: FAIR, immediate: false })],
      ['re-judge T (F4)', () => m.confirm('mock-0002', true)], // trains
      ['exclamation submit', () => m.submit({ text: '我重视真实。', partition: 'emotional', kind: 'philosophy', immediate: true, exclamation: true })], // 3 trains
      ['exclamation without immediate', () => m.submit({ text: '我重视成长。', partition: 'rational', kind: 'philosophy', immediate: false, exclamation: true })], // 4 trains
      ['confirm T again (no-op)', () => m.confirm('mock-0002', true)],
      ['confirm F on agreed', () => m.confirm('mock-0004', false)], // untrains
      ['confirm T restores', () => m.confirm('mock-0004', true)], // trains
      ['edit agreed (refused)', () => m.inputEdit('mock-0002', { text: FAIR, immediate: true })],
      ['submit pending 2', () => m.submit({ text: '我坚持安全。', partition: 'crazy', kind: 'philosophy', immediate: true })], // 5
      ['revoke agreed', () => m.revoke('mock-0002')], // untrains
      ['revoke revoked (refused)', () => m.revoke('mock-0002')],
      ['confirm F revoked (no-op)', () => m.confirm('mock-0002', false)],
      ['preview revoked', () => m.preview('mock-0002')],
      ['confirm T revoked restores', () => m.confirm('mock-0002', true)], // trains
      ['confirm T pending 2', () => m.confirm('mock-0005', true)], // trains
      ['delete pending F', () => m.inputDelete('mock-0001')],
      ['revoke exclamation', () => m.revoke('mock-0003')], // untrains
      ['revoke pending 2', () => m.revoke('mock-0005')], // untrains
      ['edit revoked', () => m.inputEdit('mock-0003', { text: '我重视真实。', immediate: true })],
      ['confirm T edited', () => m.confirm('mock-0003', true)], // trains
      ['delete agreed', () => m.inputDelete('mock-0003')], // untrains, history gone
    ];
    let trained = 0;
    for (const [name, op] of ops) {
      const before = await snapshot(m);
      try {
        await op();
      } catch (e) {
        expect(e, name).toBeInstanceOf(BackendError);
        expect((e as BackendError).code, name).toBe(name.includes('refused') ? 'INVALID_ARGUMENT' : 'never');
      }
      const after = await snapshot(m);
      const setMoved = before.trainable !== after.trainable;
      expect(before.state !== after.state, `state moves iff the trainable set moves: ${name}`).toBe(setMoved);
      if (setMoved) trained++;
      // Invariants at every step: only a fully agreed record is trainable, and it carries both true judgements.
      for (const r of after.records) {
        if (r.status === 'agreed') expect([r.immediate, r.confirm], name).toEqual([true, true]);
        if (!r.immediate) expect(r.status, name).toBe('disagreed');
        if (r.confirm === false) expect(['disagreed', 'revoked'], name).toContain(r.status);
        if (r.status === 'revoked') expect([r.immediate, r.confirm, r.reason], name).toEqual([true, false, 'user_revoked']);
        if (r.status === 'pending') expect([r.immediate, r.confirm], name).toEqual([true, null]);
      }
      if (after.trainable === '[]') expect(after.observed, name).toBe(false);
    }
    expect(trained).toBe(12);
  });

  test('deleting an agreed input withdraws it and removes its whole history', async () => {
    const m = mock();
    await m.submit({ text: FAIR, partition: 'rational', kind: 'philosophy', immediate: true, exclamation: true });
    const base = await m.state();
    const baseEffects = (await m.effects()).length;
    const { source_id } = await m.submit({ text: '我坚持自由。我很难过。', partition: 'rational', kind: 'philosophy', immediate: true, exclamation: true });
    expect(await m.state()).not.toEqual(base);
    expect((await m.effects(source_id)).length).toBeGreaterThan(0);
    await m.inputDelete(source_id);
    // the model is what it was before that input, and nothing of it is left
    expect(await m.state()).toEqual(base);
    expect(await codeOf(m.inputGet(source_id))).toBe('NOT_FOUND');
    expect(await codeOf(m.effects(source_id))).toBe('NOT_FOUND');
    expect((await m.effects()).filter((e) => e.source_id === source_id)).toEqual([]);
    expect((await m.effects()).length).toBe(baseEffects);
    expect((await m.inputList()).map((r) => r.source_id)).not.toContain(source_id);
  });

  test('revoking restores the model exactly', async () => {
    const m = mock();
    await m.submit({ text: FAIR, partition: 'rational', kind: 'philosophy', immediate: true, exclamation: true });
    const base = await m.state();
    const { source_id } = await m.submit({ text: `${FAIR}${'我坚持自由。'}我很难过。`, partition: 'rational', kind: 'philosophy', immediate: true, exclamation: true });
    expect(await m.state()).not.toEqual(base);
    const res = await m.revoke(source_id);
    expect(await m.state()).toEqual(base);
    expect(res.effects.length).toBeGreaterThan(0);
    for (const e of res.effects) {
      expect(e.action).toBe('revoke');
      expect(e.support_after).toBe(e.support_before - 1);
    }
    const revisions = (await m.effects()).map((e) => e.revision as number);
    expect(revisions).toEqual([...revisions].sort((a, b) => a - b));
    expect(new Set(revisions).size).toBe(revisions.length);
    // The first input's own history is untouched by another input's revoke.
    expect((await m.effects('mock-0001')).map((e) => e.action)).toEqual(['approve']);
  });
});

// ---- unavailable ---------------------------------------------------------------------------

test('unavailable adapter rejects everything with UNAVAILABLE', async () => {
  const u = new UnavailableAdapter();
  expect(u.info).toEqual({ kind: 'unavailable', label: '后端未连接', trains: false });
  expect((await u.capabilities()).size).toBe(0);
  const calls = [
    u.submit({ text: 'x', partition: 'rational', immediate: true }),
    u.preview('a'),
    u.confirm('a', true),
    u.revoke('a'),
    u.inputList(),
    u.inputPage(),
    u.inputGet('a'),
    u.inputEdit('a', { text: 'x', immediate: true }),
    u.inputDelete('a'),
    u.state(),
    u.effects(),
    u.rank([]),
  ];
  for (const p of calls) expect(await codeOf(p)).toBe('UNAVAILABLE');
});

// ---- remote --------------------------------------------------------------------------------

type Handler = (params: Record<string, unknown>, env: RequestEnvelope) => unknown;
class ApiError {
  constructor(
    readonly code: string,
    readonly message = 'x',
  ) {}
}

function fake(handlers: Record<string, Handler>, tweak?: (res: ResponseEnvelope, env: RequestEnvelope) => ResponseEnvelope) {
  const seen: RequestEnvelope[] = [];
  let inflight = 0;
  let peak = 0;
  const transport: Transport = {
    async request(env) {
      seen.push(env);
      inflight++;
      peak = Math.max(peak, inflight);
      await new Promise((r) => setTimeout(r, 2));
      inflight--;
      const h = handlers[env.method];
      let res: ResponseEnvelope;
      if (!h) res = { schema_version: 1, id: env.id, ok: false, error: { code: 'METHOD_NOT_FOUND', message: 'unknown method' } };
      else {
        try {
          res = { schema_version: 1, id: env.id, ok: true, result: h(env.params, env) };
        } catch (e) {
          if (!(e instanceof ApiError)) throw e;
          res = { schema_version: 1, id: env.id, ok: false, error: { code: e.code, message: e.message } };
        }
      }
      return tweak ? tweak(res, env) : res;
    },
  };
  return { transport, seen, peak: () => peak };
}

const ROW = {
  source_id: 's1',
  partition: 'rational',
  kind: 'diary',
  self_speaker: null,
  status: 'agreed',
  reviewed_at: '2026-09-30T00:00:00+00:00',
  source_ref: 'd.md',
  created_at: '2026-09-30T00:00:00+00:00',
};

test.describe('remote adapter', () => {
  test('sends exact api.md envelopes with unique ids and only api.md fields', async () => {
    const f = fake({
      submit: () => ({ source_id: 's1', status: 'pending', partition: 'rational' }),
      review: () => ({ source_id: 's1', status: 'agreed', effects: [], translator_effects: [] }),
      state: () => ({}),
      effects: () => [],
      rank: () => ({ status: 'abstain', reason: 'x', ranked: [] }),
      preview: () => ({ source_id: 's1', effects: [], translator_effects: [] }),
      revoke: () => ({ source_id: 's1', status: 'revoked', effects: [] }),
    });
    const a = new RemoteBrainAdapter(f.transport);
    await a.submit({ text: 'hi', partition: 'rational', immediate: true, source_ref: 'd.md' });
    await a.submit({ text: 'yo', partition: 'emotional', kind: 'chat', self_speaker: 'A', immediate: true });
    await a.confirm('s1', true);
    await a.confirm('s1', false);
    await a.preview('s1');
    await a.revoke('s1');
    await a.state();
    await a.effects();
    await a.effects('s1');
    await a.rank([{ id: 'A', impacts: { 'value.care': 1 } }, { id: 'B', impacts: {} }]);

    expect(f.seen.map((e) => [e.method, e.params])).toEqual([
      ['submit', { text: 'hi', partition: 'rational', kind: 'diary', source_ref: 'd.md' }],
      ['submit', { text: 'yo', partition: 'emotional', kind: 'chat', self_speaker: 'A' }],
      ['review', { source_id: 's1', agree: true }],
      ['review', { source_id: 's1', agree: false }],
      ['preview', { source_id: 's1' }],
      ['revoke', { source_id: 's1' }],
      ['state', {}],
      ['effects', {}],
      ['effects', { source_id: 's1' }],
      ['rank', { options: [{ id: 'A', impacts: { 'value.care': 1 } }, { id: 'B', impacts: {} }] }],
    ]);
    for (const e of f.seen) {
      expect(Object.keys(e).sort()).toEqual(['id', 'method', 'params', 'schema_version']);
      expect(e.schema_version).toBe(1);
      expect(e.id.length).toBeGreaterThanOrEqual(1);
      expect(e.id.length).toBeLessThanOrEqual(128);
    }
    expect(new Set(f.seen.map((e) => e.id)).size).toBe(f.seen.length);
  });

  test('twoJudgements=false refuses what the current back end cannot represent, without sending it', async () => {
    const f = fake({ submit: () => ({ source_id: 's1', status: 'pending', partition: 'rational' }) });
    const a = new RemoteBrainAdapter(f.transport);
    expect(await codeOf(a.submit({ text: 'x', partition: 'rational', immediate: false }))).toBe('UNSUPPORTED');
    expect(await codeOf(a.submit({ text: 'x', partition: 'rational', immediate: true, exclamation: true }))).toBe('UNSUPPORTED');
    expect(f.seen).toHaveLength(0);
    await a.submit({ text: 'x', partition: 'rational', immediate: true, exclamation: false });
    expect(f.seen).toHaveLength(1);
    expect(f.seen[0].params).not.toHaveProperty('immediate');
    expect(f.seen[0].params).not.toHaveProperty('exclamation');
  });

  test('twoJudgements=true sends immediate and exclamation', async () => {
    const f = fake({ submit: () => ({ source_id: 's1', status: 'agreed', partition: 'rational', effects: [] }) });
    const a = new RemoteBrainAdapter(f.transport, { twoJudgements: true });
    await a.submit({ text: 'x', partition: 'rational', immediate: true, exclamation: true });
    await a.submit({ text: 'x', partition: 'rational', immediate: false });
    // An exclamation with immediate=false is valid now: the back end sets both judgements true itself,
    // so the adapter sends what the user gave and does not second-guess it.
    await a.submit({ text: 'x', partition: 'rational', immediate: false, exclamation: true });
    await a.submit({ text: 'x', partition: 'rational', immediate: true });
    expect(f.seen.map((e) => [e.params.immediate, e.params.exclamation])).toEqual([
      [true, true],
      [false, false],
      [false, true],
      [true, false],
    ]);
  });

  test('response id must match; codes are mapped; unknown code is INTERNAL_ERROR', async () => {
    const wrongId = fake({ state: () => ({}) }, (res) => ({ ...res, id: 'other' }));
    expect(await codeOf(new RemoteBrainAdapter(wrongId.transport).state())).toBe('INTERNAL_ERROR');
    const nullId = fake({ state: () => ({}) }, (res) => ({ ...res, id: null }));
    expect(await codeOf(new RemoteBrainAdapter(nullId.transport).state())).toBe('INTERNAL_ERROR');
    const version = fake({ state: () => ({}) }, (res) => ({ ...res, schema_version: 2 }));
    expect(await codeOf(new RemoteBrainAdapter(version.transport).state())).toBe('UNSUPPORTED_VERSION');

    for (const code of ['INVALID_REQUEST', 'UNSUPPORTED_VERSION', 'METHOD_NOT_FOUND', 'INVALID_ARGUMENT', 'NOT_FOUND', 'MODEL_UNAVAILABLE', 'STORAGE_ERROR', 'INTERNAL_ERROR']) {
      const f = fake({ preview: () => { throw new ApiError(code, 'boom'); } });
      const err = await new RemoteBrainAdapter(f.transport).preview('x').catch((e: unknown) => e);
      expect(err).toBeInstanceOf(BackendError);
      expect((err as BackendError).code).toBe(code);
      expect((err as BackendError).message).toBe('boom');
    }
    const odd = fake({ preview: () => { throw new ApiError('LOCKED', 'locked'); } });
    expect(await codeOf(new RemoteBrainAdapter(odd.transport).preview('x'))).toBe('INTERNAL_ERROR');
    // The two front-end-only codes are not accepted from the wire either.
    const spoof = fake({ preview: () => { throw new ApiError('UNAVAILABLE'); } });
    expect(await codeOf(new RemoteBrainAdapter(spoof.transport).preview('x'))).toBe('INTERNAL_ERROR');
    // A transport that dies is "unavailable".
    const dead = new RemoteBrainAdapter({ request: () => Promise.reject(new Error('pipe closed')) });
    expect(await codeOf(dead.state())).toBe('UNAVAILABLE');
    // STALE_CURSOR is a real api.md code and passes through; the codes the UI matches on all exist.
    const stale = fake({ input_page: () => { throw new ApiError('STALE_CURSOR', 'list changed'); } });
    const err = await new RemoteBrainAdapter(stale.transport).inputPage({ cursor: 'abc.def' }).catch((e: unknown) => e);
    expect([(err as BackendError).code, (err as BackendError).message]).toEqual(['STALE_CURSOR', 'list changed']);
    expect(BACKEND_ERROR_CODES).toContain('STALE_CURSOR');
  });

  test('edit and delete are UNSUPPORTED; when proposed methods are on, METHOD_NOT_FOUND maps to UNSUPPORTED', async () => {
    const f = fake({});
    const a = new RemoteBrainAdapter(f.transport);
    expect(await codeOf(a.inputEdit('s1', { text: 'x', immediate: true }))).toBe('UNSUPPORTED');
    expect(await codeOf(a.inputDelete('s1'))).toBe('UNSUPPORTED');
    expect(f.seen).toHaveLength(0);
    const b = new RemoteBrainAdapter(f.transport, { proposedMethods: true });
    const err = await b.inputDelete('s1').catch((e: unknown) => e);
    expect((err as BackendError).code).toBe('UNSUPPORTED');
    expect((err as BackendError).message).toContain('后端尚不支持');
    expect(f.seen.map((e) => e.method)).toEqual(['input_delete']);
  });

  test('capabilities are health.methods intersected with what the adapter can do', async () => {
    const f = fake({ health: () => ({ methods: ['health', 'submit', 'review', 'input_list', 'input_page', 'rank', 'terms', 'input_edit'] }) });
    const a = new RemoteBrainAdapter(f.transport);
    expect([...(await a.capabilities())].sort()).toEqual(['confirm', 'inputList', 'inputPage', 'rank', 'submit']);
    await a.capabilities();
    expect(f.seen.filter((e) => e.method === 'health')).toHaveLength(1);
    const b = new RemoteBrainAdapter(f.transport, { proposedMethods: true });
    expect((await b.capabilities()).has('inputEdit')).toBe(true);
    expect((await b.capabilities()).has('inputDelete')).toBe(false);
  });

  test('input_list rows get defaults; missing excerpts are hydrated through input_get with a cache', async () => {
    const texts: Record<string, string> = {
      s1: `${EMOJI.repeat(90)}尾`,
      s2: '短',
      s3: 'c',
      s4: 'd',
      s5: 'e',
    };
    const rows = [
      { ...ROW, source_id: 's1', status: 'agreed' },
      { ...ROW, source_id: 's2', status: 'disagreed' },
      { ...ROW, source_id: 's3', status: 'pending', reviewed_at: null },
      { ...ROW, source_id: 's4', status: 'revoked' },
      { ...ROW, source_id: 's5', status: 'pending', reviewed_at: null, excerpt: 'given', char_count: 1, immediate: false, confirm: null },
    ];
    const f = fake({
      input_list: () => rows,
      input_get: (p) => ({ ...rows.find((r) => r.source_id === p.source_id), text: texts[p.source_id as string] }),
    });
    const a = new RemoteBrainAdapter(f.transport, { hydrateConcurrency: 2 });
    const list = await a.inputList({ limit: 50 });
    expect(f.seen[0].params).toEqual({ limit: 50 });
    expect(f.seen.filter((e) => e.method === 'input_get').map((e) => e.params.source_id).sort()).toEqual(['s1', 's2', 's3', 's4']);
    expect(f.peak()).toBeLessThanOrEqual(2);

    const by = Object.fromEntries(list.map((r) => [r.source_id, r]));
    expect(codePointLength(by.s1.excerpt)).toBe(80);
    expect(by.s1.char_count).toBe(91);
    expect(by.s2.excerpt).toBe('短');
    expect(by.s5.excerpt).toBe('given');
    expect(by.s5.immediate).toBe(false); // a field the back end sent wins over the default
    expect(list.map((r) => [r.immediate, r.confirm, r.exclamation, r.confirmed_by, r.reason, r.edited_at]).slice(0, 4)).toEqual([
      [true, true, false, null, null, null],
      [true, false, false, null, null, null],
      [true, null, false, null, null, null],
      [true, true, false, null, 'user_revoked', null],
    ]);
    expect(list.map((r) => isTrainable(r))).toEqual([true, false, false, false, false]);

    // A second list is served from the cache: no more input_get.
    const before = f.seen.length;
    const again = await a.inputList();
    expect(f.seen.length - before).toBe(1);
    expect(again.find((r) => r.source_id === 's2')?.excerpt).toBe('短');
  });

  test('input_get returns the exact text and normalised metadata', async () => {
    const text = `\r\n${RARE}我重视公平`;
    const f = fake({ input_get: () => ({ ...ROW, text }) });
    const detail = await new RemoteBrainAdapter(f.transport).inputGet('s1');
    expect(detail.text).toBe(text);
    expect(detail.char_count).toBe(codePointLength(text));
    expect(detail.confirm).toBe(true);
    expect(detail.partition).toBe('rational');
    const broken = fake({ input_get: () => ({ ...ROW, status: 'weird', text }) });
    expect(await codeOf(new RemoteBrainAdapter(broken.transport).inputGet('s1'))).toBe('INTERNAL_ERROR');
  });
});

// ---- text files and validation ---------------------------------------------------------------

const bytes = (...parts: (string | number[])[]): Uint8Array =>
  Uint8Array.from(parts.flatMap((p) => (typeof p === 'string' ? [...new TextEncoder().encode(p)] : p)));
const file = (name: string, data: Uint8Array | string): File => new File([data as BlobPart], name);

test.describe('text files', () => {
  test('reads UTF-8, keeps CRLF, returns the file name only', async () => {
    const r = await readTextFile(file('日记.txt', `第一行\r\n${EMOJI}${RARE}\r\n`));
    expect(r).toEqual({ text: `第一行\r\n${EMOJI}${RARE}\r\n`, source_ref: '日记.txt' });
    expect((await readTextFile(file('C:\\Users\\me\\notes.MD', 'x'))).source_ref).toBe('notes.MD');
    expect((await readTextFile(file('a/b/NOTES.TXT', 'x'))).source_ref).toBe('NOTES.TXT');
    expect((await readTextFile(file('empty.txt', ''))).text).toBe('');
  });

  test('strips exactly one leading BOM', async () => {
    expect((await readTextFile(file('a.txt', bytes([0xef, 0xbb, 0xbf], '你好')))).text).toBe('你好');
    expect((await readTextFile(file('a.txt', bytes([0xef, 0xbb, 0xbf, 0xef, 0xbb, 0xbf], '你好')))).text).toBe('\ufeff你好');
    expect((await readTextFile(file('a.txt', bytes('你', [0xef, 0xbb, 0xbf], '好')))).text).toBe('你\ufeff好');
  });

  test('rejects invalid UTF-8 instead of substituting', async () => {
    for (const bad of [[0xff], [0xc3, 0x28], [0xed, 0xa0, 0x80] /* encoded surrogate */, [0xe4, 0xbd] /* truncated */, [0xc0, 0xaf]]) {
      const err = await readTextFile(file('bad.txt', bytes('ok', bad))).catch((e: unknown) => e);
      expect((err as { code: string }).code).toBe('INVALID_UTF8');
    }
  });

  test('rejects other extensions and oversize files', async () => {
    for (const name of ['a.pdf', 'a.txt.exe', 'a', 'a.markdown', 'txt', '.gitignore']) {
      const err = await readTextFile(file(name, 'x')).catch((e: unknown) => e);
      expect((err as { code: string }).code, name).toBe('EXTENSION');
    }
    const big = new Uint8Array(MAX_FILE_BYTES + 1).fill(0x61);
    expect(((await readTextFile(file('big.txt', big)).catch((e: unknown) => e)) as { code: string }).code).toBe('TOO_LARGE');
    const ok = new Uint8Array(MAX_FILE_BYTES).fill(0x61);
    expect((await readTextFile(file('max.md', ok))).text.length).toBe(MAX_FILE_BYTES);
    // A file-like whose size lies is caught after reading, too.
    const liar = { name: 'x.txt', size: 1, arrayBuffer: async () => big.buffer as ArrayBuffer };
    expect(((await readTextFile(liar).catch((e: unknown) => e)) as { code: string }).code).toBe('TOO_LARGE');
  });

  test('normalizeForSubmit drops one BOM, keeps CRLF, rejects lone surrogates', () => {
    expect(normalizeForSubmit('\ufeff\ufeffa\r\nb')).toBe('\ufeffa\r\nb');
    expect(normalizeForSubmit(`${EMOJI}\r\n`)).toBe(`${EMOJI}\r\n`);
    expect(() => normalizeForSubmit('a\ud83d')).toThrow(BackendError);
    expect(() => normalizeForSubmit('\ude00b')).toThrow(BackendError);
  });
});

test.describe('validateEntry', () => {
  const base = { partition: 'rational', kind: 'diary' } as const;

  test('blocking errors', () => {
    expect(validateEntry({ ...base, text: '' }).errors).toEqual(['内容不能为空']);
    expect(validateEntry({ ...base, text: ' \n\t\u3000 ' }).errors).toEqual(['内容不能为空']);
    expect(validateEntry({ ...base, text: 'x'.repeat(MAX_INPUT_CHARS) }).errors).toEqual([]);
    expect(validateEntry({ ...base, text: 'x'.repeat(MAX_INPUT_CHARS + 1) }).errors).toHaveLength(1);
    // Length counts code points: half as many emoji fit under the limit as UTF-16 units would allow.
    expect(validateEntry({ ...base, text: EMOJI.repeat(MAX_INPUT_CHARS) }).errors).toEqual([]);
    expect(validateEntry({ ...base, text: 'a\ud83d' }).errors).toHaveLength(1);
    expect(validateEntry({ ...base, text: 'ok' }).errors).toEqual([]);
  });

  test('chat needs one trimmed line as the speaker', () => {
    const chat = { ...base, kind: 'chat', text: '我: 你好' } as const;
    expect(validateEntry(chat).errors).toHaveLength(1);
    expect(validateEntry({ ...chat, self_speaker: '' }).errors).toHaveLength(1);
    expect(validateEntry({ ...chat, self_speaker: '  ' }).errors).toHaveLength(1);
    expect(validateEntry({ ...chat, self_speaker: ' 我' }).errors).toHaveLength(1);
    expect(validateEntry({ ...chat, self_speaker: '我\n他' }).errors).toHaveLength(1);
    expect(validateEntry({ ...chat, self_speaker: '我' })).toMatchObject({ errors: [], warnings: [] });
    // Non-chat ignores the speaker entirely.
    expect(validateEntry({ ...base, text: 'x', self_speaker: '  ' }).errors).toEqual([]);
  });

  test('chat warnings: no line for the speaker, and unlabeled lines to be skipped', () => {
    const text = '我: 你好\r\n他：在吗\r\n没有冒号的一行\r\n\r\n我：再见';
    const ok = validateEntry({ ...base, kind: 'chat', text, self_speaker: '我' });
    expect(ok.errors).toEqual([]);
    expect(ok.chat).toEqual({ selfLines: 2, otherLines: 1, unlabeledLines: 1 });
    expect(ok.warnings).toHaveLength(1);
    expect(ok.warnings[0]).toContain('1 行');

    const missing = validateEntry({ ...base, kind: 'chat', text, self_speaker: '你' });
    expect(missing.errors).toEqual([]);
    expect(missing.chat?.selfLines).toBe(0);
    expect(missing.warnings).toHaveLength(2);
    expect(missing.warnings[0]).toContain('没有找到发言者');

    // Exact match only: a longer or shorter name is another speaker.
    expect(validateEntry({ ...base, kind: 'chat', text: '小我: hi', self_speaker: '我' }).chat?.selfLines).toBe(0);
    // A name the back end regex can never match (space inside) is called out.
    const spaced = validateEntry({ ...base, kind: 'chat', text: 'Amy Lee: hi', self_speaker: 'Amy Lee' });
    expect(spaced.chat?.selfLines).toBe(0);
    expect(spaced.warnings[0]).toContain('无法');
    // Python-style line splitting: a lone \r and U+2028 separate lines.
    expect(validateEntry({ ...base, kind: 'chat', text: '我: a\r我: b\u2028我: c', self_speaker: '我' }).chat?.selfLines).toBe(3);
  });
});

// ---- mock: input_page ------------------------------------------------------------------------

test.describe('mock inputPage', () => {
  test('pages the whole list newest first, without gaps or repeats, past 100 items', async () => {
    const m = new MockBrainAdapter();
    expect(await m.inputPage()).toEqual({ items: [], total: 0, next_cursor: null, revision: 0 });
    for (let i = 0; i < 250; i++) {
      await m.submit({ text: `第${i}条`, partition: PARTITION_CYCLE[i % 3], immediate: i % 5 !== 0 });
    }
    const seen: string[] = [];
    let cursor: string | null = null;
    let pages = 0;
    do {
      const page: Awaited<ReturnType<MockBrainAdapter['inputPage']>> = await m.inputPage({ limit: 100, cursor });
      expect(page.total).toBe(250);
      expect(page.items.length).toBeLessThanOrEqual(100);
      seen.push(...page.items.map((r) => r.source_id));
      cursor = page.next_cursor;
      pages++;
    } while (cursor);
    expect(pages).toBe(3);
    expect(seen).toHaveLength(250);
    expect(new Set(seen).size).toBe(250);
    expect(seen).toEqual(Array.from({ length: 250 }, (_, i) => `mock-${String(250 - i).padStart(4, '0')}`));
    // The limit may change between pages.
    const first = await m.inputPage({ limit: 7 });
    const second = await m.inputPage({ limit: 3, cursor: first.next_cursor });
    expect(second.items.map((r) => r.source_id)).toEqual(['mock-0243', 'mock-0242', 'mock-0241']);
  });

  test('filters apply before the count and the limit; null equals missing', async () => {
    const m = mock();
    for (let i = 0; i < 9; i++) await m.submit({ text: `x${i}`, partition: PARTITION_CYCLE[i % 3], immediate: i % 2 === 0 });
    const page = await m.inputPage({ partition: 'rational', status: 'pending', limit: 2 });
    expect(page.total).toBe(2); // mock-0001 and mock-0007 (i = 0, 6); i = 3 is immediate=false
    expect(page.items.map((r) => r.source_id)).toEqual(['mock-0007', 'mock-0001']);
    expect(page.next_cursor).toBeNull();
    const a = await m.inputPage({ limit: 4 });
    const b = await m.inputPage({ limit: 4, cursor: a.next_cursor, partition: undefined, status: undefined });
    expect(b.items).toHaveLength(4);
    expect(await m.inputPage({ limit: 4, cursor: a.next_cursor, partition: null as never, status: null as never })).toEqual(b);
    const dis = await m.inputPage({ status: 'disagreed', limit: 2 });
    expect([dis.total, dis.items.length, dis.next_cursor === null]).toEqual([4, 2, false]);
  });

  test('a cursor is stale after any change to the inputs, never after a read or a no-op', async () => {
    const m = mock();
    const a = await m.submit({ text: FAIR, partition: 'rational', kind: 'philosophy', immediate: true });
    for (let i = 0; i < 4; i++) await m.submit({ text: `y${i}`, partition: 'rational', immediate: true });
    const page = await m.inputPage({ limit: 2 });
    const cursor = page.next_cursor as string;
    expect(cursor).toBeTruthy();

    // Reads and hypothetical work do not move it.
    await m.preview(a.source_id);
    await m.state();
    await m.effects();
    await m.inputList();
    await m.inputGet(a.source_id);
    await m.rank([{ id: 'A', impacts: {} }, { id: 'B', impacts: {} }]).catch(() => undefined);
    expect((await m.inputPage({ limit: 2, cursor })).revision).toBe(page.revision);

    const moves: [string, () => Promise<unknown>][] = [
      ['submit', () => m.submit({ text: 'z', partition: 'emotional', immediate: true })],
      ['changed review', () => m.confirm(a.source_id, true)],
      ['review back (F)', () => m.confirm(a.source_id, false)],
      ['restore', () => m.confirm(a.source_id, true)],
      ['revoke', () => m.revoke(a.source_id)],
      ['edit (mock only)', () => m.inputEdit(a.source_id, { text: FREE, immediate: true })],
      ['delete (mock only)', () => m.inputDelete('mock-0002')],
    ];
    let stale = cursor;
    let revision = page.revision;
    for (const [name, op] of moves) {
      // A cursor taken before the change is valid until then and stale after, whatever partition changed.
      expect(await codeOf(m.inputPage({ limit: 2, cursor: stale })), name).toBe('RESOLVED');
      await op();
      const now = await m.inputPage({ limit: 2 });
      expect(now.revision, name).toBeGreaterThan(revision);
      expect(await codeOf(m.inputPage({ limit: 2, cursor: stale })), name).toBe('STALE_CURSOR');
      revision = now.revision;
      stale = now.next_cursor as string;
      expect((await m.inputPage({ limit: 2, cursor: stale })).items.length, name).toBeGreaterThan(0);
    }
    // No-ops: the same judgement again, a refused call.
    await m.confirm(a.source_id, false); // pending -> disagreed: a change
    const settled = await m.inputPage({ limit: 2 });
    await m.confirm(a.source_id, false); // the same judgement again
    expect(await codeOf(m.revoke('mock-0003'))).toBe('INVALID_ARGUMENT'); // refused: mock-0003 is pending
    expect((await m.inputPage({ limit: 2 })).revision).toBe(settled.revision);
    expect(await codeOf(m.inputPage({ limit: 2, cursor: settled.next_cursor }))).toBe('RESOLVED');
  });

  test('invalid cursors, filters and limits are INVALID_ARGUMENT', async () => {
    const m = mock();
    for (let i = 0; i < 4; i++) await m.submit({ text: `q${i}`, partition: 'rational', immediate: true });
    const { next_cursor: cursor } = await m.inputPage({ limit: 2, partition: 'rational' });
    for (const bad of ['', 'garbage', 'mock1.', 'mock1.!!!', 'mock1.e30', `${cursor}x`, `${cursor}.`, 'abc.' + '0'.repeat(64)]) {
      expect(await codeOf(m.inputPage({ limit: 2, partition: 'rational', cursor: bad })), bad).toBe('INVALID_ARGUMENT');
    }
    // Filters must match the ones the cursor was made with.
    expect(await codeOf(m.inputPage({ limit: 2, cursor }))).toBe('INVALID_ARGUMENT');
    expect(await codeOf(m.inputPage({ limit: 2, partition: 'emotional', cursor }))).toBe('INVALID_ARGUMENT');
    expect(await codeOf(m.inputPage({ limit: 2, partition: 'rational', status: 'pending', cursor }))).toBe('INVALID_ARGUMENT');
    expect(await codeOf(m.inputPage({ limit: 2, partition: 'rational', cursor }))).toBe('RESOLVED');
    for (const limit of [0, 101, 1.5, -1, Number.NaN]) expect(await codeOf(m.inputPage({ limit })), String(limit)).toBe('INVALID_ARGUMENT');
    expect(await codeOf(m.inputPage({ partition: 'nope' as never }))).toBe('INVALID_ARGUMENT');
    expect(await codeOf(m.inputPage({ status: 'nope' as never }))).toBe('INVALID_ARGUMENT');
    expect(await codeOf(m.inputList({ status: 'nope' as never }))).toBe('INVALID_ARGUMENT');
  });

  test('what a page hands out cannot corrupt the store', async () => {
    const m = mock();
    await m.submit({ text: FAIR, partition: 'rational', immediate: true });
    const page = await m.inputPage();
    page.items[0].status = 'agreed';
    page.total = 99;
    expect((await m.inputPage()).items[0].status).toBe('pending');
    expect((await m.inputPage()).total).toBe(1);
  });
});

const PARTITION_CYCLE = ['rational', 'emotional', 'crazy'] as const;

// ---- remote: input_page and probe ---------------------------------------------------------------

const ALL_METHODS = [
  'health', 'baseline', 'submit', 'input_get', 'input_list', 'input_page', 'preview', 'review', 'review_history',
  'correction_set', 'correction_history', 'revoke', 'state', 'effects', 'terms', 'rank', 'candidate_propose',
  'candidate_review', 'candidate_list', 'memory_list', 'memory_search', 'input_edit', 'input_delete',
];
const FEATURES = {
  two_judgements: true,
  exclamation_sets_both_true: true,
  repeat_review: true,
  preview_untrained: true,
  input_summary: true,
  input_pagination: true,
  source_edit: true,
  source_delete: true,
};
const health = (over: Record<string, unknown> = {}) => () => ({
  schema_version: 1,
  candidate_publication: 'manual',
  llm_runtime_configured: false,
  methods: ALL_METHODS,
  features: FEATURES,
  ...over,
});
const FULL_ROW = {
  ...ROW,
  status: 'pending',
  reviewed_at: null,
  immediate: true,
  confirm: null,
  exclamation: false,
  confirmed_by: null,
  reason: null,
  excerpt: '今天',
  char_count: 2,
  edited_at: null,
};

test.describe('remote inputPage', () => {
  test('sends input_page with only the given fields and the cursor verbatim; rows need no input_get', async () => {
    const pages = [
      { items: [{ ...FULL_ROW, source_id: 'a' }, { ...FULL_ROW, source_id: 'b', status: 'agreed', confirm: true, confirmed_by: 'legacy' }], total: 5, next_cursor: 'tok.' + 'a'.repeat(64), revision: 7 },
      { items: [], total: 5, next_cursor: null, revision: 7 },
    ];
    let n = 0;
    const f = fake({ input_page: () => pages[n++], input_get: () => { throw new Error('must not be called'); } });
    const a = new RemoteBrainAdapter(f.transport);
    const first = await a.inputPage({ partition: 'rational', limit: 2 });
    const second = await a.inputPage({ partition: 'rational', limit: 2, cursor: first.next_cursor, status: undefined });
    expect(f.seen.map((e) => [e.method, e.params])).toEqual([
      ['input_page', { partition: 'rational', limit: 2 }],
      ['input_page', { partition: 'rational', limit: 2, cursor: 'tok.' + 'a'.repeat(64) }],
    ]);
    expect([first.total, first.revision, first.items.map((r) => r.source_id)]).toEqual([5, 7, ['a', 'b']]);
    expect(first.items[0].excerpt).toBe('今天');
    expect(first.items[1].confirmed_by).toBe('legacy');
    expect([second.items, second.next_cursor]).toEqual([[], null]);
    expect((await new RemoteBrainAdapter(fake({ input_page: () => pages[1] }).transport).inputPage({ cursor: null })).next_cursor).toBeNull();
    // inputList still uses input_list.
    const g = fake({ input_list: () => [FULL_ROW] });
    await new RemoteBrainAdapter(g.transport).inputList();
    expect(g.seen.map((e) => e.method)).toEqual(['input_list']);
  });

  test('a page row without excerpt is hydrated; a malformed page is INTERNAL_ERROR', async () => {
    const { excerpt: _e, char_count: _c, ...bare } = FULL_ROW;
    const f = fake({
      input_page: () => ({ items: [{ ...bare, source_id: 'x' }], total: 1, next_cursor: null, revision: 1 }),
      input_get: () => ({ ...FULL_ROW, source_id: 'x', text: '全文' }),
    });
    const page = await new RemoteBrainAdapter(f.transport).inputPage();
    expect(page.items[0].excerpt).toBe('全文');
    expect(f.seen.map((e) => e.method)).toEqual(['input_page', 'input_get']);
    for (const result of [null, [], { items: [], total: 0, revision: 0 }, { items: {}, total: 0, next_cursor: null, revision: 0 }, { items: [], total: '0', next_cursor: null, revision: 0 }]) {
      const g = fake({ input_page: () => result });
      expect(await codeOf(new RemoteBrainAdapter(g.transport).inputPage())).toBe('INTERNAL_ERROR');
    }
  });
});

test.describe('RemoteBrainAdapter.probe', () => {
  test('two_judgements comes from the feature flag, capabilities from the methods, proposedMethods from health (F6)', async () => {
    const f = fake({ health: health({ model_epoch: 3 }) });
    const probe = await RemoteBrainAdapter.probe(f.transport);
    expect(f.seen.map((e) => [e.method, e.params])).toEqual([['health', {}]]);
    expect(probe.options).toEqual({ twoJudgements: true, proposedMethods: true });
    expect(probe.methods).toEqual(ALL_METHODS);
    expect(probe.features).toEqual(FEATURES);
    expect(probe.modelEpoch).toBe(3);
    expect([...probe.capabilities].sort()).toEqual(
      ['confirm', 'effects', 'inputDelete', 'inputEdit', 'inputGet', 'inputList', 'inputPage', 'preview', 'rank', 'revoke', 'state', 'submit'],
    );
    // An older back end: not listing the methods, or not reporting both features, keeps edit and delete off.
    const noMethods = await RemoteBrainAdapter.probe(fake({ health: health({ methods: ALL_METHODS.filter((m) => !m.startsWith('input_e') && m !== 'input_delete') }) }).transport);
    expect([noMethods.options.proposedMethods, noMethods.capabilities.has('inputEdit')]).toEqual([false, false]);
    for (const features of [{ ...FEATURES, source_edit: false }, { ...FEATURES, source_delete: false }, { ...FEATURES, source_delete: undefined }, { ...FEATURES, source_edit: 'true' }]) {
      const part = await RemoteBrainAdapter.probe(fake({ health: health({ features }) }).transport);
      expect(part.options.proposedMethods, JSON.stringify(features)).toBe(false);
    }
    // The caller can still force it off; model_epoch is absent -> null.
    const forced = await RemoteBrainAdapter.probe(fake({ health: health() }).transport, { proposedMethods: false });
    expect([forced.options.proposedMethods, forced.capabilities.has('inputDelete'), forced.modelEpoch]).toEqual([false, false, null]);

    // The probed options make an adapter that really sends the two judgements.
    const g = fake({ health: health(), submit: () => ({ source_id: 's', status: 'agreed', partition: 'rational', effects: [] }) });
    const adapter = new RemoteBrainAdapter(g.transport, (await RemoteBrainAdapter.probe(g.transport)).options);
    await adapter.submit({ text: 'x', partition: 'rational', immediate: false, exclamation: true });
    expect(g.seen.at(-1)?.params).toMatchObject({ immediate: false, exclamation: true });
    expect([...(await adapter.capabilities())].sort()).toEqual([...probe.capabilities].sort());
  });

  test('model_active / model_epoch of a row and health.model_epoch are kept, never invented', async () => {
    const row = (id: string, extra: Record<string, unknown>) => ({ source_id: id, partition: 'rational', kind: 'diary', status: 'agreed', immediate: true, confirm: true, exclamation: false, confirmed_by: 'manual', reason: null, excerpt: 'x', char_count: 1, edited_at: null, created_at: 't', reviewed_at: 't', source_ref: null, self_speaker: null, ...extra });
    const f = fake({ health: health({ model_epoch: 2 }), input_list: () => [row('a', { model_active: false, model_epoch: 1 }), row('b', {})] });
    const a = new RemoteBrainAdapter(f.transport);
    expect(await a.modelEpoch()).toBe(2);
    const [x, y] = await a.inputList();
    expect([x.model_active, x.model_epoch, 'model_active' in y, 'model_epoch' in y]).toEqual([false, 1, false, false]);
    expect(isTrainable(x)).toBe(false);
    expect(isTrainable(y)).toBe(true);
  });

  test('an older back end (flag false, missing, not a boolean) probes as twoJudgements=false', async () => {
    for (const features of [{ ...FEATURES, two_judgements: false }, {}, undefined, { two_judgements: 'true' }, { two_judgements: 1 }, null]) {
      const probe = await RemoteBrainAdapter.probe(fake({ health: health({ features }) }).transport);
      expect(probe.options.twoJudgements, JSON.stringify(features)).toBe(false);
    }
    const f = fake({ health: health({ features: { two_judgements: false } }), submit: () => ({ source_id: 's', status: 'pending', partition: 'rational' }) });
    const adapter = new RemoteBrainAdapter(f.transport, (await RemoteBrainAdapter.probe(f.transport)).options);
    expect(await codeOf(adapter.submit({ text: 'x', partition: 'rational', immediate: false }))).toBe('UNSUPPORTED');
    expect(f.seen.map((e) => e.method)).toEqual(['health']); // the refused submit never reached the transport
  });

  test("the caller's own options pass through; failures are BackendErrors", async () => {
    let n = 0;
    const f = fake({ health: health() });
    const probe = await RemoteBrainAdapter.probe(f.transport, { hydrateConcurrency: 1, newId: () => `probe-${++n}` });
    expect(probe.options).toEqual({ hydrateConcurrency: 1, newId: expect.any(Function), twoJudgements: true, proposedMethods: true });
    expect(f.seen[0].id).toBe('probe-1');

    expect(await codeOf(RemoteBrainAdapter.probe({ request: () => Promise.reject(new Error('gone')) }))).toBe('UNAVAILABLE');
    const denied = fake({ health: () => { throw new ApiError('MODEL_UNAVAILABLE', 'no python'); } });
    expect(await codeOf(RemoteBrainAdapter.probe(denied.transport))).toBe('MODEL_UNAVAILABLE');
    expect(await codeOf(RemoteBrainAdapter.probe(fake({ health: () => ({ features: FEATURES }) }).transport))).toBe('INTERNAL_ERROR');
    expect(await codeOf(RemoteBrainAdapter.probe(fake({ health: () => ({ methods: [1], features: FEATURES }) }).transport))).toBe('INTERNAL_ERROR');
    expect(await codeOf(RemoteBrainAdapter.probe(fake({ health: health() }, (res) => ({ ...res, id: 'other' })).transport))).toBe('INTERNAL_ERROR');
    // A failed capabilities probe is not remembered: the next call asks again.
    let fail = true;
    const flaky = fake({ health: () => { if (fail) throw new ApiError('MODEL_UNAVAILABLE'); return health()(); } });
    const a = new RemoteBrainAdapter(flaky.transport);
    expect(await codeOf(a.capabilities())).toBe('MODEL_UNAVAILABLE');
    fail = false;
    expect((await a.capabilities()).has('submit')).toBe(true);
  });

  test('adapter methods and error codes stay in step', () => {
    expect(new Set(ADAPTER_METHODS).size).toBe(ADAPTER_METHODS.length);
    expect(ADAPTER_METHODS).toContain('inputPage');
    expect(new Set(BACKEND_ERROR_CODES).size).toBe(BACKEND_ERROR_CODES.length);
  });
});

// ---- Tauri brain_call shim ---------------------------------------------------------------------

type Invoke = (command: string, args?: Record<string, unknown>) => Promise<unknown>;

/** Runs `fn` with `globalThis.window` set (and restores it), like the Tauri webview. */
async function withWindow<T>(win: unknown, fn: () => Promise<T> | T): Promise<T> {
  const g = globalThis as { window?: unknown };
  const had = 'window' in g;
  const previous = g.window;
  g.window = win;
  try {
    return await fn();
  } finally {
    if (had) g.window = previous;
    else delete g.window;
  }
}
const tauriWindow = (invoke: Invoke) => ({ __TAURI_INTERNALS__: { invoke } });

const ENV: RequestEnvelope = { schema_version: 1, id: 'req-1', method: 'state', params: {} };

test.describe('tauri transport', () => {
  test('null outside the Tauri webview', async () => {
    expect(createTauriTransport()).toBeNull(); // plain Node: no window at all
    expect(await withWindow({}, () => createTauriTransport())).toBeNull();
    expect(await withWindow({ isTauri: true }, () => createTauriTransport())).toBeNull();
    expect(await withWindow({ __TAURI_INTERNALS__: {} }, () => createTauriTransport())).toBeNull();
    expect(await withWindow({ __TAURI_INTERNALS__: { invoke: 'nope' } }, () => createTauriTransport())).toBeNull();
    expect(await withWindow(null, () => createTauriTransport())).toBeNull();
    expect(createTauriTransport({})).toBeNull();
  });

  test('invokes brain_call once with { request } and returns the envelope untouched; creating it calls nothing', async () => {
    const calls: { command: string; args: unknown; self: unknown }[] = [];
    const internals = {
      invoke(this: unknown, command: string, args?: Record<string, unknown>): Promise<unknown> {
        calls.push({ command, args, self: this });
        return Promise.resolve({ schema_version: 1, id: 'req-1', ok: true, result: { hello: 'world' } });
      },
    };
    const transport = await withWindow({ __TAURI_INTERNALS__: internals }, () => createTauriTransport());
    expect(transport).not.toBeNull();
    expect(calls).toHaveLength(0);
    const res = await (transport as Transport).request(ENV);
    expect(res).toEqual({ schema_version: 1, id: 'req-1', ok: true, result: { hello: 'world' } });
    expect(calls).toHaveLength(1);
    expect(calls[0].command).toBe(BRAIN_COMMAND);
    expect(BRAIN_COMMAND).toBe('brain_call');
    expect(calls[0].args).toEqual({ request: ENV });
    expect(Object.keys(calls[0].args as object)).toEqual(['request']);
    expect(calls[0].self).toBe(internals);
    // The explicit-scope form used by tests reads the same global.
    expect(createTauriTransport({ window: { __TAURI_INTERNALS__: internals } })).not.toBeNull();
  });

  test('every rejection becomes a MODEL_UNAVAILABLE envelope with the request id, without a retry', async () => {
    const reasons: unknown[] = [
      'window "x" not allowed to call command brain_call',
      new Error('ACL denied'),
      { message: 'desktop unavailable' },
      undefined,
      null,
      42,
      `line one\n   line two ${'x'.repeat(500)}`,
    ];
    for (const reason of reasons) {
      let calls = 0;
      const transport = createTauriTransport({ window: tauriWindow(() => { calls++; return Promise.reject(reason); }) }) as Transport;
      const res = await transport.request({ ...ENV, id: 'id-ü' });
      expect(res.schema_version, String(reason)).toBe(1);
      expect(res.id).toBe('id-ü');
      expect(res.ok).toBe(false);
      if (res.ok) throw new Error('unreachable');
      expect(res.error.code).toBe('MODEL_UNAVAILABLE');
      expect(res.error.message.startsWith('桌面后端不可用')).toBe(true);
      expect(res.error.message).not.toMatch(/\n/);
      expect(res.error.message.length).toBeLessThan(260);
      expect(calls, 'never retried').toBe(1);
    }
    // A synchronous throw is the same, and so is a rejection of a write.
    let calls = 0;
    const thrower = createTauriTransport({ window: tauriWindow(() => { calls++; throw new Error('boom'); }) }) as Transport;
    const res = await thrower.request({ ...ENV, method: 'submit', id: 'w1' });
    expect([res.ok, res.id, calls]).toEqual([false, 'w1', 1]);
    expect(unavailableEnvelope('z', 'why')).toEqual({ schema_version: 1, id: 'z', ok: false, error: { code: 'MODEL_UNAVAILABLE', message: '桌面后端不可用：why' } });
    expect(unavailableEnvelope('z')).toMatchObject({ error: { message: '桌面后端不可用' } });
  });

  test('through RemoteBrainAdapter: a rejecting invoke is a MODEL_UNAVAILABLE BackendError, never a throw of another kind', async () => {
    let calls = 0;
    const transport = createTauriTransport({ window: tauriWindow(() => { calls++; return Promise.reject('ACL'); }) }) as Transport;
    const a = new RemoteBrainAdapter(transport);
    expect(await codeOf(a.submit({ text: 'x', partition: 'rational', immediate: true }))).toBe('MODEL_UNAVAILABLE');
    expect(calls).toBe(1);
    expect(await codeOf(a.state())).toBe('MODEL_UNAVAILABLE');
    expect(calls).toBe(2);
    // A host that answers garbage is an INTERNAL_ERROR, not a hang or a crash.
    const odd = createTauriTransport({ window: tauriWindow(() => Promise.resolve('not an envelope')) }) as Transport;
    expect(await codeOf(new RemoteBrainAdapter(odd).state())).toBe('INTERNAL_ERROR');
  });
});

// ---- backendStore.connectDesktopBackend ---------------------------------------------------------

/** An in-memory stand-in for the Rust host + Python back end, behind `invoke`. */
function fakeHost(features: Record<string, unknown> = FEATURES) {
  const seen: RequestEnvelope[] = [];
  const invoke: Invoke = async (_command, args) => {
    const request = (args as { request: RequestEnvelope }).request;
    seen.push(request);
    const ok = (result: unknown) => ({ schema_version: 1, id: request.id, ok: true, result });
    if (request.method === 'health') return ok(health({ features })());
    if (request.method === 'submit') return ok({ source_id: 'h1', status: 'agreed', partition: 'rational', effects: [] });
    return { schema_version: 1, id: request.id, ok: false, error: { code: 'METHOD_NOT_FOUND', message: 'unknown method' } };
  };
  return { invoke, seen };
}

test.describe('backendStore.connectDesktopBackend', () => {
  test.describe.configure({ mode: 'serial' });
  test.beforeEach(() => {
    backendStore.disconnectRemote();
    backendStore.leaveDemo();
  });

  test('not in the desktop app: nothing changes except the reason', async () => {
    let notified = 0;
    const off = backendStore.subscribe(() => notified++);
    const before = backendStore.get();
    expect(before.mode).toBe('unconnected');
    expect(before.lastConnectError).toBeNull();
    expect(await backendStore.connectDesktopBackend()).toBe(false);
    const after = backendStore.get();
    expect([after.mode, after.generation, after.adapter]).toEqual([before.mode, before.generation, before.adapter]);
    expect(after.adapter.info.kind).toBe('unavailable');
    expect(after.lastConnectError).toContain('桌面');
    expect(notified).toBe(1);
    off();
  });

  test('in the desktop app: probes health, connects with the probed options, clears the reason', async () => {
    const host2 = fakeHost();
    const generation = backendStore.get().generation;
    const ok = await withWindow(tauriWindow(host2.invoke), () => backendStore.connectDesktopBackend());
    expect(ok).toBe(true);
    const snap = backendStore.get();
    expect([snap.mode, snap.adapter.info.kind, snap.adapter.info.trains, snap.lastConnectError]).toEqual(['remote', 'remote', true, null]);
    expect(snap.generation).toBeGreaterThan(generation);
    expect(host2.seen.map((e) => e.method)).toEqual(['health']);
    // twoJudgements came from the flag: an exclamation with immediate=false goes out as given.
    const res = await withWindow(tauriWindow(host2.invoke), () => snap.adapter.submit({ text: 'x', partition: 'rational', immediate: false, exclamation: true }));
    expect(res.status).toBe('agreed');
    expect(host2.seen.at(-1)?.params).toMatchObject({ immediate: false, exclamation: true });
    expect([...(await withWindow(tauriWindow(host2.invoke), () => snap.adapter.capabilities()))]).toContain('inputPage');
    backendStore.disconnectRemote();
    expect([backendStore.get().mode, backendStore.get().lastConnectError]).toEqual(['unconnected', null]);
  });

  test('a back end without two_judgements connects with twoJudgements=false', async () => {
    const host = fakeHost({ ...FEATURES, two_judgements: false });
    const ok = await withWindow(tauriWindow(host.invoke), () => backendStore.connectDesktopBackend());
    expect(ok).toBe(true);
    const { adapter } = backendStore.get();
    expect(await withWindow(tauriWindow(host.invoke), () => codeOf(adapter.submit({ text: 'x', partition: 'rational', immediate: false })))).toBe('UNSUPPORTED');
    expect(host.seen.map((e) => e.method)).toEqual(['health']);
  });

  test('failures stay unconnected and say why; they never throw or fall back to the mock', async () => {
    const cases: [string, Invoke, string][] = [
      ['rejects', () => Promise.reject('ACL denied'), '桌面后端不可用'],
      ['throws', () => { throw new Error('boom'); }, '桌面后端不可用'],
      ['garbage', () => Promise.resolve('nope'), '后端'],
      ['host error envelope', async (_c, a) => ({ schema_version: 1, id: (a as { request: RequestEnvelope }).request.id, ok: false, error: { code: 'MODEL_UNAVAILABLE', message: 'python missing' } }), 'python missing'],
    ];
    for (const [name, invoke, expected] of cases) {
      const before = backendStore.get();
      const ok = await withWindow(tauriWindow(invoke), () => backendStore.connectDesktopBackend());
      const after = backendStore.get();
      expect(ok, name).toBe(false);
      expect([after.mode, after.generation, after.adapter], name).toEqual(['unconnected', before.generation, before.adapter]);
      expect(after.lastConnectError, name).toContain(expected);
      expect(after.adapter.info.kind, name).toBe('unavailable');
    }
    // The reason goes away with the next change of adapter.
    backendStore.enterDemo();
    expect(backendStore.get().lastConnectError).toBeNull();
  });

  test('a failed connect does not drop a demo the user entered, and a demo entered meanwhile wins', async () => {
    backendStore.enterDemo();
    const demo = backendStore.get();
    expect(await withWindow(tauriWindow(() => Promise.reject('no')), () => backendStore.connectDesktopBackend())).toBe(false);
    expect(backendStore.get().adapter).toBe(demo.adapter);
    expect(backendStore.get().mode).toBe('demo');

    backendStore.leaveDemo();
    const host = fakeHost();
    let release: () => void = () => undefined;
    const gate = new Promise<void>((r) => (release = r));
    const slow: Invoke = async (c, a) => {
      await gate;
      return host.invoke(c, a);
    };
    const pending = withWindow(tauriWindow(slow), () => backendStore.connectDesktopBackend());
    backendStore.enterDemo();
    const chosen = backendStore.get().adapter;
    release();
    expect(await pending).toBe(false);
    expect([backendStore.get().mode, backendStore.get().adapter]).toEqual(['demo', chosen]);
  });
});

// ---- the REAL Python back end, through a spawn-based Transport -------------------------------------

const BACKEND_DIR = fileURLToPath(new URL('../back-end-core', import.meta.url));

/** One JSON line per request over stdio, exactly like `core.api`; serial, with a deadline. */
class PythonBackend implements Transport {
  private readonly child;
  private readonly lines: string[] = [];
  private readonly waiting: ((line: string | null) => void)[] = [];
  private buffer = '';
  private chain: Promise<unknown> = Promise.resolve();
  private exited = false;

  constructor(dbPath: string) {
    this.child = spawn('python3', ['-B', '-s', '-u', '-m', 'core.api', '--db', dbPath], {
      cwd: BACKEND_DIR,
      env: { ...process.env, PYTHONDONTWRITEBYTECODE: '1' },
      stdio: ['pipe', 'pipe', 'pipe'],
    });
    this.child.stderr.on('data', () => undefined); // jieba prints progress; drain it
    this.child.stdout.setEncoding('utf8');
    this.child.stdout.on('data', (chunk: string) => {
      this.buffer += chunk;
      let at: number;
      while ((at = this.buffer.indexOf('\n')) >= 0) {
        const line = this.buffer.slice(0, at);
        this.buffer = this.buffer.slice(at + 1);
        const waiter = this.waiting.shift();
        if (waiter) waiter(line);
        else this.lines.push(line);
      }
    });
    this.child.on('exit', () => {
      this.exited = true;
      for (const w of this.waiting.splice(0)) w(null);
    });
    this.child.on('error', () => {
      this.exited = true;
      for (const w of this.waiting.splice(0)) w(null);
    });
  }

  private nextLine(timeoutMs: number): Promise<string> {
    const queued = this.lines.shift();
    if (queued !== undefined) return Promise.resolve(queued);
    if (this.exited) return Promise.reject(new Error('backend process exited'));
    return new Promise((resolveLine, reject) => {
      const timer = setTimeout(() => reject(new Error('backend timed out')), timeoutMs);
      this.waiting.push((line) => {
        clearTimeout(timer);
        if (line === null) reject(new Error('backend process exited'));
        else resolveLine(line);
      });
    });
  }

  request(envelope: RequestEnvelope): Promise<ResponseEnvelope> {
    const run = async (): Promise<ResponseEnvelope> => {
      this.child.stdin.write(`${JSON.stringify(envelope)}\n`);
      return JSON.parse(await this.nextLine(60_000)) as ResponseEnvelope;
    };
    const result = this.chain.then(run, run);
    this.chain = result.catch(() => undefined);
    return result;
  }

  async close(): Promise<void> {
    if (this.exited) return;
    const done = new Promise<void>((r) => this.child.once('exit', () => r()));
    this.child.stdin.end();
    await Promise.race([done, new Promise<void>((r) => setTimeout(r, 10_000))]);
    if (!this.exited) this.child.kill();
  }
}

let pythonSkip: string | null | undefined;
/** Why the real back end cannot run here, or null. Checked once: python3, the package, jieba and a health call. */
function pythonUnavailableReason(): string | null {
  if (pythonSkip !== undefined) return pythonSkip;
  if (!existsSync(join(BACKEND_DIR, 'core', 'api.py'))) return (pythonSkip = 'back-end-core is not present');
  const dir = mkdtempSync(join(tmpdir(), 'alpha-probe-'));
  try {
    const run = spawnSync('python3', ['-B', '-s', '-u', '-m', 'core.api', '--db', join(dir, 'probe.sqlite3')], {
      cwd: BACKEND_DIR,
      env: { ...process.env, PYTHONDONTWRITEBYTECODE: '1' },
      input: '{"schema_version":1,"id":"p","method":"health","params":{}}\n',
      encoding: 'utf8',
      timeout: 90_000,
    });
    if (run.error) return (pythonSkip = `python3 is not available (${run.error.message})`);
    const line = (run.stdout ?? '').split('\n').find((l) => l.startsWith('{')) ?? '';
    let ok = false;
    try {
      ok = JSON.parse(line).ok === true && JSON.parse(line).result.features?.two_judgements === true;
    } catch {
      ok = false;
    }
    return (pythonSkip = ok ? null : `the back end did not answer health (status ${run.status}); is jieba in ext-refs?`);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

/** A fresh back end on a temporary database under the OS temp directory (never back-end-core/data). */
async function withPython<T>(fn: (python: PythonBackend, sent: RequestEnvelope[]) => Promise<T>): Promise<T> {
  const dir = mkdtempSync(join(tmpdir(), 'alpha-py-'));
  const python = new PythonBackend(join(dir, 'brain.sqlite3'));
  const sent: RequestEnvelope[] = [];
  const recording: Transport = {
    request: (env) => {
      sent.push(env);
      return python.request(env);
    },
  };
  try {
    return await fn(recording as PythonBackend, sent);
  } finally {
    await python.close();
    rmSync(dir, { recursive: true, force: true });
  }
}

/** What a step shows of a decision, comparable between the mock and the real back end. */
function shape(r: { status: string; immediate?: boolean; confirm?: boolean | null; exclamation?: boolean; confirmed_by?: string | null; reason?: string | null; effects?: { action: string; parameter: string; before: number; after: number; support_before: number; support_after: number; span: readonly number[]; evidence: string; revision?: number; rule_id: string }[]; restored_fit?: boolean }) {
  return {
    meta: [r.status, r.immediate, r.confirm, r.exclamation, r.confirmed_by, r.reason],
    effects: (r.effects ?? []).map((e) => [
      e.action, e.parameter, e.before, e.after, e.support_before, e.support_after, [...e.span], e.evidence, e.revision ?? null,
      e.rule_id.replace(MOCK_RULE_PREFIX, ''),
    ]),
    restored: r.restored_fit ?? null,
  };
}

test.describe('the real Python back end', () => {
  test.describe.configure({ mode: 'serial', timeout: 180_000 });

  test('mock and real back end take the same steps: states, effects, revisions, stale cursors', async () => {
    const skip = pythonUnavailableReason();
    test.skip(skip !== null, skip ?? '');
    const text = '我重视公平。我坚持自由。';
    const script = async (a: BrainAdapter): Promise<unknown[]> => {
      const out: unknown[] = [];
      const revisionOf = async (): Promise<number> => (await a.inputPage({ limit: 1 })).revision;
      let revision = await revisionOf();
      const step = async (name: string, fn: () => Promise<unknown>): Promise<void> => {
        let value: unknown;
        try {
          value = shape((await fn()) as never);
        } catch (e) {
          value = e instanceof BackendError ? `error:${e.code}` : String(e);
        }
        const now = await revisionOf();
        out.push([name, value, now !== revision]);
        revision = now;
      };
      let id = '';
      await step('submit pending', async () => {
        const r = await a.submit({ text, partition: 'rational', kind: 'philosophy', immediate: true });
        id = r.source_id;
        return r;
      });
      await step('preview', () => a.preview(id));
      await step('T', () => a.confirm(id, true));
      await step('T again', () => a.confirm(id, true));
      await step('F on agreed', () => a.confirm(id, false));
      await step('F again', () => a.confirm(id, false));
      await step('preview after F', () => a.preview(id));
      await step('T restores', () => a.confirm(id, true));
      await step('revoke', () => a.revoke(id));
      await step('revoke again', () => a.revoke(id));
      await step('F on revoked', () => a.confirm(id, false));
      await step('preview revoked', () => a.preview(id));
      await step('T on revoked', () => a.confirm(id, true));
      let b = '';
      await step('submit immediate false', async () => {
        const r = await a.submit({ text, partition: 'emotional', kind: 'philosophy', immediate: false });
        b = r.source_id;
        return r;
      });
      await step('T on immediate false', () => a.confirm(b, true));
      await step('F on immediate false', () => a.confirm(b, false));
      await step('revoke immediate false', () => a.revoke(b));
      await step('preview immediate false', () => a.preview(b));
      await step('exclamation with immediate false', () => a.submit({ text, partition: 'crazy', kind: 'philosophy', immediate: false, exclamation: true }));
      await step('exclamation', () => a.submit({ text: '我重视真实。', partition: 'rational', kind: 'philosophy', immediate: true, exclamation: true }));
      await step('plain diary', () => a.submit({ text: '今天很平静。', partition: 'rational', immediate: true }));
      out.push(['state', await a.state()]);
      out.push(['effects', (await a.effects()).map((e) => shape({ status: 'x', effects: [e] }).effects[0])]);
      const rows = await a.inputList({ limit: 100 });
      // The real back end orders by created_at (whole seconds) and breaks ties by a random id, so inputs
      // submitted within one second come back in any order: compare the rows as sets.
      const asRow = (r: InputRecord): string =>
        JSON.stringify([r.status, r.immediate, r.confirm, r.exclamation, r.confirmed_by, r.reason, r.partition, r.kind, r.char_count, r.excerpt, r.edited_at]);
      out.push(['rows', rows.map(asRow).sort()]);
      const paged: string[] = [];
      const totals: number[] = [];
      let cursor: string | null = null;
      do {
        const page: Awaited<ReturnType<BrainAdapter['inputPage']>> = await a.inputPage({ limit: 2, cursor });
        paged.push(...page.items.map(asRow));
        totals.push(page.total);
        cursor = page.next_cursor;
      } while (cursor);
      out.push(['pages', totals, paged.sort()]);
      return out;
    };

    const mockOut = await script(new MockBrainAdapter());
    const realOut = await withPython(async (python) => {
      const probe = await RemoteBrainAdapter.probe(python);
      return script(new RemoteBrainAdapter(python, probe.options));
    });
    expect(realOut.length).toBe(mockOut.length);
    // Step by step, so a difference names the step.
    for (let i = 0; i < mockOut.length; i++) expect(mockOut[i], String((realOut[i] as unknown[])[0])).toEqual(realOut[i]);
  });

  test('probe, exclamation, spans over emoji, paging with STALE_CURSOR, F6 edit and delete', async () => {
    const skip = pythonUnavailableReason();
    test.skip(skip !== null, skip ?? '');
    await withPython(async (python, sent) => {
      const probe = await RemoteBrainAdapter.probe(python);
      expect(probe.options).toEqual({ twoJudgements: true, proposedMethods: true });
      expect(probe.methods).toHaveLength(23);
      expect(probe.features).toMatchObject({ two_judgements: true, input_pagination: true, source_edit: true, source_delete: true });
      expect(typeof probe.modelEpoch).toBe('number');
      expect(probe.capabilities.has('inputPage')).toBe(true);
      expect(probe.capabilities.has('inputEdit')).toBe(true);
      expect(probe.capabilities.has('inputDelete')).toBe(true);
      const a = new RemoteBrainAdapter(python, probe.options);
      expect(a.info.trains).toBe(true);
      expect([...(await a.capabilities())].sort()).toEqual([...probe.capabilities].sort());

      // Exclamation overrides immediate=false; the submit response carries the formal effects.
      const text = `${EMOJI}我重视公平。\r\n${RARE}我坚持自由。`;
      const r = await a.submit({ text, partition: 'emotional', kind: 'philosophy', immediate: false, exclamation: true });
      expect([r.status, r.immediate, r.confirm, r.exclamation, r.confirmed_by, r.reason]).toEqual(['agreed', true, true, true, 'exclamation', null]);
      expect(r.effects!.length).toBeGreaterThan(0);
      for (const e of r.effects!) {
        expect(e.revision).toBeGreaterThan(0);
        expect(e.rule_id.startsWith(MOCK_RULE_PREFIX)).toBe(false);
        expect(e.partition).toBe('emotional');
        expect(evidenceMatches(text, e), `${e.evidence} @ ${e.span}`).toBe(true);
        expect(codePointSlice(text, e.span)).toBe(e.evidence);
      }
      const detail = await a.inputGet(r.source_id);
      expect(detail.text).toBe(text); // CRLF and astral characters come back untouched
      expect(detail.char_count).toBe(codePointLength(text));
      expect((await a.state()).emotional['value.fairness'].observed).toBe(true);
      expect(await codeOf(a.preview(r.source_id))).toBe('INVALID_ARGUMENT');

      // Paging across a change of the inputs.
      for (let i = 0; i < 4; i++) await a.submit({ text: `今天第${i}天`, partition: 'rational', immediate: true });
      const before = sent.length;
      const first = await a.inputPage({ limit: 2 });
      expect([first.total, first.items.length, typeof first.next_cursor]).toEqual([5, 2, 'string']);
      expect(first.items.every((row) => row.excerpt.length > 0)).toBe(true);
      expect(sent.slice(before).map((e) => e.method)).toEqual(['input_page']); // the summaries are complete: no input_get
      const second = await a.inputPage({ limit: 2, cursor: first.next_cursor });
      expect(second.items.map((row) => row.source_id)).not.toContain(first.items[0].source_id);
      await a.submit({ text: '又一条', partition: 'rational', immediate: true });
      expect(await codeOf(a.inputPage({ limit: 2, cursor: second.next_cursor }))).toBe('STALE_CURSOR');
      expect((await a.inputPage({ limit: 2 })).total).toBe(6);
      expect(await codeOf(a.inputPage({ limit: 2, partition: 'emotional', cursor: second.next_cursor }))).toBe('INVALID_ARGUMENT');

      // F6: edit an agreed input is refused (revoke first), then edit, then delete any status.
      expect(await codeOf(a.inputEdit(r.source_id, { text: 'x', immediate: true }))).toBe('INVALID_ARGUMENT');
      const fresh = await a.submit({ text: '会被编辑和删除的一条', partition: 'rational', immediate: true });
      const edited = await a.inputEdit(fresh.source_id, { text: '改过的一条', immediate: true });
      expect([edited.status, edited.confirm, edited.edited_at === null, edited.excerpt]).toEqual(['pending', null, false, '改过的一条']);
      expect(await codeOf(a.inputEdit(fresh.source_id, { text: 'a\u0000b', immediate: true }))).toBe('INVALID_ARGUMENT');
      await a.inputDelete(fresh.source_id);
      expect(await codeOf(a.inputGet(fresh.source_id))).toBe('NOT_FOUND');
      expect(await codeOf(a.inputDelete(fresh.source_id))).toBe('NOT_FOUND');
      expect(await codeOf(a.confirm('0'.repeat(32), true))).toBe('NOT_FOUND');
    });
  });
});

// ---- fixes of the 2026-10-01 verification -----------------------------------------------------------

/** Milliseconds `fn` takes (best of two runs, so one GC pause cannot fail it). */
function timeOf(fn: () => unknown): number {
  let best = Infinity;
  for (let i = 0; i < 2; i++) {
    const t0 = performance.now();
    fn();
    best = Math.min(best, performance.now() - t0);
  }
  return best;
}

test.describe('whitespace handling is linear (a pasted run of spaces must not freeze the page)', () => {
  const N = 200_000;
  // The old trailing regex took 30 s for 100k; 1.5 s here is generous even on a loaded machine.
  const LIMIT_MS = 1500;

  test('pyStrip / pyLstrip / isBlank / validateEntry on a 200k-space run followed by a letter', () => {
    for (const ws of [' ', '\n', '\u3000', '\t\r']) {
      const text = 'a' + ws.repeat(N) + 'x';
      expect(timeOf(() => pyStrip(text)), `pyStrip ${JSON.stringify(ws)}`).toBeLessThan(LIMIT_MS);
      expect(timeOf(() => isBlank(text))).toBeLessThan(LIMIT_MS);
      expect(timeOf(() => validateEntry({ text, partition: 'rational', kind: 'diary' }))).toBeLessThan(LIMIT_MS);
      const padded = ws.repeat(N) + 'x' + ws.repeat(N);
      expect(timeOf(() => pyStrip(padded))).toBeLessThan(LIMIT_MS);
      expect(pyStrip(padded)).toBe('x');
      expect(pyLstrip(padded)).toBe('x' + ws.repeat(N));
      expect(timeOf(() => isBlank(ws.repeat(N)))).toBeLessThan(LIMIT_MS);
    }
    expect(validateEntry({ text: 'a' + ' '.repeat(N) + 'x', partition: 'rational', kind: 'diary' }).errors).toEqual([]);
  });

  test('the lookup equals Python str.isspace on every UTF-16 unit and keeps the PY_WS regex class in step', () => {
    const cls = new RegExp(`^[${PY_WS}]$`, 'u');
    const mismatches: string[] = []; // one expect for all 65k units: a per-unit expect is slow under load
    for (let c = 0; c <= 0xffff; c++) {
      if (c >= 0xd800 && c <= 0xdfff) continue;
      if (isPyWhitespace(c) !== cls.test(String.fromCharCode(c))) mismatches.push(`U+${c.toString(16)}`);
    }
    expect(mismatches).toEqual([]);
    // 29 code points, as Python reports them.
    let count = 0;
    for (let c = 0; c <= 0xffff; c++) if (isPyWhitespace(c)) count++;
    expect(count).toBe(29);
    // Not JavaScript's \s: U+FEFF is not Python whitespace, U+001C..U+001F and U+0085 are.
    expect([isPyWhitespace(0xfeff), isPyWhitespace(0x1c), isPyWhitespace(0x85)]).toEqual([false, true, true]);
    expect(pyStrip('\u0085\u001ca b\u2029 ')).toBe('a b');
    expect(pyStrip('\ufeffa')).toBe('\ufeffa');
  });

  test('mockExtract / mockTranslate on 200k spaces and on one long segment of cue words stay fast', () => {
    const spaced = '我重视公平' + ' '.repeat(N) + '我很失望';
    expect(timeOf(() => mockExtract(spaced, 'diary', null))).toBeLessThan(LIMIT_MS);
    // 失望 x 80,000 in ONE segment (no sentence terminator): the cue lookbehind is a 32-character window.
    const cues = '失望'.repeat(80_000);
    expect(timeOf(() => mockTranslate(cues, 'diary', null))).toBeLessThan(LIMIT_MS);
    expect(mockTranslate('我没有失望，别人说他失望', 'diary', null).cues.map((c) => [c.value, c.negated])).toEqual([['disappointment', true], ['disappointment', false]]);
  });
});

test.describe('NUL, BOM and file size edge cases', () => {
  const base = { partition: 'rational', kind: 'diary' } as const;

  test('hasNul: U+0000 anywhere (the back end refuses it in any position, nothing is stripped)', () => {
    expect([hasNul('\u0000'), hasNul('  \u0000x'), hasNul('\u0000我重视成长。'), hasNul('\n\u0000x'), hasNul('a\u0000'), hasNul('a\u0000b')]).toEqual([true, true, true, true, true, true]);
    expect([hasNul('x'), hasNul(''), hasNul(' \u3000')]).toEqual([false, false, false]);
    expect(() => normalizeForSubmit('a\u0000b')).toThrow(/空字符/);
  });

  test('validateEntry blocks a NUL anywhere and treats a text blank after the BOM as empty', () => {
    expect(validateEntry({ ...base, text: '\u0000我重视成长。' }).errors).toHaveLength(1);
    expect(validateEntry({ ...base, text: '  \u0000x' }).errors[0]).toContain('空字符');
    expect(validateEntry({ ...base, text: '\ufeff\u0000x' }).errors).toHaveLength(1); // the BOM is dropped before sending
    expect(validateEntry({ ...base, text: 'a\u0000b' }).errors).toHaveLength(1);
    expect(validateEntry({ ...base, text: '\n\u0000x' }).errors).toHaveLength(1);
    expect(validateEntry({ ...base, text: '\ufeff' }).errors).toEqual(['内容不能为空']);
    expect(validateEntry({ ...base, text: '\ufeff   \n' }).errors).toEqual(['内容不能为空']);
    expect(validateEntry({ ...base, text: '\ufeff\ufeff' }).errors).toEqual([]); // a second FEFF is text, as in the back end
    expect(validateEntry({ ...base, text: '\ufeffx' }).errors).toEqual([]);
    // The length limit is judged on what is sent.
    expect(validateEntry({ ...base, text: '\ufeff' + 'x'.repeat(MAX_INPUT_CHARS) }).errors).toEqual([]);
  });

  test('the mock refuses U+0000 in any position, like the real back end (INVALID_ARGUMENT)', async () => {
    const m = mock();
    for (const text of ['\u0000', '\u0000我重视公平。', '  \u0000我重视公平。', '\n\u0000x', 'a\u0000', 'y\u0000']) {
      expect(await codeOf(m.submit({ text, partition: 'rational', immediate: true })), JSON.stringify(text)).toBe('INVALID_ARGUMENT');
    }
    // Edit goes through the same check.
    const r = await m.submit({ text: 'ok', partition: 'rational', immediate: true });
    expect(await codeOf(m.inputEdit(r.source_id, { text: 'a\u0000x', immediate: true }))).toBe('INVALID_ARGUMENT');
  });

  test('the mock rejects a blank source_ref like the back end, and accepts null / absent', async () => {
    const m = mock();
    for (const source_ref of ['', '   ', '\n\t']) {
      expect(await codeOf(m.submit({ text: FAIR, partition: 'rational', immediate: true, source_ref })), JSON.stringify(source_ref)).toBe('INVALID_ARGUMENT');
    }
    expect(await codeOf(m.submit({ text: FAIR, partition: 'rational', immediate: true, source_ref: 5 as never }))).toBe('INVALID_ARGUMENT');
    expect((await m.submit({ text: FAIR, partition: 'rational', immediate: true, source_ref: null as never })).status).toBe('pending');
    expect((await m.submit({ text: FAIR, partition: 'rational', immediate: true, source_ref: 'a.txt' })).status).toBe('pending');
    expect((await m.submit({ text: FAIR, partition: 'rational', immediate: true })).status).toBe('pending');
  });

  test('readTextFile refuses a file with NUL characters, e.g. UTF-16 without a BOM', async () => {
    const utf16be = bytes([0x00, 0x6f, 0x00, 0x6b]); // "ok" as UTF-16BE: valid UTF-8, but NUL, 'o', NUL, 'k'
    const err = await readTextFile(file('u16.txt', utf16be)).catch((e: unknown) => e);
    expect((err as { code: string }).code).toBe('INVALID_UTF8');
    expect((err as Error).message).toContain('UTF-16');
    const mid = await readTextFile(file('mid.txt', bytes('a', [0x00], 'b'))).catch((e: unknown) => e);
    expect((mid as { code: string }).code).toBe('INVALID_UTF8');
    expect((await readTextFile(file('fine.txt', '我重视成长。'))).text).toBe('我重视成长。');
  });

  test('a BOM does not count against the size limit: BOM + 1,000,000 emoji is readable', async () => {
    const body = new Uint8Array(MAX_FILE_BYTES);
    for (let i = 0; i < MAX_INPUT_CHARS; i++) body.set([0xf0, 0x9f, 0x98, 0x80], i * 4);
    const withBom = new Uint8Array(MAX_FILE_BYTES + 3);
    withBom.set([0xef, 0xbb, 0xbf], 0);
    withBom.set(body, 3);
    const r = await readTextFile(file('max.txt', withBom));
    expect(codePointLength(r.text)).toBe(MAX_INPUT_CHARS);
    expect(validateEntry({ partition: 'rational', kind: 'diary', text: r.text }).errors).toEqual([]);
    expect((await readTextFile(file('max2.txt', body))).text.length).toBe(MAX_INPUT_CHARS * 2);
    // One byte more than the BOM allows, or three extra bytes without a BOM, are still too large.
    const tooBig = new Uint8Array(MAX_FILE_BYTES + 4).fill(0x61);
    tooBig.set([0xef, 0xbb, 0xbf], 0);
    expect(((await readTextFile(file('a.txt', tooBig)).catch((e: unknown) => e)) as { code: string }).code).toBe('TOO_LARGE');
    const noBom = new Uint8Array(MAX_FILE_BYTES + 3).fill(0x61);
    expect(((await readTextFile(file('b.txt', noBom)).catch((e: unknown) => e)) as { code: string }).code).toBe('TOO_LARGE');
    // A liar of a File-like with a BOM is caught after reading as well.
    const liar = { name: 'x.txt', size: 1, arrayBuffer: async () => tooBig.buffer as ArrayBuffer };
    expect(((await readTextFile(liar).catch((e: unknown) => e)) as { code: string }).code).toBe('TOO_LARGE');
  });
});

test.describe('the ported rules equal the real ones (read-only look at back-end-core)', () => {
  test('every ported regex source equals the Python pattern', () => {
    const skip = existsSync(join(BACKEND_DIR, 'model', 'evidence.py')) ? null : 'back-end-core is not present';
    test.skip(skip !== null, skip ?? '');
    const code = [
      'import json',
      'from model import evidence as e',
      'from translator import discourse as d, pipeline as p',
      'print(json.dumps({"_BOUNDARY": e._BOUNDARY.pattern, "_FIRST_PERSON": e._FIRST_PERSON.pattern, "_DIRECT": e._DIRECT.pattern,',
      ' "_IMPORTANCE": e._IMPORTANCE.pattern, "_NORMATIVE": e._NORMATIVE.pattern, "_NEGATIVE": e._NEGATIVE.pattern,',
      ' "_NEGATIVE_NORMATIVE": e._NEGATIVE_NORMATIVE.pattern, "_ANTI": e._ANTI.pattern, "_SOFT_BOUNDARY": d._SOFT_BOUNDARY.pattern,',
      ' "_SEGMENT": p._SEGMENT.pattern, "_LESS_CONTACT": p._LESS_CONTACT.pattern, "_CONTACT_VERB": p._CONTACT_VERB.pattern,',
      ' "_REPORTED": p._REPORTED.pattern}, ensure_ascii=False))',
    ].join('\n');
    const run = spawnSync('python3', ['-B', '-s', '-c', code], {
      cwd: BACKEND_DIR,
      env: { ...process.env, PYTHONDONTWRITEBYTECODE: '1', PYTHONPATH: BACKEND_DIR },
      encoding: 'utf8',
      timeout: 60_000,
    });
    test.skip(run.status !== 0, `python3 cannot import the rules (${(run.stderr ?? '').split('\n').slice(-2)[0] ?? run.error?.message})`);
    const python = JSON.parse(run.stdout) as Record<string, string>;
    expect(Object.keys(PORTED_PATTERNS).sort()).toEqual(Object.keys(python).sort());
    for (const [name, source] of Object.entries(PORTED_PATTERNS)) expect(source, name).toBe(python[name]);
  });
});

test.describe('mock vs the real back end on rejected input', () => {
  test.describe.configure({ timeout: 180_000 });

  test('a NUL anywhere and a blank source_ref are refused by both, with the same error codes', async () => {
    const skip = pythonUnavailableReason();
    test.skip(skip !== null, skip ?? '');
    const cases: { name: string; req: { text: string; source_ref?: string } }[] = [
      { name: 'NUL', req: { text: '\u0000' } },
      { name: 'NUL then text', req: { text: '\u0000我重视公平。' } },
      { name: 'spaces then NUL', req: { text: '  \u0000我重视公平。' } },
      { name: 'newline then NUL', req: { text: '\n\u0000x' } },
      { name: 'NUL inside', req: { text: 'a\u0000b我重视公平。' } },
      { name: 'trailing NUL', req: { text: 'a\u0000' } },
      { name: 'blank source_ref', req: { text: FAIR, source_ref: '   ' } },
      { name: 'empty source_ref', req: { text: FAIR, source_ref: '' } },
      { name: 'good source_ref', req: { text: FAIR, source_ref: 'a.txt' } },
    ];
    const run = async (a: BrainAdapter): Promise<string[]> => {
      const out: string[] = [];
      for (const c of cases) {
        try {
          out.push((await a.submit({ ...c.req, partition: 'rational', kind: 'diary', immediate: true })).status);
        } catch (e) {
          out.push(e instanceof BackendError ? e.code : String(e));
        }
      }
      return out;
    };
    const mockOut = await run(mock());
    const realOut = await withPython(async (python) => {
      const probe = await RemoteBrainAdapter.probe(python);
      return run(new RemoteBrainAdapter(python, probe.options));
    });
    expect(mockOut).toEqual(realOut);
    expect(mockOut).toEqual(['INVALID_ARGUMENT', 'INVALID_ARGUMENT', 'INVALID_ARGUMENT', 'INVALID_ARGUMENT', 'INVALID_ARGUMENT', 'INVALID_ARGUMENT', 'INVALID_ARGUMENT', 'INVALID_ARGUMENT', 'pending']);
  });
});
