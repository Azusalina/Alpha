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
import { CONFIRMED_BY_LABELS, KIND_LABELS, PARTITION_LABELS, partitionColor} from '../shared/labels';
import { WithheldNotes } from '../shared/WithheldNotes';
import { EffectsTable } from '../shared/EffectsTable';
import { HighlightedText, marksFromEffects } from '../shared/HighlightedText';
import { StatusChip } from '../shared/StatusChip';
import { RecordEditor } from './RecordEditor';
import { displayExcerpt, formatTime, tf } from './format';
import { t } from '../../i18n/lang';

interface Props {
  rec: InputRecord;
  s: InputState;
  open: boolean;
  mode: BackendMode;
  /** The row is held open although the current filter no longer matches it. */
  sticky: boolean;
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
  /** The row's status changed a moment ago: the button is held back (SETTLE_MS). */
  settling?: boolean;
}

function Action({ method, id, label, testid, onClick, tag, busy, busyText, tone = 'plain', settling }: ActionProps) {
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
  const demoTag = demo ? t('rec.demoOnly') : null;

  // ---- which effects does the body show
  const formal = cache?.formalEffects ?? null;
  const history = cache?.effects ?? null;
  const preview = rec.status !== 'agreed' ? (cache?.preview ?? null) : null;
  const historyMain = { kind: 'history' as const, effects: history ?? [], title: rec.status === 'agreed' ? (demo ? t('rec.hist.demo') : t('rec.hist.trained')) : t('rec.hist.all') };
  const formalMain = {
    kind: 'formal' as const,
    effects: formal ?? [],
    // D56: the demo mock never trains, so its heading never says 已训练
    title:
      rec.status === 'agreed'
        ? demo
          ? t('rec.formal.demo')
          : t('rec.formal.trained')
        : t('rec.formal.judged'),
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
  if (rec.status === 'pending') checkCap('confirm', t('rec.cap.confirm'));
  if (rec.status === 'agreed') checkCap('revoke', t('rec.revoke'));
  checkCap('inputDelete', t('rec.delete'));
  if (rec.status === 'disagreed') {
    checkCap('inputEdit', t('rec.edit'));
    if (rec.reason === 'confirm_false') checkCap('confirm', t('rec.changeToT'));
  }
  if (rec.status === 'revoked') checkCap('confirm', t('rec.agreeAgain'));

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
        onClick={() => {
          inputStore.expand(id);
          inputStore.replay(id);
        }}
      >
        <span className="rec__mark" aria-hidden="true" />
        <span className="rec__excerpt" data-testid="record-excerpt">
          {excerpt}
        </span>
        <span className="rec__meta">
          <StatusChip status={rec.status} reason={rec.reason} />
          <span className="rec__j" data-testid="record-immediate">
            <b>{t('rec.immediate')}</b> {tf(rec.immediate)}
          </span>
          <span className="rec__j" data-testid="record-confirm">
            <b>{t('rec.second')}</b> {tf(rec.confirm)}
          </span>
          {rec.exclamation && (
            <span className="rec__bang" data-testid="record-exclamation">
              !<span className="rec__sr">{t('entry.assert')}</span>
            </span>
          )}
          <span className="rec__when">
            <span data-testid="record-partition">{PARTITION_LABELS[rec.partition]}</span> · {formatTime(rec.created_at)} ·{' '}
            <span data-testid="record-chars">{rec.char_count}</span> {t('rec.chars')}
          </span>
        </span>
      </button>

      {open && (
        <div className="rec__body" id={`rec-body-${id}`} data-testid="record-body">
          <p className="rec__facts" data-testid="record-facts">
            {KIND_LABELS[rec.kind]}
            {rec.self_speaker ? ` · ${t('rec.me')}: ${rec.self_speaker}` : ''}
            {rec.source_ref ? ` · ${rec.source_ref}` : ''}
            {rec.confirmed_by ? ` · ${CONFIRMED_BY_LABELS[rec.confirmed_by]}` : ''}
            {rec.edited_at ? ` · ${t('rec.edited', { when: formatTime(rec.edited_at) })}` : ''}
          </p>

          {editing ? (
            text === null ? (
              <p className="rec__quiet">{t('rec.loadingText')}</p>
            ) : (
              <RecordEditor rec={rec} original={text} demoTag={demoTag} />
            )
          ) : (
            <>
              <h4 className="rec__h">{t('result.text')}</h4>
              {text === null ? (
                <p className="rec__quiet" data-testid="record-text-loading">
                  {inputStore.isBusy(id, 'detail') ? t('rec.loadingText') : t('rec.textNotLoaded')}
                </p>
              ) : (
                <HighlightedText text={text} marks={marksFromEffects(primary)} activeId={activeEffect} data-testid="record-text" />
              )}

              {(loadingMain || main) && (
                <>
                  <h4 className="rec__h" data-testid="record-effects-title">
                    {main ? main.title : t('rec.effects')}
                  </h4>
                  {loadingMain ? (
                    <p className="rec__quiet">{t('rec.loadingEffects')}</p>
                  ) : main && main.effects.length === 0 && main.kind === 'history' && rec.status !== 'agreed' ? (
                    <p className="rec__quiet" data-testid="record-no-history">
                      {t('rec.noEffects')}
                    </p>
                  ) : main && main.effects.length === 0 && rec.status !== 'agreed' ? (
                    <p className="rec__quiet" data-testid="record-no-change">
                      {t('rec.noChange')}
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
                    {t('action.preview')} · {rec.status === 'disagreed' && rec.reason === 'immediate_false' ? t('rec.preview.ifAgreed') : t('rec.preview.ifTrue')}
                  </h4>
                  {loadingPreview ? (
                    <p className="rec__quiet">{t('rec.loadingPreview')}</p>
                  ) : (
                    preview && (
                      <>
                        <EffectsTable
                          effects={preview.effects}
                          activeId={preview.effects === primary ? activeEffect : null}
                          onActiveChange={preview.effects === primary ? setActiveEffect : undefined}
                        />
                        <WithheldNotes interpretation={preview.interpretation} />
                      </>
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
                {t('rec.gotIt')}
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
                    label={t('rec.act.T')}
                    busyText={t('rec.busy.agreeing')}
                    busy={busyConfirm}
                    settling={settling}
                    tone="primary"
                    testid="act-confirm-true"
                    onClick={() => void inputStore.confirm(id, true)}
                  />
                  <Action
                    method="confirm"
                    id={id}
                    label={t('rec.act.F')}
                    busyText={t('rec.busy.working')}
                    busy={busyConfirm}
                    settling={settling}
                    testid="act-confirm-false"
                    onClick={() => void inputStore.confirm(id, false)}
                  />
                </>
              )}
              {rec.status === 'agreed' && rec.model_active === false && (
                <Action
                  method="confirm"
                  id={id}
                  label={t('rec.act.enlist')}
                  busyText={t('rec.busy.enlisting')}
                  busy={busyConfirm}
                  settling={settling}
                  tone="primary"
                  testid="act-reenlist"
                  onClick={() => void inputStore.confirm(id, true)}
                />
              )}
              {rec.status === 'agreed' && (
                <Action
                  method="revoke"
                  id={id}
                  label={t('rec.revoke')}
                  busyText={t('rec.busy.revoking')}
                  busy={busyRevoke}
                  settling={settling}
                  testid="act-revoke"
                  onClick={() => void inputStore.revoke(id)}
                />
              )}
              {rec.status === 'disagreed' && rec.reason === 'confirm_false' && (
                <Action
                  method="confirm"
                  id={id}
                  label={t('rec.changeToT')}
                  busyText={t('rec.busy.agreeing')}
                  busy={busyConfirm}
                  tone="primary"
                  testid="act-rejudge"
                  onClick={() => void inputStore.confirm(id, true)}
                />
              )}
              {rec.status === 'revoked' && (
                <Action
                  method="confirm"
                  id={id}
                  label={t('rec.agreeAgain')}
                  busyText={t('rec.busy.agreeing')}
                  busy={busyConfirm}
                  settling={settling}
                  tone="primary"
                  testid="act-reagree"
                  onClick={() => void inputStore.confirm(id, true)}
                />
              )}
              {rec.status === 'disagreed' && (
                <Action
                  method="inputEdit"
                  id={id}
                  label={t('rec.edit')}
                  tag={demoTag}
                  testid="act-edit"
                  settling={settling}
                  onClick={() => inputStore.openEditor(id)}
                />
              )}
              {confirmDelete ? (
                <span className="rec__confirm" data-testid="delete-confirm" role="group" aria-label={t('rec.delete.confirm')}>
                  <span>
                    {t('rec.delete.ask')}
                  </span>
                  <button
                    type="button"
                    className="rec__act rec__act--danger"
                    data-testid="act-delete-confirm"
                    disabled={busyRemove || mutating}
                    autoFocus
                    onClick={() => void inputStore.remove(id)}
                  >
                    {busyRemove ? t('rec.busy.deleting') : t('rec.delete.confirm')}
                  </button>
                  <button type="button" className="rec__act rec__act--plain" data-testid="act-delete-cancel" onClick={() => setConfirmDelete(false)}>
                    {t('common.cancel')}
                  </button>
                </span>
              ) : (
                <Action
                  method="inputDelete"
                  id={id}
                  label={t('rec.delete')}
                  tag={demoTag}
                  testid="act-delete"
                  settling={settling}
                  onClick={() => setConfirmDelete(true)}
                />
              )}
            </div>
          )}
        </div>
      )}
    </li>
  );
}
