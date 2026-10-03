/**
 * The entry (D54): the human destination's input box grew into this panel, in
 * the upper-right triangle above the divide line. It shows the back end's state
 * (BackendBanner), then either the form or, after a write, the result of that
 * write (`inputStore.lastResult`) with the form collapsed to one line.
 *
 * Fit. The area is the triangle above the diagonal, and it gets narrower toward
 * the bottom: the panel's lower-left corner is the point that would cross the
 * line first. So the panel's maximum height is measured, not guessed: from its
 * own top down to the diagonal at its left edge (`x_left * H / W`), minus a
 * margin, and its body scrolls inside that (`--entry-max-h`). It follows the
 * window size.
 *
 * Keys. Typing T never toggles the theme (the global key ignores text fields; the
 * panel also stops a T that lands on one of its buttons). Escape closes the result
 * (HumanPanel runs `inputStore.closeTopLayer` first); in the form it first leaves the
 * field when there is a draft.
 *
 * The container is the lightning's anchor: after a write that trains, the brain's
 * performance leaves from it (`ENTRY_ANCHOR`).
 */

import './entry.css';
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import type { KeyboardEvent } from 'react';

import { useBackend } from '../../backend';
import { ENTRY_ANCHOR, inputStore, useInputs } from '../../app/inputStore';
import { focusBrain } from '../../app/navigation';
import { BackendBanner } from '../shared/BackendBanner';
import { EntryForm } from './EntryForm';
import { ResultPanel } from './ResultPanel';
import { t } from '../../i18n/lang';

const MARGIN_PX = 18;
const MIN_HEIGHT_PX = 200;

function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(
    () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false,
  );
  useEffect(() => {
    const mq = window.matchMedia?.('(prefers-reduced-motion: reduce)');
    if (!mq) return;
    const on = () => setReduced(mq.matches);
    mq.addEventListener('change', on);
    return () => mq.removeEventListener('change', on);
  }, []);
  return reduced;
}

/** Sets `--entry-max-h` so the panel's lower-left corner stays above the divide line. */
function useAboveDivideLine(ref: React.RefObject<HTMLElement | null>): void {
  useLayoutEffect(() => {
    const el = ref.current;
    const parent = el?.offsetParent as HTMLElement | null;
    if (!el || !parent) return;
    const fit = () => {
      const W = parent.clientWidth;
      const H = parent.clientHeight;
      if (W === 0 || H === 0) return;
      const diagonalAtLeft = (el.offsetLeft * H) / W;
      const max = Math.max(MIN_HEIGHT_PX, diagonalAtLeft - el.offsetTop - MARGIN_PX);
      el.style.setProperty('--entry-max-h', `${Math.floor(max)}px`);
    };
    fit();
    const ro = new ResizeObserver(fit);
    ro.observe(parent);
    return () => ro.disconnect();
  }, [ref]);
}

export function EntryPanel() {
  const { lastResult } = useInputs();
  const backend = useBackend();
  const reduced = usePrefersReducedMotion();
  const rootRef = useRef<HTMLElement | null>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const seenResult = useRef<string | null>(lastResult?.source_id ?? null);

  useAboveDivideLine(rootRef);

  // a result that appears WHILE this panel is open takes the focus (a result that was already
  // there when the panel mounted does not); closing it gives the focus back to the text
  useEffect(() => {
    const id = lastResult?.source_id ?? null;
    if (id && id !== seenResult.current) headingRef.current?.focus();
    // the button that closed the result is gone, so the focus fell to the page: hand it to the text
    if (!id && seenResult.current && document.activeElement === document.body)
      document.getElementById('alpha-input')?.focus();
    seenResult.current = id;
  }, [lastResult]);

  const onKeyDown = (e: KeyboardEvent<HTMLElement>): void => {
    if ((e.key === 't' || e.key === 'T') && !e.ctrlKey && !e.metaKey && !e.altKey) e.stopPropagation();
  };

  const setRoot = useCallback((el: HTMLElement | null) => {
    rootRef.current = el;
    inputStore.registerAnchor(ENTRY_ANCHOR, el);
  }, []);

  return (
    <section
      className="human-panel__input entry-panel"
      data-testid="entry-panel"
      data-backend={backend.mode}
      aria-label={t('entry.aria')}
      ref={setRoot}
      onKeyDown={onKeyDown}
    >
      <BackendBanner />
      <div className="entry-body" data-testid="entry-body">
        {lastResult ? (
          <ResultPanel ref={headingRef} result={lastResult} onBrain={() => focusBrain(true, reduced)} />
        ) : (
          <EntryForm />
        )}
      </div>
    </section>
  );
}
