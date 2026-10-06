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
 *  - `inputEdit` / `inputDelete` (F6) call `input_edit` / `input_delete` only
 *    with `proposedMethods: true`, otherwise UNSUPPORTED. `probe` turns it on
 *    exactly when `health` lists both methods AND reports
 *    `features.source_edit` and `source_delete` true (an older back end keeps
 *    them off); METHOD_NOT_FOUND maps to UNSUPPORTED too;
 *  - `health.model_epoch` (model reset) is kept: `modelEpoch()`. Rows keep the
 *    optional `model_active` / `model_epoch`; nothing is invented when absent.
 *
 * Pure module: no React, DOM or three.
 */

import { codePointLength, codePointSlice } from './spans';
import { ADAPTER_METHODS, BACKEND_ERROR_CODES, BackendError, KINDS, PARTITIONS } from './types';
import type {
  AccessStatus,
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
import { t } from '../i18n/lang';

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
  /** Call `input_edit` / `input_delete` (F6). Default false: both are UNSUPPORTED; `probe` sets it from `health`. */
  proposedMethods?: boolean;
  /** Request ids; default unique per adapter and per request. */
  newId?: () => string;
  /** Parallel `input_get` calls while hydrating excerpts. Default 4. */
  hydrateConcurrency?: number;
  /**
   * Called when a private method answers `LOCKED` (F13): the host drops every private cache
   * and shows the unlock prompt. Not called for `unlock` itself (a wrong password is also `LOCKED`).
   */
  onLocked?: () => void;
}

/** What `health` says, reduced to what the adapter needs. */
export interface HealthReport {
  /** `health.methods`, verbatim. */
  methods: readonly string[];
  /** `health.features`, boolean entries only (`two_judgements`, `input_pagination`, `source_edit` ...). */
  features: Readonly<Record<string, boolean>>;
  /** `health.model_epoch`, null when the back end does not report one (a locked back end omits it). */
  modelEpoch: number | null;
  /** `health.access`, null when absent (an older back end has no gate). */
  access: AccessStatus | null;
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
  modelReset: 'model_reset',
  state: 'state',
  effects: 'effects',
  rank: 'rank',
};

/** F6 methods: switched on by `proposedMethods` (set by `probe` from `health`). */
const PROPOSED_API_METHODS = new Set(['input_edit', 'input_delete']);

function offersSourceEditing(h: HealthReport): boolean {
  return (
    h.methods.includes('input_edit') &&
    h.methods.includes('input_delete') &&
    h.features.source_edit === true &&
    h.features.source_delete === true
  );
}

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



function bad(message: string): never {
  throw new BackendError('INTERNAL_ERROR', message);
}

function obj(value: unknown, what: string): Record<string, unknown> {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) bad(t('be.badShape', { what }));
  return value as Record<string, unknown>;
}

export class RemoteBrainAdapter implements BrainAdapter {
  readonly info: AdapterInfo = { kind: 'remote', label: t('be.local'), trains: true };

  private readonly transport: Transport;
  private readonly twoJudgements: boolean;
  private readonly proposedMethods: boolean;
  private readonly newId: () => string;
  private readonly concurrency: number;
  private readonly onLocked: (() => void) | undefined;
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
    this.onLocked = options.onLocked;
  }

  // -- wire

  private async call(method: string, params: Record<string, unknown> = {}): Promise<unknown> {
    const id = this.newId();
    if (typeof id !== 'string' || id.length < 1 || id.length > 128) bad(t('be.reqId'));
    let response: ResponseEnvelope;
    try {
      response = await this.transport.request({ schema_version: 1, id, method, params });
    } catch (e) {
      if (e instanceof BackendError) throw e;
      throw new BackendError('UNAVAILABLE', t('be.dropped'));
    }
    if (typeof response !== 'object' || response === null) bad(t('be.badResponse'));
    if (response.schema_version !== 1) throw new BackendError('UNSUPPORTED_VERSION', t('be.badVersion'));
    if (response.id !== id) bad(t('be.idMismatch'));
    if (response.ok === true) return response.result;
    if (response.ok !== false || typeof response.error !== 'object' || response.error === null) {
      bad(t('be.badResponse'));
    }
    const { code, message } = response.error;
    if (code === 'LOCKED' && method !== 'unlock') {
      // Private text (excerpts) and the epoch memo of the previous session must not survive the lock.
      this.forgetPrivate();
      this.onLocked?.();
    }
    if (code === 'METHOD_NOT_FOUND' && PROPOSED_API_METHODS.has(method)) {
      throw new BackendError('UNSUPPORTED', t('be.unsupported'));
    }
    const known = WIRE_ERROR_CODES.has(code) ? (code as BackendErrorCode) : 'INTERNAL_ERROR';
    throw new BackendError(known, typeof message === 'string' && message ? message : t('be.opFailed'));
  }

  /** Drop everything this adapter cached from private reads, and the memoised `health` (its epoch). */
  private forgetPrivate(): void {
    this.excerpts.clear();
    this.health = null;
  }

  private unsupported(what: string): never {
    throw new BackendError('UNSUPPORTED', `${t('be.unsupported')}: ${what}`);
  }

  // -- rows

  /** Fills the dual-judgement fields an older back end does not send (a current one always does). `text` is known only from `input_get`. */
  private normalize(raw: unknown, text?: string): InputRecord {
    const r = obj(raw, t('be.what.record'));
    const status = r.status as InputStatus;
    if (typeof r.source_id !== 'string' || !STATUSES.includes(status)) bad(t('be.recordFields'));
    if (!PARTITIONS.includes(r.partition as never) || !KINDS.includes(r.kind as never)) bad(t('be.recordFields'));
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
      ...(typeof r.model_active === 'boolean' ? { model_active: r.model_active } : {}),
      ...(typeof r.model_epoch === 'number' ? { model_epoch: r.model_epoch } : {}),
    };
  }

  // -- BrainAdapter

  /** `health`, asked once; a failed probe is not remembered. */
  private readHealth(): Promise<HealthReport> {
    if (!this.health) {
      const pending = this.call('health').then((res): HealthReport => {
        const h = obj(res, t('be.what.health'));
        if (!Array.isArray(h.methods) || !h.methods.every((m) => typeof m === 'string')) bad(t('be.healthMethods'));
        const features: Record<string, boolean> = {};
        if (typeof h.features === 'object' && h.features !== null && !Array.isArray(h.features)) {
          for (const [k, v] of Object.entries(h.features)) if (typeof v === 'boolean') features[k] = v;
        }
        const a = h.access;
        const access =
          typeof a === 'object' && a !== null && typeof (a as { configured?: unknown }).configured === 'boolean' && typeof (a as { locked?: unknown }).locked === 'boolean'
            ? { configured: (a as AccessStatus).configured, locked: (a as AccessStatus).locked }
            : null;
        return { methods: h.methods as string[], features, modelEpoch: typeof h.model_epoch === 'number' ? h.model_epoch : null, access };
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
   * `health.features.two_judgements`; `proposedMethods` follows `base` when it
   * says so, else is true only if `health` advertises edit AND delete (F6).
   * Rejects with a BackendError when the back end cannot be reached.
   */
  static async probe(transport: Transport, base: RemoteOptions = {}): Promise<ProbeResult> {
    const report = await new RemoteBrainAdapter(transport, base).readHealth();
    const options: RemoteOptions = {
      ...base,
      twoJudgements: report.features.two_judgements === true,
      proposedMethods: base.proposedMethods ?? offersSourceEditing(report),
    };
    return { ...report, options, capabilities: capabilitiesFor(report.methods, options.proposedMethods === true) };
  }

  async capabilities(): Promise<ReadonlySet<AdapterMethod>> {
    return capabilitiesFor((await this.readHealth()).methods, this.proposedMethods);
  }

  async modelEpoch(): Promise<number | null> {
    return (await this.readHealth()).modelEpoch;
  }

  private accessOf(raw: unknown): AccessStatus {
    const r = obj(raw, t('be.what.access'));
    if (typeof r.configured !== 'boolean' || typeof r.locked !== 'boolean') bad(t('be.badAccess'));
    return { configured: r.configured, locked: r.locked };
  }

  async accessStatus(): Promise<AccessStatus> {
    return this.accessOf(await this.call('access_status'));
  }

  async unlock(password: string): Promise<AccessStatus> {
    if (typeof password !== 'string') throw new BackendError('INVALID_ARGUMENT', t('be.badPassword'));
    // The back end revokes the earlier session before it checks anything, so whatever was cached is stale either way.
    this.forgetPrivate();
    try {
      return this.accessOf(await this.call('unlock', { password }));
    } finally {
      this.forgetPrivate();
    }
  }

  async lock(): Promise<AccessStatus> {
    this.forgetPrivate();
    return this.accessOf(await this.call('lock'));
  }

  async submit(req: SubmitRequest): Promise<SubmitResult> {
    if (typeof req.immediate !== 'boolean') throw new BackendError('INVALID_ARGUMENT', t('be.bool', { name: 'immediate' }));
    const exclamation = req.exclamation ?? false;
    if (!this.twoJudgements && (!req.immediate || exclamation)) {
      // A back end without `two_judgements` rejects unknown fields and cannot store either; sending a plain
      // submit would make something the user said is not true eligible for training.
      this.unsupported(t('be.noTwoJudgements'));
    }
    const params: Record<string, unknown> = { text: req.text, partition: req.partition, kind: req.kind ?? 'diary' };
    if (req.self_speaker !== undefined) params.self_speaker = req.self_speaker;
    if (req.source_ref !== undefined) params.source_ref = req.source_ref;
    if (this.twoJudgements) {
      // Exactly as given: the back end lets an exclamation override immediate=false itself.
      params.immediate = req.immediate;
      params.exclamation = exclamation;
    }
    const r = obj(await this.call('submit', params), t('be.what.submit'));
    if (typeof r.source_id !== 'string') bad(t('be.submitFields'));
    return r as unknown as SubmitResult;
  }

  async preview(sourceId: string): Promise<PreviewResult> {
    const r = obj(await this.call('preview', { source_id: sourceId }), t('be.what.preview'));
    if (!Array.isArray(r.effects)) bad(t('be.previewFields'));
    return r as unknown as PreviewResult;
  }

  async confirm(sourceId: string, confirm: boolean): Promise<ReviewResult> {
    const r = obj(await this.call('review', { source_id: sourceId, agree: confirm }), t('be.what.review'));
    if (!Array.isArray(r.effects)) bad(t('be.reviewFields'));
    return r as unknown as ReviewResult;
  }

  async revoke(sourceId: string): Promise<ReviewResult> {
    const r = obj(await this.call('revoke', { source_id: sourceId }), t('be.what.revoke'));
    if (!Array.isArray(r.effects)) bad(t('be.revokeFields'));
    return r as unknown as ReviewResult;
  }

  async inputList(query: InputListQuery = {}): Promise<InputRecord[]> {
    const params: Record<string, unknown> = {};
    if (query.partition !== undefined) params.partition = query.partition;
    if (query.status !== undefined) params.status = query.status;
    if (query.limit !== undefined) params.limit = query.limit;
    const raw = await this.call('input_list', params);
    if (!Array.isArray(raw)) bad(t('be.badList'));
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
    const r = obj(await this.call('input_page', params), t('be.what.page'));
    if (!Array.isArray(r.items) || typeof r.total !== 'number' || typeof r.revision !== 'number') {
      bad(t('be.badPage'));
    }
    if (r.next_cursor !== null && typeof r.next_cursor !== 'string') bad(t('be.badPage'));
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
          const detail = obj(await this.call('input_get', { source_id: id }), t('be.what.input'));
          if (typeof detail.text === 'string') this.normalize(detail, detail.text);
        } catch {
          // A row that cannot be hydrated keeps an empty excerpt; the list itself still works.
        }
      }
    };
    await Promise.all(Array.from({ length: Math.min(this.concurrency, missing.length) }, worker));
  }

  async inputGet(sourceId: string): Promise<InputDetail> {
    const r = obj(await this.call('input_get', { source_id: sourceId }), t('be.what.input'));
    if (typeof r.text !== 'string') bad(t('be.inputText'));
    return { ...this.normalize(r, r.text), text: r.text };
  }

  async inputEdit(sourceId: string, edit: InputEditRequest): Promise<InputRecord> {
    if (!this.proposedMethods) this.unsupported(t('be.op.edit'));
    const params: Record<string, unknown> = { source_id: sourceId, text: edit.text, immediate: edit.immediate };
    if (edit.kind !== undefined) params.kind = edit.kind;
    if (edit.self_speaker !== undefined) params.self_speaker = edit.self_speaker;
    return this.normalize(await this.call('input_edit', params), edit.text);
  }

  async inputDelete(sourceId: string): Promise<void> {
    if (!this.proposedMethods) this.unsupported(t('be.op.delete'));
    await this.call('input_delete', { source_id: sourceId });
    this.excerpts.delete(sourceId);
  }

  async modelReset(): Promise<void> {
    await this.call('model_reset', { confirm: 'RESET_MODEL', clear_history: true });
  }

  async state(): Promise<ModelState> {
    return obj(await this.call('state'), t('be.what.state')) as unknown as ModelState;
  }

  async effects(sourceId?: string): Promise<ParameterEffect[]> {
    const raw = await this.call('effects', sourceId === undefined ? {} : { source_id: sourceId });
    if (!Array.isArray(raw)) bad(t('be.badEffects'));
    return raw as ParameterEffect[];
  }

  async rank(options: { id: string; impacts: Partial<Record<ParameterId, number>> }[]): Promise<RankResult> {
    return obj(await this.call('rank', { options }), t('be.what.rank')) as unknown as RankResult;
  }
}
