/**
 * Global light / dark switch (decision D38): a small mark in the top-right
 * corner — the one corner no hot zone uses — nearly invisible until hovered,
 * plus the T key anywhere outside a text field. The choice persists
 * (config/theme.ts).
 *
 * Mounted from the moment home is first reached, never during startup, so the
 * startup screen stays clean (spec 2, 启动); absent in the dev capture view
 * modes, whose frames must hold the hands only.
 */

import { useEffect } from 'react';

import { captureClean, themeStore, useTheme } from '../config/theme';
import { useViewMode } from '../scene/useViewMode';

export function ThemeToggle() {
  const theme = useTheme();
  // the dev capture modes (docs/CONTRACTS.md §9) must contain nothing but the hands
  const viewMode = useViewMode();
  const next = theme === 'dark' ? '亮色' : '暗色';

  useEffect(() => {
    const on = (e: KeyboardEvent) => {
      if (e.key !== 't' && e.key !== 'T') return;
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) return;
      themeStore.toggle();
    };
    window.addEventListener('keydown', on);
    return () => window.removeEventListener('keydown', on);
  }, []);

  if (viewMode !== 'full' || captureClean) return null;

  return (
    <button
      type="button"
      className="theme-toggle"
      data-testid="theme-toggle"
      aria-label={`切换到${next}模式（T）`}
      title={`切换到${next}模式（T）`}
      onClick={() => themeStore.toggle()}
    >
      <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">
        {theme === 'dark' ? (
          // a sun: switch to light
          <g fill="none" stroke="currentColor" strokeWidth="1">
            <circle cx="8" cy="8" r="3" />
            <path d="M8 1.5v2M8 12.5v2M1.5 8h2M12.5 8h2M3.4 3.4l1.4 1.4M11.2 11.2l1.4 1.4M3.4 12.6l1.4-1.4M11.2 4.8l1.4-1.4" />
          </g>
        ) : (
          // a moon: switch to dark
          <path d="M11.5 10.5A5 5 0 0 1 5.5 4.5a5 5 0 1 0 6 6z" fill="none" stroke="currentColor" strokeWidth="1" />
        )}
      </svg>
    </button>
  );
}
