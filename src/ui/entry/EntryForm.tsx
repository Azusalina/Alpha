/**
 * The entry form (D54, D55): what the user writes into the human destination's
 * upper-right area.
 *
 *  - 状态 (partition): 理性 / 感性 / 癫狂, a radio group, each with its own accent
 *    mark (D57). Never preselected. 癫狂 is the user's own name for a situational
 *    state, not a diagnosis, and the form says so on its face.
 *  - 类型 (kind): 日记 / 聊天 / 哲学. For 聊天 the speaker field is required
 *    (`validateEntry` mirrors the back end, so a warning here predicts what the
 *    back end will do).
 *  - the text: multi-line, Enter is a line break, Ctrl/Cmd+Enter writes. A `.txt`
 *    / `.md` can be chosen or dropped (strict UTF-8, `readTextFile`); the file's
 *    name becomes `source_ref` until the text is edited.
 *  - two judgements. "是否为真（当下）" is the immediate one, UNCHECKED by default, so
 *    nothing trains unless the user says so. "断言为真" is independent of it: the
 *    back end then sets BOTH judgements true by itself, skips the second
 *    confirmation and trains at once, so ticking it shows the first box as
 *    checked and locked, and unticking it gives back the user's own choice.
 *
 * Without a back end (mode `unconnected`) the form can still be drafted in, but
 * 写入 is disabled and says why. Everything goes through `inputStore`; this file
 * never touches an adapter.
 */

import { useDeferredValue, useMemo, useRef, useState } from 'react';
import type { ChangeEvent, DragEvent, KeyboardEvent } from 'react';

import {
  MAX_INPUT_CHARS,
  TextFileError,
  codePointLength,
  effectiveJudgement,
  readTextFile,
  useBackend,
  validateEntry,
} from '../../backend';
import type { Kind, Partition, SubmitRequest } from '../../backend';
import { inputStore, useInputs } from '../../app/inputStore';
import { KIND_LABELS, PARTITION_LABELS, partitionColor } from '../shared/labels';
import { draftStore, shownImmediate, useDraft } from './draft';
import { EntryError } from './EntryError';

const PARTITION_OPTIONS: Partition[] = ['rational', 'emotional', 'crazy'];
const KIND_OPTIONS: Kind[] = ['diary', 'chat', 'philosophy'];

export const CRAZY_NOTE = '癫狂：用户命名的情境状态，不是诊断';
export const EXCLAMATION_NOTE = '仅当你强烈认同这是自己的想法：跳过大脑内的二次确认，直接用于训练';

/** A drag that carries files (not selected text). */
const hasFiles = (e: DragEvent): boolean => Array.from(e.dataTransfer?.types ?? []).includes('Files');

export function EntryForm() {
  const draft = useDraft();
  const backend = useBackend();
  const inputs = useInputs();
  const [fileError, setFileError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const [undo, setUndo] = useState<{ text: string; source_ref: string | null; file_chars: number | null } | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  // validating a megabyte on every key must not hold typing back
  const deferredText = useDeferredValue(draft.text);
  const validation = useMemo(
    () =>
      validateEntry({
        text: deferredText,
        partition: draft.partition ?? ('' as Partition),
        kind: draft.kind,
        self_speaker: draft.self_speaker,
      }),
    [deferredText, draft.partition, draft.kind, draft.self_speaker],
  );

  const chars = useMemo(() => codePointLength(draft.text), [draft.text]);
  const unconnected = backend.mode === 'unconnected';
  const busy = inputs.busy.submit;
  const blocked = validation.errors.length > 0 || deferredText !== draft.text;
  const canSubmit = !unconnected && !busy && !blocked;
  const immediateShown = shownImmediate(draft);

  const submit = async (): Promise<void> => {
    const d = draftStore.get();
    if (unconnected || inputStore.get().busy.submit) return;
    // judged again on the exact current text, not the deferred one
    const v = validateEntry({
      text: d.text,
      partition: d.partition ?? ('' as Partition),
      kind: d.kind,
      self_speaker: d.self_speaker,
    });
    if (v.errors.length > 0 || !d.partition) return;
    const req: SubmitRequest = {
      text: d.text,
      partition: d.partition,
      kind: d.kind,
      // what the form shows is what is sent: an exclamation implies the first judgement
      immediate: effectiveJudgement(d.immediate, d.exclamation).immediate,
      exclamation: d.exclamation,
    };
    if (d.kind === 'chat') req.self_speaker = d.self_speaker;
    if (d.source_ref) req.source_ref = d.source_ref;
    const out = await inputStore.submitInput(req);
    if (out) {
      draftStore.clearContent();
      setUndo(null);
      setFileError(null);
    }
  };

  const loadFile = async (file: File): Promise<void> => {
    setFileError(null);
    try {
      const r = await readTextFile(file);
      const cur = draftStore.get();
      // replacing a draft must not lose it silently
      setUndo(cur.text === '' ? null : { text: cur.text, source_ref: cur.source_ref, file_chars: cur.file_chars });
      draftStore.set({ text: r.text, source_ref: r.source_ref, file_chars: codePointLength(r.text) });
    } catch (e) {
      const name = file.name.split(/[\\/]/).pop() ?? file.name;
      setFileError(`${name}：${e instanceof TextFileError ? e.message : '文件读取失败'}`);
    }
  };

  const onFileChosen = (e: ChangeEvent<HTMLInputElement>): void => {
    const f = e.target.files?.[0];
    e.target.value = ''; // the same file can be chosen again
    if (f) void loadFile(f);
  };

  const onDrop = (e: DragEvent): void => {
    setDragging(false);
    if (!hasFiles(e)) return;
    e.preventDefault();
    const f = e.dataTransfer.files[0];
    if (f) void loadFile(f);
  };

  const onKeyDown = (e: KeyboardEvent<HTMLElement>): void => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey) && !e.nativeEvent.isComposing) {
      e.preventDefault();
      void submit();
      return;
    }
    // Escape in the middle of writing must not throw the draft's place away by leaving the
    // destination: the first press only leaves the field, the next one is the ordinary Escape
    if (e.key === 'Escape' && (draft.text !== '' || draft.self_speaker !== '') && e.target !== e.currentTarget) {
      e.stopPropagation();
      (e.target as HTMLElement).blur();
    }
  };

  const reason = unconnected ? '后端未连接：先进入演示模式才能写入（现在只能起草）' : null;

  return (
    <form
      className="entry-form"
      data-testid="entry-form"
      aria-label="写入一段话"
      noValidate
      onSubmit={(e) => {
        e.preventDefault();
        void submit();
      }}
      onKeyDown={onKeyDown}
    >
      <div className="entry-form__scroll">
        <div className="entry-field">
          <span className="entry-field__label" id="entry-partition-label">
            状态
          </span>
          <div
            className="entry-choices"
            role="radiogroup"
            aria-labelledby="entry-partition-label"
            data-testid="entry-partition"
          >
            {PARTITION_OPTIONS.map((p) => (
              <label key={p} className="entry-choice" style={{ ['--c' as string]: partitionColor(p) }}>
                <input
                  type="radio"
                  name="entry-partition"
                  value={p}
                  checked={draft.partition === p}
                  data-testid={`entry-partition-${p}`}
                  onChange={() => draftStore.set({ partition: p })}
                />
                <span>{PARTITION_LABELS[p]}</span>
              </label>
            ))}
          </div>
          <span className="entry-note" data-testid="entry-crazy-note">
            {CRAZY_NOTE}
          </span>
        </div>

        <div className="entry-field">
          <span className="entry-field__label" id="entry-kind-label">
            类型
          </span>
          <div className="entry-choices" role="radiogroup" aria-labelledby="entry-kind-label" data-testid="entry-kind">
            {KIND_OPTIONS.map((k) => (
              <label key={k} className="entry-choice entry-choice--plain">
                <input
                  type="radio"
                  name="entry-kind"
                  value={k}
                  checked={draft.kind === k}
                  data-testid={`entry-kind-${k}`}
                  onChange={() => draftStore.set({ kind: k })}
                />
                <span>{KIND_LABELS[k]}</span>
              </label>
            ))}
          </div>
        </div>

        {draft.kind === 'chat' && (
          <div className="entry-field entry-field--speaker">
            <label className="entry-field__label" htmlFor="entry-speaker">
              我的名字
            </label>
            <div className="entry-speaker">
              <input
                id="entry-speaker"
                type="text"
                autoComplete="off"
                spellCheck={false}
                required
                aria-required="true"
                aria-describedby="entry-speaker-help"
                data-testid="entry-speaker"
                placeholder="聊天里代表我的名字"
                value={draft.self_speaker}
                onChange={(e) => draftStore.set({ self_speaker: e.target.value })}
              />
              <small id="entry-speaker-help">每行「姓名: 内容」，只分析这位发言者</small>
            </div>
          </div>
        )}

        <div
          className={`entry-text${dragging ? ' is-dragging' : ''}`}
          onDragOver={(e) => {
            if (!hasFiles(e)) return;
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
        >
          <div className="entry-text__head">
            <label htmlFor="alpha-input" className="entry-field__label">
              内容
            </label>
            <span className={`entry-count${chars > MAX_INPUT_CHARS ? ' is-over' : ''}`} data-testid="entry-count">
              {chars.toLocaleString('en-US')} / {MAX_INPUT_CHARS.toLocaleString('en-US')}
            </span>
          </div>
          <textarea
            id="alpha-input"
            data-testid="human-input"
            autoComplete="off"
            spellCheck={false}
            rows={4}
            placeholder="写下一段话…（Ctrl/⌘ + Enter 写入）"
            value={draft.text}
            onChange={(e) => draftStore.set({ text: e.target.value, source_ref: null, file_chars: null })}
          />
          <div className="entry-file">
            <input
              ref={fileRef}
              type="file"
              accept=".txt,.md,text/plain,text/markdown"
              className="entry-file__input"
              tabIndex={-1}
              aria-hidden="true"
              data-testid="entry-file-input"
              onChange={onFileChosen}
            />
            <button
              type="button"
              className="entry-link"
              data-testid="entry-file-button"
              onClick={() => fileRef.current?.click()}
            >
              选择 .txt / .md 文件
            </button>
            <span className="entry-file__hint">或拖到这里</span>
            {draft.source_ref && (
              <span className="entry-file__name" data-testid="entry-file-name">
                来自 {draft.source_ref} · {(draft.file_chars ?? 0).toLocaleString('en-US')} 字符
              </span>
            )}
            {undo && (
              <button
                type="button"
                className="entry-link"
                data-testid="entry-file-undo"
                onClick={() => {
                  draftStore.set(undo);
                  setUndo(null);
                }}
              >
                撤销替换
              </button>
            )}
          </div>
          {fileError && (
            <p className="entry-issue entry-issue--error" role="alert" data-testid="entry-file-error">
              {fileError}
            </p>
          )}
        </div>
      </div>

      <div className="entry-form__foot">
        <div className="entry-judgements">
          <label className={`entry-check${draft.exclamation ? ' is-locked' : ''}`}>
            <input
              type="checkbox"
              data-testid="entry-immediate"
              checked={immediateShown}
              disabled={draft.exclamation}
              aria-describedby="entry-immediate-note"
              onChange={(e) => draftStore.set({ immediate: e.target.checked })}
            />
            <span>是否为真（当下）</span>
          </label>
          <small id="entry-immediate-note" className="entry-check__note" data-testid="entry-immediate-note">
            {draft.exclamation
              ? '已由「断言为真」决定，不能单独更改'
              : draft.immediate
                ? '写入后待确认：要在展开的大脑里再判定一次，才会用于训练'
                : '不勾选：只保存这段话，不用于训练'}
          </small>
          <label className="entry-check">
            <input
              type="checkbox"
              data-testid="entry-exclamation"
              checked={draft.exclamation}
              aria-describedby="entry-exclamation-note"
              onChange={(e) => draftStore.set({ exclamation: e.target.checked })}
            />
            <span>断言为真</span>
          </label>
          <small id="entry-exclamation-note" className="entry-check__note" data-testid="entry-exclamation-note">
            {EXCLAMATION_NOTE}
          </small>
        </div>

        <ul className="entry-issues" aria-live="polite" data-testid="entry-issues">
          {reason && (
            <li className="entry-issue entry-issue--error" data-testid="entry-reason">
              {reason}
            </li>
          )}
          {validation.errors.map((m) => (
            <li key={m} className="entry-issue entry-issue--error" data-testid="entry-validation-error">
              {m}
            </li>
          ))}
          {validation.warnings.map((m) => (
            <li key={m} className="entry-issue entry-issue--warn" data-testid="entry-validation-warning">
              {m}
            </li>
          ))}
        </ul>

        <EntryError actions={['submit']} />

        <div className="entry-actions">
          <button
            type="submit"
            className="entry-submit"
            data-testid="entry-submit"
            disabled={!canSubmit}
            aria-disabled={!canSubmit}
          >
            {busy ? '写入中…' : '写入'}
          </button>
        </div>
      </div>
    </form>
  );
}
