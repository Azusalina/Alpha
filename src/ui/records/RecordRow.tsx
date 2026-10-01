/**
 * One past input in the list (D55): a bullet with the partition's accent, the
 * excerpt, the record's own status and its two judgements; Enter / click opens
 * it inline (one at a time) to the ORIGINAL text with the evidence marked, the
 * effects, and the actions the status allows.
 *
 * Which effects are shown (never a guess, never a stale preview):
 *  - after a judgement in this session: the review's OWN effects
 *    (`cache.formalEffects`: committed, with revisions; a reversal says
 *    已撤销). The panel never offers an identical repeated judgement (T on an
 *    agreed row, F on a disagreed one), so `cache.lastWasNoop` is not used:
 *    the store also sets it for a FIRST judgement that changed no parameter
 *    (pending -> F), where "repeated" would be wrong;
 *  - otherwise an agreed record shows its effect history, and a revoked or
 *    confirm-false one shows its history too (the store does not load that, this
 *    row asks once per status version);
 *  - a record that is not agreed also shows the PREVIEW, labelled hypothetical
 *    (no revision numbers; "预览"), and only while it is fresh: a judgement,
 *    an edit or a delete clears it in the store.
 *
 * Actions by status (brief):
 *  - pending    T 认可为真 / F 不同意
 *  - agreed     撤销 (history is kept)
 *  - disagreed  编辑, 删除; with reason confirm_false also 改判为 T
 *  - revoked    重新认可 (F4: the back end allows agreeing again; a mistaken
 *               revoke can be undone), 删除
 *
 * A status change disables the buttons for SETTLE_MS (see `settling`): the new
 * action lands in the slot of the one just clicked, and a double click must not
 * turn 认可 into 撤销.
 * An action whose adapter capability is missing is greyed out with the tooltip
 * and the visible note UNSUPPORTED_NOTE. Edit and delete exist only in the
 * mock (F6): they carry the tag 仅演示 while the demo is the back end.
 */

import { useEffect, useRef, useState } from 'react';

import { inputStore } from '../../app/inputStore';
import type { InputState } from '../../app/inputStore';
import type { AdapterMethod, InputRecord } from '../../backend';
import type { BackendMode } from '../../backend';
import { CONFIRMED_BY_LABELS, KIND_LABELS, PARTITION_LABELS, partitionColor, statusHint } from '../shared/labels';
import { EffectsTable } from '../shared/EffectsTable';
import { HighlightedText, marksFromEffects } from '../shared/HighlightedText';
import { StatusChip } from '../shared/StatusChip';
import { RecordEditor } from './RecordEditor';
import { UNSUPPORTED_NOTE, displayExcerpt, formatFull, formatTime, tf } from './format';

interface Props {
  rec: InputRecord;
  s: InputState;
  open: boolean;
  mode: BackendMode;
  /** The row is held open although the current filter no longer matches it. */
  sticky: boolean;
}

/**
 * Why a record is what it is, in one sentence, with what the user may do. In
 * demo mode (D56) nothing says the model is being trained: the mock only marks.
 */
function explain(rec: InputRecord, demo: boolean): string {
  switch (rec.status) {
    case 'pending':
      return demo
        ? '当下判断为真，等待二次确认。T：认可为真，演示里只会标记并让大脑演出一次，没有运行模型；F：不同意。'
        : '当下判断为真，等待二次确认。T：认可为真，从此参与训练，大脑会有一次演出；F：不同意，不参与训练。';
    case 'agreed':
      if (demo) {
        return rec.confirmed_by === 'exclamation'
          ? '录入时「断言为真」，两次判断都已为真。演示：只是标记为训练，没有运行模型。撤销会取消这个标记；历史保留，不会删除。'
          : '两次判断都为真。演示：只是标记为训练，没有运行模型。撤销会取消这个标记；历史保留，不会删除。';
      }
      return rec.confirmed_by === 'exclamation'
        ? '录入时「断言为真」，两次判断都已为真，已直接参与训练。撤销会把它从训练里拿掉；历史保留，不会删除。'
        : '两次判断都为真，正在参与训练。撤销会把它从训练里拿掉；历史保留，不会删除。';
    case 'disagreed':
      return rec.reason === 'confirm_false'
        ? '二次确认为否，不参与训练。可以改判为 T，或编辑、删除。'
        : '录入时判断为否，不参与训练。编辑并把「是否为真」改为是后，才能进入二次确认；或直接删除。';
    case 'revoked':
      return '曾经被认可，已被撤销；历史保留。可以重新认可，或删除。';
  }
}

/** Clicks on a row's action buttons are ignored this long after its status changes. */
export const SETTLE_MS = 600;

interface ActionProps {
  method: AdapterMethod;
  id: string;
  label: string;
  testid: string;
  onClick: () => void;
  /** Tag beside the label (仅演示). */
  tag?: string | null;
  busyText?: string;
  busy?: boolean;
  tone?: 'primary' | 'plain';
  title?: string;
  /** The row's status changed a moment ago: the button is held back (SETTLE_MS). */
  settling?: boolean;
}

function Action({ method, id, label, testid, onClick, tag, busy, busyText, tone = 'plain', title, settling }: ActionProps) {
  const supported = inputStore.can(method);
  const disabled = !supported || busy === true || settling === true || inputStore.isMutating(id);
  return (
    <button
      type="button"
      className={`rec__act rec__act--${tone}`}
      data-testid={testid}
      data-supported={supported ? 'true' : 'false'}
      data-settling={settling ? 'true' : undefined}
      disabled={disabled}
      aria-disabled={disabled}
      title={!supported ? UNSUPPORTED_NOTE : title}
      onClick={onClick}
    >
      {busy && busyText ? busyText : label}
      {tag && supported && <span className="rec__tag">{tag}</span>}
    </button>
  );
}

export function RecordRow({ rec, s, open, mode, sticky }: Props) {
  const id = rec.source_id;
  const cache = s.cache[id] ?? null;
  const editing = s.editingId === id;
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [activeEffect, setActiveEffect] = useState<string | null>(null);
  const asked = useRef<string>('');
  const demo = mode === 'demo';
  const rootRef = useRef<HTMLLIElement | null>(null);

  // a new status version: a half-made delete confirmation does not carry over
  const version = `${rec.status}|${rec.reason ?? ''}|${rec.reviewed_at ?? ''}|${rec.edited_at ?? ''}`;
  useEffect(() => setConfirmDelete(false), [version, open]);

  // The actions of a row sit in fixed slots, and a new status brings a new
  // action into the slot the user just clicked (T 认可为真 -> 撤销, 改判为 T ->
  // 撤销, F -> 编辑). A double click would confirm and then undo. So for
  // SETTLE_MS after a status change (not on first mount) the buttons are
  // disabled: the second click lands on a disabled button and does nothing.
  const [settling, setSettling] = useState(false);
  const lastStatus = useRef(version);
  useEffect(() => {
    if (lastStatus.current === version) return;
    lastStatus.current = version;
    setSettling(true);
    const t = window.setTimeout(() => setSettling(false), SETTLE_MS);
    return () => window.clearTimeout(t);
  }, [version]);

  // A row opened near the bottom of the list brings its actions into view:
  // the list's own scroll box is moved by hand (never scrollIntoView, which can
  // also shift clipped ancestors), by no more than keeps the row's head visible.
  useEffect(() => {
    if (!open) return;
    const t = window.setTimeout(() => {
      const box = rootRef.current?.closest<HTMLElement>('.records-panel__scroll');
      const acts = rootRef.current?.querySelector<HTMLElement>('[data-testid="record-actions"]');
      const head = rootRef.current?.querySelector<HTMLElement>('.rec__head');
      if (!box || !acts || !head) return;
      const bottom = acts.getBoundingClientRect().bottom;
      const edge = box.getBoundingClientRect().bottom - 8;
      if (bottom <= edge) return;
      const headRoom = head.getBoundingClientRect().top - box.getBoundingClientRect().top;
      box.scrollTop += Math.max(0, Math.min(bottom - edge, headRoom));
    }, 80);
    return () => window.clearTimeout(t);
  }, [open, cache?.detail?.text]);

  // a revoked / confirm-false record shows its history; the store loads it only for an agreed one
  const wantsHistory = rec.status === 'revoked' || (rec.status === 'disagreed' && rec.reason === 'confirm_false');
  const errored = s.error?.action === 'effects' && s.error.id === id;
  useEffect(() => {
    if (!open || !wantsHistory || errored) return;
    if (cache?.effects != null || inputStore.isBusy(id, 'effects')) return;
    const key = `${id}|${version}`;
    if (asked.current === key) return;
    asked.current = key;
    void inputStore.loadEffects(id);
  }, [open, wantsHistory, errored, cache?.effects, id, version]);

  const mutating = inputStore.isMutating(id);
  const busyConfirm = s.busy.records[id]?.includes('confirm') ?? false;
  const busyRevoke = s.busy.records[id]?.includes('revoke') ?? false;
  const busyRemove = s.busy.records[id]?.includes('remove') ?? false;
  const rowError = s.error && s.error.id === id ? s.error : null;
  const demoTag = demo ? '仅演示' : null;

  // ---- which effects does the body show
  const formal = cache?.formalEffects ?? null;
  const history = cache?.effects ?? null;
  const preview = rec.status !== 'agreed' ? (cache?.preview ?? null) : null;
  const historyMain = { kind: 'history' as const, effects: history ?? [], title: rec.status === 'agreed' ? (demo ? '演示效应（历史）' : '训练效应（历史）') : '历史效应（含撤销）' };
  const formalMain = {
    kind: 'formal' as const,
    effects: formal ?? [],
    // D56: the demo mock never trains, so its heading never says 已训练
    title:
      rec.status === 'agreed'
        ? demo
          ? '本次写入的效应（演示 · 带修订号 · 未运行模型）'
          : '本次写入的效应（已训练 · 带修订号）'
        : '本次判断写入的效应（带修订号）',
  };
  // a revoked / confirm-false record: the history is a superset of the reversal just made (its last revisions)
  const main: typeof historyMain | typeof formalMain | null =
    wantsHistory && history !== null && history.length > 0
      ? historyMain
      : formal !== null
        ? formalMain
        : history !== null && (rec.status === 'agreed' || wantsHistory)
          ? historyMain
          : null;
  const primary = main && main.effects.length > 0 ? main.effects : (preview?.effects ?? []);
  const loadingMain = !main && (rec.status === 'agreed' || wantsHistory) && (s.busy.records[id]?.includes('effects') ?? false);
  const loadingPreview = rec.status !== 'agreed' && !preview && (s.busy.records[id]?.includes('preview') ?? false);
  const text = cache?.detail?.text ?? null;

  const excerpt = displayExcerpt(rec.excerpt, rec.char_count);
  const unsupported: string[] = [];
  const checkCap = (m: AdapterMethod, name: string) => {
    if (!inputStore.can(m)) unsupported.push(name);
  };
  if (rec.status === 'pending') checkCap('confirm', '认可 / 不同意');
  if (rec.status === 'agreed') checkCap('revoke', '撤销');
  checkCap('inputDelete', '删除');
  if (rec.status === 'disagreed') {
    checkCap('inputEdit', '编辑');
    if (rec.reason === 'confirm_false') checkCap('confirm', '改判为 T');
  }
  if (rec.status === 'revoked') checkCap('confirm', '重新认可');

  return (
    <li
      ref={rootRef}
      className={`rec rec--${rec.status}${open ? ' is-open' : ''}${sticky ? ' is-sticky' : ''}`}
      data-testid="record-row"
      data-id={id}
      data-status={rec.status}
      data-partition={rec.partition}
      data-reason={rec.reason ?? ''}
      data-immediate={String(rec.immediate)}
      data-confirm={rec.confirm === null ? 'null' : String(rec.confirm)}
      data-exclamation={String(rec.exclamation)}
      style={{ ['--rec-accent' as string]: partitionColor(rec.partition) }}
    >
      <button
        type="button"
        className="rec__head"
        data-testid="record-head"
        aria-expanded={open}
        aria-controls={`rec-body-${id}`}
        ref={(el) => inputStore.registerAnchor(id, el)}
        onClick={() => inputStore.expand(id)}
      >
        <span className="rec__mark" aria-hidden="true" />
        <span className="rec__excerpt" data-testid="record-excerpt">
          {excerpt}
        </span>
        <span className="rec__meta">
          <StatusChip status={rec.status} reason={rec.reason} />
          <span className="rec__j" data-testid="record-immediate" title="当下判断：录入时「是否为真」">
            <b>当下</b> {tf(rec.immediate)}
          </span>
          <span className="rec__j" data-testid="record-confirm" title="二次判断：在脑内确认，— 表示还没做">
            <b>二次</b> {tf(rec.confirm)}
          </span>
          {rec.exclamation && (
            <span className="rec__bang" data-testid="record-exclamation" title="录入时断言为真：两次判断由此同时为真">
              !<span className="rec__sr">断言为真</span>
            </span>
          )}
          <span className="rec__when" title={`创建 ${formatFull(rec.created_at)}`}>
            <span data-testid="record-partition">{PARTITION_LABELS[rec.partition]}</span> · {formatTime(rec.created_at)} ·{' '}
            <span data-testid="record-chars">{rec.char_count}</span> 字
          </span>
        </span>
      </button>

      {open && (
        <div className="rec__body" id={`rec-body-${id}`} data-testid="record-body">
          <p className="rec__facts" data-testid="record-facts">
            {KIND_LABELS[rec.kind]}
            {rec.self_speaker ? ` · 我：${rec.self_speaker}` : ''}
            {rec.source_ref ? ` · ${rec.source_ref}` : ''}
            {rec.confirmed_by ? ` · ${CONFIRMED_BY_LABELS[rec.confirmed_by]}` : ''}
            {rec.edited_at ? ` · 已编辑 ${formatTime(rec.edited_at)}` : ''}
          </p>
          <p className="rec__explain" data-testid="record-explain" title={statusHint(rec.status, demo)}>
            {explain(rec, demo)}
          </p>

          {editing ? (
            text === null ? (
              <p className="rec__quiet">读取原文…</p>
            ) : (
              <RecordEditor rec={rec} original={text} demoTag={demoTag} />
            )
          ) : (
            <>
              <h4 className="rec__h">原文</h4>
              {text === null ? (
                <p className="rec__quiet" data-testid="record-text-loading">
                  {inputStore.isBusy(id, 'detail') ? '读取原文…' : '原文尚未读取'}
                </p>
              ) : (
                <HighlightedText text={text} marks={marksFromEffects(primary)} activeId={activeEffect} data-testid="record-text" />
              )}

              {(loadingMain || main) && (
                <>
                  <h4 className="rec__h" data-testid="record-effects-title">
                    {main ? main.title : '效应'}
                  </h4>
                  {loadingMain ? (
                    <p className="rec__quiet">读取效应…</p>
                  ) : main && main.effects.length === 0 && main.kind === 'history' && rec.status !== 'agreed' ? (
                    <p className="rec__quiet" data-testid="record-no-history">
                      还没有写入过任何效应。
                    </p>
                  ) : main && main.effects.length === 0 && rec.status !== 'agreed' ? (
                    <p className="rec__quiet" data-testid="record-no-change">
                      本次判断没有改变任何参数。
                    </p>
                  ) : (
                    main && (
                      <EffectsTable
                        effects={main.effects}
                        activeId={main.effects === primary ? activeEffect : null}
                        onActiveChange={main.effects === primary ? setActiveEffect : undefined}
                      />
                    )
                  )}
                </>
              )}
              {(preview || loadingPreview) && (
                <>
                  <h4 className="rec__h" data-testid="record-preview-title">
                    预览 · {rec.status === 'disagreed' && rec.reason === 'immediate_false' ? '若它被认可（假设，不会训练）' : '若认可为真（假设，尚未写入）'}
                  </h4>
                  {loadingPreview ? (
                    <p className="rec__quiet">读取预览…</p>
                  ) : (
                    preview && (
                      <EffectsTable
                        effects={preview.effects}
                        activeId={preview.effects === primary ? activeEffect : null}
                        onActiveChange={preview.effects === primary ? setActiveEffect : undefined}
                      />
                    )
                  )}
                </>
              )}
            </>
          )}

          {rowError && (
            <p className="rec__error" role="alert" data-testid="record-error">
              <code>{rowError.code}</code> {rowError.message}{' '}
              <button type="button" onClick={() => inputStore.dismissError()}>
                知道了
              </button>
            </p>
          )}

          {!editing && (
            <div className="rec__acts" data-testid="record-actions">
              {rec.status === 'pending' && (
                <>
                  <Action
                    method="confirm"
                    id={id}
                    label="T 认可为真"
                    busyText="认可中…"
                    busy={busyConfirm}
                    settling={settling}
                    tone="primary"
                    testid="act-confirm-true"
                    title={demo ? '二次判断为真：标记为训练，大脑演出一次（演示，没有运行模型）' : '二次判断为真：训练模型，大脑演出一次'}
                    onClick={() => void inputStore.confirm(id, true)}
                  />
                  <Action
                    method="confirm"
                    id={id}
                    label="F 不同意"
                    busyText="处理中…"
                    busy={busyConfirm}
                    settling={settling}
                    testid="act-confirm-false"
                    title={demo ? '二次判断为否：不标记为训练，可编辑或删除' : '二次判断为否：不训练，可编辑或删除'}
                    onClick={() => void inputStore.confirm(id, false)}
                  />
                </>
              )}
              {rec.status === 'agreed' && (
                <Action
                  method="revoke"
                  id={id}
                  label="撤销"
                  busyText="撤销中…"
                  busy={busyRevoke}
                  settling={settling}
                  testid="act-revoke"
                  title={demo ? '取消演示里的训练标记；历史保留' : '把它从训练里拿掉；历史保留'}
                  onClick={() => void inputStore.revoke(id)}
                />
              )}
              {rec.status === 'disagreed' && rec.reason === 'confirm_false' && (
                <Action
                  method="confirm"
                  id={id}
                  label="改判为 T"
                  busyText="认可中…"
                  busy={busyConfirm}
                  tone="primary"
                  testid="act-rejudge"
                  title={demo ? '二次判断改为真：标记为训练（演示，没有运行模型）' : '二次判断改为真：训练模型'}
                  onClick={() => void inputStore.confirm(id, true)}
                />
              )}
              {rec.status === 'revoked' && (
                <Action
                  method="confirm"
                  id={id}
                  label="重新认可"
                  busyText="认可中…"
                  busy={busyConfirm}
                  settling={settling}
                  tone="primary"
                  testid="act-reagree"
                  title={demo ? '二次判断再次为真：重新标记为训练（演示，没有运行模型）' : '二次判断再次为真：重新参与训练；之前冻结的拟合会恢复'}
                  onClick={() => void inputStore.confirm(id, true)}
                />
              )}
              {rec.status === 'disagreed' && (
                <Action
                  method="inputEdit"
                  id={id}
                  label="编辑"
                  tag={demoTag}
                  testid="act-edit"
                  settling={settling}
                  onClick={() => inputStore.openEditor(id)}
                />
              )}
              {confirmDelete ? (
                <span className="rec__confirm" data-testid="delete-confirm" role="group" aria-label="确认删除">
                  <span>
                    确认删除？<em>连同全部历史一起删除{rec.status === 'agreed' ? '，它对模型的贡献也会撤回' : ''}</em>
                    {mode === 'demo' && <em>演示模式下删除后不可恢复</em>}
                  </span>
                  <button
                    type="button"
                    className="rec__act rec__act--danger"
                    data-testid="act-delete-confirm"
                    disabled={busyRemove || mutating}
                    autoFocus
                    onClick={() => void inputStore.remove(id)}
                  >
                    {busyRemove ? '删除中…' : '确认删除'}
                  </button>
                  <button type="button" className="rec__act rec__act--plain" data-testid="act-delete-cancel" onClick={() => setConfirmDelete(false)}>
                    取消
                  </button>
                </span>
              ) : (
                <Action
                  method="inputDelete"
                  id={id}
                  label="删除"
                  tag={demoTag}
                  testid="act-delete"
                  settling={settling}
                  onClick={() => setConfirmDelete(true)}
                />
              )}
            </div>
          )}
          {!editing && unsupported.length > 0 && (
            <p className="rec__unsupported" data-testid="record-unsupported" role="note">
              {unsupported.join('、')}：{UNSUPPORTED_NOTE}
            </p>
          )}
          {sticky && <p className="rec__quiet">这一条已不在当前筛选里，关闭后会消失。</p>}
        </div>
      )}
    </li>
  );
}
