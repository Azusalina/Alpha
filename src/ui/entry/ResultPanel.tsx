/**
 * What the entry area shows after a write (D54, D55): the form collapses to one
 * line with 再写一份, and under it the result of THIS input.
 *
 *  - `disagreed` (当下判断为否): saved, not used for training. There is no path
 *    to training from here: a preview may exist but it is not offered; the
 *    record can be edited or deleted in the brain's list (demo only today).
 *  - `pending` (当下为真, no assertion): the PREVIEW, hypothetical and possibly
 *    stale: translation cues as chips, the original text with the evidence
 *    marked (through spans.ts: code points, never UTF-16 slices), the effects.
 *    Nothing has trained: 展开大脑 leads to the list on the right where the second
 *    judgement is made.
 *  - `agreed` (断言为真): the FORMAL effects, with revision numbers. There is no
 *    preview and no second confirmation; the brain performs (inputStore does
 *    that). In demo mode the wording says it is not real training.
 *
 * Focus moves to the heading when a result appears (EntryPanel), and a polite
 * status line announces it. Escape closes the panel (`inputStore.closeTopLayer`).
 */

import { forwardRef, useEffect, useRef, useState } from 'react';
import type { RefObject } from 'react';

import { useBackend } from '../../backend';
import type { TranslationCue } from '../../backend';
import { inputStore, type SubmitOutcome, useInputs } from '../../app/inputStore';
import { codePointLength } from '../../backend';
import { EffectsTable } from '../shared/EffectsTable';
import { HighlightedText, marksFromEffects } from '../shared/HighlightedText';
import { KIND_LABELS, PARTITION_LABELS, partitionColor } from '../shared/labels';
import { StatusChip } from '../shared/StatusChip';
import { EntryError } from './EntryError';

export const PREVIEW_NOTE = '预览是假设值，可能过期；以确认后返回的正式结果为准';
export const SAVED_NOT_TRAINED = '已保存，不用于训练（当下判断为否）。可在展开的大脑右侧列表里编辑或删除。';
export const PENDING_NOTE = '尚未用于训练：展开大脑，在右侧列表里再次判定 T/F 后才会训练';
export const ASSERTED_NOTE = '已按你的断言直接用于训练';
export const ASSERTED_DEMO_NOTE = '演示：已按你的断言标记为直接训练。这是演示数据，没有运行模型，不会真的训练';

const MAX_CUES = 24;

interface Props {
  result: SubmitOutcome;
  onBrain: () => void;
}

function Cues({ cues }: { cues: readonly TranslationCue[] }) {
  if (cues.length === 0) return null;
  const shown = cues.slice(0, MAX_CUES);
  return (
    <div className="entry-cues" data-testid="entry-cues">
      <span className="entry-field__label">识别到的线索</span>
      <ul>
        {shown.map((c, i) => (
          <li
            key={`${c.category}:${c.span[0]}:${i}`}
            className="entry-cue"
            title={`${c.category} · ${c.value}`}
            data-testid="entry-cue"
          >
            {c.negated && <i>否定</i>}
            <span className="entry-cue__text">{c.evidence}</span>
            <small>{c.value}</small>
          </li>
        ))}
        {cues.length > shown.length && (
          <li className="entry-cue entry-cue--more">另有 {cues.length - shown.length} 个</li>
        )}
      </ul>
    </div>
  );
}

/**
 * True while the scroll box has content below the visible part. The result is
 * taller than the panel on common windows (1366x768 and smaller); the fade this
 * drives (`data-more`) tells the user there is more under the last visible row.
 */
function useMoreBelow(ref: RefObject<HTMLElement | null>): boolean {
  const [more, setMore] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const measure = () => setMore(el.scrollHeight - el.clientHeight - el.scrollTop > 6);
    measure();
    el.addEventListener('scroll', measure, { passive: true });
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    const mo = new MutationObserver(measure);
    mo.observe(el, { childList: true, subtree: true, characterData: true });
    return () => {
      el.removeEventListener('scroll', measure);
      ro.disconnect();
      mo.disconnect();
    };
  }, [ref]);
  return more;
}

export const ResultPanel = forwardRef<HTMLHeadingElement, Props>(function ResultPanel({ result, onBrain }, headingRef) {
  const backend = useBackend();
  const inputs = useInputs();
  const [active, setActive] = useState<string | null>(null);
  const demo = backend.mode === 'demo';
  const rootRef = useRef<HTMLDivElement | null>(null);
  const moreBelow = useMoreBelow(rootRef);

  const effects = result.trained ? result.effects : (result.preview?.effects ?? []);
  const marks = marksFromEffects(effects);
  const chars = codePointLength(result.text);

  // the judgement path in one phrase: what the user said when writing
  const path = result.exclamation ? '断言为真' : result.immediate === false ? '当下：否' : '当下：是';

  const announce = result.trained
    ? `已写入：已认可，${ASSERTED_NOTE}`
    : result.status === 'pending'
      ? `已写入：待确认，${result.previewState === 'ready' ? '预览已生成' : '正在生成预览'}`
      : '已写入：不同意，不用于训练';

  return (
    <div
      className="entry-result"
      ref={rootRef}
      data-more={moreBelow ? 'true' : undefined}
      data-testid="entry-result"
      data-status={result.status}
      data-partition={result.partition}
      data-source-id={result.source_id}
      data-trained={result.trained ? 'true' : 'false'}
    >
      <p className="entry-sr" role="status" aria-live="polite" data-testid="entry-announce">
        {announce}
      </p>

      <div className="entry-summary" data-testid="entry-summary">
        <h3 className="entry-summary__title" tabIndex={-1} ref={headingRef} data-testid="entry-result-heading">
          已写入
        </h3>
        <span className="entry-summary__facts">
          <i className="state-dot" style={{ background: partitionColor(result.partition) }} aria-hidden="true" />
          <span data-testid="entry-result-partition">{PARTITION_LABELS[result.partition]}</span>
          {' · '}
          {KIND_LABELS[result.kind]}
          {' · '}
          {chars.toLocaleString('en-US')} 字符
          {' · '}
          {path}
        </span>
        <button type="button" className="entry-link" data-testid="entry-again" onClick={inputStore.dismissResult}>
          再写一份
        </button>
      </div>

      <div className="entry-result__status">
        <StatusChip status={result.status} reason={result.reason} />
      </div>

      {/* the key message and the way on come FIRST: the evidence below can be long, and on a 1366x768 window it scrolls */}
      {result.status === 'pending' && (
        <div className="entry-result__block" data-testid="entry-pending-note">
          <p>{PENDING_NOTE}</p>
          <button type="button" className="entry-link" data-testid="entry-open-brain" onClick={onBrain}>
            展开大脑
          </button>
        </div>
      )}

      {result.status === 'disagreed' && (
        <div className="entry-result__block" data-testid="entry-saved-note">
          <p>{SAVED_NOT_TRAINED}</p>
          {!inputStore.can('inputEdit') && inputStore.can('submit') && (
            <p className="entry-result__fine">当前后端尚不支持编辑和删除；这两项只在演示模式可用。</p>
          )}
          <button type="button" className="entry-link" data-testid="entry-open-brain" onClick={onBrain}>
            展开大脑
          </button>
        </div>
      )}

      {result.trained && (
        <div className="entry-result__block" data-testid="entry-trained-note">
          <p>{demo ? ASSERTED_DEMO_NOTE : ASSERTED_NOTE}</p>
        </div>
      )}

      {result.status === 'pending' && (
        <p className="entry-result__fine" data-testid="entry-preview-note">
          {PREVIEW_NOTE}
        </p>
      )}

      {result.status === 'pending' && result.previewState === 'loading' && (
        <p className="entry-result__fine" data-testid="entry-preview-loading">
          正在生成预览…
        </p>
      )}
      {result.status === 'pending' && result.previewState === 'error' && (
        <p className="entry-result__fine" data-testid="entry-preview-failed">
          预览没有生成；这不影响已保存的这份内容。
        </p>
      )}
      <EntryError actions={['preview']} id={result.source_id} />

      {result.status === 'pending' && result.preview && <Cues cues={result.preview.translation.cues} />}

      {(result.trained || (result.status === 'pending' && result.previewState === 'ready')) && (
        <div className="entry-result__evidence">
          <span className="entry-field__label">{result.trained ? '原文与证据' : '原文与证据（预览）'}</span>
          <HighlightedText text={result.text} marks={marks} activeId={active} data-testid="entry-result-text" />
          <EffectsTable effects={effects} activeId={active} onActiveChange={setActive} />
        </div>
      )}

      {result.status === 'disagreed' && (
        <div className="entry-result__evidence">
          <span className="entry-field__label">原文</span>
          <HighlightedText text={result.text} data-testid="entry-result-text" />
        </div>
      )}

      {inputs.busy.submit && <p className="entry-result__fine">处理中…</p>}
    </div>
  );
});
