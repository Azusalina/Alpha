/**
 * The ball page — the other side of the particle-brain page, reached by
 * clicking the divide line there (and left by clicking the divide line here).
 * Three things live here: whether the page is up, which phase of the
 * transition it is in (D69: the brain flies into the ball and back; which of
 * the two flights is drawn is picked at random each time), and which of the
 * two looks is showing.
 *
 *  - effect 1: monochrome line work (white on black, ink on paper), no fill;
 *  - effect 2: dark theme → dark gold with currents of brighter gold moving
 *    through it; light theme → black outline only.
 *
 * The look persists (localStorage, wrapped: it can throw). The main canvas is
 * paused while the page fully covers it (`covering`), see App.tsx.
 */

import { useSyncExternalStore } from 'react';

import type { FxKind } from '../ball/transitionFx';
import { FX_KINDS } from '../ball/transitionFx';

export type BallEffect = 1 | 2;
export type BallPhase = 'closed' | 'entering' | 'open' | 'leaving';

export interface BallUi {
  /** Mounted (also during the fade out). */
  mounted: boolean;
  /** Shown: drives the CSS fade. */
  shown: boolean;
  /** Fully opaque: the scene underneath need not render. */
  covering: boolean;
  effect: BallEffect;
  phase: BallPhase;
  /** The flight being drawn while `entering` / `leaving`; null for a plain fade. */
  fx: FxKind | null;
}

const KEY = 'alpha.ball.effect';
/** A plain fade, and the two fades that open / close a flight (the flight's own pictures cross-fade with the page). */
export const FADE_MS = 650;
export const FX_FADE_IN_MS = 250;
export const FX_FADE_OUT_MS = 550;

function loadEffect(): BallEffect {
  try {
    return window.localStorage.getItem(KEY) === '2' ? 2 : 1;
  } catch {
    return 1;
  }
}

const reduced = (): boolean => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false;
const pick = (): FxKind => FX_KINDS[Math.floor(Math.random() * FX_KINDS.length)];

class BallStore {
  private ui: BallUi = { mounted: false, shown: false, covering: false, effect: loadEffect(), phase: 'closed', fx: null };
  private listeners = new Set<() => void>();
  private timer = 0;

  subscribe = (fn: () => void) => {
    this.listeners.add(fn);
    return () => {
      this.listeners.delete(fn);
    };
  };

  get = (): BallUi => this.ui;

  private set(patch: Partial<BallUi>): void {
    this.ui = { ...this.ui, ...patch };
    this.listeners.forEach((l) => l());
  }

  /** `kind` forces the flight (tests, screenshots); otherwise one is picked at random. */
  open(kind?: FxKind): void {
    if (this.ui.mounted && (this.ui.phase === 'entering' || this.ui.phase === 'open')) return;
    window.clearTimeout(this.timer);
    const plain = reduced();
    this.set({ mounted: true, shown: false, covering: false, phase: plain ? 'open' : 'entering', fx: plain ? null : (kind ?? pick()) });
    // two frames: the element must exist at opacity 0 before the fade starts
    requestAnimationFrame(() =>
      requestAnimationFrame(() => {
        this.set({ shown: true });
        // the page is opaque once it has faded in: the brain's canvas underneath can rest (during a flight too)
        this.timer = window.setTimeout(() => this.set({ covering: true }), plain ? FADE_MS : FX_FADE_IN_MS);
      }),
    );
  }

  /** The flight into the ball has landed. */
  finishEnter(): void {
    if (this.ui.phase === 'entering') this.set({ phase: 'open', fx: null });
  }

  close(kind?: FxKind): void {
    if (!this.ui.mounted || this.ui.phase === 'closed' || this.ui.phase === 'leaving') return;
    window.clearTimeout(this.timer);
    if (this.ui.phase === 'open' && !reduced()) {
      // the flight back: the page stays up (and the brain's canvas paused) until the brain has been rebuilt
      this.set({ phase: 'leaving', fx: kind ?? pick() });
      return;
    }
    this.fadeOut(FADE_MS);
  }

  /** The flight back to the brain has landed: show the brain underneath. */
  finishLeave(): void {
    if (this.ui.phase === 'leaving' && this.ui.fx) this.fadeOut(FX_FADE_OUT_MS);
  }

  /** Down at once, no flight (the page was left by another route). */
  dismiss(): void {
    window.clearTimeout(this.timer);
    if (this.ui.mounted) this.set({ mounted: false, shown: false, covering: false, phase: 'closed', fx: null });
  }

  private fadeOut(ms: number): void {
    window.clearTimeout(this.timer);
    this.set({ shown: false, covering: false, phase: 'leaving' });
    this.timer = window.setTimeout(() => this.set({ mounted: false, phase: 'closed', fx: null }), ms);
  }

  setEffect(effect: BallEffect): void {
    try {
      window.localStorage.setItem(KEY, String(effect));
    } catch {
      /* no persistence: fine */
    }
    this.set({ effect });
  }

  toggleEffect(): void {
    this.setEffect(this.ui.effect === 1 ? 2 : 1);
  }
}

export const ballStore = new BallStore();

export function useBall(): BallUi {
  return useSyncExternalStore(ballStore.subscribe, ballStore.get);
}
