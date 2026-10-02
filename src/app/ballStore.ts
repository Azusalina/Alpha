/**
 * The ball page — the other side of the particle-brain page, reached by
 * clicking the divide line there. Two things live here: whether the page is
 * up (with a short cross-fade), and which of the two looks is showing.
 *
 *  - effect 1: monochrome line work (white on black, ink on paper), no fill;
 *  - effect 2: dark theme → dark gold with currents of brighter gold moving
 *    through it; light theme → black outline only.
 *
 * The look persists (localStorage, wrapped: it can throw). The main canvas is
 * paused while the page fully covers it (`covering`), see App.tsx.
 */

import { useSyncExternalStore } from 'react';

export type BallEffect = 1 | 2;

export interface BallUi {
  /** Mounted (also during the fade out). */
  mounted: boolean;
  /** Shown: drives the CSS fade. */
  shown: boolean;
  /** Fully opaque: the scene underneath need not render. */
  covering: boolean;
  effect: BallEffect;
}

const KEY = 'alpha.ball.effect';
const FADE_MS = 650;

function loadEffect(): BallEffect {
  try {
    return window.localStorage.getItem(KEY) === '2' ? 2 : 1;
  } catch {
    return 1;
  }
}

class BallStore {
  private ui: BallUi = { mounted: false, shown: false, covering: false, effect: loadEffect() };
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

  open(): void {
    if (this.ui.mounted && this.ui.shown) return;
    window.clearTimeout(this.timer);
    this.set({ mounted: true, shown: false, covering: false });
    // two frames: the element must exist at opacity 0 before the fade starts
    requestAnimationFrame(() =>
      requestAnimationFrame(() => {
        this.set({ shown: true });
        this.timer = window.setTimeout(() => this.set({ covering: true }), FADE_MS);
      }),
    );
  }

  close(): void {
    if (!this.ui.mounted) return;
    window.clearTimeout(this.timer);
    this.set({ shown: false, covering: false });
    this.timer = window.setTimeout(() => this.set({ mounted: false }), FADE_MS);
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
