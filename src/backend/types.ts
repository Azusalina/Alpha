/**
 * The contract between the UI and the local brain model (D54–D56).
 *
 * Two layers, kept apart on purpose:
 *  - what `back-end-core/docs/api.md` (schema_version 1) provides. Since the
 *    back end's 2026-10-01 replies that includes the two judgements (F1-F4),
 *    `exclamation`, preview of any untrained input (F7) and `input_page` (F5).
 *    The real back end only offers them when `health.features.two_judgements`
 *    is true; `RemoteBrainAdapter.probe` reads that flag;
 *  - editing and deleting an input (F6: `inputEdit`, `inputDelete`,
 *    `edited_at`): the back end implements them (23 methods,
 *    `health.features.source_edit` / `source_delete`); `RemoteBrainAdapter.probe`
 *    switches them on only when `health` advertises all four. Against an older
 *    back end the UI greys them out; the mock marks them 仅演示.
 *
 * Text spans are zero-based Unicode CODE POINT offsets into the exact string
 * that was submitted, end exclusive. JavaScript strings index UTF-16 code
 * units, so never slice with a span directly: use `spans.ts`.
 */

export const PARTITIONS = ['rational', 'emotional', 'crazy'] as const;
export type Partition = (typeof PARTITIONS)[number];

export const KINDS = ['diary', 'chat', 'philosophy'] as const;
export type Kind = (typeof KINDS)[number];

export const PARAMETER_IDS = [
  'value.autonomy',
  'value.fairness',
  'value.care',
  'value.truth',
  'value.security',
  'value.growth',
  'value.achievement',
  'value.connection',
  'affect.disappointment',
  'affect.sadness',
  'affect.happiness',
  'affect.anger',
  'expression.less_initiative',
] as const;
export type ParameterId = (typeof PARAMETER_IDS)[number];

/** Backend limit on one input, in Unicode code points (`translator.pipeline.MAX_CHARS`). */
export const MAX_INPUT_CHARS = 1_000_000;

/** `[start, end)`, code points. */
export type Span = readonly [number, number];

export type InputStatus = 'pending' | 'agreed' | 'disagreed' | 'revoked';

/**
 * Why an input is not (or no longer) in training (api.md, F2).
 * `immediate_false`: the user said "not true right now" when writing it.
 * `confirm_false`: the second judgement, made inside the brain view, was F.
 * `user_revoked`: an agreed input was explicitly withdrawn (status `revoked`).
 */
export type InputReason = 'immediate_false' | 'confirm_false' | 'user_revoked';

/**
 * How the last second judgement was reached: `exclamation` (set together with
 * `immediate` at submit), `manual` (the user, inside the brain view) or
 * `legacy` (data written before the two judgements existed; consent was never
 * given in the new sense and is never invented).
 */
export type ConfirmedBy = 'exclamation' | 'manual' | 'legacy';

/**
 * The dual-judgement metadata the real back end puts on every decision
 * (submit, review, revoke, preview) and on every input row.
 */
export interface ApprovalMetadata {
  status: InputStatus;
  immediate: boolean;
  /** null = the second judgement has not been made. */
  confirm: boolean | null;
  exclamation: boolean;
  confirmed_by: ConfirmedBy | null;
  reason: InputReason | null;
}

/** Decision results carry the metadata; optional here so an older back end still type-checks. */
export type DecisionMetadata = Partial<Omit<ApprovalMetadata, 'status'>>;

/**
 * What submitting really stores (engine.py `submit_result`): an `exclamation`
 * sets BOTH judgements true, even when `immediate` was false or the box was not
 * ticked, so the form shows immediate as implied-checked and locked while
 * exclamation is on. `confirm` is then already true; every other submit
 * leaves it null.
 */
export function effectiveJudgement(immediate: boolean, exclamation: boolean): { immediate: boolean; confirm: true | null } {
  return exclamation ? { immediate: true, confirm: true } : { immediate, confirm: null };
}

/**
 * `interpretation` of a preview or a fresh approval (api.schema.json
 * `$defs.interpretation`). Only the evidence-policy diagnostics are typed; the
 * UI must not infer a final effect from `withheld_values` (an explicit
 * correction can override a withheld rule). Old frozen contexts lack the newer
 * fields; never fabricate them.
 */
export interface Interpretation {
  correction_revision: number;
  corrections: unknown[];
  learned_rules: unknown[];
  evidence_policy?: string;
  withheld_values?: { reason: string; parameters: ParameterId[]; evidence: string; span: Span }[];
  withheld_count?: number;
  withheld_truncated?: boolean;
  legacy_context_unavailable?: true;
}

// ---- results ---------------------------------------------------------------------

/** One parameter change with its evidence (api.md "Review and client state"). */
export interface ParameterEffect {
  /** Absent on a preview: hypothetical effects have no revision. */
  revision?: number;
  source_id: string;
  partition: Partition;
  parameter: ParameterId;
  before: number;
  after: number;
  delta: number;
  support_before: number;
  support_after: number;
  /** Exact source excerpt the rule matched. */
  evidence: string;
  span: Span;
  rule_id: string;
  action: 'preview' | 'approve' | 'revoke';
  created_at?: string;
  /** The model epoch that wrote it (formal effects). History is never rewritten: compare with `health.model_epoch`. */
  model_epoch?: number;
}

export interface TranslatorEffect {
  term: string;
  documents_before: number;
  documents_after: number;
  source_id: string;
}

export interface TranslationCue {
  category: string;
  value: string;
  evidence: string;
  span: Span;
  speaker: string;
  negated: boolean;
}

export interface TranslationCandidate {
  type: string;
  value: string;
  evidence: string;
  span: Span;
  speaker: string;
  certainty: string;
  status: string;
}

/** `translator.translate` output (schema_version 1). Lexical rules only. */
export interface Translation {
  schema_version: number;
  kind: 'diary' | 'chat';
  self_speaker: string | null;
  cues: TranslationCue[];
  candidates: TranslationCandidate[];
  skipped: { span: Span; reason: string }[];
  limitations: string[];
}

export interface PreviewResult extends DecisionMetadata {
  source_id: string;
  /**
   * The input's own status: `pending`, `disagreed` (also immediate_false) or
   * `revoked`. The back end refuses `agreed`. Show this status, never "pending".
   */
  status: Exclude<InputStatus, 'agreed'>;
  partition: Partition;
  kind: Kind;
  hypothetical: true;
  effects: ParameterEffect[];
  translator_effects: TranslatorEffect[];
  observed_terms: number;
  translation: Translation;
  interpretation?: Interpretation;
}

/**
 * Result of a review or a revoke (api.md: the same decision shape as a submit
 * with `exclamation`). `effects` are the formal, committed ones (they carry a
 * revision). A repeated identical judgement is a no-op: empty effects, no new
 * event, and none of `observed_terms` / `interpretation` / `restored_fit`.
 * `confirm(false)` on an `agreed` input returns reversal effects
 * (`action: 'revoke'`) while the status becomes `disagreed`.
 */
export interface ReviewResult extends DecisionMetadata {
  source_id: string;
  status: InputStatus;
  partition?: Partition;
  effects: ParameterEffect[];
  translator_effects: TranslatorEffect[];
  /** Only on a fresh approval or a restore. */
  observed_terms?: number;
  interpretation?: Interpretation;
  /** true: an earlier frozen fit was restored, nothing was re-translated or counted twice. */
  restored_fit?: boolean;
}

export interface ParameterState {
  value: number;
  support: number;
  /** false = no evidence yet. Show "尚无证据"; never draw it as a measured neutral. */
  observed: boolean;
}
export type PartitionState = Record<ParameterId, ParameterState>;
export type ModelState = Record<Partition, PartitionState>;

export type RankResult =
  | { status: 'abstain'; reason: string; ranked: [] }
  | {
      status: 'provisional';
      basis: string;
      not_a_probability: true;
      used_parameters: string[];
      ranked: { id: string; alignment_score: number }[];
    };

// ---- inputs ----------------------------------------------------------------------

/** Metadata of one input (api.md `input_list` / `input_page` / `input_get`). */
export interface InputRecord {
  source_id: string;
  partition: Partition;
  kind: Kind;
  self_speaker: string | null;
  status: InputStatus;
  source_ref: string | null;
  created_at: string;
  reviewed_at: string | null;
  /** "Is it true (right now)" at input time. An `exclamation` forces it true. */
  immediate: boolean;
  /** The second judgement inside the brain view; null = not yet made. */
  confirm: boolean | null;
  /**
   * The historical submit flag "strongly asserted": the back end set BOTH
   * judgements true at submit. It does not keep forcing them: a later manual
   * review or revoke can change `confirm`/`status`; `confirmed_by` and `reason` say how.
   */
  exclamation: boolean;
  confirmed_by: ConfirmedBy | null;
  /** Set when `status` is `disagreed` or `revoked`. */
  reason: InputReason | null;
  /**
   * The first 80 code points of the ORIGINAL text, raw (no ellipsis, may hold
   * line breaks and NUL). Not a summary and not sanitised: render as plain text.
   */
  excerpt: string;
  /** Code points of the whole text. */
  char_count: number;
  /** UTC time of the last edit (F6); null until the input was edited. */
  edited_at: string | null;
  /**
   * Model-reset metadata (api.md, optional on a back end that predates it).
   * `false` on an `agreed` input = still approved (vocabulary, corrections and
   * memories keep it) but NOT part of the current personalised model; only an
   * explicit `confirm(true)` enlists it again. Never show it as "training".
   */
  model_active?: boolean;
  /** The model epoch the input's contribution belongs to. */
  model_epoch?: number;
}

/** An input with its original text (api.md `input_get`). */
export interface InputDetail extends InputRecord {
  text: string;
}

/** Training rule (D55): both judgements true. An `exclamation` sets both true itself. */
export function isTrainable(r: Pick<InputRecord, 'immediate' | 'confirm' | 'status' | 'model_active'>): boolean {
  return r.status === 'agreed' && r.immediate && r.confirm === true && r.model_active !== false;
}

// ---- requests --------------------------------------------------------------------

export interface SubmitRequest {
  text: string;
  partition: Partition;
  /** Default `diary`. */
  kind?: Kind;
  /** Required for `chat`, exact match to the speaker name in the `name: text` lines. */
  self_speaker?: string;
  /** Display file name of a chosen .txt/.md; never a path. */
  source_ref?: string;
  /** "Is it true (right now)". Send it explicitly; false saves the text without training. */
  immediate: boolean;
  /**
   * The user strongly asserts the idea is their own. Independent of
   * `immediate`: the back end sets BOTH judgements true itself (also when
   * `immediate` is false), skips the second confirmation and trains at once.
   * Never infer it from the text. Needs `two_judgements` on the real back end.
   */
  exclamation?: boolean;
}

/**
 * `submit` result. Status is `pending` (immediate only), `disagreed`
 * (`immediate_false`) or, after an `exclamation`, `agreed` with
 * `confirmed_by: 'exclamation'` and the FORMAL `effects` (with revisions): show
 * them as they are, do not call `preview` or `confirm` afterwards.
 */
export interface SubmitResult extends DecisionMetadata {
  source_id: string;
  status: InputStatus;
  partition: Partition;
  effects?: ParameterEffect[];
  translator_effects?: TranslatorEffect[];
  observed_terms?: number;
  interpretation?: Interpretation;
  restored_fit?: boolean;
}

export interface InputListQuery {
  partition?: Partition;
  status?: InputStatus;
  /** 1–100, api.md. */
  limit?: number;
}

/** `input_page` (api.md): same filters as `inputList`, plus a cursor. */
export interface InputPageQuery extends InputListQuery {
  /** Exactly the `next_cursor` of the previous page, with the same filters. Never build one. */
  cursor?: string | null;
}

/**
 * One bounded page, newest first. `total` counts every matching input, not the
 * rest. `next_cursor` is null on the last page. `revision` moves whenever an
 * input changes (submit, changed review, revoke; in the mock also edit/delete);
 * a cursor from an older revision fails with STALE_CURSOR: throw the pages
 * you hold away and ask for page 1 again.
 */
export interface InputPage {
  items: InputRecord[];
  total: number;
  next_cursor: string | null;
  revision: number;
}

/** F6 `input_edit`. Refused while the input is `agreed` (revoke it first). Never trains; `confirm` is reset to null. */
export interface InputEditRequest {
  text: string;
  /** Re-declared with every edit; the second judgement is reset to null. */
  immediate: boolean;
  kind?: Kind;
  self_speaker?: string;
}

// ---- errors ----------------------------------------------------------------------

/** Codes of api.md (incl. `STALE_CURSOR`), plus two that only the front end produces. */
export type BackendErrorCode =
  | 'INVALID_REQUEST'
  | 'UNSUPPORTED_VERSION'
  | 'METHOD_NOT_FOUND'
  | 'INVALID_ARGUMENT'
  /** An `inputPage` cursor is out of date: discard the pages and ask for page 1 again. */
  | 'STALE_CURSOR'
  | 'NOT_FOUND'
  | 'MODEL_UNAVAILABLE'
  | 'STORAGE_ERROR'
  | 'INTERNAL_ERROR'
  /** No backend is connected (the default in a product build). */
  | 'UNAVAILABLE'
  /** Connected, but that backend does not offer this method (yet). */
  | 'UNSUPPORTED';

export class BackendError extends Error {
  readonly code: BackendErrorCode;
  constructor(code: BackendErrorCode, message: string) {
    super(message);
    this.name = 'BackendError';
    this.code = code;
  }
}

// ---- the adapter -----------------------------------------------------------------

/** Names of the operations, used for `capabilities`. */
export type AdapterMethod =
  | 'submit'
  | 'preview'
  | 'confirm'
  | 'revoke'
  | 'inputList'
  | 'inputPage'
  | 'inputGet'
  | 'inputEdit'
  | 'inputDelete'
  | 'state'
  | 'effects'
  | 'rank';

export interface AdapterInfo {
  /** `mock`: in-memory demonstration, never trains a model. `remote`: a real backend. `unavailable`: none. */
  kind: 'mock' | 'remote' | 'unavailable';
  /** Human-readable, shown in the UI banner. */
  label: string;
  /** True only for a backend that really fits a model. The mock is always false. */
  trains: boolean;
}

/**
 * Everything the UI may ask of the model. UI code imports this interface and
 * `getAdapter()`, never a transport. Every method rejects with `BackendError`.
 */
export interface BrainAdapter {
  readonly info: AdapterInfo;
  /** Methods this backend really offers; the UI greys out the rest. */
  capabilities(): Promise<ReadonlySet<AdapterMethod>>;
  /** `health.model_epoch` of a real back end; null when it does not report one (older back end, mock, none). */
  modelEpoch(): Promise<number | null>;

  submit(req: SubmitRequest): Promise<SubmitResult>;
  /** Read-only hypothetical effects of any input that is not `agreed` (pending, disagreed, revoked). */
  preview(sourceId: string): Promise<PreviewResult>;
  /**
   * The second judgement (`confirm`). Maps to api.md `review(agree)`; needs
   * `immediate` true (an `immediate_false` input is refused, edit it first, F6).
   * Re-judging is allowed: T after `confirm_false` or after a revoke restores
   * the frozen fit; F on an `agreed` input removes it from training; the same
   * judgement again is a no-op.
   */
  confirm(sourceId: string, confirm: boolean): Promise<ReviewResult>;
  /** Withdraw an agreed input from training; history is kept. */
  revoke(sourceId: string): Promise<ReviewResult>;

  inputList(query?: InputListQuery): Promise<InputRecord[]>;
  /** One bounded page of the same rows (api.md `input_page`); STALE_CURSOR when the inputs changed. */
  inputPage(query?: InputPageQuery): Promise<InputPage>;
  inputGet(sourceId: string): Promise<InputDetail>;
  /** F6. Not offered by an older back end (capability `inputEdit`). */
  inputEdit(sourceId: string, edit: InputEditRequest): Promise<InputRecord>;
  /** F6. Any status; hard delete with history, no tombstone. */
  inputDelete(sourceId: string): Promise<void>;

  state(): Promise<ModelState>;
  effects(sourceId?: string): Promise<ParameterEffect[]>;
  rank(options: { id: string; impacts: Partial<Record<ParameterId, number>> }[]): Promise<RankResult>;
}

// ---- additions by the adapter layer (D56) ----------------------------------------------

/** Every `AdapterMethod`, for iteration (capabilities, the UI's greying-out). */
export const ADAPTER_METHODS = [
  'submit',
  'preview',
  'confirm',
  'revoke',
  'inputList',
  'inputPage',
  'inputGet',
  'inputEdit',
  'inputDelete',
  'state',
  'effects',
  'rank',
] as const satisfies readonly AdapterMethod[];

/** Every `BackendErrorCode`, for validating codes that arrive over a transport. */
export const BACKEND_ERROR_CODES = [
  'INVALID_REQUEST',
  'UNSUPPORTED_VERSION',
  'METHOD_NOT_FOUND',
  'INVALID_ARGUMENT',
  'STALE_CURSOR',
  'NOT_FOUND',
  'MODEL_UNAVAILABLE',
  'STORAGE_ERROR',
  'INTERNAL_ERROR',
  'UNAVAILABLE',
  'UNSUPPORTED',
] as const satisfies readonly BackendErrorCode[];

/**
 * Rule ids of the mock always start with this, so a mock effect can never be
 * mistaken for a real one (`rule_id.startsWith(MOCK_RULE_PREFIX)`).
 */
export const MOCK_RULE_PREFIX = 'mock.';
