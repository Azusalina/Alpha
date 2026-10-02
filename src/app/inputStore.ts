/**
 * The orchestration store of the entry and records panels (round 3, part 9,
 * D54–D57). External store + hook, like `humanStore`. Panels render this
 * state and call these actions; they never call the adapter themselves, so
 * the race rules and the performance trigger live in exactly one place.
 *
 * Everything goes through `getAdapter()` (D56): this file does not know whether
 * the back end is the mock, a real one or none. Every action catches
 * `BackendError` into `error` (shown inline by the panel, never swallowed) and
 * never rejects.
 *
 * Race safety. Three layers:
 *  - `epoch` bumps on every `reset()` (a backend change, leaving demo): any
 *    response that started before it is dropped;
 *  - reads (refresh, loadDetail, loadPreview, loadEffects) carry a per-key
 *    counter: only the newest request of that key may write;
 *  - a mutation (submit, confirm, revoke, edit, remove) is refused while one is
 *    still running on the same record (submit: while a submit runs), so the
 *    order the back end applies them in is the order the user made them in. The
 *    buttons read `busy` to disable themselves.
 * After any mutation the record is re-read from the back end (`inputGet`) and
 * patched into the list, so what is shown is what is stored.
 *
 * The brain's answer (D57): after an event that TRAINS, `humanStore.perform` is
 * called with the input's partition and a strength from its effects. A training
 * event is an `agreed` result that changed the model: it carries effects, or a
 * fresh approval's `observed_terms`, or a `restored_fit`. An identical repeated
 * judgement (no effects, none of those) is not one. A disagreed or revoked
 * result never performs. Where the lightning leaves from: the element
 * registered with `registerAnchor(key, el)` for the record (or ENTRY_ANCHOR for
 * a submit); its rect centre is read at the moment of the call, else null.
 */

import { useSyncExternalStore } from 'react';

import {
  BackendError,
  backendStore,
  getAdapter,
  isTrainable,
  normalizeForSubmit,
} from '../backend';
import type {
  AdapterMethod,
  BackendErrorCode,
  InputDetail,
  InputEditRequest,
  InputRecord,
  InputStatus,
  Interpretation,
  Kind,
  ParameterEffect,
  Partition,
  PreviewResult,
  ReviewResult,
  SubmitRequest,
  SubmitResult,
  TranslatorEffect,
} from '../backend';
import { humanStore } from './humanStore';

/** Key of the anchor element the entry form registers; the lightning of a submit leaves from it. */
export const ENTRY_ANCHOR = 'entry';

/** Records per page of `refresh()` / `loadMore()` (api.md allows 1–100). */
export const PAGE_SIZE = 50;

export type RecordAction = 'detail' | 'preview' | 'effects' | 'confirm' | 'revoke' | 'edit' | 'remove';

/** What one record has loaded. `null` = not loaded (or dropped because it went stale). */
export interface RecordCache {
  /** The original text (`inputGet`). The text that spans refer to. */
  detail: InputDetail | null;
  /**
   * Hypothetical effects, only for a record that is not `agreed`. May be stale:
   * a review or an edit clears it. After a review show `formalEffects` instead.
   */
  preview: PreviewResult | null;
  /** The effect history of this record (`effects(id)`), for an agreed or once-agreed record. */
  effects: ParameterEffect[] | null;
  /**
   * The effects the LAST judgement of this record committed (they carry
   * revisions; a reversal has `action: 'revoke'`). An empty array means that
   * judgement changed no parameter: show "未提取到可拟合的证据" (or, after a
   * repeated identical judgement, nothing new). `null` = no judgement since load.
   */
  formalEffects: ParameterEffect[] | null;
  /** The last judgement changed nothing (identical repeat): no effects, no event. */
  lastWasNoop: boolean;
}

/** What the entry form shows after a submit. */
export interface SubmitOutcome {
  source_id: string;
  /** The exact string that was sent (normalised); every span in this outcome refers to it. */
  text: string;
  partition: Partition;
  kind: Kind;
  status: InputStatus;
  immediate: boolean | null;
  confirm: boolean | null;
  exclamation: boolean;
  confirmed_by: SubmitResult['confirmed_by'] | null;
  reason: SubmitResult['reason'] | null;
  /**
   * The FORMAL effects of an exclamation submit (revisions present). Empty for
   * every other submit: its effects are hypothetical, see `preview`.
   */
  effects: ParameterEffect[];
  translator_effects: TranslatorEffect[];
  observed_terms?: number;
  interpretation?: Interpretation;
  /** true: the input trained the model at once (status agreed): show `effects` as they are, no preview. */
  trained: boolean;
  /**
   * For a `pending` submit: the preview of what confirming would do
   * (hypothetical, no revisions). Never present when `trained`.
   */
  preview: PreviewResult | null;
  previewState: 'none' | 'loading' | 'ready' | 'error';
}

export interface InputError {
  code: BackendErrorCode;
  message: string;
  /** Which action failed. */
  action: 'refresh' | 'loadMore' | 'submit' | RecordAction | 'capabilities';
  /** The record it was about, if any. */
  id: string | null;
}

export interface InputState {
  /** Newest first. Only what has been loaded (`total` says how many exist). */
  records: InputRecord[];
  /** Every input that exists on the back end (from the page response). */
  total: number;
  /** `refresh()` has completed for the current back end. */
  loaded: boolean;
  /** There is another page: `loadMore()`. */
  hasMore: boolean;
  /** The row whose detail is open in the list (one at a time), or null. */
  expandedId: string | null;
  /** The record whose editor is open, or null. The editor is the records panel's; the store only keeps its id for Escape. */
  editingId: string | null;
  cache: Record<string, RecordCache>;
  busy: {
    refresh: boolean;
    submit: boolean;
    /** Actions running per record id. */
    records: Record<string, RecordAction[]>;
  };
  /** The result panel of the entry form (null = closed). */
  lastResult: SubmitOutcome | null;
  error: InputError | null;
  /** Methods the back end offers; null until loaded (and in "后端未连接": empty). */
  capabilities: AdapterMethod[] | null;
  /** `health.model_epoch` of the connected back end; null when unknown. Effects of an older epoch are history, not the current model. */
  modelEpoch: number | null;
  /** The `backendStore` generation this state belongs to. */
  generation: number;
}

type Listener = () => void;

const emptyCache = (): RecordCache => ({ detail: null, preview: null, effects: null, formalEffects: null, lastWasNoop: false });

const clamp = (x: number, lo: number, hi: number): number => Math.min(hi, Math.max(lo, x));

/**
 * The strength of the brain's answer: `clamp(0.25 + 0.15·n + 0.5·Σ|Δ|, 0.25, 1)`
 * for `n` effects (D57). There is no mapping from a parameter to a region; the
 * visual keys off the state and this number.
 */
export function performIntensity(effects: readonly Pick<ParameterEffect, 'delta'>[]): number {
  let sum = 0;
  for (const e of effects) sum += Math.abs(Number.isFinite(e.delta) ? e.delta : 0);
  return clamp(0.25 + 0.15 * effects.length + sum * 0.5, 0.25, 1);
}

/** Did this decision change the model (so the brain should answer)? */
export function isTrainingEvent(r: {
  status: InputStatus;
  effects?: readonly unknown[];
  observed_terms?: number;
  restored_fit?: boolean;
}): boolean {
  return r.status === 'agreed' && ((r.effects?.length ?? 0) > 0 || r.observed_terms !== undefined || r.restored_fit === true);
}

function toError(e: unknown, action: InputError['action'], id: string | null): InputError {
  if (e instanceof BackendError) return { code: e.code, message: e.message, action, id };
  return { code: 'INTERNAL_ERROR', message: e instanceof Error ? e.message : String(e), action, id };
}

/** A record as the list shows it: the detail without its text. */
function toRecord(d: InputDetail): InputRecord {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const { text: _text, ...rest } = d;
  return rest;
}

class InputStore {
  private state: InputState = this.fresh(backendStore.get().generation);
  private listeners = new Set<Listener>();

  private epoch = 0;
  private cursor: string | null = null;
  private refreshSeq = 0;
  private submitSeq = 0;
  private readSeq = new Map<string, number>();
  private anchors = new Map<string, HTMLElement>();
  /** Partition of inputs submitted in this session, for a review result that omits it. */
  private submitted = new Map<string, Partition>();

  constructor() {
    // A different back end (demo entered or left, a connect): nothing held is valid any more.
    backendStore.subscribe(() => {
      if (backendStore.get().generation !== this.state.generation) this.reset();
    });
  }

  private fresh(generation: number): InputState {
    return {
      records: [],
      total: 0,
      loaded: false,
      hasMore: false,
      expandedId: null,
      editingId: null,
      cache: {},
      busy: { refresh: false, submit: false, records: {} },
      lastResult: null,
      error: null,
      capabilities: null,
      modelEpoch: null,
      generation,
    };
  }

  // ---- store plumbing ------------------------------------------------------------

  get = (): InputState => this.state;

  subscribe = (l: Listener): (() => void) => {
    this.listeners.add(l);
    return () => this.listeners.delete(l);
  };

  private set(patch: Partial<InputState>): void {
    this.state = { ...this.state, ...patch };
    for (const l of this.listeners) l();
  }

  private patchCache(id: string, patch: Partial<RecordCache>): void {
    this.set({ cache: { ...this.state.cache, [id]: { ...(this.state.cache[id] ?? emptyCache()), ...patch } } });
  }

  private setBusy(id: string, action: RecordAction, on: boolean): void {
    const cur = this.state.busy.records[id] ?? [];
    const next = on ? [...cur, action] : cur.filter((a, i) => !(a === action && i === cur.lastIndexOf(action)));
    const records = { ...this.state.busy.records };
    if (next.length) records[id] = next;
    else delete records[id];
    this.set({ busy: { ...this.state.busy, records } });
  }

  private setBusyFlag(flag: 'refresh' | 'submit', on: boolean): void {
    this.set({ busy: { ...this.state.busy, [flag]: on } });
  }

  private fail(e: unknown, action: InputError['action'], id: string | null): void {
    this.set({ error: toError(e, action, id) });
  }

  /** True while a response that began at (`epoch`) may still be applied. */
  private live(epoch: number): boolean {
    return epoch === this.epoch && backendStore.get().generation === this.state.generation;
  }

  private bump(key: string): number {
    const n = (this.readSeq.get(key) ?? 0) + 1;
    this.readSeq.set(key, n);
    return n;
  }

  /** A judgement, edit or delete starts: whatever preview / history is still on its way is stale. */
  private invalidate(id: string): void {
    this.bump(`${id}:preview`);
    this.bump(`${id}:effects`);
  }

  /** Is this record (still) held? */
  has = (id: string): boolean => this.state.records.some((r) => r.source_id === id);

  record = (id: string): InputRecord | undefined => this.state.records.find((r) => r.source_id === id);

  /** Does the current back end offer `method`? False until capabilities are loaded. */
  can = (method: AdapterMethod): boolean => this.state.capabilities?.includes(method) ?? false;

  isBusy = (id: string, action?: RecordAction): boolean => {
    const a = this.state.busy.records[id];
    return !!a && (action ? a.includes(action) : a.length > 0);
  };

  /** A mutation of this record is running (the buttons disable themselves on this). */
  isMutating = (id: string): boolean => {
    const a = this.state.busy.records[id];
    return !!a && a.some((x) => x === 'confirm' || x === 'revoke' || x === 'edit' || x === 'remove');
  };

  dismissError = (): void => {
    if (this.state.error) this.set({ error: null });
  };

  // ---- anchors -------------------------------------------------------------------

  /**
   * Register (element) or unregister (null) the DOM element an event "comes
   * from": the brain's lightning leaves from its centre. Call from a ref
   * callback: `ref={(el) => inputStore.registerAnchor(id, el)}`.
   */
  registerAnchor = (key: string, el: HTMLElement | null): void => {
    if (el) this.anchors.set(key, el);
    else this.anchors.delete(key);
  };

  private anchorCss(key: string | null): [number, number] | null {
    const el = key ? this.anchors.get(key) : undefined;
    if (!el || !el.isConnected) return null;
    const r = el.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) return null;
    return [r.left + r.width / 2, r.top + r.height / 2];
  }

  private performFor(partition: Partition, effects: readonly ParameterEffect[], anchorKey: string | null): void {
    humanStore.perform({ partition, intensity: performIntensity(effects), fromCss: this.anchorCss(anchorKey) });
  }

  /**
   * Play the brain's answer to a record again, from what is already held (no
   * request): only a record that trains the current model (both judgements T).
   * The strength comes from the effects the row has loaded, else a middling one.
   */
  replay = (id: string): boolean => {
    const rec = this.record(id);
    if (!rec || !isTrainable(rec)) return false;
    const c = this.state.cache[id];
    const effects = c?.formalEffects ?? c?.effects ?? [];
    this.performFor(rec.partition, effects, id);
    return true;
  };

  /**
   * Reset the personalised model and clean its history (adapter `modelReset`), then drop everything
   * held and read the lists again, so no row, effect or graph node of the old model survives.
   * Resolves with the error shown to the user, or null on success.
   */
  resetModel = async (): Promise<InputError | null> => {
    try {
      await getAdapter().modelReset();
    } catch (e) {
      const err = toError(e, 'refresh', null);
      this.set({ error: err });
      return err;
    }
    humanStore.set({ reply: null });
    this.reset();
    await this.refresh();
    return null;
  };

  // ---- lifecycle -----------------------------------------------------------------

  /** Forget everything (back end changed, demo left) and drop every response still on its way. */
  reset = (): void => {
    this.epoch++;
    this.cursor = null;
    this.readSeq.clear();
    this.submitted.clear();
    this.state = this.fresh(backendStore.get().generation);
    for (const l of this.listeners) l();
  };

  /** Load capabilities (once per back end) and the first page, unless already done. Panels call it on mount and when `generation` changes. */
  ensureLoaded = async (): Promise<void> => {
    if (this.state.loaded || this.state.busy.refresh) return;
    if (backendStore.get().mode === 'unconnected') {
      await this.loadCapabilities();
      return;
    }
    await this.refresh();
  };

  private loadCapabilities = async (): Promise<void> => {
    const epoch = this.epoch;
    try {
      const caps = await getAdapter().capabilities();
      if (!this.live(epoch)) return;
      this.set({ capabilities: [...caps] });
    } catch (e) {
      if (this.live(epoch)) this.fail(e, 'capabilities', null);
    }
  };

  /** Reload the first page (newest first). Replaces the list; drops the pages loaded before. */
  refresh = async (): Promise<void> => {
    const epoch = this.epoch;
    const seq = ++this.refreshSeq;
    this.setBusyFlag('refresh', true);
    try {
      const adapter = getAdapter();
      const caps = await adapter.capabilities();
      const modelEpoch = await adapter.modelEpoch().catch(() => null);
      if (!this.live(epoch) || seq !== this.refreshSeq) return;
      const res = caps.has('inputPage')
        ? await adapter.inputPage({ limit: PAGE_SIZE })
        : await adapter.inputList({ limit: PAGE_SIZE }).then((items) => ({ items, total: items.length, next_cursor: null as string | null }));
      if (!this.live(epoch) || seq !== this.refreshSeq) return;
      this.cursor = res.next_cursor;
      const keep = new Set(res.items.map((r) => r.source_id));
      const cache = Object.fromEntries(Object.entries(this.state.cache).filter(([id]) => keep.has(id)));
      this.set({
        records: res.items,
        total: res.total,
        hasMore: res.next_cursor !== null,
        loaded: true,
        capabilities: [...caps],
        modelEpoch,
        cache,
        expandedId: this.state.expandedId && keep.has(this.state.expandedId) ? this.state.expandedId : null,
        editingId: this.state.editingId && keep.has(this.state.editingId) ? this.state.editingId : null,
        error: this.state.error?.action === 'refresh' ? null : this.state.error,
      });
    } catch (e) {
      if (this.live(epoch) && seq === this.refreshSeq) this.fail(e, 'refresh', null);
    } finally {
      if (this.live(epoch) && seq === this.refreshSeq) this.setBusyFlag('refresh', false);
    }
  };

  /**
   * The next page. On `STALE_CURSOR` (an input changed since the cursor was
   * issued) the pages held are thrown away and page 1 is loaded again.
   */
  loadMore = async (): Promise<void> => {
    if (!this.cursor || this.state.busy.refresh) return;
    const epoch = this.epoch;
    const seq = this.refreshSeq;
    const cursor = this.cursor;
    this.setBusyFlag('refresh', true);
    try {
      const res = await getAdapter().inputPage({ limit: PAGE_SIZE, cursor });
      if (!this.live(epoch) || seq !== this.refreshSeq || this.cursor !== cursor) return;
      const have = new Set(this.state.records.map((r) => r.source_id));
      this.cursor = res.next_cursor;
      this.set({
        records: [...this.state.records, ...res.items.filter((r) => !have.has(r.source_id))],
        total: res.total,
        hasMore: res.next_cursor !== null,
      });
    } catch (e) {
      if (!this.live(epoch)) return;
      if (e instanceof BackendError && e.code === 'STALE_CURSOR') {
        this.cursor = null;
        this.setBusyFlag('refresh', false);
        await this.refresh();
        return;
      }
      this.fail(e, 'loadMore', null);
    } finally {
      if (this.live(epoch) && this.state.busy.refresh && seq === this.refreshSeq) this.setBusyFlag('refresh', false);
    }
  };

  // ---- reads ---------------------------------------------------------------------

  /** Read one record from the back end and patch it into the list (and the cache's detail). */
  private async reread(id: string, epoch: number): Promise<InputDetail | null> {
    const key = `${id}:detail`;
    const seq = this.bump(key);
    this.setBusy(id, 'detail', true);
    try {
      const d = await getAdapter().inputGet(id);
      if (!this.live(epoch) || seq !== this.readSeq.get(key)) return null;
      const rec = toRecord(d);
      const records = this.has(id)
        ? this.state.records.map((r) => (r.source_id === id ? rec : r))
        : [rec, ...this.state.records];
      this.set({ records, total: this.has(id) ? this.state.total : this.state.total + 1 });
      this.patchCache(id, { detail: d });
      return d;
    } catch (e) {
      if (this.live(epoch) && seq === this.readSeq.get(key)) this.fail(e, 'detail', id);
      return null;
    } finally {
      if (this.live(epoch)) this.setBusy(id, 'detail', false);
    }
  }

  /** Load the original text of a record (cached; call again to re-read). */
  loadDetail = async (id: string): Promise<InputDetail | null> => {
    return this.reread(id, this.epoch);
  };

  /** Hypothetical effects of a record that is not `agreed`. Never changes anything stored. */
  loadPreview = async (id: string): Promise<PreviewResult | null> => {
    const rec = this.record(id);
    if (rec?.status === 'agreed') return null;
    const epoch = this.epoch;
    const key = `${id}:preview`;
    const seq = this.bump(key);
    this.setBusy(id, 'preview', true);
    try {
      const p = await getAdapter().preview(id);
      if (!this.live(epoch) || seq !== this.readSeq.get(key)) return null;
      this.patchCache(id, { preview: p });
      return p;
    } catch (e) {
      if (this.live(epoch) && seq === this.readSeq.get(key)) this.fail(e, 'preview', id);
      return null;
    } finally {
      if (this.live(epoch)) this.setBusy(id, 'preview', false);
    }
  };

  /** The committed effect history of one record. */
  loadEffects = async (id: string): Promise<ParameterEffect[] | null> => {
    const epoch = this.epoch;
    const key = `${id}:effects`;
    const seq = this.bump(key);
    this.setBusy(id, 'effects', true);
    try {
      const list = await getAdapter().effects(id);
      if (!this.live(epoch) || seq !== this.readSeq.get(key)) return null;
      this.patchCache(id, { effects: list });
      return list;
    } catch (e) {
      if (this.live(epoch) && seq === this.readSeq.get(key)) this.fail(e, 'effects', id);
      return null;
    } finally {
      if (this.live(epoch)) this.setBusy(id, 'effects', false);
    }
  };

  /**
   * Open (or, for the open one, close) a row. Opening loads the text and, by
   * status, the preview (pending / disagreed / revoked) or the effect history
   * (agreed). `null` closes.
   */
  expand = (id: string | null): void => {
    if (id === null || id === this.state.expandedId) {
      this.set({ expandedId: null, editingId: null });
      return;
    }
    this.set({ expandedId: id, editingId: this.state.editingId === id ? id : null });
    void this.loadForExpanded(id);
  };

  private async loadForExpanded(id: string): Promise<void> {
    const rec = this.record(id);
    const tasks: Promise<unknown>[] = [this.loadDetail(id)];
    if (rec && rec.status !== 'agreed') tasks.push(this.loadPreview(id));
    else tasks.push(this.loadEffects(id));
    await Promise.all(tasks);
  }

  // ---- entry ---------------------------------------------------------------------

  /**
   * Submit one input. `req.text` is normalised here (one leading BOM dropped,
   * lone surrogates refused), so the string the outcome's spans refer to is
   * `outcome.text`. Then:
   *  - `agreed` (exclamation): the result's FORMAL effects are kept in
   *    `lastResult.effects`, no preview is requested, and the brain performs;
   *  - `pending`: the preview is requested into `lastResult.preview`
   *    (`previewState`), hypothetical and without revisions;
   *  - `disagreed` (immediate false): only the status; nothing is previewed.
   * Resolves the outcome, or null if it failed or was stale (see `error`).
   */
  submitInput = async (req: SubmitRequest): Promise<SubmitOutcome | null> => {
    if (this.state.busy.submit) return null;
    const epoch = this.epoch;
    const seq = ++this.submitSeq;
    this.set({ error: null });
    this.setBusyFlag('submit', true);
    try {
      const text = normalizeForSubmit(req.text);
      const sent: SubmitRequest = { ...req, text };
      const res = await getAdapter().submit(sent);
      if (!this.live(epoch) || seq !== this.submitSeq) return null;
      const formal = res.effects ?? [];
      const trained = res.status === 'agreed';
      const outcome: SubmitOutcome = {
        source_id: res.source_id,
        text,
        partition: res.partition,
        kind: sent.kind ?? 'diary',
        status: res.status,
        immediate: res.immediate ?? null,
        confirm: res.confirm ?? null,
        exclamation: res.exclamation ?? sent.exclamation === true,
        confirmed_by: res.confirmed_by ?? null,
        reason: res.reason ?? null,
        effects: formal,
        translator_effects: res.translator_effects ?? [],
        observed_terms: res.observed_terms,
        interpretation: res.interpretation,
        trained,
        preview: null,
        previewState: res.status === 'pending' ? 'loading' : 'none',
      };
      this.submitted.set(res.source_id, res.partition);
      this.set({ lastResult: outcome });
      this.patchCache(res.source_id, { formalEffects: trained ? formal : null });
      if (trained && isTrainingEvent(res)) this.performFor(res.partition, formal, ENTRY_ANCHOR);
      // the list: patch the new record in (a full refresh would drop loaded pages)
      await this.reread(res.source_id, epoch);
      if (res.status === 'pending') void this.previewForOutcome(res.source_id, epoch);
      return outcome;
    } catch (e) {
      if (this.live(epoch) && seq === this.submitSeq) this.fail(e, 'submit', null);
      return null;
    } finally {
      if (this.live(epoch) && seq === this.submitSeq) this.setBusyFlag('submit', false);
    }
  };

  private async previewForOutcome(id: string, epoch: number): Promise<void> {
    try {
      const p = await getAdapter().preview(id);
      const cur = this.state.lastResult;
      if (!this.live(epoch) || !cur || cur.source_id !== id) return;
      this.set({ lastResult: { ...cur, preview: p, previewState: 'ready' } });
      this.patchCache(id, { preview: p });
    } catch (e) {
      const cur = this.state.lastResult;
      if (!this.live(epoch) || !cur || cur.source_id !== id) return;
      this.set({ lastResult: { ...cur, previewState: 'error' } });
      this.fail(e, 'preview', id);
    }
  }

  /** Close the entry form's result panel. */
  dismissResult = (): void => {
    if (this.state.lastResult) this.set({ lastResult: null });
  };

  // ---- judgements ----------------------------------------------------------------

  /**
   * The second judgement (D55). `true` trains the model when the result is
   * `agreed` (then the brain performs); `false` on an agreed input removes it
   * from training (reversal effects, status disagreed / confirm_false). An
   * `immediate_false` input is refused by the back end (INVALID_ARGUMENT): the
   * error says so; the panel should send the user to edit it.
   */
  confirm = async (id: string, value: boolean): Promise<ReviewResult | null> => {
    return this.judge(id, 'confirm', () => getAdapter().confirm(id, value));
  };

  /** Withdraw an agreed input from training (status revoked). History stays. */
  revoke = async (id: string): Promise<ReviewResult | null> => {
    return this.judge(id, 'revoke', () => getAdapter().revoke(id));
  };

  private async judge(id: string, action: 'confirm' | 'revoke', call: () => Promise<ReviewResult>): Promise<ReviewResult | null> {
    if (this.isMutating(id)) return null;
    const epoch = this.epoch;
    this.set({ error: null });
    this.invalidate(id);
    this.setBusy(id, action, true);
    try {
      const res = await call();
      if (!this.live(epoch)) return null;
      const effects = res.effects ?? [];
      const noop = effects.length === 0 && res.observed_terms === undefined && res.restored_fit !== true;
      // the preview was made before this judgement: stale, dropped; the review's own effects replace it
      this.patchCache(id, { formalEffects: effects, preview: null, effects: null, lastWasNoop: noop });
      // a review result may omit the partition: take it from what is held, else read the record first
      let d: InputDetail | null = null;
      let partition = res.partition ?? this.record(id)?.partition ?? this.state.cache[id]?.detail?.partition ?? this.submitted.get(id);
      if (!partition) {
        d = await this.reread(id, epoch);
        partition = d?.partition;
      }
      if (!this.live(epoch)) return res;
      if (action === 'confirm' && partition && isTrainingEvent(res)) this.performFor(partition, effects, id);
      d = d ?? (await this.reread(id, epoch));
      if (d && this.live(epoch)) {
        if (this.state.expandedId === id) {
          // the list reflects the new status; refresh what the open row shows under it
          if (d.status === 'agreed') void this.loadEffects(id);
          else void this.loadPreview(id);
        }
        // a submit's result panel about this same input is out of date now
        const r = this.state.lastResult;
        if (r && r.source_id === id) this.set({ lastResult: null });
      }
      return res;
    } catch (e) {
      if (this.live(epoch)) this.fail(e, action, id);
      return null;
    } finally {
      if (this.live(epoch)) this.setBusy(id, action, false);
    }
  }

  // ---- edit / delete (F6) --------------------------------------------------------

  /** Open or close the editor of a record (the records panel draws it). */
  openEditor = (id: string | null): void => {
    this.set({ editingId: id, expandedId: id ?? this.state.expandedId });
    if (id && this.state.expandedId !== id) void this.loadForExpanded(id);
  };

  /**
   * Replace the text of a record that is not agreed (F6). Against a back end that
   * does not offer it the adapter answers UNSUPPORTED and the panel greys the
   * button out via `can('inputEdit')`.
   */
  edit = async (id: string, req: InputEditRequest): Promise<InputRecord | null> => {
    if (this.isMutating(id)) return null;
    const epoch = this.epoch;
    this.set({ error: null });
    this.invalidate(id);
    this.setBusy(id, 'edit', true);
    try {
      const text = normalizeForSubmit(req.text);
      const rec = await getAdapter().inputEdit(id, { ...req, text });
      if (!this.live(epoch)) return null;
      // the old text, its spans, its preview and its effects no longer apply
      this.patchCache(id, { detail: null, preview: null, effects: null, formalEffects: null, lastWasNoop: false });
      this.set({ records: this.state.records.map((r) => (r.source_id === id ? rec : r)), editingId: null });
      if (this.state.lastResult?.source_id === id) this.set({ lastResult: null });
      if (this.state.expandedId === id) void this.loadForExpanded(id);
      // every input cursor is stale after an edit: reload page 1 (the model state re-reads by itself)
      void this.refresh();
      return rec;
    } catch (e) {
      if (this.live(epoch)) this.fail(e, 'edit', id);
      return null;
    } finally {
      if (this.live(epoch)) this.setBusy(id, 'edit', false);
    }
  };

  /**
   * Delete a record, whatever its status, together with its whole history (the user's
   * decision, F6). The back end deletes the source's records hard (no tombstone) and
   * withdraws an agreed input's contribution first; backups and other inputs' frozen
   * evidence are untouched, so the wording must not claim a forensic erase.
   */
  remove = async (id: string): Promise<boolean> => {
    if (this.isMutating(id)) return false;
    const epoch = this.epoch;
    this.set({ error: null });
    this.invalidate(id);
    this.setBusy(id, 'remove', true);
    try {
      await getAdapter().inputDelete(id);
      if (!this.live(epoch)) return false;
      const cache = { ...this.state.cache };
      delete cache[id];
      this.set({
        records: this.state.records.filter((r) => r.source_id !== id),
        total: Math.max(0, this.state.total - 1),
        cache,
        expandedId: this.state.expandedId === id ? null : this.state.expandedId,
        editingId: this.state.editingId === id ? null : this.state.editingId,
        lastResult: this.state.lastResult?.source_id === id ? null : this.state.lastResult,
      });
      // the old cursors are stale and the totals moved: reload page 1; the model state re-reads
      // because the record list changed (a deleted agreed input no longer contributes)
      void this.refresh();
      return true;
    } catch (e) {
      if (this.live(epoch)) this.fail(e, 'remove', id);
      return false;
    } finally {
      if (this.live(epoch)) this.setBusy(id, 'remove', false);
    }
  };

  // ---- Escape --------------------------------------------------------------------

  /**
   * One Escape press: closes the topmost layer — the editor, then the expanded
   * row, then the entry form's result panel. Returns whether it closed
   * something (false: let the next handler have the key). `drilledIn` says which
   * panel is on screen, so a layer that is not visible never swallows the key:
   * true = only the records panel's layers (editor, row), false = only the entry
   * form's result panel; leave it out to consider all three.
   */
  closeTopLayer = (drilledIn?: boolean): boolean => {
    if (drilledIn !== false) {
      if (this.state.editingId) {
        this.set({ editingId: null });
        return true;
      }
      if (this.state.expandedId) {
        this.set({ expandedId: null });
        return true;
      }
    }
    if (drilledIn !== true && this.state.lastResult) {
      this.set({ lastResult: null });
      return true;
    }
    return false;
  };
}

export const inputStore = new InputStore();

/** React hook: the whole state (immutable snapshot, replaced on every change). */
export function useInputs(): InputState {
  return useSyncExternalStore(inputStore.subscribe, inputStore.get, inputStore.get);
}
