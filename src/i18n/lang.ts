/**
 * Language switch (English is the default; D67). One small store like the
 * theme's: the choice persists (localStorage, wrapped), `?lang=en|zh` overrides
 * it for one page load (tests, screenshots). Components call `useT()` so they
 * re-render on a switch; plain modules call `t()`, which reads the current
 * language at call time.
 */

import { useSyncExternalStore } from 'react';

import { en, type Key } from './en';
import { zh } from './zh';

export type Lang = 'en' | 'zh';

const STORAGE_KEY = 'alpha.lang';
const DICT: Record<Lang, Record<Key, string>> = { en, zh };

function initialLang(): Lang {
  // node-side tests import modules that read the language: no window there, English
  if (typeof window === 'undefined') return 'en';
  const q = new URLSearchParams(window.location.search).get('lang');
  if (q === 'en' || q === 'zh') return q;
  try {
    const s = window.localStorage.getItem(STORAGE_KEY);
    if (s === 'en' || s === 'zh') return s;
  } catch {
    // storage unavailable: the default
  }
  return 'en';
}

class LangStore {
  private lang: Lang = initialLang();
  private listeners = new Set<() => void>();

  constructor() {
    this.apply();
  }

  get = (): Lang => this.lang;

  set(l: Lang): void {
    if (l === this.lang) return;
    this.lang = l;
    try {
      window.localStorage.setItem(STORAGE_KEY, l);
    } catch {
      // not persisted: fine
    }
    this.apply();
    this.listeners.forEach((f) => f());
  }

  toggle(): void {
    this.set(this.lang === 'en' ? 'zh' : 'en');
  }

  subscribe = (f: () => void) => {
    this.listeners.add(f);
    return () => {
      this.listeners.delete(f);
    };
  };

  private apply(): void {
    if (typeof document === 'undefined') return;
    document.documentElement.lang = this.lang === 'zh' ? 'zh-CN' : 'en';
  }
}

export const langStore = new LangStore();

/** `{name}` placeholders are replaced from `vars`. */
export function t(key: Key, vars?: Record<string, string | number>): string {
  const s = DICT[langStore.get()][key] ?? en[key];
  if (!vars) return s;
  return s.replace(/\{(\w+)\}/g, (m, k: string) => (k in vars ? String(vars[k]) : m));
}

export function useLang(): Lang {
  return useSyncExternalStore(langStore.subscribe, langStore.get);
}

/** A `t` that makes the calling component re-render when the language changes. */
export function useT(): typeof t {
  useLang();
  return t;
}

/**
 * A record whose values follow the language: `labels(['a','b'], 'x.')['a']` is
 * `t('x.a')` at the moment it is read. For tables of labels that used to be
 * constants.
 */
export function lazyLabels<K extends string>(keys: readonly K[], prefix: string): Record<K, string> {
  const o = {} as Record<K, string>;
  for (const k of keys) Object.defineProperty(o, k, { enumerable: true, get: () => t(`${prefix}${k}` as Key) });
  return o;
}

/** `t` for a key built at run time: `fallback` when this language has no such key. */
export function tOr(key: string, fallback: string): string {
  return (DICT[langStore.get()] as Record<string, string>)[key] ?? fallback;
}

/** The locale for grouping digits in numbers shown to the user. */
export const numLocale = (): string => (langStore.get() === 'zh' ? 'zh-CN' : 'en-US');
