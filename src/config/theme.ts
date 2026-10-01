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
  /** The one restrained colour: a brain region answering the input box (D53). */
  accent: string;
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
    accent: '#3d6a8a',
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
    accent: '#9cc3e0',
  },
};

/**
 * Colours of the brain's answer to an input, by state (D57). There is no
 * parameter-to-region mapping (IDEA section 6 leaves the classification
 * undefined), so the performance is keyed by the input's state alone:
 *
 * - rational  one steady, muted hue (a deep slate-teal on paper, a pale steel
 *             blue on black): calm and composed;
 * - emotional a vivid spread, coral / amber / magenta / cyan / lime, darker and
 *             more saturated on white, luminous on black;
 * - crazy     the whole hue wheel, cycling; `s` and `v` are the saturation and
 *             value the shader gives that wheel in each theme.
 *
 * The names are the user's situational states, not a diagnosis.
 */
export interface StatePalette {
  rational: string;
  emotional: [string, string, string, string, string];
  crazy: { s: number; v: number };
}

export const STATE_PALETTE: Record<Theme, StatePalette> = {
  light: {
    rational: '#2a6a78',
    emotional: ['#d8402f', '#cc7a00', '#b71f78', '#0a86a6', '#4f9412'],
    crazy: { s: 0.92, v: 0.8 },
  },
  dark: {
    rational: '#7aa3cf',
    emotional: ['#ff7566', '#ffc247', '#ff52bd', '#4fe0ff', '#b4f25a'],
    crazy: { s: 0.78, v: 1 },
  },
};

const STORAGE_KEY = 'alpha.theme';

/**
 * `?capture=1`: acceptance captures. Hides the screen furniture that is not
 * part of the measured composition — the home divide line (D47) and the theme
 * switch — since every gate was derived without them.
 */
export const captureClean = new URLSearchParams(window.location.search).get('capture') === '1';

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
