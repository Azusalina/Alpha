/**
 * MockBrainAdapter — a demonstration double of the back end (D56). It MIMICS,
 * it does not learn: nothing here fits a model, nothing is persisted, a page
 * reload forgets everything, and `info.trains` is always false. The UI shows
 * the permanent label "演示数据 · 未运行模型" whenever it is the active adapter,
 * and every `rule_id` it emits starts with `mock.`, so no effect it produces
 * can be mistaken for a real one.
 *
 * What is faithful: the response shapes of `back-end-core` api.md, the
 * arithmetic (`score = net / (support + 4)`, one contribution per parameter per
 * source, state per partition, monotonic revisions, reversal effects, exact
 * recomputation from the remaining agreed inputs) and the code point spans of
 * the ORIGINAL text. What is simplified: the extraction rules. A port of
 * `model/evidence.py` + `translator/pipeline.py` covers (a) first-person value
 * statements -> `value.*` (negative importance gives a negative contribution),
 * (b) non-negated first-person emotion words -> `affect.*`, (c) an explicit
 * reduced-contact intention -> `expression.less_initiative`. No personal
 * vocabulary (`translator_effects` is always empty), no learned corrections,
 * no jieba. Its translations say so: `limitations` contains `mock_rules_only`.
 *
 * NOT ported: the real back end's non-assertion protection (translator/discourse.py
 * `AssertionGuards`: quotations and code, questions, hypotheticals, reported speech,
 * other people's values) and the ambiguity withholding of evidence.py (nested
 * negation, comparisons, opposition), and so `interpretation` has no
 * `evidence_policy` / `withheld_*`. For the same text the demo can therefore
 * extract effects the real back end deliberately withholds, e.g. a question or a
 * quotation of a value word. The patterns that ARE ported equal evidence.py
 * (checked in tests/backend.spec.ts against the Python source) and a contact
 * intention is narrowed to its clause like `guards.clause_span`. The limitation
 * `mock_no_assertion_guards` says this in every translation; a surface that
 * shows demo effects should say it too.
 *
 * The two-judgement state machine (D55, front-back-communicate.md F1-F7) mirrors
 * `model/engine.py` (`submit_result`, `_review`, `_deactivate`, `preview`) as the
 * back end implements it since 2026-10-01; only edit/delete (F6) are mock-only:
 *
 *   submit  immediate=false                 -> disagreed (immediate_false)
 *   submit  immediate=true                  -> pending
 *   submit  exclamation (with or without immediate)
 *                                           -> immediate AND confirm set true by the
 *                                              exclamation itself, agreed at once
 *                                              (confirmed_by exclamation), formal effects
 *   confirm on immediate=false              -> INVALID_ARGUMENT (edit it first)
 *   confirm(true)  from pending / confirm_false / revoked
 *                                           -> agreed (manual); the first time the fit is
 *                                              extracted and frozen, every later time the
 *                                              FROZEN contributions are restored (nothing
 *                                              re-extracted, support never counted twice)
 *   confirm(false) from pending             -> disagreed (confirm_false, manual), no effects
 *   confirm(false) from agreed              -> disagreed (confirm_false); reversal effects
 *                                              (action revoke) remove its contributions
 *   the same judgement again                -> no-op: no effects, no new revision, no event
 *   revoke         from agreed only         -> revoked (user_revoked), reversal effects
 *   preview        any input that is not agreed (immediate_false included; it is
 *                                              hypothetical and never authorises a review)
 *   inputEdit (F6, mock only) -> only when not agreed; inputDelete (F6, mock only) -> any status, history included
 *
 * Training is possible only when `isTrainable`: the model state is always
 * recomputed from the agreed inputs, so no other transition can change it.
 *
 * Pure module: no React, DOM or three. Deterministic given `now` and `newId`.
 */

import { CodePointIndex, codePointLength, codePointSlice, hasLoneSurrogate } from './spans';
import { isBlank, leadingNul, parseChatLine, pyLstrip, pyStrip, PY_WS, splitLines } from './text';
import {
  BackendError,
  KINDS,
  MAX_INPUT_CHARS,
  MOCK_RULE_PREFIX,
  PARAMETER_IDS,
  PARTITIONS,
} from './types';
import type {
  AdapterInfo,
  AdapterMethod,
  BrainAdapter,
  ConfirmedBy,
  DecisionMetadata,
  InputDetail,
  InputEditRequest,
  InputListQuery,
  InputPage,
  InputPageQuery,
  InputReason,
  InputRecord,
  InputStatus,
  Interpretation,
  Kind,
  ModelState,
  ParameterEffect,
  ParameterId,
  Partition,
  PartitionState,
  PreviewResult,
  RankResult,
  ReviewResult,
  SubmitRequest,
  SubmitResult,
  Translation,
  TranslationCandidate,
  TranslationCue,
} from './types';
import { ADAPTER_METHODS } from './types';

export const MOCK_LABEL = '演示数据 · 未运行模型';
/** Same constant as `model.catalog.PRIOR_STRENGTH`. */
const PRIOR_STRENGTH = 4;
const EXCERPT_CHARS = 80;

// ---- simplified extraction rules (port of evidence.py / pipeline.py) ------------------

const WS = PY_WS;
const R = (source: string, flags = 'su'): RegExp => new RegExp(source, flags);

const BOUNDARY = R('[。！？!?；;，,\\n]|但(?:是)?|不(?:过|過)|而(?:是)?|却|卻', 'gu');
const FIRST_PERSON = R('我(?:也|仍然|一直)?(?:不|没|沒|沒有|没有)?(?:认为|認為|觉得|覺得|相信|重视|重視|看重|珍惜|坚持|堅持)|(?:对|對)我来[说說]');
const DIRECT = R('我(?:也|仍然|一直)?(?:不|没|沒|沒有|没有)?(?:重视|重視|看重|珍惜|坚持|堅持)');
const IMPORTANCE = R('重要|优先|優先|值得');
const NORMATIVE = R('(?:应该|應該|应当|應當|必须|必須)(?:[^。！？!?；;，,]{0,3})');
const NEGATIVE = R('(?:不|没|沒|沒有|没有)(?:重视|重視|看重|珍惜)|我不(?:认为|認為|觉得|覺得|相信)|不重要|不太重要|没那么重要|沒那麼重要|沒有那麼重要');
const NEGATIVE_NORMATIVE = R('不(?:应该|應該|应当|應當|必須|必须)');
const ANTI = R('反对|反對|拒绝|拒絕|排斥');
const REPORTED_VALUE = R('(?:他|她|有人|朋友|阿[\\u3400-\\u9fff]{1,3})(?:说|說|觉得|覺得|认为|認為|重视|重視)');

/** `model.catalog.VALUE_WORDS`. */
const VALUE_WORDS: Record<string, readonly string[]> = {
  'value.autonomy': ['自由', '自主', '自我决定', '自我決定'],
  'value.fairness': ['公平', '公正'],
  'value.care': ['关怀', '關懷', '照顾', '照顧', '善待'],
  'value.truth': ['真实', '真實', '诚实', '誠實', '真相'],
  'value.security': ['安全', '稳定', '穩定'],
  'value.growth': ['成长', '成長', '学习', '學習', '进步', '進步'],
  'value.achievement': ['成就', '成果', '成功'],
  'value.connection': ['陪伴', '归属', '歸屬', '联结', '連結'],
};

const SEGMENT = R('[^。！？!?；;]+', 'gu');
const CUE_RULES: readonly (readonly [string, string, string])[] = [
  ['event_word', 'cancellation', '取消|放鴿子|放鸽子'],
  ['frequency_word', 'claimed_repetition', '又|總是|总是|每次'],
  ['contrast_word', 'contrast', '但(?:是)?|不過|不过|其實|其实'],
  ['uncertainty_word', 'hedge', '可能|也許|也许|或許|或许|大概'],
  ['emotion_word', 'disappointment', '失望'],
  ['emotion_word', 'sadness', '難過|难过|傷心|伤心'],
  ['emotion_word', 'happiness', '開心|开心|高興|高兴'],
  ['emotion_word', 'anger', '生氣|生气|憤怒|愤怒'],
];
const HEDGE = R('可能|也許|也许|或許|或许|大概');
/** `guards._SOFT_BOUNDARY`: where a contact intention's clause ends. */
const SOFT_BOUNDARY = R('[，,]|但(?:是)?|不(?:过|過)|而(?:是)?|却|卻', 'gu');
const NEGATION = R(`(?:不|沒|没|沒有|没有|無|无|未)[${WS}]{0,2}$`);
const THIRD_PERSON = R(`(?:他|她|別人|别人|朋友|同事|阿[^${WS}，,。；;]{1,3}).{0,12}$`);
const REPORTED_CUE = R('(?:他|她|別人|别人|朋友|同事).{0,6}(?:說|说|表示).{0,12}$');
const FIRST_PERSON_OBJECT = R('我(?:對|对).{0,8}$');
const LESS_CONTACT = R(
  '(?:不會|不会|不想|不再|少|減少|减少).{0,6}(?:主動|主动)|(?:主動|主动).{0,6}(?:不會|不会|不想|不再|少|減少|减少)',
);
const CONTACT_VERB = R('約|约|聯繫|联系|找');
const SELF_WORD = R('我|自己');
const THEY_INITIATIVE = R('(?:他|她).{0,8}(?:主動|主动)');

/**
 * The ported patterns by their Python name, for the parity test (it compares each
 * source with the `re.compile(r"...")` in the back end's own files).
 */
export const PORTED_PATTERNS: Readonly<Record<string, string>> = {
  _BOUNDARY: BOUNDARY.source,
  _FIRST_PERSON: FIRST_PERSON.source,
  _DIRECT: DIRECT.source,
  _IMPORTANCE: IMPORTANCE.source,
  _NORMATIVE: NORMATIVE.source,
  _NEGATIVE: NEGATIVE.source,
  _NEGATIVE_NORMATIVE: NEGATIVE_NORMATIVE.source,
  _ANTI: ANTI.source,
  _SOFT_BOUNDARY: SOFT_BOUNDARY.source,
  _SEGMENT: SEGMENT.source,
  _LESS_CONTACT: LESS_CONTACT.source,
  _CONTACT_VERB: CONTACT_VERB.source,
  _REPORTED: REPORTED_CUE.source,
};

interface Seg {
  text: string;
  /** UTF-16 index in the whole text. */
  start: number;
}

/** `evidence._split_segments`: clause segments with their UTF-16 start. */
function* splitSegments(text: string, base: number): Generator<Seg> {
  let start = 0;
  const emit = function* (piece: string, pieceStart: number): Generator<Seg> {
    if (!isBlank(piece)) {
      const leading = piece.length - pyLstrip(piece).length;
      yield { text: pyStrip(piece), start: base + pieceStart + leading };
    }
  };
  for (const m of text.matchAll(BOUNDARY)) {
    const at = m.index as number;
    yield* emit(text.slice(start, at), start);
    start = at + m[0].length;
  }
  yield* emit(text.slice(start), start);
}

/** `evidence.authored_segments`: the whole text, or only the self speaker's lines of a chat. */
function* authoredSegments(text: string, kind: Kind, selfSpeaker: string | null): Generator<Seg> {
  if (kind !== 'chat') {
    yield* splitSegments(text, 0);
    return;
  }
  for (const line of splitLines(text)) {
    const parsed = parseChatLine(line.bare);
    if (parsed && parsed.speaker === selfSpeaker) {
      yield* splitSegments(parsed.content, line.start + parsed.contentStart);
    }
  }
}

interface Part extends Seg {
  speaker: string;
}

/** `pipeline._parts`. */
function translatorParts(
  text: string,
  kind: 'diary' | 'chat',
  selfSpeaker: string | null,
  ix: CodePointIndex,
): { parts: Part[]; skipped: Translation['skipped'] } {
  const parts: Part[] = [];
  const skipped: Translation['skipped'] = [];
  for (const line of splitLines(text)) {
    let content: string;
    let base: number;
    if (kind === 'chat') {
      const parsed = parseChatLine(line.bare);
      if (!parsed) {
        if (!isBlank(line.bare)) {
          skipped.push({
            span: [ix.fromUtf16(line.start), ix.fromUtf16(line.start + line.bare.length)],
            reason: 'unlabeled_chat_line',
          });
        }
        continue;
      }
      if (parsed.speaker !== selfSpeaker) continue;
      content = parsed.content;
      base = line.start + parsed.contentStart;
    } else {
      content = line.bare;
      base = line.start;
    }
    for (const m of content.matchAll(SEGMENT)) {
      const value = pyStrip(m[0]);
      if (!value) continue;
      const leading = m[0].length - pyLstrip(m[0]).length;
      parts.push({ text: value, start: base + (m.index as number) + leading, speaker: selfSpeaker || 'author' });
    }
  }
  return { parts, skipped };
}

/** `translator.translate`, simplified. Spans are code points of the original `text`. */
export function mockTranslate(text: string, kind: Kind, selfSpeaker: string | null): Translation {
  const ix = new CodePointIndex(text);
  const tKind: 'diary' | 'chat' = kind === 'chat' ? 'chat' : 'diary';
  const { parts, skipped } = translatorParts(text, tKind, selfSpeaker, ix);
  const cues: TranslationCue[] = [];
  const candidates: TranslationCandidate[] = [];
  for (const part of parts) {
    const seg = part.text;
    const hedged = HEDGE.test(seg);
    for (const [category, value, source] of CUE_RULES) {
      for (const m of seg.matchAll(new RegExp(source, 'gu'))) {
        const at = m.index as number;
        // pipeline.py looks back at most 32 characters: the end-anchored patterns below need
        // far less, and copying the whole prefix per cue was quadratic in a long segment.
        const before = seg.slice(Math.max(0, at - 32), at);
        const negated = category === 'emotion_word' && NEGATION.test(before);
        const span: [number, number] = [ix.fromUtf16(part.start + at), ix.fromUtf16(part.start + at + m[0].length)];
        cues.push({ category, value, evidence: m[0], span, speaker: part.speaker, negated });
        if (category !== 'emotion_word' || negated) continue;
        // Quoted or reported feelings are not evidence of the writer's mood.
        const clause = before.split(/[，,、]/).pop() as string;
        const firstPersonObject = FIRST_PERSON_OBJECT.test(clause);
        if (REPORTED_CUE.test(clause) || (THIRD_PERSON.test(clause) && !firstPersonObject)) continue;
        candidates.push({
          type: 'textual_emotion',
          value,
          evidence: m[0],
          span,
          speaker: part.speaker,
          certainty: hedged ? 'hedged' : 'explicit_word',
          status: 'pending_review',
        });
      }
    }
    const intent = LESS_CONTACT.exec(seg);
    if (intent) {
      // `guards.clause_span`: the clause around the intention between soft boundaries
      // (commas, 但, 不过, 而, 却), clipped to the segment and trimmed.
      let left = 0;
      let right = seg.length;
      for (const b of seg.matchAll(SOFT_BOUNDARY)) {
        const bStart = b.index as number;
        const bEnd = bStart + b[0].length;
        if (bEnd <= intent.index) left = bEnd;
        else if (bStart > intent.index) {
          right = bStart;
          break;
        }
      }
      const raw = seg.slice(left, right);
      const trimmedLeft = left + (raw.length - pyLstrip(raw).length);
      const intentText = pyStrip(raw);
      const trimmedRight = trimmedLeft + intentText.length;
      if (
        CONTACT_VERB.test(intentText) &&
        SELF_WORD.test(intentText) &&
        !THEY_INITIATIVE.test(intentText) &&
        !REPORTED_CUE.test(intentText.slice(0, intent.index - trimmedLeft))
      ) {
        candidates.push({
          type: 'contact_intention',
          value: 'less_initiative',
          evidence: intentText,
          span: [ix.fromUtf16(part.start + trimmedLeft), ix.fromUtf16(part.start + trimmedRight)],
          speaker: part.speaker,
          certainty: hedged ? 'hedged' : 'explicit_word',
          status: 'pending_review',
        });
      }
    }
  }
  return {
    schema_version: 1,
    kind: tKind,
    self_speaker: selfSpeaker,
    cues,
    candidates,
    skipped,
    limitations: ['lexical_rules_only', 'no_trait_or_diagnosis', 'mock_rules_only', 'mock_no_assertion_guards'],
  };
}

export interface MockContribution {
  parameter: ParameterId;
  sign: 1 | -1;
  evidence: string;
  /** Code points, end exclusive. */
  span: readonly [number, number];
  /** Always starts with `mock.`. */
  rule_id: string;
}

const EMOTION_PARAMETER: Record<string, ParameterId> = {
  disappointment: 'affect.disappointment',
  sadness: 'affect.sadness',
  happiness: 'affect.happiness',
  anger: 'affect.anger',
};

/** `evidence.extract_contributions`, simplified: at most one per parameter, none on conflict. */
export function mockExtract(text: string, kind: Kind, selfSpeaker: string | null): MockContribution[] {
  const ix = new CodePointIndex(text);
  const pool = new Map<ParameterId, MockContribution[]>();
  const add = (c: MockContribution): void => {
    const list = pool.get(c.parameter);
    if (list) list.push(c);
    else pool.set(c.parameter, [c]);
  };

  for (const { text: segment, start } of authoredSegments(text, kind, selfSpeaker)) {
    if (!segment || REPORTED_VALUE.test(segment)) continue;
    const explicit = FIRST_PERSON.test(segment) || DIRECT.test(segment);
    if (!explicit && kind !== 'philosophy') continue;
    if (!(DIRECT.test(segment) || IMPORTANCE.test(segment) || (kind === 'philosophy' && NORMATIVE.test(segment)))) continue;
    if (kind === 'philosophy' && NORMATIVE.test(segment) && (NEGATIVE_NORMATIVE.test(segment) || ANTI.test(segment))) {
      // Nested negation and normative opposition need deeper semantics.
      continue;
    }
    const comparative = segment.includes('比');
    const negative = NEGATIVE.test(segment) || NEGATIVE_NORMATIVE.test(segment);
    if (comparative && negative) continue;
    const winner = comparative ? segment.split('比', 1)[0] : '';
    for (const [parameter, words] of Object.entries(VALUE_WORDS)) {
      if (!words.some((w) => segment.includes(w))) continue;
      if (comparative && !words.some((w) => winner.includes(w))) continue;
      const sign = negative && !comparative ? -1 : 1;
      const rule = comparative ? 'comparative_value_preference' : sign < 0 ? 'negated_value_statement' : 'explicit_value_statement';
      add({
        parameter: parameter as ParameterId,
        sign,
        evidence: segment,
        span: [ix.fromUtf16(start), ix.fromUtf16(start + segment.length)],
        rule_id: MOCK_RULE_PREFIX + rule,
      });
    }
  }

  for (const item of mockTranslate(text, kind, selfSpeaker).candidates) {
    if (item.type === 'textual_emotion') {
      const parameter = EMOTION_PARAMETER[item.value];
      if (parameter) add({ parameter, sign: 1, evidence: item.evidence, span: item.span, rule_id: `${MOCK_RULE_PREFIX}textual_emotion_cue` });
    } else if (item.type === 'contact_intention') {
      add({
        parameter: 'expression.less_initiative',
        sign: 1,
        evidence: item.evidence,
        span: item.span,
        rule_id: `${MOCK_RULE_PREFIX}contact_intention_cue`,
      });
    }
  }

  const out: MockContribution[] = [];
  for (const items of pool.values()) {
    // Contradictory claims in one source do not move a parameter.
    if (items.some((i) => i.sign === 1) && items.some((i) => i.sign === -1)) continue;
    out.push(items[0]);
  }
  return out.sort((a, b) => a.span[0] - b.span[0] || (a.parameter < b.parameter ? -1 : a.parameter > b.parameter ? 1 : 0));
}

// ---- the adapter -----------------------------------------------------------------------

export interface MockOptions {
  /** Timestamps; default the real clock. */
  now?: () => Date | string | number;
  /** Source ids; default `mock-0001`, `mock-0002`, ... */
  newId?: () => string;
  /** Delay of every response, for demonstrations. Default 0. */
  latencyMs?: number;
}

interface Row {
  rec: InputRecord;
  text: string;
  seq: number;
  /**
   * Extracted the FIRST time the input was agreed and frozen from then on (engine.py
   * `brain_contributions` + `brain_fit_context`): a later revoke / re-judgement
   * removes them from the model, a restore puts the very same ones back.
   */
  contributions: MockContribution[];
  /** True once `contributions` are frozen. An edit (mock only) clears it. */
  fitted: boolean;
}

/** A decision result whose partition is always known (assignable to both SubmitResult and ReviewResult). */
type Decision = ReviewResult & { partition: Partition };

const STATUSES: readonly InputStatus[] = ['pending', 'agreed', 'disagreed', 'revoked'];

/** The dual-judgement fields every decision result carries. */
function metaOf(rec: InputRecord): Required<DecisionMetadata> {
  return { immediate: rec.immediate, confirm: rec.confirm, exclamation: rec.exclamation, confirmed_by: rec.confirmed_by, reason: rec.reason };
}

const MOCK_INTERPRETATION: Interpretation = { correction_revision: 0, corrections: [], learned_rules: [] };

function encodeCursor(payload: { r: number; p: string | null; s: string | null; a: number }): string {
  return 'mock1.' + btoa(JSON.stringify(payload)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

function decodeCursor(token: unknown): { r: number; p: string | null; s: string | null; a: number } {
  const bad = (): never => fail('INVALID_ARGUMENT', '无效的分页游标');
  if (typeof token !== 'string' || !/^mock1\.[A-Za-z0-9_-]+$/.test(token)) return bad();
  let payload: unknown;
  try {
    const b64 = token.slice(6).replace(/-/g, '+').replace(/_/g, '/');
    payload = JSON.parse(atob(b64 + '='.repeat((4 - (b64.length % 4)) % 4)));
  } catch {
    return bad();
  }
  const c = payload as { r?: unknown; p?: unknown; s?: unknown; a?: unknown } | null;
  if (!c || typeof c !== 'object' || !Number.isInteger(c.r) || !Number.isInteger(c.a) || (c.p !== null && typeof c.p !== 'string') || (c.s !== null && typeof c.s !== 'string')) {
    return bad();
  }
  return c as { r: number; p: string | null; s: string | null; a: number };
}

interface Aggregate {
  net: number;
  support: number;
}

const score = (net: number, support: number): number => net / (support + PRIOR_STRENGTH);

function fail(code: ConstructorParameters<typeof BackendError>[0], message: string): never {
  throw new BackendError(code, message);
}

function cloneOf<T>(value: T): T {
  return structuredClone(value);
}

export class MockBrainAdapter implements BrainAdapter {
  readonly info: AdapterInfo = { kind: 'mock', label: MOCK_LABEL, trains: false };

  private readonly rows = new Map<string, Row>();
  private effectLog: ParameterEffect[] = [];
  private revision = 0;
  /** Like the back end's review-history watermark: moves when an input changes; stales `inputPage` cursors. */
  private inputRevision = 0;
  private seq = 0;
  private idCounter = 0;
  private readonly now: () => string;
  private readonly newId: () => string;
  private readonly latencyMs: number;

  constructor(options: MockOptions = {}) {
    const clock = options.now ?? (() => new Date());
    this.now = () => {
      const t = clock();
      return typeof t === 'string' ? t : new Date(t).toISOString();
    };
    this.newId = options.newId ?? (() => `mock-${String(++this.idCounter).padStart(4, '0')}`);
    this.latencyMs = options.latencyMs ?? 0;
  }

  // -- plumbing

  /** Runs `fn` after the optional demo latency; a thrown BackendError becomes a rejection. */
  private call<T>(fn: () => T): Promise<T> {
    const wait = this.latencyMs > 0 ? new Promise<void>((r) => setTimeout(r, this.latencyMs)) : Promise.resolve();
    return wait.then(() => cloneOf(fn()));
  }

  private row(sourceId: string): Row {
    const row = typeof sourceId === 'string' ? this.rows.get(sourceId) : undefined;
    if (!row) fail('NOT_FOUND', '找不到这份输入');
    return row;
  }

  /** Per partition and parameter, the evidence of the agreed inputs — the ONLY source of model state. */
  private aggregate(): Record<Partition, Record<string, Aggregate>> {
    const agg = {} as Record<Partition, Record<string, Aggregate>>;
    for (const p of PARTITIONS) agg[p] = {};
    for (const { rec, contributions } of this.rows.values()) {
      if (rec.status !== 'agreed') continue;
      for (const c of contributions) {
        const a = (agg[rec.partition][c.parameter] ??= { net: 0, support: 0 });
        a.net += c.sign;
        a.support += 1;
      }
    }
    return agg;
  }

  private stateFrom(agg: Record<Partition, Record<string, Aggregate>>): ModelState {
    const state = {} as ModelState;
    for (const p of PARTITIONS) {
      const ps = {} as PartitionState;
      for (const id of PARAMETER_IDS) {
        const a = agg[p][id];
        ps[id] = a ? { value: score(a.net, a.support), support: a.support, observed: a.support > 0 } : { value: 0, support: 0, observed: false };
      }
      state[p] = ps;
    }
    return state;
  }

  private effectsBetween(
    row: Row,
    contributions: readonly MockContribution[],
    before: ModelState,
    after: ModelState,
    action: 'approve' | 'revoke',
  ): ParameterEffect[] {
    const at = this.now();
    const out = contributions.map((c): ParameterEffect => {
      const b = before[row.rec.partition][c.parameter];
      const a = after[row.rec.partition][c.parameter];
      return {
        revision: ++this.revision,
        source_id: row.rec.source_id,
        partition: row.rec.partition,
        parameter: c.parameter,
        before: b.value,
        after: a.value,
        delta: a.value - b.value,
        support_before: b.support,
        support_after: a.support,
        evidence: c.evidence,
        span: c.span,
        rule_id: c.rule_id,
        action,
        created_at: at,
      };
    });
    this.effectLog.push(...out);
    return out;
  }

  private checkContent(text: unknown, kind: Kind, selfSpeaker: string | null | undefined): void {
    if (typeof text !== 'string' || isBlank(text) || codePointLength(text) > MAX_INPUT_CHARS) {
      fail('INVALID_ARGUMENT', `内容须为 1 到 ${MAX_INPUT_CHARS} 个字符的文字`);
    }
    if (hasLoneSurrogate(text)) fail('INVALID_ARGUMENT', '内容含有无法编码的孤立代理字符');
    // The real back end cannot store a text that starts with U+0000 (SQLite length()
    // stops at the NUL, so its CHECK length(trim(body)) > 0 fails) and answers with
    // an opaque STORAGE_ERROR. Mirror it so demo mode does not hide that failure.
    if (leadingNul(text)) fail('STORAGE_ERROR', 'local storage operation failed');
    if (kind === 'chat' && (typeof selfSpeaker !== 'string' || isBlank(selfSpeaker))) {
      fail('INVALID_ARGUMENT', '聊天记录必须指定发言者');
    }
  }

  private describe(row: Row, text: string): void {
    row.text = text;
    row.rec.excerpt = codePointSlice(text, [0, Math.min(EXCERPT_CHARS, codePointLength(text))]);
    row.rec.char_count = codePointLength(text);
  }

  /** The decision shape shared by every result (engine.py `_decision_result`). */
  private decision(rec: InputRecord, effects: ParameterEffect[] = []): Decision {
    return { source_id: rec.source_id, status: rec.status, partition: rec.partition, ...metaOf(rec), effects, translator_effects: [] };
  }

  /**
   * The formal approval (`engine._review`, agree): the first time extract and freeze
   * the contributions, afterwards restore the frozen ones. Shared by exclamation and `confirm(true)`.
   */
  private approve(row: Row, by: ConfirmedBy): Decision {
    const before = this.stateFrom(this.aggregate());
    const restored = row.fitted;
    if (!restored) {
      row.contributions = mockExtract(row.text, row.rec.kind, row.rec.self_speaker);
      row.fitted = true;
    }
    row.rec.status = 'agreed';
    row.rec.confirm = true;
    row.rec.confirmed_by = by;
    row.rec.reason = null;
    row.rec.reviewed_at = this.now();
    const after = this.stateFrom(this.aggregate());
    const effects = this.effectsBetween(row, row.contributions, before, after, 'approve');
    this.inputRevision++;
    return {
      ...this.decision(row.rec, effects),
      observed_terms: 0,
      interpretation: structuredClone(MOCK_INTERPRETATION),
      restored_fit: restored,
    };
  }

  /**
   * `engine._deactivate`: an agreed input leaves training, its frozen contributions
   * are removed (reversal effects, action `revoke`); an input that was not agreed just
   * changes its judgement and has no effects.
   */
  private deactivate(row: Row, status: 'disagreed' | 'revoked', reason: InputReason, by: ConfirmedBy | null): ReviewResult {
    const active = row.rec.status === 'agreed';
    const before = this.stateFrom(this.aggregate());
    row.rec.status = status;
    row.rec.confirm = false;
    row.rec.reason = reason;
    row.rec.confirmed_by = by;
    row.rec.reviewed_at = this.now();
    const after = this.stateFrom(this.aggregate());
    const effects = active ? this.effectsBetween(row, row.contributions, before, after, 'revoke') : [];
    this.inputRevision++;
    return this.decision(row.rec, effects);
  }

  // -- BrainAdapter

  capabilities(): Promise<ReadonlySet<AdapterMethod>> {
    return this.call(() => new Set<AdapterMethod>(ADAPTER_METHODS));
  }

  submit(req: SubmitRequest): Promise<SubmitResult> {
    return this.call((): SubmitResult => {
      if (!PARTITIONS.includes(req.partition)) fail('INVALID_ARGUMENT', '无效的状态分区');
      const kind = req.kind ?? 'diary';
      if (!KINDS.includes(kind)) fail('INVALID_ARGUMENT', '无效的类型');
      if (typeof req.immediate !== 'boolean') fail('INVALID_ARGUMENT', 'immediate 必须是布尔值');
      const exclamation = req.exclamation ?? false;
      if (typeof exclamation !== 'boolean') fail('INVALID_ARGUMENT', 'exclamation 必须是布尔值');
      // core.api: a given source_ref must contain text (null / absent is fine).
      if (req.source_ref != null && (typeof req.source_ref !== 'string' || isBlank(req.source_ref))) {
        fail('INVALID_ARGUMENT', 'source_ref must contain text');
      }
      this.checkContent(req.text, kind, req.self_speaker);
      // engine.submit_result: an explicit exclamation overrides immediate=false.
      const immediate = req.immediate || exclamation;

      const at = this.now();
      const id = this.newId();
      const rec: InputRecord = {
        source_id: id,
        partition: req.partition,
        kind,
        self_speaker: kind === 'chat' ? (req.self_speaker as string) : null,
        status: immediate ? 'pending' : 'disagreed',
        source_ref: req.source_ref ?? null,
        created_at: at,
        reviewed_at: immediate ? null : at,
        immediate,
        confirm: null,
        exclamation,
        confirmed_by: null,
        reason: immediate ? null : 'immediate_false',
        excerpt: '',
        char_count: 0,
        edited_at: null,
      };
      const row: Row = { rec, text: '', seq: ++this.seq, contributions: [], fitted: false };
      this.describe(row, req.text);
      this.rows.set(id, row);
      this.inputRevision++;

      if (exclamation) return this.approve(row, 'exclamation');
      return this.decision(rec);
    });
  }

  preview(sourceId: string): Promise<PreviewResult> {
    return this.call((): PreviewResult => {
      const row = this.row(sourceId);
      const { rec, text } = row;
      // engine.preview: every input that is not in training, immediate_false included.
      if (rec.status === 'agreed') fail('INVALID_ARGUMENT', '已在训练中的输入无需预览');
      const agg = this.aggregate()[rec.partition];
      // A previously fitted input projects the restoration of its frozen evidence.
      const contributions = row.fitted ? row.contributions : mockExtract(text, rec.kind, rec.self_speaker);
      const effects: ParameterEffect[] = contributions.map((c) => {
        const cur = agg[c.parameter] ?? { net: 0, support: 0 };
        const before = cur.support > 0 ? score(cur.net, cur.support) : 0;
        const after = score(cur.net + c.sign, cur.support + 1);
        // Hypothetical: no revision, no created_at.
        return {
          source_id: rec.source_id,
          partition: rec.partition,
          parameter: c.parameter,
          before,
          after,
          delta: after - before,
          support_before: cur.support,
          support_after: cur.support + 1,
          evidence: c.evidence,
          span: c.span,
          rule_id: c.rule_id,
          action: 'preview',
        };
      });
      return {
        source_id: rec.source_id,
        ...metaOf(rec),
        status: rec.status,
        partition: rec.partition,
        kind: rec.kind,
        hypothetical: true,
        effects,
        translator_effects: [],
        observed_terms: 0,
        translation: mockTranslate(text, rec.kind, rec.self_speaker),
        interpretation: structuredClone(MOCK_INTERPRETATION),
      };
    });
  }

  confirm(sourceId: string, confirm: boolean): Promise<ReviewResult> {
    return this.call((): ReviewResult => {
      if (typeof confirm !== 'boolean') fail('INVALID_ARGUMENT', 'confirm 必须是布尔值');
      const row = this.row(sourceId);
      const { rec } = row;
      if (!rec.immediate) fail('INVALID_ARGUMENT', '当下判断为“不是真的”的输入不能认可或不同意，请先修改并重新声明');
      // The same decision again: no fit, no effects, no revision, no audit event.
      if ((confirm && rec.status === 'agreed') || (!confirm && rec.confirm === false)) return this.decision(rec);
      if (!confirm) return this.deactivate(row, 'disagreed', 'confirm_false', 'manual');
      return this.approve(row, 'manual');
    });
  }

  revoke(sourceId: string): Promise<ReviewResult> {
    return this.call((): ReviewResult => {
      const row = this.row(sourceId);
      if (row.rec.status !== 'agreed') fail('INVALID_ARGUMENT', '只有已认可的输入才能撤销');
      return this.deactivate(row, 'revoked', 'user_revoked', row.rec.confirmed_by);
    });
  }

  /** Filtered rows, newest first; validates like `BrainCore._input_filters`. */
  private filtered(query: InputListQuery): Row[] {
    const limit = query.limit ?? 20;
    if (!Number.isInteger(limit) || limit < 1 || limit > 100) fail('INVALID_ARGUMENT', 'limit 须为 1 到 100 的整数');
    if (query.partition != null && !PARTITIONS.includes(query.partition)) fail('INVALID_ARGUMENT', '无效的状态分区');
    if (query.status != null && !STATUSES.includes(query.status)) fail('INVALID_ARGUMENT', '无效的输入状态');
    return [...this.rows.values()]
      .filter((r) => (query.partition == null || r.rec.partition === query.partition) && (query.status == null || r.rec.status === query.status))
      .sort((a, b) => b.seq - a.seq);
  }

  inputList(query: InputListQuery = {}): Promise<InputRecord[]> {
    return this.call(() =>
      this.filtered(query)
        .slice(0, query.limit ?? 20)
        .map((r) => r.rec),
    );
  }

  inputPage(query: InputPageQuery = {}): Promise<InputPage> {
    return this.call((): InputPage => {
      let rows = this.filtered(query);
      const limit = query.limit ?? 20;
      const total = rows.length;
      if (query.cursor !== undefined && query.cursor !== null) {
        const c = decodeCursor(query.cursor);
        // Same order of checks as core/pagination.py `decode`: shape, filters, then revision.
        if (c.p !== (query.partition ?? null) || c.s !== (query.status ?? null)) {
          fail('INVALID_ARGUMENT', '分页游标与当前筛选不符，请从第一页重新开始');
        }
        if (c.r !== this.inputRevision) fail('STALE_CURSOR', '输入已变化，请丢弃已取的页并从第一页重新开始');
        rows = rows.filter((r) => r.seq < c.a);
      }
      const items = rows.slice(0, limit);
      const next =
        rows.length > limit
          ? encodeCursor({ r: this.inputRevision, p: query.partition ?? null, s: query.status ?? null, a: items[items.length - 1].seq })
          : null;
      return { items: items.map((r) => r.rec), total, next_cursor: next, revision: this.inputRevision };
    });
  }

  inputGet(sourceId: string): Promise<InputDetail> {
    return this.call(() => {
      const row = this.row(sourceId);
      return { ...row.rec, text: row.text };
    });
  }

  inputEdit(sourceId: string, edit: InputEditRequest): Promise<InputRecord> {
    return this.call(() => {
      const row = this.row(sourceId);
      const { rec } = row;
      if (rec.status === 'agreed') fail('INVALID_ARGUMENT', '已认可的输入不能编辑，请先撤销');
      if (typeof edit.immediate !== 'boolean') fail('INVALID_ARGUMENT', 'immediate 必须是布尔值');
      const kind = edit.kind ?? rec.kind;
      if (!KINDS.includes(kind)) fail('INVALID_ARGUMENT', '无效的类型');
      const speaker = kind === 'chat' ? (edit.self_speaker ?? rec.self_speaker) : null;
      this.checkContent(edit.text, kind, speaker);

      this.describe(row, edit.text);
      rec.kind = kind;
      rec.self_speaker = speaker;
      const at = this.now();
      rec.edited_at = at;
      rec.immediate = edit.immediate;
      rec.confirm = null;
      rec.exclamation = false;
      rec.confirmed_by = null;
      rec.status = edit.immediate ? 'pending' : 'disagreed';
      rec.reason = edit.immediate ? null : 'immediate_false';
      rec.reviewed_at = edit.immediate ? null : at;
      // A new text starts over: nothing of the old fit is frozen any more.
      row.contributions = [];
      row.fitted = false;
      this.inputRevision++;
      return rec;
    });
  }

  inputDelete(sourceId: string): Promise<void> {
    return this.call(() => {
      this.row(sourceId);
      // A hard delete of any input, whatever its status (the user's decision): the text, both
      // judgements and its whole effect history go. An agreed input stops training with it, the
      // model state is always recomputed from the inputs that remain. Other inputs' effects keep
      // the numbers they had when they were written. (The real back end decides F6 itself.)
      this.rows.delete(sourceId);
      this.inputRevision++;
      this.effectLog = this.effectLog.filter((e) => e.source_id !== sourceId);
    });
  }

  state(): Promise<ModelState> {
    return this.call(() => this.stateFrom(this.aggregate()));
  }

  effects(sourceId?: string): Promise<ParameterEffect[]> {
    return this.call(() => {
      if (sourceId !== undefined) this.row(sourceId);
      return sourceId === undefined ? this.effectLog : this.effectLog.filter((e) => e.source_id === sourceId);
    });
  }

  rank(options: { id: string; impacts: Partial<Record<ParameterId, number>> }[]): Promise<RankResult> {
    return this.call((): RankResult => {
      if (!Array.isArray(options) || options.length < 2) fail('INVALID_ARGUMENT', '至少需要两个选项');
      const ids = new Set<string>();
      for (const o of options) {
        if (!o || typeof o.id !== 'string' || o.id === '') fail('INVALID_ARGUMENT', '每个选项都需要非空 id');
        if (!o.impacts || typeof o.impacts !== 'object') fail('INVALID_ARGUMENT', '每个选项都需要 impacts');
        for (const [parameter, value] of Object.entries(o.impacts)) {
          if (!(PARAMETER_IDS as readonly string[]).includes(parameter) || !parameter.startsWith('value.')) {
            fail('INVALID_ARGUMENT', `未知或非价值参数：${parameter}`);
          }
          if (typeof value !== 'number' || !Number.isFinite(value) || value < -1 || value > 1) {
            fail('INVALID_ARGUMENT', 'impacts 必须是 -1 到 1 之间的有限数');
          }
        }
        ids.add(o.id);
      }
      if (ids.size !== options.length) fail('INVALID_ARGUMENT', '选项 id 不能重复');

      const rational = this.stateFrom(this.aggregate()).rational;
      const usable: Record<string, number> = {};
      for (const id of PARAMETER_IDS) {
        if (id.startsWith('value.') && rational[id].support >= 2) usable[id] = rational[id].value;
      }
      const touches = options.some((o) => Object.entries(o.impacts).some(([k, v]) => k in usable && v !== 0));
      if (!touches) return { status: 'abstain', reason: 'insufficient_confirmed_value_evidence', ranked: [] };
      const ranked = options
        .map((o) => ({
          id: o.id,
          alignment_score: Object.entries(o.impacts).reduce((sum, [k, v]) => sum + (usable[k] ?? 0) * (v as number), 0),
        }))
        .sort((a, b) => b.alignment_score - a.alignment_score || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
      if (ranked.every((r) => r.alignment_score === ranked[0].alignment_score)) {
        return { status: 'abstain', reason: 'options_indistinguishable_with_current_evidence', ranked: [] };
      }
      return {
        status: 'provisional',
        basis: 'confirmed_value_alignment_only',
        not_a_probability: true,
        used_parameters: Object.keys(usable).sort(),
        ranked,
      };
    });
  }
}
