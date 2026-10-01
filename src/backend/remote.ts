/**
 * RemoteBrainAdapter — the BrainAdapter over the real back end's JSON envelope
 * (`back-end-core/docs/api.md`, schema_version 1). It is real code with NO
 * transport of its own: `Transport.request` is whatever carries one request
 * envelope to the local back-end process and returns its response envelope. The
 * Tauri host command `brain_call` exists (front-back-communicate.md F11);
 * `tauriTransport.ts` is the React side and `backendStore.connectDesktopBackend()`
 * wires them together. Tests use a fake transport or a spawned Python process.
 *
 * What it does on top of the wire format:
 *  - every request gets a fresh id (1..128 chars); the response id must match;
 *  - error codes are mapped (an unknown code -> INTERNAL_ERROR; STALE_CURSOR is known);
 *  - api.md rejects unknown fields, so `immediate` / `exclamation` are only sent
 *    when `twoJudgements` is true (`health.features.two_judgements`, read by
 *    `RemoteBrainAdapter.probe`). With false, a submit that an older back end
 *    cannot represent (`immediate: false`, `exclamation: true`) fails with
 *    UNSUPPORTED instead of being silently downgraded into a trained input.
 *    With true both are sent exactly as given: the back end itself sets
 *    immediate AND confirm true for an `exclamation`, also when immediate is
 *    false, and answers with the formal effects;
 *  - `probe(transport)` calls `health` once and returns the options to connect
 *    with and the capability set derived from `health.methods`;
 *  - `inputList` uses `input_list`, `inputPage` uses `input_page`. Rows are
 *    normalised; defaults are filled in for fields an older back end lacks, and
 *    a row WITHOUT `excerpt` is hydrated through `input_get`, a few at a time,
 *    with a cache. A current back end always sends `excerpt`, so that never runs;
 *  - `inputEdit` / `inputDelete` have no back-end method (F6, not implemented):
 *    UNSUPPORTED. With `proposedMethods: true` they call `input_edit` /
 *    `input_delete` as proposed in F6, for the day the back end agrees;
 *    METHOD_NOT_FOUND then maps to UNSUPPORTED too. `probe` never turns it on.
 *
 * Pure module: no React, DOM or three.
 */

import { codePointLength, codePointSlice } from './spans';
import { ADAPTER_METHODS, BACKEND_ERROR_CODES, BackendError, KINDS, PARTITIONS } from './types';
import type {
  AdapterInfo,
  AdapterMethod,
  BackendErrorCode,
  BrainAdapter,
  InputDetail,
  InputEditRequest,
  InputListQuery,
  InputPage,
  InputPageQuery,
  InputRecord,
  InputStatus,
  ModelState,
  ParameterEffect,
  ParameterId,
  PreviewResult,
  RankResult,
  ReviewResult,
  SubmitRequest,
  SubmitResult,
} from './types';

export interface RequestEnvelope {
  schema_version: 1;
  id: string;
  method: string;
  params: Record<string, unknown>;
}

export type ResponseEnvelope =
  | { schema_version: number; id: string | null; ok: true; result: unknown }
  | { schema_version: number; id: string | null; ok: false; error: { code: string; message: string } };

/** Carries one envelope to the back end and its answer back. Owned by the host glue, not by the UI. */
export interface Transport {
  request(envelope: RequestEnvelope): Promise<ResponseEnvelope>;
}

export interface RemoteOptions {
  /**
   * Send `immediate` / `exclamation` with `submit`; true only when the back end
   * reports `health.features.two_judgements` (use `RemoteBrainAdapter.probe`). Default false.
   */
  twoJudgements?: boolean;
  /** Call the PROPOSED `input_edit` / `input_delete`. Default false: both are UNSUPPORTED. */
  proposedMethods?: boolean;
  /** Request ids; default unique per adapter and per request. */
  newId?: () => string;
  /** Parallel `input_get` calls while hydrating excerpts. Default 4. */
  hydrateConcurrency?: number;
}

/** What `health` says, reduced to what the adapter needs. */
export interface HealthReport {
  /** `health.methods`, verbatim. */
  methods: readonly string[];
  /** `health.features`, boolean entries only (`two_judgements`, `input_pagination`, `source_edit` ...). */
  features: Readonly<Record<string, boolean>>;
}

/** The outcome of `RemoteBrainAdapter.probe`. */
export interface ProbeResult extends HealthReport {
  /** Pass to `new RemoteBrainAdapter(transport, options)` / `backendStore.connectRemote`. */
  options: RemoteOptions;
  /** What the UI may enable: `health.methods` mapped to adapter methods. */
  capabilities: ReadonlySet<AdapterMethod>;
}

/** api.md method behind each adapter method. */
const API_METHOD: Record<AdapterMethod, string> = {
  submit: 'submit',
  preview: 'preview',
  confirm: 'review',
  revoke: 'revoke',
  inputList: 'input_list',
  inputPage: 'input_page',
  inputGet: 'input_get',
  inputEdit: 'input_edit',
  inputDelete: 'input_delete',
  state: 'state',
  effects: 'effects',
  rank: 'rank',
};

/** Methods that exist only as a proposal (front-back-communicate.md F6). */
const PROPOSED_API_METHODS = new Set(['input_edit', 'input_delete']);

const WIRE_ERROR_CODES = new Set<string>(
  BACKEND_ERROR_CODES.filter((c) => c !== 'UNAVAILABLE' && c !== 'UNSUPPORTED'),
);
function capabilitiesFor(methods: readonly string[], proposedMethods: boolean): ReadonlySet<AdapterMethod> {
  const offered = new Set<unknown>(methods);
  return new Set<AdapterMethod>(
    ADAPTER_METHODS.filter((m) => offered.has(API_METHOD[m]) && (!PROPOSED_API_METHODS.has(API_METHOD[m]) || proposedMethods)),
  );
}

const STATUSES: readonly InputStatus[] = ['pending', 'agreed', 'disagreed', 'revoked'];
const EXCERPT_CHARS = 80;

const UNSUPPORTED_TEXT = '后端尚不支持';

function bad(message: string): never {
  throw new BackendError('INTERNAL_ERROR', message);
}

function obj(value: unknown, what: string): Record<string, unknown> {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) bad(`后端返回的${what}格式不正确`);
  return value as Record<string, unknown>;
}

export class RemoteBrainAdapter implements BrainAdapter {
  readonly info: AdapterInfo = { kind: 'remote', label: '本机后端', trains: true };

  private readonly transport: Transport;
  private readonly twoJudgements: boolean;
  private readonly proposedMethods: boolean;
  private readonly newId: () => string;
  private readonly concurrency: number;
  private counter = 0;
  private readonly prefix = Math.random().toString(36).slice(2, 8);
  /** Excerpts fetched with `input_get` (workaround for F5). */
  private readonly excerpts = new Map<string, { excerpt: string; char_count: number }>();
  private health: Promise<HealthReport> | null = null;

  constructor(transport: Transport, options: RemoteOptions = {}) {
    this.transport = transport;
    this.twoJudgements = options.twoJudgements ?? false;
    this.proposedMethods = options.proposedMethods ?? false;
    this.newId = options.newId ?? (() => `alpha-${this.prefix}-${++this.counter}`);
    this.concurrency = Math.max(1, Math.floor(options.hydrateConcurrency ?? 4));
  }

  // -- wire

  private async call(method: string, params: Record<string, unknown> = {}): Promise<unknown> {
    const id = this.newId();
    if (typeof id !== 'string' || id.length < 1 || id.length > 128) bad('请求编号必须是 1 到 128 个字符');
    let response: ResponseEnvelope;
    try {
      response = await this.transport.request({ schema_version: 1, id, method, params });
    } catch (e) {
      if (e instanceof BackendError) throw e;
      throw new BackendError('UNAVAILABLE', '后端连接中断');
    }
    if (typeof response !== 'object' || response === null) bad('后端返回的响应格式不正确');
    if (response.schema_version !== 1) throw new BackendError('UNSUPPORTED_VERSION', '后端协议版本不受支持');
    if (response.id !== id) bad('后端响应的编号与请求不符');
    if (response.ok === true) return response.result;
    if (response.ok !== false || typeof response.error !== 'object' || response.error === null) {
      bad('后端返回的响应格式不正确');
    }
    const { code, message } = response.error;
    if (code === 'METHOD_NOT_FOUND' && PROPOSED_API_METHODS.has(method)) {
      throw new BackendError('UNSUPPORTED', UNSUPPORTED_TEXT);
    }
    const known = WIRE_ERROR_CODES.has(code) ? (code as BackendErrorCode) : 'INTERNAL_ERROR';
    throw new BackendError(known, typeof message === 'string' && message ? message : '后端操作失败');
  }

  private unsupported(what: string): never {
    throw new BackendError('UNSUPPORTED', `${UNSUPPORTED_TEXT}：${what}`);
  }

  // -- rows

  /** Fills the dual-judgement fields an older back end does not send (a current one always does). `text` is known only from `input_get`. */
  private normalize(raw: unknown, text?: string): InputRecord {
    const r = obj(raw, '输入记录');
    const status = r.status as InputStatus;
    if (typeof r.source_id !== 'string' || !STATUSES.includes(status)) bad('后端返回的输入记录缺少必要字段');
    if (!PARTITIONS.includes(r.partition as never) || !KINDS.includes(r.kind as never)) bad('后端返回的输入记录缺少必要字段');
    const known = this.excerpts.get(r.source_id);
    let excerpt = typeof r.excerpt === 'string' ? r.excerpt : known?.excerpt ?? '';
    let charCount = typeof r.char_count === 'number' ? r.char_count : known?.char_count ?? 0;
    if (text !== undefined) {
      charCount = codePointLength(text);
      excerpt = codePointSlice(text, [0, Math.min(EXCERPT_CHARS, charCount)]);
      this.excerpts.set(r.source_id, { excerpt, char_count: charCount });
    }
    return {
      source_id: r.source_id,
      partition: r.partition as InputRecord['partition'],
      kind: r.kind as InputRecord['kind'],
      self_speaker: typeof r.self_speaker === 'string' ? r.self_speaker : null,
      status,
      source_ref: typeof r.source_ref === 'string' ? r.source_ref : null,
      created_at: typeof r.created_at === 'string' ? r.created_at : '',
      reviewed_at: typeof r.reviewed_at === 'string' ? r.reviewed_at : null,
      immediate: typeof r.immediate === 'boolean' ? r.immediate : true,
      // Only for a back end that does not send `confirm` (F2): agreed -> true, disagreed -> false,
      // pending -> null; an old revoked input was once agreed.
      confirm: typeof r.confirm === 'boolean' ? r.confirm : r.confirm === null ? null : status === 'disagreed' ? false : status === 'pending' ? null : true,
      exclamation: typeof r.exclamation === 'boolean' ? r.exclamation : false,
      confirmed_by: r.confirmed_by === 'exclamation' || r.confirmed_by === 'manual' || r.confirmed_by === 'legacy' ? r.confirmed_by : null,
      reason:
        r.reason === 'immediate_false' || r.reason === 'confirm_false' || r.reason === 'user_revoked'
          ? r.reason
          : status === 'revoked'
            ? 'user_revoked'
            : null,
      excerpt,
      char_count: charCount,
      edited_at: typeof r.edited_at === 'string' ? r.edited_at : null,
    };
  }

  // -- BrainAdapter

  /** `health`, asked once; a failed probe is not remembered. */
  private readHealth(): Promise<HealthReport> {
    if (!this.health) {
      const pending = this.call('health').then((res): HealthReport => {
        const h = obj(res, '健康检查');
        if (!Array.isArray(h.methods) || !h.methods.every((m) => typeof m === 'string')) bad('后端返回的健康检查缺少 methods');
        const features: Record<string, boolean> = {};
        if (typeof h.features === 'object' && h.features !== null && !Array.isArray(h.features)) {
          for (const [k, v] of Object.entries(h.features)) if (typeof v === 'boolean') features[k] = v;
        }
        return { methods: h.methods as string[], features };
      });
      this.health = pending;
      pending.catch(() => {
        if (this.health === pending) this.health = null;
      });
    }
    return this.health;
  }

  /**
   * Ask the back end what it can do, before connecting. `base` carries the
   * caller's own options (ids, concurrency); `twoJudgements` is taken from
   * `health.features.two_judgements`, `proposedMethods` is never switched on
   * (F6 edit/delete do not exist in the back end) unless `base` says so.
   * Rejects with a BackendError when the back end cannot be reached.
   */
  static async probe(transport: Transport, base: RemoteOptions = {}): Promise<ProbeResult> {
    const report = await new RemoteBrainAdapter(transport, base).readHealth();
    const options: RemoteOptions = {
      ...base,
      twoJudgements: report.features.two_judgements === true,
      proposedMethods: base.proposedMethods ?? false,
    };
    return { ...report, options, capabilities: capabilitiesFor(report.methods, options.proposedMethods === true) };
  }

  async capabilities(): Promise<ReadonlySet<AdapterMethod>> {
    return capabilitiesFor((await this.readHealth()).methods, this.proposedMethods);
  }

  async submit(req: SubmitRequest): Promise<SubmitResult> {
    if (typeof req.immediate !== 'boolean') throw new BackendError('INVALID_ARGUMENT', 'immediate 必须是布尔值');
    const exclamation = req.exclamation ?? false;
    if (!this.twoJudgements && (!req.immediate || exclamation)) {
      // A back end without `two_judgements` rejects unknown fields and cannot store either; sending a plain
      // submit would make something the user said is not true eligible for training.
      this.unsupported('当前后端无法记录“当下不是真的”或“断言为真”');
    }
    const params: Record<string, unknown> = { text: req.text, partition: req.partition, kind: req.kind ?? 'diary' };
    if (req.self_speaker !== undefined) params.self_speaker = req.self_speaker;
    if (req.source_ref !== undefined) params.source_ref = req.source_ref;
    if (this.twoJudgements) {
      // Exactly as given: the back end lets an exclamation override immediate=false itself.
      params.immediate = req.immediate;
      params.exclamation = exclamation;
    }
    const r = obj(await this.call('submit', params), '提交结果');
    if (typeof r.source_id !== 'string') bad('后端返回的提交结果缺少 source_id');
    return r as unknown as SubmitResult;
  }

  async preview(sourceId: string): Promise<PreviewResult> {
    const r = obj(await this.call('preview', { source_id: sourceId }), '预览结果');
    if (!Array.isArray(r.effects)) bad('后端返回的预览缺少 effects');
    return r as unknown as PreviewResult;
  }

  async confirm(sourceId: string, confirm: boolean): Promise<ReviewResult> {
    const r = obj(await this.call('review', { source_id: sourceId, agree: confirm }), '审核结果');
    if (!Array.isArray(r.effects)) bad('后端返回的审核结果缺少 effects');
    return r as unknown as ReviewResult;
  }

  async revoke(sourceId: string): Promise<ReviewResult> {
    const r = obj(await this.call('revoke', { source_id: sourceId }), '撤销结果');
    if (!Array.isArray(r.effects)) bad('后端返回的撤销结果缺少 effects');
    return r as unknown as ReviewResult;
  }

  async inputList(query: InputListQuery = {}): Promise<InputRecord[]> {
    const params: Record<string, unknown> = {};
    if (query.partition !== undefined) params.partition = query.partition;
    if (query.status !== undefined) params.status = query.status;
    if (query.limit !== undefined) params.limit = query.limit;
    const raw = await this.call('input_list', params);
    if (!Array.isArray(raw)) bad('后端返回的输入列表格式不正确');
    await this.hydrate(raw);
    return raw.map((row) => this.normalize(row));
  }

  async inputPage(query: InputPageQuery = {}): Promise<InputPage> {
    const params: Record<string, unknown> = {};
    if (query.partition != null) params.partition = query.partition;
    if (query.status != null) params.status = query.status;
    if (query.limit !== undefined) params.limit = query.limit;
    // The cursor is opaque: it goes back exactly as received, never built or decoded here.
    if (query.cursor != null) params.cursor = query.cursor;
    const r = obj(await this.call('input_page', params), '输入分页');
    if (!Array.isArray(r.items) || typeof r.total !== 'number' || typeof r.revision !== 'number') {
      bad('后端返回的输入分页格式不正确');
    }
    if (r.next_cursor !== null && typeof r.next_cursor !== 'string') bad('后端返回的输入分页格式不正确');
    await this.hydrate(r.items);
    return {
      items: r.items.map((row) => this.normalize(row)),
      total: r.total,
      next_cursor: r.next_cursor as string | null,
      revision: r.revision,
    };
  }

  /**
   * Only for a back end whose rows lack `excerpt` (before F5): such rows get it from
   * `input_get`, `concurrency` at a time, once per source id (later lists hit the cache).
   * A row that has `excerpt` never costs a request.
   */
  private async hydrate(raw: unknown[]): Promise<void> {
    const missing: string[] = [];
    for (const row of raw) {
      const r = row as { source_id?: unknown; excerpt?: unknown } | null;
      if (r && typeof r.source_id === 'string' && typeof r.excerpt !== 'string' && !this.excerpts.has(r.source_id)) {
        missing.push(r.source_id);
      }
    }
    let next = 0;
    const worker = async (): Promise<void> => {
      while (next < missing.length) {
        const id = missing[next++];
        try {
          const detail = obj(await this.call('input_get', { source_id: id }), '输入');
          if (typeof detail.text === 'string') this.normalize(detail, detail.text);
        } catch {
          // A row that cannot be hydrated keeps an empty excerpt; the list itself still works.
        }
      }
    };
    await Promise.all(Array.from({ length: Math.min(this.concurrency, missing.length) }, worker));
  }

  async inputGet(sourceId: string): Promise<InputDetail> {
    const r = obj(await this.call('input_get', { source_id: sourceId }), '输入');
    if (typeof r.text !== 'string') bad('后端返回的输入缺少 text');
    return { ...this.normalize(r, r.text), text: r.text };
  }

  async inputEdit(sourceId: string, edit: InputEditRequest): Promise<InputRecord> {
    if (!this.proposedMethods) this.unsupported('编辑输入');
    const params: Record<string, unknown> = { source_id: sourceId, text: edit.text, immediate: edit.immediate };
    if (edit.kind !== undefined) params.kind = edit.kind;
    if (edit.self_speaker !== undefined) params.self_speaker = edit.self_speaker;
    return this.normalize(await this.call('input_edit', params), edit.text);
  }

  async inputDelete(sourceId: string): Promise<void> {
    if (!this.proposedMethods) this.unsupported('删除输入');
    await this.call('input_delete', { source_id: sourceId });
    this.excerpts.delete(sourceId);
  }

  async state(): Promise<ModelState> {
    return obj(await this.call('state'), '模型状态') as unknown as ModelState;
  }

  async effects(sourceId?: string): Promise<ParameterEffect[]> {
    const raw = await this.call('effects', sourceId === undefined ? {} : { source_id: sourceId });
    if (!Array.isArray(raw)) bad('后端返回的 effects 格式不正确');
    return raw as ParameterEffect[];
  }

  async rank(options: { id: string; impacts: Partial<Record<ParameterId, number>> }[]): Promise<RankResult> {
    return obj(await this.call('rank', { options }), '排序结果') as unknown as RankResult;
  }
}
