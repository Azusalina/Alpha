/**
 * Global light / dark theme (round 3, decisions D38–D40).
 *
 * - Dark is the default (D40); light is the white scheme every acceptance gate
 *   was derived on, so the acceptance tests pin `?theme=light`.
 * - Dark = the light scheme inverted, plus a glow (D39): near-black ground
 *   (sampled from aes-ref/alpha-black-main-line.PNG: #050505, lines ≈ #f2f2f2),
 *   light plaster, and additively blended particles and lines.
 * - Switched from a small corner icon or the T key (D38); the choice persists.
 *   `?theme=light|dark` overrides for one page load (tests, screenshots).
 *
 * The silhouette view mode ignores all of this (pure white, ID colours).
 */

import { useSyncExternalStore } from 'react';

export type Theme = 'light' | 'dark';

export interface Palette {
  paper: string;
  paperDeep: string;
  ink: string;
  inkSoft: string;
  construction: string;
  sculptureLight: string;
  sculptureShadow: string;
  /** Lighting: hemisphere ground colour and fill colour. */
  lightGround: string;
  lightFill: string;
  /** Point / line glow: additive blending and a softer dot edge. */
  glow: boolean;
  /** Opacity multiplier for points and lines (additive light needs less). */
  inkAlpha: number;
}

export const PALETTES: Record<Theme, Palette> = {
  light: {
    paper: '#f4f2ee',
    paperDeep: '#eceae5',
    ink: '#1b1b1d',
    inkSoft: '#54565c',
    construction: '#7b7d85',
    sculptureLight: '#e6e1d7',
    sculptureShadow: '#9d9890',
    lightGround: '#b0aa9f',
    lightFill: '#eceae5',
    glow: false,
    inkAlpha: 1,
  },
  dark: {
    paper: '#050505',
    paperDeep: '#0d0d0e',
    ink: '#f2f2f2',
    inkSoft: '#c9cad0',
    construction: '#8a8c94',
    // plaster on a dark ground: still clearly lighter than the lines' shadows
    sculptureLight: '#bdb8ae',
    sculptureShadow: '#4a4743',
    lightGround: '#2a2826',
    lightFill: '#8d8a84',
    glow: true,
    inkAlpha: 0.72,
  },
};

const STORAGE_KEY = 'alpha.theme';

function initialTheme(): Theme {
  const q = new URLSearchParams(window.location.search).get('theme');
  if (q === 'light' || q === 'dark') return q;
  try {
    const s = window.localStorage.getItem(STORAGE_KEY);
    if (s === 'light' || s === 'dark') return s;
  } catch {
    // storage unavailable: fall through to the default
  }
  return 'dark';
}

class ThemeStore {
  private theme: Theme = initialTheme();
  private listeners = new Set<() => void>();

  constructor() {
    this.apply();
  }

  get = (): Theme => this.theme;

  palette(): Palette {
    return PALETTES[this.theme];
  }

  set(t: Theme): void {
    if (t === this.theme) return;
    this.theme = t;
    try {
      window.localStorage.setItem(STORAGE_KEY, t);
    } catch {
      // not persisted; the switch still applies to this session
    }
    this.apply();
    for (const l of this.listeners) l();
  }

  toggle(): void {
    this.set(this.theme === 'dark' ? 'light' : 'dark');
  }

  subscribe = (l: () => void): (() => void) => {
    this.listeners.add(l);
    return () => this.listeners.delete(l);
  };

  /** CSS reads the theme from the root element (styles.css). */
  private apply(): void {
    document.documentElement.dataset.theme = this.theme;
  }
}

export const themeStore = new ThemeStore();

export function useTheme(): Theme {
  return useSyncExternalStore(themeStore.subscribe, themeStore.get);
}

export function usePalette(): Palette {
  return PALETTES[useTheme()];
}
