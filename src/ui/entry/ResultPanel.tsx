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
import { WithheldNotes } from '../shared/WithheldNotes';
import { HighlightedText, marksFromEffects } from '../shared/HighlightedText';
import { KIND_LABELS, PARTITION_LABELS, partitionColor } from '../shared/labels';
import { StatusChip } from '../shared/StatusChip';
import { EntryError } from './EntryError';
import { t } from '../../i18n/lang';







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
      <span className="entry-field__label">{t('result.cues')}</span>
      <ul>
        {shown.map((c, i) => (
          <li
            key={`${c.category}:${c.span[0]}:${i}`}
            className="entry-cue"
            title={`${c.category} · ${c.value}`}
            data-testid="entry-cue"
          >
            {c.negated && <i>{t('result.negated')}</i>}
            <span className="entry-cue__text">{c.evidence}</span>
            <small>{c.value}</small>
          </li>
        ))}
        {cues.length > shown.length && (
          <li className="entry-cue entry-cue--more">{t('result.more', { n: cues.length - shown.length })}</li>
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
  const path = result.exclamation ? t('result.path.assert') : result.immediate === false ? t('result.path.no') : t('result.path.yes');

  const announce = result.trained
    ? `${t('result.saved')}: ${t('result.agreed')}, ${t('result.asserted')}`
    : result.status === 'pending'
      ? `${t('result.saved')}: ${t('result.pending')}, ${result.previewState === 'ready' ? t('result.previewReady') : t('result.previewBusy')}`
      : `${t('result.saved')}: ${t('result.disagreed')}`;

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
          {t('result.saved')}
        </h3>
        <span className="entry-summary__facts">
          <i className="state-dot" style={{ background: partitionColor(result.partition) }} aria-hidden="true" />
          <span data-testid="entry-result-partition">{PARTITION_LABELS[result.partition]}</span>
          {' · '}
          {KIND_LABELS[result.kind]}
          {' · '}
          {t('result.chars', { n: chars.toLocaleString('en-US') })}
          {' · '}
          {path}
        </span>
        <button type="button" className="entry-link" data-testid="entry-again" onClick={inputStore.dismissResult}>
          {t('result.again')}
        </button>
      </div>

      <div className="entry-result__status">
        <StatusChip status={result.status} reason={result.reason} />
      </div>

      {/* the key message and the way on come FIRST: the evidence below can be long, and on a 1366x768 window it scrolls */}
      {result.status === 'pending' && (
        <div className="entry-result__block" data-testid="entry-pending-note">
          <p>{t('result.pendingNote')}</p>
          <button type="button" className="entry-link" data-testid="entry-open-brain" onClick={onBrain}>
            {t('result.openBrain')}
          </button>
        </div>
      )}

      {result.status === 'disagreed' && (
        <div className="entry-result__block" data-testid="entry-saved-note">
          <p>{t('result.savedNotTrained')}</p>
          {!inputStore.can('inputEdit') && inputStore.can('submit') && (
            <p className="entry-result__fine">{t('result.noEdit')}</p>
          )}
          <button type="button" className="entry-link" data-testid="entry-open-brain" onClick={onBrain}>
            {t('result.openBrain')}
          </button>
        </div>
      )}

      {result.trained && (
        <div className="entry-result__block" data-testid="entry-trained-note">
          <p>{demo ? t('result.assertedDemo') : t('result.asserted')}</p>
        </div>
      )}

      {result.status === 'pending' && (
        <p className="entry-result__fine" data-testid="entry-preview-note">
          {t('result.previewNote')}
        </p>
      )}

      {result.status === 'pending' && result.previewState === 'loading' && (
        <p className="entry-result__fine" data-testid="entry-preview-loading">
          {t('result.previewing')}
        </p>
      )}
      {result.status === 'pending' && result.previewState === 'error' && (
        <p className="entry-result__fine" data-testid="entry-preview-failed">
          {t('result.previewFailed')}
        </p>
      )}
      <EntryError actions={['preview']} id={result.source_id} />

      {result.status === 'pending' && result.preview && <Cues cues={result.preview.translation.cues} />}
      <WithheldNotes interpretation={result.trained ? result.interpretation : result.preview?.interpretation} />

      {(result.trained || (result.status === 'pending' && result.previewState === 'ready')) && (
        <div className="entry-result__evidence">
          <span className="entry-field__label">{result.trained ? t('result.textEvidence') : t('result.textEvidencePreview')}</span>
          <HighlightedText text={result.text} marks={marks} activeId={active} data-testid="entry-result-text" />
          <EffectsTable effects={effects} activeId={active} onActiveChange={setActive} />
        </div>
      )}

      {result.status === 'disagreed' && (
        <div className="entry-result__evidence">
          <span className="entry-field__label">{t('result.text')}</span>
          <HighlightedText text={result.text} data-testid="entry-result-text" />
        </div>
      )}

      {inputs.busy.submit && <p className="entry-result__fine">{t('busy.processing')}</p>}
    </div>
  );
});
